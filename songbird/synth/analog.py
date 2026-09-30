"""Analog synthesizers: oscillators, a ladder filter, envelopes and a chorus, the subtractive way.

A subtractive synthesizer starts from waveforms rich in harmonics and
carves them. Its oscillators are sawtooths (every harmonic at 1/n) and
pulses (a pulse of width d loses every harmonic that 1/d divides); each is
an analog circuit whose tuning wanders with its temperature, a few cents
over some seconds, and a patch with two or three of them detunes them a few
cents so they beat slowly against each other: the thickness of an analog
synth. Their sum goes into a resonant low-pass, here the transistor ladder
of the Moog (four one-pole stages, 24 dB an octave, the output fed back to
the input: at a loop gain of 4 it rings at its cutoff by itself, and the
more it resonates the more bass it loses, 1/(1 + k) at DC). The input pair
of transistors saturates like tanh (Huovilainen 2004), which is where a
driven ladder's warmth comes from. Two envelopes, each four RC segments
(attack, decay, sustain, release: a capacitor charging and discharging, so
an attack is aimed past its peak and rises almost straight), move the
cutoff and the loudness; the cutoff also follows the keyboard. A monophonic
synth glides between legato notes: its pitch is an RC lag toward the new
note, 20 to 80 ms, and a note that follows a released one starts again
(fingered portamento). A polyphonic one gives each key a voice, and some
put the whole instrument through a bucket-brigade chorus (the Juno's: two
delay lines of a few milliseconds swept by slow triangle LFOs, one per
side, in antiphase, added to the dry signal).

How it is modelled. The oscillators are osc.py's four-point polyBLEP saw
and pulse, drawn inside the voice's loop with osc._edges (the same residual
osc.saw and osc.pulse use: a test holds them sample-identical), at twice
the sample rate with the filter; each part is brought down once with
osc.decimate2. Each oscillator's pitch is the note times a control track
of its detune, the machine's trim and a slow drift (osc.drift, 0.1 to 0.3
Hz). A width-modulated pulse is the difference of two saws half its width
either side of its phase, so both edges move and its centre stays put: its
width changes and its pitch doesn't (a pulse with one edge fixed wobbles
the pitch of every harmonic by half the width's rate of change, 2 cents
at A3 at the pad's rate). The ladder is four trapezoidal one-poles with
zero-delay feedback: each stage's output is G^i times the saturated input
plus what the integrators hold, so the loop's one nonlinear equation, u + k
G^4 sat(u) = x - k S, is solved outright (k G^4 is under 0.14 below 18 kHz,
so its linear solution and at most one fixed-point step suffice) and the
cutoff is exact: the self-oscillating ladder rings within 0.05 cents of its
cutoff from C3 to C7 (a tanh-like rational saturator limits it). Envelopes
and glide are per-sample RC segments; the cutoff, its tan() prewarping
and the oscillators' ratios are updated every 16 samples and glided
between. Each voice is one numba loop over its phrase (the notes between
two silences).

The instruments. synth-pad: a width-modulated pulse (0.55 Hz) with two
saws half as loud either side of it, 1 cent apart on a new machine and 12
on a worn one, a ladder at resonance 0.18 opening over 0.4 s, eight voices
(a voice still sounding a key's pitch takes that key again; else a free
one; else the one released longest ago), through the chorus.
synth-bass: a saw, a second saw 1 to 7 cents above it at 40%, a square an
octave down; a snappy filter envelope (2.8 octaves, falling 90% in 0.25 s)
at resonance 0.35; glide 45 ms. synth-solo: two saws and a 4' square, a
ladder that tracks the keyboard by 75%, glide 70 ms, and a vibrato from
ornament (up to ±30 cents at 5.1 to 5.9 Hz) that comes in after 0.3 s and
fades in over 0.4. synth-arp: a saw and a 40% pulse, a resonant (0.4)
filter that snaps shut in 0.17 s, six voices. sub-bass: a sine with its
2nd harmonic 15 dB and its 3rd 30 dB down (brightness moves them ±4 and ±6
dB), run at the plain rate since nothing in it comes near half the sample
rate, its phase set to zero at every new attack (a note still sounding is
faded out over 3 ms first), so every attack, and every attack under a
kick, is the same waveform.

Measured (tests/test_analog.py): in tune within 1.2 cents at wear 0 over
twelve machines (a detuned pair sits under an oscillator on the note, so a
beat's null can't pull the fundamental); drift at the default wear ±3 to 4
cents for the ensemble; above the cutoff the ladder falls 21 to 23 dB an
octave; folded (non-harmonic) content at C7 with the filter wide open -74
dB on the solo and -78 on the arp (the input stage's drive is kept low
there: at twice the drive the saturator's products fold to -68); releases
T60 0.8 s (pad), 83 ms (bass), 183 ms (solo), 162 ms (arp), 77 ms (sub);
legato glides 90% of the way in 39 (bass), 62 (solo) and 59 ms (sub),
within a decibel of level, while a detached note's release is followed by a
new attack; the chorus's lines swing 3.2 to 4.7 ms, a pitch swing of ±3.6
cents; velocity 0.3 to 0.9 is 8 to 10 dB louder and 0.3 to 0.46 octave
brighter (the filter envelope's amount and the cutoff follow it); the sub's
attacks correlate 1.00000 note to note. A three-minute part costs 0.3 s
(sub) to 5 s (pad, eight voices) of CPU on an efficiency core.

Settings: brightness moves every cutoff ±0.8 octave (the sub's harmonics);
wear widens the detune, the drift (0.15 cents to 5 at wear 1, per
oscillator) and the trim, and adds a breath of noise into the filter;
ornament is the solo's vibrato; body is not used. make gives each machine
its own trims, filter and envelope tolerances, LFO rates and chorus.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit
from scipy.signal import sosfilt

from . import osc, touch
from .iir import butter

SPEC = {
    "synth-pad": dict(
        family="synth",
        role="comping",
        register=(36, 91),
        place=(0.0, 0.9),
        level=0.405,
        poly=True,
        articulations={
            "": "a held pad: two detuned saws and a slowly width-modulated pulse, a soft attack, the filter "
                "opening over the first half second, a long release, through the stereo chorus",
            "swell": "a slow swell: the amplitude and the filter open over about a second",
            "stab": "a chord stab: an instant attack, the filter snapping shut, gone in about 0.3 s",
        },
        about="a polyphonic analog pad (a Juno or an OB): detuned saws and PWM through a 24 dB ladder low-pass, "
              "eight voices, a BBD-style stereo chorus",
        brighter=0.3,
    ),
    "synth-bass": dict(
        family="synth",
        role="bass",
        register=(28, 60),
        place=(0.0, 0.0),
        level=0.6,
        poly=False,
        articulations={
            "": "fingered legato: touching or overlapping notes glide into each other without a new attack; "
                "a detached note starts again",
            "accent": "accented: louder, with a sharper, brighter filter envelope",
            "short": "staccato: the amplitude and filter fall away in about a tenth of a second",
            "glide": "slides into this note from the last one even when detached",
        },
        about="a monophonic analog bass (a Minimoog or an SH): two saws and a square an octave down through a "
              "resonant ladder low-pass with a snappy filter envelope, and glide",
        brighter=0.4,
    ),
    "synth-solo": dict(
        family="synth",
        role="lead",
        register=(48, 96),
        place=(0.12, 0.0),
        level=0.574,
        poly=False,
        loudness=-22.0,
        articulations={
            "": "legato glides without a new attack, detached notes start again; long notes take a delayed "
                "vibrato (its depth from ornament)",
            "accent": "accented: louder and brighter at the attack",
            "glide": "slides into this note from the last one even when detached",
            "bend": "scoops up into the note from a whole tone below, as a pitch wheel would",
            "short": "staccato",
        },
        about="a monophonic analog solo synthesizer (a Minimoog lead): two detuned saws and a pulse through a "
              "ladder low-pass, glide, a delayed vibrato",
        brighter=0.4,
    ),
    "synth-arp": dict(
        family="synth",
        role="comping",
        register=(48, 96),
        place=(-0.25, 0.0),
        level=0.574,
        poly=True,
        articulations={
            "": "a pluck: the resonant filter snaps shut in about 0.2 s and the tone holds quietly under the key",
            "accent": "accented: louder, and the filter opens further",
            "short": "a very short blip",
        },
        about="a polyphonic analog pluck for arpeggios: a saw and a pulse through a resonant ladder low-pass "
              "with a fast filter envelope",
        brighter=0.35,
    ),
    "sub-bass": dict(
        family="synth",
        role="bass",
        register=(24, 50),
        place=(0.0, 0.0),
        level=0.314,
        poly=False,
        loudness=-27.0,
        articulations={
            "": "a held sub: a sine with a touch of its octave, its phase reset at every new attack so each "
                "note (and each note with a kick) starts alike",
            "short": "a short, plucked sub",
            "glide": "slides into this note from the last one (legato notes always do)",
            "boom": "an 808-style sub: a thump of pitch at the attack and a long decay instead of a sustain",
        },
        about="a sub bass: a sine with a little second and third harmonic, phase-reset attacks, glide",
    ),
}

DEFAULTS = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0)

SAW, PULSE, TRIANGLE = 0, 1, 2
WAVES = {"saw": SAW, "pulse": PULSE, "triangle": TRIANGLE}

# Each preset: its oscillators as (wave, octave, detune share, level, pulse width, PWM depth); the detune in
# cents between oscillators at wear 0 and added at wear 1; drift (cents, the knots' spread) at wear 0 and
# added at wear 1; the filter's cutoff (Hz) at the reference note and brightness 0.5, its key tracking,
# resonance (1 self-oscillates), drive into the ladder; the envelopes as (attack s, decay s to 90%,
# sustain, release T60 s); the filter envelope's amount (octaves) scaled by fvel[0] + fvel[1] * velocity;
# the velocity's dynamic span (dB, touch.gain); glide (s to 90% of the interval, legato notes only).
PRESETS = {
    "synth-pad": dict(
        oscs=(("pulse", 0, 0.0, 1.0, 0.5, 0.16), ("saw", 0, -0.5, 0.5, 0.5, 0.0), ("saw", 0, 0.5, 0.5, 0.5, 0.0)),
        detune=(1.0, 11.0), drift=(0.15, 5.0), pwm_rate=0.55,
        cutoff=1100.0, ref=60.0, track=0.6, resonance=0.18, drive=0.45,
        aenv=(0.15, 1.2, 0.85, 0.8), fenv=(0.4, 1.6, 0.45, 0.8), famount=1.2, fvel=(0.4, 1.0), vcut=0.6,
        span=12.0, voices=8, chorus=True, glide=0.0, noise=0.008, out=0.15,
    ),
    "synth-bass": dict(
        oscs=(("saw", 0, 0.0, 1.0, 0.5, 0.0), ("saw", 0, 1.0, 0.4, 0.5, 0.0), ("pulse", -1, 0.0, 0.8, 0.5, 0.0)),
        detune=(1.0, 6.0), drift=(0.15, 5.0), pwm_rate=0.0,
        cutoff=320.0, ref=36.0, track=0.5, resonance=0.35, drive=0.6,
        aenv=(0.002, 0.8, 0.7, 0.08), fenv=(0.001, 0.25, 0.12, 0.1), famount=2.8, fvel=(0.3, 1.2), vcut=1.0,
        span=14.0, voices=1, chorus=False, glide=0.045, noise=0.006, out=0.3,
    ),
    "synth-solo": dict(
        oscs=(("saw", 0, 0.0, 1.0, 0.5, 0.0), ("saw", 0, 1.0, 0.45, 0.5, 0.0), ("pulse", 1, 0.0, 0.25, 0.5, 0.0)),
        detune=(1.5, 6.0), drift=(0.15, 5.0), pwm_rate=0.0,
        cutoff=1300.0, ref=60.0, track=0.75, resonance=0.28, drive=0.35,
        aenv=(0.006, 0.4, 0.88, 0.18), fenv=(0.004, 0.45, 0.45, 0.2), famount=1.6, fvel=(0.45, 0.9), vcut=0.4,
        span=12.0, voices=1, chorus=False, glide=0.07, noise=0.006, out=0.3,
        vibrato=(30.0, 5.5, 0.3, 0.4),  # cents at ornament 1, Hz, delay s, fade-in s
    ),
    "synth-arp": dict(
        oscs=(("saw", 0, 0.0, 1.0, 0.5, 0.0), ("pulse", 0, 1.0, 0.3, 0.4, 0.0)),
        detune=(0.5, 6.0), drift=(0.15, 5.0), pwm_rate=0.0,
        cutoff=550.0, ref=60.0, track=0.85, resonance=0.4, drive=0.35,
        aenv=(0.0015, 0.45, 0.22, 0.16), fenv=(0.001, 0.17, 0.04, 0.15), famount=3.2, fvel=(0.3, 1.2), vcut=1.0,
        span=16.0, voices=6, chorus=False, glide=0.0, noise=0.006, out=0.3,
    ),
}

K_MAX = 4.25  # the ladder's feedback at full resonance: a little past the 4 where it starts to sing
COMP = 0.5  # how much of the bass the ladder loses to its resonance is given back (the Moog gives none)
CTRL = 32  # drift and pulse width are control tracks, one value every CTRL samples at twice the rate
AC_HZ = 8.0  # the output stage's coupling capacitor
ATTACK_TARGET = 1.3  # an attack is an RC charge aimed past the peak, so it rises nearly straight and stops at 1


# --- the ladder -----------------------------------------------------------------------------


@njit(cache=True, nogil=True)
def _sat(v):
    """A soft saturator shaped like tanh: slope 1 at 0, reaching ±1 smoothly at ±3 (a rational fit)."""
    if v >= 3.0:
        return 1.0
    if v <= -3.0:
        return -1.0
    v2 = v * v
    return v * (27.0 + v2) / (27.0 + 9.0 * v2)


@njit(cache=True, nogil=True)
def _ladder_step(x, G, k, st):
    """One sample of the four-pole ladder with zero-delay feedback; st holds the four integrators.

    The stages are trapezoidal one-poles (g = tan(pi fc / fs), G = g / (1 + g)): stage i puts out
    G y_(i-1) + (1 - G) s_i, so the last one is G^4 t plus what the integrators hold, S, whatever the
    input t. The input stage saturates, t = sat(u), with u = x - k y4 (the Moog's input pair taking the
    difference of the input and the fed-back output): u + k G^4 sat(u) = x - k S. k G^4 is under 0.14 at
    any cutoff below 18 kHz at twice the rate, so the linear solution and at most one fixed-point step
    solve it closely; then each stage is G^i t plus its share of S, all four at once."""
    h = 1.0 - G
    g2 = G * G
    g3 = g2 * G
    g4 = g2 * g2
    a1 = h * st[0]
    a2 = h * st[1]
    a3 = h * st[2]
    a4 = h * st[3]
    p2 = G * a1 + a2
    p3 = g2 * a1 + G * a2 + a3
    p4 = g3 * a1 + g2 * a2 + G * a3 + a4
    c = k * g4
    d = x - k * p4
    u = d / (1.0 + c)
    if c > 0.002:
        u = d - c * _sat(u)
    t = _sat(u)
    y1 = G * t + a1
    y2 = g2 * t + p2
    y3 = g3 * t + p3
    y4 = g4 * t + p4
    st[0] = 2.0 * y1 - st[0]
    st[1] = 2.0 * y2 - st[1]
    st[2] = 2.0 * y3 - st[2]
    st[3] = 2.0 * y4 - st[3]
    return y4


@njit(cache=True, nogil=True)
def _ladder(x, G, k, drive):
    n = x.shape[0]
    y = np.empty(n)
    st = np.zeros(5)
    gain = (1.0 + COMP * k) / drive
    for i in range(n):
        y[i] = _ladder_step(drive * x[i], G[i], k, st) * gain
    return y


def ladder(x: np.ndarray, cutoff, resonance: float, sr: float, drive: float = 0.5) -> np.ndarray:
    """The ladder low-pass alone: x through a cutoff (Hz, a number or a track) at resonance 0..1 (1 sings)."""
    fc = np.minimum(np.broadcast_to(np.asarray(cutoff, dtype=np.float64), x.shape), 0.45 * sr)
    g = np.tan(np.pi * fc / sr)
    return _ladder(np.ascontiguousarray(x, dtype=np.float64), np.ascontiguousarray(g / (1.0 + g)),
                   K_MAX * float(resonance), float(drive))


# --- the voice ------------------------------------------------------------------------------


@njit(cache=True, nogil=True)
def _wave(kind, q, dt, d):
    """One sample of a saw (kind 0) or a pulse of width d (kind 1) at phase q, dt of a cycle a sample:
    exactly what osc.saw and osc.pulse draw there."""
    if kind == 0:
        return 2.0 * q - 1.0 - 2.0 * osc._edges(q, dt)
    if d < 0.02:
        d = 0.02
    elif d > 0.98:
        d = 0.98
    y = 1.0 if q < d else -1.0
    y += 2.0 * osc._edges(q, dt)
    r = q - d
    if r < 0.0:
        r += 1.0
    y -= 2.0 * osc._edges(r, dt)
    return y - (2.0 * d - 1.0)


@njit(cache=True, nogil=True)
def _voice(buf, at, n, on, off, pitch, retrig, glide, bend, amp, env, famt, fbase, kinds, levels, shifted, ratio,
           pw, phases, gcoef, bcoef, vib, track, pref, k, drive, noise, seed, inv_sr2):
    """One voice's phrase, sample by sample at twice the rate, added into buf from `at`; returns the samples
    it sounded for.

    Events: each note's start and (unless the next note carries on) end, in samples from the phrase's
    start, whether it attacks again (retrig), glides (an RC lag toward it) or bends up from a tone below.
    The waves are osc.saw's and osc.pulse's own band-limited steps (osc._edges), one per wave, each at the
    pitch times its oscillator's control-rate ratio (detune and drift, every CTRL samples) plus, for the two
    saws of a modulated pulse, a shift in Hz; then the ladder and the amplifier. env: per note, the amp
    envelope's attack, decay, sustain, release coefficients and the filter envelope's."""
    nev = on.shape[0]
    n_w = kinds.shape[0]
    ph = phases.copy()
    lad = np.zeros(4)
    gain = (1.0 + COMP * k) / drive
    depth, rate, delay, fade = vib[0], vib[1], vib[2], vib[3]
    cur_p = pitch[0]
    target = pitch[0]
    coef = 1.0
    since = 0
    ea = 0.0
    astg = 0
    ef = 0.0
    fstg = 0
    gate = 0
    cur = 0
    j = 0
    vg = amp[0]
    big_g = 0.0
    dg = 0.0
    base = 0.0
    last_p = -1e9
    x_state = seed
    hz = np.zeros(n_w)
    duty = np.zeros(n_w)
    for i in range(n):
        while j < nev and on[j] <= i:
            if glide[j]:
                target = pitch[j]
                coef = gcoef
            elif bend[j]:
                cur_p = pitch[j] - 2.0
                target = pitch[j]
                coef = bcoef
            else:
                cur_p = pitch[j]
                target = pitch[j]
            since = i
            if retrig[j] or gate == 0:
                if ea < 1e-3:
                    vg = amp[j]
                astg = 1
                fstg = 1
            gate = 1
            cur = j
            j += 1
        if gate == 1 and off[cur] >= 0 and i >= off[cur]:
            gate = 0
            astg = 3
            fstg = 3
        # the pitch: glides and bends are RC lags, the vibrato comes in after its delay
        cur_p += (target - cur_p) * coef
        p = cur_p
        if depth > 0.0:
            tt = (i - since) * inv_sr2 - delay
            if tt > 0.0:
                w = tt / fade if tt < fade else 1.0
                p += 0.01 * depth * w * math.sin(2.0 * math.pi * rate * tt)
        if p != last_p:
            base = 440.0 * math.exp(0.057762265046662105 * (p - 69.0))
            last_p = p
        # the envelopes: RC segments
        if astg == 1:
            ea += (ATTACK_TARGET - ea) * env[cur, 0]
            if ea >= 1.0:
                ea = 1.0
                astg = 2
        elif astg == 2:
            ea += (env[cur, 2] - ea) * env[cur, 1]
        elif astg == 3:
            ea -= ea * env[cur, 3]
        if fstg == 1:
            ef += (ATTACK_TARGET - ef) * env[cur, 4]
            if ef >= 1.0:
                ef = 1.0
                fstg = 2
        elif fstg == 2:
            ef += (env[cur, 6] - ef) * env[cur, 5]
        elif fstg == 3:
            ef -= ef * env[cur, 7]
        vg += (amp[cur] - vg) * 0.004
        # every 16 samples: the cutoff (glided between) and each wave's detune, drift and width
        if (i & 15) == 0:
            lf = fbase[cur] + track * (p - pref) / 12.0 + famt[cur] * ef
            fc = math.exp(0.6931471805599453 * lf)
            if fc < 16.0:
                fc = 16.0
            elif fc > 18000.0:
                fc = 18000.0
            g = math.tan(math.pi * fc * inv_sr2)
            tg = g / (1.0 + g)
            if i == 0:
                big_g = tg
                dg = 0.0
            else:
                dg = (tg - big_g) * 0.0625
            c = i / CTRL
            kc = int(c)
            fr = c - kc
            for w in range(n_w):
                hz[w] = ratio[w, kc] + (ratio[w, kc + 1] - ratio[w, kc]) * fr
                duty[w] = pw[w, kc] + (pw[w, kc + 1] - pw[w, kc]) * fr
        big_g += dg
        # the waves, as osc.saw and osc.pulse draw them
        x = 0.0
        for w in range(n_w):
            f = base * hz[w]
            if shifted[w]:
                f += duty[w]
            dt = f * inv_sr2
            if dt > 0.25:
                dt = 0.25
            q = ph[w]
            x += levels[w] * _wave(kinds[w], q, dt, duty[w])
            q += dt
            if q >= 1.0:
                q -= 1.0
            ph[w] = q
        if noise > 0.0:
            x_state ^= x_state >> np.uint64(12)
            x_state ^= x_state << np.uint64(25)
            x_state ^= x_state >> np.uint64(27)
            rr = (x_state * np.uint64(2685821657736338717)) >> np.uint64(11)
            x += noise * (rr * (2.0 / 9007199254740992.0) - 1.0)
        buf[at + i] += _ladder_step(drive * x, big_g, k, lad) * gain * ea * vg
        if gate == 0 and j >= nev and ea < 3e-5:
            return i + 1
    return n


# --- the sub bass -------------------------------------------------------------------------------


@njit(cache=True, nogil=True)
def _sub(buf, at, n, on, off, pitch, retrig, glide, amp, env, thump, gcoef, tcoef, h2, h3, drift, dstep, fade,
         inv_sr):
    """A sub bass phrase at the plain rate: a sine and a little of its 2nd and 3rd harmonics, the phase set to
    zero at every retriggered attack (after a fade of `fade` samples if the last note still sounds)."""
    nev = on.shape[0]
    phase = 0.0
    cur_p = pitch[0]
    target = pitch[0]
    coef = gcoef
    ea = 0.0
    stage = 0
    gate = 0
    cur = 0
    j = 0
    for i in range(n):
        while j < nev and on[j] <= i:
            if retrig[j]:
                phase = 0.0
                ea = 0.0
                stage = 1
                if thump[j] != 0.0:
                    cur_p = pitch[j] + thump[j]
                    coef = tcoef
                elif glide[j]:
                    coef = gcoef
                else:
                    cur_p = pitch[j]
            elif gate == 0:
                stage = 1
                coef = gcoef
            else:
                coef = gcoef
            target = pitch[j]
            gate = 1
            cur = j
            j += 1
        if gate == 1 and off[cur] >= 0 and i >= off[cur]:
            gate = 0
            stage = 3
        # a retrigger coming: fade what still sounds so the phase can start again from zero
        w = 1.0
        if j < nev and retrig[j] and on[j] - i <= fade and ea > 0.0:
            w = 0.5 - 0.5 * math.cos(math.pi * (on[j] - i) / fade)
        if stage == 1:
            ea += (ATTACK_TARGET - ea) * env[cur, 0]
            if ea >= 1.0:
                ea = 1.0
                stage = 2
        elif stage == 2:
            ea += (env[cur, 2] - ea) * env[cur, 1]
        elif stage == 3:
            ea -= ea * env[cur, 3]
        cur_p += (target - cur_p) * coef
        c = i / dstep
        kk = int(c)
        fr = c - kk
        cents = drift[kk] * (1.0 - fr) + drift[kk + 1] * fr
        f = 440.0 * 2.0 ** ((cur_p - 69.0 + 0.01 * cents) / 12.0)
        s = math.sin(2.0 * math.pi * phase)
        co = math.cos(2.0 * math.pi * phase)
        y = s + h2 * 2.0 * s * co - h3 * s * (3.0 - 4.0 * s * s)
        buf[at + i] += y * ea * amp[cur] * w
        phase += f * inv_sr
        if phase >= 1.0:
            phase -= 1.0
        if gate == 0 and j >= nev and ea < 1e-5:
            return i + 1
    return n


# --- the chorus ---------------------------------------------------------------------------------


@njit(cache=True, nogil=True)
def _delays(x, d1, d2):
    """x read through two time-varying delays (samples), cubic Hermite interpolation."""
    n = x.shape[0]
    w = np.zeros((n, 2))
    for i in range(n):
        for c in range(2):
            pos = i - (d1[i] if c == 0 else d2[i])
            k = int(math.floor(pos))
            f = pos - k
            if k - 1 < 0 or k + 2 >= n:
                continue
            xm = x[k - 1]
            x0 = x[k]
            x1 = x[k + 1]
            x2 = x[k + 2]
            c1 = 0.5 * (x1 - xm)
            c2 = xm - 2.5 * x0 + 2.0 * x1 - 0.5 * x2
            c3 = 0.5 * (x2 - xm) + 1.5 * (x0 - x1)
            w[i, c] = ((c3 * f + c2) * f + c1) * f + x0
    return w


def _triangle_lfo(t: np.ndarray, rate: float, phase: float) -> np.ndarray:
    p = (t * rate + phase) % 1.0
    return 1.0 - 4.0 * np.abs(p - 0.5)


def chorus_delays(n: int, sr: float, centre: float, depth: float, rates=(0.5, 0.85), mix=0.6,
                  phases=(0.0, 0.0)) -> tuple[np.ndarray, np.ndarray]:
    """The two delay tracks (samples): centre ± depth (s), swept by two triangle LFOs, the second line in
    antiphase to the first. `mix` is the share of the first LFO."""
    t = np.arange(n) / sr
    sweep = mix * _triangle_lfo(t, rates[0], phases[0]) + (1.0 - mix) * _triangle_lfo(t, rates[1], phases[1])
    return (centre + depth * sweep) * sr, (centre - depth * sweep) * sr


def chorus(x: np.ndarray, sr: float, centre: float = 0.004, depth: float = 0.0008, rates=(0.5, 0.85),
           mix: float = 0.6, phases=(0.0, 0.0), wet: float = 0.8) -> np.ndarray:
    """A BBD-style stereo chorus: the dry signal in both channels, plus on each side a copy through a
    bucket-brigade delay swept by triangle LFOs (the two sides in antiphase), band-limited as a BBD's
    clock filters are. Returns (n, 2)."""
    d1, d2 = chorus_delays(len(x), sr, centre, depth, rates, mix, phases)
    w = _delays(np.ascontiguousarray(x, dtype=np.float64), d1, d2)
    w = sosfilt(butter(2, 9000.0, fs=sr, output="sos"), w, axis=0)
    return (x[:, None] + wet * w) / (1.0 + 0.5 * wet)


# --- playing a part -----------------------------------------------------------------------------


def _coef(seconds: float, sr: float, span: float) -> float:
    """Per-sample coefficient of an RC segment that covers `span` nepers in `seconds`."""
    return float(1.0 - np.exp(-span / max(seconds * sr, 1.0)))


def _arts(note) -> set:
    return set(str(note.art).replace("+", " ").split())


class _Machine:
    """One machine's synthesizer: its preset set up by the band's settings, with the maker's own tolerances."""

    def __init__(self, name: str, make: np.random.Generator, settings: dict):
        s = {**DEFAULTS, **settings}
        self.name = name
        self.brightness = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
        self.wear = float(np.clip(s.get("wear", 0.25), 0.0, 1.0))
        self.ornament = float(np.clip(s.get("ornament", 0.5), 0.0, 1.0))
        p = PRESETS.get(name)
        self.p = p
        if p is None:
            return
        n_osc = len(p["oscs"])
        # a machine's oscillators are trimmed a little differently, its filter and envelopes are within
        # their components' tolerances, its LFOs run at their own rates
        self.trim = make.normal(0.0, 0.2 + 2.5 * self.wear, n_osc)
        self.cutoff_trim = float(make.normal(0.0, 0.08))
        self.res_trim = float(make.normal(0.0, 0.03))
        self.time_trim = np.exp(make.normal(0.0, 0.06, 8))
        self.drift_rates = make.uniform(0.1, 0.3, n_osc)
        self.pwm_rate = p["pwm_rate"] * float(np.exp(make.normal(0.0, 0.1)))
        self.glide = p["glide"] * float(np.exp(make.normal(0.0, 0.1)))
        vib = p.get("vibrato", (0.0, 5.5, 0.3, 0.4))
        self.vibrato = np.array([vib[0] * self.ornament, vib[1] + make.uniform(-0.4, 0.4), vib[2], vib[3]])
        self.chorus_centre = make.uniform(0.0033, 0.0045)
        self.chorus_depth = (0.55 + 0.4 * self.wear) * 1e-3 * float(np.exp(make.normal(0.0, 0.1)))
        self.chorus_rates = (0.5 * float(np.exp(make.normal(0.0, 0.06))), 0.85 * float(np.exp(make.normal(0.0, 0.06))))
        self.chorus_mix = make.uniform(0.5, 0.7)
        detune = p["detune"][0] + p["detune"][1] * self.wear
        self.offsets = np.array([o[2] * detune for o in p["oscs"]]) + self.trim
        self.octaves = np.array([o[1] for o in p["oscs"]], dtype=np.float64)
        # the waves the voice mixes: each oscillator's, and a width-modulated pulse as two saws (the
        # trailing one less the leading one, half the width either side of the oscillator's phase)
        kinds, owner, levels, widths, signs = [], [], [], [], []
        for o, (wave, _octave, _share, level, width, depth) in enumerate(p["oscs"]):
            if wave == "pulse" and depth > 0.0:
                for sign in (1.0, -1.0):
                    kinds.append(SAW)
                    owner.append(o)
                    levels.append(-sign * level)
                    widths.append((width, depth))
                    signs.append(sign)
            else:
                kinds.append(WAVES[wave])
                owner.append(o)
                levels.append(level)
                widths.append((width, 0.0))
                signs.append(0.0)
        self.kinds, self.owner, self.widths, self.signs = kinds, owner, widths, signs
        self.levels = np.array(levels, dtype=np.float64)
        self.shifted = np.array([sg != 0.0 for sg in signs], dtype=np.bool_)
        self.drift = p["drift"][0] + p["drift"][1] * self.wear ** 0.7
        self.k = K_MAX * float(np.clip(p["resonance"] + self.res_trim, 0.0, 1.0))
        self.noise = p["noise"] * self.wear

    def note_params(self, note, sr2: float):
        """(amplitude, the eight envelope coefficients, filter envelope amount, log2 base cutoff) of a note."""
        p = self.p
        art = _arts(note)
        vel = float(np.clip(note.vel, 0.0, 1.0))
        a_att, a_dec, a_sus, a_rel = p["aenv"]
        f_att, f_dec, f_sus, f_rel = p["fenv"]
        tt = self.time_trim
        amount = p["famount"]
        gain = touch.gain(vel, p["span"])
        if "accent" in art:
            gain *= 10 ** (3.5 / 20.0)
            amount += 1.5
            f_dec *= 0.6
        if "short" in art:
            a_dec, a_sus = min(a_dec, 0.1), 0.0
            f_dec, f_sus = f_dec * 0.5, f_sus * 0.3
            a_rel = min(a_rel, 0.08)
        if "stab" in art:
            a_att, a_dec, a_sus = 0.004, 0.3, 0.0
            f_att, f_dec, f_sus = 0.002, 0.22, 0.0
            amount += 0.8
        if "swell" in art:
            a_att *= 8.0
            f_att *= 4.0
            f_dec *= 1.5
        env = np.array([
            _coef(a_att * tt[0], sr2, np.log(ATTACK_TARGET / (ATTACK_TARGET - 1.0))),
            _coef(a_dec * tt[1], sr2, np.log(10.0)),
            a_sus,
            _coef(a_rel * tt[2], sr2, np.log(1000.0)),
            _coef(f_att * tt[3], sr2, np.log(ATTACK_TARGET / (ATTACK_TARGET - 1.0))),
            _coef(f_dec * tt[4], sr2, np.log(10.0)),
            f_sus,
            _coef(f_rel * tt[5], sr2, np.log(1000.0)),
        ])
        amount *= p["fvel"][0] + p["fvel"][1] * vel
        base = (np.log2(p["cutoff"]) + 1.6 * (self.brightness - 0.5) + self.cutoff_trim
                + p["vcut"] * (vel - 0.6))
        return gain, env, amount, base

    def tail(self) -> float:
        """Seconds after a note's end until its release has fallen 100 dB."""
        return self.p["aenv"][3] * 1.1 * 90.0 / 60.0 + 0.01


