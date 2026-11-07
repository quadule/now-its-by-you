"""The packet's woodcut: one daisy come up through a crack in a concrete slab.

Cut the way a woodcut is cut: black line that swells and tapers, hatching for shade, white lines gouged
out of the black, and flat tints printed under the key block (a yellow for the disc, a sap green for stem
and leaves, a concrete grey, a white for the petals). Everything is drawn in the face's own units
(990 x 1440, 300 px/in, y running down) and comes back as marks in painting order, which face.py turns
into one mask per ink. The light is a window at the upper left, so shade falls to the lower right.
"""

from __future__ import annotations

import math

import numpy as np

LIGHT = np.array([-0.62, -0.78])
LIGHT /= np.linalg.norm(LIGHT)
SHADE = -LIGHT


# ---- geometry ------------------------------------------------------------------------------------------

def path_d(rings) -> str:
    return " ".join("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in np.asarray(r)) + " Z" for r in rings)


def spline(pts, n: int = 14, closed: bool = False) -> np.ndarray:
    """Catmull-Rom through pts, n samples per span."""
    p = np.asarray(pts, float)
    p = np.vstack([p[-1], p, p[0], p[1]]) if closed else np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])
    t = np.linspace(0, 1, n, endpoint=False)[:, None]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t**2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t**3))
    if not closed:
        out.append(p[-2][None])
    return np.vstack(out)


def resample(poly, step: float, closed: bool = False) -> np.ndarray:
    poly = np.asarray(poly, float)
    if closed:
        poly = np.vstack([poly, poly[:1]])
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(poly, axis=0), axis=1))])
    n = max(3, int(math.ceil(s[-1] / step)) + 1)
    t = np.linspace(0, s[-1], n)
    out = np.column_stack([np.interp(t, s, poly[:, 0]), np.interp(t, s, poly[:, 1])])
    return out[:-1] if closed else out


def normals(poly, closed: bool = False) -> np.ndarray:
    d = (np.roll(poly, -1, 0) - np.roll(poly, 1, 0)) if closed else np.gradient(poly, axis=0)
    d = d / (np.linalg.norm(d, axis=1, keepdims=True) + 1e-9)
    return np.column_stack([-d[:, 1], d[:, 0]])


def smooth_noise(rng, n: int, corr: float) -> np.ndarray:
    """n samples of smooth noise of about unit amplitude, correlated over about corr samples."""
    k = int(n / max(1.0, corr)) + 4
    v = rng.normal(0, 1, k)
    x = np.linspace(1, k - 3, n)
    i = np.floor(x).astype(int)
    f = x - i
    p0, p1, p2, p3 = v[i - 1], v[i], v[np.minimum(i + 1, k - 1)], v[np.minimum(i + 2, k - 1)]
    return 0.5 * (2 * p1 + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f**2
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * f**3)


def profile(n: int, taper=(0.3, 0.3), floor: float = 0.1, power: float = 0.6) -> np.ndarray:
    s = np.linspace(0, 1, n)
    p = np.ones(n)
    a, b = taper
    if a > 0:
        p = np.minimum(p, np.clip(s / a, 0, 1) ** power)
    if b > 0:
        p = np.minimum(p, np.clip((1 - s) / b, 0, 1) ** power)
    return np.maximum(p, floor)


def inside(pts, ring) -> np.ndarray:
    pts, ring = np.asarray(pts, float), np.asarray(ring, float)
    x, y = pts[:, :1], pts[:, 1:]
    xa, ya = ring[None, :, 0], ring[None, :, 1]
    xb, yb = np.roll(ring[:, 0], -1)[None], np.roll(ring[:, 1], -1)[None]
    cross = ((ya > y) != (yb > y)) & (x < (xb - xa) * (y - ya) / (yb - ya + 1e-12) + xa)
    return cross.sum(1) % 2 == 1


