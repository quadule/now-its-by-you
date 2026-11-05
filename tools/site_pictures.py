"""The home page's studio pictures, from the screenshots tools/site_pictures.mjs takes: each to 860 x 645 WebP in
web/sing/page/ (tab-page.webp, tab-arrange.webp, tab-mix.webp, tab-sing.webp).

usage: uv run python tools/site_pictures.py SHOTS_DIR
"""

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SIZE = (860, 645)


def main(shots: str) -> None:
    for name in ("page", "arrange", "mix", "sing"):
        picture = Image.open(Path(shots) / f"{name}.png").convert("RGB").resize(SIZE, Image.LANCZOS)
        out = ROOT / "web" / "sing" / "page" / f"tab-{name}.webp"
        picture.save(out, "WEBP", quality=82, method=6)
        print(f"{out.relative_to(ROOT)}: {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
