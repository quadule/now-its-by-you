"""data/s09/: the seed packet's face as its plates, for s09_broadside to print one ink at a time.

    uv run python tools/promo/video/prep/s09_face.py

The face is tools/cover/face.py's front, printed again by its own functions (woodcut.py's marks from seed 11,
face.py's front_types(), layer_svg(), rasterise(), noise(), press(), fibres(), crease_distance()) in print_face()'s
order with its seed, 1966, so every random field is the cover's. What face.py keeps in one image is kept here
apart: the paper before any ink, each ink's cover (as it lies after the press and the cracks), and the handling
that darkens the paper afterwards. Black and red are split into the parts the film prints at different moments,
and a few covers that the finished face hides are kept too (the sky's lines where the roundel and the petals later
cover them, the red under the title's letters), pressed with the same noise as the plate they belong to.
The check: these layers composited as the film's shader composites them, from the 8-bit files, equal
renders/review/artwork/cover/front-color.png inside the crop (the result is printed and kept in face.json).

Everything is cropped to the face's frame-0 crop of the closing shot (blender/corners.json crop_uv_frame0, a few
pixels wider on each side), at face.py's 900 px/in (3 px a face unit).

Writes, under renders/promo/video/data/s09/:
  paper.png    RGB sRGB: the paper (formation cloud, fibres, flecks) before any ink
  handling.png L: the handling's multiplier on the printed paper, m = 0.75 + v / 255 * 0.25
  sky.png      R the sky's black as printed; G the sky's lines inside the roundel's ring (hidden when the roundel
               prints); B the sky's lines under the daisy's fills (hidden when the daisy prints)
  black.png    R the rules (the two borders and the panel's frame); G the "51"; B the daisy's black
  tints.png    R white; G yellow; B green (the daisy's)
  red.png      R the title band as printed (the title cut out of it, and the seed house's name at the crop's top
               edge); G the red inside the title's letters (what the
               band would be uncut); B the roundel's two rings
  grey.png     R MIN. and SEEDS; G concrete (its specks: every plate leaves a few where the tooth took ink)
  face.json    the crop, the inks, the sky's lines as vectors (each hatch row: its y and its stretches, centre
               lines in face units with widths), the title's words (x spans in crop px), the roundel, the check
"""
from __future__ import annotations

import copy
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

import common

COVER = common.guard(common.ROOT / "tools/cover")
sys.path.insert(0, str(COVER))
import face  # noqa: E402
import woodcut  # noqa: E402

ART = common.guard(common.ROOT / "renders/review/artwork/cover")
CORNERS = common.guard(common.ROOT / "renders/promo/video/blender/corners.json")
SEED_WOODCUT, SEED_FACE = 11, 1966
MARGIN_UV = 0.004          # the crop, this much wider than the frame's corners on each side


def staged():
    """woodcut.draw(), step by step (the same calls in the same order), noting where each part's marks fall, and the
    sky's hatch lines as drawn: each ribbon's centre line and width before its wobble."""
    b = woodcut.Block(SEED_WOODCUT)
    spans = {}
    ribbons = []
    orig = b._ribbon

    def rec(poly, w, wob, cut=False, corr=10):
        ribbons.append((np.array(poly, float), np.broadcast_to(np.asarray(w, float), (len(poly),)).copy(), len(b.marks)))
        return orig(poly, w, wob, cut, corr)

    b._ribbon = rec
    woodcut.sky(b)
    b._ribbon = orig
    spans["sky"] = (0, len(b.marks))
    n0 = len(b.marks)
    root, gap = woodcut.slab(b)
    spans["slab"] = (n0, len(b.marks))
    n0 = len(b.marks)
    line = woodcut.stem(b, root)
    lip = root + np.array([(-11, 0.5), (-4, 3.5), (5, 4.0), (12, 0.0), (9, 6.5), (-7, 6.8)])
    b.fill(lip, "black")

    def at(y):
        return line[np.argmin(np.abs(line[:, 1] - y))]

    C, L = woodcut.C, root[1] - woodcut.C[1]
    woodcut.leaf(b, at(C[1] + 0.64 * L) + (-3, 0), math.radians(-146), 192, 55, -0.1, 7)
    woodcut.leaf(b, at(C[1] + 0.77 * L) + (3, 0), math.radians(-27), 174, 50, 0.12, 6)
    woodcut.petals(b, 12, math.pi / 12, 229, 44, back=True)
    woodcut.petals(b, 12, 0.0, 215, 41, back=False)
    woodcut.disc(b)
    spans["daisy"] = (n0, len(b.marks))
    assert b.marks == woodcut.draw(SEED_WOODCUT).marks, "not the cover's marks"
    return b.marks, spans, ribbons


