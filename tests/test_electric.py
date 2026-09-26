"""The electric guitar through its amp, and the electric bass through its DI, measured as real ones are."""

import sys
import time
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import butter, hilbert, sosfiltfilt

from songbird.score import Note
from songbird.synth import electric, fretboard, master
from songbird.theory import midi_to_hz

sys.path.insert(0, str(Path(__file__).parent))
from _levels_b import TARGETS, loudness  # noqa: E402

SR = 44100
S0 = dict(brightness=0.5, wear=0.0, ornament=0.5, body=1.0, maker=0, tonic=62)


def render(name, notes, seconds, **settings):
    return electric.render(name, tuple(notes), SR, int(seconds * SR), np.random.default_rng(3),
                           np.random.default_rng(4), {**S0, **settings})


def mono(y):
    return y.mean(axis=1) if y.ndim == 2 else y


def note(pitch, start=0.1, dur=2.5, vel=0.6, art="", part="electric"):
    return Note(part, start, dur, float(pitch), vel, art=art)


def cents_of(y, pitch, t0, t1):
    """The strongest peak within 3% of the pitch, by zero-padded FFT and parabolic interpolation, in cents."""
    f = midi_to_hz(pitch)
    seg = y[int(t0 * SR): int(t1 * SR)]
    seg = seg * np.hanning(len(seg))
    spec = np.abs(np.fft.rfft(seg, 16 * SR))
    freqs = np.fft.rfftfreq(16 * SR, 1 / SR)
    band = (freqs > f * 0.97) & (freqs < f * 1.03)
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return 1200 * np.log2((freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])) / f)


def centroid(y, t0, t1):
    seg = y[int(t0 * SR): int(t1 * SR)]
    p = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    return float(np.sum(f * p) / np.sum(p))


def fall_time(y, db=30.0):
    """Seconds from the loudest moment until 10 ms windows stay db under it."""
    e = 20 * np.log10(np.sqrt(np.convolve(y**2, np.ones(441) / 441, mode="same")) + 1e-12)
    pk = int(np.argmax(e))
    below = np.flatnonzero(e[pk:] < e[pk] - db)
    return below[0] / SR if len(below) else np.inf


def t60(y, f, t0, t1):
    band = sosfiltfilt(butter(2, [f * 0.9, f * 1.1], btype="bandpass", fs=SR, output="sos"), y)
    hop = SR // 20
    env = 20 * np.log10(np.sqrt(np.convolve(band**2, np.ones(hop) / hop, mode="valid"))[::hop] + 1e-12)
    x = np.arange(len(env)) / 20
    sel = (x >= t0) & (x <= t1)
    return -60 / np.polyfit(x[sel], env[sel], 1)[0]


def pickup(pitch, string, fret, seconds=4.0, **settings):
    """What the pickup alone hears of one note (no amp): its voltage."""
    s = {**S0, **settings}
    strings, coil, circuit, _ = electric.rig("electric", s, SR)
    placed = [(note(pitch, dur=seconds - 0.3), string, fret)]
    segs = fretboard.segments(placed, strings, SR, np.random.default_rng(1))
    return electric._pickup_voltage(segs, strings, coil, circuit, SR, int(seconds * SR), np.random.default_rng(1))


# --- the guitar ------------------------------------------------------------------------------------


@pytest.mark.parametrize("pitch", [40, 52, 64, 76, 88])
def test_the_guitar_is_in_tune_up_the_neck(pitch):
    y = mono(render("electric", [note(pitch)], 3.0))
    assert abs(cents_of(y, pitch, 0.8, 2.4)) < 2.0


@pytest.mark.parametrize("art", ["bend", "slide", "hammer", "pull"])
def test_it_arrives_in_tune_after_a_bend_a_slide_and_legato(art):
    notes = [note(57, dur=0.5), note(59 if art != "pull" else 55, start=0.6, dur=2.0, art=art)]
    y = mono(render("electric", notes, 3.0))
    assert abs(cents_of(y, notes[1].pitch, 1.2, 2.5)) < 2.0


