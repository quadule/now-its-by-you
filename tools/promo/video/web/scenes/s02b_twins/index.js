// Breath 1: the synth lead, the whistle's two synth twins on the same notes, over the layer's drum machine.
// The strand parts in two, each an oscilloscope's trace of one twin: a fixed span of its sound across the frame,
// triggered on a rising zero crossing so a steady tone stands still, so a higher note packs more periods in.
//   upper  whistle~, the analog synth: bold, its own stem samples (the ladder's output, what is heard); fine behind
//          it, the two oscillators it filters, re-run from the preset (physics/analog.json: a square, and a quarter-
//          width pulse an octave down at 0.35, each detuned as captured) at the captured pitch (analog-traces).
//          Its light follows the captured amp envelope, its bloom the filter envelope opening the ladder.
//   lower  epiano~, the tine piano: bold, its own stem samples (the pickup, preamp and speaker); fine behind it,
//          the struck tine's own swing past the pickup as the model rang it (s02b/tine, prep/s02b_twins.py), so
//          the bark is the difference between the two. Its light follows the tine's swing.
//   floor  the 808's hits (physics/drummachine.json) as ring-downs on song time, now at the strand's own place:
//          each a comb of hairlines from the hit, as tall as its trigger size, falling to silence over its len_s,
//          choked at cut_s.
// Each source is drawn as a second trace of the same scope, at the shift (within a period) that lies closest to the
// sound. The strands fold back onto the strand's rest pose over the first beat of s03's two-beat dissolve.
// The traces' sizes are each part's own peak over the breath drawn as AMP; their shapes are the data's.
import { ground, lyric, label, strandPoints } from '../../core/draw.js';
import { clamp, smoothstep, mix } from '../../core/math.js';

const SPAN = 0.006;           // s of sound across the frame
const AMP = 100;              // a part's peak over the breath, in design units
const Y = { whistle: 360, epiano: 640 };
const TAPER = 0.1;            // the traces ease into the strand over this fraction of the width at each end
const FLOOR = { y: 1000, size: 170, step: 1 / 60, at: 0.62, back: 4.5, ahead: 2.5 };

// The source drawn under the sound as a second trace of the same scope: of its shifts over one period P (s), the one
// that lies closest to the heard trace. at(tau) is the source tau s after its window's start; returns source(u).
function aligned(heard, at, P, M = 96, K = 48) {
  const h = new Float32Array(M);
  for (let i = 0; i < M; i++) h[i] = heard((i + 0.5) / M);
  let best = 0, bestC = -Infinity;
  for (let j = 0; j < K; j++) {
    const d = (j / K) * P;
    let c = 0;
    for (let i = 0; i < M; i++) c += h[i] * at(((i + 0.5) / M) * SPAN + d);
    if (c > bestC) { bestC = c; best = d; }
  }
  return (u) => at(u * SPAN + best);
}

