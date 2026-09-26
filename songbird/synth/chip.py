"""Chip voices: a game console's sound chip (the NES's 2A03), channel by channel.

The 2A03 makes sound with counters. Its two pulse channels step an 8-step
sequence (0 1 0 0 0 0 0 0 for 12.5%, and 25%, 50% and a 75% that is 25%
upside down) at eight times the note, driven by an 11-bit timer, f = CPU /
(16 (t + 1)); each has a 4-bit volume. The triangle channel steps a 32-step
table of 4-bit values (15 down to 0 and back) at 32 times the note: a
triangle drawn as a staircase, with no volume control at all, only on or
stopped (a counter halts it wherever it happens to be). The noise channel
shifts a 15-bit register at one of sixteen rates, 440 Hz to 447 kHz (a
period of 4068 down to 4 CPU cycles); its feedback is bit 0 xor bit 1 (a
32767-step sequence: noise) or, in its short mode, bit 0 xor bit 6 (93
steps: a metallic buzz with a pitch), and it sounds its volume whenever
bit 0 is clear. The channels are summed by two nonlinear resistor networks,
pulse_out = 95.88 / (8128 / (p1 + p2) + 100) and tnd_out = 159.79 / (1 / (t
/ 8227 + n / 12241 + d / 22638) + 100), and the console filters the sum:
high-passes at 90 and 440 Hz and a low-pass at 14 kHz (the front-loading
NES; the NESdev wiki's measurements). A game's sound driver runs once a
video frame (60.1 Hz): it sets each channel's period and volume, so
volume envelopes, arpeggios (a chord from one voice, a frame per note),
vibrato and slides all move in sixtieths of a second, and a new note
restarts the pulse's sequence.

How it is modelled. Each channel is a list of the moments its output level
changes (the pulse sequence's edges, the triangle's steps, the shift
register's output bit, the driver's volume changes), each level passed
through the mixer's curve, drawn as a staircase at twice the sample rate
with every step band-limited by osc's four-point residual (osc._blep4),
brought down with osc.decimate2, and filtered as the console is. The noise
register's steps are band-limited one by one, even at 447 kHz, five or so
to an output sample. The pitch is exact: the chip's timers would round it
to a whole period (C7 on a pulse 14.5 cents sharp), which is left out.
Frames are counted from each note's start, a driver ticking in time with
the score rather than a free 60 Hz clock that would move every note onto
the next frame. The triangle stops where it is when its note ends and
starts again from there (so its attacks differ, as the chip's do); before
anything plays it is taken as settled at its first step, so nothing sounds
before the first note. The noise register runs on between hits (skipped
ahead by the clocks that passed), so each hit plays its own stretch of the
sequence.

The instruments. chip: one pulse channel, its width by art (default 25%;
50% when brightness is under 0.35, 12.5% over 0.7), velocity to the 4-bit
volume, which sags a step or three over the first frames and holds, then
falls three steps a frame when the note ends; frame arpeggios, a pluck
envelope, frame-by-frame slides, and a vibrato from ornament (±0.35
semitone at ornament 1, 5.5 to 6.5 Hz, after 12 to 20 frames). chip-bass:
the triangle, at its one level (dynamic False: the chip gives it none; the
DMC trick that could duck it pops). chip-drums: the noise channel and the
triangle as NES games used them: a snare of mid-clock noise over nine
frames with a triangle blip, hats at the top clock, a stuttering clap, a
crash, a rim and a cowbell from the looped noise, a kick and toms swept
down the triangle a frame a step (a harder kick sweeps further); one sound
at a time on each channel, a later noise hit cutting the one sounding, and
of two struck together the snare's family before the hats.

Measured (tests/test_chip.py): a 12.5% pulse lacks every 8th harmonic
(-179 dB), a 25% one every 4th, a square every even one; the register's
sequences are 32767 and 93 steps long from any start; the 15 volume steps
follow the mixer's curve exactly, 22 dB from 1 to 15; in tune to 0.00
cents; folded content from a 12.5% pulse at C7 -83 dB, and off the looped
noise's lines -69 dB; the triangle changes level 30 times a period through
16 values, and its steps put its 31st and 33rd harmonics 30 dB under the
fundamental (an ideal triangle's are 60 down): the chip's buzz; the
console's filters take 14.5 dB off a 110 Hz triangle's fundamental and 24
off a 55 Hz one; an arpeggio steps 440, 554, 659 Hz frame by frame. A
three-minute part costs under 1.1 s of CPU.

Settings: brightness picks the pulse's default width; ornament its
vibrato; wear and body are not used (a chip doesn't wear). make gives each
machine its own sound driver: how far a held note's volume sags, the
vibrato's speed and delay, the snare's and hats' clock a step either way,
the kick's pitch.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit
from scipy.signal import butter, sosfilt

from . import osc

SPEC = {
    "chip": dict(
        family="chip",
        role="lead",
        register=(45, 96),
        place=(-0.1, 0.0),
        level=0.634,
        poly=False,
        articulations={
            "": "a pulse at the default width (25%; 50% when brightness is under 0.35, 12.5% over 0.7), its "
                "volume stepping down a little over the first frames and holding, a quick stepped release",
            "12": "a 12.5% pulse: thin and nasal (every 8th harmonic missing)",
            "25": "a 25% pulse: bright and reedy (every 4th harmonic missing)",
            "50": "a square: hollow, clarinet-like (no even harmonics)",
            "75": "a 75% pulse: sounds as the 25% one does (it is its negative)",
            "arp-maj": "the note steps through its major triad, a frame (1/60 s) each: a chord from one voice",
            "arp-min": "through its minor triad",
            "arp-sus": "through root, fourth and fifth",
            "arp-pow": "root and fifth",
            "arp-oct": "root and octave",
            "pluck": "the volume falls to silence over half a second (30 frames) while held: a plucked, harp-like "
                     "note",
            "glide": "slides from the last note, frame by frame, without restarting its waveform",
        },
        about="one of the NES's two pulse channels: a pulse of four widths, sixteen volume steps set sixty times "
              "a second, frame arpeggios, a delayed vibrato from ornament",
    ),
    "chip-bass": dict(
        family="chip",
        role="bass",
        register=(28, 67),
        place=(0.0, 0.0),
        level=0.849,
        poly=False,
        dynamic=False,
        articulations={
            "": "the triangle channel's 32-step, 4-bit triangle, at one level (the chip gives it no volume); "
                "it stops where it is when the note ends and starts again from there",
            "glide": "slides from the last note, frame by frame",
            "arp-oct": "alternates root and octave a frame each: the chip's way to thicken a bass",
        },
        about="the NES's triangle channel: a stepped triangle with no volume control, thinned below 440 Hz by the "
              "console's own output filter",
    ),
    "chip-drums": dict(
        family="chip",
        role="percussion",
        register=None,
        place=(0.08, 0.0),
        level=0.459,
        poly=True,
        articulations={
            "snare": "noise at a middle clock, falling over nine frames, over a triangle blip",
            "kick": "the triangle swept down from about 250 Hz, a frame a step (longer when harder), and a tick "
                    "of low noise",
            "hat": "noise at the top clock (447 kHz), three frames",
            "hat-open": "the same, falling over twelve frames",
            "clap": "noise that stutters on and off frame by frame, then falls",
            "crash": "bright noise falling over three quarters of a second",
            "rim": "a frame of the looped (93-step) noise: a buzzy tick",
            "cowbell": "the looped noise at a pitch: a metallic ring over seven frames",
            "tom-hi": "a triangle sweep from about 330 Hz",
            "tom-mid": "from about 220 Hz",
            "tom-lo": "from about 150 Hz",
        },
        about="the NES's noise channel (a 15-bit shift register clocked at one of sixteen rates, long or looped) "
              "and triangle kicks and toms; a later noise hit cuts the one sounding",
    ),
}

CPU = 1789773.0  # the NTSC 2A03's clock (Hz)
FRAME = CPU / 29780.5  # the video frame (60.0988 Hz): a sound driver runs once each
NOISE_PERIODS = (4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068)  # CPU cycles
TRIANGLE_STEPS = np.array(list(range(15, -1, -1)) + list(range(16)), dtype=np.int64)  # 15..0, 0..15
OUT = 4.0  # the stems' scale: the chip's own output is a fraction of a volt
PAD = 128  # samples (at twice the rate) the staircase runs on past the part, so a halted triangle's held level
# doesn't meet the decimator's zero padding as a step
DUTIES = {"12": (0.875, 1.0), "25": (0.75, 1.0), "50": (0.5, 1.0), "75": (0.0, 0.75)}  # the high part of a period
ARPS = {"arp-maj": (0, 4, 7), "arp-min": (0, 3, 7), "arp-sus": (0, 5, 7), "arp-pow": (0, 7), "arp-oct": (0, 12)}


def pulse_level(v: float) -> float:
    """The 2A03's mixer for one pulse channel at volume v (0..15): 95.88 / (8128 / v + 100)."""
    return 0.0 if v <= 0 else 95.88 / (8128.0 / v + 100.0)