def test_a_solid_body_sustains_and_its_partials_die_by_their_frequency():
    """A solid body takes little from its strings: the open A's fundamental rings 6 to 14 s, a high E's 3 to
    8 s; each partial loses b3 f^2 more, so the A's 10th partial (1.1 kHz) is gone in under half the time."""
    a2 = pickup(45, 1, 0, 5.0)
    e4 = pickup(64, 5, 0, 5.0)
    fund = t60(a2, 110.0, 0.5, 4.0)
    assert 6.0 < fund < 14.0 and 3.0 < t60(e4, 329.6, 0.5, 4.0) < 8.0
    assert t60(a2, 1100.0, 0.2, 1.5) < 0.5 * fund


def test_the_pickup_hears_its_place_on_the_string():
    """The neck single coil sits a quarter of the scale from the bridge, so the open A's 4th harmonic is
    notched out; at the 12th fret the string is half as long and the notch falls to the 2nd harmonic (the
    neck pickup's hollow high notes). The bridge pickup, 7% along, keeps the 2nd to 5th strong."""
    maker = next(m for m in range(20) if not electric.built(m)["humbucker"])

    def harmonics(y, f):
        seg = y[int(0.2 * SR): int(1.2 * SR)] * np.hanning(SR)
        p = np.abs(np.fft.rfft(seg, 1 << 18))
        fr = np.fft.rfftfreq(1 << 18, 1 / SR)
        lv = np.array([p[np.abs(fr - f * h) < 0.03 * f].max() for h in range(1, 7)])
        return 20 * np.log10(lv / lv[0])

    neck = harmonics(pickup(45, 1, 0, 1.5, maker=maker, brightness=0.0), 110.0)
    high = harmonics(pickup(57, 1, 12, 1.5, maker=maker, brightness=0.0), 220.0)
    bridge = harmonics(pickup(45, 1, 0, 1.5, maker=maker, brightness=1.0), 110.0)
    assert neck[3] < min(neck[2], neck[4]) - 8 and neck[3] < -20
    assert high[1] < -20
    assert np.all(bridge[1:5] > -10)


def test_the_tone_knob_sits_near_the_top_and_the_coil_sings():
    """At a middling brightness the player's tone knob is near the top, so the coil's resonance with the pots
    and cable stands up as Zollner measures it: a single coil's 3 dB and more at 3-6 kHz, a humbucker's 4 dB
    and more at 2.5-4 kHz; turned toward the bridge it is sharper still."""
    from songbird.synth import amp

    for maker in range(8):
        d = electric.built(maker)
        for bright in (0.5, 1.0):
            chosen, _, coil, circuit = electric.pickups(d, bright, "clean")
            f, height, q = amp.resonance(*amp.pickup_ba(coil, **circuit))
            if d["humbucker"]:
                assert 2500 < f < 4000 and height > 4.0
            else:
                assert 3000 < f < 6000 and height > 2.5
            if bright == 1.0:
                assert height > 5.0 and q > 1.4


def test_every_makers_cabinet_is_a_close_miked_open_back_combo():
    """Its cone's resonance standing as a hump over what the open back cancels below it, 100 Hz within a few
    dB of the middle (it was 10 dB under on some makers, with no hump on any), a presence rise at 2-4 kHz
    within 10 dB, and the fall past 5-6 kHz; the reflections the microphones also hear 12-20 dB down."""
    from songbird.synth import amp

    n = 1 << 15
    f = np.fft.rfftfreq(n, 1 / SR)

    def at(h, x, frac=1 / 6):
        sel = (f > x / 2 ** (frac / 2)) & (f < x * 2 ** (frac / 2))
        return 10 * np.log10(np.mean(10 ** (h[sel] / 10)))

    for maker in range(20):
        cab = electric.built(maker)["cabinet"]
        h = 20 * np.log10(np.abs(np.fft.rfft(amp.cabinet_ir(cab, SR)[:, 0], n)) + 1e-12)  # 0 dB: 200 Hz-4 kHz
        mid = at(h, 1000, 1 / 3)
        assert -4.0 < at(h, 100) < 3.0 and at(h, cab.fs) > at(h, 200) - 1.0 and at(h, 50) < at(h, 100) - 6.0
        assert 0.0 < max(at(h, x, 1 / 3) for x in (2000, 2500, 3150, 4000)) - mid < 10.0
        assert at(h, 10000, 1 / 3) < mid - 8.0
        assert all(level <= 0.25 for _, level, _ in cab.mics)


