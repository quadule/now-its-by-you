// Writing. Black, then one point of cold light draws the strand. The intro's first phrase set as the genome
// writes it (scale degrees on an eighth-note grid); each digit lifts to its pitch as the lead plays it and the
// strand bends through the lifted notes. Then the bank's 51 verses as a drawer of cards, the verse about to be
// sung coming forward, and the drum machine's triggers on the strand.
import { ground, label, lyric, strandPoints } from '../../core/draw.js';
import { clamp, smoothstep, mix, ease } from '../../core/math.js';
import { buildBank, drawBank } from './bank.js';
import { buildRegister, drawRegister } from './register.js';
import { buildLayers, drawLayers } from './layers.js';
import { GRID, PART, setPhrase, cellX, liftY, lifted, gridX, gridHeight, traceOf, restPitch } from './tune.js';

const S = {};
const STEP = 1 / 60;
const FOOT = { from: 880, to: 960, band: 4 };   // the dark at the frame's foot under the bank's label: none at `from`, full by `to`   // the core strand's sampling of song time

// The strand at frame time t as points over song time s. The rest pose is the core's strandPoints exactly
// (extended by whole steps either side with the same rule); the grid places s in its eighth-note cell and
// raises each played note; wB blends the two (x and y), so the notes slide from the rest pose into their cells.
function strandAt(ctx, t) {
  const { T0, T2, T4, beat, eighth } = S;
  const core = strandPoints(ctx, t);
  const back = 4.5, ahead = 2.5, at = 0.62;
  const X = (s) => 1920 * (at + (s - t) / (back + ahead));
  const lead = ctx.score.lead(t);
  const notes = ctx.score.notes(lead.part);
  const tonic = ctx.timeline.tonic;
  const wIn = ease.inOutSine(clamp((t - T0) / beat));
  const flat = S.flatAt(t);
  const wOut = ease.inOutSine(clamp((t - (T4 - beat)) / beat));
  const wB = wIn * (1 - wOut);
  // song times whose grid x is on screen, as whole steps from the core's first sample
  const s0 = t - back;
  const gx0 = T0 + ((-40 - cellX(0)) / GRID.cell) * eighth, gx1 = T0 + ((1960 - cellX(0)) / GRID.cell) * eighth;
  const k0 = wB > 0 ? Math.min(0, Math.floor((gx0 - s0) / STEP)) : 0;
  const k1 = wB > 0 ? Math.max(core.points.length - 1, Math.ceil((gx1 - s0) / STEP)) : core.points.length - 1;
  const n = k1 - k0 + 1;
  const xr = new Float32Array(n), yr = new Float32Array(n), hb = new Float32Array(n), ss = new Float32Array(n);
  for (let k = k0; k <= k1; k++) {
    const i = k - k0, s = s0 + k * STEP;
    ss[i] = s;
    const c = core.points[k];
    if (c) { xr[i] = c[0]; yr[i] = c[1]; } else { xr[i] = X(s); yr[i] = 540 - (restPitch(notes, s, tonic) - tonic) * 9; }
    hb[i] = wB > 0 && s < S.T2 ? gridHeight(S.trace, s, t) : 0;
  }
  const h = hb;
  const nowX = core.nowX;
  const pts = [], alpha = [], times = [], lifts = [];
  for (let i = 0; i < n; i++) {
    const xb = gridX(ss[i], T0, eighth);
    const yb = mix(GRID.y - h[i], 540, flat);
    const x = mix(xr[i], xb, wB), y = mix(yr[i], yb, wB);
    if (x < -30 || x > 1950) continue;
    // the core strand's alpha: the past solid (fading in from the left), the unsung ahead dim
    const ar = xr[i] <= nowX ? smoothstep(0, nowX * 0.6, xr[i]) : 0.28 * (1 - (xr[i] - nowX) / Math.max(1920 - nowX, 1));
    pts.push([x, y]); alpha.push(mix(ar, 1, wB)); times.push(ss[i]); lifts.push(h[i] * (1 - flat) * wB);
  }
  // before the first downbeat a point of light draws it from the left
  const head = headX(t);
  return { pts, alpha, times, lift: lifts, head, wB, flat };
}

// the point of light that draws the strand before the first downbeat: from the left margin, off the right edge
function headX(t) {
  return t < S.T0 ? 96 + ease.inOutCubic(clamp((t - S.Tb) / (S.T0 - S.Tb))) * (1960 - 96) : Infinity;
}

