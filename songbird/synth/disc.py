"""The recording: the whole mix as if sung and played into an acoustic recording horn, cut onto a 78 and played
back (docs/STYLES.md, "An old 78").

A stage at the end of the mix (mixing.mix_made, after the glue and the tilt) where the mix has a disc
(MixParams.disc > 0); nothing else ever enters it. In order:

- **mono**: the mid, written back to both channels;
- **the horn**: the band it took, about 140 Hz to 5 kHz, with its resonances (a honk in the low mids, a
  little more around 1 to 1.5 kHz and at the recording diaphragm's 2.5 to 3 kHz, a dip between), each record's
  its own, drawn; the cutting stylus's slight saturation;
- **the turntable**: the disc a little off centre, so the pitch wavers once a revolution (78.26 a minute: a
  wow at 1.30 Hz, 0.1 to 0.3% at its peak, each record its own), and a little flutter from the motor;
- **the surface**: the groove's noise through the playback's band, swelling once a revolution where an arc of
  the groove is worn and drifting slowly across the side; a fine crackle; clicks from scratches, each heard
  once a revolution (exactly the rotation's period, in step with the wow) for a few turns, and a pop now and
  then;
- **the needle**: dropped into the lead-in groove before the music (where the mix begins in silence: a whole
  song's preroll, not a section heard alone), and at the end, where the music has died away, the run-out
  groove's swish and click once a revolution, three seconds of it added after the song, then lifted.

`disc` is how worn the shellac is: the surface's noise and clicks scale with it (1 as designed); the horn, the
mono and the turntable are the same at any amount above 0. Every random draw is the rendition's (its seed, a
stream of its own), made in a fixed order and a fixed stretch at a time, so the same record gives the same
samples. Plain numpy and scipy, and fx's filters, saturation and warp: no kernel of its own.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt

from . import fx
from .master import loudness

RPM = 78.26  # a 78's speed (a 60 Hz motor's 3600 / 46 teeth)
TURN = 60.0 / RPM  # s a revolution: 0.767
STREAM = 0x78  # the disc's own random stream, beside the rendition's seed
BLOCK = 1 << 18  # samples of the surface made at a time (fixed: the draws come in the same order whatever the song)

WOW = (0.001, 0.003)  # the eccentricity's peak speed error, drawn per record (0.1 to 0.3%: 1.7 to 5 cents)
WOW_SECOND = 0.25  # its second harmonic, against the first
FLUTTER = 0.0002  # RMS speed error from the motor, 6 to 14 Hz
SATURATION = 0.2  # the cutting stylus (fx.saturate's drive)
NOISE_DB = -38.0  # the surface's loudness under the music's (LU), at disc 1
SWELL = 0.2  # the noise's swell once a revolution (a worn arc of the groove)
DRIFT = 0.1  # and its slow drift across the side
CRACKLE = 25.0  # small ticks a second
SCRATCHES = 0.05  # scratches a second, each heard once a revolution for 2 to 20 turns
POPS = 0.08  # single pops a second
CLICK = 0.12  # a click's size against the music's loud peak (before its filter: its peaks about -14 dB)
TICK = 0.02  # a crackle's
LEAD_SILENT = 0.3  # s of silence the mix must begin with for the needle to be dropped (a whole song's preroll)
DROP = 0.05  # s: the needle lands
RISE = 0.15  # s the groove's noise takes to come in
RUN_OUT = 3.0  # s of run-out groove after the music has died away (added to the song)
DIED = 50.0  # dB under the music's loud level where it has died away
LIFT = 0.25  # s before the end the needle is lifted


def horn(rng: np.random.Generator) -> tuple:
    """A recording horn's band and resonances (fx.design's bands), drawn: each record its own."""
    return (("hp", float(rng.uniform(130.0, 150.0)), 2), ("lp", float(rng.uniform(4600.0, 5200.0)), 4),
            ("peak", float(rng.uniform(450.0, 700.0)), float(rng.uniform(4.0, 6.0)), float(rng.uniform(2.5, 3.5))),
            ("peak", float(rng.uniform(1100.0, 1600.0)), float(rng.uniform(2.0, 4.0)), 3.0),
            ("peak", float(rng.uniform(1800.0, 2100.0)), -3.0, 2.0),
            ("peak", float(rng.uniform(2400.0, 3200.0)), float(rng.uniform(3.0, 5.0)), float(rng.uniform(2.5, 3.0))))


def playback(spec: tuple) -> tuple:
    """The band the groove's noise and clicks are heard through: the reproducer's, a little wider than the horn's."""
    lp = spec[1][1]
    return (("hp", 150.0, 2), ("lp", lp + 1000.0, 2), ("peak", 2500.0, 2.0, 0.7))


