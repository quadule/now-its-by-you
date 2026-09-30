"""The electric instruments' electronics: a magnetic pickup, a small valve amp, its spring reverb and its cabinet.

A helper for electric.py and steel.py; it plays no notes of its own.

The pickup. A magnetic pickup hears the string's velocity where it sits: the
wave running toward the bridge and the one coming back from it, a delay of
twice the pickup's distance from the bridge apart, so it is a comb (the
strings' own business: see fretboard.py). Its coil is an inductance with a
resistance and a capacitance, loaded by the guitar's volume and tone pots,
the cable and the amp's input: a resonant low-pass, near 4 kHz for a single
coil and near 3 kHz for a humbucker (M. Zollner, "Physik der Elektrogitarre",
2014, ch. 5), worked out here from the circuit.

The amp. Two 12AX7 gain stages, each solved on its load line from Koren's
triode equations (N. Koren, "Improved vacuum tube models for SPICE
simulations", 1996): asymmetric by nature, softly squashed toward cutoff and
clamped where the grid starts to conduct. The second stage's grid current
charges its coupling capacitor, pushing its bias down for a few tens of
milliseconds after a hard attack (the "blocking" that makes a pushed amp
breathe). Between them the Fender or Marshall tone stack (the treble, middle
and bass network whose transfer function Yeh and Smith worked out,
"Discretization of the '59 Fender Bassman tone stack", DAFx 2006), third order
over third order, its coefficients taken here from the circuit's nodal
equations and discretized by the bilinear transform. Then the spring reverb's
return and the tremolo, and the push-pull power stage: symmetric clipping,
nearly linear until close to its ceiling (the firmer with negative feedback),
the ceiling sagging as the supply is drawn down, and the output transformer's
band. The nonlinear stages run four times oversampled, the resampling fused
into the same pass so nothing oversampled is ever stored.

The spring (V. Välimäki, J. Parker and J. Abel, "Parametric spring
reverberation effect", JAES 58(7/8), 2010): each spring is a feedback loop
whose chain of stretched allpass filters delays the highs more than the lows
below a transition frequency near 4 kHz, so every echo is a chirp, spread
further by every trip round the loop; the echoes come a round trip apart.

The cabinet: an impulse response made from a loudspeaker's physics: the cone's
mass on its suspension (a resonance at 75 to 110 Hz), an open back letting what
lies below it cancel, the cone breaking up into a presence region at 2 to 4 kHz
with a scatter of peaks and dips, the steep fall above 5 or 6 kHz, and two
microphones, each with the comb of a reflection it also hears.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from numba import njit
from scipy.signal import bilinear, ellip, firwin, sosfilt, sosfreqz, tf2sos

from . import fx, oa
from .iir import butter

OS = 4  # oversampling of the nonlinear stages
TAPS = 65  # the polyphase resampler: flat to 10 kHz, 85 dB down wherever anything could fold back into the band


# --- the pickup -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Coil:
    """A pickup's electrical side, and how hot it is."""

    inductance: float  # H
    resistance: float  # ohm, the coil's DC resistance
    capacitance: float  # F, its own winding capacitance
    sensitivity: float  # volts per unit of string velocity (its turns and magnet)


SINGLE = Coil(2.4, 6000.0, 110e-12, 1.0)  # a Fender-style single coil (Zollner: 2.2-2.6 H, 5.6-6.3 kohm)
HUMBUCKER = Coil(4.4, 8200.0, 150e-12, 2.2)  # a PAF-style humbucker: two coils in series, hotter and darker
BASS_P = Coil(3.6, 10500.0, 180e-12, 2.4)  # a split-coil bass pickup
BASS_J = Coil(3.2, 7200.0, 130e-12, 1.4)  # a jazz-bass single coil


def parallel(coil: Coil) -> Coil:
    """Two of the same pickup switched in parallel: half the inductance and resistance, twice the capacitance."""
    return Coil(coil.inductance / 2.0, coil.resistance / 2.0, coil.capacitance * 2.0, coil.sensitivity)


def pickup_ba(coil: Coil, *, pot: float, tone: float | None, tone_cap: float, cable: float,
              load: float = 1e6) -> tuple[np.ndarray, np.ndarray]:
    """The analog transfer function (b, a: powers of s, highest first) from the coil's EMF to the amp's
    input: the coil's resistance and inductance in series, then its capacitance and the cable's, the volume
    pot, the amp's input resistance and (unless tone is None) the tone pot's resistance `tone` in series
    with its capacitor, all to ground."""
    rl = 1.0 / (1.0 / pot + 1.0 / load)
    c = coil.capacitance + cable
    if tone is None:
        yd = np.array([1.0])
        yn = np.array([c, 1.0 / rl])  # the shunt admittance sC + 1/rl
    else:
        rc = tone * tone_cap  # Y = sC + 1/rl + sCt / (1 + s R Ct), over the common denominator (1 + s R Ct)
        yd = np.array([rc, 1.0])
        yn = np.polyadd(np.polymul([c, 1.0 / rl], [rc, 1.0]), [tone_cap, 0.0])
    den = np.polyadd(yd, np.polymul([coil.inductance, coil.resistance], yn))  # H = yd / (yd + (R + sL) yn)
    return yd / den[-1], den / den[-1]