def tnd_level(t: float, n: float) -> float:
    """The mixer for the triangle (t, 0..15) and noise (n, 0..15), the DMC silent."""
    if t <= 0 and n <= 0:
        return 0.0
    return 159.79 / (1.0 / (t / 8227.0 + n / 12241.0) + 100.0)


# --- band-limited steps ------------------------------------------------------------------------


@njit(cache=True)
def _staircase(times, levels, n):
    """A staircase that is levels[i] from times[i] on (samples, ascending), 0 before the first, each step
    band-limited by osc's four-point residual."""
    y = np.empty(n)
    ne = times.shape[0]
    j = 0
    cur = 0.0
    for i in range(n):
        while j < ne and times[j] <= i:
            cur = levels[j]
            j += 1
        y[i] = cur
    prev = 0.0
    for j in range(ne):
        h = levels[j] - prev
        prev = levels[j]
        if h == 0.0:
            continue
        t = times[j]
        k0 = int(math.floor(t)) - 1
        for k in range(k0, k0 + 4):
            if 0 <= k < n:
                y[k] += h * osc._blep4(k - t)
    return y


# --- the channels, as event lists: when the DAC's level changes ------------------------------------


@njit(cache=True)
def _pulse_events(t0, t1, hz, vol, reset, lo, hi, table):
    """A pulse channel's changes of level from its frames: each frame a time span, a frequency, a volume
    (0..15), whether the sequencer restarts (a new note), and the high part of its period [lo, hi)."""
    cap = 16
    for k in range(t0.shape[0]):
        cap += 2 * int((t1[k] - t0[k]) * hz[k] + 2.0) + 1
    out_t = np.empty(cap)
    out_l = np.empty(cap)
    m = 0
    frac = 0.0
    high = False
    level = 0.0
    for k in range(t0.shape[0]):
        t = t0[k]
        end = t1[k]
        f = hz[k]
        a = lo[k]
        b = hi[k]
        if reset[k]:
            frac = 0.0
        high = frac >= a and frac < b
        top = table[vol[k]]
        new = top if high else 0.0
        if new != level:
            out_t[m] = t
            out_l[m] = new
            m += 1
            level = new
        while True:
            target = b if high else a
            dist = target - frac
            if dist <= 0.0:
                dist += 1.0
            te = t + dist / f
            if te >= end:
                frac += f * (end - t)
                frac -= math.floor(frac)
                break
            t = te
            frac = target if target < 1.0 else 0.0
            high = not high
            new = top if high else 0.0
            if new != level:
                out_t[m] = t
                out_l[m] = new
                m += 1
                level = new
    return out_t[:m], out_l[:m]


