import { Container, Graphics } from "pixi.js";
import { pointAt, polylineLength, type Pt } from "./geom";
import { LANE_W, roadWidth, type ScreenSized } from "./map";
import type { MapData } from "./types";

/**
 * Two-phase fixed-time traffic lights (assumption: 60 s cycle, 25 s green + 3 s amber +
 * 2 s all-red per phase). Approaches are split into two phases by their heading: roughly
 * parallel approaches share a phase, crossing ones take the other.
 */
const GREEN = 25;
const AMBER = 3;
const ALL_RED = 2;
const PHASE = GREEN + AMBER + ALL_RED;
const CYCLE = 2 * PHASE;
const STOP_BACK = 9; // stop line, metres before the end of the approach road

export type Light = "green" | "amber" | "red";
const COLOR: Record<Light, number> = { green: 0x2fbf5b, amber: 0xf2b630, red: 0xe0453a };

interface Approach {
  edge: number;
  signal: number;
  phase: 0 | 1;
  head: Graphics;
  shown?: Light;
}

export class Signals {
  readonly layer = new Container();
  private readonly approaches = new Map<number, Approach>();
  private readonly offsets: number[];
  private readonly lengths: number[];
  time = 0;

  constructor(private readonly data: MapData, screenSized: ScreenSized) {
    const paths = data.edges.map(([, , road, fwd]) => (fwd ? data.roads[road].pts : [...data.roads[road].pts].reverse()));
    this.lengths = paths.map(polylineLength);
    // spread start times so neighbouring lights do not switch together
    this.offsets = data.signals.map((_, i) => (i * 23) % CYCLE);
    const stopLines = new Graphics();

    data.signals.forEach((s, si) => {
      const group = new Set(s.nodes);
      const incoming = data.edges
        .map((e, i) => ({ e, i }))
        .filter(({ e }) => group.has(e[1]) && !group.has(e[0]));
      let refAngle: number | null = null;
      for (const { e, i } of incoming) {
        const len = this.lengths[i];
        const { p, dir } = pointAt(paths[i], Math.max(0, len - Math.min(STOP_BACK, len / 2)));
        const angle = Math.atan2(dir[1], dir[0]);
        if (refAngle === null) refAngle = angle;
        const diff = Math.abs(((angle - refAngle) % Math.PI + Math.PI) % Math.PI);
        const phase: 0 | 1 = diff < Math.PI / 4 || diff > (3 * Math.PI) / 4 ? 0 : 1;

        // white stop line across the approach lanes, signal head at the kerb on the right
        const road = data.roads[e[2]];
        const w = road.oneway ? roadWidth(road) : roadWidth(road) / 2;
        const right: Pt = [dir[1], -dir[0]];
        const from = road.oneway ? -w / 2 : 0;
        const a: Pt = [p[0] + right[0] * from, p[1] + right[1] * from];
        const b: Pt = [p[0] + right[0] * (from + w), p[1] + right[1] * (from + w)];
        stopLines.moveTo(a[0], a[1]).lineTo(b[0], b[1]).stroke({ width: 0.45, color: 0xf3f3f0 });

        const head = new Graphics();
        const holder = new Container();
        holder.addChild(head);
        holder.position.set(b[0] + right[0] * (LANE_W * 0.4), b[1] + right[1] * (LANE_W * 0.4));
        this.layer.addChild(screenSized.add(holder));
        this.approaches.set(i, { edge: i, signal: si, phase, head });
      }
    });
    this.layer.addChildAt(stopLines, 0);
    this.redraw();
  }

  /** Light shown to cars on this road edge, or null if its end has no signal. */
  light(edge: number): Light | null {
    const a = this.approaches.get(edge);
    if (!a) return null;
    const t = (this.time + this.offsets[a.signal]) % CYCLE - a.phase * PHASE;
    if (t >= 0 && t < GREEN) return "green";
    if (t >= GREEN && t < GREEN + AMBER) return "amber";
    return "red";
  }

  /** Distance along the edge where cars must stop when the light is not green. */
  stopAt(edge: number): number {
    const len = this.lengths[edge];
    return Math.max(0, len - Math.min(STOP_BACK, len / 2));
  }

  step(dt: number) {
    this.time += dt;
    this.redraw();
  }

  private redraw() {
    for (const a of this.approaches.values()) {
      const l = this.light(a.edge)!;
      if (a.shown === l) continue;
      a.shown = l;
      a.head.clear();
      a.head.roundRect(-6.5, -6.5, 13, 13, 3.5).fill(0x23272e).stroke({ width: 1.5, color: 0xffffff });
      a.head.circle(0, 0, 4.2).fill(COLOR[l]);
    }
  }
}
