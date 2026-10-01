"""Public-domain folk singing as training material for the learned throat (dev only).

    uv run python tools/throat/folk.py fetch WORK MANIFEST.json      # the recordings, into WORK/sources/
    uv run python tools/throat/folk.py separate WORK --python DEMUCS_VENV/bin/python   # sung alone or not
    uv run python tools/throat/folk.py transcribe WORK [--model medium.en]
    uv run python tools/throat/folk.py cut WORK [--jobs 6]
    uv run python tools/throat/features.py WORK/corpus --out WORK/features
    uv run python tools/throat/phones.py WORK/corpus
    uv run python tools/throat/check.py WORK --cents 200 --min-tune 0.75
    uv run python tools/throat/dataset.py WORK --out WORK/dataset-folk.npz
    uv run python tools/throat/folk.py merge WORK [--house renders/throat/dataset-house.npz]
        [--base songbird/synth/throat.npz]

WORK is a scratch directory of your choosing, never renders/ or recordings/.

What it reads. MANIFEST is a JSON list, one recording each: {"id", "url", "title", "performer",
"licence", "page", "singer" ("folk" for singing its singers released themselves, "records" for
commercial records old enough to be public domain), "year", optionally "lyrics" (the printed words,
public domain like the tune), "start"/"end" (seconds to keep)}. `separate` marks each one "accompanied" or
not (Demucs's accompaniment stem against its voice); an accompanied one is left out, or with --separated
its voice taken out of the band (WORK/vocals/<id>.wav) is used. Every source's licence and page stay
in WORK/manifest.json; nothing about them goes into the model but the singer's name and "human".

How a recording with no score is labelled (the volunteers' takes had their guides' scores; these have
only the singing):
- `transcribe`: faster-whisper's words, each with its start, end and probability, prompted with the
  printed words where the manifest has them.
- `cut`: the words are corrected against the printed words where there are some (a word Whisper
  heard differently inside a stretch that otherwise matches is taken as printed), grouped into lines
  at the gaps between them (LINE_GAP) and the lines into segments of at most SEGMENT seconds. Each
  line is aligned with the Montreal Forced Aligner against our own pronunciation of its words (as
  phones.py does it; voices above A3 an octave down). Each syllable is then one note: its phones
  from songbird.phonetics, its span from the alignment, its pitch the median of what was sung on its
  vowel (Harvest), rounded to the semitone. A melisma is one note sung over several pitches, which is
  fine: the network is given the f0 sung, never the note.
- What can't be trusted is left out or masked: a line with a word no dictionary has, with words that
  look like the LibriVox announcements, or that isn't sung (a spoken line's vowels are short and its
  pitch glides: SUNG); a note whose word Whisper wasn't sure of, whose vowel is mostly unvoiced, or
  whose phones the aligner stretched past belief ("doubt" in its label, which dataset.py masks).
- Every recording is brought to the house corpus's level, as the volunteers' takes were, and its
  background (the quietest unvoiced frames against the singing) must be at least --min-quiet dB down.
  Reverb isn't gated (a decay read off phrase ends measured the singers' own releases, not the rooms); on
  house audio with an RT60 of 0.7 s the aligner's phone starts within 20 ms of the scored ones fell from
  94% to 67%, so a reverberant recording teaches blurrier boundaries, partly masked as doubtful.
- Bandwidth: a record made before 1926 has nothing above about 4 kHz but noise, and its noise would
  read as breath. Each recording's band is measured (the highest frequency where its sung spectrum
  stands --band-db above its quiet frames'), and the label says so ("band_hz"); dataset.py writes it per
  frame and train.py learns the envelope only below it. A record's aperiodicity is not learned at all
  ("ap_band_hz" 0): through surface noise, D4C hears breath everywhere.

Each performer is a singer of their own ("folk-<performer>", source "folk"; "record-..." for records):
pooled into one row, many people's voices and dialects would leave the network nothing to explain their
differences with, and it would average them away (flat formants, blurred vowels). A voice made from them
is a blend of rows (throat.timbre), never one alone, as for the house singers. Their source isn't
"human": that names the volunteers, whose share of a blend is fixed (throat.HUMAN_SHARE).

`merge` adds the folk frames to the house dataset and keeps every singer the base model knows (with
--base; the volunteers, whose takes are gone) in the singer list with no frames, so a fine-tune from it
keeps their row.
"""

from __future__ import annotations

import argparse
import difflib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from phones import LOCK, MFA, SKIP, textgrid  # noqa: E402
from soulx import syllables  # noqa: E402

from songbird import phonetics as P  # noqa: E402

SOURCES = {"folk": "folk", "records": "record"}  # a singer's source by its group: not "human", the volunteers' share
SR = 24000  # the corpus's rate
FRAME = 0.005
PAUSE = 0.15  # seconds of quiet in the audio between two words that ends a line
LINE_MAX = 16.0  # seconds: a longer line is split at its quietest point between words
SEGMENT = 24.0  # seconds: lines are gathered into segments up to this long
SEGMENT_GAP = 1.6  # a gap this long between lines always starts a new segment
LEAD, TAIL = 0.25, 0.3  # seconds of a pause kept before a line and after it
HOUSE = Path(os.environ.get("THROAT_HOUSE", ROOT / "renders/throat"))  # the house corpus (a worktree has no renders/)
HIGH = 57  # MIDI: lines whose median pitch is at or above A3 are aligned an octave down (as phones.py does)
DEFICIT = 15.0  # dB under a full-band voice's spectrum that ends a recording's band
SUNG = dict(vowel_s=0.16, steady=0.45)  # a line is sung if its median vowel and its steady-pitch share reach these
BOILERPLATE = re.compile(r"librivox|public domain|recording|volunteer|information|end of (section|track|song)|"
                         r"read by|sung by|performed by|chapter|section|copyright", re.I)


