// A sung note's shape from its nine numbers, as songbird/synth/voice.py applies a gesture (pitch_track) and
// songbird/realize.py places it (sung_as). Re-run here: the cents, the dB and the times are the record's;
// the vibrato's rate (5.6 Hz) and onset (0.25 s, at most 0.35 of the note) are VoiceParams' own defaults,
// its phase starts at the onset (the engine draws each note's phase and drift at random).
import { clamp } from '../../core/math.js';

export const FIELDS = ['early', 'hold', 'level', 'swell', 'scoop', 'bend', 'fall', 'vibrato', 'tune'];
export const VIBRATO_RATE = 5.6;
export const VIBRATO_DELAY = 0.25;

// cents off the written pitch at time u of a note sung from `start` for `dur` seconds
export function cents(g, start, dur, u) {
  const heard = start + dur, d = Math.max(dur, 0.05);
  const x = clamp((u - start) / d);
  const approach = Math.min(0.12, 0.3 * d), letgo = Math.min(0.12, 0.35 * d);
  const into = clamp((u - start) / approach), out = clamp((u - (heard - letgo)) / letgo);
  let c = g.scoop * 0.5 * (1 + Math.cos(Math.PI * into));
  c += g.bend * clamp((x - 0.3) / 0.6);
  c += g.fall * 0.5 * (1 - Math.cos(Math.PI * out));
  c += g.tune * clamp((u - start) / 0.03) * clamp((heard - u) / 0.03);
  if (g.vibrato > 0) {
    const delay = Math.min(VIBRATO_DELAY, 0.35 * d), w = Math.max(u - start - delay, 0);
    const v = (1 - Math.exp(-w / 0.12)) * clamp((heard - u) / 0.08);
    c += g.vibrato * v * Math.sin(2 * Math.PI * VIBRATO_RATE * w);
  }
  return c;
}

// dB over the note's own level at fraction x of it: level, growing by swell from start to end
export const decibels = (g, x) => g.level + g.swell * x;

// the written note under a sung one: realize.sung_as undone (start = written - early beats, held hold of its length)
export function written(n, beat) {
  const g = n.g;
  const start = n.t + g.early * beat;
  return { t: start, d: (n.d - g.early * beat) / g.hold };
}

// a number as the record stores it, with a true minus
export function figure(v) {
  const s = Number.isInteger(v) ? String(v) : String(+v.toFixed(4));
  return s.replace('-', '−');
}
