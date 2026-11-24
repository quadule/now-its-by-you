// The throat's envelope as a field of hairlines receding in depth: one line per 5 ms frame, the newest nearest,
// each hiding what is behind it (a fill under every line writes depth), drawn in two instanced calls from a
// texture of the levels. World: x across the 128 points (high to low: the camera's right is -x, so low is on the left), y up is -y (the core camera's up), z back.
import { dataTexture, depthLayer, freeLayer, camUniforms, CAMERA_GLSL, strips } from './gpu.js';

const COMMON = `#version 300 es
precision highp float; precision highp int;
uniform sampler2D uLev;
uniform float uNow, uRate, uWX, uHY, uSpeed, uFlat, uZ0, uNear, uFar, uWidth, uNewWidth, uBack, uSub;
uniform int uEvery, uRow0, uRows, uSegs;
uniform vec2 uDesign; uniform float uPx;
${CAMERA_GLSL}
float lev(int row, float q) {
  int i = int(floor(q)); float f = q - float(i);
  float a = texelFetch(uLev, ivec2(clamp(i - 1, 0, 127), row), 0).r;
  float b = texelFetch(uLev, ivec2(clamp(i, 0, 127), row), 0).r;
  float c = texelFetch(uLev, ivec2(clamp(i + 1, 0, 127), row), 0).r;
  float d = texelFetch(uLev, ivec2(clamp(i + 2, 0, 127), row), 0).r;
  return 0.5 * (2.0 * b + (-a + c) * f + (2.0 * a - 5.0 * b + 4.0 * c - d) * f * f + (-a + 3.0 * b - 3.0 * c + d) * f * f * f);
}
// line l's frame, its age in seconds and its row in the texture
int frameOf(int l) { return int(floor(uNow)) - l * uEvery; }
float ageOf(int l) { return (uNow - float(frameOf(l))) / uRate; }
vec3 world(int l, float q, bool base) {
  int row = clamp(frameOf(l) - uRow0, 0, uRows - 1);
  float h = base ? 0.0 : max(lev(row, q), 0.0) * uHY * uFlat;
  return vec3((0.5 - q / 127.0) * uWX, -h, uZ0 + ageOf(l) * uSpeed);  // low on the left
}
float depthOf(float z) { return clamp((z - uNear) / (uFar - uNear), 0.0, 1.0) * 2.0 - 1.0; }
vec2 toClip(vec2 p) { vec2 c = p / uDesign * 2.0 - 1.0; return vec2(c.x, -c.y); }
`;

const VERT_FILL = `${COMMON}
void main() {
  int l = gl_InstanceID / uSegs, s = gl_InstanceID % uSegs;
  float q = (float(s) + ((gl_VertexID & 1) == 1 ? 1.0 : 0.0)) / uSub;
  bool base = gl_VertexID >= 2;
  vec3 p = project(world(l, q, base));
  if (p.z < uNear) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  gl_Position = vec4(toClip(p.xy), depthOf(p.z), 1.0);
}`;
const FRAG_FILL = `#version 300 es
precision highp float;
uniform vec3 uGround; out vec4 o;
void main() { o = vec4(uGround, 1.0); }`;

