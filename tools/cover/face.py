"""The seed packets' faces, made ready for Blender: the printed paper, the ink's bite, and each sheet's shape.

    uv run --with segno --with pillow python tools/cover/face.py [front] [back]    # both, if neither named

Two packets, 4.25 x 5.5 in (1275 x 1650 units, 300 units/in). The one in front shows its face: the seed
house's name over a red stripe carrying the title, and the woodcut from woodcut.py in a framed panel with
the count in a roundel. The one behind shows its back: the envelope's flaps (side flaps, the bottom flap
folded up, the top flap closed), the sowing lines, and the QR in a ruled box. Type in Young Serif and Libre
Caslon Text (fonts/ and fonts.conf beside the outputs); the QR fresh from segno. Each ink is rasterised on
its own at 900 px/in and printed onto the paper in turn, a little out of register, with a letterpress edge.
Writes to renders/review/artwork/cover/, for each of front and back:

    <side>-color.png   the printed paper, sRGB (3825 x 4950)
    <side>-bump.png    16-bit height: ink pressed in, the tooth, the creases' sharp lines, the flaps' steps
    <side>-ink.png     where ink lies (for the shader's roughness)
    <side>-flat.png    as printed, flat, without handling (for checking)
    <side>-sheet.npy   the sheet's shape: a grid of points in metres, for scene.py

and faces.json with the sizes and each bump's range.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import segno
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent))
import woodcut  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "renders/review/artwork/cover"
FW, FH = 1275, 1650                # face units: 300 per inch
S = 3                              # pixels per unit in the textures: 900 px/in
MM = 25.4 / 300                    # one unit in mm
URL = "https://now.itsby.you"
FONT = "Libre Caslon Text"         # the small type: the seed house, the count, the sowing lines
DISPLAY = "Young Serif"            # the title

PAPER = "#eee3cb"
INKS = {  # colour, register offset in px, how hard the plate bit (for the bump)
    "concrete": ("#cdc5b4", (-3, -2), 0.35),
    "green": ("#98a36b", (4, 2), 0.45),
    "yellow": ("#dea833", (-4, 3), 0.45),
    "white": ("#fbf8f1", (3, 4), 0.35),
    "grey": ("#7a6b5c", (1, 1), 0.8),
    "red": ("#b8432e", (2, -1), 1.0),
    "black": ("#2b231d", (0, 0), 1.0),
}
TINTS = {"concrete", "green", "yellow"}   # transparent inks: they multiply with what is under them


def _scaled(creases):
    return [(x0 * FW, y0 * FH, x1 * FW, y1 * FH, *rest) for x0, y0, x1, y1, *rest in creases]


# creases, as fractions of the face: (x0, y0, x1, y1, depth mm, half-width mm, +1 ridge / -1 valley)
FRONT_CREASES = _scaled([
    (-0.04, 0.58, 1.04, 0.52, 0.40, 2.6, -1),    # folded across once, soft
    (-0.01, 0.33, 0.35, -0.01, 0.30, 1.8, 1),    # the top left corner, bent back once
    (1.01, 0.68, 0.78, 1.01, 0.28, 1.6, 1),      # the lower right, from being held
    (-0.01, 0.04, 1.01, 0.037, 0.12, 0.9, -1),   # where the flap was opened once
    (-0.01, 0.73, 0.19, 0.69, 0.20, 1.2, -1),    # a small one at the left edge
    (0.71, -0.01, 0.87, 0.21, 0.16, 1.4, -1),    # and one from the top edge
    (1.01, 0.36, 0.65, 0.49, 0.14, 2.0, 1),      # a long soft one across the flower's right
    (-0.01, 0.87, 0.11, 1.01, 0.16, 1.2, -1),    # the bottom left corner, handled
])
BACK_CREASES = _scaled([   # soft enough not to crack the ink, and clear of the QR
    (-0.03, 0.47, 1.03, 0.55, 0.19, 2.4, -1),
    (0.62, -0.01, 1.01, 0.30, 0.17, 1.6, 1),
    (-0.01, 0.20, 0.25, -0.01, 0.16, 1.2, 1),
])
DOG_EAR = ((-2, 190), (190, -2), 20.0)          # the front's, top left: fold line (face units), degrees lifted

# the back's construction, outermost last: (outline in face units, thickness mm)
SIDE = 140
FLAPS = [
    ([(0, 0), (SIDE, 40), (SIDE, FH - 40), (0, FH)], 0.11),                       # left side flap
    ([(FW, 0), (FW - SIDE, 40), (FW - SIDE, FH - 40), (FW, FH)], 0.11),           # right side flap
    ([(0, FH), (0, 0.455 * FH), (150, 0.394 * FH), (FW - 150, 0.394 * FH), (FW, 0.455 * FH), (FW, FH)],
     0.12),                                                                        # bottom flap, folded up
    ([(0, 0), (FW, 0), (FW, 0.384 * FH), (FW - 56, 0.423 * FH), (56, 0.423 * FH), (0, 0.384 * FH)],
     0.12),                                                                        # top flap, closed
]


def hex_lin(h: str) -> np.ndarray:
    c = np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)


def noise(rng, shape, sigma: float) -> np.ndarray:
    """Smooth noise of unit deviation over a feature size of about sigma px (broad noise made small, then
    enlarged)."""
    f = max(1, int(sigma / 3))
    small = tuple(int(math.ceil(s / f)) + 2 for s in shape)
    n = ndi.gaussian_filter(rng.standard_normal(small).astype(np.float32), sigma / f, mode="wrap")
    if f > 1:
        n = ndi.zoom(n, f, order=3)
    n = n[:shape[0], :shape[1]]
    return n / (n.std() + 1e-9)


# ---- the layouts ---------------------------------------------------------------------------------------

def spaced(x: float, spacing: float) -> float:
    """Letterspaced text centred on x: the spacing after the last letter would pull it left."""
    return x + spacing / 2


def qr_rects(x0: float, y0: float, module: float) -> tuple[str, int]:
    q = segno.make(URL, error="m", micro=False)
    rows = list(q.matrix_iter(border=0))
    out = []
    for j, row in enumerate(rows):
        for i, v in enumerate(row):
            if v:  # a hair over a module so neighbours join without seams
                out.append(f'<rect x="{x0 + i * module:.2f}" y="{y0 + j * module:.2f}" '
                           f'width="{module + 0.25:.2f}" height="{module + 0.25:.2f}"/>')
    return f'<g fill="#000">{"".join(out)}</g>', len(rows)


def borders() -> str:
    return (f'<rect x="36" y="36" width="{FW - 72}" height="{FH - 72}" fill="none" stroke="#000" stroke-width="4.5"/>'
            f'<rect x="48" y="48" width="{FW - 96}" height="{FH - 96}" fill="none" stroke="#000" stroke-width="1.6"/>')


def front_types() -> dict[str, str]:
    """The front's type and rules, per ink, plus 'occlude': shapes that clear every ink under them."""
    t, d = f'font-family="{FONT}"', f'font-family="{DISPLAY}"'
    x0, y0, x1, y1 = woodcut.PANEL
    cx = FW / 2
    black = [borders(),
             f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="none" stroke="#000" '
             'stroke-width="2.6"/>']
    # the seed house's name, then the variety's on a red stripe, cut out of the red
    red = [f'<text x="{spaced(cx, 12):.1f}" y="112" text-anchor="middle" {t} font-size="34" letter-spacing="12" '
           'font-weight="bold" fill="#000">THE VOLUNTEERS</text>',
           f'<rect x="{x0}" y="134" width="{x1 - x0}" height="140" fill="#000"/>',
           f'<text x="{cx}" y="239" text-anchor="middle" {d} font-size="98" fill="#fff">Now It’s by You</text>']
    # the count, in a roundel like an old packet's price, in the picture's upper left
    rx, ry, r = x0 + 116, y0 + 110, 74.0
    occlude = f'<circle cx="{rx}" cy="{ry}" r="{r + 3}" fill="#fff"/>'
    red += [f'<circle cx="{rx}" cy="{ry}" r="{r}" fill="none" stroke="#000" stroke-width="3.6"/>',
            f'<circle cx="{rx}" cy="{ry}" r="{r - 7}" fill="none" stroke="#000" stroke-width="1.2"/>']
    black.append(f'<text x="{rx}" y="{ry + 18}" text-anchor="middle" {d} font-size="54" fill="#000">51</text>')
    grey = [f'<text x="{spaced(rx, 4):.1f}" y="{ry - 29}" text-anchor="middle" {t} font-size="17" '
            'letter-spacing="4" fill="#000">MIN.</text>',
            f'<text x="{spaced(rx, 4):.1f}" y="{ry + 44}" text-anchor="middle" {t} font-size="17" '
            'letter-spacing="4" fill="#000">SEEDS</text>']
    return {"black": "".join(black), "red": "".join(red), "grey": "".join(grey), "occlude": occlude}


