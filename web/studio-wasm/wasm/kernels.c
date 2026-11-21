// Songbird's heaviest numba kernels, hand-ported to C for wasm32: the same arithmetic in the same order as
// the Python sources they are named after (songbird/synth/*.py), so that with IEEE doubles and no fused
// multiply-add (wasm has none) they give numba's numbers.
//
// Built without libc (tools/build_wasm.sh): the transcendental functions are imported from JavaScript's
// Math (so they round as the JS port's do), and the module imports Pyodide's own memory, so every pointer
// is a numpy array's data (zero copy). It has no data segment and never uses the linear-memory stack
// (checked by the build), so it writes nothing but the arrays it is handed.

#include <stdint.h>
#ifdef __wasm_simd128__
#include <wasm_simd128.h>
#endif

#define IMPORT(name) __attribute__((import_module("env"), import_name(#name)))
IMPORT(exp) double js_exp(double);
IMPORT(sin) double js_sin(double);
IMPORT(cos) double js_cos(double);
IMPORT(tanh) double js_tanh(double);
IMPORT(log10) double js_log10(double);
IMPORT(pow) double js_pow(double, double);

#define EXPORT(name) __attribute__((export_name(#name)))

static inline double pmin(double a, double b) { return b < a ? b : a; }
static inline double pmax(double a, double b) { return b > a ? b : a; }
static inline int32_t pymod(int32_t a, int32_t b) { int32_t m = a % b; return (m != 0 && ((m < 0) != (b < 0))) ? m + b : m; }
static inline double floor_(double x) { return __builtin_floor(x); }  // wasm f64.floor

// pluck._loop: y (pad + length, zeroed) is the caller's; the result is y[pad:]
EXPORT(pluck_loop)
void pluck_loop(const double *x, int32_t nx, int32_t whole, const double *taps, int32_t n_taps, double gain,
                int32_t release_at, double release_gain, int32_t length, double smooth, double *y) {
  int32_t pad = whole + n_taps;
  double g = gain;
  for (int32_t n = 0; n < length; n++) {
    if (n >= release_at) g = release_gain + (g - release_gain) * smooth;
    double acc = 0.0;
    if (n < nx) acc = x[n];
    int32_t base = pad + n - whole;
    double fb = 0.0;
    for (int32_t k = 0; k < n_taps; k++) fb += taps[k] * y[base - k];
    y[pad + n] = acc + g * fb;
  }
}

// pluck._bank: lines (n_strings x ring, zeroed; ring a power of two at least pad) and out (length) are the
// caller's; each string's line is a ring of its last `ring` values, as in the Python
EXPORT(pluck_bank)
void pluck_bank(const double *x, int32_t length, const int32_t *wholes, const double *taps, int32_t n_strings,
                int32_t n_taps, const double *gains, double coupling, double *lines, int32_t pad, int32_t ring,
                double *out) {
  int32_t mask = ring - 1;
  for (int32_t n = 0; n < length; n++) {
    double drive = coupling * x[n];
    double total = 0.0;
    for (int32_t s = 0; s < n_strings; s++) {
      int32_t base = pad + n - wholes[s];
      double *line = lines + (int64_t)s * ring;
      const double *t = taps + s * n_taps;
      double fb = 0.0;
      for (int32_t k = 0; k < n_taps; k++) fb += t[k] * line[(base - k) & mask];
      double v = drive + gains[s] * fb;
      line[(pad + n) & mask] = v;
      total += v;
    }
    out[n] = total;
  }
}

// fx._four / _two / _one: biquads in cascade over each channel of y (n x chans, C order), in place
EXPORT(fx_four)
void fx_four(double *y, int32_t n, int32_t chans, const double *p, const double *q, const double *r, const double *s) {
  double p0 = p[0], p1 = p[1], p2 = p[2], p4 = p[4], p5 = p[5];
  double q0 = q[0], q1 = q[1], q2 = q[2], q4 = q[4], q5 = q[5];
  double r0 = r[0], r1 = r[1], r2 = r[2], r4 = r[4], r5 = r[5];
  double s0 = s[0], s1 = s[1], s2 = s[2], s4 = s[4], s5 = s[5];
#ifdef __wasm_simd128__
  if (chans == 2) {
    v128_t vp0 = wasm_f64x2_splat(p0), vp1 = wasm_f64x2_splat(p1), vp2 = wasm_f64x2_splat(p2),
           vp4 = wasm_f64x2_splat(p4), vp5 = wasm_f64x2_splat(p5);
    v128_t vq0 = wasm_f64x2_splat(q0), vq1 = wasm_f64x2_splat(q1), vq2 = wasm_f64x2_splat(q2),
           vq4 = wasm_f64x2_splat(q4), vq5 = wasm_f64x2_splat(q5);
    v128_t vr0 = wasm_f64x2_splat(r0), vr1 = wasm_f64x2_splat(r1), vr2 = wasm_f64x2_splat(r2),
           vr4 = wasm_f64x2_splat(r4), vr5 = wasm_f64x2_splat(r5);
    v128_t vs0 = wasm_f64x2_splat(s0), vs1 = wasm_f64x2_splat(s1), vs2 = wasm_f64x2_splat(s2),
           vs4 = wasm_f64x2_splat(s4), vs5 = wasm_f64x2_splat(s5);
    v128_t z1 = wasm_f64x2_splat(0.0), z2 = wasm_f64x2_splat(0.0), w1 = wasm_f64x2_splat(0.0),
           w2 = wasm_f64x2_splat(0.0), u1 = wasm_f64x2_splat(0.0), u2 = wasm_f64x2_splat(0.0),
           t1 = wasm_f64x2_splat(0.0), t2 = wasm_f64x2_splat(0.0);
    for (int32_t i = 0; i < n; i++) {
      double *yp = y + (int64_t)i * 2;
      v128_t v = wasm_v128_load(yp);
      v128_t o = wasm_f64x2_add(wasm_f64x2_mul(vp0, v), z1);
      z1 = wasm_f64x2_add(wasm_f64x2_sub(wasm_f64x2_mul(vp1, v), wasm_f64x2_mul(vp4, o)), z2);
      z2 = wasm_f64x2_sub(wasm_f64x2_mul(vp2, v), wasm_f64x2_mul(vp5, o));
      v128_t u = wasm_f64x2_add(wasm_f64x2_mul(vq0, o), w1);
      w1 = wasm_f64x2_add(wasm_f64x2_sub(wasm_f64x2_mul(vq1, o), wasm_f64x2_mul(vq4, u)), w2);
      w2 = wasm_f64x2_sub(wasm_f64x2_mul(vq2, o), wasm_f64x2_mul(vq5, u));
      v128_t m = wasm_f64x2_add(wasm_f64x2_mul(vr0, u), u1);
      u1 = wasm_f64x2_add(wasm_f64x2_sub(wasm_f64x2_mul(vr1, u), wasm_f64x2_mul(vr4, m)), u2);
      u2 = wasm_f64x2_sub(wasm_f64x2_mul(vr2, u), wasm_f64x2_mul(vr5, m));
      v128_t k = wasm_f64x2_add(wasm_f64x2_mul(vs0, m), t1);
      t1 = wasm_f64x2_add(wasm_f64x2_sub(wasm_f64x2_mul(vs1, m), wasm_f64x2_mul(vs4, k)), t2);
      t2 = wasm_f64x2_sub(wasm_f64x2_mul(vs2, m), wasm_f64x2_mul(vs5, k));
      wasm_v128_store(yp, k);
    }
    return;
  }
#endif
  for (int32_t c = 0; c < chans; c++) {
    double z1 = 0, z2 = 0, w1 = 0, w2 = 0, u1 = 0, u2 = 0, t1 = 0, t2 = 0;
    for (int32_t i = 0; i < n; i++) {
      double v = y[(int64_t)i * chans + c];
      double o = p0 * v + z1;
      z1 = p1 * v - p4 * o + z2;
      z2 = p2 * v - p5 * o;
      double u = q0 * o + w1;
      w1 = q1 * o - q4 * u + w2;
      w2 = q2 * o - q5 * u;
      double m = r0 * u + u1;
      u1 = r1 * u - r4 * m + u2;
      u2 = r2 * u - r5 * m;
      double k = s0 * m + t1;
      t1 = s1 * m - s4 * k + t2;
      t2 = s2 * m - s5 * k;
      y[(int64_t)i * chans + c] = k;
    }
  }
}

