"""Measure finished packets at equal loudness, optionally checking words (dev-only).

    uv run python tools/packet_review.py renders/review/*.flac --wer --out renders/review/report.json

Only synthesized packets belong in this comparison, not raw volunteer takes.
Whisper runs locally; --wer uses the cached base.en model unless --model names
another installed model. WER uses wer_suite's section scorer, including its
repetition/hallucination handling. It is a regression aid, not a listening test.
The current checkout reconstructs section times; the report says whether it
matches the packet's program. No code from the packet is executed.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import fields
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from songbird import genome as G, pack, phrasing as P, variation  # noqa: E402
from songbird.arrange import Lyrics  # noqa: E402
from songbird.realize import Params, realize  # noqa: E402
from songbird.synth import master  # noqa: E402
from songbird.synth.voice import VoiceParams, schedule  # noqa: E402


def db(power: float) -> float | None:
    return round(float(10 * np.log10(power)), 3) if power > 0 else None


def review(path: Path, program_hash: str, model=None) -> dict:
    record = pack.read_record(path)  # checks the audio against its recorded id
    source = pack.read_member(path, "genome.json")
    if source is None:
        raise ValueError(f"{path.name} needs its program packet; use songbird pack first")
    pcm, sr = sf.read(path, dtype="int16", always_2d=True)
    y = pcm / 32768.0
    mono = y.mean(axis=1)
    power = float(np.mean(y**2))
    row = {"file": path.name, "id": record["id"], "duration": round(len(y) / sr, 3),
           "program_sha256": record.get("program_sha256"),
           "same_program": record.get("program_sha256") == program_hash,
           "loudness_lufs": round(master.loudness(y, sr), 2),
           "loudness_range_lu": round(master.loudness_range(y, sr), 2),
           "true_peak_dbtp": round(master.true_peak(y), 2),
           "mono_power_loss_db": db(float(np.mean(mono**2)) / power) if power else None}
    with zipfile.ZipFile(path) as z:
        row["payload_uncompressed_bytes"] = sum(i.file_size for i in z.infolist())
    row["payload_archive_bytes"] = path.stat().st_size - pack.packet_start(path)
    row["within_budget"] = max(row["payload_uncompressed_bytes"], row["payload_archive_bytes"]) <= pack.LIMIT
    if model is not None:
        import wer_suite as W

        if sr != W.SR:
            raise ValueError(f"{path.name}: section WER expects {W.SR} Hz, got {sr}")
        genome = G.from_dict(json.loads(source))
        params = Params.from_dict(record["params"])
        lead, choir = P.inherited(genome.source, record)
        score = variation.lay(realize(
            genome, params, phrasing=P.from_json(lead) if lead else None,
            choir=[P.from_json(c) if c else None for c in choir],
            lyrics=Lyrics.from_dict(record["lyrics"]) if record.get("lyrics") else None), params)
        notes = sorted(score.part("voice"), key=lambda n: n.start)
        known = {f.name for f in fields(VoiceParams)}
        singer = VoiceParams(**{k: v for k, v in (record.get("singer") or params.singer).items() if k in known})
        segs = schedule(notes, singer, genome.lexicon)
        edits, words, _, sections = W.score_sections(model, mono, notes, segs, False) if notes else (0, 0, [], [])
        row["intelligibility"] = {"edits": edits, "words": words,
                                  "wer": edits / words if words else None, "sections": sections}
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("packets", nargs="+", type=Path)
    ap.add_argument("--wer", action="store_true", help="also transcribe each sung section locally")
    ap.add_argument("--model", default="base.en", help="cached Whisper model name or local directory")
    ap.add_argument("--out", type=Path, help="save machine-readable comparison")
    args = ap.parse_args()
    model = None
    if args.wer:
        from faster_whisper import WhisperModel

        model = WhisperModel(args.model, device="cpu", compute_type="int8", local_files_only=True)
    digest = pack.program_sha256(pack.program_files())
    report = {"budget": pack.budget(), "wer_model": args.model if args.wer else None, "renditions": []}
    for path in args.packets:
        row = review(path, digest, model)
        report["renditions"].append(row)
        heard = row.get("intelligibility", {})
        wer = f"; WER {heard['edits']}/{heard['words']} ({heard['wer']:.1%})" if heard.get("wer") is not None else ""
        match = "" if row["same_program"] else "; section reconstruction uses a different program revision"
        print(f"{path.name}: {row['loudness_lufs']} LUFS; {row['loudness_range_lu']} LU range; "
              f"{row['true_peak_dbtp']} dBTP{wer}{match}", flush=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
