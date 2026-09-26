"""Edits: a person's choices, on top of what the program chose.

An edit is one entry in a flat map from a path to a value (docs/STUDIO.md):
what someone changed about their version of the song, in the studio or in a
file given to `songbird render --edits`. The program chooses as it always
does (realize.choose_params, arrange); each edit then takes the place of the
choice it names, checked against the same bounds and rules the program
keeps. An edit that can't be kept is left out and said why, never bent.

    date                 "YYYY-MM-DD": the day the song is sung (noon UTC, as --date has it)
    roll                 chance drawn again: the rendition's k-th draw, which still follows the day
    tonic, mode, tempo   the key's note (MIDI), its mode, beats a minute
    form.verses          how many verses; form.pairs, form.intro, form.turn, form.break,
                         form.tag, form.outro, form.bridge2: each part of the shape on or off
    band.pattern, band.lead, band.density, band.brightness, band.<instrument> (0: it sits out)
    mix.space, mix.width, mix.forward, mix.intimacy
    variants.<name>      a melody variant, once a rendition carries them (Params.variants)
    words.verse.<i>      {"id": verse, "slots": {slot: words}}, or just the verse: the i-th verse (from 0)
    words.refrain.<i>    a couplet for the i-th refrain (never the last's: it always sings the canon)
    words.refrain        {slot: words}: the refrain's once-a-song words
    words.bridge         {slot: words}: the bridge's once-a-song words
    words.bridge2        the second bridge's stanza
    words.tag            the tag's syllable
    phrasing             whose way the song is sung: a phrasing made on this computer

The edits go in inside the program's table (choose_params(overrides=...)),
so a decision that reads one reads the person's: a mode chosen minor leans
the words darker, as the machine's own minor would. That is the one knock-on
so far; any added later should be listed here. Each part of the shape is its
own edit, so "no intro" holds while the day moves the rest of the shape.

A rendition's record marks each edit that took effect with what the program
had chosen (marks()): the choices are recorded as a person's, never whose.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, fields, replace
from datetime import date

from . import arrange as arrange_mod
from . import variation
from .band import INSTRUMENTS, LEADS, PATTERNS
from .genome import Genome
from .synth.mixing import RANGES, MixParams

MIX = ("space", "width", "forward", "intimacy")
SHAPE = ("verses", "pairs", "intro", "turn", "break", "tag", "outro", "bridge2")
WORDS = re.compile(r"words\.(verse|refrain)\.(\d+)|words\.(refrain|bridge|bridge2|tag)")


def Problem(path: str, why: str) -> dict:
    """An edit that couldn't be kept, and why, in one plain sentence."""
    return {"path": path, "why": why}


# ---------------------------------------------------------------- bounds


def song_params(genome: Genome):
    from .realize import Params

    return Params.from_dict(genome.seed_params)


def _knob(path: str):
    return next(k for k in variation.KNOBS if k.path == path)


def bounds(genome: Genome) -> dict:
    """What a person may choose, path by path: the tempo and key as far as the program's table lets any
    machine go (0.75 to 1.3 times the song's tempo, five semitones either way), the modes the song's chords
    keep their shape in, and the band's and the mix's designed ranges (wider than a machine's own)."""
    song = song_params(genome)
    tempo = _knob("tempo").bounds(song.tempo)
    tonic = _knob("tonic").bounds(song.tonic)
    out = {
        "tempo": {"min": round(tempo[0], 1), "max": round(tempo[1], 1), "step": 0.5, "song": song.tempo},
        "tonic": {"min": int(tonic[0]), "max": int(tonic[1]), "song": song.tonic},
        "mode": {"options": list(variation.allowed_modes(genome, song.mode)), "song": song.mode},
        "band.pattern": {"options": list(PATTERNS)},
        "band.lead": {"options": list(LEADS)},
        "band.density": {"min": 0.0, "max": 1.0, "step": 0.01},
        "band.brightness": {"min": 0.0, "max": 1.0, "step": 0.01},
        "band.players": {"options": list(INSTRUMENTS)},
        "form.verses": {"options": list(verse_counts(genome))},
    }
    for name in MIX:
        lo, hi = RANGES[name]
        out[f"mix.{name}"] = {"min": lo, "max": hi, "step": 0.1 if name == "forward" else 0.01,
                              "song": getattr(MixParams(), name)}
    return out


