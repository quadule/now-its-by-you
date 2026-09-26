"""Command line: `songbird render`, `harvest`, `year`, `pack` and `unpack` now, `songbird sing` once the pipeline is whole."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path

import numpy as np

from . import __version__, drift as drift_mod, genome as genome_mod, harvest, pack as pack_mod, phrasing as phrasing_mod, synth, variation
from .arrange import ArrangeError, arrange, problem
from .realize import Params, choose_params, realize
from .synth import master
from .synth.mixing import MixParams
from .synth.voice import VoiceParams


def _machine(args: argparse.Namespace):
    """The voice (--machine) and the drift (--date, or now when a machine sings)."""
    voice = harvest.machine_voice(args.machine) if getattr(args, "machine", None) else None
    t = drift_mod.parse(args.date) if getattr(args, "date", None) else (drift_mod.now() if voice is not None else None)
    drift = drift_mod.drift(t, (voice or harvest.Voice()).hash) if t is not None else None
    return voice, drift


def _parent_record(path: str | None) -> dict | None:
    """A parent rendition's record: from the rendition itself (a FLAC carrying its packet) or its render record."""
    return pack_mod.read_record(path) if path else None


def _parent(path: str | None) -> Params | None:
    """A parent rendition's parameters."""
    record = _parent_record(path)
    return Params.from_dict(record["params"]) if record else None


def words(genome, params: Params, seed: int | None = None, sung_by_a_machine: bool = False):
    """The words to sing: drawn from the song's bank with `seed` (--lyrics-seed); or, when a machine or a
    date sings a song that has a bank, with the rendition's own seed (from the machine, the instant and the
    parent) and the leanings chosen with its parameters; otherwise None, the seed's own words (as also for
    a form set by hand that the bank can't fill, unless words were asked for)."""
    if seed is None and not (sung_by_a_machine and genome.source.get("bank") and not problem(genome, params.form)):
        return None
    return arrange(genome, params.form, params.seed if seed is None else seed, variation.leanings(params))


def _singer(params: Params, overrides: list[str]) -> VoiceParams:
    defaults = VoiceParams()
    chosen = {k: type(getattr(defaults, k))(v) for k, v in params.singer.items() if hasattr(defaults, k)}
    singer = replace(defaults, **chosen)
    return replace(singer, **{k: type(getattr(defaults, k))(v) for k, v in (kv.split("=", 1) for kv in overrides)})


