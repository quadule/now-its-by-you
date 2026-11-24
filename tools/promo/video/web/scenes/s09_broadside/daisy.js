// Line 3: the daisy leaves the corner where the bridge grew it for its place on the face, and takes its inks.
//
// It is the cover's woodcut (data/daisy.json, woodcut.py's own marks), cut into face.py's plates: each ink a mask in
// painting order (a later fill of another ink hides a tint or the black beneath it; a cut takes white out of the
// black). It stands where core/daisy.js put it (foot at 1690, 1010, 300 high), drawn on a grid of the face's points
// so that, moved and grown, it lands on the face's own daisy point for point: the grid goes from the woodcut placed
// in the corner to the face's grid in the closing shot, its scale in equal ratios and the sheet's bow coming in as it
// arrives. It sets out on the sung "grows" (line 2's last word) and grows into its place over all of line 3 in black
// and white; on arrival the face's own plates take over and print its tints.
import { clamp, smoothstep, ease } from '../../core/math.js';

const CANVAS_H = 2048, PAD = 64;   // the pad keeps the texture's edge clear at every mip level used
export const CORNER = { x: 1690, y: 1010, height: 300 };

function plates(json) {
  const box = json.box;
  const W = Math.ceil(box.w * CANVAS_H) + 2 * PAD, H = CANVAS_H + 2 * PAD;
  const inks = ['black', 'white', 'yellow', 'green'];
  const canvases = {};
  const marks = json.groups.flatMap((g) => g.marks);
  for (const ink of inks) {
    const cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const c = cv.getContext('2d');
    c.setTransform(CANVAS_H, 0, 0, CANVAS_H, PAD, PAD);
    c.fillStyle = '#fff';
    for (const m of marks) {
      let mode = null;
      if (m.op === 'fill') {
        if (m.ink === ink) mode = 'source-over';
        else if (ink === 'black' || m.ink !== 'black') mode = 'destination-out';
      } else if (ink === 'black') mode = 'destination-out';
      if (!mode) continue;
      const p = new Path2D();
      for (const ring of m.rings) {
        ring.forEach(([x, y], i) => (i ? p.lineTo(x, y) : p.moveTo(x, y)));
        p.closePath();
      }
      c.globalCompositeOperation = mode;
      c.fill(p, m.rule === 'evenodd' ? 'evenodd' : 'nonzero');
    }
    canvases[ink] = cv;
  }
  return { canvases, W, H };
}

export class Daisy {
  init(ctx, F, grid) {
    const json = ctx.data.get('daisy.json');
    this.json = json;
    const { canvases, W, H } = plates(json);
    this.W = W; this.H = H;
    this.tex = Object.fromEntries(Object.entries(canvases).map(([k, cv]) => [k, ctx.g.texture(cv, { mips: true })]));
    this.F = F;
    const box = json.box;
    // the texture's coordinates at face u = 0, 1 and v = 0, 1 (linear in the face's units)
    const cu = (fx) => (((fx - box.x0) / box.size) * CANVAS_H + PAD) / W;
    const cv = (fy) => (((fy - box.y0) / box.size) * CANVAS_H + PAD) / H;
    this.uv = [cu(0), cv(0), cu(1275), cv(1650)];
    // the grid's face points (units)
    const cols = F.cols, rows = F.rows;
    this.fpts = new Float32Array(cols * rows * 2);
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const i = r * cols + c;
      this.fpts[i * 2] = (c / (cols - 1)) * 1275;
      this.fpts[i * 2 + 1] = (r / (rows - 1)) * 1650;
    }
    // the face's grid as a scale and a shift (least squares), and what is left: the sheet's bow
    const n = cols * rows;
    let sx = 0, sy = 0, gx = 0, gy = 0;
    for (let i = 0; i < n; i++) { sx += this.fpts[i * 2]; sy += this.fpts[i * 2 + 1]; gx += grid[i * 2]; gy += grid[i * 2 + 1]; }
    const mfx = sx / n, mfy = sy / n, mgx = gx / n, mgy = gy / n;
    let num = 0, den = 0;
    for (let i = 0; i < n; i++) {
      const fx = this.fpts[i * 2] - mfx, fy = this.fpts[i * 2 + 1] - mfy;
      num += fx * (grid[i * 2] - mgx) + fy * (grid[i * 2 + 1] - mgy);
      den += fx * fx + fy * fy;
    }
    const a1 = num / den;
    this.a1 = a1;
    this.b1 = [mgx - a1 * mfx, mgy - a1 * mfy];
    this.bow = new Float32Array(n * 2);
    for (let i = 0; i < n; i++) {
      this.bow[i * 2] = grid[i * 2] - (a1 * this.fpts[i * 2] + this.b1[0]);
      this.bow[i * 2 + 1] = grid[i * 2 + 1] - (a1 * this.fpts[i * 2 + 1] + this.b1[1]);
    }
    // the corner: core/daisy.js's placement, foot (x, y), the whole woodcut `height` high
    const a0 = CORNER.height / box.size;
    this.a0 = a0;
    this.b0 = [CORNER.x - (box.x0 / box.size + json.root[0]) * CORNER.height, CORNER.y - (box.y0 / box.size + json.root[1]) * CORNER.height];
    // the disc's centre in face units: what travels on the path
    this.disc = [json.disc_centre[0] * box.size + box.x0, json.disc_centre[1] * box.size + box.y0];
    this.grid = new Float32Array(n * 2);

