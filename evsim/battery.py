"""Battery module added on top of a black-box dispatcher (mentor's framing, 2026-10-04).

GSM's real cost function is unknown, so it is treated as a black box C^GSM (in the simulator:
the B1 proxy, or any other policy via addon_base). The battery module only adds to it:

    C'_ij = C^GSM_ij  +  lambda * dP_reject(SOC_after_ij)      (b) expected rejection cost
    C'_ij = inf       if the car could not reach a charger after the trip   (a) feasibility
    plus timed charge nudges for idle low-SOC cars                          (c) not in the cost

Rationale of each component
(a) Safety constraint: never send a car on a trip after which it cannot reach the charger
    nearest the drop-off with soc_reserve left. Unit-free, no weight to tune.
(b) Drivers often decline a ride that would leave them low on battery (in the baselines about
    a third to two thirds of all declines are battery-related). Every decline costs the rider
    one more matching round and raises the chance they cancel. The term is the expected extra
    declines caused by battery, dP = P(decline | SOC after trip) - P(decline | high SOC), with
    P(decline | SOC) estimated from offer logs (scripts/fit_reject_curve.py; simulated logs for
    now, GSM's accept/decline logs with SOC later). lambda is the black-box cost of one
    expected decline; since the black box's units are unknown, lambda is swept.
(c) Time spent charging costs most at the peaks. Idle cars below a time-of-day SOC level are
    asked to charge: higher just before the peaks (enter them charged), lower during them.

What the platform knows about SOC is set by soc_info: exact | noise (telemetry error) |
stale (periodic reports) | coarse (SOC only in bands), for the information ablation.
"""
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from . import values
from .dispatch import BIG, POLICIES
from .geo import road_km


class RejectCurve:
    """Empirical decline rate as a function of SOC after the trip (monotone, interpolated)."""

    def __init__(self, path):
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        self.x = np.array(d["soc_after"])
        self.p = np.array(d["p_decline"])
        self.base = float(d["p_base"])

    def excess(self, soc_after):
        """Extra decline probability caused by battery, relative to a well-charged car."""
        return np.maximum(0.0, np.interp(soc_after, self.x, self.p) - self.base)


