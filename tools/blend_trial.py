"""Which blend of the singers is easiest to understand? Renders the stage version
sung several ways and has Whisper write down what it hears. (dev-only)

    uv run python tools/blend_trial.py performance/genome.json --with h-now-its-by-you
    uv run python tools/blend_trial.py performance/genome.json --with h-now-its-by-you --again

Each way is the stage rendition (--replay) with one lead phrasing: as recorded,
today's singers, each of them alone, and today's singers with the earlier ones
at each weight the recording page offers. The choir stays as recorded, so only
the lead differs. Renders go to renders/blends/<way>.flac with the lead's stem; the
scores to renders/blends/scores.json, which renders/blends/index.html (the
comparison page, tools/blend_compare.html) reads.

Whisper (small.en; --model for others) hears each section of the dry lead and
of the finished mix on its own: a whole song sends it into loops on long notes.
Two scores: the words it gets wrong, writing down what it hears, and how sure
it is of the words sung when it is told them. Both stand in for a listener's
ear, roughly: a word or two either way, or a model that disagrees, is noise.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shutil
import sys
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent))
import everyone as EV  # noqa: E402
import guides as M  # noqa: E402
import takes as K  # noqa: E402
from intelligibility import align, normalize  # noqa: E402
from recorder import WEIGHTS  # noqa: E402
from wer_suite import collapse_loops  # noqa: E402

from songbird import genome as G  # noqa: E402

ROOT = Path(__file__).parent.parent
OUT = ROOT / "renders" / "blends"


def ways(genome_path: Path, genome, also: str | None) -> dict[str, dict]:
    """Each way to sing it: {name: {"label", "phrasing" (None: as recorded), "detail"}}."""
    today = [t for t in K.takes(genome_path.stem) if t.use]
    earlier = [t for t in K.measured_only(also) if t.use] if also else []
    out = {"recorded": {"label": "as recorded", "phrasing": None, "detail": "the stage version"}}

    def add(name, label, takes):
        out[name] = {"label": label, "phrasing": EV.blend(genome_path, genome, f"trial.{name}", takes),
                     "detail": f"{len(takes)} takes by {len({t.person for t in takes})} singers".replace(" by 1 singers", "")}

    add("today", "today", today)
    for person in sorted({t.person for t in today}):
        add(person, person, [t for t in today if t.person == person])
    for w in WEIGHTS if earlier else ():
        for t in today:
            t.weight = w
        add(f"with-x{w:g}", f"with the volunteers, ×{w:g}", today + earlier)
    for t in today:
        t.weight = 1.0
    return out


def render(genome_path: Path, record: Path, name: str, phrasing: Path | None) -> Path:
    from songbird.cli import main as songbird

    out = OUT / f"{name}.flac"
    args = ["render", str(genome_path), "--replay", str(record), "--stems", "--out", str(out)]
    args += ["--phrasing", str(phrasing)] if phrasing else []
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        songbird(args)
    for stem in OUT.glob(f"{name}.*.wav"):  # the lead's stem is all the scoring needs
        if stem.name != f"{name}.voice.wav":
            stem.unlink()
    return out


def sections(score: dict) -> list[dict]:
    """The sung sections in order: {"name", "from", "to", "words", "lines"}: the words as Whisper should hear
    them, and for each, whether a line ends on it."""
    out, cur = [], []
    notes = sorted((n for n in score["notes"] if n["part"] == "voice"), key=lambda n: n["start"])
    for n in notes:
        if cur and (n["section"] != cur[-1]["section"] or n["start"] - (cur[-1]["start"] + cur[-1]["dur"]) > 3):
            out.append(cur)
            cur = []
        cur.append(n)
    out.append(cur)
    result = []
    for s in out:
        words, ends, i = [], [], 0
        while i < len(s):
            j = i + max(s[i]["word_len"], 1)
            said = normalize(re.sub(r"\{[^{}]*\}", "", s[i]["word"]).replace("-", ""))  # without its say, bass{fish}
            words += said
            ends += [k == len(said) - 1 and any(n.get("line_end") for n in s[i:j]) for k in range(len(said))]
            i = j
        result.append({"name": s[0]["section"], "from": s[0]["start"], "to": s[-1]["start"] + s[-1]["dur"],
                       "words": words, "lines": ends})
    return result


def written(words: list[str], lines: list[bool]) -> list[tuple[str, str]]:
    """The words as Whisper writes a lyric down: each line capitalized and ending in a comma (I is always
    capital). Told the words in lower case and run together, it doubts every word that starts a line."""
    out, start = [], True
    for w, end in zip(words, lines):
        shown = "I" + w[1:] if w == "i" or w.startswith("i'") else (w.capitalize() if start else w)
        out.append((" " + shown, "," if end else ""))
        start = end
    return out


def sure(model, clip: np.ndarray, words: list[str], lines: list[bool]) -> list[float]:
    """How sure Whisper is of each sung word when it is told the words: the
    chance it gives the word's tokens, one after another, given the audio and
    the words before (the commas between lines are told, never counted). Unlike
    the error rate, it moves when a word gets a little clearer or a little
    muddier, not only when it flips to another word."""
    from faster_whisper.audio import pad_or_trim
    from faster_whisper.tokenizer import Tokenizer

    tokenizer = Tokenizer(model.hf_tokenizer, model.model.is_multilingual, task="transcribe", language="en")
    features = model.feature_extractor(clip)
    frames = features.shape[-1]
    tokens, spans = [], []
    for word, after in written(words, lines):
        spans.append((len(tokens), len(tokens) + len(tokenizer.encode(word))))
        tokens += tokenizer.encode(word) + (tokenizer.encode(after) if after else [])
    probs = model.model.align(model.encode(pad_or_trim(features)), tokenizer.sot_sequence, [tokens], frames)[0].text_token_probs
    return [float(np.prod(probs[a:b])) for a, b in spans]


def hear(model, audio: np.ndarray, sr: int, part: dict) -> dict:
    a, b = max(int((part["from"] - 0.3) * sr), 0), int((part["to"] + 0.5) * sr)
    clip = resample_poly(audio[a:b], 16000, sr).astype(np.float32)
    clip /= np.abs(clip).max() + 1e-9
    certain = sure(model, clip, part["words"], part["lines"])
    segments, _ = model.transcribe(clip, language="en", beam_size=5, temperature=0.0,
                                   condition_on_previous_text=False, vad_filter=False, no_repeat_ngram_size=5)
    heard = " ".join(s.text for s in segments).strip()
    _, pairs = align(part["words"], collapse_loops(normalize(heard)))
    while pairs and not pairs[-1][0]:  # words Whisper runs on with after the last note are its own
        pairs.pop()
    while pairs and not pairs[0][0]:
        pairs.pop(0)
    return {"heard": heard, "edits": sum(r != h for r, h in pairs),
            "missed": [[r, h] for r, h in pairs if r != h], "sure": [round(p, 3) for p in certain]}


def score(model, flac: Path, parts: list[dict]) -> dict:
    out = {}
    for kind, path in (("voice", flac.with_suffix(".voice.wav")), ("mix", flac)):
        audio, sr = sf.read(path)
        mono = audio.mean(axis=1) if audio.ndim == 2 else audio
        heard = [hear(model, mono, sr, p) for p in parts]
        words = sum(len(p["words"]) for p in parts)
        every = [p for h in heard for p in h["sure"]]
        out[kind] = {"wer": sum(h["edits"] for h in heard) / words, "edits": sum(h["edits"] for h in heard),
                     # the typical word's chance (a geometric mean: one lost word counts for more than one clear one)
                     "sure": float(np.exp(np.mean(np.log(np.maximum(every, 1e-6))))),
                     "sections": heard}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    ap.add_argument("--with", dest="also", metavar="SONG")
    ap.add_argument("--model", default=["small.en"], nargs="+",
                    help="Whisper models to hear with; the page shows the first, the others are printed to check it by")
    ap.add_argument("--again", action="store_true", help="render every way again, not just the ones not yet rendered")
    args = ap.parse_args()
    genome_path = Path(args.genome).resolve()
    genome = G.load(genome_path)
    record = ROOT / M.sets(genome_path, genome)[0]["record"]
    OUT.mkdir(parents=True, exist_ok=True)

    found = ways(genome_path, genome, args.also)
    for name, way in found.items():
        if args.again or not (OUT / f"{name}.voice.wav").exists():
            print(f"rendering {name}", flush=True)
            render(genome_path, record, name, way["phrasing"])

    from faster_whisper import WhisperModel

    parts = sections(json.load(open(OUT / "recorded.score.json")))
    result = {"model": args.model[0], "sections": [{k: p[k] for k in ("name", "from", "to", "lines")} | {"words": " ".join(p["words"])}
                                                 for p in parts], "ways": []}
    for m, model_name in enumerate(args.model):
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        print(f"{model_name:<32} {'lead: missed':>14} {'sure':>6}   {'mix: missed':>12} {'sure':>6}", flush=True)
        for name, way in found.items():
            s = score(model, OUT / f"{name}.flac", parts)
            print(f"{way['label']:<32} {s['voice']['wer']:14.1%} {s['voice']['sure']:6.1%}   "
                  f"{s['mix']['wer']:12.1%} {s['mix']['sure']:6.1%}", flush=True)
            if m == 0:
                result["ways"].append({"name": name, "label": way["label"], "detail": way["detail"],
                                       "file": f"{name}.flac", **s})
        if m == 0:  # the page can open while the other models check it
            (OUT / "scores.json").write_text(json.dumps(result, indent=1))
            shutil.copy(Path(__file__).with_name("blend_compare.html"), OUT / "index.html")


if __name__ == "__main__":
    main()