EXPORT(fx_two)
void fx_two(double *y, int32_t n, int32_t chans, const double *p, const double *q) {
  double p0 = p[0], p1 = p[1], p2 = p[2], p4 = p[4], p5 = p[5];
  double q0 = q[0], q1 = q[1], q2 = q[2], q4 = q[4], q5 = q[5];
#ifdef __wasm_simd128__
  if (chans == 2) {
    v128_t vp0 = wasm_f64x2_splat(p0), vp1 = wasm_f64x2_splat(p1), vp2 = wasm_f64x2_splat(p2),
           vp4 = wasm_f64x2_splat(p4), vp5 = wasm_f64x2_splat(p5);
    v128_t vq0 = wasm_f64x2_splat(q0), vq1 = wasm_f64x2_splat(q1), vq2 = wasm_f64x2_splat(q2),
           vq4 = wasm_f64x2_splat(q4), vq5 = wasm_f64x2_splat(q5);
    v128_t z1 = wasm_f64x2_splat(0.0), z2 = wasm_f64x2_splat(0.0),
           w1 = wasm_f64x2_splat(0.0), w2 = wasm_f64x2_splat(0.0);
    for (int32_t i = 0; i < n; i++) {
      double *yp = y + (int64_t)i * 2;
      v128_t v = wasm_v128_load(yp);
      v128_t o = wasm_f64x2_add(wasm_f64x2_mul(vp0, v), z1);
      z1 = wasm_f64x2_add(wasm_f64x2_sub(wasm_f64x2_mul(vp1, v), wasm_f64x2_mul(vp4, o)), z2);
      z2 = wasm_f64x2_sub(wasm_f64x2_mul(vp2, v), wasm_f64x2_mul(vp5, o));
      v128_t u = wasm_f64x2_add(wasm_f64x2_mul(vq0, o), w1);
      w1 = wasm_f64x2_add(wasm_f64x2_sub(wasm_f64x2_mul(vq1, o), wasm_f64x2_mul(vq4, u)), w2);
      w2 = wasm_f64x2_sub(wasm_f64x2_mul(vq2, o), wasm_f64x2_mul(vq5, u));
      wasm_v128_store(yp, u);
    }
    return;
  }
#endif
  for (int32_t c = 0; c < chans; c++) {
    double z1 = 0, z2 = 0, w1 = 0, w2 = 0;
    for (int32_t i = 0; i < n; i++) {
      double v = y[(int64_t)i * chans + c];
      double o = p0 * v + z1;
      z1 = p1 * v - p4 * o + z2;
      z2 = p2 * v - p5 * o;
      double u = q0 * o + w1;
      w1 = q1 * o - q4 * u + w2;
      w2 = q2 * o - q5 * u;
      y[(int64_t)i * chans + c] = u;
    }
  }
}

EXPORT(fx_one)
void fx_one(double *y, int32_t n, int32_t chans, const double *p) {
  double p0 = p[0], p1 = p[1], p2 = p[2], p4 = p[4], p5 = p[5];
#ifdef __wasm_simd128__
  if (chans == 2) {
    v128_t vp0 = wasm_f64x2_splat(p0), vp1 = wasm_f64x2_splat(p1), vp2 = wasm_f64x2_splat(p2),
           vp4 = wasm_f64x2_splat(p4), vp5 = wasm_f64x2_splat(p5);
    v128_t z1 = wasm_f64x2_splat(0.0), z2 = wasm_f64x2_splat(0.0);
    for (int32_t i = 0; i < n; i++) {
      double *yp = y + (int64_t)i * 2;
      v128_t v = wasm_v128_load(yp);
      v128_t o = wasm_f64x2_add(wasm_f64x2_mul(vp0, v), z1);
      z1 = wasm_f64x2_add(wasm_f64x2_sub(wasm_f64x2_mul(vp1, v), wasm_f64x2_mul(vp4, o)), z2);
      z2 = wasm_f64x2_sub(wasm_f64x2_mul(vp2, v), wasm_f64x2_mul(vp5, o));
      wasm_v128_store(yp, o);
    }
    return;
  }
#endif
  for (int32_t c = 0; c < chans; c++) {
    double z1 = 0, z2 = 0;
    for (int32_t i = 0; i < n; i++) {
      double v = y[(int64_t)i * chans + c];
      double o = p0 * v + z1;
      z1 = p1 * v - p4 * o + z2;
      z2 = p2 * v - p5 * o;
      y[(int64_t)i * chans + c] = o;
    }
  }
}

// drum._ring: out (n, zeroed) is the caller's
EXPORT(drum_ring)
void drum_ring(const double *freqs, const double *amps, const double *t60s, int32_t n_modes, double glide,
               double glide_time, int32_t n, double sr, double *out) {
  const double PI = 3.141592653589793;
  for (int32_t k = 0; k < n_modes; k++) {
    double f = freqs[k];
    if (f >= 0.45 * sr) continue;
    double decay = js_exp(-6.9078 / (t60s[k] * sr));
    double a = amps[k];
    if (k < 2 && glide > 0.0) {
      double phase = 0.0, g = 1.0;
      double fall = js_exp(-1.0 / (glide_time * sr));
      double bend = glide;
      for (int32_t i = 0; i < n; i++) {
        phase += 2.0 * PI * f * (1.0 + bend) / sr;
        bend *= fall;
        out[i] += a * g * js_sin(phase);
        g *= decay;
        if (g < 1e-5) break;
      }
    } else {
      double w = 2.0 * PI * f / sr;
      double c = 2.0 * decay * js_cos(w);
      double d = decay * decay;
      double y1 = a * decay * js_sin(w);
      double y2 = 0.0;
      out[0] += y2;
      if (n > 1) out[1] += y1;
      for (int32_t i = 2; i < n; i++) {
        double y0 = c * y1 - d * y2;
        out[i] += y0;
        y2 = y1;
        y1 = y0;
        if (i % 256 == 0 && __builtin_fabs(y0) < 1e-6 * __builtin_fabs(a) && __builtin_fabs(y1) < 1e-6 * __builtin_fabs(a)) break;
      }
    }
  }
}

