"""The drum kit, measured against real kits: tunings, decays, spectra, dynamics, the hi-hat's pedal, level."""

import numpy as np
import pytest
from scipy.signal import butter, sosfiltfilt

from _levels_b import TARGETS, loudness
from songbird.score import Note
from songbird.synth import kit

SR = 44100


def render(arts, vel=0.8, dur=2.0, maker=0, seed=0, times=None, durs=None, **settings):
    notes = [Note("kit", 0.1 if times is None else times[k], 0.2 if durs is None else durs[k], 38.0, vel, art=art)
             for k, art in enumerate(arts)]
    s = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0, maker=maker, **settings)
    y = kit.render("kit", tuple(notes), SR, int(dur * SR), np.random.default_rng([seed, 17, 5]),
                   np.random.default_rng([maker, 29, 5]), s)
    return y.mean(axis=1)


def band(y, lo, hi):
    return sosfiltfilt(butter(4, [lo, hi], btype="bandpass", fs=SR, output="sos"), y)


def env_db(y, hop=0.005):
    n = int(hop * SR)
    k = len(y) // n
    return 20 * np.log10(np.sqrt(np.mean(y[: k * n].reshape(k, n) ** 2, axis=1)) + 1e-12)


def t60(y, lo, hi, top=-5, bottom=-35):
    e = env_db(band(y, lo, hi))
    pk = int(np.argmax(e))
    seg = e[pk:]
    a, b = int(np.argmax(seg < seg[0] + top)), int(np.argmax(seg < seg[0] + bottom))
    return -60.0 / np.polyfit(np.arange(a, b) * 0.005, seg[a:b], 1)[0]


def strongest(y, lo, hi, t0=0.1, t1=0.6):
    seg = y[int(t0 * SR): int(t1 * SR)] * np.hanning(int(t1 * SR) - int(t0 * SR))
    spec = np.abs(np.fft.rfft(seg, 1 << 18))
    f = np.fft.rfftfreq(1 << 18, 1 / SR)
    sel = (f > lo) & (f < hi)
    return f[sel][np.argmax(spec[sel])]


