"""Drift: time as a smooth noise field seeded by the voice (milestone 4).

    drift(t_days: float, voice_hash: str) -> Drift

A machine's song changes a little day to day, more month to month and most
year to year, and never at a calendar edge. The render time is a continuous
t in days since the Unix epoch, and every named dimension of the field sums
three octaves of one-dimensional gradient noise:

    d(t) = 0.15 N1(t / 0.9973) + 0.35 N2(t / 29.3) + 0.5 N3(t / 371.6)

Each N is its own noise function, seeded from the voice hash, the
dimension's name and the octave, so two machines drift along different paths
on the same day and adding a dimension never moves the others. The periods
sit slightly off the day, the month and the year, so the field neither lines
up with the calendar nor repeats.

The field is read four ways, each spanning about -1..1 (standard deviation
about 0.4 to 0.45, clipped at 1):

    full    all three octaves, for what may move a little every day (tempo,
            feel, the singer's day)
    slow    the month and year octaves, for choices that should hold for
            weeks (the accompaniment, the lyric's leanings); a quantized
            choice on it changes three to six times a year
    season  mostly the year, a little of the month, for the form: with its
            nine or so choices it changes about ten times a year, so forms a
            month apart differ about half the time and a year apart mostly
    year    the year octave alone, for the most salient choices (key, mode),
            which change about once a year and never flicker

A stateless field can't hold a choice with hysteresis, so the smoothness of
the view a choice reads is what keeps it from flickering across a threshold.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timezone

import numpy as np

PERIODS = (0.9973, 29.3, 371.6)  # days: a day, a month and a year, each a little off the calendar
SCALE = 1.45  # stretches the noise so each view spans about -1..1
# Each view's weight on the day, month and year octaves. `full` is the plan's
# 0.15 / 0.35 / 0.5, the knob for how audible drift is; tune by ear.
VIEWS = {
    "full": (0.15, 0.35, 0.5),
    "slow": (0.0, 0.35, 0.5),
    "season": (0.0, 0.15, 0.6),
    "year": (0.0, 0.0, 0.62),
}

# Every dimension of the field and what reads it (see variation.KNOBS and
# DECISIONS). "held" choices change with hysteresis: see variation.held.
DIMENSIONS = {
    "key": "tonic offset (year)",
    "mode": "which member of the voice's mode family (year)",
    "tempo": "tempo within the voice's range",
    "verses": "how many verses (season)",
    "pairs": "whether added verses come two to a refrain (season)",
    "intro": "whether the intro plays (season)",
    "turn": "whether the strings take a turn after the refrains (season)",
    "break": "whether an instrumental break comes before the bridge (season)",
    "tag": "whether everyone sings the tag (season)",
    "outro": "whether the outro plays (season)",
    "other": "whether any other optional section plays (season)",
    "extra": "whether a long form sings the bridge's extra stanza (season)",
    "texture": "how busy the accompaniment pattern is (slow)",
    "feel": "humanize, ritardando and swing: how loose the playing is",
    "voice": "the singer's day: breath, vibrato depth, dynamics, glottal shape",
    "mood": "the lyric's mood, lighter or heavier (slow)",
    "era": "the lyric's era, older or newer verses (slow)",
    "rarity": "the lyric's appetite for rare verses (slow)",
    "ensemble": "the band leaning on its plucked strings or its bowed and blown ones (slow)",
    "balance": "the band's balance, each machine's instruments moving their own ways (slow)",
    "sheen": "the instruments' brightness, the record's tilt, and (slowly) its width",
    "pattern": "the band's accompaniment family: air, pick, lilt, strum (slow, held)",
    "lead": "who states the tune where nobody sings: whistle, fiddle, lute (year, held)",
    "arc": "how strongly the band builds through the song (slow)",
    "space": "how much of the room is heard (slow)",
    "near": "how close the singer stands: the voice's own reverb (slow)",
    "duck": "how much the band and the room make way for the voice (slow)",
    "tune": "how freely the singer takes the tune this season: how often it learns or forgets a variant (slow)",
    "words": "how restless the words are this season: how often one is swapped (slow)",
}

DAY = 86400.0
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Drift:
    """The field at one instant: every dimension, read each way."""

    t: float  # days since the epoch
    full: dict  # dimension -> value, all three octaves
    slow: dict  # the month and year octaves
    season: dict  # mostly the year, a little of the month
    year: dict  # the year octave
    hash: str = ""  # the voice hash that seeded it, so its past can be read (held choices look back)

    def view(self, name: str) -> dict:
        return getattr(self, name)

    def to_dict(self) -> dict:
        out = {"t": round(self.t, 6), "at": when(self.t).isoformat(), "hash": self.hash}
        for name in VIEWS:
            out[name] = {k: round(v, 4) for k, v in self.view(name).items()}
        return out

    @classmethod
    def from_dict(cls, data: dict) -> Drift:
        return cls(t=float(data["t"]), **{name: dict(data.get(name, {})) for name in VIEWS},
                   hash=str(data.get("hash", "")))


def _seed(*parts) -> int:
    """A 64-bit seed from any parts, the same on every platform and run."""
    return int.from_bytes(hashlib.sha256("\x1f".join(map(str, parts)).encode()).digest()[:8], "little")


_GOLDEN = np.uint64(0x9E3779B97F4A7C15)
_M1 = np.uint64(0xBF58476D1CE4E5B9)
_M2 = np.uint64(0x94D049BB133111EB)
_SLOPE = 0x632BE59BD9B4E019  # salts the slopes apart from the values


def _mix(x: np.ndarray) -> np.ndarray:
    """SplitMix64's finalizer, elementwise on uint64 arrays (wrapping arithmetic)."""
    x = x + _GOLDEN
    x = (x ^ (x >> np.uint64(30))) * _M1
    x = (x ^ (x >> np.uint64(27))) * _M2
    return x ^ (x >> np.uint64(31))