def clip_line(p0, d, ring):
    """The stretches (t0, t1) of the line p0 + t d that lie inside ring."""
    a = np.asarray(ring, float)
    e = np.roll(a, -1, 0) - a
    den = d[0] * e[:, 1] - d[1] * e[:, 0]
    ok = np.abs(den) > 1e-9
    den = np.where(ok, den, 1)
    q = a - p0
    t = (q[:, 0] * e[:, 1] - q[:, 1] * e[:, 0]) / den
    u = (q[:, 0] * d[1] - q[:, 1] * d[0]) / den
    ts = np.sort(t[ok & (u >= 0) & (u < 1)])
    return list(zip(ts[0::2], ts[1::2]))


def jagged(rng, pts, rough: float, depth: int = 4) -> np.ndarray:
    """Midpoint displacement: a crack's line between the given points."""
    pts = np.asarray(pts, float)
    for _ in range(depth):
        new = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            d = b - a
            L = np.linalg.norm(d) + 1e-9
            new += [(a + b) / 2 + np.array([-d[1], d[0]]) / L * rng.normal(0, rough * L), b]
        pts = np.array(new)
    return pts


def unit(v):
    v = np.asarray(v, float)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


def rot(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, s], [-s, c]])  # row vectors: p @ rot(a) turns p by a (y down: clockwise)


# ---- the block -----------------------------------------------------------------------------------------

class Block:
    """The woodcut's marks in painting order: (op, ink, path d, fill rule)."""

    def __init__(self, seed: int = 11):
        self.rng = np.random.default_rng(seed)
        self.marks: list[tuple[str, str, str, str]] = []

    def fill(self, rings, ink: str, rule: str = "nonzero"):
        if isinstance(rings, np.ndarray):
            rings = [rings]
        self.marks.append(("fill", ink, path_d(rings), rule))

    def cut(self, rings, rule: str = "nonzero"):
        if isinstance(rings, np.ndarray):
            rings = [rings]
        self.marks.append(("cut", "black", path_d(rings), rule))

    def _ribbon(self, poly, w, wob: float, cut: bool = False, corr: float = 10):
        n = len(poly)
        w = np.broadcast_to(np.asarray(w, float), (n,)) * (1 + wob * smooth_noise(self.rng, n, corr))
        nr = normals(poly)
        ring = np.vstack([poly + nr * (w / 2)[:, None], (poly - nr * (w / 2)[:, None])[::-1]])
        (self.cut if cut else lambda r: self.fill(r, "black"))(ring)

    def stroke(self, pts, width, taper=(0.3, 0.3), wob: float = 0.12, smooth: bool = True,
               step: float = 0.8, cut: bool = False, floor: float = 0.1, power: float = 0.6):
        poly = spline(pts) if smooth and len(pts) > 2 else np.asarray(pts, float)
        poly = resample(poly, step)
        w = np.asarray(width, float)
        if w.ndim:  # widths given along the points: stretch them over the resampled line
            w = np.interp(np.linspace(0, 1, len(poly)), np.linspace(0, 1, len(w)), w)
        self._ribbon(poly, w * profile(len(poly), taper, floor, power), wob, cut)

    def outline(self, ring, width: float, shade: float = 0.8, wob: float = 0.12, closed_step: float = 0.8):
        """A closed black line round a shape, heavier on the side away from the light."""
        ring = resample(np.asarray(ring, float), closed_step, closed=True)
        nr = normals(ring, closed=True)
        if np.mean(np.sum((ring - ring.mean(0)) * nr, 1)) < 0:
            nr = -nr
        k = 1 + shade * np.clip(nr @ SHADE, 0, None) - 0.45 * shade * np.clip(nr @ LIGHT, 0, None)
        w = width * np.maximum(k, 0.35) * (1 + wob * smooth_noise(self.rng, len(ring), 14))
        self.fill([ring + nr * (w / 2)[:, None], ring - nr * (w / 2)[:, None]], "black", "evenodd")

    def hatch(self, ring, angle: float, spacing: float, width: float, mapf=None, tone=None,
              jitter: float = 0.12, taper=(0.12, 0.12), inset: float = 0.0, breaks: float = 0.0,
              wave: float = 0.35, cut: bool = False, min_len: float = 3.0, skip: float = 0.0):
        """Parallel gouge lines across a region; ring and lines live in the region's own plane, drawn
        through mapf (a face of the slab, say) onto the page."""
        ring = np.asarray(ring, float)
        d = np.array([math.cos(angle), math.sin(angle)])
        nv = np.array([-d[1], d[0]])
        proj = ring @ nv
        o = proj.min() + spacing * 0.5
        while o < proj.max():
            oo = o + self.rng.normal(0, jitter * spacing)
            o += spacing
            if skip and self.rng.random() < skip:
                continue
            for t0, t1 in clip_line(nv * oo, d, ring):
                t0, t1 = t0 + inset + self.rng.uniform(0, 1.5), t1 - inset - self.rng.uniform(0, 1.5)
                spans = [(t0, t1)]
                if breaks > 0:
                    cuts = np.sort(self.rng.uniform(t0, t1, self.rng.poisson(breaks * (t1 - t0) / 100)))
                    spans, a = [], t0
                    for c in cuts:
                        g = self.rng.uniform(2.0, 6.0)
                        spans.append((a, c - g / 2))
                        a = c + g / 2
                    spans.append((a, t1))
                for a, b in spans:
                    if b - a < min_len:
                        continue
                    ts = np.linspace(a, b, max(4, int((b - a) / 1.0)))
                    pts = nv * oo + ts[:, None] * d
                    pts = pts + nv * (wave * smooth_noise(self.rng, len(ts), 18))[:, None]
                    w = width * (tone(pts) if tone else 1.0) * profile(len(ts), taper, 0.15, 0.5)
                    scr = mapf(pts) if mapf else pts
                    self._ribbon(scr, w, 0.18, cut)

    def dots(self, pts, radii, cut: bool = False, ink: str = "black"):
        for p, r in zip(np.asarray(pts, float), np.broadcast_to(np.asarray(radii, float), (len(pts),))):
            k = int(self.rng.integers(5, 8))
            a = np.sort(self.rng.uniform(0, 2 * math.pi, k))
            rad = r * (0.7 + 0.5 * self.rng.random(k))
            poly = p + np.column_stack([np.cos(a) * rad, np.sin(a) * rad])
            if cut:
                self.cut(poly)
            else:
                self.fill(poly, ink)

    def scatter(self, ring, n: int, weight=None) -> np.ndarray:
        ring = np.asarray(ring, float)
        lo, hi = ring.min(0), ring.max(0)
        pts = lo + self.rng.random((n * 6, 2)) * (hi - lo)
        pts = pts[inside(pts, ring)]
        if weight is not None:
            pts = pts[self.rng.random(len(pts)) < weight(pts)]
        return pts[:n]


