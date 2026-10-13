"""Scientific figure of the battery framework, in the style of the baseline figure
(so_do_pipeline_ghep_xe_khach.svg): stage panels, numbered steps, outline icons, worked example.

    .venv/Scripts/python scripts/make_framework_svg.py
        -> docs/figures/battery_framework.svg and battery_framework.html

Worked example (computed with the simulator's rules, scripts/make_framework_svg.py prints it):
the baseline matrix C of the baseline figure; cars v1, v2, v3 at 80 / 30 / 10 % SOC, riders
p1, p2, p3 with 3 / 12 / 2 km trips. v3 cannot take the 12 km trip (4 % left, 3.5 % at the
charger < 5 %): masked. The decline-risk term then moves v3 to the short trip p1.
"""
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

OUT = Path(__file__).resolve().parent.parent / "docs" / "figures"
NAVY, ORANGE, BLUE, RED, GREEN = "#1d3557", "#e08e45", "#3f7ac6", "#c94242", "#2e8b57"
INK, MUTED = "#222", "#555"
SERIF = "'Times New Roman', Times, serif"

# ---------------- worked example ----------------
INF = 1e9
C = np.array([[1.0, 2.0, INF], [5.0, 10.0, 3.0], [3.5, 2.5, 2.0]])
SOC = np.array([0.80, 0.30, 0.10])
PICK = np.array([[0.6, 1.3, 9], [3.0, 5.6, 1.9], [2.2, 1.6, 1.2]])
TRIP = np.array([3.0, 12.0, 2.0])
E, B = 0.16, 37.23
AFTER = SOC[:, None] - (PICK + TRIP[None, :]) * E / B
LEFT = AFTER - np.array([0.8, 1.5, 0.6])[None, :] * E / B
MASK = LEFT < 0.05
Q = 0.9 / (1 + np.exp((AFTER - 0.20) / 0.04))
S_F = float(np.subtract(*np.percentile(C[C < INF], [75, 25])))
G = C + 0.5 * S_F * Q
G[MASK | (C >= INF)] = INF
ROWS, COLS = linear_sum_assignment(G)
CHOSEN = set(zip(ROWS.tolist(), COLS.tolist()))


def fmt(v):
    return "∞" if v >= INF / 2 else f"{v:.1f}".replace(".", ",")


# ---------------- svg helpers ----------------
parts = []


def add(s):
    parts.append(s)


def text(x, y, s, size=13, color=INK, anchor="start", weight="normal", italic=False, family=SERIF):
    st = ' font-style="italic"' if italic else ""
    add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" fill="{color}" text-anchor="{anchor}" '
        f'font-weight="{weight}"{st}>{s}</text>')


def rect(x, y, w, h, fill="#fff", stroke=MUTED, sw=1.2, dash=None, r=8):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def badge(x, y, n, color=NAVY):
    add(f'<circle cx="{x}" cy="{y}" r="12" fill="{color}"/>')
    text(x, y + 4.5, str(n), 13, "#fff", "middle", "bold", family="Arial")


