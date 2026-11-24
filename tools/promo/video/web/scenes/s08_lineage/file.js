// The release file as one strand, to scale: world x is the byte offset from the zip's first byte (the join), so the
// audio is x < 0 and the program x >= 0. y is down (the band's cross-section), z is depth. The cross-section's
// height is set by the view (H), so the strand reads at every distance the camera takes.
//
//   model(ctx)                         the file: FLAC frames with the mix's level over each, zip entries, textures
//   drawFile(ctx, target, cam, H, ink, o)   the strand as cam sees it
import { Segs } from './lines.js';
import { clamp, smoothstep } from '../../core/math.js';
import { below } from '../../core/timeline.js';

export const FILE_ASSETS = ['s08/file.json', 's08/mix-bands', 's08/weights', 'packet-bytes'];

const FAMILY = '"Film Serif"';
let M = null;


export function model(ctx) {
  const json = ctx.data.get('s08/file.json');
  if (M && M.json === json) return M;
  const bands = ctx.data.get('s08/mix-bands');
  const join = json.zip;
  const frames = Float64Array.from(json.frames, (b) => b - join);
  const nf = frames.length;
  // the mix over each FLAC frame (4096 samples): the loudest video frame's RMS, and each of its eight bands
  const rms = new Float32Array(nf), band = new Float32Array(nf * 8);
  for (let i = 0; i < nf; i++) {
    const t0 = (i * json.block) / json.rate, t1 = Math.min((i + 1) * json.block, json.samples) / json.rate;
    let r = -100;
    const b = new Float32Array(8).fill(-100);
    for (let j = Math.max(Math.round(t0 * 60), 0); j <= Math.min(Math.round(t1 * 60), bands.rows - 1); j++) {
      const row = bands.row(j);
      r = Math.max(r, row[0]);
      for (let c = 0; c < 8; c++) b[c] = Math.max(b[c], row[c + 1]);
    }
    rms[i] = r;
    band.set(b, i * 8);
  }
  // each band's range over the song (its 5th to 99.9th percentile), so its tone shows its own life
  const range = [];
  for (let c = 0; c < 8; c++) {
    const v = Array.from({ length: nf }, (_, i) => band[i * 8 + c]).sort((a, b) => a - b);
    range.push([v[Math.floor(nf * 0.05)], v[Math.floor(nf * 0.999)]]);
  }
  const entries = json.entries.map((e, i) => ({ ...e, i, x: e.offset - join, x1: (json.entries[i + 1]?.offset ?? json.bytes) - join,
    d: e.data_offset - join, leaf: e.name.split('/').pop() }));
  const bytes = ctx.data.get('packet-bytes');
  const zipCol = bytes.zip_column;
  const edge = bytes.raw.subarray(bytes.rowLength, bytes.rowLength * 2);
  M = {
    json, join, frames, rms, band, range, entries, edge, zipCol, edgeX0: -zipCol,
    start: -join, end: json.bytes - join, audio0: json.audio.offset - join,
    npz: entries.find((e) => e.name.endsWith('throat.npz')),
    pages: new Map(),
  };
  return M;
}

