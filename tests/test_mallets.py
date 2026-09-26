"""The mallets measured against the real instruments: modes, decays, the mallet's contact, the motor,
the dampers, tuning, the music box's comb."""

import numpy as np
import pytest
from scipy.signal import butter, hilbert, sosfiltfilt

from songbird.score import Note
from songbird.synth import mallets

SR = 44100
QUIET = dict(brightness=0.5, wear=0.0, ornament=0.0, body=1.0)


def render(name, notes, secs, settings=None, seed=1, maker=2):
    return mallets.render(name, tuple(notes), SR, int(secs * SR), np.random.default_rng(seed),
                          np.random.default_rng(maker), {**QUIET, **(settings or {})})


def one(name, pitch, secs, vel=0.6, art="", dur=None, settings=None, seed=1, maker=2):
    note = Note("x", 0.1, secs if dur is None else dur, float(pitch), vel, art=art)
    return render(name, [note], secs, settings, seed, maker).mean(axis=1)


def peak_hz(y, guess, t0, t1, width=0.03):
    """The strongest peak within `width` of guess, by zero-padded FFT and parabolic interpolation."""
    seg = y[int(t0 * SR): int(t1 * SR)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 20))
    freqs = np.fft.rfftfreq(1 << 20, 1 / SR)
    band = (freqs > guess * (1 - width)) & (freqs < guess * (1 + width))
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


def envelope_db(y, f, hop=0.005, width=0.07):
    band = sosfiltfilt(butter(2, [f * (1 - width), f * (1 + width)], btype="bandpass", fs=SR, output="sos"), y)
    n = int(hop * SR)
    return 20 * np.log10(np.sqrt(np.convolve(band**2, np.ones(n) / n, mode="same"))[::n] + 1e-20)


def t60(y, f, lo=5.0, hi=30.0, hop=0.005):
    db = envelope_db(y, f, hop)
    k = int(np.argmax(db))
    idx = np.flatnonzero((db[k:] < db[k] - lo) & (db[k:] > db[k] - hi)) + k
    return -60.0 / np.polyfit(idx * hop, db[idx], 1)[0]


def cents(a, b):
    return 1200 * np.log2(a / b)


# --- the bars' and the comb's modes ------------------------------------------------------------------


@pytest.mark.parametrize("name,pitch,expected,t1", [
    ("marimba", 60, (4.0, 10.0), 0.15),  # undercut to 1:4:10
    ("vibraphone", 65, (4.0, 10.0), 0.4),
    ("glockenspiel", 79, (2.737, 5.311), 0.4),  # a thick steel bar, a little under 2.756 and 5.404
    ("music-box", 96, (6.267,), 0.3),  # a plain cantilever
])
def test_partials_sit_where_the_bars_modes_are(name, pitch, expected, t1):
    y = one(name, pitch, 1.0, vel=0.9, settings=dict(brightness=0.9))
    f1 = peak_hz(y, mallets._hz(pitch), 0.12, 0.8)
    for ratio in expected:
        measured = peak_hz(y, f1 * ratio, 0.102, t1) / f1
        assert abs(measured / ratio - 1.0) < 0.005, (name, ratio, measured)


def test_the_model_ratios_are_the_physical_ones():
    # a thin free bar: 1 : 2.756 : 5.404 : 8.933
    bend, _ = mallets.thick_bar(784.0, 1e-5, 0.025)
    assert np.allclose(bend[1:], [2.7565, 5.4039, 8.9330], atol=2e-3)
    # a glockenspiel's short thick bars sit lower, the top ones most
    low, twist_low = mallets.thick_bar(mallets._hz(79), 0.007, 0.025)
    high, twist_high = mallets.thick_bar(mallets._hz(108), 0.007, 0.025)
    assert 2.70 < low[1] < 2.756 and 5.2 < low[2] < 5.404 and high[1] < low[1] and high[2] < low[2]
    assert twist_high[0] < twist_low[0]  # the short bars twist relatively lower
    # a cantilever: βL 1.875, 4.694 (1 : 6.27 : 17.55); a tip mass alone raises the second ratio (10.4 at
    # the tooth's own mass), a rocking lump lowers it to a music box's bass tooth's 4-5
    b = mallets.weighted_tooth(0.0, 0.0)
    assert abs(b[0] - 1.8751) < 1e-3 and abs(b[1] - 4.6941) < 1e-3 and abs((b[2] / b[0]) ** 2 - 17.547) < 0.01
    b = mallets.weighted_tooth(1.0, 0.0)
    assert abs(b[0] - 1.2479) < 1e-3 and abs((b[1] / b[0]) ** 2 - 10.43) < 0.05
    for m in (72, 76, 80):
        ratios, _ = mallets.tooth(m)
        assert 4.0 < ratios[1] < 5.0
    assert abs(mallets.tooth(96)[0][1] - 6.267) < 1e-3


