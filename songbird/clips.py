"""Independent clips: a song of a person's own form (docs/notes/STUDIO-CLIPS.md).

A clip arrangement is one entry in the rendition's composition, written by the edit path `clips`:

    {"form": [the source form], "order": [clip ids, one per instance], "clips": {id: spec}, "next": n}

Each clip is a section of its own: its id (verse102) is its section's name in the resolved song, the source
section's name or a blank clip's role followed by a number from 101. A clip with "from" sings a section of the
source form (its generated words, tune and chords); a blank clip has a role and whether it is sung, and its lines
are rests until a person writes them. resolved() turns the arrangement into an ordinary song once (a genome with a
section per clip, parameters whose form is the order, the words for that form) and everything downstream reads
that. Without an arrangement every function here gives back what it was given.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace

FIRST = 101  # the first clip number
LAST = 999  # the last
MAX_INSTANCES = 48  # as composition.MAX_SECTIONS
MAX_CLIPS = 48
MAX_LINES = 16  # as takeover.MAX_LINES
LINE_BARS = 8  # bars a blank line may have
CLIP_BARS = 64
SONG_BARS = 768  # 48 sections of 16 bars, the most an arrangement without clips can lay
LABEL = 24  # characters in a clip's own label
ROLES = ("intro", "verse", "refrain", "turn", "break", "bridge", "tag", "outro")  # band.ROLES
ID = re.compile(r"([a-z]{1,24})(\d{3})")
SUNG_BLOCKS = {"verse": "verse", "refrain": "refrain", "bridge": "bridge", "tag": "tag"}  # a sung blank's lyric block


def base(name: str) -> str:
    """A section's name without its number: bridge2 is a bridge, verse102 a verse."""
    return re.sub(r"\d+$", "", name)


def stored(params) -> dict | None:
    """The clip arrangement these parameters hold, or None."""
    return (getattr(params, "composition", None) or {}).get("clips") or None


def implicit(form) -> dict:
    """The arrangement a form is without one: each section its own clip, in order (nothing stored)."""
    from .composition import section_ids

    form = list(form)
    ids = [f"{base(name)}{FIRST + k}" for k, name in enumerate(form)]
    return {"form": form, "order": ids, "clips": {c: {"from": sid} for c, sid in zip(ids, section_ids(form))},
            "next": FIRST + len(form)}


def arrangement(params) -> dict:
    """The clips these parameters sing: their own, or the form's implicit ones."""
    return stored(params) or implicit(params.form)


def home(value: dict, sid: str) -> str | None:
    """The clip a section of the source form became when the clips were made (the implicit one's id), if the
    arrangement still has it."""
    from .composition import section_ids

    form = value["form"]
    ids = section_ids(form)
    if sid not in ids:
        return None
    k = ids.index(sid)
    clip = f"{base(form[k])}{FIRST + k}"
    spec = value["clips"].get(clip)
    return clip if spec is not None and spec.get("from") == sid and clip in value["order"] else None


# ---------------------------------------------------------------- checked on the way in


def _whole(value, what: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) \
            or not lo <= int(value) <= hi:
        raise ValueError(f"{what} is a whole number from {lo} to {hi}")
    return int(value)


