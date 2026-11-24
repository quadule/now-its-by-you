// The seed packet's face, printed plate by plate (data/s09/, prep/s09_face.py), laid over a grid of the face's points.
//
//   const F = await loadFace(ctx)                     the plates, face.json, corners.json
//   drawFace(ctx, target, F, grid, state)             the face through `grid` (17 x 21 points in design units, the
//                                                     face's u = i/16, v = j/20), printed as `state` says
//   F.grid(frame)                                     the face's true points in the closing shot's frame (film frame)
//   F.toDesign(grid, fx, fy)                          a point in face units to design units, as the mesh lays it
//
// The plates composite exactly as tools/cover/face.py prints them (linear light): the tints multiply the paper, the
// opaque inks lie over it with face.py's (col / paper)^0.35, the handling darkens the printed sheet. With every
// plate printed the result equals the cover's front-color.png (prep/s09_face.py checks it from these files).

const COLS = 17, ROWS = 21;

const hexLin = (h) => [1, 3, 5].map((i) => {
  const c = parseInt(h.slice(i, i + 2), 16) / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
});

// every plate's printed amount; 0 is unprinted
export const UNPRINTED = {
  sky: 0, rules: 0, n51: 0, rings: 0, grey: 0, band: 0, white: 0, yellow: 0, green: 0, daisy: 0, concrete: 0,
  ringErase: 0, petalErase: 0,
};
export const PRINTED = Object.fromEntries(Object.keys(UNPRINTED).map((k) => [k, 1]));
// the plates that can land out of register, in the order of uOff
export const PLATES = ['sky', 'rules', 'roundel', 'band', 'white', 'yellow', 'green', 'daisy'];

const VERT = `#version 300 es
layout(location=0) in vec2 pos;
layout(location=1) in vec2 uv;
uniform vec2 uDesign;
out vec2 vUv;
void main() {
  vUv = uv;
  vec2 clip = pos / uDesign * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
}`;

const FRAG = `#version 300 es
precision highp float; precision highp int;
in vec2 vUv;
uniform sampler2D uPaper, uHand, uSky, uBlack, uTints, uRed, uGrey, uRows, uTitle, uMask;
uniform vec2 uScreen;
uniform int uMasked;
uniform vec2 uCrop;
uniform vec4 uP0, uP1, uP2, uP3;   // sky rules n51 rings | grey band white yellow | green daisy concrete ringErase | petalErase
uniform vec2 uOff[8];      // crop px: sky rules roundel band white yellow green daisy
uniform vec3 uPaperInk, uConcrete, uGreen, uYellow, uWhite, uGreyInk, uRedInk, uBlackInk, uGain;
uniform float uBias, uAlpha, uFeather;
out vec4 o;
vec3 toL(vec3 c) { return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
vec4 at(sampler2D t, int k) { return texture(t, vUv + uOff[k] / uCrop, uBias); }
vec3 tint(vec3 c, vec3 ink, float cov) { return c * (1.0 + (ink / uPaperInk - 1.0) * cov); }
vec3 over(vec3 c, vec3 ink, float cov, float alpha) {
  float a = cov * alpha;
  return c * (1.0 - a) + ink * a * pow(max(c / uPaperInk, 0.0), vec3(0.35));
}
void main() {
  vec3 c = toL(texture(uPaper, vUv, uBias).rgb);
  float m = 0.75 + 0.25 * texture(uHand, vUv, uBias).r;
  float uP[16] = float[16](uP0.x, uP0.y, uP0.z, uP0.w, uP1.x, uP1.y, uP1.z, uP1.w, uP2.x, uP2.y, uP2.z, uP2.w,
                            uP3.x, uP3.y, uP3.z, uP3.w);
  vec4 g = at(uGrey, 2);
  c = tint(c, uConcrete, g.g * uP[10]);
  c = tint(c, uGreen, at(uTints, 6).b * uP[8]);
  c = tint(c, uYellow, at(uTints, 5).g * uP[7]);
  c = over(c, uWhite, at(uTints, 4).r * uP[6], 0.8);
  c = over(c, uGreyInk, g.r * uP[4], 0.97);
  // red: the band (its title's letters still filled where the title is not yet revealed), the roundel's rings.
  // uTitle per column: -1..0 the band not yet rolled on (0 laid), 0..1 the title revealed
  vec4 band = at(uRed, 3);
  float col = texture(uTitle, vec2(vUv.x + uOff[3].x / uCrop.x, 0.5)).r;
  float laid = clamp(1.0 + col, 0.0, 1.0), reveal = max(col, 0.0);
  float red = max(band.r, band.g * (1.0 - reveal)) * uP[5] * laid + at(uRed, 2).b * uP[3];
  c = over(c, uRedInk, min(red, 1.0), 0.97);
  // black: the sky row by row (whole until the roundel and the petals cover it), the rules, the 51, the daisy
  vec4 s = at(uSky, 0);
  float row = texture(uRows, vec2(0.5, vUv.y + uOff[0].y / uCrop.y)).r;
  float sky = max(s.r, max(s.g * (1.0 - uP[11]), s.b * (1.0 - uP[12]))) * row * uP[0];
  float black = sky + at(uBlack, 1).r * uP[1] + at(uBlack, 2).g * uP[2] + at(uBlack, 7).b * uP[9];
  c = over(c, uBlackInk, min(black, 1.0), 0.97);
  // a soft edge where the crop ends (the overlay on a sheet that shows more than the crop)
  vec2 e2 = min(vUv, 1.0 - vUv) * uCrop;
  float a = uAlpha * (uFeather > 0.0 ? smoothstep(0.0, uFeather, min(e2.x, e2.y)) : 1.0);
  if (uMasked == 1) a *= texture(uMask, gl_FragCoord.xy / uScreen).r;
  o = vec4(c * m * uGain * a, a);
}`;

