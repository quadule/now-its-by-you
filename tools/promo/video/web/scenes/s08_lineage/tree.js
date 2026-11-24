// The lineage: what happens next to the file. Every hand-over makes a child one generation on, with its parent's
// id in its ancestry (songbird/pack.py lineage()). The root is this file, its id, generation, parent and ancestry
// as its manifest holds them (packet.json); a child's id does not exist until it is sung, so it is a rule of dots.
//
// The tree is grown by the song's second bridge line: each syllable the lead sings hands the coal on (a child of the
// version it is on); each choir note sung with it makes a sibling the coal does not follow; each harp, drum, bass and
// fiddle note makes a copy of a version chosen by a seeded hash. A branch leaves its parent along the parent's own
// way, turned by the note that made it: the lead's step in pitch bends the newest branch, a choir note's interval
// from the lead sets its sibling's angle, an instrument's pitch its copy's; a longer note makes a longer branch.
// Laid out once, from the root at the lower left, and stretched to fill the frame clear of the lyric and the lower
// right (its whole as the wide view sees it; a view o.view = {O, Z} draws it at Z about O).
import { Segs } from './lines.js';
import { clamp, smoothstep, mix, ease } from '../../core/math.js';

export const DOTS = '·'.repeat(12);
const ROOT = [140, 770], BOX = [140, 150, 1560, 800], GROW = 0.42;
const DEG = Math.PI / 180;
let T = null;

export function tree(ctx) {
  const tl = ctx.timeline;
  if (T && T.tl === tl) return T;
  const line = tl.lineOf('bridge', 1);
  const heard = (part) => ctx.score.range(part, line.t0 - 0.05, line.t1).filter((n) => n.a > 0);
  const nodes = [{ i: 0, parent: -1, gen: 0, t: -Infinity, trunk: true, kids: [], x: 0, y: 0, dir: -26 * DEG, p: null }];
  const events = [
    ...heard('voice').map((n) => ({ t: n.t, kind: 'lead', p: n.p, d: n.d })),
    ...['choir1', 'choir2', 'choir3'].flatMap((p) => heard(p).map((n) => ({ t: n.t, kind: 'choir', p: n.p, d: n.d, part: p }))),
    ...['harp', 'drum', 'bass', 'fiddle'].flatMap((p) => heard(p).map((n) => ({ t: n.t, kind: 'copy', p: n.p, d: n.d, v: n.v, part: p }))),
  ].sort((a, b) => a.t - b.t || (a.kind === 'lead' ? -1 : b.kind === 'lead' ? 1 : 0));
  let coal = 0;
  for (const e of events) {
    let parent, dir, len;
    if (e.kind === 'lead') {
      parent = coal;
      const P = nodes[parent], step = P.p === null ? 0 : e.p - P.p;
      dir = clamp(P.dir - step * 2.6 * DEG, -48 * DEG, 6 * DEG);
      len = 92 + 70 * clamp(e.d / 0.6);
    } else if (e.kind === 'choir') {
      const lead = nodes[coal];
      parent = lead.parent >= 0 && Math.abs(lead.t - e.t) < 0.08 ? lead.parent : coal;
      const ref = Math.abs(lead.t - e.t) < 0.08 ? lead : nodes[parent];
      dir = nodes[parent].dir + clamp(-(e.p - (ref.p ?? e.p)) * 3.4, -72, 72) * DEG + (e.part === 'choir3' ? 9 : 0) * DEG;
      len = 58 + 46 * clamp(e.d / 0.6);
    } else {
      // a copy from a version that exists, the newer ones most often
      const pool = nodes.filter((n) => n.t < e.t - 0.08);
      const h = ctx.rand('lineage', e.part, e.t, e.p);
      parent = pool[Math.min(Math.floor((1 - h * h * h) * pool.length), pool.length - 1)].i;
      dir = nodes[parent].dir + clamp((60 - e.p) * 1.7 + (ctx.rand('turn', e.t, e.p) - 0.5) * 50, -80, 80) * DEG;
      len = 46 + 52 * clamp((e.v ?? 0.7) * (0.4 + e.d));
    }
    const P = nodes[parent];
    const n = { i: nodes.length, parent, gen: P.gen + 1, t: e.t, trunk: e.kind === 'lead', kids: [], dir, p: e.p,
      x: P.x + Math.cos(dir) * len, y: P.y + Math.sin(dir) * len, len };
    P.kids.push(n.i);
    nodes.push(n);
    if (n.trunk) coal = n.i;
  }
  // fitted: the root at the lower left, the whole within the box
  let x1 = 0, y0 = 0, y1 = 0;
  for (const n of nodes) { x1 = Math.max(x1, n.x); y0 = Math.min(y0, n.y); y1 = Math.max(y1, n.y); }
  // across the width, and up as far as the frame goes (the up scale held within 0.7 to 4 of the across)
  const sc = (BOX[2] - ROOT[0]) / x1;
  // (what hangs below the root pressed into the room there)
  const up = clamp((ROOT[1] - BOX[1]) / -y0, sc * 0.7, sc * 4), down = y1 > 0 ? Math.min(up, (BOX[3] - ROOT[1]) / y1) : up;
  for (const n of nodes) { n.x = ROOT[0] + n.x * sc; n.y = ROOT[1] + n.y * (n.y > 0 ? down : up); }
  // the record each holds
  const man = ctx.data.get('packet.json').manifest, short = (id) => id.slice(0, 12);
  const ids = (n) => (n.i === 0 ? short(man.id) : DOTS);
  for (const n of nodes) {
    const anc = [];
    for (let p = n.parent; p >= 0; p = nodes[p].parent) anc.unshift(ids(nodes[p]));
    n.record = { id: ids(n), generation: man.generation + n.gen,
      parent: n.parent < 0 ? (man.parent_id ? short(man.parent_id) : null) : ids(nodes[n.parent]),
      ancestry: [...man.ancestry.map(short), ...anc] };
  }
  // how much grows from each version (its descendants), for the branch's weight
  const size = (n) => (n.size = 1 + n.kids.reduce((s, k) => s + size(nodes[k]), 0));
  size(nodes[0]);
  T = { tl, nodes, line, sc, trunk: nodes.filter((n) => n.trunk), segs: new Segs() };
  return T;
}