function drawStrand(ctx, t, target, ink) {
  const s = strandAt(ctx, t);
  const pts = [], al = [];
  for (let i = 0; i < s.pts.length; i++) {
    const [x, y] = s.pts[i];
    if (x > s.head) {
      if (i > 0) {
        const [xa, ya] = s.pts[i - 1];
        pts.push([s.head, mix(ya, y, clamp((s.head - xa) / (x - xa)))]);
        al.push(s.alpha[i - 1]);
      }
      break;
    }
    pts.push([x, y]); al.push(s.alpha[i]);
  }
  if (pts.length > 1) ctx.g.stroke(target, pts, { width: 2.5, color: ink.cold, intensity: mix(1.35, 1, ink.k), alpha: (i) => al[i] });
  // the note sounding now, in amber, from its start to now
  const n = S.trace && s.wB > 0 ? ctx.score.sounding(PART, t, 0.3).filter((m) => m.art !== 'cut' && m.t < S.T2).pop() : null;
  if (n) {
    const run = [];
    for (let i = 0; i < pts.length; i++) if (s.times[i] >= n.t && s.times[i] <= Math.min(t, n.t + n.d)) run.push(pts[i]);
    const end = n.t + n.d, glow = (t < end ? 1 : 1 - smoothstep(end, end + 0.3, t)) * s.wB * (1 - s.flat);
    if (run.length > 1) ctx.g.stroke(target, run, { width: 2.5, color: ink.sung, intensity: 1.25 + 0.9 * level(ctx, t), alpha: glow });
  }
  // the point of light that draws it
  if (s.head < 1950) {
    const hx = Math.max(s.head, 0), hy = pts.length ? pts[pts.length - 1][1] : 540;
    const a = smoothstep(0, S.Tb, t) * (1 - smoothstep(S.T0 - 0.05, S.T0, t));
    ctx.g.points(target, [{ x: hx, y: hy, r: 5, color: ink.cold, alpha: a, intensity: 3.2, soft: 0.9 }]);
  }
  return s;
}

// the whistle's sound level at t (its stem's RMS, 0..1 over the last 40 dB)
function level(ctx, t) {
  const env = ctx.data.get('stems/whistle~.env');
  const v = env.at(t)[0];
  return clamp((v + 40) / 34);
}

// where song time s sits on the strand at t, for a height hb above the grid's line: the same blend as strandAt
function placeAt(ctx, t, s, hb) {
  const { T0, T2, T4, beat, eighth } = S;
  const tonic = ctx.timeline.tonic;
  const wIn = ease.inOutSine(clamp((t - T0) / beat));
  const flat = S.flatAt(t);
  const wOut = ease.inOutSine(clamp((t - (T4 - beat)) / beat));
  const wB = wIn * (1 - wOut);
  const xr = 1920 * (0.62 + (s - t) / 7), yr = 540 - (restPitch(ctx.score.notes(ctx.score.lead(t).part), s, tonic) - tonic) * 9;
  return [mix(xr, gridX(s, T0, eighth), wB), mix(yr, mix(GRID.y - hb, 540, flat), wB), wB * (1 - flat)];
}

