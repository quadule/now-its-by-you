// Every weight of the singer, one cell each (throat/weights: 886,372 in a 1020 x 984 picture as singer_picture.py lays
// them out), lit by what each adds at this moment: the weight times the one number of act-verse1 it is multiplied by
// (s02/weights-index), amount clip(|w x input| / scale, 0, 1) ** 0.8 with singer_picture's per-array scale; at rest a
// cell shows its weight's size alone (0.06 + 0.22 x clip(|w| / size)). Amber adds, cold takes away.
//
// Pass 1 lights the picture into a texture, one texel a weight; each smaller level of its chain keeps the colour of
// the brightest of the four texels under it, at the geometric mean of that brightness and the four's mean. Pass 2 draws it on a plane: a homography from the frame to the picture's cells, so
// the same pass draws it in perspective through the camera or laid flat. At every size the picture is a field of
// round points at least a few pixels apart: one a weight close up, and further off one for each block of weights,
// lit as that reduction says. The plane repeats the picture as a grid of identical copies (every copy
// reads the same texture, so all flicker alike).
import { dataTexture, mipTarget } from './gpu.js';

export const COLS = 1020, ROWS = 984;
const BIAS = 65535, ZERO = 65534, NONE = 65533;

// half-float bits to a number
const F16 = (() => {
  const exp = new Float32Array(32);
  for (let e = 0; e < 32; e++) exp[e] = 2 ** (e - 15);
  return (h) => {
    const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 31, m = h & 1023;
    if (e === 0) return s * m * 2 ** -24;
    if (e === 31) return m ? NaN : s * Infinity;
    return s * exp[e] * (1 + m / 1024);
  };
})();

const FRAG_LIGHT = `#version 300 es
precision highp float; precision highp int;
uniform sampler2D uW, uAct;
uniform float uRow, uLit, uRest;
uniform int uRows;
uniform vec3 uInk, uPos, uNeg, uGround;
uniform float uGlow, uCurve;
out vec4 o;
vec3 toS(vec3 c) { return mix(c * 12.92, 1.055 * pow(max(c, 0.0), vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c)); }
vec3 toL(vec3 c) { return mix(c / 12.92, pow((max(c, 0.0) + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
float act(int row, int col) { return texelFetch(uAct, ivec2(col, clamp(row, 0, uRows - 1)), 0).r; }
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  vec4 w = texelFetch(uW, p, 0);            // weight, its column (or a mark), light scale, size scale
  if (w.g > 65532.5) { o = vec4(0.0); return; }
  float m;
  if (w.g > 65534.5) m = 1.0;
  else if (w.g > 65533.5) m = 0.0;
  else {
    int r0 = int(floor(uRow)); float f = uRow - float(r0); int c = int(w.g + 0.5);
    m = mix(act(r0, c), act(r0 + 1, c), f);
  }
  float c = w.r * m;
  float amount = pow(clamp(abs(c) / w.b, 0.0, 1.0), 0.8) * uLit;
  float shown = pow(amount, uCurve);       // singer_picture's amount, steepened for the frame so light reads as light
  float rest = (0.06 + 0.22 * clamp(abs(w.r) / w.a, 0.0, 1.0)) * uRest;
  // as singer_picture.py mixes them, in display values: the ground inked by the weight's size, then lit
  vec3 lit = c > 0.0 ? uPos : uNeg;
  vec3 base = toS(uGround) + (toS(uInk) - toS(uGround)) * rest;
  vec3 col = toL(base + (toS(min(lit, 1.0)) - base) * shown) + lit * shown * shown * uGlow;
  o = vec4(col, 1.0);
}`;

const FRAG_REDUCE = `#version 300 es
precision highp float; precision highp int;
uniform sampler2D uSrc; uniform ivec2 uSrcSize;
out vec4 o;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy) * 2;
  // the brightest of the four keeps its colour (amber adds, cold takes away: never mixed to grey), at the geometric
  // mean of its brightness and the four's mean brightness, so a block lit throughout stays bright and one lone lit
  // weight fades as the block grows
  vec4 best = vec4(0.0); float lb = 0.0, sum = 0.0, cov = 0.0;
  for (int dy = 0; dy < 2; dy++) for (int dx = 0; dx < 2; dx++) {
    vec4 v = texelFetch(uSrc, min(p + ivec2(dx, dy), uSrcSize - 1), 0);
    float l = dot(v.rgb, vec3(0.2126, 0.7152, 0.0722));
    sum += l; cov += v.a;
    if (l >= lb) { lb = l; best = v; }
  }
  float k = lb > 1e-6 ? sqrt((sum * 0.25) / lb) : 0.0;
  o = vec4(best.rgb * k, cov * 0.25);
}`;

