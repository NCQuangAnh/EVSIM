"""Trace every run-out (vehicle with an empty battery) in a run, by leg type.

    .venv/Scripts/python -W ignore scripts/trace_strandings.py --policy gsm_baseline --seed 3
    .venv/Scripts/python -W ignore scripts/trace_strandings.py --policy battery_addon --seed 3 --set addon_reject=False addon_nudge=False

Same scenario and seed as the official runs (hanoi_full, crn off) so the events are the ones
counted there. Output: outputs/dev/strandings_<policy>_seed<k>.csv
"""
import argparse
import dataclasses
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evsim.battery import POLICIES  # noqa: E402
from evsim.config import SCENARIOS, Config  # noqa: E402
from evsim.simulator import Simulator  # noqa: E402
from run_baseline import parse_overrides  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="gsm_baseline")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--set", nargs="*", default=[])
    a = ap.parse_args()
    cfg = dataclasses.replace(Config(), seed=a.seed, **{**SCENARIOS["hanoi_full"], **parse_overrides(a.set)})
    sim = Simulator(cfg, POLICIES[a.policy](cfg)).run()
    log = pd.DataFrame(sim.strand_log)
    out = ROOT / "outputs" / "dev" / f"strandings_{a.policy}_seed{a.seed}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    log.to_csv(out, index=False)
    print(f"{len(log)} run-outs on legs, {sim.home_runouts} on the drive home; saved {out}")
    if len(log):
        log["hour"] = (log.t / 3600 % 24).round(2)
        print(log.to_string())


if __name__ == "__main__":
    main()
