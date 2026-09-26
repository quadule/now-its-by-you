"""Reference singers: a phrasing we choose, sung by voices that belong to nobody (dev-only).

    uv run python tools/reference.py songs/h-now-its-by-you.json --voice formant say:Daniel --takes 4
    ELEVENLABS_API_KEY=... uv run python tools/reference.py songs/h-now-its-by-you.json --voice elevenlabs:George
    GEMINI_API_KEY=... uv run python tools/reference.py songs/h-now-its-by-you.json --voice gemini:Kore

The extractor (tools/phrasing.py) can only be checked against singing whose
phrasing is known. A reference singer has a way with the song, an intended
phrasing drawn at random but shaped like a person's (a little behind the beat,
scooping into leaps, falling off the ends of lines, vibrato on long notes),
and never sings it quite the same way twice: every sighting of every note
strays from the intent by a performance's worth (NOISE). Each take follows the
same guide a person sings along to, in one of these voices:

    formant                      the machine's own singer, as a lineage stand-in (the easy case)
    say:<voice>                  a macOS voice's reading of the lyric, moved onto the tune
    elevenlabs:<voice>, gemini:<voice>    the same, read by those services (tools/tts.py)
    seedvc:<file.wav>            the formant singer's take, sung again by Seed-VC (singing voice
                                 conversion, installed beside the repo, SEED_VC) in the voice of the
                                 singer in file.wav (1 to 30 s of them alone, e.g. from
                                 tools/music_takes.py): a voice that sounds like a person, with the
                                 pitch and timing sung exactly as planted

and is then heard through a cheap microphone in a small room. The spoken
voices are moved onto the tune the way tools/speech_to_song.py does it: their
consonants and vowels, the tune's pitch and timing, and this take's gestures.
Takes and every note's gesture as sung go to renders/reference/<voice>/.
These voices never join the lineage; tools/phrasing_eval.py compares what the
extractor finds in them with what they sang.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import warnings
from dataclasses import astuple, fields
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import phrasing as T  # noqa: E402
import speech_to_song as S  # noqa: E402
import tts  # noqa: E402
from speech_to_song import pyworld  # noqa: E402

from songbird import genome as G  # noqa: E402
from songbird import phrasing as P  # noqa: E402
from songbird.realize import sung_as  # noqa: E402
from songbird.synth import lineage_voices  # noqa: E402
from songbird.synth import voice as V  # noqa: E402
from songbird.theory import hz_to_midi  # noqa: E402

OUT = T.ROOT / "renders" / "reference"
# How far one performance strays from the singer's intent, note by note (one standard deviation).
NOISE = P.Gesture(early=0.03, hold=0.04, level=1.0, swell=1.0, scoop=15.0, bend=8.0, fall=15.0, vibrato=5.0)


def clip(g: P.Gesture) -> P.Gesture:
    return P.Gesture(*[min(max(v, lo), hi) for v, lo, hi in zip(astuple(g), astuple(P.LOW), astuple(P.HIGH))])


def keys(g: T.Guide) -> list[tuple[str, int]]:
    """(phrase, place in phrase) for every note of the guide: what a phrasing is keyed by."""
    return [(n.phrase, T.index_in_phrase(g.notes, k)) for k, n in enumerate(g.notes)]


def intend(g: T.Guide, rng) -> dict[tuple[str, int], P.Gesture]:
    """A singer's way with every note of the tune, shaped like a person's."""
    lean = float(rng.normal(-0.03, 0.02))  # most people sit a little behind the beat
    out = {}
    for k, (note, key) in enumerate(zip(g.notes, keys(g))):
        if key in out:
            continue
        prev = g.notes[k - 1] if k and not g.notes[k - 1].line_end else None
        leap = note.pitch - prev.pitch if prev else 0.0
        long = note.dur >= 0.6
        detached = not note.line_end and rng.random() < 0.15
        out[key] = clip(P.Gesture(
            early=float(np.clip(rng.normal(lean, 0.035), -0.15, 0.15)),
            hold=float(rng.uniform(0.7, 0.95)) if note.line_end else float(rng.uniform(0.75, 0.95)) if detached else 1.0,
            level=float(rng.normal(0.0, 2.0)),
            swell=float(rng.normal(0.0, 2.5 if long else 0.8)),
            scoop=float(rng.normal(-60.0, 25.0) if leap >= 3 else rng.normal(-15.0, 15.0)),
            bend=float(rng.normal(0.0, 10.0)),
            fall=float(rng.normal(-60.0, 30.0) if note.line_end else rng.normal(0.0, 10.0)),
            vibrato=float(rng.uniform(20.0, 40.0)) if long else 0.0,
        ))
    return out


def perform(intent: dict, g: T.Guide, rng) -> list[P.Gesture]:
    """One take's gesture for every note of the guide: the intent, strayed from."""
    sung = []
    for key in keys(g):
        want = intent[key]
        noisy = {f.name: getattr(want, f.name) + rng.normal(0.0, getattr(NOISE, f.name)) for f in fields(P.Gesture)}
        noisy["hold"] = noisy["hold"] if want.hold < 1.0 else 1.0  # a legato note stays legato
        noisy["vibrato"] = max(noisy["vibrato"], 0.0) if want.vibrato > 0 else 0.0
        sung.append(clip(P.Gesture(**noisy)))
    return sung


