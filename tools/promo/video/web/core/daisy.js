// The cover's woodcut daisy (data/daisy.json: tools/cover/woodcut.py's own marks), grown continuously.
//
//   daisy(ctx, target, {x, y, height, growth, k, alpha})
//     (x, y): the foot of the stem, design units. height: the whole woodcut (the crack's foot to the top petal).
//     growth 0..4: 0 the crack; 0-1 the stem rises from it; 1-2 each leaf unfurls from its base; 2-3 the back
//     petals open outward from the centre; 3-4 the front petals open and the disc fills.
//     k: the paper amount (default ctx.k(t) is the caller's to pass). On paper: the cover's print (black line
//     over green, yellow and white; the tints multiplied with the paper). On the stage: the line in the stage's
//     ink, no fills but a dim disc. Between, the fills come in with the inks' side.
//   daisyAnchor(ctx, {x, y, height}) -> {root, stemTop, disc: {x, y, r}} in design units (for the strand)
//
// Drawn with Canvas 2D paths at device size into a texture cached by growth (in 1/120 steps), side and size,
// placed on whole pixels: the same arguments give the same pixels.
import { side as inkSide, inks, groundAt, light, srgb as SRGB, toSrgb } from './palette.js';
import { clamp, ease } from './math.js';

const STEPS = 120, SIDE_STEPS = 32, KEEP = 48;
let prepared = null;
const cache = new Map();

function prepare(json) {
  if (prepared && prepared.json === json) return prepared;
  const [cx, cy] = json.disc_centre, R = json.disc_radius;
  const stemX = json.root[0];
  const groups = {};
  for (const g of json.groups) {
    groups[g.id] = g.marks.map((m) => {
      const path = new Path2D();
      let sx = 0, sy = 0, n = 0;
      for (const ring of m.rings) {
        ring.forEach(([x, y], i) => (i ? path.lineTo(x, y) : path.moveTo(x, y)));
        path.closePath();
        for (const [x, y] of ring) { sx += x; sy += y; n++; }
      }
      const c = [sx / n, sy / n];
      return { ...m, path, c, angle: Math.atan2(c[1] - cy, c[0] - cx), r: Math.hypot(c[0] - cx, c[1] - cy) };
    });
  }
  // the leaves: each mark to the leaf on its side of the stem; a leaf's base is its green fill's point nearest the stem
  const leaves = [-1, 1].map((sideOf) => {
    const marks = groups.leaves.filter((m) => Math.sign(m.c[0] - stemX) === sideOf);
    const green = marks.find((m) => m.ink === 'green') || marks[0];
    let base = green.rings[0][0];
    for (const ring of green.rings) for (const p of ring) if (Math.abs(p[0] - stemX) < Math.abs(base[0] - stemX)) base = p;
    return { side: sideOf, marks, base };
  });
  // petals open in order round the flower; each mark's delay from its angle
  const order = (marks) => {
    for (const m of marks) m.turn = ((m.angle + Math.PI * 2.5) % (Math.PI * 2)) / (Math.PI * 2);
  };
  order(groups.back_petals);
  const front = groups.front_petals_disc;
  for (const m of front) m.disc = m.ink === 'yellow' || (m.r < R * 1.05 && m.ink === 'black');
  order(front);
  let stemTop = 1;
  for (const m of groups.stem) for (const ring of m.rings) for (const p of ring) stemTop = Math.min(stemTop, p[1]);
  prepared = { json, groups, leaves, centre: [cx, cy], R, root: json.root, stemTop, box: json.box };
  return prepared;
}

const css = (rgb) => '#' + rgb.map((c) => Math.round(Math.min(Math.max(c, 0), 1) * 255).toString(16).padStart(2, '0')).join('');
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);

