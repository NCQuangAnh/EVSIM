"""Export map data for the Ocean Park 1 web UI (run once, needs internet the first time):

    .venv/Scripts/python scripts/build_oceanpark_map.py

Writes web/public/data/oceanpark.json with everything in local metres (UTM 48N, origin at
the south-west corner of the view, y pointing north):
  roads      drawable road segments (one per two-way road) with class, lanes, oneway
  nodes/edges directed road graph for routing and car movement
  vin        Vin buildings (footprints) with a category, plus landmark labels
  blocks     every other building as a plain block (no labels)
  green/water parks, grass, pitches and lakes (drawn plainly)
  stations   car charging stations, OSM + Google merged
  signals    traffic lights: OSM traffic_signals plus assumed ones at major junctions
  boundary   Ocean Park 1 outline
Sources: © OpenStreetMap contributors (ODbL); stations also from Google Places
(data/stations_google.csv).
"""
import json
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import MultiPolygon, Point, Polygon

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public" / "data" / "oceanpark.json"
AREA_QUERY = "Vinhomes Ocean Park, Gia Lâm, Hà Nội"
MARGIN_DEG = 0.004
CRS = 32648  # UTM zone 48N, metres

# default total lanes when OSM has no lanes tag
DEFAULT_LANES = {"motorway": 6, "trunk": 6, "primary": 4, "secondary": 4, "tertiary": 2,
                 "unclassified": 2, "residential": 2, "living_street": 1, "service": 1}
VIN_TYPES = {"apartments", "university", "school", "dormitory", "kindergarten", "commercial",
             "retail", "office", "industrial", "hospital", "construction", "yes"}
MIN_AREA_M2 = 300
MIN_BLOCK_M2 = 15  # smaller footprints are mapping noise
# assumed traffic lights: junction of two roads whose class ranks add up to at least this
CLASS_RANK = {"trunk": 3, "primary": 3, "secondary": 2, "tertiary": 1}
SIGNAL_MIN_RANK = 4
SIGNAL_CLUSTER_M = 45  # junction nodes this close share one controller (dual carriageways)
SIGNAL_SNAP_M = 60     # OSM often puts the signal on the approach, ~30-40 m before the junction
# assumed lights the user removed after reviewing the map (2026-10-03): the main boulevard
# from the Masteri Waterfront area to the roundabout, and the junction north-east of it
SIGNALS_REMOVED = [  # (lat, lon) of the controller centre
    (20.999859, 105.953922),
    (20.998386, 105.951597),
    (20.998005, 105.951238),
    (20.997489, 105.950713),
    (20.997063, 105.949683),
    (20.996186, 105.948617),
    (20.994676, 105.946500),
    (20.994098, 105.945925),
    (20.993473, 105.945807),
    (20.993050, 105.945237),
]
SIGNAL_REMOVE_RADIUS_M = 25
# category of a Vin building, decided by its own name or the name of the area it sits in
CATEGORIES = [
    ("edu", r"vinuni|vinschool|ký túc xá|ktx|đại học|trường"),
    ("mall", r"vincom|mega mall"),
    ("office", r"technopark"),
    ("hospital", r"vinmec"),
    ("depot", r"vinbus"),
    ("residential", r"sapphire|masteri|zenpark|pavilion|ruby|ocean view|san hô|vinhomes"),
]
LANDMARKS = (r"(?:Trường Đại học VinUni|Ký túc xá VinUni|Sân vận động VinUni|Vincom Mega Mall Ocean Park|"
             r"Tòa Technopark|Tòa Ruby|VinBus Depot|Vinmec Hospital|Trường Trung học cơ sở Vinschool|"
             r"Trường Tiểu học Vinschool|Trường Mầm non Vinschool|"
             r"Trường Trung học phổ thông Vinschool Ocean Park)$")
SHORT = [("Trường Trung học phổ thông", "THPT"), ("Trường Trung học cơ sở", "THCS"),
         ("Trường Tiểu học", "Tiểu học"), ("Trường Mầm non", "Mầm non"), ("Trường Đại học", "ĐH"),
         ("Ký túc xá", "KTX"), ("Sân vận động", "SVĐ"), (" Ocean Park", ""), (" Vinhomes", "")]