def verse_counts(genome: Genome) -> tuple[int, ...]:
    """How many verses a shape may have: the template's range, and what the bank can fill."""
    lo, hi = variation.verse_range(genome)
    counts = tuple(range(lo, hi + 1))
    if genome.source.get("bank"):
        counts = tuple(n for n in counts if n in arrange_mod.forms(genome)["verse"])
    return counts


# ---------------------------------------------------------------- the shape


def optional(genome: Genome) -> tuple[str, ...]:
    """The shape's parts that can be on or off, in the template's order (pairs and bridge2 where they apply)."""
    names = []
    for it in variation.items(genome):
        for name, flag in it.tokens[1:] if it.repeat else it.tokens:
            if flag == "?" and name not in names:
                names.append(name)
    if any(it.repeat and len(it.tokens) > 1 for it in variation.items(genome)):
        names.insert(0, "pairs")
    if variation.extra_bridge(genome):
        names.append("bridge2")
    return tuple(names)


def shape(genome: Genome, form) -> dict | None:
    """A form read as its parts: {"verses": n, "pairs": bool, "intro": bool, ...}; None for a form that
    doesn't follow the song's template (one set by hand)."""
    parsed = variation.parse_form(genome, form)
    if parsed is None:
        return None
    out: dict = {"verses": sum(1 for n in form if variation.is_verse(genome, n))}
    for name in optional(genome):
        if name == "pairs":
            out["pairs"] = any(chunk.split(",").count(it.tokens[0][0]) > 1
                               for it in variation.items(genome) if it.repeat and len(it.tokens) > 1
                               for chunk in parsed.get(f"t{it.index}", "").split(f"{it.tokens[1][0]},"))
        else:
            out[name] = name in form
    return out


def build(genome: Genome, parts: dict) -> tuple[str, ...]:
    """The form with these parts, every optional part on or off everywhere it can come."""
    present = {}
    for it in variation.items(genome):
        for name, flag in it.tokens[1:] if it.repeat else it.tokens:
            if flag == "?":
                for r in range(8):
                    present[(it.index, name, r)] = bool(parts.get(name))
    return variation.build(genome, int(parts["verses"]), present, bool(parts.get("bridge2")), bool(parts.get("pairs")))


def form_problem(genome: Genome, form) -> str | None:
    """Why a shape can't be sung: outside the song's template or verse counts, or words the bank can't fill."""
    if not variation.fits(genome, form):
        lo, hi = variation.verse_range(genome)
        verses = sum(1 for n in form if variation.is_verse(genome, n))
        if not lo <= verses <= hi:
            return f"the song sings {lo} to {hi} verses, not {verses}"
        return "the song's shape doesn't allow that"
    if genome.source.get("bank"):
        return arrange_mod.problem(genome, form)
    return None


def reshape(genome: Genome, form, changes: dict) -> tuple[tuple[str, ...], list[dict], list[str]]:
    """A form with some of its parts changed, one at a time in SHAPE's order, each kept only if the result
    can be sung: the form, why any couldn't be, and the paths that took effect."""
    parts = shape(genome, form)
    if parts is None:
        return tuple(form), [Problem(f"form.{k}", "this version's shape was set by hand, outside the song's "
                                                  "template, so its parts can't be changed one by one")
                             for k in changes], []
    current, problems, applied = tuple(form), [], []
    for name in SHAPE:
        if name not in changes:
            continue
        if name not in parts:
            problems.append(Problem(f"form.{name}", f"this song has no {name} to change"))
            continue
        trial = dict(parts, **{name: changes[name]})
        candidate = build(genome, trial)
        why = form_problem(genome, candidate)
        if why:
            problems.append(Problem(f"form.{name}", why))
            continue
        parts, current = trial, candidate
        applied.append(f"form.{name}")
    return current, problems, applied