const VERT_LINE = `${COMMON}
uniform float uFogNear, uFogFar, uBias, uDense;
out vec2 vP; flat out vec2 vA; flat out vec2 vB; flat out vec4 vRA; flat out int vNew;
void main() {
  int l = gl_InstanceID / uSegs, s = gl_InstanceID % uSegs;
  vec3 p0 = project(world(l, float(s) / uSub, false)), p1 = project(world(l, float(s + 1) / uSub, false));
  if (p0.z < uNear || p1.z < uNear) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  float age = ageOf(l);
  float w = l == 0 ? uNewWidth : uWidth;
  float r0 = 0.5 * w * uFocal / p0.z, r1 = 0.5 * w * uFocal / p1.z;     // design units
  float fog = 1.0 - smoothstep(uFogNear, uFogFar, age);
  float a = fog * (1.0 - smoothstep(uBack * 0.8, uBack, age));
  // where lines pack closer than a few pixels they fade, so the dense far field reads as a sheet, not as moire
  vec3 n0 = project(world(l + 1, float(s) / uSub, false));
  float gap = length(n0.xy - p0.xy) * uPx;
  a *= l == 0 ? 1.0 : mix(uDense, 1.0, smoothstep(0.6, 4.0, gap));
  vec2 A = p0.xy * uPx, B = p1.xy * uPx;
  float r = max(max(r0, r1) * uPx, 0.5) + 1.0;
  vec2 d = B - A; float len = length(d);
  vec2 u = len > 1e-5 ? d / len : vec2(1.0, 0.0), n = vec2(-u.y, u.x);
  vec2 corner = vec2((gl_VertexID & 1) == 1 ? 1.0 : -1.0, gl_VertexID >= 2 ? 1.0 : -1.0);
  vec2 P = mix(A - u * r, B + u * r, corner.x * 0.5 + 0.5) + n * r * corner.y;
  vP = P; vA = A; vB = B; vRA = vec4(r0 * uPx, r1 * uPx, a, a); vNew = l == 0 ? 1 : 0;
  float z = mix(p0.z, p1.z, corner.x * 0.5 + 0.5);
  gl_Position = vec4(toClip(P / uPx), depthOf(z) - uBias, 1.0);
}`;
const FRAG_LINE = `#version 300 es
precision highp float; precision highp int;
in vec2 vP; flat in vec2 vA; flat in vec2 vB; flat in vec4 vRA; flat in int vNew;
uniform vec3 uColor, uNewColor; out vec4 o;
void main() {
  vec2 pa = vP - vA, ba = vB - vA;
  float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
  float r = mix(vRA.x, vRA.y, h);
  float d = length(pa - ba * h) - max(r, 0.5);
  float cov = clamp(0.5 - d, 0.0, 1.0) * min(2.0 * r, 1.0) * vRA.z;
  if (cov <= 0.0) discard;
  o = vec4((vNew == 1 ? uNewColor : uColor) * cov, cov);
}`;
const FRAG_COMP = `#version 300 es
precision highp float;
in vec2 vUv; uniform sampler2D uSrc; uniform float uAlpha; out vec4 o;
void main() { o = texture(uSrc, vUv) * uAlpha; }`;

export class Ridge {
  // levels: Float32Array [rows, 128] (0..~1.15), row 0 is frame row0 at `rate` frames a second
  constructor(g, levels, rows, row0, rate) {
    this.g = g; this.rows = rows; this.row0 = row0; this.rate = rate;
    this.tex = dataTexture(g.gl, 128, rows, levels, 'r32f');
    this.layer = null;
  }

  _layer(t) {
    const gl = this.g.gl;
    if (!this.layer || this.layer.w !== t.w || this.layer.h !== t.h) {
      freeLayer(gl, this.layer);
      this.layer = depthLayer(gl, t.w, t.h);
    }
    return this.layer;
  }

  // now: the frame (fractional) of the newest line; count lines, `every` frames apart
  draw(target, cam, o) {
    const g = this.g, gl = g.gl, t = target || g.screen;
    const L = this._layer(t);
    const { px, design } = g.frameOf(t);
    gl.bindFramebuffer(gl.FRAMEBUFFER, L.fb);
    gl.viewport(0, 0, L.w, L.h);
    gl.disable(gl.SCISSOR_TEST);
    gl.clearColor(0, 0, 0, 0); gl.clearDepth(1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const sub = o.sub ?? 3, segs = 127 * sub;
    const u = {
      uLev: this.tex, uNow: o.now, uRate: this.rate, uWX: o.wx, uHY: o.hy, uSpeed: o.speed, uFlat: o.flat ?? 1, uZ0: o.z0 ?? 0,
      uNear: cam.near, uFar: o.far ?? 200, uWidth: o.width, uNewWidth: o.newWidth ?? o.width, uBack: o.back,
      uSub: sub, uEvery: o.every ?? 1, uRow0: this.row0, uRows: this.rows, uSegs: segs, uDesign: design, uPx: px,
      ...camUniforms(cam),
    };
    gl.enable(gl.DEPTH_TEST);
    // the fills: opaque ground under every line, writing depth
    if (o.fill !== false) {
      gl.depthFunc(gl.LESS); gl.depthMask(true);
      g.blend('none');
      g.program('s02:ridge-fill', FRAG_FILL, VERT_FILL).set({ ...u, uGround: o.ground });
      strips(g, o.count * segs);
    }
    // the lines, a hair nearer than their own fill
    gl.depthFunc(gl.LEQUAL); gl.depthMask(false);
    g.blend('over');
    g.program('s02:ridge-line', FRAG_LINE, VERT_LINE).set({
      ...u, uFogNear: o.fog[0], uFogFar: o.fog[1], uBias: 2e-5, uDense: o.dense ?? 0.3, uColor: o.color, uNewColor: o.newColor,
    });
    strips(g, o.count * segs);
    gl.depthMask(true);
    gl.disable(gl.DEPTH_TEST);
    g.pass(t, g.program('s02:ridge-comp', FRAG_COMP), { uSrc: L.tex, uAlpha: o.alpha ?? 1 }, { blend: 'over' });
  }
}
