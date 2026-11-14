"""The band's instruments: how each instrument's notes in a score become a stem.

The seed's band is eight instruments, each a physical or physically inspired
model (see pluck, bowed, pipe, drum and reed) played through its own body, and
delivered dry, panned and at a level that sits with the others and under the
singer:

    lute     a cittern-like long-neck lute, paired courses, played with a pick
    guitar   a steel-string flat top, strummed, capoed to the song's key
    harp     a lever harp, plucked with the fingertips, left to ring
    bass     an upright bass, pizzicato
    fiddle   a bowed string with a violin's body
    whistle  a wooden flute or low whistle
    drum     a frame drum played with a tipper
    drone    a box of free reeds, bellows-blown

How the instruments are built (their bodies' maker, size, brightness, how
worn they are) and how loud each plays comes from the score's band settings,
which realize() copies from Params.band.

Every other instrument a style can call on (a piano, a banjo, a kit, a synth)
comes from the registry: a module under songbird/synth/ that exposes

    SPEC: {name: dict(family, register=(lo, hi) or None, place=(position, width), level, poly,
                      articulations={art: meaning}, about)}
    render(name, notes, sr, length, rng, make, settings) -> dry mono (length,) or stereo (length, 2)

registers its instruments by name (registry()); this module places each stem
and sets its level (SPEC level times the lineup's gain), exactly as it does for
the eight. An instrument no module provides yet is played by a stand-in, one
of the eight models (STAND_INS), under its own name, place and level, so every
style renders from the start and the mix treats the stem by its real name.
"""

from __future__ import annotations

import hashlib
import importlib
import pkgutil
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import numpy as np
from numba import njit
from scipy.signal import sosfilt

from ..score import Note, Score
from ..theory import midi_to_hz
from . import body, bowed, drum, fx, pipe, pluck, reed
from .iir import butter

INSTRUMENTS = ("lute", "guitar", "harp", "bass", "fiddle", "whistle", "drum", "drone")

# Where each sits (-1 left, 1 right) and how wide its body sounds; as a small
# band stands: bass and drum in the middle, the chordal instruments either
# side, the two melody instruments further out, opposite each other.
PLACE = {
    "lute": (-0.35, 0.8),
    "guitar": (0.3, 0.6),
    "harp": (-0.2, 0.7),
    "bass": (0.0, 0.15),
    "fiddle": (0.5, 0.4),
    "whistle": (-0.3, 0.0),
    "drum": (0.12, 0.0),
    "drone": (0.0, 0.9),
}

# Stem gain for each instrument at balance 1: set so that, played as the
# band part arranges them, each sits where a folk band's players would under
# a singer (the voice stem stays the loudest thing in the song).
LEVEL = {
    "lute": 0.28,
    "guitar": 0.19,
    "harp": 0.18,
    "bass": 0.26,
    "fiddle": 0.2,
    "whistle": 0.12,
    "drum": 1.4,
    "drone": 0.09,
}

DEFAULTS = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0, maker=0, tonic=62, capo=0,
                **{name: 1.0 for name in INSTRUMENTS})

