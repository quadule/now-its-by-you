"""Variation: how a rendition decides what the genome leaves open.

realize.choose_params() brings three things together here: the parent's
parameters (what was inherited), the machine's voice (who is singing) and the
drift (when), plus chance. Every number goes the same way:

1. The machine's own value: read from its voice (see Character); where it
   gave no signal the decision reads, its own value is the parent's, as it
   stood before this machine's day moved it: if this machine made the parent
   (its own last rendition), the day it added then is taken back out, so
   singing its own rendition again never adds its day twice (see centre()).
2. Drift moves the machine's own value: today it is a little brisker, a
   little lower, a little breathier. A drift of 1 moves it by the knob's span.
3. The child pulls from its parent toward that: child = parent + PULL (own
   - parent), so it is 0.4 its parent and 0.6 its machine today, and a
   lineage keeps its accent. A body (the singer's register, tract, mouth,
   vibrato rate and grain; the instruments' size and maker; the room and
   the recording's wear) is the machine's own outright.

Choices a number can't express (mode, form, accompaniment, choir, the
band's pattern and lead, lyric leanings) follow the same logic in DECISIONS;
the band's two categories are held against flicker (see held()). Chance, seeded by (voice hash,
instant, parent), sets only the rendition's seed, which colours every detail
of the sound and the lyric's draws; the form and the key never depend on the
second a render starts, so they can't flicker between two renders a minute
apart.

To add a knob: give Params (or VoiceParams, the band's Band or the mix's
MixParams) the field, then add one row to KNOBS reading the machine through
Character and time through a dimension of drift.DIMENSIONS.
"""

from __future__ import annotations

import collections
import functools
import hashlib
import json
import re
import threading
from dataclasses import dataclass, replace

import numpy as np
from typing import Callable

from . import evolve
from .band import INSTRUMENTS, Band
from .drift import DIMENSIONS, Drift, series
from .drift import drift as field_at
from .genome import Genome
from .harvest import MODE_FAMILIES, THEMES, Voice
from .synth.mixing import MixParams
from .synth.voice import VoiceParams
from .theory import MODES, chord_tones

PULL = 0.6  # how far a child moves from its parent toward its machine: the plan's 0.4 parent, 0.6 voice
CHOIR_MAX = 6  # the most lineage voices that join in (synth.CHOIR_PANS has places for six)


def clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


GENOMES_REMEMBERED = 16  # the songs per_genome keeps answers for: a studio opens other people's versions too


def per_genome(fn):
    """Remember fn(genome, ...) for the genome objects asked about most lately (a genome never changes, and a
    year of choices asks the same things daily); the answers for a genome no one has asked about in a while
    are let go, and the genome with them."""
    memo: collections.OrderedDict = collections.OrderedDict()  # id(genome) -> (genome, {args: answer})
    lock = threading.Lock()

    @functools.wraps(fn)
    def remembered(genome, *args):
        with lock:
            entry = memo.get(id(genome))
            if entry is None or entry[0] is not genome:
                entry = memo[id(genome)] = (genome, {})
                while len(memo) > GENOMES_REMEMBERED:
                    memo.popitem(last=False)
            else:
                memo.move_to_end(id(genome))
            answers = entry[1]
            if args in answers:
                return answers[args]
        answer = fn(genome, *args)
        with lock:
            answers[args] = answer
        return answer

    return remembered


# ---------------------------------------------------------------- the machine, read musically


@dataclass(frozen=True)
class Character:
    """What a voice means for the music: a few traits, each -1..1 with 0 typical.
    `known` names the ones this machine's signals gave; the rest read 0, and a
    decision that reads only unknown traits keeps the parent's value."""

    known: frozenset = frozenset()
    pace: float = 0.0  # unhurried (-) or brisk (+): old files, slow hands
    range: float = 0.0  # how widely its tempo wanders: the spread of its file ages
    wear: float = 0.0  # fresh (-) or worn (+): young or old files
    density: float = 0.0  # sparse (-) or busy (+): cores and memory
    tired: float = 0.0  # rested (-) or tired (+): how long since the machine last restarted
    brightness: float = 0.0  # a dark (-) or light (+) screen
    warmth: float = 0.0  # a cool (-) or warm (+) screen
    lay: float = 0.0  # behind (-) or ahead (+) of the beat: slow or quick hands
    rubato: float = 0.0  # steady (-) or free (+): even or uneven hands
    swing: float = 0.0  # straight (-) or lilting (+): the skew of the hands
    richness: float = 0.0  # a plain (-) or rich (+) vocabulary
    era: float = 0.0  # old-fashioned (-) or new (+) words
    themes: dict | None = None  # theme -> share of the person's common words
    family: str | None = None  # mode family (harvest.MODE_FAMILIES)
    inventory: str | None = None  # phoneme inventory (harvest.INVENTORIES)
    room: dict | None = None  # rt60 and tone
    hash: str = ""

    def id(self, trait: str) -> float:
        """A stable draw in [-1, 1) for a trait no signal explains (a body, a
        habit), from the voice hash; 0 for a neutral voice."""
        if "identity" not in self.known:
            return 0.0
        digest = hashlib.sha256(f"identity|{self.hash}|{trait}".encode()).digest()
        return int.from_bytes(digest[:8], "little") / 2**63 - 1.0


def character(voice: Voice | None) -> Character:
    """The voice's signals as musical traits (docs/HARVEST.md lists each mapping)."""
    if voice is None or voice.neutral:
        return Character()
    known = {"identity"}
    traits: dict = {}
    paces = []
    if voice.ages:
        paces.append(clip((2.3 - voice.ages.median) / 1.2))
        traits["range"] = clip(voice.ages.spread - 1.0)
        traits["wear"] = clip(voice.ages.median - 2.5)
        known |= {"range", "wear"}
    if voice.hand:
        lay = clip((220 - voice.hand.interval) / 120)
        paces.append(lay)
        traits |= {"lay": lay, "rubato": clip((voice.hand.unevenness - 0.45) / 0.3),
                   "swing": clip((voice.hand.skew - 1.0) / 1.5)}
        known |= {"lay", "rubato", "swing"}
    if paces:
        traits["pace"] = sum(paces) / len(paces)
        known.add("pace")
    if voice.machine:
        traits["density"] = clip(voice.machine.cores + voice.machine.memory - 1)
        traits["tired"] = 2 * voice.machine.uptime - 1
        known |= {"density", "tired"}
    if voice.colour:
        traits["brightness"] = 2 * voice.colour.brightness - 1
        traits["warmth"] = voice.colour.warm - voice.colour.cool
        known |= {"brightness", "warmth"}
    if voice.words:
        traits |= {"richness": clip(2 * voice.words.richness - 1), "era": voice.words.era,
                   "themes": dict(voice.words.themes)}
        known |= {"richness", "era", "themes"}
    if voice.tongue:
        traits |= {"family": voice.tongue.family, "inventory": voice.tongue.inventory}
        known |= {"family", "inventory"}
    if voice.room:
        traits["room"] = {"rt60": voice.room.rt60, "tone": list(voice.room.tone)}
        known.add("room")
    return Character(known=frozenset(known), hash=voice.hash, **traits)


def size(c: Character) -> float:
    """The singer's build, -1 big to 1 small: register, tract and comfortable key all follow it, loosely."""
    return c.id("size")


def low(c: Character) -> bool:
    """Whether the machine's singer sings an octave down (half of all machines;
    mostly the bigger ones, but a tenor or a low contralto happens too)."""
    return size(c) + 0.4 * c.id("register") < 0


def comfort(c: Character) -> float:
    """Semitones from the song's own key to where this singer is at ease."""
    return (1.0 if low(c) else -1.0) + 2.0 * size(c) + 0.8 * c.id("comfort")


# ---------------------------------------------------------------- chance


