"""The tonewheel organ, its rotary speaker and the harmonium, measured against what the real ones do."""

import numpy as np
import pytest
from scipy.signal import butter, hilbert, sosfiltfilt

from songbird.score import Note
from songbird.synth import organ

SR = 44100
PLAIN = dict(wear=0.0, ornament=0.0)


def render(name, notes, secs, seed=0, maker=0, **settings):
    s = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0)
    s.update(settings)
    return organ.render(name, tuple(notes), SR, int(secs * SR), np.random.default_rng([seed, 17, 99]),
                        np.random.default_rng([maker, 29, 99]), s)


def mono(y):
    return y if y.ndim == 1 else y.mean(axis=1)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def peak_hz(y, guess, t0, t1, rel=0.03):
    seg = y[int(t0 * SR): int(t1 * SR)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 16 * SR))
    freqs = np.fft.rfftfreq(16 * SR, 1 / SR)
    band = (freqs > guess * (1 - rel)) & (freqs < guess * (1 + rel))
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


def cents(a, b):
    return 1200 * np.log2(a / b)


def rms_db(y, t0=None, t1=None):
    seg = y if t0 is None else y[int(t0 * SR): int(t1 * SR)]
    return 10 * np.log10(np.mean(seg**2) + 1e-30)


def generator(notes, secs, click=True, seed=1, **settings):
    """The wheels through the contacts and drawbars alone: (drawbars' signal, percussion's signal)."""
    o = organ.Organ(SR, np.random.default_rng(0), {**PLAIN, **settings})
    plan, _ = o.plan(notes)
    return o.generator(plan, int(secs * SR), np.random.default_rng(seed), click=click)


def one(pitch=60, art="008000000", start=0.1, dur=1.0, vel=0.6):
    return Note("x", start, dur, float(pitch), vel, art=art)


# --- the generator ---------------------------------------------------------------------------------


def test_each_drawbar_is_played_by_the_nearest_equal_tempered_wheel():
    """The quints 2 cents flat of pure, the 1 3/5' 14 cents sharp, the octaves exact."""
    pure = (0.5, 1.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0)
    tempered = (0.0, -1.955, 0.0, 0.0, -1.955, 0.0, 13.686, -1.955, 0.0)
    for d in range(9):
        bars = "".join("8" if i == d else "0" for i in range(9))
        main, _ = generator([one(60, bars)], 1.2)
        f = peak_hz(main, hz(60) * pure[d], 0.3, 1.0, 0.02)
        assert abs(cents(f, hz(60) * pure[d]) - tempered[d]) < 0.2, organ.DRAWBARS[d]


def test_a_drawbar_step_is_3_db():
    levels = []
    for n in range(8, 0, -1):
        main, _ = generator([one(60, f"00{n}000000")], 1.2)
        levels.append(rms_db(main, 0.3, 1.0))
    assert np.allclose(np.diff(levels), -3.0, atol=0.1)


def test_the_generator_folds_back_where_it_runs_out_of_wheels():
    assert organ.wheel_for(36, -12) == 36 and organ.wheel_for(47, -12) == 47 and organ.wheel_for(48, -12) == 36
    assert organ.wheel_for(78, 36) == 114 and organ.wheel_for(79, 36) == 103 and organ.wheel_for(96, 36) == 108
    main, _ = generator([one(36, "800000000")], 1.2)  # the 16' of the lowest C: C2, not C1
    assert abs(cents(peak_hz(main, hz(36), 0.3, 1.0), hz(36))) < 0.5
    main, _ = generator([one(96, "000000008")], 1.2)  # the 1' of the top C: C8, not C10
    assert abs(cents(peak_hz(main, hz(108), 0.3, 1.0), hz(108))) < 0.5


def test_the_wheels_run_on_between_notes():
    """A key switches in a wheel wherever it happens to be: two notes on the same key started a whole
    number and a half of wheel periods apart begin in opposite phase, as the wheel never stopped (had its
    phase started afresh with each note, they would begin alike)."""
    f = hz(69)
    gap = (round(0.5 * f) + 0.5) / f
    main, _ = generator([one(69, "008000000", 0.1, 0.2), one(69, "008000000", 0.1 + gap, 0.2)], 1.0, click=False)
    a = main[int(0.15 * SR): int(0.25 * SR)]
    b = main[int((0.15 + gap) * SR): int((0.25 + gap) * SR)]
    assert np.corrcoef(a, b)[0, 1] < -0.99


# --- the key click ----------------------------------------------------------------------------------


