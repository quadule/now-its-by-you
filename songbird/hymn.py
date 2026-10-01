"""A hymn (docs/STYLES.md, "A hymn", 2026-09-30): the style's own setting of the tune, and its parts.

The hymn is an organ (or a harmonium) under everyone singing the song's tune in parts. Two things here are its
own, and nothing else calls them for any other style:

- **the setting** (`setting`): a harmonization of the tune as a hymn sets one, a chord to a beat or a half bar,
  plain triads and their first inversions, a bass that moves by step where it can, cadences that close the
  lines, the song's own chords its backbone; scored against the sung notes so nothing grinds. It is laid in
  composition.form_phrases (beside a style's loop), so the organ, the voices' chords, the MIDI file and the page
  all read it from one place. A line whose chords or tune a person set keeps the song's (or the person's) chords;
  a line with no tune (a turn) keeps the song's.
- **the parts** (`voicing`, `parts`, `w_hymn`): over the setting, the four lines a hymn is sung and played in:
  the tune on top, the alto and the tenor under it (between the throat's floor, E3, and the tune), and the bass
  in the organ's pedal (the throat thins below E3: no voice sings it), and the organ's descant over the last
  refrain in some renditions. The singers take the tune, the alto and the tenor; the organ plays them all.
"""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

import numpy as np

from .theory import FLOOR, MODES, chord_tones, degree_semitones, parse_symbol

NAME = "hymn"
NUMERALS = ("I", "II", "III", "IV", "V", "VI", "VII")


def active(params) -> bool:
    return getattr(getattr(params, "style", None), "name", "") == NAME


# --- the setting: a harmonization of the tune ------------------------------------------------------------------

# Costs (in a sung beat's worth): how much each thing a hymn avoids weighs against the others
ON_BEAT = 3.0  # a note struck on the beat that isn't a tone of the chord (an appoggiatura: the parts would grind)
HELD = 1.5  # a note held into a beat whose chord it isn't in (a suspension, unresolved)
PASSING = 0.5  # a passing note between the beats
RUB = 1.0  # more where it is a semitone from one of the chord's tones (that tone is left out there)
NOT_SONGS = 0.6  # a chord other than the song's own at that beat (the song's chords are the backbone)
INVERSION = 0.35  # a first inversion, unless it smooths the bass
STAY = {0: 0.15, "half": 0.25}  # keeping the chord over a bar line, over the half bar (a hymn moves a half bar)
WEAK = 0.35  # a change on a weak beat
PARALLEL = 2.5  # parallel fifths or octaves between the tune and the bass
TRITONE = 2.0  # the bass leaping a tritone
# a root's motion, in scale steps up (mod 7): down a fifth (3) strong, up a step (1) and down a third (5) good,
# up a fifth (4) fine, up a third (2) weak, down a step (6) a retrogression unless out of V
MOTION = {0: 0.1, 1: 0.0, 2: 0.6, 3: -0.3, 4: 0.2, 5: 0.0, 6: 0.6}


@lru_cache(maxsize=16)
def candidates(mode: str) -> tuple[str, ...]:
    """The chords a hymn sets a tune with in this mode: its own major and minor triads on 1 to 7 (no diminished
    or augmented one), root position and first inversion."""
    out = []
    for d in range(1, 8):
        root, third, fifth = (degree_semitones(d + k, mode) for k in (0, 2, 4))
        kind = ((third - root) % 12, (fifth - root) % 12)
        if kind not in ((4, 7), (3, 7)):
            continue
        name = NUMERALS[d - 1] if kind == (4, 7) else NUMERALS[d - 1].lower()
        out += [name, f"{name}/3"]
    return tuple(out)


def _pcs(symbol: str, mode: str) -> tuple[int, int, int]:
    return tuple(t % 12 for t in chord_tones(symbol, mode)[:3])


def _bass(symbol: str, mode: str) -> int:
    tones = chord_tones(symbol, mode)
    return tones[{1: 0, 3: 1, 5: 2}.get(parse_symbol(symbol)[3], 0)] % 12


def _degree(symbol: str) -> tuple[int, int]:
    d, alter, _q, _b = parse_symbol(symbol)
    return d, alter


