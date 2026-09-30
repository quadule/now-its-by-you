"""Transitions: risers, downlifters and impacts, and the band's filter sweep into a section (docs/SOUND-DESIGN.md).

What a producer puts at a section boundary so a build and a drop sound like one: a riser over the bars
before (noise through a band-pass rising from 250 Hz to 9 kHz and swelling 18 dB, a sine climbing three
octaves under it, wider as it rises, stopping at the downbeat); an impact on the downbeat (a sine falling
from 110 to 42 Hz in a quarter second and ringing a second and a half, over a burst of dark noise; where a
kick lands with it, its boom high-passed and lower, so the two don't fight); a downlifter over the bars
after (noise through a band-pass falling from 6 kHz to 200 Hz, fading); and a filter sweep on the band over
the bars before (a high-pass rising from 20 Hz to 1.5 kHz, or a low-pass falling from 16 kHz to 350 Hz), and
a stop (the band silent for the last beats before the downbeat, the singer and the transitions going on),
which the mix applies to the band's bus.

They come from the score's `sound["transitions"]` (songbird.sound writes them): each its kind, its span in
seconds, its level and a key. Each is made over its whole span from its own noise stream (the render's seed
and its key), and only what falls inside the render is kept, so a section's preview that begins in the middle
of a riser hears it as the whole song does. Everything here is numpy and scipy: noise, a biquad whose
coefficients move every BLOCK samples with its state carried, cumulative phases; no compiled kernel. A snare
roll with no drum player in the band is played here on a 909.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt

BLOCK = 64  # samples between a moving filter's coefficients
LEVEL = 0.2  # the fx stem's level: a riser's last bar, an impact's first half second about as loud as the band
RISER = (250.0, 9000.0, 18.0)  # Hz its band-pass rises from and to, dB it swells by
DOWN = (6000.0, 200.0, 24.0)  # Hz the downlifter's band-pass falls from and to, dB it fades by
IMPACT = (110.0, 42.0, 0.25, 1.5)  # Hz the boom falls from and to, over s, its T60
ON_A_KICK = (90.0, -6.0)  # an impact's boom where a kick lands with it: high-passed here (Hz), this much lower (dB)
SWEEP_HP = (20.0, 1500.0)
SWEEP_LP = (16000.0, 350.0)
SWEEP_OPEN = (350.0, 16000.0)  # a low-pass opening: a filtered intro, a house breakdown building to its drop
SWEEP_Q = 0.707 + 0.3  # the sweep's resonance: a little bite at the moving corner
FADE = 0.003  # s: every sound starts and stops over this much, and a sweep hands back to the dry band
SWEEPS = ("sweep-hp", "sweep-lp", "stop", "sweep-open")  # what the mix does to the band's bus, not a sound here


def _biquad(kind: str, f: float, q: float, sr: float) -> np.ndarray:
    """One RBJ biquad section (b0 b1 b2 1 a1 a2): "lp", "hp" or "bp" (constant 0 dB peak)."""
    f = min(max(f, 10.0), 0.45 * sr)
    w = 2.0 * np.pi * f / sr
    cw, alpha = np.cos(w), np.sin(w) / (2.0 * q)
    if kind == "lp":
        b = ((1 - cw) / 2, 1 - cw, (1 - cw) / 2)
    elif kind == "hp":
        b = ((1 + cw) / 2, -(1 + cw), (1 + cw) / 2)
    else:
        b = (alpha, 0.0, -alpha)
    a0 = 1 + alpha
    return np.array([[b[0] / a0, b[1] / a0, b[2] / a0, 1.0, -2 * cw / a0, (1 - alpha) / a0]])


def moving(x: np.ndarray, kind: str, corner, q: float, sr: float) -> np.ndarray:
    """x (samples, or samples by channels) through a biquad whose corner is corner(i) Hz at sample i of x, set
    every BLOCK samples at the block's middle, its state carried from block to block."""
    n = len(x)
    y = np.empty(x.shape)
    zi = np.zeros((1, 2) + x.shape[1:])
    for a in range(0, n, BLOCK):
        b = min(n, a + BLOCK)
        y[a:b], zi = sosfilt(_biquad(kind, float(corner((a + b) / 2.0)), q, sr), x[a:b], axis=0, zi=zi)
    return y


def _ends(y: np.ndarray, sr: int) -> np.ndarray:
    k = min(len(y) // 2, int(FADE * sr))
    if k:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, k))
        y[:k] *= ramp[:, None]
        y[len(y) - k:] *= ramp[::-1][:, None]
    return y


def _stereo(rng: np.random.Generator, n: int, width) -> np.ndarray:
    """Two channels of white noise, their shared part and their own part mixed by width (0 mono, 1 apart)."""
    common, apart = rng.standard_normal(n), rng.standard_normal(n)
    w = np.asarray(width, dtype=np.float64)
    return np.stack([common * (1.0 - 0.5 * w) + apart * w, common * (1.0 - 0.5 * w) - apart * w], axis=1)


def riser(n: int, sr: int, rng: np.random.Generator) -> np.ndarray:
    """The riser over n samples: rising, swelling, widening, gone at the downbeat."""
    x = np.arange(n) / max(n, 1)
    lo, hi, swell = RISER
    noise = moving(_stereo(rng, n, 0.2 + 0.6 * x), "bp", lambda i: lo * (hi / lo) ** ((i / max(n, 1)) ** 1.3), 1.4,
                   sr)
    tone = 0.25 * np.sin(2.0 * np.pi * np.cumsum(200.0 * 8.0 ** x) / sr)  # the sine under it: three octaves up
    y = noise + tone[:, None]
    y *= (10.0 ** (swell * (x ** 1.5 - 1.0) / 20.0))[:, None]
    return _ends(y, sr)


