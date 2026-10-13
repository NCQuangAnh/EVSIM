#!/usr/bin/env python3
"""Execute OCP1 20-day 7-seed validation scenarios across baseline and policy arms.

Executes:
  - 7 seeds: [7, 101, 2024, 31337, 55555, 9001, 4242]
  - 20 days per seed under map="ocp1" and physics="docx"
  - Baseline arm: soc_price_weight = 0.0 (F form)
  - Policy arm: soc_price_weight = 0.5 (F+B form)
  - Writes results/ocp1-baseline.json and results/ocp1-policy.json
  - Pre-warms Dijkstra shortest path cache on _OCP1_ADJ for sub-microsecond lookups
  - Prints comparative Table 9/10 benchmark reconciliation

Usage:
  uv run --no-project python scripts/run_ocp1.py
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import gsm_sim as G  # noqa: E402

DEFAULT_SEEDS = [7, 101, 2024, 31337, 55555, 9001, 4242]
DEFAULT_DAYS = 20
DEFAULT_VEHICLES = 60
DEFAULT_WEIGHT = 0.5


def prewarm_route_cache(cfg: G.Config) -> int:
    """Pre-warm Dijkstra route cache for all 36 pairwise zone combinations."""
    G.load_ocp1_adj()
    zones = G.build_ocp1_zones(cfg)
    count = 0
    for i, z1 in enumerate(zones):
        for z2 in zones[i + 1:]:
            if z1.node is not None and z2.node is not None:
                G.route_km(z1.node, z2.node)
                count += 1
    return count


def run_arm_multiseed(
    cfg_template: G.Config,
    seeds: list[int],
    label: str,
    out_path: Path,
) -> dict:
    """Execute multi-seed multi-day simulation for one experimental arm."""
    all_records: list[dict] = []
    by_seed: dict[str, dict] = {}

    for seed in seeds:
        cfg = G.Config(**{**asdict(cfg_template), "seed": seed})
        rng0 = random.Random(seed)
        zones = G.build_zones(cfg, rng0)
        fleet = None
        seed_days: list[dict] = []

        for d in range(cfg.days):
            day_res = G.run_day(cfg, zones, d, rng0, opening_fleet=fleet)
            if getattr(cfg, "physics", "legacy") == "docx":
                fleet = day_res.get("_fleet")

            clean = {k: v for k, v in day_res.items() if k != "_fleet"}
            clean["seed"] = seed
            tot_km = clean["deadhead_km"] + clean["distance_km"]
            clean["deadhead_fraction"] = (
                clean["deadhead_km"] / max(1e-6, tot_km)
            )
            clean["service_level"] = clean["match_rate"]

            # Profit calculations:
            # 1. Simulator standard profit
            profit_sim = (
                clean["revenue_vnd"]
                - clean["energy_vnd"]
                - clean["trips"] * G.DRIVER_PAY_VND_PER_TRIP
                - tot_km * G.OPEX_VND_PER_KM
            )
            clean["profit_sim_vnd"] = profit_sim
            clean["profit_sim_per_vehicle_day"] = profit_sim / cfg.n_vehicles

            # 2. Docx Table 8 / Table 10 accounting profit (Gross margin / veh / day)
            profit_docx = (clean["revenue_vnd"] - clean["energy_vnd"]) / cfg.n_vehicles
            clean["profit_vnd"] = clean["revenue_vnd"] - clean["energy_vnd"]
            clean["profit_per_vehicle_day"] = profit_docx

            seed_days.append(clean)
            all_records.append(clean)

        by_seed[str(seed)] = {
            "summary": G.summarise(seed_days),
            "days": seed_days,
        }

    global_summary = G.summarise(all_records)
    global_summary["label"] = label
    global_summary["n_seeds"] = len(seeds)
    global_summary["n_days"] = cfg_template.days
    global_summary["total_records"] = len(all_records)
    global_summary["seeds"] = list(seeds)
    global_summary["config"] = asdict(cfg_template)

    global_summary["benchmark"] = {
        "service_level": global_summary["mean"].get("match_rate", 0.0),
        "pickup_wait_avg_min": global_summary["mean"].get("pickup_wait_min", 0.0),
        "deadhead_fraction": global_summary["mean"].get("deadhead_fraction", 0.0),
        "profit_per_vehicle_day_vnd": global_summary["mean"].get("profit_per_vehicle_day", 0.0),
        "revenue_vnd_day": global_summary["mean"].get("revenue_vnd", 0.0),
        "energy_vnd_day": global_summary["mean"].get("energy_vnd", 0.0),
        "cancel_before_day": global_summary["mean"].get("cancel_before", 0.0),
        "cancel_after_day": global_summary["mean"].get("cancel_after", 0.0),
        "wasted_km_day": global_summary["mean"].get("wasted_km", 0.0),
    }

    output_payload = {
        "summary": global_summary,
        "seeds": list(seeds),
        "by_seed": by_seed,
        "days": all_records,
        "daily_records": all_records,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output_payload, indent=1), encoding="utf-8")
    return global_summary


def print_benchmark_table(base_sum: dict, pol_sum: dict) -> None:
    """Print ASCII comparison against docx Table 9/10 benchmarks."""
    b_mean = base_sum["mean"]
    p_mean = pol_sum["mean"]

    b_sl = b_mean["match_rate"] * 100.0
    p_sl = p_mean["match_rate"] * 100.0

    b_wait = b_mean["pickup_wait_min"]
    p_wait = p_mean["pickup_wait_min"]

    b_dh = b_mean["deadhead_fraction"] * 100.0
    p_dh = p_mean["deadhead_fraction"] * 100.0

    b_rev = b_mean["revenue_vnd"] / 1e6
    p_rev = p_mean["revenue_vnd"] / 1e6

    b_ene = b_mean["energy_vnd"] / 1e6
    p_ene = p_mean["energy_vnd"] / 1e6

    b_prof = b_mean["profit_per_vehicle_day"] / 1e6
    p_prof = p_mean["profit_per_vehicle_day"] / 1e6

    b_cb = b_mean.get("cancel_before", 0.0)
    p_cb = p_mean.get("cancel_before", 0.0)

    b_ca = b_mean.get("cancel_after", 0.0)
    p_ca = p_mean.get("cancel_after", 0.0)

    b_wasted = b_mean.get("wasted_km", 0.0)
    p_wasted = p_mean.get("wasted_km", 0.0)

    print("\n" + "=" * 80)
    print(" V-RIC OCP1 20-DAY 7-SEED VALIDATION BENCHMARK COMPARISON (DOCX RECONCILIATION)")
    print("=" * 80)
    print(f"{'Metric':<32} {'Base (B1)':>11} {'Policy (B2)':>12} {'Delta':>9} {'docx B1':>9} {'docx B2':>9}")
    print("-" * 80)

    def row(name, bv, pv, fmt, docx_b1, docx_b2, lower_better=False):
        d = pv - bv
        pct = (d / bv * 100.0) if bv else 0.0
        sign = "+" if d > 0 else ""
        d_str = f"{sign}{d:.2f}" if fmt == "f" else f"{pct:+.1f}%"
        b_str = f"{bv:.2f}" if fmt == "f" else f"{bv:.1f}%" if fmt == "%" else f"{bv:.3f}M"
        p_str = f"{pv:.2f}" if fmt == "f" else f"{pv:.1f}%" if fmt == "%" else f"{pv:.3f}M"
        print(f"{name:<32} {b_str:>11} {p_str:>12} {d_str:>9} {docx_b1:>9} {docx_b2:>9}")

    row("Service Level (Match Rate)", b_sl, p_sl, "%", "81.4%", "82.7%")
    row("Pickup Wait Avg (min)", b_wait, p_wait, "f", "5.97", "5.70", lower_better=True)
    row("Deadhead Fraction (% km)", b_dh, p_dh, "%", "8.9%", "8.1%", lower_better=True)
    row("Fleet Revenue / day (M VND)", b_rev, p_rev, "M", "10,460M", "10,630M")
    row("Fleet Energy / day (M VND)", b_ene, p_ene, "M", "564M", "564M")
    row("Profit / Vehicle / Day (M VND)", b_prof, p_prof, "M", "1.256M", "1.281M")
    row("Pre-Assign Cancels / day", b_cb, p_cb, "f", "—", "—", lower_better=True)
    row("Mid-Deadhead Cancels / day", b_ca, p_ca, "f", "—", "—", lower_better=True)
    row("Wasted Empty Km / day", b_wasted, p_wasted, "f", "6,311", "5,123", lower_better=True)
    print("=" * 80 + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run OCP1 20-day 7-seed validation scenarios.")
    ap.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS,
                    help="Simulation random seeds (default: 7, 101, 2024, 31337, 55555, 9001, 4242)")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS,
                    help="Simulation days per seed (default: 20)")
    ap.add_argument("--vehicles", type=int, default=DEFAULT_VEHICLES,
                    help="Fleet size (default: 60)")
    ap.add_argument("--weight", type=float, default=DEFAULT_WEIGHT,
                    help="Policy soc_price_weight (default: 0.5)")
    ap.add_argument("--baseline-weight", type=float, default=0.0,
                    help="Baseline soc_price_weight (default: 0.0)")
    ap.add_argument("--outdir", default="results",
                    help="Output directory (default: results)")
    ap.add_argument("--map", default="ocp1", choices=["lattice", "ocp1"],
                    help="Map graph topology (default: ocp1)")
    ap.add_argument("--physics", default="docx", choices=["legacy", "docx"],
                    help="Physics engine (default: docx)")
    ap.add_argument("--scenario", default="normal",
                    help="Demand scenario profile (default: normal)")
    ap.add_argument("--skip-baseline", action="store_true",
                    help="Skip baseline run (debug only)")
    ap.add_argument("--skip-policy", action="store_true",
                    help="Skip policy run (debug only)")
    args = ap.parse_args()

    outdir = ROOT / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    base_cfg = G.Config(
        days=args.days,
        n_vehicles=args.vehicles,
        scenario=args.scenario,
        map=args.map,
        physics=args.physics,
        soc_price_weight=args.baseline_weight,
    )

    print(f"Pre-warming OCP1 route cache for map='{args.map}'...")
    cached_pairs = prewarm_route_cache(base_cfg)
    print(f"Pre-warmed {cached_pairs} zone-pair routes in {time.time() - t_start:.2f}s.")

    base_sum, pol_sum = None, None

    if not args.skip_baseline:
        print(f"\n[1/2] Executing Baseline Arm (weight={args.baseline_weight}, {len(args.seeds)} seeds x {args.days} days)...")
        t0 = time.time()
        base_out = outdir / "ocp1-baseline.json"
        base_sum = run_arm_multiseed(base_cfg, args.seeds, "ocp1-baseline", base_out)
        print(f"      Completed in {time.time() - t0:.1f}s -> {base_out.relative_to(ROOT)}")

    if not args.skip_policy:
        print(f"\n[2/2] Executing Policy Arm (weight={args.weight}, {len(args.seeds)} seeds x {args.days} days)...")
        t0 = time.time()
        pol_cfg = G.Config(**{**asdict(base_cfg), "soc_price_weight": args.weight})
        pol_out = outdir / "ocp1-policy.json"
        pol_sum = run_arm_multiseed(pol_cfg, args.seeds, "ocp1-policy", pol_out)
        print(f"      Completed in {time.time() - t0:.1f}s -> {pol_out.relative_to(ROOT)}")

    total_time = time.time() - t_start
    print(f"\nAll validation runs finished in {total_time:.1f}s ({total_time / 60.0:.2f} min).")

    if base_sum and pol_sum:
        print_benchmark_table(base_sum, pol_sum)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
