"""The accordion and the concertina, measured against what real free reeds, bellows and players do."""

import time

import numpy as np
import pytest
from scipy.signal import butter, sosfiltfilt

from _levels_b import SETTINGS, TARGETS, loudness, streams
from songbird.score import Note
from songbird.synth import accordion, instruments
from songbird.theory import midi_to_hz

SR = 44100
PLAIN = dict(brightness=0.5, wear=0.0, ornament=0.0, body=1.0, maker=0, tonic=62)
MUSETTE = 1  # a maker whose accordion is a musette box (three middle reeds), French-tuned: 17.4 cents at A4


def play(name, notes, dur, maker=0, seed=1, **s):
    return accordion.render(name, tuple(notes), SR, int(dur * SR), np.random.default_rng([seed, 17]),
                            np.random.default_rng([maker, 29]), {**PLAIN, "maker": maker, **s})


def played(name, notes, dur, maker=0, **s):
    """As the band's registry plays it: its own streams for this maker."""
    rng, make = streams(name, 0, maker)
    return accordion.render(name, tuple(notes), SR, int(dur * SR), rng, make, {**PLAIN, "maker": maker, **s})


def note(p, art="", vel=0.6, start=0.1, dur=1.2, part="accordion"):
    return Note(part, start, dur, float(p), vel, art=art)


def mono(y):
    return y.mean(axis=1)


def spectrum(y, t0, t1, pad=16):
    seg = mono(y)[int(t0 * SR): int(t1 * SR)]
    seg = seg * np.hanning(len(seg))
    return np.fft.rfftfreq(pad * SR, 1 / SR), np.abs(np.fft.rfft(seg, pad * SR))


def peak_hz(y, guess, t0, t1, width=0.03):
    freqs, spec = spectrum(y, t0, t1)
    band = (freqs > guess * (1 - width)) & (freqs < guess * (1 + width))
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


def reeds_near(y, f0, t0, t1, cents=60.0):
    """The cents from f0 of every reed sounding within +-cents of it (spectral peaks over a long window)."""
    freqs, spec = spectrum(y, t0, t1, pad=32)
    band = (freqs > f0 * 2 ** (-cents / 1200)) & (freqs < f0 * 2 ** (cents / 1200))
    s, f = spec[band], freqs[band]
    peaks = [k for k in range(1, len(s) - 1) if s[k] > s[k - 1] and s[k] > s[k + 1] and s[k] > 0.2 * s.max()]
    return sorted(1200 * np.log2(f[k] / f0) for k in peaks)


def cents(a, b):
    return 1200 * np.log2(a / b)


def harmonic_db(y, f0, t0, t1, count):
    freqs, spec = spectrum(y, t0, t1, pad=4)
    levels = [spec[(freqs > f0 * (h - 0.3)) & (freqs < f0 * (h + 0.3))].max() for h in range(1, count + 1)]
    return 20 * np.log10(np.array(levels) / levels[0])


def centroid(y, t0, t1):
    freqs, spec = spectrum(y, t0, t1, pad=1)
    return float(np.sum(freqs * spec**2) / np.sum(spec**2))


def envelope(y, win=0.004):
    n = int(win * SR)
    return np.sqrt(np.convolve(mono(y) ** 2, np.ones(n) / n, mode="same"))


def speaks(y, start, steady=(0.5, 0.9)):
    """Seconds from `start` until the note reaches three tenths and nine tenths of its steady level."""
    e = envelope(y)
    full = np.median(e[int((start + steady[0]) * SR): int((start + steady[1]) * SR)])
    i = int(start * SR)
    return np.argmax(e[i:] > 0.3 * full) / SR, np.argmax(e[i:] > 0.9 * full) / SR


