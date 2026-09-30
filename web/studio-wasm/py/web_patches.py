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


def install() -> None:
    from songbird.synth import master

    master.sliding_window_view = _Windows
