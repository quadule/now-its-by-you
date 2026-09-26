"""Body percussion (hand.py): claps and stomps, measured against what hands and wooden floors do."""

import numpy as np
import pytest
from scipy.signal import butter, sosfiltfilt

from _levels_b import SETTINGS, TARGETS, loudness, streams
from songbird.score import Note
from songbird.synth import hand

SR = 44100


def play(name, notes, seconds, maker=0, seed=0, **settings):
    rng, make = streams(name, seed, maker)
    return hand.render(name, tuple(notes), SR, int(seconds * SR), rng, make, {**SETTINGS, "maker": maker, **settings})


def hits(name, art, n=6, gap=0.8, vel=0.7):
    return [Note(name, 0.2 + i * gap, 0.1, 60.0, vel, art=art) for i in range(n)]


def power_spectrum(y, t0=0.0, t1=None):
    y = y.mean(axis=1) if y.ndim == 2 else y
    seg = y[int(t0 * SR): int(t1 * SR) if t1 else None]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16)) ** 2
    return np.fft.rfftfreq(1 << 16, 1 / SR), spec


def centroid(y, t0=0.0, t1=None):
    f, p = power_spectrum(y, t0, t1)
    return (f * p).sum() / p.sum()


def band(y, lo, hi, t0=0.0, t1=None):
    f, p = power_spectrum(y, t0, t1)
    return 10 * np.log10(p[(f >= lo) & (f < hi)].sum() + 1e-30)


@pytest.mark.parametrize("name,plain", [("claps", "clap"), ("stomps", "stomp")])
def test_the_contract(name, plain):
    notes = hits(name, plain, n=3)
    y = play(name, notes, 3.0)
    assert y.shape == (3 * SR, 2) and np.all(np.isfinite(y)) and np.abs(y).max() > 0
    assert np.array_equal(y, play(name, notes, 3.0))  # the same streams play the same part
    assert not np.allclose(y, play(name, notes, 3.0, maker=1))  # another maker, another group and floor
    assert not np.allclose(y, play(name, notes, 3.0, seed=1))  # another performance
    assert not np.any(play(name, [], 1.0))
    late = notes + [Note(name, 5.0, 0.1, 60.0, 0.7, art=plain)]
    assert np.array_equal(play(name, late, 3.0), y)  # a note past the end is ignored
    unknown = [Note(name, n.start, n.dur, n.pitch, n.vel, art="cajon-slap") for n in notes]
    assert np.array_equal(play(name, unknown, 3.0), y)  # an art it doesn't know is its plain stroke
    assert abs(y.mean()) < 1e-3 * np.sqrt(np.mean(y**2))  # no DC


def test_each_persons_clap_rings_in_their_hands_pocket():
    """Repp 1987, Peltola et al. 2007: a clap's resonance sits between about 0.7 kHz (cupped hands) and
    2.4 kHz (flat), a few hundred hertz wide; that is where a clap's energy is."""
    for maker in range(4):
        rng, make = streams("claps", 0, maker)
        leader = hand._clappers(make, 1.0)[0]
        y = play("claps", hits("claps", "clap-solo", n=8), 7.0, maker=maker)
        f, p = power_spectrum(y)
        inside = (f > 300) & (f < 6000)
        assert abs(np.log2(f[inside][np.argmax(p[inside])] / leader["fc"])) < 0.25
        assert 1000 < centroid(play("claps", hits("claps", "clap", n=8), 7.0, maker=maker)) < 3500


def test_a_clap_lasts_milliseconds_and_a_group_spreads_like_a_band_clapping_along():
    rng, make = streams("claps", 0, 0)
    people = hand._clappers(make, 1.0)
    for i, p in enumerate(people):
        y = hand._clap(p, 0.7, SR, np.random.default_rng(i), 0.5)
        c = np.cumsum(y**2) / np.sum(y**2)
        assert (np.argmax(c > 0.95) - np.argmax(c > 0.05)) / SR < 0.008

    def spread(wear):
        spans = []
        for k in range(8):
            y = play("claps", hits("claps", "clap", n=1), 1.0, maker=k % 3, seed=k, wear=wear).sum(axis=1)
            c = np.cumsum(y**2) / np.sum(y**2)
            spans.append((np.argmax(c > 0.95) - np.argmax(c > 0.05)) / SR)
        return np.median(spans)

    assert 0.008 < spread(0.25) < 0.025
    assert spread(1.0) > spread(0.0) + 0.006  # a worn group is looser


def test_the_floor_booms_for_a_few_tenths_and_the_boards_knock():
    low = butter(4, [30, 200], btype="bandpass", fs=SR, output="sos")
    for maker in range(3):
        y = play("stomps", hits("stomps", "stomp", n=3, gap=1.5), 5.0, maker=maker)
        f, p = power_spectrum(y, 0.2, 1.2)
        inside = (f > 20) & (f < 400)
        assert 38 < f[inside][np.argmax(p[inside])] < 120  # the boom
        knock = band(y, 200, 2000, 0.2, 0.3) - band(y, 30, 200, 0.2, 0.3)
        assert -16 < knock < -2  # the boards knock under it
        env = np.sqrt(np.convolve(sosfiltfilt(low, y.mean(axis=1)) ** 2, np.ones(441) / 441, mode="same"))
        db = 20 * np.log10(env[: int(1.6 * SR)] + 1e-12)
        top = np.argmax(db)
        t60 = 2.0 * (np.argmax(db[top:] < db[top] - 35) - np.argmax(db[top:] < db[top] - 5)) / SR
        assert 0.15 < t60 < 0.7


@pytest.mark.parametrize("name,art,t1", [("claps", "clap", 0.25), ("stomps", "stomp", 0.25)])
def test_harder_is_louder_and_brighter(name, art, t1):
    soft, loud = (play(name, hits(name, art, vel=v), 5.0, maker=1) for v in (0.35, 0.95))
    assert np.sqrt(np.mean(loud**2)) > 3.0 * np.sqrt(np.mean(soft**2))
    starts = [n.start for n in hits(name, art)]
    bright = [np.mean([centroid(y, t, t + t1 - 0.2) for t in starts]) for y in (soft, loud)]
    assert bright[1] > 1.1 * bright[0]


def test_the_spectrum_falls_away_at_the_top_and_the_tail_is_quiet():
    for name, art in (("claps", "clap"), ("stomps", "stomp")):
        y = play(name, hits(name, art, n=1), 2.0)
        f, p = power_spectrum(y)
        top, upper = p[f > 16000].sum(), p[(f > 8000) & (f <= 16000)].sum()
        assert top < 3e-3 * p.sum() and top < upper  # falling past 8 kHz, nothing folded back from above
        assert np.abs(y[int(1.8 * SR):]).max() < 1e-3 * np.abs(y).max()  # rung out, nothing left to click


@pytest.mark.parametrize("name,art,beats", [("claps", "clap", range(1, 32, 2)), ("stomps", "stomp", range(0, 32, 2))])
def test_a_typical_part_sits_at_the_frame_drums_level(name, art, beats):
    """Claps on 2 and 4, stomps on 1 and 3, at 100 BPM, vel 0.6: at the frame drum's level whoever made them."""
    part = [Note(name, b * 0.6, 0.1, 60.0, 0.6, art=art) for b in beats]
    levels = [loudness(hand, name, part, int(20.0 * SR), maker=maker) for maker in range(3)]
    assert all(abs(level - TARGETS["percussion"]) < 1.5 for level in levels)