# ---- the slab ------------------------------------------------------------------------------------------

PANEL = (66.0, 296.0, 1209.0, 1580.0)   # the picture's frame on the face: left, top, right, bottom
CX = (PANEL[0] + PANEL[2]) / 2
HP = PANEL[3] - PANEL[1]
W, D, T = 840.0, 290.0, 132.0           # the slab: across, deep, thick (face units)
YAW, ELEV, F = math.radians(-9), math.radians(21), 2900.0
ORIGIN = np.array([CX - 3, PANEL[1] + 0.775 * HP])   # where the top face's centre lands on the page


def project(p) -> np.ndarray:
    p = np.asarray(p, float)
    x, y, z = p[..., 0], p[..., 1], p[..., 2]
    c, s = math.cos(YAW), math.sin(YAW)
    xr, yr = x * c - y * s, x * s + y * c
    ce, se = math.cos(ELEV), math.sin(ELEV)
    k = F / (F + yr * ce - z * se)
    return np.stack([ORIGIN[0] + xr * k, ORIGIN[1] - (yr * se + z * ce) * k], -1)


def top(uv):
    uv = np.asarray(uv, float)
    return project(np.stack([uv[..., 0], uv[..., 1], np.zeros(uv.shape[:-1])], -1))


def front(uv):
    uv = np.asarray(uv, float)
    return project(np.stack([uv[..., 0], np.full(uv.shape[:-1], -D / 2), uv[..., 1]], -1))


def side(uv):
    uv = np.asarray(uv, float)
    return project(np.stack([np.full(uv.shape[:-1], W / 2), uv[..., 0], uv[..., 1]], -1))