// fx._detect_every: out ((n + step - 1) / step) is the caller's
EXPORT(fx_detect_every)
void fx_detect_every(const double *key, int32_t n, int32_t chans, double coef, int32_t step, double *out) {
  double p = 0.0;
  double one_m = 1.0 - coef;
  int32_t count = (n + step - 1) / step;
  if (chans == 2) {
    for (int32_t k = 0; k < count; k++) {
      int32_t start = (k - 1) * step + 1;
      if (start < 0) start = 0;
      for (int32_t i = start; i < k * step + 1; i++) {
        double a = key[(int64_t)i * 2], b = key[(int64_t)i * 2 + 1];
        double s = a * a + b * b;
        p = coef * p + one_m * s / 2.0;
      }
      out[k] = p;
    }
    return;
  }
  if (chans == 1) {
    for (int32_t k = 0; k < count; k++) {
      int32_t start = (k - 1) * step + 1;
      if (start < 0) start = 0;
      for (int32_t i = start; i < k * step + 1; i++) {
        double a = key[i];
        p = coef * p + one_m * (a * a);
      }
      out[k] = p;
    }
    return;
  }
  for (int32_t k = 0; k < count; k++) {
    int32_t start = (k - 1) * step + 1;
    if (start < 0) start = 0;
    for (int32_t i = start; i < k * step + 1; i++) {
      double s = 0.0;
      for (int32_t c = 0; c < chans; c++) s += key[(int64_t)i * chans + c] * key[(int64_t)i * chans + c];
      p = coef * p + one_m * s / chans;
    }
    out[k] = p;
  }
}

EXPORT(fx_apply)
void fx_apply(const double *x, int32_t n, int32_t chans, const double *lin, int32_t n_lin, int32_t step,
              const double *band, int32_t band_chans, double *y) {
  int split = band_chans == chans;
  int32_t count = (n + step - 1) / step;
#ifdef __wasm_simd128__
  if (chans == 2) {
    double fstep = (double)step;
    for (int32_t k = 0; k < count; k++) {
      int32_t start = k * step;
      int32_t stop = start + step < n ? start + step : n;
      double lk = lin[k];
      if (k + 1 < n_lin) {
        double change = lin[k + 1] - lk;
        if (split) {
          for (int32_t i = start; i < stop; i++) {
            double g = lk + ((double)(i - start) / fstep) * change;
            v128_t vg = wasm_f64x2_splat(g - 1.0);
            int64_t at = (int64_t)i * 2;
            wasm_v128_store(y + at, wasm_f64x2_add(wasm_v128_load(x + at),
                                                   wasm_f64x2_mul(wasm_v128_load(band + at), vg)));
          }
        } else {
          for (int32_t i = start; i < stop; i++) {
            double g = lk + ((double)(i - start) / fstep) * change;
            v128_t vg = wasm_f64x2_splat(g);
            int64_t at = (int64_t)i * 2;
            wasm_v128_store(y + at, wasm_f64x2_mul(wasm_v128_load(x + at), vg));
          }
        }
      } else {
        if (split) {
          v128_t vg = wasm_f64x2_splat(lk - 1.0);
          for (int32_t i = start; i < stop; i++) {
            int64_t at = (int64_t)i * 2;
            wasm_v128_store(y + at, wasm_f64x2_add(wasm_v128_load(x + at),
                                                   wasm_f64x2_mul(wasm_v128_load(band + at), vg)));
          }
        } else {
          v128_t vg = wasm_f64x2_splat(lk);
          for (int32_t i = start; i < stop; i++) {
            int64_t at = (int64_t)i * 2;
            wasm_v128_store(y + at, wasm_f64x2_mul(wasm_v128_load(x + at), vg));
          }
        }
      }
    }
    return;
  }
#endif
  for (int32_t k = 0; k < count; k++) {
    int32_t start = k * step;
    int32_t stop = start + step < n ? start + step : n;
    if (k + 1 < n_lin) {
      double change = lin[k + 1] - lin[k];
      for (int32_t i = start; i < stop; i++) {
        double f = (double)(i - start) / (double)step;
        double g = lin[k] + f * change;
        for (int32_t c = 0; c < chans; c++) {
          int64_t at = (int64_t)i * chans + c;
          y[at] = split ? x[at] + band[at] * (g - 1.0) : x[at] * g;
        }
      }
    } else {
      for (int32_t i = start; i < stop; i++) {
        for (int32_t c = 0; c < chans; c++) {
          int64_t at = (int64_t)i * chans + c;
          y[at] = split ? x[at] + band[at] * (lin[k] - 1.0) : x[at] * lin[k];
        }
      }
    }
  }
}

EXPORT(fx_products)
void fx_products(const double *x, int32_t n, int32_t chans, double *out3) {
  double ll = 0.0, rr = 0.0, lr = 0.0;
  for (int32_t i = 0; i < n; i++) {
    double a = x[(int64_t)i * chans], b = x[(int64_t)i * chans + 1];
    ll += a * a;
    rr += b * b;
    lr += a * b;
  }
  out3[0] = ll;
  out3[1] = rr;
  out3[2] = lr;
}

EXPORT(fx_block_power)
void fx_block_power(const double *x, int32_t n, int32_t chans, int32_t block, double *out) {
  int32_t k = n / block;
  for (int32_t b = 0; b < k; b++) {
    double s = 0.0;
    for (int32_t i = b * block; i < (b + 1) * block; i++)
      for (int32_t c = 0; c < chans; c++) s += x[(int64_t)i * chans + c] * x[(int64_t)i * chans + c];
    out[b] = s / (double)(block * chans);
  }
}

