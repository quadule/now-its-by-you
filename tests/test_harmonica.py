"""The diatonic harmonica, measured against what real harps and players do."""

import time

import numpy as np
import pytest
from scipy.signal import butter, hilbert, sosfiltfilt

from _levels_b import TARGETS, loudness
from songbird.score import Note
from songbird.synth import harmonica
from songbird.theory import midi_to_hz

SR = 44100
PLAIN = dict(brightness=0.5, wear=0.0, ornament=0.0, body=1.0, maker=0, tonic=62, temperament="equal")


def play(notes, dur, maker=0, seed=1, **s):
    return harmonica.render("harmonica", tuple(notes), SR, int(dur * SR), np.random.default_rng([seed, 17]),
                            np.random.default_rng([maker, 29]), {**PLAIN, "maker": maker, **s})


def note(p, art="", vel=0.6, start=0.1, dur=1.2):
    return Note("harmonica", start, dur, float(p), vel, art=art)


def peak_hz(y, guess, t0, t1, width=0.06):
    seg = y[int(t0 * SR): int(t1 * SR)] * np.hanning(int(t1 * SR) - int(t0 * SR))
    spec = np.abs(np.fft.rfft(seg, 16 * SR))
    freqs = np.fft.rfftfreq(16 * SR, 1 / SR)
    band = (freqs > guess * (1 - width)) & (freqs < guess * (1 + width))
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


def cents(a, b):
    return 1200 * np.log2(a / b)


