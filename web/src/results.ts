// "Kết quả" panel of the replay page: pick a scenario, a black box and any subset of the 20 seeds, and get the
// comparison table "black box + battery layer | black box | difference (%)" averaged over the chosen runs.
// Data: /data/ocp1_runs.json (scripts/ocp1_demo.py stats), one record per (scene, black box, arm, seed).

interface Run { scene: string; bb: string; arm: "base" | "v21"; seed: number; m: number[] }
interface RunsFile { keys: string[]; runs: Run[] }

/** Display rows: metric key, label, unit kind, which direction is better. */
const ROWS: { key: string; label: string; kind: "pct" | "min" | "vnd" | "count"; better: 1 | -1 | 0 }[] = [
  { key: "service_level", label: "Tỉ lệ phục vụ", kind: "pct", better: 1 },
  { key: "service_level_peak", label: "Tỉ lệ phục vụ giờ cao điểm", kind: "pct", better: 1 },
  { key: "profit_adj_per_vehicle_day_vnd", label: "Lợi nhuận/xe/ngày", kind: "vnd", better: 1 },
  { key: "ride_reject_soc_share", label: "Tỉ trọng từ chối do pin", kind: "pct", better: -1 },
  { key: "peak_share_charging", label: "Xe đang sạc trong giờ cao điểm", kind: "pct", better: -1 },
  { key: "wait_min_mean", label: "Thời gian chờ trung bình của khách", kind: "min", better: -1 },
  { key: "wait_min_p90", label: "Thời gian chờ P90 của khách", kind: "min", better: -1 },
  { key: "charge_queue_min_mean", label: "Thời gian chờ ở trạm sạc", kind: "min", better: -1 },
  { key: "strandings_per_day", label: "Xe cạn pin giữa đường/ngày", kind: "count", better: -1 },
  { key: "energy_cost_adj_vnd_day", label: "Chi phí điện (điều chỉnh)/ngày", kind: "vnd", better: -1 },
  { key: "charge_sessions_per_day", label: "Lượt sạc/ngày", kind: "count", better: 0 },
  { key: "charge_nudges_per_day", label: "Lượt gợi ý sạc/ngày", kind: "count", better: 0 },
];

const BB_NAME: Record<string, string> = {
  b1: "B1 kiểu GSM", b0: "B0 greedy", b6: "B6 giá trị chuyến", b2: "B2 forward + repositioning", didi: "DiDi",
};
const SCENE_NAME: Record<string, string> = {
  normal: "Ocean Park 1 · Bình thường", harsh: "Ocean Park 1 · Khắc nghiệt (stress)", hanoi: "Hà Nội · quy mô đầy đủ",
};

// two-sided 95 % Student t quantiles, df = 1..30 (df > 30: 1.96)
const T975 = [12.71, 4.30, 3.18, 2.78, 2.57, 2.45, 2.36, 2.31, 2.26, 2.23, 2.20, 2.18, 2.16, 2.14, 2.13, 2.12, 2.11,
  2.10, 2.09, 2.09, 2.08, 2.07, 2.07, 2.06, 2.06, 2.06, 2.05, 2.05, 2.05, 2.04];

/** Number in Vietnamese format: "," decimals, "." thousands. */
const num = (v: number, d: number) => v.toLocaleString("vi-VN", { minimumFractionDigits: d, maximumFractionDigits: d });

function fmt(v: number, kind: string): string {
  if (kind === "pct") return `${num(v * 100, 2)}%`;
  if (kind === "min") return `${num(v, 2)} phút`;
  if (kind === "vnd") return `${num(Math.round(v), 0)} đ`;
  return num(v, Math.abs(v) < 10 ? 2 : 1);
}

function fmtDiff(d: number, kind: string): string {
  const s = d >= 0 ? "+" : "−";
  const a = Math.abs(d);
  if (kind === "pct") return `${s}${num(a * 100, 2)} điểm`;
  if (kind === "min") return `${s}${num(a, 2)} phút`;
  if (kind === "vnd") return `${s}${num(Math.round(a), 0)} đ`;
  return `${s}${num(a, 2)}`;
}

