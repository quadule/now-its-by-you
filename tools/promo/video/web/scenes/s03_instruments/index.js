// Refrain 1: the instruments as their physics. Each player comes in on its line as the synth it takes over from
// goes out, and each string and the skin are the models' own shapes re-run from captured parameters.
//   line 1  the harp's strings standing on the bass string (the strand becomes the bass string)
//   line 2  the guitar's six strings and the strumming hand's strokes
//   line 3  the frame drum's skin, an engraving moving by its 196 modes; the light comes up onto paper
//   line 4  the four as one plate standing on the bass string, the sung "now it's by you" underlined
// One picture a line; the pictures dissolve into each other over the beat that spans each line change.
// World units are the frame's design units at depth 0 (the camera stands at the focal distance).
import { ground, lyric, label, strandPoints } from '../../core/draw.js';
import { smoothstep, mix, clamp } from '../../core/math.js';
import { Camera } from '../../core/camera.js';
import { Plucks, strobeSample } from './pluck.js';
import { Skin, drawSkin } from './skin.js';

const PARTS = ['harp', 'bass', 'guitar'];
// the strobe: each string's phase turns this many times slower than the string (its ring decays in real time)
export const RATE = { harp: 400, bass: 100, guitar: 160 };
// the drum: the first moments after each hit are shown this many times slower (skin.js)
export const DRUM_RATE = 40;
// displacement drawn per unit of the model's bridge-force sum, per unit of the string's drawn scale
const AMP = { harp: 20, bass: 0.85, guitar: 5 };
// a synth's sample drawn as this many units of displacement
const TWIN = { bass: 520, guitar: 160, drum: 9 };
// the snapshots of one period drawn behind each sounding string: the lens its corner sweeps
const LENS = 16;
export const FOV = 30, FOCAL = 540 / Math.tan((FOV * Math.PI) / 360);

// the pictures, one per line
const P1 = {
  harp: { xLong: 1560, xShort: 500, foot: 770, height: 700, scale: 1 },
  bass: { y: 795 },
};
const P2 = {
  // string 0 (low E) from its bridge end (near, left) to its far end; each next string `step` lower
  guitar: { a: [-120, 350, 120], b: [2080, 390, -420], step: [0, 72, 0], pick: 0.33, scale: 1.2 },
};
export const P3 = { drum: { c: [960, 385, 0], R: 545, tilt: 0.98, scale: 1.45 } };
const P4 = {
  // each on its own ground, left to right, none crossing another: harp, guitar, drum; the bass under them all
  harp: { xLong: 130, xShort: 500, foot: 740, height: 470, scale: 0.7 },
  guitar: { a: [600, 560, 0], b: [1200, 590, 0], step: [0, 22, 0], pick: 0.3, scale: 0.5, line: 0.55 },
  drum: { c: [1560, 585, 0], R: 270, tilt: 0.98, scale: 0.8 },
  bass: { y: 838, amp: 0.32 },
};

