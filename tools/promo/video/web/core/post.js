// The final pass over the composed frame: transitions between scenes, bloom on the stage only, the paper's
// fibre, a faint vignette in the dark, the highlight shoulder, and dither. Every noise here is a function of
// the pixel (in design units, so 1080p and 4K match) and the frame index.
//
//   post.transition(out, a, b, {kind: 'cut' | 'dissolve' | 'ink', k, seed, from})   a and b are scene targets
//   post.finish(src, out, {paper, raw, finish, frame, check, flip, bits})          src: linear light, out: display values
//     paper: the ground's lightness; raw: how much to pass untouched (photographs); finish: the cover's lens
//     fall-off and grain (tools/cover/finish.py)
import { GL } from './gl.js';

const NOISE = `
// integer hash -> [0, 1)
uint hash3(uvec3 v) {
  v = v * 1664525u + 1013904223u;
  v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y;
  v ^= v >> 16u;
  v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y;
  return v.x ^ v.y ^ v.z;
}
float rnd(vec2 p, float s) { return float(hash3(uvec3(ivec3(floor(p), int(s)))) & 0xffffffu) / 16777216.0; }
float vnoise(vec2 p, float s) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(rnd(i, s), rnd(i + vec2(1, 0), s), u.x), mix(rnd(i + vec2(0, 1), s), rnd(i + vec2(1, 1), s), u.x), u.y);
}
float fbm(vec2 p, float s) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 5; i++) { v += a * vnoise(p, s + float(i)); p = p * 2.03 + vec2(17.1, 9.7); a *= 0.5; }
  return v;
}`;

const FRAG_TRANSITION = `#version 300 es
precision highp float; precision highp int;
in vec2 vUv;
uniform sampler2D uA, uB;
uniform int uKind;          // 0 cut (b when k >= 0.5), 1 dissolve, 2 ink
uniform float uK, uSeed, uPx;
uniform vec2 uSize, uFrom;  // uFrom: where the ink starts, in design units
out vec4 o;
${NOISE}
vec3 toP(vec3 c) { return pow(max(c, 0.0), vec3(1.0 / 2.2)); }
vec3 fromP(vec3 c) { return pow(max(c, 0.0), vec3(2.2)); }
void main() {
  vec4 a = texture(uA, vUv), b = texture(uB, vUv);
  if (uKind == 0) { o = uK >= 0.5 ? b : a; return; }
  if (uKind == 1) {
    // a dissolve even to the eye: mixed in display-like values
    o = vec4(fromP(mix(toP(a.rgb), toP(b.rgb), uK)), 1.0);
    return;
  }
  // ink: a front spreading from uFrom, its edge shaped by fibre-scale noise, crisp to the pixel
  vec2 p = gl_FragCoord.xy / uPx;
  p.y = uSize.y / uPx - p.y;
  vec2 dsz = uSize / uPx;
  float far = length(max(abs(uFrom - vec2(0.0)), abs(uFrom - dsz))) + 60.0;
  float d = length(p - uFrom) / far;
  float n = fbm(p / 140.0, uSeed) * 0.22 + fbm(p / 26.0, uSeed + 7.0) * 0.05;
  float edge = (uK * 1.3 - 0.04) - (d + n - 0.14);
  float m = clamp(edge * far * uPx + 0.5, 0.0, 1.0);
  o = mix(a, b, m);
}`;

