"""A person's phrasing, taken from a sung take or a plain reading (dev-only).

    uv run python tools/phrasing.py songs/h-now-its-by-you.json --guide     # a backing track to sing along to
    uv run python tools/phrasing.py songs/h-now-its-by-you.json --sung recordings/h-take1.wav [more takes]
    uv run python tools/phrasing.py songs/h-now-its-by-you.json --speech recordings/h-reading.m4a
    uv run python tools/phrasing.py songs/h-now-its-by-you.json --say Daniel
    uv run songbird render songs/h-now-its-by-you.json --phrasing renders/phrasing/h-now-its-by-you.h-take1.json

Sung takes. Someone sings along to the guide (--guide) on headphones; the take
is placed against the guide's own score (by cross-correlating where they sing
with where the song has singing, unless it already lines up), found an
octave or key if they sang in their own, and aligned line by line by warping
the formant singer's performance of that line, whose every note boundary is
known, onto the take. Each note is then measured at full strength (SUNG): how
early or late its vowel lands against the beat, how long it's held, its level
and swell, how the pitch scoops in, bends and falls off, and the depth of any
vibrato. Wrong notes are fine: pitch gestures are measured around the note the
singer actually sang, and skipped where that was far from the tune.

Readings. The reading is aligned the way tools/speech_to_song.py aligns it, then every
syllable is measured against its note: where it falls in its line compared
with where the tune puts it, how long it lasts, how loud it is and whether it
grows or fades, and how its pitch moves into, through and out of it. Speech
isn't singing, so each measurement is scaled down (SPEECH) before it becomes
a gesture: the speaker's rhythm and emphasis lean on the tune rather than
replace it. Each note of the tune gets one gesture, averaged over every word
sung to it, rounded (songbird.phrasing), and written to renders/phrasing/.
Nothing of the voice is kept.

Either way, every note of the tune gets one gesture, averaged over each time
it comes round (and over every take), and a short portrait of the phrasing is
printed.
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
# A sung take is phrasing already; keep nearly all of it.
SUNG = dict(timing=1.0, level=0.8, swell=0.8, scoop=0.8, bend=0.8, fall=0.8, vibrato=1.0)
WRONG_NOTE = 150.0  # cents from the tune beyond which a note's pitch gestures aren't trusted


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


def load_guide(stem: str):
    """The voice notes of the guide someone sang along to, exactly as it was rendered."""
    from songbird.score import Note

    path = Path("renders") / "guide" / f"{stem}.guide.score.json"
    if not path.exists():
        raise SystemExit(f"no guide at {path}: write one with --guide and sing along to that")
    data = json.loads(path.read_text())
    return sorted((Note(**{**d, "gesture": None}) for d in data["notes"] if d["part"] == "voice"), key=lambda n: n.start)


def analyze_take(y: np.ndarray):
    """f0, vowel-band level and speech activity every FRAME seconds (no aperiodicity needed)."""
    x = np.ascontiguousarray(y, dtype=np.float64)
    f0, t = S.pyworld.harvest(x, S.SR, f0_floor=60.0, f0_ceil=900.0, frame_period=S.FRAME * 1000)
    band, active = S.tracks(S.pyworld.cheaptrick(x, f0, t, S.SR))
    return f0, band, active


def place_take(f0, active, knots, n_frames: int) -> int:
    """Frames by which the take runs behind the guide: where they sing against
    where the song has singing. Within 0.25 s it counts as already lined up
    (a take exported from a DAW), so a singer's own habit of sitting behind
    or ahead of the beat survives."""
    expected = np.zeros(n_frames)
    for _, v0, v1, _, _, _ in knots:
        expected[int(v0 / S.FRAME) : int(v1 / S.FRAME)] = 1.0
    sung = ((f0 > 0) & active).astype(float)
    size = 1 << int(np.ceil(np.log2(len(expected) + len(sung))))
    xc = np.fft.irfft(np.fft.rfft(sung - sung.mean(), size) * np.conj(np.fft.rfft(expected - expected.mean(), size)), size)
    reach = int(30.0 / S.FRAME)
    lags = np.concatenate([np.arange(0, reach), np.arange(-reach, 0)])
    best = int(lags[np.argmax(np.concatenate([xc[:reach], xc[-reach:]]))])
    return 0 if abs(best) * S.FRAME < 0.25 else best


def pitch_contour(notes, knots, n: int, t0: float) -> np.ndarray:
    """The tune's pitch every alignment frame from t0, zero between vowels."""
    out = np.zeros(n)
    for note, (_, v0, v1, *_rest) in zip(notes, knots):
        a, b = int((v0 - t0) * S.SR / S.HOP), int((v1 - t0) * S.SR / S.HOP)
        out[max(a, 0) : max(b, 0)] = note.pitch
    return out


