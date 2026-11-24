// Line 1: the phones the throat is told. The strand is the human-0 take's pitch line (its log f0, every note a level
// step), drawn over the line's own seconds; each phone is a bead on it at its middle, and under the line a column
// per phone holds its symbol and the numbers it was given: position through the phone, log duration, stress,
// level, log f0. The sung phone's bead is lit and its position counts through it.
import { clamp, smoothstep, mix } from '../../core/math.js';

export const SEMI = 9;                       // design units a semitone, as the core's strand
const COL_TOP = 628, ROW0 = 654, ROW = 19;   // the columns: hairlines end at COL_TOP; symbol, then five rows
const FMT = (v, d = 2) => (v < 0 ? '−' : '') + Math.abs(v).toFixed(d);

export function setupLine1(ctx, S) {
  const tl = ctx.timeline, line = tl.lineOf('verse1', 0);
  const all = ctx.data.get('s02/phones-line1.json').phones;
  // the phones sung on this line (not its silences, not the next line's first)
  S.phones = all.filter((p) => p.note >= 0 && p.t0 < line.t1);
  const B = tl.beatLength;
  S.B = B;
  S.l1 = { t0: S.phones[0].t0 - B / 2, t1: S.phones[S.phones.length - 1].t1 + B / 2 };
  const n = S.phones.length, x0 = 150, x1 = ctx.size.w - 150;
  S.phones.forEach((p, i) => { p.col = x0 + ((x1 - x0) * i) / (n - 1); p.mid = (p.t0 + p.t1) / 2; });
  // the syllables of "sent it by wire": a pulse runs out along the wire from each
  const words = line.words;
  S.pulses = words.slice(words.length - 4).flatMap((w) => w.syllables.map((s) => s.t0));
}

// the human-0 take's pitch (MIDI) at song time s: log f0 at 200 frames a second, held across gaps
export function pitch0(S, s) {
  const lf = S.lf0whole, f = clamp(s * 200, 0, lf.length - 2), i = Math.floor(f), k = f - i;
  let a = lf[i], b = lf[i + 1];
  if (!Number.isFinite(a)) a = b;
  if (!Number.isFinite(b)) b = a;
  const v = Number.isFinite(a) ? a + (b - a) * k : Math.log(440 * 2 ** ((59 - 69) / 12));
  return 69 + (12 * Math.log2(Math.exp(v) / 440));
}

// x of song time s on line 1's strand, which spans the frame over the line's seconds
export const xOf = (ctx, S, s) => (ctx.size.w * (s - S.l1.t0)) / (S.l1.t1 - S.l1.t0);
export const yOf = (ctx, S, s) => 540 - (pitch0(S, s) - ctx.timeline.tonic) * SEMI;

// the strand of line 1 as points across the frame
export function line1Points(ctx, S, step = 1 / 400) {
  const pts = [];
  for (let s = S.l1.t0; s <= S.l1.t1 + 1e-9; s += step) pts.push([xOf(ctx, S, s), yOf(ctx, S, s)]);
  return pts;
}