def check(genome, value) -> dict | None:
    """A clip arrangement, cleaned, or why it can't be sung (ValueError). None gives the song its form back."""
    from . import composition

    if value is None:
        return None
    if not isinstance(value, dict) or not {"form", "order", "clips"} <= set(value) <= {"form", "order", "clips", "next"}:
        raise ValueError("clips are a form, an order and the clips it names")
    try:
        form = composition.order(genome, value["form"])
    except ValueError as e:
        raise ValueError(f"the clips' source form can't be sung: {e}") from None
    ids = composition.section_ids(form)
    order = value["order"]
    if not isinstance(order, list) or not 1 <= len(order) <= MAX_INSTANCES:
        raise ValueError(f"a song has 1 to {MAX_INSTANCES} clips in its order")
    specs = value["clips"]
    if not isinstance(specs, dict) or len(specs) > MAX_CLIPS:
        raise ValueError(f"a song has at most {MAX_CLIPS} clips")
    numbers = [int(m.group(2)) for c in specs for m in [ID.fullmatch(str(c))] if m]
    nxt = value.get("next", max(numbers, default=FIRST - 1) + 1)
    nxt = _whole(nxt, "the next clip's number", FIRST, LAST + 1)
    clean: dict = {}
    for clip in order:
        if not isinstance(clip, str) or clip not in specs:
            raise ValueError(f"the order names a clip the arrangement hasn't got: {clip!r}")
    total = 0
    for clip in dict.fromkeys(order):  # clips the order doesn't name are left out
        match = ID.fullmatch(clip)
        if match is None or not FIRST <= int(match.group(2)) < nxt:
            raise ValueError(f"{clip!r} isn't a clip's name: a section's name and a number from {FIRST}")
        spec = specs[clip]
        if not isinstance(spec, dict) or not set(spec) <= {"from", "role", "sung", "lines", "label"}:
            raise ValueError(f"the {clip} is from a section, or a blank one with its role, and its lines")
        out: dict = {}
        if spec.get("from") is not None:
            sid = spec["from"]
            if sid not in ids:
                raise ValueError(f"the {clip} is from {sid!r}, which the source form hasn't got")
            if "role" in spec or "sung" in spec:
                raise ValueError(f"the {clip} sings its section; only a blank clip has a role of its own")
            name = form[ids.index(sid)]
            if base(name) != match.group(1):
                raise ValueError(f"a clip from the {name} is named {base(name)}, then its number")
            out["from"] = sid
            own = len(genome.section(name).phrases)
        else:
            role = spec.get("role")
            if role not in ROLES:
                raise ValueError(f"a blank clip is an {', '.join(ROLES[:-1])} or {ROLES[-1]}")
            if role != match.group(1):
                raise ValueError(f"a blank {role} is named {role}, then its number")
            sung = spec.get("sung", False)
            if not isinstance(sung, bool):
                raise ValueError("a blank clip is sung (true) or played (false)")
            if "lines" not in spec:
                raise ValueError("a blank clip needs its lines")
            out.update(role=role, sung=sung)
            own = 0
        bars = 0
        if "lines" in spec:
            lines = spec["lines"]
            if not isinstance(lines, list) or not 1 <= len(lines) <= MAX_LINES:
                raise ValueError(f"a clip has 1 to {MAX_LINES} lines")
            kept = []
            for i, line in enumerate(lines):
                if isinstance(line, dict) and set(line) == {"of"} and own:
                    k = _whole(line["of"], f"line {i + 1}'s line of its section", 0, own - 1)
                    kept.append({"of": k})
                    bars += genome.phrases[genome.section(form[ids.index(out["from"])]).phrases[k]].bars
                elif isinstance(line, dict) and set(line) == {"bars"}:
                    n = _whole(line["bars"], f"line {i + 1}'s bars", 1, LINE_BARS)
                    kept.append({"bars": n})
                    bars += n
                else:
                    raise ValueError(f"line {i + 1} is a line of its section ({{\"of\": 0}}) or a blank line "
                                     f"({{\"bars\": 2}})" if own else f"line {i + 1} is a blank line ({{\"bars\": 2}})")
            out["lines"] = kept
        else:
            bars = sum(genome.phrases[p].bars for p in genome.section(form[ids.index(out["from"])]).phrases)
        if bars > CLIP_BARS:
            raise ValueError(f"a clip is at most {CLIP_BARS} bars; the {clip} has {bars}")
        if "label" in spec:
            label = spec["label"]
            if not isinstance(label, str) or len(" ".join(label.split())) > LABEL or any(ord(c) < 32 for c in label):
                raise ValueError(f"a clip's label is plain text of at most {LABEL} characters")
            if label.strip():
                out["label"] = " ".join(label.split())
        total += bars * order.count(clip)
        clean[clip] = out
    if total > SONG_BARS:
        raise ValueError(f"a song is at most {SONG_BARS} bars; these clips make {total}")
    return {"form": list(form), "order": list(order), "clips": clean, "next": nxt}


# ---------------------------------------------------------------- the song the clips make


@dataclass(frozen=True)
class Clips:
    """What a genome made from clips knows of them (Genome.clips)."""

    base: object  # the song's own genome
    value: dict  # the arrangement, checked
    lyrics: object = None  # the words for the resolved form (arrange.Lyrics), once resolved with them


_SONGS: dict = {}  # (the song, the arrangement) -> the genome they make, a few kept: one object each


