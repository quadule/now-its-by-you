import numpy as np
import pytest

from songbird.synth.pluck import loop_filter, pluck

SR = 44100


def measured_f0(y: np.ndarray, guess: float) -> float:
    """Fundamental by zero-padded FFT peak with parabolic interpolation."""
    seg = y[int(0.1 * SR): int(1.1 * SR)] * np.hanning(SR)
    spec = np.abs(np.fft.rfft(seg, 16 * SR))
    freqs = np.fft.rfftfreq(16 * SR, 1 / SR)
    band = (freqs > guess * 0.9) & (freqs < guess * 1.1)
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2])
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


@pytest.mark.parametrize("freq", [82.41, 146.83, 261.63, 440.0, 987.77])
def test_tuning_within_two_cents(freq):
    y = pluck(freq, 1.5, SR, np.random.default_rng(0), brightness=0.6, decay=4.0)
    cents = 1200 * np.log2(measured_f0(y, freq) / freq)
    assert abs(cents) < 2.0


def test_loop_filter_fraction_stays_in_lagrange_range():
    for period in np.linspace(20.3, 600.7, 50):
        whole, taps = loop_filter(period, 0.3)
        assert whole >= 2 and len(taps) == 5


def test_pluck_decays_and_is_deterministic():
    a = pluck(220.0, 2.0, SR, np.random.default_rng(7))
    b = pluck(220.0, 2.0, SR, np.random.default_rng(7))
    assert np.array_equal(a, b)
    early, late = np.abs(a[: SR // 4]).max(), np.abs(a[int(1.75 * SR): 2 * SR]).max()
    assert late < early * 0.5
