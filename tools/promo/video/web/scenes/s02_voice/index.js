// The voice (verse 1). Line 1: the phones the throat is told, beads on the machine's straight pitch line with their
// numbers beneath. Line 2: the throat's envelope, 200 lines a second, receding in depth. Line 3: the lines fall flat
// into rows and become every weight of the singer, lit by what each adds; the camera pulls back into a grid of
// identical copies. Line 4: the copies go out, one strand is left, and the harp's first plucked string rings in it.
import { ground, lyric, label, strandPoints } from '../../core/draw.js';
import { clamp, smoothstep, mix } from '../../core/math.js';
import { Ridge } from './ridge.js';
import { setupLine1, drawLine1, line1Points, scope } from './phones.js';
import { Weights, homography, COLS, ROWS } from './weights.js';
import { Harp } from './harp.js';

const RATE = 200;               // the throat's frames a second
const ENV0 = 1800, ENVN = 4600; // the envelope rows kept: 9.0 to 32.0 s
const RANGE = 62;               // dB from the loudest point shown to a line's foot (as throat_line.py)
const FIELD = { wx: 13, hy: 2.7, speed: 6, back: 360 / RATE, z0: 3.2 };   // the envelope field: 360 lines deep
// the weights lie on the floor where the field was: cell (u, v) at x = X0 - u * CELL, z = ZF - v * CELL (row 0 far)
const CELL = FIELD.wx / COLS, X0 = FIELD.wx / 2, ZF = FIELD.z0 + ROWS * CELL;
const onFloor = (u, v) => [X0 - u * CELL, 0, ZF - v * CELL];
const PITCH = [COLS + 90, ROWS + 150];   // cells from one copy to the next
const GRID = [14, 10];                    // copies either side of the original
const HINGE = ROWS / 2;                   // the row the picture closes along

// a camera by what it looks at: target T on the floor, distance h, elevation el and azimuth az (radians)
// (up turns from -y toward +z as the camera looks down, so it can look straight down with far still up the frame)
const viewOf = ({ T, h, el, az }) => {
  const k = smoothstep(1.0, 1.45, el), up = [0, -(1 - k), k], n = Math.hypot(...up);
  return {
    position: [T[0] - h * Math.cos(el) * Math.sin(az), T[1] - h * Math.sin(el), T[2] - h * Math.cos(el) * Math.cos(az)], target: T,
    up: up.map((v) => v / n),
  };
};
const paramsOf = (position, T) => {
  const d = [T[0] - position[0], T[1] - position[1], T[2] - position[2]], h = Math.hypot(...d);
  return { T, h, el: Math.asin(d[1] / h), az: Math.atan2(d[0], d[2]) };
};
const lerpView = (a, b, k) => ({
  T: a.T.map((v, i) => mix(v, b.T[i], k)), h: Math.exp(mix(Math.log(a.h), Math.log(b.h), k)), el: mix(a.el, b.el, k), az: mix(a.az, b.az, k),
});

// y of a polyline (x increasing) at x
function yAt(pts, x) {
  let lo = 0, hi = pts.length - 1;
  if (x <= pts[0][0]) return pts[0][1];
  if (x >= pts[hi][0]) return pts[hi][1];
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (pts[m][0] <= x) lo = m; else hi = m; }
  const k = (x - pts[lo][0]) / Math.max(pts[hi][0] - pts[lo][0], 1e-9);
  return pts[lo][1] + (pts[hi][1] - pts[lo][1]) * k;
}

// MIDI pitch from 200-a-second log f0 at song time s (held across gaps)
function midiAt(lf, s) {
  const f = clamp(s * RATE, 0, lf.length - 2), i = Math.floor(f), k = f - i;
  let a = lf[i], b = lf[i + 1];
  if (!Number.isFinite(a)) a = b;
  if (!Number.isFinite(b)) b = a;
  return Number.isFinite(a) ? 69 + 12 * Math.log2(Math.exp(a + (b - a) * k) / 440) : null;
}