def _lines_of(genome, value: dict, clip: str) -> list:
    """A clip's lines: (tune line id, the source line it sings, or None for a blank line's), in order."""
    from .composition import section_ids

    spec = value["clips"][clip]
    lines = spec.get("lines")
    if spec.get("from") is None:
        return [(f"{clip}-{i}", None) for i in range(len(lines))]
    form = value["form"]
    own = genome.section(form[section_ids(form).index(spec["from"])]).phrases
    if lines is None:
        return [(pid, k) for k, pid in enumerate(own)]
    return [(own[line["of"]], line["of"]) if "of" in line else (f"{clip}-{i}", None) for i, line in enumerate(lines)]


def song(genome, value: dict):
    """The genome a clip arrangement makes: the song's own, with a section for each clip (its source section's
    lines, lyric block and choir, or a blank clip's) and a tune line for each blank line (a rest as long as it is,
    the key's I chord in each bar). The same arrangement gives the same object back."""
    from .genome import Phrase, Section, TuneNote

    key = (id(genome), json.dumps(value, sort_keys=True))
    held = _SONGS.get(key)
    if held is not None and held[0] is genome:
        return held[1]
    from .composition import section_ids

    form = value["form"]
    sections, phrases = dict(genome.sections), dict(genome.phrases)
    bar = genome.meter.bar
    for clip, spec in value["clips"].items():
        lines = _lines_of(genome, value, clip)
        for i, (pid, of) in enumerate(lines):
            if of is None:
                bars = spec["lines"][i]["bars"]
                phrases[pid] = Phrase(pid, "", (TuneNote(None, 0, 0, bars * bar),), bars, (("I",),) * bars)
        if spec.get("from") is not None:
            source = genome.section(form[section_ids(form).index(spec["from"])])
            block, choir = source.lyrics, source.choir
        else:
            block = SUNG_BLOCKS.get(spec["role"], "verse") if spec["sung"] else None
            choir = spec["role"] in ("bridge", "tag") and any(s.choir for s in genome.sections.values())
        sections[clip] = Section(clip, tuple(pid for pid, _ in lines), block, choir, clip=True)
    out = replace(genome, sections=sections, phrases=phrases, clips=Clips(genome, value))
    if len(_SONGS) >= 32:
        _SONGS.pop(next(iter(_SONGS)))
    _SONGS[key] = (genome, out)
    return out


def words(info: Clips, src_lyrics, src_form, free=frozenset()):
    """The words for the resolved form (arrange.Lyrics): each clip's lines its source section's as these words
    sing them (src_lyrics, for the source form; free: its lines of their own count, composition.own_places), a
    blank line's empty."""
    from .arrange import Lyrics, Sung

    genome, value = info.base, info.value
    from .composition import section_ids

    drawn = src_lyrics.lines_for(genome, src_form, free) if src_lyrics is not None else [None] * len(src_form)
    ids = section_ids(src_form)
    sections = []
    for clip in value["order"]:
        spec = value["clips"][clip]
        lines = _lines_of(genome, value, clip)
        if spec.get("from") is not None:
            block = genome.section(src_form[ids.index(spec["from"])]).lyrics
            if not block:
                continue
            source = drawn[ids.index(spec["from"])]
            sung = () if source is None else tuple(source[of] if of is not None else "" for _, of in lines)
        elif spec["sung"]:
            block = SUNG_BLOCKS.get(spec["role"], "verse")
            sung = tuple("" for _ in lines)
        else:
            continue
        sections.append(Sung(clip, block, clip, {}, sung))
    leanings = getattr(src_lyrics, "leanings", None)
    return Lyrics(tuple(value["order"]), None, tuple(sections), leanings)


def held_words(genome, params):
    """The words a resolved song sings (Genome.clips.lyrics), or, for a song made from clips without them, the ones
    its source form's held words make (composition.held_lyrics)."""
    info = genome.clips
    if info.lyrics is not None:
        return info.lyrics
    from .composition import held_lyrics

    form = tuple(info.value["form"])
    return words(info, held_lyrics(info.base, replace(params, form=form)), form)


_RESOLVED: dict = {}


