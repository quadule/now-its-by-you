"""What a singer hears while they sing along: the karaoke's guide mixes (dev-only).

    full     the song as the machine sings it: its singer and its band, mixed and mastered
    melody   the tune alone, on one soft instrument (the band's whistle, played plainly), over a
             quiet pulse on the beats, the downbeats a little higher: every sung note as the
             singer sings it, and where no one sings, the tune as the band plays it there, in
             the singer's register. The default for singers: they keep time and hear the tune
             without copying the machine's phrasing, which is what their takes are for.
    voice    the machine's singer alone, as it sounds in the full guide

Every mix comes from one score. tools/phrasing.py's write_guide renders the full
guide and writes the score it follows, with its tempo, seed and beats
(renders/guide/<song>.guide.score.json); the other mixes are rendered from that
file alone, so a take sung to any of them lines up with the same timeline and is
measured against the same guide, by the same digest. Each mix is kept beside the
full one (renders/guide/<song>.guide.<mix>.wav) with a note of the score digest
and recipe it was made from, and made again when either changes.

    uv run python tools/guides.py songs/h-now-its-by-you.json melody     # write it and say where
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import threading
import warnings
from dataclasses import fields, replace
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import takes as K  # noqa: E402  (tools/takes.py)

from songbird.phrasing import Gesture  # noqa: E402
from songbird.score import Note, Score  # noqa: E402

ROOT = Path(__file__).parent.parent
GUIDES = ROOT / "renders" / "guide"
MIXES = ("melody", "full", "voice")
DEFAULT = "melody"

# The melody's instrument: the band's whistle (songbird.synth.pipe) played for a singer to follow.
# Measured on H's sung notes (harvest f0 against the score): within 5 cents at the 95th percentile,
# every note held (96% of each within 10 dB of its peak), 17 dB between repeated notes, breath hiss
# 39 dB under the tone. The lute was as clear but let long notes die (59% held); a pure tone
# was clean but isn't one of the song's instruments.
WHISTLE = dict(brightness=0.25, wear=0.0, breathiness=0.3, vibrato=0.3)
STATED = 0.8  # the tune the band states where no one sings, a little softer than the sung line
MELODIC = ("whistle", "fiddle", "lute", "melody")  # parts that can state the tune ("melody": scores from before the band)
REST = 2.0  # seconds without singing before the band's statement of the tune is heard in the melody guide
# The pulse: a small woodblock, higher on the downbeat. Nothing under 600 Hz, so it can't cover the
# tune's fundamentals; 27 ms long; its level against the tune's is set in render_melody.
TOCK = 1150.0  # Hz, the block's lowest mode; the downbeat's is a major third higher
PULSE_DB = (-15.0, -12.0)  # a beat's and a downbeat's level (first 20 ms) against the tune's typical level
PULSE_PAN = 0.2  # a little to the right of the tune, so the ear can tell them apart
ROOM = dict(rt60=0.7, wet=0.1)  # a small room around the whistle, so it isn't clinical; the pulse stays dry

_lock = threading.Lock()


def full_paths(stem: str) -> tuple[Path, Path]:
    """The full guide's WAV and the score every mix follows."""
    return GUIDES / f"{stem}.guide.wav", GUIDES / f"{stem}.guide.score.json"


def mix_path(stem: str, mix: str) -> Path:
    if mix not in MIXES:
        raise ValueError(f"no guide mix {mix!r}; there are {', '.join(MIXES)}")
    return full_paths(stem)[0] if mix == "full" else GUIDES / f"{stem}.guide.{mix}.wav"


def recipe() -> str:
    """What a derived mix depends on beyond its score: this file and the synthesis it calls."""
    h = hashlib.sha256(Path(__file__).read_bytes())
    for f in sorted((ROOT / "songbird" / "synth").glob("*.py")):
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


def load_score(path: Path) -> tuple[Score, dict]:
    """A guide score as written by write_guide: the Score, and the file's data (tempo, seed, beats...)."""
    data = json.loads(Path(path).read_text())
    known = {f.name for f in fields(Note)}
    notes = []
    for n in data["notes"]:
        n = {k: v for k, v in n.items() if k in known}
        if n.get("gesture"):
            n["gesture"] = Gesture(**n["gesture"])
        notes.append(Note(**n))
    score = Score(tuple(notes), float(data["duration"]), tuple(tuple(s) for s in data["sections"]),
                  data.get("lexicon") or {}, data.get("band") or {})
    return score, data


