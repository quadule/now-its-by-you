"""The analog synthesizers, measured against what analog synthesizers do."""

import numpy as np
import pytest
from scipy.signal import butter, hilbert, sosfiltfilt

from songbird.score import Note
from songbird.synth import analog, osc

SR = 44100
SETTINGS = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0, maker=0, tonic=62)


def render(name, notes, secs, settings=None, seed=0, maker=0):
    rng = np.random.default_rng([seed, 17, 99])
    make = np.random.default_rng([maker, 29, 99])
    y = analog.render(name, tuple(notes), SR, int(secs * SR), rng, make, {**SETTINGS, **(settings or {})})
    return y if y.ndim == 1 else y.mean(axis=1)


def hz(m):
    return 440.0 * 2.0 ** ((m - 69.0) / 12.0)


def cents_of_peak(y, f, t0, t1, sr=SR):
    seg = y[int(t0 * sr): int(t1 * sr)]
    n = 16 * len(seg)
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n))
    freqs = np.fft.rfftfreq(n, 1 / sr)
    band = (freqs > f * 0.97) & (freqs < f * 1.03)
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    peak = freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])
    return 1200.0 * np.log2(peak / f)


def rms_track(y, ms):
    n = max(1, int(ms * 1e-3 * SR))
    return np.sqrt(np.convolve(y**2, np.ones(n) / n, mode="same"))


def semitones_track(y, lo, hi, ref):
    """The pitch of the fundamental (semitones re ref Hz), from the analytic signal of a band around it."""
    band = sosfiltfilt(butter(4, [lo, hi], btype="bandpass", fs=SR, output="sos"), y)
    phase = np.unwrap(np.angle(hilbert(band)))
    f = np.convolve(np.gradient(phase) * SR / (2 * np.pi), np.ones(128) / 128, mode="same")
    return 12.0 * np.log2(np.maximum(f, 1.0) / ref)


def test_the_voice_draws_oscs_own_band_limited_waves():
    sr2 = 2.0 * SR
    f = 1234.5
    n = 4000
    saw, _ = osc.saw(np.full(n, f), sr2, 0.3)
    pulse, _ = osc.pulse(np.full(n, f), np.full(n, 0.35), sr2, 0.3)
    q = 0.3
    ours_saw, ours_pulse = np.empty(n), np.empty(n)
    for i in range(n):
        ours_saw[i] = analog._wave(0, q, f / sr2, 0.5)
        ours_pulse[i] = analog._wave(1, q, f / sr2, 0.35)
        q += f / sr2
        if q >= 1.0:
            q -= 1.0
    assert np.max(np.abs(ours_saw - saw)) < 1e-9 and np.max(np.abs(ours_pulse - pulse)) < 1e-9


