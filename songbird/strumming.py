"""A strumming hand: the grooves a guitarist strums, how the hand moves between them, and what one stroke does
to the strings. Shared by the seed's band (songbird.band) and the styles' guitars (songbird.idioms).

A groove is one bar of the hand's pendulum, written as slots: eighths in simple time (sixteenths in a slow
song's busier grooves), three to a beat in compound time. In simple time the hand goes down on the even slots
and up on the odd ones whether it touches the strings or not, so a groove mostly says where it touches them:

    D  a down stroke                           d  a light down
    U  an up stroke, the top three strings     u  a light up, the top two
    x  a chop: down across strings the fretting hand has deadened
    B  the thumb (or the pick) on the chord's bass string        b  on the other bass string
    .  the hand passes without touching

Accents lean on the backbeat, as folk, country and pop strummers do: 2 and 4 the strongest, 1 a little under,
3 under that, the ups about half. A down on 1 (or where a chord starts) crosses every string; a down on a
backbeat or between beats takes the upper four or five; one on 3 the lower five.

Each player has a home groove for the song, drawn from the grooves its style plays by the band's density and
the song's tempo, and repeats it through a section as a player does. A section's energy moves first how many
strings a down crosses and how hard, and only past a point a step along the ladder to a quieter or busier
groove. A phrase's last bar is where a player varies: the last beat left to ring, or a light up filling a rest.
Now and then an up becomes a ghost, the pick brushing the top strings. The up just before a chord change is
often the open strings, the fretting hand already lifting for the next shape (softer, and only where the open
strings don't rub what is sung), or left out.

A stroke meets its strings 4 to 7 ms apart (2 to 3 hard or fast, up to 11 on a slow, soft rake), never taking
more than 30% of a slot, and a little quicker as the hand accelerates through it; it starts before the beat so
that its weight lands on it. In the lazier grooves the ups sit a few milliseconds late, each player by its own
amount; in the driving ones they are on time.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Groove:
    name: str
    slots: str  # one bar
    busy: float  # 0..1, its place on the ladder
    lazy: bool = True  # its ups may sit late


# Simple time, four beats: eighths, then the slow song's sixteenths. Ladders are ordered by busyness.
FOUR = (
    Groove("half", "D...D..U", 0.15),
    Groove("quarters", "D.D.D.D.", 0.25),
    Groove("sparse", "D...D.DU", 0.3),
    Groove("tresillo", "D..U..D.", 0.35),
    Groove("boom-strum", "B.dUb.dU", 0.45),
    Groove("calypso", "D..U.UDU", 0.45),
    Groove("lilt", "D.DUD.DU", 0.5),
    Groove("faithful", "D.DU.UDU", 0.55),
    Groove("backbeat", "D.xUD.xU", 0.6),
    Groove("downs", "DDDDDDDD", 0.7, lazy=False),  # every eighth a down, against the pendulum: indie's
    Groove("drive", "D.DUDUDU", 0.75, lazy=False),
    Groove("eighths", "DUDUDUDU", 0.85, lazy=False),
)
FOUR_SIXTEENTHS = (
    Groove("slow-ballad", "D...D.DUD...D.DU", 0.45),
    Groove("slow-folk", "D..U..D.D.DU.UDU", 0.6),
    Groove("slow-faithful", "D.DU.UDUD.DU.UDU", 0.75, lazy=False),
    Groove("slow-backbeat", "D.DUx.DUD.DUx.DU", 0.8, lazy=False),
)
THREE = (
    Groove("waltz", "D.D.D.", 0.25),
    Groove("boom-waltz", "B.d.d.", 0.3),
    Groove("waltz-hold", "D...DU", 0.35),
    Groove("waltz-lift", "D..UDU", 0.5),
    Groove("waltz-full", "D.DUDU", 0.7),
)
TWO = (
    Groove("two", "D.D.", 0.25),
    Groove("two-up", "D.DU", 0.5),
    Groove("two-full", "DUDU", 0.75, lazy=False),
)
# Compound time: a bar of two dotted beats written out (a bar of more repeats its first beat's three slots).
COMPOUND = (
    Groove("dotted", "D..D..", 0.2),
    Groove("rock", "D.UD.U", 0.45),
    Groove("rock-lift", "D..DdU", 0.5),
    Groove("six-eighths", "DUDUDU", 0.6),  # a slow six-eight in straight eighths, on 1 and 4
    Groove("lilt-six", "D.uDdU", 0.65),
    Groove("jig", "DdUDdU", 0.8, lazy=False),
    Groove("jig-rock", "DUDDUD", 0.85, lazy=False),
)

# The grooves a style's guitar strums (by name); a style not listed strums any.
STYLE_GROOVES = {
    "ballad": ("half", "sparse", "calypso", "lilt", "faithful", "drive", "slow-ballad", "slow-folk", "slow-faithful",
               "waltz", "waltz-hold", "waltz-lift", "waltz-full", "dotted", "rock", "rock-lift", "six-eighths",
               "lilt-six", "jig", "two", "two-up", "two-full"),
    "country": ("quarters", "sparse", "boom-strum", "faithful", "backbeat", "drive", "slow-ballad", "slow-faithful",
                "boom-waltz", "waltz-hold", "waltz-lift", "waltz-full"),
    "indie": ("half", "sparse", "tresillo", "faithful", "backbeat", "downs", "drive", "eighths", "slow-folk",
              "slow-backbeat"),
    "synthfolk": ("sparse", "tresillo", "calypso", "faithful", "drive", "eighths", "slow-folk", "slow-faithful",
                  "slow-backbeat"),
}
# The open strings of a guitar in standard tuning, low to high (MIDI, before any capo).
OPEN = (40, 45, 50, 55, 59, 64)


def ladder(beats: int, compound: bool, bpm: float) -> tuple[Groove, ...]:
    """The grooves a bar of this meter can take at this tempo, ordered by busyness."""
    if compound:
        return COMPOUND
    if beats == 3:
        return THREE
    if beats == 2:
        return TWO
    if beats == 4 and bpm >= 150:  # a fast song: the hand can't keep eighths up, or need to
        return tuple(g for g in FOUR if g.busy <= 0.6)
    if beats == 4 and bpm < 85:  # a slow one has room for sixteenths
        return tuple(sorted(FOUR + FOUR_SIXTEENTHS, key=lambda g: g.busy))
    return FOUR


@dataclass(frozen=True)
class Stroke:
    at: float  # beats from the bar line
    kind: str  # D d U u x B b
    accent: float
    flag: str = ""  # "open": the open strings, the fretting hand lifting for the next chord
    slot: int = 0  # its slot in the bar
    slots: int = 8  # how many slots the bar has


def _seed(*keys) -> np.random.Generator:
    digest = hashlib.sha256("|".join(str(k) for k in keys).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "little"))


class Hand:
    """One player's strumming hand through a song."""

    def __init__(self, seed: int, part: str, *, beats: int, compound: bool, bpm: float, density: float,
                 style: str = "ballad", base: str | None = None):
        self.part, self.beats, self.compound, self.bpm, self.density = part, beats, compound, float(bpm), density
        self.seed = seed
        rng = _seed(seed, "strumming", part)
        allowed = STYLE_GROOVES.get(style)
        full = ladder(beats, compound, bpm)
        self.ladder = tuple(g for g in full if allowed is None or g.name in allowed) or full
        target = 0.3 + 0.55 * density + rng.normal(0.0, 0.1)
        self.home = int(np.argmin([abs(g.busy - target) for g in self.ladder]))
        named = {"lilt": "lilt", "strum": "faithful"}.get(base or "")
        if named in [g.name for g in self.ladder]:  # the seed band's family is its home groove (the lilt the lilt)
            self.home = [g.name for g in self.ladder].index(named)
        self.lean = float(rng.uniform(0.002, 0.008))  # seconds this player's ups sit late in a lazy groove
        self.reach = float(rng.uniform(0.0, 1.0))  # how often a down comes in above the lowest string
        self.lifts = float(rng.uniform(0.35, 0.75))  # how often the up before a change is the open strings
        self.gap = float(rng.uniform(0.0045, 0.0065))  # seconds between strings on an ordinary stroke
        self._held: dict[int, tuple[Groove, float]] = {}

    def groove(self, section: int, energy: float, role: str = "") -> tuple[Groove, float]:
        """The groove held through a section, and its span (0..1: how much of the strings and force the
        section's energy asks of a down). Energy moves the span first; only far from the middle a step along
        the ladder."""
        if section not in self._held:
            rng = _seed(self.seed, self.part, "section", section)
            lean = energy - 0.55 + rng.normal(0.0, 0.08)
            step = int(np.sign(lean)) if abs(lean) > 0.22 else 0
            if role == "bridge" and rng.random() < 0.4:  # a bridge often changes the feel
                step += 1 if rng.random() < 0.5 else -1
            k = int(np.clip(self.home + step, 0, len(self.ladder) - 1))
            self._held[section] = (self.ladder[k], float(np.clip(0.5 + 1.6 * (energy - 0.55), 0.0, 1.0)))
        return self._held[section]

    def bar(self, groove: Groove, rng: np.random.Generator, *, last: bool = False,
            changes: tuple[float, ...] = ()) -> list[Stroke]:
        """One bar's strokes. last: the phrase's last bar; changes: beats in the bar (or at its end, `beats`)
        where a new chord starts, other than its first."""
        slots = groove.slots
        if self.compound and self.beats != 2:
            slots = slots[:3] * self.beats
        n = len(slots)
        per = n / self.beats  # slots a beat
        change_slots = {int(round(b * per)) for b in changes}
        ring = last and rng.random() < 0.3  # a phrase's end: its last beat left to ring
        fill = last and not ring and rng.random() < 0.4
        out: list[Stroke] = []
        for k, ch in enumerate(slots):
            at = k / per
            downbeat = abs(at - round(at)) < 1e-9
            if ring and at >= self.beats - 1 - 1e-9 and at > 0:
                break
            if ch == "." and fill and not self.compound and k % 2 == 1 and at > self.beats / 2:
                ch = "u"  # a phrase's last bar fills a rest
            if ch == ".":
                continue
            flag = ""
            if ch in "Uu":
                if rng.random() < 0.05:
                    ch = "u"  # a ghost: the pick brushing the top strings
                if (k + 1) in change_slots:
                    r = rng.random()
                    if r < self.lifts:
                        flag = "open"
                    elif r < self.lifts + 0.2:
                        continue
            accent = self._accent(ch, at, downbeat)
            if ch == "u" and slots[k] == "U":
                accent = 0.25
            out.append(Stroke(at, ch, accent, flag, k, n))
        return out

    def _accent(self, ch: str, at: float, downbeat: bool) -> float:
        if ch == "x":
            return 0.8
        if ch in "Bb":
            return 0.85 if at == 0 else 0.75
        if ch in "Dd":
            light = 1.0 if ch == "D" else 0.7
            if not downbeat:
                return 0.6 * light
            beat = int(round(at))
            if self.compound:
                return (0.95 if beat == 0 else 0.85) * light
            if self.beats == 4:
                return {0: 0.85, 1: 1.0, 2: 0.78, 3: 1.0}.get(beat, 0.8) * light
            if self.beats == 3:
                return (0.9 if beat == 0 else 0.75) * light
            return (0.85 if beat == 0 else 1.0) * light
        return 0.5 if ch == "U" else 0.32

    def late(self, groove: Groove) -> float:
        """Seconds an up stroke sits behind the grid in this groove."""
        return self.lean if groove.lazy else 0.0

    # --- what a stroke does to the strings ------------------------------------------------------------

    def strings(self, stroke: Stroke, notes: list[float], span: float, rng: np.random.Generator, *,
                first: bool) -> list[float]:
        """The strings a stroke meets, in the order it meets them (notes low to high). first: the stroke where
        the bar or the chord starts."""
        n, kind = len(notes), stroke.kind
        if n == 0:
            return []
        if kind == "B":
            return [notes[0]]
        if kind == "b":
            return [notes[min(1, n - 1)]]
        if kind == "x":
            return list(notes[-min(n, 5):])
        if kind in "Dd":
            beat = int(round(stroke.at)) if abs(stroke.at - round(stroke.at)) < 1e-9 else -1
            wide = 4 + int(round(2 * span))  # how many strings a full down crosses at this energy (4..6)
            if kind == "d":
                return list(notes[-min(n, 3 if rng.random() < 0.5 else 4):])
            if first:
                return list(notes)
            if beat < 0 or (self.beats == 4 and beat in (1, 3)) or self.compound and beat > 0:
                return list(notes[-min(n, wide - 1):])  # a backbeat's or an off-beat's down: the upper strings
            if rng.random() < 0.15 + 0.3 * self.reach and n > 4:
                return list(notes[1:min(n, wide + 1)])  # the pick comes in above the lowest string
            return list(notes[:max(3, min(n, wide))])  # 3's down: the lower strings
        if kind == "U":
            r = rng.random()
            k = 2 if r < 0.2 else 4 if r > 0.85 else 3
            return list(notes[-min(n, k):])[::-1]
        return list(notes[-min(n, 2):])[::-1]  # u

    def voiced(self, stroke: Stroke, hit: list[float], vel: float, slot: float, rng: np.random.Generator,
               late: float = 0.0) -> list[tuple[float, float, float]]:
        """(pitch, velocity, seconds from the grid) for each string a stroke meets; slot: seconds a slot lasts."""
        n = len(hit)
        if n == 0:
            return []
        gap = self.gap * (1.45 - 0.9 * vel) * float(np.clip((100.0 / self.bpm) ** 0.5, 0.8, 1.25))
        if stroke.kind in "Uu":
            gap *= 0.85
        elif stroke.kind == "x":
            gap *= 0.7
        gap = float(np.clip(gap, 0.002, 0.011))
        if n > 1:
            gaps = gap * np.linspace(1.08, 0.9, n - 1) * rng.uniform(0.9, 1.1, n - 1)  # the hand accelerates
            total = float(gaps.sum())
            if total > 0.3 * slot:
                gaps *= 0.3 * slot / total
            times = np.concatenate([[0.0], np.cumsum(gaps)])
        else:
            times = np.zeros(1)
        lead = -0.3 * float(times[-1])
        if stroke.kind in "Uu":
            lead += late
        out = []
        for j, p in enumerate(hit):
            x = j / max(n - 1, 1)
            if stroke.kind in "Dxd":  # a down stroke digs into the low strings and lightens as it goes
                v = vel * (1.0 - 0.15 * x)
            elif stroke.kind in "Uu":  # an up meets the top string first, hardest
                v = vel * (0.85 - 0.2 * x)
            else:
                v = vel
            out.append((p, float(np.clip(v * rng.uniform(0.92, 1.06), 0.03, 1.0)), float(lead + times[j])))
        return out


def open_strings(capo: int) -> list[int]:
    """The top three strings open (behind the capo), low to high: what an up meets while the fretting hand lifts."""
    return [p + capo for p in OPEN[3:]]
