"""Notes in: a take played on a keyboard, or a MIDI file brought back from a sequencer, as edits.

docs/STUDIO.md, "Notes in". Both come to the same thing: notes laid over the version on the page, a line of the
form at a time, and turned into the edits a person could have made by hand, each checked as those are:

- a band player's notes in a line: part.<player>.<section>:<n>.<line> (composition.check_part);
- the singer's: tune.<line>, a note a syllable, through the tune's fences (composition.check_phrase);
- the Chords track's (a file only): chords.<line>, in the chord grammar (composition.check_chords).

Nothing is applied here. Each answer is a preview: the changes, each with its path, value and place, what
couldn't be taken and why, and what was left alone; the page applies the changes as one undoable step.

A file is compared with the MIDI file this version makes (midi.from_score), line by line, so a file brought back
unchanged is no change at all; a line whose notes differ is taken as the file has it. A line is where its notes
belong as the band's do (from its pickup to the next line's, an eighth of a beat early for a player's pushed
notes: composition.EARLY); ticks are read back as grid positions exactly (midi.tick_grid).
"""

from __future__ import annotations

import base64
import binascii
import math
from bisect import bisect_left, bisect_right

from . import composition as C
from . import midi
from .theory import MODES, SEVENTHS, chord_bass, chord_tones, degree_semitones

MAX_TAKE = 4096  # notes in one take
MAX_CHORD_NOTES = 20_000  # notes in a file's Chords track
ROOTS = ("I", "bII", "II", "bIII", "III", "IV", "#IV", "V", "bVI", "VI", "bVII", "VII")
QUALITIES = ("", "maj", "m", "dim", "aug", "sus2", "sus4",  # the plainest first: the triads, then a fourth tone
             "7", "m7", "maj7", "m7b5", "dim7", "6", "m6", "add9", "madd9", "7sus4", "7sus2")


# ---------------------------------------------------------------- the version's lines


def section_label(form, index: int) -> str:
    name = form[index]
    label = name.replace("bridge2", "Bridge 2").title()
    if list(form).count(name) > 1:
        label += f" {list(form)[:index + 1].count(name)}"
    return label


def layout(genome, params) -> list[dict]:
    """Every line of the form in order: its part key (verse:1.0), tune line, section's name and place in words,
    its first and last bar lines and the window its notes belong to (composition.line_windows), in grid units;
    whether the singer sings it, and how far a style's lift has raised it."""
    from .realize import timeline
    from .style import repeated_phrases

    clock = timeline(genome, params)
    m = genome.meter
    from .takeover import phrase_plan

    # each section's lines, as long as a person made it and sung or played as they had it (songbird.takeover)
    lined = phrase_plan(genome, params)
    flat = [(sid, name, i, j, pid) for i, (sid, name) in enumerate(zip(C.section_ids(params.form), params.form))
            for j, (pid, _) in enumerate(lined[i])]
    repeated = repeated_phrases(genome, params)
    refrains = [i for i, name in enumerate(params.form) if genome.section(name).lyrics == "refrain"]
    lift_from = refrains[-1] if params.style.lift and len(refrains) >= 2 else None
    out, u = [], clock.lead
    for k, (sid, name, i, j, pid) in enumerate(flat):
        phrase = genome.phrases[pid]
        after = genome.phrases[flat[k + 1][4]].pickup if k + 1 < len(flat) else (repeated[0].pickup if repeated else 0)
        end = u + phrase.bars * m.bar
        out.append({"key": f"{sid}.{j}", "sid": sid, "line": j, "pid": pid, "name": name, "index": i,
                    "where": f"{section_label(params.form, i)}, line {j + 1}", "u0": u, "u1": end,
                    "w0": u - phrase.pickup, "w1": end - after, "pickup": phrase.pickup,
                    "sung": bool(genome.section(name).lyrics) and bool(phrase.sung) and lined[i][j][1],
                    "up": 2 if lift_from is not None and i >= lift_from else 0,
                    # the section's own line there: a place a change can be kept for (one an arrangement added isn't)
                    "own": j < len(genome.section(name).phrases) and genome.section(name).phrases[j] == pid})
        u = end
    return out


