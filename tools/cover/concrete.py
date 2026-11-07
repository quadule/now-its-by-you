"""Concrete for the cover's paving stone and kerb, as maps: colour, height and roughness.

    uv run --with pillow python tools/cover/concrete.py

Cast concrete left out for years. The cement-and-sand skin is worn back to show the aggregate (gravel of a
few kinds of stone, from grit to a centimetre, some still under a film of cement), with bugholes where air
was trapped, a hairline crack, the stains of rain and leaves, grey lichen rosettes and black specks of
lichen, algae where it stays damp, and dirt settled into every hollow. The kerb is older: rain has streaked
its face, algae climbs from its foot, its top is worn smooth and its arris chipped.

Writes to renders/review/artwork/cover/: paving-color.png, paving-height.png (16-bit), paving-rough.png,
the same for kerb-, and concrete.json with each map's size in mm and its height range. The paving's image
top is the joint with the kerb; the kerb's image runs up its profile from its foot (bottom) over the arris
and across its top, and tiles left to right.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "renders/review/artwork/cover"
PX = 0.08                          # mm per pixel

# the kerb's profile, up from its foot (mm along the surface): its face, the rounded arris, its top
KERB_FACE, KERB_ARRIS, KERB_TOP = 62.0, 12.6, 44.0

STONE_KINDS = [  # (colour, how often): grey flint, brown and tan gravel, dark basalt, white quartz, rust
    ("#6f6b66", 5), ("#857260", 4), ("#a8927a", 4), ("#4a4642", 2), ("#d6d0c4", 1.5), ("#96684a", 1),
    ("#8c8a84", 3),
]
CEMENT = "#a6a095"


def lin(h: str) -> np.ndarray:
    c = np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def srgb8(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, 1)
    return (np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055) * 255 + 0.5).astype(np.uint8)


def noise(rng, shape, sigma: float, aniso=(1.0, 1.0)) -> np.ndarray:
    """Smooth, tileable noise of unit deviation over about sigma px (stretched by aniso = (y, x))."""
    f = max(1, int(sigma / 4))
    small = tuple(int(math.ceil(s / f)) for s in shape)
    n = ndi.gaussian_filter(rng.standard_normal(small).astype(np.float32),
                            (sigma * aniso[0] / f, sigma * aniso[1] / f), mode="wrap")
    if f > 1:
        n = ndi.zoom(n, f, order=1, mode="grid-wrap")
    n = n[:shape[0], :shape[1]]
    return n / (n.std() + 1e-9)


class Slab:
    """One surface's maps, being worked: colour (linear RGB), height (mm), roughness."""

    def __init__(self, w_mm: float, h_mm: float, seed: int, wave: float = 0.18):
        self.rng = np.random.default_rng(seed)
        self.H, self.W = int(round(h_mm / PX)), int(round(w_mm / PX))
        shape = (self.H, self.W)
        r = self.rng
        # the cement and sand: a warm grey, clouded, with sand grains light and dark through it
        self.col = lin(CEMENT)[None, None, :] * np.ones(shape + (3,), np.float32)
        self.col *= (1 + 0.06 * noise(r, shape, 400) + 0.035 * noise(r, shape, 60))[..., None]
        # the sand: the paste worn back to its grains, each one proud; pale quartz, dark specks among them
        sand = noise(r, shape, 0.8)
        grains = np.clip(noise(r, shape, 1.1), 0, None)
        self.col *= (1 + 0.1 * np.clip(sand, -2.5, 2.5))[..., None]
        light = ndi.gaussian_filter((noise(r, shape, 0.9) > 1.6).astype(np.float32), 0.5)
        dark = ndi.gaussian_filter((noise(r, shape, 0.7) > 1.9).astype(np.float32), 0.5)
        self.col = self.col * (1 - 0.4 * dark[..., None]) + lin("#dcd6ca")[None, None, :] * 0.35 * light[..., None]
        self.hgt = 0.06 * sand + 0.09 * grains + 0.08 * noise(r, shape, 40) + wave * noise(r, shape, 300)
        self.rough = np.full(shape, 0.96, np.float32)

    # -- pieces ---------------------------------------------------------------------------------------

    def _patch(self, cx, cy, R):
        ys = np.arange(int(cy) - R, int(cy) + R + 1)
        xs = np.arange(int(cx) - R, int(cx) + R + 1)
        yy, xx = np.meshgrid(ys, xs, indexing="ij")
        return yy, xx, yy % self.H, xx % self.W

    def stones(self, count: int, rmin: float, rmax: float, rise: tuple, film: tuple, where=None):
        """Gravel: irregular rounded stones, some proud of the worn surface, some still under cement; a ring of
        dirt where each meets the paste."""
        r = self.rng
        cement_ = lin(CEMENT)
        kinds = [lin(c) * 0.55 + cement_ * 0.45 for c, _ in STONE_KINDS]   # dusty with cement, never bright
        weights = np.array([w for _, w in STONE_KINDS], float)
        weights /= weights.sum()
        cement = lin(CEMENT)
        for _ in range(count):
            cx, cy = r.uniform(0, self.W), r.uniform(0, self.H)
            if where is not None and r.random() > where(cy / self.H):
                continue
            rad = (rmin * (rmax / rmin) ** (r.random() ** 1.7)) / PX
            ecc, ang = r.uniform(0.55, 1.0), r.uniform(0, math.pi)
            R = int(rad * 1.5) + 3
            yy, xx, yi, xi = self._patch(cx, cy, R)
            dx, dy = xx - cx, yy - cy
            u = dx * math.cos(ang) + dy * math.sin(ang)
            v = (-dx * math.sin(ang) + dy * math.cos(ang)) / ecc
            d = np.hypot(u, v)
            th = np.arctan2(v, u)
            ph = r.uniform(0, 2 * math.pi, 3)
            edge = rad * (1 + 0.13 * np.sin(3 * th + ph[0]) + 0.07 * np.sin(5 * th + ph[1]) + 0.04 * np.sin(8 * th + ph[2]))
            m = np.clip((edge - d) / 2.6, 0, 1)
            ring = np.clip((edge + 3.0 - d) / 3.0, 0, 1) - m
            base = kinds[r.choice(len(kinds), p=weights)] * r.uniform(0.8, 1.15)
            speck = 1 + 0.07 * ndi.gaussian_filter(r.standard_normal(d.shape), 1.2) * 2.5
            f = r.uniform(*film)
            c = (base[None, None, :] * speck[..., None]) * (1 - f) + cement[None, None, :] * f
            dome = np.sqrt(np.clip(1 - (d / np.maximum(edge, 1e-3)) ** 2, 0, 1)) ** 0.5 * r.uniform(*rise) * (1 - f)
            col = self.col[yi, xi]
            col = col * (1 - m[..., None]) + c * m[..., None]
            col *= (1 - 0.08 * ring)[..., None]
            self.col[yi, xi] = col
            self.hgt[yi, xi] = np.maximum(self.hgt[yi, xi] - 0.06 * ring, self.hgt[yi, xi] * (1 - m) + dome * m)
            self.rough[yi, xi] = self.rough[yi, xi] * (1 - m) + r.uniform(0.82, 0.92) * m

    def pores(self, count: int, rmin: float, rmax: float, where=None):
        """Bugholes: small voids where air was trapped against the mould, dark with what has blown in."""
        r = self.rng
        for _ in range(count):
            cx, cy = r.uniform(0, self.W), r.uniform(0, self.H)
            if where is not None and r.random() > where(cy / self.H):
                continue
            rad = (rmin * (rmax / rmin) ** (r.random() ** 2.2)) / PX
            R = int(rad * 1.4) + 2
            yy, xx, yi, xi = self._patch(cx, cy, R)
            th = np.arctan2(yy - cy, xx - cx)
            ph = r.uniform(0, 6.3, 2)
            d = np.hypot(xx - cx, (yy - cy) * r.uniform(0.6, 1.4)) / (1 + 0.2 * np.sin(2 * th + ph[0])
                                                                        + 0.12 * np.sin(5 * th + ph[1]))
            m = np.clip((rad - d) / 1.2, 0, 1)
            depth = rad * PX * r.uniform(0.4, 1.0)
            bowl = np.sqrt(np.clip(1 - (d / rad) ** 2, 0, 1))
            lip = np.clip((rad + 2 - d) / 2, 0, 1) - m
            self.hgt[yi, xi] = self.hgt[yi, xi] - depth * bowl * m
            deep = (bowl * m)[..., None] ** 1.5
            self.col[yi, xi] = (self.col[yi, xi] * (1 - 0.55 * deep) + lin("#3b352e") * 0.55 * deep) \
                * (1 + 0.1 * lip[..., None])
            self.rough[yi, xi] = np.maximum(self.rough[yi, xi], m)

    def crack(self, x0, y0, heading, length_mm, width_px=1.8):
        """A hairline crack wandering across, with a branch or two; its edges a little spalled."""
        r = self.rng
        img = Image.new("L", (self.W, self.H), 0)
        dr = ImageDraw.Draw(img)

        def walk(x, y, a, L, w):
            pts = [(x, y)]
            step = 1.2 / PX
            for _ in range(int(L / 1.2)):
                a += r.normal(0, 0.28)
                x, y = x + math.cos(a) * step, y + math.sin(a) * step
                pts.append((x, y))
                if r.random() < 0.012 and L > 20:
                    walk(x, y, a + r.choice([-1, 1]) * r.uniform(0.5, 1.1), L * r.uniform(0.15, 0.35), w * 0.6)
            dr.line(pts, fill=255, width=max(1, int(round(w))))

        walk(x0 / PX, y0 / PX, heading, length_mm, width_px)
        m = ndi.gaussian_filter(np.asarray(img, np.float32) / 255, 0.7)
        chips = ndi.gaussian_filter(m, 4) * np.clip(noise(r, m.shape, 3) - 0.8, 0, 1)
        self.hgt -= 0.5 * m + 0.25 * chips
        self.col *= (1 - 0.65 * np.clip(m * 1.5, 0, 1) - 0.12 * np.clip(chips * 3, 0, 1))[..., None]

    def lichen(self, count: int, rmin: float, rmax: float, where=None):
        """Crustose lichen: lobed grey-green rosettes, older and darker at the heart."""
        r = self.rng
        tones = [lin("#aaad9c"), lin("#b3b092"), lin("#a2a69c"), lin("#bdbaaf")]
        for _ in range(count):
            cx, cy = r.uniform(0, self.W), r.uniform(0, self.H)
            if where is not None and r.random() > where(cy / self.H):
                continue
            rad = r.uniform(rmin, rmax) / PX
            R = int(rad * 1.3) + 3
            yy, xx, yi, xi = self._patch(cx, cy, R)
            d = np.hypot(xx - cx, yy - cy)
            th = np.arctan2(yy - cy, xx - cx)
            lobes = int(r.integers(9, 16))
            edge = rad * (0.85 + 0.12 * np.abs(np.sin(lobes * th / 2 + r.uniform(0, 6))) + 0.06 * np.sin(3 * th))
            holes = ndi.gaussian_filter(r.standard_normal(d.shape), 2.5)
            m = np.clip((edge - d) / 2.0, 0, 1) * np.clip(holes * 3 + 0.4, 0, 1)
            m = ndi.gaussian_filter(m, 0.8)
            tone = tones[int(r.integers(len(tones)))] * r.uniform(0.85, 1.05)
            heart = np.clip(1 - d / (rad * 0.55), 0, 1)
            c = tone[None, None, :] * (1 - 0.35 * heart[..., None])
            a = 0.45 * m[..., None]
            self.col[yi, xi] = self.col[yi, xi] * (1 - a) + c * a
            self.hgt[yi, xi] += 0.08 * m
            self.rough[yi, xi] = self.rough[yi, xi] * (1 - m) + 0.95 * m

    def specks(self, clusters: int, where=None):
        """Black lichen: pinhead specks gathered in loose colonies."""
        r = self.rng
        for _ in range(clusters):
            cx, cy = r.uniform(0, self.W), r.uniform(0, self.H)
            if where is not None and r.random() > where(cy / self.H):
                continue
            spread = r.uniform(4, 14) / PX
            for _ in range(int(r.integers(20, 70))):
                x, y = cx + r.normal(0, spread), cy + r.normal(0, spread)
                rad = r.uniform(0.08, 0.35) / PX
                R = int(rad) + 2
                yy, xx, yi, xi = self._patch(x, y, R)
                m = np.clip((rad - np.hypot(xx - x, yy - y)) / 0.8, 0, 1)[..., None]
                self.col[yi, xi] = self.col[yi, xi] * (1 - 0.9 * m) + lin("#1e1b17") * 0.9 * m

    def stain(self, amount: float, sigma: float, tint="#4a463c", aniso=(1.0, 1.0), bias=0.0, mask=None):
        """Weathering: broad blotches where water and dirt have lain (streaks, with aniso)."""
        n = np.clip(noise(self.rng, (self.H, self.W), sigma, aniso) * 0.5 + bias, 0, 1)
        if mask is not None:
            n *= mask
        a = (amount * n)[..., None]
        self.col = self.col * (1 - a) + lin(tint)[None, None, :] * self.col.mean() * 2.2 * a

    def finish(self):
        """Dirt settles in every hollow: darker where the surface is below its neighbours."""
        cavity = np.clip(ndi.gaussian_filter(self.hgt, 6) - self.hgt, 0, None)
        self.col *= (1 - np.clip(cavity * 1.6, 0, 0.45))[..., None]
        self.col *= (1 - 0.1 * np.clip(ndi.gaussian_filter(self.hgt, 30) - self.hgt, 0, None))[..., None]

    def save(self, name: str) -> dict:
        Image.fromarray(srgb8(self.col)).save(OUT / f"{name}-color.png")
        lo, hi = float(self.hgt.min()), float(self.hgt.max())
        Image.fromarray(((self.hgt - lo) / (hi - lo) * 65535 + 0.5).astype(np.uint16)).save(OUT / f"{name}-height.png")
        Image.fromarray((np.clip(self.rough, 0, 1) * 255 + 0.5).astype(np.uint8)).save(OUT / f"{name}-rough.png")
        return {"width_mm": self.W * PX, "height_mm": self.H * PX, "height_range_mm": [lo, hi]}