@njit(cache=True)
def _triangle_events(t0, t1, hz, phase):
    """The triangle channel's steps (time, value 0..15) from its running frames; between frames its
    sequencer is halted and holds its step. Returns the events and the phase (0..32) it stopped at."""
    cap = 16
    for k in range(t0.shape[0]):
        cap += int((t1[k] - t0[k]) * hz[k] * 32.0 + 2.0)
    out_t = np.empty(cap)
    out_v = np.empty(cap)
    m = 0
    for k in range(t0.shape[0]):
        t = t0[k]
        end = t1[k]
        rate = 32.0 * hz[k]
        while True:
            dist = math.floor(phase) + 1.0 - phase
            te = t + dist / rate
            if te >= end:
                phase += rate * (end - t)
                break
            t = te
            phase = math.floor(phase) + 1.0
            if phase >= 32.0:
                phase -= 32.0
            step = int(phase)
            v = TRIANGLE_STEPS[step]
            prev = TRIANGLE_STEPS[step - 1 if step > 0 else 31]
            if v != prev:
                out_t[m] = t
                out_v[m] = v
                m += 1
    return out_t[:m], out_v[:m], phase


@njit(cache=True)
def _lfsr(reg, short):
    """One clock of the noise channel's 15-bit shift register: feedback from bit 0 and bit 1 (long, a
    32767-step sequence) or bit 6 (short: 93 steps)."""
    tap = 6 if short else 1
    fb = (reg ^ (reg >> tap)) & 1
    return (reg >> 1) | (fb << 14)