// the textures: a page of each text entry's opening lines, the weights, the bytes across the join
export function buildTextures(ctx) {
  const m = model(ctx), g = ctx.g;
  if (m.tex) return;
  const canvas = document.createElement('canvas'), c = canvas.getContext('2d');
  const page = (e, near) => {
    const px = near ? 30 : 13, lead = Math.round(px * 1.4), rows = 7, cols = near ? 110 : 80;
    const lines = e.text.replace(/\t/g, '    ').split('\n').slice(0, rows).map((l) => l.slice(0, cols));
    c.font = `400 ${px}px ${FAMILY}`;
    const w = Math.ceil(Math.max(...lines.map((l) => c.measureText(l).width), px * 4)) + 4;
    canvas.width = w; canvas.height = lead * rows + Math.round(px * 0.4);
    c.font = `400 ${px}px ${FAMILY}`;
    c.fillStyle = '#fff';
    c.textBaseline = 'alphabetic';
    lines.forEach((l, i) => c.fillText(l, 2, Math.round(px * 1.05) + i * lead));
    return { tex: g.texture(canvas, { mips: true }), w: canvas.width, h: canvas.height, rowPx: lead };
  };
  m.entries.forEach((e, i) => { if (e.text) m.pages.set(e.name, page(e, i < 6)); });
  // the weights: ink where the voice's weights are large
  // packed: the picture's empty columns and rows (between tiles) left out, so the weights stand as one block
  const W = ctx.data.get('s08/weights'), [wh0, ww0] = W.shape;
  const colsUsed = [], rowsUsed = [];
  for (let x = 0; x < ww0; x++) { for (let y = 0; y < wh0; y++) if (W.raw[y * ww0 + x]) { colsUsed.push(x); break; } }
  for (let y = 0; y < wh0; y++) { for (let x = 0; x < ww0; x++) if (W.raw[y * ww0 + x]) { rowsUsed.push(y); break; } }
  const ww = colsUsed.length, wh = rowsUsed.length, rgba = new Uint8Array(wh * ww * 4);
  for (let r = 0; r < wh; r++) for (let q = 0; q < ww; q++) {
    const i = r * ww + q;
    rgba[i * 4] = rgba[i * 4 + 1] = rgba[i * 4 + 2] = 255; rgba[i * 4 + 3] = W.raw[rowsUsed[r] * ww0 + colsUsed[q]];
  }
  m.weights = { tex: g.texture({ width: ww, height: wh, data: rgba }, { mips: true }), w: ww, h: wh };
  // the bytes either side of the join: each byte's two hex digits, and below them its character where printable
  const N = 192, cell = 40, fpx = 24;
  canvas.width = N * 2 * cell; canvas.height = 76;
  c.clearRect(0, 0, canvas.width, canvas.height);
  c.fillStyle = '#fff';
  c.textAlign = 'center';
  for (let k = 0; k < N * 2; k++) {
    const v = m.edge[m.zipCol - N + k], x = k * cell + cell / 2;
    c.font = `400 ${fpx}px ${FAMILY}`;
    c.fillText(v.toString(16).padStart(2, '0'), x, 28);
    if (v > 32 && v < 127) { c.font = `italic 400 ${fpx}px ${FAMILY}`; c.fillText(String.fromCharCode(v), x, 64); }
  }
  m.hex = { tex: g.texture(canvas, { mips: true }), n: N, cell, w: canvas.width, h: canvas.height };
  m.tex = true;
}

// the FLAC frame holding byte x (relative), clamped
const frameAt = (m, x) => clamp(below(m.frames, x), 0, m.frames.length - 1);

// world x on the strand (y = 0, z = 0) that projects to screen x sx, or null
function strandX(cam, sx) {
  const p = cam.position, r = cam.r, f = cam.f, k = (sx - cam.center[0]) / cam.focal;
  const A = -(p[0] * r[0] + p[1] * r[1] + p[2] * r[2]), B = -(p[0] * f[0] + p[1] * f[1] + p[2] * f[2]);
  const den = r[0] - f[0] * k;
  if (Math.abs(den) < 1e-12) return null;
  const x = (B * k - A) / den;
  return f[0] * x + B > cam.near ? x : null;
}

const segs = { band: new Segs(), edge: new Segs(), tick: new Segs(), fine: new Segs(), axis: new Segs() };

