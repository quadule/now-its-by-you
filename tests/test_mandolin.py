"""The mandolin, measured against real mandolins: its courses and their beating, its box (Cohen and
Rossing's modes), its short ring, the tremolo and the chop, its level and its cost."""

import time

import numpy as np
import pytest
from _fretted import SR, cents, centroid, early_db, env_db, mono, render, share_db, t60
from _levels_b import TARGETS, loudness, streams
from scipy.signal import butter, sosfiltfilt

from songbird.score import Note
from songbird.synth import body, fretwork, mandolin


def note(start, dur, pitch, vel=0.6, art=""):
    return Note("mandolin", start, dur, float(pitch), vel, art=art)


def play(notes, seconds, **kw):
    return render(mandolin, "mandolin", notes, seconds, **kw)


STRUM = {"D": (57, 62, 69, 78), "G": (55, 62, 71, 79), "A": (57, 64, 73, 81)}
CHOP = {"D": (57, 66, 74, 78), "G": (59, 67, 74, 79), "A": (61, 69, 76, 81)}


def comping(chords, tempo=110.0, vel=0.6):
    """Strums down on 1 and 3 (up on 3's off-beat), chops on 2 and 4."""
    beat = 60.0 / tempo
    notes = []
    for bar, name in enumerate(chords):
        at = 4 * bar * beat
        notes += [note(at, beat, p, vel, "down") for p in STRUM[name]]
        notes += [note(at + 2 * beat, 0.5 * beat, p, vel, "down") for p in STRUM[name]]
        notes += [note(at + 2.5 * beat, 0.5 * beat, p, 0.8 * vel, "up") for p in STRUM[name][1:]]
        notes += [note(at + b * beat, 0.25 * beat, p, vel, "chop") for b in (1, 3) for p in CHOP[name]]
    return notes


# --- the courses ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("pitch", [55, 62, 69, 76, 81, 88])
def test_in_tune_across_its_register(pitch):
    y = play([note(0.05, 1.5, pitch, vel=0.5)], 1.7, wear=0.0)
    assert abs(cents(y, pitch, 0.3, 1.0)) < 2.0


def test_a_worn_courses_two_strings_beat():
    """1 cent apart new, 6 worn: an A4 held on a worn mandolin swells and fades as its strings beat."""

    def wobble(wear):
        y = mono(play([note(0.05, 2.5, 69)], 2.6, wear=wear, maker=3))
        band = sosfiltfilt(butter(2, [400, 480], btype="bandpass", fs=SR, output="sos"), y)
        env = 20 * np.log10(np.sqrt(np.convolve(band**2, np.ones(441) / 441, mode="same"))[::441] + 1e-12)
        t = np.arange(len(env)) / 100
        keep = (t > 0.3) & (t < 1.6)
        residual = env[keep] - np.polyval(np.polyfit(t[keep], env[keep], 1), t[keep])
        return residual.std()

    assert wobble(1.0) > wobble(0.0) + 0.5


def test_the_pick_meets_a_chords_courses_in_turn():
    neck = fretwork.Board(opens=tuple(map(float, mandolin.OPENS)), top=(17,) * 4, fretted=(True,) * 4,
                          order=(0, 1, 2, 3))
    for art, order in (("down", [57, 62, 69, 78]), ("up", [78, 69, 62, 57])):
        fingered = fretwork.assign([note(0.2, 0.5, p, art=art) for p in STRUM["D"]], neck)
        fretwork.spread(fingered, neck, lambda a: 0.016, np.random.default_rng(0))
        fingered.sort(key=lambda f: f.start)
        assert [f.pitch for f in fingered] == order and 0.008 < fingered[-1].start - fingered[0].start < 0.03


# --- the box, and how fast it takes the strings' energy ---------------------------------------------


def test_the_box_has_the_modes_cohen_and_rossing_measured():
    """The lowest (0,0) mode at 209 to 313 Hz (oval hole lower than f-holes), the top's (1,0) at 451
    to 575, (2,0) and (3,0) near 900 and 1100 Hz."""
    styles = set()
    for maker in range(8):
        q = mandolin._maker(streams("mandolin", 0, maker)[1])
        spec = mandolin.box(q["style"], q["low"], q["spread"], q["q"], 0.5)
        f = [m[0] for m in spec.modes]
        styles.add(q["style"])
        assert (200 <= f[0] <= 235) if q["style"] == "A" else (295 <= f[0] <= 325)
        top = f[3] if q["style"] == "A" else f[2]  # the (1,0)
        assert 430 <= top <= 680
        assert any(820 <= x <= 1060 for x in f) and any(1040 <= x <= 1300 for x in f)
    assert styles == {"A", "F"}
    freqs, db = body.response(body.impulse_response(spec, SR, seed=2), SR, n=1 << 16)
    assert np.all(db[(freqs > 40) & (freqs < 0.5 * f[0])] < db[(freqs > 0.9 * f[0]) & (freqs < 1.1 * f[0])].max() - 6)


def test_a_mandolin_dies_fast():
    """The open G course falls 60 dB in one to two seconds, the E course's high notes in half a second."""
    low, open_e, high = (t60(play([note(0.05, 3.0, p)], 3.2), 0.05) for p in (55, 76, 88))
    assert 1.1 < low < 2.2 and open_e < 0.9 and high < 0.6 and high < open_e < low


