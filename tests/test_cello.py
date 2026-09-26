"""The cello, the viola and the string section, measured against what real ones do."""

import time

import numpy as np
import pytest
from scipy.signal import butter, hilbert, sosfiltfilt

from _levels_b import TARGETS, loudness
from songbird.score import Note
from songbird.synth import body, cello
from songbird.theory import midi_to_hz

SR = 44100
PLAIN = dict(brightness=0.5, wear=0.0, ornament=0.5, body=1.0)


def peak_hz(y, guess, t0, t1):
    seg = y[int(t0 * SR): int(t1 * SR)]
    seg = seg * np.hanning(len(seg))
    n = 16 * SR
    spec = np.abs(np.fft.rfft(seg, n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    band = (freqs > guess * 0.94) & (freqs < guess * 1.06)
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


def harmonic_db(y, f0, t0, t1, count):
    seg = y[int(t0 * SR): int(t1 * SR)] * np.hanning(int(t1 * SR) - int(t0 * SR))
    n = 1 << int(np.ceil(np.log2(4 * len(seg))))
    spec = np.abs(np.fft.rfft(seg, n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    levels = [spec[(freqs > f0 * (h - 0.3)) & (freqs < f0 * (h + 0.3))].max() for h in range(1, count + 1)]
    return 20 * np.log10(np.array(levels) / levels[0])


def envelope(y, f, lo=0.8, hi=1.25):
    band = sosfiltfilt(butter(2, [f * lo, f * hi], btype="bandpass", fs=SR, output="sos"), y)
    n = max(88, int(2 * SR / f))
    return np.sqrt(np.convolve(band**2, np.ones(n) / n, mode="same"))


def centroid(y, t0, t1):
    seg = y[int(t0 * SR): int(t1 * SR)]
    seg = seg.mean(axis=1) if seg.ndim == 2 else seg
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    return float(np.sum(f * spec) / np.sum(spec))


def upper_db(y, t0, t1, cut=2000.0):
    seg = y[int(t0 * SR): int(t1 * SR)]
    seg = seg.mean(axis=1) if seg.ndim == 2 else seg
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    return 10 * np.log10(spec[f > cut].sum() / spec.sum())


def held(kind, pitch, art="", vel=0.6, dur=1.5, seed=3, **s):
    """One player's bridge force for one note from 0.1 s, no vibrato, and the pitch it means to play (bowed.tracks'
    first draw is the player's intonation for the note)."""
    y = cello.player(kind, [Note("x", 0.1, dur, float(pitch), vel, art=art)], SR, int((dur + 0.4) * SR),
                     np.random.default_rng(seed), {**PLAIN, **s}, {"depth": 0.0})
    return y, midi_to_hz(pitch + np.random.default_rng(seed).normal(0.0, cello.INTONATION))


def stem(name, notes, dur, maker=0, seed=1, **s):
    settings = {**PLAIN, "wear": 0.25, "maker": maker, **s}
    return cello.render(name, tuple(notes), SR, int(dur * SR), np.random.default_rng([seed, 17]),
                        np.random.default_rng([maker, 29]), settings)


# --- bodies ------------------------------------------------------------------------------


@pytest.mark.parametrize("maker", [0, 1, 2])
def test_the_boxes_ring_where_cellos_and_violas_do(maker):
    def strongest(box, lo, hi):
        freqs, db = body.response(body.impulse_response(box, SR, seed=maker), SR, n=1 << 17)
        band = (freqs > lo) & (freqs < hi)
        return freqs[band][np.argmax(db[band])]

    assert 94 < strongest(body.CELLO, 85, 125) < 106  # the cello's A0, 95-105 Hz
    assert 170 < strongest(body.CELLO, 160, 240) < 228  # its B1 pair, near 180 and 215 (the wolf near F-F#)
    assert 218 < strongest(body.VIOLA, 200, 260) < 242  # the viola's A0, 220-235 Hz
    assert 390 < strongest(body.VIOLA, 370, 500) < 480  # its B1 pair, 400-460


@pytest.mark.parametrize("maker", [0, 1, 2])
def test_no_hole_after_the_b1_pair(maker):
    """A cello radiates well through 250-500 Hz, its principal formant (Meyer); the violin's dip after its B1 pair,
    scaled down, had left a 7-10 dB hole there (a hollow D string). The viola's plate modes run on from its B1 pair
    to its bridge hill."""
    def bands(box, centres):
        ir = cello.voiced(body.impulse_response(box, SR, seed=maker), SR).mean(axis=1)
        power = np.abs(np.fft.rfft(ir, 1 << 17)) ** 2
        f = np.fft.rfftfreq(1 << 17, 1 / SR)
        return [10 * np.log10(power[(f >= c * 2 ** -(1 / 6)) & (f < c * 2 ** (1 / 6))].mean()) for c in centres]

    b200, *cluster = bands(body.CELLO, (200, 250, 315, 400))
    assert all(b > b200 - 6 for b in cluster)  # within 6 dB of the B1 band (7-10 dB under it before)
    top, *trough = bands(body.VIOLA, (315, 500, 630, 800))
    top = max(top, bands(body.VIOLA, (400,))[0])
    assert all(b > top - 7 for b in trough)  # (5-12 dB under before)


# --- the bowed string, played as a cellist plays it ----------------------------------------


@pytest.mark.parametrize("kind,pitches", [(cello.CELLO, (36, 48, 57, 69, 76)), (cello.VIOLA, (48, 62, 74, 84))])
def test_in_tune_across_the_register_at_every_bow_position(kind, pitches):
    for pitch in pitches:
        for art, bright in (("", 0.0), ("", 1.0), ("tasto", 0.5), ("pont", 0.5)):
            y, f = held(kind, pitch, art, brightness=bright)
            assert abs(1200 * np.log2(peak_hz(y, f, 0.6, 1.5) / f)) < 2.5, (pitch, art, bright)


@pytest.mark.parametrize("pitch", [36, 50, 62])
def test_helmholtz_motion_a_sawtooth_at_the_bridge(pitch):
    y, f = held(cello.CELLO, pitch)
    h = harmonic_db(y, f, 0.8, 1.5, 4)
    assert np.all(np.abs(h[1:] - 20 * np.log10(1 / np.arange(2, 5))) < 2.0)


@pytest.mark.parametrize("pitch,limit", [(36, 0.09), (43, 0.05), (50, 0.05), (57, 0.05), (69, 0.05)])
def test_a_fresh_stroke_speaks_within_guettler_and_askenfelts_limits(pitch, limit):
    """Helmholtz motion within 50 ms of the bow's landing, 90 on the C string (Guettler and Askenfelt 1997), at
    both ends of the dynamics."""
    for vel in (0.35, 0.85):
        y, f = held(cello.CELLO, pitch, vel=vel)
        env = envelope(y, f)
        steady = np.median(env[int(0.8 * SR): int(1.4 * SR)])
        assert np.argmax(env[int(0.1 * SR):] > 0.9 * steady) / SR < limit, vel


def test_a_bow_change_on_the_c_string_recovers_quickly_and_a_slur_barely_dips():
    notes = [Note("x", 0.1 + 0.45 * k, 0.45, float(36 + s), 0.6, art=art)
             for k, (s, art) in enumerate([(0, ""), (2, ""), (4, "slur"), (5, "slur")])]
    y = cello.player(cello.CELLO, notes, SR, int(2.2 * SR), np.random.default_rng(4), PLAIN, {"depth": 0.0})
    f = midi_to_hz(38)
    env = envelope(y, f)
    steady = np.median(env[int(0.75 * SR): int(1.0 * SR)])
    assert np.argmax(env[int(0.55 * SR):] > 0.9 * steady) / SR < 0.09  # the fundamental back within 90 ms
    rms = np.sqrt(np.convolve(y**2, np.ones(441) / 441, mode="same"))
    around = rms[int(0.95 * SR): int(1.1 * SR)]
    assert 20 * np.log10(around.min() / np.median(rms[int(0.75 * SR): int(0.95 * SR)])) > -6  # a slur's dip


def test_tasto_is_dark_ponticello_glassy_and_brightness_moves_between():
    notes = lambda art: [Note("cello", 0.1, 1.6, 50.0, 0.6, art=art)]  # noqa: E731
    tasto, arco, pont = (upper_db(stem("cello", notes(a), 2.0), 0.6, 1.6) for a in ("tasto", "", "pont"))
    assert tasto < arco - 6 and pont > arco + 6
    dark, bright = (upper_db(stem("cello", notes(""), 2.0, brightness=b), 0.6, 1.6) for b in (0.0, 1.0))
    assert bright > dark + 5


@pytest.mark.parametrize("name,pitch", [("cello", 50), ("viola", 62)])
def test_louder_is_brighter(name, pitch):
    levels, centroids = [], []
    for vel in (0.3, 0.6, 0.9):
        y = stem(name, [Note(name, 0.1, 1.6, float(pitch), vel)], 2.0)
        levels.append(10 * np.log10(np.mean(y[int(0.6 * SR): int(1.6 * SR)] ** 2)))
        centroids.append(centroid(y, 0.6, 1.6))
    assert levels[0] < levels[1] - 3 < levels[2] - 5
    assert np.log2(centroids[2] / centroids[0]) > 0.3  # a third of an octave and more


@pytest.mark.parametrize("name,pitch,rate", [("cello", 50, (5.0, 6.0)), ("viola", 62, (5.4, 6.5))])
def test_a_players_vibrato_rate_and_width(name, pitch, rate):
    depths = []
    for ornament in (0.0, 1.0):
        y = stem(name, [Note(name, 0.1, 2.6, float(pitch), 0.6)], 2.9, ornament=ornament, wear=0.0).mean(axis=1)
        f0 = midi_to_hz(pitch)
        band = sosfiltfilt(butter(2, [f0 * 0.85, f0 * 1.15], btype="bandpass", fs=SR, output="sos"), y)
        inst = np.diff(np.unwrap(np.angle(hilbert(band)))) * SR / (2 * np.pi)
        c = 1200 * np.log2(np.convolve(inst[int(0.9 * SR): int(2.6 * SR)], np.ones(441) / 441, mode="valid") / f0)
        depths.append((np.percentile(c, 97) - np.percentile(c, 3)) / 2)
        if ornament:
            spec = np.abs(np.fft.rfft((c - c.mean()) * np.hanning(len(c)), 1 << 18))
            fr = np.fft.rfftfreq(1 << 18, 1 / SR)
            sel = (fr > 2) & (fr < 12)
            assert rate[0] < fr[sel][np.argmax(spec[sel])] < rate[1]
    assert depths[0] < 5 and depths[1] > 15  # plain: nearly none; ornamented: a wide singer's vibrato


def cents(y, f0, t0, t1):
    """The pitch of a bridge force's fundamental from t0 to t1 s, in cents from f0 (a 10 ms average)."""
    band = sosfiltfilt(butter(4, [f0 * 0.92, f0 * 1.08], btype="bandpass", fs=SR, output="sos"), y)
    inst = np.diff(np.unwrap(np.angle(hilbert(band)))) * SR / (2 * np.pi)
    return 1200 * np.log2(np.maximum(np.convolve(inst, np.ones(441) / 441, mode="same"), 1.0) / f0)[
        int(t0 * SR): int(t1 * SR)]


def swing(c, cycle=0.18):
    """Half the vibrato's peak to peak over the cycle before each 10 ms step."""
    n = int(cycle * SR)
    return np.array([np.ptp(c[max(0, i - n): i]) / 2 for i in range(n // 4, len(c), int(0.01 * SR))])


def bowed_line(kind, notes, dur, q=None, **s):
    return cello.player(kind, notes, SR, int(dur * SR), np.random.default_rng(5), {**PLAIN, **s}, q)


def test_the_vibrato_grows_in_at_once_and_carries_through_a_phrase():
    """A cellist's vibrato is one motion of the hand: on a note after a rest it is half there in 0.08-0.2 s and
    whole by 0.4 s (it was nothing for a quarter of a second, then half at 0.35); through a slur it keeps going (it
    started again from nothing on every note); a 0.3 s note in a line still has some (it had none under 0.35 s)."""
    f = midi_to_hz(50)
    y = bowed_line(cello.CELLO, [Note("x", 0.1, 2.0, 50.0, 0.6)], 2.4)
    w = swing(cents(y, f, 0.13, 2.0))
    full = np.median(w[80:])
    t = np.arange(len(w)) * 0.01 + 0.18 / 4 + 0.03
    assert 0.08 < t[np.argmax(w > 0.5 * full)] < 0.2 and t[np.argmax(w > 0.9 * full)] < 0.4 and full > 15
    slur = [Note("x", 0.1, 0.8, 50.0, 0.6), Note("x", 0.9, 0.8, 52.0, 0.6, art="slur")]
    y = bowed_line(cello.CELLO, slur, 2.0)
    before = np.ptp(cents(y, f, 0.65, 0.88)) / 2
    after = np.ptp(cents(y, midi_to_hz(52), 1.0, 1.25)) / 2
    assert after > 0.6 * before
    for dur, least in ((0.3, 5.0), (0.45, 10.0)):
        line = [Note("x", 0.1 + dur * k, dur, float(p), 0.6, art="slur" if k % 2 else "")
                for k, p in enumerate([50, 52, 54, 55, 57, 55])]
        y = bowed_line(cello.CELLO, line, 0.5 + 6 * dur)
        for k, p in enumerate([50, 52, 54, 55, 57, 55][1:], start=1):
            c = cents(y, midi_to_hz(p), 0.1 + dur * k + 0.04, 0.1 + dur * (k + 1) - 0.02)
            assert np.ptp(c) / 2 > least, (dur, k)


def test_a_section_player_starts_the_vibrato_in_their_own_time():
    f = midi_to_hz(62)
    halves = []
    for wait, onset in ((0.0, 0.15), (0.2, 0.35)):
        y = bowed_line(cello.VIOLA, [Note("x", 0.1, 1.6, 62.0, 0.6)], 2.0, {"wait": wait, "onset": onset, "depth": 0.7})
        w = swing(cents(y, f, 0.13, 1.6))
        halves.append(np.argmax(w > 0.5 * np.median(w[80:])) * 0.01)
    assert halves[1] - halves[0] > 0.15


def test_pizzicato_rings_down_and_tremolo_reverses_a_dozen_times_a_second():
    y = stem("cello", [Note("cello", 0.1, 0.3, 43.0, 0.7, art="pizz")], 2.0).mean(axis=1)
    env = envelope(y, midi_to_hz(43))
    early, late = env[int(0.25 * SR)], env[int(0.9 * SR)]
    assert 6 < 20 * np.log10(early / late) < 40  # a plucked G2 falls, and keeps ringing past the written note
    t = stem("cello", [Note("cello", 0.1, 1.5, 50.0, 0.6, art="trem")], 1.8).mean(axis=1)
    rms = np.sqrt(np.convolve(t**2, np.ones(220) / 220, mode="same"))[int(0.3 * SR): int(1.5 * SR)]
    spec = np.abs(np.fft.rfft((rms - rms.mean()) * np.hanning(len(rms)), 1 << 18))
    fr = np.fft.rfftfreq(1 << 18, 1 / SR)
    sel = (fr > 5) & (fr < 40)
    assert 9 < fr[sel][np.argmax(spec[sel])] < 18  # a dip at every reversal: 11 to 15 strokes a second


# --- the section ----------------------------------------------------------------------------


def test_the_section_sits_violins_left_cellos_right_and_every_line_is_a_chorus():
    high = stem("strings", [Note("strings", 0.1, 1.8, 76.0, 0.6)], 2.2)
    low = stem("strings", [Note("strings", 0.1, 1.8, 43.0, 0.6)], 2.2)
    side = lambda y: 10 * np.log10(np.sum(y[:, 0] ** 2) / np.sum(y[:, 1] ** 2))  # noqa: E731
    assert side(high) > 3 and side(low) < -3  # left louder for violins, right for cellos
    # three players a few cents apart beat: the note's level wanders more than one player's does
    solo = stem("viola", [Note("viola", 0.1, 1.8, 64.0, 0.6)], 2.2, ornament=0.0).mean(axis=1)
    section = stem("strings", [Note("strings", 0.1, 1.8, 64.0, 0.6)], 2.2, ornament=0.0).mean(axis=1)

    def wander(y):
        e = envelope(y, midi_to_hz(64))[int(0.6 * SR): int(1.8 * SR)]
        return e.std() / e.mean()

    assert wander(section) > 1.5 * wander(solo)


def test_a_section_entry_spreads_but_nobody_comes_in_early():
    y = stem("strings", [Note("strings", 0.5, 1.0, p, 0.6) for p in (50.0, 57.0, 62.0, 66.0)], 1.8, wear=0.5)
    peak = np.abs(y).max()
    assert np.abs(y[: int(0.495 * SR)]).max() < 1e-4 * peak


# --- levels, streams, edges ------------------------------------------------------------------


BASS = [Note("cello", 0.5 + 2.0 * k, 1.95, float(p), 0.6) for k, p in enumerate([38, 45, 43, 38, 47, 43])]
TUNE = [Note("cello", 0.5 + 0.5 * k, 0.5 if k % 4 != 3 else 0.9, float(p), 0.65, art="slur" if k % 2 else "")
        for k, p in enumerate([50, 52, 54, 55, 57, 55, 54, 52, 50, 54, 57, 62, 61, 59, 57])]
PAD = [Note("strings", 0.5 + 2.0 * k, 1.95, float(p), 0.6)
       for k, chord in enumerate([(50, 57, 62, 66), (43, 55, 59, 62), (45, 57, 61, 64)]) for p in chord]


@pytest.mark.parametrize("name,kind,notes", [
    ("cello", "comping", BASS), ("cello", "lead", TUNE),
    ("viola", "comping", [Note("viola", n.start, n.dur, n.pitch + 12, n.vel) for n in BASS]),
    ("viola", "lead", [Note("viola", n.start, n.dur, n.pitch + 12, n.vel, art=n.art) for n in TUNE]),
    ("strings", "comping", PAD),
])
def test_levels_sit_with_todays_stems(name, kind, notes):
    length = int((max(n.start + n.dur for n in notes) + 1.0) * SR)
    for maker in (0, 1, 2):
        assert abs(loudness(cello, name, notes, length, maker=maker) - TARGETS[kind]) < 1.5, maker


def test_deterministic_makers_differ_and_the_edges_hold():
    notes = [Note("cello", 0.2, 0.5, 50.0, 0.6), Note("cello", 0.7, 0.5, 52.0, 0.6, art="slur"),
             Note("cello", 1.3, 0.4, 55.0, 0.7, art="pizz")]
    a, b = stem("cello", notes, 2.0), stem("cello", notes, 2.0)
    assert np.array_equal(a, b) and a.shape == (2 * SR, 2) and np.all(np.isfinite(a))
    assert not np.allclose(a, stem("cello", notes, 2.0, maker=5))
    for name in ("cello", "viola", "strings"):
        lo, hi = cello.SPEC[name]["register"]
        assert not stem(name, [], 1.0).any() and stem(name, [], 1.0).shape == (SR, 2)
        edge = [Note(name, 0.1, 0.001, float(lo), 0.0), Note(name, 0.3, 0.6, float(lo), 1.0, art="no-such-art"),
                Note(name, 1.0, 0.6, float(hi), 1.0), Note(name, 1.7, 0.3, float(hi), 0.5, art="trem"),
                Note(name, 5.0, 1.0, 60.0, 0.6)]  # the last starts past the end
        y = stem(name, edge, 2.2)
        assert y.shape == (int(2.2 * SR), 2) and np.all(np.isfinite(y)) and np.abs(y).max() > 0
        assert np.abs(y[: int(0.095 * SR)]).max() < 1e-4 * np.abs(y).max()  # nothing before the first note
        for ch in range(2):
            assert abs(y[:, ch].mean()) < 1e-3 * np.sqrt(np.mean(y[:, ch] ** 2))


def test_a_typical_part_costs_little():
    part = [Note("strings", 2.0 * k, 1.95, float(p), 0.6) for k in range(20)
            for p in ((50, 57, 62, 66), (43, 55, 59, 62))[k % 2]]
    stem("strings", part[:4], 2.0)  # compile
    t = time.process_time()
    stem("strings", part, 41.0)
    assert time.process_time() - t < 4.0
