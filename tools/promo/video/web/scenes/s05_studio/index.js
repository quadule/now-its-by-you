// The studio: verse 2. A cut on the downbeat into a dark room: a wall of screens, every one the studio's Page of the
// stage version, standing on the horizon; over "a million bright faces" the rest of the room lights up, receding to
// the vanishing point; they scroll together and diverge into what the studio does while the camera travels along
// them; they go out like a room emptying, the last on "gone", leaving the strand alone in the black.
//
// The screens are real captures of the studio opened on the stage version (renders/promo/video/studio/, made by
// capture/studio_stills.mjs; index.json lists them). One instanced draw places every screen in the world through
// the scene's camera, sampling an sRGB texture array (mipmapped, anisotropic) and the tall Page for scrolling.
import { lyric, strand } from '../../core/draw.js';
import { Camera } from '../../core/camera.js';
import { clamp, mix, smoothstep, smootherstep, ease } from '../../core/math.js';
import { Wall } from './wall.js';

// the room: two walls of screens facing each other across a corridor; the camera stands in it
const HALF = 30;          // the corridor's half width (world units; a screen is 16 x 9)
const PITCH_Z = 18;       // a column's pitch along a wall
const PITCH_Y = 10.5;     // a row's pitch up a wall
const ROWS = [-6, 0];     // rows from the top (y up is negative) to the row standing on the floor line
const COLS = [-8, 240];   // columns along z
const EYE = 4.5;          // the camera's height below row 0's centre: the walls' foot, so every screen stands on the horizon
const HORIZON = 790;      // the horizon's height in the frame (the lyric sits below it)
const FOV = 35;

// the views the screens diverge into, those captured (the wall's pattern of views repeats as many columns apart)
const DIVERGE = ['arrange', 'mix', 'sing', 'time', 'style', 'notes', 'export', 'arrange-section', 'piano', 'tools',
  'cell', 'new', 'singer', 'help', 'key', 'sing-offer'];
// the three screens the camera stops at on line 3, side by side on the left wall's lowest row, and their views
const HOLDS = [{ c: 1, view: 'arrange' }, { c: 2, view: 'notes' }, { c: 3, view: 'mix' }];
const SLIDE = 0.45;       // seconds a screen's own view takes to scroll up into it (the wall's uSlide)
const HOLD_D = 22;        // the distance a held screen is read from: 700 units tall, a texel at most a pixel
const LIT_COLS = 14;      // the columns of the left wall lit from the cut (the wall in sight on line 1)

let S = null;

function times(ctx) {
  const tl = ctx.timeline, B = tl.beatLength;
  const L = [0, 1, 2, 3].map((i) => tl.lineOf('verse2', i));
  const word = (l, text) => l.words.find((w) => w.text.replace(/[^a-z]/gi, '').toLowerCase() === text);
  const sec = tl.byId('verse2');
  return {
    B, L, t0: sec.t0, t1: sec.t1,
    watching: word(L[0], 'watching').t0, day: word(L[0], 'day').t1,
    million: word(L[1], 'million').t0, lit: word(L[1], 'lit').t0, same: word(L[1], 'same').t0,
    laughed: word(L[2], 'laughed').t0, wept: word(L[2], 'wept').t0, scrolled: word(L[2], 'scrolled').t0,
    on2: L[2].words[L[2].words.length - 1].t1,
    was: word(L[3], 'was').t0, then: word(L[3], 'then').t0,
    gone: tl.syllables.find((y) => y.line === L[3] && y.text.replace(/[^a-z]/gi, '').toLowerCase() === 'gone').t0,
    // the beats of line 3, from its first downbeat: beat(i)
    beat: ((i0) => (i) => tl.beats[i0 + i])(tl.beats.findIndex((b) => b >= L[2].t0)),
  };
}

// The camera at t: poses held between keys, each move eased to rest. Line 1 stands in the corridor facing the left
// wall a little down its length and drifts in toward the first screen; then the corridor, three holds square-on to a
// screen on the beat, and the wide room as it empties. The eye is at the height of the walls' foot, so every screen
// stands on the horizon, which the strand runs just below.
function pose(T, t) {
  const keys = S.keys;
  let i = 0;
  while (i < keys.length - 1 && t >= keys[i + 1][0]) i++;
  const [ta, A] = keys[i], [tb, B] = keys[Math.min(i + 1, keys.length - 1)];
  const k = tb > ta ? smootherstep(ta, tb, t) : 1;
  return { p: A.p.map((v, j) => mix(v, B.p[j], k)), yaw: mix(A.yaw, B.yaw, k), cy: mix(A.cy, B.cy, k) };
}