def repeated(name, vel, strums=12):
    return [note(p, start=0.1 + 0.3 * k, dur=0.3, vel=vel, art="down" if k % 2 == 0 else "up", part=name)
            for k in range(strums) for p in (45, 52, 57, 61, 64)]


def test_harder_is_louder_and_brighter_and_crunch_compresses():
    clean = [render("electric", repeated("electric", v), 4.2) for v in (0.3, 0.9)]
    crunch = [render("electric-crunch", repeated("electric-crunch", v), 4.2) for v in (0.3, 0.9)]
    rise = master.loudness(clean[1], SR) - master.loudness(clean[0], SR)
    squeezed = master.loudness(crunch[1], SR) - master.loudness(crunch[0], SR)
    assert rise > 6.0 and squeezed < rise - 2.0
    assert centroid(mono(clean[1]), 0.1, 3.5) > centroid(mono(clean[0]), 0.1, 3.5)


def test_crunch_and_tremolo_sit_about_as_loud_as_clean():
    """The amp's master volume: the same playing, whatever the setting, within 2.5 LU."""
    part = repeated("electric", 0.6, 16)
    clean = master.loudness(render("electric", part, 5.5), SR)
    for name in ("electric-crunch", "electric-tremolo"):
        assert abs(master.loudness(render(name, part, 5.5), SR) - clean) < 2.5


def strum_error(maker, name, vel):
    """How far the rig's amp is from linear on its own strummed A chord, dB: the output against the same amp
    played 60 dB quieter and scaled back up (distortion, intermodulation and compression together)."""
    from dataclasses import replace

    from songbird.synth import amp

    strings, coil, circuit, rig_amp = electric.rig(name, {**S0, "maker": maker}, SR)
    rig_amp = replace(rig_amp, reverb=0.0)
    notes = [note(p, dur=1.0, vel=vel, art="down") for p in (45, 52, 57, 61, 64)]
    placed = fretboard.fret(fretboard.strum(notes, np.random.default_rng(0)), strings)
    segs = fretboard.segments(placed, strings, SR, np.random.default_rng(0))
    v = electric._pickup_voltage(segs, strings, coil, circuit, SR, int(1.2 * SR), np.random.default_rng(0))
    chain = amp.Chain(rig_amp, SR, os_=4 if name == "electric-crunch" else 2)
    idle = chain.run(np.zeros_like(v))
    y, lin = chain.run(v) - idle, (chain.run(v * 1e-3) - idle) * 1e3
    return 10 * np.log10(np.sum((y - lin) ** 2) / np.sum(lin**2))


@pytest.mark.parametrize("maker", range(6))
def test_clean_is_clean_and_crunch_crunches_whatever_the_guitar(maker):
    """A player turns the volume to the sound, not to a place on the knob: a hard strum through the clean
    setting stays within 3% of linear, humbucker or single coil, Fender or Marshall; the crunch breaks up
    as much on every rig (12-32% from linear), rather than a hot humbucker into a Marshall's stack fuzzing
    while a single coil into a Fender's barely does."""
    assert strum_error(maker, "electric", 0.9) < -30.0
    assert -18.0 < strum_error(maker, "electric-crunch", 0.6) < -10.0


def test_the_tremolo_is_deep_enough_to_hear():
    """The amp's tremolo as players set it to be heard: its swing 11 to 19 dB, a photocell's dipping fast
    and coming back slowly, a bias tremolo's evenly."""
    from dataclasses import replace

    from songbird.synth import amp

    t = np.arange(3 * SR) / SR
    for maker in range(4):
        *_, rig_amp = electric.rig("electric-tremolo", {**S0, "maker": maker}, SR)
        chain = amp.Chain(replace(rig_amp, reverb=0.0), SR, os_=2)
        y = chain.run(0.1 * np.sin(2 * np.pi * 330.0 * t))
        env = 20 * np.log10(np.sqrt(np.convolve(y**2, np.ones(128) / 128, mode="same"))[int(0.5 * SR): int(2.9 * SR)])
        assert 11.0 < np.percentile(env, 99) - np.percentile(env, 1) < 19.0
        phase = (np.arange(len(env)) / SR * chain.rate) % 1.0
        cycle = np.array([env[(phase >= k / 40) & (phase < (k + 1) / 40)].mean() for k in range(40)])
        top = int(np.argmax(cycle))
        falls = (int(np.argmin(np.roll(cycle, -top))) % 40) / 40  # the part of the cycle from the top to the bottom
        assert (falls < 0.35) if rig_amp.tremolo[0] == "optical" else (0.35 < falls < 0.65)


