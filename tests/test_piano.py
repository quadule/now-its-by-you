"""The piano, measured against what real pianos do."""

import numpy as np
import pytest
from scipy.signal import butter, sosfiltfilt

from songbird.score import Note
from songbird.synth import piano

SR = 44100
SET = dict(brightness=0.5, wear=0.0, ornament=0.5, body=1.0, maker=0, tonic=62)


def play(notes, secs, settings=None, seed=0, maker=7):
    return piano.render("piano", tuple(notes), SR, int(secs * SR), np.random.default_rng(seed),
                        np.random.default_rng(maker), {**SET, **(settings or {})})


def one(m, dur=1.0, vel=0.6, secs=None, art="", **settings):
    return play([Note("piano", 0.05, dur, float(m), vel, art=art)], secs or dur + 0.5, settings).mean(axis=1)


def peak_hz(y, guess, t0, t1, width=0.03):
    seg = y[int(t0 * SR): int(t1 * SR)]
    seg = seg * np.hanning(len(seg))
    spec = np.abs(np.fft.rfft(seg, 16 * SR))
    freqs = np.fft.rfftfreq(16 * SR, 1 / SR)
    band = (freqs > guess * (1 - width)) & (freqs < guess * (1 + width))
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


def cents(a, b):
    return 1200 * np.log2(a / b)


def rms_db(y, t0, t1):
    return 20 * np.log10(np.sqrt(np.mean(y[int(t0 * SR): int(t1 * SR)] ** 2)) + 1e-30)


def above_db(y, hz):
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    freqs = np.fft.rfftfreq(len(y), 1 / SR)
    return 10 * np.log10(spec[freqs > hz].sum() / spec.sum())


REF = piano.Piano(SR, np.random.default_rng(7), SET)


@pytest.mark.parametrize("m", [33, 48, 60, 72, 84, 96])
def test_each_key_sounds_its_stretched_fundamental(m):
    target = REF.fundamental[m - piano.LOW]
    y = one(m, dur=2.5)
    assert abs(cents(peak_hz(y, target, 0.3, 2.3), target)) < 2.0


def test_the_stretch_is_railsbacks():
    stretch = {m: cents(REF.fundamental[m - piano.LOW], 440 * 2 ** ((m - 69) / 12)) for m in (21, 48, 60, 84, 96, 108)}
    assert all(abs(stretch[m]) < 1.0 for m in (48, 60, 84))  # the maker's own error only, 0.25 cents
    assert 4.0 < stretch[96] < 16.0 and 20.0 < stretch[108] < 50.0 and -15.0 < stretch[21] < -3.0


def test_partials_are_stretched_as_a_stiff_string_s():
    m = 48
    b = REF.inharmonicity(m)
    f1 = REF.fundamental[m - piano.LOW]
    y = one(m, dur=3.0, vel=0.8)
    for n in (2, 3, 5, 7, 10):
        expected = n * f1 * np.sqrt((1 + b * n * n) / (1 + b))
        assert abs(cents(peak_hz(y, expected, 0.1, 1.6, width=0.01), expected)) < 1.0


def test_the_hammer_is_on_the_string_as_long_as_a_real_ones():
    def contact(m, vel):
        p = REF
        n = piano.strings_for(m)
        f0 = p.fundamental[m - piano.LOW]
        x0 = piano._interp(m, piano.STRIKE_TABLE)
        fs = 4 * SR
        f = piano.hammer_force(0.35 * (5.5 / 0.35) ** vel, piano._log_interp(m, piano.MASS_TABLE) * n,
                               piano._log_interp(m, piano.K_TABLE) * p.hardness * n, piano._interp(m, piano.P_TABLE),
                               piano._log_interp(m, piano.Z_TABLE) * n, x0 / f0 * fs, (1 - x0) / f0 * fs, 0.98,
                               float(fs), 0.03)
        on = np.flatnonzero(f > 0)
        return (on[-1] - on[0]) / fs * 1000, f.max()

    assert 2.5 < contact(60, 0.2)[0] < 4.5 and 1.6 < contact(60, 1.0)[0] < 2.5  # C4: about 4 ms pp, 2 ff
    assert contact(36, 0.6)[0] > 3.0 and contact(96, 0.6)[0] < 1.5  # longer in the bass, short at the top
    assert 30.0 < contact(60, 1.0)[1] < 150.0  # tens of newtons at ff