class Chance:
    """The rendition's seed, from (voice hash, instant, parent) or --seed: the
    same machine, instant and parent always give the same child."""

    def __init__(self, voice: Voice | None, drift: Drift | None, parent, seed: int | None = None):
        digest = hashlib.sha256(json.dumps(parent.to_dict(), sort_keys=True).encode()).hexdigest()[:16]
        instant = f"{drift.t:.6f}" if drift is not None else "timeless"
        self.material = f"{voice.hash if voice is not None else 'no-voice'}|{instant}|{digest}"
        self.fixed = seed

    @property
    def seed(self) -> int:
        """Seeds every random choice in the rendition's sound (and the lyric's draws)."""
        if self.fixed is not None:
            return self.fixed
        return int.from_bytes(hashlib.sha256(f"{self.material}|seed".encode()).digest()[:4], "little") % 2**31


# ---------------------------------------------------------------- where a value lives

# The lyric's leanings, named as songbird.arrange.Leanings names them; neutral values. vocabulary is kept
# weighted (word -> weight, an even share of the person's words being 1) so a lineage can remember it;
# leanings() hands arrange the words at VOCABULARY_AT or more.
LEANINGS = {"mood_weights": {"plain": 1.0, "light": 1.0, "dark": 1.0, "tender": 1.0}, "era_bias": 0.0,
            "rarity_appetite": 0.0, "vocabulary": {}}
VOCABULARY_AT = 0.6


def read(params, path: str):
    """A value from Params by path: 'tempo', 'singer.rd', 'mix.rt60', 'leanings.era_bias', 'band.density'.
    A singer, mix or leaning the params don't set has its default; the band always has every field."""
    head, _, tail = path.partition(".")
    if not tail:
        return getattr(params, head)
    held = getattr(params, head)
    if not isinstance(held, dict):  # a dataclass, the band
        return getattr(held, tail)
    if tail in held:
        return held[tail]
    return {"singer": lambda: getattr(VoiceParams(), tail), "mix": lambda: getattr(MixParams(), tail),
            "leanings": lambda: LEANINGS[tail]}[head]()


def write(out: dict, path: str, value) -> None:
    head, _, tail = path.partition(".")
    if tail:
        out.setdefault(head, {})[tail] = value
    else:
        out[head] = value


def exists(path: str) -> bool:
    """Whether a knob's field exists (a singer's or the band's may be gone after it changes)."""
    head, _, tail = path.partition(".")
    return {"singer": lambda: hasattr(VoiceParams(), tail), "band": lambda: hasattr(Band(), tail),
            "mix": lambda: hasattr(MixParams(), tail)}.get(head, lambda: True)()


# ---------------------------------------------------------------- the table of numbers


@dataclass(frozen=True)
class Knob:
    """One number a rendition decides.

    path    where it goes: a Params field, singer.<VoiceParams field>, band.<Band field>,
            mix.<MixParams field>, leanings.<key>
    uses    the traits its own value reads; with none of them known, own is the parent's
            (as it stood before this machine's day moved it: centre())
    own     the machine's own value, from its character c and x, the song's own value
    drift   the drift dimension that moves the machine's own value, and span how far
            a drift of 1 moves it (a fraction of it where ratio); or a tuple of each
    view    which view of the drift: full (daily), slow (weeks), season (months), year (about once a year)
    bounds  (lo, hi), or a function of x
    step    what the value is rounded to
    inherit False for a body: the machine's own value outright, not pulled from the parent
    """

    path: str
    uses: tuple
    own: Callable
    drift: str | tuple | None = None
    span: float | Callable | tuple = 0.0
    ratio: bool = False
    view: str = "full"
    bounds: tuple | Callable = (float("-inf"), float("inf"))
    step: float = 0.001
    inherit: bool = True

    def moved(self, value: float, drift: Drift, c: Character) -> float:
        """A machine's own value as the drift moves it."""
        dims = self.drift if isinstance(self.drift, tuple) else (self.drift,)
        spans = self.span if isinstance(self.span, tuple) else (self.span,)
        for dim, span in zip(dims, spans):
            d = drift.view(self.view).get(dim, 0.0)
            span = span(c) if callable(span) else span
            value = value * (1 + span * d) if self.ratio else value + span * d
        return value

    def reads(self, drift: Drift) -> tuple:
        dims = self.drift if isinstance(self.drift, tuple) else (self.drift,)
        return tuple(drift.view(self.view).get(dim, 0.0) for dim in dims)

    def centre(self, was: float, ctx: Context, x: float | None = None, bounds: tuple | None = None) -> float:
        """Where a machine that knows nothing of its own here starts from: the parent's value as it stood
        before this machine's day moved it. That is the parent's value, unless this machine made the parent
        (ctx.then): then the share of that day the parent heard comes back out, so singing its own rendition
        again gives the same while the field stands and, as the field moves, a field around the same centre,
        never the day added again each time (which walked a quiet machine's own versions up a semitone and
        about 5 BPM a generation to the bounds, until October 7, 2026).

        The day is affine in the value (a shift, or for a ratio a scale), so it comes straight back out. When
        more than one centre fits the parent (a bound cut the day off, or the rounding), the song's own value x
        if it is one of them; else, once the field has moved, a centre on the knob's grid that sings the
        parent's value again (regained), so it comes back exactly each time and the rounding can't wander.
        bounds: those the parent's value was held to, if not the knob's."""
        if ctx.then is None or not self.drift:
            return was
        share = PULL if self.inherit else 1.0
        zero = share * self.moved(0.0, ctx.then, ctx.c)
        slope = 1.0 + share * (self.moved(1.0, ctx.then, ctx.c) - 1.0) - zero
        if slope <= 0:  # (no drift can turn a value round; never divide by it)
            return was
        x = read(ctx.song, self.path) if x is None else x
        lo, hi = bounds or (self.bounds(x) if callable(self.bounds) else self.bounds)
        day = zero + slope * x  # the song's own value, as that day moved it
        if (was <= lo and day <= lo) or (was >= hi and day >= hi) or abs(day - was) <= self.step / 2:
            return x  # the song's own fits the parent (a lineage from the seed, say)
        centre = (was - zero) / slope
        if ctx.drift is not None and self.reads(ctx.drift) == self.reads(ctx.then):
            return centre  # the field hasn't moved since: the parent's value comes straight back
        step = self.step

        def sung(c: float) -> float:  # what the machine sang from c that day
            return round(float(round(clip(zero + slope * c, lo, hi) / step) * step), 6)

        return regained(was, centre, sung, step, even=self.ratio)

    def apply(self, out: dict, ctx: Context) -> None:
        if not exists(self.path):
            return
        x = read(ctx.song, self.path)
        was = read(ctx.parent, self.path)
        if any(u in ctx.c.known for u in self.uses):
            base, own = was, self.own(ctx.c, x)
        else:  # nothing of its own here: the parent's, as it stood before this machine's day moved it
            base = own = self.centre(was, ctx, x)
        machine = own
        if self.drift and ctx.drift is not None:
            own = self.moved(own, ctx.drift, ctx.c)
        raw = base + PULL * (own - base) if self.inherit else own
        lo, hi = self.bounds(x) if callable(self.bounds) else self.bounds
        value = round(float(round(clip(raw, lo, hi) / self.step) * self.step), 6)
        if ctx.trace is not None:  # how the value came to be: the parent's, the machine's own, moved by time
            shown, moved = machine, own
            if base != was:  # its own rendition sung again: no pull of its own, only how far time has moved since
                shown, moved = was, was + (raw - was) / (PULL if self.inherit else 1.0)
            ctx.trace[self.path] = {"was": was, "own": shown, "moved": moved, "value": value, "inherit": self.inherit}
        head, _, tail = self.path.partition(".")
        held = getattr(ctx.parent, head)
        if tail and isinstance(held, dict) and value == was and tail not in held:
            return  # nothing chosen: the default the parent sang with stands
        write(out, self.path, int(value) if self.step >= 1 else value)


