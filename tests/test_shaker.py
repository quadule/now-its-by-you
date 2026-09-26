"""Shaken things (shaker.py): a shaker and a tambourine, measured against what beads, shells and jingles do."""

import numpy as np
import pytest

from _levels_b import SETTINGS, loudness, streams
from _percussion_b import contract, target
from songbird.score import Note
from songbird.synth import shaker

SR = 44100


def play(name, notes, seconds, maker=0, seed=0, **settings):
    rng, make = streams(name, seed, maker)
    return shaker.render(name, tuple(notes), SR, int(seconds * SR), rng, make, {**SETTINGS, "maker": maker, **settings})


def hits(name, art, n=6, gap=0.8, vel=0.7, start=0.2):
    return [Note(name, start + i * gap, 0.1, 60.0, vel, art=art) for i in range(n)]


def power_spectrum(y, t0=0.0, t1=None):
    seg = y[int(t0 * SR): int(t1 * SR) if t1 else None]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16)) ** 2
    return np.fft.rfftfreq(1 << 16, 1 / SR), spec


def centroid(y, t0=0.0, t1=None):
    f, p = power_spectrum(y, t0, t1)
    return (f * p).sum() / p.sum()


def smooth_peak(y, lo, hi, width=300.0):
    f, p = power_spectrum(y)
    k = int(width / (f[1] - f[0]))
    p = np.convolve(p, np.ones(k) / k, mode="same")
    band = (f > lo) & (f < hi)
    return f[band][np.argmax(p[band])]


def envelope_db(y, seconds=0.01):
    n = int(seconds * SR)
    return 10 * np.log10(np.convolve(y**2, np.ones(n) / n, mode="same") + 1e-24)


def makers_of(name, kind):
    """Makers whose instrument is of this kind (the shaker's kind, or a tambourine headed or not)."""
    out = []
    for maker in range(12):
        rng, make = streams(name, 0, maker)
        built = shaker._shaker(make, 1.0, 0.5, 0.25) if name == "shaker" else shaker._tambourine(make, 1.0, 0.5, 0.25)
        if (built["kind"] if name == "shaker" else built["headed"]) == kind:
            out.append((maker, built))
    return out


@pytest.mark.parametrize("name,plain", [("shaker", "shaker"), ("tambourine", "tambourine")])
def test_the_contract(name, plain):
    notes = hits(name, plain, n=3)
    y = play(name, notes, 3.0)
    assert y.shape == (3 * SR,) and np.all(np.isfinite(y)) and np.abs(y).max() > 0
    assert np.array_equal(y, play(name, notes, 3.0))
    assert not np.allclose(y, play(name, notes, 3.0, maker=1))
    assert not np.allclose(y, play(name, notes, 3.0, seed=1))
    assert not np.any(play(name, [], 1.0))
    late = notes + [Note(name, 5.0, 0.1, 60.0, 0.7, art=plain)]
    assert np.array_equal(play(name, late, 3.0), y)
    unknown = [Note(name, n.start, n.dur, n.pitch, n.vel, art="clap") for n in notes]
    assert np.array_equal(play(name, unknown, 3.0), y)
    assert abs(y.mean()) < 1e-3 * np.sqrt(np.mean(y**2))


@pytest.mark.parametrize("kind", ["egg", "gourd", "tube"])
def test_a_shaker_rings_its_shell(kind):
    """Cook 1997: a maraca's shell rings near 3.2 kHz; an egg is brighter, a tube of sand in between.
    The strongest part of the spectrum is one of the maker's shell resonances."""
    maker, sh = makers_of("shaker", kind)[0]
    y = play("shaker", hits("shaker", "shaker", n=8, gap=0.5, vel=0.8), 4.5, maker=maker)
    peak = smooth_peak(y, 1000, 16000)
    assert min(abs(np.log2(peak / f)) for f in sh["shell"][0]) < 0.3
    assert 3000 < centroid(y) < 9000


def test_a_shake_is_a_crowd_of_impacts_that_settles():
    for kind in ("egg", "gourd", "tube"):
        maker, sh = makers_of("shaker", kind)[0]
        y = play("shaker", [Note("shaker", 0.2, 0.1, 60.0, 0.8, art="shaker")], 1.0, maker=maker)
        db = envelope_db(y)[int(0.2 * SR): int(0.7 * SR)]
        top = np.argmax(db)
        assert 0.04 < np.argmax(db[top:] < db[top] - 30) / SR < 0.25  # a stroke settles in about a tenth
        # grains, not hiss: against its own 5 ms envelope, the stroke's tail is far spikier than noise (3)
        tail = y[int((0.2 + top / SR + 0.02) * SR): int((0.2 + top / SR + 0.08) * SR)]
        smooth = np.sqrt(np.convolve(tail**2, np.ones(220) / 220, mode="same")) + 1e-12
        z = tail / smooth
        assert np.mean(z**4) / np.mean(z**2) ** 2 > 4.0


