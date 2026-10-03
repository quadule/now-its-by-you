"""Instrument work saved without changing a sample: shared FFTs, bounded temporaries and owned buffers."""

import hashlib

import numpy as np
import pytest

from songbird.score import Note
from songbird.synth import body, bowed, epiano, oa, organ, osc, pipe


def same(a, b):
    return a.shape == b.shape and a.dtype == b.dtype and np.ascontiguousarray(a).tobytes() == \
        np.ascontiguousarray(b).tobytes()


@pytest.mark.parametrize("n,m,channels", [(5000, 3, 2), (100_000, 2048, 2), (400_000, 11025, 3),
                                         (1_500_000, 26460, 2), (300_000, 70000, 2), (40_000, 30000, 2),
                                         (4096, 4096, 2), (20_001, 31, 1)])
def test_shared_input_ffts_are_each_microphones_separate_convolution(n, m, channels):
    rng = np.random.default_rng(n + m)
    # Strided inputs and response columns, as an instrument's force and microphones may be laid out.
    x = rng.standard_normal(n * 2)[::2]
    h = rng.standard_normal((m, channels + 1))[:, :channels]
    for take in (None, n, n // 3 + 17, 0):
        want = np.stack([oa.convolve(x, h[:, ch], take) for ch in range(channels)], axis=1)
        assert same(oa.convolve_shared(x, h, take), want)


@pytest.mark.parametrize("dtype", [np.float64, np.float32, np.int16])
def test_empty_bridge_force_keeps_an_empty_stereo_stem(dtype):
    x, h = np.empty(0, dtype=dtype), np.ones((31, 2), dtype=dtype)
    assert same(body.resonate(x, h), np.empty((0, 2)))
    assert same(oa.convolve_shared(x, h), np.empty((0, 2)))
    assert same(oa.convolve_shared(np.ones(31), np.empty((0, 2))), np.empty((0, 2)))


def test_bounded_amplifiers_keep_the_whole_expressions_and_only_change_owned_inputs():
    rng = np.random.default_rng(17)
    for n in (0, 1, 31, 65_537, 200_003):
        x = rng.standard_normal(n) * 20.0
        if n > 1:
            x[:2] = [0.0, -0.0]
        for ceiling in (2.2, 2.5):
            want = ceiling * np.tanh(x / ceiling)
            before = x.copy()
            assert same(epiano._soft_clip(x, ceiling), want) and same(x, before)
            mine = x.copy()
            assert epiano._soft_clip(mine, ceiling, inplace=True) is mine and same(mine, want)
        for drive in (0.0, 0.3, 1.0):
            k, b = organ.TUBE_GAIN * (0.6 + 0.8 * drive), 0.12
            clipped = np.clip(k * x + b, -1.0, 1.0)
            p = clipped * (1.5 - 0.5 * clipped * clipped)
            want = (p - b * (1.5 - 0.5 * b * b)) / (k * 1.5 * (1.0 - b * b))
            before = x.copy()
            assert same(organ.tubes(x, drive), want) and same(x, before)
            mine = x.copy()
            assert organ.tubes(mine, drive, inplace=True) is mine and same(mine, want)


@pytest.mark.parametrize("n", [0, 1, 31, 65_537, 200_003])
def test_oscillators_wander_is_the_same_smooth_interpolation(n):
    sr, cents, rate = 44100, 6.0, 0.3
    points = max(4, int(n / sr * rate * 2.0) + 4)
    old_rng, rng = np.random.default_rng(18), np.random.default_rng(18)
    if n > 0:
        knots = old_rng.standard_normal(points) * cents
        t = np.linspace(0.0, points - 1.0, n)
        i = np.minimum(t.astype(np.int64), points - 2)
        f = t - i
        s = f * f * (3.0 - 2.0 * f)
        want = knots[i] * (1.0 - s) + knots[i + 1] * s
    else:
        want = np.zeros(0)
    assert same(osc.drift(n, sr, rng, cents, rate), want)
    assert rng.random() == old_rng.random()


@pytest.mark.parametrize("n", [1, 31, 65_537, 200_003])
def test_bellows_pressure_keeps_the_whole_tracks_average(n):
    harmonium = organ.Harmonium(44100, np.random.default_rng(19), {})
    rng, old_rng = np.random.default_rng(20), np.random.default_rng(20)
    t = np.arange(n) / harmonium.sr
    phase = (t / harmonium.pump + old_rng.uniform(0.0, 1.0)) % 1.0
    stroke = np.where(phase < 0.25, np.sin(np.pi * phase / 0.5), np.exp(-(phase - 0.25) * 2.2))
    assert same(harmonium.pressure(n, rng), 1.0 + 0.05 * (stroke - np.mean(stroke)))
    assert rng.random() == old_rng.random()


def _notes():
    arts = ["", "slur", "swell", "slide", "", "cut", "tap", "jazz", "gospel", "fast", "chime", "slow",
            "full", "soft", "ballad", ""]
    return tuple(Note("x", 0.1 + i * 0.37, 0.6 if i % 3 else 0.2, 48.0 + (i * 5) % 29,
                      0.3 + (i % 5) * 0.15, art=art) for i, art in enumerate(arts))


# Captured before these optimizations: overlapping notes, rests, expressive changes, and a partial last block.
MADE = {
    "fiddle": "73c42b20822ed32786eabbb419e054ea94e93fbf143d59072833cb1433c48fa0",
    "whistle": "12eb8f32c94b2ce87f57a572ecf145407922f97cfdfc5205f47a6a4d513eca64",
    "epiano": "720f7c728107b3a8b1361730f8e04f168dd64fbabf3b0f2d01897edd37cd24a6",
    "epiano-reed": "894488b7edb4d03f8366a2c025dc30fa9ea8821b32a6d1d11e5d8415639ed505",
    "organ": "0fc850afd44191f57817d0efe1e33c740b71b9a91933a84bfeba018d2a443f60",
    "harmonium": "582c0000a7d6539eaff89ae1fd7b6f5206b41e3b3999d02e9140611068fb746d",
}


@pytest.mark.parametrize("name", list(MADE))
def test_optimized_instruments_make_the_samples_they_made(name):
    notes, sr, length = _notes(), 44100, 8 * 44100 + 37
    rng, make = np.random.default_rng(1701), np.random.default_rng(2901)
    if name == "fiddle":
        y = bowed.bow(notes, sr, length, rng, vibrato=17, wear=0.4, noise=0.7)
    elif name == "whistle":
        y = pipe.blow(notes, sr, length, rng, brightness=0.6, wear=0.4, breathiness=1.1, vibrato=0.7)
    else:
        module = epiano if name.startswith("epiano") else organ
        y = module.render(name, notes, sr, length, rng, make,
                          dict(brightness=0.6, wear=0.4, ornament=0.7, body=1.1))
    assert hashlib.sha256(np.ascontiguousarray(y).tobytes()).hexdigest() == MADE[name]
