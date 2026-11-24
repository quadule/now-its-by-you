"""The look frames as the cover was finished after Blender (tools/cover/finish.py): the lens's fall-off to the
corners, in linear light, and a fine even grain. Writes <name>-finished.png beside each frame_*.png given.

    python3 tools/promo/video/blender/finish_look.py renders/promo/video/blender/look/frame_*.png
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def finish(a, rng):
    """a: float RGB 0..1 (sRGB). The cover's own numbers: fall-off 1 - 0.16 r^2.4 with r = 1 at the corners,
    grain a unit normal field blurred by sigma 0.6 px, scaled to 0.006, the same in each channel."""
    h, w, _ = a.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / np.sqrt(2)
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4) * (1 - 0.16 * r ** 2.4)[..., None]
    lin = np.clip(lin, 0, 1)
    out = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    g = ndi.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), 0.6)
    return np.clip(out + (g / g.std() * 0.006)[..., None], 0, 1)


for p in map(Path, sys.argv[1:]):
    if p.stem.endswith("-finished"):
        continue
    im = np.asarray(Image.open(p))
    a = im.astype(np.float32) / (65535 if im.dtype == np.uint16 else 255)
    out = finish(a[..., :3], np.random.default_rng(3))
    Image.fromarray((out * 255 + 0.5).astype(np.uint8)).save(p.with_name(p.stem + "-finished.png"))
    print(p.with_name(p.stem + "-finished.png"))
