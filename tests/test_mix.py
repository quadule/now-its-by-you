import numpy as np
import pytest
from scipy.signal import butter, sosfilt

from songbird.synth import fx, master, mixing, room
from songbird.synth.mixing import MixParams, role_of

SR = 44100


def pluck_track(seconds: float, f0: float, every: float, rng: np.random.Generator) -> np.ndarray:
    """A mono stand-in for an instrument: decaying tones on a beat."""
    n = int(seconds * SR)
    out = np.zeros(n)
    t = np.arange(int(0.8 * SR)) / SR
    note = np.sin(2 * np.pi * f0 * t) * np.exp(-t / 0.25) + 0.3 * np.sin(4 * np.pi * f0 * t) * np.exp(-t / 0.1)
    for start in np.arange(0.0, seconds - 0.8, every):
        i = int(start * SR)
        out[i : i + len(note)] += note * rng.uniform(0.5, 1.0)
    return out


def panned(mono: np.ndarray, position: float) -> np.ndarray:
    theta = (position + 1.0) * np.pi / 4.0
    return np.stack([mono * np.cos(theta), mono * np.sin(theta)], axis=1)


@pytest.fixture(scope="module")
def stems() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(5)
    seconds = 6.0
    n = int(seconds * SR)
    t = np.arange(n) / SR
    # a "voice": vowel-like buzz with syllables and a gap, and a little hiss for its consonants
    buzz = sum(np.sin(2 * np.pi * 220 * k * t) / k for k in range(1, 20))
    syllables = (np.sin(2 * np.pi * 2.0 * t) > -0.2) * (t < 4.5)
    voice = 0.1 * buzz * syllables + 0.01 * rng.standard_normal(n) * syllables
    return {
        "voice": panned(voice, 0.0),
        "guitar": panned(pluck_track(seconds, 196.0, 0.25, rng), -0.2),
        "bass": panned(pluck_track(seconds, 82.0, 0.5, rng), 0.05),
        "choir1": panned(0.05 * buzz * (t > 3.0), -0.45),
        "shaker": np.stack([rng.standard_normal(n), rng.standard_normal(n)], axis=1) * 0.01,  # truly stereo, unknown role
    }


def test_roles_from_names():
    assert role_of("voice") == "voice"
    assert role_of("choir3") == "choir"
    assert role_of("melody") == "lute"
    assert role_of("guitar_low") == "guitar"
    assert role_of("fiddle2") == "fiddle"
    assert role_of("bodhran") == "drum"
    assert role_of("theremin") == "band"


def test_params_round_trip_and_ranges():
    p = MixParams.parse(["rt60=2.2", "wear=0.5", "tone=1,1,1,0.8,0.6", "balance=fiddle:2,drum:-3"])
    assert p.rt60 == 2.2 and p.tone == (1.0, 1.0, 1.0, 0.8, 0.6) and dict(p.balance) == {"fiddle": 2.0, "drum": -3.0}
    assert MixParams.from_dict(p.to_dict()) == p
    wild = MixParams(rt60=9.0, width=-1.0, wear=3.0, forward=40.0).clamped()
    for name, (lo, hi) in mixing.RANGES.items():
        assert lo <= getattr(wild, name) <= hi
    with pytest.raises(ValueError):
        MixParams.parse(["loudness=3"])


def test_mix_is_deterministic(stems):
    a = mixing.mix(stems, SR, seed=4)
    b = mixing.mix({k: v.copy() for k, v in stems.items()}, SR, seed=4)
    assert a.shape[1] == 2 and len(a) > len(stems["voice"])  # the room rings on
    assert np.array_equal(a, b)
    assert not np.array_equal(a, mixing.mix(stems, SR, seed=5))  # a different room


@pytest.mark.parametrize("name", list(mixing.RANGES))
def test_every_knob_at_both_ends(stems, name):
    lo, hi = mixing.RANGES[name]
    for value in (lo, hi):
        y = mixing.mix(stems, SR, seed=1, params=MixParams(**{name: value}))
        assert np.all(np.isfinite(y))
        assert -40.0 < master.loudness(y, SR) < 10.0


def test_mix_without_a_voice_or_band(stems):
    band_only = mixing.mix({k: v for k, v in stems.items() if k not in ("voice", "choir1")}, SR)
    voice_only = mixing.mix({"voice": stems["voice"]}, SR)
    assert np.all(np.isfinite(band_only)) and np.all(np.isfinite(voice_only))
    assert mixing.mix({}, SR).shape == (0, 2)


