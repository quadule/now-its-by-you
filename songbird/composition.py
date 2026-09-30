"""Small, portable arrangements and phrase edits, carried in rendition parameters.

The editor speaks beats; the record stores scale degrees and grid units. A phrase
keeps its syllable count, bar length and cadence so its words, harmony and future
renditions still fit. Empty composition data leaves old renditions unchanged.

A person's own lyric lines ("lines") are kept by the words they replace, not by
where those words fall in the form: a verse's lines under the verse it sings
(verse:wire, the bank's verse; verse:seed2, the seed's second verse, in a song
without a bank), and any other sung section's under its name and time round
(refrain:0, bridge2:0), the last refrain's round being "last", as arrange hands
down its rounds (the first ones and the last, which sings the canon). The words
underneath go on changing down a lineage (arrange.hold, songbird.evolve): a
descendant that still sings that verse sings the person's line in it, wherever
the verse now comes; one that no longer sings it doesn't sing the line, and a
later one that sings the verse again brings the line back with it. So a line
never lands in a verse it wasn't written for, or moves when the verse count
changes. Keeping the drawn words for every authored section instead would stop
the lineage's words changing wherever a person wrote a line, and still leave a
line keyed by place to shift when the count of verses did.

A record made before lines were kept this way keeps them by place ("lyrics",
under section_ids); it sings them where it sang them, and hands them down
(handed_down) by key, read from the words it sang.

A line a person writes in the studio is checked as a bank line is for being
sung: a syllable per note, every word pronounceable, any *focus* mark wrapping
a whole word (check_lyric, through songbird.bank.line_problem). It is not held
to the bank's arrangement rules in songbird.arrange: the canon couplet sung
last, the rules for which question words a refrain asks and when, the twins
rule against two heads asking the same question as written, or held_problem's
fit of held words to a form. Those rules govern what the bank draws and hands
down, so a song drawn by chance stays one story; an authored line is none of
that. It is laid over one line of one section's performance copy
(lyric_overlay), never written into the held words, so the bank's own choices
underneath still keep every rule. What a person writes on purpose, even a
question asked twice, is theirs to sing. An arrangement's order is different:
order() still asks arrange.problem whether the bank can fill it.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import replace

from . import variants
from .genome import sung_words
from .theory import MODES, SEVENTHS, chord_bass, chord_name, chord_tones, degree_semitones, parse_symbol

GRID = 0.25  # a sixteenth note in a quarter-note beat
MAX_SECTIONS = 48
LYRIC_PATH = re.compile(r"lyrics\.([A-Za-z][A-Za-z0-9_-]*):([A-Za-z0-9_-]+)\.(\d+)")
LAST = "last"  # the last refrain's round, which the bank's rules always sing the same way


def section_ids(form) -> list[str]:
    """Each section of a form as the arrangement names it: its name and which time it comes (verse:1)."""
    seen: Counter = Counter()
    result = []
    for name in form:
        result.append(f"{name}:{seen[name]}")
        seen[name] += 1
    return result


def lyric_keys(genome, form, lyrics=None) -> list[str | None]:
    """The key a person's lines are kept under for each section of the form, None where it sings no
    words: a verse's the verse the words sing (arrange.Lyrics; None while the words aren't known, as
    for lyrics=None), any other sung section's its round, the last refrain's "last"."""
    form = tuple(form)
    total, seen = Counter(form), Counter()
    sung = iter(lyrics.sections) if lyrics is not None else None
    out: list[str | None] = []
    for name in form:
        block = genome.section(name).lyrics
        if not block:
            out.append(None)
            continue
        verse = next(sung).id if sung is not None else None
        if block == "verse":
            out.append(f"{name}:{verse}" if verse else None)
        elif block == "refrain" and seen[name] == total[name] - 1:
            out.append(f"{name}:{LAST}")
        else:
            out.append(f"{name}:{seen[name]}")
        seen[name] += 1
    return out


def verse_names(genome) -> set[str]:
    """What a verse can be called in a lyric key: the bank's verses, and the seed's (seed1, seed2...)."""
    names = {f"seed{i + 1}" for i in range(len(genome.seed_verses))}
    if genome.source.get("bank"):
        from .arrange import verse_ids

        names.update(verse_ids(genome))
    return names


def lyric_target(genome, path: str) -> tuple[str, int, str]:
    """A lyric path's key, line number and phrase: lyrics.verse:wire.2 is the third line of the verse wire."""
    match = LYRIC_PATH.fullmatch(path)
    if match is None:
        raise ValueError("a lyric line needs its section, which verse or time round it is, and its line number")
    name, which, line = match.groups()
    try:
        section = genome.section(name)
    except KeyError:
        raise ValueError(f"there is no section called {name}") from None
    if name not in genome.sections and name != "bridge2":
        raise ValueError(f"there is no section called {name}")
    if not section.lyrics:
        raise ValueError("this section is instrumental; write words in a sung section")
    if section.lyrics == "verse":
        if which.isdigit():
            raise ValueError("a verse's lines go with the verse they're written for, named for it, "
                             "not its place; choose the line again where it's sung")
        if which not in verse_names(genome):
            raise ValueError(f"this song has no verse called {which}")
    elif not ((which.isdigit() and int(which) < MAX_SECTIONS) or (which == LAST and section.lyrics == "refrain")):
        raise ValueError("there is no such lyric line in this section")
    index = int(line)
    if index >= len(section.phrases):
        raise ValueError("there is no such lyric line in this section")
    return f"{name}:{which}", index, section.phrases[index]