def render_one(genome, params: Params, out: Path, *, voice=None, drift=None, lyrics=None, phrasing_json=None,
               choir_json=(), singer_overrides=(), stems: bool = False, mix_overrides=(), parent: dict | None = None,
               packet_genome: str | Path | None = None) -> dict:
    """Render one rendition to out (FLAC), with its record (.json), score (.score.json) and, if its words were
    drawn, its lyric sheet (.txt) beside it. With packet_genome (the genome file sung), the FLAC carries its
    packet: the program, the genome, the record and the words (songbird/pack.py)."""
    phrasing = phrasing_mod.from_json(phrasing_json) if phrasing_json else None
    choir = [phrasing_mod.from_json(d) for d in choir_json]
    score = variation.lay(realize(genome, params, phrasing=phrasing, choir=choir, lyrics=lyrics), params)
    singer = _singer(params, list(singer_overrides))
    # the mix: as the rendition chose it (params.mix: the machine's room, its drift and its habits), then any --mix
    mixing = MixParams.parse(list(mix_overrides), base=MixParams.from_dict(params.mix or {}))

    out.parent.mkdir(parents=True, exist_ok=True)
    # the earlier versions' singers, the parent's first, sing the lineage choir (as many as it has voices)
    lineage_singers = ([{"id": parent.get("id"), "singer": parent.get("singer")}, *(parent.get("lineage_singers") or [])]
                       if parent and parent.get("singer") else [])[: variation.CHOIR_MAX]
    ancestors = synth.ancestors_from(lineage_singers, learned=singer.engine == "learned")
    mix = synth.render(score, seed=params.seed, voice=singer, mix_params=mixing, ancestors=ancestors)
    mastered = master.master(mix, synth.SR)
    pcm = master.to_pcm16(mastered, seed=params.seed)
    master.write_flac(out, pcm, synth.SR)

    record = {
        "id": master.pcm_sha256(pcm),
        "title": genome.title,
        **pack_mod.lineage(parent),
        "rendered_at": drift.to_dict()["at"] if drift is not None else None,
        "params": params.to_dict(),
        "lyrics": lyrics.to_dict() if lyrics else None,  # the words drawn from the bank; None: the seed's own
        "singer": asdict(singer),
        "lineage_singers": lineage_singers,  # who sings in the choir: the earlier versions, the parent's first
        "voice": voice.to_dict() if voice is not None else None,
        "drift": drift.to_dict() if drift is not None else None,
        "phrasing": {k: v for k, v in phrasing_json.items() if k not in ("phrases", "fields")} if phrasing_json else None,
        "choir_phrasings": [{k: v for k, v in d.items() if k not in ("phrases", "fields")} for d in choir_json] or None,
        "mix": mixing.to_dict(),
        "loudness_lufs": round(master.loudness(pcm / 32768.0, synth.SR), 2),
        "loudness_range_lu": round(master.loudness_range(pcm / 32768.0, synth.SR), 2),
        "true_peak_dbtp": round(master.true_peak(pcm / 32768.0), 2),
        "peak_dbfs": round(20 * np.log10(np.max(np.abs(pcm)) / 32768.0), 2),
        "duration": round(len(pcm) / synth.SR, 3),
        "program_version": __version__,
    }
    if packet_genome is not None:  # one file: the record and the words travel inside it
        sung = lyrics.sheet(genome.title) if lyrics else pack_mod.words_as_sung(score.to_dict(), genome.title)
        pack_mod.pack(out, record, packet_genome, lyrics=sung)
    else:
        out.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")
        out.with_suffix(".score.json").write_text(json.dumps(score.to_dict()) + "\n")
        if lyrics:
            out.with_suffix(".txt").write_text(lyrics.sheet(genome.title))

    if stems:
        import soundfile as sf

        for name, stem in synth.render_stems(score, seed=params.seed, voice=singer, ancestors=ancestors).items():
            sf.write(str(out.with_name(f"{out.stem}.{name}.wav")), stem, synth.SR, subtype="FLOAT")

    print(f"{out}  {record['duration']:.1f}s  {record['loudness_lufs']} LUFS  id {record['id'][:12]}")
    return record


def _arrangement(items: list[str]) -> dict | None:
    """--arrange FIELD=VALUE ... as Style fields (songbird/style.py): true/false, numbers, or names."""
    out = {}
    for item in items or []:
        key, _, value = item.partition("=")
        low = value.strip().lower()
        if low in ("true", "yes", "on", "false", "no", "off"):
            out[key] = low in ("true", "yes", "on")
        else:
            try:
                out[key] = int(value) if low.lstrip("-").isdigit() else float(value)
            except ValueError:
                out[key] = value
    return out or None


def render_command(args: argparse.Namespace) -> int:
    genome = genome_mod.load(args.genome)
    voice, drift = _machine(args)
    parent = _parent_record(args.parent)
    params = choose_params(genome, Params.from_dict(parent["params"]) if parent else None, voice, drift, seed=args.seed,
                           style=args.style, arrange=_arrangement(args.arrange))
    if args.form:
        params = replace(params, form=tuple(args.form))
    if args.choir is not None:
        params = replace(params, choir=args.choir)
    # a person's phrasing: the file given, or the one the seed carries
    phrasing_json = json.loads(Path(args.phrasing).read_text()) if args.phrasing else genome.source.get("seed_phrasing")
    choir_json = [json.loads(Path(f).read_text()) for f in args.choir_phrasing]
    if choir_json and args.choir is None:
        params = replace(params, choir=len(choir_json))
    try:
        lyrics = words(genome, params, args.lyrics_seed, sung_by_a_machine=voice is not None or drift is not None)
    except (ArrangeError, ValueError) as e:
        print(f"songbird: can't draw words for that form: {e}", file=sys.stderr)
        return 2
    out = Path(args.out or Path("renders") / (Path(args.genome).stem + ".flac"))
    render_one(genome, params, out, voice=voice, drift=drift, lyrics=lyrics, phrasing_json=phrasing_json,
               choir_json=choir_json, singer_overrides=args.voice, stems=args.stems, mix_overrides=args.mix,
               parent=parent, packet_genome=args.genome if args.pack else None)
    return 0