export default {
  id: 's03_instruments',
  section: 'refrain1',
  enter: { kind: 'dissolve', beats: 2 },
  assets: [
    ...PARTS.flatMap((p) => [`physics/pluck-${p}-notes.json`, `physics/pluck-${p}`]),
    'physics/strum.json', 'physics/drum.json', 'physics/drum-modes',
    's03/twin-synthbass', 's03/twin-arp', 's03/twin-drummachine',
  ],

  async init(ctx) {
    const d = ctx.data, sec = ctx.timeline.byId('refrain1');
    this.ctx = ctx;
    this.sec = sec;
    this.lines = [0, 1, 2, 3].map((i) => ctx.timeline.lineOf('refrain1', i));
    // each picture comes in over the beat before the first bar line after its line starts
    this.cuts = [1, 2, 3].map((i) => ctx.timeline.bars.find((b) => b > this.lines[i].t0));
    this.pl = {};
    for (const p of PARTS) this.pl[p] = new Plucks(d.get(`physics/pluck-${p}-notes.json`), d.get(`physics/pluck-${p}`));
    // the harp's strings: every pitch it plucks in the refrain, low to high; a string's length is its period
    const harpNotes = this.pl.harp.notes.filter((n) => n.t >= sec.t0 - ctx.timeline.beatLength && n.t < sec.t1);
    const pitches = [...new Set(harpNotes.map((n) => n.p))].sort((a, b) => a - b);
    const per = Object.fromEntries(pitches.map((p) => [p, harpNotes.find((n) => n.p === p)]));
    const pmax = Math.max(...pitches.map((p) => this.pl.harp.period(per[p])));
    this.harp = pitches.map((p, i) => ({ p, len: this.pl.harp.period(per[p]) / pmax, i, n: pitches.length }));
    // the guitar: each note's string (0 low E .. 5) from the strumming hand's strokes
    this.strokes = d.get('physics/strum.json').strokes;
    const stringOf = new Map();
    for (const s of this.strokes) for (const q of s.strings) {
      if (q.string === undefined || q.string === null) continue;
      stringOf.set(`${(s.t + q.dt).toFixed(3)}:${q.p}`, q.string);
    }
    for (const n of this.pl.guitar.notes) {
      const key = (dt) => `${(n.t + dt).toFixed(3)}:${n.p}`;
      n.string = stringOf.get(key(0)) ?? stringOf.get(key(0.001)) ?? stringOf.get(key(-0.001)) ?? null;
    }
    this.skin = new Skin(d.get('physics/drum.json'), d.get('physics/drum-modes'), { rate: DRUM_RATE });
    const lv = ctx.timeline.levels;
    const off = (part, i) => (lv[part] || []).find((q) => q[0] > this.lines[i].t0 - 1 && q[1] === null)?.[0] ?? -1;
    this.arpEnd = off('arp', 1);
    this.dmEnd = off('drummachine', 2);
  },

  // how much of picture i (0..3) is drawn at t
  weights(ctx, t) {
    const beat = ctx.timeline.beatLength;
    const s = this.cuts.map((c) => smoothstep(c - beat, c, t));
    return [1 - s[0], s[0] * (1 - s[1]), s[1] * (1 - s[2]), s[2]];
  },

  // a frontal camera on the frame, drifting a little each bar
  camera(ctx, t, i) {
    const bar = ctx.timeline.barLength, drift = (t - this.sec.t0) / bar;
    const dx = [-60, 40, -30, 0][i] + [14, -12, 10, 6][i] * drift;
    return new Camera({ position: [960 + dx, 540 - 0.12 * FOCAL, FOCAL], target: [960 + dx * 0.4, 540, 0], fov: FOV, size: ctx.size });
  },

  // N samples of a synth's stem (s03/twin-<name>, prep/s03_twins.py) ending at or before t, starting at the latest
  // rising zero crossing that leaves room for them: an oscilloscope's trigger, so a steady wave stands still
  twin(name, t, N, out = new Float32Array(N)) {
    const a = this.ctx.data.get(`s03/twin-${name}`), x = a.values;
    const end = Math.floor((t - a.t0) * a.rate);
    if (end - N < 1 || end >= x.length) { out.fill(0); return out; }
    let s = end - N;
    for (let i = end - N; i > Math.max(end - N - 4096, 1); i--) if (x[i - 1] < 0 && x[i] >= 0) { s = i; break; }
    for (let i = 0; i < N; i++) out[i] = x[s + i];
    return out;
  },

  // A string's motion at t from a part's notes (filter picks the string's): its shown shape in both planes, and its
  // LENS snapshots spread over the period it is in now, summed over its sounding notes; count points from the bridge.
  // e: the largest displacement; flash: how freshly the string was met (1 at a note's start, fading in 0.15 s).
  motion(part, t, count, filter = null, amp = 1) {
    const P = this.pl[part];
    const notes = P.between(t, t).filter((n) => n.t <= t && (!filter || filter(n)));
    const cur = [new Float32Array(count), new Float32Array(count)];
    const lens = [];
    let e = 0, flash = 0, live = 0;
    for (const n of notes) {
      const s = strobeSample(n, t, P.sr, n.planes[0].f, RATE[part]);
      if (s < 0 || s >= n.len) continue;
      live++;
      flash = Math.max(flash, Math.exp(-(t - n.t) / 0.15));
      const per = P.sr / n.planes[0].f, start = Math.floor((s / per) | 0) * per;
      for (let k = 0; k < 2; k++) {
        const a = P.shape(n, k, s, count);
        for (let c = 0; c < count; c++) cur[k][c] += a[c] * AMP[part] * amp;
      }
      for (let q = 0; q < LENS; q++) {
        if (!lens[q]) lens[q] = [new Float32Array(count), new Float32Array(count)];
        const sq = Math.min(start + (q / LENS) * per, n.len - 1);
        for (let k = 0; k < 2; k++) {
          const a = P.shape(n, k, sq, count);
          for (let c = 0; c < count; c++) lens[q][k][c] += a[c] * AMP[part] * amp;
        }
      }
    }
    for (let c = 0; c < count; c++) e = Math.max(e, Math.hypot(cur[0][c], cur[1][c]));
    return { cur, lens: live ? lens : [], e, flash, live };
  },

  // A plucked string from world point a (its bridge) to b: its lens of snapshots faint behind, its shown shape bold.
  // Plane 0 moves along `across`, plane 1 along `along`. Resting, it is a fine lit line.
  string(ctx, target, cam, part, a, b, { t, count = 96, filter = null, ink, alpha = 1, width = 2.6, across, along,
    amp = 1, lightAt = 60, rest = 0.5 }) {
    if (alpha <= 0.002) return;
    const m = this.motion(part, t, count, filter, amp);
    const at = (d) => {
      const pts = [];
      for (let c = 0; c < count; c++) {
        const u = c / (count - 1);
        pts.push([0, 1, 2].map((q) => mix(a[q], b[q], u) + across[q] * d[0][c] + along[q] * d[1][c]));
      }
      return pts;
    };
    const lit = Math.min(m.e / lightAt, 1);
    const on = m.live ? 1 : 0;
    const col = on ? lineInk(ctx, ink) : ctx.palette.mix(lineInk(ctx, ink), ink.ink2, 0.4);
    const glow = mix(1, 0, ink.side);   // light only on the stage
    for (const d of m.lens) {
      strokeWorld(ctx, target, cam, at(d), { width: 0.9, color: col, alpha: alpha * (0.1 + 0.28 * lit),
        intensity: 1 + 0.6 * lit * glow });
    }
    strokeWorld(ctx, target, cam, at(m.cur), {
      width: on ? width * (1 + 0.5 * m.flash) : 1.1, color: col, alpha: alpha * (on ? 1 : rest),
      intensity: on ? 1 + (1.1 * lit + 1.4 * m.flash) * glow : mix(0.8, 1, ink.side),
    });
  },

  // the harp: its strings standing on a foot line, longest at xLong; a string's length its period
  harpDraw(ctx, t, target, cam, ink, alpha, H) {
    const n = this.harp.length;
    for (const s of this.harp) {
      const x = mix(H.xLong, H.xShort, (n - 1 - s.i) / (n - 1)), L = H.height * s.len;
      this.string(ctx, target, cam, 'harp', [x, H.foot, 0], [x, H.foot - L, 0], { t, filter: (q) => q.p === s.p, ink, alpha,
        across: [1, 0, 0], along: [0, 0, 1], count: 72, amp: H.scale, lightAt: 40 * H.scale });
    }
  },

  // the bass: one long string across the frame at height y, its bridge at the right; out of the strand's rest by pull
  bassDraw(ctx, t, target, ink, alpha, B, pull) {
    if (alpha <= 0.002) return;
    const rest = strandPoints(ctx, t, { y: 540 });
    const count = rest.points.length, w = ctx.size.w;
    const t0 = this.sec.t0, beat = ctx.timeline.beatLength;
    // the synth bass it takes over from: its own samples on the strand until it falls silent at the downbeat
    const tw = 1 - smoothstep(t0 - 0.25 * beat, t0, t);
    const wave = tw > 0 ? this.twin('synthbass', t, count * 4) : null;
    const m = this.motion('bass', t, count, null, B.amp ?? 1);
    const lit = Math.min(m.e / 70, 1), on = m.live ? pull : 0;
    const col = ctx.palette.mix(ink.cold, lineInk(ctx, ink), on), glow = mix(1, 0, ink.side);
    const line = (d, synth) => rest.points.map((r, c) => {
      const s = synth ? wave[c * 4] * TWIN.bass * tw : 0;
      return [mix(r[0], (c / (count - 1)) * w, pull), mix(r[1] - s, B.y - d[0][count - 1 - c], pull)];
    });
    for (const d of m.lens) ctx.g.stroke(target, line(d, false), { width: 0.9, color: col, alpha: alpha * pull * (0.1 + 0.26 * lit), intensity: 1 + 0.5 * lit * glow });
    ctx.g.stroke(target, line(m.cur, !!wave), { width: 2.5, color: col, alpha,
      intensity: mix(1.35, 1, ink.side) * (1 + (0.6 * lit + 0.8 * m.flash) * on * glow) });
  },

  guitarDraw(ctx, t, target, cam, ink, alpha, G) {
    if (alpha <= 0.002) return;
    const S = (s, u) => [0, 1, 2].map((q) => mix(G.a[q], G.b[q], u) + G.step[q] * s);
    for (let s = 0; s < 6; s++) {
      this.string(ctx, target, cam, 'guitar', S(s, 0), S(s, 1), { t, filter: (q) => q.string === s, ink, alpha,
        across: [0, 1, 0], along: [0, 0, 1], count: 128, amp: G.scale, lightAt: 40 * G.scale, width: 2.2 * (G.line ?? 1) });
    }
    // the arp it takes over from: its own samples along each string, until it stops
    const arpOn = this.arpEnd > 0 ? 1 - smoothstep(this.arpEnd, this.arpEnd + 0.25, t) : 0;
    if (arpOn > 0) {
      const n = 175, wave = this.twin('arp', t, n * 10);
      for (let s = 0; s < 6; s++) {
        const pts = [];
        for (let c = 0; c < n; c++) { const p = S(s, c / (n - 1)); p[1] -= wave[c * 10] * TWIN.guitar * G.scale; pts.push(p); }
        strokeWorld(ctx, target, cam, pts, { width: 1.3, color: ink.cold, intensity: mix(1.35, 1, ink.side), alpha: alpha * arpOn });
      }
    }
    // The strumming hand: each stroke the path of the pick, one fine line through the strings it met, at the pick's
    // place, leaning by the order and time it met them (DT_X world units a second), down and up leaning opposite
    // ways; its head a soft point where the pick is; heavier on accents. It drifts toward the neck as it fades.
    const DT_X = 2.6e3 * G.scale, DRIFT = 200 * G.scale, LIFE = 1.4;
    const heads = [];
    for (const st of this.strokes) {
      const age = t - st.t;
      if (age < 0 || age > LIFE || !st.kind) continue;
      const met = st.strings.filter((q) => q.string !== null && q.string !== undefined && q.dt <= age);
      if (!met.length) continue;
      const sgn = st.dir === 'up' ? -1 : 1;
      const P = (string, dt, extra = 0) => {
        const p = S(string, G.pick);
        p[0] += DRIFT * (age - dt) + sgn * DT_X * dt;
        p[1] += extra; p[2] += 30;
        return p;
      };
      // the path through the strings met, carried half a string's gap past the first (and the last, once met)
      const pts = met.map((q) => P(q.string, q.dt));
      const a0 = pts[0], a1 = pts.length > 1 ? pts[pts.length - 1] : P(met[0].string + (sgn > 0 ? 1 : -1), met[0].dt + 0.006);
      const span = Math.max(Math.abs(a1[1] - a0[1]), 1e-3), ext = (0.5 * G.step[1]) / span;
      const dir = [0, 1, 2].map((q) => a1[q] - a0[q]);
      pts.unshift([0, 1, 2].map((q) => a0[q] - dir[q] * ext));
      if (met.length === st.strings.length && met.length > 1) pts.push([0, 1, 2].map((q) => a1[q] + dir[q] * ext));
      const fade = (1 - smoothstep(0.25, LIFE, age)) * alpha;
      const w = (0.9 + 2.2 * (st.accent ?? 0.5)) * G.scale;
      strokeWorld(ctx, target, cam, pts, { width: w, color: ink.ink, alpha: fade * 0.85, intensity: mix(1.1, 1, ink.side) });
      const hq = cam.project(pts[pts.length - 1]);
      heads.push({ x: hq.x, y: hq.y, r: w * 1.6 * hq.scale, color: ink.ink, alpha: fade * 0.9, soft: (1 - ink.side) * 0.6 });
    }
    ctx.g.points(target, heads);
  },

  drumDraw(ctx, t, target, cam, ink, alpha, D) {
    if (alpha <= 0.002) return;
    // the drum machine it takes over from: its own samples as rings from the centre out, until it stops
    const dmOn = this.dmEnd > 0 ? 1 - smoothstep(this.dmEnd, this.dmEnd + 0.25, t) : 0;
    const add = dmOn > 0 ? (z, nr, na) => {
      const wave = this.twin('drummachine', t, nr * 24);
      for (let i = 0; i < nr; i++) for (let j = 0; j < na; j++) z[i * na + j] += wave[(nr - 1 - i) * 24] * TWIN.drum * dmOn;
    } : null;
    drawSkin(ctx, t, target, cam, this.skin, ink, alpha, D, { add });
  },

  render(ctx, t, target) {
    const k = ctx.k(t), ink = ctx.palette.inks(k);
    ground(ctx, t, target);
    const beat = ctx.timeline.beatLength, t0 = this.sec.t0, t1 = this.sec.t1;
    // the strand: out of rest over the first two beats, back to it over the last
    const pullIn = smoothstep(t0, t0 + 2 * beat, t), pullOut = 1 - smoothstep(t1 - beat, t1, t);
    const w = this.weights(ctx, t);
    // the plate dims as the title sets and is gone before the strand rises back to rest; the title stays to the cut
    const set = this.lines[3].words.at(-1).syllables.at(-1).t0;
    const plate = w[3] * (1 - smoothstep(Math.min(set - 0.1, t1 - 2 * beat), t1 - beat, t));

    if (w[0] > 0.002) {
      const cam = this.camera(ctx, t, 0);
      this.harpDraw(ctx, t, target, cam, ink, w[0] * pullIn, P1.harp);
      this.bassDraw(ctx, t, target, ink, w[0], P1.bass, pullIn);
    }
    if (w[1] > 0.002) this.guitarDraw(ctx, t, target, this.camera(ctx, t, 1), ink, w[1], P2.guitar);
    if (w[2] > 0.002) this.drumDraw(ctx, t, target, this.camera(ctx, t, 2), ink, w[2], P3.drum);
    if (w[3] > 0.002) {
      const cam = this.camera(ctx, t, 3);
      this.harpDraw(ctx, t, target, cam, ink, plate, P4.harp);
      this.drumDraw(ctx, t, target, cam, ink, plate, P4.drum);
      this.guitarDraw(ctx, t, target, cam, ink, plate, P4.guitar);
      this.bassDraw(ctx, t, target, ink, w[3], P4.bass, pullOut);
    }

    // labels with their pictures, never two crossing
    const la = (i) => smoothstep(0.6, 1, w[i]);
    label(ctx, t, target, 'harp', { alpha: la(0) * smoothstep(t0, t0 + beat, t) });
    label(ctx, t, target, 'bass', { y: 158, alpha: la(0) * smoothstep(t0 + beat, t0 + 2 * beat, t) });
    label(ctx, t, target, 'guitar', { alpha: la(1) });
    label(ctx, t, target, 'drum', { alpha: la(2) });
    lyric(ctx, t, target, { focus: 'italic' });
  },
};

// a sounding string's ink: amber light on the stage, print on paper
function lineInk(ctx, ink) { return ctx.palette.mix(ctx.palette.lin.sung, ink.ink, ink.side); }

function strokeWorld(ctx, target, cam, points, opts) {
  const q = points.map((p) => cam.project(p));
  ctx.g.stroke(target, q.map((p) => [p.x, p.y]), { ...opts, width: (i) => opts.width * q[i].scale });
}