// master._weighted_hop_power: state (4 x chans, zeroed: z1, z2, w1, w2) and out (n / hop, zeroed) are the
// caller's
EXPORT(master_weighted_hop_power)
void master_weighted_hop_power(const double *x, int32_t n, int32_t chans, const double *p, const double *q,
                               int32_t hop, double *state, double *out) {
  int32_t k = n / hop;
  double p0 = p[0], p1 = p[1], p2 = p[2], p4 = p[4], p5 = p[5];
  double q0 = q[0], q1 = q[1], q2 = q[2], q4 = q[4], q5 = q[5];
  if (chans == 2) {
#ifdef __wasm_simd128__
    v128_t vp0 = wasm_f64x2_splat(p0), vp1 = wasm_f64x2_splat(p1), vp2 = wasm_f64x2_splat(p2),
           vp4 = wasm_f64x2_splat(p4), vp5 = wasm_f64x2_splat(p5);
    v128_t vq0 = wasm_f64x2_splat(q0), vq1 = wasm_f64x2_splat(q1), vq2 = wasm_f64x2_splat(q2),
           vq4 = wasm_f64x2_splat(q4), vq5 = wasm_f64x2_splat(q5);
    v128_t z1 = wasm_f64x2_make(state[0], state[1]), z2 = wasm_f64x2_make(state[2], state[3]);
    v128_t w1 = wasm_f64x2_make(state[4], state[5]), w2 = wasm_f64x2_make(state[6], state[7]);
    for (int32_t j = 0; j < k; j++) {
      double s = 0.0;
      for (int32_t i = j * hop; i < (j + 1) * hop; i++) {
        v128_t v = wasm_v128_load(x + (int64_t)i * 2);
        v128_t o = wasm_f64x2_add(wasm_f64x2_mul(vp0, v), z1);
        z1 = wasm_f64x2_add(wasm_f64x2_sub(wasm_f64x2_mul(vp1, v), wasm_f64x2_mul(vp4, o)), z2);
        z2 = wasm_f64x2_sub(wasm_f64x2_mul(vp2, v), wasm_f64x2_mul(vp5, o));
        v128_t u = wasm_f64x2_add(wasm_f64x2_mul(vq0, o), w1);
        w1 = wasm_f64x2_add(wasm_f64x2_sub(wasm_f64x2_mul(vq1, o), wasm_f64x2_mul(vq4, u)), w2);
        w2 = wasm_f64x2_sub(wasm_f64x2_mul(vq2, o), wasm_f64x2_mul(vq5, u));
        v128_t u2 = wasm_f64x2_mul(u, u);
        s += wasm_f64x2_extract_lane(u2, 0);
        s += wasm_f64x2_extract_lane(u2, 1);
      }
      out[j] = s / hop;
    }
    state[0] = wasm_f64x2_extract_lane(z1, 0); state[1] = wasm_f64x2_extract_lane(z1, 1);
    state[2] = wasm_f64x2_extract_lane(z2, 0); state[3] = wasm_f64x2_extract_lane(z2, 1);
    state[4] = wasm_f64x2_extract_lane(w1, 0); state[5] = wasm_f64x2_extract_lane(w1, 1);
    state[6] = wasm_f64x2_extract_lane(w2, 0); state[7] = wasm_f64x2_extract_lane(w2, 1);
    return;
#else
    double z1l = state[0], z2l = state[2], w1l = state[4], w2l = state[6];
    double z1r = state[1], z2r = state[3], w1r = state[5], w2r = state[7];
    for (int32_t j = 0; j < k; j++) {
      double s = 0.0;
      for (int32_t i = j * hop; i < (j + 1) * hop; i++) {
        double v = x[(int64_t)i * 2];
        double o = p0 * v + z1l;
        z1l = p1 * v - p4 * o + z2l;
        z2l = p2 * v - p5 * o;
        double u = q0 * o + w1l;
        w1l = q1 * o - q4 * u + w2l;
        w2l = q2 * o - q5 * u;
        s += u * u;
        v = x[(int64_t)i * 2 + 1];
        o = p0 * v + z1r;
        z1r = p1 * v - p4 * o + z2r;
        z2r = p2 * v - p5 * o;
        u = q0 * o + w1r;
        w1r = q1 * o - q4 * u + w2r;
        w2r = q2 * o - q5 * u;
        s += u * u;
      }
      out[j] = s / hop;
    }
    state[0] = z1l; state[2] = z2l; state[4] = w1l; state[6] = w2l;
    state[1] = z1r; state[3] = z2r; state[5] = w1r; state[7] = w2r;
    return;
#endif
  }
  double *z1 = state, *z2 = state + chans, *w1 = state + 2 * chans, *w2 = state + 3 * chans;
  for (int32_t j = 0; j < k; j++) {
    double s = 0.0;
    for (int32_t i = j * hop; i < (j + 1) * hop; i++)
      for (int32_t c = 0; c < chans; c++) {
        double v = x[(int64_t)i * chans + c];
        double o = p0 * v + z1[c];
        z1[c] = p1 * v - p4 * o + z2[c];
        z2[c] = p2 * v - p5 * o;
        double u = q0 * o + w1[c];
        w1[c] = q1 * o - q4 * u + w2[c];
        w2[c] = q2 * o - q5 * u;
        s += u * u;
      }
    out[j] = s / hop;
  }
}

EXPORT(master_recover)
void master_recover(const double *held, int32_t n, double coef, double *out) {
  double g = 1.0;
  for (int32_t i = 0; i < n; i++) {
    g = 1.0 - (1.0 - g) * coef;
    if (held[i] < g) g = held[i];
    out[i] = g;
  }
}

// bowed._read: cubic Lagrange read `delay` behind `pos` in a circular buffer of `size`
static inline double bowed_read(const double *buf, int32_t size, int32_t pos, double delay) {
  double x = pos - delay;
  int32_t i = (int32_t)floor_(x);
  double f = x - i;
  double a = buf[pymod(i - 1, size)], b = buf[pymod(i, size)], c = buf[pymod(i + 1, size)], d = buf[pymod(i + 2, size)];
  double wa = -f * (f - 1.0) * (f - 2.0) / 6.0;
  double wb = (f + 1.0) * (f - 1.0) * (f - 2.0) / 2.0;
  double wc = -(f + 1.0) * f * (f - 2.0) / 2.0;
  double wd = (f + 1.0) * f * (f - 1.0) / 6.0;
  return wa * a + wb * b + wc * c + wd * d;
}

// bowed.run: to_nut, to_bridge (4096 each, zeroed) and out (n) are the caller's
EXPORT(bowed_run)
void bowed_run(const double *period, const double *bridge_len, const double *bow_v, const double *grip,
               const double *noise, int32_t n, double pole, double gain, double *to_nut, double *to_bridge, double *out) {
  const int32_t size = 4096;
  double lp = 0.0;
  for (int32_t t = 0; t < n; t++) {
    double lb = bridge_len[t];
    double ln = period[t] - lb;
    double arriving = bowed_read(to_bridge, size, t, lb);
    lp = (1.0 - pole) * arriving + pole * lp;
    double from_bridge = -gain * lp;
    double from_nut = -bowed_read(to_nut, size, t, ln);
    double v_string = from_bridge + from_nut;
    double v = 0.0;
    if (bow_v[t] != 0.0) {
      double dv = bow_v[t] - v_string + noise[t];
      double r = __builtin_fabs(0.25 * dv / grip[t]) + 0.75;
      r = js_pow(r, -4.0);
      if (r > 1.0) r = 1.0;
      v = dv * r;
    }
    to_nut[pymod(t, size)] = from_bridge + v;
    to_bridge[pymod(t, size)] = from_nut + v;
    out[t] = arriving;
  }
}

// pipe.run: bore (8192, zeroed) and out (n) are the caller's
EXPORT(pipe_run)
void pipe_run(const double *freq, const double *breath, const double *chiff, const double *drive, const double *aim,
              const double *noise, int32_t n, double feedback, double damping, double sr, double *bore, double *out) {
  const int32_t size = 8192;
  const double PI = 3.141592653589793;
  double phase = 0.0, lp = 0.0, turb_lp = 0.0;
  for (int32_t t = 0; t < n; t++) {
    double f = freq[t];
    phase += f / sr;
    if (phase > 1.0) phase -= 1.0;
    double jet = js_sin(2.0 * PI * phase);
    double k = drive[t];
    double flow = js_tanh(k * jet + aim[t]) - js_tanh(aim[t]);
    turb_lp = 0.35 * noise[t] + 0.65 * turb_lp;
    double turb = turb_lp * (0.6 + 0.4 * jet) * (0.1 * breath[t] + chiff[t]);
    double x = flow * breath[t] / (k + 0.3) + turb;
    double period = sr / f - damping / (1.0 - damping);
    double pos = t - period;
    int32_t i = (int32_t)floor_(pos);
    double frac = pos - i;
    double back = (1.0 - frac) * bore[pymod(i, size)] + frac * bore[pymod(i + 1, size)];
    lp = (1.0 - damping) * back + damping * lp;
    double y = x + feedback * lp;
    bore[pymod(t, size)] = y;
    out[t] = y;
  }
}