def short(name):
    for long, abbr in SHORT:
        name = name.replace(long, abbr)
    return name


def first(v):
    return v[0] if isinstance(v, list) else v


def lanes_of(row):
    raw = first(row.get("lanes"))
    try:
        return max(1, int(float(str(raw).split(";")[0])))
    except (TypeError, ValueError):
        hw = str(first(row["highway"])).replace("_link", "")
        return DEFAULT_LANES.get(hw, 2) if "_link" not in str(first(row["highway"])) else 1


def main():
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(ROOT / "data" / "osm_cache")
    area = ox.geocode_to_gdf(AREA_QUERY)
    w, s, e, n = area.total_bounds
    bbox = (w - MARGIN_DEG, s - MARGIN_DEG, e + MARGIN_DEG, n + MARGIN_DEG)

    area_m = area.to_crs(CRS)
    corners = gpd.GeoSeries([Point(bbox[0], bbox[1]), Point(bbox[2], bbox[3])], crs=4326).to_crs(CRS)
    (ox0, oy0), (ox1, oy1) = corners.iloc[0].coords[0], corners.iloc[1].coords[0]

    def xy(coords):
        return [[round(x - ox0, 1), round(y - oy0, 1)] for x, y in coords]

    def rings(geom):
        polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
        return [xy(p.exterior.coords) for p in polys if isinstance(p, Polygon)]

    # --- roads ---
    g = ox.graph_from_bbox(bbox, network_type="drive", simplify=True)
    g = ox.truncate.largest_component(g, strongly=True)
    g = ox.project_graph(g, to_crs=CRS)
    nodes, edges = ox.graph_to_gdfs(g)
    node_ids = {nid: i for i, nid in enumerate(nodes.index)}
    out_nodes = [[round(r.x - ox0, 1), round(r.y - oy0, 1)] for r in nodes.itertuples()]

    roads, seg_of, out_edges = [], {}, []
    for (u, v, k), r in edges.iterrows():
        key = (min(u, v), max(u, v), round(r["length"], 1))
        geom = r["geometry"]
        if key not in seg_of:
            hw = str(first(r["highway"]))
            seg_of[key] = len(roads)
            roads.append({"pts": xy(geom.coords), "cls": hw.replace("_link", ""), "link": "_link" in hw,
                          "lanes": lanes_of(r), "oneway": bool(r.get("oneway", False)),
                          "rb": str(first(r.get("junction"))) in ("roundabout", "circular"),
                          "name": str(first(r.get("name"))) if isinstance(first(r.get("name")), str) else ""})
            forward = True
        else:
            # same physical road in the other direction: its geometry runs backwards
            seg_pts = roads[seg_of[key]]["pts"]
            forward = abs(seg_pts[0][0] - (geom.coords[0][0] - ox0)) < 0.5 and \
                abs(seg_pts[0][1] - (geom.coords[0][1] - oy0)) < 0.5
        out_edges.append([node_ids[u], node_ids[v], seg_of[key], int(forward), round(float(r["length"]), 1)])

    # --- Vin buildings, landmarks ---
    named = ox.features_from_bbox(bbox, tags={"name": True}).to_crs(CRS)
    named = named[~named["name"].astype(str).str.contains("Đối diện", case=False, na=False)]
    blds = ox.features_from_bbox(bbox, tags={"building": True}).to_crs(CRS)
    blds = blds[blds.geom_type.isin(["Polygon", "MultiPolygon"])]
    boundary = area_m.geometry.iloc[0]
    named_areas = named[named.geom_type.isin(["Polygon", "MultiPolygon"])]

    def category(text):
        t = text.lower()
        for cat, pat in CATEGORIES:
            if re.search(pat, t):
                return cat
        return None

    vin, blocks = [], []
    for _, b in blds.iterrows():
        c = b.geometry.centroid
        own = str(b.get("name")) if isinstance(b.get("name"), str) else ""
        btype = str(b.get("building"))
        if not boundary.contains(c) or b.geometry.area < MIN_AREA_M2 or (btype not in VIN_TYPES and not own):
            if b.geometry.area >= MIN_BLOCK_M2:
                blocks.append({"rings": rings(b.geometry), "kind": btype})
            continue
        host = named_areas[named_areas.contains(c) & (named_areas.area < boundary.area * 0.5)]
        host_name = " ".join(host["name"].astype(str)) if len(host) else ""
        cat = category(own) or category(host_name) or {
            "university": "edu", "school": "edu", "dormitory": "edu", "kindergarten": "edu",
            "commercial": "mall", "retail": "mall", "office": "office", "industrial": "depot",
            "hospital": "hospital"}.get(btype, "residential")
        if btype == "construction":
            cat = "construction"
        vin.append({"rings": rings(b.geometry), "cat": cat, "name": short(own)})

    labels = []
    lm = named[named["name"].astype(str).str.match(LANDMARKS, case=False, na=False)]
    lm = lm.assign(_poly=lm.geom_type.ne("Point"), _key=lm["name"].str.lower())
    for _, r in lm.sort_values("_poly", ascending=False).drop_duplicates("_key").iterrows():
        c = r.geometry.representative_point() if r["_poly"] else r.geometry
        labels.append({"name": short(r["name"]), "at": xy([c.coords[0]])[0],
                       "cat": category(r["name"]) or "office"})
    zones = named_areas[(named_areas.get("landuse") == "residential")
                        & named_areas.centroid.within(boundary) & (named_areas.area < boundary.area * 0.5)]
    zone_out = [{"name": short(z["name"].replace(" Vinhomes Ocean Park", "")),
                 "at": xy([z.geometry.representative_point().coords[0]])[0]} for _, z in zones.iterrows()]

    # --- green and water ---
    gw = ox.features_from_bbox(bbox, tags={"leisure": ["park", "garden", "pitch", "playground"],
                                           "landuse": ["grass", "recreation_ground", "park"],
                                           "natural": ["water"], "water": True}).to_crs(CRS)
    gw = gw[gw.geom_type.isin(["Polygon", "MultiPolygon"])]
    is_water = (gw.get("natural") == "water") | gw.get("water", pd.Series(index=gw.index)).notna()
    green = [{"rings": rings(r.geometry), "kind": str(first(r.get("leisure"))) if isinstance(first(r.get("leisure")), str) else "grass"}
             for _, r in gw[~is_water].iterrows()]
    water = [{"rings": rings(r.geometry)} for _, r in gw[is_water].iterrows()]

    # --- charging stations: OSM car stations + Google, merged within 30 m ---
    osm_st = named[named.get("amenity") == "charging_station"]
    osm_st = osm_st[~osm_st["name"].astype(str).str.contains("xe máy|xe may|scooter", case=False, na=False)]
    pts = [(p.centroid.x, p.centroid.y, "osm", None) for p in osm_st.geometry]
    gs = pd.read_csv(ROOT / "data" / "stations_google.csv")
    gs = gs[gs.for_cars.astype(bool) & gs.lat.between(bbox[1], bbox[3]) & gs.lon.between(bbox[0], bbox[2])]
    gpts = gpd.GeoSeries([Point(x, y) for x, y in zip(gs.lon, gs.lat)], crs=4326).to_crs(CRS)
    for p, ports in zip(gpts, gs.get("ports_est", pd.Series([None] * len(gs)))):
        if all(np.hypot(p.x - x, p.y - y) > 30 for x, y, _, _ in pts):
            pts.append((p.x, p.y, "google", int(ports) if pd.notna(ports) else None))
        else:
            pts = [(x, y, "osm+google" if np.hypot(p.x - x, p.y - y) <= 30 else src, pr)
                   for x, y, src, pr in pts]
    stations = [{"at": [round(x - ox0, 1), round(y - oy0, 1)], "src": src, "ports": pr} for x, y, src, pr in pts]

    # --- traffic lights ---
    sig = ox.features_from_bbox(bbox, tags={"highway": "traffic_signals"}).to_crs(CRS)
    sig = sig[sig.geom_type == "Point"]
    xy_nodes = np.array([[r.x, r.y] for r in nodes.itertuples()])
    osm_nodes = set()
    for p in sig.geometry:
        d = np.hypot(xy_nodes[:, 0] - p.x, xy_nodes[:, 1] - p.y)
        if d.min() < SIGNAL_SNAP_M:
            osm_nodes.add(int(d.argmin()))
    touching = [[] for _ in out_nodes]  # roads at each node
    for u, v, seg, _, _ in out_edges:
        for nd in (u, v):
            if seg not in touching[nd]:
                touching[nd].append(seg)
    assumed = set()
    for nd, segs in enumerate(touching):
        if len(segs) < 3 or any(roads[s]["rb"] for s in segs):
            continue
        # both sides of a dual carriageway are one road axis: group by street name
        axes = {}
        for sg in segs:
            if roads[sg]["link"]:
                continue
            axis = roads[sg]["name"] or f"#{sg}"
            axes[axis] = max(axes.get(axis, 0), CLASS_RANK.get(roads[sg]["cls"], 0))
        ranks = sorted(axes.values(), reverse=True)
        if len(ranks) >= 2 and ranks[0] + ranks[1] >= SIGNAL_MIN_RANK and ranks[1] >= 1:
            assumed.add(nd)
    # group nearby junction nodes into one controller
    signals, used = [], set()
    for nd in sorted(osm_nodes | assumed):
        if nd in used:
            continue
        group, todo = set(), [nd]
        while todo:
            a = todo.pop()
            if a in group:
                continue
            group.add(a)
            todo += [b for b in (osm_nodes | assumed) if b not in group
                     and np.hypot(*(xy_nodes[a] - xy_nodes[b])) < SIGNAL_CLUSTER_M]
        used |= group
        c = xy_nodes[sorted(group)].mean(axis=0)
        signals.append({"nodes": sorted(group), "at": [round(c[0] - ox0, 1), round(c[1] - oy0, 1)],
                        "src": "osm" if group & osm_nodes else "assumed"})

    removed = gpd.GeoSeries([Point(lon, lat) for lat, lon in SIGNALS_REMOVED], crs=4326).to_crs(CRS)
    rm_xy = np.array([[p.x - ox0, p.y - oy0] for p in removed])
    n_before = len(signals)
    signals = [sg for sg in signals
               if np.hypot(rm_xy[:, 0] - sg["at"][0], rm_xy[:, 1] - sg["at"][1]).min() > SIGNAL_REMOVE_RADIUS_M]
    print(f"traffic lights removed by review: {n_before - len(signals)}")

    data = {
        "meta": {"name": "Vinhomes Ocean Park 1", "crs": f"EPSG:{CRS}", "origin": [ox0, oy0],
                 "size": [round(ox1 - ox0, 1), round(oy1 - oy0, 1)],
                 "attribution": "© OpenStreetMap contributors (ODbL) · trạm sạc: OSM + Google Places"},
        "boundary": rings(boundary),
        "roads": roads, "nodes": out_nodes, "edges": out_edges,
        "vin": vin, "blocks": blocks, "labels": labels, "zones": zone_out,
        "green": green, "water": water, "stations": stations, "signals": signals,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    cats = pd.Series([v["cat"] for v in vin]).value_counts().to_dict()
    print(f"saved {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
    print(f"view {data['meta']['size']} m; roads {len(roads)}, nodes {len(out_nodes)}, edges {len(out_edges)}; "
          f"vin buildings {len(vin)} {cats}; other blocks {len(blocks)}; labels {len(labels)}, zones {len(zone_out)}; "
          f"green {len(green)}, water {len(water)}; stations {len(stations)}; "
          f"signals {len(signals)} ({sum(s['src'] == 'osm' for s in signals)} from OSM)")


if __name__ == "__main__":
    main()