def arrow(x1, y1, x2, y2, color=NAVY, w=2, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    mid = {"#1d3557": "an", GREEN: "ag", RED: "ar"}.get(color, "an")
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}"{d} marker-end="url(#{mid})"/>')


def car(x, y, s=1.0, color=ORANGE):
    add(f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round">'
        '<path d="M2 16 L2 10 L8 9 L13 3 L27 3 L32 9 L38 10 L38 16 Z" fill="#fff"/>'
        '<path d="M11 9 L15 5 L19 5 L19 9 Z M21 9 L21 5 L26 5 L29 9 Z"/>'
        '<circle cx="10" cy="16" r="3.5" fill="#fff"/><circle cx="30" cy="16" r="3.5" fill="#fff"/></g>')


def person(x, y, s=1.0, color=BLUE):
    add(f'<g transform="translate({x},{y}) scale({s})" stroke="{color}" stroke-width="2" fill="#dbe8f7">'
        '<circle cx="12" cy="7" r="6"/><path d="M1 26 C1 16 23 16 23 26 Z"/></g>')


def charger(x, y, s=1.0):
    add(f'<g transform="translate({x},{y}) scale({s})" stroke="{GREEN}" stroke-width="2" fill="#e9f6ee">'
        '<rect x="2" y="2" width="16" height="24" rx="2"/><path d="M18 9 h4 v10 a2 2 0 0 0 4 0 v-8" fill="none"/>'
        f'<path d="M11 6 L6 15 L10 15 L8 22 L14 12 L10 12 Z" fill="{GREEN}" stroke="none"/></g>')


def battery(x, y, level, w=26, h=12):
    col = RED if level < 0.2 else ORANGE if level < 0.4 else "#d8b13a" if level < 0.6 else GREEN
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="#fff" stroke="{INK}" stroke-width="1.2"/>'
        f'<rect x="{x + w}" y="{y + 3.5}" width="3" height="{h - 7}" fill="{INK}"/>'
        f'<rect x="{x + 2}" y="{y + 2}" width="{(w - 4) * level:.1f}" height="{h - 4}" fill="{col}"/>')


def lock(x, y, s=1.0):
    add(f'<g transform="translate({x},{y}) scale({s})"><path d="M5 10 V6 a5 5 0 0 1 10 0 V10" fill="none" '
        f'stroke="{INK}" stroke-width="2"/><rect x="2" y="10" width="16" height="11" rx="2" fill="#9aa3b5" '
        f'stroke="{INK}" stroke-width="1.2"/></g>')


