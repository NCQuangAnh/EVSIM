"""Run, merge and summarise experiments from scripts/experiments.py, locally or on Kaggle.

One job = one arm on one seed. Each job writes outputs/jobs/<experiment>/<arm>__s<seed>.json,
so jobs can be split across machines (shards), resumed, and merged by copying files.

    # run (all shards on this machine, or one shard of a Kaggle batch)
    .venv/Scripts/python -W ignore scripts/run_jobs.py run --batch dev1 --jobs 7
    python scripts/run_jobs.py run --batch dev1 --shard 3 --nshards 14 --jobs 4
    # merge Kaggle result zips, then summarise
    .venv/Scripts/python scripts/run_jobs.py merge path/to/jobs_dev1_shard*.zip
    .venv/Scripts/python scripts/run_jobs.py summarize --batch dev1
    # list what is still missing
    .venv/Scripts/python scripts/run_jobs.py status --batch dev1
"""
import argparse
import dataclasses
import json
import os
import re
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from experiments import BATCHES, EXPERIMENTS, PROTOCOL, SCALES  # noqa: E402

JOBS_DIR = ROOT / "outputs" / "jobs"
METRICS = [  # key, label, scale, non-inferiority margin (None = none)
    ("service_level", "Service level (pt)", 100, 0.1),
    ("service_level_peak", "Service peak (pt)", 100, None),
    ("wait_min_p90", "Wait P90 (min)", 1, None),
    ("ride_reject_soc_share", "Battery share of declines (pt)", 100, None),
    ("charge_queue_min_mean", "Charger queue (min)", 1, None),
    ("strandings_per_day", "Run-outs/day", 1, None),
    ("energy_cost_adj_vnd_day", "Energy cost adj (k VND/day)", 1e-3, None),
    ("profit_adj_per_vehicle_day_vnd", "Profit adj/car/day (VND)", 1, 2000.0),
]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def job_path(exp, arm, seed):
    return JOBS_DIR / exp / f"{slug(arm)}__s{seed}.json"


def all_jobs(exp_names):
    """Every (experiment, arm, policy, overrides, seed), ordered so shards get a mix of arms."""
    jobs = []
    for exp in exp_names:
        e = EXPERIMENTS[exp]
        for seed in e["seeds"]:
            for name, policy, over, _ in e["arms"]:
                jobs.append((exp, name, policy, over, seed))
    jobs.sort(key=lambda j: (j[4], j[0], j[1]))
    return jobs


def run_one(job):
    from evsim.battery import POLICIES
    from evsim.config import SCENARIOS, Config
    from evsim.metrics import summarize
    from evsim.simulator import Simulator
    exp, name, policy, over, seed = job
    e = EXPERIMENTS[exp]
    sets = {**SCENARIOS["hanoi_full"], **SCALES[e["scale"]], **PROTOCOL, **e.get("extra", {}), **over}
    t0 = time.time()
    cfg = dataclasses.replace(Config(), seed=seed, **sets)
    m = summarize(Simulator(cfg, POLICIES[policy](cfg)).run())[0]
    out = {"experiment": exp, "arm": name, "policy": policy, "seed": seed, "overrides": sets,
           "runtime_s": round(time.time() - t0, 1), "host": os.environ.get("KAGGLE_KERNEL_RUN_TYPE", "local"),
           "metrics": {k: float(v) for k, v in m.items()}}
    p = job_path(exp, name, seed)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, default=str), encoding="utf-8")
    return exp, name, seed, out["runtime_s"]


def exp_names(a):
    names = BATCHES[a.batch] if a.batch else []
    return names + (a.exp or [])