def check_lyric(genome, path: str, value) -> str | None:
    """A pronounceable syllable per note; spelling, punctuation and emphasis stay
    human. The line is checked as a bank line is (songbird.bank.line_problem),
    a *focus* mark included, and told what's wrong in the studio's words."""
    from .bank import line_problem

    _, _, pid = lyric_target(genome, path)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError("write a lyric line of 1 to 500 characters")
    if any(ord(c) < 32 and c not in "\t\n\r" for c in value) or any(c in value for c in "{}<>|\\"):
        raise ValueError("use words and punctuation; split syllables with hyphens")
    text = " ".join(value.replace("’", "'").split())
    if any(not part for word in text.split() for part in word.split("-")):
        raise ValueError("put syllable hyphens inside words, like car-ry")
    target = len(genome.phrases[pid].sung)
    problem = line_problem(text, target, genome.lexicon)
    if problem is None:
        return text
    kind = problem[0]
    if kind == "mark":
        raise ValueError(f"mark the word to lean on with a star each side, like *heart*, "
                         f"punctuation outside; {problem[1]!r} isn't marked that way")
    if kind == "count":
        raise ValueError(f"this line needs {target} syllables, one per note; it has {problem[1]}. "
                         "Split longer words with hyphens, like car-ry")
    if kind == "unknown":
        raise ValueError(f"the singer doesn't know how to pronounce {problem[1]!r}; try another spelling or word")
    raise ValueError(f"{problem[1]!r} needs {problem[3]} syllables; show them with hyphens")


def has_lines(params) -> bool:
    """Whether a person wrote any of the lines sung, kept by key or, in an older record, by place."""
    return bool(params.composition.get("lines") or params.composition.get("lyrics"))


def authored(genome, params, lyrics=None) -> list[dict]:
    """A person's lines for each section of the form ({line number: text}, {} for none), as sung over
    these words (arrange.Lyrics; None: the seed's own): those kept by key, over any an older record
    keeps by place."""
    lines, placed = params.composition.get("lines", {}), params.composition.get("lyrics", {})
    if not lines and not placed:
        return [{} for _ in params.form]
    if lines and lyrics is None:
        from .arrange import seed_lyrics

        lyrics = seed_lyrics(genome, params.form)
    keys = lyric_keys(genome, params.form, lyrics) if lines else [None] * len(params.form)
    return [{**placed.get(place, {}), **lines.get(key, {})} if genome.section(name).lyrics else {}
            for name, place, key in zip(params.form, section_ids(params.form), keys)]


def lyric_overlay(genome, params, lyrics):
    """Overlay authored lines on a display/performance copy, never on the bank's held words."""
    if not has_lines(params):
        return lyrics
    from .arrange import seed_lyrics

    base = lyrics if lyrics is not None else seed_lyrics(genome, params.form)
    sung = iter(base.sections)
    sections = []
    for name, patch in zip(params.form, authored(genome, params, base)):
        if not genome.section(name).lyrics:
            continue
        section = next(sung)
        lines = tuple(patch.get(str(i), text) for i, text in enumerate(section.lines))
        sections.append(replace(section, lines=lines) if patch else section)
    return replace(base, sections=tuple(sections))


def lyric_value(genome, params, lyrics, path):
    """The line a lyric path names as these words sing it (a person's own over them), None if they don't."""
    key, line, _ = lyric_target(genome, path)
    from .arrange import seed_lyrics

    base = lyrics if lyrics is not None else seed_lyrics(genome, params.form)
    keys = lyric_keys(genome, params.form, base)
    if key not in keys:
        return None
    sung = lyric_overlay(genome, params, base).lines_for(genome, params.form)[keys.index(key)]
    return sung[line] if sung else None


def handed_down(genome, params):
    """A rendition's parameters as its child inherits them: lines an older record keeps by place
    ("lyrics") kept by key instead, read from the words it sang (its held words, or the seed's own);
    a line in a section it didn't sing is left behind. The same parameters when there are none."""
    placed = params.composition.get("lyrics")
    if placed is None:
        return params
    from . import arrange

    words = params.words
    if words and genome.source.get("bank") and not arrange.held_problem(genome, params.form, words):
        sung = arrange.sing(genome, params.form, words)
    else:
        sung = arrange.seed_lyrics(genome, params.form)
    keys = dict(zip(section_ids(params.form), lyric_keys(genome, params.form, sung)))
    lines: dict = {}
    for place, patch in placed.items():
        if keys.get(place):
            lines.setdefault(keys[place], {}).update(patch)
    for key, patch in params.composition.get("lines", {}).items():
        lines.setdefault(key, {}).update(patch)
    held = {k: v for k, v in params.composition.items() if k != "lyrics"}
    if lines:
        held["lines"] = lines
    return replace(params, composition=held)


def order(genome, value) -> list[str] | None:
    """Check occurrence identities as well as section names, preserving lyric order."""
    from . import arrange, variation

    if value is None:
        return None
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_SECTIONS:
        raise ValueError(f"an arrangement needs 1 to {MAX_SECTIONS} sections")
    names, seen = [], Counter()
    for token in value:
        if not isinstance(token, str):
            raise ValueError("each section needs its name and occurrence")
        name, separator, index = token.partition(":")
        try:
            section = genome.section(name)
        except KeyError:
            raise ValueError(f"there is no section called {name}") from None
        if separator and index != str(seen[name]):
            raise ValueError("repeated sections keep their story order; move them around other sections, "
                             "or choose different words within them")
        if name != section.name or (name not in genome.sections and name != "bridge2"):
            raise ValueError(f"there is no section called {name}")
        seen[name] += 1
        names.append(name)
    lo, hi = variation.verse_range(genome)
    count = sum(variation.is_verse(genome, n) for n in names)
    if not lo <= count <= hi:
        raise ValueError(f"the song sings {lo} to {hi} verses, not {count}")
    if "bridge2" in names and ("bridge" not in names or names.index("bridge2") < names.index("bridge")):
        raise ValueError("the second bridge follows the first bridge")
    if genome.source.get("bank"):
        why = arrange.problem(genome, names)
        if why:
            raise ValueError(why)
    return names


def bounds(genome, phrase) -> dict:
    degrees = [n.degree for p in genome.phrases.values() for n in p.sung]
    low, high = min(degrees) - 2, max(degrees) + 2
    end = phrase.bars * genome.meter.bar / genome.meter.beat
    pickup = max(p.pickup for p in genome.phrases.values()) / genome.meter.beat
    last = phrase.sung[-1].onset / genome.meter.beat if phrase.sung else end
    return {"min_degree": low, "max_degree": high,
            "allowed_degrees": list(range(low, high + 1)),
            "min_onset": -phrase.pickup / genome.meter.beat,
            "max_end": end, "max_final_onset": max(last, end - pickup - GRID),
            "min_duration": GRID, "grid": GRID, "cadence_degree": phrase.sung[-1].degree if phrase.sung else None,
            "max_leap": 7}