def resolved(genome, params, lyrics=None):
    """(genome, params, lyrics) as the clips make them: one song whose form is the clips' order, everything a
    person wrote kept by the clip, the words each clip's. What was given, unchanged, without a clip arrangement
    (or for a song already resolved)."""
    value = stored(params)
    if value is None or getattr(genome, "clips", None) is not None:
        return genome, params, lyrics
    if tuple(params.form) != tuple(value["form"]):  # a form changed under the clips: the song's own, as sung
        return genome, params, lyrics
    key = (id(genome), params.digest, id(lyrics), json.dumps(lyrics.to_dict(), sort_keys=True) if lyrics else None)
    held = _RESOLVED.get(key)
    if held is not None and held[0] is genome and held[1] is lyrics:
        return held[2]
    from . import arrange, composition

    shaped = song(genome, value)
    form = tuple(params.form)
    src = lyrics if lyrics is not None else arrange.seed_lyrics(genome, form)
    sung = words(shaped.clips, src, form, composition.own_places(genome, params, src))
    composed = _keyed(genome, params, value, src)
    out = (replace(shaped, clips=replace(shaped.clips, lyrics=sung)),
           replace(params, form=tuple(value["order"]), composition=composed), sung)
    composition.harmonized(out[0], out[1])  # (made once, as the consumers ask for it)
    if len(_RESOLVED) >= 16:
        _RESOLVED.pop(next(iter(_RESOLVED)))
    _RESOLVED[key] = (genome, lyrics, out)
    return out


def _keyed(genome, params, value: dict, src_lyrics) -> dict:
    """The composition as the resolved song keys it: without the arrangement itself; a person's lines kept by the
    source's verse or round (and a record's by place) sung in the clip that section became, under the clip's own;
    and a linked repeat's tune, chords, parts and arrangement its first instance's, where it has none of its own."""
    from .composition import lyric_keys, section_ids

    held = {k: v for k, v in params.composition.items() if k not in ("clips", "lyrics")}
    form = tuple(value["form"])
    keys = lyric_keys(genome, form, src_lyrics)
    placed = params.composition.get("lyrics") or {}
    for kind in ("lines", "own"):
        mine = {k: dict(v) for k, v in (held.get(kind) or {}).items()}
        for k, sid in enumerate(section_ids(form)):
            clip = home(value, sid)
            if clip is None or (not keys[k] and not placed.get(sid)):
                continue
            source = dict(placed.get(sid, {})) if kind == "lines" else {}
            source.update((held.get(kind) or {}).get(keys[k], {}) if keys[k] else {})
            if not source:
                continue
            here = {}
            for j, (_, of) in enumerate(_lines_of(genome, value, clip)):
                if of is not None and str(of) in source:
                    here[str(j)] = source[str(of)]
            mine[f"{clip}:0"] = {**here, **mine.get(f"{clip}:0", {})}
        mine = {k: v for k, v in mine.items() if v}
        if mine:
            held[kind] = mine
        else:
            held.pop(kind, None)
    repeats = {c: n for c in value["order"] for n in [value["order"].count(c)] if n > 1}
    if repeats:
        held = _linked(held, repeats)
    return held


def _linked(held: dict, repeats: dict) -> dict:
    """A linked repeat's own entries, its first instance's where it has none (repeats: {clip: instances})."""
    out = dict(held)
    for kind in ("tune", "chords", "melisma"):
        now = dict(out.get(kind) or {})
        for key in list(now):
            clip, _, rest = key.partition(":")
            nth, _, line = rest.partition(".")
            if clip in repeats and nth == "0":
                for n in range(1, repeats[clip]):
                    now.setdefault(f"{clip}:{n}.{line}", now[key])
        if now:
            out[kind] = now
    parts = {p: dict(lines) for p, lines in (out.get("parts") or {}).items()}
    for lines in parts.values():
        for key in list(lines):
            sid, _, line = key.rpartition(".")
            clip, _, nth = sid.partition(":")
            if clip in repeats and nth == "0":
                for n in range(1, repeats[clip]):
                    lines.setdefault(f"{clip}:{n}.{line}", lines[key])
    if parts:
        out["parts"] = parts
    arranged = {k: v for k, v in (out.get("arrange") or {}).items()}
    for sid in list(arranged):
        clip, _, nth = sid.partition(":")
        if clip in repeats and nth == "0":
            for n in range(1, repeats[clip]):
                arranged.setdefault(f"{clip}:{n}", arranged[sid])
    if arranged:
        out["arrange"] = arranged
    return out