def back_types() -> dict[str, str]:
    """The back: the seed house on the closed flap, the sowing lines on the bottom flap, and the QR in a ruled
    box at the lower right, where it shows past the packet in front."""
    t = f'font-family="{FONT}"'
    cx = FW / 2
    y1 = 0.514 * FH                     # the sowing lines' heading, below the flaps' edges
    red = [f'<text x="{spaced(cx, 10):.1f}" y="{0.215 * FH:.0f}" text-anchor="middle" {t} font-size="30" '
           'letter-spacing="10" font-weight="bold" fill="#000">THE VOLUNTEERS</text>',
           f'<text x="{spaced(cx, 9):.1f}" y="{y1:.0f}" text-anchor="middle" {t} font-size="30" letter-spacing="9" '
           'font-weight="bold" fill="#000">SOWING INSTRUCTIONS</text>']
    lines = ["1. Play it. The file is a song.", "2. Run it. It sings a new version, today.",
             "3. Sing into it, and pass it on."]
    black = [f'<path d="M{cx - 150} {0.215 * FH + 30:.0f} h300" stroke="#000" stroke-width="1.4"/>',
             f'<path d="M140 {y1 + 40:.0f} h{FW - 280}" stroke="#000" stroke-width="1.2"/>',
             f'<path d="M140 {y1 + 48:.0f} h{FW - 280}" stroke="#000" stroke-width="3.0"/>']
    black += [f'<text x="150" y="{y1 + 122 + 64 * i:.0f}" {t} font-size="38" fill="#000">{s}</text>'
              for i, s in enumerate(lines)]
    bx0, by1, bx1 = 730, FH - 68, 1150        # large enough to read from the cover at 1500 px on a phone
    by0 = by1 - (bx1 - bx0)
    black += [f'<rect x="{bx0}" y="{by0}" width="{bx1 - bx0}" height="{by1 - by0}" fill="none" stroke="#000" '
              'stroke-width="3.4"/>',
              f'<rect x="{bx0 + 8}" y="{by0 + 8}" width="{bx1 - bx0 - 16}" height="{by1 - by0 - 16}" fill="none" '
              'stroke="#000" stroke-width="1.2"/>']
    module = 12.4
    qr, n = qr_rects((bx0 + bx1) / 2 - 12.5 * module, (by0 + by1) / 2 - 12.5 * module, module)
    black.append(qr)
    return {"black": "".join(black), "red": "".join(red), "occlude": ""}