def test_forward_sets_the_voice_over_the_band(stems):
    near, far = {}, {}
    mixing.mix(stems, SR, params=MixParams(forward=12.0), taps=near)
    mixing.mix(stems, SR, params=MixParams(forward=4.0), taps=far)
    sung = near["singing"] > 0.5

    def gap(t):
        return master.loudness(t["voice"][sung], SR) - master.loudness(t["band"][sung], SR)
    assert gap(near) - gap(far) == pytest.approx(8.0, abs=1.5)


def test_panned_stems_are_treated_as_one_sound():
    rng = np.random.default_rng(2)
    mono = rng.standard_normal(SR)
    found = fx.as_mono(panned(mono, 0.3))
    assert found is not None
    sound, gains = found
    assert np.allclose(sound[:, None] * gains[None, :], panned(mono, 0.3))
    assert fx.as_mono(rng.standard_normal((SR, 2))) is None


def test_equalizer_matches_scipy():
    rng = np.random.default_rng(3)
    x = rng.standard_normal((SR, 2))
    sos = fx.design((("hp", 80), ("peak", 800, -2.0, 1.2), ("peak", 3200, 2.0, 0.9), ("high", 10000, 1.0), ("lp", 15000)), SR)
    assert np.allclose(fx.equalize(x, sos), sosfilt(sos, x, axis=0), atol=1e-10)


def test_dynamics_leave_quiet_or_plain_signals_alone():
    rng = np.random.default_rng(4)
    x = 0.01 * rng.standard_normal((SR, 2))
    assert np.allclose(fx.compress(x, SR, threshold=0.0, ratio=4.0, attack=0.01, release=0.1)[0], x)
    lows = sosfilt(butter(4, 1000, fs=SR, output="sos"), rng.standard_normal((SR, 2)), axis=0)
    assert np.allclose(fx.deess(lows, SR)[0], lows, atol=1e-6)
    assert np.allclose(fx.width(x, SR, 1.0), x)
    mono = fx.width(x, SR, 0.0)
    assert np.allclose(mono[:, 0], mono[:, 1])
    tone = np.sin(2 * np.pi * 440 * np.arange(SR) / SR)[:, None]
    shaped = fx.saturate(np.concatenate([0.5 * tone, 1e-3 * tone]), SR, 1.0)  # loud, then quiet
    quiet = shaped[SR + SR // 2 :]
    assert np.sqrt(np.mean(quiet**2)) == pytest.approx(1e-3 / np.sqrt(2), rel=0.02)  # unity gain for small signals
    loud = shaped[SR // 2 : SR]
    assert np.max(np.abs(loud)) < 0.5 * 0.9  # the loud peaks are rounded off


def test_room_decays_as_asked():
    for rt60 in (0.3, 1.1, 2.5):
        ir = room.impulse_response(SR, rt60=rt60, seed=2)
        assert np.sum(ir**2) / 2 == pytest.approx(1.0)
        band = sosfilt(butter(3, [700, 1400], btype="bandpass", fs=SR, output="sos"), ir, axis=0)
        energy = np.cumsum((band**2).sum(axis=1)[::-1])[::-1]
        edc = 10 * np.log10(energy / energy[0] + 1e-30)
        t30 = 2 * (np.argmax(edc < -35) - np.argmax(edc < -5)) / SR
        assert t30 == pytest.approx(rt60, rel=0.15)
        high = sosfilt(butter(3, 2000, btype="highpass", fs=SR, output="sos"), ir, axis=0)
        coherence = np.sum(high[:, 0] * high[:, 1]) / np.sqrt(np.sum(high[:, 0] ** 2) * np.sum(high[:, 1] ** 2))
        assert abs(coherence) < 0.3  # the ears hear different things: a wide, diffuse tail


def test_wear_adds_noise_and_bends_time(stems):
    clean = mixing.mix(stems, SR, seed=1)
    worn = mixing.mix(stems, SR, seed=1, params=MixParams(wear=1.0))
    assert np.all(np.isfinite(worn)) and worn.shape == clean.shape
    tail = slice(len(clean) - SR // 2, len(clean))  # the room has died away: only the hiss is left
    assert np.std(worn[tail]) > 4 * np.std(clean[tail])