def test_the_settings_can_ask_for_another_amp_setting():
    part = repeated("electric", 0.6, 4)
    a = render("electric", part, 1.8, amp="crunch")
    b = render("electric-crunch", part, 1.8)
    assert np.allclose(a, b)
    assert not np.allclose(a, render("electric", part, 1.8))


def test_a_palm_mute_chugs_and_a_chop_scratches():
    plain = mono(render("electric", [note(50, dur=1.0, vel=0.7)], 1.5))
    mute = mono(render("electric", [note(50, dur=1.0, vel=0.7, art="mute")], 1.5))
    chop = mono(render("electric", [note(p, dur=1.0, vel=0.7, art="chop") for p in (50, 57, 62)], 1.5))
    assert 0.05 < fall_time(mute) < 0.5 < fall_time(plain)
    assert centroid(mute, 0.12, 0.2) < centroid(plain, 0.12, 0.2)
    assert fall_time(chop) < 0.08


def test_a_strum_crosses_the_strings_and_an_up_stroke_comes_back():
    rng = np.random.default_rng(0)
    down = fretboard.strum([note(p, art="down") for p in (40, 47, 52, 56, 59, 64)], rng)
    up = fretboard.strum([note(p, art="up") for p in (52, 56, 59, 64)], rng)
    assert [n.pitch for n in down] == sorted(n.pitch for n in down)
    assert 0.015 < down[-1].start - down[0].start < 0.045
    assert [n.pitch for n in up] == sorted((n.pitch for n in up), reverse=True)
    spread = [note(p, start=0.1 + 0.01 * k) for k, p in enumerate((40, 47, 52))]
    assert fretboard.strum(spread, rng) == spread  # already spread: left alone


def test_a_finger_vibrato_bends_up_and_back():
    y = mono(render("electric", [note(69, dur=2.5, vel=0.7, art="vibrato")], 3.0))
    f = midi_to_hz(69)
    band = sosfiltfilt(butter(2, [f * 0.9, f * 1.1], btype="bandpass", fs=SR, output="sos"), y)
    inst = np.diff(np.unwrap(np.angle(hilbert(band)))) * SR / (2 * np.pi)
    c = 1200 * np.log2(np.convolve(inst, np.ones(441) / 441, mode="same")[int(1.0 * SR): int(2.4 * SR)] / f)
    spec = np.abs(np.fft.rfft((c - c.mean()) * np.hanning(len(c)), 1 << 18))
    fr = np.fft.rfftfreq(1 << 18, 1 / SR)
    rate = fr[(fr > 2) & (fr < 10)][np.argmax(spec[(fr > 2) & (fr < 10)])]
    assert 5.0 <= rate <= 6.6 and 8.0 < c.max() - c.min() < 35.0 and c.min() > -5.0