def test_the_key_click_is_a_broadband_tick_of_a_few_milliseconds_and_softer_at_release():
    notes = [Note("x", 0.1, 0.5, 60.0, 0.7)]
    clicky, _ = generator(notes, 0.8, click=True, wear=0.25)
    smooth, _ = generator(notes, 0.8, click=False, wear=0.25)
    hp = butter(4, 2000.0, btype="highpass", fs=SR, output="sos")
    high = sosfiltfilt(hp, clicky)
    quiet = sosfiltfilt(hp, smooth)
    steady = rms_db(high, 0.3, 0.5)  # the house sound at C4 has almost nothing above 2 kHz
    assert rms_db(high, 0.1, 0.11) - steady > 20.0  # the click: broadband, far above the tone up there
    assert rms_db(quiet, 0.1, 0.11) - steady < 6.0  # a key without contacts has none
    hop = int(0.0005 * SR)
    env = np.sqrt(np.convolve(high**2, np.ones(hop) / hop, mode="same"))[int(0.09 * SR): int(0.2 * SR)]
    loud = np.flatnonzero(env > 0.1 * env.max())
    assert 0.001 < (loud[-1] - loud[0]) / SR < 0.012  # within 20 dB of its peak for a few milliseconds
    assert rms_db(high, 0.6, 0.61) < rms_db(high, 0.1, 0.11) - 6.0  # the release is the softer click


# --- the scanner ------------------------------------------------------------------------------------


def scanned(mode, f=440.0, secs=3.0):
    x = np.sin(2 * np.pi * f * np.arange(int(secs * SR)) / SR)
    depth = organ.SCANNER_CENTS[mode] / 1731.234 * SR / (4.0 * organ.SCANNER_HZ)
    wet, dry = (1.0, 0.0) if mode[0] == "V" else (0.5, 0.5)
    lp = 1.0 - np.exp(-2.0 * np.pi * 6000.0 / SR)
    return organ._scanner(x, float(SR), np.array([0], dtype=np.int64), np.array([depth]), np.array([wet]),
                          np.array([dry]), 0.1, lp)[int(0.3 * SR):]


def test_the_scanner_swings_the_pitch_8_16_24_cents_at_687_hz():
    f = 440.0
    for mode, want in (("V1", 8.0), ("V2", 16.0), ("V3", 24.0)):
        y = scanned(mode, f)
        inst = np.diff(np.unwrap(np.angle(hilbert(y)))) * SR / (2 * np.pi)
        inst = np.convolve(inst, np.ones(64) / 64, mode="same")[500:-500]
        swing = cents(np.percentile(inst, [2, 98]), f)
        assert abs(swing[0] + want) < 1.0 and abs(swing[1] - want) < 1.0, mode
    # its sidebands, 6.87 Hz either side, and a chorus that beats against the dry signal
    for mode, weakest in (("V3", -8.0), ("C3", -16.0)):
        y = scanned(mode, f)
        spec = np.abs(np.fft.rfft(y * np.hanning(len(y)), 4 * len(y)))
        freqs = np.fft.rfftfreq(4 * len(y), 1 / SR)
        carrier = spec[np.argmin(np.abs(freqs - f))]
        for k in (-1, 1):
            side = spec[np.argmin(np.abs(freqs - (f + k * organ.SCANNER_HZ)))]
            assert 20 * np.log10(side / carrier) > weakest, mode
    env = np.abs(hilbert(scanned("C3", f)))[2000:-2000]
    assert 20 * np.log10(np.percentile(env, 99) / np.percentile(env, 1)) > 1.0


# --- the percussion -----------------------------------------------------------------------------------


def percussion(notes, secs=2.0):
    return generator(notes, secs)[1]


def test_the_percussion_sounds_only_when_every_key_was_up():
    detached = [one(60, "jazz", 0.1, 0.4), one(62, "", 0.6, 0.4), one(64, "", 1.1, 0.4)]
    legato = [one(60, "jazz", 0.1, 0.55), one(62, "", 0.6, 0.55), one(64, "", 1.1, 0.4)]
    for notes, second in ((detached, (-3.0, 3.0)), (legato, (-60.0, -15.0))):
        p = percussion(notes)
        first = rms_db(p, 0.11, 0.15)
        assert second[0] < rms_db(p, 0.61, 0.65) - first < second[1]


def test_the_percussion_is_the_3rd_or_2nd_harmonic_and_dies_fast_or_slow():
    for art, pitch, tau in (("jazz", 79, 0.2), ("chime", 72, 1.0)):
        p = percussion([one(60, art, 0.1, 3.0)], 3.2)
        assert abs(cents(peak_hz(p, hz(pitch), 0.15, 0.8), hz(pitch))) < 1.0
        env = np.sqrt(np.convolve(p**2, np.ones(441) / 441, mode="same"))
        t = np.arange(len(env)) / SR
        sel = (t > 0.2) & (t < min(0.2 + 3 * tau, 2.9))
        got = -1.0 / np.polyfit(t[sel], np.log(env[sel] + 1e-12), 1)[0]
        assert abs(got / tau - 1.0) < 0.1, art


