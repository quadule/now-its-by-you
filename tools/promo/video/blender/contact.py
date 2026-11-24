"""A contact sheet of the closing shot's previz: twelve frames across the move, four across, each marked with
its film frame and time.

    python3 tools/promo/video/blender/contact.py [renders/promo/video/blender/previz] [out.png]
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[4]
src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "renders/promo/video/blender/previz"
dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src / "contact.png"
files = sorted(src.glob("frame_*.png"))
moving = [f for f in files if int(f.stem[6:]) <= 8880]      # the move rests by 148 s (frame 8880)
pick = [moving[round(i * (len(moving) - 1) / 10)] for i in range(11)] + [files[-1]]
w, h = 480, 270
sheet = Image.new("RGB", (4 * w + 5 * 8, 3 * h + 4 * 8 + 3 * 22), (24, 22, 20))
d = ImageDraw.Draw(sheet)
for k, f in enumerate(pick):
    im = Image.open(f).convert("RGB").resize((w, h), Image.LANCZOS)
    x, y = 8 + (k % 4) * (w + 8), 8 + (k // 4) * (h + 8 + 22)
    sheet.paste(im, (x, y))
    n = int(f.stem[6:])
    d.text((x, y + h + 5), f"frame {n}   {n / 60:.2f} s", fill=(220, 214, 200))
sheet.save(dst)
print(dst)
