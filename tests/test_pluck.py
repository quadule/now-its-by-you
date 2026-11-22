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


def test_two_planes_give_a_loud_start_and_a_long_soft_tail():
    y = pluck(146.83, 4.0, SR, np.random.default_rng(3), brightness=0.5, decay=3.0, planes=0.35)
    hop = SR // 50
    env = 20 * np.log10(np.sqrt(np.convolve(y**2, np.ones(hop) / hop, mode="valid"))[::hop] + 1e-12)
    early = np.polyfit(np.arange(5, 25) / 50, env[5:25], 1)[0]
    late = np.polyfit(np.arange(120, 190) / 50, env[120:190], 1)[0]
    assert early < late < 0  # decays fast while the plane across the top dominates, then slower


def test_a_paired_course_beats_and_a_muted_stroke_stops():
    single = pluck(293.66, 2.0, SR, np.random.default_rng(4), decay=4.0)
    paired = pluck(293.66, 2.0, SR, np.random.default_rng(4), decay=4.0, course=6.0, spread=0.004)
    assert not np.allclose(single, paired)
    muted = pluck(146.83, 0.3, SR, np.random.default_rng(4), mute=True)
    rms = lambda x: np.sqrt(np.mean(x**2))  # noqa: E731
    assert rms(muted[int(0.1 * SR): int(0.3 * SR)]) < 0.05 * rms(muted[: int(0.01 * SR)])


def test_open_strings_answer_what_shares_their_harmonics():
    from songbird.synth.pluck import sympathetic

    note = pluck(146.83, 1.0, SR, np.random.default_rng(5), decay=3.0)  # D3
    tuned = sympathetic(note, SR, [50, 57])  # open D3 and A3
    detuned = sympathetic(note, SR, [51, 56])  # open strings sharing nothing with it
    assert np.sqrt(np.mean(tuned**2)) > 4 * np.sqrt(np.mean(detuned**2))


def test_dc_blocker_preserves_low_bass_fundamentals():
    """The 10 Hz DC blocker removes DC without eating the bass's low E1 (41.2 Hz)."""
    y = pluck(41.2, 1.5, SR, np.random.default_rng(1), brightness=0.3, decay=2.0)
    assert abs(float(np.mean(y))) < 1e-3
    # Fundamental around 41 Hz should remain strong relative to the 2nd harmonic (~82 Hz)
    seg = y[int(0.05 * SR): int(1.05 * SR)] * np.hanning(SR)
    spec = np.abs(np.fft.rfft(seg, 4 * SR))
    freqs = np.fft.rfftfreq(4 * SR, 1 / SR)
    f1 = spec[(freqs > 38) & (freqs < 45)].max()
    f2 = spec[(freqs > 78) & (freqs < 86)].max()
    assert 20 * np.log10(f1 / (f2 + 1e-12)) > -6.0
