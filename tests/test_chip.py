"""The chip voices, measured against what the NES's 2A03 does."""

import numpy as np
import pytest
from scipy.signal.windows import blackmanharris

from songbird.score import Note
from songbird.synth import chip

SR = 44100
SETTINGS = dict(brightness=0.5, wear=0.25, ornament=0.0, body=1.0, maker=0, tonic=62)


def render(name, notes, secs, settings=None, maker=0):
    rng = np.random.default_rng([0, 17, 99])
    make = np.random.default_rng([maker, 29, 99])
    return chip.render(name, tuple(notes), SR, int(secs * SR), rng, make, {**SETTINGS, **(settings or {})})


def hz(m):
    return 440.0 * 2.0 ** ((m - 69.0) / 12.0)


def spectrum(y, t0, t1, pad=1):
    seg = y[int(t0 * SR): int(t1 * SR)]
    n = pad * len(seg)
    return np.abs(np.fft.rfft(seg * blackmanharris(len(seg)), n)), np.fft.rfftfreq(n, 1 / SR)


def harmonics_db(y, f0, count):
    spec, freqs = spectrum(y, 0.4, 1.4, pad=4)
    h = np.array([spec[(freqs > f0 * (k - 0.2)) & (freqs < f0 * (k + 0.2))].max() for k in range(1, count + 1)])
    return 20 * np.log10(h / h.max())


def off_the_lines_db(y, f0, t0=0.5, t1=1.5):
    """The strongest component more than 10 Hz from any multiple of f0, against the strongest on one."""
    spec, freqs = spectrum(y, t0, t1)
    k = np.maximum(np.round(freqs / f0), 1)
    on = np.abs(freqs - k * f0) < 10.0
    band = (freqs > 30) & (freqs < 20000)
    return 20 * np.log10(spec[band & ~on].max() / spec[band & on].max())


@pytest.mark.parametrize("duty,missing", [("12", 8), ("25", 4), ("50", 2)])
def test_a_pulse_of_each_width_lacks_the_harmonics_its_width_divides(duty, missing):
    db = harmonics_db(render("chip", [Note("x", 0.1, 1.5, 69.0, 1.0, art=duty)], 1.8), 440.0, 16)
    gone = [k for k in range(1, 17) if k % missing == 0]
    kept = [k for k in range(1, 8) if k % missing != 0]
    assert np.all(db[np.array(gone) - 1] < -80.0)
    assert np.all(db[np.array(kept) - 1] > -20.0)


def test_75_percent_is_25_percent_upside_down():
    a = harmonics_db(render("chip", [Note("x", 0.1, 1.5, 69.0, 1.0, art="25")], 1.8), 440.0, 12)
    b = harmonics_db(render("chip", [Note("x", 0.1, 1.5, 69.0, 1.0, art="75")], 1.8), 440.0, 12)
    ok = a > -60
    assert np.allclose(a[ok], b[ok], atol=0.3)


@pytest.mark.parametrize("short,period", [(False, 32767), (True, 93)])
def test_the_noise_register_repeats_after_32767_or_93_steps(short, period):
    reg = 1
    seen = {reg: 0}
    for k in range(1, 40000):
        reg = int(chip._lfsr(reg, short))
        if reg in seen:
            break
        seen[reg] = k
    assert k - seen[reg] == period


def test_fifteen_volume_steps_on_the_mixers_curve():
    amps = []
    for v in range(1, 16):
        y = render("chip", [Note("x", 0.1, 0.6, 69.0, v / 15.0, art="50")], 1.0)
        amps.append(np.ptp(y[int(0.104 * SR): int(0.1155 * SR)]))  # the note's first frame, at its own volume
    amps = np.array(amps) / amps[-1]
    curve = np.array([chip.pulse_level(v) for v in range(1, 16)]) / chip.pulse_level(15)
    assert np.all(np.diff(amps) > 0) and np.allclose(amps, curve, rtol=0.01)
    assert 21.0 < 20 * np.log10(1.0 / amps[0]) < 23.0  # not 23.5, as a linear 1..15 would be


