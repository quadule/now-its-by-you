"""Electric pianos: a tine piano and a reed piano, as struck modes heard through their pickups.

A tine piano has, for each key, a small tuning fork laid on its side: a thin
steel rod (the tine) clamped at one end into a block screwed to a heavier
brass bar (the tonebar) tuned to the same note. A neoprene-tipped hammer
strikes the tine near its clamp. The push starts gently, as the tip's
contact grows, and lets go more slowly than it came; it lasts about 3.6 ms
in the bass to 0.5 ms at the top (harder tips toward the treble) and halves
from a soft blow to a hard one, since rubber stiffens as it is squeezed. Its
spectrum falls 18 dB an octave above the contact's corner, so a hard blow
reaches the upper modes far better than a soft one. The tine rings in the
modes of a cantilever, 1 : 6.27 : 17.55, except that its tuning spring, a
coil of wire wound on it, loads the second mode, pulling it down toward 5.2
times the fundamental in the bass. Struck near the clamp, the tine takes up
its upper modes nearly as well as its fundamental, and since the pickup
hears speed, not swing, they come out louder by their frequency: they are
the bell of a hard blow (at middle C about 21 dB under the fundamental at
velocity 0.3 and 10 dB under at 0.9), and they die in a tenth to a third of
a second. The fundamental rings for a long time because the tonebar swings
against the tine and the pair barely moves the rail it is screwed to; the
two moving together (the fork's other mode) shake the rail and die in a
second or so, which gives the note a quick first drop (about 3 dB) and then
its long sustain: T60 10 s x (262 / f0)^0.8, held within 1.5 to 20 s.

Nothing of that is heard directly: the tine's tip swings past an
electromagnetic pickup, and the voltage is the rate of change of the flux
through its coil. The flux follows the pole's field where the tip is, which
against the tip's sideways position is a bell curve: (1 + u^2)^-3/2, a
magnetic point charge's field, with u in units of the tip's height over
the pole. A technician voices each tine a little off the pole's axis (u0 =
0.35 here). A small swing sees nearly a straight slope and gives a nearly
pure tone; a large one sweeps over the curve's top and gives the second
harmonic and more: the bark. It grows with the swing, so it is a matter of
how hard the key is played, and it fades as the note decays. Each note's
own tine goes through its own pickup (render each tine, voice it, then
sum), at twice the sample rate, since the curve makes harmonics without
end. Then a preamp's soft clip, the amplifier's speakers, and a stereo
tremolo: the two sides' levels swung against each other at 4 to 6 Hz, as
deep as `ornament` asks (0: none; 0.5: each side swings ±43%).

Measured (middle C, 20-220 ms after the blow): the 2nd harmonic 22 dB under
the fundamental at velocity 0.3, 12 under at 0.5, 4 over at 0.9, the 3rd
level with the fundamental at 0.9; a second later the bark has fallen 13 dB.
The spectral centroid of a note's first 0.3 s at E4 rises from 330 Hz at
velocity 0.3 to 640 Hz at 0.9 (0.96 octave). In tune within 0.4 cent.

A reed piano's keys strike steel reeds with felt hammers. Each reed is one
plate of a capacitor: it swings in a slot cut in a charged plate, and the
current it drives into the preamp follows the change of a capacitance that
goes as 1 / (d - x), where d is the gap and x the reed's excursion toward
it. That curve is lopsided, so a reed piano's tone has strong odd and even
harmonics together and a nasal bark when played hard: at middle C the 2nd
harmonic is 17 dB under the fundamental at velocity 0.3 and 4 dB under at
0.9, the 3rd 35 and 10 dB under, the 4th 16 dB under at 0.9. A reed rings
for 4 s at C3 and 1 s at C6 (a lump of solder on its tip tunes it, and puts
its second mode at four to five times the fundamental). Its amplifier has a
tremolo, its level swung at 5.5 to 6.5 Hz, as deep as `ornament` asks (0.5:
dipping 35%).

Both have felt dampers: when a key rises the note stops in a tenth to a
fifth of a second. Articulations: "" a key played and released; "ped" with
the sustain pedal, which holds every damper off, so the note's written
length includes the pedal's hold (the part writer lengthens the note; a key
struck again while it rings stops the old note and starts anew).

brightness is the hammer tips and the pickups' voicing: soft tips, and tines
set back from their pickups and further off the poles' axes (0: round, a
little bell, less bark), to hard tips and tines close to their pickups,
nearer the axes (1). wear pulls single keys off pitch, the tonebars off
their tines, voices keys unevenly and lets the dampers leak. make gives
each machine its own instrument: every key's tuning, voicing and level, its
tonebars and the tremolo's rate. A three-minute comping part costs about 2 s.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy.signal import butter, sosfilt

from . import modal, osc

SPEC = {
    "epiano": dict(
        family="keys",
        role="comping",
        register=(28, 100),
        place=(0.05, 0.9),
        level=0.118,
        poly=True,
        articulations={
            "": "a key played and released: the damper falls at the end of the note",
            "ped": "with the sustain pedal held: the note rings for its whole written length (which includes the "
                   "pedal's hold), then the damper falls",
        },
        about="a tine piano: steel tines and tonebars struck by neoprene-tipped hammers, electromagnetic pickups "
              "that bark when played hard, a soft-clipping preamp and a stereo tremolo as deep as ornament asks",
        brighter=0.95,
        dynamic=True,
    ),
    "epiano-reed": dict(
        family="keys",
        role="comping",
        register=(33, 96),
        place=(-0.12, 0.0),
        level=0.146,
        poly=True,
        articulations={
            "": "a key played and released: the damper falls at the end of the note",
            "ped": "with the sustain pedal held: the note rings for its whole written length, then the damper falls",
        },
        about="a reed piano: steel reeds struck by felt hammers, an electrostatic pickup that makes a nasal bark "
              "when played hard, and an amplifier's tremolo as deep as ornament asks",
        brighter=0.5,
        dynamic=True,
    ),
}

DEFAULTS = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0)
OVERSAMPLE = 2  # the pickups' curves make harmonics without end: tines and reeds are rendered at twice the rate


def _settings(settings: dict) -> tuple[float, float, float, float]:
    s = {**DEFAULTS, **(settings or {})}
    return (float(np.clip(s["brightness"], 0.0, 1.0)), float(np.clip(s["wear"], 0.0, 1.0)),
            float(np.clip(s["ornament"], 0.0, 1.0)), float(np.clip(s["body"], 0.7, 1.35)))


def _interp(m: float, table) -> float:
    xs, ys = zip(*table)
    return float(np.interp(m, xs, ys))


def _log_interp(m: float, table) -> float:
    xs, ys = zip(*table)
    return float(np.exp(np.interp(m, xs, np.log(ys))))


def _hz(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69.0) / 12.0)


def _fold(m: float, lo: float, hi: float) -> float:
    """A pitch outside the keyboard played an octave (or more) in, where the keys are."""
    while m < lo - 0.5:
        m += 12.0
    while m > hi + 0.5:
        m -= 12.0
    return m


def _pulse(tau: float, sr: float) -> np.ndarray:
    """A hammer's push, unit peak, about as long as a half sine of `tau` seconds: it starts gently, as
    the tip's contact area grows from nothing, and lets go more slowly than it came (rubber and felt give
    back less than they took). Its shape, (t/θ)^2 e^(2 - t/θ) with θ = 0.22 tau, has a spectrum without
    dips, falling 18 dB an octave above 1 / (2π θ): a shorter push reaches the upper modes far better."""
    theta = 0.22 * tau
    n = max(4, int(np.ceil(10.0 * theta * sr)))
    t = (np.arange(n) + 0.5) / (theta * sr)
    push = t**2 * np.exp(2.0 - t)
    fade = min(n, max(2, int(2.0 * theta * sr)))
    push[n - fade:] *= 0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, fade))
    return push


def _reach(force: np.ndarray, freqs, sr: float) -> np.ndarray:
    """How strongly a push reaches each frequency: the magnitude of its spectrum there."""
    t = np.arange(len(force)) / sr
    return np.abs((force[None, :] * np.exp(-2j * np.pi * np.asarray(freqs)[:, None] * t[None, :])).sum(axis=1))


@njit(cache=True)
def _magnetic(x, u0, scale, out, start):
    """A tine's tip, x (in units of its height over the pole), swinging past an electromagnetic pickup voiced
    u0 off its axis: the flux through the coil goes as the pole's field there, (1 + u^2)^-3/2; its change
    from sample to sample, times scale, is added to out."""
    q = 1.0 + u0 * u0
    prev = 1.0 / (q * np.sqrt(q))
    end = min(x.shape[0], out.shape[0] - start)
    for i in range(end):
        u = u0 + x[i]
        q = 1.0 + u * u
        phi = 1.0 / (q * np.sqrt(q))
        out[start + i] += scale * (phi - prev)
        prev = phi


@njit(cache=True)
def _electrostatic(x, limit, scale, out, start):
    """A reed's tip, x (fractions of the gap to the charged plate), swinging in its slot: the capacitance
    goes as 1 / (1 - x); its change from sample to sample, times scale, is added to out. The reed never
    touches the plate: past 0.8 of the gap its approach is eased toward `limit`."""
    prev = 1.0
    knee = 0.8
    room = limit - knee
    end = min(x.shape[0], out.shape[0] - start)
    for i in range(end):
        xi = x[i]
        if xi > knee:
            xi = knee + room * np.tanh((xi - knee) / room)
        c = 1.0 / (1.0 - xi)
        out[start + i] += scale * (c - prev)
        prev = c


def _restrikes(notes) -> tuple[list, list]:
    """The notes in time order, and for each the time after its start when its key is struck again (None if not)."""
    ordered = sorted(notes, key=lambda n: (n.start, n.pitch))
    next_strike: dict[int, float] = {}
    until = [None] * len(ordered)
    for i in range(len(ordered) - 1, -1, -1):
        key = int(round(ordered[i].pitch))
        if key in next_strike:
            until[i] = next_strike[key] - ordered[i].start
        next_strike[key] = ordered[i].start
    return ordered, until


def _soft_clip(x: np.ndarray, ceiling: float) -> np.ndarray:
    """A preamp running out of headroom: linear while small, rounding off toward `ceiling`."""
    return ceiling * np.tanh(x / ceiling)


# --- the tine piano ---------------------------------------------------------------------------------

TINE_LOW, TINE_HIGH = 28, 100  # E1 to E7: a 73-key stage piano
U0 = 0.35  # the pickups' voicing: the tine's rest off the pole's axis, in units of its height over the pole
TINE_GAMMA = 2.0  # the tine's swing grows as vel^2: its bark, 12 dB under at 0.5, level at 0.9
TINE_SWING = 0.27  # the swing (heights over the pole) at velocity 0.5 at middle C
# The hammer's contact (s) at velocity 0.5: soft and long in the bass, harder tips toward the treble;
# it shortens as the blow gets harder, halving from velocity 0.3 to 0.9 or so.
CONTACT_TABLE = ((28, 3.6e-3), (48, 2.2e-3), (60, 1.6e-3), (72, 1.1e-3), (88, 0.6e-3), (100, 0.45e-3))
# The upper modes' strength at the tip against the fundamental's, per unit push (a strike near the clamp
# reaches them nearly as well as the fundamental), and their T60 (s).
BELL_TABLE = ((28, 0.45), (48, 0.7), (60, 0.95), (76, 1.0), (100, 1.0))
BELL_T60_TABLE = ((28, 0.35), (60, 0.3), (84, 0.18), (100, 0.12))


def contact(m: float, vel: float) -> float:
    """The tine hammer's contact (s) for key m struck at velocity vel (brightness 0.5)."""
    return _log_interp(m, CONTACT_TABLE) * 2.0 ** (-1.6 * (vel - 0.5))


