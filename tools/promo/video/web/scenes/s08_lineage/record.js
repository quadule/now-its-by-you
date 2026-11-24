// The record of the version the coal is on, as its manifest.json holds it: id, generation, parent_id, ancestry.
// Set beside the coal and moving with it, at the corner no branch enters; on each hand-over the new version's fields arrive one after another, the
// ancestry lengthening by its parent's id. The one id that exists is eb8fb05eb2bb; the rest are rules of dots.
import { clamp, smoothstep, mix } from '../../core/math.js';

import { branch, grown } from './tree.js';

const SIZE = 30, LEAD = 42, PER_ROW = 4, PAD = 26;

// the card's rows for node n: [[sprite, field], ...] per row, field the arrival order (-1 there throughout)
function layout(ctx, n) {
  const r = n.record, q = (s) => (s === null ? 'null' : `"${s}"`);
  const T = (s) => ctx.type.text(s, { role: 'numeral', size: SIZE });
  const rows = [[[T(`"id": ${q(r.id)},`), 0]], [[T(`"generation": ${r.generation},`), 1]], [[T(`"parent_id": ${q(r.parent)},`), 2]]];
  const head = T('"ancestry": [');
  const anc = r.ancestry.map((id, i) => [T(`${q(id)}${i < r.ancestry.length - 1 ? ',' : ']'}`), i === r.ancestry.length - 1 ? 3 : -1]);
  if (!anc.length) rows.push([[T('"ancestry": []'), -1]]);
  else for (let i = 0; i < anc.length; i += PER_ROW) rows.push([...(i === 0 ? [[head, -1]] : []), ...anc.slice(i, i + PER_ROW)]);
  const gap = SIZE * 0.32, indent = head.width + gap;
  const w = Math.max(...rows.map((row, ri) => row.reduce((w, [s]) => w + s.width + gap, ri > 3 ? indent : 0)));
  return { rows, gap, indent, w, h: LEAD * rows.length };
}

// where the card sits beside the coal at (cx, cy): one of four corners, kept in the frame
function corner(ctx, k, cx, cy, w, h) {
  const dx = k % 2 === 0 ? 56 : -56 - w, dy = k < 2 ? -h - 44 : 50;
  return [clamp(cx + dx, 96, ctx.size.w - 80 - w), clamp(cy + dy, 150, 830 - h)];
}

// For each version the coal rests on, the corner whose card no branch enters while the coal is there: scored over the
// tree as it stands when the coal moves on (or line 2 ends), seen as the view sees it then.
const CORNER = new Map();
export function cornerFor(ctx, T, node, leave, viewAt) {
  if (CORNER.get(T)?.has(node.i)) return CORNER.get(T).get(node.i);
  if (!CORNER.has(T)) CORNER.set(T, new Map());
  const { w, h } = layout(ctx, node), v = viewAt(leave), S = (p) => [v.O[0] + p[0] * v.Z, v.O[1] + p[1] * v.Z];
  const pts = [];
  for (const n of T.nodes) {
    if (n.i === 0 || !(n.t <= leave)) continue;
    for (const p of branch(T.nodes[n.parent], n, grown(n, leave), 12)) pts.push(S(p));
  }
  const [cx, cy] = S([node.x, node.y]);
  let best = 0, score = Infinity;
  for (let k = 0; k < 4; k++) {
    const [x, y] = corner(ctx, k, cx, cy, w, h);
    const c = pts.filter(([px, py]) => px > x - PAD && px < x + w + PAD && py > y - PAD && py < y + h + PAD).length;
    if (c < score) { score = c; best = k; }
  }
  CORNER.get(T).set(node.i, best);
  return best;
}

// The card for the coal (screen place c, its node c.node) at alpha; k, k0: this version's corner and the last one's,
// eased between over the hand-over. A field the hand-over changes passes from the last version's value to the new.
export function drawRecord(ctx, t, target, ink, c, alpha, k, k0, last) {
  const n = c.node, born = Number.isFinite(n.t) ? n.t : -Infinity;
  const arrive = (i) => (i < 0 || !Number.isFinite(born) ? 1 : smoothstep(born + 0.06 * i, born + 0.06 * i + 0.16, t));
  const L = layout(ctx, n), P = last ? layout(ctx, last) : null;
  const a = corner(ctx, k, c.x, c.y, L.w, L.h), b = corner(ctx, k0, c.x, c.y, L.w, L.h);
  const u = Number.isFinite(born) ? smoothstep(born, born + 0.3, t) : 1;
  const x0 = mix(b[0], a[0], u), y0 = mix(b[1], a[1], u);
  const put = (rows, ri, alphaOf) => {
    let x = x0 + (ri > 3 ? L.indent : 0);
    for (const [s, f] of rows[ri] || []) {
      const fa = alphaOf(s, f);
      if (fa > 0) ctx.type.draw(target, s, x, y0 + ri * LEAD + SIZE, { color: ink.ink, alpha: alpha * fa });
      x += s.width + L.gap;
    }
  };
  const field = (r, ri) => [r.id, r.generation, r.parent][ri];
  const same = (ri) => last && field(last.record, ri) === field(n.record, ri);
  L.rows.forEach((row, ri) => {
    const keep = same(ri) && ri < 3;
    put(L.rows, ri, (s, f) => (keep ? 1 : arrive(f)));
    if (P && !keep && ri < 3) put(P.rows, ri, (s, f) => 1 - arrive(f));
  });
}