export async function loadFace(ctx) {
  const json = await ctx.data.json('s09/face.json');
  const corners = await ctx.data.json('/blender/corners.json');
  const names = ['paper', 'handling', 'sky', 'black', 'tints', 'red', 'grey'];
  const imgs = await Promise.all(names.map((n) => ctx.data.image(`/data/s09/${n}.png`)));
  const tex = Object.fromEntries(names.map((n, i) => [n, imgs[i].tex]));
  const [cw, ch] = json.size;
  const g = ctx.g, gl = g.gl;
  // the row and title masks: one value per crop row (y) and column (x), rewritten each frame
  const rowsData = new Float32Array(ch), titleData = new Float32Array(cw);
  const rowsTex = g.texture({ width: 1, height: ch, data: rowsData, format: 'r32f' }, { filter: 'nearest' });
  const titleTex = g.texture({ width: cw, height: 1, data: titleData, format: 'r32f' }, { filter: 'nearest' });
  const inks = Object.fromEntries(Object.entries(json.inks).map(([k, v]) => [k, hexLin(v)]));
  const paper = hexLin(json.paper);
  const [cu0, cv0, cu1, cv1] = json.crop_uv;
  // the mesh: the 17 x 21 face grid, its texture coordinates into the crop
  const uv = new Float32Array(COLS * ROWS * 2);
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
    const i = r * COLS + c;
    uv[i * 2] = (c / (COLS - 1) - cu0) / (cu1 - cu0);
    uv[i * 2 + 1] = (r / (ROWS - 1) - cv0) / (cv1 - cv0);
  }
  const idx = new Uint32Array((COLS - 1) * (ROWS - 1) * 6);
  let k = 0;
  for (let r = 0; r < ROWS - 1; r++) for (let c = 0; c < COLS - 1; c++) {
    const a = r * COLS + c, b = a + 1, e = a + COLS, f = e + 1;
    idx.set([a, b, f, a, f, e], k);
    k += 6;
  }
  const vao = gl.createVertexArray(), posBuf = gl.createBuffer(), uvBuf = gl.createBuffer(), idxBuf = gl.createBuffer();
  gl.bindVertexArray(vao);
  gl.bindBuffer(gl.ARRAY_BUFFER, uvBuf);
  gl.bufferData(gl.ARRAY_BUFFER, uv, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(1);
  gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
  gl.bufferData(gl.ARRAY_BUFFER, COLS * ROWS * 8, gl.DYNAMIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, idxBuf);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.STATIC_DRAW);
  gl.bindVertexArray(null);

  const first = corners.first_frame;
  const grids = new Map();
  const F = {
    json, corners, tex, rowsTex, titleTex, rowsData, titleData, inks, paper, vao, posBuf, size: [cw, ch],
    cols: COLS, rows: ROWS, first,
    // the face's true points at a film frame of the closing shot (the grid while there is one, else the homography)
    grid(frame) {
      const i = Math.min(Math.max(Math.round(frame) - first, 0), corners.frames.length - 1);
      if (grids.has(i)) return grids.get(i);
      const fr = corners.frames[i];
      const out = new Float32Array(COLS * ROWS * 2);
      for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
        const j = r * COLS + c;
        if (fr.grid_px) { out[j * 2] = fr.grid_px[j][0]; out[j * 2 + 1] = fr.grid_px[j][1]; continue; }
        const u = c / (COLS - 1), v = r / (ROWS - 1), H = fr.H_uv_to_px;
        const w = H[2][0] * u + H[2][1] * v + H[2][2];
        out[j * 2] = (H[0][0] * u + H[0][1] * v + H[0][2]) / w;
        out[j * 2 + 1] = (H[1][0] * u + H[1][1] * v + H[1][2]) / w;
      }
      grids.set(i, out);
      return out;
    },
    // face units (x right, y down, 1275 x 1650) to design units, through the grid's triangles as the mesh draws them
    toDesign(grid, fx, fy) {
      const u = fx / 1275 * (COLS - 1), v = fy / 1650 * (ROWS - 1);
      const c = Math.min(Math.max(Math.floor(u), 0), COLS - 2), r = Math.min(Math.max(Math.floor(v), 0), ROWS - 2);
      const s = u - c, t = v - r;
      const P = (cc, rr) => [grid[(rr * COLS + cc) * 2], grid[(rr * COLS + cc) * 2 + 1]];
      const a = P(c, r), b = P(c + 1, r), e = P(c, r + 1), f = P(c + 1, r + 1);
      if (s >= t) return [a[0] + s * (b[0] - a[0]) + t * (f[0] - b[0]), a[1] + s * (b[1] - a[1]) + t * (f[1] - b[1])];
      return [a[0] + t * (e[0] - a[0]) + s * (f[0] - e[0]), a[1] + t * (e[1] - a[1]) + s * (f[1] - e[1])];
    },
  };
  return F;
}

