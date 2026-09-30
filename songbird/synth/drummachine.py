"""A drum machine: Roland's TR-808 and TR-909, built the way their circuits make their sounds.

The TR-808 (1980) makes everything with analog circuits, and most of its
drums with one: the bridged-T network, a resonant filter that, struck by the
millisecond-long pulse the sequencer sends, rings on as a decaying sine at its
own frequency, the way a skin would. Its bass drum is one tuned near 50 Hz
(Roland's service notes: 56; Werner, Abel and Smith, DAFx 2014: 49.5 from the
parts) whose decay knob feeds some output back to cancel its damping, so it
rings from a short thud to over a second. Two things bend its pitch, neither
an envelope: for its first 4 to 6 ms a transistor shorts part of the network
and it rings 2.6 times higher (130 Hz, less than one cycle, heard as punch
rather than pitch), and while its swing is big another transistor leaks, so
it starts a few percent sharp and sighs down as it rings away (58 to 48 Hz
over 300 ms in their measurements). The pulse leaks through as the click,
under a one-pole tone control (305 Hz to 7.2 kHz). The snare is two such rings
(173 and 336 Hz on later machines, 238 and 476 on the first), the upper dying
three times faster, and white noise high-passed at 2.75 kHz with its own
envelope, the snappy. The toms and congas ring through diodes that conduct on
the big swings: a hard hit starts up to 1.7 times high and falls as it dies,
and an accent bends it further; the toms add a little dark noise. The rim shot
is two short rings (455 Hz, 1.7 kHz) through a distorting transistor, the
claves one at 2.5 kHz gated after 22 ms, the maracas 30 ms of noise
high-passed at 10.6 kHz.

Its hats, cymbal and cowbell come from six square waves on one chip, always
running: 205, 304, 370 and 523 Hz, and two trimmed at the factory to 540 and
800 Hz (the four untrimmed ones differ from machine to machine). Summed and
band-passed at 3.44 and 7.1 kHz, where none has its fundamental, they make a
clang of high overtones beating against each other, not a chord (a clone that
uses noise here misses the 808's hat). Each voice passes that through a
"swing" VCA, a transistor whose collector supply is the envelope itself: it
switches hard on the overtones' peaks and clips between the envelope and its
own saturation, more as the envelope falls, so a hat gets grittier as it
decays (Werner, Abel and Smith, ICMC 2014); a high-pass after it keeps the top
(7.8 kHz for the open hat, 11.7 for the closed). A closed hat cuts a ringing
open one off. The cowbell is the two trimmed squares, gated, falling fast and
then slowly, through a band-pass near 2.6 kHz; the cymbal both bands through
three envelopes. The clap is noise band-passed at 1.07 kHz, struck three times
about 11 ms apart by a sawtooth through an exponential converter, over a
50 ms "reverb" of the same noise.

The TR-909 (1983) is a hybrid. Its drums are oscillators rather than rings:
the bass drum a triangle rounded into a near-sine by two diodes, swept down
about two octaves in its first 30 to 60 ms (the Tune knob sets how fast), with
a click of pulse and filtered noise and a little saturation; the snare two
such oscillators (about 190 and 345 Hz) bent sharp for 20 ms, each through a
transistor VCA whose envelope starts higher on an accent and so rings longer,
and noise held for 24 ms and then shut off; the toms the same with a deeper
sweep and a noisy attack. Its hats, crash and ride are 6-bit recordings of
real cymbals in ROM, compressed before they were sampled so the grain follows
the sound down, restarted from the top on every hit and shaped by a VCA. Here
each recording is made by striking a modal model of the cymbal (a few hundred
inharmonic modes, bright and dense) and storing it the same way. The 909 has
no cowbell, claves, congas or maracas: asked for them it plays the 808's, as
the house producers who sampled one into the other did.

Playing (Note.art is the piece; pitch and duration are ignored, a drum
machine is triggered): velocity sets the trigger's size, 18 dB from 0.2 to 1
(touch.gain); above 0.8 the accent comes in, 5 dB more by 0.9, and because an
accent is a bigger trigger rather than a louder fader it drives the circuits
harder: a deeper sigh and more click on the 808 kick, a deeper sweep and more
drive on the 909's, a further bend on the toms, a longer ring on the 909
snare's tone, more snap. A piece it doesn't know is played as the closed hat.

Each machine is its maker's (`make`): the parts' tolerances (a kick within
3% of its tuning, the untrimmed squares within 4%, decays and filters within
5 to 15%, the noise's colour) and the knobs as its owner left them (decays,
tone, snappy). `wear` is an old machine: pitch that wanders a few cents,
decays that aren't quite the same twice, and hiss through every VCA. Timing
is the part's, not the machine's. `brightness` turns the tone knobs: the
kick's click, the snappy and the noise's top, the hats' band. `body` retunes
the drums (a bigger body lower and longer). The kit is returned in stereo
as a drum machine's separate outputs would be panned: kick, snare, clap and
rim in the middle, the hats and crash a little right, the toms spread from
right (high) to left (low), as the audience hears a kit.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numba import njit
from scipy.signal import lfilter, sosfilt

from . import modal, osc, touch
from .osc import _blep4

SPAN = 18.0  # dB between pp (0.2) and ff (1), before the accent
ACCENT_DB = 5.0  # what an accent adds, fully in by velocity 0.9
LN1000 = 6.907755278982137

COMMON = ("kick", "snare", "clap", "hat", "hat-open", "hat-pedal", "tom-hi", "tom-mid", "tom-lo", "rim",
          "cowbell", "crash", "ride")
EXTRAS = ("clave", "conga-hi", "conga-mid", "conga-lo", "maracas")  # the 808's own; the 909 borrows them
PIECES = COMMON + EXTRAS
DEFAULT = "hat"
ALIASES = {
    "bd": "kick", "bass": "kick", "bass-drum": "kick", "sd": "snare", "cp": "clap", "handclap": "clap",
    "ch": "hat", "hh": "hat", "hat-closed": "hat", "closed": "hat", "oh": "hat-open", "open": "hat-open",
    "pedal": "hat-pedal", "hat-foot": "hat-pedal", "ht": "tom-hi", "mt": "tom-mid", "lt": "tom-lo",
    "tom": "tom-mid", "rs": "rim", "rimshot": "rim", "side-stick": "rim", "cb": "cowbell", "cy": "crash",
    "cymbal": "crash", "rd": "ride", "cl": "clave", "claves": "clave", "ma": "maracas", "shaker": "maracas",
    "conga": "conga-mid", "hc": "conga-hi", "mc": "conga-mid", "lc": "conga-lo",
}

# Where each piece sits (-1 left .. 1 right), as the audience hears a kit.
PAN = {
    "kick": 0.0, "snare": 0.0, "clap": 0.0, "rim": 0.0, "hat": 0.25, "hat-open": 0.25, "hat-pedal": 0.25,
    "tom-hi": 0.3, "tom-mid": 0.0, "tom-lo": -0.3, "cowbell": 0.15, "crash": 0.35, "ride": -0.35,
    "clave": -0.15, "conga-hi": 0.25, "conga-mid": 0.05, "conga-lo": -0.2, "maracas": 0.35,
}

# What cuts a piece off: the same piece again (its envelope is one capacitor, recharged), and for the open
# hat the closed and pedal hats too (the choke).
CUT_BY = {
    "hat": ("hat", "hat-pedal"), "hat-pedal": ("hat", "hat-pedal"), "hat-open": ("hat", "hat-pedal", "hat-open"),
    "clap": ("clap",), "cowbell": ("cowbell",), "crash": ("crash",), "ride": ("ride",), "clave": ("clave",),
    "maracas": ("maracas",), "rim": ("rim",),
}
CHOKE = 0.004  # s: how fast a choked open hat falls (e-folding)
RETRIGGER = 0.0015  # s: how fast a retriggered envelope lets go of the old sound

DEFAULTS = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0, maker=0, tonic=62)

# The kit's own balance, the owner's level knobs. Each piece's gain is set so that, struck at velocity 0.6,
# its first 100 ms (about as long as the ear takes to judge a hit's loudness) is as loud, K-weighted, as a
# producer would mix it against the kick (BALANCE, dB), averaged over machines. tests/test_drummachine.py
# measures it.
BALANCE = {
    "kick": 0.0, "snare": 0.0, "clap": -1.0, "hat": -10.0, "hat-open": -8.0, "hat-pedal": -14.0, "tom-hi": -2.0,
    "tom-mid": -2.0, "tom-lo": -2.0, "rim": -7.0, "cowbell": -7.0, "crash": -3.0, "ride": -9.0, "clave": -8.0,
    "conga-hi": -4.0, "conga-mid": -4.0, "conga-lo": -4.0, "maracas": -12.0,
}
MIX_808 = {
    "kick": 1.0, "snare": 1.095, "clap": 0.897, "hat": 1.079, "hat-open": 0.286, "hat-pedal": 0.746,
    "tom-hi": 0.732, "tom-mid": 0.655, "tom-lo": 0.634, "rim": 2.635, "cowbell": 1.7, "crash": 0.36, "ride": 0.192,
    "clave": 0.579, "conga-hi": 0.589, "conga-mid": 0.593, "conga-lo": 0.42, "maracas": 0.227,
}
MIX_909 = {
    "kick": 1.0, "snare": 0.478, "clap": 0.784, "hat": 0.792, "hat-open": 0.512, "hat-pedal": 0.743,
    "tom-hi": 0.713, "tom-mid": 0.64, "tom-lo": 0.674, "rim": 2.892, "cowbell": 1.84, "crash": 0.562, "ride": 0.307,
    "clave": 0.613, "conga-hi": 0.669, "conga-mid": 0.613, "conga-lo": 0.445, "maracas": 0.241,
}

SPEC = {
    "drums-808": dict(
        family="drum machine",
        role="percussion",
        register=None,
        place=(0.0, 0.8),
        level=0.4204,
        poly=True,
        articulations={
            "kick": "the bass drum: a ring near 50 Hz with a click and a punch, sighing a few percent flat as it "
                    "booms on (half a second to a second)",
            "snare": "two rings (173 and 336 Hz) and the snappy noise, more tone than rattle",
            "clap": "three bursts of noise about 11 ms apart over a short reverb",
            "hat": "closed hi-hat: the six squares' clang, gone in about 60 ms; chokes an open hat",
            "hat-open": "open hi-hat: the same clang ringing a few hundred ms, until the next closed or pedal hat",
            "hat-pedal": "a foot on the hat: a shorter, softer closed hat; also chokes an open hat",
            "tom-hi": "a ring near 185 Hz whose pitch falls as it dies, a little dark noise under it",
            "tom-mid": "a ring near 135 Hz, the same",
            "tom-lo": "a ring near 90 Hz, the same, longest",
            "rim": "rim shot: two short rings through a distorting transistor, a woody tick",
            "cowbell": "the two trimmed squares (540 and 800 Hz) through a band-pass: a clank, then a short tail",
            "crash": "the cymbal: both bands of the squares, its decay knob up (about two seconds)",
            "ride": "the cymbal with its decay knob down: a shorter wash for time-keeping",
            "clave": "a pure 2.5 kHz ring gated after 22 ms",
            "conga-hi": "the high tom's circuit without its noise, tuned near 400 Hz: purer, bending down",
            "conga-mid": "the same near 280 Hz",
            "conga-lo": "the same near 185 Hz",
            "maracas": "30 ms of very high noise",
        },
        about="a Roland TR-808 by circuit: bridged-T rings for the drums, six square waves and swing VCAs for "
              "hats, cymbal and cowbell, a burst-enveloped clap; velocity is the trigger's size, 0.8 to 0.9 "
              "brings in the accent; unknown pieces play the closed hat",
        # the kick (the probe) is barely brighter hit harder, by its sigh and click; the snare's snap and the
        # toms' bend brighten more; the hats darken a little (their swing VCA clips less on a bigger trigger)
        brighter=0.05,
    ),
    "drums-909": dict(
        family="drum machine",
        role="percussion",
        register=None,
        place=(0.0, 0.8),
        level=0.3964,
        poly=True,
        articulations={
            "kick": "the bass drum: a rounded triangle swept about two octaves down to 54 Hz in 30-60 ms, a "
                    "click of pulse and noise, tighter than the 808's (about 0.4 s)",
            "snare": "two oscillators (190 and 345 Hz) bent sharp for 20 ms and a bright noise held 24 ms: a "
                     "crack",
            "clap": "noise bursts 10 ms apart and a longer reverb than the 808's",
            "hat": "closed hi-hat: a 6-bit recording of a real hat, cut short by the VCA; chokes an open hat",
            "hat-open": "open hi-hat: the recording ringing a few hundred ms, until the next closed or pedal hat",
            "hat-pedal": "a foot on the hat: the recording cut shortest and softer; also chokes an open hat",
            "tom-hi": "an oscillator near 190 Hz swept down from half as high again, a noisy attack",
            "tom-mid": "the same near 135 Hz",
            "tom-lo": "the same near 95 Hz, longest",
            "rim": "rim shot: short rings through a distorting transistor, brighter than the 808's",
            "cowbell": "(the 909 has none) the 808's two squares",
            "crash": "a 6-bit recording of a crash, about two seconds",
            "ride": "a 6-bit recording of a ride: a ping over a wash",
        },
        about="a Roland TR-909 by circuit: swept oscillators for the drums, 6-bit cymbal recordings (made here "
              "from modal models) for hats, crash and ride; velocity is the trigger's size, 0.8 to 0.9 brings "
              "in the accent; the 808's cowbell, claves, congas and maracas when asked; unknown pieces play "
              "the closed hat",
        brighter=0.03,  # the kick, by its accent's deeper sweep, drive and click
    ),
}


# ---------------------------------------------------------------------------------------------- circuits


@njit(cache=True, nogil=True)
def _ring(x, sr, f0, t60, att_ratio, att_n, sigh, knee, n):
    """A bridged-T ring: a two-pole resonance at f0 Hz falling 60 dB in t60 s, driven by x (then left to ring),
    n samples. For the first att_n samples it rings att_ratio times higher, gliding back over half a
    millisecond (the 808 kick's attack); while its swing is well above `knee` its pitch rises by up to `sigh`
    (a fraction): a transistor or a diode conducting on the big swings. Starts like a sine."""
    y = np.zeros(n)
    r = np.exp(-LN1000 / (t60 * sr))
    ramp = max(1.0, 0.0005 * sr)
    settled = att_n + int(ramp) + 2  # after the attack the pitch moves slowly: turn the rotation every 8 samples
    zr = 0.0
    zi = 0.0
    c = r
    s = 0.0
    nx = x.shape[0]
    k2 = 1.0 / (knee * knee)
    for i in range(n):
        if i < settled or i % 8 == 0:
            a2 = (zr * zr + zi * zi) * k2
            f = f0 * (1.0 + sigh * a2 / (1.0 + a2))
            if i < att_n:
                f *= att_ratio
            elif i < att_n + ramp:
                u = (i - att_n) / ramp
                f *= 1.0 + (att_ratio - 1.0) * 0.5 * (1.0 + np.cos(np.pi * u))
            w = 2.0 * np.pi * f / sr
            c = r * np.cos(w)
            s = r * np.sin(w)
        drive = x[i] if i < nx else 0.0
        zr, zi = zr * c - zi * s + drive, zr * s + zi * c
        y[i] = zi
    return y


@njit(cache=True, nogil=True)
def _square(p, d, dt, inv):
    """One sample of a zero-mean pulse wave at phase p, duty d, with osc.pulse's four-point polyBLEP edges."""
    v = 1.0 if p < d else -1.0
    if p < 2.0 * dt:
        v += 2.0 * _blep4(p * inv)
    elif p > 1.0 - 2.0 * dt:
        v += 2.0 * _blep4((p - 1.0) * inv)
    q = p - d
    if q < 0.0:
        q += 1.0
    if q < 2.0 * dt:
        v -= 2.0 * _blep4(q * inv)
    elif q > 1.0 - 2.0 * dt:
        v -= 2.0 * _blep4((q - 1.0) * inv)
    return v - (2.0 * d - 1.0)


@njit(cache=True, nogil=True)
def _bank(freqs, duties, phases, n, sr):
    """Square waves summed, n samples at sr from the given phases: osc.pulse's pulses, all in one pass (the
    808's six are shared by every hat, cymbal and cowbell note)."""
    y = np.zeros(n)
    count = freqs.shape[0]
    ph = phases.copy()
    dts = np.minimum(freqs / sr, 0.25)
    invs = 1.0 / dts
    for i in range(n):
        total = 0.0
        for k in range(count):
            total += _square(ph[k], duties[k], dts[k], invs[k])
            ph[k] += dts[k]
            if ph[k] >= 1.0:
                ph[k] -= 1.0
        y[i] = total
    return y


@njit(cache=True, nogil=True)
def _hat808(freqs, duties, phases, pre, n, sr, bp, norm, env, vt, theta, lower, alpha, hp):
    """An 808 hat at the oversampled rate, in one pass: the six squares (from `pre` samples before the hit, so
    the band-pass has settled), the band-pass (a biquad, b0 b1 b2 a1 a2), the swing VCA with the envelope
    `env` (see _swing), the high-pass after it."""
    y = np.zeros(n)
    count = freqs.shape[0]
    ph = phases.copy()
    dts = np.minimum(freqs / sr, 0.25)
    invs = 1.0 / dts
    s1 = 0.0
    s2 = 0.0
    t1 = 0.0
    t2 = 0.0
    root = 1.0 / alpha
    for i in range(pre + n):
        total = 0.0
        for k in range(count):
            total += _square(ph[k], duties[k], dts[k], invs[k])
            ph[k] += dts[k]
            if ph[k] >= 1.0:
                ph[k] -= 1.0
        o = bp[0] * total + s1
        s1 = bp[1] * total - bp[3] * o + s2
        s2 = bp[2] * total - bp[4] * o
        if i >= pre:
            j = i - pre
            e = env[j]
            current = np.exp(min((o * norm - theta) / vt, 40.0))
            ceiling = e * (1.0 - lower) + 1e-12
            x = current / ceiling
            if x < 1e-3:  # the transistor barely on: linear
                sw = e - ceiling * x
            elif x > 1e3:  # hard against the ceiling
                sw = e - ceiling
            else:
                sw = e - ceiling * x / (1.0 + x**alpha) ** root
            u = hp[0] * sw + t1
            t1 = hp[1] * sw - hp[3] * u + t2
            t2 = hp[2] * sw - hp[4] * u
            y[j] = u
    return y


def _biquad(kind: str, f: float, q: float, sr: float) -> np.ndarray:
    """One second-order section (RBJ's cookbook): a low-pass, high-pass, or band-pass with 0 dB at its peak."""
    f = min(f, 0.45 * sr)
    w = 2.0 * np.pi * f / sr
    cw, alpha = np.cos(w), np.sin(w) / (2.0 * q)
    if kind == "lp":
        b = [(1.0 - cw) / 2.0, 1.0 - cw, (1.0 - cw) / 2.0]
    elif kind == "hp":
        b = [(1.0 + cw) / 2.0, -(1.0 + cw), (1.0 + cw) / 2.0]
    else:
        b = [alpha, 0.0, -alpha]
    a = [1.0 + alpha, -2.0 * cw, 1.0 - alpha]
    return np.array([[b[0] / a[0], b[1] / a[0], b[2] / a[0], 1.0, a[1] / a[0], a[2] / a[0]]])


def _onepole(x: np.ndarray, f: float, sr: float) -> np.ndarray:
    """A one-pole low-pass at f Hz (the 808's tone controls are an RC)."""
    p = np.exp(-2.0 * np.pi * f / sr)
    return lfilter([1.0 - p], [1.0, -p], x)


def _noise_gain(sos: np.ndarray, sr: float) -> float:
    """The RMS a filter gives unit white noise, from its impulse response."""
    h = sosfilt(sos, np.r_[1.0, np.zeros(int(0.2 * sr))])
    return float(np.sqrt(np.sum(h * h)))


SWING = (0.4, 0.8, 0.1, 3.5)  # the swing VCA: vt, theta, lower, alpha (see _swing)
SOS = [0, 1, 2, 4, 5]  # a second-order section's b0 b1 b2 a1 a2


def _swing(v: np.ndarray, env: np.ndarray, vt: float = SWING[0], theta: float = SWING[1], lower: float = SWING[2],
           alpha: float = SWING[3]) -> np.ndarray:
    """The 808's swing-type VCA: a common-emitter transistor whose collector supply is the envelope.

    v is the source at the base (unit RMS). Its collector current rises exponentially with v (scale vt, and
    reaching the start's ceiling at v = theta), and the output falls from the envelope toward the
    transistor's saturation (a `lower` fraction of the envelope), with corners as round as Werner, Abel and
    Smith's fit (alpha 3.5). While the envelope is high the current seldom reaches it and the output is a
    train of peaks; as it falls the same current clips flat against it, wider and squarer: grittier as it
    decays. The output rides on the envelope; the high-pass after takes that away."""
    current = np.exp(np.minimum((v - theta) / vt, 40.0))
    ceiling = env * (1.0 - lower) + 1e-12
    x = np.minimum(current / ceiling, 1e6)
    return env - ceiling * x / (1.0 + x**alpha) ** (1.0 / alpha)


def _noise(rng: np.random.Generator, n: int, tilt: float) -> np.ndarray:
    """White noise with a machine's own colour: a first-difference tilt of `tilt` (+-0.12 moves 10 kHz about a
    decibel and 5 kHz a quarter of one: Whittle heard no difference between one 808's noise and another's, so
    it stays small)."""
    x = rng.standard_normal(n + 1)
    return x[1:] + tilt * (x[1:] - x[:-1])


def _saturate(x: np.ndarray, limit: float) -> np.ndarray:
    """A transistor stage's soft ceiling: linear for small signals, rounding off toward +-limit."""
    return limit * np.tanh(x / limit)


def _soft_gate(env: np.ndarray, theta: float, soft: float = 0.02) -> np.ndarray:
    """A transistor VCA with a threshold: what passes is the envelope's excess over theta, the corner rounded
    (a parabola `soft` either side of it), and nothing at all below."""
    d = env - theta
    return np.where(d > soft, d, np.where(d < -soft, 0.0, (d + soft) ** 2 / (4.0 * soft)))


def _attack(n: int, sr: float, rise: float) -> np.ndarray:
    """An envelope's first moment: a quarter-sine rise over `rise` seconds, then 1."""
    out = np.ones(n)
    k = min(n, int(np.ceil(rise * sr)))
    out[:k] = np.sin(0.5 * np.pi * np.arange(k) / (rise * sr))
    return out


def _cut(env: np.ndarray, at: int | None, tau: float, sr: float) -> tuple[np.ndarray, int]:
    """An envelope discharged from sample `at` on with time constant tau; returns it and where it is gone."""
    n = len(env)
    if at is None or at >= n:
        return env, n
    at = max(at, 0)
    gone = min(n, at + int(9.0 * tau * sr) + 1)
    env = env[:gone].copy()
    env[at:] *= np.exp(-np.arange(gone - at) / (tau * sr))
    return env, gone


# ---------------------------------------------------------------------------------------------- a hit


class Hit:
    """One trigger: where it lands, how big it is, and its own randomness (the noise it catches, the wear)."""

    __slots__ = ("i", "t", "vel", "size", "accent", "rng", "cents", "loose", "cut", "cut_tau")

    def __init__(self, i, t, vel, rng, cents, loose, cut, cut_tau):
        self.i, self.t, self.vel, self.rng = i, t, vel, rng
        vel = float(np.clip(vel, 0.0, 1.0))
        u = min(max((vel - 0.8) / 0.1, 0.0), 1.0)
        self.accent = u * u * (3.0 - 2.0 * u)
        self.size = touch.gain(vel, SPAN) * 10.0 ** (ACCENT_DB * self.accent / 20.0)
        self.cents, self.loose, self.cut, self.cut_tau = cents, loose, cut, cut_tau

    @property
    def detune(self) -> float:
        return 2.0 ** (self.cents / 1200.0)


def _rimshot(h: Hit, freqs, t60s, weights, sr2: float, hp: np.ndarray) -> np.ndarray:
    """A rim shot: short rings, struck together, into a swing VCA whose supply dies in a few milliseconds (the
    distortion is the sound: a woody tick with a pitch), the thump high-passed away, gated shut after 22 ms."""
    n2 = int(0.03 * sr2) // 2 * 2
    pulse = _pulse(1.0, sr2)
    x = np.zeros(n2)
    for f, t60, w in zip(freqs, t60s, weights):
        x += w * _ring(pulse, sr2, f * h.detune, t60, 1.0, 0, 0.0, 1.0, n2)
    v = x / (np.std(x[: int(0.01 * sr2)]) + 1e-12) * (1.0 + 0.3 * h.accent)  # a bigger trigger drives it harder
    env = h.size * _attack(n2, sr2, 0.0002) * np.exp(-np.arange(n2) / (0.004 * sr2))
    y = sosfilt(hp, _swing(v, env))
    gate = np.clip((0.022 - np.arange(n2) / sr2) / 0.002, 0.0, 1.0)
    return osc.decimate2(y * gate)


def _pulse(size: float, sr: float) -> np.ndarray:
    """The sequencer's 1 ms trigger as the pulse shaper passes it on: its rising edge, a kick that dies in a
    tenth of a millisecond (the falling edge is clamped by a diode and barely counts). Scaled so a low ring it
    strikes swings to `size`; one at a few kHz, a little less (the edge's own roll-off)."""
    k = np.arange(max(2, int(round(0.0006 * sr))))
    edge = np.exp(-k / (1e-4 * sr))
    return edge * (size / edge.sum())


# ---------------------------------------------------------------------------------------------- the 808


OSC_808 = (205.3, 369.6, 304.4, 522.7, 800.0, 540.0)  # Hz; the last two trimmed at the factory (the cowbell's)


class TR808:
    """One TR-808: its parts' tolerances drawn from `make`, its knobs as its owner left them."""

    def __init__(self, sr: int, make: np.random.Generator, s: dict):
        self.sr = sr
        b = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
        size = float(np.clip(s.get("body", 1.0), 0.8, 1.25)) ** 0.5

        def tol(spread):
            return 1.0 + spread * make.uniform(-1.0, 1.0)

        # bass drum
        self.bd_f0 = 50.5 * tol(0.03) / size
        self.bd_t60 = 0.45 * 2.0 ** make.uniform(0.0, 1.1) * size  # the decay knob: 0.45 to 0.97 s
        self.bd_attack = 0.0045 * tol(0.2)
        self.bd_sigh = 0.16 * tol(0.2)
        self.bd_click = 0.9 * tol(0.2)
        self.bd_tone = 305.0 * (7200.0 / 305.0) ** (0.15 + 0.6 * b) * tol(0.1)
        # snare: two rings and the snappy
        self.sd_f = (173.0 * tol(0.03) / size, 336.0 * tol(0.03) / size)
        self.sd_t60 = (0.20 * tol(0.15) * size, 0.065 * tol(0.15) * size)
        self.sd_tone = 0.55 * tol(0.2)
        self.sd_snappy = 0.45 * tol(0.2) * 2.0 ** (b - 0.5)
        self.sd_noise = np.vstack([_biquad("hp", 2750.0 * tol(0.05), 0.7, sr),
                                   _biquad("lp", 7000.0 * 2.0 ** (b - 0.5) * tol(0.05), 0.7, sr)])
        self.sd_noise_rms = _noise_gain(self.sd_noise, sr)
        self.sd_tau = 0.0155 * tol(0.15)
        # clap
        self.cp_period = 0.011 * tol(0.08)
        self.cp_bp = _biquad("bp", 1070.0 * tol(0.05) * 2.0 ** (0.3 * (b - 0.5)), 1.6, sr)
        self.cp_rms = _noise_gain(self.cp_bp, sr)
        self.cp_tail = 0.05 * tol(0.1)
        self.cp_tail_level = 0.3 * tol(0.15)
        self.cp_levels = (1.0, 0.85, 0.7)
        # toms and congas: (Hz, T60 s) for hi, mid, lo
        self.tom = tuple((f * tol(0.03) / size, t * tol(0.15) * size) for f, t in ((185.0, 0.30), (135.0, 0.40),
                                                                                (90.0, 0.62)))
        self.conga = tuple((f * tol(0.03) / size, t * tol(0.15) * size) for f, t in ((400.0, 0.30), (280.0, 0.30),
                                                                                  (185.0, 0.65)))
        # rim shot and claves
        self.rs_f = (455.0 * tol(0.05), 1700.0 * tol(0.05))
        self.rs_hp = _biquad("hp", 200.0, 0.7071, 2.0 * sr)
        self.cl_f = 2500.0 * tol(0.03)
        # maracas
        self.ma_hp = _biquad("hp", 10600.0 * tol(0.05) * 2.0 ** (0.3 * (b - 0.5)), 2.3, sr)
        self.ma_rms = _noise_gain(self.ma_hp, sr)
        # the six squares: the four untrimmed within 4% of their design, the trimmed two within 1%
        self.osc_f = np.array([f * tol(0.04 if k < 4 else 0.01) for k, f in enumerate(OSC_808)])
        self.osc_duty = np.array([0.4798 * tol(0.01) for _ in OSC_808])
        self.osc_phase = make.uniform(0.0, 1.0, len(OSC_808))
        sr2 = 2.0 * sr
        shift = 2.0 ** (0.5 * (b - 0.5))
        self.bp_hi = _biquad("bp", 7100.0 * tol(0.05), 5.0 * tol(0.2), sr2)
        self.bp_lo = _biquad("bp", 3440.0 * tol(0.05), 5.0 * tol(0.2), sr2)
        self.hp_oh = _biquad("hp", 7800.0 * tol(0.05) * shift, 1.5, sr2)
        self.hp_ch = _biquad("hp", 11700.0 * tol(0.05) * shift, 1.5, sr2)
        self.hp_pedal = _biquad("hp", 9000.0 * tol(0.05) * shift, 1.2, sr2)
        self.ch_tau = 0.016 * tol(0.15)
        self.oh_tau = 0.08 * 2.0 ** make.uniform(-0.4, 0.4)  # the open hat's decay knob
        self.pedal_tau = 0.008 * tol(0.15)
        # cymbal: low band, the variable high band (the decay knob: crash long, ride short), the short high band
        self.cy_tau = (0.10 * tol(0.15), 0.34 * tol(0.2), 0.14 * tol(0.2), 0.02 * tol(0.15))
        self.cy_hp = (_biquad("hp", 2500.0 * tol(0.05) * shift, 1.0, sr2),
                      _biquad("hp", 9000.0 * tol(0.05) * shift, 1.5, sr2),
                      _biquad("hp", 10500.0 * tol(0.05) * shift, 2.0, sr2))
        # cowbell
        self.cb_bp = _biquad("bp", 2640.0 * tol(0.05), 1.3, sr2)
        self.cb_tau = (0.005 * tol(0.15), 0.03 * tol(0.15))
        # the metal's level at the band-passes, to set the swing VCAs' operating point
        probe = self._squares(0.0, int(0.05 * sr2), sr2, 1.0)
        self.hi_norm = 1.0 / (np.std(sosfilt(self.bp_hi, probe)[int(0.01 * sr2):]) + 1e-12)
        self.lo_norm = 1.0 / (np.std(sosfilt(self.bp_lo, probe)[int(0.01 * sr2):]) + 1e-12)
        # the output coupling: a gentle high-pass at 20 Hz, so a ring's lopsided start leaves no DC
        self.hp_out = _biquad("hp", 20.0, 0.7071, sr)
        self.tilt = 0.12 * make.uniform(-1.0, 1.0)  # its noise's colour

    # -- the square bank

    def _squares(self, t0: float, n2: int, sr2: float, detune: float, which=(0, 1, 2, 3, 4, 5)) -> np.ndarray:
        """The chosen squares summed, n2 samples at sr2 from the machine's time t0 (they never stop)."""
        k = np.array(which)
        f = self.osc_f[k] * detune
        return _bank(f, self.osc_duty[k], (self.osc_phase[k] + f * t0) % 1.0, n2, sr2)

    # -- the voices

    def kick(self, h: Hit) -> np.ndarray:
        sr = self.sr
        t60 = self.bd_t60 * h.loose
        n = int((1.35 * t60 + 0.03) * sr)
        pulse = _pulse(h.size, sr)
        body = _ring(pulse, float(sr), self.bd_f0 * h.detune, t60, 2.6, int(self.bd_attack * sr), self.bd_sigh,
                     0.5, n)
        # the pulse leaks through: its two edges, as the pulse shaper differentiates it (the falling one, 1 ms
        # on, clamped small by a diode)
        k = np.arange(int(0.0008 * sr))
        edge = np.exp(-k / (1e-4 * sr))
        click = np.zeros(n)
        click[: len(k)] += edge
        fall = int(round(0.001 * sr))
        click[fall: fall + len(k)] -= 0.25 * edge
        y = body + click * (h.size * self.bd_click * (1.0 + 0.5 * h.accent))
        return sosfilt(self.hp_out, _onepole(y, self.bd_tone, sr))

    def snare(self, h: Hit) -> np.ndarray:
        sr = self.sr
        (f1, f2), (t1, t2) = self.sd_f, self.sd_t60
        n = int((1.35 * t1 * h.loose + 0.02) * sr)
        pulse = _pulse(h.size, sr)
        low = _ring(pulse, float(sr), f1 * h.detune, t1 * h.loose, 1.0, 0, 0.0, 1.0, n)
        high = _ring(pulse, float(sr), f2 * h.detune, t2 * h.loose, 1.0, 0, 0.0, 1.0, n)
        y = (1.0 - 0.5 * self.sd_tone) * low + self.sd_tone * high
        m = min(n, int(9.0 * self.sd_tau * h.loose * sr))
        noise = sosfilt(self.sd_noise, _noise(h.rng, m + 256, self.tilt))[256:] / self.sd_noise_rms
        env = _attack(m, sr, 0.001) * np.exp(-np.arange(m) / (self.sd_tau * h.loose * sr))
        # its VCA is one transistor fed 130 mV rms of noise, past its linear range: the peaks are rounded off
        y[:m] += _saturate(noise, 1.8) * env * (h.size * self.sd_snappy * (1.0 + 0.3 * h.accent))
        return sosfilt(self.hp_out, y)

    def clap(self, h: Hit) -> np.ndarray:
        sr = self.sr
        n = int((self.cp_tail * 9.0 + 0.04) * sr)
        noise = sosfilt(self.cp_bp, _noise(h.rng, n + 256, self.tilt))[256:] / self.cp_rms
        t = np.arange(n) / sr
        period = self.cp_period
        kappa = 3.5
        bursts = np.zeros(n)
        for k, level in enumerate(self.cp_levels):
            s = t - k * period
            span = period if k < len(self.cp_levels) - 1 else 0.5 * period  # the third is stopped half way
            live = (s >= 0.0) & (s < span + 0.0006)
            ss = s[live]
            shape = (np.exp(kappa * (1.0 - ss / period)) - 1.0) / (np.exp(kappa) - 1.0)
            rise = np.sin(0.5 * np.pi * np.minimum(ss / 0.0002, 1.0))
            fall = np.clip((span + 0.0006 - ss) / 0.0006, 0.0, 1.0)
            bursts[live] += level * shape * rise * fall
        tail = self.cp_tail_level * np.exp(-t / self.cp_tail) * _attack(n, sr, 0.001)
        bursts, gone = _cut(bursts * (1.0 + 0.4 * h.accent), h.cut, RETRIGGER, sr)
        tail, gone = _cut(tail, h.cut, RETRIGGER, sr)
        # the bursts' VCA is an OTA, whose differential pair saturates the noise it is fed (a tanh): distorted
        # noise with its peaks rounded off; the tail's transistor VCA only rounds the biggest
        noise = noise[:gone]
        return (_saturate(noise, 1.2) * bursts + _saturate(noise, 2.5) * tail) * h.size

    def _hat(self, h: Hit, tau: float, hp: np.ndarray) -> np.ndarray:
        sr2 = 2.0 * self.sr
        tau = tau * h.loose
        n2 = int((7.5 * tau + 0.004) * sr2) // 2 * 2
        env = _attack(n2, sr2, 0.0002) * np.exp(-np.arange(n2) / (tau * sr2)) * h.size
        cut = None if h.cut is None else 2 * h.cut
        env, gone = _cut(env, cut, h.cut_tau, sr2)
        pre = int(0.004 * sr2)  # the squares never stop: the band-pass is already ringing when the VCA opens
        f = self.osc_f * h.detune
        phase = (self.osc_phase + f * (h.t - pre / sr2)) % 1.0
        y = _hat808(f, self.osc_duty, phase, pre, gone // 2 * 2, sr2, self.bp_hi[0, SOS], self.hi_norm, env,
                    SWING[0], SWING[1], SWING[2], SWING[3], hp[0, SOS])
        return osc.decimate2(y)

    def hat(self, h: Hit) -> np.ndarray:
        return self._hat(h, self.ch_tau, self.hp_ch)

    def hat_open(self, h: Hit) -> np.ndarray:
        return self._hat(h, self.oh_tau, self.hp_oh)

    def hat_pedal(self, h: Hit) -> np.ndarray:
        return self._hat(h, self.pedal_tau, self.hp_pedal)

    def _cymbal(self, h: Hit, decay: float) -> np.ndarray:
        sr, sr2 = self.sr, 2.0 * self.sr
        taus = (self.cy_tau[0], decay, self.cy_tau[3])
        n2 = int((7.0 * max(taus) * h.loose + 0.004) * sr2) // 2 * 2
        pre = int(0.004 * sr2)
        src = self._squares(h.t - pre / sr2, n2 + pre, sr2, h.detune)
        lo = sosfilt(self.bp_lo, src)[pre:] * self.lo_norm
        hi = sosfilt(self.bp_hi, src)[pre:] * self.hi_norm
        rise = _attack(n2, sr2, 0.0002) * h.size
        k = np.arange(n2)
        y = np.zeros(n2)
        for band, tau, hp, weight in ((lo, taus[0], self.cy_hp[0], 0.8), (hi, taus[1], self.cy_hp[1], 1.0),
                                      (hi, taus[2], self.cy_hp[2], 0.6)):
            env = rise * np.exp(-k / (tau * h.loose * sr2))
            y += weight * sosfilt(hp, _swing(band, env))
        cut = None if h.cut is None else 2 * h.cut
        y, gone = _cut(y, cut, h.cut_tau, sr2)
        return osc.decimate2(y[: gone // 2 * 2])

    def crash(self, h: Hit) -> np.ndarray:
        return self._cymbal(h, self.cy_tau[1])

    def ride(self, h: Hit) -> np.ndarray:
        return self._cymbal(h, self.cy_tau[2])

    def cowbell(self, h: Hit) -> np.ndarray:
        sr, sr2 = self.sr, 2.0 * self.sr
        fast, slow = self.cb_tau
        n2 = int((9.0 * slow + 0.005) * sr2) // 2 * 2
        t = np.arange(n2) / sr2
        env = (0.5 * np.exp(-t / fast) + 0.5 * np.exp(-t / (slow * h.loose))) * _attack(n2, sr2, 0.0002) * h.size
        cut = None if h.cut is None else 2 * h.cut
        env, gone = _cut(env, cut, h.cut_tau, sr2)
        y = np.zeros(gone)
        for k in (4, 5):  # each square through its own gate: the envelope when off, near saturation when on
            y += env * (0.55 - 0.45 * self._squares(h.t, gone, sr2, h.detune, which=(k,)))
        return osc.decimate2(sosfilt(self.cb_bp, y)[: gone // 2 * 2])

    def _tom(self, h: Hit, f: float, t60: float, noisy: bool) -> np.ndarray:
        sr = self.sr
        t60 = t60 * h.loose
        n = int((1.35 * t60 + 0.02) * sr)
        y = _ring(_pulse(h.size, sr), float(sr), f * h.detune, t60, 1.0, 0, 0.7, 0.75, n)
        if noisy:  # pink noise, low-passed at 400 Hz, a little longer than the tone: "artificial reverberation"
            m = min(n, int(0.085 * 7.0 * sr))
            rumble = _onepole(_noise(h.rng, m + 512, self.tilt), 400.0, sr)[512:]
            rumble /= np.std(rumble) + 1e-12
            y[:m] += 0.05 * h.size * rumble * np.exp(-np.arange(m) / (0.085 * sr)) * _attack(m, sr, 0.001)
        return sosfilt(self.hp_out, y)

    def tom_hi(self, h):
        return self._tom(h, *self.tom[0], True)

    def tom_mid(self, h):
        return self._tom(h, *self.tom[1], True)

    def tom_lo(self, h):
        return self._tom(h, *self.tom[2], True)

    def conga_hi(self, h):
        return self._tom(h, *self.conga[0], False)

    def conga_mid(self, h):
        return self._tom(h, *self.conga[1], False)

    def conga_lo(self, h):
        return self._tom(h, *self.conga[2], False)

    def rim(self, h: Hit) -> np.ndarray:
        return _rimshot(h, self.rs_f, (0.032, 0.017), (1.0, 0.8), 2.0 * self.sr, self.rs_hp)

    def clave(self, h: Hit) -> np.ndarray:
        sr = self.sr
        n = int(0.026 * sr)
        y = _ring(_pulse(h.size, sr), float(sr), self.cl_f * h.detune, 0.25, 1.0, 0, 0.0, 1.0, n)
        gate = 0.5 * (1.0 + np.cos(np.pi * np.clip((np.arange(n) / sr - 0.020) / 0.0025, 0.0, 1.0)))
        return y * gate

    def maracas(self, h: Hit) -> np.ndarray:
        sr = self.sr
        n = int(0.1 * sr)
        noise = sosfilt(self.ma_hp, _noise(h.rng, n + 256, self.tilt))[256:] / self.ma_rms
        env = _attack(n, sr, 0.0015) * np.exp(-np.arange(n) / (0.012 * h.loose * sr)) * h.size
        env, gone = _cut(env, h.cut, RETRIGGER, sr)
        return noise[:gone] * env


# ---------------------------------------------------------------------------------------------- the 909


@lru_cache(maxsize=8)
def _cymbal_rom(kind: str, sr: int, clock: float) -> np.ndarray:
    """A 6-bit recording of a real cymbal, as the 909 keeps in ROM: struck once (a modal model: a few hundred
    inharmonic modes, the higher the shorter, a shimmer of noise, the stick's tick), compressed flat before it
    was sampled, 64 levels, then played through the DAC's filter. `clock` is the machine's ROM clock against
    its design (within 2%): the whole recording plays that much higher. The same for every machine and
    every hit: it is a recording."""
    rng = np.random.default_rng({"hat": 909, "crash": 9091, "ride": 9092}[kind])
    # a cymbal's modes crowd so close (and its nonlinearity spreads them so) that its wash is nearly noise: a
    # thousand or more, or the mids ring as separate lines (360 left the crash's 1-2 kHz 37 dB peakier than
    # noise; 1600, 3 dB)
    if kind == "hat":  # an open hi-hat struck with a stick: dense modes 2.5 to 17 kHz, the most near 8
        length, count, lo, hi, centre, width, ring = 1.6, 900, 2200.0, 17000.0, 8000.0, 0.9, 1.8
    elif kind == "crash":  # a thin crash: broad, bright, long
        length, count, lo, hi, centre, width, ring = 2.4, 1600, 300.0, 16000.0, 4500.0, 1.3, 3.2
    else:  # a ride's wash
        length, count, lo, hi, centre, width, ring = 2.2, 1200, 400.0, 15000.0, 3500.0, 1.1, 2.6
    n = int(length * sr)
    f = np.exp(rng.uniform(np.log(lo), np.log(hi), count))
    amp = np.exp(-0.5 * (np.log2(f / centre) / width) ** 2) * rng.uniform(0.3, 1.0, count)
    t60 = ring * (f / 1000.0) ** -0.45 * rng.uniform(0.7, 1.3, count)
    if kind == "ride":  # the stick on the bow: a few strong modes 2.5 to 5 kHz, a ping over the wash
        ping = np.exp(rng.uniform(np.log(2500.0), np.log(5000.0), 12))
        f = np.r_[f, ping]
        amp = np.r_[amp, 2.5 * np.sqrt(count / 260.0) * rng.uniform(0.6, 1.0, 12)]  # as loud against the wash
        t60 = np.r_[t60, rng.uniform(0.5, 0.9, 12)]
    phase = rng.uniform(0.0, 2.0 * np.pi, len(f))
    out = np.zeros((1, n))
    modal.ring(out, 0, np.zeros(0), f * clock, amp * np.cos(phase), amp * np.sin(phase), t60 / clock,
               t60 / clock, -1, 1.0, np.array([1.0]), float(sr), 1e-7)
    y = out[0]
    y /= np.sqrt(np.mean(y[: int(0.1 * sr)] ** 2)) + 1e-12
    # the shimmer between the modes, and the stick
    sos = np.vstack([_biquad("hp", 0.5 * centre, 0.7, sr), _biquad("lp", min(2.0 * centre, 0.4 * sr), 0.7, sr)])
    shimmer = sosfilt(sos, rng.standard_normal(n)) / _noise_gain(sos, sr)
    y += 0.5 * shimmer * np.exp(-np.arange(n) / (0.15 * ring * sr / clock))
    tick = int(0.002 * sr)
    y[:tick] += 1.0 * sosfilt(_biquad("hp", 2000.0, 0.7, sr), rng.standard_normal(tick)) * np.exp(
        -np.arange(tick) / (0.0004 * sr))
    # compressed flat before sampling (the envelope divided out: a level followed both ways, so it is there from
    # the first sample), the converter's range set a little under the loudest peaks (it clips the rare ones),
    # 6 bits, expanded again by the playback VCA
    p = np.exp(-1.0 / (0.004 * sr))
    power = lfilter([1.0 - p], [1.0, -p], y * y)
    power = lfilter([1.0 - p], [1.0, -p], power[::-1])[::-1]
    level = np.sqrt(np.maximum(power, 1e-6 * power.max()))
    flat = y / level
    flat = np.clip(flat / np.percentile(np.abs(flat), 99.9), -1.0, 1.0)
    stored = (np.floor(flat * 31.999 + 32.0) - 31.5) / 32.0  # 64 levels, mid-rise
    dac = sosfilt(np.vstack([_biquad("lp", 14000.0, 0.7071, sr), _biquad("hp", 400.0, 0.7071, sr)]), stored)
    fade = np.ones(n)
    fade[-int(0.3 * sr):] = np.linspace(1.0, 0.0, int(0.3 * sr))
    fade *= _attack(n, sr, 0.0003)  # a recording starts from silence: the stick's contact
    if kind == "hat":  # the hats' decay is the VCA's; the recording is kept flat
        return dac * fade
    return dac * level / level.max() * fade  # the crash and ride: the recording's own decay, re-imposed


class TR909:
    """One TR-909: its parts' tolerances drawn from `make`, its knobs as its owner left them; an 808 beside it
    for the pieces the 909 hasn't got."""

    def __init__(self, sr: int, make: np.random.Generator, s: dict):
        self.sr = sr
        b = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
        size = float(np.clip(s.get("body", 1.0), 0.8, 1.25)) ** 0.5

        def tol(spread):
            return 1.0 + spread * make.uniform(-1.0, 1.0)

        # bass drum: pitch, the Tune knob (how fast the sweep falls), decay, the attack knob
        self.bd_f = 54.0 * tol(0.03) / size
        self.bd_sweep = 0.012 * 2.0 ** make.uniform(-0.4, 0.4)
        self.bd_t60 = 0.42 * 2.0 ** make.uniform(-0.35, 0.35) * size
        self.bd_click = 0.6 * tol(0.25)
        self.bd_noise = _biquad("lp", 3500.0 * 2.0 ** (b - 0.5) * tol(0.05), 0.7071, sr)
        self.bd_noise_rms = _noise_gain(self.bd_noise, sr)
        # snare
        self.sd_f = (190.0 * tol(0.03) / size, 345.0 * tol(0.03) / size)
        self.sd_tau = (0.045 * tol(0.15) * size, 0.025 * tol(0.15) * size)
        self.sd_noise_tau = 0.06 * tol(0.2)
        self.sd_snappy = 0.75 * tol(0.2) * 2.0 ** (b - 0.5)
        self.sd_noise = np.vstack([_biquad("hp", 1400.0 * tol(0.05), 0.7, sr),
                                   _biquad("lp", 9000.0 * 2.0 ** (b - 0.5) * tol(0.05), 0.7, sr)])
        self.sd_noise_rms = _noise_gain(self.sd_noise, sr)
        # clap
        self.cp_period = 0.010 * tol(0.08)
        self.cp_bp = _biquad("bp", 1200.0 * tol(0.05) * 2.0 ** (0.3 * (b - 0.5)), 1.3, sr)
        self.cp_rms = _noise_gain(self.cp_bp, sr)
        self.cp_tail = 0.065 * tol(0.1)
        self.cp_tail_level = 0.35 * tol(0.15)
        self.cp_levels = (1.0, 0.9, 0.8)
        # toms: (Hz, T60 s) for hi, mid, lo
        self.tom = tuple((f * tol(0.03) / size, t * tol(0.15) * size) for f, t in ((190.0, 0.35), (135.0, 0.45),
                                                                                (95.0, 0.55)))
        self.tom_noise = _biquad("lp", 2500.0 * 2.0 ** (b - 0.5), 0.7071, sr)
        self.tom_noise_rms = _noise_gain(self.tom_noise, sr)
        # rim shot
        self.rs_f = (500.0 * tol(0.05), 1750.0 * tol(0.05), 3300.0 * tol(0.05))
        self.rs_hp = _biquad("hp", 300.0, 0.7071, 2.0 * sr)
        # the cymbal ROMs, their clock (and the crash and ride's Tune knobs, which play them faster or slower:
        # the brightness), and the hats' VCA knobs
        self.clock = tol(0.02)
        self.cymbal_tune = 2.0 ** (0.5 * (b - 0.5))
        self.ch_tau = 0.015 * tol(0.15)
        self.oh_tau = 0.085 * 2.0 ** make.uniform(-0.4, 0.4)
        self.pedal_tau = 0.007 * tol(0.15)
        self.hat_tone = _biquad("lp", 11000.0 * 2.0 ** (0.8 * (b - 0.5)), 0.7071, sr)
        self.hp_out = _biquad("hp", 20.0, 0.7071, sr)
        self.borrowed = TR808(sr, make, s)
        self.tilt = 0.12 * make.uniform(-1.0, 1.0)  # its noise's colour (a shift register's, clocked a little
        # faster or slower from one 909 to the next)

    def kick(self, h: Hit) -> np.ndarray:
        sr, sr2 = self.sr, 2.0 * self.sr
        t60 = self.bd_t60 * h.loose
        n = int((1.3 * t60 + 0.02) * sr)
        t = np.arange(2 * n) / sr2
        depth = 3.0 * (1.0 + 0.3 * h.accent)  # the sweep starts (1 + depth) times the final pitch
        freq = self.bd_f * h.detune * (1.0 + depth * np.exp(-t / self.bd_sweep))
        tri, _ = osc.triangle(freq, sr2, 0.75)
        drive = 1.6 + 0.8 * h.accent
        body = np.tanh(drive * tri) / np.tanh(drive)
        body *= _attack(2 * n, sr2, 0.0003) * np.exp(-t * LN1000 / t60)
        y = osc.decimate2(body) * h.size
        # the click: a short pulse and a burst of filtered noise (the Attack knob)
        m = int(0.012 * sr)
        tick = np.zeros(m)
        width = max(2, int(0.0006 * sr))
        tick[:width] = np.sin(np.pi * np.arange(width) / width)
        noise = sosfilt(self.bd_noise, _noise(h.rng, m + 256, self.tilt))[256:] / self.bd_noise_rms
        tick += 0.35 * noise * np.exp(-np.arange(m) / (0.003 * sr))
        y[:m] += tick * (h.size * self.bd_click * (1.0 + 0.6 * h.accent))
        y = np.tanh(0.5 * y) / 0.5  # the VCA and output stage, pushed by a big trigger
        return sosfilt(self.hp_out, y)

    def snare(self, h: Hit) -> np.ndarray:
        sr, sr2 = self.sr, 2.0 * self.sr
        n = int(0.3 * sr)
        t = np.arange(2 * n) / sr2
        bend = 1.0 + 0.2 * np.exp(-t / 0.006)  # ENV1: the pitch pushed up at the start, the same every time
        tone = np.zeros(2 * n)
        for f, tau, weight in zip(self.sd_f, self.sd_tau, (1.0, 0.6)):
            tri, _ = osc.triangle(f * h.detune * bend, sr2, 0.75)
            wave = np.tanh(1.4 * tri) / np.tanh(1.4)
            env = _soft_gate(h.size * np.exp(-t / (tau * h.loose)), 0.08) * _attack(2 * n, sr2, 0.0003)
            tone += weight * wave * env
        y = osc.decimate2(tone)
        # the snappy: noise held 24 ms, then discharged toward a negative voltage, so it stops rather than fades
        tn = np.arange(n) / sr
        held = np.where(tn < 0.024, 1.0, 1.25 * np.exp(-(tn - 0.024) / (self.sd_noise_tau * h.loose)) - 0.25)
        env = _soft_gate(held, 0.0, 0.01) * _attack(n, sr, 0.0005)
        noise = sosfilt(self.sd_noise, _noise(h.rng, n + 256, self.tilt))[256:] / self.sd_noise_rms
        y += _saturate(noise, 2.0) * env * (h.size * self.sd_snappy * (1.0 + 0.3 * h.accent))  # its VCA's ceiling
        return sosfilt(self.hp_out, y)

    def clap(self, h: Hit) -> np.ndarray:
        return TR808.clap(self, h)  # the same circuit, the 909's numbers

    def _tom(self, h: Hit, f: float, t60: float) -> np.ndarray:
        sr, sr2 = self.sr, 2.0 * self.sr
        t60 = t60 * h.loose
        n = int((1.3 * t60 + 0.02) * sr)
        t = np.arange(2 * n) / sr2
        sweep = 0.45 * (1.0 + 0.4 * h.accent)
        tri, _ = osc.triangle(f * h.detune * (1.0 + sweep * np.exp(-t / 0.025)), sr2, 0.75)
        body = np.tanh(1.4 * tri) / np.tanh(1.4) * _attack(2 * n, sr2, 0.0003) * np.exp(-t * LN1000 / t60)
        y = osc.decimate2(body) * h.size
        m = int(0.08 * sr)
        noise = sosfilt(self.tom_noise, _noise(h.rng, m + 256, self.tilt))[256:] / self.tom_noise_rms
        y[:m] += 0.25 * h.size * noise * np.exp(-np.arange(m) / (0.012 * sr)) * _attack(m, sr, 0.0005)
        return sosfilt(self.hp_out, y)

    def tom_hi(self, h):
        return self._tom(h, *self.tom[0])

    def tom_mid(self, h):
        return self._tom(h, *self.tom[1])

    def tom_lo(self, h):
        return self._tom(h, *self.tom[2])

    def rim(self, h: Hit) -> np.ndarray:
        return _rimshot(h, self.rs_f, (0.03, 0.018, 0.012), (1.0, 0.8, 0.5), 2.0 * self.sr, self.rs_hp)

    def _rom(self, h: Hit, kind: str, tau: float | None) -> np.ndarray:
        sr = self.sr
        rom = _cymbal_rom(kind, sr, round(self.clock * (1.0 if kind == "hat" else self.cymbal_tune), 4))
        n = len(rom) if tau is None else min(len(rom), int(9.0 * tau * h.loose * sr))
        env = _attack(n, sr, 0.0002) * h.size
        if tau is not None:
            env *= np.exp(-np.arange(n) / (tau * h.loose * sr))
        env, gone = _cut(env, h.cut, h.cut_tau, sr)
        y = rom[:gone] * env
        return sosfilt(self.hat_tone, y) if kind == "hat" else y

    def hat(self, h):
        return self._rom(h, "hat", self.ch_tau)

    def hat_open(self, h):
        return self._rom(h, "hat", self.oh_tau)

    def hat_pedal(self, h):
        return self._rom(h, "hat", self.pedal_tau)

    def crash(self, h):
        return self._rom(h, "crash", None)

    def ride(self, h):
        return self._rom(h, "ride", None)

    def cowbell(self, h):
        return self.borrowed.cowbell(h)

    def clave(self, h):
        return self.borrowed.clave(h)

    def conga_hi(self, h):
        return self.borrowed.conga_hi(h)

    def conga_mid(self, h):
        return self.borrowed.conga_mid(h)

    def conga_lo(self, h):
        return self.borrowed.conga_lo(h)

    def maracas(self, h):
        return self.borrowed.maracas(h)


# ---------------------------------------------------------------------------------------------- playing


def piece_of(art: str) -> str:
    """The piece a note's articulation names: itself, an alias's, or the closed hat."""
    a = (art or "").strip().lower()
    a = ALIASES.get(a, a)
    return a if a in PIECES else DEFAULT


def _wander(rng: np.random.Generator, cents: float):
    """A part's slow drift in cents: three slow sines, one to a few minutes round."""
    periods = rng.uniform(40.0, 200.0, 3)
    phases = rng.uniform(0.0, 2.0 * np.pi, 3)
    amps = rng.normal(0.0, cents / np.sqrt(3.0), 3)
    return lambda t: float(np.sum(amps * np.sin(2.0 * np.pi * t / periods + phases)))


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict | None = None) -> np.ndarray:
    """A drum machine part: every trigger through its voice, dry, in stereo, `length` samples long."""
    if name not in SPEC:
        raise ValueError(f"no such drum machine: {name}")
    s = {**DEFAULTS, **(settings or {})}
    lofi = s.get("kit") == "lofi"
    if lofi:  # a person's lofi kit: the machine soft and worn (docs/SOUND-DESIGN.md)
        s = {**s, **LOFI}
    wear = float(np.clip(s.get("wear", 0.25), 0.0, 1.0))
    kit = TR808(sr, make, s) if name == "drums-808" else TR909(sr, make, s)
    character(kit, s)
    mix = MIX_808 if name == "drums-808" else MIX_909
    out = np.zeros((length, 2))
    base = int(rng.integers(1 << 62))
    hiss = 10.0 ** ((-58.0 + 18.0 * wear) / 20.0)
    size = 1 << 17
    table = np.random.default_rng([base, 11]).standard_normal(size)
    table = np.concatenate([table, table])  # the machine's hiss, read from anywhere
    events = sorted(((int(round(n.start * sr)), piece_of(n.art), n) for n in notes
                     if 0 <= int(round(n.start * sr)) < length), key=lambda e: (e[0], PIECES.index(e[1])))
    drift = {p: _wander(np.random.default_rng([base, 3, k]), 2.0 + 10.0 * wear) for k, p in enumerate(PIECES)}
    starts = {p: np.array([i for i, q, _ in events if q == p], dtype=np.int64) for p in PIECES}
    for i, piece, note in events:
        code = PIECES.index(piece)
        hr = np.random.default_rng([base, i, code])
        cut, cut_tau = None, RETRIGGER
        for other in CUT_BY.get(piece, ()):  # the next trigger that cuts this one off, if any
            later = starts[other][np.searchsorted(starts[other], i, side="right"):]
            if len(later) and (cut is None or later[0] - i < cut):
                cut = int(later[0]) - i
                cut_tau = CHOKE if (piece == "hat-open" and other != "hat-open") else RETRIGGER
        cents = float(hr.normal(0.0, 1.0 + 6.0 * wear)) + drift[piece](i / sr)
        loose = float(np.exp(hr.normal(0.0, 0.02 + 0.08 * wear)))
        hit = Hit(i, i / sr, float(note.vel), hr, cents, loose, cut, cut_tau)
        y = getattr(kit, piece.replace("-", "_"))(hit)
        y = y * (mix[piece] * 10.0 ** (hr.normal(0.0, 0.1 + 0.4 * wear) / 20.0))
        # every VCA lets a little hiss through while it is open: as much as the voice is loud, 6 ms at a time
        m = len(y)
        noise = table[(start := int(hr.integers(size))): start + m] if m <= size else hr.standard_normal(m)
        blocks = -(-m // 256)
        level = np.zeros(blocks * 256)
        level[:m] = np.abs(y)
        y = y + noise * np.repeat(level.reshape(blocks, 256).max(axis=1), 256)[:m] * hiss
        tail = min(m, int(0.003 * sr))  # every voice ends at rest, however far down it has already fallen
        y[m - tail:] *= 0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, tail))
        # ...and starts from it: a voice whose oscillator or noise is already mid-swing when its VCA opens
        # would step from silence to a third of full scale in one sample; an analog output takes half a
        # millisecond, which keeps the click (a millisecond or two long) and loses the step
        rise = min(m, int(0.0005 * sr))
        y[:rise] *= 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, rise + 1)[1:])  # sounding from the note's sample
        j = min(length, i + len(y))
        theta = (PAN[piece] + 1.0) * np.pi / 4.0
        out[i:j, 0] += y[: j - i] * np.cos(theta) * np.sqrt(2.0)
        out[i:j, 1] += y[: j - i] * np.sin(theta) * np.sqrt(2.0)
    if lofi:  # as a sampler keeps it: the top rolled off, the peaks rounded
        out = sosfilt(_biquad("lp", LOFI_TOP, 0.7071, sr), out, axis=0)
        out = np.tanh(LOFI_DRIVE * out) / LOFI_DRIVE
    return out


# ---------------------------------------------------------------------------------------------- a person's kit
#
# docs/SOUND-DESIGN.md: the lofi kit (the machine soft and worn, then a sampler's top and peaks) and each piece's
# character, moved on the machine once it is made, so its maker's tolerances are drawn as ever.

LOFI = dict(brightness=0.15, body=1.25, wear=0.6)
LOFI_TOP = 6000.0  # Hz
LOFI_DRIVE = 1.5
TUNE = (-12.0, 12.0)  # semitones a piece may be retuned
DECAY = (0.25, 4.0)  # times its decay
SNAPPY = (0.0, 2.0)  # times the snare's snappy
PIECE_KNOBS = {"kick": ("tune", "decay"), "snare": ("tune", "decay", "snappy"), "hat": ("decay",)}


def character(kit, s: dict) -> None:
    """A person's kick, snare and hat (settings "kick", "snare", "hat": {"tune": semitones, "decay": times,
    "snappy": times}) on a machine made: its drums retuned, their decays and the snare's snappy scaled."""
    for piece, knobs in PIECE_KNOBS.items():
        want = s.get(piece)
        if not want:
            continue
        tune = 2.0 ** (float(np.clip(want.get("tune", 0.0), *TUNE)) / 12.0)
        decay = float(np.clip(want.get("decay", 1.0), *DECAY))
        if piece == "kick":
            if isinstance(kit, TR808):
                kit.bd_f0 *= tune
            else:
                kit.bd_f *= tune
            kit.bd_t60 *= decay
        elif piece == "snare":
            kit.sd_f = tuple(f * tune for f in kit.sd_f)
            if isinstance(kit, TR808):
                kit.sd_t60 = tuple(t * decay for t in kit.sd_t60)
                kit.sd_tau *= decay
            else:
                kit.sd_tau = tuple(t * decay for t in kit.sd_tau)
                kit.sd_noise_tau *= decay
            kit.sd_snappy *= float(np.clip(want.get("snappy", 1.0), *SNAPPY))
        else:
            kit.ch_tau *= decay
            kit.oh_tau *= decay
            kit.pedal_tau *= decay