export async function initResults(current: () => { scene: string; bb: string }) {
  const data = (await (await fetch("/data/ocp1_runs.json")).json()) as RunsFile;
  const idx = Object.fromEntries(data.keys.map((k, i) => [k, i]));
  const scenes = [...new Set(data.runs.map((r) => r.scene))];
  const bbs = [...new Set(data.runs.map((r) => r.bb))];

  const overlay = document.createElement("div");
  overlay.id = "results";
  overlay.hidden = true;
  overlay.innerHTML = `
    <div class="panel" role="dialog" aria-label="Kết quả">
      <div class="head">
        <strong>Kết quả: luật ghép có và không có lớp pin</strong>
        <button class="close" title="Đóng (Esc)">✕</button>
      </div>
      <div class="pick">
        <label>Kịch bản <select class="r-scene"></select></label>
        <label>Luật ghép <select class="r-bb"></select></label>
        <span class="seed-tools">Seed: <button class="all">tất cả</button><button class="none">bỏ chọn</button></span>
      </div>
      <div class="seeds"></div>
      <table><thead></thead><tbody></tbody></table>
      <p class="foot"></p>
    </div>`;
  document.body.appendChild(overlay);
  const $ = <T extends Element>(s: string) => overlay.querySelector(s) as T;
  const sceneSel = $<HTMLSelectElement>(".r-scene"), bbSel = $<HTMLSelectElement>(".r-bb");
  for (const s of scenes) sceneSel.add(new Option(SCENE_NAME[s] ?? s, s));
  const fillBbs = () => {   // black boxes that have runs in the chosen scenario
    const keep = bbSel.value;
    bbSel.innerHTML = "";
    for (const b of bbs) if (data.runs.some((r) => r.scene === sceneSel.value && r.bb === b)) bbSel.add(new Option(BB_NAME[b] ?? b, b));
    if ([...bbSel.options].some((o) => o.value === keep)) bbSel.value = keep;
  };
  const seedBox = $<HTMLDivElement>(".seeds");
  const chosen = new Set<number>();

  const pairs = () => {
    const sel = data.runs.filter((r) => r.scene === sceneSel.value && r.bb === bbSel.value);
    const by = new Map<number, { base?: Run; v21?: Run }>();
    for (const r of sel) by.set(r.seed, { ...by.get(r.seed), [r.arm]: r });
    return [...by.entries()].filter(([, p]) => p.base && p.v21).sort((a, b) => a[0] - b[0]);
  };

  const drawSeeds = () => {
    seedBox.innerHTML = "";
    for (const [seed] of pairs()) {
      const b = document.createElement("button");
      b.textContent = String(seed);
      b.className = chosen.has(seed) ? "on" : "";
      b.onclick = () => { chosen.has(seed) ? chosen.delete(seed) : chosen.add(seed); drawSeeds(); drawTable(); };
      seedBox.appendChild(b);
    }
  };

  const drawTable = () => {
    const name = BB_NAME[bbSel.value] ?? bbSel.value;
    $<HTMLElement>("thead").innerHTML =
      `<tr><th>Chỉ số</th><th>${name} + lớp pin</th><th>${name}</th><th>Chênh lệch (%)</th></tr>`;
    const ps = pairs().filter(([s]) => chosen.has(s)).map(([, p]) => p as { base: Run; v21: Run });
    const n = ps.length;
    const body = $<HTMLElement>("tbody");
    if (!n) {
      body.innerHTML = `<tr><td colspan="4" class="empty">Chọn ít nhất một seed.</td></tr>`;
      $<HTMLElement>(".foot").textContent = "";
      return;
    }
    const mean = (a: number[]) => a.reduce((x, y) => x + y, 0) / a.length;
    body.innerHTML = ROWS.map((row) => {
      const i = idx[row.key];
      const v = ps.map((p) => p.v21.m[i]), b = ps.map((p) => p.base.m[i]);
      const mv = mean(v), mb = mean(b);
      const d = v.map((x, k) => x - b[k]), md = mean(d);
      const sd = n > 1 ? Math.sqrt(d.reduce((s, x) => s + (x - md) ** 2, 0) / (n - 1)) : NaN;
      const h = n > 1 ? (T975[Math.min(n - 1, 30) - 1] ?? 1.96) * sd / Math.sqrt(n) : NaN;
      const sig = n > 1 && Math.abs(md) > h;
      const rel = Math.abs(mb) > 1e-9 ? (mv / mb - 1) * 100 : NaN;
      const tone = row.better === 0 || !sig ? "neutral" : Math.sign(md) === row.better ? "good" : "bad";
      const relTxt = Number.isFinite(rel) ? `${rel >= 0 ? "+" : "−"}${num(Math.abs(rel), 2)}%` : "—";
      const tip = `Chênh lệch tuyệt đối ${fmtDiff(md, row.kind)}` + (n > 1 ? ` ± ${fmtDiff(h, row.kind).slice(1)} (KTC 95%)` : "")
        + ` · ${d.filter((x) => Math.sign(x) === row.better && x !== 0).length}/${n} seed theo hướng tốt`;
      return `<tr><td>${row.label}</td><td>${fmt(mv, row.kind)}</td><td>${fmt(mb, row.kind)}</td>`
        + `<td class="${tone}" title="${tip}">${relTxt}${sig ? "" : " <small>(chưa rõ)</small>"}</td></tr>`;
    }).join("");
    $<HTMLElement>(".foot").textContent =
      `Trung bình ${n} seed, so theo cặp (cùng seed hai bên). Xanh: tốt hơn và có ý nghĩa thống kê `
      + `(KTC 95% không chứa 0); đỏ: xấu hơn và có ý nghĩa; "(chưa rõ)": khoảng tin cậy chứa 0 hoặc chỉ có 1 seed. `
      + `Rê chuột lên ô chênh lệch để xem chênh lệch tuyệt đối. Lợi nhuận và chi phí điện đã điều chỉnh theo năng lượng còn trong pin.`;
  };

  const open = () => {
    const c = current();
    sceneSel.value = c.scene;
    fillBbs();
    bbSel.value = c.bb;
    chosen.clear();
    for (const [s] of pairs()) chosen.add(s);
    drawSeeds();
    drawTable();
    overlay.hidden = false;
  };
  const close = () => { overlay.hidden = true; };
  const resetSeeds = () => { chosen.clear(); for (const [s] of pairs()) chosen.add(s); drawSeeds(); drawTable(); };
  sceneSel.onchange = () => { fillBbs(); resetSeeds(); };
  bbSel.onchange = resetSeeds;
  $<HTMLButtonElement>(".all").onclick = resetSeeds;
  $<HTMLButtonElement>(".none").onclick = () => { chosen.clear(); drawSeeds(); drawTable(); };
  $<HTMLButtonElement>(".close").onclick = close;
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  window.addEventListener("keydown", (e) => { if (e.key === "Escape" && !overlay.hidden) close(); }, true);
  document.getElementById("results-btn")!.addEventListener("click", open);
}