def test_a_weighted_bass_tooth_sounds_its_low_second_mode():
    y = one("music-box", 74, 1.5, vel=0.9)
    f1 = peak_hz(y, mallets._hz(74), 0.2, 1.2)
    ratio = mallets.tooth(74)[0][1]
    assert abs(peak_hz(y, f1 * ratio, 0.102, 0.5) / (f1 * ratio) - 1.0) < 0.005


# --- decays ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("name,pitch,lo,hi,secs", [
    ("marimba", 45, 1.5, 2.1, 5.0),  # low bars 1.5-2 s
    ("marimba", 96, 0.25, 0.35, 1.5),  # high ~0.3 s
    ("vibraphone", 53, 8.0, 15.0, 8.0),  # undamped 8-15 s low
    ("vibraphone", 89, 3.0, 6.0, 4.0),  # 3-6 s high
    ("glockenspiel", 79, 3.0, 5.2, 4.0),
    ("glockenspiel", 108, 2.8, 5.0, 3.0),
    ("celesta", 60, 1.0, 2.1, 2.5),
    ("celesta", 108, 0.9, 2.0, 1.5),
    ("music-box", 72, 2.0, 4.2, 4.0),
    ("music-box", 108, 1.8, 4.0, 2.5),
])
def test_the_fundamental_rings_as_long_as_the_real_ones(name, pitch, lo, hi, secs):
    y = one(name, pitch, secs, art="ped" if name == "celesta" else "")
    assert lo < t60(y, mallets._hz(pitch)) < hi


def test_upper_partials_die_first_and_the_resonator_blooms():
    y = one("marimba", 58, 2.0, vel=0.8)
    f1 = mallets._hz(58)
    assert t60(y, 4 * f1) < 0.4 * t60(y, f1)
    # the tube starts at rest: A#3's fundamental keeps growing for tens of milliseconds after the stroke
    db = envelope_db(y, f1, hop=0.002)
    at = lambda t: db[int((0.1 + t) / 0.002)]  # noqa: E731
    assert at(0.06) > at(0.01) + 3.0
    # the resonator's two coupled modes: at exact tuning the slow one rings the table's T60, and the
    # tube's share starts at nothing
    freqs, t60s, from_bar, from_tube = mallets.resonated(220.0, 1.5, 1.6, 0.3, 0.0, 20.0)
    assert abs(max(t60s) - 1.5) < 0.01 and abs(from_tube.sum()) < 1e-9 and abs(from_bar.sum() - 1.0) < 1e-9


# --- the mallet ------------------------------------------------------------------------------------


def test_harder_is_shorter_and_its_spectrum_reaches_higher():
    mallet = mallets.MARIMBA.mallet
    soft, tau_soft = mallets.pulse(mallet, 60.0, 0.3, 0.5, SR, 20.0)
    hard, tau_hard = mallets.pulse(mallet, 60.0, 0.9, 0.5, SR, 20.0)
    assert tau_hard < 0.6 * tau_soft and abs(soft.sum() - 1) < 1e-9 and abs(hard.sum() - 1) < 1e-9
    assert 2.5e-3 < mallets.pulse(mallet, 60.0, 0.6, 0.5, SR, 20.0)[1] < 4.5e-3  # yarn: 3-6 ms low, 1-2 high

    def level(force, f):
        t = np.arange(len(force)) / SR
        return 20 * np.log10(abs(np.sum(force * np.exp(-2j * np.pi * f * t))))

    # flat below the knee near 1/2τ (where the pulse, (t/b)^a e^(-t/b), is 3(a + 1) dB down), then falling at
    # least 12 dB an octave
    knee = 1.0 / (2.0 * tau_soft)
    assert level(soft, knee / 4) > -1.5 and -9.0 < level(soft, knee) < -4.0
    assert level(soft, 8 * knee) - level(soft, 4 * knee) < -12.0
    # the hard stroke reaches 2 kHz 20 dB better
    assert level(hard, 2000.0) - level(soft, 2000.0) > 20.0
    # a harder mallet (brightness) is a shorter contact
    assert mallets.pulse(mallet, 60.0, 0.6, 1.0, SR, 20.0)[1] < 0.7 * mallets.pulse(mallet, 60.0, 0.6, 0.5, SR, 20.0)[1]


