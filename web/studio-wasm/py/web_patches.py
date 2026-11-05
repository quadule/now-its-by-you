"""What the browser needs changed in songbird, the same numbers either way. Installed by the loader after
songbird is imported; natively nothing imports this.

- throat._matmul by BLAS, including every convolution and residual layer: Pyodide's numpy has none.
- plain_docs(), before scipy is imported: scipy's docstrings left as they are, not parsed and rewritten.

(Until 2026-09-29 master.true_peak_envelope was patched too: it gathered rows from a sliding_window_view,
a virtual array over 2 GiB for a whole song, which numpy on wasm32 refuses. The memory work gathers them
with a kernel, master._windows, so the patch went.)"""

from __future__ import annotations

import numpy as np


def _dgemm_matmul(x: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """throat._matmul (x @ W.T) by BLAS: Pyodide's numpy has none (its matmul is a plain loop, ~1 GFLOP/s,
    4x slower than scipy's OpenBLAS here). Summed in another order, as native numpy's BLAS also does."""
    from scipy.linalg import blas

    if x.dtype != np.float64 or weight.dtype != np.float64 or x.ndim != 2 or weight.ndim != 2 or len(x) < 64:
        return x @ weight.T
    # (x W')' = W x': x and W are C-ordered, so x' and W' are Fortran-ordered as they lie, and the result's
    # transpose is C-ordered: no copy of x (a whole song's activations are ~100 MB each), none of the result
    return blas.dgemm(1.0, weight.T, x.T, trans_a=True).T


def plain_docs() -> None:
    """scipy rewrites about 800 of its docstrings as it is imported (each function's array-API note, axis and
    nan_policy parameters added to the stats tests' Parameters), parsing each with its numpydoc reader: half a second
    of a render worker's start in node (a quarter of importing the program, once its bytecode is kept). Nothing here
    reads them, so the reader (scipy._lib._docscrape's FunctionDoc and ClassDoc) is stood in for, before any of scipy's
    modules take it, by one that leaves each docstring as it was: what they add to its sections is dropped. Only
    docstrings change.
    Call before anything imports scipy beyond its own package (scipy.signal, scipy.stats, scipy.ndimage...)."""
    from collections import defaultdict

    from scipy._lib import _docscrape

    class Unread:
        def __init__(self, obj=None, *args, **kwargs):
            self._doc = getattr(obj, "__doc__", None) or ""
            self._sections = defaultdict(list)

        def __getitem__(self, key):
            return self._sections[key]

        def __setitem__(self, key, value):
            self._sections[key] = value

        def __str__(self):  # a signature's line (which they drop), then the docstring
            return "\n" + self._doc

    _docscrape.FunctionDoc = _docscrape.ClassDoc = Unread


def install(dgemm: bool = True) -> None:
    from songbird.synth import throat

    if dgemm:
        throat._matmul = _dgemm_matmul
