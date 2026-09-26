"""Measure a rendition in each style the way BAND.md and MIX.md measure the seed's band.

    uv run python tools/stylemeter.py songs/h-now-its-by-you.json --machine fictional:ada --date 2026-09-26 \
        [--styles gospel country ...] [--form intro verse refrain] [--choir 2] [--wer] [--out DIR]

For each style (every one in the palette by default) it renders the song as that machine would sing it in
that style (songbird render --style), mixes and masters it, and reports:

- the master: integrated loudness, true peak, sample peak, loudness range;
- the voice over the band in each sung section (voice bus against band bus, LUFS while the voice sings),
  and the band's own loudness section by section (its arc);
- each instrument's level while it plays (its dry stem), to see the balance inside the band;
- clashes: comping notes on the pitch being sung at their onset, and any chord colour forming a second or
  a tritone with a sung note on a strong beat;
- with --wer, Whisper's word error rate on the finished mix (tools/wer_suite.py's method), section by section;
- with --out, the FLAC of each (mastered) for listening.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from songbird import cli, drift as D, genome as G, harvest as H, style as S, synth, variation  # noqa: E402
from songbird.realize import choose_params, realize  # noqa: E402
from songbird.synth import master, mixing  # noqa: E402
from songbird.synth.mixing import MixParams  # noqa: E402

SR = synth.SR
LEADS = ("lead", "quote", "counter", "descant", "under", "tone", "double", "hook", "fills")


def clash_count(score) -> tuple[int, int]:
    """(band notes starting on a pitch being sung, of the comping parts), counting only the pitched band."""
    sung = [n for n in score.notes if n.part == "voice" or n.part.startswith("choir")]
    band = [n for n in score.notes if n.part != "voice" and not n.part.startswith("choir") and n.pitch > 0]
    roles = {}
    for s in score.band.get("sections", []):
        for p, what in s["parts"].items():
            roles.setdefault(p, set()).add(what)
    comping = [n for n in band if not (roles.get(n.part, set()) <= set(LEADS)) and n.part not in S.UNPITCHED]
    hits = 0
    for n in comping:
        if any(v.start - 0.02 <= n.start < v.start + v.dur - 0.03 and abs(v.pitch - n.pitch) < 0.5 for v in sung):
            hits += 1
    return hits, len(comping)


def measure(genome, params, voice, drift, words, out: Path | None, wer_model=None) -> dict:
    score = variation.lay(realize(genome, params, lyrics=words), params)
    singer = cli._singer(params, [])
    stems = synth.render_stems(score, seed=params.seed, voice=singer)
    mix = MixParams.from_dict(params.mix or {})
    taps, mtaps = {}, {}
    mixed = mixing.mix(stems, SR, params.seed, mix, taps=taps)
    final = master.master(mixed, SR, taps=mtaps)
    pcm = master.to_pcm16(final, seed=params.seed)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        master.write_flac(out, pcm, SR)
    gain = 10 ** (mtaps["gain_db"] / 20)
    x = pcm / 32768.0
    report = {"style": params.style.name, "feel": params.style.feel, "tempo": params.tempo,
              "duration": round(len(x) / SR, 1), "lufs": round(master.loudness(x, SR), 2),
              "true_peak": round(master.true_peak(x), 2), "peak": round(20 * np.log10(np.abs(x).max() + 1e-12), 2),
              "lra": round(master.loudness_range(x, SR), 1)}
    singing = taps.get("singing")
    voice_bus = taps["voice"] * gain if taps.get("voice") is not None else None
    band_bus = taps["band"] * gain if taps.get("band") is not None else None
    sections = []
    for name, t0, t1 in score.sections:
        a, b = int(t0 * SR), int(t1 * SR)
        row = {"section": name}
        if band_bus is not None:
            seg = band_bus[a:b]
            row["band"] = round(master.loudness(seg, SR), 1) if np.any(seg) else None
        if voice_bus is not None and singing is not None:
            on = singing[a:b] > 0.5
            if on.mean() > 0.2 and band_bus is not None:
                v = master.loudness(voice_bus[a:b][on], SR)
                bb = master.loudness(band_bus[a:b][on], SR)
                row["voice_over_band"] = round(v - bb, 1) if np.isfinite(bb) else None
        sections.append(row)
    report["sections"] = sections
    report["stems"] = {}
    for name, stem in sorted(stems.items()):
        if name == "voice" or name.startswith("choir"):
            continue
        playing = np.abs(stem).max(axis=1) > 1e-4
        report["stems"][name] = round(master.loudness(stem[playing], SR), 1) if playing.mean() > 0.01 else None
    hits, total = clash_count(score)
    report["on_sung_pitch"] = f"{hits}/{total}"
    if wer_model is not None:
        from wer_suite import score_sections
        from songbird.synth.voice import schedule

        notes = sorted(score.part("voice"), key=lambda n: n.start)
        segs = schedule(notes, singer, genome.lexicon)
        e, w, misses, _ = score_sections(wer_model, x.mean(axis=1), notes, segs, False)
        report["wer"] = round(e / max(w, 1), 3)
        report["misses"] = misses[:12]
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("genome")
    ap.add_argument("--machine", default="fictional:ada")
    ap.add_argument("--date", default="2026-09-26")
    ap.add_argument("--styles", nargs="*", default=None)
    ap.add_argument("--form", nargs="*", default=None)
    ap.add_argument("--choir", type=int, default=None)
    ap.add_argument("--wer", action="store_true")
    ap.add_argument("--out", help="write each style's mastered FLAC here")
    ap.add_argument("--json", help="write the reports here")
    args = ap.parse_args()
    genome = G.load(args.genome)
    voice = H.machine_voice(args.machine)
    drift = D.drift(D.parse(args.date), voice.hash)
    model = None
    if args.wer:
        sys.path.insert(0, str(Path(__file__).parent))
        from faster_whisper import WhisperModel

        model = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=2)
    reports = []
    for name in args.styles or list(S.RING):
        params = choose_params(genome, None, voice, drift, style=name)
        if args.form:
            params = replace(params, form=tuple(args.form))
        if args.choir is not None:
            params = replace(params, choir=args.choir)
        words = cli.words(genome, params, sung_by_a_machine=True)
        out = Path(args.out) / f"{name}.flac" if args.out else None
        r = measure(genome, params, voice, drift, words, out, model)
        reports.append(r)
        vob = [s["voice_over_band"] for s in r["sections"] if s.get("voice_over_band") is not None]
        print(f"{name:11s} {r['feel']:8s} {r['tempo']:6.1f} bpm {r['duration']:5.1f}s  {r['lufs']:6.1f} LUFS  "
              f"TP {r['true_peak']:5.1f}  peak {r['peak']:5.1f}  LRA {r['lra']:4.1f}  voice/band "
              f"{min(vob) if vob else float('nan'):5.1f}..{max(vob) if vob else float('nan'):5.1f} dB  "
              f"on-sung {r['on_sung_pitch']}" + (f"  WER {r['wer']:.1%}" if "wer" in r else ""))
        print("            sections " + "  ".join(f"{s['section']}:{s.get('band')}/{s.get('voice_over_band')}"
                                                for s in r["sections"]))
        print("            stems    " + "  ".join(f"{k}:{v}" for k, v in r["stems"].items()))
        sys.stdout.flush()
    if args.json:
        Path(args.json).write_text(json.dumps(reports, indent=1))


if __name__ == "__main__":
    main()
