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


def note_spans(knots, active, found=None):
    """(vowel start, vowel end, release) in frames for every note: where the
    alignment found them in a take, or where the schedule put them in the
    template. A note is held until the voice stops or the next vowel starts."""
    spans = found or [(int(round(v0 / S.FRAME)), int(round(v1 / S.FRAME)), 0) for _, v0, v1, _, _, _ in knots]
    out = []
    for k, (v0, v1, _) in enumerate(spans):
        nxt = spans[k + 1][0] if k + 1 < len(spans) else v1 + 40
        sounding = np.flatnonzero(active[v0 : max(nxt, v0 + 1)])
        out.append((v0, max(v1, v0 + 1), v0 + (sounding[-1] + 1 if len(sounding) else 1)))
    return out


def contour(f0, a: int, b: int, target: float) -> np.ndarray:
    """Cents from the target note, frame by frame; NaN where unvoiced or where
    the tracker slipped an octave."""
    seg = f0[a:b]
    c = np.where(seg > 0, 1200 * np.log2(np.maximum(seg, 1.0) / 440.0) + 6900 - 100 * target, np.nan)
    if np.isfinite(c).any():
        c[np.abs(c - np.nanmedian(c)) > 700] = np.nan
    return c


def fit_edge(c, c_t, shape: np.ndarray, at_end: bool, reach: int = 5) -> float | None:
    """How much of a gesture shape (a scoop settling at a vowel's start, or a
    fall at its end) best explains how the take's pitch differs from the
    template's there, allowing either to sit up to reach frames (25 ms) off
    the other. Near a note's edges the machine is still gliding from or to its
    neighbours at several cents a millisecond, so without the shift a slip of
    a few milliseconds would pass for a gesture. None if too little is voiced."""
    w = len(shape)
    mine = c[-w:] if at_end else c[:w]
    best = None
    for shift in range(-reach, reach + 1):
        lo = len(c_t) - reach - w + shift if at_end else reach + shift
        theirs = c_t[lo : lo + w]
        if len(theirs) != w:
            continue
        ok = np.isfinite(mine) & np.isfinite(theirs)
        if ok.sum() < 4 or not np.any(shape[ok]):
            continue
        d, x = mine[ok] - theirs[ok], shape[ok]
        size = float(np.dot(d, x) / np.dot(x, x))
        err = float(np.sum((d - size * x) ** 2))
        if best is None or err < best[0]:
            best = (err, size)
    return None if best is None else best[1]


def shapes(c, c_t, dur: float) -> dict:
    """The pitch gestures by which one note's contour (cents, about its middle)
    differs from the template singer's: the same shapes the singer draws."""
    c = c - np.nanmedian(c)
    c_t = c_t - np.nanmedian(c_t)
    approach, letgo = min(0.12, 0.3 * dur), min(0.12, 0.35 * dur)
    w = max(int(round(max(approach, letgo) / S.FRAME)), 4)
    t = np.arange(w) * S.FRAME
    settle = 0.5 * (1 + np.cos(np.pi * np.clip(t / approach, 0.0, 1.0)))
    go = 0.5 * (1 - np.cos(np.pi * np.clip((t - (t[-1] - letgo)) / letgo, 0.0, 1.0)))
    inner = c_t[5:-5] if len(c_t) > 10 else c_t

    def q(r, a, b):
        part = r[int(a * len(r)) : max(int(b * len(r)), int(a * len(r)) + 1)]
        return float(np.nanmedian(part)) if np.isfinite(part).any() else 0.0

    out = {"bend": (q(c, 0.7, 0.9) - q(c, 0.2, 0.4)) - (q(inner, 0.7, 0.9) - q(inner, 0.2, 0.4))}
    for name, edge, at_end in (("scoop", settle, False), ("fall", go, True)):
        size = fit_edge(c, c_t, edge, at_end) if len(c) >= w else None
        if size is not None:
            out[name] = size
    return out