def resonance(b: np.ndarray, a: np.ndarray, lo: float = 300.0, hi: float = 12000.0) -> tuple[float, float, float]:
    """An analog low-pass's resonance: its frequency, its height over the response at 100 Hz (dB), and its
    Q (the peak's frequency over the width where it stands within 3 dB of its top)."""
    f = np.exp(np.linspace(np.log(lo), np.log(hi), 4000))
    h = np.abs(np.polyval(b, 2j * np.pi * f) / np.polyval(a, 2j * np.pi * f))
    i = int(np.argmax(h))
    ref = float(np.abs(np.polyval(b, 2j * np.pi * 100.0) / np.polyval(a, 2j * np.pi * 100.0)))
    inside = np.flatnonzero(h > h[i] / np.sqrt(2.0))
    width = f[inside[-1]] - f[inside[0]] if len(inside) > 1 else f[i]
    return float(f[i]), float(20.0 * np.log10(h[i] / ref)), float(f[i] / width)


def digital(b: np.ndarray, a: np.ndarray, fs: float, warp: float) -> np.ndarray:
    """An analog transfer function by the bilinear transform, prewarped at `warp` Hz, as second-order sections."""
    k = 2.0 * np.pi * warp / np.tan(np.pi * warp / fs)  # s = k (1 - 1/z) / (1 + 1/z)
    bz, az = bilinear(b, a, fs=k / 2.0)
    return tf2sos(bz, az)


# --- the valves -----------------------------------------------------------------------------------

KOREN_12AX7 = (100.0, 1.4, 1060.0, 600.0, 300.0)  # mu, ex, kg1, kp, kvb; the plate current in amperes


def plate_current(vgk, vpk, tube=KOREN_12AX7):
    """Koren's triode: Ip = 2 E1^ex / kg1, E1 = (Vp / kp) ln(1 + exp(kp (1/mu + Vg / sqrt(kvb + Vp^2))))."""
    mu, ex, kg1, kp, kvb = tube
    vpk = np.maximum(vpk, 1e-6)
    e1 = vpk / kp * np.logaddexp(0.0, kp * (1.0 / mu + vgk / np.sqrt(kvb + vpk**2)))
    return 2.0 * np.maximum(e1, 0.0) ** ex / kg1


def plate_voltage(vgk: np.ndarray, bplus: float, ra: float) -> np.ndarray:
    """The plate voltage where the valve meets its load line, B+ - Vp = Ip(Vgk, Vp) Ra (bisection)."""
    lo, hi = np.zeros_like(vgk), np.full_like(vgk, bplus)
    for _ in range(64):
        mid = 0.5 * (lo + hi)
        above = bplus - mid - plate_current(vgk, mid) * ra > 0.0
        lo, hi = np.where(above, mid, lo), np.where(above, hi, mid)
    return 0.5 * (lo + hi)


def operating_point(bplus: float, ra: float, rk: float) -> tuple[float, float]:
    """The grid bias its cathode resistor sets (Vgk = -Ip Rk) and the plate voltage there."""
    lo, hi = -8.0, 0.0
    for _ in range(64):
        v = 0.5 * (lo + hi)
        vp = plate_voltage(np.array([v]), bplus, ra)[0]
        if v + plate_current(v, vp) * rk > 0.0:
            hi = v
        else:
            lo = v
    v = 0.5 * (lo + hi)
    return v, float(plate_voltage(np.array([v]), bplus, ra)[0])


GRID_R = 1500.0  # ohm: the grid-cathode path once it conducts (Koren's RGI is 2 kohm)
GRID_KNEE = 0.12  # V: how gradually the grid starts to conduct
TABLE = (-60.0, 12.0, 24001)  # the stage curves' grid-voltage range and points


@lru_cache(maxsize=16)
def stage_table(bplus: float, ra: float, rk: float, source: float) -> tuple[np.ndarray, np.ndarray, float]:
    """A gain stage as curves: the plate's swing from its idle voltage (V; the stage inverts), and the
    voltage the grid current drops across the source, both against the grid-cathode voltage the drive
    would give if the grid never conducted.

    Past zero volts the grid conducts through GRID_R, and the source driving it (resistance `source`) can
    push it only a little further: Vg = v - (1 - k) softplus(v), k = GRID_R / (GRID_R + source).
    Returns the two curves over TABLE's range and the stage's bias (V)."""
    bias, vp0 = operating_point(bplus, ra, rk)
    lo, hi, n = TABLE
    v = np.linspace(lo, hi, n)
    k = GRID_R / (GRID_R + source)
    drop = (1.0 - k) * GRID_KNEE * np.logaddexp(0.0, v / GRID_KNEE)
    return plate_voltage(v - drop, bplus, ra) - vp0, drop, bias


# --- the tone stack -------------------------------------------------------------------------------

