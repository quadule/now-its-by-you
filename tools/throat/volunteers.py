"""The volunteers' takes as training material for the learned throat (dev only; private, temporary).

    uv run python tools/throat/volunteers.py cut WORK [--min-quiet 20] [--jobs 6]
    uv run python tools/throat/features.py WORK/corpus --out WORK/features
    uv run python tools/throat/phones.py WORK/corpus
    uv run python tools/throat/check.py WORK --cents 200 --min-tune 0.75
    uv run python tools/throat/dataset.py WORK --out WORK/dataset-volunteers.npz
    uv run python tools/throat/volunteers.py merge WORK [--house renders/throat/dataset-house.npz]

WORK is a scratch directory of your choosing, never renders/ or recordings/. `cut` reads every take in
recordings/<singer>/ that counts (tools/takes.py's `use`), leaving out the artist's tests (sim-*.wav,
*-test-* folders), and cuts it into its sung lines using the score of the guide it was sung to
(recordings/guides/): the notes whose start falls inside the take's window (from_s, to_s) and that
end before its sound does, as tools/phrasing.py's measure_window takes them. Each line is written as
a segment exactly as tools/throat/soulx_batch.py writes the SoulX corpus (24 kHz 16-bit mono, and a
.json label with the notes relative to the segment: phones per note from the score's words through
songbird.phonetics (tools/throat/soulx.py's segment()), sung_start/sung_end, pitch in the key the
singer actually sang, level, stress), so features.py, phones.py and dataset.py read them unchanged.

How a take is placed and keyed:
- the take's first sample is from_s on its guide's clock (the page lines takes up already); each
  line is then slid within +-0.25 s to where the take's voicing best matches the line's notes, so a
  singer who sat a little behind the guide is still labelled where they sang;
- the key is the median of (their pitch - the tune's) near the notes, rounded (most sang an octave
  down), as phrasing.find_key reads it;
- every take is brought to one loudness (its sung frames' median level to the house corpus's), so
  the network isn't taught that people are quieter than SoulX.

The guide leaking into the microphone: no sidecar here carries a measured leak (leak_ms/leak_db),
and cancelling it the way tools/karaoke.js's cancelLeak does needs the guide's audio, which is not
kept with the takes. So each take's background is measured instead: the level of the take where the
guide has no singing (its pre-roll and the gaps between lines, which carry any room noise and any
leak of the backing) against the level of its singing. A take whose background is within
--min-quiet dB of its singing is left out, and said so.

`merge` adds the volunteer frames (dataset.py's output on WORK) to the house dataset as one more
singer, "volunteers", source "human", and writes WORK/dataset-house-volunteers.npz.

`cut` starts clean each time (it deletes WORK's earlier segments, features and alignments), so a take
deleted from recordings/ since (a singer who withdrew) leaves nothing behind in WORK.

The quality check for people: check.py's --cents 200 --min-tune 0.75 (at 50 cents, SoulX's standard,
only 3 of 195 lines pass: people singing along drift 50-150 cents, and that doesn't matter here, since
the network is given the f0 they sang, not the note). What the check still guards is that the voice
was tracked in its key (not an octave off, not the leak) and that MFA found the vowels where the notes
are.

ALL SINGERS SHARE ONE SINGER ID, "volunteers" (the consent in web/sing/consent.md: a voice trained on
everyone's takes at once, never set to sound like any one person). Segment names are a hash of the
take, not the singer; WORK/takes.json (which stays in WORK) is the only map back to the takes.

PRIVACY: WORK/corpus holds cuts of the recordings, and WORK/features, the datasets and any model
trained on them can rebuild a voice. All of WORK, and every copy of it (a desktop packet, a trained
model-volunteers.npz), must be deleted with the recordings, by the end of 2026-09-30 (Pacific).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).parent))

import takes as K  # noqa: E402
from soulx import segment  # noqa: E402

SINGER = "volunteers"
SOURCE = "human"
SR = 24000  # the corpus's rate
FRAME = 0.005
SLIDE = 0.25  # seconds a line may be slid to where it was sung
LEAD, TAIL = 0.3, 0.4  # seconds kept before a line's first note and after its last, as soulx.segments keeps
HOUSE_LEVEL = None  # filled from the house features: the median level (dB) of their voiced frames


def counts(t: K.Take) -> str | None:
    """Why a take is left out, or None if it counts."""
    if t.path.name.startswith("sim-") or "-test-" in t.path.parent.name or "-test-" in t.path.name:
        return "the artist's test"
    if not t.use:
        return "marked not to use"
    if not K.guide_score(t.song, t.guide):
        return "its guide's score isn't kept"
    return None


def voice_notes(score: Path) -> tuple[list[dict], dict]:
    data = json.loads(score.read_text())
    notes = sorted((n for n in data["notes"] if n["part"] == "voice"), key=lambda n: n["start"])
    return notes, data.get("lexicon") or {}


def lines_of(notes: list[dict]) -> list[list[int]]:
    out, cur = [], []
    for k, n in enumerate(notes):
        cur.append(k)
        if n.get("line_end") or k == len(notes) - 1:
            out.append(cur)
            cur = []
    return out


def house_level() -> float:
    feats = sorted((ROOT / "renders/throat/features").glob("house-*/*.npz"))[::25]
    levels = []
    for f in feats:
        z = np.load(f)
        levels.append(np.median(z["level"][z["f0"] > 0]))
    return float(np.median(levels)) if levels else -20.0


def tag(t: K.Take) -> str:
    return "vol-" + hashlib.sha256(t.rel.encode()).hexdigest()[:10]


def cut_take(wav: Path, out_dir: str, min_quiet: float, target_db: float) -> dict:
    import pyworld as pw
    import soundfile as sf
    from scipy.signal import resample_poly

    t = K.load(wav)
    notes, lexicon = voice_notes(K.guide_score(t.song, t.guide))
    y, sr = sf.read(str(t.path), dtype="float64")
    y = y if y.ndim == 1 else y.mean(axis=1)
    y = resample_poly(y, SR, sr) if sr != SR else y
    dur = len(y) / SR
    from_s = t.from_s
    to_s = min(t.to_s if t.to_s is not None else from_s + dur, from_s + dur)
    info = dict(take=t.rel, tag=tag(t), seconds=round(dur, 1), from_s=from_s, to_s=round(to_s, 3))
    inside = {k for k, n in enumerate(notes) if from_s <= n["start"] < to_s and n["start"] + n["dur"] <= from_s + dur}
    lines = [ln for ln in lines_of(notes) if all(k in inside for k in ln)]
    if not lines:
        return dict(info, skipped="no whole line inside the take")
    # the take on its guide's clock: f0 and level every frame
    x16 = resample_poly(y, 16000, SR)
    f0, _ = pw.harvest(x16, 16000, f0_floor=60.0, f0_ceil=900.0, frame_period=FRAME * 1000)
    hop = int(FRAME * SR)
    nfr = len(f0)
    level = 20 * np.log10(np.maximum(np.array([np.sqrt(np.mean(y[i * hop: i * hop + 2 * hop] ** 2) + 1e-20)
                                               for i in range(nfr)]), 1e-6))
    at = lambda s: int(round((s - from_s) / FRAME))  # noqa: E731  guide time -> take frame
    # key: their pitch against the tune near every note's middle
    diffs = []
    for k in inside:
        n = notes[k]
        seg = f0[max(at(n["start"] + 0.3 * n["dur"]), 0): max(at(n["start"] + 0.8 * n["dur"]), 0)]
        seg = seg[seg > 0]
        if len(seg) >= 5:
            diffs.append(12 * np.log2(np.median(seg) / 440.0) + 69 - n["pitch"])
    if len(diffs) < 5:
        return dict(info, skipped="hardly any singing found")
    key = int(np.round(np.median(diffs)))
    info["key"] = key
    info["key_spread"] = round(float(np.percentile(np.abs(np.array(diffs) - key), 75)), 2)
    # background: where the guide has no singing (0.35 s clear of every note), against the singing
    expect = np.zeros(nfr, dtype=bool)
    for n in notes:
        a, b = at(n["start"] - 0.35), at(n["start"] + n["dur"] + 0.35)
        expect[max(a, 0): max(min(b, nfr), 0)] = True
    sung = (f0 > 0) & expect
    quiet = ~expect
    sing_db = float(np.median(level[sung])) if sung.any() else -120.0
    back_db = float(np.median(level[quiet])) if quiet.sum() >= 40 else None
    info["singing_db"] = round(sing_db, 1)
    info["background_db"] = None if back_db is None else round(back_db - sing_db, 1)
    # voicing where the tune isn't sung (the leak of a melody guide shows here, as pitch in the gaps)
    info["voiced_in_gaps"] = round(float(np.mean(f0[quiet] > 0)), 3) if quiet.sum() >= 40 else None
    if back_db is not None and back_db - sing_db > -min_quiet:
        return dict(info, skipped=f"background {back_db - sing_db:+.1f} dB against the singing (a leak or a loud room)")
    gain = 10 ** ((target_db - sing_db) / 20)
    y = y * gain
    if np.max(np.abs(y)) > 0.99:
        y = y * 0.99 / np.max(np.abs(y))
    voiced = (f0 > 0).astype(float)
    segs = []
    for li, line in enumerate(lines):
        ln = [notes[k] for k in line]
        # slide the line to where its notes were sung: voicing against the notes' spans
        a, b = at(ln[0]["start"]) , at(ln[-1]["start"] + ln[-1]["dur"])
        want = np.zeros(b - a)
        for n in ln:
            want[max(at(n["start"] + 0.1 * n["dur"]) - a, 0): max(at(n["start"] + 0.9 * n["dur"]) - a, 0)] = 1.0
        reach = int(SLIDE / FRAME)
        best, lag = -1.0, 0
        for d in range(-reach, reach + 1):
            lo, hi = a + d, b + d
            if lo < 0 or hi > nfr:
                continue
            s = float(np.dot(voiced[lo:hi], want))
            if s > best + 1e-9 or (abs(s - best) < 1e-9 and abs(d) < abs(lag)):
                best, lag = s, d
        cover = best / max(want.sum(), 1.0)
        lag_s = lag * FRAME
        # the segment's clock: take seconds; notes moved onto it
        moved = [dict(n, start=n["start"] - from_s + lag_s) for n in ln]
        prev_end = (notes[lines[li - 1][-1]]["start"] + notes[lines[li - 1][-1]]["dur"] - from_s + lag_s) if li else 0.0
        next_start = (notes[lines[li + 1][0]]["start"] - from_s + lag_s) if li + 1 < len(lines) else dur
        t0 = max(0.0, moved[0]["start"] - LEAD, 0.5 * (prev_end + moved[0]["start"]))
        t1 = min(dur, moved[-1]["start"] + moved[-1]["dur"] + TAIL, 0.5 * (moved[-1]["start"] + moved[-1]["dur"] + next_start))
        if cover < 0.5:
            segs.append(dict(line=li, skipped=f"only {cover:.0%} of the line's notes voiced"))
            continue
        name = f"{info['tag']}.l{li:02d}"
        seg = segment(moved, lexicon, t0, t1, breath=0.0, index=name, shift=key)
        label = {k2: v for k2, v in seg.items() if k2 not in ("duration", "text", "phoneme", "note_pitch", "note_type")}
        label.update(singer=SINGER, source=SOURCE, item=t.song, kind="take", shift=key, sr=SR,
                     audio_s=round(t1 - t0, 3), lag_s=round(lag_s, 3), gain_db=round(20 * np.log10(gain), 1))
        audio = y[int(round(t0 * SR)): int(round(t1 * SR))]
        d = Path(out_dir) / "corpus" / SINGER
        d.mkdir(parents=True, exist_ok=True)
        sf.write(str(d / f"{name}.wav"), np.clip(audio, -1, 1), SR, subtype="PCM_16")
        (d / f"{name}.json").write_text(json.dumps(label, indent=1))
        segs.append(dict(line=li, name=name, seconds=round(t1 - t0, 2), lag_s=round(lag_s, 3), voiced=round(cover, 2)))
    return dict(info, lines=segs)


def cut(args) -> None:
    work = args.work.resolve()
    for forbidden in (ROOT / "renders", ROOT / "recordings"):
        if work == forbidden or forbidden in work.parents:
            raise SystemExit(f"{work} is inside {forbidden}: give a scratch directory")
    # start clean: a take deleted since the last cut (a singer who withdrew) must leave nothing behind here
    import shutil

    for sub in ("corpus", "features", "align"):
        shutil.rmtree(work / sub / SINGER, ignore_errors=True)
    for f in ("quality.json", "takes.json", "dataset-volunteers.npz", "dataset-house-volunteers.npz"):
        (work / f).unlink(missing_ok=True)
    todo, report = [], []
    for wav in sorted(K.RECORDINGS.glob("*/*.wav")):
        if wav.parent.name in K.NOT_SINGERS:
            continue
        t = K.load(wav)
        why = counts(t)
        if why:
            report.append(dict(take=t.rel, skipped=why))
        else:
            todo.append(wav)
    for wav in sorted(K.RECORDINGS.glob("*.wav")):  # sim-*.wav and anything else loose: never a volunteer's take
        report.append(dict(take=wav.relative_to(ROOT).as_posix(), skipped="not in a singer's folder (the artist's test)"))
    target = house_level()
    print(f"{len(todo)} takes count; bringing each to the house corpus's level ({target:.1f} dB)", flush=True)
    with ProcessPoolExecutor(args.jobs) as pool:
        for r in pool.map(cut_take, todo, [str(work)] * len(todo), [args.min_quiet] * len(todo), [target] * len(todo)):
            report.append(r)
            lines = r.get("lines", [])
            kept = [s for s in lines if "name" in s]
            print(f"{r['tag']}: key {r.get('key')}, background {r.get('background_db')} dB, "
                  f"{len(kept)}/{len(lines)} lines, {sum(s['seconds'] for s in kept):.0f} s"
                  + (f"  LEFT OUT: {r['skipped']}" if r.get("skipped") else ""), flush=True)
    work.mkdir(parents=True, exist_ok=True)
    (work / "takes.json").write_text(json.dumps(report, indent=1))
    secs = sum(s["seconds"] for r in report for s in r.get("lines", []) if "name" in s)
    n = sum(1 for r in report for s in r.get("lines", []) if "name" in s)
    print(f"{n} line segments, {secs / 60:.1f} min -> {work / 'corpus' / SINGER} (map back to the takes: {work / 'takes.json'})")


def merge(args) -> None:
    """The house dataset with the volunteers' frames added as one more singer."""
    house = np.load(args.house)
    vol = np.load(args.volunteers or args.work / "dataset-volunteers.npz")
    if list(house["phones"]) != list(vol["phones"]):
        raise SystemExit("the two datasets have different phone lists")
    singers = [str(s) for s in house["singers"]]
    sources = [str(s) for s in house["sources"]]
    if SINGER in singers:
        raise SystemExit(f"{args.house} already has a {SINGER!r} singer")
    frames = [k for k in house.files if k not in ("singers", "sources", "phones", "segments", "offsets", "lengths")]
    out = {}
    for k in frames:
        v = vol[k]
        if k == "singer":
            v = np.full(len(v), len(singers), dtype=house[k].dtype)
        out[k] = np.concatenate([house[k], v.astype(house[k].dtype)])
    n = len(house["phone"])
    out.update(singers=np.array(singers + [SINGER]), sources=np.array(sources + [SOURCE]), phones=house["phones"],
               segments=np.concatenate([house["segments"], np.array([f"{SINGER}/{s.split('/')[-1]}" for s in vol["segments"]])]),
               offsets=np.concatenate([house["offsets"], vol["offsets"] + n]),
               lengths=np.concatenate([house["lengths"], vol["lengths"]]))
    dest = args.out or args.work / "dataset-house-volunteers.npz"
    np.savez(dest, **out)
    m = len(vol["phone"])
    print(f"{args.house.name}: {n} frames ({n * FRAME / 60:.1f} min, {len(singers)} singers) + volunteers {m} frames "
          f"({m * FRAME / 60:.1f} min, {vol['mask'].mean():.0%} unmasked) -> {dest}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cut", help="the takes as line segments under WORK/corpus/volunteers")
    c.add_argument("work", type=Path)
    c.add_argument("--min-quiet", type=float, default=20.0,
                   help="leave out a take whose background is less than this many dB under its singing")
    c.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    m = sub.add_parser("merge", help="the house dataset plus the volunteers' frames")
    m.add_argument("work", type=Path)
    m.add_argument("--house", type=Path, default=ROOT / "renders/throat/dataset-house.npz")
    m.add_argument("--volunteers", type=Path, default=None, help="default: WORK/dataset-volunteers.npz")
    m.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    cut(args) if args.cmd == "cut" else merge(args)


if __name__ == "__main__":
    main()