// soft-knee threshold into the first bloom level (13-tap with a Karis average against fireflies)
const FRAG_PREFILTER = `#version 300 es
precision highp float; precision highp int;
in vec2 vUv;
uniform sampler2D uSrc; uniform vec2 uTexel; uniform float uThreshold, uKnee;
out vec4 o;
float lum(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
vec3 bright(vec3 c) {
  float b = max(c.r, max(c.g, c.b));
  float soft = clamp(b - uThreshold + uKnee, 0.0, 2.0 * uKnee);
  soft = soft * soft / (4.0 * uKnee + 1e-5);
  return c * max(soft, b - uThreshold) / max(b, 1e-5);
}
vec3 tap(vec2 off) { return bright(texture(uSrc, vUv + off * uTexel).rgb); }
void main() {
  vec3 A = tap(vec2(-1,-1)), B = tap(vec2(1,-1)), C = tap(vec2(-1,1)), D = tap(vec2(1,1));
  vec3 E = tap(vec2(-2,-2)), F = tap(vec2(0,-2)), G = tap(vec2(2,-2)), H = tap(vec2(-2,0)), I = tap(vec2(0,0));
  vec3 J = tap(vec2(2,0)), K = tap(vec2(-2,2)), L = tap(vec2(0,2)), M = tap(vec2(2,2));
  vec3 g0 = (A+B+C+D) * 0.25, g1 = (E+F+H+I) * 0.25, g2 = (F+G+I+J) * 0.25, g3 = (H+I+K+L) * 0.25, g4 = (I+J+L+M) * 0.25;
  float w0 = 1.0 / (1.0 + lum(g0)), w1 = 1.0 / (1.0 + lum(g1)), w2 = 1.0 / (1.0 + lum(g2)), w3 = 1.0 / (1.0 + lum(g3)), w4 = 1.0 / (1.0 + lum(g4));
  vec3 c = (g0 * w0 * 0.5 + (g1 * w1 + g2 * w2 + g3 * w3 + g4 * w4) * 0.125) / (w0 * 0.5 + (w1 + w2 + w3 + w4) * 0.125);
  o = vec4(c, 1.0);
}`;
const FRAG_DOWN = `#version 300 es
precision highp float; precision highp int;
in vec2 vUv;
uniform sampler2D uSrc; uniform vec2 uTexel;
out vec4 o;
vec3 t(vec2 off) { return texture(uSrc, vUv + off * uTexel).rgb; }
void main() {
  vec3 c = (t(vec2(-1,-1)) + t(vec2(1,-1)) + t(vec2(-1,1)) + t(vec2(1,1))) * 0.125;
  c += (t(vec2(-2,-2)) + t(vec2(2,-2)) + t(vec2(-2,2)) + t(vec2(2,2))) * 0.03125;
  c += (t(vec2(0,-2)) + t(vec2(-2,0)) + t(vec2(2,0)) + t(vec2(0,2))) * 0.0625;
  c += t(vec2(0,0)) * 0.125;
  o = vec4(c, 1.0);
}`;
const FRAG_UP = `#version 300 es
precision highp float; precision highp int;
in vec2 vUv;
uniform sampler2D uSrc; uniform vec2 uTexel; uniform float uWeight;
out vec4 o;
vec3 t(vec2 off) { return texture(uSrc, vUv + off * uTexel).rgb; }
void main() {
  vec3 c = t(vec2(0,0)) * 4.0;
  c += (t(vec2(-1,0)) + t(vec2(1,0)) + t(vec2(0,-1)) + t(vec2(0,1))) * 2.0;
  c += t(vec2(-1,-1)) + t(vec2(1,-1)) + t(vec2(-1,1)) + t(vec2(1,1));
  o = vec4(c / 16.0 * uWeight, 1.0);
}`;

// the paper's fibre, baked once per size: a formation cloud and sparse short fibres, values near 0 (signed)
const FRAG_FIBRE = `#version 300 es
precision highp float; precision highp int;
in vec2 vUv;
uniform vec2 uSize; uniform float uPx;
out vec4 o;
${NOISE}
float fibres(vec2 p, float cell, float s) {
  vec2 c = floor(p / cell);
  float v = 0.0;
  for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
    vec2 q = c + vec2(i, j);
    if (rnd(q, s + 4.0) > 0.45) continue;
    float r0 = rnd(q, s), r1 = rnd(q, s + 1.0), r2 = rnd(q, s + 2.0), r3 = rnd(q, s + 3.0);
    vec2 m = (q + vec2(r0, r1)) * cell;
    float ang = r2 * 6.2831853, len = cell * (0.35 + 0.6 * r3);
    vec2 dir = vec2(cos(ang), sin(ang));
    vec2 d = p - m;
    float along = dot(d, dir), across = dot(d, vec2(-dir.y, dir.x));
    // a curved fibre: across bends with along
    across -= along * along / (len * 6.0) * (r0 - 0.5);
    float w = 0.45 + 0.5 * r3;
    float f = (1.0 - smoothstep(len * 0.3, len * 0.5, abs(along))) * (1.0 - smoothstep(0.0, w, abs(across)));
    v += f * (r1 > 0.5 ? 1.0 : -0.7);
  }
  return v;
}
void main() {
  vec2 p = gl_FragCoord.xy / uPx;
  float formation = (fbm(p / 38.0, 3.0) - 0.5) * 1.0 + (fbm(p / 9.0, 11.0) - 0.5) * 0.45;
  float f = fibres(p, 30.0, 21.0) * 0.6 + fibres(p + 7.3, 14.0, 41.0) * 0.3;
  float tooth = (vnoise(p / 1.3, 77.0) - 0.5) * 0.5 + (vnoise(p / 3.1, 78.0) - 0.5) * 0.3;
  o = vec4(formation, f, tooth, 1.0);
}`;