# C1, C2, C3, R1, R2, R3, R4, and the source: the treble cap, bass cap, mid cap, treble pot, bass pot, mid
# pot, slope resistor, and what drives the stack (a plate: about 38 kohm; a cathode follower: about 1 kohm)
STACKS = {
    "fender": (250e-12, 0.02e-6, 0.02e-6, 250e3, 1e6, 25e3, 56e3, 38e3),  # the '59 Bassman 5F6-A
    "marshall": (470e-12, 0.022e-6, 0.022e-6, 220e3, 1e6, 25e3, 33e3, 1e3),  # a JTM45 or plexi
}


def _stack_matrix(s: complex, t: float, m: float, l: float, parts, load: float) -> tuple[np.ndarray, np.ndarray]:
    """The TMB network's nodal admittance matrix and source vector at complex frequency s, driven by a 1 V
    source through its source resistance. Nodes: 0 input, 1 the treble pot's top, 2 its wiper (the output),
    3 its bottom and the bass pot's top, 4 the bass pot's bottom and the mid pot's top, 5 where the slope
    resistor meets the bass and mid caps, 6 the mid pot's wiper, where the mid cap lands (the whole mid pot
    runs from node 4 to ground: Yeh and Smith's circuit, whose closed form this reproduces exactly)."""
    c1, c2, c3, r1, r2, r3, r4, rs = parts
    y = np.zeros((7, 7), dtype=complex)
    src = np.zeros(7, dtype=complex)

    def branch(a, b, g):
        y[a, a] += g
        if b is not None:
            y[b, b] += g
            y[a, b] -= g
            y[b, a] -= g

    branch(0, None, 1.0 / rs)
    src[0] = 1.0 / rs
    branch(0, 1, s * c1)
    branch(1, 2, 1.0 / ((1.0 - t) * r1))
    branch(2, 3, 1.0 / (t * r1))
    branch(3, 4, 1.0 / (l * r2))
    branch(4, 6, 1.0 / ((1.0 - m) * r3))
    branch(6, None, 1.0 / (m * r3))
    branch(0, 5, 1.0 / r4)
    branch(5, 3, s * c2)
    branch(5, 6, s * c3)
    branch(2, None, 1.0 / load)
    return y, src


def _pots(treble: float, middle: float, bass: float) -> tuple[float, float, float]:
    """Knob positions (0..1) to the pots' fractions: treble and middle linear, the bass pot an audio taper."""
    clip = lambda v: float(min(max(v, 1e-3), 1.0 - 1e-3))  # noqa: E731
    return clip(treble), clip(middle), clip((np.exp(3.4 * bass) - 1.0) / (np.exp(3.4) - 1.0))


def stack_response(freqs, treble: float, middle: float, bass: float, voicing: str = "fender",
                   load: float = 1e6) -> np.ndarray:
    """The tone stack's complex response at `freqs` Hz, solving its nodal equations directly (for checks)."""
    t, m, l = _pots(treble, middle, bass)
    out = []
    for f in np.atleast_1d(freqs):
        y, src = _stack_matrix(2j * np.pi * f, t, m, l, STACKS[voicing], load)
        out.append(np.linalg.solve(y, src)[2])
    return np.array(out)


def stack_ba(treble: float, middle: float, bass: float, voicing: str = "fender",
             load: float = 1e6) -> tuple[np.ndarray, np.ndarray]:
    """The stack's analytic transfer function b(s) / a(s), third order over third order.

    By Cramer's rule the output is det(Y with the source in the output's column) / det(Y); each
    determinant is a polynomial of degree three in s (a power for each capacitor), recovered exactly from
    its values at seven points round a circle (their discrete Fourier transform)."""
    t, m, l = _pots(treble, middle, bass)
    scale = 2.0 * np.pi * 1000.0
    n = 7
    zs = np.exp(2j * np.pi * np.arange(n) / n)
    dets, nums = [], []
    for z in zs:
        y, src = _stack_matrix(scale * z, t, m, l, STACKS[voicing], load)
        dets.append(np.linalg.det(y))
        y[:, 2] = src
        nums.append(np.linalg.det(y))
    dets, nums = np.array(dets), np.array(nums)
    den = np.array([np.mean(dets * zs ** (-j)) for j in range(4)]).real  # in powers of z = s / scale
    num = np.array([np.mean(nums * zs ** (-j)) for j in range(4)]).real
    powers = scale ** (-np.arange(4.0))
    a, b = (den * powers)[::-1], (num * powers)[::-1]
    return b / a[-1], a / a[-1]


# --- the spring -----------------------------------------------------------------------------------


