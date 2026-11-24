// The frame drum's skin re-run from its captured modes (physics/drum.json, physics/drum-modes.bin):
//   z(rho, phi, T) = sum over hits, modes k: strike_k J_m(j_k rho) cos(m_k (phi - theta)) exp(-6.9078 tau / T60_k) sin(phase_k(tau))
// tau = T - the hit's time; phase_k = 2 pi f0 ratio_k tau, the two lowest modes starting `glide` sharp and falling back
// with time constant glide_time (as hit() does). rho 0 at the centre to 1 at the rim. A pressed stroke (its `choke`
// [left, tau], as play() does) stops what the earlier hits still ring where it lands: from its time t_c on, their part
// of z is multiplied by left + (1 - left) exp(-(T - t_c) / tau).
//
// Slow motion: the skin shown at song time t is its true state at T(t). From each hit to the next, T starts at the
// hit running `rate` times slower than the song and speeds up smoothly (an exponential ramp) so that it reaches the
// next hit exactly when the song does: the first moments after each strike are seen slowed, the rest of the ring
// passes quickly, and each hit starts from the skin as the earlier hits truly left it.
//
// drawSkin draws it as an engraving: one ring a radius, each line's weight the skin's shade there.
import { smoothstep, clamp } from '../../core/math.js';

// J_0..J_mmax at x, by Miller's backward recurrence normalised with J_0 + 2 sum J_2k = 1
export function besselJ(x, mmax) {
  const out = new Float64Array(mmax + 1);
  if (x === 0) { out[0] = 1; return out; }
  const M = 2 * Math.ceil((Math.max(mmax, x) + 30) / 2);
  let jp = 0, j = 1e-300, sum = 0;
  const tmp = new Float64Array(M + 2);
  for (let m = M; m >= 1; m--) {
    const jm = (2 * m / x) * j - jp;
    jp = j; j = jm;
    tmp[m - 1] = jm;
    if ((m - 1) % 2 === 0 && m - 1 > 0) sum += 2 * jm;
    if (Math.abs(j) > 1e250) { // rescale
      for (let q = m - 1; q <= M; q++) tmp[q] *= 1e-250;
      j *= 1e-250; jp *= 1e-250; sum *= 1e-250;
    }
  }
  sum += tmp[0];
  for (let m = 0; m <= mmax; m++) out[m] = tmp[m] / sum;
  return out;
}

export class Skin {
  // nr radii (rho = i / (nr - 1)), na angles (phi = 2 pi j / na) on a polar grid
  constructor(drumJson, modes, { nr = 49, na = 192, rate = 40 } = {}) {
    this.hits = drumJson.hits;
    this.modes = drumJson.modes;
    this.K = this.modes.length;
    this.M = Math.max(...this.modes.map((m) => m.m));
    this.amp = modes.values;   // [hits, K, 3]: amp, T60, strike
    this.nr = nr; this.na = na; this.rate = rate;
    // J_m(j_k rho_i)
    this.R = new Float32Array(this.K * nr);
    for (let i = 0; i < nr; i++) {
      const rho = i / (nr - 1);
      this.modes.forEach((md, k) => { this.R[k * nr + i] = besselJ(md.j * rho, md.m)[md.m]; });
    }
    this.cos = new Float32Array((this.M + 1) * na);
    this.sin = new Float32Array((this.M + 1) * na);
    for (let m = 0; m <= this.M; m++) for (let j = 0; j < na; j++) {
      this.cos[m * na + j] = Math.cos(m * 2 * Math.PI * j / na);
      this.sin[m * na + j] = Math.sin(m * 2 * Math.PI * j / na);
    }
    // the ramp's shape a: its slope at the hit is a / (e^a - 1) of the average, set to 1 / rate
    let lo = 0.01, hi = 30;
    for (let it = 0; it < 80; it++) { const a = (lo + hi) / 2; if (a / Math.expm1(a) > 1 / rate) lo = a; else hi = a; }
    this.a = (lo + hi) / 2;
    this.A = new Float64Array((this.M + 1) * nr);
    this.B = new Float64Array((this.M + 1) * nr);
    this.z = new Float32Array(nr * na);
  }