def _finite(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("note values must be finite numbers")
    return float(value)


def edit_key(genome, key: str) -> str:
    """The key a tune or chord edit is kept under: a line's id, or a place key written the one way (place_key)."""
    return place_key(genome, key) if is_place(key) else key


def line_of(genome, key: str) -> str:
    """The tune line a tune or chord edit's key names: the line itself, or the line sung at that place."""
    return place_target(genome, key)[3] if is_place(key) else key


def check_phrase(genome, pid: str, value) -> list[dict] | None:
    """Validate atomically: a rejected note leaves the entire phrase unchanged. pid: a tune line, or a place of
    the form (refrain:last.1), whose line's fences it keeps."""
    pid = line_of(genome, pid)
    if pid not in genome.phrases:
        raise ValueError(f"there is no tune line called {pid}")
    if value is None:
        return None
    phrase = genome.phrases[pid]
    if not phrase.sung:
        raise ValueError("this line is a rest; it has no melody notes to move")
    if not isinstance(value, list) or len(value) != len(phrase.sung):
        raise ValueError(f"this line needs {len(phrase.sung)} notes, one for each syllable")
    limits = bounds(genome, phrase)
    result = []
    for i, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"degree", "onset", "duration"}:
            raise ValueError("each note needs degree, onset and duration")
        degree, onset, duration = (_finite(item[k]) for k in ("degree", "onset", "duration"))
        if not degree.is_integer() or not limits["min_degree"] <= degree <= limits["max_degree"]:
            raise ValueError(f"note {i + 1} is outside this song's singing range")
        if duration < GRID or onset < limits["min_onset"] or onset + duration > limits["max_end"] + 1e-8:
            raise ValueError(f"note {i + 1} must stay inside the line, with at least a quarter beat for its syllable")
        # A machine's expressive timings may fall between the editing grid. Keep
        # those exact values when submitted; newly dragged notes snap in the UI.
        if result and onset < result[-1]["onset"] + result[-1]["duration"] - 1e-8:
            raise ValueError(f"notes {i} and {i + 1} overlap; each syllable needs its own time")
        if result and abs(degree - result[-1]["degree"]) > max(7, abs(phrase.sung[i].degree - phrase.sung[i - 1].degree)):
            raise ValueError(f"the leap into note {i + 1} is wider than an octave")
        result.append({"degree": int(degree), "onset": onset, "duration": duration})
    if (result[-1]["degree"] - phrase.sung[-1].degree) % 7:
        raise ValueError("the last note keeps the line's home note; try moving it an octave")
    if result[-1]["onset"] > limits["max_final_onset"] + 1e-8:
        raise ValueError("the last syllable needs room before the next line's pickup")
    return result


def pack_phrase(genome, notes) -> list[list]:
    # Independent rounding can turn touching notes into overlaps in compound
    # meters, so the next edit rejects a rhythm we already accepted. Preserve
    # floating-point timing through the compact representation and JSON.
    return [[n["degree"], n["onset"] * genome.meter.beat,
             n["duration"] * genome.meter.beat] for n in notes]


_HARMONIZED: dict = {}  # (the song, a person's chords) -> the song with them: one object each, so caches keyed by it hit


def harmonized(genome, params):
    """The song with a person's chords in place of the tune lines' own (params.composition["chords"]), for
    realizing it: the same genome, untouched, when nobody changed a chord. The same chords give the same
    object back (a few dozen kept), so what is cached per song isn't made again for every request."""
    chords = {pid: bars for pid, bars in (params.composition.get("chords") or {}).items() if pid in genome.phrases}
    if not chords:
        return genome
    key = (id(genome), json.dumps(chords, sort_keys=True))
    held = _HARMONIZED.get(key)
    if held is not None and held[0] is genome:
        return held[1]
    phrases = {pid: replace(p, chords=tuple(tuple(bar) for bar in chords[pid])) if pid in chords else p
               for pid, p in genome.phrases.items()}
    out = replace(genome, phrases=phrases)
    if len(_HARMONIZED) >= 64:
        _HARMONIZED.pop(next(iter(_HARMONIZED)))
    _HARMONIZED[key] = (genome, out)
    return out


def chords_per_bar(genome) -> list[int]:
    """How many chords a bar may have: each a whole number of beats, the bar shared evenly (1, 2 or 4 in
    4/4; 1 or 2 in 6/8), as the band lays a bar's chords on its beats."""
    beats = max(1, int(round(genome.meter.bar / genome.meter.beat)))
    return [n for n in range(1, beats + 1) if beats % n == 0]


def check_chords(genome, pid: str, value) -> list[list[str]] | None:
    """A person's chords for a tune line: a list of chords for each of its bars, each bar shared evenly on
    its beats, each chord a function of the key (theory.parse_symbol: a numeral, a quality, a bass). None
    releases the line to the song's own chords. Validated whole: a refused chord leaves the line as it was. pid: a
    tune line, or a place of the form (refrain:last.1)."""
    pid = line_of(genome, pid)
    if pid not in genome.phrases:
        raise ValueError(f"there is no tune line called {pid}")
    if value is None:
        return None
    phrase = genome.phrases[pid]
    if not isinstance(value, list) or len(value) != phrase.bars:
        raise ValueError(f"this line is {phrase.bars} bar{'s' if phrase.bars > 1 else ''} long: give chords for each")
    counts = chords_per_bar(genome)
    out = []
    for b, bar in enumerate(value):
        if not isinstance(bar, list) or len(bar) not in counts:
            raise ValueError(f"bar {b + 1} takes {', '.join(map(str, counts[:-1]))} or {counts[-1]} chords, "
                             "sharing it evenly on its beats")
        chords = []
        for symbol in bar:
            if not isinstance(symbol, str) or len(symbol) > 16:
                raise ValueError(f"bar {b + 1} has a chord that isn't one")
            try:
                parse_symbol(symbol)
            except ValueError:
                raise ValueError(f"{symbol.strip()!r} isn't a chord this song can name: a numeral of the key "
                                 "(I to VII, b or # before it), then maj, m, dim, aug, sus2, sus4, 7, maj7, m7, m7b5, "
                                 "dim7, 6, m6, add9, madd9, 7sus4 or 7sus2, then /3, /5 or (with a seventh) /7") from None
            chords.append(symbol.strip())
        out.append(chords)
    return out