def test_normal_percussion_takes_3_db_from_the_drawbars():
    with_perc, _ = generator([one(60, "jazz")], 1.2)
    without, _ = generator([one(60, "888000000")], 1.2)
    assert abs(rms_db(without, 0.3, 1.0) - rms_db(with_perc, 0.3, 1.0) - 3.0) < 0.3


# --- the whole organ ------------------------------------------------------------------------------------


def test_in_tune_through_the_amplifier_and_rotary_speaker_with_the_vibrato_off():
    for m in (43, 60, 79):
        y = mono(render("organ", [one(m, "jazz", 0.1, 1.4)], 1.6, **PLAIN))
        assert abs(cents(peak_hz(y, hz(m), 0.3, 1.4), hz(m))) < 2.0, m


def test_velocity_is_the_swell_pedal_with_its_loudness_contour():
    chord = [60, 64, 67]
    lo = mono(render("organ", [one(p, "", 0.1, 1.0, 0.3) for p in chord], 1.2))
    hi = mono(render("organ", [one(p, "", 0.1, 1.0, 0.9) for p in chord], 1.2))
    assert rms_db(hi, 0.3, 1.0) - rms_db(lo, 0.3, 1.0) > 10.0

    def tilt(y):
        seg = y[int(0.3 * SR): int(1.0 * SR)]
        return rms_db(sosfiltfilt(butter(4, 1500.0, btype="highpass", fs=SR, output="sos"), seg)) - rms_db(
            sosfiltfilt(butter(4, 500.0, btype="lowpass", fs=SR, output="sos"), seg))

    assert tilt(hi) - tilt(lo) > 2.5  # less treble as the swell closes


def test_the_tubes_are_nearly_clean_at_the_typical_swell_and_growl_wide_open():
    def distortion(art, vel):
        o = organ.Organ(SR, np.random.default_rng(0), {})
        notes = [Note("x", 0.1, 1.5, float(p), vel, art=art) for p in (50, 54, 57, 62)]
        rng = np.random.default_rng(1)
        plan, _ = o.plan(notes)
        main, perc = o.generator(plan, int(2.0 * SR), rng)
        y = organ.expression(o.scanner(main, plan, rng) + perc, SR, o.swell(plan))
        out = organ.tubes(y, organ.registration(art, 0.5).drive)
        seg = slice(int(0.3 * SR), int(1.5 * SR))
        resid = out[seg] - np.dot(out[seg], y[seg]) / np.dot(y[seg], y[seg]) * y[seg]
        return 10 * np.log10(np.mean(resid**2) / np.mean(out[seg] ** 2))

    assert distortion("", 0.6) < -32.0
    assert -24.0 < distortion("full", 1.0) < -12.0


# --- the rotary speaker ------------------------------------------------------------------------------


def through_the_speaker(f, secs, changes, seed=3):
    o = organ.Organ(SR, np.random.default_rng(0), {})
    x = np.sin(2 * np.pi * f * np.arange(int(secs * SR)) / SR)
    return o.speaker(x, changes, 0.0, np.random.default_rng(seed)), o.speeds


def modulation(y, f, t0):
    """(AM depth dB, AM rate Hz, FM depth %) of a sine heard through the speaker, from t0 s on."""
    a = hilbert(y[int(t0 * SR):])
    env = np.convolve(np.abs(a), np.ones(441) / 441, mode="same")[2000:-2000]
    inst = np.diff(np.unwrap(np.angle(a))) * SR / (2 * np.pi)
    inst = np.convolve(inst, np.ones(441) / 441, mode="same")[2000:-2000]
    e = env - env.mean()
    spec = np.abs(np.fft.rfft(e * np.hanning(len(e)), 1 << 20))
    freqs = np.fft.rfftfreq(1 << 20, 1 / SR)
    sel = (freqs > 0.3) & (freqs < 15.0)
    fm = np.percentile(np.abs(inst / f - 1.0), 99) * 100
    return 20 * np.log10(np.percentile(env, 99.5) / np.percentile(env, 0.5)), freqs[sel][np.argmax(spec[sel])], fm


@pytest.mark.parametrize("fast", [True, False])
def test_the_horn_and_drum_turn_at_their_speeds_with_their_doppler_and_beaming(fast):
    secs = 4.0 if fast else 9.0
    for f, rotor, am, fm in ((3000.0, 0, (6.0, 10.5), (0.5, 0.85)), (200.0, 2, (3.0, 6.0), (0.12, 0.3))):
        out, speeds = through_the_speaker(f, secs, [(0.0, fast)])
        speed = speeds[rotor + int(fast)]
        for m in range(2):
            depth, rate, dev = modulation(out[:, m], f, 1.0)
            assert am[0] < depth < am[1], (f, fast, depth)
            assert abs(rate / speed - 1.0) < 0.06, (f, fast, rate, speed)
            if fast:
                assert fm[0] < dev < fm[1], (f, dev)
            else:  # the same radius turning 8 times slower: a small Doppler
                assert dev < 0.2 * fm[1], (f, dev)


