import { Container, Graphics, Text } from "pixi.js";
import { dashes, offset, polylineLength, pointAt, slice, type Pt } from "./geom";
import type { MapData, Road } from "./types";

export const LANE_W = 3.2; // metres

const C = {
  ground: 0xe6dcc6,
  area: 0xece3cf,
  curb: 0xc4b89f,
  asphalt: 0x4a4f5b,
  yellow: 0xf2c94c,
  white: 0xf3f3f0,
  shadow: 0x2a2620,
  park: 0x86c05f,
  parkEdge: 0x5f9a43,
  pitch: 0x5fae5f,
  water: 0x86cbe6,
  waterEdge: 0x4fa3c7,
  boundary: 0x2e7d32,
  station: 0x22a06b,
  zone: 0x7a5c48,
};

const BUILDING: Record<string, [number, number]> = {
  // fill, outline
  residential: [0x9aa3c9, 0xf4f2fb],
  edu: [0x7fb4e6, 0xeef6ff],
  mall: [0xf2a35e, 0xfff3e6],
  office: [0x8fd3e8, 0xf0fbff],
  hospital: [0xf4f4f4, 0xd94848],
  depot: [0xa0a7b0, 0xf0f0f0],
  construction: [0xd9cba8, 0xb8a983],
};

// other buildings: plain muted blocks so Vin buildings stand out
const BLOCK_FILLS = [0xd3c5a8, 0xcdc4b3, 0xd8c9ad, 0xc8c0b2, 0xd1c2a2];
const BLOCK_EDGE = 0xf2ebdc;

const LABEL_INK: Record<string, number> = {
  edu: 0x1f5f9e, mall: 0xb5591a, office: 0x1d7f99, hospital: 0xc23a3a, depot: 0x50565e, residential: 0x4a4f7a,
};

export function roadWidth(r: Road): number {
  return Math.max(r.link ? 4.5 : 5.5, r.lanes * LANE_W);
}

function flat(pts: Pt[]): number[] {
  return pts.flatMap((p) => p);
}

function strokePath(g: Graphics, pts: Pt[], width: number, color: number, alpha = 1) {
  if (pts.length < 2) return;
  g.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]);
  g.stroke({ width, color, alpha, cap: "round", join: "round" });
}

/** Screen-size-constant children: re-scaled on every zoom change. */
export class ScreenSized {
  readonly items: Container[] = [];
  add(c: Container) {
    this.items.push(c);
    return c;
  }
  update(scale: number) {
    for (const c of this.items) c.scale.set(1 / scale, -1 / scale);
  }
}

export interface MapLayers {
  root: Container;
  green: Container;
  blocks: Container;
  vin: Container;
  stations: Container;
  labels: Container;
  boundary: Container;
  traffic: Container;
  screenSized: ScreenSized;
  setZoom(scale: number): void;
}

export function buildMap(data: MapData): MapLayers {
  const root = new Container();
  const screenSized = new ScreenSized();

  // ground and the Ocean Park area
  const base = new Graphics();
  base.rect(0, 0, data.meta.size[0], data.meta.size[1]).fill(C.ground);
  for (const ring of data.boundary) base.poly(flat(ring)).fill(C.area);
  root.addChild(base);

  // parks and water: plain shapes
  const green = new Graphics();
  for (const f of data.green) {
    const pitch = f.kind === "pitch";
    for (const ring of f.rings) green.poly(flat(ring)).fill(pitch ? C.pitch : C.park).stroke({ width: 0.8, color: C.parkEdge });
  }
  for (const f of data.water) for (const ring of f.rings) green.poly(flat(ring)).fill(C.water).stroke({ width: 1.2, color: C.waterEdge });
  root.addChild(green);

  // roads: curbs, then asphalt for every road, then markings on top so junctions stay clean
  const degree = new Map<string, number>();
  const key = (p: Pt) => `${Math.round(p[0])},${Math.round(p[1])}`;
  for (const r of data.roads) for (const p of [r.pts[0], r.pts[r.pts.length - 1]]) degree.set(key(p), (degree.get(key(p)) ?? 0) + 1);

  const curbs = new Graphics();
  const asphalt = new Graphics();
  const marks = new Graphics();
  const order = [...data.roads].sort((a, b) => roadWidth(a) - roadWidth(b));
  for (const r of order) strokePath(curbs, r.pts, roadWidth(r) + 3, C.curb);
  for (const r of order) strokePath(asphalt, r.pts, roadWidth(r), C.asphalt);
  for (const r of data.roads) drawMarkings(marks, r, degree, key);
  root.addChild(curbs, asphalt, marks);

  // other buildings: same block style as Vin buildings, muted colours, no labels
  const blocks = new Container();
  const blockShadows = new Graphics();
  const blockRoofs = new Graphics();
  data.blocks.forEach((b, i) => {
    for (const ring of b.rings) {
      blockShadows.poly(flat(ring.map(([x, y]) => [x + 2, y - 2] as Pt))).fill({ color: C.shadow, alpha: 0.16 });
      blockRoofs.poly(flat(ring)).fill(BLOCK_FILLS[i % BLOCK_FILLS.length]).stroke({ width: 0.6, color: BLOCK_EDGE });
    }
  });
  blocks.addChild(blockShadows, blockRoofs);
  root.addChild(blocks);

  // Vin buildings: drop shadow + flat roof + light outline
  const vin = new Container();
  const shadows = new Graphics();
  const roofs = new Graphics();
  for (const b of data.vin) {
    const [fill, edge] = BUILDING[b.cat] ?? BUILDING.residential;
    for (const ring of b.rings) {
      shadows.poly(flat(ring.map(([x, y]) => [x + 3, y - 3] as Pt))).fill({ color: C.shadow, alpha: 0.22 });
      roofs.poly(flat(ring)).fill(fill).stroke({ width: 1, color: edge });
    }
  }
  vin.addChild(shadows, roofs);
  root.addChild(vin);

  const boundary = new Graphics();
  for (const ring of data.boundary) {
    for (const d of dashes(ring, 14, 10)) strokePath(boundary, d, 2.2, C.boundary, 0.8);
  }
  root.addChild(boundary);

  // charging stations (constant screen size)
  const stations = new Container();
  for (const s of data.stations) {
    const icon = new Container();
    const g = new Graphics();
    g.circle(0, 0, 9).fill(C.station).stroke({ width: 2, color: 0xffffff });
    g.poly([1.5, -7, -4, 1, 0, 1, -1.5, 7, 4, -1, 0, -1]).fill(0xffffff); // lightning bolt
    icon.addChild(g);
    icon.position.set(s.at[0], s.at[1]);
    stations.addChild(screenSized.add(icon));
  }
  root.addChild(stations);

  const traffic = new Container();
  root.addChild(traffic);

  // landmark and zone labels (constant screen size)
  const labels = new Container();
  for (const z of data.zones) labels.addChild(screenSized.add(makeLabel(z.name, z.at, C.zone, true)));
  for (const l of data.labels) labels.addChild(screenSized.add(makeLabel(l.name, l.at, LABEL_INK[l.cat] ?? 0x333333, false)));
  root.addChild(labels);

  return {
    root, green, blocks, vin, stations, labels, boundary, traffic, screenSized,
    setZoom(scale: number) {
      screenSized.update(scale);
      // zone names only once zoomed in a bit
      for (const c of labels.children) if ((c as Container).label === "zone") c.visible = scale > 0.35;
    },
  };
}

