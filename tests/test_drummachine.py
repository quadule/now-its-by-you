"""The drum machines, measured against what Roland's circuits do.

The numbers come from Roland's TR-808 service notes (its voice chart), Werner, Abel and Smith's circuit models
of the 808's bass drum (DAFx 2014) and cymbal (ICMC 2014), Robin Whittle's notes on the 909's circuits, and a
reviewer's reference figures; each test says which it holds a voice to.
"""

import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import butter, lfilter, sosfiltfilt

from songbird.score import Note
from songbird.synth import drummachine as dm
from songbird.synth import master

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import instrument_levels as levels  # noqa: E402

SR = 44100
KITS = ("drums-808", "drums-909")
BASE = dict(brightness=0.5, wear=0.0, ornament=0.5, body=1.0, tonic=62)


def render(name, notes, secs, seed=0, maker=0, **settings):
    rng = np.random.default_rng([seed, 17, 99])
    make = np.random.default_rng([maker, 29, 99])
    return dm.render(name, tuple(notes), SR, int(secs * SR), rng, make, {**BASE, **settings})


def hit(name, piece, vel=0.6, secs=1.5, at=0.05, **kw):
    """One stroke, mono, from its onset."""
    y = render(name, [Note("x", at, 0.1, 60.0, vel, art=piece)], secs, **kw)
    return y.mean(axis=1)[int(round(at * SR)):]


def rms_db(y, t0, t1):
    seg = y[int(t0 * SR): int(t1 * SR)]
    return 20 * np.log10(np.sqrt(np.mean(seg**2)) + 1e-30)


def envelope_db(y, win=0.005):
    n = int(win * SR)
    e = np.sqrt(np.convolve(y * y, np.ones(n) / n, mode="same")) + 1e-15
    return 20 * np.log10(e / e.max())


def fall(y, db):
    """Seconds until the envelope last stands within `db` of its peak."""
    return np.flatnonzero(envelope_db(y) > -db)[-1] / SR


def track(y, lo, hi):
    """Instantaneous frequency from the upward zero crossings of y band-passed to lo..hi Hz: (times, Hz)."""
    x = sosfiltfilt(butter(2, [lo, hi], btype="bandpass", fs=SR, output="sos"), y)
    k = np.flatnonzero((x[:-1] < 0.0) & (x[1:] >= 0.0))
    t = (k + x[k] / (x[k] - x[k + 1])) / SR
    return 0.5 * (t[1:] + t[:-1]), 1.0 / np.diff(t)


def spectrum(seg, n=1 << 17):
    """Magnitude spectrum under a window that falls from the onset (a decaying sound's start kept)."""
    w = np.hanning(2 * len(seg))[len(seg):]
    return np.fft.rfftfreq(n, 1 / SR), np.abs(np.fft.rfft(seg * w, n))


def strongest(seg, lo, hi):
    f, s = spectrum(seg)
    band = (f > lo) & (f < hi)
    i = np.flatnonzero(band)[np.argmax(s[band])]
    return f[i], s[i]


def share(seg, lo, hi):
    p = np.abs(np.fft.rfft(seg)) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    return p[(f >= lo) & (f < hi)].sum() / p.sum()


def centroid(seg):
    p = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    return (p * f).sum() / p.sum()


# --- the bass drums ----------------------------------------------------------------------------------------


def test_808_kick_rings_near_50_hz_and_sighs_flat_as_it_booms_on():
    """A bridged-T ring (Roland: 56 Hz, Werner: 49.5), its pitch a few percent high while its swing is big (Werner:
    58 to 48 Hz over 300 ms), more so accented; the decay knob gives 0.3 to 1.2 s (reviewer)."""
    for maker in (0, 1, 2):
        y = hit("drums-808", "kick", 0.6, 2.0, maker=maker)
        t, f = track(y, 25.0, 200.0)
        early, late = np.interp(0.03, t, f), np.median(f[(t > 0.35) & (t < 0.6)])
        assert 48.0 < late < 56.0
        assert 0.02 < early / late - 1.0 < 0.15
        assert 0.3 < fall(y, 60) < 1.2
    t, f = track(hit("drums-808", "kick", 0.95, 2.0), 25.0, 200.0)
    accented = np.interp(0.03, t, f) / np.median(f[(t > 0.35) & (t < 0.6)]) - 1.0
    assert accented > early / late - 1.0 + 0.03  # a bigger trigger swings further: a deeper sigh