    const tl = ctx.timeline;
    const line = tl.lineOf('refrain3', 2);
    const syl = line.words.flatMap((w) => w.syllables);
    // it grows in black and white; its tints print with the face's plates when it lands
    this.yellowT = Infinity;
    this.greenT = Infinity;
    // it sets out on "grows" and arrives in the bar after line 3's last word
    const before = tl.lineOf('refrain3', 1).words.flatMap((w) => w.syllables);
    this.goT = before[before.length - 1].t0;
    this.landT = tl.bar(syl[syl.length - 1].t0).t1;
    this.printT = this.landT;
    this.handT = 0.3;
  }

  // how far along its way at t (0 the corner, 1 its place on the face)
  travel(t) { return ease.inOutSine(clamp((t - this.goT) / (this.landT - this.goT))); }

  // the grid the woodcut is drawn on at travel e
  gridAt(e) {
    const s = Math.exp(Math.log(this.a0) + (Math.log(this.a1) - Math.log(this.a0)) * e);
    const d0 = [this.a0 * this.disc[0] + this.b0[0], this.a0 * this.disc[1] + this.b0[1]];
    const d1 = [this.a1 * this.disc[0] + this.b1[0], this.a1 * this.disc[1] + this.b1[1]];
    // the disc's way: up and over to the left, then down into its place
    const c = [(d0[0] + d1[0]) / 2 + 60, Math.min(d0[1], d1[1]) - 260];
    const q = (1 - e) * (1 - e), w = 2 * e * (1 - e), k = e * e;
    const d = [q * d0[0] + w * c[0] + k * d1[0], q * d0[1] + w * c[1] + k * d1[1]];
    const bx = d[0] - s * this.disc[0], by = d[1] - s * this.disc[1];
    const g = this.grid, f = this.fpts, b = this.bow, bow = e * e;
    for (let i = 0; i < f.length / 2; i++) {
      g[i * 2] = s * f[i * 2] + bx + b[i * 2] * bow;
      g[i * 2 + 1] = s * f[i * 2 + 1] + by + b[i * 2 + 1] * bow;
    }
    return g;
  }

  // a plate's landing: its offset (design units) from where it settles, and its amount
  landing(t, t0, dx, dy) {
    const k = clamp((t - t0) / 0.55);
    const amt = smoothstep(t0, t0 + 0.06, t);
    const d = k >= 1 ? 0 : Math.exp(-5 * k) * Math.cos(k * 10);
    return { amt, off: [dx * d, dy * d] };
  }

  // the plates the face prints for the daisy at t
  // it lands on the face's own daisy point for point, so the face takes it over on the landing frame (two daisies
  // over each other while one fades into the other would flash); its tints then print over handT
  plates(t, st) {
    const on = t >= this.printT ? 1 : 0, p = smoothstep(this.printT, this.printT + this.handT, t);
    st.white = on; st.daisy = on; st.petalErase = on;
    st.yellow = p; st.green = p;
    return st;
  }

  // where its fills lie at t (r), to clear the sky's lines beneath them as the face's own fills do
  mask(ctx, t, target) {
    const away = t < this.printT ? 1 : 0;
    if (away <= 0) return null;
    const tg = target || ctx.g.screen;
    if (!this.m || this.m.w !== tg.w || this.m.h !== tg.h) {
      if (this.m) ctx.g.free(this.m);
      this.m = ctx.g.target(tg.w, tg.h, { float: false });
    }
    ctx.g.clear(this.m, [0, 0, 0, 0]);
    const grid = this.gridAt(this.travel(t));
    const opts = { cols: this.F.cols, rows: this.F.rows, uv: this.uv, srgb: true, blend: 'over', tint: [1, 1, 1] };
    // every fill clears the sky beneath it, its tint printed or not, as the face's own fills do
    for (const k of ['white', 'yellow', 'green']) ctx.g.mesh(this.m, this.tex[k], grid, { ...opts, alpha: away });
    return this.m;
  }

  draw(ctx, t, target) {
    const away = t < this.printT ? 1 : 0;
    if (away <= 0) return;
    const F = this.F, g = ctx.g;
    const e = this.travel(t);
    const grid = this.gridAt(e);
    const paper = F.paper, I = F.inks;
    const opts = { cols: F.cols, rows: F.rows, uv: this.uv, srgb: true };
    const shifted = (off) => {
      if (!off[0] && !off[1]) return grid;
      const s = new Float32Array(grid.length);
      for (let i = 0; i < s.length; i += 2) { s[i] = grid[i] + off[0]; s[i + 1] = grid[i + 1] + off[1]; }
      return s;
    };
    const unit = Math.exp(Math.log(this.a0) + (Math.log(this.a1) - Math.log(this.a0)) * e);
    const gr = this.landing(t, this.greenT, 2.2 * unit * 4, 1.1 * unit * 4);
    const ye = this.landing(t, this.yellowT, -2.6 * unit * 4, 1.8 * unit * 4);
    if (gr.amt > 0) g.mesh(target, this.tex.green, shifted(gr.off), { ...opts, blend: 'multiply', alpha: gr.amt * away, tint: I.green.map((v, i) => v / paper[i]) });
    if (ye.amt > 0) g.mesh(target, this.tex.yellow, shifted(ye.off), { ...opts, blend: 'multiply', alpha: ye.amt * away, tint: I.yellow.map((v, i) => v / paper[i]) });
    g.mesh(target, this.tex.white, grid, { ...opts, blend: 'over', alpha: 0.8 * away, tint: I.white });
    g.mesh(target, this.tex.black, grid, { ...opts, blend: 'over', alpha: 0.97 * away, tint: I.black });
  }
}
