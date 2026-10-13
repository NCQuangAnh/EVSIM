"""Draw an OSM map of one area: roads, buildings, named residential sub-zones, EV charging
stations (Google Places and OSM) and labelled landmarks.

    .venv/Scripts/python scripts/plot_area_map.py "Vinhomes Ocean Park, Gia Lâm, Hà Nội" ocean_park1 \
        "(?:Trường Đại học VinUni|Ký túc xá VinUni|Vincom Mega Mall Ocean Park)$"

The optional third argument is a regex matched against the start of OSM place names (case
insensitive); matching places get a star label with a shortened name.
Google stations come from data/stations_google.csv (scripts/fetch_google_stations.py).
Output: outputs/maps/<name>.png
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import osmnx as ox
import pandas as pd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent.parent
MARGIN_DEG = 0.004  # ~400 m of context around the area boundary
SCOOTER = r"xe máy|xe may|scooter|motorbike"
SHORT = [("Trường Trung học phổ thông", "THPT"), ("Trường Trung học cơ sở", "THCS"),
         ("Trường Tiểu học", "Tiểu học"), ("Trường Mầm non", "Mầm non"), ("Trường Đại học", "ĐH"),
         ("Ký túc xá", "KTX"), ("Sân vận động", "SVĐ"), (" Ocean Park", ""), (" Vinhomes", "")]


def short(name):
    for long, abbr in SHORT:
        name = name.replace(long, abbr)
    return name


def centroids(gdf):
    """Centroids computed in metres (Web Mercator) and returned in lon/lat."""
    return gdf.geometry.to_crs(3857).centroid.to_crs(4326)


def label(ax, x, y, text, color, offset=(7, -10), size=7.5, weight="bold", style="normal"):
    ax.annotate(text, (x, y), xytext=offset, textcoords="offset points", fontsize=size,
                fontweight=weight, fontstyle=style, color=color, zorder=8,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))


def main(query, name, label_regex=None):
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(ROOT / "data" / "osm_cache")

    area = ox.geocode_to_gdf(query)
    boundary = area.geometry.iloc[0]
    west, south, east, north = area.total_bounds
    bbox = (west - MARGIN_DEG, south - MARGIN_DEG, east + MARGIN_DEG, north + MARGIN_DEG)

    roads = ox.graph_from_bbox(bbox, network_type="drive")
    buildings = ox.features_from_bbox(bbox, tags={"building": True})
    buildings = buildings[buildings.geom_type.isin(["Polygon", "MultiPolygon"])]
    named = ox.features_from_bbox(bbox, tags={"name": True})
    named = named[~named["name"].astype(str).str.contains("Đối diện", case=False, na=False)]

    fig, ax = plt.subplots(figsize=(12, 10), dpi=150)
    fig.patch.set_facecolor("white")
    buildings.plot(ax=ax, color="#d9d4cc", linewidth=0)

    # named residential sub-zones inside the area (Sapphire, Zenpark, ...)
    zones = named[(named.get("landuse") == "residential") & named.geom_type.isin(["Polygon", "MultiPolygon"])]
    area_m2 = area.to_crs(3857).geometry.iloc[0].area
    zones = zones[centroids(zones).within(boundary) & (zones.to_crs(3857).area < area_m2 * 0.5)]
    if len(zones):
        zones.boundary.plot(ax=ax, color="#8d6e63", linewidth=0.8, linestyle=":")
        for (_, z), c in zip(zones.iterrows(), centroids(zones)):
            label(ax, c.x, c.y, short(z["name"].replace(" Vinhomes Ocean Park", "")), "#6d4c41",
                  offset=(-20, 6), size=7, weight="normal", style="italic")

    area.boundary.plot(ax=ax, color="#2e7d32", linewidth=2, linestyle="--")
    ox.plot_graph(roads, ax=ax, node_size=0, edge_color="#6b6b6b", edge_linewidth=0.6,
                  bgcolor="white", show=False, close=False)

    # charging stations: Google Places (used by the simulator) and OSM (for comparison)
    st = pd.read_csv(ROOT / "data" / "stations_google.csv")
    st = st[st.lat.between(bbox[1], bbox[3]) & st.lon.between(bbox[0], bbox[2]) & st.for_cars.astype(bool)]
    ax.scatter(st.lon, st.lat, s=60, c="#1565c0", edgecolors="white", linewidths=0.8, zorder=5,
               label=f"Trạm sạc ô tô – Google Places: {len(st)} (số = cổng ước lượng)")
    for _, r in st.iterrows():
        if pd.notna(r.get("ports_est")):
            ax.annotate(str(int(r.ports_est)), (r.lon, r.lat), xytext=(4, 4), textcoords="offset points",
                        fontsize=6, color="#1565c0", zorder=6)
    osm_st = named[(named.get("amenity") == "charging_station")]
    osm_st = osm_st.assign(geometry=centroids(osm_st))
    scooter = osm_st["name"].astype(str).str.contains(SCOOTER, case=False, na=False)
    ax.scatter(osm_st[~scooter].geometry.x, osm_st[~scooter].geometry.y, s=28, marker="s",
               facecolors="none", edgecolors="#00838f", linewidths=1.2, zorder=5,
               label=f"Trạm sạc ô tô – OSM: {int((~scooter).sum())}")
    ax.scatter(osm_st[scooter].geometry.x, osm_st[scooter].geometry.y, s=10, c="#9e9e9e", zorder=4,
               label=f"Trạm sạc xe máy – OSM: {int(scooter.sum())}")

    # landmarks
    if label_regex:
        lm = named[named["name"].astype(str).str.match(label_regex, case=False, na=False)]
        lm = lm.assign(_poly=lm.geom_type.ne("Point"), _key=lm["name"].str.lower(), _c=centroids(lm))
        lm = lm.sort_values("_poly", ascending=False).drop_duplicates("_key")
        placed = []
        for _, r in lm.iterrows():
            c = r["_c"]
            # the same place is often mapped twice (building + point): one label per ~50 m
            if any(abs(c.x - x) < 0.0005 and abs(c.y - y) < 0.0005 for x, y in placed):
                continue
            placed.append((c.x, c.y))
            ax.scatter(c.x, c.y, marker="*", s=200, c="#c62828", edgecolors="white", zorder=7)
            label(ax, c.x, c.y, short(r["name"]), "#c62828")

    ax.plot([], [], color="#2e7d32", linestyle="--", label="Ranh giới khu (OSM)")
    ax.plot([], [], color="#8d6e63", linestyle=":", label="Phân khu (OSM)")
    ax.scatter([], [], marker="*", s=120, c="#c62828", label="Địa điểm")
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])
    ax.set_title(f"{query}\nĐường bộ, toà nhà, địa điểm: © OpenStreetMap contributors · "
                 f"trạm sạc: Google Places và OpenStreetMap", fontsize=9)
    ax.legend(loc="lower left", fontsize=7.5, frameon=True)
    ax.set_axis_off()

    out = ROOT / "outputs" / "maps" / f"{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    inside = sum(boundary.contains(Point(x, y)) for x, y in zip(st.lon, st.lat))
    print(f"saved {out}")
    print(f"{len(roads.nodes)} road nodes, {len(buildings)} buildings, {len(zones)} sub-zones; "
          f"Google car stations {len(st)} ({inside} inside), OSM car {int((~scooter).sum())}, "
          f"OSM scooter {int(scooter.sum())}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
