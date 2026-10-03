"""A preview can reuse its owned mix while retaining the same fading, ceiling and dither."""

import numpy as np
import pytest

from songbird.studio import PREVIEW_GAIN_DB, faded
from songbird.synth import master


@pytest.mark.parametrize("skip", [0.0, 0.25, 1.8])
def test_owned_preview_has_the_same_pcm(skip):
    sr = 44100
    rng = np.random.default_rng(14)
    t = np.arange(2 * sr + 77) / sr
    x = np.sin(2 * np.pi * 12_000.0 * t)[:, None] * [2.7, 2.2]
    x += rng.standard_normal(x.shape) * 0.08
    ceiling = master.CEILING_DB - master.MARGIN_DB
    gain = 10.0 ** (PREVIEW_GAIN_DB / 20.0)
    want = faded(master.limit(master.clip(x * gain, ceiling), sr, ceiling), sr, skip)
    mine = x.copy()
    mine *= gain
    loud = master.limit(master.clip(mine, ceiling, inplace=True), sr, ceiling, inplace=True)
    got = faded(loud, sr, skip, inplace=True)
    assert np.shares_memory(mine, got)
    assert got.tobytes() == want.tobytes()
    assert master.to_pcm16(got, seed=14).tobytes() == master.to_pcm16(want, seed=14).tobytes()


def test_fading_remains_a_copy_unless_the_mix_is_owned():
    x = np.ones((100_077, 2))
    was = x.copy()
    preview = faded(x, 44100, 0.25)
    assert not np.shares_memory(x, preview)
    assert np.array_equal(x, was)
    owned = faded(x, 44100, 0.25, inplace=True)
    assert np.shares_memory(x, owned)
    assert preview.tobytes() == owned.tobytes()
