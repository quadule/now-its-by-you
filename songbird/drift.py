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

The field is read three ways, each spanning about -1..1 (standard deviation
about 0.45, clipped at 1):

    full  all three octaves, for what may move a little every day (tempo,
          feel, the singer's day)
    slow  the month and year octaves, for choices that should hold for weeks
          (the form, the accompaniment, the lyric's leanings); a quantized
          choice on it changes three to six times a year
    year  the year octave alone, for the most salient choices (key, mode),
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
    "year": (0.0, 0.0, 0.62),
}

# Every dimension of the field and what reads it (see variation.KNOBS and
# DECISIONS). The last four are for the instruments and the mix.
DIMENSIONS = {
    "key": "tonic offset (year)",
    "mode": "which member of the voice's mode family (year)",
    "tempo": "tempo within the voice's range",
    "verses": "how many verses (slow)",
    "intro": "whether the intro plays (slow)",
    "turns": "whether the strings take a turn after a refrain (slow)",
    "break": "whether an instrumental break comes before the bridge (slow)",
    "tag": "whether everyone sings the tag (slow)",
    "outro": "whether the outro plays (slow)",
    "extra": "whether a long form sings the bridge's extra stanza (slow)",
    "texture": "how busy the accompaniment pattern is (slow)",
    "feel": "humanize, ritardando and swing: how loose the playing is",
    "voice": "the singer's day: breath, vibrato depth, dynamics, glottal shape",
    "mood": "the lyric's mood, lighter or heavier (slow)",
    "era": "the lyric's era, older or newer verses (slow)",
    "rarity": "the lyric's appetite for rare verses (slow)",
    "ensemble": "which instruments play (for the instruments)",
    "balance": "the instruments' balance (for the instruments)",
    "sheen": "the instruments' brightness and tilt (for the instruments and the mix)",
    "space": "the mix's width and distance (for the mix)",
}

DAY = 86400.0
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Drift:
    """The field at one instant: every dimension, read each way."""

    t: float  # days since the epoch
    full: dict  # dimension -> value, all three octaves
    slow: dict  # the month and year octaves
    year: dict  # the year octave

    def view(self, name: str) -> dict:
        return {"full": self.full, "slow": self.slow, "year": self.year}[name]

    def to_dict(self) -> dict:
        out = {"t": round(self.t, 6), "at": when(self.t).isoformat()}
        for name in VIEWS:
            out[name] = {k: round(v, 4) for k, v in self.view(name).items()}
        return out

    @classmethod
    def from_dict(cls, data: dict) -> Drift:
        return cls(t=float(data["t"]), **{name: dict(data.get(name, {})) for name in VIEWS})


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


def _lattice(seed: int, i: np.ndarray, salt: int) -> np.ndarray:
    """A value in [-1, 1) for each lattice point i, fixed by the seed."""
    h = _mix(_mix(i.astype(np.int64).view(np.uint64)) ^ np.uint64((seed + salt) % 2**64))
    return (h >> np.uint64(11)).astype(np.float64) * (2.0 / 2**53) - 1.0


def noise(x, seed: int) -> np.ndarray:
    """One-dimensional gradient noise. Each lattice point carries a random value
    and a random slope, and cubic Hermite pieces join them, so the curve and its
    slope are continuous everywhere and it never pins to zero at the lattice
    (as plain gradient noise does). Values stay within about -1.2..1.2."""
    x = np.atleast_1d(np.asarray(x, dtype=np.float64))
    i = np.floor(x)
    f = x - i
    i = i.astype(np.int64)
    v0, v1 = _lattice(seed, i, 0), _lattice(seed, i + 1, 0)
    m0, m1 = _lattice(seed, i, _SLOPE), _lattice(seed, i + 1, _SLOPE)
    f2 = f * f
    f3 = f2 * f
    return (2 * f3 - 3 * f2 + 1) * v0 + (f3 - 2 * f2 + f) * m0 + (3 * f2 - 2 * f3) * v1 + (f3 - f2) * m1


def octaves(t, voice_hash: str, dimension: str) -> np.ndarray:
    """The three octaves of one dimension at times t, unweighted (each SCALE x N),
    shape (3, len(t))."""
    t = np.atleast_1d(np.asarray(t, dtype=np.float64))
    out = []
    for k, period in enumerate(PERIODS):
        seed = _seed("drift", voice_hash, dimension, k)
        phase = (seed >> 11) / 2.0**53  # where the lattice falls, so it never sits on midnight
        out.append(SCALE * noise(t / period + phase, seed))
    return np.array(out)


def series(t, voice_hash: str, dimensions=None) -> dict[str, dict[str, np.ndarray]]:
    """The field over many times at once: dimension -> view -> array."""
    out = {}
    for name in dimensions or DIMENSIONS:
        o = octaves(t, voice_hash, name)
        out[name] = {view: np.clip(np.tensordot(weights, o, axes=1), -1.0, 1.0) for view, weights in VIEWS.items()}
    return out


def drift(t_days: float, voice_hash: str) -> Drift:
    """The drift vector for one machine (its voice hash) at one instant."""
    values = series([t_days], voice_hash)
    return Drift(t=float(t_days), **{view: {k: float(v[view][0]) for k, v in values.items()} for view in VIEWS})


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
