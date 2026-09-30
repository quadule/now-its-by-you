"""Sound design: a person's choice of each player's sound, its channel, and what happens at a section boundary.

docs/SOUND-DESIGN.md. The edits (songbird.edits calls this module for each; a player's *pattern*, what it
plays, is the arrangement's, never this module's):

    sound.<player>.patch       a patch for the player's synth (PATCHES), null: the program's own
    sound.<player>.cutoff      Hz, the synth's ladder at its reference note; .resonance 0..1; .envelope octaves
    sound.<player>.kit         a drum player's kit (808, 909, lofi, acoustic)
    sound.<player>.kick        {"tune": semitones, "decay": times}; .snare also "snappy"; .hat {"decay"}
    mix.<player>.pan           -1..1, in place of the player's own place
    mix.<player>.send          0..3 times the channel's designed send to the room
    mix.<player>.sidechain     a preset (subtle, classic, heavy) or {depth dB, release beats, key, sections}
    transition.<section-id>    {riser, down, roll: bars; stop: beats; impact: bool; sweep: {bars, type}}, into it

They live in Params.sound ({"players": {player: {...}}, "transitions": {section-id: {...}}}), recorded,
handed down and replayed like the composition. realize() calls produce(): the drum player's roll strokes go
into the notes, and the score's `sound` carries what the synthesis needs (each player's sound, the sidechain's
key track, the transitions, all in seconds). With no sound design every function here gives back what it was
given, and nothing else changes.
"""

from __future__ import annotations

import math
import re

from . import composition

SOUND = re.compile(r"sound\.([a-z][a-z0-9-]*)\.(patch|cutoff|resonance|envelope|kit|kick|snare|hat)")
CHANNEL = re.compile(r"mix\.([a-z][a-z0-9-]*)\.(pan|send|sidechain)")
TRANSITION = re.compile(r"transition\.([a-z][a-z0-9]*):(\d+)")
MAX_OCCURRENCE = 48

# ---------------------------------------------------------------- the catalog

# Each patch in plain words, by the synth it's for (the program's own first; synth.analog.PATCHES, chip.PATCHES).
PATCHES = {
    "synth-bass": {
        "analog": "two saws and a square an octave down through a snappy filter: the synth bass as it always was",
        "sub": "a sine with a touch of its octave, every note starting alike: felt more than heard",
        "reese": "two saws a little apart, beating slowly, through a closed filter, held: a dark, moving bass",
        "pluck": "a saw and a pulse whose filter snaps shut: short, round notes",
    },
    "synth-solo": {
        "saw": "two saws and a square an octave up, a delayed vibrato: the lead as it always was",
        "square": "a square and a thinner pulse an octave down: hollow, like a clarinet",
        "supersaw": "seven saws spread wide, the filter open: the big trance lead",
    },
    "synth-pad": {
        "warm": "a slowly moving pulse and two saws through a warm filter and a chorus: the pad as it always was",
        "glass": "a narrow pulse and a saw an octave up through a ringing filter, slow to rise: bright and clear",
        "wide": "the pad's saws further apart and its chorus twice as deep: wider and thicker",
    },
    "synth-arp": {
        "pluck": "a saw and a pulse whose filter snaps shut: the arpeggio as it always was",
        "bell": "a saw with a pulse an octave and a fifth up, a ringing filter, gone in half a second: a bell",
    },
    "chip": {
        "own": "the pulse's width as the band's brightness picks it: the chip as it always was",
        "thin": "a 12.5% pulse: thin and nasal",
        "reedy": "a 25% pulse: bright and reedy",
        "hollow": "a square: hollow",
    },
}
FILTERED = ("synth-bass", "synth-solo", "synth-pad", "synth-arp")  # the synths with a ladder a person may turn
FILTER = {"cutoff": (40.0, 16000.0, 0), "resonance": (0.0, 1.0, 2), "envelope": (0.0, 6.0, 2)}  # range, digits

# The kits: which module plays, and its settings' "kit" (the lofi machine is the 808's).
KITS = {"808": ("drums-808", None), "909": ("drums-909", None), "lofi": ("drums-808", "lofi"),
        "acoustic": ("kit", None)}
KIT_ABOUT = {"808": "the Roland TR-808: a booming kick, a ticking hat, a clap",
             "909": "the Roland TR-909: a tight punchy kick, a cracking snare, sampled cymbals",
             "lofi": "the 808 soft and worn, its top rolled off: a dusty, sampled kit",
             "acoustic": "a drum kit played by a drummer: sticks on skins and cymbals"}
