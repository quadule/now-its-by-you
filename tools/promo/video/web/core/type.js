// Type for the film: Georgia as the private family `Film Serif`, set with Canvas 2D into cached textures
// rasterised at the frame's device size and placed on whole pixels, so letters are as sharp as the browser draws them.
//
// Roles
//   lyric    the sung line: the book face, sentence case
//   label    letterspaced small capitals (labels from copy.json), as the house sets its kickers and rubrics;
//            Georgia's old-style figures sit at the small capitals' height
//   numeral  figures in equal-width cells, so a counting number does not shimmy
//
//   await type.ready()
//   const s = type.text('THE SONG', {role: 'label', size: 22})     -> sprite {w, h, ascent, ...} in design units
//   type.draw(target, s, x, y, {color, alpha, align, valign, ground})
//   const lay = type.lyric(line, {size, maxWidth, focus})          -> {sprite, rows, syllables: [{x, y, w, h, t0, t1, text, focus}]}
//     focus: null (default) | 'italic' | 'red': sets the timeline's focus syllables (the leaned-on word) apart
//   type.drawLyric(target, lay, t, x, y, {ink, lit, focusInk, ground, align})   lights the sung syllables, sweeping across each
//
// `ground` is the colour under the text (linear). Coverage is blended as the browser blends text on a page
// (in display values), so light-on-dark and dark-on-light letters keep the same weight.
import { toSrgb } from './palette.js';

export const FAMILY = 'Film Serif';
const FACES = [
  { url: '/fonts/Georgia.ttf', style: 'normal', weight: '400' },
  { url: '/fonts/Georgiai.ttf', style: 'italic', weight: '400' },
  { url: '/fonts/Georgiab.ttf', style: 'normal', weight: '700' },
];
const ROLE = {
  lyric: { tracking: 0, italic: false, weight: 400, caps: 'normal', case: (s) => s },
  label: { tracking: 0.14, italic: false, weight: 400, caps: 'all-small-caps', case: (s) => s },
  numeral: { tracking: 0, italic: false, weight: 400, caps: 'normal', case: (s) => s },
};
const PAD = 4; // device px around each sprite

const FRAG_TEXT = `#version 300 es
precision highp float; precision highp int;
in vec2 vLocal; in vec4 vColor; in vec2 vUv;
uniform sampler2D uTex;
uniform vec3 uInk, uLit, uGround, uFocus;  // linear; uFocus: the ink of focus syllables drawn red in the sprite
uniform float uAlpha;
uniform vec4 uLitX;                    // per row: the lit edge in sprite px (left of it is lit)
uniform vec4 uRowEdge;                 // per row: its bottom in sprite px (rows top to bottom)
uniform vec2 uSprite;                  // sprite size in px
vec3 toS(vec3 c) { return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c)); }
vec3 toL(vec3 c) { return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
void main() {
  vec4 tx = texture(uTex, vUv);
  float cov = tx.a;
  float focus = cov > 0.0 ? 1.0 - tx.g : 0.0;
  vec2 p = vUv * uSprite;
  int row = p.y < uRowEdge.x ? 0 : p.y < uRowEdge.y ? 1 : p.y < uRowEdge.z ? 2 : 3;
  float edge = row == 0 ? uLitX.x : row == 1 ? uLitX.y : row == 2 ? uLitX.z : uLitX.w;
  float lit = clamp(edge - p.x + 0.5, 0.0, 1.0);
  vec3 ink = mix(mix(uInk, uFocus, focus), uLit, lit);
  // the blend a page makes in display values, expressed as a linear-light coverage over the known ground
  vec3 gs = toS(uGround), is = toS(ink);
  vec3 want = toL(mix(gs, is, cov));
  vec3 d = ink - uGround;
  vec3 k = vec3(abs(d.r) > 1e-4 ? (want.r - uGround.r) / d.r : cov, abs(d.g) > 1e-4 ? (want.g - uGround.g) / d.g : cov,
                abs(d.b) > 1e-4 ? (want.b - uGround.b) / d.b : cov);
  float a = clamp(dot(k, vec3(0.2126, 0.7152, 0.0722)), 0.0, 1.0) * uAlpha;
  o = vec4(ink * a, a);
}`.replace('void main', 'out vec4 o;\nvoid main');