# ---------------------------------------------------------------- the packet

def pack_command(args: argparse.Namespace) -> int:
    flac = Path(args.flac)
    record_path = Path(args.record) if args.record else flac.with_suffix(".json")
    if not record_path.exists():
        print(f"songbird: no render record at {record_path} (--record)", file=sys.stderr)
        return 2
    record = json.loads(record_path.read_text())
    genome_path = Path(args.genome) if args.genome else None
    if genome_path is None:  # the song whose title the record carries
        songs = Path(__file__).resolve().parents[1] / "songs"
        genome_path = next((g for g in sorted(songs.glob("*.json"))
                            if json.loads(g.read_text()).get("title") == record.get("title")), None)
        if genome_path is None:
            print(f"songbird: which genome sang {record.get('title')!r}? (--genome)", file=sys.stderr)
            return 2
    sheet, score = flac.with_suffix(".txt"), flac.with_suffix(".score.json")
    lyrics = sheet.read_text() if sheet.exists() else \
        pack_mod.words_as_sung(json.loads(score.read_text()), record.get("title")) if score.exists() else None
    out = pack_mod.pack(flac, record, genome_path, lyrics=lyrics, out=args.out)
    print(f"{out}  carries the program ({out.stat().st_size / 2**20:.1f} MB in all)")
    return 0


def unpack_command(args: argparse.Namespace) -> int:
    to = Path(args.to) if args.to else Path(args.flac).with_name(Path(args.flac).stem + "-unpacked")
    try:
        pack_mod.unpack(args.flac, to)
    except ValueError as e:
        print(f"songbird: {e}", file=sys.stderr)
        return 2
    print(f"unpacked into {to}")
    return 0


# ---------------------------------------------------------------- harvest

DRIVES = {
    "tongue": "the mode family (and, once the singer reads it, its vowels)",
    "machine": "how busy the band is; uptime: how tired the voice and the band sound today",
    "ages": "tempo, how far the tempo wanders, how worn the voice, the band and the recording are, the lyric's era",
    "colour": "the singer's, the band's and the record's brightness, the mix's width, the lyric's mood",
    "words": "the lyric's vocabulary, era, appetite for rare verses, the verse count, the band's ornament",
    "hand": "how far ahead of or behind the beat the singer sits, rubato, the band's swing, tempo",
    "room": "the reverb every rendition on this machine lives in, and how soon it answers",
}


def _describe(voice: harvest.Voice, without=()) -> str:
    lines = []
    for name in harvest.SIGNALS:
        value = voice.signals()[name]
        if value is None:
            why = "left out" if name in without else (
                "not read: a microphone isn't supported yet" if name == "room" else
                "not read: run `songbird harvest` at a terminal to type the line" if name == "hand" else "not read")
            lines.append(f"  {name:8s} ({why})")
            continue
        parts = []
        for key, v in value.items():
            if isinstance(v, dict):
                v = " ".join(f"{k} {x:g}" for k, x in v.items() if x)
            elif isinstance(v, list):
                v = " ".join(f"{x:g}" for x in v)
            parts.append(f"{key} {v}")
        lines.append(f"  {name:8s} {', '.join(parts)}\n  {'':8s}   -> {DRIVES[name]}")
    return "\n".join(lines)


def _shown(path: Path) -> str:
    home = str(Path.home())
    return "~" + str(path)[len(home):] if str(path).startswith(home) else str(path)