def test_808_kick_attack_is_a_short_punch_not_a_sweep():
    """For its first 4 to 6 ms the ring runs 2.6 times higher (130 Hz: Werner; Roland's service notes): the first
    lobe is a quarter of a 50 Hz one, then the boom goes on at its own pitch. Nearly a pure sine after it."""
    y = hit("drums-808", "kick", 0.6, 1.0)
    body = sosfiltfilt(butter(4, 1000.0, fs=SR, output="sos"), y)
    first = np.flatnonzero(np.diff(np.signbit(body[int(0.0005 * SR):]).astype(int)))[0] / SR
    assert 0.0025 < first < 0.006  # half a cycle at ~130 Hz, where a 50 Hz ring would take 10 ms
    seg = y[int(0.3 * SR): int(0.8 * SR)]
    s = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 17))
    f = np.fft.rfftfreq(1 << 17, 1 / SR)
    f0 = f[np.argmax(s * (f < 120))]
    second = s[(f > 1.8 * f0) & (f < 2.2 * f0)].max()
    assert 20 * np.log10(second / s.max()) < -40.0


def test_909_kick_sweeps_two_octaves_down_in_30_to_60_ms():
    """A rounded triangle whose pitch envelope falls about two octaves, reaching within 10% of its final
    50-60 Hz in 30 to 60 ms (reviewer; the Tune knob sets how fast); shorter than the 808's; an accent sweeps
    from higher and drives the diodes harder."""
    def first_half_cycle(y):  # the wave starts at zero going up: its first crossing back is half a cycle in
        lp = sosfiltfilt(butter(4, 1000.0, fs=SR, output="sos"), y)
        skip = int(0.0003 * SR)  # past the click
        return 1.0 / (2.0 * (skip + np.flatnonzero(np.diff(np.signbit(lp[skip:]).astype(int)))[0]) / SR)

    for maker in (0, 1, 2):
        y = hit("drums-909", "kick", 0.6, 1.5, maker=maker)
        t, f = track(y, 25.0, 600.0)
        final = np.median(f[(t > 0.15) & (t < 0.3)])
        assert 50.0 < final < 60.0
        assert first_half_cycle(y) > 3.0 * final  # its first half cycle nearly two octaves up
        settled = t[np.flatnonzero(f < 1.1 * final)[0]]
        assert 0.025 < settled < 0.065
        assert 0.2 < fall(y, 60) < 0.65
    soft, hard = hit("drums-909", "kick", 0.7, 1.0), hit("drums-909", "kick", 0.95, 1.0)
    assert first_half_cycle(hard) > 1.1 * first_half_cycle(soft)


# --- snares and clap --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name,low,high", [("drums-808", 173.0, 336.0), ("drums-909", 190.0, 345.0)])
def test_snare_rings_at_its_two_bodies(name, low, high):
    """808: two rings at 173 and 336 Hz on later machines (the service notes' capacitor change), the upper
    dying about three times faster; 909: two oscillators near 190 and 345 Hz (reviewer)."""
    y = hit(name, "snare", 0.6, 1.0)
    f1, a1 = strongest(y[: int(0.5 * SR)], 120.0, 260.0)
    f2, a2 = strongest(y[: int(0.5 * SR)], 270.0, 450.0)
    assert abs(f1 / low - 1.0) < 0.1 and abs(f2 / high - 1.0) < 0.1
    assert -20.0 < 20 * np.log10(a2 / a1) < 0.0


def test_the_909_snare_is_noisier_and_the_808s_snap_is_high_passed_noise():
    """The 808's snappy is white noise high-passed at 2.75 kHz (its circuit), more tone than rattle; the 909's
    crack is noise louder than its tone (reviewer: brighter and noisier)."""
    def noise_over_tone(name):
        f, s = spectrum(hit(name, "snare", 0.6, 1.0)[: int(0.05 * SR)])
        p = s**2
        return 10 * np.log10(p[f >= 1000].sum() / p[f < 800].sum()), (p * f)[f >= 1000].sum() / p[f >= 1000].sum()

    n808, c808 = noise_over_tone("drums-808")
    n909, _ = noise_over_tone("drums-909")
    assert -9.0 < n808 < -1.0 and 1.0 < n909 < 7.0
    assert 3500.0 < c808 < 8000.0  # the snap's noise sits between 1 and 8 kHz (reviewer)
    y = hit("drums-808", "snare", 0.6, 1.0)
    assert 0.035 < fall(y, 20) < 0.09  # Roland's chart: 60 ms