# --- the hands ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("tempo,rate", [(None, None), (120.0, 12.0), (100.0, 10.0)])
def test_a_tremolo_fills_the_note_with_picks(tempo, rate):
    """Nine to fourteen picks a second; a subdivision of the beat when the tempo is known."""
    settings = {} if tempo is None else {"tempo": tempo}
    y = mono(play([note(0.1, 2.0, 69, art="tremolo")], 2.3, **settings))
    hi = sosfiltfilt(butter(2, 3000, btype="highpass", fs=SR, output="sos"), y)
    env = np.sqrt(np.convolve(hi**2, np.ones(88) / 88, mode="same"))[int(0.2 * SR): int(2.0 * SR): 44]
    env = env - env.mean()
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    lags = np.arange(len(ac)) * 44 / SR
    window = (lags > 1 / 15) & (lags < 1 / 8)
    measured = 1.0 / lags[window][np.argmax(ac[window])]
    assert 9.0 <= measured <= 14.0
    if rate is not None:
        assert abs(measured - rate) < 0.5


def test_a_chop_is_a_short_knock():
    """30 to 60 ms of chord, then choked: 100 ms after the stroke it is 25 dB down; a strum rings on."""
    chopped = env_db(play([note(0.1, 0.5, p, art="chop") for p in CHOP["D"]], 1.0))
    strummed = env_db(play([note(0.1, 0.5, p, art="down") for p in CHOP["D"]], 1.0))
    assert chopped[20] < chopped.max() - 25 and strummed[20] > chopped[20] + 15


def test_harder_is_louder_and_brighter():
    soft, hard = (play([note(0.05, 1.5, 69, vel=v)], 1.7) for v in (0.3, 0.9))
    swing = 20 * np.log10(fretwork.dynamics(0.9) / fretwork.dynamics(0.3))
    assert abs(early_db(hard, 0.05) - early_db(soft, 0.05) - swing) < 1.5
    assert centroid(hard, 0.05, 0.25) > centroid(soft, 0.05, 0.25)
    assert share_db(hard, 4000, 16000, 0.05, 0.25) > share_db(soft, 4000, 16000, 0.05, 0.25) + 3


def test_hammer_on_pull_off_and_slide_land_on_their_notes():
    hammered = play([note(0.05, 0.3, 69), note(0.35, 1.0, 71, art="hammer")], 1.5, wear=0.0)
    assert abs(cents(hammered, 71, 0.5, 1.1)) < 3.0
    pulled = play([note(0.05, 0.3, 71), note(0.35, 1.0, 69, art="pull")], 1.5, wear=0.0)
    assert abs(cents(pulled, 69, 0.5, 1.1)) < 3.0
    slid = play([note(0.05, 1.2, 73, vel=0.5, art="slide")], 1.4, wear=0.0)
    assert cents(slid, 71, 0.05, 0.085) < 100 and abs(cents(slid, 73, 0.4, 1.1)) < 3.0


# --- the part as a whole --------------------------------------------------------------------------


def test_silent_before_its_first_note_no_dc_and_quiet_after_its_last():
    y = play([note(0.2, 0.4, p, vel=1.0, art="down") for p in STRUM["G"]] + [note(0.8, 0.2, 69, art="chop")], 3.0)
    peak = np.abs(y).max()
    assert np.abs(y[: int(0.195 * SR)]).max() < 1e-4 * peak
    for ch in range(2):
        assert abs(y[:, ch].mean()) < 1e-3 * np.sqrt(np.mean(y[:, ch] ** 2))
    assert np.abs(y[-int(0.05 * SR):]).max() < 1e-3 * peak


def test_a_stopped_note_ends_without_a_click():
    from scipy.signal import sosfilt

    y = mono(play([note(0.1, 0.6, 69, vel=0.8)], 1.2))
    hi = sosfilt(butter(4, 8000, btype="highpass", fs=SR, output="sos"), y)
    attack = np.sqrt(np.mean(hi[int(0.1 * SR): int(0.13 * SR)] ** 2))
    stop = np.sqrt(np.mean(hi[int(0.7 * SR): int(0.73 * SR)] ** 2))
    assert stop < 0.01 * attack


def test_the_same_maker_plays_the_same_mandolin_and_another_maker_another():
    notes = [note(0.1 + 0.2 * k, 0.4, p) for k, p in enumerate((62, 66, 69, 74, 76))]
    a = play(notes, 1.6)
    assert np.array_equal(a, play(notes, 1.6))
    assert not np.allclose(a, play(notes, 1.6, maker=5))
    lows = {mandolin._maker(streams("mandolin", 0, m)[1])["low"] for m in (0, 5)}
    assert len(lows) == 2


def test_any_part_renders():
    assert np.array_equal(play([], 1.0), np.zeros((SR, 2)))
    odd = [note(0.1, 0.001, 55, vel=1.0), note(0.2, 0.5, 88, vel=0.0), note(0.3, 0.2, 62, art="zzz"),
           note(0.4, 0.3, 40, art="tremolo"), note(0.6, 0.3, 100, art="chop"), note(5.0, 1.0, 62)]
    y = play(odd, 1.0, brightness=1.0, wear=1.0, body=0.8, tempo=200.0)
    assert y.shape == (SR, 2) and np.all(np.isfinite(y)) and np.abs(y).max() > 0
    assert np.array_equal(play([note(0.1, 0.5, 62, art="zzz")], 1.0), play([note(0.1, 0.5, 62)], 1.0))


@pytest.mark.parametrize("maker", [0, 1, 2])
def test_chops_and_strums_sit_where_the_guitars_strum_does(maker):
    notes = comping(["D", "D", "G", "A"])
    length = int((max(n.start + n.dur for n in notes) + 1.0) * SR)
    assert abs(loudness(mandolin, "mandolin", notes, length, maker=maker) - TARGETS["comping"]) < 1.5


def test_forty_seconds_of_comping_cost_little():
    notes = comping(["D", "D", "G", "A"] * 5)
    play(notes[:4], 1.0)
    t = time.process_time()
    play(notes, max(n.start + n.dur for n in notes) + 1.0)
    assert time.process_time() - t < 4.0
