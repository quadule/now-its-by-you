"""Blind A/B listening by Gemini: which of two renders of the same singing sounds more like a person (dev only).

    GEMINI_API_KEY=... uv run python tools/throat/gemini_judge.py A.wav B.wav [--windows 20:40 60:80] [--model ...]
        [--log renders/throat-scylla/eval/gemini.jsonl]

UTMOS preferred the synthetic house voice to real singers (docs/THROAT.md, round 3), so it can't choose between
voices here. This asks a listening model instead. Each window of the two files (the same notes, timing and seed,
so only the voice differs) is cut out, loudness-matched and sent as two clips, asked twice with the order swapped,
so a preference for the first or second clip cancels out. The answer is JSON: which clip sounds more like a real
person singing (less robotic, buzzy or vocoded), which has clearer words, and what it heard in each. Each call's
tokens go to the log with the answer, so the spend can be added up (--cost says what a million tokens cost).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import time
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf

PROMPT = """You are an expert vocal producer judging singing synthesis. Clip 1 and Clip 2 are two renders of the same
sung phrase: the same words, notes and timing, and only the voice differs. Listen carefully to both.

Judge:
1. human: which clip sounds more like a real person singing (less robotic, buzzy, metallic, vocoded or
   synthetic), and how strongly (0 = no difference, 1 = slight, 2 = clear, 3 = large).
2. words: which clip's words are clearer, and how strongly (same scale).
3. notes: for each clip, a short note on what sounds artificial or wrong in it.

Answer only with JSON: {"human": 1 or 2, "human_strength": 0-3, "words": 1 or 2, "words_strength": 0-3,
"clip1": "...", "clip2": "..."}"""


def clip(path: Path, a: float, b: float) -> np.ndarray:
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    x = x.mean(axis=1)[int(a * sr): int(b * sr)]
    rms = float(np.sqrt(np.mean(x ** 2))) or 1.0
    return np.clip(x * (0.1 / rms), -1, 1), sr


def flac(x: np.ndarray, sr: int) -> str:
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="FLAC")
    return base64.b64encode(buf.getvalue()).decode()


def ask(model: str, one: tuple, two: tuple) -> tuple[dict, dict]:
    body = {"contents": [{"parts": [{"text": "Clip 1:"}, {"inline_data": {"mime_type": "audio/flac", "data": flac(*one)}},
                                    {"text": "Clip 2:"}, {"inline_data": {"mime_type": "audio/flac", "data": flac(*two)}},
                                    {"text": PROMPT}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                out = json.loads(r.read())
            text = "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"])
            return json.loads(text), out.get("usageMetadata", {})
        except Exception as e:  # rate limits, the odd 500, an answer that isn't JSON: wait and ask again
            if attempt == 3:
                raise
            print(f"  retrying after {e}", flush=True)
            time.sleep(20 * (attempt + 1))
    raise AssertionError("unreachable")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--windows", nargs="*", default=["30:55"], help="START:END seconds, cut from both files")
    ap.add_argument("--model", default="gemini-3.8-flash")
    ap.add_argument("--log", type=Path, default=None)
    ap.add_argument("--cost", default="1:6", help="dollars per million input:output tokens (an upper guess)")
    args = ap.parse_args()
    cin, cout = (float(c) for c in args.cost.split(":"))
    score = dict(human=0.0, words=0.0)
    spent = 0.0
    for w in args.windows:
        a, b = (float(t) for t in w.split(":"))
        A, B = clip(args.a, a, b), clip(args.b, a, b)
        for order, (one, two) in (("AB", (A, B)), ("BA", (B, A))):
            ans, use = ask(args.model, one, two)
            first_is_a = order == "AB"
            for k in ("human", "words"):
                a_won = (ans.get(k) == 1) == first_is_a
                score[k] += (1 if a_won else -1) * float(ans.get(f"{k}_strength", 1))
            cost = (use.get("promptTokenCount", 0) * cin + (use.get("candidatesTokenCount", 0)
                    + use.get("thoughtsTokenCount", 0)) * cout) / 1e6
            spent += cost
            rec = dict(a=str(args.a), b=str(args.b), window=w, order=order, answer=ans, usage=use, cost=round(cost, 4))
            if args.log:
                args.log.parent.mkdir(parents=True, exist_ok=True)
                with open(args.log, "a") as f:
                    f.write(json.dumps(rec) + "\n")
            print(f"{w} {order}: human {ans.get('human')} ({ans.get('human_strength')}), words {ans.get('words')} "
                  f"({ans.get('words_strength')})  ${cost:.3f}", flush=True)
    n = 2 * len(args.windows)
    print(f"A over B: human {score['human'] / n:+.2f}, words {score['words'] / n:+.2f} (per question, -3..+3); "
          f"about ${spent:.2f}")


if __name__ == "__main__":
    main()