def bucket(lines: list[dict], notes: list, early: float, at=lambda n: n[0]) -> tuple[list[list], list]:
    """Notes (sorted by at) shared out among the lines' windows, each window opened `early` grid units before
    its own; those before the first and after the last, apart."""
    out: list[list] = [[] for _ in lines]
    outside = []
    starts = [ln["w0"] - early for ln in lines]
    for n in notes:
        u = at(n)
        k = bisect_left(starts, u + 1e-9) - 1
        if k < 0 or u >= lines[k]["w1"] - early - 1e-9 and k == len(lines) - 1:
            outside.append(n)
        else:
            out[k].append(n)
    return out, outside


# ---------------------------------------------------------------- one line's notes, as edits


def part_notes(genome, line: dict, notes, tonic: int) -> list[list[int]]:
    """A band player's notes in one line as a part edit's numbers: [onset, length, pitch, velocity], onset in
    composition.PPB-ths of a beat from the line's first bar line (never before its pickup), pitch from the key's
    note (and from under a style's lift)."""
    beat = genome.meter.beat
    pickup = int(round(line["pickup"] / beat * C.PPB))
    out = []
    for u, u_end, pitch, vel in notes:
        onset = max(-pickup, int(round((u - line["u0"]) / beat * C.PPB)))
        length = min(C.PART_LONGEST * C.PPB, max(1, int(round((u_end - u) / beat * C.PPB))))
        out.append([onset, length, int(pitch) - tonic - line["up"], max(1, min(127, int(vel)))])
    return out


def degree_of(semitones: int, mode: str) -> int | None:
    """A pitch (semitones above the key's note) as a degree of the mode's scale (1 the key's note, 8 its
    octave), or None if the scale hasn't got it."""
    octave, step = divmod(int(semitones), 12)
    steps = MODES[mode]
    return octave * 7 + steps.index(step) + 1 if step in steps else None


def pitch_name(pitch: int) -> str:
    from .theory import NOTE_NAMES

    return f"{NOTE_NAMES[pitch % 12]}{pitch // 12 - 1}"


def tune_notes(genome, params, line: dict, notes) -> list[dict]:
    """A take on the singer's line as a tune edit's notes: each note a degree of the scale (the key's), its onset
    and length in beats from the line's first bar line; a note held into the next ends where it begins, and one
    too short for its syllable is given its quarter beat where there's room. Raises with why."""
    beat = genome.meter.beat
    out = []
    for k, (u, u_end, pitch, _) in enumerate(notes):
        degree = degree_of(int(pitch) - params.tonic - line["up"], params.mode)
        if degree is None:
            raise ValueError(f"note {k + 1} ({pitch_name(int(pitch))}) isn't in the key's scale")
        onset = round((u - line["u0"]) / beat * C.PPB) / C.PPB
        length = max(C.GRID, round((u_end - u) / beat * C.PPB) / C.PPB)
        out.append({"degree": degree, "onset": onset, "duration": length})
    for a, b in zip(out, out[1:]):
        a["duration"] = min(a["duration"], b["onset"] - a["onset"])
    return out


def _what(player: str, notes: list) -> str:
    return f"the {player}: {len(notes)} note{'s' if len(notes) != 1 else ''}" if notes else f"the {player} rests"


def _change(changes: dict, path: str, value, where: str, what: str) -> None:
    changes[path] = {"path": path, "value": value, "where": where, "what": what}


# ---------------------------------------------------------------- a take


