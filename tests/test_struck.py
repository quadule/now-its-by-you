"""The struck bank: modes ring at their frequencies for their T60s, hits add, and it is cheap."""

import time

import numpy as np
import pytest

from songbird.synth import struck

SR = 44100


def peak(y: np.ndarray, guess: float) -> float:
    seg = y * np.hanning(len(y))
    n = 1 << 20
    spec = np.abs(np.fft.rfft(seg, n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    band = (freqs > guess * 0.95) & (freqs < guess * 1.05)
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


@pytest.mark.parametrize("freq", [55.0, 700.0, 3000.0, 6500.0, 15000.0])
def test_a_mode_rings_at_its_frequency_for_its_t60(freq):
    y = struck.ring([freq], [0.8], [0.01], [[1.0]], SR, SR)
    assert abs(1200 * np.log2(peak(y[int(0.02 * SR):], freq) / freq)) < 0.5
    env = np.abs(y)
    a = np.sqrt(np.mean(y[int(0.05 * SR): int(0.15 * SR)] ** 2))
    b = np.sqrt(np.mean(y[int(0.45 * SR): int(0.55 * SR)] ** 2))
    assert abs(20 * np.log10(b / a) - (-60 * 0.4 / 0.8)) < 1.0  # 30 dB down after 0.4 s
    assert abs(y[int(0.01 * SR) - 1]) < 1e-9 and env.max() < 1.01  # nothing before the strike, a sine start


def test_quarter_rate_modes_match_full_rate():
    rng = np.random.default_rng(0)
    freqs = rng.uniform(80, 4000, 40)
    amps = rng.normal(0, 1, (5, 40))
    times = [0.0, 0.1234567, 0.3, 0.31, 0.7]
    a = struck.ring(freqs, 0.5, times, amps, SR, SR)
    b = struck.ring(freqs, 0.5, times, amps, SR, SR, multirate=False)
    # the same but for each strike's first 2 ms, which the upsampling smooths (as a stick's contact would)
    away = np.ones(SR, bool)
    for t in times:
        away[max(0, int(t * SR) - 90): int(t * SR) + 90] = False
    err = np.sqrt(np.mean((a - b)[away] ** 2)) / np.sqrt(np.mean(b[away] ** 2))
    assert err < 3e-4  # -70 dB


def test_hits_add_and_channels_hear_their_own_mix():
    freqs = [200.0, 431.0, 977.0]
    one = struck.ring(freqs, 1.0, [0.05], [[1, 0.5, 0.2]], SR, SR)
    two = struck.ring(freqs, 1.0, [0.2], [[0.3, 1.0, 0.1]], SR, SR)
    both = struck.ring(freqs, 1.0, [0.05, 0.2], [[1, 0.5, 0.2], [0.3, 1.0, 0.1]], SR, SR)
    assert np.allclose(both, one + two, atol=1e-6)
    stereo = struck.ring(freqs, 1.0, [0.05], [[1, 0.5, 0.2]], SR, SR, mix=[[1, 0], [0, 1], [1, 1]])
    assert stereo.shape == (SR, 2) and not np.allclose(stereo[:, 0], stereo[:, 1])


def test_bend_and_damping_act_on_every_mode():
    bent = struck.ring([500.0], 2.0, [0.0], [[1.0]], SR, SR, bend=np.full(SR, 0.01))
    assert abs(peak(bent, 505.0) - 505.0) < 0.3
    damp = np.zeros(SR)
    damp[SR // 2:] = 40.0  # a hand on it halfway: 40 nepers a second more
    held = struck.ring([500.0], 2.0, [0.0], [[1.0]], SR, SR, damp=damp)
    free = struck.ring([500.0], 2.0, [0.0], [[1.0]], SR, SR)
    late = slice(int(0.7 * SR), int(0.8 * SR))
    assert np.sqrt(np.mean(held[late] ** 2)) < 0.01 * np.sqrt(np.mean(free[late] ** 2))


def test_a_song_of_strikes_is_cheap():
    rng = np.random.default_rng(1)
    freqs = np.sort(rng.uniform(150, 4000, 150))
    times = np.arange(0, 180, 0.25)
    amps = rng.normal(0, 1, (len(times), 150))
    struck.ring(freqs, 3.0, times[:3], amps[:3], SR, SR)  # compile
    t = time.perf_counter()
    y = struck.ring(freqs, 3.0, times, amps, SR, 180 * SR)
    assert time.perf_counter() - t < 6.0 and np.all(np.isfinite(y))
