"""How our singer delivers a line, against a natural teacher singing the same notes (dev only).

    uv run python tools/delivery.py measure [--split test] [--engine formant] [--out renders/delivery/formant.json]
    uv run python tools/delivery.py table renders/delivery/teacher.json renders/delivery/formant.json ...

The teacher is SoulX-Singer singing our own scores (renders/throat/corpus/<singer>/<segment>.wav, with
the notes it was asked to sing beside it in <segment>.json). Only the house singers (source "formant":
SoulX prompted with our own formant singer) are measured by default; the singers prompted with Eleven
Music voices are a comparison at most (--source eleven-music), never something to fit.

Ours is the same notes sung by our singer (the formant singer, or the learned throat with
SONGBIRD_THROAT set). Both are analysed the same way, every 5 ms: f0 (WORLD's Harvest, searched within
a fifth of the notes), how periodic the voice is (1 - D4C aperiodicity, 150 Hz-3 kHz), level (dB, 30 ms
windows) and the level in octave bands. Then, note by note on the score's own clock:

- transitions between legato notes: when the pitch leaves the old note and arrives at the new one
  (10/50/90% of the interval, against the note's start), how far it prepares (moves away first) and
  overshoots, and how soon it settles;
- scoops: where a line's first note starts from, and how fast it arrives;
- held notes: vibrato (extent, rate, when it starts, how it varies within and between notes), slow
  wander, and the modulation spectrum of the pitch;
- consonants: the pitch around a consonant between two notes on the same pitch (micro-prosody);
- line ends: the pitch and level as the voice lets go;
- loudness: each syllable's level against its stress, word, place in the line and pitch; the envelope
  inside a held vowel; the modulation spectrum of the level;
- breaths: the sound between lines (level, length, spectrum);
- timing: where the voice starts against the note (after a voiceless consonant, where it's clear).

`measure` writes every number (and the curves behind them) to a JSON file; `table` prints several
side by side. The f0 distance to the teacher (note by note, on voiced frames both share) is only
computed when ours is measured, since the teacher is the reference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import warnings
import zlib
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path

for _var in ("OMP_NUM_THREADS", "NUMBA_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "2")  # a shared machine: each worker keeps to two threads

import numpy as np  # noqa: E402

warnings.filterwarnings("ignore", message="pkg_resources")
warnings.filterwarnings("ignore", category=RuntimeWarning)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FRAME = 0.005  # seconds per analysis frame
SR = 24000  # the corpus's rate; ours is sung at it too
STRONG = 0.6  # periodicity (1 - aperiodicity) above which a frame's f0 is trusted
BANDS = (0, 250, 500, 1000, 2000, 4000, 8000, 12000)  # Hz: octave bands for breath spectra
VOICELESS = {"P", "T", "K", "F", "TH", "S", "SH", "CH", "HH"}
VOICED_OBSTRUENT = {"B", "D", "G", "V", "DH", "Z", "ZH", "JH"}
SONORANT = {"M", "N", "NG", "L", "R", "W", "Y"}
HELD_OUT = {"h-now-its-by-you", "k-still-you-grew"}  # held out whole; other items by hash


def split_of(item: str) -> str:
    return "held" if item in HELD_OUT or zlib.crc32(item.encode()) % 5 == 0 else "fit"


def lexicon_for(item: str) -> dict:
    from songbird import genome as G

    songs = sorted((ROOT / "songs").glob("*.json"))
    if item.startswith("h-"):
        return G.load(ROOT / "songs/h-now-its-by-you.json").lexicon
    if item.startswith("cover-"):
        letter = item.split("-")[2]
        path = next(p for p in songs if p.stem.startswith(letter + "-"))
        return G.load(path).lexicon
    path = next((p for p in songs if p.stem == item), None)
    return G.load(path).lexicon if path else {}


# ---- analysis: the same for the teacher and for ours ------------------------------------------------


def analyse(x: np.ndarray, sr: int, pitches: list[float]) -> dict[str, np.ndarray]:
    import pyworld as pw

    x = np.ascontiguousarray(x, dtype=np.float64)
    lo = 440.0 * 2 ** ((min(pitches) - 7 - 69) / 12)
    hi = 440.0 * 2 ** ((max(pitches) + 7 - 69) / 12)
    f0, t = pw.harvest(x, sr, f0_floor=max(lo, 50.0), f0_ceil=min(hi, 1100.0), frame_period=FRAME * 1000)
    ap = pw.d4c(x, f0, t, sr)
    freqs = np.linspace(0, sr / 2, ap.shape[1])
    band = (freqs >= 150) & (freqs <= 3000)
    periodic = np.where(f0 > 0, 1.0 - ap[:, band].mean(axis=1), 0.0)
    hop, win = int(round(FRAME * sr)), int(round(0.03 * sr))
    padded = np.pad(x, (win // 2, win // 2 + hop * len(f0)))
    idx = np.arange(len(f0))[:, None] * hop + np.arange(win)[None, :]
    spec = np.abs(np.fft.rfft(padded[idx] * np.hanning(win), axis=1)) ** 2
    hz = np.fft.rfftfreq(win, 1 / sr)
    power = spec.sum(axis=1) / (np.hanning(win) ** 2).sum() * 2 / win
    level = 10 * np.log10(np.maximum(power, 1e-12))
    bands = np.stack([10 * np.log10(np.maximum(spec[:, (hz >= a) & (hz < b)].sum(axis=1), 1e-12))
                      for a, b in zip(BANDS, BANDS[1:])], axis=1)
    return {"f0": f0.astype(np.float32), "periodic": periodic.astype(np.float32), "level": level.astype(np.float32),
            "bands": bands.astype(np.float32)}


@dataclass
class Seg:
    path: Path  # the teacher's wav
    label: dict
    notes: list[dict] = field(default_factory=list)


def load_segments(corpus: Path, sources: set[str], split: str | None, singers: list[str] | None = None) -> list[Seg]:
    out = []
    for js in sorted(corpus.glob("*/*.json")):
        wav = js.with_suffix(".wav")
        if not wav.exists():
            continue
        label = json.loads(js.read_text())
        if label.get("source", "eleven-music") not in sources:
            continue
        if singers and label["singer"] not in singers:
            continue
        if split and split != "all" and split_of(label["item"]) != split:
            continue
        out.append(Seg(wav, label, label["notes"]))
    return out


def teacher_analysis(seg: Seg, cache: Path) -> dict:
    out = cache / "teacher" / seg.path.parent.name / f"{seg.path.stem}.npz"
    if out.exists() and out.stat().st_mtime >= seg.path.stat().st_mtime:
        return dict(np.load(out))
    import soundfile as sf

    x, sr = sf.read(str(seg.path), dtype="float64")
    an = analyse(x, sr, [n["pitch"] for n in seg.notes])
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **an)
    return an


def score_notes(seg: Seg):
    from songbird.score import Note

    return [Note(part="voice", start=n["start"], dur=n["dur"], pitch=float(n["pitch"]), vel=float(n.get("vel", 0.75)),
                 syllable=n.get("syllable"), word=n["word"], word_len=int(n["word_len"]), line_end=bool(n["line_end"]))
            for n in seg.notes]


def sing_ours(seg: Seg, engine: str, voice_set: dict, seed: int) -> np.ndarray:
    from songbird.synth.voice import VoiceParams, sing

    voice = replace(VoiceParams(engine=engine), **voice_set)
    y = sing(score_notes(seg), SR, voice, seed=seed, lexicon=lexicon_for(seg.label["item"]))
    frames_wanted = int(round((seg.label["t1"] - seg.label["t0"]) * SR))
    return np.pad(y, (0, max(0, frames_wanted - len(y))))[: max(frames_wanted, 1)]


def singer_version(engine: str, voice_set: dict, seed: int) -> str:
    """What our rendition of a segment depends on: the singer's code, its settings and the throat's weights."""
    h = hashlib.sha256(repr((engine, sorted(voice_set.items()), seed)).encode())
    for f in sorted((ROOT / "songbird" / "synth").glob("*.py")) + [ROOT / "songbird" / "phonetics.py"]:
        h.update(f.read_bytes())
    for f in sorted((ROOT / "songbird" / "synth").glob("*.npz")):
        h.update(f.read_bytes())
    if engine.startswith("learned"):
        h.update(os.environ.get("SONGBIRD_THROAT", "").encode())
    return h.hexdigest()[:12]


def our_analysis(seg: Seg, engine: str, voice_set: dict, seed: int, keep: Path | None = None,
                 cache: Path | None = None) -> dict:
    out = None
    if cache is not None:
        out = cache / "ours" / singer_version(engine, voice_set, seed) / f"{seg.path.stem}.npz"
        if out.exists() and keep is None:
            return dict(np.load(out))
    y = sing_ours(seg, engine, voice_set, seed)
    if keep is not None:
        import soundfile as sf

        keep.mkdir(parents=True, exist_ok=True)
        sf.write(str(keep / f"{seg.path.stem}.wav"), (0.9 * y / max(np.abs(y).max(), 1e-9)).astype(np.float32), SR)
    an = analyse(y, SR, [n["pitch"] for n in seg.notes])
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out, **an)
    return an


# ---- measures -----------------------------------------------------------------------------------


def hz(pitch: float) -> float:
    return 440.0 * 2 ** ((pitch - 69) / 12)


def span(t0: float, t1: float, n: int) -> slice:
    return slice(int(np.clip(round(t0 / FRAME), 0, n)), int(np.clip(round(t1 / FRAME), 0, n)))


def cents_of(an: dict, pitch: float) -> np.ndarray:
    """Cents from the pitch where the voice is clearly periodic, NaN elsewhere."""
    f0 = an["f0"].astype(np.float64)
    ok = (f0 > 0) & (an["periodic"] >= STRONG)
    return np.where(ok, 1200 * np.log2(np.maximum(f0, 1.0) / hz(pitch)), np.nan)


def fill(x: np.ndarray, most: int = 8) -> np.ndarray:
    """Interpolate over runs of NaN no longer than `most` frames."""
    y = x.copy()
    bad = np.isnan(y)
    if not bad.any() or bad.all():
        return y
    idx = np.arange(len(y))
    interp = np.interp(idx, idx[~bad], y[~bad])
    run_start = None
    for i in range(len(y) + 1):
        b = i < len(y) and bad[i]
        if b and run_start is None:
            run_start = i
        elif not b and run_start is not None:
            if run_start > 0 and i < len(y) and i - run_start <= most:
                y[run_start:i] = interp[run_start:i]
            run_start = None
    return y


def lowpass(x: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    from scipy.signal import butter, sosfiltfilt

    if len(x) < 16:
        return np.full_like(x, np.nanmean(x))
    sos = butter(order, cutoff, fs=1 / FRAME, output="sos")
    return sosfiltfilt(sos, x, padlen=min(len(x) - 1, 3 * 12))


def bandpass(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    from scipy.signal import butter, sosfiltfilt

    sos = butter(2, [lo, hi], btype="band", fs=1 / FRAME, output="sos")
    return sosfiltfilt(sos, x, padlen=min(len(x) - 1, 3 * 12))


def phones_of(note: dict) -> tuple[list[str], str | None, list[str]]:
    ph = [p for p in note.get("phones", [])]
    v = next((i for i, p in enumerate(ph) if p[-1:].isdigit()), None)
    if v is None:
        return [p for p in ph], None, []
    return [p for p in ph[:v]], ph[v], [p for p in ph[v + 1:]]


def boundary_class(phones: list[str]) -> str:
    if any(p in VOICELESS for p in phones):
        return "voiceless"
    if any(p in VOICED_OBSTRUENT for p in phones):
        return "voiced"
    return "open"  # vowel to vowel, or through a nasal, liquid or glide


def lines_of(notes: list[dict]) -> list[list[int]]:
    lines, cur = [], []
    for k, n in enumerate(notes):
        cur.append(k)
        if n["line_end"] or k == len(notes) - 1:
            lines.append(cur)
            cur = []
    return lines


def steady_span(notes: list[dict], k: int) -> tuple[float, float]:
    """The part of note k clear of the way in and out: from 0.15 s after it starts to 0.1 s before
    it is let go or the next note (sung straight on) begins."""
    n = notes[k]
    end = min(n["sung_end"], n["start"] + n["dur"])
    if k + 1 < len(notes) and notes[k + 1]["start"] - end < 0.03:
        end = min(end, notes[k + 1]["start"])
    return n["start"] + 0.15, end - 0.1


def note_centre(c: np.ndarray, notes: list[dict], k: int) -> float:
    a, b = steady_span(notes, k)
    s = span(a, max(b, a + 0.05), len(c))
    vals = c[s]
    vals = vals[~np.isnan(vals)]
    return float(np.median(vals)) if len(vals) >= 6 else float("nan")


def measure_segment(an: dict, notes: list[dict]) -> dict:
    """Every per-note and per-boundary measure of one sung segment."""
    n_frames = len(an["f0"])
    level = an["level"].astype(np.float64)
    out: dict[str, list] = {k: [] for k in ("transitions", "scoops", "held", "micro", "finals", "notes", "breaths",
                                            "timing", "envelopes", "f0_psd", "level_psd", "line_psd")}
    lines = lines_of(notes)
    line_of = {k: li for li, line in enumerate(lines) for k in line}
    cents = [cents_of(an, n["pitch"]) for n in notes]
    centres = [note_centre(cents[k], notes, k) for k in range(len(notes))]

    # --- each syllable's level, and where it sits in its line
    note_levels = []
    for k, n in enumerate(notes):
        end = min(n["sung_end"], n["start"] + n["dur"])
        s = span(n["start"] - 0.02, end, n_frames)
        voiced = an["periodic"][s] >= STRONG
        lv = level[s][voiced]
        note_levels.append(float(np.percentile(lv, 90)) if len(lv) >= 4 else float("nan"))
    med = float(np.nanmedian(note_levels)) if np.isfinite(note_levels).any() else 0.0
    for li, line in enumerate(lines):
        pitches = [notes[j]["pitch"] for j in line]
        mid = float(np.median(pitches))
        for pos, k in enumerate(line):
            n = notes[k]
            onset, vowel, coda = phones_of(n)
            word = (n["word"] or "").replace("-", "").replace("*", "").lower().strip(".,;:!?\"'")
            from songbird import phonetics as ph

            out["notes"].append(dict(
                level=note_levels[k] - med, stressed=bool(vowel and vowel[-1] in "12" and n["word_len"] > 1),
                unstressed=bool(vowel and vowel[-1] == "0"), function=word in ph.FUNCTION_WORDS,
                first=pos == 0, last=pos == len(line) - 1, climb=n["pitch"] - mid, vel=float(n.get("vel", 0.75)),
                focus="*" in (n["word"] or ""), dur=n["dur"], pos=pos / max(len(line) - 1, 1), line=li,
                tune=centres[k]))

    # --- transitions between legato notes in a line
    for k in range(1, len(notes)):
        a, b = notes[k - 1], notes[k]
        if line_of[k] != line_of[k - 1] or b["start"] - min(a["sung_end"], a["start"] + a["dur"]) > 0.03:
            continue
        d = b["pitch"] - a["pitch"]
        _, _, coda = phones_of(a)
        onset, _, _ = phones_of(b)
        cls = boundary_class(coda + onset)
        m_a, m_b = centres[k - 1], centres[k]
        if d == 0 or not np.isfinite(m_a) or not np.isfinite(m_b) or abs((m_b + 100 * d) - m_a) < 30:
            continue
        lo_t = max(b["start"] - 0.3, a["start"] + 0.1)
        hi_t = min(b["start"] + 0.4, steady_span(notes, k)[1] + 0.05)
        s = span(lo_t, hi_t, n_frames)
        c = fill(cents[k - 1][s] - m_a, 6)
        size = (m_b + 100 * d) - m_a  # cents the voice has to move, centre to centre
        y = c / size
        t = np.arange(s.start, s.stop) * FRAME - b["start"]
        rec = dict(interval=int(d), cls=cls, size=float(size), t=t.tolist(), y=np.where(np.isnan(y), None, y).tolist())
        ok = ~np.isnan(y)
        if ok.mean() > 0.8 and ok[:3].all() and cls != "voiceless":
            ys = np.convolve(np.where(ok, y, 0), np.ones(3) / 3, mode="same")
            ys[~ok] = np.nan
            window = (t > -0.25) & (t < 0.3)
            cross = np.flatnonzero(window[1:] & (ys[:-1] < 0.5) & (ys[1:] >= 0.5))
            if len(cross):
                i50 = cross[0] + 1
                i10 = i50
                while i10 > 0 and not ys[i10] < 0.1:
                    i10 -= 1
                i90 = i50
                while i90 < len(ys) - 1 and not ys[i90] > 0.9:
                    i90 += 1
                if ys[i10] < 0.1 and ys[i90] > 0.9:
                    after = slice(i90, min(i90 + int(0.25 / FRAME), len(ys)))
                    before = slice(max(i10 - int(0.12 / FRAME), 0), i10 + 1)
                    peak = np.nanmax(ys[after]) - 1.0
                    dip = np.nanmin(ys[before])
                    settle = None
                    close = np.abs(ys[i90:] - 1.0) * abs(size) < 15
                    for j in range(len(close)):
                        if close[j : j + 8].all() and j + 8 <= len(close):
                            settle = float(t[i90 + j] - t[i90])
                            break
                    rec.update(t10=float(t[i10]), t50=float(t[i50]), t90=float(t[i90]),
                               overshoot=float(peak * abs(size)), prep=float(min(dip, 0.0) * abs(size)), settle=settle)
        out["transitions"].append(rec)

    # --- scoops: a line's first note, after a rest
    for li, line in enumerate(lines):
        k = line[0]
        n = notes[k]
        if k > 0 and n["start"] - notes[k - 1]["sung_end"] < 0.1:
            continue
        m = centres[k]
        if not np.isfinite(m):
            continue
        s = span(n["start"] - 0.15, n["start"] + 0.35, n_frames)
        c = cents[k][s] - m
        t = np.arange(s.start, s.stop) * FRAME - n["start"]
        ok = np.flatnonzero(~np.isnan(c))
        if len(ok) < 10:
            continue
        first = ok[0]
        within = np.flatnonzero(np.abs(np.nan_to_num(c[first:], nan=999)) < 20)
        early = c[first + 2: first + 8]
        early = early[np.abs(early) < 300]  # past the first glottal pulses, and no octave slips
        out["scoops"].append(dict(onset=boundary_class(phones_of(n)[0]) if phones_of(n)[0] else "vowel",
                                  start=float(c[first]), t_voice=float(t[first]),
                                  early=float(np.median(early)) if len(early) >= 3 else None,
                                  mean50=float(np.nanmean(c[first:first + 10])),
                                  arrive=float(t[first + within[0]] - t[first]) if len(within) else None,
                                  t=t.tolist(), y=np.where(np.isnan(c), None, c).tolist()))

    # --- held notes: vibrato, wander, the pitch's modulation spectrum
    for k, n in enumerate(notes):
        a, b = steady_span(notes, k)
        if b - a < 0.3:
            continue
        s = span(a, b, n_frames)
        c = cents[k][s]
        if np.isnan(c).mean() > 0.15:
            continue
        c = fill(c, 10)
        if np.isnan(c).any():
            continue
        trend = lowpass(c, 3.0)
        vib = bandpass(c - trend, 3.5, 9.0)
        from scipy.signal import hilbert

        env = np.abs(hilbert(vib))
        phase = np.unwrap(np.angle(hilbert(vib)))
        inst = np.diff(phase) / (2 * np.pi * FRAME)
        edge = min(len(env) // 6, 8)
        core = slice(edge, len(env) - edge)
        extent = float(np.median(env[core]))
        rate = float(np.median(inst[core])) if len(inst[core]) else float("nan")
        # zero crossings of the vibrato: its half cycles, for how evenly it runs
        zc = np.flatnonzero(np.diff(np.sign(vib[core])) != 0)
        halves = np.diff(zc) * FRAME
        lin = np.polyval(np.polyfit(np.arange(len(c)), c, 1), np.arange(len(c)))
        wander = float(np.std(trend - lin))
        fast = float(np.std(c - trend - vib))
        t_from = a - n["start"]
        rec = dict(dur=n["dur"], steady=b - a, extent=extent, rate=rate,
                   rate_cv=float(np.std(1 / (2 * halves[halves > 0.02])) / max(np.mean(1 / (2 * halves[halves > 0.02])), 1e-9))
                   if (halves > 0.02).sum() >= 3 else None,
                   extent_cv=float(np.std(env[core]) / max(np.mean(env[core]), 1e-9)),
                   wander=wander, fast=fast, last=bool(n["line_end"]),
                   env_t=(t_from + np.arange(len(env)) * FRAME).tolist()[::4], env=env.tolist()[::4])
        out["held"].append(rec)
        if b - a >= 0.5:
            x = c - lin
            w = np.hanning(len(x))
            spec = np.abs(np.fft.rfft(x * w, n=512)) ** 2 / (w**2).sum()
            out["f0_psd"].append(dict(weight=len(x), psd=spec.tolist()))
            lv = level[s]
            lv = lv - np.polyval(np.polyfit(np.arange(len(lv)), lv, 1), np.arange(len(lv)))
            spec = np.abs(np.fft.rfft(lv * w, n=512)) ** 2 / (w**2).sum()
            out["level_psd"].append(dict(weight=len(x), psd=spec.tolist()))

    # --- micro-prosody: the pitch through a consonant between two notes on one pitch
    for k in range(1, len(notes)):
        a, b = notes[k - 1], notes[k]
        if line_of[k] != line_of[k - 1] or b["pitch"] != a["pitch"]:
            continue
        if b["start"] - min(a["sung_end"], a["start"] + a["dur"]) > 0.03:
            continue
        _, _, coda = phones_of(a)
        onset, _, _ = phones_of(b)
        m = np.nanmean([centres[k - 1], centres[k]])
        if not np.isfinite(m):
            continue
        s = span(b["start"] - 0.2, b["start"] + 0.2, n_frames)
        c = cents[k][s] - m
        out["micro"].append(dict(cls=boundary_class(coda + onset), phones=coda + onset,
                                 t=(np.arange(s.start, s.stop) * FRAME - b["start"]).tolist(),
                                 y=np.where(np.isnan(c), None, c).tolist()))

    # --- line ends: the last 300 ms of voice, pitch and level
    for li, line in enumerate(lines):
        k = line[-1]
        n = notes[k]
        stop = min(n["start"] + n["dur"], n["sung_end"] + 0.1)
        if k + 1 < len(notes):
            stop = min(stop, notes[k + 1]["start"] - 0.05)  # never into the next line's first sound
        s = span(n["start"], stop, n_frames)
        voiced = np.flatnonzero(an["periodic"][s] >= STRONG)
        if len(voiced) < 20:
            continue
        last = s.start + voiced[-1]
        m = centres[k]
        e = span((last + 1) * FRAME - 0.3, (last + 1) * FRAME, n_frames)
        c = cents[k][e] - m if np.isfinite(m) else np.full(e.stop - e.start, np.nan)
        lv = level[e] - np.nanmax(level[s])
        out["finals"].append(dict(voice_end=float((last + 1) * FRAME - n["sung_end"]),
                                  y=np.where(np.isnan(c), None, c).tolist(), level=lv.tolist(),
                                  fall=float(np.nanmean(c[-10:]) - np.nanmean(c[:20])) if np.isfinite(m) and np.isfinite(c[-10:]).sum() >= 3 else None))

    # --- the envelope inside a held vowel
    for k, n in enumerate(notes):
        end = min(n["sung_end"], n["start"] + n["dur"])
        s = span(n["start"] - 0.1, end + 0.05, n_frames)
        voiced = np.flatnonzero(an["periodic"][s] >= STRONG)
        if len(voiced) < int(0.25 / FRAME):
            continue
        # the longest run of voice in the note: the vowel, with its voiced neighbours
        runs = np.split(voiced, np.flatnonzero(np.diff(voiced) > 2) + 1)
        run = max(runs, key=len)
        if len(run) < int(0.25 / FRAME):
            continue
        lv = level[s.start + run[0]: s.start + run[-1] + 1]
        peak = float(lv.max())
        x = np.linspace(0, 1, len(lv))
        curve = np.interp(np.linspace(0, 1, 20), x, lv - peak)
        att = np.flatnonzero(lv >= peak - 3)
        out["envelopes"].append(dict(dur=len(lv) * FRAME, curve=curve.tolist(), peak_at=float(np.argmax(lv) / len(lv)),
                                     attack=float(att[0] * FRAME), taper=float(np.mean(lv[int(0.8 * len(lv)):]) - np.mean(lv[int(0.2 * len(lv)): int(0.4 * len(lv))])),
                                     last=bool(n["line_end"]), stressed=bool((phones_of(n)[1] or "0")[-1] in "12")))

    # --- the loudness of whole lines: syllables come and go
    for line in lines:
        a = notes[line[0]]["start"] - 0.1
        b = min(notes[line[-1]]["sung_end"], notes[line[-1]]["start"] + notes[line[-1]]["dur"])
        s = span(a, b, n_frames)
        if s.stop - s.start < 200:
            continue
        lv = np.maximum(level[s], med - 50.0)
        lv = lv - lv.mean()
        w = np.hanning(len(lv))
        spec = np.abs(np.fft.rfft(lv * w, n=2048)) ** 2 / (w**2).sum()
        out["line_psd"].append(dict(weight=len(lv), psd=spec.tolist()))

    # --- breaths between lines: what sounds between the voice letting go and the next line's first sound
    for li in range(len(lines) - 1):
        k, j = lines[li][-1], lines[li + 1][0]
        s0 = span(notes[k]["start"], min(notes[k]["sung_end"] + 0.05, notes[j]["start"] - 0.05), n_frames)
        voiced = np.flatnonzero(an["periodic"][s0] >= STRONG)
        if not len(voiced):
            continue
        coda = phones_of(notes[k])[2]
        # after a voiceless coda (or a voiced obstruent, often devoiced at a line's end) the gap starts
        # with that consonant's noise: skip past it
        skip = 0.04 + (0.12 if any(p in VOICELESS or p in VOICED_OBSTRUENT for p in coda) else 0.0)
        # and stop short of the next line's first consonants, which a singer may start before the note
        a, b = (s0.start + voiced[-1] + 1) * FRAME + skip, notes[j]["start"] - 0.04 - 0.08 * len(phones_of(notes[j])[0])
        if b - a < 0.08:
            continue
        s = span(a, b, n_frames)
        lv = level[s] - med
        loud = np.argsort(lv)[-5:]
        spectrum = an["bands"][s][loud].mean(axis=0)
        audible = lv > -50
        out["breaths"].append(dict(coda=boundary_class(coda), gap=b - a, peak=float(lv.max()), floor=float(np.percentile(lv, 10)),
                                   mean=float(10 * np.log10(np.mean(10 ** (lv / 10)))),
                                   audible=float(audible.sum() * FRAME),
                                   peak_at=float(np.argmax(lv) / max(len(lv) - 1, 1)),
                                   periodic=float(np.mean(an["periodic"][s] >= STRONG)),
                                   spectrum=(spectrum - spectrum.max()).tolist(),
                                   curve=np.interp(np.linspace(0, 1, 12), np.linspace(0, 1, len(lv)), lv).tolist()))

    # --- where the voice starts against the note, after a voiceless consonant or a rest
    for k, n in enumerate(notes):
        onset, _, _ = phones_of(n)
        after_rest = k == 0 or n["start"] - notes[k - 1]["sung_end"] > 0.1
        prev_coda = phones_of(notes[k - 1])[2] if k else []
        if not onset or not all(p in VOICELESS for p in onset):
            continue
        if not after_rest and any(p not in VOICELESS for p in prev_coda):
            continue
        s = span(n["start"] - 0.25, n["start"] + 0.25, n_frames)
        v = an["periodic"][s] >= STRONG
        t = np.arange(s.start, s.stop) * FRAME - n["start"]
        start = None
        for i in range(4, len(v) - 6):
            if not v[i - 4: i].any() and v[i: i + 6].all():
                start = float(t[i])
        if start is not None:
            # the unvoiced stretch before it: the consonants' length, where it's bounded by voice on both sides
            before = np.flatnonzero(v[: int(round((start - t[0]) / FRAME))])
            gap = float(start - t[before[-1]]) if len(before) and not after_rest else None
            out["timing"].append(dict(onset=" ".join(onset), start=start, gap=gap))
    return out


def teacher_job(args) -> tuple[str, dict]:
    seg, cache = args
    return seg.path.stem, measure_segment(teacher_analysis(seg, cache), seg.notes)


def ours_job(args) -> tuple[str, dict, dict]:
    seg, cache, engine, voice_set, seed, keep = args
    if engine.startswith("learned") and ":" in engine:
        os.environ["SONGBIRD_THROAT"] = engine.split(":", 1)[1]
    ours = our_analysis(seg, engine.split(":")[0], voice_set, seed, keep, cache)
    teacher = teacher_analysis(seg, cache)
    return seg.path.stem, measure_segment(ours, seg.notes), distance(teacher, ours, seg.notes)


def distance(teacher: dict, ours: dict, notes: list[dict]) -> dict:
    """Note by note on the frames both voice clearly: the pitch's distance to the teacher's, raw and with
    everything faster than 3 Hz (vibrato, jitter) smoothed away; the note's centre in cents."""
    n = min(len(teacher["f0"]), len(ours["f0"]))
    raw, smooth, centre = [], [], []
    tc_all = [cents_of(teacher, x["pitch"])[:n] for x in notes]
    oc_all = [cents_of(ours, x["pitch"])[:n] for x in notes]
    for k, x in enumerate(notes):
        s = span(x["start"] - 0.1, min(x["sung_end"], x["start"] + x["dur"]), n)
        tc, oc = tc_all[k][s], oc_all[k][s]
        both = ~np.isnan(tc) & ~np.isnan(oc)
        if both.sum() < 10:
            continue
        raw.append(np.sqrt(np.mean((tc[both] - oc[both]) ** 2)))
        ts, os_ = fill(tc, 12), fill(oc, 12)
        ok = ~np.isnan(ts) & ~np.isnan(os_)
        if ok.sum() >= 16:
            d = lowpass(np.where(ok, ts, 0), 3.0) - lowpass(np.where(ok, os_, 0), 3.0)
            smooth.append(np.sqrt(np.mean(d[both & ok] ** 2)))
        centre.append(np.median(tc[both]) - np.median(oc[both]))
    return dict(raw=[float(v) for v in raw], smooth=[float(v) for v in smooth], centre=[float(v) for v in centre])


