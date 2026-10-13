"""Ablation study of the battery module on top of the black-box dispatcher (B1).

    .venv/Scripts/python scripts/run_ablation.py --stage small   # 1,000 cars: groups A-D (~30 min)
    .venv/Scripts/python scripts/run_ablation.py --stage full    # 5,080 cars: groups A and E (~3 h)
    .venv/Scripts/python scripts/run_ablation.py --stage small --summarize-only
    python scripts/run_ablation.py --stage full --shard 0 --nshards 5 --jobs 4 --run-only   # Kaggle

Groups
  A  cumulative: black box -> +(a) feasibility -> +(b) decline cost -> +(c) charge nudges
  B  leave-one-out from the full module, and (c) alone
  C  lambda sweep for (b)
  D  information: SOC with telemetry noise, stale reports, coarse bands
  E  robustness: the same module on other black boxes (B2, B4c), full scale only
  F  driver behaviour: drivers who never decline for battery (F1), drivers who charge late (F2)
  G  form of G(F, B), the way the black-box cost F and the battery term are joined: add (default),
     mult, tiebreak, hard; each without (c) to isolate the matching effect, and with (c)
All runs use evaluation seeds 0-4; differences are paired by seed against each run's own
black box, with a paired t-test p-value (5 pairs). Runs already on disk are reused, so the script can be resumed.
Outputs: outputs/ablation/<stage>_table.csv, <stage>_table.md, <stage>_*.png
"""
import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import ttest_rel

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
OUT = ROOT / "outputs" / "ablation"

SCALE = {
    "small": ["n_vehicles=1000", "daily_requests=23333"],
    "full": [],
}
OFF = {"a": "addon_feasible=False", "b": "addon_reject=False", "c": "addon_nudge=False"}
LATE = ["soc_threshold_min=0.03", "soc_threshold_max=0.12"]  # drivers wait until 3-12 % to charge

# label, group, policy, extra --set overrides, black-box label it is compared with
CONFIGS = [
    ("black box (B1)", "A", "gsm_baseline", [], None),
    ("+ (a) feasibility", "A", "battery_addon", [OFF["b"], OFF["c"]], "black box (B1)"),
    ("+ (a)(b) decline cost", "A", "battery_addon", [OFF["c"]], "black box (B1)"),
    ("+ (a)(b)(c) full", "A", "battery_addon", [], "black box (B1)"),
    ("full without (a)", "B", "battery_addon", [OFF["a"]], "black box (B1)"),
    ("full without (b)", "B", "battery_addon", [OFF["b"]], "black box (B1)"),
    ("(c) nudges only", "B", "battery_addon", [OFF["a"], OFF["b"]], "black box (B1)"),
    ("lambda 0.5", "C", "battery_addon", ["addon_lambda=0.5"], "black box (B1)"),
    ("lambda 2", "C", "battery_addon", ["addon_lambda=2.0"], "black box (B1)"),
    ("lambda 4", "C", "battery_addon", ["addon_lambda=4.0"], "black box (B1)"),
    ("lambda 8", "C", "battery_addon", ["addon_lambda=8.0"], "black box (B1)"),
    ("SOC noise sd 5%", "D", "battery_addon", ["soc_info=noise"], "black box (B1)"),
    ("SOC reported every 5 min", "D", "battery_addon", ["soc_info=stale"], "black box (B1)"),
    ("SOC in 25% bands", "D", "battery_addon", ["soc_info=coarse"], "black box (B1)"),
    ("black box B2", "E", "gsm_fwd_repo", [], None),
    ("B2 + full module", "E", "battery_addon", ["addon_base=gsm_fwd_repo"], "black box B2"),
    ("black box B4c", "E", "b4_didi", ["didi_cancel_aware=True"], None),
    ("B4c + full module", "E", "battery_addon", ["addon_base=b4_didi", "didi_cancel_aware=True"], "black box B4c"),
    ("F1 black box, no battery declines", "F", "gsm_baseline", ["driver_soc_decline=False"], None),
    ("F1 + (a) feasibility", "F", "battery_addon", ["driver_soc_decline=False", OFF["b"], OFF["c"]],
     "F1 black box, no battery declines"),
    ("F1 + full module", "F", "battery_addon", ["driver_soc_decline=False"], "F1 black box, no battery declines"),
    ("F2 black box, late chargers", "F", "gsm_baseline", LATE, None),
    ("F2 + full module", "F", "battery_addon", LATE, "F2 black box, late chargers"),
]
for form in ["mult", "tiebreak", "hard"]:
    CONFIGS += [(f"G {form}, (a)(b)", "G", "battery_addon", [f"addon_form={form}", OFF["c"]], "black box (B1)"),
                (f"G {form}, full", "G", "battery_addon", [f"addon_form={form}"], "black box (B1)")]