def _slots(notes, bars: int, meter, mode: str) -> list[list[tuple[int, float, str]]]:
    """Each beat of a line: the tune's notes sounding in it (notes: (degree, alteration, onset, length) in grid
    units, as sung), as (pitch class from the tonic, beats it sounds there, how: "on" struck on the beat, "held"
    from before, "passing" struck within it). A pickup sounds over the line before, so it is left to that line's
    last chord."""
    beat = meter.beat
    n = bars * meter.bar // beat
    out: list[list[tuple[int, float, str]]] = [[] for _ in range(n)]
    for degree, alter, a, length in notes:
        pc = degree_semitones(degree, mode, alter) % 12
        z = a + length
        for k in range(max(0, int(np.floor(a / beat + 1e-9))), min(n, int(np.ceil(z / beat - 1e-9)))):
            s0, s1 = k * beat, (k + 1) * beat
            over = (min(z, s1) - max(a, s0)) / beat
            if over <= 1e-9:
                continue
            how = "on" if abs(a - s0) < 1e-9 else "held" if a < s0 else "passing"
            out[k].append((pc, over, how))
    return out


def _fit(symbol: str, mode: str, notes) -> float:
    pcs = _pcs(symbol, mode)
    cost = 0.0
    for pc, over, how in notes:
        if pc in pcs:
            continue
        cost += {"on": ON_BEAT * over + 1.0, "held": HELD * over, "passing": PASSING * over}[how]
        if any((pc - q) % 12 in (1, 11) for q in pcs):
            cost += RUB * over
    return cost


def _move(a: str, b: str, mode: str, pos: int, beats: int) -> float:
    """What going from chord a to chord b at this beat of the bar costs."""
    if a == b:
        if pos == 0:
            return STAY[0]
        return STAY["half"] if beats % 2 == 0 and pos == beats // 2 else 0.0
    (da, xa), (db, xb) = _degree(a), _degree(b)
    step = (db - da) % 7
    cost = MOTION[step]
    if da == 5 and db in (2, 4):  # V to ii or IV: backwards
        cost += 2.0
    if 3 in (da, db):  # iii, seldom
        cost += 0.4
    if pos % 2 == 1 or (beats % 2 == 1 and pos != 0):
        cost += WEAK
    ba, bb = _bass(a, mode), _bass(b, mode)
    leap = min((bb - ba) % 12, (ba - bb) % 12)
    cost += {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.25, 4: 0.25, 5: 0.15, 6: TRITONE}[leap]
    return cost


def _top(notes) -> int | None:
    """The tune's note at the start of a beat (struck there or held into it)."""
    for pc, _over, how in notes:
        if how in ("on", "held"):
            return pc
    return None


def _parallel(ta, tb, a: str, b: str, mode: str) -> float:
    if ta is None or tb is None or ta == tb:
        return 0.0
    ba, bb = _bass(a, mode), _bass(b, mode)
    if ba == bb:
        return 0.0
    ia, ib = (ta - ba) % 12, (tb - bb) % 12
    return PARALLEL if ia == ib and ia in (0, 7) else 0.0


