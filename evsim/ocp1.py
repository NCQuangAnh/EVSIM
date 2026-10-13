"""Vinhomes Ocean Park 1 (OCP1) demo world: node-level road network, demand, chargers.

Data (docs/OCP1_DATA.md): data/ocp1/ocp1_graph.json (OSM, 1,110 nodes, edges [u, v, km, kmh],
pois: stations, gates, anchors) and data/ocp1/ocp1_stations_demo40.json (40 car DC ports).

The router answers road distances between any two points: points inside the area snap to the
nearest node of the main connected component; a point outside the area (destination of a
gateway trip) is reached through the gate that gives the shortest total, the part outside the
map counted as detour x great-circle distance.
"""
import json
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

from .geo import haversine_km

DATA = Path(__file__).resolve().parent.parent / "data" / "ocp1"
GRAPH = DATA / "ocp1_graph.json"
STATIONS = DATA / "ocp1_stations_demo40.json"
CACHE = DATA / "ocp1_router.npz"
LAKE_EDGES = {120, 206, 551, 552, 871, 923}          # San Ho lake: never cross the water
SNAP_KM = 0.35                                       # farther than this from any node = outside the map
# demand anchors (docs/OCP1_DATA.md, zones without the isolated east gate): lat, lon, weight
ZONES = np.array([
    (20.99400, 105.95863, 3.0),   # Vincom Mega Mall
    (20.99448, 105.93663, 2.0),   # Vinschool
    (20.99195, 105.96066, 1.0),   # VinBus depot
    (21.01039, 105.93473, 0.6),   # north gate
    (20.97096, 105.95165, 0.6),   # south gate
    (20.98801, 105.93882, 0.8),   # west gate
    (20.99950, 105.94720, 2.5),   # Sapphire 1 (north)
    (20.99220, 105.93920, 2.5),   # Sapphire 2 (west)
    (20.98950, 105.94860, 2.0),   # Sapphire 3 / Ruby (centre-south, residential charger cluster)
])
ZONE_SIGMA_DEG = 0.0025          # ~250 m spread around each anchor
GATE_NAMES = ("north", "south", "west")
KM_PER_DEG_LAT = 111.2


class NodeRouter:
    def __init__(self):
        g = json.loads(GRAPH.read_text(encoding="utf-8"))
        ids = list(g["nodes"].keys())
        self.idx = {int(k): i for i, k in enumerate(ids)}
        self.xy = np.array([g["nodes"][k] for k in ids])            # lat, lon
        n = len(ids)
        if CACHE.exists():
            z = np.load(CACHE)
            self.dist, self.pred, keep = z["dist"], z["pred"], z["keep"]
        else:
            rows, cols, w = [], [], []
            for k, (u, v, km, _kmh) in enumerate(g["edges"]):
                if k in LAKE_EDGES:
                    continue
                a, b = self.idx[int(u)], self.idx[int(v)]
                rows += [a, b]
                cols += [b, a]
                w += [km, km]
            m = csr_matrix((w, (rows, cols)), shape=(n, n))
            _, lab = connected_components(m, directed=False)
            keep = lab == np.bincount(lab).argmax()                   # main component only
            self.dist, self.pred = dijkstra(m, directed=False, return_predecessors=True)
            np.savez_compressed(CACHE, dist=self.dist, pred=self.pred, keep=keep)
        self.keep = keep.astype(bool)
        self.main = np.flatnonzero(self.keep)
        self.cos = np.cos(np.radians(self.xy[:, 0].mean()))
        self.tree = cKDTree(np.column_stack([self.xy[self.main, 0], self.xy[self.main, 1] * self.cos]))
        gates = [p for p in g["pois"]["gates"] if p["name"] in GATE_NAMES]
        self.gate_nodes = np.array([self.idx[int(p["node"])] for p in gates])
        self.gate_xy = self.xy[self.gate_nodes]

    # ---- snapping ----
    def snap(self, lat, lon):
        """Nearest main-component node and its distance in km (arrays)."""
        lat, lon = np.broadcast_arrays(np.asarray(lat, float), np.asarray(lon, float))
        d, k = self.tree.query(np.column_stack([lat.ravel(), lon.ravel() * self.cos]))
        return self.main[k].reshape(lat.shape), (d * KM_PER_DEG_LAT).reshape(lat.shape)

    def road(self, lat1, lon1, lat2, lon2, detour):
        b = np.broadcast_arrays(*(np.asarray(a, float) for a in (lat1, lon1, lat2, lon2)))
        shape = b[0].shape
        lat1, lon1, lat2, lon2 = (a.ravel() for a in b)
        n1, s1 = self.snap(lat1, lon1)
        n2, s2 = self.snap(lat2, lon2)
        in1, in2 = s1 <= SNAP_KM, s2 <= SNAP_KM
        out = detour * haversine_km(lat1, lon1, lat2, lon2)            # both outside (or fallback)
        both = in1 & in2
        if both.any():
            d = self.dist[n1[both], n2[both]]
            out[both] = np.where(n1[both] == n2[both], out[both], np.maximum(d, out[both] / detour))
        for inside, n_in, lat_o, lon_o in ((in1 & ~in2, n1, lat2, lon2), (in2 & ~in1, n2, lat1, lon1)):
            if inside.any():   # one end outside the map: through the best gate
                via = (self.dist[n_in[inside][:, None], self.gate_nodes[None, :]]
                       + detour * haversine_km(self.gate_xy[None, :, 0], self.gate_xy[None, :, 1],
                                               lat_o[inside][:, None], lon_o[inside][:, None]))
                out[inside] = via.min(axis=1)
        return out.reshape(shape)

    # ---- paths for the replay ----
    def node_path(self, a, b):
        path = [b]
        while path[-1] != a:
            p = self.pred[a, path[-1]]
            if p < 0:
                return [a, b]
            path.append(p)
        return path[::-1]

    def path(self, lat1, lon1, lat2, lon2):
        """Polyline (lat, lon) of the road route; outside the map a straight line from the gate."""
        (n1, s1), (n2, s2) = self.snap(lat1, lon1), self.snap(lat2, lon2)
        n1, n2, s1, s2 = int(n1), int(n2), float(s1), float(s2)
        start, end = [(lat1, lon1)], [(lat2, lon2)]
        if s1 <= SNAP_KM and s2 <= SNAP_KM:
            mid = [tuple(self.xy[k]) for k in self.node_path(n1, n2)]
        elif s1 <= SNAP_KM:                     # leaving the map
            gk = self.gate_nodes[np.argmin(self.dist[n1, self.gate_nodes]
                                           + haversine_km(self.gate_xy[:, 0], self.gate_xy[:, 1], lat2, lon2))]
            mid = [tuple(self.xy[k]) for k in self.node_path(n1, int(gk))]
        elif s2 <= SNAP_KM:                     # coming back into the map
            gk = self.gate_nodes[np.argmin(self.dist[self.gate_nodes, n2]
                                           + haversine_km(self.gate_xy[:, 0], self.gate_xy[:, 1], lat1, lon1))]
            mid = [tuple(self.xy[k]) for k in self.node_path(int(gk), n2)]
        else:
            mid = []
        return start + mid + end

    def inside(self, lat, lon):
        return bool(self.snap(lat, lon)[1] <= SNAP_KM)