  // the index of the latest hit at or before t, or -1
  hitAt(t) {
    let i = -1;
    for (let h = 0; h < this.hits.length; h++) if (this.hits[h].t <= t) i = h;
    return i;
  }

  // what is left at true time T of hit h's ring after the later hits' chokes
  left(h, T) {
    let g = 1;
    for (let c = h + 1; c < this.hits.length && this.hits[c].t <= T; c++) {
      const ch = this.hits[c].choke;
      if (ch) g *= ch[0] + (1 - ch[0]) * Math.exp(-(T - this.hits[c].t) / ch[1]);
    }
    return g;
  }

  // the size of hit h's own ring tau seconds after it, free of its oscillation: the root sum square of its modes'
  // decaying strike amplitudes
  size(h, tau) {
    let s = 0;
    for (let k = 0; k < this.K; k++) {
      const base = (h * this.K + k) * 3, a = this.amp[base + 2] * Math.exp(-6.9078 * tau / this.amp[base + 1]);
      s += a * a;
    }
    return Math.sqrt(s);
  }

  // the true time shown at song time t (see above)
  shown(t) {
    const h = this.hitAt(t);
    if (h < 0) return t;
    const t0 = this.hits[h].t, t1 = h + 1 < this.hits.length ? this.hits[h + 1].t : t0 + 2;
    const D = t1 - t0, u = Math.min((t - t0) / D, 1);
    return t0 + D * Math.expm1(this.a * u) / Math.expm1(this.a);
  }

  // z on the polar grid at true time T, into this.z (row i: radius i, column j: angle j); returns the peak |z|.
  // gainOf(hit, tau, h): a factor on hit h's ring tau seconds after it; phaseOf(hit, tau): the time its modes' phases
  // are read at (tau itself by default)
  at(T, { window = 1.5, gainOf = null, phaseOf = null } = {}) {
    const { K, nr, na, M, A, B, z } = this;
    A.fill(0); B.fill(0);
    for (let h = 0; h < this.hits.length; h++) {
      const hit = this.hits[h], tau = T - hit.t;
      if (tau < 0 || tau > window) continue;
      const g = (gainOf ? gainOf(hit, tau, h) : 1) * this.left(h, T);
      const tp = phaseOf ? phaseOf(hit, tau) : tau;
      for (let k = 0; k < K; k++) {
        const md = this.modes[k], base = (h * K + k) * 3;
        const T60 = this.amp[base + 1], strike = this.amp[base + 2];
        let ph = 2 * Math.PI * hit.f0 * md.ratio * tp;
        if (k < 2 && hit.glide) ph += 2 * Math.PI * hit.f0 * md.ratio * hit.glide * hit.glide_time * (1 - Math.exp(-tp / hit.glide_time));
        const c = g * strike * Math.exp(-6.9078 * tau / T60) * Math.sin(ph);
        if (c === 0) continue;
        const m = md.m, ca = Math.cos(m * hit.theta), sa = Math.sin(m * hit.theta);
        for (let i = 0; i < nr; i++) {
          const r = this.R[k * nr + i] * c;
          A[m * nr + i] += r * ca; B[m * nr + i] += r * sa;
        }
      }
    }
    // cos(m (phi - theta)) = cos m phi cos m theta + sin m phi sin m theta
    let peak = 0;
    for (let i = 0; i < nr; i++) for (let j = 0; j < na; j++) {
      let s = 0;
      for (let m = 0; m <= M; m++) s += A[m * nr + i] * this.cos[m * na + j] + B[m * nr + i] * this.sin[m * na + j];
      z[i * na + j] = s;
      peak = Math.max(peak, Math.abs(s));
    }
    return peak;
  }
}

