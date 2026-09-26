"""The oracle test: a perfect throat under our puppeteer (dev only).

    uv run python tools/throat/oracle.py SINGER/SEGMENT [...] [--out renders/throat/oracle]

A learned throat will be driven by our schedule (when each phone starts and ends), our pitch track
(glides, vibrato, gestures) and our dynamics. Before training one, this checks that interface with a
throat that can't be wrong: SoulX's own envelope and aperiodicity for the same notes, each phone's
frames stretched or squeezed from where MFA found them onto where songbird.synth.voice.schedule puts
that phone, voiced at our pitch track and sung through songbird.synth.throat. If this doesn't sound
right and isn't understood, no network trained on these labels will be.

For each segment, writes and transcribes (Whisper base.en, a verse at a time): the SoulX original,
the oracle, and our formant singer on the same notes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).parent))

from dataset import ours  # noqa: E402
from intelligibility import align as word_align, normalize  # noqa: E402

from songbird import genome as G  # noqa: E402
from songbird.score import Note  # noqa: E402
from songbird.synth import throat  # noqa: E402
from songbird.synth.voice import BLOCK, VoiceParams, pitch_track, schedule, sing  # noqa: E402

SR = 24000


def notes_of(label: dict) -> list[Note]:
    return [Note(part="voice", start=n["start"], dur=n["dur"], pitch=float(n["pitch"]), vel=n["vel"],
                 syllable=n["syllable"], word=n["word"], word_len=n["word_len"], line_end=n["line_end"])
            for n in label["notes"]]


def lexicon_of(item: str) -> dict:
    song = item.split("-verse-")[0].split("-refrain-")[0].split("-bridge-")[0]
    path = ROOT / "songs" / f"{song}.json"
    if not path.exists():
        path = ROOT / "songs/h-now-its-by-you.json"
    return G.load(path).lexicon


def warp(segs, src: list[dict], feats, n_out: int) -> tuple[np.ndarray, np.ndarray]:
    """SoulX's frames for each of our phones, stretched from where MFA found that phone to where we sing it."""
    sp, ap = feats["sp"].astype(np.float64), feats["ap"].astype(np.float64)
    ours_ = [s for s in segs if s.role != "breath"]
    if [s.phone for s in ours_] != [p["phone"] for p in src]:
        raise ValueError("our phones and MFA's differ")
    # anchor points: (our time, source time) at every phone boundary; silence maps onto silence
    anchors = [(0.0, 0.0)]
    for s, p in zip(ours_, src):
        anchors += [(s.t0, p["start"]), (s.t1, p["end"])]
    anchors.append((n_out * throat.FRAME, len(sp) * throat.FRAME))
    anchors.sort()
    t_ours = np.array([a[0] for a in anchors])
    t_src = np.array([a[1] for a in anchors])
    keep = np.concatenate([[True], np.diff(t_ours) > 1e-6])
    at = np.interp(np.arange(n_out) * throat.FRAME, t_ours[keep], t_src[keep]) / throat.FRAME
    i0 = np.clip(np.floor(at).astype(int), 0, len(sp) - 1)
    i1 = np.minimum(i0 + 1, len(sp) - 1)
    w = (at - np.floor(at))[:, None]
    return sp[i0] * (1 - w) + sp[i1] * w, ap[i0] * (1 - w) + ap[i1] * w


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("segments", nargs="+", help="SINGER/SEGMENT, as in renders/throat/corpus")
    ap.add_argument("--out", type=Path, default=ROOT / "renders/throat/oracle")
    args = ap.parse_args()
    from faster_whisper import WhisperModel

    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    args.out.mkdir(parents=True, exist_ok=True)
    totals: dict[str, list[int]] = {}
    for key in args.segments:
        singer, seg = key.split("/")
        base = ROOT / "renders/throat"
        label = json.loads((base / "corpus" / singer / f"{seg}.json").read_text())
        al = json.loads((base / "align" / singer / f"{seg}.json").read_text())
        feats = np.load(base / "features" / singer / f"{seg}.npz")
        x, sr = sf.read(str(base / "corpus" / singer / f"{seg}.wav"), dtype="float64")
        notes = notes_of(label)
        lexicon = lexicon_of(label["item"])
        voice = VoiceParams()
        segs = schedule(notes, voice, lexicon)
        n_out = int(np.ceil((max(s.t1 for s in segs) + 0.5) / throat.FRAME))
        sp, apr = warp(segs, ours(al["phones"], label["notes"]), feats, n_out)
        # our pitch track, on the envelope's frames; silent where we sing nothing voiced
        n_blocks = int(np.ceil(n_out * throat.FRAME * SR / BLOCK))
        vowels = [s for s in segs if s.role == "vowel"]
        f0b = pitch_track(notes, n_blocks, SR, voice, np.random.default_rng(1), [s.t1 for s in vowels])
        f0 = np.interp(np.arange(n_out) * throat.FRAME, (np.arange(n_blocks) + 0.5) * BLOCK / SR, f0b)
        voiced = np.zeros(n_out, dtype=bool)
        for s in segs:
            if s.phone not in throat.UNVOICED:
                voiced[int(np.ceil(s.t0 / throat.FRAME)): int(np.ceil(s.t1 / throat.FRAME))] = True
        oracle = throat.synthesize(np.where(voiced, f0, 0.0), sp, apr, SR, np.random.default_rng(0))
        formant = resample_poly(sing(notes, 44100, voice, seed=1, lexicon=lexicon), 80, 147)
        takes = {"soulx": x, "oracle": oracle, "formant": formant}
        for name, y in takes.items():
            sf.write(str(args.out / f"{seg}.{name}.wav"), (0.9 * y / max(np.max(np.abs(y)), 1e-9)).astype(np.float32), SR)
        # a verse (four lines) at a time; SoulX's cut where MFA found the lines, ours where we sing them
        lines, cur = [], []
        for k, n in enumerate(label["notes"]):
            cur.append(k)
            if n["line_end"] or k == len(label["notes"]) - 1:
                lines.append(cur)
                cur = []
        found = {p["note"]: p for p in al["phones"]}
        for g0 in range(0, len(lines), 4):
            group = [k for line in lines[g0: g0 + 4] for k in line]
            words, i = [], group[0]
            while i <= group[-1]:
                words.append(label["notes"][i]["word"].replace("-", "").replace("*", ""))
                i += max(1, label["notes"][i]["word_len"])
            ref = normalize(" ".join(words))
            first, last = notes[group[0]], notes[group[-1]]
            src_a = min(p["start"] for p in al["phones"] if p["note"] == group[0]) if group[0] in found else first.start
            src_b = max(p["end"] for p in al["phones"] if p["note"] == group[-1]) if group[-1] in found else last.start + last.dur
            our_a = min(s.t0 for s in segs if abs(s.t0 - first.start) < 0.4 and s.role in ("onset", "vowel"))
            our_b = last.start + last.dur
            for name, y in takes.items():
                a, b = (src_a, src_b) if name == "soulx" else (our_a, our_b)
                cut = y[max(int((a - 0.1) * SR), 0): int((b + 0.15) * SR)]
                cut = resample_poly(cut, 2, 3).astype(np.float32)
                cut /= np.abs(cut).max() + 1e-9
                parts, _ = model.transcribe(cut, language="en", beam_size=5, temperature=0.0,
                                            condition_on_previous_text=False, vad_filter=False, no_repeat_ngram_size=5)
                heard = normalize(" ".join(p.text for p in parts))
                _, pairs = word_align(ref, heard)
                while pairs and not pairs[-1][0]:
                    pairs.pop()
                e = sum(r != h for r, h in pairs)
                t = totals.setdefault(name, [0, 0])
                t[0] += e
                t[1] += len(ref)
        print(f"{key}: " + "  ".join(f"{k} {v[0]}/{v[1]}" for k, v in totals.items()), flush=True)
    print("WER: " + "  ".join(f"{k} {v[0] / max(v[1], 1):.1%}" for k, v in totals.items()))


if __name__ == "__main__":
    main()
