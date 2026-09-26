"""The mix: stems in, one stereo record out, ready for mastering.

A warm, intimate acoustic folk record with the voice clear and in front.
Every stem goes through a channel strip chosen by its name (voice, choir1,
guitar, fiddle...; anything unknown gets a sensible instrument strip), then
onto one of three buses:

- the voice: cleaned below 80 Hz, a little mud and honk taken out, presence
  and air added, sibilance tamed by its balance against the rest of the
  voice, a compressor that only leans on the loudest syllables, a touch of
  warmth; it has a plate of its own and stands nearer than the band;
- the lineage choir: thinner and softer in the presence range than the
  lead, compressed as one group, wider, and further back in the room;
- the band: each instrument set to its place in the balance by loudness
  (so an instrument model that comes out louder or quieter still lands in
  the same place), carved around the voice, then compressed together
  gently; where the voice sings, the band's presence range dips a few dB,
  and comes back when it stops.

The buses share the room (room.py: this machine's RT60, tone and predelay),
each at its own distance; its return is kept out of the low end, and dips a
little while the voice sings so the words keep their edges. The sum is
glued with a slow compressor, tilted brighter or darker, and optionally worn
like an old tape. master.py then brings it to loudness under a true-peak
ceiling.

Everything a variation might turn is in MixParams, with its range.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields

import numpy as np

from . import fx, room
from .master import loudness

# --- the knobs ------------------------------------------------------------------------


@dataclass(frozen=True)
class MixParams:
    """What a rendition may vary about its mix. Every knob has a default that
    is the mix as designed, and a range (RANGES) it is held to; the harvest
    sets the room, the drift may move any of them.

    rt60      0.3-2.5 s   how long the room rings, mid band (the harvest measures it)
    tone      5 x 0-2     the room's level in five bands from 40 Hz to 16 kHz (the harvest)
    predelay  0-0.08 s    how soon the room answers after the sound
    space     0-2         how much of the room is heard: 0 dry, 1 as designed, 2 twice the sends
    width     0-1.6       stereo width of the band, choir and room: 0 mono, 1 as designed
    forward   3-15 dB     how far the voice stands above the band while it sings
                          (before the band makes way: the dip and the lead lines' step back add more)
    tilt      -3-+3 dB    the whole record darker (-) or brighter (+), turning about 1 kHz
    wear      0-1         0 new; toward 1 an old tape: wow and flutter, saturation, a narrower
                          band, hiss, and from 0.35 crackle
    balance   role: dB    an instrument role up or down against its designed place, e.g. fiddle: +2
    """

    rt60: float = 1.1
    tone: tuple[float, ...] = room.TONE
    predelay: float = 0.012
    space: float = 1.0
    width: float = 1.0
    forward: float = 10.0
    tilt: float = 0.0
    wear: float = 0.0
    balance: tuple[tuple[str, float], ...] = ()

    @classmethod
    def from_dict(cls, data: dict) -> MixParams:
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        if "tone" in values:
            values["tone"] = tuple(float(v) for v in values["tone"])
        if "balance" in values:
            pairs = values["balance"].items() if isinstance(values["balance"], dict) else values["balance"]
            values["balance"] = tuple((str(k), float(v)) for k, v in pairs)
        return cls(**{k: (float(v) if k in RANGES else v) for k, v in values.items()})

    @classmethod
    def parse(cls, items: list[str], base: MixParams | None = None) -> MixParams:
        """From FIELD=VALUE strings: rt60=2.2 wear=0.5 tone=1,1,1,0.8,0.6 balance=fiddle:2,drum:-3."""
        values = (base or cls()).to_dict()
        for item in items:
            key, _, value = item.partition("=")
            if key not in values:
                raise ValueError(f"no mix setting {key!r}; there are {', '.join(values)}")
            if key == "tone":
                values[key] = [float(v) for v in value.split(",")]
            elif key == "balance":
                values[key] = {k: float(v) for k, v in (pair.split(":") for pair in value.split(",") if pair)}
            else:
                values[key] = float(value)
        return cls.from_dict(values)

    def to_dict(self) -> dict:
        out = {f.name: getattr(self, f.name) for f in fields(self)}
        out["tone"] = list(self.tone)
        out["balance"] = dict(self.balance)
        return out

    def clamped(self) -> MixParams:
        """The same settings held inside their ranges."""
        values = {name: float(np.clip(getattr(self, name), lo, hi)) for name, (lo, hi) in RANGES.items()}
        tone = tuple(float(np.clip(v, 0.0, 2.0)) for v in self.tone)[:5]
        tone = tone + room.TONE[len(tone):]
        return MixParams(**values, tone=tone, balance=tuple((k, float(np.clip(v, -12.0, 12.0))) for k, v in self.balance))


RANGES = {
    "rt60": (0.3, 2.5),
    "predelay": (0.0, 0.08),
    "space": (0.0, 2.0),
    "width": (0.0, 1.6),
    "forward": (3.0, 15.0),
    "tilt": (-3.0, 3.0),
    "wear": (0.0, 1.0),
}

# --- channel strips ---------------------------------------------------------------------


@dataclass(frozen=True)
class Strip:
    """How one kind of instrument is treated on its way to the band bus. The
    arrangement sets each instrument's level and place (and the drift its
    balance); the strip only shapes its sound and trims it."""

    eq: tuple = ()  # equalizer bands, fx.design
    trim: float = 0.0  # dB against its level as arranged
    comp: tuple[float, float, float, float] | None = None  # dB under its loud passages, ratio, attack s, release s
    drive: float = 0.0  # warmth, fx.saturate
    send: float = 1.0  # how much reaches the room, against the band's usual
    duck: float = 0.0  # dB it steps back while the voice sings (a doubling of the tune, a lead line)


ROLES: dict[str, Strip] = {
    # A plucked lute or cittern, doubling the tune under the words: boxiness and the voice's range cleared,
    # and it steps back while the voice sings the same notes.
    "lute": Strip(eq=(("hp", 90), ("peak", 320, -2.0, 1.0), ("peak", 2800, -2.0, 0.9), ("high", 7500, -1.5)),
                  drive=0.1, duck=4.0),
    # The main accompaniment: weight kept, boom and clang tamed, sparkle above the voice.
    "guitar": Strip(eq=(("hp", 75), ("peak", 200, -2.0, 1.1), ("peak", 2600, -2.0, 0.8), ("high", 9000, 1.0)),
                    comp=(8.0, 2.0, 0.015, 0.2), drive=0.1, send=0.9),
    "harp": Strip(eq=(("hp", 70), ("peak", 2800, -1.5, 0.9)), send=1.2),
    # Round and even: mud out, no string noise, saturated so small speakers hear its pitch.
    "bass": Strip(eq=(("hp", 35, 4), ("low", 100, 2.0), ("peak", 380, -2.0, 0.8), ("lp", 3000)),
                  comp=(6.0, 3.0, 0.01, 0.15), drive=0.35, send=0.25),
    "fiddle": Strip(eq=(("hp", 180), ("peak", 2500, -2.5, 1.0), ("high", 8000, -2.0)),
                    comp=(8.0, 2.0, 0.02, 0.25), send=1.3, duck=2.0),
    "whistle": Strip(eq=(("hp", 250), ("peak", 3000, -2.0, 1.4), ("high", 9000, -2.0)), send=1.3, duck=2.0),
    "drum": Strip(eq=(("hp", 40), ("peak", 420, -2.0, 1.0), ("high", 8000, -1.5)), comp=(6.0, 3.0, 0.004, 0.12), send=0.6),
    "drone": Strip(eq=(("hp", 50), ("peak", 2500, -3.0, 0.7), ("lp", 6000))),
    "band": Strip(eq=(("hp", 60), ("peak", 2800, -1.5, 0.9))),  # anything else
}

NAMES = {
    "voice": ("voice", "lead", "vocal", "singer"),
    "choir": ("choir", "harmony", "backing"),
    "lute": ("melody", "lute", "mandolin", "bouzouki", "cittern", "oud", "banjo"),
    "guitar": ("guitar", "strum", "pick"),
    "harp": ("harp", "dulcimer", "zither", "kantele", "psaltery"),
    "bass": ("bass", "contrabass", "upright"),
    "fiddle": ("fiddle", "violin", "viola", "cello", "strings", "bow"),
    "whistle": ("whistle", "flute", "pipe", "recorder", "fife", "blown"),
    "drum": ("drum", "drums", "percussion", "bodhran", "tambourine", "shaker", "kick", "snare", "skin", "frame"),
    "drone": ("drone", "pad", "organ", "harmonium", "shruti", "bagpipe", "hum"),
}


def role_of(name: str) -> str:
    """The role a stem plays, from its name: "choir2" is choir, "guitar_low" guitar, anything unknown "band"."""
    word = re.sub(r"[\d_\-\s.]+$", "", name.lower())
    for role, names in NAMES.items():
        if word in names:
            return role
    for role, names in NAMES.items():
        if any(n in word for n in names):
            return role
    return "band"


# The voice and choir, in the same terms as the band's roles.
VOICE_EQ = (("hp", 80), ("peak", 900, -2.0, 1.2), ("peak", 3500, 1.5, 0.9), ("high", 11000, -2.0))
VOICE_COMP = (2.0, 2.0, 0.015, 0.2)  # dB under its loud syllables, ratio, attack, release: only the loudest are leaned on
CHOIR_EQ = (("hp", 120), ("low", 260, -2.0), ("peak", 3000, -2.5, 0.8), ("high", 9000, -2.0))
CHOIR_COMP = (6.0, 2.0, 0.03, 0.3)
CHOIR_UNDER = 4.0  # dB the choir as a whole sits under the lead
CHOIR_WIDTH = 1.35
CHOIR_LATER = 0.02  # s the choir's sound reaches the room after the band's: it stands further back

# Sends to the room (amplitude, before `space`), and the plate's for the voice.
VOICE_ROOM = 0.08
VOICE_PLATE = 0.13
BAND_ROOM = 0.25
CHOIR_ROOM = 0.5
CHOIR_PLATE = 0.12
PLATE_RT60 = 1.5
RETURN_EQ = (("hp", 180), ("lp", 9000))
RETURN_DIP = 5.0  # dB the room and plate give way while the voice sings

CARVE = (2600.0, 0.7)  # the band's dip for the voice: centre Hz, Q
CARVE_DEPTH = 5.0  # dB at full voice
BAND_EQ = (("low", 180, 3.0), ("high", 4500, -2.5))  # the band as a whole: warm, full, out of the words' way
BAND_COMP = (6.0, 1.8, 0.02, 0.25)
GLUE = (4.0, 1.5, 0.08, 0.6)  # the whole mix, slow enough to leave syllables alone: dB under its loud passages, ratio, attack, release
REFERENCE = -20.0  # LUFS the voice is brought to before the balance is set


# --- helpers ----------------------------------------------------------------------------


def quick_loudness(x: np.ndarray, sr: int) -> float:
    """Integrated loudness at half the sample rate (pairs averaged): within a
    few tenths of a LU of the full measurement for a stem, at half the cost."""
    n = len(x) // 2 * 2
    if n < 2 * sr:
        return loudness(x, sr)
    return loudness((x[:n:2] + x[1:n:2]) / 2.0, sr // 2)


def _compressed(x: np.ndarray, sr: int, setting, key: np.ndarray | None = None) -> np.ndarray:
    under, ratio, attack, release = setting
    threshold = fx.loud_level(x if key is None else key, sr) - under
    return fx.compress(x, sr, threshold, ratio, attack, release, key=key)[0]


def _at(x: np.ndarray, sr: int, target: float) -> np.ndarray:
    """x scaled so its loudness is `target` LUFS."""
    measured = quick_loudness(x, sr)
    return x * 10.0 ** ((target - measured) / 20.0) if np.isfinite(measured) else x


def _treated(x: np.ndarray, treat) -> np.ndarray:
    """treat(x), done once on the sound itself when the stem is one mono sound panned."""
    mono = fx.as_mono(x)
    if mono is None:
        return treat(x)
    sound, gains = mono
    return treat(sound[:, None]) * gains[None, :]


def _sum(stems: dict[str, np.ndarray], names: list[str]) -> np.ndarray | None:
    out = None
    for name in names:
        out = stems[name].copy() if out is None else out + stems[name]
    return out if out is not None and np.any(out) else None


# --- the mix --------------------------------------------------------------------------------


def mix(stems: dict[str, np.ndarray], sr: int, seed: int = 0, params: MixParams | None = None,
        taps: dict | None = None) -> np.ndarray:
    """Stems (each stereo, all one length) into one unmastered stereo mix, room
    included. taps: a dict to receive the buses and each treated stem as they
    go into the sum (for analysis)."""
    p = (params or MixParams()).clamped()
    if not stems:
        return np.zeros((0, 2))
    length = len(next(iter(stems.values())))
    balance = dict(p.balance)
    roles = {name: role_of(name) for name in sorted(stems)}

    # The lead first: everything else is placed against it.
    voice = _sum(stems, [n for n, r in roles.items() if r == "voice"])
    singing = None
    if voice is not None:
        def lead(x):
            x = fx.equalize(x, fx.design(VOICE_EQ, sr))
            x = fx.deess(x, sr)[0]
            x = _compressed(x, sr, VOICE_COMP)
            return _at(fx.saturate(x, sr, 0.2), sr, REFERENCE)
        voice = _treated(voice, lead)
        singing = fx.activity(voice, sr)

    # The lineage choir, as one group, where it sings.
    choir = _sum(stems, [n for n, r in roles.items() if r == "choir"])
    if choir is not None:
        where = fx.span(choir, sr)
        if where.stop - where.start > sr // 2:
            group = fx.equalize(choir[where], fx.design(CHOIR_EQ, sr))
            group = fx.width(_compressed(group, sr, CHOIR_COMP), sr, CHOIR_WIDTH * p.width)
            choir = np.zeros((length, 2))
            choir[where] = _at(group, sr, REFERENCE - CHOIR_UNDER + balance.get("choir", 0.0))
        else:
            choir = None

    # The band: each instrument to its place, then together.
    band = np.zeros((length, 2))
    band_send = np.zeros((length, 2))
    stepping = np.zeros((length, 2))  # what the instruments that step back under the voice give up
    for name, role in roles.items():
        if role in ("voice", "choir"):
            continue
        strip = ROLES[role]
        where = fx.span(stems[name], sr)
        if where.stop <= where.start:
            continue

        def channel(x, strip=strip):
            x = fx.equalize(x, fx.design(strip.eq, sr))
            if strip.comp:
                x = _compressed(x, sr, strip.comp)
            return fx.saturate(x, sr, strip.drive)
        x = _treated(stems[name][where], channel) * 10.0 ** ((strip.trim + balance.get(role, 0.0)) / 20.0)
        if taps is not None:
            taps[name] = (where, x)
        band[where] += x
        band_send[where] += x * strip.send
        if strip.duck and singing is not None:
            stepping[where] += x * (1.0 - 10.0 ** (-strip.duck * singing[where] / 20.0))[:, None]
    gain = 1.0
    if np.any(band):
        eq = fx.design(BAND_EQ, sr)
        band = fx.equalize(band, eq)
        under, ratio, attack, release = BAND_COMP
        band, squeeze = fx.compress(band, sr, fx.loud_level(band, sr) - under, ratio, attack, release)
        # the band under the voice, measured where the voice sings, before it makes way for it
        sung = singing is not None and np.mean(singing > 0.5) > 0.05
        level = quick_loudness(band[singing > 0.5], sr) if sung else quick_loudness(band, sr)
        if np.isfinite(level):
            gain = 10.0 ** ((REFERENCE - (p.forward if sung else 3.0) - level) / 20.0)
        if np.any(stepping):  # the lead lines step back, through the same equalizer and compressor
            band -= fx.apply_gain(fx.equalize(stepping, eq), squeeze)
        band *= gain
        band_send *= gain
        if singing is not None:
            band = fx.dynamic_dip(band, sr, CARVE[0], CARVE[1], CARVE_DEPTH * singing)
        band = fx.width(band, sr, p.width)

    # The room, heard from each bus at its own distance; the plate for the singers.
    size = (1.1 / p.rt60) ** 0.25  # a long room needs less sent to be heard as much
    send = band_send * BAND_ROOM
    plate_send = np.zeros(length)
    if voice is not None:
        send += voice * VOICE_ROOM
        plate_send += voice.sum(axis=1) * (VOICE_PLATE * np.sqrt(0.5))
    if choir is not None:
        send += fx.delay(choir, int(CHOIR_LATER * sr)) * CHOIR_ROOM
        plate_send += choir.sum(axis=1) * (CHOIR_PLATE * np.sqrt(0.5))
    early, tail = room.responses(sr, p.rt60, p.tone, p.predelay, seed)
    plates = [(plate_send * p.space, room.plate(sr, PLATE_RT60, seed))] if np.any(plate_send) else []
    wet = room.convolve(send * (p.space * size), early, tail, plates)
    wet = fx.width(fx.equalize(wet, fx.design(RETURN_EQ, sr)), sr, p.width)
    if singing is not None:
        dip = np.zeros(len(wet))
        dip[:length] = RETURN_DIP * singing
        wet *= (10.0 ** (-dip / 20.0))[:, None]

    if taps is not None:
        taps.update(voice=voice, choir=choir, band=band, wet=wet.copy(), singing=singing, band_gain=gain)
    out = wet
    for bus in (voice, choir, band):
        if bus is not None:
            out[:length] += bus

    # The whole: glued, tilted, maybe worn.
    under, ratio, attack, release = GLUE
    out, glue = fx.compress(out, sr, fx.loud_level(out, sr) - under, ratio, attack, release, knee=8.0, window=0.05)
    if taps is not None:
        taps["glue"] = glue
    if p.tilt:
        out = fx.equalize(out, fx.design((("low", 250, -p.tilt / 2), ("high", 4000, p.tilt / 2)), sr))
    if p.wear > 0:
        out = wear(out, sr, p.wear, seed)
    return out


# --- wear -------------------------------------------------------------------------------------

WOW = 0.0022  # peak speed error from wow (0.22%, about 4 cents) at full wear
FLUTTER = 0.0007  # RMS speed error from flutter at full wear
HISS = (-74.0, -46.0)  # dB of hiss under the music's loudness, from a trace of wear to full
CRACKLE = 0.35  # wear from which the surface starts to crackle


def _band_noise(rng: np.random.Generator, n: int, rate: float, lo: float, hi: float) -> np.ndarray:
    """Unit-RMS noise between lo and hi Hz, `n` points at `rate` per second."""
    x = rng.standard_normal(n)
    x = fx.equalize(x[:, None], fx.design((("hp", lo), ("lp", hi)), int(rate)))[:, 0]
    return x / (np.sqrt(np.mean(x**2)) + 1e-12)


def wear(x: np.ndarray, sr: int, amount: float, seed: int = 0) -> np.ndarray:
    """How worn the recording sounds, 0 (new) to 1 (an old copy of a copy):
    the tape transport's wow and flutter bend the pitch, the tape saturates
    and loses its top and bottom (with a little bump where the head
    resonates), hiss rises under the music, and past a third of the way the
    surface starts to crackle. Everything is made from `seed`."""
    a = float(np.clip(amount, 0.0, 1.0))
    if a <= 0 or not len(x):
        return x
    rng = np.random.default_rng(seed + 4242)
    n = len(x)
    level = quick_loudness(x, sr)

    # Transport: the speed wanders slowly (wow) and trembles (flutter); the tape is read that much early or late.
    rate = 1000.0
    k = int(n / sr * rate) + 2
    t = np.arange(k) / rate
    wow = (np.sin(2 * np.pi * rng.uniform(0.45, 0.8) * t + rng.uniform(0, 2 * np.pi))
           + 0.5 * np.sin(2 * np.pi * rng.uniform(0.15, 0.3) * t + rng.uniform(0, 2 * np.pi))) / 1.5
    speed = a * (WOW * wow + FLUTTER * _band_noise(rng, k, rate, 5.0, 14.0))
    lag = np.cumsum(speed) / rate * sr  # samples read ahead (+) or behind (-)
    y = fx.warp(x, np.interp(np.arange(n) / sr, t, lag - lag.mean()))

    # The tape itself: saturation, a narrower band, the head bump.
    y = fx.saturate(y, sr, 0.25 + 0.75 * a, bias=0.12)
    top = 20000.0 * (1.0 - 0.62 * a)
    y = fx.equalize(y, fx.design((("hp", 20.0 + 60.0 * a), ("low", 90.0, 2.0 * a), ("lp", top)), sr))

    # Hiss under everything, each channel its own, brighter than pink, through the same narrow band.
    if np.isfinite(level):
        hiss = rng.standard_normal((n, 2))
        hiss = fx.equalize(hiss, fx.design((("hp", 400.0), ("high", 6000.0, 4.0), ("lp", top)), sr))
        target = level + HISS[0] + (HISS[1] - HISS[0]) * a
        y = y + hiss * 10.0 ** ((target - quick_loudness(hiss, sr)) / 20.0)

    # Crackle: sparse clicks, each a tiny ring somewhere between 1.5 and 5 kHz, mostly toward one side or the other.
    if a > CRACKLE and np.isfinite(level):
        depth = (a - CRACKLE) / (1.0 - CRACKLE)
        count = rng.poisson(n / sr * (1.0 + 14.0 * depth))
        peak = float(np.max(np.abs(y))) * 10.0 ** ((-46.0 + 10.0 * depth) / 20.0)
        span = int(0.002 * sr)
        tt = np.arange(span) / sr
        for at, size, f, side in zip(rng.integers(0, max(1, n - span), count), rng.lognormal(0.0, 0.8, count),
                                     rng.uniform(1500.0, 5000.0, count), rng.uniform(0.15, 0.85, count)):
            click = np.exp(-tt / 0.0003) * np.sin(2 * np.pi * f * tt + np.pi / 2) * min(size, 4.0) * peak * rng.choice((-1, 1))
            y[at : at + span, 0] += click * np.sqrt(1.0 - side)
            y[at : at + span, 1] += click * np.sqrt(side)
    return y
