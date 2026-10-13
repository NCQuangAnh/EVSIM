// Side-by-side replay of the Ocean Park 1 demo: a black box vs the same black box + battery layer v2.1, same seed.
// Data: /data/oceanpark.json, /data/ocp1_manifest.json and /data/ocp1_replay_<scene>_<bb>_<base|v21>.json (scripts/ocp1_demo.py).
import { Application, Container, Graphics, Text } from "pixi.js";
import { buildMap, type MapLayers } from "./map";
import type { Pt } from "./geom";
import type { MapData } from "./types";

type Leg = [number, number, number, string, number, number, Pt[]]; // car, t0, t1, kind, soc0, soc1, path
type State = [number, number, string, number, number, number, number]; // t, car, status, soc, x, y, station
type Rider = [number, number, number, number, number]; // booked, end of wait, x, y, outcome
type Journey = [number, number, number, number, number]; // trip id, served (0/1), end (pickup or last cancel), x, y
/** A journey served on one side and lost on the other: drawn as a star on both maps. */
interface Diff { x: number; y: number; t: number; rightServed: boolean }
interface ManifestEntry {
  scene: string; scene_label: string; bb: string; bb_label: string; seed: number; n: number;
  summary: Record<string, { diff: number; ci: number; pos: number }>;
}
interface Replay {
  meta: { arm: string; seed: number; label: string; duration_s: number; metrics: Record<string, number> };
  stations: { xy: Pt; ports: number }[];
  legs: Leg[];
  states: State[];
  riders: Rider[];
  journeys: Journey[];
  kpi: Record<string, number[]>;
}
interface CarNow { x: number; y: number; status: string; soc: number; station: number }

const CHARGE_STATES = new Set(["to_station", "queued", "charging"]);
const BUSY_STATES = new Set(["to_pickup", "on_trip"]);
const LEG_STATUS: Record<string, string> = {
  deadhead: "to_pickup", trip: "on_trip", to_station: "to_station", reposition: "reposition", home: "off",
};

function socColor(s: number): number {
  return s < 0.2 ? 0xe03131 : s < 0.4 ? 0xf08c00 : s < 0.6 ? 0xf2c94c : 0x2f9e44;
}

