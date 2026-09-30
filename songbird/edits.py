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
    mix.space, mix.width, mix.forward, mix.intimacy, mix.rt60 (s), mix.predelay (s)
    variants.<name>      a melody variant, once a rendition carries them (Params.variants)
    tune.<line>          a tune line's notes: [{degree, onset, duration}, ...] in beats (songbird.composition)
    chords.<line>        a tune line's chords: a list of chords a bar ([["I"], ["V/3", "vi"]]), each a function
                         of the key with a quality and a bass if named (theory.parse_symbol); null: the song's own
    tune.<section>:<n>.<i>, chords.<section>:<n>.<i>, and <section>:last.<i>
                         the same for one place of the form only: the i-th line of the n-th time that section comes
                         (the arrangement's id), or of the last time it comes; over the line's everywhere edit
                         (songbird.composition.form_phrases); null gives the place back to the line
    part.<player>.<section>:<n>.<line>
                         a person's own notes for a band player in one line of one section of the form, played in
                         or brought back from a MIDI file: [[onset, length, pitch, velocity], ...], whole numbers
                         (96ths of a beat from the line's first bar line; semitones from the key's note; 1..127),
                         in place of that player's own notes there; [] it rests; null: the program's own part
    words.verse.<i>      {"id": verse, "slots": {slot: words}}, or just the verse: the i-th verse (from 0)
    words.refrain.<i>    the i-th refrain's own words: {"id": couplet, "head": head, "slots": {slot: words}},
                         any of the three, or just a couplet (never the last's: it always sings the canon)
    words.refrain        {slot: words}: words for every refrain (while, then), unless one chooses its own
    words.bridge         {slot: words}: the bridge's once-a-song words
    words.bridge2        the second bridge's stanza
    words.tag            the tag's syllable
    phrasing             whose way the song is sung: a phrasing made on this computer
    arrange.<section>:<n>.<player>.level|pattern|from|fill, arrange.<section>:<n>.bars|sung|build
                         the arrangement taken over, section by section and player by player (songbird.takeover):
                         in or out and how hard, what it plays, the line it comes in at, a drum fill; a section's
                         length, played rather than sung, a build; null: the program's own
    style.intro, style.stops, style.alone, style.alone_with, style.bridge (beside style.entrances, style.breakdown...)
                         the style's options for the whole song: how it starts, which verse is in stop-time or
                         bare (and over whom), a half-time bridge

  Sound design (songbird.sound, docs/SOUND-DESIGN.md): what each player sounds like, never what it plays
    sound.<player>.patch, .cutoff, .resonance, .envelope   a synth's patch and its filter
    sound.<player>.kit, .kick, .snare, .hat                a drum player's kit and its pieces' character
    mix.<player>.pan, .send, .sidechain                    the player's channel: its place, its send to the room,
                                                           and ducking on the kick (or every beat)
    transition.<section-id>                                a riser, roll, sweep, impact or downlifter into it

The edits go in inside the program's table (choose_params(overrides=...)),
so a decision that reads one reads the person's: a mode chosen minor leans
the words darker, as the machine's own minor would. That is the one knock-on
so far; any added later should be listed here. A tune line's chords reach
everything that sounds from them (the band, the choir's harmony, the backing
voices: realize sings composition.harmonized), but not the choices the
program makes about the tune (its variants and the modes a machine may take
read the song's own chords). Each part of the shape is its
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
from . import takeover
from . import variation
from . import composition
from . import sound as sound_mod
from .band import INSTRUMENTS, LEADS, PATTERNS
from .genome import Genome
from .synth.mixing import RANGES, MixParams

MIX = ("space", "width", "forward", "intimacy", "rt60", "predelay")  # the room: how long it rings, how soon it answers
# The arrangement's options a person may set (songbird.style.Style), each as the style's own choices go
STYLE_OPTIONS = {"feel": ("straight", "swing", "shuffle", "twelve", "half", "double", "waltz", "six"),
                 "ending": ("ring", "rit", "cold", "amen", "repeat"), "backing": ("", "oohs", "echo", "thirds", "gang"),
                 "lift": bool, "entrances": bool, "breakdown": bool, "coda": ("", "quote"), "motif": ("", "bridge", "chance"),
                 # how it starts, which verse is in stop-time or bare and over whom, a half-time bridge (2026-09-29)
                 "intro": ("", "lead", "pad", "count", "voice", "quote"), "stops": int, "alone": int, "alone_with": str,
                 "bridge": ("", "half")}


def instruments() -> tuple[str, ...]:
    """Every instrument a band can have: the eight, and every other a style may bring."""
    from .synth.instruments import known

    return known()
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
    """What a person may choose, path by path: the tempo as far as any style lets a person take it (0.4 to 1.6
    times the song's; each style's own range is tempo_range's), the key as far as the program's table lets any
    machine go (five semitones either way), the modes the song's chords
    keep their shape in, and the band's and the mix's designed ranges (wider than a machine's own)."""
    song = song_params(genome)
    tempo = tuple(TEMPO_REACH[k] * song.tempo for k in (0, 1))  # the widest any style allows (tempo_range)
    tonic = _knob("tonic").bounds(song.tonic)
    out = {
        "tempo": {"min": round(tempo[0], 1), "max": round(tempo[1], 1), "step": 0.5, "song": song.tempo},
        "tonic": {"min": int(tonic[0]), "max": int(tonic[1]), "song": song.tonic},
        "mode": {"options": list(variation.allowed_modes(genome, song.mode)), "song": song.mode},
        "band.pattern": {"options": list(PATTERNS)},
        "band.lead": {"options": list(LEADS)},
        "band.density": {"min": 0.0, "max": 1.0, "step": 0.01},
        "band.brightness": {"min": 0.0, "max": 1.0, "step": 0.01},
        "band.arc": {"min": 0.0, "max": 1.0, "step": 0.01},
        "band.players": {"options": list(INSTRUMENTS)},
        "form.verses": {"options": list(verse_counts(genome))},
    }
    for name in MIX:
        lo, hi = RANGES[name]
        out[f"mix.{name}"] = {"min": lo, "max": hi, "step": {"forward": 0.1, "rt60": 0.05, "predelay": 0.001}.get(name, 0.01),
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
    played = 0  # notes played in so far (part.*), against composition.PART_NOTES
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
            elif path == "form.order":
                names = composition.order(genome, value)
                clean[path] = composition.section_ids(names) if names is not None else None
            elif path.startswith("tune."):
                clean[path] = composition.check_phrase(genome, path[5:], value)
            elif path.startswith("chords."):
                clean[path] = composition.check_chords(genome, path[7:], value)
            elif path.startswith("part."):
                notes = composition.check_part(genome, path, value)
                if notes and played + len(notes) > composition.PART_NOTES:
                    raise ValueError(f"a version takes at most {composition.PART_NOTES:,} notes played in")
                played += len(notes or ())
                clean[path] = notes
            elif path.startswith("lyrics."):
                clean[path] = composition.check_lyric(genome, path, value)
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
            elif path in ("band.density", "band.brightness", "band.arc"):
                clean[path] = round(_number(value, 0.0, 1.0), 2)
            elif path.startswith("band.") and path[5:] in instruments():
                clean[path] = round(_number(value, 0.0, 2.0), 2)
            elif path == "style.name":
                from .style import STYLES

                if value not in STYLES:
                    raise LookupError(f"the styles are {', '.join(sorted(STYLES))}")
                clean[path] = value
            elif path.startswith("arrange."):  # the arrangement taken over (songbird.takeover)
                clean[path] = takeover.check(genome, path, value)
            elif path.startswith("style.") and path[6:] in STYLE_OPTIONS:
                options = STYLE_OPTIONS[path[6:]]
                if options is bool:
                    clean[path] = bool(value)
                elif options is int:  # which verse (1 the first), 0 none
                    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 8:
                        raise LookupError(f"the {path[6:]} is a verse's number, 1 the first, or 0 for none")
                    clean[path] = value
                elif options is str:  # the one instrument under a bare verse, "" none
                    if value and value not in instruments():
                        raise LookupError(f"there's no player called {value}")
                    clean[path] = str(value or "")
                elif value not in options:
                    raise LookupError(f"the {path[6:]} is one of {', '.join(o or 'none' for o in options)}")
                else:
                    clean[path] = value
            elif sound_mod.owns(path):  # sound design: a player's sound, its channel, a transition (songbird.sound)
                clean[path] = sound_mod.check(genome, path, value)
            elif path.startswith("mix.") and path[4:] in MIX:
                lo, hi = RANGES[path[4:]]
                clean[path] = round(_number(value, lo, hi), 3 if path == "mix.predelay" else 2)
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
        except (TypeError, ValueError) as e:
            if path == "form.order" or path.startswith(("tune.", "chords.", "lyrics.", "part.", "arrange.")) \
                    or sound_mod.owns(path):
                problems.append(Problem(path, str(e)))
                continue
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
        self._lines_before: dict | None = None

    def pin(self, out: dict) -> None:
        """The edits, in the table's working dict of parameters. Idempotent: the table calls it after its
        knobs and after each of its decisions."""
        e, applied, problems = self.edits, [], []
        for key in ("tonic", "mode", "tempo"):
            if key in e:
                out[key] = e[key]
                applied.append(key)
        if "tempo" in e:  # held to the range of the style it is played in (tempo_range), said if it had to be
            lo, hi = tempo_range(self.genome, out.get("style"))
            out["tempo"] = round(min(hi, max(lo, float(e["tempo"]))), 1)
            if abs(out["tempo"] - float(e["tempo"])) > 0.05:
                problems.append(Problem("tempo", f"this style plays the song from {lo:g} to {hi:g} beats a minute, "
                                                 f"so {out['tempo']:g}"))
        for head in ("band", "mix"):  # (a player's channel, mix.<player>.*, is sound design's: below)
            values = {p[len(head) + 1:]: v for p, v in e.items() if p.startswith(head + ".") and not sound_mod.owns(p)}
            if values:
                held = out.get(head)
                held = held.to_dict() if hasattr(held, "to_dict") else dict(held or {})
                if head == "band":
                    # an instrument a style brought is in its lineup; one of the eight, where no style set one,
                    # is a field of its own; one the band hasn't got can't be sat out
                    lineup = dict(held.get("lineup") or {})
                    for name in [k for k in values if k in instruments()]:
                        gain = values.pop(name)
                        if lineup and name in lineup:
                            lineup[name] = gain
                        elif not lineup and name in INSTRUMENTS:
                            held[name] = gain
                        else:
                            problems.append(Problem(f"band.{name}", "this version's band has no such player"))
                            continue
                        applied.append(f"band.{name}")
                    if lineup:
                        held["lineup"] = lineup
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
        changes = {p[5:]: v for p, v in e.items() if p.startswith("form.") and p != "form.order"}
        if changes:
            form, trouble, done = reshape(self.genome, out["form"], changes)
            out["form"] = list(form)
            problems += trouble
            applied += done
        # Copy the nested data: the parent's choices are immutable and pin() is
        # called repeatedly while the machine makes the dependent decisions.
        held = dict(out.get("composition") or {})
        tune = dict(held.get("tune") or {})
        melisma = dict(held.get("melisma") or {})  # a line's melismas, beside its syllables' notes
        for path, value in e.items():
            if not path.startswith("tune."):
                continue
            try:
                notes = composition.check_phrase(self.genome, path[5:], value)
                key = composition.edit_key(self.genome, path[5:])  # a line, or one place of the form
                melisma.pop(key, None)  # a line changed or restored takes its melismas with it
                if notes is None:
                    tune.pop(key, None)
                else:
                    tune[key] = composition.pack_phrase(self.genome, notes)
                    turns = composition.pack_melisma(self.genome, notes)
                    if turns:
                        melisma[key] = turns
                applied.append(path)
            except (ValueError, TypeError) as ex:
                problems.append(Problem(path, str(ex)))
        for kind, now in (("tune", tune), ("melisma", melisma)):
            if now:
                held[kind] = now
            else:
                held.pop(kind, None)
        # a person's chords for a tune line, everywhere it is sung (composition.harmonized), or at one place of the
        # form (composition.form_phrases)
        chords = {k: [list(bar) for bar in v] for k, v in (held.get("chords") or {}).items()}
        for path, value in e.items():
            if not path.startswith("chords."):
                continue
            try:
                bars = composition.check_chords(self.genome, path[7:], value)
                key = composition.edit_key(self.genome, path[7:])
                if bars is None:
                    chords.pop(key, None)
                else:
                    chords[key] = bars
                applied.append(path)
            except (ValueError, TypeError) as ex:
                problems.append(Problem(path, str(ex)))
        if chords:
            held["chords"] = chords
        else:
            held.pop("chords", None)
        # a person's own notes for a player in one line of the form, played in (composition.performed)
        parts = {k: dict(v) for k, v in (held.get("parts") or {}).items()}
        for path, value in e.items():
            if not path.startswith("part."):
                continue
            try:
                notes = composition.check_part(self.genome, path, value)
                player, key = composition.part_key(path)
                lines = parts.setdefault(player, {})
                if notes is None:
                    lines.pop(key, None)
                else:
                    lines[key] = notes
                if not lines:
                    parts.pop(player, None)
                applied.append(path)
            except (ValueError, TypeError) as ex:
                problems.append(Problem(path, str(ex)))
        if parts:
            held["parts"] = parts
        else:
            held.pop("parts", None)
        # a person's own lines, each kept by the verse (or time round) it's written for (songbird.composition)
        lines = {k: dict(v) for k, v in held.get("lines", {}).items()}
        if self._lines_before is None:
            self._lines_before = {k: dict(v) for k, v in lines.items()}
        for path, value in e.items():
            if not path.startswith("lyrics."):
                continue
            try:
                text = composition.check_lyric(self.genome, path, value)
                key, line, _ = composition.lyric_target(self.genome, path)
                patch = lines.setdefault(key, {})
                if text is None:
                    patch.pop(str(line), None)
                else:
                    patch[str(line)] = text
                if not patch:
                    lines.pop(key, None)
                applied.append(path)
            except (ValueError, TypeError) as ex:
                problems.append(Problem(path, str(ex)))
        if lines:
            held["lines"] = lines
        else:
            held.pop("lines", None)
        if "form.order" in e:
            try:
                names = composition.order(self.genome, e["form.order"])
                if names is None:
                    # Released, the form is the one the table has without it: the parent's, which a machine
                    # singing this version then chooses from (variation.choose_form, after this first pin);
                    # with no parent, the song's own. Never the seed's in place of the machine's.
                    held.pop("order", None)
                else:
                    out["form"] = held["order"] = names
                applied.append("form.order")
            except (ValueError, TypeError) as ex:
                problems.append(Problem("form.order", str(ex)))
        held = self._arrange(out, held, applied, problems)  # the arrangement taken over (songbird.takeover)
        if held:
            out["composition"] = held
        else:
            out.pop("composition", None)
        # sound design (songbird.sound): against the band and the form this call leaves, into out["sound"]
        done, trouble = sound_mod.pin(self.genome, out, e)
        applied += done
        problems += trouble
        self.applied, self.problems = applied, problems

    def _arrange(self, out: dict, held: dict, applied: list, problems: list) -> dict:
        """The arrangement a person took over, in the composition's working copy (held): each choice checked and
        put in place, and a sung section's length that its lines can't have with the rest said and left as it
        was (songbird.takeover). The same dict when there are no such edits."""
        wanted = [p for p in self.edits if p.startswith("arrange.")]
        if not wanted:
            return held
        before = takeover.copy(held.get("arrange") or {})
        mine = takeover.copy(before)
        for path in wanted:
            try:
                takeover.put(mine, path, self.genome, takeover.check(self.genome, path, self.edits[path]))
                applied.append(path)
            except (ValueError, TypeError) as ex:
                problems.append(Problem(path, str(ex)))
        for path, why in takeover.shape_problems(self.genome, out["form"], mine).items():
            # a length asked for now goes back to what the version held; one held from before (a section sung
            # again now) goes back to the section's own
            was = before.get(path.split(".")[1], {}).get("bars") if path in self.edits else None
            takeover.put(mine, path, self.genome, was)
            if takeover.shape_problems(self.genome, out["form"], mine).get(path):
                takeover.put(mine, path, self.genome, None)
            if path in applied:
                applied.remove(path)
            problems.append(Problem(path, why))
        held = dict(held)
        if mine:
            held["arrange"] = mine
        else:
            held.pop("arrange", None)
        return held

    def style(self) -> tuple[str | None, dict]:
        """The style asked for and the arrangement's options, which go in by name (choose_params(style=,
        arrange=)), not pinned: a style brings its lineup, its tempo and its leans with it."""
        options = {p[6:]: v for p, v in self.edits.items() if p.startswith("style.") and p != "style.name"}
        return self.edits.get("style.name"), options

    def finish(self, params):
        """The parameters with chance drawn again, if a roll was asked for; and which style edits took
        effect (a feel the style can't play this song in doesn't)."""
        if self.edits.get("roll"):
            params = replace(params, seed=rolled(params.seed, self.edits["roll"]))
            self.applied = [*self.applied, "roll"]
        style = getattr(params, "style", None)
        for path, value in self.edits.items():
            if not path.startswith("style.") or style is None:
                continue
            field = path[6:]
            now = (style.name or "ballad") if field == "name" else getattr(style, field, None)
            verses = sum(1 for n in params.form if self.genome.section(n).lyrics == "verse")
            if field in ("stops", "alone") and value > verses:  # a verse this shape doesn't sing
                self.problems = [*self.problems, Problem(path, f"this shape sings {verses} verses")]
            elif now == value:
                self.applied = [*self.applied, path]
            else:
                self.problems = [*self.problems, Problem(path, f"the {style.name or 'ballad'} style can't play "
                                                               f"this song that way")]
        # a line for a time round the form hasn't got; which verses it sings is known with its words (unsung())
        return self.unsung(params, composition.lyric_keys(self.genome, params.form), verses=False)[0]

    def unsung(self, params, keys, verses: bool = True) -> tuple:
        """The parameters without the lines a person wrote for a section these keys (composition.lyric_keys)
        don't sing, each put back as it was and said why, and the paths left out. verses=False: the words
        aren't known yet, so a verse's lines stay until they are."""
        absent = []
        for path in self.applied:
            if not path.startswith("lyrics.") or self.edits.get(path) is None:
                continue
            key = composition.lyric_target(self.genome, path)[0]
            if not verses and self.genome.section(key.split(":", 1)[0]).lyrics == "verse":
                continue
            if key not in keys:
                absent.append(path)
        if not absent:
            return params, []
        held = dict(params.composition)
        lines = {k: dict(v) for k, v in held.get("lines", {}).items()}
        for path in absent:
            key, line, _ = composition.lyric_target(self.genome, path)
            previous = (self._lines_before or {}).get(key, {}).get(str(line))
            patch = lines.setdefault(key, {})
            if previous is None:
                patch.pop(str(line), None)
            else:
                patch[str(line)] = previous
            if not patch:
                lines.pop(key, None)
            self.applied = [p for p in self.applied if p != path]
            self.problems = [*self.problems, Problem(path, "this version doesn't sing that section; "
                                                           "choose a line shown in the song")]
        if lines:
            held["lines"] = lines
        else:
            held.pop("lines", None)
        return replace(params, composition=held), absent

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
            chosen.setdefault("refrains", {})[i] = dict(value) if isinstance(value, dict) else {"id": value}
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
        else:  # words.refrain, words.bridge: words for every refrain, the bridge's once-a-song words
            if not isinstance(value, dict):
                problems.append(Problem(path, "these words are chosen slot by slot"))
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
            phrasing_json: dict | None = None, trace: dict | None = None, day_chosen: bool = False,
            log: list | None = None) -> Resolved:
    """The rendition with a person's (checked) edits in place of the program's choices: the parameters
    through choose_params(overrides=...), a style by name; then the words: the ones the lineage holds
    (Params.words, songbird.evolve), with each word a person chose put in its place and nothing else moved,
    kept only if the song's rules can keep it beside the ones before it. The lineage then holds what is
    sung (as `songbird render` sets it). trace receives the program's own arithmetic and log what it changed
    in the tune and the words, with why (variation.choose); day_chosen marks the date as the person's;
    phrasing_json is the phrasing the edits chose, if any."""
    from . import evolve
    from .cli import words
    from .realize import choose_params

    sung_by_a_machine = voice is not None or drift is not None
    if voice is None and drift is None:
        generated = choose_params(genome, parent, voice, drift, seed, log=log)
    else:
        generated = variation.choose(genome, parent, voice, drift, seed, trace=trace, log=log)
    applied: list[str] = ["date"] if day_chosen else []
    problems: list[dict] = []
    params = generated
    body = {k: v for k, v in edits.items() if k not in ("date", "phrasing") and not WORDS.fullmatch(k)}
    if "style.feel" in body:  # a feel the style can't play this song in is said, not bent
        from .style import STYLES, feels_for, of

        name = body.get("style.name") or (generated.style.name or "ballad")
        feels = feels_for(genome, STYLES.get(name) or of(generated.style))
        if body["style.feel"] not in feels:
            problems.append(Problem("style.feel", f"that style plays this song {' or '.join(sorted(feels))}, "
                                                  f"not {body.pop('style.feel')}"))
    if body:
        overrides = Overrides(genome, body)
        params = choose_params(genome, parent, voice, drift, seed, overrides=overrides)
        applied += overrides.applied
        problems += overrides.problems
    generated_lyrics = words(genome, generated, sung_by_a_machine=sung_by_a_machine, voice=voice, drift=drift)
    lyrics = generated_lyrics
    if params is not generated:  # the person's choices may have moved the shape, and the words with it
        lyrics = words(genome, params, sung_by_a_machine=sung_by_a_machine, voice=voice, drift=drift)
    chosen, trouble, wanted = pins(genome, params.form, edits)
    problems += trouble
    kept: list[str] = []
    if chosen and lyrics is None and genome.source.get("bank"):
        # The seed normally sings without a drawn Lyrics record. A person
        # can still choose one of its bank's verses: start from the exact
        # seed words so that editing one verse doesn't redraw the others.
        generated_lyrics = arrange_mod.seed_lyrics(genome, generated.form)
        lyrics = arrange_mod.seed_lyrics(genome, params.form)
    if chosen and lyrics is not None:
        base = lyrics
        for path in wanted:
            trial = pins(genome, params.form, {p: edits[p] for p in [*kept, path]})[0]
            try:
                attempt = arrange_mod.keep(genome, base, trial, variation.leanings(params))
                if base.held:  # sung as held words, so the lineage can hand them down
                    attempt = arrange_mod.sing(genome, params.form, arrange_mod.hold(genome, attempt))
            except arrange_mod.ArrangeError as e:
                problems.append(Problem(path, str(e)))
                continue
            kept.append(path)
            lyrics = attempt
        applied += kept
    elif chosen:
        problems += [Problem(p, "this song's words aren't drawn from a store of verses, so they can't be chosen")
                     for p in wanted]
    if body and composition.has_lines(params):  # a line for a verse these words don't sing isn't kept
        sung = lyrics if lyrics is not None else arrange_mod.seed_lyrics(genome, params.form)
        before = len(overrides.problems)
        params, unsung = overrides.unsung(params, composition.lyric_keys(genome, params.form, sung))
        applied = [p for p in applied if p not in unsung]
        problems += overrides.problems[before:]
    if sung_by_a_machine and lyrics is not None and genome.source.get("bank"):
        # the lineage holds what is sung: the person's words among them, else its own fitted to the form
        params = replace(params, words=arrange_mod.hold(genome, lyrics) if kept
                         else evolve.fitted(genome, params, voice, drift))
    silent = {p: composition.part_silent(genome, params, p) or takeover.part_missing(genome, params, p)
              for p in applied if p.startswith("part.") and edits.get(p) is not None}
    silent = {p: why for p, why in silent.items() if why}
    if silent:  # notes played for a place this version doesn't play, or a player its band hasn't got: said, not kept
        params = _unplayed(params, generated, silent)
        applied = [p for p in applied if p not in silent]
        problems += [Problem(p, why) for p, why in silent.items()]
    params, applied, problems, edits = _taken_over(genome, generated, params, applied, problems, edits)
    # a change for one place this version doesn't sing (or whose section an arrangement laid to other lines): said,
    # and put back as the version before had it (after the arrangement, which decides the lines)
    unplaced = {p: composition.place_silent(genome, params, p.split(".", 1)[1]) for p in applied
                if p.startswith(("tune.", "chords.")) and composition.is_place(p.split(".", 1)[1])
                and edits.get(p) is not None}
    unplaced = {p: why for p, why in unplaced.items() if why}
    if unplaced:
        params = _unplaced(genome, params, generated, unplaced)
        applied = [p for p in applied if p not in unplaced]
        problems += [Problem(p, why) for p, why in unplaced.items()]
    if "phrasing" in edits and phrasing_json is not None:
        applied.append("phrasing")
    marks_ = marks(genome, generated, generated_lyrics, lyrics, applied, edits, phrasing_json, params=params,
                   program=_program_for(genome, parent, voice, drift, seed, generated, body))
    return Resolved(generated, params, generated_lyrics, lyrics, applied, problems, marks_)


# The choices that decide what the program's own is for the rest: the style (its band, its tempo, its sound) and
# the shape (its order). "was" for a tempo after the style changed is that style's tempo, not the one it replaced.
CONTEXT = re.compile(r"style\.\w+|form\.(?!order$)\w+")


def _program_for(genome, parent, voice, drift, seed, generated, body: dict):
    """The program's own choices for this version as the person has set its style and shape: what a tempo, a
    player's level, a sound or the order would be had the person not set them too (`generated` when neither is
    set)."""
    from .realize import choose_params

    context = {p: v for p, v in body.items() if CONTEXT.fullmatch(p)}
    if not context:
        return generated
    return choose_params(genome, parent, voice, drift, seed, overrides=Overrides(genome, context))


def _unplaced(genome, params, generated, paths) -> object:
    """The parameters with a person's tune or chords for these places put back as the version before had them."""
    held = dict(params.composition)
    for path in paths:
        kind, key = path.split(".", 1)
        key = composition.edit_key(genome, key)
        for kind in (kind, "melisma") if kind == "tune" else (kind,):
            now = dict(held.get(kind) or {})
            was = (generated.composition.get(kind) or {}).get(key)
            if was is None:
                now.pop(key, None)
            else:
                now[key] = was
            if now:
                held[kind] = now
            else:
                held.pop(kind, None)
    return replace(params, composition=held)


def _unplayed(params, generated, paths) -> object:
    """The parameters with a person's parts at these paths put back as the version before had them."""
    held = dict(params.composition)
    parts = {k: dict(v) for k, v in (held.get("parts") or {}).items()}
    before = composition.performed_parts(generated)
    for path in paths:
        player, key = composition.part_key(path)
        was = before.get(player, {}).get(key)
        lines = parts.setdefault(player, {})
        if was is None:
            lines.pop(key, None)
        else:
            lines[key] = was
        if not lines:
            parts.pop(player, None)
    if parts:
        held["parts"] = parts
    else:
        held.pop("parts", None)
    return replace(params, composition=held)


# ---------------------------------------------------------------- what the record keeps


def phrasing_mark(phrasing_json: dict) -> dict:
    """How a record marks a phrasing chosen by a person: whose it was never, only what it is and a
    fingerprint of it, so the same phrasing can be recognised (and given again to replay the rendition)."""
    everyone = "singers" in str(phrasing_json.get("source_detail", ""))
    digest = hashlib.sha256(json.dumps(phrasing_json, sort_keys=True).encode()).hexdigest()[:16]
    return {"value": "everyone's way" if everyone else "a person's way", "was": "the song's own way",
            "detail": phrasing_json.get("source_detail", ""), "digest": digest}


def marks(genome: Genome, generated, generated_lyrics, final_lyrics, applied: list[str], edits: dict,
          phrasing_json: dict | None = None, params=None, program=None) -> dict:
    """The record's block of a person's choices: for each edit that took effect, the value chosen and what
    the program had chosen ("was"). Replaying the values as edits (from_record) makes the same rendition
    from the same parent, machine and day. A choice of the arrangement's that keeps what the program chose
    (a lock: the page's padlock on a cell, a section or an option) is marked locked: true; params, the version
    as sung, says what the program had in a cell (takeover.program_cells); program, the program's own for the style
    and shape the person chose (_program_for), what a tempo, a level, a sound or the order was in that version."""
    program = program if program is not None else generated
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
        elif path == "form.order":  # the program's order for the shape chosen
            was = composition.section_ids(program.form)
        elif path.startswith("tune."):  # a line everywhere, or one place of the form: what the program sang there
            key = path[5:]
            was = (composition.phrase_value(genome, generated, composition.line_of(genome, key),
                                            place=key if composition.is_place(key) else None))
        elif path.startswith("chords."):
            was = composition.chords_value(genome, generated, path[7:])
        elif path.startswith("arrange."):  # the arrangement taken over: what the version held, else the program's
            was = takeover.value(genome, generated, path)
            if was == "the program's own" and params is not None:
                was = takeover.program_value(genome, params, path)
        elif path.startswith("part."):  # the notes are in the record's parameters: marked by their count
            was = composition.part_value(generated, path)
            out[path] = {"value": {"notes": len(value or [])} if value is not None else None,
                         "was": {"notes": len(was)} if isinstance(was, list) else was}
            continue
        elif path.startswith("lyrics."):
            was = composition.lyric_value(genome, generated, generated_lyrics, path)
        elif path.startswith("form."):
            was = generated_shape.get(path[5:])
        elif path in ("words.refrain", "words.bridge"):  # words for all: just the slots chosen, as first sung
            sung = _sung(generated_lyrics, path) or {}
            was = {k: sung.get(k) for k in value}
        elif path.startswith("words."):
            was = _sung(generated_lyrics, path, value, genome)
            value = _sung(final_lyrics, path, value, genome) or value
        elif path.startswith("variants."):  # every variant the program chose was sung: dropping one changes it
            was = int(path[9:]) < len(getattr(generated, "variants", None) or ())
        elif path.startswith("band.") and path[5:] in instruments():  # a player's gain, in a lineup or of the eight
            was = program.band.gain(path[5:])
        elif path.startswith("style."):
            was = getattr(generated.style, path[6:], None)
            was = (was or "ballad") if path == "style.name" else was
        elif sound_mod.owns(path):  # sound design: what the program has there (a parent's choice among it)
            was = sound_mod.value_of(program, path)
        else:
            was = variation.read(program, path)
        out[path] = {"value": value, "was": was}
        if path.startswith(("arrange.", "style.")) and value == was and value is not None:
            out[path]["locked"] = True  # a lock: the program's own choice, kept (docs/STUDIO-REDESIGN.md)
    return out


def _sung(lyrics, path: str, like=None, genome: Genome | None = None):
    """What some words sing at a word edit's place: a verse's id and its slot words; a refrain's couplet,
    or, for an edit that chose more of it (like), its couplet, head and the slot words chosen..."""
    if lyrics is None:
        return None
    match = WORDS.fullmatch(path)
    block, index, whole = match.group(1), match.group(2), match.group(3)
    if block:
        sung = [s for s in lyrics.sections if s.block == block]
        i = int(index)
        if i >= len(sung):
            return None
        s = sung[i]
        if block == "verse":
            return {"id": s.id, "slots": dict(s.slots)}
        if not isinstance(like, dict):
            return s.id
        out = {"id": s.id} if "id" in like else {}
        if "head" in like:
            out["head"] = s.head or (arrange_mod.refrain_heads(genome)[0] if genome is not None else None)
        if "slots" in like:
            out["slots"] = {k: s.slots.get(k) for k in like["slots"]}
        return out
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
    out = {path: mark["value"] for path, mark in (data.get("chosen_by_you") or {}).items() if path != "phrasing"}
    parts = ((data.get("params") or {}).get("composition") or {}).get("parts") or {}
    for path in [p for p in out if p.startswith("part.")]:  # a part's notes, from the parameters they were sung with
        if out[path] is not None:
            player, key = composition.part_key(path)
            out[path] = parts.get(player, {}).get(key, [])
    return out


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
    for i, s in enumerate(refrains):  # each refrain's own words: what the rules leave it to choose
        place = arrange_mod.refrain_place(genome, i, len(refrains), s.head)
        head = s.head or arrange_mod.refrain_heads(genome)[0]
        free = arrange_mod.head_words(genome, head)
        keep = {"id": s.id} if i < len(refrains) - 1 else {}
        if place["head"] is None:
            keep["head"] = head
        slots = {k: v for k, v in s.slots.items() if len(free.get(k, (None, None))) > 1
                 and not (k == "question" and place["question"] is not None) and k not in arrange_mod.refrain_once(genome)}
        if slots:
            keep["slots"] = slots
        if keep:
            out[f"words.refrain.{i}"] = keep
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


# ---------------------------------------------------------------- the arrangement taken over (docs/ARRANGE.md, 2026-09-29)
#
# A person's arrangement (arrange.*: songbird.takeover) goes in with the composition (Overrides._arrange); what a
# version can't play of it is said here, after the rest is resolved, as a played part's is. The tempo a person may
# choose follows the style it is played in.

TEMPO_REACH = (0.4, 1.6)  # of the song's own tempo: the widest a person may take it, in any style
TEMPO_WIDEN = (0.9, 1.1)  # a style's own range, widened this much each way (multiplied), for a person


def tempo_range(genome: Genome, style=None) -> tuple[float, float]:
    """The tempos a person may choose for a version in a style (a Style, its dict, or None for the song's own):
    the style's range at its feel, times 0.9 and 1.1, never narrower than the song's designed 0.75 to 1.3 of its
    own tempo, inside 0.4 to 1.6 of it. The ballad keeps 0.75 to 1.3 (H: 72 to 124.8); synth folk reaches 134."""
    from .style import STYLES, Style, of

    song = song_params(genome).tempo
    lo, hi = _knob("tempo").bounds(1.0)
    s = style if isinstance(style, Style) else Style.from_dict(style) if style else Style()
    if s.name and s.name != "ballad" and s.name in STYLES:
        sdef = of(s)
        feel = s.feel or next(iter(sdef.feels), "straight")
        low, _, high = sdef.centre(feel)
        lo, hi = min(lo, TEMPO_WIDEN[0] * low), max(hi, TEMPO_WIDEN[1] * high)
    lo, hi = max(TEMPO_REACH[0], lo), min(TEMPO_REACH[1], hi)
    return round(lo * song, 1), round(hi * song, 1)


def _taken_over(genome: Genome, generated, params, applied: list, problems: list, edits: dict):
    """The version with the arrangement choices it can't play (a section it doesn't sing, a player its band hasn't
    got, a pattern its player doesn't play, a build at the end) said and put back as the version before had
    them; and the tempo marked as it is sung, where the style held it to its range."""
    if "tempo" in applied and abs(params.tempo - float(edits.get("tempo", params.tempo))) > 0.05:
        edits = {**edits, "tempo": params.tempo}
    quiet = {p: takeover.silent(genome, params, p, edits) for p in applied
             if p.startswith("arrange.") and edits.get(p) is not None}
    quiet = {p: why for p, why in quiet.items() if why}
    if not quiet:
        return params, applied, problems, edits
    held = takeover.copy(takeover.arranged(params))
    for path in quiet:
        takeover.put(held, path, genome, _held_before(genome, generated, path))
    composition_ = dict(params.composition)
    if held:
        composition_["arrange"] = held
    else:
        composition_.pop("arrange", None)
    params = replace(params, composition=composition_)
    return (params, [p for p in applied if p not in quiet], problems + [Problem(p, why) for p, why in quiet.items()],
            edits)


def _held_before(genome: Genome, generated, path: str):
    """What the version before held at an arrangement path (None: nothing, the program's own)."""
    sid, _, player, field = takeover.target(genome, path)
    entry = takeover.arranged(generated).get(sid, {})
    return entry.get("players", {}).get(player, {}).get(field) if player else entry.get(field)
