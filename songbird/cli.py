"""Command line: `songbird render` now, `songbird sing` once the pipeline is whole."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from . import __version__, genome as genome_mod, phrasing as phrasing_mod, synth
from .realize import choose_params, realize
from .synth import master
from .synth.voice import VoiceParams


def render_command(args: argparse.Namespace) -> int:
    genome = genome_mod.load(args.genome)
    params = choose_params(genome)
    if args.form:
        params = replace(params, form=tuple(args.form))
    if args.choir is not None:
        params = replace(params, choir=args.choir)
    # a person's phrasing: the file given, or the one the seed carries
    phrasing_json = json.loads(Path(args.phrasing).read_text()) if args.phrasing else genome.source.get("seed_phrasing")
    phrasing = phrasing_mod.from_json(phrasing_json) if phrasing_json else None
    score = realize(genome, params, phrasing=phrasing)
    defaults = VoiceParams()
    voice = replace(defaults, **{k: type(getattr(defaults, k))(v) for k, v in (kv.split("=", 1) for kv in args.voice)})

    out = Path(args.out or Path("renders") / (Path(args.genome).stem + ".flac"))
    out.parent.mkdir(parents=True, exist_ok=True)

    mix = synth.render(score, seed=params.seed, voice=voice)
    mastered = master.master(mix, synth.SR)
    pcm = master.to_pcm16(mastered, seed=params.seed)
    master.write_flac(out, pcm, synth.SR)

    record = {
        "id": master.pcm_sha256(pcm),
        "title": genome.title,
        "params": params.to_dict(),
        "voice": asdict(voice),
        "phrasing": {k: v for k, v in phrasing_json.items() if k not in ("phrases", "fields")} if phrasing_json else None,
        "loudness_lufs": round(master.loudness(pcm / 32768.0, synth.SR), 2),
        "peak_dbfs": round(20 * np.log10(np.max(np.abs(pcm)) / 32768.0), 2),
        "duration": round(len(pcm) / synth.SR, 3),
        "program_version": __version__,
    }
    out.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")
    out.with_suffix(".score.json").write_text(json.dumps(score.to_dict()) + "\n")

    if args.stems:
        import soundfile as sf

        for name, stem in synth.render_stems(score, seed=params.seed, voice=voice).items():
            sf.write(str(out.with_name(f"{out.stem}.{name}.wav")), stem, synth.SR, subtype="FLOAT")

    print(f"{out}  {record['duration']:.1f}s  {record['loudness_lufs']} LUFS  id {record['id'][:12]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="songbird", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    render = commands.add_parser("render", help="render a genome with its seed parameters")
    render.add_argument("genome", help="path to a genome JSON file")
    render.add_argument("--out", help="output FLAC path (default renders/<genome>.flac)")
    render.add_argument("--form", nargs="+", help="override the section order, e.g. intro verse refrain")
    render.add_argument("--stems", action="store_true", help="also write each part, dry, as WAV")
    render.add_argument("--voice", nargs="*", default=[], metavar="FIELD=VALUE",
                        help="override the singer, e.g. --voice tract=1.0 shift=-12 rd=1.3")
    render.add_argument("--choir", type=int, metavar="N",
                        help="lineage voices joining in harmony where the song has a choir (stand-ins for now)")
    render.add_argument("--phrasing", metavar="FILE",
                        help="sing with a person's phrasing, from tools/phrasing.py (default: the seed's own, if any)")
    render.set_defaults(run=render_command)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