def clip_defs() -> str:
    x0, y0, x1, y1 = woodcut.PANEL
    return (f'<defs><clipPath id="panel"><rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}"/>'
            '</clipPath></defs>')


def layer_svg(layer: str, marks, types: dict[str, str]) -> str:
    body = []
    for op, ink, d, rule in marks:
        if op == "fill":
            if ink == layer:
                col = "#000"
            elif ink == "black":
                continue      # the key block prints over the tints; it never takes them away
            else:
                col = "#fff"  # anything else painted later hides this ink beneath it
        else:                 # a cut: white out of the black
            if layer != "black":
                continue
            col = "#fff"
        body.append(f'<path d="{d}" fill="{col}" fill-rule="{rule}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{FW * S}" height="{FH * S}" '
            f'viewBox="0 0 {FW} {FH}">{clip_defs()}<rect width="{FW}" height="{FH}" fill="#fff"/>'
            f'<g clip-path="url(#panel)">{"".join(body)}</g>{types["occlude"]}{types.get(layer, "")}</svg>')


def rasterise(svg: str, tmp: Path, name: str) -> np.ndarray:
    src, dst = tmp / f"{name}.svg", tmp / f"{name}.png"
    src.write_text(svg)
    env = dict(os.environ, FONTCONFIG_FILE=str(OUT / "fonts.conf"))
    subprocess.run(["rsvg-convert", str(src), "-o", str(dst)], check=True, env=env)
    g = np.asarray(Image.open(dst).convert("L"), np.float32) / 255
    return 1 - g