# --- the instruments a style can call on --------------------------------------------------------
#
# What the arrangement needs to know of each (its family, the range it plays, where it sits, how
# loud, whether it plays chords) and which of the eight models plays it until its own module lands.
# A registered module's SPEC replaces everything here but the stand-in. The levels are the stand-ins':
# each set so a typical part at velocity 0.6 sits as the band's own reference for its kind does (comping
# as the guitar's strum, a lead as the whistle, a bass as the upright, percussion as the frame drum; pads
# 4 dB and bells 3 to 6 dB under), as the instrument contract asks of the real modules.
#   name: (family, register or None, place, level, poly, stand-in, what it is)
KNOWN = {
    "piano": ("keys", (28, 96), (-0.1, 0.8), 0.12, True, "harp", "an upright or grand piano"),
    "epiano": ("keys", (36, 91), (0.15, 0.7), 0.12, True, "harp", "an electric piano, tines and a soft hammer"),
    "organ": ("organ", (36, 91), (0.0, 0.8), 0.2, True, "drone", "a drawbar organ, or a small church organ"),
    "vibes": ("mallets", (53, 89), (-0.25, 0.6), 0.09, True, "harp", "a vibraphone, motor slow or off"),
    "marimba": ("mallets", (45, 96), (-0.3, 0.6), 0.095, True, "harp", "a marimba"),
    "glock": ("mallets", (79, 108), (0.35, 0.2), 0.2, False, "harp", "a glockenspiel"),
    "musicbox": ("mallets", (60, 100), (-0.15, 0.3), 0.17, True, "harp", "a music box's comb"),
    "celesta": ("mallets", (60, 108), (0.2, 0.5), 0.095, True, "harp", "a celesta"),
    "synthpad": ("pad", (36, 88), (0.0, 1.0), 0.18, True, "drone", "an analog synth pad"),
    "synthbass": ("bass", (24, 55), (0.0, 0.0), 0.41, False, "bass", "an analog synth bass"),
    "synthlead": ("lead", (48, 96), (-0.2, 0.2), 0.15, False, "whistle", "an analog synth lead"),
    "arp": ("synth", (48, 96), (0.25, 0.7), 0.135, False, "harp", "an analog synth arpeggio"),
    "chip": ("synth", (36, 96), (0.0, 0.3), 0.17, False, "whistle", "a game console's square waves"),
    "drummachine": ("drums", None, (0.0, 0.3), 1.2, True, "drum", "a drum machine"),
    "banjo": ("plucked", (50, 84), (0.3, 0.5), 0.27, True, "lute", "a five-string banjo"),
    "mandolin": ("plucked", (55, 88), (-0.35, 0.5), 0.29, True, "lute", "a mandolin"),
    "electric": ("plucked", (40, 88), (0.4, 0.6), 0.175, True, "guitar", "an electric guitar through a small amp"),
    "steel": ("bowed", (40, 88), (0.45, 0.5), 0.27, True, "fiddle", "a pedal steel guitar"),
    "slide": ("plucked", (40, 84), (0.4, 0.5), 0.21, False, "fiddle", "a slide guitar"),
    "cello": ("bowed", (36, 76), (0.3, 0.5), 0.25, False, "fiddle", "a cello"),
    "strings": ("bowed", (36, 96), (0.0, 0.9), 0.2, True, "drone", "a string section or quartet"),
    "ebass": ("bass", (28, 60), (0.0, 0.0), 0.3, False, "bass", "an electric bass"),
    "kit": ("drums", None, (0.05, 0.6), 1.25, True, "drum", "a drum kit: sticks, brushes or rods"),
    "claps": ("percussion", None, (-0.2, 0.5), 1.0, True, "drum", "hand claps"),
    "stomps": ("percussion", None, (0.0, 0.3), 1.2, True, "drum", "feet on a wooden floor"),
    "shaker": ("percussion", None, (0.35, 0.2), 0.5, True, "drum", "a shaker"),
    "tambourine": ("percussion", None, (-0.35, 0.2), 1.0, True, "drum", "a tambourine"),
    "cajon": ("percussion", None, (0.1, 0.2), 1.3, True, "drum", "a cajon"),
    "harmonica": ("reed", (60, 96), (-0.3, 0.1), 0.125, False, "whistle", "a diatonic harmonica"),
    "accordion": ("reed", (41, 93), (-0.25, 0.8), 0.2, True, "drone", "an accordion"),
    "concertina": ("reed", (48, 96), (-0.25, 0.6), 0.21, True, "drone", "a concertina"),
}

# How a stand-in frame drum takes a kit's (or a hand percussionist's) strokes.
DRUM_STROKES = {
    "kick": "bass", "stomp": "bass", "cajon-bass": "bass", "tom-lo": "bass", "tom-mid": "tip", "tom-hi": "tip",
    "snare": "rim", "rim": "rim", "clap": "rim", "cajon-slap": "rim", "crash": "tip", "ride": "mute",
    "hat": "mute", "hat-open": "mute", "shaker": "mute", "tambourine": "mute", "brush-tap": "tip",
    "brush-sweep": "mute", "ghost": "mute",
}
QUIET = {"hat": 0.45, "hat-open": 0.55, "ride": 0.5, "shaker": 0.35, "tambourine": 0.5, "brush-sweep": 0.35,
         "ghost": 0.4}

