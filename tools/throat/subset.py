"""Part of a throat training set: the segments whose names start with a prefix, and only the singers they sing
(dev only).

    uv run python tools/throat/subset.py renders/throat/dataset-blendA.npz renders/throat-scylla/dataset-house.npz house-

The shipped voice's own dataset (dataset-house-volunteers.npz) is gone with the volunteers' recordings, but its
house corpus lives on inside October's blend A as the house-* segments. This cuts them back out, so the house corpus
can be merged with another (`folk.py merge --house`, which keeps the shipped model's volunteers row by name).
"""

from __future__ import annotations

import sys

import numpy as np

PER_SEGMENT = ("singers", "sources", "phones", "segments", "offsets", "lengths")


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    src, dst, prefix = sys.argv[1:]
    z = np.load(src)
    keep = [i for i, s in enumerate(z["segments"]) if str(s).startswith(prefix)]
    if not keep:
        raise SystemExit(f"no segment in {src} starts with {prefix}")
    frames = np.concatenate([np.arange(z["offsets"][i], z["offsets"][i] + z["lengths"][i]) for i in keep])
    out = {k: z[k][frames] for k in z.files if k not in PER_SEGMENT}
    used = np.unique(out["singer"])  # only the singers sung here stay in the list
    remap = np.full(len(z["singers"]), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    out["singer"] = remap[out["singer"].astype(np.int64)].astype(z["singer"].dtype)
    lengths = z["lengths"][keep]
    out.update(singers=z["singers"][used], sources=z["sources"][used], phones=z["phones"],
               segments=z["segments"][keep], offsets=np.concatenate([[0], np.cumsum(lengths)[:-1]]).astype(np.int64),
               lengths=lengths)
    np.savez(dst, **out)
    print(f"{dst}: {len(keep)} segments, {len(frames)} frames ({len(frames) * 0.005 / 60:.1f} min), "
          f"singers {[str(s) for s in out['singers']]}")


if __name__ == "__main__":
    main()
