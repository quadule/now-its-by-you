"""A person's phrasing, taken from a sung take or a plain reading (dev-only).

    uv run python tools/phrasing.py songs/h-now-its-by-you.json --guide     # a backing track to sing along to
    uv run python tools/phrasing.py songs/h-now-its-by-you.json --singer Milo      # every take they kept
    uv run python tools/phrasing.py songs/h-now-its-by-you.json --sung recordings/milo/h-now-its-by-you-*.wav
    uv run python tools/phrasing.py songs/h-now-its-by-you.json --speech recordings/h-reading.m4a
    uv run python tools/phrasing.py songs/h-now-its-by-you.json --say Daniel
    uv run songbird render songs/h-now-its-by-you.json --phrasing renders/phrasing/h-now-its-by-you.milo.json

Sung takes. Someone sings along to the guide (--guide) on headphones, usually
through tools/karaoke.py, which keeps each singer's takes apart
(tools/takes.py). The take is placed against the guide it was sung to (by
cross-correlating where they sing with where the song has singing, unless it
already lines up), found an octave or key if they sang in their own, and
aligned line by line by warping the tune onto the pitch they sang; each
vowel's start is then found where its loudness climbs out of the consonant
before it, less the bias measured for that consonant (ONSET_BIAS). Where the
Montreal Forced Aligner is installed (tools/align.py), its vowel starts lead
and these are the fallback: it reads consonants against vowels far better,
and its own timing shows where it has lost its place. Each note
is measured against the template singer singing the same notes: how early or
late its vowel lands against the beat, how long it's held, its level and
swell (against the same vowel elsewhere), how the pitch scoops in, bends and
falls off, and the depth of any vibrato. Wrong notes are fine: pitch
gestures are measured around the note the singer actually sang, and skipped
where that was far from the tune. Each take is measured once, raw, into
renders/measured/ (until the take, its guide, the measuring code or the
aligner changes).

A phrasing is made from those measurements: scaled as a phrasing keeps them
(SUNG), and learned as the singer's rules for notes like each one (on the
downbeat or not, reached by a leap or a step, long or short, at the end of
a line...), each note keeping its own way only as far as the evidence for it
goes (ruled, shrunk). Some of what the extractor gets wrong
repeats in every take by the same voice (REPEATS), so more takes by one
person only go so far; other people's takes go further, and several singers'
takes make everyone's way at once, each person counting once. How well all
this works, checked against reference singers whose every gesture is known:
docs/PHRASING-CALIBRATION.md.

Readings. The reading is aligned the way tools/speech_to_song.py aligns it, then every
syllable is measured against its note: where it falls in its line compared
with where the tune puts it, how long it lasts, how loud it is and whether it
grows or fades, and how its pitch moves into, through and out of it. Speech
isn't singing, so each measurement is scaled down (SPEECH) before it becomes
a gesture: the speaker's rhythm and emphasis lean on the tune rather than
replace it. Each note of the tune gets one gesture, averaged over every word
sung to it, rounded (songbird.phrasing), and written to renders/phrasing/.
Nothing of the voice is kept.

Either way, every note of the tune gets one gesture, from each time it comes
round (and every take), and a short portrait of the phrasing is printed.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import inspect
import json
import os
import sys
import warnings
from collections import defaultdict
from dataclasses import astuple, dataclass, field, fields, replace
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import align as A  # noqa: E402
import speech_to_song as S  # noqa: E402
import takes as K  # noqa: E402

from faster_whisper import WhisperModel  # noqa: E402

from songbird import genome as G  # noqa: E402
from songbird import phonetics as ph  # noqa: E402
from songbird import phrasing as P  # noqa: E402
from songbird.realize import choose_params, realize  # noqa: E402
from songbird.synth import voice as V  # noqa: E402

ROOT = Path(__file__).parent.parent
MEASURED = ROOT / "renders" / "measured"

# How much of each spoken measurement a singer keeps, and how far it may go.
# Speech rhythm, emphasis and intonation don't follow a tune; leaning on them
# harder than this pushed syllables off the beat, weakened weak words and
# swooped the pitch, and cost words (H, formant voice: 18% misheard -> 26%).
SPEECH = dict(timing=0.15, level=0.3, swell=0.3, scoop=0.15, bend=0.1, fall=0.2)
SPEECH_LIMIT = dict(early=0.1, level=(-4.0, 4.0), cents=60.0)
# A sung take is phrasing already; keep nearly all of it. Checked against reference singers
# (tools/phrasing_eval.py --reference): vibrato reads at about 0.57 of its size, so it's scaled back
# up. Swell read poorly on the robotic references, but a person's held notes fade the same way take
# after take (Milo: -7 to -9 dB by the end of a long note, both takes), so it's kept.
SUNG = dict(timing=1.0, level=0.8, swell=1.0, scoop=0.8, bend=0.8, fall=0.8, vibrato=1.75, tune=1.0)
# The extractor's error that repeats in every take of one voice at one place in the song (its timbre,
# its way with those consonants), as a standard deviation in the extractor's units: more takes by the
# same person can't average it away, only other words on the same note or other people. Measured on
# reference singers (say-daniel, elevenlabs-george, elevenlabs-matilda); the same within a tenth on
# gemini-kore and the formant singer.
REPEATS = P.Gesture(early=0.048, hold=0.08, level=2.6, swell=3.0, scoop=50.0, bend=13.0, fall=23.0, vibrato=6.0, tune=15.0)
WRONG_NOTE = 150.0  # cents from the tune beyond which a note's pitch gestures aren't trusted
# the template singer: the machine's own schedule and tune, without any habits of its own
FLAT = V.VoiceParams(vibrato_depth=0.0, scoop=0.0, jitter=0.0, wander=0.0, spread=0.0)
NAN = float("nan")
# Where the aligner puts a vowel's start against where it began (seconds; negative is early), by what comes
# before the vowel, taken back off every take. Measured on natural voices (Seed-VC re-voicing planted takes as
# two Eleven Music singers, 6 takes, 1566 vowels; tools/phrasing_eval.py --reference seedvc-... --onsets): all
# within 15 ms. Robotic references (WORLD speech moved onto the tune) had glides and nasals found 20 to 35 ms
# early, and correcting natural voices by those put their vowels as late: a shared error that passed for
# shared timing.
ONSET_BIAS = {"affricate": 0.014, "aspirate": -0.012, "fricative": 0.009, "fricative+v": 0.004, "glide+v": 0.003,
              "liquid+v": -0.008, "nasal+v": 0.008, "stop": 0.007, "stop+v": 0.001, "vowel": 0.007}


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


@functools.cache
def version() -> str:
    """What a measurement depends on: the functions that measure, the template singer and its phonetics.
    Anything else in this file (how a phrasing is made from measurements) can change without measuring again."""
    h = hashlib.sha256()
    for name in MEASURING:
        h.update(inspect.getsource(globals()[name]).encode())
    for fn in (S.load, S.tracks, S.target_knots, S.lines_of, A.plausible, A.combine):
        h.update(inspect.getsource(fn).encode())
    h.update(repr((WRONG_NOTE, FLAT, ONSET_BIAS, A.MFA_BIAS, A.GATE, S.FRAME, S.SR)).encode())
    for f in (ROOT / "songbird" / "synth" / "voice.py", ROOT / "songbird" / "phonetics.py"):
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


@dataclass
class Guide:
    """The guide someone sang along to, exactly as it was rendered."""

    digest: str
    notes: list  # its voice notes, in order
    knots: list  # the template singer's (onset, vowel start, vowel end, coda end, vowel, coda) for each
    lines: list  # note indices, line by line
    tempo: float
    lexicon: dict
    before: list  # what each vowel comes after: a consonant's manner (+v if voiced), or "vowel"
    templates: dict = field(default_factory=dict)  # key -> the template singer's analysis in that key


_guides: dict[str, Guide] = {}


def guide(genome_path: Path, genome, digest: str | None = None) -> Guide:
    """The guide a take was sung to, as kept beside the takes, or else the current one."""
    from songbird.score import Note

    path = K.guide_score(genome_path.stem, digest) or ROOT / "renders" / "guide" / f"{genome_path.stem}.guide.score.json"
    if not path.exists():
        raise SystemExit(f"no guide at {path}: write one with --guide and sing along to that")
    d = K.digest(path)
    if d not in _guides:
        data = json.loads(path.read_text())
        notes = sorted((Note(**{**n, "gesture": None}) for n in data["notes"] if n["part"] == "voice"), key=lambda n: n.start)
        lexicon = data.get("lexicon") or genome.lexicon
        segs = V.schedule(notes, FLAT, lexicon)
        before = []
        for i, seg in enumerate(segs):
            if seg.role == "vowel":
                c = segs[i - 1].phone if i and segs[i - 1].role == "onset" else None
                before.append("vowel" if c is None else ph.CONSONANTS[c][0] + ("+v" if ph.CONSONANTS[c][2] else ""))
        tempo = data.get("tempo") or choose_params(genome).tempo
        _guides[d] = Guide(d, notes, S.target_knots(segs), S.lines_of(notes), tempo, lexicon, before)
    return _guides[d]


def template(g: Guide, key: int):
    """The template singer's f0, loudness and activity, singing the guide in a take's key."""
    if key not in g.templates:
        cache = MEASURED / "templates" / f"{g.digest}.{key:+d}.{version()}.npz"
        if cache.exists():
            z = np.load(cache)
            g.templates[key] = (z["f0"], z["band"], z["active"])
        else:  # sung where the take was sung, so their spectra compare
            singer = replace(FLAT, shift=key, tract=1.0 if key <= -6 else 1.12)
            f0, band, active = g.templates[key] = analyze_take(V.sing(g.notes, S.SR, singer, 0, g.lexicon))
            cache.parent.mkdir(parents=True, exist_ok=True)
            part = cache.with_name(f"{cache.stem}.{os.getpid()}.part.npz")  # whole or not at all, if two measure at once
            np.savez_compressed(part, f0=f0, band=band, active=active)
            os.replace(part, cache)
    return g.templates[key]


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


def next_sound(knots, spans, k: int) -> int:
    """The frame where the syllable after note k begins: its vowel less its consonants as the template sings them."""
    if k + 1 >= len(spans):
        return spans[k][1] + 40
    on, v0 = knots[k + 1][0], knots[k + 1][1]
    return max(spans[k + 1][0] - int(round((v0 - on) / S.FRAME)), spans[k][0] + 1)


def note_spans(knots, active, band, found=None):
    """(vowel start, vowel end, release) in frames for every note: where the
    alignment found them in a take, or where the schedule put them in the
    template. A note is held until the voice falls 20 dB below its vowel or
    the next syllable's first sound (its consonants, as long as the template
    sings them, before its vowel) begins; a room's reverberation and hiss don't count."""
    spans = found or [(int(round(v0 / S.FRAME)), int(round(v1 / S.FRAME)), 0) for _, v0, v1, _, _, _ in knots]
    out = []
    for k, (v0, v1, _) in enumerate(spans):
        nxt = next_sound(knots, spans, k)
        floor = np.median(band[v0 : max(v1, v0 + 1)]) - 20.0
        sounding = np.flatnonzero(active[v0 : max(nxt, v0 + 1)] & (band[v0 : max(nxt, v0 + 1)] >= floor))
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
        # too little of the shape heard (the voice unvoiced where it moves most) and its size is a guess
        if ok.sum() < 4 or np.dot(shape[ok], shape[ok]) < 0.25 * np.dot(shape, shape):
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


def vowel_onsets(found, band, f0=None):
    """Move each note's start from where its pitch arrived to where its vowel
    began: the loudness climbing back out of the consonant before it. Someone
    who slides up into a note starts it on time and scoops; judged by pitch
    alone they would seem late. Notes with no clear trough keep their place.
    A vowel is voiced: given f0, a start in the breath or a voiceless
    consonant before a line moves on to where the voice has pitch."""
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
        if f0 is not None and f0[min(start, len(f0) - 1)] <= 0:
            voiced = np.flatnonzero(f0[start : max(v0 + 10, start + 1)] > 0)
            start = start + int(voiced[0]) if len(voiced) else start
        out.append((start, max(v1, start + 2), max(c1, start + 2)))
        floor = start + 16  # the next vowel starts at least 80 ms later
    return out


def with_aligner(found, heard: dict, g: Guide, lag: int):
    """Each note's vowel start where the forced aligner heard it (tools/align.py): wherever its own timing
    looks like singing of the tune or it agrees with ours, less its bias; ours elsewhere, and wherever its
    start would come within 40 ms of the note before. Where ours was far off (it had lost its place in the
    line) or ended the vowel before the aligner starts it, the vowel ends where the aligner ends it too.
    Returns the spans and which notes are the aligner's."""
    ours = np.array([v0 for v0, _, _ in found]) * S.FRAME - lag * S.FRAME  # on the guide's timeline
    onset, use = A.combine(ours, heard, g.notes, g.before)
    out, used, last = [], [], -(10**9)
    for k, ((v0, v1, c1), t, mfa, end) in enumerate(zip(found, onset, use, heard["vowel_end"])):
        start = int(round(t / S.FRAME)) + lag
        mfa = bool(mfa) and start > last + 8
        if mfa:
            if end is not None and (abs(t - ours[k]) > A.GATE or v1 < start + 8):
                v1 = int(round(end / S.FRAME)) + lag
            v0 = start
        out.append((v0, max(v1, v0 + 2), max(c1, v0 + 2)))
        used.append(mfa)
        last = v0
    return out, used