def harmonic_db(y, f0, t0, t1, count):
    seg = y[int(t0 * SR): int(t1 * SR)] * np.hanning(int(t1 * SR) - int(t0 * SR))
    n = 1 << int(np.ceil(np.log2(4 * len(seg))))
    spec = np.abs(np.fft.rfft(seg, n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    levels = [spec[(freqs > f0 * (h - 0.3)) & (freqs < f0 * (h + 0.3))].max() for h in range(1, count + 1)]
    return 20 * np.log10(np.array(levels) / levels[0])


def centroid(y, t0, t1):
    seg = y[int(t0 * SR): int(t1 * SR)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    return float(np.sum(f * spec) / np.sum(spec))


def band_env(y, f, win=0.004, width=0.15, order=2):
    band = sosfiltfilt(butter(order, [f * (1 - width), f * (1 + width)], btype="bandpass", fs=SR, output="sos"), y)
    n = int(win * SR)
    return np.sqrt(np.convolve(band**2, np.ones(n) / n, mode="same"))


# --- the harp ----------------------------------------------------------------------------------


def test_richter_layout_and_the_bends_bahnson_antaki_and_beery_measured():
    c = harmonica.layout(60)  # a C harp
    natural = sorted(p for p, ways in c.items() if any(r.bend == 0 for _, r in ways))
    assert natural[:6] == [60, 62, 64, 67, 71, 72]  # the low octave skips F and A
    assert all(p in natural for p in (72, 74, 76, 77, 79, 81, 83, 84))  # holes 4-7: the whole major scale
    assert 93 in natural and 95 not in natural  # hole 10 draw A6, and no natural B6
    bends = {(r.hole + 1, r.breath): r.bend for ways in c.values() for _, r in ways if r.bend > 0}
    most = {}
    for (hole, breath), b in bends.items():
        most[(hole, breath)] = max(most.get((hole, breath), 0), b)
    assert [most.get((h, "draw"), 0) for h in range(1, 8)] == [1, 2, 3, 1, 0, 1, 0]
    assert [most.get((h, "blow"), 0) for h in (7, 8, 9, 10)] == [0, 1, 1, 2]
    assert all(p in c for p in range(60, 97))  # with overblows and overdraws, every semitone


@pytest.mark.parametrize("pcs,key,position", [
    ((0, 2, 4, 5, 7, 9, 11), 62, 1),  # D major: a D harp, first position
    ((0, 3, 4, 5, 7, 10), 55, 2),  # a D blues, both thirds and the flat seventh: a G harp, cross harp
    ((0, 2, 4, 7, 9), 62, 1),  # pentatonic, no seventh at all: first position
    ((0, 2, 3, 5, 7, 9, 10), 60, 3),  # D dorian: a C harp in third position (cross harp would overblow F5)
])
def test_the_harp_is_chosen_for_the_tune(pcs, key, position):
    notes = [note(62 + pc) for pc in pcs] + [note(74 + pc) for pc in pcs]
    assert harmonica.harp(notes, 62) == (key, position)


def test_a_d_harp_bends_g_and_b_in_the_low_octave_and_plays_the_middle_straight():
    notes = [note(p) for p in (62, 64, 66, 67, 69, 71, 73, 74, 76, 78, 79, 81, 83, 85, 86)]
    reeds = harmonica.fingering(notes, 62)
    bent = {int(n.pitch): (r.hole + 1, r.breath, r.bend) for n, r in zip(notes, reeds) if r.bend}
    assert bent == {67: (2, "draw", 2), 71: (3, "draw", 2)}  # G4 a whole-tone bend on 2 draw, B4 on 3 draw
    assert all(4 <= r.hole + 1 <= 7 for n, r in zip(notes, reeds) if 74 <= n.pitch <= 86)


def test_the_blues_takes_the_cross_harp_and_its_draw_notes():
    fills = [note(p) for p in (76, 78, 66, 69, 71)]  # what the blues style wrote in D: E5 F#5, F#4 A4 B4
    assert harmonica.harp(fills, 62) == (62, 1)  # a folk player keeps the D harp (B4 a 3-draw whole-tone bend)
    assert harmonica.harp(fills, 62, "blues") == (55, 2)  # a blues player a G harp: all five natural
    tonic = harmonica.fingering([note(62)], 55, 2)[0]
    assert (tonic.hole + 1, tonic.breath) == (2, "draw")  # D4 on the cross harp: 2 draw, not 3 blow
    leading = [note(p) for p in (73, 74, 73, 71, 73, 74)]  # a tune leaning on its seventh, C#5
    assert harmonica.harp(leading, 62, "blues") == (62, 1)  # the cross harp would overblow it (5): stays straight


def test_joined_notes_slide_on_one_breath_turn_round_with_a_dip_and_a_repeat_is_tongued():
    def dip(a, b):  # the deepest the sound falls at the join, against the notes either side (dB)
        y = play([note(a, dur=0.4), note(b, start=0.5, dur=0.4)], 1.1)
        env = 20 * np.log10(np.sqrt(np.convolve(y**2, np.ones(88) / 88, mode="same")) + 1e-12)
        around = min(np.median(env[int(0.3 * SR): int(0.45 * SR)]), np.median(env[int(0.65 * SR): int(0.85 * SR)]))
        return around - env[int(0.47 * SR): int(0.56 * SR)].min()
    moved, turned, repeat = dip(74, 78), dip(74, 76), dip(74, 74)  # 4 to 5 blow; 4 blow to 4 draw; 4 blow again
    assert moved < 5.0 and turned > 10.0 and repeat > 10.0  # the lips slide on; the breath turns; the tongue stops it


def test_a_bend_or_a_slide_takes_a_reed_that_bends():
    plain, bend = harmonica.fingering([note(69)], 62)[0], harmonica.fingering([note(69, "bend")], 62)[0]
    assert (plain.hole + 1, plain.breath) == (3, "blow") and (bend.hole + 1, bend.breath) == (2, "draw")


# --- the reed ----------------------------------------------------------------------------------


@pytest.mark.parametrize("pitch", [62, 66, 69, 74, 79, 86, 93])
def test_natural_notes_are_in_tune_speak_in_time_and_are_rich(pitch):
    y = play([note(pitch)], 1.6, temperament="equal")
    f = midi_to_hz(pitch)
    assert -1.5 < cents(peak_hz(y, f, 0.5, 1.2), f) < 3.5  # tuned so a mezzo-forte breath sits 0-2 c over the band
    env = band_env(y, f)
    speak = (np.argmax(env > 0.9 * np.median(env[int(0.6 * SR): int(1.1 * SR)])) - int(0.1 * SR)) / SR
    assert 0.008 < speak < (0.045 if pitch < 70 else 0.03)  # a free reed speaks in 10-40 ms, the low ones slowest
    h = harmonic_db(y, f, 0.5, 1.2, 12)
    assert np.sum(h[1:] > -20) >= (6 if pitch <= 86 else 3)  # the reed chops the air: strong harmonics to 5-8 kHz


def test_the_tone_is_as_bright_drawing_as_blowing_and_bright_to_eight_kilohertz():
    blow, draw = play([note(74)], 1.6), play([note(76)], 1.6)  # D5 4 blow, E5 4 draw
    ratio = [centroid(y, 0.5, 1.2) / midi_to_hz(p) for y, p in ((blow, 74), (draw, 76))]
    assert abs(np.log(ratio[1] / ratio[0])) < np.log(1.2)  # within 20%, not the old 40% jump between neighbours
    h = harmonic_db(blow, midi_to_hz(74), 0.5, 1.2, 14)
    assert h[7] > -22 and h[11] > -28 and 1.3e3 < centroid(blow, 0.5, 1.2) < 2.0e3  # H8 (4.7 kHz), H12 (7 kHz)


def test_the_harp_is_tuned_sharp_sags_with_the_breath_and_has_a_makers_temperament():
    f = midi_to_hz(74)
    soft, hard = (cents(peak_hz(play([note(74, vel=v)], 1.6, temperament="equal"), f, 0.5, 1.2), f) for v in (0.3, 0.9))
    assert soft - hard > 4.0 and soft > 1.5 and hard < 0.0  # a soft breath sharp, a hard one flat
    third = {t: cents(peak_hz(play([note(78)], 1.6, temperament=t), midi_to_hz(78), 0.5, 1.2), midi_to_hz(78))
             for t in ("equal", "compromise", "just")}  # F#5, 5 blow: the blow chord's third
    assert third["equal"] - third["compromise"] > 3.0 and third["equal"] - third["just"] > 9.0


@pytest.mark.parametrize("pitch", [69, 76])
def test_a_harder_breath_is_louder_and_brighter(pitch):
    f = midi_to_hz(pitch)
    level, slope = [], []
    for vel in (0.3, 0.9):
        y = play([note(pitch, vel=vel)], 1.6)
        level.append(10 * np.log10(np.mean(y[int(0.5 * SR): int(1.2 * SR)] ** 2)))
        h = harmonic_db(y, f, 0.5, 1.2, 12)
        slope.append(np.polyfit(np.log2(np.arange(1, 13)), h, 1)[0])  # dB per octave of harmonic number
    assert level[1] - level[0] > 7
    assert 1.5 < slope[1] - slope[0] < 5  # the spectrum's slope rises 2 to 3 dB an octave


def test_a_bent_note_is_attacked_a_little_high_and_a_blues_bend_drawn_down_from_the_unbent_reed():
    f = midi_to_hz(67)  # G4 on a D harp: 2 draw, bent a whole tone from A4
    for seed in (1, 2, 3):
        bent = play([note(67)], 1.6, seed=seed)
        assert 12 < cents(peak_hz(bent, f * 2 ** (0.3 / 12), 0.1, 0.13, 0.05), f) < 50  # a little above
        assert abs(cents(peak_hz(bent, f, 0.5, 1.2), f)) < 25  # then held by ear: near G, a little off
        blues = play([note(67, "bend")], 1.6, seed=seed)
        assert cents(peak_hz(blues, f * 2 ** (1.8 / 12), 0.1, 0.14, 0.08), f) > 150  # held on the reed's A first
    straight = play([note(69)], 1.6)
    k = lambda y: 10 * np.log10(np.mean(y[int(0.5 * SR): int(1.2 * SR)] ** 2))  # noqa: E731
    assert -5.5 < k(bent) - k(straight) < -1.5  # weaker, 1.5-2 dB a semitone
    assert centroid(bent, 0.5, 1.2) / f < 0.9 * centroid(straight, 0.5, 1.2) / midi_to_hz(69)  # and darker


def test_the_throat_vibrato_pulses_the_breath_and_only_a_reed_that_bends_dips_in_pitch():
    for pitch, bends in ((74, False), (76, True)):  # 4 blow can't bend; 4 draw can
        f = midi_to_hz(pitch)
        y = play([note(pitch, dur=2.0)], 2.4, ornament=0.5)
        band = sosfiltfilt(butter(3, [f * 0.9, f * 1.1], btype="bandpass", fs=SR, output="sos"), y)
        a = hilbert(band)
        inst = np.convolve(np.diff(np.unwrap(np.angle(a))) * SR / (2 * np.pi), np.ones(265) / 265, mode="same")
        c = cents(inst[int(0.9 * SR): int(2.0 * SR)], f)
        db = 20 * np.log10(np.abs(a)[int(0.9 * SR): int(2.0 * SR)])
        assert 3.0 < np.percentile(db, 95) - np.percentile(db, 5) < 7.0  # the breath pulses, 3-6 dB
        swing = np.percentile(c, 95) - np.percentile(c, 5)
        assert (8.0 < swing < 25.0 and np.percentile(c, 95) - np.median(c) < 0.4 * swing) if bends else swing < 4.0


def test_a_soft_breath_speaks_slowly_and_a_hard_one_quickly():
    rise = []
    for vel in (0.3, 0.6, 0.9):
        y = play([note(76, vel=vel)], 1.6)
        env = np.sqrt(np.convolve(y**2, np.ones(132) / 132, mode="same"))
        steady = np.median(env[int(0.5 * SR): int(0.8 * SR)])
        rise.append((np.argmax(env > 0.9 * steady) - np.argmax(env > 0.1 * steady)) / SR)
    assert 0.025 < rise[0] < 0.06 and 0.012 < rise[1] < 0.03 and 0.006 < rise[2] < 0.016


def test_the_hands_open_in_a_wah_and_flutter_in_a_tremolo_but_not_on_a_rack():
    wah = play([note(74, "wah", dur=0.8)], 1.1)
    assert centroid(wah, 0.1, 0.16) < 0.6 * centroid(wah, 0.45, 0.8)  # muffled, then open
    shut = harmonic_db(wah, midi_to_hz(74), 0.105, 0.155, 8) - harmonic_db(wah, midi_to_hz(74), 0.5, 0.8, 8)
    assert -30 < shut[5] < -10  # shut, the highs 10-30 dB down, not gone
    trem = play([note(74, "trem", dur=1.4)], 1.7)
    rms = np.sqrt(np.convolve(trem**2, np.ones(441) / 441, mode="same"))[int(0.3 * SR): int(1.4 * SR)]
    spec = np.abs(np.fft.rfft((rms - rms.mean()) * np.hanning(len(rms)), 1 << 18))
    fr = np.fft.rfftfreq(1 << 18, 1 / SR)
    sel = (fr > 2) & (fr < 15)
    assert 4.5 < fr[sel][np.argmax(spec[sel])] < 7.0
    db = 20 * np.log10(rms)
    assert 2.5 < np.percentile(db, 95) - np.percentile(db, 5) < 7.0  # the whole sound pulses 3-5 dB
    racked = play([note(74, "trem", dur=1.4)], 1.7, style="songwriter")  # hands on the guitar: no tremolo
    assert np.allclose(racked, play([note(74, dur=1.4)], 1.7, style="songwriter"))


def test_a_slap_bursts_a_chord_then_leaves_the_note():
    y = play([note(81, "slap", dur=0.8)], 1.1)  # A5, 6 blow on a D harp: holes 3-5 blow under it (A4 D5 F#5)
    low = band_env(y, midi_to_hz(69), win=0.01)  # A4, hole 3 blow
    assert low[int(0.13 * SR)] > 8 * low[int(0.4 * SR)]
    chord = play([note(81, "chord", dur=0.8)], 1.1)
    assert band_env(chord, midi_to_hz(78), win=0.01)[int(0.4 * SR)] > 0.2 * band_env(chord, midi_to_hz(81), 0.01)[
        int(0.4 * SR)]  # a vamp keeps its F#5 (5 blow) sounding


def test_a_chord_written_out_is_one_breath_and_an_octave_is_an_octave():
    written = play([note(p, "chord", dur=0.8) for p in (62, 66, 69)], 1.1)  # D4 F#4 A4: 1, 2 and 3 blow
    single = play([note(69, "chord", dur=0.8)], 1.1)  # the same three holes from the top note alone
    level = lambda y: 10 * np.log10(np.mean(y[int(0.3 * SR): int(0.8 * SR)] ** 2))  # noqa: E731
    assert abs(level(written) - level(single)) < 1.0  # not each reed sounded again for every note written
    split = play([note(81, "octave", dur=0.8)], 1.1)  # A5 (6 blow) and A4 (3 blow)
    assert band_env(split, midi_to_hz(69))[int(0.5 * SR)] > 0.3 * band_env(split, midi_to_hz(81))[int(0.5 * SR)]
    seventh = play([note(79, "octave", dur=0.8)], 1.1)  # G5, 5 draw: 2 draw is A4, no octave; played alone
    assert band_env(seventh, midi_to_hz(69))[int(0.5 * SR)] < 0.05 * band_env(seventh, midi_to_hz(79))[int(0.5 * SR)]


def test_a_slide_scoops_a_reed_that_bends_and_crosses_the_next_hole_onto_one_that_doesnt():
    scoop = play([note(83, "slide")], 1.6)  # B5, 6 draw on a D harp: scooped up from under
    f = midi_to_hz(83)
    assert -80 < cents(peak_hz(scoop, f * 2 ** (-0.5 / 12), 0.1, 0.13, 0.06), f) < -25
    assert abs(cents(peak_hz(scoop, f, 0.3, 1.2), f)) < 3.0
    notes = [note(78, "", dur=0.4), note(81, "slide", start=0.7)]  # F#5 (5 blow), then A5 (6 blow) slid onto
    onto, plain = play(notes, 1.8), play([notes[0], note(81, start=0.7)], 1.8)
    passing = [band_env(y, midi_to_hz(78), 0.005, 0.04, 3) for y in (onto, plain)]  # 5 blow, as the lips cross it
    assert passing[0][int(0.72 * SR)] > 10 * passing[1][int(0.72 * SR)]
    assert passing[0][int(0.8 * SR)] < 0.05 * passing[0][int(0.72 * SR)]  # then gone


# --- levels, streams, edges ------------------------------------------------------------------------

LEAD = [Note("harmonica", 0.5 + b * 0.5, d * 0.475, float(p), 0.65, art="slur" if k % 3 == 1 else "")
        for k, (b, d, p) in enumerate([(0, 1, 74), (1, 1, 76), (2, 1, 78), (3, 1, 79), (4, 2, 81), (6, 1, 79),
                                       (7, 1, 78), (8, 1, 76), (9, 1, 74), (10, 2, 78), (12, 1, 81), (13, 1, 83),
                                       (14, 2, 86), (16, 1, 81), (17, 1, 78), (18, 2, 76), (20, 4, 74)])]
VAMP = [Note("harmonica", 0.5 + b * 0.5, 0.4, float(81 if (b // 4) % 2 == 0 else 76), 0.6, art="chord")
        for b in range(24)]


@pytest.mark.parametrize("kind,notes", [("lead", LEAD), ("comping", VAMP)])
def test_levels_sit_with_todays_stems(kind, notes):
    length = int((max(n.start + n.dur for n in notes) + 1.0) * SR)
    for maker in (0, 1, 2):
        assert abs(loudness(harmonica, "harmonica", notes, length, maker=maker) - TARGETS[kind]) < 1.5, maker


def test_deterministic_makers_differ_and_the_edges_hold():
    notes = [note(74, start=0.2, dur=0.4), note(76, "slur", start=0.6, dur=0.4), note(71, "bend", start=1.1)]
    a, b = play(notes, 2.5, wear=0.25), play(notes, 2.5, wear=0.25)
    assert np.array_equal(a, b) and a.shape == (int(2.5 * SR),) and np.all(np.isfinite(a))
    assert not np.allclose(a, play(notes, 2.5, wear=0.25, maker=4))
    assert not play([], 1.0).any() and play([], 1.0).shape == (SR,)
    lo, hi = harmonica.SPEC["harmonica"]["register"]
    edge = [note(lo, vel=0.0, start=0.1, dur=0.001), note(lo, "no-such-art", 1.0, 0.3, 0.5),
            note(hi, "", 1.0, 0.9, 0.6), note(hi + 7, "slap", 0.5, 1.6, 0.3), note(40, "octave", 0.6, 2.0, 0.3),
            note(62.4, "chord", 0.6, 2.4, 0.3), note(60, "", 0.6, 9.0, 1.0)]
    y = play(edge, 3.0)
    assert y.shape == (3 * SR,) and np.all(np.isfinite(y)) and np.abs(y).max() > 0
    assert np.abs(y[: int(0.095 * SR)]).max() < 1e-4 * np.abs(y).max()  # nothing before the first note
    assert abs(y.mean()) < 1e-3 * np.sqrt(np.mean(y**2))


def test_a_typical_part_costs_little():
    part = [Note("harmonica", 0.25 * k, 0.22, float((74, 76, 78, 81, 79, 76, 67, 71)[k % 8]), 0.65,
                 art=("", "slur", "bend", "", "chord", "wah", "", "slap")[k % 8]) for k in range(160)]
    play(part[:8], 2.0)  # compile
    t = time.process_time()
    play(part, 41.0)
    assert time.process_time() - t < 4.0