def take(genome, params, player: str, notes, keys) -> dict:
    """A take played along with the sketch, as edits for the lines it covered (keys, "verse:1.0"...): notes as
    [beat, length, pitch, velocity], beats counted as the page's score counts them (from the song's first
    pickup), pitch a MIDI note. A band player's lines become part edits ([] where nothing was played: it
    rests there); the singer's ("voice") tune edits, the first place a line was played taken."""
    if not isinstance(notes, list) or len(notes) > MAX_TAKE:
        raise ValueError(f"a take is a list of at most {MAX_TAKE} notes")
    lines = layout(genome, params)
    by_key = {ln["key"]: ln for ln in lines}
    if not isinstance(keys, list) or not keys or len(keys) > len(lines) or any(k not in by_key for k in keys):
        raise ValueError("a take covers lines this version sings")
    if player != "voice":
        C.part_player(player)
    beat = genome.meter.beat
    clean = []
    for item in notes:
        if not isinstance(item, (list, tuple)) or len(item) != 4:
            raise ValueError("each note of a take is its beat, length, pitch and velocity")
        b, length, pitch, vel = item
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in item):
            raise ValueError("a take's notes are numbers")
        if not (0 <= pitch <= 127 and 0 < length <= 64 and 1 <= vel <= 127 and -64 <= b <= 1e5):
            raise ValueError("a take's note is out of range")
        clean.append((b * beat, (b + length) * beat, int(pitch), int(vel)))
    clean.sort()
    covered = [ln for ln in lines if ln["key"] in set(keys)]
    shared, _ = bucket(covered, clean, C.EARLY * beat)
    changes: dict = {}
    refused, said = [], []
    if player == "voice":
        taken: dict[str, str] = {}
        for ln, mine in zip(covered, shared):
            if not ln["sung"]:
                continue
            try:
                value = C.check_phrase(genome, ln["pid"], tune_notes(genome, params, ln, mine))
            except ValueError as e:
                refused.append({"where": ln["where"], "why": str(e)})
                continue
            if ln["pid"] in taken:
                if value != changes[f"tune.{ln['pid']}"]["value"]:
                    said.append(f"{ln['where']} is the same tune line as {taken[ln['pid']]}, played differently; "
                                f"a tune line is sung the same everywhere, so the first was taken")
                continue
            taken[ln["pid"]] = ln["where"]
            _change(changes, f"tune.{ln['pid']}", value, ln["where"],
                    f"the tune: {len(value)} notes, everywhere it's sung")
        return {"changes": list(changes.values()), "refused": refused, "said": said}
    for ln, mine in zip(covered, shared):
        path = f"part.{player}.{ln['key']}"
        try:
            value = C.check_part(genome, path, part_notes(genome, ln, mine, params.tonic))
        except ValueError as e:
            refused.append({"where": ln["where"], "why": str(e)})
            continue
        _change(changes, path, value, ln["where"], _what(player, value))
    return {"changes": list(changes.values()), "refused": refused, "said": said}


# ---------------------------------------------------------------- a MIDI file brought back


def decode(file: str) -> bytes:
    """A file sent as base64, held to the reader's size before it is decoded."""
    if not isinstance(file, str) or len(file) > (midi.MAX_FILE * 4) // 3 + 8:
        raise midi.Unreadable(f"it is bigger than a song's MIDI file can be ({midi.MAX_FILE // 1024} KB)")
    try:
        return base64.b64decode(file, validate=True)
    except (binascii.Error, ValueError):
        raise midi.Unreadable("it didn't arrive whole; try again") from None


def _tracks(read: dict) -> list[dict]:
    """A file's tracks as named note lists; a format 0 file's one track split by channel (named by the
    channel, for matching with the export's)."""
    tracks = [dict(t, index=i) for i, t in enumerate(read["tracks"])]
    if read["format"] == 0 and tracks:
        whole = tracks[0]
        channels = sorted({n[2] for n in whole["notes"]})
        return [dict(whole, name=None, channel=c, index=f"0:{c}", notes=[n for n in whole["notes"] if n[2] == c])
                for c in channels] + [dict(whole, notes=[], index="0")]
    return tracks


def _texts(read: dict, kind: int, scale: float) -> list[tuple[float, str]]:
    return sorted((t * scale, s) for tr in read["tracks"] for t, k, s in tr["texts"] if k == kind)


def _first(read: dict, field: str):
    found = sorted((x[0], x[1:]) for tr in read["tracks"] for x in tr[field])
    return found[0][1] if found else None


