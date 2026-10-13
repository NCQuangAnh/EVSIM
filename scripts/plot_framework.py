"""Draw the battery framework (battery layer + interface levels of the dispatch rule).

    .venv/Scripts/python scripts/plot_framework.py      -> docs/figures/battery_framework.png
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent / "docs" / "figures" / "battery_framework.png"
INK, MUTED = "#1f2937", "#4b5563"
DATA, LAYER, MATCH, CHARGE, BOX, SOLVER, GUAR = ("#f3f4f6", "#fef3c7", "#fde68a", "#bbf7d0", "#d1d5db",
                                                 "#bfdbfe", "#ede9fe")
LEVEL = ["#e5e7eb", "#d1d5db", "#9ca3af", "#6b7280"]


def box(ax, x, y, w, h, title, lines, fill, edge="#374151", dashed=False, size=8.6, title_size=10.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",
                                fc=fill, ec=edge, lw=1.3, ls="--" if dashed else "-"))
    if title:
        ax.text(x + w / 2, y + h - 0.018, title, ha="center", va="top", fontsize=title_size,
                fontweight="bold", color=INK)
    for i, line in enumerate(lines):
        ax.text(x + 0.012, y + h - (0.058 if title else 0.022) - i * 0.03, line, ha="left", va="top",
                fontsize=size, color=MUTED)


def arrow(ax, a, b, color="#374151", style="-|>", ls="-"):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=13, lw=1.3, color=color, ls=ls))


def main():
    fig, ax = plt.subplots(figsize=(17.5, 9.6), dpi=160)
    ax.set_xlim(0, 1.76)
    ax.set_ylim(0, 0.96)
    ax.axis("off")
    ax.text(0.85, 0.95, "Framework pin: lớp pin bọc quanh luật dispatch có sẵn, mức giao diện càng cao thì càng làm được nhiều",
            ha="center", va="top", fontsize=13.5, fontweight="bold", color=INK)

    # ---- inputs from the platform ----
    box(ax, 0.01, 0.40, 0.25, 0.47, "Nền tảng cung cấp",
        ["• SOC từng xe (telemetry):", "  đủ khi nhiễu 5%, báo 5 phút,", "  hoặc theo dải 25%",
         "• Mô hình năng lượng:", "  kWh/km, dung lượng pin",
         "• Danh sách trạm sạc", "  + cổng trống (V-Green)",
         "• Log tài xế: nhận/từ chối cuốc", "  kèm SOC; có làm theo nhắc sạc",
         "• Dự báo nhu cầu (nếu có)"], DATA)

    # ---- battery layer ----
    ax.add_patch(FancyBboxPatch((0.30, 0.18), 0.66, 0.69, boxstyle="round,pad=0.006,rounding_size=0.015",
                                fc=LAYER, ec="#b45309", lw=1.8))
    ax.text(0.63, 0.86, "Lớp pin (battery layer)", ha="center", va="top", fontsize=12, fontweight="bold", color="#92400e")
    box(ax, 0.32, 0.66, 0.62, 0.15, "Ước lượng",
        ["SOC sau chuyến = SOC lúc rảnh − (km đón + km chở) × kWh/km",
         "p̂(từ chối | SOC sau, km đón, km chở): logistic, kiểm tra calibration",
         "q_pin = p̂(SOC thật) − p̂(cùng cặp, pin cao);   s_F = IQR của F trong batch"], "#fffbeb",
        size=8.4)
    box(ax, 0.32, 0.21, 0.30, 0.42, "Can thiệp vào ghép (G)",
        ["(a) Mặt nạ an toàn: G = ∞ nếu sau", "     chuyến không tới được trạm nào",
         "(a') Phạt mềm khi biên dự trữ thấp",
         "(b) Rủi ro từ chối: + λ·s_F·q_pin",
         "(d) Thưởng trả khách gần trạm còn", "     cổng trống, cho xe sắp pin thấp",
         "(e) Ưu tiên xe pin cao trước cao", "     điểm (khi thừa xe)",
         "", "G = F khi pin không là vấn đề"], MATCH)
    box(ax, 0.64, 0.21, 0.30, 0.42, "Hành động sạc (ngoài G)",
        ["(c) Nhắc sạc xe rảnh theo giờ:", "     <50% trước cao điểm, <15% trong,",
         "     <30% giờ khác",
         "     • tài xế làm theo với xác suất p", "     • bỏ qua khi các trạm gần đều đầy",
         "     • tài xế tự chọn trạm",
         "(c') Sạc theo giá trị: nhắc khi giá trị", "     của xe trên đường thấp nhất (V,",
         "     dự báo nhu cầu)"], CHARGE)

    # ---- dispatch rule with interface levels ----
    box(ax, 1.00, 0.40, 0.36, 0.47, "Luật dispatch (black box)", [], BOX, dashed=True)
    levels = [("L0", "Chỉ danh sách cặp đã ghép", "→ chặn cặp không an toàn, (c)"),
              ("L1", "Ma trận cost F; solver nhận G", "→ (a), (a'), (b), (e)"),
              ("L2", "Ứng viên forward, trạng thái", "→ (d), SOC chính xác, phối hợp (c)"),
              ("L3", "Hàm giá trị V / dự báo", "→ (c') sạc theo giá trị")]
    for k, (lv, what, gets) in enumerate(levels):
        y = 0.43 + k * 0.095
        ax.add_patch(FancyBboxPatch((1.015, y), 0.33, 0.08, boxstyle="round,pad=0.004,rounding_size=0.008",
                                    fc=LEVEL[k], ec="#374151", lw=1.0))
        ax.text(1.025, y + 0.066, lv, fontsize=10, fontweight="bold", color="white" if k >= 2 else INK, va="top")
        ax.text(1.06, y + 0.066, what, fontsize=8.4, color="white" if k >= 2 else INK, va="top")
        ax.text(1.06, y + 0.034, gets, fontsize=8.4, color="white" if k >= 2 else INK, va="top", style="italic")
    ax.text(1.18, 0.412, "mức cao bao gồm mức thấp", ha="center", fontsize=8, color=MUTED, style="italic")
    box(ax, 1.40, 0.66, 0.35, 0.21, "Black box trong mô phỏng",
        ["B0 greedy (L0/L1)  ·  B1 GSM (L1)", "B2-F, B2-R, B2 (L2)  ·  B6 giá trị tức thời (L1)",
         "B4c kiểu DiDi (L3)"], DATA, size=8.3)

    # ---- matching and feedback ----
    box(ax, 1.40, 0.40, 0.35, 0.22, "Ghép & gửi cuốc (mỗi 30 giây)",
        ["Hungarian trên G", "→ gửi cuốc → tài xế nhận/từ chối", "→ khách bị từ chối vào vòng sau"], SOLVER)

    # ---- guarantees ----
    box(ax, 0.30, 0.02, 1.45, 0.12, "Cam kết của lớp pin với luật dispatch",
        ["1) Trung lập: G = F khi pin không là vấn đề     2) Giữ thứ hạng: G tăng theo F     3) Bất biến khi F → aF + b (đã có unit test)",
         "4) Cấm cứng chỉ khi thật sự không an toàn     5) Nhắc sạc là gợi ý: tài xế có thể bỏ qua và tự chọn trạm"], GUAR, size=8.8)
    box(ax, 0.01, 0.02, 0.25, 0.33, "Đánh giá",
        ["• Ablation từng thành phần", "• Ablation theo mức L0 → L3", "  (kỳ vọng lợi ích tăng dần)",
         "• 7 black box, CRN, seed dev", "  300–319 / đánh giá 1000–1019",
         "• Không kém hơn: biên 0,1 pt", "  service, 2.000 đ/xe/ngày", "• OOD: nhu cầu, trạm, tiêu hao"], DATA, size=8.3)

    # ---- arrows ----
    arrow(ax, (0.26, 0.74), (0.32, 0.74))
    arrow(ax, (0.26, 0.50), (0.32, 0.50))
    arrow(ax, (0.47, 0.66), (0.47, 0.63))
    arrow(ax, (0.79, 0.66), (0.79, 0.63))
    arrow(ax, (1.015, 0.51), (0.94, 0.51), color="#6b7280")
    ax.text(1.18, 0.812, "← cung cấp F, ứng viên, V cho lớp pin", ha="center", fontsize=8.2, color=MUTED,
            style="italic")
    orange, green, grey = "#b45309", "#15803d", "#6b7280"
    # G and mask: from the matching box of the layer, under the charging box, up into the solver
    ax.plot([0.47, 0.47, 1.47], [0.21, 0.196, 0.196], color=orange, lw=1.4)
    arrow(ax, (1.47, 0.196), (1.47, 0.40), color=orange)
    ax.text(1.20, 0.201, "G và mặt nạ cấm", ha="center", fontsize=8.6, color=orange)
    # cars withdrawn to charge
    ax.plot([0.94, 1.62], [0.30, 0.30], color=green, lw=1.3, ls="--")
    arrow(ax, (1.62, 0.30), (1.62, 0.40), color=green, ls="--")
    ax.text(1.20, 0.305, "xe được rút đi sạc (không nhận cuốc)", ha="center", fontsize=8.6, color=green)
    # feedback: offer outcomes back to the platform data
    ax.plot([1.70, 1.70, 0.28, 0.28], [0.40, 0.158, 0.158, 0.60], color=grey, lw=1.1, ls="--")
    arrow(ax, (0.28, 0.60), (0.26, 0.60), color=grey, ls="--")
    ax.text(1.33, 0.163, "phản hồi: log nhận/từ chối, làm theo nhắc sạc → fit lại p̂, ước lượng p",
            fontsize=8.2, color=MUTED, ha="center")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    print("saved", OUT)


if __name__ == "__main__":
    main()
