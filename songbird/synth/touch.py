"""Touch: how hard a note is played becomes how loud it is, the same way for every new instrument.

A player's velocity (0..1) is a gesture, not a gain. Loudness follows it as a
power law, amplitude = vel^γ, with γ set by the instrument's dynamic span:
how many decibels lie between a note at 0.2 (pp) and one at 1 (ff). A piano
spans about 22 dB of that, a vibraphone 20, a drum machine's voices 18
(its accent adds more on top); an organ has none (its velocity is the swell
pedal instead) and a chip only its sixteen volume steps. Timbre (a harder
hammer, a brighter tine, more bark) is each model's own business: it should
come from the physics, not from this.
"""

from __future__ import annotations

import numpy as np

LOG5 = float(np.log10(5.0))


def gain(vel: float, span: float = 22.0) -> float:
    """Amplitude of a note at velocity vel for an instrument whose pp (0.2) sits `span` dB under its ff (1)."""
    return float(max(vel, 0.02) ** (span / (20.0 * LOG5)))


def exponent(span: float) -> float:
    """The power law's exponent γ for a dynamic span in dB (22 dB: 1.57)."""
    return span / (20.0 * LOG5)
