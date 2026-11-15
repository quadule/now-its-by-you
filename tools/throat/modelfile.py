"""A throat model's arrays from its .npz, with numpy alone, for the tools that run in torch's environment (dev only).

The same reading as songbird.synth.throat.arrays, which the program uses: the shipped file keeps each float32 array
as its bytes in four planes and names them in its "planes" entry; a file as train.py writes it reads as it is.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def arrays(path: str | Path) -> dict[str, np.ndarray]:
    with np.load(path) as z:
        planed = {str(k) for k in z["planes"]} if "planes" in z.files else set()
        out = {}
        for k in z.files:
            if k == "planes":
                continue
            a = z[k]
            if k in planed:  # (4, *shape) bytes -> (*shape,) little-endian float32
                a = np.ascontiguousarray(np.moveaxis(a, 0, -1)).view("<f4").reshape(a.shape[1:])
            out[k] = a
    return out
