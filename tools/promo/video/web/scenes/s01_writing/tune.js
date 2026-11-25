// The tune as written: the intro's phrase in scale degrees on its eighth-note grid (text.json phrases),
// each digit matched to the lead's note that plays it (score.json whistle~), and the strand over the grid.
// The strand is a function of song time s: in the rest pose s maps to x as the core's strand maps it; on the
// grid s maps to its eighth-note cell, so a morph between them slides each note into its cell.
import { clamp, smoothstep, ease } from '../../core/math.js';

// semitones above the tonic for each scale degree of the major scale
const DEGREE = { 1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11 };
export const PART = 'whistle~';

// the grid: 17 cells (the pickup and two bars of eighths), the strand's line on it, digits set under the line
export const GRID = { x0: 110, cell: 100, y: 570, digitBase: 712, digitSize: 92, lift: 27, floor: 67 };

// semitones of a written degree ("5", "6,", "1'") above the tonic
function semis(deg) {
  const n = DEGREE[deg[0]];
  const oct = (deg.match(/'/g) || []).length - (deg.match(/,/g) || []).length;
  return n + 12 * oct;
}

// the phrase played from bar line t0: each written note with the score note that sounds it (null: not played)
export function setPhrase(ctx, phrase, t0) {
  const eighth = ctx.timeline.barLength / 8, tonic = ctx.timeline.tonic;
  const all = ctx.score.notes(PART);
  const notes = all.filter((n) => n.art !== 'cut');
  const cuts = all.filter((n) => n.art === 'cut');
  return phrase.notes.map((w) => {
    const at = t0 + w.at * eighth;
    const n = notes.find((m) => Math.abs(m.t - at) < eighth * 0.4);
    // a digit is set only where the note played is the written degree (in any octave)
    const ok = !!n && (((n.p - tonic - semis(w.degree)) % 12) + 12) % 12 === 0;
    const cut = ok ? cuts.find((c) => c.t < n.t && n.t - c.t < 0.06) || null : null;
    return { ...w, t0: at, t1: at + w.units * eighth, note: ok ? n : null, cut };
  });
}

export const cellX = (at) => GRID.x0 + (at + 1) * GRID.cell;
export const liftY = (p) => GRID.y - (p - GRID.floor) * GRID.lift;

// how far a note has lifted at t: it rises over the first part of its sounding
export const lifted = (n, t) => (n ? ease.outCubic(clamp((t - n.t) / 0.16)) : 0);

// x on the grid for song time s, with the phrase's first bar line at T
export const gridX = (s, T, eighth) => cellX(0) + ((s - T) / eighth) * GRID.cell;

// The synth's own trace for the lead's phrase (physics/analog.json + analog-traces: pitch with its glide and
// vibrato, and the amp envelope, 240 a second from the phrase's start)
export function traceOf(ctx, part, t0, t1) {
  const an = ctx.data.get('physics/analog.json'), tr = ctx.data.get('physics/analog-traces');
  const ph = an.phrases.find((p) => p.stem === part && p.t < t1 && p.t + p.rows / an.rate > t0);
  if (!ph) return null;
  const rate = an.rate, row = (i) => tr.row(ph.row0 + Math.min(Math.max(i, 0), ph.rows - 1));
  const at = (s, col) => {
    const f = (s - ph.t) * rate, i = Math.floor(f), k = f - i;
    if (f < 0 || f > ph.rows - 1) return null;
    return row(i)[col] * (1 - k) + row(i + 1)[col] * k;
  };
  return { pitch: (s) => at(s, 0), amp: (s) => at(s, 1) ?? 0, t0: ph.t, t1: ph.t + ph.rows / rate, notes: ph.notes };
}

// height above the grid's line at song time s, at frame time t: the synth's pitch there, as far as the note
// sounding at s has lifted
export function gridHeight(trace, s, t) {
  if (!trace || s < trace.t0 || s > t + 0.02) return 0;
  let n = null;
  for (const m of trace.notes) { if (m.t > s) break; n = m; }
  const p = trace.pitch(s);
  if (!n || p === null) return 0;
  return Math.max(p - GRID.floor, 0) * GRID.lift * lifted(n, t);
}

// a glide between stretches, as a pitch line moves from note to note: a triangle-weighted mean over +-R samples
export function smoothed(h, R) {
  const n = h.length, out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    let s = 0, c = 0;
    for (let j = -R; j <= R; j++) {
      const q = h[clamp(i + j, 0, n - 1)], wgt = R + 1 - Math.abs(j);
      s += q * wgt; c += wgt;
    }
    out[i] = s / c;
  }
  return out;
}

// the rest pose's height at song time s for frame time t, exactly as the core's strandPoints draws it at human 0
// (the lead's note sounding at s, or the last one held, the tonic before any)
export function restPitch(notes, s, tonic) {
  let held = null;
  for (const m of notes) {
    if (m.t > s) break;
    held = m;
  }
  return held ? held.p : tonic;
}
export { smoothstep };
