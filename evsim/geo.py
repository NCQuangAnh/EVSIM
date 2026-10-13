from pathlib import Path

import numpy as np

EARTH_R_KM = 6371.0
ROAD_DATA = Path(__file__).resolve().parent.parent / "data" / "road_cells.npz"

_router = None


class CellRouter:
    """OSM shortest-path road distances between ~1 km grid cells (built offline by
    scripts/build_osm_data.py). Points are snapped to their cell's representative node."""

    def __init__(self, path):
        z = np.load(path)
        self.lat0, self.lon0, self.step = float(z["lat0"]), float(z["lon0"]), float(z["step"])
        self.grid = z["grid"]          # (rows, cols) -> compact cell index or -1
        self.dist = z["dist_km"]       # (cells, cells) road km, inf if unreachable

    def cell(self, lat, lon):
        r = np.floor((np.asarray(lat) - self.lat0) / self.step).astype(int)
        c = np.floor((np.asarray(lon) - self.lon0) / self.step).astype(int)
        inside = (r >= 0) & (r < self.grid.shape[0]) & (c >= 0) & (c < self.grid.shape[1])
        return np.where(inside, self.grid[np.clip(r, 0, self.grid.shape[0] - 1),
                                          np.clip(c, 0, self.grid.shape[1] - 1)], -1)


def set_router(enabled):
    """True: Hanoi OSM cell router; "ocp1": node router of the Ocean Park 1 demo; falsy: none."""
    global _router
    if enabled == "ocp1":
        from .ocp1 import router
        _router = router()
    else:
        _router = CellRouter(ROAD_DATA) if enabled else None


def haversine_km(lat1, lon1, lat2, lon2):
    """Broadcasting great-circle distance in km."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))


def road_km(lat1, lon1, lat2, lon2, detour):
    """Road distance. With the OSM router: shortest path between the two points' grid cells;
    same-cell, off-grid or unreachable pairs fall back to detour * great-circle distance."""
    if _router is not None and hasattr(_router, "road"):   # node-level router (OCP1)
        out = _router.road(lat1, lon1, lat2, lon2, detour)
        return float(out) if np.ndim(out) == 0 else out
    hav = haversine_km(lat1, lon1, lat2, lon2)
    if _router is None:
        return detour * hav
    c1, c2 = np.broadcast_arrays(_router.cell(lat1, lon1), _router.cell(lat2, lon2))
    valid = (c1 >= 0) & (c2 >= 0) & (c1 != c2)
    d = np.where(valid, _router.dist[np.maximum(c1, 0), np.maximum(c2, 0)], np.inf)
    out = np.where(np.isfinite(d), np.maximum(d, hav), detour * hav)
    return float(out) if out.ndim == 0 else out


def speed_kmh(t_s):
    """Average urban speed by hour of day (assumption, Hanoi-like congestion)."""
    h = (t_s / 3600.0) % 24
    if 7 <= h < 9 or 17 <= h < 19:
        return 15.0
    if 6 <= h < 22:
        return 22.0
    return 32.0


def travel_s(km, t_s):
    return km / speed_kmh(t_s) * 3600.0
