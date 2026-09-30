"""Idioms: the band a style calls for, each player playing the way its tradition plays.

songbird/band.py arranges the seed's ballad band; this arranges every other
style (songbird/style.py's palette) with the same care and the same rules,
reusing its facts about the song (sections and their energies, the chords, the
tune and the lineage choir, a random stream per part and bar):

- Each player has a role (bass, chords, lead, pad, percussion) and, section
  by section, an idiom: a banjo's forward roll, a mandolin's chop on the
  backbeat, a Travis-picked guitar, gospel piano in 12/8, an organ's swell, a
  kit's shuffle, a drum machine's boom-bap, an arpeggiator, a music box.
- The grid a style plays on (Grid) follows its feel: straight or swung eighths,
  a shuffle's or 12/8's triplets, half-time or double-time drums, or the song
  re-barred in three (a waltz, or a slow six-eight) where every stressed
  syllable can stay on a downbeat.
- The harmony keeps the genome's functions and adds the style's colour (a
  sixth, a seventh, an added ninth, a suspension, a minor iv, an open fifth),
  only where the sung tune allows it at that moment (tones()).
- The singer stays the point: comping sits under the tune and never on a sung
  pitch, leads and counter-lines keep above it, everything plays softer under
  words, and the arrangement's options (an a cappella verse, a breakdown, a
  count-in, a key lift, a cold ending, backing voices) come from Params.style.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import band as B
from .band import Chord, Context, Ev, Tune, nearest
from .score import Note
from .theory import harmony as choir_harmony

# --- the grid ---------------------------------------------------------------------------------------


def triple_ok(genome) -> bool:
    """Whether the song can be re-barred in three (a waltz, or a slow six-eight): two feet of four
    units to a bar, two units a beat, and every sung note starting on a foot's strong-weak-weak
    positions (0, 2, 3), so each stressed syllable lands on a downbeat and nothing between beats."""
    m = genome.meter
    if not (m.bar == 2 * m.foot and m.foot == 4 and m.beat == 2):
        return False
    return all(n.onset % m.foot in (0, 2, 3) for p in genome.phrases.values() for n in p.sung)


def chord_times(genome, params) -> list[tuple[float, float, str]]:
    """Every chord of a rendition as (start, end, function) in seconds, laid out as realize() lays out the
    form (a style's repeated last line and amen included), for checking what the band plays against them."""
    from .composition import form_phrases
    from .realize import timeline
    from .style import coda, repeated_phrases

    clock = timeline(genome, params)
    m = genome.meter
    phrases = form_phrases(genome, params)  # each line as its place sings it (a person's chords for one place)
    phrases += phrases[-1:] if repeated_phrases(genome, params) else []  # a style's last line again, as sung
    out, u = [], clock.lead
    for phrase in phrases:
        for b, chords in enumerate(phrase.chords):
            for k, symbol in enumerate(chords):
                a = u + b * m.bar + round(k * (m.bar / m.beat) / len(chords)) * m.beat
                z = u + b * m.bar + (round((k + 1) * (m.bar / m.beat) / len(chords)) * m.beat if k + 1 < len(chords) else m.bar)
                out.append((clock.seconds(a), clock.seconds(z), symbol))
        u += phrase.bars * m.bar
    if coda(genome, params):
        out += [(clock.seconds(u), clock.seconds(u + m.bar), "IV"), (clock.seconds(u + m.bar), clock.seconds(u + 2 * m.bar), "I")]
    return out


def warp(u: float, origin: float) -> float:
    """Grid units re-barred in three: within each foot of four units (bar lines at `origin`), the
    strong-weak-weak positions 0, 2, 3 move to 0, 4/3, 8/3, three even pulses; bar lines stay put."""
    k, x = divmod(u - origin, 4.0)
    y = x * 2.0 / 3.0 if x <= 2.0 else 4.0 / 3.0 + (x - 2.0) * 4.0 / 3.0
    return origin + 4.0 * k + y


class Grid:
    """Where a style's players put their notes: the bars, beats and subdivisions of its feel, in the
    song's grid units (realize turns them into time, swinging or re-barring them)."""

    def __init__(self, ctx: Context, feel: str):
        m = ctx.meter
        self.origin = ctx.sections[0].u0  # a bar line
        self.feel = feel
        compound = m.beat % 3 == 0 and m.beat > 1
        if feel == "waltz":  # a bar a foot: three beats at 0, 2, 3 (even once re-barred), eighths between
            self.bar, beats, subs = float(m.foot), [0.0, 2.0, 3.0], [0.0, 1.0, 2.0, 2.5, 3.0, 3.5]
        elif feel == "six":  # six-eight: two dotted beats a bar, a foot each, three eighths in each
            self.bar, beats, subs = float(m.bar), [0.0, 4.0], [0.0, 2.0, 3.0, 4.0, 6.0, 7.0]
        else:
            self.bar = float(m.bar)
            beats = [float(b) for b in np.arange(0, m.bar, m.beat)]
            if compound:
                subs = [float(s) for s in np.arange(0, m.bar, m.beat / 3)]
            elif feel in ("shuffle", "twelve"):  # a full swing turns 0, 1/4 and 1/2 of a beat into triplets
                subs = [b + f * m.beat for b in beats for f in (0.0, 0.25, 0.5)]
            else:
                subs = [float(s) for s in np.arange(0, m.bar, m.beat / 2)]
        self.beats, self.subs = beats, subs
        self.beat = m.beat if feel not in ("waltz", "six") else (m.foot / 3 if feel == "waltz" else m.foot)
        self.triple = feel in ("waltz", "six") or compound or len(beats) == 3
        if feel in ("shuffle", "twelve", "six", "waltz") or compound:
            self.fine = subs
        else:  # sixteenths
            self.fine = [float(s) for s in np.arange(0, m.bar, m.beat / 4)]

    def bars(self, u0: float, u1: float) -> list[float]:
        k = int(np.ceil((u0 - self.origin) / self.bar - 1e-9))
        out = []
        while self.origin + k * self.bar < u1 - 1e-9:
            out.append(self.origin + k * self.bar)
            k += 1
        return out

    def _in(self, offsets, u0: float, u1: float) -> list[float]:
        start = self.origin + np.floor((u0 - self.origin) / self.bar + 1e-9) * self.bar
        out = []
        b = start
        while b < u1 - 1e-9:
            out += [b + o for o in offsets if u0 - 1e-9 <= b + o < u1 - 1e-9]
            b += self.bar
        return out

    def beats_in(self, u0: float, u1: float) -> list[float]:
        return self._in(self.beats, u0, u1)

    def subs_in(self, u0: float, u1: float) -> list[float]:
        return self._in(self.subs, u0, u1)

    def fine_in(self, u0: float, u1: float) -> list[float]:
        return self._in(self.fine, u0, u1)

    def beat_index(self, u: float) -> int:
        """Which beat of its bar u falls in (0 the downbeat)."""
        x = (u - self.origin) % self.bar
        return max(k for k, b in enumerate(self.beats) if b <= x + 1e-9)

    def on_beat(self, u: float) -> bool:
        x = (u - self.origin) % self.bar
        return any(abs(x - b) < 1e-6 for b in self.beats)

    def backbeat(self, u: float) -> bool:
        """Beats two and four (of four), two and three (a waltz), the second (six-eight, or a bar of two)."""
        if not self.on_beat(u):
            return False
        k, n = self.beat_index(u), len(self.beats)
        if self.feel == "waltz" or n == 3:
            return k > 0
        return k % 2 == 1


# --- harmony: the genome's functions, coloured where the tune allows ---------------------------------

# A colour: (semitones above the chord's root it adds, what it replaces: "third" or None, the qualities it
# suits). "minor" as a colour of IV is the minor iv (its third lowered); "power" drops the third.
COLOURS = {
    "6": (9, None, ("major",)),
    "maj7": (11, None, ("major",)),
    "7": (10, None, ("major", "minor")),
    "add9": (2, None, ("major", "minor")),
    "sus2": (2, "third", ("major", "minor")),
    "sus4": (5, "third", ("major",)),
    "power": (None, "third", ("major", "minor")),
    "minor": (3, "third", ("major",)),
}


def quality(pcs: tuple[int, int, int]) -> str:
    third = (pcs[1] - pcs[0]) % 12
    return "major" if third == 4 else "minor" if third == 3 else "other"


def clashes(pc: int, sung: list[tuple[float, float, int, bool]]) -> bool:
    """Whether a tone (a pitch class, in any octave) sounding against these sung notes would clash: a minor
    second or major seventh with any of them, or a major second, minor seventh or tritone with one that is
    strong (on a foot's start) or long (a beat or more)."""
    for _u0, _u1, pitch, strong in sung:
        ic = min((pc - pitch) % 12, (pitch - pc) % 12)
        if ic == 1 or (strong and ic in (2, 6)):
            return True
    return False


def rubs(pitch: int, sung: list[tuple[float, float, int, bool]]) -> bool:
    """Whether a pitch, where it is, rubs against a sung note: a minor second or a major seventh at any
    distance, or a major second, minor seventh or tritone within an octave of a strong or long one. A
    ninth or more away, a second is an ordinary extension of the chord (an added ninth under the tune)."""
    for _u0, _u1, q, strong in sung:
        d = abs(pitch - q)
        ic = min(d % 12, 12 - d % 12)
        if ic == 1 or (strong and ic in (2, 6) and d < 12):
            return True
    return False


# --- the context ---------------------------------------------------------------------------------------


@dataclass
class Plan:
    """What a style's arrangement decided beyond each section's parts."""

    feel: str = "straight"
    entrances: dict = field(default_factory=dict)  # (section, part) -> grid unit it comes in at
    exits: dict = field(default_factory=dict)  # (section, part) -> grid unit it stops at
    stops: set = field(default_factory=set)  # sections in stop-time
    half: set = field(default_factory=set)  # sections whose rhythm plays half-time


class StyleContext(Context):
    """The song laid out for a style's band: Context's facts, the style's grid, colour and lineup."""

    def __init__(self, genome, params, placed, lead, end, melody, sdef, feel: str):
        self.sdef = sdef
        self.style = params.style
        super().__init__(genome, params, placed, lead, end, melody)
        self.feel = feel
        self.grid = Grid(self, feel)
        self.plan = Plan(feel=feel)
        self.lineup = [name for name in sdef.order(self.band.lineup) if self.band.plays(name)]
        self.backing: list[tuple[float, float, int]] = []  # the backing voices' notes (grid units, pitch)
        self._colour: dict[float, str | None] = {}
        self._last: dict[str, list[int]] = {}  # each part's last voicing, for leading the next

    def on(self, name: str) -> bool:
        return name in self.lineup

    # --- what is sung, and where -----------------------------------------------------------------

    def sung_in(self, u0: float, u1: float) -> list[tuple[float, float, int, bool]]:
        """Every note sung over [u0, u1): the singer's, the lineage choir's and the backing voices',
        as (start, end, pitch, strong)."""
        out = []
        for t in self.tune:
            if t.sung and t.u0 < u1 - 1e-9 and t.u1 > u0 + 1e-9:
                strong = (t.u0 - self.sections[t.section].u0) % self.meter.foot < 1e-9 or t.u1 - t.u0 >= self.beat
                out.append((t.u0, t.u1, t.pitch, strong))
        for v0, v1, p in self.choir + self.backing:
            if v0 < u1 - 1e-9 and v1 > u0 + 1e-9:
                out.append((v0, v1, p, True))
        return out

    def floor(self, section: int) -> int:
        """Where comping should stay under: a little above the low end of what is sung in the section."""
        sung = sorted(t.pitch for t in self.tune_in(section) if t.sung) or sorted(t.pitch for t in self.tune)
        return int(sung[max(0, len(sung) // 10)]) + 2

    def top(self, section: int) -> int:
        """The top of what is sung (or played as the tune) in the section."""
        return max([t.pitch for t in self.tune_in(section)] or [t.pitch for t in self.tune])

    # --- harmony -----------------------------------------------------------------------------------

    def colour(self, c: Chord) -> str | None:
        """The colour this chord is meant to have (the style's vocabulary, as often as its harmony
        knob says), before the tune has its say at each moment."""
        if c.u0 not in self._colour:
            if len(self.pcs(c.symbol)) > 3:  # a person's seventh (sixth, ninth) is its colour: none drawn on top
                self._colour[c.u0] = None
                return None
            rng = self.rand("colour", c.u0)
            options = self.sdef.colours_for(c.symbol)
            pick = None
            if options and rng.random() < self.style.harmony:
                pick = options[int(rng.integers(len(options)))]
            self._colour[c.u0] = pick
        return self._colour[c.u0]

    def tones(self, c: Chord, u0: float, u1: float, colour: bool = True) -> list[int]:
        """The chord's pitch classes sounding over [u0, u1), root first: its triad, with its colour where
        no sung note there is a semitone from the colour's tone (where the colour then sits in a voicing
        is checked there: see fits())."""
        pcs = list(self.pcs(c.symbol))
        name = self.colour(c) if colour else None
        if not name:
            return pcs
        interval, replaces, suits = COLOURS[name]
        if quality(tuple(pcs)) not in suits:
            return pcs
        if interval is None:  # an open fifth: no third to clash
            return [pcs[0], pcs[2]]
        tone = (pcs[0] + interval) % 12
        if any(min((tone - q) % 12, (q - tone) % 12) == 1 for _a, _b, q, _s in self.sung_in(u0, u1)):
            return pcs
        if replaces == "third":
            return [pcs[0], tone, pcs[2]]
        return pcs + [tone]

    def fits(self, pitch: int, c: Chord, u0: float, u1: float) -> bool:
        """Whether a pitch may sound over [u0, u1) with this chord: its triad's own tones always; a colour's
        only where it doesn't rub against what is sung (rubs())."""
        if pitch % 12 in self.pcs(c.symbol):
            return True
        return not rubs(pitch, self.sung_in(u0, u1))

    def voicing(self, part: str, pcs: list[int], lo: int, hi: int, u0: float, u1: float, size: int = 4,
                root: bool = True, chord: Chord | None = None) -> list[int]:
        """A chord for a part in [lo, hi]: close position, led smoothly from the part's last chord,
        never on a pitch being sung (moved an octave down, or left out), and with `chord`, a colour tone
        that would rub against the tune where it lands moved an octave down, or left for the third."""
        tones = list(dict.fromkeys(pcs))
        if not root and len(tones) > 3:  # the bass has its note (the root, or a person's inversion's); the hands the rest
            under = self.bass(chord.symbol) if chord is not None else tones[0]
            tones = [t for t in tones if t != under] if under in tones else tones[1:]
        options = []
        for start in range(len(tones)):
            order = tones[start:] + tones[:start]
            for base in range(lo, hi + 1):
                if base % 12 != order[0]:
                    continue
                stack, p = [base], base
                for pc in order[1:size]:
                    p = p + ((pc - p) % 12 or 12)
                    stack.append(p)
                if stack[-1] <= hi:
                    options.append(stack)
        if not options:
            return []
        prev = self._last.get(part)
        if prev:
            centre = float(np.mean(prev))
            best = min(options, key=lambda ch: (sum(min(abs(p - q) for q in prev) for p in ch)
                                                + 0.3 * abs(np.mean(ch) - centre), ch))
        else:
            mid = (lo + hi) / 2
            best = min(options, key=lambda ch: (abs(np.mean(ch) - mid), ch))
        self._last[part] = best
        sung = {p for _a, _b, p, _s in self.sung_in(u0, u1)}
        out = []
        for p in best:
            while p in sung and p - 12 >= lo:
                p -= 12
            if chord is not None and not self.fits(p, chord, u0, u1):
                if p - 12 >= lo and self.fits(p - 12, chord, u0, u1):
                    p -= 12
                else:  # the colour gives way: the chord's own third (or root) in its place
                    triad = self.pcs(chord.symbol)
                    p = nearest({triad[1]}, p, lo, hi) if triad[1] not in pcs else nearest({triad[0]}, p, lo, hi)
            if p not in sung and p not in out:
                out.append(p)
        return sorted(out)

    def vel(self, part: str, u: float, base: float, under_words: float = 0.78) -> float:
        return super().vel(part, u, base, under_words)


# --- who does what where -----------------------------------------------------------------------------

PERCUSSION = ("drums", "percussion")


def family(part: str) -> str:
    from .synth import instruments

    return instruments.spec(part)["family"]


def busy(ctx: StyleContext, s) -> float:
    """How full the band is in a section: its energy, and a busy band comes in earlier and fuller."""
    return s.energy + 0.3 * (ctx.band.density - 0.5)


def idiom_of(spec, b: float) -> str:
    if isinstance(spec, str):
        return spec
    for threshold, idiom in spec:
        if b >= threshold - 1e-9:
            return idiom
    return ""


DEFAULT_PARTS = {  # for an instrument the style doesn't know (one added to the lineup by hand), by family
    "bass": {"*": "roots", "tag": "long"},
    "keys": {"verse1": "", "*": "comp", "tag": "ring"},
    "mallets": {"refrain": "bells", "bridge": "bells"},
    "organ": {"verse1": "", "*": "pad"},
    "pad": {"*": "pad"},
    "plucked": {"*": "strum", "tag": "ring"},
    "bowed": {"verse": "tone", "refrain": "counter", "bridge": "tone"},
    "blown": {"verse": "fills", "refrain": "descant"},
    "reed": {"verse": "fills", "refrain": "counter"},
    "lead": {"verse": "fills", "refrain": "descant"},
    "synth": {"verse1": "", "*": "arp"},
    "drums": {"verse1": "", "*": "groove", "tag": "end"},
    "percussion": {"refrain": "claps"},
}


def plan_style(ctx: StyleContext) -> None:
    """Decide, for every section, what each of the style's players does there."""
    sdef = ctx.sdef
    leads = [x for x in (sdef.playing(x, ctx.lineup) for x in sdef.leads) if ctx.on(x)] \
        or [x for x in ctx.lineup if family(x) not in PERCUSSION + ("bass",)]
    refrains = [i for i, s in enumerate(ctx.sections) if s.role == "refrain"]
    breaks = turns = verses = 0
    for i, s in enumerate(ctx.sections):
        r = s.role
        keys = []
        if r == "verse":
            verses += 1
            if verses == 1:
                keys.append("verse1")
        if r == "refrain" and len(refrains) > 1 and i == refrains[-1]:
            keys.append("last")
        keys += [r, "*"]
        parts: dict[str, str] = {}
        if leads and r in ("intro", "outro"):
            parts[leads[0]] = "lead"
        elif leads and r == "break":
            parts[leads[(breaks + 1) % len(leads)]] = "lead"
            breaks += 1
        elif leads and r == "turn":
            parts[leads[(turns + 1) % len(leads)]] = "quote"
            turns += 1
        b = busy(ctx, s)
        for inst in ctx.lineup:
            if inst in parts:
                continue
            table = sdef.parts.get(inst) or sdef.parts.get(sdef.part_of(inst)) or DEFAULT_PARTS.get(family(inst), {})
            spec = next((table[k] for k in keys if k in table), "")
            idiom = idiom_of(spec, b)
            if idiom:
                parts[inst] = idiom
        s.parts = parts


# --- helpers for the writers ----------------------------------------------------------------------------


def bass_range(ctx: StyleContext, part: str) -> tuple[int, int]:
    lo, hi = B.register_of(part)
    lo, hi = max(lo, ctx.tonic - 34), min(hi, ctx.tonic - 12)
    return lo, max(hi, lo + 12)


def comp_range(ctx: StyleContext, part: str, i: int) -> tuple[int, int]:
    """Where a comping part's chords sit: under the tune, clear of the singer's line."""
    lo, hi = B.register_of(part)
    return max(lo, ctx.tonic - 17), max(min(hi, ctx.floor(i)), max(lo, ctx.tonic - 17) + 9)


def high_range(ctx: StyleContext, part: str, i: int, gap: int = 3, span: int = 17) -> tuple[int, int]:
    """Above the tune: where bells, a music box or an arpeggio sparkle, out of the singer's way."""
    lo, hi = B.register_of(part)
    base = ctx.top(i) + gap
    while base + 7 > hi and base - 12 >= lo:
        base -= 12
    return max(lo, base), min(hi, base + span)


def until(positions: list[float], k: int, end: float) -> float:
    return positions[k + 1] if k + 1 < len(positions) else end


def chord_after(ctx: StyleContext, c: Chord) -> Chord | None:
    return next((x for x in ctx.chords if abs(x.u0 - c.u1) < 1e-9), None)


def scale_step(ctx: StyleContext, p: int, steps: int) -> int:
    """The pitch `steps` scale steps from p (in the tune's scale)."""
    q = p
    d = 1 if steps > 0 else -1
    for _ in range(abs(steps)):
        q += d
        while q % 12 not in ctx.scale:
            q += d
    return q


def ev(part: str, u0: float, u1: float, pitch: float, vel: float, art: str = "", i: int = 0, **kw) -> Ev:
    return Ev(part, u0, max(u1, u0 + 1e-3), float(pitch), float(np.clip(vel, 0.03, 1.0)), art=art, section=i, **kw)


# --- the bass --------------------------------------------------------------------------------------------


def w_roots(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A root where each chord starts, and its fifth half way through a long one."""
    lo, hi = bass_range(ctx, part)
    out = []
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        pcs = ctx.pcs(c.symbol)
        root = nearest({ctx.bass(c.symbol)}, lo + 7, lo, lo + 14)
        beats = ctx.grid.beats_in(c.u0, c.u1)
        out.append(ev(part, c.u0, c.u1, root, ctx.vel(part, c.u0, 0.8, 0.85), i=i))
        if len(beats) >= 3 and rng.random() < 0.6:
            mid = beats[len(beats) // 2]
            out[-1].u1 = mid
            out.append(ev(part, mid, c.u1, nearest({pcs[2]}, root - 5 if root - 5 >= lo else root + 7, lo, hi),
                          ctx.vel(part, mid, 0.7, 0.85), i=i))
    return out


def w_long(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    lo, hi = bass_range(ctx, part)
    return [ev(part, c.u0, c.u1, nearest({ctx.bass(c.symbol)}, lo + 7, lo, lo + 14), ctx.vel(part, c.u0, 0.7, 0.85), i=i)
            for c in ctx.chords_in(i)]


def w_two(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """The two-beat: the root on one and the fifth on three (in a waltz the root on one; in six-eight on
    both dotted beats), walking up into a new chord now and then."""
    lo, hi = bass_range(ctx, part)
    out = []
    density = ctx.band.density
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        pcs = ctx.pcs(c.symbol)
        root = nearest({ctx.bass(c.symbol)}, lo + 7, lo, lo + 14)
        fifth = nearest({pcs[2]}, root - 5 if root - 5 >= lo else root + 7, lo, hi)
        beats = ctx.grid.beats_in(c.u0, c.u1)
        hits = []
        bars = 0
        for u in beats:
            k, n = ctx.grid.beat_index(u), len(ctx.grid.beats)
            if abs(u - c.u0) < 1e-9:
                hits.append((u, root))
            elif k == 0:  # a chord held into another bar starts it on its fifth, then its root
                bars += 1
                hits.append((u, fifth if bars % 2 else root))
            elif (n == 4 and k == 2) or (n == 2 and k == 1):
                hits.append((u, fifth))
        nxt = chord_after(ctx, c)
        if nxt is not None and nxt.symbol != c.symbol and len(beats) >= 2 and rng.random() < 0.3 + 0.35 * density:
            target = nearest({ctx.bass(nxt.symbol)}, root, lo, hi)
            walk = [scale_step(ctx, target, -2), scale_step(ctx, target, -1)] if target > root else \
                [scale_step(ctx, target, 2), scale_step(ctx, target, 1)]
            hits = [h for h in hits if h[0] < beats[-2] - 1e-9] + list(zip(beats[-2:], walk))
        for k, (u, p) in enumerate(hits):
            u1 = hits[k + 1][0] if k + 1 < len(hits) else c.u1
            out.append(ev(part, u, min(u1, u + 1.6 * ctx.beat), p, ctx.vel(part, u, 0.82 if k == 0 else 0.7, 0.85), i=i))
    return out


def w_walk(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A walking line, a note a beat: the root, chord tones through, a step into each new chord."""
    lo, hi = bass_range(ctx, part)
    out = []
    prev = None
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        pcs = ctx.pcs(c.symbol)
        root = nearest({ctx.bass(c.symbol)}, prev if prev is not None else lo + 7, lo, hi)
        tones = [nearest({pcs[2]}, root + 7, lo, hi), nearest({pcs[1]}, root + 4, lo, hi), root + 12 if root + 12 <= hi else root]
        beats = ctx.grid.beats_in(c.u0, c.u1)
        nxt = chord_after(ctx, c)
        for k, u in enumerate(beats):
            if k == 0:
                p = root
            elif k == len(beats) - 1 and nxt is not None:
                target = nearest({ctx.bass(nxt.symbol)}, root, lo, hi)
                p = scale_step(ctx, target, -1 if rng.random() < 0.6 else 1)
                if clashes(p % 12, [x for x in ctx.sung_in(u, u + ctx.beat) if x[3]]):
                    p = tones[0]
            else:
                p = tones[int(rng.integers(len(tones)))]
            out.append(ev(part, u, until(beats, k, c.u1), p, ctx.vel(part, u, 0.78 if k == 0 else 0.66, 0.85), i=i))
            prev = p
    return out


def w_eighths(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """An electric or synth bass driving eighths on the root, an octave's pop now and then, and a step
    into each new chord."""
    lo, hi = bass_range(ctx, part)
    out = []
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        root = nearest({ctx.bass(c.symbol)}, lo + 7, lo, lo + 14)
        subs = ctx.grid.subs_in(c.u0, c.u1)
        nxt = chord_after(ctx, c)
        for k, u in enumerate(subs):
            p = root
            if k % 2 == 1 and rng.random() < 0.18 and root + 12 <= hi + 12:
                p = root + 12
            if nxt is not None and k == len(subs) - 1 and nxt.symbol != c.symbol:
                target = nearest({ctx.bass(nxt.symbol)}, root, lo, hi)
                p = scale_step(ctx, target, -1 if target >= root else 1)
            out.append(ev(part, u, u + 0.8 * (until(subs, k, c.u1) - u), p,
                          ctx.vel(part, u, 0.66 if ctx.grid.on_beat(u) else 0.5, 0.85), i=i))
    return out


def w_boogie(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A shuffle boogie on the low strings: the root under each beat, then its fifth or sixth on the lilt."""
    lo, hi = B.register_of(part)
    lo = max(lo, ctx.tonic - 24)
    out = []
    for c in ctx.chords_in(i):
        root = nearest({ctx.bass(c.symbol)}, lo + 4, lo, lo + 12)
        subs = ctx.grid.subs_in(c.u0, c.u1)
        for k, u in enumerate(subs):
            on = ctx.grid.on_beat(u)
            if not on and ctx.feel in ("shuffle", "twelve") and abs(((u - ctx.grid.origin) % ctx.beat) - ctx.beat / 4) < 1e-6:
                continue  # the shuffle's middle triplet is left out: long-short
            beat_no = ctx.grid.beat_index(u)
            p = root if on else root + (9 if beat_no % 2 else 7)
            if not on and clashes(p % 12, ctx.sung_in(u, u + ctx.beat / 2)):
                p = root + 7
            out.append(ev(part, u, until(subs, k, c.u1), p, ctx.vel(part, u, 0.72 if on else 0.58, 0.85),
                          art="down" if on else "up", i=i))
    return out


def w_sub(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A synth's sub bass: the root held through each bar, pushed on the last eighth into a new chord."""
    lo, hi = bass_range(ctx, part)
    out = []
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        root = nearest({ctx.bass(c.symbol)}, lo + 5, lo, lo + 12)
        starts = sorted(set([c.u0] + [b for b in ctx.grid.bars(c.u0, c.u1)]))
        for k, u in enumerate(starts):
            end = starts[k + 1] if k + 1 < len(starts) else c.u1
            out.append(ev(part, u, end - 0.1, root, ctx.vel(part, u, 0.8, 0.9), i=i))
        if ctx.energy_at(c.u0) > 0.5 and rng.random() < 0.5:  # a lift an octave up on the last beat's off-beat
            subs = ctx.grid.subs_in(c.u0, c.u1)
            if len(subs) >= 4:
                u = subs[-1]
                out[-1].u1 = u
                out.append(ev(part, u, c.u1, root + 12, ctx.vel(part, u, 0.6, 0.9), i=i))
    return out


def w_oom(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A waltz's bass: a root on each bar's one, the fifth on the next bar of a long chord."""
    lo, hi = bass_range(ctx, part)
    out = []
    for c in ctx.chords_in(i):
        pcs = ctx.pcs(c.symbol)
        root = nearest({ctx.bass(c.symbol)}, lo + 7, lo, lo + 14)
        fifth = nearest({pcs[2]}, root - 5 if root - 5 >= lo else root + 7, lo, hi)
        bars = sorted(set([c.u0] + ctx.grid.bars(c.u0, c.u1)))
        for k, u in enumerate(bars):
            end = bars[k + 1] if k + 1 < len(bars) else c.u1
            out.append(ev(part, u, min(end, u + 2 * ctx.beat), root if k % 2 == 0 else fifth,
                          ctx.vel(part, u, 0.8, 0.85), i=i))
    return out


def w_pedal(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """The tonic held under the chords, where the tune allows it; the chord's root where it doesn't."""
    lo, hi = bass_range(ctx, part)
    tonic = nearest({ctx.tonic % 12}, lo + 7, lo, lo + 14)
    out = []
    for c in ctx.chords_in(i):
        strong = [x for x in ctx.sung_in(c.u0, c.u1) if x[3]]
        p = tonic if not clashes(tonic % 12, strong) else nearest({ctx.bass(c.symbol)}, tonic, lo, hi)
        if out and out[-1].pitch == p and abs(out[-1].u1 - c.u0) < 1e-9:
            out[-1].u1 = c.u1
        else:
            out.append(ev(part, c.u0, c.u1, p, ctx.vel(part, c.u0, 0.7, 0.9), i=i))
    return out


# --- chords ----------------------------------------------------------------------------------------------

GUITARS = ("guitar", "electric")


def strokes(ctx: StyleContext, kind: str) -> list[tuple[float, str, float]]:
    """(offset in the bar, stroke, accent) for a strum in this feel: D a down stroke across the strings, U
    an up stroke catching the top strings, d a light down on the top strings."""
    feel, g = ctx.feel, ctx.grid
    if feel == "waltz":
        return [(0.0, "D", 1.0), (2.0, "D", 0.65), (2.5, "U", 0.42), (3.0, "D", 0.65), (3.5, "U", 0.42)]
    if feel == "six":
        return [(0.0, "D", 1.0), (2.0, "d", 0.55), (3.0, "U", 0.5), (4.0, "D", 0.85), (6.0, "d", 0.55), (7.0, "U", 0.5)]
    beats = g.beats
    if kind == "ring":
        return [(0.0, "D", 0.9)]
    if feel in ("shuffle", "twelve"):
        return [x for b in beats for x in ((b, "D", 1.0 if b == 0 else 0.75), (b + ctx.beat / 2, "U", 0.5))]
    if feel == "half":
        return [(0.0, "D", 1.0), (beats[len(beats) // 2], "D", 0.8)] + [(b + ctx.beat / 2, "U", 0.45) for b in beats[1::2]]
    if feel == "double":
        return [(u, "D" if k % 2 == 0 else "U", 0.9 if k == 0 else 0.6) for k, u in enumerate(g.subs)]
    if len(beats) == 4:  # the old faithful: down, down-up, up-down-up
        half = ctx.beat / 2
        return [(beats[0], "D", 1.0), (beats[1], "D", 0.7), (beats[1] + half, "U", 0.5), (beats[2] + half, "U", 0.5),
                (beats[3], "D", 0.7), (beats[3] + half, "U", 0.5)]
    return [(b, "D", 1.0 if k == 0 else 0.7) for k, b in enumerate(beats)] + [(b + ctx.beat / 2, "U", 0.45) for b in beats[1:]]


def fingering(ctx: StyleContext, part: str, c: Chord, u0: float, u1: float, i: int) -> list[int]:
    """The notes a chordal instrument holds for a chord: a guitar's open shape, anyone else's close chord
    under the tune."""
    tones = ctx.tones(c, u0, u1)
    if part in GUITARS:
        capo = ctx.capo
        pcs = tuple(tones) if len(tones) >= 3 else (tones[0], tones[1], tones[1])
        shape, _ = B.guitar_voicing(pcs, capo, len(ctx.pcs(c.symbol)))  # a person's added tone required
        sung = {p for _a, _b, p, _s in ctx.sung_in(u0, u1)}
        notes = [p - 12 if p in sung and p - 12 >= 40 + capo else p for _, p in shape]
        kept = [p for p in notes if ctx.fits(p, c, u0, u1)]  # a colour's string that would rub is left unplayed
        return kept if len(kept) >= 3 else [p for p in notes if p % 12 in ctx.pcs(c.symbol)]
    lo, hi = comp_range(ctx, part, i)
    return ctx.voicing(part, tones, lo, hi, u0, u1, size=4, chord=c)


def w_strum(ctx: StyleContext, i: int, part: str, kind: str = "strum") -> list[Ev]:
    """Strummed chords in the feel's pattern, each bar its own: some up strokes dropped, a chop now and then."""
    out = []
    density = ctx.band.density
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        for bar in sorted(set(ctx.grid.bars(c.u0, c.u1)) | {c.u0 - ((c.u0 - ctx.grid.origin) % ctx.grid.bar)}):
            for off, stroke, accent in strokes(ctx, kind):
                u = bar + off
                if not (c.u0 - 1e-9 <= u < c.u1 - 1e-9) or (kind == "ring" and u > c.u0 + 1e-9):
                    continue
                if stroke == "U" and (density < 0.3 or rng.random() < 0.15 + 0.3 * max(0.0, 0.5 - density)):
                    continue
                notes = fingering(ctx, part, c, u, c.u1, i)
                if not notes:
                    continue
                if stroke in ("U", "d"):
                    notes = notes[-min(len(notes), 3):][::-1] if stroke == "U" else notes[-4:]
                vel = ctx.vel(part, u, 0.85 * accent)
                spread = 0.05 if kind == "ring" else (0.018 + 0.02 * (1.0 - vel)) * (0.8 if stroke == "U" else 1.0)
                end = c.u1 if kind != "ring" else max(c.u1, ctx.sections[i].u1 if c.last else c.u1)
                for j, p in enumerate(notes):
                    out.append(ev(part, u, end, p, vel * (1.0 - 0.05 * j) * rng.uniform(0.85, 1.05),
                                  art="up" if stroke == "U" else "down", i=i,
                                  shift=spread * j / max(len(notes) - 1, 1)))
    return ring_on(out)


def ring_on(events: list[Ev]) -> list[Ev]:
    """Each string (pitch) of a strummed or picked part sounds until it is played again."""
    events.sort(key=lambda e: (e.u0, e.shift, e.pitch))
    last: dict[float, Ev] = {}
    for e in events:
        held = last.get(e.pitch)
        if held is not None and held.u1 > e.u0:
            held.u1 = e.u0
        last[e.pitch] = e
    return [e for e in events if e.u1 - e.u0 > 1e-6]


def w_ring(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    if part in GUITARS or family(part) in ("plucked",):
        return w_strum(ctx, i, part, "ring")
    out = []
    for c in ctx.chords_in(i):
        for j, p in enumerate(fingering(ctx, part, c, c.u0, c.u1, i)):
            out.append(ev(part, c.u0, c.u1, p, ctx.vel(part, c.u0, 0.6), i=i, shift=0.03 * j))
    return out


def bass_string(ctx: StyleContext, part: str, c: Chord, lo: int) -> tuple[int, int]:
    """A chord's root and fifth on a guitar's (or banjo's, a piano's left hand's) low strings."""
    pcs = ctx.pcs(c.symbol)
    root = nearest({ctx.bass(c.symbol)}, lo + 5, lo, lo + 11)
    return root, nearest({pcs[2]}, root + 7 if root + 7 <= lo + 16 else root - 5, lo, lo + 16)


def w_boom(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Boom-chick: the thumb on the bass string on the strong beats (root, then fifth), the upper strings on
    the others; and at a line's end, where the singer holds, a run on the bass strings into the next chord."""
    out = []
    lo = max(B.register_of(part)[0], ctx.tonic - 24)
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        root, fifth = bass_string(ctx, part, c, lo)
        beats = ctx.grid.beats_in(c.u0, c.u1)
        thumbs = 0
        for k, u in enumerate(beats):
            b, n = ctx.grid.beat_index(u), len(ctx.grid.beats)
            strong = b == 0 or (n == 4 and b == 2) or (n == 2 and b == 1)
            end = until(beats, k, c.u1)
            if strong:
                p = root if thumbs % 2 == 0 else fifth
                thumbs += 1
                out.append(ev(part, u, end, p, ctx.vel(part, u, 0.75), art="down", i=i))
            else:
                notes = fingering(ctx, part, c, u, end, i)[-4:]
                vel = ctx.vel(part, u, 0.55)
                for j, p in enumerate(notes):
                    out.append(ev(part, u, min(end, u + 0.8 * ctx.beat), p, vel * (1 - 0.04 * j), art="down", i=i,
                                  shift=0.012 * j))
        nxt = chord_after(ctx, c)
        if c.last and ctx.sections[i].sung and nxt is not None and len(beats) >= 2 and rng.random() < 0.55:
            target = nearest({ctx.bass(nxt.symbol)}, root, lo, lo + 12)
            start = beats[-2]
            run = [scale_step(ctx, target, -k) for k in (3, 2, 1)] + [target]
            subs = [u for u in ctx.grid.subs_in(start, c.u1)][:3]
            if all(not rubs(run[k], ctx.sung_in(u, until(subs, k, c.u1))) for k, u in enumerate(subs)):
                out = [e for e in out if not (start - 1e-9 <= e.u0 < c.u1 - 1e-9)]
                for k, u in enumerate(subs):
                    out.append(ev(part, u, until(subs, k, c.u1), run[k], ctx.vel(part, u, 0.62), art="down", i=i))
    return ring_on(out)


def w_travis(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Travis picking: the thumb alternating between the root string and another bass string on every
    beat, the fingers on the treble strings between, a pinch on the one."""
    out = []
    lo = max(B.register_of(part)[0], ctx.tonic - 24)
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        notes = fingering(ctx, part, c, c.u0, c.u1, i)
        if len(notes) < 3:
            continue
        root, fifth = bass_string(ctx, part, c, lo)
        treble = [p for p in notes if p > fifth + 2] or notes[-2:]
        beats = ctx.grid.beats_in(c.u0, c.u1)
        subs = ctx.grid.subs_in(c.u0, c.u1)
        for k, u in enumerate(beats):
            thumb = root if k % 2 == 0 else fifth
            out.append(ev(part, u, until(beats, k, c.u1), thumb, ctx.vel(part, u, 0.62 if k % 2 == 0 else 0.55),
                          art="down", i=i))
            if ctx.grid.beat_index(u) == 0 and rng.random() < 0.7:  # a pinch: thumb and a treble string together
                out.append(ev(part, u, until(beats, k, c.u1), treble[-1], ctx.vel(part, u, 0.5), art="up", i=i))
        for u in subs:
            if ctx.grid.on_beat(u) or rng.random() > 0.55 + 0.4 * ctx.band.density:
                continue
            p = treble[int(rng.integers(len(treble)))]
            out.append(ev(part, u, u + ctx.beat, p, ctx.vel(part, u, 0.45), art="up", i=i))
    return ring_on(out)


def own_art(part: str, art: str, plain: str) -> str:
    """The instrument's own stroke for an articulation where its module plays one (its SPEC names it: a
    banjo's `claw`, a mandolin's `chop`), else the plain stroke every plucked instrument knows."""
    from .synth import instruments

    return art if art in instruments.spec(part).get("articulations", {}) else plain


def fifth_string(ctx: StyleContext, part: str) -> int | None:
    """The pitch a banjo's short fifth string is tuned to for this key, as its module tunes it (A4 in D,
    G4 in G), or None for an instrument without one."""
    from .synth import instruments

    _, found = instruments.registered(part)
    tuned = getattr(found[1], "fifth_string", None) if found is not None else None
    return int(tuned(ctx.tonic)) if callable(tuned) else None


def first_position(ctx: StyleContext, part: str, pcs: list[int], u0: float, u1: float) -> list[int] | None:
    """A chord as a banjo player makes it near the nut, on the third, second and first strings as the
    banjo is tuned for the key: on each, the chord's tone at the lowest fret from open to the fourth (a
    tone no other string has yet, where it can), never on a pitch being sung. Open D's D chord is its
    open strings (F#3 A3 D4), its G G3 B3 D4, its A A3 C#4 E4; or None for an instrument without such
    strings (or a chord that doesn't lie there)."""
    from .synth import instruments

    _, found = instruments.registered(part)
    longs = getattr(found[1], "long_strings", None) if found is not None else None
    if not callable(longs):
        return None
    sung = {p for _a, _b, p, _s in ctx.sung_in(u0, u1)}
    shape: list[int] = []
    for open_ in reversed(longs(ctx.tonic)[:3]):  # the third string, the second, the first
        options = [open_ + f for f in range(5) if (open_ + f) % 12 in pcs and open_ + f not in sung]
        if not options:
            return None
        shape.append(min(options, key=lambda p: (p % 12 in {q % 12 for q in shape}, p - open_)))
    return shape


def roll_notes(ctx: StyleContext, part: str, c: Chord, u0: float, u1: float, i: int) -> tuple[list[int], int]:
    """A banjo's three fretted strings for a chord (as its player makes the chord near the nut), and its
    short fifth string: the drone the banjo is tuned to (the key's tonic or fifth, high), or the tonic
    high on an instrument without one."""
    tones = ctx.tones(c, u0, u1, colour=False)
    lo, hi = B.register_of(part)
    chord = first_position(ctx, part, tones, u0, u1) or \
        ctx.voicing(part, tones, max(lo, ctx.tonic - 7), min(hi, ctx.tonic + 12), u0, u1, size=3)
    drone = fifth_string(ctx, part)
    if drone is None:
        drone = nearest({ctx.tonic % 12}, ctx.tonic + 10, ctx.tonic + 5, min(hi, ctx.tonic + 17))
    if not ctx.fits(drone, c, u0, u1):  # the open fifth string, left for a chord tone where it would rub
        drone = nearest(set(tones), drone, ctx.tonic + 5, min(hi, ctx.tonic + 17))
    return chord or [ctx.tonic], drone


def w_roll(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A banjo's forward roll: thumb, index, middle, thumb, index, middle, thumb, middle across the eighths
    (third string, second, first, fifth, second, first, fifth, first), the thumb's notes of the 3-3-2 a
    little stronger (the roll's drive), never on a sung note; in triplets thumb, index, middle. Rolls are
    picked firmly (0.55 to 0.65 where nobody sings: a banjo is the loudest thing in a string band, and a
    roll's twang and sparkle go when it is picked softly), backing off under the words as backup does."""
    out = []
    for c in ctx.chords_in(i):
        subs = ctx.grid.subs_in(c.u0, c.u1)
        for k, u in enumerate(subs):
            chord, drone = roll_notes(ctx, part, c, u, u + ctx.beat, i)
            low, mid, top = chord[0], chord[len(chord) // 2], chord[-1]
            eighths = len(ctx.grid.subs) >= 8
            step = k % (8 if eighths else 6)
            cell = ([low, mid, top, drone, mid, top, drone, top] if eighths else [low, mid, top, drone, mid, top])[step]
            sung = {p for _a, _b, p, _s in ctx.sung_in(u, u + ctx.beat / 2)}
            if cell in sung:
                cell = drone if drone not in sung else cell - 12
            thumb = step in ((0, 3, 6) if eighths else (0, 3))
            accent = (0.72 if step == 0 else 0.68) if thumb else 0.62
            out.append(ev(part, u, u + 2 * ctx.beat, cell, ctx.vel(part, u, accent, 0.72), art="pick", i=i))
    return ring_on(out)


def w_claw(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Clawhammer: bum-ditty, a note struck down on the beat with the nail, the back of the nail brushing
    the strings, the thumb catching the high fifth string: the long-short-short the song's feet already
    have. A banjo plays them as its own strokes (claw, brush, thumb); another instrument strums them."""
    out = []
    bum, brush, thumb = own_art(part, "claw", "down"), own_art(part, "brush", "down"), own_art(part, "thumb", "up")
    for c in ctx.chords_in(i):
        for bar in sorted(set(ctx.grid.bars(c.u0, c.u1)) | {c.u0 - ((c.u0 - ctx.grid.origin) % ctx.grid.bar)}):
            cells = ([(0.0, "bum"), (2.0, "dit"), (3.0, "ty"), (4.0, "bum"), (6.0, "dit"), (7.0, "ty")]
                     if ctx.grid.bar >= 8 else [(0.0, "bum"), (2.0, "dit"), (3.0, "ty")])
            for off, what in cells:
                u = bar + off
                if not (c.u0 - 1e-9 <= u < c.u1 - 1e-9):
                    continue
                chord, drone = roll_notes(ctx, part, c, u, u + ctx.beat, i)
                if what == "bum":
                    sung = {p for _a, _b, p, _s in ctx.sung_in(u, u + ctx.beat)}
                    p = next((q for q in reversed(chord) if q not in sung), chord[0])
                    out.append(ev(part, u, u + ctx.beat, p, ctx.vel(part, u, 0.8, 0.88), art=bum, i=i))
                elif what == "dit":
                    for j, p in enumerate(chord):
                        out.append(ev(part, u, u + ctx.beat / 2, p, ctx.vel(part, u, 0.58, 0.88), art=brush, i=i,
                                      shift=0.01 * j))
                else:
                    out.append(ev(part, u, u + ctx.beat, drone, ctx.vel(part, u, 0.55, 0.88), art=thumb, i=i))
    return ring_on(out)


def w_chop(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A mandolin's chop: a three-note chord on every backbeat, struck hard and choked at once by the
    fretting hand (the mandolin's own `chop`: a burst of chord, the pick's scrape, the box's knock; a
    short muted strum on an instrument without one)."""
    out = []
    lo, hi = B.register_of(part)
    art = own_art(part, "chop", "mute")
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        for u in ctx.grid.beats_in(c.u0, c.u1):
            if not ctx.grid.backbeat(u):
                continue
            tones = ctx.tones(c, u, u + ctx.beat / 2, colour=False)
            notes = ctx.voicing(part, tones, max(lo, ctx.tonic - 5), min(hi, ctx.tonic + 14), u, u + ctx.beat / 2, 3)
            vel = ctx.vel(part, u, 0.64, 0.85) * rng.uniform(0.9, 1.05)
            for j, p in enumerate(notes):
                out.append(ev(part, u, u, p, vel, art=art, i=i, length=0.11, shift=0.006 * j))
    return out


def w_tremolo(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Tremolo picking: two notes of the chord above the tune picked fast and even, as a mandolin or an
    electric guitar through a tremolo sustains a chord. An instrument with a tremolo stroke of its own (a
    mandolin's: down and up at its player's rate, each pick landing on the ringing course) holds the two
    notes through the chord with it."""
    out = []
    own = own_art(part, "tremolo", "") == "tremolo"
    for c in ctx.chords_in(i):
        lo, hi = high_range(ctx, part, i, 2, 12)
        notes = ctx.voicing(part, ctx.tones(c, c.u0, c.u1), lo, hi, c.u0, c.u1, 2, chord=c)
        if own:
            out += [ev(part, c.u0, c.u1, p, ctx.vel(part, c.u0, 0.36), art="tremolo", i=i) for p in notes]
            continue
        for k, u in enumerate(ctx.grid.fine_in(c.u0, c.u1)):  # picked down and up in turn
            for p in notes:
                out.append(ev(part, u, u + 0.4, p, ctx.vel(part, u, 0.5 if not ctx.grid.on_beat(u) else 0.58),
                              art="up" if k % 2 else "down", i=i))
    return out


def left_hand(ctx: StyleContext, part: str, c: Chord) -> tuple[int, int]:
    lo = max(B.register_of(part)[0], ctx.tonic - 26)
    return bass_string(ctx, part, c, lo)


def w_comp(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A piano's comping: the left hand's root and fifth on the strong beats, the right hand's chord on the
    others (a shuffle's with its lilting pickup), in a waltz oom-pah-pah."""
    out = []
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        root, fifth = left_hand(ctx, part, c)
        beats = ctx.grid.beats_in(c.u0, c.u1)
        lh = 0
        for k, u in enumerate(beats):
            b, n = ctx.grid.beat_index(u), len(ctx.grid.beats)
            end = until(beats, k, c.u1)
            if b == 0 or (n == 4 and b == 2) or (n == 2 and b == 1) or abs(u - c.u0) < 1e-9:
                out.append(ev(part, u, end, root if lh % 2 == 0 else fifth, ctx.vel(part, u, 0.62), i=i))
                lh += 1
            if b != 0 or n == 2:
                for j, p in enumerate(fingering(ctx, part, c, u, end, i)):
                    out.append(ev(part, u, u + 0.85 * (end - u), p, ctx.vel(part, u, 0.5), i=i, shift=0.004 * j))
                if ctx.feel in ("shuffle", "twelve", "swing") and ctx.grid.backbeat(u) and rng.random() < 0.35:
                    v = u + ctx.beat / 2  # the lilting pickup into the next beat
                    if v < c.u1 - 1e-9:
                        for p in fingering(ctx, part, c, v, v + ctx.beat / 2, i):
                            out.append(ev(part, v, v + ctx.beat / 2, p, ctx.vel(part, v, 0.36), i=i))
    return out


def w_arpeggio(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Broken chords: the root low in the left hand, then up the chord through the subdivisions and back,
    as a ballad's piano or a harp plays them, staying under the tune."""
    out = []
    lo_r, hi_r = B.register_of(part)
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        root, _ = left_hand(ctx, part, c)
        subs = ctx.grid.subs_in(c.u0, c.u1)
        top = ctx.floor(i) + 1
        tones = ctx.tones(c, c.u0, c.u1)
        ladder = [p for p in range(root, top + 1) if p % 12 in tones and ctx.fits(p, c, c.u0, c.u1)][:6]
        if len(ladder) < 3:
            ladder = [root, root + 7, root + 12]
        shape = ladder + ladder[-2:0:-1]
        start = int(rng.integers(0, 2))
        for k, u in enumerate(subs):
            p = shape[(k + start) % len(shape)] if k else root
            if not (lo_r <= p <= hi_r):
                continue
            sung = {q for _a, _b, q, _s in ctx.sung_in(u, u + ctx.beat)}
            if p in sung:
                p -= 12
            out.append(ev(part, u, min(c.u1, u + 3 * ctx.beat), p, ctx.vel(part, u, 0.6 if k == 0 else 0.45), i=i))
    return ring_on(out)


def w_block(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Gospel piano in twelve-eight: a chord on every beat, the left hand's octave on the strong ones, and
    the last triplet of the backbeats pushing into the next beat."""
    out = []
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        root, _ = left_hand(ctx, part, c)
        beats = ctx.grid.beats_in(c.u0, c.u1)
        for k, u in enumerate(beats):
            end = until(beats, k, c.u1)
            b = ctx.grid.beat_index(u)
            if b % 2 == 0 or abs(u - c.u0) < 1e-9:
                out.append(ev(part, u, end, root, ctx.vel(part, u, 0.6), i=i))
                if root + 12 < ctx.floor(i) - 7:
                    out.append(ev(part, u, end, root + 12, ctx.vel(part, u, 0.45), i=i))
            accent = 0.62 if ctx.grid.backbeat(u) else 0.5
            for j, p in enumerate(fingering(ctx, part, c, u, end, i)):
                out.append(ev(part, u, u + 0.8 * (end - u), p, ctx.vel(part, u, accent), i=i, shift=0.005 * j))
            if ctx.grid.backbeat(u) and rng.random() < 0.6:
                v = u + ctx.beat / 2
                if v < c.u1 - 1e-9:
                    for p in fingering(ctx, part, c, v, v + ctx.beat / 2, i):
                        out.append(ev(part, v, v + ctx.beat / 2, p, ctx.vel(part, v, 0.38), i=i))
    return out


def w_oompah(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Oom-pah: a bass note on the strong beats (root, then fifth), a short chord on the others, as a
    concertina, an accordion or a pub piano keeps a song going; an instrument with a left hand of bass and
    chord buttons (an accordion's Stradella) is told which is which."""
    from .synth import instruments

    arts = instruments.spec(part).get("articulations", {})
    oom, pah = ("bass", "chord") if "bass" in arts and "chord" in arts else ("", "")
    out = []
    n = len(ctx.grid.beats)
    for c in ctx.chords_in(i):
        root, fifth = left_hand(ctx, part, c)
        beats = ctx.grid.beats_in(c.u0, c.u1)
        subs = ctx.grid.subs_in(c.u0, c.u1)
        lh = 0
        for k, u in enumerate(beats):
            b = ctx.grid.beat_index(u)
            end = until(beats, k, c.u1)
            if n == 2:  # a bar of two beats: each an oom and its subdivisions the pahs (oom-pa-pa in six-eight)
                pas = [v for v in subs if u + 1e-9 < v < end - 1e-9]
                out.append(ev(part, u, u + 0.7 * ((pas[0] if pas else end) - u), root if lh % 2 == 0 else fifth,
                              ctx.vel(part, u, 0.7), art=oom, i=i))
                lh += 1
                for j, v in enumerate(pas):
                    stop = pas[j + 1] if j + 1 < len(pas) else end
                    for p in fingering(ctx, part, c, v, stop, i)[-3:]:
                        out.append(ev(part, v, v + 0.55 * (stop - v), p, ctx.vel(part, v, 0.55 - 0.05 * j), art=pah,
                                      i=i))
            elif b == 0 or (n == 4 and b == 2) or abs(u - c.u0) < 1e-9:
                out.append(ev(part, u, u + 0.7 * (end - u), root if lh % 2 == 0 else fifth, ctx.vel(part, u, 0.7),
                              art=oom, i=i))
                lh += 1
            else:
                for p in fingering(ctx, part, c, u, end, i)[-3:]:
                    out.append(ev(part, u, u + 0.55 * (end - u), p, ctx.vel(part, u, 0.55), art=pah, i=i))
    return out


def w_pad(ctx: StyleContext, i: int, part: str, swell_all: bool = False) -> list[Ev]:
    """Held chords under the tune, each chord led smoothly into the next, swelling in at each phrase."""
    out = []
    phrase_starts = {p0 for p0, _ in ctx.phrases}
    lo, hi = B.register_of(part)
    lo, hi = max(lo, ctx.tonic - 14), max(min(hi, ctx.floor(i)), max(lo, ctx.tonic - 14) + 10)
    s = ctx.sections[i]
    alone = not s.sung and len(s.parts) == 1  # a pad on its own (an intro swelling in) plays out, not under
    base = 0.85 if alone else 0.5
    for c in ctx.chords_in(i):
        notes = ctx.voicing(part, ctx.tones(c, c.u0, c.u1), lo, hi, c.u0, c.u1, size=4, chord=c)
        art = "swell" if swell_all or any(abs(c.u0 - p) < 1e-9 for p in phrase_starts) else ""
        for p in notes:
            held = next((e for e in out if e.pitch == p and abs(e.u1 - c.u0) < 1e-9), None)
            if held is not None and not art:
                held.u1 = c.u1  # a common tone is held over
            else:
                out.append(ev(part, c.u0, c.u1, p, ctx.vel(part, c.u0, base, 0.9), art=art, i=i))
    return out


def w_swell(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    return w_pad(ctx, i, part, swell_all=True)


def w_epiano(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Lo-fi electric piano: the chord's colour without its root (the bass has it), laid back: struck on
    the one and let ring, answered on an off-beat, a little different every bar."""
    out = []
    lo, hi = B.register_of(part)
    lo, hi = max(lo, ctx.tonic - 10), max(min(hi, ctx.floor(i)), max(lo, ctx.tonic - 10) + 9)
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        subs = ctx.grid.subs_in(c.u0, c.u1)
        hits = [subs[0]] if subs else []
        offs = [u for u in subs if not ctx.grid.on_beat(u)]
        if offs:
            hits.append(offs[int(rng.integers(len(offs)))])
        if len(subs) >= 6 and rng.random() < 0.4:
            hits.append(subs[-2] if subs[-2] not in hits else subs[-1])
        hits = sorted(set(hits))
        for k, u in enumerate(hits):
            end = hits[k + 1] if k + 1 < len(hits) else c.u1
            notes = ctx.voicing(part, ctx.tones(c, u, end), lo, hi, u, end, size=4, root=False, chord=c)
            for j, p in enumerate(notes):
                out.append(ev(part, u, end, p, ctx.vel(part, u, 0.5 if k == 0 else 0.4), i=i, shift=0.008 * j))
    return out


def w_pulse(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A chord repeated on every eighth, accented on the beats, struck down on them and up between: a driving
    electric guitar, a pulsing piano."""
    out = []
    for c in ctx.chords_in(i):
        subs = ctx.grid.subs_in(c.u0, c.u1)
        for k, u in enumerate(subs):
            end = until(subs, k, c.u1)
            notes = fingering(ctx, part, c, u, end, i)[-3:]
            on = ctx.grid.on_beat(u)
            for p in notes:
                out.append(ev(part, u, u + 0.8 * (end - u), p, ctx.vel(part, u, 0.58 if on else 0.46),
                              art="down" if on else "up", i=i))
    return out


def w_arp(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """An arpeggiator: the chord's tones up and down through two octaves above the tune, every sixteenth
    (every triplet in a lilting feel)."""
    out = []
    for c in ctx.chords_in(i):
        lo, hi = high_range(ctx, part, i, 2, 20)
        tones = ctx.tones(c, c.u0, c.u1)
        ladder = [p for p in range(lo, hi + 1) if p % 12 in tones and ctx.fits(p, c, c.u0, c.u1)][:7]
        if len(ladder) < 3:
            continue
        shape = ladder + ladder[-2:0:-1]
        fine = ctx.grid.fine_in(c.u0, c.u1)
        for k, u in enumerate(fine):
            end = until(fine, k, c.u1)
            p = shape[k % len(shape)]
            out.append(ev(part, u, u + 0.9 * (end - u), p, ctx.vel(part, u, 0.46 if ctx.grid.on_beat(u) else 0.36, 0.85), i=i))
    return out


def w_box(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A music box: the chord's tones picked out high above the tune, up and back, ringing on, a few left out."""
    out = []
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        lo, hi = high_range(ctx, part, i, 5, 19)
        tones = ctx.tones(c, c.u0, c.u1)
        ladder = [p for p in range(lo, hi + 1) if p % 12 in tones and ctx.fits(p, c, c.u0, c.u1)][:5]
        if len(ladder) < 2:
            continue
        shape = [ladder[k] for k in (0, 2, 1, 3, 2, 4, 3, 1) if k < len(ladder)]
        subs = ctx.grid.subs_in(c.u0, c.u1)
        for k, u in enumerate(subs):
            if k and rng.random() < 0.25 * (1.0 - ctx.band.density):
                continue
            p = shape[k % len(shape)]
            out.append(ev(part, u, min(c.u1 + ctx.beat, u + 4 * ctx.beat), p, ctx.vel(part, u, 0.45, 0.9), i=i))
    return ring_on(out)


def w_bells(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Bells, a celesta or a vibraphone: a chord tone or two high above the tune on the strong beats, ringing."""
    out = []
    for c in ctx.chords_in(i):
        rng = ctx.rand(part, c.u0)
        lo, hi = high_range(ctx, part, i, 3, 14)
        tones = ctx.tones(c, c.u0, c.u1)
        options = [p for p in range(lo, hi + 1) if p % 12 in tones and ctx.fits(p, c, c.u0, c.u1)]
        if not options:
            continue
        for u in ctx.grid.beats_in(c.u0, c.u1):
            b = ctx.grid.beat_index(u)
            if b not in (0, len(ctx.grid.beats) // 2) and not abs(u - c.u0) < 1e-9:
                continue
            if rng.random() < 0.3:
                continue
            p = options[int(rng.integers(len(options)))]
            out.append(ev(part, u, u + 3 * ctx.beat, p, ctx.vel(part, u, 0.42, 0.9), i=i))
    return ring_on(out)


def w_drone(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """The tonic and a softer fifth held through the section, below the singer."""
    s = ctx.sections[i]
    root = ctx.tonic - 12
    lo, hi = B.register_of(part)
    while root < lo:
        root += 12
    fifth = root + 7
    return [ev(part, s.u0, s.u1, root, 0.7 * (0.7 + 0.4 * s.energy), i=i),
            ev(part, s.u0, s.u1, fifth, 0.4 * (0.7 + 0.4 * s.energy), i=i)]


# --- the tune, answers and lines ---------------------------------------------------------------------------

BOWED = ("fiddle", "cello", "strings", "steel")
SLIDING = ("steel", "slide", "harmonica", "synthlead")
TREMOLO_LEADS = ("mandolin",)  # plucked instruments whose players tremolo a tune's long notes


def sliding(ctx: StyleContext, part: str, events: list[Ev]) -> list[Ev]:
    """How a pedal steel, a slide, a harmonica or a synth lead joins its notes: sliding into the long ones;
    and how a mandolin holds a tune's long notes (a beat and a half or more): tremolo, its picks filling
    them as its short-ringing courses would not."""
    if part in TREMOLO_LEADS and own_art(part, "tremolo", "") == "tremolo":
        for e in events:
            if e.u1 - e.u0 >= 1.5 * ctx.beat - 1e-9 and not e.art:
                e.art = "tremolo"
        return events
    if part not in SLIDING:
        return events
    for e in events:
        rng = ctx.rand(part, e.u0)
        if e.u1 - e.u0 >= 2 * ctx.sub and not e.art and rng.random() < 0.55:
            e.art = "slide"
    return events


def w_lead(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """The tune where nobody sings (an intro, a break, an outro), in the instrument's own octave and way."""
    return sliding(ctx, part, B.statement(ctx, part, [t for t in ctx.tune_in(i) if not t.sung], 0.85, i))


def w_quote(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    return sliding(ctx, part, B.quote(ctx, i, part))


def w_counter(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    top = ctx.top(i)
    return sliding(ctx, part, B.counter(ctx, i, part, top + 1, top + 13, 0.55, bow=part in BOWED))


def w_descant(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    top = ctx.top(i)
    return B.counter(ctx, i, part, top + 5, top + 17, 0.48)


def w_under(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A line of its own below the tune: a cello's, or a pedal steel's swells in the alto, moving where the
    singer holds and clear of every sung note."""
    lo = ctx.tonic - (19 if part == "cello" else 12)
    hi = ctx.floor(i) - 3
    out = B.counter(ctx, i, part, lo, max(hi, lo + 7), 0.5, bow=part in BOWED)
    for e in out:
        if part == "steel" and e.u1 - e.u0 >= ctx.bar / 2 - 1e-9:
            e.art = "swell"
    return sliding(ctx, part, out)


def w_tone(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    return B.held_tone(ctx, i, part, ctx.top(i))


def w_double(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    tune = ctx.tune_in(i)
    if not tune:
        return []
    return sliding(ctx, part, B.statement(ctx, part, B.held_through(ctx, tune) if ctx.choir else tune, 0.5, i))


def w_hook(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A glockenspiel or a celesta ringing the tune's strong notes an octave or two above the singer."""
    notes = [t for t in ctx.tune_in(i) if t.sung and (t.u0 - ctx.sections[i].u0) % ctx.meter.foot < 1e-9]
    if not notes:
        return []
    lo, hi = B.register_of(part)
    shift = 12
    while max(t.pitch for t in notes) + shift + 12 <= hi and min(t.pitch for t in notes) + shift < lo:
        shift += 12
    if min(t.pitch for t in notes) + shift < lo:
        shift += 12
    return [ev(part, t.u0, t.u0 + 2 * ctx.beat, t.pitch + shift, ctx.vel(part, t.u0, 0.45, 1.0), i=i) for t in notes
            if lo <= t.pitch + shift <= hi]


# --- percussion -------------------------------------------------------------------------------------------


def hit(part: str, u: float, art: str, vel: float, i: int, length: float = 0.0) -> Ev:
    return Ev(part, u, u + 0.5, 0.0, float(np.clip(vel, 0.03, 1.0)), art=art, section=i, length=length)


def groove_bar(ctx: StyleContext, kind: str) -> list[tuple[float, str, float]]:
    """(offset in the bar, piece, velocity) for one bar of a kit or a drum machine."""
    g, feel = ctx.grid, ctx.feel
    beats, subs = g.beats, g.subs
    n = len(beats)
    back = [b for k, b in enumerate(beats) if (k > 0 if n == 3 else k % 2 == 1)]
    out = []
    if kind == "brushes":
        for k, b in enumerate(beats):
            out.append((b, "brush-sweep", 0.5 if k == 0 else 0.4))
        out += [(b, "brush-tap", 0.55) for b in back] + [(0.0, "kick", 0.35)]
        if n == 4:
            out.append((beats[2], "kick", 0.28))
        return out
    if kind == "toms":  # the floor tom on every beat, the kick under the strong ones, a rim click on the backbeat
        out += [(b, "tom-lo", 0.62 if k == 0 else 0.5) for k, b in enumerate(beats)]
        out += [(0.0, "kick", 0.7)] + ([(beats[2], "kick", 0.6)] if n == 4 else [])
        out += [(b, "rim", 0.4) for b in back]
        return out
    if kind == "four":  # four to the floor: the kick on every beat, the snare on the backbeat, open hats between
        out += [(b, "kick", 0.72) for b in beats] + [(b, "snare", 0.64) for b in back]
        out += [(s, "hat-open" if k % 4 == 3 else "hat", 0.4) for k, s in enumerate(subs) if not g.on_beat(g.origin + s)]
        return out
    if kind == "half" or feel == "half":
        out += [(0.0, "kick", 0.75), (beats[n // 2] if n > 1 else 0.0, "snare", 0.7)]
        out += [(s, "hat", 0.42 if g.on_beat(g.origin + s) else 0.3) for s in subs]
        return out
    if kind == "lofi":  # a soft boom-bap: kick on the one and late in the bar, snare on the backbeat, lazy hats
        out += [(0.0, "kick", 0.62), (subs[len(subs) * 5 // 8] if len(subs) >= 8 else beats[-1], "kick", 0.5)]
        out += [(b, "snare", 0.5) for b in back]
        out += [(s, "hat", 0.34 if g.on_beat(g.origin + s) else 0.24) for s in subs]
        return out
    if kind == "machine":
        return groove_bar(ctx, "four")
    # a kit's own groove for the feel
    if feel == "waltz":
        return [(0.0, "kick", 0.7)] + [(b, "snare", 0.45) for b in beats[1:]] + [(s, "hat", 0.32) for s in subs]
    if feel == "six":
        return [(0.0, "kick", 0.72), (4.0, "snare", 0.6)] + [(s, "hat", 0.36 if s in (0.0, 4.0) else 0.26) for s in subs]
    if feel == "double":
        out += [(b, "kick", 0.7) for b in beats] + [(b + ctx.beat / 2, "snare", 0.55) for b in beats]
        return out + [(s, "hat", 0.3) for s in subs]
    out += [(0.0, "kick", 0.78)] + ([(beats[2], "kick", 0.65)] if n == 4 else [])
    out += [(b, "snare", 0.7) for b in back]
    ride = [s for s in subs if feel not in ("shuffle", "twelve") or abs((s % ctx.beat) - ctx.beat / 4) > 1e-6]
    out += [(s, "hat", 0.42 if g.on_beat(g.origin + s) else 0.3) for s in ride]
    return out


def w_groove(ctx: StyleContext, i: int, part: str, kind: str = "groove") -> list[Ev]:
    """A kit or drum machine playing the feel's groove bar by bar: ghost strokes left out when the band is
    sparse, a fill into a bigger section, a crash where the band arrives."""
    out = []
    s = ctx.sections[i]
    nxt = ctx.sections[i + 1] if i + 1 < len(ctx.sections) else None
    bars = ctx.grid.bars(s.u0, s.u1)
    for k, bar in enumerate(bars):
        rng = ctx.rand(part, bar)
        hits = groove_bar(ctx, kind)
        last = k == len(bars) - 1
        if last and nxt is not None and nxt.energy >= s.energy and kind not in ("brushes", "lofi"):
            start = ctx.grid.beats[-1]
            hits = [h for h in hits if h[0] < start - 1e-9]
            fine = [f for f in ctx.grid.fine if f >= start - 1e-9]
            toms = ("snare", "tom-hi", "tom-mid", "tom-lo")
            hits += [(f, toms[min(3, j * 4 // max(len(fine), 1))], 0.45 + 0.3 * j / max(len(fine) - 1, 1))
                     for j, f in enumerate(fine)]
        if k == 0 and i > 0 and s.energy >= ctx.sections[i - 1].energy + 0.05 and kind not in ("brushes", "lofi"):
            hits.append((0.0, "crash", 0.6))
        for off, piece, v in hits:
            if piece == "hat" and v < 0.32 and rng.random() > 0.4 + 0.6 * ctx.band.density:
                continue
            u = bar + off
            if s.u0 - 1e-9 <= u < s.u1 - 1e-9:
                out.append(hit(part, u, piece, ctx.vel(part, u, v, 0.9), i))
    return out


def w_brushes(ctx, i, part):
    return w_groove(ctx, i, part, "brushes")


def w_four(ctx, i, part):
    return w_groove(ctx, i, part, "four")


def w_toms(ctx, i, part):
    return w_groove(ctx, i, part, "toms")


def w_half(ctx, i, part):
    return w_groove(ctx, i, part, "half")


def w_lofi(ctx, i, part):
    return w_groove(ctx, i, part, "lofi")


def w_machine(ctx, i, part):
    return w_groove(ctx, i, part, "machine")


def w_end(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Winding down: a soft kick on each bar's one and a crash on the last chord."""
    s = ctx.sections[i]
    out = [hit(part, bar, "kick", 0.35, i) for bar in ctx.grid.bars(s.u0, s.u1)[:-1]]
    if i == len(ctx.sections) - 1 and ctx.chords:
        final = ctx.chords[-1].u0
        out += [hit(part, final, "kick", 0.6, i), hit(part, final, "crash", 0.5, i)]
    return out


def on_beats(ctx: StyleContext, i: int, part: str, which, piece: str, vel: float) -> list[Ev]:
    s = ctx.sections[i]
    out = []
    for u in ctx.grid.beats_in(s.u0, s.u1):
        if which(u):
            out.append(hit(part, u, piece, ctx.vel(part, u, vel, 0.95), i))
    return out


def w_stomp(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Feet on the floor on the strong beats (every beat in a waltz's one, both dotted beats in six-eight)."""
    n = len(ctx.grid.beats)
    return on_beats(ctx, i, part, lambda u: ctx.grid.beat_index(u) in ((0, 2) if n == 4 else (0,) if n == 3 else (0, 1)),
                    "stomp", 0.8)


def w_stomp4(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    return on_beats(ctx, i, part, lambda u: True, "stomp", 0.7)


def w_claps(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """Hand claps on the backbeat."""
    return on_beats(ctx, i, part, ctx.grid.backbeat, "clap", 0.72)


def w_tambourine(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    """A tambourine struck on the backbeat and shaken lightly between when the band is full."""
    out = on_beats(ctx, i, part, ctx.grid.backbeat, "tambourine", 0.7)
    s = ctx.sections[i]
    if s.energy > 0.6:
        for u in ctx.grid.subs_in(s.u0, s.u1):
            if not ctx.grid.on_beat(u):
                out.append(hit(part, u, "shaker", ctx.vel(part, u, 0.3, 0.95), i))
    return out


def w_shaker(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    s = ctx.sections[i]
    return [hit(part, u, "shaker", ctx.vel(part, u, 0.42 if not ctx.grid.on_beat(u) else 0.3, 0.95), i)
            for u in ctx.grid.subs_in(s.u0, s.u1)]


def w_cajon(ctx: StyleContext, i: int, part: str) -> list[Ev]:
    s = ctx.sections[i]
    out = []
    for bar in ctx.grid.bars(s.u0, s.u1):
        rng = ctx.rand(part, bar)
        for off, piece, v in groove_bar(ctx, "groove"):
            piece = {"kick": "cajon-bass", "snare": "cajon-slap"}.get(piece)
            if piece is None or (piece == "cajon-bass" and off > 0 and rng.random() < 0.4):
                continue
            out.append(hit(part, bar + off, piece, ctx.vel(part, bar + off, v, 0.9), i))
    return out


WRITERS = {
    "roots": w_roots, "long": w_long, "two": w_two, "walk": w_walk, "eighths": w_eighths, "boogie": w_boogie,
    "sub": w_sub, "oom": w_oom, "pedal": w_pedal,
    "strum": w_strum, "ring": w_ring, "boom": w_boom, "travis": w_travis, "roll": w_roll, "claw": w_claw,
    "chop": w_chop, "tremolo": w_tremolo, "comp": w_comp, "arpeggio": w_arpeggio, "block": w_block,
    "oompah": w_oompah, "pad": w_pad, "swell": w_swell, "epiano": w_epiano, "pulse": w_pulse, "arp": w_arp,
    "box": w_box, "bells": w_bells, "drone": w_drone,
    "lead": w_lead, "quote": w_quote, "counter": w_counter, "descant": w_descant, "under": w_under,
    "tone": w_tone, "double": w_double, "hook": w_hook,
    "groove": w_groove, "brushes": w_brushes, "four": w_four, "toms": w_toms, "half": w_half, "lofi": w_lofi,
    "machine": w_machine, "end": w_end, "stomp": w_stomp, "stomp4": w_stomp4, "claps": w_claps,
    "tambourine": w_tambourine, "shaker": w_shaker, "cajon": w_cajon,
}
# "fills" is written for all sections at once (band.fills), after the rest.


# --- backing voices -----------------------------------------------------------------------------------------
#
# The lineage's voices (the choir, one more each generation) back the singer where the style wants them:
# the gang on the tune, a harmony above and below, answers at the ends of lines, or oohs on the chords.
# Never where the genome already gives the lineage its own harmony (the bridge, the tag), and only as
# many voices as the lineage has: at the first generation a shanty's gang is one sailor.


@dataclass
class Sung:
    """A backing voice's note in grid units, and what it sings."""

    voice: int
    u0: float
    u1: float
    pitch: int
    vel: float
    syllable: str
    word: str
    word_len: int
    line_end: bool
    section: str
    phrase: str


def backing(ctx: Context, melody: list[dict], style) -> list[Sung]:
    n = int(getattr(ctx.params, "choir", 0))
    kind = style.backing
    if not kind or n <= 0:
        return []
    genome = ctx.genome
    ordered = sorted(melody, key=lambda m: m["u"])
    refrains = [i for i, s in enumerate(ctx.sections) if s.role == "refrain"]
    verses = [i for i, s in enumerate(ctx.sections) if s.role == "verse"]
    if kind == "oohs":
        where = set(verses[1:]) | set(refrains)
    elif kind == "thirds":
        where = set(refrains[1:] if len(refrains) > 2 else refrains)
    else:
        where = set(refrains)
    where = {i for i in where if not genome.section(ctx.sections[i].name).choir}
    out: list[Sung] = []
    for k, m in enumerate(ordered):
        if not m["syllable"]:
            continue
        i = ctx.section_at(m["u"])
        if i not in where:
            continue
        u1 = min(m["u_end"], ordered[k + 1]["u"]) if k + 1 < len(ordered) else ctx.end
        if kind == "gang":
            for v in range(n):
                out.append(Sung(v, m["u"], u1, int(m["pitch"]), 0.85 * m["vel"], m["syllable"], m["word"], m["word_len"],
                                m["line_end"], m["section"], m["phrase"]))
        elif kind == "thirds":
            for v in range(n):
                p = choir_harmony(int(m["pitch"]), m["chord"], ctx.tonic, ctx.mode, (1, 0, 2)[v % 3]) - 12 * (v // 3)
                out.append(Sung(v, m["u"], u1, p, 0.8 * m["vel"], m["syllable"], m["word"], m["word_len"], m["line_end"],
                                m["section"], m["phrase"]))
        elif kind == "echo" and m["line_end"]:
            out += echo(ctx, ordered, k, n)
    if kind == "oohs":
        out += oohs(ctx, where, n)
    return out


def echo(ctx: Context, ordered: list[dict], k: int, n: int) -> list[Sung]:
    """The voices answering a line: its last word again, while the singer holds it, before the next line."""
    m = ordered[k]
    word = [x for x in ordered[max(0, k - m["word_len"] + 1): k + 1] if x["word"] == m["word"]]
    nxt = ordered[k + 1]["u"] if k + 1 < len(ordered) else ctx.end
    start = m["u"] + ctx.beat
    step = ctx.sub
    if start + (len(word) + 1) * step > nxt - step + 1e-9:
        return []
    out = []
    for j, x in enumerate(word):
        u0 = start + j * step
        u1 = u0 + step if j + 1 < len(word) else nxt - step
        for v in range(n):
            p = int(x["pitch"]) if v % 2 == 0 else choir_harmony(int(x["pitch"]), x["chord"], ctx.tonic, ctx.mode, 0)
            out.append(Sung(v, u0, u1, p, 0.75 * x["vel"], x["syllable"], x["word"], x["word_len"],
                            j == len(word) - 1, x["section"], x["phrase"]))
    return out


def oohs(ctx: Context, where: set, n: int) -> list[Sung]:
    """Held chord tones on "oo" under the singer, one a chord, each voice led smoothly to its next."""
    out = []
    last: dict[int, int] = {}
    for c in ctx.chords:
        if c.section not in where:
            continue
        sung = [t.pitch for t in ctx.tune if t.sung and t.u0 < c.u1 and t.u1 > c.u0]
        if not sung:
            continue
        ceiling = min(sung) - 3
        pcs = ctx.pcs(c.symbol)
        options = [p for p in range(ceiling - 14, ceiling + 1) if p % 12 in pcs]
        for v in range(n):
            if not options:
                break
            prev = last.get(v, ceiling - 3 - 4 * (v % 3))
            p = min(options, key=lambda q: (abs(q - prev), q))
            if v % 3 and len(options) > 1:  # the voices take different tones
                taken = {s.pitch for s in out if abs(s.u0 - c.u0) < 1e-9}
                free = [q for q in options if q not in taken]
                p = min(free or options, key=lambda q: (abs(q - prev), q))
            last[v] = p
            s = ctx.sections[c.section]
            end_of_phrase = any(abs(c.u1 - p1) < 1e-9 for _p0, p1 in ctx.phrases)
            out.append(Sung(v, c.u0, c.u1 - (ctx.sub if end_of_phrase else 0.0), p, 0.55, "oo", "oo", 1, end_of_phrase,
                            s.name, ""))
    return out


def amen(ctx: Context, u0: float, n: int) -> list[Sung]:
    """The plagal amen over the coda's IV and I: "A-" on the IV, "-men" on the I, the voices moving 6 to 5,
    4 to 3, and holding the tonic."""
    if n <= 0:
        return []
    t = ctx.tonic
    lines = [(t + 9, t + 7), (t + 5, t + 4), (t, t)]
    out = []
    name = ctx.sections[-1].name
    for v in range(n):
        a, b = lines[v % 3]
        out.append(Sung(v, u0, u0 + ctx.bar - ctx.sub, a, 0.6, "a", "a-men", 2, False, name, ""))
        out.append(Sung(v, u0 + ctx.bar, u0 + 2 * ctx.bar, b, 0.6, "men", "a-men", 2, True, name, ""))
    return out


def sung_notes(sung: list[Sung], seconds, seed: int) -> list[Note]:
    """The backing voices' notes, in time, each voice a hair off the beat its own way."""
    out = []
    for s in sorted(sung, key=lambda x: (x.voice, x.u0)):
        rng = np.random.default_rng([seed & 0xFFFFFFFF, 0xBAC, s.voice, int(round(s.u0 * 1000))])
        start = max(0.0, seconds(s.u0) + float(rng.normal(0.0, 0.012)))
        end = seconds(s.u1)
        out.append(Note(part=f"choir{s.voice + 1}", start=start, dur=max(end - start, 0.05), pitch=float(s.pitch),
                        vel=float(np.clip(s.vel, 0.05, 1.0)), syllable=s.syllable, word=s.word, word_len=s.word_len,
                        line_end=s.line_end, section=s.section, phrase=s.phrase))
    return out


# --- the arrangement's options -------------------------------------------------------------------------------


def phrase_starts(ctx: Context, i: int) -> list[float]:
    s = ctx.sections[i]
    return [p0 for p0, _p1 in ctx.phrases if s.u0 - 1e-9 <= p0 < s.u1 - 1e-9]


def shape_plan(ctx: Context, style, plan: Plan, rhythm, pads, chords_first) -> None:
    """The style's arrangement options applied to the plan: which parts play where and when they come in."""
    sections = ctx.sections
    verses = [i for i, s in enumerate(sections) if s.role == "verse"]
    refrains = [i for i, s in enumerate(sections) if s.role == "refrain"]
    if style.intro == "pad" and sections and sections[0].role == "intro":
        s = sections[0]
        keep = {p: ("swell" if w in ("pad", "swell") else w) for p, w in s.parts.items() if p in pads or w in ("drone", "hold")}
        if not keep and chords_first:
            keep = {chords_first: "ring"}
        s.parts = keep
    if style.intro == "voice" and sections and sections[0].sung:  # the singer alone, the band in on the second line
        starts = phrase_starts(ctx, 0)
        if len(starts) > 1:
            for p in sections[0].parts:
                plan.entrances[(0, p)] = starts[1]
    if style.intro == "quote" and getattr(ctx, "prelude", None) and sections and sections[0].role == "intro":
        starts = phrase_starts(ctx, 0)  # after the quote, the intro's rhythm waits for its second phrase
        if len(starts) > 1:
            for p in sections[0].parts:
                if p in rhythm or p == "guitar" or family(p) in ("drums", "percussion", "bass"):
                    plan.entrances[(0, p)] = starts[1]
    if style.alone and len(verses) >= style.alone:
        i = verses[style.alone - 1]
        alone_with = style.alone_with
        if alone_with and getattr(ctx, "sdef", None) is not None:  # or whoever the style swapped in for it
            alone_with = ctx.sdef.playing(alone_with, ctx.lineup)
        with_ = alone_with if alone_with in sections[i].parts or alone_with in chords_first_all(ctx) else ""
        sections[i].parts = {with_: sections[i].parts.get(with_) or "ring"} if with_ else {}
    if style.stops and len(verses) >= style.stops:
        plan.stops.add(verses[style.stops - 1])
    if style.breakdown and len(refrains) >= 2:
        i = refrains[-1]
        starts = phrase_starts(ctx, i)
        if len(starts) >= 3:
            for p in list(sections[i].parts):
                if p not in rhythm:
                    plan.entrances[(i, p)] = starts[2]
    if style.bridge == "half":
        for i, s in enumerate(sections):
            if s.role == "bridge":
                plan.half.add(i)
    if style.entrances and verses:
        i = verses[0]
        starts = phrase_starts(ctx, i)
        # The preferred chord player may sit out this verse (the ballad's
        # guitar does). Start with a player who is actually accompanying it,
        # so the first line has harmony before the bass and fills join.
        first = chords_first if chords_first in sections[i].parts else next(
            (p for p in chords_first_all(ctx) if p in sections[i].parts), chords_first)
        order = sorted(sections[i].parts, key=lambda p: (0 if p == first else 1 if p in rhythm and
                                                        family(p) == "bass" else 2 if p in rhythm else 3, p))
        for k, p in enumerate(order):
            if k and len(starts) > 1:
                plan.entrances[(i, p)] = starts[min(k, len(starts) - 1)]


def chords_first_all(ctx: Context) -> list[str]:
    from .style import CHORDS_FIRST

    return [p for p in CHORDS_FIRST if ctx.on(p)]


LINES = ("lead", "quote", "counter", "descant", "under", "tone", "double", "hook", "fills")


def shape_events(ctx: Context, plan: Plan, events: list[Ev], rhythm, style) -> list[Ev]:
    """The options applied to what was written: late entrances, stop-time (everyone keeping time hits
    each bar's one together and leaves the words bare; a line or a fill may go on), a cold ending."""
    out = []
    for e in events:
        start = plan.entrances.get((e.section, e.part))
        if start is not None and e.u0 < start - 1e-9:
            continue
        if e.section in plan.stops and ctx.sections[e.section].parts.get(e.part, "fills") not in LINES:
            s = ctx.sections[e.section]
            at_bar = abs(((e.u0 - s.u0) % ctx.bar)) < 1e-6 and e.shift < 0.06
            if not at_bar:
                continue
            e.u1 = min(e.u1, e.u0 + ctx.beat)
        out.append(e)
    if style.ending == "cold" and ctx.chords:
        final = ctx.chords[-1].u0
        for e in out:
            if e.u0 >= final - 1e-9 and e.length <= 0:
                e.u1 = min(e.u1, e.u0 + ctx.beat)
    return out


def count_in(ctx: Context, style, lineup: list[str]) -> list[Ev]:
    """A count-in: four clicks on the beats of the bar before the first (on sticks, hands or a chop)."""
    if style.intro != "count" or not ctx.sections:
        return []
    first = ctx.sections[0].u0
    who = next((p for p in ("kit", "drummachine", "claps", "stomps", "drum") if p in lineup), None)
    beats = [first - ctx.bar + b for b in np.arange(0, ctx.bar, ctx.beat)]
    if who is not None:
        piece = {"kit": "rim", "drummachine": "rim", "claps": "clap", "stomps": "stomp", "drum": "rim"}[who]
        return [hit(who, u, piece, 0.5 + 0.05 * k, 0) for k, u in enumerate(beats) if u >= 0]
    chopper = next((p for p in lineup if family(p) in ("plucked", "keys")), None)
    if chopper is None:
        return []
    return [ev(chopper, u, u, ctx.tonic - 12 + 7 * (k % 2), 0.45, art="mute", i=0, length=0.08)
            for k, u in enumerate(beats) if u >= 0]


# --- putting it together --------------------------------------------------------------------------------------

LAG = {"bass": 0.007, "bowed": -0.012, "blown": -0.004, "reed": -0.004, "keys": 0.002, "drums": 0.0,
       "percussion": 0.0, "plucked": -0.002}
# How much steadier than the band's humanize a pattern the hands run on their own is played: a banjo's
# rolls go like clockwork (a Scruggs-style picker's onsets wander 6-8 ms, not the band's 9).
STEADY = {"roll": 0.75}


def arrange_style(genome, params, placed, lead, end, melody, seconds, sdef) -> tuple[list[Note], dict]:
    """The band's notes for a rendition in a style other than the seed's ballad, and the settings its
    instruments are built with (see band.arrange for the arguments)."""
    from .style import rebarred

    feel = params.style.feel or next(iter(sdef.feels))
    if feel in ("waltz", "six") and not rebarred(genome, params):
        feel = "straight"
    ctx = StyleContext(genome, params, placed, lead, end, melody, sdef, feel)
    sung_end = max((m["u_end"] for m in melody), default=end)
    if params.style.ending == "amen" and end > sung_end + 1e-9 and ctx.sections:
        # the coda: a bar of IV and a bar of I after the last line, in the last section's hands
        last = len(ctx.sections) - 1
        ctx.sections[last].u1 = end
        ctx.chords += [Chord(end - 2 * ctx.bar, end - ctx.bar, "IV", last, False), Chord(end - ctx.bar, end, "I", last, True)]
    ctx.capo = B.choose_capo(ctx)
    plan_style(ctx)
    B.overhear(ctx, melody, seconds, lead, end)  # for the piano score (songbird.piano), when asked
    if params.style.intro == "quote":  # the lead's quote of an older song before the song (songbird.band)
        ctx.prelude = B.prelude_span(ctx)
    rhythm = {p for p in ctx.lineup if family(p) in PERCUSSION + ("bass",)}
    pads = {p for p in ctx.lineup if family(p) in ("pad", "organ") or p in ("strings", "drone")}
    chords_first = next((p for p in chords_first_all(ctx)), None)
    shape_plan(ctx, params.style, ctx.plan, rhythm, pads, chords_first)
    for i in ctx.plan.half:
        for p, what in list(ctx.sections[i].parts.items()):
            if family(p) == "drums":
                ctx.sections[i].parts[p] = "half"
            elif family(p) == "bass" and what in ("walk", "eighths", "two"):
                ctx.sections[i].parts[p] = "roots"

    sung = backing(ctx, melody, params.style)
    if params.style.ending == "amen":
        sung += amen(ctx, end - 2 * ctx.bar, int(params.choir))
    ctx.backing = [(s.u0, s.u1, s.pitch) for s in sung]

    events: list[Ev] = []
    for i, s in enumerate(ctx.sections):
        for part, what in s.parts.items():
            writer = WRITERS.get(what)
            if writer is not None and ctx.on(part):
                events += writer(ctx, i, part)
    if params.style.backing != "echo":
        events += B.fills(ctx)
    else:  # the voices answer the lines: the players leave the ends of lines to them
        events += [e for e in B.fills(ctx) if ctx.sections[e.section].role != "refrain"]
    events += count_in(ctx, params.style, ctx.lineup)
    lead_part = next((x for x in (sdef.playing(x, ctx.lineup) for x in sdef.leads) if ctx.on(x)), None)
    if ctx.prelude is not None and lead_part:  # the style's lead alone quotes an older song before the song (songbird.band)
        events += B.prelude_part(ctx, lead_part)
    if lead_part and params.style.ending != "amen":  # ...or its opening after the last chord, as a coda
        events += B.coda_part(ctx, sung_end, lead_part)
    events = shape_events(ctx, ctx.plan, [e for e in events if ctx.on(e.part)], rhythm, params.style)

    # the singer's notes are nobody else's: a chord's note on a sung pitch goes an octave down
    for e in events:
        if e.part in rhythm or family(e.part) in ("lead",) or e.length > 0:
            continue
        what = ctx.sections[e.section].parts.get(e.part, "")
        if what in ("lead", "quote", "counter", "descant", "under", "tone", "double", "hook", "fills"):
            continue
        while int(round(e.pitch)) in ctx.voices_at(e.u0) + [p for u0, u1, p in ctx.backing if u0 - 1e-9 <= e.u0 < u1 - 1e-9]:
            e.pitch -= 12
    from .synth import instruments

    by_part: dict[str, list[Ev]] = {}
    for e in events:
        by_part.setdefault(e.part, []).append(e)
    events = []
    for part in sorted(by_part):
        mine = by_part[part]
        info = instruments.spec(part)
        events += mine if info["poly"] or info["register"] is None else B._monophonic(mine)
    # whatever sounds through the last chord holds to the end, and rings on from there (through a quote coda's bars too)
    hold = sung_end if params.style.coda == "quote" and params.style.ending != "amen" and ctx.end > sung_end + 1e-9 else ctx.end
    for e in events:
        if family(e.part) not in PERCUSSION and e.length <= 0 and e.u1 >= hold - ctx.sub - 1e-9 \
                and params.style.ending != "cold":
            e.u1 = ctx.end
    from .composition import make_room

    events = make_room(genome, params, placed, lead, events, seconds)  # a person's played parts (notes in)

    wobble = params.humanize * (1.0 + 1.5 * ctx.band.wear)
    jitters: dict[tuple[str, int], float] = {}
    notes = []
    for e in sorted(events, key=lambda e: (e.u0, e.shift, e.part, e.pitch)):
        key = (e.part, int(round(e.u0 * 1000)))
        s = ctx.sections[min(max(e.section, 0), len(ctx.sections) - 1)]
        if key not in jitters:
            rng = np.random.default_rng([ctx.seed & 0xFFFFFFFF, 0x71, B.stream_of(e.part), key[1] + (1 << 20)])
            jitters[key] = float(rng.normal(0.0, wobble * STEADY.get(s.parts.get(e.part, ""), 1.0)))
        start = max(0.0, seconds(e.u0) + e.shift + LAG.get(family(e.part), 0.0) + jitters[key])
        dur = e.length if e.length > 0 else seconds(e.u1) - start
        notes.append(Note(part=e.part, start=start, dur=max(dur, 0.03), pitch=float(e.pitch),
                          vel=float(np.clip(e.vel, 0.02, 1.0)), section=s.name, art=e.art))
    notes += sung_notes(sung, seconds, ctx.seed)
    settings = {
        "brightness": ctx.band.brightness,
        "wear": ctx.band.wear,
        "ornament": ctx.band.ornament,
        "body": ctx.band.body,
        "maker": ctx.band.maker,
        "tonic": ctx.tonic,
        "capo": ctx.capo,
        "gains": {p: ctx.band.gain(p) for p in ctx.lineup},
        "style": sdef.name,
        "feel": feel,
        "sections": [{"name": s.name, "role": s.role, "energy": round(s.energy, 3), "parts": dict(sorted(s.parts.items()))}
                     for s in ctx.sections],
    }
    return notes, settings