@pytest.mark.parametrize("name,period", [("drums-808", 0.011), ("drums-909", 0.010)])
def test_clap_is_three_bursts_about_ten_ms_apart_over_a_tail(name, period):
    """Noise band-passed near 1 kHz (808: 1.07 kHz, Q 1.6), struck three times in a 30 ms window (the service
    notes: bursts 10-12 ms apart), over a reverb tail of 150 to 300 ms (reviewer)."""
    y = hit(name, "clap", 0.6, 1.0)
    env = np.convolve(np.abs(y), np.ones(44) / 44, mode="same")[: int(0.035 * SR)]
    env = env - env.mean()
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    lag = (int(0.006 * SR) + np.argmax(ac[int(0.006 * SR): int(0.016 * SR)])) / SR
    assert abs(lag - period) < 0.0015 and 0.009 < lag < 0.013
    assert 0.12 < fall(y, 40) < 0.35
    assert 850.0 < strongest(y[: int(0.3 * SR)], 300.0, 5000.0)[0] < 1450.0


# --- hats and cymbals ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", KITS)
def test_hats_live_between_3_and_16_khz_and_close_as_the_chart_says(name):
    """Their energy between 3 and 12 kHz (reviewer; the 808's closed hat reaches higher, high-passed at 11.7 kHz),
    nothing folded down below 1 kHz, the closed about 50-80 ms, the open 300-500 ms (reviewer; Roland's chart:
    50 ms and 90 to 600 ms to fall 20 dB), the pedal shortest."""
    lengths = {}
    for piece in ("hat", "hat-open", "hat-pedal"):
        y = hit(name, piece, 0.6, 2.0)
        seg = y[: int(0.25 * SR)]
        assert share(seg, 3000.0, 16000.0) > 0.9 and share(seg, 3000.0, 12000.0) > 0.7
        assert 10 * np.log10(share(seg, 0.0, 1000.0)) < -30.0
        lengths[piece] = fall(y, 40)
    assert 0.04 < lengths["hat"] < 0.11
    assert 0.2 < lengths["hat-open"] < 0.7
    assert lengths["hat-pedal"] < 0.8 * lengths["hat"]


def test_808_hats_are_the_six_squares_not_noise():
    """The 808's metal is six square waves (205.3, 369.6, 304.4, 522.7 Hz, untrimmed, and 540 and 800, trimmed:
    the service notes, Werner, Abel and Smith): its spectrum is lines, peaked as noise never is (a clone's
    tell), and it gets grittier (brighter) as its swing VCA's envelope falls (ICMC 2014)."""
    for maker in (0, 1):
        bank = dm.TR808(SR, np.random.default_rng([maker, 29, 99]), BASE).osc_f
        design = np.array(dm.OSC_808)
        assert np.all(np.abs(bank[:4] / design[:4] - 1.0) <= 0.04) and np.all(np.abs(bank[4:] / design[4:] - 1.0) <= 0.01)

    def peaked(y):  # the loudest lines against the spectrum's median, 5 to 10 kHz
        seg = y[: int(0.3 * SR)]
        s = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16))
        f = np.fft.rfftfreq(1 << 16, 1 / SR)
        b = s[(f > 5000.0) & (f < 10000.0)]
        return 20 * np.log10(np.percentile(b, 99) / np.median(b))

    assert peaked(hit("drums-808", "hat-open", 0.6, 1.0)) > 20.0
    assert peaked(hit("drums-808", "maracas", 0.6, 1.0)) < 17.0  # noise, for comparison
    y = hit("drums-808", "hat", 0.6, 1.0)
    assert centroid(y[int(0.04 * SR): int(0.06 * SR)]) > centroid(y[: int(0.02 * SR)]) * 1.1
    assert centroid(y[: int(0.02 * SR)]) > 6000.0