def _lattice(seed, i: np.ndarray, salt: int) -> np.ndarray:
    """A value in [-1, 1) for each lattice point i, fixed by the seed (one, or one per point)."""
    seed = np.asarray(seed, dtype=np.uint64) + np.uint64(salt)
    h = _mix(_mix(i.astype(np.int64).view(np.uint64)) ^ seed)
    return (h >> np.uint64(11)).astype(np.float64) * (2.0 / 2**53) - 1.0


def noise(x, seed) -> np.ndarray:
    """One-dimensional gradient noise. Each lattice point carries a random value
    and a random slope, and cubic Hermite pieces join them, so the curve and its
    slope are continuous everywhere and it never pins to zero at the lattice
    (as plain gradient noise does). Values stay within about -1.2..1.2. The
    seed may be an array broadcasting with x: many noise functions at once."""
    x = np.atleast_1d(np.asarray(x, dtype=np.float64))
    i = np.floor(x)
    f = x - i
    i = i.astype(np.int64)
    v0, v1 = _lattice(seed, i, 0), _lattice(seed, i + 1, 0)
    m0, m1 = _lattice(seed, i, _SLOPE), _lattice(seed, i + 1, _SLOPE)
    f2 = f * f
    f3 = f2 * f
    return (2 * f3 - 3 * f2 + 1) * v0 + (f3 - 2 * f2 + f) * m0 + (3 * f2 - 2 * f3) * v1 + (f3 - f2) * m1


def _seeds(voice_hash: str, dimensions: tuple) -> tuple[np.ndarray, np.ndarray]:
    """Each (dimension, octave)'s seed and lattice phase, so the lattice never sits on midnight."""
    seeds = np.array([[_seed("drift", voice_hash, name, k) for k in range(len(PERIODS))] for name in dimensions],
                     dtype=np.uint64)
    return seeds, (seeds >> np.uint64(11)).astype(np.float64) / 2.0**53


