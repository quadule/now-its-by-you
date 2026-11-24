// Breath 3: the harp, a plucked string. The bridge left one ember (the tree's root, this file) and the daisy in the
// dark. From the ember each harp note of the breath's two rolls lights a string in amber, fanning upward, low strings
// long and near the level, high ones short and steep: its shape the note's own loop re-run from its start with the
// captured parameters (physics/pluck-harp), its travelling wave shown in slow motion, once a beat; it rings out and
// stays lit. Beneath them the bowed bass's first notes, one long string out of the strand: its Helmholtz corner
// running round it once every two beats (data/bass/breath3-period, prep/bass.py), the period's snapshots behind it.
// The light warms a little, as under a lamp; refrain 3's daylight comes in from the daisy (s09_broadside's ink).
import { ground, lyric, label, strandPoints } from '../../core/draw.js';
import { smoothstep, clamp, mix, ease } from '../../core/math.js';
import { tree } from '../s08_lineage/tree.js';
import { DAISY } from '../s08_lineage/index.js';
import { Helmholtz } from '../s09b_bass/helmholtz.js';
import { runPlane, shapeAt, SR } from './strings.js';

const DEG = Math.PI / 180;
const ANGLE = [-7, -46];       // a string's angle from the ember (degrees, up) at the lowest and highest pitch
const PITCH = [36, 72];        // the pitches those angles belong to
const LONGEST = 1720;          // the lowest note's length; a string's length goes as its period to the 0.3
const SWING = 120;             // design units of a string's swing per unit of velocity, at its pluck
const BASS = { angle: 6.5, length: 1400, scale: 0.62 };   // the bowed bass's string beneath the fan
const M = 160;                 // points along a string
const LAMP = 0.3;              // the paper amount the breath warms to (below the flip: a lamp on the stage)