@pytest.mark.parametrize("name", KITS)
def test_a_closed_hat_chokes_an_open_one(name):
    """The closed (or pedal) hat's trigger discharges the open hat's envelope (the 808's service notes)."""
    for closer in ("hat", "hat-pedal"):
        both = render(name, [Note("x", 0.05, 0.1, 60.0, 0.6, art="hat-open"), Note("x", 0.25, 0.1, 60.0, 0.6, art=closer)],
                      1.2).mean(axis=1)
        alone = render(name, [Note("x", 0.25, 0.1, 60.0, 0.6, art=closer)], 1.2).mean(axis=1)
        free = render(name, [Note("x", 0.05, 0.1, 60.0, 0.6, art="hat-open")], 1.2).mean(axis=1)
        choked = both - alone  # every stroke is its own voice, summed
        ref = rms_db(free, 0.2, 0.25)
        assert rms_db(choked, 0.32, 0.5) - ref < -45.0  # gone within tens of milliseconds
        assert rms_db(free, 0.32, 0.5) - ref > -25.0  # where it would still have been ringing
        assert np.max(np.abs(choked[int(0.35 * SR):])) < 1e-3 * np.max(np.abs(free))


@pytest.mark.parametrize("name", KITS)
def test_crash_and_ride_ring_long_and_the_crash_longest(name):
    y_crash, y_ride = hit(name, "crash", 0.6, 3.5), hit(name, "ride", 0.6, 3.5)
    assert fall(y_crash, 40) > 0.8 and fall(y_ride, 40) > 0.4
    assert fall(y_crash, 40) > fall(y_ride, 40) or name == "drums-909"
    for y in (y_crash, y_ride):
        seg = y[: int(0.5 * SR)]
        assert 2500.0 < centroid(seg) < 9000.0


# --- cowbell, toms, rim, the 808's extras ------------------------------------------------------------------


@pytest.mark.parametrize("name", KITS)
def test_cowbell_is_two_squares_at_540_and_800_hz(name):
    """The 808's two trimmed squares (540 and 800 Hz, the service notes) through a band-pass near 2.6 kHz
    (reviewer), falling fast then slowly (the chart: 50 ms): its lines are theirs and their overtones."""
    y = hit(name, "cowbell", 0.6, 1.0)
    seg = y[: int(0.3 * SR)]
    lo, a_lo = strongest(seg, 500.0, 580.0)
    hi, a_hi = strongest(seg, 760.0, 840.0)
    assert abs(lo / 540.0 - 1.0) < 0.02 and abs(hi / 800.0 - 1.0) < 0.02
    f, s = spectrum(y[int(0.02 * SR): int(0.25 * SR)])  # past the fast drop, which smears every line
    p = s**2
    band = (f > 300.0) & (f < 10000.0)
    near = np.zeros_like(f, dtype=bool)
    for base in (lo, hi):
        k = np.round(f / base)
        near |= (k >= 1) & (np.abs(f - k * base) < np.maximum(15.0, 0.015 * f))
    assert p[band & near].sum() > 0.8 * p[band].sum()
    top = s[band].max()
    assert 20 * np.log10(a_lo / top) > -15.0 and 20 * np.log10(a_hi / top) > -15.0
    assert 0.03 < fall(y, 20) < 0.09


@pytest.mark.parametrize("name,nominal", [("drums-808", (185.0, 135.0, 90.0)), ("drums-909", (190.0, 135.0, 95.0))])
def test_toms_are_tuned_high_to_low_and_bend_down(name, nominal):
    """Rings (808) or oscillators (909) near 160-200, 120-140 and 80-100 Hz (reviewer; Roland's chart 185, 135,
    90), each starting sharp and falling to its pitch: the 808's diodes bend more the harder the hit (up to 1.7
    times), the 909's envelope the same every time and further on an accent."""
    for piece, f0 in zip(("tom-hi", "tom-mid", "tom-lo"), nominal):
        t, f = track(hit(name, piece, 0.4, 1.5), f0 / 1.8, f0 * 2.2)
        settled = np.median(f[(t > 0.12) & (t < 0.2)])
        assert abs(settled / f0 - 1.0) < 0.07
        soft = np.interp(0.008, t, f) / settled - 1.0
        t, f = track(hit(name, piece, 0.95, 1.5), f0 / 1.8, f0 * 2.2)
        hard = np.interp(0.008, t, f) / settled - 1.0
        assert hard > 0.2 and hard > soft + 0.03


