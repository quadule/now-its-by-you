"""Two renders of the same thing, sample by sample: how many 16-bit samples differ, by how much, and where.

usage: uv run python web/studio-wasm/tools/pcm_diff.py A.flac B.flac"""

import sys

import numpy as np
import soundfile as sf


def main():
    a, sr = sf.read(sys.argv[1], dtype="int16", always_2d=True)
    b, _ = sf.read(sys.argv[2], dtype="int16", always_2d=True)
    print(f"lengths {len(a)} {len(b)}")
    n = min(len(a), len(b))
    d = a[:n].astype(np.int32) - b[:n].astype(np.int32)
    where = np.nonzero(np.any(d != 0, axis=1))[0]
    print(f"samples differing: {len(where)} of {n} ({len(where) / max(n, 1):.2e}); largest {np.abs(d).max()} LSB")
    if len(where):
        print(f"first at {where[0] / sr:.3f} s, last at {where[-1] / sr:.3f} s")
        hist = np.bincount(np.abs(d[d != 0]))
        print("by size (LSB: count):", {k: int(v) for k, v in enumerate(hist) if v})


if __name__ == "__main__":
    main()