def centroid(y, t0, t1):
    seg = y[int(t0 * SR): int(t1 * SR)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    return float(np.sum(f * spec) / np.sum(spec))


def early_db(y, t=0.1, w=0.1):
    return 20 * np.log10(np.sqrt(np.mean(y[int(t * SR): int((t + w) * SR)] ** 2)) + 1e-12)


@pytest.mark.parametrize("maker", [0, 1, 2])
def test_the_drums_are_tuned_as_kits_are(maker):
    kick = render(["kick"], maker=maker)
    assert 44 < strongest(kick, 30, 150) < 70  # a 22-inch kick's fundamental: 50-65 Hz
    assert 0.25 < t60(kick, 30, 150) < 0.7
    snare = render(["snare"], maker=maker)
    assert 150 < strongest(snare, 100, 260) < 240  # the lower of the heads' pair (Rossing: 182 and 330 Hz)
    assert 0.13 < t60(snare, 120, 600) < 0.32  # the batter dies quickly with the wires on
    toms = [strongest(render([t], maker=maker), 50, 260, 0.35, 0.9) for t in ("tom-hi", "tom-mid", "tom-lo")]
    assert toms[0] > toms[1] > toms[2] and 70 < toms[2] < 110 and 120 < toms[0] < 210


def test_a_hard_tom_hit_starts_sharp_and_falls_back():
    y = render(["tom-mid"], vel=1.0)
    early = strongest(y, 60, 250, 0.1, 0.16)
    late = strongest(y, 60, 250, 0.45, 0.95)
    assert 1.03 < early / late < 1.15  # about a semitone of glide


def test_the_snare_wires_buzz_on_after_the_head_and_brighten_the_snare():
    y = render(["snare"])
    wires = env_db(band(y, 2000, 9000))
    pk = int(np.argmax(wires))
    assert 0.25 < np.argmax(wires[pk:] < wires[pk] - 40) * 0.005 < 0.7  # the buzz lasts 0.3-0.5 s
    assert 1000 < centroid(y, 0.1, 0.15) < 3500


def test_ghost_notes_are_soft_and_dull():
    ghost, accent = render(["snare"], vel=0.2), render(["snare"], vel=1.0)
    assert -26 < early_db(ghost) - early_db(accent) < -14
    assert centroid(ghost, 0.1, 0.2) < 0.7 * centroid(accent, 0.1, 0.2)


@pytest.mark.parametrize("art", ["snare", "hat", "ride", "kick", "tom-lo"])
def test_harder_is_louder_and_brighter(art):
    soft, hard = render([art], vel=0.25, dur=1.0), render([art], vel=0.9, dur=1.0)
    assert early_db(hard) > early_db(soft) + 12
    assert centroid(hard, 0.1, 0.2) > centroid(soft, 0.1, 0.2)


def test_the_hi_hat_pedal():
    closed = render(["hat"])
    assert 0.04 < t60(closed, 3000, 16000) < 0.16
    assert 5000 < centroid(closed, 0.1, 0.16) < 11000
    ringing = render(["hat-open"], dur=3.0)
    assert t60(ringing, 4000, 16000) > 0.8  # open, with nothing to close it, it rings on
    # an open hat closed by the next stroke: silent a little after, bar that stroke's own short tick
    shut = render(["hat-open", "hat"], times=[0.1, 0.6], dur=2.0)
    late = np.sqrt(np.mean(band(shut, 3000, 16000)[int(0.9 * SR): int(1.2 * SR)] ** 2))
    free = np.sqrt(np.mean(band(ringing, 3000, 16000)[int(0.9 * SR): int(1.2 * SR)] ** 2))
    assert late < 0.05 * free


def test_the_cymbals_ring_as_bronze_does():
    ride = render(["ride"], dur=6.0)
    assert t60(ride, 300, 1000) > 5.0 and t60(ride, 4000, 10000) > 2.0
    assert 1500 < centroid(ride, 0.6, 2.1) < 3500
    soft, hard = render(["crash"], vel=0.4, dur=4.0), render(["crash"], vel=1.0, dur=4.0)
    assert 2.0 < t60(hard, 1000, 3000) < 8.0 and 1.0 < t60(hard, 4000, 10000) < 4.0
    # a hard crash blooms: its top swells for tens of milliseconds after the strike
    e = env_db(band(hard, 4000, 10000), hop=0.002)[int(0.1 / 0.002):]
    smooth = np.convolve(e[:100], np.ones(5) / 5, mode="valid")  # 10 ms
    assert 0.008 < (np.argmax(smooth) + 2) * 0.002 < 0.1
    assert centroid(hard, 0.12, 0.18) > 1.2 * centroid(soft, 0.12, 0.18)


def test_a_choke_stops_the_crash():
    free = render(["crash"], dur=3.0)
    choked = render(["crash-choke"], durs=[0.5], dur=3.0)
    later = slice(int(1.0 * SR), int(1.5 * SR))
    assert np.sqrt(np.mean(choked[later] ** 2)) < 0.02 * np.sqrt(np.mean(free[later] ** 2))


def test_implements_and_strokes():
    stick = early_db(render(["snare"], vel=0.7))
    assert early_db(render(["brush-tap"], vel=0.7)) < stick - 4  # brushes are quieter
    assert early_db(render(["snare:rod"], vel=0.7)) < stick  # rods lighter than sticks
    assert early_db(render(["rim"], vel=0.7)) > stick + 1  # a rim shot cracks louder
    sweep = render(["brush-sweep"], durs=[0.8], dur=1.2)
    assert np.sqrt(np.mean(sweep[int(0.3 * SR): int(0.7 * SR)] ** 2)) > 0  # a sustained swish
    assert 1500 < centroid(sweep, 0.3, 0.7) < 7000
    cross = render(["cross"], vel=0.7)
    assert 500 < centroid(cross, 0.1, 0.13) < 4000


def test_arts_fall_back_and_general_midi_pitches_name_pieces():
    unknown = render(["woodblock"])
    assert np.all(np.isfinite(unknown)) and np.any(unknown)
    notes = (Note("kit", 0.1, 0.1, 36.0, 0.8), Note("kit", 0.5, 0.1, 42.0, 0.8))
    y = kit.render("kit", notes, SR, SR, np.random.default_rng(1), np.random.default_rng(2), {})
    assert strongest(y.mean(axis=1), 30, 150, 0.1, 0.4) < 75  # 36 is a kick
    assert kit.parse("", 46) == ("hat-open", "stick") and kit.parse("ride:brush") == ("ride", "brush")


def test_deterministic_seeded_by_its_maker_no_dc():
    a = render(["kick", "snare", "hat", "crash"], times=[0.1, 0.3, 0.5, 0.7], maker=4)
    b = render(["kick", "snare", "hat", "crash"], times=[0.1, 0.3, 0.5, 0.7], maker=4)
    c = render(["kick", "snare", "hat", "crash"], times=[0.1, 0.3, 0.5, 0.7], maker=5)
    assert np.array_equal(a, b) and not np.allclose(a, c)
    assert abs(a.mean()) < 1e-3 * np.sqrt(np.mean(a ** 2))
    empty = kit.render("kit", (), SR, 1000, np.random.default_rng(0), np.random.default_rng(0), {})
    assert empty.shape == (1000, 2) and not np.any(empty)


@pytest.mark.parametrize("maker", [0, 1, 2])
def test_a_groove_sits_at_the_frame_drums_level(maker):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "instrument_phrases_b"))
    import kit as phrases

    notes = phrases.LEVELS["kit"][1]
    length = int((max(n.start for n in notes) + 2.0) * SR)
    assert abs(loudness(kit, "kit", notes, length, maker=maker) - TARGETS["percussion"]) < 1.5
