"""Draw the 'black box + battery module' pipeline figure for the mentor document.

    .venv/Scripts/python scripts/plot_pipeline.py      -> docs/figures/pipeline_battery_addon.png
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent / "docs" / "figures" / "pipeline_battery_addon.png"
INK, MUTED = "#1f2937", "#4b5563"
BLACKBOX, BATTERY, SOLVER, NUDGE, DATA = "#d1d5db", "#fde68a", "#bfdbfe", "#bbf7d0", "#f3f4f6"


def box(ax, x, y, w, h, title, lines, fill, edge="#374151", dashed=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.008,rounding_size=0.015",
                                fc=fill, ec=edge, lw=1.4, ls="--" if dashed else "-"))
    ax.text(x + w / 2, y + h - 0.025, title, ha="center", va="top", fontsize=10.5, fontweight="bold", color=INK)
    for i, line in enumerate(lines):
        ax.text(x + 0.014, y + h - 0.075 - i * 0.036, line, ha="left", va="top", fontsize=8.4, color=MUTED)


def arrow(ax, a, b, color="#374151"):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=14, lw=1.4, color=color))


def main():
    fig, ax = plt.subplots(figsize=(16, 6.6), dpi=170)
    ax.set_xlim(0, 1.62)
    ax.set_ylim(0, 0.74)
    ax.axis("off")
    ax.text(0.81, 0.725, "Black box + module pin: thông tin pin chỉ được cộng thêm vào hàm cost hiện tại của GSM",
            ha="center", va="top", fontsize=13, fontweight="bold", color=INK)

    box(ax, 0.01, 0.26, 0.24, 0.36, "Đầu vào mỗi 30 giây",
        ["• Xe rảnh / sắp rảnh", "• Khách đang chờ", "• SOC từng xe (telemetry),",
         "  có thể nhiễu / trễ / thô"], DATA)
    box(ax, 0.30, 0.42, 0.31, 0.20, "C^GSM (black box)",
        ["Hàm cost GSM hiện tại, giữ nguyên.", "Trong mô phỏng: bản xấp xỉ B1",
         "(quãng đón + rủi ro huỷ + ...)"], BLACKBOX, dashed=True)
    box(ax, 0.30, 0.04, 0.31, 0.34, "Module pin (cộng thêm)",
        ["(a) Ràng buộc: cấm cặp i–j nếu sau", "     chuyến không đủ pin tới trạm",
         "     gần nhất (dự phòng 5%)", "(b) λ · ΔP_từ chối(SOC sau chuyến):",
         "     phần từ chối tăng thêm do pin,", "     fit từ log nhận/từ chối cuốc"], BATTERY)
    ax.text(0.645, 0.33, "+", fontsize=26, ha="center", va="center", color=INK)
    box(ax, 0.68, 0.18, 0.22, 0.30, "C'_ij → Hungarian",
        ["C' = C^GSM + λ·ΔP", "C' = ∞ nếu vi phạm (a)", "", "min Σ C'_ij · x_ij"], SOLVER)
    box(ax, 0.94, 0.18, 0.20, 0.30, "Ghép & gửi cuốc",
        ["Mỗi xe ≤ 1 khách,", "mỗi khách ≤ 1 xe;", "tài xế nhận", "hoặc từ chối"], SOLVER)
    box(ax, 1.19, 0.30, 0.42, 0.32, "(c) Nhắc sạc đúng giờ (mỗi 5 phút)",
        ["Xe đang rảnh, SOC dưới mức theo giờ:", "• trước cao điểm (6–7h, 15h30–17h): < 50%",
         "• trong cao điểm: < 15%   • giờ khác: < 30%", "→ gợi ý đi sạc ngay (không đổi C')"], NUDGE)
    box(ax, 1.19, 0.04, 0.42, 0.22, "Đánh giá (ablation)",
        ["Bật/tắt (a)(b)(c), quét λ, chất lượng SOC,", "3 black box, hành vi tài xế;",
         "so theo cặp seed 0–4, kèm p-value"], DATA)

    arrow(ax, (0.25, 0.52), (0.30, 0.52))
    arrow(ax, (0.25, 0.32), (0.30, 0.26))
    arrow(ax, (0.61, 0.52), (0.68, 0.42))
    arrow(ax, (0.61, 0.20), (0.68, 0.26))
    arrow(ax, (0.90, 0.33), (0.94, 0.33))
    green = "#15803d"
    ax.plot([0.13, 0.13, 1.40], [0.62, 0.665, 0.665], color=green, lw=1.4)
    arrow(ax, (1.40, 0.665), (1.40, 0.62), color=green)
    ax.text(0.75, 0.675, "SOC của xe đang rảnh", ha="center", fontsize=8.4, color=green)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    print("saved", OUT)


if __name__ == "__main__":
    main()