export default {
  id: 's02b_twins',
  section: 'breath1',
  enter: { kind: 'cut' },
  assets: ['s02b/stem-whistle~', 's02b/stem-epiano~', 's02b/tine', 's02b/tine-notes.json',
    'physics/analog.json', 'physics/analog-traces', 'physics/drummachine.json'],

  async init(ctx) {
    const d = ctx.data, tl = ctx.timeline;
    this.sec = tl.byId('breath1');
    const t0 = this.sec.t0, t1 = this.sec.t1;
    this.stem = { whistle: d.get('s02b/stem-whistle~'), epiano: d.get('s02b/stem-epiano~') };
    this.peak = {};
    for (const [k, a] of Object.entries(this.stem)) {
      let m = 1e-6;
      const i0 = Math.max(0, Math.floor((t0 - a.t0) * a.rate)), i1 = Math.min(a.values.length, Math.ceil((t1 - a.t0) * a.rate));
      for (let i = i0; i < i1; i++) m = Math.max(m, Math.abs(a.values[i]));
      this.peak[k] = m;
    }
    // the analog phrase of whistle~ over the breath, its traces, and the oscillators' phase against each other
    const an = d.get('physics/analog.json'), tr = d.get('physics/analog-traces');
    const ph = an.phrases.find((p) => p.stem === 'whistle~' && p.t < t1 && p.t + p.rows / an.rate > t0);
    this.ph = ph; this.anRate = an.rate;
    this.rows = tr.values.subarray(ph.row0 * 4, (ph.row0 + ph.rows) * 4);
    this.osc = ph.oscillators.map((o, i) => ({ ...o, ratio: 2 ** o.octave * 2 ** ((ph.detune_cents[i] || 0) / 1200) }));
    // the sub's phase when the main oscillator is at a rising edge: the integral of their frequency difference.
    // The oscillators' starting phases are not captured: they are taken as starting together with the phrase.
    const [o0, o1] = this.osc;
    this.drift = new Float64Array(ph.rows + 1);
    for (let i = 0; i < ph.rows; i++) {
      const f = 440 * 2 ** ((this.rows[i * 4] - 69) / 12);
      this.drift[i + 1] = this.drift[i] + f * (o1.ratio - o0.ratio / 2) / an.rate;
    }
    let am = 1e-6, fm = 1e-6;
    for (let i = 0; i < ph.rows; i++) { am = Math.max(am, this.rows[i * 4 + 1]); fm = Math.max(fm, this.rows[i * 4 + 2]); }
    this.ampMax = am; this.filtMax = fm;
    // the tines
    const tn = d.get('s02b/tine-notes.json');
    this.tine = d.get('s02b/tine').values; this.tineRate = tn.rate;
    // each tine's own frequency, from its rising zero crossings 10 to 200 ms after the blow (the piano sounds an
    // octave under the written note: the data's pitch, not the score's, sets the period)
    this.tines = tn.notes.map((n) => {
      const x = this.tine.subarray(n.x0, n.x0 + n.n), a = Math.round(0.01 * tn.rate), b = Math.min(n.n, Math.round(0.2 * tn.rate));
      let first = -1, last = -1, count = 0;
      for (let i = a + 1; i < b; i++) if (x[i - 1] < 0 && x[i] >= 0) { if (first < 0) first = i; last = i; count++; }
      return { ...n, hz: count > 1 ? ((count - 1) * tn.rate) / (last - first) : 440 * 2 ** ((n.p - 69) / 12) };
    });
    this.tinePeak = Math.max(1e-6, ...tn.notes.map((n) => n.peak));
    // the 808: the layer's hits within reach of the breath
    const back = FLOOR.back + 2.5;
    this.hits = d.get('physics/drummachine.json').hits
      .filter((h) => h.stem === 'drummachine' && h.t > t0 - back && h.t < t1 + FLOOR.ahead)
      .map((h) => ({ ...h, ring: Math.min(h.len_s, h.cut_s ?? Infinity) }));
    this.buf = new Float32Array(2048);
  },

  // the analog trace's column c at song time s (null outside the phrase)
  trace(s, c) {
    const f = (s - this.ph.t) * this.anRate, i = Math.floor(f), k = f - i;
    if (f < 0 || i >= this.ph.rows - 1) return null;
    return this.rows[i * 4 + c] * (1 - k) + this.rows[(i + 1) * 4 + c] * k;
  },

  // n samples of x (rate r, starting at song time a0) ending at song time t, from the latest rising zero crossing
  // that leaves room: an oscilloscope's trigger. Returns null where the data does not reach.
  window(x, rate, a0, t, n) {
    const end = Math.floor((t - a0) * rate);
    if (end - n < 1 || end >= x.length) return null;
    let s = end - n;
    for (let i = end - n; i > Math.max(end - n - 4096, 1); i--) if (x[i - 1] < 0 && x[i] >= 0) { s = i; break; }
    return s;
  },

  // read x at fractional index f
  at(x, f) { const i = Math.floor(f), k = f - i; return (x[i] || 0) * (1 - k) + (x[i + 1] || 0) * k; },

  // whistle~ at t: heard(u) and source(u) for u 0..1 across the frame, in units of AMP, and its light
  whistle(t) {
    const a = this.stem.whistle, n = Math.round(SPAN * a.rate);
    const s = this.window(a.values, a.rate, a.t0, t, n);
    const p = this.trace(t, 0), env = clamp((this.trace(t, 1) ?? 0) / this.ampMax), filt = clamp((this.trace(t, 2) ?? 0) / this.filtMax);
    const heard = s === null ? () => 0 : (u) => this.at(a.values, s + u * n) / this.peak.whistle;
    let source = () => 0;
    if (p !== null && env > 0.002) {
      const f = 440 * 2 ** ((p - 69) / 12), [o0, o1] = this.osc;
      const fi = clamp((t - this.ph.t) * this.anRate, 0, this.ph.rows - 1);
      const sub = this.drift[Math.floor(fi)] % 1;
      // osc.pulse: high for its width of each period, zero mean
      const pulse = (ph, w) => (((ph % 1) + 1) % 1 < w ? 1 : -1) - (2 * w - 1);
      const norm = o0.level * 2 * Math.max(o0.width, 1 - o0.width) + o1.level * 2 * Math.max(o1.width, 1 - o1.width);
      const at = (tau) => env * (o0.level * pulse(tau * f * o0.ratio, o0.width)
        + o1.level * pulse(sub + tau * f * o1.ratio, o1.width)) / norm;
      source = aligned(heard, at, 2 / (f * o0.ratio));
    }
    return { heard, source, env, glow: filt };
  },

  // epiano~ at t: the same, its source the newest struck tine
  epiano(t) {
    const a = this.stem.epiano, n = Math.round(SPAN * a.rate);
    const s = this.window(a.values, a.rate, a.t0, t, n);
    const heard = s === null ? () => 0 : (u) => this.at(a.values, s + u * n) / this.peak.epiano;
    let note = null;
    for (const q of this.tines) if (q.t <= t && t < q.t + q.n / this.tineRate) note = q;
    if (!note) return { heard, source: () => 0, env: 0, glow: 0 };
    const x = this.tine.subarray(note.x0, note.x0 + note.n), R = this.tineRate;
    const P = 1 / note.hz, m = Math.round((SPAN + P) * R);
    const st = this.window(x, R, note.t, t, m);
    if (st === null) return { heard, source: () => 0, env: 0, glow: 0 };
    let e = 0;
    for (let i = 0; i < m; i += 4) e = Math.max(e, Math.abs(x[st + i]));
    const source = aligned(heard, (tau) => this.at(x, st + tau * R) / this.tinePeak, P);
    return { heard, source, env: clamp(e / this.tinePeak), glow: Math.exp(-(t - note.t) / 0.15) };
  },

  render(ctx, t, target) {
    const k = ctx.k(t), ink = ctx.palette.inks(k), g = ctx.g;
    ground(ctx, t, target);
    const B = ctx.timeline.beatLength, t0 = this.sec.t0, t1 = this.sec.t1, W = ctx.size.w;
    const pull = smoothstep(t0, t0 + B, t) * (1 - smoothstep(t1 - 2 * B, t1 - B, t));
    const amber = ctx.palette.mix(ctx.palette.lin.sung, ink.ink, ink.side);
    const bloom = mix(1, 0, ink.side);

    this.floor(ctx, t, target, ink, pull);

    const rest = this.rest(ctx, t);
    const taper = (u) => smoothstep(0, TAPER, u) * smoothstep(1, 1 - TAPER, u);
    for (const [name, v] of [['whistle', this.whistle(t)], ['epiano', this.epiano(t)]]) {
      const yb = Y[name];
      const place = (fn) => rest.map((r) => {
        const u = clamp(r[0] / W);
        return [r[0], mix(r[1], yb - fn(u) * AMP * taper(u), pull)];
      });
      // the source, fine and cold, behind
      if (pull > 0.002) g.stroke(target, place(v.source), { width: 1.1, color: ink.cold, alpha: 0.42 * pull });
      // the sound, bold, amber as it sounds
      const col = ctx.palette.mix(ink.cold, amber, clamp(v.env * 1.3) * pull);
      g.stroke(target, place(v.heard), { width: mix(2.5, 2.8, pull), color: col,
        intensity: mix(1.35, 1, ink.side) * (1 + bloom * pull * (0.25 * v.env + 0.6 * v.glow)) });
    }

    const la = smoothstep(t0, t0 + B, t) * (1 - smoothstep(t1 - 2 * B, t1 - B, t));
    label(ctx, t, target, 'twins', { alpha: la });
    lyric(ctx, t, target);
  },

  // the drum machine's ring-downs on song time, now at the strand's own place
  floor(ctx, t, target, ink, pull) {
    if (pull <= 0.002) return;
    const W = ctx.size.w, F = FLOOR, span = F.back + F.ahead;
    const X = (s) => W * (F.at + (s - t) / span);
    const dots = [];
    for (const h of this.hits) {
      if (h.t > t) continue;
      const x0 = X(h.t);
      if (x0 > W + 10 || X(h.t + h.ring) < -10) continue;
      const H = h.size * F.size, age = t - h.t, flash = Math.exp(-age / 0.12);
      const fadeL = (x) => smoothstep(-20, W * 0.12, x);
      // the comb: a hairline each 1/60 s from the hit to now or its end, its height the ring's level then
      const until = Math.min(age, h.ring), n = Math.floor(until / F.step);
      for (let i = 0; i <= n; i++) {
        const tau = i * F.step, x = X(h.t + tau);
        if (x < -4 || x > W + 4) continue;
        const choke = h.cut_s != null && tau > h.cut_s - 4 * (h.cut_tau || 0.0015) ? 0 : 1;
        const lv = Math.exp(-6.9078 * tau / h.len_s) * choke;
        if (lv < 0.01) break;
        const y = H * lv;
        ctx.g.stroke(target, [[x, F.y - y], [x, F.y + y * 0.35]],
          { width: i === 0 ? 1.8 : 1, color: ink.cold, alpha: pull * fadeL(x) * (i === 0 ? 0.9 : 0.22 + 0.4 * lv),
            intensity: i === 0 ? 1 + 1.6 * flash * mix(1, 0, ink.side) : 1 });
      }
      dots.push({ x: x0, y: F.y - H, r: 2.2 + 3 * flash, color: ink.cold, alpha: pull * fadeL(x0) * (0.5 + 0.5 * flash),
        intensity: 1 + 2 * flash * mix(1, 0, ink.side), soft: 0.5 * flash });
    }
    // the floor's own line
    ctx.g.stroke(target, [[0, F.y], [W, F.y]], { width: 1, color: ink.rule, alpha: pull * 0.8 });
    ctx.g.points(target, dots);
  },

  // the strand's rest pose across the whole frame, as s02_voice hands it over (held level past its ends)
  rest(ctx, t) {
    const pts = strandPoints(ctx, t, { y: 540 }).points, out = [], W = ctx.size.w;
    let j = 0;
    for (let x = 0; x <= W; x += 4) {
      while (j < pts.length - 2 && pts[j + 1][0] < x) j++;
      const a = pts[j], b = pts[j + 1], k = clamp((x - a[0]) / Math.max(b[0] - a[0], 1e-9));
      out.push([x, mix(a[1], b[1], k)]);
    }
    return out;
  },

  // the strand where s03 takes it: the rest line
  anchor(ctx, t) {
    return { points: this.rest(ctx, t), width: 2.5, color: ctx.palette.inks(ctx.k(t)).cold };
  },
};