OWN_KIT = {"drums-808": "808", "drums-909": "909", "kit": "acoustic"}
MACHINES = ("drums-808", "drums-909")
PIECES = {"kick": ("tune", "decay"), "snare": ("tune", "decay", "snappy"), "hat": ("decay",)}
PIECE_RANGES = {"tune": (-12.0, 12.0), "decay": (0.25, 4.0), "snappy": (0.0, 2.0)}

PAN = (-1.0, 1.0)
SEND = (0.0, 3.0)
PRESETS = {  # the sidechain's: dB, beats to come back, what keys it
    "subtle": {"depth": 4.0, "release": 0.35, "key": "kick"},
    "classic": {"depth": 8.0, "release": 0.55, "key": "kick"},
    "heavy": {"depth": 14.0, "release": 0.85, "key": "kick"},
}
KEYS = ("kick", "beat")
DEPTH = (0.0, 24.0)
RELEASE = (0.1, 2.0)
ATTACK = 0.003  # s: how fast a pumped channel ducks

PRESETS["off"] = {"depth": 0.0, "release": 0.55, "key": "kick"}  # no pump, over a style's own (house's pumps)
BARS = (0, 1, 2, 4)
SWEEP_TYPES = ("highpass", "lowpass", "open")  # open: a low-pass rising (2026-09-30)
SWEEP_KINDS = {"highpass": "sweep-hp", "lowpass": "sweep-lp", "open": "sweep-open"}
TRANSITION_KEYS = ("riser", "roll", "sweep", "stop", "impact", "down")  # a stop in beats, the rest in bars
BEFORE = ("riser", "roll", "sweep", "stop")  # over the bars before the section: nothing comes before the first
IMPACT_S = 1.6  # s an impact's span lasts
RISER_LEVEL = 1.0

# The band's drum player, in idioms' own order for a count-in: the one whose kick keys a sidechain and plays a roll.
DRUMMERS = ("kit", "drummachine", "claps", "stomps", "cajon", "drum")
ROLL_STROKE = {"kit": "snare", "drummachine": "snare", "cajon": "cajon-slap", "drum": "tip", "claps": "clap"}
KICKS = ("kick", "kick-dead", "bd", "bass-drum", "bassdrum", "kick-drum", "cajon-bass", "stomp")
KEPT_UNDER_A_ROLL = ("hat", "ride", "shaker", "maracas", "mute")  # a roll's bars keep the kick and the time


def owns(path: str) -> bool:
    """Whether an edit's path is sound design's."""
    return bool(SOUND.fullmatch(path) or CHANNEL.fullmatch(path) or TRANSITION.fullmatch(path))


def synth_of(player: str) -> str | None:
    """The module's name for the instrument a player is (synthbass: synth-bass, drummachine: drums-808), or None."""
    from .synth import instruments

    try:
        own, found = instruments.registered(player)
    except Exception:  # noqa: BLE001 - an unknown player has no module
        return None
    return own if found is not None else None


def patches_of(player: str) -> list[str]:
    return list(PATCHES.get(synth_of(player) or "", {}))


def kits_of(player: str) -> list[str]:
    return list(KITS) if synth_of(player) in OWN_KIT else []


def own_patch(player: str) -> str | None:
    names = patches_of(player)
    return names[0] if names else None


def own_kit(player: str) -> str | None:
    return OWN_KIT.get(synth_of(player) or "")


def is_kick(player: str, art: str) -> bool:
    a = (art or "").split(":")[0].strip().lower()
    return a in KICKS or (a == "bass" and player in ("drum", "drummachine"))


# ---------------------------------------------------------------- checking a value


def _number(value, lo: float, hi: float, digits: int) -> float:
    if isinstance(value, bool):
        raise ValueError("not a number")
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("not a number")
    x = round(min(hi, max(lo, x)), digits)
    return int(x) if digits == 0 else x


def _known(player: str) -> None:
    from .synth.instruments import known

    if player not in known():
        raise LookupError(f"there's no player called {player}")


def _player_name(player: str) -> str:
    from .explain import player as named

    return named(player)