# Where each instrument leans when the ensemble drift moves: toward the plucked strings (-1) or the bowed
# and blown (+1).
ENSEMBLE = {"lute": -1.0, "guitar": -1.0, "harp": -1.0, "bass": 0.0, "fiddle": 1.0, "whistle": 1.0, "drum": 0.0,
            "drone": 1.0}

# Own values are read from the machine's character c and x, the song's own
# value of the same knob (its seed parameters; VoiceParams' defaults for the
# singer, Band's for the band). Spans are what a drift of 1 does to the
# machine's own value; a child hears 0.6 of it.
KNOBS = (
    # ---- the performance ------------------------------------------------------------------------------------------
    Knob("tempo", ("pace",), lambda c, x: x * 2 ** (0.18 * c.pace),
         drift="tempo", span=lambda c: 0.10 + 0.06 * c.range, ratio=True, bounds=lambda x: (0.75 * x, 1.3 * x), step=0.1),
    Knob("tonic", ("identity",), lambda c, x: x + comfort(c),
         drift="key", span=2.0, view="year", bounds=lambda x: (x - 5, x + 5), step=1),
    Knob("humanize", ("rubato",), lambda c, x: x * 2 ** (0.8 * c.rubato),
         drift="feel", span=0.4, ratio=True, bounds=(0.002, 0.02), step=0.0001),
    Knob("ritardando", ("rubato", "pace"), lambda c, x: x + 0.12 * c.rubato - 0.08 * c.pace,
         drift="feel", span=0.12, bounds=(0.1, 0.7), step=0.01),
    Knob("lay", ("lay",), lambda c, x: 0.07 * c.lay, bounds=(-0.08, 0.08), step=0.005),
    # ---- the singer's body: this machine's own, never inherited -------------------------------------------------
    Knob("singer.shift", ("identity",), lambda c, x: -12 if low(c) else 0, inherit=False, bounds=(-12, 0), step=12),
    Knob("singer.tract", ("identity",), lambda c, x: 1.07 + 0.07 * size(c) + 0.025 * c.id("tract"),
         inherit=False, bounds=(0.94, 1.21), step=0.005),
    Knob("singer.mouth", ("identity",), lambda c, x: x + 0.12 * c.id("mouth"), inherit=False, bounds=(0.85, 1.15), step=0.01),
    Knob("singer.tilt", ("identity",), lambda c, x: x + 0.1 * c.id("tilt") - 0.06 * c.brightness,
         inherit=False, bounds=(0.25, 0.7), step=0.01),
    Knob("singer.vibrato_rate", ("identity",), lambda c, x: x + 0.45 * c.id("vibrato_rate") + 0.2 * c.lay,
         inherit=False, bounds=(4.6, 6.2), step=0.05),
    Knob("singer.jitter", ("identity",), lambda c, x: x + 0.07 * c.id("jitter") + 0.05 * c.wear + 0.04 * c.tired,
         inherit=False, bounds=(0.15, 0.55), step=0.01),
    Knob("singer.shimmer", ("identity",), lambda c, x: x + 0.5 * c.id("shimmer") + 0.4 * c.wear,
         inherit=False, bounds=(1.5, 4.0), step=0.1),
    # ---- the singer's habits: learned, so inherited and pulled toward this machine's; drift is the singer's day --
    Knob("singer.rd", ("identity",), lambda c, x: x + 0.15 * c.id("rd") + 0.08 * c.wear - 0.06 * c.brightness,
         drift="voice", span=0.06, bounds=(0.55, 1.3), step=0.01),
    Knob("singer.breath", ("identity",), lambda c, x: x + 0.02 * c.id("breath") + 0.015 * c.wear + 0.01 * c.tired,
         drift="voice", span=0.015, bounds=(0.02, 0.13), step=0.005),
    Knob("singer.vibrato_depth", ("identity",), lambda c, x: x + 9 * c.id("vibrato_depth") + 5 * c.rubato,
         drift="voice", span=12.0, bounds=(14.0, 44.0), step=0.5),
    Knob("singer.vibrato_delay", ("identity",), lambda c, x: x + 0.07 * c.id("vibrato_delay"), bounds=(0.18, 0.4), step=0.01),
    Knob("singer.glide", ("identity",), lambda c, x: x + 0.02 * c.id("glide") - 0.01 * c.lay, bounds=(0.07, 0.15), step=0.005),
    Knob("singer.scoop", ("identity",), lambda c, x: x + 0.1 * c.id("scoop") - 0.08 * c.lay, bounds=(0.15, 0.55), step=0.01),
    Knob("singer.wander", ("identity",), lambda c, x: x + 1.5 * c.id("wander") + 1.2 * c.wear, bounds=(3.0, 10.0), step=0.1),
    Knob("singer.dynamics", ("identity",), lambda c, x: x + 2.5 * c.id("dynamics"),
         drift="voice", span=2.5, bounds=(10.0, 19.0), step=0.5),
    # ---- the band (songbird.band.Band) ---------------------------------------------------------------------------
    # swing, 0 straight to 1 a triplet lilt, for the players and the singer's time alike
    Knob("band.swing", ("swing",), lambda c, x: 0.18 + 0.18 * c.swing,
         drift="feel", span=0.09, bounds=(0.0, 0.6), step=0.01),
    Knob("band.brightness", ("brightness",), lambda c, x: x + 0.25 * c.brightness - 0.1 * c.warmth,
         drift="sheen", span=0.15, bounds=(0.1, 0.9), step=0.01),
    Knob("band.density", ("density",), lambda c, x: x + 0.25 * c.density,
         drift="texture", span=0.2, view="slow", bounds=(0.1, 0.9), step=0.01),
    Knob("band.wear", ("wear", "tired"), lambda c, x: x + 0.2 * c.wear + 0.05 * c.tired, bounds=(0.0, 0.7), step=0.01),
    Knob("band.ornament", ("richness",), lambda c, x: x + 0.25 * c.richness,
         drift="feel", span=0.1, bounds=(0.1, 0.9), step=0.01),
    Knob("band.arc", ("identity",), lambda c, x: x + 0.12 * c.id("arc"),
         drift="arc", span=0.12, view="slow", bounds=(0.4, 1.0), step=0.01),
    # the instruments' size and their maker's hand are the machine's own, like the singer's body
    Knob("band.body", ("identity",), lambda c, x: x - 0.1 * size(c) + 0.04 * c.id("body"),
         inherit=False, bounds=(0.85, 1.2), step=0.01),
    Knob("band.maker", ("identity",), lambda c, x: (c.id("maker") + 1) / 2 * (2**31 - 1),
         inherit=False, bounds=(0, 2**31 - 1), step=1),
    # each instrument's gain: the machine's own balance, moved by two slow drifts, one that each machine's
    # instruments follow their own ways and one between the plucked strings and the bowed and blown; never
    # below 0.5, since a gain under 0.02 would drop the part and hand its role to another
    *(Knob(f"band.{name}", ("identity",), lambda c, x, name=name: x * 2 ** (0.35 * c.id(f"gain:{name}")),
           drift=("balance", "ensemble"), span=(lambda c, name=name: 0.3 * c.id(f"balance:{name}"), 0.25 * ENSEMBLE[name]),
           ratio=True, view="slow", bounds=(0.5, 1.5), step=0.01)
      for name in INSTRUMENTS),
    # ---- the mix (songbird.synth.mixing.MixParams); the room's rt60 and tone are choose_room's ------------------
    # the room answers sooner in a small room and later in a big one: part of the room, so the machine's own
    Knob("mix.predelay", ("room", "identity"),
         lambda c, x: x * (c.room["rt60"] / 1.1 if c.room else 1.0) ** 0.8 * 2 ** (0.25 * c.id("predelay")),
         inherit=False, bounds=(0.005, 0.04), step=0.001),
    Knob("mix.space", ("identity",), lambda c, x: x + 0.12 * c.id("space"),
         drift="space", span=0.3, view="slow", bounds=(0.7, 1.3), step=0.01),
    Knob("mix.intimacy", ("identity",), lambda c, x: x + 0.12 * c.id("intimacy"),
         drift="near", span=0.12, view="slow", bounds=(0.3, 0.7), step=0.01),
    Knob("mix.width", ("warmth", "identity"), lambda c, x: x - 0.08 * c.warmth + 0.05 * c.id("width"),
         drift="sheen", span=0.12, view="slow", bounds=(0.9, 1.25), step=0.01),
    # how far the voice stands over the band: kept near the designed 10 dB (lower costs words; 6-7 might be warmer)
    Knob("mix.forward", ("identity",), lambda c, x: x + 0.6 * c.id("forward"),
         drift="voice", span=0.5, bounds=(8.5, 11.0), step=0.1),
    Knob("mix.duck", (), lambda c, x: x, drift="duck", span=0.4, view="slow", bounds=(0.6, 1.4), step=0.01),
    Knob("mix.tilt", ("brightness",), lambda c, x: x + 0.8 * c.brightness,
         drift="sheen", span=0.5, bounds=(-1.2, 1.2), step=0.05),
    # the recording's wear, a tape's: from old files and a tired machine; crackle starts at 0.35, which only the
    # oldest machines reach (a median file age of about eight years or more)
    Knob("mix.wear", ("wear", "tired"), lambda c, x: max(0.0, 0.12 + 0.24 * c.wear + 0.03 * c.tired),
         inherit=False, bounds=(0.0, 0.4), step=0.01),
    # ---- what the lyric leans toward (for songbird.arrange) ------------------------------------------------------
    Knob("leanings.era_bias", ("era", "wear"), lambda c, x: x + 0.6 * c.era - 0.3 * c.wear,
         drift="era", span=0.6, view="slow", bounds=(-1.0, 1.0), step=0.05),
    Knob("leanings.rarity_appetite", ("richness",), lambda c, x: x + 0.7 * c.richness,
         drift="rarity", span=0.5, view="slow", bounds=(-1.0, 1.0), step=0.05),
)


