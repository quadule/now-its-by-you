// The wall of screens: every screen one instance of a quad placed in the world and projected through a core Camera
// (the same projection as camera.project, written as clip coordinates so the texture is perspective-correct).
// Textures: the captures as one sRGB texture array and the tall Page as one sRGB texture, both mipmapped and
// filtered anisotropically, so a screen far down the corridor is an average of its page, not a shimmer.
//
// A screen's light: on (a short rise), out (a fall with a phosphor's tail), dimmed a little with distance.
// Its picture: the tall Page at the shared scroll, until it diverges: then its own view scrolls up into it.
// Edges are anti-aliased in the shader from the quad's own texture coordinates (the quad is drawn a little larger).

export const SCREEN_W = 16, SCREEN_H = 9;
// the quad's extra size, in texture units: room for the anti-aliased edge near, and enough to close the gaps
// between screens far away, where they merge into one band of light
const MARGIN = [0.07, 0.09];

const VERT = `#version 300 es
layout(location=0) in vec2 corner;
layout(location=1) in vec4 aPos;     // centre xyz, side (-1: the left wall, texture u along -z; 1: the right, along +z)
layout(location=2) in vec4 aTime;    // on, diverge, out, layer
layout(location=3) in vec4 aMore;    // hero, seed, fall (s)
uniform vec3 uCam, uF, uR, uU;
uniform float uFocal, uNear;
uniform vec2 uMargin;
uniform vec2 uCenter, uDesign, uHalf;
out vec2 vUv; flat out vec4 vTime; flat out vec4 vMore; out float vDepth;
void main() {
  vec3 axisU = vec3(0.0, 0.0, aPos.w), axisV = vec3(0.0, 1.0, 0.0);
  vec2 c = corner * (1.0 + 2.0 * uMargin);
  vec3 p = aPos.xyz + axisU * c.x * uHalf.x + axisV * c.y * uHalf.y;
  vUv = 0.5 + 0.5 * c;
  vec3 d = p - uCam;
  float z = dot(d, uF), x = dot(d, uR), y = dot(d, uU);
  vDepth = z;
  gl_Position = vec4((2.0 * uCenter.x / uDesign.x - 1.0) * z + 2.0 * x * uFocal / uDesign.x,
                     (1.0 - 2.0 * uCenter.y / uDesign.y) * z + 2.0 * y * uFocal / uDesign.y,
                     z - 2.0 * uNear, z);
  vTime = aTime; vMore = aMore;
}`;

