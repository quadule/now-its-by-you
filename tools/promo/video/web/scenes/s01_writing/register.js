// The drum machine's triggers on the strand (physics/drummachine.json, the drummachine# twin's TR808): a step
// grid of the bar now playing, sixteen sixteenths across, one row per circuit voice. A trigger fills its cell
// at its own time, by its height (size), and its light decays over the voice's own length (len_s, or cut_s
// where a later trigger chokes it). The column under the bar's playhead is drawn brighter. Cells are heard only
// where the stage has the twin up.
import { clamp, smoothstep } from '../../core/math.js';
import { below } from '../../core/timeline.js';

export const STEM = 'drummachine#';
const ROWS = ['crash', 'hat-open', 'hat', 'snare', 'tom', 'kick'];
const STEPS = 16, CELL = 22, PITCH = 28;

const row = (piece) => (piece.startsWith('tom') ? 'tom' : piece);

export function buildRegister(ctx) {
  const dm = ctx.data.get('physics/drummachine.json');
  const hits = dm.hits.filter((h) => h.stem === STEM && ROWS.includes(row(h.piece))).sort((a, b) => a.t - b.t);
  return { hits, bars: ctx.timeline.bars, bar: ctx.timeline.barLength };
}

// the stage's linear gain for a part at t, as the engine fades it: linear in amplitude between points, null
// silent, the first and last points held; a part with no curve at 1
function stageGain(ctx, part, t) {
  const pts = ctx.timeline.levels[part];
  if (!pts || !pts.length) return 1;
  const g = (db) => (db === null ? 0 : 10 ** (db / 20));
  const i = below(pts, t, (p) => p[0]);
  if (i < 0) return g(pts[0][1]);
  if (i >= pts.length - 1) return g(pts[pts.length - 1][1]);
  const [t0, a] = pts[i], [t1, b] = pts[i + 1];
  return t1 > t0 ? g(a) + (g(b) - g(a)) * (t - t0) / (t1 - t0) : g(b);
}

export function drawRegister(ctx, t, target, ink, R, { x0 = 96, y = 540, alpha = 1 } = {}) {
  if (alpha <= 0) return;
  const bi = below(R.bars, t);
  if (bi < 0) return;
  const b0 = R.bars[bi], b1 = R.bars[bi + 1] ?? b0 + R.bar;
  const step = (b1 - b0) / STEPS;
  const head = Math.floor((t - b0) / step);
  const heardNow = stageGain(ctx, STEM, t);
  const fill = [], edges = [];
  // the bar's triggers so far, each lit by its height, its light decaying over its voice's length
  const lit = new Map();
  let j = below(R.hits, t, (h) => h.t);
  for (; j >= 0 && R.hits[j].t >= b0 - step / 2; j--) {
    const h = R.hits[j];
    const s = clamp(Math.round((h.t - b0) / step), 0, STEPS - 1), r = ROWS.indexOf(row(h.piece));
    const key = r * STEPS + s;
    if (lit.has(key)) continue;
    const heard = stageGain(ctx, STEM, h.t + 0.02);
    if (heard <= 0) continue;
    const len = h.cut_s ?? h.len_s;
    const ring = Math.exp(-Math.max(0, t - h.t) / Math.max(0.03, len / 3));
    lit.set(key, { r, s, size: clamp(0.35 + h.size * 1.3), ring, heard });
  }
  const fade = alpha * Math.min(1, heardNow * 4 + (lit.size ? 0.5 : 0));
  if (fade <= 0) return;
  const c = CELL / 2, w = 1;
  for (let r = 0; r < ROWS.length; r++) {
    for (let s = 0; s < STEPS; s++) {
      const x = x0 + s * PITCH, yy = y + r * PITCH;
      const on = lit.get(r * STEPS + s);
      const isHead = s === head;
      if (on) {
        const k = on.ring;
        fill.push({ x: x - c, y: yy - c, w: CELL, h: CELL, color: k > 0.3 ? ink.sung : ink.cold,
          alpha: fade * Math.min(1, on.heard * 4) * (0.35 + 0.65 * Math.max(k, 0.25) * on.size), intensity: 1 + 1.8 * k });
      } else {
        const a = fade * (isHead ? 0.9 : 0.45) * (s % 4 === 0 ? 1 : 0.75);
        const color = ink.cold;
        edges.push({ x: x - c, y: yy - c, w: CELL, h: w, color, alpha: a, intensity: 1 },
          { x: x - c, y: yy + c - w, w: CELL, h: w, color, alpha: a, intensity: 1 },
          { x: x - c, y: yy - c + w, w, h: CELL - 2 * w, color, alpha: a, intensity: 1 },
          { x: x + c - w, y: yy - c + w, w, h: CELL - 2 * w, color, alpha: a, intensity: 1 });
      }
    }
  }
  ctx.g.rects(target, fill.concat(edges));
}
export { smoothstep, clamp };