# ---------------------------------------------------------------- the choices a number can't make


@dataclass
class Context:
    genome: Genome
    song: object  # the seed's Params: what own values are measured from
    parent: object  # the parent's Params
    c: Character
    drift: Drift | None
    log: list | None = None  # where to note what changed from the parent in the tune and the words, and why
    trace: dict | None = None  # if given, each knob's arithmetic by path (for the studio's reasons)
    style: str | None = None  # a style asked for by name (songbird render --style), else the ring decides
    arrange: dict | None = None  # the arrangement's options asked for (Style fields), else the style decides
    then: Drift | None = None  # this machine's drift when it made the parent, if it did (made_here)

    def at(self, view: str, dimension: str) -> float:
        return self.drift.view(view).get(dimension, 0.0) if self.drift is not None else 0.0

    def pull(self, was: float, own: float) -> float:
        return was + PULL * (own - was)

    def at_then(self, view: str, dimension: str) -> float:
        return self.then.view(view).get(dimension, 0.0) if self.then is not None else 0.0

    def habit(self, name: str, where: str = "") -> float | None:
        """How much this machine likes something (0..1), stable for the machine,
        a little different at each place it comes up; None for a neutral voice."""
        if "identity" not in self.c.known:
            return None
        local = 0.1 * self.c.id(f"habit:{name}:{where}") if where else 0.0
        return clip(0.5 + 0.3 * self.c.id(f"habit:{name}") + local, 0.0, 1.0)


def regained(was: float, inverse: float, sung: Callable, step: float, even: bool = False) -> float:
    """A centre on the step grid, near inverse (where the day points back to), that sings the parent's value
    (was) again: sung(centre) == was. So the record's rounding never wanders down a machine's own versions.
    Where a ratio could fold two grid points onto one value (even), the one on the grid of two steps, so the
    next time comes back to the same one exactly; at most one such move, made where it can't be heard (both
    sang was). If none sings was (a person's own value, say), the nearest grid point."""
    k = round(inverse / step)
    fits = [c for c in (round((k + i) * step, 6) for i in (0, -1, 1)) if sung(c) == was]
    if not fits:
        return round(k * step, 6)
    return min(fits, key=lambda c: (even and round(c / step) % 2 != 0, abs(c - inverse)))


def made_here(parent, drift: Drift | None) -> Drift | None:
    """This machine's drift at the moment it made the parent (Params.made), if it made it: its own last
    rendition, sung again. What the machine knows nothing of its own about, the parent already carries that
    day's move in, so it is taken back out before today's goes in (Knob.centre, centred()). None for a parent
    from another machine or from no machine (the seed): that hand-off takes its one turn."""
    made = getattr(parent, "made", None) or {}
    if drift is None or not drift.hash or made.get("by") != drift.hash[:12] or made.get("at") is None:
        return None
    return _field_at(float(made["at"]), drift.hash)


@functools.lru_cache(maxsize=256)
def _field_at(t: float, hash_: str) -> Drift:
    """The drift at a moment, remembered: the studio asks of one parent's moment for a year of days."""
    return field_at(t, hash_)


def centred(ctx: Context, was, options, choose, home, estimate: Callable):
    """The option a decision starts from for a machine that knows nothing of its own there: the parent's
    (was), unless this machine made the parent; then the one its day then moved to the parent's, one of the
    options from which choose(option, ctx.then) gives was. So the same day gives the parent's again, and
    later days the machine's field around one centre, never a walk. A held choice or a nearest mode can't
    always tell which option that was: then the song's own (home) if it is one, else the nearest to where
    the day points back to (estimate(option): how far from it), the parent's own in a tie."""
    if ctx.then is None:
        return was
    found = [o for o in options if choose(o, ctx.then) == was]
    if not found:
        return was
    return min(found, key=lambda o: (o != home, estimate(o), o != was))


# Modes by brightness, and a chord's quality in a mode. A drift of 1 moves the machine's own mode this many
# steps of brightness, so every member of its family comes round some year (ionian to aeolian is three).
BRIGHTNESS = {"lydian": 6, "ionian": 5, "mixolydian": 4, "dorian": 3, "aeolian": 2, "phrygian": 1, "locrian": 0}
MODE_SPAN = 3.5
MINOR = {"dorian", "aeolian", "phrygian", "locrian"}


def quality(symbol: str, mode: str) -> str:
    root, third, fifth = chord_tones(symbol, mode)[:3]
    return {(4, 7): "major", (3, 7): "minor", (3, 6): "diminished", (4, 8): "augmented"}.get(
        ((third - root) % 12, (fifth - root) % 12), "other")


@per_genome
def allowed_modes(genome: Genome, own_mode: str) -> tuple[str, ...]:
    """Modes the song can be sung in, brightest first: every chord it uses stays
    a major or minor triad (or keeps the quality it has in the song's own mode).
    For I IV V vi that is ionian, mixolydian and aeolian; dorian would make vi
    diminished, lydian IV and phrygian V."""
    chords = {s for phrase in genome.phrases.values() for bar in phrase.chords for s in bar}
    ok = [m for m in MODES
          if all(quality(s, m) in ("major", "minor") or quality(s, m) == quality(s, own_mode) for s in chords)]
    return tuple(sorted(ok, key=lambda m: -BRIGHTNESS[m]))


