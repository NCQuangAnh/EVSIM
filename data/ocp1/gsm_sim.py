#!/usr/bin/env python3
"""GreenSM fleet dispatch simulation: baseline vs battery-aware Hungarian.

Models the Group 2 decision directly: at every tick, each available vehicle can
(1) take an order, (2) go charge, or (3) wait -- and a trip longer than the
battery can serve is not assignable to that vehicle. The baseline ignores the
battery constraint except a hard SoC floor; the policy under test prices the
opportunity cost of the energy a vehicle is carrying, so it declines trips it
cannot finish and prefers near-chargeable vehicles for far trips.

Both arms run the identical scenario stream. The only difference is the
assignment rule, so any metric difference is attributable to the policy.

Vehicle parameters are the published VinFast VF e34 / Nerio Green figures -- the
model Green SM actually operates in Hanoi. Demand is synthesised, not measured:
no Green SM operational data was available, so this is a simulation study and
says so on every page.

    uv run --no-project python scripts/gsm_sim.py --days 20 --seed 20260929

Stdlib only. No numpy, no scipy, no pandas -- the Hungarian assignment is ~40
lines of Kuhn-Munkres and the whole harness runs in seconds, which matters more
here than speed.
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Vehicle types.
#
# The fleet spec is DATA now, in data/fleet_spec.json, not module constants.
# It was one hardcoded VinFast VF e34 -- every one of the 60 vehicles identical
# -- which made the findings true only for a single homogeneous car fleet and
# unable to represent GreenSM's actual mixed fleet, which the research pass
# confirmed includes both cars and battery-swap motorbikes. A swap takes
# seconds; a charge session takes tens of minutes. That single difference
# dominates dispatch economics, so a mixed fleet is not a refinement of this
# model -- it is a different question.
#
# The module-level constants below are kept as the DEFAULT TYPE's derived
# figures so that every existing gate, test and published figure keeps working
# unchanged. Adding a second type changes behaviour only when a run asks for it.
# ---------------------------------------------------------------------------
import json as _json

_SPEC_PATH = ROOT / "data" / "fleet_spec.json"
_FLEET_SPEC = _json.loads(_SPEC_PATH.read_text(encoding="utf-8")) if _SPEC_PATH.exists() else None

_GRAPH_PATH = ROOT / "data" / "ocp1_graph.json"
_OCP1_GRAPH: dict | None = None
_OCP1_ADJ: dict[int, list[tuple[int, float]]] = {}
_ROUTE_CACHE: dict[tuple[int, int], float] = {}


def load_ocp1_adj() -> dict[int, list[tuple[int, float]]]:
    """Load OCP1 graph and build module-level cached adjacency graph once."""
    global _OCP1_GRAPH, _OCP1_ADJ
    if _OCP1_ADJ:
        return _OCP1_ADJ
    if not _GRAPH_PATH.exists():
        return {}
    data = _json.loads(_GRAPH_PATH.read_text(encoding="utf-8"))
    data["nodes"] = {int(k): (float(v[0]), float(v[1])) for k, v in data["nodes"].items()}
    data["edges"] = [(int(a), int(b), float(km), int(kmh)) for a, b, km, kmh in data["edges"]]
    _OCP1_GRAPH = data
    adj: dict[int, list[tuple[int, float]]] = {}
    for u, v, km, _ in data["edges"]:
        adj.setdefault(u, []).append((v, km))
        if v != u:
            adj.setdefault(v, []).append((u, km))
    _OCP1_ADJ = adj
    return _OCP1_ADJ


def get_ocp1_graph() -> tuple[dict, dict[int, list[tuple[int, float]]]]:
    """Return tuple of (graph_dict, adjacency_dict)."""
    global _OCP1_GRAPH, _OCP1_ADJ
    if _OCP1_GRAPH is None or not _OCP1_ADJ:
        load_ocp1_adj()
    return _OCP1_GRAPH, _OCP1_ADJ


def route_km(a: int | dict, b: int = -1, target: int | None = None) -> float:
    """Shortest path distance (km) on OCP1 road graph via Dijkstra on _OCP1_ADJ.

    Supports both:
      route_km(u, v) -> float
      route_km(graph, u, v) -> float
    Returns math.inf when disconnected or missing.
    """
    if target is not None:
        u, v = b, target
    else:
        u, v = a, b
    if u == v:
        return 0.0
    cache_key = (min(u, v), max(u, v))
    if cache_key in _ROUTE_CACHE:
        return _ROUTE_CACHE[cache_key]

    adj = _OCP1_ADJ if _OCP1_ADJ else load_ocp1_adj()
    if u not in adj or v not in adj:
        _ROUTE_CACHE[cache_key] = math.inf
        return math.inf

    dist = {u: 0.0}
    pq = [(0.0, u)]
    found = math.inf
    while pq:
        d, curr = heapq.heappop(pq)
        if curr == v:
            found = d
            break
        if d > dist[curr]:
            continue
        for nxt, w in adj[curr]:
            nd = d + w
            if nd < dist.get(nxt, math.inf):
                dist[nxt] = nd
                heapq.heappush(pq, (nd, nxt))

    _ROUTE_CACHE[cache_key] = found
    return found


if _GRAPH_PATH.exists():
    load_ocp1_adj()



@dataclass(frozen=True)
class VehicleType:
    """One vehicle class: its battery, its range, and how it refuels."""
    key: str
    name: str
    kind: str                 # "car" or "motorbike"
    battery_kwh: float
    range_km: float
    range_cycle: str          # NEDC, WLTP, or VF-STD-30 -- they differ materially
    dc_kw: float
    ac_kw: float
    seats: int
    swap_based: bool
    swap_minutes: float       # downtime for a swap; 0 for a charging vehicle
    realised_range_factor: float

    @property
    def usable_km(self) -> float:
        """What the simulator believes this vehicle can actually drive.

        Derived, not measured. Real fleets run below the certified cycle once
        air conditioning, load and age are counted, and this multiplier is the
        single most load-bearing assumption in the model.
        """
        return self.range_km * self.realised_range_factor

    @property
    def kwh_per_km(self) -> float:
        return self.battery_kwh / self.usable_km if self.usable_km else 0.0

    @property
    def charge_minutes_full(self) -> float:
        """0-100% on the DEPOT charger, not the public DC peak.

        Charging uses CHARGE_POWER_KW because that is what a fleet depot has.
        The published 250 kW figure is a public fast-charger peak that a
        duty-cycle fleet does not have access to for 20 hours a day.
        """
        return (self.battery_kwh / CHARGE_POWER_KW * 60.0) / CHARGE_EFFICIENCY


DEFAULT_TYPE = "e34"


def fleet_types() -> dict[str, VehicleType]:
    """Every type in the spec file, keyed by name."""
    if not _FLEET_SPEC:
        return {}
    factor = _FLEET_SPEC.get("realised_range_factor", 0.8)
    out = {}
    for key, t in _FLEET_SPEC["types"].items():
        out[key] = VehicleType(
            key=key,
            name=t.get("name", key),
            kind=t.get("kind", "car"),
            battery_kwh=float(t["battery_kwh"]),
            range_km=float(t["range_km"]),
            range_cycle=t.get("range_cycle", "unverified"),
            dc_kw=float(t.get("dc_kw", 0.0)),
            ac_kw=float(t.get("ac_kw", 0.0)),
            seats=int(t.get("seats", 4)),
            swap_based=bool(t.get("swap_based", False)),
            swap_minutes=float(t.get("swap_minutes", 1.0 if t.get("swap_based") else 0.0)),
            realised_range_factor=float(t.get("realised_range_factor", factor)),
        )
    return out


def default_type() -> VehicleType:
    return fleet_types()[DEFAULT_TYPE]


def build_fleet_types(cfg) -> list[VehicleType]:
    """The type of each vehicle id, from cfg.fleet_mix.

    Returns a list long enough for cfg.n_vehicles, ordered so that ids are
    assigned deterministically. An empty mix means every vehicle is the default
    type -- the behaviour before this existed.

    Raises rather than silently padding: a fleet_mix that sums to 56 when
    n_vehicles is 60 is a specification error, and quietly filling the gap with
    the default type would hide it behind a plausible-looking run.
    """
    avail = fleet_types()
    if not avail:
        raise SystemExit("data/fleet_spec.json is missing or empty")
    mix = dict(getattr(cfg, "fleet_mix", None) or {})
    if not mix:
        return [avail[DEFAULT_TYPE]] * cfg.n_vehicles
    unknown = sorted(set(mix) - set(avail))
    if unknown:
        raise SystemExit(f"cfg.fleet_mix names unknown type(s) {unknown}; "
                         f"the spec file has {sorted(avail)}")
    total = sum(int(n) for n in mix.values())
    if total != cfg.n_vehicles:
        raise SystemExit(f"cfg.fleet_mix sums to {total} but n_vehicles is "
                         f"{cfg.n_vehicles}; every vehicle needs a type")
    out: list[VehicleType] = []
    for key, n in mix.items():
        out.extend([avail[key]] * int(n))
    return out


def fleet_composition(cfg) -> dict:
    """Counts per type, for the results file. A run whose fleet is all one type
    should say so rather than leaving a reader to assume it."""
    out: dict = {}
    for vt in build_fleet_types(cfg):
        out[vt.key] = out.get(vt.key, 0) + 1
    return out


# The default type's figures, so existing gates and published results are
# unchanged. Derived from the spec file rather than restated, so the two cannot
# drift -- which is exactly how the soc_price_weight bug happened twice.
_D = default_type() if _FLEET_SPEC else None
BATTERY_KWH = _D.battery_kwh if _D else 44.5
RANGE_KM_CLAIMED = (_D.range_km / _D.realised_range_factor) if _D else 300.0
RANGE_KM_NEDC = _D.range_km if _D else 285.0
REALISED_RANGE_FACTOR = _D.realised_range_factor if _D else 0.80
USABLE_KM = _D.usable_km if _D else 228.0
CONSUMPTION_KWH_PER_KM = _D.kwh_per_km if _D else 0.195
CHARGE_POWER_KW = 60.0          # depot, not the 250 kW public peak
CHARGE_EFFICIENCY = 0.92
# Chargers per zone. 2.4 was a bare multiplier buried in the queue update and
# produced 212 minutes of mean wait for a 25-minute charge: the depot is the
# binding constraint in that configuration, not the dispatch policy, so every
# result was measuring queueing. Real metro depots run one fast charger per
# 8-12 vehicles; with 60 vehicles over 9 zones that is ~0.7/zone, and this
# study needs headroom so charging is a decision, not a wall.
PORTS_PER_ZONE = 8
SWAP_OR_FASTCHARGE_MIN = 25.0   # minutes per full charge at 60 kW
SWAP_TRAVEL_KM = 1.0             # a swap station is closer than a charger
DEGRADATION_PER_CYCLE = 0.00002 # capacity loss per full equivalent cycle

# ---------------------------------------------------------------------------
# Economics. Fares are per-trip in the range Green SM / Xanh SM advertise for
# Hanoi airport runs; costs are VND. Every figure is a parameter, not a finding.
# ---------------------------------------------------------------------------
FARE_BASE_VND = 68_000.0
FARE_PER_KM_VND = 12_500.0
ENERGY_PRICE_VND_PER_KWH = 4_200.0   # Hanoi off-peak commercial tariff
ENERGY_PRICE_PEAK_MULT = 1.9         # peak-hour uplift
DRIVER_PAY_VND_PER_TRIP = 52_000.0
OPEX_VND_PER_KM = 4_800.0

VEHICLE_COST_VND = 400_000_000.0    # ~USD 16k at 25,000 VND/USD

# Dummy assignment cost when a vehicle has no feasible order: worse than any
# real fare but far better than infeasible, so padding never outbids work.
PADDING_EPS = -1e9


@dataclass
class Vehicle:
    vid: int
    soc: float = 0.60           # state of charge, 0..1
    node: int = 0               # current zone
    busy_until: float = 0.0     # sim-minutes
    available_km: float = 0.0
    odometer_km: float = 0.0
    cycles: float = 0.0
    trips: int = 0
    shift_trips: int = 0
    charging: bool = False
    charge_until: float = 0.0
    idle_km: float = 0.0
    # Which class this vehicle is. None means the default type, so every
    # existing caller that does not care keeps working untouched.
    type: VehicleType | None = None
    shift: str = "day"
    self_charge_threshold: float = 0.15
    driving_time_today: float = 0.0
    continuous_driving_min: float = 0.0
    charge_target: float = 1.0

    def spec(self) -> VehicleType:
        """This vehicle's type, defaulting rather than being Optional everywhere.

        A field that is None in 400 places is a field that will be None in one of
        them. Resolving it at the point of use keeps the call sites unchanged.
        """
        if isinstance(self.type, dict):
            return VehicleType(**self.type)
        return self.type or default_type()


@dataclass
class Order:
    oid: int
    origin: int
    dest: int
    distance_km: float
    created: float
    deadline: float
    is_airport: bool = False
    patience_min: float = 20.0
    rebooks_remaining: int = 3
    early_cancel: bool = False


@dataclass
class Zone:
    zid: int
    trips_per_hour: float
    mean_trip_km: float
    spread_km: float
    cx: float
    cy: float
    node: int | None = None
    name: str = ""
    kind: str = ""


@dataclass
class Config:
    n_vehicles: int = 60
    n_zones: int = 9
    days: int = 20
    tick_min: float = 2.0
    seed: int = 20260929
    soc_floor: float = 0.15        # hard reserve; below this the vehicle charges
    soc_price_weight: float = 0.0  # 0 = baseline (battery-blind), >0 = policy
    battery_energy_term: bool = True   # price the kWh the trip burns (term E)
    battery_opportunity_term: bool = True  # penalise arriving depleted (term O)
    scenario: str = "normal"
    max_trips_per_day: int = 18   # realistic single-shift workload
    # Fleet composition. `fleet_mix` maps a type key to how many of the 60 are
    # that type; it must sum to n_vehicles. Empty means "all of the default
    # type", which is what every pre-existing run used, so no published figure
    # changes. A mixed fleet is a different experiment and has to be asked for.
    fleet_mix: dict = field(default_factory=dict)
    open_hour: float = 5.0
    close_hour: float = 23.0
    map: str = "lattice"          # "lattice" (legacy 3x3) | "ocp1" (real OSM road graph)
    physics: str = "legacy"       # "legacy" (synthetic baseline) | "docx" (calibrated)


_PARAMS_PATH = ROOT / "data" / "ocp1_params.json"
_OCP1_PARAMS: dict | None = None


def get_ocp1_params() -> dict:
    """Load and cache OCP1 simulation parameters with float-converted charge targets."""
    global _OCP1_PARAMS
    if _OCP1_PARAMS is not None:
        return _OCP1_PARAMS
    if not _PARAMS_PATH.exists():
        return {}
    raw = _json.loads(_PARAMS_PATH.read_text(encoding="utf-8"))
    params = {}
    for section, sec_dict in raw.items():
        params[section] = {}
        for k, v in sec_dict.items():
            params[section][k] = v["value"] if isinstance(v, dict) and "value" in v else v

    # Float-convert driver.charge_target keys: {"0.8": 0.7, ...} -> {0.8: 0.7, ...}
    if "driver" in params and "charge_target" in params["driver"]:
        ct = params["driver"]["charge_target"]
        params["driver"]["charge_target"] = {float(k): float(val) for k, val in ct.items()}

    _OCP1_PARAMS = params
    return _OCP1_PARAMS


def calculate_fare(
    distance_km: float,
    hour: float = 12.0,
    is_airport: bool = False,
    physics: str = "legacy",
) -> float:
    """Calculate trip fare in VND for legacy and docx physics.

    Table 7 tariff:
      legacy: 68,000 + 12,500 * km
      docx:
        airport: 189,000 flat (<=20 km) + 9,500/km beyond 20 km
        distance-banded: 30,500 base (<=2 km) + 14,700/km (2-12 km) + 13,800/km (12-25 km) + 11,900/km (>25 km)
        night surcharge: +20,000 VND (22:00-06:00)
    """
    if physics == "legacy":
        return FARE_BASE_VND + FARE_PER_KM_VND * distance_km

    d = max(0.0, float(distance_km))
    if is_airport:
        base_fare = 189_000.0 if d <= 20.0 else 189_000.0 + 9_500.0 * (d - 20.0)
    else:
        if d <= 2.0:
            base_fare = 30_500.0
        elif d <= 12.0:
            base_fare = 30_500.0 + 14_700.0 * (d - 2.0)
        elif d <= 25.0:
            base_fare = 30_500.0 + 14_700.0 * 10.0 + 13_800.0 * (d - 12.0)
        else:
            base_fare = (
                30_500.0
                + 14_700.0 * 10.0
                + 13_800.0 * 13.0
                + 11_900.0 * (d - 25.0)
            )

    h = hour % 24.0
    night = 20_000.0 if (h >= 22.0 or h < 6.0) else 0.0
    return base_fare + night


compute_fare_vnd = calculate_fare


def calc_charge_duration_docx(
    soc: float,
    target_soc: float,
    battery_kwh: float,
    p_low: float = 40.0,
    p_high: float = 15.0,
    knee_soc: float = 0.80,
) -> float:
    """Calculate minutes to charge from soc to target_soc under two-tier curve."""
    if soc >= target_soc:
        return 0.0
    t = 0.0
    curr_soc = soc
    if curr_soc < knee_soc:
        s_end = min(knee_soc, target_soc)
        t += ((s_end - curr_soc) * battery_kwh / p_low) * 60.0
        curr_soc = s_end
    if curr_soc < target_soc:
        t += ((target_soc - curr_soc) * battery_kwh / p_high) * 60.0
    return t


def charge_step_docx(
    soc: float,
    battery_kwh: float,
    dt_min: float,
    target_soc: float = 1.0,
    p_low: float = 40.0,
    p_high: float = 15.0,
    knee_soc: float = 0.80,
) -> tuple[float, float]:
    """Advance battery charging over dt_min minutes with two-tier power curve.
    Returns (new_soc, kwh_in).
    """
    if soc >= target_soc or dt_min <= 0.0:
        return soc, 0.0

    kwh_in = 0.0
    rem_dt = dt_min

    if soc < knee_soc:
        cap = min(knee_soc, target_soc)
        e_needed = (cap - soc) * battery_kwh
        t_needed = (e_needed / p_low) * 60.0
        if rem_dt <= t_needed:
            e = p_low * (rem_dt / 60.0)
            return min(target_soc, soc + e / battery_kwh), e
        else:
            soc = cap
            kwh_in += e_needed
            rem_dt -= t_needed

    if soc < target_soc and rem_dt > 0.0:
        e_needed = (target_soc - soc) * battery_kwh
        t_needed = (e_needed / p_high) * 60.0
        if rem_dt <= t_needed:
            e = p_high * (rem_dt / 60.0)
            return min(target_soc, soc + e / battery_kwh), kwh_in + e
        else:
            soc = target_soc
            kwh_in += e_needed

    return soc, kwh_in


def apply_charging_step(v: Vehicle, dt_min: float, vt: VehicleType | None = None) -> float:
    """Advance vehicle charging using calibrated two-tier curve. Returns kwh_in."""
    sp = vt or v.spec()
    tgt = getattr(v, "charge_target", 1.0)
    new_soc, kwh_in = charge_step_docx(
        soc=v.soc, battery_kwh=sp.battery_kwh, dt_min=dt_min,
        target_soc=tgt, p_low=40.0, p_high=15.0, knee_soc=0.80
    )
    v.soc = new_soc
    v.available_km = sp.usable_km * v.soc
    v.cycles += kwh_in / sp.battery_kwh
    return kwh_in


def assign_driver_shift(vid: int, n_vehicles: int) -> str:
    """Assign driver shift: 70% day, 10% late, 20% night."""
    n_day = int(round(n_vehicles * 0.70))
    n_late = int(round(n_vehicles * 0.10))
    if vid < n_day:
        return "day"
    elif vid < n_day + n_late:
        return "late"
    return "night"


def is_shift_active(shift: str, hour: float) -> bool:
    """Return True if shift is currently on-duty."""
    h = hour % 24.0
    if shift == "day":
        return 6.0 <= h < 19.0
    elif shift == "late":
        return 10.0 <= h < 22.0
    elif shift == "night":
        # Spans midnight from 19:00 to 07:30
        return h >= 19.0 or h < 7.5
    return True


def apply_overnight_carryover(
    closing_fleet: list[Vehicle],
    day_idx: int,
    cfg: Config,
) -> list[Vehicle]:
    """Apply 50% overnight charging probability and thread state into Day d+1."""
    params = get_ocp1_params()
    targets = params.get("driver", {}).get(
        "charge_target", {0.8: 0.7, 0.9: 0.2, 1.0: 0.1}
    )
    target_keys = list(targets.keys())
    target_weights = list(targets.values())

    carry_rng = random.Random(cfg.seed * 99991 + day_idx * 1009)
    new_fleet = []
    for v in closing_fleet:
        sp = v.spec()
        new_v = Vehicle(
            vid=v.vid,
            soc=v.soc,
            node=v.node,
            odometer_km=v.odometer_km,
            cycles=v.cycles,
            type=v.type,
            shift=v.shift,
            self_charge_threshold=v.self_charge_threshold,
            idle_km=v.idle_km,
            trips=v.trips,
        )
        if carry_rng.random() < 0.50:
            tgt = carry_rng.choices(target_keys, weights=target_weights)[0]
            new_v.soc = max(new_v.soc, tgt)
        new_v.available_km = sp.usable_km * new_v.soc
        new_fleet.append(new_v)
    return new_fleet



# ---------------------------------------------------------------------------
# Hungarian algorithm (Kuhn-Munkres, O(n^3)). Rectangular: pad rows to columns.
# ---------------------------------------------------------------------------
def hungarian(cost: list[list[float]]) -> list[int]:
    """Minimum-cost perfect assignment. cost[i][j] -> row i goes to column j.

    Requires len(cost) <= len(cost[0]): rows are VEHICLES and columns are
    ORDERS, and a busy fleet can have more vehicles than pending orders. With
    n > m the augmenting-path loop below never finds a free column, `delta`
    stays infinite, and it spins forever -- caught by test_gsm_sim.py, which
    hung on a 4x3 matrix. Pad the columns instead.
    """
    n, m = len(cost), len(cost[0])
    assert n <= m, (
        f"hungarian needs rows <= columns, got {n}x{m}; "
        f"pad the columns with {n - m} dummy entries")
    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)      # p[j] = row matched to column j
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta, j1 = INF, -1
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j], way[j] = cur, j0
                if minv[j] < delta:
                    delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    ans = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            ans[p[j] - 1] = j - 1
    return ans


def travel_km(a: Zone, b: Zone) -> float:
    if getattr(a, "node", None) is not None and getattr(b, "node", None) is not None:
        return route_km(a.node, b.node)
    return math.hypot(a.cx - b.cx, a.cy - b.cy)


def build_ocp1_zones(cfg: Config) -> list[Zone]:
    """Construct the 9 authoritative OCP1 zones."""
    zone_specs = [
        (0, "vincom", 7262861319, 20.9942822, 105.9581313, "anchor", 13.5, 2.0, 1.5),
        (1, "vinschool", 7262861412, 20.9945928, 105.9364513, "anchor", 13.5, 2.0, 1.5),
        (2, "bus_depot", 7262861361, 20.9917915, 105.9605375, "anchor", 13.5, 2.0, 1.5),
        (3, "north", 642954579, 21.0103876, 105.9347303, "gate", 0.0, 10.0, 2.0),
        (4, "south", 10691095504, 20.9709609, 105.9516521, "gate", 0.0, 10.0, 2.0),
        (5, "west", 10876114913, 20.9993943, 105.9303469, "gate", 0.0, 10.0, 2.0),
        (6, "east", 4915951940, 21.0009873, 105.9661654, "gate", 0.0, 10.0, 2.0),
        (7, "st01", 8333311848, 20.9933723, 105.9609094, "residential", 13.5, 2.0, 1.5),
        (8, "st17", 12011835346, 20.9903610, 105.9401671, "residential", 13.5, 2.0, 1.5),
    ]
    return [
        Zone(zid=zid, trips_per_hour=tph, mean_trip_km=mkm, spread_km=skm,
             cx=lat, cy=lon, node=node, name=name, kind=kind)
        for zid, name, node, lat, lon, kind, tph, mkm, skm in zone_specs
    ]


def build_zones(cfg: Config, rng: random.Random) -> list[Zone]:
    """A 3x3 lattice over central Hanoi, sized so the whole fleet fits the
    demand. Trip lengths follow a lognormal-ish draw, which is what real
    city taxi traces look like: many short hops, a long tail of airport runs."""
    if getattr(cfg, "map", "lattice") == "ocp1":
        return build_ocp1_zones(cfg)
    zs = []
    for i in range(cfg.n_zones):
        r, c = divmod(i, 3)
        # central Hanoi: ~10 km across, zones ~4 km apart
        base = 1.0 + 11.0 * rng.random()
        # Demand sized so the fleet is genuinely CONSTRAINED but not absurd.
        #
        # Two calibrations, both wrong in opposite directions before this one:
        #   6-22/zone/hour  -> 2,596 orders vs ~1,200 servable, match rate 1.000
        #                       everywhere, pickup wait 0.0, and 84 trips per
        #                       vehicle-day, which no Hanoi taxi performs.
        #                       There was no dispatch problem to solve, so every
        #                       metric was measuring an empty queue.
        #   0.35-1.10       -> 127 orders against 1,080 capacity: 8% utilisation,
        #                       the mirror-image failure.
        # This one targets ~1,100-1,300 orders/day against 1,080 of vehicle-day
        # capacity, i.e. demand roughly equal to supply, where a dispatch
        # decision actually moves the match rate.
        zs.append(Zone(
            zid=i,
            trips_per_hour=rng.uniform(5.0, 10.0),
            mean_trip_km=max(1.6, rng.lognormvariate(1.35, 0.62)),
            spread_km=rng.uniform(1.0, 3.2),
            cx=base * 10.4, cy=(1.0 + 11.0 * rng.random()) * 10.4,
        ))
    return zs


def sample_orders_ocp1(cfg: Config, zones: list[Zone], n_orders: int, rng: random.Random) -> list[Order]:
    """Sample n_orders for OCP1 topology: 65% intra-OCP, 35% gateway."""
    internal = [z for z in zones if z.kind in ("anchor", "residential")]
    connected_gates = [z for z in zones if z.kind == "gate" and z.name not in ("east", "east_gate")]
    orders = []
    for oid in range(1, n_orders + 1):
        o_z = rng.choices(internal, weights=[z.trips_per_hour for z in internal])[0]
        if rng.random() < 0.35:
            d_z = min(connected_gates, key=lambda g: travel_km(o_z, g))
            hwy = max(6.0, min(16.0, rng.lognormvariate(2.302585092994046, 0.35)))
            dist = travel_km(o_z, d_z) + hwy
        else:
            d_z = rng.choice([z for z in internal if z.zid != o_z.zid])
            dist = travel_km(o_z, d_z)
        orders.append(Order(oid=oid, origin=o_z.zid, dest=d_z.zid,
                            distance_km=dist, created=0.0,
                            deadline=12.0 + 4.0 * dist))
    return orders



def make_scenario(cfg: Config) -> dict:
    """Multiplier profile per scenario. `rain` shifts demand later and lengthens
    trips; `peak` compresses demand into the evening; `night` empties it."""
    if cfg.scenario == "peak":
        return {"name": "peak", "rate": 1.85, "trip_len": 1.05,
                "energy_price": ENERGY_PRICE_PEAK_MULT,
                "hour_boost": (17.0, 21.0), "hours": (5.0, 23.0)}
    if cfg.scenario == "rain":
        return {"name": "rain", "rate": 0.72, "trip_len": 1.62,
                "energy_price": 1.25,
                "hour_boost": None, "hours": (5.0, 23.0)}
    if cfg.scenario == "night":
        return {"name": "night", "rate": 0.22, "trip_len": 1.15,
                "energy_price": 0.92, "hour_boost": None, "hours": (21.0, 5.0)}
    return {"name": "normal", "rate": 1.0, "trip_len": 1.0,
            "energy_price": 1.0, "hour_boost": (7.5, 9.5), "hours": (5.0, 23.0)}


def order_cost(v: Vehicle, o: Order, zones: list[Zone], cfg: Config) -> float:
    """Assignment cost, F+B form.

    F (company baseline, battery-blind): fare minus driver pay, minus the
    operating cost of deadhead plus trip distance. The company cost F is a
    black box -- its true weights are unknown -- so F here is our stand-in:
    greedy assignment with a hard SoC floor. The claim is never "our F equals
    GSM's F". The claim is that B, added on top of the same F, moves the
    metrics. Same stream, same F, only B differs: the difference isolates B.

    B (battery add-on, two terms priced at the current tariff):
      E: kWh the trip burns, priced at tariff. Rationale: energy is cash, so
         a trip that burns more should cost more to assign. Without E, a far
         trip on an empty battery prices identically to the same trip on a
         full one, and the matcher cannot prefer the efficient pairing.
      O: w * (1 - soc) * trip_km * kwh_per_km * tariff * 3.0. Rationale: the
         (1 - soc) shape penalises arriving depleted -- a vehicle at 25% pays
         3x the penalty of one at 75% for the same trip -- which reserves
         low-SoC vehicles for short trips instead of stranding them far from
         a charger. Linear in (1 - soc), not a curve spiking near empty,
         because the hard SoC floor already handles the near-empty case; O
         shapes choices above the floor. The x3.0 scales the penalty to the
         same order as the fare margin so it actually moves assignments; at
         x1.0 it prices correctly but too quietly to matter (ablation in
         gsm_sensitivity.py measures this). Without O, E alone prices energy
         but never protects a nearly-empty vehicle from a long trip it can
         barely finish -- feasible, yet fragile.

    Negative values are allowed and meaningful: a fare minus driver pay is
    the gross contribution of taking this trip.
    """
    if getattr(cfg, "physics", "legacy") == "docx":
        h_order = (o.created / 60.0) % 24.0
        fare = calculate_fare(
            o.distance_km,
            hour=h_order,
            is_airport=getattr(o, "is_airport", False),
            physics="docx",
        )
        floor = getattr(v, "self_charge_threshold", cfg.soc_floor)
    else:
        fare = FARE_BASE_VND + FARE_PER_KM_VND * o.distance_km
        floor = cfg.soc_floor
    gross = fare - DRIVER_PAY_VND_PER_TRIP
    # deadhead to the pickup
    pick = travel_km(zones[v.node], zones[o.origin])
    total = o.distance_km + pick
    need = o.distance_km + pick

    # available_km IS already soc * USABLE_KM. An earlier version multiplied
    # it by USABLE_KM * soc a second time, so a 49%-charged vehicle looked as
    # if it had 26,000 km of range and every trip was assignable. Caught by
    # test_no_trip_exceeds_battery: 4007 assignments needed more charge than
    # the vehicle held.
    if v.soc < floor or v.available_km < need:
        return float("inf")   # not assignable

    op = total * OPEX_VND_PER_KM
    if cfg.soc_price_weight > 0:
        # Term E: energy actually spent, priced at the current tariff.
        # Term O: opportunity penalty for arriving with a depleted pack.
        # Independent flags so the ablation study can knock each out.
        energy = 0.0
        sp = v.spec()
        consumption = sp.kwh_per_km if getattr(cfg, "physics", "legacy") == "docx" else CONSUMPTION_KWH_PER_KM
        if cfg.battery_energy_term:
            kwh = total * consumption
            energy = kwh * ENERGY_PRICE_VND_PER_KWH * 1.0
        if cfg.battery_opportunity_term:
            op += cfg.soc_price_weight * (1.0 - v.soc) * total * consumption \
                  * ENERGY_PRICE_VND_PER_KWH * 3.0
        return -(gross - op - energy)
    return -(gross - op)


def run_day(cfg: Config, zones: list[Zone], day_idx: int, rng: random.Random,
            collect: list | None = None,
            soc_trace: list | None = None,
            trace_every: int = 1,
            opening_fleet: list[Vehicle] | None = None) -> dict:
    """Run one simulated day.

    `soc_trace`, when given, receives one dict per traced tick per vehicle --
    the per-vehicle state of charge that `results/*.json` currently collapses
    into a single daily `mean_soc`. It is observation only: every number the
    simulation itself uses is computed before the trace is appended, so
    collecting a trace cannot change the outcome. Proven, not assumed:
    `test_gsm_sim.py::test_soc_trace_does_not_change_results` runs a day with
    and without tracing and compares all 18 output fields.

    Trace volume: n_vehicles x (ticks per day) rows. At the default 60 vehicles
    x 540 ticks that is 32,400 rows per vehicle-day, so a 20-day run is ~648k
    rows -- about 60 MB of JSON. Pass `trace_every=6` for 108k rows per day.
    """
    sc = make_scenario(cfg)
    is_docx = getattr(cfg, "physics", "legacy") == "docx"
    per_day = {k: 0.0 for k in
               ("revenue_vnd", "energy_vnd", "trips", "requests", "match_rate",
                "pickup_wait_min", "charger_wait_min", "deadhead_km",
                "distance_km", "soc_deficit", "stranded_min", "charge_events",
                "swap_events", "cancel_before", "cancel_after", "wasted_km",
                "rebooks")}
    # Two independent streams from one seed. Demand must NOT depend on policy:
    # a single rng shared by the arrival generator and the charging logic means
    # a policy that dispatches a different number of vehicles to charge also
    # draws a different number of random numbers per tick, so the next tick's
    # arrivals differ. The two arms then see different worlds and every metric
    # difference is noise. Measured: 2247 vs 2243 requests on the same seed.
    # demand_rng drives arrivals only; policy_rng drives decisions.
    rng_day = random.Random(cfg.seed * 7919 + day_idx)
    policy_rng = random.Random(cfg.seed * 104729 + day_idx * 31)

    types = build_fleet_types(cfg)
    if is_docx and opening_fleet is not None and day_idx > 0:
        fleet = apply_overnight_carryover(opening_fleet, day_idx, cfg)
    else:
        fleet = []
        for i in range(cfg.n_vehicles):
            vt = types[i % len(types)]
            v = Vehicle(vid=i, soc=rng_day.uniform(0.45, 0.95),
                        node=(rng_day.choice([z.zid for z in zones if z.name not in ("east", "east_gate")])
                              if getattr(cfg, "map", "lattice") == "ocp1" else rng_day.randrange(cfg.n_zones)),
                        type=vt)
            v.available_km = vt.usable_km * v.soc  # set once; updated on every spend
            if is_docx:
                v.shift = assign_driver_shift(i, cfg.n_vehicles)
                driver_rng = random.Random(cfg.seed * 31337 + i)
                v.self_charge_threshold = driver_rng.uniform(0.08, 0.25)
            fleet.append(v)

    pending: list[Order] = []
    oid = 0
    t = sc["hours"][0] * 60.0
    end = sc["hours"][1] * 60.0
    if end <= t:
        end = t + 12 * 60.0

    # charger queue state per zone
    charger_free_at: list[list[float]] = [
        [0.0] * PORTS_PER_ZONE for _ in range(len(zones))]

    while t < end:
        # ---- generate arrivals for this tick
        hours_here = cfg.tick_min / 60.0
        boosted = 1.0
        if sc["hour_boost"] and sc["hour_boost"][0] <= (t / 60.0) % 24 <= sc["hour_boost"][1]:
            boosted = 1.45
        lam = sum(z.trips_per_hour for z in zones) * hours_here * sc["rate"] * boosted
        k = rng_day.random()
        n_new = int(lam) + (1 if (lam - int(lam)) > k else 0)
        for _ in range(n_new):
            if getattr(cfg, "map", "lattice") == "ocp1":
                internal = [z for z in zones if z.kind in ("anchor", "residential")]
                connected_gates = [z for z in zones if z.kind == "gate" and z.name not in ("east", "east_gate")]
                o_z = rng_day.choices(internal, weights=[z.trips_per_hour for z in internal])[0]
                if rng_day.random() < 0.35:
                    d_z = min(connected_gates, key=lambda g: travel_km(o_z, g))
                    hwy = max(6.0, min(16.0, rng_day.lognormvariate(2.302585092994046, 0.35)))
                    dist = travel_km(o_z, d_z) + hwy
                else:
                    d_z = rng_day.choice([z for z in internal if z.zid != o_z.zid])
                    dist = travel_km(o_z, d_z)
            else:
                o_z = rng_day.choices(zones, weights=[z.trips_per_hour for z in zones])[0]
                d_z = rng_day.choices(zones, weights=[z.trips_per_hour for z in zones])[0]
                if d_z.zid == o_z.zid and cfg.n_zones > 1:
                    d_z = rng_day.choice(zones)
                raw = rng_day.lognormvariate(
                    math.log(max(0.8, o_z.mean_trip_km * sc["trip_len"])), 0.55)
                dist = max(0.8, min(raw, 70.0))
            oid += 1
            if is_docx:
                early = rng_day.random() < 0.05
                pat = rng_day.uniform(0.5, cfg.tick_min) if early else rng_day.expovariate(1.0 / 20.0)
                dl = t + pat
                pending.append(Order(oid=oid, origin=o_z.zid, dest=d_z.zid,
                                     distance_km=dist, created=t, deadline=dl,
                                     patience_min=pat, early_cancel=early))
            else:
                pending.append(Order(oid=oid, origin=o_z.zid, dest=d_z.zid,
                                     distance_km=dist, created=t,
                                     deadline=t + 12 + 4 * dist))

        per_day["requests"] += n_new

        # ---- retire / cancel unassigned orders
        if is_docx:
            surviving: list[Order] = []
            for o in pending:
                if (t - o.created) >= o.patience_min or t >= o.deadline:
                    per_day["cancel_before"] += 1
                    if o.rebooks_remaining > 0 and rng_day.random() < 0.55:
                        o.rebooks_remaining -= 1
                        per_day["rebooks"] += 1
                        o.created = t
                        decay = 0.7 ** (3 - o.rebooks_remaining)
                        o.patience_min = rng_day.expovariate(1.0 / (20.0 * decay))
                        o.deadline = t + o.patience_min
                        surviving.append(o)
                else:
                    surviving.append(o)
            pending = surviving
        else:
            pending = [o for o in pending if o.deadline > t]

        # ---- advance vehicle states
        avail: list[Vehicle] = []
        h_now = (t / 60.0) % 24.0
        for v in fleet:
            if v.charging:
                sp = v.spec()
                if is_docx:
                    tgt = getattr(v, "charge_target", 1.0)
                    v.soc, kwh_in = charge_step_docx(
                        soc=v.soc, battery_kwh=sp.battery_kwh, dt_min=cfg.tick_min,
                        target_soc=tgt, p_low=40.0, p_high=15.0, knee_soc=0.80
                    )
                    v.cycles += kwh_in / sp.battery_kwh
                    if t >= v.charge_until or v.soc >= tgt - 1e-6:
                        v.charging = False
                        v.available_km = sp.usable_km * v.soc
                        v.continuous_driving_min = 0.0
                else:
                    # minutes of charge accumulated
                    kwh_in = CHARGE_POWER_KW * cfg.tick_min / 60.0
                    v.soc = min(1.0, v.soc + kwh_in * CHARGE_EFFICIENCY / sp.battery_kwh)
                    v.cycles += kwh_in / sp.battery_kwh
                    if t >= v.charge_until:
                        v.charging = False
                        v.available_km = sp.usable_km * v.soc
                continue

            if t >= v.busy_until + 30.0:
                v.continuous_driving_min = 0.0

            if t >= v.busy_until and v.shift_trips < cfg.max_trips_per_day:
                if is_docx:
                    if is_shift_active(v.shift, h_now) and v.driving_time_today < 600.0:
                        avail.append(v)
                else:
                    avail.append(v)

        # ---- assign: Hungarian over (available vehicles) x (pending orders)
        taken_orders: set[int] = set()
        if avail and pending:
            # Pad columns so rows <= cols. A dummy column costs PADDING_EPS,
            # which is strictly worse than any real assignment but cheaper than
            # an infeasible one, so a vehicle is left unassigned only when it
            # genuinely has no feasible order.
            n_real = len(pending)
            n_pad = max(0, len(avail) - n_real)
            cost: list[list[float]] = []
            for v in avail:
                row = []
                for o in pending:
                    c = order_cost(v, o, zones, cfg)
                    row.append(1e12 if math.isinf(c) else c)
                row.extend([PADDING_EPS] * n_pad)
                cost.append(row)
            assign = hungarian(cost)
            for i, j in enumerate(assign):
                if j < 0 or j >= len(pending):
                    continue
                if cost[i][j] >= 1e11:
                    continue
                v, o = avail[i], pending[j]
                if o.oid in taken_orders:
                    continue
                pick = travel_km(zones[v.node], zones[o.origin])
                per_day["pickup_wait_min"] += t - o.created

                if is_docx:
                    speed_kmh = (
                        32.0 if (h_now >= 22.0 or h_now < 6.0)
                        else 15.0 if (6.75 <= h_now <= 7.5 or 17.0 <= h_now <= 19.0)
                        else 22.0
                    )
                    eta_min = (pick / speed_kmh) * 60.0 if speed_kmh > 0 else 0.0
                    rem_patience = o.patience_min - (t - o.created)

                    if eta_min > 0 and rem_patience < eta_min:
                        per_day["cancel_after"] += 1
                        frac = max(0.0, rem_patience) / eta_min
                        wasted = pick * frac
                        per_day["wasted_km"] += wasted
                        per_day["deadhead_km"] += wasted

                        sp = v.spec()
                        spent = wasted * sp.kwh_per_km
                        v.soc = max(0.0, v.soc - spent / sp.battery_kwh)
                        v.cycles += spent / sp.battery_kwh
                        v.available_km = sp.usable_km * v.soc
                        v.odometer_km += wasted
                        v.idle_km += wasted
                        v.busy_until = t + max(0.0, rem_patience)
                        if frac >= 0.5:
                            v.node = o.origin
                        per_day["energy_vnd"] += spent * ENERGY_PRICE_VND_PER_KWH * sc["energy_price"]

                        taken_orders.add(o.oid)
                        if o.rebooks_remaining > 0 and rng_day.random() < 0.55:
                            rebooks_left = o.rebooks_remaining - 1
                            per_day["rebooks"] += 1
                            t_new = t + max(0.0, rem_patience)
                            decay = 0.7 ** (3 - rebooks_left)
                            pat_new = rng_day.expovariate(1.0 / (20.0 * decay))
                            oid += 1
                            rebooked = Order(
                                oid=oid, origin=o.origin, dest=o.dest,
                                distance_km=o.distance_km, created=t_new,
                                deadline=t_new + pat_new, patience_min=pat_new,
                                rebooks_remaining=rebooks_left, is_airport=getattr(o, "is_airport", False)
                            )
                            pending.append(rebooked)
                        continue

                per_day["deadhead_km"] += pick
                # serve the trip: deduct energy for deadhead + fare distance
                sp = v.spec()
                spent = (pick + o.distance_km) * sp.kwh_per_km
                v.soc = max(0.0, v.soc - spent / sp.battery_kwh)
                v.cycles += spent / sp.battery_kwh
                v.available_km = sp.usable_km * v.soc
                drive_time = (pick / 22.0 + o.distance_km / 22.0) * 60.0
                v.busy_until = t + pick / 22.0 + o.distance_km / 22.0   # ~22 km/h city avg
                v.node = o.dest
                v.trips += 1
                v.shift_trips += 1
                v.odometer_km += pick + o.distance_km
                v.idle_km += pick

                if is_docx:
                    v.driving_time_today += drive_time
                    v.continuous_driving_min += drive_time
                    if v.continuous_driving_min >= 240.0:
                        v.busy_until = max(v.busy_until, t + 30.0)
                        v.continuous_driving_min = 0.0

                    fare = calculate_fare(
                        o.distance_km,
                        hour=h_now,
                        is_airport=getattr(o, "is_airport", False),
                        physics="docx",
                    )
                else:
                    fare = FARE_BASE_VND + FARE_PER_KM_VND * o.distance_km

                per_day["revenue_vnd"] += fare
                per_day["energy_vnd"] += spent * ENERGY_PRICE_VND_PER_KWH * sc["energy_price"]
                per_day["distance_km"] += o.distance_km
                taken_orders.add(o.oid)
            pending = [o for o in pending if o.oid not in taken_orders]

        per_day["match_rate"] += len(taken_orders)

        # ---- dispatch vehicles to charge when they cannot serve
        for v in avail:
            thresh = v.self_charge_threshold if is_docx else cfg.soc_floor
            if v.soc < thresh or (v.available_km < 25.0 and policy_rng.random() < 0.35):
                sp = v.spec()
                z = v.node
                if sp.swap_based:
                    # A swap-based vehicle changes battery rather than charging.
                    per_day["swap_events"] += 1
                    travel = SWAP_TRAVEL_KM + policy_rng.random() * 2.0
                    v.soc = max(0.0, v.soc - travel * sp.kwh_per_km / sp.battery_kwh)
                    v.odometer_km += travel
                    v.idle_km += travel
                    v.available_km = sp.usable_km * v.soc
                    v.charging = True
                    v.charge_until = t + sp.swap_minutes
                    # a swap installs a fresh battery: the pack returns to full
                    v.soc = 1.0
                    v.available_km = sp.usable_km
                    v.cycles += 0.0   # a swapped-out pack's cycles accrue elsewhere
                    continue

                if is_docx:
                    params = get_ocp1_params()
                    targets = params.get("driver", {}).get(
                        "charge_target", {0.8: 0.7, 0.9: 0.2, 1.0: 0.1}
                    )
                    tgt = policy_rng.choices(list(targets.keys()), weights=list(targets.values()))[0]
                    v.charge_target = tgt
                    charge_min = calc_charge_duration_docx(v.soc, tgt, sp.battery_kwh, 40.0, 15.0, 0.80)
                else:
                    charge_min = max((1.0 - v.soc) * sp.battery_kwh / CHARGE_POWER_KW * 60.0,
                                     SWAP_OR_FASTCHARGE_MIN)

                # Next free slot at this zone's depot.
                slots = charger_free_at[z]
                start = max(t, slots[0])
                heapq.heapreplace(slots, start + charge_min)
                per_day["charger_wait_min"] += start - t
                per_day["charge_events"] += 1
                travel = 3.0 + policy_rng.random() * 5.0
                v.soc = max(0.0, v.soc - travel * sp.kwh_per_km / sp.battery_kwh)
                v.odometer_km += travel
                v.idle_km += travel
                v.available_km = sp.usable_km * v.soc
                v.charging = True
                v.charge_until = start + charge_min
                if not is_docx:
                    v.cycles += charge_min / 60.0 * CHARGE_POWER_KW / sp.battery_kwh

        # ---- parked vehicle idle AC drain under calibrated docx physics
        if is_docx:
            drain_kwh = 1.2 * (cfg.tick_min / 60.0)
            for v in fleet:
                if not v.charging and t >= v.busy_until:
                    sp = v.spec()
                    v.soc = max(0.0, v.soc - drain_kwh / sp.battery_kwh)
                    v.available_km = sp.usable_km * v.soc

        # ---- stranded: charging fleet while orders wait and nobody can serve
        served_cap = [v for v in fleet if not v.charging and t >= v.busy_until]
        if pending and not served_cap:
            per_day["stranded_min"] += cfg.tick_min

        # ---- SoC deficit: how far the fleet sits below a comfortable reserve
        per_day["soc_deficit"] += sum(max(0.0, cfg.soc_floor + 0.20 - v.soc)
                                      for v in fleet) / len(fleet)

        # ---- per-vehicle SoC trace (observation only; nothing below reads it)
        if soc_trace is not None and int(round(t, 6)) % trace_every == 0:
            for v in fleet:
                soc_trace.append({
                    "day": day_idx,
                    "tick": int(round(t, 6)),
                    "minute": round(t, 2),
                    "hour": round(t / 60.0, 4),
                    "vehicle_id": v.vid,
                    "soc": round(v.soc, 6),
                    "soc_pct": round(v.soc * 100.0, 3),
                    "available_km": round(v.available_km, 3),
                    "energy_kwh": round(v.soc * BATTERY_KWH, 4),
                    "node": v.node,
                    "odometer_km": round(v.odometer_km, 4),
                    "charging": v.charging,
                    "state": ("charging" if v.charging else
                              "busy" if t < v.busy_until else
                              "idle" if v.soc < cfg.soc_floor else "ready"),
                })

        t += cfg.tick_min

    # ---- aggregate
    demand = per_day["requests"] or 1
    out = {
        "day": day_idx,
        "scenario": sc["name"],
        "revenue_vnd": per_day["revenue_vnd"],
        "energy_vnd": per_day["energy_vnd"],
        "trips": int(per_day["match_rate"]),
        "requests": int(per_day["requests"]),
        "match_rate": per_day["match_rate"] / demand,
        "mean_trip_vnd": (per_day["revenue_vnd"] / per_day["match_rate"]
                          if per_day["match_rate"] else 0.0),
        "pickup_wait_min": (per_day["pickup_wait_min"] / per_day["match_rate"]
                            if per_day["match_rate"] else 0.0),
        "charger_wait_min": (per_day["charger_wait_min"]
                             / max(1, per_day["charge_events"])),
        "deadhead_km": per_day["deadhead_km"],
        "deadhead_ratio": (per_day["deadhead_km"] / per_day["distance_km"]
                           if per_day["distance_km"] else 0.0),
        "distance_km": per_day["distance_km"],
        "soc_deficit": (per_day["soc_deficit"] /
                        ((end - sc["hours"][0] * 60.0) / cfg.tick_min)),
        "stranded_min": per_day["stranded_min"],
        "mean_soc": sum(v.soc for v in fleet) / len(fleet),
        "trips_per_vehicle_day": sum(v.trips for v in fleet) / len(fleet),
        "odometer_km": sum(v.odometer_km for v in fleet),
        "fleet_km": sum(v.odometer_km for v in fleet),
    }
    if is_docx:
        out["cancel_before"] = int(per_day["cancel_before"])
        out["cancel_after"] = int(per_day["cancel_after"])
        out["wasted_km"] = per_day["wasted_km"]
        out["rebooks"] = int(per_day["rebooks"])
        out["_fleet"] = fleet
    if collect is not None:
        collect.append(out)
    return out


def summarise(days: list[dict]) -> dict:
    keys = [k for k in days[0] if k not in ("day", "scenario", "_fleet") and
            isinstance(days[0][k], (int, float))]
    n = len(days)
    mu = {k: sum(d[k] for d in days) / n for k in keys}
    sd = {}
    for k in keys:
        var = sum((d[k] - mu[k]) ** 2 for d in days) / max(1, n - 1)
        sd[k] = math.sqrt(var)
    return {"n_days": n, "mean": mu, "sd": sd,
            "sem": {k: sd[k] / math.sqrt(n) for k in keys}}


def run_arm(cfg: Config, label: str, out: Path) -> dict:
    rng0 = random.Random(cfg.seed)
    zones = build_zones(cfg, rng0)
    days = []
    fleet = None
    for d in range(cfg.days):
        day_res = run_day(cfg, zones, d, rng0, opening_fleet=fleet)
        days.append(day_res)
        if getattr(cfg, "physics", "legacy") == "docx":
            fleet = day_res.get("_fleet")
    s = summarise(days)
    s["label"] = label
    s["config"] = asdict(cfg)
    clean_days = [{k: v for k, v in d.items() if k != "_fleet"} for d in days]
    out.write_text(json.dumps({"summary": s, "days": clean_days}, indent=1),
                   encoding="utf-8")
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--vehicles", type=int, default=60)
    ap.add_argument("--seed", type=int, default=20260929)
    ap.add_argument("--outdir", default="results")
    ap.add_argument("--map", choices=["lattice", "ocp1"], default="lattice")
    ap.add_argument("--physics", choices=["legacy", "docx"], default="legacy")
    args = ap.parse_args()

    outdir = ROOT / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    results = {}
    for scenario in ("normal", "peak", "rain", "night"):
        base_cfg = Config(days=args.days, seed=args.seed,
                          n_vehicles=args.vehicles, scenario=scenario,
                          map=args.map, physics=args.physics)
        base = run_arm(base_cfg, f"{scenario}-baseline", outdir / f"{scenario}-baseline.json")
        pol = run_arm(Config(**{**asdict(base_cfg), "soc_price_weight": 1.0}),
                      f"{scenario}-battery-aware", outdir / f"{scenario}-policy.json")
        results[scenario] = {"baseline": base, "policy": pol}
        b, p = base["mean"], pol["mean"]
        print(f"\n== {scenario.upper()} ({args.days} days, {args.vehicles} vehicles)")
        for k, lab, pct in (("revenue_vnd", "revenue        ", False),
                            ("match_rate", "match rate     ", False),
                            ("pickup_wait_min", "pickup wait    ", True),
                            ("charger_wait_min", "charger wait   ", True),
                            ("deadhead_ratio", "deadhead ratio ", True)):
            bv, pv = b[k], p[k]
            better = pv < bv if pct else pv > bv
            delta = (pv - bv) / bv * 100.0 if bv else 0.0
            flag = "better" if better else ("worse" if abs(delta) > 0.5 else "same")
            print(f"   {lab} base {bv:>12,.1f}   pol {pv:>12,.1f}   "
                  f"{delta:+6.1f}%  {flag}")
    (outdir / "all.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nwrote {outdir.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())