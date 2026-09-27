"""A singer's own version of the song, and their voice alone (dev-only).

    uv run python tools/versions.py songs/h-now-its-by-you.json --singer <folder> [--spec a.k0.t100] --out DIR

For one singer and one spec (the set, key and speed they sang to, as tools/guides.py
names them), two files:

    version.mp3   the band as that spec's guide plays it, with their takes in the sections they
                  sang, level-matched to the machine's lead in the same sections (one gain a
                  take, so their own louder and softer sections stay) and put through the
                  machine voice's own strip and room, and the machine's lead where they didn't
                  sing, crossfaded at the edges; mastered (songbird.synth.master), stereo MP3
                  at 192k
    vocals.wav    their takes alone, placed on the spec's timeline, dry: 16-bit mono at the
                  takes' own rate (48 kHz if they differ)

A take counts for every sung section whose notes all start inside it: a take of
one section for its own, a take of the whole song for every one. Where two
takes sing the same section, the latest one marked to use (Take.use) wins, or
the latest if none is. A section's take is heard from halfway through the gap
before it to halfway through the gap after (the band's turns between sections),
so the singer and the machine hand over where neither is singing.

Only takes sung to this spec count: a take at another speed or in another key
follows another timeline. The band and the lead come from the spec's guide
stems (tools/guides.py stems(), each unmastered at songbird.synth.SR with the
full mix's gain staging), the strip and room from guides.voice_strip. The files
hold a person's voice: tools/invite.py gives them to that person alone, and
deletes them with their takes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable, NamedTuple

import numpy as np
import soundfile as sf

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import takes as K  # noqa: E402  (tools/takes.py)

GAP = 1.0  # seconds without singing that part two runs of one section's name (sections touch where their names change)
XFADE = 0.25  # seconds the machine's lead takes to hand over to the singer, and back
FADE = 0.01  # seconds of fade where a take is cut
GAIN_LIMIT = 30.0  # dB a take is raised or lowered at most to meet the machine's level
FRAME = 0.05  # seconds per frame when measuring a level
RATE = 48000  # the vocals' rate when the takes' own rates differ
MP3 = ["-c:a", "libmp3lame", "-b:a", "192k", "-ac", "2"]


class Run(NamedTuple):
    """One sung section of a guide: its voice notes' start and end, and the notes themselves."""

    start: float
    end: float
    notes: list  # dicts, as the score keeps them


class Made(NamedTuple):
    version: Path  # the MP3
    vocals: Path  # the dry WAV
    sections: list  # for each sung section: {"start", "end", "take" (its path, or None where the machine sings)}


def runs(score: dict) -> list[Run]:
    """The guide's sung sections, in order: its voice notes, split where the section's name changes
    or GAP seconds pass without singing."""
    notes = sorted((n for n in score["notes"] if n["part"] == "voice"), key=lambda n: n["start"])
    out: list[list[dict]] = []
    for n in notes:
        last = out[-1][-1] if out else None
        if last is None or n["section"] != last["section"] or n["start"] - (last["start"] + last["dur"]) > GAP:
            out.append([])
        out[-1].append(n)
    return [Run(r[0]["start"], max(n["start"] + n["dur"] for n in r), r) for r in out]


def seconds(take: K.Take) -> float:
    return sf.info(str(take.path)).duration


def covers(take: K.Take, run: Run) -> bool:
    """Whether a take sang all of a section: every one of its notes starts inside the take's
    stretch of the guide (from_s to to_s, or where its sound ends if that's sooner)."""
    end = take.from_s + seconds(take)
    end = min(end, take.to_s) if take.to_s is not None else end
    return take.from_s <= run.start + 1e-6 and max(n["start"] for n in run.notes) < end


def choose(takes: list[K.Take], sung: list[Run]) -> list[K.Take | None]:
    """The take heard in each sung section: of those that sang all of it, the latest marked to use, or
    else the latest; None where no take did."""
    out = []
    for run in sung:
        found = [t for t in takes if covers(t, run)]
        kept = [t for t in found if t.use] or found
        out.append(max(kept, key=lambda t: (t.recorded_at or datetime.min, t.path.name)) if kept else None)
    return out


def cuts(sung: list[Run], length: float) -> list[tuple[float, float]]:
    """Where each sung section's take is heard: from halfway through the gap before it to halfway
    through the gap after (from the start, and to the end, for the first and last)."""
    mids = [(a.end + b.start) / 2 for a, b in zip(sung, sung[1:])]
    return list(zip([0.0, *mids], [*mids, length]))


def audio(take: K.Take, sr: int) -> np.ndarray:
    """A take as mono at sr."""
    from scipy.signal import resample_poly

    y, rate = sf.read(str(take.path), always_2d=True)
    y = y.mean(axis=1)
    return resample_poly(y, sr, rate) if rate != sr else y


