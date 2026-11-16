"""Phrasing: how a person sang or said the song, reduced to a few numbers a note.

The voice stays the machine's; the phrasing is a person's. A performance is
analysed once (tools/phrasing.py) into one gesture for every note of the tune,
keyed by the phrase the note belongs to and its place in that phrase, so a
gesture carries over to verses the LLM writes new words for. A gesture is a
handful of rounded numbers (when the syllable lands against the beat, how long
it is held, how loud it is and whether it swells or fades, the pitch's way
into, through and out of the note, and where the note sits against its
written pitch): nothing a voice could be rebuilt from.
"""

from __future__ import annotations

import re
from dataclasses import astuple, dataclass, fields, replace


@dataclass(frozen=True)
class Gesture:
    early: float = 0.0  # beats the syllable lands ahead of the grid; negative lags behind
    hold: float = 1.0  # fraction of the written length sung before letting go
    level: float = 0.0  # dB louder than the singer would sing the note unprompted
    swell: float = 0.0  # dB the note grows from its start to its end; negative fades
    scoop: float = 0.0  # cents the voice comes into the note from; negative is from below
    bend: float = 0.0  # cents the held note has drifted by the time it lets go
    fall: float = 0.0  # cents it falls (negative) or lifts as it lets go
    vibrato: float = -1.0  # cents of vibrato on the note; -1 leaves it to the singer
    tune: float = 0.0  # cents the held note sits off its written pitch (sharp +), against the singer's own tuning


# Every gesture is rounded to these steps and kept inside these bounds, so a
# phrasing file holds tendencies, not a recording's fine detail.
STEP = Gesture(early=1 / 48, hold=0.05, level=0.5, swell=0.5, scoop=5.0, bend=5.0, fall=5.0, vibrato=1.0, tune=2.0)
LOW = Gesture(early=-0.25, hold=0.6, level=-8.0, swell=-6.0, scoop=-150.0, bend=-80.0, fall=-150.0, vibrato=-1.0, tune=-50.0)
HIGH = Gesture(early=0.25, hold=1.0, level=8.0, swell=6.0, scoop=150.0, bend=80.0, fall=150.0, vibrato=60.0, tune=50.0)

Phrasing = dict[str, tuple[Gesture, ...]]  # phrase id -> one gesture per sung note of that phrase


def reduce(g: Gesture) -> Gesture:
    """Clip a gesture to its bounds and round it to its steps; a field that
    was never measured (NaN) takes its default."""
    values = []
    for f, lo, hi, step in zip(fields(Gesture), astuple(LOW), astuple(HIGH), astuple(STEP)):
        v = getattr(g, f.name)
        v = f.default if v != v else min(max(v, lo), hi)
        values.append(round(round(v / step) * step, 4))
    return Gesture(*values)


def average(gestures: list[Gesture]) -> Gesture:
    """One gesture from several sightings of the same note (a verse tune sung to
    different words, say), field by field over the sightings that measured it;
    'leave it to the singer' wins a tie on vibrato."""
    mean = []
    for f in fields(Gesture):
        seen = [getattr(g, f.name) for g in gestures if getattr(g, f.name) == getattr(g, f.name)]
        mean.append(sum(seen) / len(seen) if seen else float("nan"))
    judged = [g.vibrato for g in gestures if g.vibrato == g.vibrato]
    own = [v for v in judged if v >= 0]
    mean[[f.name for f in fields(Gesture)].index("vibrato")] = sum(own) / len(own) if len(own) * 2 > len(judged) else -1.0
    return reduce(Gesture(*mean))


def blend(phrasings: list[Phrasing]) -> Phrasing:
    """Several people's phrasings as one, note by note, each person counting
    once however many takes they sang: the song's way, as far as they agree.
    Only the tune's lines blend: a line one person wrote, and one person's
    habits, are theirs, so everyone's way is a plain phrasing."""
    out = {}
    for pid in dict.fromkeys(p for ph in phrasings for p in ph):
        rows = [ph[pid] for ph in phrasings if pid in ph]
        out[pid] = tuple(average([r[j] for r in rows if j < len(r)]) for j in range(max(map(len, rows))))
    return out


def to_json(phrasing: Phrasing, **about) -> dict:
    """The file format: what the phrasing came from, then one row of numbers per note (and its lines and habits,
    if it has them)."""
    out = {
        "fields": [f.name for f in fields(Gesture)],
        **about,
        "phrases": {pid: [list(astuple(g)) for g in gestures] for pid, gestures in phrasing.items()},
    }
    lines, habits = getattr(phrasing, "lines", None), getattr(phrasing, "habits", None)
    if lines:
        out["lines"] = {key: {"notes": [list(s) for s in ln.shapes],
                              "gestures": [None if g is None else list(astuple(g)) for g in ln.gestures]}
                        for key, ln in lines.items()}
    if habits:
        out["habits"] = {key: list(astuple(g)) for key, g in habits.items()}
    return out