def shapes(genome: Genome, form) -> list[dict]:
    """Every change to one part of a shape, each with whether it can be sung and why not (for the page)."""
    parts = shape(genome, form)
    if parts is None:
        return []
    out = []
    lo, hi = variation.verse_range(genome)
    for name in ("verses", *optional(genome)):
        for value in (list(range(lo, hi + 1)) if name == "verses" else [True, False]):
            if parts.get(name) == value:
                out.append({"part": name, "value": value, "allowed": True, "why": None, "sung": True})
                continue
            why = form_problem(genome, build(genome, dict(parts, **{name: value})))
            out.append({"part": name, "value": value, "allowed": why is None, "why": why, "sung": False})
    return out


# ---------------------------------------------------------------- checking values


def _number(value, lo: float, hi: float) -> float:
    x = float(value)
    if x != x:  # NaN
        raise ValueError("not a number")
    return min(hi, max(lo, x))


def check(genome: Genome, edits: dict, phrasings=()) -> tuple[dict, list[dict]]:
    """The edits that name a choice a person can make, their values cleaned (numbers held to their
    bounds), and why the others can't be made."""
    b = bounds(genome)
    clean: dict = {}
    problems: list[dict] = []
    for path, value in (edits or {}).items():
        try:
            if path == "date":
                clean[path] = date.fromisoformat(str(value)).isoformat()
            elif path == "roll":
                roll = int(value)
                if roll < 0 or roll >= 2**31:
                    raise ValueError
                if roll:
                    clean[path] = roll
            elif path == "tempo":
                clean[path] = round(_number(value, b["tempo"]["min"], b["tempo"]["max"]), 1)
            elif path == "tonic":
                clean[path] = int(_number(round(float(value)), b["tonic"]["min"], b["tonic"]["max"]))
            elif path == "mode":
                if value not in b["mode"]["options"]:
                    raise LookupError(f"the song's chords keep their shape only in {', '.join(b['mode']['options'])}")
                clean[path] = value
            elif path.startswith("form."):
                part = path[5:]
                if part == "verses":
                    counts = b["form.verses"]["options"]
                    if int(value) not in counts:
                        raise LookupError(f"the song sings {counts[0]} to {counts[-1]} verses, not {int(value)}")
                    clean[path] = int(value)
                elif part in SHAPE:
                    clean[path] = bool(value)
                else:
                    raise LookupError(f"the shape has no part called {part}")
            elif path in ("band.pattern", "band.lead"):
                options = b[path]["options"]
                if value not in options:
                    raise LookupError(f"the band's {path[5:]} is one of {', '.join(options)}")
                clean[path] = value
            elif path in ("band.density", "band.brightness"):
                clean[path] = round(_number(value, 0.0, 1.0), 2)
            elif path.startswith("band.") and path[5:] in INSTRUMENTS:
                clean[path] = round(_number(value, 0.0, 2.0), 2)
            elif path.startswith("mix.") and path[4:] in MIX:
                lo, hi = RANGES[path[4:]]
                clean[path] = round(_number(value, lo, hi), 2)
            elif path.startswith("variants."):  # a variant of the tune the lineage carries: kept (true) or dropped
                if not path[9:].isdigit():
                    raise LookupError("a variant is named by its place among the tune's variants")
                clean[path] = bool(value)
            elif path == "phrasing":
                if value and value not in phrasings:
                    raise LookupError("no such phrasing has been made on this computer")
                if value:
                    clean[path] = str(value)
            elif WORDS.fullmatch(path):
                clean[path] = value
            else:
                raise LookupError("there's no such choice")
        except LookupError as e:
            problems.append(Problem(path, str(e.args[0]) if e.args else "there's no such choice"))
        except (TypeError, ValueError):
            problems.append(Problem(path, f"{value!r} isn't a value this choice can take"))
    return clean, problems


# ---------------------------------------------------------------- into the program's table


def rolled(seed: int, roll: int) -> int:
    """Chance drawn again: the roll-th draw from a rendition's own seed, which follows the day."""
    if not roll:
        return seed
    return int.from_bytes(hashlib.sha256(f"songbird-roll|{seed}|{roll}".encode()).digest()[:4], "little") % 2**31


