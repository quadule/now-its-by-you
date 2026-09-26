"""The banjo, measured against real banjos: its tuning, its head, how fast it dies, the twang of a hard
pick, the hands' strokes, its level and its cost."""

import time

import numpy as np
import pytest
from _fretted import SR, cents, centroid, early_db, env_db, mono, render, share_db, t60
from _levels_b import TARGETS, loudness, streams

from songbird.score import Note
from songbird.synth import banjo, body, fretwork


def note(start, dur, pitch, vel=0.6, art="pick"):
    return Note("banjo", start, dur, float(pitch), vel, art=art)


def play(notes, seconds, **kw):
    return render(banjo, "banjo", notes, seconds, **kw)


ROLL = {"D": (54, 57, 62, 69, 57, 62, 69, 62), "G": (55, 59, 62, 69, 59, 62, 69, 62),
        "A": (57, 61, 64, 69, 61, 64, 69, 64)}


def roll(chords, tempo=110.0, vel=0.6):
    """Forward rolls in eighths, a bar a chord, each string ringing until it is picked again."""
    beat = 60.0 / tempo
    notes = []
    for bar, name in enumerate(chords):
        shape = ROLL[name]
        for k, p in enumerate(shape):
            again = next((j for j in range(k + 1, 8) if shape[j] == p), 8)
            notes.append(note((4 * bar + 0.5 * k) * beat, 0.5 * (again - k) * beat, p, vel))
    return notes


# --- the tuning ----------------------------------------------------------------------------------


@pytest.mark.parametrize("tonic", range(60, 72))
def test_the_long_strings_sound_the_keys_chord_and_the_drone_its_tonic_or_fifth(tonic):
    longs, drone, capo = banjo.tuning(tonic)
    t = tonic % 12
    assert 49 <= longs[3] <= 55 and list(longs) == sorted(longs, reverse=True)
    assert {p % 12 for p in longs} == {t, (t + 4) % 12, (t + 7) % 12}
    assert 64 <= drone <= 71 and drone % 12 in (t, (t + 7) % 12)
    assert 0 <= capo <= 5


def test_open_g_and_open_d():
    assert banjo.tuning(67)[:2] == ((62, 59, 55, 50), 67)  # gDGBD
    assert banjo.tuning(62)[:2] == ((62, 57, 54, 50), 69)  # open D, the fifth string on A


def test_the_drones_note_is_played_on_the_fifth_string_and_chops_on_fretted_ones():
    neck = banjo.neck(62)
    fingered = fretwork.assign([note(0.0, 0.4, 69), note(0.5, 0.4, 62), note(1.0, 0.4, 69, art="thumb")], neck)
    assert [f.string for f in fingered] == [4, 0, 4]
    chop = fretwork.assign([note(0.0, 0.2, p, art="chop") for p in (61, 64, 69)], neck)
    assert all(f.fret > 0 for f in chop)  # an open string can't be choked
    slide = fretwork.assign([note(0.0, 0.5, 54, art="slide")], neck)
    assert slide[0].fret >= 2  # slid into from two frets below, not from under the nut


@pytest.mark.parametrize("pitch", [50, 57, 62, 69, 74, 84])
def test_in_tune_across_its_register(pitch):
    y = play([note(0.05, 2.0, pitch, vel=0.5)], 2.3, wear=0.0)
    assert abs(cents(y, pitch, 0.35, 1.2)) < 2.0


# --- the head, and how fast the strings die ---------------------------------------------------


def test_the_head_rings_at_a_membranes_modes():
    """(0,1) between 300 and 400 Hz, then (1,1), (2,1), (0,2) at an ideal membrane's ratios, Q 20 to 40."""
    for maker in range(4):
        q = banjo._maker(streams("banjo", 0, maker)[1])
        spec = banjo.head(q["head"], q["q"], q["bridge"], True, q["helm"], 0.5)
        f = np.array([m[0] for m in spec.modes[:4]])
        assert 300 <= f[0] <= 400
        assert np.allclose(f[1:] / f[0], [1.593, 2.136, 2.295], atol=0.01)
        assert all(20 <= m[1] <= 40 for m in spec.modes[:10])
    freqs, db = body.response(body.impulse_response(spec, SR, seed=1), SR, n=1 << 16)
    near = (freqs > 250) & (freqs < 450)
    assert abs(freqs[near][np.argmax(db[near])] - f[0]) < 0.08 * f[0]


