// Turn 1: the lute quoting the tune, over the guitar's strumming hand.
// The lute's courses are paired strings, each pair re-run from its captured pluck (physics/pluck-lute-notes.json and
// its .bin: four planes a note, two strings `cents` apart, the second plucked `lag` samples after the first). One
// course for each pitch it plays here, low to high from the top, each running from the bridge (right) off the frame's
// left edge; the part that rings runs from the bridge to the finger, its length the string's period, the longest
// period the whole speaking length. The highest course lies on the strand: on the cut the strand doubles into it,
// and two beats before verse 2 it closes back to the strand at rest.
// Under them the guitar's six strings and the strumming hand's strokes, drawn by s03_instruments' own code, quieter.
import { ground, lyric, label, strandPoints } from '../../core/draw.js';
import { smoothstep, mix } from '../../core/math.js';
import { Camera } from '../../core/camera.js';
import s03 from '../s03_instruments/index.js';
import { Plucks, strobeSample } from '../s03_instruments/pluck.js';

// the strobe: each string's phase turns this many times slower than the string (its ring decays in real time)
const RATE = 200;
// displacement drawn per unit of the model's bridge-force sum
const AMP = 12;
// the snapshots of one period drawn behind each sounding string
const LENS = 12;
// points along a string's speaking length
const COUNT = 112;
const FOV = 30, FOCAL = 540 / Math.tan((FOV * Math.PI) / 360);

const LUTE = {
  bridge: 1730,       // x of the bridge
  speak: 1480,        // the longest period's speaking length
  y0: 540,            // the highest course (on the strand)
  step: 76,           // from one course to the next one lower in pitch, upward
  pair: 11,           // between a course's two strings
};
// the guitar under the lute: bridge at the left as in refrain 1, six strings `step` apart
const GUITAR = { a: [-120, 668, 0], b: [2080, 668, 0], step: [0, 21, 0], pick: 0.3, scale: 0.55, line: 0.6 };
const GUITAR_ALPHA = 0.5;