# ---- summaries --------------------------------------------------------------------------------


def q(values, digits=1) -> list | None:
    v = np.array([x for x in values if x is not None and np.isfinite(x)], dtype=float)
    if not len(v):
        return None
    return [round(float(np.percentile(v, p)), digits) for p in (25, 50, 75)] + [len(v)]


def mean_curve(recs, t_grid) -> list:
    ys = []
    for r in recs:
        t = np.array(r["t"])
        y = np.array([np.nan if v is None else v for v in r["y"]], dtype=float)
        ys.append(np.interp(t_grid, t, y, left=np.nan, right=np.nan))
    if not ys:
        return []
    return [None if not np.isfinite(v) else round(float(v), 3) for v in np.nanmedian(np.array(ys), axis=0)]


def psd_bands(recs, n=512, edges=(0.5, 2, 3.5, 4.5, 6, 7.5, 10, 20, 40)) -> dict:
    if not recs:
        return {}
    w = np.array([r["weight"] for r in recs], dtype=float)
    p = np.average(np.array([r["psd"] for r in recs]), axis=0, weights=w)
    f = np.fft.rfftfreq(n, FRAME)
    out = {}
    for a, b in zip(edges, edges[1:]):
        sel = (f >= a) & (f < b)
        out[f"{a:g}-{b:g}"] = round(float(10 * np.log10(p[sel].sum() * (f[1] - f[0]) + 1e-12)), 1)
    sel = (f >= 3) & (f <= 9)
    out["peak_hz"] = round(float(f[sel][np.argmax(p[sel])]), 2)
    return out


