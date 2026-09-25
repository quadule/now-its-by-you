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
CHOIR_GAIN = 0.55  # each lineage voice about 5 dB under the lead
CHOIR_PANS = (-0.45, 0.45, -0.25, 0.25, -0.65, 0.65)

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
    choir = sorted({n.part for n in score.notes if n.part.startswith("choir")}, key=lambda p: int(p[5:]))
    for name, singer in zip(choir, lineage_voices(len(choir), seed)):
        i = int(name[5:]) - 1
        y = sing(list(score.part(name)), sr, singer, seed + 101 * (i + 1), score.lexicon)[:length]
        stems[name] = pan(np.pad(y, (0, length - len(y))), CHOIR_PANS[i % len(CHOIR_PANS)]) * VOICE_GAIN * CHOIR_GAIN
    return stems


def lineage_voices(n: int, seed: int) -> list[VoiceParams]:
    """Stand-ins for the voices of a rendition's ancestors, until the seed
    packet carries them (milestone 5): each a different singer, drawn from the
    ranges the voice harvest will span, half of them an octave down."""
    rng = np.random.default_rng(7919 + seed)
    voices = []
    for _ in range(n):
        low = bool(rng.random() < 0.5)
        u = lambda a, b: float(rng.uniform(a, b))  # noqa: E731
        voices.append(VoiceParams(
            shift=-12 if low else 0, tract=u(0.95, 1.05) if low else u(1.08, 1.2),
            rd=u(0.6, 1.3), tilt=u(0.3, 0.7), breath=u(0.03, 0.12),
            vibrato_rate=u(4.8, 6.0), vibrato_depth=u(15.0, 40.0), vibrato_delay=u(0.2, 0.4),
            glide=u(0.06, 0.12), scoop=u(0.2, 0.5), jitter=u(0.2, 0.5), wander=u(4.0, 9.0),
            shimmer=u(1.5, 3.5), dynamics=u(6.0, 12.0), mouth=u(0.8, 1.2),
        ))
    return voices


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
