"""The arrangement taken over: a person's choices, section by section and player by player (docs/ARRANGE.md,
"Taking over the arrangement").

The program arranges every rendition itself: songbird.band (the ballad) and songbird.idioms (every other
style) decide what each player does in each section of the form, from the section's role and energy, the
style's own way and what chance drew for this machine and season (the band joining line by line, a bare verse,
stop-time, the breakdown). That stays the default and stays visible. A person may take any of it over:

    arrange.<section>:<n>.<player>.level     out, soft, plays or hard: in or out, and how hard
    arrange.<section>:<n>.<player>.pattern   what it plays there (an idiom of the player's: four, half, walk...)
    arrange.<section>:<n>.<player>.from      the line it comes in at (0: from the start)
    arrange.<section>:<n>.<player>.fill      a drum fill into the next section, or none (a kit, a drum machine)
    arrange.<section>:<n>.bars               the section's length, 2, 4, 8 or 16 bars, fitted from its tune lines
    arrange.<section>:<n>.sung               false: played, not sung (a drop); its words are still drawn
    arrange.<section>:<n>.build              true: its players fill in bar by bar toward the next section

kept in params.composition["arrange"] ({"verse:0": {"bars": 16, "sung": False, "build": True, "players":
{"kit": {"level": "hard"}}}}), by the arrangement's own section ids as form.order and part.* name them. Absent,
everything is as it was: every function here gives back what it was given.

The program decides first, always: take_over() is called by both arrangers right after their own plan (and the
style's options), keeps what the program decided beside the person's, and puts the person's in its place;
shape() then applies the levels, the late entrances, a build and a played section's tune to the written notes.
"""

from __future__ import annotations

import re
from functools import lru_cache

LEVELS = ("out", "soft", "plays", "hard")  # the page's words for a cell (docs/STUDIO-REDESIGN.md)
BARS = (2, 4, 8, 16)
SECTION_FIELDS = ("bars", "sung", "build")
CELL_FIELDS = ("level", "pattern", "from", "fill")
MAX_SECTIONS = 48  # as composition.MAX_SECTIONS
MAX_LINES = 16  # lines a section can have (a 16-bar section of two-bar lines, or more short ones)
PATH = re.compile(r"arrange\.([A-Za-z][A-Za-z0-9_-]{0,31}):(\d{1,2})\."
                  r"(?:([a-z][a-z0-9-]{0,31})\.)?(bars|sung|build|level|pattern|from|fill)")
# how hard a level plays, against the program's own (1); the section's energy itself doesn't change
LEVEL_VEL = {"soft": 0.8, "plays": 1.0, "hard": 1.15}
# where soft and hard read a style's table: the section's own busyness (songbird.idioms.busy), less or more
LEVEL_SHIFT = {"soft": -0.3, "hard": 0.3}
DRUMS = ("drums", "drum machine")  # the families that play a kit's grooves (songbird.idioms.groove_bar)
FILLED = ("groove", "four", "toms", "half", "machine")  # the grooves that end a section with a fill (w_groove)
# Idioms that play the same as another, offered once: the drum machine's own four on the floor was "machine" until
# 2026-09-30 (idioms.w_machine is w_four); a record, a draft or a lock that says it is read as the one kept.
ALIASES = {"machine": "four", "bodhran": "tipped", "bodhran-light": "tipped-light"}  # (the jig's drum, renamed)
LINES = ("lead", "quote", "counter", "descant", "under", "tone", "double", "hook", "fills")  # idioms.LINES

# The ballad band's players (songbird.band) and what their own writers play
BALLAD = {"bass": ("roots", "walk", "long"), "guitar": ("light", "strum", "ring", "pick"),
          "harp": ("arp", "high", "roll"), "drum": ("light", "pulse", "full", "heart", "end"), "drone": ("hold",),
          "lute": ("fills", "double", "lead", "quote"), "fiddle": ("pad", "counter", "fills", "lead", "quote"),
          "whistle": ("counter", "double", "fills", "lead", "quote")}
# ...and each one's steps from sparest to fullest: soft is a step down from what the program has it play there,
# hard a step up (the ends where it plays nothing there), plays the program's own (the middle where it has none)
BALLAD_STEPS = {"bass": ("long", "roots", "walk"), "guitar": ("ring", "light", "strum"), "harp": ("arp", "high"),
                "drum": ("light", "pulse", "full"), "drone": ("hold",), "lute": ("fills", "double"),
                "fiddle": ("pad", "counter"), "whistle": ("double", "counter")}
# What each family can be asked to play beyond what the styles give it (songbird.idioms.WRITERS)
EXTRAS = {"drums": ("groove", "four", "half", "end", "build"), "drum machine": ("groove", "four", "half", "end", "build"),
          "bass": ("roots", "long", "two", "walk", "eighths"), "keys": ("comp", "arpeggio", "block", "pad", "ring"),
          "organ": ("pad", "swell"), "pad": ("pad", "swell"), "plucked": ("strum", "ring"),
          "mallets": ("bells", "hook"), "bowed": ("counter", "tone", "double", "fills"),
          "blown": ("fills", "descant", "double", "counter"), "reed": ("fills", "counter", "double"),
          "lead": ("fills", "descant", "double", "counter"), "synth": ("arp",),
          "percussion": ()}
PLAYER_EXTRAS = {"synthbass": ("roots", "sub", "eighths", "long"), "synthlead": ("counter", "descant", "fills", "double"),
                 "synthpad": ("pad", "swell"), "sub-bass": ("roots", "sub", "long"), "synth-bass": ("roots", "sub", "eighths"),
                 "stomps": ("stomp", "stomp4"), "claps": ("claps",), "tambourine": ("tambourine",),
                 "shaker": ("shaker",), "cajon": ("cajon",)}
# Each idiom in a person's words (the page's pattern names)
LABELS = {
    "roots": "roots", "long": "held notes", "two": "on one and three", "walk": "a walking line",
    "eighths": "driving eighths", "boogie": "a boogie", "sub": "a round sub", "oom": "oom-pah on the bass",
    "pedal": "a pedal note", "strum": "strummed", "ring": "one strum a chord, left to ring", "boom": "boom-chick",
    "travis": "Travis-picked", "roll": "forward rolls", "claw": "clawhammer", "chop": "a chop on the backbeat",
    "tremolo": "tremolo", "comp": "comping", "arpeggio": "broken chords", "block": "a chord on every beat",
    "oompah": "oom-pah", "pad": "held chords", "swell": "swelling chords", "epiano": "lazy chords", "pulse": "a pulse",
    "arp": "an arpeggio", "box": "a music box's pattern", "bells": "bell notes", "drone": "a drone", "lead": "the tune",
    "quote": "quoting the tune", "counter": "a counter-melody", "descant": "a descant", "under": "a line under the tune",
    "tone": "one held tone a line", "double": "doubling the tune", "hook": "the tune's strong notes, high",
    "fills": "answers between the lines", "groove": "a groove", "brushes": "brushes", "four": "four on the floor",
    "toms": "on the floor toms", "half": "half time", "lofi": "a boom-bap", "machine": "four on the floor (the machine's own)",
    "end": "winding down", "stomp": "stamping on one and three", "stomp4": "stamping every beat",
    "claps": "claps on the backbeat", "tambourine": "tambourine on the backbeat", "shaker": "shaking",
    "cajon": "a cajon's groove", "build": "a build", "light": "lightly", "full": "the full pattern",
    "heart": "a heartbeat", "hold": "a held note", "high": "picking high", "pick": "fingerpicked",
    "tipped": "tipped: down-up-down on each beat", "tipped-light": "tipped, lightly", "dadgad": "strummed in DADGAD",
}


