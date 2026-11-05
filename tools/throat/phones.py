"""Phone boundaries in the learned throat's corpus, from the Montreal Forced Aligner (dev only).

    uv run python tools/throat/phones.py [renders/throat/corpus] [--jobs 8]

Every rendered segment is cut into its lines at the quiet between them, each line aligned with MFA's
english_us_arpa acoustic model against exactly the phones SoulX was asked to sing (a dictionary
made for the corpus: one entry per word and reading, so MFA can't choose another pronunciation).
Voices singing above A3 are aligned an octave down: MFA's model learned speech, and on high voices
it loses vowels (the reference study in renders/reference/mfa/ found 17% of a high female voice's
vowels off by more than 0.15 s, and lowering an octave with the spectral envelope kept fixed most of
it). The octave is taken by resynthesis with songbird.synth.throat at half the f0, which keeps the
timing exact.

Writes renders/throat/align/<singer>/<segment>.json: every phone with its start and end (seconds,
on the segment's own clock), the note it belongs to and its role (onset, vowel, coda), and, per
note, whether MFA's vowel sits where the note is sung (its start within [-0.15, +0.25] s of the
note's start and lasting at least a fifth of it). MFA is found as tools/align.py finds it ($MFA_HOME,
or $MFA naming its wrapper), and runs are serialized with the lock the phrasing extractor uses
(align.lock()), since two runs at once collide unpacking the model.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import align  # noqa: E402  (tools/align.py: where MFA is, and its lock)

from songbird.synth import throat  # noqa: E402

SR = 16000
HIGH = 57  # MIDI: voices whose median note is at or above A3 are aligned an octave down
SKIP = {"", "sil", "sp", "spn", "<eps>"}


def token(word: str, phones: tuple[str, ...], seen: dict) -> str:
    """A dictionary word for this spelling read this way: letters only, unique per reading."""
    key = (word, phones)
    if key not in seen:
        base = re.sub(r"[^a-z]", "", word.lower()) or "w"
        n = sum(1 for w, _ in seen if re.sub(r"[^a-z]", "", w.lower()) == base)
        code = ""
        while True:
            code = chr(ord("a") + n % 26) + code
            n //= 26
            if n == 0:
                break
        seen[key] = f"{base}q{code}"
    return seen[key]


def words_of(notes: list[dict]) -> list[tuple[str, tuple[str, ...], list[int]]]:
    """(word, its phones, the notes it's sung on), in order."""
    out, i = [], 0
    while i < len(notes):
        k = max(1, int(notes[i]["word_len"]))
        group = list(range(i, min(i + k, len(notes))))
        while len(group) > 1 and notes[group[-1]]["word"] != notes[i]["word"]:
            group.pop()
        phones = tuple(p for j in group if notes[j]["type"] == 2 for p in notes[j]["phones"])
        out.append((notes[i]["word"], phones, group))
        i = group[-1] + 1
    return out


def lines_of(notes: list[dict]) -> list[list[int]]:
    lines, cur = [], []
    for k, n in enumerate(notes):
        cur.append(k)
        if n["line_end"] or k == len(notes) - 1:
            lines.append(cur)
            cur = []
    return lines


def textgrid(path: Path) -> dict[str, list[tuple[float, float, str]]]:
    """The tiers of a Praat TextGrid (long text format) as (start, end, label) lists."""
    tiers: dict[str, list] = {}
    name = None
    xmin = xmax = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("name ="):
            name = line.split("=", 1)[1].strip().strip('"')
            tiers[name] = []
        elif line.startswith("xmin =") and name:
            xmin = float(line.split("=", 1)[1])
        elif line.startswith("xmax =") and name:
            xmax = float(line.split("=", 1)[1])
        elif line.startswith("text =") and name:
            tiers[name].append((xmin, xmax, line.split("=", 1)[1].strip().strip('"')))
    return tiers


def lowered(wav: Path, feats: Path, sr: int) -> np.ndarray:
    """The segment an octave down, spectral envelope and timing kept."""
    f = np.load(feats)
    y = throat.synthesize(f["f0"].astype(np.float64) / 2, f["sp"].astype(np.float64), f["ap"].astype(np.float64), sr,
                          np.random.default_rng(0), fft=int(f["fft"]) * 2)
    return y


def prepare(corpus: Path, features: Path, work: Path, todo: list[Path]) -> tuple[dict, list]:
    seen: dict = {}
    cuts = []
    for wav in todo:
        label = json.loads(wav.with_suffix(".json").read_text())
        notes = label["notes"]
        x, sr = sf.read(str(wav), dtype="float64")
        high = np.median([n["pitch"] for n in notes]) >= HIGH
        if high:
            x = lowered(wav, features / wav.parent.name / f"{wav.stem}.npz", sr)
        x = resample_poly(x, SR, sr)
        x = 0.9 * x / max(float(np.max(np.abs(x))), 1e-9)
        words = words_of(notes)
        note_word = {j: w for w, (_, _, group) in enumerate(words) for j in group}
        lines = lines_of(notes)
        for li, line in enumerate(lines):
            first, last = notes[line[0]], notes[line[-1]]
            t0 = 0.0 if li == 0 else 0.5 * (notes[lines[li - 1][-1]]["sung_end"] + first["sung_start"])
            t1 = len(x) / SR if li == len(lines) - 1 else 0.5 * (last["sung_end"] + notes[lines[li + 1][0]]["sung_start"])
            ws = sorted({note_word[j] for j in line})
            name = f"{wav.stem}.l{li:02d}"
            d = work / "corpus" / wav.parent.name
            d.mkdir(parents=True, exist_ok=True)
            a, b = int(round(t0 * SR)), int(round(t1 * SR))
            sf.write(str(d / f"{name}.wav"), (np.clip(x[a:b], -1, 1) * 32767).astype(np.int16), SR, subtype="PCM_16")
            (d / f"{name}.lab").write_text(" ".join(token(words[w][0], words[w][1], seen) for w in ws) + "\n")
            cuts.append((wav, name, t0, [(token(words[w][0], words[w][1], seen), words[w]) for w in ws], high))
    return seen, cuts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus", type=Path, nargs="?", default=ROOT / "renders/throat/corpus")
    ap.add_argument("--features", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--keep", type=Path, default=None, help="keep MFA's work here")
    args = ap.parse_args()
    features = args.features or args.corpus.parent / "features"
    out_dir = args.out or args.corpus.parent / "align"
    todo = [w for w in sorted(args.corpus.glob("*/*.wav"))
            if w.with_suffix(".json").exists() and (features / w.parent.name / f"{w.stem}.npz").exists()
            and not (out_dir / w.parent.name / f"{w.stem}.json").exists()]
    if not todo:
        print("nothing to align")
        return
    mfa = align.executable()
    if mfa is None:
        raise SystemExit("MFA isn't installed: set MFA_HOME to where it is (or MFA to its wrapper)")
    work = args.keep or Path(tempfile.mkdtemp(prefix="throat-mfa-"))
    try:
        seen, cuts = prepare(args.corpus, features, work, todo)
        with open(work / "corpus.dict", "w") as f:
            for (word, phones), tok in sorted(seen.items(), key=lambda kv: kv[1]):
                f.write(f"{tok}\t{' '.join(phones)}\n")
        cmd = [str(mfa), "align", str(work / "corpus"), str(work / "corpus.dict"), "english_us_arpa", str(work / "aligned"),
               "-t", str(work / "tmp"), "-j", str(args.jobs), "--clean", "--beam", "100", "--retry_beam", "400", "-q"]
        print(f"{len(cuts)} lines from {len(todo)} segments; waiting for MFA's lock...", flush=True)
        with align.lock():
            print("aligning", flush=True)
            run = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if run.returncode != 0:
            raise SystemExit(f"mfa align failed:\n{run.stdout[-3000:]}\n{run.stderr[-3000:]}")
        results: dict[Path, dict] = {}
        for wav, name, t0, words, high in cuts:
            label = json.loads(wav.with_suffix(".json").read_text()) if wav not in results else None
            if wav not in results:
                results[wav] = {"segment": wav.stem, "singer": wav.parent.name, "lowered": bool(high), "phones": [],
                                "notes": [dict(found=False) for _ in label["notes"]], "_notes": label["notes"]}
            r = results[wav]
            path = work / "aligned" / wav.parent.name / f"{name}.TextGrid"
            if not path.exists():
                continue
            tg = textgrid(path)
            got = [w for w in tg.get("words", []) if w[2] not in SKIP]
            heard = [p for p in tg.get("phones", []) if p[2] not in SKIP]
            i = 0
            for tok, (_, phones, group) in words:
                j = i
                while j < len(got) and got[j][2] != tok:
                    j += 1
                if j == len(got):
                    continue
                a, b, _ = got[j]
                i = j + 1
                inside = [p for p in heard if p[0] >= a - 1e-6 and p[1] <= b + 1e-6]
                if len(inside) != len(phones):
                    continue
                # hand the word's phones back to its notes, syllable by syllable
                q = 0
                for k in group:
                    n = r["_notes"][k]
                    if n["type"] != 2:
                        continue
                    for m, p in enumerate(n["phones"]):
                        s, e, _ = inside[q]
                        vowel = p[-1:].isdigit()
                        before_vowel = not any(x[-1:].isdigit() for x in n["phones"][:m])
                        role = "vowel" if vowel else ("onset" if before_vowel else "coda")
                        r["phones"].append(dict(phone=p, start=round(t0 + s, 4), end=round(t0 + e, 4), note=k, role=role))
                        if vowel:
                            r["notes"][k].update(found=True, vowel_start=round(t0 + s, 4), vowel_end=round(t0 + e, 4))
                        q += 1
        for wav, r in results.items():
            notes = r.pop("_notes")
            for k, (n, f) in enumerate(zip(notes, r["notes"])):
                if f.get("found"):
                    off = f["vowel_start"] - n["sung_start"]
                    f["offset"] = round(off, 4)
                    f["plausible"] = bool(-0.15 <= off <= 0.25 and f["vowel_end"] - f["vowel_start"]
                                          >= 0.2 * (n["sung_end"] - n["sung_start"]))
            r["phones"].sort(key=lambda p: p["start"])
            dest = out_dir / r["singer"] / f"{wav.stem}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(r, indent=1))
        found = [f for r in results.values() for f in r["notes"]]
        ok = [f for f in found if f.get("plausible")]
        offs = np.array([f["offset"] for f in found if "offset" in f])
        print(f"{len(results)} segments: vowels found for {sum(f['found'] for f in found)}/{len(found)} notes, "
              f"plausible {len(ok)}; vowel start - note start: median {np.median(offs) * 1000:+.0f} ms, "
              f"IQR {np.percentile(offs, 25) * 1000:+.0f}..{np.percentile(offs, 75) * 1000:+.0f} ms")
    finally:
        if args.keep is None:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