def from_file(genome, params, score, file_bytes: bytes, assign: dict | None = None) -> dict:
    """A MIDI file brought back (the version's own export, changed), as edits: see the module's docstring.
    assign: {file track index: the export's track name, or "" to leave it} for tracks it couldn't name.
    Raises midi.Unreadable for a file it can't read, or one made from another version."""
    theirs = midi.parse(file_bytes)
    data, _ = midi.from_score(genome, params, score, title=genome.title)
    ours = midi.parse(data)
    scale = midi.TPQ / theirs["tpq"]
    # the same version: its sections where ours are, in the same time and key (when the file says)
    mine, own = _texts(theirs, 0x06, scale), _texts(ours, 0x06, 1.0)
    if mine and ([s for _, s in mine] != [s for _, s in own]
                 or any(abs(a - b) > 1.5 for (a, _), (b, _) in zip(mine, own))):
        raise midi.Unreadable("it was made from another version of the song (its sections differ): download "
                              "the MIDI again from this version, change that, and bring it back")
    said = [] if mine else ["The file has no section markers, so it was read against this version's bars."]
    for field, what in (("meters", "time signature"), ("keys", "key")):
        a, b = _first(theirs, field), _first(ours, field)
        if a is not None and a[:2] != b[:2]:
            raise midi.Unreadable(f"its {what} isn't this version's: change the {what} in the studio, "
                                  "download the MIDI again, and bring that back")
    # its tracks, matched with ours by name (or as the page was told)
    ours_by_name = {t["name"]: t for t in ours["tracks"][1:] if t["name"]}
    channel_names = {n[2]: t["name"] for t in ours["tracks"][1:] for n in t["notes"][:1]}
    assign = {str(k): v for k, v in (assign or {}).items()}
    matched: dict[str, dict] = {}
    unmatched = []
    for t in _tracks(theirs):
        if not t["notes"]:
            continue
        name = t["name"] if t.get("channel") is None else channel_names.get(t["channel"])
        chosen = assign.get(str(t["index"]))
        if chosen is not None:
            if chosen == "":
                continue
            if chosen not in ours_by_name:
                raise ValueError(f"this version has no track called {chosen}")
            name = chosen
        else:
            name = next((n for n in ours_by_name if name and n.lower() == name.strip().lower()), None)
        if name is None:
            unmatched.append({"track": str(t["index"]), "name": t["name"] or f"channel {t.get('channel', 0) + 1}",
                              "notes": len(t["notes"])})
            continue
        if name in matched:
            said.append(f"Two tracks are {name}; the first was read.")
            continue
        matched[name] = t
    out = {"changes": [], "refused": [], "said": said, "unmatched": unmatched,
           "tracks": sorted(ours_by_name)}
    if not matched:
        out["said"].append("No track in the file is one this version plays.")
        return out
    _, origin, step, per, _, _ = midi.tick_grid(genome, params)
    to_u = lambda tick: origin + tick * step / per  # noqa: E731
    lines = layout(genome, params)
    parts = {midi.part_name(p): p for p in {n.part for n in score.notes}}
    changes: dict = {}
    for name, t in sorted(matched.items(), key=lambda kv: (kv[0] != "Voice", kv[0] != "Chords", kv[0])):
        mine_notes = [(to_u(on * scale), to_u(off * scale), key, vel) for on, off, _, key, vel in t["notes"]]
        our_notes = [(to_u(on), to_u(off), key, vel) for on, off, _, key, vel in ours_by_name[name]["notes"]]
        if name == "Chords":
            _chords(genome, params, score, lines, t["notes"], ours_by_name[name]["notes"], scale, changes, out)
            continue
        part = parts.get(name)
        same = _same_lines(genome, params, lines, sorted(mine_notes), sorted(our_notes), name == "Voice")
        changed = [k for k, s in enumerate(same["lines"]) if not s]
        if not changed and same["outside"]:
            continue
        if not same["outside"]:
            out["said"].append(f"{name}: changes before the first line or after the last (a count-in, an ending) "
                               "aren't taken.")
        if not changed:
            continue
        if name == "Voice":
            _voice(genome, params, lines, same, changed, changes, out)
        elif part is None or part.startswith("choir"):
            out["said"].append(f"{name}: the lineage voices sing harmony made from the tune and the chords; "
                               "change those instead.")
        elif midi.percussive(part):
            out["said"].append(f"{name}: the drums' changes aren't taken yet.")
        else:
            for k in changed:
                ln = lines[k]
                path = f"part.{part}.{ln['key']}"
                try:
                    value = C.check_part(genome, path, part_notes(genome, ln, same["mine"][k], params.tonic))
                except ValueError as e:
                    out["refused"].append({"where": f"{ln['where']} ({name})", "why": str(e)})
                    continue
                _change(changes, path, value, ln["where"], _what(part, value))
    out["changes"] = list(changes.values())
    return out


def _normal(genome, ln: dict, notes, voice: bool) -> list[tuple]:
    beat = genome.meter.beat
    return sorted((round((u - ln["u0"]) / beat * C.PPB), round((z - u) / beat * C.PPB), int(p), int(v))
                  for u, z, p, v in notes) if not voice else \
        sorted((round((u - ln["u0"]) / beat * C.PPB), round((z - u) / beat * C.PPB), int(p), 0) for u, z, p, v in notes)