def spoken(spec: str, g: T.Guide, model):
    """A voice's reading of the lyric, analysed and aligned syllable by syllable (the alignment kept)."""
    texts, which = S.script(g.notes, g.lines)
    reading = tts.speak(texts, spec, S.SR, S.PAUSE)
    world = S.analyze(reading)
    band, active = S.tracks(world[1])
    midi = hz_to_midi(float(np.median(world[0][world[0] > 0])))
    cache = OUT / tts.slug(spec) / f"reading.{g.digest}.knots.json"
    if cache.exists():
        knots = json.loads(cache.read_text())
    else:
        first_of = {}
        for i, w in enumerate(which):
            first_of.setdefault(w, g.lines[i])
        knots = S.align_reading(model(), reading, world, band, active, texts, first_of, g.notes, g.lexicon, midi)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(knots) + "\n")
    return {"world": world, "knots": knots, "band": band, "which": which, "midi": midi}


def octave_for(midi: float, g: T.Guide) -> int:
    """The octave a speaker would sing the tune in: its middle about four semitones above their speaking pitch."""
    return 12 * int(np.round((midi + 4 - np.median([n.pitch for n in g.notes])) / 12))


def mic(y: np.ndarray, rng) -> np.ndarray:
    """A cheap microphone in a small room: no deep lows or airy highs, a little
    reflection and hiss, and some level of its own."""
    y = sosfilt(butter(2, 110.0, "highpass", fs=S.SR, output="sos"), y)
    y = sosfilt(butter(4, 7000.0, "lowpass", fs=S.SR, output="sos"), y)
    n = int(0.3 * S.SR)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / S.SR * 6.9 / 0.25)  # RT60 a quarter second
    wet = fftconvolve(y, ir / np.sqrt(np.sum(ir**2)))[: len(y)]
    y = y + 0.15 * wet + 10 ** (-58 / 20) * np.max(np.abs(y)) * rng.standard_normal(len(y))
    return y * 10 ** (rng.uniform(-12.0, -4.0) / 20) / (np.max(np.abs(y)) + 1e-12)


SEED_VC = Path(os.environ.get("SEED_VC", T.ROOT.parent / "seed-vc"))