@njit(cache=True)
def _noise_events(t0, t1, rate, short, vol, reg):
    """The noise channel's changes of level (time, 0..15) from its frames: each a span, a clock rate (Hz),
    the mode and a volume. The register runs on between frames at the last rate, as the chip's does."""
    cap = 16
    for k in range(t0.shape[0]):
        cap += int((t1[k] - t0[k]) * rate[k] + 2.0) + 2
    out_t = np.empty(cap)
    out_v = np.empty(cap)
    m = 0
    level = 0.0
    last_end = -1.0
    last_rate = 0.0
    last_short = False
    next_clock = 0.0
    for k in range(t0.shape[0]):
        t = t0[k]
        r = rate[k]
        if last_end >= 0.0 and t > last_end and last_rate > 0.0:
            # the silence between: the register kept shifting (only its place in its cycle matters)
            clocks = int((t - last_end) * last_rate) % (2883 if last_short else 32767)
            for _ in range(clocks):
                reg = _lfsr(reg, last_short)
        if r != last_rate or t > last_end:
            next_clock = t + 1.0 / r
        v = vol[k]
        new = v if (reg & 1) == 0 else 0.0
        if new != level:
            out_t[m] = t
            out_v[m] = new
            m += 1
            level = new
        while next_clock < t1[k]:
            reg = _lfsr(reg, short[k])
            new = v if (reg & 1) == 0 else 0.0
            if new != level:
                out_t[m] = next_clock
                out_v[m] = new
                m += 1
                level = new
            next_clock += 1.0 / r
        last_end = t1[k]
        last_rate = r
        last_short = short[k]
    return out_t[:m], out_v[:m], reg


@njit(cache=True)
def _mix_tnd(tt, tv, nt, nv, t_start, ref):
    """The triangle's and the noise's changes merged through the chip's shared mixer, less `ref` (the level
    the halted triangle sat at before anything played)."""
    out_t = np.empty(tt.shape[0] + nt.shape[0])
    out_l = np.empty(tt.shape[0] + nt.shape[0])
    i = 0
    j = 0
    m = 0
    t_val = t_start
    n_val = 0.0
    while i < tt.shape[0] or j < nt.shape[0]:
        if j >= nt.shape[0] or (i < tt.shape[0] and tt[i] <= nt[j]):
            time = tt[i]
            t_val = tv[i]
            i += 1
        else:
            time = nt[j]
            n_val = nv[j]
            j += 1
        if t_val <= 0.0 and n_val <= 0.0:
            level = 0.0
        else:
            level = 159.79 / (1.0 / (t_val / 8227.0 + n_val / 12241.0) + 100.0)
        out_t[m] = time
        out_l[m] = level - ref
        m += 1
    return out_t[:m], out_l[:m]


