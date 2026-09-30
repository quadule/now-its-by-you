"""The heaviest parts made with less memory make the same samples (docs/PERFORMANCE.md, "The heaviest parts",
2026-09-30): each lean piece against the way it replaced, and a whole kit, every piece and implement, against the
samples the kit made before (its hash, taken from the tree before the change)."""

import hashlib
from dataclasses import dataclass

import numpy as np
import pytest

from songbird.synth import cymbals, kit, struck

SR = 44100


def same(a, b) -> bool:
    a, b = np.ascontiguousarray(a), np.ascontiguousarray(b)
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()


def _ring_as_it_was(freqs, t60s, times, amps, sr, length, *, mix=None, bend=None, damp=None, dweight=None,
                    damp2=None, dweight2=None, phase=None, multirate=True):
    """struck.ring before 2026-09-30: every track padded whole, each group's sum doubled whole and added, the
    result added to zeros."""
    freqs = np.asarray(freqs, dtype=np.float64)
    k = len(freqs)
    t60s = np.broadcast_to(np.asarray(t60s, dtype=np.float64), (k,))
    times = np.asarray(times, dtype=np.float64)
    amps = np.asarray(amps, dtype=np.float64).reshape(len(times), k)
    order = np.argsort(times, kind="stable")
    times, amps = times[order], amps[order]
    mono = mix is None
    mix = np.ones((k, 1)) if mono else np.asarray(mix, dtype=np.float64).reshape(k, -1)
    phase = np.zeros(k) if phase is None else np.broadcast_to(np.asarray(phase, dtype=np.float64), (k,))
    tracks, weights = [], []
    for track_, weight in ((damp, dweight), (damp2, dweight2)):
        if track_ is not None:
            tracks.append(np.asarray(track_, dtype=np.float64))
            weights.append(np.ones(k) if weight is None else np.broadcast_to(np.asarray(weight, dtype=np.float64), (k,)))
    out = np.zeros((length, mix.shape[1]))
    if k == 0 or len(times) == 0 or length == 0:
        return out[:, 0] if mono else out
    decay = 6.907755 / t60s
    loudest = np.max(np.abs(amps), axis=0) * np.max(np.abs(mix), axis=1)
    floor = float((struck.QUIET * loudest.max()) ** 2)
    audible = (freqs < 0.47 * sr) & (freqs > 0.0) & (loudest > 0.0)
    factors = np.array([struck._factor(f, sr) if multirate else 1 for f in freqs])

    def double(y):
        return np.stack([struck._up2(np.ascontiguousarray(y[:, c]), struck._ODD, struck._MIDDLE)
                         for c in range(y.shape[1])], axis=1)

    base = -(-length // 8) + 16
    acc, at = None, 8
    for factor in (8, 4, 2, 1):
        while acc is not None and at > factor:
            acc, at = double(acc), at // 2
        sel = np.flatnonzero(audible & (factors == factor))
        if not len(sel):
            continue
        rate = sr / factor
        n = base * (8 // factor)
        track = lambda x: np.zeros(0) if x is None else np.ascontiguousarray(  # noqa: E731
            np.pad(np.asarray(x, dtype=np.float64)[::factor], (0, n)))[:n]
        damps = np.stack([track(t) for t in tracks]) if tracks else np.zeros((0, n))
        dweights = np.stack([w[sel] for w in weights]) if weights else np.zeros((0, len(sel)))
        y = struck._bank(freqs[sel], decay[sel], np.ascontiguousarray(phase[sel]), times * rate,
                         np.ascontiguousarray(amps[:, sel]), np.ascontiguousarray(mix[sel]), track(bend),
                         np.ascontiguousarray(damps), np.ascontiguousarray(dweights), float(rate), n, floor)
        acc, at = (y if acc is None else acc + y), factor
    while acc is not None and at > 1:
        acc, at = double(acc), at // 2
    if acc is not None:
        out += acc[:length]
    return out[:, 0] if mono else out


def test_a_bank_of_modes_rings_as_it_did():
    rng = np.random.default_rng(1)
    for trial in range(150):
        k = int(rng.integers(1, 40))
        length = int(rng.integers(0, 20000))
        freqs = np.exp(rng.uniform(np.log(20.0), np.log(21000.0), k))
        if trial % 7 == 0:
            freqs[0] = 0.0
        times = rng.uniform(-0.01, length / SR + 0.01, int(rng.integers(0, 8)))
        kw = {}
        if rng.random() < 0.7:
            kw["mix"] = rng.standard_normal((k, int(rng.integers(1, 4))))
        if rng.random() < 0.5:
            kw["bend"] = rng.uniform(0.0, 0.05, max(0, length + int(rng.integers(-50, 50))))
        if rng.random() < 0.5:
            kw["damp"] = rng.uniform(0.0, 30.0, length)
            if rng.random() < 0.5:
                kw["dweight"] = rng.uniform(0.0, 2.0, k)
        if rng.random() < 0.4:
            kw["damp2"] = rng.uniform(0.0, 30.0, length)
        if rng.random() < 0.3:
            kw["multirate"] = False
        if rng.random() < 0.3:
            kw["phase"] = rng.uniform(0.0, 6.0, k)
        args = (freqs, rng.uniform(0.05, 3.0, k), times, rng.standard_normal((len(times), k)), SR, length)
        assert same(struck.ring(*args, **kw), _ring_as_it_was(*args, **kw)), trial


def test_a_track_at_every_sample_is_interp():
    rng = np.random.default_rng(2)
    for frames, length in ((10, 500), (3000, 3000 * 64 - 5), (5000, 200_000), (2, 64)):
        values = np.cumsum(rng.random(frames))
        whole = np.interp(np.arange(length) / 64, np.arange(frames), values)
        assert same(struck.per_sample(values, 64, length), whole)
        assert same(struck.per_sample(values, 64, length, block=777), whole)


def test_a_cymbals_wash_and_ticks_are_added_as_whole_tracks_were():
    rng = np.random.default_rng(3)
    plate, length = cymbals.CRASH, 60_000
    cym = cymbals.make_cymbal(plate, np.random.default_rng(4), SR)
    feed = rng.standard_normal(length) * 0.01
    damp = np.where(np.arange(length) > 40_000, 60.0, 0.0)
    wet = cymbals._fdn(feed, cym.lines, *[np.full(8, 0.9), np.full(8, 0.3)], cym.taps, cym.signs, damp, float(SR), 1024)
    # (the wash as it was, from the network's output: its burst, filters and gains on the whole stereo signal)
    from scipy.signal import bilinear, lfilter, sosfilt

    from songbird.synth.iir import butter

    was = wet + feed[:, None] * np.array([0.5, 0.5])
    was = sosfilt(butter(2, 2200.0, btype="highpass", fs=SR, output="sos"), was, axis=0)
    b, a = bilinear([1.0 / (2 * np.pi * 3500.0), 1.0], [1.0 / (2 * np.pi * 9000.0), 1.0], fs=SR)
    was = lfilter(b, a, was, axis=0) * 2.0 * cymbals.WASH * 1.1
    now = wet.copy()
    now += feed[:, None] * np.array([0.5, 0.5])
    for c in range(2):
        now[:, c] = lfilter(b, a, sosfilt(butter(2, 2200.0, btype="highpass", fs=SR, output="sos"), now[:, c]))
    now *= 2.0
    now *= cymbals.WASH
    now *= 1.1
    assert same(now, was)
    # ticks, touching and apart (a flam, a roll, the end of the song), as a whole track added, or where they lie
    hits = sorted([cymbals.Hit(float(t), float(v), z, "stick") for t, v, z in
                   zip(rng.uniform(0.0, length / SR, 40), rng.uniform(0.1, 1.0, 40), rng.choice(["bow", "edge"], 40))]
                  + [cymbals.Hit(0.5, 0.8), cymbals.Hit(0.5005, 0.7), cymbals.Hit(0.5011, 0.6),
                     cymbals.Hit(length / SR - 0.001, 1.0)], key=lambda h: h.time)
    base = rng.standard_normal((length, 2))
    whole = base + cymbals._ticks(hits, SR, length, np.random.default_rng(5), 0.5)
    into = base + 0.0
    cymbals._ticks(hits, SR, length, np.random.default_rng(5), 0.5, into=into)
    assert same(into, whole)


@dataclass
class _Note:
    start: float
    dur: float
    pitch: float
    vel: float
    art: str = ""


def _pattern(seconds: float = 12.0):
    """Every piece and implement the kit knows, over a few bars."""
    notes, beat, rng = [], 0.5, np.random.default_rng(6)
    arts = ["kick", "kick-dead", "snare", "snare-rim", "snare-cross", "snare-ghost", "hat", "hat-open", "hat-half",
            "hat-foot", "ride", "ride-bell", "ride-crash", "crash", "tom-hi", "tom-mid", "tom-lo", "brush-tap",
            "snare:rod", "tom-lo:mallet", "hat:rod", "ride:brush"]
    t = 0.0
    while t < seconds - 2.0:
        for k, art in enumerate(arts):
            if rng.random() < 0.3:
                notes.append(_Note(t + k * beat / len(arts), 0.2, 38.0, float(rng.uniform(0.2, 1.0)), art))
        t += beat
    notes += [_Note(2.0, 0.6, 38.0, 0.7, "snare-roll"), _Note(4.0, 1.0, 38.0, 0.8, "tom-lo-roll"),
              _Note(5.0, 1.5, 38.0, 0.9, "crash-roll"), _Note(6.0, 1.0, 38.0, 0.8, "ride-roll"),
              _Note(7.0, 0.4, 38.0, 0.9, "crash-choke"), _Note(8.0, 0.8, 38.0, 0.6, "brush-sweep"),
              _Note(8.8, 0.8, 38.0, 0.6, "brush-sweep"), _Note(9.5, 0.2, 36.0, 0.9, ""), _Note(9.7, 0.2, 42.0, 0.5, "")]
    return notes


CASES = {  # which of the pattern's pieces play
    "kit": None,
    "brushed": ("brush-sweep", "brush-tap", "hat", "ride:brush"),
    "no snare": ("kick", "kick-dead", "tom-hi", "tom-lo", "tom-lo-roll", "hat", "crash-choke"),  # its wires still ring
    "cymbals": ("hat", "hat-open", "hat-half", "hat-foot", "ride", "ride-bell", "crash", "crash-roll"),
}
# What the kit made of each before 2026-09-30 (the tree at 02384c8).
MADE = {
    "kit": "2df965efcaa1c0fad9a95628dbe6dabcea0e4d7c57101c0415b15f93c067d15f",
    "brushed": "143cf21baaaf2b89d128b7dd0f37d0358516a8461e45dc83416cf754a37a6e05",
    "no snare": "fdac4186afbfd0890e065fd2cd1583f6aba5a1dd1e8e493036fce4cd45c0b158",
    "cymbals": "d37ae68d8e9ed4c4d49e1d9ca07b1153967cf3665676ca83e0c138a39177d4ed",
}


def made(which: str) -> str:
    notes = [n for n in _pattern() if CASES[which] is None or n.art in CASES[which]]
    y = kit.render("kit", notes, SR, int(12.0 * SR), np.random.default_rng(7), np.random.default_rng(8),
                   {"brightness": 0.6, "wear": 0.4})
    return hashlib.sha256(np.ascontiguousarray(y).tobytes()).hexdigest()


@pytest.mark.parametrize("which", list(CASES))
def test_a_whole_kit_makes_the_samples_it_made(which):
    assert made(which) == MADE[which]


@pytest.mark.parametrize("s1,s2", [(5000, 3), (100_000, 15435), (2_000_000, 15435), (70_000, 15435), (40_000, 30_000),
                                   (4096, 4096)])
def test_a_signal_through_a_two_microphone_body_blockwise_is_oaconvolves(s1, s2):
    from scipy.signal import oaconvolve

    from songbird.synth import oa

    rng = np.random.default_rng(s1 + s2)
    x = rng.standard_normal(s1)
    h = rng.standard_normal((s2, 2)) * np.exp(-np.arange(s2) / (s2 / 4 + 1))[:, None]
    whole = oaconvolve(x[:, None], h, axes=0)
    for n in (None, s1, s1 // 3 + 17):
        assert same(oa.convolve_columns(x, h, n), whole[: len(whole) if n is None else n])


def _bowing(seconds: float = 10.0, up: float = 0.0):
    """A line for a bowed string with every way of bowing it, a double stop, a rest long enough to part two
    stretches, and plucks among the bowed notes."""
    arts = ["", "slur", "slide", "swell", "trem", "tasto", "pont", "slur", "", "pizz", "pizz", ""]
    notes, t, rng = [], 0.1, np.random.default_rng(9)
    for k, art in enumerate(arts * 2):
        dur = float(rng.uniform(0.2, 0.9))
        notes.append(_Note(t, dur, float(48 + rng.integers(0, 14)) + up, float(rng.uniform(0.3, 0.95)), art))
        if k == 5:
            notes.append(_Note(t, dur, float(60 + rng.integers(0, 5)) + up, 0.6, ""))  # a double stop
        t += dur + (3.0 if k == 11 else 0.0)
    return [n for n in notes if n.start < seconds - 1.0]


# What the bowed strings made of _bowing() before 2026-09-30 (the tree at 02384c8).
BOWED = {
    "cello": "8ae2c85148929a492e1f925ba2e751f3cebf657a1639681af7cdb025ea5675d5",
    "viola": "f1bf4b3c73e5248078ebb36fb1cc0925afd9d38b823b6392134ce5644f3362e0",
    "strings": "6514f9b8a9ef6eca3849ab7c75518fbf29aee39b6c60fd12685e10af1c1cc8fb",
}


def bowed_made(name: str) -> str:
    from songbird.synth import cello

    y = cello.render(name, _bowing(up=12.0 if name == "viola" else 0.0), SR, int(10.0 * SR),
                     np.random.default_rng(10), np.random.default_rng(11), {"brightness": 0.6, "wear": 0.3,
                                                                            "ornament": 0.7})
    return hashlib.sha256(np.ascontiguousarray(y).tobytes()).hexdigest()


@pytest.mark.parametrize("name", list(BOWED))
def test_bowed_strings_make_the_samples_they_made(name):
    assert bowed_made(name) == BOWED[name]


def test_a_tape_read_a_stretch_at_a_time_is_read_as_whole():
    from songbird.synth import fx

    rng = np.random.default_rng(12)
    for n, shape in ((200_003, (2,)), (70_000, ()), (4, (2,))):
        x = rng.standard_normal((n,) + shape)
        offset = np.cumsum(rng.standard_normal(n)) * 0.01 + 3.0 * np.sin(np.arange(n) / 500.0)
        pos = np.clip(np.arange(n) + offset, 1.0, n - 3.0)
        i = np.floor(pos).astype(np.int64)
        t = (pos - i)[:, None] if x.ndim == 2 else pos - i
        p0, p1, p2, p3 = x[i - 1], x[i], x[i + 1], x[i + 2]
        whole = p1 + 0.5 * t * (p2 - p0 + t * (2 * p0 - 5 * p1 + 4 * p2 - p3 + t * (3 * (p1 - p2) + p3 - p0)))
        assert same(fx.warp(x, offset), whole) and same(fx.warp(x, offset, block=777), whole)


# What mixing.wear made of _worn() before 2026-09-30 (the tree at 02384c8), at a little and a lot of wear.
WORN = {0.3: "e51c1f5f9b8ec0e2246423f3b230ef6222446118d965b63ba6bc7b4fb3872690",
        0.8: "c64f9890e63a66229f9176a80c11afcfebcafaf387ae38ae36387ccbc6b1a928"}


def worn(amount: float) -> str:
    from songbird.synth import mixing

    rng = np.random.default_rng(13)
    n = 44100 * 6 + 11
    x = rng.standard_normal((n, 2)) * 0.1 * np.sin(np.arange(n) / 3000.0)[:, None]
    return hashlib.sha256(np.ascontiguousarray(mixing.wear(x, SR, amount, seed=4)).tobytes()).hexdigest()


@pytest.mark.parametrize("amount", list(WORN))
def test_a_worn_mix_is_worn_as_it_was(amount):
    assert worn(amount) == WORN[amount]


# What the mallets made of _struck() before 2026-09-30 (the tree at 02384c8): a vibraphone's motor on, changing
# speed and off, and with no motor at all; a celesta through its case; a marimba.
MALLETS = {
    ("vibraphone", 0.6): "b7cc420c5aab8cb6a38b172476dedf35407838ddd68c5128b4fd4611fedcf94c",
    ("vibraphone", 0.0): "d18f121556d248efe09c8a58ecda9d28a6ee5a9fc893d8de7122d72f3ea638a3",
    ("vibraphone", -1.0): "cf01187aab7da47569e5ec99643c0dd45e1b83c017f3a84d980cf53aa29a5364",  # no motor at all: ornament 0 and no motor's art
    ("celesta", 0.5): "b5636dcc9389e721d411f30d0bf66c2839eb65778ce10ecae4913110ff72f9f1",
    ("marimba", 0.5): "fe1fdc1d1b05ffa999167c75c5a6f4cb07280cd6bbeddfe0948b154e27206dab",
}


def _struck(name: str, motor: bool = True):
    rng = np.random.default_rng(14)
    arts = ["", "", "motor-fast", "", "motor-slow", "", "motor-off", "", "motor-fast", ""] if motor else [""] * 10
    return [_Note(0.2 + 0.7 * k, float(rng.uniform(0.2, 1.5)), float(60 + rng.integers(0, 19)),
                  float(rng.uniform(0.3, 1.0)), art) for k, art in enumerate(arts)]


def mallets_made(name: str, ornament: float) -> str:
    from songbird.synth import mallets

    y = mallets.render(name, _struck(name, name == "vibraphone" and ornament >= 0.0), SR, int(9.0 * SR),
                       np.random.default_rng(15), np.random.default_rng(16), {"ornament": max(0.0, ornament), "wear": 0.5})
    return hashlib.sha256(np.ascontiguousarray(y).tobytes()).hexdigest()


@pytest.mark.parametrize("name,ornament", list(MALLETS))
def test_mallets_make_the_samples_they_made(name, ornament):
    assert mallets_made(name, ornament) == MALLETS[name, ornament]