class BatteryAddOn:
    """Wraps a black-box policy (cfg.addon_base) and adds the battery components that are on."""

    name = "battery_addon"

    def __init__(self, cfg):
        self.cfg = cfg
        self.base = POLICIES[cfg.addon_base](cfg)
        self.forward = getattr(self.base, "forward", False)
        self.reposition = getattr(self.base, "reposition", False)
        self.charge_nudge = cfg.addon_nudge or cfg.addon_mask_nudge
        self.regular_nudge = cfg.addon_nudge   # time-of-day / smart nudges (off: only mask-triggered ones)
        self.flagged = set()                   # idle cars the safety mask shut out of most trips
        self.home_nudge = cfg.addon_home_nudge
        self.curve = RejectCurve(cfg.reject_curve) if cfg.addon_reject else None
        self.noise_rng = np.random.default_rng(cfg.seed + 7919)  # separate from the simulation RNG
        self.reports = {}  # vehicle id -> (report time, reported SOC) for stale telemetry

    def attach(self, sim):
        self.sim = sim
        self.stations = sim.stations
        self.last_scale = 1.0
        self.veto = None
        if hasattr(self.base, "attach"):
            self.base.attach(sim)
        if getattr(self.base, "V", None) is not None:   # L3 possible: the black box exposes V
            self.v_q25 = True

    def solve(self, cost):
        """The black box's own solver (Hungarian unless it has one); at level 0 the safety rule
        can only veto solved pairs (marked BIG, so the simulator skips them)."""
        rows, cols = getattr(self.base, "solve", linear_sum_assignment)(cost)
        if self.veto is not None:
            for i, j in zip(rows, cols):
                if self.veto[i, j]:
                    cost[i, j] = BIG
            self.veto = None
        return rows, cols

    def target_nudges(self, t):
        """Supply-target nudges before a peak: how many idle cars must start charging now so that
        target_share of the cars on shift reach the peak with SOC >= target_soc, and which ones
        (lowest SOC first, closest to a free charger first), capped by the free ports."""
        c, sim = self.cfg, self.sim
        on_shift = [v for v in sim.vehicles if v.status != "off"]
        charging = ("to_station", "queued", "charging")
        ready = sum((max(v.soc, v.charge_target) if v.status in charging else v.soc) >= c.target_soc
                    for v in on_shift)
        need = int(np.ceil(c.target_share * len(on_shift))) - ready
        free = int(np.maximum(0, sim.ports_available(t) - sim.ports_busy
                              - np.array([len(q) for q in sim.queues])).sum())
        need = min(need, free)
        if need <= 0:
            return set()
        idle = [v for v in on_shift if v.status == "idle" and self.observe_soc(v, t) < c.target_soc
                and v.charge_target >= c.target_soc]
        if not idle:
            return set()
        free_st = (sim.ports_available(t) - sim.ports_busy - np.array([len(q) for q in sim.queues])) > 0
        st = self.stations[free_st] if free_st.any() else self.stations
        km = road_km(np.array([v.lat for v in idle])[:, None], np.array([v.lon for v in idle])[:, None],
                     st[None, :, 0], st[None, :, 1], c.detour).min(axis=1)
        score = np.array([self.observe_soc(v, t) for v in idle]) + 0.02 * km   # 1 km ~ 2 % SOC
        return {idle[i].id for i in np.argsort(score)[:need]}

    def nudge_value(self, v, t, soc, level):
        """L3 nudges: the time-of-day rule, but a car standing where the black box values it
        highly is not pulled off the road unless low (< 15 %), and a car standing where it is worth
        little is sent to top up below 60 % outside the peaks ("highly" / "little" = top / bottom
        quartile of V among the idle cars at that moment)."""
        c = self.cfg
        if not hasattr(self, "v_q25"):
            return soc < level
        k = values.slot(t)
        if getattr(self, "_v_t", None) != t:   # quartiles over the idle cars right now
            idle = [u for u in self.sim.vehicles if u.status == "idle"]
            vals = self.base.V[self.base.grid.cell([u.lat for u in idle], [u.lon for u in idle]), k]
            self._v_t, (self._q25, self._q75) = t, np.percentile(vals, [25, 75])
        val = self.base.V[self.base.grid.cell(v.lat, v.lon), k]
        h = (t / 3600) % 24
        in_peak = any(a <= h < b for a, b in c.nudge_peak_hours)
        if soc < level:
            return soc < 0.15 or val < self._q75
        return not in_peak and soc < 0.60 and val <= self._q25

    # ---- what the platform knows about a car's battery ----
    def observe_soc(self, v, t):
        c = self.cfg
        if c.soc_info == "exact":
            return v.soc
        if c.soc_info == "noise":
            return float(np.clip(v.soc + self.noise_rng.normal(0, c.soc_noise_sd), 0, 1))
        if c.soc_info == "stale":
            t_rep, soc = self.reports.get(v.id, (-np.inf, v.soc))
            if t - t_rep >= c.soc_report_min * 60:
                t_rep, soc = t, v.soc
                self.reports[v.id] = (t_rep, soc)
            return soc
        if c.soc_info == "coarse":
            step = c.soc_coarse_step
            return min(1.0, (np.floor(v.soc / step) + 0.5) * step)
        raise ValueError(f"unknown soc_info {c.soc_info}")

    def cost_matrix(self, cands, riders, t):
        cost, pickup_km = self.base.cost_matrix(cands, riders, t)
        c = self.cfg
        if not (c.addon_feasible or c.addon_reject or c.addon_station_bonus or c.addon_prepeak_bonus
                or c.addon_soft_margin):
            return cost, pickup_km
        ok = cost < BIG / 2
        scale = self.cost_scale(cost, ok)
        soc_per_km = c.kwh_per_km / c.battery_kwh
        if c.addon_level >= 2:   # SOC when the car becomes free (forward: minus its current leg)
            soc0 = np.array([self.observe_soc(cd.v, t) - (cd.v.soc - cd.soc) for cd in cands])[:, None]
        else:                    # L0/L1: only today's SOC is known
            soc0 = np.array([self.observe_soc(cd.v, t) for cd in cands])[:, None]
        trip_km = np.array([r.trip_km for r in riders])[None, :]
        soc_after = soc0 - (pickup_km + trip_km) * soc_per_km
        if c.addon_reject and c.addon_level >= 1:
            q = self.curve.excess(soc_after) if c.driver_model == "legacy" else self.decline_risk(cands, soc_after)
            cost = self.combine(cost, scale * q)
        if c.addon_station_bonus:
            if c.driver_model == "legacy":
                low = np.clip((c.station_bonus_soc - soc_after) / 0.15, 0.0, 1.0)
            else:   # the driver will head to a charger right after this drop-off
                low = self.self_charge_prob(cands, soc_after)
            near = np.clip(1.0 - self.free_charger_km(riders, t) / c.station_bonus_radius_km, 0.0, 1.0)[None, :]
            cost = cost - c.addon_station_bonus * scale * low * near
        if c.addon_prepeak_bonus and self.in_prepeak(t) and len(cands) > len(riders):
            cost = cost - c.addon_prepeak_bonus * scale * soc0
        if c.addon_station_bonus or c.addon_prepeak_bonus:
            cost = np.where(ok, cost, BIG)   # bonuses never revive a pair the black box ruled out
        if c.addon_feasible or c.addon_soft_margin:
            d_lat = np.array([r.d_lat for r in riders])[:, None]
            d_lon = np.array([r.d_lon for r in riders])[:, None]
            to_charger = road_km(d_lat, d_lon, self.stations[None, :, 0], self.stations[None, :, 1],
                                 c.detour).min(axis=1)[None, :]
            left = soc_after - to_charger * soc_per_km     # SOC left on reaching the nearest charger
            if c.addon_soft_margin:
                short = np.clip(1.0 - (left - c.soc_reserve) / c.soft_margin_width, 0.0, 1.0)
                cost = np.where(ok, cost + c.addon_soft_margin * scale * short, cost)
            if c.addon_feasible:
                masked = left < c.soc_reserve
                if c.addon_level == 0:
                    self.veto = masked.copy()   # applied after the black box has solved
                else:
                    cost[masked] = BIG
                if c.addon_mask_nudge:
                    self.flag_masked(cands, ok, masked, t)
        return cost, pickup_km

    def forced_nudge(self, v, t):
        """Nudge regardless of the time of day: the safety mask (a) leaves this car near-useless,
        either seen in the batches (flagged) or because its SOC cannot cover a typical trip."""
        c = self.cfg
        if not c.addon_mask_nudge:
            return False
        if v.id in self.flagged:
            return True
        return self.observe_soc(v, t) < c.soc_reserve + c.mask_nudge_km * c.kwh_per_km / c.battery_kwh

    def flag_masked(self, cands, ok, masked, t):
        """Remember idle cars that the safety mask shuts out of >= mask_nudge_share of the trips their black
        box would consider (at least 3): they should charge now, not idle."""
        n_ok = ok.sum(axis=1)
        n_masked = (ok & masked).sum(axis=1)
        for i, cd in enumerate(cands):
            if cd.t_avail <= t and n_ok[i] >= 3 and n_masked[i] >= self.cfg.mask_nudge_share * n_ok[i]:
                self.flagged.add(cd.v.id)

    # ---- driver model (pooled / oracle; docs/driver_model_design.md) ----
    def thresholds(self, cands, t=None):
        """Per-candidate charging thresholds (oracle), shape (n, 1); with heterogeneous drivers
        including the end-of-shift rise (the per-decision noise is not knowable)."""
        if t is None or not self.cfg.driver_hetero:
            return np.array([cd.v.soc_threshold for cd in cands])[:, None]
        return np.array([cd.v.soc_threshold + (cd.v.end_shift_extra if cd.v.shift_end - cd.t_avail < 7200 else 0.0)
                         for cd in cands])[:, None]

    def population_rule(self):
        """Fleet-average decline margin and sharpness (what a pooled model would estimate)."""
        c = self.cfg
        if c.driver_hetero:
            return float(np.mean(c.hetero_margin)), float(np.mean(c.hetero_scale))
        return c.ride_reject_soc_margin, c.ride_reject_soc_scale

    def population_grid(self):
        c = self.cfg
        return np.linspace(c.soc_threshold_min, c.soc_threshold_max, 9)

    def _decline_given_thr(self, thr, soc_after, margin=None, scale=None):
        """The drivers' battery-decline rule for a known threshold, minus the same rule at full SOC."""
        c = self.cfg
        if not c.driver_soc_decline:
            return np.zeros(np.broadcast(thr, soc_after).shape)
        if margin is None:
            margin, scale = self.population_rule()
        f = lambda x: 1.0 / (1.0 + np.exp(-(thr + margin - x) / scale))
        return f(soc_after) - f(1.0)

    def decline_risk(self, cands, soc_after):
        """q = extra decline probability caused by battery for this pair."""
        if self.cfg.driver_model == "oracle":
            m = np.array([cd.v.soc_margin for cd in cands])[:, None]
            sc = np.array([cd.v.soc_scale for cd in cands])[:, None]
            return self._decline_given_thr(self.thresholds(cands, 0), soc_after, m, sc)
        grid = self.population_grid()   # pooled: average over the fleet's threshold distribution
        return np.mean([self._decline_given_thr(th, soc_after) for th in grid], axis=0)

    def self_charge_prob(self, cands, soc_after):
        """Probability that the driver goes to charge right after the drop-off (SOC below threshold)."""
        c = self.cfg
        if c.driver_model == "oracle":
            return np.clip((self.thresholds(cands, 0) + 0.02 - soc_after) / 0.04, 0.0, 1.0)
        return np.clip((c.soc_threshold_max - soc_after) / (c.soc_threshold_max - c.soc_threshold_min), 0.0, 1.0)

    def nudge_wanted(self, v, t, soc):
        """Smart nudge: shortly before a peak, send the car to charge if at the usual drain rate it
        would reach its driver's threshold before the peak ends (it would then charge in the peak)."""
        c = self.cfg
        h = (t / 3600) % 24
        for a, b in c.nudge_peak_hours:
            if a - c.nudge_lookahead_h <= h < a:
                extra = v.end_shift_extra if c.driver_hetero and v.shift_end - t < 7200 else 0.0
                thr = v.soc_threshold + extra if c.driver_model == "oracle" else \
                    float(np.median(self.population_grid()))
                return soc - c.drain_soc_per_h * (b - h) < thr + c.smart_nudge_margin
        return False

    def cost_scale(self, f, ok):
        """Unit of the battery terms: 1 (black-box units) or the IQR of the feasible costs."""
        if self.cfg.addon_scale == "none":
            return 1.0
        if ok.sum() >= 4:
            q75, q25 = np.percentile(f[ok], [75, 25])
            if q75 - q25 > 1e-9:
                self.last_scale = float(q75 - q25)
        return self.last_scale   # tiny batches reuse the last good scale

    def free_charger_km(self, riders, t):
        """Road km from each drop-off to the nearest station with a free port right now."""
        sim = self.sim
        free = (sim.ports_available(t) - sim.ports_busy - np.array([len(q) for q in sim.queues])) > 0
        if not free.any():
            return np.full(len(riders), np.inf)
        st = self.stations[free]
        d_lat = np.array([r.d_lat for r in riders])[:, None]
        d_lon = np.array([r.d_lon for r in riders])[:, None]
        return road_km(d_lat, d_lon, st[None, :, 0], st[None, :, 1], self.cfg.detour).min(axis=1)

    def in_prepeak(self, t):
        h = (t / 3600) % 24
        return any(a <= h < b for a, b in self.cfg.nudge_prepeak_hours)

    def combine(self, f, g):
        """G(F, B): how the black-box cost F and the battery term g = dP_decline(SOC after) are joined.

        All forms give G = F when g = 0 (well-charged car), grow with F and grow with g.
        add       F + lambda*g                     (g priced in F's units by lambda)
        mult      F+ * (1 + lambda*g)              (scale-free; F+ = F shifted so the batch minimum is
                                                    addon_shift_km, which leaves the ranking by F unchanged)
        tiebreak  F + addon_tiebreak*g             (battery only decides between near-equal F)
        hard      F, or BIG if g > addon_hard_p    (battery as a filter instead of a price)
        """
        c = self.cfg
        if c.addon_form == "add":
            return f + c.addon_lambda * g
        if c.addon_form == "tiebreak":
            return f + c.addon_tiebreak * g
        if c.addon_form == "hard":
            return np.where(g > c.addon_hard_p, BIG, f)
        if c.addon_form == "mult":
            ok = f < BIG / 2
            if not ok.any():
                return f
            f_pos = f - f[ok].min() + c.addon_shift_km
            return np.where(ok, f_pos * (1.0 + c.addon_lambda * g), f)
        raise ValueError(f"unknown addon_form {c.addon_form}")


POLICIES[BatteryAddOn.name] = BatteryAddOn
