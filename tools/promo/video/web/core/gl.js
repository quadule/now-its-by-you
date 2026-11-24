// WebGL2 for the film: programs, targets, a fullscreen pass, and the drawing primitives every scene uses.
//
// Coordinates: scenes draw in design units, a frame 1080 high (1920 wide at 16:9), y down, origin top left.
// `gl.px` is device pixels per design unit, so a 4K render is the 1080p frame drawn at twice the detail.
// Colours are linear light, premultiplied by alpha. Values over 1 are light (they bloom on the stage).
// Edges drawn 'over' are blended as ink on a page over `g.ground` (the colour beneath, set by draw.ground()).
//
//   const g = new GL(canvas)
//   g.target(w, h, {float: true})            -> {fb, tex, w, h}      a render target (RGBA16F or RGBA8)
//   g.use(target) / g.clear(target, rgba)
//   g.program(key, fragSource, vertSource?)   cached; p.set({uName: value}) by the uniforms' own types
//   g.pass(target, program, uniforms, {blend})  a fullscreen triangle
//   g.stroke(target, points, opts)           the strand: a thick anti-aliased polyline (see stroke below)
//   g.points(target, list, opts)             anti-aliased discs: [{x, y, r, color, alpha, soft}]
//   g.rects(target, list, opts)              filled rectangles, optional texture: [{x, y, w, h, color, alpha, uv}]
//   g.mesh(target, tex, grid, opts)          an image over a warped grid (cols x rows points) or 4 corners in perspective
//   g.texture(source, opts) / g.upload(tex, source)  textures from Canvas 2D, ImageBitmap or typed arrays

const VERT_FULL = `#version 300 es
out vec2 vUv;
void main() {
  vec2 p = vec2(gl_VertexID == 1 ? 3.0 : -1.0, gl_VertexID == 2 ? 3.0 : -1.0);
  vUv = p * 0.5 + 0.5;
  gl_Position = vec4(p, 0.0, 1.0);
}`;

// a segment p0-p1 with radii r0, r1 (device px) and alphas a0, a1; drawn as a quad around it
const VERT_SEG = `#version 300 es
layout(location=0) in vec2 corner;
layout(location=1) in vec4 seg;      // p0.xy, p1.xy in design units
layout(location=2) in vec4 ra;       // r0, r1 (design units), a0, a1
uniform vec2 uDesign;                // the frame in design units
uniform float uPx;                   // device px per design unit
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
const FRAG_SEG = `#version 300 es
precision highp float; precision highp int;
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

// Coverage blended as a page blends ink: in display values over the ground under it, expressed as a
// linear-light alpha, so a dark line on paper keeps the weight a light line has on the stage.
export const PERCEPTUAL = `
vec3 toS_(vec3 c) { return mix(c * 12.92, 1.055 * pow(max(c, 0.0), vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c)); }
vec3 toL_(vec3 c) { return mix(c / 12.92, pow((max(c, 0.0) + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
float perceptual(float cov, vec3 ink, vec3 ground) {
  vec3 ic = min(ink, 1.0);
  vec3 want = toL_(mix(toS_(ground), toS_(ic), cov));
  vec3 d = ic - ground;
  vec3 k = vec3(abs(d.r) > 1e-3 ? (want.r - ground.r) / d.r : cov, abs(d.g) > 1e-3 ? (want.g - ground.g) / d.g : cov,
                abs(d.b) > 1e-3 ? (want.b - ground.b) / d.b : cov);
  return clamp(dot(k, vec3(0.2126, 0.7152, 0.0722)), 0.0, 1.0);
}`;

// coverage (from the max-blended mask) tinted into the target
const FRAG_TINT = `#version 300 es
precision highp float; precision highp int;
uniform sampler2D uMask; uniform vec4 uColor; uniform vec2 uSize; uniform vec3 uGround; uniform int uPerceptual;
out vec4 o;
${PERCEPTUAL}
void main() {
  float m = texture(uMask, gl_FragCoord.xy / uSize).r;
  if (uPerceptual == 1 && m > 0.0 && m < 1.0) m = perceptual(m, uColor.rgb / max(uColor.a, 1e-4), uGround);
  o = uColor * m;
}`;