def _alike(a: list[tuple], b: list[tuple]) -> bool:
    """Two lines' notes the same, as a sequencer's saving can leave them: each pitch exact, its onset within a
    48th of a beat, its length within a 24th, its velocity within 2."""
    return len(a) == len(b) and all(x[2] == y[2] and abs(x[0] - y[0]) <= 2 and abs(x[1] - y[1]) <= 4
                                    and abs(x[3] - y[3]) <= 2 for x, y in zip(a, b))


def _same_lines(genome, params, lines, mine, ours, voice: bool) -> dict:
    """Both tracks' notes shared out among the lines (the singer's with the lineage's lay taken off, so its
    notes fall in their own lines), and whether each line's are alike."""
    beat = genome.meter.beat
    back = params.lay * beat if voice else 0.0
    mine = [(u + back, z + back, p, v) for u, z, p, v in mine]
    ours = [(u + back, z + back, p, v) for u, z, p, v in ours]
    early = C.EARLY * beat
    a, a_out = bucket(lines, mine, early)
    b, b_out = bucket(lines, ours, early)
    same = [_alike(_normal(genome, ln, x, voice), _normal(genome, ln, y, voice)) for ln, x, y in zip(lines, a, b)]
    return {"lines": same, "mine": a, "ours": b,
            "outside": _alike(sorted((round(u * 96), 0, p, v) for u, _, p, v in a_out),
                              sorted((round(u * 96), 0, p, v) for u, _, p, v in b_out))}


def _scoped(lines, found: dict, kind: str, where: list[int], what, said: list | None = None) -> dict:
    """Changed lines as edits, one place or everywhere (docs/STUDIO.md, "Looser harmony and melody"): a tune line
    changed the same way in every place it comes (of `where`, the lines that can be compared) is one edit for the
    line everywhere; one changed in only some of its places, or differently, an edit for each of those places.
    found: {line index: its new value}. what(value, everywhere): the change in words."""
    out: dict = {}
    for pid in dict.fromkeys(lines[k]["pid"] for k in found):
        places = [k for k in where if lines[k]["pid"] == pid]
        mine = [k for k in places if k in found]
        values = [found[k] for k in mine]
        if len(mine) == len(places) and all(v == values[0] for v in values):
            path = f"{kind}.{pid}"
            out[path] = {"path": path, "value": values[0], "where": lines[mine[0]]["where"], "what": what(values[0], True)}
            continue
        for k in mine:
            if not lines[k].get("own", True):  # a line an arrangement repeated: no place of its own to keep it for
                if said is not None:
                    said.append(f"{lines[k]['where']}: a line the arrangement plays again has no place of its own; "
                                "change it where the section has it, or everywhere")
                continue
            path = f"{kind}.{lines[k]['key']}"
            out[path] = {"path": path, "value": found[k], "where": lines[k]["where"], "what": what(found[k], False)}
    return out


def _voice(genome, params, lines, same, changed, changes, out) -> None:
    """The singer's changed lines as tune edits: each note moved as the file moved it, from the line's notes as
    written there (not their performed timing); a note added or taken away is refused with the count. A line
    changed alike wherever it's sung is changed everywhere, one changed in some places only there (_scoped)."""
    beat = genome.meter.beat
    found: dict[int, list] = {}
    for k in changed:
        ln = lines[k]
        if not ln["sung"]:
            continue
        mine, ours = sorted(same["mine"][k]), sorted(same["ours"][k])
        want = len(genome.phrases[ln["pid"]].sung)
        if len(mine) != len(ours):
            out["refused"].append({"where": f"{ln['where']} (Voice)", "why": f"the line needs {want} notes, one for "
                                   f"each syllable; the file has {len(mine)} there"})
            continue
        written = C.notes_at(genome, params, ln["key"])  # as this place sings it
        notes = []
        try:
            for i, ((u, z, p, _), (u0, z0, p0, _), w) in enumerate(zip(mine, ours, written)):
                degree = w["degree"]
                if p != p0:
                    semis = degree_semitones(degree, params.mode) + (p - p0)
                    degree = degree_of(semis, params.mode)
                    if degree is None:
                        raise ValueError(f"note {i + 1} ({pitch_name(p)}) isn't in the key's scale")
                moved = (u - u0) / beat
                held = ((z - u) - (z0 - u0)) / beat
                onset = w["onset"] + (round(moved * C.PPB) / C.PPB if abs(moved) > 1 / 48 else 0)
                length = w["duration"] + (round(held * C.PPB) / C.PPB if abs(held) > 1 / 24 else 0)
                notes.append({"degree": degree, "onset": onset, "duration": max(C.GRID, length)})
            for a, b in zip(notes, notes[1:]):
                a["duration"] = min(a["duration"], max(C.GRID, b["onset"] - a["onset"]))
            value = C.check_phrase(genome, ln["pid"], notes)
        except ValueError as e:
            out["refused"].append({"where": f"{ln['where']} (Voice)", "why": str(e)})
            continue
        if value != written:
            found[k] = value
    sung = [k for k, ln in enumerate(lines) if ln["sung"]]
    changes.update(_scoped(lines, found, "tune", sung, lambda value, everywhere: "the tune, everywhere this line is "
                           "sung" if everywhere else "the tune, here only", out["said"]))


