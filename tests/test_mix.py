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
    assert np.array_equal(a, mixing.mix(stems, SR, seed=5))  # a room is its numbers: the same every rendition
    assert not np.array_equal(a, mixing.mix(stems, SR, seed=4, params=MixParams(rt60=1.3)))  # another room


def test_stems_of_any_shape(stems):
    odd = {"voice": stems["voice"][:, 0], "guitar": stems["guitar"][: SR], "bass": stems["bass"][:, :1]}
    y = mixing.mix(odd, SR)  # mono, short and single-column stems all take part
    assert y.shape[1] == 2 and len(y) > len(stems["voice"]) and np.all(np.isfinite(y))


def test_tilt_does_what_it_says():
    rng = np.random.default_rng(8)
    noise = {"guitar": rng.standard_normal((4 * SR, 2)) * 0.1}
    flat, bright = (mixing.mix(noise, SR, params=MixParams(space=0.0, tilt=t)) for t in (0.0, 2.0))

    def band(x, lo, hi):
        f = np.fft.rfftfreq(len(x), 1 / SR)
        p = np.abs(np.fft.rfft(x[:, 0])) ** 2
        return 10 * np.log10(p[(f >= lo) & (f < hi)].sum())
    assert band(bright, 10000, 14000) - band(flat, 10000, 14000) == pytest.approx(2.0, abs=0.5)
    assert band(bright, 40, 80) - band(flat, 40, 80) == pytest.approx(-2.0, abs=0.5)


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


def test_the_de_esser_takes_an_s_across_its_split_and_leaves_the_vowels():
    """An "s" centred at 5 kHz, half under the 5.5 kHz split (a learned singer's, a little lower than most):
    heard against the voice's body and taken from the voice in phase, it comes down by several dB; the vowel
    either side is untouched. (Heard against x minus a high-pass, and taken as that high-pass, the same "s"
    lost nothing.)"""
    rng = np.random.default_rng(5)
    t = np.arange(2 * SR) / SR
    vowel = sum(np.sin(2 * np.pi * 220 * k * t) / k for k in range(1, 12))
    ess = sosfilt(butter(4, [3800, 8000], btype="bandpass", fs=SR, output="sos"), rng.standard_normal(len(t)))
    ess *= 0.5 * np.std(vowel) / np.std(ess)
    s = (t > 0.9) & (t < 1.05)
    x = (np.where(s, ess, vowel) * 0.1)[:, None]
    y = fx.deess(x, SR)[0]
    band = butter(4, [4000, 11000], btype="bandpass", fs=SR, output="sos")

    def level(z, a, b):
        return 10 * np.log10(np.mean(sosfilt(band, z[:, 0])[int(a * SR): int(b * SR)] ** 2))
    assert level(x, 0.92, 1.03) - level(y, 0.92, 1.03) > 3.0
    assert np.allclose(y[: int(0.85 * SR)], x[: int(0.85 * SR)])
    assert np.allclose(y[int(1.6 * SR):], x[int(1.6 * SR):], atol=1e-4)
    # it turns the "s" down and never up: no third of an octave from 1 to 16 kHz is louder (the old one lifted
    # 3-5 kHz by a decibel while it cut)
    seg = slice(int(0.92 * SR), int(1.03 * SR))
    f = np.fft.rfftfreq(seg.stop - seg.start, 1 / SR)
    px, py = (np.abs(np.fft.rfft(z[seg, 0] * np.hanning(seg.stop - seg.start))) ** 2 for z in (x, y))
    for c in 1000 * 2 ** (np.arange(0, 13) / 3):
        m = (f >= c / 2 ** (1 / 6)) & (f < c * 2 ** (1 / 6))
        assert 10 * np.log10(py[m].sum() / px[m].sum()) < 0.05


def test_the_choir_is_de_essed_as_a_group():
    """The lineage choir's voices say each "s" together and send the most to the room and plate: the group is
    de-essed as the lead is."""
    from unittest import mock

    rng = np.random.default_rng(6)
    t = np.arange(3 * SR) / SR
    vowel = sum(np.sin(2 * np.pi * 196 * k * t) / k for k in range(1, 12))
    ess = sosfilt(butter(4, [3800, 8000], btype="bandpass", fs=SR, output="sos"), rng.standard_normal(len(t)))
    ess *= 0.5 * np.std(vowel) / np.std(ess)
    s = (t > 1.4) & (t < 1.55)
    choir = np.where(s, ess, vowel) * 0.05 * ((t > 0.5) & (t < 2.5))
    stems = {"choir1": panned(choir, -0.45), "choir2": panned(choir, 0.45), "guitar": panned(0.02 * vowel, 0.0)}
    band = butter(4, [4000, 11000], btype="bandpass", fs=SR, output="sos")

    def choir_s(deess=None):
        taps = {}
        with mock.patch.object(fx, "deess", deess or fx.deess):
            mixing.mix(stems, SR, 0, MixParams(), taps=taps)
        vowels = 10 * np.log10(np.mean(taps["choir"][int(0.8 * SR): int(1.3 * SR)] ** 2))
        return 10 * np.log10(np.mean(sosfilt(band, taps["choir"], axis=0)[int(1.42 * SR): int(1.53 * SR)] ** 2)) - vowels
    assert choir_s(deess=lambda x, sr, **_: (x, None)) - choir_s() > 3.0