def test_a_held_note_has_a_prompt_sound_and_an_aftersound():
    f0 = REF.fundamental[60 - piano.LOW]
    y = one(60, dur=12.0, secs=12.3)
    band = sosfiltfilt(butter(2, [f0 * 0.97, f0 * 1.03], btype="bandpass", fs=SR, output="sos"), y)
    hop = SR // 20
    env = 20 * np.log10(np.sqrt(np.convolve(band ** 2, np.ones(hop) / hop, mode="valid"))[::hop] + 1e-12)
    t = np.arange(len(env)) / 20

    def slope(a, b):
        sel = (t >= a) & (t < b)
        return np.polyfit(t[sel], env[sel], 1)[0]

    early, late = slope(0.2, 1.2), slope(6.0, 11.5)
    assert -11.0 < early < -6.5  # measured C4s: about 8-10 dB/s at first
    assert late > 1.5 * early  # then more slowly


def test_high_partials_die_within_a_second():
    y = one(60, dur=3.0, vel=0.9)
    hi = sosfiltfilt(butter(4, 3000.0, btype="highpass", fs=SR, output="sos"), y)
    assert rms_db(hi, 1.05, 1.25) < rms_db(hi, 0.06, 0.16) - 40.0


def test_dampers_stop_the_strings_and_the_top_has_none():
    def fall(m):
        y = one(m, dur=1.0, secs=2.0)
        return rms_db(y, 0.95, 1.05) - rms_db(y, 1.25, 1.35)

    assert fall(60) > 30.0  # a mid damper: 30 dB in a fifth of a second
    assert 8.0 < fall(36) < 35.0  # the heavy bass strings take longer
    assert fall(96) < 20.0  # no dampers above F#6: the note rings on at its own rate


def test_a_harder_blow_is_louder_and_much_brighter():
    soft = one(60, vel=0.3)[int(0.05 * SR): int(0.2 * SR)]
    hard = one(60, vel=0.9)[int(0.05 * SR): int(0.2 * SR)]
    assert rms_db(hard, 0, 0.14) - rms_db(soft, 0, 0.14) > 12.0
    assert above_db(hard, 3000.0) - above_db(soft, 3000.0) > 25.0


def test_the_felt_piano_is_dark_and_hard_hammers_bright():
    def top(b):
        return above_db(one(60, brightness=b)[int(0.05 * SR): int(0.2 * SR)], 3000.0)

    assert top(1.0) - top(0.0) > 20.0 and top(0.0) < -50.0


def test_una_corda_is_softer_with_more_of_the_aftersound():
    open_ = one(57, dur=5.0)
    soft = one(57, dur=5.0, art="soft")
    assert rms_db(soft, 0.05, 0.3) < rms_db(open_, 0.05, 0.3) - 2.0
    tail = lambda y: rms_db(y, 3.5, 4.5) - rms_db(y, 0.05, 0.3)  # noqa: E731
    assert tail(soft) > tail(open_) + 1.5


def test_the_pedal_adds_a_halo():
    plain = one(62, dur=3.0, vel=0.7)
    pedalled = one(62, dur=3.0, vel=0.7, art="ped")
    assert rms_db(pedalled, 1.0, 3.0) > rms_db(plain, 1.0, 3.0) + 0.5
    assert abs(rms_db(pedalled, 0.05, 0.15) - rms_db(plain, 0.05, 0.15)) < 0.5  # it builds up, no louder attack


def test_a_key_struck_again_stops_its_last_note():
    once = play([Note("piano", 0.05, 4.0, 60.0, 0.7)], 4.5).mean(axis=1)
    again = play([Note("piano", 0.05, 4.0, 60.0, 0.7), Note("piano", 2.0, 0.5, 60.0, 0.3)], 4.5).mean(axis=1)
    # the soft second blow replaces the loud first one's ring, it doesn't pile on it
    assert rms_db(again, 2.8, 3.2) < rms_db(once, 2.8, 3.2) - 3.0


def test_the_bass_sits_left_and_the_treble_right():
    low = play([Note("piano", 0.05, 1.0, 36.0, 0.6)], 1.5)
    high = play([Note("piano", 0.05, 1.0, 88.0, 0.6)], 1.5)
    balance = lambda y: 10 * np.log10(np.sum(y[:, 0] ** 2) / np.sum(y[:, 1] ** 2))  # noqa: E731
    assert balance(low) > 1.5 and balance(high) < -1.5


def test_each_machine_owns_its_piano():
    a = play([Note("piano", 0.05, 1.0, 60.0, 0.6)], 1.2, maker=1)
    b = play([Note("piano", 0.05, 1.0, 60.0, 0.6)], 1.2, maker=2)
    assert np.array_equal(a, play([Note("piano", 0.05, 1.0, 60.0, 0.6)], 1.2, maker=1))
    assert not np.allclose(a, b)