def align_sung_line(take, f0, line_notes, line_knots, template, lag: int):
    """(vowel start, vowel end, release) in take frames for each note of one
    sung line: warp the template singer's performance of the line onto the take."""
    import librosa

    y_t, f0_t = template
    t0 = line_knots[0][0] - 0.05
    t1 = line_knots[-1][3] + 0.05
    a, b = int(t0 * S.SR), int(t1 * S.SR)
    ta = max(int((t0 + lag * S.FRAME - 0.35) * S.SR), 0)
    tb = min(int((t1 + lag * S.FRAME + 0.35) * S.SR), len(take))
    frames_t = np.clip(((a + np.arange((b - a) // S.HOP + 2) * S.HOP) / S.SR / S.FRAME).astype(int), 0, len(f0_t) - 1)
    frames_y = np.clip(((ta + np.arange((tb - ta) // S.HOP + 2) * S.HOP) / S.SR / S.FRAME).astype(int), 0, len(f0) - 1)
    X = S.features(y_t[a:b], (f0_t[frames_t] > 0).astype(float))
    Y = S.features(take[ta:tb], (f0[frames_y] > 0).astype(float))
    # relative pitch: the tune's shape and the singer's, each about its own middle
    tune = pitch_contour(line_notes, line_knots, X.shape[1], t0)
    heard = np.where(f0[frames_y[: Y.shape[1]]] > 0, 12 * np.log2(np.maximum(f0[frames_y[: Y.shape[1]]], 1) / 440) + 69, 0)
    for arr in (tune, heard):
        on = arr > 0
        if on.any():
            arr[on] -= np.median(arr[on])
    X = np.vstack([X, tune[None]])
    Y = np.vstack([Y, heard[None]])
    both = np.hstack([X, Y])
    mu, sd = both.mean(axis=1, keepdims=True), both.std(axis=1, keepdims=True) + 1e-9
    # a person and the template singer differ most in timbre; lean on loudness,
    # voicing and the shape of the melody instead
    weight = np.full((X.shape[0], 1), 0.5)
    weight[0] = 1.0  # loudness (c0)
    weight[-2] = 2.0  # voicing
    weight[-1] = 3.0  # pitch
    # a singer following the guide never runs at more than twice or half its pace
    steps = np.array([[1, 1], [1, 2], [2, 1]])
    _, path = librosa.sequence.dtw(X=(X - mu) / sd * weight, Y=(Y - mu) / sd * weight, metric="euclidean",
                                   subseq=True, step_sizes_sigma=steps, weights_add=np.zeros(3), weights_mul=np.ones(3))
    path = path[::-1]

    xs, first = np.unique(path[:, 0], return_index=True)
    ys = np.array([path[path[:, 0] == x, 1].mean() for x in xs])  # the warp skips frames at a 2:1 step

    def to_take(t: float) -> int:
        i = float(np.clip((t - t0) * S.SR / S.HOP, 0, X.shape[1] - 1))
        return int(round((ta + float(np.interp(i, xs, ys)) * S.HOP) / S.SR / S.FRAME))

    return [(to_take(v0), to_take(v1), to_take(c1)) for _, v0, v1, c1, _, _ in line_knots]


def measure_sung(notes, knots, found, f0, band, active, lag: int, key: int, tempo: float):
    """One gesture per sung note, and each note's distance from the tune (cents)."""
    levels = np.array([np.median(band[v0 : max(v1, v0 + 1)]) for v0, v1, _ in found])
    gestures, off = [], []
    for k, (note, (_, T_v0, T_v1, _, _, _), (v0, v1, c1)) in enumerate(zip(notes, knots, found)):
        g = {}
        late = (v0 * S.FRAME - (T_v0 + lag * S.FRAME)) * tempo / 60.0
        # a quarter of a beat off is past anyone's phrasing: the alignment slipped, so don't count it
        g["early"] = -SUNG["timing"] * late if abs(late) <= 0.25 else float("nan")
        # held until the voice stops, or the next note starts
        nxt = found[k + 1][0] if k + 1 < len(found) else c1 + 40
        sounding = np.flatnonzero(active[v0 : max(nxt, v0 + 1)])
        release = v0 + (sounding[-1] + 1 if len(sounding) else 1)
        g["hold"] = float(np.clip((release - v0) * S.FRAME / max(note.dur, 1e-3), 0.6, 1.0))
        g["level"] = SUNG["level"] * (levels[k] - np.median(levels))
        n = max(v1 - v0, 4)
        g["swell"] = SUNG["swell"] * (np.mean(band[v0 + 3 * n // 4 : v0 + n]) - np.mean(band[v0 : v0 + n // 4 + 1]))
        voiced = np.flatnonzero(f0[v0:release] > 0)
        if len(voiced) >= 6:
            c = 1200 * np.log2(f0[v0:release][voiced] / 440.0) + 6900 - 100 * (note.pitch + key)
            keep = np.abs(c - np.median(c)) < 700  # a tracker's octave slips are not gestures
            c, where = c[keep], voiced[keep]
            middle = float(np.median(c))
            off.append(middle)
            if abs(middle) <= WRONG_NOTE and len(c) >= 6:
                r = c - middle
                q = lambda a, b: float(np.median(r[int(a * len(r)) : max(int(b * len(r)), int(a * len(r)) + 1)]))  # noqa: E731
                g["scoop"] = SUNG["scoop"] * float(np.mean(r[:3]))
                g["bend"] = SUNG["bend"] * (q(0.7, 0.9) - q(0.2, 0.4))
                g["fall"] = SUNG["fall"] * (float(np.mean(r[-3:])) - q(0.6, 0.8))
                if len(r) * S.FRAME >= 0.35:
                    smooth = np.convolve(r, np.ones(30) / 30, mode="same")
                    wobble = (r - smooth)[len(r) // 5 : -len(r) // 5 or None]
                    depth = float(np.sqrt(2) * np.std(wobble)) if len(wobble) > 20 else 0.0
                    g["vibrato"] = SUNG["vibrato"] * depth if depth >= 8.0 else 0.0
        gestures.append(P.Gesture(**{k2: float(v) for k2, v in g.items()}))
    return gestures, off


def sung_phrasing(genome_path: Path, genome, takes: list[str]):
    """Gestures from one or more sung takes of the guide."""
    from songbird.synth import voice as V

    notes = load_guide(genome_path.stem)
    tempo = choose_params(genome).tempo
    flat = V.VoiceParams(vibrato_depth=0.0, scoop=0.0, jitter=0.0, wander=0.0)
    segs = V.schedule(notes, flat, genome.lexicon)
    knots = S.target_knots(segs)
    lines = S.lines_of(notes)
    templates = {}  # the template singer in each key a take was sung in
    seen: dict[tuple[str, int], list[P.Gesture]] = defaultdict(list)
    portrait = []
    for path in takes:
        take = S.load(path)
        f0, band, active = analyze_take(take)
        lag = place_take(f0, active, knots, max(len(f0), int(notes[-1].start / S.FRAME) + 400))
        # the singer's octave or key: their median against the tune's, near each vowel
        guesses = []
        for (_, v0, v1, *_r), note in zip(knots, notes):
            a, b = int(v0 / S.FRAME) + lag, int(v1 / S.FRAME) + lag
            v = f0[max(a, 0) : max(b, 0)]
            v = v[v > 0]
            if len(v) >= 5:
                guesses.append(12 * np.log2(np.median(v) / 440) + 69 - note.pitch)
        key = int(np.round(np.median(guesses))) if guesses else 0
        if key not in templates:  # sing the template where the take was sung, so their spectra compare
            singer = replace(flat, shift=key, tract=1.0 if key <= -6 else 1.12)
            y_t = V.sing(notes, S.SR, singer, 0, genome.lexicon)
            templates[key] = (y_t, analyze_take(y_t)[0])
        found = []
        for line in lines:
            found += align_sung_line(take, f0, [notes[k] for k in line], [knots[k] for k in line], templates[key], lag)
        gestures, off = measure_sung(notes, knots, found, f0, band, active, lag, key, tempo)
        for note, g in zip(notes, gestures):
            seen[(note.phrase, index_in_phrase(notes, note))].append(g)
        portrait.append((path, lag * S.FRAME, key, gestures, off))
    return seen, portrait


def index_in_phrase(notes, note) -> int:
    """A note's place within its line (one sounding of its phrase)."""
    i = notes.index(note)
    j = i
    while j > 0 and not notes[j - 1].line_end:
        j -= 1
    return i - j


def describe(portrait, tempo: float) -> str:
    """A few plain sentences about how someone sang."""
    out = []
    for path, lag, key, gestures, off in portrait:
        ms = 60000.0 / tempo
        early = np.array([g.early for g in gestures if g.early == g.early]) * ms
        scoops = np.array([g.scoop for g in gestures if g.scoop])
        falls = np.array([g.fall for g in gestures if g.fall])
        vib = [g.vibrato for g in gestures if g.vibrato >= 0]
        where = "lined up with the guide" if lag == 0 else f"{lag:+.2f} s against the guide"
        pitch = {0: "in the guide's key", 12: "an octave up", -12: "an octave down"}.get(key, f"{key:+d} semitones from the guide")
        out.append(
            f"{Path(path).name}: {where}, {pitch}. "
            f"You land {abs(np.median(early)):.0f} ms {'behind' if np.median(early) < 0 else 'ahead of'} the beat on average "
            f"(spread {np.std(early):.0f} ms); {len(scoops)} of {len(gestures)} notes come in from off the note "
            f"(median {np.median(scoops) if len(scoops) else 0:+.0f} cents); falls median {np.median(falls) if len(falls) else 0:+.0f} cents; "
            f"vibrato on {sum(v > 0 for v in vib)} of {len(vib)} long notes; "
            f"{sum(abs(o) > WRONG_NOTE for o in off)} of {len(off)} notes more than {WRONG_NOTE:.0f} cents off the tune."
        )
    return "\n".join(out)


def write_guide(path: Path, genome, transpose: int) -> None:
    """The seed's own rendition as a WAV to sing along to, and the exact score
    it follows, which the sung-take extractor reads back."""
    import soundfile as sf

    from songbird import synth
    from songbird.synth import master

    params = choose_params(genome)
    params = replace(params, tonic=params.tonic + transpose)
    score = realize(genome, params)
    pcm = master.to_pcm16(master.master(synth.render(score, seed=params.seed), synth.SR), seed=params.seed)
    out = Path("renders") / "guide"
    out.mkdir(parents=True, exist_ok=True)
    wav = out / f"{path.stem}.guide.wav"
    sf.write(str(wav), pcm, synth.SR, subtype="PCM_16")
    (out / f"{path.stem}.guide.score.json").write_text(json.dumps(score.to_dict()) + "\n")
    first = min(n.start for n in score.part("voice"))
    print(f"{wav}  {len(pcm) / synth.SR:.0f} s, key tonic {params.tonic}, first word at {first:.1f} s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--speech", help="a recording of the script, read plainly")
    source.add_argument("--say", metavar="VOICE", help="read the script with a macOS voice instead")
    source.add_argument("--script", action="store_true", help="print the lines to read and stop")
    source.add_argument("--guide", action="store_true", help="write a backing track to sing along to, and stop")
    source.add_argument("--sung", nargs="+", metavar="TAKE", help="one or more takes sung along to the guide")
    ap.add_argument("--transpose", type=int, default=0, help="with --guide: move the song this many semitones to suit you")
    ap.add_argument("--name", help="who the phrasing came from, if they want it said (principle 12)")
    ap.add_argument("--out", help="output JSON (default renders/phrasing/<genome>.<source>.json)")
    args = ap.parse_args()

    genome = G.load(args.genome)
    if args.guide:
        write_guide(Path(args.genome), genome, args.transpose)
        return
    if args.sung:
        seen, portrait = sung_phrasing(Path(args.genome), genome, args.sung)
        phrasing = gather(genome, seen)
        who = args.name or "the singer"
        data = P.to_json(phrasing, source="song", source_detail=f"{len(args.sung)} sung take(s) by {who}", scale=SUNG)
        tag = Path(args.sung[0]).stem.split()[0].lower()
        write(data, phrasing, args.out or Path("renders") / "phrasing" / f"{Path(args.genome).stem}.{tag}.json")
        print(describe(portrait, choose_params(genome).tempo))
        return
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
    phrasing = gather(genome, seen)
    who = args.name or (f"{args.say} (macOS say)" if args.say else "a reader")
    data = P.to_json(phrasing, source="speech", source_detail=f"a reading by {who}", scale=SPEECH, limit=SPEECH_LIMIT)
    tag = (args.say or Path(args.speech).stem).split()[0].lower()
    write(data, phrasing, args.out or Path("renders") / "phrasing" / f"{Path(args.genome).stem}.{tag}.json")


def gather(genome, seen) -> P.Phrasing:
    """One gesture per note of every phrase anyone sang, averaged over every sighting."""
    phrasing = {}
    for pid, phrase in genome.phrases.items():
        count = len(phrase.sung)
        if any((pid, j) in seen for j in range(count)):
            phrasing[pid] = tuple(P.average(seen[(pid, j)]) if (pid, j) in seen else P.Gesture() for j in range(count))
    return phrasing


def write(data: dict, phrasing: P.Phrasing, out) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1) + "\n")
    rows = [g for gs in phrasing.values() for g in gs]
    print(f"{out}: {len(rows)} notes in {len(phrasing)} phrases; "
          f"timing spread {np.std([g.early for g in rows]):.3f} beats, level spread {np.std([g.level for g in rows]):.1f} dB, "
          f"falls {np.mean([g.fall for g in rows]):+.0f} cents on average")


if __name__ == "__main__":
    main()