def check(genome, path: str, value):
    """A sound, channel or transition edit's value made canonical (fixed keys in a fixed order, numbers held to
    their ranges and rounded, a preset spelled out), None to give the choice back to the program; LookupError
    or ValueError with why it can't be."""
    m = SOUND.fullmatch(path)
    if m:
        player, what = m.groups()
        _known(player)
        if value is None:
            return None
        if what == "patch":
            options = patches_of(player)
            if not options:
                raise LookupError(f"{_player_name(player)} has no patches to choose from")
            if value not in options:
                raise LookupError(f"{_player_name(player)}'s patches are {', '.join(options)}")
            return value
        if what in FILTER:
            if synth_of(player) not in FILTERED:
                raise LookupError(f"{_player_name(player)} has no filter to turn")
            lo, hi, digits = FILTER[what]
            return _number(value, lo, hi, digits)
        if what == "kit":
            if value not in kits_of(player):
                raise LookupError(f"{_player_name(player)} has no kits to choose from" if not kits_of(player)
                                  else f"the kits are {', '.join(KITS)}")
            return value
        if not kits_of(player):  # kick, snare, hat
            raise LookupError(f"{_player_name(player)} has no {what} to change")
        if not isinstance(value, dict):
            raise ValueError(f"the {what}'s character is a map of {', '.join(PIECES[what])}")
        unknown = set(value) - set(PIECES[what])
        if unknown:
            raise ValueError(f"the {what} has {', '.join(PIECES[what])}, not {', '.join(sorted(unknown))}")
        out = {k: _number(value[k], *PIECE_RANGES[k], 2) for k in PIECES[what] if value.get(k) is not None}
        return out or None
    m = CHANNEL.fullmatch(path)
    if m:
        player, what = m.groups()
        _known(player)
        if value is None:
            return None
        if what == "pan":
            return _number(value, *PAN, 2)
        if what == "send":
            return _number(value, *SEND, 2)
        return sidechain(genome, value)
    m = TRANSITION.fullmatch(path)
    if m:
        name, n = m.group(1), int(m.group(2))
        try:
            section = genome.section(name)
        except KeyError:
            raise LookupError(f"there is no section called {name}") from None
        if section.name != name and name != "bridge2":
            raise LookupError(f"there is no section called {name}")
        if n >= MAX_OCCURRENCE:
            raise LookupError(f"a section comes at most {MAX_OCCURRENCE} times")
        return transition(value)
    raise LookupError("there's no such choice")


def sidechain(genome, value) -> dict:
    """A sidechain spelled out: {"depth": dB, "release": beats, "key": "kick" or "beat", "sections": [...] or
    None}, from a preset's name or a map (anything left out the classic preset's)."""
    if isinstance(value, str):
        if value not in PRESETS:
            raise LookupError(f"the sidechain's presets are {', '.join(PRESETS)}")
        return {**PRESETS[value], "sections": None}
    if not isinstance(value, dict):
        raise ValueError("a sidechain is a preset's name or a map of depth, release, key and sections")
    unknown = set(value) - {"preset", "depth", "release", "key", "sections"}
    if unknown:
        raise ValueError(f"a sidechain has depth, release, key and sections, not {', '.join(sorted(unknown))}")
    base = PRESETS.get(value.get("preset") or "classic")
    if base is None:
        raise LookupError(f"the sidechain's presets are {', '.join(PRESETS)}")
    key = value.get("key") or base["key"]
    if key not in KEYS:
        raise LookupError("a sidechain is keyed on the kick or on every beat")
    sections = value.get("sections")
    if sections is not None:
        if not isinstance(sections, list) or not sections or len(sections) > MAX_OCCURRENCE:
            raise ValueError("name the sections as a list")
        for token in sections:
            name, _, n = str(token).partition(":")
            try:
                genome.section(name)
            except KeyError:
                raise LookupError(f"there is no section called {name}") from None
            if n and (not n.isdigit() or int(n) >= MAX_OCCURRENCE):
                raise LookupError(f"there is no section {token}")
        sections = sorted({str(t) for t in sections})
    return {"depth": _number(value.get("depth", base["depth"]), *DEPTH, 1),
            "release": _number(value.get("release", base["release"]), *RELEASE, 2),
            "key": key, "sections": sections}


def transition(value) -> dict | None:
    """A transition spelled out, in TRANSITION_KEYS' order, with only what happens (bars 1, 2 or 4; an impact
    true); None if nothing does."""
    if value is None:
        return None
    if value is False:  # nothing here, not even the style's own (a house drop's riser and roll)
        return False
    if not isinstance(value, dict):
        raise ValueError("a transition is a map of riser, roll, sweep, stop, impact and down")
    unknown = set(value) - set(TRANSITION_KEYS)
    if unknown:
        raise ValueError(f"a transition has {', '.join(TRANSITION_KEYS)}, not {', '.join(sorted(unknown))}")
    out: dict = {}
    for key in TRANSITION_KEYS:
        v = value.get(key)
        if v is None or v is False:
            continue
        if key == "impact":
            if not isinstance(v, bool):
                raise ValueError("an impact is there or not (true or false)")
            out[key] = True
            continue
        kind = "highpass"
        if key == "sweep" and isinstance(v, dict):
            if set(v) - {"bars", "type"}:
                raise ValueError("a sweep has bars and type")
            kind = v.get("type", "highpass")
            if kind not in SWEEP_TYPES:
                raise LookupError("a sweep is a highpass (rising) or a lowpass (falling)")
            v = v.get("bars", 0)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v not in BARS:
            raise ValueError(f"a {key} lasts {', '.join(str(b) for b in BARS[1:])} {'beats' if key == 'stop' else 'bars'}")
        if v:
            out[key] = {"bars": int(v), "type": kind} if key == "sweep" else int(v)
    return out or None