# --- playing a part ---------------------------------------------------------------------------------


def _arts(note) -> set:
    return set(str(note.art).replace("+", " ").split())


def _volume(vel: float) -> int:
    """Velocity to the chip's 4-bit volume: sixteen steps, the softest audible note at 1."""
    v = float(np.clip(vel, 0.0, 1.0))
    return 0 if v <= 0.0 else max(1, int(round(15.0 * v)))


def _scaled(v: int, e: float) -> int:
    """A volume times an envelope's fraction, as a driver multiplies them: never 0 unless one of them is."""
    if v <= 0 or e <= 0.0:
        return 0
    return max(1, int(round(v * e)))


def _hz(pitch):
    return 440.0 * 2.0 ** ((np.asarray(pitch, dtype=np.float64) - 69.0) / 12.0)


def _console(y: np.ndarray, sr: int) -> np.ndarray:
    """The console's output: first-order high-passes at 90 and 440 Hz and a low-pass at 14 kHz."""
    sos = np.vstack([butter(1, 90.0, btype="highpass", fs=sr, output="sos"),
                     butter(1, 440.0, btype="highpass", fs=sr, output="sos"),
                     butter(1, min(14000.0, 0.45 * sr), fs=sr, output="sos")])
    return sosfilt(sos, y)


def _pulse_part(notes, sr: int, length: int, s: dict, make: np.random.Generator) -> np.ndarray:
    bright = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
    ornament = float(np.clip(s.get("ornament", 0.5), 0.0, 1.0))
    default = "50" if bright < 0.35 else "12" if bright > 0.7 else "25"
    # a machine's sound driver: its envelope's shape, its vibrato's speed and delay
    sag = make.uniform(0.7, 0.85)  # where the held volume settles
    vib_rate = make.uniform(5.5, 6.5)
    vib_delay = int(make.integers(12, 20))  # frames
    depth = 0.35 * ornament  # semitones, peak
    end_time = length / sr
    t0, t1, hz, vol, reset, lo, hi = [], [], [], [], [], [], []
    last_pitch = None
    for i, note in enumerate(notes):
        start = note.start
        cut = min(notes[i + 1].start if i + 1 < len(notes) else np.inf, end_time)
        if cut <= start:
            continue
        art = _arts(note)
        duty = next((d for d in ("12", "25", "50", "75") if d in art), default)
        a, b = DUTIES[duty]
        chord = next((ARPS[k] for k in ARPS if k in art), (0,))
        v = _volume(note.vel)
        held = max(1, int(math.ceil(note.dur * FRAME - 1e-9)))
        glide = "glide" in art and last_pitch is not None
        p = float(last_pitch) if glide else float(note.pitch)
        level = v
        k = 0
        while True:
            f0 = start + k / FRAME
            if f0 >= cut:
                break
            if k < held:
                if "pluck" in art:
                    level = _scaled(v, max(0.0, 1.0 - k / 30.0))
                else:
                    level = _scaled(v, max(sag, 1.0 - 0.06 * k))
            else:
                level = max(0, level - 3)  # the driver's release: three steps a frame
            if glide:
                p = note.pitch + (p - note.pitch) * 0.6
            else:
                p = float(note.pitch)
            offset = chord[k % len(chord)]
            if depth > 0.0 and k >= vib_delay:
                fade = min(1.0, (k - vib_delay) / 10.0)
                offset += depth * fade * math.sin(2.0 * math.pi * vib_rate * (k - vib_delay) / FRAME)
            t0.append(f0)
            t1.append(min(f0 + 1.0 / FRAME, cut))
            hz.append(440.0 * 2.0 ** ((p + offset - 69.0) / 12.0))
            vol.append(level)
            reset.append(k == 0 and not glide)
            lo.append(a)
            hi.append(b)
            if level == 0 and k >= held:
                break
            k += 1
        last_pitch = note.pitch
    if not t0:
        return np.zeros(length)
    sr2 = 2.0 * sr
    table = np.array([pulse_level(v) for v in range(16)])
    et, el = _pulse_events(np.array(t0), np.array(t1), np.array(hz), np.array(vol, dtype=np.int64),
                           np.array(reset, dtype=np.bool_), np.array(lo), np.array(hi), table)
    y = osc.decimate2(_staircase(et * sr2, el, 2 * length + PAD))[:length]
    return _console(y, sr) * OUT