def octaves(t, voice_hash: str, dimensions) -> np.ndarray:
    """The three octaves of each dimension at times t, unweighted (each SCALE x N),
    shape (dimensions, 3, len(t))."""
    t = np.atleast_1d(np.asarray(t, dtype=np.float64))
    seeds, phases = _seeds(voice_hash, tuple(dimensions))
    x = t[None, None, :] / np.asarray(PERIODS)[None, :, None] + phases[:, :, None]
    return SCALE * noise(x, seeds[:, :, None])


def series(t, voice_hash: str, dimensions=None) -> dict[str, dict[str, np.ndarray]]:
    """The field over many times at once: dimension -> view -> array."""
    names = tuple(dimensions or DIMENSIONS)
    o = octaves(t, voice_hash, names)
    views = {view: np.clip(np.einsum("k,dkt->dt", np.asarray(w), o), -1.0, 1.0) for view, w in VIEWS.items()}
    return {name: {view: values[d] for view, values in views.items()} for d, name in enumerate(names)}


def epoch(t_days: float, voice_hash: str, name: str, lo: float, hi: float) -> tuple[int, float]:
    """Which stretch of a named clock the moment t falls in, and the day that stretch began.

    A choice made from a set (which variants a singer adds, which verse comes in) can't ride a smooth field
    the way a number or an ordered category (held()) can, so it rides a clock instead. Each machine's clock
    of each name runs in stretches of one length of its own between lo and hi days, from a phase of its
    own; anything chosen from (machine, name, stretch) holds through the stretch and changes only as the
    next begins. So it never flickers from one day to the next, no two clocks turn together, and none
    turns on a calendar edge. Rates can still follow the drift: read it at the stretch's start.

    The stretches sit on a grid of the clock's own period with each boundary nudged by up to a quarter of
    it, so no two stretches need be alike and a clock never repeats itself."""
    u = _seed("epoch", voice_hash, name)
    period = lo + (hi - lo) * ((u & 0xFFFFFFFF) / 2.0**32)
    phase = period * ((u >> 32) / 2.0**32)

    def boundary(k: int) -> float:
        return phase + k * period + 0.25 * period * (2.0 * chance("boundary", voice_hash, name, k) - 1.0)

    t = float(t_days)
    k = int(np.floor((t - phase) / period)) - 1
    while boundary(k + 1) <= t:
        k += 1
    while boundary(k) > t:
        k -= 1
    return k, boundary(k)


def chance(*parts) -> float:
    """A number in [0, 1) fixed by its parts: a coin tossed once for good."""
    return _seed("chance", *parts) / 2.0**64


def drift(t_days: float, voice_hash: str) -> Drift:
    """The drift vector for one machine (its voice hash) at one instant."""
    values = series([t_days], voice_hash)
    return Drift(t=float(t_days), **{view: {k: float(v[view][0]) for k, v in values.items()} for view in VIEWS},
                 hash=voice_hash)


def days(moment: datetime) -> float:
    """Days since the epoch; a naive datetime is taken as UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (moment - _EPOCH).total_seconds() / DAY


def when(t_days: float) -> datetime:
    """The instant t days after the epoch, to the second, in UTC."""
    return datetime.fromtimestamp(round(t_days * DAY), tz=timezone.utc)


def parse(text: str) -> float:
    """t for a --date: YYYY-MM-DD (noon UTC that day), a full ISO timestamp
    (naive is UTC), or 'now' (the clock, to the second)."""
    if text == "now":
        return now()
    if len(text) == 10:
        d = date.fromisoformat(text)
        return days(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc))
    return days(datetime.fromisoformat(text.replace("Z", "+00:00")))


def now() -> float:
    """The render instant, to the whole second, so a record can replay it."""
    return round(datetime.now(timezone.utc).timestamp()) / DAY