def test_the_head_takes_the_strings_energy_fast():
    """An open string falls 60 dB in one to two seconds, a high fretted note far sooner."""
    low, first, high = (t60(play([note(0.05, 4.0, p)], 4.3), 0.05) for p in (50, 62, 81))
    assert 1.4 < low < 2.4 and 1.0 < first < 1.9 and high < 0.9


def test_clawhammer_is_played_on_an_open_back_and_picks_on_a_resonator():
    claw, picks = [note(0.1, 0.1, 62, art="claw")] * 3, [note(0.1, 0.1, 62, art="pick")] * 3
    assert banjo.style(claw, 0.5) == (True, False) and banjo.style(picks, 0.5) == (False, True)
    assert banjo.style(claw, 0.05) == (True, True)  # a few players choose the other back
    # the open back's head cancels itself below its first mode: a low D3 keeps less of its fundamental
    odd = next(m for m in range(100) if banjo._maker(streams("banjo", 0, m)[1])["back"] < 0.12)
    usual = next(m for m in range(100) if banjo._maker(streams("banjo", 0, m)[1])["back"] > 0.12)
    d3 = [note(0.05, 1.5, 50)]
    lows = [share_db(play(d3, 1.6, maker=m), 100, 200, 0.1, 0.6) for m in (odd, usual)]
    assert lows[0] < lows[1] - 5


# --- the twang -------------------------------------------------------------------------------------


def test_a_hard_pick_starts_sharp_and_relaxes_in_a_tenth_of_a_second():
    y = play([note(0.0, 2.0, 62, vel=1.0)], 2.2, wear=0.0)
    settled = cents(y, 62, 0.6, 1.6)
    start = cents(y, 62, 0.0, 0.04) - settled
    later = cents(y, 62, 0.1, 0.14) - settled
    assert 5.0 < start < 18.0 and later < 0.5 * start
    soft = play([note(0.0, 2.0, 62, vel=0.3)], 2.2, wear=0.0)
    assert cents(soft, 62, 0.0, 0.04) - cents(soft, 62, 0.6, 1.6) < 0.25 * start


def test_the_break_angle_pulls_the_bridge_at_twice_the_frequency_harder_as_it_is_picked_harder():
    """The pull alone (the force with it less the force without) against the string's own fundamental."""
    freqs = np.fft.rfftfreq(1 << 15, 1 / SR)
    flat = np.ones(len(freqs))

    def level(y, f):
        seg = y[int(0.02 * SR): int(0.12 * SR)] * np.hanning(int(0.12 * SR) - int(0.02 * SR))
        spec = np.abs(np.fft.rfft(seg, 1 << 18))
        fr = np.fft.rfftfreq(1 << 18, 1 / SR)
        return 20 * np.log10(spec[(fr > 0.97 * f) & (fr < 1.03 * f)].max())

    def pull(vel):
        out = []
        for gain in (0.0, banjo.PULL):
            strings = fretwork.Strings(loss=(0.1,), decay=1.35, offsets=(0.0,), splits=(0.5,), glide=0.0, pull=gain)
            stroke = fretwork.Stroke(string=0, at=0, until=SR, pitch=62.0, fret=0, vel=vel, beta=0.07, hardness=0.9)
            out.append(fretwork.play([stroke], strings, SR, SR, np.random.default_rng(0), freqs, flat))
        return level(out[1] - out[0], 2 * 293.66) - level(out[0], 293.66)

    hard, soft = pull(1.0), pull(0.25)
    assert -26 < hard < -16
    swing = 20 * np.log10(fretwork.dynamics(1.0) / fretwork.dynamics(0.25))
    assert abs((hard - soft) - swing) < 1.5  # quadratic: the pull grows as the square of the swing