const FRAG = `#version 300 es
precision highp float; precision highp int; precision highp sampler2DArray;
in vec2 vUv; flat in vec4 vTime; flat in vec4 vMore; in float vDepth;
uniform sampler2DArray uViews;
uniform sampler2D uTall;
uniform float uT, uScroll, uWin, uPageIn, uMatch, uGain, uHeroGain, uSlide, uRise, uFar;
uniform vec3 uPaper, uPageBg;
out vec4 o;
void main() {
  vec2 uv = vUv;
  vec2 fw = max(fwidth(uv), vec2(1e-6));
  // how many pixels the screen spans, across and down: under about 26 it merges into a band of its own average light
  float span = min(1.0 / fw.x, 1.78 / fw.y);
  float sharp = smoothstep(9.0, 26.0, span);
  vec2 e = min(uv, 1.0 - uv) / fw + 0.5;
  float cov = mix(1.0, clamp(e.x, 0.0, 1.0) * clamp(e.y, 0.0, 1.0), sharp);
  if (cov <= 0.0) discard;
  float hero = vMore.x;
  // light
  float on = smoothstep(vTime.x, vTime.x + uRise, uT);
  float since = uT - vTime.z, fall = vMore.z;
  float out_ = since < 0.0 ? 1.0 : exp(-since / fall) * (1.0 - smoothstep(0.0, 4.0 * fall, since));
  float L = on * out_;
  if (L <= 0.0) discard;
  // the picture: the tall Page at the scroll, then the screen's own view scrolling up into it. Near the camera the
  // texture is read half a level sharper (the 2048 px capture shown at 1000 to 1900 px); far, at its own level.
  vec2 cuv = clamp(uv, 0.0, 1.0);
  float bias = mix(0.55, 1.0, smoothstep(24.0, 70.0, vDepth));
  vec2 dx = dFdx(uv) * bias, dy = dFdy(uv) * bias;
  float k = clamp((uT - vTime.y) / uSlide, 0.0, 1.0);
  k = k * k * (3.0 - 2.0 * k);
  float v = cuv.y + k;
  vec3 c;
  if (v < 1.0) c = textureGrad(uTall, vec2(cuv.x, (uScroll + v) * uWin), vec2(dx.x, dx.y * uWin), vec2(dy.x, dy.y * uWin)).rgb;
  else c = textureGrad(uViews, vec3(cuv.x, v - 1.0, vTime.w), dx, dy).rgb;
  vec3 avg = k < 0.5 ? textureLod(uTall, vec2(0.5, (uScroll + 0.5) * uWin), 7.0).rgb : textureLod(uViews, vec3(0.5, 0.5, vTime.w), 7.0).rgb;
  c = mix(avg * 0.5, c, sharp);
  // on the paper the Page is the paper: its ground matched to the film's, its light rising as the room goes dark
  float gain = mix(uGain, uHeroGain, hero);
  vec3 tint = mix(vec3(1.0), uPaper / uPageBg, hero * uMatch);
  // the far end of the room goes into haze, so the vanishing point is a glow, not a pattern
  float fog = mix(1.0, 0.35, smoothstep(30.0, 700.0, vDepth)) * (1.0 - 0.9 * smoothstep(700.0, uFar, vDepth));
  float a = cov * mix(1.0, uPageIn, hero) * min(L * 3.0, 1.0);
  // a dying screen: its light falls and cools toward the machine's blue
  vec3 cool = mix(vec3(0.75, 0.86, 1.15), vec3(1.0), smoothstep(0.0, 0.6, out_));
  o = vec4(c * tint * gain * fog * L * cool, 1.0) * a;
}`;

export class Wall {
  static async create(ctx, { index, layers, tall }) {
    const w = new Wall(ctx);
    await w.load(index, layers, tall);
    return w;
  }

  constructor(ctx) {
    this.ctx = ctx;
    this.gl = ctx.gl;
    this.g = ctx.g;
  }

  async load(index, layers, tall) {
    const gl = this.gl;
    const bitmap = async (file) => {
      const r = await fetch(`/studio/${file}`, { cache: 'no-store' });
      if (!r.ok) throw new Error(`s05_studio: /studio/${file} ${r.status}`);
      return createImageBitmap(await r.blob(), { premultiplyAlpha: 'none', colorSpaceConversion: 'none' });
    };
    const aniso = gl.getExtension('EXT_texture_filter_anisotropic');
    const filtered = (target) => {
      gl.generateMipmap(target);
      gl.texParameteri(target, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(target, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(target, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(target, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      if (aniso) gl.texParameterf(target, aniso.TEXTURE_MAX_ANISOTROPY_EXT, Math.min(16, gl.getParameter(aniso.MAX_TEXTURE_MAX_ANISOTROPY_EXT)));
    };
    const levels = (w, h) => Math.floor(Math.log2(Math.max(w, h))) + 1;
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);

    const bms = await Promise.all(layers.map((n) => bitmap(`${n}.jpg`)));
    const W = bms[0].width, H = bms[0].height;
    this.views = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D_ARRAY, this.views);
    gl.texStorage3D(gl.TEXTURE_2D_ARRAY, levels(W, H), gl.SRGB8_ALPHA8, W, H, bms.length);
    bms.forEach((bm, i) => {
      if (bm.width !== W || bm.height !== H) throw new Error(`s05_studio: ${layers[i]} is ${bm.width}x${bm.height}, not ${W}x${H}`);
      gl.texSubImage3D(gl.TEXTURE_2D_ARRAY, 0, 0, 0, i, W, H, 1, gl.RGBA, gl.UNSIGNED_BYTE, bm);
      bm.close();
    });
    filtered(gl.TEXTURE_2D_ARRAY);

    const tb = await bitmap(`${tall}.jpg`);
    this.tall = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.tall);
    gl.texStorage2D(gl.TEXTURE_2D, levels(tb.width, tb.height), gl.SRGB8_ALPHA8, tb.width, tb.height);
    gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, gl.RGBA, gl.UNSIGNED_BYTE, tb);
    filtered(gl.TEXTURE_2D);
    // the window a screen shows of the tall page, and how far it can scroll, as fractions of its height
    this.win = (W / tb.width) * H / tb.height;
    this.scrollMax = (tb.height - (tb.width / W) * H) / ((tb.width / W) * H);
    // the Page's own ground (a corner of the page, as linear light)
    const cv = new OffscreenCanvas(1, 1), c2 = cv.getContext('2d');
    c2.drawImage(tb, 8, tb.height - 8, 1, 1, 0, 0, 1, 1);
    const px = c2.getImageData(0, 0, 1, 1).data;
    this.pageBg = [px[0], px[1], px[2]].map((v) => this.ctx.palette.toLinear(v / 255));
    tb.close();
    gl.bindTexture(gl.TEXTURE_2D, null);
    gl.bindTexture(gl.TEXTURE_2D_ARRAY, null);

    this.prog = this.g.program('s05:wall', FRAG, VERT);
    this.vao = gl.createVertexArray();
    this.quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    this.inst = gl.createBuffer();
  }