def chords_value(genome, params, pid: str) -> list[list[str]]:
    """A tune line's chords as these parameters sing them: a person's, or the song's own; at a place of the form
    (refrain:last.1), the chords it sings there."""
    if is_place(pid):
        return [list(bar) for bar in at_place(genome, params, pid).chords]
    held = (params.composition.get("chords") or {}).get(pid)
    return [list(bar) for bar in held] if held else [list(bar) for bar in genome.phrases[pid].chords]


SEVENTH_KINDS = {(4, 7, 11): "maj7", (3, 7, 10): "m7", (4, 7, 10): "7", (3, 6, 10): "m7b5", (3, 6, 9): "dim7",
                 (3, 7, 11): None, (4, 8, 11): None}  # a mode's own sevenths as the grammar writes them (None: not one)


def key_sevenths(params) -> list[dict]:
    """The key's own seventh chords (the triad on each degree and the scale's seventh above it), each written as
    the chord it is (Imaj7, iim7, V7, viim7b5 in major; the mode's own in any other), with its name; a degree
    whose seventh the grammar has no name for (a minor-major seventh) is left out."""
    out = []
    for d in range(1, 8):
        tones = [degree_semitones(d + k, params.mode) for k in (0, 2, 4, 6)]
        kind = SEVENTH_KINDS.get(tuple((t - tones[0]) % 12 for t in tones[1:]))
        if kind is None:
            continue
        numeral = ("I", "II", "III", "IV", "V", "VI", "VII")[d - 1]
        numeral = numeral.lower() if kind in ("m7", "m7b5", "dim7") else numeral
        symbol = numeral + kind
        out.append({"symbol": symbol, "name": chord_name(symbol, params.tonic, params.mode)})
    return out


def chord_choices(params) -> dict:
    """What the chord card offers in this key: the chords of the key (a numeral each, with its name), its seventh
    chords, and every root a chord can have (the twelve numerals, each with its note)."""
    from .theory import NOTE_NAMES

    sharps = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")  # a raised root is spelt sharp

    roots = ["I", "bII", "II", "bIII", "III", "IV", "#IV", "V", "bVI", "VI", "bVII", "VII"]
    diatonic = []
    for numeral in ("I", "II", "III", "IV", "V", "VI", "VII"):
        name = chord_name(numeral, params.tonic, params.mode)
        minor = name.endswith(("m", "°")) and not name.endswith("sus4")
        diatonic.append({"symbol": numeral.lower() if minor else numeral, "name": name})
    return {"diatonic": diatonic, "sevenths": key_sevenths(params),
            "roots": [{"numeral": r, "note": (sharps if r.startswith("#") else NOTE_NAMES)[
                (params.tonic + chord_tones(r + "maj", params.mode)[0]) % 12]} for r in roots],
            "qualities": [["", "as the key has it"], ["maj", "major"], ["m", "minor"], ["dim", "diminished"],
                          ["aug", "augmented"], ["sus2", "sus2"], ["sus4", "sus4"],
                          ["7", "7 (dominant seventh)"], ["maj7", "maj7 (major seventh)"], ["m7", "m7 (minor seventh)"],
                          ["m7b5", "m7♭5 (half-diminished)"], ["dim7", "°7 (diminished seventh)"], ["6", "6 (sixth)"],
                          ["m6", "m6 (minor sixth)"], ["add9", "add9"], ["madd9", "m(add9)"], ["7sus4", "7sus4"],
                          ["7sus2", "7sus2"]],
            "basses": [[1, "root"], [3, "third"], [5, "fifth"], [7, "seventh"]],
            "with_seventh": sorted(SEVENTHS)}


def tune_key(phrase) -> str:
    """The key a line's own tune is kept under where it is sung: its place's, where that place has one
    (form_phrases), else the line's."""
    return phrase.place or phrase.id


def played(phrase, params):
    """Human choices take precedence over variants on this line alone: a place's own tune, else the line's."""
    notes = variants.realized(phrase, params.variants)
    edited = params.composition.get("tune", {}).get(tune_key(phrase))
    if not edited:
        return notes
    return tuple(replace(n, degree=d, onset=t, dur=duration, ornament=(), variant=None)
                 for n, (d, t, duration) in zip(notes, edited))


def phrase_value(genome, params, pid, place: str | None = None):
    """A line's notes as an edit writes them, as these parameters sing it: everywhere, or at one place of the form
    (a place key, "refrain:2.1"; its own tune if it has one, else the line's)."""
    phrase = genome.phrases[pid] if place is None else at_place(genome, params, place)
    return [{"degree": n.degree, "onset": n.onset / genome.meter.beat, "duration": n.dur / genome.meter.beat}
            for n in played(phrase, params)]


# ---------------------------------------------------------------- one place, or everywhere (2026-09-29)
#
# A chord or tune edit names a line everywhere it is sung (chords.<line>, tune.<line>), or one place of the form:
# <section>:<n>.<i>, the i-th line of the n-th time that section comes (the arrangement's id, as form.order and a
# played part name it), or <section>:last.<i>, of the last time it comes (docs/STUDIO.md, "Looser harmony and
# melody"). Kept in the same maps as the lines' (composition["tune"], composition["chords"]): a place key has a
# colon, a line's id never does. At each line of the form the place by number wins, then by last, then the line.

PLACE = re.compile(r"([A-Za-z][A-Za-z0-9_-]{0,31}):(\d{1,2}|last)\.(\d{1,2})")


def is_place(key: str) -> bool:
    return ":" in key