# --- the hands ----------------------------------------------------------------------------------------


def test_harder_is_louder_and_brighter():
    soft, hard = (play([note(0.05, 1.5, 62, vel=v)], 1.7) for v in (0.3, 0.9))
    swing = 20 * np.log10(fretwork.dynamics(0.9) / fretwork.dynamics(0.3))
    assert abs(early_db(hard, 0.05) - early_db(soft, 0.05) - swing) < 1.5
    assert centroid(hard, 0.05, 0.25) > 1.08 * centroid(soft, 0.05, 0.25)
    assert share_db(hard, 4000, 16000, 0.05, 0.25) > share_db(soft, 4000, 16000, 0.05, 0.25) + 3


def test_picks_near_the_bridge_are_brighter_than_the_nail_over_the_neck():
    pick = play([note(0.05, 1.5, 62, art="pick")], 1.7, maker=1)
    claw = play([note(0.05, 1.5, 62, art="claw")], 1.7, maker=1)
    assert centroid(pick, 0.05, 0.35) > 1.3 * centroid(claw, 0.05, 0.35)


def test_a_hammer_on_moves_the_ringing_string_without_a_pick():
    hammered = play([note(0.05, 0.3, 62), note(0.35, 1.0, 64, art="hammer")], 1.6, wear=0.0)
    picked = play([note(0.05, 0.3, 62), note(0.35, 1.0, 64)], 1.6, wear=0.0)
    assert abs(cents(hammered, 64, 0.6, 1.2)) < 3.0
    assert early_db(hammered, 0.35, 0.05) < early_db(picked, 0.35, 0.05) - 3


def test_a_pull_off_plucks_the_lower_note_as_the_finger_leaves():
    y = play([note(0.05, 0.3, 64), note(0.35, 1.0, 62, art="pull")], 1.6, wear=0.0)
    assert abs(cents(y, 62, 0.6, 1.2)) < 3.0
    assert early_db(y, 0.36, 0.05) > early_db(y, 0.3, 0.04) - 6  # plucked again, not just left ringing


def test_a_slide_rises_two_frets_into_its_note():
    y = play([note(0.05, 1.2, 66, vel=0.5, art="slide")], 1.4, wear=0.0)
    assert cents(y, 64, 0.05, 0.09) < 100  # it starts near E4, two frets under the F#4
    assert abs(cents(y, 66, 0.4, 1.1)) < 3.0


def test_a_chop_is_choked_at_once_and_a_brush_is_spread_low_to_high():
    chords = [note(0.1, 0.5, p, art="chop") for p in (61, 64, 69)]
    choked, ringing = env_db(play(chords, 1.0)), env_db(play([note(0.1, 0.5, p) for p in (61, 64, 69)], 1.0))
    assert choked[25] < choked.max() - 30 and ringing[25] > choked[25] + 15
    brush = fretwork.assign([note(0.2, 0.4, p, art="brush") for p in (54, 57, 62)], banjo.neck(62))
    fretwork.spread(brush, banjo.neck(62), lambda art: 0.02, np.random.default_rng(0))
    brush.sort(key=lambda f: f.start)
    assert [f.pitch for f in brush] == [54, 57, 62] and 0.01 < brush[-1].start - brush[0].start < 0.03


# --- the part as a whole --------------------------------------------------------------------------


def test_silent_before_its_first_note_no_dc_and_quiet_after_its_last():
    y = play([note(0.2, 0.4, 62, vel=1.0), note(0.8, 0.3, 69, vel=1.0, art="claw")], 3.0)
    peak = np.abs(y).max()
    assert np.abs(y[: int(0.195 * SR)]).max() < 1e-4 * peak
    for ch in range(2):
        assert abs(y[:, ch].mean()) < 1e-3 * np.sqrt(np.mean(y[:, ch] ** 2))
    assert np.abs(y[-int(0.05 * SR):]).max() < 1e-3 * peak


