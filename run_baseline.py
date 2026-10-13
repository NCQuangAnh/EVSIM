"""Run dispatch policies over several seeds and compare mean +/- std.

    python run_baseline.py --scenario stress --seeds 5 --policies gsm_baseline gsm_fwd_repo

Every run is recorded in the run registry so results can be looked up (or reproduced
exactly) by run id + policy + seed later:
  outputs/runs/index.csv                         one row per (run, policy, seed), key metrics
  outputs/runs/<run_id>/<policy>_seed<k>.json    full config and every metric
"""
import argparse
import dataclasses
import json
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import pandas as pd

from evsim.config import SCENARIOS, Config
from evsim.battery import POLICIES  # includes the battery add-on
from evsim.metrics import summarize
from evsim.simulator import Simulator

KEY_METRICS = [
    "trips", "service_level", "service_level_peak", "request_fill_rate", "rebooks_per_day",
    "cancel_assigned", "cancel_unassigned", "ride_reject_rate", "ride_reject_soc_share",
    "wait_min_mean", "wait_min_p90", "wait_min_peak_mean", "deadhead_ratio",
    "wasted_deadhead_km_day", "forward_assign_share", "reposition_offers_per_day",
    "repositions_per_day", "reposition_accept_rate",
    "strandings_per_day", "charge_queue_min_mean", "peak_share_charging",
    "utilization", "idle_share_online", "driver_earn_per_online_h_vnd", "driver_earn_cv",
    "charge_soc_to_mean", "charge_session_min_mean", "charge_nudges_per_day",
    "home_km_day", "lost_fare_vnd_day", "energy_cost_vnd_day", "driver_income_month_vnd",
    "profit_per_vehicle_day_vnd",
]


def parse_overrides(pairs):
    out = {}
    for kv in pairs:
        k, v = kv.split("=", 1)
        default = getattr(Config, k)
        out[k] = (v == "True") if isinstance(default, bool) else type(default)(v)
    return out


RUNS = Path("outputs/runs")
INDEX_COLS = ["service_level", "service_level_peak", "wait_min_mean", "wait_min_p90", "ride_reject_soc_share",
              "charge_queue_min_mean", "peak_share_charging", "driver_income_month_vnd", "profit_per_vehicle_day_vnd"]


def run_one(outdir, name, seed, overrides, run_id):
    """One simulation; saves detailed CSVs for seed 0, records config + metrics in the run
    registry and returns the summary row."""
    cfg = dataclasses.replace(Config(), seed=seed, **overrides)
    sim = Simulator(cfg, POLICIES[name](cfg)).run()
    summary, req, charge, snaps = summarize(sim)
    record = {"run_id": run_id, "policy": name, "seed": seed, "config": dataclasses.asdict(cfg),
              "metrics": {k: (None if v != v else v) for k, v in summary.items()}}  # NaN -> null
    (RUNS / run_id).mkdir(parents=True, exist_ok=True)
    (RUNS / run_id / f"{name}_seed{seed}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    if seed == 0:
        out = Path(outdir) / name
        out.mkdir(parents=True, exist_ok=True)
        req.to_csv(out / "requests_seed0.csv", index=False)
        charge.to_csv(out / "charging_seed0.csv", index=False)
        snaps.to_csv(out / "soc_snapshots_seed0.csv", index=False)
    print(f"{name} seed {seed}: service_level={summary['service_level']:.3f} "
          f"wait={summary['wait_min_mean']:.1f}min "
          f"profit/veh/day={summary['profit_per_vehicle_day_vnd']:,.0f}", flush=True)
    return {"seed": seed, **summary}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=SCENARIOS, default="stress")
    ap.add_argument("--policies", nargs="+", choices=POLICIES, default=list(POLICIES))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--seed-start", type=int, default=0,
                    help="first seed; evaluation uses 0-4, tuning should use other seeds (e.g. 100)")
    ap.add_argument("--jobs", type=int, default=1, help="simulations run in parallel")
    ap.add_argument("--tag", default="", help="suffix for the output folder, e.g. a quick test")
    ap.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE",
                    help="override Config fields, e.g. --set daily_requests=8000 n_vehicles=250")
    args = ap.parse_args()

    overrides = {**SCENARIOS[args.scenario], **parse_overrides(args.set)}
    outdir = f"outputs/{args.scenario}" + (f"_{args.tag}" if args.tag else "")
    started = datetime.now()
    run_id = started.strftime("%Y%m%d-%H%M%S") + f"_{args.scenario}" + (f"_{args.tag}" if args.tag else "")
    jobs = [(outdir, name, seed, overrides, run_id) for name in args.policies
            for seed in range(args.seed_start, args.seed_start + args.seeds)]
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(run_one, *zip(*jobs)))
    else:
        results = [run_one(*j) for j in jobs]

    means = {}
    for name in args.policies:
        out = Path(outdir) / name
        out.mkdir(parents=True, exist_ok=True)
        rows = [r for (_, n, _, _, _), r in zip(jobs, results) if n == name]
        df = pd.DataFrame(rows)
        df.to_csv(out / "summary_per_seed.csv", index=False)
        agg = df.drop(columns="seed").agg(["mean", "std"]).T
        agg.to_csv(out / "summary.csv")
        means[name] = agg["mean"].map("{:,.3f}".format) + " ± " + agg["std"].map("{:,.3f}".format)

    # run registry index: one row per policy and seed
    index = pd.DataFrame([{"run_id": run_id, "started": started.isoformat(timespec="seconds"),
                           "scenario": args.scenario, "tag": args.tag, "policy": n, "seed": s,
                           "n_vehicles": o.get("n_vehicles", Config.n_vehicles),
                           "sim_hours": o.get("sim_hours", Config.sim_hours),
                           "overrides": json.dumps(parse_overrides(args.set), ensure_ascii=False),
                           **{k: r[k] for k in INDEX_COLS}}
                          for (_, n, s, o, _), r in zip(jobs, results)])
    idx_path = RUNS / "index.csv"
    index.to_csv(idx_path, mode="a", header=not idx_path.exists(), index=False)
    print(f"run registry: {idx_path} (run_id {run_id})")

    table = pd.DataFrame(means).loc[KEY_METRICS]
    table.to_csv(f"{outdir}/comparison.csv")
    print(f"\nscenario={args.scenario} overrides={overrides} seeds={args.seeds}\n" + table.to_string())


if __name__ == "__main__":
    main()
