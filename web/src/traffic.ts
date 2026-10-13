import { Container, Graphics } from "pixi.js";
import { polylineLength, pointAt, type Pt } from "./geom";
import { LANE_W } from "./map";
import type { Signals } from "./signals";
import type { MapData } from "./types";

const CAR_LEN = 4.6;
const CAR_WID = 2.0;
const GAP = CAR_LEN + 2.5; // centre-to-centre distance kept to the car ahead in the same lane
const ACCEL = 2.5; // m/s²
const DEMO_COLORS = [0xd8343b, 0x2f6fd6, 0xf2c230, 0xf5f5f5, 0x2f9e5c];

interface DemoCar {
  edge: number;
  next: number; // edge taken after this one
  lane: number;
  dist: number;
  speed: number;
  cruise: number; // m/s
  sprite: Container;
}

/** A car sprite drawn in metres, pointing along +x. */
export function carSprite(color: number): Container {
  const g = new Graphics();
  g.roundRect(-CAR_LEN / 2, -CAR_WID / 2, CAR_LEN, CAR_WID, 0.6).fill(color).stroke({ width: 0.15, color: 0x1d1d1d });
  g.roundRect(0.35, -CAR_WID / 2 + 0.25, 1.1, CAR_WID - 0.5, 0.25).fill(0x26313d); // windscreen
  g.roundRect(-CAR_LEN / 2 + 0.4, -CAR_WID / 2 + 0.3, 0.7, CAR_WID - 0.6, 0.2).fill(0x3a4553); // rear window
  const c = new Container();
  c.addChild(g);
  return c;
}

/**
 * Cars wandering randomly over the road graph on the right-hand lanes. Cars in the same lane
 * keep a gap (no overtaking, no lane changes) and only enter the next road when its first
 * metres are free. Crossing traffic inside junctions is not resolved.
 * Only for checking the map; the real vehicles will come from the simulator.
 */
export class DemoTraffic {
  private readonly out: number[][];
  private readonly paths: Pt[][];
  private readonly lengths: number[];
  private cars: DemoCar[] = [];
  /** cars per "edge:lane", sorted by distance along the edge */
  private lanes = new Map<string, DemoCar[]>();

  constructor(private readonly data: MapData, private readonly layer: Container, private readonly signals?: Signals) {
    this.out = data.nodes.map(() => []);
    data.edges.forEach((e, i) => this.out[e[0]].push(i));
    this.paths = data.edges.map(([, , road, fwd]) => {
      const pts = data.roads[road].pts;
      return fwd ? pts : [...pts].reverse();
    });
    this.lengths = this.paths.map(polylineLength);
  }

  private lanesPerDir(edge: number): number {
    const road = this.data.roads[this.data.edges[edge][2]];
    return road.oneway ? road.lanes : Math.max(1, Math.floor(road.lanes / 2));
  }

  private queue(edge: number, lane: number): DemoCar[] {
    const k = `${edge}:${lane}`;
    let q = this.lanes.get(k);
    if (!q) this.lanes.set(k, (q = []));
    return q;
  }

  setCount(n: number) {
    while (this.cars.length > n) {
      const c = this.cars.pop()!;
      const q = this.queue(c.edge, c.lane);
      q.splice(q.indexOf(c), 1);
      this.layer.removeChild(c.sprite);
    }
    for (let tries = 0; this.cars.length < n && tries < n * 20; tries++) {
      const edge = Math.floor(Math.random() * this.data.edges.length);
      const lane = Math.floor(Math.random() * this.lanesPerDir(edge));
      const dist = Math.random() * this.lengths[edge];
      const q = this.queue(edge, lane);
      if (q.some((o) => Math.abs(o.dist - dist) < GAP)) continue; // spawn only into free space
      const sprite = carSprite(DEMO_COLORS[Math.floor(Math.random() * DEMO_COLORS.length)]);
      this.layer.addChild(sprite);
      const cruise = 7 + Math.random() * 6;
      const car: DemoCar = { edge, lane, dist, sprite, cruise, speed: cruise, next: this.pickNext(edge) };
      q.push(car);
      q.sort((a, b) => a.dist - b.dist);
      this.place(car);
      this.cars.push(car);
    }
  }