const VERT_INST = `#version 300 es
layout(location=0) in vec2 corner;
layout(location=1) in vec4 box;      // x, y, w, h (design units) for a rect; cx, cy, r, soft for a disc
layout(location=2) in vec4 color;    // linear, premultiplied
layout(location=3) in vec4 uv;       // u0, v0, u1, v1
uniform vec2 uDesign; uniform float uPx; uniform int uDisc; uniform int uSnap;
out vec2 vLocal; out vec4 vColor; out vec2 vUv; flat out vec2 vR;
void main() {
  vec2 p;
  vec2 c01 = corner * 0.5 + 0.5;
  if (uDisc == 1) {
    float r = box.z * uPx, sigma = max(r * 1.6, 2.0) * box.w, pad = 3.0 * sigma + 1.5;
    vec2 c = box.xy * uPx;
    vLocal = corner * (r + pad);
    vR = vec2(r, sigma);
    p = c + vLocal;
  } else {
    vec2 o = box.xy * uPx, s = box.zw * uPx;
    if (uSnap == 1) { o = floor(o + 0.5); }
    p = o + s * c01;
    vLocal = c01 * s; vR = s;
  }
  vUv = mix(uv.xy, uv.zw, c01);
  vColor = color;
  vec2 clip = p / (uDesign * uPx) * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
}`;
const FRAG_DISC = `#version 300 es
precision highp float; precision highp int;
in vec2 vLocal; in vec4 vColor; flat in vec2 vR;
uniform vec3 uGround; uniform int uPerceptual;
out vec4 o;
${PERCEPTUAL}
void main() {
  float d = length(vLocal) - max(vR.x, 0.5);
  float cov = clamp(0.5 - d, 0.0, 1.0) * min(2.0 * vR.x, 1.0);
  if (uPerceptual == 1 && cov > 0.0 && cov < 1.0 && vColor.a > 0.0) cov = perceptual(cov, vColor.rgb / vColor.a, uGround);
  // soft: a halo beyond the edge (vR.y is its width in px), gone well inside the quad
  float halo = vR.y > 0.0 ? 0.35 * exp(-pow(max(d, 0.0) / vR.y, 2.0)) * (1.0 - cov) : 0.0;
  o = vColor * (cov + halo);
}`;
// a texel as linear light, premultiplied: srgb 1 for images and Canvas 2D drawings (unpremultiplied sRGB values)
const TEXEL = `
vec4 texel(sampler2D t, vec2 uv, int srgb) {
  vec4 c = texture(t, uv);
  if (srgb == 1) return vec4(toL_(c.rgb) * c.a, c.a);
  return c;
}`;
const FRAG_RECT = `#version 300 es
precision highp float; precision highp int;
in vec2 vLocal; in vec4 vColor; in vec2 vUv;
uniform sampler2D uTex; uniform int uTextured, uSrgb;
out vec4 o;
${PERCEPTUAL}
${TEXEL}
void main() {
  vec4 c = vColor;
  if (uTextured == 1) c *= texel(uTex, vUv, uSrgb);
  o = c;
}`;

// a textured triangle mesh: positions in design units, texture coordinates per vertex
const VERT_MESH = `#version 300 es
layout(location=0) in vec2 pos;
layout(location=1) in vec3 uvq;      // u, v, q: q is 1 except where a 4-corner quad is drawn in perspective
uniform vec2 uDesign; uniform float uPx;
out vec3 vUvq;
void main() {
  vUvq = uvq;
  vec2 clip = pos / uDesign * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
}`;
const FRAG_MESH = `#version 300 es
precision highp float; precision highp int;
in vec3 vUvq;
uniform sampler2D uTex; uniform int uSrgb; uniform float uAlpha; uniform vec3 uTint;
out vec4 o;
${PERCEPTUAL}
${TEXEL}
void main() { o = texel(uTex, vUvq.xy / vUvq.z, uSrgb) * vec4(uTint, 1.0) * uAlpha; }`;