def _allocate(notes, voices: int, tail: float):
    """Poly: each note to a voice. A voice still sounding the same pitch takes it again; else a free voice;
    else the one released longest ago; else the one holding the oldest note."""
    out = [[] for _ in range(voices)]
    busy = np.full(voices, -np.inf)
    held = np.full(voices, -np.inf)
    started = np.full(voices, -np.inf)
    pitch = [None] * voices
    for note in notes:
        s, e = note.start, note.start + note.dur
        same = [v for v in range(voices) if pitch[v] == note.pitch and busy[v] > s]
        if same:
            v = same[0]
        else:
            free = [v for v in range(voices) if busy[v] <= s]
            if free:
                v = min(free, key=lambda q: busy[q])
            else:
                released = [v for v in range(voices) if held[v] <= s]
                v = min(released, key=lambda q: held[q]) if released else int(np.argmin(started))
        out[v].append(note)
        pitch[v] = note.pitch
        held[v] = e
        busy[v] = e + tail
        started[v] = s
    return [v for v in out if v]


def _phrases(notes, tail: float, legato: bool):
    """A voice's notes split where it falls silent; each note marked (retrigger, glide, gate-off time)."""
    phrases = []
    current = []
    sounding_until = -np.inf
    last_end = -np.inf
    for note in notes:
        s, e = note.start, note.start + note.dur
        if current and s >= sounding_until:
            phrases.append(current)
            current = []
        touching = bool(current) and last_end >= s - 0.002
        glides = legato and bool(current) and (touching or "glide" in _arts(note))
        retrig = not (legato and touching)
        current.append((note, retrig, glides))
        # the newest note decides when the key goes up: one it overlaps no longer releases
        last_end = e
        sounding_until = e + tail
    if current:
        phrases.append(current)
    return phrases


