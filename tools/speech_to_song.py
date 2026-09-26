"""Sing with a real voice: spoken lyrics moved onto the tune. A probe; dev-only.

    uv run python tools/speech_to_song.py songs/h-now-its-by-you.json --script
    uv run python tools/speech_to_song.py songs/h-now-its-by-you.json --speech recordings/h.wav
    uv run python tools/speech_to_song.py songs/h-now-its-by-you.json --say "Zoe (Premium)"

Nobody has to sing. The speaker reads each different lyric line once, in
order, with a short pause after each (--script prints them). WORLD, a
classical vocoder with no neural network, splits the reading into pitch,
spectral envelope and aperiodicity. Every vowel is stretched to fill its note,
consonants are fitted to the formant singer's schedule, the spoken pitch is
replaced by the formant singer's own pitch track (scoops, glides, overshoot,
vibrato, drift), and loudness follows the score rather than the reading. The
voice is mixed and mastered like any render, and it and the formant singer
are both scored with Whisper the way tools/wer_suite.py does.

This is the cheap first test proposed after docs/VOICE-OPTIONS.md: does the
artist's own voice, pushed onto the tune by our puppeteer, sound like the
song? Lines are found with Whisper's word timestamps; inside a line every phoneme
is found by warping our own formant voice, speaking the same words, onto the
reading. A plain, clean reading works best. --say reads the lines with
a macOS system voice as a stand-in for a recording.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from scipy.ndimage import uniform_filter1d
from scipy.signal import resample_poly

warnings.filterwarnings("ignore", message="pkg_resources")
import pyworld  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from intelligibility import align, normalize  # noqa: E402
from wer_suite import score_sections  # noqa: E402

from songbird import genome as G  # noqa: E402
from songbird import phonetics as ph  # noqa: E402
from songbird import synth  # noqa: E402
from songbird.realize import choose_params, realize  # noqa: E402
from songbird.synth import master  # noqa: E402
from songbird.synth import voice as V  # noqa: E402
from songbird.theory import hz_to_midi  # noqa: E402

SR = synth.SR
FRAME = 0.005  # seconds per WORLD frame
PAUSE = 0.7  # seconds of silence --say leaves after each line


# --- the lyric, line by line ---------------------------------------------------


def lines_of(notes) -> list[list[int]]:
    """Indices of the sung notes, one list per lyric line."""
    lines, current = [], []
    for k, note in enumerate(notes):
        current.append(k)
        if note.line_end:
            lines.append(current)
            current = []
    return lines + ([current] if current else [])


def words_of_line(notes, line: list[int]) -> list[tuple[str, list[int]]]:
    """(word as written, its note indices) along one line."""
    words, i = [], 0
    while i < len(line):
        n = notes[line[i]].word_len
        words.append((notes[line[i]].word.replace("-", "").replace("*", ""), line[i : i + n]))
        i += n
    return words


def script(notes, lines) -> tuple[list[str], list[int]]:
    """The lines to read, each once, and which of them every sung line is."""
    texts, keys, which = [], [], []
    for line in lines:
        text = " ".join(w for w, _ in words_of_line(notes, line))
        key = " ".join(normalize(text))
        if key not in keys:
            texts.append(text)
            keys.append(key)
        which.append(keys.index(key))
    return texts, which


# --- the reading -----------------------------------------------------------------


def load(path) -> np.ndarray:
    try:
        y, sr = sf.read(str(path), always_2d=True)
        y = y.mean(axis=1)
    except sf.LibsndfileError:  # m4a from a phone's voice memos, say: let ffmpeg decode it
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "reading.wav"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", str(wav)], check=True)
            y, sr = sf.read(str(wav))
    return resample_poly(y, SR, sr) if sr != SR else y


def say(lines: list[str], voice: str) -> np.ndarray:
    """Read the lines aloud with a macOS voice, a pause after each."""
    parts = [np.zeros(int(0.3 * SR))]
    with tempfile.TemporaryDirectory() as tmp:
        for i, text in enumerate(lines):
            path = Path(tmp) / f"{i}.aiff"
            subprocess.run(["say", "-v", voice, "-o", str(path), text], check=True)
            parts += [load(path), np.zeros(int(PAUSE * SR))]
    return np.concatenate(parts)


def analyze(y: np.ndarray):
    """WORLD: f0, spectral envelope and aperiodicity every FRAME seconds."""
    x = np.ascontiguousarray(y, dtype=np.float64)
    f0, t = pyworld.harvest(x, SR, f0_floor=55.0, f0_ceil=800.0, frame_period=FRAME * 1000)
    return f0, pyworld.cheaptrick(x, f0, t, SR), pyworld.d4c(x, f0, t, SR)


def tracks(sp: np.ndarray):
    """Per frame: vowel-band level (dB, 300 Hz to 3 kHz) and whether anyone is speaking."""
    freqs = np.linspace(0.0, SR / 2, sp.shape[1])
    band = 10 * np.log10(sp[:, (freqs >= 300) & (freqs <= 3000)].sum(axis=1) + 1e-30)
    full = 10 * np.log10(sp.sum(axis=1) + 1e-30)
    return band, full > np.percentile(full, 99.5) - 50.0


def word_spans(model, y: np.ndarray, words: list[str]) -> list[tuple[float, float] | None]:
    """Where Whisper hears each expected word, in seconds; None where it heard something else."""
    audio = resample_poly(y, 16000, SR).astype(np.float32)
    segments, _ = model.transcribe(audio, language="en", beam_size=5, word_timestamps=True,
                                   condition_on_previous_text=False, vad_filter=False)
    heard = []
    for s in segments:
        for w in s.words:
            tokens = normalize(w.word)
            step = (w.end - w.start) / max(len(tokens), 1)
            heard += [(tok, w.start + i * step, w.start + (i + 1) * step) for i, tok in enumerate(tokens)]
    _, pairs = align(["".join(normalize(w)) for w in words], [h[0] for h in heard])
    spans: list = [None] * len(words)
    i = j = 0
    for r, h in pairs:
        if r and r == h:
            spans[i] = heard[j][1:]
        i, j = i + bool(r), j + bool(h)
    return spans


LINE_GAP = 60  # frames of quiet (300 ms) that may separate two lines of the reading
SPLIT = 20  # frames of quiet (100 ms) that split a line into pieces aligned on their own
HOP = 220  # samples per alignment frame, about 5 ms


def stretches(active, lo: int, hi: int, gap: int) -> list[tuple[int, int]]:
    """Runs of speech between frames lo and hi, split wherever it pauses for gap frames or more."""
    on = lo + np.flatnonzero(active[lo:hi])
    if not len(on):
        return []
    edges = np.flatnonzero(np.diff(on) > gap)
    runs = list(zip([on[0]] + [on[e + 1] for e in edges], [on[e] + 1 for e in edges] + [on[-1] + 1]))
    return [(a, b) for a, b in runs if b - a >= 8] or runs  # drop clicks


def align_reading(model, reading, world, band, active, texts, first_of, notes, lexicon, midi) -> list[list[tuple]]:
    """Knots for every syllable of every spoken line. The reading is cut at
    its pauses; the words Whisper hears say which line each stretch belongs to."""
    words, weights, owner = [], [], []
    for li in range(len(texts)):
        for word, idx in words_of_line(notes, first_of[li]):
            words += [word]
            weights += [len(idx)]
            owner += [li]
    spans = word_spans(model, reading, words)
    if all(s is None for s in spans):
        raise SystemExit("Whisper heard none of the lyric in the reading")

    runs = stretches(active, 0, len(active), LINE_GAP)
    votes = [[owner[m] for m, s in enumerate(spans) if s is not None and a <= (s[0] + s[1]) / 2 / FRAME < b]
             for a, b in runs]
    label = [max(set(v), key=v.count) if v else None for v in votes]
    # a stretch nobody's words landed in is the next line Whisper missed, if any, or part of its neighbour
    for r, lab in enumerate(label):
        if lab is None:
            prev = next((label[q] for q in range(r - 1, -1, -1) if label[q] is not None), -1)
            nxt = next((label[q] for q in range(r + 1, len(label)) if label[q] is not None), len(texts))
            label[r] = prev + 1 if nxt - prev > 1 else max(prev, 0)
    label = list(np.maximum.accumulate(label))
    windows: dict[int, list[int]] = {}
    for (a, b), lab in zip(runs, label):
        w = windows.setdefault(lab, [a, b])
        w[0], w[1] = min(w[0], a), max(w[1], b)

    knots = []
    for li in range(len(texts)):
        if li not in windows:
            raise SystemExit(f"couldn't find line {li + 1} in the reading: {texts[li]!r}")
        mine = [m for m, o in enumerate(owner) if o == li]
        knots.append(align_line(reading, windows[li], [notes[k] for k in first_of[li]],
                                [(spans[m], weights[m]) for m in mine], midi, lexicon, active, world[0], band))
    return knots


def features(y: np.ndarray, voiced: np.ndarray) -> np.ndarray:
    """Per alignment frame: mel cepstra and their deltas, loudness, and
    voicing. Mean-normalized, so that two different voices compare."""
    import librosa

    m = librosa.feature.mfcc(y=y.astype(np.float32), sr=SR, n_mfcc=20, n_fft=2048, hop_length=HOP,
                             n_mels=40, fmin=80.0, fmax=8000.0)
    m -= m.mean(axis=1, keepdims=True)
    delta = librosa.feature.delta(m[1:], width=5) if m.shape[1] >= 5 else np.zeros_like(m[1:])
    return np.vstack([m, delta, voiced[: m.shape[1]][None]])


def template(piece_notes, seconds: float, midi: float, lexicon):
    """Our formant voice speaking a few syllables on one pitch at the
    reading's pace: audio in which every phoneme's time is known. Returns the
    audio, each syllable's knots in seconds, and a voicing flag per alignment frame."""
    unit = seconds / len(piece_notes)
    notes = [replace(n, start=0.2 + i * unit, dur=unit, pitch=midi, line_end=i == len(piece_notes) - 1)
             for i, n in enumerate(piece_notes)]
    flat = V.VoiceParams(engine="formant", tract=1.12 if midi > 52 else 1.0, vibrato_depth=0.0, scoop=0.0, jitter=0.0, wander=0.0)
    segs = V.schedule(notes, flat, lexicon)
    y = V.sing(notes, SR, flat, 0, lexicon)
    t = np.arange(len(y) // HOP + 2) * HOP / SR
    voiced = np.zeros(len(t))
    for g in segs:
        if g.role == "vowel" or (g.role in ("onset", "coda") and ph.CONSONANTS[g.phone][2]):
            voiced[(t >= g.t0) & (t < g.t1)] = 1.0
    return y, target_knots(segs), voiced


def align_piece(reading, a: int, b: int, piece_notes, midi: float, lexicon, active, f0_world) -> list[list[int]]:
    """Knots in reading frames for a few syllables spoken between frames a
    and b: warp the template's known phoneme times onto the reading (dynamic
    time warping), leaving the reading's silences out of the warp."""
    import librosa

    s0, s1 = int(a * FRAME * SR), int(b * FRAME * SR)
    y_t, knots_t, voiced_t = template(piece_notes, (s1 - s0) / SR, midi, lexicon)
    ta, tb = int((knots_t[0][0] - 0.02) * SR), int((knots_t[-1][3] + 0.02) * SR)
    world_frame = np.clip(((s0 + np.arange((s1 - s0) // HOP + 2) * HOP) / SR / FRAME).astype(int), 0, len(f0_world) - 1)
    X = features(y_t[ta:tb], voiced_t[ta // HOP :])
    Y = features(reading[s0:s1], (f0_world[world_frame] > 0).astype(float))
    keep = active[world_frame[: Y.shape[1]]].copy()
    quiet = np.flatnonzero(np.diff(np.concatenate([[1], keep.astype(int), [1]])))
    for q0, q1 in zip(quiet[::2], quiet[1::2]):
        if q1 - q0 < 12:
            keep[q0:q1] = True
    cols = np.flatnonzero(keep) if keep.any() else np.arange(Y.shape[1])
    both = np.hstack([X, Y[:, cols]])
    mu, sd = both.mean(axis=1, keepdims=True), both.std(axis=1, keepdims=True) + 1e-9
    weight = np.ones((X.shape[0], 1))
    weight[-1] = 2.0  # voicing
    _, path = librosa.sequence.dtw(X=(X - mu) / sd * weight, Y=(Y[:, cols] - mu) / sd * weight, metric="euclidean")
    path = path[::-1]

    def to_reading(t: float) -> float:
        i = int(np.clip(round((t * SR - ta) / HOP), 0, X.shape[1] - 1))
        return (s0 + float(np.median(cols[path[path[:, 0] == i, 1]])) * HOP) / SR / FRAME

    flat = np.maximum.accumulate([to_reading(t) for k in knots_t for t in k[:4]])
    return [list(map(int, np.round(flat[4 * j : 4 * j + 4]))) for j in range(len(knots_t))]


def align_line(reading, window, line_notes, words, midi: float, lexicon, active, f0_world, band) -> list[tuple]:
    """(onset start, vowel start, vowel end, coda end), in reading frames, for
    every syllable of one spoken line within window (frames). The line is cut
    at its pauses and each piece aligned on its own; Whisper's word times, where
    it heard the word, say which words fall in which piece. words: (span or None, syllables)."""
    w0, w1 = window
    pieces = stretches(active, w0, w1, SPLIT) or [(w0, w1)]
    # a word Whisper missed sits in proportion between its heard neighbours
    total = sum(n for _, n in words)
    where, done = [], 0
    for span, n in words:
        mid = (span[0] + span[1]) / 2 / FRAME if span else w0 + (w1 - w0) * (done + n / 2) / total
        inside = [i for i, (p0, p1) in enumerate(pieces) if p0 <= mid < p1]
        where.append(inside[0] if inside else int(np.argmin([min(abs(mid - p0), abs(mid - p1)) for p0, p1 in pieces])))
        done += n
    where = list(np.maximum.accumulate(where))
    # pieces nobody's words landed in join the piece before them (or the first one)
    groups: dict[int, list[int]] = {}
    for i, (p0, p1) in enumerate(pieces):
        owner = max([w for w in where if w <= i], default=min(where))
        g = groups.setdefault(owner, [p0, p1])
        g[0], g[1] = min(g[0], p0), max(g[1], p1)

    knots, k = [], 0
    for g in sorted(set(where)):
        n = sum(syl for (_, syl), w in zip(words, where) if w == g)
        p0, p1 = groups[g]
        knots += align_piece(reading, max(p0 - 4, 0), p1 + 4, line_notes[k : k + n], midi, lexicon, active, f0_world)
        k += n
    flat = np.maximum.accumulate([x for kn in knots for x in kn])
    knots = [list(flat[4 * j : 4 * j + 4]) for j in range(len(knots))]
    for kn in knots:
        kn[2] = max(kn[2], kn[1] + 2)  # every vowel keeps at least two frames
        kn[3] = max(kn[3], kn[2])
    # Inside one syllable the vowel is the loudest voiced stretch. Where the
    # warp plainly missed it (mostly unvoiced, or far quieter than the
    # syllable's best), move it there; otherwise trust the warp, which keeps
    # nasals and liquids out of the vowel better than loudness can.
    prev_end = w0
    for kn in knots:
        lo, hi = max(kn[0] - 4, prev_end), kn[3]
        if hi - lo >= 3:
            score = band[lo:hi] - 30.0 * (f0_world[lo:hi] <= 0)
            q = lo + int(np.argmax(score))
            here = slice(kn[1], max(kn[2], kn[1] + 1))
            missed = np.mean(f0_world[here] > 0) < 0.5 or band[q] - np.median(band[here]) > 12.0
            if missed and f0_world[q] > 0:
                a = b = q
                while a - 1 >= lo and band[a - 1] >= band[q] - 10.0 and f0_world[a - 1] > 0:
                    a -= 1
                while b + 1 < hi and band[b + 1] >= band[q] - 10.0 and f0_world[b + 1] > 0:
                    b += 1
                kn[1], kn[2] = a, max(b + 1, a + 2)
                kn[0], kn[3] = min(kn[0], a), max(kn[3], kn[2])
        prev_end = kn[2]
    for kn, nxt in zip(knots, knots[1:]):  # a pause belongs to neither side
        quiet = np.flatnonzero(~active[kn[2] : nxt[1]])
        if len(quiet) >= 12:
            kn[3], nxt[0] = kn[2] + quiet[0], kn[2] + quiet[-1] + 1
    return [tuple(int(x) for x in kn) for kn in knots]


# --- the song ----------------------------------------------------------------------


def target_knots(segs) -> list[tuple]:
    """(onset start, vowel start, vowel end, coda end, vowel segment, coda
    phones) for every sung note, times in seconds."""
    out = []
    for i, s in enumerate(segs):
        if s.role != "vowel":
            continue
        a = b = i
        while a > 0 and segs[a - 1].role == "onset":
            a -= 1
        while b + 1 < len(segs) and segs[b + 1].role == "coda":
            b += 1
        out.append((segs[a].t0, s.t0, s.t1, segs[b].t1, s, [g.phone for g in segs[i + 1 : b + 1]]))
    return out


def steadiest(S0: int, S1: int, level, noise, f0, diphthong: bool) -> int:
    """The frame of a spoken vowel a singer would hold: loud, clearly pitched
    and least noisy, away from the vowel's edges, where a spoken word fades,
    creaks or breathes out (in a diphthong, in its first quality)."""
    lo = S0 + (S1 - S0) // 5
    hi = S0 + (S1 - S0) // 2 if diphthong else S1 - (S1 - S0) // 5
    if hi <= lo:
        return (S0 + S1) // 2
    score = level[lo:hi] - 20.0 * noise[lo:hi] - 30.0 * (f0[lo:hi] <= 0)
    return lo + int(np.argmax(score))


def vowel_map(tt, T0, T1, S0, S1, core: int, wobble):
    """Source frame for target times inside one vowel. A note longer than the
    spoken vowel arrives at the vowel's steadiest frame at speaking speed,
    holds it (drifting a frame or two so it never freezes), and leaves at
    speaking speed into whatever follows; a diphthong's steadiest frame lies
    in its first quality, so it turns to the second at the end of the note."""
    Ts = (T1 - T0) / FRAME
    if Ts <= S1 - S0:
        return np.interp(tt, [T0, T1], [S0, S1])
    attack = float(np.clip(core - S0, 1, 0.35 * Ts)) * FRAME
    release = float(np.clip(S1 - core, 1, 0.35 * Ts)) * FRAME
    s = np.interp(tt, [T0, T0 + attack, T1 - release, T1], [S0, core, core, S1])
    hold = (tt > T0 + attack) & (tt < T1 - release)
    s[hold] = np.clip(s[hold] + wobble[hold], max(S0, core - 2), min(S1, core + 2))
    return s


def warp_envelope(rows: np.ndarray, factor: float) -> np.ndarray:
    """Move every resonance by a factor along frequency: a shorter or longer tract."""
    n = rows.shape[1]
    pos = np.clip(np.arange(n) / factor, 0, n - 1.001)
    i0 = pos.astype(int)
    w = pos - i0
    return rows[:, i0] * (1 - w) + rows[:, i0 + 1] * w


def sing_from_speech(notes, segs, reading, lines, which, voice, seed, formant=1.0):
    f0_s, sp_s, ap_s = reading["world"]
    knots_s = reading["knots"]  # per spoken line, per syllable
    level = reading["band"]
    log_sp = np.log(sp_s + 1e-30)
    freqs = np.linspace(0.0, SR / 2, sp_s.shape[1])
    noise = ap_s[:, (freqs >= 500) & (freqs <= 4000)].mean(axis=1)  # 0 periodic, 1 noise

    targets = target_knots(segs)
    duration = max(s.t1 for s in segs) + 0.5
    n_out = int(np.ceil(duration / FRAME)) + 1
    t_out = np.arange(n_out) * FRAME
    rng = np.random.default_rng(seed)
    wobble = uniform_filter1d(rng.standard_normal(n_out), 40)
    wobble *= 1.5 / (np.std(wobble) + 1e-12)  # frames

    src = np.full(n_out, np.nan)
    gain = np.zeros(n_out)
    vowel = np.zeros(n_out, dtype=bool)
    keep_voicing = np.zeros(n_out, dtype=bool)
    levels, amps, spans, swells = [], [], [], []
    for line_index, line in enumerate(lines):
        spoken = knots_s[which[line_index]]
        for j, k in enumerate(line):
            T_on, T_v0, T_v1, T_c1, seg, coda = targets[k]
            S_on, S_v0, S_v1, S_c1 = spoken[j]
            core = steadiest(S_v0, S_v1, level, noise, f0_s, seg.phone in ph.DIPHTHONGS)
            f = np.arange(int(np.ceil(T_on / FRAME)), min(int(np.ceil(T_c1 / FRAME)), n_out))
            tt = f * FRAME
            s = np.empty(len(f))
            on, vw, co = tt < T_v0, (tt >= T_v0) & (tt < T_v1), tt >= T_v1
            s[on] = np.interp(tt[on], [T_on, T_v0], [S_on, S_v0])
            s[vw] = vowel_map(tt[vw], T_v0, T_v1, S_v0, S_v1, core, wobble[f[vw]])
            s[co] = np.interp(tt[co], [T_v1, T_c1], [S_v1, max(S_c1, S_v1)])
            src[f] = s
            vowel[f[vw]] = True
            if coda and all(ph.CONSONANTS[c][2] for c in coda):  # a voiced ending stays voiced
                keep_voicing[f[co][:-2]] = True
            if seg.swell:  # a phrasing's swell or fade through the vowel
                swells.append((f[vw], seg.swell * np.clip((tt[vw] - T_v0) / max(T_v1 - T_v0, 1e-3), 0.0, 1.0)))
            levels.append(float(np.mean(level[max(core - 3, 0) : core + 4])))
            amps.append(seg.amp)
            spans.append(f)
    # loudness follows the score: level every syllable, then apply the singer's dynamics
    middle = float(np.median(levels))
    for f, lv, amp in zip(spans, levels, amps):
        # a vowel far below the rest was found in the wrong place; never boost it
        correction = float(np.clip(lv - middle, -8.0, 8.0)) if lv > middle - 30.0 else 0.0
        gain[f] = 20 * np.log10(amp / 0.9) - correction
    for f, ramp in swells:
        gain[f] += ramp
    gain = uniform_filter1d(gain, 7)
    sung = ~np.isnan(src)
    # fade in and out wherever the voice starts or stops, so nothing clicks
    edges = np.flatnonzero(np.diff(np.concatenate([[0], sung.astype(int), [0]])))
    for a, b in zip(edges[::2], edges[1::2]):
        fade_in, fade_out = min(2, (b - a) // 4), min(4, (b - a) // 3)
        gain[a : a + fade_in] += np.linspace(-18.0, 0.0, fade_in, endpoint=False)
        gain[b - fade_out : b] += np.linspace(0.0, -30.0, fade_out)

    s = np.clip(src[sung], 0, len(f0_s) - 1.001)
    i0 = s.astype(int)
    w = (s - i0)[:, None]
    env = np.exp((1 - w) * log_sp[i0] + w * log_sp[i0 + 1]) * 10.0 ** (gain[sung, None] / 10.0)
    ape = (1 - w) * ap_s[i0] + w * ap_s[i0 + 1]
    if formant != 1.0:
        env, ape = warp_envelope(env, formant), warp_envelope(ape, formant)

    sp = np.full((n_out, sp_s.shape[1]), 1e-16)
    ap = np.ones((n_out, sp_s.shape[1]))
    sp[sung], ap[sung] = env, ape
    n_blocks = int(np.ceil(duration * SR / V.BLOCK))
    tb = (np.arange(n_blocks) + 0.5) * V.BLOCK / SR
    sounding = [g.t1 for g in segs if g.role == "vowel"]  # so a phrasing's falls happen while the vowel is heard
    pitch = np.interp(t_out, tb, V.pitch_track(notes, n_blocks, SR, voice, rng, sounding))
    voiced = np.zeros(n_out, dtype=bool)
    voiced[sung] = f0_s[np.round(s).astype(int)] > 0
    voiced |= vowel | keep_voicing
    f0 = np.where(voiced & sung, pitch, 0.0)

    y = pyworld.synthesize(np.ascontiguousarray(f0), np.ascontiguousarray(sp), np.ascontiguousarray(ap), SR, FRAME * 1000)
    mask = np.zeros(len(y), dtype=bool)
    for _, T_v0, T_v1, *_ in targets:
        mask[int(T_v0 * SR) : int(T_v1 * SR)] = True
    return 0.3 * y / (np.sqrt(np.mean(y[mask] ** 2)) + 1e-12) / np.sqrt(2.0)


def voice_params(overrides: dict[str, str]) -> V.VoiceParams:
    defaults = V.VoiceParams()
    return replace(defaults, **{k: type(getattr(defaults, k))(v) for k, v in overrides.items()})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--speech", help="a recording of the script, read plainly")
    source.add_argument("--say", metavar="VOICE", help="read the script with a macOS voice instead")
    source.add_argument("--script", action="store_true", help="print the lines to read and stop")
    ap.add_argument("--form", nargs="+", help="override the section order, e.g. refrain")
    ap.add_argument("--voice", nargs="*", default=[], metavar="FIELD=VALUE", help="override the singer's pitch and timing")
    ap.add_argument("--formant", type=float, default=1.0, help="move the speaker's resonances: above 1 a shorter tract")
    ap.add_argument("--out", help="output FLAC (default renders/<genome>.speech.flac)")
    ap.add_argument("--no-score", action="store_true", help="skip the Whisper word-error scores")
    args = ap.parse_args()

    genome = G.load(args.genome)
    params = choose_params(genome)
    if args.form:
        params = replace(params, form=tuple(args.form))
    score = realize(genome, params)
    notes = sorted(score.part("voice"), key=lambda n: n.start)
    lines = lines_of(notes)
    texts, which = script(notes, lines)
    if args.script:
        print("\n".join(texts))
        return

    overrides = dict(kv.split("=", 1) for kv in args.voice)
    base = voice_params(overrides)

    reading = say(texts, args.say) if args.say else load(args.speech)
    world = analyze(reading)
    band, active = tracks(world[1])
    voiced = world[0] > 0

    # A singer picks a key that suits them: the tune's middle about four
    # semitones above where they speak. Whole octaves go to the voice; the
    # rest moves the key, so the instruments come along.
    spoken = hz_to_midi(float(np.median(world[0][voiced])))
    shift = base.shift
    if "shift" not in overrides:
        total = int(np.round(spoken + 4 - np.median([n.pitch for n in notes])))
        shift = 12 * int(np.round(total / 12))
        params = replace(params, tonic=params.tonic + total - shift)
        score = realize(genome, params)
        notes = sorted(score.part("voice"), key=lambda n: n.start)
    voice = replace(base, shift=shift)
    segs = V.schedule(notes, base, genome.lexicon)

    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    first_of = {}
    for i, w in enumerate(which):
        first_of.setdefault(w, lines[i])
    knots = align_reading(model, reading, world, band, active, texts, first_of, notes, genome.lexicon, spoken)

    sung = sing_from_speech(notes, segs, {"world": world, "knots": knots, "band": band},
                            lines, which, voice, params.seed, args.formant)

    out = Path(args.out or Path("renders") / (Path(args.genome).stem + ".speech.flac"))
    out.parent.mkdir(parents=True, exist_ok=True)
    bare = replace(score, notes=tuple(n for n in score.notes if n.part != "voice"))
    stems = synth.render_stems(bare, seed=params.seed)
    length = len(next(iter(stems.values())))
    stems["voice"] = synth.pan(np.pad(sung, (0, max(0, length - len(sung))))[:length], 0.0) * synth.VOICE_GAIN
    pcm = master.to_pcm16(master.master(synth.mix(stems, SR, params.seed), SR), seed=params.seed)
    master.write_flac(out, pcm, SR)
    sf.write(str(out.with_suffix(".voice.wav")), sung, SR, subtype="FLOAT")
    sf.write(str(out.with_suffix(".reading.wav")), reading, SR, subtype="FLOAT")
    print(f"{out}  {len(pcm) / SR:.1f}s  tonic {params.tonic} (seed {genome.seed_params['tonic']}), voice {shift:+d}, "
          f"speaker's median {440 * 2 ** ((spoken - 69) / 12):.0f} Hz")

    if not args.no_score:
        formant_voice = V.sing(notes, SR, voice, seed=params.seed, lexicon=genome.lexicon)  # same register
        for name, y in (("speech-to-song", sung), ("formant singer", formant_voice)):
            e, n, misses, _ = score_sections(model, y, notes, segs, False)
            print(f"{name:16} WER {e / n:5.1%}  ({e}/{n})  " + ", ".join(misses[:12]))


if __name__ == "__main__":
    main()
