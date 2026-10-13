"""Package the simulator for Kaggle.

    .venv/Scripts/python kaggle/make_bundle.py

Writes kaggle/evsim_bundle/ (upload this folder as a Kaggle Dataset) containing
  vric.zip          code + the data files the hanoi_full scenario needs
  fingerprint.json  a tiny reference run made here, so the notebook can check that Kaggle
                    reproduces this machine's random streams (needed to reuse the black-box
                    runs made here and to pair seeds across machines)
  versions.json     library versions to pin on Kaggle
"""
import dataclasses
import json
import shutil
import sys
import zipfile
from pathlib import Path

import numpy
import pandas
import scipy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FILES = ["run_baseline.py", "scripts/run_ablation.py", "scripts/run_jobs.py", "scripts/experiments.py",
         "data/road_cells.npz", "data/stations_google.csv",
         "data/didi_values_hanoi_full.npz", "data/reject_curve.json"]
FINGERPRINT = {"n_vehicles": 200, "daily_requests": 4667, "sim_hours": 3.0}
FINGER_KEYS = ["requests", "service_level", "wait_min_mean", "charge_sessions_per_day", "kwh_public_per_day"]


PROTO = {"crn": True, "charge_before_home": True, "addon_scale": "iqr", "addon_lambda": 0.5,
         "addon_station_bonus": 0.5, "addon_prepeak_bonus": 0.5}
# (name, policy, extra overrides): old code path, and the protocol path (CRN, bonuses, IQR)
CASES = [("gsm_baseline", "gsm_baseline", {}), ("battery_addon", "battery_addon", {}),
         ("battery_addon_protocol", "battery_addon", PROTO)]


def fingerprint():
    from evsim.battery import POLICIES
    from evsim.config import SCENARIOS, Config
    from evsim.metrics import summarize
    from evsim.simulator import Simulator
    out = {}
    for name, policy, extra in CASES:
        over = {**FINGERPRINT, **extra}
        cfg = dataclasses.replace(Config(), seed=0, **{**SCENARIOS["hanoi_full"], **over})
        summary = summarize(Simulator(cfg, POLICIES[policy](cfg)).run())[0]
        out[name] = {"policy": policy, "overrides": over,
                     "metrics": {k: round(float(summary[k]), 6) for k in FINGER_KEYS}}
    return out


def main():
    out = ROOT / "kaggle" / "evsim_bundle"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    with zipfile.ZipFile(out / "vric.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted((ROOT / "evsim").glob("*.py")):
            z.write(f, f.relative_to(ROOT).as_posix())
        for f in FILES:
            z.write(ROOT / f, f)
    (out / "versions.json").write_text(json.dumps(
        {"python": sys.version.split()[0], "numpy": numpy.__version__, "scipy": scipy.__version__,
         "pandas": pandas.__version__}, indent=1))
    (out / "fingerprint.json").write_text(json.dumps(
        {"scenario": "hanoi_full", "seed": 0, "cases": fingerprint()}, indent=1))
    size = sum(p.stat().st_size for p in out.iterdir()) / 1e6
    print(f"bundle ready: {out} ({size:.1f} MB)")


if __name__ == "__main__":
    main()