def grid(x, y, vals, cell=40, kind="cost", circled=()):
    """3x3 matrix with row / column labels; kind: cost (navy shades) | soc (battery colours) | adj."""
    for k in range(3):
        text(x + cell * k + cell / 2, y - 7, f"p<tspan font-size='9' dy='3'>{k + 1}</tspan>", 13, BLUE, "middle", italic=True)
        text(x - 12, y + cell * k + cell / 2 + 5, f"v<tspan font-size='9' dy='3'>{k + 1}</tspan>", 13, ORANGE, "middle", italic=True)
    for i in range(3):
        for j in range(3):
            v = vals[i][j]
            if kind == "soc":
                fill = RED if v < 0.2 else ORANGE if v < 0.4 else "#d8b13a" if v < 0.6 else GREEN
                label, fc = f"{v * 100:.0f}%", "#fff"
            else:
                inf = v >= INF / 2
                masked = kind == "adj" and MASK[i, j]
                fill = "#f6d4d4" if masked else ("#1d3557" if inf else
                                                 ["#a8b5c8", "#7d8fac", "#566b8e", "#3a5076"][min(3, int(v // 2.6))])
                label = "∞" if inf else fmt(v)
                fc = RED if masked else "#fff"
            add(f'<rect x="{x + j * cell}" y="{y + i * cell}" width="{cell - 2}" height="{cell - 2}" fill="{fill}"/>')
            text(x + j * cell + cell / 2 - 1, y + i * cell + cell / 2 + 5, label, 14, fc, "middle", "bold" if (i, j) in circled else "normal")
            if (i, j) in circled:
                add(f'<circle cx="{x + j * cell + cell / 2 - 1}" cy="{y + i * cell + cell / 2 - 1}" r="16" fill="none" '
                    f'stroke="{ORANGE}" stroke-width="2.5"/>')


# ---------------- figure: two parallel layers (matching / charging) ----------------
W, H = 1290, 600
add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">')
add('<defs>'
    f'<marker id="an" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{NAVY}"/></marker>'
    f'<marker id="ag" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{GREEN}"/></marker>'
    f'<marker id="am" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#8a919e"/></marker>'
    '</defs>')
add(f'<rect width="{W}" height="{H}" fill="#fff"/>')


def path(d, color=NAVY, w=2, dash=None, marker="an"):
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}"{ds} marker-end="url(#{marker})"/>')


# ---- shared fleet state (left)
rect(12, 60, 140, 420, "#fdf1e6", ORANGE, 1.4, "6 4", 10)
text(82, 84, "Trạng thái đội xe", 14, NAVY, "middle", "bold")
for k, (lvl, lab) in enumerate([(0.8, "80%"), (0.3, "30%"), (0.1, "10%")]):
    y = 104 + k * 56
    car(26, y, 0.9)
    battery(68, y + 4, lvl, 22, 11)
    text(44, y + 34, f"v<tspan font-size='10' dy='3'>{k + 1}</tspan>", 14, INK, "middle", italic=True)
    text(80, y + 34, lab, 11.5, MUTED, "middle")
for k, km in enumerate([3, 12, 2]):
    y = 284 + k * 38
    person(30, y, 0.8)
    text(60, y + 17, f"p<tspan font-size='10' dy='3'>{k + 1}</tspan>", 14, INK, italic=True)
    text(80, y + 17, f"{km} km", 11.5, MUTED)
charger(32, 404, 0.8)
text(60, 424, "trạm sạc", 11.5, MUTED)
text(82, 462, "cập nhật liên tục", 11, MUTED, "middle", italic=True)

# ---- battery layer frame
rect(172, 16, 966, 494, "#fff", "#8a919e", 1.4, "7 4", 14)
text(190, 40, "LỚP PIN", 15, NAVY, weight="bold")
text(262, 40, "bọc quanh luật ghép của công ty, không sửa nó", 12.5, MUTED, italic=True)

# ---- matching layer (top)
rect(186, 54, 938, 236, "#f1f5fb", "#7fa3d6", 1.3, "6 4", 10)
add('<rect x="186" y="54" width="190" height="24" rx="6" fill="#bfd5ec"/>')
text(281, 71, "Tầng ghép · mỗi 30 giây", 13, NAVY, "middle", "bold")

rect(200, 92, 172, 184, "#fff", "#9aa3ae", 1.1, None, 8)
badge(216, 110, 1)
text(232, 115, "Pin sau chuyến", 14, NAVY, weight="bold")
text(210, 142, "SOC<tspan font-size='9' dy='3'>sau</tspan><tspan dy='-3'> = SOC − e·d/B</tspan>", 13.5, INK, italic=True)
text(210, 160, "d: quãng đón + quãng chở", 11, MUTED)
car(214, 184, 0.75)
battery(248, 188, 0.10, 20, 10)
text(280, 198, "10%", 11, RED)
text(214, 222, "+ cuốc p<tspan font-size='8' dy='3'>2</tspan><tspan dy='-3'> 12 km</tspan>", 11.5, INK)
car(214, 236, 0.75)
battery(248, 240, 0.04, 20, 10)
text(280, 250, "4%", 11, RED, weight="bold")
text(214, 268, "tới trạm &lt; 5% dự trữ", 11, RED)

rect(388, 92, 150, 184, "#e8ebf0", "#555", 1.3, None, 8)
badge(404, 110, 2)
text(420, 115, "Chi phí gốc", 14, NAVY, weight="bold")
lock(512, 98, 0.8)
text(400, 150, "C<tspan font-size='9' dy='3'>ij</tspan><tspan dy='-3'> của black box</tspan>", 13, INK, italic=True)
text(400, 172, "giữ nguyên,", 12, MUTED)
text(400, 190, "đơn vị bất kỳ", 12, MUTED)

rect(554, 92, 150, 184, "#fff", RED, 1.3, None, 8)
badge(570, 110, 3, RED)
text(586, 115, "Cấm", 14, RED, weight="bold")
text(566, 150, "C′ = ∞ nếu", 13, INK, italic=True)
text(566, 170, "sau chuyến không", 12, INK)
text(566, 188, "tới được trạm", 12, INK)
text(566, 206, "với 5% dự trữ", 12, INK)

rect(720, 92, 178, 184, "#fff", BLUE, 1.3, None, 8)
badge(736, 110, 4, BLUE)
text(752, 115, "Phạt rủi ro", 14, BLUE, weight="bold")
text(730, 150, "C′ = C + λ s<tspan font-size='9' dy='3'>C</tspan><tspan dy='-3'> q</tspan>", 14, INK, italic=True)
text(730, 174, "q: xác suất từ chối", 12, MUTED)
text(730, 192, "vì pin thấp", 12, MUTED)
text(730, 214, "s<tspan font-size='9' dy='3'>C</tspan><tspan dy='-3'> = IQR(C):</tspan>", 12, MUTED)
text(730, 232, "không phụ thuộc đơn vị", 12, MUTED)

rect(914, 92, 196, 184, "#fdf1e6", ORANGE, 1.3, None, 8)
badge(930, 110, 5, ORANGE)
text(946, 115, "Solver gốc", 14, NAVY, weight="bold")
lock(1086, 98, 0.8)
grid(950, 140, G.tolist(), 36, "adj", circled=CHOSEN)
text(1012, 262, "min Σ C′x", 13, INK, "middle", italic=True)

for x1, x2 in ((372, 388), (538, 554), (704, 720), (898, 914)):
    arrow(x1, 184, x2, 184)

# ---- charging layer (bottom)
rect(186, 304, 938, 192, "#eef8f1", "#7fbf95", 1.3, "6 4", 10)
add('<rect x="186" y="304" width="176" height="24" rx="6" fill="#cde9d6"/>')
text(274, 321, "Tầng sạc · mỗi 5 phút", 13, GREEN, "middle", "bold")

rect(200, 340, 360, 142, "#fff", GREEN, 1.3, None, 8)
badge(216, 358, 6, GREEN)
text(232, 363, "Nhắc sạc theo giờ", 14, GREEN, weight="bold")
text(548, 363, "xe rảnh, pin dưới mức", 11.5, MUTED, "end")
bx, by, bw, bh = 220, 380, 320, 66
segs = [(0, 4.5, 0.30), (4.5, 7, 0.70), (7, 9, 0.15), (9, 14.5, 0.30), (14.5, 17, 0.70), (17, 19, 0.15), (19, 24, 0.30)]
for a, b, v in segs:
    col = GREEN if v == 0.70 else ORANGE if v == 0.15 else "#a9c2b0"
    add(f'<rect x="{bx + a / 24 * bw:.1f}" y="{by + bh * (1 - v):.1f}" width="{(b - a) / 24 * bw - 1:.1f}" height="{bh * v:.1f}" fill="{col}"/>')
add(f'<line x1="{bx}" y1="{by + bh}" x2="{bx + bw}" y2="{by + bh}" stroke="{INK}"/>')
for hr in (0, 6, 12, 18, 24):
    text(bx + hr / 24 * bw, by + bh + 15, f"{hr}h", 11, MUTED, "middle")
text(bx + 5.75 / 24 * bw, by + bh * 0.3 - 4, "70%", 11, GREEN, "middle", "bold")
text(bx + 15.75 / 24 * bw, by + bh * 0.3 - 4, "70%", 11, GREEN, "middle", "bold")
text(bx + 8 / 24 * bw, by + bh * 0.85 - 4, "15%", 10, ORANGE, "middle")
text(bx + 11.75 / 24 * bw, by + bh * 0.7 - 4, "30%", 10, MUTED, "middle")

rect(578, 340, 262, 142, "#fff", GREEN, 1.3, None, 8)
badge(594, 358, 7, GREEN)
text(610, 363, "Không rút xe khi thiếu", 14, GREEN, weight="bold")
for k in range(3):
    car(596 + k * 34, 384, 0.6, NAVY)
for k in range(2):
    person(720 + k * 24, 382, 0.6)
text(592, 438, "nhắc thêm ≤ 0,5·(N<tspan font-size='9' dy='3'>rảnh</tspan><tspan dy='-3'> − N</tspan>"
     "<tspan font-size='9' dy='3'>chờ</tspan><tspan dy='-3'>)</tspan>", 13, INK, italic=True)
text(592, 462, "xe rảnh − khách đang chờ", 11.5, MUTED)

rect(858, 340, 252, 142, "#fff", GREEN, 1.3, "5 3", 8)
badge(874, 358, 8, GREEN)
text(890, 363, "Tài xế tự quyết", 14, GREEN, weight="bold")
car(878, 392, 0.8)
battery(916, 396, 0.25, 20, 10)
arrow(944, 401, 984, 401, GREEN, 2)
charger(992, 386, 0.85)
text(872, 444, "làm theo với xác suất p<tspan font-size='8' dy='3'>i</tspan>", 12.5, INK, italic=True)
text(872, 464, "tự chọn trạm", 12, MUTED)

arrow(560, 411, 578, 411, GREEN)
arrow(840, 411, 858, 411, GREEN)

# ---- inputs from the shared state, outputs, feedback
path("M152 184 H200")
path("M152 411 H200", GREEN, 2, None, "ag")
rect(1150, 140, 128, 88, "#fff", NAVY, 1.4, None, 8)
car(1180, 152, 0.6)
person(1214, 148, 0.65)
text(1214, 192, "Gửi cuốc", 13, NAVY, "middle", "bold")
text(1214, 212, "tài xế nhận / từ chối", 11, MUTED, "middle")
path("M1110 184 H1150")
rect(1150, 368, 128, 88, "#fff", GREEN, 1.4, None, 8)
car(1178, 382, 0.6)
charger(1216, 374, 0.65)
text(1214, 424, "Xe đi sạc", 13, GREEN, "middle", "bold")
text(1214, 443, "rời tập xe rảnh", 11, MUTED, "middle")
path("M1110 411 H1150", GREEN, 2, None, "ag")
add('<path d="M1214 228 V368" fill="none" stroke="#8a919e" stroke-width="1.6" stroke-dasharray="5 4"/>')
path("M1214 456 V534 H82 V480", "#8a919e", 1.6, "5 4", "am")
text(648, 527, "trạng thái đội xe được cập nhật: xe đã nhận cuốc hoặc đi sạc rời khỏi tập xe rảnh của vòng sau", 12, MUTED, "middle", italic=True)

# ---- legend
lx, ly = 20, 576
car(lx, ly - 13, 0.55); text(lx + 30, ly + 2, "Xe", 12.5)
person(lx + 66, ly - 16, 0.6); text(lx + 86, ly + 2, "Khách", 12.5)
charger(lx + 140, ly - 18, 0.65); text(lx + 160, ly + 2, "Trạm sạc", 12.5)
battery(lx + 228, ly - 8, 0.6, 20, 10); text(lx + 255, ly + 2, "Mức pin", 12.5)
lock(lx + 320, ly - 15, 0.75); text(lx + 340, ly + 2, "Phần của công ty, giữ nguyên", 12.5)
add(f'<rect x="{lx + 530}" y="{ly - 11}" width="20" height="15" fill="#f6d4d4"/>'); text(lx + 556, ly + 2, "Cặp bị cấm", 12.5)
add(f'<circle cx="{lx + 650}" cy="{ly - 3}" r="9" fill="none" stroke="{ORANGE}" stroke-width="2.5"/>'); text(lx + 665, ly + 2, "Cặp được chọn", 12.5)
add(f'<line x1="{lx + 780}" y1="{ly - 3}" x2="{lx + 820}" y2="{ly - 3}" stroke="#8a919e" stroke-width="1.6" stroke-dasharray="5 4"/>'); text(lx + 828, ly + 2, "Phản hồi trạng thái", 12.5)
add("</svg>")

svg = "\n".join(parts)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "battery_framework.svg").write_text(svg, encoding="utf-8")
(OUT / "battery_framework.html").write_text(
    "<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>Battery Framework</title>"
    "<style>body{margin:0;background:#fff}svg{display:block;margin:16px auto;max-width:100%;height:auto}</style>"
    f"</head><body>{svg}</body></html>", encoding="utf-8")
print("chosen", sorted(CHOSEN), "C' sum", round(float(G[ROWS, COLS].sum()), 2))
print("saved", OUT / "battery_framework.svg")