def press_fields(rng, shape):
    """The four noise fields face.press() draws, in its order."""
    return {"nz": face.noise(rng, shape, 0.9), "mot": face.noise(rng, shape, 14), "salt": face.noise(rng, shape, 1.1),
            "big": face.noise(rng, shape, 40)}


def press_with(m, f, key):
    """face.press()'s arithmetic on given fields (so a part of a plate is pressed with the plate's own noise)."""
    mb = ndi.gaussian_filter(m, 0.8)
    edge = np.clip((mb - 0.5 + (0.1 if key else 0.14) * f["nz"]) * 2.6 + 0.5, 0, 1)
    voids = np.clip((f["salt"] - 2.6) * 1.2, 0, 1) * np.clip(0.3 + 0.5 * f["big"], 0, 1)
    cover = edge * (0.98 + 0.006 * f["mot"]) * (1 - 0.4 * voids)
    rim = np.clip(edge - ndi.gaussian_filter(edge, 2.0), 0, 1)
    return np.clip(cover + 0.03 * rim, 0, 1)


def raster(svg_layer, marks, types, tmp, name):
    return face.rasterise(face.layer_svg(svg_layer, marks, types), tmp, name)


def main():
    corners = common.read_json(CORNERS)
    fc = np.array(corners["crop_uv_frame0"]["frame_corners_uv"])
    u0, v0 = fc[:, 0].min() - MARGIN_UV, fc[:, 1].min() - MARGIN_UV
    u1, v1 = fc[:, 0].max() + MARGIN_UV, fc[:, 1].max() + MARGIN_UV
    W, H = face.FW * face.S, face.FH * face.S
    x0, x1 = int(math.floor(u0 * W)), int(math.ceil(u1 * W))
    y0, y1 = int(math.floor(v0 * H)), int(math.ceil(v1 * H))
    crop = (slice(y0, y1), slice(x0, x1))

    marks, spans, ribbons = staged()
    types = face.front_types()
    sub = lambda a, z: marks[a:z]  # noqa: E731
    blank = {"occlude": ""}
    out_dir = common.out("s09/face.json").parent
    scratch = common.guard(common.SCRATCH / "s09")
    scratch.mkdir(parents=True, exist_ok=True)

    # ---- the plates, as face.print_face rasterises them, and the parts ----
    with tempfile.TemporaryDirectory(dir=scratch) as td:
        tmp = Path(td)
        masks = {k: raster(k, marks, types, tmp, k) for k in face.INKS}
        # black, by part: only that part's black fills, every other ink's fills and every cut still erasing them
        keep_black = lambda a, z: [m for i, m in enumerate(marks) if m[1] != "black" or m[0] == "cut" or a <= i < z]  # noqa: E731
        bt = face.front_types()
        parts = {
            "sky": raster("black", keep_black(*spans["sky"]), {"occlude": types["occlude"], "black": ""}, tmp, "b_sky"),
            "slab": raster("black", keep_black(*spans["slab"]), {"occlude": types["occlude"], "black": ""}, tmp, "b_slab"),
            "daisy": raster("black", keep_black(*spans["daisy"]), {"occlude": types["occlude"], "black": ""}, tmp, "b_daisy"),
        }
        i51 = bt["black"].index("<text")
        parts["rules"] = raster("black", [], {"occlude": "", "black": bt["black"][:i51]}, tmp, "b_rules")
        parts["n51"] = raster("black", [], {"occlude": "", "black": bt["black"][i51:]}, tmp, "b_51")
        # the sky's lines whole, nothing over them
        sky_whole = raster("black", sub(*spans["sky"]), blank, tmp, "b_sky_whole")
        occl = raster("black", [], {"occlude": "", "black": types["occlude"].replace('fill="#fff"', 'fill="#000"')},
                      tmp, "occlude")
        # red, by part: the band (rect and the title cut from it), the band uncut, the rings, the seed house's name
        red = types["red"]
        iband, ititle, iring = red.index("<rect"), red.index("<text", red.index("<rect")), red.index("<circle")
        rparts = {
            "house": raster("red", [], {"occlude": "", "red": red[:iband]}, tmp, "r_house"),
            "band": raster("red", [], {"occlude": "", "red": red[iband:iring]}, tmp, "r_band"),
            "rings": raster("red", [], {"occlude": "", "red": red[iring:]}, tmp, "r_rings"),
        }
        band_solid = raster("red", [], {"occlude": "", "red": red[iband:ititle]}, tmp, "r_band_solid")
        title = raster("red", [], {"occlude": "", "red": red[ititle:iring].replace('fill="#fff"', 'fill="#000"')},
                       tmp, "r_title")

    # ---- print_face's paper and inks, its random stream in its order ----
    rng = np.random.default_rng(SEED_FACE)
    shape = masks["black"].shape
    h, w = shape
    assert (w, h) == (W, H)
    paper = face.hex_lin(face.PAPER)
    cloud = 0.022 * face.noise(rng, shape, 70) + 0.012 * face.noise(rng, shape, 9)
    fib = face.fibres(rng, shape, int(26000 * w * h / (2970 * 4320)))
    col = paper[None, None, :] * (1 + cloud + 0.045 * fib)[..., None]
    col *= (1 + 0.012 * face.noise(rng, shape, 120))[..., None] * np.array([1.0, 0.995, 0.985])
    for _ in range(45):
        y, x, r = rng.integers(8, h - 8), rng.integers(8, w - 8), rng.uniform(1.2, 3.5)
        sy, sx = np.ogrid[y - 8:y + 8, x - 8:x + 8]
        spot = np.exp(-(((sy - y) ** 2 + (sx - x) ** 2) / r ** 2))
        col[y - 8:y + 8, x - 8:x + 8] *= (1 - rng.uniform(0.25, 0.6) * spot)[..., None] * np.array([1.0, 0.93, 0.85])
    paper_img = col.astype(np.float32).copy()
    del cloud, fib
    cracks = np.zeros(shape, np.float32)
    for c in face.FRONT_CREASES:
        if c[4] < 0.2:
            continue
        across, along = face.crease_distance(shape, c)
        wander = across + 1.2 * face.noise(rng, shape, 6)
        broken = np.clip(face.noise(rng, shape, 1.5) - 0.3, 0, 1)
        cracks = np.maximum(cracks, np.exp(-(wander / 0.9) ** 2) * broken * 0.6 * (c[4] / 0.3)
                            * np.clip(np.minimum(along, 1 - along) * 12, 0, 1))
        del across, along, wander, broken
    covers, fields, rolls = {}, {}, {}
    for k, (hexcol, (dx, dy), hard) in face.INKS.items():
        if masks[k].max() < 0.01:
            continue
        m = np.roll(masks[k], (dy, dx), axis=(0, 1))
        key = k in ("black", "red", "grey")
        ref_rng = copy.deepcopy(rng)
        _, cover_ref = face.press(m, ref_rng, key=key)
        f = press_fields(rng, shape)
        cover = press_with(m, f, key)
        assert np.array_equal(cover, cover_ref), f"press differs for {k}"
        assert ref_rng.bit_generator.state == rng.bit_generator.state
        cover *= 1 - 0.75 * cracks
        covers[k] = cover.astype(np.float32)
        rolls[k] = (dy, dx)
        if k in ("black", "red"):
            fields[k] = {n: v[crop] for n, v in f.items()}
        ink = face.hex_lin(hexcol)
        if k in face.TINTS:
            col *= 1 + (ink / paper - 1)[None, None, :] * cover[..., None]
        else:
            a = cover[..., None] * (0.97 if k != "white" else 0.8)
            col[:] = col * (1 - a) + ink[None, None, :] * a * (col / paper) ** 0.35
        del m, cover, cover_ref, f
    printed = col.copy()
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    de = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy))
    rub = np.exp(-de / 5) * np.clip(0.6 + 0.5 * face.noise(rng, shape, 6), 0, 1)
    grime = np.exp(-de / 90) * np.clip(0.5 + 0.5 * face.noise(rng, shape, 25), 0, 1)
    mult = (1 - 0.05 * grime)
    (ax, ay), (bx, by), _ = face.DOG_EAR
    S = face.S
    fold_d = ((xx - ax * S) * (by - ay) - (yy - ay * S) * (bx - ax)) / math.hypot(bx - ax, by - ay)
    mult = mult * (1 - 0.035 * np.exp(-np.abs(fold_d) / 25))
    for c in face.FRONT_CREASES:
        across, along = face.crease_distance(shape, c)
        env = np.clip(np.minimum(along, 1 - along) * 10, 0, 1)
        mult = mult * (1 - 0.03 * c[4] / 0.3 * np.exp(-(across / 30) ** 2) * env)
    rub_c = rub[crop]
    assert rub_c.max() < 1e-4, "the rubbed edge reaches into the crop"
    del yy, xx, de, rub, grime, fold_d

    # ---- the parts of black and red, as covers (the plate's cover shared out by where each part's marks lie) ----
    def share(total, part_masks, roll):
        bl = {n: ndi.gaussian_filter(np.roll(m, roll, axis=(0, 1))[crop], 1.5) for n, m in part_masks.items()}
        s = sum(bl.values())
        names = list(bl)
        fallback = names[0]
        out = {}
        for n in names:
            out[n] = np.where(s > 1e-4, bl[n] / np.maximum(s, 1e-4), 1.0 if n == fallback else 0.0) * total[crop]
        return out

    black_c = share(covers["black"], parts, rolls["black"])
    red_c = share(covers["red"], rparts, rolls["red"])
    for n, v in black_c.items():
        print(f"black {n}: max cover in crop {v.max():.3f}")
    for n, v in red_c.items():
        print(f"red {n}: max cover in crop {v.max():.3f}")
    cr = lambda a: 1 - 0.75 * cracks[crop]  # noqa: E731
    # the covers the finished face hides, pressed with their plate's noise
    rb, rr = rolls["black"], rolls["red"]
    sky_whole_c = press_with(np.roll(sky_whole, rb, axis=(0, 1))[crop], fields["black"], True) * cr(0)
    occl_c = ndi.gaussian_filter(np.roll(occl, rb, axis=(0, 1))[crop], 1.0)
    # where the daisy's fills (white petals, yellow disc, green stem) lie over the sky and hide its lines
    fills = np.maximum.reduce([np.roll(masks[k], rolls[k], axis=(0, 1))[crop] for k in ("white", "yellow", "green")])
    petal_c = ndi.gaussian_filter(fills, 1.0)
    near = lambda m, r: ndi.maximum_filter(m, size=2 * r + 1)  # noqa: E731
    sky_in_ring = sky_whole_c * near(occl_c, 6)
    sky_in_petals = sky_whole_c * near(petal_c, 6) * (1 - near(occl_c, 6))
    band_solid_c = press_with(np.roll(band_solid, rr, axis=(0, 1))[crop], fields["red"], True) * cr(0)
    title_c = np.roll(title, rr, axis=(0, 1))[crop]
    in_title = band_solid_c * near(ndi.gaussian_filter(title_c, 1.0), 6)

    # ---- the crop, written ----
    def u8(a):
        return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)

    def save(name, chans, mode="RGB"):
        arr = np.stack([u8(c) for c in chans], -1) if mode == "RGB" else u8(chans)
        Image.fromarray(arr, mode).save(out_dir / name, optimize=False, compress_level=6)

    paper_c = face.lin_srgb(paper_img[crop])
    Image.fromarray((paper_c * 255 + 0.5).astype(np.uint8), "RGB").save(out_dir / "paper.png", compress_level=6)
    mult_c = mult[crop]
    assert mult_c.min() >= 0.75, mult_c.min()
    Image.fromarray(np.clip((mult_c - 0.75) / 0.25 * 255 + 0.5, 0, 255).astype(np.uint8), "L").save(out_dir / "handling.png")
    save("sky.png", [black_c["sky"], sky_in_ring, sky_in_petals])
    save("black.png", [black_c["rules"], black_c["n51"], black_c["daisy"] + black_c["slab"]])
    tint = lambda k: covers[k][crop] if k in covers else np.zeros_like(mult_c)  # noqa: E731
    save("tints.png", [tint("white"), tint("yellow"), tint("green")])
    save("red.png", [red_c["band"] + red_c["house"], in_title, red_c["rings"]])
    save("grey.png", [tint("grey"), tint("concrete"), np.zeros_like(mult_c)])

    # ---- the check: the 8-bit layers composited as the film's shader does, against the cover's own image ----
    def load(name):
        a = np.asarray(Image.open(out_dir / name), np.float32) / 255
        return a if a.ndim == 3 else a[..., None]

    def lin(c):
        return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

    P = lin(load("paper.png"))
    M = 0.75 + load("handling.png")[..., 0] * 0.25
    sky_, blk, tin, rd, g2 = load("sky.png"), load("black.png"), load("tints.png"), load("red.png"), load("grey.png")
    gry = g2[..., 0]
    c = P.copy()
    inks = {k: face.hex_lin(v[0]) for k, v in face.INKS.items()}

    def tint_(c, k, cov):
        return c * (1 + (inks[k] / paper - 1)[None, None, :] * cov[..., None])

    def opaque(c, k, cov, alpha=0.97):
        a = cov[..., None] * alpha
        return c * (1 - a) + inks[k][None, None, :] * a * (c / paper) ** 0.35

    c = tint_(c, "concrete", g2[..., 1])
    c = tint_(c, "green", tin[..., 2])
    c = tint_(c, "yellow", tin[..., 1])
    c = opaque(c, "white", tin[..., 0], 0.8)
    c = opaque(c, "grey", gry)
    c = opaque(c, "red", np.minimum(rd[..., 0] + rd[..., 2], 1))
    c = opaque(c, "black", np.minimum(sky_[..., 0] + blk[..., 0] + blk[..., 1] + blk[..., 2], 1))
    c = c * M[..., None]
    mine = face.lin_srgb(c) * 255
    art = np.asarray(Image.open(ART / "front-color.png").convert("RGB"), np.float32)[crop]
    d = np.abs(mine - art)
    ref = face.lin_srgb(printed[crop] * mult_c[..., None]) * 255
    d_ref = np.abs(ref - art)
    check = {"max_abs_8bit": float(d.max()), "mean_abs_8bit": float(d.mean()), "p999_abs_8bit": float(np.percentile(d, 99.9)),
             "unquantised_max_abs_8bit": float(d_ref.max()), "unquantised_mean_abs_8bit": float(d_ref.mean())}
    print("check against front-color.png:", check)

    # ---- the sky's lines as vectors: rows by their height, each stretch a centre line with its widths ----
    rows = {}
    spacing = 7.2
    top = woodcut.PANEL[1] - 4
    for poly, wid, _ in ribbons:
        yc = float(np.median(poly[:, 1]))
        rows.setdefault(int(round((yc - top - spacing * 0.5) / spacing)), []).append((poly, wid))
    vy0, vy1 = y0 / S, y1 / S
    row_list = []
    for i in sorted(rows):
        st = sorted(rows[i], key=lambda pw: pw[0][0, 0])
        ys = float(np.median(np.concatenate([p[:, 1] for p, _ in st])))
        if ys < vy0 - 6 or ys > vy1 + 6:
            continue
        stretches = []
        for p, wd in st:
            k = max(1, len(p) // 60)
            idx = np.unique(np.r_[np.arange(0, len(p), k), len(p) - 1])
            stretches.append({"x": [round(float(v), 2) for v in p[idx, 0]], "y": [round(float(v), 2) for v in p[idx, 1]],
                              "w": [round(float(v), 3) for v in wd[idx]]})
        row_list.append({"i": i, "y": round(ys, 2), "stretches": stretches})
    # the title's words: x spans (crop px) of the letters, split where the gap between letters is widest
    cols = np.where(title_c.max(0) > 0.3)[0]
    gaps = np.diff(cols)
    cut = np.sort(np.argsort(gaps)[-3:])
    edges = [cols[0]] + sum(([cols[c], cols[c + 1]] for c in cut), []) + [cols[-1]]
    words = [[int(edges[2 * j]), int(edges[2 * j + 1])] for j in range(4)]
    rx, ry = woodcut.PANEL[0] + 116, woodcut.PANEL[1] + 110
    info = {
        "about": "the seed packet's front face (tools/cover/face.py, seed 1966; woodcut.py seed 11) as its plates, "
                 "cropped to the closing shot's frame-0 crop; px are the crop's, 3 per face unit; face units are "
                 "face.py's (1275 x 1650, y down)",
        "face_px": [W, H], "px_per_unit": S,
        "crop_px": [x0, y0, x1, y1], "crop_uv": [x0 / W, y0 / H, x1 / W, y1 / H], "size": [x1 - x0, y1 - y0],
        "paper": face.PAPER, "inks": {k: v[0] for k, v in face.INKS.items()},
        "register_px": {k: list(v[1]) for k, v in face.INKS.items()},
        "order": ["concrete", "green", "yellow", "white", "grey", "red", "black"],
        "tints": sorted(face.TINTS), "opacity": {"white": 0.8, "grey": 0.97, "red": 0.97, "black": 0.97},
        "handling": "m = 0.75 + v / 255 * 0.25, multiplies the printed paper",
        "files": {"paper.png": "RGB sRGB paper before ink", "handling.png": "L handling multiplier",
                  "sky.png": "R sky black as printed, G sky lines inside the roundel's ring, B sky lines under the daisy's fills",
                  "black.png": "R rules (borders, panel frame), G the 51, B the daisy's black",
                  "tints.png": "R white, G yellow, B green", "red.png": "R band as printed, G red inside the title's "
                  "letters, B the roundel's rings", "grey.png": "R MIN. and SEEDS, G concrete's specks"},
        "sky": {"spacing": spacing, "rows": row_list, "panel": list(woodcut.PANEL)},
        "title": {"words": words, "text": ["Now", "It’s", "by", "You"], "band_y": [134, 274]},
        "roundel": {"x": rx, "y": ry, "r": [74.0, 67.0]},
        "daisy": {"disc": [float(woodcut.C[0]), float(woodcut.C[1])], "disc_r": woodcut.DISC},
        "check": check,
    }
    common.write_json("s09/face.json", info)
    print(f"rows {len(row_list)}; words {words}; crop {x1 - x0} x {y1 - y0}")


if __name__ == "__main__":
    main()
