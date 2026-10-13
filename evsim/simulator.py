"""Batch time-step simulator for an EV ride-hailing fleet.

Each step (cfg.batch_s): finish legs and timed states that ended, start queued charging
sessions, add new requests, drop riders who ran out of patience, then match idle vehicles
to waiting riders.

With cfg.shifts the fleet follows driver shifts: each driver has a personal shift start and
online length, a 10 h/day driving cap, a 4 h continuous-driving cap (reset by a stop of at
least rest_reset_min), one meal break (used for charging when SOC is low) and optional
overnight charging at home/depot.
"""
import heapq
from collections import defaultdict, deque
from pathlib import Path
from dataclasses import dataclass, field
from typing import NamedTuple, Optional

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.stats import truncnorm

from . import demand, geo, ocp1
from .config import EXTERNAL_OCCUPANCY
from .dispatch import BIG
from .economics import fare
from .geo import road_km, travel_s

IDLE, TO_PICKUP, ON_TRIP, TO_STATION, QUEUED, CHARGING, TOWED, BREAK, OFF, REPOSITION = (
    "idle", "to_pickup", "on_trip", "to_station", "queued", "charging", "towed", "break", "off",
    "reposition")
DRIVING = (TO_PICKUP, ON_TRIP, TO_STATION, REPOSITION)
DAY_S = 86400.0
DATA = Path(__file__).resolve().parent.parent / "data"
STATIONS_CSV = {"osm": DATA / "stations_osm.csv", "google": DATA / "stations_google.csv"}

# random streams used with cfg.crn (one per kind of draw)
(S_JITTER, S_NIGHT, S_ONLINE, S_MEAL, S_REST, S_REBOOK, S_REBOOK_DELAY, S_REBOOK_PATIENCE,
 S_DECLINE_SOC, S_DECLINE_OTHER, S_RESPONSE, S_REPO_ACCEPT, S_REPO_LAT, S_REPO_LON, S_NUDGE,
 S_THR_NOISE, S_TARGET_NOISE) = range(1, 18)
S_SHIFT_EST = 18
M64 = (1 << 64) - 1


def _mix(x):
    """splitmix64 finaliser."""
    x = (x + 0x9E3779B97F4A7C15) & M64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & M64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & M64
    return x ^ (x >> 31)


class Cand(NamedTuple):
    """Matching candidate: a vehicle, when it becomes available, where, and its SOC then."""
    v: "Vehicle"
    t_avail: float
    lat: float
    lon: float
    soc: float


@dataclass
class Vehicle:
    id: int
    lat: float
    lon: float
    soc: float
    soc_threshold: float
    home: tuple = (0.0, 0.0)
    charge_target: float = 1.0  # SOC at which this driver unplugs at a public station
    status: str = IDLE
    t_free: float = np.inf     # end time of the current leg / timed state
    # current leg
    dest: tuple = (0.0, 0.0)
    leg_km: float = 0.0
    leg_s: float = 0.0
    leg_kind: str = ""         # deadhead | trip | to_station
    request: Optional[demand.Request] = None
    next_request: Optional[demand.Request] = None   # forward dispatch: rider queued after this leg
    outcome: str = ""          # what happens when the leg/state ends
    station: int = -1
    t_queued: float = 0.0
    idle_since: float = 0.0
    repo_cooldown_until: float = 0.0
    nudge_cooldown_until: float = 0.0
    home_charge_done: bool = False
    # personal behaviour (cfg.driver_hetero; otherwise the fleet-wide values)
    soc_margin: float = 0.05
    soc_scale: float = 0.02
    end_shift_extra: float = 0.0
    nudge_p: float = 1.0
    # shift
    shift_offset_h: float = 0.0
    shift_len_h: float = 12.0
    day: int = 0
    shift_start: float = 0.0
    shift_end: float = np.inf
    shift_end_est: float = np.inf          # platform's belief about shift_end (cfg.shift_end_info)
    drive_today_s: float = 0.0
    drive_cont_s: float = 0.0
    t_stop: Optional[float] = None
    meal_done: bool = True
    meal_at: float = 0.0
    rest_done: bool = True
    rest_at: float = 0.0
    online_s: float = 0.0
    drive_s: float = 0.0
    trip_s: float = 0.0        # time with a passenger on board
    shifts_ended_by_drive_cap: int = 0
    km: dict = field(default_factory=lambda: {"deadhead": 0.0, "trip": 0.0, "to_station": 0.0,
                                                    "reposition": 0.0, "home": 0.0})


