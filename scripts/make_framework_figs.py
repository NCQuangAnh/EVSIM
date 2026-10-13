"""Three paper-style figures of the battery framework, one idea each (style of Yue et al., CIKM'24,
Fig. 1-3: pastel avatar icons, dashed rounded panels, bipartite rider-car sketches, brackets).

    .venv/Scripts/python scripts/make_framework_figs.py
        -> docs/figures/fw_fig1_overview.svg   Hình 1: lớp pin bọc bộ ghép qua các vòng
           docs/figures/fw_fig2_two_layers.svg Hình 2: hai tầng, hai nhịp thời gian (ví dụ cụ thể)
           docs/figures/fw_fig3_architecture.svg Hình 3: kiến trúc các mô-đun, đầu vào / đầu ra
           docs/figures/framework_figures.html  cả ba hình kèm chú thích

Worked example (same as scripts/make_framework_svg.py): cars v1, v2, v3 at 80 / 30 / 10 % SOC,
riders p1, p2, p3 with 3 / 12 / 2 km trips; the baseline solver gives v3 the 12 km trip, the layer
masks it and v3 takes p1.
"""
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
OUT = Path(__file__).resolve().parent.parent / "docs" / "figures"
SANS = "Helvetica, Arial, sans-serif"
INK, MUTED, GRID = "#2b2b2b", "#666", "#c3c8d0"
NAVY, BLUE, GREEN, RED, ORANGE = "#2c3e66", "#7aa7dd", "#4fa95a", "#d1495b", "#e08e45"
EDGE = "#a9c6e8"

# ---------------- worked example (real Ocean Park 1 positions, road distances) ----------------
# The company's matcher in the example minimises pickup distance (road km on the OSM graph, x1.3 detour off-graph).
from evsim.ocp1 import router as _router  # noqa: E402

ROUTER = _router()
INF = 1e9
CARS = [(20.9995, 105.9472), (20.9922, 105.9392), (20.9880, 105.9470)]     # v1 Sapphire 1, v2 Sapphire 2, v3 Ruby
RIDERS = [(20.9978, 105.9515), (20.9888, 105.9505), (20.9862, 105.9425)]   # p1, p2, p3
SOC = np.array([0.80, 0.30, 0.10])
TRIP = np.array([3.0, 12.0, 2.0])
TO_CHARGER = np.array([0.8, 1.5, 0.6])          # km from each drop-off to the nearest charger
PICK = np.array([[float(ROUTER.road(*v, *r, 1.3)) for r in RIDERS] for v in CARS])
C = PICK.copy()
E, B = 0.16, 37.23
AFTER = SOC[:, None] - (PICK + TRIP[None, :]) * E / B
LEFT = AFTER - TO_CHARGER[None, :] * E / B
MASK = LEFT < 0.05
Q = 0.9 / (1 + np.exp((AFTER - 0.20) / 0.04))
S_F = float(np.subtract(*np.percentile(C, [75, 25])))
G = C + 0.5 * S_F * Q
G[MASK] = INF
CHOSEN = set(zip(*[a.tolist() for a in linear_sum_assignment(G)]))
BASE = set(zip(*[a.tolist() for a in linear_sum_assignment(C)]))
BANNED = {(i, j) for i in range(3) for j in range(3) if MASK[i, j]}
CHOSEN_TXT = ", ".join(f"v{i + 1}→p{j + 1}" for i, j in sorted(CHOSEN))
V3_TRIP = TRIP[[j for i, j in CHOSEN if i == 2][0]]


def route(a, b):
    return ROUTER.path(*a, *b)


# ---------------- svg core ----------------
P = []


def add(s):
    P.append(s)


def begin(w, h):
    P.clear()
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">')
    marks = {"an": NAVY, "ag": GREEN, "am": "#8a919e", "ar": RED, "ao": ORANGE}
    add("<defs>" + "".join(
        f'<marker id="{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" '
        f'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>' for k, c in marks.items()) + "</defs>")
    add(f'<rect width="{w}" height="{h}" fill="#fff"/>')


def text(x, y, s, size=12, color=INK, anchor="start", weight="normal", italic=False):
    st = ' font-style="italic"' if italic else ""
    add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{SANS}" font-size="{size}" fill="{color}" '
        f'text-anchor="{anchor}" font-weight="{weight}"{st}>{s}</text>')


