"""Build offline OSM data for the simulator (run once, needs internet):

    .venv/Scripts/python scripts/build_osm_data.py

Outputs
  data/road_cells.npz   shortest-path road km between ~1.1 km grid cells (drive network)
  data/stations_osm.csv OSM charging stations usable by cars (lat, lon, ports, name, operator)
"""
from pathlib import Path

import numpy as np
import osmnx as ox
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

# inner Hanoi plus the corridor to Noi Bai airport
SOUTH, NORTH, WEST, EAST = 20.95, 21.24, 105.74, 105.93
STEP = 0.01  # degrees, ~1.1 km
DATA = Path(__file__).resolve().parent.parent / "data"


def build_road_cells():
    print("downloading drive network ...")
    g = ox.graph_from_bbox((WEST, SOUTH, EAST, NORTH), network_type="drive", simplify=True)
    g = ox.truncate.largest_component(g, strongly=True)
    nodes, edges = ox.graph_to_gdfs(g)
    print(f"  {len(nodes)} nodes, {len(edges)} edges")

    idx = {n: i for i, n in enumerate(nodes.index)}
    e = edges.reset_index()
    u = e["u"].map(idx).to_numpy()
    v = e["v"].map(idx).to_numpy()
    w = e["length"].to_numpy() / 1000.0
    # keep the shortest of parallel edges
    order = np.lexsort((w, v, u))
    u, v, w = u[order], v[order], w[order]
    first = np.ones(len(u), bool)
    first[1:] = (u[1:] != u[:-1]) | (v[1:] != v[:-1])
    adj = csr_matrix((w[first], (u[first], v[first])), shape=(len(nodes), len(nodes)))

    rows = int(np.ceil((NORTH - SOUTH) / STEP))
    cols = int(np.ceil((EAST - WEST) / STEP))
    lat = nodes["y"].to_numpy()
    lon = nodes["x"].to_numpy()
    r = np.floor((lat - SOUTH) / STEP).astype(int)
    c = np.floor((lon - WEST) / STEP).astype(int)
    grid = -np.ones((rows, cols), dtype=np.int32)
    reps = []
    for rr in range(rows):
        for cc in range(cols):
            members = np.where((r == rr) & (c == cc))[0]
            if len(members) == 0:
                continue
            clat, clon = SOUTH + (rr + 0.5) * STEP, WEST + (cc + 0.5) * STEP
            k = members[np.argmin((lat[members] - clat) ** 2 + (lon[members] - clon) ** 2)]
            grid[rr, cc] = len(reps)
            reps.append(k)
    print(f"  {len(reps)} grid cells with road nodes; running Dijkstra ...")
    dist = dijkstra(adj, directed=True, indices=np.array(reps))[:, reps].astype(np.float32)
    DATA.mkdir(exist_ok=True)
    np.savez_compressed(DATA / "road_cells.npz", lat0=SOUTH, lon0=WEST, step=STEP, grid=grid, dist_km=dist)
    finite = np.isfinite(dist).mean()
    print(f"  saved road_cells.npz ({dist.shape[0]} cells, {finite:.1%} reachable pairs)")


def build_stations():
    print("downloading charging stations ...")
    f = ox.features_from_bbox((WEST, SOUTH, EAST, NORTH), tags={"amenity": "charging_station"})
    f = f.to_crs(3857)
    pts = f.geometry.centroid.to_crs(4326)
    df = pd.DataFrame({"lat": pts.y.to_numpy(), "lon": pts.x.to_numpy()})
    for col in ("name", "operator", "brand", "capacity", "motorcar", "motorcycle", "bicycle",
                "socket:type2", "socket:type2_combo", "socket:ccs", "socket:chademo"):
        df[col] = f[col].to_numpy() if col in f else None
    df.to_csv(DATA / "stations_osm_raw.csv", index=False)

    # drop stations explicitly tagged as not for cars, or only for two-wheelers
    # (many VinFast scooter chargers are only marked by name, e.g. "VinFast (xe máy điện)")
    not_car = ((df.motorcar == "no")
               | (((df.motorcycle == "yes") | (df.bicycle == "yes")) & (df.motorcar != "yes"))
               | df.name.fillna("").str.contains("xe máy|xe may|scooter|motorbike", case=False))
    cars = df[~not_car].copy()
    cars["ports"] = pd.to_numeric(cars.capacity, errors="coerce")
    cars[["lat", "lon", "ports", "name", "operator", "brand"]].to_csv(DATA / "stations_osm.csv", index=False)
    print(f"  {len(df)} charging stations in OSM, {len(cars)} kept for cars "
          f"({cars.ports.notna().sum()} with a capacity tag)")


if __name__ == "__main__":
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(DATA / "osm_cache")
    build_stations()
    build_road_cells()
