"""The mix: stems in, one stereo record out, ready for mastering.

A warm, intimate acoustic folk record with the voice clear and in front.
Every stem goes through a channel strip chosen by its name (voice, choir1,
guitar, fiddle...; anything unknown gets a plain instrument strip), then onto
one of three buses:

- the voice: cleaned below 80 Hz, a little honk and synthetic sizzle taken
  out, a little presence added, sibilance tamed by its balance against the
  rest of the voice, a compressor that only leans on the loudest syllables,
  a touch of warmth; it has a plate of its own and stands nearer than the band;
- the lineage choir: thinner and softer in the presence range than the
  lead, de-essed and compressed as one group, wider, and further back in
  the room;
- the band: each instrument at the level and place the arrangement gave it
  (the drift's balance included), its sound shaped and cleared around the
  voice; together, set `forward` dB under the voice while it sings, and
  there its presence range dips and the lute doubling the tune steps back,
  both coming back when the voice stops.

The buses share the room (room.py: this machine's RT60, tone and predelay),
each at its own distance; its return is kept out of the low end and the top,
and gives way a little while the voice sings so the words keep their edges.
The sum is glued lightly, tilted brighter or darker, and optionally worn like
an old tape. master.py then brings it to loudness under a true-peak ceiling.
docs/MIX.md has the design and how it was measured.

Everything a variation might turn is in MixParams, with its range.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from functools import partial

import numpy as np

from . import fx, room, threads
from .master import limit, loudness

# --- the knobs ------------------------------------------------------------------------


@dataclass(frozen=True)
class MixParams:
    """What a rendition may vary about its mix. Every knob has a default that
    is the mix as designed, and a range (RANGES) it is held to; the harvest
    sets the room, the drift may move any of them.

    rt60      0.3-2.5 s   how long the room rings, mid band (the harvest measures it)
    tone      5 x 0-2     the room's level in five bands from 40 Hz to 16 kHz (the harvest)
    predelay  0.005-0.08 s  how soon the room answers after the sound
    space     0-1.5       how much of the room is heard: 0 dry, 1 as designed, 1.5 half again
    intimacy  0-1         how close the singer is: 0 back in the room (twice the voice's reverb),
                          0.5 as designed, 1 right at the ear (half of it)
    width     0-1.4       stereo width of the band, choir and room: 0 mono, 1 as designed
    forward   5-15 dB     how far the voice stands above the band while it sings
                          (before the band makes way: the dip and the lead lines' step back add more)
    duck      0-2         how much the band and room make way for the voice: 0 not at all, 1 as designed
    tilt      -2-+2 dB    the whole record darker (-) or brighter (+): the top end up and the bottom
                          down by this much against 1 kHz
    wear      0-1         0 new; toward 1 an old tape: wow and flutter, saturation, a narrower
                          band, hiss, and from 0.35 crackle
    balance   name: dB    an instrument (by stem name or role) up or down, e.g. fiddle: +2
    plate     0-2         how much of the singers' plate is heard: 0 none, 1 as designed (a style's taste)
    """

    rt60: float = 1.1
    tone: tuple[float, ...] = room.TONE
    predelay: float = 0.012
    space: float = 1.0
    intimacy: float = 0.5
    width: float = 1.0
    forward: float = 10.0
    duck: float = 1.0
    tilt: float = 0.0
    wear: float = 0.0
    balance: tuple[tuple[str, float], ...] = ()
    plate: float = 1.0

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
    "predelay": (0.005, 0.08),
    "space": (0.0, 1.5),
    "intimacy": (0.0, 1.0),
    "width": (0.0, 1.4),
    "forward": (5.0, 15.0),
    "duck": (0.0, 2.0),
    "tilt": (-2.0, 2.0),
    "wear": (0.0, 1.0),
    "plate": (0.0, 2.0),
}

# --- channel strips ---------------------------------------------------------------------


@dataclass(frozen=True)
class Strip:
    """How one kind of instrument is treated on its way to the band bus. The
    arrangement sets each instrument's level and place (and the drift its
    balance); the strip only shapes its sound and trims it."""

    eq: tuple = ()  # equalizer bands, fx.design
    trim: float = 0.0  # dB against its level as arranged
    comp: tuple | None = None  # a compressor (see VOICE_COMP)
    drive: float = 0.0  # warmth, fx.saturate
    send: float = 1.0  # how much reaches the room, against the band's usual
    duck: float = 0.0  # dB it steps back while the voice sings (a doubling of the tune, a lead line)


ROLES: dict[str, Strip] = {
    # A plucked lute or cittern, doubling the tune under the words: boxiness and the voice's range cleared,
    # and it steps back while the voice sings the same notes.
    "lute": Strip(eq=(("hp", 90), ("peak", 320, -2.0, 1.0), ("peak", 2800, -2.0, 0.9)), drive=0.1, duck=3.0),
    # A banjo comping (rolls, clawhammer): nothing under its lowest string, 1 dB of its ring out where the voice's
    # consonants are (the band's own dip does the rest while the voice sings), a compressor slow to grab and
    # leaning only on what stands 5 dB out of its bar, so the picks keep their edge and a roll its accents;
    # it comps, so it doesn't duck.
    "banjo": Strip(eq=(("hp", 90), ("peak", 2800, -1.0, 0.9)), comp=(10.0, 2.0, 0.015, 0.2, 1.5, 5.0), drive=0.05,
                   send=0.8),
    # A mandolin comping (strums, the chop): its weak low course cleared, nothing taken from its bark,
    # compressed gently and slowly (a tremolo evened, the chop untouched).
    "mandolin": Strip(eq=(("hp", 110),), comp=(10.0, 2.0, 0.02, 0.2, 1.5, 3.0), drive=0.05),
    # The main accompaniment: weight kept, boom and clang tamed, sparkle above the voice.
    "guitar": Strip(eq=(("hp", 75), ("peak", 200, -2.0, 1.1), ("peak", 2600, -2.0, 0.8), ("high", 9000, 1.0)),
                    comp=(10.0, 2.0, 0.015, 0.2, 1.5, 3.0), drive=0.1, send=0.9),
    "harp": Strip(eq=(("hp", 70), ("peak", 2800, -1.5, 0.9)), send=1.2),
    # Round and even: no rumble, mud out, no string noise, saturated so small speakers hear its pitch.
    "bass": Strip(eq=(("hp", 40, 4), ("peak", 380, -2.0, 0.8), ("lp", 3000)),
                  comp=(10.0, 3.0, 0.01, 0.15, 1.5, 3.0), drive=0.35, send=0.25),
    "fiddle": Strip(eq=(("hp", 180), ("peak", 2500, -2.5, 1.0), ("high", 8000, -1.0)),
                    comp=(10.0, 2.0, 0.02, 0.25, 2.0, 3.0), send=1.3, duck=2.0),
    "whistle": Strip(eq=(("hp", 250), ("peak", 3000, -2.0, 1.4), ("high", 9000, -1.0)), send=1.3, duck=2.0),
    "drum": Strip(eq=(("hp", 40), ("peak", 420, -2.0, 1.0), ("high", 8000, -1.0)), comp=(12.0, 3.0, 0.004, 0.12, 1.0, 4.0), send=0.6),
    # A drum kit: the kick's 50 Hz kept, boxiness out, the cymbals' air left alone, a compressor slower to grab
    # than the frame drum's (a kit's transients are its point), half the band's room.
    "kit": Strip(eq=(("hp", 30), ("peak", 420, -2.0, 1.0)), comp=(12.0, 3.0, 0.02, 0.15, 1.0, 4.0), send=0.5),
    # A held drone stays out of the words altogether.
    "drone": Strip(eq=(("hp", 50), ("peak", 2500, -3.0, 0.7), ("lp", 6000))),
    # Keys and mallets comping like the guitar: weight kept, boxiness and the voice's presence cleared.
    "keys": Strip(eq=(("hp", 60), ("peak", 250, -1.5, 1.0), ("peak", 2600, -2.0, 0.8), ("high", 9000, 0.5)),
                  comp=(10.0, 2.0, 0.015, 0.2, 1.5, 3.0), send=1.0),
    # An organ or a pad: held under everything, out of the words, no fizz.
    "organ": Strip(eq=(("hp", 55), ("peak", 2500, -2.5, 0.7), ("lp", 8000)), send=1.0),
    # Free reeds: nasal mids tamed, stepping back a little under the voice like a lead line.
    "reed": Strip(eq=(("hp", 140), ("peak", 1200, -1.5, 1.0), ("peak", 2800, -2.0, 1.0), ("high", 9000, -1.0)),
                  send=1.1, duck=2.0),
    # Squeezeboxes: the reed's treatment, but an accordion's Stradella bass (65-123 Hz) and a concertina's oom (from
    # 131 Hz) kept, the box's hump near 250 Hz eased; they mostly comp, so they step back only a little.
    "squeezebox": Strip(eq=(("hp", 50), ("peak", 250, -1.0, 1.0), ("peak", 1200, -1.5, 1.0), ("peak", 2800, -2.0, 1.0),
                            ("high", 9000, -1.0)), send=1.1, duck=1.0),
    # A harmonica: its cover plates' presence near 3 kHz is its reed's own now, so only a little of its honk near
    # 1 kHz out and its breath's top softened; a lead line, it steps back under the voice.
    "harmonica": Strip(eq=(("hp", 180), ("peak", 1000, -1.5, 1.0), ("high", 10000, -1.0)), send=1.1, duck=2.0),
    # A cello or a section: the fiddle's treatment without its 180 Hz high-pass, so the low strings are heard; the
    # cut for boxiness at the B1 pair's boom (190 Hz), not in the cello's formant above it (250-500 Hz).
    "strings": Strip(eq=(("hp", 45), ("peak", 190, -1.5, 1.0), ("peak", 2500, -2.0, 1.0), ("high", 8000, -1.0)),
                     comp=(10.0, 2.0, 0.02, 0.25, 2.0, 3.0), send=1.3),
    # Synths: an arpeggio or a lead line, cleared around the voice.
    "synth": Strip(eq=(("hp", 80), ("peak", 2800, -2.0, 0.9)), send=0.9, duck=1.5),
    # A pedal steel: its low strings kept (B2 is 123 Hz, its warmth below 250), the voice's presence cleared, a
    # generous send; no compressor and no duck, since its own volume pedal swells it in and out under the voice.
    "steel": Strip(eq=(("hp", 70), ("peak", 2600, -2.0, 0.9), ("high", 8000, -1.0)), send=1.2),
    # A slide guitar answering the voice: the guitar's weight kept, its box and the voice's presence cleared, and
    # a small step back while the voice sings, as a lead line takes.
    "slide": Strip(eq=(("hp", 70), ("peak", 250, -1.5, 1.0), ("peak", 2800, -2.0, 0.9), ("high", 9000, -0.5)),
                   comp=(10.0, 2.0, 0.015, 0.2, 1.5, 3.0), send=1.1, duck=1.5),
    "band": Strip(eq=(("hp", 60), ("peak", 2800, -1.5, 0.9))),  # anything else
}

NAMES = {
    "voice": ("voice", "lead", "vocal", "singer"),
    "choir": ("choir", "harmony", "backing"),
    "lute": ("melody", "lute", "bouzouki", "cittern", "oud"),
    "banjo": ("banjo",),
    "mandolin": ("mandolin", "mandola"),
    "guitar": ("guitar", "strum", "pick", "electric", "nylon", "ukulele"),
    "harp": ("harp", "dulcimer", "zither", "kantele", "psaltery"),
    "bass": ("bass", "contrabass", "upright"),
    "fiddle": ("fiddle", "violin", "bow"),
    "whistle": ("whistle", "flute", "pipe", "recorder", "fife", "blown"),
    "drum": ("drum", "drums", "percussion", "bodhran", "tambourine", "shaker", "kick", "snare", "skin", "frame",
             "claps", "clap", "stomps", "stomp", "cajon", "machine", "hats"),
    "kit": ("kit",),
    "drone": ("drone", "pad", "shruti", "bagpipe", "hum"),
    "keys": ("piano", "epiano", "rhodes", "keys", "celesta", "musicbox", "music-box", "glock", "glockenspiel", "vibes",
             "vibraphone", "marimba", "xylophone", "bells"),
    "organ": ("organ", "synthpad", "synth-pad", "harmonium"),  # sustained keys: no drone's 6 kHz low-pass
    "reed": ("reed",),
    "squeezebox": ("accordion", "concertina", "melodeon", "bandoneon", "squeezebox"),
    "harmonica": ("harmonica",),
    "strings": ("cello", "viola", "strings", "quartet"),  # their low strings kept: no fiddle's 180 Hz high-pass
    "synth": ("synth", "synthlead", "arp", "chip"),
    "steel": ("steel", "pedalsteel", "lapsteel"),  # its low strings kept, and no fiddle's duck: it swells by its pedal
    "slide": ("slide", "bottleneck"),
}
SINGERS = ("voice", "choir")  # stems sung by the singers: matched by their whole names only


def role_of(name: str) -> str:
    """The role a stem plays, from its name: "choir2" is choir, "guitar_low" guitar, anything unknown "band".
    Only a whole name makes a stem a singer ("synthlead" is a synth, never the lead voice)."""
    word = re.sub(r"[\d_\-\s.]+$", "", name.lower())
    for role, names in NAMES.items():
        if word in names:
            return role
    for role, names in NAMES.items():
        if role not in SINGERS and any(n in word for n in names):
            return role
    return "band"


# The voice and choir, in the same terms as the band's roles.
VOICE_EQ = (("hp", 80), ("peak", 900, -2.0, 1.2), ("peak", 3500, 0.5, 0.9))  # presence 2.0 until 2026-09-27 (the top notes were harsh)
# The voice's air (7-14 kHz) against its body (0.5-2 kHz): natural singers (SoulX-Singer renders of our score)
# measure -21 to -23 dB. A voice brighter than AIR is brought half way back, never by more than 3 dB.
AIR = -20.0
# Compressors: (floor: dB under the part's loud passages, ratio, attack s, release s, ride s, above dB).
# With a ride, the threshold is `above` dB over the level of the surrounding `ride` seconds (never under the
# floor): a syllable is evened against its phrase, a strum against its bar, but a quiet verse stays quiet.
VOICE_COMP = (10.0, 2.0, 0.015, 0.2, 3.0, 3.0)  # only the syllables that stand out of their phrase are leaned on
CHOIR_EQ = (("hp", 120), ("low", 260, -2.0), ("peak", 3000, -2.5, 0.8), ("high", 9000, -2.0))
CHOIR_COMP = (6.0, 2.0, 0.03, 0.3, 0.0, 0.0)
PEAKS = 3.0  # dB over its loud peaks a choir's, drum's or the room's onset may reach before a peak stage rounds it off
CHOIR_UNDER = 4.0  # dB the choir as a whole sits under the lead
CHOIR_WIDTH = 1.35  # never past 1.6, whatever `width` asks
CHOIR_LATER = 0.02  # s the choir's sound reaches the room after the band's: it stands further back

# Sends to the room (amplitude, before `space`), and the plate's for the voice.
VOICE_ROOM = 0.08
VOICE_PLATE = 0.18
BAND_ROOM = 0.18
CHOIR_ROOM = 0.5
CHOIR_PLATE = 0.12
PLATE_RT60 = 1.5
RETURN_EQ = (("hp", 120), ("lp", 12000))  # wide enough that the harvested tone's ends are heard
RETURN_DIP = 3.0  # dB the room and plate give way while the voice sings
MAKE_WAY = (0.02, 0.9)  # s the band and room take to make way for the voice (quick: its first consonants), and to come back after it (slow: no breathing)
RIDE = (5.0, 1.5)  # dB the band comes up where the voice rests, over this many seconds (3.0 until 2026-09-27)

CARVE = (2600.0, 0.7)  # the band's dip for the voice: centre Hz, Q
CARVE_DEPTH = 6.0  # dB at full voice
BAND_EQ = (("low", 200, 2.5), ("peak", 600, -2.0, 0.8))  # the band as a whole: warmer, and less boxy where the voice's vowels sit
BAND_COMP = (10.0, 1.5, 0.02, 0.2, 2.0, 3.0)  # the band together, lightly: its arc from sparse verses to full refrains is kept
GLUE = (8.0, 1.5, 0.05, 0.4, 3.0, 3.0)  # the whole mix, lightly: what stands out of its surroundings, never the song's arc
REFERENCE = -20.0  # LUFS the voice is brought to before the balance is set
# The lead's saturation. At 0.2 its drive was set against the voice's typical peaks, and the throat's loudest
# syllables (its crest is 13.7 dB) ran 4-9 dB further into the curve: distortion above 2 kHz at -21 dB under
# the voice's own highs on the loudest twentieth, which nothing masked (the band's highs sit 18-29 dB under
# the voice's). That was the "roughness as the voice gets loud" the artist heard (2026-09-27). 0.05: -33 dB.
VOICE_DRIVE = 0.05
# The transient softener on the lead (fx.soften: dB over its own recent level a jump may reach, the fraction of the
# excess taken off), before the saturation, which would harden what it leaves: the learned voice's consonant
# bursts read as clipping to the artist (2026-09-27; Whisper in the mix 11.4% -> 11.9% of words, within noise). None: off.
VOICE_SOFTEN = (6.0, 0.6)
# The singers rise and fall with the arrangement's energy (songbird.band: each section's, 0..1, arcing across
# the song): LEAD_ARC[0] dB per unit of energy above ENERGY_REST, held between LEAD_ARC[1] and LEAD_ARC[2] dB and
# smoothed over LEAD_ARC[3] s. Without it the lead came out at REFERENCE in every sung section, whatever the band
# did, so a build the band made of 6 dB reached the record as half a dB (the mix review of 2026-09-27).
LEAD_ARC = (6.0, -2.0, 2.5, 1.0)
ENERGY_REST = 0.55
WARMTH = (("low", 180, 2.0),)  # the whole record: a little more weight under the voice, where only the band and a low singer reach


# --- helpers ----------------------------------------------------------------------------


def quick_loudness(x: np.ndarray, sr: int) -> float:
    """Integrated loudness at half the sample rate (pairs averaged): within a
    few tenths of a LU of the full measurement for a stem, at half the cost."""
    n = len(x) // 2 * 2
    if n < 2 * sr:
        return loudness(x, sr)
    return loudness((x[:n:2] + x[1:n:2]) / 2.0, sr // 2)


def _compressor(x: np.ndarray, sr: int, setting, **extra) -> tuple[np.ndarray, np.ndarray]:
    floor, ratio, attack, release, ride, above = (*setting, 0.0, 0.0)[:6]
    if ride:  # a narrow knee, whose foot stays over the surroundings' level: only what stands out is touched
        extra = {"knee": 4.0, **extra} if "knee" not in extra else {**extra, "knee": min(extra["knee"], 2 * (above - 1))}
    return fx.compress(x, sr, fx.loud_level(x, sr) - floor, ratio, attack, release, ride=ride, above=above, **extra)


def _sizzle(x: np.ndarray, sr: int) -> tuple:
    """A high shelf that brings a voice brighter than natural singers (AIR) half way back."""
    mono = x.reshape(len(x), -1).mean(axis=1)
    n = 1 << 13
    if len(mono) < n:
        return ()
    starts = np.linspace(0, len(mono) - n, min(200, len(mono) // n)).astype(np.int64)
    spectrum = (np.abs(np.fft.rfft(mono[starts[:, None] + np.arange(n)] * np.hanning(n), axis=1)) ** 2).sum(axis=0)
    f = np.fft.rfftfreq(n, 1.0 / sr)
    air = spectrum[(f >= 7000) & (f < 14000)].sum()
    body = spectrum[(f >= 500) & (f < 2000)].sum()
    if air <= 0 or body <= 0:
        return ()
    over = 10.0 * np.log10(air / body) - AIR
    return (("high", 9000, -min(3.0, 0.5 * over)),) if over > 0 else ()


def _compressed(x: np.ndarray, sr: int, setting, inplace: bool = False) -> np.ndarray:
    return _compressor(x, sr, setting, inplace=inplace)[0]


def _at(x: np.ndarray, sr: int, target: float, inplace: bool = False) -> np.ndarray:
    """x scaled so its loudness is `target` LUFS (inplace: where it lies, when x is float64)."""
    measured = quick_loudness(x, sr)
    if not np.isfinite(measured):
        return x
    if inplace and x.dtype == np.float64:
        x *= 10.0 ** ((target - measured) / 20.0)
        return x
    return x * 10.0 ** ((target - measured) / 20.0)


def _treated(x: np.ndarray, treat, own: bool = False) -> np.ndarray:
    """treat(x, own), done once on the sound itself (its own: treat may work on it where it lies) when the
    stem is one mono sound panned. own: x is the treatment's to overwrite."""
    mono = fx.as_mono(x)
    if mono is None:
        return treat(x, own)
    sound, gains = mono
    return treat(sound[:, None], True) * gains[None, :]


