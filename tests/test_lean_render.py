"""A render that holds less memory makes the same samples: each lean way of working against the way it replaced
(docs/PERFORMANCE.md, 2026-09-29). The goldens (h-seed, b-refrain) hold the whole; these hold each piece."""

import numpy as np
import pytest
from numba import njit
from scipy.signal import oaconvolve

from songbird.synth import fx, instruments, mixing, oa, pluck

SR = 44100


def same(a, b) -> bool:
    a, b = np.ascontiguousarray(a), np.ascontiguousarray(b)
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()


@pytest.mark.parametrize("s1,s2", [(5000, 3), (100_000, 2048), (400_000, 11025), (1_500_000, 26460), (300_000, 70000),
                                   (40_000, 30_000), (4096, 4096)])
def test_blockwise_convolution_is_oaconvolves(s1, s2):
    rng = np.random.default_rng(s1 + s2)
    x = rng.standard_normal(s1)
    h = (rng.standard_normal((s2, 2)) * np.exp(-np.arange(s2) / (s2 / 4 + 1))[:, None])[:, 1]  # a column, as bodies give
    whole = oaconvolve(x, h)
    for n in (None, s1, s1 // 3 + 17):
        assert same(oa.convolve(x, h, n), whole[: len(whole) if n is None else n])
    out = np.zeros((s1, 2))
    oa.convolve(x, h, s1, out=out[:, 1])
    assert same(out[:, 1], whole[:s1]) and not out[:, 0].any()


@njit(cache=True)
def _bank_whole(x, wholes, taps, gains, coupling):
    """pluck._bank as it was: every string's whole history kept."""
    n_strings, n_taps = taps.shape
    length = x.shape[0]
    pad = 0
    for s in range(n_strings):
        pad = max(pad, wholes[s] + n_taps)
    lines = np.zeros((n_strings, pad + length))
    out = np.zeros(length)
    for n in range(length):
        drive = coupling * x[n]
        total = 0.0
        for s in range(n_strings):
            base = pad + n - wholes[s]
            fb = 0.0
            for k in range(n_taps):
                fb += taps[s, k] * lines[s, base - k]
            v = drive + gains[s] * fb
            lines[s, pad + n] = v
            total += v
        out[n] = total
    return out


def test_open_strings_ring_as_with_their_whole_history():
    rng = np.random.default_rng(2)
    force = rng.standard_normal(200_000) * np.exp(-np.arange(200_000) / 5e4)
    for pitches in ([43, 48, 55, 60, 64, 67, 72, 79], [40, 45, 50, 55, 59, 64], [28], [81, 93]):
        wholes, rows, gains = [], [], []
        for p in pitches:
            freq = 440.0 * 2.0 ** ((p - 69.0) / 12.0)
            whole, taps = pluck._cached_loop(round(SR / freq, 6), round(0.395, 4))
            wholes.append(whole)
            rows.append(taps)
            gains.append(0.9999)
        args = (force, np.array(wholes, dtype=np.int64), np.array(rows), np.array(gains), 0.0015)
        assert same(pluck._bank(*args), _bank_whole(*args))


def _place_as_it_was(y, position, width):
    theta = (position + 1.0) * np.pi / 4.0
    if y.ndim == 1:
        return np.stack([y * np.cos(theta), y * np.sin(theta)], axis=1) * np.sqrt(2.0)
    mid = 0.5 * (y[:, 0] + y[:, 1])
    side = 0.5 * (y[:, 0] - y[:, 1]) * width
    return np.stack([mid * np.cos(theta) * np.sqrt(2.0) + side, mid * np.sin(theta) * np.sqrt(2.0) - side], axis=1)


def test_placing_is_as_it_was():
    rng = np.random.default_rng(3)
    for position, width in [(-0.35, 0.8), (0.3, 0.6), (0.0, 1.0), (1.0, 0.0), (-1.0, 0.3)]:
        for y in (rng.standard_normal(10_001), rng.standard_normal((10_001, 2)), rng.standard_normal((10_001, 3))[:, :2],
                  rng.standard_normal((5000, 2))[::2]):
            want = _place_as_it_was(y, position, width)
            assert same(instruments.place(y, position, width), want)
            if y.ndim == 2 and y.flags.c_contiguous and y.shape[1] == 2:
                mine = y.copy()
                assert same(instruments.place(mine, position, width, inplace=True), want) and same(mine, want)


def test_treating_in_place_is_the_same():
    rng = np.random.default_rng(4)
    n = 2 * SR + 77
    t = np.arange(n) / SR
    x = (rng.standard_normal((n, 2)) * 0.1 + np.sin(2 * np.pi * 220 * t)[:, None] * [0.5, 0.3]) * np.sin(3 * t)[:, None] ** 2
    sos = fx.design((("hp", 80), ("peak", 900, -2.0, 1.2), ("high", 9000, 1.0), ("lp", 12000)), SR)
    for sig in (x, x[:, :1].copy(), x[:, 0].copy()):
        mine = sig.copy()
        assert same(fx.equalize(mine, sos, inplace=True), fx.equalize(sig, sos)) and same(mine, fx.equalize(sig, sos))
    for kw in ({}, {"ride": 2.0, "above": 3.0}):
        mine = x.copy()
        a, ga = fx.compress(mine, SR, -20.0, 2.0, 0.01, 0.2, inplace=True, **kw)
        b, gb = fx.compress(x, SR, -20.0, 2.0, 0.01, 0.2, **kw)
        assert same(a, b) and same(ga, gb) and same(mine, b)
    depth = 6.0 * np.sin(3 * t) ** 2
    mine = x.copy()
    assert same(fx.dynamic_dip(mine, SR, 2600.0, 0.7, depth, inplace=True), fx.dynamic_dip(x, SR, 2600.0, 0.7, depth))
    g = rng.uniform(-6, 0, n // fx.STEP + 1)
    mine = x.copy()
    assert same(fx.apply_gain(mine, g, inplace=True), fx.apply_gain(x, g))


def test_a_mix_of_stems_made_as_it_goes_is_the_mix_of_them_all(monkeypatch):
    from tests.test_mix import panned, pluck_track

    rng = np.random.default_rng(5)
    n = int(4.0 * SR)
    t = np.arange(n) / SR
    buzz = sum(np.sin(2 * np.pi * 220 * k * t) / k for k in range(1, 20))
    syllables = (np.sin(2 * np.pi * 2.0 * t) > -0.2) * (t < 3.0)
    stems = {
        "voice": panned(0.1 * buzz * syllables + 0.01 * rng.standard_normal(n) * syllables, 0.0),
        "guitar": panned(pluck_track(4.0, 196.0, 0.25, rng), -0.2),
        "bass": panned(pluck_track(4.0, 82.0, 0.5, rng), 0.05),
        "choir1": panned(0.05 * buzz * (t > 2.0), -0.45),
        "shaker": np.stack([rng.standard_normal(n), rng.standard_normal(n)], axis=1) * 0.01,
    }
    stems["choir2"] = stems["choir1"][::-1].copy()
    stems["lute"] = stems["guitar"][:, ::-1].copy()  # a lute steps back under the voice
    length = len(stems["voice"])
    for threads in ("1", "3"):
        monkeypatch.setenv("SONGBIRD_THREADS", threads)
        taps_a, taps_b = {}, {}
        a = mixing.mix(stems, SR, seed=4, taps=taps_a)
        told = []
        b = mixing.mix_made([(k, lambda v=v: v.copy()) for k, v in stems.items()], length, SR, seed=4, taps=taps_b,
                            progress=told.append)
        assert same(a, b)
        assert told == ["voice", "choir1", "choir2", "bass", "guitar", "lute", "shaker", "mix"]
        for key in ("voice", "choir", "band", "wet", "glue", "singing"):
            assert same(taps_a[key], taps_b[key])
