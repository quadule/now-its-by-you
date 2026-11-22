"""The room every rendition on a machine lives in.

The voice harvest reduces a real room to an RT60 and a five-band tonal
profile; this module regenerates a room from exactly those few numbers (and a
predelay), so the room travels as parameters, never as a recording.

A room answers a sound in two parts. First the early reflections: the echoes
off the walls, floor and ceiling of a room as large as the RT60 suggests,
worked out by mirror images (to the second bounce) for a player standing a
little left or right of centre, each echo smeared a little by the surface it
met and arriving from its own side. Then the late tail: noise whose every
octave decays at its own rate (highs first, as air and soft surfaces take
them), coloured by the tonal profile, heard independently by the two ears
above a few hundred hertz, as in a real diffuse field (Polack's model).
Neither part has the regular echoes of a delay network, so nothing rings
metallic at any size, from a 0.3 s living room to a 2.5 s church.

The plate is the studio's own reverb for the voice, the same on every
machine: dense from the start, bright, wide, with little low end.
"""

from __future__ import annotations

import zlib
from functools import lru_cache

import numpy as np
from scipy.fft import irfft, next_fast_len, rfft, rfftfreq
from scipy.signal import oaconvolve

from . import oa

BANDS = ((40.0, 250.0), (250.0, 700.0), (700.0, 2000.0), (2000.0, 5600.0), (5600.0, 16000.0))
AIR = (1.2, 1.1, 1.0, 0.8, 0.55)  # relative decay time per band: highs die first
TONE = (1.0, 1.0, 1.0, 0.9, 0.7)  # the room's level per band (amplitude)
OCTAVES = 31.25 * 2.0 ** np.arange(10)  # 31 Hz .. 16 kHz: the tail is shaped octave by octave
SPEED = 343.0  # m/s

# The plate: decay per band relative to its RT60, its colour, and where the ears stop agreeing.
PLATE_AIR = (0.75, 0.95, 1.0, 0.85, 0.6)
PLATE_TONE = (0.35, 0.8, 1.0, 1.0, 0.75)


def _per_octave(values) -> np.ndarray:
    """Five per-band values spread over the ten octaves, linear in log frequency."""
    centres = np.log2([np.sqrt(lo * hi) for lo, hi in BANDS])
    return np.interp(np.log2(OCTAVES), centres, np.asarray(values, dtype=float))


def _octave_masks(f: np.ndarray) -> np.ndarray:
    """Ten amplitude masks over frequency that sum to one everywhere: each rises
    and falls as a raised cosine over the octave either side of its centre."""
    x = np.log2(np.maximum(f, 1e-3) / OCTAVES[0])  # 0 at the first centre, 1 per octave
    masks = np.zeros((len(OCTAVES), len(f)))
    for k in range(len(OCTAVES)):
        d = x - k
        m = np.cos(np.pi / 2 * np.clip(np.abs(d), 0.0, 1.0)) ** 2
        if k == 0:
            m[d < 0] = 1.0
        if k == len(OCTAVES) - 1:
            m[d > 0] = 1.0
        masks[k] = m
    return masks


def dimensions(rt60: float) -> np.ndarray:
    """Length, width and height (m) of a room with this RT60: bigger rooms ring
    longer. 0.3 s is a furnished room of about 5 m, 1.1 s a hall of 10 m, 2.5 s
    a church of 18 m."""
    size = 3.0 + 6.0 * float(np.clip(rt60, 0.1, 4.0))
    return np.array([size, 0.72 * size, max(2.4, 0.42 * size)])