def claimed(genome, value: dict, composition: dict, sound: dict) -> tuple[dict, dict]:
    """A composition and sound design as the clips keep them: each entry kept under a section of the source form
    (arrange.verse:1, part.fiddle.verse:1.2, tune.refrain:last.1, transition.verse:1) moved to the clip that
    section became, its line to the clip's line that sings it; one whose clip has gone stays where it was,
    unheard. The same dicts where there is nothing to move."""
    from .composition import section_ids

    form = value["form"]
    ids = section_ids(form)
    last = {name: f"{name}:{form.count(name) - 1}" for name in form}

    def clip_line(sid: str, line: str) -> str | None:
        clip = home(value, sid)
        if clip is None or not line.isdigit():
            return None
        for j, (_, of) in enumerate(_lines_of(genome, value, clip)):
            if of == int(line):
                return f"{clip}:0.{j}"
        return None

    def place(key: str) -> str | None:  # name:n.j or name:last.j, of the source form
        sid_, _, line = key.rpartition(".")
        name, _, which = sid_.partition(":")
        sid = last.get(name) if which == "last" else f"{name}:{which}"
        return clip_line(sid, line) if sid in ids else None

    out = dict(composition)
    for kind in ("tune", "chords", "melisma"):
        held = out.get(kind) or {}
        if any(":" in k and place(k) for k in held):
            out[kind] = {(place(k) or k) if ":" in k else k: v for k, v in held.items()}
    parts = out.get("parts") or {}
    if any(place(k) for lines in parts.values() for k in lines):
        out["parts"] = {p: {(place(k) or k): v for k, v in lines.items()} for p, lines in parts.items()}
    arranged = out.get("arrange") or {}
    if any(sid in ids and home(value, sid) for sid in arranged):
        out["arrange"] = {(f"{home(value, sid)}:0" if sid in ids and home(value, sid) else sid): v
                          for sid, v in arranged.items()}
    moved = dict(sound)
    transitions = sound.get("transitions") or {}
    if any(sid in ids and home(value, sid) for sid in transitions):
        moved["transitions"] = {(f"{home(value, sid)}:0" if sid in ids and home(value, sid) else sid): v
                                for sid, v in transitions.items()}
    return out, moved



# ---------------------------------------------------------------- for the editor


def labels(genome, form) -> list[str] | None:
    """What the page calls each section of a song made from clips: a clip's own label, else its role and its
    number among the clips of that role ("Verse 2"); a linked repeat's its clip's, "again". None for any other song."""
    if getattr(genome, "clips", None) is None:
        return None
    from .band import _role

    value, seen, named, out = genome.clips.value, {}, {}, []
    for clip in form:
        if clip in named:
            out.append(f"{named[clip]} again")
            continue
        role = _role(clip, genome.section(clip))
        seen[role] = seen.get(role, 0) + 1
        total = len({c for c in form if _role(c, genome.section(c)) == role})
        named[clip] = value["clips"][clip].get("label") or (
            role.title() + (f" {seen[role]}" if total > 1 else ""))
        out.append(named[clip])
    return out


def _authored(params, clip: str, sids: list[str]) -> bool:
    """Whether a person wrote anything on a clip: words, notes, chords, parts, its arrangement or a transition."""
    held = params.composition
    prefixes = tuple(f"{s}." for s in sids) + tuple(f"{s}:" for s in sids if ":" not in s)
    keys = [k for kind in ("lines", "own", "tune", "chords", "melisma", "arrange") for k in (held.get(kind) or {})]
    keys += [k for lines in (held.get("parts") or {}).values() for k in lines]
    keys += list((getattr(params, "sound", None) or {}).get("transitions") or {})
    return any(k in sids or k.startswith(prefixes) or k.startswith(f"{clip}-") for k in keys)


