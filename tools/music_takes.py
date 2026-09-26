"""Takes of the song by music models, steered onto the guide as closely as they go (dev-only).

    ELEVENLABS_API_KEY=... uv run python tools/music_takes.py songs/h-now-its-by-you.json --eleven "warm baritone folk singer" ...
    GEMINI_API_KEY=... uv run python tools/music_takes.py songs/h-now-its-by-you.json --lyria "warm baritone folk singer"

A music model sings like a person, but picks its own melody and timing. So
each is told everything it will take about ours:

- Eleven Music (music_v2_5): each sung section of the song asked for on its
  own, exactly as long as in the guide, with that section's words, sung a
  cappella in the voice described, and conditioned (condition_strength
  "xhigh") on the same stretch of the guide's own singer, uploaded once.
  That's the closest thing to "sing this melody" it has: on the first
  refrain, 69% of the notes landed within a semitone of ours, and the words
  within about 0.2 s. (Asked for the whole song at once, it let the words
  slide about a line early through each section.)
- Lyria 3.5: a prompt with the tempo, key and metre, and every lyric line
  with its own timestamp from the guide. It takes no audio, so it only
  follows as far as words go.

Each take is laid on the guide's timeline and written to
renders/reference/music/<model>-<voice>/<song>-take1.wav, with what was
asked for beside it. What phrasing a take sang isn't known: these are for
extracting and combining phrasings from singers who sound like people (a
test; they never join the lineage), not for checking the extractor against
a truth (tools/reference.py).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import phrasing as T  # noqa: E402
import speech_to_song as S  # noqa: E402
import tts  # noqa: E402

from songbird import genome as G  # noqa: E402
from songbird.realize import choose_params  # noqa: E402
from songbird.synth import voice as V  # noqa: E402

OUT = T.ROOT / "renders" / "reference" / "music"
NAMES = {"intro": "Intro", "verse": "Verse", "refrain": "Chorus", "turn": "Interlude", "bridge": "Bridge", "tag": "Outro",
         "break": "Interlude", "outro": "Outro"}
UNSUNG = "(soft humming, no words)"
A_CAPPELLA = ["a cappella", "solo voice", "unaccompanied", "no instruments", "intimate", "natural"]
AVOID = ["guitar", "piano", "drums", "percussion", "bass", "strings", "synth", "choir", "backing vocals", "harmonies"]


def sections(genome_path: Path, genome) -> list[dict]:
    """The guide's sections in order: name, start, end (seconds), and the lines sung in each with
    every word's time: (text, start, end, [(word, start)]). A line belongs where most of it falls,
    though its pickup starts before the bar line."""
    score = json.loads((T.ROOT / "renders" / "guide" / f"{genome_path.stem}.guide.score.json").read_text())
    g = T.guide(genome_path, genome)
    out = []
    for name, a, b in score["sections"]:
        lines = []
        for line in g.lines:
            first, last = g.notes[line[0]], g.notes[line[-1]]
            if a <= (first.start + last.start + last.dur) / 2 < b:
                words, k = [], line[0]
                while k <= line[-1]:
                    words.append((g.notes[k].word.replace("-", "").replace("*", ""), g.notes[k].start))
                    k += g.notes[k].word_len
                lines.append((" ".join(w for w, _ in words), first.start, last.start + last.dur, words))
        out.append({"name": name, "start": a, "end": b, "lines": lines})
    return out


def windows(parts: list[dict], end: float) -> list[tuple[dict, float, float]]:
    """Each sung section's stretch of the song: from just before its first pickup to just before the
    next sung section's, so the stretches meet without overlapping and a turn between sections
    rides at the end of the one before (quiet, as in the guide)."""
    sung = [p for p in parts if p["lines"]]
    starts = [min(p["start"], p["lines"][0][1] - 0.15) for p in sung]
    return [(p, a, b) for p, a, b in zip(sung, starts, starts[1:] + [end])]


def decode(raw: bytes) -> tuple[np.ndarray, int]:
    """Mono sound from a WAV or MP3 a service sent."""
    if raw[:4] == b"RIFF":
        y, sr = sf.read(io.BytesIO(raw), always_2d=True)
        return y.mean(axis=1), sr
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.mp3", Path(tmp) / "out.wav"
        src.write_bytes(raw)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(src), str(dst)], check=True)
        y, sr = sf.read(str(dst), always_2d=True)
    return y.mean(axis=1), sr


def on_guide(y: np.ndarray, sr: int, start: float) -> np.ndarray:
    """A take laid on the guide's timeline: starting at start seconds, at the guide's rate."""
    y = resample_poly(y, S.SR, sr) if sr != S.SR else y
    return np.concatenate([np.zeros(int(start * S.SR)), y])


def guide_singer(genome_path: Path, genome) -> np.ndarray:
    """The guide's own singer alone, the melody Eleven Music is conditioned on."""
    g = T.guide(genome_path, genome)
    return V.sing(g.notes, S.SR, V.VoiceParams(), choose_params(genome).seed, g.lexicon)