STAGE_GROUPS = {"small": "ABCDFG", "full": "AE"}
# full-scale black boxes already run officially (same code, same seeds 0-4): reused, not rerun
REUSE = {
    ("full", "black box (B1)"): ROOT / "outputs" / "hanoi_full" / "gsm_baseline",
    ("full", "black box B2"): ROOT / "outputs" / "hanoi_full" / "gsm_fwd_repo",
    ("full", "black box B4c"): ROOT / "outputs" / "hanoi_full_b4c" / "b4_didi",
}

METRICS = [
    ("service_level", "Service level", 100, "{:+.2f} pt"),
    ("service_level_peak", "Service level (peak)", 100, "{:+.2f} pt"),
    ("wait_min_mean", "Wait mean (min)", 1, "{:+.2f}"),
    ("wait_min_p90", "Wait P90 (min)", 1, "{:+.2f}"),
    ("ride_reject_rate", "Decline rate", 100, "{:+.2f} pt"),
    ("ride_reject_soc_share", "Battery share of declines", 100, "{:+.1f} pt"),
    ("peak_share_charging", "Charging at peak", 100, "{:+.2f} pt"),
    ("charge_queue_min_mean", "Charger queue (min)", 1, "{:+.2f}"),
    ("strandings_per_day", "Run-outs/day", 1, "{:+.2f}"),
    ("energy_cost_vnd_day", "Energy cost (M VND/day)", 1e-6, "{:+.1f}"),
    ("profit_per_vehicle_day_vnd", "Profit/car/day (k VND)", 1e-3, "{:+.2f}"),
]


def tag_of(label, stage):
    slug = "".join(ch if ch.isalnum() else "_" for ch in label.lower()).strip("_")
    return f"abl_{stage}_{slug}"


def run_dir(label, policy, stage):
    return REUSE.get((stage, label), ROOT / "outputs" / f"hanoi_full_{tag_of(label, stage)}" / policy)


def no_reuse():
    """Run the black boxes too (e.g. on a machine whose random streams differ from the originals)."""
    REUSE.clear()


def todo(stage):
    """Configs of this stage that still have to run (not reused, not on disk), in a fixed order."""
    return [c for c in CONFIGS if c[1] in STAGE_GROUPS[stage] and (stage, c[0]) not in REUSE
            and not (run_dir(c[0], c[2], stage) / "summary_per_seed.csv").exists()]