class Overrides:
    """A person's edits, ready for realize.choose_params(overrides=...): pin() puts them in place of the
    program's choices as the table makes them, finish() draws chance again if asked; afterwards `applied`
    lists the edits that took effect and `problems` why the others couldn't (words, the date and the
    phrasing act elsewhere: pins(), the drift's instant, the singer)."""

    def __init__(self, genome: Genome, edits: dict):
        self.genome = genome
        self.edits = dict(edits or {})
        self.applied: list[str] = []
        self.problems: list[dict] = []
        self._has_variants = None

    def pin(self, out: dict) -> None:
        """The edits, in the table's working dict of parameters. Idempotent: the table calls it after its
        knobs and after each of its decisions."""
        e, applied, problems = self.edits, [], []
        for key in ("tonic", "mode", "tempo"):
            if key in e:
                out[key] = e[key]
                applied.append(key)
        for head in ("band", "mix"):
            values = {p[len(head) + 1:]: v for p, v in e.items() if p.startswith(head + ".")}
            if values:
                held = out.get(head)
                held = held.to_dict() if hasattr(held, "to_dict") else dict(held or {})
                out[head] = {**held, **values}
                applied += [f"{head}.{k}" for k in values]
        variants = {p[9:]: v for p, v in e.items() if p.startswith("variants.")}
        if variants:
            from .realize import Params

            if "variants" in {f.name for f in fields(Params)}:
                held = list(out.get("variants") or ())  # the lineage's variants (songbird.variants), in order
                out["variants"] = [x for i, x in enumerate(held) if variants.get(str(i), True)]
                applied += [f"variants.{k}" for k in variants if k.isdigit() and int(k) < len(held)]
                problems += [Problem(f"variants.{k}", "this version's tune has no such variant")
                             for k in variants if not (k.isdigit() and int(k) < len(held))]
            else:
                problems += [Problem(f"variants.{k}", "this program has no melody variants yet") for k in variants]
        changes = {p[5:]: v for p, v in e.items() if p.startswith("form.")}
        if changes:
            form, trouble, done = reshape(self.genome, out["form"], changes)
            out["form"] = list(form)
            problems += trouble
            applied += done
        self.applied, self.problems = applied, problems

    def finish(self, params):
        """The parameters with chance drawn again, if a roll was asked for."""
        if self.edits.get("roll"):
            params = replace(params, seed=rolled(params.seed, self.edits["roll"]))
            self.applied = [*self.applied, "roll"]
        return params

    def params(self, params):
        """Edits on parameters the table didn't make (no machine, no day): the same edits, the same way."""
        from .realize import Params

        out = params.to_dict()
        self.pin(out)
        return self.finish(Params.from_dict(out))


def pins(genome: Genome, form, edits: dict) -> tuple[dict, list[dict], list[str]]:
    """The word edits as arrange keeps them (arrange.keep), for this form: the ones with a place in it,
    why the others have none, and the paths of the ones that have."""
    counts = {"verse": 0, "refrain": 0, "bridge": 0, "tag": 0}
    for name in form:
        block = genome.section(name).lyrics
        if block in counts:
            counts[block] += 1
    chosen: dict = {}
    problems: list[dict] = []
    wanted: list[str] = []
    for path, value in edits.items():
        match = WORDS.fullmatch(path)
        if not match:
            continue
        block, index, whole = match.group(1), match.group(2), match.group(3)
        if block == "verse":
            i = int(index)
            if i >= counts["verse"]:
                problems.append(Problem(path, f"this shape sings {counts['verse']} verses, so it has no verse {i + 1}"))
                continue
            chosen.setdefault("verses", {})[i] = value if isinstance(value, dict) else {"id": value}
        elif block == "refrain":
            i = int(index)
            if i >= counts["refrain"]:
                problems.append(Problem(path, f"this shape sings {counts['refrain']} refrains, so it has no refrain {i + 1}"))
                continue
            chosen.setdefault("couplets", {})[i] = value
        elif whole == "bridge2":
            if counts["bridge"] < 2:
                problems.append(Problem(path, "this shape sings the bridge once, so it has no second stanza"))
                continue
            chosen["bridge2"] = value
        elif whole == "tag":
            if not counts["tag"]:
                problems.append(Problem(path, "this shape has no tag"))
                continue
            chosen["tag"] = value
        else:  # words.refrain, words.bridge: the once-a-song words
            if not isinstance(value, dict):
                problems.append(Problem(path, "the once-a-song words are chosen slot by slot"))
                continue
            if not counts[whole]:
                problems.append(Problem(path, f"this shape has no {whole}"))
                continue
            chosen[whole] = dict(value)
        wanted.append(path)
    return chosen, problems, wanted


