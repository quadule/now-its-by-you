"""What a visitor sings to: the version on the studio's page (or the released one), as a guide (docs/WEB-SINGING.md).

A guide is made from the version as it is when they open Sing, not ahead of time, so its words, tune, key and tempo
are always the ones the Page shows:

    score_for(genome, params, lyrics, speed, key)   the guide's score: the version laid on its grid (realize(),
                                                    without a singer's phrasing, so each note is where the tune
                                                    puts it), at a practice speed and in a key moved for a voice;
                                                    only the voice and the parts that state the tune are kept
    released(speed, key)                            the same for the released version (released.json: laid with
                                                    the release's own program, tools/released_guide.py)
    words(data, title, digest)                      the karaoke's words for it: lines, syllables, beats, and each
                                                    sung section's window for singing it alone
    melody(data, a, b)                              its melody guide from a to b seconds: the tune on a whistle
                                                    over a pulse (tools/guides.py's, the karaoke's default mix),
                                                    mono, 16-bit, at half the program's rate

score_for and words need only the program (the studio's own process, or its worker in a visitor's browser); melody
needs tools/guides.py and the synthesizer's kernels (the measuring process, or a singing worker in the browser).
A whole song's melody is made a stretch at a time and added up, so its memory is a stretch's (about 250 MB
natively), not the whole song's (2.2 GB).
"""

from __future__ import annotations

import io
import json
import sys
import wave
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RELEASED = HERE / "released.json"
SPEEDS = (100, 90, 80)  # percent of the version's tempo: as written, and two practice speeds (tools/guides.py TEMPOS)
SPEED = 90  # where a singer starts (tools/karaoke.py SLOWER)
KEYS = (-4, -2, 0, 2, 4)  # semitones from the version's key, for a voice it sits too high or low for (guides.KEYS)
MELODIC = ("whistle", "fiddle", "lute", "melody")  # parts that can state the tune (tools/guides.py MELODIC)
TAIL = 4.0  # seconds a stretch of melody rings on past its last note's start (a held note, the room)
STRETCH = 40.0  # seconds: a whole song's melody is made in stretches no longer, cut in its rests (worker.pieces)
LOUDNESS = -18.0  # LUFS: the guide's level (under a voice; a little quieter than a mastered song)
RING = 1.0  # seconds a section's melody runs past its window's end, for its last note and the room (webstudio/sing.js)


def _tools() -> None:
    tools = str(ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)


def digest(data: dict) -> str:
    """A guide's name: the first 12 hex digits of the SHA-256 of its file (tools/takes.py digest, of text())."""
    import hashlib

    return hashlib.sha256(text(data).encode()).hexdigest()[:12]


def text(data: dict) -> str:
    """A guide's file, as it is kept and named: the same score always gives the same bytes."""
    return json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"


def score_for(genome, params, lyrics=None, speed: int = 100, key: int = 0, which: str = "page") -> dict:
    """A version's guide score, as a guide's file keeps it (tools/guides.py realized()'s shape): the notes on the
    grid (no phrasing, no lay: where the tune puts them), the beats, sections and words, the tempo, and how far the
    key was moved from the song's own ("transpose", which tools/phrasing.py reads to know the tune)."""
    from songbird.realize import choose_params, realize, timeline

    if speed not in SPEEDS or key not in KEYS:
        raise ValueError(f"a guide is at {', '.join(map(str, SPEEDS))}% and {', '.join(map(str, KEYS))} semitones")
    score = realize(genome, replace(params, tonic=params.tonic + key), lyrics=lyrics)
    beats = [[t, int(bar)] for t, bar in timeline(genome, params).beats()]
    data = {**score.to_dict(), "tempo": params.tempo, "seed": params.seed,
            "transpose": params.tonic + key - choose_params(genome).tonic, "beats": beats}
    return slowed(slim(data), speed, key, which)


