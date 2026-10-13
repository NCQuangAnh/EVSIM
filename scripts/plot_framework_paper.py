"""Paper-style figure of the battery framework (final design v2.1 / v2.2).

    .venv/Scripts/python scripts/plot_framework_paper.py
        -> docs/figures/battery_framework_paper.png / .pdf

Style follows the reference figures the user collected (stage panels with tinted backgrounds,
circled step numbers, a frozen black box, maths in the boxes, legend at the bottom).
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Arc, Circle, FancyArrowPatch, FancyBboxPatch, Rectangle

OUT = Path(__file__).resolve().parent.parent / "docs" / "figures" / "battery_framework_paper"
plt.rcParams.update({"font.family": "DejaVu Sans", "mathtext.fontset": "cm"})
INK, MUTED = "#1f2433", "#565d6e"
BLUE, BLUE_L = "#2f5fb3", "#e8effb"
ORANGE, ORANGE_L = "#d9772b", "#fdf1e6"
GREEN, GREEN_L = "#2e8b57", "#eaf6ee"
GREY_L = "#eef0f3"
RED = "#d64545"


def panel(ax, x, y, w, h, fill, edge, title, title_color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.018",
                                fc=fill, ec=edge, lw=1.6, ls=(0, (5, 3))))
    ax.text(x + 0.012, y + h - 0.02, title, fontsize=12.5, fontweight="bold", style="italic", color=title_color,
            va="top")


def box(ax, x, y, w, h, fill="white", edge=INK, lw=1.3, dashed=False, r=0.012):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.003,rounding_size={r}",
                                fc=fill, ec=edge, lw=lw, ls=(0, (4, 2)) if dashed else "-"))


def step(ax, x, y, n, color=INK):
    ax.add_patch(Circle((x, y), 0.0125, fc="white", ec=color, lw=1.3, zorder=5))
    ax.text(x, y - 0.001, str(n), ha="center", va="center", fontsize=9.5, fontweight="bold", color=color, zorder=6)


def arrow(ax, a, b, color=INK, dashed=False, lw=1.4, rad=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=13, lw=lw, color=color,
                                 ls=(0, (4, 2.5)) if dashed else "-", connectionstyle=f"arc3,rad={rad}"))


def battery(ax, x, y, level, w=0.022, h=0.011):
    color = RED if level < 0.2 else ORANGE if level < 0.4 else "#e0b030" if level < 0.6 else GREEN
    ax.add_patch(Rectangle((x, y), w, h, fc="white", ec=INK, lw=0.9))
    ax.add_patch(Rectangle((x + w, y + h * 0.3), w * 0.12, h * 0.4, fc=INK, ec=INK, lw=0))
    ax.add_patch(Rectangle((x + 0.0015, y + 0.0015), (w - 0.003) * level, h - 0.003, fc=color, lw=0))


def car(ax, x, y, color="#6b8fd6", s=1.0):
    ax.add_patch(FancyBboxPatch((x, y), 0.03 * s, 0.012 * s, boxstyle="round,pad=0.001,rounding_size=0.004",
                                fc=color, ec=INK, lw=0.9))
    ax.add_patch(FancyBboxPatch((x + 0.006 * s, y + 0.011 * s), 0.017 * s, 0.008 * s,
                                boxstyle="round,pad=0.001,rounding_size=0.003", fc=color, ec=INK, lw=0.9))
    for dx in (0.007, 0.023):
        ax.add_patch(Circle((x + dx * s, y), 0.0035 * s, fc=INK, ec=INK))


def person(ax, x, y, color="#8a63d2"):
    ax.add_patch(Circle((x, y + 0.017), 0.0055, fc=color, ec=INK, lw=0.8))
    ax.add_patch(FancyBboxPatch((x - 0.007, y), 0.014, 0.01, boxstyle="round,pad=0.001,rounding_size=0.005",
                                fc=color, ec=INK, lw=0.8))


def charger(ax, x, y):
    ax.add_patch(FancyBboxPatch((x, y), 0.018, 0.03, boxstyle="round,pad=0.001,rounding_size=0.003",
                                fc=GREEN, ec=INK, lw=0.9))
    ax.plot([x + 0.011, x + 0.006, x + 0.010, x + 0.007], [y + 0.025, y + 0.015, y + 0.015, y + 0.005],
            color="white", lw=1.6)


def lock(ax, x, y, s=1.0):
    ax.add_patch(Arc((x, y + 0.012 * s), 0.016 * s, 0.022 * s, theta1=0, theta2=180, color=INK, lw=1.6))
    ax.add_patch(FancyBboxPatch((x - 0.011 * s, y - 0.004 * s), 0.022 * s, 0.016 * s,
                                boxstyle="round,pad=0.001,rounding_size=0.003", fc="#9aa3b5", ec=INK, lw=1.0))


def main():
    fig, ax = plt.subplots(figsize=(22, 10.9), dpi=170)
    ax.set_xlim(0, 1.7)
    ax.set_ylim(0, 0.84)
    ax.axis("off")

    # ------------------------------------------------------------------ platform state
    panel(ax, 0.01, 0.30, 0.235, 0.52, GREY_L, "#8a93a6", "Platform state", MUTED)
    ax.text(0.025, 0.775, "refreshed every 30 s", fontsize=8.5, color=MUTED, style="italic")
    ax.text(0.025, 0.735, "Idle / soon-free cars", fontsize=10, color=INK)
    for k, (lvl, dy) in enumerate([(0.85, 0), (0.55, -0.045), (0.32, -0.09), (0.14, -0.135)]):
        car(ax, 0.03, 0.69 + dy)
        battery(ax, 0.072, 0.692 + dy, lvl)
        ax.text(0.106, 0.697 + dy, f"SOC$_{{{k + 1}}}$={int(lvl * 100)}%", fontsize=8.5, color=MUTED, va="center")
    ax.text(0.025, 0.505, "Waiting riders", fontsize=10, color=INK)
    for k in range(4):
        person(ax, 0.04 + k * 0.038, 0.46)
    ax.text(0.025, 0.43, "origin, destination, trip km", fontsize=8.5, color=MUTED)
    ax.text(0.025, 0.39, "Chargers", fontsize=10, color=INK)
    for k in range(3):
        charger(ax, 0.035 + k * 0.03, 0.335)
    ax.text(0.135, 0.35, "free ports,\nqueues", fontsize=8.5, color=MUTED)

    # ------------------------------------------------------------------ dispatch path (centre)
    panel(ax, 0.265, 0.30, 0.86, 0.52, BLUE_L, BLUE, "Battery layer (inside every matching round)", BLUE)

    # frozen black box
    box(ax, 0.282, 0.585, 0.218, 0.16, fill="#dfe3ea", edge=INK, lw=1.6)
    lock(ax, 0.485, 0.722, 0.8)
    ax.text(0.385, 0.715, "Black-box dispatch", ha="center", fontsize=10.5, fontweight="bold", color=INK)
    ax.text(0.385, 0.683, "(company's cost, unchanged)", ha="center", fontsize=8.4, color=MUTED, style="italic")
    ax.text(0.385, 0.635, r"$F_{ij}$" + ": cost of car $i$ for rider $j$", ha="center", fontsize=9.6, color=INK)
    ax.text(0.385, 0.602, "values only, any units", ha="center", fontsize=8.3, color=MUTED)

    # (1) SOC after the trip
    box(ax, 0.52, 0.64, 0.25, 0.105, edge=BLUE)
    step(ax, 0.535, 0.728, 1, BLUE)
    ax.text(0.553, 0.728, "Energy budget", fontsize=10.5, fontweight="bold", va="center", color=INK)
    ax.text(0.53, 0.686, r"$\mathrm{SOC}^{\,\mathrm{after}}_{ij}=\mathrm{SOC}_i-\frac{e\,(d^{\,\mathrm{pick}}_{ij}+d^{\,\mathrm{trip}}_{j})}{B}$",
            fontsize=11.5, color=INK, va="center")
    ax.text(0.53, 0.652, "forward cars: SOC when they become free", fontsize=8.2, color=MUTED)

    # (2) safety mask
    box(ax, 0.52, 0.505, 0.25, 0.115, edge=RED)
    step(ax, 0.535, 0.603, 2, RED)
    ax.text(0.553, 0.603, "Safety mask (a)", fontsize=10.5, fontweight="bold", va="center", color=INK)
    ax.text(0.53, 0.562, r"$G_{ij}=\infty$  if  $\mathrm{SOC}^{\,\mathrm{after}}_{ij}-\frac{e\,d^{\,\mathrm{chg}}_{j}}{B}<r$",
            fontsize=11.5, color=INK, va="center")
    ax.text(0.53, 0.522, r"$d^{\,\mathrm{chg}}_j$: to the nearest charger,  $r=5\%$", fontsize=8.4, color=MUTED)

    # (3) decline-risk term
    box(ax, 0.79, 0.565, 0.31, 0.18, edge=BLUE)
    step(ax, 0.805, 0.728, 3, BLUE)
    ax.text(0.823, 0.728, "Decline-risk term (b), scale-free", fontsize=10.5, fontweight="bold", va="center", color=INK)
    ax.text(0.80, 0.684, r"$G_{ij}=F_{ij}+\lambda\, s_F\, q\!\left(\mathrm{SOC}^{\,\mathrm{after}}_{ij}\right)$",
            fontsize=12.5, color=INK, va="center")
    ax.text(0.80, 0.645, r"$s_F=\mathrm{IQR}(F)$ of the batch: invariant to $F\to aF+b$",
            fontsize=8.6, color=MUTED, va="center")
    ax.text(0.80, 0.617, r"$q$: extra decline prob. due to battery,  $\lambda=0.5$",
            fontsize=8.6, color=MUTED, va="center")
    # mini curve q(SOC_after)
    xs = np.linspace(0, 1, 60)
    qx, qy, qw, qh = 1.02, 0.575, 0.07, 0.025
    curve = 0.9 / (1 + np.exp((xs - 0.2) / 0.04))
    ax.plot(qx + xs * qw, qy + curve / 0.9 * qh, color=BLUE, lw=1.5)
    ax.plot([qx, qx + qw], [qy, qy], color=MUTED, lw=0.8)
    ax.text(qx + qw, qy - 0.012, r"SOC$^{\mathrm{after}}$", fontsize=7.5, color=MUTED, ha="right")
    ax.text(qx, qy + qh + 0.004, "$q$", fontsize=8, color=BLUE)

    # solver and offers
    box(ax, 0.282, 0.335, 0.218, 0.17, fill="#dfe3ea", edge=INK, lw=1.6)
    lock(ax, 0.485, 0.482, 0.8)
    ax.text(0.395, 0.474, "Black-box solver", ha="center", fontsize=10.5, fontweight="bold", color=INK)
    ax.text(0.385, 0.432, r"$\min_x\ \sum_{ij} G_{ij}\,x_{ij}$", ha="center", fontsize=12, color=INK)
    ax.text(0.385, 0.398, "(Hungarian, greedy, ...)", ha="center", fontsize=8.5, color=MUTED, style="italic")
    ax.text(0.385, 0.356, "offers → drivers accept / decline", ha="center", fontsize=8.6, color=INK)
    step(ax, 0.298, 0.488, 4, INK)

    arrow(ax, (0.245, 0.62), (0.282, 0.66))
    ax.plot([0.43, 0.43, 0.95], [0.745, 0.768, 0.768], color=BLUE, lw=1.4)
    arrow(ax, (0.95, 0.768), (0.95, 0.745), color=BLUE)
    ax.text(0.80, 0.774, r"$F_{ij}$ (black-box cost)", fontsize=10.5, color=BLUE, ha="center")
    arrow(ax, (0.645, 0.64), (0.645, 0.62), color=BLUE)
    arrow(ax, (0.77, 0.69), (0.79, 0.69), color=BLUE)
    arrow(ax, (0.945, 0.565), (0.50, 0.44), color=BLUE, rad=-0.12)
    ax.text(0.79, 0.47, r"$G_{ij}$ + mask", fontsize=11, color=BLUE, ha="center")
    arrow(ax, (0.52, 0.525), (0.50, 0.47), color=RED)

    # ------------------------------------------------------------------ charging coordination
    panel(ax, 0.265, 0.02, 0.86, 0.255, GREEN_L, GREEN, "Charging coordination (every 5 min, outside the matching)", GREEN)
    box(ax, 0.29, 0.045, 0.30, 0.18, edge=GREEN)
    step(ax, 0.305, 0.208, 5, GREEN)
    ax.text(0.323, 0.208, "Time-of-day charge nudges (c)", fontsize=10.5, fontweight="bold", va="center", color=INK)
    # mini schedule: nudge level by hour
    hx, hy, hw, hh = 0.30, 0.065, 0.27, 0.105
    hours = np.array([0, 4.5, 7, 9, 14.5, 17, 19, 24])
    lev = np.array([0.30, 0.70, 0.15, 0.30, 0.70, 0.15, 0.30, 0.30])
    for a, b, v in zip(hours[:-1], hours[1:], lev[:-1]):
        c = GREEN if v == 0.7 else ORANGE if v == 0.15 else "#9fb6a5"
        ax.add_patch(Rectangle((hx + a / 24 * hw, hy), (b - a) / 24 * hw, v * hh, fc=c, ec="white", lw=0.6))
    ax.plot([hx, hx + hw], [hy, hy], color=INK, lw=0.8)
    for hr in (0, 6, 12, 18, 24):
        ax.text(hx + hr / 24 * hw, hy - 0.016, f"{hr}h", fontsize=7.5, color=MUTED, ha="center")
    ax.text(hx + 5.75 / 24 * hw, hy + 0.72 * hh, "70%", fontsize=8, color=GREEN, ha="center", fontweight="bold")
    ax.text(hx + 15.75 / 24 * hw, hy + 0.72 * hh, "70%", fontsize=8, color=GREEN, ha="center", fontweight="bold")
    ax.text(hx + 8 / 24 * hw, hy + 0.17 * hh, "15%", fontsize=7.5, color=ORANGE, ha="center")
    ax.text(hx + 18 / 24 * hw, hy + 0.17 * hh, "15%", fontsize=7.5, color=ORANGE, ha="center")
    ax.text(hx + 11.7 / 24 * hw, hy + 0.33 * hh, "30%", fontsize=7.5, color=MUTED, ha="center")
    ax.text(hx + hw, hy + hh + 0.004, "nudge an idle car if SOC < level", fontsize=7.8, color=MUTED, ha="right")

    box(ax, 0.61, 0.135, 0.24, 0.09, edge=GREEN)
    step(ax, 0.625, 0.208, 6, GREEN)
    ax.text(0.643, 0.208, "Supply gate (v2.2)", fontsize=10.5, fontweight="bold", va="center", color=INK)
    ax.text(0.62, 0.172, "extra pre-peak nudges per round", fontsize=8.6, color=MUTED, va="center")
    ax.text(0.62, 0.147, r"$\leq 0.5\,(N^{\mathrm{idle}}-N^{\mathrm{wait}})$, lowest SOC first", fontsize=9.2,
            color=INK, va="center")
    box(ax, 0.61, 0.045, 0.24, 0.075, edge=RED)
    step(ax, 0.625, 0.103, 7, RED)
    ax.text(0.643, 0.103, "Mask-triggered nudge", fontsize=10.5, fontweight="bold", va="center", color=INK)
    ax.text(0.62, 0.066, "cars shut out by ② are sent to charge", fontsize=8.6, color=MUTED, va="center")

    box(ax, 0.885, 0.045, 0.225, 0.18, edge=GREEN, dashed=True)
    ax.text(0.9975, 0.2, "Drivers (not controlled)", fontsize=10.5, fontweight="bold", ha="center", color=INK)
    person(ax, 0.905, 0.135, color="#7fb08f")
    ax.text(0.922, 0.158, r"follow a nudge with prob. $p_i$", fontsize=8.3, color=INK)
    ax.text(0.922, 0.130, "choose the station themselves", fontsize=8.3, color=INK)
    ax.text(0.922, 0.102, "decline rides when SOC is low", fontsize=8.3, color=INK)
    ax.text(0.897, 0.062, "the layer suggests, never forces", fontsize=8, color=MUTED, style="italic")
    arrow(ax, (0.59, 0.135), (0.61, 0.165), color=GREEN)
    arrow(ax, (0.85, 0.18), (0.885, 0.16), color=GREEN)
    arrow(ax, (0.85, 0.083), (0.885, 0.11), color=GREEN)
    ax.plot([0.765, 0.867, 0.867], [0.505, 0.505, 0.083], color=RED, lw=1.1, ls=(0, (4, 2.5)))
    arrow(ax, (0.867, 0.083), (0.85, 0.083), color=RED, dashed=True, lw=1.1)
    arrow(ax, (0.15, 0.30), (0.29, 0.15), color=GREEN, dashed=True, rad=0.15)
    ax.text(0.06, 0.215, "SOC, time,\nfree ports", fontsize=8.5, color=GREEN)

    # ------------------------------------------------------------------ guarantees + evidence (right)
    panel(ax, 1.145, 0.30, 0.545, 0.52, ORANGE_L, ORANGE, "Guarantees to the black box", ORANGE)
    rows = [("Neutral", r"$G=F$ when every car is well charged"),
            ("Order-preserving", r"$G$ increases with $F$"),
            ("Scale-free", r"same matching for $F\to aF+b$ (unit test)"),
            ("Hard only for safety", "forbid only unreachable chargers"),
            ("Minimum interface", "L0: solved pairs + SOC + nudge channel"),
            ]
    for k, (a, b) in enumerate(rows):
        y = 0.735 - k * 0.058
        ax.text(1.165, y, "✓", fontsize=13, color=GREEN, va="center", fontweight="bold")
        ax.text(1.19, y + 0.006, a, fontsize=10, fontweight="bold", color=INK, va="center")
        ax.text(1.19, y - 0.019, b, fontsize=8.8, color=MUTED, va="center")
    box(ax, 1.16, 0.315, 0.515, 0.115, fill="white", edge=ORANGE)
    ax.text(1.175, 0.41, "Evaluation (simulation, Hanoi, 5,080 cars, 20 fresh seeds)", fontsize=9.5, fontweight="bold", color=INK,
            va="center")
    ax.text(1.175, 0.377, r"7 black boxes, all non-inferior (Holm);  mean gain $+0.56$ pt service,", fontsize=9, color=INK,
            va="center")
    ax.text(1.175, 0.350, r"$+8.3$k VND/car/day;  demand $+20\%$: $+0.56$ pt, $+10.3$k;  100% of seeds", fontsize=9,
            color=INK, va="center")
    ax.text(1.175, 0.325, "ablation: almost all gain comes from ⑤; ①–③ add safety (run-outs → 0)", fontsize=8.4,
            color=MUTED, va="center")

    # ------------------------------------------------------------------ legend
    lx, ly = 1.145, 0.02
    box(ax, lx, ly, 0.545, 0.255, fill="white", edge="#c4c9d4")
    ax.text(lx + 0.015, ly + 0.23, "Legend", fontsize=10, fontweight="bold", color=INK, va="center")
    lock(ax, lx + 0.03, ly + 0.185, 0.8)
    ax.text(lx + 0.05, ly + 0.188, "frozen: the company's dispatch, not modified", fontsize=8.8, color=INK, va="center")
    ax.plot([lx + 0.018, lx + 0.042], [ly + 0.148, ly + 0.148], color=BLUE, lw=1.4)
    ax.text(lx + 0.05, ly + 0.148, "data passed to the solver", fontsize=8.8, color=INK, va="center")
    ax.plot([lx + 0.018, lx + 0.042], [ly + 0.113, ly + 0.113], color=GREEN, lw=1.4, ls=(0, (4, 2.5)))
    ax.text(lx + 0.05, ly + 0.113, "information read by the charging coordinator", fontsize=8.8, color=INK, va="center")
    battery(ax, lx + 0.02, ly + 0.072, 0.7)
    ax.text(lx + 0.05, ly + 0.078, "state of charge (SOC)", fontsize=8.8, color=INK, va="center")
    step(ax, lx + 0.03, ly + 0.04, 1, BLUE)
    ax.text(lx + 0.05, ly + 0.04, "steps: ①–④ each matching round, ⑤–⑦ every 5 min", fontsize=8.8, color=INK, va="center")
    ax.text(lx + 0.36, ly + 0.188, r"$e$: kWh/km,  $B$: battery kWh", fontsize=8.6, color=MUTED, va="center")
    ax.text(lx + 0.36, ly + 0.148, r"$d$: road distance (km)", fontsize=8.6, color=MUTED, va="center")
    ax.text(lx + 0.36, ly + 0.113, r"$x_{ij}\in\{0,1\}$: car $i$ ↔ rider $j$", fontsize=8.6, color=MUTED, va="center")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT.with_suffix(".png"), bbox_inches="tight", facecolor="white")
    fig.savefig(OUT.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    print("saved", OUT.with_suffix(".png"))


if __name__ == "__main__":
    main()