def choose_mode(out: dict, ctx: Context) -> None:
    """The parent's mode pulled toward the voice family's home, moved by the
    year's drift (a positive drift brightens), then the nearest mode the family
    and the song's chords allow. With no family, the home is the parent's
    (centred(): as it stood before this machine's day moved it)."""
    allowed = allowed_modes(ctx.genome, ctx.song.mode)

    def mode(parent: str, d: float) -> str:
        members = allowed
        home = parent
        if ctx.c.family in MODE_FAMILIES:
            family, home = MODE_FAMILIES[ctx.c.family]
            members = [m for m in family if m in allowed] or allowed
        elif parent not in allowed:
            members = sorted(set(allowed) | {parent}, key=lambda m: -BRIGHTNESS[m])
        target = ctx.pull(BRIGHTNESS[parent], BRIGHTNESS[home] + MODE_SPAN * d)
        return min(members, key=lambda m: (abs(BRIGHTNESS[m] - target), abs(BRIGHTNESS[m] - BRIGHTNESS[parent])))

    parent = ctx.parent.mode
    if ctx.c.family not in MODE_FAMILIES:
        back = BRIGHTNESS[parent] - PULL * MODE_SPAN * ctx.at_then("year", "mode")
        parent = centred(ctx, parent, sorted(set(allowed) | {parent}, key=lambda m: -BRIGHTNESS[m]),
                         lambda m, then: mode(m, then.view("year").get("mode", 0.0)), ctx.song.mode,
                         lambda m: abs(BRIGHTNESS[m] - back))
    out["mode"] = mode(parent, ctx.at("year", "mode"))


# The accompaniment: patterns over the chord voicing (0 the bass, 1-4 above it; . rests), by steps per bar.
PATTERNS = {
    8: ("0 . . . 2 . . .", "0 . . . 2 . 3 .", "0 . 2 . 3 . 4 .", "0 . 2 . 3 . 4 1", "0 . 2 3 4 . 3 2",
        "0 . 2 3 . 4 3 2", "0 . 3 4 2 . 3 4", "0 . 2 3 4 3 2 3", "0 2 3 4 2 3 4 3"),
    6: ("0 . . 2 . .", "0 . 2 . 3 .", "0 . 2 3 4 3", "0 1 2 3 2 1", "0 2 3 4 3 2"),
}


@functools.lru_cache(maxsize=256)
def busy(pattern: str) -> float:
    steps = pattern.split()
    return sum(s != "." for s in steps) / len(steps)


def choose_accomp(out: dict, ctx: Context) -> None:
    """The pattern nearest in busyness to the parent's pulled toward the
    machine's density moved by the texture drift; close enough keeps the
    parent's own pattern. With no density, the machine's own is the parent's
    (centred(): as it stood before this machine's day moved it)."""
    parent = ctx.parent.accomp
    choices = PATTERNS.get(len(parent.split()))
    if not choices:
        return

    def accomp(parent: str, d: float) -> str:
        was = busy(parent)
        own = 0.72 + 0.2 * ctx.c.density if "density" in ctx.c.known else was
        target = ctx.pull(was, own + 0.3 * d)
        if abs(target - was) < 0.08:
            return parent
        best = min(abs(busy(p) - target) for p in choices)
        near = [p for p in choices if abs(busy(p) - target) - best < 1e-9]
        return near[min(len(near) - 1, int((ctx.c.id("accomp") + 1) / 2 * len(near)))]

    start = parent
    if "density" not in ctx.c.known:
        back = busy(parent) - PULL * 0.3 * ctx.at_then("slow", "texture")
        start = centred(ctx, parent, tuple(dict.fromkeys((parent, *choices))),
                        lambda p, then: accomp(p, then.view("slow").get("texture", 0.0)), ctx.song.accomp,
                        lambda p: abs(busy(p) - back))
    chosen = accomp(start, ctx.at("slow", "texture"))
    if chosen != parent:
        out["accomp"] = chosen


HOLD = 0.2  # a held choice moves to a neighbour only once its position is this far past the boundary
HISTORY = 730  # days a held choice looks back for where it last stood firmly


def held(ctx: Context, view: str, dimension: str, base: float, span: float, n: int) -> int:
    """One of n ordered categories (0..n-1) at position base + span x the drift, with hysteresis:
    a Schmitt trigger with no state. Within HOLD of a boundary between two categories the choice
    is the one the position last sat firmly in, found by reading the drift field back day by day;
    so a choice changes only when the drift has moved well past a boundary, and never flickers
    between renders a day apart."""

    def firm(p: float) -> int | None:
        if p <= 0.5 - HOLD:
            return 0
        if p >= n - 1.5 + HOLD:
            return n - 1
        k = int(np.floor(p + 0.5))
        return k if abs(p - k) <= 0.5 - HOLD else None

    now = base + span * ctx.at(view, dimension)
    here = firm(now)
    if here is not None:
        return here
    drift = ctx.drift
    if drift is not None and drift.hash:
        for start in range(1, HISTORY + 1, 60):
            back = np.arange(start, min(start + 60, HISTORY + 1), dtype=float)
            for v in series(drift.t - back, drift.hash, [dimension])[dimension][view]:
                k = firm(base + span * float(v))
                if k is not None:
                    return k
    return int(np.clip(np.floor(now + 0.5), 0, n - 1))


# The band's categories in an order the drift can walk: accompaniment families from the sparest to the
# busiest, and the lead instruments from breath through bow to pluck. A drift of 1 moves either this many steps.
PATTERN_ORDER = ("air", "pick", "lilt", "strum")
LEAD_ORDER = ("whistle", "fiddle", "lute")
PATTERN_SPAN = 1.2
LEAD_SPAN = 1.2


def choose_pattern(out: dict, ctx: Context) -> None:
    """The band's accompaniment family: the parent's pulled toward the machine's own (its identity,
    a busy machine leaning to the strum), moved by the slow drift, held against flicker."""
    index = lambda band: PATTERN_ORDER.index(band.pattern) if band.pattern in PATTERN_ORDER else 2  # noqa: E731
    was = index(ctx.parent.band)
    if "identity" in ctx.c.known:
        base = ctx.pull(was, 2.0 + 1.1 * ctx.c.id("pattern") + 0.4 * ctx.c.density)
    else:
        base = held_centre(ctx, "slow", "pattern", was, index(ctx.song.band), PATTERN_SPAN, len(PATTERN_ORDER))
    k = held(ctx, "slow", "pattern", base, PATTERN_SPAN, len(PATTERN_ORDER))
    out.setdefault("band", {})["pattern"] = PATTERN_ORDER[k]


def choose_lead(out: dict, ctx: Context) -> None:
    """Who states the tune where nobody sings: the parent's lead pulled toward the machine's own,
    moved by the year's drift, held against flicker."""
    index = lambda band: LEAD_ORDER.index(band.lead) if band.lead in LEAD_ORDER else 0  # noqa: E731
    was = index(ctx.parent.band)
    if "identity" in ctx.c.known:
        base = ctx.pull(was, 1.0 + 1.3 * ctx.c.id("lead"))
    else:
        base = held_centre(ctx, "year", "lead", was, index(ctx.song.band), LEAD_SPAN, len(LEAD_ORDER))
    k = held(ctx, "year", "lead", base, LEAD_SPAN, len(LEAD_ORDER))
    out.setdefault("band", {})["lead"] = LEAD_ORDER[k]


def held_centre(ctx: Context, view: str, dimension: str, was: int, home: int, span: float, n: int) -> int:
    """Where a held choice starts for a machine with no identity: the parent's (was), as it stood before this
    machine's day moved it (centred(); home: the song's own)."""
    if ctx.then is None:
        return was
    return _held_centre(ctx.then.t, ctx.then.hash, view, dimension, was, home, span, n)


@functools.lru_cache(maxsize=1024)
def _held_centre(t: float, hash_: str, view: str, dimension: str, was: int, home: int, span: float, n: int) -> int:
    """held_centre for the parent made at t, remembered (reading a held choice back can take the field's past)."""
    then = _field_at(t, hash_)
    ctx = Context(None, None, None, Character(), then, then=then)
    back = was - span * ctx.at_then(view, dimension)
    return centred(ctx, was, range(n), lambda k, _: held(ctx, view, dimension, k, span, n), home,
                   lambda k: abs(k - back))