// the phrase set as type: digits under the strand, dashes for held units, bar lines; each digit lifting as it is played
function drawTune(ctx, t, target, ink) {
  const { T0, T2, beat, eighth } = S;
  const out = 1 - smoothstep(T2 - beat * 0.6, T2 + beat * 0.1, t);
  if (out <= 0) return;
  const set = S.r3;
  const n = set.length;
  const marks = [], pts = [];
  const lvl = level(ctx, t);
  set.forEach((w, i) => {
    // composed left to right across the first beat after the downbeat
    const ts = T0 + (i / n) * beat * 0.9;
    const k = ease.outCubic(clamp((t - ts) / (beat * 0.35))) * out;
    if (k <= 0) return;
    const cx = cellX(w.at) + GRID.cell / 2;
    const up = lifted(w.note, t);
    const spr = ctx.type.text(w.degree.replace(/[,']/g, ''), { role: 'numeral', size: GRID.digitSize });
    // the written digit stays, dim once played
    ctx.type.draw(target, spr, cx, GRID.digitBase - (1 - k) * 18, { color: ink.ink2, alpha: k * mix(1, 0.42, up), align: 'center' });
    // held units
    for (let u = 1; u < w.units; u++) {
      const dx = cellX(w.at + u) + GRID.cell / 2;
      marks.push({ p: [[dx - 20, GRID.digitBase - 29], [dx + 20, GRID.digitBase - 29]], a: k * mix(1, 0.42, up), w: 2 });
    }
  });
  // the notes played: each a point where its digit went, amber while it sounds; its copy rises to it
  for (const w of S.grid) {
    if (!w.note) continue;
    const up = lifted(w.note, t);
    if (up <= 0) continue;
    const s = w.t0 + eighth / 2;
    const [x, y, wb] = placeAt(ctx, t, s, (GRID.y - liftY(w.note.p)) * up);
    if (x > headX(t)) continue;
    const end = w.note.t + w.note.d;
    const glow = t < end ? 1 : 1 - smoothstep(end, end + 0.3, t);
    pts.push({ x, y, r: 4.2 * up, color: glow > 0 ? ink.sung : ink.cold, alpha: 1, intensity: mix(1.6, 1.8 + 1.4 * lvl, glow), soft: 0.6 });
    if (up < 1 && w.at >= 0 && w.at < 16 || (up < 1 && w.at === -1)) {
      const spr = ctx.type.text(w.degree.replace(/[,']/g, ''), { role: 'numeral', size: GRID.digitSize });
      const cx = cellX(w.at) + GRID.cell / 2;
      ctx.type.draw(target, spr, cx, mix(GRID.digitBase, y + spr.ascent * 0.4, up), { color: ink.ink, alpha: wb * (1 - up) ** 1.5, align: 'center' });
    }
  }
  // bar lines of the written tune
  for (const at of [0, 8, 16]) {
    const x = cellX(at), k = ease.outCubic(clamp((t - T0) / (beat * 0.6))) * out;
    marks.push({ p: [[x, GRID.digitBase + 18], [x, GRID.digitBase - 78]], a: k, w: 1.6 });
  }
  for (const m of marks) ctx.g.stroke(target, m.p, { width: m.w || 1.2, color: ink.ink2, alpha: m.a });
  ctx.g.points(target, pts);
}

export default {
  id: 's01_writing',
  section: 'intro',
  enter: { kind: 'dissolve', beats: 1 },
  assets: ['text.json', 'stems/whistle~.env', 'physics/analog.json', 'physics/analog-traces',
    'physics/drummachine.json', 'stems/drone.env', 'stems/synthpad.env'],
  async init(ctx) {
    const tl = ctx.timeline, intro = tl.byId('intro');
    const text = ctx.data.get('text.json');
    const [p1, p2] = text.sections.intro.phrases;
    S.beat = tl.beatLength;
    S.eighth = tl.barLength / 8;
    S.T0 = intro.t0;
    S.T2 = tl.bars.find((b) => b > intro.t0 + tl.barLength * 1.5);
    S.T4 = intro.t1;
    S.Tb = tl.beats.filter((b) => b < intro.t0).pop() ?? intro.t0 - tl.beatLength;
    S.r3 = setPhrase(ctx, text.phrases[p1], S.T0);
    S.r4 = setPhrase(ctx, text.phrases[p2], S.T2);
    // the second phrase's pickup sounds in the first phrase's last unit
    const pick = S.r4.filter((w) => w.at < 0).map((w) => ({ ...w, at: 16 + w.at }));
    S.grid = S.r3.concat(pick);
    S.trace = traceOf(ctx, PART, intro.t0, intro.t1);
    S.flatAt = (t) => ease.inOutSine(clamp((t - (S.T2 - S.beat * 0.6)) / (S.beat * 0.75)));
    S.gridAt = (t) => ease.inOutSine(clamp((t - S.T0) / S.beat)) * (1 - ease.inOutSine(clamp((t - (S.T4 - S.beat)) / S.beat)));
    S.layers = await buildLayers(ctx, S);
    S.T3 = tl.bars.find((b) => b > S.T2 + tl.barLength / 2);
    S.bank = buildBank(ctx);
    S.reg = buildRegister(ctx);
    const b = S.beat;
    S.bankT = { start: S.T2, stream1: S.T3 + b, rise0: S.T3, rise1: S.T3 + b, close0: S.T3 + b, close1: S.T3 + 2 * b,
      out0: S.T4 - 1.75 * b, out1: S.T4 - 1.25 * b };
  },
  render(ctx, t, target) {
    ground(ctx, t, target);
    const ink = ctx.palette.inks(ctx.k(t));
    drawBank(ctx, t, target, ink, S.bank, S.bankT);
    // the bank's floor fades into the dark at the frame's foot, under its label
    const { T0, T2, T4, beat } = S;
    const bankLabel = smoothstep(T2, T2 + beat / 2, t) * (1 - smoothstep(T4 - beat / 2, T4, t));
    if (bankLabel > 0) {
      const shade = [];
      for (let y = FOOT.from; y < ctx.size.h; y += FOOT.band) {
        shade.push({ x: 0, y, w: ctx.size.w, h: FOOT.band, color: ctx.g.ground, alpha: bankLabel * smoothstep(FOOT.from, FOOT.to, y + FOOT.band / 2) });
      }
      ctx.g.rects(target, shade);
    }
    drawLayers(ctx, t, target, ink, S, S.layers, smoothstep(0.8, 1, S.gridAt(t)) * (1 - S.flatAt(t)));
    drawTune(ctx, t, target, ink);
    drawStrand(ctx, t, target, ink);
    drawRegister(ctx, t, target, ink, S.reg, { x0: 960 - 7.5 * 28, alpha: 1 - smoothstep(S.bankT.out0, S.bankT.out1, t) });
    // one label at a time, each up for its two bars
    label(ctx, t, target, 'tune', { alpha: smoothstep(T0 - beat / 2, T0, t) * (1 - smoothstep(T2 - beat / 2, T2, t)) });
    label(ctx, t, target, 'bank', { alpha: bankLabel });
    lyric(ctx, t, target);
  },
  anchor(ctx, t) {
    const s = strandAt(ctx, t);
    return { points: s.pts, alpha: s.alpha, width: 2.5, color: ctx.palette.inks(ctx.k(t)).cold };
  },
};
