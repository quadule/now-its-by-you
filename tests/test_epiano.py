"""The electric pianos, measured against what tine and reed pianos do."""

import numpy as np
import pytest
from scipy.signal import butter, sosfiltfilt

from songbird.score import Note
from songbird.synth import epiano

SR = 44100
PLAIN = dict(wear=0.0, ornament=0.0)


def render(name, notes, secs, seed=0, maker=0, **settings):
    s = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0)
    s.update(settings)
    return epiano.render(name, tuple(notes), SR, int(secs * SR), np.random.default_rng([seed, 17, 99]),
                         np.random.default_rng([maker, 29, 99]), s)


def mono(y):
    return y if y.ndim == 1 else y.mean(axis=1)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def spectrum(y, t0, t1, pad=8):
    seg = y[int(t0 * SR): int(t1 * SR)]
    seg = seg * np.hanning(len(seg))
    n = 1 << int(np.ceil(np.log2(pad * len(seg))))
    return np.fft.rfftfreq(n, 1 / SR), np.abs(np.fft.rfft(seg, n))


def peak_hz(y, guess, t0, t1):
    seg = y[int(t0 * SR): int(t1 * SR)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 16 * SR))
    freqs = np.fft.rfftfreq(16 * SR, 1 / SR)
    band = (freqs > guess * 0.97) & (freqs < guess * 1.03)
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


def harmonics_db(y, f0, t0, t1, count=3):
    freqs, spec = spectrum(y, t0, t1)
    levels = np.array([spec[(freqs > f0 * (h - 0.25)) & (freqs < f0 * (h + 0.25))].max() for h in range(1, count + 1)])
    return 20 * np.log10(levels / levels[0])