function raster(P, growth, sideAmt, k, H) {
  const box = P.box, W = Math.ceil(box.w * H) + 8, Hh = Math.ceil(box.h * H) + 8;
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = Hh;
  const c = canvas.getContext('2d');
  const base = () => c.setTransform(H, 0, 0, H, 4, 4);
  const lineInk = css(inks(k).ink.map(toSrgb));
  // the paper the tints multiply with; on the stage a tint is laid as it is (only the dim disc shows there)
  const ground = groundAt(light(k)).map(toSrgb), paper = ground.map((v) => 1 + (v - 1) * sideAmt);
  // a tint multiplies with the paper under it; white is laid over
  const fillOf = (ink) => {
    const v = hex(P.json.inks[ink]);
    return css(ink === 'white' ? v : v.map((x, i) => x * paper[i]));
  };
  const p = (stage) => clamp(growth - stage);
  const marksDo = (list, black, fn) => {
    for (const m of list) {
      if ((m.ink === 'black') !== black) continue;
      fn(m);
    }
  };
  for (const black of [false, true]) {
    const fill = (m, a) => {
      if (a <= 0) return;
      c.globalAlpha = a;
      c.fillStyle = black ? lineInk : fillOf(m.ink);
      c.fill(m.path, m.rule === 'evenodd' ? 'evenodd' : 'nonzero');
    };
    const fillA = (m) => (black ? 1 : m.ink === 'yellow' ? Math.max(sideAmt, 0.35) : sideAmt);
    // the crack
    base();
    marksDo(P.groups.crack, black, (m) => fill(m, fillA(m)));
    // the stem, rising from the crack's lip
    const ps = p(0);
    if (ps > 0) {
      c.save();
      base();
      const top = P.root[1] - ease.outCubic(ps) * (P.root[1] - P.stemTop + 0.01);
      c.beginPath();
      c.rect(-1, top, 3, 2);
      c.clip();
      marksDo(P.groups.stem, black, (m) => fill(m, fillA(m)));
      c.restore();
    }
    // the leaves, unfurling from their bases
    const pl = p(1);
    if (pl > 0) for (const leaf of P.leaves) {
      const s = ease.outCubic(pl), [bx, by] = leaf.base;
      base();
      c.translate(bx, by);
      c.rotate((1 - s) * 1.1 * leaf.side * -1);
      c.scale(Math.max(s, 1e-3), Math.max(s, 1e-3));
      c.translate(-bx, -by);
      marksDo(leaf.marks, black, (m) => fill(m, fillA(m) * clamp(pl * 4)));
    }
    // the petals, opening outward from the centre in turn round the flower
    const petal = (m, pp) => {
      const q = clamp((pp - m.turn * 0.35) / 0.65);
      if (q <= 0) return;
      const s = 0.12 + 0.88 * ease.outCubic(q), [cx, cy] = P.centre;
      base();
      c.translate(cx, cy);
      c.rotate((1 - ease.outCubic(q)) * 0.35);
      c.scale(s, s);
      c.translate(-cx, -cy);
      fill(m, fillA(m) * clamp(q * 3));
    };
    const pb = p(2);
    if (pb > 0) marksDo(P.groups.back_petals, black, (m) => petal(m, pb));
    const pf = p(3);
    if (pf > 0) marksDo(P.groups.front_petals_disc, black, (m) => {
      if (!m.disc) return petal(m, clamp(pf / 0.8));
      // the disc fills from its centre once the front petals are half open
      const q = clamp((pf - 0.45) / 0.55);
      if (q <= 0) return;
      const s = ease.outCubic(q), [cx, cy] = P.centre;
      base();
      c.translate(cx, cy);
      c.scale(s, s);
      c.translate(-cx, -cy);
      fill(m, fillA(m));
    });
  }
  return canvas;
}

export function daisy(ctx, target, { x, y, height, growth = 4, k = 1, alpha = 1 } = {}) {
  const json = ctx.data.get('daisy.json');
  const P = prepare(json);
  const { px } = ctx.g.frameOf(target);
  const H = Math.round(height * px);
  const gq = Math.round(clamp(growth, 0, 4) * STEPS) / STEPS;
  const sq = Math.round(inkSide(k) * SIDE_STEPS) / SIDE_STEPS;
  // k sets the inks (they change sides at the flip) and the paper the tints multiply with
  const kq = Math.round(clamp(k) * SIDE_STEPS) / SIDE_STEPS;
  const key = `${gq}|${kq}|${H}`;
  let hit = cache.get(key);
  if (!hit) {
    const canvas = raster(P, gq, sq, kq, H);
    hit = { tex: ctx.g.texture(canvas, { filter: 'nearest' }), w: canvas.width, h: canvas.height };
    cache.set(key, hit);
    while (cache.size > KEEP) {
      const [old, v] = cache.entries().next().value;
      cache.delete(old);
      ctx.g.deleteTexture(v.tex);
    }
  } else {
    cache.delete(key);
    cache.set(key, hit);
  }
  // the stem's foot at (x, y), on whole device pixels
  const left = Math.round((x - P.root[0] * height) * px - 4) / px, top = Math.round((y - P.root[1] * height) * px - 4) / px;
  ctx.g.rects(target, [{ x: left, y: top, w: hit.w / px, h: hit.h / px, alpha }], { texture: hit.tex, srgb: true });
}

export function daisyAnchor(ctx, { x, y, height }) {
  const P = prepare(ctx.data.get('daisy.json'));
  const at = ([u, v]) => [x + (u - P.root[0]) * height, y + (v - P.root[1]) * height];
  const [dx, dy] = at(P.centre);
  return { root: [x, y], stemTop: at([P.root[0], P.stemTop]), disc: { x: dx, y: dy, r: P.R * height } };
}

export { SRGB };
