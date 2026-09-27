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

from dataclasses import astuple, dataclass, fields


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
    once however many takes they sang: the song's way, as far as they agree."""
    out = {}
    for pid in dict.fromkeys(p for ph in phrasings for p in ph):
        rows = [ph[pid] for ph in phrasings if pid in ph]
        out[pid] = tuple(average([r[j] for r in rows if j < len(r)]) for j in range(max(map(len, rows))))
    return out


def to_json(phrasing: Phrasing, **about) -> dict:
    """The file format: what the phrasing came from, then one row of numbers per note."""
    return {
        "fields": [f.name for f in fields(Gesture)],
        **about,
        "phrases": {pid: [list(astuple(g)) for g in gestures] for pid, gestures in phrasing.items()},
    }


def from_json(data: dict) -> Phrasing:
    names = data.get("fields", [f.name for f in fields(Gesture)])
    return {
        pid: tuple(reduce(Gesture(**dict(zip(names, row)))) for row in rows)
        for pid, rows in data["phrases"].items()
    }


def gesture(phrasing: Phrasing | None, phrase_id: str, index: int) -> Gesture | None:
    if not phrasing or phrase_id not in phrasing or index >= len(phrasing[phrase_id]):
        return None
    return phrasing[phrase_id][index]


def inherited(source: dict, record: dict | None = None) -> tuple[dict | None, list[dict]]:
    """The small performance a rendition carries, or the seed's for older
    records. Only rounded gestures travel; recordings and local paths do not."""
    if record is not None and "performance" in record:
        performance = record["performance"]
        return performance.get("lead"), list(performance.get("choir") or [])
    return source.get("seed_phrasing"), []