def summarize(per_seg: dict[str, dict]) -> dict:
    recs = {k: [r for seg in per_seg.values() for r in seg[k]] for k in next(iter(per_seg.values()))}
    S: dict = {}
    tr = [r for r in recs["transitions"] if "t50" in r]
    for name, sel in (("all", tr), ("up", [r for r in tr if r["interval"] > 0]), ("down", [r for r in tr if r["interval"] < 0]),
                      ("step", [r for r in tr if abs(r["interval"]) <= 2]), ("leap", [r for r in tr if abs(r["interval"]) >= 3]),
                      ("open", [r for r in tr if r["cls"] == "open"]), ("voiced", [r for r in tr if r["cls"] == "voiced"])):
        S[f"transition.{name}"] = dict(
            t10_ms=q([1000 * r["t10"] for r in sel], 0), t50_ms=q([1000 * r["t50"] for r in sel], 0),
            t90_ms=q([1000 * r["t90"] for r in sel], 0), dur_ms=q([1000 * (r["t90"] - r["t10"]) for r in sel], 0),
            overshoot_c=q([r["overshoot"] for r in sel]), prep_c=q([r["prep"] for r in sel]),
            overshoot_frac=q([r["overshoot"] / abs(r["size"]) for r in sel], 3),
            settle_ms=q([1000 * r["settle"] for r in sel if r["settle"] is not None], 0))
    if tr:
        durs = np.array([r["t90"] - r["t10"] for r in tr])
        sizes = np.array([abs(r["size"]) / 100 for r in tr])
        S["transition.dur_per_semitone_ms"] = round(float(np.polyfit(sizes, durs, 1)[0] * 1000), 1)
    grid = np.arange(-0.25, 0.35, 0.01)
    S["transition.curve"] = dict(t=[round(x, 3) for x in grid],
                                 up=mean_curve([r for r in recs["transitions"] if r["interval"] > 0 and r["cls"] != "voiceless"], grid),
                                 down=mean_curve([r for r in recs["transitions"] if r["interval"] < 0 and r["cls"] != "voiceless"], grid))
    sc = recs["scoops"]
    for cls in ("vowel", "open", "voiced", "voiceless"):
        sel = [r for r in sc if r.get("onset") == cls]
        S[f"scoop.{cls}"] = dict(early_c=q([r["early"] for r in sel if r["early"] is not None]),
                                 curve=mean_curve(sel, np.arange(-0.1, 0.35, 0.02)))
    S["scoop"] = dict(start_c=q([r["start"] for r in sc]), first50ms_c=q([r["mean50"] for r in sc]),
                      early_c=q([r["early"] for r in sc if r.get("early") is not None]),
                      arrive_ms=q([1000 * r["arrive"] for r in sc if r["arrive"] is not None], 0),
                      voice_ms=q([1000 * r["t_voice"] for r in sc], 0),
                      curve=mean_curve(sc, np.arange(-0.1, 0.35, 0.02)))
    held = recs["held"]
    for name, lo, hi in (("short", 0.0, 0.5), ("mid", 0.5, 0.9), ("long", 0.9, 1.5), ("longest", 1.5, 99)):
        sel = [r for r in held if lo <= r["dur"] < hi]
        S[f"held.{name}"] = dict(extent_c=q([r["extent"] for r in sel]), rate_hz=q([r["rate"] for r in sel], 2),
                                 vibrato_share=round(float(np.mean([r["extent"] >= 12 for r in sel])), 2) if sel else None,
                                 wander_c=q([r["wander"] for r in sel]), fast_c=q([r["fast"] for r in sel]),
                                 rate_cv=q([r["rate_cv"] for r in sel if r["rate_cv"] is not None], 3),
                                 extent_cv=q([r["extent_cv"] for r in sel], 3))
    vib = [r for r in held if r["extent"] >= 12 and r["dur"] >= 0.6]
    if vib:
        S["vibrato.between_notes"] = dict(rate_sd=round(float(np.std([r["rate"] for r in vib])), 2),
                                          extent_sd=round(float(np.std([r["extent"] for r in vib])), 1),
                                          extent_mean=round(float(np.mean([r["extent"] for r in vib])), 1), n=len(vib))
        # how vibrato grows through a note: the median envelope against time from the note's start
        tg = np.arange(0.15, 1.6, 0.05)
        curves = [np.interp(tg, r["env_t"], r["env"], left=np.nan, right=np.nan) for r in held if r["dur"] >= 1.0]
        S["vibrato.growth"] = dict(t=[round(x, 2) for x in tg],
                                   extent=[None if not np.isfinite(v) else round(float(v), 1) for v in np.nanmedian(curves, axis=0)]) if curves else {}
    S["f0_psd_db"] = psd_bands(recs["f0_psd"])
    S["level_psd_db"] = psd_bands(recs["level_psd"])
    S["line_level_psd_db"] = psd_bands(recs["line_psd"], n=2048, edges=(0.5, 1, 2, 3, 4, 6, 8, 12, 20))
    for cls in ("open", "voiced", "voiceless"):
        sel = [r for r in recs["micro"] if r["cls"] == cls]
        S[f"micro.{cls}"] = dict(n=len(sel), curve=mean_curve(sel, np.arange(-0.15, 0.16, 0.025)))
    fin = recs["finals"]
    S["final"] = dict(fall_c=q([r["fall"] for r in fin if r["fall"] is not None]),
                      voice_end_ms=q([1000 * r["voice_end"] for r in fin], 0),
                      level_last300=[round(float(v), 1) for v in np.nanmedian([np.interp(np.linspace(0, 1, 10), np.linspace(0, 1, len(r["level"])), r["level"]) for r in fin], axis=0)] if fin else [])
    nts = [r for r in recs["notes"] if np.isfinite(r["level"])]
    if nts:
        names = ("stressed", "unstressed", "function", "first", "last", "climb", "vel", "focus")
        X = np.array([[float(r[k]) for k in names] + [1.0] for r in nts])
        yv = np.array([r["level"] for r in nts])
        coef, *_ = np.linalg.lstsq(X, yv, rcond=None)
        resid = yv - X @ coef
        S["level.fit_db"] = {k: round(float(c), 2) for k, c in zip(names + ("const",), coef)}
        S["level.fit_db"]["resid_sd"] = round(float(np.std(resid)), 2)
        S["level.fit_db"]["r2"] = round(float(1 - resid.var() / yv.var()), 3)
        S["level.syllable_sd_db"] = round(float(np.std(yv)), 2)
        S["level.by_pos"] = [round(float(np.median([r["level"] for r in nts if a <= r["pos"] < b] or [np.nan])), 2)
                             for a, b in ((0, 0.01), (0.01, 0.34), (0.34, 0.67), (0.67, 0.99), (0.99, 1.01))]
        S["tune.centre_c"] = q([r["tune"] for r in nts if np.isfinite(r["tune"])])
    env = recs["envelopes"]
    for name, lo, hi in (("short", 0.25, 0.45), ("mid", 0.45, 0.8), ("long", 0.8, 99)):
        sel = [r for r in env if lo <= r["dur"] < hi]
        S[f"envelope.{name}"] = dict(n=len(sel), attack_ms=q([1000 * r["attack"] for r in sel], 0),
                                     peak_at=q([r["peak_at"] for r in sel], 2), taper_db=q([r["taper"] for r in sel]),
                                     curve=[round(float(v), 1) for v in np.median([r["curve"] for r in sel], axis=0)] if sel else [])
    br = recs["breaths"]
    open_br = [r for r in br if r.get("coda") == "open"]
    S["breath.after_open"] = dict(n=len(open_br), peak_db=q([r["peak"] for r in open_br]), mean_db=q([r["mean"] for r in open_br]),
                                  audible_s=q([r["audible"] for r in open_br], 3), peak_at=q([r["peak_at"] for r in open_br], 2),
                                  spectrum_db=[round(float(v), 1) for v in np.median([r["spectrum"] for r in open_br], axis=0)] if open_br else [],
                                  curve=[round(float(v), 1) for v in np.median([r["curve"] for r in open_br], axis=0)] if open_br else [])
    S["breath"] = dict(n=len(br), gap_s=q([r["gap"] for r in br], 2), peak_db=q([r["peak"] for r in br]),
                       mean_db=q([r["mean"] for r in br]), floor_db=q([r["floor"] for r in br]),
                       audible_s=q([r["audible"] for r in br], 3), peak_at=q([r["peak_at"] for r in br], 2),
                       periodic=q([r["periodic"] for r in br], 2),
                       spectrum_db=[round(float(v), 1) for v in np.median([r["spectrum"] for r in br], axis=0)] if br else [],
                       curve=[round(float(v), 1) for v in np.median([r["curve"] for r in br], axis=0)] if br else [])
    tm = recs["timing"]
    S["timing"] = dict(voice_start_ms=q([1000 * r["start"] for r in tm], 0),
                       after_rest_ms=q([1000 * r["start"] for r in tm if r["gap"] is None], 0),
                       consonant_gap_ms=q([1000 * r["gap"] for r in tm if r["gap"] is not None], 0))
    return S


