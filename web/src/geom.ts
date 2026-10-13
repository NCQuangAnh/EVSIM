export type Pt = [number, number];

export function polylineLength(pts: Pt[]): number {
  let len = 0;
  for (let i = 1; i < pts.length; i++) len += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  return len;
}

/** Point and unit direction at distance d along a polyline. */
export function pointAt(pts: Pt[], d: number): { p: Pt; dir: Pt } {
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const seg = Math.hypot(x1 - x0, y1 - y0);
    if (d <= seg || i === pts.length - 1) {
      const t = seg > 0 ? Math.min(1, Math.max(0, d / seg)) : 0;
      const dir: Pt = seg > 0 ? [(x1 - x0) / seg, (y1 - y0) / seg] : [1, 0];
      return { p: [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t], dir };
    }
    d -= seg;
  }
  return { p: pts[0], dir: [1, 0] };
}

/** Part of a polyline between distances a and b. */
export function slice(pts: Pt[], a: number, b: number): Pt[] {
  const out: Pt[] = [pointAt(pts, a).p];
  let acc = 0;
  for (let i = 1; i < pts.length; i++) {
    acc += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    if (acc > a && acc < b) out.push(pts[i]);
  }
  out.push(pointAt(pts, b).p);
  return out;
}

/** Parallel polyline at signed distance d (positive = left of travel direction). */
export function offset(pts: Pt[], d: number): Pt[] {
  const n = pts.length;
  const normals: Pt[] = [];
  for (let i = 0; i < n - 1; i++) {
    const dx = pts[i + 1][0] - pts[i][0];
    const dy = pts[i + 1][1] - pts[i][1];
    const len = Math.hypot(dx, dy) || 1;
    normals.push([-dy / len, dx / len]);
  }
  return pts.map((p, i) => {
    const a = normals[Math.max(0, i - 1)];
    const b = normals[Math.min(n - 2, i)];
    let nx = a[0] + b[0];
    let ny = a[1] + b[1];
    const len = Math.hypot(nx, ny) || 1;
    nx /= len;
    ny /= len;
    // miter length, capped so sharp bends do not spike
    const cos = Math.max(0.5, nx * b[0] + ny * b[1]);
    return [p[0] + (nx * d) / cos, p[1] + (ny * d) / cos] as Pt;
  });
}

/** Split a polyline into dash pieces. */
export function dashes(pts: Pt[], dash: number, gap: number): Pt[][] {
  const total = polylineLength(pts);
  const out: Pt[][] = [];
  for (let s = 0; s < total; s += dash + gap) out.push(slice(pts, s, Math.min(total, s + dash)));
  return out;
}
