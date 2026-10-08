"""Command line: `songbird render`, `harvest`, `year`, `pack`, `unpack` and `studio` now, `songbird sing` once the
pipeline is whole."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path

import numpy as np

from . import __version__, drift as drift_mod, genome as genome_mod, harvest, pack as pack_mod, phrasing as phrasing_mod, synth, variation
from . import evolve, variants as variants_mod
from .arrange import ArrangeError, Lyrics, arrange, hold, problem, sing, verse_problem
from .composition import has_lines
from .dates import us_date
from .realize import Params, choose_params, realize
from .synth import master, threads
from .synth.mixing import MixParams
from .synth.voice import VoiceParams


def _machine(args: argparse.Namespace):
    """The voice (--machine) and the drift (--date, or now when a machine sings)."""
    voice = harvest.machine_voice(args.machine) if getattr(args, "machine", None) else None
    t = drift_mod.parse(args.date) if getattr(args, "date", None) else (drift_mod.now() if voice is not None else None)
    drift = drift_mod.drift(t, (voice or harvest.Voice()).hash) if t is not None else None
    return voice, drift


def _parent_record(path: str | None) -> dict | None:
    """A parent rendition's record: from the rendition itself (a FLAC carrying its packet), its render record,
    or the render record beside a FLAC that carries none."""
    if not path:
        return None
    beside = Path(path).with_suffix(".json")
    if Path(path).suffix.lower() != ".json" and not Path(path).exists() and beside.exists():
        return json.loads(beside.read_text())
    try:
        return pack_mod.read_record(path)
    except ValueError:
        if Path(path).suffix.lower() != ".json" and beside.exists():
            return json.loads(beside.read_text())
        raise


def _parent(path_or_record, genome=None) -> Params | None:
    """A parent rendition's parameters, from its record (or the path to one). Its generation is the record's.
    A record from before its lineage held words gives the words it sang as the words it holds."""
    record = _parent_record(path_or_record) if isinstance(path_or_record, (str, Path)) else path_or_record
    if not record:
        return None
    params = Params.from_dict(record["params"])
    if "generation" in record:
        params = replace(params, generation=int(record["generation"]))
    if not params.words and genome is not None and genome.source.get("bank") and record.get("lyrics"):
        held = hold(genome, Lyrics.from_dict(record["lyrics"]))
        if not verse_problem(genome, held.get("verses", [])):
            params = replace(params, words=held)
    return params


def words(genome, params: Params, seed: int | None = None, sung_by_a_machine: bool = False, voice=None, drift=None):
    """The words to sing: drawn from the song's bank with `seed` (--lyrics-seed); or, when a machine or a
    date sings a song that has a bank, the words its lineage holds (params.words, chosen with its parameters
    by songbird.evolve, fitted to its form if the form was set afterwards); otherwise None, the seed's own
    words (as also for a form set by hand that the bank can't fill, unless words were asked for)."""
    if seed is not None:
        return arrange(genome, params.form, seed, variation.leanings(params))
    if not (sung_by_a_machine and genome.source.get("bank") and not problem(genome, params.form)):
        return None
    return sing(genome, params.form, evolve.fitted(genome, params, voice, drift))


def evolution(genome, params: Params, parent: Params | None, lyrics=None, changes=None) -> dict | None:
    """What a record says of the lineage's tune and words: each variant sung (in words), what changed from the
    parent and why, and how far the tune's contour has come from the parent and from the seed (as the lineage
    gate will measure it). None for a rendition with nothing to say (the seed as written), so its record
    stays as it was."""
    if not params.variants and not changes and parent is None:
        return None
    return {
        "variants": [{"about": variants_mod.describe(genome, v, lyrics), **v.to_dict()} for v in params.variants],
        "changes": list(changes or []),
        "distance": {"parent": variants_mod.distance(genome, parent.variants if parent else (), params.variants),
                     "seed": variants_mod.distance(genome, (), params.variants)},
    }


def _singer(params: Params, overrides: list[str]) -> VoiceParams:
    defaults = VoiceParams()
    chosen = {k: type(getattr(defaults, k))(v) for k, v in params.singer.items() if hasattr(defaults, k)}
    singer = replace(defaults, **chosen)
    return replace(singer, **{k: type(getattr(defaults, k))(v) for k, v in (kv.split("=", 1) for kv in overrides)})


def choir_of(parent: dict | None, singer: VoiceParams) -> tuple[list[dict], list[VoiceParams]]:
    """The earlier versions' singers, the parent's first, who sing the lineage choir (as many as it has
    voices): as a record keeps them, and as the synth sings them."""
    lineage_singers = ([{"id": parent.get("id"), "singer": parent.get("singer")}, *(parent.get("lineage_singers") or [])]
                       if parent and parent.get("singer") else [])[: variation.CHOIR_MAX]
    return lineage_singers, synth.ancestors_from(lineage_singers, learned=singer.engine == "learned")


ARTIST = "The Volunteers"  # the FLAC tag: who the song is by (the artist's decision, 2026-09-27; the program stays Songbird)


def render_one(genome, params: Params, out: Path, *, voice=None, drift=None, lyrics=None, phrasing_json=None,
               choir_json=(), singer_overrides=(), stems: bool = False, mix_overrides=(), parent: dict | None = None,
               midi_file: bool = False,
               packet_genome: str | Path | None = None, changes=None, chosen_by_you=None, progress=None) -> dict:
    """Render one rendition to out (FLAC), with its record (.json), score (.score.json) and, if its words were
    drawn or held, its lyric sheet (.txt) beside it. With packet_genome (the genome file sung), the FLAC carries
    its packet: the program, the genome, the record and the words (songbird/pack.py). parent: the parent's
    record; changes: what choosing these parameters changed from it (choose_params' log), for the record's
    evolution (docs/EVOLUTION.md); chosen_by_you: which of its choices a person made, and what the program had
    chosen (songbird.edits.marks), kept in the record; progress: told each part's name as the render starts
    on it (synth.render), then "master"."""
    phrasing = phrasing_mod.from_json(phrasing_json) if phrasing_json else None
    choir_json = list(choir_json)
    choir = [phrasing_mod.from_json(d) for d in choir_json]
    score = variation.lay(realize(genome, params, phrasing=phrasing, choir=choir, lyrics=lyrics), params)
    singer = _singer(params, list(singer_overrides))
    # the mix: as the rendition chose it (params.mix: the machine's room, its drift and its habits), then any --mix
    mixing = MixParams.parse(list(mix_overrides), base=MixParams.from_dict(params.mix or {}))

    out.parent.mkdir(parents=True, exist_ok=True)
    lineage_singers, ancestors = choir_of(parent, singer)
    mix = synth.render(score, seed=params.seed, voice=singer, mix_params=mixing, ancestors=ancestors,
                       progress=progress)
    if progress is not None:
        progress("master")
    mastered = master.master(mix, synth.SR, target=float(getattr(params, "loudness", master.TARGET_LUFS)))
    del mix  # (each let go once the next is made: a whole song is a tenth of a gigabyte a copy)
    pcm = master.to_pcm16(mastered, seed=params.seed)
    del mastered
    lineage = pack_mod.lineage(parent)
    tags = dict(
        title=genome.title, artist=ARTIST, date=drift.to_dict()["at"][:10] if drift is not None else None,
        comment=f"Generation {lineage['generation']}, id {master.pcm_sha256(pcm)[:12]}."
                + (" This file is also the program that sang it: run it with python3, or unzip it."
                   if packet_genome is not None else ""))
    # the FLAC written while the rendition's loudness, range and true peak are measured (threads.in_order)
    heard = pcm / 32768.0
    measured = dict(threads.in_order([
        ("flac", lambda: master.write_flac(out, pcm, synth.SR, tags=tags)),
        ("lufs", lambda: round(master.loudness(heard, synth.SR), 2)),
        ("lu", lambda: round(master.loudness_range(heard, synth.SR), 2)),
        ("dbtp", lambda: round(master.true_peak(heard), 2)),
    ]))

    record = {
        "id": master.pcm_sha256(pcm),
        "title": genome.title,
        **lineage,
        "rendered_at": drift.to_dict()["at"] if drift is not None else None,
        "params": params.to_dict(),
        "lyrics": lyrics.to_dict() if lyrics else None,  # the words drawn from the bank; None: the seed's own
        "singer": asdict(singer),
        "lineage_singers": lineage_singers,  # who sings in the choir: the earlier versions, the parent's first
        "voice": voice.to_dict() if voice is not None else None,
        "drift": drift.to_dict() if drift is not None else None,
        "phrasing": {k: v for k, v in phrasing_json.items() if k not in ("phrases", "fields")} if phrasing_json else None,
        "choir_phrasings": [{k: v for k, v in d.items() if k not in ("phrases", "fields")} for d in choir_json] or None,
        "performance": {"lead": phrasing_mod.to_json(phrasing) if phrasing is not None else None,
                        "choir": [phrasing_mod.to_json(ph) for ph in choir]},
        "mix": mixing.to_dict(),
        "loudness_lufs": measured["lufs"],
        "loudness_range_lu": measured["lu"],
        "true_peak_dbtp": measured["dbtp"],
        "peak_dbfs": round(20 * np.log10(np.max(np.abs(pcm)) / 32768.0), 2),
        "duration": round(len(pcm) / synth.SR, 3),
        "program_version": __version__,
    }
    story = evolution(genome, params, _parent(parent, genome) if parent else None, lyrics, changes)
    if story is not None:  # the tune's variants and what changed from the parent (docs/EVOLUTION.md)
        record["evolution"] = story
    if chosen_by_you:  # a person's choices, marked as theirs (never who they are)
        record["chosen_by_you"] = chosen_by_you
    if packet_genome is not None:  # one file: the record and the words travel inside it
        sung = (lyrics.sheet(genome.title) if lyrics and not has_lines(params)
                else pack_mod.words_as_sung(score.to_dict(), genome.title))
        pack_mod.pack(out, record, packet_genome, lyrics=sung)
    else:
        out.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")
        out.with_suffix(".score.json").write_text(json.dumps(score.to_dict()) + "\n")
        if lyrics or has_lines(params):
            sung = (lyrics.sheet(genome.title) if lyrics and not has_lines(params)
                    else pack_mod.words_as_sung(score.to_dict(), genome.title))
            out.with_suffix(".txt").write_text(sung)

    if stems:
        import soundfile as sf

        for name, stem in synth.render_stems(score, seed=params.seed, voice=singer, ancestors=ancestors).items():
            sf.write(str(out.with_name(f"{out.stem}.{name}.wav")), stem, synth.SR, subtype="FLOAT")
    if midi_file:  # every part, the words and the chords, for a musician's own tools (songbird/midi.py)
        from . import midi

        data, lead_in = midi.from_score(genome, params, score)
        out.with_suffix(".mid").write_bytes(data)
        print(f"{out.with_suffix('.mid')}  bar 1 begins {-lead_in:.3f}s before the audio's first sample")

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


def parent_of(record: dict) -> dict | None:
    """As much of a rendition's parent as its record keeps: its place in the lineage, and the earlier
    versions' singers who sang its choir (the parent's first), so rendering it again sings the same."""
    if not record.get("parent_id"):
        return None
    sang = list(record.get("lineage_singers") or [])
    return {"id": record["parent_id"], "generation": int(record.get("generation", 1)) - 1,
            "ancestry": list(record.get("ancestry") or [])[:-1],
            "singer": sang[0].get("singer") if sang else None, "lineage_singers": sang[1:]}


def recording_of(path: str | Path) -> tuple[bytes | None, bool]:
    """The audio a record describes, if it is at hand: a packet's own, or the FLAC a render wrote beside its
    .json record (render_one writes NAME.flac and NAME.json); and whether it came from beside the record."""
    path = Path(path)
    if pack_mod.read_manifest(path) is not None:
        return pack_mod.audio_bytes(path), False
    beside = path.with_suffix(".flac")
    return (pack_mod.audio_bytes(beside), True) if beside.is_file() and beside != path else (None, False)


def replayed(record: dict, made: dict, out: Path, recorded: bytes | None, beside: bool) -> str:
    """How a replay (its record made, its audio at out) compares with the rendition the record describes, in
    pack.compare_samples' words: by their samples when the recording is at hand, else by their ids. A FLAC
    beside the record that holds other samples (rendered again since) is no recording of it."""
    if record.get("id") and made["id"] == record["id"]:
        return "matches"
    if recorded is not None:
        heard = pack_mod.samples(recorded)
        if not (beside and record.get("id") and master.pcm_sha256(heard) != record["id"]):
            return pack_mod.compare_samples(pack_mod.samples(pack_mod.audio_bytes(out)), heard, synth.SR)
    if not record.get("id"):
        return "can't say: the record names no samples to compare with"
    return (f"differs from the record's id ({made['id'][:12]}, the record {record['id'][:12]}); no recording "
            f"of it is at hand to compare the samples with")


def credited(gestures: dict | None, about: dict | None) -> dict | None:
    """A performance's gestures as a record carries them, with what its record says of them beside (render_one
    keeps all but the gestures as the record's phrasing); the gestures alone where it says nothing."""
    if not gestures or not isinstance(about, dict):
        return gestures
    return {**{k: v for k, v in about.items() if k not in ("phrases", "fields")}, **gestures}


def replay_command(args: argparse.Namespace, genome) -> int:
    """A rendition rendered again exactly as its record says: its parameters, the words it recorded (not
    drawn again), its machine and moment, and the small performance it carries. Then it says how the replay
    compares with the recording (replayed): 0 if it matches, sample for sample or within a few steps, 1 if not."""
    from .arrange import Lyrics

    record = pack_mod.read_record(args.replay)
    recorded, beside = recording_of(args.replay)  # read now: the replay may be written over it
    params = Params.from_dict(record["params"])
    # The final singer and mix include any overrides used for the original.
    # They can differ from the machine's choices stored in params.
    params = replace(params, singer=record.get("singer") or params.singer, mix=record.get("mix") or params.mix)
    lyrics = Lyrics.from_dict(record["lyrics"]) if record.get("lyrics") else None
    voice = harvest.Voice.from_dict(record["voice"]) if record.get("voice") else None
    drift = drift_mod.Drift.from_dict(record["drift"]) if record.get("drift") else None
    phrasing_json, choir_json = phrasing_mod.inherited(genome.source, record)
    if isinstance(record.get("performance"), dict):  # the gestures it carries, with what the record says of them
        # (where they came from, "79 sung takes by 12 singers"), so the replay's record says it again
        phrasing_json = credited(phrasing_json, record.get("phrasing"))
        about = list(record.get("choir_phrasings") or [])
        choir_json = [credited(c, about[i] if i < len(about) else None) for i, c in enumerate(choir_json)]
    if args.phrasing:
        phrasing_json = json.loads(Path(args.phrasing).read_text())
    if record.get("phrasing") and "performance" not in record and not args.phrasing:
        print("songbird: this rendition was sung with a person's phrasing; give it with --phrasing to hear it "
              "the same", file=sys.stderr)
    if args.choir_phrasing:
        choir_json = [json.loads(Path(f).read_text()) for f in args.choir_phrasing]
    parent = parent_of(record)
    out = Path(args.out or Path("renders") / (Path(args.genome).stem + ".replay.flac"))
    made = render_one(genome, params, out, voice=voice, drift=drift, lyrics=lyrics, phrasing_json=phrasing_json,
                      choir_json=choir_json, singer_overrides=args.voice, stems=args.stems, midi_file=args.midi,
                      mix_overrides=args.mix, parent=parent, packet_genome=args.genome if args.pack else None,
                      chosen_by_you=record.get("chosen_by_you"))
    said = replayed(record, made, out, recorded, beside)
    print(f"replay: {said}")
    return 1 if said.startswith("differs") else 0


def render_command(args: argparse.Namespace) -> int:
    genome = genome_mod.load(args.genome)
    if args.replay:
        return replay_command(args, genome)
    edits = None
    if args.edits:  # a person's choices: an edits file, or a record's marks
        from . import edits as edits_mod

        edits, problems = edits_mod.check(genome, edits_mod.from_record(json.loads(Path(args.edits).read_text())))
        if edits.pop("phrasing", None):
            print("songbird: a phrasing is given with --phrasing", file=sys.stderr)
        if "date" in edits and not args.date:
            args.date = edits["date"]
        elif "date" in edits:
            edits.pop("date")  # --date given: that day, not the file's
        for problem in problems:
            print(f"songbird: can't keep {problem['path']}: {problem['why']}", file=sys.stderr)
    voice, drift = _machine(args)
    try:
        parent = _parent_record(args.parent)
    except (ValueError, OSError) as e:
        print(f"songbird: can't sing from that parent: {e}", file=sys.stderr)
        return 2
    changes: list = []
    parent_params = _parent(parent, genome) if parent else None
    chosen = resolved = None
    if edits:
        if args.lyrics_seed is not None or (args.form and any(p.startswith(("form.", "words.")) for p in edits)):
            print("songbird: these edits choose the shape or the words; leave out --form and --lyrics-seed",
                  file=sys.stderr)
            return 2
        resolved = edits_mod.resolve(genome, parent_params, voice, drift, edits, seed=args.seed,
                                     day_chosen="date" in edits)
        for problem in resolved.problems:
            print(f"songbird: can't keep {problem['path']}: {problem['why']}", file=sys.stderr)
        params, chosen = resolved.params, resolved.marks or None
        if args.form:
            params = replace(params, form=tuple(args.form))
    else:
        params = choose_params(genome, parent_params, voice, drift, seed=args.seed, log=changes,
                               form=tuple(args.form) if args.form else None, style=args.style,
                               arrange=_arrangement(args.arrange))
    if args.choir is not None:
        params = replace(params, choir=args.choir)
    # A new contribution replaces the inherited delivery; otherwise it keeps
    # travelling even when the original recordings are long gone.
    phrasing_json, choir_json = phrasing_mod.inherited(genome.source, parent)
    if args.phrasing:
        phrasing_json = json.loads(Path(args.phrasing).read_text())
    if args.choir_phrasing:
        choir_json = [json.loads(Path(f).read_text()) for f in args.choir_phrasing]
    if args.choir_phrasing and args.choir is None:
        params = replace(params, choir=len(choir_json))
    sung_by_a_machine = voice is not None or drift is not None
    chose_words = resolved is not None and not args.form and any(p.startswith("words.") for p in edits)
    try:
        lyrics = resolved.lyrics if chose_words else \
            words(genome, params, args.lyrics_seed, sung_by_a_machine=sung_by_a_machine, voice=voice, drift=drift)
    except (ArrangeError, ValueError) as e:
        print(f"songbird: can't draw words for that form: {e}", file=sys.stderr)
        return 2
    if sung_by_a_machine and lyrics is not None and genome.source.get("bank"):
        if args.lyrics_seed is not None:  # drawn afresh by hand: the lineage holds what was sung, not what was chosen
            params = replace(params, words=hold(genome, lyrics))
            changes = [c for c in changes if c.get("what") != "words"] + [
                {"what": "words", "change": "drawn",
                 "why": f"drawn afresh from the bank with --lyrics-seed {args.lyrics_seed}, not handed down"}]
        elif chose_words:  # a person chose words: the lineage holds what was sung, their choices among it
            params = replace(params, words=hold(genome, lyrics))
        else:
            params = replace(params, words=evolve.fitted(genome, params, voice, drift))
    out = Path(args.out or Path("renders") / (Path(args.genome).stem + ".flac"))
    render_one(genome, params, out, voice=voice, drift=drift, lyrics=lyrics, phrasing_json=phrasing_json,
               choir_json=choir_json, singer_overrides=args.voice, stems=args.stems, midi_file=args.midi, mix_overrides=args.mix,
               parent=parent, packet_genome=args.genome if args.pack else None,
               changes=changes if sung_by_a_machine else None, chosen_by_you=chosen)
    return 0


# ---------------------------------------------------------------- the packet

def budget_command(args: argparse.Namespace) -> int:
    try:
        report = pack_mod.budget()
    except ValueError as e:
        print(f"songbird: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Program and model: {report['program_bytes'] / 2**20:.2f} MiB; the goal is {report['goal_bytes'] / 2**20:g} MiB"
              + ("" if report["headroom_bytes"] >= 0 else " (past it: pack warns)"))
        print(f"  model {report['model_bytes'] / 2**20:.2f} MiB; source and assets {report['source_bytes'] / 2**20:.2f} MiB; "
              f"room {report['headroom_bytes'] / 2**20:.2f} MiB")
        print("Before compression. Audio and installed runtime dependencies are separate; packing also checks rendition data.")
    return 0


def pack_command(args: argparse.Namespace) -> int:
    flac = Path(args.flac)
    record_path = Path(args.record) if args.record else flac.with_suffix(".json")
    inside = pack_mod.read_manifest(flac)  # a packet already: pack it again with the program running now
    if record_path.exists():
        record = json.loads(record_path.read_text())
    elif inside is not None:
        record = inside
    else:
        print(f"songbird: no render record at {record_path} (--record)", file=sys.stderr)
        return 2
    if args.parent:
        try:
            record = {**record, **pack_mod.lineage(pack_mod.read_record(args.parent))}
        except (ValueError, OSError) as e:
            print(f"songbird: {e}", file=sys.stderr)
            return 2
    genome_path = Path(args.genome) if args.genome else None
    if genome_path is None and inside is not None:  # the genome the packet carries
        import tempfile

        genome_path = Path(tempfile.mkdtemp()) / "genome.json"
        genome_path.write_text(pack_mod.read_member(flac, "genome.json") or "")
    if genome_path is None:  # the song whose title the record carries
        songs = Path(__file__).resolve().parents[1] / "songs"
        genome_path = next((g for g in sorted(songs.glob("*.json"))
                            if json.loads(g.read_text()).get("title") == record.get("title")), None)
        if genome_path is None:
            print(f"songbird: which genome sang {record.get('title')!r}? (--genome)", file=sys.stderr)
            return 2
    sheet, score = flac.with_suffix(".txt"), flac.with_suffix(".score.json")
    lyrics = sheet.read_text() if sheet.exists() else \
        pack_mod.words_as_sung(json.loads(score.read_text()), record.get("title")) if score.exists() else \
        pack_mod.read_member(flac, "lyrics.txt")
    out = pack_mod.pack(flac, record, genome_path, lyrics=lyrics, out=args.out)
    print(f"{out}  carries the program ({out.stat().st_size / 2**20:.1f} MB in all)")
    return 0


def unpack_command(args: argparse.Namespace) -> int:
    to = Path(args.to) if args.to else Path(args.flac).with_name(Path(args.flac).stem + "-unpacked")
    try:
        pack_mod.unpack(args.flac, to)
    except (ValueError, OSError) as e:
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
    parent_record = _parent_record(args.parent)
    parent = _parent(parent_record, genome)
    start = drift_mod.parse(args.start) if args.start else drift_mod.parse(drift_mod.when(drift_mod.now()).date().isoformat())
    label = args.machine.split(":", 1)[-1] if args.machine.startswith("fictional:") else Path(args.machine).stem
    print(f"{genome.title}: machine {args.machine} (voice {voice.hash}), {args.days} days from "
          f"{us_date(drift_mod.when(start).date())}, every {args.step:g}")
    print(f"form: {', '.join(f'{v}={k}' for k, v in FORM_LETTERS.items())}\n")
    head = f"{'date':10s}  {'key':3s} {'mode':10s} {'bpm':>5s}  {'form':16s} {'band':14s} {'dens':>4s} {'brt':>4s} " \
           f"{'harp':16s} {'hum':>5s} {'rit':>4s} {'breath':>6s} {'vib':>4s}  {'mood (p l d t)':19s} {'era':>5s} " \
           f"{'var':>3s}  verses"
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
              f"{p.leanings.get('era_bias', 0.0):5.2f} {len(p.variants):3d}  "
              f"{' '.join(v['id'] for v in p.words.get('verses', [])) or '-'}")
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
          f"harp's picking {changes(lambda p: p.accomp)}; tempo {min(tempos):.1f}-{max(tempos):.1f}; "
          f"the tune's variants {changes(lambda p: p.variants)} (at most {max(len(p.variants) for p in rows)}), "
          f"the words {changes(lambda p: json.dumps(p.words, sort_keys=True))}")

    if args.render:
        out_dir = Path(args.render)
        for offset, name in ((0, "day 0"), (1, "a day on"), (7, "a week on"), (30, "a month on"), (365, "a year on")):
            t = start + offset
            d = drift_mod.drift(t, voice.hash)
            log: list = []
            p = choose_params(genome, parent, voice, d, log=log)
            day = (drift_mod.when(start) + timedelta(days=offset)).date().isoformat()
            print(f"{name}: ", end="")
            phrasing_json, choir_json = phrasing_mod.inherited(genome.source, parent_record)
            render_one(genome, p, out_dir / f"{Path(args.genome).stem}.{label}.{day}.flac", voice=voice, drift=d,
                       lyrics=words(genome, p, sung_by_a_machine=True), phrasing_json=phrasing_json, choir_json=choir_json,
                       parent=parent_record, changes=log)
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
                        help="inherit from a parent rendition: its FLAC (carrying its packet, or with its record "
                             "beside it) or its record (.json)")
    render.add_argument("--pack", action="store_true",
                        help="attach the packet: the FLAC carries the program, the genome, its record and its words "
                             "(and nothing is written beside it)")
    render.add_argument("--form", nargs="+", help="override the section order, e.g. intro verse refrain")
    render.add_argument("--lyrics-seed", type=int, metavar="N",
                        help="draw the words from the song's bank with this seed, and write their lyric sheet "
                             "beside the render (default: when a machine or a date sings, with the rendition's "
                             "own seed; otherwise the seed's own words)")
    render.add_argument("--stems", action="store_true", help="also write each part, dry, as WAV")
    render.add_argument("--midi", action="store_true",
                        help="also write every part, the words and the chords as a MIDI file (.mid) beside it")
    render.add_argument("--voice", nargs="*", default=[], metavar="FIELD=VALUE",
                        help="override the singer, e.g. --voice tract=1.0 shift=-12 rd=1.3")
    render.add_argument("--mix", nargs="*", default=[], metavar="FIELD=VALUE",
                        help="change the mix (synth/mixing.py MixParams), e.g. --mix rt60=2.2 wear=0.5 "
                             "tone=1,1,1,0.8,0.6 balance=fiddle:2")
    render.add_argument("--style", metavar="NAME",
                        help="play it in this style (songbird/style.py STYLES: ballad, stringband, country, gospel, "
                             "shanty, songwriter, chamber, lullaby, ambient, synthfolk, lofi, indie, blues; beside the ring, house, dub, acappella, "
                             "jig and hymn) instead of "
                             "the one the machine and its parent lead to")
    render.add_argument("--arrange", nargs="*", default=[], metavar="FIELD=VALUE",
                        help="set the arrangement's options (songbird/style.py Style), e.g. --arrange feel=waltz "
                             "lift=true ending=cold backing=gang")
    render.add_argument("--choir", type=int, metavar="N",
                        help="lineage voices joining in harmony where the song has a choir (stand-ins for now)")
    render.add_argument("--phrasing", metavar="FILE",
                        help="sing with a person's phrasing, from tools/phrasing.py (default: inherited from the "
                             "parent, or the seed's own)")
    render.add_argument("--choir-phrasing", nargs="+", default=[], metavar="FILE",
                        help="a phrasing for each choir voice, in order (sets --choir to their number unless given)")
    render.add_argument("--edits", metavar="FILE",
                        help="a person's choices on top of the program's (songbird.edits): an edits file, or a "
                             "record whose marked choices are made again")
    render.add_argument("--replay", metavar="RECORD",
                        help="render a rendition again exactly as its record says (its words as recorded)")
    render.set_defaults(run=render_command)

    from .studio import add_arguments as studio_arguments, run as studio_run

    studio = commands.add_parser("studio", help="see how your version of the song is made, change it if you "
                                                "like, and export it, in a page on this computer")
    studio_arguments(studio)
    studio.set_defaults(run=studio_run)

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
    year.add_argument("--parent", metavar="FILE",
                      help="inherit from a parent rendition: its FLAC (carrying its packet, or with its record beside it) "
                           "or its record (.json)")
    year.add_argument("--render", metavar="DIR",
                      help="also render the first day, a day, a week, a month and a year on into DIR")
    year.set_defaults(run=year_command)

    pack_parser = commands.add_parser("pack", help="attach the packet to a rendered FLAC: the program, genome, record, words")
    pack_parser.add_argument("flac", help="a rendered FLAC, with its record (.json) beside it")
    pack_parser.add_argument("--record", metavar="FILE", help="its render record (default: beside the FLAC)")
    pack_parser.add_argument("--genome", metavar="FILE", help="the genome it sang (default: the song with its title)")
    pack_parser.add_argument("--out", metavar="FILE", help="write the packet here (default: attach it in place)")
    pack_parser.add_argument("--parent", metavar="FILE",
                             help="the rendition it was sung from (packet or record), if its record doesn't say")
    pack_parser.set_defaults(run=pack_command)

    budget_parser = commands.add_parser("budget", help="the portable program and model's size against the 8 MiB goal")
    budget_parser.add_argument("--json", action="store_true", help="print exact byte counts for build checks")
    budget_parser.set_defaults(run=budget_command)

    unpack_parser = commands.add_parser("unpack", help="unpack a rendition's packet into a folder")
    unpack_parser.add_argument("flac", help="a FLAC carrying its packet")
    unpack_parser.add_argument("--to", metavar="DIR", help="the folder (default: beside the FLAC)")
    unpack_parser.set_defaults(run=unpack_command)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