def run_measure(args) -> None:
    corpus = args.corpus
    cache = args.cache
    segs = load_segments(corpus, set(args.source), args.split, args.singers)
    if args.limit:
        segs = segs[: args.limit]
    voice_set = {}
    for kv in args.set:
        k, v = kv.split("=")
        from songbird.synth.voice import VoiceParams

        voice_set[k] = type(getattr(VoiceParams(), k))(v)
    print(f"{len(segs)} segments ({args.split}, {', '.join(args.source)})", flush=True)
    per_seg, dist = {}, {"raw": [], "smooth": [], "centre": []}
    with ProcessPoolExecutor(args.jobs) as pool:
        if args.engine == "teacher":
            for name, m in pool.map(teacher_job, [(s, cache) for s in segs]):
                per_seg[name] = m
        else:
            keep = args.keep
            jobs = [(s, cache, args.engine, voice_set, args.seed, keep) for s in segs]
            for name, m, d in pool.map(ours_job, jobs):
                per_seg[name] = m
                for k in dist:
                    dist[k] += d[k]
    summary = summarize(per_seg)
    if args.engine != "teacher":
        summary["distance"] = dict(raw_c=q(dist["raw"]), smooth_c=q(dist["smooth"]), centre_c=q(dist["centre"]),
                                   smooth_rms_c=round(float(np.sqrt(np.mean(np.square(dist["smooth"])))), 1) if dist["smooth"] else None)
    about = dict(engine=args.engine, split=args.split, source=args.source, set=voice_set, seed=args.seed,
                 segments=len(segs), model=os.environ.get("SONGBIRD_THROAT", ""))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"about": about, "summary": summary}, indent=1))
    if args.raw:
        args.raw.write_text(json.dumps(per_seg))
    print(f"-> {args.out}")