# ---------------------------------------------------------------- into the program's table


def in_band(band, player: str) -> bool:
    """Whether a band has this player (sitting out or not): its lineup when a style set one, else the eight."""
    from .band import INSTRUMENTS, Band

    band = band if isinstance(band, Band) else Band.from_dict(dict(band or {}))
    return player in band.lineup if band.lineup else player in INSTRUMENTS


def pin(genome, out: dict, edits: dict) -> tuple[list[str], list[dict]]:
    """The sound edits into the table's working dict (out["sound"], from the parent's), each checked against
    the band and the form it now has: (the paths that took effect, why the others couldn't). Idempotent: the
    table calls it after each of its decisions, and the last call's band and form are the version's."""
    from .edits import Problem

    edits = {p: v for p, v in edits.items() if SOUND.fullmatch(p) or CHANNEL.fullmatch(p) or TRANSITION.fullmatch(p)}
    if not edits:
        return [], []
    held = dict(out.get("sound") or {})
    players = {k: dict(v) for k, v in (held.get("players") or {}).items()}
    transitions = dict(held.get("transitions") or {})
    applied, problems = [], []
    ids = composition.section_ids(out.get("form") or ())
    first = ids[0] if ids else None
    for path, value in edits.items():
        m = SOUND.fullmatch(path) or CHANNEL.fullmatch(path)
        if m:
            player, what = m.groups()
            if not in_band(out.get("band"), player):
                problems.append(Problem(path, "this version's band has no such player"))
                continue
            mine = players.setdefault(player, {})
            if value is None:
                mine.pop(what, None)
            else:
                mine[what] = value
            if not mine:
                players.pop(player, None)
            applied.append(path)
            continue
        sid = path.split(".", 1)[1]
        if value is not None and sid not in ids:
            problems.append(Problem(path, "this version doesn't sing that section"))
            continue
        if value and sid == first and any(k in value for k in BEFORE):
            problems.append(Problem(path, "the song begins there: nothing comes before it to build from "
                                          "(an impact or a downlifter can)"))
            continue
        if value is None:
            transitions.pop(sid, None)
        else:
            transitions[sid] = value
        applied.append(path)
    sound = {}
    if players:
        sound["players"] = {k: {w: v[w] for w in sorted(v)} for k, v in sorted(players.items())}
    if transitions:
        sound["transitions"] = {k: transitions[k] for k in sorted(transitions)}
    if sound:
        out["sound"] = sound
    else:
        out.pop("sound", None)
    return applied, problems


def value_of(params, path: str):
    """What the program has at a path in these parameters (a parent's choice among them): for the record's
    "was" and the page's "program"."""
    sound = getattr(params, "sound", None) or {}
    m = SOUND.fullmatch(path) or CHANNEL.fullmatch(path)
    if m:
        player, what = m.groups()
        held = merged_players(params).get(player, {}).get(what)  # a style's own sound under a person's
        if held is not None:
            return held
        if what == "patch":
            return own_patch(player)
        if what == "kit":
            return own_kit(player)
        if what == "pan":
            return place_of(player)
        if what == "send":
            return 1.0
        return None
    m = TRANSITION.fullmatch(path)
    return (sound.get("transitions") or {}).get(path.split(".", 1)[1]) if m else None


def place_of(player: str) -> float:
    from .synth import instruments

    try:
        return float(instruments.spec(player)["place"][0])
    except (ValueError, KeyError):
        return 0.0


# ---------------------------------------------------------------- into the score