# house's and dub's (2026-09-30; docs/STYLES.md, "House and dub")
LABELS.update({
    "floor": "four on the floor, open hats between", "house": "a house groove: claps on two and four",
    "drop": "the drop: the ride on every beat", "offbeat": "on the off-beats", "rolling": "a rolling bass",
    "stab": "chord stabs", "pluck": "a pluck's figure", "onedrop": "a one drop", "steppers": "steppers: the kick on every beat",
    "dubbass": "the riddim", "skank": "the skank on the off-beats", "bubble": "the organ bubble",
})
FILLED += ("onedrop", "steppers")


def label(player: str, idiom: str) -> str:
    """What a player plays, in the page's words."""
    return PLAYER_LABELS.get((player, idiom)) or LABELS.get(idiom, idiom)
# where one player's idiom has its own name (the ballad's harp picks; its guitar's light is a boom-chick)
PLAYER_LABELS = {("harp", "arp"): "picked chords", ("harp", "high"): "picking high above the tune",
                 ("harp", "roll"): "rolled chords", ("guitar", "light"): "a boom-chick", ("guitar", "pick"): "fingerpicking",
                 ("drum", "light"): "a light pulse", ("drum", "pulse"): "the pulse on the foot",
                 ("drone", "hold"): "a held drone", ("fiddle", "pad"): "long held notes"}
LEVEL_WORDS = {"out": "out", "soft": "soft", "plays": "plays", "hard": "hard"}


# ---------------------------------------------------------------- what can be asked


def arranged(params) -> dict:
    """{section id: {bars, sung, build, players: {player: {level, pattern, from, fill}}}} as these parameters
    carry a person's arrangement ({} for none)."""
    return (getattr(params, "composition", None) or {}).get("arrange") or {}


@lru_cache(maxsize=None)
def style_patterns(player: str) -> tuple[str, ...]:
    """What a player in a style's band can be asked to play: every idiom any style gives it (or the part it
    stands in for), what its family plays, "lead" (the tune) for a pitched player, and for the drums the
    grooves and a build."""
    from .idioms import DEFAULT_PARTS
    from .style import STYLES
    from .synth.instruments import spec

    about = spec(player)
    family = about["family"]
    found: set[str] = set()
    for sdef in STYLES.values():
        for name in (player, sdef.part_of(player)):
            for entry in sdef.parts.get(name, {}).values():
                found.update([entry] if isinstance(entry, str) else [idiom for _, idiom in entry])
    found.update(v for v in DEFAULT_PARTS.get(family, {}).values())
    found.update(EXTRAS.get(family, ()))
    found.update(PLAYER_EXTRAS.get(player, ()))
    if about["register"] is not None and family not in ("bass",) and player not in ("synthbass", "sub-bass",
                                                                                   "synth-bass", "chip-bass"):
        found.add("lead")
    found.discard("")
    return tuple(sorted({ALIASES.get(x, x) for x in found}))


def patterns(player: str, ballad: bool) -> tuple[str, ...]:
    """What a player can be asked to play in this band: the ballad's own writers', or a style's."""
    if ballad:
        return BALLAD.get(player, ())
    return style_patterns(player)


def known_patterns(player: str) -> tuple[str, ...]:
    return tuple(sorted(set(BALLAD.get(player, ())) | set(style_patterns(player))))


def fills_for(player: str) -> bool:
    """Whether a player plays fills a person can ask for or take away: a kit or a drum machine."""
    from .synth.instruments import spec

    return spec(player)["family"] in DRUMS


def tail(genome, own: list[str], bars: int) -> list[str] | None:
    """Tune lines making `bars` bars, the section's last ones kept (its cadence) and repeated backwards from
    there: an eight-bar break of four lines at four bars is its last two, at sixteen its four twice."""
    out: list[str] = []
    left, k = bars, len(own) - 1
    while left > 0:
        pid = own[k % len(own)]
        b = genome.phrases[pid].bars
        if b > left or len(out) >= 64:
            return None
        out.insert(0, pid)
        left -= b
        k -= 1
    return out


def fit(genome, name: str, bars: int | None, sung: bool) -> list[tuple[str, bool]] | None:
    """A section's tune lines at a length, each with whether it is sung: its own, a played section's from its
    last lines (tail), a sung one's lines and then its last lines played again. None where it can't be."""
    own = list(genome.section(name).phrases)
    total = sum(genome.phrases[p].bars for p in own)
    if bars is None or bars == total:
        return [(p, sung) for p in own]
    if not any(genome.phrases[p].sung for p in own):
        return None  # a turn: its tune is a line quoted to fit its own bars
    if sung:
        extra = tail(genome, own, bars - total) if bars > total else None
        return [(p, True) for p in own] + [(p, False) for p in extra] if extra is not None else None
    lines = tail(genome, own, bars)
    return [(p, False) for p in lines] if lines is not None else None


def target(genome, path: str) -> tuple[str, str, str | None, str]:
    """A path's section id, section name, player (None for the section's own fields) and field."""
    match = PATH.fullmatch(path)
    if match is None:
        raise ValueError("an arrangement choice needs its section and which time it comes (verse:1), then a "
                         "player and its level, pattern, from or fill, or the section's bars, sung or build")
    name, nth, player, field = match.groups()
    try:
        genome.section(name)
    except KeyError:
        raise ValueError(f"there is no section called {name}") from None
    if (name not in genome.sections and name != "bridge2") or int(nth) >= MAX_SECTIONS:
        raise ValueError(f"there is no section called {name}")
    if player is None and field in CELL_FIELDS:
        raise ValueError(f"a {field} is a player's: name the player (arrange.{name}:{int(nth)}.drum.{field})")
    if player is not None and field in SECTION_FIELDS:
        raise ValueError(f"the {field} is the section's, not a player's")
    return f"{name}:{int(nth)}", name, player, field