def early_reflections(sr: int, rt60: float = 1.1, predelay: float = 0.012, seed: int = 0) -> np.ndarray:
    """The first echoes, shape (2, samples, 2): for a player left of centre and
    one right of it, what reaches the left and right ear. Times are after the
    direct sound, the first echo arriving `predelay` seconds after it."""
    rng = np.random.default_rng(seed + 11)
    room = dimensions(rt60) * rng.uniform(0.92, 1.08, 3)
    volume = float(np.prod(room))
    surface = 2.0 * (room[0] * room[1] + room[0] * room[2] + room[1] * room[2])
    absorption = float(np.clip(0.161 * volume / (surface * max(rt60, 0.1)), 0.05, 0.9))  # Sabine
    wall = np.sqrt(1.0 - absorption)
    bounce = np.array([wall, wall, 0.7 * wall])  # floor and ceiling take more: people, rugs, seats
    ear = np.array([0.62 * room[0], 0.5 * room[1], 1.3])  # listening toward the front wall (x = 0)
    order = 2
    reach = np.arange(-order, order + 1)
    grid = np.array(np.meshgrid(reach, reach, reach, indexing="ij")).reshape(3, -1).T
    grid = grid[(np.abs(grid).sum(axis=1) >= 1) & (np.abs(grid).sum(axis=1) <= order)]

    events = []  # (source side, time, amplitude, lateral position, bounces)
    for side, offset in ((0, -1.0), (1, 1.0)):
        source = np.array([0.3 * room[0], 0.5 * room[1] + offset * min(1.2, 0.3 * room[1]), 1.5])
        direct = np.linalg.norm(source - ear)
        # mirror images: an odd number of bounces off a wall pair flips the source across it
        images = np.where(grid % 2 == 0, grid * room + source, grid * room + (room - source))
        v = images - ear
        d = np.linalg.norm(v, axis=1)
        amp = direct / d * np.prod(bounce ** np.abs(grid), axis=1)
        for k in range(len(grid)):
            events.append((side, (d[k] - direct) / SPEED, amp[k], v[k, 1] / d[k], int(np.abs(grid[k]).sum())))
    first = min(e[1] for e in events)
    length = int(sr * (max(e[1] for e in events) - first + predelay + 0.01)) + 64
    out = np.zeros((2, length, 2))
    for side, t, amp, lateral, bounces in events:
        # a surface scatters and softens what it returns: a short noise burst, darker per bounce
        n = int(sr * (0.0006 + 0.0006 * bounces)) + 2
        burst = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.4 * n))
        a = 0.25 + 0.2 * bounces  # one-pole low-pass coefficient
        for i in range(1, n):
            burst[i] = (1 - a) * burst[i] + a * burst[i - 1]
        burst /= np.sqrt(np.sum(burst**2))
        theta = (lateral + 1.0) * np.pi / 4.0
        gains = (np.cos(theta), np.sin(theta))
        lag = 0.0003 * lateral  # the nearer ear hears it first
        for e, (g, late) in enumerate(zip(gains, (max(lag, 0.0), max(-lag, 0.0)))):
            i = int(round((t - first + predelay + late) * sr))
            out[side, i : i + n, e] += amp * g * burst
    return out


def late_tail(sr: int, rt60: float = 1.1, tone=TONE, seed: int = 0, start: float = 0.0, ramp: float = 0.02,
              air=AIR, coherence: float = 400.0) -> np.ndarray:
    """The diffuse tail, shape (samples, 2): noise decaying octave by octave,
    rising over `ramp` seconds from `start`. Below `coherence` Hz the ears
    hear much the same thing, above it independent things."""
    t60 = rt60 * _per_octave(air)
    level = _per_octave(tone)
    n = int(sr * (start + ramp + 1.1 * t60.max()))  # to 66 dB down
    nfft = next_fast_len(n)
    rng = np.random.default_rng(seed + 29)
    left, right = rfft(rng.standard_normal(nfft)), rfft(rng.standard_normal(nfft))
    masks = _octave_masks(rfftfreq(nfft, 1.0 / sr))
    t = np.arange(n) / sr
    after = np.maximum(t - start, 0.0)
    out = np.zeros((n, 2))
    for k in range(len(OCTAVES)):
        env = level[k] * 10.0 ** (-3.0 * after / t60[k])
        a = irfft(masks[k] * left, nfft)[:n]
        b = irfft(masks[k] * right, nfft)[:n]
        rho = max(0.0, float(np.sinc(OCTAVES[k] / coherence)))
        out[:, 0] += env * a
        out[:, 1] += env * (rho * a + np.sqrt(1.0 - rho * rho) * b)
    onset = 0.5 - 0.5 * np.cos(np.pi * np.clip((t - start) / max(ramp, 1e-4), 0.0, 1.0))
    return out * onset[:, None]


def _unit(ir: np.ndarray) -> np.ndarray:
    """Scale so each ear's response has unit energy on average."""
    return ir / np.sqrt(np.sum(ir**2) / ir.shape[-1])


def seed_of(rt60: float, tone=TONE, predelay: float = 0.012) -> int:
    """A room's own seed, from its numbers (as the harvest rounds them): a
    machine's room is the same room every rendition, echo for echo."""
    key = f"{rt60:.2f}|" + ",".join(f"{t:.2f}" for t in tone) + f"|{predelay:.3f}"
    return zlib.crc32(key.encode())


def _coloured(early: np.ndarray, sr: int, tone) -> np.ndarray:
    """The early reflections through the tonal profile too: surfaces colour the first echoes as they do the tail."""
    n = next_fast_len(early.shape[1] + 256)
    f = rfftfreq(n, 1.0 / sr)
    centres = np.log2([np.sqrt(lo * hi) for lo, hi in BANDS])
    gain = np.interp(np.log2(np.maximum(f, 20.0)), centres, np.asarray(tone, dtype=float))
    return irfft(rfft(early, n, axis=1) * gain[None, :, None], n, axis=1)[:, : early.shape[1]]


