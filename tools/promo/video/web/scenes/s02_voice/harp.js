// The harp's strings re-run from the model's captured loop (physics/pluck-harp, DATA.md): each plane
//   y[n] = x[n] + g[n] * sum_k taps[k] * y[n - N - k],  g = g0 until `held`, then g <- rg + (g - rg) * smooth,
// run once per note from its first sample (cached), so any frame can read the string at any time. The plane's y is
// bridge force; over one period P it is the slope of the travelling wave, so with S the running sum of the last P
// samples (less their mean) the string's shape is y(j) = S[n - P + j] - S[n - j], j = 0..P/2 (x = 2j / P).

export class Harp {
  constructor(notes, excitation, { from, to }) {
    this.sr = notes.sr;
    this.x = excitation;
    // the notes that ring in [from, to]: started before `to`, still sounding after `from`
    this.notes = notes.notes.filter((n) => n.t < to && n.t + n.len / notes.sr > from);
    this.runs = new Map();
  }

  _run(note, plane) {
    const key = `${note.s}:${plane.string}:${plane.plane}`;
    if (this.runs.has(key)) return this.runs.get(key);
    const len = plane.len, N = plane.N, taps = plane.taps, y = new Float64Array(len);
    const x0 = plane.x0, xn = plane.xn, ex = this.x;
    let g = plane.g;
    for (let n = 0; n < len; n++) {
      if (n >= plane.held) g = plane.rg + (g - plane.rg) * plane.smooth;
      let acc = 0;
      for (let k = 0; k < 5; k++) {
        const j = n - N - k;
        if (j >= 0) acc += taps[k] * y[j];
      }
      y[n] = (n < xn ? ex[x0 + n] : 0) + g * acc;
    }
    this.runs.set(key, y);
    return y;
  }

  // the shape of one plane at sample n of its run (n counted from the plane's start): `points` displacements, bridge
  // to nut; null before its first period or after its end
  shapeAt(note, plane, n, points = 241) {
    n = Math.floor(n);
    const P = Math.max(4, Math.round(this.sr / plane.f));
    if (n < P || n >= plane.len) return null;
    const y = this._run(note, plane);
    let mean = 0;
    for (let i = n - P + 1; i <= n; i++) mean += y[i];
    mean /= P;
    // S[k]: the running sum (less the mean) up to sample n - P + k; the shape at j is S[j] - S[P - j]
    const S = new Float64Array(P + 1);
    for (let i = 0; i < P; i++) S[i + 1] = S[i] + (y[n - P + 1 + i] - mean);
    const half = P / 2, shape = new Float32Array(points);
    for (let p = 0; p < points; p++) {
      const a = (p / (points - 1)) * half, b = P - a;
      const ia = Math.min(Math.floor(a), P - 1), ib = Math.min(Math.floor(b), P - 1);
      shape[p] = (S[ia] + (S[ia + 1] - S[ia]) * (a - ia)) - (S[ib] + (S[ib + 1] - S[ib]) * (b - ib));
    }
    return shape;
  }

  // samples of a plane's run elapsed at song time t
  elapsed(note, plane, t) { return t * this.sr - (note.s + plane.lag); }

  // a plane's period in samples
  period(plane) { return Math.max(4, Math.round(this.sr / plane.f)); }

  // Strobed: the string as a camera would see it with a shutter that fires once a period but `drift` periods late
  // each beat, so the kink seems to run once along the string each beat while the shape keeps its true size and
  // decay. `back` is a fraction of a period before that (the fan of snapshots).
  strobed(note, plane, t, beat, back = 0, points = 241) {
    const e = this.elapsed(note, plane, t), P = this.period(plane);
    if (e < P) return null;
    const phase = (((t - note.t) / beat) % 1) * P - back * P;
    let n = Math.floor(e / P) * P + phase;
    while (n > e) n -= P;
    return this.shapeAt(note, plane, n, points);
  }
}