def flat(summary: dict, prefix="") -> dict:
    out = {}
    for k, v in summary.items():
        if isinstance(v, dict):
            out |= flat(v, f"{prefix}{k}.")
        else:
            out[f"{prefix}{k}"] = v
    return out


def run_table(args) -> None:
    runs = [json.loads(Path(p).read_text()) for p in args.files]
    rows = [flat(r["summary"]) for r in runs]

    def curve(k: str) -> bool:
        return k.endswith(".t") or any(x in k for x in ("curve", "growth", "spectrum", "level_last", "by_pos"))

    keys = [k for k in dict.fromkeys(k for r in rows for k in r) if not curve(k)]
    names = [Path(p).stem for p in args.files]
    print(f"{'':42}" + "".join(f"{n[:26]:>28}" for n in names))
    for k in keys:
        if args.grep and args.grep not in k:
            continue
        cells = []
        for r in rows:
            v = r.get(k)
            if isinstance(v, list) and len(v) == 4 and all(isinstance(x, (int, float)) for x in v):
                cells.append(f"{v[1]:g} [{v[0]:g},{v[2]:g}] n{v[3]}")
            else:
                cells.append(str(v))
        print(f"{k:42}" + "".join(f"{c[:27]:>28}" for c in cells))
    if args.curves:
        for k in dict.fromkeys(k for r in rows for k in r):
            if curve(k) and not k.endswith(".t") and (not args.grep or args.grep in k):
                print(k)
                for n, r in zip(names, rows):
                    v = r.get(k) or []
                    print(f"  {n[:20]:20} " + " ".join("   ." if x is None else f"{x:5.2f}" if abs(x) < 10 else f"{x:5.0f}" for x in v))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--corpus", type=Path, default=ROOT / "renders/throat/corpus")
    m.add_argument("--cache", type=Path, default=ROOT / "renders/delivery/cache")
    m.add_argument("--source", nargs="*", default=["formant"])
    m.add_argument("--singers", nargs="*", default=None)
    m.add_argument("--split", default="all", choices=("fit", "held", "all"))
    m.add_argument("--engine", default="teacher", help="teacher, formant, or learned[:model.npz]")
    m.add_argument("--set", nargs="*", default=[], metavar="FIELD=VALUE", help="VoiceParams fields for ours")
    m.add_argument("--seed", type=int, default=1)
    m.add_argument("--limit", type=int, default=0)
    m.add_argument("--jobs", type=int, default=3)
    m.add_argument("--keep", type=Path, default=None, help="write our renders here")
    m.add_argument("--raw", type=Path, default=None, help="also write every per-note record here")
    m.add_argument("--out", type=Path, required=True)
    t = sub.add_parser("table")
    t.add_argument("files", nargs="+")
    t.add_argument("--grep", default="")
    t.add_argument("--curves", action="store_true")
    args = ap.parse_args()
    {"measure": run_measure, "table": run_table}[args.cmd](args)


if __name__ == "__main__":
    main()