@pytest.mark.parametrize("name,pitch,ratio", [("marimba", 62, 4.0), ("vibraphone", 65, 4.0),
                                               ("celesta", 72, 2.75)])
def test_a_harder_stroke_brings_up_the_upper_partials(name, pitch, ratio):
    def relative(vel):
        y = one(name, pitch, 0.5, vel=vel)
        seg = y[int(0.1 * SR): int(0.14 * SR)]
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16))
        freqs = np.fft.rfftfreq(1 << 16, 1 / SR)
        f1 = mallets._hz(pitch)
        up = spec[(freqs > f1 * ratio * 0.97) & (freqs < f1 * ratio * 1.03)].max()
        return 20 * np.log10(up / spec[(freqs > f1 * 0.97) & (freqs < f1 * 1.03)].max())

    assert relative(0.9) - relative(0.3) > 5.0


def test_no_click_while_the_mallet_touches():
    """A soft, long contact under a high bar leaves the modes' push-and-give-back, not a spike: every stroke's
    peak stays within a few times its ring (the marimba's top rings 0.3 s: its natural crest is about 5)."""
    for name in mallets.SPEC:
        lo, hi = mallets.SPEC[name]["register"]
        for pitch in (lo, hi):
            for vel in (0.05, 1.0):
                y = one(name, pitch, 0.5, vel=vel)
                ring = np.sqrt(np.mean(y[int(0.12 * SR): int(0.3 * SR)] ** 2))
                assert np.max(np.abs(y)) < 7.0 * ring, (name, pitch, vel)


# --- the vibraphone's motor and the dampers ------------------------------------------------------


def tremolo(y, f):
    band = sosfiltfilt(butter(2, [f * 0.9, f * 1.1], btype="bandpass", fs=SR, output="sos"), y)
    a = hilbert(band)[int(1.5 * SR): int(3.5 * SR)]
    db = 20 * np.log10(np.abs(a))
    t = np.arange(len(db)) / SR
    db = db - np.polyval(np.polyfit(t, db, 1), t)
    spec = np.abs(np.fft.rfft(db - db.mean(), 1 << 20))
    freqs = np.fft.rfftfreq(1 << 20, 1 / SR)
    band_ = (freqs > 1.0) & (freqs < 15.0)
    inst = np.convolve(np.diff(np.unwrap(np.angle(a))) * SR / (2 * np.pi), np.ones(882) / 882, mode="valid")
    swing = cents(inst, f)
    return (freqs[band_][np.argmax(spec[band_])], np.percentile(db, 98) - np.percentile(db, 2),
            np.percentile(swing, 98) - np.percentile(swing, 2))


def test_the_motor_makes_a_tremolo_of_6_to_12_db_at_3_to_7_hz():
    f = mallets._hz(65)
    kit = mallets.Kit(mallets.VIBRAPHONE, np.random.default_rng(2), dict(QUIET, ornament=0.5))
    y = one("vibraphone", 65, 4.0, settings=dict(ornament=0.5))
    rate, depth, pitch = tremolo(y, f)
    assert abs(rate / ((2.5 + 4.0 * 0.5) * kit.motor_rate) - 1.0) < 0.03
    assert 6.0 < depth < 12.0 and 2.0 < pitch < 8.0  # and a couple of cents of pitch, either way
    for art, hz in (("motor-slow", 3.5), ("motor-fast", 6.5)):
        rate, depth, _ = tremolo(one("vibraphone", 65, 4.0, art=art), f)
        assert abs(rate / (hz * kit.motor_rate) - 1.0) < 0.03 and 6.0 < depth < 12.0
    _, depth, pitch = tremolo(one("vibraphone", 65, 4.0), f)  # ornament 0: the motor is off
    assert depth < 1.0 and pitch < 0.5
    _, shallow, _ = tremolo(one("vibraphone", 65, 4.0, settings=dict(ornament=0.1)), f)
    assert 1.5 < shallow < 7.0  # a little ornament, a little tremolo: no flip from off to full