// instruments._placed: place a mono or stereo signal into stereo out (out may alias y when stereo)
EXPORT(instruments_placed)
void instruments_placed(const double *y, int32_t n, int32_t chans, double c, double s, double root2, double width,
                        double *out) {
#ifdef __wasm_simd128__
  v128_t vcs = wasm_f64x2_make(c, s), vr2 = wasm_f64x2_splat(root2);
  if (chans == 1) {
    for (int32_t i = 0; i < n; i++) {
      v128_t v = wasm_f64x2_splat(y[i]);
      wasm_v128_store(out + (int64_t)i * 2, wasm_f64x2_mul(wasm_f64x2_mul(v, vcs), vr2));
    }
    return;
  }
  if (chans == 2) {
    v128_t vsign = wasm_f64x2_make(width, -width);
    for (int32_t i = 0; i < n; i++) {
      int64_t at = (int64_t)i * 2;
      double l = y[at], r = y[at + 1];
      v128_t mid = wasm_f64x2_splat(0.5 * (l + r));
      v128_t side = wasm_f64x2_mul(wasm_f64x2_splat(0.5 * (l - r)), vsign);
      wasm_v128_store(out + at, wasm_f64x2_add(wasm_f64x2_mul(wasm_f64x2_mul(mid, vcs), vr2), side));
    }
    return;
  }
#endif
  if (chans == 1) {
    for (int32_t i = 0; i < n; i++) {
      double v = y[i];
      out[(int64_t)i * 2] = (v * c) * root2;
      out[(int64_t)i * 2 + 1] = (v * s) * root2;
    }
  } else {
    for (int32_t i = 0; i < n; i++) {
      double l = y[(int64_t)i * chans], r = y[(int64_t)i * chans + 1];
      double mid = 0.5 * (l + r);
      double side = (0.5 * (l - r)) * width;
      out[(int64_t)i * 2] = (mid * c) * root2 + side;
      out[(int64_t)i * 2 + 1] = (mid * s) * root2 - side;
    }
  }
}

static inline int32_t fx_extended(int32_t p, int32_t n, int32_t reflect) {
  if (!reflect) return p < 0 ? 0 : (p >= n ? n - 1 : p);
  while (p < 0 || p >= n) p = p < 0 ? -p - 1 : 2 * n - 1 - p;
  return p;
}

// fx._sliding_min: qi (int32_t, cap) and qv (double, cap) are scratch buffers of length cap = before + after + 2
EXPORT(fx_sliding_min)
void fx_sliding_min(const double *x, int32_t n, int32_t before, int32_t after, int32_t reflect, int32_t *qi,
                    double *qv, double *out) {
  int32_t cap = before + after + 2;
  int32_t head = 0, count = 0, nxt = -before;
  for (int32_t i = 0; i < n; i++) {
    while (nxt <= i + after) {
      int32_t src = (nxt >= 0 && nxt < n) ? nxt : fx_extended(nxt, n, reflect);
      double v = x[src];
      while (count > 0) {
        int32_t tail = head + count - 1;
        if (tail >= cap) tail -= cap;
        if (qv[tail] < v) break;
        count--;
      }
      int32_t pos = head + count;
      if (pos >= cap) pos -= cap;
      qi[pos] = nxt;
      qv[pos] = v;
      count++;
      nxt++;
    }
    while (qi[head] < i - before) {
      if (++head == cap) head = 0;
      count--;
    }
    out[i] = qv[head];
  }
}

// fx._running_mean: ring (size) is scratch; out may alias x
EXPORT(fx_running_mean)
void fx_running_mean(const double *x, int32_t n, int32_t size, double *ring, double *out) {
  int32_t size1 = size / 2;
  double total = 0.0;
  for (int32_t j = 0; j < size; j++) {
    int32_t idx = j - size1;
    if (idx < 0) idx = 0;
    else if (idx >= n) idx = n - 1;
    double v = x[idx];
    ring[j] = v;
    total += v;
  }
  double fs = (double)size;
  out[0] = total / fs;
  int32_t k = 0;
  for (int32_t i = 1; i < n; i++) {
    double gone = ring[k];
    int32_t idx = i - 1 + size - size1;
    if (idx < 0) idx = 0;
    else if (idx >= n) idx = n - 1;
    double v = x[idx];
    ring[k] = v;
    if (++k == size) k = 0;
    total += v - gone;
    out[i] = total / fs;
  }
}

EXPORT(fx_follow)
void fx_follow(const double *x, int32_t n, int32_t chans, double detect, double rise, double fall, double floor_db,
               double span_db, double *out) {
  double p = 0.0, a = 0.0;
  for (int32_t i = 0; i < n; i++) {
    double s = 0.0;
    for (int32_t c = 0; c < chans; c++) {
      double v = x[(int64_t)i * chans + c];
      s += v * v;
    }
    p = detect * p + (1.0 - detect) * s / chans;
    double t = (10.0 * js_log10(p + 1e-20) - floor_db) / span_db;
    t = pmin(pmax(t, 0.0), 1.0);
    double coef = t > a ? rise : fall;
    a = coef * a + (1.0 - coef) * t;
    out[i] = a;
  }
}

EXPORT(fx_block_peaks)
void fx_block_peaks(const double *x, int32_t n, int32_t chans, int32_t block, double *out) {
  int32_t k = n / block;
  for (int32_t b = 0; b < k; b++) {
    double m = 0.0;
    for (int32_t i = b * block; i < (b + 1) * block; i++)
      for (int32_t c = 0; c < chans; c++) {
        double v = __builtin_fabs(x[(int64_t)i * chans + c]);
        if (v > m) m = v;
      }
    out[b] = m;
  }
}

static inline double fx_soft(double v) {
  if (v >= 3.0) return 1.0;
  if (v <= -3.0) return -1.0;
  double w = v * v;
  return v * (27.0 + w) / (27.0 + 9.0 * w);
}

EXPORT(fx_saturate)
void fx_saturate(const double *x, int32_t n, int32_t chans, double k, double bias, double dc, double *y) {
  double th = fx_soft(bias);
  double w = bias * bias;
  double denom = 27.0 + 9.0 * w;
  double slope = (729.0 - 162.0 * w + 9.0 * w * w) / (denom * denom);
  double norm = 1.0 / (k * slope);
#ifdef __wasm_simd128__
  if (chans == 2) {
    v128_t vk = wasm_f64x2_splat(k), vbias = wasm_f64x2_splat(bias), vth = wasm_f64x2_splat(th),
           vnorm = wasm_f64x2_splat(norm), vdc = wasm_f64x2_splat(dc);
    v128_t v3 = wasm_f64x2_splat(3.0), vm3 = wasm_f64x2_splat(-3.0), v1 = wasm_f64x2_splat(1.0),
           vm1 = wasm_f64x2_splat(-1.0), v27 = wasm_f64x2_splat(27.0), v9 = wasm_f64x2_splat(9.0);
    v128_t prev_in = wasm_f64x2_splat(0.0), prev_out = wasm_f64x2_splat(0.0);
    for (int32_t i = 0; i < n; i++) {
      int64_t at = (int64_t)i * 2;
      v128_t u = wasm_f64x2_add(wasm_f64x2_mul(vk, wasm_v128_load(x + at)), vbias);
      v128_t u2 = wasm_f64x2_mul(u, u);
      v128_t soft = wasm_f64x2_div(wasm_f64x2_mul(u, wasm_f64x2_add(v27, u2)),
                                   wasm_f64x2_add(v27, wasm_f64x2_mul(v9, u2)));
      soft = wasm_v128_bitselect(vm1, soft, wasm_f64x2_le(u, vm3));
      soft = wasm_v128_bitselect(v1, soft, wasm_f64x2_ge(u, v3));
      v128_t v = wasm_f64x2_mul(wasm_f64x2_sub(soft, vth), vnorm);
      v128_t out = wasm_f64x2_add(wasm_f64x2_sub(v, prev_in), wasm_f64x2_mul(vdc, prev_out));
      prev_in = v;
      prev_out = out;
      wasm_v128_store(y + at, out);
    }
    return;
  }
#endif
  for (int32_t c = 0; c < chans; c++) {
    double prev_in = 0.0, prev_out = 0.0;
    for (int32_t i = 0; i < n; i++) {
      double v = (fx_soft(k * x[(int64_t)i * chans + c] + bias) - th) * norm;
      double out = v - prev_in + dc * prev_out;
      prev_in = v;
      prev_out = out;
      y[(int64_t)i * chans + c] = out;
    }
  }
}