def eleven(genome_path: Path, genome, voice: str, seed: int, song_id: str | None, strength: str = "xhigh",
           only: list[int] | None = None) -> tuple[np.ndarray, dict]:
    """A take section by section: asked for all at once, Eleven Music let the words slide about a line
    early through each section, but a single section, conditioned on its own stretch of the guide, keeps
    within about 0.2 s. Every sung section is asked for on its own (same voice, same seed) and laid where
    it belongs; the unsung ones stay silent."""
    xi = {"xi-api-key": tts.key("ELEVENLABS_API_KEY")}
    parts = sections(genome_path, genome)
    origin = parts[0]["start"]
    if song_id is None:  # the guide's singer, uploaded once, sliced per section
        buf = io.BytesIO()
        y = guide_singer(genome_path, genome)
        sf.write(buf, y[int(origin * S.SR):].astype(np.float32), S.SR, format="WAV", subtype="PCM_16")
        body, kind = tts.multipart({"extract_composition_plan": "false"}, "file", "guide.wav", buf.getvalue())
        song_id = json.loads(tts.request("https://api.elevenlabs.io/v1/music/upload", {**xi, "Content-Type": kind}, body))["song_id"]
    take = np.zeros(int((parts[-1]["end"] + 1.0) * S.SR))
    asked = []
    for w, (part, t0, t1) in enumerate(windows(parts, parts[-1]["end"] + 0.5)):
        if only is not None and w not in only:
            continue
        a, b = int(round((t0 - origin) * 1000)), int(round((t1 - origin) * 1000))
        chunk = {
            "text": f"[{NAMES.get(part['name'], part['name'].title())}]\n" + "\n".join(line[0] for line in part["lines"]),
            "duration_ms": b - a,
            "positive_styles": [voice, *A_CAPPELLA, f"{choose_params(genome).tempo:.0f} bpm"],
            "negative_styles": AVOID,
            "context_adherence": "high",
            "conditioning_ref": {"song_id": song_id, "range": {"start_ms": a, "end_ms": min(b, a + 30000)}},
            "condition_strength": strength,
        }
        best = None
        for attempt in range(TRIES):  # a stretch that sings other words, or sings them late or early, is asked for again
            request = {"composition_plan": {"chunks": [chunk]}, "model_id": "music_v2_5", "seed": seed + 1000 * attempt}
            y, sr = decode(tts.request("https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128", xi, request))
            y = on_guide(y, sr, t0)[: int(t1 * S.SR)]
            y, moved, tune, key = placed(y, genome_path, genome, t0, t1)
            heard, off = check(y, part["lines"], t0)
            if len({w for line in part["lines"] for w, _ in line[3]}) <= 2:
                off = 0.0  # la la la: one word over and over can't say where it was sung
            good = heard >= WORDS_NEEDED and off <= WHEN_NEEDED and tune >= TUNE_NEEDED and key % 12 == 0
            rank = (good, key % 12 == 0, tune >= TUNE_NEEDED, heard >= 0.75, tune, -off)
            if best is None or rank > best[0]:
                best = (rank, y, heard, off, tune, key, moved, request)
            if good:
                break
            print(f"  {part['name']} at {t0:.0f} s: {heard:.0%} of its words heard, {off:.2f} s from ours; "
                  f"{tune:.0%} of notes on our tune, {key:+d} semitones; asking again")
        _, y, heard, off, tune, key, moved, request = best
        fade = np.minimum(1.0, np.minimum(np.arange(len(y)), np.arange(len(y))[::-1]) / (0.02 * S.SR))
        take[: len(y)] += (y * fade)[: len(take)]
        asked.append({**request, "words_heard": round(heard, 2), "seconds_off": round(off, 2), "on_tune": round(tune, 2),
                      "key": key, "moved_s": round(moved, 3)})
    return take, {"model": "music_v2_5", "voice": voice, "seed": seed, "strength": strength, "song_id": song_id, "requests": asked}