def bellows(name, notes, maker=0, **s):
    """Where the bellows turn for a part, as render() would turn them."""
    s = {**PLAIN, "maker": maker, **s}
    rng, make = np.random.default_rng([1, 17]), np.random.default_rng([maker, 29])
    made = accordion.maker(name, make, s["wear"])
    notes = sorted(notes, key=lambda n: (n.start, n.pitch))
    ranks = accordion.register(made["box"], s["ornament"], s["brightness"])
    reeds = [accordion.voices(n, h, name, made, ranks, s["brightness"])
             for n, h in zip(notes, accordion.hands(notes, name))]
    kind = accordion.CONCERTINA if name == "concertina" else accordion.ACCORDION
    length = int((max(n.start + n.dur for n in notes) + 1.0) * SR)
    pressure, turns = accordion.bellows(notes, reeds, SR, length, kind, made["stroke"], rng, s.get("tempo"))
    return np.array(turns) / SR, made, pressure


# --- the registry ------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["accordion", "concertina"])
def test_the_band_plays_the_real_instrument_not_its_stand_in(name):
    own, found = instruments.registered(name)
    assert own == name and found is not None and found[1] is accordion
    info = instruments.spec(name)
    assert info["stand_in"] is None and info["family"] == "reed" and info["articulations"]
    notes = (note(62, part=name), note(66, "slur", start=1.3, dur=0.5, part=name))
    length = 2 * SR
    y = instruments.render_other(name, notes, SR, length, dict(SETTINGS), seed=7)
    rng = np.random.default_rng([7, 17, instruments.stream(name)])
    make = np.random.default_rng([0, 29, instruments.stream(name)])
    direct = accordion.render(name, notes, SR, length, rng, make, {**instruments.DEFAULTS, **SETTINGS})
    position, width = accordion.SPEC[name]["place"]
    assert np.allclose(y, instruments.place(direct, position, width) * accordion.SPEC[name]["level"])


# --- the reed ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("name,pitch", [("accordion", 55), ("accordion", 69), ("accordion", 84), ("accordion", 93),
                                        ("concertina", 50), ("concertina", 69), ("concertina", 88)])
def test_a_reed_is_in_tune_rich_and_speaks_as_free_reeds_do(name, pitch):
    y = play(name, [note(pitch + 12, dur=0.4, part=name), note(pitch, start=0.8, dur=1.4, part=name)], 2.5)
    f = midi_to_hz(pitch)
    assert abs(cents(peak_hz(y, f, 1.3, 2.1), f)) < 2.0
    h = harmonic_db(y, f, 1.3, 2.1, 6)
    assert np.sum(h[1:] > -20) >= (3 if pitch < 85 else 1)  # the reed chops the air: a rich series of harmonics
    t30, t90 = speaks(y, 0.8)
    t90_expected = accordion.speaking(pitch) * (0.6 if name == "concertina" else 1.0)
    assert 0.6 * t90_expected < t90 < 1.8 * t90_expected + 0.004  # to nine tenths: 15-60 ms, the low reeds slowest
    assert t30 > 0.3 * t90  # swelling in from the pallet's puff, not struck


def test_the_concertina_speaks_quicker_and_brighter_than_the_accordion_and_low_reeds_slowest():
    times = {}
    for name in ("accordion", "concertina"):
        y = play(name, [note(81, dur=0.4, part=name), note(69, start=0.8, dur=1.4, part=name)], 2.5)
        times[name] = speaks(y, 0.8)[1]
    assert times["concertina"] < 0.8 * times["accordion"]
    y = play("accordion", [note(62, "bass", dur=0.4), note(62, "bass", start=0.8, dur=1.4)], 2.5)
    assert speaks(y, 0.8)[1] > 1.3 * times["accordion"]  # the Stradella bass reeds are long and weighted


