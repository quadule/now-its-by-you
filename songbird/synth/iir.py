"""Butterworth filters, designed once each.

scipy.signal.butter takes a few hundred microseconds a design, and the instruments ask for the same few
designs again and again (a pluck's attack and touch, a drum's slap and knock, a consonant's noise band:
over 3,000 designs in one song, a second of its render). butter() here is scipy's, with the same
arguments and the same result, remembered by its arguments; each call gets its own copy, so a caller may
change what it is given.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.signal import butter as _scipy_butter


@lru_cache(maxsize=2048)
def _designed(N, key: tuple, btype: str, analog, output: str, fs):
    shape, dtype, values = key
    Wn = np.array(values, dtype=dtype).reshape(shape)
    return _scipy_butter(N, Wn if shape else Wn[()], btype=btype, analog=analog, output=output, fs=fs)


def butter(N, Wn, btype="low", analog=False, output="ba", fs=None):
    """scipy.signal.butter, remembered: the same arguments give the same design, a fresh copy of it."""
    w = np.asarray(Wn)
    if w.dtype.kind not in "iuf" or w.ndim > 1:  # nothing to remember it by: scipy as it is
        return _scipy_butter(N, Wn, btype=btype, analog=analog, output=output, fs=fs)
    key = (w.shape, w.dtype.str, tuple(w.ravel().tolist()))
    made = _designed(N, key, btype, analog, output, fs)
    return tuple(np.array(x) for x in made) if isinstance(made, tuple) else np.array(made)
