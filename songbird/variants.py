"""Variants: small departures from the written tune, sung by a rendition and passed down its lineage.

The genome keeps the tune; a variant is how one lineage has come to sing a note of it: a grace note
flicked in, a turn, a passing note sliding through a leap, a leap sung a step wider, a pair of notes
dotted. They are kept in Params.variants, inherited, and gained and forgotten a few at a time
(songbird.evolve decides which), so a lineage accumulates its own way with the tune as a folk tune does.
A singer's own variants, learned from their takes (docs/history/MAKING-IT-THEIR-OWN.md), come in as the same
record with source "sung:<name>"; a person editing the song in the studio makes source "edit".

What a variant may never change (problems() checks every one, and candidates() offers none that break):

- the contour: each phrase's string of holds, steps and leaps (Phrase.contour) is the same after it;
- a phrase's last note (its target): its degree and its time;
- the stress: a stressed note never moves, and a weak note moved stays weak, in its foot, in order;
- the mode and the song's scale: every note, and every ornament tone that is held, is a degree of the
  song's own scale (for a pentatonic tune, its five notes); only the quick tones of a passing tone, a
  mordent or a turn may touch the mode's other degrees, and nothing is ever chromatic;
- the harmony: a note moved to another degree is a tone of the chord under it;
- the hooks, and the refrain's first line: sung as written (catchiness first);
- how many: at most SHARE of the notes of any section carry one, never two on one note or on
  neighbouring notes.

Ornaments are sung inside their note: a syllable stays one note for the singer, and the pitch track
(synth.voice.pitch_track) follows the ornament's shape, given as breakpoints (a fraction of the note,
scale steps from it), so it follows the mode and the tempo. A leap changes the note itself; a rhythm
variant moves a weak note's onset, the note before it taking or giving the time. The band's lead plays
the same variants where it states the tune.

    python -m songbird.variants songs/h-now-its-by-you.json     # every variant the tune allows
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from dataclasses import asdict, dataclass, fields, replace

import numpy as np

from .genome import Genome, Phrase, load
from .theory import MODES, degree_semitones, parse_chord

# The vocabulary. Ornaments are sung inside one note; the rest change the note itself.
ORNAMENTS = ("grace", "mordent", "turn", "neighbour", "passing", "anticipation")
KINDS = ORNAMENTS + ("leap", "dotted", "even")
HEAD = ("grace", "mordent", "turn")  # at the note's start
TAIL = ("passing", "anticipation")  # leading out of the note into the next
RHYTHM = ("dotted", "even")
QUICK = ("passing", "mordent", "turn")  # tones so quick (75-80 ms) they may touch the mode's degrees outside the song's scale

SHARE = 0.12  # at most this share of any section's sung notes carries a variant
SOURCES = ("drift", "edit")  # and "sung:<name>" for a singer's own

# Ornament timing, in seconds at the song's own tempo; stored as fractions of the sung vowel (a note less
# the consonants after it, CODA), so a slower rendition ornaments a little slower. Each kind also needs its
# note to be long enough to hold it (H's vowels measured at 96 bpm: a 1-unit note gets about
# 230 ms, a 2-unit one 535, a line's last note about a second).
CODA = 0.085  # seconds of a note, on average, that aren't its vowel
GRACE = 0.075  # a grace note's length
TONE = 0.075  # each quick tone of a mordent or turn
NEIGHBOUR = (0.42, 0.6)  # where a neighbour note sits in a long note's vowel, as fractions of it
PASSING = 0.08  # a passing tone is a waypoint this long, just before the voice moves on
ANTICIPATION = 0.14  # the next note's pitch arrives this long before the voice would move to it
LONG_ENOUGH = {"grace": 0.28, "mordent": 0.45, "turn": 0.45, "neighbour": 0.9, "passing": 0.28,
               "anticipation": 0.28}  # seconds of note, at the song's own tempo
SHORTEST = 1.0  # grid units: a rhythm variant never leaves a note shorter (in H, dotting a pair of quavers would)


@dataclass(frozen=True)
class Variant:
    """One note of one phrase, sung another way. A phrase is sung wherever the form sings it (a verse
    line in every verse, a refrain line in the intro and the tag), and so is its variant.

    phrase, note  the genome phrase and the note's index among its sung notes
    kind          one of KINDS
    degree        leap: the note's new scale degree (the genome's numbering: 1 the tonic, 8 an octave up)
    steps         an ornament: ((fraction of the note, scale steps from the note), ...), each the pitch the
                  voice turns to at that point; the last is where the note leaves off (0: back on it)
    shift         rhythm: grid units the note's onset moves, later if positive; the note before it takes
                  up (or gives) the time
    source        "drift" (a machine's way, chosen by the drift), "sung:<name>" (learned from a person's
                  takes) or "edit" (chosen by a person in the studio)
    born          the generation it came into the lineage
    """

    phrase: str
    note: int
    kind: str
    degree: int | None = None
    steps: tuple = ()
    shift: float = 0.0
    source: str = "drift"
    born: int = 0

    @property
    def key(self) -> tuple[str, int]:
        """Where it is: one variant a note."""
        return self.phrase, self.note

    @property
    def what(self) -> tuple:
        """What it does, whoever brought it and whenever."""
        return self.phrase, self.note, self.kind, self.degree, self.steps, self.shift

    def to_dict(self) -> dict:
        data = asdict(self)
        data["steps"] = [list(s) for s in self.steps]
        return data

    @classmethod
    def from_dict(cls, data) -> Variant:
        if isinstance(data, Variant):
            return data
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        values["steps"] = tuple((float(f), int(s)) for f, s in values.get("steps", ()))
        values["note"] = int(values["note"])
        if values.get("degree") is not None:
            values["degree"] = int(values["degree"])
        values["shift"] = float(values.get("shift", 0.0))
        return cls(**values)


def parse(items) -> tuple[Variant, ...]:
    """Variants from a record's list of dicts (or Variants), in a stable order."""
    return tuple(sorted((Variant.from_dict(v) for v in items or ()), key=lambda v: (v.phrase, v.note)))