def from_json(data: dict) -> Phrasing:
    """A phrasing from its file: a plain dict of phrases, or a Way where the file has lines or habits. Every
    gesture is rounded and bounded on the way in; lines and habits are checked (checked_extras)."""
    names = data.get("fields", [f.name for f in fields(Gesture)])
    phrases = {
        pid: tuple(reduce(Gesture(**dict(zip(names, row)))) for row in rows)
        for pid, rows in data["phrases"].items()
    }
    if not data.get("lines") and not data.get("habits"):
        return phrases
    lines, habits = checked_extras(data, names)
    return Way(phrases, lines, habits)


def _number(x, lo: float, hi: float) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not lo <= x <= hi:
        raise ValueError("a number out of its bounds")
    return float(x)


def checked_extras(data: dict, names: list[str]) -> tuple[dict[str, Line], dict[str, Gesture]]:
    """A file's lines and habits, held to their shape and bounds: at most MAX_LINES lines of 1 to MAX_LINE_NOTES
    notes under line keys, each note's shape on the song's scale (onset -8 to 128 beats, length up to 32, pitch -48
    to 48 semitones) and its gesture a row or null; habits only under HABITS' keys. Raises ValueError."""
    lines_in, habits_in = data.get("lines") or {}, data.get("habits") or {}
    if not isinstance(lines_in, dict) or not isinstance(habits_in, dict) or len(lines_in) > MAX_LINES:
        raise ValueError("a phrasing's lines or habits aren't ones this program reads")
    lines = {}
    for key, ln in lines_in.items():
        if not isinstance(key, str) or not LINE_KEY.fullmatch(key) or not isinstance(ln, dict):
            raise ValueError("a phrasing's line isn't one this program reads")
        notes, rows = ln.get("notes"), ln.get("gestures")
        if not isinstance(notes, list) or not isinstance(rows, list) or not 1 <= len(notes) <= MAX_LINE_NOTES \
                or len(rows) != len(notes):
            raise ValueError("a phrasing's line isn't one this program reads")
        shapes = []
        for n in notes:
            if not isinstance(n, list) or len(n) != 3 or isinstance(n[2], bool) or not isinstance(n[2], int):
                raise ValueError("a phrasing's line isn't one this program reads")
            shapes.append(shape(_number(n[0], -8, 128), _number(n[1], 0, 32), int(_number(n[2], -48, 48))))
        gestures = []
        for row in rows:
            if row is not None and (not isinstance(row, list) or len(row) > len(names)):
                raise ValueError("a phrasing's line isn't one this program reads")
            gestures.append(None if row is None else
                            reduce(Gesture(**dict(zip(names, (_number(x, -1e6, 1e6) for x in row))))))
        lines[key] = Line(tuple(shapes), tuple(gestures))
    habits = {}
    for key, row in habits_in.items():
        if key not in HABITS or not isinstance(row, list) or len(row) > len(names):
            raise ValueError("a phrasing's habits aren't ones this program reads")
        habits[key] = reduce(Gesture(**dict(zip(names, (_number(x, -1e6, 1e6) for x in row)))))
    return lines, habits


def inherited(source: dict, record: dict | None = None) -> tuple[dict | None, list[dict]]:
    """The small performance a rendition carries (only rounded gestures travel; recordings and local paths do
    not), or the seed's for a record that names none. An explicit empty performance is meaningful:
    that version chose to sing without contributions, so it must not silently pick the seed's phrasing up."""
    performance = (record or {}).get("performance")
    if isinstance(performance, dict):
        return performance.get("lead"), list(performance.get("choir") or [])
    return source.get("seed_phrasing"), []


def gesture(phrasing: Phrasing | None, phrase_id: str, index: int) -> Gesture | None:
    if not phrasing or phrase_id not in phrasing or index >= len(phrasing[phrase_id]):
        return None
    return phrasing[phrase_id][index]


# ---------------------------------------------------------------- after rewriting
#
# docs/notes/SINGING-AFTER-REWRITING.md. A phrasing may also carry, beside its phrases:
#
#   lines   the gestures of lines a person wrote (a line of its own, a blank clip's line), by the key its words and
#           notes are kept under (verse:wire.2, verse112:0.0), with each note's shape as it was sung: its onset and
#           length in beats and its pitch in semitones above the tonic
#   habits  how this singer sings notes alike (by place in the line, length and the step into it), for any sung
#           note no gesture was measured for
#
# A phrasing without them is a plain dict and sings exactly as it always has.