# Modules under songbird/synth/ that are not instruments (never imported to look for a SPEC).
NOT_INSTRUMENTS = {"__init__", "instruments", "cache", "body", "bowed", "drum", "pipe", "pluck", "reed", "glottis", "master",
                   "mixing", "fx", "room", "throat", "tract", "tube", "tubevoice", "voice"}


def place(y: np.ndarray, position: float, width: float, inplace: bool = False) -> np.ndarray:
    """A mono or stereo signal to stereo at `position`, keeping `width` of a
    stereo source's side signal (0 collapses it to its middle). inplace: a stereo y (float64, two columns)
    is placed where it lies, and returned."""
    theta = (position + 1.0) * np.pi / 4.0
    if fx.JIT and y.dtype == np.float64 and y.ndim in (1, 2) and (y.ndim == 1 or y.shape[1] >= 2):
        # straight into the stereo result, sample by sample, by the same operations in the same order as
        # the expressions below (no temporaries the length of the song); each sample's pair is read before
        # it is written, so the result may be y itself
        out = y if inplace and y.ndim == 2 and y.shape[1] == 2 else np.empty((len(y), 2))
        _placed(y if y.ndim == 2 else y[:, None], np.cos(theta), np.sin(theta), np.sqrt(2.0), float(width), out)
        return out
    if y.ndim == 1:
        return np.stack([y * np.cos(theta), y * np.sin(theta)], axis=1) * np.sqrt(2.0)
    mid = 0.5 * (y[:, 0] + y[:, 1])
    side = 0.5 * (y[:, 0] - y[:, 1]) * width
    return np.stack([mid * np.cos(theta) * np.sqrt(2.0) + side, mid * np.sin(theta) * np.sqrt(2.0) - side], axis=1)


@njit(cache=True, nogil=True)
def _placed(y: np.ndarray, cos: float, sin: float, root2: float, width: float, out: np.ndarray) -> None:
    """place() into out: a mono y (one column) as (y cos) root2, (y sin) root2; a stereo one as its mid
    0.5 (l + r) at the angle, (mid cos) root2 + side and (mid sin) root2 - side, side 0.5 (l - r) width."""
    if y.shape[1] == 1:
        for i in range(y.shape[0]):
            v = y[i, 0]
            out[i, 0] = (v * cos) * root2
            out[i, 1] = (v * sin) * root2
    else:
        for i in range(y.shape[0]):
            mid = 0.5 * (y[i, 0] + y[i, 1])
            side = (0.5 * (y[i, 0] - y[i, 1])) * width
            out[i, 0] = (mid * cos) * root2 + side
            out[i, 1] = (mid * sin) * root2 - side


def _strings(notes, sr: int, length: int, rng: np.random.Generator, spec: dict, tuning=None) -> np.ndarray:
    """Every plucked note of a part laid onto one bridge-force track."""
    force = np.zeros(length)
    for note in notes:
        start = int(round(note.start * sr))
        if start >= length:
            continue
        offset = tuning(note) if tuning else 0.0
        y = pluck.pluck(
            midi_to_hz(note.pitch + offset / 100.0),
            note.dur,
            sr,
            rng,
            vel=note.vel,
            brightness=spec["brightness"] * (0.85 + 0.3 * note.vel) if note.art != "mute" else 0.2,
            decay=spec["decay"],
            pick=spec["pick"] * rng.uniform(0.85, 1.15),
            hardness=spec["hardness"],
            planes=spec["planes"],
            course=spec.get("course", 0.0),
            spread=spec.get("spread", 0.0) * rng.uniform(0.6, 1.4),
            touch=spec.get("touch", 0.0),
            mute=note.art == "mute",
            damp=spec.get("damp", 0.08),
        )
        end = min(length, start + len(y))
        force[start:end] += y[: end - start]
    return force