def run(stage, shard, nshards, jobs):
    pending = todo(stage)
    mine = pending[shard::nshards]
    print(f"{len(pending)} configs to run; shard {shard}/{nshards} takes {[c[0] for c in mine]}", flush=True)
    for label, group, policy, extra, _ in mine:
        sets = SCALE[stage] + extra
        cmd = [PY, "run_baseline.py", "--scenario", "hanoi_full", "--seeds", "5", "--jobs", str(jobs),
               "--policies", policy, "--tag", tag_of(label, stage)] + (["--set", *sets] if sets else [])
        print(f"run: {label}", flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def summarize(stage):
    OUT.mkdir(parents=True, exist_ok=True)
    data = {}
    for label, group, policy, _, ref in CONFIGS:
        f = run_dir(label, policy, stage) / "summary_per_seed.csv"
        if group in STAGE_GROUPS[stage] and f.exists():
            data[label] = (group, ref, pd.read_csv(f).sort_values("seed").reset_index(drop=True))
    rows = []
    for label, (group, ref, df) in data.items():
        row = {"group": group, "config": label}
        for key, name, scale, fmt in METRICS:
            mean = df[key].mean() * scale
            if ref is None or ref not in data:
                row[name] = f"{mean:,.2f}"
            else:
                diff = (df[key] - data[ref][2][key]) * scale
                p = ttest_rel(df[key], data[ref][2][key]).pvalue if diff.std(ddof=1) > 0 else float("nan")
                row[name] = f"{mean:,.2f} ({fmt.format(diff.mean())} ± {diff.std(ddof=1):.2f}, p={p:.3f})"
        rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(OUT / f"{stage}_table.csv", index=False, encoding="utf-8-sig")
    (OUT / f"{stage}_table.md").write_text(table.to_markdown(index=False), encoding="utf-8")
    print(table.to_string(index=False))
    plot(stage, data)


def plot(stage, data):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def paired(label, key, scale):
        group, ref, df = data[label]
        d = (df[key] - data[ref][2][key]) * scale
        return d.mean(), d.std(ddof=1)

    show = [("service_level", "Service level (pt)", 100), ("wait_min_p90", "Wait P90 (min)", 1),
            ("ride_reject_soc_share", "Battery share of declines (pt)", 100),
            ("profit_per_vehicle_day_vnd", "Profit/car/day (k VND)", 1e-3)]
    labels = [l for l, (g, ref, _) in data.items() if ref is not None and g in "ABDEF"]
    if labels:
        fig, axes = plt.subplots(1, len(show), figsize=(4.2 * len(show), 0.45 * len(labels) + 1.6), sharey=True)
        for ax, (key, title, scale) in zip(axes, show):
            vals = [paired(l, key, scale) for l in labels]
            ax.barh(labels, [v[0] for v in vals], xerr=[v[1] for v in vals], color="#4c78a8", capsize=3)
            ax.axvline(0, color="#333", lw=0.8)
            ax.set_title(title, fontsize=10)
        axes[0].invert_yaxis()
        fig.suptitle(f"Battery module vs black box (paired by seed, mean ± sd) - {stage}", fontsize=11)
        fig.tight_layout()
        fig.savefig(OUT / f"{stage}_components.png", dpi=150)
    lam = [(0.5, "lambda 0.5"), (1.0, "+ (a)(b)(c) full"), (2.0, "lambda 2"), (4.0, "lambda 4"), (8.0, "lambda 8")]
    lam = [(x, l) for x, l in lam if l in data]
    if len(lam) > 2:
        fig, axes = plt.subplots(1, len(show), figsize=(4.2 * len(show), 3.2))
        for ax, (key, title, scale) in zip(axes, show):
            v = [paired(l, key, scale) for _, l in lam]
            ax.errorbar([x for x, _ in lam], [m for m, _ in v], yerr=[s for _, s in v], marker="o", capsize=3)
            ax.axhline(0, color="#333", lw=0.8)
            ax.set_xscale("log", base=2)
            ax.set_xlabel("lambda")
            ax.set_title(title, fontsize=10)
        fig.suptitle(f"Sensitivity to lambda (difference vs black box) - {stage}", fontsize=11)
        fig.tight_layout()
        fig.savefig(OUT / f"{stage}_lambda.png", dpi=150)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=STAGE_GROUPS, required=True)
    ap.add_argument("--summarize-only", action="store_true")
    ap.add_argument("--run-only", action="store_true", help="skip the summary (e.g. one Kaggle shard)")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=5)
    ap.add_argument("--no-reuse", action="store_true", help="also run the black-box configs")
    args = ap.parse_args()
    if args.no_reuse:
        no_reuse()
    if not args.summarize_only:
        run(args.stage, args.shard, args.nshards, args.jobs)
    if not args.run_only:
        summarize(args.stage)


if __name__ == "__main__":
    main()
