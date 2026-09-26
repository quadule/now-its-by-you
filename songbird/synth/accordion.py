"""The accordion and the concertina: free reeds in a box, a bellows and two hands, played melodically.

Both are reed.py's free reeds (a brass tongue chopping the air: rich
harmonics, the spectrum's slope rising with the pressure, reed.tables
cross-faded by reed._read_mix), with what the bellows and the keys do:

- The bellows. One bellows drives every reed that sounds, so a note starts
  and the pressure follows the playing (the player's arm, smoothed over 40
  ms), the louder notes pressing harder, and brighter. The bellows open for
  a few seconds and close for a few (an accordion's travel lasts 3 to 6 s, a
  concertina's 1 to 2.5), reversing at a note's start: the pressure dips to
  a fifth for 40 to 70 ms, and the other reed of each pair takes over (a
  push reed and a pull reed are separate tongues, a cent or two apart and a
  shade different in tone). "shake" is the bellows shaken: reversals 5 to 8
  times a second.
- The keys. A pallet lifts off its hole with a small click, and the reed
  speaks in 20 to 60 ms (the bass reeds, long and heavy, in 80); when the
  pallet shuts the reed stops in a few tens of ms, with a softer click.
- The reeds. An accordion's treble sounds each note on several reeds: its
  middle reeds (8') are tuned as the maker tuned them: dry (two a few cents
  apart), wet (8 to 15 cents apart, beating) or musette (three: one true,
  one 15 to 25 cents sharp, one as flat); the player's register sounds one
  of them played plain (ornament under 0.3), two by default, all of them
  much ornamented (0.7 and up). Brightness brings in the bassoon reed an octave down
  (16') when dark and the piccolo an octave up (4') when bright, levelled so
  a register changes the colour more than the loudness. The left hand's
  Stradella buttons: a bass sounds its note's pitch class on three reeds an
  octave apart, all within the same octave whatever was written (E to D#);
  a chord button's notes are folded into F#3 to F4 with an octave above. The
  concertina has one reed a note, smaller, brighter and quicker.
- The box. The reed blocks, the box and the grille (body.ACCORDION); the
  concertina's hexagonal ends and fretwork (body.CONCERTINA). The treble
  side sits a little left, the bass side right.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit
from scipy.ndimage import maximum_filter1d
from scipy.signal import butter, oaconvolve, sosfilt

from ..theory import midi_to_hz
from . import body, reed

ARTICULATIONS = {
    "": "a key (below the treble keyboard, F3, a left-hand bass button); the bellows as they go",
    "slur": "legato: the key goes down as the last comes up, no new pressure",
    "bass": "a left-hand Stradella bass button: the note's pitch class on three reeds an octave apart (E to D#)",
    "chord": "a left-hand chord button's note: folded into F#3-F4, with its octave",
    "shake": "bellows shake: the bellows reversed 5 to 8 times a second through the note",
    "swell": "the bellows pressed harder through the note's middle",
}

SPEC = {
    "accordion": dict(
        family="reed", role="comping", register=(41, 93), place=(-0.25, 0.8), level=0.1, poly=True,
        articulations=ARTICULATIONS,
        about="a piano accordion: treble F3-A6 on the maker's middle reeds (dry, wet or musette) with the bassoon "
              "(dark) and piccolo (bright) ranks; notes below F3, and 'bass' and 'chord', on the Stradella buttons",
    ),
    "concertina": dict(
        family="reed", role="comping", register=(48, 96), place=(-0.25, 0.6), level=0.1, poly=True,
        articulations=ARTICULATIONS,
        about="a concertina: one reed a note, small, bright and quick; its bellows reverse every second or two",
    ),
}


@dataclass(frozen=True)
class Box:
    """How one kind of squeezebox is built and played."""

    treble: tuple[int, int]  # the right hand's keys, MIDI
    speak: tuple[float, float]  # a reed's build-up time constant (s): the highest reeds, the lowest treble reeds
    travel: tuple[float, float]  # seconds the bellows run one way, at the least and most
    slopes: tuple[float, float]  # harmonic k's amplitude as k**-slope at a light and a hard pressure
    box: body.Body


ACCORDION = Box(treble=(53, 93), speak=(0.007, 0.02), travel=(3.0, 6.0), slopes=(1.55, 0.95), box=body.ACCORDION)
CONCERTINA = Box(treble=(48, 96), speak=(0.005, 0.012), travel=(1.0, 2.5), slopes=(1.35, 0.8), box=body.CONCERTINA)
BASS_SPEAK = 0.027  # the Stradella bass reeds, long and heavy: speaking in about 80 ms
BASS_FOLD, CHORD_FOLD = 40, 54  # the octave a bass button's (E2-D#3) and a chord button's (F#3-F4) notes sound in
CLICK = 0.02  # a pallet's click against the note
DIP = 0.25  # the pressure at the bottom of a bellows reversal


def _fold(pitch: float, low: int) -> float:
    return low + (pitch - low) % 12.0


def _voices(note, box: Box, kind: str, make: dict, bright: float) -> list[tuple[float, float, str]]:
    """The reeds a note sounds on: (pitch with its detune, gain, side "treble" or "bass")."""
    art = note.art
    if kind == "concertina":
        pitch = note.pitch
        while pitch < box.treble[0]:
            pitch += 12.0
        while pitch > box.treble[1]:
            pitch -= 12.0
        return [(pitch, 1.0, "treble")]
    if art == "bass" or (art != "chord" and note.pitch < box.treble[0]):
        root = _fold(note.pitch, BASS_FOLD)
        return [(root - 12.0, 0.7, "bass"), (root, 1.0, "bass"), (root + 12.0, 0.3 + 0.3 * bright, "bass")]
    if art == "chord":
        p = _fold(note.pitch, CHORD_FOLD)
        return [(p, 0.55, "bass"), (p + 12.0, 0.25, "bass")]
    pitch = note.pitch
    while pitch > box.treble[1]:
        pitch -= 12.0
    # the middle reeds (the maker's), and the bassoon and piccolo ranks as brightness asks, levelled together
    ranks = [(pitch + c / 100.0, 1.0) for c in make["middle"]]
    low, high = float(np.clip(0.9 - 1.8 * bright, 0.0, 0.8)), float(np.clip(1.8 * bright - 0.9, 0.0, 0.6))
    if low > 0:
        ranks.append((pitch - 12.0 + make["low"] / 100.0, low))
    if high > 0:
        ranks.append((pitch + 12.0 + make["high"] / 100.0, high))
    total = np.sqrt(sum(g * g for _, g in ranks))
    return [(p, g / total * np.sqrt(len(make["middle"])) ** 0.5, "treble") for p, g in ranks]


@njit(cache=True)
def _arm(x, up, down):
    """The player's arm on the bellows: pressure follows the playing, quickly as it rises, slowly as it eases."""
    y = np.zeros(x.shape[0])
    v = 0.0
    for i in range(x.shape[0]):
        a = up if x[i] > v else down
        v = a * v + (1.0 - a) * x[i]
        y[i] = v
    return y