def cmd_run(a):
    todo = [j for j in all_jobs(exp_names(a)) if not job_path(j[0], j[1], j[4]).exists()]
    mine = todo[a.shard::a.nshards]
    print(f"{len(todo)} jobs missing; shard {a.shard}/{a.nshards} runs {len(mine)} with {a.jobs} workers", flush=True)
    with ProcessPoolExecutor(a.jobs) as ex:
        for k, (exp, name, seed, rt) in enumerate(ex.map(run_one, mine), 1):
            print(f"[{k}/{len(mine)}] {exp} | {name} | seed {seed} | {rt:.0f}s", flush=True)


def load(exp):
    rows = []
    for f in (JOBS_DIR / exp).glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        rows.append({"arm": d["arm"], "seed": d["seed"], **d["metrics"]})
    return pd.DataFrame(rows)


def table(exp):
    e = EXPERIMENTS[exp]
    df = load(exp)
    if df.empty:
        return None
    rows = []
    for name, _, _, ref in e["arms"]:
        g = df[df.arm == name].set_index("seed")
        if g.empty:
            continue
        row = {"arm": name, "vs": ref or "-"}
        if ref is None:
            row["n"] = len(g)
            for key, label, scale, _ in METRICS:
                row[label] = f"{g[key].mean() * scale:,.2f}"
        else:
            b = df[df.arm == ref].set_index("seed")
            seeds = g.index.intersection(b.index)
            row["n"] = len(seeds)
            for key, label, scale, margin in METRICS:
                d = (g.loc[seeds, key] - b.loc[seeds, key]) * scale
                if len(d) < 2:
                    row[label] = f"{d.mean():+,.2f}"
                    continue
                lcb = d.mean() - student_t.ppf(0.95, len(d) - 1) * d.std(ddof=1) / np.sqrt(len(d))
                flag = "" if margin is None else (" ✓" if lcb > -margin else " ✗")
                row[label] = f"{d.mean():+,.2f} [{lcb:+,.2f}]{flag}"
        rows.append(row)
    return pd.DataFrame(rows)


def cmd_summarize(a):
    out = []
    for exp in exp_names(a):
        t = table(exp)
        if t is None:
            print(f"{exp}: no results yet")
            continue
        md = t.to_markdown(index=False)
        out.append(f"## {exp}\n\n{md}\n")
        print(f"## {exp}\n{md}\n")
    note = ("Differences vs the arm in column 'vs', paired by seed; [ ] = one-sided 95 % lower bound; "
            "✓/✗ = lower bound above/below minus the protocol margin (0.1 pt service, 2,000 VND profit).\n\n")
    name = a.batch or "_".join(a.exp)
    (ROOT / "outputs" / f"jobs_{name}_summary.md").write_text(note + "\n".join(out), encoding="utf-8")


def cmd_status(a):
    jobs = all_jobs(exp_names(a))
    done = sum(job_path(j[0], j[1], j[4]).exists() for j in jobs)
    print(f"{done}/{len(jobs)} jobs done")
    for exp in exp_names(a):
        js = [j for j in jobs if j[0] == exp]
        print(f"  {exp}: {sum(job_path(j[0], j[1], j[4]).exists() for j in js)}/{len(js)}")


def cmd_merge(a):
    for p in a.zips:
        new = 0
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if not name.startswith("outputs/jobs/") or name.endswith("/"):
                    continue
                dest = ROOT / name
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(z.read(name))
                    new += 1
        print(f"{p}: {new} new job files")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("run", "summarize", "status"):
        s = sub.add_parser(c)
        s.add_argument("--batch", choices=BATCHES)
        s.add_argument("--exp", nargs="*", choices=EXPERIMENTS)
        if c == "run":
            s.add_argument("--shard", type=int, default=0)
            s.add_argument("--nshards", type=int, default=1)
            s.add_argument("--jobs", type=int, default=os.cpu_count())
    m = sub.add_parser("merge")
    m.add_argument("zips", nargs="+")
    a = ap.parse_args()
    {"run": cmd_run, "summarize": cmd_summarize, "status": cmd_status, "merge": cmd_merge}[a.cmd](a)


if __name__ == "__main__":
    main()