@pytest.mark.parametrize("name", ["chip", "chip-bass"])
def test_exactly_in_tune_without_the_timers_rounding(name):
    lo, hi = chip.SPEC[name]["register"]
    for m in (lo + 2, (lo + hi) // 2, hi - 2):
        y = render(name, [Note("x", 0.1, 1.5, float(m), 0.8)], 1.8)
        spec, freqs = spectrum(y, 0.3, 1.5, pad=16)
        band = (freqs > hz(m) * 0.97) & (freqs < hz(m) * 1.03)
        i = np.flatnonzero(band)[np.argmax(spec[band])]
        a, b, c = np.log(spec[i - 1: i + 2])
        peak = freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])
        assert abs(1200 * np.log2(peak / hz(m))) < 0.2


def test_nothing_folds_back():
    for duty in ("12", "25", "50"):
        y = render("chip", [Note("x", 0.1, 1.8, 96.0, 1.0, art=duty)], 2.2)
        assert off_the_lines_db(y, hz(96)) < -70.0
    # the looped noise is a pitched buzz: everything on its lines, clock / 93 apart
    rate = chip.CPU / chip.NOISE_PERIODS[3]
    nt, nv, _ = chip._noise_events(np.array([0.0]), np.array([1.6]), np.array([rate]), np.array([True]),
                                   np.array([15.0]), 1)
    et, el = chip._mix_tnd(np.empty(0), np.empty(0), nt, nv, 0.0, 0.0)
    y = chip.osc.decimate2(chip._staircase(et * 2 * SR, el, int(3.2 * SR)))
    assert off_the_lines_db(y - y.mean(), rate / 93.0) < -60.0


def test_the_triangle_is_32_steps_of_16_levels_and_buzzes():
    tt, tv, _ = chip._triangle_events(np.array([0.0]), np.array([1.0]), np.array([110.0]), 0.0)
    one = (tt >= 0.5) & (tt < 0.5 + 1 / 110.0)
    assert one.sum() == 30  # 32 steps, two of them repeats (the bottom and the top)
    assert sorted(set(tv.astype(int))) == list(range(16))
    et, el = chip._mix_tnd(tt, tv, np.empty(0), np.empty(0), 15.0, chip.tnd_level(15, 0))
    raw = chip.osc.decimate2(chip._staircase(et * 2 * SR, el, 2 * SR))[:SR]
    db = harmonics_db(raw, 110.0, 34)
    assert -21 < db[2] < -17.5  # the 3rd: a triangle's 1/9
    assert -33 < db[30] < -27 and -33 < db[32] < -27  # the steps' images: 30 dB down, not an ideal triangle's 60


def test_the_console_thins_a_low_triangle():
    for m, lo, hi in ((45, 13.0, 16.0), (33, 22.0, 26.0)):  # 110 Hz, 55 Hz
        y = render("chip-bass", [Note("x", 0.1, 1.5, float(m), 0.7)], 1.8)
        tt, tv, _ = chip._triangle_events(np.array([0.1]), np.array([1.6]), np.array([hz(m)]), 0.0)
        et, el = chip._mix_tnd(tt, tv, np.empty(0), np.empty(0), 15.0, chip.tnd_level(15, 0))
        raw = chip.osc.decimate2(chip._staircase(et * 2 * SR, el, int(3.6 * SR)))[: int(1.8 * SR)] * chip.OUT
        spec_y, freqs = spectrum(y, 0.4, 1.4, pad=4)
        spec_r, _ = spectrum(raw, 0.4, 1.4, pad=4)
        band = (freqs > hz(m) * 0.9) & (freqs < hz(m) * 1.1)
        assert lo < 20 * np.log10(spec_r[band].max() / spec_y[band].max()) < hi


def test_the_triangle_stops_where_it_is_and_starts_from_there():
    y = render("chip-bass", [Note("x", 0.1, 0.3037, 45.0, 0.7), Note("x", 0.6, 0.3, 45.0, 0.7)], 1.2)
    rest = y[int(0.45 * SR): int(0.59 * SR)]
    assert np.abs(rest).max() < 1e-3 * np.abs(y).max()  # stopped: the console's filters took the held level away
    steps = np.abs(np.diff(y[int(0.2 * SR): int(0.4 * SR)])).max()  # a step of the staircase, while it runs
    assert np.abs(np.diff(y[int(0.59 * SR): int(0.61 * SR)])).max() < 1.2 * steps  # coming back in is one more
    assert render("chip-bass", [Note("x", 0.1, 0.3, 45.0, 0.2)], 0.6).std() == pytest.approx(
        render("chip-bass", [Note("x", 0.1, 0.3, 45.0, 1.0)], 0.6).std())  # and no volume