# ---------------------------------------------------------------- the song's facts


def _per_genome(fn):
    """Remember fn(genome, ...) for as long as that genome object is around (a genome never changes)."""
    memo: dict = {}

    @functools.wraps(fn)
    def remembered(genome, *args):
        key = (id(genome), args)
        hit = memo.get(key)
        if hit is None or hit[0] is not genome:
            if len(memo) > 512:
                memo.clear()
            hit = memo[key] = (genome, fn(genome, *args))
        return hit[1]

    return remembered


def _seconds_per_unit(genome: Genome) -> float:
    return 60.0 / float(genome.seed_params.get("tempo", 96)) / genome.meter.beat


@_per_genome
def _facts(genome: Genome) -> dict:
    """What the guards need to know about a genome, worked out once."""
    degrees = [n.degree for p in genome.phrases.values() for n in p.sung]
    classes = sorted({(d - 1) % 7 + 1 for d in degrees})
    protected: set[tuple[str, int]] = set()
    approach: set[tuple[str, int]] = set()
    for hook in genome.hooks:
        a, b = hook["notes"]
        protected |= {(hook["phrase"], k) for k in range(int(a), int(b))}
        if int(a) > 0:  # the way into a hook is part of it: no note moved and nothing leading on into it
            approach.add((hook["phrase"], int(a) - 1))
    refrain = next((s for s in genome.sections.values() if s.lyrics == "refrain"), None)
    if refrain is not None and refrain.phrases:
        first = refrain.phrases[0]
        protected |= {(first, k) for k in range(len(genome.phrases[first].sung))}
    return {
        # the song's own scale: the degrees its tune sings, if it sings at least five of them
        "scale": tuple(classes) if len(classes) >= 5 else tuple(range(1, 8)),
        "range": (min(degrees), max(degrees)) if degrees else (1, 8),
        "protected": frozenset(protected),
        "approach": frozenset(approach - protected),
    }