def stretches(chosen: list[K.Take | None], spans: list[tuple[float, float]]) -> list[tuple[K.Take, float, float]]:
    """Each chosen take with the stretch of the timeline it's heard in: its sections' spans, joined where
    one take sings sections in a row (a take of the whole song is heard from start to end)."""
    out: list[tuple[K.Take, float, float]] = []
    for take, (a, b) in zip(chosen, spans):
        if take is None:
            continue
        if out and out[-1][0] is take and abs(out[-1][2] - a) < 1e-9:
            out[-1] = (take, out[-1][1], b)
        else:
            out.append((take, a, b))
    return out


def placed(chosen: list[K.Take | None], spans: list[tuple[float, float]], sr: int, length: int,
           gains: dict[Path, float] | None = None) -> np.ndarray:
    """The chosen takes laid on the guide's timeline (mono, sr, length samples), each in its sections'
    stretch and only where it has sound (its first sample at its from_s), faded where it's cut, and
    raised or lowered by gains[its path] dB."""
    out = np.zeros(length)
    loaded: dict[Path, np.ndarray] = {}
    fade = max(int(FADE * sr), 1)
    for take, a, b in stretches(chosen, spans):
        y = loaded.setdefault(take.path, audio(take, sr))
        at = int(round(take.from_s * sr))
        lo, hi = max(int(round(a * sr)), at, 0), min(int(round(b * sr)), at + len(y), length)
        if hi <= lo:
            continue
        piece = y[lo - at : hi - at] * 10.0 ** ((gains or {}).get(take.path, 0.0) / 20.0)
        ramp = np.minimum(np.minimum(np.arange(len(piece)), np.arange(len(piece))[::-1]) / fade, 1.0)
        out[lo:hi] += piece * ramp
    return out


def level(x: np.ndarray, sr: int, notes: list[dict]) -> float | None:
    """How loud a track is while notes sound: the median over FRAME-long frames inside them of each
    frame's RMS, in dB. None if nothing sounds there."""
    mono = x.mean(axis=1) if x.ndim == 2 else x
    n = int(FRAME * sr)
    frames = []
    for note in notes:
        a, b = int(note["start"] * sr), min(int((note["start"] + note["dur"]) * sr), len(mono))
        frames += [np.sqrt(np.mean(mono[i : i + n] ** 2)) for i in range(a, b - n + 1, n)]
    frames = [f for f in frames if f > 1e-9]
    return float(20 * np.log10(np.median(frames))) if frames else None


def smooth(mask: np.ndarray, n: int) -> np.ndarray:
    """A 0/1 mask with each step turned into a straight ramp n samples long, centred on it."""
    c = np.concatenate([[0.0], np.cumsum(mask)])
    i = np.arange(len(mask))
    lo, hi = np.clip(i - n // 2, 0, len(mask)), np.clip(i + n - n // 2, 0, len(mask))
    return (c[hi] - c[lo]) / np.maximum(hi - lo, 1)


def stereo(x: np.ndarray) -> np.ndarray:
    from songbird import synth

    return x if x.ndim == 2 else synth.pan(x, 0.0)


def lead_track(chosen: list[K.Take | None], sung: list[Run], spans, lead: np.ndarray, sr: int, seed: int,
               strip: Callable) -> tuple[np.ndarray, dict[Path, float]]:
    """The lead as the version has it (stereo, unmastered): the singer's takes through the machine voice's
    strip and room where they sang, and the machine's lead elsewhere, handing over in XFADE. Each take is
    raised or lowered until it's as loud in the sections it sings as the machine's lead is there, one gain
    for the whole take, so their own way of singing one section louder than another stays. The strip may
    compress, so the level is measured through it, and set again. Returns the lead and each take's gain
    in dB, by its path."""
    length = len(lead)
    notes: dict[Path, list] = defaultdict(list)
    for take, run in zip(chosen, sung):
        if take is not None:
            notes[take.path] += run.notes
    gains = dict.fromkeys(notes, 0.0)
    for _ in range(3):
        wet = stereo(np.asarray(strip(placed(chosen, spans, sr, length, gains), sr, seed)))[:length]
        wet = np.pad(wet, ((0, length - len(wet)), (0, 0)))
        off = {}
        for path, those in notes.items():
            want, got = level(lead, sr, those), level(wet, sr, those)
            if want is not None and got is not None:
                off[path] = want - got
        if all(abs(v) < 0.5 for v in off.values()):
            break
        for path, v in off.items():
            gains[path] = float(np.clip(gains[path] + v, -GAIN_LIMIT, GAIN_LIMIT))
    mask = np.zeros(length)
    for take, (a, b) in zip(chosen, spans):
        if take is not None:
            mask[int(round(a * sr)) : int(round(b * sr))] = 1.0
    mask = smooth(mask, int(XFADE * sr))
    return wet + lead * (1.0 - mask)[:, None], gains


def mp3(pcm: np.ndarray, sr: int, out: Path, title: str = "") -> None:
    """16-bit stereo PCM to an MP3 at 192k (ffmpeg), whole or not at all."""
    part = out.with_name(f"{out.stem}.{os.getpid()}.part.wav")
    sf.write(str(part), pcm, sr, subtype="PCM_16")
    tmp = out.with_name(f"{out.stem}.{os.getpid()}.part.mp3")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(part), *MP3,
                        *(["-metadata", f"title={title}"] if title else []), str(tmp)], check=True)
        os.replace(tmp, out)
    finally:
        part.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)