def _render_voiced(name: str, notes, sr: int, length: int, rng: np.random.Generator, machine: _Machine) -> np.ndarray:
    p = machine.p
    sr2 = 2.0 * sr
    n2 = 2 * length
    buf = np.zeros(n2 + 8)
    tail = machine.tail()
    poly = SPEC[name]["poly"]
    legato = not poly
    voices = _allocate(notes, p["voices"], tail) if poly else [list(notes)]
    base_seed = int(rng.integers(1 << 62))
    pwm_phase = float(rng.uniform())
    n_osc = len(p["oscs"])
    gcoef = _coef(machine.glide, sr2, np.log(10.0)) if machine.glide > 0 else 1.0
    bcoef = _coef(0.12, sr2, np.log(10.0))
    for voice in voices:
        for phrase in _phrases(voice, tail, legato):
            first = phrase[0][0]
            p0 = int(round(first.start * sr2))
            if p0 >= n2:
                continue
            gen = np.random.default_rng([base_seed, p0, int(round(first.pitch * 100))])
            count = len(phrase)
            on = np.empty(count, dtype=np.int64)
            off = np.empty(count, dtype=np.int64)
            pitch = np.empty(count)
            retrig = np.empty(count, dtype=np.bool_)
            glide = np.empty(count, dtype=np.bool_)
            bend = np.empty(count, dtype=np.bool_)
            amp = np.empty(count)
            env = np.empty((count, 8))
            famt = np.empty(count)
            fbase = np.empty(count)
            for q, (note, rt, gl) in enumerate(phrase):
                on[q] = int(round(note.start * sr2)) - p0
                off[q] = int(round((note.start + note.dur) * sr2)) - p0
                pitch[q] = float(note.pitch)
                retrig[q] = rt
                glide[q] = gl
                bend[q] = "bend" in _arts(note)
                amp[q], env[q], famt[q], fbase[q] = machine.note_params(note, sr2)
            # a note whose key is still down when the next is played (legato, or a restruck poly key)
            # doesn't release: the next note carries on
            for q in range(count - 1):
                if off[q] > on[q + 1] or (not retrig[q + 1] and off[q] >= on[q + 1] - int(0.002 * sr2)):
                    off[q] = -1
            end = int(max(o for o in off if o >= 0) if (off >= 0).any() else on[-1]) + int(tail * sr2)
            n = min(end, n2 - p0)
            if n <= 0:
                continue
            # control tracks: each oscillator's detune and slow drift; each wave's width (one LFO for the
            # machine, as a poly synth has): a modulated pulse's two saws are shifted in frequency by half
            # the width's rate of change, so both its edges move and its centre stays put (the width
            # changes, the pitch doesn't)
            n_ctrl = n // CTRL + 3
            cents = np.empty((n_osc, n_ctrl))
            for o in range(n_osc):
                cents[o] = machine.offsets[o] + osc.drift(n_ctrl, sr2 / CTRL, gen, machine.drift,
                                                         float(machine.drift_rates[o]))
            ratio = 2.0 ** (cents[machine.owner] / 1200.0 + machine.octaves[machine.owner][:, None])
            arg = 2.0 * np.pi * (machine.pwm_rate * (p0 + np.arange(n_ctrl) * CTRL) / sr2 + pwm_phase)
            pws = np.array([sg * 0.5 * w[1] * 2.0 * np.pi * machine.pwm_rate * np.cos(arg) if sg != 0.0
                            else np.full(n_ctrl, w[0]) for w, sg in zip(machine.widths, machine.signs)])
            start = gen.uniform(0.0, 1.0, n_osc)
            phases = [float((start[o] + 0.5 * sg * (w[0] + w[1] * np.sin(arg[0]))) % 1.0)
                      for o, w, sg in zip(machine.owner, machine.widths, machine.signs)]
            seed = np.uint64(gen.integers(1, 1 << 62))
            kinds = np.array(machine.kinds, dtype=np.int64)
            _voice(buf, p0, n, on, off, pitch, retrig, glide, bend, amp, env, famt, fbase, kinds, machine.levels,
                   machine.shifted, ratio, pws, np.array(phases), gcoef, bcoef, machine.vibrato, p["track"],
                   p["ref"], machine.k, p["drive"], machine.noise, seed, 1.0 / sr2)
    return osc.decimate2(buf[:n2])[:length] * p["out"]


