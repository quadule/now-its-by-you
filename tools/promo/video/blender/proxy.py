"""960x540 JPEG proxies (quality 90) of the closing shot's frames, for the live preview: each frame as soon as
render.log says it is written, until the render's process has gone, then a last pass over every frame.

    python3 tools/promo/video/blender/proxy.py RENDER_PID
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
B = ROOT / "renders/promo/video/blender"
FRAMES, PROXY, LOG = B / "frames", B / "proxy", B / "render.log"
PROXY.mkdir(parents=True, exist_ok=True)


def make(n):
    src, dst = FRAMES / f"frame_{n:06d}.png", PROXY / f"frame_{n:06d}.jpg"
    if dst.exists() or not src.exists():
        return
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-vf", "scale=960:540:flags=lanczos",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    tmp = dst.with_suffix(".part.jpg")
    Image.fromarray(np.frombuffer(raw, np.uint8).reshape(540, 960, 3)).save(tmp, quality=90)
    tmp.rename(dst)


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


pid = int(sys.argv[1])
while alive(pid):
    if LOG.exists():
        for n in map(int, re.findall(r"rendered frame (\d+)", LOG.read_text())):
            make(n)
    time.sleep(10)
for f in sorted(FRAMES.glob("frame_*.png")):
    make(int(f.stem[6:]))
print("proxies done", len(list(PROXY.glob("frame_*.jpg"))))