def test_a_stopped_note_ends_without_a_click():
    """Nothing above 8 kHz where the finger stops the string, against the pick's own attack."""
    y = mono(play([note(0.1, 0.6, 62, vel=0.8)], 1.2))
    from scipy.signal import butter, sosfilt

    hi = sosfilt(butter(4, 8000, btype="highpass", fs=SR, output="sos"), y)
    attack = np.sqrt(np.mean(hi[int(0.1 * SR): int(0.13 * SR)] ** 2))
    stop = np.sqrt(np.mean(hi[int(0.7 * SR): int(0.73 * SR)] ** 2))
    assert stop < 0.01 * attack


@pytest.mark.parametrize("pitch", [84.0, 106.0])
def test_a_bright_hard_note_is_purely_harmonic(pitch):
    """No aliasing: a lossless string rich up to Nyquist, picked hard with the tension's pull on (the
    only nonlinear thing in it), has nothing between its harmonics, even for a note far above the
    banjo's reach (A#7), whose third harmonic doubled would pass Nyquist were it not left out."""
    freqs = np.fft.rfftfreq(1 << 15, 1 / SR)
    strings = fretwork.Strings(loss=(0.0,), decay=60.0, offsets=(0.0,), splits=(0.0,), glide=0.0, pull=2.0)
    stroke = fretwork.Stroke(string=0, at=0, until=2 * SR, pitch=pitch, fret=0, vel=1.0, beta=0.05, hardness=1.0,
                             click=(0.0, 4000.0, 2.0))
    y = fretwork.play([stroke], strings, SR, 2 * SR, np.random.default_rng(0), freqs, np.ones(len(freqs)))
    from scipy.signal.windows import blackmanharris

    seg = y[SR // 2: SR // 2 + SR] * blackmanharris(SR)
    power = np.abs(np.fft.rfft(seg)) ** 2
    f = np.fft.rfftfreq(SR, 1 / SR)
    f0 = 440 * 2 ** ((pitch - 69) / 12)
    near = np.abs(f - f0 * np.round(f / f0)) < 12.0
    assert power[~near & (f > 20)].sum() < 1e-7 * power.sum()


def test_the_same_maker_plays_the_same_banjo_and_another_maker_another():
    notes = [note(0.1 + 0.25 * k, 0.5, p) for k, p in enumerate((62, 66, 69, 74))]
    a = play(notes, 1.8)
    assert np.array_equal(a, play(notes, 1.8))
    other = play(notes, 1.8, maker=7)
    assert not np.allclose(a, other)
    heads = [banjo._maker(streams("banjo", 0, m)[1])["head"] for m in (0, 7)]
    assert abs(heads[0] - heads[1]) > 1.0


def test_any_part_renders():
    assert np.array_equal(play([], 1.0), np.zeros((SR, 2)))
    odd = [note(0.1, 0.001, 50, vel=1.0), note(0.2, 0.5, 84, vel=0.0), note(0.3, 0.2, 62, art="zzz"),
           note(0.5, 0.3, 40), note(0.6, 0.3, 100), note(5.0, 1.0, 62)]
    y = play(odd, 1.0, brightness=1.0, wear=1.0, body=1.25)
    assert y.shape == (SR, 2) and np.all(np.isfinite(y)) and np.abs(y).max() > 0
    plain = play([note(0.1, 0.5, 62, art="")], 1.0)
    assert np.array_equal(play([note(0.1, 0.5, 62, art="zzz")], 1.0), plain)  # an unknown stroke is the plain one


@pytest.mark.parametrize("maker", [0, 1, 2])
def test_a_forward_roll_sits_where_the_guitars_strum_does(maker):
    notes = roll(["D", "D", "G", "A"])
    length = int((max(n.start + n.dur for n in notes) + 1.0) * SR)
    assert abs(loudness(banjo, "banjo", notes, length, maker=maker) - TARGETS["comping"]) < 1.5


def test_forty_seconds_of_rolls_cost_little():
    notes = roll(["D", "D", "G", "A"] * 5)
    play(notes[:4], 1.0)
    t = time.process_time()
    play(notes, max(n.start + n.dur for n in notes) + 1.0)
    assert time.process_time() - t < 4.0