@njit(cache=True, nogil=True)
def _spring(n, start, stretch, coef, first, loop, gain, lp, damp, delay):
    """One spring's response to an impulse arriving at sample `start`, n samples long.

    The first arrival passes `first` stretched allpasses (a + z^-K) / (1 + a z^-K) and the low-pass `lp`
    (second-order sections); after it, every echo is the output a round trip ago (a delay of delay[t]
    samples, which wanders) through `loop` more allpasses, the low-pass again, a one-pole damping and
    `gain`."""
    k = stretch
    total = first + loop
    xs = np.zeros((total, k))
    ys = np.zeros((total, k))
    ptr = 0
    size = 1
    while size < n + 8:
        size *= 2
    line = np.zeros(size)
    out = np.zeros(n)
    nsec = lp.shape[0]
    z0 = np.zeros((nsec, 2))
    z1 = np.zeros((nsec, 2))
    held = 0.0
    for t in range(n):
        v = 1.0 if t == start else 0.0
        for s in range(first):
            yv = coef * v + xs[s, ptr] - coef * ys[s, ptr]
            xs[s, ptr] = v
            ys[s, ptr] = yv
            v = yv
        for s in range(nsec):
            o = lp[s, 0] * v + z0[s, 0]
            z0[s, 0] = lp[s, 1] * v - lp[s, 4] * o + z0[s, 1]
            z0[s, 1] = lp[s, 2] * v - lp[s, 5] * o
            v = o
        arrival = v
        pos = t - delay[t]
        i = int(np.floor(pos))
        f = pos - i
        v = 0.0
        if i >= 0:
            v = (1.0 - f) * line[i & (size - 1)] + f * line[(i + 1) & (size - 1)]
        for s in range(first, total):
            yv = coef * v + xs[s, ptr] - coef * ys[s, ptr]
            xs[s, ptr] = v
            ys[s, ptr] = yv
            v = yv
        for s in range(nsec):
            o = lp[s, 0] * v + z1[s, 0]
            z1[s, 0] = lp[s, 1] * v - lp[s, 4] * o + z1[s, 1]
            z1[s, 1] = lp[s, 2] * v - lp[s, 5] * o
            v = o
        held = (1.0 - damp) * v + damp * held
        y = arrival + gain * held
        line[t & (size - 1)] = y
        out[t] = y
        ptr += 1
        if ptr == k:
            ptr = 0
    return out


@dataclass(frozen=True)
class Tank:
    """A spring reverb tank: its springs' one-way traversal times (s), how long it rings, its dispersion."""

    traversals: tuple[float, ...] = (0.031, 0.037)
    t60: float = 2.6  # seconds
    coef: float = 0.62  # the stretched allpasses' coefficient: higher spreads each chirp further
    stretch: int = 5  # K: the transition frequency is sr / (2 K), 4.4 kHz at 44.1 kHz
    sections: int = 40  # allpasses per traversal
    lowcut: float = 180.0  # Hz: the tank's transducers pass little bass
    seed: int = 0


def band_gain(h: np.ndarray, sr: int, lo: float = 200.0, hi: float = 4000.0) -> float:
    """RMS gain of a response over log-spaced frequencies between lo and hi."""
    spec = np.abs(np.fft.rfft(h, max(1 << 14, 1 << int(np.ceil(np.log2(len(h)))))))
    freqs = np.fft.rfftfreq(2 * (len(spec) - 1), 1.0 / sr)
    grid = np.exp(np.linspace(np.log(lo), np.log(hi), 256))
    return float(np.sqrt(np.mean(np.interp(grid, freqs, spec) ** 2)))