export default {
  id: 's08b_harp',
  section: 'breath3',
  enter: { kind: 'cut' },
  assets: ['packet.json', 's08/mix-bands', 'physics/pluck-harp-notes.json', 'physics/pluck-harp', 'bass/bass.json',
    'bass/breath3-period', 'bass/breath3-tracks'],

  async init(ctx) {
    const tl = ctx.timeline;
    this.sec = tl.byId('breath3');
    const root = tree(ctx).nodes[0];
    this.E = [root.x, root.y];
    // the harp's notes of the breath, each its 'across' plane's loop run from the start to the end of the
    // scene's drawing (refrain 3's ink transition)
    const meta = ctx.data.get('physics/pluck-harp-notes.json'), exc = ctx.data.get('physics/pluck-harp').values;
    const until = this.sec.t1 + 2 * tl.barLength;
    const f0 = Math.min(...meta.notes.filter((n) => this.inBreath(n)).map((n) => n.f));
    this.strings = meta.notes.filter((n) => this.inBreath(n)).map((n) => {
      const pl = n.planes[0];
      const y = runPlane(pl, exc, Math.ceil((until - n.t) * SR) + 8);
      const P = Math.round(SR / pl.f);
      const u = clamp((n.p - PITCH[0]) / (PITCH[1] - PITCH[0]));
      const a = mix(ANGLE[0], ANGLE[1], u) * DEG;
      // its swing at the pluck, for the drawing's scale as it rings
      const probe = new Float32Array(M), work = new Float64Array(P);
      shapeAt(y, Math.min(3 * P, y.length - 1), P, probe, work);
      let peak = 1e-9;
      for (const v of probe) peak = Math.max(peak, Math.abs(v));
      return { n, t: n.t + pl.lag / SR, y, P, peak, dir: [Math.cos(a), Math.sin(a)], len: LONGEST * (f0 / pl.f) ** 0.3 };
    });
    this.work = new Float64Array(4096);
    this.buf = new Float32Array(M);
    this.H = new Helmholtz(ctx, ctx.data.get('bass/breath3-period'), ctx.data.get('bass/breath3-tracks'), { t0: this.sec.t0, beats: 2 });
    this.sh = new Float32Array(this.H.NP);
    const b = BASS.angle * DEG;
    this.bassDir = [Math.cos(b), Math.sin(b)];
  },

  inBreath(n) { return n.t >= this.sec.t0 - 0.05 && n.t < this.sec.t1 - 0.05; },

  // the stage warms as the strings light, from the first pluck to the breath's end
  light(ctx, t) {
    const first = this.strings ? this.strings[0].t : this.sec.t0;
    return LAMP * ease.inOutSine(clamp((t - first) / (this.sec.t1 - first)));
  },

  render(ctx, t, target) {
    const tl = ctx.timeline, k = ctx.k(t), ink = ctx.palette.inks(k), b = tl.beatLength;
    const { t0, t1 } = this.sec;
    ground(ctx, t, target, k);
    const E = this.E;

    // the harp's strings, from the ember
    for (const s of this.strings) {
      if (t < s.t) continue;
      const age = t - s.t;
      const grow = ease.outCubic(clamp(age / 0.14));
      const n = Math.floor((age * SR) / s.P) * s.P + Math.floor((((age / b) % 1) * s.P));   // a period in slow motion
      const sh = shapeAt(s.y, Math.min(n, s.y.length - 1), s.P, this.buf, this.work);
      let now = 1e-9;
      for (let i = 0; i < M; i++) now = Math.max(now, Math.abs(sh[i]));
      const ring = n < s.y.length - 1 ? Math.min(now / s.peak, 1) : 0;
      // the ring drawn compressed (amplitude to the 0.4 power) so a string stays visible as it rings
      const sc = (SWING * Math.min(s.n.v, 1) * ring ** 0.4) / now;
      const L = s.len * grow, nx = -s.dir[1], ny = s.dir[0];
      const pts = [];
      for (let i = 0; i < M; i++) {
        const u = i / (M - 1), d = sh[i] * sc * grow;
        pts.push([E[0] + s.dir[0] * L * u + nx * d, E[1] + s.dir[1] * L * u + ny * d]);
      }
      const lit = 0.45 + 0.55 * ring ** 0.5;
      ctx.g.stroke(target, pts, { width: 1.6, color: ink.sung, alpha: lit, intensity: mix(1.05, 1.6, ring) });
    }

    // the bowed bass beneath: out of the strand at rest over the first beat, back to it over the last
    const pull = smoothstep(t0, t0 + b, t) * (1 - smoothstep(t1 - b, t1, t));
    const H = this.H, cur = H.shapeAt(t, this.sh), NP = H.NP;
    const g = BASS.scale * Math.sqrt(tl.gain('bowedbass', t));
    const rest = strandPoints(ctx, t, { y: 540 }).points;
    const along = (u, d) => {   // u 0 the bridge (the far end) .. 1 the nut (the ember)
      const L = BASS.length * (1 - u);
      return [E[0] + this.bassDir[0] * L - this.bassDir[1] * d, E[1] + this.bassDir[1] * L + this.bassDir[0] * d];
    };
    if (pull > 0.002) {
      for (let q = 0; q < H.S; q++) {
        const d = H.snap(cur.f, q), pts = [];
        for (let i = 0; i < M; i++) { const u = i / (M - 1); pts.push(along(u, -H.at(d, u * (NP - 1)) * g)); }
        ctx.g.stroke(target, pts, { width: 0.8, color: ink.ink, alpha: 0.34 * pull });
      }
    }
    {
      const n = rest.length, pts = [];
      for (let i = 0; i < n; i++) {
        // the strand's point i (left to right) to the string's place: the nut at the ember, the bridge far right
        const u = 1 - i / (n - 1), q = along(u, -H.at(cur.out, u * (NP - 1)) * g), r = rest[i];
        pts.push([mix(r[0], q[0], pull), mix(r[1], q[1], pull)]);
      }
      ctx.g.stroke(target, pts, { width: mix(2.5, 2.2, pull), color: ctx.palette.mix(ink.cold, ink.ink, pull), alpha: mix(0.5, 1, pull) });
      if (pull > 0.002) {
        const c = along(cur.xc, -H.at(cur.out, cur.xc * (NP - 1)) * g);
        ctx.g.points(target, [{ x: c[0], y: c[1], r: 4.5, color: ink.ink, alpha: pull }]);
      }
    }

    // the ember: the root of the bridge's tree, glowing with the song's level, as s08_lineage leaves it
    const e = clamp((ctx.data.get('s08/mix-bands').at(t)[0] + 40) / 30);
    ctx.g.points(target, [{ x: E[0], y: E[1], r: 6.2, color: ink.red, alpha: 1, intensity: 1.6 + 1.4 * e, soft: 1 }]);
    // the daisy, full grown, just visible by it and more as the light warms
    ctx.daisy.daisy(ctx, target, { ...DAISY, growth: 4, k, alpha: mix(0.34, 0.6, k / LAMP) });

    label(ctx, t, target, 'harp', { alpha: smoothstep(t0 + 0.5 * b, t0 + 1.5 * b, t) * (1 - smoothstep(t1 - b, t1, t)), k });
    lyric(ctx, t, target, { k });
  },

  // the strand where s09_broadside takes it: the rest line
  anchor(ctx, t) {
    return { points: strandPoints(ctx, t, { y: 540 }).points, width: 2.5, color: ctx.palette.inks(ctx.k(t)).cold };
  },
};