def rect(x, y, w, h, fill="#fff", stroke=GRID, sw=1.3, dash=None, r=10):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def line(x1, y1, x2, y2, color=NAVY, w=1.8, dash=None, marker=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#{marker})"' if marker else ""
    add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{w}"{d}{m}/>')


def path(d, color=NAVY, w=1.8, dash=None, marker=None, fill="none"):
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#{marker})"' if marker else ""
    add(f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{w}"{ds}{m}/>')


def sub(a, b, size=12, color=INK, italic=True):
    """a with subscript b, as tspans (for use inside text())."""
    return f"{a}<tspan font-size='{size * 0.72:.1f}' dy='3'>{b}</tspan><tspan dy='-3'> </tspan>"


# ---------------- icons (pastel avatars, as in the paper) ----------------
def soc_color(v):
    return RED if v < 0.2 else ORANGE if v < 0.4 else "#d8b13a" if v < 0.6 else GREEN


def minibat(x, y, v, w=18, h=7):
    add(f'<g data-name="battery"><rect x="{x:.1f}" y="{y:.1f}" width="{w}" height="{h}" rx="1.5" fill="#fff" stroke="{INK}" stroke-width="0.9"/>'
        f'<rect x="{x + w:.1f}" y="{y + 2:.1f}" width="2" height="{h - 4}" fill="{INK}"/>'
        f'<rect x="{x + 1.3:.1f}" y="{y + 1.3:.1f}" width="{(w - 2.6) * max(v, 0.04):.1f}" height="{h - 2.6}" fill="{soc_color(v)}"/></g>')


def rider(cx, cy, r=13):
    add(f'<g data-name="rider"><circle cx="{cx}" cy="{cy}" r="{r}" fill="#fbd9d3"/>'
        f'<circle cx="{cx}" cy="{cy - r * 0.24:.1f}" r="{r * 0.33:.1f}" fill="#d9644f"/>'
        f'<path d="M{cx - r * 0.62:.1f} {cy + r * 0.72:.1f} Q{cx} {cy - r * 0.08:.1f} {cx + r * 0.62:.1f} {cy + r * 0.72:.1f} Z" fill="#d9644f"/></g>')


def driver(cx, cy, r=13, soc=None, pct=True):
    s = r / 13
    add('<g data-name="car">')
    add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#fdecb8"/>'
        f'<path d="M{cx - 9 * s:.1f} {cy + 4 * s:.1f} V{cy:.1f} L{cx - 6 * s:.1f} {cy - 1 * s:.1f} L{cx - 3 * s:.1f} {cy - 5 * s:.1f} '
        f'H{cx + 4 * s:.1f} L{cx + 6 * s:.1f} {cy - 1 * s:.1f} L{cx + 9 * s:.1f} {cy:.1f} V{cy + 4 * s:.1f} Z" fill="#e2a21b"/>'
        f'<circle cx="{cx - 5 * s:.1f}" cy="{cy + 4 * s:.1f}" r="{2.2 * s:.1f}" fill="#444"/>'
        f'<circle cx="{cx + 5 * s:.1f}" cy="{cy + 4 * s:.1f}" r="{2.2 * s:.1f}" fill="#444"/>')
    if soc is not None:
        minibat(cx - 11, cy + r + 3, soc)
        if pct:
            text(cx + 12, cy + r + 9.5, f"{soc * 100:.0f}%", 9, soc_color(soc) if soc < 0.2 else MUTED)
    add("</g>")


def station(cx, cy, r=13):
    s = r / 13
    add(f'<g data-name="charger"><circle cx="{cx}" cy="{cy}" r="{r}" fill="#d7f0df"/>'
        f'<path d="M{cx + 2 * s:.1f} {cy - 8 * s:.1f} L{cx - 5 * s:.1f} {cy + 1 * s:.1f} L{cx - 1 * s:.1f} {cy + 1 * s:.1f} '
        f'L{cx - 3 * s:.1f} {cy + 8 * s:.1f} L{cx + 5 * s:.1f} {cy - 2 * s:.1f} L{cx + 1 * s:.1f} {cy - 2 * s:.1f} Z" fill="{GREEN}"/></g>')


def lock(x, y, s=0.7):
    add(f'<g data-name="lock" transform="translate({x},{y}) scale({s})"><path d="M5 10 V6 a5 5 0 0 1 10 0 V10" fill="none" '
        f'stroke="{INK}" stroke-width="2"/><rect x="2" y="10" width="16" height="11" rx="2" fill="#9aa3b5" '
        f'stroke="{INK}" stroke-width="1.2"/></g>')


def cross(cx, cy, k=5, color=RED):
    line(cx - k, cy - k, cx + k, cy + k, color, 2.4)
    line(cx - k, cy + k, cx + k, cy - k, color, 2.4)


def pairs(x, y, w, h, socs, kms, edges=True, chosen=(), banned=(), baseline=(), charging=(), cap=None,
          charge_label="đi sạc", named=False):
    """Bipartite sketch: riders on the left, cars on the right (pair = (car i, rider j))."""
    rect(x, y, w, h, "#fbfbfc", GRID, 1.3, "5 4")
    n = max(len(socs), len(kms))
    ys = [y + 24 + k * (h - 54) / (n - 1) for k in range(n)]
    rx, cx = x + 34, x + w - 34
    pr = lambda i, j: (rx + 14, ys[j], cx - 14, ys[i])  # noqa: E731
    if edges:
        for i in range(len(socs)):
            for j in range(len(kms)):
                if (i, j) not in banned and i not in charging:
                    line(*pr(i, j), EDGE, 1.1)
    for i, j in baseline:
        line(*pr(i, j), ORANGE, 2.0, "5 3")
    for i, j in banned:
        x1, y1, x2, y2 = pr(i, j)
        line(x1, y1, x2, y2, RED, 1.6, "4 3")
        cross((x1 + x2) / 2, (y1 + y2) / 2)
    for i, j in chosen:
        line(*pr(i, j), GREEN, 2.8)
    for j, km in enumerate(kms):
        rider(rx, ys[j])
        text(x + 10, ys[j] + 4, f"p{j + 1}" if named else str(j + 1), 10, "#b5432f" if named else MUTED, "middle",
             "bold" if named else "normal")
        text(rx, ys[j] + 25, f"{km} km", 9, MUTED, "middle")
    for i, v in enumerate(socs):
        if i in charging:
            station(cx, ys[i])
            text(cx, ys[i] + 25, charge_label, 9, GREEN, "middle", "bold")
        else:
            driver(cx, ys[i], soc=v, pct=False)
        text(x + w - 9, ys[i] + 4, f"v{i + 1}" if named else str(i + 1), 10, "#9a6a00" if named else MUTED,
             "middle", "bold" if named else "normal")
    if cap:
        text(x + w / 2, y + h + 15, cap[0], 10.5, cap[1] if len(cap) > 1 else MUTED, "middle")


def brace_v(x, y1, y2, color="#e4572e", d=10, side="left"):
    """Curly brace along a vertical span; side = side of the tip."""
    ym, k = (y1 + y2) / 2, (-1 if side == "left" else 1)
    path(f"M{x} {y1} Q{x - k * d} {y1} {x - k * d} {y1 + d} V{ym - d} Q{x - k * d} {ym} {x - k * 2 * d} {ym} "
         f"Q{x - k * d} {ym} {x - k * d} {ym + d} V{y2 - d} Q{x - k * d} {y2} {x} {y2}", color, 2.2)


def bracket(x, y1, y2, label):
    path(f"M{x} {y1} H{x + 8} V{y2} H{x}", INK, 1.4)
    line(x + 8, (y1 + y2) / 2, x + 16, (y1 + y2) / 2, INK, 1.4)
    text(x + 20, (y1 + y2) / 2 + 5, label, 14, INK, weight="bold")


def save(name, w, h):
    add("</svg>")
    svg = "\n".join(P)
    (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
    return svg


# ======================================================================
# Hình 1 — lớp pin bọc bộ ghép của công ty, qua các vòng ghép
# ======================================================================
_G = None


def ocp1_graph():
    global _G
    if _G is None:
        import json
        g = json.loads((OUT.parent.parent / "data" / "ocp1" / "ocp1_graph.json").read_text(encoding="utf-8"))
        st = json.loads((OUT.parent.parent / "data" / "ocp1" / "ocp1_stations_demo40.json").read_text(encoding="utf-8"))
        _G = g, st["stations"]
    return _G


def area_map(x, y, w, h, items, title, links=(), banned=(), routes=(), fit=False):
    """The Ocean Park 1 road network (OSM graph used by the simulator) with icons at real coordinates.
    items: (kind, lat, lon[, soc]) with kind r (rider) | c (car) | s (charging car at a station)."""
    g, stations = ocp1_graph()
    la0, lo0, la1, lo1 = g["meta"]["bbox"]
    if fit:   # zoom on the icons (0.3 km margin), keeping the panel's aspect ratio
        lats, lons = [it[1] for it in items], [it[2] for it in items]
        kx = 111.2 * np.cos(np.radians(21.0))
        hk = max((max(lats) - min(lats)) * 111.2, (max(lons) - min(lons)) * kx * h / w) + 0.6
        cla, clo = (max(lats) + min(lats)) / 2, (max(lons) + min(lons)) / 2
        la0, la1 = cla - hk / 2 / 111.2, cla + hk / 2 / 111.2
        lo0, lo1 = clo - hk * w / h / 2 / kx, clo + hk * w / h / 2 / kx
    px = lambda lat, lon: (x + (lon - lo0) / (lo1 - lo0) * w, y + (la1 - lat) / (la1 - la0) * h)  # noqa: E731
    nodes = g["nodes"]
    cid = f"clip{int(x)}{int(y)}"
    add(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/></clipPath>')
    add('<g data-raster="map">')         # road network: one picture in the PowerPoint export
    rect(x, y, w, h, "#eef3f8", "#b9c6d6", 1, None, 8)
    add(f'<g clip-path="url(#{cid})">')
    for minor in (True, False):
        segs = []
        for a, b, _km, v in g["edges"]:
            if (v < 40) != minor or str(a) not in nodes or str(b) not in nodes:
                continue
            (x1, y1), (x2, y2) = px(*nodes[str(a)]), px(*nodes[str(b)])
            segs.append(f"M{x1:.1f} {y1:.1f}L{x2:.1f} {y2:.1f}")
        add(f'<path d="{"".join(segs)}" fill="none" stroke="{"#c4cad3" if minor else "#a3abb8"}" '
            f'stroke-width="{0.7 if minor else 1.6}" stroke-linecap="round"/>')
    for st in stations:
        sx, sy = px(st["lat"], st["lon"])
        station(sx, sy, 6)
    add("</g></g>")
    for pts, col, dash in routes:
        d = "M" + "L".join(f"{px(la, lo)[0]:.1f} {px(la, lo)[1]:.1f}" for la, lo in pts)
        path(d, col, 2.6, dash)
    for (la_a, lo_a), (la_b, lo_b) in links:
        (x1, y1), (x2, y2) = px(la_a, lo_a), px(la_b, lo_b)
        line(x1, y1, x2, y2, GREEN, 2.4)
    for (la_a, lo_a), (la_b, lo_b) in banned:
        (x1, y1), (x2, y2) = px(la_a, lo_a), px(la_b, lo_b)
        line(x1, y1, x2, y2, RED, 1.8, "4 3")
        cross((x1 + x2) / 2, (y1 + y2) / 2, 4)
    nr = nc = 0
    for kind, lat, lon, *extra in items:
        cx, cy = px(lat, lon)
        if kind == "r":
            nr += 1
            rider(cx, cy, 9)
            text(cx + 11, cy - 5, f"p{nr}", 9.5, "#b5432f", weight="bold")
        else:
            nc += 1
            text(cx - 11, cy - 5, f"v{nc}", 9.5, "#9a6a00", "end", "bold")
            if kind == "s":
                station(cx + 13, cy, 8)
            driver(cx, cy, 9)
            minibat(cx - 9, cy + 11, extra[0], 16, 6)
            text(cx + 10, cy + 17, f"{extra[0] * 100:.0f}%", 9, RED if extra[0] < 0.2 else MUTED, weight="bold")
    if title:
        text(x + w / 2, y - 7, title, 11, MUTED, "middle")


def grp(name):
    """Named group: becomes a PowerPoint group in scripts/svg_to_pptx.py."""
    add(f'<g data-name="{name}">')


def end():
    add("</g>")


def card(x, y, w, head, lines, fill, stroke, hc, locked=False):
    h = 26 + 15 * len(lines)
    rect(x, y, w, h, fill, stroke, 1.3, None, 8)
    text(x + 12 + (20 if locked else 0), y + 18, head, 12.5, hc, weight="bold")
    if locked:
        lock(x + 10, y + 5, 0.65)
    for k, ln in enumerate(lines):
        text(x + 12, y + 36 + 15 * k, ln, 11.5, INK)
    return y + h


def fig1():
    """English, three rows top to bottom (round t, 20 min later, 17:00). Each row reads left to right:
    the Ocean Park 1 map -> candidate pairs -> dispatch rule (1. battery layer, 2. company matcher) -> dispatch
    result; the grey arrow carries the result down to the next row's map."""
    W, H = 1000, 930
    begin(W, H)
    MX, MW, MH = 40, 240, 180
    PX, PW = 316, 196                      # candidate pairs
    RX, RW = 546, 196                      # dispatch rule
    OX = 776                               # dispatch result (width PW)
    grp("Column headers")
    for x, w, lab in ((MX, MW, "Ocean Park 1 map"), (PX, PW, "Candidate pairs"),
                      (RX, RW, "Dispatch rule"), (OX, PW, "Dispatch result")):
        text(x + w / 2, 26, lab, 13, MUTED, "middle", "bold")
    end()
    rows = [52, 340, 628]

    # ---- the three situations
    (bi, bj), = BANNED
    ci = [j for i, j in CHOSEN if i == 2][0]
    long_car = [i for i, j in CHOSEN if j == bj][0]
    v3b = RIDERS[2]
    c2 = [(20.9958, 105.9540), (20.9935, 105.9420), (20.9890, 105.9480)]
    p2_ = [(20.9908, 105.9505)]
    soc2 = [0.48, 0.62, 0.85]
    c3 = [(20.9990, 105.9440), (20.9915, 105.9480), (20.9900, 105.9560)]
    p3_ = [(20.9958, 105.9400), (20.9885, 105.9440), (20.9935, 105.9590)]
    soc3 = [0.80, 0.50, 0.74]
    pct = lambda v: f"{v * 100:.0f}%"  # noqa: E731
    scenes = [
        dict(head="Round t (13:00)",
             items=[("c", *CARS[i], SOC[i]) for i in range(3)] + [("r", *q) for q in RIDERS],
             socs=list(SOC), kms=[int(t) for t in TRIP], chosen=CHOSEN, banned=BANNED, charging=(),
             layer=[f"mask v3–p{bj + 1}: v3 would reach", f"the charger with {pct(LEFT[2, bj])}",
                    "(&lt; 5% reserve)"],
             matcher=["nearest free car"],
             cap=[f"v{long_car + 1} takes the {TRIP[bj]:.0f} km trip ({pct(AFTER[long_car, bj])} left),",
                  f"v3 the short one ({pct(AFTER[2, ci])} left)"],
             ccol=RED),
        dict(head="15:30, before the evening peak",
             items=[("c", *c2[k], soc2[k]) for k in range(3)] + [("r", *q) for q in p2_],
             socs=soc2, kms=[6], chosen={(2, 0)}, banned=(), charging={0},
             layer=["pre-peak: top up cars below 70%.", "3 idle cars, 1 rider: 2 spare,",
                    f"nudge at most 1: v1 ({pct(soc2[0])})"],
             matcher=["nearest free car for p1"],
             cap=["v1 tops up now, not at the peak", "(alone it waits until 8–25%)"], ccol="#24663a"),
        dict(head="17:00, evening peak",
             items=[("c", *c3[k], soc3[k]) for k in range(3)] + [("r", *q) for q in p3_],
             socs=soc3, kms=[15, 9, 11], chosen={(0, 0), (1, 1), (2, 2)}, banned=(), charging=(),
             layer=["every car is above the peak", "level (15%): nothing to do"],
             matcher=["as usual"],
             cap=["charged cars take", "the long peak trips"], ccol=NAVY),
    ]
    links = ["2.5 hours later", "v1 charges; the peak starts"]
    for k, (ry, sc) in enumerate(zip(rows, scenes)):
        y0 = ry + 26
        n = k + 1
        grp(f"Row {n} - title")
        add(f'<circle cx="{MX + 7}" cy="{ry + 8}" r="7" fill="{NAVY}"/>')
        text(MX + 20, ry + 13, sc["head"], 14.5, NAVY, weight="bold")
        end()
        grp(f"Row {n} - map")
        area_map(MX, y0, MW, MH, sc["items"], None, fit=True)
        end()
        grp(f"Row {n} - candidate pairs")
        pairs(PX, y0 + 5, PW, 170, sc["socs"], sc["kms"], named=True)
        end()
        grp(f"Row {n} - dispatch result")
        pairs(OX, y0 + 5, PW, 170, sc["socs"], sc["kms"], edges=False, chosen=sc["chosen"], banned=sc["banned"],
              charging=sc["charging"], charge_label="charging", named=True)
        end()
        for x1, x2 in ((MX + MW + 4, PX - 6), (PX + PW + 4, RX - 6), (RX + RW + 4, OX - 6)):
            line(x1, y0 + 90, x2, y0 + 90, NAVY, 1.8, None, "an")
        # the dispatch rule: battery layer first, then the company's matcher
        h1, h2 = 26 + 15 * len(sc["layer"]), 41
        yy = y0 + 90 - (h1 + 17 + h2) / 2
        grp(f"Row {n} - battery layer")
        y = card(RX, yy, RW, "1. Battery layer", sc["layer"], "#e9f5ec", GREEN, "#24663a")
        end()
        line(RX + RW / 2, y + 1, RX + RW / 2, y + 15, NAVY, 1.8, None, "an")
        grp(f"Row {n} - company matcher")
        card(RX, y + 17, RW, "2. Company matcher", sc["matcher"], "#eef0f4", "#7f8a9e", INK, True)
        end()
        grp(f"Row {n} - result caption")
        for m, ln in enumerate(sc["cap"]):
            text(OX + PW / 2, y0 + 192 + 14 * m, ln, 11.5, sc["ccol"], "middle", "bold")
        end()
        # result -> next row's map
        if k < 2:
            yb = y0 + 226
            grp(f"Row {n} to {n + 1} - link")
            path(f"M{OX + PW / 2} {y0 + 218} V{yb} H{MX + MW - 30} V{rows[k + 1] + 24}", "#8a919e", 1.8, None, "am")
            text((OX + PW / 2 + MX + MW) / 2, yb - 6, links[k], 11, MUTED, "middle", italic=True)
            end()
    # legend
    ly = 910
    grp("Legend")
    rider(70, ly - 4, 9); text(84, ly, "Rider", 11)
    driver(140, ly - 4, 9); text(154, ly, "Car", 11)
    minibat(190, ly - 8, 0.6); text(216, ly, "Battery", 11)
    station(276, ly - 4, 9); text(290, ly, "Charger", 11)
    line(350, ly - 4, 380, ly - 4, EDGE, 1.4); text(386, ly, "Candidate pair", 11)
    line(486, ly - 4, 516, ly - 4, GREEN, 2.8); text(522, ly, "Matched pair", 11)
    line(612, ly - 4, 642, ly - 4, RED, 1.6, "4 3"); cross(627, ly - 4, 4); text(648, ly, "Masked pair", 11)
    lock(736, ly - 14, 0.6); text(752, ly, "Company's part, unchanged", 11)
    end()
    return save("fw_fig1_overview", W, H)


# ======================================================================
# Hình 2 — hai tầng, hai nhịp thời gian (ví dụ cụ thể)
# ======================================================================
def car_row(x, y, socs, gap=46, charging=()):
    for k, v in enumerate(socs):
        cx = x + k * gap
        if k in charging:
            station(cx, y)
            minibat(cx - 11, y + 16, v)
            text(cx, y + 36, "sạc", 9, GREEN, "middle", "bold")
        else:
            driver(cx, y, soc=v, pct=False)
            text(cx, y + 36, f"{v * 100:.0f}%", 9, MUTED, "middle")


def fig2():
    W, H = 1140, 640
    begin(W, H)
    # ---- upper: charging layer, every 5 minutes
    rect(124, 12, 984, 268, "#f6fbf7", "#9bcfa5", 1.3, "6 4", 14)
    text(66, 120, "Tầng sạc", 14, "#24663a", "middle", "bold")
    text(66, 138, "mỗi 5 phút", 11.5, MUTED, "middle")
    text(66, 156, "(cả ngày)", 11.5, MUTED, "middle")
    # schedule strip: the nudge level by hour
    x0, x1, yb = 190, 1080, 86
    hx = lambda t: x0 + (x1 - x0) * t / 24  # noqa: E731
    hy = lambda v: yb - 60 * v  # noqa: E731
    sched = [(0, 4.5, .3), (4.5, 7, .7), (7, 9, .15), (9, 14.5, .3), (14.5, 17, .7), (17, 19, .15), (19, 24, .3)]
    for a, b, v in sched:
        col = ORANGE if v > .5 else RED if v < .2 else "#9fb0c8"
        add(f'<rect x="{hx(a):.1f}" y="{hy(v):.1f}" width="{hx(b) - hx(a):.1f}" height="{yb - hy(v):.1f}" fill="{col}" opacity="0.55"/>')
        text((hx(a) + hx(b)) / 2, hy(v) - 4, f"{v * 100:.0f}%", 9.5, INK, "middle")
    line(x0, yb, x1, yb, INK, 1)
    for t in range(0, 25, 3):
        line(hx(t), yb, hx(t), yb + 4, INK, 1)
        text(hx(t), yb + 15, f"{t}h", 9, MUTED, "middle")
    text(x0 - 8, 40, "mức nhắc sạc", 10, MUTED, "end")
    text(x0 - 8, 53, "theo giờ", 10, MUTED, "end")
    # three snapshots
    snaps = [(200, 14.0, "14:00 · thấp điểm", [0.55, 0.62, 0.35, 0.48], (), "xe rảnh 4, khách chờ 1: dư 3 xe", MUTED),
             (520, 15.5, "15:30 · trước cao điểm", [0.55, 0.62, 0.35, 0.48], (2,),
              "nhắc xe &lt; 70%, rút tối đa 0,5·3 → 1 xe", "#24663a"),
             (840, 17.0, "17:00 · cao điểm", [0.83, 0.71, 0.88, 0.74], (), "ngưỡng nhắc hạ còn 15%: giữ xe chạy", NAVY)]
    for k, (sx, t, title, socs, chg, note, nc) in enumerate(snaps):
        line(hx(t), yb + 18, sx + 125, 138, "#8a919e", 1, "2 3")
        add(f'<circle cx="{hx(t):.1f}" cy="{yb}" r="3.5" fill="{INK}"/>')
        rect(sx, 140, 250, 128, "#fff", GRID, 1.3, "5 4")
        text(sx + 125, 160, title, 12, INK, "middle", "bold")
        car_row(sx + 56, 192, socs, 46, chg)
        text(sx + 125, 256, note, 10.5, nc, "middle")
        if k < 2:
            line(sx + 256, 204, sx + 314, 204, "#8a919e", 1.4, "2 3", "am")
    # ---- lower: matching layer, every 30 seconds, one round in detail
    rect(124, 312, 984, 300, "#f5f8fc", "#9fb9de", 1.3, "6 4", 14)
    text(66, 440, "Tầng ghép", 14, NAVY, "middle", "bold")
    text(66, 458, "mỗi 30 giây", 11.5, MUTED, "middle")
    text(66, 476, "(một vòng)", 11.5, MUTED, "middle")
    steps = [(140, "① Chi phí gốc", True), (382, "② Dự báo pin sau chuyến", False),
             (624, "③ Cấm cặp nguy hiểm", False), (866, "④ Phạt rủi ro → ⑤ Solver gốc", True)]
    for k, (sx, title, locked) in enumerate(steps):
        text(sx + 112, 340, title, 12.5, INK, "middle", "bold")
        if locked:
            lock(sx + 112 + len(title) * 3.6 + 4, 327, 0.55)
        if k < 3:
            line(sx + 228, 448, sx + 238, 448, NAVY, 1.8, None, "an")
    pairs(140, 352, 224, 170, SOC, [3, 12, 2], baseline={(2, 1)},
          cap=("solver gốc sẽ giao v3 chuyến 12 km", ORANGE))
    # step 2: forecast table for car v3
    rect(382, 352, 224, 170, "#fbfbfc", GRID, 1.3, "5 4")
    driver(410, 382, soc=None)
    text(430, 380, "v3 đang có 10%", 11, INK)
    text(430, 393, "pin còn lại nếu nhận:", 10, MUTED)
    for j in range(3):
        yy = 420 + j * 32
        rider(406, yy, 10)
        text(422, yy + 4, f"p{j + 1} · {TRIP[j]:.0f} km", 10.5, INK)
        minibat(498, yy - 4, AFTER[2, j], 30, 9)
        warn = MASK[2, j]
        text(538, yy + 4, f"{AFTER[2, j] * 100:.0f}%", 10.5, RED if warn else MUTED, weight="bold" if warn else "normal")
        if warn:
            text(566, yy + 4, "⚠", 11, RED)
    text(494, 537, "SOC sau = SOC − e·d / B", 10.5, MUTED, "middle", italic=True)
    pairs(624, 352, 224, 170, SOC, [3, 12, 2], banned=BANNED, cap=("đến trạm sạc còn &lt; 5% → cấm", RED))
    pairs(866, 352, 224, 170, SOC, [3, 12, 2], edges=False, chosen=CHOSEN,
          cap=(CHOSEN_TXT, "#24663a"))
    text(978, 556, "phạt cặp rủi ro từ chối: + λ·s·q(SOC sau)", 10, MUTED, "middle", italic=True)
    # links between the layers
    path("M645 268 V300 H300 V350", "#8a919e", 1.5, "5 4", "am")
    text(470, 296, "xe đi sạc rời tập xe rảnh của vòng ghép", 10.5, MUTED, "middle", italic=True)
    path("M1090 437 H1122 V150 H1110", "#8a919e", 1.5, "5 4", "am")
    add(f'<text x="1132" y="300" transform="rotate(90 1132 300)" font-family="{SANS}" font-size="10.5" '
        f'fill="{MUTED}" text-anchor="middle" font-style="italic">SOC cập nhật sau mỗi chuyến</text>')
    return save("fw_fig2_two_layers", W, H)


# ======================================================================
# Hình 3 — kiến trúc: đầu vào, các mô-đun của hai tầng, đầu ra
# ======================================================================
def module(x, y, w, title, lines, fill, locked=False):
    """Module box: bold title and one formula / fact per line. Returns the bottom y."""
    h = 50 + 15 * (len(lines) - 1)
    grp(f"Module: {title}")
    rect(x, y, w, h, fill, "none", 0, None, 9)
    text(x + w / 2, y + 20, title, 12.5, INK, "middle", "bold")
    for k, ln in enumerate(lines):
        text(x + w / 2, y + 37 + 15 * k, ln, 10.5, "#333", "middle", italic=True)
    if locked:
        lock(x + w - 22, y + 6, 0.6)
    end()
    return y + h


def pill(x, y, w, h, l1, l2, fill):
    grp(l1)
    rect(x, y, w, h, fill, "none", 0, None, h / 2)
    text(x + w / 2, y + h / 2 - 1, l1, 12.5, INK, "middle", "bold")
    text(x + w / 2, y + h / 2 + 13, l2, 10, "#3a3a3a", "middle")
    end()


IN_COL = {"F": "#3f9d4a", "R": "#d9a400", "S": "#2a8f86", "X": "#d9654c"}   # fleet, riders, chargers, context


def reads(x, y, keys):
    """Colour dots left of a module: the inputs it reads (same colours as the input pills)."""
    grp("Inputs read")
    for k, key in enumerate(keys):
        add(f'<circle cx="{x - 9}" cy="{y + 10 + 13 * k}" r="5" fill="{IN_COL[key]}" stroke="#555" stroke-width="0.8"/>')
    end()


def fig3():
    """English. Architecture of the battery layer with every rule written out (values of the locked v2.1;
    the spare-car gate is the v2.2 addition)."""
    W, H = 1130, 800
    begin(W, H)
    GREY = "#dfe2e7"
    sub = lambda a, b: f"{a}<tspan font-size='8' dy='3'>{b}</tspan><tspan dy='-3'>&#8203;</tspan>"  # noqa: E731
    soc_a, d_p, d_t, d_c, soc_c = (sub("SOC", "after"), sub("d", "pickup"), sub("d", "trip"), sub("d", "charger"),
                                   sub("SOC", "charger"))
    # ---- matching layer
    grp("Matching layer")
    grp("Matching layer frame")
    rect(40, 120, 520, 520, "#f4f5f7", "#c3c8d0", 1.3, None, 14)
    text(60, 143, "Matching layer · every 30 s", 13.5, NAVY, weight="bold")
    end()
    yb = module(55, 520, 262, "Battery after the trip",
                [f"{soc_a} = SOC − ({d_p} + {d_t}) · e / B",
                 "e = 0.16 kWh/km, B = 37.23 kWh (VF5)",
                 "≈ 0.43% per km of road distance",
                 "SOC: when the car is next free"], "#bcd5f2")
    reads(55, 520, "FR")
    module(330, 520, 210, "Original cost C",
           ["the company's cost of each", "car–rider pair (e.g. pickup", "distance); not changed by us"], GREY, True)
    reads(330, 520, "FR")
    module(115, 385, 360, "Safety mask",
           [f"{soc_c} = {soc_a} − {d_c} · e / B",
            f"{d_c}: drop-off → nearest charger (road km)",
            f"C′ = ∞ (pair removed) if {soc_c} &lt; 5%"], "#f4b9b9")
    reads(115, 385, "S")
    module(115, 262, 360, "Decline-risk penalty",
           [f"C′ = C + λ · s · q({soc_a})",
            f"q = P(decline | {soc_a}) − P(decline | full)",
            "s = IQR of C (unit-free scale), λ = 0.5"], "#d6c6ee")
    module(165, 158, 260, "Original solver",
           ["the company's matcher, unchanged", "picks the pairs: min Σ C′"], GREY, True)
    line(185, 518, 250, 467, NAVY, 1.6, None, "an")
    line(435, 518, 360, 467, NAVY, 1.6, None, "an")
    line(295, 383, 295, 344, NAVY, 1.6, None, "an")
    line(295, 260, 295, 225, NAVY, 1.6, None, "an")
    text(305, 248, "C′", 12, INK, italic=True)
    end()
    # ---- charging layer
    grp("Charging layer")
    grp("Charging layer frame")
    rect(590, 120, 440, 520, "#f3f8f4", "#b9d9c0", 1.3, None, 14)
    text(610, 143, "Charging layer · every 5 min", 13.5, "#24663a", weight="bold")
    end()
    module(615, 520, 390, "Time-of-day nudge levels",
           ["70% in the 2.5 h before each peak (4:30–7:00, 14:30–17:00)",
            "15% during the peaks (7:00–9:00, 17:00–19:00)",
            "30% at all other times"], "#bfe3c6")
    reads(615, 520, "X")
    module(615, 390, 390, "Spare-car gate (v2.2)",
           [f"extra pre-peak nudges ≤ ⌊0.5 · ({sub('N', 'idle')} − {sub('N', 'waiting')})⌋",
            "cars below 30% are always nudged"], "#b9e0dc")
    reads(615, 390, "X")
    module(615, 250, 390, "Pick cars to nudge",
           ["idle cars below the current level",
            "skip drivers whose shift ends within 1 h",
            "a driver who ignored a nudge: not asked for 15 min"], "#e6efc4")
    reads(615, 250, "F")
    line(810, 518, 810, 457, GREEN, 1.6, None, "ag")
    line(810, 388, 810, 332, GREEN, 1.6, None, "ag")
    end()
    # ---- the mask feeds the charging layer
    grp("Link: masked car → nudge")
    path("M475 425 H575 V290 H611", RED, 1.5, "5 3", "ar")
    text(612, 349, "masked car → nudged at once:", 10, RED, italic=True)
    text(612, 362, "≥ 80% of its pairs masked, or", 10, RED, italic=True)
    text(612, 375, "SOC &lt; 5% + 30 km · e / B (≈ 18%)", 10, RED, italic=True)
    end()
    # ---- outputs
    grp("Outputs")
    pill(155, 40, 280, 48, "Dispatch (v, p)", "the driver accepts or declines", "#f4c2d2")
    pill(670, 40, 280, 48, "Charge nudge", "followed with the driver's own probability (mean 60%)", "#c9ebcf")
    line(295, 156, 295, 90, NAVY, 1.8, None, "an")
    line(810, 248, 810, 90, GREEN, 1.8, None, "ag")
    bracket(1045, 40, 88, "Output")
    end()
    # ---- inputs on a shared bus
    grp("Inputs")
    l1_key = {"Fleet state": "F", "Waiting riders": "R", "Chargers": "S", "Context": "X"}
    pills = [(45, "Fleet state", "position, SOC, idle / busy, shift end", "#9fd8a3"),
             (290, "Waiting riders", "pickup point, trip length", "#f6d870"),
             (535, "Chargers", "location, ports", "#a9d8d5"),
             (780, "Context", "time of day, idle cars / waiting riders", "#f2b3a5")]
    for x, l1, l2, f in pills:
        pill(x, 700, 220, 48, l1, l2, f)
        add(f'<circle cx="{x + 18}" cy="724" r="6" fill="{IN_COL[l1_key[l1]]}" stroke="#555" stroke-width="0.8"/>')
        line(x + 110, 698, x + 110, 676, "#c98a3a", 1.6)
    line(155, 676, 890, 676, "#c98a3a", 1.6)
    for x in (300, 810):     # the inputs feed both layers; the dots say which module reads which input
        line(x, 676, x, 644, "#c98a3a", 1.8, None, "ao")
    bracket(1045, 700, 748, "Input")
    text(W - 8, 772, "dot beside a module:", 10, MUTED, "end", italic=True)
    text(W - 8, 785, "the inputs it reads", 10, MUTED, "end", italic=True)
    end()
    # ---- feedback: the environment moves to the next state
    grp("Feedback loop")
    path("M155 64 H18 V724 H41", "#555", 1.5, "6 4", "am")
    add(f'<text x="11" y="400" transform="rotate(-90 11 400)" font-family="{SANS}" font-size="11" fill="{MUTED}" '
        'text-anchor="middle" font-style="italic">the environment updates the state for the next round</text>')
    end()
    return save("fw_fig3_architecture", W, H)


CAPTIONS = [
    ("Figure 1", "Three moments of one day, top to bottom. Each row reads left to right: the situation on the "
                 "Ocean Park 1 road network, the candidate rider–car pairs, the dispatch rule (1. the battery layer "
                 "acts, 2. the company's unchanged matcher matches) and the dispatch result, which carries into the "
                 "next row. Round t: a car with 10% battery is kept off a 12 km trip. At 15:30, with spare cars, "
                 "a car at 48% is nudged to top up before the peak, which its driver would not do alone (drivers "
                 "charge at their own 8–25% threshold). At 17:00 every car is charged.",
     "fw_fig1_overview"),
    ("Hình 2", "Hai tầng của lớp pin chạy ở hai nhịp thời gian. Trên: tầng sạc (mỗi 5 phút, cả ngày) nâng mức "
               "nhắc sạc lên 70% trước cao điểm nhưng chỉ rút xe khi dư. Dưới: tầng ghép (mỗi 30 giây) với ví dụ "
               "ba xe, ba khách: solver gốc sẽ giao xe 10% chuyến 12 km; lớp pin cấm cặp đó và xe được giao "
               f"chuyến {V3_TRIP:.0f} km.", "fw_fig2_two_layers"),
    ("Figure 3", "Architecture of the battery layer. The inputs are shared by both layers; modules with a lock "
                 "belong to the company and are not changed. A car shut out by the safety mask is passed to the "
                 "charging layer and nudged to charge at once.", "fw_fig3_architecture"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    svgs = [fig1(), fig2(), fig3()]
    body = "".join(
        f"<figure><div class='svg'>{s}</div><figcaption><b>{n}:</b> {c}</figcaption></figure>"
        for s, (n, c, _) in zip(svgs, CAPTIONS))
    (OUT / "framework_figures.html").write_text(
        "<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>Battery Framework Figures</title>"
        "<style>body{margin:0;background:#fff;color:#222;font-family:'Times New Roman',serif}"
        "figure{max-width:1120px;margin:28px auto;padding:0 16px}svg{display:block;width:100%;height:auto}"
        "figcaption{margin-top:8px;font-size:15px;line-height:1.45}</style></head>"
        f"<body>{body}</body></html>", encoding="utf-8")
    print("base", sorted(BASE), "chosen", sorted(CHOSEN), "banned", sorted(BANNED))
    print("v3 after:", np.round(AFTER[2] * 100, 1))
    print("saved", OUT / "framework_figures.html")


if __name__ == "__main__":
    main()
