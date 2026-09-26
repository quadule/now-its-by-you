"""The band's instruments: how each instrument's notes in a score become a stem.

Eight instruments, each a physical or physically inspired model (see pluck,
bowed, pipe, drum and reed) played through its own body, and delivered dry,
panned and at a level that sits with the others and under the singer:

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
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt

from ..score import Note, Score
from ..theory import midi_to_hz
from . import body, bowed, drum, pipe, pluck, reed

INSTRUMENTS = ("lute", "guitar", "harp", "bass", "fiddle", "whistle", "drum", "drone")

# Where each sits (-1 left, 1 right) and how wide its body sounds; as a small
# band stands: bass and drum in the middle, the chordal instruments either
# side, the two melody instruments further out, opposite each other.
PLACE = {
    "lute": (-0.35, 0.45),
    "guitar": (0.3, 0.6),
    "harp": (-0.2, 0.7),
    "bass": (0.0, 0.15),
    "fiddle": (0.5, 0.4),
    "whistle": (-0.5, 0.0),
    "drum": (0.12, 0.0),
    "drone": (0.0, 0.9),
}

# Stem gain for each instrument at balance 1: set so that, played as the
# band part arranges them, each sits where a folk band's players would under
# a singer (the voice stem stays the loudest thing in the song).
LEVEL = {
    "lute": 0.5,
    "guitar": 0.14,
    "harp": 0.13,
    "bass": 0.23,
    "fiddle": 0.2,
    "whistle": 0.15,
    "drum": 1.0,
    "drone": 0.09,
}

DEFAULTS = dict(brightness=0.5, wear=0.25, body=1.0, maker=0, tonic=62, capo=0,
                **{name: 1.0 for name in INSTRUMENTS})


def place(y: np.ndarray, position: float, width: float) -> np.ndarray:
    """A mono or stereo signal to stereo at `position`, keeping `width` of a
    stereo source's side signal (0 collapses it to its middle)."""
    theta = (position + 1.0) * np.pi / 4.0
    if y.ndim == 1:
        return np.stack([y * np.cos(theta), y * np.sin(theta)], axis=1) * np.sqrt(2.0)
    mid = 0.5 * (y[:, 0] + y[:, 1])
    side = 0.5 * (y[:, 0] - y[:, 1]) * width
    return np.stack([mid * np.cos(theta) * np.sqrt(2.0) + side, mid * np.sin(theta) * np.sqrt(2.0) - side], axis=1)


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


def render_part(name: str, notes: tuple[Note, ...], sr: int, length: int, settings: dict, seed: int) -> np.ndarray:
    """One instrument's stem: dry, stereo, `length` samples, at its level."""
    s = {**DEFAULTS, **settings}
    bright, wear, size, maker = float(s["brightness"]), float(s["wear"]), float(s["body"]), int(s["maker"])
    # Each part has its own performance randomness, and each instrument its own maker's quirks.
    index = INSTRUMENTS.index(name)
    rng = np.random.default_rng([seed, 17, index])
    make = np.random.default_rng([maker, 29, index])

    def with_body(force: np.ndarray, spec: body.Body) -> np.ndarray:
        ir = body.impulse_response(spec, sr, seed=int(make.integers(1 << 30)), size=size)
        return body.resonate(force, ir)

    if name in ("lute", "guitar", "harp", "bass"):
        if name == "lute":
            spec = dict(brightness=0.45 + 0.35 * bright, decay=2.4, pick=0.13, hardness=0.75, planes=0.3,
                        course=1.5 + 6.0 * wear, spread=0.005, touch=0.3)
            box, opens, coupling = body.CITTERN, _open_strings(int(s["tonic"]), 45, 69), 0.0012
        elif name == "guitar":
            spec = dict(brightness=0.35 + 0.35 * bright, decay=3.2, pick=0.22, hardness=0.7, planes=0.35,
                        touch=0.15, damp=0.05)
            capo = int(s["capo"])
            box, opens, coupling = body.GUITAR, [p + capo for p in (40, 45, 50, 55, 59, 64)], 0.001
        elif name == "harp":
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
        stem = with_body(force, box)
    elif name == "fiddle":
        force = bowed.bow(notes, sr, length, rng, vibrato=16.0 + 8.0 * bright, wear=wear, noise=0.3 + 0.8 * wear)
        force = sosfilt(butter(1, 60.0, btype="highpass", fs=sr, output="sos"), force)
        stem = with_body(force, body.FIDDLE)
    elif name == "whistle":
        stem = pipe.blow(notes, sr, length, rng, brightness=bright, wear=wear)
    elif name == "drum":
        stem = drum.play(notes, sr, length, rng, pitch=float(s.get("drum_hz", 82.0)) / size, brightness=bright,
                         wear=wear)
    elif name == "drone":
        tone = reed.drone(notes, sr, length, rng, brightness=bright, wear=wear)
        stem = with_body(tone, body.REED_BOX)
    else:
        raise ValueError(f"no such instrument: {name}")
    position, width = PLACE[name]
    return place(stem, position, width) * LEVEL[name] * float(s[name])


def render_band(score: Score, sr: int, seed: int) -> dict[str, np.ndarray]:
    """A stem for every instrument that plays in the score."""
    length = int(np.ceil(score.duration * sr))
    # a low harp string can still be ringing when the song's last ring is over: let every stem end softly
    fade = min(length, int(0.3 * sr))
    ending = np.ones(length)
    ending[length - fade:] = 0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, fade))
    stems = {}
    for name in INSTRUMENTS:
        notes = score.part(name)
        if notes:
            stems[name] = render_part(name, notes, sr, length, score.band, seed) * ending[:, None]
    return stems