def test_the_motor_is_one_shaft_for_the_whole_part():
    kit = mallets.Kit(mallets.VIBRAPHONE, np.random.default_rng(2), dict(QUIET, ornament=0.5))
    notes = [Note("x", 0.5, 0.5, 65.0, 0.6), Note("x", 2.0, 0.5, 69.0, 0.6, art="motor-fast")]
    phase, engaged, rate = mallets._motor_track(notes, SR, 4 * SR, kit)
    step = np.diff(phase)
    assert np.all(step >= 0) and np.max(np.abs(np.diff(step))) < 1e-5  # no jumps: the discs keep turning
    assert abs(rate[int(1.5 * SR)] - 4.5 * kit.motor_rate) < 0.01
    assert abs(rate[int(3.9 * SR)] - 6.5 * kit.motor_rate) < 0.05
    phase_again, _, _ = mallets._motor_track(notes[:1], SR, 4 * SR, kit)
    assert np.allclose(phase[: 2 * SR], phase_again[: 2 * SR])  # later notes don't move earlier phase


@pytest.mark.parametrize("name,pitch,art,lo,hi", [
    ("vibraphone", 65, "", 0.08, 0.25),  # the pedal's damper, T60 ~0.1-0.2 s
    ("celesta", 72, "", 0.08, 0.3),
    ("glockenspiel", 88, "choke", 0.03, 0.15),
])
def test_the_damper_stops_a_note_at_its_end(name, pitch, art, lo, hi):
    f = mallets._hz(pitch)
    y = one(name, pitch, 1.5, art=art, dur=0.5)
    db = envelope_db(y, f, hop=0.002)
    k = int((0.1 + 0.52) / 0.002)  # once the felt has settled
    idx = np.flatnonzero(db[k:] > db[k] - 40.0)
    idx = k + idx[: np.argmax(np.diff(idx) > 1) + 1] if np.any(np.diff(idx) > 1) else k + idx
    fall = -np.polyfit(idx * 0.002, db[idx], 1)[0]  # dB a second
    assert lo < 60.0 / fall < hi


def test_the_pedal_and_a_free_bar_ring_on():
    f = mallets._hz(72)
    held = envelope_db(one("celesta", 72, 1.5, art="ped", dur=0.5), f)
    stopped = envelope_db(one("celesta", 72, 1.5, dur=0.5), f)
    assert held[int(1.0 / 0.005)] - stopped[int(1.0 / 0.005)] > 40.0
    glock = envelope_db(one("glockenspiel", 88, 1.5, dur=0.2), mallets._hz(88))
    assert glock[int(0.2 / 0.005)] - glock[int(1.0 / 0.005)] < 15.0  # no damper: the written length is moot


def test_a_dead_stroke_is_short_and_a_roll_keeps_going():
    for name, pitch in (("marimba", 60), ("vibraphone", 65)):
        db = envelope_db(one(name, pitch, 1.0, art="dead"), mallets._hz(pitch))
        k = int(np.argmax(db))
        assert np.flatnonzero(db[k:] < db[k] - 40.0)[0] * 0.005 < 0.2
    strokes = mallets._strokes("marimba", mallets.MARIMBA, [Note("x", 0.1, 2.0, 72.0, 0.6, art="roll")],
                               np.random.default_rng(1))
    rate = 1.0 / np.mean(np.diff([s.start for s in strokes]))
    assert 10.0 < rate < 16.0 and len({s.hand for s in strokes}) == 2
    y = one("marimba", 72, 3.0, art="roll", dur=2.0)
    hop = int(0.05 * SR)
    env = np.sqrt(np.convolve(y**2, np.ones(hop) / hop, mode="same"))
    early, late = np.median(env[int(0.3 * SR): int(0.8 * SR)]), np.median(env[int(1.4 * SR): int(2.0 * SR)])
    assert 0.5 < late / early < 2.0 and env[int(2.8 * SR)] < 0.1 * late  # it holds, then stops


# --- tuning, wear and makers -------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(mallets.SPEC))
def test_in_tune_within_2_cents_at_wear_0_across_the_compass(name):
    lo, hi = mallets.SPEC[name]["register"]
    for pitch in np.linspace(lo, hi, 5).round():
        y = one(name, pitch, 1.3)
        assert abs(cents(peak_hz(y, mallets._hz(pitch), 0.3, 1.2), mallets._hz(pitch))) < 2.0, pitch


def test_wear_pulls_bars_off_pitch_and_makers_differ():
    worn = [abs(cents(peak_hz(one("marimba", p, 1.3, settings=dict(wear=1.0)), mallets._hz(p), 0.3, 1.2),
                      mallets._hz(p))) for p in range(60, 72)]
    assert max(worn) > 4.0
    a = one("vibraphone", 65, 1.0, maker=2)
    b = one("vibraphone", 65, 1.0, maker=3)
    assert not np.allclose(a, b)
    assert np.array_equal(one("vibraphone", 65, 1.0, maker=2), a)


