"""The band's physical models, measured against what real instruments do."""

import numpy as np
import pytest

from songbird.score import Note
from songbird.synth import body, bowed, drum, pipe, reed
from songbird.theory import midi_to_hz

SR = 44100


def peak_hz(y: np.ndarray, guess: float, t0: float, t1: float) -> float:
    """Frequency of the strongest peak within 6% of guess, by zero-padded FFT and parabolic interpolation."""
    seg = y[int(t0 * SR): int(t1 * SR)]
    seg = seg * np.hanning(len(seg))
    n = 16 * SR
    spec = np.abs(np.fft.rfft(seg, n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    band = (freqs > guess * 0.94) & (freqs < guess * 1.06)
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


def harmonic_db(y: np.ndarray, f0: float, t0: float, t1: float, count: int) -> np.ndarray:
    seg = y[int(t0 * SR): int(t1 * SR)]
    seg = seg * np.hanning(len(seg))
    n = 1 << int(np.ceil(np.log2(4 * len(seg))))
    spec = np.abs(np.fft.rfft(seg, n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    levels = [spec[(freqs > f0 * (h - 0.3)) & (freqs < f0 * (h + 0.3))].max() for h in range(1, count + 1)]
    return 20 * np.log10(np.array(levels) / levels[0])


def cents(a: float, b: float) -> float:
    return 1200 * np.log2(a / b)


# --- bodies -----------------------------------------------------------------------


def test_body_is_seeded_normalized_and_rings_down():
    a = body.impulse_response(body.GUITAR, SR, seed=3)
    assert np.array_equal(a, body.impulse_response(body.GUITAR, SR, seed=3))
    assert not np.allclose(a, body.impulse_response(body.GUITAR, SR, seed=4))  # another maker, another guitar
    assert a.shape[1] == 2 and abs(np.corrcoef(a[:, 0], a[:, 1])[0, 1]) < 0.6  # two microphones, not one
    freqs, db = body.response(a, SR)
    band = (freqs > body.GUITAR.lowcut) & (freqs < body.GUITAR.highcut)
    assert abs(np.sqrt(np.mean(10 ** (db[band] / 10)))) > 0.3  # about unity gain where it plays
    tail = a[-len(a) // 10:]
    assert np.sum(tail**2) < 1e-4 * np.sum(a**2)


def test_a_bigger_body_resonates_lower():
    def air_mode(size):
        freqs, db = body.response(body.impulse_response(body.GUITAR, SR, seed=0, size=size), SR, n=1 << 17)
        band = (freqs > 60) & (freqs < 150)
        return freqs[band][np.argmax(db[band])]

    assert air_mode(1.2) < air_mode(1.0) * 0.9


# --- the bowed string -----------------------------------------------------------------


@pytest.mark.parametrize("pitch", [55, 69, 81])
def test_bowed_string_is_in_tune_and_in_helmholtz_motion(pitch):
    y = bowed.bow([Note("fiddle", 0.1, 1.6, float(pitch), 0.7)], SR, int(2.0 * SR), np.random.default_rng(1),
                  vibrato=0.0)
    f = midi_to_hz(pitch)
    assert abs(cents(peak_hz(y, f, 0.6, 1.6), f)) < 3.0
    h = harmonic_db(y, f, 0.8, 1.6, 4)
    # Helmholtz motion puts a sawtooth on the bridge: harmonics fall as 1/n
    assert np.all(np.abs(h[1:] - 20 * np.log10(1 / np.arange(2, 5))) < 2.5)


def test_bowed_string_is_deterministic_and_lifts_off():
    notes = [Note("fiddle", 0.1, 0.5, 62.0, 0.6), Note("fiddle", 0.6, 0.5, 64.0, 0.6, art="slur"),
             Note("fiddle", 1.3, 0.6, 66.0, 0.6)]
    a = bowed.bow(notes, SR, int(3.0 * SR), np.random.default_rng(5))
    b = bowed.bow(notes, SR, int(3.0 * SR), np.random.default_rng(5))
    assert np.array_equal(a, b) and np.all(np.isfinite(a))
    playing = np.sqrt(np.mean(a[int(1.4 * SR): int(1.8 * SR)] ** 2))
    after = np.sqrt(np.mean(a[int(2.6 * SR): int(3.0 * SR)] ** 2))
    assert after < 0.1 * playing  # the bow lifts and the string rings down


# --- the pipe -------------------------------------------------------------------------


@pytest.mark.parametrize("pitch", [62, 74, 86])
def test_pipe_is_in_tune_with_a_flutes_spectrum(pitch):
    y = pipe.blow([Note("whistle", 0.1, 1.4, float(pitch), 0.7)], SR, int(1.8 * SR), np.random.default_rng(1))
    f = midi_to_hz(pitch)
    assert abs(cents(peak_hz(y, f, 0.4, 1.4), f)) < 4.0
    h = harmonic_db(y, f, 0.5, 1.4, 3)
    assert -26 < h[1] < -10 and -30 < h[2] < -10  # a nearly pure tone with a little of the next two


def test_tongued_pipe_note_speaks_in_tens_of_milliseconds():
    y = pipe.blow([Note("whistle", 0.2, 0.8, 74.0, 0.8)], SR, int(1.2 * SR), np.random.default_rng(2))
    env = np.sqrt(np.convolve(y**2, np.ones(88) / 88, mode="same"))
    peak = env.max()
    rise = (np.argmax(env > 0.9 * peak) - np.argmax(env > 0.1 * peak)) / SR
    assert 0.005 < rise < 0.08


# --- the drum -------------------------------------------------------------------------


def test_drum_strokes_ring_at_the_skin_and_die_as_played():
    rng = np.random.default_rng(0)
    open_ = drum.hit("bass", 0.8, SR, rng, pitch=80.0)
    muted = drum.hit("mute", 0.8, SR, rng, pitch=80.0)
    spec = np.abs(np.fft.rfft(open_, 1 << 16))
    freqs = np.fft.rfftfreq(1 << 16, 1 / SR)
    assert 70 < freqs[np.argmax(spec)] < 95  # the (0,1) mode, pulled a little sharp by a hard hit
    assert len(muted) < len(open_) / 2
    a = drum.play([Note("drum", 0.1, 0.1, 38.0, 0.7, art="tip")], SR, SR, np.random.default_rng(1))
    b = drum.play([Note("drum", 0.1, 0.1, 38.0, 0.7, art="tip")], SR, SR, np.random.default_rng(1))
    assert np.array_equal(a, b)


# --- the drone ------------------------------------------------------------------------


def test_reeds_are_in_tune_and_beat():
    y = reed.drone([Note("drone", 0.1, 6.0, 57.0, 0.7)], SR, int(6.5 * SR), np.random.default_rng(3), wear=0.5)
    f = midi_to_hz(57)
    assert abs(cents(peak_hz(y, f, 1.5, 5.5), f)) < 3.0
    h = harmonic_db(y, f, 1.5, 5.5, 6)
    assert np.all(h[1:] > -25)  # a free reed is rich in harmonics
    # detuned reeds beat: the level of the upper harmonics swings over a few seconds
    hop = SR // 20
    env = np.sqrt(np.convolve(y**2, np.ones(hop) / hop, mode="valid"))[int(1.5 * SR): int(5.0 * SR): hop]
    assert env.std() / env.mean() > 0.02


def test_a_fresh_bow_stroke_speaks_like_a_players():
    """The Helmholtz motion is established within about a tenth of a second, as
    in a good détaché, because the hair catches the string as it lands."""
    from scipy.signal import butter, sosfiltfilt

    for pitch in (55, 69):
        f = midi_to_hz(pitch)
        y = bowed.bow([Note("fiddle", 0.1, 1.5, float(pitch), 0.6)], SR, int(1.8 * SR), np.random.default_rng(1),
                      vibrato=0.0)
        band = sosfiltfilt(butter(2, [f * 0.8, f * 1.25], btype="bandpass", fs=SR, output="sos"), y)
        env = np.sqrt(np.convolve(band**2, np.ones(88) / 88, mode="same"))
        steady = np.median(env[int(0.8 * SR): int(1.4 * SR)])
        assert np.argmax(env[int(0.1 * SR):] > 0.9 * steady) / SR < 0.15


# --- the registry: instruments beyond the eight ---------------------------------------------------


def test_every_known_instrument_has_a_spec_and_renders():
    from songbird.synth import instruments

    names = instruments.known()
    assert names[:8] == instruments.INSTRUMENTS and len(set(names)) == len(names)
    for name in ("piano", "banjo", "kit", "organ", "synthbass", "harmonica"):
        info = instruments.spec(name)
        assert info["family"] and len(info["place"]) == 2 and info["level"] > 0
        pitched = info["register"] is not None
        notes = tuple(Note(name, 0.1 + 0.25 * k, 0.4, 60.0 + 2 * k if pitched else 0.0, 0.6,
                           art="" if pitched else ("kick", "snare", "hat")[k % 3]) for k in range(6))
        stem = instruments.render_part(name, notes, SR, SR * 2, {"gains": {name: 0.5}}, seed=3)
        assert stem.shape == (SR * 2, 2) and np.all(np.isfinite(stem)) and np.abs(stem).max() > 1e-4, name
        again = instruments.render_part(name, notes, SR, SR * 2, {"gains": {name: 0.5}}, seed=3)
        assert np.array_equal(stem, again)  # deterministic from the seed


def test_an_instruments_streams_are_its_own():
    from songbird.synth import instruments

    assert [instruments.stream(n) for n in instruments.INSTRUMENTS] == list(range(8))  # the seed's band is unmoved
    others = [instruments.stream(n) for n in instruments.KNOWN]
    assert len(set(others)) == len(others) and min(others) >= 1000