EXPORT(fx_hold)
void fx_hold(const uint8_t *playing, double *track, int32_t n) {
  int32_t last = 0;
  for (int32_t i = 0; i < n; i++) {
    if (playing[i]) last = i;
    else track[i] = track[last];
  }
}

EXPORT(fx_span)
void fx_span(const double *x, int32_t n, int32_t chans, double floor, int32_t *out2) {
  int32_t first = -1, last = -1;
  for (int32_t i = 0; i < n; i++) {
    for (int32_t c = 0; c < chans; c++) {
      if (__builtin_fabs(x[(int64_t)i * chans + c]) > floor) { first = i; break; }
    }
    if (first >= 0) break;
  }
  for (int32_t i = n - 1; i >= 0; i--) {
    for (int32_t c = 0; c < chans; c++) {
      if (__builtin_fabs(x[(int64_t)i * chans + c]) > floor) { last = i; break; }
    }
    if (last >= 0) break;
  }
  out2[0] = first;
  out2[1] = last;
}

EXPORT(fx_ballistics)
void fx_ballistics(const double *target, int32_t n, double attack, double release, double *out) {
  double g = 0.0;
  for (int32_t i = 0; i < n; i++) {
    double t = target[i];
    double c = t < g ? attack : release;
    g = c * g + (1.0 - c) * t;
    out[i] = g;
  }
}

EXPORT(master_windows)
void master_windows(const double *y, int32_t n, int32_t chans, int32_t ch, const int32_t *points, int32_t n_pts,
                    int32_t reach, double *out) {
  int32_t width = 2 * reach + 1;
  for (int32_t r = 0; r < n_pts; r++) {
    int32_t p = points[r];
    int32_t top = p + reach;
    double *row = out + (int64_t)r * width;
    if (p >= reach && top < n) {
      for (int32_t j = 0; j < width; j++) row[j] = y[(int64_t)(top - j) * chans + ch];
    } else {
      for (int32_t j = 0; j < width; j++) {
        int32_t i = top - j;
        row[j] = (i >= 0 && i < n) ? y[(int64_t)i * chans + ch] : 0.0;
      }
    }
  }
}

EXPORT(master_mean_ahead)
void master_mean_ahead(const double *recovered, int32_t n, int32_t ahead, const double *need, double *ring,
                       double *out) {
  int32_t size = ahead + 2;
  ring[0] = 0.0;
  double first = recovered[0];
  double s = 0.0;
  for (int32_t m = 0; m < ahead; m++) {
    s = m == 0 ? first : s + first;
    ring[(m + 1) % size] = s;
  }
  double width = (double)(ahead + 1);
  int32_t widx = (ahead + 1) % size;
  int32_t ridx = 0;
  for (int32_t i = 0; i < n; i++) {
    int32_t m = i + ahead;
    double v = recovered[i];
    s = m == 0 ? v : s + v;
    ring[widx] = s;
    if (++widx == size) widx = 0;
    double g = (s - ring[ridx]) / width;
    if (++ridx == size) ridx = 0;
    out[i] = pmin(need[i], g);
  }
}

EXPORT(master_abs_max)
void master_abs_max(const double *y, int32_t n, int32_t chans, double *out) {
  if (chans == 2) {
    for (int32_t i = 0; i < n; i++) {
      double a = __builtin_fabs(y[(int64_t)i * 2]);
      double b = __builtin_fabs(y[(int64_t)i * 2 + 1]);
      out[i] = pmax(a, b);
    }
    return;
  }
  for (int32_t i = 0; i < n; i++) {
    double m = __builtin_fabs(y[(int64_t)i * chans]);
    for (int32_t c = 1; c < chans; c++) m = pmax(m, __builtin_fabs(y[(int64_t)i * chans + c]));
    out[i] = m;
  }
}

EXPORT(master_over)
void master_over(const double *x, int32_t n, double a, uint8_t *out) {
  for (int32_t i = 0; i < n; i++) out[i] = __builtin_fabs(x[i]) > a ? 1 : 0;
}

// Fused true_peak_envelope inner loop (py/web_patches.py): for each point r and each channel ch, computes
// max(abs(window(y, ch, point, reach) @ taps_t)) in the exact left-to-right sum order of Pyodide's numpy matmul
// (no BLAS) and updates between[r] = max(between[r], m). Eliminates the (65536, 65) window buffer and numpy's
// scalar matmul loop. taps_t is (width x 4, C order: taps.T made contiguous).
EXPORT(master_true_peak_swing)
void master_true_peak_swing(const double *y, int32_t n, int32_t chans, const int32_t *points, int32_t n_pts,
                            int32_t reach, const double *taps_t, double *between) {
  int32_t width = 2 * reach + 1;
  for (int32_t ch = 0; ch < chans; ch++) {
    for (int32_t r = 0; r < n_pts; r++) {
      int32_t p = points[r];
      int32_t top = p + reach;
#ifdef __wasm_simd128__
      v128_t s01 = wasm_f64x2_splat(0.0), s23 = wasm_f64x2_splat(0.0);
      if (p >= reach && top < n) {
        const double *yp = y + (int64_t)top * chans + ch;
        const double *tp = taps_t;
        for (int32_t j = 0; j < width; j++, yp -= chans, tp += 4) {
          v128_t xv = wasm_f64x2_splat(*yp);
          s01 = wasm_f64x2_add(s01, wasm_f64x2_mul(xv, wasm_v128_load(tp)));
          s23 = wasm_f64x2_add(s23, wasm_f64x2_mul(xv, wasm_v128_load(tp + 2)));
        }
      } else {
        const double *tp = taps_t;
        for (int32_t j = 0; j < width; j++, tp += 4) {
          int32_t i = top - j;
          double v = (i >= 0 && i < n) ? y[(int64_t)i * chans + ch] : 0.0;
          v128_t xv = wasm_f64x2_splat(v);
          s01 = wasm_f64x2_add(s01, wasm_f64x2_mul(xv, wasm_v128_load(tp)));
          s23 = wasm_f64x2_add(s23, wasm_f64x2_mul(xv, wasm_v128_load(tp + 2)));
        }
      }
      s01 = wasm_f64x2_abs(s01);
      s23 = wasm_f64x2_abs(s23);
      double m0 = pmax(wasm_f64x2_extract_lane(s01, 0), wasm_f64x2_extract_lane(s01, 1));
      double m1 = pmax(wasm_f64x2_extract_lane(s23, 0), wasm_f64x2_extract_lane(s23, 1));
      double m = pmax(m0, m1);
      if (m > between[r]) between[r] = m;
#else
      double s0 = 0.0, s1 = 0.0, s2 = 0.0, s3 = 0.0;
      if (p >= reach && top < n) {
        const double *yp = y + (int64_t)top * chans + ch;
        const double *tp = taps_t;
        for (int32_t j = 0; j < width; j++, yp -= chans, tp += 4) {
          double v = *yp;
          s0 += v * tp[0]; s1 += v * tp[1]; s2 += v * tp[2]; s3 += v * tp[3];
        }
      } else {
        const double *tp = taps_t;
        for (int32_t j = 0; j < width; j++, tp += 4) {
          int32_t i = top - j;
          double v = (i >= 0 && i < n) ? y[(int64_t)i * chans + ch] : 0.0;
          s0 += v * tp[0]; s1 += v * tp[1]; s2 += v * tp[2]; s3 += v * tp[3];
        }
      }
      double m = pmax(pmax(__builtin_fabs(s0), __builtin_fabs(s1)), pmax(__builtin_fabs(s2), __builtin_fabs(s3)));
      if (m > between[r]) between[r] = m;
#endif
    }
  }
}

