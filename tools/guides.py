"""What a singer hears while they sing along: the karaoke's guide mixes (dev-only).

    full     the song as the machine sings it: its singer and its band, mixed and mastered
    melody   the tune alone, on the band's whistle played plainly, over a quiet pulse: every sung
             note as the singer sings it, and where no one sings, the tune as the band plays it
             there, at the band's own octave and softer, so the singer hears their entry drop into
             their register; the pulse counts each entry in and steps back under the singing. The
             default for singers: they keep time and hear the tune without copying the machine's
             phrasing, which is what their takes are for.
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
from typing import NamedTuple

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
# was clean but isn't one of the song's instruments. So low (220-500 Hz) the model is nearly a sine
# (its 2nd and 3rd harmonics 16-20 dB down, whatever the brightness), which a singer's own voice
# covers in the headphones; a second whistle an octave up, 9 dB down, gives it a wooden flute's
# strong second harmonic and carries it over them, the pitch where it's written.
WHISTLE = dict(brightness=0.4, wear=0.0, breathiness=0.3, vibrato=0.3)
OCTAVE_DB = -9.0
STATED = 0.5  # the band's statement of the tune where no one sings, against the singer's level
MELODIC = ("whistle", "fiddle", "lute", "melody")  # parts that can state the tune ("melody": scores from before the band)
REST = 2.0  # seconds without singing before a line is counted in, and the band's statement is heard
# The pulse: a small woodblock. Nothing under 600 Hz, so it can't cover the tune's fundamentals; 27 ms
# long, a little to the right of the tune. Its levels (first 20 ms, against the tune's typical level):
# a beat, a downbeat (a major third higher), and the four beats that count in a line after a rest
# (higher, louder). Under the singing it steps back DUCK_DB: it keeps time without setting it, since
# a click to sing to would press the singer's own timing, which the takes are for, onto the grid.
TOCK = 1150.0  # Hz, the block's lowest mode
PULSE_DB = {"beat": -15.0, "downbeat": -12.0, "count": -9.0}
DUCK_DB = 6.0
COUNT = 4
PULSE_PAN = 0.2
ROOM = dict(rt60=0.7, wet=0.1)  # a small room around the whistle, so it isn't clinical; the pulse stays dry

_lock = threading.Lock()


class Mix(NamedTuple):
    wav: Path  # the mix to sing to
    score: Path  # the score every mix follows
    digest: str  # the score's digest, when the mix was made from it


def full_paths(stem: str) -> tuple[Path, Path]:
    """The full guide's WAV and the score every mix follows."""
    return GUIDES / f"{stem}.guide.wav", GUIDES / f"{stem}.guide.score.json"


def mix_path(stem: str, mix: str) -> Path:
    if mix not in MIXES:
        raise ValueError(f"no guide mix {mix!r}; there are {', '.join(MIXES)}")
    return full_paths(stem)[0] if mix == "full" else GUIDES / f"{stem}.guide.{mix}.wav"


def recipe() -> str:
    """What a derived mix depends on beyond its score: this file, the synthesis it calls, the phonetics."""
    h = hashlib.sha256(Path(__file__).read_bytes())
    for f in [*sorted((ROOT / "songbird" / "synth").glob("*.py")), ROOT / "songbird" / "phonetics.py"]:
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


def ensure(genome_path: Path, genome=None, mix: str = "full", rebuild: bool = False) -> Mix:
    """The guide mix to sing to, the score it follows and that score's digest, rendering whatever
    is missing or stale. genome: what to render if the full guide must be written (default: the
    genome file as it is now). A guide written transposed stays transposed. rebuild: write the
    full guide again from the current code (the other mixes follow)."""
    import phrasing as T  # tools/phrasing.py, imported late: it brings the aligner and whisper with it

    from songbird import genome as G

    genome_path = Path(genome_path)
    out = mix_path(genome_path.stem, mix)
    with _lock:
        wav, score = full_paths(genome_path.stem)
        if rebuild or not fresh(genome_path):
            transpose = json.loads(score.read_text()).get("transpose", 0) if score.exists() else 0
            with contextlib.redirect_stdout(io.StringIO()):
                T.write_guide(genome_path, genome if genome is not None else G.load(genome_path), transpose)
        digest = K.digest(score)
        if mix != "full":
            stamp = {"score": digest, "recipe": recipe()}
            note = out.with_suffix(".json")
            if not out.exists() or not note.exists() or json.loads(note.read_text()) != stamp:
                write_mix(score, mix, out)
                note.write_text(json.dumps(stamp) + "\n")
        return Mix(out, score, digest)


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


def rests(sung: list[Note], duration: float, rest: float = REST) -> list[tuple[float, float]]:
    """Every stretch of `rest` seconds or more without singing: before the first sung note, between
    two, after the last."""
    bounds = [0.0] + [t for n in sung for t in (n.start, n.start + n.dur)] + [duration]
    return [(a, b) for a, b in zip(bounds[0::2], bounds[1::2]) if b - a >= rest]