def check(genome, path: str, value):
    """A person's arrangement choice, cleaned, or why it can't be made; None gives it back to the program
    (so does the value that is the program's own shape: sung, no build)."""
    from .synth.instruments import known

    _, name, player, field = target(genome, path)
    if value is None:
        return None
    section = genome.section(name)
    if player is None:
        if field == "bars":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in BARS:
                raise ValueError(f"a section is {', '.join(map(str, BARS[:-1]))} or {BARS[-1]} bars long")
            bars = int(value)
            if fit(genome, name, bars, False) is None and (not section.lyrics or fit(genome, name, bars, True) is None):
                own = sum(genome.phrases[p].bars for p in section.phrases)
                if not any(genome.phrases[p].sung for p in section.phrases):
                    raise ValueError(f"the {name} is a line quoted to fit its {own} bars; its length stays")
                raise ValueError(f"the {name}'s lines can't make {bars} bars")
            return bars
        if not isinstance(value, bool):
            raise ValueError(f"{field} is true or false")
        if field == "sung":
            if not section.lyrics:
                raise ValueError(f"the {name} has no words to sing; it is played already")
            return None if value else False
        return True if value else None  # build
    if player not in known():
        raise ValueError(f"there's no player called {player}")
    if field == "level":
        if value not in LEVELS:
            raise ValueError(f"a player's level is {', '.join(LEVELS[:-1])} or {LEVELS[-1]}")
        return value
    if field == "pattern":
        options = known_patterns(player)
        value = ALIASES.get(value, value)
        if value not in options:
            raise ValueError(f"the {player} plays {', '.join(options) or 'only its own part'}, not {value!r}")
        return value
    if field == "from":
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < MAX_LINES:
            raise ValueError("a player comes in at a line of the section: 0 (from the start), 1, 2...")
        return int(value)
    if not isinstance(value, bool):  # fill
        raise ValueError("a fill is true or false")
    if not fills_for(player):
        raise ValueError(f"only a kit or a drum machine plays fills a person can choose; the {player} doesn't")
    return value


def put(held: dict, path: str, genome, value) -> None:
    """A cleaned choice into a person's arrangement (as params.composition["arrange"] keeps it), in place."""
    sid, _, player, field = target(genome, path)
    entry = held.setdefault(sid, {})
    if player is None:
        if value is None:
            entry.pop(field, None)
        else:
            entry[field] = value
    else:
        players = entry.setdefault("players", {})
        cell = players.setdefault(player, {})
        if value is None:
            cell.pop(field, None)
        else:
            cell[field] = value
        if not cell:
            players.pop(player, None)
        if not players:
            entry.pop("players", None)
    if not entry:
        held.pop(sid, None)


def copy(held: dict) -> dict:
    return {sid: {k: ({p: dict(c) for p, c in v.items()} if k == "players" else v) for k, v in entry.items()}
            for sid, entry in (held or {}).items()}


def value(genome, params, path: str):
    """What a path holds in these parameters: the person's (or the version before's) choice, or the song's own
    shape (its own bars, sung, no build) or "the program's own" for a player."""
    sid, name, player, field = target(genome, path)
    entry = arranged(params).get(sid, {})
    if player is not None:
        held = entry.get("players", {}).get(player, {}).get(field)
        return held if held is not None else "the program's own"
    if field in entry:
        return entry[field]
    if field == "bars":  # its own, as many times round as its style plays it
        from .style import rounds

        return sum(genome.phrases[p].bars for p in genome.section(name).phrases) * rounds(genome, params, name)
    return bool(genome.section(name).lyrics) if field == "sung" else False


def shape_problems(genome, form, held: dict) -> dict[str, str]:
    """The section lengths a person's arrangement (held) can't have with the rest of it: a sung section shorter
    than its lines (made played, it may be). {path: why}."""
    from .composition import section_ids

    out = {}
    names = dict(zip(section_ids(form), form))
    for sid, entry in held.items():
        bars = entry.get("bars")
        name = names.get(sid) or sid.split(":", 1)[0]
        if bars is None or not genome.section(name).lyrics:
            continue
        sung = entry.get("sung", True) is not False
        if fit(genome, name, bars, sung) is None:
            own = sum(genome.phrases[p].bars for p in genome.section(name).phrases)
            out[f"arrange.{sid}.bars"] = (f"a sung {name} is as long as its lines, {own} bars; to shorten it, "
                                          f"have it played rather than sung")
    return out


def sat_out(params, player: str, edits: dict | None) -> bool:
    """The band has this player and the person sat it out (its level at nothing): its cells are kept, silent until
    it plays again, and nothing is wrong with them."""
    from .band import INSTRUMENTS

    has = player in params.band.lineup if params.band.lineup else player in INSTRUMENTS
    level = (edits or {}).get(f"band.{player}")
    return has and isinstance(level, (int, float)) and level <= 0.02


def silent(genome, params, path: str, edits: dict | None = None) -> str | None:
    """Why a person's arrangement choice at this path isn't heard in this version, or None if it is (or it waits,
    unsaid, for a player the person sat out: `edits`, sat_out)."""
    from .composition import section_ids

    sid, name, player, field = target(genome, path)
    ids = section_ids(params.form)
    if sid not in ids:
        return "this version doesn't play that section; the choice waits for one that does"
    entry = arranged(params).get(sid, {})
    if player is None:
        if field == "build" and entry.get("build") and ids.index(sid) == len(ids) - 1:
            return "a build leads into the next section, and this one ends the song"
        return None
    if not params.band.plays(player):
        if sat_out(params, player, edits):
            return None
        return f"this version's band has no {player}; the choice waits for one that has"
    ballad = not params.band.lineup
    cell = entry.get("players", {}).get(player, {})
    if field == "pattern" and ALIASES.get(cell.get("pattern"), cell.get("pattern")) not in patterns(player, ballad):
        return f"this version's {player} doesn't play {LABELS.get(cell.get('pattern'), cell.get('pattern'))}"
    if field == "fill" and ballad:
        return "the ballad band's drum plays no fills"
    if field == "from":
        lines = phrase_plan(genome, params)[ids.index(sid)]
        if cell.get("from", 0) >= len(lines):
            return f"this version's {name} has {len(lines)} lines"
    return None


def part_missing(genome, params, path: str) -> str | None:
    """Why a person's played part (part.*) has no line to be heard in, where a person's arrangement made its
    section shorter or longer than its own lines; None if it has (composition.part_silent says the rest)."""
    from .composition import PART_PATH

    match = PART_PATH.fullmatch(path)
    if match is None or not arranged(params):
        return None
    from .composition import section_ids

    _, name, nth, line = match.groups()
    sid = f"{name}:{int(nth)}"
    ids = section_ids(params.form)
    if sid not in ids:
        return None
    lines = phrase_plan(genome, params)[ids.index(sid)]
    own = list(genome.section(name).phrases)
    if int(line) >= len(lines) or lines[int(line)][0] != own[int(line)]:
        return f"this version's {name} is arranged to other lines; your notes wait for one that plays this line"
    return None