  instances(list) {
    const gl = this.gl;
    const data = new Float32Array(list.length * 12);
    list.forEach((s, i) => data.set([s.x, s.y, s.z, s.side, s.on, s.sw, s.off, s.layer, s.hero ? 1 : 0, s.seed, s.fall ?? 0.16, 0], i * 12));
    this.count = list.length;
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.inst);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    for (let a = 1; a <= 3; a++) {
      gl.enableVertexAttribArray(a);
      gl.vertexAttribPointer(a, 4, gl.FLOAT, false, 48, (a - 1) * 16);
      gl.vertexAttribDivisor(a, 1);
    }
    gl.bindVertexArray(null);
  }

  draw(target, cam, t, { scroll = 0, slide = 0.45, pageIn = 1, match = 0, paper, gain = 1, heroGain = 1 }) {
    const gl = this.gl, g = this.g;
    const { px, design } = g.frameOf(g.use(target));
    void px;
    g.blend('over');
    this.prog.set({
      uCam: cam.position, uF: cam.f, uR: cam.r, uU: cam.u, uFocal: cam.focal, uNear: cam.near, uMargin: MARGIN,
      uCenter: cam.center, uDesign: design, uHalf: [SCREEN_W / 2, SCREEN_H / 2],
      uViews: null, uTall: null, uT: t, uScroll: scroll * this.scrollMax, uWin: this.win, uPageIn: pageIn, uMatch: match,
      uGain: gain, uHeroGain: heroGain, uSlide: slide, uRise: 0.12, uFar: 2600,
      uPaper: paper, uPageBg: this.pageBg,
    });
    // the samplers: the array on its own target (prog.set binds TEXTURE_2D only)
    const u = this.prog.uniforms;
    gl.activeTexture(gl.TEXTURE0 + u.uViews.unit);
    gl.bindTexture(gl.TEXTURE_2D, null);
    gl.bindTexture(gl.TEXTURE_2D_ARRAY, this.views);
    gl.uniform1i(u.uViews.loc, u.uViews.unit);
    gl.activeTexture(gl.TEXTURE0 + u.uTall.unit);
    gl.bindTexture(gl.TEXTURE_2D, this.tall);
    gl.uniform1i(u.uTall.loc, u.uTall.unit);
    gl.bindVertexArray(this.vao);
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, this.count);
    gl.bindVertexArray(null);
    gl.activeTexture(gl.TEXTURE0 + u.uViews.unit);
    gl.bindTexture(gl.TEXTURE_2D_ARRAY, null);
    gl.activeTexture(gl.TEXTURE0);
  }
}
