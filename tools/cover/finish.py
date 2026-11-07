"""The cover's last step: what a lens and a sensor add (a gentle fall-off to the corners, a little grain), then
the release sizes, and the QR read back from them.

    uv run --with pillow python tools/cover/finish.py [golf]

Reads renders/review/artwork/cover/render-3000.png (from scene.py --final) and writes, in
renders/review/artwork/: cover-3000.png, cover-3000.jpg (quality 92), cover-1500.png and cover-1500.jpg
(cover-golf-... from render-golf-3000.png with golf).
Then decodes the QR with zbarimg from the 1500 px files and from a rougher copy (smaller, softened, heavily
compressed, as a phone camera pointed at a screen might see it), and says whether each read.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "renders/review/artwork"
URL = "https://now.itsby.you"


def to_lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)


def finish(img: Image.Image, rng) -> Image.Image:
    a = np.asarray(img.convert("RGB"), np.float32) / 255
    h, w, _ = a.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / np.sqrt(2)
    lin = to_lin(a) * (1 - 0.16 * r ** 2.4)[..., None]          # the lens's fall-off, in light
    out = to_srgb(lin)
    grain = rng.standard_normal((h, w)).astype(np.float32)
    grain = ndi.gaussian_filter(grain, 0.6)
    out = out + (grain / grain.std() * 0.006)[..., None]        # a fine, even grain, the same in each channel
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8))


def reads(path: Path) -> bool:
    r = subprocess.run(["zbarimg", "-q", "--raw", str(path)], capture_output=True, text=True)
    return URL in r.stdout


def main():
    sfx = "-golf" if "golf" in sys.argv[1:] else ""
    img = finish(Image.open(ART / "cover" / f"render{sfx}-3000.png"), np.random.default_rng(3))
    img.save(ART / f"cover{sfx}-3000.png")
    img.save(ART / f"cover{sfx}-3000.jpg", quality=92, subsampling=0)
    small = img.resize((1500, 1500), Image.LANCZOS)
    small.save(ART / f"cover{sfx}-1500.png")
    small.save(ART / f"cover{sfx}-1500.jpg", quality=92, subsampling=0)
    checks = {f"cover{sfx}-1500.png": ART / f"cover{sfx}-1500.png", f"cover{sfx}-1500.jpg": ART / f"cover{sfx}-1500.jpg"}
    with tempfile.TemporaryDirectory() as td:
        rough = small.resize((820, 820), Image.BILINEAR).filter(ImageFilter.GaussianBlur(0.9))
        rp = Path(td) / "phone.jpg"
        rough.save(rp, quality=55)
        checks["820 px, softened, jpeg 55"] = rp
        ok = {name: reads(p) for name, p in checks.items()}
    for name, good in ok.items():
        print(f"QR {'reads' if good else 'DOES NOT READ'}: {name}")
    sys.exit(0 if all(ok.values()) else 1)


if __name__ == "__main__":
    main()