const FRAG_SHOW = `#version 300 es
precision highp float; precision highp int;
in vec2 vUv;
uniform sampler2D uLitTex;
uniform mat3 uH;                 // frame (design units) -> picture cells (u across, v down)
uniform vec2 uSize; uniform float uPx;
uniform vec2 uPitch;             // cells from one copy to the next
uniform vec2 uGrid;              // copies kept either side of the original (i, j)
uniform float uKeep;             // copies further than this many rings from the original are dark
uniform float uAlpha, uMaskY0, uMaskY1, uMask, uCopies, uTop0, uTop1, uFar0, uFar1, uLevels, uSpace;
uniform vec2 uRowsIn;            // the rows of the picture drawn (the fold draws each half by itself)
out vec4 o;
vec4 points(vec2 l, float foot, int L) {
  float s = exp2(float(L));
  vec2 c = l / s, cell = floor(c), d = c - cell - 0.5;
  ivec2 size = textureSize(uLitTex, L);
  if (cell.x >= float(size.x) || cell.y >= float(size.y)) return vec4(0.0);
  vec4 v = texelFetch(uLitTex, ivec2(cell), L);
  float f = foot / s;                                                 // texels of this level a pixel covers
  float cov = clamp((0.36 - length(d)) / max(f, 1e-4) + 0.5, 0.0, 1.0);
  return v * cov;
}
void main() {
  vec2 sp = vec2(gl_FragCoord.x, uSize.y - gl_FragCoord.y) / uPx;     // design units, y down
  vec3 q = uH * vec3(sp, 1.0);
  if (q.z <= 0.0) { o = vec4(0.0); return; }
  vec2 c = q.xy / q.z;
  vec2 k = floor((c + 0.5 * (uPitch - vec2(${COLS}.0, ${ROWS}.0))) / uPitch);  // which copy
  vec2 fw = fwidth(c);
  float foot = max(fw.x, fw.y);                                       // cells a pixel covers
  if (abs(k.x) > uGrid.x || abs(k.y) > uGrid.y) { o = vec4(0.0); return; }
  float ring = max(abs(k.x), abs(k.y));
  float off = clamp(ring - uKeep, 0.0, 1.0);
  vec2 l = c - k * uPitch;                                            // cells within this copy
  if (l.x < 0.0 || l.y < uRowsIn.x || l.x >= ${COLS}.0 || l.y >= min(uRowsIn.y, ${ROWS}.0)) { o = vec4(0.0); return; }
  // the level whose texels are at least uSpace pixels apart, cross-faded with the next
  float lv = clamp(log2(max(foot * uSpace, 1.0)), 0.0, uLevels - 2.0);
  int L0 = int(floor(lv));
  vec4 col = mix(points(l, foot, L0), points(l, foot, L0 + 1), smoothstep(0.0, 1.0, lv - float(L0)));
  float a = uAlpha * (1.0 - off) * (ring == 0.0 ? 1.0 : uCopies);
  a *= 1.0 - uMask * smoothstep(uMaskY0, uMaskY1, sp.y);
  a *= smoothstep(uTop0, uTop1, sp.y);
  a *= 1.0 - smoothstep(uFar0, uFar1, foot);
  o = col * a;
}`;

// the homography taking 4 points src[i] = [x, y] to dst[i]: a 3x3 (row-major) solving the 8 equations
export function homography(src, dst) {
  const A = [], b = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i], [u, v] = dst[i];
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v);
  }
  for (let c = 0; c < 8; c++) {                       // Gauss-Jordan with partial pivoting
    let p = c;
    for (let r = c + 1; r < 8; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
    [A[c], A[p]] = [A[p], A[c]]; [b[c], b[p]] = [b[p], b[c]];
    for (let r = 0; r < 8; r++) {
      if (r === c) continue;
      const f = A[r][c] / A[c][c];
      for (let k = c; k < 8; k++) A[r][k] -= f * A[c][k];
      b[r] -= f * b[c];
    }
  }
  const h = b.map((v, i) => v / A[i][i]);
  return [h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7], 1];
}

export class Weights {
  static async load(ctx) {
    const w = new Weights();
    await w.init(ctx);
    return w;
  }