@pytest.mark.parametrize("name", ["accordion", "concertina"])
def test_pressed_harder_louder_brighter_quicker_and_a_hair_flat(name):
    level, slope, pitch, speed = [], [], [], []
    f = midi_to_hz(69)
    for vel in (0.3, 0.9):
        y = play(name, [note(81, vel=vel, dur=0.4, part=name), note(69, vel=vel, start=0.8, dur=1.4, part=name)], 2.5)
        level.append(10 * np.log10(np.mean(mono(y)[int(1.3 * SR): int(2.1 * SR)] ** 2)))
        h = harmonic_db(y, f, 1.3, 2.1, 12)
        slope.append(np.polyfit(np.log2(np.arange(1, 13)), h, 1)[0])
        pitch.append(cents(peak_hz(y, f, 1.3, 2.1), f))
        speed.append(speaks(y, 0.8)[1])
    assert 8.0 < level[1] - level[0] < 16.0
    assert 1.0 < slope[1] - slope[0] < 5.0  # the pulses sharpen: the spectrum's slope rises a few dB an octave
    assert -6.0 < pitch[1] - pitch[0] < -2.0  # a free reed sags a few cents pressed hard (Cottingham)
    assert speed[1] < 0.75 * speed[0]


# --- the accordion's treble ---------------------------------------------------------------------------


def test_the_makers_tremolo_and_its_curve_across_the_keyboard():
    made = accordion.maker("accordion", streams("accordion", 0, MUSETTE)[1], 0.0)
    assert made["box"] in ("MMM", "LMMM") and made["tuning"] == "french"
    for pitch, factor in ((57, 1.3), (69, 1.0), (81, 2 / 3), (93, 4 / 9)):
        y = played("accordion", [note(pitch, dur=4.0)], 4.5, MUSETTE, ornament=0.85)
        spread = made["tremolo"] * factor * made["uneven"][pitch]
        found = reeds_near(y, midi_to_hz(pitch), 1.0, 4.0)
        assert len(found) == 3, found  # musette: the true reed, one sharp, one as flat
        assert np.allclose(found, [-spread, 0.0, spread], atol=1.0), (pitch, found, spread)
    # the register: two middle reeds (violin) at the band's default ornament, one (clarinet) plain
    assert len(reeds_near(played("accordion", [note(69, dur=4.0)], 4.5, MUSETTE, ornament=0.5), 440.0, 1.0, 4.0)) == 2
    assert len(reeds_near(played("accordion", [note(69, dur=4.0)], 4.5, MUSETTE, ornament=0.0), 440.0, 1.0, 4.0)) == 1


def test_the_tremolo_beats_as_tuned():
    made = accordion.maker("accordion", streams("accordion", 0, MUSETTE)[1], 0.0)
    for pitch in (57, 69, 81):
        y = played("accordion", [note(pitch, dur=4.0)], 4.5, MUSETTE, ornament=0.5)  # violin: true and sharp
        f = midi_to_hz(pitch)
        band = sosfiltfilt(butter(2, [f * 0.95, f * 1.05], btype="bandpass", fs=SR, output="sos"), mono(y))
        e = np.convolve(np.abs(band), np.ones(441) / 441, mode="same")[int(1.0 * SR): int(4.0 * SR)]
        spec = np.abs(np.fft.rfft((e - e.mean()) * np.hanning(len(e)), 1 << 19))
        fr = np.fft.rfftfreq(1 << 19, 1 / SR)
        sel = (fr > 0.5) & (fr < 20)
        # the tremolo reed's cents over the true one's, each with its own few cents of the tuner's (pulled: the first
        # stroke opens the bellows)
        apart = made["tremolo"] * accordion.tremolo(pitch) * made["uneven"][pitch] \
            + made["errors"][pitch, accordion.RANK["M+"], 1] - made["errors"][pitch, accordion.RANK["M"], 1]
        beat = f * (2 ** (apart / 1200) - 1)
        assert abs(fr[sel][np.argmax(spec[sel])] - beat) < 0.1, (pitch, beat)
    # the beats quicken toward the top of the keyboard, but less than the pitch does
    rates = [midi_to_hz(p) * (2 ** (10.0 * accordion.tremolo(p) / 1200) - 1) for p in (57, 69, 81, 93)]
    assert np.all(np.diff(rates) > 0) and rates[-1] / rates[0] < 8


