// The tag: the bowed bass (the whistle's tune two octaves down, the sung tag's place taken by it, drawn out). The
// broadside stays as s09 left it, the packet's face printed whole at the closing shot's first frame; the hatch line
// in the middle of its open sky (between the band and the petals' tops, level with the roundel) is the bass's string,
// fixed at the panel's two rules, the bridge on the right, behind the roundel. Bowed, it swings out of
// the hatching: its true shape from the instrumented bowed.run_primed (data/bass/tag-period, prep/bass.py), the
// Helmholtz corner running round it once every two beats in slow motion (as s04_bow shows the fiddle's), the period's
// sixteen snapshots behind it as a lens of hairlines, the bow's hair crossing it at its captured place and pressing
// with its captured force, its marks carried at the bow's slowed travel. The swing follows the stage's level.
// Over the last bar the face rides the closing shot's grid, so the photograph (s10_cover) comes in under it.
import { label } from '../../core/draw.js';
import { smoothstep, clamp, mix } from '../../core/math.js';
import { loadFace, drawFace, PRINTED } from '../s09_broadside/face.js';
import { JOIN_GAIN } from '../s09_broadside/join.js';
import { Daisy } from '../s09_broadside/daisy.js';
import { Helmholtz } from './helmholtz.js';

const SCALE = 1.9;      // design units of swing per unit of the model's displacement
const HAIRS = 9, SHEAF = 30, REACH = [210, 130];   // the bow's hair: count, width, reach above and below the string
const PANEL = [22, 10];   // the label's clearing round its type (design units)
const CLEAR = 12;         // the width cut away from the hatching round each line of the lens (design units)

// a gaussian along one axis (uDir: one texel along it): the clearing's soft edge
const BLUR = `#version 300 es
precision highp float;
in vec2 vUv;
uniform sampler2D uSrc; uniform vec2 uDir; uniform float uS;
out vec4 o;
void main() {
  float m = 0.0, w = 0.0;
  for (int i = -24; i <= 24; i++) {
    float x = float(i) * uS / 8.0;
    float k = exp(-0.5 * x * x / (uS * uS / 4.0));
    m += texture(uSrc, vUv + uDir * x).a * k;
    w += k;
  }
  m /= w;
  o = vec4(m, m, m, m);
}`;