const SETTERS = {
  0x1406: 'uniform1f', 0x8b50: 'uniform2fv', 0x8b51: 'uniform3fv', 0x8b52: 'uniform4fv',
  0x1404: 'uniform1i', 0x8b53: 'uniform2iv', 0x8b54: 'uniform3iv', 0x8b55: 'uniform4iv', 0x8b56: 'uniform1i',
  0x8b5a: 'uniformMatrix2fv', 0x8b5b: 'uniformMatrix3fv', 0x8b5c: 'uniformMatrix4fv',
  0x8b5e: 'sampler', 0x8b5f: 'sampler', 0x8dc1: 'sampler', 0x8b60: 'sampler',
};

export const DESIGN_H = 1080;

export class GL {
  constructor(canvas, { preserve = false } = {}) {
    const gl = canvas.getContext('webgl2', {
      antialias: false, alpha: false, depth: false, stencil: false, premultipliedAlpha: true,
      preserveDrawingBuffer: preserve, powerPreference: 'high-performance', desynchronized: false,
    });
    if (!gl) throw new Error('WebGL2 is not available');
    this.gl = gl;
    this.canvas = canvas;
    this.floatOK = !!gl.getExtension('EXT_color_buffer_float');
    gl.getExtension('EXT_color_buffer_half_float');
    gl.getExtension('OES_texture_float_linear');
    this.floatBlend = !!gl.getExtension('EXT_float_blend');
    this.programs = new Map();
    this.textures = new Set();
    this.design = [1920, DESIGN_H];
    this.px = 1;
    this._quad = this._buffer(new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]));
    this._inst = gl.createBuffer();
    this._vaoEmpty = gl.createVertexArray();
    this._mask = null;
    this.screen = { fb: null, w: canvas.width, h: canvas.height, screen: true };
    // the colour under what is drawn next (linear), for edges blended as on a page; draw.ground() sets it
    this.ground = [0, 0, 0];
  }

  // the frame's device size: sets px and the design width from the aspect
  size(w, h) {
    this.canvas.width = w; this.canvas.height = h;
    this.screen.w = w; this.screen.h = h;
    this.px = h / DESIGN_H;
    this.design = [w / this.px, DESIGN_H];
    if (this._mask) { this.free(this._mask); this._mask = null; }
  }

  _buffer(data) {
    const gl = this.gl, b = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, b);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    return b;
  }

  // a render target; float: RGBA16F (linear light, values over 1 kept), else RGBA8
  target(w, h, { float = true, filter = 'linear', format } = {}) {
    const gl = this.gl;
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    const f = filter === 'nearest' ? gl.NEAREST : gl.LINEAR;
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, f);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, f);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const fmt = format || (float ? 'rgba16f' : 'rgba8');
    const spec = {
      rgba16f: [gl.RGBA16F, gl.RGBA, gl.HALF_FLOAT], rgba32f: [gl.RGBA32F, gl.RGBA, gl.FLOAT],
      rgba8: [gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE], rgb10a2: [gl.RGB10_A2, gl.RGBA, gl.UNSIGNED_INT_2_10_10_10_REV],
      r8: [gl.R8, gl.RED, gl.UNSIGNED_BYTE],
    }[fmt];
    gl.texStorage2D(gl.TEXTURE_2D, 1, spec[0], w, h);
    const fb = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    const status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
    if (status !== gl.FRAMEBUFFER_COMPLETE) throw new Error(`target ${fmt} ${w}x${h} incomplete: 0x${status.toString(16)}`);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return { fb, tex, w, h, format: fmt };
  }

  free(target) {
    const gl = this.gl;
    if (target.fb) gl.deleteFramebuffer(target.fb);
    if (target.tex) gl.deleteTexture(target.tex);
  }

  use(target) {
    const gl = this.gl, t = target || this.screen;
    gl.bindFramebuffer(gl.FRAMEBUFFER, t.fb);
    gl.viewport(0, 0, t.w, t.h);
    return t;
  }

  clear(target, rgba = [0, 0, 0, 0]) {
    const gl = this.gl;
    this.use(target);
    gl.disable(gl.SCISSOR_TEST);
    gl.clearColor(rgba[0], rgba[1], rgba[2], rgba[3] ?? 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
  }

  blend(mode) {
    const gl = this.gl;
    if (!mode || mode === 'none') { gl.disable(gl.BLEND); return; }
    gl.enable(gl.BLEND);
    gl.blendEquation(mode === 'max' ? gl.MAX : gl.FUNC_ADD);
    if (mode === 'over') gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    else if (mode === 'add' || mode === 'max') gl.blendFunc(gl.ONE, gl.ONE);
    else if (mode === 'multiply') gl.blendFunc(gl.DST_COLOR, gl.ONE_MINUS_SRC_ALPHA);
    else throw new Error(`blend ${mode}`);
  }

  program(key, frag, vert = VERT_FULL) {
    if (this.programs.has(key)) return this.programs.get(key);
    const gl = this.gl;
    const sh = (type, src) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        const lines = src.split('\n').map((l, i) => `${i + 1}: ${l}`).join('\n');
        throw new Error(`shader ${key}: ${gl.getShaderInfoLog(s)}\n${lines}`);
      }
      return s;
    };
    const p = gl.createProgram();
    gl.attachShader(p, sh(gl.VERTEX_SHADER, vert));
    gl.attachShader(p, sh(gl.FRAGMENT_SHADER, frag));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(`program ${key}: ${gl.getProgramInfoLog(p)}`);
    const uniforms = {};
    let unit = 0;
    const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i++) {
      const info = gl.getActiveUniform(p, i);
      const name = info.name.replace(/\[0\]$/, '');
      const setter = SETTERS[info.type];
      uniforms[name] = { loc: gl.getUniformLocation(p, info.name), setter, unit: setter === 'sampler' ? unit++ : -1, size: info.size };
    }
    const prog = {
      key, p, uniforms,
      set: (values) => {
        gl.useProgram(p);
        for (const [name, v] of Object.entries(values)) {
          const u = uniforms[name];
          if (!u) continue;
          if (u.setter === 'sampler') {
            gl.activeTexture(gl.TEXTURE0 + u.unit);
            gl.bindTexture(gl.TEXTURE_2D, v && v.tex ? v.tex : v);
            gl.uniform1i(u.loc, u.unit);
          } else if (u.setter.startsWith('uniformMatrix')) gl[u.setter](u.loc, false, v);
          else if (u.setter === 'uniform1f') gl.uniform1f(u.loc, v);
          else if (u.setter === 'uniform1i') gl.uniform1i(u.loc, typeof v === 'boolean' ? Number(v) : v);
          else gl[u.setter](u.loc, v);
        }
        return prog;
      },
    };
    this.programs.set(key, prog);
    return prog;
  }

  // a fullscreen pass of `frag` (which reads vUv) into target
  pass(target, program, uniforms = {}, { blend = 'none', scissor = null } = {}) {
    const gl = this.gl;
    const t = this.use(target);
    this.blend(blend);
    if (scissor) { gl.enable(gl.SCISSOR_TEST); gl.scissor(...scissor); } else gl.disable(gl.SCISSOR_TEST);
    program.set({ uSize: [t.w, t.h], ...uniforms });
    gl.bindVertexArray(this._vaoEmpty);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.disable(gl.SCISSOR_TEST);
  }

  _instanced(stride, layout, data, count) {
    const gl = this.gl;
    if (!this._vaoInst) this._vaoInst = gl.createVertexArray();
    gl.bindVertexArray(this._vaoInst);
    gl.bindBuffer(gl.ARRAY_BUFFER, this._quad);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this._inst);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STREAM_DRAW);
    for (let i = 1; i <= 3; i++) gl.disableVertexAttribArray(i);
    let off = 0;
    layout.forEach((n, i) => {
      gl.enableVertexAttribArray(i + 1);
      gl.vertexAttribPointer(i + 1, n, gl.FLOAT, false, stride * 4, off * 4);
      gl.vertexAttribDivisor(i + 1, 1);
      off += n;
    });
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, count);
    for (let i = 1; i <= layout.length; i++) gl.vertexAttribDivisor(i, 0);
  }

  // device px per design unit and the design frame for a target (a half-size target draws the same frame)
  frameOf(target) {
    const t = target || this.screen, px = t.h / DESIGN_H;
    return { px, design: [t.w / px, DESIGN_H] };
  }

  _mask8(t) {
    if (!this._mask || this._mask.w !== t.w || this._mask.h !== t.h) {
      if (this._mask) this.free(this._mask);
      this._mask = this.target(t.w, t.h, { float: false, format: 'rgba8', filter: 'nearest' });
    }
    return this._mask;
  }

  // The strand and every curve: a polyline as one solid shape, anti-aliased at any width, round joins and caps.
  //   points: [[x, y], ...] or a Float32Array of x, y pairs (design units)
  //   opts: width (design units, or a function (i) -> width), alpha (0..1 or (i) -> alpha),
  //         color (linear rgb), intensity (multiplies colour: over 1 is light), blend ('over' | 'add')
  // Overlaps inside one stroke do not double: coverage is max-combined in a mask, then tinted once.
  stroke(target, points, { width = 2, alpha = 1, color = [1, 1, 1], intensity = 1, blend = 'over', closed = false } = {}) {
    const gl = this.gl;
    const P = points instanceof Float32Array ? points : Float32Array.from(points.flat());
    const n = P.length / 2;
    if (n < 1) return;
    const W = typeof width === 'function' ? width : () => width;
    const A = typeof alpha === 'function' ? alpha : () => alpha;
    const segs = Math.max(n - 1 + (closed ? 1 : 0), 1);
    const data = new Float32Array(segs * 8);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity, rmax = 0;
    for (let s = 0; s < segs; s++) {
      const i = s % n, j = n === 1 ? 0 : (s + 1) % n;
      const r0 = W(i) / 2, r1 = W(j) / 2;
      data.set([P[i * 2], P[i * 2 + 1], P[j * 2], P[j * 2 + 1], r0, r1, A(i), A(j)], s * 8);
      rmax = Math.max(rmax, r0, r1);
    }
    for (let i = 0; i < n; i++) {
      x0 = Math.min(x0, P[i * 2]); x1 = Math.max(x1, P[i * 2]); y0 = Math.min(y0, P[i * 2 + 1]); y1 = Math.max(y1, P[i * 2 + 1]);
    }
    const t = target || this.screen, { px, design } = this.frameOf(t), pad = rmax * px + 3;
    const sx = Math.max(Math.floor(x0 * px - pad), 0), sy = Math.max(Math.floor(t.h - (y1 * px + pad)), 0);
    const sw = Math.min(Math.ceil(x1 * px + pad), t.w) - sx, sh = Math.min(Math.ceil(t.h - (y0 * px - pad)), t.h) - sy;
    if (sw <= 0 || sh <= 0) return;
    const mask = this._mask8(t);
    this.use(mask);
    gl.enable(gl.SCISSOR_TEST);
    gl.scissor(sx, sy, sw, sh);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    this.blend('max');
    this.program('seg', FRAG_SEG, VERT_SEG).set({ uDesign: design, uPx: px });
    this._instanced(8, [4, 4], data, segs);
    const c = [color[0] * intensity, color[1] * intensity, color[2] * intensity, blend === 'add' ? 0 : 1];
    this.use(target);
    this.blend(blend);
    gl.scissor(sx, sy, sw, sh);
    this.program('tint', FRAG_TINT).set({ uMask: mask, uColor: c, uSize: [t.w, t.h], uGround: this.ground, uPerceptual: blend === 'over' ? 1 : 0 });
    gl.bindVertexArray(this._vaoEmpty);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.disable(gl.SCISSOR_TEST);
  }

  // anti-aliased discs: [{x, y, r, color: linear rgb, alpha, intensity, soft}] (soft 0..1: a halo of light)
  points(target, list, { blend = 'over' } = {}) {
    if (!list.length) return;
    const data = new Float32Array(list.length * 12);
    list.forEach((d, i) => {
      const a = d.alpha ?? 1, k = (d.intensity ?? 1) * a, c = d.color || [1, 1, 1];
      data.set([d.x, d.y, d.r, d.soft || 0, c[0] * k, c[1] * k, c[2] * k, blend === 'add' ? 0 : a, 0, 0, 1, 1], i * 12);
    });
    const { px, design } = this.frameOf(this.use(target));
    this.blend(blend);
    this.program('disc', FRAG_DISC, VERT_INST).set({ uDesign: design, uPx: px, uDisc: 1, uSnap: 0, uGround: this.ground, uPerceptual: blend === 'over' ? 1 : 0 });
    this._instanced(12, [4, 4, 4], data, list.length);
  }

  // rectangles: [{x, y, w, h, color, alpha, uv: [u0, v0, u1, v1]}]; texture multiplies (premultiplied); snap: to pixels
  rects(target, list, { blend = 'over', texture = null, snap = false, srgb = false } = {}) {
    if (!list.length) return;
    const data = new Float32Array(list.length * 12);
    list.forEach((d, i) => {
      const a = d.alpha ?? 1, c = d.color || [1, 1, 1], k = (d.intensity ?? 1) * a, uv = d.uv || [0, 0, 1, 1];
      data.set([d.x, d.y, d.w, d.h, c[0] * k, c[1] * k, c[2] * k, blend === 'add' ? 0 : a, ...uv], i * 12);
    });
    const { px, design } = this.frameOf(this.use(target));
    this.blend(blend);
    this.program('rect', FRAG_RECT, VERT_INST).set({
      uDesign: design, uPx: px, uDisc: 0, uSnap: snap ? 1 : 0, uTextured: texture ? 1 : 0, uSrgb: srgb ? 1 : 0, uTex: texture || this._white(),
    });
    this._instanced(12, [4, 4, 4], data, list.length);
  }

  // A texture laid over a mesh. grid: cols x rows points in design units, row by row from the top
  // ([[x, y], ...] or a Float32Array of x, y), the texture spread evenly over it (u across, v down);
  // or 4 corners (top left, top right, bottom right, bottom left), drawn in true perspective.
  // opts: cols, rows (for a grid), alpha, tint (linear rgb), srgb (an image's values), blend, uv [u0, v0, u1, v1]
  mesh(target, texture, grid, { cols, rows, alpha = 1, tint = [1, 1, 1], srgb = true, blend = 'over', uv = [0, 0, 1, 1] } = {}) {
    const gl = this.gl;
    const P = grid instanceof Float32Array ? grid : Float32Array.from(grid.flat());
    const n = P.length / 2;
    let verts, idx;
    const U = (a) => uv[0] + (uv[2] - uv[0]) * a, V = (b) => uv[1] + (uv[3] - uv[1]) * b;
    if (n === 4 && !cols) {
      // a quad in perspective: q from the diagonals' intersection, so the texture is not sheared along them
      const [x0, y0, x1, y1, x2, y2, x3, y3] = P;
      const d = (x2 - x0) * (y3 - y1) - (y2 - y0) * (x3 - x1);
      const s = ((x3 - x1) * (y0 - y1) - (y3 - y1) * (x0 - x1)) / d, tt = ((x2 - x0) * (y0 - y1) - (y2 - y0) * (x0 - x1)) / d;
      const cx = x0 + s * (x2 - x0), cy = y0 + s * (y2 - y0);
      const dist = (ax, ay) => Math.hypot(ax - cx, ay - cy);
      const d0 = dist(x0, y0), d1 = dist(x1, y1), d2 = dist(x2, y2), d3 = dist(x3, y3);
      const q0 = (d0 + d2) / d2, q1 = (d1 + d3) / d3, q2 = (d2 + d0) / d0, q3 = (d3 + d1) / d1;
      void tt;
      verts = new Float32Array([x0, y0, U(0) * q0, V(0) * q0, q0, x1, y1, U(1) * q1, V(0) * q1, q1,
        x2, y2, U(1) * q2, V(1) * q2, q2, x3, y3, U(0) * q3, V(1) * q3, q3]);
      idx = new Uint32Array([0, 1, 2, 0, 2, 3]);
    } else {
      if (!cols || !rows || cols * rows !== n) throw new Error(`mesh: ${n} points is not cols ${cols} x rows ${rows}`);
      verts = new Float32Array(n * 5);
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
        const i = r * cols + c;
        verts.set([P[i * 2], P[i * 2 + 1], U(c / (cols - 1)), V(r / (rows - 1)), 1], i * 5);
      }
      idx = new Uint32Array((cols - 1) * (rows - 1) * 6);
      let k = 0;
      for (let r = 0; r < rows - 1; r++) for (let c = 0; c < cols - 1; c++) {
        const a = r * cols + c, b = a + 1, e = a + cols, f = e + 1;
        idx.set([a, b, f, a, f, e], k);
        k += 6;
      }
    }
    const { px, design } = this.frameOf(this.use(target));
    this.blend(blend);
    this.program('mesh', FRAG_MESH, VERT_MESH).set({ uDesign: design, uPx: px, uTex: texture, uSrgb: srgb ? 1 : 0, uAlpha: alpha, uTint: tint });
    if (!this._vaoMesh) { this._vaoMesh = gl.createVertexArray(); this._meshBuf = gl.createBuffer(); this._meshIdx = gl.createBuffer(); }
    gl.bindVertexArray(this._vaoMesh);
    gl.bindBuffer(gl.ARRAY_BUFFER, this._meshBuf);
    gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STREAM_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 20, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 20, 8);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this._meshIdx);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.STREAM_DRAW);
    gl.drawElements(gl.TRIANGLES, idx.length, gl.UNSIGNED_INT, 0);
    gl.bindVertexArray(null);
  }

  // a 1x1 white texture, bound where a sampler has nothing to read (never the target being drawn into)
  _white() {
    if (!this._whiteTex) this._whiteTex = this.texture({ width: 1, height: 1, data: new Uint8Array([255, 255, 255, 255]) }, { filter: 'nearest' });
    return this._whiteTex;
  }

  // a texture from a canvas, ImageBitmap, or {width, height, data: TypedArray, format};
  // anisotropy: mipmaps with anisotropic filtering at that level (where the extension exists), off by default
  texture(source, { filter = 'linear', mips = false, wrap = 'clamp', anisotropy = 0 } = {}) {
    const gl = this.gl, tex = gl.createTexture();
    tex.opts = { filter, mips: mips || anisotropy > 0, wrap, anisotropy };
    this.upload(tex, source);
    this.textures.add(tex);
    return tex;
  }

  upload(tex, source) {
    const gl = this.gl, { filter, mips, wrap, anisotropy = 0 } = tex.opts;
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    if (source.data) {
      const f = source.format || 'rgba8';
      const spec = { rgba8: [gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE], r8: [gl.R8, gl.RED, gl.UNSIGNED_BYTE],
        r32f: [gl.R32F, gl.RED, gl.FLOAT], rgba32f: [gl.RGBA32F, gl.RGBA, gl.FLOAT], rgba16f: [gl.RGBA16F, gl.RGBA, gl.FLOAT] }[f];
      gl.texImage2D(gl.TEXTURE_2D, 0, spec[0], source.width, source.height, 0, spec[1], spec[2], source.data);
    } else {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, source);
    }
    const f = filter === 'nearest' ? gl.NEAREST : gl.LINEAR;
    if (mips) gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, mips ? gl.LINEAR_MIPMAP_LINEAR : f);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, f);
    if (anisotropy > 0) {
      const ext = gl.getExtension('EXT_texture_filter_anisotropic');
      if (ext) gl.texParameterf(gl.TEXTURE_2D, ext.TEXTURE_MAX_ANISOTROPY_EXT, Math.min(anisotropy, gl.getParameter(ext.MAX_TEXTURE_MAX_ANISOTROPY_EXT)));
    }
    const w = wrap === 'repeat' ? gl.REPEAT : gl.CLAMP_TO_EDGE;
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, w);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, w);
    tex.width = source.width; tex.height = source.height;
    return tex;
  }

  deleteTexture(tex) { this.gl.deleteTexture(tex); this.textures.delete(tex); }

  // the pixels of a target, rows from the bottom (as GL stores them)
  read(target, out) {
    const gl = this.gl, t = this.use(target);
    if (t.format === 'rgb10a2') {
      out = out || new Uint32Array(t.w * t.h);
      gl.readPixels(0, 0, t.w, t.h, gl.RGBA, gl.UNSIGNED_INT_2_10_10_10_REV, out);
    } else {
      out = out || new Uint8Array(t.w * t.h * 4);
      gl.readPixels(0, 0, t.w, t.h, gl.RGBA, gl.UNSIGNED_BYTE, out);
    }
    return out;
  }
}

export { VERT_FULL };
