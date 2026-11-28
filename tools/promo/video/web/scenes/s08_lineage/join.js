// The join, full frame: at byte 12,588,764 the song's last bytes end and the program's first file begins.
// Left of the red rule the audio's last 704 bytes as a wall of hex, receding left through the camera into the
// song's band; right of it __main__.py as the zip holds it, line for line, its first line large. Laid out in page units (the 1920 x 1080 frame) and drawn at any scale about the
// rule's point, so the dive into the strand can land on it.
import { Segs } from './lines.js';
import { model } from './file.js';
import { clamp, mix } from '../../core/math.js';

export const RULE = [800, 540];         // where the join sits on the page
const WALL = { near: 785, far: 250, top: 150, bottom: 930, farTop: 425, farBottom: 655, cols: 32, rows: 22 };
const PAGE = { x0: 830, x1: 1880, y0: 162, y1: 930 };
const FAMILY = '"Film Serif"';
const segs = new Segs();
let J = null;

function build(ctx) {
  const m = model(ctx);
  if (J && J.m === m) return J;
  const g = ctx.g, px = Math.max(ctx.size.px, 1) * 1.5;
  // the wall's glyphs: the 256 bytes' two hex digits, an atlas of 16 x 16 cells
  const C = 64, atlas = document.createElement('canvas');
  atlas.width = atlas.height = 16 * C;
  let c = atlas.getContext('2d');
  c.fillStyle = '#fff'; c.font = `400 ${C * 0.62}px ${FAMILY}`; c.textAlign = 'center'; c.textBaseline = 'middle';
  for (let v = 0; v < 256; v++) c.fillText(v.toString(16).padStart(2, '0'), (v % 16) * C + C / 2, Math.floor(v / 16) * C + C / 2);
  // the page: real source, as __main__.py has it, line for line: its first line large, then the lines that follow,
  // each cut at the page's edge
  const W = Math.round((PAGE.x1 - PAGE.x0) * px), H = Math.round((PAGE.y1 - PAGE.y0) * px);
  const page = document.createElement('canvas');
  page.width = W; page.height = H;
  c = page.getContext('2d');
  c.fillStyle = '#fff'; c.textBaseline = 'alphabetic';
  const main = (m.entries.find((e) => e.name === '__main__.py')?.text || '').replace(/\t/g, '    ').split('\n');
  const S = (v) => v * px;
  c.font = `italic 400 ${S(19)}px ${FAMILY}`;
  c.fillText('__main__.py', 0, S(22));
  c.font = `400 ${S(44)}px ${FAMILY}`;
  c.fillText(main[0].replace(/^"""/, ''), 0, S(80));
  c.font = `400 ${S(22)}px ${FAMILY}`;
  let y = S(80 + 44);
  for (const line of main.slice(1)) {
    if (y > H - S(4)) break;
    c.fillText(line, 0, y);
    y += S(29);
  }
  J = { m, atlas: g.texture(atlas, { mips: true }),
    page: { tex: g.texture(page, { mips: true }), w: W, h: H } };
  return J;
}

// the join at scale s about the screen point at (where the rule's point lands), alpha a
export function drawJoin(ctx, target, ink, { s = 1, at = RULE, alpha = 1, k } = {}) {
  const j = build(ctx), m = j.m;
  const T = (x, y) => [at[0] + (x - RULE[0]) * s, at[1] + (y - RULE[1]) * s];
  if (alpha <= 0 || s < 0.004) return;
  // the song's band, receding into the wall: the whole mix, compressed, its height growing toward the wall
  segs.clear();
  const nf = m.frames.length;
  for (let x = 0; x <= WALL.far; x += 1.6) {
    const u = x / WALL.far, i = Math.min(Math.floor(u * nf), nf - 1);
    const lv = clamp((m.rms[i] + 34) / 26) ** 1.2;
    const half = mix(10, (WALL.farBottom - WALL.farTop) / 2, u ** 1.5) * (0.08 + 0.92 * lv);
    const [ax, ay] = T(x, 440 - half), [bx, by] = T(x, 440 + half);
    segs.add(ax, ay, bx, by, 0.9 * Math.max(s, 0.3), 0.9 * Math.max(s, 0.3), alpha, alpha);
  }
  segs.draw(ctx, target, { color: ink.ink });
  // the wall, in perspective: each byte where its place falls, at its depth's size, never stretched
  {
    const n = WALL.cols * WALL.rows, from = m.zipCol - n;
    const zf = (WALL.bottom - WALL.top) / (WALL.farBottom - WALL.farTop), my = (WALL.top + WALL.bottom) / 2, myf = (WALL.farTop + WALL.farBottom) / 2;
    const rh = (WALL.bottom - WALL.top) / WALL.rows, cells = [];
    for (let k = 0; k < WALL.cols; k++) {
      const z = mix(zf, 1, k / (WALL.cols - 1)), w = (1 / z - 1 / zf) / (1 - 1 / zf);
      const x = mix(WALL.far, WALL.near - 16, w), cy = mix(myf, my, w), sz = (rh * 0.95) / z;
      for (let r = 0; r < WALL.rows; r++) {
        const v = m.edge[from + r * WALL.cols + k], [px, py] = T(x, cy + (r - (WALL.rows - 1) / 2) * (rh / z));
        cells.push({ x: px - (sz * s) / 2, y: py - (sz * s) / 2, w: sz * s, h: sz * s, color: ink.ink, alpha: alpha * mix(0.55, 1, w),
          uv: [(v % 16) / 16, Math.floor(v / 16) / 16, (v % 16 + 1) / 16, (Math.floor(v / 16) + 1) / 16] });
      }
    }
    ctx.g.rects(target, cells, { texture: j.atlas });
  }
  // the page
  const p = [T(PAGE.x0, PAGE.y0), T(PAGE.x1, PAGE.y0), T(PAGE.x1, PAGE.y1), T(PAGE.x0, PAGE.y1)];
  ctx.g.mesh(target, j.page.tex, p, { tint: ink.ink, alpha });
  // the rule, from under the lyric to the foot
  for (const [a, b] of [[168, 1100]]) {
    const [rx, ry0] = T(RULE[0] + 0.5, a), [, ry1] = T(RULE[0] + 0.5, b);
    ctx.g.stroke(target, [[rx, Math.max(ry0, -10)], [rx, Math.min(ry1, ctx.size.h + 10)]], { width: 2.2, color: ink.red, alpha });
  }
  void k;
}
