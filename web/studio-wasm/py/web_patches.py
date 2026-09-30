"""What the browser needs changed in songbird, the same numbers either way. Installed by the loader after
songbird is imported; natively nothing imports this.

- master.true_peak_envelope reads windows of the signal through numpy's sliding_window_view, a virtual
  (len x 65) array of float64: over a whole song (6.7 M samples) that is 3.4 GB of address space, more
  than wasm32's 2 GB limit on an array (numpy refuses it: "array is too big"). The only thing done with
  the view is gathering rows by an index array, so a stand-in that gathers the same elements directly
  gives the same values with memory for the rows gathered only."""

from __future__ import annotations

import numpy as np


class _Windows:
    """sliding_window_view(x, width)[rows], without the view."""

    def __init__(self, x: np.ndarray, width: int):
        self.x, self.offsets = x, np.arange(width)

    def __getitem__(self, rows):
        rows = np.asarray(rows)
        return self.x[rows[:, None] + self.offsets[None, :]]


def _dgemm_linear(x: np.ndarray, w: dict, name: str) -> np.ndarray:
    """throat._linear (x @ W.T + b) by BLAS: Pyodide's numpy has none (its matmul is a plain loop, ~1 GFLOP/s,
    4x slower than scipy's OpenBLAS here). Summed in another order, as native numpy's BLAS also does."""
    from scipy.linalg import blas

    W, b = w[f"{name}.weight"], w[f"{name}.bias"]
    if x.dtype != np.float64 or W.dtype != np.float64 or x.ndim != 2 or len(x) < 64:
        return x @ W.T + b
    return blas.dgemm(1.0, x, W, trans_b=True) + b


def install(dgemm: bool = True) -> None:
    from songbird.synth import master, throat

    master.sliding_window_view = _Windows
    if dgemm:
        throat._linear = _dgemm_linear
