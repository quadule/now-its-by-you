"""The old 78 (docs/STYLES.md, "An old 78"): the recording as a mix stage any style may have (MixParams.disc,
synth/disc.py), and the style that is recorded so: a parlour piano or a guitar, a fiddle by chance."""

from pathlib import Path

import numpy as np
import pytest
from scipy.signal import hilbert, welch

from songbird.synth import disc as DISC
from songbird.synth.mixing import MixParams

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"
SR = 44100


def song_like(seconds=12.0, seed=3, lead=0.6, ring=2.5):
    """A stand-in for a whole song's mix: silence for the preroll, broadband 'music', then a ring dying away."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    x = np.zeros((n, 2))
    a, b = int(lead * SR), n - int(ring * SR)
    x[a:b] = 0.1 * rng.standard_normal((b - a, 2))
    x[b:] = 0.1 * rng.standard_normal((n - b, 2)) * np.exp(-np.arange(n - b) / (0.15 * SR))[:, None]
    return x


# --- the recording: a mix stage ---------------------------------------------------------------------------------


def test_disc_leaves_no_trace_while_off_and_is_a_mix_setting():
    assert "disc" not in MixParams().to_dict() and MixParams().disc == 0.0
    on = MixParams.parse(["disc=1"])
    assert on.disc == 1.0 and on.to_dict()["disc"] == 1.0 and MixParams.from_dict(on.to_dict()) == on
    assert MixParams(disc=3.0).clamped().disc == 1.0
    x = song_like()
    assert DISC.record(x, SR, 0.0, 1) is x  # off: the stage isn't entered


def test_the_same_record_gives_the_same_samples_and_another_its_own():
    a = DISC.record(song_like(), SR, 1.0, 11)
    b = DISC.record(song_like(), SR, 1.0, 11)
    c = DISC.record(song_like(), SR, 1.0, 12)
    assert np.array_equal(a, b) and not np.array_equal(a[: len(c)], c[: len(a)])
    assert np.array_equal(a[:, 0], a[:, 1])  # mono


def test_the_horn_takes_about_140_hz_to_5_khz_with_its_resonances():
    taps = {}
    x = song_like(20.0)
    mono = (x[:, 0] + x[:, 1]) / 2
    DISC.record(x, SR, 1.0, 5, taps)
    s0, s1 = int(1 * SR), int(16 * SR)
    f, before = welch(mono[s0:s1], SR, nperseg=8192)
    f, after = welch(taps["music"][s0:s1], SR, nperseg=8192)
    gain = 10 * np.log10(after / before)
    gain -= np.median(gain[(f > 300) & (f < 3500)])
    at = lambda hz: float(np.interp(hz, f, gain))  # noqa: E731
    assert at(60) < -12 and at(8000) < -20 and at(12000) < -35  # no low bass, no top
    assert -6 < at(250) < 3 and -6 < at(4000) < 4  # the voice's band kept
    hp, lp = taps["horn"][0][1], taps["horn"][1][1]
    assert 130 <= hp <= 150 and 4600 <= lp <= 5200
    honk = taps["horn"][2][1]
    assert at(honk) > at(honk * 2.2) + 2  # the horn's honk stands out


def test_the_turntable_wavers_once_a_revolution():
    t = np.arange(int(14 * SR)) / SR
    x = np.zeros((len(t), 2))
    x[int(0.6 * SR):, :] = 0.3 * np.sin(2 * np.pi * 1000 * t[int(0.6 * SR):])[:, None]
    taps = {}
    DISC.record(x, SR, 1.0, 7, taps)
    m = taps["music"][int(2 * SR): int(12 * SR)]
    inst = np.diff(np.unwrap(np.angle(hilbert(m)))) * SR / (2 * np.pi)
    k = int(0.01 * SR)
    inst = np.convolve(inst, np.ones(k) / k, mode="valid")
    dev = inst / 1000.0 - 1.0
    assert DISC.WOW[0] * 0.8 < taps["eccentric"] < DISC.WOW[1] * 1.05
    assert 0.8 * taps["eccentric"] < np.max(np.abs(dev - np.median(dev))) < 1.5 * (1 + DISC.WOW_SECOND) * taps["eccentric"]
    f, p = welch(dev - dev.mean(), SR, nperseg=len(dev) // 2)
    assert abs(f[np.argmax(p * (f < 5))] - DISC.RPM / 60) < 0.15  # 1.30 Hz


def test_scratches_click_once_a_revolution_and_the_needle_drops_and_runs_out():
    taps = {}
    x = song_like(120.0)
    y = DISC.record(x, SR, 1.0, 21, taps)
    assert taps["dropped"] and len(y) == len(x) + int(DISC.RUN_OUT * SR)
    times = np.array([t for t, _s in taps["clicks"]])
    later = (times[None, :] - times[:, None]).ravel()
    turns = later[np.abs(later - DISC.TURN) < 1e-6]  # a click heard again exactly a revolution later
    assert len(turns) > 0.4 * len(times) and 0.3 < len(times) / 123.0 < 1.2
    assert times.min() == pytest.approx(DISC.DROP)  # the needle's drop
    runout = taps["runout"] / SR
    lock = times[times > runout]
    assert len(lock) >= 3 and np.allclose(np.diff(lock)[:-1], DISC.TURN)  # the run-out groove's click, then lifted
    # the surface under the music: about NOISE_DB under it, never a peak the limiter would chase
    level = DISC._quick(taps["music"], SR)
    noise = DISC._quick(taps["surface"][int(1 * SR): int(110 * SR)], SR)
    assert DISC.NOISE_DB - 4 < noise - level < DISC.NOISE_DB + 6
    assert np.abs(taps["surface"]).max() < 0.5 * np.abs(taps["music"]).max()


def test_a_section_heard_alone_has_no_needle_drop_and_no_run_out():
    rng = np.random.default_rng(1)
    x = 0.1 * rng.standard_normal((int(8 * SR), 2))  # begins and ends in the music
    taps = {}
    y = DISC.record(x.copy(), SR, 1.0, 4, taps)
    assert not taps["dropped"] and taps["runout"] is None and len(y) == len(x)