export default {
  id: 's03b_lute',
  section: 'turn1',
  enter: { kind: 'cut' },
  assets: [
    'physics/pluck-lute-notes.json', 'physics/pluck-lute',
    'physics/pluck-guitar-notes.json', 'physics/pluck-guitar', 'physics/strum.json',
  ],

  async init(ctx) {
    const d = ctx.data, tl = ctx.timeline, sec = tl.byId('turn1');
    this.sec = sec;
    this.lute = new Plucks(d.get('physics/pluck-lute-notes.json'), d.get('physics/pluck-lute'));
    // the courses: every pitch the lute plucks in the turn, high to low; speaking length in proportion to period
    const notes = this.lute.notes.filter((n) => n.t >= sec.t0 - tl.beatLength && n.t < sec.t1);
    const pitches = [...new Set(notes.map((n) => n.p))].sort((a, b) => b - a);
    const per = Object.fromEntries(pitches.map((p) => [p, this.lute.period(notes.find((n) => n.p === p))]));
    const pmax = Math.max(...Object.values(per));
    this.courses = pitches.map((p, i) => ({ p, i, len: per[p] / pmax, y: LUTE.y0 - i * LUTE.step }));

    // the guitar as refrain 1 draws it: s03_instruments' methods over this scene's own copy of its state
    const g = Object.create(s03);
    g.ctx = ctx;
    g.pl = { guitar: new Plucks(d.get('physics/pluck-guitar-notes.json'), d.get('physics/pluck-guitar')) };
    g.strokes = d.get('physics/strum.json').strokes;
    g.arpEnd = -1;
    const stringOf = new Map();
    for (const s of g.strokes) for (const q of s.strings) {
      if (q.string === undefined || q.string === null) continue;
      stringOf.set(`${(s.t + q.dt).toFixed(3)}:${q.p}`, q.string);
    }
    for (const n of g.pl.guitar.notes) {
      const key = (dt) => `${(n.t + dt).toFixed(3)}:${n.p}`;
      n.string = stringOf.get(key(0)) ?? stringOf.get(key(0.001)) ?? stringOf.get(key(-0.001)) ?? null;
    }
    this.guitar = g;
    this.out = new Float32Array(COUNT);
  },

  // a frontal camera a little above the strings, as refrain 1's (the strand's line y 540 projects to itself)
  camera(ctx, t) {
    const drift = (t - this.sec.t0) / ctx.timeline.barLength;
    const dx = 8 * drift;
    return new Camera({ position: [960 + dx, 540 - 0.12 * FOCAL, FOCAL], target: [960 + dx * 0.4, 540, 0], fov: FOV, size: ctx.size });
  },

  // One string of a course at t: its shown shape (planes across, along) and its LENS snapshots over the period it is
  // in now, summed over the course's sounding notes; COUNT points from the bridge. string 0 or 1 of the pair.
  // e: the largest displacement; flash: how freshly it was plucked; pick: where (fraction from the bridge).
  motion(course, string, t) {
    const L = this.lute;
    const notes = L.between(t, t).filter((n) => n.t <= t && n.p === course.p);
    const cur = [new Float32Array(COUNT), new Float32Array(COUNT)];
    const lens = [];
    let e = 0, flash = 0, live = 0, pick = 0, fresh = -1;
    for (const n of notes) {
      const k0 = n.planes.findIndex((q) => q.string === string);
      const p0 = n.planes[k0];
      const s = strobeSample(n, t, L.sr, p0.f, RATE);
      if (s < p0.lag || s >= n.len) continue;
      live++;
      const age = t - n.t - p0.lag / L.sr;
      if (fresh < 0 || age < fresh) { fresh = age; pick = n.pick; }
      flash = Math.max(flash, Math.exp(-age / 0.12));
      const per = L.sr / p0.f, start = Math.floor((s - p0.lag) / per) * per + p0.lag;
      for (let k = 0; k < 2; k++) {
        const a = L.shape(n, k0 + k, s, COUNT, this.out);
        for (let c = 0; c < COUNT; c++) cur[k][c] += a[c] * AMP;
      }
      for (let q = 0; q < LENS; q++) {
        if (!lens[q]) lens[q] = [new Float32Array(COUNT), new Float32Array(COUNT)];
        const sq = Math.min(start + (q / LENS) * per, n.len - 1);
        for (let k = 0; k < 2; k++) {
          const a = L.shape(n, k0 + k, sq, COUNT, this.out);
          for (let c = 0; c < COUNT; c++) lens[q][k][c] += a[c] * AMP;
        }
      }
    }
    for (let c = 0; c < COUNT; c++) e = Math.max(e, Math.hypot(cur[0][c], cur[1][c]));
    return { cur, lens: live ? lens : [], e, flash, live, pick, fresh };
  },

  // A course's string from the frame's left edge to the bridge, at height y, as screen points: still beyond the
  // finger, moving by d (across: up the frame; along: toward the camera) between the finger and the bridge.
  // rest (screen points across the frame) and pull blend it out of the strand.
  path(cam, course, y, d, rest, pull) {
    const B = LUTE.bridge, Ls = LUTE.speak * course.len, finger = B - Ls;
    const pts = [];
    // off the strand a course is tied at the bridge
    const n = rest ? rest.length : 160;
    for (let c = 0; c < n; c++) {
      const x = rest ? rest[c][0] : -40 + ((B + 40) * c) / (n - 1);
      let dy = 0, dz = 0;
      if (d && x > finger && x < B) {
        const u = ((B - x) / Ls) * (COUNT - 1), i = Math.floor(u), f = u - i, j = Math.min(i + 1, COUNT - 1);
        dy = d[0][i] + (d[0][j] - d[0][i]) * f;
        dz = d[1][i] + (d[1][j] - d[1][i]) * f;
      }
      const q = cam.project([x, y - dy, dz]);
      pts.push(rest ? [mix(rest[c][0], q.x, pull), mix(rest[c][1], q.y, pull)] : [q.x, q.y]);
    }
    return pts;
  },

  // rest: the strand's points when this course lies on it (pull 0: the strand as refrain 1 leaves it; late: as
  // core/draw.js strand draws it, fading behind now and dim ahead, for the next scene)
  courseDraw(ctx, t, target, cam, ink, course, alpha, rest, pull, late = 0) {
    if (alpha <= 0.002) return;
    const lit = lineInk(ctx, ink), glow = mix(1, 0, ink.side);
    const marks = [];
    let strandAlpha = null;
    if (rest) {
      const n = rest.length, nowX = rest.nowX, nowI = rest.findIndex((p) => p[0] >= nowX);
      strandAlpha = (i) => mix(1, i <= nowI ? smoothstep(0, nowI * 0.6, i) : 0.28 * (1 - (i - nowI) / Math.max(n - nowI, 1)), late);
    }
    for (let s = 0; s < 2; s++) {
      const m = this.motion(course, s, t);
      const y = course.y + (s === 0 ? -0.5 : 0.5) * LUTE.pair * pull;
      // on the strand the pair is one line: the second string comes apart from it
      const a = rest && s === 1 ? alpha * smoothstep(0, 0.4, pull) : alpha;
      if (a <= 0.002) continue;
      const on = m.live ? 1 : 0, e = Math.min(m.e / 30, 1);
      let col = on ? lit : ctx.palette.mix(lit, ink.ink2, 0.35);
      if (rest) col = ctx.palette.mix(ink.cold, col, pull);
      for (const d of m.lens) {
        ctx.g.stroke(target, this.path(cam, course, y, d, rest, pull), { width: 0.8, color: col,
          alpha: a * (0.08 + 0.22 * e), intensity: 1 + 0.5 * e * glow });
      }
      const w = on ? 2.1 * (1 + 0.4 * m.flash) : 1.7;
      ctx.g.stroke(target, this.path(cam, course, y, on ? m.cur : null, rest, pull), {
        width: rest ? mix(2.5, w, pull) : w, color: col,
        alpha: strandAlpha && s === 0 ? (i) => a * strandAlpha(i) : a,
        intensity: on ? 1 + (0.9 * e + 1.2 * m.flash) * glow : mix(1.35, 1, ink.side),
      });
      // the finger stopping the course, and the plucking finger's place for the first moments
      if (on) {
        const f = cam.project([LUTE.bridge - LUTE.speak * course.len, y, 0]);
        marks.push({ x: f.x, y: f.y, r: 3.2, color: ink.ink, alpha: alpha * pull });
        const pa = alpha * (1 - smoothstep(0.01, 0.06, m.fresh));
        if (pa > 0.01 && s === 0) {
          const p = cam.project([LUTE.bridge - LUTE.speak * course.len * m.pick, course.y, 0]);
          marks.push({ x: p.x, y: p.y, r: 4.5, color: ink.red, alpha: pa });
        }
      }
    }
    ctx.g.points(target, marks);
  },

  // the bridge the courses are tied to: a short rule across them
  bridgeDraw(ctx, target, cam, ink, alpha) {
    if (alpha <= 0.002) return;
    const top = this.courses.at(-1).y - LUTE.step * 0.35, foot = LUTE.y0 + LUTE.step * 0.35;
    const q = [[LUTE.bridge, top, 0], [LUTE.bridge, foot, 0]].map((p) => cam.project(p));
    ctx.g.stroke(target, q.map((p) => [p.x, p.y]), { width: 3, color: ink.ink, alpha });
  },

  render(ctx, t, target) {
    const k = ctx.k(t), ink = ctx.palette.inks(k);
    ground(ctx, t, target);
    const beat = ctx.timeline.beatLength, t0 = this.sec.t0, t1 = this.sec.t1;
    // out of the strand over the first beat; back to it at rest by two beats before verse 2 (the next scene's ink)
    const pullIn = smoothstep(t0, t0 + beat, t), late = smoothstep(t1 - 4 * beat, t1 - 2 * beat, t);
    const pull = pullIn * (1 - late);
    const cam = this.camera(ctx, t);

    // the guitar under the lute, quieter
    this.guitar.guitarDraw(ctx, t, target, cam, ink, GUITAR_ALPHA * pullIn, GUITAR);

    const st = strandPoints(ctx, t, { y: 540 }), rest = st.points;
    rest.nowX = st.nowX;
    // the other courses stay to the cut: the last note rings on the lowest through the next scene's ink
    this.bridgeDraw(ctx, target, cam, ink, smoothstep(0.15, 1, pullIn));
    for (const c of this.courses) {
      if (c.i === 0) this.courseDraw(ctx, t, target, cam, ink, c, 1, rest, pull, late);
      else this.courseDraw(ctx, t, target, cam, ink, c, smoothstep(0.15, 1, pullIn), null, 1);
    }

    label(ctx, t, target, 'lute', { alpha: smoothstep(t0, t0 + beat, t) * (1 - smoothstep(t1 - 3 * beat, t1 - 2 * beat, t)) });
    // refrain 1's last line as it set it, its turning word apart, while it fades
    lyric(ctx, t, target, { focus: t < t0 + 2 * beat ? 'italic' : null });
  },

  // the strand where it hands over: at rest at both ends of the turn (core strandPoints, y 540, 9 a semitone)
  anchor(ctx, t) {
    const k = ctx.k(t);
    return { y: 540, semitone: 9, width: 2.5, points: strandPoints(ctx, t, { y: 540 }).points,
      color: ctx.palette.inks(k).cold, intensity: mix(1.35, 1, k) };
  },
};

// a sounding string's ink: amber light on the stage, print on paper
function lineInk(ctx, ink) { return ctx.palette.mix(ctx.palette.lin.sung, ink.ink, ink.side); }
