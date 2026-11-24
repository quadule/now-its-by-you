// Many separate hairlines in one draw: the same anti-aliased segments and page-like blend as g.stroke, but a list
// of independent segments (a hatch, ticks, a tree's twigs) instead of one polyline. Overlaps inside one call do
// not double: coverage is max-combined in a mask, then tinted once.
//
//   const s = new Segs();  s.add(x0, y0, x1, y1, w0, w1, a0, a1);  s.draw(ctx, target, {color, intensity, blend})
import { PERCEPTUAL } from '../../core/gl.js';

const VERT = `#version 300 es
layout(location=0) in vec2 corner;
layout(location=1) in vec4 seg;
layout(location=2) in vec4 ra;
uniform vec2 uDesign; uniform float uPx;
out vec2 vP; flat out vec2 vA; flat out vec2 vB; flat out vec4 vRA;
void main() {
  vec2 a = seg.xy * uPx, b = seg.zw * uPx;
  float r = max(max(ra.x, ra.y) * uPx, 0.5) + 1.0;
  vec2 d = b - a; float len = length(d);
  vec2 u = len > 1e-5 ? d / len : vec2(1.0, 0.0), n = vec2(-u.y, u.x);
  vec2 p = mix(a - u * r, b + u * r, corner.x * 0.5 + 0.5) + n * r * corner.y;
  vP = p; vA = a; vB = b; vRA = vec4(ra.xy * uPx, ra.zw);
  vec2 clip = p / (uDesign * uPx) * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
}`;
const FRAG = `#version 300 es
precision highp float;
in vec2 vP; flat in vec2 vA; flat in vec2 vB; flat in vec4 vRA;
out vec4 o;
void main() {
  vec2 pa = vP - vA, ba = vB - vA;
  float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
  float r = mix(vRA.x, vRA.y, h);
  float d = length(pa - ba * h) - max(r, 0.5);
  float cov = clamp(0.5 - d, 0.0, 1.0) * min(2.0 * r, 1.0);
  o = vec4(cov * mix(vRA.z, vRA.w, h));
}`;
const TINT = `#version 300 es
precision highp float;
uniform sampler2D uMask; uniform vec4 uColor; uniform vec2 uSize; uniform vec3 uGround; uniform int uPerceptual;
out vec4 o;
${PERCEPTUAL}
void main() {
  float m = texture(uMask, gl_FragCoord.xy / uSize).r;
  if (uPerceptual == 1 && m > 0.0 && m < 1.0) m = perceptual(m, uColor.rgb / max(uColor.a, 1e-4), uGround);
  o = uColor * m;
}`;

export class Segs {
  constructor(cap = 4096) {
    this.data = new Float32Array(cap * 8);
    this.n = 0;
    this.box = [Infinity, Infinity, -Infinity, -Infinity, 0];
  }

  clear() { this.n = 0; this.box = [Infinity, Infinity, -Infinity, -Infinity, 0]; return this; }

  // a segment from (x0, y0) to (x1, y1), widths w0, w1 (design units), alphas a0, a1
  add(x0, y0, x1, y1, w0 = 1, w1 = w0, a0 = 1, a1 = a0) {
    if (!(a0 > 0 || a1 > 0)) return;
    if (this.n * 8 >= this.data.length) {
      const d = new Float32Array(this.data.length * 2);
      d.set(this.data);
      this.data = d;
    }
    this.data.set([x0, y0, x1, y1, w0 / 2, w1 / 2, a0, a1], this.n * 8);
    this.n++;
    const b = this.box;
    b[0] = Math.min(b[0], x0, x1); b[1] = Math.min(b[1], y0, y1); b[2] = Math.max(b[2], x0, x1); b[3] = Math.max(b[3], y0, y1);
    b[4] = Math.max(b[4], w0, w1);
  }

  // a polyline as segments: pts [[x, y], ...], width and alpha numbers or (i) -> value
  line(pts, width = 1, alpha = 1) {
    const W = typeof width === 'function' ? width : () => width, A = typeof alpha === 'function' ? alpha : () => alpha;
    for (let i = 0; i + 1 < pts.length; i++) this.add(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], W(i), W(i + 1), A(i), A(i + 1));
  }

  draw(ctx, target, { color = [0, 0, 0], intensity = 1, blend = 'over' } = {}) {
    if (!this.n) return;
    const g = ctx.g, gl = g.gl, t = target || g.screen, { px, design } = g.frameOf(t), b = this.box;
    const pad = b[4] * px + 3;
    const sx = Math.max(Math.floor(b[0] * px - pad), 0), sy = Math.max(Math.floor(t.h - (b[3] * px + pad)), 0);
    const sw = Math.min(Math.ceil(b[2] * px + pad), t.w) - sx, sh = Math.min(Math.ceil(t.h - (b[1] * px - pad)), t.h) - sy;
    if (sw <= 0 || sh <= 0) return;
    const mask = g._mask8(t);
    g.use(mask);
    gl.enable(gl.SCISSOR_TEST);
    gl.scissor(sx, sy, sw, sh);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    g.blend('max');
    g.program('s08:segs', FRAG, VERT).set({ uDesign: design, uPx: px });
    g._instanced(8, [4, 4], this.data.subarray(0, this.n * 8), this.n);
    const c = [color[0] * intensity, color[1] * intensity, color[2] * intensity, blend === 'add' ? 0 : 1];
    g.use(t);
    g.blend(blend);
    gl.scissor(sx, sy, sw, sh);
    g.program('s08:tint', TINT).set({ uMask: mask, uColor: c, uSize: [t.w, t.h], uGround: g.ground, uPerceptual: blend === 'over' ? 1 : 0 });
    gl.bindVertexArray(g._vaoEmpty);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.disable(gl.SCISSOR_TEST);
  }
}