def fresh(genome_path: Path) -> bool:
    """Whether the full guide on disk is current: written since the genome last changed, by a
    write_guide that keeps the beats (older ones don't)."""
    wav, score = full_paths(genome_path.stem)
    if not (wav.exists() and score.exists()) or wav.stat().st_mtime < Path(genome_path).stat().st_mtime:
        return False
    return '"beats"' in score.read_text()


def ensure(genome_path: Path, genome, mix: str = "full", rebuild: bool = False) -> tuple[Path, Path]:
    """The guide mix to sing to and the score it follows, rendering whatever is missing or stale.
    rebuild: render the full guide again from the current code (the other mixes follow)."""
    import phrasing as T  # tools/phrasing.py, imported late: it brings the aligner and whisper with it

    genome_path = Path(genome_path)
    out = mix_path(genome_path.stem, mix)
    with _lock:
        if rebuild or not fresh(genome_path):
            with contextlib.redirect_stdout(io.StringIO()):
                T.write_guide(genome_path, genome, 0)
        wav, score = full_paths(genome_path.stem)
        if mix == "full":
            return wav, score
        stamp = {"score": K.digest(score), "recipe": recipe()}
        note = out.with_suffix(".json")
        if not out.exists() or not note.exists() or json.loads(note.read_text()) != stamp:
            write_mix(score, mix, out)
            note.write_text(json.dumps(stamp) + "\n")
        return out, score