def _render_sub(notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
                settings: dict) -> np.ndarray:
    """The sub bass, at the plain rate: nothing in it comes near half the sample rate."""
    s = {**DEFAULTS, **settings}
    bright = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
    wear = float(np.clip(s.get("wear", 0.25), 0.0, 1.0))
    trim = float(make.normal(0.0, 0.1 + 0.2 * wear))
    time_trim = np.exp(make.normal(0.0, 0.05, 4))
    glide_t = 0.06 * float(np.exp(make.normal(0.0, 0.1)))
    h2 = 10 ** ((-15.0 + 8.0 * (bright - 0.5)) / 20.0)
    h3 = 10 ** ((-30.0 + 12.0 * (bright - 0.5)) / 20.0)
    out = np.zeros(length)
    base_seed = int(rng.integers(1 << 62))
    tail = 0.15 * 1.1 * 100.0 / 60.0 + 0.01
    gcoef = _coef(glide_t, sr, np.log(10.0))
    tcoef = _coef(0.035, sr, np.log(10.0))
    fade = int(0.003 * sr)
    for phrase in _phrases(list(notes), tail, True):
        first = phrase[0][0]
        p0 = int(round(first.start * sr))
        if p0 >= length:
            continue
        gen = np.random.default_rng([base_seed, p0, int(round(first.pitch * 100))])
        count = len(phrase)
        on = np.empty(count, dtype=np.int64)
        off = np.empty(count, dtype=np.int64)
        pitch = np.empty(count)
        retrig = np.empty(count, dtype=np.bool_)
        glide = np.empty(count, dtype=np.bool_)
        amp = np.empty(count)
        env = np.empty((count, 4))
        thump = np.zeros(count)
        for q, (note, rt, gl) in enumerate(phrase):
            art = _arts(note)
            on[q] = int(round(note.start * sr)) - p0
            off[q] = int(round((note.start + note.dur) * sr)) - p0
            pitch[q] = float(note.pitch)
            retrig[q] = rt
            glide[q] = gl or ("glide" in art and q > 0)
            vel = float(np.clip(note.vel, 0.0, 1.0))
            amp[q] = touch.gain(vel, 10.0) * 0.3
            att, dec, sus, rel = 0.003, 0.5, 1.0, 0.08
            if "short" in art:
                dec, sus, rel = 0.18, 0.0, 0.05
            if "boom" in art:
                dec, sus, rel = 1.1, 0.0, 0.15
                thump[q] = 3.0
            env[q] = (_coef(att * time_trim[0], sr, np.log(ATTACK_TARGET / (ATTACK_TARGET - 1.0))),
                      _coef(dec * time_trim[1], sr, np.log(10.0)), sus, _coef(rel * time_trim[2], sr, np.log(1000.0)))
        for q in range(count - 1):
            if off[q] > on[q + 1] or (not retrig[q + 1] and off[q] >= on[q + 1] - int(0.002 * sr)):
                off[q] = -1
        end = int(max(o for o in off if o >= 0) if (off >= 0).any() else on[-1]) + int(tail * sr)
        n = min(end, length - p0)
        dstep = 64
        drift = trim + osc.drift(n // dstep + 3, sr / dstep, gen, 0.1 + 0.3 * wear, 0.2)
        _sub(out, p0, n, on, off, pitch, retrig, glide, amp, env, thump, gcoef, tcoef, h2, h3, drift, float(dstep),
             float(fade), 1.0 / sr)
    return out


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A synthesizer part: dry, before placement and level; stereo (length, 2) for the pad, else mono."""
    if name not in SPEC:
        raise ValueError(f"no such instrument: {name}")
    s = {**DEFAULTS, **(settings or {})}
    playing = sorted((n for n in notes if n.dur > 0 and 0 <= n.start * sr < length), key=lambda n: (n.start, n.pitch))
    if name == "sub-bass":
        y = _render_sub(playing, sr, length, rng, make, s)
    else:
        machine = _Machine(name, make, s)
        if not playing:
            return np.zeros((length, 2)) if PRESETS[name]["chorus"] else np.zeros(length)
        y = _render_voiced(name, playing, sr, length, rng, machine)
    # the output stage is AC-coupled: a note's first and last part-periods leave a little DC, which goes
    y = sosfilt(butter(1, AC_HZ, btype="highpass", fs=sr, output="sos"), y)
    if name != "sub-bass" and PRESETS[name]["chorus"]:
        phases = tuple(rng.uniform(0.0, 1.0, 2))
        y = chorus(y, sr, machine.chorus_centre, machine.chorus_depth, machine.chorus_rates, machine.chorus_mix,
                   phases)
    return y