def responses(sr: int, rt60: float = 1.1, tone=TONE, predelay: float = 0.012, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """The room's early reflections (2, samples, 2) and late tail (samples, 2),
    scaled together so a centred source's response has unit energy per ear.
    Small rooms are heard more by their early reflections, large ones by
    their tail. Made once for each room's numbers (every render of a version is in the same room) and handed back
    read-only."""
    return _responses(sr, rt60, tuple(tone), predelay, seed)


@lru_cache(maxsize=4)
def _responses(sr: int, rt60: float, tone: tuple, predelay: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    early = _coloured(early_reflections(sr, rt60, predelay, seed), sr, tone)
    volume = float(np.prod(dimensions(rt60)))
    mixing = max(0.005, 0.001 * np.sqrt(volume))  # when echoes have become too dense to tell apart
    tail = late_tail(sr, rt60, tone, seed, start=predelay, ramp=2.0 * mixing)
    share = float(np.interp(rt60, [0.3, 2.5], [0.3, 0.15]))  # of the energy in the early reflections
    centred = (early[0] + early[1]) / 2.0
    e_early = np.sum(centred**2) / 2.0
    e_tail = np.sum(tail**2) / 2.0
    early = early * np.sqrt(share / e_early)
    tail = tail * np.sqrt((1.0 - share) / e_tail)
    early.flags.writeable = tail.flags.writeable = False
    return early, tail


def impulse_response(sr: int, rt60: float = 1.1, tone=TONE, predelay: float = 0.012, seed: int = 0) -> np.ndarray:
    """A centred source's stereo impulse response, energy-normalized, shape (samples, 2)."""
    early, tail = responses(sr, rt60, tone, predelay, seed)
    n = max(early.shape[1], len(tail))
    ir = np.zeros((n, 2))
    ir[: early.shape[1]] += (early[0] + early[1]) / 2.0
    ir[: len(tail)] += tail
    return _unit(ir)


@lru_cache(maxsize=4)
def plate(sr: int, rt60: float = 1.6, seed: int = 0) -> np.ndarray:
    """The voice's plate, shape (samples, 2), unit energy per ear: dense from the
    first millisecond, bright, wide, light in the low end. (Made once, read-only.)"""
    out = _unit(late_tail(sr, rt60, PLATE_TONE, seed + 7, start=0.0, ramp=0.003, air=PLATE_AIR, coherence=150.0))
    out.flags.writeable = False
    return out


WORKERS = 4  # threads for the long convolutions' FFTs: a fixed number, so every machine computes the same bits


def convolve(send: np.ndarray, early: np.ndarray | None, tail: np.ndarray, extra=()) -> np.ndarray:
    """A stereo send through a room: each side's early reflections from that
    side of the send, the diffuse tail from both sides together; and any
    `extra` (mono send, stereo response) pairs heard alongside, such as the
    plate. Shape (len(send) + the longest response - 1, 2).

    Worked in mid and side: the mid (both sides together) goes through the
    centred early reflections and the tail at once; the side through what
    differs between a player on the left and one on the right, which in a
    room symmetric about the listener reaches the two ears with opposite
    signs. Three convolutions instead of six.

    send may be given as a list holding it alone: it is taken out of the list, and let go once its mid and
    side are made (a long song's send is not held through the convolutions)."""
    if isinstance(send, list):
        send = send.pop()
    longest = max([len(tail)] + ([early.shape[1]] if early is not None else []) + [len(r) for _, r in extra])
    out = np.zeros((len(send) + longest - 1, 2))
    mid = (send[:, 0] + send[:, 1]) * np.sqrt(0.5)
    side = (send[:, 0] - send[:, 1]) * np.sqrt(0.5)
    del send
    response = np.zeros((max(len(tail), early.shape[1] if early is not None else 0), 2))
    response[: len(tail)] += tail
    # each convolution as oaconvolve makes it on WORKERS FFT threads, a few blocks at a time (oa.convolve)
    if early is not None:
        response[: early.shape[1]] += (early[0] + early[1]) * np.sqrt(0.5)
        differs = (early[0] - early[1]) * np.sqrt(0.5)
        y = oa.convolve(side, (differs[:, 0] - differs[:, 1]) / 2.0, workers=WORKERS) if np.any(side) else np.zeros(0)
        out[: len(y), 0] += y
        out[: len(y), 1] -= y
        del y
    del side
    y = oa.convolve_shared(mid, response, workers=WORKERS)
    out[: len(y)] += y
    del y
    del mid
    for mono, r in extra:
        y = oa.convolve_shared(mono, r, workers=WORKERS)
        out[: len(y)] += y
        del y
    return out


def apply(dry: np.ndarray, ir: np.ndarray, send: np.ndarray | None = None, wet: float = 0.3) -> np.ndarray:
    """Dry signal plus the room's response to `send` (by default the dry signal).

    Sources at different distances share one room: each stem's send level says
    how much of it reaches the room relative to the listener.
    """
    send = dry if send is None else send
    out = np.zeros((len(dry) + len(ir) - 1, 2))
    out[: len(dry)] = dry
    for ch in range(2):
        out[:, ch] += wet * oaconvolve(send[:, ch], ir[:, ch])
    return out