/** Last index i with key(arr[i]) <= t, or -1. */
function lastAtOrBefore<T>(arr: T[], t: number, key: (x: T) => number): number {
  let lo = 0, hi = arr.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (key(arr[mid]) <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

class Fleet {
  legs: Leg[][] = [];
  cum: number[][][] = [];      // cumulative lengths of each leg's path
  states: State[][] = [];
  n = 0;
  constructor(r: Replay) {
    for (const s of r.states) this.n = Math.max(this.n, s[1] + 1);
    for (let i = 0; i < this.n; i++) { this.legs.push([]); this.states.push([]); this.cum.push([]); }
    const legs = [...r.legs].sort((a, b) => a[1] - b[1]);
    for (const l of legs) {
      const c = [0];
      for (let k = 1; k < l[6].length; k++) c.push(c[k - 1] + Math.hypot(l[6][k][0] - l[6][k - 1][0], l[6][k][1] - l[6][k - 1][1]));
      this.cum[l[0]].push(c);
      this.legs[l[0]].push(l);
    }
    for (const s of r.states) this.states[s[1]].push(s);
  }

  at(car: number, t: number): CarNow | null {
    const ss = this.states[car];
    const si = lastAtOrBefore(ss, t, (s) => s[0]);
    const st = si >= 0 ? ss[si] : null;
    const ls = this.legs[car];
    const li = lastAtOrBefore(ls, t, (l) => l[1]);
    if (li >= 0) {
      const l = ls[li];
      if (t <= l[2]) {                                   // on the road: interpolate along the path
        const f = l[2] > l[1] ? (t - l[1]) / (l[2] - l[1]) : 1;
        const c = this.cum[car][li];
        const d = f * c[c.length - 1];
        let k = 1;
        while (k < c.length - 1 && c[k] < d) k++;
        const seg = c[k] - c[k - 1];
        const u = seg > 0 ? (d - c[k - 1]) / seg : 0;
        const p0 = l[6][k - 1], p1 = l[6][Math.min(k, l[6].length - 1)];
        return { x: p0[0] + (p1[0] - p0[0]) * u, y: p0[1] + (p1[1] - p0[1]) * u,
          status: LEG_STATUS[l[3]] ?? "on_trip", soc: l[4] + (l[5] - l[4]) * f, station: -1 };
      }
      if (!st || st[0] < l[2]) {                         // leg ended after the last state change
        const end = l[6][l[6].length - 1];
        return { x: end[0], y: end[1], status: st ? st[2] : "idle", soc: l[5], station: st ? st[6] : -1 };
      }
    }
    if (!st) return null;
    return { x: st[4], y: st[5], status: st[2], soc: st[3], station: st[6] };
  }
}

class Side {
  app = new Application();
  map!: MapLayers;
  fleet: Fleet;
  dyn = new Graphics();
  stationText: Text[] = [];
  scale = 1;
  diffs: Diff[] = [];
  right = false;          // the side with the battery layer
  constructor(public el: HTMLElement, public data: Replay, public base: MapData) {
    this.fleet = new Fleet(data);
  }

  setData(data: Replay) {
    this.data = data;
    this.fleet = new Fleet(data);
  }

  async init() {
    const host = this.el.querySelector<HTMLDivElement>(".map")!;
    await this.app.init({ resizeTo: host, antialias: true, background: 0xe6dcc6, autoDensity: true, resolution: devicePixelRatio });
    host.appendChild(this.app.canvas);
    this.map = buildMap(this.base);
    this.map.stations.visible = false;                    // the demo uses its own 40-port set
    this.app.stage.addChild(this.map.root);
    this.map.traffic.addChild(this.dyn);
    for (const s of this.data.stations) {
      const c = new Container();
      const g = new Graphics();
      g.roundRect(-10, -10, 20, 20, 4).fill(0x22a06b).stroke({ width: 2, color: 0xffffff });
      g.poly([1.5, -7, -4, 1, 0, 1, -1.5, 7, 4, -1, 0, -1]).fill(0xffffff);
      const t = new Text({ text: "", resolution: 2, style: { fontSize: 12, fontWeight: "700", fill: 0x14532d, stroke: { color: 0xffffff, width: 3 } } });
      t.position.set(13, -8);
      c.addChild(g, t);
      c.position.set(s.xy[0], s.xy[1]);
      this.map.labels.addChild(this.map.screenSized.add(c));
      this.stationText.push(t);
    }
  }

  view(scale: number, x: number, y: number) {
    this.scale = scale;
    this.map.root.scale.set(scale, -scale);
    this.map.root.position.set(x, y);
    this.map.setZoom(scale);
  }

  draw(t: number) {
    const g = this.dyn;
    g.clear();
    const px = 1 / this.scale;                            // one screen pixel in metres
    // riders waiting for a car
    for (const r of this.data.riders) {
      if (r[0] <= t && t < r[1]) g.circle(r[2], r[3], 3.2 * px).fill({ color: 0x7048e8, alpha: 0.85 });
    }
    // journeys one side serves and the other loses: visible for 20 minutes after the event
    for (const d of this.diffs) {
      if (t < d.t || t > d.t + 1200) continue;
      const good = d.rightServed === this.right;
      g.star(d.x, d.y, 5, 11 * px, 5 * px).fill({ color: good ? 0x12b886 : 0xe03131, alpha: 0.95 })
        .stroke({ width: 1.5 * px, color: 0xffffff });
    }
    const atStation = this.data.stations.map(() => ({ charging: 0, queued: 0 }));
    const cars: CarNow[] = [];
    for (let i = 0; i < this.fleet.n; i++) {
      const c = this.fleet.at(i, t);
      if (!c || c.status === "off" || c.status === "break") continue;
      cars.push(c);
      if (c.station >= 0 && c.station < atStation.length) {
        if (c.status === "charging") atStation[c.station].charging++;
        else if (c.status === "queued") atStation[c.station].queued++;
      }
    }
    for (const c of cars) {
      const charge = CHARGE_STATES.has(c.status);
      const busy = BUSY_STATES.has(c.status);
      const r = (charge || busy ? 6 : 5) * px;
      g.circle(c.x, c.y, r).fill({ color: socColor(c.soc), alpha: c.status === "idle" ? 0.75 : 1 })
        .stroke({ width: (charge ? 3 : 1.6) * px, color: charge ? 0x1971c2 : busy ? 0xffffff : 0x3b3b3b });
    }
    this.data.stations.forEach((s, k) => {
      const a = atStation[k];
      this.stationText[k].text = `${a.charging}/${s.ports}` + (a.queued ? ` +${a.queued}` : "");
    });
  }
}

function kpiAt(r: Replay, key: string, t: number): number {
  const ts = r.kpi.t;
  const i = Math.max(0, Math.min(ts.length - 1, Math.floor(t / (ts[1] - ts[0]))));
  return r.kpi[key][i];
}

const CARDS: [string, string, (r: Replay, t: number) => number, number, (v: number) => string][] = [
  // label, key, value, better sign (+1 higher is better, -1 lower, 0 neutral), format
  ["Đã phục vụ", "served", (r, t) => kpiAt(r, "served", t), 1, (v) => v.toFixed(0)],
  ["Khách đang chờ", "waiting", (r, t) => kpiAt(r, "waiting", t), -1, (v) => v.toFixed(0)],
  ["Khách đã huỷ", "cancelled", (r, t) => kpiAt(r, "cancelled", t), -1, (v) => v.toFixed(0)],
  ["Đang sạc + chờ sạc", "charging", (r, t) => kpiAt(r, "charging", t) + kpiAt(r, "queued", t), 0, (v) => v.toFixed(0)],
  ["Đang đón / chở", "busy", (r, t) => kpiAt(r, "busy", t), 1, (v) => v.toFixed(0)],
  ["SOC trung bình", "mean_soc", (r, t) => kpiAt(r, "mean_soc", t), 0, (v) => `${(v * 100).toFixed(0)}%`],
];

function setupKpis(el: HTMLElement, r: Replay) {
  const box = el.querySelector<HTMLDivElement>(".kpis")!;
  box.innerHTML = CARDS.map(([l, k]) => `<div class="kpi"><div class="v" data-k="${k}">–</div><div class="l">${l}</div></div>`).join("")
    + `<div class="final">Cả 48 giờ: service <b>${(r.meta.metrics.service_level * 100).toFixed(2)}%</b> · giờ cao điểm <b>${(r.meta.metrics.service_level_peak * 100).toFixed(2)}%</b> · lợi nhuận <b>${Math.round(r.meta.metrics.profit_adj_per_vehicle_day_vnd / 1000).toLocaleString("vi-VN")}k</b> đ/xe/ngày · từ chối do pin <b>${(r.meta.metrics.ride_reject_soc_share * 100).toFixed(0)}%</b></div>`;
}

function updateKpis(sides: Side[], t: number) {
  const vals = sides.map((s) => CARDS.map((c) => c[2](s.data, t)));
  sides.forEach((s, i) => {
    CARDS.forEach(([, k, , better, fmt], j) => {
      const el = s.el.querySelector<HTMLDivElement>(`.v[data-k="${k}"]`)!;
      el.textContent = fmt(vals[i][j]);
      const other = vals[1 - i][j];
      el.className = "v" + (better === 0 || vals[i][j] === other ? "" : (vals[i][j] - other) * better > 0 ? " better" : " worse");
    });
  });
}

function drawChart(side: Side, t: number, maxQ: number, maxW: number) {
  const cv = side.el.querySelector<HTMLCanvasElement>(".chart")!;
  const w = (cv.width = cv.clientWidth * devicePixelRatio);
  const h = (cv.height = cv.clientHeight * devicePixelRatio);
  const ctx = cv.getContext("2d")!;
  const k = side.data.kpi;
  const T = side.data.meta.duration_s;
  const line = (vals: number[], max: number, color: string) => {
    ctx.beginPath();
    vals.forEach((v, i) => {
      const x = (k.t[i] / T) * w, y = h - 4 - (v / max) * (h - 18);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6 * devicePixelRatio;
    ctx.stroke();
  };
  for (const [a, b] of [[7, 9], [17, 19]]) {
    ctx.fillStyle = "rgba(240,140,0,0.10)";
    ctx.fillRect((a * 3600 / T) * w, 0, ((b - a) * 3600 / T) * w, h);
  }
  line(k.charging.map((v, i) => v + k.queued[i]), maxQ, "#1971c2");
  line(k.waiting, maxW, "#7048e8");
  ctx.fillStyle = "#2f3440";
  ctx.fillRect((t / T) * w - devicePixelRatio, 0, 2 * devicePixelRatio, h);
  ctx.font = `${11 * devicePixelRatio}px system-ui`;
  ctx.fillStyle = "#1971c2";
  ctx.fillText("xe đang sạc + chờ sạc", 6 * devicePixelRatio, 13 * devicePixelRatio);
  ctx.fillStyle = "#7048e8";
  ctx.fillText("khách đang chờ", 150 * devicePixelRatio, 13 * devicePixelRatio);
  ctx.fillStyle = "#b5591a";
  ctx.fillText("cao điểm", (7 * 3600 / T) * w + 3, h - 6);
}

function computeDiffs(left: Replay, right: Replay): Diff[] {
  const l = new Map(left.journeys.map((j) => [j[0], j]));
  const out: Diff[] = [];
  for (const r of right.journeys) {
    const a = l.get(r[0]);
    if (!a || a[1] === r[1]) continue;
    out.push({ x: r[3], y: r[4], t: Math.max(a[2], r[2]), rightServed: r[1] === 1 });
  }
  return out.sort((p, q) => p.t - q.t);
}

async function main() {
  const fetchJson = async (u: string) => (await fetch(u)).json();
  const [base, manifest] = await Promise.all([fetchJson("/data/oceanpark.json"), fetchJson("/data/ocp1_manifest.json")]) as
    [MapData, ManifestEntry[]];
  const q = new URLSearchParams(location.search);
  const sceneSel = document.getElementById("scene") as HTMLSelectElement;
  const bbSel = document.getElementById("bb") as HTMLSelectElement;
  for (const sc of [...new Set(manifest.map((m) => m.scene))]) sceneSel.add(new Option(manifest.find((m) => m.scene === sc)!.scene_label, sc));
  for (const bb of [...new Set(manifest.map((m) => m.bb))]) bbSel.add(new Option(manifest.find((m) => m.bb === bb)!.bb_label, bb));
  sceneSel.value = q.get("scene") ?? "normal";
  bbSel.value = q.get("bb") ?? "b1";
  const load = async (scene: string, bb: string) =>
    Promise.all(["base", "v21"].map((arm) => fetchJson(`/data/ocp1_replay_${scene}_${bb}_${arm}.json`))) as Promise<[Replay, Replay]>;

  const [left, right] = await load(sceneSel.value, bbSel.value);
  const sides = [new Side(document.getElementById("side-b1")!, left, base), new Side(document.getElementById("side-v21")!, right, base)];
  sides[1].right = true;
  for (const s of sides) await s.init();
  let maxQ = 1, maxW = 1, diffs: Diff[] = [];
  const statsEl = document.getElementById("stats20")!;
  const sign = (v: number, d: number) => `${v >= 0 ? "+" : ""}${v.toFixed(d)}`;
  const apply = () => {
    for (const s of sides) {
      setupKpis(s.el, s.data);
      s.el.querySelector(".bb-label")!.textContent = `${s.data.meta.label} · seed ${s.data.meta.seed}`;
    }
    maxQ = Math.max(...sides.flatMap((s) => s.data.kpi.charging.map((v, i) => v + s.data.kpi.queued[i]))) * 1.1 + 1;
    maxW = Math.max(...sides.flatMap((s) => s.data.kpi.waiting)) * 1.1 + 1;
    diffs = computeDiffs(sides[0].data, sides[1].data);
    sides.forEach((s) => (s.diffs = diffs));
    const m = manifest.find((e) => e.scene === sceneSel.value && e.bb === bbSel.value)!;
    const sl = m.summary.service_level, pk = m.summary.service_level_peak, pr = m.summary.profit_adj_per_vehicle_day_vnd;
    statsEl.textContent = `Trung bình ${m.n} seed: service ${sign(sl.diff, 2)} ± ${sl.ci.toFixed(2)} pt (${Math.round(sl.pos * 100)}% seed có lợi)`
      + ` · cao điểm ${sign(pk.diff, 2)} pt · lợi nhuận ${sign(pr.diff / 1000, 1)}k ± ${(pr.ci / 1000).toFixed(1)}k đ/xe/ngày`
      + " · seed hiển thị là seed điển hình";
  };
  apply();
  const reload = async () => {
    const [l, r] = await load(sceneSel.value, bbSel.value);
    sides[0].setData(l);
    sides[1].setData(r);
    apply();
    render();
  };
  sceneSel.onchange = bbSel.onchange = () => { void reload(); };

  // shared view: fit, wheel zoom and drag pan apply to both maps
  let scale = 1, ox = 0, oy = 0;
  const host = sides[0].app;
  const fit = () => {
    const [w, h] = base.meta.size;
    scale = Math.min(host.screen.width / w, host.screen.height / h) * 0.98;
    ox = (host.screen.width - w * scale) / 2;
    oy = (host.screen.height + h * scale) / 2;
    sides.forEach((s) => s.view(scale, ox, oy));
  };
  const zoomAt = (f: number, sx: number, sy: number) => {
    const next = Math.min(30, Math.max(0.05, scale * f));
    const wx = (sx - ox) / scale, wy = (oy - sy) / scale;
    scale = next;
    ox = sx - wx * scale;
    oy = sy + wy * scale;
    sides.forEach((s) => s.view(scale, ox, oy));
  };
  requestAnimationFrame(fit);
  window.addEventListener("resize", () => requestAnimationFrame(fit));
  for (const s of sides) {
    const cv = s.app.canvas;
    cv.addEventListener("wheel", (e) => { e.preventDefault(); zoomAt(Math.exp(-e.deltaY * 0.0015), e.offsetX, e.offsetY); }, { passive: false });
    let drag: { x: number; y: number } | null = null;
    cv.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY }; cv.setPointerCapture(e.pointerId); });
    cv.addEventListener("pointermove", (e) => {
      if (!drag) return;
      ox += e.clientX - drag.x; oy += e.clientY - drag.y;
      drag = { x: e.clientX, y: e.clientY };
      sides.forEach((q) => q.view(scale, ox, oy));
    });
    cv.addEventListener("pointerup", () => (drag = null));
    cv.addEventListener("dblclick", fit);
  }

  // clock and controls
  const slider = document.getElementById("time") as HTMLInputElement;
  const speed = document.getElementById("speed") as HTMLSelectElement;
  const play = document.getElementById("play") as HTMLButtonElement;
  const clock = document.getElementById("clock")!;
  const gainNet = document.querySelector<HTMLDivElement>("#gain .net")!;
  const gainSaved = document.querySelector<HTMLElement>("#gain .saved")!;
  const gainLost = document.querySelector<HTMLElement>("#gain .lost")!;
  let t = q.has("t") ? Number(q.get("t")) * 3600 : 5 * 3600;
  let playing = q.has("play");
  const setPlaying = (p: boolean) => { playing = p; play.textContent = p ? "❚❚" : "▶"; };
  setPlaying(playing);
  play.onclick = () => setPlaying(!playing);
  window.addEventListener("keydown", (e) => { if (e.code === "Space") { e.preventDefault(); setPlaying(!playing); } });
  slider.oninput = () => (t = Number(slider.value));
  document.querySelectorAll<HTMLButtonElement>(".jump").forEach((b) => (b.onclick = () => (t = Number(b.dataset.h) * 3600)));

  const render = () => {
    const hh = Math.floor(t / 3600), mm = Math.floor((t % 3600) / 60);
    clock.textContent = `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
    slider.value = String(t);
    for (const s of sides) { s.draw(t); drawChart(s, t, maxQ, maxW); }
    updateKpis(sides, t);
    let saved = 0, lost = 0;
    for (const d of diffs) { if (d.t > t) break; if (d.rightServed) saved++; else lost++; }
    gainNet.textContent = `${sign(saved - lost, 0)} khách`;
    gainNet.classList.toggle("neg", saved - lost < 0);
    gainSaved.textContent = String(saved);
    gainLost.textContent = String(lost);
  };
  let lastChart = 0;
  host.ticker.add((tk) => {
    if (playing) {
      t = Math.min(86400, t + (tk.deltaMS / 1000) * Number(speed.value));
      if (t >= 86400) setPlaying(false);
    }
    const now = performance.now();
    for (const s of sides) s.draw(t);
    if (now - lastChart > 200) { render(); lastChart = now; }
  });
  render();
}

main();