def entries(sung: list[Note], rest: float = REST) -> list[float]:
    """Where the singer comes in: the first sung note, and every one after a rest of `rest` seconds or more."""
    out = [n.start for k, n in enumerate(sung) if k == 0 or n.start - (sung[k - 1].start + sung[k - 1].dur) >= rest]
    return out


def one_line(notes: list[Note]) -> list[Note]:
    """Notes as one line: each ends by the time the next begins."""
    notes = sorted(notes, key=lambda n: (n.start, n.pitch))
    return [replace(n, dur=max(min(n.dur, m.start - n.start), 0.01)) for n, m in zip(notes, notes[1:])] + notes[-1:]


def melody_line(score: Score) -> list[Note]:
    """The tune for the whistle: every sung note ("sung"), tongued, as the singer sings it; and in
    each stretch of REST seconds or more where no one sings, the notes of the band's part that
    states the tune there (the one with most notes) at the band's own octave, with the players'
    dynamics at STATED of the singer's level ("stated"). Each is one line: a note ends by the time
    the next begins."""
    sung = sorted(score.part("voice"), key=lambda n: n.start)
    stated = []
    if sung:
        loud = float(np.median([n.vel for n in sung]))
        for a, b in rests(sung, score.duration):
            # a statement starts after the last sung note ends (give or take the players' timing) and
            # leaves the next line's start to the singer
            found = {p: [n for n in score.part(p) if a - 0.05 <= n.start < b - 0.1] for p in MELODIC}
            part = max(found, key=lambda p: len(found[p]))
            notes = found[part]
            if not notes:
                continue
            scale = STATED * loud / max(float(np.median([n.vel for n in notes])), 1e-3)
            stated += [replace(n, part="stated", vel=float(min(1.0, n.vel * scale)), dur=min(n.dur, b - n.start))
                       for n in notes]
    line = one_line([replace(n, part="sung", art="") for n in sung]) + (one_line(stated) if stated else [])
    return sorted(line, key=lambda n: (n.start, n.pitch))


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


def strokes(beats: list[tuple[float, bool]], sung: list[Note] = ()) -> list[tuple[float, str, float]]:
    """What the pulse plays on each beat: (seconds, "count", "downbeat" or "beat", dB against a
    downbeat). The COUNT beats before each entry (before it by more than the players' timing) count
    it in; a beat under the singing steps back DUCK_DB."""
    sung = sorted(sung, key=lambda n: n.start)
    counted = set()
    for e in entries(sung):
        counted.update([t for t, _ in beats if t < e - 0.05][-COUNT:])
    spans = [(n.start - 0.05, n.start + n.dur) for n in sung]
    out = []
    for t, bar in beats:
        kind = "count" if t in counted else "downbeat" if bar else "beat"
        db = PULSE_DB[kind] - PULSE_DB["downbeat"]
        if kind != "count" and any(a <= t < b for a, b in spans):
            db -= DUCK_DB
        out.append((t, kind, db))
    return out


def pulse(beats: list[tuple[float, bool]], sr: int, length: int, sung: list[Note] = ()) -> np.ndarray:
    """The pulse as a mono track `length` samples long, a downbeat's stroke peaking at 1 (strokes())."""
    sounds = {"count": tock(True, sr), "downbeat": tock(True, sr), "beat": tock(False, sr)}
    out = np.zeros(length)
    for t, kind, db in strokes(beats, sung):
        i = int(round(t * sr))
        if 0 <= i < length:
            y = sounds[kind][: length - i] * 10.0 ** (db / 20.0)
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
    """The melody guide, unmastered stereo: the whistle (and its octave, on the sung line) in the
    middle of a small room, the pulse dry beside it at PULSE_DB against the sung line's level."""
    from songbird.synth import pipe, room
    from songbird.synth.instruments import place

    length = int(np.ceil(score.duration * sr))
    line = melody_line(score)
    sung = [n for n in line if n.part == "sung"]
    stated = [n for n in line if n.part == "stated"]
    # the octave plays from the same seed, so its tuning and breath move with the line's
    tune = pipe.blow(sung, sr, length, np.random.default_rng([seed, 23]), **WHISTLE)
    tune += pipe.blow([replace(n, pitch=n.pitch + 12) for n in sung], sr, length, np.random.default_rng([seed, 23]),
                      **WHISTLE) * 10.0 ** (OCTAVE_DB / 20.0)
    level = typical_level(tune, sr, sung)
    if stated:
        tune += pipe.blow(stated, sr, length, np.random.default_rng([seed, 29]), **WHISTLE)
    click = pulse(beats, sr, length, sung)
    if level > 0:
        click *= level * 10.0 ** (PULSE_DB["downbeat"] / 20.0) / np.sqrt(np.mean(tock(True, sr)[: int(0.02 * sr)] ** 2))
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
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    ap.add_argument("mix", nargs="?", default=DEFAULT, choices=MIXES)
    ap.add_argument("--rebuild", action="store_true", help="render the full guide again from the current code first")
    args = ap.parse_args()
    mix = ensure(Path(args.genome), None, args.mix, args.rebuild)
    print(f"{mix.wav}  (score {mix.digest})")


if __name__ == "__main__":
    main()