@lru_cache(maxsize=16)
def spring_ir(tank: Tank, sr: int) -> np.ndarray:
    """The tank's mono impulse response, ringing to 70 dB down, at unit gain between 200 Hz and 4 kHz."""
    rng = np.random.default_rng(tank.seed)
    n = int((tank.t60 * 70.0 / 60.0 + 0.1) * sr)
    lp = ellip(6, 0.5, 60.0, 0.93 * sr / (2.0 * tank.stretch), fs=sr, output="sos")
    ap = tank.stretch * (1.0 - tank.coef) / (1.0 + tank.coef)  # one allpass's delay at low frequencies
    _, h = sosfreqz(lp, worN=np.exp(np.linspace(np.log(200.0), np.log(3000.0), 64)), fs=sr)
    ripple = float(np.sqrt(np.mean(np.abs(h) ** 2)))  # what the low-pass takes from each trip where the tank sings
    total = np.zeros(n)
    for j, traverse in enumerate(tank.traversals):
        pre = max(8.0, traverse * sr - tank.sections * ap)  # the line makes up what the allpasses don't delay
        round_trip = 2.0 * traverse * sr
        gain = 10.0 ** (-3.0 * round_trip / (tank.t60 * sr)) / ripple
        # the spring's coils are never quite even: its round trip wanders by a sample or two
        steps = rng.standard_normal(n // 512 + 2)
        wander = np.interp(np.arange(n), np.arange(len(steps)) * 512.0, np.cumsum(steps) * 0.4)
        delay = 2.0 * pre + np.clip(wander - wander.mean(), -0.2 * pre, 0.2 * pre)
        y = _spring(n, int(round(pre)), tank.stretch, tank.coef, tank.sections, 2 * tank.sections, gain,
                    np.ascontiguousarray(lp), 0.18, np.ascontiguousarray(delay))
        total += y * (1.0 if j % 2 == 0 else -1.0) * rng.uniform(0.8, 1.0)
    total = sosfilt(butter(2, tank.lowcut, btype="highpass", fs=sr, output="sos"), total)
    tail = int(0.05 * n)
    total[-tail:] *= np.linspace(1.0, 0.0, tail) ** 2
    return total / band_gain(total, sr)


# --- the cabinet ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cabinet:
    """A loudspeaker in an open-backed combo, and two microphones on it."""

    fs: float = 85.0  # the cone's resonance, Hz (a 12-inch guitar speaker 75-90, a 10-inch 90-110)
    q: float = 1.3  # its Q in the box
    presence: tuple[float, float, float] = (2800.0, 5.0, 1.2)  # the breakup region's hump: Hz, dB, Q
    rolloff: float = 5500.0  # Hz where the cone stops following the coil
    order: int = 4  # how steeply it falls past there (2: -12 dB an octave, 4: -24)
    back: float = 5.0  # dB the open back cancels of the lowest octave
    back_at: float = 150.0  # Hz: where that cancellation sets in (a shelf's corner)
    breakup: float = 5.0  # dB: how far the cone's breakup peaks and dips reach
    # each microphone: its reflection's extra path (s), that reflection's level, and dB it loses above 3 kHz
    # for sitting off the cone's axis
    mics: tuple[tuple[float, float, float], ...] = ((0.00022, 0.25, 0.0), (0.0012, 0.4, -5.0))
    seed: int = 0


def _highpass(f: float, q: float, sr: int) -> np.ndarray:
    """A resonant second-order high-pass (RBJ): the cone's mass on its suspension."""
    w = 2.0 * np.pi * f / sr
    alpha = np.sin(w) / (2.0 * q)
    c = np.cos(w)
    b = [(1.0 + c) / 2.0, -(1.0 + c), (1.0 + c) / 2.0]
    a = [1.0 + alpha, -2.0 * c, 1.0 - alpha]
    return np.array([b[0] / a[0], b[1] / a[0], b[2] / a[0], 1.0, a[1] / a[0], a[2] / a[0]])


@lru_cache(maxsize=16)
def cabinet_ir(cab: Cabinet, sr: int, n: int = 2048) -> np.ndarray:
    """The cabinet as each microphone hears it: shape (n, microphones), 0 dB on average from 200 Hz to 4 kHz."""
    rng = np.random.default_rng(cab.seed)
    x = np.zeros(n)
    x[0] = 1.0
    f, db, q = cab.presence
    bands = [_highpass(cab.fs, cab.q, sr)[None], fx.shelf("low", cab.back_at, -cab.back, sr)[None],
             fx.peaking(f, db, q, sr)[None], butter(cab.order, cab.rolloff, btype="lowpass", fs=sr, output="sos")]
    # the cone breaking up: a scatter of narrow peaks and dips from 700 Hz to 6 kHz, this speaker's own
    for fb in np.exp(rng.uniform(np.log(700.0), np.log(6000.0), 7)):
        bands.append(fx.peaking(fb, rng.uniform(-1.0, 1.0) * cab.breakup, rng.uniform(3.0, 8.0), sr)[None])
    y = sosfilt(np.concatenate(bands), x)
    out = np.zeros((n, len(cab.mics)))
    for j, (delay, level, off) in enumerate(cab.mics):
        d = delay * sr
        i = int(d)
        frac = d - i
        m = y.copy()
        if i + 1 < n:  # the reflection: the same sound a little later, weaker and turned over
            m[i:] -= level * (1.0 - frac) * y[: n - i]
            m[i + 1:] -= level * frac * y[: n - i - 1]
        if off:
            m = sosfilt(fx.shelf("high", 3000.0, off, sr)[None], m)
        out[:, j] = m
    tail = n // 8
    out[-tail:] *= (np.linspace(1.0, 0.0, tail) ** 2)[:, None]
    return out / np.sqrt(np.mean([band_gain(out[:, j], sr) ** 2 for j in range(out.shape[1])]))


# --- the amp --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Amp:
    """A small valve combo and how it is set."""

    voicing: str = "fender"  # the tone stack: "fender" or "marshall"
    treble: float = 0.6
    middle: float = 0.5
    bass: float = 0.5
    stage: tuple[float, float, float] = (250.0, 100e3, 1500.0)  # each gain stage's B+, plate and cathode resistors
    source: float = 100e3  # ohm: what drives the second stage's grid (the stack and the volume pot)
    coupling: float = 22e-9  # F: its coupling capacitor
    leak: float = 1e6  # ohm: its grid leak
    volume: float = -20.0  # dB: the volume pot between the stack and the second stage
    headroom: float = 45.0  # V: the second stage's swing that takes the power stage to its knee
    # the power stage's knee, a / (1 + a^2p)^(1/2p): 1 (p = 1) very soft, compressing from a third of its
    # ceiling; 2 (p = 2) a push-pull pair with little feedback (EL84s, 6V6s: a few percent at half power);
    # 3 (p = 4) one with negative feedback (a blackface's 6V6s or 6L6s): linear nearly to its ceiling
    knee: int = 1
    tilt: float = 0.03  # the push-pull pair's mismatch: a little even distortion
    sag: float = 0.12  # how far the supply falls when the power stage is driven flat out
    sag_times: tuple[float, float] = (0.03, 0.2)  # s: how fast it falls, and recovers
    transformer: tuple[float, float] = (60.0, 11000.0)  # the output transformer's band, Hz
    reverb: float = 0.0  # the spring's return against the dry sound (amplitude)
    tank: Tank = Tank()
    tremolo: tuple[str, float, float] = ("optical", 5.5, 0.0)  # kind ("optical" or "bias"), Hz, depth 0..1
    cabinet: Cabinet = Cabinet()
    master: float = 1.0  # the output's level (amp.reference_gain sets it)


@njit(cache=True, nogil=True)
def _dot(a, b, start, count):
    """sum_k a[k] b[start + k], k < count, in four interleaved partial sums (a fixed order)."""
    s0 = 0.0
    s1 = 0.0
    s2 = 0.0
    s3 = 0.0
    k = 0
    while k + 3 < count:
        s0 += a[k] * b[start + k]
        s1 += a[k + 1] * b[start + k + 1]
        s2 += a[k + 2] * b[start + k + 2]
        s3 += a[k + 3] * b[start + k + 3]
        k += 4
    while k < count:
        s0 += a[k] * b[start + k]
        k += 1
    return (s0 + s1) + (s2 + s3)


@njit(cache=True, nogil=True)
def _run(x, rev, up, down, p, tab1, tab2, drop2, sos):
    """The amp from the pickup to the output transformer's secondary.

    x (the pickup's voltage) and rev (the spring's return, in the power stage's units) at the base rate in,
    the same rate out, the stages between at os times the rate: up (os, m) are the polyphase upsampler's
    taps, each phase's in time order, and down (os * m + 1) the decimator's, oldest first. The output lags
    the input by m samples. rev, band-limited below 4.4 kHz, is interpolated linearly."""
    n = x.shape[0]
    os_ = up.shape[0]
    per = up.shape[1]
    taps = down.shape[0]
    y = np.zeros(n)
    nsec = sos.shape[0]
    xb = np.zeros(2 * per)  # each sample written twice, so the last `per` are always one contiguous run
    zb = np.zeros(2 * taps)
    zs = np.zeros(2 * nsec)
    bias1, bias2, charge, leakc, vol, pa = p[0], p[1], p[2], p[3], p[4], p[5]
    knee, tilt, sag, sag_a, sag_r, hp, lp, dc = p[6], p[7], p[8], p[9], p[10], p[11], p[12], p[13]
    kind, rate, depth, ldr_a, ldr_r, lo, step, master = p[14], p[15], p[16], p[17], p[18], p[19], p[20], p[21]
    top = tab1.shape[0] - 1
    rot_re = np.cos(2.0 * np.pi * rate)  # the LFO turns this far each oversampled sample
    rot_im = np.sin(2.0 * np.pi * rate)
    if knee > 2.5:
        tilt_out = tilt / (1.0 + tilt**8) ** 0.125
    elif knee > 1.5:
        tilt_out = tilt / (1.0 + tilt**4) ** 0.25
    else:
        tilt_out = tilt / np.sqrt(1.0 + tilt * tilt)
    q2 = 0.0
    dc_x = 0.0
    dc_y = 0.0
    sup = 1.0
    env = 0.0
    hp_x = 0.0
    hp_y = 0.0
    lp_y = 0.0
    c_re = 1.0
    c_im = 0.0
    ldr = 0.0
    ptr = 0
    zptr = 0
    lag = (taps - 1) // (2 * os_)  # the upsampler's delay in base samples: rev is read that much later
    for i in range(n):
        ptr += 1
        if ptr == per:
            ptr = 0
        xb[ptr] = x[i]
        xb[ptr + per] = x[i]
        r_a = rev[i - lag] if i >= lag else 0.0
        r_b = rev[i - lag + 1] if i >= lag - 1 else 0.0
        for ph in range(os_):
            u = _dot(up[ph], xb, ptr + 1, per)
            r = r_a + (r_b - r_a) * ph / os_
            # the first stage: the pickup straight onto its grid
            t = (bias1 + u - lo) / step
            if t <= 0.0:
                v = tab1[0]
            elif t >= top:
                v = tab1[top]
            else:
                j = int(t)
                v = tab1[j] + (t - j) * (tab1[j + 1] - tab1[j])
            # the tone stack
            for s in range(nsec):
                o = sos[s, 0] * v + zs[2 * s]
                zs[2 * s] = sos[s, 1] * v - sos[s, 4] * o + zs[2 * s + 1]
                zs[2 * s + 1] = sos[s, 2] * v - sos[s, 5] * o
                v = o
            # the second stage: its grid current charges the coupling capacitor, pushing its bias down
            t = (bias2 + v * vol - q2 - lo) / step
            if t <= 0.0:
                v = tab2[0]
                d = 0.0
            elif t >= top:
                v = tab2[top]
                d = drop2[top]
            else:
                j = int(t)
                f = t - j
                v = tab2[j] + f * (tab2[j + 1] - tab2[j])
                d = drop2[j] + f * (drop2[j + 1] - drop2[j])
            q2 += d * charge - q2 * leakc
            o = v - dc_x + dc * dc_y  # the next coupling capacitor
            dc_x = v
            dc_y = o
            v = o * pa + r
            if depth > 0.0:  # the tremolo's LFO, a turning phasor
                nr = c_re * rot_re - c_im * rot_im
                c_im = c_re * rot_im + c_im * rot_re
                c_re = nr
                if kind < 0.5:  # optical: a lamp lights on the LFO's upper half and a photocell follows it
                    lamp = (c_im - 0.15) / 0.85
                    if lamp < 0.0:
                        lamp = 0.0
                    cf = ldr_a if lamp > ldr else ldr_r
                    ldr = cf * ldr + (1.0 - cf) * lamp
                    v *= 1.0 - depth * ldr
                else:  # bias: the power valves' bias swings, and their gain with it
                    v *= 1.0 - depth * (0.5 + 0.5 * c_im)
            # the power stage, push-pull, its ceiling the supply
            a = v / sup + tilt
            if knee > 2.5:
                a2 = a * a
                a4 = a2 * a2
                o = (a / np.sqrt(np.sqrt(np.sqrt(1.0 + a4 * a4))) - tilt_out) * sup
            elif knee > 1.5:
                a2 = a * a
                o = (a / np.sqrt(np.sqrt(1.0 + a2 * a2)) - tilt_out) * sup
            else:
                o = (a / np.sqrt(1.0 + a * a) - tilt_out) * sup
            level = abs(o)
            cf = sag_a if level > env else sag_r
            env = cf * env + (1.0 - cf) * level
            sup = 1.0 - sag * min(env, 1.0)
            hp_y = hp * (hp_y + o - hp_x)  # the output transformer's band
            hp_x = o
            lp_y += lp * (hp_y - lp_y)
            zptr += 1
            if zptr == taps:
                zptr = 0
            zb[zptr] = lp_y
            zb[zptr + taps] = lp_y
            if ph == 0:
                y[i] = _dot(down, zb, zptr + 1, taps) * master
        if (i & 4095) == 0:  # keep the LFO's phasor on the unit circle
            mag = np.sqrt(c_re * c_re + c_im * c_im)
            c_re /= mag
            c_im /= mag
    return y


@lru_cache(maxsize=4)
def _fir(os_: int) -> tuple[np.ndarray, np.ndarray]:
    """The resampler's taps: the upsampler's by phase, each in time order (oldest input first), with the
    upsampler's gain of os; and the decimator's, oldest first, with unit gain."""
    if os_ == 1:
        return np.ones((1, 1)), np.ones(1)
    h = firwin(TAPS, 0.8 / os_, window=("kaiser", 7.5))
    per = (TAPS + os_ - 1) // os_
    up = np.zeros((os_, per))
    for ph in range(os_):
        for k in range(per):
            j = ph + (per - 1 - k) * os_
            if j < TAPS:
                up[ph, k] = h[j] * os_
    return up, np.ascontiguousarray(h[::-1])


def synced(rate: float, tempo: float) -> float:
    """A tremolo's rate locked to the tempo: the subdivision of the beat (quarters to sixteenth triplets)
    nearest the amp's own rate, within 4 to 7 Hz."""
    beat = tempo / 60.0
    options = [beat * k for k in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0) if 4.0 <= beat * k <= 7.0]
    return float(min(options, key=lambda r: abs(np.log(r / rate)))) if options else rate