def work_ok(work: Path) -> Path:
    work = work.resolve()
    for forbidden in (ROOT / "renders", ROOT / "recordings"):
        if work == forbidden or forbidden in work.parents:
            raise SystemExit(f"{work} is inside {forbidden}: give a scratch directory")
    return work


# --- fetch ----------------------------------------------------------------------------------------------


def fetch(args) -> None:
    work = work_ok(args.work)
    items = json.loads(args.manifest.read_text())
    ids = [it["id"] for it in items]
    if len(set(ids)) != len(ids):
        raise SystemExit("ids in the manifest must be unique")
    src = work / "sources"
    src.mkdir(parents=True, exist_ok=True)
    for it in items:
        ext = Path(it["url"].split("?")[0]).suffix.lower() or ".audio"
        dest = src / f"{it['id']}{ext}"
        if not dest.exists():
            download(it["url"], dest)
        it["file"] = dest.name
        it["sha256"] = hashlib.sha256(dest.read_bytes()).hexdigest()
        print(f"{it['id']}: {dest.stat().st_size / 1e6:.1f} MB", flush=True)
    (work / "manifest.json").write_text(json.dumps(items, indent=1))
    print(f"{len(items)} recordings in {src}; their licences and pages in {work / 'manifest.json'}")


def download(url: str, dest: Path, tries: int = 6) -> None:
    """One file, politely: a second between files, and a server that says too many requests waited out."""
    req = urllib.request.Request(url, headers={"User-Agent": "songbird-research/0.1 (folk singing study)"})
    tmp = dest.with_suffix(dest.suffix + ".part")
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            tmp.rename(dest)
            if not url.startswith("file:"):
                time.sleep(1.0)
            return
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or k == tries - 1:
                raise
            time.sleep(float(e.headers.get("Retry-After") or 0) or 5.0 * 2**k)