def paving() -> dict:
    """The stone underfoot, 500 x 300 mm; the joint with the kerb along its top edge."""
    s = Slab(500, 300, 21)
    near_joint = lambda v: 0.4 + 0.6 * (1 - v) ** 3   # noqa: E731 (v = 0 at the image top, the joint)
    s.stones(1100, 1.4, 6.0, (0.15, 0.55), (0.35, 0.95))
    s.stones(7000, 0.45, 1.4, (0.05, 0.25), (0.3, 0.95))
    s.pores(1400, 0.1, 0.6)
    s.crack(40, 250, -0.35, 330)
    s.stain(0.22, 700, "#5a5448", bias=0.05)
    s.stain(0.15, 120, "#5c5545")
    s.stain(0.22, 900, "#b3aea2", bias=-0.05)                         # sun-bleached, dry
    yy = np.arange(s.H)[:, None] / s.H
    s.stain(0.35, 90, "#3d4230", bias=0.3, mask=np.clip(1 - yy / 0.05, 0, 1) ** 1.5)   # a little algae by the joint
    s.lichen(9, 2.5, 7.0)
    s.specks(18)
    for _ in range(3):  # leaves that lay there once, printed in tannin
        cx, cy, a = s.rng.uniform(0, s.W), s.rng.uniform(0, s.H), s.rng.uniform(0, math.pi)
        R = int(30 / PX)
        yy2, xx2, yi, xi = s._patch(cx, cy, R)
        u = ((xx2 - cx) * math.cos(a) + (yy2 - cy) * math.sin(a)) * PX
        v = (-(xx2 - cx) * math.sin(a) + (yy2 - cy) * math.cos(a)) * PX
        half = 11 * np.sqrt(np.clip(1 - (u / 26) ** 2, 0, 1)) + 1e-3
        m = ndi.gaussian_filter(np.clip(1 - (v / half) ** 2, 0, 1) * (np.abs(u) < 26), 6)
        s.col[yi, xi] = s.col[yi, xi] * (1 - 0.2 * m[..., None]) + lin("#5e4a36") * 0.2 * m[..., None]
    s.finish()
    return s.save("paving")