def _open_strings(tonic: int, low: int, high: int) -> list[int]:
    """An instrument tuned to the song: its open strings on the tonic and fifth, in range."""
    pcs = {tonic % 12, (tonic + 7) % 12}
    return [p for p in range(low, high + 1) if p % 12 in pcs]


def _model(kind: str, notes, sr: int, length: int, s: dict, rng: np.random.Generator,
           make: np.random.Generator) -> np.ndarray:
    """The dry stem of one of the eight models playing `notes`: mono or stereo, before its place and level."""
    bright, wear, size = float(s["brightness"]), float(s["wear"]), float(s["body"])
    ornament = float(s["ornament"])

    def with_body(force: np.ndarray, spec: body.Body) -> np.ndarray:
        ir = body.impulse_response(spec, sr, seed=int(make.integers(1 << 30)), size=size)
        return body.resonate(force, ir)

    if kind in ("lute", "guitar", "harp", "bass"):
        if kind == "lute":
            spec = dict(brightness=0.45 + 0.35 * bright, decay=2.4, pick=0.13, hardness=0.75, planes=0.3,
                        course=1.5 + 6.0 * wear, spread=0.005, touch=0.3)
            box, opens, coupling = body.CITTERN, _open_strings(int(s["tonic"]), 45, 69), 0.0012
        elif kind == "guitar":
            spec = dict(brightness=0.45 + 0.35 * bright, decay=3.2, pick=0.22, hardness=0.7, planes=0.35,
                        touch=0.15, damp=0.05)
            capo = int(s["capo"])
            opens = [int(p) for p in s["tuning"]] if s.get("tuning") else [p + capo for p in (40, 45, 50, 55, 59, 64)]
            box, coupling = body.GUITAR, 0.001  # (tuning: an open tuning's strings, a session's DADGAD)
        elif kind == "harp":
            spec = dict(brightness=0.3 + 0.35 * bright, decay=4.5, pick=0.36, hardness=0.25, planes=0.4,
                        touch=0.25, damp=0.12)
            box, opens, coupling = body.HARP, _open_strings(int(s["tonic"]), 43, 81), 0.0018
        else:
            spec = dict(brightness=0.16 + 0.2 * bright, decay=1.7, pick=0.27, hardness=0.12, planes=0.25,
                        touch=0.7, damp=0.1)
            box, opens, coupling = body.BASS, [], 0.0
        # A string's own tuning is a few cents off, more on a worn instrument,
        # the same all song: the maker's (and the weather's) doing.
        offsets = make.normal(0.0, 0.5 + 4.0 * wear, 128)
        force = _strings(notes, sr, length, rng, spec, tuning=lambda n: offsets[int(round(n.pitch)) % 128])
        if opens:
            force = force + pluck.sympathetic(force, sr, opens, coupling=coupling, decay=3.0, brightness=0.3)
        return with_body(force, box)
    if kind == "fiddle":
        # a folk fiddler's vibrato is narrow, when there is one: 6 to 16 cents
        force = bowed.bow(notes, sr, length, rng, vibrato=6.0 + 10.0 * ornament, wear=wear, noise=0.3 + 0.8 * wear)
        force = sosfilt(butter(1, 60.0, btype="highpass", fs=sr, output="sos"), force)
        return with_body(force, body.FIDDLE)
    if kind == "whistle":
        return pipe.blow(notes, sr, length, rng, brightness=bright, wear=wear, vibrato=ornament)
    if kind == "drum":
        # a frame drum is tuned by warming the skin, not to the key: its maker's, somewhere near 80 Hz
        skin = 80.0 * 2.0 ** make.uniform(-0.25, 0.25) / size
        return drum.play(notes, sr, length, rng, pitch=skin, brightness=bright, wear=wear)
    if kind == "drone":
        tone = reed.drone(notes, sr, length, rng, brightness=bright, wear=wear)
        return with_body(tone, body.REED_BOX)
    raise ValueError(f"no such instrument: {kind}")