def test_brightness_brings_in_the_bassoon_and_the_piccolo():
    maker = next(m for m in range(40) if accordion.maker("accordion", streams("accordion", 0, m)[1], 0.0)["box"]
                 == "LMMH")
    assert accordion.register("LMMH", 0.5, 0.2) == ["M", "M+", "L"]
    assert accordion.register("LMMH", 0.5, 0.8) == ["M", "M+", "H"]
    dark = played("accordion", [note(69, dur=2.0)], 2.5, maker, brightness=0.2)
    bright = played("accordion", [note(69, dur=2.0)], 2.5, maker, brightness=0.8)
    freqs, d = spectrum(dark, 0.8, 2.0)
    _, b = spectrum(bright, 0.8, 2.0)
    at = lambda s, hz: s[(freqs > hz * 0.99) & (freqs < hz * 1.01)].max()  # noqa: E731
    assert at(d, 220.0) > 10 * at(b, 220.0)  # the bassoon's A3 under the dark register
    assert centroid(bright, 0.8, 2.0) > 1.3 * centroid(dark, 0.8, 2.0)


# --- the accordion's left hand ------------------------------------------------------------------------


@pytest.mark.parametrize("written", [38, 50, 62])
def test_a_bass_button_sounds_its_pitch_class_on_the_bass_ranks_wherever_written(written):
    y = play("accordion", [note(written, "bass", dur=1.5)], 2.0)
    for sounding in (38, 50, 62):  # D2 on the bass rank (C2-B2), D3 on the tenor (C3-B3), D4 on the contralto
        assert abs(cents(peak_hz(y, midi_to_hz(sounding), 0.6, 1.5), midi_to_hz(sounding))) < 2.0
    # the break between B and C: a B bass button sounds B2, a C one C2
    b = play("accordion", [note(47, "bass", dur=1.5)], 2.0)
    c = play("accordion", [note(48, "bass", dur=1.5)], 2.0)
    fb, sb = spectrum(b, 0.6, 1.5)
    fc, sc = spectrum(c, 0.6, 1.5)
    at = lambda f, s, hz: s[(f > hz * 0.985) & (f < hz * 1.015)].max()  # noqa: E731
    assert at(fb, sb, midi_to_hz(47)) > 10 * at(fb, sb, midi_to_hz(35))
    assert at(fc, sc, midi_to_hz(36)) > 10 * at(fc, sc, midi_to_hz(48 - 24))


def test_chord_buttons_sound_in_their_octave_and_plain_low_notes_find_the_left_hand():
    y = play("accordion", [note(p, "chord", dur=1.5) for p in (38, 42, 45)], 2.0)  # D2 F#2 A2 as chord notes
    freqs, s = spectrum(y, 0.6, 1.5)
    at = lambda hz: s[(freqs > hz * 0.985) & (freqs < hz * 1.015)].max()  # noqa: E731
    top = max(at(midi_to_hz(p)) for p in (54, 57, 62))
    for p in (54, 57, 62, 66, 69, 74):  # F#3 A3 D4 in the contralto, and their octave
        assert at(midi_to_hz(p)) > 0.05 * top, p
    for p in (38, 42, 45, 50):  # nothing where the chord was written, or below the chord reeds
        assert at(midi_to_hz(p)) < 0.02 * top, p
    lone = [note(45, start=0.1)]
    together = [note(p, start=0.1) for p in (45, 50)] + [note(66, start=0.1)]
    assert accordion.hands(lone, "accordion") == ["bass"]
    assert accordion.hands(together, "accordion") == ["chord", "chord", "treble"]
    assert accordion.hands([note(45, part="concertina")], "concertina") == ["treble"]


# --- the bellows ---------------------------------------------------------------------------------------


