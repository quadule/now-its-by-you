import numpy as np
import pytest

from songbird.synth import master

SR = 48000


def test_bs1770_calibration():
    # BS.1770: a 0 dBFS 997 Hz sine in one channel reads -3.01 LKFS
    t = np.arange(10 * SR) / SR
    x = np.zeros((len(t), 2))
    x[:, 0] = np.sin(2 * np.pi * 997 * t)
    assert abs(master.loudness(x, SR) - (-3.01)) < 0.05


def test_limiter_respects_ceiling():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.5, (SR, 2))
    x[SR // 2] = 3.0
    y = master.limit(x, SR, ceiling_db=-1.0)
    assert np.abs(y).max() <= 10 ** (-1 / 20) + 1e-12


def test_master_hits_target():
    rng = np.random.default_rng(2)
    t = np.arange(8 * SR) / SR
    x = np.stack([np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t)], axis=1) * 0.05
    x += rng.normal(0, 0.01, x.shape)
    y = master.master(x, SR)
    assert abs(master.loudness(y, SR) - master.TARGET_LUFS) < 0.2


def test_true_peak_sees_between_samples():
    # a quarter-rate sine at 45 degrees: every sample at 0.707, the wave itself at 1.0
    t = np.arange(SR)
    x = np.sin(2 * np.pi * t / 4 + np.pi / 4)[:, None].repeat(2, axis=1)
    assert 20 * np.log10(np.abs(x[1000:-1000]).max()) == pytest.approx(-3.01, abs=0.01)
    assert master.true_peak(x[1000:-1000]) == pytest.approx(0.0, abs=0.1)


def test_master_keeps_true_peak_under_ceiling_after_dither():
    # hot and bright: plucks and noise that swing past full scale between samples
    rng = np.random.default_rng(6)
    t = np.arange(6 * SR) / SR
    x = 0.3 * np.sin(2 * np.pi * 11000 * t + 0.7)[:, None] * (np.sin(2 * np.pi * 1.5 * t) > 0.7)[:, None]
    x = x + rng.normal(0, 0.05, (len(t), 2))
    x[::SR // 3] += 0.9
    pcm = master.to_pcm16(master.master(x, SR), seed=1)
    y = pcm / 32768.0
    assert master.true_peak(y) <= master.CEILING_DB + 1e-6
    assert abs(master.loudness(y, SR) - master.TARGET_LUFS) < 0.2


def test_loudness_range_of_a_step():
    # 20 s at one level, 20 s 10 dB lower: the range is about 10 LU
    rng = np.random.default_rng(7)
    x = rng.normal(0, 0.1, (40 * SR, 2))
    x[20 * SR :] *= 10 ** (-10 / 20)
    assert master.loudness_range(x, SR) == pytest.approx(10.0, abs=1.0)


def test_pcm_hash_is_of_samples():
    pcm = master.to_pcm16(np.zeros((100, 2)), seed=3)
    assert master.pcm_sha256(pcm) == master.pcm_sha256(pcm.copy())
    assert master.to_pcm16(np.zeros((100, 2)), seed=3).tobytes() == pcm.tobytes()