def shifted(sound: dict, start: float, stop: float) -> dict:
    """A score's sound design for the stretch from `start` to `stop` s, moved so `start` is zero (a section's
    preview, studio.cut): the triggers inside it; every transition that reaches into it, whole (its span may
    begin before zero: synth.sweeps makes all of it and keeps what falls inside)."""
    out = {k: v for k, v in sound.items() if k not in ("triggers", "transitions", "throws")}
    triggers = [[round(t - start, 6), p] for t, p in sound.get("triggers") or () if start <= t < stop]
    if triggers:
        out["triggers"] = triggers
    throws = [{**t, "start": t["start"] - start, "end": t["end"] - start} for t in sound.get("throws") or ()
              if start <= t["start"] and t["end"] <= stop]  # a throw whose moment the preview plays
    if throws:
        out["throws"] = throws
    transitions = []
    for t in sound.get("transitions") or ():
        if t["end"] > start and t["start"] < stop:
            moved = {**t, "start": t["start"] - start, "end": t["end"] - start}
            if "hits" in t:
                moved["hits"] = [[h - start, v] for h, v in t["hits"]]
            transitions.append(moved)
    if transitions:
        out["transitions"] = transitions
    return out


RENDER = ("patch", "cutoff", "resonance", "envelope", "kit", "kick", "snare", "hat", "pan")


def produce(genome, params, placed, clock, notes: list, desk: dict | None = None) -> tuple[list, dict]:
    """The score's sound design, for realize(): the notes with a roll's strokes in them (the drum player's own
    snares, claps, rims and toms under the roll left out), and the score's `sound`: each player's sound for
    the synthesis (its patch, filter, kit, pan; its send and sidechain for the mix), the sidechain's key track
    ([seconds, player] for each kick or beat it ducks on), the transitions (their kind, their whole span in
    seconds, level and key) and a dub desk's throws (`desk`: the arranger's, songbird.idioms). A style's own
    sound (StyleDef.sound: house's 909 and pumps) sits under a person's, and its transitions (a drop's riser,
    roll and opening filter) under theirs at each boundary. With none of it, the notes as given and {}."""
    sound = getattr(params, "sound", None) or {}
    asked = merged_players(params)
    moves = style_transitions(genome, params)
    if not sound and not asked and not moves and not (desk or {}).get("throws") and not (desk or {}).get("splashes"):
        return notes, {}
    from .score import Note

    band = params.band
    tempo_beat = 60.0 / params.tempo
    players: dict = {}
    for player, mine in asked.items():
        if not in_band(band, player):  # inherited for a player this band hasn't got: it waits
            continue
        entry = {k: mine[k] for k in RENDER if k in mine}
        if "kit" in mine:
            module, _ = KITS[mine["kit"]]
            entry["role"] = "kit" if module == "kit" else "drum"
        if "send" in mine:
            entry["send"] = mine["send"]
        if "sidechain" in mine and mine["sidechain"]["depth"] > 0:  # a pump turned off pumps nowhere
            sc = mine["sidechain"]
            entry["sidechain"] = {"depth": sc["depth"], "release": round(sc["release"] * tempo_beat, 6),
                                  "attack": ATTACK}
        if entry:
            players[player] = entry
    out: dict = {}
    if players:
        out["players"] = players

    at = composition.beat_clock(clock)
    bar = genome.meter.bar
    windows = composition.line_windows(genome, params, placed, clock.lead)
    ids = composition.section_ids(params.form)
    starts = [windows[f"{sid}.0"][2] for sid in ids if f"{sid}.0" in windows]  # each section's first bar line
    spans = {sid: (starts[k], starts[k + 1] if k + 1 < len(starts) else clock.end) for k, sid in enumerate(ids)
             if k < len(starts)}
    playing = {n.part for n in notes}
    kicking = {n.part for n in notes if n.part in DRUMMERS and is_kick(n.part, n.art)}
    drummer = next((p for p in DRUMMERS if p in kicking), None)  # whose kick keys a sidechain
    roller = next((p for p in DRUMMERS if p in ROLL_STROKE and p in playing), None)  # who plays a roll
    kicks = sorted(n.start for n in notes if n.part == drummer and is_kick(n.part, n.art)) if drummer else []

    # the transitions: a person's at a boundary in place of the style's own there (false: none at all)
    wanted = {**{sid: t for sid, t in moves.items()}, **(sound.get("transitions") or {})}
    made = []
    for k, sid in enumerate(ids):
        want = wanted.get(sid)
        if not want or sid not in spans:
            continue
        u0 = spans[sid][0]
        downbeat = at(u0)
        key = 16 * k

        def span(bars: int, after: bool = False) -> tuple[float, float]:
            return (downbeat, at(u0 + bars * bar)) if after else (max(0.0, at(u0 - bars * bar)), downbeat)

        if want.get("riser"):
            a, b = span(want["riser"])
            made.append({"kind": "riser", "start": a, "end": b, "level": RISER_LEVEL, "key": key + 1})
        if want.get("sweep"):
            a, b = span(want["sweep"]["bars"])
            made.append({"kind": SWEEP_KINDS.get(want["sweep"]["type"], "sweep-lp"),
                         "start": a, "end": b, "level": 1.0, "key": key + 2})
        if want.get("stop"):  # the band stops for the last beats before the section (the singer and fx don't)
            made.append({"kind": "stop", "start": max(0.0, at(u0 - want["stop"] * genome.meter.beat)),
                         "end": downbeat, "level": 1.0, "key": key + 6})
        if want.get("impact"):
            on_kick = any(abs(t - downbeat) < 0.03 for t in kicks)
            made.append({"kind": "impact", "start": downbeat, "end": downbeat + IMPACT_S, "level": 1.0,
                         "key": key + 3, "kick": on_kick})
        if want.get("down"):
            a, b = span(want["down"], after=True)
            made.append({"kind": "down", "start": a, "end": b, "level": 1.0, "key": key + 4})
        if want.get("roll"):
            bars = want["roll"]
            u_start = u0 - bars * bar
            a, b = span(bars)
            beats = bars * bar / genome.meter.beat
            hits = []
            for j in range(int(round(beats))):
                rate = (1, 2, 4, 8)[min(3, int(4 * j / beats))]  # quarters, eighths, sixteenths, thirty-seconds
                for q in range(rate):
                    u = u_start + (j + q / rate) * genome.meter.beat
                    f = (u - u_start) / (bars * bar)
                    t = at(u)
                    if t >= 0.0:
                        hits.append((t, round(0.35 + 0.6 * f, 4)))
            if roller is not None:
                notes = [n for n in notes if not (n.part == roller and a - 1e-6 <= n.start < b - 1e-6
                                                  and not is_kick(n.part, n.art)
                                                  and not any(w in (n.art or "") for w in KEPT_UNDER_A_ROLL))]
                notes += [Note(part=roller, start=t, dur=0.1, pitch=38.0, vel=v, art=ROLL_STROKE[roller])
                          for t, v in hits]
            else:
                made.append({"kind": "roll", "start": a, "end": b, "level": 1.0, "key": key + 5,
                             "hits": [[t, v] for t, v in hits]})
    if made:
        out["transitions"] = made

    # the sidechain's key track: each kick of the drum player (or each beat) in the sections asked, per player
    triggers = []
    beats = None
    for player, mine in sorted(asked.items()):
        sc = mine.get("sidechain")
        if not sc or player not in players or "sidechain" not in players[player]:
            continue
        if sc["key"] == "beat":
            beats = beats if beats is not None else [t for t, _ in clock.beats()]
            times = beats
        else:
            times = kicks
        if sc.get("sections"):
            wanted = [spans[sid] for sid in ids if sid in spans
                      and (sid in sc["sections"] or sid.split(":")[0] in sc["sections"])]
            windows_s = [(at(a) - 1e-3, at(b) - 1e-3) for a, b in wanted]
            times = [t for t in times if any(a <= t < b for a, b in windows_s)]
        last = -1.0
        for t in times:
            if t - last >= 0.03:  # a flam, or a kick doubled by a count-in: one trigger
                triggers.append([round(t, 6), player])
                last = t
    if triggers:
        out["triggers"] = sorted(triggers)
    throws = thrown(params, desk or {})
    if throws:
        out["throws"] = throws
    return notes, out


