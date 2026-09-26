"""Shared by the second set of instruments' tests: how loud a part sits once placed and levelled.

The targets are today's stems in H (songs/h-now-its-by-you.json, default params), placed and at their
LEVEL, integrated loudness (BS.1770) over the passage: the guitar's strum in the first refrain (comping),
the whistle stating the tune in the intro (a lead), the frame drum (percussion: -31.5 light in the first
refrain to -28.4 full in the last) and the upright bass in the first refrain.
"""

from __future__ import annotations

import hashlib

import numpy as np

from songbird.synth import instruments, master

SR = 44100
TARGETS = {"comping": -23.7, "lead": -20.7, "percussion": -29.5, "bass": -24.0}
SETTINGS = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0, maker=0, tonic=62, capo=0)


def streams(name: str, seed: int = 0, maker: int = 0) -> tuple[np.random.Generator, np.random.Generator]:
    """A part's performance stream and its maker's stream, as the band's registry gives them (instruments.stream)."""
    k = int.from_bytes(hashlib.sha256(f"instrument|{name}".encode()).digest()[:4], "little") % 1_000_000
    return np.random.default_rng([seed, 17, 1000 + k]), np.random.default_rng([maker, 29, 1000 + k])


def placed(module, name: str, notes, length: int, *, seed: int = 0, maker: int = 0, **settings) -> np.ndarray:
    """A part rendered by module.render, then placed and levelled as its SPEC says: the stem the band would mix."""
    rng, make = streams(name, seed, maker)
    y = module.render(name, tuple(notes), SR, length, rng, make, {**SETTINGS, "maker": maker, **settings})
    position, width = module.SPEC[name]["place"]
    return instruments.place(y, position, width) * module.SPEC[name]["level"]


def loudness(module, name: str, notes, length: int, **kwargs) -> float:
    return master.loudness(placed(module, name, notes, length, **kwargs), SR)