def test_the_bellows_turn_in_the_rests_and_sooner_the_more_reeds_drink():
    held = [note(p, start=0.2, dur=14.0, part="concertina") for p in (54, 57, 62, 66)]
    one = [note(62, start=0.2, dur=14.0, part="concertina")]
    chord_turns, made, _ = bellows("concertina", held)
    note_turns, _, _ = bellows("concertina", one)
    assert len(chord_turns) >= 3 and len(chord_turns) > 2 * len(note_turns)
    # a phrase with rests: the player turns in a rest (a practised player doesn't cut a note)
    phrase = [note(62 + (k % 5), start=0.2 + 0.5 * k, dur=0.4 if k % 4 != 3 else 0.2, part="concertina")
              for k in range(40)]
    turns, _, _ = bellows("concertina", phrase)
    assert len(turns) >= 4
    for t in turns:
        assert not any(n.start + 0.005 < t < n.start + n.dur - 0.005 for n in phrase), t
    gaps = np.diff(np.concatenate([[0.2], turns]))
    assert np.all(gaps > 0.9) and np.all(gaps < 4.0)  # a concertina's stroke: a second or two, three at most


def test_a_turn_through_a_held_note_dips_and_hands_over_to_the_other_reed():
    worn = dict(wear=0.6)
    notes = [note(p, start=0.2, dur=6.0, part="concertina") for p in (57, 62, 66, 69)]
    turns, made, pressure = bellows("concertina", notes, **worn)
    assert len(turns) >= 1
    t = turns[0]
    assert 0.9 * accordion.DIP < pressure[int(t * SR)] / pressure[int((t - 0.3) * SR)] < 1.2 * accordion.DIP
    y = play("concertina", notes, 7.0, **worn)
    e = envelope(y)
    assert e[int(t * SR) - 200: int(t * SR) + 200].min() < 0.5 * np.median(e[int((t - 0.6) * SR): int((t - 0.1) * SR)])
    # before the turn the pull reeds sound (the first stroke opens the bellows), after it the push reeds
    f = midi_to_hz(62)
    before, after = peak_hz(y, f, max(0.5, t - 1.2), t - 0.1), peak_hz(y, f, t + 0.15, min(6.1, t + 1.4))
    rank = accordion.RANK["concertina"]
    expected = made["errors"][62, rank, 0] - made["errors"][62, rank, 1]  # push minus pull
    assert abs(cents(after, before) - expected) < 1.0, (cents(after, before), expected)


@pytest.mark.parametrize("name", ["accordion", "concertina"])
def test_a_shake_pulses_with_the_beat_and_a_swell_swells(name):
    y = play(name, [note(69, "shake", dur=2.0, part=name)], 2.5, tempo=100.0)
    e = envelope(y)[int(0.4 * SR): int(1.9 * SR)]
    spec = np.abs(np.fft.rfft((e - e.mean()) * np.hanning(len(e)), 1 << 18))
    fr = np.fft.rfftfreq(1 << 18, 1 / SR)
    sel = (fr > 2) & (fr < 20)
    assert abs(fr[sel][np.argmax(spec[sel])] - 100.0 / 60.0 * 4) < 0.3  # sixteenths at 100 bpm
    assert np.percentile(e, 95) > 3 * np.percentile(e, 5)
    y = play(name, [note(69, "swell", dur=2.0, part=name)], 2.5)
    e = envelope(y, 0.05)
    assert e[int(0.9 * SR)] > 1.6 * e[int(0.25 * SR)] and e[int(0.9 * SR)] > 1.2 * e[int(2.0 * SR)]


def test_legato_runs_on_and_the_concertinas_hands_alternate():
    y = play("concertina", [note(62, start=0.1, dur=0.5, part="concertina"),
                            note(64, "slur", start=0.6, dur=0.5, part="concertina")], 1.5)
    e = envelope(y)
    assert e[int(0.59 * SR): int(0.64 * SR)].min() > 0.25 * np.median(e[int(0.3 * SR): int(0.55 * SR)])
    # the English layout: C4 on the left end, D4 on the right (lines and spaces of the staff)
    assert accordion._staff_line(60) and not accordion._staff_line(62) and accordion._staff_line(64)
    left = play("concertina", [note(60, dur=1.0, part="concertina")], 1.5)
    right = play("concertina", [note(62, dur=1.0, part="concertina")], 1.5)
    side = lambda y: np.sqrt(np.mean(y[:, 0] ** 2) / np.mean(y[:, 1] ** 2))  # noqa: E731
    assert side(left) > 1.2 and side(right) < 1 / 1.2