def render_part(name: str, notes: tuple[Note, ...], sr: int, length: int, settings: dict, seed: int,
                sound: dict | None = None) -> np.ndarray:
    """One instrument's stem: dry, stereo, `length` samples, at its level. sound: a person's sound for this
    player (songbird.sound: a patch, filter, kit, the pieces' character, a pan), or None for its own."""
    if name not in INSTRUMENTS:
        return render_other(name, notes, sr, length, settings, seed, sound)
    s = {**DEFAULTS, **settings}
    # Each part has its own performance randomness, and each instrument its own maker's quirks.
    index = INSTRUMENTS.index(name)
    rng = np.random.default_rng([seed, 17, index])
    make = np.random.default_rng([int(s["maker"]), 29, index])
    stem = _model(name, notes, sr, length, s, rng, make)
    position, width = PLACE[name]
    if sound and "pan" in sound:  # a person's place for it
        position = float(sound["pan"])
    out = place(stem, position, width, inplace=True)  # the model's own fresh stem
    del stem
    out *= LEVEL[name]  # the level and the part's gain in the lineup, each where it lies (the same products)
    out *= float(s[name])
    return out


# --- the registry -------------------------------------------------------------------------------


def stream(name: str) -> int:
    """A stable number for an instrument's own random streams (the eight keep their places 0..7)."""
    if name in INSTRUMENTS:
        return INSTRUMENTS.index(name)
    return 1000 + int.from_bytes(hashlib.sha256(f"instrument|{name}".encode()).digest()[:4], "little") % 1_000_000


@lru_cache(maxsize=1)
def registry() -> dict[str, tuple[dict, object]]:
    """Every instrument a module under songbird/synth/ provides: name -> (its SPEC entry, its module).
    A module is looked at only if its source names a SPEC and a render(), and imported in name order."""
    found: dict[str, tuple[dict, object]] = {}
    here = Path(__file__).parent
    for info in sorted(pkgutil.iter_modules([str(here)]), key=lambda m: m.name):
        if info.name in NOT_INSTRUMENTS or info.name.startswith("_"):
            continue
        text = (here / f"{info.name}.py").read_text(encoding="utf-8", errors="ignore") if (here / f"{info.name}.py").exists() else ""
        if "SPEC" not in text or "def render(" not in text:
            continue
        module = importlib.import_module(f"{__package__}.{info.name}")
        spec, render = getattr(module, "SPEC", None), getattr(module, "render", None)
        if not isinstance(spec, dict) or not callable(render):
            continue
        for name, entry in spec.items():
            if name not in INSTRUMENTS and name not in found:
                found[name] = (dict(entry), module)
    return found


# The styles' names for instruments whose modules were given other names: played by those modules.
ALIASES = {"vibes": "vibraphone", "glock": "glockenspiel", "musicbox": "music-box", "synthpad": "synth-pad",
           "synthbass": "synth-bass", "synthlead": "synth-solo", "arp": "synth-arp", "drummachine": "drums-808"}


def registered(name: str) -> tuple[str, tuple[dict, object] | None]:
    """The module that plays an instrument, by its own name or its alias: (the module's name for it,
    (SPEC entry, module)), or (name, None) while no module provides it."""
    found = registry().get(name)
    if found is None and name in ALIASES and ALIASES[name] in registry():
        return ALIASES[name], registry()[ALIASES[name]]
    return name, found


def spec(name: str) -> dict:
    """What the band knows of an instrument: family, register (None: unpitched), place, level, poly,
    about, and stand_in (the model playing it until a module provides it, or None)."""
    if name in INSTRUMENTS:
        family = {"lute": "plucked", "guitar": "plucked", "harp": "plucked", "bass": "bass", "fiddle": "bowed",
                  "whistle": "blown", "drum": "percussion", "drone": "reed"}[name]
        register = {"lute": (50, 84), "guitar": (40, 80), "harp": (28, 96), "bass": (28, 55), "fiddle": (55, 88),
                    "whistle": (62, 93), "drum": None, "drone": (36, 72)}[name]
        return dict(family=family, register=register, place=PLACE[name], level=LEVEL[name],
                    poly=name in ("guitar", "harp", "drone", "drum"), about=name, stand_in=None)
    _, found = registered(name)
    if found is not None:
        entry = found[0]
        register = entry.get("register")
        return dict(family=entry.get("family", "band"), register=tuple(register) if register else None,
                    place=tuple(entry.get("place", (0.0, 0.5))), level=float(entry.get("level", 0.15)),
                    poly=bool(entry.get("poly", True)), about=entry.get("about", name), stand_in=None,
                    articulations=dict(entry.get("articulations", {})))
    if name in KNOWN:
        family, register, where, level, poly, stand_in, about = KNOWN[name]
        return dict(family=family, register=register, place=where, level=level, poly=poly, about=about,
                    stand_in=stand_in)
    raise ValueError(f"no such instrument: {name}")


