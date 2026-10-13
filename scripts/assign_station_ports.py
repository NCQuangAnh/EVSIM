"""Estimate charging ports for Google stations that have no connector data.

    .venv/Scripts/python scripts/assign_station_ports.py

Stations with a Google connector count keep it. Others get a port count drawn from the range
of their class (guidance on VinFast/V-Green station sizes in Hanoi; assumptions):
  hub       bus station / public car park / depot         20-40 ports
  standard  shopping mall / apartment basement / tower     8-16 ports
  small     petrol station / office building               2-6 ports
  zone      class unknown: inside Ring Road 3 6-8, outside 15-25 ports
Ring Road 3 is approximated as a 7.5 km radius around Hoan Kiem Lake.

Adds columns station_class, ports_est, ports_source to data/stations_google.csv.
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
CENTER = (21.0285, 105.8542)
RING3_KM = 7.5
RANGES = {"hub": (20, 40), "standard": (8, 16), "small": (2, 6),
          "inner": (6, 8), "outer": (15, 25)}
SMALL = r"xăng|petrolimex|pvoil|pv oil|văn phòng|office"
STANDARD = (r"vincom|tttm|trung tâm thương mại|times city|royal city|mega mall|aeon|lotte|"
            r"chung cư|hầm|tòa|toà|plaza|metropolis|landmark|nhà xe nổi")
HUB = r"bến xe|bãi đỗ|bãi xe|depot|hub|nhổn"


def classify(text):
    if pd.Series(text).str.contains(SMALL).item():
        return "small"
    if pd.Series(text).str.contains(STANDARD).item():   # basements inside large urban areas
        return "standard"
    if pd.Series(text).str.contains(HUB).item():
        return "hub"
    return None


def main():
    path = DATA / "stations_google.csv"
    df = pd.read_csv(path)
    rng = np.random.default_rng(42)
    text = (df.name.fillna("") + " | " + df.address.fillna("")).str.lower()
    dist = 111.0 * np.hypot(df.lat - CENTER[0], (df.lon - CENTER[1]) * np.cos(np.radians(CENTER[0])))

    cls, ports, source = [], [], []
    for i in range(len(df)):
        known = df.dc_ports.iloc[i] if pd.notna(df.dc_ports.iloc[i]) else df.ports.iloc[i]
        c = classify(text.iloc[i])
        if c is None:
            c = "inner" if dist.iloc[i] <= RING3_KM else "outer"
        cls.append(c)
        if pd.notna(known):
            ports.append(int(known))
            source.append("google")
        else:
            lo, hi = RANGES[c]
            ports.append(int(rng.integers(lo, hi + 1)))
            source.append("class" if c in ("hub", "standard", "small") else "zone")

    df["station_class"], df["ports_est"], df["ports_source"] = cls, ports, source
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(df.groupby(["station_class", "ports_source"]).ports_est.agg(["count", "mean", "sum"]).round(1))
    print("total ports", df.ports_est.sum())


if __name__ == "__main__":
    main()