def scale(genome: Genome) -> tuple[int, ...]:
    """The scale degrees (1-7) the song's tune sings: ornaments and moved notes keep to them."""
    return _facts(genome)["scale"]


def protected(genome: Genome) -> frozenset[tuple[str, int]]:
    """(phrase, note) of every note sung as written: the hooks and the refrain's first line."""
    return _facts(genome)["protected"]


def in_scale(genome: Genome, degree: int) -> bool:
    return (degree - 1) % 7 + 1 in scale(genome)


def neighbour(genome: Genome, degree: int, direction: int) -> int:
    """The next degree of the song's scale above (direction 1) or below (-1)."""
    d = degree + direction
    while not in_scale(genome, d):
        d += direction
    return d


def chord_under(phrase: Phrase, onset: int, meter) -> str:
    """The chord function sounding at a grid position of a phrase, as realize() finds it."""
    bar = min(max(onset // meter.bar, 0), phrase.bars - 1)
    in_bar = phrase.chords[bar]
    return in_bar[min(max((onset - bar * meter.bar) * len(in_bar) // meter.bar, 0), len(in_bar) - 1)]


def chord_tone(symbol: str, degree: int) -> bool:
    """Whether a scale degree is a tone of a (plain, diatonic) chord function, in any mode; a borrowed
    chord (bVII) counts no degree as its own, so nothing is moved under one."""
    root, alter = parse_chord(symbol)
    if alter:
        return False
    return ((degree - root) % 7) in (0, 2, 4)


def stressed(onset: float, meter) -> bool:
    return float(onset) % meter.foot == 0


def _moves(degrees) -> str:
    out = []
    for a, b in zip(degrees, degrees[1:]):
        step = b - a
        out.append("h" if step == 0 else ("u" if step == 1 else "d" if step == -1 else "U" if step > 0 else "D"))
    return " ".join(out)


# ---------------------------------------------------------------- a phrase as a lineage sings it


@dataclass(frozen=True)
class Played:
    """A note of a phrase as sung with its variants: grid units from the phrase's first bar line."""

    degree: int
    alter: int
    onset: float
    dur: float
    ornament: tuple  # ((fraction of the note, scale steps), ...), () for none
    variant: Variant | None  # the variant sung on this note, if any
    # a person's melisma on this syllable (songbird.composition): ((grid units after the note's onset, degree), ...),
    # each a note of its own the syllable's vowel moves to there; () for none
    melisma: tuple = ()


def realized(phrase: Phrase, variants=()) -> tuple[Played, ...]:
    """The phrase's sung notes with its variants applied. With none, exactly the tune as written."""
    notes = phrase.sung
    mine = {v.note: v for v in variants if v.phrase == phrase.id and 0 <= v.note < len(notes)}
    if not mine:
        return tuple(Played(n.degree, n.alter, float(n.onset), float(n.dur), (), None) for n in notes)
    onsets = [n.onset + (mine[k].shift if k in mine and mine[k].kind in RHYTHM else 0.0) for k, n in enumerate(notes)]
    out = []
    for k, n in enumerate(notes):
        v = mine.get(k)
        end = float(n.onset + n.dur)
        if k + 1 < len(notes) and n.onset + n.dur == notes[k + 1].onset:
            end = onsets[k + 1]  # sung on into the next note: it still ends where the next begins
        degree = v.degree if v is not None and v.kind == "leap" and v.degree is not None else n.degree
        ornament = tuple(v.steps) if v is not None and v.kind in ORNAMENTS else ()
        out.append(Played(degree, n.alter, float(onsets[k]), end - onsets[k], ornament, v))
    return tuple(out)


def semitones(ornament, degree: int, mode: str, alter: int = 0) -> tuple[tuple[float, float], ...]:
    """An ornament's breakpoints in semitones from its note, in a mode (what the singer's pitch track reads)."""
    here = degree_semitones(degree, mode, alter)
    return tuple((float(f), float(degree_semitones(degree + int(s), mode) - here)) for f, s in ornament)


# ---------------------------------------------------------------- what the tune allows


def _where(genome: Genome) -> dict[str, list[tuple[str, int]]]:
    """For each phrase, the sections that sing or play it and how many times each does."""
    out: dict[str, list[tuple[str, int]]] = {}
    for name, section in genome.sections.items():
        for pid in set(section.phrases):
            out.setdefault(pid, []).append((name, section.phrases.count(pid)))
    return out


def room(genome: Genome) -> dict[str, int]:
    """How many variant-carrying notes each section can hold: SHARE of its sung notes, rounded down."""
    return {name: int(SHARE * sum(len(genome.phrases[p].sung) for p in s.phrases) + 1e-9)
            for name, s in genome.sections.items() if any(genome.phrases[p].sung for p in s.phrases)}


def load_of(genome: Genome, variants) -> dict[str, int]:
    """How many of each section's sung notes carry a variant (a phrase sung twice counts twice)."""
    where = _where(genome)
    used: dict[str, int] = {}
    for v in variants:
        for name, times in where.get(v.phrase, ()):
            used[name] = used.get(name, 0) + times
    return used


def _check(genome: Genome, v: Variant) -> str | None:
    """Why one variant can't be sung, on its own; None if it can."""
    meter = genome.meter
    phrase = genome.phrases.get(v.phrase)
    if phrase is None:
        return f"the genome has no phrase {v.phrase!r}"
    notes = phrase.sung
    if not 0 <= v.note < len(notes):
        return f"phrase {v.phrase} has no note {v.note}"
    if v.kind not in KINDS:
        return f"{v.kind!r} isn't a kind of variant ({', '.join(KINDS)})"
    if not (v.source in SOURCES or v.source.startswith("sung:")):
        return f"source {v.source!r} is none of drift, edit or sung:<name>"
    if v.key in protected(genome):
        return f"{v.phrase} note {v.note} is a hook or the refrain's first line, sung as written"
    if v.key in _facts(genome)["approach"] and v.kind in TAIL + RHYTHM + ("leap",):
        return f"{v.phrase} note {v.note} leads into a hook, which keeps its way in"
    n = notes[v.note]
    last = v.note == len(notes) - 1
    nxt = notes[v.note + 1] if not last else None
    if n.alter:
        return f"{v.phrase} note {v.note} is chromatic; variants keep to the song's scale"
    if v.kind in ORNAMENTS:
        if v.degree is not None or v.shift:
            return f"an ornament changes neither the note's degree nor its time"
        steps = tuple(v.steps)
        if not steps or any(not 0.0 <= f <= 1.0 for f, _ in steps) or [f for f, _ in steps] != sorted(f for f, _ in steps):
            return "an ornament's breakpoints are fractions of the note, in order"
        if v.kind not in QUICK and any(not in_scale(genome, n.degree + s) for _, s in steps):
            return "an ornament's tones keep to the song's scale"
        if any(abs(s) > 4 for _, s in steps):
            return "an ornament keeps within a few steps of its note"
        if v.kind in ("mordent", "turn", "neighbour") and any(abs(s) > 1 for _, s in steps):
            return f"a {v.kind} turns a single step from its note"
        if v.kind in TAIL:
            if nxt is None or nxt.onset != n.onset + n.dur:
                return f"a {v.kind} leads into the next note of its line, so it can't be on a line's last note"
            gap = nxt.degree - n.degree
            if v.kind == "anticipation" and (steps[-1][1] != gap or gap == 0):
                return "an anticipation sings the next note's pitch early"
            if v.kind == "passing":  # a quick waypoint through the degree between, across a third only
                inside = [s for _, s in steps if s != 0]
                if abs(gap) != 2 or inside != [int(np.sign(gap))]:
                    return "a passing tone slides through the one degree between a note and the next, a third away"
        elif steps[-1][1] != 0:
            return "a grace, mordent, turn or neighbour comes back to its note"
    elif v.kind == "leap":
        if v.steps or v.shift or v.degree is None:
            return "a leap moves the note to another degree, and only that"
        if last:
            return "a line's last note keeps its target"
        lo, hi = _facts(genome)["range"]
        if not lo <= v.degree <= hi:
            return f"degree {v.degree} is outside the song's range ({lo} to {hi})"
        if not in_scale(genome, v.degree):
            return f"degree {v.degree} isn't in the song's scale"
        if not chord_tone(chord_under(phrase, n.onset, meter), v.degree):
            return f"degree {v.degree} isn't a tone of the chord under it"
        if v.degree == n.degree or abs(v.degree - n.degree) > 2:
            return "a leap moves the note by a step or two of the scale"
        for other in (notes[v.note - 1] if v.note else None, nxt):
            if other is not None and abs(v.degree - other.degree) > max(4, abs(n.degree - other.degree)):
                return "a leap grows to a fifth at most"
    else:  # rhythm
        if v.steps or v.degree is not None or not v.shift:
            return "a rhythm variant only moves the note's onset"
        if stressed(n.onset, meter):
            return "a stressed note stays on its beat"
        if last or v.note == 0:
            return "a line's first and last notes keep their time"
        before = notes[v.note - 1]
        if before.onset + before.dur != n.onset:
            return "a rhythm variant needs the note before it sung right up to it"
        onset = n.onset + v.shift
        foot = (n.onset // meter.foot) * meter.foot
        if stressed(onset, meter) or not foot < onset < foot + meter.foot:
            return "a moved note stays weak, in its foot"
        if onset - before.onset < SHORTEST - 1e-9 or n.onset + n.dur - onset < SHORTEST - 1e-9:
            return f"a moved note and the one before it each keep at least {SHORTEST:g} grid unit"
        if v.kind == "dotted" and before.dur != n.dur:
            return "dotted makes an even pair long-short"
        if v.kind == "even" and (before.dur == n.dur or stressed(before.onset, meter)):
            return "even evens an uneven pair of weak notes"
    return None


def problems(genome: Genome, variants) -> list[str]:
    """Everything wrong with a set of variants for a genome, one plain sentence each; [] if none."""
    variants = parse(variants)
    out = [f"{v.phrase} note {v.note} ({v.kind}): {why}" for v in variants if (why := _check(genome, v))]
    keys = [v.key for v in variants]
    for key in sorted({k for k in keys if keys.count(k) > 1}):
        out.append(f"{key[0]} note {key[1]} carries more than one variant")
    for a in variants:
        for b in variants:
            if a.phrase == b.phrase and b.note == a.note + 1:
                out.append(f"{a.phrase} notes {a.note} and {b.note} are neighbours; variants keep a note apart")
    for pid in sorted({v.phrase for v in variants if v.phrase in genome.phrases}):
        phrase = genome.phrases[pid]
        sung = realized(phrase, [v for v in variants if v.phrase == pid and not _check(genome, v)])
        if _moves([p.degree for p in sung]) != phrase.contour():
            out.append(f"{pid}: its contour would change")
    cap, used = room(genome), load_of(genome, variants)
    for name, n in sorted(used.items()):
        if n > cap.get(name, 0):
            out.append(f"the {name} would carry {n} variants; it holds at most {cap.get(name, 0)}")
    return out


def fits(genome: Genome, variants, v: Variant) -> bool:
    """Whether a variant can join a set that is already sound."""
    if any(u.phrase == v.phrase and abs(u.note - v.note) <= 1 for u in variants):
        return False
    return not problems(genome, tuple(variants) + (v,))


def _fractions(genome: Genome, n, seconds: list[float]) -> list[float]:
    """Seconds into a note's vowel as fractions of it, at the song's own tempo, rounded (so records are stable)."""
    vowel = n.dur * _seconds_per_unit(genome) - CODA
    return [round(min(0.9, max(0.0, s / vowel)), 3) for s in seconds]


@_per_genome
def candidates(genome: Genome) -> tuple[Variant, ...]:
    """Every single variant the tune allows, in a fixed order: what the drift chooses from and a
    person exploring the song can pick from."""
    meter = genome.meter
    unit = _seconds_per_unit(genome)
    out: list[Variant] = []
    for pid in sorted(genome.phrases):
        phrase = genome.phrases[pid]
        notes = phrase.sung
        for k, n in enumerate(notes):
            if (pid, k) in protected(genome) or n.alter:
                continue
            seconds = n.dur * unit
            last = k == len(notes) - 1
            nxt = notes[k + 1] if not last else None
            up, down = neighbour(genome, n.degree, 1) - n.degree, neighbour(genome, n.degree, -1) - n.degree
            offer: list[Variant] = []
            if seconds >= LONG_ENOUGH["grace"]:
                (f,) = _fractions(genome, n, [GRACE])
                offer += [Variant(pid, k, "grace", steps=((0.0, up), (f, 0))),
                          Variant(pid, k, "grace", steps=((0.0, down), (f, 0)))]
            # a mordent's and a turn's tones pass as quickly as a passing tone, so they turn on the mode's next
            # step even where the song's scale has a gap (a pentatonic turn a third wide sounds lopsided)
            if seconds >= LONG_ENOUGH["mordent"]:
                a, b = _fractions(genome, n, [0.05, 0.05 + TONE])
                offer += [Variant(pid, k, "mordent", steps=((a, 1), (b, 0))),
                          Variant(pid, k, "mordent", steps=((a, -1), (b, 0)))]
            if seconds >= LONG_ENOUGH["turn"]:
                a, b, c = _fractions(genome, n, [TONE, 2 * TONE, 3 * TONE])
                offer += [Variant(pid, k, "turn", steps=((0.0, 1), (a, 0), (b, -1), (c, 0)))]
            if seconds >= LONG_ENOUGH["neighbour"]:  # held longer: a step of the song's own scale, or none
                a, b = NEIGHBOUR
                offer += [Variant(pid, k, "neighbour", steps=((a, s), (b, 0))) for s in (up, down) if abs(s) == 1]
            if nxt is not None and nxt.onset == n.onset + n.dur:
                gap = nxt.degree - n.degree
                # the voice leaves this note for the next about 0.08 s before the next begins (a glide's lead)
                if abs(gap) == 2 and seconds >= LONG_ENOUGH["passing"]:  # a third: slide through the degree between
                    (f,) = _fractions(genome, n, [seconds - 0.08 - PASSING])
                    offer.append(Variant(pid, k, "passing", steps=((0.0, 0), (f, int(np.sign(gap))))))
                if gap and not stressed(n.onset, meter) and stressed(nxt.onset, meter) \
                        and seconds >= LONG_ENOUGH["anticipation"]:
                    (f,) = _fractions(genome, n, [seconds - 0.08 - ANTICIPATION])
                    offer.append(Variant(pid, k, "anticipation", steps=((0.0, 0), (max(f, 0.35), gap))))
            if not last:
                lo, hi = _facts(genome)["range"]
                for d in range(max(lo, n.degree - 3), min(hi, n.degree + 3) + 1):
                    if d != n.degree:
                        offer.append(Variant(pid, k, "leap", degree=d))
                if k > 0 and not stressed(n.onset, meter):
                    before = notes[k - 1]
                    if before.onset + before.dur == n.onset:
                        if before.dur == n.dur:
                            offer.append(Variant(pid, k, "dotted", shift=n.dur / 2))
                        elif not stressed(before.onset, meter):
                            offer.append(Variant(pid, k, "even", shift=(before.dur - n.dur) / 2))
            out += [v for v in offer if not problems(genome, (v,))]
    return tuple(out)


# ---------------------------------------------------------------- reading them


def describe(genome: Genome, v: Variant, lyrics=None) -> str:
    """A variant in words: 'a grace note from above on "it" (verse, line 1)'. With a rendition's words (an
    arrange.Lyrics), the syllable named is the one it sang there; otherwise the seed's."""
    phrase = genome.phrases.get(v.phrase)
    where = _line(genome, v.phrase)
    sung = _sung_syllable(genome, v.phrase, v.note, lyrics) or _syllable(genome, v.phrase, v.note)
    on = f'"{sung}"' if sung else f"note {v.note + 1}"
    if v.kind == "leap" and phrase is not None:
        old = phrase.sung[v.note].degree
        what = f"{on} sung {_interval(abs(v.degree - old))} {'higher' if v.degree > old else 'lower'}"
        return f"{what} ({where})"
    if v.kind in ("grace", "mordent", "neighbour"):
        first = next((s for _, s in v.steps if s), 0)
        way = "from above" if first > 0 else "from below"
        name = {"grace": "a grace note", "mordent": "a mordent", "neighbour": "a neighbour note"}[v.kind]
        return f"{name} {way} on {on} ({where})"
    if v.kind == "turn":
        return f"a turn on {on} ({where})"
    if v.kind == "passing":
        return f"{on} slides through the note{'s' if len([s for _, s in v.steps if s]) > 1 else ''} between it and the next ({where})"
    if v.kind == "anticipation":
        return f"{on} reaches the next note's pitch early ({where})"
    if v.kind == "dotted":
        return f"{on} comes a little late, dotting the pair ({where})"
    if v.kind == "even":
        return f"{on} evened with the note before it ({where})"
    return f"a {v.kind} on {on} ({where})"


def _interval(steps: int) -> str:
    return {1: "a step", 2: "a third", 3: "a fourth", 4: "a fifth"}.get(steps, f"{steps} steps")


def _line(genome: Genome, pid: str) -> str:
    """Where a phrase is sung, for reading: 'verse, line 1', 'refrain, line 3 and the intro'."""
    places = []
    for name, section in genome.sections.items():
        if pid in section.phrases and genome.phrases[pid].sung:
            lines = [str(i + 1) for i, p in enumerate(section.phrases) if p == pid]
            label = "lines" if len(lines) > 1 else "line"
            places.append(f"{name}, {label} {' and '.join(lines)}" if section.lyrics else f"the {name}")
    sung = [p for p in places if "," in p]
    return "; ".join(sung + [p for p in places if "," not in p][:1]) if places else pid


def _syllable_in(line: str, k: int) -> str:
    """The k-th sung syllable of a lyric line: a word, or a syllable marked where it sits in its word
    ("num-", "-bers")."""
    at = 0
    for word in line.split():
        pieces = [p.replace("*", "").strip(".,;:!?\"") for p in word.split("-") if p]
        if k < at + len(pieces):
            j = k - at
            if len(pieces) == 1:
                return pieces[0]
            return ("" if j == 0 else "-") + pieces[j] + ("" if j == len(pieces) - 1 else "-")
        at += len(pieces)
    return ""


@_per_genome
def _syllable(genome: Genome, pid: str, k: int) -> str:
    """The seed's syllable on a phrase's note, where a fixed block or the first seed verse sings it."""
    for section in genome.sections.values():
        if pid not in section.phrases or not section.lyrics:
            continue
        i = section.phrases.index(pid)
        block = genome.seed_verses[0] if section.lyrics == "verse" and genome.seed_verses else genome.fixed.get(section.lyrics)
        if block and i < len(block):
            return _syllable_in(block[i], k)
    return ""


def _sung_syllable(genome: Genome, pid: str, k: int, lyrics) -> str:
    """The syllable a rendition's words sang on a phrase's note, the first place they sang it."""
    for sung in getattr(lyrics, "sections", ()) or ():
        if not sung.lines:
            continue
        phrases = genome.section(sung.section).phrases
        if pid in phrases and phrases.index(pid) < len(sung.lines):
            return _syllable_in(sung.lines[phrases.index(pid)], k)
    return ""


# ---------------------------------------------------------------- how far a tune has travelled


def melody(genome: Genome, variants=(), mode: str | None = None, ornaments: bool = False) -> list[tuple[str, list[float]]]:
    """Each sung phrase's pitches (semitones above the tonic) in the song's own mode, as sung with the
    variants; with ornaments, each ornament tone as a note of its own."""
    mode = mode or genome.seed_params.get("mode", "ionian")
    out = []
    for pid in sorted(genome.phrases):
        phrase = genome.phrases[pid]
        if not phrase.sung:
            continue
        pitches: list[float] = []
        for p in realized(phrase, variants):
            base = float(degree_semitones(p.degree, mode, p.alter))
            orn = semitones(p.ornament, p.degree, mode, p.alter) if ornaments else ()
            if orn and orn[0][0] > 0:
                pitches.append(base)  # the note itself, before the ornament turns away from it
            pitches += [base + s for _, s in orn] if orn else [base]
        out.append((pid, pitches))
    return out


def dtw(a, b) -> float:
    """Dynamic time warping between two sequences of relative moves (semitones, clipped to an octave):
    the cost of the cheapest alignment, each move's difference in semitones, an insertion or deletion
    costing its move's size (at least a semitone)."""
    a = np.clip(np.asarray(a, dtype=float), -12, 12)
    b = np.clip(np.asarray(b, dtype=float), -12, 12)
    n, m = len(a), len(b)
    cost = np.full((n + 1, m + 1), np.inf)
    cost[0, 0] = 0.0
    for i in range(1, n + 1):
        cost[i, 0] = cost[i - 1, 0] + max(abs(a[i - 1]), 1.0)
    for j in range(1, m + 1):
        cost[0, j] = cost[0, j - 1] + max(abs(b[j - 1]), 1.0)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i, j] = min(cost[i - 1, j - 1] + abs(a[i - 1] - b[j - 1]),
                             cost[i - 1, j] + max(abs(a[i - 1]), 1.0),
                             cost[i, j - 1] + max(abs(b[j - 1]), 1.0))
    return float(cost[n, m])


def distance(genome: Genome, a=(), b=(), ornaments: bool = True) -> float:
    """How far two ways of singing the tune are apart, as the lineage gate will judge contour: each
    phrase's relative moves compared by dynamic time warping, the hooks' phrases counting double,
    normalized to semitones per move. 0 for the same tune; a whole unrelated tune scores several."""
    weights = {h["phrase"]: 2.0 for h in genome.hooks}
    total = moves = 0.0
    for (pid, x), (_, y) in zip(melody(genome, a, ornaments=ornaments), melody(genome, b, ornaments=ornaments)):
        w = weights.get(pid, 1.0)
        total += w * dtw(np.diff(x), np.diff(y))
        moves += w * (max(len(x), len(y)) - 1)
    return round(total / max(moves, 1.0), 4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m songbird.variants",
                                     description="List every variant a song's tune allows.")
    parser.add_argument("genome", help="path to a genome JSON file")
    parser.add_argument("--json", action="store_true", help="print them as JSON")
    args = parser.parse_args(argv)
    genome = load(args.genome)
    offered = candidates(genome)
    if args.json:
        print(json.dumps([v.to_dict() for v in offered], indent=1))
        return 0
    counts: dict[str, int] = {}
    for v in offered:
        counts[v.kind] = counts.get(v.kind, 0) + 1
        print(f"{v.phrase:4s} {v.note:2d} {v.kind:12s} {describe(genome, v)}")
    print(f"\n{len(offered)} variants: " + ", ".join(f"{k} {n}" for k, n in counts.items()))
    print("each section holds at most: " + ", ".join(f"{k} {n}" for k, n in room(genome).items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