def view(genome, params) -> dict:
    """The song's clips as the editor reads them: the arrangement as it is stored (or would be, the form's own
    without one), and each clip with its id, label, role, source, whether it is sung, its bars and lines, where
    it comes (its sections' indexes), whether a person wrote on it, and what can be done with it (true, or why
    not)."""
    from .band import _role
    from .composition import section_ids

    value = arrangement(params)
    is_stored = stored(params) is not None
    shaped = song(genome, value) if is_stored else None
    ids = section_ids(value["form"])
    names = labels(shaped, value["order"]) if shaped is not None else None
    def line_bars(c: str) -> list[int]:
        return [genome.phrases[p].bars if p in genome.phrases else value["clips"][c]["lines"][i]["bars"]
                for i, (p, _) in enumerate(_lines_of(genome, value, c))]

    bars_of = {c: sum(line_bars(c)) for c in value["clips"]}
    total = sum(bars_of[c] for c in value["order"])
    room = len(value["order"]) < MAX_INSTANCES
    out = []
    for k, (clip, spec) in enumerate(value["clips"].items()):
        source = spec.get("from")
        section = genome.section(value["form"][ids.index(source)]) if source else None
        role = _role(source.split(":")[0], section) if source else spec["role"]
        where = [i for i, c in enumerate(value["order"]) if c == clip]
        sids = [f"{clip}:{n}" for n in range(len(where))] + [f"{clip}:0", f"{clip}:last"]
        if not is_stored:
            sids = [source]
        label = names[where[0]] if names else (spec.get("label") or genome_label(value["form"], ids.index(source)))
        more = total + bars_of[clip] <= SONG_BARS
        out.append({
            "id": clip, "label": label, "role": role, "source": source,
            "sung": bool(section.lyrics) if section is not None else spec["sung"],
            "bars": bars_of[clip], "lines": [{"phrase": p, "of": of, "bars": n}
                                             for (p, of), n in zip(_lines_of(genome, value, clip), line_bars(clip))],
            "instances": where, "authored": _authored(params, clip, sids),
            "can": {"delete": True if len(value["order"]) > 1 else "a song needs one clip",
                    "duplicate": True if room and len(value["clips"]) < MAX_CLIPS and value["next"] <= LAST and more
                    else "the song has as many clips as it can",
                    "repeat": True if room and more else "the song has as many clips as it can"}})
    return {"value": value, "stored": is_stored, "clips": out, "roles": list(ROLES),
            "bounds": {"instances": MAX_INSTANCES, "clips": MAX_CLIPS, "lines": MAX_LINES, "line_bars": LINE_BARS,
                       "clip_bars": CLIP_BARS, "song_bars": SONG_BARS, "label": LABEL}}


def genome_label(form, k: int) -> str:
    """A section of a form as the page names it: Verse 2, Bridge 2 (as composition.view does)."""
    name = form[k]
    label = name.replace("bridge2", "Bridge 2").title()
    if list(form).count(name) > 1:
        label += f" {list(form[:k]).count(name) + 1}"
    return label


def sung_form(params) -> tuple:
    """The form as sung: the clips' order (what resolved() lays out), else the form."""
    value = stored(params)
    if value is not None and tuple(params.form) == tuple(value["form"]):
        return tuple(value["order"])
    return tuple(params.form)


# ---------------------------------------------------------------- edit paths


_SECTIONED = re.compile(r"(?:tune|chords|lyrics|line|transition|arrange)\.([A-Za-z][A-Za-z0-9_-]{0,31})[:-]"
                        r"|part\.[a-z][a-z0-9-]{0,31}\.([A-Za-z][A-Za-z0-9_-]{0,31}):")


def section_of(path: str) -> str | None:
    """The section an edit path names (a clip's, a blank line's clip), or None for a path that names none."""
    match = _SECTIONED.match(path)
    if match is None:
        return None
    return match.group(1) or match.group(2)


def clip_of(path: str) -> str | None:
    """The clip an edit path names (verse102 in tune.verse102:0.1, part.kit.verse102:0.0, chords.verse102-0), or
    None."""
    name = section_of(path)
    return name if name is not None and ID.fullmatch(name) else None


def refusal(genome, path: str) -> str | None:
    """Why an edit can't be kept in a song made from clips (genome: resolved, or song()'s): it names a clip the song
    hasn't got, or a section of the source form by its place there, which a clip now holds. None where it can (a
    lyric line kept by its verse still sings in its clip; a tune line everywhere is every clip's), and for any
    other song."""
    info = getattr(genome, "clips", None)
    name = section_of(path)
    if info is None or name is None or name in info.value["clips"] or path.startswith(("lyrics.", "line.")):
        return None
    if ID.fullmatch(name):
        return f"this song has no clip called {name}"
    rest = path.split(".", 2)[2] if path.startswith("part.") else path.split(".", 1)[1]
    sid = rest.split(".", 1)[0]
    which = sid.partition(":")[2]
    if which == "last":
        which = str(info.value["form"].count(name) - 1)
    clip = home(info.value, f"{name}:{which}")
    return f"the song is in clips: name its clip, {clip}" if clip else "the song is in clips, and none is that section"