_router = None


def router():
    global _router
    if _router is None:
        _router = NodeRouter()
    return _router


# ---- demand ----
def sample_points(rng, n):
    """Points around the OCP1 anchors, snapped onto the road network."""
    w = ZONES[:, 2] / ZONES[:, 2].sum()
    k = rng.choice(len(ZONES), size=n, p=w)
    lat = ZONES[k, 0] + rng.normal(0, ZONE_SIGMA_DEG, n)
    lon = ZONES[k, 1] + rng.normal(0, ZONE_SIGMA_DEG, n)
    node, _ = router().snap(lat, lon)
    r = router()
    return r.xy[node, 0].copy(), r.xy[node, 1].copy()


def _offset(lat, lon, km, bearing):
    return (lat + km * np.cos(bearing) / KM_PER_DEG_LAT,
            lon + km * np.sin(bearing) / (KM_PER_DEG_LAT * np.cos(np.radians(lat))))


def generate(cfg, rng):
    """1,276 bookings/day by default (cfg.daily_requests) with the Hanoi hourly profile:
    65 % inside OCP1 (lognormal road km, median 1.6, clipped 0.5-3.5), 35 % to Hanoi through a
    gate (median 10 km, clipped 6-16): the destination is placed beyond the gate."""
    from .demand import HOURLY, Request
    n_hours = int(np.ceil(cfg.sim_hours))
    times = []
    for h in range(n_hours):
        k = rng.poisson(cfg.daily_requests * HOURLY[h % 24])
        times.append(h * 3600 + rng.uniform(0, 3600, k))
    times = np.sort(np.concatenate(times))
    times = times[times < cfg.sim_hours * 3600]
    n = len(times)
    r = router()
    o_lat, o_lon = sample_points(rng, n)
    gateway = rng.random(n) < cfg.ocp1_gateway_share
    want = np.where(gateway, np.clip(rng.lognormal(np.log(10.0), 0.35, n), 6.0, 16.0),
                    np.clip(rng.lognormal(np.log(1.6), 0.55, n), 0.5, 3.5))
    d_lat, d_lon = np.empty(n), np.empty(n)
    gates = r.gate_xy
    centre = ZONES[:, :2].mean(axis=0)
    for i in range(n):
        if gateway[i]:
            g = gates[rng.integers(len(gates))]
            out = np.arctan2((g[1] - centre[1]) * np.cos(np.radians(centre[0])), g[0] - centre[0])
            inside_km = r.road(o_lat[i], o_lon[i], g[0], g[1], cfg.detour)
            rest = max(1.0, want[i] - float(inside_km)) / cfg.detour
            d_lat[i], d_lon[i] = _offset(g[0], g[1], rest, out + rng.normal(0, 0.25))
        else:   # pick the zone point whose road distance is closest to the wanted length
            c_lat, c_lon = sample_points(rng, 12)
            km = r.road(o_lat[i], o_lon[i], c_lat, c_lon, cfg.detour)
            j = int(np.argmin(np.abs(km - want[i])))
            d_lat[i], d_lon[i] = c_lat[j], c_lon[j]
    km = r.road(o_lat, o_lon, d_lat, d_lon, cfg.detour)
    km = np.maximum(km, 0.3)
    patience = rng.exponential(cfg.patience_mean_min * 60, n)
    early = np.zeros(n, dtype=bool)
    if cfg.rebook:
        early = rng.random(n) < cfg.p_early_cancel
        patience[early] = np.minimum(patience[early], rng.uniform(30, 180, early.sum()))
    return [Request(i, times[i], o_lat[i], o_lon[i], d_lat[i], d_lon[i], float(km[i]), patience[i],
                    trip_id=i, early=bool(early[i]), airport=False) for i in range(n)]


def load_stations(cfg):
    s = json.loads(STATIONS.read_text(encoding="utf-8"))["stations"]
    latlon = np.array([[x["lat"], x["lon"]] for x in s])
    ports = np.array([x["ports"] for x in s], int)
    kw = np.array([min(x["dc_kw"], cfg.vehicle_max_dc_kw) * cfg.dc_curve_factor for x in s])
    return latlon, ports, kw