def choose_choir(out: dict, ctx: Context) -> None:
    """Each generation adds a voice to the choir, so you can hear how far a
    rendition has travelled (the song's notes), up to six. A record of the
    lineage, so neither the machine nor the drift touches it."""
    out["choir"] = min(ctx.parent.choir + 1, CHOIR_MAX)


# ---------------------------------------------------------------- form

# How the form drifts: which view of the field, and how far a drift of 1 moves a section's score (it plays
# above 0.5) and the verse count. Each section's own dimension of the drift is named after it.
FORM_VIEW = "season"
SECTION_SPAN = 0.5
VERSE_SPAN = 1.2


def template(genome: Genome) -> list[tuple[str, str]]:
    """The form template as (section, "" | "?" | "*")."""
    return [(t.rstrip("?*"), t[len(t.rstrip("?*")):][:1]) for t in genome.form]


def is_verse(genome: Genome, name: str) -> bool:
    return genome.section(name).lyrics == "verse"


@dataclass(frozen=True)
class Item:
    """A piece of the template: one section, or a repeatable verse with the
    refrain it brings (and any turn that follows the first verse's refrain).
    A group is sung as units, each a verse (or two) and then the refrain, so
    every unit adds a refrain and the question turns once more."""

    index: int  # position of its first token in the template
    tokens: tuple  # ((name, flag), ...); a group's first token is its verse
    repeat: bool


@per_genome
def items(genome: Genome) -> tuple[Item, ...]:
    tokens = template(genome)
    lyrics = [genome.sections[n].lyrics for n, _ in tokens]
    followers: set[str] = set()  # what follows the first verse's refrain comes with every refrain a verse brings
    for k, (n, f) in enumerate(tokens):
        if f == "" and lyrics[k] == "verse":
            j = k + 1
            if j < len(tokens) and lyrics[j] == "refrain":
                j += 1
                while j < len(tokens) and tokens[j][1] == "?" and lyrics[j] is None:
                    followers.add(tokens[j][0])
                    j += 1
            break
    out, i = [], 0
    while i < len(tokens):
        name, flag = tokens[i]
        if flag == "*" and lyrics[i] == "verse":
            group, j = [(name, "")], i + 1
            if j < len(tokens) and lyrics[j] == "refrain" and tokens[j][1] == "":
                group.append(tokens[j])
                j += 1
                while j < len(tokens) and tokens[j][1] == "?" and tokens[j][0] in followers:
                    group.append(tokens[j])
                    j += 1
            out.append(Item(i, tuple(group), True))
            i = j
        else:
            out.append(Item(i, (tokens[i],), False))
            i += 1
    return tuple(out)


def extra_bridge(genome: Genome) -> bool:
    """Whether the song's bank allows a second bridge stanza in a long form,
    sung as bridge2: the bridge's phrases and choir again (Genome.section)."""
    return bool(genome.source.get("bank", {}).get("rules", {}).get("bridge", {}).get("extra"))


def required_verses(genome: Genome) -> int:
    return sum(1 for it in items(genome) if not it.repeat and it.tokens[0][1] == "" and is_verse(genome, it.tokens[0][0]))


def verse_range(genome: Genome) -> tuple[int, int]:
    """How many verses a form may have: the bank's rule, or the template's."""
    rule = genome.source.get("bank", {}).get("rules", {}).get("verses", {}).get("count")
    if rule:
        return int(rule[0]), int(rule[1])
    required = required_verses(genome)
    if not any(it.repeat for it in items(genome)):
        return required, required
    seeded = sum(1 for n in genome.seed_params.get("form", []) if is_verse(genome, n))
    lo = max(required, 2)
    return lo, max(lo, seeded, min(len(genome.seed_verses), 5))


@per_genome
def _grammar(genome: Genome) -> re.Pattern:
    parts = []
    for it in items(genome):
        if it.repeat:
            (verse, _), *rest = it.tokens
            unit = f"(?:{re.escape(verse)},)+" + "".join(f"(?:{re.escape(n)},){'?' if f == '?' else ''}" for n, f in rest)
            parts.append(f"(?P<t{it.index}>(?:{unit})*)")
        else:
            name, flag = it.tokens[0]
            parts.append(f"(?P<t{it.index}>(?:{re.escape(name)},){'?' if flag == '?' else ''})")
            if genome.sections[name].lyrics == "bridge" and extra_bridge(genome):
                parts.append(f"(?P<x{it.index}>(?:bridge2,)?)")
    return re.compile("".join(parts))


def parse_form(genome: Genome, form) -> dict[str, str] | None:
    """Each template item's part of a form (tN for the item at template position
    N, xN for a second bridge after it), or None if the form doesn't follow the
    template."""
    match = _grammar(genome).fullmatch("".join(f"{name}," for name in form))
    return None if match is None else {k: v or "" for k, v in match.groupdict().items()}


def fits(genome: Genome, form) -> bool:
    """A form follows the genome's template and has a verse count its rules allow."""
    if parse_form(genome, form) is None:
        return False
    lo, hi = verse_range(genome)
    return lo <= sum(1 for n in form if is_verse(genome, n)) <= hi


def units(genome: Genome, verses: int, pairs: bool = False) -> dict[int, list[int]]:
    """How the verses beyond the required ones are sung: for each repeatable
    group, how many verses each of its units has (one, or two where verses come
    in pairs), the units handed round the groups, first first."""
    groups = [it.index for it in items(genome) if it.repeat]
    plan: dict[int, list[int]] = {g: [] for g in groups}
    extra, k = max(0, verses - required_verses(genome)), 0
    while extra > 0 and groups:
        size = 2 if pairs and extra >= 2 else 1
        plan[groups[k % len(groups)]].append(size)
        extra -= size
        k += 1
    return plan


def build(genome: Genome, verses: int, present: dict, bridge2: bool = False, pairs: bool = False) -> tuple[str, ...]:
    """A concrete form: the required sections, each optional one where
    present[(item index, section, unit)] says so, and the verse groups sung as
    units to make the verse count."""
    plan = units(genome, verses, pairs)
    form: list[str] = []
    for it in items(genome):
        if it.repeat:
            (verse, _), *rest = it.tokens
            for r, size in enumerate(plan[it.index]):
                form += [verse] * size
                form += [n for n, f in rest if f == "" or present.get((it.index, n, r))]
            continue
        name, flag = it.tokens[0]
        if flag == "" or present.get((it.index, name, 0)):
            form.append(name)
        if bridge2 and genome.sections[name].lyrics == "bridge" and extra_bridge(genome):
            form.append("bridge2")
    return tuple(form)


