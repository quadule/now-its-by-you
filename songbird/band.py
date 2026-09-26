"""The band's arrangement: who plays what, section by section.

A small acoustic folk band backs the singer: a cittern-like lute, a guitar,
a harp, an upright bass, a fiddle, a wooden flute or whistle, a frame drum
and a reed drone (songbird.synth.instruments builds them). What each plays
follows from the section it is in and the section's place in the song:

- Each section has a role (intro, verse, refrain, turn, break, bridge, tag,
  outro) and an energy, which arcs across the song: the verses sparse, each
  refrain fuller than the last, the bridge a different colour under the
  lineage choir, the tag and the ending winding down.
- From role and energy each instrument decides what it does there: comp
  (the harp's picking, the guitar's strums, the bass's line), state the tune
  (the intro, a break, the outro: the lead instrument, with its ornaments),
  quote the refrain's melody (a turn), play a counter-melody drawn from the
  harmony (a refrain), hold a pad (the bridge), answer the singer between
  lines (fills), keep the pulse (the drum), or hold the drone.
- The singer is the point: under words everything comps softer, nothing
  but the doubling lute sits on the sung pitch, counter-lines keep above the
  tune, and fills go where the singer holds a line's last note.
- Every choice is seeded, bar by bar and part by part, so a rendition
  replays exactly, no two bars are quite alike, and a small change to one
  setting changes only what it touches (the drift is meant to be subtle day
  to day).

Band holds the choices a rendition can vary (which instruments play, their
balance, brightness, pattern family, density, swing, wear, ornament, the
arc), with defaults that are the seed's arrangement.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from functools import lru_cache

import numpy as np

from .score import Note
from .theory import MODES, chord_tones, degree_semitones, harmony

INSTRUMENTS = ("lute", "guitar", "harp", "bass", "fiddle", "whistle", "drum", "drone")
PATTERNS = ("lilt", "strum", "pick", "air")
LEADS = ("whistle", "fiddle", "lute")
ROLES = ("intro", "verse", "refrain", "turn", "break", "bridge", "tag", "outro")


@dataclass(frozen=True)
class Band:
    """How the band plays a rendition. Each field has a default (the seed's
    arrangement) and a range the drift and the voice harvest may move it
    through; out-of-range values are clamped, unknown names ignored."""

    # Which instruments play, and their balance: a stem gain for each, 0..2.
    # 0 sits out (its part is not written at all), 1 as arranged, 2 about 6 dB up.
    lute: float = 1.0
    guitar: float = 1.0
    harp: float = 1.0
    bass: float = 1.0
    fiddle: float = 1.0
    whistle: float = 1.0
    drum: float = 1.0
    drone: float = 1.0
    brightness: float = 0.5  # 0..1: gut strings, fingertips, a breathy pipe (0); steel, picks, an edgy bow (1)
    pattern: str = "lilt"  # the accompaniment's family, one of PATTERNS: lilt, strum, pick, air
    density: float = 0.5  # 0..1: roots and a strum a bar (0) to eighth-note picking, walking bass, many fills (1)
    swing: float = 0.0  # 0..1: straight (0) to a triplet lilt (1) on each beat's off-beat half; the singer swings too
    wear: float = 0.25  # 0..1: a new, tight band (0) to an old, loose one (1): detuning, looser time, more noise
    ornament: float = 0.5  # 0..1: plain (0) to much ornamented (1): cuts, rolls, slides, vibrato
    arc: float = 0.75  # 0..1: every section alike (0) to a strong build from the first verse to the last refrain (1)
    lead: str = "whistle"  # who states the tune where nobody sings, one of LEADS: whistle, fiddle, lute
    body: float = 1.0  # 0.8..1.25: the instruments' size; a bigger body resonates lower
    maker: int = 0  # seeds the instruments themselves (bodies, string quirks, the drum's skin), stable per machine
    # Who plays when a style sets the band (songbird.style): instrument -> gain, 0..2, any instrument the
    # registry knows (synth.instruments.known()). Empty: the eight above, as the seed's band always played.
    lineup: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict | None) -> Band:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in known}).clamped()

    def to_dict(self) -> dict:
        return asdict(self)

    def clamped(self) -> Band:
        values = {}
        for f in fields(self):
            v = getattr(self, f.name)
            if f.name == "lineup":  # a mapping, or (name, gain) pairs as an old JSON might hold them
                pairs = v.items() if isinstance(v, dict) else (v or ())
                v = {str(k): float(np.clip(float(g), 0.0, 2.0)) for k, g in pairs}
            elif f.name in INSTRUMENTS:
                v = float(np.clip(float(v), 0.0, 2.0))
            elif f.name in ("brightness", "density", "swing", "wear", "ornament", "arc"):
                v = float(np.clip(float(v), 0.0, 1.0))
            elif f.name == "body":
                v = float(np.clip(float(v), 0.8, 1.25))
            elif f.name == "maker":
                v = int(v)
            elif f.name == "pattern":
                v = v if v in PATTERNS else "lilt"
            elif f.name == "lead":
                v = v if v in LEADS else "whistle"
            values[f.name] = v
        return Band(**values)

    def gain(self, name: str) -> float:
        """An instrument's gain: from the lineup when a style set one, else the eight's own fields."""
        if self.lineup:
            return float(self.lineup.get(name, 0.0))
        return float(getattr(self, name, 0.0)) if name in INSTRUMENTS else 0.0

    def plays(self, name: str) -> bool:
        return self.gain(name) > 0.02


# Timing habits: seconds each part sits against the grid (a bowed note speaks
# late, so a fiddler starts early; the bass sits a hair behind).
LAG = {"lute": 0.0, "guitar": -0.004, "harp": 0.003, "bass": 0.007, "fiddle": -0.014, "whistle": -0.004,
       "drum": 0.0, "drone": 0.0}
GUITAR_TUNING = (40, 45, 50, 55, 59, 64)
REGISTER = {"whistle": (62, 93), "fiddle": (55, 88), "lute": (50, 84)}  # MIDI ranges the players reach
# Each part draws its choices from its own stream, one per bar, so changing what one part plays in one
# bar never re-rolls another's; the numbers only name the streams.
STREAM = {name: k + 1 for k, name in enumerate(INSTRUMENTS)} | {"fills": 20, "quote": 21, "time": 22}


@dataclass
class Section:
    name: str
    role: str
    nth: int  # which time this role comes round, from 0
    count: int  # how many times it comes round
    u0: float
    u1: float
    sung: bool
    energy: float = 0.5
    parts: dict = field(default_factory=dict)  # instrument -> what it does here


@dataclass
class Chord:
    u0: float
    u1: float
    symbol: str
    section: int
    last: bool  # the phrase's last chord


@dataclass
class Tune:
    u0: float
    u1: float  # trimmed where the next note starts
    pitch: int
    vel: float
    sung: bool
    section: int
    first: bool  # a phrase's first note
    last: bool  # a phrase's last note


@dataclass
class Ev:
    """A note in grid units, before it is placed in time. Notes of one part
    at one grid position (a strum, a rolled chord, a note and its grace) share
    their timing."""

    part: str
    u0: float
    u1: float
    pitch: float
    vel: float
    art: str = ""
    shift: float = 0.0  # seconds added to the onset (a strum's spread, a grace note's length)
    length: float = 0.0  # if set, the note's length in seconds (grace notes)
    section: int = 0


class Context:
    """The song laid out on the grid, and the rendition's choices."""

    def __init__(self, genome, params, placed, lead, end, melody):
        self.genome = genome
        self.meter = genome.meter
        self.params = params
        self.band = getattr(params, "band", Band()).clamped()
        self.seed = int(params.seed)
        self.tonic = int(params.tonic)
        self.mode = params.mode
        self.end = float(end)
        self.bar = self.meter.bar
        self.beat = self.meter.beat
        self.beats = max(1, self.bar // self.beat)
        self.compound = self.beat % 3 == 0 and self.beat > 1
        self.sub = self.beat / 3.0 if self.compound else self.beat / 2.0  # the pattern subdivision, in units
        self.foot = max(1, self.meter.foot // self.beat) if self.meter.foot >= self.beat else self.beats
        self.sections: list[Section] = []
        self.chords: list[Chord] = []
        self.tune: list[Tune] = []
        self.phrases: list[tuple[float, float]] = []  # each placed phrase's span, bar line to bar line
        self.choir: list[tuple[float, float, int]] = []  # the lineage voices' notes, where they sing
        self._streams: dict[tuple[str, int], np.random.Generator] = {}
        self._layout(placed, lead, melody)
        self._energy()
        self.scale = self._scale()

    def _layout(self, placed, lead, melody):
        genome, meter = self.genome, self.meter
        rounds: dict[str, int] = {}
        for name, phrase, start, _line in placed:
            section = genome.section(name)  # bridge2: the bridge sung again
            s0, s1 = start + lead, start + lead + phrase.bars * meter.bar
            if self.sections and self.sections[-1].name == name and abs(self.sections[-1].u1 - s0) < 1e-9:
                self.sections[-1].u1 = s1
            else:
                role = _role(name, section)
                self.sections.append(Section(name, role, rounds.get(role, 0), 0, s0, s1, section.lyrics is not None))
                rounds[role] = rounds.get(role, 0) + 1
            index = len(self.sections) - 1
            self.phrases.append((s0, s1))
            beats_per_bar = meter.bar / meter.beat
            for b, chords in enumerate(phrase.chords):
                bar_u = s0 + b * meter.bar
                starts = [round(k * beats_per_bar / len(chords)) * meter.beat for k in range(len(chords))]
                ends = starts[1:] + [meter.bar]
                for k, (symbol, a, z) in enumerate(zip(chords, starts, ends)):
                    last = b == len(phrase.chords) - 1 and k == len(chords) - 1
                    self.chords.append(Chord(bar_u + a, bar_u + z, symbol, index, last))
        for s in self.sections:
            s.count = rounds[s.role]
        ordered = sorted(melody, key=lambda m: m["u"])
        for i, m in enumerate(ordered):
            u1 = min(m["u_end"], ordered[i + 1]["u"]) if i + 1 < len(ordered) else self.end
            self.tune.append(Tune(m["u"], u1, int(m["pitch"]), float(m["vel"]), bool(m["syllable"]),
                                  self.section_at(m["u"]), m["index"] == 0, bool(m["line_end"])))
            if m["syllable"] and m.get("choir"):  # each lineage voice's harmony, as realize() gives it
                for role in range(int(getattr(self.params, "choir", 0))):
                    self.choir.append((m["u"], u1, harmony(int(m["pitch"]), m["chord"], self.tonic, self.mode, role)))

    def section_at(self, u: float) -> int:
        for i, s in enumerate(self.sections):
            if s.u0 - 1e-9 <= u < s.u1 - 1e-9:
                return i
        return 0 if u < self.sections[0].u0 else len(self.sections) - 1

    def _energy(self):
        """Each section's energy, 0..1, arcing across the song."""
        base: dict[int, float | None] = {}
        for i, s in enumerate(self.sections):
            x = s.nth / (s.count - 1) if s.count > 1 else 1.0
            base[i] = {"intro": 0.38, "verse": 0.3 + 0.2 * x, "refrain": 0.55 + 0.35 * x, "break": 0.7,
                       "bridge": 0.5, "tag": 0.55, "outro": 0.35}.get(s.role)
        for i, s in enumerate(self.sections):
            if base[i] is None:  # a turn sits between its neighbours, a breath lower
                around = [base[j] for j in (i - 1, i + 1) if 0 <= j < len(self.sections) and base[j] is not None]
                base[i] = (sum(around) / len(around) if around else 0.5) - 0.05
        for i, s in enumerate(self.sections):
            s.energy = float(np.clip(0.55 + self.band.arc * (base[i] - 0.55), 0.0, 1.0))

    def _scale(self) -> set[int]:
        """The pitch classes the tune uses (a pentatonic tune keeps its fills pentatonic)."""
        used = {t.pitch % 12 for t in self.tune}
        if len(used) < 5:
            used |= {(self.tonic + s) % 12 for s in MODES[self.mode]}
        return used

    # --- random streams: one per part per bar --------------------------------------

    def rand(self, part: str, u: float) -> np.random.Generator:
        bar = int(np.floor((u - self.sections[0].u0) / self.bar + 1e-9))
        key = (part, bar)
        if key not in self._streams:
            self._streams[key] = np.random.default_rng([self.seed & 0xFFFFFFFF, 0xBA4D, STREAM[part], bar + 4096])
        return self._streams[key]

    # --- the song's facts ---------------------------------------------------------

    def chords_in(self, section: int) -> list[Chord]:
        return [c for c in self.chords if c.section == section]

    def tune_in(self, section: int) -> list[Tune]:
        return [t for t in self.tune if t.section == section]

    def chord_at(self, u: float) -> Chord:
        for c in self.chords:
            if c.u0 - 1e-9 <= u < c.u1 - 1e-9:
                return c
        return self.chords[-1] if u >= self.chords[-1].u0 else self.chords[0]

    def sung_at(self, u: float) -> Tune | None:
        return next((t for t in self.tune if t.sung and t.u0 - 1e-9 <= u < t.u1 - 1e-9), None)

    def voices_at(self, u: float) -> list[int]:
        """Every pitch being sung at u: the singer's and the lineage voices'."""
        sung = self.sung_at(u)
        return ([sung.pitch] if sung else []) + [p for u0, u1, p in self.choir if u0 - 1e-9 <= u < u1 - 1e-9]

    def pcs(self, symbol: str) -> tuple[int, int, int]:
        return tuple((self.tonic + t) % 12 for t in chord_tones(symbol, self.mode))

    def root(self, symbol: str) -> int:
        return self.pcs(symbol)[0]

    def energy_at(self, u: float) -> float:
        """The section's energy, leaning toward a louder next section over the last bar."""
        i = self.section_at(u)
        s = self.sections[i]
        e = s.energy
        if i + 1 < len(self.sections) and u > s.u1 - self.bar:
            nxt = self.sections[i + 1].energy
            if nxt > e:
                e += 0.5 * (nxt - e) * (u - (s.u1 - self.bar)) / self.bar
        return e

    def on(self, name: str) -> bool:
        return self.band.plays(name)

    def breath(self, u: float) -> float:
        """Players breathe with the phrase: a little fuller through a line's middle than at its ends."""
        for p0, p1 in self.phrases:
            if p0 - 1e-9 <= u < p1 - 1e-9:
                return 0.96 + 0.08 * float(np.sin(np.pi * (u - p0) / (p1 - p0)))
        return 1.0

    def vel(self, part: str, u: float, base: float, under_words: float = 0.78) -> float:
        """A velocity: base scaled by the energy there and the phrase's breath,
        softer under words (or under an instrument stating the tune), never
        twice the same."""
        v = base * (0.62 + 0.5 * self.energy_at(u)) * self.breath(u)
        if self.sung_at(u):
            v *= under_words
        elif any(what in ("lead", "quote") for what in self.sections[self.section_at(u)].parts.values()):
            v *= 0.7
        return float(np.clip(v * (1.0 + self.rand(part, u).uniform(-0.06, 0.06)), 0.03, 1.0))


def _role(name: str, section) -> str:
    base = re.sub(r"\d+$", "", name)
    if base in ROLES:
        return base
    if section.lyrics == "verse":
        return "verse"
    if section.lyrics == "refrain":
        return "refrain"
    if section.lyrics:
        return "bridge" if section.choir else "refrain"
    return "break"


def nearest(pcs, near: float, lo: int, hi: int) -> int:
    """The pitch with one of these pitch classes closest to `near`, within [lo, hi]."""
    options = [p for p in range(int(lo), int(hi) + 1) if p % 12 in pcs]
    if not options:
        return int(round(near))
    return min(options, key=lambda p: (abs(p - near), p))


# --- who does what where ----------------------------------------------------------


def plan(ctx: Context) -> None:
    """Decide, for every section, what each instrument does there."""
    band = ctx.band
    leads = [x for x in [band.lead] + [x for x in LEADS if x != band.lead] if ctx.on(x)]
    breaks = turns = 0
    pattern = band.pattern
    for i, s in enumerate(ctx.sections):
        e, r = s.energy, s.role
        b = e + 0.3 * (band.density - 0.5)  # how busy the band is here: a dense band comes in earlier and fuller
        prv = ctx.sections[i - 1] if i > 0 else None
        last_refrain = r == "refrain" and s.nth == s.count - 1
        first_refrain = r == "refrain" and s.nth == 0 and s.count > 1
        parts: dict[str, str] = {}
        # who states the tune where nobody sings: the lead opens and closes, others take the breaks and turns
        if leads and r in ("intro", "outro"):
            parts[leads[0]] = "lead"
        elif leads and r == "break":
            parts[leads[(breaks + 1) % len(leads)]] = "lead"
            breaks += 1
        elif leads and r == "turn":
            parts[leads[(turns + 1) % len(leads)]] = "quote"
            turns += 1
        if ctx.on("bass"):
            if r in ("bridge", "tag", "outro") or (r == "intro" and e < 0.45):
                parts["bass"] = "long"
            elif pattern == "air":  # a slow air: the bass holds, and only marks the harmony in the refrains
                parts["bass"] = "roots" if r in ("refrain", "break") else "long"
            elif r == "verse" and s.nth == 0 and b < 0.5:
                parts["bass"] = "roots"
            else:
                parts["bass"] = "walk" if band.density >= 0.3 else "roots"
        if ctx.on("guitar"):
            what = None
            if pattern == "pick":
                what = "ring" if r in ("tag", "outro") else "pick" if r not in ("intro", "bridge") else None
            elif r in ("tag", "outro"):
                what = "ring"
            elif pattern == "air":
                what = "ring" if r in ("refrain", "break", "turn") else None
            elif r in ("refrain", "break"):
                what = "strum"
            elif r == "turn" and prv is not None and prv.role == "refrain":
                what = "strum"
            elif r == "verse" and (b >= 0.42 or pattern == "strum"):
                what = "light"
            if what == "strum" and band.density < 0.3:  # a sparse player: boom-chick, or one strum a chord
                what = "light" if band.density >= 0.12 else "ring"
            if what:
                parts["guitar"] = what
        if ctx.on("harp"):
            if r in ("bridge", "tag") or pattern == "air" or parts.get("guitar") == "pick":
                parts["harp"] = "roll"  # rolled chords where the picking guitar would share its octave
            elif r in ("refrain", "break") and parts.get("guitar") == "strum":
                parts["harp"] = "high"
            else:
                parts["harp"] = "arp"
        if ctx.on("lute") and "lute" not in parts:
            if last_refrain:
                parts["lute"] = "double"
            elif (r == "verse" or (r == "refrain" and not first_refrain)) and band.density > 0.15:
                parts["lute"] = "fills"
        if ctx.on("fiddle") and "fiddle" not in parts:
            if r == "bridge" or (last_refrain and ctx.on("whistle")) or (r == "verse" and s.nth >= 1):
                parts["fiddle"] = "pad"
            elif r == "refrain" and (s.nth >= 1 or b >= 0.6):
                parts["fiddle"] = "counter"
        if ctx.on("whistle") and "whistle" not in parts:  # kept for the tune's statements and the last refrain
            if last_refrain:
                parts["whistle"] = "counter"
            elif r == "tag":
                parts["whistle"] = "double"
        if ctx.on("drum") and pattern != "air":
            if r in ("refrain", "break") and b >= 0.45:
                if band.density < 0.3 or (first_refrain and b < 0.65):
                    parts["drum"] = "light"  # the pulse arrives gently, and the last refrain has somewhere to go
                else:
                    parts["drum"] = "full" if b >= 0.75 else "pulse"
            elif r == "turn" and b >= 0.5:
                parts["drum"] = "pulse"
            elif r == "verse" and b >= 0.42:
                parts["drum"] = "light"
            elif r == "bridge" and e >= 0.45:
                parts["drum"] = "heart"
            elif r == "tag":
                parts["drum"] = "end"
        if ctx.on("drone") and (r in ("intro", "bridge", "tag", "outro") or (pattern == "air" and r != "turn")):
            parts["drone"] = "hold"
        s.parts = parts


# --- the comping parts ------------------------------------------------------------


def bass_part(ctx: Context) -> list[Ev]:
    """An upright bass in its own octave: roots, a root and a fifth, or a
    walking line with approach notes and now and then an anticipation."""
    out: list[Ev] = []
    lo, hi = max(28, ctx.tonic - 34), ctx.tonic - 15
    home = lo + 6  # long notes and roots sit low
    prev = None
    tied = False  # the last chord's root was pushed early into this one
    density = ctx.band.density
    chords = ctx.chords
    for k, c in enumerate(chords):
        what = ctx.sections[c.section].parts.get("bass")
        if not what:
            prev, tied = None, False
            continue
        rng = ctx.rand("bass", c.u0)
        e = ctx.energy_at(c.u0) + 0.3 * (density - 0.5)
        pcs = ctx.pcs(c.symbol)
        walking = what == "walk" and e >= 0.5
        root = nearest({pcs[0]}, prev if walking and prev is not None else home, lo, hi if walking else lo + 12)
        fifth = nearest({pcs[2]}, root - 5 if root - 5 >= lo else root + 7, lo, hi)
        third = nearest({pcs[1]}, root + 4, lo, hi)
        nxt = chords[k + 1] if k + 1 < len(chords) else None
        nxt_root = None
        if nxt is not None and ctx.sections[nxt.section].parts.get("bass"):
            nxt_root = nearest({ctx.root(nxt.symbol)}, root, lo, hi)
        span = c.u1 - c.u0
        beat = ctx.beat
        if what == "long" or span < beat:
            steps = [(0.0, root)]
        elif not walking:
            steps = [(0.0, root)]
            if span >= 2 * beat and (what != "roots" or rng.random() < 0.6):
                steps.append((beat * max(1, int(round(span / beat)) // 2), fifth))
        else:  # walking: a note a beat, root first, chord tones through, an approach last
            n_beats = int(round(span / beat))
            steps = []
            tones = [fifth, root + 12 if root + 12 <= hi else fifth, third]
            for b in range(n_beats):
                if b == 0:
                    p = root
                elif b == n_beats - 1 and nxt_root is not None and nxt_root != root:
                    p = _approach(ctx, rng, nxt_root, lo, hi, c.u0 + b * beat)
                else:
                    p = tones[int(rng.integers(len(tones)))]
                    if rng.random() < 0.35 * (1.0 - density):
                        continue  # a beat left out: a line that breathes
                steps.append((b * beat, p))
        if tied:
            steps = [st for st in steps if st[0] > 1e-9]
            if out:
                out[-1].u1 = c.u0 + (steps[0][0] if steps else span)
        tied = False
        push = None
        if nxt_root is not None and walking and abs(nxt.u0 - c.u1) < 1e-9 and rng.random() < 0.2 * e \
                and ctx.sections[nxt.section].role not in ("bridge", "tag"):
            push = c.u1 - ctx.sub  # an anticipation: the next root an off-beat early, tied over
            steps = [st for st in steps if c.u0 + st[0] < push - 1e-9]
        for j, (off, p) in enumerate(steps):
            u0 = c.u0 + off
            u1 = c.u0 + steps[j + 1][0] if j + 1 < len(steps) else (push if push is not None else c.u1)
            accent = 1.0 if off == 0 else 0.82
            out.append(Ev("bass", u0, u1 - 0.1 * ctx.sub, p, ctx.vel("bass", u0, 0.8 * accent, 0.85), section=c.section))
            prev = p
        if push is not None:
            out.append(Ev("bass", push, nxt.u1, nxt_root, ctx.vel("bass", push, 0.8, 0.85), section=c.section))
            prev, tied = nxt_root, True
    return _monophonic(out)


def _approach(ctx: Context, rng: np.random.Generator, target: int, lo: int, hi: int, at: float) -> int:
    """A note leading into target: a scale step below or above, now and then a
    half step, but never a half step or a tritone from what is being sung."""
    below = [p for p in range(target - 2, target) if p % 12 in ctx.scale and p >= lo]
    above = [p for p in range(target + 1, target + 3) if p % 12 in ctx.scale and p <= hi]
    choices = [below[-1]] * 4 if below else []
    choices += [above[0]] * 3 if above else []
    choices += [target - 1] if target - 1 >= lo else []
    sung = ctx.sung_at(at)
    choices = [p for p in choices if sung is None or (p - sung.pitch) % 12 not in (1, 6, 11)]
    return int(choices[int(rng.integers(len(choices)))]) if choices else target


def _monophonic(events: list[Ev]) -> list[Ev]:
    """One note at a time: each stops where the next begins."""
    events.sort(key=lambda e: (e.u0, e.shift))
    for a, b in zip(events, events[1:]):
        if a.length <= 0 and a.u1 > b.u0:
            a.u1 = b.u0
    return [e for e in events if e.u1 - e.u0 > 1e-6 or e.length > 0 or e.shift > 0]


def harp_voicing(ctx: Context, symbol: str, high: bool) -> list[int]:
    """Five strings for a chord: low, spread root, fifth, octave, tenth,
    twelfth; or, high, the chord's tones climbing from just above the tune's
    usual top, out of the singer's way."""
    root_i, third_i, fifth_i = chord_tones(symbol, ctx.mode)
    if high:
        pcs = ctx.pcs(symbol)
        return [p for p in range(ctx.tonic + 10, ctx.tonic + 25) if p % 12 in pcs][:5]
    low = ctx.tonic - 22
    bass = low + (ctx.tonic + root_i - low) % 12
    return [bass, bass + (fifth_i - root_i), bass + 12, bass + 12 + (third_i - root_i), bass + 12 + (fifth_i - root_i)]


def harp_part(ctx: Context) -> list[Ev]:
    out: list[Ev] = []
    steps = ctx.params.accomp.split() or ["0"]
    density = ctx.band.density
    for c in ctx.chords:
        s = ctx.sections[c.section]
        what = s.parts.get("harp")
        if not what:
            continue
        rng = ctx.rand("harp", c.u0)
        voicing = harp_voicing(ctx, c.symbol, what == "high")
        if what == "roll":  # a chord rolled low to high, left to ring (the bass, if there is one, has the root below)
            low = voicing[0] - 12
            spread = ([low] if low >= ctx.tonic - 34 and not ctx.on("bass") else []) + voicing
            for j, p in enumerate(spread):
                out.append(Ev("harp", c.u0, c.u1, p, ctx.vel("harp", c.u0, 0.62 - 0.03 * j, 0.8), shift=0.035 * j,
                              section=c.section))
            if c.u1 - c.u0 >= ctx.bar and density > 0.4:  # and a few notes higher up, later in the bar
                for j, off in enumerate((ctx.bar / 2, ctx.bar / 2 + ctx.beat)):
                    if c.u0 + off < c.u1 and rng.random() < density:
                        out.append(Ev("harp", c.u0 + off, c.u1, voicing[3 + j % 2] + 12,
                                      ctx.vel("harp", c.u0 + off, 0.4, 0.8), section=c.section))
            continue
        step_u = ctx.bar / len(steps)
        bar_start = c.u0 - ((c.u0 - s.u0) % ctx.bar)
        first = int(round((c.u0 - bar_start) / step_u))
        last = int(round((c.u1 - bar_start) / step_u))
        tokens = list(steps)  # this bar's own version of the pattern
        if what == "high":
            tokens = [t if t in ("2", "3", "4") or rng.random() < 0.3 else "." for t in tokens]
        if ctx.energy_at(c.u0) < 0.4 or density < 0.3:
            tokens = [t if k % 2 == 0 else "." for k, t in enumerate(tokens)]
        if rng.random() < 0.18:  # the second half turned round
            half = len(tokens) // 2
            tail = iter([t for t in tokens[half:] if t != "."][::-1])
            tokens = tokens[:half] + [next(tail) if t != "." else "." for t in tokens[half:]]
        breath = c.last and s.sung and rng.random() < 0.4  # a line's end: one rolled chord, then quiet
        for k in range(first, last):
            token = tokens[k % len(tokens)]
            u0 = bar_start + k * step_u
            if breath:
                if k == first:
                    for j, p in enumerate(voicing[1:]):
                        out.append(Ev("harp", u0, c.u1, p, ctx.vel("harp", u0, 0.5), shift=0.03 * j, section=c.section))
                continue
            if token == ".":
                if density > 0.6 and k > first and rng.random() < 0.25 * density:
                    prev = out[-1].pitch if out else voicing[2]
                    passing = [p for p in range(int(prev) - 2, int(prev) + 3) if p % 12 in ctx.scale and p != prev]
                    if passing:
                        p = passing[int(rng.integers(len(passing)))]
                        out.append(Ev("harp", u0, c.u1, p, ctx.vel("harp", u0, 0.42), section=c.section))
                continue
            p = voicing[int(token) % len(voicing)]
            sung = ctx.sung_at(u0)
            if sung is not None and p == sung.pitch:
                p -= 12  # never on the singer's own note: the harp takes it an octave down
            out.append(Ev("harp", u0, c.u1, p, ctx.vel("harp", u0, 0.75 if k == first else 0.55), section=c.section))
    return out


def let_ring(ctx: Context, events: list[Ev]) -> list[Ev]:
    """A harp's strings ring until they are plucked again or the harmony moves
    away from them: a string that belongs to the next chord rings on into it
    (a bar at most); one that doesn't is damped as the chord changes."""
    for e in events:  # never on a note being sung, the choir's included: an octave down instead
        while int(round(e.pitch)) in ctx.voices_at(e.u0):
            e.pitch -= 12
    events.sort(key=lambda e: (e.u0, e.shift, e.pitch))
    starts: dict[int, list[float]] = {}
    for e in events:
        starts.setdefault(int(round(e.pitch)), []).append(e.u0)
    for e in events:
        c = ctx.chord_at(e.u0)
        nxt = next((x for x in ctx.chords if abs(x.u0 - c.u1) < 1e-9), None)
        end = max(e.u1, c.u1)
        if nxt is not None and int(round(e.pitch)) % 12 in ctx.pcs(nxt.symbol):
            end = max(end, min(nxt.u1, c.u1 + ctx.bar))
        again = [u for u in starts[int(round(e.pitch))] if u > e.u0 + 1e-9]
        if again:
            end = min(end, again[0])
        e.u1 = end
    return events


@lru_cache(maxsize=512)
def guitar_voicing(pcs: tuple[int, ...], capo: int) -> tuple[tuple[tuple[int, int], ...], float]:
    """An open-position guitar chord, capoed: (string, pitch) low to high, and
    how awkward it is to finger. The lowest string sounding carries the root
    (pcs[0]); the third must be there; open strings are welcome; the hand
    spans at most three frets; no muted string inside the chord."""
    options = []
    for open_pitch in GUITAR_TUNING:
        base = open_pitch + capo
        options.append([None] + [base + f for f in range(5) if (base + f) % 12 in pcs])
    best, best_cost = None, 1e9

    def walk(i, chosen):
        nonlocal best, best_cost
        if i == len(options):
            sounding = [(k, p) for k, p in enumerate(chosen) if p is not None]
            if len(sounding) < 4 or sounding[0][1] % 12 != pcs[0]:
                return
            if any(p is None for p in chosen[sounding[0][0]:]):
                return
            frets = [p - GUITAR_TUNING[k] - capo for k, p in sounding]
            fretted = [f for f in frets if f > 0]
            span = (max(fretted) - min(fretted)) if fretted else 0
            if span > 3:
                return
            have = {p % 12 for _, p in sounding}
            cost = 0.35 * span + 0.05 * sum(frets) - 0.25 * frets.count(0) - 0.3 * len(sounding)
            cost += (6.0 if pcs[1] not in have else 0.0) + (0.8 if pcs[2] not in have else 0.0)
            if cost < best_cost:
                best, best_cost = tuple(sounding), cost
            return
        for option in options[i]:
            walk(i + 1, chosen + [option])

    walk(0, [])
    if best is None:  # a plain triad on the middle strings
        root = nearest({pcs[0]}, 48 + capo, 45 + capo, 57 + capo)
        best = ((2, root), (3, root + (pcs[2] - pcs[0]) % 12), (4, root + 12), (5, root + 12 + (pcs[1] - pcs[0]) % 12))
        best_cost = 5.0
    return best, best_cost


def choose_capo(ctx: Context) -> int:
    """The capo that lets every chord of the song fall in open shapes."""
    symbols = sorted({c.symbol for c in ctx.chords})
    costs = [(sum(guitar_voicing(ctx.pcs(sym), capo)[1] for sym in symbols) + 0.4 * capo, capo) for capo in range(7)]
    return min(costs)[1]


def strum_pattern(ctx: Context, family: str, what: str) -> list[tuple[float, str, float]]:
    """(position in beats, stroke, accent) for one bar: D down, U up, B the
    thumb on the bass string, b the thumb on the next string up, C a chop of
    the upper strings (boom-chick)."""
    beats = ctx.beats
    if what == "ring" or family == "air":
        return [(0.0, "D", 0.9)]
    if what == "light":  # boom-chick: the thumb's bass note where a foot starts, the upper strings between
        if ctx.compound:
            return [(float(b), "B" if b == 0 else "C", 0.8 if b == 0 else 0.6) for b in range(beats)]
        out = []
        for b in range(beats):
            start = b % ctx.foot == 0 or b == beats // 2 and beats % 2 == 0
            thumb = "B" if b == 0 else "b"
            out.append((float(b), thumb if start else "C", 0.8 if b == 0 else 0.65 if start else 0.55))
        return out
    if ctx.compound:  # a jig's strum: down on the beat, up on its last third
        pattern = []
        for b in range(beats):
            pattern.append((float(b), "D", 1.0 if b == 0 else 0.8))
            if family == "strum":
                pattern.append((b + 1 / 3, "U", 0.4))
            pattern.append((b + 2 / 3, "U", 0.5))
        return pattern
    if family == "strum":  # the old faithful: down, down-up, up-down-up
        base = {4: [(0, "D", 1.0), (1, "D", 0.7), (1.5, "U", 0.5), (2.5, "U", 0.5), (3, "D", 0.7), (3.5, "U", 0.5)],
                3: [(0, "D", 1.0), (1, "D", 0.7), (1.5, "U", 0.5), (2, "D", 0.7), (2.5, "U", 0.5)],
                2: [(0, "D", 1.0), (0.5, "U", 0.5), (1, "D", 0.75), (1.5, "U", 0.5)]}
        return [(float(p), s, a) for p, s, a in base.get(beats, base[4] if beats > 3 else base[2])]
    # the lilt: down on every beat, strongest where a foot starts; up on the off-beats within a foot
    pattern = []
    for b in range(beats):
        start = b % ctx.foot == 0
        pattern.append((float(b), "D", 1.0 if b == 0 else (0.85 if start else 0.65)))
        if not start:
            pattern.append((b + 0.5, "U", 0.5))
    return pattern


def guitar_part(ctx: Context, capo: int) -> list[Ev]:
    out: list[Ev] = []
    density = ctx.band.density
    family = ctx.band.pattern
    strokes: list[tuple[float, str, float, Chord]] = []
    for c in ctx.chords:
        s = ctx.sections[c.section]
        what = s.parts.get("guitar")
        if not what:
            continue
        rng = ctx.rand("guitar", c.u0)
        if what == "pick":
            out += _fingerpick(ctx, rng, c, capo)
            continue
        bar_start = c.u0 - ((c.u0 - s.u0) % ctx.bar)
        chopped = False
        rebound = False  # after a chop the hand comes straight back up
        for pos, stroke, accent in strum_pattern(ctx, family, what):
            u = bar_start + pos * ctx.beat
            if not (c.u0 - 1e-9 <= u < c.u1 - 1e-9) or (what == "ring" and u > c.u0 + 1e-9):
                continue
            if stroke == "U" and not rebound and (density < 0.3 or rng.random() < 0.15 + 0.3 * max(0.0, 0.5 - density)):
                continue
            rebound = False
            backbeat = pos % 2 == 1 and not ctx.compound
            if stroke == "D" and backbeat and not chopped and what == "strum" and s.role == "refrain" \
                    and rng.random() < 0.2 * density:
                stroke, chopped, rebound = "X", True, True  # a muted chop on a backbeat, once a bar at most
            if stroke in ("B", "b"):  # the thumb takes the root where a chord starts, the next string after
                stroke = "B" if abs(u - c.u0) < 1e-9 else "b"
            strokes.append((u, stroke, accent, c))
        if what == "strum" and density > 0.65:  # a busy player fills the gaps with light ups
            for b in range(ctx.beats):
                u = bar_start + (b + 0.5) * ctx.beat
                if c.u0 <= u < c.u1 and not any(abs(st[0] - u) < 1e-6 for st in strokes) and rng.random() < density - 0.5:
                    strokes.append((u, "U", 0.35, c))
    strokes.sort(key=lambda st: st[0])
    ringing: dict[int, tuple[Ev, str]] = {}  # string -> (its sounding note, the chord it was fingered for)
    for u, stroke, accent, c in strokes:
        s = ctx.sections[c.section]
        rng = ctx.rand("guitar", u)
        voicing, _ = guitar_voicing(ctx.pcs(c.symbol), capo)
        if stroke == "U":
            order = list(voicing)[::-1][: max(3, len(voicing) - 2)]  # an upstroke catches the top strings
        elif stroke == "B":
            order = [voicing[0]]
        elif stroke == "b":
            order = [voicing[min(1, len(voicing) - 1)]]
        elif stroke == "C":
            order = list(voicing)[-4:] if len(voicing) > 4 else list(voicing)[1:]
        else:
            order = list(voicing)
        for string, (ev, symbol) in list(ringing.items()):
            if symbol != c.symbol and ev.u1 > u:  # the fretting hand has moved on: that string stops
                ev.u1 = u
        vel = ctx.vel("guitar", u, 0.85 * accent)
        ring = s.parts.get("guitar") == "ring"
        spread = (0.05 + 0.04 * rng.random()) if ring else (0.018 + 0.02 * (1.0 - vel)) * (0.8 if stroke == "U" else 1.0)
        if stroke in ("B", "b"):
            spread = 0.0
        end = c.u1 if not ring else max(c.u1, s.u1 if c.last else c.u1)
        for j, (string, pitch) in enumerate(order):
            v = vel * (1.0 - 0.05 * j) * (0.75 if stroke == "U" else 1.0) * rng.uniform(0.85, 1.05)
            ev = Ev("guitar", u, end, pitch, float(np.clip(v, 0.03, 1.0)),
                    art="up" if stroke == "U" else "mute" if stroke == "X" else "down",
                    shift=spread * j / max(len(order) - 1, 1) * rng.uniform(0.8, 1.2), section=c.section)
            held = ringing.get(string)
            if held is not None and held[0].u1 > u:
                held[0].u1 = u  # the pick meets the string again
            out.append(ev)
            ringing[string] = (ev, c.symbol)
    return out


def _fingerpick(ctx: Context, rng: np.random.Generator, c: Chord, capo: int) -> list[Ev]:
    """Thumb on the beats (the root string, then the next), fingers on the off-beats."""
    voicing, _ = guitar_voicing(ctx.pcs(c.symbol), capo)
    pitches = [p for _, p in voicing]
    out = []
    for b in range(int(round((c.u1 - c.u0) / ctx.beat))):
        u = c.u0 + b * ctx.beat
        thumb = pitches[0] if b % 2 == 0 else pitches[min(1, len(pitches) - 1)]
        out.append(Ev("guitar", u, c.u1, thumb, ctx.vel("guitar", u, 0.7 if b == 0 else 0.55), art="down",
                      section=c.section))
        off = u + (ctx.sub if not ctx.compound else 2 * ctx.sub)
        if off < c.u1 and rng.random() < 0.5 + 0.5 * ctx.band.density:
            top = pitches[-1 - int(rng.integers(0, min(3, len(pitches) - 1)))]
            out.append(Ev("guitar", off, c.u1, top, ctx.vel("guitar", off, 0.45), art="up", section=c.section))
    return out


# --- the melodic parts: statements, quotes, doubling, counter-melodies, pads, fills ---


def octave_for(part: str, pitches: list[int]) -> int:
    """The octave a part plays the tune in: up one if it fits the instrument."""
    lo, hi = REGISTER[part]
    for shift in (12, 0, 24, -12):
        if min(pitches) + shift >= lo and max(pitches) + shift <= hi:
            return shift
    return 12


def statement(ctx: Context, part: str, notes: list[Tune], vel_scale: float, section: int,
              ornament: bool = True, shift: int | None = None) -> list[Ev]:
    """An instrument playing a line of the tune in its own register (or `shift`
    semitones from the tune) and its own way: a whistle cuts and rolls, a
    fiddle slides and slurs; how often, the band's ornament setting says."""
    if not notes:
        return []
    if shift is None:
        shift = octave_for(part, [t.pitch for t in notes])
    often = 2.0 * ctx.band.ornament if ornament else 0.0
    out: list[Ev] = []
    prev = None
    for t in notes:
        rng = ctx.rand(part, t.u0)
        pitch = t.pitch + shift
        length_u = t.u1 - t.u0
        strong = (t.u0 - ctx.sections[t.section].u0) % ctx.beat == 0
        vel = float(np.clip(t.vel * vel_scale * (0.62 + 0.5 * ctx.energy_at(t.u0)) *
                            (0.8 if t.sung else 1.0), 0.05, 1.0))
        joined = prev is not None and abs(prev[1] - t.u0) < 1e-6
        step = joined and abs(pitch - prev[0]) <= 2
        art = ""
        if part == "fiddle":
            art = "slur" if step and not strong else ""
            if length_u >= 3 * ctx.sub and not step and rng.random() < 0.3 * often:
                art = "slide"
        elif part == "whistle":
            art = "slur" if step and not t.first else ""
        grace = None
        if often and part in ("whistle", "fiddle"):
            repeated = joined and prev[0] == pitch
            chance = (0.3 if part == "whistle" else 0.15) * often
            if repeated or (strong and length_u >= 2 * ctx.sub and rng.random() < chance):
                above = [p for p in range(pitch + 1, pitch + 6) if p % 12 in ctx.scale]
                if above:
                    grace = above[min(1, len(above) - 1)] if part == "whistle" else above[0]
        if grace is not None:  # a cut: a flick of a higher note on the beat
            cut = float(rng.uniform(0.022, 0.034))
            out.append(Ev(part, t.u0, t.u0, grace, vel * 0.8, art="cut" if prev is not None else "", length=cut,
                          section=section))
            out.append(Ev(part, t.u0, t.u1, pitch, vel, art="slur", shift=cut, section=section))
        elif part == "whistle" and length_u >= 4 * ctx.sub and rng.random() < 0.3 * often:
            # a roll: the note, cut, the note, tapped, the note
            third = length_u / 3
            above = [p for p in range(pitch + 1, pitch + 6) if p % 12 in ctx.scale]
            below = [p for p in range(pitch - 5, pitch) if p % 12 in ctx.scale]
            out.append(Ev(part, t.u0, t.u0 + third, pitch, vel, art=art, section=section))
            if above:
                out.append(Ev(part, t.u0 + third, t.u0 + third, above[0], vel * 0.7, art="cut", length=0.024,
                              section=section))
            out.append(Ev(part, t.u0 + third, t.u0 + 2 * third, pitch, vel, art="slur", shift=0.024, section=section))
            if below:
                out.append(Ev(part, t.u0 + 2 * third, t.u0 + 2 * third, below[-1], vel * 0.7, art="tap",
                              length=0.024, section=section))
            out.append(Ev(part, t.u0 + 2 * third, t.u1, pitch, vel, art="slur", shift=0.024, section=section))
        else:
            out.append(Ev(part, t.u0, t.u1, pitch, vel, art=art, section=section))
        prev = (pitch, t.u1)
    return out


def quote(ctx: Context, section: int, part: str) -> list[Ev]:
    """A turn: the instrument quotes the sung phrase whose tune best fits the
    turn's chords, a refrain's by preference."""
    s = ctx.sections[section]
    rng = ctx.rand("quote", s.u0)
    bars = int(round((s.u1 - s.u0) / ctx.bar))
    under = [(c.u0 - s.u0, c.u1 - s.u0, c.symbol) for c in ctx.chords_in(section)]
    refrain_phrases = {pid for sec in ctx.genome.sections.values() if sec.lyrics == "refrain" for pid in sec.phrases}
    best, best_score = None, -1e9
    for pid, phrase in sorted(ctx.genome.phrases.items()):
        sung = [n for n in phrase.sung if 0 <= n.onset < bars * ctx.bar]
        if phrase.bars < bars or len(sung) < 3:
            continue
        score = 1.5 if pid in refrain_phrases else 0.0
        for n in sung:
            symbol = next((sym for a, z, sym in under if a <= n.onset < z), under[-1][2])
            pc = (ctx.tonic + degree_semitones(n.degree, ctx.mode, n.alter)) % 12
            pcs = ctx.pcs(symbol)
            weight = n.dur * (1.5 if n.onset % ctx.beat == 0 else 1.0)
            if pc in pcs:
                score += weight
            elif (pc - pcs[0]) % 12 in (2, 9):
                score += 0.3 * weight
            else:
                score -= weight
        score += rng.uniform(0.0, 0.5)
        if score > best_score:
            best, best_score = sung, score
    if best is None:
        return []
    notes = []
    for k, n in enumerate(best):
        u0 = s.u0 + n.onset
        u1 = min(u0 + n.dur, s.u0 + best[k + 1].onset if k + 1 < len(best) else s.u1 - ctx.sub)
        notes.append(Tune(u0, u1, ctx.tonic + degree_semitones(n.degree, ctx.mode, n.alter),
                          0.8 if n.onset % ctx.meter.foot == 0 else 0.68, False, section, k == 0, k == len(best) - 1))
    return statement(ctx, part, notes, 0.88, section)


def window(part: str, lo: int, hi: int) -> tuple[int, int]:
    """A register for a part within what the instrument can play: trimmed if
    most of it is playable, otherwise moved by octaves until it is."""
    bottom, top = REGISTER.get(part, (0, 127))
    while min(hi, top) - max(lo, bottom) < 7 and lo < bottom and hi + 12 <= top + 12:
        lo, hi = lo + 12, hi + 12
    while min(hi, top) - max(lo, bottom) < 7 and hi > top and lo - 12 >= bottom - 12:
        lo, hi = lo - 12, hi - 12
    return max(lo, bottom), min(hi, top)


def counter(ctx: Context, section: int, part: str, lo: int, hi: int, vel_scale: float, bow: bool = False,
            others: list[Ev] | None = None) -> list[Ev]:
    """A counter-melody drawn from the harmony: a chord tone a chord, moving as
    little as it can and clear of the tune and of any other line already
    written (no seconds or doublings against them, not crowding them); it
    moves where the singer holds a line's last note, and passes through the
    step between where it leaps a third. A bowed line changes bow every two
    bars."""
    lo, hi = window(part, lo, hi)
    out: list[Ev] = []
    prev = None
    repeats = 0
    s = ctx.sections[section]
    lines = [(t.u0, t.u1, t.pitch, (t.u0 - s.u0) % ctx.beat == 0) for t in ctx.tune_in(section)]
    lines += [(u0, u1, p, True) for u0, u1, p in ctx.choir if s.u0 <= u0 < s.u1]
    lines += [(e.u0, e.u1, e.pitch, True) for e in others or []]
    for c in ctx.chords_in(section):
        rng = ctx.rand(part, c.u0)
        pcs = ctx.pcs(c.symbol)
        against = [x for x in lines if x[0] < c.u1 and x[1] > c.u0]

        def cost(p):
            x = 0.0
            if prev is not None:
                x += 0.35 * abs(p - prev) + (2.0 if abs(p - prev) > 7 else 0.0) + (0.8 if p == prev and repeats >= 2 else 0.0)
            else:
                x += 0.12 * abs(p - (lo + hi) / 2)
            for u0, u1, q, strong in against:
                w = (min(u1, c.u1) - max(u0, c.u0)) / max(c.u1 - c.u0, 1e-9) * (1.5 if strong else 1.0)
                iv = (p - q) % 12
                x += w * (1.6 if iv in (1, 2, 6, 10, 11) else 0.9 if iv == 0 else 0.0)
                x += w * (1.2 if abs(p - q) < 3 else 0.0)
            return x + rng.uniform(0.0, 0.35)

        cands = [p for p in range(lo, hi + 1) if p % 12 in pcs]
        p = min(cands, key=cost) if cands else (prev or lo)
        repeats = repeats + 1 if p == prev else 0
        offset = c.u0 - ctx.sections[section].u0
        bar = int(np.floor(offset / ctx.bar + 1e-9))
        fresh = bar % 2 == 0 and abs(offset - bar * ctx.bar) < 1e-9  # a new bow every other bar line
        art = "" if prev is None or (bow and fresh) or not bow else "slur"
        out.append(Ev(part, c.u0, c.u1, p, ctx.vel(part, c.u0, 0.75 * vel_scale, 0.85), art=art, section=section))
        prev = p
    moving: list[Ev] = []
    ends = [t for t in ctx.tune_in(section) if t.last and t.u1 - t.u0 >= 2 * ctx.sub]
    for a, b in zip(out, out[1:] + [None]):
        rng = ctx.rand(part, a.u0)
        moving.append(a)
        held = next((t for t in ends if a.u0 < t.u0 + ctx.sub < a.u1 - ctx.sub), None)
        if held is not None and rng.random() < 0.5 + 0.4 * ctx.band.density:
            # the singer holds: the line moves, a step toward where it goes next, or a neighbour and back
            goal = b.pitch if b is not None else a.pitch
            at = held.u0 + ctx.sub
            sung = ctx.voices_at(at)
            steps = [q for q in range(max(lo, int(a.pitch) - 3), min(hi, int(a.pitch) + 3) + 1)
                     if q % 12 in ctx.scale and q != a.pitch and all((q - v) % 12 not in (1, 2, 6, 10, 11) for v in sung)]
            toward = [q for q in steps if (q - a.pitch) * (goal - a.pitch) > 0] or steps
            if toward:
                q = min(toward, key=lambda x: abs(x - a.pitch))
                moving.append(Ev(part, at, a.u1, q, a.vel * 0.95, art="slur" if bow else "", section=section))
                a.u1 = at
                continue
        if b is None or a.u1 - a.u0 < 2 * ctx.beat or rng.random() > 0.3 + 0.5 * ctx.band.density:
            continue
        if 3 <= abs(b.pitch - a.pitch) <= 4 and abs(a.u1 - b.u0) < 1e-9:
            mid = [q for q in range(int(min(a.pitch, b.pitch)) + 1, int(max(a.pitch, b.pitch))) if q % 12 in ctx.scale]
            if mid:
                at = a.u1 - ctx.beat
                moving.append(Ev(part, at, a.u1, mid[len(mid) // 2], a.vel * 0.9, art="slur" if bow else "",
                                 section=section))
                a.u1 = at
    return moving


def fills(ctx: Context) -> list[Ev]:
    """Answers between the singer's lines: a short run while a line's last
    note is held, leading into the next line."""
    out: list[Ev] = []
    last_player = None
    for i, s in enumerate(ctx.sections):
        if not s.sung:
            continue
        players = [p for p, what in s.parts.items() if what == "fills"]
        if s.parts.get("harp") == "arp" and s.role == "verse":
            players.append("harp")
        if not players:
            continue
        tune = ctx.tune_in(i)
        for k, t in enumerate(tune):
            if not t.last:
                continue
            rng = ctx.rand("fills", t.u0)
            nxt = tune[k + 1] if k + 1 < len(tune) else None
            start = t.u0 + ctx.sub
            stop = min(nxt.u0 if nxt is not None else s.u1, s.u1)
            if stop - start < 2 * ctx.sub - 1e-9 or rng.random() > 0.25 + 0.55 * ctx.band.density:
                continue
            who = [p for p in players if p != last_player] or players
            player = who[int(rng.integers(len(who)))]
            last_player = player
            out += _run(ctx, rng, player, start, stop, t, nxt.pitch if nxt is not None else t.pitch, i)
    return out


def _run(ctx: Context, rng: np.random.Generator, part: str, start: float, stop: float, held: Tune, target: int,
         section: int) -> list[Ev]:
    """A fill: a flourish up the chord (harp), or a scale run into the next
    sung note, an octave up, stopping a step short of it so the singer
    completes it, coming from the side the tune is moving from."""
    n = max(2, min(int(np.floor((stop - start) / ctx.sub + 1e-6)), 4))
    chord = ctx.chord_at(start)
    pcs = ctx.pcs(chord.symbol)
    if part == "harp":
        p = nearest(pcs, held.pitch + 5, held.pitch + 1, held.pitch + 12)
        pitches = []
        for _ in range(n):
            pitches.append(p)
            p = nearest(pcs, p + 4, p + 1, p + 9)
    else:
        goal = target + 12
        floor = max(t.pitch for t in ctx.tune_in(section)) + 1  # an answer sits above the tune, as the counter-lines do
        while goal - 2 < floor:
            goal += 12
        rising = target > held.pitch if target != held.pitch else rng.random() < 0.5
        climb = rising if rng.random() < 0.75 else not rising  # a run climbing into the goal, or falling onto it
        d = 1 if climb else -1
        scale = [q for q in range(goal - 16, goal + 17) if q % 12 in ctx.scale]
        ig = min(range(len(scale)), key=lambda k: abs(scale[k] - goal))
        pitches = [scale[min(max(ig - d * (n - j), 0), len(scale) - 1)] for j in range(n)]
    bottom, top = REGISTER.get(part, (0, 127))
    while max(pitches) > top and min(pitches) - 12 >= bottom:
        pitches = [p - 12 for p in pitches]
    while min(pitches) < bottom and max(pitches) + 12 <= top:
        pitches = [p + 12 for p in pitches]
    out = []
    for j, p in enumerate(pitches):
        u0 = start + j * ctx.sub
        u1 = stop if part == "harp" else min(stop, u0 + ctx.sub * (1.0 if j + 1 < n else 1.5))
        loud = {"lute": 0.75, "harp": 0.5}.get(part, 0.55)  # a plucked answer needs a firmer touch to carry
        vel = float(np.clip((loud + 0.1 * j / n) * (0.62 + 0.5 * ctx.energy_at(u0)), 0.05, 1.0))
        art = "slur" if part in ("fiddle", "whistle") and j > 0 else ""
        out.append(Ev(part, u0, u1, p, vel, art=art, section=section))
    return out


def held_through(ctx: Context, tune: list[Tune]) -> list[Tune]:
    """The tune with each note that isn't a tone of its chord held over from the note before."""
    out: list[Tune] = []
    for t in tune:
        chord = ctx.pcs(ctx.chord_at(t.u0).symbol)
        if out and t.pitch % 12 not in chord and out[-1].pitch % 12 in chord and abs(out[-1].u1 - t.u0) < 1e-9:
            out[-1] = Tune(out[-1].u0, t.u1, out[-1].pitch, out[-1].vel, out[-1].sung, out[-1].section, out[-1].first,
                           t.last)
        else:
            out.append(t)
    return out


def held_tone(ctx: Context, section: int, part: str, top: int) -> list[Ev]:
    """One long bowed tone a line, just above the tune: the tonic or its fifth,
    whichever sits best with that line's chords, swelling and fading."""
    s = ctx.sections[section]
    lo, hi = window(part, top + 1, top + 13)
    out = []
    for p0, p1 in ctx.phrases:
        if not (s.u0 - 1e-9 <= p0 < s.u1 - 1e-9):
            continue
        chords = [c for c in ctx.chords if p0 - 1e-9 <= c.u0 < p1 - 1e-9]
        options = [q for q in range(lo, hi + 1) if q % 12 in ((ctx.tonic % 12), (ctx.tonic + 7) % 12)]
        if not options or not chords:
            continue

        def fit(q):
            return sum((c.u1 - c.u0) * (1.0 if q % 12 in ctx.pcs(c.symbol) else
                                        0.3 if (q - ctx.root(c.symbol)) % 12 in (2, 9) else -1.0) for c in chords)

        q = max(options, key=lambda q: (fit(q), -q))
        out.append(Ev(part, p0, p1 - ctx.sub, q, ctx.vel(part, p0, 0.75 * 0.4, 0.85), art="swell", section=section))
    return out


def melodic_parts(ctx: Context) -> list[Ev]:
    out: list[Ev] = []
    whole = [t.pitch for t in ctx.tune]
    for i, s in enumerate(ctx.sections):
        tune = ctx.tune_in(i)
        top = max([t.pitch for t in tune] or whole)  # counter-lines and pads go above where the tune lies here
        written: list[Ev] = []
        for part in ("whistle", "fiddle", "lute"):
            what = s.parts.get(part)
            if what == "lead":  # the tune where nobody sings (not the singer's pickup into the next line)
                mine = statement(ctx, part, [t for t in tune if not t.sung], 0.85, i)
            elif what == "quote":
                mine = quote(ctx, i, part)
            elif what == "double" and tune:
                if part == "lute":  # the cittern doubles the singer at pitch, under the words
                    mine = statement(ctx, part, tune, 0.55, i, ornament=False, shift=0)
                else:  # with the lineage singing harmony, the tune's passing notes are held over, not played
                    mine = statement(ctx, part, held_through(ctx, tune) if ctx.choir else tune, 0.5, i)
            elif what == "counter":
                if part == "whistle":  # a descant, high above the singer
                    mine = counter(ctx, i, part, top + 5, top + 17, 0.48)
                else:
                    mine = counter(ctx, i, part, top + 1, top + 13, 0.55, bow=True)
            elif what == "pad" and s.role == "verse":  # under a verse, just one held tone a line
                mine = held_tone(ctx, i, part, top)
            elif what == "pad":  # long bowed notes, a new bow a bar, swelling: above the singer, clear of a descant
                mine = counter(ctx, i, part, top + 1, top + 12, 0.45, bow=True, others=written)
                for e in mine:
                    if e.u1 - e.u0 >= ctx.bar - 1e-9:
                        e.art = "swell"
            else:
                mine = []
            written += mine
            out += mine
    out += fills(ctx)
    by_part: dict[str, list[Ev]] = {}
    for e in out:
        by_part.setdefault(e.part, []).append(e)
    # each melodic instrument plays one note at a time; the harp's answers ring
    return [e for part in sorted(by_part) for e in (by_part[part] if part == "harp" else _monophonic(by_part[part]))]


# --- the drum and the drone ----------------------------------------------------------


def drum_part(ctx: Context) -> list[Ev]:
    out: list[Ev] = []
    density = ctx.band.density
    for i, s in enumerate(ctx.sections):
        what = s.parts.get("drum")
        if not what:
            continue
        bars = int(round((s.u1 - s.u0) / ctx.bar))
        nxt = ctx.sections[i + 1] if i + 1 < len(ctx.sections) else None
        for b in range(bars):
            bar_u = s.u0 + b * ctx.bar
            rng = ctx.rand("drum", bar_u)
            hits = _drum_bar(ctx, what)
            last_bar = b == bars - 1
            if last_bar and nxt is not None and what in ("pulse", "full", "light") and \
                    (nxt.energy >= s.energy or nxt.role == "refrain"):  # a triplet into what comes next
                hits = [h for h in hits if h[0] < ctx.beats - 1]
                hits += [(ctx.beats - 1 + k / 3.0, "tip", 0.4 + 0.15 * k) for k in range(3)]
            elif last_bar and nxt is not None and nxt.energy - s.energy >= 0.2:  # a build into a much bigger section
                start = max(0, ctx.beats - 2)
                steps = int(round((ctx.beats - start) * ctx.beat / ctx.sub))
                hits = [h for h in hits if h[0] < start] + [
                    (start + k * ctx.sub / ctx.beat, "tip", 0.3 + 0.45 * k / max(steps - 1, 1)) for k in range(steps)]
            if what == "end":
                hits = [(0.0, "bass", 0.35)] if not last_bar else []
            for pos, stroke, v in hits:
                if stroke == "tip" and v < 0.4 and rng.random() > 0.35 + 0.65 * density:
                    continue  # a ghost stroke left out
                u = bar_u + pos * ctx.beat
                out.append(Ev("drum", u, u + ctx.sub, ctx.tonic - 24, ctx.vel("drum", u, v, 0.85), art=stroke, section=i))
    if out and ctx.sections[-1].parts.get("drum"):  # the last chord gets one open stroke
        final = ctx.chords[-1].u0
        out.append(Ev("drum", final, final + ctx.beat, ctx.tonic - 24, 0.6, art="bass", section=len(ctx.sections) - 1))
    return out


def _drum_bar(ctx: Context, what: str) -> list[tuple[float, str, float]]:
    beats = ctx.beats
    if what == "heart":  # under the bridge: a heartbeat, lub-dub, once a bar
        return [(0.0, "bass", 0.5), (0.5, "bass", 0.32)]
    if ctx.compound:
        if what == "light":
            return [(0.0, "bass", 0.75), (1.0, "tip", 0.4)]
        hits = []
        for b in range(beats):  # the middle tip of each beat is the one a slow jig leaves out
            hits += [(float(b), "bass" if b == 0 else "tip", 0.85 if b == 0 else 0.6), (b + 1 / 3, "tip", 0.3),
                     (b + 2 / 3, "tip", 0.45)]
        return hits
    if what == "light":
        return [(float(b), "bass" if b % ctx.foot == 0 else "tip", 0.7 if b % ctx.foot == 0 else 0.35)
                for b in range(beats)]
    hits = []
    for b in range(beats):  # the foot: a low stroke, then the tipper's short-short
        start = b % ctx.foot == 0
        hits.append((float(b), "bass" if start else "tip", 0.85 if start else 0.5))
        if what == "full" or not start:
            hits.append((b + 0.5, "tip" if not start else "mute", 0.42 if not start else 0.38))
    return hits


def drone_part(ctx: Context) -> list[Ev]:
    """The tonic and a softer fifth, below the singer, held through the drone's sections."""
    out: list[Ev] = []
    root = ctx.tonic - 12
    fifth = root + MODES[ctx.mode][4]
    spans: list[list[float]] = []
    for s in ctx.sections:
        if s.parts.get("drone"):
            if spans and abs(spans[-1][1] - s.u0) < 1e-9:
                spans[-1][1] = s.u1
            else:
                spans.append([s.u0, s.u1])
    for u0, u1 in spans:
        tail = ctx.bar if u1 < ctx.end - 1e-9 else 0.0  # held a bar into the next section, fading
        for p, v in ((root, 0.7), (fifth, 0.4)):
            out.append(Ev("drone", u0, min(u1 + tail, ctx.end), p, v * (0.7 + 0.4 * ctx.energy_at(u0)),
                          section=ctx.section_at(u0)))
    return out


# --- putting it together -----------------------------------------------------------


def arrange(genome, params, placed, lead, end, melody, seconds) -> tuple[list[Note], dict]:
    """The band's notes for a realized song, and the settings its instruments are built with.

    placed: (section name, phrase, start unit, lyric line) as realize() lays
    out the form; lead: the pickup offset; end: the last grid unit; melody:
    realize()'s melody entries; seconds: grid units to seconds.
    """
    ctx = Context(genome, params, placed, lead, end, melody)
    plan(ctx)
    capo = choose_capo(ctx)
    events: list[Ev] = []
    if ctx.on("bass"):
        events += bass_part(ctx)
    if ctx.on("harp"):
        events += harp_part(ctx)
    if ctx.on("guitar"):
        events += guitar_part(ctx, capo)
    events += melodic_parts(ctx)
    if ctx.on("drum"):
        events += drum_part(ctx)
    if ctx.on("drone"):
        events += drone_part(ctx)
    events = [e for e in events if ctx.band.plays(e.part)]
    harp = let_ring(ctx, [e for e in events if e.part == "harp"])
    events = [e for e in events if e.part != "harp"] + harp
    for e in events:  # whatever sounds through the last chord holds to the end, and rings on from there
        if e.part != "drum" and e.length <= 0 and e.u1 >= ctx.end - ctx.sub - 1e-9:
            e.u1 = ctx.end

    # Each part's timing wobbles around the grid, the same for everything it plays at one moment
    # (a strum, a rolled chord, a note and its grace), and drawn from where it is, not from how
    # many notes came before: a note that stays put keeps its timing when others change.
    wobble = params.humanize * (1.0 + 1.5 * ctx.band.wear)
    jitters: dict[tuple[str, int], float] = {}
    notes = []
    for e in sorted(events, key=lambda e: (e.u0, e.shift, e.part, e.pitch)):
        key = (e.part, int(round(e.u0 * 1000)))
        if key not in jitters:
            rng = np.random.default_rng([ctx.seed & 0xFFFFFFFF, 0x71, STREAM[e.part], key[1] + (1 << 20)])
            jitters[key] = float(rng.normal(0.0, wobble))
        start = max(0.0, seconds(e.u0) + e.shift + LAG.get(e.part, 0.0) + jitters[key])
        dur = e.length if e.length > 0 else seconds(e.u1) - start
        s = ctx.sections[min(max(e.section, 0), len(ctx.sections) - 1)]
        notes.append(Note(part=e.part, start=start, dur=max(dur, 0.03), pitch=float(e.pitch),
                          vel=float(np.clip(e.vel, 0.02, 1.0)), section=s.name, art=e.art))
    settings = {
        **{name: getattr(ctx.band, name) for name in INSTRUMENTS},
        "brightness": ctx.band.brightness,
        "wear": ctx.band.wear,
        "ornament": ctx.band.ornament,
        "body": ctx.band.body,
        "maker": ctx.band.maker,
        "tonic": ctx.tonic,
        "capo": capo,
        "sections": [{"name": s.name, "role": s.role, "energy": round(s.energy, 3), "parts": dict(sorted(s.parts.items()))}
                     for s in ctx.sections],
    }
    return notes, settings