# ---------------------------------------------------------------- a rendition with a person's edits


@dataclass
class Resolved:
    """A rendition as the program chose it and as a person changed it."""

    generated: object  # Params: the program's own choices
    params: object  # Params: what will be sung
    generated_lyrics: object  # arrange.Lyrics, or None for the song's own words
    lyrics: object
    applied: list  # the edits that took effect
    problems: list  # the ones that didn't, and why
    marks: dict  # the record's chosen_by_you


def resolve(genome: Genome, parent, voice, drift, edits: dict, *, seed: int | None = None,
            phrasing_json: dict | None = None, trace: dict | None = None, day_chosen: bool = False) -> Resolved:
    """The rendition with a person's (checked) edits in place of the program's choices: the parameters
    through choose_params(overrides=...), then the words, each chosen word kept only if the song's rules can
    keep it beside the ones before it. trace receives the program's own arithmetic (variation.choose);
    day_chosen marks the date as the person's; phrasing_json is the phrasing the edits chose, if any."""
    from .cli import words
    from .realize import choose_params

    sung_by_a_machine = voice is not None or drift is not None
    if voice is None and drift is None:
        generated = choose_params(genome, parent, voice, drift, seed)
    else:
        generated = variation.choose(genome, parent, voice, drift, seed, trace=trace)
    applied: list[str] = ["date"] if day_chosen else []
    problems: list[dict] = []
    params = generated
    body = {k: v for k, v in edits.items() if k not in ("date", "phrasing") and not WORDS.fullmatch(k)}
    if body:
        overrides = Overrides(genome, body)
        params = choose_params(genome, parent, voice, drift, seed, overrides=overrides)
        applied += overrides.applied
        problems += overrides.problems
    generated_lyrics = words(genome, generated, sung_by_a_machine=sung_by_a_machine)
    lyrics = generated_lyrics
    if (params.form, params.seed, params.leanings) != (generated.form, generated.seed, generated.leanings):
        lyrics = words(genome, params, sung_by_a_machine=sung_by_a_machine)
    chosen, trouble, wanted = pins(genome, params.form, edits)
    problems += trouble
    if chosen and lyrics is not None:
        kept: list[str] = []
        for path in wanted:
            trial = pins(genome, params.form, {p: edits[p] for p in [*kept, path]})[0]
            try:
                attempt = arrange_mod.arrange(genome, params.form, params.seed, variation.leanings(params), trial)
            except arrange_mod.ArrangeError as e:
                problems.append(Problem(path, str(e)))
                continue
            kept.append(path)
            lyrics = attempt
        applied += kept
    elif chosen:
        problems += [Problem(p, "this song's words aren't drawn from a store of verses, so they can't be chosen")
                     for p in wanted]
    if "phrasing" in edits and phrasing_json is not None:
        applied.append("phrasing")
    marks_ = marks(genome, generated, generated_lyrics, lyrics, applied, edits, phrasing_json)
    return Resolved(generated, params, generated_lyrics, lyrics, applied, problems, marks_)


# ---------------------------------------------------------------- what the record keeps


def phrasing_mark(phrasing_json: dict) -> dict:
    """How a record marks a phrasing chosen by a person: whose it was never, only what it is and a
    fingerprint of it, so the same phrasing can be recognised (and given again to replay the rendition)."""
    everyone = "singers" in str(phrasing_json.get("source_detail", ""))
    digest = hashlib.sha256(json.dumps(phrasing_json, sort_keys=True).encode()).hexdigest()[:16]
    return {"value": "everyone's way" if everyone else "a person's way", "was": "the song's own way",
            "detail": phrasing_json.get("source_detail", ""), "digest": digest}