class Chain:
    """An amp ready to play: its curves, filters and settings worked out once."""

    def __init__(self, amp: Amp, sr: int, tempo: float | None = None, os_: int = OS):
        self.amp, self.sr, self.os = amp, sr, os_
        fs = sr * os_
        bplus, ra, rk = amp.stage
        self.tab1, _, bias1 = stage_table(bplus, ra, rk, 100e3)  # the pickup and the grid stopper
        self.tab2, drop2, bias2 = stage_table(bplus, ra, rk, amp.source)
        self.drop2 = drop2
        self.stack = stack_ba(amp.treble, amp.middle, amp.bass, amp.voicing)
        self.sos = np.ascontiguousarray(digital(*self.stack, fs, 1000.0))
        kind, rate, depth = amp.tremolo
        self.rate = synced(rate, tempo) if tempo and depth > 0 else rate
        lo, hi, n = TABLE
        step = (hi - lo) / (n - 1)
        at = int(round((bias1 - lo) / step))
        self.gain = float((self.tab1[at + 1] - self.tab1[at - 1]) / (2 * step))  # the stage's gain: about -61
        self.p = np.array([
            bias1, bias2, 1.0 / (fs * amp.source * amp.coupling), 1.0 / (fs * amp.leak * amp.coupling),
            10.0 ** (amp.volume / 20.0), 1.0 / amp.headroom, float(amp.knee), amp.tilt, amp.sag,
            np.exp(-1.0 / (amp.sag_times[0] * fs)), np.exp(-1.0 / (amp.sag_times[1] * fs)),
            1.0 / (1.0 + 2.0 * np.pi * amp.transformer[0] / fs), 1.0 - np.exp(-2.0 * np.pi * amp.transformer[1] / fs),
            1.0 - 2.0 * np.pi * 8.0 / fs, 0.0 if kind == "optical" else 1.0, self.rate / fs, depth,
            np.exp(-1.0 / (0.004 * fs)), np.exp(-1.0 / (0.045 * fs)), lo, step, amp.master,
        ])
        self.up, self.down = _fir(os_)

    def run(self, x: np.ndarray, rev: np.ndarray | None = None) -> np.ndarray:
        """The amp's output (before the cabinet) for pickup voltage x, the resampling's delay taken out."""
        lag = (len(self.down) - 1) // self.os
        xp = np.concatenate([np.asarray(x, dtype=np.float64), np.zeros(lag)])
        rp = np.zeros_like(xp) if rev is None else np.concatenate([np.asarray(rev, dtype=np.float64), np.zeros(lag)])
        return _run(xp, rp, self.up, self.down, self.p, self.tab1, self.tab2, self.drop2, self.sos)[lag:]

    def send(self, x: np.ndarray) -> np.ndarray:
        """What the preamp sends the spring, in the power stage's units: the pickup through the two stages'
        small-signal gain, the tone stack and the volume (the reverb driver hears a clean amp's preamp)."""
        stack = digital(*self.stack, self.sr, 1000.0)
        return sosfilt(stack, x) * self.gain**2 * self.p[4] * self.p[5]


