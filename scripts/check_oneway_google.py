"""Cross-check OSM one-way tags in Ocean Park against Google Routes driving distances.

    GOOGLE_MAPS_API_KEY=... .venv/Scripts/python scripts/check_oneway_google.py

For a road with points A (20%) and B (80% along it), ask Google for the driving distance
A->B and B->A. A two-way road gives two short routes (about |AB|); a one-way road gives a
short route one way and a detour the other way.
Dual carriageways (a one-way road with an opposite one-way twin within 50 m) are skipped:
OSM maps each side separately and Google may snap to either side, so the test is ambiguous.
Requires the Routes API to be enabled for the key. Writes data/oneway_check.csv.
"""
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
MIN_LEN_M = 60
TWO_WAY_SAMPLE = 60
DETOUR_RATIO = 1.6     # route longer than this x |AB| means "cannot drive straight this way"
MAX_REQUESTS = 800


def polyline_len(p):
    p = np.asarray(p)
    return float(np.hypot(*np.diff(p, axis=0).T).sum())


def point_at(p, d):
    p = np.asarray(p)
    seg = np.hypot(*np.diff(p, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    i = min(np.searchsorted(cum, d, side="right") - 1, len(seg) - 1)
    t = (d - cum[i]) / seg[i] if seg[i] > 0 else 0
    return p[i] + t * (p[i + 1] - p[i])


def direction(p):
    v = np.asarray(p[-1]) - np.asarray(p[0])
    return v / (np.linalg.norm(v) or 1)


def main():
    key = os.environ.get("GOOGLE_MAPS_API_KEY") or sys.exit("set GOOGLE_MAPS_API_KEY")
    data = json.loads((ROOT / "web/public/data/oceanpark.json").read_text(encoding="utf-8"))
    ox0, oy0 = data["meta"]["origin"]
    to_ll = Transformer.from_crs(data["meta"]["crs"], "EPSG:4326", always_xy=True)
    roads = [dict(r, i=i, len=polyline_len(r["pts"])) for i, r in enumerate(data["roads"])]
    roads = [r for r in roads if r["len"] >= MIN_LEN_M]

    oneway = [r for r in roads if r["oneway"]]
    mids = {r["i"]: point_at(r["pts"], r["len"] / 2) for r in oneway}
    def has_twin(r):
        return any(o["i"] != r["i"] and np.linalg.norm(mids[o["i"]] - mids[r["i"]]) < 50
                   and direction(o["pts"]) @ direction(r["pts"]) < -0.7 for o in oneway)
    single_oneway = [r for r in oneway if not has_twin(r)]
    random.seed(0)
    two_way = random.sample([r for r in roads if not r["oneway"]], TWO_WAY_SAMPLE)
    tests = single_oneway + two_way
    print(f"one-way roads >= {MIN_LEN_M} m: {len(oneway)} ({len(oneway) - len(single_oneway)} dual-carriageway "
          f"sides skipped); testing {len(single_oneway)} single one-way + {len(two_way)} two-way "
          f"= {2 * len(tests)} requests")

    n_req = 0
    def route(a, b):
        nonlocal n_req
        if n_req >= MAX_REQUESTS:
            raise RuntimeError("request cap reached")
        (alon, alat), (blon, blat) = to_ll.transform(a[0] + ox0, a[1] + oy0), to_ll.transform(b[0] + ox0, b[1] + oy0)
        body = {"origin": {"location": {"latLng": {"latitude": alat, "longitude": alon}}},
                "destination": {"location": {"latLng": {"latitude": blat, "longitude": blon}}},
                "travelMode": "DRIVE"}
        r = requests.post(URL, json=body, timeout=30, headers={
            "X-Goog-Api-Key": key, "X-Goog-FieldMask": "routes.distanceMeters"})
        n_req += 1
        r.raise_for_status()
        routes = r.json().get("routes", [])
        time.sleep(0.05)
        return routes[0].get("distanceMeters", 0) if routes else None

    rows = []
    for r in tests:
        a, b = point_at(r["pts"], 0.2 * r["len"]), point_at(r["pts"], 0.8 * r["len"])
        ab = float(np.linalg.norm(b - a))
        fwd, back = route(a, b), route(b, a)
        f_ok = fwd is not None and fwd <= DETOUR_RATIO * ab
        b_ok = back is not None and back <= DETOUR_RATIO * ab
        google = "two-way" if f_ok and b_ok else "one-way" if f_ok != b_ok else "unclear"
        rows.append({"road": r["i"], "name": r["name"], "cls": r["cls"], "len_m": round(r["len"]),
                     "osm": "one-way" if r["oneway"] else "two-way", "ab_m": round(ab),
                     "google_ab_m": fwd, "google_ba_m": back, "google": google,
                     "agree": google == ("one-way" if r["oneway"] else "two-way")})

    df = pd.DataFrame(rows)
    out = ROOT / "data" / "oneway_check.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"{n_req} requests; saved {out}")
    print(pd.crosstab(df.osm, df.google, margins=True))


if __name__ == "__main__":
    main()