EXPORT(reed_read)
double reed_read(const double *wave, int32_t size, const double *increments, const double *amplitude, int32_t n,
                 double *out, int32_t offset, double phase) {
  for (int32_t i = 0; i < n; i++) {
    phase += increments[i];
    if (phase >= 1.0) phase -= 1.0;
    double x = phase * size;
    int32_t j = (int32_t)x;
    double f = x - j;
    out[offset + i] += amplitude[i] * ((1.0 - f) * wave[pymod(j, size)] + f * wave[pymod(j + 1, size)]);
  }
  return phase;
}

EXPORT(throat_to_bins)
void throat_to_bins(const double *values, int32_t rows, int32_t cols, const int32_t *lo, const int32_t *hi,
                    const double *before, const double *after, const uint8_t *above, const double *rolloff,
                    int32_t nbins, int32_t log_power, double *out_t) {
  for (int32_t c = 0; c < nbins; c++) {
    int32_t l = lo[c], h = hi[c];
    double b = before[c], a = after[c];
    int32_t do_sub = log_power && above[c];
    double sub = do_sub ? rolloff[c] : 0.0;
    double *dst = out_t + (int64_t)c * rows;
    if (do_sub) {
      for (int32_t r = 0; r < rows; r++) {
        const double *vr = values + (int64_t)r * cols;
        dst[r] = (vr[l] * b + vr[h] * a) - sub;
      }
    } else {
      for (int32_t r = 0; r < rows; r++) {
        const double *vr = values + (int64_t)r * cols;
        dst[r] = vr[l] * b + vr[h] * a;
      }
    }
  }
}

EXPORT(throat_turn_phase)
void throat_turn_phase(const double *bins, const double *hz, const double *frac, const double *period, int32_t rows,
                       int32_t nbins, const double *spread, int32_t has_spread, const double *scatter,
                       int32_t scat_cols, int32_t has_scatter, const int32_t *lo, const int32_t *hi,
                       const double *before, const double *after, double sr, double fft, double tx_spread,
                       double tx_scatter, double scatter_from, double scatter_span, double *out) {
  const double neg_two_pi = -2.0 * 3.141592653589793;
  for (int32_t r = 0; r < rows; r++) {
    double fr = frac[r], per = period[r];
    double sp_scale = (tx_spread * per) / sr;
    const double *sr_row = has_scatter ? scatter + (int64_t)r * scat_cols : 0;
    double *dst = out + (int64_t)r * nbins;
    for (int32_t c = 0; c < nbins; c++) {
      double t = ((neg_two_pi * bins[c]) * fr) / fft;
      if (has_spread) t += sp_scale * spread[c];
      if (has_scatter) {
        double h = (hz[c] * per) / sr;
        h -= scatter_from;
        h /= scatter_span;
        if (h < 0.0) h = 0.0;
        else if (h > 1.0) h = 1.0;
        h *= tx_scatter;
        double sm = sr_row[lo[c]] * before[c] + sr_row[hi[c]] * after[c];
        h *= sm;
        t += h;
      }
      dst[c] = t;
    }
  }
}

EXPORT(throat_noise_mask)
void throat_noise_mask(double *noise, int32_t rows, int32_t cols, const int32_t *m) {
  for (int32_t r = 0; r < rows; r++) {
    double *row = noise + (int64_t)r * cols;
    for (int32_t c = m[r]; c < cols; c++) row[c] = 0.0;
  }
}

EXPORT(throat_noise_sub_dc)
void throat_noise_sub_dc(double *noise, int32_t rows, int32_t cols, const int32_t *m, const double *dc) {
  for (int32_t r = 0; r < rows; r++) {
    int32_t mr = m[r] < cols ? m[r] : cols;
    double d = dc[r];
    double *row = noise + (int64_t)r * cols;
    for (int32_t c = 0; c < mr; c++) row[c] -= d;
  }
}

EXPORT(throat_assemble)
void throat_assemble(const double *periodic, const double *aperiodic, int32_t rows, int32_t fft, const double *hann,
                     int32_t lead, double *out) {
  int32_t half = fft / 2, pre = half - lead, post = fft - lead, width = fft + half;
  for (int32_t r = 0; r < rows; r++) {
    const double *per = periodic + (int64_t)r * fft;
    const double *aper = aperiodic + (int64_t)r * fft;
    double *dst = out + (int64_t)r * width;
    double dc = 0.0;
    for (int32_t c = 0; c < fft; c++) dc += per[c];
    for (int32_t k = 0; k < pre; k++) dst[k] = 0.0 - dc * hann[k];
    for (int32_t k = pre; k < half; k++) dst[k] = per[k + half] - dc * hann[k];
    for (int32_t k = half; k < fft; k++) dst[k] = (per[k - half] + aper[k - half]) - dc * hann[k];
    for (int32_t k = fft; k < half + post; k++) dst[k] = per[k - half] + aper[k - half];
    for (int32_t k = half + post; k < width; k++) dst[k] = 0.0 + aper[k - half];
  }
}

EXPORT(throat_lay)
void throat_lay(double *y, const int32_t *at, const double *response, int32_t rows, int32_t width) {
  for (int32_t r = 0; r < rows; r++) {
    double *dst = y + at[r];
    const double *src = response + (int64_t)r * width;
    for (int32_t k = 0; k < width; k++) dst[k] += src[k];
  }
}