def known() -> tuple[str, ...]:
    """Every instrument name the band can play: the eight, then every other, by name."""
    return INSTRUMENTS + tuple(sorted(set(KNOWN) | set(registry()) - set(INSTRUMENTS)))


def render_other(name: str, notes: tuple[Note, ...], sr: int, length: int, settings: dict, seed: int,
                 sound: dict | None = None) -> np.ndarray:
    """A stem for an instrument beyond the eight: its module's sound, or its stand-in's, placed and
    levelled by its SPEC and scaled by its gain in the lineup (settings["gains"]). sound: a person's sound
    for this player (songbird.sound), or None for its own."""
    s = {**DEFAULTS, **settings}
    info = spec(name)
    index = stream(name)
    rng = np.random.default_rng([seed, 17, index])
    make = np.random.default_rng([int(s["maker"]), 29, index])
    own, found = registered(name)
    if sound:  # a person's patch, filter, pieces and kit (docs/SOUND-DESIGN.md)
        own, found, notes, s, info = voiced(own, found, notes, s, info, sound)
    if found is not None:
        y = np.asarray(found[1].render(own, notes, sr, length, rng, make, s), dtype=np.float64)
        y = y[:length] if len(y) >= length else np.pad(y, [(0, length - len(y))] + [(0, 0)] * (y.ndim - 1))
    else:
        kind = info["stand_in"]
        if kind == "drum":  # a frame drum takes the kit's strokes as near as it can
            notes = tuple(_as_drum(n) for n in notes)
        y = _model(kind, notes, sr, length, s, rng, make)
    position, width = info["place"]
    if sound and "pan" in sound:  # a person's place for it
        position = float(sound["pan"])
    gain = float((s.get("gains") or {}).get(name, 1.0))
    out = place(y, position, width)
    del y
    out *= info["level"]
    out *= gain
    return out


# --- a person's sound (docs/SOUND-DESIGN.md) ------------------------------------------------------------------
#
# A drum player's kit is the module that plays it; a drum machine's pattern on the acoustic kit, or a drummer's
# on a machine, has its strokes named as the other knows them (a stroke neither has is left out, or the nearest).

KITS = {"808": ("drums-808", None), "909": ("drums-909", None), "lofi": ("drums-808", "lofi"),
        "acoustic": ("kit", None)}
MACHINE_TO_KIT = {"clave": ("snare-cross", 1.0), "conga-hi": ("tom-hi", 0.8), "conga-mid": ("tom-mid", 0.8),
                  "conga-lo": ("tom-lo", 0.8), "maracas": ("hat", 0.5), "hat-pedal": ("hat-foot", 1.0),
                  "clap": ("snare", 0.9), "rim": ("snare-rim", 1.0), "cowbell": ("ride-bell", 1.0)}
KIT_TO_MACHINE = {"hat-foot": ("hat-pedal", 1.0), "snare-ghost": ("snare", 0.4), "snare-rim": ("rim", 1.0),
                  "snare-cross": ("rim", 0.8), "snare-roll": ("snare", 0.8), "brush-tap": ("snare", 0.6),
                  "brush-sweep": (None, 0.0), "ride-bell": ("cowbell", 0.8), "ride-crash": ("crash", 1.0),
                  "ride-roll": ("ride", 0.8), "crash-choke": ("crash", 1.0), "crash-roll": ("crash", 0.8),
                  "hat-half": ("hat-open", 1.0), "kick-dead": ("kick", 1.0), "tom-hi-roll": ("tom-hi", 0.8),
                  "tom-mid-roll": ("tom-mid", 0.8), "tom-lo-roll": ("tom-lo", 0.8)}