def test_808_rim_and_clave_are_short_high_ticks():
    """The rim shot: rings at 455 Hz and 1.7 kHz through a distorting transistor, 10 ms to fall 20 dB (Roland's
    chart); the claves a 2.5 kHz ring gated after 22 ms (chart: 25 ms)."""
    y = hit("drums-808", "rim", 0.6, 0.5)
    assert fall(y, 20) < 0.015
    assert abs(strongest(y[: int(0.03 * SR)], 300.0, 700.0)[0] / 455.0 - 1.0) < 0.08
    assert share(y[: int(0.03 * SR)], 300.0, 6000.0) > 0.8
    y = hit("drums-808", "clave", 0.6, 0.5)
    assert abs(strongest(y[: int(0.03 * SR)], 1500.0, 4000.0)[0] / 2500.0 - 1.0) < 0.05
    assert 0.018 < fall(y, 40) < 0.03


def test_808_congas_are_the_toms_purer_and_higher():
    for piece, f0 in (("conga-hi", 400.0), ("conga-mid", 280.0), ("conga-lo", 185.0)):
        y = hit("drums-808", piece, 0.6, 1.5)
        t, f = track(y, f0 / 1.8, f0 * 2.2)
        assert abs(np.median(f[(t > 0.2) & (t < 0.3)]) / f0 - 1.0) < 0.07


def test_909_borrows_the_808s_cowbell_and_extras():
    a = hit("drums-909", "clave", 0.6, 0.5)
    assert abs(strongest(a[: int(0.03 * SR)], 1500.0, 4000.0)[0] / 2500.0 - 1.0) < 0.05


# --- playing -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", KITS)
def test_every_piece_is_louder_played_harder_and_the_accent_adds_more(name):
    """Velocity is the trigger's size, 18 dB from 0.2 to 1 (touch.gain); from 0.8 to 0.9 the accent adds 5 dB
    (reviewer: 4 to 6)."""
    for piece in dm.SPEC[name]["articulations"]:
        lv = {v: rms_db(hit(name, piece, v, 0.8), 0.0, 0.3) for v in (0.3, 0.7, 0.75, 0.95)}
        assert lv[0.7] - lv[0.3] > 6.0, piece
        assert lv[0.95] - lv[0.75] > 2.5 + 3.5, piece


def test_an_accent_drives_the_kicks_harder_not_just_louder():
    """More click on the 808 (its pulse leaks through, and a bigger swing sighs further: tested above); a deeper
    sweep and harder-driven diodes on the 909: a squarer wave."""
    def click(y):
        return share(y[: int(0.01 * SR)], 1000.0, 20000.0)

    assert click(hit("drums-808", "kick", 0.95)) > 1.3 * click(hit("drums-808", "kick", 0.7))

    def third(y):
        f, s = spectrum(y[int(0.2 * SR): int(0.5 * SR)])
        f0 = f[np.argmax(s * (f < 120))]
        return s[(f > 2.8 * f0) & (f < 3.2 * f0)].max() / s.max()

    assert third(hit("drums-909", "kick", 0.95)) > 1.5 * third(hit("drums-909", "kick", 0.7))


@pytest.mark.parametrize("name", KITS)
def test_a_machine_is_its_makers_and_replays_exactly(name):
    notes = [Note("x", 0.05, 0.1, 60.0, 0.7, art=p) for p in ("kick", "snare", "hat")]
    a, b = render(name, notes, 1.0), render(name, notes, 1.0)
    assert np.array_equal(a, b)
    kick = {}
    for maker in (0, 1):
        for seed in (0, 1):
            t, f = track(hit(name, "kick", 0.6, 1.2, seed=seed, maker=maker), 25.0, 200.0)
            kick[maker, seed] = np.median(f[(t > 0.3) & (t < 0.5)])
    assert abs(kick[0, 0] / kick[0, 1] - 1.0) < 0.004  # another performance on the same machine: its pitch
    assert abs(kick[0, 0] / kick[1, 0] - 1.0) > 0.004  # another machine: its own
    assert not np.allclose(hit(name, "hat", maker=0), hit(name, "hat", maker=1))


def test_a_worn_machine_wanders_and_hisses():
    """Wear is drift, looseness and hiss, not timing: each stroke a little off pitch, and hiss through the VCAs."""
    def pitches(wear):
        out = []
        for seed in range(6):
            t, f = track(hit("drums-808", "kick", 0.6, 1.0, seed=seed, wear=wear), 25.0, 200.0)
            out.append(np.median(f[(t > 0.3) & (t < 0.5)]))
        return np.std(1200 * np.log2(np.array(out) / np.mean(out)))

    assert pitches(1.0) > 2.0 * pitches(0.0)
    new, old = hit("drums-808", "kick", 0.6, 1.0, wear=0.0), hit("drums-808", "kick", 0.6, 1.0, wear=1.0)
    w = np.hanning(int(0.3 * SR))  # past the click: the boom and whatever hiss rides on it
    tail = slice(int(0.1 * SR), int(0.4 * SR))
    assert share(old[tail] * w, 5000.0, 20000.0) > 20.0 * share(new[tail] * w, 5000.0, 20000.0)
    # and never the timing: onsets land where the notes say
    assert np.flatnonzero(np.abs(old) > 1e-6)[0] == 0


