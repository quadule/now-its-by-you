// A small perspective camera for scenes with depth: receding envelope lines, the wall of screens, the drum
// skin, the strings. World units are free; the camera projects them into design units.
//
//   const cam = new Camera({position: [0, 0, -10], target: [0, 0, 0], up: [0, -1, 0], fov: 35, size: ctx.size})
//   cam.project([x, y, z]) -> {x, y, depth, scale, visible}   design units; depth along the view; scale: design units per world unit there
//   stroke3(ctx.g, target, cam, points3, {width, alpha, color, intensity, blend, fog: [near, far]})
//   strokes3(ctx.g, target, cam, [{points, ...opts}, ...])   several lines, drawn far to near
//   points3(ctx.g, target, cam, [{p: [x, y, z], r, color, alpha, intensity, soft}], {fog})
//
// Widths and radii are in world units and shrink with distance; fog fades alpha from 1 at fog[0] to 0 at fog[1].
// Lines are cut where they pass behind the near plane. Up is -y by default, so y down matches design units.
import { smoothstep } from './math.js';

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };

export class Camera {
  constructor({ position = [0, 0, -10], target = [0, 0, 0], up = [0, -1, 0], fov = 35, near = 0.05, size = { w: 1920, h: 1080 },
    center = null } = {}) {
    this.position = position; this.target = target; this.up = up; this.fov = fov; this.near = near;
    this.w = size.w; this.h = size.h;
    this.center = center || [size.w / 2, size.h / 2];
    this.update();
  }

  update() {
    this.f = norm(sub(this.target, this.position));        // forward
    this.r = norm(cross(this.up, this.f));                  // right on screen
    this.u = cross(this.f, this.r);                          // up on screen (toward -y)
    this.focal = (this.h / 2) / Math.tan((this.fov * Math.PI) / 360);
    return this;
  }

  project(p) {
    const d = sub(p, this.position);
    const z = dot(d, this.f);
    const scale = this.focal / Math.max(z, 1e-6);
    return { x: this.center[0] + dot(d, this.r) * scale, y: this.center[1] - dot(d, this.u) * scale, depth: z, scale, visible: z > this.near };
  }
}

const fogOf = (fog, depth) => (fog ? 1 - smoothstep(fog[0], fog[1], depth) : 1);

// one line through 3-D points; split where it goes behind the camera
export function stroke3(g, target, cam, points, { width = 0.02, alpha = 1, fog = null, ...opts } = {}) {
  const W = typeof width === 'function' ? width : () => width;
  const A = typeof alpha === 'function' ? alpha : () => alpha;
  let run = [];
  const flush = () => {
    if (run.length > 1) {
      const pts = run.map((q) => [q.x, q.y]);
      const ws = run.map((q) => W(q.i) * q.scale), as = run.map((q) => A(q.i) * fogOf(fog, q.depth));
      g.stroke(target, pts, { ...opts, width: (i) => ws[i], alpha: (i) => as[i] });
    }
    run = [];
  };
  points.forEach((p, i) => {
    const q = cam.project(p);
    if (q.visible) run.push({ ...q, i }); else flush();
  });
  flush();
}

// several lines, far to near (by mean depth), so nearer lines cover farther ones
export function strokes3(g, target, cam, list) {
  const keyed = list.map((s) => {
    let d = 0;
    for (const p of s.points) d += cam.project(p).depth;
    return { s, d: d / Math.max(s.points.length, 1) };
  });
  keyed.sort((a, b) => b.d - a.d);
  for (const { s } of keyed) stroke3(g, target, cam, s.points, s);
}

// discs at 3-D points, far to near
export function points3(g, target, cam, list, { fog = null, blend = 'over' } = {}) {
  const out = [];
  for (const d of list) {
    const q = cam.project(d.p);
    if (!q.visible) continue;
    out.push({ ...d, x: q.x, y: q.y, r: (d.r ?? 0.02) * q.scale, alpha: (d.alpha ?? 1) * fogOf(fog, q.depth), depth: q.depth });
  }
  out.sort((a, b) => b.depth - a.depth);
  g.points(target, out, { blend });
}
