"""Synthesis: a realized score becomes sound.

Everything is generated in code from the score: no samples, no presets, no
pretrained audio models, so the program stays the whole artifact.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..score import Score
from . import mixing
from .instruments import INSTRUMENTS, band_parts
from .mixing import MixParams, lead_lift
from .threads import made
from .voice import VoiceParams, sing

SR = 44100

VOICE_GAIN = 1.6  # about +4 dB: the words sit clear of the band
CHOIR_GAIN = 0.55  # each lineage voice about 5 dB under the lead
CHOIR_PANS = (-0.45, 0.45, -0.25, 0.25, -0.65, 0.65)
PARTS = INSTRUMENTS  # the band's stems, by role (songbird.synth.instruments builds each)


def _filled(y: np.ndarray, length: int) -> np.ndarray:
    """A sung line to the song's length: np.pad(y, (0, length - len(y))) where it falls short, else itself (the
    same values, without a copy)."""
    return np.pad(y, (0, length - len(y))) if len(y) < length else y


def pan(mono: np.ndarray, position: float) -> np.ndarray:
    """Constant-power pan, position -1 (left) to 1 (right)."""
    theta = (position + 1.0) * np.pi / 4.0
    if mono.dtype != np.float64 or mono.ndim != 1:
        return np.stack([mono * np.cos(theta), mono * np.sin(theta)], axis=1)
    out = np.empty((len(mono), 2))  # each side made where it goes: the same products, no copies of the song
    np.multiply(mono, np.cos(theta), out=out[:, 0])
    np.multiply(mono, np.sin(theta), out=out[:, 1])
    return out


def render_stems(score: Score, sr: int = SR, seed: int = 0, voice: VoiceParams | None = None,
                 ancestors: list[VoiceParams] | None = None, progress=None) -> dict[str, np.ndarray]:
    """Each part rendered dry, in stereo, all the same length: a stem for every
    instrument that plays (lute, guitar, harp, bass, fiddle, whistle, drum,
    drone), then the voice and each lineage voice. ancestors: the singers of
    the earlier versions, the parent's first, who sing the choir's parts in
    turn (stand-ins sing the rest). progress, if given, is told each part's
    name as it starts on it."""
    jobs, singers = stem_jobs(score, sr, seed, voice, ancestors)
    # every part at once (threads.made; each has its own random streams), the singers started first: they take longest
    return made(jobs, progress, first=singers)


def stem_jobs(score: Score, sr: int = SR, seed: int = 0, voice: VoiceParams | None = None,
              ancestors: list[VoiceParams] | None = None) -> tuple[list, tuple[str, ...]]:
    """What render_stems makes, not yet made: (name, make) for each part in its order, and the singers'
    names. Each part has its own random streams, so they can be made in any order, or at once."""
    length = int(np.ceil(score.duration * sr))
    jobs = band_parts(score, sr, seed)
    sung = list(score.part("voice"))
    if sung:
        def lead() -> np.ndarray:
            y = sing(sung, sr, voice or VoiceParams(), seed, score.lexicon)[:length]
            y = pan(_filled(y, length), 0.0)
            y *= VOICE_GAIN  # where it lies: the same products
            return y
        jobs.append(("voice", lead))
    choir = sorted({n.part for n in score.notes if n.part.startswith("choir")}, key=lambda p: int(p[5:]))
    learned = (voice or VoiceParams()).engine == "learned"
    singers = [*(ancestors or [])[: len(choir)], *lineage_voices(len(choir), seed, learned=learned)]
    for name, singer in zip(choir, singers):
        i = int(name[5:]) - 1

        def lineage(name=name, singer=singer, i=i) -> np.ndarray:
            y = sing(list(score.part(name)), sr, singer, seed + 101 * (i + 1), score.lexicon)[:length]
            y = pan(_filled(y, length), CHOIR_PANS[i % len(CHOIR_PANS)])
            y *= VOICE_GAIN
            y *= CHOIR_GAIN
            return y
        jobs.append((name, lineage))
    return jobs, (("voice",) if sung else ()) + tuple(choir)


def lineage_voices(n: int, seed: int, learned: bool = False) -> list[VoiceParams]:
    """Stand-ins for the voices of a rendition's ancestors, until the seed
    packet carries them (milestone 5): each a different singer, drawn from the
    ranges the voice harvest will span, half of them an octave down. When the
    lead sings with the learned throat, so do they, each a blend of its own
    (drawn for where it sings), near the throat's own vocal tract and source."""
    rng = np.random.default_rng(7919 + seed)
    voices = []
    for k in range(n):
        low = bool(rng.random() < 0.5)
        u = lambda a, b: float(rng.uniform(a, b))  # noqa: E731
        singer = VoiceParams(
            engine="formant", shift=-12 if low else 0, tract=u(0.95, 1.05) if low else u(1.08, 1.2),
            rd=u(0.6, 1.3), tilt=u(0.3, 0.7), breath=u(0.03, 0.12),
            vibrato_rate=u(4.8, 6.0), vibrato_depth=u(15.0, 40.0), vibrato_delay=u(0.2, 0.4),
            glide=u(0.06, 0.12), scoop=u(0.2, 0.5), jitter=u(0.2, 0.5), wander=u(4.0, 9.0),
            shimmer=u(1.5, 3.5), dynamics=u(6.0, 12.0), mouth=u(0.8, 1.2),
        )
        if learned:
            from . import throat

            singer = replace(singer, engine="learned", timbre=f"machine:{7919 + 104729 * seed + k}",
                             tract=throat.TRACT * u(0.97, 1.03), rd=u(0.65, 1.0), tilt=u(0.3, 0.5))
        voices.append(singer)
    return voices


