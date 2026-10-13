"""Fetch EV charging stations in Hanoi from Google Places API (New) Text Search.

    GOOGLE_MAPS_API_KEY=... .venv/Scripts/python scripts/fetch_google_stations.py

The API returns at most 60 results (3 pages) per query, so the Hanoi bounding box is split
into tiles; any tile that comes back full is split into four and searched again. A hard
request cap keeps the run inside the free monthly quota.

Outputs
  data/google_places_raw.jsonl  one JSON place per line (deduplicated by place id)
  data/stations_google.csv      one row per station, connector counts and power flattened
"""
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.location",
    "places.businessStatus", "places.evChargeOptions", "nextPageToken",
])
QUERY = "trạm sạc xe điện"
# Hanoi city (all districts)
SOUTH, NORTH, WEST, EAST = 20.56, 21.39, 105.28, 106.02
START_SPLIT = 4          # initial grid START_SPLIT x START_SPLIT
MIN_TILE_DEG = 0.01      # do not split below ~1 km
MAX_REQUESTS = 400
SATURATED = 50           # split tiles returning at least this many places
DATA = Path(__file__).resolve().parent.parent / "data"


class Client:
    def __init__(self, key):
        self.key = key
        self.requests = 0

    def search(self, south, west, north, east):
        """All pages for one tile. Returns (places, saturated)."""
        places, token = [], None
        for _ in range(3):
            if self.requests >= MAX_REQUESTS:
                raise RuntimeError("request cap reached")
            body = {
                "textQuery": QUERY,
                "includedType": "electric_vehicle_charging_station",
                "strictTypeFiltering": True,
                "languageCode": "vi",
                "pageSize": 20,
                "locationRestriction": {"rectangle": {
                    "low": {"latitude": south, "longitude": west},
                    "high": {"latitude": north, "longitude": east}}},
            }
            if token:
                body["pageToken"] = token
            r = requests.post(URL, json=body, timeout=30, headers={
                "X-Goog-Api-Key": self.key, "X-Goog-FieldMask": FIELDS})
            self.requests += 1
            r.raise_for_status()
            data = r.json()
            places += data.get("places", [])
            token = data.get("nextPageToken")
            if not token:
                break
            time.sleep(1.0)  # page tokens need a moment to become valid
        # the API stops at 60 results; a tile near that cap may be hiding more
        return places, len(places) >= SATURATED


def crawl(client):
    found = {}
    dlat, dlon = (NORTH - SOUTH) / START_SPLIT, (EAST - WEST) / START_SPLIT
    tiles = [(SOUTH + i * dlat, WEST + j * dlon, SOUTH + (i + 1) * dlat, WEST + (j + 1) * dlon)
             for i in range(START_SPLIT) for j in range(START_SPLIT)]
    while tiles:
        s, w, n, e = tiles.pop()
        try:
            places, saturated = client.search(s, w, n, e)
        except RuntimeError:
            print(f"stopped at request cap; {len(tiles) + 1} tiles not searched", file=sys.stderr)
            break
        for p in places:
            found[p["id"]] = p
        print(f"[{client.requests:3d} req] tile {s:.3f},{w:.3f} -> {len(places):2d} places"
              f"{' (split)' if saturated else ''}; total {len(found)}")
        if saturated and (n - s) > MIN_TILE_DEG:
            ml, mo = (s + n) / 2, (w + e) / 2
            tiles += [(s, w, ml, mo), (s, mo, ml, e), (ml, w, n, mo), (ml, mo, n, e)]
    return found


def flatten(p):
    ev = p.get("evChargeOptions", {})
    aggs = ev.get("connectorAggregation", [])
    name = p.get("displayName", {}).get("text", "")
    types = {a.get("type", "") for a in aggs}
    car_types = {"EV_CONNECTOR_TYPE_CCS_COMBO_2", "EV_CONNECTOR_TYPE_TYPE_2",
                 "EV_CONNECTOR_TYPE_CCS_COMBO_1", "EV_CONNECTOR_TYPE_CHADEMO",
                 "EV_CONNECTOR_TYPE_J1772", "EV_CONNECTOR_TYPE_GB_T", "EV_CONNECTOR_TYPE_TESLA"}
    lname = name.lower()
    scooter_name = any(k in lname for k in ("xe máy", "xe may", "scooter", "motorbike"))
    return {
        "place_id": p["id"],
        "name": name,
        "address": p.get("formattedAddress", ""),
        "lat": p["location"]["latitude"],
        "lon": p["location"]["longitude"],
        "business_status": p.get("businessStatus", ""),
        "is_vinfast": any(k in lname for k in ("vinfast", "v-green", "vgreen")),
        # car station if it has a car connector, or no connector info and a non-scooter name
        "for_cars": bool(types & car_types) or (not aggs and not scooter_name),
        "has_connector_info": bool(aggs),
        "ports": ev.get("connectorCount"),
        "dc_ports": sum(a.get("count", 0) for a in aggs
                        if a.get("type") in ("EV_CONNECTOR_TYPE_CCS_COMBO_2", "EV_CONNECTOR_TYPE_CCS_COMBO_1",
                                             "EV_CONNECTOR_TYPE_CHADEMO", "EV_CONNECTOR_TYPE_GB_T")) or None,
        "max_kw": max((a.get("maxChargeRateKw", 0) for a in aggs), default=None) or None,
        "connectors": ";".join(f"{a.get('type', '').replace('EV_CONNECTOR_TYPE_', '')}"
                               f"x{a.get('count', 0)}@{a.get('maxChargeRateKw', '?')}kW" for a in aggs),
    }


def main():
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        sys.exit("set GOOGLE_MAPS_API_KEY")
    client = Client(key)
    found = crawl(client)
    DATA.mkdir(exist_ok=True)
    with open(DATA / "google_places_raw.jsonl", "w", encoding="utf-8") as f:
        for p in found.values():
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    df = pd.DataFrame([flatten(p) for p in found.values()])
    df.to_csv(DATA / "stations_google.csv", index=False, encoding="utf-8-sig")
    print(f"\n{client.requests} requests, {len(df)} stations "
          f"({df.is_vinfast.sum()} VinFast/V-Green, {df.for_cars.sum()} for cars, "
          f"{df.has_connector_info.sum()} with connector info)")


if __name__ == "__main__":
    main()