export class Type {
  constructor(g) {
    this.g = g;
    this.cache = new Map();
    this.ground = [0, 0, 0];
    this.canvas = document.createElement('canvas');
    this.c2d = this.canvas.getContext('2d', { willReadFrequently: false });
  }

  async ready() {
    if (this._ready) return this._ready;
    this._ready = (async () => {
      for (const f of FACES) {
        const face = new FontFace(FAMILY, `url(${f.url})`, { style: f.style, weight: f.weight });
        document.fonts.add(await face.load());
      }
      await document.fonts.ready;
      for (const f of FACES) {
        const spec = `${f.style === 'italic' ? 'italic ' : ''}${f.weight} 20px "${FAMILY}"`;
        if (!document.fonts.check(spec)) throw new Error(`type: ${spec} did not load`);
      }
    })();
    return this._ready;
  }

  font(size, { italic = false, weight = 400 } = {}) {
    return `${italic ? 'italic ' : ''}${weight} ${size}px "${FAMILY}"`;
  }

  // a run of text set at device size; returns a cached sprite. size in design units.
  text(str, opts = {}) {
    const role = ROLE[opts.role || 'lyric'];
    const o = { ...role, ...opts };
    const px = this.g.frameOf(opts.target || null).px * (opts.oversample || 1);
    const text = role.case(String(str));
    const key = JSON.stringify([text, o.role, o.size, o.italic, o.weight, o.tracking, o.caps, px]);
    if (this.cache.has(key)) return this.cache.get(key);
    const size = o.size * px, c = this.c2d;
    c.font = this.font(size, o);
    c.letterSpacing = `${o.tracking * size}px`;
    c.fontVariantCaps = o.caps;
    c.fontKerning = 'normal';
    c.textRendering = 'optimizeLegibility';
    const glyphs = o.role === 'numeral' ? this._numeralLayout(text, size) : null;
    const m = c.measureText(text);
    const width = glyphs ? glyphs.width : m.width - o.tracking * size;
    const ascent = Math.ceil(c.measureText('Hdfl').fontBoundingBoxAscent ?? size * 0.9);
    const descent = Math.ceil(c.measureText('gjpy').fontBoundingBoxDescent ?? size * 0.25);
    const W = Math.ceil(width) + PAD * 2, H = ascent + descent + PAD * 2;
    this.canvas.width = W; this.canvas.height = H;
    c.font = this.font(size, o);
    c.letterSpacing = `${o.tracking * size}px`;
    c.fontVariantCaps = o.caps;
    c.fillStyle = '#fff';
    c.textBaseline = 'alphabetic';
    if (glyphs) for (const gph of glyphs.list) c.fillText(gph.ch, PAD + gph.x, PAD + ascent);
    else c.fillText(text, PAD, PAD + ascent);
    const tex = this.g.texture(this.canvas, { filter: opts.oversample > 1 ? 'linear' : 'nearest', mips: opts.oversample > 1 });
    const sprite = {
      tex, text, px, pw: W, ph: H, w: W / px, h: H / px, pad: PAD / px, ascent: ascent / px, descent: descent / px,
      width: width / px, size: o.size, rows: [{ edge: H }],
    };
    this.cache.set(key, sprite);
    return sprite;
  }

  _numeralLayout(text, size) {
    const c = this.c2d;
    let cell = 0;
    for (const d of '0123456789') cell = Math.max(cell, c.measureText(d).width);
    const list = [];
    let x = 0;
    for (const ch of text) {
      const w = c.measureText(ch).width;
      if (/[0-9]/.test(ch)) { list.push({ ch, x: x + (cell - w) / 2 }); x += cell; } else { list.push({ ch, x }); x += w; }
    }
    return { list, width: x };
  }

  // where a sprite's top-left lands for an anchor at (x, y)
  place(sprite, x, y, { align = 'left', valign = 'baseline' } = {}) {
    const ox = align === 'center' ? sprite.width / 2 : align === 'right' ? sprite.width : 0;
    const oy = valign === 'top' ? 0 : valign === 'middle' ? sprite.ascent * 0.62 : valign === 'bottom' ? sprite.ascent + sprite.descent : sprite.ascent;
    return [x - ox - sprite.pad, y - oy - sprite.pad];
  }

