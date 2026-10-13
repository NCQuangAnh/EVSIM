import { Application, Container, Text } from "pixi.js";
import { buildMap } from "./map";
import { Signals } from "./signals";
import { DemoTraffic } from "./traffic";
import type { MapData } from "./types";

const PANEL_W = 272; // left panel incl. margin, kept clear when fitting the map

async function main() {
  const data: MapData = await (await fetch("/data/oceanpark.json")).json();
  document.getElementById("attr")!.textContent = data.meta.attribution;

  const app = new Application();
  await app.init({ resizeTo: window, antialias: true, background: 0xe6dcc6, autoDensity: true, resolution: devicePixelRatio });
  document.getElementById("map")!.appendChild(app.canvas);

  const q = new URLSearchParams(location.search);
  const map = buildMap(data);
  app.stage.addChild(map.root);
  const signals = new Signals(data, map.screenSized);
  map.root.addChildAt(signals.layer, map.root.getChildIndex(map.traffic));
  const traffic = new DemoTraffic(data, map.traffic, signals);
  if (q.has("signalIds")) {
    // debug: number every traffic light controller
    data.signals.forEach((sg, i) => {
      const t = new Text({ text: String(i), resolution: 2, style: { fontSize: 13, fontWeight: "700", fill: 0xffffff, stroke: { color: 0x000000, width: 3 } } });
      t.anchor.set(0.5);
      const c = new Container();
      c.addChild(t);
      c.position.set(sg.at[0], sg.at[1]);
      map.labels.addChild(map.screenSized.add(c));
    });
  }

  // --- view: world units are metres with y up; screen y goes down ---
  let scale = 1;
  const apply = () => {
    map.root.scale.set(scale, -scale);
    map.setZoom(scale);
    traffic.setZoom(scale);
  };
  const fit = () => {
    const [w, h] = data.meta.size;
    const sideBySide = app.screen.width > 700;
    const availW = app.screen.width - (sideBySide ? PANEL_W : 0) - 24;
    scale = Math.min(availW / w, (app.screen.height - 24) / h);
    map.root.position.set((sideBySide ? PANEL_W : 0) + (availW - w * scale) / 2 + 12,
      (app.screen.height + h * scale) / 2);
    apply();
  };
  const zoomAt = (factor: number, sx: number, sy: number) => {
    const next = Math.min(40, Math.max(0.05, scale * factor));
    const wx = (sx - map.root.x) / scale;
    const wy = (map.root.y - sy) / scale;
    scale = next;
    map.root.position.set(sx - wx * scale, sy + wy * scale);
    apply();
  };
  // optional start view: ?x=<m>&y=<m>&z=<px per m>, e.g. ?x=1500&y=1100&z=4
  const showAt = () => {
    if (!q.has("z")) return fit();
    scale = Number(q.get("z"));
    map.root.position.set(app.screen.width / 2 - Number(q.get("x")) * scale,
      app.screen.height / 2 + Number(q.get("y")) * scale);
    apply();
  };
  showAt();
  window.addEventListener("resize", () => requestAnimationFrame(showAt));

  const canvas = app.canvas;
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    zoomAt(Math.exp(-e.deltaY * 0.0015), e.offsetX, e.offsetY);
  }, { passive: false });
  let drag: { x: number; y: number } | null = null;
  canvas.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    map.root.position.set(map.root.x + e.clientX - drag.x, map.root.y + e.clientY - drag.y);
    drag = { x: e.clientX, y: e.clientY };
  });
  canvas.addEventListener("pointerup", () => (drag = null));
  const center = () => [app.screen.width / 2, app.screen.height / 2] as const;
  document.getElementById("zoom-in")!.onclick = () => zoomAt(1.5, ...center());
  document.getElementById("zoom-out")!.onclick = () => zoomAt(1 / 1.5, ...center());
  document.getElementById("zoom-fit")!.onclick = fit;

  // --- layer toggles ---
  const layers = {
    green: map.green, blocks: map.blocks, vin: map.vin, stations: map.stations, labels: map.labels, boundary: map.boundary,
    signals: signals.layer,
  };
  document.querySelectorAll<HTMLInputElement>("input[data-layer]").forEach((box) => {
    box.onchange = () => (layers[box.dataset.layer as keyof typeof layers].visible = box.checked);
  });

  // --- demo traffic ---
  const on = document.getElementById("demo-on") as HTMLInputElement;
  const count = document.getElementById("demo-count") as HTMLInputElement;
  const speed = document.getElementById("demo-speed") as HTMLInputElement;
  const syncCount = () => {
    traffic.setCount(on.checked ? Number(count.value) : 0);
    traffic.setZoom(scale);
    document.getElementById("demo-count-v")!.textContent = count.value;
  };
  if (q.has("n")) count.value = q.get("n")!;
  on.onchange = count.oninput = syncCount;
  speed.oninput = () => (document.getElementById("demo-speed-v")!.textContent = `${speed.value}×`);
  syncCount();
  if (q.has("selftest")) {
    // run 5 simulated minutes at once and report car spacing in the page title
    let maxRed = 0;
    for (let i = 0; i < 3000; i++) {
      signals.step(0.1);
      traffic.step(0.1);
      maxRed = Math.max(maxRed, traffic.waitingAtRed());
    }
    const o = traffic.overlaps();
    document.title = `selftest sameLane=${o.sameLane} anywhere=${o.anywhere} maxWaitingAtRed=${maxRed}`;
  }
  app.ticker.add((t) => {
    const dt = (t.deltaMS / 1000) * Number(speed.value);
    signals.step(dt);
    traffic.step(dt);
  });
}

main();