# ---------------------------------------------------------------- a style's own sound (2026-09-30)
#
# A style may bring a sound of its own (StyleDef.sound: house's 909, its pumping pad and bass) and a habit at its
# boundaries (a drop's riser, roll and opening filter; a filtered intro): the program's, under a person's, path by
# path and boundary by boundary. Nothing for a style that brings none (every style before house and dub).


def _sdef(params):
    from .style import STYLES

    name = getattr(getattr(params, "style", None), "name", "") or ""
    return STYLES.get(name) if name and name != "ballad" else None


def program_players(params) -> dict:
    """The style's own sound for each of its players in this band: {player: {kit, patch, sidechain...}}, each value
    as check() spells it (a pump's preset spelled out), for the player playing the style's part (an organ swapped
    in for the piano takes the piano's)."""
    sdef = _sdef(params)
    if sdef is None or not getattr(sdef, "sound", None):
        return {}
    band = params.band
    out: dict = {}
    for part, fields_ in sorted((sdef.sound.get("players") or {}).items()):
        player = sdef.playing(part, band.lineup) if band.lineup else part
        if not in_band(band, player):
            continue
        entry = {}
        for what, value in sorted(fields_.items()):
            if what == "sidechain":
                value = sidechain(None, value)
            elif what == "kit" and value not in kits_of(player):
                continue
            entry[what] = value
        if entry:
            out[player] = entry
    return out