class Simulator:
    def __init__(self, cfg, policy):
        self.cfg = cfg
        self.policy = policy
        self.rng = np.random.default_rng(cfg.seed)
        geo.set_router(cfg.road_network)
        self.requests = (ocp1.generate if cfg.demand_model == "ocp1" else demand.generate)(cfg, self.rng)
        self.future = [(r.t, r.id) for r in self.requests]      # heap of requests not yet placed
        heapq.heapify(self.future)
        if cfg.real_stations and cfg.station_source == "ocp1":
            self.stations, self.ports, self.station_kw = ocp1.load_stations(cfg)
        elif cfg.real_stations:
            self.stations, self.ports, self.station_kw = demand.load_stations(
                cfg, STATIONS_CSV[cfg.station_source])
        else:
            self.stations = demand.sample_stations(cfg, self.rng)
            self.ports = np.full(cfg.n_stations, cfg.ports_per_station)
            self.station_kw = np.full(cfg.n_stations, cfg.dc_kw)
        if cfg.port_scale != 1.0:
            self.ports = np.maximum(1, np.round(self.ports * cfg.port_scale)).astype(int)
        self.ports_busy = np.zeros(len(self.stations), dtype=int)
        self.queues = [deque() for _ in range(len(self.stations))]
        if hasattr(policy, "attach"):
            policy.attach(self)  # battery-aware policies need the station list

        lat, lon = (ocp1.sample_points if cfg.demand_model == "ocp1" else demand.sample_points)(self.rng, cfg.n_vehicles)
        thr = self.rng.uniform(cfg.soc_threshold_min, cfg.soc_threshold_max, cfg.n_vehicles)
        self.vehicles = [Vehicle(i, lat[i], lon[i], self.sample_soc0(), thr[i], home=(lat[i], lon[i]))
                         for i in range(cfg.n_vehicles)]
        if cfg.driver_charge_targets:
            low = self.rng.random(cfg.n_vehicles) < cfg.charge_target_low_share
            t_low = self.rng.uniform(*cfg.charge_target_low, cfg.n_vehicles)
            t_high = self.rng.uniform(*cfg.charge_target_high, cfg.n_vehicles)
            for v, is_low, a, b in zip(self.vehicles, low, t_low, t_high):
                v.charge_target = float(a if is_low else b)
        else:
            for v in self.vehicles:
                v.charge_target = cfg.soc_target

        for v in self.vehicles:
            v.soc_margin, v.soc_scale, v.nudge_p = cfg.ride_reject_soc_margin, cfg.ride_reject_soc_scale, cfg.nudge_accept_p
        if cfg.driver_hetero:
            n = cfg.n_vehicles
            mar = self.rng.uniform(*cfg.hetero_margin, n)
            sca = self.rng.uniform(*cfg.hetero_scale, n)
            ext = self.rng.uniform(0.0, cfg.hetero_end_shift_max, n)
            a = cfg.nudge_accept_mean * cfg.nudge_accept_kappa
            nud = self.rng.beta(a, cfg.nudge_accept_kappa - a, n)
            for v, m_, s_, e_, p_ in zip(self.vehicles, mar, sca, ext, nud):
                v.soc_margin, v.soc_scale, v.end_shift_extra, v.nudge_p = float(m_), float(s_), float(e_), float(p_)

        self.pool = []                 # waiting, unassigned riders
        self.kwh_at_plug = 0.0         # public stations
        self.kwh_night = 0.0           # overnight home/depot charging
        self.strandings = 0
        self.repositions = 0
        self.repo_offers = 0
        self.forward_assigns = 0
        self.ride_offers = 0
        self.ride_rejects = 0
        self.ride_rejects_soc = 0
        self.rebooks = 0
        self.charge_nudges = 0
        self.nudge_offers = 0
        self.home_runouts = 0          # drives home off duty that would empty the battery
        self.home_nudges = 0           # end-of-shift requests to charge at home overnight
        self.strand_log = []           # one record per vehicle that ran empty on a leg
        self.leg_log = [] if cfg.log_moves else None     # (vehicle, t0, t1, from, to, kind, soc0, soc1)
        self.state_log = [] if cfg.log_moves else None   # (t, vehicle, status, soc, lat, lon, station)
        self.e0_kwh = self.e_end_kwh = 0.0   # energy stored in all batteries at start / end
        self.rejected = defaultdict(set)   # vehicle id -> request ids the driver declined
        self.accepted = set()          # pairs already accepted (forward offers are re-solved)
        self.charge_log = []           # (vehicle, station, t_queued, t_start, t_end, soc_from, soc_to)
        self.snapshots = []            # (t, vehicle, status, soc) every 15 min
        self.idle_log = None           # set to [] to log (t, lat, lon) of idle cars every 10 min
        self.offer_log = None          # set to [] to log (soc_after, pickup_km, rejected) per ride offer

        if cfg.shifts:
            starts = np.array(cfg.shift_starts)
            groups = self.rng.choice(len(starts), cfg.n_vehicles, p=starts[:, 2] / starts[:, 2].sum())
            for v, g in zip(self.vehicles, groups):
                v.shift_offset_h = self.rng.uniform(starts[g, 0], starts[g, 1])
                v.shift_len_h = starts[g, 3]
                v.day = -1
                # a shift that started yesterday evening may still be running at t = 0
                start_prev = (v.shift_offset_h - 24) * 3600
                self.start_shift(v, start_prev)
                if v.shift_end > 0:
                    v.meal_done = v.meal_at <= 0
                    v.rest_done = v.rest_done or v.rest_at <= 0
                    v.t_stop = 0.0
                else:
                    self.go_off(v, 0.0, night_charge=False, initial=True)

    # ---------- random draws ----------
    def u01(self, stream, a, b=0):
        """Uniform [0, 1) fixed by (seed, stream, a, b): the common-random-numbers draw."""
        x = _mix(self.cfg.seed & M64)
        for k in (stream, a, b):
            x = _mix(x ^ (int(k) & M64))
        return (x >> 11) * (1.0 / (1 << 53))

    def draw_u(self, stream, a, b=0):
        return self.u01(stream, a, b) if self.cfg.crn else self.rng.random()

    def draw_uniform(self, lo, hi, stream, a, b=0):
        return lo + (hi - lo) * self.u01(stream, a, b) if self.cfg.crn else self.rng.uniform(lo, hi)

    def draw_exp(self, mean, stream, a, b=0):
        return -mean * np.log1p(-self.u01(stream, a, b)) if self.cfg.crn else self.rng.exponential(mean)

    def draw_normal(self, mu, sd, stream, a, b=0):
        if not self.cfg.crn:
            return self.rng.normal(mu, sd)
        u1, u2 = self.u01(stream, a, b), self.u01(stream + 1000, a, b)
        return mu + sd * np.sqrt(-2.0 * np.log1p(-u1)) * np.cos(2.0 * np.pi * u2)

    # ---------- energy / charging helpers ----------
    def sample_soc0(self):
        c = self.cfg
        a, b = (0 - c.soc0_mean) / c.soc0_sd, (1 - c.soc0_mean) / c.soc0_sd
        return float(truncnorm.rvs(a, b, loc=c.soc0_mean, scale=c.soc0_sd, random_state=self.rng))

    def soc_for_km(self, km):
        return km * self.cfg.kwh_per_km / self.cfg.battery_kwh

    def charge_time_s(self, a, b, kw):
        c = self.cfg
        fast = max(0.0, min(b, c.taper_soc) - a) * c.battery_kwh / kw
        slow = max(0.0, b - max(a, c.taper_soc)) * c.battery_kwh / min(kw, c.taper_kw)
        return (fast + slow) * 3600.0

    def nearest_station(self, lat, lon):
        d = road_km(lat, lon, self.stations[:, 0], self.stations[:, 1], self.cfg.detour)
        k = int(np.argmin(d))
        return k, float(d[k])

    def ports_available(self, t):
        if not self.cfg.external_occupancy:
            return self.ports
        occ = EXTERNAL_OCCUPANCY[int(t / 3600) % 24]
        return np.maximum(1, self.ports - np.round(self.ports * occ).astype(int))

    # ---------- driver rest bookkeeping ----------
    def mark_stop(self, v, t):
        if v.t_stop is None:
            v.t_stop = t

    def settle_rest(self, v, t):
        """A stop of at least rest_reset_min resets the continuous-driving counter."""
        if v.t_stop is not None and t - v.t_stop >= self.cfg.rest_reset_min * 60:
            v.drive_cont_s = 0.0

    # ---------- shifts ----------
    def go_off(self, v, t, night_charge=True, initial=False):
        c = self.cfg
        if not initial:
            v.online_s += t - max(v.shift_start, 0.0)
            if v.drive_today_s >= c.max_drive_h_day * 3600:
                v.shifts_ended_by_drive_cap += 1
        v.status, v.outcome = OFF, "shift_start"
        v.request = None
        if c.home_mode and not initial:
            # drive home off duty (energy still comes out of the battery)
            km = float(road_km(v.lat, v.lon, v.home[0], v.home[1], c.detour))
            if self.soc_for_km(km) > v.soc:
                self.home_runouts += 1
            v.soc = max(0.0, v.soc - self.soc_for_km(km))
            v.km["home"] += km
            v.lat, v.lon = v.home
        # next shift starts on the first day whose start time is still ahead
        while True:
            v.day += 1
            jitter = self.draw_normal(0, c.shift_start_jitter_min / 60, S_JITTER, v.id, v.day)
            start = v.day * DAY_S + (v.shift_offset_h + jitter) * 3600
            if start > t:
                break
        v.t_free = start
        p_night = c.p_night_charge
        if night_charge and getattr(self.policy, "home_nudge", False) and v.soc < c.home_nudge_soc:
            self.home_nudges += 1          # asked to charge at home tonight (same draw: only adds chargers)
            p_night = p_night + (1.0 - p_night) * c.home_nudge_accept
        if night_charge and self.draw_u(S_NIGHT, v.id, v.day) < p_night:
            self.kwh_night += (1.0 - v.soc) * c.battery_kwh / c.charge_eff
            v.soc = 1.0
        elif initial:
            v.soc = 1.0 if self.draw_u(S_NIGHT, v.id, v.day) < c.p_night_charge else v.soc

    def threshold_now(self, v, t, key):
        """The driver's charging threshold at this decision: personal value, higher near the end
        of the shift and noisy per decision when cfg.driver_hetero (else the fixed personal value)."""
        c = self.cfg
        if not c.driver_hetero:
            return v.soc_threshold
        thr = v.soc_threshold + (v.end_shift_extra if v.shift_end - t < 2 * 3600 else 0.0)
        return thr + self.draw_normal(0.0, c.hetero_thr_noise_sd, S_THR_NOISE, v.id, key)

    def end_shift(self, v, t):
        """Shift over: drive home, or first charge when the drive home would leave less than
        soc_reserve (cfg.charge_before_home)."""
        c = self.cfg
        if c.charge_before_home and c.home_mode and not v.home_charge_done:
            km = float(road_km(v.lat, v.lon, v.home[0], v.home[1], c.detour))
            if v.soc - self.soc_for_km(km) < c.soc_reserve:
                v.home_charge_done = True
                self.go_charge(v, t)
                return
        self.go_off(v, t)

    def start_shift(self, v, t):
        c = self.cfg
        online_h = float(np.clip(self.draw_normal(v.shift_len_h, c.online_sd_h, S_ONLINE, v.id, v.day),
                                 c.online_min_h, c.online_max_h))
        v.shift_start, v.shift_end = t, t + online_h * 3600
        # what the platform believes about the shift end (used only to skip charge nudges near it)
        v.shift_end_est = v.shift_end + (self.draw_normal(0.0, c.shift_end_noise_min * 60, S_SHIFT_EST, v.id, v.day)
                                         if c.shift_end_info == "noisy" else 0.0)
        v.drive_today_s = v.drive_cont_s = 0.0
        v.t_stop, v.meal_done = None, False
        v.home_charge_done = False
        v.meal_at = t + self.draw_uniform(*c.meal_window, S_MEAL, v.id, v.day) * online_h * 3600
        v.rest_done = c.rest_break_min <= 0
        v.rest_at = t + self.draw_uniform(*c.rest_window, S_REST, v.id, v.day) * online_h * 3600
        v.status, v.outcome, v.t_free = IDLE, "", np.inf
        v.idle_since = t
        self.mark_stop(v, t)

    def shift_over(self, v, t):
        c = self.cfg
        return c.shifts and (t >= v.shift_end or v.drive_today_s >= c.max_drive_h_day * 3600)

    # ---------- leg handling ----------
    def start_leg(self, v, t, dest, km, kind, status, outcome):
        """Start a driving leg. If the battery runs out on the way the vehicle strands
        part-way and the leg outcome becomes 'strand'."""
        self.settle_rest(v, t)
        v.t_stop = None
        need = self.soc_for_km(km)
        dur = travel_s(km, t)
        if need > v.soc:
            self.strand_log.append({"t": t, "vehicle": v.id, "kind": kind, "status": status, "soc": v.soc,
                                    "km": km, "soc_needed": need, "has_rider": v.request is not None,
                                    "forward_rider": v.next_request is not None})
            frac = v.soc / need if need > 0 else 0.0
            dest = (v.lat + frac * (dest[0] - v.lat), v.lon + frac * (dest[1] - v.lon))
            km, dur, outcome = km * frac, dur * frac, "strand"
        v.status, v.dest, v.leg_km, v.leg_s, v.leg_kind, v.outcome = status, dest, km, dur, kind, outcome
        v.t_free = t + dur
        if self.leg_log is not None:
            self.leg_log.append((v.id, t, t + dur, v.lat, v.lon, dest[0], dest[1], kind, v.soc,
                                 max(0.0, v.soc - self.soc_for_km(km)),
                                 v.request.id if v.request is not None else -1))

    def start_timed(self, v, t, status, dur_s, outcome):
        self.mark_stop(v, t)
        v.status, v.outcome, v.t_free = status, outcome, t + dur_s

    def finish(self, v):
        te = v.t_free
        if v.status in DRIVING:
            v.lat, v.lon = v.dest
            v.soc = max(0.0, v.soc - self.soc_for_km(v.leg_km))
            v.km[v.leg_kind] += v.leg_km
            v.drive_today_s += v.leg_s
            v.drive_cont_s += v.leg_s
            v.drive_s += v.leg_s
            if v.leg_kind == "trip":
                v.trip_s += v.leg_s
        r = v.request

        if v.outcome == "pickup":
            r.t_pickup = te
            self.start_leg(v, te, (r.d_lat, r.d_lon), r.trip_km, "trip", ON_TRIP, "dropoff")
        elif v.outcome == "dropoff":
            r.t_dropoff, r.status = te, "served"
            r.fare = fare(r.trip_km, r.t, r.airport)
            v.request = None
            self.continue_or_free(v, te)
        elif v.outcome == "cancel":
            v.request = None
            self.continue_or_free(v, te)
        elif v.outcome == "reposition_end":
            self.continue_or_free(v, te)
        elif v.outcome == "strand":
            for rr in (r, v.next_request):
                if rr is not None:
                    rr.status = "failed_stranded"
            v.request = v.next_request = None
            self.strandings += 1
            v.station, _ = self.nearest_station(v.lat, v.lon)
            self.start_timed(v, te, TOWED, self.cfg.tow_min * 60, "towed")
        elif v.outcome == "towed":
            v.lat, v.lon = self.stations[v.station]
            self.enqueue(v, te)
        elif v.outcome == "station":
            self.enqueue(v, te)
        elif v.outcome == "charged":
            self.ports_busy[v.station] -= 1
            v.station = -1
            self.after_free(v, te)
        elif v.outcome == "break_end":
            self.after_free(v, te)
        elif v.outcome == "shift_start":
            self.start_shift(v, te)

    def continue_or_free(self, v, t):
        if v.next_request is not None:
            r, v.next_request = v.next_request, None
            self.forward_assigns += 1
            self.send_to_pickup(v, r, t)
        else:
            self.after_free(v, t)

    def send_to_pickup(self, v, r, t):
        """Drive to the rider. The rider cancels if the driver cannot arrive within their patience."""
        v.request = r
        pickup_km = float(road_km(v.lat, v.lon, r.o_lat, r.o_lon, self.cfg.detour))
        eta = travel_s(pickup_km, t)
        t_cancel = r.t + r.patience_s
        if t >= t_cancel:
            # forward-dispatched rider already gave up before the previous trip ended
            r.status = "cancel_assigned"
            self.maybe_rebook(r, t_cancel, assigned=True)
            v.request = None
            self.after_free(v, t)
        elif t + eta > t_cancel:
            r.status = "cancel_assigned"
            self.maybe_rebook(r, t_cancel, assigned=True)
            frac = (t_cancel - t) / eta
            r.wasted_km = pickup_km * frac
            dest = (v.lat + frac * (r.o_lat - v.lat), v.lon + frac * (r.o_lon - v.lon))
            self.start_leg(v, t, dest, pickup_km * frac, "deadhead", TO_PICKUP, "cancel")
        else:
            self.start_leg(v, t, (r.o_lat, r.o_lon), pickup_km, "deadhead", TO_PICKUP, "pickup")

    def maybe_rebook(self, r, t_cancel, assigned):
        """Cancelled riders often book again (same journey, new request, less patience)."""
        c = self.cfg
        if not c.rebook or r.attempt >= c.max_attempts:
            return
        p = c.p_rebook_early if r.early else (c.p_rebook_assigned if assigned else c.p_rebook_unassigned)
        if self.draw_u(S_REBOOK, r.id) >= p:
            return
        t_new = t_cancel + self.draw_exp(c.rebook_delay_mean_min * 60, S_REBOOK_DELAY, r.id)
        patience = self.draw_exp(c.patience_mean_min * 60, S_REBOOK_PATIENCE, r.id) * c.rebook_patience_factor
        nr = demand.Request(len(self.requests), t_new, r.o_lat, r.o_lon, r.d_lat, r.d_lon, r.trip_km,
                            patience, trip_id=r.trip_id, attempt=r.attempt + 1, airport=r.airport)
        self.requests.append(nr)
        heapq.heappush(self.future, (nr.t, nr.id))
        self.rebooks += 1

    def pick_station(self, v, t):
        """Drivers check port availability (V-Green app): among the nearest stations, pick
        the one with the smallest drive time + expected wait + charging time there."""
        c = self.cfg
        d = road_km(v.lat, v.lon, self.stations[:, 0], self.stations[:, 1], c.detour)
        near = np.argsort(d)[:c.station_choice_k]
        ports = self.ports_available(t)[near]
        ahead = np.array([len(self.queues[k]) for k in near]) + self.ports_busy[near]
        wait_min = np.maximum(0, ahead - ports + 1) / ports * c.typical_charge_min
        drive_min = np.array([travel_s(d[k], t) for k in near]) / 60
        charge_min = np.array([self.charge_time_s(v.soc, max(v.soc, v.charge_target), self.station_kw[k])
                               for k in near]) / 60
        k = int(near[np.argmin(drive_min + wait_min + charge_min)])
        return k, float(d[k])

    def go_charge(self, v, t):
        k, km = self.pick_station(v, t)
        v.station = k
        self.start_leg(v, t, tuple(self.stations[k]), km, "to_station", TO_STATION, "station")

    def after_free(self, v, t):
        """Driver-side decisions once a vehicle has no job (baseline behaviour, not dispatch)."""
        c = self.cfg
        self.settle_rest(v, t)
        if self.shift_over(v, t):
            self.end_shift(v, t)
        elif v.soc < self.threshold_now(v, t, int(t)):
            self.go_charge(v, t)
        elif c.return_to_area and not ocp1.router().inside(v.lat, v.lon):
            # dropped a rider outside the service area (gateway trip): drive back in empty
            lat, lon = ocp1.sample_points(np.random.default_rng((c.seed, v.id, int(t))), 1)
            dest = (float(lat[0]), float(lon[0]))
            self.start_leg(v, t, dest, float(road_km(v.lat, v.lon, dest[0], dest[1], c.detour)),
                           "reposition", REPOSITION, "reposition_end")
        elif c.shifts and not v.meal_done and t >= v.meal_at:
            v.meal_done = True
            if self.wants_break_charge(v):
                self.go_charge(v, t)
            else:
                self.start_timed(v, t, BREAK, c.meal_break_min * 60, "break_end")
        elif c.shifts and not v.rest_done and t >= v.rest_at:
            v.rest_done = True
            self.start_timed(v, t, BREAK, c.rest_break_min * 60, "break_end")
        elif c.shifts and v.drive_cont_s >= (c.max_drive_cont_h - c.drive_cont_margin_h) * 3600:
            if self.wants_break_charge(v):
                self.go_charge(v, t)
            else:
                self.start_timed(v, t, BREAK, c.break_min * 60, "break_end")
        else:
            v.status, v.outcome, v.t_free = IDLE, "", np.inf
            v.idle_since = t
            self.mark_stop(v, t)

    def wants_break_charge(self, v):
        """Use a break to charge when SOC is low and there is something worth adding
        before the driver's own unplug level."""
        return v.soc < min(self.cfg.meal_charge_soc, v.charge_target - 0.05)

    def enqueue(self, v, t):
        self.mark_stop(v, t)
        v.status, v.t_queued, v.t_free = QUEUED, t, np.inf
        self.queues[v.station].append(v)

    def start_charging(self, t):
        ports = self.ports_available(t)
        for k, q in enumerate(self.queues):
            while q and self.ports_busy[k] < ports[k]:
                v = q.popleft()
                self.ports_busy[k] += 1
                target = v.charge_target
                if self.cfg.driver_hetero:
                    target = float(np.clip(target + self.draw_normal(0.0, self.cfg.hetero_target_sd,
                                                                     S_TARGET_NOISE, v.id, int(t)), 0.5, 1.0))
                soc_to = max(v.soc, target)
                dur = self.charge_time_s(v.soc, soc_to, self.station_kw[k])
                self.kwh_at_plug += (soc_to - v.soc) * self.cfg.battery_kwh / self.cfg.charge_eff
                self.charge_log.append((v.id, k, v.t_queued, t, t + dur, v.soc, soc_to))
                v.soc = soc_to
                v.status, v.outcome, v.t_free = CHARGING, "charged", t + dur

    # ---------- matching ----------
    def forward_ok(self, v, t):
        """A busy vehicle may take a queued rider only if its driver would still be working
        after the current leg: shift not over, driving caps not hit, and SOC above the driver's
        own charging threshold (the driver would otherwise head to a charger, as in idle mode)."""
        c = self.cfg
        if v.next_request is not None or v.t_free - t > c.forward_horizon_min * 60:
            return False
        if c.shifts and (v.t_free >= v.shift_end
                         or v.drive_today_s + v.leg_s >= (c.max_drive_h_day - 0.5) * 3600
                         or v.drive_cont_s + v.leg_s >= (c.max_drive_cont_h - c.drive_cont_margin_h) * 3600):
            return False
        return v.soc - self.soc_for_km(v.leg_km) >= v.soc_threshold

    def candidates(self, t):
        cands = [Cand(v, t, v.lat, v.lon, v.soc) for v in self.vehicles if v.status == IDLE]
        if getattr(self.policy, "forward", False):
            for v in self.vehicles:
                if ((v.status == ON_TRIP and v.outcome == "dropoff") or v.status == REPOSITION) \
                        and self.forward_ok(v, t):
                    cands.append(Cand(v, v.t_free, v.dest[0], v.dest[1], v.soc - self.soc_for_km(v.leg_km)))
        return cands

    def apply_driver_filters(self, cands, cost, t):
        """Driver-side constraints the platform respects: offers a driver already declined are
        not repeated, and in going-home mode only trips that bring the driver closer to home
        (or end near home) are offered."""
        c = self.cfg
        if self.rejected:
            col = {r.id: j for j, r in enumerate(self.pool)}
            for i, cd in enumerate(cands):
                for rid in self.rejected.get(cd.v.id, ()):
                    j = col.get(rid)
                    if j is not None:
                        cost[i, j] = BIG
        if c.shifts and c.home_mode:
            d_lat = np.array([r.d_lat for r in self.pool])
            d_lon = np.array([r.d_lon for r in self.pool])
            for i, cd in enumerate(cands):
                v = cd.v
                if cd.t_avail < v.shift_end - c.home_mode_min * 60:
                    continue
                to_home = road_km(d_lat, d_lon, v.home[0], v.home[1], c.detour)
                now_home = float(road_km(cd.lat, cd.lon, v.home[0], v.home[1], c.detour))
                cost[i, (to_home > c.home_radius_km) & (to_home >= now_home)] = BIG

    def driver_accepts(self, cd, r, pickup_km, t):
        """Drivers see pickup distance and destination. They decline for battery reasons when
        the trip would leave them near their own charging threshold, and occasionally for
        other reasons (far pickup, personal)."""
        c = self.cfg
        if not c.driver_accept or (cd.v.id, r.id) in self.accepted:
            return True
        v = cd.v
        self.ride_offers += 1
        soc_start = v.soc if v.status == IDLE else v.soc - self.soc_for_km(v.leg_km)
        soc_after = soc_start - self.soc_for_km(pickup_km + r.trip_km)
        thr = self.threshold_now(v, t, -1 - r.id)
        p_soc = 1.0 / (1.0 + np.exp(-(thr + v.soc_margin - soc_after) / v.soc_scale)) if c.driver_soc_decline else 0.0
        p_other = 1.0 - c.ride_accept_base * (1.0 - min(1.0, max(0.0, pickup_km - 3.0) * c.ride_reject_per_far_km))
        if self.draw_u(S_DECLINE_SOC, v.id, r.id) < p_soc:
            self.ride_rejects_soc += 1
            if v.status == IDLE:
                # a driver who turns down a ride for battery reasons goes to charge
                self.go_charge(v, t)
        elif self.draw_u(S_DECLINE_OTHER, v.id, r.id) >= p_other:
            self.accepted.add((v.id, r.id))
            if self.offer_log is not None:
                self.offer_log.append((soc_after, pickup_km, 0))
            return True
        if self.offer_log is not None:
            self.offer_log.append((soc_after, pickup_km, 1))
        self.ride_rejects += 1
        self.rejected[v.id].add(r.id)
        return False

    def release_tentative(self):
        """Forward assignments stay tentative until the vehicle frees up: each batch the
        riders go back to the pool so a better (e.g. newly idle) vehicle can take them."""
        for v in self.vehicles:
            if v.next_request is not None:
                self.pool.append(v.next_request)
                v.next_request = None

    def dispatch(self, t):
        if getattr(self.policy, "forward", False):
            self.release_tentative()
        cands = self.candidates(t)
        if not cands or not self.pool:
            return
        cost, pickup_km = self.policy.cost_matrix(cands, self.pool, t)
        self.apply_driver_filters(cands, cost, t)
        rows, cols = getattr(self.policy, "solve", linear_sum_assignment)(cost)
        matched = set()
        for i, j in zip(rows, cols):
            if cost[i, j] >= BIG / 2:
                continue
            v, r = cands[i].v, self.pool[j]
            if not self.driver_accepts(cands[i], r, float(pickup_km[i, j]), t):
                continue
            matched.add(j)
            r.t_assign, r.pickup_km, r.vehicle = t, float(pickup_km[i, j]), v.id
            r.assign_lat, r.assign_lon = cands[i].lat, cands[i].lon
            if v.status == IDLE:
                t_go = t + (self.draw_exp(self.cfg.ride_response_s, S_RESPONSE, v.id, r.id)
                            if self.cfg.driver_accept else 0.0)
                self.send_to_pickup(v, r, t_go)
            else:
                v.next_request = r
        self.pool = [r for j, r in enumerate(self.pool) if j not in matched]

    # ---------- repositioning ----------
    def nudge_level(self, t):
        """SOC below which an idle car is sent to charge (B3): high just before the peaks so
        cars enter them charged, low during the peaks to keep supply on the road."""
        c = self.cfg
        h = (t / 3600) % 24
        if any(a <= h < b for a, b in c.nudge_prepeak_hours):
            return c.nudge_soc_prepeak
        if any(a <= h < b for a, b in c.nudge_peak_hours):
            return c.nudge_soc_peak
        return c.nudge_soc

    def nudge_charging(self, t):
        """B3: send idle low-SOC cars to charge now instead of letting them idle until they
        cross their own threshold (drivers follow the suggestion; they unplug at their usual
        level). Drivers ending their shift within the hour are left alone: they charge at night."""
        c = self.cfg
        level = self.nudge_level(t)
        observe = getattr(self.policy, "observe_soc", lambda v, t: v.soc)  # what the platform sees
        smart = c.nudge_mode in ("smart", "hybrid") and hasattr(self.policy, "nudge_wanted")
        h = (t / 3600) % 24
        prepeak = any(a - c.nudge_lookahead_h <= h < a for a, _ in c.nudge_peak_hours)
        targeted = None
        if c.nudge_mode == "target" and prepeak and hasattr(self.policy, "target_nudges"):
            targeted = self.policy.target_nudges(t)    # ids chosen to reach the pre-peak supply target
        flagged = getattr(self.policy, "flagged", set())       # shut out of most trips by the safety mask
        forced = getattr(self.policy, "forced_nudge", lambda v, t: False)
        regular = getattr(self.policy, "regular_nudge", True)
        allowed = None    # v2.2 supply-aware gate: which cars may get the raised pre-peak nudge
        if c.nudge_gate != "none" and c.nudge_mode == "time_of_day" and level > c.nudge_soc:
            idle = [v for v in self.vehicles if v.status == IDLE]
            socs = {v.id: observe(v, t) for v in idle}
            boost = sorted((v for v in idle if c.nudge_soc <= socs[v.id] < level), key=lambda v: socs[v.id])
            if c.nudge_gate == "idle_share":
                online = sum(v.status != OFF for v in self.vehicles)
                keep = boost if online and len(idle) / online >= c.gate_idle_share else []
            else:   # surplus: never take more cars than the idle surplus over waiting riders
                keep = boost[:int(c.gate_surplus_frac * max(0, len(idle) - len(self.pool)))]
            allowed = {v.id for v in idle if socs[v.id] < c.nudge_soc} | {v.id for v in keep}
        for v in self.vehicles:
            if v.status != IDLE:
                continue
            if forced(v, t):
                pass
            elif not regular:
                continue
            elif targeted is not None:
                if v.id not in targeted:
                    continue
            elif c.nudge_mode == "value" and hasattr(self.policy, "nudge_value"):
                soc = observe(v, t)
                if soc >= v.charge_target - 0.05 or not self.policy.nudge_value(v, t, soc, level):
                    continue
            elif smart:
                soc = observe(v, t)
                want = self.policy.nudge_wanted(v, t, soc)
                if c.nudge_mode == "hybrid" and not prepeak:
                    want = want or soc < level     # time-of-day floor outside the pre-peak windows
                if soc >= v.charge_target - 0.05 or not want:
                    continue
            elif observe(v, t) >= min(level, v.charge_target - 0.05):
                continue
            elif allowed is not None and v.id not in allowed:
                continue
            if (c.shifts and c.shift_end_info != "none"
                    and v.shift_end_est - t < c.nudge_skip_before_shift_end_min * 60):
                continue
            if t < v.nudge_cooldown_until:
                continue
            self.nudge_offers += 1
            if v.nudge_p < 1.0 and self.draw_u(S_NUDGE, v.id, t) >= v.nudge_p:
                v.nudge_cooldown_until = t + c.nudge_cooldown_min * 60   # ignored: keeps working as usual
                continue
            self.charge_nudges += 1
            self.go_charge(v, t)
        flagged.clear()

    def reposition(self, t):
        """Move long-idle vehicles from zones with surplus to zones with a forecast deficit.
        Zones are the demand hotspots; the forecast is the hourly demand profile (the demand
        generator's rates stand in for historical averages)."""
        c = self.cfg
        spots = ocp1.ZONES if c.demand_model == "ocp1" else demand.HOTSPOTS
        sigma = ocp1.ZONE_SIGMA_DEG if c.demand_model == "ocp1" else demand.HOTSPOT_SIGMA_DEG
        centers = spots[:, :2]
        w = spots[:, 2] / spots[:, 2].sum()
        h = int(t / 3600) % 24
        horizon_h = c.reposition_horizon_min / 60
        target = (c.reposition_target_ratio * c.daily_requests * demand.HOURLY[h] * horizon_h
                  * (1 - c.airport_share) * w)

        def zone(lat, lon):
            return int(np.argmin(road_km(lat, lon, centers[:, 0], centers[:, 1], c.detour)))

        supply = np.zeros(len(centers))
        movable = [[] for _ in centers]
        for v in self.vehicles:
            if v.status == IDLE:
                z = zone(v.lat, v.lon)
                supply[z] += 1
                if (t - v.idle_since >= c.reposition_idle_min * 60
                        and t >= v.repo_cooldown_until
                        and v.soc >= v.soc_threshold + c.reposition_soc_margin):
                    movable[z].append(v)
            elif v.status in (ON_TRIP, REPOSITION) and v.t_free - t <= horizon_h * 3600:
                supply[zone(*v.dest)] += 1

        surplus = np.floor(supply - target).astype(int)
        deficit = np.ceil(target - supply).astype(int)
        movers = [v for z in range(len(centers)) for v in movable[z][:max(0, surplus[z])]]
        slots = [z for z in range(len(centers)) for _ in range(max(0, deficit[z]))]
        if not movers or not slots:
            return
        km = road_km(np.array([v.lat for v in movers])[:, None], np.array([v.lon for v in movers])[:, None],
                     centers[slots, 0][None, :], centers[slots, 1][None, :], c.detour)
        cost = np.where(km <= c.reposition_max_km, km, BIG)
        for i, j in zip(*linear_sum_assignment(cost)):
            if cost[i, j] >= BIG / 2:
                continue
            v, z = movers[i], slots[j]
            self.repo_offers += 1
            p_accept = c.reposition_accept_p0 * np.exp(-km[i, j] / c.reposition_accept_decay_km)
            if self.draw_u(S_REPO_ACCEPT, v.id, t) >= p_accept:
                v.repo_cooldown_until = t + c.reposition_cooldown_min * 60
                continue
            dest = (centers[z, 0] + self.draw_normal(0, sigma / 2, S_REPO_LAT, v.id, t),
                    centers[z, 1] + self.draw_normal(0, sigma / 2, S_REPO_LON, v.id, t))
            km_to = float(road_km(v.lat, v.lon, dest[0], dest[1], c.detour))
            self.start_leg(v, t, dest, km_to, "reposition", REPOSITION, "reposition_end")
            self.repositions += 1

    # ---------- main loop ----------
    def run(self):
        cfg = self.cfg
        t_end = cfg.sim_hours * 3600
        next_snap = 0.0
        next_repo = 0.0
        self.e0_kwh = sum(v.soc for v in self.vehicles) * cfg.battery_kwh
        next_idle_log = 0.0
        t = 0.0
        while t < t_end:
            t += cfg.batch_s
            while True:
                due = [v for v in self.vehicles if v.t_free <= t]
                if not due:
                    break
                for v in sorted(due, key=lambda v: v.t_free):
                    self.finish(v)
            if cfg.shifts:
                for v in self.vehicles:
                    if v.status == IDLE and self.shift_over(v, t):
                        self.end_shift(v, t)
            self.start_charging(t)

            while self.future and self.future[0][0] <= t:
                self.pool.append(self.requests[heapq.heappop(self.future)[1]])
            keep = []
            for r in self.pool:
                if r.t + r.patience_s <= t:
                    r.status = "cancel_unassigned"
                    self.maybe_rebook(r, r.t + r.patience_s, assigned=False)
                else:
                    keep.append(r)
            self.pool = keep

            self.dispatch(t)
            if self.state_log is not None:
                for v in self.vehicles:
                    key = (v.status, v.station)
                    if getattr(v, "_logged", None) != key:
                        v._logged = key
                        self.state_log.append((t, v.id, v.status, round(v.soc, 4), v.lat, v.lon, v.station))
            if t >= next_repo:
                if getattr(self.policy, "charge_nudge", False):
                    self.nudge_charging(t)
                if getattr(self.policy, "reposition", False):
                    self.reposition(t)
                next_repo += cfg.reposition_every_min * 60

            if self.idle_log is not None and t >= next_idle_log:
                self.idle_log.extend((t, v.lat, v.lon) for v in self.vehicles if v.status == IDLE)
                next_idle_log += 600

            if t >= next_snap:
                self.snapshots.extend((t, v.id, v.status, v.soc) for v in self.vehicles)
                next_snap += 15 * 60

        for v in self.vehicles:
            if v.status != OFF:
                v.online_s += t_end - max(v.shift_start, 0.0)
        self.e_end_kwh = sum(v.soc for v in self.vehicles) * cfg.battery_kwh
        return self