def _band_noise(rng: np.random.Generator, n: int, rate: float, lo: float, hi: float) -> np.ndarray:
    x = rng.standard_normal(n)
    x = fx.equalize(x[:, None], fx.design((("hp", lo), ("lp", hi)), int(rate)))[:, 0]
    return x / (np.sqrt(np.mean(x**2)) + 1e-12)


def _quick(m: np.ndarray, sr: int) -> float:
    """Loudness of a mono signal at half the rate (pairs averaged), as mixing.quick_loudness measures a stem."""
    k = len(m) // 2 * 2
    if k < 2 * sr:
        return loudness(m[:, None], sr)
    return loudness(((m[:k:2] + m[1:k:2]) / 2.0)[:, None], sr // 2)


def _levels(m: np.ndarray, sr: int) -> np.ndarray:
    """dB of mean power of each 50 ms block."""
    blk = max(1, int(0.05 * sr))
    k = len(m) // blk
    if not k:
        return np.zeros(0)
    p = np.einsum("ij,ij->i", m[: k * blk].reshape(k, blk), m[: k * blk].reshape(k, blk)) / blk
    return 10.0 * np.log10(p + 1e-30)


def clicks_at(rng: np.random.Generator, length: float, phase: float) -> list[tuple[float, float]]:
    """Where the record's scratches and pops are heard (s) and how big (signed): a scratch at an angle of the disc is
    heard each time that angle comes under the needle, from where it begins for its turns."""
    out = []
    for _ in range(int(rng.poisson(length * SCRATCHES))):
        start = float(rng.uniform(0.0, length))
        angle = float(rng.uniform(0.0, 2 * np.pi))
        turns = int(rng.integers(2, 21))
        size = float(rng.lognormal(0.0, 0.5)) * float(rng.choice((-1.0, 1.0)))
        offset = ((angle - phase) % (2 * np.pi)) / (2 * np.pi) * TURN  # when that angle first passes the needle
        first = np.ceil((start - offset) / TURN)
        for j in range(turns):
            out.append((float((first + j) * TURN + offset), size * (1.0 + 0.15 * float(rng.standard_normal()))))
    for _ in range(int(rng.poisson(length * POPS))):
        out.append((float(rng.uniform(0.0, length)), float(rng.choice((-1.0, 1.0))) * float(rng.lognormal(0.3, 0.4))))
    return out


def record(x: np.ndarray, sr: int, amount: float, seed: int = 0, taps: dict | None = None) -> np.ndarray:
    """The mix x ((n, 2), float64: written over) as a 78: mono, through the horn, on the turntable, with the
    surface and the needle; three seconds longer where the run-out is added. taps: a dict to receive the horn,
    the disc's phase and eccentricity, the music before the surface, the surface alone, the clicks and where the
    run-out begins (for measuring)."""
    a = float(np.clip(amount, 0.0, 1.0))
    n = len(x)
    if a <= 0 or n < sr // 10:
        return x
    rng = np.random.default_rng([int(seed) & 0xFFFFFFFF, STREAM])
    m = np.add(x[:, 0], x[:, 1])
    m *= 0.5
    spec = horn(rng)
    m = fx.equalize(m, fx.design(spec, sr), inplace=True)
    m = fx.saturate(m, sr, SATURATION, inplace=True)

    # the turntable: the disc's angle at the start, its eccentricity; the speed's error read as a time-varying delay
    phase = float(rng.uniform(0.0, 2 * np.pi))
    eccentric = float(rng.uniform(*WOW))
    rate = 1000.0
    k = int(n / sr * rate) + 2
    t = np.arange(k) / rate
    turning = 2 * np.pi * t / TURN + phase
    speed = eccentric * (np.sin(turning) + WOW_SECOND * np.sin(2 * turning + float(rng.uniform(0.0, 2 * np.pi))))
    speed += FLUTTER * _band_noise(rng, k, rate, 6.0, 14.0)
    lag = np.cumsum(speed) / rate * sr
    offset = np.interp(np.arange(n) / sr, t, lag - lag.mean())
    del t, turning, speed, lag
    m = fx.warp(m, offset)
    del offset

    # where the music begins and ends, and how loud it is
    level = _quick(m, sr)
    peak = fx.loud_peak(m, sr)
    blocks = _levels(m, sr)
    loud = float(np.percentile(blocks[blocks > blocks.max() - 40.0], 90)) if len(blocks) else -120.0
    blk = max(1, int(0.05 * sr))
    live = np.flatnonzero(blocks > loud - DIED)
    begins = int(live[0]) * blk if len(live) else 0
    ends = (int(live[-1]) + 1) * blk if len(live) else n
    dropped = begins >= LEAD_SILENT * sr  # a whole song, from its preroll: the needle is dropped into the lead-in
    tail = len(blocks) and blocks[-max(1, int(0.5 * sr) // blk):].max() < loud - DIED + 10.0  # died away by the end
    extra = int(RUN_OUT * sr) if tail else 0
    total = n + extra
    if taps is not None:
        taps.update(horn=spec, phase=phase, eccentric=eccentric, level=level, peak=peak, begins=begins, ends=ends,
                    music=m.copy())
    if not np.isfinite(level):
        out = x if not extra else np.zeros((total, 2))
        out[:n, 0] = m
        out[:n, 1] = m
        return out

    # the surface: the groove's noise through the playback's band, a stretch at a time, swelling once a revolution
    sos = fx.design(playback(spec), sr)
    unit = loudness(sosfilt(sos, np.random.default_rng([STREAM, 1]).standard_normal(10 * sr))[:, None], sr)
    gain = a * 10.0 ** ((level + NOISE_DB - unit) / 20.0)
    worn = float(rng.uniform(0.0, 2 * np.pi))
    side = float(rng.uniform(0.0, 2 * np.pi))
    surface = np.empty(total)
    zi = np.zeros((len(sos), 2))
    for b0 in range(0, total, BLOCK):
        b1 = min(total, b0 + BLOCK)
        w, zi = sosfilt(sos, rng.standard_normal(b1 - b0), zi=zi)
        tt = np.arange(b0, b1) / sr
        w *= gain * (1.0 + SWELL * np.sin(2 * np.pi * tt / TURN + phase + worn)
                     + DRIFT * np.sin(2 * np.pi * 0.021 * tt + side))
        surface[b0:b1] = w
    idx = np.arange(total)
    start = int(DROP * sr) if dropped else 0
    if dropped:  # the needle lands and the groove's noise comes in
        surface *= np.clip((idx - start) / (RISE * sr), 0.0, 1.0)
    lift = total - int(LIFT * sr) if extra else total
    if extra:  # the run-out groove a little louder, and the needle lifted at the end
        surface *= 1.0 + 0.3 * np.clip((idx - ends) / (0.3 * sr), 0.0, 1.0)
        surface *= np.clip((total - idx) / (0.2 * sr), 0.0, 1.0)
    del idx

    # crackle, scratches and pops: impulses through a tick's filter, the big ones with a thump under them
    length = total / sr
    ticks = np.zeros(total)
    thumps = np.zeros(total)
    count = int(rng.poisson(length * CRACKLE))
    where = rng.integers(start, max(start + 1, lift), count)
    sizes = np.minimum(rng.lognormal(0.0, 0.7, count), 4.0) * rng.choice((-1.0, 1.0), count)
    np.add.at(ticks, where, TICK * sizes)
    groove = (ends if extra else lift) / sr - 0.05  # (the run-out groove has its own click)
    heard = [(t0, s) for t0, s in clicks_at(rng, length, phase) if start / sr < t0 < groove]
    swishes = []
    if extra:  # the run-out groove's click once a revolution, a swish about it
        lock = ((float(rng.uniform(0.0, 2 * np.pi)) - phase) % (2 * np.pi)) / (2 * np.pi) * TURN
        j = np.ceil((ends / sr + 0.2 - lock) / TURN)
        while (j * TURN + lock) < lift / sr - 0.1:
            swishes.append(float(j * TURN + lock))
            heard.append((swishes[-1], 1.2))
            j += 1
        heard.append((lift / sr, 0.6))  # lifted
    if dropped:
        heard.append((start / sr, 1.5))  # the needle's drop
    for t0, s in heard:
        i = int(t0 * sr)
        if 0 <= i < total:
            ticks[i] += CLICK * s
            if abs(s) >= 1.2:
                thumps[i] += CLICK * s
    ticks = sosfilt(fx.design((("hp", 1500.0, 2), ("peak", 3500.0, 6.0, 1.5), ("lp", 6500.0, 2)), sr), ticks)
    thumps = sosfilt(fx.design((("hp", 60.0, 2), ("lp", 220.0, 2)), sr), thumps)
    ticks += 6.0 * thumps
    del thumps
    ticks *= a * peak
    surface += ticks
    del ticks
    for t0 in swishes:
        i0, i1 = int((t0 - 0.08) * sr), int((t0 + 0.08) * sr)
        if 0 <= i0 and i1 <= total:
            surface[i0:i1] *= 1.0 + 3.0 * np.sin(np.linspace(0.0, np.pi, i1 - i0)) ** 2
    if taps is not None:
        taps.update(surface=surface.copy(), clicks=sorted(heard), runout=ends if extra else None, dropped=dropped)

    out = x if not extra else np.zeros((total, 2))
    del x
    surface[:n] += m
    del m
    out[:, 0] = surface
    out[:, 1] = surface
    return out