def test_a_riding_compressor_keeps_the_arc():
    # a quiet passage then one 12 dB louder, each with a syllable every half second that stands 6 dB out
    t = np.arange(8 * SR) / SR
    level = np.where(t < 4.0, 0.05, 0.2) * np.where((t % 0.5) < 0.15, 2.0, 1.0)
    x = (level * np.sin(2 * np.pi * 220 * t))[:, None]
    y, _ = fx.compress(x, SR, threshold=-60.0, ratio=4.0, attack=0.005, release=0.05, ride=2.0, above=1.0)

    def db(a, b, peaks):
        seg = y[int(a * SR) : int(b * SR), 0]
        tt = t[int(a * SR) : int(b * SR)]
        sel = ((tt % 0.5) < 0.15) == peaks
        return 10 * np.log10(np.mean(seg[sel] ** 2))
    arc = db(5, 7.5, False) - db(1, 3.5, False)
    assert arc == pytest.approx(12.0, abs=1.5)  # the loud passage is still 12 dB up
    quiet, loud = db(1, 3.5, True) - db(1, 3.5, False), db(5, 7.5, True) - db(5, 7.5, False)
    assert quiet < 5.0 and loud < 5.0  # in both, what stood out (by 6 dB) is evened
    assert quiet == pytest.approx(loud, abs=0.5)  # and alike


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


def test_every_instrument_finds_its_strip():
    """A stem's name decides its channel strip; only a whole name makes a stem a singer."""
    from songbird.synth import instruments

    assert mixing.role_of("voice") == "voice" and mixing.role_of("choir3") == "choir"
    assert mixing.role_of("synthlead") == "synth" and mixing.role_of("lead") == "voice"
    expected = {"keys": "keys", "mallets": "keys", "organ": "organ", "pad": "organ", "drums": "drum",
                "percussion": "drum", "reed": "reed", "bass": "bass"}
    # sustained keyboards take the organ's strip, whatever family their maker filed them under; squeezeboxes a
    # reed strip that keeps their left hand's bass; a kit, a banjo and a mandolin have strips of their own
    specific = {"organ": "organ", "harmonium": "organ", "synth-pad": "organ", "accordion": "squeezebox",
                "concertina": "squeezebox", "kit": "kit", "banjo": "banjo", "mandolin": "mandolin",
                "harmonica": "harmonica"}
    for name in instruments.known():
        role = mixing.role_of(name)
        assert role in mixing.ROLES and role not in ("voice", "choir"), name
        family = instruments.spec(name)["family"]
        if name in specific:
            assert role == specific[name], (name, role)
        elif family in expected and name not in instruments.INSTRUMENTS:
            assert role == expected[family], (name, role)
    assert mixing.role_of("cello") == "strings"  # a cello keeps its low strings: no fiddle's 180 Hz high-pass
    assert mixing.role_of("viola") == "strings" and mixing.role_of("music-box") == "keys"
    assert mixing.role_of("nylon") == "guitar" and mixing.role_of("ukulele") == "guitar"
    # a pedal steel keeps its low strings and swells by its own pedal: not the fiddle's 180 Hz high-pass and duck
    assert mixing.role_of("steel") == "steel" and mixing.ROLES["steel"].duck == 0.0
    assert mixing.ROLES["steel"].eq[0] == ("hp", 70) and mixing.role_of("slide") == "slide"
    assert mixing.role_of("melodeon") == "squeezebox" and mixing.role_of("harmonica") == "harmonica"
    hp = next(band for band in mixing.ROLES["squeezebox"].eq if band[0] == "hp")
    assert hp[1] <= 60  # a Stradella bass button's C2 (65 Hz) kept
    # the banjo and mandolin comp: their strips don't step back under the voice as the lute's doubling does
    assert mixing.role_of("banjo") == "banjo" and mixing.role_of("mandolin") == "mandolin"
    assert mixing.ROLES["banjo"].duck == 0.0 and mixing.ROLES["mandolin"].duck == 0.0
    assert mixing.role_of("melody") == "lute" and mixing.ROLES["lute"].duck > 0.0
    # a kit keeps its kick (a 30 Hz high-pass, not the frame drum's 40) and its cymbals' top
    assert mixing.role_of("kit") == "kit" and mixing.role_of("drummachine") == "drum"
    hp = dict((band[0], band[1]) for band in mixing.ROLES["kit"].eq)
    assert hp["hp"] <= 30 and "high" not in hp and "lp" not in hp
    assert mixing.ROLES["kit"].comp[2] > mixing.ROLES["drum"].comp[2]  # slower to grab: the strokes keep their edge
    for name in ("claps", "stomps", "cajon", "shaker", "tambourine"):
        assert mixing.role_of(name) == "drum", name  # the frame drum's strip, its 40 Hz high-pass
    # a harmonica's presence is its reed's own: its strip takes none of it, as the free reeds' still does
    assert mixing.role_of("harmonica") == "harmonica" and mixing.role_of("accordion") == "squeezebox"
    assert not any(band[0] == "peak" and 2000 <= band[1] <= 4000 for band in mixing.ROLES["harmonica"].eq)
