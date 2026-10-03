"""Block dynamics and stereo metering preserve the arithmetic they replace."""

import hashlib

import numpy as np
import pytest
from numba import njit

from songbird.synth import fx, master


def same(a, b):
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()


@njit(cache=True)
def _apply_per_sample(x, lin, step, band, y):
    n, chans = x.shape
    split = band.shape[1] == chans
    for i in range(n):
        k = i // step
        f = (i - k * step) / step
        g = lin[k] if k + 1 >= len(lin) else lin[k] + f * (lin[k + 1] - lin[k])
        for c in range(chans):
            y[i, c] = x[i, c] + band[i, c] * (g - 1.0) if split else x[i, c] * g
    return y


@njit(cache=True)
def _detect_per_sample(key, coef, step):
    n, chans = key.shape
    out = np.empty((n + step - 1) // step)
    p = 0.0
    for i in range(n):
        s = 0.0
        for c in range(chans):
            s += key[i, c] * key[i, c]
        p = coef * p + (1.0 - coef) * s / chans
        if i % step == 0:
            out[i // step] = p
    return out


@pytest.mark.parametrize("chans", [1, 2, 3])
@pytest.mark.parametrize("step", [1, 3, fx.STEP, 23])
def test_block_dynamics_match_per_sample_decisions(chans, step):
    rng = np.random.default_rng(chans + step)
    for n in (0, 1, step - 1, step, step + 1, 19 * step + 7):
        x = rng.normal(0, 0.3, (n, chans))
        x[::3] = 0.0
        lin = rng.uniform(0.1, 1.0, (n + step - 1) // step)
        assert same(fx._detect_every(x, 0.987, step), _detect_per_sample(x, 0.987, step))
        for band in (np.zeros((0, 0)), rng.normal(0, 0.01, x.shape)):
            want = _apply_per_sample(x, lin, step, band, np.empty_like(x))
            assert same(fx._apply(x, lin, step, band, np.empty_like(x)), want)
            mine = x.copy()
            assert same(fx._apply(mine, lin, step, band, mine), want)


@njit(cache=True)
def _weighted_with_array_state(x, p, q, hop):
    n, chans = x.shape
    out = np.zeros(n // hop)
    z1, z2, w1, w2 = np.zeros(chans), np.zeros(chans), np.zeros(chans), np.zeros(chans)
    for j in range(len(out)):
        s = 0.0
        for i in range(j * hop, (j + 1) * hop):
            for c in range(chans):
                v = x[i, c]
                o = p[0] * v + z1[c]
                z1[c] = p[1] * v - p[4] * o + z2[c]
                z2[c] = p[2] * v - p[5] * o
                u = q[0] * o + w1[c]
                w1[c] = q[1] * o - q[4] * u + w2[c]
                w2[c] = q[2] * o - q[5] * u
                s += u * u
        out[j] = s / hop
    return out


@pytest.mark.parametrize("chans", [1, 2, 3])
@pytest.mark.parametrize("hop", [1, 7, 103])
def test_stereo_meter_keeps_channel_and_sample_sum_order(chans, hop):
    rng = np.random.default_rng(chans + hop)
    p, q = [np.concatenate([b, a]) for b, a in master._k_weighting(44100)]
    for n in (0, hop - 1, hop, hop + 1, 17 * hop + 3):
        whole = rng.normal(0, 0.3, (n * 2, chans))
        for x in (whole[:n].copy(), whole[::2]):
            assert same(master._weighted_hop_power(x, p, q, hop), _weighted_with_array_state(x, p, q, hop))


@pytest.mark.parametrize("layout", ["C", "F", "stride", "endian", "empty"])
def test_pcm_hash_reads_the_same_bytes_without_a_bytes_copy(layout):
    pcm = np.arange(-101, 101, dtype="<i2").reshape(-1, 2)
    if layout == "F":
        pcm = np.asfortranarray(pcm)
    elif layout == "stride":
        pcm = pcm[::2, ::-1]
    elif layout == "endian":
        pcm = pcm.astype(">i2")
    elif layout == "empty":
        pcm = pcm[:0]
    assert master.pcm_sha256(pcm) == hashlib.sha256(np.ascontiguousarray(pcm, dtype="<i2").tobytes()).hexdigest()