// a pose d units from the first screen, looking along yaw (degrees; -90 square-on to the left wall)
function facing(d, yaw) {
  const dir = [Math.sin((yaw * Math.PI) / 180), 0, Math.cos((yaw * Math.PI) / 180)];
  return { p: [S.hero[0] - dir[0] * d, EYE, S.hero[2] - dir[2] * d], yaw, cy: HORIZON };
}

function keysOf(T) {
  const at = (c) => ({ p: [-HALF + HOLD_D, EYE, c * PITCH_Z], yaw: -90, cy: HORIZON });
  const drift = (P, dz) => ({ ...P, p: [P.p[0], P.p[1], P.p[2] + dz] });
  const end = facing(34, -62);
  const H = HOLDS.map((h) => at(h.c));
  // the room as it empties: backed away from the last held screen across the corridor, still looking at it, a turn
  // slow enough that the nearest screen moves under 12 px in a frame's open shutter
  const back = [HALF - 6, H[2].p[2] - 42];
  const wide = { p: [back[0], EYE, back[1]], yaw: (Math.atan2(-HALF - back[0], H[2].p[2] - back[1]) * 180) / Math.PI, cy: HORIZON };
  return [
    [T.t0, facing(42, -68)], [T.day, end],
    [T.lit, { p: [0, EYE, -48], yaw: 0, cy: HORIZON }],
    [T.beat(-1), { p: [0, EYE, -34], yaw: 0, cy: HORIZON }],
    [T.beat(1), H[0]], [T.beat(3), H[0]],
    [T.beat(4), H[1]], [T.beat(6), H[1]],
    [T.beat(7), H[2]], [T.beat(9), H[2]],
    [T.gone - T.B, wide], [T.t1, drift(wide, -3)],
  ];
}

function cameraAt(ctx, T, t) {
  const { p, yaw, cy } = pose(T, t);
  const dir = [Math.sin((yaw * Math.PI) / 180), 0, Math.cos((yaw * Math.PI) / 180)];
  return new Camera({ position: p, target: [p[0] + dir[0], p[1], p[2] + dir[2]], fov: FOV, size: ctx.size,
    center: [ctx.size.w / 2, cy] });
}

// The strand, drawn in front of the screens: at rest (y 540, 9 units a semitone) on the cut; within the first beat
// down to the floor line the screens stand on (2.5 a semitone, clear of their
// edges and of the lyric); as the room empties back up to rest, there by the last two beats (where the next
// scene's transition begins), above the last screens' tops.
function strandState(ctx, t, cam) {
  const T = S.T;
  const foot = cam.center[1] + 24;
  const settle = smoothstep(T.t0, T.t0 + T.B, t) * (1 - smoothstep(T.then, T.t1 - 2 * T.B, t));
  return { y: mix(540, foot, settle), semitone: mix(9, 2.5, settle), width: 2.5 };
}

// the dark band behind the lyric: full to `from`, gone by `to` (design px)
const SHADE = { from: 160, to: 300, band: 4, alpha: 1 };

export default {
  id: 's05_studio',
  section: 'verse2',
  enter: { kind: 'cut' },
  assets: [],

  async init(ctx) {
    const index = await ctx.data.json('/studio/index.json');
    const T = times(ctx);
    S = { T, hero: [-HALF, 0, 0] };
    S.keys = keysOf(T);
    const layers = DIVERGE.filter((n) => index.images.find((im) => im.file === `${n}.jpg`));
    S.wall = await Wall.create(ctx, { index, layers, tall: 'page-tall' });
    S.screens = layout(ctx, T, layers);
    S.wall.instances(S.screens);
  },

  // the room is dark: the screens are its light
  light() {
    return 0;
  },

  // the strand where it hands over: what render draws at t (core strandPoints with this y and semitone)
  anchor(ctx, t) {
    const st = strandState(ctx, t, cameraAt(ctx, S.T, t));
    const k = ctx.k(t);
    return { ...st, points: ctx.draw.strandPoints(ctx, t, { y: st.y, semitone: st.semitone }).points,
      color: ctx.palette.inks(k).cold, intensity: mix(1.35, 1, k) };
  },

  render(ctx, t, target) {
    const T = S.T;
    const k = ctx.k(t);
    const inks = ctx.palette.inks(k);
    // the ground: the stage, and black on the sung "gone"
    const black = smoothstep(T.L[3].t0, T.gone, t);
    const gnd = inks.ground.map((c) => c * (1 - black));
    ctx.g.clear(target, [gnd[0], gnd[1], gnd[2], 1]);
    ctx.g.ground = gnd;
    ctx.type.ground = gnd;

    const cam = cameraAt(ctx, T, t);
    // the scroll: two flicks on the beats before line 3, then each screen goes on into its own view
    // (both done before the first hold, so a held camera sees still pages)
    const flick = (t0) => ease.outCubic(clamp((t - t0) / (0.95 * T.B)));
    const scroll = flick(T.beat(-1)) * 0.45 + flick(T.beat(0)) * 0.55;
    S.wall.draw(target, cam, t, {
      scroll, slide: SLIDE, pageIn: 1, paper: inks.ground, match: 0, gain: 1.0, heroGain: 1.0,
    });

    const st = strandState(ctx, t, cam);
    strand(ctx, t, target, { y: st.y, width: st.width, semitone: st.semitone });

    // the room's dark over the screens' tops, where the sung line is set
    const shade = [];
    for (let y = 0; y < SHADE.to; y += SHADE.band) {
      shade.push({ x: 0, y, w: ctx.size.w, h: SHADE.band, color: gnd, alpha: SHADE.alpha * (1 - smoothstep(SHADE.from, SHADE.to, y + SHADE.band / 2)) });
    }
    ctx.g.rects(target, shade);
    lyric(ctx, t, target);
  },
};