def make(genome_path: Path, takes: list[K.Take], spec: str, out_dir: Path, stems: tuple | None = None,
         strip: Callable | None = None, title: str = "") -> Made:
    """One singer's version.mp3 and vocals.wav for one spec, in out_dir. takes: their takes (those
    sung to other specs are left out); stems: the spec's (band WAV, lead WAV, score JSON), by default
    tools/guides.py stems(genome_path, spec); strip: the machine voice's strip and room,
    f(mono, sr, seed) -> stereo, by default guides.voice_strip."""
    from songbird.synth import master

    if stems is None or strip is None:
        import guides as M  # tools/guides.py, which renders the stems on demand

        if not (hasattr(M, "stems") and hasattr(M, "voice_strip")):
            raise RuntimeError("tools/guides.py can't make a spec's stems yet (stems(), voice_strip())")
        stems = stems or M.stems(Path(genome_path), spec)
        strip = strip or M.voice_strip
    band_wav, lead_wav, score_json = (Path(p) for p in stems)
    score = json.loads(score_json.read_text())
    digest = K.digest(score_json)
    mine = [t for t in takes if t.spec == spec or (t.spec is None and t.guide == digest)]
    band, sr = sf.read(str(band_wav), always_2d=True)
    lead, rate = sf.read(str(lead_wav), always_2d=True)
    if rate != sr:
        raise ValueError(f"the band stem is at {sr} Hz and the lead at {rate}")
    length = max(len(band), len(lead))
    band, lead = (np.pad(x, ((0, length - len(x)), (0, 0))) for x in (band, lead))
    lead = lead if lead.shape[1] == 2 else np.repeat(lead, 2, axis=1)
    band = band if band.shape[1] == 2 else np.repeat(band, 2, axis=1)
    sung = runs(score)
    chosen = choose(mine, sung)
    if not any(chosen):
        raise ValueError(f"none of these takes sings a whole section of {spec}")
    spans = cuts(sung, length / sr)
    seed = int(score.get("seed", 0))
    voice, _ = lead_track(chosen, sung, spans, lead, sr, seed, strip)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    version = out_dir / "version.mp3"
    mp3(master.to_pcm16(master.master(band + voice, sr), seed=seed), sr, version, title)

    rates = {sf.info(str(t.path)).samplerate for t in chosen if t is not None}
    vr = rates.pop() if len(rates) == 1 else RATE
    dry = placed(chosen, spans, vr, int(round(length / sr * vr)))
    vocals = out_dir / "vocals.wav"
    part = vocals.with_name(f"vocals.{os.getpid()}.part.wav")
    sf.write(str(part), np.clip(dry, -1.0, 1.0), vr, subtype="PCM_16")
    os.replace(part, vocals)
    sections = [{"start": round(r.start, 3), "end": round(r.end, 3), "take": t.path.name if t else None}
                for r, t in zip(sung, chosen)]
    return Made(version, vocals, sections)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    ap.add_argument("--singer", required=True, help="their folder in recordings/")
    ap.add_argument("--spec", help="only this spec (default: every spec they sang to)")
    ap.add_argument("--out", required=True, help="a folder: each spec's pair goes in <out>/<spec>/")
    args = ap.parse_args()
    from songbird import genome as G

    genome_path = Path(args.genome)
    kept = K.takes(genome_path.stem, K.slug(args.singer))
    by_spec = defaultdict(list)
    for t in kept:
        if t.spec:
            by_spec[t.spec].append(t)
    if args.spec:
        by_spec = {args.spec: by_spec.get(args.spec, [])}
    if not any(by_spec.values()):
        where = f"recordings/{K.slug(args.singer)}/"
        raise SystemExit(f"no takes by {args.singer} sung to {args.spec or 'any spec'} in {where}"
                         " (a take sung to the song's own guide has no spec, and no stems to go with it)")
    title = f"{G.load(genome_path).title} (your version)"
    for spec, those in by_spec.items():
        made = make(genome_path, those, spec, Path(args.out) / spec, title=title)
        sang = sum(s["take"] is not None for s in made.sections)
        print(f"{made.version}  {made.vocals}  ({sang} of {len(made.sections)} sections theirs)")


if __name__ == "__main__":
    main()