SHAPE_STEP = 1 / 48  # beats: a note's onset and length are kept to this
MAX_LINES = 64
MAX_LINE_NOTES = 32  # composition.OWN_MAX
LINE_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}:[A-Za-z0-9_-]{1,32}\.\d{1,2}")
POSITIONS = ("first", "inside", "last")
LENGTHS = ("short", "medium", "long")  # under 3/4 of a beat; under a beat and a half; longer
INTO = ("step", "up", "down")  # within two semitones of the note before; a leap up; a leap down
# every key a habit may have: a line's first note by its length; any other by its length and the step into it; and
# "*", the singer's way with any note, for a note whose own kind wasn't heard enough
HABITS = ("*", *(f"first.{n}" for n in LENGTHS),
          *(f"{p}.{n}.{i}" for p in POSITIONS[1:] for n in LENGTHS for i in INTO))

Shape = tuple[float, float, int]  # onset and length in beats, semitones above the tonic


@dataclass(frozen=True)
class Line:
    shapes: tuple[Shape, ...]  # each note as it was sung
    gestures: tuple[Gesture | None, ...]  # each note's gesture; None where the take didn't sing it


class Way(dict):
    """A phrasing that carries lines and habits beside its phrases (a dict of phrases, as Phrasing is)."""

    def __init__(self, phrases=(), lines: dict[str, Line] | None = None, habits: dict[str, Gesture] | None = None):
        super().__init__(phrases)
        self.lines = dict(lines or {})
        self.habits = dict(habits or {})


def shape(onset_beats: float, length_beats: float, semitones: int) -> Shape:
    """A note's shape as a line keeps it: onset and length to SHAPE_STEP, the pitch in whole semitones."""
    return (round(round(onset_beats / SHAPE_STEP) * SHAPE_STEP, 4), round(round(length_beats / SHAPE_STEP) * SHAPE_STEP, 4),
            int(round(semitones)))


def kind(shapes: list[Shape], k: int) -> str:
    """Which habit note k of a line of these shapes takes (HABITS)."""
    beats = shapes[k][1]
    length = "short" if beats < 0.75 else "medium" if beats < 1.5 else "long"
    if k == 0:
        return f"first.{length}"
    into = shapes[k][2] - shapes[k - 1][2]
    return f"{'last' if k == len(shapes) - 1 else 'inside'}.{length}.{'up' if into >= 3 else 'down' if into <= -3 else 'step'}"


def line_gesture(phrasing, key: str, k: int, shapes: list[Shape]) -> tuple[Gesture | None, str | None]:
    """Note k of a line a person wrote, sung now with these shapes: its gesture from the take, and how it was
    found ("sung": the line is as it was sung; "matched": the line was changed since, and a note sung then at the
    same onset for the same length is this one; its tuning goes if its pitch moved), else (None, None)."""
    line = (getattr(phrasing, "lines", None) or {}).get(key)
    if line is None:
        return None, None
    if tuple(shapes) == line.shapes:
        return (line.gestures[k], "sung") if line.gestures[k] is not None else (None, None)
    onset, length, pitch = shapes[k]
    for was, g in zip(line.shapes, line.gestures):
        if g is not None and was[0] == onset and was[1] == length:
            return (g if was[2] == pitch else replace(g, tune=0.0)), "matched"
    return None, None


def habit(phrasing, shapes: list[Shape], k: int) -> Gesture | None:
    """The singer's habit for note k of a line of these shapes: their way with notes of its kind, else with any
    note; None for a phrasing without habits."""
    habits = getattr(phrasing, "habits", None)
    if not habits:
        return None
    return habits.get(kind(shapes, k), habits.get("*"))


def sung_gesture(phrasing, phrase_id: str, own: str | None, k: int, shapes: list[Shape]) -> tuple[Gesture | None, str]:
    """A sung note's gesture and where it came from: a tune line's note by its place ("sung", as ever); a line a
    person wrote by its key (line_gesture: "sung" or "matched"); else the singer's habit ("habit"); else none
    ("none": the singer's own timing). A line of its own takes nothing from a plain phrasing."""
    if own:
        g, how = line_gesture(phrasing, own, k, shapes)
    else:
        g = gesture(phrasing, phrase_id, k)
        how = "sung"
    if g is None:
        g = habit(phrasing, shapes, k)
        how = "habit" if g is not None else "none"
    return g, how


def without_habits(phrasing):
    """The same way with its habits left out: a note nobody sang takes the singer's own timing."""
    if not getattr(phrasing, "habits", None):
        return phrasing
    return Way(phrasing, phrasing.lines) if phrasing.lines else dict(phrasing)


def mapped(phrasing, one):
    """Every gesture of a phrasing passed through one(gesture), its lines and habits too."""
    phrases = {pid: tuple(one(g) for g in row) for pid, row in phrasing.items()}
    lines, habits = getattr(phrasing, "lines", None), getattr(phrasing, "habits", None)
    if not lines and not habits:
        return phrases
    return Way(phrases, {key: Line(ln.shapes, tuple(None if g is None else one(g) for g in ln.gestures))
                         for key, ln in (lines or {}).items()},
               {key: one(g) for key, g in (habits or {}).items()})