def polygon_mask(shape, poly) -> np.ndarray:
    img = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(img).polygon([(x * S, y * S) for x, y in poly], fill=255)
    return ndi.gaussian_filter(np.asarray(img, np.float32) / 255, 0.7)


# ---- printing ------------------------------------------------------------------------------------------

def crease_distance(shape, c) -> tuple[np.ndarray, np.ndarray]:
    """Signed distance in px from a crease line, and how far along it (0..1)."""
    h, w = shape
    x0, y0, x1, y1 = (v * S for v in c[:4])
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.array([x1 - x0, y1 - y0], np.float32)
    L = float(np.hypot(*d))
    d /= L
    along = ((xx - x0) * d[0] + (yy - y0) * d[1]) / L
    across = (xx - x0) * -d[1] + (yy - y0) * d[0]
    return across, along


def press(m: np.ndarray, rng, key: bool) -> tuple[np.ndarray, np.ndarray]:
    """One plate's ink on paper: a slightly ragged edge, uneven take, specks where the tooth missed it, and
    the ink squeezed toward the edges of the impression. Returns (the impression, the ink's cover)."""
    nz = noise(rng, m.shape, 0.9)
    mb = ndi.gaussian_filter(m, 0.8)
    edge = np.clip((mb - 0.5 + (0.1 if key else 0.14) * nz) * 2.6 + 0.5, 0, 1)
    mot = noise(rng, m.shape, 14)
    salt = noise(rng, m.shape, 1.1)
    voids = np.clip((salt - 2.6) * 1.2, 0, 1) * np.clip(0.3 + 0.5 * noise(rng, m.shape, 40), 0, 1)
    cover = edge * (0.98 + 0.006 * mot) * (1 - 0.4 * voids)
    rim = np.clip(edge - ndi.gaussian_filter(edge, 2.0), 0, 1)
    return edge, np.clip(cover + 0.03 * rim, 0, 1)


def fibres(rng, shape, count: int) -> np.ndarray:
    h, w = shape
    img = Image.new("F", (w, h), 0.0)
    dr = ImageDraw.Draw(img)
    for _ in range(count):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        a, L = rng.uniform(0, math.pi), rng.uniform(10, 55)
        bend = rng.normal(0, 4)
        pts = [(x + math.cos(a) * L * t - math.sin(a) * bend * (t * t - t), y + math.sin(a) * L * t
                + math.cos(a) * bend * (t * t - t)) for t in np.linspace(0, 1, 5)]
        dr.line(pts, fill=float(rng.choice([-1.0, 1.0]) * rng.uniform(0.4, 1.0)), width=1)
    return ndi.gaussian_filter(np.asarray(img, np.float32), 0.6)