def slim(data: dict) -> dict:
    """Only what a guide needs: the voice (what is sung, and measured against) and the parts that state the tune
    where nobody sings (the whistle plays them); the band's other notes go."""
    keep = [n for n in data["notes"] if n["part"] == "voice" or n["part"] in MELODIC]
    return {k: v for k, v in data.items() if k not in ("notes", "band", "sound")} | {"notes": keep}


def slowed(data: dict, speed: int, key: int, which: str) -> dict:
    """The guide at speed percent: every time stretched by 100/speed (the grid, the beats, the sections, a
    melisma's turns), the tempo with it. The tune and its words don't change."""
    f = 100.0 / speed
    notes = []
    for n in data["notes"]:
        n = {**n, "start": n["start"] * f, "dur": n["dur"] * f}
        if n.get("melisma"):
            n["melisma"] = [[t * f, step] for t, step in n["melisma"]]
        notes.append(n)
    return {**data, "notes": notes, "duration": data["duration"] * f, "tempo": data["tempo"] * speed / 100.0,
            "sections": [[name, a * f, b * f] for name, a, b in data["sections"]],
            "beats": [[t * f, bar] for t, bar in data["beats"]],
            "guide": {"which": which, "speed": speed, "key": key}}


def released(speed: int = 100, key: int = 0) -> dict:
    """The released version's guide (released.json, the release laid again with its own program)."""
    if speed not in SPEEDS or key not in KEYS:
        raise ValueError(f"a guide is at {', '.join(map(str, SPEEDS))}% and {', '.join(map(str, KEYS))} semitones")
    data = json.loads(RELEASED.read_text())["score"]
    if key:
        data = {**data, "transpose": data["transpose"] + key,
                "notes": [{**n, "pitch": n["pitch"] + key} for n in data["notes"]]}
    return slowed(data, speed, key, "released")


def has_released() -> bool:
    return RELEASED.is_file()


def words(data: dict, title: str, name: str) -> dict:
    """What the page shows while a visitor sings (tools/karaoke.py's words), and the guide's name."""
    _tools()
    import karaoke_words

    return {**karaoke_words.lyrics(data, title, data["tempo"]), "guide": name, **data.get("guide", {})}


def stretches_offered(data: dict) -> list[tuple[float, float]]:
    """The stretches of a guide's melody a page may ask for (webstudio/sing.js asks for no others): the whole song,
    and each sung section's window, RING seconds longer."""
    _tools()
    import karaoke_words

    duration = float(data["duration"])
    out = [(0.0, duration)]
    for s in karaoke_words.sections(data):
        if s.get("window"):
            a, b = s["window"]
            out.append((float(a), min(duration, float(b) + RING)))
    return out


# ------------------------------------------------------------ the melody guide (tools/guides.py's, a stretch at a time


def _score(data: dict):
    from dataclasses import fields

    from songbird.phrasing import Gesture
    from songbird.score import Note, Score

    known = {f.name for f in fields(Note)}
    notes = []
    for n in data["notes"]:
        n = {k: v for k, v in n.items() if k in known}
        if n.get("gesture"):
            n["gesture"] = Gesture(**n["gesture"])
        for k in ("ornament", "melisma"):
            if k in n:
                n[k] = tuple(tuple(x) for x in n[k])
        notes.append(Note(**n))
    return Score(tuple(notes), float(data["duration"]), tuple(tuple(s) for s in data["sections"]),
                 data.get("lexicon") or {}, {})


def stretches(data: dict, a: float, b: float) -> list[tuple[float, float]]:
    """Where a melody from a to b is cut to be made a stretch at a time: in its rests, none longer than STRETCH."""
    from types import SimpleNamespace

    from .worker import pieces

    sung = [SimpleNamespace(start=n["start"], dur=n["dur"]) for n in data["notes"] if n["part"] == "voice"]
    if b - a <= STRETCH + 5.0:
        return [(a, b)]
    out = []
    for lo, hi in pieces(sung, a, b):
        while hi - lo > STRETCH + 5.0:  # a long stretch with no rest: cut anyway (a note across it rings on)
            out.append((lo, lo + STRETCH))
            lo += STRETCH
        out.append((lo, hi))
    return out


