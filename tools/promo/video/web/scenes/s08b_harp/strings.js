// A plucked harp string from the instrumented replay (physics/pluck-harp, its notes' planes): the loop run from the
// note's start with its captured parameters (prep/DATA.md: y[n] = x[n] + g[n] sum_k taps[k] y[n - N - k]), and the
// string's shape at a sample read from one period of it (its own travelling wave), as s09_broadside's lines read it.

const SR = 44100;

// one plane's loop from the note's start, `samples` long
export function runPlane(pl, exc, samples) {
  const L = Math.min(pl.len, samples);
  const y = new Float32Array(Math.max(L, 1));
  const Nd = pl.N, taps = pl.taps, nt = taps.length;
  let g = pl.g;
  for (let n = 0; n < L; n++) {
    if (n >= pl.held) g = pl.rg + (g - pl.rg) * pl.smooth;
    let acc = 0;
    for (let k = 0; k < nt; k++) {
      const i = n - Nd - k;
      if (i >= 0) acc += taps[k] * y[i];
    }
    y[n] = (n < pl.xn ? exc[pl.x0 + n] : 0) + g * acc;
  }
  return y;
}

// The string's shape at sample n (into out, M places from one end to the other): one period of the loop's output
// before n, less its mean, summed (C); place j of a half period is C[j] - C[P - j], the two travelling waves met.
export function shapeAt(y, n, P, out, work) {
  const M = out.length;
  if (n < 2 || n >= y.length) { out.fill(0); return out; }
  P = Math.min(P, n);
  let mean = 0;
  for (let m = 0; m < P; m++) mean += y[n - P + 1 + m];
  mean /= P;
  const C = work.length >= P ? work : new Float64Array(P);
  let s = 0;
  for (let m = 0; m < P; m++) { s += y[n - P + 1 + m] - mean; C[m] = s; }
  const half = P / 2;
  const at = (jj) => (jj - 1 >= 0 ? C[Math.min(jj - 1, P - 1)] : 0) - C[Math.max(P - 1 - jj, 0)];
  for (let i = 0; i < M; i++) {
    const j = (i / (M - 1)) * half, j0 = Math.floor(j), f = j - j0;
    out[i] = at(j0) * (1 - f) + at(Math.min(j0 + 1, Math.floor(half))) * f;
  }
  return out;
}

export { SR };