def test_a_frame_arpeggio_steps_through_its_chord_sixty_times_a_second():
    y = render("chip", [Note("x", 0.1, 1.0, 69.0, 0.8, art="arp-maj")], 1.3)
    frame = SR / chip.FRAME
    heard = []
    for k in range(3, 12):
        a, b = int(0.1 * SR + k * frame + 60), int(0.1 * SR + (k + 1) * frame - 60)
        spec = np.abs(np.fft.rfft(y[a:b] * np.hanning(b - a), 1 << 16))
        freqs = np.fft.rfftfreq(1 << 16, 1 / SR)
        band = (freqs > 380) & (freqs < 720)
        heard.append(freqs[band][np.argmax(spec[band])])
    expect = [hz(69 + (0, 4, 7)[k % 3]) for k in range(3, 12)]
    assert np.allclose(heard, expect, rtol=0.01)


def test_the_vibrato_comes_from_ornament_after_a_delay():
    def track(ornament):
        y = render("chip", [Note("x", 0.1, 2.0, 69.0, 0.8, art="50")], 2.3, dict(ornament=ornament))
        out = []
        for t in np.arange(0.12, 1.9, 1 / chip.FRAME):
            spec, freqs = spectrum(y, t, t + 0.05, pad=32)
            band = (freqs > 400) & (freqs < 480)
            out.append(1200 * np.log2(freqs[band][np.argmax(spec[band])] / 440.0))
        return np.array(out)

    plain, wobbly = track(0.0), track(1.0)
    assert np.abs(plain).max() < 3.0
    assert np.abs(wobbly[:10]).max() < 3.0  # nothing for the first frames
    assert 25.0 < (wobbly[40:].max() - wobbly[40:].min()) / 2 < 45.0  # then about a third of a semitone


def test_each_channel_plays_one_sound_at_a_time():
    # a hat straight after a crash cuts it; of a snare and a hat together, the snare takes the noise channel
    crash = render("chip-drums", [Note("x", 0.1, 0.2, 60.0, 0.8, art="crash")], 1.2)
    cut = render("chip-drums", [Note("x", 0.1, 0.2, 60.0, 0.8, art="crash"), Note("x", 0.3, 0.1, 60.0, 0.8, art="hat")],
                 1.2)
    assert np.std(cut[int(0.5 * SR): int(0.8 * SR)]) < 0.01 * np.std(crash[int(0.5 * SR): int(0.8 * SR)])
    snare = render("chip-drums", [Note("x", 0.1, 0.2, 60.0, 0.8, art="snare")], 0.6)
    both = render("chip-drums", [Note("x", 0.1, 0.2, 60.0, 0.8, art="hat"), Note("x", 0.1, 0.2, 60.0, 0.8, art="snare")],
                  0.6)
    assert np.allclose(both, snare)


def test_the_kick_sweeps_down_the_triangle_a_frame_at_a_time():
    y = render("chip-drums", [Note("x", 0.1, 0.2, 60.0, 1.0, art="kick")], 0.6)
    frame = SR / chip.FRAME
    peaks = []
    for k in range(1, 5):
        a, b = int(0.1 * SR + k * frame + 40), int(0.1 * SR + (k + 1) * frame - 40)
        spec = np.abs(np.fft.rfft(y[a:b] * np.hanning(b - a), 1 << 16))
        freqs = np.fft.rfftfreq(1 << 16, 1 / SR)
        band = (freqs > 40) & (freqs < 400)
        peaks.append(freqs[band][np.argmax(spec[band])])
    assert np.all(np.diff(peaks) < 0)
    soft = render("chip-drums", [Note("x", 0.1, 0.2, 60.0, 0.2, art="kick")], 0.6)
    assert np.sum(soft**2) < np.sum(y**2)  # a soft kick is a shorter sweep