function makeLabel(text: string, at: Pt, color: number, italic: boolean): Container {
  const t = new Text({
    text,
    resolution: 2,
    style: {
      fontFamily: "system-ui, Segoe UI, Roboto, sans-serif",
      fontSize: italic ? 11 : 12,
      fontWeight: italic ? "400" : "700",
      fontStyle: italic ? "italic" : "normal",
      fill: color,
      stroke: { color: 0xffffff, width: 3, join: "round" },
    },
  });
  t.anchor.set(0.5);
  const c = new Container();
  c.label = italic ? "zone" : "landmark";
  c.addChild(t);
  c.position.set(at[0], at[1]);
  return c;
}

function drawMarkings(g: Graphics, r: Road, degree: Map<string, number>, key: (p: Pt) => string) {
  const len = polylineLength(r.pts);
  const w = roadWidth(r);
  // keep markings out of junction boxes
  const trimA = (degree.get(key(r.pts[0])) ?? 0) >= 3 ? w * 0.9 + 4 : 0;
  const trimB = (degree.get(key(r.pts[r.pts.length - 1])) ?? 0) >= 3 ? w * 0.9 + 4 : 0;
  if (len - trimA - trimB < 12) return;
  const pts = slice(r.pts, trimA, len - trimB);
  const major = ["trunk", "primary", "secondary", "tertiary"].includes(r.cls);

  if (r.oneway) {
    for (let j = 1; j < r.lanes; j++) {
      for (const d of dashes(offset(pts, (j - r.lanes / 2) * LANE_W), 3, 5)) strokePath(g, d, 0.15, C.white);
    }
  } else {
    const perDir = Math.max(1, Math.floor(r.lanes / 2));
    if (r.lanes >= 4) {
      strokePath(g, offset(pts, 0.22), 0.16, C.yellow);
      strokePath(g, offset(pts, -0.22), 0.16, C.yellow);
    } else {
      for (const d of dashes(pts, 3, 4)) strokePath(g, d, 0.16, C.yellow);
    }
    for (let j = 1; j < perDir; j++) {
      for (const side of [1, -1]) for (const d of dashes(offset(pts, side * j * LANE_W), 3, 5)) strokePath(g, d, 0.14, C.white);
    }
  }

  // zebra crossings where major roads meet a junction
  if (major && len > 40) {
    if (trimA > 0) zebra(g, r.pts, trimA - 2.5, w);
    if (trimB > 0) zebra(g, r.pts, len - trimB + 2.5, w);
  }
}

function zebra(g: Graphics, pts: Pt[], at: number, width: number) {
  const { p, dir } = pointAt(pts, at);
  const n: Pt = [-dir[1], dir[0]];
  const half = width / 2 - 0.4;
  for (let s = -half; s < half - 0.3; s += 1.1) {
    // stripe 0.55 m wide across the road, 3 m long along it
    const cx = p[0] + n[0] * (s + 0.27);
    const cy = p[1] + n[1] * (s + 0.27);
    const ax = dir[0] * 1.5, ay = dir[1] * 1.5, bx = n[0] * 0.27, by = n[1] * 0.27;
    g.poly([cx - ax - bx, cy - ay - by, cx + ax - bx, cy + ay - by, cx + ax + bx, cy + ay + by, cx - ax + bx, cy - ay + by])
      .fill({ color: C.white, alpha: 0.9 });
  }
}