// a branch from parent p to child c, leaving along the parent's way, drawn to u (0..1)
export function branch(p, c, u, steps = 24) {
  const pts = [], L = Math.hypot(c.x - p.x, c.y - p.y);
  const cx = p.x + Math.cos(p.dir) * L * 0.45, cy = p.y + Math.sin(p.dir) * L * 0.45;
  for (let i = 0; i <= steps; i++) {
    const s = (i / steps) * u, a = 1 - s;
    pts.push([a * a * p.x + 2 * a * s * cx + s * s * c.x, a * a * p.y + 2 * a * s * cy + s * s * c.y]);
  }
  return pts;
}

// how far a node's branch has grown at t (0 before its hand-over)
export const grown = (n, t) => (n.i === 0 ? 1 : ease.outCubic(clamp((t - n.t) / GROW)));
const weight = (n) => 0.8 + 3.2 * Math.sqrt(n.size / 60);

// the node the coal is on at t, and the coal's place in the tree's own (wide view) frame
export function coalAt(T, t) {
  let at = T.nodes[0];
  for (const n of T.trunk) if (n.t <= t) at = n;
  const p = at.i === 0 ? at : T.nodes[at.parent], u = grown(at, t);
  const pts = branch(p, at, u, 20);
  const [x, y] = pts[pts.length - 1];
  return { node: at, x, y, moving: u < 1, u };
}

// The tree at t. o.alpha its whole weight; o.out(n) 0..1 how far node n has gone out (the dark); o.glow 0..1 light
export function drawTree(ctx, t, target, ink, { alpha = 1, out = () => 0, glow = 0, coal = 1, view = { O: [0, 0], Z: 1 } } = {}) {
  const T = tree(ctx), { segs } = T, { O, Z } = view, lw = Math.sqrt(Z);
  const V = (p) => [O[0] + p[0] * Z, O[1] + p[1] * Z];
  segs.clear();
  const dots = [];
  for (const n of T.nodes) {
    const g = grown(n, t);
    if (g <= 0) continue;
    const a = alpha * (1 - out(n));
    if (n.i > 0) {
      const p = T.nodes[n.parent], pts = branch(p, n, g).map(V), m = pts.length - 1;
      // a hairline thinning toward the tips: from the parent's weight to the child's
      const w0 = weight(n) * 1.15 * lw, w1 = weight(n) * lw;
      for (let i = 0; i < m; i++) {
        const wa = mix(w0, w1, i / m), wb = mix(w0, w1, (i + 1) / m);
        segs.add(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], wa, wb, a, a);
      }
    }
    if (g >= 1 || n.i === 0) dots.push({ n, a: a * smoothstep(0.85, 1, g) });
  }
  segs.draw(ctx, target, { color: ink.ink });
  ctx.g.points(target, dots.filter((d) => d.a > 0).map(({ n, a }) => ({
    x: O[0] + n.x * Z, y: O[1] + n.y * Z, r: (n.i === 0 ? 5.5 : clamp(1.4 + weight(n) * 0.8, 1.8, 4)) * lw, color: glow > 0 ? ink.sung : ink.ink, alpha: a,
    intensity: mix(1, 1.8, glow), soft: glow * 0.9,
  })));
  // the coal: a red point on the newest branch
  const c = coalAt(T, t);
  [c.x, c.y] = V([c.x, c.y]);
  if (coal > 0) ctx.g.points(target, [{ x: c.x, y: c.y, r: 6.5 * lw, color: ink.red, alpha: coal * alpha, intensity: mix(1, 2.4, glow), soft: glow }]);
  return c;
}