# ---------------------------------------------------------------- the editor's operations


def _place_path(value: dict, path: str) -> str:
    """An edit path that names a section of the source form by its place (tune.refrain:last.1, part.kit.verse:1.0,
    arrange.verse:1.kit.level, transition.verse:1) named for the clip that section is in an implicit arrangement
    (its lines the section's own); any other path as it is."""
    name = section_of(path)
    if name is None or name in value["clips"] or path.startswith(("lyrics.", "line.")):
        return path
    head, rest = (path.split(".", 2)[0] + "." + path.split(".", 2)[1] + ".", path.split(".", 2)[2]) \
        if path.startswith("part.") else (path.split(".", 1)[0] + ".", path.split(".", 1)[1])
    sid, dot, tail = rest.partition(".")
    nth = sid.partition(":")[2]
    if nth == "last":
        nth = str(value["form"].count(name) - 1)
    clip = home(value, f"{name}:{nth}")
    return f"{head}{clip}:0{dot}{tail}" if clip else path


def _rewritten(value: dict, edits: dict) -> dict:
    """The edits of a version without clips as the same edits on its implicit clips: a place's tune, chords,
    parts, arrangement and transitions named for their clip; the shape's edits left out (the clips' source form
    is the shape they made)."""
    out = {}
    for path, v in edits.items():
        if path.startswith("form."):
            continue
        out[_place_path(value, path)] = v
    return out


def _own_notes(genome, entry: dict) -> list[dict]:
    """A line of its own's kept notes (composition.pack_own) as the edit writes them, in beats."""
    beat = genome.meter.beat
    turns = entry.get("melisma") or {}
    out = []
    for k, (d, onset, length, *rest) in enumerate(entry["tune"]):
        offs = [(float(off), int(deg)) for deg, off in turns.get(str(k), ())]
        ends = [off for off, _ in offs] + [length]
        out.append({"degree": int(d), "onset": onset / beat, "duration": ends[0] / beat,
                    **({"alter": int(rest[0])} if rest and rest[0] else {})})
        for j, (off, deg) in enumerate(offs):
            out.append({"degree": deg, "onset": (onset + off) / beat, "duration": (ends[j + 1] - off) / beat,
                        "slur": True})
    return out


def _copied(genome, params, lyrics, clip: str, new: str) -> dict:
    """Everything a person wrote on a clip (its first instance's, as the version sings it), as edits on another:
    its words, lines of their own, a place's tune and chords, its blank lines' chords, players' notes and its
    arrangement."""
    from .composition import phrase_value

    song_, heard, _ = resolved(genome, params, lyrics)
    held = heard.composition
    out: dict = {}
    own = held.get("own", {}).get(f"{clip}:0", {})
    for i, text in held.get("lines", {}).get(f"{clip}:0", {}).items():
        if i not in own:
            out[f"lyrics.{new}:0.{i}"] = text
    for i, entry in own.items():
        out[f"line.{new}:0.{i}"] = {"words": entry["words"], "notes": _own_notes(genome, entry)}
    for key in held.get("tune") or {}:
        if key.startswith(f"{clip}:0."):
            out[f"tune.{new}:0.{key.rsplit('.', 1)[1]}"] = phrase_value(song_, heard, None, place=key)
    for key, bars in (held.get("chords") or {}).items():
        if key.startswith(f"{clip}:0."):
            out[f"chords.{new}:0.{key.rsplit('.', 1)[1]}"] = [list(b) for b in bars]
        elif key.startswith(f"{clip}-"):
            out[f"chords.{new}-{key.rsplit('-', 1)[1]}"] = [list(b) for b in bars]
    for player, lines in (held.get("parts") or {}).items():
        for key, notes in lines.items():
            if key.startswith(f"{clip}:0."):
                out[f"part.{player}.{new}:0.{key.rsplit('.', 1)[1]}"] = [list(n) for n in notes]
    entry = (held.get("arrange") or {}).get(f"{clip}:0") or {}
    for field, v in entry.items():
        if field == "players":
            for player, cell in v.items():
                for f, x in cell.items():
                    out[f"arrange.{new}:0.{player}.{f}"] = x
        else:
            out[f"arrange.{new}:0.{field}"] = v
    return out