# ---------------------------------------------------------------- where the form falls on the grid


def phrase_plan(genome, params) -> list[list[tuple[str, bool]]]:
    """Each section of the form's tune lines, in order, each with whether it is sung: the section's own (sung
    where it has words) unless a person changed its length or had it played."""
    from .composition import section_ids

    from .style import rounds

    held = arranged(params)
    out = []
    for sid, name in zip(section_ids(params.form), params.form):
        section = genome.section(name)
        sung = section.lyrics is not None
        entry = held.get(sid)
        lines = None
        if entry and (entry.get("bars") is not None or rounds(genome, params, name) == 1):
            lines = fit(genome, name, entry.get("bars"), sung and entry.get("sung", True) is not False)
            if lines is None:  # a length it can't have (said by shape_problems): its own
                lines = fit(genome, name, None, sung and entry.get("sung", True) is not False)
        elif rounds(genome, params, name) > 1:  # the jig's tune round twice: the style's own length, a person's wins
            lines = [(pid, False) for pid in section.phrases] * rounds(genome, params, name)
        out.append(lines if lines is not None else [(pid, sung) for pid in section.phrases])
    return out


def arranged_plan(genome, params) -> list[list[tuple[str, bool]] | None]:
    """phrase_plan() where a person arranged a section of the form, None where the section is its own."""
    from .composition import section_ids

    from .style import rounds

    held = arranged(params)
    twice = [rounds(genome, params, name) > 1 for name in params.form]  # the jig's round twice: its own length
    if not held and not any(twice):
        return [None] * len(params.form)
    return [lines if sid in held or again else None
            for sid, lines, again in zip(section_ids(params.form), phrase_plan(genome, params), twice)]


def phrase_ids(genome, params, k: int | None = None):
    """The tune lines of the k-th section of the form (all of them, in order, with k None)."""
    plan = phrase_plan(genome, params)
    if k is not None:
        return [pid for pid, _ in plan[k]]
    return [pid for lines in plan for pid, _ in lines]


def spans(genome, params, lead: float) -> list[tuple[str, str, float, float]]:
    """Each section of the form as (id, name, first bar line, last bar line) in grid units, as realize lays
    it out (lead: the clock's, from the first pickup to the first bar line)."""
    from .composition import section_ids

    out, u = [], float(lead)
    bar = genome.meter.bar
    for sid, name, lines in zip(section_ids(params.form), params.form, phrase_plan(genome, params)):
        end = u + sum(genome.phrases[pid].bars for pid, _ in lines) * bar
        out.append((sid, name, u, end))
        u = end
    return out


# ---------------------------------------------------------------- in the arrangers (songbird.band, songbird.idioms)
#
# prepare() before the program's plan, take_over() after it (and after the style's options), shape() on the notes
# written. The program's plan runs on its own sections, as it always has: a pair of sections in a row (verses
# in pairs) is one section to it; a pair a person arranged either of is split only afterwards, both halves
# keeping what the program gave the pair, so nothing else in the band moves.


def _entry(ctx, i: int) -> dict:
    """The person's arrangement of the i-th section of the band's layout, where it is one section of the form
    ({} where there is none, or where it is still a pair)."""
    sids = ctx.sids[i] if getattr(ctx, "sids", None) and i < len(ctx.sids) else []
    return arranged(ctx.params).get(sids[0], {}) if len(sids) == 1 else {}


def _mark_played(ctx) -> None:
    for i, s in enumerate(ctx.sections):
        if _entry(ctx, i).get("sung") is False:
            s.sung = False  # no words there: no fills between lines, no backing voices
            s.played = True  # a drop: the band keeps its weight under the lead (band.Context.vel)


def prepare(ctx, lead: float) -> None:
    """Before the band's plan: which sections of the form each of its sections holds (ctx.sids, ctx.spans), and
    a section a person had played marked so. Nothing else, and nothing at all where nobody arranged anything."""
    ctx.spans = spans(ctx.genome, ctx.params, lead)
    ctx.sids = [[o[0] for o in ctx.spans if s.u0 - 1e-9 <= o[2] < s.u1 - 1e-9] for s in ctx.sections]
    if arranged(ctx.params):
        _mark_played(ctx)


def _split(ctx, plan) -> None:
    """A pair of sections in a row that a person arranged either of, split at the boundary: both halves keep the
    pair's role, energy and parts (as the program planned them), its entrances go with the half they fall in,
    stop-time and half-time with both, and no fill lands on the boundary unless a person asks for one."""
    from dataclasses import replace

    held = arranged(ctx.params)
    where = {sid: (a, b) for sid, _, a, b in ctx.spans}
    sections, owner, sids = [], [], []
    for i, s in enumerate(ctx.sections):
        if len(ctx.sids[i]) > 1 and any(sid in held for sid in ctx.sids[i]):
            for sid in ctx.sids[i]:
                sections.append(replace(s, u0=where[sid][0], u1=where[sid][1], parts=dict(s.parts)))
                owner.append(i)
                sids.append([sid])
        else:
            sections.append(s)
            owner.append(i)
            sids.append(ctx.sids[i])
    if len(sections) == len(ctx.sections):
        return
    halves = {i: [j for j, k in enumerate(owner) if k == i] for i in range(len(ctx.sections))}

    def at(i: int, u: float) -> int:
        return next((j for j in halves[i] if sections[j].u0 - 1e-9 <= u < sections[j].u1 - 1e-9), halves[i][0])

    ctx.sections, ctx.sids = sections, sids
    for c in ctx.chords:
        c.section = ctx.section_at(c.u0)
    for t in ctx.tune:
        t.section = ctx.section_at(t.u0)
    taken = ctx.taken
    taken["program"] = [dict(taken["program"][k]) for k in owner]
    taken["from"] = {(at(i, u), p): u for (i, p), u in taken["from"].items()}
    taken["stops"] = {j for i in taken["stops"] for j in halves[i]}
    taken["half"] = {j for i in taken["half"] for j in halves[i]}
    if plan is not None:
        plan.entrances = {(at(i, u), p): u for (i, p), u in plan.entrances.items()}
        plan.stops = {j for i in plan.stops for j in halves[i]}
        plan.half = {j for i in plan.half for j in halves[i]}
    fills = dict(getattr(ctx, "fills", {}))
    for i, js in halves.items():
        for j in js[:-1]:
            fills.update({(j, p): False for p in sections[j].parts})
    ctx.fills = fills
    _mark_played(ctx)


def _ballad(ctx) -> bool:
    return getattr(ctx, "sdef", None) is None