def _triangle_frames(notes, end_time: float):
    """The triangle's running frames for a bass part: each note runs from its start until its end or the next
    note, stepping its pitch each frame for a glide or an octave arpeggio."""
    t0, t1, hz = [], [], []
    last_pitch = None
    for i, note in enumerate(notes):
        start = note.start
        stop = min(note.start + note.dur, notes[i + 1].start if i + 1 < len(notes) else np.inf, end_time)
        if stop <= start:
            continue
        art = _arts(note)
        glide = "glide" in art and last_pitch is not None
        chord = ARPS["arp-oct"] if "arp-oct" in art else (0,)
        p = float(last_pitch) if glide else float(note.pitch)
        k = 0
        while True:
            f0 = start + k / FRAME
            if f0 >= stop:
                break
            p = note.pitch + (p - note.pitch) * 0.6 if glide else float(note.pitch)
            t0.append(f0)
            t1.append(min(f0 + 1.0 / FRAME, stop))
            hz.append(440.0 * 2.0 ** ((p + chord[k % len(chord)] - 69.0) / 12.0))
            k += 1
        last_pitch = note.pitch
    return np.array(t0), np.array(t1), np.array(hz)


def _triangle_part(notes, sr: int, length: int) -> np.ndarray:
    t0, t1, hz = _triangle_frames(notes, length / sr)
    if not len(t0):
        return np.zeros(length)
    sr2 = 2.0 * sr
    tt, tv, _ = _triangle_events(t0, t1, hz, 0.0)
    ref = tnd_level(15, 0)  # before anything plays the halted triangle sits at its first step
    et, el = _mix_tnd(tt, tv, np.empty(0), np.empty(0), 15.0, ref)
    y = osc.decimate2(_staircase(et * sr2, el, 2 * length + PAD))[:length]
    return _console(y, sr) * OUT


# the drum kit: for the noise channel (clock index 0 fastest .. 15, looped?, volume per frame) and for the
# triangle (frequencies per frame); the noise channel's priority when two strike together
KIT = {
    "snare": dict(noise=(7, False, (1.0, 0.87, 0.73, 0.6, 0.47, 0.33, 0.22, 0.13, 0.07)), tri=(240.0, 180.0),
                  priority=9),
    "clap": dict(noise=(5, False, (1.0, 0.15, 0.9, 0.15, 0.8, 0.6, 0.45, 0.3, 0.18, 0.08)), priority=8),
    "crash": dict(noise=(1, False, tuple(float(x) for x in np.linspace(1.0, 0.05, 45))), priority=7),
    "hat-open": dict(noise=(0, False, tuple(float(x) for x in np.linspace(0.9, 0.08, 12))), priority=6),
    "cowbell": dict(noise=(3, True, (1.0, 0.8, 0.62, 0.47, 0.33, 0.2, 0.1)), priority=5),
    "rim": dict(noise=(4, True, (1.0,)), priority=4),
    "hat": dict(noise=(0, False, (0.8, 0.45, 0.15)), priority=3),
    "kick": dict(noise=(12, False, (0.6,)), tri=(250.0, 160.0, 105.0, 78.0, 64.0, 56.0), priority=2),
    "tom-hi": dict(noise=(9, False, (0.4,)), tri=(330.0, 290.0, 260.0, 240.0, 226.0, 216.0, 210.0, 206.0),
                   priority=1),
    "tom-mid": dict(noise=(10, False, (0.4,)), tri=(220.0, 192.0, 172.0, 160.0, 151.0, 145.0, 141.0, 139.0),
                    priority=1),
    "tom-lo": dict(noise=(11, False, (0.4,)), tri=(150.0, 128.0, 113.0, 104.0, 98.0, 94.0, 92.0, 91.0),
                   priority=1),
}


