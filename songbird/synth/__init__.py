"""Synthesis: a realized score becomes sound.

Everything is generated in code from the score: no samples, no presets, no
pretrained audio models, so the program stays the whole artifact.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt

from ..score import Score
from ..theory import midi_to_hz
from . import room
from .pluck import pluck
from .voice import VoiceParams, sing

SR = 44100

# Body resonances as (centre Hz, gain dB, Q): a small lute and a lighter harp.
# Both dip around 2.5 kHz, where the voice's consonants and upper formants live.
LUTE = ((110.0, 5.0, 2.5), (250.0, 3.0, 2.0), (520.0, 2.0, 2.0), (2500.0, -5.0, 0.9))
HARP = ((180.0, 3.0, 1.5), (1000.0, 1.5, 1.0), (2500.0, -4.0, 0.9), (4500.0, -2.0, 0.7))
VOICE_GAIN = 1.6  # about +4 dB: the words sit clear of the strings

# Milestone 1 instrument settings; the voice harvest will drive these.
PARTS = {
    "melody": dict(brightness=0.62, decay=2.6, pick=0.17, body=LUTE, pan=-0.12, gain=1.0),
    "harp": dict(brightness=0.45, decay=3.4, pick=0.11, body=HARP, pan=0.22, gain=0.42),
    "bass": dict(brightness=0.30, decay=4.0, pick=0.21, body=HARP, pan=0.05, gain=0.55),
}


def _peaking(f0: float, gain_db: float, q: float, sr: int) -> np.ndarray:
    """One RBJ peaking-EQ biquad as a second-order section."""
    a = 10.0 ** (gain_db / 40.0)
    w = 2.0 * np.pi * f0 / sr
    alpha = np.sin(w) / (2.0 * q)
    b = np.array([1.0 + alpha * a, -2.0 * np.cos(w), 1.0 - alpha * a])
    den = np.array([1.0 + alpha / a, -2.0 * np.cos(w), 1.0 - alpha / a])
    return np.concatenate([b, den]) / den[0]


def body(x: np.ndarray, sr: int, resonances) -> np.ndarray:
    return sosfilt(np.array([_peaking(f, g, q, sr) for f, g, q in resonances]), x)


def pan(mono: np.ndarray, position: float) -> np.ndarray:
    """Constant-power pan, position -1 (left) to 1 (right)."""
    theta = (position + 1.0) * np.pi / 4.0
    return np.stack([mono * np.cos(theta), mono * np.sin(theta)], axis=1)


def render_stems(score: Score, sr: int = SR, seed: int = 0, voice: VoiceParams | None = None) -> dict[str, np.ndarray]:
    """Each part rendered dry, in stereo, all the same length."""
    rng = np.random.default_rng(seed)
    length = int(np.ceil(score.duration * sr))
    stems = {}
    for name, spec in PARTS.items():
        mono = np.zeros(length)
        for note in score.part(name):
            y = pluck(
                midi_to_hz(note.pitch),
                note.dur,
                sr,
                rng,
                vel=note.vel,
                brightness=spec["brightness"],
                decay=spec["decay"],
                pick=spec["pick"],
            )
            i = int(round(note.start * sr))
            j = min(length, i + len(y))
            mono[i:j] += y[: j - i]
        stems[name] = pan(body(mono, sr, spec["body"]), spec["pan"]) * spec["gain"]
    sung = list(score.part("voice"))
    if sung:
        y = sing(sung, sr, voice or VoiceParams(), seed, score.lexicon)[:length]
        stems["voice"] = pan(np.pad(y, (0, length - len(y))), 0.0) * VOICE_GAIN
    return stems


# How much of each stem reaches the room. The singer stands nearer the
# listener than the instruments do, so words keep their edges.
SENDS = {"voice": 0.5}


def mix(stems: dict[str, np.ndarray], sr: int = SR, seed: int = 0) -> np.ndarray:
    """Stems into one stereo mix, in their room."""
    dry = sum(stems.values())
    send = sum(stem * SENDS.get(name, 1.0) for name, stem in stems.items())
    return room.apply(dry, room.impulse_response(sr, seed=seed), send)


def render(score: Score, sr: int = SR, seed: int = 0, voice: VoiceParams | None = None) -> np.ndarray:
    """The unmastered stereo mix, in its room."""
    return mix(render_stems(score, sr, seed, voice), sr, seed)
