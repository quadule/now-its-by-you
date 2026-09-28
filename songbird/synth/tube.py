"""A vocal tract as a tube: a Kelly-Lochbaum waveguide with a nasal branch.

After Kelly & Lochbaum (1962), Perry Cook's SPASM singing synthesizer (1990),
and Neil Thapen's Pink Trombone (2017), which is the sound to aim for. The
tract is a row of short cylinders from glottis to lips. Pressure waves move
one section per step in each direction and partly reflect wherever the
cross-section changes; a nose branches off at the velum. Formants are not
specified anywhere: they fall out of the shape, all the way up the spectrum.

Shapes follow Stevens & House (1955): a neutral tube, a tongue constriction
given by its place and narrowness, and a lip opening; consonants add one more,
tighter constriction at their place of articulation. Units are centimetres,
measured from the glottis on a 17.5 cm tract and scaled to the voice's length.

The tract runs at twice the audio rate so that 44 sections make 17.5 cm.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit

SPEED_OF_SOUND = 35000.0  # cm/s
OVERSAMPLE = 2
REFERENCE_LENGTH = 17.5  # cm, an adult male tract
GLOTTAL_REFLECTION = 0.75
LIP_REFLECTION = -0.85
FADE = 0.999  # wall losses per section per step
NOSE_LENGTH = 11.0  # cm from velum to nostrils
VELUM_AT = 6.8  # cm from the glottis


@dataclass(frozen=True)
class Shape:
    """One articulatory posture."""

    tongue_at: float = 9.0  # cm from the glottis where the tongue narrows the tract most
    tongue_radius: float = 1.2  # cm left open there (1.2 is no constriction at all)
    lips: float = 0.8  # cm radius of the lip opening
    place: float = 0.0  # cm from the glottis of a consonant constriction; 0 for none
    place_radius: float = 1.2  # cm left open at that constriction; 0 closes it
    velum: float = 0.0  # cm^2 opening into the nose


def sections(scale: float, sr: int) -> int:
    """Section count for a tract `scale` times shorter than the reference."""
    step = SPEED_OF_SOUND / (OVERSAMPLE * sr)
    return int(round(REFERENCE_LENGTH / scale / step))


def profile(n: int, tongue_at, tongue_radius, lips, constrictions=()) -> np.ndarray:
    """Radius of each of n sections, glottis first, in reference centimetres.

    Arguments may be scalars or arrays over blocks (then the result is
    (blocks, n)). constrictions: (place, radius) pairs, each narrowing the
    tube smoothly over about a centimetre either side of its place.
    """
    x = (np.arange(n) + 0.5) * REFERENCE_LENGTH / n  # positions on the 17.5 cm reference
    at, narrow, lip = (np.asarray(v, dtype=float)[..., None] for v in (tongue_at, tongue_radius, lips))
    r = np.where(x < 2.0, 0.45, np.where(x < 4.0, 0.45 + 0.55 * (x - 2.0) / 2.0, 1.2))  # larynx tube into the pharynx
    tongue = narrow + 0.025 * (1.2 - narrow) * (x - at) ** 2
    r = np.where(x < 15.0, np.minimum(r, tongue), r)
    r = np.where(x >= REFERENCE_LENGTH - 1.0, lip, r)
    for place, radius in constrictions:
        place = np.asarray(place, dtype=float)[..., None]
        radius = np.asarray(radius, dtype=float)[..., None]
        d = np.abs(x - place)
        blend = np.where(d < 1.2, 0.5 - 0.5 * np.cos(np.pi * d / 1.2), 1.0)
        r = np.minimum(r, radius + (r - radius) * blend)
    return np.maximum(r, 0.0)


def radii(shape: Shape, n: int) -> np.ndarray:
    extra = [(shape.place, shape.place_radius)] if shape.place > 0.0 else []
    return profile(n, shape.tongue_at, shape.tongue_radius, shape.lips, extra)


def areas(shape: Shape, n: int) -> np.ndarray:
    return np.pi * radii(shape, n) ** 2


def nose_areas(n_tract: int) -> np.ndarray:
    """A fixed nasal passage: narrow at the velum, wide in the middle, narrow at the nostrils."""
    n = max(4, int(round(NOSE_LENGTH / REFERENCE_LENGTH * n_tract)))
    x = np.linspace(0.0, 1.0, n)
    nose = np.pi * (0.35 + 0.45 * np.sin(np.pi * x) ** 0.7) ** 2
    nose[0] = 0.0  # the velar port: set per block from the velum track
    return nose


@njit(cache=True, nogil=True)
def _scatter(right, left, area, out_right, out_left, lo, hi):
    """Two-port junctions i in [lo, hi): flow waves partly reflect where the area changes."""
    for i in range(lo, hi):
        total = area[i - 1] + area[i]
        if total < 1e-12:  # closed on both sides
            out_right[i] = 0.0
            out_left[i] = 0.0
            continue
        r = (area[i - 1] - area[i]) / total
        d = r * (right[i - 1] - left[i])
        out_right[i] = right[i - 1] - d
        out_left[i] = left[i] - d


@njit(cache=True, nogil=True)
def run(source, noise, noise_at, tract, velum, nose, nose_start, block):
    """Push a glottal source through the tract.

    Waves are volume-velocity waves: `right` travels toward the lips, `left`
    toward the glottis, and the flow in a section is their sum. A closed end
    reflects flow with -1 (the glottis, nearly), an open end with +1 (the
    lips and nostrils, less radiation loss).

    source, noise: per internal sample. noise is turbulence injected at
    section noise_at[b] (fractional; negative for none) during block b.
    tract: (blocks, sections) areas; velum: (blocks,) area of the velar port,
    which is the nose's first section. nose: fixed areas of the rest of the
    nasal passage. Returns the flow radiated from lips and nostrils.
    """
    n_blocks, n = tract.shape
    m = nose.shape[0]
    right = np.zeros(n)
    left = np.zeros(n)
    out_right = np.zeros(n + 1)
    out_left = np.zeros(n + 1)
    nose_right = np.zeros(m)
    nose_left = np.zeros(m)
    nose_out_right = np.zeros(m + 1)
    nose_out_left = np.zeros(m + 1)
    area = tract[0].copy()
    previous = tract[0].copy()
    nose_area = nose.copy()
    previous_port = velum[0]
    out = np.zeros(source.shape[0])
    for b in range(n_blocks):
        for k in range(block):
            t = b * block + k
            if t >= source.shape[0]:
                return out
            lam = (k + 1.0) / block
            for i in range(n):
                area[i] = previous[i] + lam * (tract[b, i] - previous[i])
            nose_area[0] = previous_port + lam * (velum[b] - previous_port)

            out_right[0] = -GLOTTAL_REFLECTION * left[0] + source[t]
            out_left[n] = -LIP_REFLECTION * right[n - 1]
            _scatter(right, left, area, out_right, out_left, 1, nose_start)
            _scatter(right, left, area, out_right, out_left, nose_start + 1, n)
            # where tract and nose meet, the three share one pressure
            i = nose_start
            total = area[i - 1] + area[i] + nose_area[0]
            if total < 1e-12:
                out_right[i] = 0.0
                out_left[i] = 0.0
                nose_out_right[0] = 0.0
            else:
                incoming = right[i - 1] - left[i] - nose_left[0]
                out_right[i] = 2.0 * area[i] / total * incoming + left[i]
                out_left[i] = right[i - 1] - 2.0 * area[i - 1] / total * incoming
                nose_out_right[0] = 2.0 * nose_area[0] / total * incoming + nose_left[0]
            where = noise_at[b]
            if where >= 1.0:
                j = int(where)
                if j < n:
                    half = 0.5 * noise[t]
                    out_right[j] += half
                    out_left[j] -= half
            for i in range(n):
                right[i] = out_right[i] * FADE
                left[i] = out_left[i + 1] * FADE

            nose_out_left[m] = -LIP_REFLECTION * nose_right[m - 1]
            _scatter(nose_right, nose_left, nose_area, nose_out_right, nose_out_left, 1, m)
            for i in range(m):
                nose_right[i] = nose_out_right[i] * FADE
                nose_left[i] = nose_out_left[i + 1] * FADE

            out[t] = right[n - 1] + nose_right[m - 1]
        for i in range(n):
            previous[i] = tract[b, i]
        previous_port = velum[b]
    return out


def impulse_response(shape: Shape, n: int, sr: int, length: int = 8192) -> np.ndarray:
    """The tract's response to one click at the glottis, at the internal rate."""
    source = np.zeros(length)
    source[0] = 1.0
    block = length
    tract = areas(shape, n)[None, :]
    return run(source, np.zeros(length), np.array([-1.0]), tract, np.array([shape.velum]),
               nose_areas(n), int(round(VELUM_AT / REFERENCE_LENGTH * n)), block)


def formants(shape: Shape, n: int = 44, sr: int = 44100, count: int = 3) -> list[float]:
    """Resonance peaks of a posture, in Hz, lowest first."""
    rate = OVERSAMPLE * sr
    h = impulse_response(shape, n, sr)
    spectrum = 20 * np.log10(np.abs(np.fft.rfft(h * np.hanning(len(h)), 1 << 16)) + 1e-12)
    freqs = np.fft.rfftfreq(1 << 16, 1.0 / rate)
    peaks = [i for i in range(1, len(spectrum) - 1)
             if spectrum[i] > spectrum[i - 1] and spectrum[i] >= spectrum[i + 1] and 150.0 < freqs[i] < 5000.0]
    return [float(freqs[i]) for i in peaks[:count]]
