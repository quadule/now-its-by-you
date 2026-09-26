"""The band's wider palette: every new instrument by name, its SPEC and how to render it.

The keyboards, mallets, synthesizers, the chip and the drum machine live in
their own modules (piano, epiano, organ, mallets, analog, chip,
drummachine), each with a SPEC and a render() (docs/INSTRUMENTS.md). This
gathers them so the band can reach for any of them by name:

    SPEC["vibraphone"]   what it is, its compass, place, level, articulations
    render(name, ...)    its dry sound, as its module makes it
    stem(name, ...)      that sound placed and at its level, as the band's stems are

A stem made by stem() sits at the loudness its SPEC's role was levelled to
(a comping part at velocity 0.6 where the guitar's strum sits in H's first
refrain, and so on), times `gain` (the band's balance for it, 1 as levelled).
"""

from __future__ import annotations

import numpy as np

from . import analog, chip, drummachine, epiano, mallets, organ, piano
from .instruments import place

MODULES = (piano, epiano, organ, mallets, analog, chip, drummachine)
SPEC = {name: spec for module in MODULES for name, spec in module.SPEC.items()}
OWNER = {name: module for module in MODULES for name in module.SPEC}


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """An instrument's part, dry, mono or stereo, before placement and level."""
    if name not in OWNER:
        raise ValueError(f"no such instrument: {name}")
    return OWNER[name].render(name, tuple(notes), sr, length, rng, make, settings)


def stem(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
         settings: dict, gain: float = 1.0) -> np.ndarray:
    """An instrument's stem: stereo, `length` samples, placed and at its SPEC level times `gain`."""
    position, width = SPEC[name]["place"]
    return place(render(name, notes, sr, length, rng, make, settings), position, width) * SPEC[name]["level"] * gain
