"""Cymbals: a plate's modes as bronze has them, a wash that blooms when struck hard, damping that closes them."""

import numpy as np
from scipy.signal import butter, sosfiltfilt

from songbird.synth import cymbals
from songbird.synth.cymbals import Hit

SR = 44100


def strike(plate, vel=0.8, zone="bow", dur=2.0, damp=None, maker=0, seed=1):
    c = cymbals.make_cymbal(plate, np.random.default_rng(maker), SR)
    return cymbals.play(plate, [Hit(0.05, vel, zone)], SR, int(dur * SR), np.random.default_rng(seed), c,
                        damp=damp).mean(axis=1)


def hf_env(y, hop=0.002):
    z = sosfiltfilt(butter(4, [4000, 10000], btype="bandpass", fs=SR, output="sos"), y)
    n = int(hop * SR)
    k = len(z) // n
    return 20 * np.log10(np.sqrt(np.mean(z[: k * n].reshape(k, n) ** 2, axis=1)) + 1e-12)


def test_modes_crowd_as_a_plates_do_and_pair_below_a_kilohertz():
    for plate, lo, hi in ((cymbals.RIDE, 15, 30), (cymbals.CRASH, 14, 26), (cymbals.HAT, 20, 34)):
        c = cymbals.make_cymbal(plate, np.random.default_rng(0), SR)
        single = np.sort(c.freqs[c.pair < 0])
        assert lo < np.diff(single).mean() < hi
    c = cymbals.make_cymbal(cymbals.RIDE, np.random.default_rng(0), SR)
    low = np.flatnonzero((c.pair >= 0) & (np.arange(len(c.freqs)) < c.pair))
    split = c.freqs[c.pair[low]] / c.freqs[low] - 1.0
    assert np.all((split > 0.002) & (split < 0.035)) and np.all(c.freqs[low] < 1000)


def test_a_hard_crash_blooms_and_a_soft_one_does_not():
    hard = hf_env(strike(cymbals.CRASH, 1.0, "edge"))[25:]
    soft = hf_env(strike(cymbals.CRASH, 0.3, "edge"))[25:]
    smooth = np.convolve(hard[:100], np.ones(5) / 5, mode="valid")  # 10 ms
    assert 0.008 < (np.argmax(smooth) + 2) * 0.002 < 0.1  # its top swells for tens of milliseconds after the strike
    # and the swell is the nonlinearity's: the top grows much faster than the strike
    assert hard.max() - soft.max() > 20 * np.log10(1.0 / 0.3) + 6


def test_the_wash_and_the_modes_decay_and_stay_finite():
    y = strike(cymbals.RIDE, 0.8, dur=4.0)
    assert np.all(np.isfinite(y)) and abs(y.mean()) < 0.01 * np.sqrt(np.mean(y ** 2))
    early = np.sqrt(np.mean(y[int(0.1 * SR): int(0.5 * SR)] ** 2))
    late = np.sqrt(np.mean(y[int(3.5 * SR): int(4.0 * SR)] ** 2))
    assert late < early / 3


def test_damping_closes_the_plate():
    damp = np.zeros(int(2.0 * SR))
    damp[int(0.5 * SR):] = 75.0
    held = strike(cymbals.HAT, damp=damp)
    free = strike(cymbals.HAT)
    later = slice(int(0.8 * SR), int(1.0 * SR))
    assert np.sqrt(np.mean(held[later] ** 2)) < 0.01 * np.sqrt(np.mean(free[later] ** 2))


def test_each_strike_differs_and_each_maker_hammers_its_own():
    a = strike(cymbals.RIDE, seed=1)
    b = strike(cymbals.RIDE, seed=2)
    assert not np.allclose(a, b) and np.array_equal(a, strike(cymbals.RIDE, seed=1))
    assert not np.allclose(a, strike(cymbals.RIDE, maker=3))