def test_the_tremolo_follows_the_tempo():
    chord = [note(p, dur=3.5, art="down", part="electric-tremolo") for p in (50, 57, 62, 66)]
    y = mono(render("electric-tremolo", chord, 4.0, tempo=100.0))
    env = np.sqrt(np.convolve(y**2, np.ones(441) / 441, mode="same"))[int(0.6 * SR): int(3.4 * SR)]
    env = env / np.convolve(env, np.ones(SR // 2) / (SR // 2), mode="same")  # the note's own decay taken out
    spec = np.abs(np.fft.rfft((env - env.mean()) * np.hanning(len(env)), 1 << 20))
    f = np.fft.rfftfreq(1 << 20, 1 / SR)
    band = (f > 3) & (f < 8)
    assert abs(f[band][np.argmax(spec[band])] - 100.0 / 60.0 * 3.0) < 0.15  # eighth triplets: 5 Hz


def test_the_guitar_keeps_the_contract():
    silent = render("electric", [], 1.0)
    assert silent.shape == (SR, 2) and not np.any(silent)
    notes = [note(64, start=0.3, dur=0.001), note(40, start=0.5, vel=1.0), note(88, start=0.7, vel=0.0),
             note(88, start=0.9, art="woodblock"), note(60, start=5.0)]
    y = render("electric", notes, 2.0)
    assert y.shape == (2 * SR, 2) and np.all(np.isfinite(y)) and np.any(y)
    assert np.max(np.abs(y[: int(0.295 * SR)])) < 1e-4 * np.max(np.abs(y))
    for ch in range(2):
        assert abs(y[:, ch].mean()) < 1e-3 * np.sqrt(np.mean(y[:, ch] ** 2))
    assert np.array_equal(y, render("electric", notes, 2.0))
    assert not np.allclose(y, render("electric", notes, 2.0, maker=3))


def test_a_note_starts_and_stops_without_a_click():
    """The finger stopping a string takes it down in milliseconds, not a sample: the highest band (8-16 kHz)
    swells no more at the stop than while the note rings."""
    y = mono(render("electric", [note(57, dur=0.8, vel=0.8)], 1.5))
    hi = sosfiltfilt(butter(4, [8000, 16000], btype="bandpass", fs=SR, output="sos"), y)
    stop = int(0.9 * SR)
    ringing = np.sqrt(np.mean(hi[int(0.5 * SR): int(0.85 * SR)] ** 2))
    at_stop = np.sqrt(np.mean(hi[stop - 200: stop + 400] ** 2))
    assert at_stop < 2.0 * ringing + 1e-9


# --- the bass --------------------------------------------------------------------------------------


@pytest.mark.parametrize("pitch", [28, 33, 43, 52, 60])
def test_the_bass_is_in_tune(pitch):
    y = render("ebass", [note(pitch, part="ebass")], 3.0)
    assert abs(cents_of(y, pitch, 0.6, 2.4)) < 2.0


def test_the_bass_attack_is_bright_and_darkens_fast():
    """Roundwound strings: the zing (1-5 kHz) is there in the first 50 ms and 30 dB further down a quarter of
    a second later, while the fundamental rings on."""
    y = render("ebass", [note(33, part="ebass")], 3.0)

    def share(t0):
        seg = y[int(t0 * SR): int((t0 + 0.05) * SR)]
        p = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
        f = np.fft.rfftfreq(len(seg), 1 / SR)
        return 10 * np.log10(p[(f > 1000) & (f < 5000)].sum() / p.sum())

    assert share(0.1) > -25 and share(0.35) < share(0.1) - 25
    assert fall_time(y) > 1.0


def test_stiff_strings_stretch_their_partials():
    """A steel string's stiffness puts its partials sharp of the harmonic series (f_k = k f0 sqrt(1 + B k^2)),
    the more so the thicker its core and the shorter it is fretted; the fundamental stays in tune. The bass's
    open E: its 8th partial some 25 cents sharp (Fable's target 18-26), its 10th 30-40; the guitar's low E's
    8th 5-8, the plain G's 5-7, the high e's under a cent and a half."""

    def stretch(y, pitch, k, f1_cents):
        return cents_of(y, pitch + 12 * np.log2(k), 0.15, 0.9) - f1_cents

    y = render("ebass", [note(28, dur=2.5, vel=0.7, part="ebass")], 3.0)
    f1 = cents_of(y, 28, 0.4, 1.6)
    assert 18.0 < stretch(y, 28, 8, f1) < 30.0 and 28.0 < stretch(y, 28, 10, f1) < 42.0
    for pitch, string, lo, hi in ((40, 0, 4.0, 9.0), (55, 3, 4.0, 8.0), (64, 5, -0.5, 1.5)):
        y = pickup(pitch, string, 0, 2.5)
        f1 = cents_of(y, pitch, 0.4, 1.6)
        assert lo < stretch(y, pitch, 8, f1) < hi


def mean_cents(y, f, t0, t1):
    """The fundamental's mean instantaneous pitch over t0..t1, cents from f."""
    band = sosfiltfilt(butter(2, [f * 0.85, f * 1.15], btype="bandpass", fs=SR, output="sos"), y)
    inst = np.diff(np.unwrap(np.angle(hilbert(band)))) * SR / (2 * np.pi)
    return 1200 * np.log2(np.mean(inst[int(t0 * SR): int(t1 * SR)]) / f)


def test_a_hard_pluck_starts_sharp_and_settles():
    """A string plucked wide is stretched tauter while it swings: a bass's fingered A1 at 0.8 starts some 13
    cents sharp and settles within a third of a second (Fable's review: 10-25 cents for a bass, 3-6 for a
    guitar's hard strum); a soft note's glide is too small to bother with."""
    strings, *_ = electric.rig("electric", S0, SR)
    seg = fretboard.Segment(string=1, start=0, base=45.0, held=SR, picks=[(0, 0.8, "pick"), (SR // 2, 0.2, "up")],
                            end=SR)
    rise = fretboard.glide(seg, strings, fretboard.KINDS, SR)
    assert 3.0 < rise[0] < 5.0 and rise[int(0.3 * SR)] < 0.1 and len(rise) < int(0.55 * SR)  # the soft one: none
    y = render("ebass", [note(33, dur=1.5, vel=0.8, part="ebass")], 2.0)
    early, late = mean_cents(y, midi_to_hz(33), 0.13, 0.25), mean_cents(y, midi_to_hz(33), 0.7, 1.3)
    assert 3.5 < early - late < 12.0
    y = render("ebass", [note(33, dur=1.5, vel=0.3, part="ebass")], 2.0)
    assert abs(mean_cents(y, midi_to_hz(33), 0.13, 0.25) - mean_cents(y, midi_to_hz(33), 0.7, 1.3)) < 2.0


def test_the_bass_articulations():
    def one(art):
        return render("ebass", [note(38, dur=1.2, art=art, part="ebass")], 1.6)

    finger, pick, mute, ghost = one(""), one("pick"), one("mute"), one("ghost")
    assert centroid(pick, 0.1, 0.16) > centroid(finger, 0.1, 0.16)
    assert 0.05 < fall_time(mute) < 0.5 < fall_time(finger)
    assert fall_time(ghost) < min(0.06, fall_time(mute))
    assert abs(cents_of(one("slide"), 38, 0.5, 1.2)) < 2.0


def test_the_bass_keeps_the_contract():
    silent = render("ebass", [], 1.0)
    assert silent.shape == (SR,) and not np.any(silent)
    notes = [note(28, start=0.3, dur=0.001, part="ebass"), note(60, start=0.5, vel=1.0, part="ebass"),
             note(40, start=0.7, vel=0.0, part="ebass"), note(45, start=0.9, art="slap", part="ebass")]
    y = render("ebass", notes, 2.0)
    assert y.shape == (2 * SR,) and np.all(np.isfinite(y)) and np.any(y)
    assert np.max(np.abs(y[: int(0.295 * SR)])) < 1e-4 * np.max(np.abs(y))
    assert abs(y.mean()) < 1e-3 * np.sqrt(np.mean(y**2))


# --- levels and cost ---------------------------------------------------------------------------------


def phrases():
    sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "instrument_phrases_b"))
    import electric as family

    return family


@pytest.mark.parametrize("name", ["electric", "electric-crunch", "electric-tremolo", "ebass"])
def test_a_typical_part_sits_at_its_target(name):
    kind, notes = phrases().LEVELS[name]
    length = int((max(n.start + n.dur for n in notes) + 1.0) * SR)
    for maker in (0, 1, 2):
        assert abs(loudness(electric, name, notes, length, maker=maker) - TARGETS[kind]) < 1.5


def test_a_typical_part_is_cheap():
    """Forty seconds of strumming in well under four seconds of CPU."""
    kind, notes = phrases().LEVELS["electric"]
    part = notes + [n.__class__(**{**n.__dict__, "start": n.start + 19.2}) for n in notes]
    render("electric", part[:5], 1.0)  # compile
    t = time.process_time()
    render("electric", part, 40.0)
    assert time.process_time() - t < 4.0