def _at(op: dict, key: str, default: int, top: int) -> int:
    at = op.get(key, default)
    return _whole(at, f"the place in the order ({key})", 0, top)


def operate(genome, params, lyrics, edits: dict, op: dict) -> dict:
    """One of the editor's operations on a version's clips (params, lyrics: the version as sung; edits: the page's
    edits that made it), as the whole edits map it leaves: {"edits": ..., "clip": the clip it made, or None}.
    The first operation on a song without clips makes its implicit ones, its edits for places named for them.
    Raises ValueError with why, for an operation that can't be done."""
    import copy

    kinds = "duplicate, repeat, delete, blank, empty, move, lines or label"
    if not isinstance(op, dict) or not isinstance(op.get("op"), str):
        raise ValueError(f"an operation on the clips is {kinds}")
    value = copy.deepcopy(arrangement(params))
    edits = dict(edits or {})
    if stored(params) is None:
        edits = _rewritten(value, edits)
    order, specs = value["order"], value["clips"]
    kind, made = op["op"], None

    def named() -> str:
        clip = op.get("clip")
        if clip not in specs:
            raise ValueError(f"this song has no clip called {clip}")
        return clip

    def fresh(name: str) -> str:
        if value["next"] > LAST:
            raise ValueError("the song has made as many clips as it can")
        clip = f"{name}{value['next']}"
        value["next"] += 1
        return clip

    if kind == "duplicate":
        clip = named()
        made = fresh(base(clip))
        specs[made] = copy.deepcopy(specs[clip])
        order.insert(_at(op, "at", len(order) - order[::-1].index(clip), len(order)), made)
        edits.update(_copied(genome, params, lyrics, clip, made))
    elif kind == "repeat":
        clip = named()
        order.insert(_at(op, "at", len(order) - order[::-1].index(clip), len(order)), clip)
    elif kind == "delete":
        k = _at(op, "at", -1, len(order) - 1)
        if len(order) == 1:
            raise ValueError("a song needs one clip")
        clip = order.pop(k)
        if clip not in order:
            specs.pop(clip)
            edits = {p: v for p, v in edits.items() if clip_of(p) != clip}
    elif kind in ("blank", "empty"):
        role = op.get("role")
        if role not in ROLES:
            raise ValueError(f"a blank clip is an {', '.join(ROLES[:-1])} or {ROLES[-1]}")
        sung = op.get("sung", role in ("verse", "refrain", "bridge", "tag"))
        if "line_bars" in op:
            if not isinstance(op["line_bars"], list):
                raise ValueError("line_bars is a list of each line's bars")
            bars = [_whole(b, "a line's bars", 1, LINE_BARS) for b in op["line_bars"]]
        else:
            n = _whole(op.get("lines", 1), "the clip's lines", 1, MAX_LINES)
            total = _whole(op.get("bars", 2 * n), "the clip's bars", n, min(CLIP_BARS, n * LINE_BARS))
            bars = [total // n + (1 if k < total % n else 0) for k in range(n)]
        made = fresh(role)
        if kind == "empty":  # the song this one clip: every other goes, with the edits that name it
            gone = set(specs)
            order.clear()
            specs.clear()
            edits = {p: v for p, v in edits.items() if clip_of(p) not in gone}
        specs[made] = {"role": role, "sung": bool(sung), "lines": [{"bars": b} for b in bars]}
        order.insert(_at(op, "at", len(order), len(order)), made)
    elif kind == "label":
        clip = named()
        label = op.get("label")
        if label is None or (isinstance(label, str) and not label.strip()):
            specs[clip].pop("label", None)
        else:
            specs[clip]["label"] = label  # (checked below)
    elif kind == "move":
        k = _at(op, "from", 0, len(order) - 1)
        order.insert(_at(op, "to", k, len(order) - 1), order.pop(k))
    elif kind == "lines":
        clip = named()
        if op.get("lines") is None:
            if specs[clip].get("from") is None:
                raise ValueError("a blank clip needs its lines")
            specs[clip].pop("lines", None)
        else:
            specs[clip]["lines"] = op["lines"]
    else:
        raise ValueError(f"an operation on the clips is {kinds}")
    edits["clips"] = check(genome, value)
    return {"edits": edits, "clip": made}