  draw(target, sprite, x, y, opts = {}) {
    const { color = [1, 1, 1], lit = color, focusInk = color, alpha = 1, ground = this.ground, litX = [-1, -1, -1, -1], snap = true } = opts;
    const [lx, ly] = this.place(sprite, x, y, opts);
    const g = this.g, gl = g.gl;
    const { px, design } = g.frameOf(g.use(target));
    // whole device pixels for crisp letters; a sprite rasterised at another scale is drawn scaled and filtered
    const s = px / sprite.px, X = snap ? Math.round(lx * px) / px : lx, Y = snap ? Math.round(ly * px) / px : ly;
    const edges = sprite.rows.map((r) => r.edge);
    while (edges.length < 4) edges.push(1e9);
    const lits = litX.slice();
    while (lits.length < 4) lits.push(-1);
    g.blend('over');
    const prog = g.program('text', FRAG_TEXT, VERT_TEXT);
    prog.set({
      uDesign: design, uPx: px, uTex: sprite.tex, uInk: color, uLit: lit, uFocus: focusInk, uGround: ground, uAlpha: alpha,
      uLitX: lits, uRowEdge: edges, uSprite: [sprite.pw, sprite.ph],
    });
    const data = new Float32Array([X, Y, sprite.pw / sprite.px * (opts.scale || 1), sprite.ph / sprite.px * (opts.scale || 1), 1, 1, 1, 1, 0, 0, 1, 1]);
    g._instanced(12, [4, 4, 4], data, 1);
    return { x: X + sprite.pad, y: Y + sprite.pad, w: sprite.width, h: sprite.ascent + sprite.descent, s };
  }

  // A sung line laid out in rows no wider than maxWidth; each syllable's rect, relative to the anchor's top left.
  // focus: null (default), 'italic' (the timeline's focus syllables, the line's leaned-on word, set in italic)
  // or 'red' (marked in the sprite so drawLyric gives them its focusInk). Runs of one style are set whole, so
  // kerning holds inside each run.
  lyric(line, { size = 46, maxWidth = 1500, leading = 1.32, italic = false, focus = null } = {}) {
    const px = this.g.frameOf(null).px;
    const key = JSON.stringify(['lyric', line.section, line.i, line.text, size, maxWidth, leading, italic, focus, px]);
    if (this.cache.has(key)) return this.cache.get(key);
    const c = this.c2d, S = size * px;
    const styleOf = (s) => ({ it: italic !== (focus === 'italic' && !!s.focus), red: focus === 'red' && !!s.focus });
    const setFont = (it) => { c.font = this.font(S, { italic: it }); c.letterSpacing = '0px'; c.fontVariantCaps = 'normal'; c.fontKerning = 'normal'; };
    const measure = (text, it) => { setFont(it); return c.measureText(text).width; };
    // pieces: each syllable, and a space between words (in the style of the word before it)
    const words = line.words.map((w) => w.syllables.map((s) => ({ text: s.text, syl: s, ...styleOf(s) })));
    const wordWidth = (w) => runsOf(w).reduce((x, r) => x + measure(r.text, r.it), 0);
    function runsOf(pieces) {
      const runs = [];
      for (const p of pieces) {
        const last = runs[runs.length - 1];
        if (last && last.it === p.it && last.red === p.red) { last.text += p.text; last.pieces.push(p); } else runs.push({ text: p.text, it: p.it, red: p.red, pieces: [p] });
      }
      return runs;
    }
    const rows = [[]];
    let x = 0;
    const space = measure(' ', italic);
    for (const w of words) {
      const ww = wordWidth(w);
      if (x > 0 && x + space + ww > maxWidth * px) { rows.push([]); x = 0; }
      const row = rows[rows.length - 1];
      if (row.length) row.push({ ...row[row.length - 1], text: ' ', syl: null });
      row.push(...w);
      x += (x > 0 ? space : 0) + ww;
    }
    setFont(italic);
    const ascent = Math.ceil(c.measureText('Hdfl').fontBoundingBoxAscent ?? S * 0.9);
    const descent = Math.ceil(c.measureText('gjpy').fontBoundingBoxDescent ?? S * 0.25);
    const lead = Math.round(S * leading);
    const rowRuns = rows.map((r) => runsOf(r));
    const widths = rowRuns.map((rr) => rr.reduce((x, r) => x + measure(r.text, r.it), 0));
    const W = Math.ceil(Math.max(...widths)) + PAD * 2, H = ascent + descent + lead * (rows.length - 1) + PAD * 2;
    this.canvas.width = W; this.canvas.height = H;
    c.textBaseline = 'alphabetic';
    const syllables = [], rowInfo = [];
    rowRuns.forEach((rr, ri) => {
      const base = PAD + ascent + lead * ri;
      let rx = 0;
      for (const run of rr) {
        setFont(run.it);
        c.fillStyle = run.red ? '#f00' : '#fff';
        c.fillText(run.text, PAD + rx, base);
        // each syllable's extent from the measured prefix of its run
        let prefix = '';
        for (const p of run.pieces) {
          const x0 = c.measureText(prefix).width;
          prefix += p.text;
          const x1 = c.measureText(prefix).width;
          if (p.syl) {
            const s = p.syl;
            syllables.push({ text: s.text, t0: s.t0, t1: s.t1, pitch: s.pitch, focus: s.focus, row: ri,
              px0: PAD + rx + x0, px1: PAD + rx + x1, x: (rx + x0) / px, w: (x1 - x0) / px, y: (lead * ri) / px, h: (ascent + descent) / px });
          }
        }
        rx += c.measureText(run.text).width;
      }
      rowInfo.push({ edge: base + descent + (ri < rows.length - 1 ? (lead - ascent - descent) / 2 : PAD), width: widths[ri] / px, baseline: (lead * ri + ascent) / px });
    });
    const tex = this.g.texture(this.canvas, { filter: 'nearest' });
    const sprite = { tex, px, pw: W, ph: H, w: W / px, h: H / px, pad: PAD / px, ascent: ascent / px, descent: descent / px,
      width: Math.max(...widths) / px, size, rows: rowInfo };
    const lay = { sprite, rows: rowInfo, syllables, line, width: sprite.width, height: (ascent + descent + lead * (rows.length - 1)) / px };
    this.cache.set(key, lay);
    return lay;
  }

