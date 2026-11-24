// Small math for scenes: clamps, mixes, eases. Every function is pure.

export const clamp = (x, lo = 0, hi = 1) => Math.min(Math.max(x, lo), hi);
export const mix = (a, b, k) => a + (b - a) * k;
export const remap = (x, a0, a1, b0 = 0, b1 = 1) => b0 + (b1 - b0) * ((x - a0) / (a1 - a0));
export const remapClamped = (x, a0, a1, b0 = 0, b1 = 1) => b0 + (b1 - b0) * clamp((x - a0) / (a1 - a0));
export const smoothstep = (e0, e1, x) => {
  const k = clamp((x - e0) / (e1 - e0));
  return k * k * (3 - 2 * k);
};
export const smootherstep = (e0, e1, x) => {
  const k = clamp((x - e0) / (e1 - e0));
  return k * k * k * (k * (k * 6 - 15) + 10);
};
export const fract = (x) => x - Math.floor(x);
export const TAU = Math.PI * 2;

// eases on [0, 1] -> [0, 1]
export const ease = {
  linear: (k) => clamp(k),
  inQuad: (k) => clamp(k) ** 2,
  outQuad: (k) => 1 - (1 - clamp(k)) ** 2,
  inOutQuad: (k) => { k = clamp(k); return k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2; },
  inCubic: (k) => clamp(k) ** 3,
  outCubic: (k) => 1 - (1 - clamp(k)) ** 3,
  inOutCubic: (k) => { k = clamp(k); return k < 0.5 ? 4 * k ** 3 : 1 - (-2 * k + 2) ** 3 / 2; },
  outExpo: (k) => { k = clamp(k); return k === 1 ? 1 : 1 - 2 ** (-10 * k); },
  inOutSine: (k) => -(Math.cos(Math.PI * clamp(k)) - 1) / 2,
  outBack: (k) => { k = clamp(k); const c = 1.70158; return 1 + (c + 1) * (k - 1) ** 3 + c * (k - 1) ** 2; },
};

// a value that rises over [t0, t0 + rise] and falls over [t1, t1 + fall]: a note's light
export const envelope = (t, t0, t1, rise, fall) =>
  smoothstep(t0, t0 + Math.max(rise, 1e-6), t) * (1 - smoothstep(t1, t1 + Math.max(fall, 1e-6), t));

// a damped decay since t0 (0 before it)
export const decay = (t, t0, tau) => (t < t0 ? 0 : Math.exp(-(t - t0) / tau));

// MIDI pitch to hertz
export const hz = (p) => 440 * 2 ** ((p - 69) / 12);

// 2D helpers
export const lerp2 = (a, b, k) => [mix(a[0], b[0], k), mix(a[1], b[1], k)];
export const dist2 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

// a centripetal Catmull-Rom curve through points [[x, y], ...], `per` samples per span
export function spline(points, per = 8) {
  if (points.length < 3) return points.slice();
  const out = [];
  const P = [points[0], ...points, points[points.length - 1]];
  for (let i = 1; i < P.length - 2; i++) {
    const [p0, p1, p2, p3] = [P[i - 1], P[i], P[i + 1], P[i + 2]];
    for (let k = 0; k < per; k++) {
      const s = k / per, s2 = s * s, s3 = s2 * s;
      out.push([0, 1].map((d) => 0.5 * (2 * p1[d] + (-p0[d] + p2[d]) * s + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * s2 +
        (-p0[d] + 3 * p1[d] - 3 * p2[d] + p3[d]) * s3)));
    }
  }
  out.push(points[points.length - 1]);
  return out;
}