def write_mix(score_path: Path, mix: str, out: Path) -> Path:
    """Render one mix from a guide score to a 16-bit WAV at out (whole or not at all)."""
    import soundfile as sf

    from songbird import synth
    from songbird.synth import master

    score, data = load_score(score_path)
    seed = int(data.get("seed", 0))
    if mix == "melody":
        if "beats" not in data:
            raise ValueError(f"{score_path} keeps no beats: write the guide again (tools/phrasing.py --guide)")
        x = render_melody(score, [(float(t), bool(b)) for t, b in data["beats"]], synth.SR, seed)
    elif mix == "voice":
        x = render_voice(score, synth.SR, seed)
    else:
        raise ValueError(f"the {mix} guide is written by tools/phrasing.py --guide")
    pcm = master.to_pcm16(master.master(x, synth.SR), seed=seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(f"{out.stem}.{os.getpid()}.part.wav")
    sf.write(str(part), pcm, synth.SR, subtype="PCM_16")
    os.replace(part, out)
    return out


# --- the melody ------------------------------------------------------------------------------


def melody_line(score: Score) -> list[Note]:
    """The tune as one line for the whistle: every sung note, tongued, as the
    singer sings it; and in each stretch of REST seconds or more where no one
    sings, the notes of the band's part that states the tune there (the one
    with most notes), moved by octaves into the singer's register and a little
    softer. Each note ends by the time the next begins."""
    sung = sorted(score.part("voice"), key=lambda n: n.start)
    line = [replace(n, part="guide", art="") for n in sung]
    if sung:
        centre = float(np.median([n.pitch for n in sung]))
        loud = float(np.median([n.vel for n in sung]))
        bounds = [0.0] + [t for n in sung for t in (n.start, n.start + n.dur)] + [score.duration]
        for a, b in zip(bounds[0::2], bounds[1::2]):  # before the first note, between notes, after the last
            if b - a < REST:
                continue
            # a statement starts after the last sung note ends (give or take the players' timing) and
            # leaves the next line's start to the singer
            found = {p: [n for n in score.part(p) if a - 0.05 <= n.start < b - 0.1] for p in MELODIC}
            part = max(found, key=lambda p: len(found[p]))
            notes = found[part]
            if not notes:
                continue
            shift = 12.0 * round((centre - float(np.median([n.pitch for n in notes]))) / 12.0)
            # the players' own dynamics, at STATED of the singer's level
            scale = STATED * loud / max(float(np.median([n.vel for n in notes])), 1e-3)
            line += [replace(n, part="guide", pitch=n.pitch + shift, vel=float(min(1.0, n.vel * scale)),
                             dur=min(n.dur, b - n.start)) for n in notes]
    line.sort(key=lambda n: (n.start, n.pitch))
    return [replace(n, dur=max(min(n.dur, m.start - n.start), 0.01)) for n, m in zip(line, line[1:])] + line[-1:]


def tock(downbeat: bool, sr: int) -> np.ndarray:
    """One stroke on a small woodblock: three damped modes and the knock of the stick, 90 ms, peak 1."""
    from scipy.signal import butter, sosfilt

    n = int(0.09 * sr)
    t = np.arange(n) / sr
    base = TOCK * (1.26 if downbeat else 1.0)
    y = np.zeros(n)
    for ratio, t60, amp in ((1.0, 0.06, 1.0), (2.21, 0.03, 0.35), (3.73, 0.015, 0.12)):
        y += amp * np.sin(2 * np.pi * base * ratio * t) * np.exp(-6.9 * t / t60)
    knock = sosfilt(butter(2, [800.0, min(5000.0, 0.45 * sr)], btype="bandpass", fs=sr, output="sos"),
                    np.random.default_rng(11).standard_normal(n))
    y += 0.3 * knock * np.exp(-t / 0.0015)
    rise = int(0.001 * sr)
    y[:rise] *= np.linspace(0.0, 1.0, rise)
    return y / np.max(np.abs(y))


def pulse(beats: list[tuple[float, bool]], sr: int, length: int) -> np.ndarray:
    """A tock on every beat (seconds, whether it begins a bar), each peaking at 1 (downbeats) or
    10^(-3/20) of that (the others): mono, `length` samples."""
    out = np.zeros(length)
    strokes = {True: tock(True, sr), False: tock(False, sr) * 10.0 ** ((PULSE_DB[0] - PULSE_DB[1]) / 20.0)}
    for t, downbeat in beats:
        i = int(round(t * sr))
        if 0 <= i < length:
            y = strokes[downbeat][: length - i]
            out[i : i + len(y)] += y
    return out


def typical_level(x: np.ndarray, sr: int, notes: list[Note]) -> float:
    """The tune's typical level: the median RMS of 20 ms windows inside its notes."""
    w = int(0.02 * sr)
    levels = []
    for n in notes:
        a, b = int(n.start * sr), int((n.start + n.dur) * sr)
        for i in range(a, b - w, w):
            levels.append(np.sqrt(np.mean(x[i : i + w] ** 2)))
    return float(np.median(levels)) if levels else 0.0


def render_melody(score: Score, beats: list[tuple[float, bool]], sr: int, seed: int = 0) -> np.ndarray:
    """The melody guide, unmastered stereo: the whistle in the middle of a small room, the pulse dry
    beside it, the downbeats PULSE_DB[1] dB against the tune's typical level."""
    from songbird.synth import pipe, room
    from songbird.synth.instruments import place

    length = int(np.ceil(score.duration * sr))
    line = melody_line(score)
    tune = pipe.blow(line, sr, length, np.random.default_rng([seed, 23]), **WHISTLE)
    level = typical_level(tune, sr, [n for n in line if n.art != "cut"])
    click = pulse(beats, sr, length)
    if level > 0:
        click *= level * 10.0 ** (PULSE_DB[1] / 20.0) / np.sqrt(np.mean(tock(True, sr)[: int(0.02 * sr)] ** 2))
    dry = place(tune, 0.0, 0.0) + place(click, PULSE_PAN, 0.0)
    ir = room.impulse_response(sr, rt60=ROOM["rt60"], seed=room.seed_of(ROOM["rt60"]))
    return room.apply(dry, ir, send=place(tune, 0.0, 0.0), wet=ROOM["wet"])


def render_voice(score: Score, sr: int, seed: int = 0) -> np.ndarray:
    """The machine's singer alone, through the voice's own strip and room, unmastered."""
    from songbird import synth
    from songbird.synth.voice import VoiceParams, sing

    length = int(np.ceil(score.duration * sr))
    y = sing(list(score.part("voice")), sr, VoiceParams(), seed, score.lexicon)[:length]
    stem = synth.pan(np.pad(y, (0, length - len(y))), 0.0) * synth.VOICE_GAIN
    return synth.mix({"voice": stem}, sr, seed)


def main() -> None:
    from songbird import genome as G

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    ap.add_argument("mix", nargs="?", default=DEFAULT, choices=MIXES)
    ap.add_argument("--rebuild", action="store_true", help="render the full guide again from the current code first")
    args = ap.parse_args()
    wav, score = ensure(Path(args.genome), G.load(args.genome), args.mix, args.rebuild)
    print(f"{wav}  (score {K.digest(score)})")


if __name__ == "__main__":
    main()