# --- levels, streams, edges ------------------------------------------------------------------------------


def _oompah(part, hands=True, bars=8):
    beat = 60.0 / 112
    changes = [(50, 57, (54, 57, 62)), (55, 50, (55, 59, 62)), (50, 57, (54, 57, 62)), (57, 52, (52, 57, 61))]
    notes = []
    for bar in range(bars):
        root, fifth, triad = changes[(bar // 2) % 4]
        t = 0.2 + 4 * beat * bar
        notes += [Note(part, t, 0.7 * beat, float(root), 0.66, art="bass" if hands else ""),
                  Note(part, t + 2 * beat, 0.7 * beat, float(fifth), 0.6, art="bass" if hands else "")]
        for b in (1, 3):
            notes += [Note(part, t + b * beat, 0.55 * beat, float(q), 0.54, art="chord" if hands else "")
                      for q in triad]
    return notes


@pytest.mark.parametrize("name", ["accordion", "concertina"])
def test_the_oompah_sits_with_todays_comping(name):
    notes = _oompah(name, hands=name == "accordion")
    length = int((max(n.start + n.dur for n in notes) + 1.0) * SR)
    for maker in (0, 1, 2):
        assert abs(loudness(accordion, name, notes, length, maker=maker) - TARGETS["comping"]) < 1.5, maker


@pytest.mark.parametrize("name", ["accordion", "concertina"])
def test_deterministic_makers_differ_and_the_edges_hold(name):
    notes = [note(62, start=0.2, dur=0.4, part=name), note(66, "slur", start=0.6, dur=0.4, part=name),
             note(45, "bass", start=1.1, part=name), note(69, "shake", start=1.2, dur=0.8, part=name)]
    a, b = play(name, notes, 2.5, wear=0.25), play(name, notes, 2.5, wear=0.25)
    assert np.array_equal(a, b) and a.shape == (int(2.5 * SR), 2) and np.all(np.isfinite(a))
    assert not np.allclose(a, play(name, notes, 2.5, wear=0.25, maker=4))
    assert not play(name, [], 1.0).any() and play(name, [], 1.0).shape == (SR, 2)
    lo, hi = accordion.SPEC[name]["register"]
    edge = [note(lo, vel=0.0, start=0.1, dur=0.001, part=name), note(lo, "no-such-art", 1.0, 0.3, 0.5, part=name),
            note(hi, "", 1.0, 0.9, 0.6, part=name), note(hi + 7, "chord", 0.5, 1.6, 0.3, part=name),
            note(20, "bass", 0.6, 2.0, 0.3, part=name), note(62.4, "swell", 0.6, 2.4, 0.3, part=name),
            note(60, "", 0.6, 9.0, 1.0, part=name)]
    y = play(name, edge, 3.0)
    assert y.shape == (3 * SR, 2) and np.all(np.isfinite(y)) and np.abs(y).max() > 0
    assert np.abs(y[: int(0.095 * SR)]).max() < 1e-4 * np.abs(y).max()  # nothing before the first note
    assert np.all(np.abs(y.mean(axis=0)) < 1e-3 * np.sqrt(np.mean(y**2, axis=0)))  # no DC leaves the box
    # placed at its level, held chords played loud (as a pad at a full band's 0.9) stay under full scale
    loud = [note(p, vel=0.9, start=0.1 + 2.0 * k, dur=2.0, part=name) for k in range(4) for p in (54, 57, 62, 66)]
    placed = instruments.place(play(name, loud, 8.5), *accordion.SPEC[name]["place"]) * accordion.SPEC[name]["level"]
    assert np.abs(placed).max() < 1.0


@pytest.mark.parametrize("name", ["accordion", "concertina"])
def test_a_typical_part_costs_little(name):
    part = _oompah(name, hands=name == "accordion", bars=24)  # about 50 s of oom-pah
    play(name, part[:16], 3.0)  # compile
    t = time.process_time()
    play(name, part, max(n.start + n.dur for n in part) + 1.0)
    assert time.process_time() - t < 4.0