# ---------------------------------------------------------------- the chords


_NAMED: dict[str, dict] = {}


def chord_table(mode: str) -> dict:
    """Every chord the grammar can write in this mode, by its tones and bass (pitch classes above the key's
    note): the plainest way to write each (the root in the bass, a numeral of the mode, the key's own quality
    first: A major in D minor is Vmaj, not bVI). The root in the bass is plainest of all, so the notes A C E G
    over A are Am7, and over C C6 (a person's inversion, /3 /5 /7, only where the bass is another tone)."""
    if mode not in _NAMED:
        table: dict = {}
        for quality_rank, quality in enumerate(QUALITIES):
            for root in ROOTS:
                for bass in ("", "/3", "/5") + (("/7",) if quality in SEVENTHS else ()):
                    symbol = root + quality + bass
                    tones = frozenset(t % 12 for t in chord_tones(symbol, mode))
                    if len(tones) < 3:
                        continue
                    key = (tones, chord_bass(symbol, mode) % 12)
                    rank = (bool(bass), root.startswith(("b", "#")), quality_rank)
                    if key not in table or rank < table[key][0]:
                        table[key] = (rank, symbol)
        _NAMED[mode] = {k: v[1] for k, v in table.items()}
    return _NAMED[mode]


def name_chord(pitches, tonic: int, mode: str) -> str:
    """Notes sounding together as a chord of the grammar (the lowest is the bass), or why they aren't one."""
    if not pitches:
        raise ValueError("no chord sounds there")
    tones = frozenset((p - tonic) % 12 for p in pitches)
    if len(tones) > 4:
        raise ValueError(f"a chord of {len(tones)} different notes (a ninth chord or more) isn't taken yet")
    if len(tones) < 3:
        raise ValueError("a chord needs three different notes")
    symbol = chord_table(mode).get((tones, (min(pitches) - tonic) % 12))
    if symbol is None:
        bass_in = (min(pitches) - tonic) % 12 in tones
        raise ValueError(("that chord isn't a major, minor, diminished, augmented or sus chord" if len(tones) == 3 else
                          "that chord isn't one the chords can write: a seventh (7, maj7, m7, m7♭5, °7, 7sus4, "
                          "7sus2), a sixth (6, m6) or an added ninth") if bass_in
                         else "its bass isn't a note of the chord" if len(tones) == 3 or bass_in
                         else "its bass isn't a note of the chord, or not one it can have (a sixth or a ninth)")
    root = symbol.split("/")[0]
    plain = root.lstrip("b#")
    if plain.isupper() and not any(root.endswith(q) for q in QUALITIES[1:]):  # a plain numeral: as the key has it
        third = (chord_tones(symbol, mode)[1] - chord_tones(symbol, mode)[0]) % 12
        if third == 3:
            symbol = symbol.replace(plain, plain.lower(), 1)
    elif plain.endswith(("m7", "m7b5", "dim7", "m6", "madd9")):  # a minor seventh (sixth, ninth) written as one: vim7
        kind = next(q for q in ("m7b5", "madd9", "dim7", "m7", "m6") if plain.endswith(q))
        numeral = plain[: -len(kind)]
        symbol = symbol.replace(numeral + kind, numeral.lower() + kind, 1)
    return symbol