def play(chain: Chain, emf: np.ndarray) -> np.ndarray:
    """The pickup's voltage through the amp, its spring and its cabinet, as the two microphones hear it: (n, 2)."""
    amp, sr = chain.amp, chain.sr
    rev = None
    if amp.reverb > 0:
        rev = oa.convolve(chain.send(emf), spring_ir(amp.tank, sr), len(emf))  # (oaconvolve's, blockwise)
        rev *= amp.reverb
    y = chain.run(emf, rev)
    del rev
    ir = cabinet_ir(amp.cabinet, sr)
    out = np.empty((len(y), ir.shape[1]))  # each microphone through the cabinet, into its column
    for j in range(ir.shape[1]):
        oa.convolve(y, ir[:, j], len(y), out=out[:, j])
    return out


@njit(cache=True, nogil=True)
def _shape(x, up, down, drive, tilt):
    """A preamp's gentle saturation, oversampled: y = (tanh(drive u + tilt) - tanh(tilt)) / (drive tanh'(tilt)),
    unity gain for small signals, a little even distortion from the tilt."""
    n = x.shape[0]
    os_ = up.shape[0]
    per = up.shape[1]
    taps = down.shape[0]
    xb = np.zeros(2 * per)
    zb = np.zeros(2 * taps)
    y = np.zeros(n)
    t0 = np.tanh(tilt)
    norm = 1.0 / (drive * (1.0 - t0 * t0))
    ptr = 0
    zptr = 0
    for i in range(n):
        ptr += 1
        if ptr == per:
            ptr = 0
        xb[ptr] = x[i]
        xb[ptr + per] = x[i]
        for ph in range(os_):
            u = _dot(up[ph], xb, ptr + 1, per)
            v = (np.tanh(drive * u + tilt) - t0) * norm
            zptr += 1
            if zptr == taps:
                zptr = 0
            zb[zptr] = v
            zb[zptr + taps] = v
            if ph == 0:
                y[i] = _dot(down, zb, zptr + 1, taps)
    return y