def decay_t60(y, f0, t0, t1):
    """T60 of the band around f0, from the slope of its level between t0 and t1."""
    band = sosfiltfilt(butter(2, [f0 * 0.9, f0 * 1.1], btype="bandpass", fs=SR, output="sos"), y)
    hop = int(0.02 * SR)
    frames = band[int(t0 * SR): int(t1 * SR)]
    frames = frames[: len(frames) // hop * hop].reshape(-1, hop)
    db = 10 * np.log10(np.mean(frames**2, axis=1) + 1e-30)
    slope = np.polyfit(np.arange(len(db)) * hop / SR, db, 1)[0]
    return -60.0 / slope


def rms_db(y, t0, t1):
    return 10 * np.log10(np.mean(y[int(t0 * SR): int(t1 * SR)] ** 2) + 1e-30)


def crossing_rate(x, t):
    """Cycles a second of a slow oscillation x sampled at times t: from its first to its last zero crossing."""
    crossings = np.flatnonzero(np.diff(np.sign(x)) != 0)
    return 0.5 * (len(crossings) - 1) / (t[crossings[-1]] - t[crossings[0]])


@pytest.mark.parametrize("name", ["epiano", "epiano-reed"])
def test_in_tune_across_the_keyboard(name):
    lo, hi = epiano.SPEC[name]["register"]
    for m in (lo + 5, 60, hi - 5):
        y = mono(render(name, [Note("x", 0.1, 1.2, float(m), 0.6)], 1.4, **PLAIN))
        assert abs(1200 * np.log2(peak_hz(y, hz(m), 0.3, 1.2) / hz(m))) < 2.0, m


def test_the_tines_fundamental_sustains_as_a_tuning_fork_does():
    """T60 10 s at middle C, 10 (262 / f0)^0.8 elsewhere; the fork's quick mode makes the first second faster."""
    for m in (60, 72):
        y = mono(render("epiano", [Note("x", 0.1, 3.4, float(m), 0.3)], 3.5, **PLAIN))
        want = epiano.tine_t60(hz(m))
        late = decay_t60(y, hz(m), 1.5, 3.4)
        assert abs(late / want - 1.0) < 0.15, (m, late, want)
        assert decay_t60(y, hz(m), 0.15, 0.6) < 0.8 * late  # the quick first drop


def test_the_tines_upper_modes_are_a_bell_that_rings_briefly_and_louder_for_a_harder_blow():
    piano = epiano.TinePiano(SR, np.random.default_rng(0), PLAIN)
    for m, ratio in ((36, 5.2), (84, 6.27)):
        heard = []
        for vel in (0.3, 0.9):
            force, freqs, gains, t60s, *_ = piano.note(Note("x", 0.0, 1.0, float(m), vel), 2.0 * SR,
                                                       np.random.default_rng(1), None)
            reach = epiano._reach(force, freqs, 2.0 * SR)
            level = np.abs(gains) * reach * freqs  # as the pickup hears each mode: its swing times its speed
            heard.append(20 * np.log10(level[2] / level[0]))
            assert abs(freqs[2] / freqs[0] - ratio) < 0.15 and 13.5 < freqs[3] / freqs[0] < 18.0
            assert np.all((t60s[2:] > 0.05) & (t60s[2:] < 0.4))
        assert heard[1] - heard[0] > 8.0  # a harder blow is a shorter contact, which reaches the bell
    # in the sound: the band between the 6th and 7th harmonics dies within a few tenths, the fundamental rings on
    m = 76
    f2 = hz(m) * epiano.tine_ratios(m)[0]
    y = mono(render("epiano", [Note("x", 0.1, 1.5, float(m), 0.6)], 1.6, **PLAIN))
    band = sosfiltfilt(butter(2, [f2 * 0.97, f2 * 1.03], btype="bandpass", fs=SR, output="sos"), y)
    fundamental = sosfiltfilt(butter(2, [hz(m) * 0.9, hz(m) * 1.1], btype="bandpass", fs=SR, output="sos"), y)
    bell_fall = rms_db(band, 0.11, 0.16) - rms_db(band, 0.31, 0.36)
    tone_fall = rms_db(fundamental, 0.11, 0.16) - rms_db(fundamental, 0.31, 0.36)
    assert bell_fall > tone_fall + 10.0 and tone_fall < 6.0


def test_the_pickup_barks_when_played_hard():
    """The 2nd harmonic about 12 dB under the fundamental at velocity 0.5 and about level with it at 0.9."""
    h = {}
    for vel in (0.3, 0.5, 0.9):
        y = mono(render("epiano", [Note("x", 0.1, 1.0, 60.0, vel)], 1.2, **PLAIN))
        h[vel] = harmonics_db(y, hz(60), 0.12, 0.32)
    assert h[0.3][1] < -18.0
    assert -14.5 < h[0.5][1] < -9.5
    assert -3.0 < h[0.9][1] < 6.0 and h[0.9][2] > -8.0  # and the third comes up with it
    late = harmonics_db(mono(render("epiano", [Note("x", 0.1, 2.0, 60.0, 0.9)], 2.2, **PLAIN)), hz(60), 1.6, 2.0)
    assert late[1] < h[0.9][1] - 8.0  # the bark fades with the swing


def test_the_tremolo_pans_at_four_to_six_hertz_as_deep_as_ornament_asks():
    notes = [Note("x", 0.1, 2.9, 57.0, 0.6)]
    for ornament in (0.5, 1.0):
        y = render("epiano", notes, 3.0, ornament=ornament)
        live = slice(int(0.3 * SR), int(2.9 * SR))
        pan = (y[live, 0] - y[live, 1]) / (y[live, 0] + y[live, 1] + 1e-12)
        ok = np.abs(y[live, 0] + y[live, 1]) > 0.05 * np.max(np.abs(y[live, 0] + y[live, 1]))
        pan = pan[ok]
        depth = np.percentile(np.abs(pan), 99)
        assert abs(depth - 0.85 * ornament) < 0.05
        # the rate: how often the pan crosses the middle
        assert 3.95 < crossing_rate(pan, np.flatnonzero(ok) / SR) < 6.05
    y = render("epiano", notes, 3.0, ornament=0.0)
    assert np.array_equal(y[:, 0], y[:, 1])


def test_the_dampers_stop_a_note_within_a_fifth_of_a_second():
    for name in ("epiano", "epiano-reed"):
        for m in (40, 60):
            y = mono(render(name, [Note("x", 0.1, 1.0, float(m), 0.7)], 1.6, **PLAIN))
            assert rms_db(y, 0.9, 1.1) - rms_db(y, 1.3, 1.4) > 40.0, (name, m)


def test_a_reed_rings_four_seconds_at_c3_and_one_at_c6():
    for m, want in ((48, 4.0), (84, 1.0)):
        y = mono(render("epiano-reed", [Note("x", 0.1, 3.0, float(m), 0.3)], 3.1, **PLAIN))
        got = decay_t60(y, hz(m), 0.3, min(3.0, 0.3 + 0.8 * want))
        assert abs(got / want - 1.0) < 0.15, (m, got)


def test_the_reeds_pickup_gives_odd_and_even_harmonics_and_a_nasal_bark():
    soft = harmonics_db(mono(render("epiano-reed", [Note("x", 0.1, 1.0, 60.0, 0.3)], 1.2, **PLAIN)), hz(60), 0.12, 0.32, 4)
    hard = harmonics_db(mono(render("epiano-reed", [Note("x", 0.1, 1.0, 60.0, 0.9)], 1.2, **PLAIN)), hz(60), 0.12, 0.32, 4)
    assert soft[1] < -13.0 and soft[2] < -28.0  # nearly pure when played softly
    assert hard[1] > -7.0 and hard[2] > -14.0 and hard[3] > -20.0  # both kinds, strong, when played hard


def test_the_reed_pianos_tremolo_swings_its_level_at_five_and_a_half_to_six_and_a_half_hertz():
    notes = [Note("x", 0.1, 2.9, 60.0, 0.6)]
    dry = render("epiano-reed", notes, 3.0, ornament=0.0)
    for ornament in (0.5, 1.0):
        wet = render("epiano-reed", notes, 3.0, ornament=ornament)
        live = np.abs(dry) > 0.05 * np.max(np.abs(dry))
        live[: int(0.2 * SR)] = False
        gain = wet[live] / dry[live]
        assert abs((gain.max() - gain.min()) - 0.7 * ornament) < 0.03  # as deep as ornament asks
        g = gain - 0.5 * (gain.max() + gain.min())
        assert 5.45 < crossing_rate(g, np.flatnonzero(live) / SR) < 6.55


def test_each_machine_has_its_own_piano_and_a_rendition_replays_exactly():
    notes = [Note("x", 0.1, 0.8, 60.0, 0.7), Note("x", 0.1, 0.8, 64.0, 0.6), Note("x", 0.5, 0.6, 67.0, 0.8)]
    for name in ("epiano", "epiano-reed"):
        a = render(name, notes, 1.5)
        assert np.array_equal(a, render(name, notes, 1.5))
        assert not np.allclose(a, render(name, notes, 1.5, maker=1))