def place_target(genome, key: str) -> tuple[str, str, int, str]:
    """A place key's section, which time ("2" or "last"), line and tune line: refrain:last.1 is the second line
    (r2) of the last refrain. Raises with why."""
    match = PLACE.fullmatch(key)
    if match is None:
        raise ValueError("a place is a section, which time it comes (a number from 0, or last) and a line: "
                         "refrain:2.1, refrain:last.1")
    name, which, line = match.groups()
    try:
        section = genome.section(name)
    except KeyError:
        raise ValueError(f"there is no section called {name}") from None
    if (name not in genome.sections and name != "bridge2") or (which != "last" and int(which) >= MAX_SECTIONS):
        raise ValueError(f"there is no section called {name}")
    if int(line) >= len(section.phrases):
        raise ValueError(f"the {name} has {len(section.phrases)} line{'s' if len(section.phrases) != 1 else ''}")
    which = which if which == "last" else str(int(which))
    return name, which, int(line), section.phrases[int(line)]


def place_key(genome, key: str) -> str:
    """A place key written the one way it is kept: refrain:02.1 is refrain:2.1."""
    name, which, line, _ = place_target(genome, key)
    return f"{name}:{which}.{line}"


def place_keys(form, index: int, line: int) -> list[str]:
    """The keys the index-th section of a form looks up for its line, strongest first: its own time, then last
    (if it is the last time that section comes)."""
    name = form[index]
    nth = list(form[:index]).count(name)
    keys = [f"{name}:{nth}.{line}"]
    if nth == list(form).count(name) - 1:
        keys.append(f"{name}:last.{line}")
    return keys


def held_at(held: dict, keys: list[str]) -> str | None:
    """The first of these place keys that a map holds."""
    return next((k for k in keys if k in held), None)


def places_held(params) -> bool:
    return any(is_place(k) for kind in ("tune", "chords") for k in (params.composition.get(kind) or {}))


def form_phrases(genome, params) -> list:
    """The phrase for each line of the form, in order: the line itself (the very object, where no place has its
    own), or a copy with its place's chords and its place (Phrase.place: where played() reads its own tune), its
    id still the line's. genome: the song as realize sings it (harmonized: a person's everywhere chords in)."""
    lines = [(i, j, genome.phrases[pid]) for i, name in enumerate(params.form)
             for j, pid in enumerate(genome.section(name).phrases)]
    if not places_held(params):
        return [phrase for _, _, phrase in lines]
    tune, chords = params.composition.get("tune") or {}, params.composition.get("chords") or {}
    out = []
    for i, j, phrase in lines:
        keys = place_keys(params.form, i, j)
        at_tune, at_chords = held_at(tune, keys), held_at(chords, keys)
        if at_tune or at_chords:
            phrase = replace(phrase, place=at_tune,
                             chords=tuple(tuple(bar) for bar in chords[at_chords]) if at_chords else phrase.chords)
        out.append(phrase)
    return out


def at_place(genome, params, key: str):
    """The phrase one place of the form sings (a place key: "refrain:2.1", "refrain:last.1"), with its place's
    chords and tune where it has its own, else the line's everywhere; a place this form doesn't have: the line
    everywhere."""
    name, which, line, pid = place_target(genome, key)
    song = harmonized(genome, params)
    where = [i for i, n in enumerate(params.form) if n == name]
    nth = len(where) - 1 if which == "last" else int(which)
    if not 0 <= nth < len(where):
        return song.phrases[pid]
    k = sum(len(genome.section(n).phrases) for n in params.form[:where[nth]]) + line
    return form_phrases(song, params)[k]


def chords_at(genome, params, key: str) -> list[list[str]]:
    """A place's chords as these parameters sing them (a part key, "refrain:2.1")."""
    return [list(bar) for bar in at_place(genome, params, key).chords]


def scope(params, form, index: int, line: int, pid: str, kind: str) -> dict:
    """Where the tune ("tune") or chords ("chords") a line of the form sings come from: "place" (its own time),
    "last" (the last time its section comes), "line" (the line everywhere) or None (the program's own); the key
    it's kept under; and a place's number and last both held (the number wins)."""
    held = params.composition.get(kind) or {}
    keys = place_keys(form, index, line)
    at = held_at(held, keys)
    both = at is not None and len(keys) > 1 and all(k in held for k in keys)
    if at is not None:
        return {"from": "last" if at.split(":")[1].startswith("last") else "place", "key": at, "both": both}
    return {"from": "line" if pid in held else None, "key": pid if pid in held else None, "both": False}


def place_silent(genome, params, key: str) -> str | None:
    """Why a place edit isn't heard in this version (its section doesn't come that many times), or None."""
    name, which, _, _ = place_target(genome, key)
    count = list(params.form).count(name)
    if count == 0 or (which != "last" and int(which) >= count):
        return "this version doesn't sing that section there; your change waits for one that does"
    return None