def print_face(side: str, marks, types, creases, dog_ear, flaps, rng) -> dict:
    with tempfile.TemporaryDirectory() as td:
        masks = {k: rasterise(layer_svg(k, marks, types), Path(td), k) for k in INKS}
    shape = masks["black"].shape
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    # the paper: cream, a little cloudy in its formation, fibres, the odd fleck
    paper = hex_lin(PAPER)
    cloud = 0.022 * noise(rng, shape, 70) + 0.012 * noise(rng, shape, 9)
    fib = fibres(rng, shape, int(26000 * w * h / (2970 * 4320)))
    col = paper[None, None, :] * (1 + cloud + 0.045 * fib)[..., None]
    col *= (1 + 0.012 * noise(rng, shape, 120))[..., None] * np.array([1.0, 0.995, 0.985])  # a warmer drift
    for _ in range(45):
        y, x, r = rng.integers(8, h - 8), rng.integers(8, w - 8), rng.uniform(1.2, 3.5)
        sy, sx = np.ogrid[y - 8:y + 8, x - 8:x + 8]
        spot = np.exp(-(((sy - y) ** 2 + (sx - x) ** 2) / r**2))
        col[y - 8:y + 8, x - 8:x + 8] *= (1 - rng.uniform(0.25, 0.6) * spot)[..., None] * np.array([1.0, 0.93, 0.85])

    # the envelope's flaps, each lying over the ones before it. Only the edge of whichever is on top shows,
    # a hair darker where it was cut; an edge underneath is felt through the paper as a soft swelling
    step = np.zeros(shape, np.float32)
    top = np.full(shape, -1, np.int8)
    for i, (poly, thick) in enumerate(flaps):
        m = polygon_mask(shape, poly)
        step += m * thick * 1000
        top = np.where(m > 0.5, i, top).astype(np.int8)
    if flaps:
        edge = ndi.gaussian_filter((ndi.maximum_filter(top, 3) != ndi.minimum_filter(top, 3)).astype(np.float32), 0.8)
        soft = ndi.gaussian_filter(step, 10)
        step = soft + (step - soft) * np.clip(ndi.gaussian_filter(edge, 4) * 6, 0, 1)
        col *= (1 - 0.07 * edge)[..., None]

    # print each plate in turn
    flat = paper[None, None, :] * np.ones(shape + (3,), np.float32)
    ink_all = np.zeros(shape, np.float32)
    bite = np.zeros(shape, np.float32)
    cracks = np.zeros(shape, np.float32)
    for c in creases:  # where a sharper crease crosses the ink, the ink has cracked, finely
        if c[4] < 0.2:
            continue
        across, along = crease_distance(shape, c)
        wander = across + 1.2 * noise(rng, shape, 6)
        broken = np.clip(noise(rng, shape, 1.5) - 0.3, 0, 1)
        cracks = np.maximum(cracks, np.exp(-(wander / 0.9) ** 2) * broken * 0.6 * (c[4] / 0.3)
                            * np.clip(np.minimum(along, 1 - along) * 12, 0, 1))
    for k, (hexcol, (dx, dy), hard) in INKS.items():
        if masks[k].max() < 0.01:
            continue
        m = np.roll(masks[k], (dy, dx), axis=(0, 1))
        edge, cover = press(m, rng, key=k in ("black", "red", "grey"))
        cover *= 1 - 0.75 * cracks
        ink = hex_lin(hexcol)
        for tgt in (col, flat):
            if k in TINTS:
                tgt *= 1 + (ink / paper - 1)[None, None, :] * cover[..., None]
            else:
                a = cover[..., None] * (0.97 if k != "white" else 0.8)
                tgt[:] = tgt * (1 - a) + ink[None, None, :] * a * (tgt / paper) ** 0.35
        ink_all = np.maximum(ink_all, cover)
        bite = np.maximum(bite, edge * hard)

    # handling: the fold edges rubbed pale, a little grime inboard of them, darker at a dog-eared corner
    de = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy))
    rub = np.exp(-de / 5) * np.clip(0.6 + 0.5 * noise(rng, shape, 6), 0, 1)
    grime = np.exp(-de / 90) * np.clip(0.5 + 0.5 * noise(rng, shape, 25), 0, 1)
    col *= (1 - 0.05 * grime)[..., None]
    fold_d = None
    if dog_ear:
        (ax, ay), (bx, by), _ = dog_ear
        fold_d = ((xx - ax * S) * (by - ay) - (yy - ay * S) * (bx - ax)) / math.hypot(bx - ax, by - ay)
        col *= (1 - 0.035 * np.exp(-np.abs(fold_d) / 25))[..., None]
    col = col * (1 - rub[..., None] * 0.5) + (paper * 1.05)[None, None, :] * rub[..., None] * 0.5
    for c in creases:  # a crease gathers a little dirt
        across, along = crease_distance(shape, c)
        env = np.clip(np.minimum(along, 1 - along) * 10, 0, 1)
        col *= (1 - 0.03 * c[4] / 0.3 * np.exp(-(across / 30) ** 2) * env)[..., None]

    Image.fromarray((lin_srgb(col) * 255 + 0.5).astype(np.uint8)).save(OUT / f"{side}-color.png")
    Image.fromarray((lin_srgb(flat) * 255 + 0.5).astype(np.uint8)).save(OUT / f"{side}-flat.png")
    Image.fromarray((np.clip(ink_all, 0, 1) * 255 + 0.5).astype(np.uint8)).save(OUT / f"{side}-ink.png")

    # the bump, in micrometres: the plates' bite, the tooth, the fibres, each crease's sharp line, the flaps
    hgt = -24 * ndi.gaussian_filter(bite, 1.6) + 3 * ndi.gaussian_filter(bite, 9) + ndi.gaussian_filter(step, 1.0)
    hgt += 3.5 * noise(rng, shape, 0.9) + 6 * noise(rng, shape, 3.2) + 5 * noise(rng, shape, 12) + 3 * fib
    for c in creases:
        across, along = crease_distance(shape, c)
        env = np.clip(np.minimum(along, 1 - along) * 10, 0, 1)
        hgt += c[6] * 18 * (c[4] / 0.3) * np.exp(-np.abs(across) / 2.2) * env
    if fold_d is not None:
        hgt -= 10 * np.exp(-np.abs(fold_d) / 2.0)
    lo, hi = float(hgt.min()), float(hgt.max())
    Image.fromarray(((hgt - lo) / (hi - lo) * 65535 + 0.5).astype(np.uint16)).save(OUT / f"{side}-bump.png")
    return {"px": [w, h], "bump_um": [lo, hi]}