def seedvc(y: np.ndarray, target: Path) -> np.ndarray:
    """y sung again in the voice of the singer in target, keeping y's pitch and timing (Seed-VC, singing model)."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "source.wav"
        sf.write(str(src), y.astype(np.float32), S.SR, subtype="FLOAT")
        subprocess.run([str(SEED_VC / ".venv" / "bin" / "python"), "inference.py", "--source", str(src),
                        "--target", str(Path(target).resolve()), "--output", tmp, "--diffusion-steps", "30", "--length-adjust", "1.0",
                        "--inference-cfg-rate", "0.7", "--f0-condition", "True", "--auto-f0-adjust", "False",
                        "--semi-tone-shift", "0", "--fp16", "False"],
                       cwd=SEED_VC, check=True, capture_output=True)
        out, sr = sf.read(str(next(Path(tmp).glob("vc_*.wav"))), always_2d=True)
    out = out.mean(axis=1)
    return resample_poly(out, S.SR, sr) if sr != S.SR else out


def sing(spec: str, g: T.Guide, sung: list[P.Gesture], reading, seed: int) -> tuple[np.ndarray, int]:
    """One take: the guide's notes sung with these gestures in the voice spec."""
    beat = 60.0 / g.tempo
    notes = [sung_as(n, ge, beat) for n, ge in zip(g.notes, sung)]
    if spec == "formant":
        singer = lineage_voices(1, seed)[0]
        return V.sing(notes, S.SR, singer, seed, g.lexicon), singer.shift
    if spec.startswith("seedvc:"):
        target = Path(spec.split(":", 1)[1])
        tone, sr = sf.read(str(target), always_2d=True)
        f0 = pyworld.harvest(np.ascontiguousarray(tone.mean(axis=1)), sr, f0_floor=60.0, f0_ceil=900.0, frame_period=5.0)[0]
        shift = octave_for(hz_to_midi(float(np.median(f0[f0 > 0]))) - 4, g)  # sung where the target sings
        singer = V.VoiceParams(engine="formant", shift=shift, vibrato_depth=1.0, scoop=0.0, jitter=0.2, wander=3.0)
        return seedvc(V.sing(notes, S.SR, singer, seed, g.lexicon), target), shift
    shift = octave_for(reading["midi"], g)
    # the gestures carry the vibrato and scoops; a unit depth lets a note's own vibrato through as it is
    singer = V.VoiceParams(engine="formant", shift=shift, vibrato_depth=1.0, scoop=0.0, jitter=0.2, wander=3.0)
    segs = V.schedule(notes, singer, g.lexicon)
    y = S.sing_from_speech(notes, segs, reading, g.lines, reading["which"], singer, seed)
    return y, shift


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    ap.add_argument("--voice", nargs="+", default=["formant"], help="formant, say:<voice>, elevenlabs:<voice>, gemini:<voice>")
    ap.add_argument("--takes", type=int, default=4, help="takes per voice")
    ap.add_argument("--seed", type=int, default=1, help="the intended phrasing (shared by every voice) and the takes")
    args = ap.parse_args()

    genome_path = Path(args.genome).resolve()
    genome = G.load(genome_path)
    g = T.guide(genome_path, genome)
    intent = intend(g, np.random.default_rng(args.seed))
    whisper = None

    def model():
        nonlocal whisper
        if whisper is None:
            whisper = T.WhisperModel("base.en", device="cpu", compute_type="int8")
        return whisper

    for vi, spec in enumerate(args.voice):
        reading = None if spec == "formant" or spec.startswith("seedvc:") else spoken(spec, g, model)
        folder = OUT / ("formant" if spec == "formant" else
                        f"seedvc-{Path(spec.split(':', 1)[1]).parent.name}" if spec.startswith("seedvc:") else tts.slug(spec))
        folder.mkdir(parents=True, exist_ok=True)
        for j in range(args.takes):
            rng = np.random.default_rng([args.seed, vi, j])
            sung = perform(intent, g, rng)
            y, shift = sing(spec, g, sung, reading, seed=1000 * args.seed + j)
            y = mic(y, rng)
            wav = folder / f"{genome_path.stem}-take{j + 1}.wav"
            sf.write(str(wav), y.astype(np.float32), S.SR, subtype="FLOAT")
            truth = {
                "voice": spec, "seed": args.seed, "take": j + 1, "guide": g.digest, "shift": shift,
                "fields": [f.name for f in fields(P.Gesture)], "noise": list(astuple(NOISE)),
                "intended": {f"{p}#{i}": list(astuple(ge)) for (p, i), ge in intent.items()},
                "sung": [list(astuple(ge)) for ge in sung],
            }
            wav.with_suffix(".truth.json").write_text(json.dumps(truth) + "\n")
            print(f"{wav.relative_to(T.ROOT)}  {len(y) / S.SR:.0f} s, sung {shift:+d}")


if __name__ == "__main__":
    main()
