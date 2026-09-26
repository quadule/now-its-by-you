"""Nylon strings: a classical guitar and a ukulele, measured against their steel cousin and each other."""

import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import butter, sosfiltfilt

from _levels_b import TARGETS, loudness
from songbird.score import Note
from songbird.synth import nylon

SR = 44100


def render(name, pitch, vel=0.6, art="", dur=2.5, maker=0, seed=0, **settings):
    s = dict(brightness=0.5, wear=0.0, ornament=0.0, body=1.0, maker=maker, **settings)
    notes = (Note(name, 0.1, dur - 0.4, float(pitch), vel, art=art),)
    y = nylon.render(name, notes, SR, int(dur * SR), np.random.default_rng([seed, 3]),
                     np.random.default_rng([maker, 4]), s)
    return y.mean(axis=1)


def f0(y, guess, t0=0.3, t1=1.5):
    seg = y[int(t0 * SR): int(t1 * SR)] * np.hanning(int(t1 * SR) - int(t0 * SR))
    spec = np.abs(np.fft.rfft(seg, 16 * SR))
    freqs = np.fft.rfftfreq(16 * SR, 1 / SR)
    band = (freqs > guess * 0.97) & (freqs < guess * 1.03)
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


def centroid(y, t0, t1):
    seg = y[int(t0 * SR): int(t1 * SR)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    return float(np.sum(f * spec) / np.sum(spec))


def db(y, t0, t1):
    return 10 * np.log10(np.mean(y[int(t0 * SR): int(t1 * SR)] ** 2) + 1e-20)


@pytest.mark.parametrize("name,pitch", [("nylon", 40), ("nylon", 57), ("nylon", 76), ("ukulele", 60), ("ukulele", 79)])
def test_in_tune(name, pitch):
    y = render(name, pitch)
    f = 440 * 2 ** ((pitch - 69) / 12)
    assert abs(1200 * np.log2(f0(y, f) / f)) < 2.0


def test_nylon_is_round_and_grows_rounder():
    y = render("nylon", 57, dur=3.0)
    early, late = centroid(y, 0.12, 0.3), centroid(y, 1.5, 2.5)
    assert 300 < early < 1200  # an A3: a few harmonics over its 220 Hz
    assert late < 0.8 * early  # its upper harmonics die first
    # nylon's own friction: the same pluck on a frictionless (steel-like) loop keeps its top far longer
    common = dict(vel=0.6, brightness=0.5, decay=2.8, pick=0.17, hardness=0.45)
    steel = nylon.stringloop.note(220.0, 2.6, SR, np.random.default_rng(0), **common)
    gut = nylon.stringloop.note(220.0, 2.6, SR, np.random.default_rng(0), pole=nylon._pole(220.0, SR, 5.6, 0.011),
                                **common)
    assert centroid(gut, 0.05, 0.3) < 0.8 * centroid(steel, 0.05, 0.3)
    assert centroid(gut, 0.5, 1.0) < 0.8 * centroid(steel, 0.5, 1.0)


def test_decays_as_nylon_does():
    for pitch, lo, hi in ((40, 3.0, 12.0), (64, 1.2, 6.0)):
        y = render("nylon", pitch, dur=5.0)
        f = 440 * 2 ** ((pitch - 69) / 12)
        band = sosfiltfilt(butter(2, [f * 0.8, f * 1.25], btype="bandpass", fs=SR, output="sos"), y)
        hop = SR // 20
        env = 20 * np.log10(np.sqrt(np.convolve(band ** 2, np.ones(hop) / hop, mode="valid"))[::hop] + 1e-12)
        slope = np.polyfit(np.arange(10, 60) / 20, env[10:60], 1)[0]
        assert lo < -60 / slope < hi  # the fundamental's T60
    uke = render("ukulele", 69, dur=3.0)
    assert db(uke, 1.8, 2.3) < db(uke, 0.15, 0.4) - 20  # a ukulele's short sustain


def test_the_body_breathes_near_its_air_mode():
    freqs, response = nylon.body.response(nylon.body.impulse_response(nylon.CLASSICAL, SR, seed=0), SR, n=1 << 17)
    band = (freqs > 70) & (freqs < 130)
    assert 85 < freqs[band][np.argmax(response[band])] < 112


def test_strokes_and_dynamics():
    free, rest = render("nylon", 64, art=""), render("nylon", 64, art="rest")
    assert db(rest, 0.1, 0.4) > db(free, 0.1, 0.4) + 0.5
    assert centroid(render("nylon", 64, art="pont"), 0.12, 0.4) > 1.2 * centroid(render("nylon", 64, art="tasto"), 0.12, 0.4)
    soft, hard = render("nylon", 64, vel=0.3), render("nylon", 64, vel=0.9)
    assert db(hard, 0.1, 0.5) > db(soft, 0.1, 0.5) + 6 and centroid(hard, 0.12, 0.4) > centroid(soft, 0.12, 0.4)


def test_a_pinched_chord_spreads_and_everything_renders():
    notes = tuple(Note("nylon", 0.2, 0.5, p, 0.7, art=a) for p in (50, 57, 62, 66)
                  for a in ("rasgueado",)) + (Note("nylon", 1.0, 0.1, 60, 0.7, art="golpe"),
                                              Note("nylon", 1.2, 1.0, 62, 0.6, art="tremolo"),
                                              Note("nylon", 1.4, 0.5, 74, 0.6, art="harmonic"),
                                              Note("nylon", 1.5, 0.001, 40, 1.0, art="no-such-art"),
                                              Note("nylon", 1.6, 0.3, 83, 0.0, art="slur"))
    y = nylon.render("nylon", notes, SR, int(3 * SR), np.random.default_rng(1), np.random.default_rng(2), {})
    assert y.shape == (3 * SR, 2) and np.all(np.isfinite(y))
    assert np.max(np.abs(y[: int(0.19 * SR)])) < 1e-4 * np.max(np.abs(y))  # nothing before the first note
    x = y[: int(3 * SR)]
    assert np.all(np.abs(x.mean(axis=0)) < 1e-3 * np.sqrt(np.mean(x ** 2, axis=0)))
    a = nylon.render("nylon", notes, SR, SR, np.random.default_rng(1), np.random.default_rng(2), {})
    assert np.array_equal(a, nylon.render("nylon", notes, SR, SR, np.random.default_rng(1), np.random.default_rng(2), {}))
    empty = nylon.render("ukulele", (), SR, 100, np.random.default_rng(0), np.random.default_rng(0), {})
    assert empty.shape == (100, 2) and not np.any(empty)


@pytest.mark.parametrize("name", ["nylon", "ukulele"])
@pytest.mark.parametrize("maker", [0, 1, 2])
def test_comping_sits_with_the_guitar(name, maker):
    sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "instrument_phrases_b"))
    import nylon as phrases

    notes = phrases.LEVELS[name][1]
    length = int((max(n.start + n.dur for n in notes) + 1.0) * SR)
    assert abs(loudness(nylon, name, notes, length, maker=maker) - TARGETS["comping"]) < 1.5