def merged_players(params) -> dict:
    """Each player's sound as it plays: the style's own, a person's (a parent's among them) over it, field by field."""
    own = program_players(params)
    mine = (getattr(params, "sound", None) or {}).get("players") or {}
    if not own:
        return mine
    out = {p: dict(v) for p, v in own.items()}
    for player, fields_ in mine.items():
        out.setdefault(player, {}).update(fields_)
    return {p: {w: v[w] for w in sorted(v)} for p, v in sorted(out.items())}


def style_transitions(genome, params) -> dict:
    """The style's own transitions, by the section they lead into (as a person's are spelled; a sweep's bars as
    long as the span it covers): a drop (Style.drop) gets a riser over the breakdown's last two bars, a snare roll
    over its last one (two when it is eight bars or more) and the band's low-pass opening across the whole
    breakdown; a style whose sound asks for it opens the same filter across the intro into what follows."""
    style = getattr(params, "style", None)
    if style is None or not params.form:
        return {}
    sdef = _sdef(params)
    drop = int(getattr(style, "drop", 0) or 0)
    if not drop and (sdef is None or (getattr(sdef, "sound", None) or {}).get("intro") != "open"):
        return {}
    ids = composition.section_ids(params.form)
    out: dict = {}
    bars = [sum(genome.phrases[p].bars for p, _ in lines) for lines in _plan(genome, params)]
    if sdef is not None and (getattr(sdef, "sound", None) or {}).get("intro") == "open" and len(ids) > 1 \
            and genome.section(params.form[0]).lyrics is None and params.form[0].startswith("intro"):
        out[ids[1]] = {"sweep": {"bars": bars[0], "type": "open"}}
    refrains = [k for k, name in enumerate(params.form) if genome.section(name).lyrics == "refrain"]
    if 0 < drop < len(refrains):
        before, into = refrains[drop - 1], refrains[drop]
        breakdown = sum(bars[before + 1: into])
        if breakdown > 0:
            out[ids[into]] = {"riser": min(2, breakdown), "roll": 2 if breakdown >= 8 else 1,
                              "sweep": {"bars": breakdown, "type": "open"}}
    return out


def _plan(genome, params):
    from .takeover import phrase_plan

    return phrase_plan(genome, params)


def thrown(params, desk: dict) -> list[dict]:
    """A dub desk's throws into the tape echo and splashes into the spring, for the mix (synth/dub.py): each its
    part, its window in seconds, and the echo's time (the style's, in beats, as seconds), feedback and level."""
    from .style import desk_of

    if not desk:
        return []
    d = desk_of(params)
    beat = 60.0 / params.tempo
    out = []
    for k, (part, start, end) in enumerate(desk.get("throws") or ()):
        out.append({"kind": "echo", "part": part, "start": round(float(start), 6), "end": round(float(end), 6),
                    "time": round(d["time"] * beat, 6), "feedback": d["feedback"],
                    "level": d["voice_level"] if part == "voice" else d["level"], "key": k})
    for k, (part, start, end) in enumerate(desk.get("splashes") or ()):
        out.append({"kind": "spring", "part": part, "start": round(float(start), 6), "end": round(float(end), 6),
                    "level": d["splash_level"], "key": 1000 + k})
    return sorted(out, key=lambda t: (t["start"], t["key"]))


# ---------------------------------------------------------------- for the page

WHAT = {"patch": "sound", "cutoff": "filter's cutoff", "resonance": "filter's resonance",
        "envelope": "filter's envelope", "kit": "kit", "kick": "kick", "snare": "snare", "hat": "hi-hat",
        "pan": "place", "send": "send to the room", "sidechain": "sidechain"}


def label(path: str) -> str:
    """A sound design edit's path in plain words ("the synth bass's sidechain", "what comes into Refrain 2")."""
    m = SOUND.fullmatch(path) or CHANNEL.fullmatch(path)
    if m:
        return f"{_player_name(m.group(1))}'s {WHAT[m.group(2)]}"
    m = TRANSITION.fullmatch(path)
    if m:
        return f"what comes into {section_label(m.group(1), int(m.group(2)))}"
    return path


def section_label(name: str, n: int) -> str:
    from .explain import SECTIONS

    return SECTIONS.get(name, name.title()) + (f" {n + 1}" if name in ("verse", "refrain") else "")