def mix(stems: dict[str, np.ndarray], sr: int = SR, seed: int = 0, params: MixParams | None = None,
        lift: np.ndarray | None = None) -> np.ndarray:
    """Stems into one stereo mix, in their room (mixing.py: the channel strips,
    buses, room and what MixParams can vary; lift: how the singers rise with the
    arrangement, mixing.lead_lift)."""
    return mixing.mix(stems, sr, seed, params, lift=lift)


def render(score: Score, sr: int = SR, seed: int = 0, voice: VoiceParams | None = None,
           mix_params: MixParams | None = None, ancestors: list[VoiceParams] | None = None,
           progress=None) -> np.ndarray:
    """The unmastered stereo mix, in its room. progress, if given, is told each
    part's name as it starts on it, then "mix"."""
    # each part is made as the mix comes to it, treated and let go (mixing.mix_made): never all held at once
    jobs, _ = stem_jobs(score, sr, seed, voice, ancestors)
    length = int(np.ceil(score.duration * sr)) if jobs else 0
    return mixing.mix_made(jobs, length, sr, seed, mix_params, lift=lift_of(score, sr, length), progress=progress,
                           sound=getattr(score, "sound", None) or None)  # a person's sound design, if any


def lift_of(score: Score, sr: int, stems: dict | int) -> np.ndarray | None:
    """How the singers rise and fall with the arrangement (mixing.lead_lift): from the score's sections and the
    energy the band gave each (score.band["sections"], in the same order). stems: the stems, or their length."""
    length = stems if isinstance(stems, int) else max((len(x) for x in stems.values()), default=0)
    band_sections = (score.band or {}).get("sections") or []
    return lead_lift(list(score.sections), [s.get("energy", 0.55) for s in band_sections], sr, length)


def ancestors_from(records: list[dict], learned: bool) -> list[VoiceParams]:
    """The singers of earlier versions, from their records' singers (the parent's first). When the lead
    sings with the learned throat, an ancestor who sang with the formant singer is heard through the
    throat too, as a singer of its own drawn from its id, so the choir stays one kind of voice."""
    from dataclasses import fields

    known = {f.name for f in fields(VoiceParams)}
    out = []
    for record in records:
        data = {k: v for k, v in (record.get("singer") or {}).items() if k in known}
        singer = VoiceParams(**data)
        if learned and singer.engine != "learned":
            from . import throat

            ident = int(str(record.get("id") or "0")[:15] or "0", 16)
            singer = replace(singer, engine="learned", timbre=f"machine:{ident}", tract=throat.TRACT,
                             rd=min(max(singer.rd, 0.65), 1.0), tilt=min(max(singer.tilt, 0.3), 0.5))
        out.append(singer)
    return out
