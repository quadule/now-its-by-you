"""The moving-pitch string loop: in tune wherever it goes, decaying as asked, and cheap."""

import time

import numpy as np
import pytest

from songbird.synth import stringloop

SR = 44100


def f0(y: np.ndarray, guess: float, t0: float, t1: float) -> float:
    """Fundamental by zero-padded FFT peak with parabolic interpolation."""
    seg = y[int(t0 * SR): int(t1 * SR)]
    seg = seg * np.hanning(len(seg))
    n = 16 * SR
    spec = np.abs(np.fft.rfft(seg, n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    band = (freqs > guess * 0.94) & (freqs < guess * 1.06)
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


def cents(a: float, b: float) -> float:
    return 1200 * np.log2(a / b)


@pytest.mark.parametrize("freq", [41.2, 98.0, 196.0, 440.0, 1318.5])
@pytest.mark.parametrize("brightness", [0.1, 0.9])
def test_a_held_string_is_in_tune(freq, brightness):
    y = stringloop.note(freq, 2.0, SR, np.random.default_rng(0), brightness=brightness, decay=4.0)
    assert abs(cents(f0(y, freq, 0.2, 1.8), freq)) < 0.5


def test_a_slide_arrives_in_tune():
    """A slide up a fourth over 150 ms, then held: in tune on the new note."""
    n = int(2.0 * SR)
    track = np.full(n, 500.0)
    track[: int(0.1 * SR)] = 0.0
    k = int(0.15 * SR)
    track[int(0.1 * SR): int(0.1 * SR) + k] = 500.0 * (0.5 - 0.5 * np.cos(np.pi * np.arange(k) / k))
    y = stringloop.note(220.0, 2.0, SR, np.random.default_rng(1), cents=track, decay=5.0)
    target = 220.0 * 2 ** (500 / 1200)
    assert abs(cents(f0(y, target, 0.5, 1.9), target)) < 0.5


def test_the_fundamental_falls_60_db_in_t60():
    freq = 196.0
    period = int(round(SR / freq)) * 4
    x = np.zeros(4 * SR)
    x[:period // 4] = stringloop.excitation(freq, SR, np.random.default_rng(2))
    y = stringloop.ring(np.full(len(x), freq), x, SR, loss=0.05, t60=2.0)
    from scipy.signal import butter, sosfiltfilt

    band = sosfiltfilt(butter(2, [freq * 0.8, freq * 1.25], btype="bandpass", fs=SR, output="sos"), y)
    hop = SR // 20
    env = 20 * np.log10(np.sqrt(np.convolve(band**2, np.ones(hop) / hop, mode="valid"))[::hop] + 1e-12)
    slope = np.polyfit(np.arange(10, 60) / 20, env[10:60], 1)[0]  # dB per second
    assert abs(-60 / slope - 2.0) < 0.2


def test_a_second_pick_lands_on_the_ringing_string():
    one = stringloop.note(293.66, 1.0, SR, np.random.default_rng(3), picks=((0.0, 1.0),))
    two = stringloop.note(293.66, 1.0, SR, np.random.default_rng(3), picks=((0.0, 1.0), (0.3, 1.0)))
    rms = lambda x: np.sqrt(np.mean(x**2))  # noqa: E731
    assert rms(two[int(0.32 * SR): int(0.5 * SR)]) > 1.2 * rms(one[int(0.32 * SR): int(0.5 * SR)])
    assert np.array_equal(two, stringloop.note(293.66, 1.0, SR, np.random.default_rng(3),
                                               picks=((0.0, 1.0), (0.3, 1.0))))


def test_a_pick_jittered_before_the_note_lands_at_its_start():
    y = stringloop.note(220.0, 0.5, SR, np.random.default_rng(6), picks=((-0.003, 1.0), (0.2, 0.8)))
    assert np.all(np.isfinite(y)) and np.abs(y[: int(0.1 * SR)]).max() > 0


def test_the_note_ends_quietly_and_without_dc():
    y = stringloop.note(110.0, 0.5, SR, np.random.default_rng(4), damp=0.1)
    assert np.all(np.isfinite(y))
    assert abs(y.mean()) < 1e-3 * np.sqrt(np.mean(y**2))
    assert np.sqrt(np.mean(y[-int(0.02 * SR):] ** 2)) < 0.02 * np.sqrt(np.mean(y[: int(0.3 * SR)] ** 2))


def test_a_string_second_costs_little():
    stringloop.note(220.0, 0.2, SR, np.random.default_rng(5))  # compile
    t = time.perf_counter()
    for _ in range(10):
        stringloop.note(220.0, 1.0, SR, np.random.default_rng(5))
    assert (time.perf_counter() - t) / 10 < 0.05