def choose_form(out: dict, ctx: Context) -> None:
    """How many verses, how they come, and which optional sections play.

    The verse count pulls the parent's toward the machine's taste (a rich
    vocabulary tells longer stories), moved by its drift. Each optional
    section (an intro, the turns, a break, the tag, an outro) is decided once
    for the whole form: its score is how often the parent played it (1 or 0,
    or 0.5 if the parent had no place for it) pulled toward the machine's
    habit (0.5 for a neutral voice), plus SECTION_SPAN of its drift; it plays
    above 0.5, so a lineage remembers its form and a machine's habits pull it.
    Two verses to a refrain is scored the same way against a machine that
    leans away from it, since a verse and then its refrain is the song's
    shape: rare where the parent never did it."""
    if out.get("composition", {}).get("order"):
        out["form"] = list(out["composition"]["order"])
        return  # a person's arrangement is carried; its words and other choices still evolve
    genome = ctx.genome
    source = ctx.parent.form if parse_form(genome, ctx.parent.form) else ctx.song.form
    was = parse_form(genome, source)
    if was is None:
        return  # a form outside the template (set by hand) is kept as it is
    lo, hi = verse_range(genome)
    had = sum(1 for n in source if is_verse(genome, n))
    if "richness" in ctx.c.known:
        own = (lo + hi) / 2 + (hi - lo) / 2 * ctx.c.richness
    else:
        habit = ctx.habit("verses")
        own = lo + (hi - lo) * (0.5 if habit is None else habit)
    verses = max(lo, min(hi, round(ctx.pull(had, own) + VERSE_SPAN * ctx.at(FORM_VIEW, "verses"))))

    def plays(before: float, habit: float | None, dimension: str) -> bool:
        score = ctx.pull(before, 0.5 if habit is None else habit)
        return score + SECTION_SPAN * ctx.at(FORM_VIEW, dimension) > 0.5

    sung = paired = 0  # the parent's units, and how many of them had two verses
    possible: dict[str, int] = {}  # where the parent could have played each optional section, and did
    played: dict[str, int] = {}
    for it in items(genome):
        text = was.get(f"t{it.index}", "")
        if it.repeat and len(it.tokens) > 1:
            verse, refrain = it.tokens[0][0], it.tokens[1][0]
            for chunk in text.split(f"{refrain},"):
                n = chunk.split(",").count(verse)
                sung += n > 0
                paired += n > 1
            for name, flag in it.tokens[1:]:
                if flag == "?":
                    possible[name] = possible.get(name, 0) + text.count(f"{refrain},")
                    played[name] = played.get(name, 0) + text.count(f"{name},")
        elif not it.repeat and it.tokens[0][1] == "?":
            name = it.tokens[0][0]
            possible[name] = possible.get(name, 0) + 1
            played[name] = played.get(name, 0) + bool(text)
    habit = ctx.habit("pairs")
    pairs = plays(float(sung > 0 and paired / sung >= 0.5), 0.25 if habit is None else habit / 2, "pairs")
    decided = {name: plays(float(played[name] / n >= 0.5) if n else 0.5, ctx.habit(name),
                           name if name in DIMENSIONS else "other")
               for name, n in possible.items()}

    plan = units(genome, verses, pairs)
    present = {}
    for it in items(genome):
        for name, flag in it.tokens[1:] if it.repeat else it.tokens:
            if flag == "?":
                for r in range(len(plan[it.index]) if it.repeat else 1):
                    present[(it.index, name, r)] = decided[name]
    second = False
    if extra_bridge(genome) and verses > lo:  # a long form may sing the bridge's extra stanza
        second = plays(float(any(v for k, v in was.items() if k.startswith("x"))), ctx.habit("extra"), "extra")
    form = build(genome, verses, present, second, pairs)
    if genome.source.get("bank"):  # the bank must be able to fill it; it always can, this makes sure
        from .arrange import problem

        if problem(genome, form) and second:
            form = build(genome, verses, present, False, pairs)
        if problem(genome, form):
            return
    out["form"] = list(form)


# ---------------------------------------------------------------- the lyric's leanings


@per_genome
def song_words(genome: Genome) -> frozenset[str]:
    """Every word the song can sing: its bank, seed verses and fixed blocks."""
    text: list[str] = []

    def walk(x) -> None:
        if isinstance(x, str):
            text.append(x)
        elif isinstance(x, (list, tuple)):
            for item in x:
                walk(item)
        elif isinstance(x, dict):
            for key, value in x.items():
                if key not in ("note", "by", "id", "mood", "scheme", "rarity", "pairs_with", "era", "rules"):
                    walk(value)

    walk(genome.source.get("bank", {}))
    walk(genome.seed_verses)
    walk(list(genome.fixed.values()))
    return frozenset(w.replace("-", "").lower() for t in text
                     for w in re.findall(r"[A-Za-z][A-Za-z'-]*", t.replace("*", "")))


def choose_mood(out: dict, ctx: Context) -> None:
    """Mood weights over plain, light, dark and tender: the parent's pulled
    toward the screen's (a light screen lightens, a warm one is tender), with
    the slow mood drift tilting the machine's own (a positive drift lightens),
    darker in a minor mode. Never read from the person's words. With no
    screen, the machine's own is the parent's, as it stood before this
    machine's day (and a minor mode's darkening) moved it, as Knob.centre."""
    was = {**LEANINGS["mood_weights"], **ctx.parent.leanings.get("mood_weights", {})}
    c = ctx.c
    screen = {"plain": 1.0, "light": 1.0 + 0.6 * c.brightness, "dark": 1.0 - 0.5 * c.brightness,
              "tender": 1.0 + 0.5 * c.warmth} if "brightness" in c.known else None
    lean = {"plain": 0.5, "light": 1.0, "dark": -1.0, "tender": -0.5}  # a drift of 1 doubles light, halves dark

    def sung(was: dict, tilt: float, mode) -> dict:
        minor = {"dark": 1.5, "tender": 1.2} if mode in MINOR else {}
        weights = {}
        for mood, w in was.items():
            own = (screen.get(mood, 1.0) if screen else w) * 2 ** (lean.get(mood, 0.0) * tilt) * minor.get(mood, 1.0)
            weights[mood] = ctx.pull(w, own)
        mean = sum(weights.values()) / len(weights)
        return {k: round(float(v / mean), 2) for k, v in weights.items()}

    tilt, mode = ctx.at("slow", "mood"), out.get("mode")
    home = {**LEANINGS["mood_weights"], **(ctx.song.leanings or {}).get("mood_weights", {})}
    if screen is None and ctx.then is not None and sung(home, ctx.at_then("slow", "mood"), ctx.parent.mode) != was:
        # its own rendition sung again, from other than the song's own: each weight as a ratio knob's centre
        def day(mood: str, tilt: float, mode) -> float:
            minor = {"dark": 1.5, "tender": 1.2} if mode in MINOR else {}
            return ctx.pull(1.0, 2 ** (lean.get(mood, 0.0) * tilt) * minor.get(mood, 1.0))

        then = {m: day(m, ctx.at_then("slow", "mood"), ctx.parent.mode) for m in was}
        now = {m: day(m, tilt, mode) for m in was}
        if now != then:  # the field has moved since: that day out (as a ratio knob's, Knob.centre), today's in;
            # unmoved, the parent's stand
            was = {m: regained(w, w / then[m], lambda c, m=m: round(float(c * then[m]), 2), 0.01, even=True) * now[m]
                   for m, w in was.items()}
        out.setdefault("leanings", {})["mood_weights"] = {m: round(float(w), 2) for m, w in was.items()}
        return
    if screen is None and ctx.then is not None:  # its own rendition of the song's own: the song's own, today
        was = home
    out.setdefault("leanings", {})["mood_weights"] = sung(was, tilt, mode)


def choose_vocabulary(out: dict, ctx: Context) -> None:
    """Words the lyric should lean toward: the song's own words in the themes
    the person's words favour (a weight above 1 is more than an even share),
    pulled with the parent's. Only the song's words ever appear."""
    was = dict(ctx.parent.leanings.get("vocabulary", {}))
    if not ctx.c.themes:
        if was:
            out.setdefault("leanings", {})["vocabulary"] = was
        return
    words = song_words(ctx.genome)
    even = 1.0 / len(ctx.c.themes)
    own: dict[str, float] = {}
    for theme, share in ctx.c.themes.items():
        if share > even:
            for w in THEMES.get(theme, "").split():
                if w in words:
                    own[w] = max(own.get(w, 0.0), share / even)
    merged = {w: ctx.pull(was.get(w, 0.0), own.get(w, 0.0)) for w in sorted(set(was) | set(own))}
    out.setdefault("leanings", {})["vocabulary"] = {w: round(float(v), 2) for w, v in merged.items() if v >= 0.05}


