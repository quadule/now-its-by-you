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

import math
import re
from collections import Counter
from dataclasses import replace

from . import variants
from .genome import sung_words
from .theory import MODES, degree_semitones

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


def check_phrase(genome, pid: str, value) -> list[dict] | None:
    """Validate atomically: a rejected note leaves the entire phrase unchanged."""
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


def played(phrase, params):
    """Human choices take precedence over variants on this line alone."""
    notes = variants.realized(phrase, params.variants)
    edited = params.composition.get("tune", {}).get(phrase.id)
    if not edited:
        return notes
    return tuple(replace(n, degree=d, onset=t, dur=duration, ornament=(), variant=None)
                 for n, (d, t, duration) in zip(notes, edited))


def phrase_value(genome, params, pid):
    return [{"degree": n.degree, "onset": n.onset / genome.meter.beat, "duration": n.dur / genome.meter.beat}
            for n in played(genome.phrases[pid], params)]


def view(genome, params, lyrics) -> dict:
    """The editor's complete arrangement and piano roll without rendering audio. duration: the realized
    score's length in seconds, the last chord's ring included, which the rendered audio lasts."""
    from .arrange import seed_lyrics
    from .realize import timeline
    from .style import ring

    clock = timeline(genome, params)
    meter = genome.meter
    lyrics = lyrics if lyrics is not None else seed_lyrics(genome, params.form)
    keys = lyric_keys(genome, params.form, lyrics)
    patches = authored(genome, params, lyrics)
    lyrics = lyric_overlay(genome, params, lyrics)
    lines = lyrics.lines_for(genome, params.form)
    edited = params.composition.get("tune", {})
    sections = []
    cursor = clock.lead
    for index, (name, identity) in enumerate(zip(params.form, section_ids(params.form))):
        section = genome.section(name)
        start = cursor
        phrases = []
        for j, pid in enumerate(section.phrases):
            phrase = genome.phrases[pid]
            words = sung_words(lines[index][j]) if lines[index] else []
            notes = []
            for k, n in enumerate(played(phrase, params)):
                syllable, word, _ = words[k] if k < len(words) else ("", "", 0)
                notes.append({"index": k, "degree": n.degree, "alter": n.alter,
                              "pitch": params.tonic + degree_semitones(n.degree, params.mode, n.alter),
                              "onset": n.onset / meter.beat, "duration": n.dur / meter.beat,
                              "syllable": syllable or "", "word": word or "", "edited": pid in edited})
            phrases.append({"id": pid, "path": f"tune.{pid}", "start_beat": cursor / meter.beat,
                            "duration_beats": phrase.bars * meter.bar / meter.beat,
                            "pickup_beats": phrase.pickup / meter.beat, "notes": notes,
                            "chords": [list(bar) for bar in phrase.chords], "bounds": bounds(genome, phrase),
                            "lyric_path": f"lyrics.{keys[index]}.{j}" if keys[index] else None,
                            "lyric_text": lines[index][j] if lines[index] else "",
                            "syllable_count": len(phrase.sung),
                            "authored": str(j) in patches[index]})
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
            "order": section_ids(params.form), "sections": sections, "edited_phrases": sorted(edited),
            "arranged": bool(params.composition.get("order")),
            "guidance": "Notes stay in the song's range. Keep one note per syllable and the final home note. "
                        "A tune line changes everywhere it appears. Repeated sections keep their story order."}