export default {
  id: 's09b_bass',
  section: 'tag',
  enter: { kind: 'cut' },
  assets: ['daisy.json', 'bass/bass.json', 'bass/tag-period', 'bass/tag-tracks'],

  async init(ctx) {
    const tl = ctx.timeline;
    this.sec = tl.byId('tag');
    this.F = await loadFace(ctx);
    const F = this.F, grid = F.grid(F.first), S = F.json.px_per_unit, cy0 = F.json.crop_px[1];
    // the string: the row nearest the middle of the open sky, between the band's foot and the petals' tops (the
    // disc's centre less two and a half of its radii)
    const rows = F.json.sky.rows.map((r) => ({ r, y: F.toDesign(grid, 600, r.y)[1] })).sort((a, b) => a.y - b.y);
    const open = (F.json.title.band_y[1] + F.json.daisy.disc[1] - 2.5 * F.json.daisy.disc_r) / 2;
    const k = rows.reduce((best, x, i) => (Math.abs(x.r.y - open) < Math.abs(rows[best].r.y - open) ? i : best), 1);
    const row = rows[k].r;
    this.row = row;
    // its band of crop rows, between it and its neighbours, left unprinted: the string stands in its place
    const mid = (a, b) => ((a.r.y + b.r.y) / 2) * S - cy0;
    this.band = [Math.floor(mid(rows[k - 1], rows[k])), Math.ceil(k + 1 < rows.length ? mid(rows[k], rows[k + 1]) : row.y * S - cy0 + 12)];
    // its points in face units, left to right; the string runs between the panel's rules
    const pts = row.stretches.flatMap((s) => s.x.map((x, i) => [x, s.y[i], s.w[i]])).sort((a, b) => a[0] - b[0]);
    const [px0, , px1] = F.json.sky.panel;
    this.face = { x0: px0, x1: px1, pts };
    this.wface = pts.reduce((s, p) => s + p[2], 0) / pts.length;   // the hatch line's own width (face units)
    this.unitAt(grid);   // design units per face unit at the first frame (this.dpf)
    this.daisy = new Daisy();
    this.daisy.init(ctx, F, grid);
    const meta = ctx.data.get('bass/bass.json');
    this.notes = meta.windows.tag.notes;
    this.H = new Helmholtz(ctx, ctx.data.get('bass/tag-period'), ctx.data.get('bass/tag-tracks'), { t0: this.sec.t0, beats: 2 });
    // the marks carried along the hair: a seeded pattern (fibres and rosin), fixed to the hair
    const rnd = ctx.prng(9161);
    this.marks = [];
    for (let h = 0; h < HAIRS; h++) for (let m = 0; m < 9; m++) this.marks.push({ h, u: rnd(), r: 0.5 + 0.7 * rnd() ** 3, a: 0.35 + 0.5 * rnd() });
    this.grid = new Float32Array(grid.length);
    this.sh = new Float32Array(this.H.NP);
  },

  // the shot's frame at t: the photograph's first frame until s10's shot starts, then the shot's own (fractional)
  shotFrame(ctx, t) {
    const s10 = ctx.scene('s10_cover');
    const start = s10 && s10.start ? s10.start(ctx) : Infinity;
    return this.F.first + Math.max(0, (t - start) * ctx.timeline.fps);
  },

  gridAt(ctx, t) {
    const F = this.F, fr = this.shotFrame(ctx, t), i = Math.floor(fr + 1e-6), k = fr - i;
    const g0 = F.grid(i), g1 = F.grid(i + 1), out = this.grid;
    for (let j = 0; j < out.length; j++) out[j] = g0[j] + (g1[j] - g0[j]) * k;
    return out;
  },

  targets(ctx, target) {
    const tg = target || ctx.g.screen;
    if (this.m && this.m.w === tg.w && this.m.h === tg.h) return;
    for (const x of [this.m, this.m2]) if (x) ctx.g.free(x);
    this.m = ctx.g.target(tg.w, tg.h, { float: false });
    this.m2 = ctx.g.target(tg.w, tg.h, { float: false });
  },

  // how far the string is out of the hatching: in over the first beat, out with the bass's last stroke's ring
  pull(ctx, t) {
    const b = ctx.timeline.beatLength;
    return smoothstep(this.sec.t0, this.sec.t0 + b, t);
  },

  render(ctx, t, target) {
    const F = this.F, g = ctx.g, tl = ctx.timeline, b = tl.beatLength;
    this.targets(ctx, target);
    const grid = this.gridAt(ctx, t);
    const riding = this.shotFrame(ctx, t) > F.first;
    const paper = ctx.palette.inks(1).ground;
    g.clear(target, [paper[0], paper[1], paper[2], 1]);
    // riding the shot, the photograph lies under the face as s10_cover shows it (the frame it has fetched for t)
    if (riding) {
      const s10 = ctx.scene('s10_cover'), img = s10 && s10.shown && s10.shown.get(s10.index(ctx, t));
      if (img) g.rects(target, [{ x: 0, y: 0, w: ctx.size.w, h: ctx.size.h }], { texture: img.tex, srgb: true });
    }
    g.ground = F.paper;
    ctx.type.ground = F.paper;
    // the face as printed, less the string's hatch line
    F.rowsData.fill(1);
    F.rowsData.fill(0, Math.max(this.band[0], 0), Math.min(this.band[1], F.rowsData.length));
    F.titleData.fill(1);
    const look = { gain: JOIN_GAIN, feather: riding ? 8 : 0 };
    drawFace(ctx, target, F, grid, PRINTED, look);

    // the string: the hatch line's own points through the grid, displaced across it by the bowed shape
    const H = this.H, pull = this.pull(ctx, t);
    const level = Math.sqrt(tl.gain('bowedbass', t));
    const unit = this.unitAt(grid);
    const ink = F.inks.black.map((v, i) => v * JOIN_GAIN[i]);
    const cur = H.shapeAt(t, this.sh), NP = H.NP, gain = SCALE * level * pull * unit;
    const N = 240;
    const place = (u, d) => {   // u 0 the bridge (right) .. 1 the nut (left); d swing (design units, up)
      const fx = mix(this.face.x1, this.face.x0, u), fy = this.rowY(fx);
      const p = F.toDesign(grid, fx, fy);
      return [p[0], p[1] - d];
    };
    if (pull > 0.002) {
      // the period's sixteen snapshots: the lens the corner sweeps, the sky's hatching cut away round it
      const lens = [];
      for (let q = 0; q < H.S; q++) {
        const d = H.snap(cur.f, q), pts = [];
        for (let i = 0; i < N; i++) { const u = i / (N - 1); pts.push(place(u, H.at(d, u * (NP - 1)) * gain)); }
        lens.push(pts);
      }
      const m = this.m, px = m.h / 1080;
      g.clear(m, [0, 0, 0, 0]);
      for (const pts of lens) g.stroke(m, pts, { width: CLEAR * unit, color: [1, 1, 1], alpha: pull });
      const prog = g.program('s09b:blur', BLUR);
      g.pass(this.m2, prog, { uSrc: m, uDir: [1 / m.w, 0], uS: 3 * px });
      g.pass(m, prog, { uSrc: this.m2, uDir: [0, 1 / m.h], uS: 3 * px });
      drawFace(ctx, target, F, grid, { ...PRINTED, sky: 0 }, { ...look, mask: m });
      for (const pts of lens) g.stroke(target, pts, { width: 1.2 * unit, color: ink, alpha: 0.8 * pull });
    }
    {
      const pts = [];
      for (let i = 0; i < N; i++) { const u = i / (N - 1); pts.push(place(u, H.at(cur.out, u * (NP - 1)) * gain)); }
      g.stroke(target, pts, { width: mix(this.wface * this.dpf, 3.2, pull) * unit, color: ink, alpha: 0.97 });
      // the corner, where the two straight lines meet
      if (pull > 0.002) {
        const c = place(cur.xc, H.at(cur.out, cur.xc * (NP - 1)) * gain);
        g.points(target, [{ x: c[0], y: c[1], r: 6 * unit, color: ink, alpha: pull }]);
      }
    }

    // the bow: a sheaf of hair across the string at its captured place, pressing as the captured force grows, its
    // marks carried at its slowed travel
    const bow = H.bowAt(t);
    const on = smoothstep(0.02, 0.08, bow.force) * pull;
    if (on > 0.003) {
      const c = place(bow.pos, H.at(cur.out, bow.pos * (NP - 1)) * gain), base = place(bow.pos, 0);
      const press = 3.2 * bow.force;
      const len = REACH[0] + REACH[1];
      for (let h = 0; h < HAIRS; h++) {
        const o = (h / (HAIRS - 1) - 0.5) * SHEAF * unit, P = [], wid = [];
        for (let i = 0; i < 32; i++) {
          const yy = (-REACH[0] + (len * i) / 31) * unit;
          P.push([base[0] + o, base[1] + yy]);
          wid.push((0.42 + press * Math.exp(-(((base[1] + yy - c[1]) / (30 * unit)) ** 2))) * unit);
        }
        g.stroke(target, P, { width: (i) => wid[i], color: ink, alpha: on * (h === 0 || h === HAIRS - 1 ? 0.95 : 0.7) });
      }
      const dots = [], L = len * unit, tr = bow.travel * gain;
      for (const m of this.marks) {
        const yy = ((((m.u * L - tr) % L) + L) % L) - REACH[0] * unit;
        const o = (m.h / (HAIRS - 1) - 0.5) * SHEAF * unit;
        dots.push({ x: base[0] + o, y: base[1] + yy, r: m.r * unit, color: ink, alpha: on * m.a });
      }
      g.points(target, dots);
    }

    // the daisy stands in front of the sky: its fills printed again over the string
    const dm = this.daisyMask(ctx, grid);
    drawFace(ctx, target, F, grid, PRINTED, { ...look, mask: dm });

    // the label, in a clearing cut in the sky under the band, as the woodcut leaves a panel round type
    const la = smoothstep(this.sec.t0 + b, this.sec.t0 + 2 * b, t) * (1 - smoothstep(this.labelEnd(ctx) - b, this.labelEnd(ctx), t));
    if (la > 0) {
      const at = this.labelAt(grid);
      const s = ctx.type.text(ctx.label('bass'), { role: 'label', size: 26 });
      const mask = this.panel(ctx, at, s, la);
      drawFace(ctx, target, F, grid, { ...PRINTED, sky: 0 }, { ...look, mask });
      label(ctx, t, target, 'bass', { x: at[0], y: at[1], size: 26, alpha: la, k: 1, color: F.inks.red.map((v, i) => v * JOIN_GAIN[i]) });
    }
  },

  // the row's height (face units) at face x
  rowY(fx) {
    const p = this.face.pts;
    let lo = 0, hi = p.length - 1;
    if (fx <= p[0][0]) return p[0][1];
    if (fx >= p[hi][0]) return p[hi][1];
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (p[m][0] <= fx) lo = m; else hi = m; }
    const w = (fx - p[lo][0]) / Math.max(p[hi][0] - p[lo][0], 1e-6);
    return p[lo][1] + (p[hi][1] - p[lo][1]) * w;
  },

  // design units per face unit at the sky, over the face's own scale at the first frame (1 there)
  unitAt(grid) {
    const a = this.F.toDesign(grid, 300, 600), c = this.F.toDesign(grid, 1000, 600);
    if (!this.unit0) {
      const g0 = this.F.grid(this.F.first), a0 = this.F.toDesign(g0, 300, 600), c0 = this.F.toDesign(g0, 1000, 600);
      this.unit0 = c0[0] - a0[0];
      this.dpf = this.unit0 / 700;
    }
    return (c[0] - a[0]) / this.unit0;
  },

  // the label's baseline: in the sky under the band, left, above the roundel
  labelAt(grid) {
    return this.F.toDesign(grid, 86, 310);
  },

  // the label is up until the photograph comes in
  labelEnd(ctx) {
    const s10 = ctx.scene('s10_cover');
    return s10 && s10.start ? s10.start(ctx) : this.sec.t1;
  },

  // the clearing round the label's type, its edge softened
  panel(ctx, at, s, a) {
    const g = ctx.g, m = this.m, px = m.h / 1080;
    g.clear(m, [0, 0, 0, 0]);
    g.rects(m, [{ x: at[0] - PANEL[0], y: at[1] - s.ascent - PANEL[1], w: s.width + 2 * PANEL[0], h: s.ascent + s.descent + 2 * PANEL[1], color: [1, 1, 1], alpha: a }]);
    const prog = g.program('s09b:blur', BLUR);
    g.pass(this.m2, prog, { uSrc: m, uDir: [1 / m.w, 0], uS: 5 * px });
    g.pass(m, prog, { uSrc: this.m2, uDir: [0, 1 / m.h], uS: 5 * px });
    return m;
  },

  // where the daisy's fills and black and the roundel lie on the face (r), through the grid: what stands in front
  // of the sky
  daisyMask(ctx, grid) {
    const D = this.daisy, g = ctx.g, R = this.F.json.roundel;
    g.clear(this.m, [0, 0, 0, 0]);
    const opts = { cols: this.F.cols, rows: this.F.rows, uv: D.uv, srgb: true, blend: 'over', tint: [1, 1, 1] };
    for (const k of ['white', 'yellow', 'green', 'black']) g.mesh(this.m, D.tex[k], grid, { ...opts, alpha: 1 });
    const c = this.F.toDesign(grid, R.x, R.y), e = this.F.toDesign(grid, R.x + R.r[0] + 2, R.y);
    g.points(this.m, [{ x: c[0], y: c[1], r: e[0] - c[0], color: [1, 1, 1], alpha: 1 }]);
    return this.m;
  },

  // the face's grade: the photograph's (s09 hands over in it)
  raw() { return 1; },
  finish() { return 1; },
  light() { return 1; },
};