// Every screen: its centre, which wall, its times (on, diverging, out) from the song's words, and its view.
// Views: a pattern over the wall (3 a column, 5 a row, 11 a wall, modulo 16) through a seeded shuffle, so no two
// neighbours (beside, above, diagonal) show the same view; the held screens are given theirs.
function layout(ctx, T, layers) {
  const rnd = ctx.prng('s05_studio');
  const N = layers.length;
  const cell = (side, r, c) => (((3 * c + 5 * r + (side > 0 ? 11 : 0)) % N) + N) % N;
  const P = layers.map((_, i) => i);
  for (let i = N - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [P[i], P[j]] = [P[j], P[i]]; }
  for (const h of HOLDS) {
    const want = layers.indexOf(h.view), slot = cell(-1, 0, h.c), from = P.indexOf(want);
    [P[slot], P[from]] = [P[from], P[slot]];
  }
  const B = T.B, list = [];
  for (const side of [-1, 1]) {
    for (let r = ROWS[0]; r <= ROWS[1]; r++) {
      for (let c = COLS[0]; c <= COLS[1]; c++) {
        const x = side * HALF, y = r * PITCH_Y, z = c * PITCH_Z;
        const hero = side < 0 && r === 0 && c === 0;
        const hold = side < 0 && r === 0 ? HOLDS.findIndex((h) => h.c === c) : -1;
        // the left wall's near columns lit from the cut; the rest of the room in a wave out from them over "a million
        // bright faces", every one on by "lit"
        const d = Math.hypot((side < 0 ? 0 : 2 * HALF), y, Math.max(z - LIT_COLS * PITCH_Z, 0));
        const wave = clamp(Math.log1p(d / 30) / Math.log1p(4400 / 30));
        const near = side < 0 && c >= COLS[0] && c <= LIT_COLS;
        const jitter = (rnd() - 0.5) * 0.4 * B;
        const on = near ? -1e9 : mix(T.million, T.lit, wave) + jitter;
        // diverging: only while the camera moves (a held camera sees still pages); a held screen just before the
        // camera comes to it
        const win = [[T.beat(0), T.beat(1) - SLIDE], [T.beat(3), T.beat(4) - SLIDE], [T.beat(6), T.beat(7) - SLIDE],
          [T.beat(9), T.beat(9) + 4 * B]][Math.floor(rnd() * 4)];
        let sw = mix(win[0], win[1], rnd());
        if (hold >= 0) sw = [T.beat(0) + 0.2 * B, T.beat(3), T.beat(6)][hold];
        // out: a room emptying, most early in the line and fewer after; the last held screen on "gone"
        const u = rnd();
        let off = mix(T.L[3].t0 + 0.3 * B, T.was - B, Math.pow(u, 1.7)) + (rnd() - 0.5) * 0.3 * B;
        let fall = 0.12;
        if (hold === 2) { off = T.gone - 0.05; fall = 0.03; }
        list.push({ x, y, z, side, on, sw, off, fall, layer: P[cell(side, r, c)], hero, seed: rnd() });
      }
    }
  }
  // a few stay to "was", in sight of the wide room
  const keep = list.filter((s) => s.side < 0 && s.y === 0 && s.z > 80 && s.z < 400 && s.off < T.gone).filter((s, i) => i % 4 === 1).slice(0, 4);
  keep.forEach((s, i) => { s.off = mix(T.then, T.was - 0.3 * B, i / 3); });
  return list;
}
