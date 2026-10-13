"""Phase 0 checks on development seeds (300+): paired-difference spread and statistical power.

For each seed, runs the black box and the black box + battery module on identical inputs and
records every metric, with and without common random numbers (cfg.crn).

    .venv/Scripts/python -W ignore scripts/dev_variance.py --seeds 10 --jobs 8
    .venv/Scripts/python -W ignore scripts/dev_variance.py --summarize-only

Output: outputs/dev/variance_runs.csv (one row per run) and outputs/dev/variance_summary.md
(sd of paired differences, and the seeds needed to show non-inferiority with the margins below).
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
SMALL = {"n_vehicles": 1000, "daily_requests": 23333}
ARMS = {"black box (B1)": ("gsm_baseline", {}), "B1 + module": ("battery_addon", {})}
# protocol margins (non-inferiority), 2026-10-11
MARGINS = {"service_level": (100, 0.1, "pt"), "profit_adj_per_vehicle_day_vnd": (1, 2000.0, "VND")}


def one(job):
    arm, policy, extra, seed, crn = job
    cfg = dataclasses.replace(Config(), seed=seed, **{**SCENARIOS["hanoi_full"], **SMALL, **extra, "crn": crn})
    m = summarize(Simulator(cfg, POLICIES[policy](cfg)).run())[0]
    return {"arm": arm, "seed": seed, "crn": crn, **{k: float(v) for k, v in m.items()}}


def summarize_runs(df):
    lines = ["| CRN | metric | mean diff | sd of paired diff | n | seeds for LCB > -margin if true diff = 0 |",
             "|---|---|---|---|---|---|"]
    for crn, g in df.groupby("crn"):
        base = g[g.arm == "black box (B1)"].set_index("seed")
        mod = g[g.arm == "B1 + module"].set_index("seed")
        seeds = base.index.intersection(mod.index)
        for key, (scale, margin, unit) in MARGINS.items():
            d = (mod.loc[seeds, key] - base.loc[seeds, key]) * scale
            sd = d.std(ddof=1)
            # one-sided 95 % lower bound = mean - t * sd / sqrt(n); need it above -margin when mean = 0
            need = next((n for n in range(3, 201) if student_t.ppf(0.95, n - 1) * sd / np.sqrt(n) < margin), ">200")
            lines.append(f"| {crn} | {key} | {d.mean():+.3f} {unit} | {sd:.3f} {unit} | {len(d)} | {need} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--seed-start", type=int, default=300)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--summarize-only", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "variance_runs.csv"
    if not a.summarize_only:
        jobs = [(arm, pol, extra, s, crn) for crn in (True, False) for s in range(a.seed_start, a.seed_start + a.seeds)
                for arm, (pol, extra) in ARMS.items()]
        rows = []
        with ProcessPoolExecutor(a.jobs) as ex:
            for r in ex.map(one, jobs):
                rows.append(r)
                print(f"done {r['arm']} seed {r['seed']} crn {r['crn']}", flush=True)
        pd.DataFrame(rows).to_csv(f, index=False)
    text = summarize_runs(pd.read_csv(f))
    (OUT / "variance_summary.md").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