@lru_cache(maxsize=1024)
def harmonize(notes: tuple, chords: tuple, bars: int, meter, mode: str) -> tuple[tuple[str, ...], ...]:
    """A hymn's chords for one line of the tune, as it is sung (notes: (degree, alteration, onset, length) in grid
    units; chords: the line's own, per bar): per bar, one, two or as many as it has beats (the bar shared evenly,
    as the band lays a bar's chords), found by a dynamic programme over the beats (see the costs above). A line
    with no tune keeps its own chords."""
    slots = _slots(notes, bars, meter, mode)
    if not notes or not slots or not any(slots):
        return chords
    beats = meter.bar // meter.beat
    n = len(slots)
    own = []  # the song's own chord at each beat
    for b, bar in enumerate(chords):
        for k in range(beats):
            own.append(bar[min(len(bar) - 1, k * len(bar) // beats)])
    cands = candidates(mode)
    final = own[-1]
    last_onset = max(a for _d, _x, a, _length in notes)
    cadence = max(0, min(n - 1, int(last_onset // meter.beat)))  # from the line's last note on: its cadence chord
    tops = [_top(s) for s in slots]

    def local(k: int, c: str) -> float:
        cost = _fit(c, mode, slots[k])
        if _degree(c) != _degree(own[k]):
            cost += NOT_SONGS
        if c.endswith("/3"):
            cost += INVERSION
        if k >= cadence and (c.endswith("/3") or _degree(c) != _degree(final)):
            cost += 50.0  # the line closes on the song's own chord, in root position
        if k == 0 and _degree(own[0]) == (1, 0) and c != own[0]:
            cost += 0.5  # a line that starts on the tonic starts on it plainly
        return cost

    # the dynamic programme: best[k][c] = the cheapest way to beat k ending on c
    inf = float("inf")
    best = [{c: local(0, c) for c in cands}]
    back: list[dict] = [{}]
    for k in range(1, n):
        row, arrow = {}, {}
        pos = k % beats
        for c in cands:
            here = local(k, c)
            if here >= 50.0 and k < cadence:
                continue
            choice, cost = None, inf
            for p, prev in best[-1].items():
                x = prev + _move(p, c, mode, pos, beats) + _parallel(tops[k - 1], tops[k], p, c, mode)
                if k == cadence and c != p and _degree(c) == (1, 0):
                    x += {5: -0.5, 4: -0.3}.get(_degree(p)[0], 0.4)  # V-I, or IV-I (plagal), into the tonic
                if x < cost or (x == cost and choice is not None and p < choice):
                    choice, cost = p, x
            row[c], arrow[c] = cost + here, choice
        best.append(row)
        back.append(arrow)
    end = min(best[-1], key=lambda c: (best[-1][c], c))
    chosen = [end]
    for k in range(n - 1, 0, -1):
        chosen.append(back[k][chosen[-1]])
    chosen.reverse()
    out = []
    for b in range(bars):
        bar = chosen[b * beats:(b + 1) * beats]
        if all(c == bar[0] for c in bar):
            out.append((bar[0],))
        elif beats % 2 == 0 and all(c == bar[0] for c in bar[:beats // 2]) and all(c == bar[beats // 2] for c in bar[beats // 2:]):
            out.append((bar[0], bar[beats // 2]))
        else:
            out.append(tuple(bar))
    return tuple(out)


def setting(genome, params, lines, phrases) -> list:
    """The phrases with a hymn's own chords under every line that has a tune, set against the tune as it is sung
    there (the lineage's variants, a person's tune for the line or its place: composition.played); a line whose
    chords a person set (everywhere, or at its place) keeps theirs. The same list for every other style."""
    if not active(params) or params.mode not in MODES:
        return phrases
    from .composition import held_at, place_keys, played

    chords = params.composition.get("chords") or {}
    out = []
    for (i, j, _line), phrase in zip(lines, phrases):
        keys = place_keys(params.form, i, j) if j is not None else []
        if phrase.id not in chords and held_at(chords, keys) is None:
            notes = tuple((int(n.degree), int(n.alter), float(n.onset), float(n.dur)) for n in played(phrase, params)
                          if n.degree is not None)
            phrase = replace(phrase, chords=harmonize(notes, phrase.chords, phrase.bars, genome.meter, params.mode))
        out.append(phrase)
    return out


# --- the parts: the four lines over the setting --------------------------------------------------------------

ROLES = ("tenor", "alto", "treble")  # voice v of the group sings ROLES[v % 3]: the treble the tune with the lead
TOP = 81  # A5: the organ's descant's ceiling (played, not sung: the throat is measured to B4)
PEDAL = (36, 50)  # C2 to D3: the pedal's line, written at its 8' pitch (its 16' bourdon sounds an octave under)
ORGAN_TOP = (60, 72)  # where the organ's top line sits where nobody's tune is (a turn, a rest, the amen)
PARALLELS = 12.0  # what parallel fifths or octaves cost the parts (more than a doubled third or a unison)
VEL = {"unison": 0.76, True: 0.76, False: 0.8}  # how hard the group sings: in a unison verse, on the tune, a part
UNISON_ROLES = ("alto", "treble")  # who joins the lead on the tune in a unison verse: the tenors (the lowest) rest
DESCANT = 0.65  # how often a rendition has a descant over the last refrain (by its seed)


class Slice:
    """A stretch with one chord and one note of the tune (or none), and the lines' notes there: top (the tune, or
    the organ's own line where there is none), a (alto), t (tenor), b (the pedal), d (the descant, or None)."""

    __slots__ = ("u0", "u1", "chord", "tune", "struck", "section", "top", "a", "t", "b", "d")

    def __init__(self, u0, u1, chord, tune, struck, section):
        self.u0, self.u1, self.chord, self.tune, self.struck, self.section = u0, u1, chord, tune, struck, section
        self.top = self.a = self.t = self.b = self.d = None

    def lines(self) -> dict:
        return {"s": self.top, "a": self.a, "t": self.t, "b": self.b, **({"d": self.d} if self.d is not None else {})}


def descant(params) -> bool:
    """Whether this rendition has a descant over its last refrain: about two in three, by its seed."""
    rng = np.random.default_rng([int(params.seed) & 0xFFFFFFFF, 0xDE5C])
    return bool(rng.random() < DESCANT)


def _semitone(p: int, q: int) -> bool:
    return (p - q) % 12 in (1, 11)


def parallels(prev: dict, now: dict) -> int:
    """Parallel fifths and octaves (or unisons) between any two lines that both moved the same way, from one slice
    to the next (two lines on one note in both, a doubling, are one line)."""
    found = 0
    names = [k for k in now if now[k] is not None and prev.get(k) is not None]
    for x in range(len(names)):
        for y in range(x + 1, len(names)):
            p, q = names[x], names[y]
            if prev[p] == now[p] or prev[q] == now[q] or (prev[p] == prev[q] and now[p] == now[q]):
                continue
            a, b = (prev[p] - prev[q]) % 12, (now[p] - now[q]) % 12
            if a == b and a in (0, 7) and (now[p] - prev[p]) * (now[q] - prev[q]) > 0:
                found += 1
    return found


def _inner(s: int, basses, pcs, prev: dict) -> tuple[int, int, int]:
    """The alto and the tenor under the tune s, and the bass (one of `basses`, an octave of the chord's bass in the
    pedal's range), together, from the chord's tones (root, third, fifth): the missing tones first (the third above
    all, never doubled), held where they can be, the bass led by step where it can, never a semitone from the tune
    or each other, no parallels; in unison with the tune only where nothing fits under it."""
    root, third, fifth = pcs
    best, cost = None, float("inf")
    for b, a in ((b, a) for b in basses for a in range(FLOOR + 1, s + 1)):
        if a % 12 not in pcs or _semitone(a, s):
            continue
        tenors = [p for p in range(FLOOR, a) if p % 12 in pcs and not _semitone(p, s) and not _semitone(p, a)] or [a]
        was_b = prev.get("b")
        moved = 0.0 if was_b is None else 0.15 * abs(b - was_b) + (1.0 if abs(b - was_b) > 7 else 0.0)
        for t in tenors:
            have = [s % 12, a % 12, t % 12, b % 12]
            c = (6.0 if third not in have else 0.0) + (3.0 if root not in have else 0.0) \
                + (0.3 if fifth not in have else 0.0) + (3.0 if have.count(third) > 1 else 0.0) \
                + (4.0 if a == s else 0.0) + (5.0 if t == a else 0.0) \
                + (2.0 if s - a > 12 else 0.0) + (1.5 if a - t > 12 else 0.0)
            for name, q in (("a", a), ("t", t)):
                was = prev.get(name)
                if was is not None:
                    c += 0.5 * abs(q - was) + (2.0 if abs(q - was) > 7 else 0.0)
                else:
                    c += 0.1 * abs(q - (s - (4 if name == "a" else 9)))
            c += moved + PARALLELS * parallels(prev, {"s": s, "a": a, "t": t, "b": b})
            if c < cost:
                best, cost = (a, t, b), c
    return best if best is not None else (s, s, basses[0])


def _descant(s: int, b: int, a: int, t: int, pcs, prev: dict) -> int | None:
    """The organ's descant over the tune: a chord tone a third to an octave above it (to A5), held where it can be,
    by step, the third or fifth rather than the root, no parallels with the tune or the bass."""
    best, cost = None, float("inf")
    for d in range(s + 3, min(s + 12, TOP) + 1):
        if d % 12 not in pcs or _semitone(d, s) or _semitone(d, a) or _semitone(d, t):
            continue
        c = 0.5 if d % 12 == pcs[0] else 0.0
        was = prev.get("d")
        c += 0.6 * abs(d - was) + (2.0 if abs(d - was) > 5 else 0.0) if was is not None else 0.2 * abs(d - (s + 7))
        c += 6.0 * parallels(prev, {"s": s, "a": a, "t": t, "b": b, "d": d})
        if c < cost:
            best, cost = d, c
    return best


def voicing(ctx) -> list[Slice]:
    """The four lines over the whole rendition, and the organ's descant over the last refrain where it has one,
    slice by slice (a slice wherever the chord or the tune's note changes). Made once, kept on the context."""
    held = getattr(ctx, "_hymn", None)
    if held is not None:
        return held
    sections = ctx.sections
    out: list[Slice] = []
    ctx._hymn = out
    if not sections or not ctx.chords:
        return out
    start, end = min([sections[0].u0] + [t.u0 for t in ctx.tune]), ctx.end  # (from the first pickup)
    bounds = {start, end}
    bounds.update(c.u0 for c in ctx.chords if start < c.u0 < end)
    bounds.update(s.u0 for s in sections if start < s.u0 < end)
    bounds.update(t.u0 for t in ctx.tune if start < t.u0 < end)
    bounds.update(t.u1 for t in ctx.tune if start < t.u1 < end)
    edges = sorted(bounds)
    refrains = [i for i, s in enumerate(sections) if s.role == "refrain"]
    over = refrains[-1] if refrains and descant(ctx.params) else None
    tune = sorted(ctx.tune, key=lambda t: t.u0)
    median = int(np.median([t.pitch for t in tune])) if tune else ctx.tonic + 7
    k = 0
    prev: dict = {}
    for u0, u1 in zip(edges, edges[1:]):
        while k + 1 < len(tune) and tune[k + 1].u0 <= u0 + 1e-9:
            k += 1
        note = tune[k] if tune and tune[k].u0 - 1e-9 <= u0 < tune[k].u1 - 1e-9 else None
        chord = ctx.chord_at(u0)
        sl = Slice(u0, u1, chord, None if note is None else int(note.pitch),
                   note is not None and abs(note.u0 - u0) < 1e-9, ctx.section_at(u0))
        pcs = tuple(ctx.pcs(chord.symbol)[:3])
        bass = ctx.bass(chord.symbol)
        # the pedal: the chord's bass, held while the chord is; at a new chord, an octave of it chosen with the parts
        b = prev.get("b")
        if b is None or b % 12 != bass or out[-1].chord is not chord:
            basses = [p for p in range(PEDAL[0], PEDAL[1] + 1) if p % 12 == bass]
            if b is None:
                basses = [min(basses, key=lambda p: (abs(p - 43), p))]
        else:
            basses = [b]
        b = basses[0]
        s = sl.tune
        if s is None:  # nobody's tune here: the organ's own top line, held where the chord keeps it
            was = prev.get("s")
            if was is None or was % 12 not in pcs or not ORGAN_TOP[0] <= was <= ORGAN_TOP[1]:
                options = [p for p in range(ORGAN_TOP[0], ORGAN_TOP[1] + 1) if p % 12 in pcs]
                s = min(options, key=lambda p: (abs(p - (was if was is not None else median)), p))
            else:
                s = was
        a, t = prev.get("a"), prev.get("t")
        now = {"s": s, "a": a, "t": t, "b": b}
        keep = (len(basses) == 1 and a is not None and t is not None and a % 12 in pcs and t % 12 in pcs
                and FLOOR <= t < a < s and not _semitone(a, s) and not _semitone(t, s) and parallels(prev, now) == 0
                and pcs[1] in (s % 12, a % 12, t % 12, b % 12))
        if not keep:
            a, t, b = _inner(s, basses, pcs, prev)
        d = _descant(s, b, a, t, pcs, prev) if over is not None and sl.section == over and sl.tune is not None else None
        sl.top, sl.a, sl.t, sl.b, sl.d = s, a, t, b, d
        prev = sl.lines()
        out.append(sl)
    return out


def at(slices: list[Slice], u: float) -> Slice | None:
    """The slice sounding at u."""
    import bisect

    k = bisect.bisect_right([s.u0 for s in slices], u + 1e-9) - 1
    return slices[k] if 0 <= k < len(slices) and u < slices[k].u1 - 1e-9 else None


def _section_of(ctx, m: dict) -> int:
    """The section a sung note belongs to (a pickup sounds in the section before its own)."""
    j = ctx.section_at(m["u"])
    if ctx.sections[j].name != m["section"] and j + 1 < len(ctx.sections) and ctx.sections[j + 1].name == m["section"]:
        return j + 1
    return j


def kinds(ctx) -> dict[int, str]:
    """How the group sings each sung section: "unison" (everyone on the tune: the first verse, the third...),
    "parts" (the other verses, the refrains), "own" (the bridge and the tag: the lineage's own harmony, the
    program's voices under it)."""
    out: dict[int, str] = {}
    verses = [i for i, s in enumerate(ctx.sections) if s.role == "verse" and s.sung]
    refrains = [i for i, s in enumerate(ctx.sections) if s.role == "refrain" and s.sung]
    for n, i in enumerate(verses):
        out[i] = "unison" if n % 2 == 0 else "parts"
    for i in refrains:
        out[i] = "parts"
    for i, s in enumerate(ctx.sections):
        if s.sung and i not in out:
            out[i] = "own" if ctx.genome.section(s.name).choir else "parts"
    return out


def parts(ctx, melody: list[dict], style) -> list:
    """The group's notes (idioms.Sung): on every syllable of the tune, each voice its line's note there: the
    tenor, the alto, the treble on the tune with the lead; everyone on the tune in a unison verse; in the bridge
    and the tag the lineage's own harmony, the program's voices on the tenor under it. None where a person turned
    the backing voices off (the lead alone with the organ)."""
    from .idioms import Sung

    if not style.backing:
        return []
    lineage = int(getattr(ctx.params, "choir", 0))
    n = min(6, max(lineage, int(style.voices), int(ctx.sdef.group)))
    slices = voicing(ctx)
    how = kinds(ctx)
    ordered = sorted((m for m in melody if m["syllable"]), key=lambda m: m["u"])
    out = []
    for k, m in enumerate(ordered):
        i = _section_of(ctx, m)
        kind = how.get(i)
        sl = at(slices, m["u"])
        if kind is None or sl is None:
            continue
        u1 = min(m["u_end"], ordered[k + 1]["u"]) if k + 1 < len(ordered) else ctx.end
        tune = int(m["pitch"])
        for v in range(n):
            role = ROLES[v % 3]
            if kind == "unison":
                if role not in UNISON_ROLES:
                    continue
                pitch = tune
            elif kind == "own":
                if lineage and v < lineage:
                    continue  # the lineage sings its own harmony here (realize)
                pitch = sl.t if lineage else {"tenor": sl.t, "alto": sl.a, "treble": tune}[role]
            else:
                pitch = {"tenor": sl.t, "alto": sl.a, "treble": tune}[role]
            if pitch is None or (_semitone(pitch, tune) and pitch != tune):
                pitch = tune
            out.append(Sung(v, m["u"], u1, int(pitch), VEL[kind if kind == "unison" else pitch == tune] * m["vel"], m["syllable"],
                            m["word"], m["word_len"], bool(m["line_end"]), m["section"], m["phrase"]))
    return sorted(out, key=lambda x: (x.u0, x.voice))


# --- the organ ------------------------------------------------------------------------------------------------

# The organ's registration and swell (velocity) by what the section is: the tune given out full, unison singing
# on the diapasons, parts on the flutes, the last refrain full
REGISTRATION = {"intro": ("full", 0.82), "break": ("full", 0.82), "outro": ("full", 0.8), "turn": ("flutes", 0.6),
                "unison": ("flutes", 0.62), "parts": ("flutes", 0.62), "last": ("full", 0.76),
                "own": ("flutes", 0.58), "refrain": ("", 0.66)}


def registration(ctx, i: int) -> tuple[str, float]:
    s = ctx.sections[i]
    kind = kinds(ctx).get(i)
    refrains = [j for j, x in enumerate(ctx.sections) if x.role == "refrain"]
    if s.role == "refrain":
        return REGISTRATION["last" if refrains and i == refrains[-1] else "refrain"]
    if kind is not None:
        return REGISTRATION[kind]
    return REGISTRATION.get(s.role, REGISTRATION["turn"])


def w_hymn(ctx, i: int, part: str) -> list:
    """The organ in a hymn: the four lines in its hands and feet (the tune on top, the alto and the tenor, the bass
    in the pedal), as the group sings them, or alone where nobody sings (giving the tune out, an interlude's held
    chords), and a descant over the last refrain where the rendition has one; each line's note held while it stays
    (the tune struck again on each of its notes)."""
    from .band import Ev

    s = ctx.sections[i]
    reg, vel = registration(ctx, i)
    vel = float(np.clip(vel * (0.9 + 0.2 * s.energy), 0.05, 1.0))
    mine = [sl for sl in voicing(ctx) if s.u0 - 1e-9 <= sl.u0 < s.u1 - 1e-9]
    events: list = []
    for line in ("s", "a", "t", "b", "d"):
        held: list = []  # [u0, u1, pitch] of each note of this line
        for sl in mine:
            p = sl.lines().get(line)
            if p is None:
                continue
            if held and held[-1][2] == p and abs(held[-1][1] - sl.u0) < 1e-9 and not (line == "s" and sl.struck):
                held[-1][1] = sl.u1  # tied: the same note held on
            else:
                held.append([sl.u0, sl.u1, p])
        art = f"{reg} pedal".strip() if line == "b" else reg
        events += [Ev(part, u0, u1, float(p), vel, art, section=i) for u0, u1, p in held]
    return events