def _conformed(stems: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Every stem as a float (samples, 2) array, all as long as the longest: a
    mono stem sounds in the middle, a longer one isn't cut."""
    out = {}
    for name, x in stems.items():
        x = np.asarray(x, dtype=np.float64)
        x = x.reshape(len(x), -1)
        if x.shape[1] == 1:
            x = np.repeat(x * np.sqrt(0.5), 2, axis=1)
        out[name] = x[:, :2]
    length = max((len(x) for x in out.values()), default=0)
    return {k: (np.pad(x, ((0, length - len(x)), (0, 0))) if len(x) < length else x) for k, x in out.items()}


def _peaks(x: np.ndarray, sr: int, inplace: bool = False) -> np.ndarray:
    """A peak stage for parts whose onsets jump far over the rest (a choir's
    consonants, a drum's strike, the room's first echoes of them): what
    swings past PEAKS dB over the part's loud peaks is rounded off by a
    look-ahead limiter, so the master's limiter hardly has to work."""
    return limit(x, sr, 20.0 * np.log10(fx.loud_peak(x, sr) + 1e-12) + PEAKS, inplace=inplace)


def _sum(stems: dict[str, np.ndarray], names: list[str]) -> np.ndarray | None:
    out = None
    for name in names:
        out = stems[name].copy() if out is None else out + stems[name]
    return out if out is not None and np.any(out) else None


def _alone(x: np.ndarray) -> np.ndarray | None:
    """_sum of one stem, without its copy where the copy would be laid out as it is."""
    return (x if x.flags.c_contiguous else x.copy()) if np.any(x) else None


def lead_lift(sections, energies, sr: int, length: int) -> np.ndarray | None:
    """dB per sample the singers rise with the arrangement: from each section's (name, start, end) and its
    energy (0..1, the band's, in the same order), LEAD_ARC dB per unit above ENERGY_REST, held within the
    arc's bounds and smoothed over LEAD_ARC[3] s so a section's change arrives as a swell, not a step. None
    when the sections and energies don't pair up (an older score: level singers, as before)."""
    if not sections or not energies or len(sections) != len(energies) or length <= 0:
        return None
    lift = np.zeros(length)
    for (_, start, end), energy in zip(sections, energies):
        a, b = int(max(0.0, float(start)) * sr), int(min(float(end) * sr, length))
        if b > a:
            lift[a:b] = np.clip(LEAD_ARC[0] * (float(energy) - ENERGY_REST), LEAD_ARC[1], LEAD_ARC[2])
    lift[int(float(sections[-1][2]) * sr):] = lift[min(int(float(sections[-1][2]) * sr), length) - 1]  # the ring holds
    lift[: int(max(0.0, float(sections[0][1])) * sr)] = lift[min(int(max(0.0, float(sections[0][1])) * sr), length - 1)]
    return fx.running_mean(lift, max(int(LEAD_ARC[3] * sr), 1), out=lift)  # uniform_filter1d's, where it lies


# --- the mix --------------------------------------------------------------------------------


def mix(stems: dict[str, np.ndarray], sr: int, seed: int = 0, params: MixParams | None = None,
        taps: dict | None = None, lift: np.ndarray | None = None) -> np.ndarray:
    """Stems (each stereo, all one length) into one unmastered stereo mix, room
    included. taps: a dict to receive the buses and each treated stem as they
    go into the sum (for analysis). lift: dB per sample the singers rise and
    fall with the arrangement (lead_lift), or None for level singers."""
    stems = _conformed(stems)
    if not stems:
        return np.zeros((0, 2))
    length = len(next(iter(stems.values())))
    return mix_made([(name, lambda x=x: x) for name, x in stems.items()], length, sr, seed, params, taps, lift,
                    own=False)


def _conform(x: np.ndarray, length: int) -> np.ndarray:
    """One stem as _conformed makes it, for a mix `length` samples long."""
    x = np.asarray(x, dtype=np.float64)
    x = x.reshape(len(x), -1)
    if x.shape[1] == 1:
        x = np.repeat(x * np.sqrt(0.5), 2, axis=1)
    x = x[:, :2]
    if len(x) > length:
        raise ValueError(f"a stem of {len(x)} samples for a mix of {length}")
    return np.pad(x, ((0, length - len(x)), (0, 0))) if len(x) < length else x


def mix_made(parts: list, length: int, sr: int, seed: int = 0, params: MixParams | None = None,
             taps: dict | None = None, lift: np.ndarray | None = None, progress=None, own: bool = True) -> np.ndarray:
    """mix(), from the stems' makers: (name, make) for each stem, none longer than `length` samples. Each
    stem is made, treated and put into its bus as the mix comes to it, and let go: the band's instruments in
    their names' order, the singers before the first instrument that steps back under the voice (the band
    makes way for it; on one or two threads, before them all), a few made ahead on threads
    (threads.in_order, the lead started first), so a song's stems are never all held at once. The same mix, to the bit,
    as mix() of all of them. progress, if given, is told each stem's name as the mix comes to it, then
    "mix". own: each make() gives a stem of its own, which the mix may treat where it lies (mix() passes
    False: its stems are the caller's)."""
    p = (params or MixParams()).clamped()
    if not parts:
        return np.zeros((0, 2))
    makers = dict(parts)
    rise = None if lift is None else (10.0 ** (np.asarray(lift, dtype=float)[:length] / 20.0))[:, None]
    lift = None
    balance = dict(p.balance)
    roles = {name: role_of(name) for name in sorted(makers)}
    nudge = {name: balance.get(name, balance.get(role, 0.0)) for name, role in roles.items()}  # a name wins over its role

    def stem(name: str) -> np.ndarray:
        return _conform(makers[name](), length)

    # The lead: everything else is placed against it.
    # Each treatment works on its sound where it lies once the sound is its own (a copy made by the first step
    # that makes one, or a stem the mix was given to keep): the same samples as treated copies.
    def lead(x, owned):
        x = fx.equalize(x, fx.design(VOICE_EQ + _sizzle(x, sr), sr), inplace=owned)  # VOICE_EQ: a copy if not
        x = fx.deess(x, sr, inplace=True)[0]
        x = _compressed(x, sr, VOICE_COMP, inplace=True)
        if VOICE_SOFTEN:
            x = fx.soften(x, sr, *VOICE_SOFTEN, inplace=True)
        return _at(_peaks(fx.saturate(x, sr, VOICE_DRIVE, inplace=True), sr, inplace=True), sr, REFERENCE, inplace=True)

    def lead_bus(voice, owned):
        if voice is None:
            return None
        voice = _treated(voice, lead, owned)
        if rise is not None:  # the lead rises with the arrangement: quieter in a sparse verse, fuller at the climax
            voice *= rise[:len(voice)]
        return voice, fx.activity(voice, sr, attack=MAKE_WAY[0], release=MAKE_WAY[1])

    # The lineage choir, as one group, where it sings; de-essed as the lead is (its voices say each "s" together,
    # and its sends to the room and plate are the biggest)
    def choir_bus(choir, owned):
        if choir is None:
            return None
        where = fx.span(choir, sr)
        if where.stop - where.start > sr // 2:
            group = fx.deess(fx.equalize(choir[where], fx.design(CHOIR_EQ, sr), inplace=owned), sr, inplace=True)[0]
            group = _peaks(_compressed(group, sr, CHOIR_COMP, inplace=True), sr, inplace=True)
            group = fx.width(group, sr, min(CHOIR_WIDTH * p.width, 1.6), inplace=True)
            choir = np.zeros((length, 2))
            choir[where] = _at(group, sr, REFERENCE - CHOIR_UNDER + balance.get("choir", 0.0))
            if rise is not None:
                choir[where] *= rise[where]
            return choir
        return None

    # The band: each instrument to its place, then together.
    def channel(x, owned, strip, role):
        sos = fx.design(strip.eq, sr)
        x = fx.equalize(x, sos, inplace=owned)
        owned = owned or len(sos) > 0  # a copy, if not where it lay
        if strip.comp:
            x = _compressed(x, sr, strip.comp, inplace=owned)
            owned = True
        if role in ("drum", "kit"):
            y = _peaks(x, sr, inplace=owned)
            owned = owned or y is not x
            x = y
        return fx.saturate(x, sr, strip.drive, inplace=owned)

    def instrument(name: str):
        x = stem(name)
        where = fx.span(x, sr)
        if where.stop <= where.start:
            return None
        strip = ROLES[roles[name]]
        y = _treated(x[where], partial(channel, strip=strip, role=roles[name]), own)
        gain = 10.0 ** ((strip.trim + nudge[name]) / 20.0)
        if own or not np.shares_memory(y, x):
            y *= gain  # where it lies: the same products
            return where, y
        return where, y * gain

    # Each bus's and instrument's own treatment depends on nothing but its own sound, so they are made at once
    # (threads.in_order, a few ahead); they are put together below, one at a time, in the order they always were:
    # a bus of one stem is made with its stem; a bus of several is summed as they come, then treated.
    buses = {"voice": lead_bus, "choir": choir_bus}
    groups = {bus: [n for n, r in roles.items() if r == bus] for bus in buses}
    sung = []
    for bus, names in groups.items():
        if len(names) == 1:
            sung.append((names[0], lambda bus=bus, name=names[0]: buses[bus](_alone(stem(name)), own)))
        else:
            sung += [(name, partial(stem, name)) for name in names]
    played = [(name, partial(instrument, name)) for name, role in roles.items() if role not in buses]
    # The instruments go into the band in their names' order; only those that step back under the voice need
    # it made first (singing). On three threads or more the singers are put together just before the first
    # of those, and started first of all: the instruments before it are made and summed while the voice is
    # still being sung (faster; on two, 0.07 GB more at the peak). On one or two, the singers come first, and
    # the voice is sung before the band's sums are begun (the least memory).
    steps_back = next((i for i, (name, _) in enumerate(played) if ROLES[roles[name]].duck), len(played))
    if threads.workers() <= 2:
        steps_back = 0
    jobs = played[:steps_back] + sung + played[steps_back:]
    singers_left = len(sung)

    voice = choir = singing = None
    band = np.zeros((length, 2))
    band_send = np.zeros((length, 2))
    stepping = np.zeros((length, 2))  # what the instruments that step back under the voice give up
    held: dict = {}
    results = threads.in_order(jobs, first=tuple(name for name, _ in sung[:1]), ahead=threads.workers())
    try:
        for name, _ in jobs:
            if progress is not None:
                progress(name)
            result = next(results)[1]
            role = roles[name]
            if role in buses:
                singers_left -= 1
                if len(groups[role]) > 1:
                    held[name] = result
                    if len(held) < len(groups[role]):
                        continue
                    result = buses[role](_sum(held, groups[role]), True)
                    held = {}
                if role == "voice":
                    voice, singing = result if result is not None else (None, None)
                else:
                    choir = result
                if not singers_left:
                    rise = None  # the singers' buses are made: nothing else rises with the arrangement
                continue
            if result is None:
                continue
            strip, (where, x) = ROLES[role], result
            if taps is not None:
                taps[name] = (where, x)
            band[where] += x
            band_send[where] += x * strip.send
            if strip.duck and singing is not None:
                stepping[where] += x * (1.0 - 10.0 ** (-strip.duck * p.duck * singing[where] / 20.0))[:, None]
            del result, x
    finally:
        results.close()
    if progress is not None:
        progress("mix")
    # from here each long signal is let go as soon as it has been used, and treated where it lies when nothing
    # else holds it (the same samples as a treated copy)
    rise = None
    gain = 1.0
    if np.any(band):
        eq = fx.design(BAND_EQ, sr)
        band = fx.equalize(band, eq, inplace=True)
        band, squeeze = _compressor(band, sr, BAND_COMP, inplace=True)
        # the band under the voice, measured where the voice sings, before it makes way for it
        sung = singing is not None and np.mean(singing > 0.5) > 0.05
        level = quick_loudness(band[singing > 0.5], sr) if sung else quick_loudness(band, sr)
        if np.isfinite(level):
            gain = 10.0 ** ((REFERENCE - (p.forward if sung else 3.0) - level) / 20.0)
        if np.any(stepping):  # the lead lines step back, through the same equalizer and compressor
            band -= fx.apply_gain(fx.equalize(stepping, eq, inplace=True), squeeze, inplace=True)
        del stepping
        band *= gain
        band_send *= gain
        if singing is not None:
            # where the voice rests a while (the intro, the turns), the band is ridden up, as an engineer would;
            # the ride goes up and comes back down inside the rest, so the band is down again before the voice returns
            # (minimum_filter1d's and uniform_filter1d's, and the ride's gain, each where the last left it)
            ride = (singing < 0.05).astype(float)
            fx.sliding_min(ride, int(RIDE[1] * sr), out=ride)
            fx.running_mean(ride, int(RIDE[1] * sr / 2), out=ride)
            ride *= RIDE[0] * p.duck
            ride /= 20.0
            np.power(10.0, ride, out=ride)
            band *= ride[:, None]
            band_send *= ride[:, None]
            del ride
            band = fx.dynamic_dip(band, sr, CARVE[0], CARVE[1], CARVE_DEPTH * p.duck * singing, inplace=True)
        band = fx.width(band, sr, p.width, inplace=True)

    # The room, heard from each bus at its own distance; the plate for the singers.
    size = min(1.0, (1.1 / p.rt60) ** 0.25)  # a long room needs less sent to be heard as much
    near = 2.0 ** (1.0 - 2.0 * p.intimacy)  # the voice's own sends: 2 far back, 1 as designed, 0.5 at the ear
    band_send *= BAND_ROOM
    send, band_send = band_send, None
    plate_send = np.zeros(length)
    if voice is not None:
        send += voice * (VOICE_ROOM * near)
        plate_send += voice.sum(axis=1) * (VOICE_PLATE * p.plate * near * np.sqrt(0.5))
    if choir is not None:
        send += fx.delay(choir, int(CHOIR_LATER * sr)) * CHOIR_ROOM
        plate_send += choir.sum(axis=1) * (CHOIR_PLATE * p.plate * np.sqrt(0.5))
    # the room is its numbers: the same numbers (a machine's harvested room) give the same room every rendition
    early, tail = room.responses(sr, p.rt60, p.tone, p.predelay, room.seed_of(p.rt60, p.tone, p.predelay))
    if np.any(plate_send):
        plate_send *= p.space
        plates = [(plate_send, room.plate(sr, PLATE_RT60, 0))]
    else:
        plates = []
    del plate_send
    send *= p.space * size
    given = [send]  # room.convolve takes the send out of the list: it is let go once its mid and side are made
    del send
    wet = room.convolve(given, early, tail, plates)
    del plates
    wet = _peaks(fx.width(fx.equalize(wet, fx.design(RETURN_EQ, sr), inplace=True), sr, p.width, inplace=True), sr,
                 inplace=True)
    if singing is not None:
        # the room gives way to the lead's words, but not where the lineage sings with it: that is its space
        dip = np.zeros(len(wet))
        dip[:length] = RETURN_DIP * p.duck * singing * (1.0 - fx.activity(choir, sr) if choir is not None else 1.0)
        wet *= (10.0 ** (-dip / 20.0))[:, None]
        del dip

    if taps is not None:
        taps.update(voice=voice, choir=choir, band=band, wet=wet.copy(), singing=singing, band_gain=gain)
    out = wet
    for bus in (voice, choir, band):
        if bus is not None:
            out[:length] += bus
    del wet, voice, choir, band, singing

    # The whole: glued, tilted, maybe worn.
    out, glue = _compressor(out, sr, GLUE, knee=8.0, window=0.05, inplace=True)
    if taps is not None:
        taps["glue"] = glue
    tone = WARMTH
    if p.tilt:  # shelves reach their gain only well past their corners: these give +-tilt at 60 Hz and 12 kHz
        tone = tone + (("low", 300, -1.15 * p.tilt), ("high", 3000, 1.15 * p.tilt))
    out = fx.equalize(out, fx.design(tone, sr), inplace=True)
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
    y = fx.saturate(y, sr, 0.1 + 0.9 * a, bias=0.12)
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