def tine_ratios(m: float) -> tuple[float, float]:
    """The tine's second and third modes against its fundamental: a cantilever's 6.27 and 17.55, pulled
    down toward 5.2 and 14 in the bass by the tuning spring's weight partway along it."""
    bass = float(np.clip((72.0 - m) / 36.0, 0.0, 1.0))
    return 6.267 - 1.067 * bass, 17.55 - 3.55 * bass


def tine_t60(f0: float) -> float:
    """T60 (s) of a tine's fundamental, the tonebar holding it: 10 s at middle C, 10 (262 / f0)^0.8, 1.5..20 s."""
    return float(np.clip(10.0 * (262.0 / f0) ** 0.8, 1.5, 20.0))


class TinePiano:
    """One machine's tine piano: every key's tuning, tonebar, voicing and level (from `make`)."""

    def __init__(self, sr: int, make: np.random.Generator, settings: dict):
        self.sr = sr
        self.brightness, self.wear, self.ornament, self.size = _settings(settings)
        wear = self.wear
        self.cents = make.normal(0.0, 0.3 + 4.0 * wear, 128)  # each tine a little off
        self.tonebar = make.normal(0.0, 1.0 + 6.0 * wear, 128)  # each tonebar a little off its tine (cents)
        self.voicing = np.exp(make.normal(0.0, 0.05 + 0.3 * wear, 128))  # each tine's rest against its pickup
        self.level = np.exp(make.normal(0.0, 0.06 + 0.12 * wear, 128))  # each key's loudness, voiced by ear
        self.hardness = np.exp(make.normal(0.0, 0.06 + 0.1 * wear, 128))  # each hammer tip's wear
        self.spring = np.exp(make.normal(0.0, 0.015, 128))  # where each tuning spring sits: the 2nd mode moves
        self.side = np.where(make.random(128) < 0.5, -1.0, 1.0)  # which side of its pickup's axis each tine rests
        self.rate = 4.0 + 2.0 * make.uniform()  # the tremolo's rate knob, 4..6 Hz
        self.u0 = U0 * (1.3 - 0.6 * self.brightness)  # toward the axis: more even harmonics, more bark
        self.reach = 0.8 + 0.4 * self.brightness  # pickups set closer: a bigger swing in pole widths

    def note(self, note, sr2: float, rng: np.random.Generator, until: float | None):
        """One struck key: the hammer's push and the tine's modes, when its damper lands, and its pickup."""
        m = _fold(float(note.pitch), TINE_LOW, TINE_HIGH)
        key = int(round(m))
        vel = float(np.clip(note.vel, 0.0, 1.0))
        f0 = _hz(m + self.cents[key] / 100.0)
        # the hammer: a harder blow is a shorter contact (neoprene stiffens as it is squeezed)
        tau = (contact(m, vel) * (1.25 - 0.5 * self.brightness) / self.hardness[key]
               * np.exp(rng.normal(0.0, 0.04)))
        force = _pulse(tau, sr2)
        # the tine's swing at its tip, in pole widths
        register = float(np.clip(2.0 ** ((60.0 - m) / 48.0), 0.6, 1.5))  # the long bass tines swing wider
        swing = TINE_SWING * (max(vel, 0.02) / 0.5) ** TINE_GAMMA * register * self.reach
        swing *= np.exp(rng.normal(0.0, 0.03))
        # the modes: the fork's slow mode (tine against tonebar), its quick one (moving together, shaking the
        # rail), and the tine's own upper modes
        r2, r3 = tine_ratios(m)
        r2 *= self.spring[key]
        t60 = tine_t60(f0) * (1.0 - 0.2 * self.wear)
        quick = float(np.clip(0.12 * t60, 0.4, 1.5))
        bell = _interp(m, BELL_TABLE)
        bell_t60 = _interp(m, BELL_T60_TABLE)
        freqs = np.array([f0, f0 * 2.0 ** (self.tonebar[key] / 1200.0), f0 * r2, f0 * r3])
        rel = np.array([1.0, 0.35, bell * 0.8, bell * 0.6])
        t60s = np.array([t60, quick, bell_t60, 0.5 * bell_t60])
        reach = _reach(force, freqs, sr2)
        gains = -1j * swing * rel / reach[0]  # a tine starts from rest: each mode a sine
        # the damper: felt from below, a tenth to a fifth of a second; a worn one leaks
        end = note.dur if until is None else min(note.dur, until)
        damped = np.array([0.15, 0.15, 0.08, 0.05]) * (1.0 + 1.5 * self.wear)
        if until is not None and until < note.dur:
            damped = np.minimum(damped, 0.05)  # struck again: the new blow takes over
        damped = np.minimum(damped, t60s)
        damp_at = int(round(end * sr2))
        u0 = self.u0 * self.voicing[key] * self.side[key]
        slope = 3.0 * abs(u0) / (1.0 + u0 * u0) ** 2.5
        scale = self.level[key] / register**0.5 / (2.0 * np.sin(np.pi * f0 / sr2) * slope)
        return force, freqs, gains, t60s, damped, damp_at, end, u0, scale, swing

    def render(self, notes, length: int, rng: np.random.Generator) -> np.ndarray:
        """Every note's tine through its own pickup, summed at twice the rate and brought down: mono, the preamp's input."""
        sr = self.sr
        sr2 = float(sr * OVERSAMPLE)
        length2 = length * OVERSAMPLE
        out = np.zeros(length2)
        ordered, until = _restrikes(notes)
        one = np.ones(1)
        for i, note in enumerate(ordered):
            start = int(round(note.start * sr2))
            if start >= length2 or note.dur <= 0.0:
                continue
            force, freqs, gains, t60s, damped, damp_at, end, u0, scale, swing = self.note(note, sr2, rng, until[i])
            n = min(length2 - start, int((end + 0.45) * sr2))
            tine = np.zeros((1, n))
            modal.ring(tine, 0, force, freqs, np.ascontiguousarray(gains.real), np.ascontiguousarray(gains.imag),
                       t60s, damped, damp_at, float(0.01 * sr2), one, sr2, swing * 1e-5)
            _magnetic(tine[0], u0, scale, out, start)
        return out


