"""The cajon (cajon.py): a box's air through its hole, a thin face, snares behind it, measured."""

import numpy as np
import pytest
from scipy.signal import butter, sosfiltfilt

from _levels_b import loudness, streams
from _percussion_b import contract, play, target
from songbird.score import Note
from songbird.synth import cajon

SR = 44100


def strokes(art, n=4, gap=1.0, vel=0.8):
    return [Note("cajon", 0.2 + i * gap, 0.1, 60.0, vel, art=art) for i in range(n)]


def built(maker, size=1.0):
    rng, make = streams("cajon", 0, maker)
    return cajon._cajon(make, size, 0.5, 0.25, SR)


def power_spectrum(y, t0=0.0, t1=None):
    seg = y[int(t0 * SR): int(t1 * SR) if t1 else None]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 17)) ** 2
    return np.fft.rfftfreq(1 << 17, 1 / SR), spec


def centroid(y, t0=0.0, t1=None):
    f, p = power_spectrum(y, t0, t1)
    return (f * p).sum() / p.sum()


def envelope_db(y, seconds=0.005):
    n = int(seconds * SR)
    return 10 * np.log10(np.convolve(y**2, np.ones(n) / n, mode="same") + 1e-24)


GROOVE = sorted([Note("cajon", b * 0.6, 0.1, 60.0, 0.6, art="cajon-bass" if b % 2 == 0 else "cajon-slap")
                 for b in range(32)] + [Note("cajon", (b + q / 4) * 0.6, 0.05, 60.0, 0.6, art="cajon-tap")
                                        for b in range(32) for q in (1, 3)], key=lambda n: n.start)


def test_the_registrys_contract():
    contract(cajon, "cajon", "cajon-slap", GROOVE[:12])
    y = play(cajon, "cajon", strokes("cajon-bass", n=2), 2.5)
    assert np.array_equal(y, play(cajon, "cajon", strokes("cajon-bass", n=2), 2.5))
    assert not np.allclose(y, play(cajon, "cajon", strokes("cajon-bass", n=2), 2.5, maker=1))
    kick = [Note("cajon", n.start, n.dur, n.pitch, n.vel, art="kick") for n in strokes("cajon-bass", n=2)]
    assert np.array_equal(play(cajon, "cajon", kick, 2.5), y)  # a drummer's kick is the cajon's bass


def test_the_air_breathes_through_the_hole():
    """A 30 x 30 x 48 cm box with a 10 to 12 cm hole is a Helmholtz resonator near 85 Hz; coupled to the face
    (its own first mode 120 to 160 Hz) the pair splits, and the lower, the boom, is a bass stroke's peak."""
    for maker in range(3):
        cj = built(maker)
        assert 78 < cj["helmholtz"] < 95
        assert cj["pair"][0] < min(cj["helmholtz"], cj["face"]) and cj["pair"][1] > max(cj["helmholtz"], cj["face"])
        y = play(cajon, "cajon", strokes("cajon-bass"), 4.5, maker=maker)
        f, p = power_spectrum(y)
        inside = (f > 30) & (f < 400)
        assert abs(np.log2(f[inside][np.argmax(p[inside])] / cj["pair"][0])) < 0.1
        low = envelope_db(sosfiltfilt(butter(4, [40, 200], btype="bandpass", fs=SR, output="sos"), y), 0.01)
        seg = low[int(0.2 * SR): int(1.1 * SR)]
        top = np.argmax(seg)
        t60 = 2.0 * (np.argmax(seg[top:] < seg[top] - 35) - np.argmax(seg[top:] < seg[top] - 5)) / SR
        assert 0.25 < t60 < 0.6
    assert built(0, size=1.2)["pair"][0] < 0.9 * built(0)["pair"][0]  # a bigger box booms lower


def test_a_slap_cracks_and_rattles_and_a_bass_stroke_barely_lifts_the_snares():
    high = butter(4, [2000, 10000], btype="bandpass", fs=SR, output="sos")
    found = set()
    for maker in range(6):
        cj = built(maker)
        if cj["kind"] in found:
            continue
        found.add(cj["kind"])
        slap = play(cajon, "cajon", strokes("cajon-slap"), 4.5, maker=maker)
        bass = play(cajon, "cajon", strokes("cajon-bass"), 4.5, maker=maker)
        assert 1200 < centroid(slap, 0.2, 0.3) < 5000 and centroid(slap, 0.2, 0.3) > 8 * centroid(bass, 0.2, 0.4)
        hs, hb = (sosfiltfilt(high, y) for y in (slap, bass))
        assert 10 * np.log10(np.mean(hb**2) / np.mean(hs**2)) < -10  # the wires ride a bass stroke's slow push
        db = envelope_db(hs)[int(0.2 * SR): int(1.1 * SR)]
        top = np.argmax(db)
        assert 0.04 < np.argmax(db[top:] < db[top] - 40) / SR < 0.3  # a buzz of a tenth of a second or so
        assert np.abs(slap[int(0.9 * SR): int(1.2 * SR)]).max() < 1e-2 * np.abs(slap).max()  # and settles
    assert found >= {"wires", "strings"}


def test_a_ghost_tap_sits_well_under_a_slap():
    slap = play(cajon, "cajon", strokes("cajon-slap"), 4.5, maker=1)
    tap = play(cajon, "cajon", strokes("cajon-tap"), 4.5, maker=1)
    assert -14 < 10 * np.log10(np.mean(tap**2) / np.mean(slap**2)) < -5


@pytest.mark.parametrize("art,window", [("cajon-bass", 0.1), ("cajon-slap", 0.05)])
def test_harder_is_louder_and_brighter(art, window):
    notes = [strokes(art, vel=v) for v in (0.3, 0.95)]
    soft, loud = (play(cajon, "cajon", n, 4.5, maker=1) for n in notes)
    assert np.sqrt(np.mean(loud**2)) > 3.0 * np.sqrt(np.mean(soft**2))
    bright = [np.mean([centroid(y, n.start, n.start + window) for n in notes[0]]) for y in (soft, loud)]
    assert bright[1] > 1.1 * bright[0]


def test_a_groove_sits_at_the_frame_drums_level():
    """Bass on 1 and 3, slaps on 2 and 4, ghost taps on the e and the a, 100 BPM, vel 0.6."""
    levels = [loudness(cajon, "cajon", GROOVE, int(20.5 * SR), maker=maker) for maker in range(3)]
    assert all(abs(level - target(cajon, "cajon")) < 1.5 for level in levels)