MACHINE_KNOBS = ("kick", "snare", "hat")  # a drum machine's pieces' character
SYNTH_KNOBS = ("patch", "cutoff", "resonance", "envelope")


def _restroke(notes, table: dict) -> tuple[Note, ...]:
    from dataclasses import replace

    out = []
    for n in notes:
        art = (n.art or "").split(":")[0].strip().lower()
        if art in table:
            to, vel = table[art]
            if to is None:
                continue
            n = replace(n, art=to, vel=n.vel * vel)
        out.append(n)
    return tuple(out)


def voiced(own: str, found, notes, s: dict, info: dict, sound: dict):
    """A player's module, notes, settings and SPEC facts with a person's sound: a synth's patch and filter (and
    a drum machine's pieces) into its settings; a kit's module in place of its own, its strokes renamed, at
    that module's level (its place stays the player's)."""
    s = {**s, **{k: sound[k] for k in SYNTH_KNOBS + MACHINE_KNOBS if k in sound}}
    kit = sound.get("kit")
    if kit in KITS:
        module, flavour = KITS[kit]
        if flavour:
            s["kit"] = flavour
        if module != own and module in registry():
            table = MACHINE_TO_KIT if module == "kit" else KIT_TO_MACHINE if own == "kit" else {}
            notes = _restroke(notes, table)
            own, found = module, registry()[module]
            info = {**info, "level": float(found[0].get("level", info["level"]))}
    return own, found, notes, s, info


def _as_drum(note: Note) -> Note:
    from dataclasses import replace

    return replace(note, art=DRUM_STROKES.get(note.art, "tip"), vel=note.vel * QUIET.get(note.art, 1.0))


def band_parts(score: Score, sr: int, seed: int) -> list[tuple[str, Callable[[], np.ndarray]]]:
    """The band's stems to be made, as (name, a function that makes it): every instrument that plays in the
    score, the eight in their order, then any other by name. Each part has its own random streams, so they
    can be made in any order, or at once."""
    length = int(np.ceil(score.duration * sr))
    # a low harp string can still be ringing when the song's last ring is over: let every stem end softly
    fade = min(length, int(0.3 * sr))
    ending = np.ones(length)
    ending[length - fade:] = 0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, fade))
    ending = ending[length - fade:].copy()  # the stem's last `fade` samples: before them it multiplies by 1 (exact)
    others = sorted({n.part for n in score.notes} - set(INSTRUMENTS) - {"voice", "chop"}
                    - {p for p in {n.part for n in score.notes} if p.startswith("choir")})
    design = getattr(score, "sound", None) or {}  # a person's sound design (songbird.sound), if any
    players = design.get("players") or {}

    def make(name: str, notes) -> Callable[[], np.ndarray]:
        def part() -> np.ndarray:
            y = render_part(name, notes, sr, length, score.band, seed, players.get(name))
            if y.shape == (length, 2) and y.dtype == np.float64:
                if fade:  # where it lies: the same products (every sample before the fade times 1, left as it is)
                    y[length - fade:] *= ending[:, None]
                return y
            whole = np.ones(length)
            whole[length - fade:] = ending
            return y * whole[:, None]
        return part

    jobs = [(name, make(name, notes)) for name in INSTRUMENTS + tuple(others) if (notes := score.part(name))]
    if design.get("transitions"):  # risers, impacts, downlifters: a stem of their own (synth.sweeps), last
        from . import sweeps

        def fx() -> np.ndarray:
            y = sweeps.make_fx(design["transitions"], sr, length, seed)
            y = np.zeros((length, 2)) if y is None else y
            if fade:
                y[length - fade:] *= ending[:, None]
            return y
        if any(t["kind"] not in sweeps.SWEEPS for t in design["transitions"]):
            jobs.append(("fx", fx))
    return jobs