def _drum_part(notes, sr: int, length: int, make: np.random.Generator) -> np.ndarray:
    end_time = length / sr
    # a machine's drum driver: its snare and hats a clock step either way, its kick a little higher or lower
    shift = {"snare": int(make.integers(-1, 2)), "hat": int(make.integers(0, 2)), "hat-open": 0, "crash": 0}
    shift["hat-open"] = shift["hat"]
    kick_scale = float(np.exp(make.normal(0.0, 0.06)))
    hits = []
    for note in notes:
        piece = str(note.art) if str(note.art) in KIT else None
        if piece is None or note.start >= end_time:
            continue
        hits.append((note.start, piece, float(np.clip(note.vel, 0.0, 1.0))))
    hits.sort(key=lambda h: (h[0], -KIT[h[1]]["priority"]))
    # each channel plays one thing at a time: of two that strike together the higher priority takes it, and
    # a later one cuts what is sounding
    noise, tri = [], []
    for start, piece, vel in hits:
        spec = KIT[piece]
        if "noise" in spec and not (noise and abs(noise[-1][0] - start) < 0.002):
            noise.append((start, piece, vel))
        if "tri" in spec and not (tri and abs(tri[-1][0] - start) < 0.002):
            tri.append((start, piece, vel))
    n0, n1, rate, short, vol = [], [], [], [], []
    for i, (start, piece, vel) in enumerate(noise):
        cut = min(noise[i + 1][0] if i + 1 < len(noise) else np.inf, end_time)
        index, looped, env = KIT[piece]["noise"]
        index = int(np.clip(index + shift.get(piece, 0), 0, 15))
        v = _volume(vel)
        for k, e in enumerate(env + (0.0,)):
            f0 = start + k / FRAME
            if f0 >= cut:
                break
            n0.append(f0)
            n1.append(min(f0 + 1.0 / FRAME, cut))
            rate.append(CPU / NOISE_PERIODS[index])
            short.append(looped)
            vol.append(_scaled(v, e))
    t0, t1, thz = [], [], []
    for i, (start, piece, vel) in enumerate(tri):
        cut = min(tri[i + 1][0] if i + 1 < len(tri) else np.inf, end_time)
        sweep = KIT[piece]["tri"]
        if piece == "kick":  # harder, longer: the driver's sweep for an accent runs further down
            sweep = tuple(f * kick_scale for f in sweep[: 3 + int(round(3 * vel))])
        for k, f in enumerate(sweep):
            f0 = start + k / FRAME
            if f0 >= cut:
                break
            t0.append(f0)
            t1.append(min(f0 + 1.0 / FRAME, cut))
            thz.append(f)
    if not n0 and not t0:
        return np.zeros(length)
    sr2 = 2.0 * sr
    tt, tv, _ = _triangle_events(np.array(t0), np.array(t1), np.array(thz), 0.0) if t0 else (np.empty(0),) * 3
    nt, nv, _ = _noise_events(np.array(n0), np.array(n1), np.array(rate), np.array(short, dtype=np.bool_),
                              np.array(vol, dtype=np.float64), 1) if n0 else (np.empty(0), np.empty(0), 1)
    et, el = _mix_tnd(tt, tv, nt, nv, 15.0, tnd_level(15, 0))
    y = osc.decimate2(_staircase(et * sr2, el, 2 * length + PAD))[:length]
    return _console(y, sr) * OUT


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A chip part: mono, dry, `length` samples, before placement and level."""
    if name not in SPEC:
        raise ValueError(f"no such instrument: {name}")
    s = dict(settings or {})
    playing = sorted((n for n in notes if n.dur > 0 and 0 <= n.start * sr < length), key=lambda n: (n.start, n.pitch))
    if name == "chip":
        return _pulse_part(playing, sr, length, s, make)
    if name == "chip-bass":
        return _triangle_part(playing, sr, length)
    return _drum_part(playing, sr, length, make)
