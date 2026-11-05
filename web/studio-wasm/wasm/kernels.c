// Songbird's heaviest numba kernels, hand-ported to C for wasm32: the same arithmetic in the same order as
// the Python sources they are named after (songbird/synth/*.py), so that with IEEE doubles and no fused
// multiply-add (wasm has none) they give numba's numbers.
//
// Built without libc (tools/build_wasm.sh): the transcendental functions are imported from JavaScript's
// Math (so they round as the JS port's do), and the module imports Pyodide's own memory, so every pointer
// is a numpy array's data (zero copy). It has no data segment and never uses the linear-memory stack
// (checked by the build), so it writes nothing but the arrays it is handed.

#include <stdint.h>

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
  for (int32_t c = 0; c < chans; c++) {
    double z1 = 0, z2 = 0, w1 = 0, w2 = 0, u1 = 0, u2 = 0, t1 = 0, t2 = 0;
    for (int32_t i = 0; i < n; i++) {
      double v = y[(int64_t)i * chans + c];
      double o = p[0] * v + z1;
      z1 = p[1] * v - p[4] * o + z2;
      z2 = p[2] * v - p[5] * o;
      double u = q[0] * o + w1;
      w1 = q[1] * o - q[4] * u + w2;
      w2 = q[2] * o - q[5] * u;
      double m = r[0] * u + u1;
      u1 = r[1] * u - r[4] * m + u2;
      u2 = r[2] * u - r[5] * m;
      double k = s[0] * m + t1;
      t1 = s[1] * m - s[4] * k + t2;
      t2 = s[2] * m - s[5] * k;
      y[(int64_t)i * chans + c] = k;
    }
  }
}

EXPORT(fx_two)
void fx_two(double *y, int32_t n, int32_t chans, const double *p, const double *q) {
  for (int32_t c = 0; c < chans; c++) {
    double z1 = 0, z2 = 0, w1 = 0, w2 = 0;
    for (int32_t i = 0; i < n; i++) {
      double v = y[(int64_t)i * chans + c];
      double o = p[0] * v + z1;
      z1 = p[1] * v - p[4] * o + z2;
      z2 = p[2] * v - p[5] * o;
      double u = q[0] * o + w1;
      w1 = q[1] * o - q[4] * u + w2;
      w2 = q[2] * o - q[5] * u;
      y[(int64_t)i * chans + c] = u;
    }
  }
}

EXPORT(fx_one)
void fx_one(double *y, int32_t n, int32_t chans, const double *p) {
  for (int32_t c = 0; c < chans; c++) {
    double z1 = 0, z2 = 0;
    for (int32_t i = 0; i < n; i++) {
      double v = y[(int64_t)i * chans + c];
      double o = p[0] * v + z1;
      z1 = p[1] * v - p[4] * o + z2;
      z2 = p[2] * v - p[5] * o;
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
  int32_t count = (n + step - 1) / step;
  for (int32_t k = 0; k < count; k++) {
    int32_t start = (k - 1) * step + 1;
    if (start < 0) start = 0;
    for (int32_t i = start; i < k * step + 1; i++) {
      double s = 0.0;
      for (int32_t c = 0; c < chans; c++) s += key[(int64_t)i * chans + c] * key[(int64_t)i * chans + c];
      p = coef * p + (1.0 - coef) * s / chans;
    }
    out[k] = p;
  }
}

EXPORT(fx_apply)
void fx_apply(const double *x, int32_t n, int32_t chans, const double *lin, int32_t n_lin, int32_t step,
              const double *band, int32_t band_chans, double *y) {
  int split = band_chans == chans;
  int32_t count = (n + step - 1) / step;
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
  if (chans == 2) {
    double z1l = state[0], z2l = state[2], w1l = state[4], w2l = state[6];
    double z1r = state[1], z2r = state[3], w1r = state[5], w2r = state[7];
    for (int32_t j = 0; j < k; j++) {
      double s = 0.0;
      for (int32_t i = j * hop; i < (j + 1) * hop; i++) {
        double v = x[(int64_t)i * 2];
        double o = p[0] * v + z1l;
        z1l = p[1] * v - p[4] * o + z2l;
        z2l = p[2] * v - p[5] * o;
        double u = q[0] * o + w1l;
        w1l = q[1] * o - q[4] * u + w2l;
        w2l = q[2] * o - q[5] * u;
        s += u * u;
        v = x[(int64_t)i * 2 + 1];
        o = p[0] * v + z1r;
        z1r = p[1] * v - p[4] * o + z2r;
        z2r = p[2] * v - p[5] * o;
        u = q[0] * o + w1r;
        w1r = q[1] * o - q[4] * u + w2r;
        w2r = q[2] * o - q[5] * u;
        s += u * u;
      }
      out[j] = s / hop;
    }
    state[0] = z1l; state[2] = z2l; state[4] = w1l; state[6] = w2l;
    state[1] = z1r; state[3] = z2r; state[5] = w1r; state[7] = w2r;
    return;
  }
  double *z1 = state, *z2 = state + chans, *w1 = state + 2 * chans, *w2 = state + 3 * chans;
  for (int32_t j = 0; j < k; j++) {
    double s = 0.0;
    for (int32_t i = j * hop; i < (j + 1) * hop; i++)
      for (int32_t c = 0; c < chans; c++) {
        double v = x[(int64_t)i * chans + c];
        double o = p[0] * v + z1[c];
        z1[c] = p[1] * v - p[4] * o + z2[c];
        z2[c] = p[2] * v - p[5] * o;
        double u = q[0] * o + w1[c];
        w1[c] = q[1] * o - q[4] * u + w2[c];
        w2[c] = q[2] * o - q[5] * u;
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

#ifdef __wasm_simd128__
// throat._matmul (x @ W.T) as Pyodide's scipy computes it, BLAS dgemm: the build with -msimd128 only
// (kernels-simd.wasm; py/web_patches.py). Every output is summed exactly as that OpenBLAS (0.3.31, built for
// RISCV64_GENERIC: dgemm's Q 120, unroll 2, its generic 2x2 kernel) sums it: C zeroed (beta 0), then for each
// block of k in turn, its products summed one after another from zero, added to C. The blocks are level3.c's:
// Q at a time while at least 2Q remain, then what remains if no more than Q, else half of it rounded up to
// the unroll (480: four of 120; 160: 80 and 80). Found by experiment against blas.dgemm, which it equals bit
// for bit (tools/check_kernels.py; web_patches checks again before using it). Two outputs of a row at a time,
// one in each f64x2 lane; wasm has no fused multiply-add, so a product rounds before it is added, as there.
#include <wasm_simd128.h>

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