TRIES = 4
WORDS_NEEDED = 0.85  # of a stretch's words that Whisper must hear sung, in order
TUNE_NEEDED = 0.6  # of its notes that must land within a semitone of ours (in our key, any octave)


def placed(y: np.ndarray, genome_path: Path, genome, t0: float, t1: float) -> tuple[np.ndarray, float, float, int]:
    """A stretch laid where it was sung along to the guide: slid (up to a second either way) so its
    singing sits over the guide's vowels, as someone singing along would have it. Returns it, how far
    it moved (seconds, positive later), the share of its notes within a semitone of ours, and the key
    it was sung in (semitones from ours)."""
    g = T.guide(genome_path, genome)
    a, b = int(t0 / S.FRAME), int(t1 / S.FRAME)
    f0, _band, active = T.analyze_take(y[int(t0 * S.SR) : int(t1 * S.SR)])
    inside = [(n, kn) for n, kn in zip(g.notes, g.knots) if t0 <= kn[1] < t1]
    expected = np.zeros(b - a)
    for _n, (_on, v0, v1, *_r) in inside:
        expected[max(int(v0 / S.FRAME) - a, 0) : max(int(v1 / S.FRAME) - a, 0)] = 1.0
    sung = ((f0 > 0) & active)[: b - a].astype(float)
    sung = np.pad(sung, (0, max(0, (b - a) - len(sung))))
    reach = 200  # frames: a second
    score = [np.dot(np.roll(sung, -lag), expected) - (abs(lag) * 1e-3) for lag in range(-reach, reach + 1)]
    lag = int(np.argmax(score)) - reach  # the stretch runs lag frames behind the guide
    shift = int(round(-lag * S.FRAME * S.SR))
    y = np.roll(y, shift)
    y[: max(shift, 0)] = 0.0
    if shift < 0:
        y[shift:] = 0.0
    f0 = np.roll(f0, -lag)
    cents = []
    for n, (_on, v0, v1, *_r) in inside:
        i0, i1 = int(v0 / S.FRAME) - a, int(v1 / S.FRAME) - a
        v = f0[max(i0, 0) : max(i1, 0)]
        v = v[v > 0]
        if len(v) >= 5:
            cents.append(1200 * np.log2(np.median(v) / 440.0) + 6900 - 100 * n.pitch)
    if not cents:
        return y, -lag * S.FRAME, 0.0, 99
    cents = np.array(cents)
    key = int(np.round(np.median(cents) / 100))
    return y, -lag * S.FRAME, float(np.mean(np.abs(cents - 100 * key) <= 100)), key
WHEN_NEEDED = 0.6  # seconds: how far, typically, the words may fall from where the guide sings them
_whisper = None


def check(y: np.ndarray, lines: list, t0: float) -> tuple[float, float]:
    """For a stretch laid on the guide's timeline from t0: the share of its lines' words heard sung
    (in order), and the median distance (seconds) between where they were sung and where the guide sings them."""
    global _whisper
    from faster_whisper import WhisperModel
    from intelligibility import align, normalize

    if _whisper is None:
        _whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
    audio = resample_poly(y[int(t0 * S.SR):], 16000, S.SR).astype(np.float32)
    segments, _ = _whisper.transcribe(audio, language="en", beam_size=5, condition_on_previous_text=False, word_timestamps=True)
    heard = [(tok, t0 + w.start) for s in segments for w in s.words for tok in normalize(w.word)]
    want = [(tok, at) for line in lines for word, at in line[3] for tok in normalize(word)]
    _, pairs = align([w for w, _ in want], [w for w, _ in heard])
    i = j = 0
    offs = []
    for r, h in pairs:
        if r and h and r == h:
            offs.append(abs(heard[j][1] - want[i][1]))
        i, j = i + bool(r), j + bool(h)
    return len(offs) / max(len(want), 1), float(np.median(offs)) if offs else 99.0


