"""Synthesis: a realized score becomes sound.

Everything is generated in code from the score: no samples, no presets, no
pretrained audio models, so the program stays the whole artifact.
"""

from __future__ import annotations

import numpy as np

from ..score import Score
from . import mixing
from .instruments import INSTRUMENTS, render_band
from .mixing import MixParams
from .voice import VoiceParams, sing

SR = 44100

VOICE_GAIN = 1.6  # about +4 dB: the words sit clear of the band
CHOIR_GAIN = 0.55  # each lineage voice about 5 dB under the lead
CHOIR_PANS = (-0.45, 0.45, -0.25, 0.25, -0.65, 0.65)
PARTS = INSTRUMENTS  # the band's stems, by role (songbird.synth.instruments builds each)


def pan(mono: np.ndarray, position: float) -> np.ndarray:
    """Constant-power pan, position -1 (left) to 1 (right)."""
    theta = (position + 1.0) * np.pi / 4.0
    return np.stack([mono * np.cos(theta), mono * np.sin(theta)], axis=1)


def render_stems(score: Score, sr: int = SR, seed: int = 0, voice: VoiceParams | None = None,
                 progress=None) -> dict[str, np.ndarray]:
    """Each part rendered dry, in stereo, all the same length: a stem for every
    instrument that plays (lute, guitar, harp, bass, fiddle, whistle, drum,
    drone), then the voice and each lineage voice. progress, if given, is told
    each part's name as it starts on it."""
    length = int(np.ceil(score.duration * sr))
    stems = render_band(score, sr, seed, progress)
    sung = list(score.part("voice"))
    if sung:
        if progress is not None:
            progress("voice")
        y = sing(sung, sr, voice or VoiceParams(), seed, score.lexicon)[:length]
        stems["voice"] = pan(np.pad(y, (0, length - len(y))), 0.0) * VOICE_GAIN
    choir = sorted({n.part for n in score.notes if n.part.startswith("choir")}, key=lambda p: int(p[5:]))
    for name, singer in zip(choir, lineage_voices(len(choir), seed)):
        i = int(name[5:]) - 1
        if progress is not None:
            progress(name)
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


def mix(stems: dict[str, np.ndarray], sr: int = SR, seed: int = 0, params: MixParams | None = None) -> np.ndarray:
    """Stems into one stereo mix, in their room (mixing.py: the channel strips,
    buses, room and what MixParams can vary)."""
    return mixing.mix(stems, sr, seed, params)


def render(score: Score, sr: int = SR, seed: int = 0, voice: VoiceParams | None = None,
           mix_params: MixParams | None = None, progress=None) -> np.ndarray:
    """The unmastered stereo mix, in its room. progress, if given, is told each
    part's name as it starts on it, then "mix"."""
    stems = render_stems(score, sr, seed, voice, progress)
    if progress is not None:
        progress("mix")
    return mix(stems, sr, seed, mix_params)