def load_audio(path: Path, sr: int, start: float | None = None, end: float | None = None) -> np.ndarray:
    """Any audio file as mono float64 at sr, through ffmpeg."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    if end:
        cmd += ["-to", f"{end:.3f}"]
    cmd += ["-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f64le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float64).copy()


def source_of(work: Path, it: dict) -> Path:
    if it.get("accompanied"):
        v = work / "vocals" / f"{it['id']}.wav"
        if not v.exists():
            raise FileNotFoundError(f"{it['id']} is accompanied and {v} isn't there (separate it first)")
        return v
    return work / "sources" / it["file"]


# --- separate -------------------------------------------------------------------------------------------


ACCOMPANIED_DB = -25.0  # dB: band (Demucs's accompaniment stem) against voice, where the voice sings, that counts as accompanied


def separate(args) -> None:
    """Every recording through Demucs (MIT; run from its own environment: --python, or DEMUCS_PYTHON), to
    hear whether it is sung alone: where the voice stem sings, the accompaniment stem's level against it.
    Over ACCOMPANIED_DB, the recording is marked accompanied in WORK/manifest.json and its voice kept as
    WORK/vocals/<id>.wav (transcribe and cut leave it out unless --separated); under it, it is sung alone
    and the source is used as it is. The numbers go to WORK/separation.json."""
    work = work_ok(args.work)
    items = json.loads((work / "manifest.json").read_text())
    report_path = work / "separation.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    todo = [it for it in items if it["id"] not in report and (not args.only or it["id"] in args.only)]
    (work / "vocals").mkdir(exist_ok=True)
    tmp = work / "demucs"
    for k in range(0, len(todo), 8):  # a few at a time: the model loads once per call
        batch = todo[k: k + 8]
        cmd = [args.python, "-m", "demucs", "--two-stems", "vocals", "-n", args.model, "-d", args.device,
               "-o", str(tmp)] + [str(work / "sources" / it["file"]) for it in batch]
        run = subprocess.run(cmd, capture_output=True, text=True, check=False)
        for it in batch:
            stems = tmp / args.model / Path(it["file"]).stem
            if run.returncode != 0 or not (stems / "vocals.wav").exists():
                print(f"{it['id']}: demucs failed: {run.stderr[-500:]}", flush=True)
                continue
            v = load_audio(stems / "vocals.wav", 16000)
            a = load_audio(stems / "no_vocals.wav", 16000)
            hop = 800  # 50 ms
            n = min(len(v), len(a)) // hop
            ev = (v[: n * hop].reshape(n, hop) ** 2).mean(axis=1)
            ea = (a[: n * hop].reshape(n, hop) ** 2).mean(axis=1)
            singing = 10 * np.log10(ev + 1e-20) > np.percentile(10 * np.log10(ev + 1e-20), 95) - 20
            acc = float(10 * np.log10(ea[singing].sum() / (ev[singing].sum() + 1e-20) + 1e-20))
            report[it["id"]] = dict(accompaniment_db=round(acc, 1), accompanied=acc > ACCOMPANIED_DB)
            if acc > ACCOMPANIED_DB:
                shutil.move(str(stems / "vocals.wav"), work / "vocals" / f"{it['id']}.wav")
            shutil.rmtree(stems, ignore_errors=True)
            print(f"{it['id']}: accompaniment {acc:+.1f} dB" + ("  ACCOMPANIED" if acc > ACCOMPANIED_DB else ""), flush=True)
        report_path.write_text(json.dumps(report, indent=1))
    for it in items:
        if it["id"] in report:
            it["accompanied"] = report[it["id"]]["accompanied"]
    (work / "manifest.json").write_text(json.dumps(items, indent=1))
    alone = sum(1 for r in report.values() if not r["accompanied"])
    print(f"{len(report)} recordings heard: {alone} sung alone, {len(report) - alone} accompanied")


# --- transcribe -----------------------------------------------------------------------------------------


def transcribe(args) -> None:
    from faster_whisper import WhisperModel

    work = work_ok(args.work)
    items = json.loads((work / "manifest.json").read_text())
    out = work / "words"
    out.mkdir(exist_ok=True)
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=args.threads)
    for it in items:
        dest = out / f"{it['id']}.json"
        if dest.exists() or (args.only and it["id"] not in args.only) or (it.get("accompanied") and not args.separated):
            continue
        try:
            path = source_of(work, it)
        except FileNotFoundError as e:
            print(f"{it['id']}: {e}")
            continue
        x = load_audio(path, 16000, it.get("start"), it.get("end")).astype(np.float32)
        prompt = " ".join((it.get("lyrics") or "").split()[:120]) or None
        segs, _ = model.transcribe(x, language="en", word_timestamps=True, initial_prompt=prompt,
                                      condition_on_previous_text=False, vad_filter=False, beam_size=5,
                                      temperature=0.0)
        words = [dict(word=w.word.strip(), start=round(w.start, 3), end=round(w.end, 3), p=round(w.probability, 3))
                 for s in segs for w in (s.words or [])]
        dest.write_text(json.dumps(dict(id=it["id"], model=args.model, seconds=round(len(x) / 16000, 2),
                                        words=words), indent=0))
        print(f"{it['id']}: {len(words)} words, {len(x) / 16000:.0f} s", flush=True)


# --- cut ------------------------------------------------------------------------------------------------


def norm(word: str) -> str:
    return re.sub(r"[^a-z'\-]", "", word.lower().replace("’", "'")).strip("'-")


def reading(word: str) -> list[str] | None:
    """Our pronunciation of a sung word (stress digits kept), or None. A dropped g (wanderin') is read
    as the -ing word ending in N."""
    dropped = re.sub(r"[^a-z']", "", word.lower().replace("’", "'")).endswith("in'")  # before norm() strips the '
    w = norm(word)
    if not w:
        return None

    def ing(stem: str) -> list[str] | None:
        r = P.pronunciations(stem + "g")
        return list(r[0][:-1]) + ["N"] if r and r[0][-1] == "NG" else None

    def sung(r: list[str] | None) -> list[str] | None:
        """A reading as the program sings it: none with no vowel ("hm", "sh"); a diphthong's -er one syllable with
        it (fire, wire, hour: AY R, as songbird.phonetics.fit sings fi-er on a note, which the dataset makes AYR).
        Read as two syllables, a folk corpus never sings AYR and the network forgets it: "fire" came out "fi"."""
        if not r or not any(p[-1:].isdigit() for p in r):
            return None
        return [("R" if p == "ER0" and k and r[k - 1].rstrip("012") in ("AY", "AW", "OY") else p) for k, p in enumerate(r)]

    if dropped and ing(w):  # rollin' (rollin alone is a name in the dictionary)
        return sung(ing(w))
    for candidate in (w, w.replace("'", "")):
        r = P.pronunciations(candidate)
        if r:
            return sung(list(r[0]))
    return sung(ing(w)) if w.endswith("in") else None


def corrected(words: list[dict], lyrics: str | None) -> list[dict]:
    """Whisper's words with the printed ones where a stretch otherwise matches: a word heard differently
    between matching neighbours, one for one, is taken as printed (and trusted as much as its neighbours)."""
    if not lyrics:
        return words
    printed = [norm(w) for w in lyrics.split() if norm(w)]
    heard = [norm(w["word"]) for w in words]
    out = [dict(w) for w in words]
    sm = difflib.SequenceMatcher(a=heard, b=printed, autojunk=False)
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal":
            for i in range(a0, a1):
                out[i]["printed"] = True
        elif op == "replace" and a1 - a0 == b1 - b0 and a1 - a0 <= 3:
            for i, j in zip(range(a0, a1), range(b0, b1)):
                if heard[i] and printed[j]:
                    out[i]["heard"], out[i]["word"] = out[i]["word"], printed[j]
                    out[i]["printed"] = True
                    out[i]["p"] = max(out[i]["p"], 0.6)
    return out


def pauses(level: np.ndarray, f0: np.ndarray, sing_db: float, back_db: float) -> list[tuple[float, float]]:
    """Stretches (seconds) of real quiet: unvoiced, nearer the background than the singing, PAUSE long."""
    quiet = (f0 <= 0) & (level < 0.5 * (sing_db + back_db))
    out, k = [], 0
    while k < len(quiet):
        if quiet[k]:
            j = k
            while j < len(quiet) and quiet[j]:
                j += 1
            if (j - k) * FRAME >= PAUSE:
                out.append((k * FRAME, j * FRAME))
            k = j
        else:
            k += 1
    return out


def lines_from(words: list[dict], quiet: list[tuple[float, float]], level: np.ndarray, dur: float):
    """The words in lines, each line with its audio's span (t0, t1). A line ends at a pause in the audio
    between two words (Whisper's word ends come early on a held note, so its gaps can't be trusted); a
    line longer than LINE_MAX is split at the quietest point between two of its words."""
    mids = [0.5 * (w["start"] + w["end"]) for w in words]
    breaks = {}  # index k: the pause between words k and k+1
    for a, b in quiet:
        c = 0.5 * (a + b)
        k = int(np.searchsorted(mids, c)) - 1
        if 0 <= k < len(words) - 1 and (k not in breaks or b - a > breaks[k][1] - breaks[k][0]):
            breaks[k] = (a, b)
    groups, cur = [], []
    for k, w in enumerate(words):
        cur.append(k)
        if k in breaks or k == len(words) - 1:
            groups.append(cur)
            cur = []
    out = []  # (word indices, t0, t1)
    for g in groups:
        stack = [g]
        while stack:
            h = stack.pop(0)
            if words[h[-1]]["end"] - words[h[0]]["start"] <= LINE_MAX or len(h) < 4:
                out.append(h)
                continue
            dips = []
            for i in range(1, len(h) - 2):
                a, b = int(mids[h[i]] / FRAME), int(mids[h[i + 1]] / FRAME)
                dips.append(float(level[a:b].min()) if b > a else 0.0)
            i = 1 + int(np.argmin(dips))
            stack[:0] = [h[: i + 1], h[i + 1:]]
    spans = []
    for n, h in enumerate(out):
        before = breaks.get(out[n - 1][-1]) if n else None
        after = breaks.get(h[-1]) if n + 1 < len(out) else None
        if before:
            t0 = max(0.5 * (before[0] + before[1]), before[1] - LEAD)
        elif n:  # split without a pause: at the quietest frame between the two words
            a, b = int(mids[out[n - 1][-1]] / FRAME), int(mids[h[0]] / FRAME)
            t0 = (a + int(np.argmin(level[a:b]))) * FRAME if b > a else words[h[0]]["start"]
        else:
            t0 = max(0.0, words[h[0]]["start"] - LEAD)
        if after:
            t1 = min(0.5 * (after[0] + after[1]), after[0] + TAIL)
        elif n + 1 < len(out):
            a, b = int(mids[h[-1]] / FRAME), int(mids[out[n + 1][0]] / FRAME)
            t1 = (a + int(np.argmin(level[a:b]))) * FRAME if b > a else words[h[-1]]["end"]
        else:
            t1 = min(dur, words[h[-1]]["end"] + 1.0)
        spans.append(([words[k] for k in h], round(t0, 4), round(t1, 4)))
    return spans


def f0_of(x: np.ndarray, sr: int) -> np.ndarray:
    import pyworld as pw

    x16 = x if sr == 16000 else np.interp(np.arange(0, len(x), sr / 16000), np.arange(len(x)), x)
    f0, _ = pw.harvest(x16, 16000, f0_floor=55.0, f0_ceil=1000.0, frame_period=FRAME * 1000)
    return f0


def levels(x: np.ndarray, sr: int, n: int) -> np.ndarray:
    hop = int(round(FRAME * sr))
    pad = np.pad(x, (hop, hop * (n + 2)))
    return 20 * np.log10(np.maximum(np.array([np.sqrt(np.mean(pad[i * hop: i * hop + 2 * hop] ** 2) + 1e-20)
                                              for i in range(n)]), 1e-6))


BAND_GRID = np.geomspace(150.0, 11800.0, 160)  # Hz: where a recording's sung spectrum is compared


def sung_spectrum(x: np.ndarray, sr: int, f0: np.ndarray) -> np.ndarray | None:
    """The average spectrum (dB) of the voiced frames on BAND_GRID, 1/6-octave smoothed."""
    from scipy.signal import stft

    f, t, X = stft(x, sr, nperseg=1024, noverlap=512)
    p = np.abs(X) ** 2
    sung = f0[np.clip((t / FRAME).astype(int), 0, len(f0) - 1)] > 0
    if sung.sum() < 20:
        return None
    return smooth_db(f, p[:, sung].mean(axis=1))


def smooth_db(f: np.ndarray, power: np.ndarray) -> np.ndarray:
    out = []
    for g in BAND_GRID:
        sel = (f >= g * 2 ** (-1 / 12)) & (f <= g * 2 ** (1 / 12))
        out.append(10 * np.log10(power[sel].mean() + 1e-20) if sel.any() else -200.0)
    return np.array(out)


def reference_spectrum() -> np.ndarray:
    """The house corpus's sung spectrum (a few dozen segments), the shape a full-band voice has."""
    import soundfile as sf

    specs = []
    for wav in sorted((HOUSE / "corpus").glob("house-*/*.wav"))[::10]:
        x, sr = sf.read(str(wav), dtype="float64")
        s = sung_spectrum(x, sr, f0_of(x, sr))
        if s is not None:
            specs.append(s - np.median(s[(BAND_GRID > 300) & (BAND_GRID < 2000)]))
    return np.median(specs, axis=0)


def band_of(x: np.ndarray, sr: int, f0: np.ndarray, level: np.ndarray, band_db: float, ref: np.ndarray) -> float:
    """The top of the recording's band (Hz): the highest frequency, counting up from the voice's own
    region, where its sung spectrum is no more than DEFICIT dB under a full-band voice's shape (the house
    corpus's, matched at 300 Hz-2 kHz; an MP3's lowpass or an old record's roll-off fails this) and stands
    band_db over its quietest frames (its silences; surface noise filling the top fails this)."""
    from scipy.signal import stft

    s = sung_spectrum(x, sr, f0)
    if s is None:
        return 0.0
    voice = (BAND_GRID > 300) & (BAND_GRID < 2000)
    deficit = (ref + np.median(s[voice])) - s
    ok = deficit <= DEFICIT
    quiet = level <= np.percentile(level, 2)
    f, t, X = stft(x, sr, nperseg=1024, noverlap=512)
    q = quiet[np.clip((t / FRAME).astype(int), 0, len(level) - 1)]
    if q.sum() >= 5:
        ok &= s - smooth_db(f, (np.abs(X[:, q]) ** 2).mean(axis=1)) >= band_db
    ok &= BAND_GRID < sr / 2 * 0.98
    top = None
    for i in range(int(np.argmax(BAND_GRID > 1000)), len(BAND_GRID)):
        if not ok[i]:
            break
        top = i
    return float(BAND_GRID[top]) if top is not None else 0.0


def house_level() -> float:
    feats = sorted((HOUSE / "features").glob("house-*/*.npz"))[::25]
    lv = []
    for f in feats:
        z = np.load(f)
        lv.append(np.median(z["level"][z["f0"] > 0]))
    return float(np.median(lv)) if lv else -20.0


def token_for(word: str, phones: tuple, seen: dict) -> str:
    key = (word, phones)
    if key not in seen:
        base = re.sub(r"[^a-z]", "", word.lower()) or "w"
        n = sum(1 for w, _ in seen if (re.sub(r"[^a-z]", "", w.lower()) or "w") == base)
        seen[key] = f"{base}q{n}"
    return seen[key]


def lowered(x: np.ndarray, sr: int, f0: np.ndarray) -> np.ndarray:
    """The audio an octave down with its spectral envelope kept (WORLD), for the aligner; f0 is the pitch already
    tracked for it (FRAME apart from its first sample)."""
    import pyworld as pw

    n = int(len(x) / sr / FRAME) + 1
    f0 = np.ascontiguousarray(np.pad(f0[:n], (0, max(0, n - len(f0))))).astype(np.float64)
    t = np.arange(n) * FRAME
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)
    return pw.synthesize(f0 / 2, sp, ap, sr, FRAME * 1000)