def down(n: int, sr: int, rng: np.random.Generator) -> np.ndarray:
    """The downlifter over n samples: falling and fading."""
    x = np.arange(n) / max(n, 1)
    hi, lo, fade = DOWN
    y = moving(_stereo(rng, n, 0.6 - 0.4 * x), "bp", lambda i: hi * (lo / hi) ** ((i / max(n, 1)) ** 0.7), 1.4, sr)
    y *= (10.0 ** (-fade * x / 20.0))[:, None]
    return _ends(y, sr)


def impact(sr: int, rng: np.random.Generator, kick: bool = False) -> np.ndarray:
    """The impact: a boom falling in pitch and ringing, over a burst of dark noise; on a kick, the boom's
    low end left to the kick."""
    top, bottom, fall, t60 = IMPACT
    n = int((t60 + 0.1) * sr)
    t = np.arange(n) / sr
    f = bottom + (top - bottom) * np.exp(-t / (fall / 3.0))
    boom = np.sin(2.0 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 6.907755278982137 / t60) * 1.2
    if kick:
        boom = sosfilt(_biquad("hp", ON_A_KICK[0], 0.707, sr), boom) * 10.0 ** (ON_A_KICK[1] / 20.0)
    burst = moving(_stereo(rng, n, 0.5), "lp", lambda i: 4000.0 * (300.0 / 4000.0) ** (i / n), 0.707, sr)
    burst *= (0.5 * np.exp(-t / 0.08))[:, None]
    return _ends(boom[:, None] + burst, sr)


def make_fx(transitions, sr: int, length: int, seed: int) -> np.ndarray | None:
    """The fx stem: every riser, downlifter, impact and drummerless roll of the score's transitions, stereo,
    `length` samples, at LEVEL and each one's level; None when there are none (a sweep is the mix's)."""
    out = None
    hits = []
    for t in transitions:
        kind = t["kind"]
        if kind in SWEEPS:
            continue
        if kind == "roll":
            hits += [(at, vel) for at, vel in t.get("hits", ())]
            continue
        i0 = int(round(t["start"] * sr))
        rng = np.random.default_rng([seed, 4099, int(t["key"])])
        n = max(1, int(round((t["end"] - t["start"]) * sr)))
        y = riser(n, sr, rng) if kind == "riser" else down(n, sr, rng) if kind == "down" else \
            impact(sr, rng, bool(t.get("kick")))
        a, b = max(0, i0), min(length, i0 + len(y))  # only what falls inside the render
        if b > a:
            out = np.zeros((length, 2)) if out is None else out
            out[a:b] += y[a - i0: b - i0] * (LEVEL * float(t.get("level", 1.0)))
    if hits:  # no drum player in the band: the roll on a 909
        from . import drummachine
        from ..score import Note

        notes = [Note("fx", at, 0.1, 38.0, float(vel), art="snare") for at, vel in hits if 0.0 <= at < length / sr]
        if notes:
            y = drummachine.render("drums-909", notes, sr, length, np.random.default_rng([seed, 4099, 17]),
                                   np.random.default_rng([0, 29, 4099]), {})
            out = np.zeros((length, 2)) if out is None else out
            out += y * drummachine.SPEC["drums-909"]["level"]
    return out


def sweep_spans(transitions, sr: int) -> list[tuple[str, int, int]]:
    """The band's filter sweeps as (kind, first sample, sample after the last): their whole spans, which may
    begin before the render does (a section's preview in the middle of one)."""
    return [(t["kind"], int(round(t["start"] * sr)), int(round(t["end"] * sr)))
            for t in transitions if t["kind"] in SWEEPS]


def sweep(signals: list[np.ndarray], sr: int, spans) -> None:
    """The band's bus (and what goes with it: its send, what steps back under the voice), each a float64
    array the caller owns, through each sweep where it lies: over its span a filter whose corner moves
    exponentially between its ends, all of the span's curve counted from its own start; handed back to the
    dry sound over FADE after it."""
    for kind, a, b in spans:
        a0, b = max(0, a), b
        n = len(signals[0])
        if b - a0 < BLOCK or a0 >= n:
            continue
        if kind == "stop":  # the band stops: out over FADE where the span begins, back at once at its end
            k = min(int(FADE * sr), b - a0)
            gate = np.zeros(min(b, n) - a0)
            if a0 == a:
                gate[:k] = 0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, k))
            for x in signals:
                if x is not None:
                    x[a0:a0 + len(gate)] *= gate[:, None] if x.ndim == 2 else gate
            continue
        lo, hi = SWEEP_HP if kind == "sweep-hp" else SWEEP_OPEN if kind == "sweep-open" else SWEEP_LP
        k = max(0, min(int(FADE * sr), n - b))  # the filter runs on past the span while it hands back
        span = b - a

        def corner(i, lo=lo, hi=hi, off=a0 - a, span=span):
            return lo * (hi / lo) ** min(1.0, (i + off) / span)

        stop = min(n, b + k)
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, k)) if k else None
        for x in signals:
            if x is None:
                continue
            wet = moving(x[a0:stop], "hp" if kind == "sweep-hp" else "lp", corner, SWEEP_Q, sr)
            inner = min(b, n) - a0
            x[a0:a0 + inner] = wet[:inner]
            if k:
                r = ramp[:, None] if x.ndim == 2 else ramp
                x[b:b + k] = wet[inner:] * (1.0 - r) + x[b:b + k] * r