def harvest_command(args: argparse.Namespace) -> int:
    if args.fictional:
        voice = harvest.fictional(args.fictional)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(voice.to_dict(), indent=2, sort_keys=True) + "\n")
        print(f"fictional machine {args.fictional!r}  voice {voice.hash}\n{_describe(voice)}")
        if args.show:
            print(json.dumps(voice.to_dict(), indent=2, sort_keys=True))
        return 0

    path = harvest.cache_path()
    cached = harvest.load()
    stored = json.loads(path.read_text()) if cached is not None else {}
    kept_out = set(stored.get("without", []))
    without = (kept_out | {harvest.signal_name(s) for s in args.without}) - {harvest.signal_name(s) for s in args.allow}
    # a voice read quietly by a render (languages, size, screen) is read in full the first time a person asks
    if cached is not None and not (args.refresh or args.new_voice or args.allow or stored.get("quiet")):
        voice = replace(cached, **{s: None for s in without})  # leaving a signal out never reads anything
        if args.wallpaper and "colour" not in without:
            voice = replace(voice, colour=harvest.colour(Path(args.wallpaper)))
        voice = harvest.rested(voice)
        fresh = False
    else:
        typing = sys.stdin.isatty() and sys.stdout.isatty() and not args.no_typing and "hand" not in without
        salt = cached.salt if cached is not None and not args.new_voice else None
        voice = harvest.harvest(without, wallpaper=Path(args.wallpaper) if args.wallpaper else None, typing=typing,
                                salt=salt)
        if cached is not None and voice.hand is None and cached.hand is not None and "hand" not in without:
            voice = replace(voice, hand=cached.hand)  # a typed sample is kept until it is typed again
        fresh = True
    if not args.no_save:
        harvest.save(voice)
        data = json.loads(path.read_text())
        data["without"] = sorted(without)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    where = f"cached in {_shown(path)}" if not args.no_save else "not saved"
    print(f"This machine's voice ({'harvested now' if fresh else 'from the cache'}, {where}), hash {voice.hash}")
    if args.show:
        print(_describe(voice, without))
        print("\nExactly what is kept, and all that leaves this machine in a rendition's record:")
        print(json.dumps(voice.to_dict(), indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------- year

NOTE_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
FORM_LETTERS = {"intro": "i", "verse": "V", "refrain": "R", "turn": "t", "break": "k", "bridge": "B",
                "bridge2": "b", "tag": "g", "outro": "o"}


def _form(form) -> str:
    return "".join(FORM_LETTERS.get(name, name[:1]) for name in form)


def year_command(args: argparse.Namespace) -> int:
    genome = genome_mod.load(args.genome)
    voice = harvest.machine_voice(args.machine)
    parent = _parent(args.parent)
    start = drift_mod.parse(args.start) if args.start else drift_mod.parse(drift_mod.when(drift_mod.now()).date().isoformat())
    label = args.machine.split(":", 1)[-1] if args.machine.startswith("fictional:") else Path(args.machine).stem
    print(f"{genome.title}: machine {args.machine} (voice {voice.hash}), {args.days} days from "
          f"{drift_mod.when(start).date()}, every {args.step:g}")
    print(f"form: {', '.join(f'{v}={k}' for k, v in FORM_LETTERS.items())}\n")
    head = f"{'date':10s}  {'key':3s} {'mode':10s} {'bpm':>5s}  {'form':16s} {'band':14s} {'dens':>4s} {'brt':>4s} " \
           f"{'harp':16s} {'hum':>5s} {'rit':>4s} {'breath':>6s} {'vib':>4s}  {'mood (p l d t)':19s} {'era':>5s}"
    print(head)
    rows = []
    t = start
    while t < start + args.days:
        d = drift_mod.drift(t, voice.hash)
        p = choose_params(genome, parent, voice, d)
        sing = _singer(p, [])
        mood = p.leanings.get("mood_weights", {})
        rows.append(p)
        print(f"{drift_mod.when(t).date()!s:10s}  {NOTE_NAMES[p.tonic % 12]:3s} {p.mode:10s} {p.tempo:5.1f}  "
              f"{_form(p.form):16s} {p.band.pattern + '/' + p.band.lead:14s} {p.band.density:4.2f} "
              f"{p.band.brightness:4.2f} {p.accomp:16s} {p.humanize * 1000:4.1f}m {p.ritardando:4.2f} "
              f"{sing.breath:6.3f} {sing.vibrato_depth:4.1f}  "
              f"{' '.join(f'{mood.get(k, 1):.2f}' for k in ('plain', 'light', 'dark', 'tender')):19s} "
              f"{p.leanings.get('era_bias', 0.0):5.2f}")
        t += args.step

    def changes(key) -> int:
        values = [key(p) for p in rows]
        return sum(a != b for a, b in zip(values, values[1:]))

    tempos = [p.tempo for p in rows]
    print(f"\nover {len(rows)} renders: key changed {changes(lambda p: p.tonic)} times "
          f"({', '.join(sorted({NOTE_NAMES[p.tonic % 12] for p in rows}))}), "
          f"mode {changes(lambda p: p.mode)} ({', '.join(sorted({p.mode for p in rows}))}), "
          f"form {changes(lambda p: p.form)} ({len({p.form for p in rows})} forms, "
          f"{min(sum(n == 'verse' for n in p.form) for p in rows)}-{max(sum(n == 'verse' for n in p.form) for p in rows)} verses), "
          f"band pattern {changes(lambda p: p.band.pattern)} ({', '.join(sorted({p.band.pattern for p in rows}))}), "
          f"lead {changes(lambda p: p.band.lead)} ({', '.join(sorted({p.band.lead for p in rows}))}), "
          f"harp's picking {changes(lambda p: p.accomp)}; tempo {min(tempos):.1f}-{max(tempos):.1f}")

    if args.render:
        out_dir = Path(args.render)
        for offset, name in ((0, "day 0"), (1, "a day on"), (7, "a week on"), (30, "a month on"), (365, "a year on")):
            t = start + offset
            d = drift_mod.drift(t, voice.hash)
            p = choose_params(genome, parent, voice, d)
            day = (drift_mod.when(start) + timedelta(days=offset)).date().isoformat()
            print(f"{name}: ", end="")
            render_one(genome, p, out_dir / f"{Path(args.genome).stem}.{label}.{day}.flac", voice=voice, drift=d,
                       lyrics=words(genome, p, sung_by_a_machine=True), phrasing_json=genome.source.get("seed_phrasing"))
    return 0


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="songbird", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    render = commands.add_parser("render", help="render a genome: the seed's parameters, or a machine's at a date")
    render.add_argument("genome", help="path to a genome JSON file")
    render.add_argument("--out", help="output FLAC path (default renders/<genome>.flac)")
    render.add_argument("--machine", metavar="here|none|fictional:NAME|FILE",
                        help="sing as a machine: this one (its cached voice), a made-up one, or a voice file "
                             "(a render's .json replays its voice)")
    render.add_argument("--date", metavar="YYYY-MM-DD",
                        help="the moment for the drift: a date (noon UTC), an ISO timestamp, or now "
                             "(default: now, if a machine sings)")
    render.add_argument("--seed", type=int, help="the rendition's seed (default: from the machine, instant and parent)")
    render.add_argument("--parent", metavar="FILE",
                        help="inherit from a parent rendition: its FLAC (if it carries its packet) or its record (.json)")
    render.add_argument("--pack", action="store_true",
                        help="attach the packet: the FLAC carries the program, the genome, its record and its words "
                             "(and nothing is written beside it)")
    render.add_argument("--form", nargs="+", help="override the section order, e.g. intro verse refrain")
    render.add_argument("--lyrics-seed", type=int, metavar="N",
                        help="draw the words from the song's bank with this seed, and write their lyric sheet "
                             "beside the render (default: when a machine or a date sings, with the rendition's "
                             "own seed; otherwise the seed's own words)")
    render.add_argument("--stems", action="store_true", help="also write each part, dry, as WAV")
    render.add_argument("--voice", nargs="*", default=[], metavar="FIELD=VALUE",
                        help="override the singer, e.g. --voice tract=1.0 shift=-12 rd=1.3")
    render.add_argument("--mix", nargs="*", default=[], metavar="FIELD=VALUE",
                        help="change the mix (synth/mixing.py MixParams), e.g. --mix rt60=2.2 wear=0.5 "
                             "tone=1,1,1,0.8,0.6 balance=fiddle:2")
    render.add_argument("--style", metavar="NAME",
                        help="play it in this style (songbird/style.py STYLES: ballad, stringband, country, gospel, "
                             "shanty, songwriter, chamber, lullaby, ambient, synthfolk, lofi, indie, blues) instead of "
                             "the one the machine and its parent lead to")
    render.add_argument("--arrange", nargs="*", default=[], metavar="FIELD=VALUE",
                        help="set the arrangement's options (songbird/style.py Style), e.g. --arrange feel=waltz "
                             "lift=true ending=cold backing=gang")
    render.add_argument("--choir", type=int, metavar="N",
                        help="lineage voices joining in harmony where the song has a choir (stand-ins for now)")
    render.add_argument("--phrasing", metavar="FILE",
                        help="sing with a person's phrasing, from tools/phrasing.py (default: the seed's own, if any)")
    render.add_argument("--choir-phrasing", nargs="+", default=[], metavar="FILE",
                        help="a phrasing for each choir voice, in order (sets --choir to their number unless given)")
    render.set_defaults(run=render_command)

    harvest_parser = commands.add_parser(
        "harvest", help="read this machine's voice (see docs/HARVEST.md for exactly what is read)")
    harvest_parser.add_argument("--show", action="store_true", help="print the reduced numbers, all that is kept")
    harvest_parser.add_argument("--refresh", action="store_true", help="read the machine again (the same singer)")
    harvest_parser.add_argument("--new-voice", action="store_true", help="read the machine again as a new singer (a new salt)")
    harvest_parser.add_argument("--without", nargs="+", default=[], metavar="SIGNAL",
                                help=f"leave signals out, now and from now on: {', '.join(harvest.SIGNALS)} "
                                     "(or locale, hardware, files, screen, documents, typing, mic)")
    harvest_parser.add_argument("--allow", nargs="+", default=[], metavar="SIGNAL",
                                help="take back a --without and read the signal again")
    harvest_parser.add_argument("--wallpaper", metavar="FILE", help="read the screen's colour from this picture")
    harvest_parser.add_argument("--no-typing", action="store_true", help="don't ask to type a line")
    harvest_parser.add_argument("--no-save", action="store_true", help="don't write the cache")
    harvest_parser.add_argument("--fictional", metavar="NAME", help="make up a machine instead (the same for a name)")
    harvest_parser.add_argument("--out", metavar="FILE", help="with --fictional: write its voice to this file")
    harvest_parser.set_defaults(run=harvest_command)

    year = commands.add_parser("year", help="one machine's choices through a year, to tune the drift by eye")
    year.add_argument("genome", help="path to a genome JSON file")
    year.add_argument("--machine", required=True, metavar="here|none|fictional:NAME|FILE")
    year.add_argument("--from", dest="start", metavar="YYYY-MM-DD", help="the first day (default today)")
    year.add_argument("--days", type=float, default=365, help="how many days (default 365)")
    year.add_argument("--step", type=float, default=1, help="days between rows (default 1)")
    year.add_argument("--parent", metavar="FILE", help="inherit from a parent rendition: its packet FLAC or record (.json)")
    year.add_argument("--render", metavar="DIR",
                      help="also render the first day, a day, a week, a month and a year on into DIR")
    year.set_defaults(run=year_command)

    pack_parser = commands.add_parser("pack", help="attach the packet to a rendered FLAC: the program, genome, record, words")
    pack_parser.add_argument("flac", help="a rendered FLAC, with its record (.json) beside it")
    pack_parser.add_argument("--record", metavar="FILE", help="its render record (default: beside the FLAC)")
    pack_parser.add_argument("--genome", metavar="FILE", help="the genome it sang (default: the song with its title)")
    pack_parser.add_argument("--out", metavar="FILE", help="write the packet here (default: attach it in place)")
    pack_parser.set_defaults(run=pack_command)

    unpack_parser = commands.add_parser("unpack", help="unpack a rendition's packet into a folder")
    unpack_parser.add_argument("flac", help="a FLAC carrying its packet")
    unpack_parser.add_argument("--to", metavar="DIR", help="the folder (default: beside the FLAC)")
    unpack_parser.set_defaults(run=unpack_command)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