def lyria(genome_path: Path, genome, voice: str) -> tuple[np.ndarray, dict]:
    params = choose_params(genome)
    parts = sections(genome_path, genome)
    origin = parts[0]["start"]

    def at(t: float) -> str:
        t -= origin
        return f"{int(t // 60)}:{t % 60:04.1f}"

    lines = []
    for part in parts:
        name = NAMES.get(part["name"], part["name"].title())
        if not part["lines"]:
            lines.append(f"[{at(part['start'])} - {at(part['end'])}] {name}: soft humming, no words")
        for text, a, b, _ in part["lines"]:
            lines.append(f"[{at(a)} - {at(b)}] {name}: {text}")
    prompt = (f"A folk song sung a cappella by one {voice}, completely unaccompanied, no instruments. "
              f"{params.tempo:.0f} BPM, 4/4, in D major, gentle and unhurried; every line sung exactly where "
              f"its timestamp puts it, a breath between lines.\n" + "\n".join(lines))
    body = {"model": "lyria-3.5", "input": prompt, "response_format": {"type": "audio"}}
    reply = json.loads(tts.request("https://generativelanguage.googleapis.com/v1beta/interactions",
                                   {"x-goog-api-key": tts.key("GEMINI_API_KEY")}, body))
    found = []

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("data"), str) and len(x["data"]) > 1000:
                found.append(base64.b64decode(x["data"]))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(reply)
    if not found:
        raise SystemExit(f"Lyria sent no audio: {json.dumps(reply)[:300]}")
    y, sr = decode(found[0])
    return on_guide(y, sr, origin), {"model": "lyria-3.5", "voice": voice, "prompt": prompt}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    ap.add_argument("--eleven", nargs="*", default=[], metavar="VOICE", help="Eleven Music takes, one per voice described")
    ap.add_argument("--lyria", nargs="*", default=[], metavar="VOICE", help="Lyria 3.5 takes, one per voice described")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--takes", type=int, default=1, help="takes per voice (each its own seed)")
    ap.add_argument("--first", type=int, default=1, help="number the takes from this one (to add to a voice's takes)")
    ap.add_argument("--windows", type=int, nargs="*", default=None, metavar="N",
                    help="only these sung sections (0 the first verse, 1 the first refrain...): a timbre prompt needs only one")
    ap.add_argument("--strength", default="xhigh", choices=("low", "medium", "high", "xhigh"),
                    help="how hard Eleven Music holds to the guide's melody: looser leaves the singer more of their own way")
    args = ap.parse_args()
    genome_path = Path(args.genome).resolve()
    genome = G.load(genome_path)
    song_id = None
    jobs = [("eleven", v, t) for v in args.eleven for t in range(args.first, args.first + args.takes)]
    jobs += [("lyria", v, t) for v in args.lyria for t in range(args.first, args.first + args.takes)]
    for i, (model, voice, number) in enumerate(jobs):
        if model == "eleven":
            y, about = eleven(genome_path, genome, voice, args.seed + i + 100 * (number - 1), song_id, args.strength,
                              args.windows)
            song_id = about["song_id"]
        else:
            y, about = lyria(genome_path, genome, voice)
        folder = OUT / (f"{model}-" + "-".join(w for w in "".join(c if c.isalnum() else " " for c in voice.lower()).split()[:3])
                        + ("" if model != "eleven" or args.strength == "xhigh" else f"-{args.strength}"))
        folder.mkdir(parents=True, exist_ok=True)
        wav = folder / f"{genome_path.stem}-take{number}.wav"
        sf.write(str(wav), (0.5 * y / (np.max(np.abs(y)) + 1e-12)).astype(np.float32), S.SR, subtype="FLOAT")
        about["guide"] = T.guide(genome_path, genome).digest  # the guide it was steered onto
        wav.with_suffix(".json").write_text(json.dumps(about, indent=1) + "\n")
        print(f"{wav.relative_to(T.ROOT)}  {len(y) / S.SR:.0f} s")


if __name__ == "__main__":
    main()
