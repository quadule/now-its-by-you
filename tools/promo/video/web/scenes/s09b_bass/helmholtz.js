// The bowed bass's string in slow motion (data/bass/, prep/bass.py), read as s04_bow reads the fiddle's: at each video
// frame, sixteen snapshots of one period of the string (the instrumented bowed.run_primed's own waves); the corner is
// shown going round once every `beats` beats, its phase set by `t0`, each frame's shape read at that phase from its
// own period (the two nearest snapshots, each warped so their corners meet). The bow's tracks at 240 a second.
import { clamp, mix } from '../../core/math.js';

const SR = 44100;

export class Helmholtz {
  // period, tracks: the window's arrays (data.get); t0: the phase's origin (s); beats: beats a shown trip
  constructor(ctx, period, tracks, { t0, beats = 2 }) {
    this.period = period;
    this.tracks = tracks;
    this.t0 = t0;
    this.trip = beats * ctx.timeline.beatLength;
    const [F, S, , NP] = period.shape;
    this.F = F; this.S = S; this.NP = NP;
    this.phase0 = new Float32Array(F);
    this.corner = new Float32Array(F * S);
    this.peak = new Float32Array(F);
    for (let f = 0; f < F; f++) {
      let cx = 0, cy = 0, m = 0;
      for (let s = 0; s < S; s++) {
        const { x, sign } = this.cornerOf(f, s);
        this.corner[f * S + s] = x;
        const psi = sign > 0 ? 0.5 * x : 0.5 + 0.5 * (1 - x);
        const a = 2 * Math.PI * (psi - s / S);
        cx += Math.cos(a); cy += Math.sin(a);
        const d = this.snap(f, s);
        for (let p = 0; p < NP; p++) m = Math.max(m, Math.abs(d[p]));
      }
      this.phase0[f] = ((Math.atan2(cy, cx) / (2 * Math.PI)) % 1 + 1) % 1;
      this.peak[f] = m;
    }
    // the bow's travel, slowed as the string is: in one shown trip the hair moves as far as it truly moves in one
    // period of the string (velocity x samples a period), in the model's displacement units
    const n = tracks.rows, rl = tracks.rowLength;
    this.travel = new Float64Array(n + 1);
    for (let i = 0; i < n; i++) {
      const v = tracks.values[i * rl], hz = tracks.values[i * rl + 3];
      this.travel[i + 1] = this.travel[i] + (hz > 0 ? v * (SR / hz) / this.trip : 0) / tracks.rate;
    }
    this.out = new Float32Array(NP);
  }

  // a snapshot's displacement at place p (0 the bridge .. NP - 1 the nut)
  snap(f, s) {
    const NP = this.NP, base = ((f * this.S + s) * 2) * NP;
    return this.period.values.subarray(base, base + NP);
  }

  // the corner of a snapshot: the place of its largest displacement (refined by a parabola), 0..1 from the bridge
  cornerOf(f, s) {
    const d = this.snap(f, s), NP = this.NP;
    let i = 0;
    for (let p = 1; p < NP; p++) if (Math.abs(d[p]) > Math.abs(d[i])) i = p;
    let x = i;
    if (i > 0 && i < NP - 1) {
      const a = Math.abs(d[i - 1]), b = Math.abs(d[i]), c = Math.abs(d[i + 1]), den = a - 2 * b + c;
      if (Math.abs(den) > 1e-9) x = i + clamp(0.5 * (a - c) / den, -0.5, 0.5);
    }
    return { x: x / (NP - 1), sign: Math.sign(d[i]) || 1 };
  }

  frame(t) { return clamp(Math.floor((t - this.period.t0) * this.period.rate), 0, this.F - 1); }

  // the string's shape at t (into out, or this.out): the frame's period at the shown phase
  shapeAt(t, out = this.out) {
    const f = this.frame(t), S = this.S, NP = this.NP;
    const phi = (((t - this.t0) / this.trip) % 1 + 1) % 1;
    const q = ((phi - this.phase0[f]) % 1 + 1) % 1 * S;
    const s0 = Math.floor(q) % S, s1 = (s0 + 1) % S, u = q - Math.floor(q);
    const c0 = this.corner[f * S + s0], c1 = this.corner[f * S + s1];
    const xc = clamp(mix(c0, c1, u), 0.02, 0.98);
    const d0 = this.snap(f, s0), d1 = this.snap(f, s1);
    const read = (d, cs, x) => {
      const src = x <= xc ? x * cs / xc : cs + (x - xc) * (1 - cs) / (1 - xc);
      const p = clamp(src, 0, 1) * (NP - 1), i = Math.min(Math.floor(p), NP - 2), w = p - i;
      return d[i] * (1 - w) + d[i + 1] * w;
    };
    for (let p = 0; p < NP; p++) {
      const x = p / (NP - 1);
      out[p] = read(d0, c0, x) * (1 - u) + read(d1, c1, x) * u;
    }
    return { f, out, xc };
  }

  // the bow's track values at t: velocity, force, position, pitch, its travel so far, and the bridge force
  bowAt(t) {
    const tr = this.tracks, rl = tr.rowLength;
    const p = clamp((t - tr.t0) * tr.rate, 0, tr.rows - 1), i = Math.min(Math.floor(p), tr.rows - 2), w = p - i;
    const v = (c) => tr.values[i * rl + c] * (1 - w) + tr.values[(i + 1) * rl + c] * w;
    return { v: v(0), force: v(1), pos: v(2), hz: v(3), out: v(4), travel: this.travel[i] * (1 - w) + this.travel[i + 1] * w };
  }

  // displacement d at place p (0..NP-1, fractional) of a shape
  at(d, p) {
    const NP = this.NP, a = clamp(Math.floor(p), 0, NP - 2), w = clamp(p - a, 0, 1);
    return d[a] * (1 - w) + d[a + 1] * w;
  }
}
