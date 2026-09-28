"""Drone: free reeds in a box (a harmonium, a shruti box), physically inspired.

A free reed is a brass tongue swinging through a slot: it chops the air
stream into pulses, so its tone is rich in harmonics, falling off slowly. Each
drone note sounds two or three reeds tuned a few cents apart, which beat
slowly against each other (the more worn the instrument, the wider apart). A
reed takes a moment to speak; the bellows swell the sound in, breathe it with
the pumping hand, and let it fade. Air leaks past the reeds as a soft hiss.
The reed chamber's resonances are added by the caller, as a body.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy.signal import sosfilt

from ..theory import midi_to_hz

from .iir import butter

TABLE = 4096


def table(freq: float, sr: int, rng: np.random.Generator, brightness: float = 0.5) -> np.ndarray:
    """One period of a free reed's tone, band-limited for `freq`."""
    top = int(min(80, 0.45 * sr / freq))
    k = np.arange(1, top + 1)
    amps = k ** -(1.5 - 0.6 * brightness)
    amps[1::2] *= 0.8  # a reed's pulse is a little narrower than half the period: even harmonics a shade weaker
    phases = rng.uniform(0.0, 2.0 * np.pi, top)
    x = np.arange(TABLE) / TABLE
    wave = (amps[:, None] * np.sin(2.0 * np.pi * k[:, None] * x[None, :] + phases[:, None])).sum(axis=0)
    return wave / np.max(np.abs(wave))


def tables(freq: float, sr: int, rng: np.random.Generator, slopes, even: float = 0.8, shape=None,
           top: float | None = None, pulse: float = 0.0) -> np.ndarray:
    """Periods of a free reed's tone, one for each spectral slope (harmonic k's amplitude goes as k**-slope),
    sharing their phases so they can be cross-faded without cancelling (a reed played harder is brighter: its
    pulse of air is sharper). even scales the even harmonics (a pulse a little narrower than half the period);
    shape, if given, is a gain per frequency in Hz (a chamber's or a mouth's resonances); top, the highest
    frequency the tone must stay under (for a note that will bend up), by default the note's own; pulse (0..1),
    how far the harmonics start in phase as a pulse train's do (at 1 within 0.3 radian of a cosine: the growl
    of a low reed, whose period the ear hears as a pulse; at 0 their phases random).
    Shape (len(slopes), TABLE), scaled by the brightest row's RMS (0.35), so a reed's loudness doesn't hang
    on how its harmonics' phases happen to peak."""
    count = int(min(80, 0.45 * sr / max(freq, top or freq)))
    count = max(count, 1)
    k = np.arange(1, count + 1)
    phases = rng.uniform(0.0, 2.0 * np.pi, count)
    if pulse:
        phases = 0.5 * np.pi + (phases - np.pi) * (1.0 - float(pulse) * (1.0 - 0.3 / np.pi))
    gain = np.ones(count)
    gain[1::2] *= even
    if shape is not None:
        gain = gain * shape(k * freq)
    x = np.arange(TABLE) / TABLE
    basis = np.sin(2.0 * np.pi * k[:, None] * x[None, :] + phases[:, None])
    out = np.stack([((k ** -float(s)) * gain) @ basis for s in slopes])
    return out * (0.35 / np.sqrt(np.mean(out[int(np.argmin(slopes))] ** 2)))


@njit(cache=True)
def _read_mix(dark, bright, increments, amplitude, mix, out, offset, phase):
    """_read, cross-fading from the dark period to the bright one by mix (0..1), sample by sample."""
    size = dark.shape[0]
    for i in range(increments.shape[0]):
        phase += increments[i]
        if phase >= 1.0:
            phase -= 1.0
        x = phase * size
        j = int(x)
        f = x - j
        j0 = j % size
        j1 = (j + 1) % size
        a = (1.0 - f) * dark[j0] + f * dark[j1]
        b = (1.0 - f) * bright[j0] + f * bright[j1]
        out[offset + i] += amplitude[i] * (a + mix[i] * (b - a))
    return phase


@njit(cache=True)
def _read(wave, increments, amplitude, out, offset, phase):
    size = wave.shape[0]
    for i in range(increments.shape[0]):
        phase += increments[i]
        if phase >= 1.0:
            phase -= 1.0
        x = phase * size
        j = int(x)
        f = x - j
        out[offset + i] += amplitude[i] * ((1.0 - f) * wave[j % size] + f * wave[(j + 1) % size])
    return phase


def drone(notes, sr: int, length: int, rng: np.random.Generator, *, brightness: float = 0.5, wear: float = 0.0,
          reeds: int = 3) -> np.ndarray:
    """A drone part: each note held on `reeds` reeds, swelled in and out by the bellows."""
    out = np.zeros(length)
    for note in notes:
        i0 = max(0, int(round(note.start * sr)))
        i1 = min(length, int(round((note.start + note.dur) * sr)))
        m = i1 - i0
        if m < sr // 10:
            continue
        t = np.arange(m) / sr
        # the bellows: a slow swell in and out, and the pumping hand's breathing
        rise, fall = min(1.2, 0.3 * note.dur), min(1.5, 0.35 * note.dur)
        env = np.clip(t / rise, 0.0, 1.0) ** 1.5 * np.clip((note.dur - t) / fall, 0.0, 1.0) ** 1.2
        pump = rng.uniform(3.0, 4.5)
        env *= 1.0 + 0.07 * np.sin(2.0 * np.pi * t / pump + rng.uniform(0, 6.28))
        env *= note.vel
        freq = midi_to_hz(note.pitch)
        wave = table(freq, sr, rng, brightness)
        spread = 2.0 + 6.0 * wear  # cents between the outer reeds
        for r in range(reeds):
            cents = (r - (reeds - 1) / 2.0) * spread / max(reeds - 1, 1) + rng.normal(0.0, 0.5)
            drift = np.interp(t, np.linspace(0.0, t[-1] + 1e-9, 8), rng.normal(0.0, 0.6 + wear, 8))
            f = freq * 2.0 ** ((cents + drift) / 1200.0)
            # a reed speaks late and softly, the higher ones a little quicker
            speak = np.clip(t / rng.uniform(0.05, 0.12), 0.0, 1.0)
            _read(wave, f / sr, env * speak / reeds, out, i0, rng.random())
        # air past the reeds
        n = m + 64
        hiss = sosfilt(butter(2, [300.0, 2500.0], btype="bandpass", fs=sr, output="sos"), rng.standard_normal(n))[64:]
        out[i0:i1] += hiss * env * 0.02 * (1.0 + wear)
    return out