def test_the_rotors_spin_up_in_1_and_4_seconds_and_coast_down_more_slowly():
    def doppler_track(f, window):
        out, _ = through_the_speaker(f, 16.0, [(0.0, False), (1.0, True), (8.0, False)])
        inst = np.diff(np.unwrap(np.angle(hilbert(out[:, 0])))) * SR / (2 * np.pi)
        dev = np.abs(np.convolve(inst, np.ones(441) / 441, mode="same") / f - 1.0)
        hop = int(window * SR)
        frames = dev[: len(dev) // hop * hop].reshape(-1, hop).max(axis=1)
        return (np.arange(len(frames)) + 1) * window, frames

    for f, window, up, down in ((3000.0, 0.25, (0.4, 1.6), (1.0, 5.0)), (200.0, 0.4, (2.0, 6.0), (4.0, 8.0))):
        t, dev = doppler_track(f, window)
        top = np.median(dev[(t > 6.0) & (t < 8.0)])
        rise = t[np.argmax((t > 1.0) & (dev > 0.9 * top))] - 1.0
        fall = t[np.argmax((t > 8.0) & (dev < 0.3 * top))] - 8.0
        assert up[0] < rise < up[1], (f, rise)
        assert down[0] < fall < down[1] and fall > rise, (f, fall)


# --- every machine its own ----------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["organ", "harmonium"])
def test_each_machine_has_its_own_and_a_rendition_replays_exactly(name):
    notes = [Note("x", 0.1, 0.8, 60.0, 0.7), Note("x", 0.1, 0.8, 64.0, 0.6), Note("x", 0.5, 0.6, 67.0, 0.8)]
    a = render(name, notes, 1.2)
    assert np.array_equal(a, render(name, notes, 1.2))
    assert not np.allclose(a, render(name, notes, 1.2, maker=1))


# --- the harmonium ---------------------------------------------------------------------------------------


def test_the_harmonium_is_in_tune():
    for m in (45, 65, 86):
        y = mono(render("harmonium", [one(m, "", 0.1, 1.5)], 1.7, **PLAIN))
        assert abs(cents(peak_hz(y, hz(m), 0.4, 1.5), hz(m))) < 2.0, m


def test_the_harmoniums_reeds_speak_in_20_to_60_ms_the_low_ones_slowest():
    times = []
    for m in (41, 65, 89):
        y = mono(render("harmonium", [one(m, "", 0.1, 1.0)], 1.2, **PLAIN))
        b = sosfiltfilt(butter(2, [hz(m) * 0.8, hz(m) * 1.25], btype="bandpass", fs=SR, output="sos"), y)
        hop = int(0.004 * SR)
        env = np.sqrt(np.convolve(b**2, np.ones(hop) / hop, mode="same"))
        steady = np.median(env[int(0.4 * SR): int(0.9 * SR)])
        times.append(np.argmax(env > 0.9 * steady) / SR - 0.1)
    assert all(0.012 < t < 0.065 for t in times) and times[0] > times[1] > times[2], times


def test_the_harmoniums_4ft_comes_in_with_brightness_and_its_celeste_beats():
    def second(b):
        y = mono(render("harmonium", [one(62, "", 0.1, 1.5)], 1.7, wear=0.0, brightness=b))
        seg = y[int(0.4 * SR): int(1.5 * SR)]
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 8 * len(seg)))
        freqs = np.fft.rfftfreq(8 * len(seg), 1 / SR)
        level = [spec[(freqs > hz(62) * (h - 0.2)) & (freqs < hz(62) * (h + 0.2))].max() for h in (1, 2)]
        return 20 * np.log10(level[1] / level[0])

    assert second(1.0) - second(0.0) > 6.0
    y = mono(render("harmonium", [one(57, "", 0.1, 6.0)], 6.2))
    b = sosfiltfilt(butter(2, [hz(57) * 0.9, hz(57) * 1.1], btype="bandpass", fs=SR, output="sos"), y)
    hop = int(0.02 * SR)
    env = 20 * np.log10(np.sqrt(np.convolve(b**2, np.ones(hop) / hop, mode="same"))[int(0.5 * SR): int(6.0 * SR)])
    assert 4.0 < np.percentile(env, 98) - np.percentile(env, 2) < 14.0  # a celeste's slow shimmer


def test_the_harmoniums_swell_opens_slowly():
    y = mono(render("harmonium", [one(57, "swell", 0.1, 3.0)], 3.2, **PLAIN))
    env = np.sqrt(np.convolve(y**2, np.ones(882) / 882, mode="same"))
    assert np.argmax(env > 0.9 * env.max()) / SR - 0.1 > 0.4
