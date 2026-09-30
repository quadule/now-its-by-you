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

// pluck._bank: lines (n_strings x (pad + length), zeroed) and out (length) are the caller's
EXPORT(pluck_bank)
void pluck_bank(const double *x, int32_t length, const int32_t *wholes, const double *taps, int32_t n_strings,
                int32_t n_taps, const double *gains, double coupling, double *lines, int32_t pad, double *out) {
  int32_t width = pad + length;
  for (int32_t n = 0; n < length; n++) {
    double drive = coupling * x[n];
    double total = 0.0;
    for (int32_t s = 0; s < n_strings; s++) {
      int32_t base = pad + n - wholes[s];
      const double *line = lines + (int64_t)s * width;
      const double *t = taps + s * n_taps;
      double fb = 0.0;
      for (int32_t k = 0; k < n_taps; k++) fb += t[k] * line[base - k];
      double v = drive + gains[s] * fb;
      lines[(int64_t)s * width + pad + n] = v;
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

EXPORT(fx_detect)
void fx_detect(const double *key, int32_t n, int32_t chans, double coef, double *out) {
  double p = 0.0;
  for (int32_t i = 0; i < n; i++) {
    double s = 0.0;
    for (int32_t c = 0; c < chans; c++) s += key[(int64_t)i * chans + c] * key[(int64_t)i * chans + c];
    p = coef * p + (1.0 - coef) * s / chans;
    out[i] = p;
  }
}

EXPORT(fx_apply)
void fx_apply(const double *x, int32_t n, int32_t chans, const double *lin, int32_t n_lin, int32_t step,
              const double *band, int32_t band_chans, double *y) {
  int split = band_chans == chans;
  for (int32_t i = 0; i < n; i++) {
    int32_t k = i / step;
    double f = (double)(i - k * step) / (double)step;
    double g = (k + 1 >= n_lin) ? lin[k] : lin[k] + f * (lin[k + 1] - lin[k]);
    for (int32_t c = 0; c < chans; c++) {
      int64_t at = (int64_t)i * chans + c;
      y[at] = split ? x[at] + band[at] * (g - 1.0) : x[at] * g;
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

EXPORT(master_hop_power)
void master_hop_power(const double *y, int32_t n, int32_t chans, int32_t hop, double *out) {
  int32_t k = n / hop;
  for (int32_t j = 0; j < k; j++) {
    double s = 0.0;
    for (int32_t i = j * hop; i < (j + 1) * hop; i++)
      for (int32_t c = 0; c < chans; c++) s += y[(int64_t)i * chans + c] * y[(int64_t)i * chans + c];
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
