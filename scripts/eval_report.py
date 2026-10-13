"""Final evaluation report for a locked configuration, following docs/protocol.md.

    .venv/Scripts/python -W ignore scripts/eval_report.py --exp eval_main

Goal B (per black box): non-inferiority, one-sided paired t-test of H0: mean diff <= -margin,
Holm-corrected over all black boxes x {service, profit}; also the one-sided 95 % lower bound.
Goal C: equal-weight average of the per-black-box differences, seed by seed; gain if the lower
bound of the mean is above 0 (reported per metric). Output: outputs/<exp>_report.md
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import run_jobs as rj  # noqa: E402
from experiments import EXPERIMENTS  # noqa: E402

PRIMARY = [("service_level", "Service level (pt)", 100, 0.1), ("profit_adj_per_vehicle_day_vnd", "Profit adj/car/day (VND)", 1, 2000.0)]
SECONDARY = [("service_level_peak", "Service peak (pt)", 100), ("wait_min_mean", "Wait mean (min)", 1),
             ("wait_min_p90", "Wait P90 (min)", 1), ("ride_reject_soc_share", "Battery share of declines (pt)", 100),
             ("peak_share_charging", "Charging at peak (pt)", 100), ("charge_queue_min_mean", "Charger queue (min)", 1),
             ("strandings_per_day", "Run-outs/day", 1), ("energy_cost_adj_vnd_day", "Energy cost adj (M VND/day)", 1e-6),
             ("driver_income_month_vnd", "Driver income (M VND/month)", 1e-6), ("driver_earn_cv", "Driver earnings CV", 1)]


def holm(pvals):
    order = np.argsort(pvals)
    adj, run = np.empty(len(pvals)), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(pvals) - rank) * pvals[i]))
        adj[i] = run
    return adj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="eval_main")
    a = ap.parse_args()
    e = EXPERIMENTS[a.exp]
    df = rj.load(a.exp)
    pairs = [(name, ref) for name, _, _, ref in e["arms"] if ref is not None]
    rows, tests, diffs = [], [], {}
    for name, ref in pairs:
        g, b = df[df.arm == name].set_index("seed"), df[df.arm == ref].set_index("seed")
        seeds = g.index.intersection(b.index)
        n = len(seeds)
        row = {"arm": name, "n": n, "baseline service %": f"{b.loc[seeds, 'service_level'].mean() * 100:.2f}"}
        for key, label, scale, margin in PRIMARY:
            d = (g.loc[seeds, key] - b.loc[seeds, key]) * scale
            diffs.setdefault(key, {})[name] = d
            se = d.std(ddof=1) / np.sqrt(n)
            lcb = d.mean() - student_t.ppf(0.95, n - 1) * se
            p_ni = 1 - student_t.cdf((d.mean() + margin) / se, n - 1)       # H0: diff <= -margin
            p_sup = 1 - student_t.cdf(d.mean() / se, n - 1)                  # H0: diff <= 0
            tests.append(p_ni)
            row[label] = f"{d.mean():+,.2f} [LCB {lcb:+,.2f}]"
            row[f"{label} p(sup)"] = f"{p_sup:.4f}"
            row[f"_{key}_pni"] = p_ni
        for key, label, scale in SECONDARY:
            d = (g.loc[seeds, key] - b.loc[seeds, key]) * scale
            h = student_t.ppf(0.975, n - 1) * d.std(ddof=1) / np.sqrt(n)
            row[label] = f"{d.mean():+,.2f} ± {h:.2f}"
        rows.append(row)
    adj = holm(np.array(tests))
    k = 0
    for row in rows:
        for key, label, _, _ in PRIMARY:
            row[f"{label} non-inferior (Holm p)"] = f"{'✓' if adj[k] < 0.05 else '✗'} ({adj[k]:.2g})"
            row.pop(f"_{key}_pni")
            k += 1
    table = pd.DataFrame(rows)

    # goal C over the main pairs (one per black box, excluding variants)
    main_pairs = [name for name, ref in pairs if name.endswith("+ v2.1") or name.endswith("+ v2.2")]
    goal_c = []
    for key, label, scale, _ in PRIMARY:
        m = pd.concat([diffs[key][nm] for nm in main_pairs], axis=1).mean(axis=1)
        n = len(m)
        h = student_t.ppf(0.95, n - 1) * m.std(ddof=1) / np.sqrt(n)
        goal_c.append(f"| {label} | {m.mean():+,.3f} | {m.mean() - h:+,.3f} | {'✓ gain' if m.mean() - h > 0 else '✗'} | "
                      f"{(m > 0).mean():.0%} |")
    prim_cols = ["arm", "n", "baseline service %"] + [c for c in table.columns if any(c.startswith(p[1]) for p in PRIMARY)]
    out = [f"# Final evaluation: {a.exp}", "",
           f"Full scale, seeds {min(e['seeds'])}–{max(e['seeds'])}, paired by seed. Margins: 0.1 pt service, 2,000 VND profit.",
           "Non-inferiority: one-sided paired t-test, Holm-corrected over all arms x 2 metrics.", "",
           "## Goal B: every black box", "", table[prim_cols].to_markdown(index=False), "",
           "## Goal C: equal-weight average over the 7 black boxes", "",
           "| Metric | Mean gain | One-sided 95 % LCB | Result | Seeds with a gain |", "|---|---|---|---|---|", *goal_c, "",
           "## Secondary metrics (diff ± 95 % CI half-width)", "",
           table[["arm"] + [s[1] for s in SECONDARY]].to_markdown(index=False), ""]
    path = ROOT / "outputs" / f"{a.exp}_report.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