def test_loose_bars_buzz_only_when_worn():
    kit = mallets.Kit(mallets.MARIMBA, np.random.default_rng([0, 29, 99]), dict(wear=1.0))
    loose = [k for k in range(45, 97) if kit.loose[k] > 0]
    assert 0 < len(loose) < 8  # a few bars, the machine's own
    buzz = mallets._rattle(mallets._hz(loose[0]), 1.0, int(0.08 * SR), SR, np.random.default_rng(0))
    spec = np.abs(np.fft.rfft(buzz))
    freqs = np.fft.rfftfreq(len(buzz), 1 / SR)
    assert np.sum(spec[(freqs > 1000) & (freqs < 6000)] ** 2) > 0.5 * np.sum(spec**2)  # a bright buzz


# --- the music box ---------------------------------------------------------------------------------


def test_a_tooth_plucked_again_is_stopped_with_a_buzz():
    pitch = 76
    f = mallets._hz(pitch)
    once = render("music-box", [Note("x", 0.1, 0.3, float(pitch), 0.6)], 1.5).mean(axis=1)
    twice = render("music-box", [Note("x", 0.1, 0.3, float(pitch), 0.6), Note("x", 0.4, 0.3, float(pitch), 0.6)],
                   1.5).mean(axis=1)
    second = render("music-box", [Note("x", 0.4, 0.3, float(pitch), 0.6)], 1.5).mean(axis=1)

    def harmonics(y):
        seg = y[int(0.37 * SR): int(0.4 * SR)] * np.hanning(int(0.4 * SR) - int(0.37 * SR))
        spec = np.abs(np.fft.rfft(seg, 1 << 18))
        freqs = np.fft.rfftfreq(1 << 18, 1 / SR)
        h = [spec[(freqs > k * f * 0.97) & (freqs < k * f * 1.03)].max() for k in (1, 2, 3)]
        return 20 * np.log10(max(h[1], h[2]) / h[0])

    assert harmonics(twice) > harmonics(once) + 30.0  # the damper slapping the swing: a buzz
    tail = lambda y: np.sqrt(np.mean(y[int(0.6 * SR): int(1.2 * SR)] ** 2))  # noqa: E731
    assert abs(20 * np.log10(tail(twice) / tail(second))) < 0.2  # the old ring is gone


def test_the_box_is_small_narrow_and_ticks():
    y = render("music-box", [Note("x", 0.1, 1.0, 84.0, 0.6)], 1.2)
    assert 0.6 < np.corrcoef(y[:, 0], y[:, 1])[0, 1] < 0.98  # two microphones, close together
    spec = np.abs(np.fft.rfft(y.mean(axis=1)))
    freqs = np.fft.rfftfreq(len(y), 1 / SR)
    assert np.sum(spec[freqs < 250] ** 2) < 1e-4 * np.sum(spec**2)  # little below the box's panels
    loud = render("music-box", [Note("x", 0.1, 1.0, 84.0, 1.0)], 0.5).mean(axis=1)
    soft = render("music-box", [Note("x", 0.1, 1.0, 84.0, 0.2)], 0.5).mean(axis=1)
    assert 0.0 < 20 * np.log10(np.std(loud) / np.std(soft)) < 5.0  # the pins pluck almost alike


def test_every_articulation_and_the_contract():
    for name, spec in mallets.SPEC.items():
        lo, hi = spec["register"]
        notes = [Note("x", 0.1 + 0.2 * i, 0.3, float((lo + hi) // 2), 0.6, art=a)
                 for i, a in enumerate(list(spec["articulations"]) + ["dead+motor-fast"])]
        a = render(name, notes, 3.0)
        b = render(name, notes, 3.0)
        assert a.shape == (3 * SR, 2) and np.all(np.isfinite(a)) and np.array_equal(a, b)
        assert np.max(np.abs(a[: int(0.095 * SR)])) < 1e-12 * np.max(np.abs(a))  # nothing before the first
    with pytest.raises(ValueError):
        render("xylophone", [], 0.1)
    for name in mallets.SPEC:  # nothing to play, or nowhere to play it
        assert not np.any(render(name, [], 0.5)) and render(name, [Note("x", 0.1, 0.5, 72.0, 0.6)], 0.0).shape == (0, 2)