def kerb() -> dict:
    """The kerb's surface, 500 mm along and up its profile from the foot: face, arris, top."""
    total = KERB_FACE + KERB_ARRIS + KERB_TOP
    s = Slab(500, total, 22, wave=0.06)     # cast against a mould: flatter than the trowelled paving
    s.col *= 0.9
    v_face = KERB_FACE / total                    # image rows run top (end of the top face) to bottom (foot)
    v_arris = (KERB_FACE + KERB_ARRIS) / total
    up = lambda r_: 1 - r_                        # noqa: E731 (fraction up the profile from the foot)
    s.stones(900, 1.4, 6.0, (0.1, 0.45), (0.45, 0.95))
    s.stones(5000, 0.45, 1.4, (0.05, 0.2), (0.4, 0.95))
    s.pores(1500, 0.1, 0.8, where=lambda r_: 1.0 if up(r_) < v_face else 0.3)   # the face was against the mould
    yy = np.arange(s.H)[:, None] / s.H
    upv = 1 - yy
    # rain has run down the face in streaks; algae climbs from the foot
    s.stain(0.45, 60, "#3c3a31", aniso=(8.0, 0.6), bias=0.1, mask=np.clip((v_face - upv) / 0.05, 0, 1))
    s.stain(0.75, 70, "#2c3222", bias=0.5, mask=np.clip(1 - upv / 0.22, 0, 1) ** 1.3)
    s.stain(0.3, 600, "#4b473d", bias=0.15)
    # the top worn smooth and pale by feet and mower wheels
    top = np.clip((upv - v_arris) / 0.04, 0, 1) * np.clip((1 - upv) / 0.05, 0, 1)
    s.col = s.col * (1 + 0.14 * top[..., None])
    s.rough = s.rough * (1 - 0.08 * top)
    # the arris knocked about: spalls, where fresher concrete and aggregate show
    arris = np.exp(-((upv - (v_face + v_arris) / 2) / 0.045) ** 2)
    spall = (np.clip(noise(s.rng, (s.H, s.W), 9) - 1.7, 0, 1) * arris).astype(np.float32)
    spall = ndi.gaussian_filter(np.clip(spall * 4, 0, 1), 1.0)
    s.hgt -= 1.0 * spall
    s.col = s.col * (1 - 0.3 * spall[..., None]) + lin("#b1aa9c")[None, None, :] * 0.3 * spall[..., None]
    s.lichen(8, 2.5, 8.0, where=lambda r_: 0.4 + 0.6 * (up(r_) > v_face))
    s.specks(22)
    s.finish()
    return s.save("kerb")


def main():
    info = {"mm_per_px": PX, "paving": paving(), "kerb": kerb(),
            "kerb_profile_mm": [KERB_FACE, KERB_ARRIS, KERB_TOP]}
    (OUT / "concrete.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info))


if __name__ == "__main__":
    main()
