// What a lantern's screen shows during the song: one of a few shapes, drawn on the board from a 20-byte record
// the laptop sends each frame, so the laptop moves them by changing the numbers. The screen is portrait, 135 x 240,
// below the arch of the case; everything is centered on it.
//
// A record: [id][scene][r g b][r2 g2 b2][a][b][c][d][e][f][g][h][i][j][k][backlight]. The shape is drawn in the
// first color over the second; a to k are the scene's own:
//   0 dark      the second color alone
//   1 glow      a soft disc: a radius, b softness
//   2 ring      a circle's outline: a radius, b thickness
//   3 ripples   rings moving out from the center: b spacing, c phase (one turn = 256)
//   4 rays      spokes from the center: a length, b count / 10, c rotation (one turn = 256)
//   5 rise      the screen filled from the bottom: a height, b softness of the edge
//   6 arch      the case's outline: a inset, b thickness, c how bright its inside is
//   7 bands     horizontal stripes drifting: b how many / 16, c phase (one turn = 256)
//   8 mouth     a superellipse with lips: a how open, b how wide, c how square (an "oo" is round), d how high
//               (128 the middle), e its tilt (128 level), f the lips' thickness, g how bright its inside is
//   9 face      the mouth (a to g as above) with two eyes above it: h how open they are (0 shut), i where they
//               look (128 ahead, 0 to the left, 255 to the right), j their size, k how far apart
//   10 dot      a soft disc anywhere: a its radius, b softness, c a faint halo around it, d its height (0 the
//               top, 255 the bottom), e its place across (128 the middle)
// backlight 0 turns the screen off (an LCD's black still glows on a dark stage).
//
// Every shape is a function of one thing per pixel (its distance from the center, its angle, its height, or its
// distance from the arch), so those are worked out once at start (a quarter of the screen, by symmetry) and each
// frame only makes a table from that thing to brightness: a frame takes a few ms. The mouth is worked out per pixel,
// but only in the box around it.

#pragma once
#include <TFT_eSPI.h>

struct Scene {
  uint8_t kind, r, g, b, r2, g2, b2, a, pb, c, pd, pe, pf, pg, ph, pi, pj, pk, backlight;  // a to k
};

