"""Batch matching policies. A policy builds a (candidates x riders) cost matrix; the
simulator solves it with the Hungarian algorithm. A candidate is a vehicle plus the time
and place it becomes available (now for idle vehicles, drop-off for forward dispatch)."""
import numpy as np

from . import values
from .economics import fare
from .geo import road_km, speed_kmh

BIG = 1e9


class GSMBaseline:
    """B1. Current GSM-style matching as described by the mentor: batch of idle drivers and
    waiting riders, cost = pickup distance + cancellation risk (+ waiting priority),
    Hungarian assignment. Battery state is NOT used."""

    name = "gsm_baseline"
    forward = False
    reposition = False

    def __init__(self, cfg):
        self.cfg = cfg

    def cost_matrix(self, cands, riders, t):
        cfg = self.cfg
        c_lat = np.array([c.lat for c in cands])[:, None]
        c_lon = np.array([c.lon for c in cands])[:, None]
        c_wait = np.array([c.t_avail - t for c in cands])[:, None]   # 0 for idle vehicles
        r_lat = np.array([r.o_lat for r in riders])[None, :]
        r_lon = np.array([r.o_lon for r in riders])[None, :]
        pickup_km = road_km(c_lat, c_lon, r_lat, r_lon, cfg.detour)

        speed = speed_kmh(t)
        eta_s = c_wait + pickup_km / speed * 3600.0
        # Exponential patience is memoryless, so P(cancel before arrival) depends on ETA only.
        p_cancel = 1.0 - np.exp(-eta_s / (cfg.patience_mean_min * 60))
        waited_min = np.array([(t - r.t) / 60.0 for r in riders])[None, :]
        # time until a busy vehicle is free, expressed in km at current speed (0 for idle vehicles)
        wait_km = c_wait / 3600.0 * speed

        cost = cfg.w_dist * (pickup_km + wait_km) + cfg.w_cancel * p_cancel - cfg.w_wait * waited_min
        if cfg.w_idle:
            # fairness: drivers who have waited longer for a job get priority
            idle_min = np.array([min((t - c.v.idle_since) / 60.0, cfg.idle_bonus_cap_min)
                                 if c.t_avail <= t else 0.0 for c in cands])[:, None]
            cost = cost - cfg.w_idle * idle_min
        if cfg.radius_expand:
            # search radius grows with the rider's waiting time
            radius = np.minimum(cfg.pickup_radius0_km + cfg.radius_growth_km_per_min * waited_min,
                                cfg.max_pickup_km)
            cost[pickup_km > radius] = BIG
        else:
            cost[pickup_km > cfg.max_pickup_km] = BIG
        return cost, pickup_km


class GSMForwardReposition(GSMBaseline):
    """B2. B1 plus forward dispatch (riders may be matched to vehicles finishing a trip within
    forward_horizon_min) and repositioning of long-idle vehicles toward forecast demand.
    Still battery-blind: only the driver's own charging threshold filters candidates."""

    name = "gsm_fwd_repo"
    forward = True
    reposition = True


class GSMForward(GSMBaseline):
    """Ablation: B1 + forward dispatch only."""
    name = "gsm_fwd"
    forward = True


class GSMReposition(GSMBaseline):
    """Ablation: B1 + repositioning only."""
    name = "gsm_repo"
    reposition = True


class BatteryAware(GSMForwardReposition):
    """B3. B2 plus battery state in the cost matrix. For every (vehicle, rider) pair the
    dispatcher predicts the vehicle's SOC after pickup + trip (starting from its SOC when it
    becomes available, which for forward dispatch is after its current trip) and
      - forbids the pair if the car could not then reach the charger nearest the drop-off
        with soc_reserve left (feasibility filter);
      - adds a penalty that grows as the SOC after the trip falls below soc_comfort, so long
        trips go to well-charged cars and low-SOC cars get short trips.
    It also nudges idle low-SOC cars to charge at the right time (see Simulator.nudge_charging).
    The dispatcher uses SOC (vehicle telemetry) but not the drivers' personal charging habits."""

    name = "b3_battery"
    charge_nudge = True

    def attach(self, sim):
        self.stations = sim.stations

    def cost_matrix(self, cands, riders, t):
        cost, pickup_km = super().cost_matrix(cands, riders, t)
        cfg = self.cfg
        soc_per_km = cfg.kwh_per_km / cfg.battery_kwh
        soc0 = np.array([c.soc for c in cands])[:, None]
        trip_km = np.array([r.trip_km for r in riders])[None, :]
        d_lat = np.array([r.d_lat for r in riders])[:, None]
        d_lon = np.array([r.d_lon for r in riders])[:, None]
        to_charger_km = road_km(d_lat, d_lon, self.stations[None, :, 0], self.stations[None, :, 1],
                                cfg.detour).min(axis=1)[None, :]

        soc_after = soc0 - (pickup_km + trip_km) * soc_per_km
        infeasible = soc_after - to_charger_km * soc_per_km < cfg.soc_reserve
        shortfall = np.maximum(0.0, cfg.soc_comfort - soc_after) / 0.05
        cost = cost + cfg.w_soc * shortfall
        cost[infeasible] = BIG
        return cost, pickup_km


