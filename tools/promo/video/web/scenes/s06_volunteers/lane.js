// Lines 1 and 2: the sung line as the Sing view's lane shows it (tools/karaoke.js drawLane), large, in ink on
// paper, and each note's bar becoming a ribbon in the shape its nine numbers describe, the numbers set against
// the part of the shape each one makes.
import { clamp, smoothstep, mix } from '../../core/math.js';
import { cents, decibels, written, figure, FIELDS } from './gesture.js';

// the lane's frame (design units)
export const LANE = { x0: 150, x1: 1770, lo: 54.5, hi: 69.5, bottom: 690, semitone: 26, bar: 22 };
// for the eye: cents (scoop, bend, fall, vibrato, tune) drawn 4 times their size; dB (level, swell) twice
export const CENTS_EYE = 4;
export const DB_EYE = 2;
const DEGREE = { 1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11 };

export const laneY = (p) => LANE.bottom - (p - LANE.lo) * LANE.semitone;

// one page per lane line: its notes (sung and written) and the time-to-x of the page
export function page(ctx, line, rows, phrases) {
  const tl = ctx.timeline, beat = tl.beatLength, eighth = beat / 2;
  const sung = ctx.score.range('voice', line.t0, line.t1 + 1e-3);
  const pid = sung[0].phrase, tune = phrases[pid].notes;
  const gRows = rows.filter((r) => r.phrase === pid);
  // the phrase's first bar line: where its note 0 (at 0) was written, from the sung pickup undone
  const est = written(sung[1], beat).t;
  const barline = tl.nearestBar(est - tune[1].at * eighth);
  const notes = sung.map((n, i) => {
    const w = { t: barline + tune[i].at * eighth, d: tune[i].units * eighth };
    const row = gRows.find((r) => r.note === i);
    const g = Object.fromEntries(FIELDS.map((f, j) => [f, row.g[j]]));
    return { n, w, g, row, i, degree: tune[i].degree };
  });
  const t0 = Math.min(notes[0].w.t, notes[0].n.t), t1 = Math.max(...notes.map((m) => Math.max(m.w.t + m.w.d, m.n.t + m.n.d)));
  const X = (s) => LANE.x0 + (s - t0) / (t1 - t0) * (LANE.x1 - LANE.x0);
  return { line, pid, notes, t0, t1, X };
}

// the bar of one note: [x, yCentre, thickness] at `count` places from its start to its end, shaped by k of its gesture
export function barShape(m, X, k, count = 72) {
  const { n, w, g } = m;
  const out = [];
  for (let j = 0; j <= count; j++) {
    const f = j / count;
    const uw = w.t + w.d * f, us = n.t + n.d * f;
    const xs = mix(X(uw), X(us), k);
    const c = cents(g, n.t, n.d, us) * CENTS_EYE / 100;
    const y = laneY(n.p + c * k);
    const th = LANE.bar * 10 ** (k * DB_EYE * decibels(g, f) / 20);
    out.push([xs, y, th]);
  }
  return out;
}

// a bar as woodcut: vertical hairlines every `pitch` units between its edges, and the two edges
export function drawBar(ctx, target, shape, { color, alpha = 1, pitch = 3, hatch = 1.5, edge = 1.3, fill = 1, white }) {
  const g = ctx.g;
  if (alpha <= 0) return;
  const x0 = shape[0][0], x1 = shape[shape.length - 1][0];
  if (fill > 0) {
    const rects = [];
    let j = 0;
    for (let x = Math.ceil(x0 / pitch) * pitch; x <= x1; x += pitch) {
      while (j < shape.length - 2 && shape[j + 1][0] < x) j++;
      const a = shape[j], b = shape[j + 1] || a, f = b[0] > a[0] ? (x - a[0]) / (b[0] - a[0]) : 0;
      const y = mix(a[1], b[1], f), th = mix(a[2], b[2], f);
      rects.push({ x, y: y - th / 2, w: hatch, h: th, color, alpha: alpha * fill });
    }
    g.rects(target, rects, { snap: true, texture: white });
  }
  const top = shape.map(([x, y, th]) => [x, y - th / 2]), bot = shape.map(([x, y, th]) => [x, y + th / 2]);
  g.stroke(target, [...top, ...bot.reverse()], { width: edge, color, alpha, closed: true });
}