const FRAG_FINISH = `#version 300 es
precision highp float; precision highp int;
in vec2 vUv;
uniform sampler2D uSrc, uBloom, uFibre;
uniform vec2 uSize;
uniform float uPaper, uBloomGain, uFrame, uLevels, uFlip, uCheck, uIndex, uPx, uVignette, uFibreGain, uRaw, uFinish;
out vec4 o;
${NOISE}
vec3 toS(vec3 c) { return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c)); }
vec3 shoulder(vec3 c) {
  // identity below 0.8; light above it rolls toward 1 instead of clipping
  vec3 over = max(c - 0.8, 0.0);
  return min(c, 0.8) + 0.2 * (1.0 - exp(-over / 0.2));
}
// a standard normal per pixel and frame (Box-Muller on two hashes)
float gauss(vec2 ip, float f) {
  float u = max(rnd(ip, f * 4.0 + 101.0), 1e-7), v = rnd(ip, f * 4.0 + 102.0);
  return sqrt(-2.0 * log(u)) * cos(6.2831853 * v);
}
// the cover's grain (tools/cover/finish.py): white Gaussian noise blurred by sigma 0.6 px, scaled to std 1
float grain(vec2 ip, float f) {
  float s = 0.0, w2 = 0.0;
  for (int j = -2; j <= 2; j++) for (int i = -2; i <= 2; i++) {
    float w = exp(-float(i * i + j * j) / (2.0 * 0.36));
    s += w * gauss(ip + vec2(i, j), f);
    w2 += w * w;
  }
  return s / sqrt(w2);
}
void main() {
  vec2 frag = vec2(gl_FragCoord.x, uFlip > 0.5 ? uSize.y - gl_FragCoord.y : gl_FragCoord.y);
  vec2 uv = frag / uSize;
  // the frame index, as 16 cells in the top rows: black 0, white 1, then a white and a black guard
  if (uCheck > 0.5) {
    float cell = floor(uSize.x / 18.0), rows = max(floor(8.0 * uPx), 4.0);
    float yTop = uSize.y - frag.y;
    if (yTop < rows && frag.x < cell * 18.0) {
      int k = int(frag.x / cell);
      float bit = k < 16 ? mod(floor(uIndex / pow(2.0, float(15 - k))), 2.0) : (k == 16 ? 1.0 : 0.0);
      o = vec4(vec3(bit), 1.0);
      return;
    }
  }
  vec3 c = texture(uSrc, uv).rgb;
  vec3 rawC = c;
  float dark = 1.0 - uPaper;
  c += texture(uBloom, uv).rgb * uBloomGain * dark * dark;
  // the paper's fibre: formation and fibres in the sheet, fixed to the page (not to the screen's grain)
  vec3 fib = texture(uFibre, uv).rgb;
  float paperTex = (fib.x * 0.016 + fib.y * 0.010 + fib.z * 0.012) * uFibreGain;
  c *= 1.0 + paperTex * smoothstep(0.5, 1.0, uPaper);
  // a faint vignette, on the stage only
  vec2 q = (uv - 0.5) * vec2(uSize.x / uSize.y, 1.0);
  c *= 1.0 - uVignette * dark * smoothstep(0.35, 1.05, length(q));
  c = shoulder(c);
  // raw: a photographic frame passes without the grade, bloom, fibre or vignette
  c = mix(c, rawC, uRaw);
  // the cover's finish: the lens's fall-off in light (r = 1 at the corners), then its grain in display values
  vec2 hr = (frag - uSize * 0.5) / (uSize * 0.5);
  c *= mix(1.0, 1.0 - 0.16 * pow(length(hr) / sqrt(2.0), 2.4), uFinish);
  vec3 s = toS(clamp(c, 0.0, 1.0));
  if (uFinish > 0.0) s += uFinish * 0.006 * grain(floor(frag), uFrame);
  // triangular dither of one step, a function of the pixel and the frame
  vec2 ip = floor(frag);
  float n = rnd(ip, uFrame * 2.0 + 1.0) + rnd(ip + 0.5, uFrame * 2.0 + 2.0) - 1.0;
  s = s + n / uLevels;
  o = vec4(clamp(s, 0.0, 1.0), 1.0);
}`;

