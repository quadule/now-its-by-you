"""The oscillators: band-limited, in tune, zero mean."""

import numpy as np
import pytest

from songbird.synth import osc

SR = 44100


def alias_db(y, f0):
    """The strongest component below 20 kHz that is not a harmonic of f0, against the strongest harmonic."""
    seg = y[SR // 10: SR // 10 + SR] * np.blackman(SR)
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(SR, 1 / SR)
    near = np.abs(freqs - np.round(freqs / f0) * f0) < 8
    band = freqs < 20000
    return 20 * np.log10(spec[band & ~near].max() / spec[band & near].max())


def at_2x(kind, f0, duty=0.25):
    n = int(1.3 * SR * 2)
    freq = np.full(n, f0)
    if kind == "saw":
        y, _ = osc.saw(freq, 2.0 * SR)
    elif kind == "pulse":
        y, _ = osc.pulse(freq, np.full(n, duty), 2.0 * SR)
    else:
        y, _ = osc.triangle(freq, 2.0 * SR)
    return osc.decimate2(y)


@pytest.mark.parametrize("kind", ["saw", "pulse", "triangle"])
@pytest.mark.parametrize("f0", [440.0, 2000.0])
def test_oscillators_at_twice_the_rate_fold_nothing_audible(kind, f0):
    assert alias_db(at_2x(kind, f0), f0) < -75.0


def test_a_saw_keeps_its_harmonics_and_no_dc():
    y = at_2x("saw", 441.0)
    seg = y[SR // 10: SR // 10 + SR] * np.blackman(SR)
    spec = np.abs(np.fft.rfft(seg))
    for k in (2, 5, 10, 20):
        assert abs(20 * np.log10(spec[int(441 * k)] / spec[441]) - 20 * np.log10(1 / k)) < 0.8
    assert abs(y[SR // 10:].mean()) < 1e-3


def test_pulse_duty_sets_its_missing_harmonics():
    y = at_2x("pulse", 441.0, duty=0.25)  # a quarter-duty pulse has no 4th, 8th... harmonic
    seg = y[SR // 10: SR // 10 + SR] * np.blackman(SR)
    spec = np.abs(np.fft.rfft(seg))
    assert 20 * np.log10(spec[441 * 4] / spec[441]) < -40.0
    assert 20 * np.log10(spec[441 * 3] / spec[441]) > -15.0


def test_stepped_table_and_drift():
    table = np.concatenate([np.arange(15, -1, -1), np.arange(0, 16)]).astype(float) / 7.5 - 1.0
    n = int(1.3 * SR * 2)
    y, _ = osc.stepped(np.full(n, 440.0), table, 2.0 * SR)
    assert alias_db(osc.decimate2(y), 440.0) < -60.0
    d = osc.drift(SR * 4, SR, np.random.default_rng(0), 3.0)
    assert d.shape == (SR * 4,) and 0.5 < d.std() < 6.0 and np.max(np.abs(np.diff(d))) < 0.01