// beads, the columns of numbers and their hairlines, and the pulses on the wire. `show` 0..1 brings the picture in
// (left to right) and `fade` takes it away.
export function drawLine1(ctx, t, target, S, { show, fade, ink, light = 1 }) {
  const g = ctx.g, type = ctx.type;
  if (fade <= 0 || show <= 0) return;
  const beads = [], halo = [];
  S.phones.forEach((p, i) => {
    const arrive = clamp(show * 1.6 - (i / S.phones.length) * 0.6);
    if (arrive <= 0) return;
    const bx = xOf(ctx, S, p.mid), by = yOf(ctx, S, p.mid);
    const sung = t >= p.t0, now = t >= p.t0 && t < p.t1;
    const lit = now ? 1 : sung ? Math.exp(-(t - p.t1) / S.B) : 0;
    const a = arrive * fade;
    // the hairline from the bead down to its column
    const hx = [[bx, by + 6], [mix(bx, p.col, 0.5), mix(by, COL_TOP, 0.62)], [p.col, COL_TOP]];
    g.stroke(target, hx, { width: 0.7, color: sung ? ink.ink2 : ink.rule, alpha: a * (sung ? 0.55 : 0.9) });
    // the bead: a ring, filled once sung
    const r = 3.4 + 2.2 * lit;
    beads.push({ x: bx, y: by, r, color: sung ? ink.sung : ink.cold, alpha: a * (sung ? 1 : 0.55),
      intensity: 1 + 1.6 * lit * light, soft: 0.6 * lit });
    if (!sung) beads.push({ x: bx, y: by, r: r - 1.3, color: ink.ground, alpha: a });
    if (lit > 0.02) halo.push({ x: bx, y: by, r: 9 + 8 * lit, color: ink.sung, alpha: 0.18 * lit * a, intensity: 1.5, soft: 1 });
    // the column: the phone, then its numbers
    const colInk = now ? ink.ink : sung ? ink.ink2 : ink.ruleStrong;
    const ca = a * (now ? 1 : sung ? 0.85 : 0.7);
    const sym = type.text(p.phone, { role: 'label', size: 15 });
    type.draw(target, sym, p.col, ROW0, { color: now ? ink.sung : colInk, alpha: ca, align: 'center' });
    const pos = now ? mix(p.pos0, p.pos1, (t - p.t0) / (p.t1 - p.t0)) : sung ? p.pos1 : p.pos0;
    const vals = [FMT(pos), FMT(p.dur), FMT(p.stress, 0), FMT(p.level), FMT(p.lf0)];
    vals.forEach((v, k) => {
      const s = type.text(v, { role: 'numeral', size: 13 });
      type.draw(target, s, p.col, ROW0 + ROW * (k + 1) + 4, { color: colInk, alpha: ca, align: 'center' });
    });
  });
  g.points(target, halo, { blend: 'add' });
  g.points(target, beads);
  // pulses: from each syllable of "sent it by wire", light runs out along the wire to the frame's edge
  const pts = [];
  for (const t0 of S.pulses) {
    const age = t - t0;
    const life = 2 * S.B;
    if (age < 0 || age > life) continue;
    // the pulse travels the wire at 2.2 of the line's seconds a second, a fifth of a beat long
    const s0 = t0 + age * 2.2, len = S.B / 5;
    const trail = [];
    for (let k = 0; k <= 24; k++) {
      const s = s0 - len * (k / 24);
      if (s < t0) break;
      trail.push([xOf(ctx, S, s), yOf(ctx, S, s)]);
    }
    if (trail.length > 1) {
      const n = trail.length;
      g.stroke(target, trail, { width: (i) => 3.2 * (1 - i / n) + 0.6, color: ink.cold, intensity: 2.4 * light,
        alpha: (i) => fade * (1 - i / n) * (1 - smoothstep(0.65 * life, life, age)), blend: 'add' });
      pts.push({ x: trail[0][0], y: trail[0][1], r: 3.5, color: ink.cold, intensity: 3 * light, alpha: fade * (1 - smoothstep(0.65 * life, life, age)), soft: 1 });
    }
  }
  g.points(target, pts, { blend: 'add' });
}

// a faint oscilloscope trace of a stem's real samples: `span` seconds across the frame, held still on a rising zero
// crossing near t, centred at y with `amp` design units for full scale
export function scope(ctx, t, target, wave, { y, amp, span = 0.025, color, alpha, width = 1 }) {
  const sr = wave.rate, v = wave.values, i0 = Math.round((t - wave.t0) * sr);
  if (i0 < 1 || i0 >= v.length - sr * 0.08) return;
  let at = i0;
  for (let i = i0; i < i0 + sr * 0.02; i++) if (v[i - 1] < 0 && v[i] >= 0) { at = i; break; }
  const n = Math.round(span * sr), w = ctx.size.w, pts = [];
  for (let k = 0; k <= n; k++) {
    const j = at - (n >> 1) + k;
    pts.push([(w * k) / n, y - v[j] * amp]);
  }
  ctx.g.stroke(target, pts, { width, color, alpha, blend: 'add' });
}