export class Post {
  constructor(g) {
    this.g = g;
    this.levels = [];
    this.fibre = null;
    this.bloomGain = 0.55;
    this.threshold = 1.0;
    this.knee = 0.5;
    this.vignette = 0.22;
    this.fibreGain = 1.0;
  }

  resize(w, h) {
    const g = this.g;
    for (const t of this.levels) g.free(t);
    this.levels = [];
    let lw = w, lh = h;
    for (let i = 0; i < 6 && lw > 8 && lh > 8; i++) {
      lw = Math.max(Math.floor(lw / 2), 1); lh = Math.max(Math.floor(lh / 2), 1);
      this.levels.push(g.target(lw, lh, { float: true }));
    }
    if (this.fibre) g.free(this.fibre);
    this.fibre = g.target(w, h, { float: true });
    g.pass(this.fibre, g.program('post:fibre', FRAG_FIBRE), { uPx: h / GL_DESIGN_H });
    this.w = w; this.h = h;
  }

  transition(out, a, b, { kind = 'dissolve', k = 0, seed = 1, from = null } = {}) {
    const g = this.g, px = out.h / GL_DESIGN_H;
    const KIND = { cut: 0, dissolve: 1, ink: 2 }[kind];
    if (KIND === undefined) throw new Error(`post: transition ${kind}`);
    g.pass(out, g.program('post:transition', FRAG_TRANSITION), {
      uA: a, uB: b, uKind: KIND, uK: k, uSeed: seed, uPx: px, uFrom: from || [0, out.h / px],
    });
  }

  bloom(src) {
    const g = this.g, L = this.levels;
    g.pass(L[0], g.program('post:prefilter', FRAG_PREFILTER), { uSrc: src, uTexel: [1 / src.w, 1 / src.h], uThreshold: this.threshold, uKnee: this.knee });
    const down = g.program('post:down', FRAG_DOWN), up = g.program('post:up', FRAG_UP);
    for (let i = 1; i < L.length; i++) g.pass(L[i], down, { uSrc: L[i - 1], uTexel: [1 / L[i - 1].w, 1 / L[i - 1].h] });
    // up the chain, each level added into the one above: wide levels give the long, faint falloff of light
    for (let i = L.length - 1; i > 0; i--) g.pass(L[i - 1], up, { uSrc: L[i], uTexel: [1 / L[i].w, 1 / L[i].h], uWeight: 1.0 }, { blend: 'add' });
    return L[0];
  }

  finish(src, out, { paper = 0, raw = 0, finish = 0, frame = 0, check = false, flip = false, bits = 8 } = {}) {
    const g = this.g;
    const bloom = paper < 0.999 ? this.bloom(src) : this.levels[0];
    if (paper >= 0.999) g.clear(this.levels[0], [0, 0, 0, 1]);
    const t = out || g.screen;
    g.pass(out, g.program('post:finish', FRAG_FINISH), {
      uSrc: src, uBloom: bloom, uFibre: this.fibre, uPaper: paper, uBloomGain: this.bloomGain / this.levels.length,
      uFrame: frame, uLevels: 2 ** bits - 1, uFlip: flip ? 1 : 0, uCheck: check ? 1 : 0, uIndex: frame,
      uPx: t.h / GL_DESIGN_H, uVignette: this.vignette, uFibreGain: this.fibreGain, uRaw: raw, uFinish: finish,
    });
  }
}

const GL_DESIGN_H = 1080;
export { GL };