def marks(genome: Genome, generated, generated_lyrics, final_lyrics, applied: list[str], edits: dict,
          phrasing_json: dict | None = None) -> dict:
    """The record's block of a person's choices: for each edit that took effect, the value chosen and what
    the program had chosen ("was"). Replaying the values as edits (from_record) makes the same rendition
    from the same parent, machine and day."""
    out: dict = {}
    generated_shape = shape(genome, generated.form) or {}
    for path in applied:
        value, was = edits.get(path), None
        if path == "date":
            was = "the day it was made"
        elif path == "roll":
            was = 0
        elif path == "phrasing":
            out[path] = phrasing_mark(phrasing_json or {})
            continue
        elif path.startswith("form."):
            was = generated_shape.get(path[5:])
        elif path in ("words.refrain", "words.bridge"):  # once-a-song words: just the slots chosen
            sung = _sung(generated_lyrics, path) or {}
            was = {k: sung.get(k) for k in value}
        elif path.startswith("words."):
            was = _sung(generated_lyrics, path)
            value = _sung(final_lyrics, path) or value
        elif path.startswith("variants."):  # every variant the program chose was sung: dropping one changes it
            was = int(path[9:]) < len(getattr(generated, "variants", None) or ())
        else:
            was = variation.read(generated, path)
        out[path] = {"value": value, "was": was}
    return out


def _sung(lyrics, path: str):
    """What some words sing at a word edit's place: a verse's id and its slot words, a couplet's id..."""
    if lyrics is None:
        return None
    match = WORDS.fullmatch(path)
    block, index, whole = match.group(1), match.group(2), match.group(3)
    if block:
        sung = [s for s in lyrics.sections if s.block == block]
        i = int(index)
        if i >= len(sung):
            return None
        return {"id": sung[i].id, "slots": dict(sung[i].slots)} if block == "verse" else sung[i].id
    if whole == "tag":
        return lyrics.tag
    bridges = [s for s in lyrics.sections if s.block == "bridge"]
    if whole == "bridge2":
        return bridges[1].id if len(bridges) > 1 else None
    sections = bridges if whole == "bridge" else [s for s in lyrics.sections if s.block == whole]
    return dict(sections[0].slots) if sections else None


def from_record(data: dict) -> dict:
    """The edits in a file: an edits map as it is, or a record's marks (its chosen_by_you) as the edits that
    made them. A phrasing isn't among them: its file stays on the computer it was made on, and is given
    again with --phrasing."""
    if "chosen_by_you" not in data and "params" not in data:
        return dict(data)
    return {path: mark["value"] for path, mark in (data.get("chosen_by_you") or {}).items() if path != "phrasing"}


def keep_words(genome: Genome, lyrics) -> dict:
    """Edits that hold every section's words as they are now ("keep these words"): each verse and its
    slot words, every refrain's couplet but the last's, the once-a-song words, the second bridge, the tag."""
    rules = (genome.source.get("bank") or {}).get("rules")
    if lyrics is None or not rules:
        return {}
    out: dict = {}
    verses = [s for s in lyrics.sections if s.block == "verse"]
    refrains = [s for s in lyrics.sections if s.block == "refrain"]
    bridges = [s for s in lyrics.sections if s.block == "bridge"]
    for i, s in enumerate(verses):
        out[f"words.verse.{i}"] = {"id": s.id, "slots": dict(s.slots)}
    for i, s in enumerate(refrains[:-1]):
        out[f"words.refrain.{i}"] = s.id
    for block, sections in (("refrain", refrains), ("bridge", bridges)):
        once = {k: v for k, v in (sections[0].slots if sections else {}).items()
                if k in rules.get(block, {}).get("once_per_song", ())}
        if once:
            out[f"words.{block}"] = once
    if len(bridges) > 1:
        out["words.bridge2"] = bridges[1].id
    if lyrics.tag:
        out["words.tag"] = lyrics.tag
    return out