def _chords(genome, params, score, lines, theirs, ours, scale, changes, out) -> None:
    """The Chords track's changed lines as chord edits: the chord sounding at each beat, a bar shared as evenly
    as its changes allow, each named from its notes."""
    if len(theirs) > MAX_CHORD_NOTES:
        out["refused"].append({"where": "Chords", "why": f"the track has more than {MAX_CHORD_NOTES:,} notes"})
        return
    m = genome.meter
    ticks, _, _ = midi.clock_map(genome, params, score.duration)
    clock = midi.tick_grid(genome, params)[0]
    theirs = sorted((on * scale, off * scale, key) for on, off, _, key, _ in theirs)
    ours = sorted((float(on), float(off), key) for on, off, _, key, _ in ours)
    ons_theirs = [n[0] for n in theirs]
    ons_ours = [n[0] for n in ours]
    longest = max((n[1] - n[0] for n in theirs + ours), default=0)
    beats = int(round(m.bar / m.beat))
    counts = C.chords_per_bar(genome)
    found: dict[int, list] = {}

    def sounding(notes, ons, tick):
        lo = bisect_left(ons, tick - longest - 1)
        hi = bisect_left(ons, tick + 1e-9)
        return sorted(n[2] for n in notes[lo:hi] if n[0] <= tick < n[1])

    for k, ln in enumerate(lines):
        grid = [ticks.tick(clock.seconds(ln["u0"] + b * m.bar + k * m.beat))
                for b in range(genome.phrases[ln["pid"]].bars) for k in range(beats)]
        nudge = midi.TPQ / 8
        mine = [sounding(theirs, ons_theirs, t + nudge) for t in grid]
        own = [sounding(ours, ons_ours, t + nudge) for t in grid]
        start, end = grid[0] - nudge, ticks.tick(clock.seconds(ln["u1"])) - nudge
        struck = [n[0] for n in theirs[bisect_left(ons_theirs, start):bisect_left(ons_theirs, end)]]
        off_beat = next((t for t in struck if min(abs(t - g) for g in grid) > midi.TPQ / 16), None)
        if mine == own and off_beat is None:
            continue
        where = f"{ln['where']} (Chords)"
        if off_beat is not None:
            bar = max(0, bisect_right(grid, off_beat) - 1) // beats
            out["refused"].append({"where": where, "why": f"a chord changes off the beat in bar {bar + 1}; the "
                                   "chords change on beats"})
            continue
        tonic = params.tonic + ln["up"]
        bars = []
        try:
            for b in range(len(grid) // beats):
                sample = mine[b * beats:(b + 1) * beats]
                n = next(c for c in counts if all(sample[i] == sample[(i // (beats // c)) * (beats // c)]
                                                  for i in range(beats)))
                bar = []
                for c in range(n):
                    try:
                        bar.append(name_chord(sample[c * (beats // n)], tonic, params.mode))
                    except ValueError as e:
                        raise ValueError(f"bar {b + 1}: {e}") from None
                bars.append(bar)
        except ValueError as e:
            out["refused"].append({"where": where, "why": str(e)})
            continue
        current = [list(bar) for bar in C.at_line(genome, params, ln["key"]).chords]  # as this place sings them
        bars = [[_kept(s, old, params.mode) for s, old in zip(bar, now)] if len(bar) == len(now) else bar
                for bar, now in zip(bars, current)]
        if bars == current:
            continue
        found[k] = C.check_chords(genome, ln["pid"], bars)
    from .theory import chord_name

    def what(value, everywhere):
        named = " | ".join(" ".join(chord_name(s, params.tonic, params.mode) for s in bar) for bar in value)
        return f"the chords: {named}, " + ("everywhere this line is sung" if everywhere else "here only")

    changes.update(_scoped(lines, found, "chords", list(range(len(lines))), what, out["said"]))


def _kept(symbol: str, old: str, mode: str) -> str:
    """The chord as the song wrote it, where the file's names the same notes (a revoicing isn't a change)."""
    same = lambda s: (frozenset(t % 12 for t in chord_tones(s, mode)), chord_bass(s, mode) % 12)  # noqa: E731
    return old if same(symbol) == same(old) else symbol
