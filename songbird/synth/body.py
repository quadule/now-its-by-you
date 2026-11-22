"""Instrument bodies, as impulse responses built from resonant modes.

A string or a reed barely radiates on its own: what we hear is the wooden
box it drives. A body here is a few named low modes (the air in the box
breathing through its hole, the top plate's first bending shapes), a denser
scatter of higher plate modes whose exact places differ from one instrument to
the next, and the instantaneous push of the bridge. Its impulse response is
all of those modes ringing down together; a stem's sound is the strings'
bridge force convolved with it.

The scatter is drawn from a seed (the instrument's maker), so two machines own
two different guitars of the same kind, and each channel of the stereo pair
hears a different mix of the high modes, as two microphones would.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.signal import sosfilt

from . import oa
from .iir import butter


@dataclass(frozen=True)
class Body:
    modes: tuple[tuple[float, float, float], ...]  # the named low modes: (Hz, Q, dB)
    dense: tuple[float, float, int]  # the scattered plate modes: lowest Hz, highest Hz, how many
    tilt: float  # dB per octave the scattered modes fall above the lowest
    q: tuple[float, float]  # Q of the scattered modes, from the lowest to the highest
    direct: float  # the instantaneous, unresonated part, against the modes (0..1)
    lowcut: float  # Hz below which the body hardly radiates
    highcut: float  # Hz above which radiation falls away
    hill: tuple[float, float, float] = (0.0, 1.0, 0.0)  # a broad bump over the scatter: Hz, octaves wide, dB
    length: float = 0.6  # seconds of response kept
    coherent: bool = False  # the scattered modes all push one way: broad humps, never a plate's deep notches


# Mode frequencies and Qs follow published measurements of each family (Fletcher
# and Rossing, The Physics of Musical Instruments, chapters 9 and 10, and the
# violin literature for the bridge hill); gains are set so each body's response
# has the shape those measurements show.
GUITAR = Body(  # a steel-string flat top: air mode near 100 Hz, top plate near 200
    modes=((101.0, 22.0, 4.5), (196.0, 30.0, 7.0), (234.0, 28.0, 3.0), (392.0, 30.0, 2.0),
           (532.0, 34.0, 4.0), (660.0, 30.0, 1.0)),
    dense=(700.0, 11000.0, 110), tilt=-1.0, q=(34.0, 22.0), direct=0.25, lowcut=75.0, highcut=11000.0,
)
CITTERN = Body(  # a small bright long-neck lute (bouzouki, cittern): everything higher and livelier
    modes=((132.0, 22.0, 5.0), (262.0, 34.0, 7.0), (318.0, 30.0, 4.0), (486.0, 36.0, 5.0),
           (650.0, 34.0, 2.0), (830.0, 30.0, 2.0)),
    dense=(900.0, 12000.0, 110), tilt=-1.0, q=(40.0, 24.0), direct=0.25, lowcut=110.0, highcut=13000.0,
)
HARP = Body(  # a lever harp's long soundbox: warm, even, a gentle top
    modes=((142.0, 18.0, 4.0), (228.0, 22.0, 5.0), (362.0, 24.0, 3.0), (516.0, 26.0, 2.5), (700.0, 24.0, 1.0)),
    dense=(760.0, 8000.0, 80), tilt=-3.0, q=(28.0, 18.0), direct=0.3, lowcut=90.0, highcut=8000.0,
)
BASS = Body(  # an upright bass, played pizzicato: the air mode near 60 Hz, a big soft top
    modes=((58.0, 16.0, 3.0), (98.0, 20.0, 6.0), (132.0, 24.0, 4.0), (178.0, 22.0, 3.0),
           (240.0, 24.0, 2.0), (330.0, 22.0, 1.0)),
    dense=(360.0, 3000.0, 60), tilt=-5.0, q=(24.0, 16.0), direct=0.25, lowcut=55.0, highcut=3200.0,
)
FIDDLE = Body(  # the violin: A0 near 275 Hz, the B1 pair near 470 and 540, a bridge hill near 2.5 kHz
    modes=((276.0, 18.0, 5.0), (410.0, 28.0, 1.0), (468.0, 34.0, 8.0), (542.0, 36.0, 7.0),
           (700.0, 30.0, 3.0), (910.0, 28.0, 2.0)),
    dense=(950.0, 10000.0, 120), tilt=-1.5, q=(34.0, 20.0), direct=0.2, lowcut=190.0, highcut=9000.0,
    hill=(2600.0, 1.3, 7.0),
)
CELLO = Body(  # the cello: A0 near 100 Hz, the B1 pair near 180 and 215 (the wolf's F-F#), a bridge hill near 1.3 kHz
    # (Askenfelt 1982; Bynum and Rossing 1997; the bridge's own resonances near 1 and 2.2 kHz, Reinicke 1973): a
    # violin scaled about 0.38 in its low modes, the hill half as high up. Above the B1 pair a cello radiates well
    # through 250-500 Hz (its principal formant, Meyer), where the scaled violin has a 7-10 dB hole: a cluster of
    # modes fills it, and the pair stands 6-9 dB over it rather than 11-13.
    modes=((100.0, 16.0, 4.0), (150.0, 26.0, 1.0), (182.0, 30.0, 5.5), (216.0, 32.0, 4.5),
           (258.0, 24.0, 4.0), (292.0, 28.0, 3.0), (330.0, 24.0, 4.0), (372.0, 26.0, 4.0)),
    dense=(400.0, 8000.0, 120), tilt=-2.0, q=(30.0, 18.0), direct=0.2, lowcut=70.0, highcut=7500.0,
    hill=(1300.0, 1.4, 6.0),
)
VIOLA = Body(  # the viola: A0 near 230 Hz, the B1 pair near 410 and 460, a bridge hill near 2.1 kHz; too small a box for
    # its pitch, so its C string's fundamental is weak (Fletcher and Rossing ch. 10). The plate modes run on from
    # 540 Hz, so there is no 5-12 dB trough between the B1 pair and the hill (it left the E string's first notes
    # 5 dB down)
    modes=((230.0, 18.0, 5.0), (340.0, 28.0, 1.0), (410.0, 34.0, 7.0), (462.0, 36.0, 6.0),
           (540.0, 28.0, 3.0), (620.0, 30.0, 3.0)),
    dense=(650.0, 9000.0, 130), tilt=-1.7, q=(34.0, 20.0), direct=0.2, lowcut=160.0, highcut=8500.0,
    hill=(2100.0, 1.3, 6.5),
)
HARMONICA = Body(  # a harmonica's comb and cover plates: hardly any box at all, the reed heard as it is, flat from
    # 120 Hz to 11 kHz (resonant modes here, summed with the reed's direct sound, cut notches of 10-18 dB above
    # 5 kHz); the plates' broad hump near 3 kHz, the player's mouth, the radiation and the hands are shaped by
    # harmonica.py itself, harmonic by harmonic
    modes=(), dense=(2000.0, 12000.0, 0), tilt=0.0, q=(4.0, 3.0), direct=1.0, lowcut=120.0, highcut=11000.0,
    length=0.02,
)
ACCORDION = Body(  # an accordion's reed blocks in their box behind the grille: the box's low hump, the reed
    # chambers' nasal humps near 1.1 and 2.6 kHz, the grille and its cloth taking a little off the top; otherwise
    # nearly flat, as a free reed's radiated pulses are
    modes=((240.0, 4.0, 1.5), (1100.0, 3.0, 3.0), (2600.0, 3.5, 3.0)),
    dense=(500.0, 7000.0, 36), tilt=-0.4, q=(12.0, 8.0), direct=0.65, lowcut=70.0, highcut=8000.0,
    hill=(3000.0, 2.0, 4.0), length=0.2, coherent=True,
)
CONCERTINA = Body(  # a concertina's small hexagonal ends: the reed pan's chambers and the action board's holes
    # lift 1.5 to 3.5 kHz (its cutting edge), the fretwork takes the very top off, the small box rings down quickly
    modes=((420.0, 4.0, 1.5), (1600.0, 3.0, 3.0), (3200.0, 3.5, 3.5)),
    dense=(800.0, 8000.0, 30), tilt=0.0, q=(12.0, 8.0), direct=0.65, lowcut=120.0, highcut=7000.0,
    hill=(3200.0, 1.5, 6.0), length=0.12, coherent=True,
)
REED_BOX = Body(  # a harmonium's reed chamber and bellows box: a few broad, nasal humps
    modes=((180.0, 6.0, 2.0), (420.0, 5.0, 5.0), (1250.0, 4.0, 4.0), (2600.0, 4.0, 1.0)),
    dense=(500.0, 4000.0, 30), tilt=-4.0, q=(14.0, 8.0), direct=0.6, lowcut=60.0, highcut=5000.0,
    length=0.25,
)


def impulse_response(body: Body, sr: int, seed: int = 0, size: float = 1.0, channels: int = 2,
                     alike: float = 0.0) -> np.ndarray:
    """The body's response to one push of the bridge, shape (samples, channels),
    scaled so its average gain across the playing range is 0 dB.

    size scales the body: 1.25 is a quarter bigger, so every mode sits a
    quarter lower; the maker's seed places the scattered modes and nudges the
    named ones, a few percent either way. alike is the share of the scattered
    modes both microphones hear in the same phase (0: each its own, as two
    microphones apart hear them; a pair close together hears most alike, so
    the two don't cancel where they are summed to mono). Made once per
    (body, sr, seed, size, channels, alike) and handed back read-only.
    """
    return _impulse_response(body, int(sr), int(seed), float(size), int(channels), float(alike))


@lru_cache(maxsize=32)
def _impulse_response(body: Body, sr: int, seed: int, size: float, channels: int, alike: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    agree = np.random.default_rng([seed, 1]) if alike > 0.0 else None  # its own draws: the rest stay as they were
    n = int(body.length * sr)
    ir = np.zeros((n, channels))

    def ring(freq: float, q: float) -> tuple[int, np.ndarray]:
        """A mode's unit ring, cut where it has fallen 80 dB."""
        if freq >= 0.45 * sr:
            return 0, np.zeros(0)
        m = min(n, int(9.2 * q / (np.pi * freq) * sr) + 1)
        t = np.arange(m) / sr
        return m, np.exp(-np.pi * freq * t / q) * np.sin(2.0 * np.pi * freq * t)

    # The named modes move with the body, a little each for each maker, and
    # reach both microphones alike: they are the box breathing as a whole.
    for freq, q, db in body.modes:
        f = freq / size * np.exp(rng.normal(0.0, 0.025))
        q = q * np.exp(rng.normal(0.0, 0.1))
        g = 10.0 ** ((db + rng.normal(0.0, 0.7)) / 20.0) * 2.0 * np.pi * f / q  # modal gain ~ bandwidth
        m, y = ring(f, q)
        ir[:m] += g * y[:, None]

    # The scattered plate modes: each microphone hears its own mix of them.
    lo, hi, count = body.dense
    freqs = np.sort(np.exp(rng.uniform(np.log(lo / size), np.log(hi / size), count)))
    hill_f, hill_w, hill_db = body.hill
    for f in freqs:
        x = np.log2(f / (lo / size))
        db = body.tilt * x + rng.normal(0.0, 3.0)
        if hill_db:
            db += hill_db * np.exp(-0.5 * (np.log2(f / (hill_f / size)) / (hill_w / 2.0)) ** 2)
        q = np.interp(x, [0.0, np.log2(hi / lo)], body.q) * np.exp(rng.normal(0.0, 0.15))
        g = 10.0 ** (db / 20.0) * 2.0 * np.pi * f / q
        levels = rng.uniform(0.3, 1.0, channels)  # drawn before the signs, as always
        signs = np.ones(channels) if body.coherent else rng.choice([-1.0, 1.0], channels)
        if agree is not None and agree.random() < alike:
            signs = np.full(channels, signs[0])
        weights = g * levels * signs
        m, y = ring(f, q)
        ir[:m] += y[:, None] * weights[None, :]

    # Radiation: the body is a poor speaker below its air mode and above its top plate's reach.
    band = butter(2, [body.lowcut / size, min(body.highcut / size, 0.45 * sr)], btype="bandpass", fs=sr, output="sos")
    ir = sosfilt(band, ir, axis=0)
    # The instantaneous push, band-limited the same way, carries each attack's edge.
    kick = np.zeros(n)
    kick[0] = 1.0
    kick = sosfilt(band, kick)
    ir = _normalized(ir, sr, body, size)
    ir += body.direct * kick[:, None] * _unit(kick, sr, body, size)
    ir = _normalized(ir, sr, body, size)
    fade = np.ones(n)
    tail = int(0.1 * n)
    fade[-tail:] = np.linspace(1.0, 0.0, tail) ** 2
    out = ir * fade[:, None]
    out.flags.writeable = False
    return out


def _band_gain(h: np.ndarray, sr: int, body: Body, size: float) -> float:
    """RMS gain of a response over the octaves the instrument plays in."""
    spectrum = np.abs(np.fft.rfft(h, 1 << 16))
    freqs = np.fft.rfftfreq(1 << 16, 1.0 / sr)
    lo, hi = max(body.lowcut / size, 40.0), min(body.highcut / size, 0.45 * sr)
    grid = np.exp(np.linspace(np.log(lo), np.log(hi), 256))  # log-spaced: each octave counts alike
    return float(np.sqrt(np.mean(np.interp(grid, freqs, spectrum) ** 2)))


def _unit(h: np.ndarray, sr: int, body: Body, size: float) -> float:
    return 1.0 / max(_band_gain(h, sr, body, size), 1e-12)


def _normalized(ir: np.ndarray, sr: int, body: Body, size: float) -> np.ndarray:
    gains = [_band_gain(ir[:, ch], sr, body, size) for ch in range(ir.shape[1])]
    return ir / max(float(np.mean(gains)), 1e-12)


def resonate(force: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """A mono bridge force through a (samples, channels) body: the stem, same
    length as the force (the body's ring past the end is dropped; stems carry
    their own tails)."""
    return oa.convolve_shared(force, ir, len(force))


def response(ir: np.ndarray, sr: int, n: int = 1 << 15) -> tuple[np.ndarray, np.ndarray]:
    """Frequency response of a body in dB, for checks and plots."""
    spectrum = np.abs(np.fft.rfft(ir.mean(axis=1) if ir.ndim == 2 else ir, n))
    return np.fft.rfftfreq(n, 1.0 / sr), 20.0 * np.log10(spectrum + 1e-12)