def test_brightness_turns_the_tone_knobs():
    for name, piece in (("drums-808", "hat"), ("drums-808", "snare"), ("drums-909", "crash"), ("drums-909", "hat")):
        dark = centroid(hit(name, piece, 0.6, 1.0, brightness=0.0)[: int(0.25 * SR)])
        bright = centroid(hit(name, piece, 0.6, 1.0, brightness=1.0)[: int(0.25 * SR)])
        assert np.log2(bright / dark) > 0.15, (name, piece)


def test_unknown_pieces_play_the_closed_hat_and_aliases_their_piece():
    assert np.array_equal(hit("drums-808", "no-such-piece"), hit("drums-808", "hat"))
    assert np.array_equal(hit("drums-909", ""), hit("drums-909", "hat"))
    assert np.array_equal(hit("drums-808", "BD"), hit("drums-808", "kick"))
    assert dm.piece_of("oh") == "hat-open" and dm.piece_of("claves") == "clave"


@pytest.mark.parametrize("name", KITS)
def test_voices_end_cleanly_and_start_on_time(name):
    """Every voice rings down and stops: nothing is left once the longest has died, and no voice sounds before
    its note."""
    notes = [Note("x", 0.2 + 0.1 * k, 0.1, 60.0, 0.9, art=p) for k, p in enumerate(dm.SPEC[name]["articulations"])]
    y = render(name, notes, 5.5)
    assert np.all(y[: int(0.2 * SR)] == 0.0)
    assert np.all(y[int(5.0 * SR):] == 0.0)
    assert np.all(np.isfinite(y))


def test_the_kit_is_spread_as_an_audience_hears_it():
    kick = render("drums-808", [Note("x", 0.05, 0.1, 60.0, 0.6, art="kick")], 0.5)
    assert np.allclose(kick[:, 0], kick[:, 1])
    for piece, side in (("tom-hi", 1), ("tom-lo", 0), ("hat", 1), ("ride", 0)):
        y = render("drums-909", [Note("x", 0.05, 0.1, 60.0, 0.6, art=piece)], 1.0)
        assert np.sum(y[:, side] ** 2) > 1.3 * np.sum(y[:, 1 - side] ** 2), piece


@pytest.mark.parametrize("name", KITS)
def test_the_pieces_sit_in_the_kits_balance(name):
    """Each piece's first 100 ms at velocity 0.6, K-weighted, against the kick, within 2 dB of BALANCE (a producer's
    mix: the snare with the kick, the hats 10 dB under), over two machines."""
    kw = master._k_weighting(SR)

    def short(y):
        x = y[: int(0.1 * SR)]
        for b, a in kw:
            x = lfilter(b, a, x)
        return 10 * np.log10(np.mean(x * x) + 1e-30)

    for piece in dm.SPEC[name]["articulations"]:
        rel = [short(hit(name, piece, 0.6, 0.5, maker=m)) - short(hit(name, "kick", 0.6, 0.5, maker=m)) for m in (0, 1)]
        assert abs(np.mean(rel) - dm.BALANCE[piece]) < 2.0, (piece, np.mean(rel))


@pytest.mark.parametrize("name", KITS)
def test_the_groove_sits_at_the_drums_level_without_spikes(name):
    """The typical groove (tools/instrument_levels.py) at -28.4 LUFS, the frame drum's full pattern, within half a
    dB; its true peak 15 to 23 dB over that (the frame drum's own part in H peaks 26.6 dB over its loudness)."""
    spec = dm.SPEC[name]
    notes = levels.typical_part(spec)
    y = levels.render_placed(dm, name, notes)
    lufs = levels.loudness_while_playing(y, notes)
    assert abs(lufs - levels.target_of(spec)) < 0.5
    s0, s1 = min(n.start for n in notes), max(n.start + n.dur for n in notes) + 0.5
    seg = y[int(s0 * SR): int(s1 * SR)]
    assert 15.0 < master.true_peak(seg) - lufs < 23.0