def _family(name: str) -> str:
    from .synth.instruments import spec

    return spec(name)["family"]


def _spec(ctx, i: int, player: str):
    """The style's table entry for a player in a section (as idioms.plan_style reads it)."""
    from .idioms import DEFAULT_PARTS

    sdef, s = ctx.sdef, ctx.sections[i]
    keys = []
    if s.role == "verse" and i == next(k for k, x in enumerate(ctx.sections) if x.role == "verse"):
        keys.append("verse1")
    refrains = [k for k, x in enumerate(ctx.sections) if x.role == "refrain"]
    if s.role == "refrain" and len(refrains) > 1 and i == refrains[-1]:
        keys.append("last")
    if getattr(ctx, "drop", None) and i == ctx.drop[1]:
        keys.insert(0, "drop")  # the refrain after a breakdown (idioms.plan_style)
    keys += [s.role, "*"]
    table = sdef.parts.get(player) or sdef.parts.get(sdef.part_of(player)) or DEFAULT_PARTS.get(_family(player), {})
    return next((table[k] for k in keys if k in table), "")


def _idiom(ctx, i: int, player: str, level: str) -> str:
    """What a player plays at a level a person chose where they didn't choose the pattern: normal, the
    program's own there; soft and hard, what the style gives it with the band a little quieter or fuller
    than here (the ballad's players: a step down or up from the program's); else what it plays elsewhere."""
    program = ctx.taken["program"][i].get(player, "")
    if _ballad(ctx):
        steps = BALLAD_STEPS.get(player, ())
        if not steps or (program and program not in steps):
            return program  # a line or a colour of its own (the tune, a quote, rolled chords, a heartbeat)
        if level == "plays":
            return program or steps[len(steps) // 2]
        if not program:
            return steps[0] if level == "soft" else steps[-1]
        k = steps.index(program) + (-1 if level == "soft" else 1)
        return steps[min(max(k, 0), len(steps) - 1)]
    from .idioms import busy, idiom_of

    spec = _spec(ctx, i, player)
    here = busy(ctx, ctx.sections[i])
    if level == "plays":
        found = program or idiom_of(spec, here)
    else:
        found = idiom_of(spec, here + LEVEL_SHIFT[level]) or program
    if found:
        return found
    elsewhere = [parts.get(player) for parts in ctx.taken["program"] if parts.get(player)]
    if elsewhere:
        return max(sorted(set(elsewhere)), key=elsewhere.count)
    options = [x for x in style_patterns(player) if x not in ("lead", "build", "end")]
    return options[0] if options else ""


def lead_of(ctx, i: int) -> str | None:
    """Who plays the tune where nobody sings it in a section: the band's lead, the next if a person sat it out."""
    rested = {p for p, c in _entry(ctx, i).get("players", {}).items() if c.get("level") == "out"}
    if _ballad(ctx):
        from .band import LEADS

        order = [ctx.band.lead] + [x for x in LEADS if x != ctx.band.lead]
    else:
        from .idioms import PERCUSSION, family

        sdef = ctx.sdef
        order = [sdef.playing(x, ctx.lineup) for x in sdef.leads]
        order += [x for x in ctx.lineup if family(x) not in PERCUSSION + ("bass", "drum machine")]
    return next((p for p in order if ctx.on(p) and p not in rested), None)


def _joining(ctx, i: int, players: list[str]) -> list[str]:
    """The order players come in through a build: the chords first, then the bass, the drums, the rest (as the
    band joins line by line: idioms.shape_plan)."""
    from .style import CHORDS_FIRST

    def rank(p: str) -> tuple:
        family = _family(p)
        return (0 if p in CHORDS_FIRST else 1 if family == "bass" else 2 if family in DRUMS + ("percussion",) else 3, p)

    return sorted(players, key=rank)


def take_over(ctx, plan=None) -> None:
    """After the program's plan (and the style's options, `plan`: idioms.Plan, its entrances, stop-time and
    half-time): what the program decided is kept (ctx.taken, for the page), and a person's arrangement is put
    in its place, section by section and player by player. Nothing changes where nobody arranged anything."""
    ctx.taken = {"program": [dict(s.parts) for s in ctx.sections],
                 "from": dict(plan.entrances) if plan is not None else {},
                 "stops": set(plan.stops) if plan is not None else set(),
                 "half": set(plan.half) if plan is not None else set(),
                 "played": {}, "cells": set(), "build": {}}
    if not arranged(ctx.params):
        return
    if not hasattr(ctx, "sids"):
        return  # an arranger that didn't prepare()
    _split(ctx, plan)
    ballad = _ballad(ctx)
    bar = ctx.meter.bar
    lined = dict(zip([o[0] for o in ctx.spans], phrase_plan(ctx.genome, ctx.params)))
    for i, s in enumerate(ctx.sections):
        if not _entry(ctx, i):
            continue
        # a section played, or the bars a sung one plays after its lines: the lead plays the tune there
        u, played = s.u0, []
        for pid, sung in lined.get(ctx.sids[i][0], []):
            end = u + ctx.genome.phrases[pid].bars * bar
            if not sung:
                played.append((u, end))
            u = end
        if played and not s.sung:
            lead = lead_of(ctx, i)
            if lead is not None and "lead" not in s.parts.values():
                s.parts[lead] = "lead"
        elif played:
            ctx.taken["played"][i] = (played[0][0], played[-1][1])
        ctx.taken["program"][i] = dict(s.parts)
    for i, s in enumerate(ctx.sections):
        entry = _entry(ctx, i)
        cells = entry.get("players", {})
        for player, cell in sorted(cells.items()):
            if not ctx.on(player):
                continue
            level, pattern = cell.get("level"), ALIASES.get(cell.get("pattern"), cell.get("pattern"))
            if pattern not in patterns(player, ballad):
                pattern = None
            if (level or "from" in cell) and plan is not None:
                plan.entrances.pop((i, player), None)
            if level == "out":
                s.parts.pop(player, None)
                continue
            if pattern:
                s.parts[player] = pattern
            elif level:
                what = _idiom(ctx, i, player, level)
                if what:
                    s.parts[player] = what
            if level or pattern:
                ctx.taken["cells"].add((i, player))
            if "fill" in cell and not ballad:
                ctx.fills = {**getattr(ctx, "fills", {}), (i, player): bool(cell["fill"])}
        if entry.get("build") and i < len(ctx.sections) - 1:
            if not ballad:  # the drums play a build (idioms.w_build); the ballad's frame drum keeps its pattern
                for player in list(s.parts):
                    if _family(player) in DRUMS and not cells.get(player, {}).get("pattern"):
                        s.parts[player] = "build"
            joining = _joining(ctx, i, [p for p, what in s.parts.items() if what not in LINES + ("build",)
                                        and "from" not in cells.get(p, {})])
            n = max(1, int(round((s.u1 - s.u0) / bar)))
            for k, player in enumerate(joining):
                at = (k * max(1, n // 2)) // max(len(joining), 1)
                if at:
                    ctx.taken["build"][(i, player)] = s.u0 + at * bar
                    if plan is not None:
                        plan.entrances.pop((i, player), None)


def _starts(ctx, i: int) -> list[float]:
    s = ctx.sections[i]
    return [p0 for p0, _ in ctx.phrases if s.u0 - 1e-9 <= p0 < s.u1 - 1e-9]


def _on_beat(ctx, s, u: float) -> bool:
    x = (u - s.u0) / ctx.beat
    return abs(x - round(x)) < 1e-6


def shape(ctx, events: list) -> list:
    """The person's arrangement on the notes the band wrote (band.Ev), in the order written: a player coming in
    at the line a person chose (or, through a build, at its bar), each level's weight (a soft player keeps
    only its beats), a build rising from soft to full, and the tune played in the bars a sung section plays
    after its lines. The same list where nobody arranged anything."""
    taken = getattr(ctx, "taken", None)
    if not arranged(ctx.params) or taken is None or not hasattr(ctx, "sids"):
        return events
    from .band import statement

    cells: dict[tuple[int, str], dict] = {}
    for i in range(len(ctx.sections)):
        for player, cell in _entry(ctx, i).get("players", {}).items():
            cells[(i, player)] = cell
    starts = dict(taken["build"])
    for (i, player), cell in cells.items():
        k = int(cell.get("from", 0) or 0)
        where = _starts(ctx, i)
        if k and where:
            starts[(i, player)] = where[min(k, len(where) - 1)]
    builds = {i for i in range(len(ctx.sections) - 1) if _entry(ctx, i).get("build")}
    played = taken["played"]
    leads = {i: lead_of(ctx, i) for i in played}
    out = []
    for e in events:
        key = (e.section, e.part)
        if key in starts and e.u0 < starts[key] - 1e-9:
            continue
        if e.section in played and e.part == leads[e.section]:
            a, b = played[e.section]
            if a - 1e-9 <= e.u0 < b - 1e-9:
                continue
        s = ctx.sections[min(max(e.section, 0), len(ctx.sections) - 1)]
        what = s.parts.get(e.part, "")
        level = cells.get(key, {}).get("level")
        if level in LEVEL_VEL:
            if level == "soft" and what not in LINES and not _on_beat(ctx, s, e.u0):
                continue
            e.vel = float(min(1.0, e.vel * LEVEL_VEL[level]))
        if e.section in builds and what != "build":
            x = min(1.0, max(0.0, (e.u0 - s.u0) / max(s.u1 - s.u0, 1e-9)))
            e.vel = float(min(1.0, e.vel * (0.7 + 0.45 * x)))
        out.append(e)
    for i, (a, b) in sorted(played.items()):  # the tune again, after a sung section's lines
        lead = leads[i]
        if lead is None:
            continue
        notes = [t for t in ctx.tune_in(i) if not t.sung and a - 1e-9 <= t.u0 < b - 1e-9]
        mine = statement(ctx, lead, notes, 0.85, i)
        if not _ballad(ctx):
            from .idioms import sliding

            mine = sliding(ctx, lead, mine)
        out += mine
    return out


# ---------------------------------------------------------------- the grid, for the page (docs/STUDIO.md, "Arrangement control")
#
# The version as a timeline draws it: the sections of the form as regions, the band's players as tracks, and in
# each cell what the player does there, how hard, from where, whose choice it is (the program's, the person's,
# or a person's from the version before) and why the program chose what it did, in the page's own words.

# the style's options that belong to one section, and how the page says each
OPTION_WORDS = {"entrances": "the band joins line by line", "breakdown": "the last refrain starts stripped down",
                "stops": "stop-time: the band hits each bar's one and leaves the words bare",
                "alone": "sung bare", "bridge": "the bridge in half time", "intro": "how it starts",
                "drop": "the breakdown before the drop: the singer with the pad, the filter opening into the refrain"}
INTRO_WORDS = {"lead": "an instrument states the tune", "pad": "a pad swells in alone", "count": "a count-in",
               "voice": "the singer begins alone", "quote": "a line of an older song",
               "air": "the tune slow and free, the lead alone", "": "as the form has it"}
# ...and in a style of voices alone (a cappella)
VOICES_INTRO_WORDS = {**INTRO_WORDS, "lead": "the lead hums the tune over the voices' chords",
                      "pad": "the voices' chords swell in alone"}
ROLE_WORDS = {"intro": "the intro", "verse": "a verse", "refrain": "a refrain", "turn": "a turn", "break": "the break",
              "bridge": "the bridge", "tag": "the tag", "outro": "the outro"}


def level_of(busy: float, playing: bool) -> str:
    """How hard the program has a player play, in the grid's four words: from how busy the band is there."""
    if not playing:
        return "out"
    return "soft" if busy < 0.42 else "plays" if busy < 0.72 else "hard"


def _kind(v, option: str) -> str:
    """Whose an option of the style is: the person's, drawn this time (chance, for this machine and season), or
    kept (from the version before, or the song's own)."""
    if f"style.{option}" in v.applied:
        return "you"
    now, base = getattr(v.generated.style, option, None), getattr(v.context.base.style, option, None)
    if now != base:
        return "chance"
    return "parent" if v.context.parent is not None else "song"


def _whose(v, paths: list[str], inherited: bool) -> str:
    if any(p in v.applied for p in paths):
        return "you"
    return "before" if inherited else "program"


def grid(genome, v, heard: dict) -> dict:
    """The version (an explain.Version) as a grid: sections x players, each cell the program's and the person's,
    with the program's reasons; `heard` is what band.overheard() caught of its score (the band's layout)."""
    from . import explain
    from .edits import tempo_range
    from .idioms import busy as busy_of
    from .realize import timeline
    from .style import of as style_of, voices_alone

    params = v.params
    ctx = heard["ctx"]
    taken = getattr(ctx, "taken", None) or {"program": [dict(s.parts) for s in ctx.sections], "from": {},
                                            "stops": set(), "half": set(), "played": {}, "cells": set(), "build": {}}
    clock = timeline(genome, params)
    beat = genome.meter.beat
    ballad = not params.band.lineup
    held, before = arranged(params), arranged(v.generated)
    style = params.style
    sname = style.name or "ballad"
    band_words = explain.STYLE_NAMES.get(sname, sname).split(",")[0]
    everyone = explain.players(params.band, style)
    plan = phrase_plan(genome, params)
    verses = [k for k, n in enumerate(params.form) if genome.section(n).lyrics == "verse"]
    refrains = [k for k, n in enumerate(params.form) if genome.section(n).lyrics == "refrain"]

    def band_index(sid: str) -> int:
        return next(i for i, sids in enumerate(ctx.sids) if sid in sids)

    sections, cells = [], []
    for k, (sid, name, a, b) in enumerate(spans(genome, params, clock.lead)):
        section = genome.section(name)
        entry, was = held.get(sid, {}), before.get(sid, {})
        i = band_index(sid)
        s = ctx.sections[i]
        own = sum(genome.phrases[p].bars for p in section.phrases)
        bars = sum(genome.phrases[p].bars for p, _ in plan[k])
        sung_now = any(sung for _, sung in plan[k])
        played = bool(section.lyrics) and entry.get("sung") is False
        options = sorted({own} | {n for n in BARS if fit(genome, name, n, bool(section.lyrics) and not played)})
        lines, u = [], a
        for j, (pid, sung) in enumerate(plan[k]):
            lines.append({"index": j, "phrase": pid, "sung": sung, "start_beat": (u - clock.lead) / beat})
            u += genome.phrases[pid].bars * genome.meter.bar
        said = []  # the style's options that live here
        if k == 0:
            said.append({"field": "intro", "value": style.intro, "path": "style.intro", "by": _kind(v, "intro"),
                         "text": (VOICES_INTRO_WORDS if voices_alone(v.params) else INTRO_WORDS).get(style.intro, "")})
        if verses and k == verses[0]:
            said.append({"field": "entrances", "value": style.entrances, "path": "style.entrances",
                         "by": _kind(v, "entrances"), "text": OPTION_WORDS["entrances"]})
        if style.stops and len(verses) >= style.stops and k == verses[style.stops - 1]:
            said.append({"field": "stops", "value": style.stops, "path": "style.stops", "by": _kind(v, "stops"),
                         "text": OPTION_WORDS["stops"]})
        if style.alone and len(verses) >= style.alone and k == verses[style.alone - 1]:
            said.append({"field": "alone", "value": style.alone, "path": "style.alone", "by": _kind(v, "alone"),
                         "text": f"sung {'with the ' + explain.player(style.alone_with) + ' alone' if style.alone_with else 'bare'}"})
        if len(refrains) >= 2 and k == refrains[-1]:
            said.append({"field": "breakdown", "value": style.breakdown, "path": "style.breakdown",
                         "by": _kind(v, "breakdown"), "text": OPTION_WORDS["breakdown"]})
        if s.role == "bridge":
            said.append({"field": "bridge", "value": style.bridge, "path": "style.bridge", "by": _kind(v, "bridge"),
                         "text": OPTION_WORDS["bridge"]})
        drop = getattr(ctx, "drop", None)
        if drop and i == drop[0][0] and ctx.sids[i] and ctx.sids[i][0] == sid:  # the breakdown's first section
            said.append({"field": "drop", "value": style.drop, "path": "style.drop", "by": _kind(v, "drop"),
                         "text": OPTION_WORDS["drop"]})
        paths = {f: f"arrange.{sid}.{f}" for f in SECTION_FIELDS}
        title = name.replace("bridge2", "Bridge 2").title()
        if params.form.count(name) > 1:
            title += f" {int(sid.split(':')[1]) + 1}"
        sections.append({
            "index": k, "id": sid, "name": name, "label": title, "role": s.role, "energy": round(s.energy, 3),
            "bars": bars, "bar_options": options, "own_bars": own, "sung": sung_now, "can_play": bool(section.lyrics),
            "build": bool(entry.get("build")), "lines": lines,
            "start_beat": (a - clock.lead) / beat, "duration_beats": (b - a) / beat,
            "start_seconds": clock.seconds(a), "end_seconds": clock.seconds(b),
            "pair": [x for x in ctx.sids[i] if x != sid], "options": said, "paths": paths,
            "program": {"bars": own, "sung": bool(section.lyrics), "build": False},
            "by": {f: _whose(v, [p], f in was) for f, p in paths.items()},
            "problems": [p for p in v.problems if p["path"].startswith(f"arrange.{sid}.")
                         and p["path"].count(".") == 2],
        })
        starts = [ln["start_beat"] * beat + clock.lead for ln in lines]  # each line's first bar line, in grid units
        for player in everyone:
            cell_now, cell_was = entry.get("players", {}).get(player, {}), was.get("players", {}).get(player, {})
            plays = params.band.plays(player)
            program, enters = _program_cell(ctx, taken, i, player, starts, ballad, plays)
            now = s.parts.get(player, "") if plays else ""
            why = _reasons(v, ctx, i, k, player, program["pattern"] or "", enters, program["from"], band_words,
                           ballad, taken)
            chance = any(r["kind"] == "chance" for r in why)
            mine = [f"arrange.{sid}.{player}.{f}" for f in CELL_FIELDS]
            whose = _whose(v, mine, bool(cell_was))
            locked = whose == "you" and all(program.get(f) == x for f, x in cell_now.items())
            if whose != "program":
                shown = explain.player(player)
                had = label(player, program["pattern"]) if program["pattern"] else "nothing here"
                said = ("locked by you: the program's own, kept" if locked
                        else f"chosen by you; the program had the {shown} play {had}" if whose == "you"
                        else "kept from the version before, where a person chose it")
                why.insert(0, {"kind": "you" if whose == "you" else "lineage", "text": said})
            if entry.get("build") and whose == "program" and now:
                why.insert(0, {"kind": "you", "text": "the section builds, as you chose: the players come in one "
                                                    "after another and it grows louder toward what follows"})
            late = (cell_now.get("from") and starts[min(cell_now["from"], len(starts) - 1)]) \
                or taken["build"].get((i, player)) or (enters if enters is not None and a - 1e-9 <= enters < b else None)
            fills = fills_for(player) and not ballad
            quiet = [{"path": p, "why": said} for p in mine if cell_now.get(p.rsplit(".", 1)[1]) is not None
                     for said in [silent(genome, params, p, v.edits)] if said]
            cells.append({
                "section": sid, "player": player, "plays": plays,
                "value": {"level": cell_now.get("level") or level_of(busy_of(ctx, s), bool(now)), "pattern": now or None,
                          "pattern_label": label(player, now) if now else "out",
                          "from": cell_now.get("from", program["from"]),
                          "fill": cell_now.get("fill") if "fill" in cell_now
                          else (_fills_here(ctx, i, player, now) if fills else None),
                          "enters_beat": ((late - a) / beat) if now and late else 0.0},
                "program": program, "by": whose, "chance": chance, "locked": locked, "why": why,
                "paths": dict(zip(CELL_FIELDS, mine)),
                "problems": [x for x in v.problems if x["path"] in mine] + quiet,
            })
    low, high = tempo_range(genome, style)
    feel = style.feel or next(iter(style_of(style).feels), "straight")
    return {
        "sections": sections,
        "players": [{"name": p, "label": explain.player(p), "family": _family(p), "plays": params.band.plays(p),
                     "patterns": [{"id": x, "label": label(p, x)} for x in patterns(p, ballad)],
                     "fills": fills_for(p) and not ballad} for p in everyone],
        "cells": cells,
        "levels": [{"id": x, "label": LEVEL_WORDS[x]} for x in LEVELS],
        "tempo": {"value": params.tempo, "min": low, "max": high, "song": genome.seed_params["tempo"],
                  "style": band_words, "feel": explain.FEEL_NAMES.get(feel, feel), "by": "you" if "tempo" in v.applied else "program"},
        "problems": [p for p in v.problems if p["path"].startswith(("arrange.", "tempo"))],
    }


def _program_cell(ctx, taken: dict, i: int, player: str, starts: list[float], ballad: bool, plays: bool):
    """What the program has a player do in a section of the band's layout, before any person's choice: its
    level, pattern, the line it comes in at and a fill; and where it comes in (grid units, None from the start)."""
    program = taken["program"][i].get(player, "") if plays else ""
    enters = taken["from"].get((i, player))
    line_in = next((j for j, x in enumerate(starts) if enters is not None and abs(x - enters) < 1e-6), 0)
    from .idioms import busy as busy_of

    fill = _fills_here(ctx, i, player, program, False) if fills_for(player) and not ballad else None
    return ({"level": level_of(busy_of(ctx, ctx.sections[i]), bool(program)), "pattern": program or None,
             "from": line_in, "fill": fill}, enters)


_PROGRAM: dict = {}  # the program's cells for a version's parameters (program_cells), the last few


def program_cells(genome, params) -> dict[tuple[str, str], dict]:
    """The program's own choice in every cell of a version (section id, player) -> {level, pattern, from, fill},
    before any person's: what a record's marks say the program had ("was"), and what a lock keeps. The score
    laid out once (no audio) and kept for the same parameters."""
    import hashlib
    import json

    from .band import INSTRUMENTS, overheard
    from .realize import realize

    key = hashlib.sha256(json.dumps([genome.title, params.to_dict()], sort_keys=True, default=str).encode()).hexdigest()
    if key in _PROGRAM:
        return _PROGRAM[key]
    with overheard() as heard:
        realize(genome, params)
    ctx = heard["ctx"]
    taken = ctx.taken
    ballad = not params.band.lineup
    out: dict = {}
    lines = dict(zip([o[0] for o in ctx.spans], phrase_plan(genome, params)))
    for sid, _, a, _b in ctx.spans:
        i = next(j for j, sids in enumerate(ctx.sids) if sid in sids)
        u, starts = a, []
        for pid, _ in lines[sid]:
            starts.append(u)
            u += genome.phrases[pid].bars * genome.meter.bar
        for player in (list(params.band.lineup) or list(INSTRUMENTS)):
            out[(sid, player)] = _program_cell(ctx, taken, i, player, starts, ballad, params.band.plays(player))[0]
    if len(_PROGRAM) > 32:
        _PROGRAM.clear()
    _PROGRAM[key] = out
    return out


def program_value(genome, params, path: str):
    """The program's own value at a cell's path in this version (program_cells), "out" for a player it has
    playing nowhere there."""
    sid, _, player, field = target(genome, path)
    cell = program_cells(genome, params).get((sid, player))
    if cell is None:
        return {"level": "out", "pattern": None, "from": 0, "fill": None}.get(field)
    return cell.get(field)


def _fills_here(ctx, i: int, player: str, idiom: str, mine: bool = True) -> bool:
    """Whether a kit's or a drum machine's groove ends this section with a fill, as it is (idioms.w_groove)."""
    if idiom not in FILLED or i + 1 >= len(ctx.sections):
        return False
    asked = getattr(ctx, "fills", {}).get((i, player)) if mine else None
    nxt, s = ctx.sections[i + 1], ctx.sections[i]
    return bool(asked) if asked is not None else nxt.energy >= s.energy


def _reasons(v, ctx, i: int, k: int, player: str, program: str, enters, line_in: int, band_words: str,
             ballad: bool, taken: dict) -> list[dict]:
    """Why the program has a player do what it does in a section, in the page's words."""
    from . import explain

    s = ctx.sections[i]
    shown = explain.player(player)
    style = v.params.style
    where = ROLE_WORDS.get(s.role, s.role)
    out = []
    if not v.params.band.plays(player):
        return [{"kind": "rule", "text": f"the {shown} sits out the whole song: its level in the band is at 0"}]
    if not program:
        verses = [j for j, x in enumerate(ctx.sections) if x.role == "verse"]
        if style.alone and len(verses) >= style.alone and i == verses[style.alone - 1]:
            out.append({"kind": _kind(v, "alone"), "text": f"verse {style.alone} is sung "
                        + (f"with the {explain.player(style.alone_with)} alone" if style.alone_with else "bare")})
        elif style.intro == "pad" and i == 0:
            out.append({"kind": _kind(v, "intro"), "text": "a pad swells in alone to begin"})
        elif getattr(ctx, "drop", None) and i in ctx.drop[0]:
            out.append({"kind": _kind(v, "drop"), "text": "the breakdown before the drop: the drums and the bass drop "
                                                          "out, and the singer is left with the pad"})
        else:
            out.append({"kind": "rule", "text": f"{band_words} leaves the {shown} out of {where}"})
        return out
    out.append({"kind": "rule", "text": f"{band_words}: the {shown} plays {label(player, program)} in {where}"})
    busy = "busier" if s.energy >= 0.6 else "quieter" if s.energy < 0.42 else "in between"
    out.append({"kind": "rule", "text": f"the band builds from the first verse to the last refrain; here it is {busy}"})
    if enters is not None and line_in:
        if style.breakdown and s.role == "refrain" and i == max(j for j, x in enumerate(ctx.sections) if x.role == "refrain"):
            out.append({"kind": _kind(v, "breakdown"), "text": f"the last refrain starts stripped down; the {shown} "
                                                              f"comes back at line {line_in + 1}"})
        elif style.intro == "voice" and i == 0:
            out.append({"kind": _kind(v, "intro"), "text": f"the singer begins alone; the {shown} comes in at line 2"})
        else:
            out.append({"kind": _kind(v, "entrances"), "text": f"the band joins line by line; the {shown} comes in "
                                                              f"at line {line_in + 1}"})
    if i in taken["stops"] and program not in LINES:
        out.append({"kind": _kind(v, "stops"), "text": "stop-time: it hits each bar's one with the band"})
    if i in taken["half"] and _family(player) in DRUMS + ("drums", "bass"):
        out.append({"kind": _kind(v, "bridge"), "text": "the bridge in half time"})
    return out
