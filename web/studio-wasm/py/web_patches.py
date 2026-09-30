"""What the browser needs changed in songbird, the same numbers either way. Installed by the loader after
songbird is imported; natively nothing imports this.

- throat._linear by BLAS: Pyodide's numpy has none.

(Until 2026-09-29 master.true_peak_envelope was patched too: it gathered rows from a sliding_window_view,
a virtual array over 2 GiB for a whole song, which numpy on wasm32 refuses. The memory work gathers them
with a kernel, master._windows, so the patch went.)"""

from __future__ import annotations

import numpy as np


def _dgemm_linear(x: np.ndarray, w: dict, name: str) -> np.ndarray:
    """throat._linear (x @ W.T + b) by BLAS: Pyodide's numpy has none (its matmul is a plain loop, ~1 GFLOP/s,
    4x slower than scipy's OpenBLAS here). Summed in another order, as native numpy's BLAS also does."""
    from scipy.linalg import blas

    W, b = w[f"{name}.weight"], w[f"{name}.bias"]
    if x.dtype != np.float64 or W.dtype != np.float64 or x.ndim != 2 or len(x) < 64:
        return x @ W.T + b
    # (x W')' = W x': x and W are C-ordered, so x' and W' are Fortran-ordered as they lie, and the result's
    # transpose is C-ordered: no copy of x (a whole song's activations are ~100 MB each), none of the result
    y = blas.dgemm(1.0, W.T, x.T, trans_a=True).T
    y += b
    return y


def install(dgemm: bool = True) -> None:
    from songbird.synth import throat

    if dgemm:
        throat._linear = _dgemm_linear