namespace scenes {

const int W = 135, H = 240;
const int QW = 68, QH = 120;   // a quarter: columns 67..134 and rows 120..239, mirrored to the rest
const int DIST_STEPS = 8;      // distances in eighths of a pixel
const int MAX_DIST = 140 * DIST_STEPS;
const int ARCH_STEPS = 4;      // distances to the arch in quarters of a pixel
const int ARCH_OFFSET = 80 * ARCH_STEPS, ARCH_RANGE = 2 * ARCH_OFFSET;

uint16_t *dist;    // [QH][QW] distance from the center
uint8_t *angle;    // [QH][QW] angle in the quarter, 0-64 of a 256 turn
int16_t *arch;     // [H][QW] signed distance to the arch (inside negative), right half
uint8_t lut[MAX_DIST + 1 > ARCH_RANGE + 1 ? MAX_DIST + 1 : ARCH_RANGE + 1];
uint8_t spin[256];
uint16_t color[256];

inline float clamp01(float x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
inline float smooth(float e0, float e1, float x) {
  float t = clamp01((x - e0) / (e1 - e0));
  return t * t * (3 - 2 * t);
}
inline uint8_t byte(float v) { return (uint8_t)(clamp01(v) * 255 + 0.5f); }

void begin() {
  dist = (uint16_t *)malloc(QW * QH * 2);
  angle = (uint8_t *)malloc(QW * QH);
  arch = (int16_t *)malloc(QW * H * 2);
  for (int qy = 0; qy < QH; qy++)
    for (int qx = 0; qx < QW; qx++) {
      float dx = qx, dy = qy + 0.5f;  // the center is column 67 and between rows 119 and 120
      dist[qy * QW + qx] = min((int)(sqrtf(dx * dx + dy * dy) * DIST_STEPS + 0.5f), MAX_DIST);
      angle[qy * QW + qx] = (uint8_t)(atan2f(dy, dx) / (2 * PI) * 256 + 0.5f);
    }
  // the arch: the case's shape, a rectangle with a half circle on top whose center is W/2 down from the top
  const float half = W / 2.0f;
  for (int y = 0; y < H; y++)
    for (int qx = 0; qx < QW; qx++) {
      float sd;
      if (y < half) sd = sqrtf(qx * qx + (y - half) * (y - half)) - half;
      else sd = fmaxf(qx - half, y - (H - 1));
      arch[y * QW + qx] = (int16_t)(sd * ARCH_STEPS);
    }
}

// lut[i]: brightness at distance i / DIST_STEPS from the center
void radial(const Scene &s) {
  for (int i = 0; i <= MAX_DIST; i++) {
    float d = i / (float)DIST_STEPS, v = 0;
    switch (s.kind) {
      case 1: {
        float radius = s.a * 0.6f, soft = 1 + s.pb * 0.5f;
        v = smooth(radius + soft, radius - soft, d);
        break;
      }
      case 2: {
        float radius = s.a * 0.6f, half = (1 + s.pb / 8.0f) / 2;
        v = clamp01(half + 0.5f - fabsf(d - radius));
        break;
      }
      case 3: {
        float spacing = 8 + s.pb / 2.0f;
        float w = 0.5f + 0.5f * cosf(2 * PI * (d / spacing - s.c / 256.0f));
        v = w * w * w * w * clamp01(1 - d / 150);
        break;
      }
      case 4:
        v = smooth(s.a * 0.6f + 3, s.a * 0.6f - 3, d);
        break;
    }
    lut[i] = byte(v);
  }
}

void fill(TFT_eSprite &sprite, uint8_t level) {
  uint16_t *px = (uint16_t *)sprite.getPointer();
  for (int i = 0; i < W * H; i++) px[i] = color[level];
}

// x to the power p for x > 0, to about 0.5%: powf is far too slow to call three times a pixel
inline float fastPow(float x, float p) {
  union { float f; uint32_t i; } v = {x};
  float e = (float)(int)((v.i >> 23) & 255) - 127;
  v.i = (v.i & 0x007FFFFF) | 0x3F800000;  // the mantissa, 1-2
  float m = v.f;
  float lg = e + (-0.34484843f * m + 2.02466578f) * m - 0.67487759f;
  float q = p * lg;
  if (q < -126) return 0;
  if (q > 126) q = 126;
  int w = (int)floorf(q);
  float z = q - w;
  union { uint32_t i; float f; } s = {(uint32_t)(w + 127) << 23};
  return s.f * (1 + z * (0.69606564f + z * (0.22449433f + z * 0.07944023f)));
}

// The mouth: everything per frame, so a pixel costs a few multiplies, one division and one square root.
struct Mouth {
  float invHw, invHh, n, invN, nm1, cs, sn, cy, lipHalf, inside;
  Mouth(const Scene &s) {
    float hh = 3 + s.a / 255.0f * 110, hw = 20 + s.pb / 255.0f * 47;
    n = 2 + s.c / 255.0f * 4, invN = 1 / n, nm1 = n - 1;
    invHw = 1 / hw, invHh = 1 / hh;
    float tilt = (s.pe - 128) / 128.0f * 0.5f;
    cs = cosf(tilt), sn = sinf(tilt), cy = 119.5f + (s.pd - 128);
    lipHalf = (1.5f + s.pf / 20.0f) / 2 + 0.5f, inside = s.pg / 255.0f;
  }
  // brightness at (px, py) from its center: its lips, and its inside; show.html draws the same
  float level(float px, float py) const {
    float rx = fabsf(px * cs + py * sn) * invHw + 1e-4f, ry = fabsf(-px * sn + py * cs) * invHh + 1e-4f;
    float gx = fastPow(rx, nm1), gy = fastPow(ry, nm1);  // rx^(n-1): the gradient's parts
    float sum = gx * rx + gy * ry;
    float F = fastPow(sum, invN);
    // distance ~ (F - 1) / |grad F|, |grad F| = F / sum * |(gx / hw, gy / hh)|
    float g2 = sq(gx * invHw) + sq(gy * invHh);
    float sd = (F - 1) * sum / (F * sqrtf(g2));
    return fmaxf(clamp01(lipHalf - fabsf(sd)), inside * clamp01(0.5f - sd));
  }
};

// The mouth, drawn over what is there, centered across the screen.
void drawMouth(uint16_t *px, const Scene &s) {
  float hh = 3 + s.a / 255.0f * 110, hw = 20 + s.pb / 255.0f * 47, n = 2 + s.c / 255.0f * 4;
  float tilt = (s.pe - 128) / 128.0f * 0.5f, cs = cosf(tilt), sn = sinf(tilt);
  float cy = 119.5f + (s.pd - 128);
  float lip = 1.5f + s.pf / 20.0f;
  // the box around it, tilted: wide enough for its corners and lips
  float rx = fabsf(hw * cs) + fabsf(hh * sn) + lip + 2, ry = fabsf(hw * sn) + fabsf(hh * cs) + lip + 2;
  int x0 = max(0, (int)(67 - rx)), x1 = min(W - 1, (int)(67 + rx + 1));
  int y0 = max(0, (int)(cy - ry)), y1 = min(H - 1, (int)(cy + ry + 1));
  // it is the same turned half a turn about its center (column 67, row cy, which is on a half row): each
  // pixel in the top half of the box is drawn twice. Along a row it is sampled every STEP pixels and worked out
  // pixel by pixel only between samples that differ: the lips are wider than STEP, so no edge hides between two
  // samples that agree.
  const int STEP = 4;
  Mouth m(s);
  int mirror = (int)(2 * cy);  // row y's partner is mirror - y
  uint8_t coarse[W / STEP + 2];
  for (int y = y0; y <= y1 && y <= mirror - y; y++) {
    uint16_t *row = px + y * W, *other = px + (mirror - y) * W;
    bool both = mirror - y <= y1 && mirror - y < H;
    float py = y - cy;
    int k = 0;
    for (int x = x0; x <= x1; x += STEP) coarse[k++] = byte(m.level(x - 67.0f, py));
    k = 0;
    for (int x = x0; x <= x1; x += STEP, k++) {
      int end = min(x + STEP, x1 + 1);
      bool same = end > x1 || coarse[k] == coarse[k + 1];
      for (int xx = x; xx < end; xx++) {
        uint16_t c = color[same || xx == x ? coarse[k] : byte(m.level(xx - 67.0f, py))];
        row[xx] = c;
        if (both) other[W - 1 - xx] = c;
      }
    }
  }
}

// Two eyes over what is there: ellipses that shut to a line, moving together to look aside.
void drawEyes(uint16_t *px, const Scene &s) {
  float r = 6 + s.pj / 255.0f * 24, ry = fmaxf(1.2f, r * s.ph / 255.0f);
  float gaze = (s.pi - 128) / 128.0f * 22, apart = 18 + s.pk / 255.0f * 30;
  float ey = 70 + (s.pd - 128) * 0.3f;  // they follow the mouth's height a little
  float invR = 1 / r, invRy = 1 / ry;
  for (int side = -1; side <= 1; side += 2) {
    float ex = 67 + side * apart + gaze;
    int x0 = max(0, (int)(ex - r - 2)), x1 = min(W - 1, (int)(ex + r + 2));
    int y0 = max(0, (int)(ey - ry - 2)), y1 = min(H - 1, (int)(ey + ry + 2));
    for (int y = y0; y <= y1; y++) {
      float dy = (y - ey) * invRy;
      for (int x = x0; x <= x1; x++) {
        float dx = (x - ex) * invR, F = sqrtf(dx * dx + dy * dy);
        float v = clamp01(0.5f - (F - 1) * ry);  // about a pixel's distance from the edge
        if (v > 0) px[y * W + x] = color[byte(v)];
      }
    }
  }
}

// A soft disc with a faint halo, over what is there.
void drawDot(uint16_t *px, const Scene &s) {
  float cx = 67 + (s.pe - 128) / 128.0f * 60, cy = s.pd / 255.0f * (H - 1);
  float r = 2 + s.a * 0.25f, soft = 1 + s.pb * 0.1f, halo = s.c / 255.0f;
  float reach = r + soft + (halo > 0 ? 1.5f * r + 2 : 0);
  int x0 = max(0, (int)(cx - reach)), x1 = min(W - 1, (int)(cx + reach + 1));
  int y0 = max(0, (int)(cy - reach)), y1 = min(H - 1, (int)(cy + reach + 1));
  for (int y = y0; y <= y1; y++)
    for (int x = x0; x <= x1; x++) {
      float d = sqrtf(sq(x - cx) + sq(y - cy));
      float out = clamp01(1 - (d - r) / (1.5f * r + 2));
      float v = fmaxf(smooth(r + soft, r - soft, d), halo * 0.5f * out * out);
      if (v > 0) px[y * W + x] = color[byte(v)];
    }
}

void render(TFT_eSprite &sprite, const Scene &s) {
  // the colors, from the ground's (0) to the shape's (255), in the screen's byte order as a sprite keeps them
  for (int v = 0; v < 256; v++) {
    float t = v / 255.0f;
    uint8_t r = s.r2 + (s.r - s.r2) * t, g = s.g2 + (s.g - s.g2) * t, b = s.b2 + (s.b - s.b2) * t;
    uint16_t c = ((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3);
    color[v] = (c >> 8) | (c << 8);
  }
  uint16_t *px = (uint16_t *)sprite.getPointer();
  const int CX = 67, CY = 120;
  if (s.kind >= 1 && s.kind <= 4) {
    radial(s);
    if (s.kind == 4) {
      int n = max(1, s.pb / 10);
      for (int i = 0; i < 256; i++) {
        float w = 0.5f + 0.5f * cosf(n * (i / 256.0f * 2 * PI));
        spin[i] = byte(powf(w, 12));
      }
    }
    uint8_t rot = s.c;
    for (int qy = 0; qy < QH; qy++) {
      uint16_t *below = px + (CY + qy) * W, *above = px + (CY - 1 - qy) * W;
      for (int qx = 0; qx < QW; qx++) {
        uint8_t v = lut[dist[qy * QW + qx]];
        if (s.kind != 4) {
          below[CX + qx] = below[CX - qx] = above[CX + qx] = above[CX - qx] = color[v];
          continue;
        }
        // rays: the angle differs in each quarter (y grows downward: below-right is the first)
        uint8_t a = angle[qy * QW + qx];
        below[CX + qx] = color[v * spin[(uint8_t)(a - rot)] / 255];
        below[CX - qx] = color[v * spin[(uint8_t)(128 - a - rot)] / 255];
        above[CX - qx] = color[v * spin[(uint8_t)(128 + a - rot)] / 255];
        above[CX + qx] = color[v * spin[(uint8_t)(-a - rot)] / 255];
      }
    }
  } else if (s.kind == 5 || s.kind == 7) {
    for (int y = 0; y < H; y++) {
      float v;
      if (s.kind == 5) {
        float edge = H - s.a / 255.0f * H, soft = 1 + s.pb * 0.5f;
        v = smooth(edge - soft, edge + soft, y);
      } else {
        float n = 1 + s.pb / 16.0f, w = 0.5f + 0.5f * cosf(2 * PI * (y / (float)H * n + s.c / 256.0f));
        v = w * w;
      }
      uint16_t c = color[byte(v)], *row = px + y * W;
      for (int x = 0; x < W; x++) row[x] = c;
    }
  } else if (s.kind == 6) {
    // the outline at inset m is where the arch's distance is -m; c lights the inside
    float m = s.a / 4.0f, half = (1 + s.pb / 8.0f) / 2;
    for (int i = 0; i <= ARCH_RANGE; i++) {
      float sd = (i - ARCH_OFFSET) / (float)ARCH_STEPS + m;
      lut[i] = byte(fmaxf(clamp01(half + 0.5f - fabsf(sd)), s.c / 255.0f * clamp01(0.5f - sd)));
    }
    for (int y = 0; y < H; y++) {
      uint16_t *row = px + y * W;
      for (int qx = 0; qx < QW; qx++) {
        int i = constrain(arch[y * QW + qx] + ARCH_OFFSET, 0, ARCH_RANGE);
        row[CX + qx] = row[CX - qx] = color[lut[i]];
      }
    }
  } else if (s.kind == 8) {
    fill(sprite, 0);
    drawMouth(px, s);
  } else if (s.kind == 9) {
    fill(sprite, 0);
    drawMouth(px, s);
    drawEyes(px, s);
  } else if (s.kind == 10) {
    fill(sprite, 0);
    drawDot(px, s);
  } else {
    fill(sprite, 0);
  }
}

}  // namespace scenes