@pytest.mark.parametrize("name", ["synth-pad", "synth-bass", "synth-solo", "synth-arp", "sub-bass"])
def test_a_new_machine_is_in_tune_whatever_its_maker(name):
    """At wear 0 every machine plays within 2 cents across the compass: its detuned oscillators sit
    under one on the note, and a width-modulated pulse keeps its centre (its pitch) still."""
    lo, hi = analog.SPEC[name]["register"]
    for maker in (1, 2, 3):
        for pitch in (lo + 5, (lo + hi) // 2, hi - 5):
            y = render(name, [Note("x", 0.1, 1.2, float(pitch), 0.6)], 1.5, dict(wear=0.0, ornament=0.0), seed=maker,
                       maker=maker)
            assert abs(cents_of_peak(y, hz(pitch), 0.3, 1.2)) < 2.0, (maker, pitch)


def test_the_ladder_sings_at_its_cutoff_at_full_resonance():
    """Key-tracked at full resonance the ladder is an oscillator in tune with the keyboard."""
    sr2 = 2.0 * SR
    for m in (48, 72, 96):
        f = hz(m)
        x = np.zeros(int(1.5 * sr2))
        k = int(4 * sr2 / f)
        x[:k] = 0.3 * np.sin(2 * np.pi * f * np.arange(k) / sr2)  # a few periods to start it
        y = analog.ladder(x, f, 1.0, sr2)
        assert abs(cents_of_peak(y, f, 0.8, 1.5, sr=sr2)) < 0.5, m
        assert np.sqrt(np.mean(y[int(1.0 * sr2):] ** 2)) > 0.2  # it keeps singing by itself


def test_the_ladder_is_a_24_db_low_pass_that_loses_bass_as_it_resonates():
    sr2 = 2.0 * SR
    x = np.random.default_rng(0).standard_normal(int(2 * sr2)) * 0.05
    f = np.fft.rfftfreq(len(x), 1 / sr2)
    X = np.abs(np.fft.rfft(x)) ** 2

    def gain_db(y, lo, hi):
        band = (f > lo) & (f < hi)
        return 10 * np.log10((np.abs(np.fft.rfft(y)) ** 2)[band].sum() / X[band].sum())

    flat = analog.ladder(x, 1000.0, 0.0, sr2)
    assert abs(gain_db(flat, 80, 120)) < 0.5
    assert -13.5 < gain_db(flat, 980, 1020) < -10.5  # each stage 3 dB down at the cutoff
    slope = gain_db(flat, 3920, 4080) - gain_db(flat, 7840, 8160)
    assert 20.0 < slope < 25.0
    ringing = analog.ladder(x, 1000.0, 0.9, sr2)
    assert gain_db(ringing, 980, 1020) > 20.0  # the resonant peak
    assert -6.0 < gain_db(ringing, 80, 120) < -2.0  # the bass it costs (half given back)


@pytest.mark.parametrize("name", ["synth-solo", "synth-arp"])
def test_nothing_folds_back_at_c7(name):
    f0 = hz(96)
    y = render(name, [Note("x", 0.1, 1.8, 96.0, 0.9)], 2.2, dict(wear=0.0, ornament=0.0, brightness=1.0))
    seg = y[int(0.5 * SR): int(1.5 * SR)] * np.blackman(SR)
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(SR, 1 / SR)
    h = np.maximum(np.round(freqs / f0), 1)
    harmonic = np.abs(freqs - h * f0) < 0.02 * h * f0
    band = (freqs > 30) & (freqs < 20000)
    assert 20 * np.log10(spec[band & ~harmonic].max() / spec[band & harmonic].max()) < -70.0


@pytest.mark.parametrize("name,t60", [("synth-pad", 0.8), ("synth-bass", 0.08), ("synth-solo", 0.18),
                                      ("synth-arp", 0.16), ("sub-bass", 0.08)])
def test_a_note_releases_as_its_envelope_says(name, t60):
    m = 72 if name != "sub-bass" else 48
    y = render(name, [Note("x", 0.2, 1.5, float(m), 0.8)], 4.0, dict(wear=0.0))
    e = rms_track(y, 1000.0 / hz(m))
    held = e[int(1.69 * SR)]
    after = e[int(1.7 * SR):]
    measured = np.argmax(after < held * 1e-3) / SR
    assert abs(measured / t60 - 1.0) < 0.2
    assert np.all(e[: int(0.195 * SR)] == 0.0)


@pytest.mark.parametrize("name,a,b", [("synth-solo", 60, 67), ("synth-bass", 36, 43), ("sub-bass", 33, 40)])
def test_legato_glides_and_a_detached_note_starts_again(name, a, b):
    touching = [Note("x", 0.2, 0.6, float(a), 0.7), Note("x", 0.8, 0.8, float(b), 0.7)]
    y = render(name, touching, 2.0, dict(wear=0.0, ornament=0.0))
    semis = semitones_track(y, hz(a) * 0.8, hz(b) * 1.25, hz(a))[int(0.8 * SR): int(1.2 * SR)]
    t90 = np.argmax(semis > 0.9 * (b - a)) / SR
    assert 0.02 < t90 < 0.08  # a glide of 20 to 80 ms
    e = rms_track(y, 2000.0 / hz(a - 12))
    assert 20 * np.log10(e[int(0.75 * SR): int(0.9 * SR)].min() / e[int(0.7 * SR)]) > -2.0  # no new attack
    apart = [Note("x", 0.2, 0.5, float(a), 0.7), Note("x", 0.8, 0.8, float(b), 0.7)]
    y = render(name, apart, 2.0, dict(wear=0.0, ornament=0.0))
    e = rms_track(y, 1000.0 / hz(a))
    assert 20 * np.log10(e[int(0.75 * SR): int(0.81 * SR)].min() / e[int(0.65 * SR)]) < -25.0  # released
    if name != "synth-bass":  # (the bass's octave-down square confuses the tracker so soon after an attack)
        semis = semitones_track(y, hz(a) * 0.8, hz(b) * 1.25, hz(a))
        assert abs(semis[int(0.83 * SR)] - (b - a)) < 0.3  # and it starts on its own pitch, no glide


def test_the_chorus_sweeps_two_bucket_brigades_in_antiphase():
    d1, d2 = analog.chorus_delays(SR * 6, SR, 0.004, 0.0008, (0.5, 0.85), 0.6)
    assert 3.1 < d1.min() / SR * 1e3 < 3.3 and 4.7 < d1.max() / SR * 1e3 < 4.9
    assert np.allclose(d1 + d2, 2 * 0.004 * SR)  # antiphase: one side lengthens as the other shortens
    x = np.sin(2 * np.pi * 1000 * np.arange(SR * 6) / SR)
    w = analog._delays(x, d1, d2)[:, 0]
    phase = np.unwrap(np.angle(hilbert(w)))
    f = np.convolve(np.gradient(phase) * SR / (2 * np.pi), np.ones(441) / 441, mode="same")[SR:-SR]
    swing = 1200 * np.log2(f / 1000.0)
    assert 3.0 < swing.max() < 4.0 and -4.0 < swing.min() < -3.0  # the chorus's pitch wobble, a few cents
    pad = analog.render("synth-pad", (Note("x", 0.1, 1.0, 60.0, 0.7),), SR, 2 * SR, np.random.default_rng(0),
                        np.random.default_rng(1), SETTINGS)
    left, right = pad[int(0.3 * SR): int(1.0 * SR)].T
    assert 0.3 < np.corrcoef(left, right)[0, 1] < 0.98  # wide, but not two different instruments


def test_the_sub_attacks_the_same_way_every_time():
    notes = [Note("x", 0.2, 0.3, 36.0, 0.8), Note("x", 0.55, 0.3, 36.0, 0.8), Note("x", 1.3, 0.3, 36.0, 0.8)]
    y = render("sub-bass", notes, 2.0)
    first = y[int(0.2 * SR): int(0.21 * SR)]
    for start in (0.55, 1.3):  # one straight after a release, one from silence
        seg = y[int(start * SR): int((start + 0.01) * SR)]
        assert np.dot(first, seg) / np.sqrt(np.dot(first, first) * np.dot(seg, seg)) > 0.9999
    spec = np.abs(np.fft.rfft(y[int(0.25 * SR): int(0.5 * SR)] * np.hanning(int(0.25 * SR)), 1 << 16))
    freqs = np.fft.rfftfreq(1 << 16, 1 / SR)
    h = [spec[np.argmin(np.abs(freqs - k * hz(36)))] for k in (1, 2, 3)]
    assert -17 < 20 * np.log10(h[1] / h[0]) < -13 and -33 < 20 * np.log10(h[2] / h[0]) < -27


def test_drift_is_a_few_cents_and_grows_with_wear():
    def wander(wear):
        y = render("synth-solo", [Note("x", 0.1, 8.0, 69.0, 0.7)], 8.3, dict(wear=wear, ornament=0.0))
        return np.array([cents_of_peak(y, hz(69), t, t + 0.5) for t in np.arange(0.5, 7.5, 0.5)])

    new, worn = wander(0.0), wander(1.0)
    assert np.ptp(new) < 2.0 and np.ptp(worn) > 5.0


def test_the_solos_vibrato_comes_in_late_and_as_deep_as_ornament():
    y = render("synth-solo", [Note("x", 0.1, 2.5, 69.0, 0.7)], 3.0, dict(wear=0.0, ornament=1.0))
    cents = 100 * semitones_track(y, hz(69) * 0.9, hz(69) * 1.1, hz(69))
    assert np.abs(cents[int(0.15 * SR): int(0.35 * SR)]).max() < 2.0
    late = cents[int(1.2 * SR): int(2.4 * SR)]
    assert 20.0 < (late.max() - late.min()) / 2 < 40.0
    ups = np.flatnonzero(np.diff(np.sign(late - late.mean())) > 0)
    assert 5.0 < (len(ups) - 1) / ((ups[-1] - ups[0]) / SR) < 6.0


def test_articulations_do_what_the_spec_says():
    pad = rms_track(render("synth-pad", [Note("x", 0.1, 2.0, 64.0, 0.7)], 3.0), 20)
    swell = rms_track(render("synth-pad", [Note("x", 0.1, 2.0, 64.0, 0.7, art="swell")], 3.0), 20)
    stab = rms_track(render("synth-pad", [Note("x", 0.1, 2.0, 64.0, 0.7, art="stab")], 3.0), 20)
    at = int(0.25 * SR)
    assert swell[at] / swell.max() < 0.5 * pad[at] / pad.max()  # a swell takes its time
    assert stab[int(0.45 * SR)] < 0.1 * stab.max()  # a stab has fallen 20 dB in 0.3 s
    bend = render("synth-solo", [Note("x", 0.2, 1.0, 67.0, 0.7, art="bend")], 1.6, dict(wear=0.0, ornament=0.0))
    semis = semitones_track(bend, hz(64), hz(70), hz(67))
    assert -2.0 < semis[int(0.21 * SR)] < -1.2 and abs(semis[int(0.5 * SR)]) < 0.1
    plain = render("synth-bass", [Note("x", 0.1, 0.5, 40.0, 0.6)], 1.0)
    accent = render("synth-bass", [Note("x", 0.1, 0.5, 40.0, 0.6, art="accent")], 1.0)
    short = render("synth-bass", [Note("x", 0.1, 0.5, 40.0, 0.6, art="short")], 1.0)
    w = slice(int(0.1 * SR), int(0.2 * SR))
    assert 3.0 < 20 * np.log10(np.std(accent[w]) / np.std(plain[w])) < 4.0
    assert np.std(short[int(0.4 * SR): int(0.45 * SR)]) < 0.01 * np.std(plain[int(0.4 * SR): int(0.45 * SR)])


def test_a_restruck_key_takes_its_voice_again_and_nothing_clicks():
    """A pad chord struck four times: the same eight voices carry it, nothing doubles or clicks."""
    chord = (60.0, 64.0, 67.0, 72.0)
    notes = [Note("x", 0.1 + 0.4 * k, 0.38, p, 0.6) for k in range(4) for p in chord]
    y = render("synth-pad", notes, 3.0)
    e = rms_track(y, 30)
    assert e[int(1.5 * SR)] < 1.6 * e[int(0.45 * SR)]  # restriking doesn't pile voices up
    # each restrike attacks again from where the release had got to: no gap, no jump
    one = rms_track(render("synth-pad", [Note("x", 0.1 + 0.4 * k, 0.38, 60.0, 0.6) for k in range(4)], 3.0), 30)
    for t in (0.5, 0.9, 1.3):
        before = one[int((t - 0.06) * SR)]
        assert 20 * np.log10(one[int((t - 0.03) * SR): int((t + 0.05) * SR)].min() / before) > -2.0