def prepare(work: Path, it: dict, target_db: float, min_quiet: float, band_db: float, ref: np.ndarray) -> dict:
    """One recording's lines: written for MFA under WORK/mfa/corpus/<id>/, with what cut needs afterwards."""
    from scipy.signal import resample_poly

    words_path = work / "words" / f"{it['id']}.json"
    if not words_path.exists():
        return dict(id=it["id"], skipped="not transcribed")
    x = load_audio(source_of(work, it), SR, it.get("start"), it.get("end"))
    cache = work / "cache" / f"{it['id']}.{(it.get('sha256') or 'x')[:12]}.{it.get('start')}-{it.get('end')}.f0.npy"
    if cache.exists():  # Harvest over a whole recording is most of cut's time: kept between runs
        f0 = np.load(cache).astype(np.float64)
    else:
        f0 = f0_of(x, SR)
        cache.parent.mkdir(exist_ok=True)
        np.save(cache, f0.astype(np.float32))
    n = len(f0)
    lv = levels(x, SR, n)
    words = corrected(json.loads(words_path.read_text())["words"], it.get("lyrics"))
    info = dict(id=it["id"], seconds=round(len(x) / SR, 1), words=len(words))
    sung = f0 > 0
    if sung.sum() < 200:
        return dict(info, skipped="hardly any voicing")
    sing_db = float(np.median(lv[sung]))
    # the background: the quietest of the unvoiced frames (the pauses; Whisper's word ends come early on a
    # held note, so the gaps between its words are no measure)
    back_db = float(np.percentile(lv[~sung], 5)) if (~sung).sum() > 100 else float(np.percentile(lv, 2))
    info.update(singing_db=round(sing_db, 1), background_db=round(back_db - sing_db, 1))
    if back_db - sing_db > -min_quiet:
        return dict(info, skipped=f"background {back_db - sing_db:+.1f} dB against the singing")
    band = band_of(x, SR, f0, lv, band_db, ref)
    if it.get("max_band_hz"):
        band = min(band, float(it["max_band_hz"]))
    info["band_hz"] = round(band)
    gain = 10 ** ((target_db - sing_db) / 20)
    x = x * gain
    if np.max(np.abs(x)) > 0.99:
        x = x * 0.99 / np.max(np.abs(x))
    np.save(work / "mfa" / "audio" / f"{it['id']}.npy", x.astype(np.float32))
    np.save(work / "mfa" / "audio" / f"{it['id']}.f0.npy", f0.astype(np.float32))
    lines = []
    found = lines_from(words, pauses(lv, f0, sing_db, back_db), lv, len(x) / SR)
    for li, (ln, t0, t1) in enumerate(found):
        text = " ".join(w["word"] for w in ln)
        why = None
        if BOILERPLATE.search(text):
            why = "announcement"
        ph = [reading(w["word"]) for w in ln]
        if why is None and any(p is None for p in ph):
            why = "a word no dictionary has: " + ", ".join(w["word"] for w, p in zip(ln, ph) if p is None)
        if why is None and any(re.search(r"\d", w["word"]) for w in ln):
            why = "a number"
        if why is None and t1 - t0 > LINE_MAX + 4.0:  # a few words spread over too long: their times are wrong
            why = f"{t1 - t0:.0f} s for {len(ln)} words"
        if why is None and t1 - t0 < 0.3:
            why = f"a span of {t1 - t0:.2f} s ({t0:.2f}-{t1:.2f})"
        if why:
            lines.append(dict(line=li, text=text, skipped=why))
            continue
        a, b = int(t0 * SR), int(t1 * SR)
        seg = x[a:b]
        fl = f0[int(t0 / FRAME): int(t1 / FRAME)]
        med = 69 + 12 * np.log2(np.median(fl[fl > 0]) / 440.0) if (fl > 0).sum() > 10 else 60.0
        high = med >= HIGH
        try:
            y = lowered(seg, SR, f0[int(round(t0 / FRAME)):]) if high else seg
        except MemoryError:  # pyworld on a degenerate stretch
            lines.append(dict(line=li, text=text, skipped=f"WORLD failed on {t0:.2f}-{t1:.2f} s"))
            continue
        y16 = resample_poly(y, 16000, SR)
        y16 = 0.9 * y16 / max(float(np.max(np.abs(y16))), 1e-9)
        lines.append(dict(line=li, text=text, t0=round(t0, 4), t1=round(t1, 4), high=bool(high),
                          words=[dict(w, phones=p) for w, p in zip(ln, ph)], wav16=y16.astype(np.float32)))
    info["lines"] = lines
    return info