def main(sides):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "faces.json"
    info = json.loads(path.read_text()) if path.exists() else {}
    info.update({"width_mm": FW * MM, "height_mm": FH * MM, "url": URL})
    jobs = {"front": (1966, lambda: woodcut.draw().marks, front_types, FRONT_CREASES, DOG_EAR, []),
            "back": (1967, lambda: [], back_types, BACK_CREASES, None, FLAPS)}
    for side in sides:
        seed_no, marks, types, creases, dog_ear, flaps = jobs[side]
        rng = np.random.default_rng(seed_no)
        info[side] = print_face(side, marks(), types(), creases, dog_ear, flaps, rng)
        sheet = make_sheet(rng, creases, dog_ear)
        np.save(OUT / f"{side}-sheet.npy", sheet.astype(np.float32))
        info[side]["sheet_grid"] = list(sheet.shape[:2])
        path.write_text(json.dumps(info, indent=1))
        print(side, json.dumps(info[side]))


# ---- the sheet's shape ---------------------------------------------------------------------------------

def make_sheet(rng, creases, dog_ear, step_mm: float = 0.15) -> np.ndarray:
    """The packet's side toward us as a grid of points (rows bottom to top), in metres: x across, y up, z
    out toward the viewer. The seeds make a low pillow; creases, a gentle cockle, a rolled edge where the
    paper turns round the fold, and perhaps a dog-eared corner."""
    Wm, Hm = FW * MM, FH * MM
    nx, ny = int(round(Wm / step_mm)) + 1, int(round(Hm / step_mm)) + 1
    X, Y = np.meshgrid(np.linspace(0, Wm, nx), np.linspace(0, Hm, ny))
    fx, fy = X / MM, (Hm - Y) / MM           # face units, y down
    Z = np.zeros_like(X)

    # the seeds' pillow: low in the packet, gone at the folds
    wx = np.sin(np.pi * X / Wm) ** 0.55
    wy = np.sin(np.pi * np.clip(Y / (0.62 * Hm), 0, 1)) ** 0.7 * (Y < 0.62 * Hm)
    Z += 2.8 * wx * wy * (1 + 0.08 * (X / Wm - 0.5))
    # the seeds themselves, felt through the paper
    for _ in range(11):
        cx, cy = rng.uniform(0.2, 0.8) * Wm, rng.uniform(0.12, 0.38) * Hm
        a, L, r = rng.uniform(0, np.pi), rng.uniform(2.2, 3.2), rng.uniform(0.8, 1.1)
        u = (X - cx) * np.cos(a) + (Y - cy) * np.sin(a)
        v = -(X - cx) * np.sin(a) + (Y - cy) * np.cos(a)
        Z += 0.14 * np.exp(-((u / L) ** 2 + (v / r) ** 2) * 2)
    # cockle: the paper was never quite flat
    for sigma_mm, amp in ((15, 0.22), (1.5, 0.08), (4, 0.12)):
        ck = ndi.gaussian_filter(rng.standard_normal((ny, nx)).astype(np.float32), sigma_mm / step_mm, mode="reflect")
        Z += amp * ck / ck.std()
    # creases: a sharp tent with a soft shoulder, one side left a touch higher than the other
    for x0, y0, x1, y1, depth, width, sgn in creases:
        d = np.array([x1 - x0, y1 - y0], float)
        L = np.hypot(*d)
        d /= L
        across = ((fx - x0) * -d[1] + (fy - y0) * d[0]) * MM
        along = ((fx - x0) * d[0] + (fy - y0) * d[1]) / L
        env = np.clip(np.minimum(along, 1 - along) * 8, 0, 1) ** 0.7
        Z += sgn * depth * env * (np.exp(-np.abs(across) / width) + 0.35 * np.tanh(across / (2.5 * width)))
    # the edges roll away where the paper turns round the fold
    de = np.minimum(np.minimum(X, Wm - X), np.minimum(Y, Hm - Y))
    Z -= 0.28 * np.clip(1 - de / 0.7, 0, 1) ** 2
    # the edges not quite straight
    P = np.stack([X, Y, Z], -1)
    jit = 0.07 * np.clip(1 - de / 0.3, 0, 1)
    P[..., 0] += jit * 3 * ndi.gaussian_filter(rng.standard_normal((ny, nx)), 4)
    P[..., 1] += jit * 3 * ndi.gaussian_filter(rng.standard_normal((ny, nx)), 4)
    if dog_ear:
        # the corner beyond the fold line lifted toward us, curling a little as it goes
        (ax, ay), (bx, by), deg = dog_ear
        A = np.array([ax * MM, Hm - ay * MM])
        B = np.array([bx * MM, Hm - by * MM])
        u = (B - A) / np.linalg.norm(B - A)
        n = np.array([u[1], -u[0]])               # in the sheet's plane, toward the corner
        corners = np.array([(0, 0), (Wm, 0), (0, Hm), (Wm, Hm)])
        corner = corners[np.argmin(np.linalg.norm(corners - (A + B) / 2, axis=1))]
        if n @ (corner - A) < 0:
            n = -n
        rel = P[..., :2] - A
        dist = rel @ n
        beyond = dist > 0
        ang = np.radians(deg) * np.clip(dist / 1.2, 0, 1) + np.radians(10) * np.clip(dist / 12, 0, 1) ** 2
        along = rel @ u
        base_z = P[..., 2]
        newd = dist * np.cos(ang) - base_z * np.sin(ang)
        newz = dist * np.sin(ang) + base_z * np.cos(ang)
        P[..., 0] = np.where(beyond, A[0] + along * u[0] + newd * n[0], P[..., 0])
        P[..., 1] = np.where(beyond, A[1] + along * u[1] + newd * n[1], P[..., 1])
        P[..., 2] = np.where(beyond, newz, P[..., 2])
    return P / 1000.0


if __name__ == "__main__":
    main([a for a in sys.argv[1:] if a in ("front", "back")] or ["front", "back"])