class DiDiValue(GSMForwardReposition):
    """B4. Value-based matching, Xu et al. (DiDi, KDD 2018), Eq. (8): with V(cell, slot) learned
    by scripts/train_didi_values.py, each (vehicle, rider) pair gets the advantage
        A = gamma^dt * V(drop-off cell, slot at drop-off) - V(vehicle cell, slot) + R_gamma(fare)
    where dt = pickup + delivery time in slots and R_gamma spreads the fare over dt (Eq. 1).
    After the required filters (search radius), KM / Hungarian maximises the total advantage.
    Same framework as B2 (forward dispatch, repositioning, driver behaviour). Battery-blind.
    didi_cancel_aware (off by default) is our variant weighting the gain by P(no cancel)."""

    name = "b4_didi"

    def attach(self, sim):
        self.V, self.gamma = values.load(self.cfg.didi_values)
        self.grid = values.Grid()

    def cost_matrix(self, cands, riders, t):
        cfg = self.cfg
        c_lat = np.array([c.lat for c in cands])[:, None]
        c_lon = np.array([c.lon for c in cands])[:, None]
        c_wait = np.array([c.t_avail - t for c in cands])[:, None]
        r_lat = np.array([r.o_lat for r in riders])[None, :]
        r_lon = np.array([r.o_lon for r in riders])[None, :]
        pickup_km = road_km(c_lat, c_lon, r_lat, r_lon, cfg.detour)
        speed = speed_kmh(t)
        eta_s = c_wait + pickup_km / speed * 3600.0
        p_cancel = 1.0 - np.exp(-eta_s / (cfg.patience_mean_min * 60))

        trip_km = np.array([r.trip_km for r in riders])[None, :]
        trip_s = trip_km / speed * 3600.0
        fares = np.array([fare(r.trip_km, r.t, r.airport) for r in riders])[None, :]
        g = self.gamma
        # the car's state s is (its cell, the slot when it is free); dt runs from then
        t_free = np.array([c.t_avail for c in cands])[:, None]
        dt_slots = ((eta_s - c_wait) + trip_s) / values.SLOT_S
        reward = values.spread_reward(fares, dt_slots, g)
        d_cell = self.grid.cell([r.d_lat for r in riders], [r.d_lon for r in riders])[None, :]
        v_end = values.lookup(self.V, d_cell, values.slot_after(t_free, t_free + dt_slots * values.SLOT_S))
        v_now = self.V[self.grid.cell(c_lat[:, 0], c_lon[:, 0]), values.slot(t_free[:, 0])][:, None]
        gain = g ** dt_slots * v_end + reward
        if cfg.didi_cancel_aware:
            gain = (1 - p_cancel) * gain
        advantage = gain - v_now

        cost = -advantage / 1000.0  # thousand VND
        waited_min = np.array([(t - r.t) / 60.0 for r in riders])[None, :]
        if cfg.radius_expand:
            radius = np.minimum(cfg.pickup_radius0_km + cfg.radius_growth_km_per_min * waited_min, cfg.max_pickup_km)
            cost[pickup_km > radius] = BIG
        else:
            cost[pickup_km > cfg.max_pickup_km] = BIG
        return cost, pickup_km


class GreedyNearest(GSMBaseline):
    """B0. No batch optimisation: riders are served in booking order, each taking the free car
    with the shortest pickup (ETA in km, same search radius as B1). A different matching
    structure from the Hungarian black boxes."""

    name = "b0_greedy"

    def cost_matrix(self, cands, riders, t):
        cost, pickup_km = super().cost_matrix(cands, riders, t)
        c_wait = np.array([c.t_avail - t for c in cands])[:, None]
        eta_km = pickup_km + c_wait / 3600.0 * speed_kmh(t)
        return np.where(cost < BIG / 2, eta_km, BIG), pickup_km

    def solve(self, cost):
        """Riders in pool order (oldest booking first), each takes its cheapest remaining car."""
        rows, cols, used = [], [], np.zeros(cost.shape[0], bool)
        for j in range(cost.shape[1]):
            col = np.where(used, np.inf, cost[:, j])
            i = int(np.argmin(col))
            if col[i] < BIG / 2:
                used[i] = True
                rows.append(i)
                cols.append(j)
        return np.array(rows, int), np.array(cols, int)


class ImmediateValue(GSMBaseline):
    """B6. Economic score of the trip itself, no future value: expected platform margin
    = P(rider still there) x fare x (1 - driver commission) - energy for pickup + trip,
    in thousand VND (cost = minus margin). Same search radius as B1."""

    name = "b6_value"

    def cost_matrix(self, cands, riders, t):
        cfg = self.cfg
        cost, pickup_km = super().cost_matrix(cands, riders, t)
        c_wait = np.array([c.t_avail - t for c in cands])[:, None]
        eta_s = c_wait + pickup_km / speed_kmh(t) * 3600.0
        p_ok = np.exp(-eta_s / (cfg.patience_mean_min * 60))
        trip_km = np.array([r.trip_km for r in riders])[None, :]
        fares = np.array([fare(r.trip_km, r.t, r.airport) for r in riders])[None, :]
        energy_vnd_km = cfg.kwh_per_km / cfg.charge_eff * cfg.price_kwh
        margin = p_ok * fares * (1 - cfg.driver_commission) - (pickup_km + trip_km) * energy_vnd_km
        return np.where(cost < BIG / 2, -margin / 1000.0, BIG), pickup_km


POLICIES = {p.name: p for p in (GSMBaseline, GSMForward, GSMReposition, GSMForwardReposition, BatteryAware,
                                DiDiValue, GreedyNearest, ImmediateValue)}