def _filter_of(synth: str, patch: str | None, brightness: float) -> dict | None:
    """The program's own filter for a synth's patch: its cutoff where the band's brightness sets it, its
    resonance, its envelope's amount."""
    from .synth import analog

    preset = analog.PATCHES.get(synth, {}).get(patch or "") if patch else analog.PRESETS.get(synth)
    if not isinstance(preset, dict):
        return None
    return {"cutoff": round(preset["cutoff"] * 2.0 ** (1.6 * (brightness - 0.5))),
            "resonance": round(preset["resonance"], 2), "envelope": round(preset["famount"], 2)}


def view(genome, params, generated, applied, problems, score) -> dict:
    """Every player's sound and channel, and every boundary's transition, as the page shows them: each value
    the one sung, the program's (a parent's choice among it), and whether it is the person's; the choices
    and their ranges; the problems with any of them."""
    from .band import INSTRUMENTS

    band = params.band
    names = list(band.lineup) if band.lineup else list(INSTRUMENTS)
    sound = params.sound or {}
    mine_all = merged_players(params)  # a style's own sound under the person's (house's 909 and pumps)
    moves = style_transitions(genome, params)
    kicking = any(n.part in DRUMMERS and is_kick(n.part, n.art) for n in score.notes)

    def entry(path: str, value, **extra) -> dict:
        return {"path": path, "value": value, "program": value_of(generated, path), "yours": path in applied,
                **extra}

    players = []
    for p in names:
        synth = synth_of(p)
        mine = mine_all.get(p, {})
        out = {"player": p, "name": _player_name(p), "synth": synth, "playing": band.plays(p),
               "gain": {"path": f"band.{p}", "value": round(band.gain(p), 2), "yours": f"band.{p}" in applied}}
        patch = mine.get("patch") or own_patch(p)
        out["patch"] = entry(f"sound.{p}.patch", patch, options=[{"name": k, "about": v}
                                                                 for k, v in PATCHES[synth].items()]) \
            if synth in PATCHES else None
        own_filter = _filter_of(synth, patch, band.brightness) if synth in FILTERED and patch != "sub" else None
        out["filter"] = {k: {**entry(f"sound.{p}.{k}", mine.get(k, own_filter[k])), "patch": own_filter[k],
                             "min": FILTER[k][0], "max": FILTER[k][1]} for k in FILTER} if own_filter else None
        kit = mine.get("kit") or own_kit(p)
        out["kit"] = entry(f"sound.{p}.kit", kit, options=[{"name": k, "about": KIT_ABOUT[k]} for k in KITS]) \
            if kits_of(p) else None
        machine = bool(kits_of(p)) and KITS[kit][0] in MACHINES
        out["pieces"] = {piece: {**entry(f"sound.{p}.{piece}", mine.get(piece)),
                                 "knobs": {k: {"min": PIECE_RANGES[k][0], "max": PIECE_RANGES[k][1],
                                               "own": 0.0 if k == "tune" else 1.0} for k in knobs}}
                         for piece, knobs in PIECES.items()} if machine else None
        out["pan"] = {**entry(f"mix.{p}.pan", mine.get("pan", place_of(p))), "min": PAN[0], "max": PAN[1]}
        out["send"] = {**entry(f"mix.{p}.send", mine.get("send", 1.0)), "min": SEND[0], "max": SEND[1]}
        out["sidechain"] = {**entry(f"mix.{p}.sidechain", mine.get("sidechain")), "presets": PRESETS,
                            "keys": list(KEYS), "has_kick": kicking,
                            "is_key": p in DRUMMERS,  # the drummer keys the pump: it isn't one to duck on itself
                            "depth": {"min": DEPTH[0], "max": DEPTH[1]},
                            "release": {"min": RELEASE[0], "max": RELEASE[1]}}
        players.append(out)
    ids = composition.section_ids(params.form)
    boundaries = []
    for k, sid in enumerate(ids):
        name, n = sid.split(":")
        path = f"transition.{sid}"
        mine = (sound.get("transitions") or {})
        boundaries.append({**entry(path, mine[sid] if sid in mine else moves.get(sid)), "id": sid,
                           "name": section_label(name, int(n)), "from": ids[k - 1] if k else None,
                           "before": k > 0})
    return {"players": players, "boundaries": boundaries,
            "transition": {"bars": list(BARS[1:]), "sweep": list(SWEEP_TYPES), "kinds": list(TRANSITION_KEYS)},
            "problems": [q for q in problems if owns(q["path"])]}