def by_vowel(x: np.ndarray, vowels: list[str], keep: bool = False) -> np.ndarray:
    """Each value less the median of its vowel's (or of all, for a vowel sung fewer than three times).
    keep: add the median over everything back, so what every note shares (a singer's habit) stays."""
    out = x - np.median(x)
    for v in set(vowels):
        idx = [i for i, w in enumerate(vowels) if w == v]
        if len(idx) >= 3:
            out[idx] = x[idx] - np.median(x[idx])
    return out + (np.median(x) if keep else 0.0)


def measure_sung(notes, knots, found, take, template, lag: int, key: int, tempo: float):
    """One raw gesture per sung note (nothing scaled, rounded or clipped yet),
    and each note's distance from the tune in cents (NaN if it couldn't tell).

    Everything is measured twice, on the take and on the template singer
    singing the same notes in the same key, and a gesture is the difference:
    what the person did that the machine wouldn't have done anyway (its glides
    between notes, its louder high notes, its breath at line ends). A pitch
    gesture that couldn't be measured (a wrong note, too little voiced) is NaN,
    so averages skip it rather than count it as none."""
    f0, band, active = take
    f0_t, band_t, active_t = template
    spans = note_spans(knots, active, band, found)
    spans_t = note_spans(knots, active_t, band_t)

    def swell(b, v0, v1):
        n = max(v1 - v0, 4)
        return float(np.mean(b[v0 + 3 * n // 4 : v0 + n]) - np.mean(b[v0 : v0 + n // 4 + 1]))

    # Loudness in the vowel band depends on the vowel and on the voice (where a person's formants sit
    # against the machine's), so each note's level and swell are taken against the same vowel's
    # elsewhere in the take: what's left is how the person leaned on that note.
    vowels = [kn[4].phone for kn in knots]
    level = np.array([np.median(band[v0:v1]) - np.median(band_t[t0:t1]) for (v0, v1, _), (t0, t1, _) in zip(spans, spans_t)])
    swells = np.array([swell(band, v0, v1) - swell(band_t, t0, t1) for (v0, v1, _), (t0, t1, _) in zip(spans, spans_t)])
    # a singer who fades every held note more than the machine does keeps that: only the vowel's own part goes
    level, swells = by_vowel(level, vowels), by_vowel(swells, vowels, keep=True)

    gestures, off = [], []
    for k, (note, (_, T_v0, *_r), (v0, v1, release), (t0, t1, release_t)) in enumerate(zip(notes, knots, spans, spans_t)):
        g = dict(scoop=NAN, bend=NAN, fall=NAN, vibrato=NAN)
        late = (v0 * S.FRAME - (T_v0 + lag * S.FRAME)) * tempo / 60.0
        # a quarter of a beat off is past anyone's phrasing: the alignment slipped, so don't count it
        g["early"] = -late if abs(late) <= 0.25 else NAN
        # detached: a gap of silence before the next note, where the machine would have sung on
        nxt = next_sound(knots, spans, k) if k + 1 < len(spans) else None
        if nxt is not None and (nxt - release) * S.FRAME >= 0.04 and not note.line_end:
            nominal = T_v0 / S.FRAME + lag
            g["hold"] = float(np.clip((release - nominal) / max(release_t - T_v0 / S.FRAME, 1.0), 0.6, 1.0))
        elif note.line_end:
            g["hold"] = float(np.clip((release - (T_v0 / S.FRAME + lag)) / max(release_t - T_v0 / S.FRAME, 1.0), 0.6, 1.0))
        g["level"] = level[k]
        g["swell"] = swells[k]
        c = contour(f0, v0, v1, note.pitch + key)  # the vowel only: its consonants belong to their neighbours
        middle = NAN
        if np.isfinite(c).sum() >= 6:
            middle = float(np.nanmedian(c))
            c_t = contour(f0_t, max(t0 - 5, 0), t1 + 5, note.pitch + key)  # a little either side, to slide against
            if abs(middle) <= WRONG_NOTE and np.isfinite(c_t).sum() >= 6:
                g.update(shapes(c, c_t, (t1 - t0) * S.FRAME))
                depth, depth_t = wobble(c), wobble(c_t[5:-5])
                if depth is not None and depth_t is not None:  # beyond the machine's own settling wobble
                    extra = float(np.sqrt(max(depth**2 - depth_t**2, 0.0)))
                    g["vibrato"] = extra if extra >= 8.0 else 0.0
        off.append(middle)
        gestures.append(P.Gesture(**{k2: float(v) for k2, v in g.items()}))
    return gestures, off


def find_key(f0, g: Guide, lag: int) -> int:
    """The singer's octave or key: their median pitch against the tune's, near each vowel."""
    guesses = []
    for (_, v0, v1, *_r), note in zip(g.knots, g.notes):
        a, b = int(v0 / S.FRAME) + lag, int(v1 / S.FRAME) + lag
        v = f0[max(a, 0) : max(b, 0)]
        v = v[v > 0]
        if len(v) >= 5:
            guesses.append(12 * np.log2(np.median(v) / 440) + 69 - note.pitch)
    return int(np.round(np.median(guesses))) if guesses else 0


def measure_take(path: Path, g: Guide) -> dict:
    """Every note of the guide as one take sang it: its raw gesture, where its
    vowel began, and how far from the tune it was."""
    f0, band, active = analyze_take(S.load(path))
    lag = place_take(f0, active, g.knots, max(len(f0), int(g.notes[-1].start / S.FRAME) + 400))
    key = find_key(f0, g, lag)
    found = []
    for line in g.lines:
        found += align_by_pitch(f0, band, [g.notes[k] for k in line], [g.knots[k] for k in line], lag, key)
    found = vowel_onsets(found, band, f0)
    shift = [int(round(ONSET_BIAS.get(b, 0.0) / S.FRAME)) for b in g.before]
    found = [(v0 - d, max(v1, v0 - d + 2), max(c1, v0 - d + 2)) for (v0, v1, c1), d in zip(found, shift)]
    heard = A.aligned(path, g, lag * S.FRAME)  # None without MFA: our own onsets alone
    if heard is not None:
        found, used = with_aligner(found, heard, g, lag)
    gestures, off = measure_sung(g.notes, g.knots, found, (f0, band, active), template(g, key), lag, key, g.tempo)
    return {
        "lag": lag * S.FRAME,
        "key": key,
        "aligner": None if heard is None else {"mfa": heard["key"]["mfa"], "lowered": heard["lowered"],
                                               "onsets": int(sum(used))},
        "fields": [f.name for f in fields(P.Gesture)],
        "notes": [{"phrase": n.phrase, "index": index_in_phrase(g.notes, k), "start": round(n.start, 4),
                   "onset": round(v0 * S.FRAME, 4), "off": rounded(o, 1),
                   "gesture": [rounded(v, 4) for v in astuple(ge)]}
                  for k, (n, (v0, _v1, _c1), ge, o) in enumerate(zip(g.notes, found, gestures, off))],
    }


def rounded(v: float, digits: int) -> float | None:
    """A number for JSON, which has no NaN."""
    return None if np.isnan(v) else round(float(v), digits)


def measured(genome_path: Path, genome, take) -> dict:
    """A take (a kept take or a path) measured once and kept in renders/measured/
    until the take, the guide it was sung to or this extractor changes."""
    if not isinstance(take, K.Take):  # a reference take: the guide it followed is written beside it
        path = Path(take).resolve()
        about = [path.with_suffix(".truth.json"), path.with_suffix(".json")]
        pinned = next((json.loads(f.read_text()).get("guide") for f in about if f.exists()), None)
        take = K.Take(path, "", genome_path.stem, pinned)
    g = guide(genome_path, genome, take.guide)
    stat = take.path.stat()
    stamp = {"guide": g.digest, "extractor": version(), "aligner": A.fingerprint(), "bytes": stat.st_size,
             "mtime": int(stat.st_mtime)}
    name = take.path.relative_to(ROOT).as_posix() if take.path.is_relative_to(ROOT) else take.path.as_posix().lstrip("/")
    cache = MEASURED / (name.replace("/", "__").removesuffix(".wav") + ".json")
    if cache.exists():
        data = json.loads(cache.read_text())
        if data.get("stamp") == stamp:
            return data
    data = {"take": name, "stamp": stamp, **measure_take(take.path, g)}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data) + "\n")
    return data


def gestures_of(data: dict) -> list[P.Gesture]:
    """A measured take's raw gestures, NaN where a field wasn't measured. A note's tune is where its
    vowel sat against the tune (off), less where the whole take sat: someone singing a little flat all
    through leans on no note; wrong notes (off by more than WRONG_NOTE) aren't intonation."""
    offs = np.array([NAN if n["off"] is None else n["off"] for n in data["notes"]], dtype=float)
    fine = np.abs(offs) <= WRONG_NOTE
    centre = float(np.median(offs[fine])) if fine.any() else 0.0
    out = []
    for n, off, ok in zip(data["notes"], offs, fine):
        g = {f: NAN if v is None else v for f, v in zip(data["fields"], n["gesture"])}
        g["tune"] = off - centre if ok else NAN
        out.append(P.Gesture(**g))
    return out


def scaled(g: P.Gesture, s: dict) -> P.Gesture:
    """A raw measurement, as much of it as a phrasing keeps."""
    return replace(g, early=g.early * s["timing"], level=g.level * s["level"], swell=g.swell * s["swell"],
                   scoop=g.scoop * s["scoop"], bend=g.bend * s["bend"], fall=g.fall * s["fall"],
                   vibrato=g.vibrato * s["vibrato"] if g.vibrato >= 0 else g.vibrato, tune=g.tune * s.get("tune", 1.0))


def bounded(g: P.Gesture) -> P.Gesture:
    """A sighting within a phrasing's bounds, so one wild reading can't drag a note's average; NaN stays unmeasured."""
    return P.Gesture(*[v if np.isnan(v) else min(max(v, lo), hi) for v, lo, hi in zip(astuple(g), astuple(P.LOW), astuple(P.HIGH))])


def sung_phrasing(genome_path: Path, genome, takes):
    """Gestures from one or more sung takes (paths, or kept takes): every
    sighting of every note of the tune, scaled as a phrasing keeps them, what
    each was sung to, and a portrait of each take."""
    seen: dict[tuple[str, int], list[P.Gesture]] = defaultdict(list)
    words: dict[tuple[str, int], list[str]] = defaultdict(list)  # who sang it to what: singer|syllable
    weights: dict[tuple[str, int], list[float]] = defaultdict(list)
    who = [t.who if isinstance(t, K.Take) else "" for t in takes]
    portrait = []
    for take, singer in zip(takes, who):
        data = measured(genome_path, genome, take)
        gestures = gestures_of(data)
        sung_to = guide(genome_path, genome, data["stamp"]["guide"]).notes
        for n, note, ge in zip(data["notes"], sung_to, gestures):
            key = (n["phrase"], n["index"])
            seen[key].append(bounded(scaled(ge, SUNG)))
            words[key].append(f"{singer}|{(note.syllable or '').lower()}")
            weights[key].append(1.0 / who.count(singer))  # each person counts once
        portrait.append((data["take"], data["lag"], data["key"], gestures, [n["off"] for n in data["notes"]]))
    return seen, (words, weights), portrait


def components(groups: list[np.ndarray]) -> tuple[float, float]:
    """How much notes differ from one another, and how much one note's sightings
    differ among themselves (variances; one-way random effects). Can't tell: (0, 1)."""
    many = [x[np.isfinite(x)] for x in groups]
    many = [x for x in many if len(x) >= 2]
    if len(many) < 5:
        return 0.0, 1.0
    within = sum(((x - x.mean()) ** 2).sum() for x in many) / sum(len(x) - 1 for x in many)
    between = np.var([x.mean() for x in many], ddof=1) - within / np.mean([len(x) for x in many])
    return max(float(between), 0.0), float(within)


def shrunk(seen: dict, contexts: dict | None = None, floor: P.Gesture | None = None, weights: dict | None = None,
           prior: dict | None = None) -> dict:
    """Every note's sightings as one gesture, each field pulled toward the
    singer's habit (their mean over every note) as far as the evidence for
    that note's own way goes. A note's mean is off by the noise of each
    sighting, which more sightings average away, and by what the extractor
    gets wrong at that place every time (floor, a standard deviation per
    field), which only other words (contexts: what was sung, sighting by
    sighting) or other people average away. A note heard once takes mostly
    the habit; one heard often, to several words, keeps its own way. How far
    notes truly differ from one another is what's left of their spread once
    both errors are taken off. weights: how much each sighting counts (so
    that each person counts once, however many takes they sang). prior:
    what to pull each note toward instead of the habit, field by field
    (the singer's rules for notes like it: ruled()). Vibrato keeps its
    vote (P.average) unless a prior says otherwise."""
    names = [f.name for f in fields(P.Gesture) if f.name != "vibrato" or prior]
    floor = floor or P.Gesture(**dict.fromkeys([f.name for f in fields(P.Gesture)], 0.0))
    est: dict = {k: {} for k in seen}
    for name in names:
        bias = getattr(floor, name) ** 2
        values, words, counts = {}, {}, {}
        for k, v in seen.items():
            x = np.array([getattr(g, name) for g in v], dtype=float)
            ok = np.isfinite(x)
            values[k] = x[ok]
            words[k] = [w for w, good in zip(contexts[k], ok) if good] if contexts else list(range(ok.sum()))
            counts[k] = np.array(weights[k], dtype=float)[ok] if weights else np.ones(ok.sum())
        pooled = np.concatenate(list(values.values()))
        if not len(pooled):
            for k in seen:
                est[k][name] = NAN
            continue
        habit = float(np.average(pooled, weights=np.concatenate(list(counts.values()))))
        toward = {k: prior[k][name] if prior and k in prior else habit for k in seen}
        # noise: how the same note sung to the same word varies (another take, another time round)
        same = [values[k][[i for i, w in enumerate(words[k]) if w == word]] for k in values for word in set(words[k])]
        same = [x for x in same if len(x) >= 2]
        if same:
            noise = sum(((x - x.mean()) ** 2).sum() for x in same) / sum(len(x) - 1 for x in same)
        else:  # every note sung once to each word: its spread less what the extractor gets wrong
            many = [x for x in values.values() if len(x) >= 2]
            spread = sum(((x - x.mean()) ** 2).sum() for x in many) / max(sum(len(x) - 1 for x in many), 1)
            noise = max(spread - bias, 0.25 * spread)
        heard = [k for k in values if len(values[k])]
        mean = {k: float(np.average(values[k], weights=counts[k])) for k in heard}
        sightings = {k: counts[k].sum() ** 2 / (counts[k] ** 2).sum() for k in heard}  # as many as count equally
        error = {k: noise / sightings[k] + bias / len(set(words[k])) for k in heard}
        apart = np.array([mean[k] - toward[k] for k in heard])  # how far each note strays from what it's pulled toward
        spread = float(np.mean(apart**2)) if prior else float(np.var(apart, ddof=1)) if len(heard) > 1 else 0.0
        truly = max(spread - float(np.mean(list(error.values()))), 0.0) if len(heard) >= 5 else 0.0
        for k in seen:
            if k in error:
                trust = truly / (truly + error[k]) if truly > 0 else 0.0
                est[k][name] = toward[k] + trust * (mean[k] - toward[k])
            else:
                est[k][name] = toward[k]
    return {k: [P.Gesture(**{**est[k], **({} if "vibrato" in est[k] else {"vibrato": P.average(v).vibrato})})]
            for k, v in seen.items()}


def features(genome, key: tuple[str, int]) -> np.ndarray:
    """What a note of the tune is, as a singer might treat it: where it falls in its line and its bar,
    how long it is, and how it's reached and left (by leap or step, up or down)."""
    from songbird.theory import degree_semitones

    mode = choose_params(genome).mode
    m = genome.meter
    notes = genome.phrases[key[0]].sung
    k = key[1]
    n = notes[k]
    at = [degree_semitones(x.degree, mode, x.alter) for x in notes]
    into = at[k] - at[k - 1] if k else 0
    out = at[k + 1] - at[k] if k + 1 < len(notes) else 0
    beats = n.dur / m.beat
    return np.array([
        k == 0, k == len(notes) - 1, n.onset < 0,  # first, last, a pickup
        k / max(len(notes) - 1, 1),  # how far along the line: pushing on or easing off through it
        n.onset % m.bar == 0, n.onset % m.foot == 0,  # on the downbeat, on a stressed beat
        np.log2(max(beats, 0.25)), beats >= 1.5,  # how long; long enough to hold (index 7)
        into >= 3, 0 < into < 3, -3 < into < 0, into <= -3,  # reached by a leap or step up, a step or leap down
        out > 0, out < 0,  # left rising, left falling
    ], dtype=float)


def ruled(genome, seen: dict, contexts: dict | None = None, floor: P.Gesture | None = None,
          weights: dict | None = None, ridge: float = 4.0) -> dict:
    """Every note's gesture from a singer's rules as well as the note itself.

    A singer treats notes alike when they're alike: leans on downbeats, scoops
    into leaps, lets go at line ends, puts vibrato on long notes. For each
    field, a ridge regression on what each note is (features()) says what
    this singer does with notes like it, learned from every sighting of every
    note; each note is then pulled toward that rather than toward one habit
    for all, and keeps its own way only as far as the evidence goes (shrunk)."""
    keys = list(seen)
    X = np.array([features(genome, k) for k in keys])
    mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-9
    Z = (X - mu) / sd
    prior: dict = {k: {} for k in keys}
    for f in fields(P.Gesture):
        rows, ys, ws = [], [], []
        for i, k in enumerate(keys):
            for j, g in enumerate(seen[k]):
                v = getattr(g, f.name)
                if np.isfinite(v) and (f.name != "vibrato" or v >= 0):
                    rows.append(i)
                    ys.append(v)
                    ws.append(weights[k][j] if weights else 1.0)
        if len(ys) < 10:
            continue
        A, y, w = Z[rows], np.array(ys), np.array(ws)
        base = float(np.average(y, weights=w))
        beta = np.linalg.solve(A.T @ (A * w[:, None]) + ridge * np.eye(A.shape[1]), A.T @ (w * (y - base)))
        for i, k in enumerate(keys):
            prior[k][f.name] = base + float(Z[i] @ beta)
    prior = {k: v for k, v in prior.items() if v}
    made = shrunk(seen, contexts, floor, weights, prior)
    for k, v in made.items():
        # vibrato: where the singer was heard, their call (mostly none: leave it to the machine) with the
        # rules' depth; on a long note never heard held, the rules' depth; otherwise the machine's own
        judged = [g.vibrato for g in seen[k] if np.isfinite(g.vibrato)]
        left = judged and 2 * sum(x >= 0 for x in judged) <= len(judged)
        held = features(genome, k)[7] > 0
        depth = v[0].vibrato if np.isfinite(v[0].vibrato) else NAN
        vibrato = -1.0 if left or not (judged or held) or np.isnan(depth) else max(depth, 0.0)
        made[k] = [replace(v[0], vibrato=vibrato)]
    return made


def floor_for(scale: dict) -> P.Gesture:
    """REPEATS in the units of sightings scaled as a phrasing keeps them."""
    keys = dict(early="timing")
    return P.Gesture(**{f.name: getattr(REPEATS, f.name) * abs(scale.get(keys.get(f.name, f.name), 1.0))
                        for f in fields(P.Gesture)})


def singer_phrasing(genome_path: Path, genome, takes, credit: str | None = None):
    """A phrasing from sung takes, the JSON to keep, and a portrait: one
    singer's, or, given several singers' takes, everyone's at once, each
    person counting once and each voice's own errors averaging away."""
    seen, (words, weights), portrait = sung_phrasing(genome_path, genome, takes)
    phrasing = gather(genome, ruled(genome, seen, words, floor_for(SUNG), weights))
    detail = f"{len(takes)} sung take(s)" + (f" by {credit}" if credit else "")
    return phrasing, P.to_json(phrasing, source="song", source_detail=detail, scale=SUNG), portrait


def index_in_phrase(notes, k: int) -> int:
    """Note k's place within its line (one sounding of its phrase)."""
    j = k
    while j > 0 and not notes[j - 1].line_end:
        j -= 1
    return k - j


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
        off = [o for o in off if o is not None and np.isfinite(o)]
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
    (out / f"{path.stem}.guide.score.json").write_text(json.dumps({**score.to_dict(), "tempo": params.tempo}) + "\n")
    first = min(n.start for n in score.part("voice"))
    print(f"{wav}  {len(pcm) / synth.SR:.0f} s, key tonic {params.tonic}, first word at {first:.1f} s")


# everything a take's measurement depends on (version() hashes their source)
MEASURING = ("guide", "template", "analyze_take", "place_take", "next_sound", "note_spans", "contour", "fit_edge",
             "shapes", "wobble", "align_by_pitch", "vowel_onsets", "with_aligner", "by_vowel", "measure_sung", "find_key",
             "measure_take", "index_in_phrase", "rounded")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--speech", help="a recording of the script, read plainly")
    source.add_argument("--say", metavar="VOICE", help="read the script with a macOS voice instead")
    source.add_argument("--script", action="store_true", help="print the lines to read and stop")
    source.add_argument("--guide", action="store_true", help="write a backing track to sing along to, and stop")
    source.add_argument("--sung", nargs="+", metavar="TAKE", help="one or more takes sung along to the guide")
    source.add_argument("--singer", metavar="NAME", help="every take this singer kept in recordings/ (and marked to use)")
    ap.add_argument("--transpose", type=int, default=0, help="with --guide: move the song this many semitones to suit you")
    ap.add_argument("--name", help="who the phrasing came from, if they want it said (principle 12)")
    ap.add_argument("--out", help="output JSON (default renders/phrasing/<genome>.<source>.json)")
    args = ap.parse_args()

    genome = G.load(args.genome)
    if args.guide:
        write_guide(Path(args.genome), genome, args.transpose)
        return
    if args.sung or args.singer:
        stem = Path(args.genome).stem
        chosen = [t for t in K.takes(stem, K.slug(args.singer)) if t.use] if args.singer else args.sung
        if not chosen:
            raise SystemExit(f"no takes of {stem} by {args.singer} in recordings/{K.slug(args.singer)}/")
        phrasing, data, portrait = singer_phrasing(Path(args.genome), genome, chosen, args.name)
        tag = K.slug(args.singer) if args.singer else Path(args.sung[0]).stem.split()[0].lower()
        write(data, phrasing, args.out or ROOT / "renders" / "phrasing" / f"{stem}.{tag}.json")
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
