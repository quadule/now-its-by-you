import numpy as np

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


def test_pcm_hash_is_of_samples():
    pcm = master.to_pcm16(np.zeros((100, 2)), seed=3)
    assert master.pcm_sha256(pcm) == master.pcm_sha256(pcm.copy())
    assert master.to_pcm16(np.zeros((100, 2)), seed=3).tobytes() == pcm.tobytes()