  async init(ctx) {
    const gl = ctx.gl, d = ctx.data;
    const [wb, ab, actHead] = await Promise.all([d.bytes('throat/weights.bin'), d.bytes('throat/act-verse1.bin'),
      d.json('throat/act-verse1.json')]);
    const idx = d.get('s02/weights-index').raw, arr = d.get('s02/weights-array').raw;
    const arrays = d.get('s02/weights-arrays.json').arrays;
    const wbits = new Uint16Array(wb);
    const px = new Float32Array(COLS * ROWS * 4);
    let n = 0;
    for (let i = 0; i < COLS * ROWS; i++) {
      const col = idx[i];
      px[i * 4 + 1] = col;
      if (col === NONE) continue;
      const a = arrays[arr[i]];
      px[i * 4] = F16(wbits[i]);
      px[i * 4 + 2] = Math.max(a.light, 1e-9);
      px[i * 4 + 3] = Math.max(a.size, 1e-9);
      n++;
    }
    if (n !== 886372) throw new Error(`s02: ${n} weights, not 886,372`);
    this.count = n;
    this.W = dataTexture(gl, COLS, ROWS, px, 'rgba32f');
    this.actRows = actHead.shape[0];
    this.actRate = actHead.rate; this.actT0 = actHead.t0;
    this.Act = dataTexture(gl, actHead.shape[1], actHead.shape[0], new Uint16Array(ab), 'r16f');
    this.lit = mipTarget(gl, COLS, ROWS);
  }

  // light the picture for song time t (the act rows either side, mixed)
  light(ctx, t, { ground, ink, pos, neg, lit = 1, rest = 1, glow = 0.6, curve = 1 }) {
    const g = ctx.g, gl = g.gl;
    const row = Math.min(Math.max((t - this.actT0) * this.actRate - 0.5, 0), this.actRows - 1);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.lit.fb);
    gl.viewport(0, 0, COLS, ROWS);
    gl.disable(gl.SCISSOR_TEST);
    g.blend('none');
    const p = g.program('s02:weights-light', FRAG_LIGHT).set({
      uW: this.W, uAct: this.Act, uRow: row, uRows: this.actRows, uLit: lit, uRest: rest, uInk: ink, uPos: pos, uNeg: neg, uGround: ground, uGlow: glow, uCurve: curve,
    });
    void p;
    gl.bindVertexArray(g._vaoEmpty);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    // the chain: each level the brightest of the four texels under it (sampling only the level above while writing)
    const L = this.lit, red = g.program('s02:weights-reduce', FRAG_REDUCE);
    for (let l = 1; l < L.levels; l++) {
      gl.bindTexture(gl.TEXTURE_2D, L.tex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_BASE_LEVEL, l - 1);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAX_LEVEL, l - 1);
      gl.bindFramebuffer(gl.FRAMEBUFFER, L.fbs[l]);
      gl.viewport(0, 0, L.sizes[l][0], L.sizes[l][1]);
      red.set({ uSrc: L.tex, uSrcSize: L.sizes[l - 1] });
      gl.bindVertexArray(g._vaoEmpty);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    gl.bindTexture(gl.TEXTURE_2D, L.tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_BASE_LEVEL, 0);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAX_LEVEL, L.levels - 1);
  }

  // draw the lit picture through H (frame -> cells, row-major 3x3)
  show(ctx, target, H, { pitch = [COLS + 90, ROWS + 150], grid = [0, 0], keep = 1e3, alpha = 1, mask = 0, maskY = [800, 850],
    copies = 1, top = [-2, -1], far = [1e5, 2e5], rows = [0, ROWS], space = 2.6 } = {}) {
    const g = ctx.g;
    // GLSL mat3 is column-major
    const M = [H[0], H[3], H[6], H[1], H[4], H[7], H[2], H[5], H[8]];
    const { px } = g.frameOf(target || g.screen);
    g.pass(target, g.program('s02:weights-show', FRAG_SHOW), {
      uLitTex: this.lit.tex, uH: M, uPx: px, uPitch: pitch, uGrid: grid, uKeep: keep, uAlpha: alpha,
      uMask: mask, uMaskY0: maskY[0], uMaskY1: maskY[1], uCopies: copies, uTop0: top[0], uTop1: top[1],
      uFar0: far[0], uFar1: far[1], uLevels: this.lit.levels, uSpace: space, uRowsIn: rows,
    }, { blend: 'over' });
  }
}