// the nine numbers of a note with their units, each where its part of the shape is:
// at the start the scoop, early and level; in the middle the bend, vibrato and swell; at the end the fall, tune and hold
const signed = (v) => (v > 0 ? '+' : '') + figure(v);
const TEXT = {
  early: (v) => `early ${signed(v)} beat`, hold: (v) => `hold ${figure(v)}`, level: (v) => `level ${signed(v)} dB`,
  swell: (v) => `swell ${signed(v)} dB`, scoop: (v) => `scoop ${signed(v)}¢`, bend: (v) => `bend ${signed(v)}¢`,
  fall: (v) => `fall ${signed(v)}¢`, vibrato: (v) => (v < 0 ? 'vibrato −' : `vibrato ${figure(v)}¢`),
  tune: (v) => `tune ${signed(v)}¢`,
};
const SHORT = { scoop: (v) => `${signed(v)}¢`, fall: (v) => `${signed(v)}¢`, vibrato: (v) => (v > 0 ? `~${figure(v)}¢` : '') };
const GRID = [['scoop', 'bend', 'fall'], ['early', 'vibrato', 'tune'], ['level', 'swell', 'hold']];

// full: 0..1 the note's whole annotation (while it is sung); rest: what stays (scoop, vibrato, fall, values only)
export function annotate(ctx, target, m, shape, { color, full, rest, size = 22, avoid = [] }) {
  const ty = ctx.type;
  const xs0 = shape[0][0], xs1 = shape[shape.length - 1][0], xm = (xs0 + xs1) / 2;
  const top = Math.min(...shape.map(([, y, th]) => y - th / 2));
  if (full > 0) {
    // set in the band over the lane, the start's numbers over its start, the end's over its end, a hairline down to the shape
    const cx = [Math.min(xs0, xm - 215), xm, Math.max(xs1, xm + 215)].map((x) => clamp(x, 130, 1790));
    const band = 300;
    GRID.forEach((row, r) => row.forEach((f, c) => {
      const s = ty.text(TEXT[f](m.g[f]), { role: 'numeral', size });
      const a = full * clamp(full * 3 - (r * 3 + c) * 0.12);
      if (a > 0) ty.draw(target, s, cx[c], band - r * (size + 7), { color, alpha: a, align: 'center' });
    }));
    if (top - 14 > band + 8) ctx.g.stroke(target, [[xm, band + 8], [xm, top - 8]], { width: 0.8, color, alpha: full * 0.6 });
  }
  if (rest > 0) {
    const keep = [['scoop', xs0, 'left'], ['vibrato', xm, 'center'], ['fall', xs1, 'right']];
    for (const [f, x, align] of keep) {
      const str = SHORT[f](m.g[f]);
      if (!str || (f !== 'vibrato' && m.g[f] === 0) || (f === 'vibrato' && xs1 - xs0 < 150)) continue;
      const sp = ty.text(str, { role: 'numeral', size: size - 3 });
      const left = align === 'left' ? x : align === 'right' ? x - sp.width : x - sp.width / 2, y = top - 12;
      // never over a syllable
      if (avoid.some((b) => left < b.x1 + 4 && left + sp.width > b.x0 - 4 && y > b.y0 - 2 && y - sp.ascent < b.y1 + 2)) continue;
      ty.draw(target, sp, x, y, { color, alpha: rest, align });
      avoid.push({ x0: left, x1: left + sp.width, y0: y - sp.ascent, y1: y + sp.descent });
    }
  }
}

export function degreePitch(degree, tonic) {
  const d = degree.replace(/[,']/g, '');
  const oct = (degree.match(/'/g) || []).length - (degree.match(/,/g) || []).length;
  return tonic + DEGREE[d] + 12 * oct;
}
