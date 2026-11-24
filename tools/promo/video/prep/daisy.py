"""daisy.json: the cover's woodcut daisy (tools/cover/woodcut.py) as its own marks, grouped by when it grows:
the crack it comes up through, then stem, leaves, back petals, front petals and disc. And a picture of the stages,
renders/promo/video/scratch/daisy-stages.png, to look at.

    uv run python tools/promo/video/prep/daisy.py

The marks are woodcut.py's own, made by its own functions in draw()'s order from the same seed, so the random
streams and every point are the cover's (checked: the marks equal draw()'s, one for one)."""
from __future__ import annotations

import math
import re
import sys

import numpy as np

import common

sys.path.insert(0, str(common.guard(common.ROOT / "tools/cover")))
import woodcut  # noqa: E402

SEED = 11  # draw()'s default, the cover's
INK_HEX = {"concrete": "#cdc5b4", "green": "#98a36b", "yellow": "#dea833", "white": "#fbf8f1", "grey": "#7a6b5c",
           "red": "#b8432e", "black": "#2b231d"}  # tools/cover/face.py INKS
TINTS = {"concrete", "green", "yellow"}  # face.py: transparent inks, multiplied with what is under them
CRUMBS = 7  # slab()'s last marks: the crumbs at the crack's mouth (b.dots of 7 points)


def staged() -> tuple[woodcut.Block, dict[str, tuple[int, int]], dict]:
    """draw(), step by step, noting which marks each step made; the crack's marks are told apart inside slab() by
    its own calls: from its first jagged() line to the first slab edge (its edge() projecting), and its last CRUMBS
    marks."""
    b = woodcut.Block(SEED)
    spans = {}
    n0 = len(b.marks)
    woodcut.sky(b)
    spans["sky"] = (n0, len(b.marks))

    seen = {"jagged": None, "project": None}
    jag, proj = woodcut.jagged, woodcut.project

    def jagged(*a, **k):
        if seen["jagged"] is None:
            seen["jagged"] = len(b.marks)
        return jag(*a, **k)

    def project(*a, **k):
        if seen["project"] is None and seen["jagged"] is not None and sys._getframe(1).f_code.co_name == "edge":
            seen["project"] = len(b.marks)
        return proj(*a, **k)

    woodcut.jagged, woodcut.project = jagged, project
    try:
        n0 = len(b.marks)
        root, gap = woodcut.slab(b)
        n1 = len(b.marks)
    finally:
        woodcut.jagged, woodcut.project = jag, proj
    spans["slab"] = (n0, n1)
    spans["crack"] = (seen["jagged"], seen["project"])
    spans["crumbs"] = (n1 - CRUMBS, n1)

    n0 = len(b.marks)
    line = woodcut.stem(b, root)
    lip = root + np.array([(-11, 0.5), (-4, 3.5), (5, 4.0), (12, 0.0), (9, 6.5), (-7, 6.8)])
    b.fill(lip, "black")
    spans["stem"] = (n0, len(b.marks))

    def at(y):
        return line[np.argmin(np.abs(line[:, 1] - y))]

    C, L = woodcut.C, root[1] - woodcut.C[1]
    n0 = len(b.marks)
    woodcut.leaf(b, at(C[1] + 0.64 * L) + (-3, 0), math.radians(-146), 192, 55, -0.1, 7)
    woodcut.leaf(b, at(C[1] + 0.77 * L) + (3, 0), math.radians(-27), 174, 50, 0.12, 6)
    spans["leaves"] = (n0, len(b.marks))
    n0 = len(b.marks)
    woodcut.petals(b, 12, math.pi / 12, 229, 44, back=True)
    spans["back_petals"] = (n0, len(b.marks))
    n0 = len(b.marks)
    woodcut.petals(b, 12, 0.0, 215, 41, back=False)
    woodcut.disc(b)
    spans["front_petals_disc"] = (n0, len(b.marks))
    assert b.marks == woodcut.draw(SEED).marks, "not the cover's marks"
    return b, spans, {"root": root.tolist(), "gap": gap.tolist(), "stem_line": line.tolist()}


def rings(d: str) -> list[np.ndarray]:
    return [np.array([float(v) for v in re.findall(r"-?\d+\.?\d*", seg)]).reshape(-1, 2)
            for seg in d.split("M")[1:]]