def harmony(genome, phrase, params) -> list[dict]:
    """A tune line's chords as the band plays them: each where it starts in the line (beats from its first
    bar line) and how long it lasts (a bar's chords share it out on its beats, as songbird.band lays them),
    with its name in this key, its pitch classes (root first) and its bass; and the sung notes under it that
    aren't its tones (rubs, as the band hears them: a pickup under the first bar's chord, as realize puts
    it), "hard" where one is a semitone from a tone of the chord."""
    per_bar = genome.meter.bar / genome.meter.beat
    m = genome.meter
    notes = [n for n in played(phrase, params) if n.degree is not None]
    under: dict = {}
    for k, n in enumerate(notes):
        bar = int(min(max(n.onset // m.bar, 0), phrase.bars - 1))
        in_bar = phrase.chords[bar]
        slot = int(min(max((n.onset - bar * m.bar) * len(in_bar) // m.bar, 0), len(in_bar) - 1))
        pitch = params.tonic + degree_semitones(n.degree, params.mode, n.alter)
        under.setdefault((bar, slot), []).append((k, pitch % 12))
    out = []
    for b, bar in enumerate(phrase.chords):
        for k, symbol in enumerate(bar):
            a = round(k * per_bar / len(bar))
            z = round((k + 1) * per_bar / len(bar)) if k + 1 < len(bar) else per_bar
            tones = chord_tones(symbol, params.mode)
            pcs = [(params.tonic + t) % 12 for t in tones]
            rubs = [(i, pc) for i, pc in under.get((b, k), []) if pc not in pcs]
            entry = {"bar": b, "slot": k, "start": b * per_bar + a, "beats": z - a, "symbol": symbol,
                     "name": chord_name(symbol, params.tonic, params.mode), "pcs": pcs,
                     "bass": (params.tonic + chord_bass(symbol, params.mode)) % 12,
                     "rubs": [i for i, _ in rubs],
                     "hard": any(min((pc - t) % 12, (t - pc) % 12) == 1 for _, pc in rubs for t in pcs)}
            if len(pcs) > 3:  # a person's seventh (sixth, ninth) a half step from a sung note: a sharp rub of its own
                entry["tension"] = [i for i, pc in under.get((b, k), [])
                                    if min((pc - pcs[3]) % 12, (pcs[3] - pc) % 12) == 1]
                entry["hard"] = entry["hard"] or bool(entry["tension"])
            out.append(entry)
    return out


def view(genome, params, lyrics) -> dict:
    """The editor's complete arrangement and piano roll without rendering audio. duration: the realized
    score's length in seconds, the last chord's ring included, which the rendered audio lasts."""
    from .arrange import seed_lyrics
    from .realize import timeline
    from .style import ring

    clock = timeline(genome, params)
    meter = genome.meter
    song = genome
    genome = harmonized(genome, params)  # a person's chords, where they changed any
    chorded = params.composition.get("chords") or {}
    lyrics = lyrics if lyrics is not None else seed_lyrics(genome, params.form)
    keys = lyric_keys(genome, params.form, lyrics)
    patches = authored(genome, params, lyrics)
    lyrics = lyric_overlay(genome, params, lyrics)
    lines = lyrics.lines_for(genome, params.form)
    edited = params.composition.get("tune", {})
    in_parts = performed_parts(params)
    at_places = iter(form_phrases(genome, params))  # each line as its place sings it
    sections = []
    cursor = clock.lead
    for index, (name, identity) in enumerate(zip(params.form, section_ids(params.form))):
        section = genome.section(name)
        start = cursor
        phrases = []
        for j, pid in enumerate(section.phrases):
            phrase = next(at_places)
            words = sung_words(lines[index][j]) if lines[index] else []
            here = place_keys(params.form, index, j)  # this place's own key, and its "last" if it is the last time
            several = params.form.count(name) > 1
            tune_from, chords_from = scope(params, params.form, index, j, pid, "tune"), scope(
                params, params.form, index, j, pid, "chords")
            notes = []
            for k, n in enumerate(played(phrase, params)):
                syllable, word, _ = words[k] if k < len(words) else ("", "", 0)
                notes.append({"index": k, "degree": n.degree, "alter": n.alter,
                              "pitch": params.tonic + degree_semitones(n.degree, params.mode, n.alter),
                              "onset": n.onset / meter.beat, "duration": n.dur / meter.beat,
                              "syllable": syllable or "", "word": word or "",
                              "edited": tune_from["from"] is not None})
            phrases.append({"id": pid, "path": f"tune.{pid}", "start_beat": cursor / meter.beat,
                            "duration_beats": phrase.bars * meter.bar / meter.beat,
                            "pickup_beats": phrase.pickup / meter.beat, "notes": notes,
                            "chords": [list(bar) for bar in phrase.chords], "bounds": bounds(genome, phrase),
                            "harmony": harmony(genome, phrase, params),
                            "chords_path": f"chords.{pid}", "chords_edited": chords_from["from"] is not None,
                            "song_chords": [list(bar) for bar in song.phrases[pid].chords],
                            # one place, or everywhere: this place's paths, where its tune and chords come from
                            # ("place", "last", "line" or None), and how many places sing the line
                            "place": here[0], "place_last": here[1] if several and len(here) > 1 else None,
                            "tune_scope": tune_from, "chords_scope": chords_from,
                            # what the line sings everywhere, where this place has its own: what an edit for
                            # everywhere starts from
                            "line_chords": [list(bar) for bar in genome.phrases[pid].chords]
                            if chords_from["from"] in ("place", "last") else None,
                            "line_notes": phrase_value(song, params, pid)
                            if tune_from["from"] in ("place", "last") else None,
                            "appearances": sum(p == pid for n in params.form for p in genome.section(n).phrases),
                            "lyric_path": f"lyrics.{keys[index]}.{j}" if keys[index] else None,
                            "lyric_text": lines[index][j] if lines[index] else "",
                            "syllable_count": len(phrase.sung),
                            "authored": str(j) in patches[index],
                            # a person's own notes played in for a player here (notes in)
                            "part_key": f"{identity}.{j}",
                            "parts": sorted(p for p, held in in_parts.items() if f"{identity}.{j}" in held)})
            cursor += phrase.bars * meter.bar
        nth = int(identity.rsplit(":", 1)[1])
        label = name.replace("bridge2", "Bridge 2").title()
        if sum(n == name for n in params.form) > 1:
            label += f" {nth + 1}"
        sections.append({"index": index, "id": identity, "lyric_key": keys[index], "name": name, "label": label,
                         "start_beat": start / meter.beat, "duration_beats": (cursor - start) / meter.beat,
                         "start_seconds": clock.seconds(start), "end_seconds": clock.seconds(cursor),
                         "sung": bool(section.lyrics), "phrases": phrases})
    return {"tempo": params.tempo, "tonic": params.tonic, "mode": params.mode, "scale": list(MODES[params.mode]),
            "beats_per_bar": meter.bar / meter.beat, "grid": GRID,
            "duration_beats": clock.end / meter.beat, "duration_seconds": clock.seconds(clock.end),
            "duration": round(clock.seconds(clock.end) + ring(params), 3),
            "order": section_ids(params.form), "sections": sections,
            "edited_phrases": sorted(k for k in edited if not is_place(k)),
            "edited_places": {kind: sorted(k for k in (params.composition.get(kind) or {}) if is_place(k))
                              for kind in ("tune", "chords")},
            "edited_chords": sorted(p for p in chorded if p in song.phrases), "chords_per_bar": chords_per_bar(song),
            "chord_choices": chord_choices(params),
            "players": playable(params), "performed": {p: sorted(held) for p, held in in_parts.items()},
            "arranged": bool(params.composition.get("order")),
            "guidance": "Notes stay in the song's range. Keep one note per syllable and the final home note. "
                        "A tune line changes everywhere it appears, or only in one place. Repeated sections keep "
                        "their story order."}


# ---------------------------------------------------------------- a player's notes, played in (notes in)
#
# A person's own notes for one band player in one line of one section of the form (docs/STUDIO.md, "Notes
# in"): part.<player>.<section>:<n>.<line>, a list of [onset, length, pitch, velocity], whole numbers: onset
# and length in PPB-ths of a beat from the line's first bar line, pitch in semitones from the key's note,
# velocity 1..127. Kept in params.composition["parts"][player]["<section>:<n>.<line>"]; realize plays them in
# place of that player's own notes there (performed()), on the rendition's clock beat by beat.

PPB = 96  # parts of a beat a played note's times are counted in
PART_PATH = re.compile(r"part\.([a-z][a-z0-9-]{0,31})\.([A-Za-z][A-Za-z0-9_-]{0,31}):(\d{1,3})\.(\d{1,2})")
PART_LINE_NOTES = 512  # notes a line
PART_NOTES = 4096  # notes across every line of a version played in
PART_BEAT_ONSETS = 32  # notes starting in any one beat
PART_SOUNDING = 10  # notes sounding at once (ten fingers)
PART_LONGEST = 32  # beats a note may be held
PART_SLACK = 5  # semitones a note may go past its player's range, for the key moving (the table's own reach)
EARLY = 1 / 8  # of a beat: a band note this much before a line's first bar line belongs to that line
UNPLAYABLE = ("drum", "voice")  # the drums' strokes aren't pitches; the singer's notes are the tune


def part_player(name: str) -> dict:
    """What a player that can be played in is: its range and whether it plays one note at a time (its
    synth's own spec), or why it can't be."""
    from .synth.instruments import known, spec

    if name == "voice" or name.startswith("choir") or name not in known():
        raise ValueError(f"{name} isn't a player whose notes can be played in"
                         + ("; the tune is changed as the tune" if name == "voice" else ""))
    about = spec(name)
    if about["register"] is None or name in UNPLAYABLE:
        raise ValueError(f"the {name} plays strokes, not notes; its part can't be played in yet")
    return {"register": tuple(about["register"]), "poly": bool(about["poly"])}


def playable(params) -> list[dict]:
    """The players of this version's band whose notes a person can play in (the page's choices): the
    singer's tune first, then each pitched player that plays, with its range (MIDI notes) and whether it
    plays one note at a time."""
    from .band import INSTRUMENTS
    from .midi import part_name

    out = [{"name": "voice", "label": "The tune (the singer's notes)", "low": 0, "high": 127, "poly": False}]
    for name in (params.band.lineup or INSTRUMENTS):
        if not params.band.plays(name):
            continue
        try:
            about = part_player(name)
        except ValueError:
            continue
        lo, hi = about["register"]
        out.append({"name": name, "label": part_name(name), "low": lo, "high": hi, "poly": about["poly"]})
    return out


def part_target(genome, path: str) -> tuple[str, str, int, str]:
    """A part path's player, section id, line number and tune line: part.fiddle.verse:1.0 is the fiddle in
    the first line of the second verse (tune line v1)."""
    match = PART_PATH.fullmatch(path)
    if match is None:
        raise ValueError("a played part needs its player, its section and which time it comes, and its line")
    player, name, nth, line = match.groups()
    part_player(player)
    try:
        section = genome.section(name)
    except KeyError:
        raise ValueError(f"there is no section called {name}") from None
    if (name not in genome.sections and name != "bridge2") or int(nth) >= MAX_SECTIONS:
        raise ValueError(f"there is no section called {name}")
    if int(line) >= len(section.phrases):
        raise ValueError(f"the {name} has {len(section.phrases)} lines")
    return player, f"{name}:{int(nth)}", int(line), section.phrases[int(line)]


def _whole(value, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, float) and value.is_integer() and abs(value) < 2**31:
            return int(value)
        raise ValueError(f"{what} must be whole numbers")
    return value


def check_part(genome, path: str, value) -> list[list[int]] | None:
    """A person's notes for one player in one line, checked whole (a refused note leaves the line as it was):
    each note starting inside the line (or its pickup) and held at most PART_LONGEST beats, in the player's
    range at the song's key (PART_SLACK either side, for the key moving), velocity 1..127, no more than the
    caps; sorted, an exact
    repeat dropped, and a one-note player's overlaps trimmed (each note ends where the next begins), so the
    numbers kept are the numbers played. [] rests the player through the line; None gives it back."""
    player, _, _, pid = part_target(genome, path)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("a played part is a list of notes")
    if len(value) > PART_LINE_NOTES:
        raise ValueError(f"a line takes at most {PART_LINE_NOTES} notes; this has {len(value)}")
    about = part_player(player)
    lo, hi = about["register"]
    tonic = int(genome.seed_params["tonic"])
    phrase = genome.phrases[pid]
    span = int(round(phrase.bars * genome.meter.bar / genome.meter.beat * PPB))
    pickup = int(round(phrase.pickup / genome.meter.beat * PPB))  # a note may lead in from the line's pickup
    notes = []
    for i, item in enumerate(value):
        if not isinstance(item, (list, tuple)) or len(item) != 4:
            raise ValueError(f"note {i + 1} needs its onset, length, pitch and velocity")
        onset, length, pitch, vel = (_whole(x, f"note {i + 1}'s numbers") for x in item)
        if not -pickup <= onset < span:
            raise ValueError(f"note {i + 1} starts outside the line")
        if not 1 <= length <= PART_LONGEST * PPB:
            raise ValueError(f"note {i + 1} is held longer than {PART_LONGEST} beats, or not at all")
        if not lo - PART_SLACK <= tonic + pitch <= hi + PART_SLACK or not 0 <= tonic + pitch <= 127:
            raise ValueError(f"note {i + 1} is outside what the {player} plays")
        if not 1 <= vel <= 127:
            raise ValueError(f"note {i + 1}'s velocity must be 1 to 127")
        notes.append([onset, length, pitch, vel])
    notes.sort(key=lambda n: (n[0], n[2], -n[1]))
    unique = [n for k, n in enumerate(notes) if not k or (n[0], n[2]) != (notes[k - 1][0], notes[k - 1][2])]
    starts = Counter(n[0] // PPB for n in unique)
    if starts and max(starts.values()) > PART_BEAT_ONSETS:
        beat = max(starts, key=starts.get)
        raise ValueError(f"more than {PART_BEAT_ONSETS} notes start in beat {beat + 1}")
    if not about["poly"]:
        for k in range(1, len(unique)):
            if unique[k][0] == unique[k - 1][0]:
                raise ValueError(f"the {player} plays one note at a time; notes {k} and {k + 1} start together")
        for k in range(len(unique) - 1):
            unique[k][1] = min(unique[k][1], unique[k + 1][0] - unique[k][0])
    else:
        ends: list[int] = []
        for n in unique:
            ends = [e for e in ends if e > n[0]] + [n[0] + n[1]]
            if len(ends) > PART_SOUNDING:
                raise ValueError(f"more than {PART_SOUNDING} notes sound at once in beat {n[0] // PPB + 1}")
    return unique


def performed_parts(params) -> dict:
    """{player: {"<section>:<n>.<line>": notes}} as these parameters carry them."""
    return {p: dict(lines) for p, lines in (params.composition.get("parts") or {}).items() if lines}


def part_key(path: str) -> tuple[str, str]:
    """A part path's player and the key its notes are kept under: part.fiddle.verse:1.0 -> fiddle, verse:1.0."""
    match = PART_PATH.fullmatch(path)
    return match.group(1), f"{match.group(2)}:{int(match.group(3))}.{int(match.group(4))}"


def part_value(params, path: str):
    """What a part path holds in these parameters: a person's notes, or "the program's own part"."""
    player, key = part_key(path)
    held = performed_parts(params).get(player, {}).get(key)
    return [list(n) for n in held] if held is not None else "the program's own part"


def part_silent(genome, params, path: str) -> str | None:
    """Why a person's notes at this path aren't heard in this version, or None if they are."""
    player, sid, _, _ = part_target(genome, path)
    if sid not in section_ids(params.form):
        return "this version doesn't play that section; your notes wait for one that does"
    if not params.band.plays(player):
        return f"this version's band has no {player}; your notes wait for one that has"
    return None


def beat_clock(clock):
    """Grid units to seconds along a rendition's clock, beat by beat and straight within a beat (a foot of a
    song re-barred in three), as a MIDI file's tempo map has it: where a person's played notes go."""
    m = clock.meter
    step = m.foot if clock.triple else m.beat

    def at(u: float) -> float:
        k = math.floor((u - clock.lead) / step)
        a = clock.lead + k * step
        s0, s1 = clock.seconds(a), clock.seconds(a + step)
        return s0 + (u - a) / step * (s1 - s0)

    return at


def line_windows(genome, params, placed, lead) -> dict[str, tuple[float, float, float, str]]:
    """Each line of the form by its part key ("verse:1.0"), in grid units: where a player's notes belong to
    it (from its own pickup before its first bar line to the next line's pickup, as the tune's notes do), its
    first bar line (where its notes' onsets count from) and its section's name, from realize's layout."""
    out, k = {}, 0
    bar = genome.meter.bar
    for sid, name in zip(section_ids(params.form), params.form):
        for j, _ in enumerate(genome.section(name).phrases):
            _, phrase, start, _ = placed[k]
            after = placed[k + 1][1].pickup if k + 1 < len(placed) else 0
            k += 1
            u0 = start + lead
            out[f"{sid}.{j}"] = (u0 - phrase.pickup, u0 + phrase.bars * bar - after, u0, name)
    return out


def _runs(genome, params, placed, lead):
    """For each player a person played in (and this version's band has), the lines of the form they played
    (key, window) and the runs those make (lines played one after another make one run), in grid units."""
    parts = performed_parts(params)
    if not parts:
        return {}
    windows = line_windows(genome, params, placed, lead)
    out = {}
    for player, lines in sorted(parts.items()):
        if player in UNPLAYABLE or not params.band.plays(player):
            continue
        here = sorted((windows[k][0], windows[k][1], k) for k in lines if k in windows)
        runs: list[list[float]] = []
        for w0, w1, _ in here:
            if runs and abs(runs[-1][1] - w0) < 1e-9:
                runs[-1][1] = w1
            else:
                runs.append([w0, w1])
        if here:
            out[player] = (here, runs, windows)
    return out


def make_room(genome, params, placed, lead, events: list, seconds) -> list:
    """The band's notes (band.Ev, in grid units, before they are placed in time) with room made for a
    person's played parts: each such player's own notes starting in a line they played are left out, and one
    started before and sounding into it (a held pad, a ringing harp string) stops where their notes begin.
    The same list when nobody played any in (band.arrange and idioms.arrange_style call this last)."""
    played = _runs(genome, params, placed, lead)
    if not played:
        return events
    kept = []
    for e in events:
        runs = played[e.part][1] if e.part in played else ()
        if any(a - 1e-9 <= e.u0 < b - 1e-9 for a, b in runs):
            continue
        for a, _ in runs:
            if e.u0 < a - 1e-9:
                if e.length > 0:
                    e.length = min(e.length, max(0.03, seconds(a) - seconds(e.u0) - e.shift))
                else:
                    e.u1 = min(e.u1, a)
        kept.append(e)
    return kept


def played_in(genome, params, placed, clock) -> list:
    """A person's played parts as notes (score.Note): each on the rendition's clock beat by beat (beat_clock:
    as the MIDI file's tempo map places a tick), its onset from its line's first bar line, held as played but
    not past the run of lines played in, at the key's note plus its pitch, as hard as it was played. None
    when nobody played any in."""
    played = _runs(genome, params, placed, clock.lead)
    if not played:
        return []
    from .score import Note

    beat = genome.meter.beat
    at = beat_clock(clock)
    out = []
    lines = performed_parts(params)
    for player, (here, runs, windows) in played.items():
        for w0, _, key in here:
            end = next(b for a, b in runs if a - 1e-9 <= w0 < b)
            _, _, u0, name = windows[key]
            for onset, length, pitch, vel in lines[player][key]:
                u = u0 + onset / PPB * beat
                start = at(u)
                stop = at(min(u + length / PPB * beat, end))
                out.append(Note(part=player, start=start, dur=max(stop - start, 0.03),
                                pitch=float(params.tonic + pitch), vel=vel / 127, section=name))
    return out


