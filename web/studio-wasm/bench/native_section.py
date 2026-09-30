"""Native reference: render a section (or the whole song) with numba, time it, and keep its PCM as .npy
for comparison with the browser's. usage: native_section.py SONG INDEX|whole OUT.npy"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np  # noqa: E402

import section as S  # noqa: E402

song, which, out = sys.argv[1], sys.argv[2], sys.argv[3]
g, params, score = S.score_of(song)
print("form", params.form)
for rep in ("cold", "warm"):
    t = time.perf_counter()
    pcm, info = S.whole(song) if which == "whole" else S.section(song, int(which))
    print(rep, info, f"{time.perf_counter() - t:.2f}s")
np.save(out, pcm)