// state: plate amounts (UNPRINTED's keys), off: {plate: [dx, dy] crop px}, rows(y) / title(x) fill F.rowsData and
// F.titleData before the call; gain: rgb multiplier; alpha: the face's opacity over what is under it
export function drawFace(ctx, target, F, grid, state, { off = {}, gain = [1, 1, 1], alpha = 1, bias = -0.35, feather = 0, mask = null } = {}) {
  const g = ctx.g, gl = g.gl;
  g.upload(F.rowsTex, { width: 1, height: F.size[1], data: F.rowsData, format: 'r32f' });
  g.upload(F.titleTex, { width: F.size[0], height: 1, data: F.titleData, format: 'r32f' });
  const t0 = g.use(target), { design } = g.frameOf(t0);
  g.blend(alpha < 1 || feather > 0 || mask ? 'over' : 'none');
  const p = g.program('s09:face', FRAG, VERT);
  const P = ['sky', 'rules', 'n51', 'rings', 'grey', 'band', 'white', 'yellow', 'green', 'daisy', 'concrete', 'ringErase', 'petalErase']
    .map((k) => state[k] ?? 0).concat([0, 0, 0]);
  const O = new Float32Array(16);
  PLATES.forEach((k, i) => { const v = off[k] || [0, 0]; O[i * 2] = v[0]; O[i * 2 + 1] = v[1]; });
  const I = F.inks;
  p.set({
    uDesign: design, uPaper: F.tex.paper, uHand: F.tex.handling, uSky: F.tex.sky, uBlack: F.tex.black, uTints: F.tex.tints,
    uRed: F.tex.red, uGrey: F.tex.grey, uRows: F.rowsTex, uTitle: F.titleTex, uCrop: F.size, uP0: P.slice(0, 4), uP1: P.slice(4, 8), uP2: P.slice(8, 12), uP3: P.slice(12, 16), uOff: O,
    uPaperInk: F.paper, uConcrete: I.concrete, uGreen: I.green, uYellow: I.yellow, uWhite: I.white, uGreyInk: I.grey,
    uRedInk: I.red, uBlackInk: I.black, uGain: gain, uBias: bias, uAlpha: alpha, uFeather: feather,
    uMasked: mask ? 1 : 0, uMask: mask || F.tex.handling, uScreen: [t0.w, t0.h],
  });
  gl.bindVertexArray(F.vao);
  gl.bindBuffer(gl.ARRAY_BUFFER, F.posBuf);
  gl.bufferSubData(gl.ARRAY_BUFFER, 0, grid instanceof Float32Array ? grid : Float32Array.from(grid));
  gl.drawElements(gl.TRIANGLES, (COLS - 1) * (ROWS - 1) * 6, gl.UNSIGNED_INT, 0);
  gl.bindVertexArray(null);
}