def wobble(c: np.ndarray) -> float | None:
    """Depth (cents) of the 4 to 8 Hz wobble in the second half of a held note,
    where vibrato lives; None if the note is too short to tell."""
    r = c[len(c) // 2 :]
    r = r[np.isfinite(r)]
    if len(r) * S.FRAME < 0.25:
        return None
    r = r - np.polyval(np.polyfit(np.arange(len(r)), r, 1), np.arange(len(r)))
    spectrum = np.fft.rfft(r * np.hanning(len(r)), 256)
    freqs = np.fft.rfftfreq(256, S.FRAME)
    band = (freqs >= 4.0) & (freqs <= 8.0)
    power = 2 * np.sum(np.abs(spectrum[band]) ** 2) / np.sum(np.hanning(len(r)) ** 2) / 256
    return float(np.sqrt(2 * power))


def align_by_pitch(f0, band, line_notes, line_knots, lag: int, key: int):
    """(vowel start, vowel end, release) in take frames for each note of one
    sung line, by warping the tune onto the pitch the person actually sang:
    their pitch moving from one note to the next is the anchor, their voice
    falling silent marks the rests, and the dip in loudness at each consonant
    separates syllables sung on one pitch. Timbre plays no part, so any voice
    through any microphone will do, and a wrong note costs no more than a few
    semitones' worth, so a line sung flat still lines up."""
    from scipy.ndimage import maximum_filter1d

    import librosa

    t0, t1 = line_knots[0][0] - 0.05, line_knots[-1][3] + 0.05
    a, b = int(t0 / S.FRAME), int(t1 / S.FRAME)
    ta, tb = max(a + lag - 70, 0), min(b + lag + 70, len(f0))  # 350 ms either side
    tune = np.full(b - a, np.nan)
    for note, (_, v0, v1, *_r) in zip(line_notes, line_knots):
        i0, i1 = max(int(v0 / S.FRAME) - a, 0), max(int(v1 / S.FRAME) - a, 0)
        tune[i0:i1] = note.pitch
    heard = f0[ta:tb]
    sung = np.where(heard > 0, 12 * np.log2(np.maximum(heard, 1.0) / 440.0) + 69 - key, np.nan)
    gap = np.abs((tune[:, None] - sung[None, :] + 6.0) % 12.0 - 6.0)  # octave-blind distance in semitones
    loud = band[ta:tb]
    dip = np.clip((maximum_filter1d(loud, 41) - loud) / 12.0, 0.0, 1.0)[None, :]  # 1 in a consonant's trough
    in_vowel = np.isfinite(tune)[:, None]
    cost = np.where(in_vowel,
                    np.where(np.isfinite(sung)[None, :], np.minimum(np.nan_to_num(gap, nan=3.0), 3.0) / 3.0, 0.8) + 0.25 * dip,
                    0.3 - 0.25 * dip)  # between vowels anything goes, a trough best
    steps = np.array([[1, 1], [1, 2], [2, 1]])
    _, path = librosa.sequence.dtw(C=cost, subseq=True, step_sizes_sigma=steps,
                                   weights_add=np.zeros(3), weights_mul=np.ones(3))
    path = path[::-1]
    xs = np.unique(path[:, 0])
    ys = np.array([path[path[:, 0] == x, 1].mean() for x in xs])

    def to_take(t: float) -> int:
        return int(round(ta + float(np.interp(t / S.FRAME - a, xs, ys))))

    return [(to_take(v0), to_take(v1), to_take(c1)) for _, v0, v1, c1, _, _ in line_knots]


def vowel_onsets(found, band):
    """Move each note's start from where its pitch arrived to where its vowel
    began: the loudness climbing back out of the consonant before it. Someone
    who slides up into a note starts it on time and scoops; judged by pitch
    alone they would seem late. Notes with no clear trough keep their place."""
    out, floor = [], 0
    for k, (v0, v1, c1) in enumerate(found):
        lo = max(v0 - 40, floor)  # up to 200 ms back, never into the last vowel
        hi = min(v0 + 10, len(band) - 1)
        if hi - lo < 6:
            out.append((v0, v1, c1))
            floor = v0 + 16
            continue
        m = lo + int(np.argmin(band[lo:hi]))
        peak = float(np.max(band[m : min(m + 40, len(band))]))
        if peak - band[m] >= 6.0:
            rise = np.flatnonzero(band[m : m + 40] >= band[m] + 0.6 * (peak - band[m]))
            start = m + int(rise[0]) if len(rise) else v0
        else:
            start = v0
        out.append((start, max(v1, start + 2), max(c1, start + 2)))
        floor = start + 16  # the next vowel starts at least 80 ms later
    return out


def measure_sung(notes, knots, found, take, template, lag: int, key: int, tempo: float):
    """One gesture per sung note, and each note's distance from the tune (cents).

    Everything is measured twice, on the take and on the template singer
    singing the same notes in the same key, and a gesture is the difference:
    what the person did that the machine wouldn't have done anyway (its glides
    between notes, its louder high notes, its breath at line ends)."""
    f0, band, active = take
    f0_t, band_t, active_t = template
    spans = note_spans(knots, active, found)
    spans_t = note_spans(knots, active_t)
    level = np.array([np.median(band[v0:v1]) for v0, v1, _ in spans])
    level_t = np.array([np.median(band_t[v0:v1]) for v0, v1, _ in spans_t])
    level, level_t = level - np.median(level), level_t - np.median(level_t)

    def swell(b, v0, v1):
        n = max(v1 - v0, 4)
        return float(np.mean(b[v0 + 3 * n // 4 : v0 + n]) - np.mean(b[v0 : v0 + n // 4 + 1]))

    gestures, off = [], []
    for k, (note, (_, T_v0, *_r), (v0, v1, release), (t0, t1, release_t)) in enumerate(zip(notes, knots, spans, spans_t)):
        g = {}
        late = (v0 * S.FRAME - (T_v0 + lag * S.FRAME)) * tempo / 60.0
        # a quarter of a beat off is past anyone's phrasing: the alignment slipped, so don't count it
        g["early"] = -SUNG["timing"] * late if abs(late) <= 0.25 else float("nan")
        # detached: a gap of silence before the next note, where the machine would have sung on
        nxt = spans[k + 1][0] if k + 1 < len(spans) else None
        if nxt is not None and (nxt - release) * S.FRAME >= 0.04 and not note.line_end:
            nominal = T_v0 / S.FRAME + lag
            g["hold"] = float(np.clip((release - nominal) / max(release_t - T_v0 / S.FRAME, 1.0), 0.6, 1.0))
        elif note.line_end:
            g["hold"] = float(np.clip((release - (T_v0 / S.FRAME + lag)) / max(release_t - T_v0 / S.FRAME, 1.0), 0.6, 1.0))
        g["level"] = SUNG["level"] * (level[k] - level_t[k])
        g["swell"] = SUNG["swell"] * (swell(band, v0, v1) - swell(band_t, t0, t1))
        c = contour(f0, v0, v1, note.pitch + key)  # the vowel only: its consonants belong to their neighbours
        if np.isfinite(c).sum() >= 6:
            middle = float(np.nanmedian(c))
            off.append(middle)
            c_t = contour(f0_t, max(t0 - 5, 0), t1 + 5, note.pitch + key)  # a little either side, to slide against
            if abs(middle) <= WRONG_NOTE and np.isfinite(c_t).sum() >= 6:
                for name, size in shapes(c, c_t, (t1 - t0) * S.FRAME).items():
                    g[name] = SUNG[name] * size
                depth, depth_t = wobble(c), wobble(c_t[5:-5])
                if depth is not None and depth_t is not None:  # beyond the machine's own settling wobble
                    extra = float(np.sqrt(max(depth**2 - depth_t**2, 0.0)))
                    g["vibrato"] = SUNG["vibrato"] * extra if extra >= 8.0 else 0.0
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
            templates[key] = (y_t, analyze_take(y_t))
        y_t, analysis_t = templates[key]
        found = []
        for line in lines:
            found += align_by_pitch(f0, band, [notes[k] for k in line], [knots[k] for k in line], lag, key)
        found = vowel_onsets(found, band)
        gestures, off = measure_sung(notes, knots, found, (f0, band, active), analysis_t, lag, key, tempo)
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


def way(values, down: str, up: str) -> str:
    """Which way most of some gestures go, as the end of a sentence."""
    if not len(values):
        return "."
    below = values[values < 0]
    above = values[values > 0]
    if len(below) >= 2 * len(above):
        return f", mostly {down} (typically {np.median(below):+.0f} cents)."
    if len(above) >= 2 * len(below):
        return f", mostly {up} (typically {np.median(above):+.0f} cents)."
    return f", both ways ({np.median(below):+.0f} and {np.median(above):+.0f} cents)."


def describe(portrait, tempo: float) -> str:
    """A few plain sentences about how someone sang."""
    out = []
    for path, lag, key, gestures, off in portrait:
        ms = 60000.0 / tempo
        early = np.array([g.early for g in gestures if g.early == g.early]) * ms
        scoops = np.array([g.scoop for g in gestures if abs(g.scoop) >= 20])
        falls = np.array([g.fall for g in gestures if abs(g.fall) >= 20])
        vib = [g.vibrato for g in gestures if g.vibrato >= 0]
        where = "lined up with the guide" if lag == 0 else f"{lag:+.2f} s against the guide"
        pitch = {0: "in the guide's key", 12: "an octave up", -12: "an octave down"}.get(key, f"{key:+d} semitones from the guide")
        lean = np.median(early) if len(early) else 0.0
        sentences = [
            f"{Path(path).name}: {where}, {pitch}.",
            f"You sit {abs(lean):.0f} ms {'behind' if lean < 0 else 'ahead of'} the beat on average, give or take {np.std(early) if len(early) else 0:.0f} ms.",
            f"You slide into {len(scoops)} of {len(gestures)} notes by 20 cents or more{way(scoops, 'from below', 'from above')}",
            f"You bend off the end of {len(falls)} notes{way(falls, 'down', 'up')}",
            f"Vibrato on {sum(v > 0 for v in vib)} of {len(vib)} long notes"
            + (f" (about {np.median([v for v in vib if v > 0]):.0f} cents deep)." if any(v > 0 for v in vib) else "."),
            f"{sum(abs(o) > WRONG_NOTE for o in off)} of {len(off)} notes were more than {WRONG_NOTE:.0f} cents from the tune"
            " (fine: their pitch gestures are left out).",
        ]
        out.append(" ".join(sentences))
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
