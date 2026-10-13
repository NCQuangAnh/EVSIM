"""Synthetic Hanoi ride requests. Replace `generate` with a loader once GSM trip logs arrive."""
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .geo import road_km

# (lat, lon, weight): inner-district hotspots
HOTSPOTS = np.array([
    (21.0285, 105.8542, 1.5),  # Hoan Kiem
    (21.0340, 105.8140, 1.0),  # Ba Dinh
    (21.0180, 105.8290, 1.2),  # Dong Da
    (21.0330, 105.7900, 1.3),  # Cau Giay
    (21.0060, 105.8570, 1.0),  # Hai Ba Trung
    (20.9950, 105.8100, 1.0),  # Thanh Xuan
    (21.0680, 105.8230, 0.7),  # Tay Ho
    (21.0450, 105.8900, 0.6),  # Long Bien
])
HOTSPOT_SIGMA_DEG = 0.012      # ~1.3 km
AIRPORT = (21.2187, 105.8042)  # Noi Bai

# relative request intensity per hour, morning and evening peaks
HOURLY = np.array([0.5, 0.3, 0.2, 0.2, 0.3, 0.8, 2.0, 4.5, 5.5, 4.0, 3.5, 3.8,
                   4.2, 3.8, 3.5, 3.8, 4.8, 6.0, 6.5, 5.0, 4.2, 3.5, 2.5, 1.2])
HOURLY = HOURLY / HOURLY.sum()

MIN_TRIP_KM = 1.0


@dataclass
class Request:
    id: int
    t: float
    o_lat: float
    o_lon: float
    d_lat: float
    d_lon: float
    trip_km: float
    patience_s: float
    trip_id: int = -1          # same for every (re)booking of one journey
    attempt: int = 1
    early: bool = False        # cancels early for non-ETA reasons (address, price, changed mind)
    airport: bool = False      # to/from Noi Bai, priced with the airport package
    status: str = "pending"   # pending | served | cancel_unassigned | cancel_assigned | failed_stranded
    t_assign: Optional[float] = None
    t_pickup: Optional[float] = None
    t_dropoff: Optional[float] = None
    pickup_km: Optional[float] = None
    vehicle: Optional[int] = None
    assign_lat: Optional[float] = None  # where the matched vehicle was (or would be free) when matched
    assign_lon: Optional[float] = None
    wasted_km: float = 0.0    # deadhead driven before the rider cancelled
    fare: float = 0.0


def sample_points(rng, n):
    w = HOTSPOTS[:, 2] / HOTSPOTS[:, 2].sum()
    idx = rng.choice(len(HOTSPOTS), size=n, p=w)
    lat = HOTSPOTS[idx, 0] + rng.normal(0, HOTSPOT_SIGMA_DEG, n)
    lon = HOTSPOTS[idx, 1] + rng.normal(0, HOTSPOT_SIGMA_DEG, n)
    return lat, lon


def generate(cfg, rng):
    n_hours = int(np.ceil(cfg.sim_hours))
    times = []
    for h in range(n_hours):
        k = rng.poisson(cfg.daily_requests * HOURLY[h % 24])
        times.append(h * 3600 + rng.uniform(0, 3600, k))
    times = np.sort(np.concatenate(times))
    times = times[times < cfg.sim_hours * 3600]
    n = len(times)

    o_lat, o_lon = sample_points(rng, n)
    d_lat, d_lon = sample_points(rng, n)
    # airport trips: half to the airport, half from it
    airport = rng.random(n) < cfg.airport_share
    to_airport = airport & (rng.random(n) < 0.5)
    from_airport = airport & ~to_airport
    d_lat[to_airport], d_lon[to_airport] = AIRPORT
    o_lat[from_airport], o_lon[from_airport] = AIRPORT
    # resample destinations of too-short trips
    km = road_km(o_lat, o_lon, d_lat, d_lon, cfg.detour)
    short = km < MIN_TRIP_KM
    while short.any():
        d_lat[short], d_lon[short] = sample_points(rng, short.sum())
        km = road_km(o_lat, o_lon, d_lat, d_lon, cfg.detour)
        short = km < MIN_TRIP_KM

    patience = rng.exponential(cfg.patience_mean_min * 60, n)
    early = np.zeros(n, dtype=bool)
    if cfg.rebook:
        early = rng.random(n) < cfg.p_early_cancel
        patience[early] = np.minimum(patience[early], rng.uniform(30, 180, early.sum()))
    return [Request(i, times[i], o_lat[i], o_lon[i], d_lat[i], d_lon[i], float(km[i]), patience[i],
                    trip_id=i, early=bool(early[i]), airport=bool(airport[i]))
            for i in range(n)]


# simulated area (matches data/road_cells.npz) plus a ~2 km margin
AREA = (20.95 - 0.02, 21.24 + 0.02, 105.74 - 0.02, 105.93 + 0.02)


def load_stations(cfg, path):
    """Real station list. Returns (lat/lon array, ports, effective charging kW per station).
    Missing ports / power fall back to cfg.ports_per_station / cfg.dc_kw."""
    import pandas as pd
    df = pd.read_csv(path)
    s, n, w, e = AREA
    df = df[df.lat.between(s, n) & df.lon.between(w, e)]
    if "for_cars" in df:
        df = df[df.for_cars.astype(bool)]
    df = df.reset_index(drop=True)
    ports = df["ports"] if "ports" in df else pd.Series(np.nan, index=df.index)
    if "dc_ports" in df:
        ports = df["dc_ports"].fillna(ports)          # cars use the DC connectors when present
    if "ports_est" in df:
        ports = df["ports_est"]                        # scripts/assign_station_ports.py
    ports = ports.fillna(cfg.ports_per_station).clip(lower=1).astype(int).to_numpy()
    kw = np.full(len(df), cfg.dc_kw)
    if "max_kw" in df:
        is_dc = df.get("dc_ports", pd.Series(np.nan, index=df.index)).fillna(0).to_numpy() > 0
        known = df.max_kw.notna().to_numpy()
        nominal = df.max_kw.to_numpy()
        dc = known & is_dc
        ac = known & ~is_dc
        kw[dc] = np.minimum(nominal[dc], cfg.vehicle_max_dc_kw) * cfg.dc_curve_factor
        kw[ac] = np.minimum(nominal[ac], cfg.vehicle_max_ac_kw)
    return df[["lat", "lon"]].to_numpy(), ports, kw


def sample_stations(cfg, rng):
    lat, lon = sample_points(rng, cfg.n_stations)
    return np.column_stack([lat, lon])
