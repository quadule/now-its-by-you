"""What the browser needs changed in songbird, the same numbers either way. Installed by the loader after
songbird is imported; natively nothing imports this.

- throat._matmul by BLAS, including every convolution and residual layer: Pyodide's numpy has none. Where wasm
  SIMD is supported, by the C kernel that sums as that BLAS does, twice as fast (wasm/kernels.c matmul_blas).
- plain_docs(), before scipy is imported: scipy's docstrings left as they are, not parsed and rewritten.

(master.true_peak_envelope needs no patch: it gathers its rows with a kernel, master._windows, not from a
sliding_window_view, a virtual array over 2 GiB for a whole song, which numpy on wasm32 refuses.)"""

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


def _kernel():
    """The SIMD build's matmul_blas (wasm/kernels.mjs fetched kernels-simd.wasm), or None: no wasm kernels, or
    the build without SIMD."""
    try:
        import songbird_wasm
    except ImportError:
        return None
    return getattr(songbird_wasm, "matmul_blas", None)


def _address(a: np.ndarray) -> int:
    return a.__array_interface__["data"][0]


def _simd_product(kernel, x: np.ndarray, weight: np.ndarray) -> np.ndarray:
    x = np.ascontiguousarray(x)
    wt = np.ascontiguousarray(weight.T)  # 600 KB for the convolutions' weights
    out = np.empty((len(x), len(weight)))
    kernel(_address(x), len(x), x.shape[1], _address(wt), len(weight), _address(out))
    return out


_AGREES: dict[tuple[int, int], bool] = {}


def _agrees(kernel, k: int, m: int) -> bool:
    """Whether the kernel gives dgemm's own bits for this k and m (once each): it bakes in how this Pyodide's
    OpenBLAS blocks its sums, so a Pyodide with another would be caught here and keep to dgemm. Inputs of every
    magnitude, with zero rows, where any other order of the sums shows; its own generator, so the program's
    random numbers are untouched."""
    if (k, m) not in _AGREES:
        rng = np.random.default_rng([k, m])
        x = rng.standard_normal((67, k)) * np.exp2(rng.integers(-30, 30, (67, k)))
        w = rng.standard_normal((m, k)) * np.exp2(rng.integers(-30, 30, (m, k)))
        x[::7] = 0.0
        want = _dgemm_matmul(x, w)
        got = _simd_product(kernel, x, w)
        _AGREES[k, m] = bool(np.array_equal(want.view(np.int64), got.view(np.int64)))
    return _AGREES[k, m]


def _simd_matmul(x: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """throat._matmul by wasm/kernels.c's matmul_blas: dgemm's numbers bit for bit (each output summed in its
    order, f64x2 lanes two outputs at a time), about twice its speed. Whatever dgemm wouldn't take goes where
    _dgemm_matmul sends it."""
    if (x.dtype != np.float64 or weight.dtype != np.float64 or x.ndim != 2 or weight.ndim != 2 or len(x) < 64
            or x.shape[1] != weight.shape[1] or weight.shape[1] == 0):  # (k 0: the kernel writes nothing)
        return _dgemm_matmul(x, weight)
    kernel = _kernel()
    if not _agrees(kernel, weight.shape[1], weight.shape[0]):
        return _dgemm_matmul(x, weight)
    return _simd_product(kernel, x, weight)


def matmul() -> str:
    """Which product throat._matmul is: "simd", "dgemm" or "numpy" (as installed)."""
    from songbird.synth import throat

    return {_simd_matmul: "simd", _dgemm_matmul: "dgemm"}.get(throat._matmul, "numpy")
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


def _true_peak_envelope(x: np.ndarray, floor: float = 0.0) -> np.ndarray:
    """master.true_peak_envelope with the window gather + 4-tap matmul fused in wasm (master_true_peak_swing):
    no 34 MB window matrix and no Pyodide un-BLASed matmul loop, bit-identical to numpy's left-to-right sum."""
    import songbird_wasm as W
    from songbird.synth import fx, master

    y = np.ascontiguousarray(x.reshape(len(x), -1), dtype=np.float64)
    env = master._abs_max(y) if fx.JIT else np.abs(y).max(axis=1)
    near = env >= floor
    near[:-1] |= near[1:]
    near[-1] = False
    loud = np.flatnonzero(near)
    if not len(loud):
        return env
    taps_t = np.ascontiguousarray(master._interpolator().T, dtype=np.float64)
    pts = np.ascontiguousarray(loud, dtype=np.int32)
    between = np.zeros(len(pts), dtype=np.float64)
    W.master_true_peak_swing(_address(y), y.shape[0], y.shape[1], _address(pts), len(pts),
                             master.REACH, _address(taps_t), _address(between))
    env[loud] = np.maximum(env[loud], between)
    env[loud + 1] = np.maximum(env[loud + 1], between)
    return env


def install(dgemm: bool = True) -> None:
    from songbird.synth import master, throat

    if dgemm:
        throat._matmul = _simd_matmul if _kernel() is not None else _dgemm_matmul
    try:
        import songbird_wasm
    except ImportError:
        return
    if hasattr(songbird_wasm, "master_true_peak_swing"):
        master.true_peak_envelope = _true_peak_envelope
