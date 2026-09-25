"""A person's phrasing, taken from a plain reading of the lyrics (dev-only).

    uv run python tools/phrasing.py songs/h-now-its-by-you.json --script
    uv run python tools/phrasing.py songs/h-now-its-by-you.json --speech recordings/h.m4a
    uv run python tools/phrasing.py songs/h-now-its-by-you.json --say Daniel
    uv run songbird render songs/h-now-its-by-you.json --phrasing renders/phrasing/h-now-its-by-you.daniel.json

The reading is aligned the way tools/speech_to_song.py aligns it, then every
syllable is measured against its note: where it falls in its line compared
with where the tune puts it, how long it lasts, how loud it is and whether it
grows or fades, and how its pitch moves into, through and out of it. Speech
isn't singing, so each measurement is scaled down (SPEECH) before it becomes
a gesture: the speaker's rhythm and emphasis lean on the tune rather than
replace it. Each note of the tune gets one gesture, averaged over every word
sung to it, rounded (songbird.phrasing), and written to renders/phrasing/.
Nothing of the voice is kept.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import speech_to_song as S  # noqa: E402

from faster_whisper import WhisperModel  # noqa: E402

from songbird import genome as G  # noqa: E402
from songbird import phrasing as P  # noqa: E402
from songbird.realize import choose_params, realize  # noqa: E402

# How much of each spoken measurement a singer keeps, and how far it may go.
# Speech rhythm, emphasis and intonation don't follow a tune; leaning on them
# harder than this pushed syllables off the beat, weakened weak words and
# swooped the pitch, and cost words (H, formant voice: 18% misheard -> 26%).
SPEECH = dict(timing=0.15, level=0.3, swell=0.3, scoop=0.15, bend=0.1, fall=0.2)
SPEECH_LIMIT = dict(early=0.1, level=(-4.0, 4.0), cents=60.0)


def cents(f0: np.ndarray) -> np.ndarray:
    return 1200.0 * np.log2(f0 / np.median(f0))


def measure(line_notes, knots, f0, band, tempo: float) -> list[P.Gesture]:
    """One gesture for each syllable of one spoken line."""
    beats = np.array([n.start * tempo / 60.0 for n in line_notes])
    spoken = np.array([k[1] * S.FRAME for k in knots])  # vowel onsets, seconds
    # the reading's pace against the tune's: seconds per beat, and where the line starts
    slope, offset = np.polyfit(beats, spoken, 1) if len(knots) >= 3 else (0.0, 0.0)
    levels = np.array([np.mean(band[max(v0, (v0 + v1) // 2 - 3) : (v0 + v1) // 2 + 4]) for _, v0, v1, _ in knots])
    gestures = []
    for j, (on, v0, v1, c1) in enumerate(knots):
        g = {}
        if slope > 0:
            late = (spoken[j] - (slope * beats[j] + offset)) / slope  # beats behind where the tune would put it
            g["early"] = -SPEECH["timing"] * late
        # where the speaker paused after a word, the singer lets go a little early and breathes
        if j + 1 < len(knots) and (knots[j + 1][0] - c1) * S.FRAME > 0.06:
            g["hold"] = 0.85
        g["level"] = SPEECH["level"] * (levels[j] - np.median(levels))
        n = max(v1 - v0, 1)
        g["swell"] = SPEECH["swell"] * (np.mean(band[v1 - max(n // 4, 1) : v1]) - np.mean(band[v0 : v0 + max(n // 4, 1)]))
        voiced = np.flatnonzero(f0[v0:c1] > 0)
        c = cents(f0[v0:c1][voiced]) if len(voiced) else np.zeros(0)
        c = c[np.abs(c) < 700.0]  # a tracker's octave slips are not gestures
        if len(c) >= 4:
            q1, q3 = c[len(c) // 4], c[3 * len(c) // 4]
            g["scoop"] = SPEECH["scoop"] * np.mean(c[:3])
            g["bend"] = SPEECH["bend"] * (q3 - q1)
            g["fall"] = SPEECH["fall"] * (np.mean(c[-3:]) - q3)
        if "early" in g:
            g["early"] = np.clip(g["early"], -SPEECH_LIMIT["early"], SPEECH_LIMIT["early"])
        g["level"] = np.clip(g["level"], *SPEECH_LIMIT["level"])
        for k in ("scoop", "bend", "fall"):
            if k in g:
                g[k] = np.clip(g[k], -SPEECH_LIMIT["cents"], SPEECH_LIMIT["cents"])
        gestures.append(P.Gesture(**{k: float(v) for k, v in g.items()}))
    return gestures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--speech", help="a recording of the script, read plainly")
    source.add_argument("--say", metavar="VOICE", help="read the script with a macOS voice instead")
    source.add_argument("--script", action="store_true", help="print the lines to read and stop")
    ap.add_argument("--name", help="who the phrasing came from, if they want it said (principle 12)")
    ap.add_argument("--out", help="output JSON (default renders/phrasing/<genome>.<source>.json)")
    args = ap.parse_args()

    genome = G.load(args.genome)
    params = choose_params(genome)
    # every phrase of the song, once: the seed's form plus every verse
    form = list(params.form) + ["verse"] * max(len(genome.seed_verses) - list(params.form).count("verse"), 0)
    score = realize(genome, replace(params, form=tuple(form)))
    notes = sorted(score.part("voice"), key=lambda n: n.start)
    lines = S.lines_of(notes)
    texts, which = S.script(notes, lines)
    if args.script:
        print("\n".join(texts))
        return

    reading = S.say(texts, args.say) if args.say else S.load(args.speech)
    world = S.analyze(reading)
    band, active = S.tracks(world[1])
    spoken = S.hz_to_midi(float(np.median(world[0][world[0] > 0])))
    first_of = {}
    for i, w in enumerate(which):
        first_of.setdefault(w, lines[i])
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    knots = S.align_reading(model, reading, world, band, active, texts, first_of, notes, genome.lexicon, spoken)

    seen: dict[tuple[str, int], list[P.Gesture]] = defaultdict(list)
    for li, line in first_of.items():
        line_notes = [notes[k] for k in line]
        for j, g in enumerate(measure(line_notes, knots[li], world[0], band, params.tempo)):
            seen[(line_notes[0].phrase, j)].append(g)
    phrasing = {}
    for pid, phrase in genome.phrases.items():
        count = len(phrase.sung)
        if any((pid, j) in seen for j in range(count)):
            phrasing[pid] = tuple(P.average(seen[(pid, j)]) if (pid, j) in seen else P.Gesture() for j in range(count))

    who = args.name or (f"{args.say} (macOS say)" if args.say else "a reader")
    data = P.to_json(phrasing, source="speech", source_detail=f"a reading by {who}", scale=SPEECH, limit=SPEECH_LIMIT)
    tag = (args.say or Path(args.speech).stem).split()[0].lower()
    out = Path(args.out or Path("renders") / "phrasing" / f"{Path(args.genome).stem}.{tag}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1) + "\n")
    rows = [g for gs in phrasing.values() for g in gs]
    print(f"{out}: {len(rows)} notes in {len(phrasing)} phrases; "
          f"timing spread {np.std([g.early for g in rows]):.3f} beats, level spread {np.std([g.level for g in rows]):.1f} dB, "
          f"falls {np.mean([g.fall for g in rows]):+.0f} cents on average")


if __name__ == "__main__":
    main()