# --- the reed piano ---------------------------------------------------------------------------------

REED_LOW, REED_HIGH = 33, 96  # A1 to C7: 64 keys
REED_GAMMA = 1.3  # the reed's swing grows as vel^1.3
REED_SWING = 0.42  # its swing (fractions of the gap) at velocity 0.5
REED_CONTACT = ((33, 3.2e-3), (48, 2.4e-3), (60, 1.9e-3), (72, 1.5e-3), (96, 1.0e-3))


def reed_t60(f0: float) -> float:
    """T60 (s) of a reed's fundamental: 4 s at C3 falling to 1 s at C6, held within 0.7..6 s."""
    return float(np.clip(4.0 * (130.81 / f0) ** (2.0 / 3.0), 0.7, 6.0))


class ReedPiano:
    """One machine's reed piano: every reed's tuning (its solder), its level, and the tremolo's rate."""

    def __init__(self, sr: int, make: np.random.Generator, settings: dict):
        self.sr = sr
        self.brightness, self.wear, self.ornament, self.size = _settings(settings)
        wear = self.wear
        self.cents = make.normal(0.0, 0.3 + 4.0 * wear, 128)
        self.gap = np.exp(make.normal(0.0, 0.08 + 0.25 * wear, 128))  # each reed's rest in its slot
        self.level = np.exp(make.normal(0.0, 0.06 + 0.12 * wear, 128))
        self.hardness = np.exp(make.normal(0.0, 0.06 + 0.1 * wear, 128))
        self.solder = make.uniform(-1.0, 1.0, 128)  # how much solder: moves the second mode a little
        self.rate = 5.5 + make.uniform()  # the tremolo's rate, 5.5..6.5 Hz
        self.reach = 0.8 + 0.4 * self.brightness

    def note(self, note, sr2: float, rng: np.random.Generator, until: float | None):
        m = _fold(float(note.pitch), REED_LOW, REED_HIGH)
        key = int(round(m))
        vel = float(np.clip(note.vel, 0.0, 1.0))
        f0 = _hz(m + self.cents[key] / 100.0)
        tau = (_log_interp(m, REED_CONTACT) * (1.4 - 0.6 * vel) * (1.25 - 0.5 * self.brightness)
               / self.hardness[key] * np.exp(rng.normal(0.0, 0.04)))
        force = _pulse(tau, sr2)
        swing = REED_SWING * (max(vel, 0.02) / 0.5) ** REED_GAMMA * self.reach * self.gap[key]
        swing = min(swing, 0.95) * np.exp(rng.normal(0.0, 0.03))
        r2 = 4.5 + 0.35 * self.solder[key]
        t60 = reed_t60(f0) * (1.0 - 0.15 * self.wear)
        freqs = np.array([f0, f0 * r2, f0 * (12.6 + 0.8 * self.solder[key])])
        rel = np.array([1.0, 0.3, 0.12])
        t60s = np.array([t60, float(np.clip(0.15 * (262.0 / f0) ** 0.3, 0.05, 0.3)), 0.05])
        reach = _reach(force, freqs, sr2)
        gains = -1j * swing * rel / reach[0]
        end = note.dur if until is None else min(note.dur, until)
        damped = np.array([0.12, 0.06, 0.04]) * (1.0 + 1.5 * self.wear)
        if until is not None and until < note.dur:
            damped = np.minimum(damped, 0.05)
        damped = np.minimum(damped, t60s)
        damp_at = int(round(end * sr2))
        scale = self.level[key] / (2.0 * np.sin(np.pi * f0 / sr2))
        return force, freqs, gains, t60s, damped, damp_at, end, scale, swing

    def render(self, notes, length: int, rng: np.random.Generator) -> np.ndarray:
        sr2 = float(self.sr * OVERSAMPLE)
        length2 = length * OVERSAMPLE
        out = np.zeros(length2)
        ordered, until = _restrikes(notes)
        one = np.ones(1)
        for i, note in enumerate(ordered):
            start = int(round(note.start * sr2))
            if start >= length2 or note.dur <= 0.0:
                continue
            force, freqs, gains, t60s, damped, damp_at, end, scale, swing = self.note(note, sr2, rng, until[i])
            n = min(length2 - start, int((end + 0.4) * sr2))
            reed = np.zeros((1, n))
            modal.ring(reed, 0, force, freqs, np.ascontiguousarray(gains.real), np.ascontiguousarray(gains.imag),
                       t60s, damped, damp_at, float(0.01 * sr2), one, sr2, swing * 1e-5)
            _electrostatic(reed[0], 0.97, scale, out, start)
        return out


