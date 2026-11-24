// The sung line's clearing: a panel of the block left uncut round the line of type, as a woodcut leaves it. Each row
// of the lyric's box with a margin, its edge softened evenly, as a mask (r: 1 where the hatching is cleared).
import { smoothstep } from '../../core/math.js';

// a gaussian along one axis (uDir: one texel along it)
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

export const LYRIC = { size: 46, y: 860, maxWidth: 1500 };
const MARGIN = [16, 9], SOFT = 5;   // design units

// the sung line's opacity at t, as core/draw.js lyric() fades it, times the scene's own
export function lyricAlpha(ctx, t, line, extra = 1) {
  return extra * smoothstep(line.t0 - 0.35, line.t0 - 0.1, t) * (1 - smoothstep(line.t1 + 0.25, line.t1 + 0.6, t));
}

export class Halo {
  constructor() { this.size = null; }

  _targets(ctx, target) {
    const t = target || ctx.g.screen;
    if (this.size && this.size[0] === t.w && this.size[1] === t.h) return;
    if (this.a) { ctx.g.free(this.a); ctx.g.free(this.b); }
    this.a = ctx.g.target(t.w, t.h, { float: false });
    this.b = ctx.g.target(t.w, t.h, { float: false });
    this.size = [t.w, t.h];
  }

  // the mask for the line sung at t (null when none shows); alpha: the scene's own fade of the line
  mask(ctx, t, target, { focus = 'italic', alpha = 1, y = LYRIC.y } = {}) {
    const line = ctx.timeline.line(t);
    if (!line) return null;
    const a = lyricAlpha(ctx, t, line, alpha);
    if (a <= 0) return null;
    this._targets(ctx, target);
    const g = ctx.g;
    g.clear(this.a, [0, 0, 0, 0]);
    const lay = ctx.type.lyric(line, { size: LYRIC.size, maxWidth: LYRIC.maxWidth, focus });
    const x0 = ctx.size.w / 2 - lay.width / 2, sp = lay.sprite;
    const boxes = lay.rows.map((r) => ({
      x: x0 - MARGIN[0], y: y + r.baseline - sp.ascent - MARGIN[1],
      w: r.width + 2 * MARGIN[0], h: sp.ascent + sp.descent + 2 * MARGIN[1], color: [1, 1, 1], alpha: a,
    }));
    g.rects(this.a, boxes);
    const px = this.a.h / 1080, s = SOFT * px, prog = g.program('s09:blur', BLUR);
    g.pass(this.b, prog, { uSrc: this.a, uDir: [1 / this.a.w, 0], uS: s });
    g.pass(this.a, prog, { uSrc: this.b, uDir: [0, 1 / this.a.h], uS: s });
    return this.a;
  }
}
