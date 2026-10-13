"""Development-seed ablation of battery-layer variants (protocol: seeds 300-319, crn on).

Every arm runs on the same seeds with common random numbers and the corrected driver rule
(charge before driving home); differences are paired by seed against the black box and
reported with one-sided 95 % lower confidence bounds against the protocol margins.

    .venv/Scripts/python -W ignore scripts/dev_ablation.py --group bonus --seeds 10 --jobs 6
    .venv/Scripts/python -W ignore scripts/dev_ablation.py --group bonus --summarize-only

Outputs: outputs/dev/<group>_runs.csv, outputs/dev/<group>_table.md
"""
import argparse
import dataclasses
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evsim.battery import POLICIES  # noqa: E402
from evsim.config import SCENARIOS, Config  # noqa: E402
from evsim.metrics import summarize  # noqa: E402
from evsim.simulator import Simulator  # noqa: E402

OUT = ROOT / "outputs" / "dev"
BASE = {**SCENARIOS["hanoi_full"], "n_vehicles": 1000, "daily_requests": 23333, "crn": True,
        "charge_before_home": True}
NO = {"addon_feasible": False, "addon_reject": False, "addon_nudge": False}
IQR = {"addon_scale": "iqr", "addon_lambda": 0.5}

# group -> list of (arm, policy, overrides); the first arm is the black box everything is paired with
GROUPS = {
    "bonus": [
        ("black box (B1)", "gsm_baseline", {}),
        ("(c) nudges only", "battery_addon", {**NO, "addon_nudge": True}),
        ("v1 full (a)(b)(c)", "battery_addon", {}),
        ("full, IQR-scaled (b)", "battery_addon", IQR),
        ("full IQR + station bonus", "battery_addon", {**IQR, "addon_station_bonus": 0.5}),
        ("full IQR + pre-peak bonus", "battery_addon", {**IQR, "addon_prepeak_bonus": 0.5}),
        ("full IQR + both bonuses", "battery_addon", {**IQR, "addon_station_bonus": 0.5, "addon_prepeak_bonus": 0.5}),
        ("station bonus only", "battery_addon", {**NO, **IQR, "addon_station_bonus": 0.5}),
    ],
}
METRICS = [  # key, label, scale, margin (None = no margin)
    ("service_level", "Service level (pt)", 100, 0.1),
    ("service_level_peak", "Service peak (pt)", 100, None),
    ("wait_min_p90", "Wait P90 (min)", 1, None),
    ("ride_reject_soc_share", "Battery share of declines (pt)", 100, None),
    ("charge_queue_min_mean", "Charger queue (min)", 1, None),
    ("energy_cost_adj_vnd_day", "Energy cost adj (k VND/day)", 1e-3, None),
    ("profit_adj_per_vehicle_day_vnd", "Profit adj/car/day (VND)", 1, 2000.0),
]


def one(job):
    arm, policy, over, seed = job
    cfg = dataclasses.replace(Config(), seed=seed, **{**BASE, **over})
    m = summarize(Simulator(cfg, POLICIES[policy](cfg)).run())[0]
    return {"arm": arm, "seed": seed, **{k: float(v) for k, v in m.items()}}


def table(df, arms):
    base = df[df.arm == arms[0]].set_index("seed")
    rows = []
    for arm in arms:
        g = df[df.arm == arm].set_index("seed")
        seeds = base.index.intersection(g.index)
        row = {"arm": arm, "n": len(seeds)}
        for key, label, scale, margin in METRICS:
            if arm == arms[0]:
                row[label] = f"{g[key].mean() * scale:,.2f}"
                continue
            d = (g.loc[seeds, key] - base.loc[seeds, key]) * scale
            half = student_t.ppf(0.95, len(d) - 1) * d.std(ddof=1) / np.sqrt(len(d))
            flag = "" if margin is None else (" ✓" if d.mean() - half > -margin else " ✗")
            row[label] = f"{d.mean():+,.2f} [LCB {d.mean() - half:+,.2f}]{flag}"
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="bonus", choices=GROUPS)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--seed-start", type=int, default=300)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--summarize-only", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{a.group}_runs.csv"
    arms = [x[0] for x in GROUPS[a.group]]
    if not a.summarize_only:
        old = pd.read_csv(f) if f.exists() else pd.DataFrame(columns=["arm", "seed"])
        done = set(zip(old.arm, old.seed))
        jobs = [(arm, pol, over, s) for s in range(a.seed_start, a.seed_start + a.seeds)
                for arm, pol, over in GROUPS[a.group] if (arm, s) not in done]
        rows = old.to_dict("records")
        with ProcessPoolExecutor(a.jobs) as ex:
            for r in ex.map(one, jobs):
                rows.append(r)
                pd.DataFrame(rows).to_csv(f, index=False)   # resumable
                print(f"done {r['arm']} seed {r['seed']}", flush=True)
    t = table(pd.read_csv(f), arms)
    md = t.to_markdown(index=False)
    (OUT / f"{a.group}_table.md").write_text(
        "Differences vs the black box, paired by seed; [LCB] = one-sided 95 % lower bound; "
        "✓/✗ = LCB above/below minus the protocol margin.\n\n" + md + "\n", encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