  // the lit edge per row at t: syllables already sung are lit; the one being sung fills across its duration
  litEdges(lay, t) {
    const edges = lay.rows.map(() => -1);
    for (const s of lay.syllables) {
      if (t < s.t0) continue;
      const k = Math.min((t - s.t0) / Math.max(s.t1 - s.t0, 1e-3), 1);
      edges[s.row] = Math.max(edges[s.row], s.px0 + (s.px1 - s.px0) * k);
    }
    // a row is lit to its end once a later row has begun
    for (let r = 0; r < edges.length - 1; r++) if (edges[r + 1] >= 0) edges[r] = 1e9;
    return edges;
  }

  // the syllable being sung at t, with its rect relative to the layout's anchor, or null
  current(lay, t) {
    return lay.syllables.find((s) => t >= s.t0 && t < s.t1) || null;
  }

  drawLyric(target, lay, t, x, y, { ink, lit, focusInk = ink, alpha = 1, ground = this.ground, align = 'left' } = {}) {
    const ox = align === 'center' ? lay.width / 2 : align === 'right' ? lay.width : 0;
    return this.draw(target, lay.sprite, x - ox, y, { color: ink, lit, focusInk, alpha, ground, valign: 'top', litX: this.litEdges(lay, t) });
  }

  clear() {
    for (const s of this.cache.values()) this.g.deleteTexture((s.sprite || s).tex);
    this.cache.clear();
  }
}

const VERT_TEXT = `#version 300 es
layout(location=0) in vec2 corner;
layout(location=1) in vec4 box;
layout(location=2) in vec4 color;
layout(location=3) in vec4 uv;
uniform vec2 uDesign; uniform float uPx;
out vec2 vLocal; out vec4 vColor; out vec2 vUv;
void main() {
  vec2 c01 = corner * 0.5 + 0.5;
  vec2 p = box.xy * uPx + box.zw * uPx * c01;
  vLocal = c01; vUv = mix(uv.xy, uv.zw, c01); vColor = color;
  vec2 clip = p / (uDesign * uPx) * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
}`;

export { toSrgb };
