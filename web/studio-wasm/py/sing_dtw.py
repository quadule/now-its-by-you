"""librosa.sequence.dtw as tools/phrasing.py align_by_pitch calls it, in numpy alone (librosa needs numba, which
Pyodide hasn't): a cost matrix given, subsequence matching, steps that each advance the row by one or more, and
their weights. The same accumulated costs and the same warping path, bit for bit (tests/test_sing_dtw.py checks
it against librosa on real and random costs); docs/WEB-SINGING.md, "On the device".

What librosa does, kept exactly:
- Its default steps (1,1), (0,1), (1,0) go before the steps given, with infinite weights: an infinite cost (or a
  NaN, for a zero cost times infinity) never compares less, so they never win and only shift the indices.
- Each cell takes the first of the steps, in order, whose cost (D[n - dn, m - dm] + (w_mul * C[n, m] + w_add)) is
  strictly less than the best so far, starting from infinity (the first row, in subsequence matching, from C).
  Every step advancing the row, a row depends on the rows before it alone, so it is computed a row at a time.
- The path ends at the first least cost of the last row and runs back until it reaches the first row.
- Where C has more rows than columns the path's two columns come back swapped (librosa flips them whenever it
  thinks it transposed C, and that test counts C's shape even when C was given).
"""

from __future__ import annotations

import numpy as np

DEFAULT_STEPS = np.array([[1, 1], [0, 1], [1, 0]])


class ParameterError(Exception):
    """librosa.util.exceptions.ParameterError's stand-in."""


def dtw(X=None, Y=None, *, C=None, metric="euclidean", step_sizes_sigma=None, weights_add=None, weights_mul=None,
        subseq=False, backtrack=True, global_constraints=False, band_rad=0.25, return_steps=False):
    if X is not None or Y is not None or C is None:
        raise NotImplementedError("only a cost matrix given (C=...), as tools/phrasing.py calls it")
    if not subseq or not backtrack or global_constraints or return_steps or step_sizes_sigma is None:
        raise NotImplementedError("only subsequence matching with steps of its own, as tools/phrasing.py calls it")
    given = np.asarray(step_sizes_sigma)
    if np.any(given < 0):
        raise ParameterError("step_sizes_sigma cannot contain negative values")
    if np.any(given[:, 0] < 1):
        raise NotImplementedError("only steps that advance the row")
    w_add = np.zeros(len(given)) if weights_add is None else np.asarray(weights_add, dtype=np.float64)
    w_mul = np.ones(len(given)) if weights_mul is None else np.asarray(weights_mul, dtype=np.float64)
    if len(given) != len(w_add):
        raise ParameterError("len(weights_add) must be equal to len(step_sizes_sigma)")
    if len(given) != len(w_mul):
        raise ParameterError("len(weights_mul) must be equal to len(step_sizes_sigma)")
    C = np.atleast_2d(C)
    if np.any(np.isnan(C)):
        raise ParameterError("DTW cost matrix C has NaN values. ")

    steps = np.concatenate((DEFAULT_STEPS, given))
    max_0, max_1 = int(steps[:, 0].max()), int(steps[:, 1].max())
    N, M = C.shape
    D = np.full((N + max_0, M + max_1), np.inf)
    D[max_0, max_1:] = C[0, :]
    chosen = np.zeros((N, M), dtype=np.int8)  # librosa's step matrix: an index into steps, 0 where never set
    for n in range(1, N):
        best = np.full(M, np.inf)
        which = np.zeros(M, dtype=np.int8)
        for i, (dn, dm) in enumerate(given):
            cost = w_mul[i] * C[n]
            cost += w_add[i]
            total = D[max_0 + n - dn, max_1 - dm : max_1 - dm + M] + cost
            better = total < best
            best = np.where(better, total, best)
            which = np.where(better, np.int8(len(DEFAULT_STEPS) + i), which)
        D[max_0 + n, max_1:] = best
        chosen[n] = which
    D = D[max_0:, max_1:]

    if np.all(np.isinf(D[-1])):
        raise ParameterError("No valid sub-sequence warping path could be constructed with the given step sizes.")
    n, m = N - 1, int(np.argmin(D[-1, :]))
    wp = [(n, m)]
    while n > 0:
        dn, dm = steps[chosen[n, m]]
        n, m = n - int(dn), m - int(dm)
        if min(n, m) < 0:
            break
        wp.append((n, m))
    path = np.asarray(wp, dtype=int)
    if C.shape[0] > C.shape[1]:
        path = np.fliplr(path)
    return D, path


class _Namespace:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def librosa_module():
    """A module standing in for librosa where only sequence.dtw (and its ParameterError) is reached for."""
    import types

    module = types.ModuleType("librosa")
    module.__doc__ = "librosa's stand-in in the browser: sequence.dtw alone (web/studio-wasm/py/sing_dtw.py)"
    module.sequence = _Namespace(dtw=dtw)
    module.util = _Namespace(exceptions=_Namespace(ParameterError=ParameterError))
    module.ParameterError = ParameterError
    return module
