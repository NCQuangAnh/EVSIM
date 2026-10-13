"""Learn V(cell, 10-min slot) for the B4 DiDi-style dispatcher from simulated experience.

    .venv/Scripts/python scripts/train_didi_values.py --scenario hanoi_full --seeds 200 201

Runs the B2 policy on training seeds (never the evaluation seeds 0-4) and, as in Xu et al.
(KDD 2018, Section 3), breaks the log into transitions:
  - serving: from the vehicle's cell/slot when matched to the drop-off cell, after
    dt = pickup + wait + delivery time; reward = fare spread over dt and discounted (Eq. 1);
  - idle: a free car stays in its cell for one 10-minute slot, reward 0;
then runs Algorithm 1 (DP backwards over the slots of a day).
Writes data/didi_values_<scenario>.npz.
"""
import argparse
import dataclasses
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evsim import values  # noqa: E402
from evsim.config import SCENARIOS, Config  # noqa: E402
from evsim.dispatch import GSMForwardReposition  # noqa: E402
from evsim.simulator import IDLE, Simulator  # noqa: E402


def collect(scenario, seed, hours, gamma):
    cfg = dataclasses.replace(Config(), seed=seed, **{**SCENARIOS[scenario], "sim_hours": hours})
    sim = Simulator(cfg, GSMForwardReposition(cfg))
    sim.idle_log = []
    sim.run()
    grid = values.Grid()

    served = [r for r in sim.requests if r.status == "served" and r.assign_lat is not None]
    t0 = np.array([r.t_assign for r in served])
    t1 = np.array([r.t_dropoff for r in served])
    dt = (t1 - t0) / values.SLOT_S
    trips = dict(
        s_cell=grid.cell([r.assign_lat for r in served], [r.assign_lon for r in served]),
        s_slot=values.slot(t0),
        e_cell=grid.cell([r.d_lat for r in served], [r.d_lon for r in served]),
        e_slot=values.slot_after(t0, t1),
        dt=dt,
        r=values.spread_reward(np.array([r.fare for r in served]), dt, gamma),
    )
    idle = np.array(sim.idle_log)  # t, lat, lon, logged every slot
    idles = dict(
        s_cell=grid.cell(idle[:, 1], idle[:, 2]), s_slot=values.slot(idle[:, 0]),
        e_cell=grid.cell(idle[:, 1], idle[:, 2]), e_slot=values.slot(idle[:, 0]) + 1,
        dt=np.ones(len(idle)), r=np.zeros(len(idle)),
    )
    print(f"seed {seed}: {len(served)} trip transitions, {len(idle)} idle transitions", flush=True)
    return {k: np.concatenate([trips[k], idles[k]]) for k in trips}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="hanoi_full")
    ap.add_argument("--seeds", type=int, nargs="+", default=[200, 201])
    ap.add_argument("--hours", type=float, default=48.0)
    ap.add_argument("--gamma", type=float, default=Config.didi_gamma)
    args = ap.parse_args()
    if any(s in range(0, 5) for s in args.seeds):
        sys.exit("seeds 0-4 are evaluation seeds; train on others")

    with ProcessPoolExecutor(max_workers=len(args.seeds)) as pool:
        parts = list(pool.map(collect, [args.scenario] * len(args.seeds), args.seeds,
                              [args.hours] * len(args.seeds), [args.gamma] * len(args.seeds)))
    tr = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    grid = values.Grid()
    V, counts = values.evaluate(tr, grid, args.gamma)
    out = ROOT / "data" / f"didi_values_{args.scenario}.npz"
    np.savez_compressed(out, V=V, counts=counts, gamma=args.gamma, seeds=np.array(args.seeds),
                        hours=args.hours)
    seen = counts.sum(axis=1) > 0
    print(f"saved {out}: {grid.n} cells ({seen.sum()} visited) x {values.SLOTS} slots; "
          f"V mean {V[seen].mean():,.0f} VND, p5-p95 {np.percentile(V[seen], 5):,.0f}-{np.percentile(V[seen], 95):,.0f}")


if __name__ == "__main__":
    main()