def align(work: Path, prepared: list[dict], jobs: int) -> None:
    """MFA on every line at once; each line's words get their phones' spans (seconds on the recording)."""
    import soundfile as sf

    mfa = work / "mfa"
    corpus = mfa / "corpus"
    shutil.rmtree(corpus, ignore_errors=True)
    seen: dict = {}
    for r in prepared:
        for ln in r.get("lines", []):
            if "wav16" not in ln:
                continue
            d = corpus / r["id"]
            d.mkdir(parents=True, exist_ok=True)
            name = f"{r['id']}.l{ln['line']:03d}"
            sf.write(str(d / f"{name}.wav"), (np.clip(ln.pop("wav16"), -1, 1) * 32767).astype(np.int16), 16000,
                     subtype="PCM_16")
            ln["tokens"] = [token_for(norm(w["word"]), tuple(w["phones"]), seen) for w in ln["words"]]
            (d / f"{name}.lab").write_text(" ".join(ln["tokens"]) + "\n")
    if not seen:
        return
    with open(mfa / "corpus.dict", "w") as f:
        for (word, phones), tok in sorted(seen.items(), key=lambda kv: kv[1]):
            f.write(f"{tok}\t{' '.join(phones)}\n")
    out = mfa / "aligned"
    shutil.rmtree(out, ignore_errors=True)
    cmd = [MFA, "align", str(corpus), str(mfa / "corpus.dict"), "english_us_arpa", str(out),
           "-t", str(mfa / "tmp"), "-j", str(jobs), "--clean", "--beam", "100", "--retry_beam", "400", "-q"]
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lock:
        print("waiting for MFA's lock...", flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
        print("aligning", flush=True)
        run = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if run.returncode != 0:
        raise SystemExit(f"mfa align failed:\n{run.stdout[-3000:]}\n{run.stderr[-3000:]}")
    for r in prepared:
        for ln in r.get("lines", []):
            if "tokens" not in ln:
                continue
            tg_path = out / r["id"] / f"{r['id']}.l{ln['line']:03d}.TextGrid"
            if not tg_path.exists():
                ln["skipped"] = "the aligner gave up"
                continue
            tg = textgrid(tg_path)
            got = [w for w in tg.get("words", []) if w[2] not in SKIP]
            heard = [p for p in tg.get("phones", []) if p[2] not in SKIP]
            i = 0
            for w, tok in zip(ln["words"], ln["tokens"]):
                j = i
                while j < len(got) and got[j][2] != tok:
                    j += 1
                if j == len(got):
                    w["spans"] = None
                    continue
                a, b, _ = got[j]
                i = j + 1
                inside = [p for p in heard if p[0] >= a - 1e-6 and p[1] <= b + 1e-6]
                w["spans"] = ([(round(ln["t0"] + s, 4), round(ln["t0"] + e, 4)) for s, e, _ in inside]
                              if len(inside) == len(w["phones"]) else None)


def is_sung(notes: list[dict], f0: np.ndarray) -> tuple[bool, float, float]:
    """Sung, not spoken: long vowels, and pitch that holds still on them (within 60 cents over 30 ms)."""
    vs = [n["_vowel"] for n in notes if n.get("_vowel")]
    if not vs:
        return False, 0.0, 0.0
    med = float(np.median([b - a for a, b in vs]))
    steady, total = 0, 0
    for a, b in vs:
        seg = f0[int(a / FRAME): int(b / FRAME)]
        seg = seg[seg > 0]
        if len(seg) < 8:
            continue
        c = 1200 * np.log2(seg)
        d = np.abs(c[6:] - c[:-6])
        steady += int((d < 60).sum())
        total += len(d)
    share = steady / total if total else 0.0
    return med >= SUNG["vowel_s"] and share >= SUNG["steady"], med, share


def notes_of(ln: dict, f0: np.ndarray) -> list[dict] | None:
    notes = []
    for w in ln["words"]:
        if not w.get("spans"):
            return None
        phones, spans = w["phones"], w["spans"]
        sylls = syllables(phones)
        q = 0
        for si, syl in enumerate(sylls):
            sp = spans[q: q + len(syl)]
            q += len(syl)
            vi = next(k for k, p in enumerate(syl) if p[-1:].isdigit())
            va, vb = sp[vi]
            seg = f0[int((va + 0.3 * (vb - va)) / FRAME): int((va + 0.8 * (vb - va)) / FRAME) + 1]
            seg = seg[seg > 0]
            voiced = f0[int(va / FRAME): int(vb / FRAME) + 1]
            doubt = []
            if w["p"] < 0.45:
                doubt.append("unsure word")
            if len(voiced) and (voiced > 0).mean() < 0.5:
                doubt.append("vowel unvoiced")
            if vb - va < 0.04:
                doubt.append("vowel too short")
            if any(e - s > 3.0 for s, e in sp) or any(e - s > 0.4 for k, (s, e) in enumerate(sp) if k != vi):
                doubt.append("stretched")
            notes.append(dict(word=norm(w["word"]), word_len=len(sylls), syllable=si, phones=syl, type=2,
                              sung_start=sp[0][0], sung_end=sp[-1][1], start=sp[0][0], dur=sp[-1][1] - sp[0][0],
                              midi=float(69 + 12 * np.log2(np.median(seg) / 440.0)) if len(seg) >= 3 else None,
                              line_end=False, vel=0.75, _vowel=(va, vb), doubt=doubt))
    for k in range(len(notes) - 1):  # a note lasts until the next one starts, when they join
        if notes[k + 1]["sung_start"] - notes[k]["sung_end"] < 0.1:
            notes[k]["sung_end"] = notes[k + 1]["sung_start"]
            notes[k]["dur"] = notes[k]["sung_end"] - notes[k]["sung_start"]
    known = [n["midi"] for n in notes if n["midi"] is not None]
    if not known:
        return None
    for n in notes:
        if n["midi"] is None:
            n["midi"] = float(np.median(known))
            n["doubt"].append("no pitch")
        n["pitch"] = int(round(n["midi"]))
    notes[-1]["line_end"] = True
    return notes


def singer_of(it: dict) -> str:
    """The singer a recording trains: one per performer, named for its group ("folk-makemi")."""
    who = re.sub(r"[^a-z0-9]+", "-", it.get("performer", "unknown").lower()).strip("-")[:24] or "unknown"
    return f"{it.get('singer', 'folk')}-{who}"


def build(work: Path, r: dict, it: dict) -> dict:
    """The recording's aligned lines as corpus segments (24 kHz wav + label) under WORK/corpus/<singer>/."""
    import soundfile as sf

    x = np.load(work / "mfa" / "audio" / f"{r['id']}.npy").astype(np.float64)
    f0 = np.load(work / "mfa" / "audio" / f"{r['id']}.f0.npy").astype(np.float64)
    good = []
    for ln in r.get("lines", []):
        if ln.get("skipped"):
            continue
        try:
            notes = notes_of(ln, f0)
        except (StopIteration, ValueError, IndexError) as e:  # one odd line never stops the rest
            ln["skipped"] = f"labelling failed: {type(e).__name__}"
            continue
        if notes is None:
            ln["skipped"] = "a word the aligner couldn't place"
            continue
        sung, vowel_s, steady = is_sung(notes, f0)
        ln.update(vowel_s=round(vowel_s, 3), steady=round(steady, 3))
        if not sung:
            ln["skipped"] = f"not sung (median vowel {vowel_s:.2f} s, pitch steady {steady:.0%})"
            continue
        doubted = sum(bool(n["doubt"]) for n in notes) / len(notes)
        ln["doubted"] = round(doubted, 2)
        if doubted > 0.4:
            ln["skipped"] = f"{doubted:.0%} of its notes doubtful"
            continue
        good.append((ln, notes))
    # lines into segments
    groups, cur = [], []
    for ln, notes in good:
        # a new segment after a long gap, when it would grow too long, and after a line left out (its singing
        # mustn't sit unlabelled, read as silence, inside a segment)
        if cur and (ln["t0"] - cur[-1][0]["t1"] > SEGMENT_GAP or ln["t1"] - cur[0][0]["t0"] > SEGMENT
                    or ln["line"] != cur[-1][0]["line"] + 1):
            groups.append(cur)
            cur = []
        cur.append((ln, notes))
    if cur:
        groups.append(cur)
    group = it.get("singer", "folk")
    singer = singer_of(it)
    d = work / "corpus" / singer
    d.mkdir(parents=True, exist_ok=True)
    segs = []
    for gi, g in enumerate(groups):
        t0, t1 = g[0][0]["t0"], g[-1][0]["t1"]
        name = f"{r['id']}.s{gi:02d}"
        notes = []
        for _, ns in g:
            for n in ns:
                n = {k: v for k, v in n.items() if not k.startswith("_") and k != "midi"}
                for k in ("sung_start", "sung_end", "start"):
                    n[k] = round(n[k] - t0, 4)
                n["dur"] = round(n["dur"], 4)
                notes.append(n)
        label = dict(index=name, language="English", t0=t0, t1=t1, notes=notes, singer=singer, group=group,
                     source=SOURCES[group], item=it["id"], sr=SR, audio_s=round(t1 - t0, 3),
                     band_hz=r["band_hz"], ap_band_hz=0 if group == "records" else r["band_hz"])
        audio = x[int(round(t0 * SR)): int(round(t1 * SR))]
        sf.write(str(d / f"{name}.wav"), np.clip(audio, -1, 1), SR, subtype="PCM_16")
        (d / f"{name}.json").write_text(json.dumps(label, indent=1))
        segs.append(dict(name=name, seconds=round(t1 - t0, 2), lines=len(g)))
    return dict({k: v for k, v in r.items() if k != "lines"}, segments=segs,
                lines=[{k: v for k, v in ln.items() if k not in ("words", "tokens", "wav16")} for ln in r.get("lines", [])])


def cut(args) -> None:
    work = work_ok(args.work)
    items = {it["id"]: it for it in json.loads((work / "manifest.json").read_text())}
    if args.only:
        items = {k: v for k, v in items.items() if k in args.only}
    for sub in ("corpus", "features", "align", "mfa"):
        shutil.rmtree(work / sub, ignore_errors=True)
    (work / "quality.json").unlink(missing_ok=True)
    (work / "mfa" / "audio").mkdir(parents=True)
    target = house_level()
    print(f"{len(items)} recordings; bringing each to the house corpus's level ({target:.1f} dB)", flush=True)
    todo = [it for it in items.values() if (work / "words" / f"{it['id']}.json").exists()
            and (args.separated or not it.get("accompanied"))]
    with ProcessPoolExecutor(args.jobs) as pool:
        ref = reference_spectrum()
        prepared = list(pool.map(prepare, [work] * len(todo), todo, [target] * len(todo),
                                 [args.min_quiet] * len(todo), [args.band_db] * len(todo), [ref] * len(todo)))
    for r in prepared:
        if r.get("skipped"):
            print(f"{r['id']}: LEFT OUT: {r['skipped']}")
    align(work, prepared, args.jobs)
    report = []
    for r in prepared:
        if r.get("skipped"):
            report.append(r)
            continue
        b = build(work, r, items[r["id"]])
        report.append(b)
        kept = sum(s["seconds"] for s in b["segments"])
        why = {}
        for ln in b["lines"]:
            if ln.get("skipped"):
                k = ln["skipped"].split(":")[0].split(" (")[0]
                why[k] = why.get(k, 0) + 1
        print(f"{r['id']}: band {r['band_hz']} Hz, background {r['background_db']} dB, "
              f"{sum(1 for ln in b['lines'] if not ln.get('skipped'))}/{len(b['lines'])} lines, {kept:.0f} s"
              + (f"; left out {why}" if why else ""), flush=True)
    (work / "cut.json").write_text(json.dumps(report, indent=1))
    total = sum(s["seconds"] for r in report for s in r.get("segments", []))
    print(f"{sum(len(r.get('segments', [])) for r in report)} segments, {total / 60:.1f} min -> {work / 'corpus'}")


# --- merge ----------------------------------------------------------------------------------------------


def merge(args) -> None:
    """The house dataset with the folk frames added, one singer per manifest singer, and every singer the
    base model knows kept in the list (with no frames of its own, it keeps its learned row)."""
    house = np.load(args.house)
    folk = np.load(args.folk or args.work / "dataset-folk.npz")
    if list(house["phones"]) != list(folk["phones"]):
        raise SystemExit("the two datasets have different phone lists")
    singers = [str(s) for s in house["singers"]]
    sources = [str(s) for s in house["sources"]]
    if args.base:
        z = np.load(args.base)
        cfg = json.loads(str(z["config"]))
        for name in cfg["singers"]:
            if name not in singers:
                singers.append(name)
                sources.append(cfg["sources"].get(name, "formant"))
    new = [str(s) for s in folk["singers"]]
    clash = [s for s in new if s in singers]
    if clash:
        raise SystemExit(f"{args.house} or the base model already has {clash}")
    remap = np.array([len(singers) + i for i in range(len(new))], dtype=np.int16)
    keys = [k for k in house.files if k not in ("singers", "sources", "phones", "segments", "offsets", "lengths")]
    n, m = len(house["phone"]), len(folk["phone"])
    out = {}
    for k in keys + [k for k in ("sp_top", "ap_top") if k not in keys]:
        h = house[k] if k in house.files else np.full(n, house["sp"].shape[1] if k == "sp_top" else house["ap"].shape[1],
                                                       dtype=np.int16)
        v = folk[k] if k in folk.files else np.full(m, h.max(), dtype=h.dtype)
        if k == "singer":
            v = remap[folk[k].astype(np.int64)].astype(h.dtype)
        out[k] = np.concatenate([h, v.astype(h.dtype)])
    out.update(singers=np.array(singers + new), sources=np.array(sources + [str(s) for s in folk["sources"]]),
               phones=house["phones"], segments=np.concatenate([house["segments"], folk["segments"]]),
               offsets=np.concatenate([house["offsets"], folk["offsets"] + n]),
               lengths=np.concatenate([house["lengths"], folk["lengths"]]))
    dest = args.out or args.work / "dataset-house-folk.npz"
    np.savez(dest, **out)
    per = {s: int((folk["singer"] == i).sum()) for i, s in enumerate(new)}
    print(f"{Path(args.house).name}: {n} frames ({n * FRAME / 60:.1f} min) + "
          + ", ".join(f"{s} {c * FRAME / 60:.1f} min" for s, c in per.items())
          + f" ({folk['mask'].mean():.0%} unmasked); singers {singers + new} -> {dest}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("work", type=Path)
    f.add_argument("manifest", type=Path)
    sp = sub.add_parser("separate")
    sp.add_argument("work", type=Path)
    sp.add_argument("--python", default=os.environ.get("DEMUCS_PYTHON", "python3"))
    sp.add_argument("--model", default="htdemucs")
    sp.add_argument("--device", default="mps")
    sp.add_argument("--only", nargs="*", default=None)
    t = sub.add_parser("transcribe")
    t.add_argument("work", type=Path)
    t.add_argument("--model", default="medium.en")
    t.add_argument("--threads", type=int, default=8)
    t.add_argument("--only", nargs="*", default=None)
    t.add_argument("--separated", action="store_true", help="accompanied recordings too, their Demucs voice")
    c = sub.add_parser("cut")
    c.add_argument("work", type=Path)
    c.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    c.add_argument("--min-quiet", type=float, default=25.0,
                   help="leave out a recording whose background is less than this many dB under its singing")
    c.add_argument("--band-db", type=float, default=12.0,
                   help="a frequency is inside the recording's band if its sung spectrum stands this far over the quiet")
    c.add_argument("--only", nargs="*", default=None)
    c.add_argument("--separated", action="store_true", help="accompanied recordings too, their Demucs voice")
    m = sub.add_parser("merge")
    m.add_argument("work", type=Path)
    m.add_argument("--house", type=Path, default=HOUSE / "dataset-house.npz")
    m.add_argument("--folk", type=Path, default=None, help="default: WORK/dataset-folk.npz")
    m.add_argument("--base", type=Path, default=ROOT / "songbird/synth/throat.npz",
                   help="keep this model's singers in the list (none: '')")
    m.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if getattr(args, "base", None) is not None and str(args.base) == "":
        args.base = None
    {"fetch": fetch, "separate": separate, "transcribe": transcribe, "cut": cut, "merge": merge}[args.cmd](args)


if __name__ == "__main__":
    main()
