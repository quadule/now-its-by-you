// The two kernels the translator can't take (they use complex numbers), ported by hand in the same
// descriptor convention as kernels.gen.mjs, with numba's complex arithmetic spelled out:
// (a+bi)(c+di) = (ac - bd) + (ad + bc)i; exp(x+yi) = (e^x cos y, e^x sin y) for finite x, y.
import * as rt from './rt.mjs';

// songbird/synth/piano.py _spectrum: returns complex128 as interleaved (re, im) doubles, t 'c16'
export function k_synth$piano$_spectrum(force, freqs, sr) {
  const K = freqs.n0, T = force.n0, f = force.d, fs = force.s0;
  const out = new Float64Array(2 * K);
  for (let k = 0; k < K; k++) {
    const w = 2.0 * Math.PI * freqs.d[k * freqs.s0] / sr;
    const step_r = Math.cos(w), step_i = -Math.sin(w);
    let pr = 1.0, pi = 0.0, acc_r = 0.0, acc_i = 0.0;
    for (let t = 0; t < T; t++) {
      acc_r += f[t * fs] * pr;
      acc_i += f[t * fs] * pi;
      const nr = pr * step_r - pi * step_i;
      const ni = pr * step_i + pi * step_r;
      pr = nr; pi = ni;
    }
    out[2 * k] = acc_r;
    out[2 * k + 1] = acc_i;
  }
  return { d: out, nd: 1, n0: K, n1: 0, s0: 1, s1: 1, t: 'c16' };
}

const BLOCK = 1024, CONTROL = 32;  // songbird/synth/struck.py

function cexp(x, y) {  // numba's cmath.exp for finite x, y
  const c = Math.cos(y), s = Math.sin(y), r = Math.exp(x);
  return [r * c, r * s];
}

// songbird/synth/struck.py _bank
export function k_synth$struck$_bank(freqs, decay, phase, pos, amps, mix, bend, damp, dweight, rate, length, floor) {
  const n_modes = freqs.n0, n_hits = pos.n0, channels = mix.n1;
  const out = rt.alloc(2, length, channels, 'f8', 0), o = out.d;
  const zr = new Float64Array(n_modes), zi = new Float64Array(n_modes);
  const alive = new Uint8Array(n_modes);
  const omega = new Float64Array(n_modes), fr = new Float64Array(n_modes), fi = new Float64Array(n_modes);
  const F = (a, i) => a.d[i * a.s0];
  const M2 = (a, i, j) => a.d[i * a.s0 + j * a.s1];
  for (let k = 0; k < n_modes; k++) omega[k] = 2.0 * Math.PI * F(freqs, k) / rate;
  for (let k = 0; k < n_modes; k++) [fr[k], fi[k]] = cexp(-F(decay, k) / rate, omega[k]);
  const moving = bend.n0 > 0 || damp.n0 > 0;
  let first = 0;
  for (let b0 = 0; b0 < length; b0 += BLOCK) {
    const b1 = Math.min(length, b0 + BLOCK);
    let last = first;
    while (last < n_hits && F(pos, last) <= b1 - 1) last += 1;
    for (let k = 0; k < n_modes; k++) {
      if (!alive[k] && last === first) continue;
      let gain = 0.0;
      for (let c = 0; c < channels; c++) gain = rt.pmax(gain, Math.abs(M2(mix, k, c)));
      if (gain === 0.0) continue;
      let r = zr[k], i = zi[k];
      let mr = fr[k], mi = fi[k];
      let h = first;
      for (let s0 = b0; s0 < b1; s0 += CONTROL) {
        const s1 = Math.min(b1, s0 + CONTROL);
        if (moving) {
          let w = omega[k];
          if (bend.n0 > 0) w = w * (1.0 + F(bend, s0));
          let a = F(decay, k);
          for (let d = 0; d < damp.n0; d++) a = a + M2(damp, d, s0) * M2(dweight, d, k);
          [mr, mi] = cexp(-a / rate, w);
        }
        for (let n = s0; n < s1; n++) {
          const nr = r * mr - i * mi, ni = r * mi + i * mr;
          r = nr; i = ni;
          while (h < last && F(pos, h) <= n) {
            const ahead = n - F(pos, h);
            const [er, ei] = cexp(-F(decay, k) * ahead / rate, F(phase, k) + omega[k] * ahead);
            const amp = M2(amps, h, k);  // a real times a complex, as numba does it: (amp + 0i)(er + ei i)
            r = r + (amp * er - 0.0 * ei);
            i = i + (amp * ei + 0.0 * er);
            h += 1;
          }
          const v = i;
          for (let c = 0; c < channels; c++) o[n * channels + c] += v * M2(mix, k, c);
        }
      }
      zr[k] = r; zi[k] = i;
      alive[k] = (r * r + i * i) * gain * gain > floor ? 1 : 0;
      if (!alive[k]) { zr[k] = 0.0; zi[k] = 0.0; }
    }
    first = last;
  }
  return out;
}
