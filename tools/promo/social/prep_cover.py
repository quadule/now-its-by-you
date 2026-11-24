"""The ride's ending: the daisy of the album cover, for the cloud and its line to turn into.

Finds where the flat face art (renders/review/artwork/cover/front-flat.png) lies in the cover photograph
(renders/review/artwork/cover-golf-3000.png) by matching features (a homography: the sheet is nearly flat), then
samples the daisy alone: places on its head (the petals, and the yellow middle), on its leaves, and the line of
its stem from the middle of the head down to the crack it grows from, each place with the art's colour there.
Writes renders/promo/social/synced/cover.json (places as x, y in the photograph, each 0..1 from its top left,
then r, g, b), cover-1080.jpg, and cover-check.png (the art warped onto the photograph, with the stem's line and
the head's circle drawn, to check by eye).

  uv run --with opencv-python-headless python tools/promo/social/prep_cover.py
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / "renders/review/artwork"
OUT = ROOT / "renders/promo/social/synced"

face = cv2.imread(str(ART / "cover/front-flat.png"))
photo = cv2.imread(str(ART / "cover-golf-3000.png"))
fs = 1200 / face.shape[1]
f_small = cv2.resize(face, None, fx=fs, fy=fs, interpolation=cv2.INTER_AREA)
ps = 0.6
p_small = cv2.resize(photo, None, fx=ps, fy=ps, interpolation=cv2.INTER_AREA)
sift = cv2.SIFT_create(8000)
ka, da = sift.detectAndCompute(cv2.cvtColor(f_small, cv2.COLOR_BGR2GRAY), None)
kb, db = sift.detectAndCompute(cv2.cvtColor(p_small, cv2.COLOR_BGR2GRAY), None)
pairs = cv2.BFMatcher().knnMatch(da, db, k=2)
good = [m for m, n in pairs if m.distance < 0.75 * n.distance]
src = np.float32([ka[m.queryIdx].pt for m in good]) / fs
dst = np.float32([kb[m.trainIdx].pt for m in good]) / ps
H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 6.0)
print(len(good), "matches,", int(mask.sum()), "agree")

# to check by eye: the art laid over the photograph, half and half
warped = cv2.warpPerspective(face, H, (photo.shape[1], photo.shape[0]))
inside = cv2.warpPerspective(np.full(face.shape[:2], 255, np.uint8), H, (photo.shape[1], photo.shape[0])) > 0
check = photo.copy()
check[inside] = (0.5 * photo[inside] + 0.5 * warped[inside]).astype(np.uint8)
cv2.imwrite(str(OUT / "cover-1080.jpg"), cv2.resize(photo, (1080, 1080), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 94])

# the daisy in the art, at a quarter of its size
a = cv2.resize(face, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA).astype(np.float32) / 255
h, w = a.shape[:2]
paper = np.median(a.reshape(-1, 3), axis=0)
yy, xx = np.mgrid[0:h, 0:w]
b, g, r = a[..., 0], a[..., 1], a[..., 2]
yellow = (r > 0.75) & (g > 0.55) & (b < 0.4)
cy, cx = [float(v.mean()) for v in np.nonzero(yellow)]
rad = np.hypot(xx - cx, yy - cy)
head_r = 0.21 * w
head = rad < head_r
middle = yellow & head
petal = head & ~middle & (b > paper[0] + 0.05) & (np.minimum(np.minimum(r, g), b) > 0.86)
green = (g > r + 0.015) & (g > b + 0.14) & (np.abs(xx - cx) < 0.2 * w) & (yy > cy) & (yy < cy + 0.45 * h)
# the stem: followed down from the head, the green nearest the line so far
stem, x = [], cx
for y in range(int(cy), h):
    row = np.nonzero(green[y] & (np.abs(np.arange(w) - x) < 0.012 * w))[0]
    if y > cy + head_r * 0.9 and len(row) == 0:
        if stem and y - stem[-1][1] > 0.01 * h:
            break
        continue
    if len(row):
        x = float(row.mean())
        stem.append((x, y))
stem = np.float32([(cx, cy)] + [p for p in stem if p[1] > cy + head_r * 0.5])
stem_line = np.zeros((h, w), bool)
for sx, sy in stem:
    stem_line[int(sy), max(0, int(sx - 0.008 * w)):int(sx + 0.008 * w)] = True
leaf = green & ~cv2.dilate(stem_line.astype(np.uint8), np.ones((1, 5), np.uint8)).astype(bool)
rng = np.random.default_rng(5)


def places(mask, n):
    """n places on the mask, as photograph x, y (0..1) and the art's colour."""
    ys, xs = np.nonzero(mask)
    k = rng.integers(0, len(ys), n)
    pts = np.float32(np.stack([(xs[k] + rng.random(n)) * 4, (ys[k] + rng.random(n)) * 4], 1))
    uv = cv2.perspectiveTransform(pts[None], H)[0] / photo.shape[0]
    return np.round(np.column_stack([uv, a[ys[k], xs[k]][:, ::-1]]), 4).tolist()


def to_photo(pts):
    return (cv2.perspectiveTransform(np.float32(pts)[None] * 4, H)[0] / photo.shape[0]).round(4).tolist()


step = max(1, len(stem) // 24)
line = to_photo(np.vstack([stem[::step], stem[-1:]]))
centre = to_photo([[cx, cy]])[0]
edge = to_photo([[cx + head_r, cy]])[0]
data = {"petals": places(petal, 26000), "middle": places(middle, 4000), "leaves": places(leaf, 4000), "stem": line,
        "daisy": centre, "head": float(np.hypot(edge[0] - centre[0], edge[1] - centre[1]))}
(OUT / "cover.json").write_text(json.dumps(data))
S = 1000
for (x0, y0), (x1, y1) in zip(line[:-1], line[1:]):
    cv2.line(check, (int(x0 * 3000), int(y0 * 3000)), (int(x1 * 3000), int(y1 * 3000)), (255, 0, 255), 6)
cv2.circle(check, (int(centre[0] * 3000), int(centre[1] * 3000)), int(data["head"] * 3000), (255, 0, 255), 4)
cv2.imwrite(str(OUT / "cover-check.png"), cv2.resize(check, (S, S), interpolation=cv2.INTER_AREA))
print("daisy at", centre, "head", round(data["head"], 4), "stem", len(line), "points to", line[-1],
      "| petal, middle, leaf pixels:", int(petal.sum()), int(middle.sum()), int(leaf.sum()))