def ground(uv):
    uv = np.asarray(uv, float)
    return project(np.stack([uv[..., 0], uv[..., 1], np.full(uv.shape[:-1], -T)], -1))


def worn(rng, ring, amp: float, step: float = 3.0) -> np.ndarray:
    """A rectangle's edges, a little knocked about."""
    r = resample(ring, step, closed=True)
    nr = normals(r, closed=True)
    return r + nr * (amp * smooth_noise(rng, len(r), 5))[:, None]


def slab(b: Block):
    rng = b.rng
    top_r = np.array([(-W / 2, -D / 2), (W / 2, -D / 2), (W / 2, D / 2), (-W / 2, D / 2)])
    front_r = np.array([(-W / 2, -T), (W / 2, -T), (W / 2, 0), (-W / 2, 0)])
    side_r = np.array([(-D / 2, -T), (D / 2, -T), (D / 2, 0), (-D / 2, 0)])

    # the ground round about, fading into the distance
    far = np.array([(-1400.0, -D / 2 - 120), (1400.0, -D / 2 - 120), (1400.0, D / 2 + 700), (-1400.0, D / 2 + 700)])
    b.hatch(far, 0.0, 9.0, 1.5, mapf=ground, breaks=5.0, skip=0.25, taper=(0.3, 0.3), min_len=6, jitter=0.3,
            tone=lambda p: np.clip(1.1 - (p[:, 1] + D / 2) / 700, 0.2, 1))
    # the slab's shadow thrown to the right, and a few strokes of earth at its foot
    sh = np.array([(W / 2 - 4, -D / 2 + 2), (W / 2 + 70, -D / 2 + 30), (W / 2 + 55, D / 2 + 30), (W / 2 - 4, D / 2)])
    b.hatch(sh, 0.0, 6.5, 1.5, mapf=ground, taper=(0.02, 0.7), jitter=0.25, wave=0.5, breaks=1.0)
    for i, (x0, x1) in enumerate([(-W / 2 - 80, -W / 2 + 30), (-W / 2 - 45, -W / 2 + 60), (W / 2 - 60, W / 2 + 70)]):
        yy = -D / 2 - 10 - 9 * i
        b.stroke(ground(np.array([(x0, yy), ((x0 + x1) / 2, yy - 1.5), (x1, yy)])), 1.8, (0.45, 0.45), 0.25)
    pebbles = np.array([(-W / 2 - 20, -D / 2 - 24), (-W / 2 - 58, -D / 2 - 30), (W / 2 + 40, -D / 2 - 18),
                        (-30, -D / 2 - 26), (60, -D / 2 - 34), (190, -D / 2 - 22)])
    b.dots(ground(pebbles), rng.uniform(1.4, 2.6, len(pebbles)))

    # the three faces, tinted concrete, and cut
    inset = np.array([0.985, 0.97])
    b.fill(top(worn(rng, top_r * inset, 0.8)), "concrete")
    b.fill(front(worn(rng, front_r * [0.985, 1.0] + [0, -1.0], 0.8)), "concrete")
    b.fill(side(worn(rng, side_r * [0.97, 1.0] + [0, -1.0], 0.8)), "concrete")

    # the side in shadow: near black, with white lines gouged along it
    b.fill(side(worn(rng, side_r, 1.0)), "black")
    b.hatch(side_r, 0.0, 6.5, 1.5, mapf=side, cut=True, breaks=4.0, taper=(0.3, 0.3), inset=3, min_len=5,
            tone=lambda p: 0.45 + 0.7 * np.clip((p[:, 1] + T) / T, 0, 1))
    pts = b.scatter(side_r * [0.9, 0.9] + [0, -3], 40)
    b.dots(side(pts), rng.uniform(0.8, 1.5, len(pts)), cut=True)

    # the front: horizontal gouges, heavier toward the foot, broken by aggregate
    b.hatch(front_r, 0.0, 5.6, 2.4, mapf=front, breaks=7.0, taper=(0.3, 0.3), inset=2, min_len=4, jitter=0.2,
            wave=0.6, tone=lambda p: 0.3 + 0.8 * np.clip(-p[:, 1] / T, 0, 1) ** 0.9)
    pts = b.scatter(front_r * [0.97, 0.92] + [0, -2], 160, weight=lambda p: 0.3 + 0.7 * np.clip(-p[:, 1] / T, 0, 1))
    b.dots(front(pts), rng.uniform(0.7, 1.5, len(pts)))
    pts = b.scatter(front_r * [0.97, 0.9], 60)
    b.dots(front(pts), rng.uniform(1.0, 2.0, len(pts)), cut=True)

    # the top: in the light; aggregate stippled, a few pits, a light scumble of lines toward the back
    b.hatch(top_r * [0.96, 0.9], 0.0, 9.0, 1.0, mapf=top, breaks=2.5, skip=0.35, taper=(0.3, 0.3),
            tone=lambda p: np.clip((p[:, 1] + 20) / (D / 2 + 20), 0, 1) ** 1.2)
    pts = b.scatter(top_r * [0.97, 0.94], 330, weight=lambda p: 0.35 + 0.65 * (p[:, 1] + D / 2) / D)
    b.dots(top(pts), rng.uniform(0.7, 1.7, len(pts)))
    for c in b.scatter(top_r * [0.85, 0.8], 13):
        r = rng.uniform(2.5, 5.0)
        a = np.linspace(math.radians(150), math.radians(330), 10)
        arc = c + np.column_stack([np.cos(a) * r, np.sin(a) * r])
        b.stroke(top(arc), 1.6, (0.4, 0.4), 0.1, smooth=False)

    # the crack: across the top from the back edge, through the flower's root, over the front edge and down
    S = np.array([8.0, 6.0])
    ctl = np.array([(40.0, D / 2), (26.0, 64.0), S, (-10.0, -58.0), (-22.0, -D / 2)])
    crack = resample(jagged(rng, ctl, 0.16, 4), 1.5)
    s = np.linspace(0, 1, len(crack))
    s0 = s[np.argmin(np.linalg.norm(crack - S, axis=1))]
    g = 2.5 + 24.0 * np.exp(-((s - s0) / 0.16) ** 2) + 6.0 * np.exp(-((s - s0) / 0.45) ** 2) \
        + 4.0 * np.exp(-((s - 1.0) / 0.08) ** 2)
    nr = normals(crack)
    left = crack + nr * (g / 2 * (1 + 0.35 * smooth_noise(rng, len(s), 4)))[:, None]
    right = crack - nr * (g / 2 * (1 + 0.35 * smooth_noise(rng, len(s), 4)))[:, None]
    gap = np.vstack([left, right[::-1]])
    b.fill(top(gap), "black")
    # hairlines running off it
    for i0, end in [(0.22, (-150.0, 80.0)), (0.33, (170.0, 95.0)), (0.62, (-140.0, -30.0)), (0.72, (150.0, -70.0)),
                    (0.5, (80.0, 20.0))]:
        a = crack[int(i0 * (len(crack) - 1))]
        line = jagged(rng, np.array([a, (a + end) / 2 + rng.normal(0, 8, 2), end]), 0.14, 3)
        b.stroke(top(line), 2.0, (0.02, 0.8), 0.25, smooth=False)
    # down the front face, with a branch
    mouth = crack[-1]
    fc = jagged(rng, np.array([(mouth[0], 0.0), (mouth[0] + 8, -30.0), (mouth[0] - 4, -58.0), (mouth[0] + 12, -T)]),
                0.14, 4)
    b.stroke(front(fc), np.array([9.0, 5.0, 3.4, 2.4]), (0.0, 0.05), 0.3, smooth=False, floor=0.5)
    br = jagged(rng, np.array([fc[len(fc) // 3], (mouth[0] - 45, -52.0), (mouth[0] - 85, -70.0)]), 0.15, 3)
    b.stroke(front(br), 2.0, (0.02, 0.7), 0.25, smooth=False)
    b.fill(front(np.array([(mouth[0] - 9, 0.5), (mouth[0] + 9, 0.5), (mouth[0] + 3, -12.0)])), "black")

    # the edges: a woodcut's line, heavier underneath and on the shaded side; a few chips knocked out
    def edge(pts3, w):
        a, z = np.asarray(pts3, float)
        n = int(np.linalg.norm(z - a) / 4) + 2
        line = a + np.linspace(0, 1, n)[:, None] * (z - a)
        line[1:-1] += rng.normal(0, 0.5, (n - 2, 3)) * [1, 1, 1]
        b.stroke(project(line), w, (0.04, 0.04), 0.2, smooth=True)

    hw, hd = W / 2, D / 2
    edge([(-hw, hd, 0), (hw, hd, 0)], 2.0)
    edge([(-hw, -hd, 0), (-hw, hd, 0)], 2.4)
    edge([(-hw, -hd, 0), (hw, -hd, 0)], 2.8)
    edge([(hw, -hd, 0), (hw, hd, 0)], 2.6)
    edge([(-hw, -hd, -T), (hw, -hd, -T)], 4.6)
    edge([(hw, -hd, -T), (hw, hd, -T)], 4.4)
    edge([(-hw, -hd, 0), (-hw, -hd, -T)], 3.0)
    edge([(hw, -hd, 0), (hw, -hd, -T)], 2.6)
    edge([(hw, hd, 0), (hw, hd, -T)], 3.2)
    for x0 in (-190.0, -110.0, 85.0, 205.0):
        w0 = rng.uniform(6, 11)
        b.fill(front(np.array([(x0 - w0, 0.6), (x0 + w0, 0.6), (x0 + w0 * 0.3, -rng.uniform(5, 9)),
                               (x0 - w0 * 0.4, -rng.uniform(3, 7))])), "black")
    for y0 in (-40.0, 70.0):
        b.fill(top(np.array([(hw + 0.5, y0 - 8), (hw + 0.5, y0 + 8), (hw - 7, y0 + 2)])), "black")

    # crumbs at the crack's mouth
    root = top(S)
    crumbs = root + rng.normal(0, 1, (7, 2)) * [26, 7] + [0, 6]
    b.dots(crumbs, rng.uniform(1.3, 2.8, len(crumbs)))
    return top(S), top(gap)


# ---- the daisy -----------------------------------------------------------------------------------------

C = np.array([CX, PANEL[1] + 0.33 * HP])   # the disc's centre on the page
HEAD_ROT, HEAD_SQ = math.radians(-9), 0.9
DISC = 65.0
R0 = DISC * 0.52                  # where a petal starts, under the disc


def head(p) -> np.ndarray:
    """The flower's own plane (a circle facing us) onto the page: tipped back a little, and turned."""
    return C + (np.asarray(p, float) * [1.0, HEAD_SQ]) @ rot(HEAD_ROT)


def petal_ring(rng, L: float, w: float, bend: float, r0: float = R0) -> np.ndarray:
    t = np.linspace(0, 1, 48)
    x = r0 + (L - r0) * t
    hw = w / 2 * (0.26 + 0.74 * np.clip(t / 0.42, 0, 1) ** 0.6) * (1 - 0.2 * np.clip((t - 0.72) / 0.28, 0, 1) ** 2)
    asym = 1 + 0.07 * rng.normal()
    h1 = hw[-1]
    u = np.linspace(0, 1, 32)[1:-1]
    lobes = int(rng.integers(2, 4))
    tip_x = x[-1] + 0.5 * h1 * np.sqrt(1 - (2 * u - 1) ** 2) + 2.4 * (np.abs(np.sin(math.pi * lobes * u)) ** 0.5 - 1)
    tip_y = h1 * asym * (1 - u) - h1 / asym * u
    ring = np.vstack([np.column_stack([x, hw * asym]), np.column_stack([tip_x, tip_y]),
                      np.column_stack([x, -hw / asym])[::-1]])
    ring[:, 1] += bend * (ring[:, 0] - r0) ** 2 / L
    return ring


def petals(b: Block, n: int, phase: float, L: float, w: float, back: bool):
    rng = b.rng
    for i in range(n):
        th = 2 * math.pi * i / n + phase + rng.normal(0, 0.035)
        Li, wi, bend = L * rng.uniform(0.89, 1.07), w * rng.uniform(0.88, 1.12), rng.normal(0, 0.06)
        R = rot(th)
        ring = petal_ring(rng, Li, wi, bend)
        b.fill(head(ring @ R), "white")
        axis_dir = unit(head(np.array([100.0, 0.0]) @ R) - C)
        shade = float(axis_dir @ SHADE)
        # grooves down the petal
        r0 = R0
        for off in ((-0.13, 0.14) if not back else (0.0,)):
            if not back and rng.random() < 0.25:
                continue
            t = np.linspace(0.14 + rng.uniform(0, 0.08), 0.62 + rng.uniform(0, 0.12), 12)
            x = r0 + (Li - r0) * t
            y = off * wi + bend * (x - r0) ** 2 / Li
            b.stroke(head(np.column_stack([x, y]) @ R), 1.5, (0.35, 0.5), 0.15)
        # shade at the root, longer on the side away from the light and on the petals behind
        reach = 0.1 + 0.32 * max(shade, 0) + (0.2 if back else 0)
        if reach > 0.14:
            for off in (-0.26, -0.09, 0.09, 0.26):
                t = np.linspace(0.0, reach * rng.uniform(0.7, 1.1), 8)
                x = r0 + (Li - r0) * t
                y = off * wi + bend * (x - r0) ** 2 / Li
                b.stroke(head(np.column_stack([x, y]) @ R), 1.35, (0.0, 0.6), 0.15)
        b.outline(head(ring @ R), 2.9 if not back else 2.6, shade=0.9)


def disc(b: Block):
    rng = b.rng
    a = np.linspace(0, 2 * math.pi, 120, endpoint=False)
    r = DISC * (1 + 0.012 * smooth_noise(rng, 120, 8))
    ring = np.column_stack([np.cos(a) * r, np.sin(a) * r])
    b.fill(head(ring), "yellow")
    # the florets, set on the sunflower's spiral; bigger and closer in the shade, thin in the light
    n = 190
    k = np.arange(n)
    rr = (DISC - 4) * np.sqrt((k + 0.5) / n)
    ang = k * math.radians(137.508)
    p = np.column_stack([np.cos(ang) * rr, np.sin(ang) * rr])
    scr = head(p)
    sf = (unit(scr - C) @ SHADE) * (rr / DISC)
    keep = (sf > -0.42) | (rng.random(n) < 0.35)
    rad = 1.25 + 1.2 * np.clip(sf, 0, None) + 0.45 * rr / DISC
    b.dots(scr[keep], rad[keep])
    # a crescent of shade inside the rim, and the rim itself
    for rad0, span in ((DISC - 5, 1.0), (DISC - 10, 0.75)):
        c0 = math.atan2(SHADE[1], SHADE[0]) - HEAD_ROT
        aa = np.linspace(c0 - 1.1 * span, c0 + 1.1 * span, 30)
        b.stroke(head(np.column_stack([np.cos(aa), np.sin(aa)]) * rad0), 2.2, (0.4, 0.4), 0.15)
    b.outline(head(ring), 3.4, shade=1.0)


def leaf(b: Block, base, angle: float, L: float, Wd: float, bend: float, teeth: int = 6):
    rng = b.rng
    t = np.linspace(0, 1, 110)
    hw = Wd / 2 * np.sin(math.pi * t**0.8) ** 0.85
    saw = (t * teeth + 0.3) % 1.0
    serr = np.where((t > 0.18) & (t < 0.93), 0.2 * saw**2, 0.0)
    upper = np.column_stack([t * L, hw * (1 + serr)])
    lower = np.column_stack([t * L, -hw * (1 + np.roll(serr, 5))])
    ring = np.vstack([upper, lower[::-1][1:-1]])

    def place(p):
        p = np.array(p, float)
        p[:, 1] += bend * p[:, 0] ** 2 / L
        return base + p @ rot(angle)

    b.fill(place(ring), "green")
    # the half away from the light, hatched
    half_up = place(np.vstack([upper, [[L, 0], [0, 0]]]))
    half_lo = place(np.vstack([lower, [[L, 0], [0, 0]]]))
    nup = unit(place(np.array([[L / 2, 10.0]])) - place(np.array([[L / 2, 0.0]])))[0]
    shaded = half_up if nup @ SHADE > 0 else half_lo
    b.hatch(shaded, angle + math.radians(55 if nup @ SHADE > 0 else -55), 4.2, 1.3, taper=(0.05, 0.6), inset=1.5)
    # midrib and veins
    tt = np.linspace(0.0, 0.9, 20)
    b.stroke(place(np.column_stack([tt * L, np.zeros_like(tt)])), 2.6, (0.02, 0.8), 0.1)
    for tv in (0.2, 0.34, 0.48, 0.62, 0.76):
        for sgn in (1, -1):
            h = Wd / 2 * np.sin(math.pi * (tv + 0.12) ** 0.8) ** 0.85 * 0.8
            b.stroke(place(np.array([(tv * L, 0), ((tv + 0.07) * L, sgn * h * 0.6), ((tv + 0.13) * L, sgn * h)])),
                     1.2, (0.05, 0.7), 0.15)
    b.outline(place(ring), 2.6, shade=0.8)


def stem(b: Block, root):
    rng = b.rng
    L = root[1] - C[1]
    pts = np.array([root + (0, 4), root + (-2, -44), C + (-10, 0.69 * L), C + (-13, 0.5 * L), C + (-4, 0.3 * L),
                    C + (0, 38)])
    line = resample(spline(pts), 1.0)
    n = len(line)
    w = np.linspace(14.5, 10.5, n)
    nr = normals(line)
    b.fill(np.vstack([line + nr * (w / 2)[:, None], (line - nr * (w / 2)[:, None])[::-1]]), "green")
    for sgn in (1, -1):
        edge_line = line + sgn * nr * (w / 2)[:, None]
        lit = float(np.mean(sgn * nr @ LIGHT)) > 0
        b.stroke(edge_line, 1.7 if lit else 3.0, (0.0, 0.0), 0.2, smooth=False)
    # a few short cuts of shade across the stem's dark side
    for y0 in rng.uniform(0.15, 0.85, 7):
        i = int(y0 * (n - 1))
        side_n = nr[i] if float(nr[i] @ SHADE) > 0 else -nr[i]
        p = line[i] + side_n * w[i] * 0.5
        b.stroke(np.array([p, p - side_n * w[i] * 0.45 + (0, -2.5)]), 1.1, (0.0, 0.8), 0.1, smooth=False)
    return line


def sky(b: Block):
    """A woodcut's sky: level lines, heavy at the top of the frame and thinning out toward the horizon."""
    x0, y0, x1, y1 = PANEL
    top_, fade = y0, 0.55 * HP
    ring = np.array([(x0 - 4, y0 - 4), (x1 + 4, y0 - 4), (x1 + 4, y0 + fade), (x0 - 4, y0 + fade)])
    b.hatch(ring, 0.0, 7.2, 2.2, jitter=0.1, taper=(0.0, 0.0), wave=0.6, breaks=0.35,
            tone=lambda p: np.clip(1 - (p[:, 1] - top_) / fade, 0, 1) ** 1.15)


def draw(seed: int = 11) -> Block:
    b = Block(seed)
    sky(b)
    root, gap = slab(b)
    line = stem(b, root)
    # the crack's near lip over the root of the stem
    lip = root + np.array([(-11, 0.5), (-4, 3.5), (5, 4.0), (12, 0.0), (9, 6.5), (-7, 6.8)])
    b.fill(lip, "black")

    def at(y):
        return line[np.argmin(np.abs(line[:, 1] - y))]

    L = root[1] - C[1]
    leaf(b, at(C[1] + 0.64 * L) + (-3, 0), math.radians(-146), 192, 55, -0.1, 7)
    leaf(b, at(C[1] + 0.77 * L) + (3, 0), math.radians(-27), 174, 50, 0.12, 6)
    petals(b, 12, math.pi / 12, 229, 44, back=True)
    petals(b, 12, 0.0, 215, 41, back=False)
    disc(b)
    return b