// The strand as cam sees it. H: the cross-section's half-height (world units); grow 0..1 pulls the band out of the
// line; o.alpha fades it all; o.program 0..1 shows the program's pages.
export function drawFile(ctx, target, cam, H, ink, o = {}) {
  const m = model(ctx);
  buildTextures(ctx);
  const { grow = 1, alpha = 1, step = 2.4, program = 1, page = 1 } = o;
  const P = (x, y) => cam.project([x, y, 0]);
  for (const s of Object.values(segs)) s.clear();
  const W = ctx.size.w;
  // the visible stretch of the strand
  let xa = strandX(cam, -40), xb = strandX(cam, W + 40);
  if (xa === null) xa = m.start;
  if (xb === null) xb = m.end;
  if (xa > xb) [xa, xb] = [xb, xa];
  xa = Math.max(xa, m.start); xb = Math.min(xb, m.end);
  // the axis: the whole file, end to end
  {
    const a = P(xa, 0), b = P(xb, 0);
    if (a.visible && b.visible) segs.axis.add(a.x, a.y, b.x, b.y, 1.3, 1.3, alpha, alpha);
  }
  // the song: a column every `step` design units over the bytes it covers: as tall as the mix's level there, and
  // toned by its eight bands, lows at the foot and highs at the top (each band against its own range)
  const level = (d) => clamp((d + 34) / 26) ** 1.2;
  const tone = new Float32Array(8);
  let prev = null;
  const s0 = Math.max(P(Math.max(xa, m.audio0), 0).x, -20), s1 = Math.min(P(Math.min(xb, 0), 0).x, W + 20);
  if (xb > m.audio0 && xa < 0) {
    for (let sx = s0; sx <= s1 + 1e-6; sx += step) {
      const x0 = strandX(cam, sx - step / 2), x1 = strandX(cam, sx + step / 2), x = strandX(cam, sx);
      if (x === null || x0 === null || x1 === null) continue;
      const lo = Math.max(Math.min(x0, x1), m.audio0), hi = Math.min(Math.max(x0, x1), -1);
      if (hi < lo) continue;
      const i0 = frameAt(m, lo), i1 = frameAt(m, hi);
      let lv = 0;
      tone.fill(0);
      for (let i = i0; i <= i1; i++) {
        lv = Math.max(lv, level(m.rms[i]));
        for (let c = 0; c < 8; c++) tone[c] = Math.max(tone[c], clamp((m.band[i * 8 + c] - m.range[c][0]) / (m.range[c][1] - m.range[c][0])));
      }
      // where single bytes can be told apart the bytes are drawn instead
      const fine = 1 - smoothstep(1.5, 5, Math.abs(P(x + 1, 0).x - P(x, 0).x));
      const a = alpha * fine, h = H * grow * (0.02 + 0.98 * lv);
      const top = P(x, -h), bot = P(x, h);
      for (let c = 0; c < 8; c++) {
        const p = P(x, h - (2 * h * c) / 8), q = P(x, h - (2 * h * (c + 1)) / 8);
        segs.band.add(p.x, p.y, q.x, q.y, 1.0, 1.0, a * (0.45 + 0.55 * tone[c] ** 1.5), a * (0.45 + 0.55 * tone[c] ** 1.5));
      }
      if (prev) {
        segs.edge.add(prev[0].x, prev[0].y, top.x, top.y, 1.5, 1.5, prev[2], a);
        segs.edge.add(prev[1].x, prev[1].y, bot.x, bot.y, 1.5, 1.5, prev[2], a);
      }
      prev = [top, bot, a];
    }
  }
  // FLAC frames, once they are far enough apart to see: a tick at each frame's first byte
  {
    const fa = frameAt(m, Math.max(xa, m.audio0)), fb = frameAt(m, Math.min(xb, 0));
    if (fb - fa < 900) for (let i = fa; i <= fb; i++) {
      const x = m.frames[i], gap = Math.abs(P(m.frames[Math.min(i + 1, m.frames.length - 1)], 0).x - P(x, 0).x);
      const a = alpha * grow * smoothstep(3, 9, gap);
      if (a <= 0) continue;
      const lvl = level(m.rms[i]);
      const top = P(x, -H * (0.12 + 1.0 * lvl) * grow), bot = P(x, H * (0.12 + 1.0 * lvl) * grow);
      segs.tick.add(top.x, top.y, bot.x, bot.y, 0.9, 0.9, a, a);
    }
  }
  // the program: a tick at each entry's header, and its page of text standing on the strand
  const pages = [];
  if (xb > 0) for (const e of m.entries) {
    if (e.x1 < xa || e.x > xb) continue;
    pages.push(e);
    if (e.i === 0) continue;
    const a = P(e.x, -H * 0.95 * grow), b = P(e.x, H * 0.32 * grow);
    const gap = Math.abs(P(e.x1, 0).x - P(e.x, 0).x);
    segs.tick.add(a.x, a.y, b.x, b.y, 1.2, 1.2, alpha * smoothstep(0.4, 2, gap), alpha * smoothstep(0.4, 2, gap));
  }
  // the bytes either side of the join, once single bytes can be told apart: below the strand, each as long as its value
  {
    const bx0 = Math.max(Math.ceil(xa) - 1, -m.zipCol), bx1 = Math.min(Math.floor(xb) + 1, m.edge.length - m.zipCol - 1);
    for (let x = bx0; x <= bx1; x++) {
      const sp = Math.abs(P(x + 1, 0).x - P(x, 0).x), a = alpha * grow * smoothstep(2, 5, sp);
      if (a <= 0) continue;
      const v = m.edge[x + m.zipCol], q0 = P(x + 0.5, H * 0.08), q1 = P(x + 0.5, H * (0.08 + (0.45 * v) / 255));
      segs.fine.add(q0.x, q0.y, q1.x, q1.y, Math.min(0.8 + sp * 0.02, 1.3), Math.min(0.8 + sp * 0.02, 1.3), a * 0.8, a * 0.8);
    }
  }
  // each entry's span as its own block of tone, alternate ones a shade apart, so the 129 read as divisions
  const blocks = [];
  for (const e of pages) {
    const a = P(e.x, -H * 0.95 * grow), b = P(e.x1, -H * 0.12 * grow);
    const w = b.x - a.x;
    if (w < 0.5 || !a.visible || !b.visible || e === m.npz) continue;
    blocks.push({ x: a.x + 0.4, y: a.y, w: w - 0.8, h: b.y - a.y, color: ink.ink, alpha: alpha * program * (e.i % 2 ? 0.42 : 0.7) * (1 - smoothstep(60, 400, w)) });
  }
  ctx.g.rects(target, blocks);
  segs.band.draw(ctx, target, { color: ink.ink });
  segs.fine.draw(ctx, target, { color: ink.ink });
  segs.edge.draw(ctx, target, { color: ink.ink });
  segs.tick.draw(ctx, target, { color: ink.ink });
  segs.axis.draw(ctx, target, { color: ink.ink });
  // the join: a red rule where the song's last frame ends and the zip's first header begins
  {
    const a = P(0, -H * 1.35 * Math.max(grow, 0.05)), b = P(0, H * 1.35 * Math.max(grow, 0.05));
    if (a.visible && b.visible) ctx.g.stroke(target, [[a.x, a.y], [b.x, b.y]], { width: 2.4, color: ink.red, alpha });
  }
  // the bytes' hex digits and, below, the characters of those that print: in runs of eight bytes, each a flat card
  {
    const hx = m.hex, y0 = H * 0.62, y1 = y0 + hx.h / hx.cell;
    const sp = Math.abs(P(1, 0).x - P(0, 0).x), a = alpha * program * smoothstep(9, 16, sp);
    if (a > 0) for (let k = -hx.n; k < hx.n; k += 8) {
      if (k + 8 < xa || k > xb) continue;
      const q = [P(k, y0), P(k + 8, y0), P(k + 8, y1), P(k, y1)];
      if (!q.every((p) => p.visible)) continue;
      const u0 = (k + hx.n) / (2 * hx.n), u1 = (k + 8 + hx.n) / (2 * hx.n);
      ctx.g.mesh(target, hx.tex, q.map((p) => [p.x, p.y]), { uv: [u0, 0, u1, 1], tint: ink.ink, alpha: a });
    }
  }
  // pages: the entry's first lines, as tall as the cross-section allows, cut off at the next entry
  const top = -H * (0.14 + 0.76 * page) * grow, bottom = -H * 0.14 * grow;
  for (const e of pages) {
    if (program <= 0) break;
    if (e === m.npz) {
      // the voice's weights, a band through their picture as wide as the entry's bytes
      const span = e.x1 - e.d, ph = bottom - top;
      const q = [P(e.d, top), P(e.x1, top), P(e.x1, bottom), P(e.d, bottom)];
      if (!q.every((p) => p.visible) || Math.abs(q[1].x - q[0].x) < 1) continue;
      const aspect = Math.abs(q[1].x - q[0].x) / Math.max(Math.abs(q[3].y - q[0].y), 1);
      const rows = clamp(m.weights.w / aspect / m.weights.h, 0.02, 1), v0 = 0.5 - rows / 2;
      ctx.g.mesh(target, m.weights.tex, q.map((p) => [p.x, p.y]), { uv: [0, v0, 1, v0 + rows], tint: ink.ink, alpha: alpha * program });
      void span; void ph;
      continue;
    }
    const pg = m.pages.get(e.name);
    if (!pg) continue;
    const ph = bottom - top, pw = ph * (pg.w / pg.h), x1 = Math.min(e.d + pw, e.x1 - (e.x1 - e.d) * 0.04);
    if (x1 <= e.d) continue;
    const q = [P(e.d, top), P(x1, top), P(x1, bottom), P(e.d, bottom)];
    if (!q.every((p) => p.visible)) continue;
    if (Math.abs(q[1].x - q[0].x) < 0.6) continue;
    ctx.g.mesh(target, pg.tex, q.map((p) => [p.x, p.y]), { uv: [0, 0, (x1 - e.d) / pw, 1], tint: ink.ink, alpha: alpha * program });
  }
  return { xa, xb };
}
