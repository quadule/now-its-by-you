// Breath 2: the fiddle, a bowed string. One string across the frame in ink, its true shape from the instrumented
// bowed model (physics/bow-period): two straight lines meeting at a corner that runs round the string once a period,
// the Helmholtz motion. Behind it, the sixteen snapshots of the current period as a fan of hairlines: the lens the
// corner sweeps. The bow's hair crosses the string at its captured place (bow-tracks), moving with its captured
// velocity and pressing with its captured force.
//
// Slow motion: the corner is shown going round once every two beats (the string's 554 to 988 Hz period stretched
// to 1.25 s), its phase set so it leaves the bridge on every other beat. Each frame's shape is that frame's own
// period, read at that phase from its sixteen snapshots (the two nearest, each warped so their corners meet).
import { ground, lyric, label, strandPoints } from '../../core/draw.js';
import { smoothstep, mix, clamp } from '../../core/math.js';
import { Camera } from '../../core/camera.js';

const Y = 540;          // the string's rest height
const SCALE = 9;        // design units of displacement per unit of the model's displacement
const BEATS_PER_TRIP = 2;
const HAIRS = 22;       // the sheaf of hair drawn
const SHEAF = 70;       // its width (world units)
// the string in depth: its bridge near on the right, its nut far on the upper left; displacement is world up
const BRIDGE = [780, 110, 380], NUT = [-1300, -260, -1150];
const FOV = 30, FOCAL = 540 / Math.tan((FOV * Math.PI) / 360);
// the smallest drawn swing: a quiet frame's displacement is scaled up (at most GAIN_MAX times) so its peak reads
// as FLOOR units; the shape is the data's, only its size is raised
const FLOOR = 7, GAIN_MAX = 4;