# --- the amplifiers ------------------------------------------------------------------------------------


def _tremolo_wave(n: int, sr: int, rate: float, phase: float) -> np.ndarray:
    return np.sin(2.0 * np.pi * rate * np.arange(n) / sr + phase)


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """An electric piano part, dry, `length` samples, before placement and level: the tine piano stereo
    (its tremolo pans), the reed piano mono."""
    if name not in SPEC:
        raise ValueError(f"no such instrument: {name}")
    settings = settings or {}
    if name == "epiano":
        piano = TinePiano(sr, make, settings)
        ceiling = 2.5
    else:
        piano = ReedPiano(sr, make, settings)
        ceiling = 2.2
    phase = rng.uniform(0.0, 2.0 * np.pi)  # where the tremolo's oscillator happens to be when the part starts
    y2 = piano.render(notes, length, rng)
    # the preamp, at twice the rate so its rounding doesn't fold back
    y = osc.decimate2(_soft_clip(y2, ceiling))[:length]
    if len(y) < length:
        y = np.concatenate([y, np.zeros(length - len(y))])
    # the amplifier's speakers: nothing much under 60 Hz, a gentle fall above 7-9 kHz (a bigger cabinet lower)
    top = (9000.0 if name == "epiano" else 7000.0) / piano.size
    y = sosfilt(butter(2, [55.0 / piano.size, min(top, 0.45 * sr)], btype="bandpass", fs=sr, output="sos"), y)
    wave = _tremolo_wave(length, sr, piano.rate, phase)
    if name == "epiano":
        depth = 0.85 * piano.ornament
        return np.stack([y * (1.0 + depth * wave), y * (1.0 - depth * wave)], axis=1)
    depth = 0.7 * piano.ornament
    return y * (1.0 - depth * 0.5 * (1.0 - wave))