def leanings(params):
    """The leanings chosen with params (or the leanings dict itself), as songbird.arrange
    takes them; None for parameters that chose none (the seed's), which arrange reads as neutral."""
    lean = params if isinstance(params, dict) else params.leanings
    if not lean:
        return None
    from .arrange import Leanings

    vocabulary = lean.get("vocabulary", {})
    return Leanings(mood_weights=lean.get("mood_weights", {}), era_bias=lean.get("era_bias", 0.0),
                    rarity_appetite=lean.get("rarity_appetite", 0.0),
                    vocabulary=frozenset(w for w, weight in vocabulary.items() if weight >= VOCABULARY_AT))


LEANING_KNOBS = tuple(k for k in KNOBS if k.path.startswith("leanings."))


def own_leanings(ctx: Context, t: float | None = None, mode: str | None = None):
    """The lyric leanings this machine would choose from its parent's at a moment (a clock's stretch's start,
    so a choice made with them holds through the stretch), or with no moment, from its character alone: its
    taste without the season's drift. As songbird.arrange takes them; None if neutral. (They depend on
    ctx.then too, for what the machine knows nothing of its own about: a memo of them keys it.)"""
    from .drift import drift as drift_at

    hash_ = ctx.drift.hash if ctx.drift is not None else ""
    moment = drift_at(t, hash_) if t is not None and hash_ else None
    sub = Context(ctx.genome, ctx.song, ctx.parent, ctx.c, moment, then=ctx.then)
    tmp = {"leanings": dict(getattr(ctx.parent, "leanings", None) or {}), "mode": mode}
    for knob in LEANING_KNOBS:
        knob.apply(tmp, sub)
    choose_mood(tmp, sub)
    choose_vocabulary(tmp, sub)
    return leanings(tmp["leanings"])


def choose_inventory(out: dict, ctx: Context) -> None:
    """The phoneme inventory the singer's vowels will come from (the singer doesn't read it yet)."""
    if ctx.c.inventory:
        out["inventory"] = ctx.c.inventory


def sung_pitch(genome: Genome, out: dict) -> float:
    """Where this rendition's singer sings: the median of the tune's notes (MIDI) in its key and mode,
    with the singer's octave."""
    from .theory import degree_semitones

    shift = (out.get("singer") or {}).get("shift", 0)
    pitches = [out["tonic"] + degree_semitones(n.degree, out["mode"], n.alter)
               for phrase in genome.phrases.values() for n in phrase.notes if n.degree is not None]
    return float(np.median(pitches) if pitches else out["tonic"]) + shift


def choose_timbre(out: dict, ctx: Context) -> None:
    """The learned singer's own voice: a blend of the singers the throat learned from, drawn from the
    machine's identity among those who sing where it sings, pulled from the parent's blend as every
    trait is, and never more than 0.6 of any one of them (throat.machine_mix). Only when the learned
    throat sings (it is there, and the singer's engine is "learned"), for a machine with an identity."""
    from .synth import throat

    engine = (out.get("singer") or {}).get("engine") or VoiceParams().engine
    if engine != "learned" or "identity" not in ctx.c.known or not throat.available():
        return
    model = throat.load()
    pitch = sung_pitch(ctx.genome, out)
    seed = int.from_bytes(hashlib.sha256(f"identity|{ctx.c.hash}|timbre".encode()).digest()[:8], "little")
    own = throat.parse_mix(throat.machine_mix(seed, pitch, model))
    was = throat.parse_mix(read(ctx.parent, "singer.timbre"))
    was = {n: w for n, w in (was or {}).items() if n in model.config["singers"]} or throat.default_mix(model, pitch)
    names = set(own) | set(was)
    blend = {n: was.get(n, 0.0) + PULL * (own.get(n, 0.0) - was.get(n, 0.0)) for n in names}
    out["singer"]["timbre"] = throat.blend_spec(throat.capped(blend))


def choose_room(out: dict, ctx: Context) -> None:
    """The room (the mix's rt60 and tone) is where the machine lives: its own, else its parent's."""
    if ctx.c.room:
        out.setdefault("mix", {}).update(rt60=ctx.c.room["rt60"], tone=list(ctx.c.room["tone"]))


def style_shaped(genome: Genome, out: dict) -> None:
    from .style import shaped

    shaped(genome, out)


def choose_style(out: dict, ctx: Context) -> None:
    """The rendition's style and what it brings (songbird/style.py): once the form, the choir and every
    number are chosen, since a style leans on them."""
    from .style import choose_style as choose

    choose(out, ctx, ctx.style, ctx.arrange)


# The words and the tune last: they read the form and the leanings chosen above (songbird.evolve).
DECISIONS = (choose_mode, choose_form, choose_accomp, choose_pattern, choose_lead, choose_choir, choose_mood,
             choose_vocabulary, choose_inventory, choose_room, choose_timbre, choose_style, evolve.choose_words,
             evolve.choose_variants)


# ---------------------------------------------------------------- putting it together


def choose(genome: Genome, parent=None, voice: Voice | None = None, drift: Drift | None = None,
           seed: int | None = None, log: list | None = None, form=None, pin: Callable | None = None,
           trace: dict | None = None, style: str | None = None, arrange: dict | None = None):
    """The child's parameters; see realize.choose_params. log, form: as there. pin(out), if given, puts a
    person's choices (songbird.edits) in place after the knobs and after every decision, so a decision that
    reads one reads the person's and none overwrites it; trace, if given, receives each knob's arithmetic.
    style, arrange: a style asked for by name and its options (songbird.style), else the ring decides."""
    from .realize import Params

    song = Params.from_dict(genome.seed_params)
    if parent is not None:  # a person's lines from an older record, by verse rather than by place
        from .composition import handed_down

        parent = handed_down(genome, parent)
    # a generation on from its parent, made here and now (a child on this machine changes only what a clock has
    # turned on since); sung from the genome with no parent rendition it is, as its record counts, generation 0
    generation = int(getattr(parent, "generation", 0)) + 1 if parent is not None else 0
    parent = parent if parent is not None else song
    if voice is None and drift is None:
        chosen = parent if seed is None else replace(parent, seed=seed)
        if style is None and not arrange:
            return chosen
        # a style asked for with no machine: the parent played in it, nothing else chosen
        out = chosen.to_dict()
        choose_style(out, Context(genome, song, parent, Character(), None, log=log,
                                  style=style or (parent.style.name or "ballad"), arrange=arrange))
        if form is None:
            style_shaped(genome, out)  # the parts of the form a style always plays (the old 78's intro and break)
        return Params.from_dict(out)
    ctx = Context(genome, song, parent, character(voice), drift, log=log, trace=trace, style=style, arrange=arrange,
                  then=made_here(parent, drift))
    out = parent.to_dict()
    for key in ("singer", "mix", "leanings"):
        out[key] = dict(out.get(key) or {})
    out["generation"] = generation
    out["made"] = {"by": drift.hash[:12], "at": round(drift.t, 6)} if drift is not None and drift.hash else {}
    for knob in KNOBS:
        knob.apply(out, ctx)
    if pin is not None:
        pin(out)
    for decide in DECISIONS:
        decide(out, ctx)
        if decide in (choose_form, choose_style) and form is not None:  # a form set by hand stands in for the
            # season's (and for a style's: the jazz trio adds a break where a form has none)
            out["form"] = list(form)
        if decide is choose_style and form is None:  # the parts of the form a style always plays (the old 78's)
            style_shaped(genome, out)
        if pin is not None:
            pin(out)
    out["seed"] = Chance(voice, drift, parent, seed).seed
    return Params.from_dict(out)


def lay(score, params):
    """The sung parts moved ahead of the beat (or behind it) by params.lay beats:
    where this lineage's singer sits against the band."""
    if not getattr(params, "lay", 0.0):
        return score
    shift = params.lay * 60.0 / params.tempo
    sung = lambda n: n.part == "voice" or n.part.startswith("choir")  # noqa: E731
    notes = tuple(replace(n, start=max(0.0, n.start - shift)) if sung(n) else n for n in score.notes)
    return replace(score, notes=tuple(sorted(notes, key=lambda n: (n.start, n.part, n.pitch))))