export default {
  id: 's04_bow',
  section: 'breath2',
  enter: { kind: 'cut' },
  assets: ['physics/bow.json', 'physics/bow-period', 'physics/bow-tracks'],

  async init(ctx) {
    this.sec = ctx.timeline.byId('breath2');
    this.period = ctx.data.get('physics/bow-period');
    this.tracks = ctx.data.get('physics/bow-tracks');
    const [, S, , NP] = this.period.shape;
    this.S = S; this.NP = NP;
    // each frame's phase: where its first snapshot is in the corner's trip (0 at the bridge going out)
    const F = this.period.shape[0];
    this.phase0 = new Float32Array(F);
    this.corner = new Float32Array(F * S);
    for (let f = 0; f < F; f++) {
      let cx = 0, cy = 0;
      for (let s = 0; s < S; s++) {
        const { x, sign } = this.cornerOf(f, s);
        this.corner[f * S + s] = x;
        const psi = sign > 0 ? 0.5 * x : 0.5 + 0.5 * (1 - x);
        const a = 2 * Math.PI * (psi - s / S);
        cx += Math.cos(a); cy += Math.sin(a);
      }
      this.phase0[f] = ((Math.atan2(cy, cx) / (2 * Math.PI)) % 1 + 1) % 1;
    }
    // The bow's travel, slowed as the string is: in one shown trip (two beats) the hair moves as far as it truly
    // moves in one period of the string, velocity x samples a period (bow-tracks columns 0 and 3), drawn at the
    // string's own displacement scale. So the hair and the string under it move together while the hair grips.
    const tr = this.tracks, n = tr.rows, rl = tr.rowLength, sr = 44100;
    const trip = BEATS_PER_TRIP * ctx.timeline.beatLength;
    this.travel = new Float64Array(n + 1);
    for (let i = 0; i < n; i++) {
      const v = tr.values[i * rl], hz = tr.values[i * rl + 3];
      this.travel[i + 1] = this.travel[i] + (hz > 0 ? v * (sr / hz) * SCALE / trip : 0) / tr.rate;
    }
    // the marks carried along each hair: a seeded pattern (fibres and rosin), fixed to the hair
    const rnd = ctx.prng(5303);
    this.marks = [];
    for (let h = 0; h < HAIRS; h++) for (let m = 0; m < 22; m++) {
      this.marks.push({ h, u: rnd() * 1400, r: 0.5 + 0.9 * rnd() ** 3, a: 0.35 + 0.5 * rnd() });
    }
    this.shape = new Float32Array(NP);
    this.peak = new Float32Array(F);
    for (let f = 0; f < F; f++) {
      let m = 0;
      for (let q = 0; q < S; q++) { const d = this.snap(f, q); for (let p = 0; p < NP; p++) m = Math.max(m, Math.abs(d[p])); }
      this.peak[f] = m;
    }
  },

  // a snapshot's displacement at place p (0 the bridge .. NP - 1 the nut)
  snap(f, s) {
    const NP = this.NP, base = ((f * this.S + s) * 2) * NP;
    return this.period.values.subarray(base, base + NP);
  },

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
  },

  frame(t) { return clamp(Math.floor((t - this.period.t0) * this.period.rate), 0, this.period.shape[0] - 1); },

  // the string's shape at t into this.shape: the frame's period at the shown phase
  shapeAt(ctx, t) {
    const f = this.frame(t), S = this.S, NP = this.NP, out = this.shape;
    const trip = BEATS_PER_TRIP * ctx.timeline.beatLength;
    const phi = (((t - this.sec.t0) / trip) % 1 + 1) % 1;
    const q = ((phi - this.phase0[f]) % 1 + 1) % 1 * S;
    const s0 = Math.floor(q) % S, s1 = (s0 + 1) % S, u = q - Math.floor(q);
    const c0 = this.corner[f * S + s0], c1 = this.corner[f * S + s1];
    const xc = clamp(mix(c0, c1, u), 0.02, 0.98);
    const d0 = this.snap(f, s0), d1 = this.snap(f, s1);
    // read snapshot d (corner at cs) at place x of a string whose corner is at xc
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
  },

  // the bow's track values at t: velocity, force, position, pitch, and its travel so far
  bowAt(t) {
    const tr = this.tracks, rl = tr.rowLength;
    const p = clamp((t - tr.t0) * tr.rate, 0, tr.rows - 1), i = Math.min(Math.floor(p), tr.rows - 2), w = p - i;
    const v = (c) => tr.values[i * rl + c] * (1 - w) + tr.values[(i + 1) * rl + c] * w;
    return { v: v(0), force: v(1), pos: v(2), hz: v(3), travel: this.travel[i] * (1 - w) + this.travel[i + 1] * w };
  },

  // the drawn scale of frame f's displacement
  gain(f) { return SCALE * clamp(FLOOR / Math.max(this.peak[f], 1e-6), 1, GAIN_MAX); },

  render(ctx, t, target) {
    const k = ctx.k(t), ink = ctx.palette.inks(k);
    ground(ctx, t, target);
    const beat = ctx.timeline.beatLength, t0 = this.sec.t0, t1 = this.sec.t1, H = ctx.size.h;
    const pull = smoothstep(t0, t0 + beat, t) * (1 - smoothstep(t1 - beat, t1, t));
    const bow = this.bowAt(t);
    const cur = this.shapeAt(ctx, t), f = cur.f, xc = cur.xc, out = Float32Array.from(cur.out);
    const NP = this.NP, g = this.gain(f);
    const drift = (t - t0) / ctx.timeline.barLength;
    const cam = new Camera({ position: [140 - 30 * drift, -0.2 * FOCAL, FOCAL], target: [60 - 12 * drift, 20, -250], fov: FOV, size: ctx.size });
    // place p (0 the bridge) displaced by d, in the world; and on the frame
    const W3 = (p, d) => { const u = p / (NP - 1); return [mix(BRIDGE[0], NUT[0], u), mix(BRIDGE[1], NUT[1], u) - d, mix(BRIDGE[2], NUT[2], u)]; };
    const line = (o, gg) => { const pts = [], sc = []; for (let p = 0; p < NP; p++) { const q = cam.project(W3(p, o[p] * gg)); pts.push([q.x, q.y]); sc.push(q.scale); } return { pts, sc }; };

    // the string's recent shapes, a line a frame at its own place: they build the lens round the string
    const HIST = 72;
    for (let i = HIST; i >= 1; i--) {
      const ti = t - i / 60;
      if (ti < this.period.t0) continue;
      const r = this.shapeAt(ctx, ti), L = line(r.out, this.gain(r.f));
      ctx.g.stroke(target, L.pts, { width: (j) => 0.8 * L.sc[j], color: ink.ink, alpha: 0.28 * (1 - i / (HIST + 1)) ** 1.2 * pull });
    }
    // the period's sixteen snapshots: the lens the corner sweeps
    for (let q = 0; q < this.S; q++) {
      const L = line(this.snap(f, q), g);
      ctx.g.stroke(target, L.pts, { width: (j) => 0.9 * L.sc[j], color: ink.ink, alpha: 0.3 * pull });
    }

    // the string: the shown shape, bold, out of the strand's rest by pull
    const rest = strandPoints(ctx, t, { y: Y });
    const n = rest.points.length, pts = [];
    for (let i = 0; i < n; i++) {
      const pp = (1 - i / (n - 1)) * (NP - 1), a = Math.min(Math.floor(pp), NP - 2), w = pp - a;
      const d = (out[a] * (1 - w) + out[a + 1] * w) * g;
      const q = cam.project(W3(pp, d)), r = rest.points[i];
      pts.push([mix(r[0], q.x, pull), mix(r[1], q.y, pull)]);
    }
    ctx.g.stroke(target, pts, { width: mix(2.5, 3.4, pull), color: ctx.palette.mix(ink.cold, ink.ink, pull) });
    // the corner: the place the two straight lines meet, running round the string once a shown period
    {
      const pc = xc * (NP - 1), a = Math.min(Math.floor(pc), NP - 2), w = pc - a;
      const q = cam.project(W3(pc, (out[a] * (1 - w) + out[a + 1] * w) * g));
      ctx.g.points(target, [{ x: q.x, y: q.y, r: 8 * q.scale, color: ink.ink, alpha: pull }]);
    }

    // The bow: a sheaf of hair crossing the string at its captured place (bow-tracks), the hairs heavier where they
    // press the string as the captured force grows, marks carried along them at the bow's travel
    const on = smoothstep(0.02, 0.08, bow.force) * pull;
    if (on > 0.003) {
      const pb = bow.pos * (NP - 1), a = Math.min(Math.floor(pb), NP - 2), wq = pb - a;
      const db = (out[a] * (1 - wq) + out[a + 1] * wq) * g;
      const base = W3(pb, 0), dx = NUT[0] - BRIDGE[0], dz = NUT[2] - BRIDGE[2], dl = Math.hypot(dx, dz);
      const perp = [-dz / dl, 0, dx / dl];
      const N = 40, span = 760, press = 7 * bow.force;
      for (let h = 0; h < HAIRS; h++) {
        const o = (h / (HAIRS - 1) - 0.5) * SHEAF, P = [], wid = [];
        for (let i = 0; i < N; i++) {
          const yy = -span + (2 * span * i) / (N - 1);
          const q = cam.project([base[0] + perp[0] * o, base[1] + yy, base[2] + perp[2] * o]);
          P.push([q.x, q.y]);
          wid.push((0.45 + press * Math.exp(-(((yy + db) / 60) ** 2))) * q.scale);
        }
        ctx.g.stroke(target, P, { width: (i) => wid[i], color: ink.ink, alpha: on * (h === 0 || h === HAIRS - 1 ? 0.95 : 0.5) });
      }
      const L = 2 * span, dots = [];
      for (const m of this.marks) {
        const yy = ((((m.u - bow.travel) % L) + L) % L) - span;
        const o = (m.h / (HAIRS - 1) - 0.5) * SHEAF;
        const q = cam.project([base[0] + perp[0] * o, base[1] + yy, base[2] + perp[2] * o]);
        if (q.y < -10 || q.y > H + 10) continue;
        dots.push({ x: q.x, y: q.y, r: m.r * q.scale, color: ink.ink, alpha: on * m.a });
      }
      ctx.g.points(target, dots);
    }

    label(ctx, t, target, 'fiddle', { alpha: smoothstep(t0, t0 + beat, t) * (1 - smoothstep(t1 - beat, t1, t)) });
    lyric(ctx, t, target);
  },

  // the strand where s05 takes it: the rest line
  anchor(ctx, t) {
    return { points: strandPoints(ctx, t, { y: Y }).points, width: 2.5, color: ctx.palette.inks(ctx.k(t)).cold };
  },
};