EXPORT(throat_assemble_lay)
void throat_assemble_lay(double *y, const int32_t *at, const double *periodic, const double *aperiodic, int32_t rows,
                         int32_t fft, const double *hann, int32_t lead) {
  int32_t half = fft / 2, pre = half - lead, post = fft - lead, width = fft + half;
  for (int32_t r = 0; r < rows; r++) {
    double *dst = y + at[r];
    const double *per = periodic + (int64_t)r * fft;
    const double *aper = aperiodic + (int64_t)r * fft;
    double dc = 0.0;
    for (int32_t c = 0; c < fft; c++) dc += per[c];
#ifdef __wasm_simd128__
    if ((pre & 1) == 0 && (half & 1) == 0 && (post & 1) == 0 && (fft & 1) == 0) {
      v128_t vdc = wasm_f64x2_splat(dc), vz = wasm_f64x2_splat(0.0);
      for (int32_t k = 0; k < pre; k += 2) {
        v128_t val = wasm_f64x2_sub(vz, wasm_f64x2_mul(vdc, wasm_v128_load(hann + k)));
        wasm_v128_store(dst + k, wasm_f64x2_add(wasm_v128_load(dst + k), val));
      }
      for (int32_t k = pre; k < half; k += 2) {
        v128_t val = wasm_f64x2_sub(wasm_v128_load(per + k + half), wasm_f64x2_mul(vdc, wasm_v128_load(hann + k)));
        wasm_v128_store(dst + k, wasm_f64x2_add(wasm_v128_load(dst + k), val));
      }
      for (int32_t k = half; k < fft; k += 2) {
        v128_t sum = wasm_f64x2_add(wasm_v128_load(per + k - half), wasm_v128_load(aper + k - half));
        v128_t val = wasm_f64x2_sub(sum, wasm_f64x2_mul(vdc, wasm_v128_load(hann + k)));
        wasm_v128_store(dst + k, wasm_f64x2_add(wasm_v128_load(dst + k), val));
      }
      for (int32_t k = fft; k < half + post; k += 2) {
        v128_t val = wasm_f64x2_add(wasm_v128_load(per + k - half), wasm_v128_load(aper + k - half));
        wasm_v128_store(dst + k, wasm_f64x2_add(wasm_v128_load(dst + k), val));
      }
      for (int32_t k = half + post; k < width; k += 2) {
        v128_t val = wasm_f64x2_add(vz, wasm_v128_load(aper + k - half));
        wasm_v128_store(dst + k, wasm_f64x2_add(wasm_v128_load(dst + k), val));
      }
      continue;
    }
#endif
    for (int32_t k = 0; k < pre; k++) dst[k] += 0.0 - dc * hann[k];
    for (int32_t k = pre; k < half; k++) dst[k] += per[k + half] - dc * hann[k];
    for (int32_t k = half; k < fft; k++) dst[k] += (per[k - half] + aper[k - half]) - dc * hann[k];
    for (int32_t k = fft; k < half + post; k++) dst[k] += per[k - half] + aper[k - half];
    for (int32_t k = half + post; k < width; k++) dst[k] += 0.0 + aper[k - half];
  }
}

#ifdef __wasm_simd128__
// throat._matmul (x @ W.T) as Pyodide's scipy computes it, BLAS dgemm: the build with -msimd128 only
// (kernels-simd.wasm; py/web_patches.py). Every output is summed exactly as that OpenBLAS (0.3.31, built for
// RISCV64_GENERIC: dgemm's Q 120, unroll 2, its generic 2x2 kernel) sums it: C zeroed (beta 0), then for each
// block of k in turn, its products summed one after another from zero, added to C. The blocks are level3.c's:
// Q at a time while at least 2Q remain, then what remains if no more than Q, else half of it rounded up to
// the unroll (480: four of 120; 160: 80 and 80). Found by experiment against blas.dgemm, which it equals bit
// for bit (tools/check_kernels.py; web_patches checks again before using it). Two outputs of a row at a time,
// one in each f64x2 lane; wasm has no fused multiply-add, so a product rounds before it is added, as there.

#define MM_Q 120
#define MM_UNROLL 2

static inline int32_t mm_block(int32_t left) {
  if (left >= 2 * MM_Q) return MM_Q;
  if (left > MM_Q) return ((left / 2 + MM_UNROLL - 1) / MM_UNROLL) * MM_UNROLL;
  return left;
}

// rows i..i+R of out, columns j..j+2V: for each block of k, R x V sums of products in f64x2 lanes, then added
// to out (to 0.0 for the first: C's zeros). Called with constant R and V, each call its own code; 2 x 4 keeps
// the eight sums, four of W's pairs and one of x in registers
static inline __attribute__((always_inline)) void mm_tile(const double *x, int32_t k, const double *wt, int32_t m,
                                                          double *out, int32_t i, int32_t j, int R, int V) {
  for (int32_t k0 = 0; k0 < k;) {
    int32_t k1 = k0 + mm_block(k - k0);
    v128_t s[2][4];
    for (int r = 0; r < R; r++)
      for (int v = 0; v < V; v++) s[r][v] = wasm_f64x2_splat(0.0);
    for (int32_t q = k0; q < k1; q++) {
      const double *w = wt + (int64_t)q * m + j;
      v128_t b[4];
      for (int v = 0; v < V; v++) b[v] = wasm_v128_load(w + 2 * v);
      for (int r = 0; r < R; r++) {
        v128_t a = wasm_f64x2_splat(x[(int64_t)(i + r) * k + q]);
        for (int v = 0; v < V; v++) s[r][v] = wasm_f64x2_add(s[r][v], wasm_f64x2_mul(a, b[v]));
      }
    }
    for (int r = 0; r < R; r++)
      for (int v = 0; v < V; v++) {
        double *o = out + (int64_t)(i + r) * m + j + 2 * v;
        v128_t c = k0 == 0 ? wasm_f64x2_splat(0.0) : wasm_v128_load(o);
        wasm_v128_store(o, wasm_f64x2_add(c, s[r][v]));
      }
    k0 = k1;
  }
}

// out (n x m, C order) = x (n x k, C order) times wt (k x m, C order: W.T made contiguous)
EXPORT(matmul_blas)
void matmul_blas(const double *x, int32_t n, int32_t k, const double *wt, int32_t m, double *out) {
  int32_t m8 = m & ~7, m2 = m & ~1;
  for (int32_t i0 = 0; i0 < n; i0 += 64) {  // 64 rows of x at a time, kept in cache across every column
    int32_t i1 = i0 + 64 < n ? i0 + 64 : n;
    int32_t i2 = i0 + ((i1 - i0) & ~1);
    for (int32_t j = 0; j < m8; j += 8) {
      for (int32_t i = i0; i < i2; i += 2) mm_tile(x, k, wt, m, out, i, j, 2, 4);
      if (i2 < i1) mm_tile(x, k, wt, m, out, i2, j, 1, 4);
    }
    for (int32_t j = m8; j < m2; j += 2) {
      for (int32_t i = i0; i < i2; i += 2) mm_tile(x, k, wt, m, out, i, j, 2, 1);
      if (i2 < i1) mm_tile(x, k, wt, m, out, i2, j, 1, 1);
    }
    if (m > m2)  // the last column alone, in plain doubles: the same sums
      for (int32_t i = i0; i < i1; i++) {
        double c = 0.0;
        for (int32_t k0 = 0; k0 < k;) {
          int32_t k1 = k0 + mm_block(k - k0);
          double s = 0.0;
          for (int32_t q = k0; q < k1; q++) s = s + x[(int64_t)i * k + q] * wt[(int64_t)q * m + m2];
          c = c + s;
          k0 = k1;
        }
        out[(int64_t)i * m + m2] = c;
      }
  }
}
#endif
