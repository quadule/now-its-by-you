// The plucked string re-run from its captured parameters (physics/pluck-<part>-notes.json and its .bin), and its
// shape at an instant from the loop's last period (prep/DATA.md):
//   y[n] = x[n] + g[n] * sum_k taps[k] * y[n - N - k],   g = g0 until held, then g <- rg + (g - rg) * smooth
// y is bridge force. Over one period P the bridge force is the slope of the travelling wave, so with S the running
// sum of the last P samples (less their mean) the string at sample n is y(j) = S[n - P + j] - S[n - j],
// j = 0..P/2 samples of travel from the bridge (x = 2j / P of the string).
//
// Each plane is simulated once, whole, in float64 arithmetic at the audio rate, and kept as float32 by note.

export class Plucks {
  constructor(notesJson, excitation) {
    this.sr = notesJson.sr;
    this.notes = notesJson.notes;
    this.x = excitation.values;
    this.cache = new Map();
    this.notes.forEach((n, i) => { n.i = i; });
  }

  // the notes sounding (start <= t < start + len) in [t0, t1]
  between(t0, t1) {
    return this.notes.filter((n) => n.t <= t1 && n.t + n.len / this.sr >= t0);
  }

  // one plane's bridge force, every sample of the note
  plane(note, k) {
    const key = note.i * 8 + k;
    let y = this.cache.get(key);
    if (y) return y;
    const p = note.planes[k], N = p.N, taps = p.taps, nt = taps.length, pad = N + nt;
    const len = p.len, buf = new Float64Array(pad + len), x = this.x, x0 = p.x0, xn = p.xn;
    let g = p.g;
    for (let n = 0; n < len; n++) {
      if (n >= p.held) g = p.rg + (g - p.rg) * p.smooth;
      const acc = n < xn ? x[x0 + n] : 0;
      const base = pad + n - N;
      let fb = 0;
      for (let q = 0; q < nt; q++) fb += taps[q] * buf[base - q];
      buf[pad + n] = acc + g * fb;
    }
    y = new Float32Array(len);
    for (let n = 0; n < len; n++) y[n] = buf[pad + n];
    this.cache.set(key, y);
    return y;
  }

  // the period of a plane in samples (N plus the taps' delay: sr / f exactly)
  period(note, k = 0) { return this.sr / note.planes[k].f; }

  // The string's displacement in plane k at sample n of the note (n from the note's start), `count` points from the
  // bridge (0) to the far end (count - 1), into out. Returns out.
  shape(note, k, n, count, out = new Float32Array(count)) {
    const y = this.plane(note, k), p = note.planes[k];
    const P = Math.max(4, Math.round(this.sr / p.f)), lag = p.lag || 0;
    const end = Math.floor(n) - lag;                      // the last sample of the window, in the plane's own count
    // S[i], i = 0..P: the running sum of the window's samples (y[end - P + 1 .. end]) less their mean
    const S = this._S && this._S.length >= P + 1 ? this._S : (this._S = new Float64Array(Math.max(P + 1, 4096)));
    let mean = 0;
    for (let i = 0; i < P; i++) { const m = end - P + 1 + i; mean += m >= 0 && m < y.length ? y[m] : 0; }
    mean /= P;
    S[0] = 0;
    for (let i = 0; i < P; i++) { const m = end - P + 1 + i; S[i + 1] = S[i] + ((m >= 0 && m < y.length ? y[m] : 0) - mean); }
    // y(j) = S[j] - S[P - j] (S indexed from the window's start), j = 0..P/2, read at count places by linear interpolation
    const half = P / 2;
    const at = (u) => { const i = Math.floor(u), f = u - i; const a = S[Math.min(i, P)], b = S[Math.min(i + 1, P)]; return a + (b - a) * f; };
    for (let c = 0; c < count; c++) {
      const j = (c / (count - 1)) * half;
      out[c] = at(j) - at(P - j);
    }
    return out;
  }
}

// The strobe: at song time t, the sample of a note shown. Each frame shows the string at a true instant: the
// period it is in now (real time: the ring decays as heard), at a phase that turns `rate` times slower than the
// string itself (a stroboscope locked to the string's own period). rate 400: a 988 Hz string turns 2.5 times a second.
export function strobeSample(note, t, sr, f, rate) {
  const tau = t - note.t;
  if (tau < 0) return -1;
  const P = sr / f;
  const periods = Math.floor((tau * sr) / P);
  const phase = (tau * f / rate) % 1;
  return periods * P + phase * P;
}
