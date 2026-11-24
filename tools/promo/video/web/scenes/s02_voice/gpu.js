// Raw WebGL2 pieces the core's helpers lack: float textures from typed arrays, a layer with a depth buffer (for lines
// that hide the lines behind them), a mipmapped float target, and the camera as shader uniforms.

// a texture from a typed array: fmt 'r16f' (half-float bits in a Uint16Array), 'r32f', 'rgba32f'
export function dataTexture(gl, width, height, data, fmt) {
  const spec = {
    r16f: [gl.R16F, gl.RED, gl.HALF_FLOAT], r32f: [gl.R32F, gl.RED, gl.FLOAT], rgba32f: [gl.RGBA32F, gl.RGBA, gl.FLOAT],
  }[fmt];
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
  gl.texImage2D(gl.TEXTURE_2D, 0, spec[0], width, height, 0, spec[1], spec[2], data);
  for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, p, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  return tex;
}

// an RGBA16F target with a full mip chain and a framebuffer per level (render into level 0, then reduce)
export function mipTarget(gl, w, h) {
  const levels = 1 + Math.floor(Math.log2(Math.max(w, h)));
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texStorage2D(gl.TEXTURE_2D, levels, gl.RGBA16F, w, h);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST_MIPMAP_NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  const fbs = [], sizes = [];
  for (let l = 0; l < levels; l++) {
    const fb = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, l);
    fbs.push(fb);
    sizes.push([Math.max(w >> l, 1), Math.max(h >> l, 1)]);
  }
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return { fb: fbs[0], fbs, sizes, tex, w, h, levels };
}

// a layer the size of the frame: RGBA16F colour (premultiplied, cleared transparent) and a 24-bit depth buffer
export function depthLayer(gl, w, h) {
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RGBA16F, w, h);
  for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, p, gl.NEAREST);
  const depth = gl.createRenderbuffer();
  gl.bindRenderbuffer(gl.RENDERBUFFER, depth);
  gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT24, w, h);
  const fb = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, depth);
  const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  if (!ok) throw new Error('s02: depth layer incomplete');
  return { fb, tex, depth, w, h };
}
export function freeLayer(gl, l) {
  if (!l) return;
  gl.deleteFramebuffer(l.fb); gl.deleteTexture(l.tex);
  if (l.depth) gl.deleteRenderbuffer(l.depth);
}

// the core camera as uniforms (GLSL: uCamPos, uCamR, uCamU, uCamF, uFocal, uCenter) for project() in CAMERA_GLSL
export const camUniforms = (cam) => ({
  uCamPos: cam.position, uCamR: cam.r, uCamU: cam.u, uCamF: cam.f, uFocal: cam.focal, uCenter: cam.center,
});
// the same projection as core/camera.js: design units, y down; .z the depth along the view
export const CAMERA_GLSL = `
uniform vec3 uCamPos, uCamR, uCamU, uCamF; uniform float uFocal; uniform vec2 uCenter;
vec3 project(vec3 p) {
  vec3 d = p - uCamPos;
  float z = dot(d, uCamF);
  float s = uFocal / max(z, 1e-6);
  return vec3(uCenter.x + dot(d, uCamR) * s, uCenter.y - dot(d, uCamU) * s, z);
}`;

// draw `count` instances of a 4-vertex strip with the bound program (no attributes: shaders use gl_VertexID, gl_InstanceID)
export function strips(g, count) {
  const gl = g.gl;
  if (!g._s02vao) g._s02vao = gl.createVertexArray();
  gl.bindVertexArray(g._s02vao);
  gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, count);
  gl.bindVertexArray(null);
}