def main() -> None:
    from PIL import Image, ImageDraw

    b, spans, extra = staged()
    groups = [("crack", [spans["crack"], spans["crumbs"]]), ("stem", [spans["stem"]]), ("leaves", [spans["leaves"]]),
              ("back_petals", [spans["back_petals"]]), ("front_petals_disc", [spans["front_petals_disc"]])]
    pts = np.vstack([r for _, ss in groups for a, z in ss for m in b.marks[a:z] for r in rings(m[2])])
    lo, hi = pts.min(0), pts.max(0)
    side = float((hi - lo).max())
    norm = lambda r: np.round((r - lo) / side, 5)  # noqa: E731
    out_groups = []
    for name, ss in groups:
        marks = []
        for a, z in ss:
            for op, ink, d, rule in b.marks[a:z]:
                marks.append({"op": op, "ink": ink, "rule": rule, "rings": [norm(r).tolist() for r in rings(d)]})
        out_groups.append({"id": name, "marks": marks})
    stages = {"crack": 0, "stem": 1, "leaves": 2, "back_petals": 3, "front_petals_disc": 4}
    data = {
        "source": "tools/cover/woodcut.py draw(seed=11): sky(), slab() (its crack), stem() and the lip, two leaf(), "
                  "petals(back), petals(front), disc()",
        "box": {"face_units": "990 x 1440 face units at 300 px/in, y down (woodcut.py)", "x0": float(lo[0]),
                "y0": float(lo[1]), "size": side, "w": float((hi - lo)[0] / side), "h": float((hi - lo)[1] / side),
                "about": "a point p is stored as (p - (x0, y0)) / size; x right, y down, the longer side is 1"},
        "paint": "marks in painting order. op fill: a filled polygon of that ink (rule nonzero or evenodd over its "
                 "rings). op cut: white gouged out of the black only. Every line of the woodcut is cut as a filled "
                 "ribbon (Block.stroke/outline): its width is the polygon's own. As face.py prints them: one plate "
                 "per ink; black prints over the tints and is never hidden; a later fill of another ink hides a "
                 "tint beneath it; the tints (concrete, green, yellow) multiply with the paper.",
        "inks": INK_HEX, "tints": sorted(TINTS),
        "stages": stages,
        "groups": out_groups,
        "root": norm(np.array(extra["root"])).tolist(),
        "crack_gap": norm(np.array(extra["gap"])).tolist(),
        "stem_line": norm(np.array(extra["stem_line"])).tolist()[::4],
        "disc_centre": norm(woodcut.head(np.zeros(2))).tolist(), "disc_radius": woodcut.DISC / side,
    }
    p = common.write_json("daisy.json", data)
    common.say(f"daisy.json: {', '.join(f'{g['id']} {len(g['marks'])}' for g in out_groups)}; "
               f"{p.stat().st_size / 1e6:.2f} MB")

    # the stages, side by side, printed as face.py prints the plates (each ink a mask; tints multiply)
    S = 900
    paper = np.array([0xEE, 0xE3, 0xCB], float) / 255
    tiles = []
    for k in range(len(groups)):
        masks = {ink: Image.new("L", (S, int(S * data["box"]["h"]) + 4), 0) for ink in INK_HEX}
        for g in out_groups[: k + 1]:
            for m in g["marks"]:
                shape = Image.new("L", masks["black"].size, 0)
                dd = ImageDraw.Draw(shape)
                for ring in m["rings"]:
                    tmp = Image.new("L", shape.size, 0)
                    ImageDraw.Draw(tmp).polygon([(x * S, y * S) for x, y in ring], fill=255)
                    if m["rule"] == "evenodd":
                        shape = Image.fromarray(np.asarray(shape) ^ np.asarray(tmp))
                    else:
                        shape = Image.fromarray(np.maximum(np.asarray(shape), np.asarray(tmp)))
                del dd
                sh = np.asarray(shape) > 0
                for ink, mask in masks.items():
                    a = np.asarray(mask).copy()
                    if m["op"] == "fill":
                        if ink == m["ink"]:
                            a[sh] = 255
                        elif m["ink"] != "black":
                            a[sh] = 0
                    elif ink == "black":
                        a[sh] = 0
                    masks[ink] = Image.fromarray(a)
        img = np.tile(paper, (*np.asarray(masks["black"]).shape, 1))
        for ink in ("concrete", "green", "yellow", "white", "black"):
            col = np.array([int(INK_HEX[ink][i: i + 2], 16) for i in (1, 3, 5)], float) / 255
            a = (np.asarray(masks[ink]) / 255.0)[..., None]
            img = img * (1 - a + a * col) if ink in TINTS else img * (1 - a) + col * a
        tiles.append((img * 255).astype(np.uint8))
    sheet = np.concatenate(tiles, axis=1)
    dst = common.guard(common.SCRATCH / "daisy-stages.png")
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sheet).save(dst)
    common.say(dst)


if __name__ == "__main__":
    main()