  /** Keep cars visible when zoomed out: never smaller than ~11 px long. */
  setZoom(scale: number) {
    const s = Math.max(1, 11 / (CAR_LEN * scale));
    for (const c of this.cars) c.sprite.scale.set(s);
  }

  step(dt: number) {
    // leaders first, so each follower sees where the car ahead has already moved to
    const order = [...this.cars].sort((a, b) => b.dist / this.lengths[b.edge] - a.dist / this.lengths[a.edge]);
    for (const c of order) {
      c.speed = Math.min(c.cruise, c.speed + ACCEL * dt);
      let target = c.dist + c.speed * dt;
      const q = this.queue(c.edge, c.lane);
      const ahead = q[q.indexOf(c) + 1];
      if (ahead) target = Math.min(target, ahead.dist - GAP);
      const len = this.lengths[c.edge];
      // traffic light at the end of this road: stop at the line on red, and on amber
      // unless already too close to stop
      const light = ahead ? null : this.signals?.light(c.edge);
      if (light && light !== "green") {
        const stop = this.signals!.stopAt(c.edge);
        if (light === "red" ? c.dist <= stop : c.dist < stop - 4) target = Math.min(target, stop);
      }

      if (target > len && !ahead) {
        // try to move onto the next road; wait at the end of this one if its entry is busy
        const lane = Math.min(c.lane, this.lanesPerDir(c.next) - 1);
        const nq = this.queue(c.next, lane);
        const room = nq.length ? nq[0].dist - GAP : Infinity;
        const over = target - len;
        if (over <= room && over >= 0) {
          q.splice(q.indexOf(c), 1);
          c.edge = c.next;
          c.lane = lane;
          c.dist = Math.min(over, this.lengths[c.edge]);
          nq.unshift(c);
          c.next = this.pickNext(c.edge);
        } else {
          c.dist = len;
          c.speed = 0;
        }
      } else {
        // blocked by the car ahead: move only as far as the gap allows, and slow to that speed
        const moved = Math.max(c.dist, Math.min(target, len));
        if (dt > 0) c.speed = Math.min(c.speed, (moved - c.dist) / dt);
        c.dist = moved;
      }
      this.place(c);
    }
  }

  /** Cars currently stopped at a red light. */
  waitingAtRed(): number {
    return this.cars.filter((c) => this.signals?.light(c.edge) === "red" && c.speed < 0.1).length;
  }

  /** Pairs of cars in the same lane closer than the gap, and pairs anywhere within 2 m. */
  overlaps(): { sameLane: number; anywhere: number } {
    let sameLane = 0;
    for (const q of this.lanes.values()) for (let i = 1; i < q.length; i++) if (q[i].dist - q[i - 1].dist < GAP - 0.01) sameLane++;
    let anywhere = 0;
    for (let i = 0; i < this.cars.length; i++) {
      for (let j = i + 1; j < this.cars.length; j++) {
        const a = this.cars[i].sprite.position, b = this.cars[j].sprite.position;
        if (Math.hypot(a.x - b.x, a.y - b.y) < 2) anywhere++;
      }
    }
    return { sameLane, anywhere };
  }

  private pickNext(edge: number): number {
    const [from, to] = this.data.edges[edge];
    const options = this.out[to];
    const forward = options.filter((e) => this.data.edges[e][1] !== from); // avoid U-turns
    const pool = forward.length ? forward : options;
    return pool.length ? pool[Math.floor(Math.random() * pool.length)] : edge;
  }

  private place(c: DemoCar) {
    const road = this.data.roads[this.data.edges[c.edge][2]];
    const { p, dir } = pointAt(this.paths[c.edge], c.dist);
    // right-hand traffic: two-way roads use the lanes right of the centre line
    const off = road.oneway ? ((road.lanes - 1) / 2 - c.lane) * LANE_W : -(c.lane + 0.5) * LANE_W;
    c.sprite.position.set(p[0] - dir[1] * off, p[1] + dir[0] * off);
    c.sprite.rotation = Math.atan2(dir[1], dir[0]);
  }
}