export default {
  id: 's02_voice',
  section: 'verse1',
  enter: { kind: 'cut' },
  assets: ['throat/lead-0.00.env', 'throat/lead-0.00.ap', 'throat/lead-0.00.lf0', 'throat/lead-0.00.flags',
    'throat/lead-0.00-whole.lf0', 's02/phones-line1.json', 's02/wave-arp', 's02/wave-synthpad',
    'stems/drummachine.env', 'stems/synthbass.env', 's02/weights-index', 's02/weights-array', 's02/weights-arrays.json',
    'throat/lead-0.20.lf0', 'throat/lead-0.30.lf0', 'physics/pluck-harp-notes.json', 'physics/pluck-harp'],

  async init(ctx) {
    const S = (this.S = {});
    const env = ctx.data.get('throat/lead-0.00.env'), flags = ctx.data.get('throat/lead-0.00.flags');
    const tl = ctx.timeline, l2 = tl.lineOf('verse1', 1);
    S.lines = [0, 1, 2, 3].map((i) => tl.lineOf('verse1', i));
    S.sec = tl.byId('verse1');
    S.lf0whole = ctx.data.get('throat/lead-0.00-whole.lf0').values;
    S.freqs = env.freqs;
    S.ap = ctx.data.get('throat/lead-0.00.ap');
    S.lf0 = ctx.data.get('throat/lead-0.00.lf0').values;
    S.flags = flags.values;
    S.waves = { arp: ctx.data.get('s02/wave-arp'), pad: ctx.data.get('s02/wave-synthpad') };
    setupLine1(ctx, S);
    // the loudest point of line 2's frames (99th percentile of each frame's peak) sets the top
    const peaks = [];
    for (let f = Math.floor(l2.t0 * RATE); f < Math.ceil(l2.t1 * RATE); f++) {
      let m = -200;
      for (const v of env.row(f)) m = Math.max(m, v);
      peaks.push(m);
    }
    peaks.sort((a, b) => a - b);
    const top = peaks[Math.floor(0.99 * (peaks.length - 1))];
    // silence is not sung: a line settles over 40 ms where the phone is silence or breath (a 17-tap Hann)
    const han = Array.from({ length: 17 }, (_, i) => 0.5 - 0.5 * Math.cos((2 * Math.PI * (i + 1)) / 18));
    const hs = han.reduce((a, b) => a + b, 0);
    const lev = new Float32Array(ENVN * 128);
    for (let r = 0; r < ENVN; r++) {
      const f = ENV0 + r;
      let sil = 0;
      for (let k = 0; k < 17; k++) {
        const j = Math.min(Math.max(f + k - 8, 0), flags.rows - 1);
        sil += ((flags.values[j] >> 1) & 1) * han[k];
      }
      const keep = 1 - sil / hs, row = env.row(Math.min(f, env.rows - 1));
      for (let i = 0; i < 128; i++) lev[r * 128 + i] = clamp((row[i] - (top - RANGE)) / RANGE, 0, 1.15) * keep;
    }
    S.lev = lev;
    this.weights = await Weights.load(ctx);
    S.id = (await ctx.data.json('packet.json')).manifest.id.slice(0, 12);
    // the heard lead's pitch: each take where the stage plan has it (throat/takes.json "plan")
    const plan = (await ctx.data.json('throat/takes.json')).plan.filter((p) => p.t < S.sec.t1 + tl.barLength);
    S.heard = plan.map((p, i) => [i === 0 ? -Infinity : p.t, ctx.data.get(`throat/${p.id}.lf0`).values]);
    // the harp's strings over line 4, re-run from the captured loop
    S.harp = new Harp(ctx.data.get('physics/pluck-harp-notes.json'), ctx.data.get('physics/pluck-harp').values,
      { from: S.lines[3].t0 - tl.barLength / 4, to: S.sec.t1 + tl.barLength });
    // display scale, per note: each note's own largest shape in its second period is drawn at 80 to 190 design
    // units by its velocity, so every pluck opens the string clearly; its decay after that is the model's own
    S.pluckFrom = S.lines[3].t0 - tl.barLength / 4;
    S.noteGain = new Map();
    const plucked = S.harp.notes.filter((n) => n.t >= S.pluckFrom);
    const vs = plucked.map((n) => n.v), v0 = Math.min(...vs), v1 = Math.max(...vs);
    for (const n of plucked) {
      let big = 1e-9;
      for (const pl of n.planes) {
        const P = S.harp.period(pl);
        for (let k = 0; k < 8; k++) {
          const sh = S.harp.shapeAt(n, pl, 2 * P + (k * P) / 8, 61);
          if (sh) for (const v of sh) big = Math.max(big, Math.abs(v));
        }
      }
      S.noteGain.set(n, mix(80, 190, (n.v - v0) / Math.max(v1 - v0, 1e-9)) / big);
    }
    this.ridge = new Ridge(ctx.g, lev, ENVN, ENV0, RATE);
    // the drum machine's hits and the synth bass, as light: each hit's spectral flux, decaying over a quarter beat;
    // the bass's level above -48 dB
    const dm = ctx.data.get('stems/drummachine.env'), sb = ctx.data.get('stems/synthbass.env');
    S.hit = new Float32Array(dm.rows); S.bass = new Float32Array(sb.rows);
    let held = 0;
    for (let i = 0; i < dm.rows; i++) {
      const flux = dm.raw[i * 99 + 2] * (dm.flux_scale ?? 0.25);
      held = Math.max(held * Math.exp(-1 / dm.rate / (tl.beatLength / 4)), clamp(flux / 8));
      S.hit[i] = held;
    }
    for (let i = 0; i < sb.rows; i++) S.bass[i] = clamp((sb.values[i * 99] + 48) / 30);
  },

  // the field's level at a frame and a fractional point q (0..127), as the ridge's shader reads it
  level(S, frame, q) {
    const row = clamp(frame - ENV0, 0, ENVN - 1), i = Math.floor(q), f = q - i, L = S.lev;
    const at = (j) => L[row * 128 + clamp(j, 0, 127)];
    const a = at(i - 1), b = at(i), c = at(i + 1), d = at(i + 2);
    return Math.max(0.5 * (2 * b + (-a + c) * f + (2 * a - 5 * b + 4 * c - d) * f * f + (-a + 3 * b - 3 * c + d) * f * f * f), 0);
  },

  // the harmonics as amber stalks where the voice is pitched; breath as points where it is not (newest lines)
  newest(ctx, t, target, cam, { flat, alpha, ink, light }) {
    const S = this.S, g = ctx.g, now = t * RATE, frame = Math.floor(now);
    const age = (now - frame) / RATE, z = FIELD.z0 + age * FIELD.speed;
    const W = (q, h) => [(0.5 - q / 127) * FIELD.wx, -h * FIELD.hy * flat, z];
    const fl = S.flags[frame] ?? 2, voiced = (fl & 1) && !(fl & 2);
    const ap = S.ap.row(Math.min(frame, S.ap.rows - 1));
    const apAt = (row, q) => { const x = (q / 127) * 31, i = Math.min(Math.floor(x), 30); return row[i] + (row[i + 1] - row[i]) * (x - i); };
    const qOf = (hz) => {
      const F = S.freqs; let i = 0;
      while (i < 126 && F[i + 1] < hz) i++;
      return i + clamp((hz - F[i]) / (F[i + 1] - F[i]));
    };
    if (voiced) {
      const f0 = Math.exp(S.lf0[frame]);
      for (let k = 1; k * f0 < S.freqs[127]; k++) {
        const q = qOf(k * f0), h = this.level(S, frame, q);
        const p0 = cam.project(W(q, 0)), p1 = cam.project(W(q, h));
        if (!p0.visible || h < 0.01) continue;
        const clear = 1 - apAt(ap, q);
        g.stroke(target, [[p0.x, p0.y], [p1.x, p1.y]], { width: Math.max(0.006 * p0.scale, 0.9), color: ink.sung,
          intensity: 1.2 * light, alpha: alpha * (0.25 + 0.75 * clear) });
      }
    }
    // breath: the network's aperiodicity as scattered points under the newest few lines, seeded by their frame
    const pts = [];
    for (let l = 0; l < 4; l++) {
      const f = frame - l, fz = FIELD.z0 + ((now - f) / RATE) * FIELD.speed;
      if ((S.flags[f] ?? 2) & 2) continue;
      const apl = S.ap.row(Math.min(f, S.ap.rows - 1));
      const rnd = ctx.prng(9203, f);
      for (let n = 0; n < 700; n++) {
        const q = rnd() * 127, u = rnd(), v = rnd();
        if (u >= apAt(apl, q) ** 1.5) continue;
        const h = v * this.level(S, f, q);
        const p = cam.project([(0.5 - q / 127) * FIELD.wx, -h * FIELD.hy * flat, fz]);
        if (!p.visible) continue;
        pts.push({ x: p.x, y: p.y, r: Math.max(0.0075 * p.scale, 0.7), color: ink.ink2, alpha: alpha * (1 - l / 4) * 0.9, intensity: light });
      }
    }
    g.points(target, pts);
  },

  // the beats that pace line 4: the first three on or after its start
  beats4(ctx) {
    const L4 = this.S.lines[3], bs = ctx.timeline.beats.filter((b) => b >= L4.t0);
    return bs.slice(0, 3);
  },

  // the camera at t: drifting along the ridge (line 2); down over the weights, slowly across them, then pulled back
  // over the grid of copies (line 3); in to the one copy left, looking straight down along its middle row (line 4)
  view(ctx, t) {
    const [, L2, L3, L4] = this.S.lines, B = ctx.timeline.beatLength, [, b1] = this.beats4(ctx);
    const u = clamp((t - L2.t0) / (L3.t0 - L2.t0));
    const drift = mix(1.6, -1.4, smoothstep(0, 1, u));
    const k2 = paramsOf([drift, -3.4, -4.6 + 0.8 * u], [drift * 0.4 - 0.4, -0.2, 7]);
    const a = { T: onFloor(420, 130), h: 3.2, el: 1.2, az: 0.05 };
    const b = { T: onFloor(455, 165), h: 2.7, el: 1.28, az: 0.02 };
    const c = { T: onFloor(COLS / 2, HINGE + 900), h: 210, el: 1.02, az: 0 };
    // straight down at the hinge, the picture's width filling the frame's
    const focal = ctx.size.h / 2 / Math.tan((40 * Math.PI) / 360);
    const d = { T: onFloor(COLS / 2, HINGE), h: (COLS * CELL * focal) / ctx.size.w, el: Math.PI / 2 - 1e-4, az: 0 };
    const ta = L3.t0 + 2 * B, tb = L3.t0 + 5 * B, tc = L4.t0 - B / 2;
    if (t < L3.t0) return k2;
    if (t < ta) return lerpView(k2, a, smoothstep(L3.t0, ta, t));
    if (t < tb) return lerpView(a, b, ctx.math.ease.inOutSine((t - ta) / (tb - ta)));
    if (t < L4.t0) return lerpView(b, c, smoothstep(tb, tc, t));
    return lerpView(c, d, ctx.math.ease.inOutSine((t - L4.t0) / (b1 - L4.t0)));
  },
  camera(ctx, t) {
    return new ctx.camera.Camera({ ...viewOf(this.view(ctx, t)), fov: 40, size: ctx.size, near: 0.05 });
  },

  // frame -> cells of the picture on the floor, seen through cam: from four cells around where it looks
  floorH(cam) {
    const T = cam.target, u0 = (X0 - T[0]) / CELL, v0 = (ZF - T[2]) / CELL, r = 40;
    const cells = [[u0 - r, v0 - r], [u0 + r, v0 - r], [u0 + r, v0 + r], [u0 - r, v0 + r]];
    const scr = cells.map(([u, v]) => cam.project(onFloor(u, v)));
    if (scr.some((p) => !p.visible)) return null;
    const H = homography(scr.map((p) => [p.x, p.y]), cells);
    const c = cam.project(onFloor(u0, v0));
    if (H[6] * c.x + H[7] * c.y + H[8] < 0) for (let i = 0; i < 9; i++) H[i] = -H[i];
    return H;
  },

  // line 4: the strand as a taut, level string across the frame, plucked by each harp note (the newest note's planes,
  // strobed so the kink runs once along it each beat, with the last period as a faint fan); above it the voice's
  // pitch line, the heard take loosening away from the human-0 take's straight steps
  string4(ctx, t, target, { ink, alpha, light, rest, pitchIn }) {
    const S = this.S, g = ctx.g, tl = ctx.timeline, w = ctx.size.w, B = tl.beatLength;
    // the notes plucked by now; a new note takes the string over in a sixteenth
    const notes = S.harp.notes.filter((n) => n.t <= t && n.t >= S.pluckFrom);
    const amp = tl.gain('harp', t) * (1 - rest);
    const layers = [];
    notes.forEach((n, i) => {
      const next = notes[i + 1], k = next ? 1 - smoothstep(next.t, next.t + B / 4, t) : 1;
      if (k > 0) layers.push({ n, k: k * S.noteGain.get(n) });
    });
    // the displacement of one plane ('across' or 'along') at song time u, a fraction `back` of a period earlier
    const at = (u, back, plane) => {
      const parts = [];
      for (const { n, k } of layers) for (const pl of n.planes) {
        if (pl.plane !== plane) continue;
        const sh = S.harp.strobed(n, pl, u, B, back, 321);
        if (sh) parts.push({ sh, k });
      }
      return (x) => {
        let d = 0;
        for (const { sh, k } of parts) {
          const p = (x / w) * (sh.length - 1), i = Math.min(Math.floor(p), sh.length - 2);
          d += k * (sh[i] + (sh[i + 1] - sh[i]) * (p - i));
        }
        return d * amp;
      };
    };
    const xs = [];
    for (let x = 0; x <= w; x += 3) xs.push(x);
    const rl = this.restLine(ctx, t, rest), base = xs.map(rl);
    const across = at(t, 0, 'across'), along = at(t, 0, 'along');
    let peak = 0;
    const line = xs.map((x, i) => { const d = across(x); peak = Math.max(peak, Math.abs(d)); return [x, base[i] - d]; });
    if (peak > 0.5) {
      const vis = clamp(peak / 20);
      // the trail: where the string was over the last half beat, fading
      for (let k = 6; k >= 1; k--) {
        const dk = at(t - (k * B) / 12, 0, 'across');
        g.stroke(target, xs.map((x, i) => [x, base[i] - dk(x)]), { width: 1, color: ink.sung, intensity: light, blend: 'add',
          alpha: alpha * vis * 0.16 * (1 - k / 7) });
      }
      // the lens of the last period: sixteen snapshots
      for (let k = 1; k <= 16; k++) {
        const dk = at(t, k / 16, 'across');
        g.stroke(target, xs.map((x, i) => [x, base[i] - dk(x)]), { width: 0.8, color: ink.sung, intensity: light, alpha: alpha * 0.3 * vis });
      }
      // the other plane (the string's swing toward and away from us) as a fine line of its own between the same ends
      g.stroke(target, xs.map((x, i) => [x, base[i] - along(x)]), { width: 1.2, color: ink.ink2, intensity: light,
        alpha: alpha * 0.6 * vis });
      // the string's glow on the dark
      g.stroke(target, line, { width: 18, color: ink.sung, intensity: 0.6 * light, blend: 'add', alpha: alpha * 0.3 * vis });
    }
    const r = clamp(peak / 10) * (1 - rest);
    g.stroke(target, line, { width: mix(4, 2.5, rest), color: ink.cold.map((c, i) => mix(c, ink.sung[i], Math.max(r, 1 - rest) * (1 - rest))),
      intensity: mix(1.4, 1.9, r) * light, alpha });
    // the voice above: the human-0 take's steps as a ghost, the heard take over it, in the core strand's window
    if (pitchIn > 0) {
      const back = 1.8 * tl.barLength, ahead = tl.barLength, nowAt = 0.62, top = 300, tonic = tl.tonic;  // the core strand's window
      const sOf = (x) => t + (x / w - nowAt) * (back + ahead);
      const heard = (s) => { let lf = S.heard[0][1]; for (const [a, v] of S.heard) if (s >= a) lf = v; return midiAt(lf, s); };
      const ghost = [], voice = [];
      for (let x = 0; x <= w; x += 2) {
        const s = sOf(x), m0 = midiAt(S.lf0whole, s), m = heard(s);
        if (m0 !== null) ghost.push([x, top - (m0 - tonic) * 9]);
        if (m !== null) voice.push([x, top - (m - tonic) * 9]);
      }
      const nowI = Math.round((nowAt * w) / 2);
      const fade = (i, n) => (i <= nowI ? smoothstep(0, nowI * 0.5, i) : 0.3 * (1 - (i - nowI) / Math.max(n - nowI, 1)));
      g.stroke(target, ghost, { width: 1, color: ink.cold, alpha: (i) => pitchIn * 0.45 * fade(i, ghost.length) });
      g.stroke(target, voice, { width: 1.8, color: ink.ink, intensity: 1.2 * light, alpha: (i) => pitchIn * fade(i, voice.length) });
    }
  },

  // the string with no pluck in it: level at y 540, eased in the last beat onto the strand's rest pose
  restLine(ctx, t, rest) {
    if (rest <= 0) return () => 540;
    const pts = strandPoints(ctx, t).points;
    return (x) => mix(540, yAt(pts, x), rest);
  },

  // the strand at t as this scene hands it over: on the last bar line, the rest pose
  anchor(ctx, t) {
    const end = this.S.sec.t1, B = ctx.timeline.beatLength, rest = smoothstep(end - B, end, t);
    const y = this.restLine(ctx, t, rest), pts = [];
    for (let x = 0; x <= ctx.size.w; x += 3) pts.push([x, y(x)]);
    return { points: pts, alpha: 1, width: 2.5, color: ctx.palette.inks(ctx.k(t)).cold };
  },

  render(ctx, t, target) {
    const S = this.S, g = ctx.g, tl = ctx.timeline, ink = ctx.palette.inks(ctx.k(t));
    const gnd = ground(ctx, t, target);
    const B = tl.beatLength, [L1, L2, L3, L4] = S.lines, t0 = S.sec.t0;
    const fi = clamp(Math.round(t * 60), 0, S.hit.length - 1);
    const light = 1 + 0.35 * S.hit[fi] + 0.12 * S.bass[fi];

    // line 1: out of rest into the phones, then away as line 2 begins
    const show = smoothstep(t0, t0 + 2 * B, t);
    const fade1 = 1 - smoothstep(L2.t0 - B / 2, L2.t0 + B / 4, t);
    if (fade1 > 0) {
      const wa = smoothstep(S.waves.arp.t0, t0 + B, t) * fade1;
      scope(ctx, t, target, S.waves.arp, { y: 300, amp: 900, color: ink.cold, alpha: 0.16 * wa, width: 1 });
      scope(ctx, t, target, S.waves.pad, { y: 300, amp: 900, span: 0.025, color: ink.ink2, alpha: 0.13 * wa, width: 1 });
      const rest = strandPoints(ctx, t).points, mine = line1Points(ctx, S);
      const pts = [];
      for (let x = 0; x <= ctx.size.w; x += 3) pts.push([x, mix(yAt(rest, x), yAt(mine, x), show)]);
      g.stroke(target, pts, { width: mix(2.5, 2, show), color: ink.cold, intensity: 1.3 * light, alpha: fade1 });
      drawLine1(ctx, t, target, S, { show, fade: fade1, ink, light });
    }

    // line 2: the envelope field rises out of the strand, the camera drifting along the ridge
    const rise = smoothstep(L2.t0, L2.t0 + 1.25 * B, t) * (1 - smoothstep(L3.t0 - B / 8, L3.t0 + B, t));
    const gone = 1 - smoothstep(L3.t0 + B / 2, L3.t0 + 1.5 * B, t);
    if (rise > 0 || (t > L3.t0 && gone > 0)) {
      // the field is drawn at the frame's own instant (its shutter closed): 200 lines a second moving under a
      // half-frame shutter would draw each hairline several times over
      const tq = Math.floor(t * tl.fps + 1e-6) / tl.fps;
      const cam = this.camera(ctx, tq);
      this.ridge.draw(target, cam, {
        now: tq * RATE, count: 360, every: 1, ...FIELD, flat: rise, width: 0.0045, newWidth: 0.014,
        fog: [FIELD.back / 9, FIELD.back], color: ink.cold.map((c) => c * 0.9 * light), newColor: ink.cold.map((c) => c * 1.8 * light),
        ground: gnd, alpha: t < L3.t0 ? rise : gone, fill: t < L3.t0,
      });
      if (t < L3.t0) this.newest(ctx, tq, target, cam, { flat: rise, alpha: rise, ink, light });
    }
    // line 3: the field falls flat and the weights are on the floor where it lay
    const wIn = smoothstep(L3.t0 - B / 8, L3.t0 + B, t);
    // line 4: the copies go dark from the outside in on the beats; the one left closes along its middle row, on a
    // beat, into a single line of light, which is the strand
    const [b0, b1, b2] = this.beats4(ctx);
    // rings of copies kept: all, then the outer ones on line 4's start, the middle ones on its first beat, the rest
    // but the original on its second
    const keep = Math.max(GRID[0] + 1 - 6 * smoothstep(L4.t0 - B / 8, L4.t0 + B / 8, t)
      - (GRID[0] - 5) * smoothstep(b0 - B / 8, b0 + B / 8, t) - 6 * smoothstep(b1 - B / 4, b1, t), 0);
    const fold = t < b1 ? 0 : clamp((t - b1) / (b2 - b1)) ** 2;          // closing faster to the beat, like a book let fall
    const closed = t >= b2;
    if (wIn > 0 && !closed) {
      const cam = this.camera(ctx, t);
      const back = smoothstep(L3.t0 + 5 * B, L4.t0 - B / 2, t);
      this.weights.light(ctx, t, { ground: gnd, ink: ink.ink, pos: ink.sung.map((c) => c * 1.5 * light),
        neg: ink.cold.map((c) => c * 1.5 * light), rest: mix(0.2, 0.08, back), glow: 1.4, curve: mix(1, 2.2, back) });
      const lyr = smoothstep(L3.t0 - B / 2, L3.t0, t);
      const opts = { alpha: wIn, grid: GRID, keep, pitch: PITCH, mask: lyr, maskY: [770, 845], copies: smoothstep(0.1, 0.5, back),
        top: [mix(110, 130, back), mix(250, 270, back)], far: [mix(1e5, 12, back), mix(2e5, 30, back)] };
      if (fold <= 0) {
        const H = this.floorH(cam);
        if (H) this.weights.show(ctx, target, H, opts);
      } else {
        // each half turns up about the hinge row until the two meet face to face
        const th = (fold * Math.PI) / 2, zh = onFloor(0, HINGE)[2];
        for (const [v0, v1, sgn] of [[0, HINGE, 1], [HINGE, ROWS, -1]]) {
          const W = (u, v) => { const dd = Math.abs(v - HINGE) * CELL; return [X0 - u * CELL, -dd * Math.sin(th), zh + sgn * dd * Math.cos(th)]; };
          const cells = [[0, v0], [COLS, v0], [COLS, v1], [0, v1]];
          const scr = cells.map(([u, v]) => cam.project(W(u, v)));
          if (scr.some((p) => !p.visible) || fold > 0.985) continue;
          const H = homography(scr.map((p) => [p.x, p.y]), cells);
          const m = scr.reduce((a, p) => [a[0] + p.x / 4, a[1] + p.y / 4], [0, 0]);
          if (H[6] * m[0] + H[7] * m[1] + H[8] < 0) for (let i = 0; i < 9; i++) H[i] = -H[i];
          this.weights.show(ctx, target, H, { ...opts, grid: [0, 0], rows: [v0, v1] });
        }
      }
      // under each copy near enough to read, the file's id
      if (back > 0) {
        const id = ctx.type.text(S.id, { role: 'numeral', size: 10 });
        for (let j = -GRID[1]; j <= GRID[1]; j++) for (let i = -GRID[0]; i <= GRID[0]; i++) {
          const ring = Math.max(Math.abs(i), Math.abs(j)), on = clamp(keep - ring + 1) * (ring === 0 ? 1 : smoothstep(0.1, 0.5, back));
          if (on <= 0) continue;
          const p = cam.project(onFloor(i * PITCH[0] + COLS / 2, j * PITCH[1] + ROWS + 75));
          const wide = (COLS * CELL) * p.scale;
          if (!p.visible || wide < id.w + 22 || p.x < -60 || p.x > ctx.size.w + 60 || p.y < 230 || p.y > 800) continue;
          ctx.type.draw(target, id, Math.round(p.x), Math.round(p.y), { color: ink.ink2,
            alpha: on * back * (1 - fold) * smoothstep(id.w + 22, id.w + 45, wide) * (1 - smoothstep(770, 800, p.y)) * smoothstep(230, 290, p.y), align: 'center' });
        }
      }
    }
    // the line of light where the halves meet, then the strand: a string plucked by the harp
    if (fold > 0.6) {
      const flash = smoothstep(0.6, 1, fold) * (closed ? Math.exp(-(t - b2) / B) : 1);
      g.stroke(target, [[0, 540], [ctx.size.w, 540]], { width: 2.5, color: ink.sung, intensity: 1 + 2.5 * flash, alpha: closed ? flash : smoothstep(0.6, 1, fold) });
    }
    if (closed) {
      const end = S.sec.t1, rest = smoothstep(end - B, end, t);
      this.string4(ctx, t, target, { ink, alpha: 1, light, rest, pitchIn: smoothstep(b2, b2 + B, t) * (1 - rest) });
    }
    label(ctx, t, target, 'weights', { alpha: smoothstep(L3.t0 + B / 2, L3.t0 + 1.25 * B, t) * (1 - smoothstep(b1, b1 + B / 2, t)) });
    label(ctx, t, target, 'throat', { alpha: smoothstep(L2.t0, L2.t0 + B, t) * (1 - smoothstep(L3.t0, L3.t0 + B / 2, t)) });
    lyric(ctx, t, target);
  },
};