def _bellows(notes, sr: int, length: int, box: Box, rng: np.random.Generator):
    """The bellows over the part: pressure (0..1, following the loudest sounding note, smoothed like an arm, with
    the reversals' dips) and the direction (+1 push, -1 pull), and the samples where it reverses."""
    press = np.zeros(length)
    for n in notes:
        i0, i1 = int(round(n.start * sr)), min(length, int(round((n.start + n.dur) * sr)))
        if i1 > i0:
            v = float(np.clip(n.vel, 0.0, 1.0))
            if n.art == "swell":
                v = v * (0.75 + 0.35 * np.sin(np.pi * np.linspace(0.0, 1.0, i1 - i0)))
            press[i0:i1] = np.maximum(press[i0:i1], v)
    hold = int(0.03 * sr)
    held = maximum_filter1d(press, hold, origin=(hold - 1) // 2)  # the last 30 ms: a gap that short isn't a lift
    press = _arm(held, float(np.exp(-1.0 / (0.008 * sr))), float(np.exp(-1.0 / (0.06 * sr))))
    # reversals: at a note's start once the bellows have run far enough; a shaken note reverses 5-8 times a second
    turns = []
    since = min(n.start for n in notes)
    travel = rng.uniform(*box.travel)
    for n in sorted(notes, key=lambda n: n.start):
        i0 = int(round(n.start * sr))
        if i0 >= length:
            break
        if n.art == "shake":
            rate = rng.uniform(5.0, 8.0)  # reversals a second: the pulse the shake is heard as
            k = 1
            while n.start + k / rate < n.start + n.dur - 0.02:
                turns.append(int(round((n.start + k / rate) * sr)))
                k += 1
            since = n.start + n.dur
            continue
        if n.start - since > travel:
            turns.append(i0)
            since = n.start
            travel = rng.uniform(*box.travel)
    turns = sorted(set(t for t in turns if 0 < t < length))
    direction = np.ones(length)
    sign = 1.0
    last = 0
    for t in turns:
        direction[last:t] = sign
        sign = -sign
        last = t
    direction[last:] = sign
    dip = np.ones(length)
    for t in turns:
        w = int(rng.uniform(0.04, 0.07) * sr)
        lo, hi = max(0, t - w // 3), min(length, t + w)
        shape = 1.0 - (1.0 - DIP) * np.sin(np.pi * np.linspace(0.0, 1.0, hi - lo)) ** 2
        dip[lo:hi] = np.minimum(dip[lo:hi], shape)
    return press * dip, direction, turns


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """The instrument's dry stereo stem, `length` samples (before its place and level)."""
    s = {"brightness": 0.5, "wear": 0.25, "ornament": 0.5, "body": 1.0, **settings}
    bright, wear = float(s["brightness"]), float(s["wear"])
    box = CONCERTINA if name == "concertina" else ACCORDION
    # the maker's instrument, drawn in a fixed order: the middle reeds' tuning (dry, wet or musette), the other
    # ranks' and the pull reeds' own offsets, the two sides' boxes
    style = int(make.integers(3))
    spread = 1.0 + 3.0 * wear
    if style == 0:
        d = make.uniform(1.0, 5.0)
        middle = [-d / 2.0, d / 2.0]
    elif style == 1:
        middle = [0.0, float(make.uniform(8.0, 15.0))]
    else:
        middle = [0.0, float(make.uniform(15.0, 25.0)), -float(make.uniform(15.0, 25.0))]
    quirks = dict(middle=[m + float(make.normal(0.0, 0.3 * spread)) for m in middle],
                  low=float(make.normal(0.0, spread)), high=float(make.normal(0.0, spread)))
    pull = float(make.normal(0.0, 0.7 * spread))  # the pull reeds against the push reeds, cents
    seeds = [int(make.integers(1 << 30)) for _ in range(2)]
    # the player's register: plain, one true middle reed (clarinet); by default two (violin: dry or wet as made);
    # much ornamented, all three of a musette box
    ornament = float(s["ornament"])
    sounding = 1 + int(ornament >= 0.3) + int(ornament >= 0.7)
    quirks["middle"] = quirks["middle"][:sounding]
    if box is CONCERTINA:
        quirks["middle"] = [0.0]
    notes = sorted((n for n in notes if n.start * sr < length and n.dur > 0), key=lambda n: n.start)
    out = {"treble": np.zeros(length), "bass": np.zeros(length)}
    if not notes:
        return np.zeros((length, 2))
    pressure, direction, turns = _bellows(notes, sr, length, box, rng)
    turn_at = np.array(turns + [length], dtype=np.int64)
    cache: dict = {}
    clicks = np.zeros(length)
    click_sos = butter(2, (300.0, 3500.0), btype="bandpass", fs=sr, output="sos")
    for k, note in enumerate(notes):
        i0 = int(round(note.start * sr))
        m = max(1, min(length - i0, int(round(note.dur * sr))))
        voices = _voices(note, box, name, quirks, bright)
        is_bass = voices[0][2] == "bass" and note.art != "chord"
        speak = BASS_SPEAK if is_bass else box.speak[0] + (box.speak[1] - box.speak[0]) * float(
            np.clip((72.0 - voices[0][0]) / 19.0, 0.0, 1.0))
        stop = 1.5 * speak
        tail = min(length - i0 - m, int(4.0 * stop * sr))
        n = m + max(0, tail)
        t = np.arange(n) / sr
        key = np.ones(n)
        carried = note.art == "slur" and k > 0 and note.start - (notes[k - 1].start + notes[k - 1].dur) < 0.02
        key *= 1.0 - np.exp(-t / (0.4 * speak if carried else speak))
        key[m:] *= np.exp(-np.arange(n - m) / (stop * sr))
        p = pressure[i0: i0 + n]
        mix = np.clip(0.25 + 0.5 * bright + 1.2 * (p - 0.6), 0.0, 1.0)
        # the note's reeds, the push reed or the pull reed as the bellows go
        pieces = np.concatenate([[0], turn_at[(turn_at > i0) & (turn_at < i0 + n)] - i0, [n]])
        for pitch, gain, side in voices:
            for a, b in zip(pieces[:-1], pieces[1:]):
                if b <= a:
                    continue
                pulling = direction[i0 + a] < 0
                ck = (round(pitch, 3), pulling, name)
                if ck not in cache:
                    cache[ck] = reed.tables(midi_to_hz(pitch), sr, rng, box.slopes, even=0.75 if pulling else 0.85)
                dark, brightw = cache[ck]
                f = midi_to_hz(pitch + (pull / 100.0 if pulling else 0.0))
                reed._read_mix(dark, brightw, np.full(b - a, f / sr), gain * key[a:b] * p[a:b], mix[a:b],
                               out[side], i0 + a, rng.random())
        if not carried:  # the pallet lifts: a small click, bigger on an old box; and shuts again, softer
            c = min(n, int(0.006 * sr))
            burst = sosfilt(click_sos, rng.standard_normal(c + 32))[32:] * np.exp(-np.arange(c) / (0.0012 * sr))
            clicks[i0: i0 + c] += burst * CLICK * (0.5 + note.vel) * (1.0 + 2.0 * wear)
            j = i0 + m
            if j + c < length:
                clicks[j: j + c] += 0.5 * burst * CLICK * (1.0 + 2.0 * wear)
    # air past the reeds and pallets, more on an old box
    hiss = sosfilt(butter(2, (400.0, 4000.0), btype="bandpass", fs=sr, output="sos"), rng.standard_normal(length))
    out["treble"] += clicks + hiss * pressure * 0.004 * (1.0 + 3.0 * wear)
    size = float(s["body"])
    stereo = np.zeros((length, 2))
    for side, position, seed in (("treble", -0.3, seeds[0]), ("bass", 0.3, seeds[1])):
        if not out[side].any():
            continue
        ir = body.impulse_response(box.box, sr, seed=seed, size=size, channels=1)[:, 0]
        y = oaconvolve(out[side], ir)[:length]
        y = sosfilt(butter(1, 20.0, btype="highpass", fs=sr, output="sos"), y)  # a reed's pulses carry DC
        theta = (position + 1.0) * np.pi / 4.0
        stereo[:, 0] += y * np.cos(theta) * np.sqrt(2.0)
        stereo[:, 1] += y * np.sin(theta) * np.sqrt(2.0)
    return stereo