// The skin at song time t as an engraver's rings, its plane centred at world D.c, radius D.R, tilted D.tilt from
// facing the camera, line weights times D.scale. add(z, nr, na) changes the grid before it is drawn; gainOf, phaseOf as at();
// rimAlpha the outer ring's alpha (times alpha). Returns the outer ring's points on the frame and their scales.
export function drawSkin(ctx, t, target, cam, S, ink, alpha, D, { add = null, gainOf = null, phaseOf = null, rimAlpha = 1 } = {}) {
  const T = S.shown(t);
  S.at(T, { gainOf, phaseOf });
  const { nr, na, z } = S, R = D.R;
  if (add) add(z, nr, na);
  const c = Math.cos(D.tilt), sn = Math.sin(D.tilt);
  const ZS = 0.09 * R;   // world units of skin displacement per unit of z
  const P = (i, j) => {
    const rho = i / (nr - 1), phi = (2 * Math.PI * j) / na, h = z[i * na + (j % na)] * ZS;
    const u = rho * R * Math.cos(phi), v = rho * R * Math.sin(phi);
    // the skin's plane: u across, v receding (down and toward the camera); its normal points up and toward us
    return [D.c[0] + u, D.c[1] + v * c - h * sn, D.c[2] + v * sn + h * c];
  };
  // an engraver's rings: each a line whose weight is the skin's shade there (light from the upper left), so the
  // moving surface is drawn by the swelling and thinning of its lines
  const slope = (i, j) => {
    const i0 = Math.max(i - 1, 0), i1 = Math.min(i + 1, nr - 1);
    const dr = (z[i1 * na + j] - z[i0 * na + j]) / ((i1 - i0) / (nr - 1));
    const dp = (z[i * na + ((j + 1) % na)] - z[i * na + ((j + na - 1) % na)]) / (2 * (2 * Math.PI / na) * Math.max(i / (nr - 1), 0.05));
    const phi = (2 * Math.PI * j) / na;
    return [dr * Math.cos(phi) - dp * Math.sin(phi), dr * Math.sin(phi) + dp * Math.cos(phi)];
  };
  const light = [-0.6, -0.8];
  let rimOut = null;
  for (let i = 1; i < nr; i++) {
    const pts = [], wid = [];
    for (let j = 0; j <= na; j++) {
      pts.push(P(i, j));
      const g = slope(i, j % na);
      const shade = clamp(0.5 + 0.9 * (g[0] * light[0] + g[1] * light[1]) * ZS / R, 0, 1);
      wid.push((0.45 + 2.5 * shade * shade) * D.scale);
    }
    const rim = i === nr - 1;
    const q = pts.map((p) => cam.project(p));
    if (rim) rimOut = { points: q.map((p) => [p.x, p.y]), scale: q.map((p) => p.scale) };
    const a = alpha * (rim ? rimAlpha : 0.92);
    if (a <= 0.002) continue;
    ctx.g.stroke(target, q.map((p) => [p.x, p.y]), {
      width: (j) => (rim ? 3.4 : wid[j]) * q[j].scale, color: ink.ink, alpha: a,
    });
  }
  // where the stick landed, while the shown ring passes its first 25 ms: a bass stroke (the hand's heel, near the
  // centre) a full disc as wide as its contact; a tip stroke (a fingertip, near the rim) a ring round a fine point
  const h = S.hitAt(t);
  if (h >= 0) {
    const hit = S.hits[h], tau = T - hit.t;
    const a = alpha * (1 - smoothstep(0.006, 0.025, tau));
    if (a > 0.01) {
      const u = hit.r * R * Math.cos(hit.theta), v = hit.r * R * Math.sin(hit.theta);
      const q = cam.project([D.c[0] + u, D.c[1] + v * c, D.c[2] + v * sn]);
      const r = hit.contact_ms * 4.5 * q.scale * D.scale;
      if (hit.stroke === 'tip') {
        const ring = [];
        for (let j = 0; j <= 48; j++) {
          const ph = (2 * Math.PI * j) / 48;
          ring.push([q.x + r * 2.6 * Math.cos(ph), q.y + r * 2.6 * Math.sin(ph) * c]);
        }
        ctx.g.stroke(target, ring, { width: 1.6, color: ink.red, alpha: a });
        ctx.g.points(target, [{ x: q.x, y: q.y, r: 2.4, color: ink.red, alpha: a }]);
      } else {
        ctx.g.points(target, [{ x: q.x, y: q.y, r, color: ink.red, alpha: a * 0.9 }]);
      }
    }
  }
  return rimOut;
}