def test_forward_strokes_are_accented_on_the_eighths():
    six = [Note("shaker", 0.2 + i * 0.15, 0.05, 60.0, 0.6, art="shaker") for i in range(32)]
    for tempo in (0.0, 100.0):
        y = play("shaker", six, 5.5, maker=1, tempo=tempo)
        level = [np.sqrt(np.mean(y[int(n.start * SR): int((n.start + 0.04) * SR)] ** 2)) for n in six]
        on, off = (np.mean(level[0::2]), np.mean(level[1::2]))
        if tempo:  # 0.2 s is a sixteenth past the beat at 100 BPM: the odd strokes land on the eighths
            on, off = off, on
        assert 3.0 < 20 * np.log10(on / off) < 9.0


def test_a_roll_is_held_for_the_note():
    y = play("shaker", [Note("shaker", 0.2, 2.0, 60.0, 0.6, art="shaker-roll")], 3.0, maker=0)
    db = envelope_db(y, 0.02)[int(0.4 * SR): int(2.1 * SR)]
    assert np.percentile(db, 95) - np.percentile(db, 5) < 12.0
    assert envelope_db(y, 0.05)[int(2.6 * SR)] < np.median(db) - 30  # and stops after it


def test_the_jingles_ring_where_cooks_do():
    """Cook 1997: a tambourine's jingles ring near 5.6 and 8.1 kHz and its frame near 2.3 kHz; a crash
    rings down in a few tenths of a second."""
    for maker, tb in makers_of("tambourine", False)[:2]:
        y = play("tambourine", hits("tambourine", "tambourine", n=4, gap=1.0, vel=0.8), 4.8, maker=maker)
        assert 4000 < centroid(y) < 9000
        db = envelope_db(y, 0.005)[int(0.2 * SR): int(1.15 * SR)]
        top = np.argmax(db)
        assert 0.25 < np.argmax(db[top:] < db[top] - 40) / SR < 0.8


def test_a_headed_tambourine_thumps_and_a_tap_does_not():
    maker, tb = makers_of("tambourine", True)[0]
    hit = play("tambourine", hits("tambourine", "tambourine", n=4, gap=1.0), 4.8, maker=maker)
    tap = play("tambourine", hits("tambourine", "tambourine-tap", n=4, gap=1.0), 4.8, maker=maker)
    assert 0.8 * tb["skin"][0] < smooth_peak(hit, 100, 800, 20.0) < 1.25 * tb["skin"][0]

    def low(y):
        f, p = power_spectrum(y)
        return 10 * np.log10(p[(f > 100) & (f < 800)].sum() / p.sum())

    assert low(hit) > -10 and low(tap) < -25
    assert -20 < 10 * np.log10(np.mean(tap**2) / np.mean(hit**2)) < -10


@pytest.mark.parametrize("name,art", [("shaker", "shaker"), ("tambourine", "tambourine")])
def test_harder_is_louder_and_brighter(name, art):
    notes = [hits(name, art, n=4, gap=1.0, vel=v) for v in (0.3, 0.95)]
    soft, loud = (play(name, n, 4.8, maker=1) for n in notes)
    assert np.sqrt(np.mean(loud**2)) > 3.0 * np.sqrt(np.mean(soft**2))
    bright = [np.mean([centroid(y, n.start, n.start + 0.05) for n in notes[0]]) for y in (soft, loud)]
    assert bright[1] > 1.1 * bright[0]


@pytest.mark.parametrize("name,part", [
    ("shaker", [Note("shaker", i * 0.15, 0.05, 60.0, 0.6, art="shaker") for i in range(128)]),
    ("tambourine", [Note("tambourine", b * 0.6, 0.1, 60.0, 0.6, art="tambourine") for b in range(1, 32, 2)]),
    ("tambourine", [Note("tambourine", i * 0.3, 0.1, 60.0, 0.6, art="tambourine-shake") for i in range(64)]),
])
def test_a_typical_part_sits_at_the_frame_drums_level(name, part):
    """Sixteenths on the shaker, a palm on 2 and 4 or shaken eighths on the tambourine, 100 BPM, vel 0.6."""
    levels = [loudness(shaker, name, part, int(20.5 * SR), maker=maker) for maker in range(3)]
    assert all(abs(level - target(shaker, name)) < 1.5 for level in levels)


@pytest.mark.parametrize("name,plain,part", [
    ("shaker", "shaker", [Note("shaker", i * 0.15, 0.05, 60.0, 0.6, art="shaker") for i in range(16)]),
    ("tambourine", "tambourine", [Note("tambourine", i * 0.3, 0.1, 60.0, 0.6, art="tambourine-shake" if i % 2 else
                                       "tambourine") for i in range(8)]),
])
def test_the_registrys_contract(name, plain, part):
    contract(shaker, name, plain, part)