def melody(data: dict, a: float, b: float) -> tuple[bytes, int]:
    """The melody guide from a to b seconds of the guide, as a WAV (mono, 16-bit, half the program's rate: a
    whistle and a pulse lose nothing a singer needs), and its rate. Its first sample is guide time a."""
    import numpy as np
    from scipy.signal import resample_poly

    from songbird import synth
    from songbird.synth import master, pipe, room
    from songbird.synth.instruments import place

    _tools()
    import guides as M

    sr = synth.SR
    score = _score(data)
    line = M.melody_line(score)
    sung_all = [n for n in line if n.part == "sung"]
    beats = [(float(t), bool(bar)) for t, bar in data["beats"]]
    strokes = M.strokes(beats, sorted(score.part("voice"), key=lambda n: n.start))
    sounds = {"count": M.tock(True, sr), "downbeat": M.tock(True, sr), "beat": M.tock(False, sr)}
    ir = room.impulse_response(sr, rt60=M.ROOM["rt60"], seed=room.seed_of(M.ROOM["rt60"]))
    seed = int(data.get("seed", 0))
    half = sr // 2
    out = np.zeros(int(np.ceil((b - a) * half)) + 1)
    # the pulse sits against the sung line's level, as in tools/guides.py: the line's first few notes, heard alone
    probe = [replace(n, start=n.start - sung_all[0].start) for n in sung_all[:12]] if sung_all else []
    probe_len = int(np.ceil(((probe[-1].start + probe[-1].dur) if probe else 0.0) * sr)) + sr
    level = M.typical_level(pipe.blow(probe, sr, probe_len, np.random.default_rng([seed, 23]), **M.WHISTLE), sr, probe) \
        if probe else 0.0
    for k, (lo, hi) in enumerate(stretches(data, a, b)):
        length = int(np.ceil((hi - lo + TAIL) * sr))
        mine = [replace(n, start=n.start - lo) for n in line if lo <= n.start < hi]
        sung = [n for n in mine if n.part == "sung"]
        stated = [n for n in mine if n.part == "stated"]
        rng = [seed, 23, k]
        tune = pipe.blow(sung, sr, length, np.random.default_rng(rng), **M.WHISTLE)
        tune += pipe.blow([replace(n, pitch=n.pitch + 12) for n in sung], sr, length, np.random.default_rng(rng),
                          **M.WHISTLE) * 10.0 ** (M.OCTAVE_DB / 20.0)
        if stated:
            tune += pipe.blow(stated, sr, length, np.random.default_rng([seed, 29, k]), **M.WHISTLE)
        click = np.zeros(length)
        for t, kind, db in strokes:
            if lo <= t < hi:
                i = round((t - lo) * sr)
                y = sounds[kind][: length - i] * 10.0 ** (db / 20.0)
                click[i : i + len(y)] += y
        if level > 0:
            click *= level * 10.0 ** (M.PULSE_DB["downbeat"] / 20.0) / np.sqrt(np.mean(sounds["downbeat"][: int(0.02 * sr)] ** 2))
        dry = place(tune, 0.0, 0.0) + place(click, M.PULSE_PAN, 0.0)
        wet = room.apply(dry, ir, send=place(tune, 0.0, 0.0), wet=M.ROOM["wet"])
        del tune, click, dry
        mono = resample_poly(wet.mean(axis=1), 1, 2)
        del wet
        i0 = round((lo - a) * half)
        n = min(len(mono), len(out) - i0)
        if n > 0:
            out[i0 : i0 + n] += mono[:n]
    loud = master.loudness(np.column_stack([out, out]), half) if np.any(out) else float("nan")
    if np.isfinite(loud):
        out *= 10.0 ** ((LOUDNESS - loud) / 20.0)
    peak = float(np.max(np.abs(out))) if len(out) else 0.0
    if peak > 0.95:
        out *= 0.95 / peak
    pcm = master.to_pcm16(out, seed=seed)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(half)
        w.writeframes(np.ascontiguousarray(pcm, dtype="<i2").tobytes())
    return buffer.getvalue(), half
