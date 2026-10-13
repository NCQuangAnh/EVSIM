"""Estimate P(driver declines a ride | SOC after the trip) from offer logs.

    .venv/Scripts/python scripts/fit_reject_curve.py --seeds 200 201

Until GSM's accept/decline logs (with SOC at offer time) arrive, the logs come from the B1
black box simulated on training seeds (never the evaluation seeds 0-4). The platform only
sees declines, not their reasons, so every decline counts. Rates are computed in SOC bins,
made monotone (lower SOC never declines less) and saved with the base rate of well-charged
cars (SOC after trip >= 0.6), which the battery module subtracts.
Writes data/reject_curve.json.
"""
import argparse
import dataclasses
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evsim.config import SCENARIOS, Config  # noqa: E402
from evsim.dispatch import GSMBaseline  # noqa: E402
from evsim.simulator import Simulator  # noqa: E402

BIN = 0.02
HIGH_SOC = 0.6


def collect(scenario, seed, hours, overrides):
    cfg = dataclasses.replace(Config(), seed=seed, **{**SCENARIOS[scenario], "sim_hours": hours, **overrides})
    sim = Simulator(cfg, GSMBaseline(cfg))
    sim.offer_log = []
    sim.run()
    print(f"seed {seed}: {len(sim.offer_log)} offers", flush=True)
    return np.array(sim.offer_log)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="hanoi_full")
    ap.add_argument("--seeds", type=int, nargs="+", default=[200, 201])
    ap.add_argument("--hours", type=float, default=48.0)
    ap.add_argument("--vehicles", type=int, default=1000, help="decline behaviour does not depend on fleet size")
    args = ap.parse_args()
    if any(s in range(0, 5) for s in args.seeds):
        sys.exit("seeds 0-4 are evaluation seeds")
    over = {"n_vehicles": args.vehicles, "daily_requests": round(args.vehicles * 118_533 / 5080)}
    with ProcessPoolExecutor(max_workers=len(args.seeds)) as pool:
        logs = list(pool.map(collect, [args.scenario] * len(args.seeds), args.seeds,
                             [args.hours] * len(args.seeds), [over] * len(args.seeds)))
    log = np.concatenate(logs)
    soc, declined = log[:, 0], log[:, 2]

    edges = np.arange(-0.2, 1.0 + BIN, BIN)
    idx = np.digitize(soc, edges) - 1
    n = np.bincount(idx, minlength=len(edges))[:len(edges) - 1]
    k = np.bincount(idx, weights=declined, minlength=len(edges))[:len(edges) - 1]
    centres = edges[:-1] + BIN / 2
    keep = n >= 30  # enough offers in the bin
    rate = k[keep] / n[keep]
    x = centres[keep]
    rate = np.maximum.accumulate(rate[::-1])[::-1]  # monotone: lower SOC never declines less
    base = float(declined[soc >= HIGH_SOC].mean())

    out = ROOT / "data" / "reject_curve.json"
    out.write_text(json.dumps({"soc_after": x.round(3).tolist(), "p_decline": rate.round(4).tolist(),
                               "p_base": round(base, 4), "offers": int(len(log)),
                               "seeds": args.seeds, "vehicles": args.vehicles, "hours": args.hours},
                              indent=1), encoding="utf-8")
    print(f"saved {out}: {len(log)} offers, base decline rate {base:.3f}")
    for s in (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5):
        print(f"  SOC after {s:.2f}: P(decline) {np.interp(s, x, rate):.3f}")


if __name__ == "__main__":
    main()