def preamp(x: np.ndarray, drive: float, tilt: float = 0.1, os_: int = 2) -> np.ndarray:
    """A DI's preamp: x (volts, its peaks near 1) with a touch of saturation, twice oversampled, delay removed."""
    up, down = _fir(os_)
    lag = (len(down) - 1) // os_
    xp = np.concatenate([np.asarray(x, dtype=np.float64), np.zeros(lag)])
    return _shape(xp, up, down, float(drive), float(tilt))[lag:]


def reference_gain(chain: Chain, level: float) -> float:
    """The master volume that brings a steady chord of `level` volts peak from the pickup to a fixed level
    out of the power stage, whatever the amp's gain: an amp's master volume, so a crunch sits about as loud
    as a clean sound played the same."""
    sr = chain.sr
    t = np.arange(int(0.8 * sr)) / sr  # long enough to average a tremolo's swing
    x = (np.sin(2 * np.pi * 110.0 * t) + 0.7 * np.sin(2 * np.pi * 164.8 * t + 1.0)
         + 0.5 * np.sin(2 * np.pi * 220.0 * t + 2.0) + 0.35 * np.sin(2 * np.pi * 277.2 * t + 0.5))
    x *= level / np.max(np.abs(x))
    y = chain.run(x) / chain.amp.master
    return float(0.3 / (np.sqrt(np.mean(y[int(0.2 * sr):] ** 2)) + 1e-12))
