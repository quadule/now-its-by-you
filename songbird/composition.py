"""Small, portable arrangements and phrase edits, carried in rendition parameters.

The editor speaks beats; the record stores scale degrees and grid units. A phrase
keeps its syllable count, bar length and cadence so its words, harmony and future
renditions still fit. Empty composition data leaves old renditions unchanged.

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
LYRIC_PATH = re.compile(r"lyrics\.([A-Za-z][A-Za-z0-9_-]*):(\d+)\.(\d+)")


def section_ids(form) -> list[str]:
    seen: Counter = Counter()
    result = []
    for name in form:
        result.append(f"{name}:{seen[name]}")
        seen[name] += 1
    return result


def lyric_target(genome, path: str) -> tuple[str, int, str]:
    match = LYRIC_PATH.fullmatch(path)
    if match is None:
        raise ValueError("a lyric line needs its section, occurrence and line number")
    name, occurrence, line = match.groups()
    try:
        section = genome.section(name)
    except KeyError:
        raise ValueError(f"there is no section called {name}") from None
    if name not in genome.sections and name != "bridge2":
        raise ValueError(f"there is no section called {name}")
    if not section.lyrics:
        raise ValueError("this section is instrumental; write words in a sung section")
    index = int(line)
    if int(occurrence) >= MAX_SECTIONS or index >= len(section.phrases):
        raise ValueError("there is no such lyric line in this section")
    return f"{name}:{int(occurrence)}", index, section.phrases[index]


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


def lyric_overlay(genome, params, lyrics):
    """Overlay authored lines on a display/performance copy, never on the bank's held words."""
    authored = params.composition.get("lyrics", {})
    if not authored:
        return lyrics
    from .arrange import seed_lyrics

    base = lyrics if lyrics is not None else seed_lyrics(genome, params.form)
    sung = iter(base.sections)
    sections = []
    for name, identity in zip(params.form, section_ids(params.form)):
        if not genome.section(name).lyrics:
            continue
        section = next(sung)
        patches = authored.get(identity, {})
        lines = tuple(patches.get(str(i), text) for i, text in enumerate(section.lines))
        sections.append(replace(section, lines=lines) if patches else section)
    return replace(base, sections=tuple(sections))


def lyric_value(genome, params, lyrics, path):
    identity, line, _ = lyric_target(genome, path)
    if identity not in section_ids(params.form):
        return None
    from .arrange import seed_lyrics

    sung = lyric_overlay(genome, params, lyrics) or seed_lyrics(genome, params.form)
    index = section_ids(params.form).index(identity)
    return sung.lines_for(genome, params.form)[index][line]


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
    """The editor's complete arrangement and piano roll without rendering audio."""
    from .realize import timeline

    clock = timeline(genome, params)
    meter = genome.meter
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
                            "lyric_path": f"lyrics.{identity}.{j}" if section.lyrics else None,
                            "lyric_text": lines[index][j] if lines[index] else "",
                            "syllable_count": len(phrase.sung),
                            "authored": str(j) in params.composition.get("lyrics", {}).get(identity, {})})
            cursor += phrase.bars * meter.bar
        nth = int(identity.rsplit(":", 1)[1])
        label = name.replace("bridge2", "Bridge 2").title()
        if sum(n == name for n in params.form) > 1:
            label += f" {nth + 1}"
        sections.append({"index": index, "id": identity, "name": name, "label": label,
                         "start_beat": start / meter.beat, "duration_beats": (cursor - start) / meter.beat,
                         "start_seconds": clock.seconds(start), "end_seconds": clock.seconds(cursor),
                         "sung": bool(section.lyrics), "phrases": phrases})
    return {"tempo": params.tempo, "tonic": params.tonic, "mode": params.mode, "scale": list(MODES[params.mode]),
            "beats_per_bar": meter.bar / meter.beat, "grid": GRID,
            "duration_beats": clock.end / meter.beat, "duration_seconds": clock.seconds(clock.end),
            "order": section_ids(params.form), "sections": sections, "edited_phrases": sorted(edited),
            "arranged": bool(params.composition.get("order")),
            "guidance": "Notes stay in the song's range. Keep one note per syllable and the final home note. "
                        "A tune line changes everywhere it appears. Repeated sections keep their story order."}
