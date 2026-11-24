"""Frame-to-frame flicker in a run of consecutive frames: for each inner frame, how far it departs from the mean
of its two neighbours (smooth motion cancels; noise crawl, denoiser flicker and shimmer do not), and the plain
difference from the previous frame. In 16-bit units of full scale x 1000, over the whole frame and in bands.

    python3 tools/promo/video/blender/flicker.py renders/promo/video/blender/scratch/run_hold [--low]

--low measures on 16 x 16 block means, where smooth camera motion nearly cancels and blotchy flicker remains.
"""

import subprocess
import sys
from pathlib import Path

import numpy as np


def load(p):
    w, h = 1920, 1080
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "rawvideo", "-pix_fmt", "rgb48le", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint16).reshape(h, -1, 3).astype(np.float32) / 65535
    a = a.mean(2)
    if LOW:                                   # 16 x 16 block means: the denoiser's blotches, not fine detail in motion
        a = a[: a.shape[0] // 16 * 16, : a.shape[1] // 16 * 16]
        a = a.reshape(a.shape[0] // 16, 16, a.shape[1] // 16, 16).mean((1, 3))
    return a


LOW = "--low" in sys.argv
d = Path(sys.argv[1])
fs = sorted(d.glob("frame_*.png"))
ims = [load(f) for f in fs]
H = ims[0].shape[0]
bands = {"all": slice(0, H), "top (lawn, trees)": slice(0, H // 4), "middle (packets, rough, kerb)": slice(H // 4, 3 * H // 4),
         "bottom (shaded paving)": slice(3 * H // 4, H)}
for name, sl in bands.items():
    sec = [np.abs(ims[i][sl] - 0.5 * (ims[i - 1][sl] + ims[i + 1][sl])).mean() for i in range(1, len(ims) - 1)]
    p99 = [np.percentile(np.abs(ims[i][sl] - 0.5 * (ims[i - 1][sl] + ims[i + 1][sl])), 99.5) for i in range(1, len(ims) - 1)]
    first = [np.abs(ims[i][sl] - ims[i - 1][sl]).mean() for i in range(1, len(ims))]
    print(f"{d.name:10s} {name:30s} second-diff mean {1000 * np.mean(sec):.3f}  p99.5 {1000 * np.mean(p99):.2f}  "
          f"first-diff mean {1000 * np.mean(first):.3f}")
