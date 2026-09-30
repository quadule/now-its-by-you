"""Piano: felt hammers, stiff strings in unisons, dampers, a pedal and a soundboard.

A piano note starts with a felt hammer thrown at two or three strings. The
felt is a nonlinear spring, F = K δ^p: the harder it is squeezed the
stiffer it gets, so a hard blow is not only louder, its push peaks more
sharply and reaches higher partials. The hammer is simulated while it
touches the string (a millisecond or less at the top, three to five in the
bass) as a mass on that spring against the string's impedance, with the
waves it launches coming back from the agraffe and the bridge, which is
what throws the hammer off in the treble. With p from 3.2 in the bass to 4
at the top (measured hammers run from about 2.2 to 3.5 and more), a C4's
contact lasts 3 ms at pp and 2 at ff (measured, about 4 and 2) and its
force at 3-4 kHz rises some 45 dB between them. The force drives the
string's modes, weighted by where it struck: about an eighth of the way
along, which all but silences the eighth partial.

The strings are stiff, so their partials are stretched, f_n = n f1
sqrt((1 + B n^2) / (1 + B)), B from about 0.0002 in the tenor to 0.01 and
more at the top (higher in a small piano's short bass), and the tuner
stretches the octaves to match: C7 some 8 cents sharp, A0 7 flat. Each
partial of a note is two or three strings a fraction of a cent apart,
coupled through the bridge they share (Weinreich 1977): moving together
they push the bridge and lose their energy fast (the prompt sound), moving
against each other they barely move it and ring on (the aftersound). The
hammer excites mostly the first; the unisons' small mistuning and the felt's
unevenness feed the second. That is the piano's double decay and its slow
beating, from the eigenmodes of the coupled strings (three complex modes a
partial) rather than two decays stacked by hand; each string's plane along
the soundboard adds a quieter, slower one, which a single bass string needs.
A C4 falls about 8 dB a second at first and 4 later. Partials decay faster
the higher they sit, 7 s at 262 Hz and under a second above 3 kHz. Una corda
shifts the hammer so it misses one string: softer, rounder, longer.

When a key rises, its damper lands and the strings stop within a few tenths
of a second (the bass's heavy strings take longer); the top notes have no
dampers. The sustain pedal (art "ped") holds the dampers off for the note's
whole written length and lets the open strings that share its partials
answer, building up over a few tenths of a second: a halo. Every string
drives the soundboard, a modal body like the others' (body.py) that radiates
poorly below its lowest modes, and the key and hammer knock on the frame as
they land, most audibly at the top. The stereo image is a player's: the bass
to the left, the treble to the right.

brightness is the hammers' voicing: soft, needled felt (0) to hard,
lacquered (1); at the low end the hammers are wrapped in a strip of felt, as
upright players do for quiet practice, which passes only the slow push: a
dark, close "felt piano". wear widens the unisons, pulls single keys off
pitch, hardens the hammers (compacted felt) and lets the dampers leak. body
is the piano's size: 0.8 a small upright (a shorter, much more inharmonic
bass), 1.25 a small grand. make gives each machine its own piano: the
unisons, the hammers' unevenness and voicing, the soundboard's modes.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy.signal import sosfilt

from . import body, modal, oa
from .iir import butter

SPEC = {
    "piano": dict(
        family="keys",
        role="comping",
        register=(21, 108),
        place=(-0.08, 0.8),
        level=0.51,
        poly=True,
        brighter=0.12,  # the centroid, held down by the strong low partials; above 3 kHz a C4 gains 45 dB pp to ff
        articulations={
            "": "a key played and released: the damper falls at the end of the note",
            "ped": "with the sustain pedal: the note rings for its whole length and the open strings answer",
            "soft": "una corda: the hammer strikes two strings of three; softer, rounder, a longer tail",
            "ped+soft": "both pedals",
        },
        about="an acoustic piano, from a small upright to a small grand (the body setting), felt hammers, "
              "strings in unisons, dampers and a sustain pedal; brightness low is a felt-muted piano",
    ),
}

# --- how the instrument is scaled across its compass ------------------------------------

LOW, HIGH = 21, 108  # A0 to C8


def _interp(m, table):
    xs, ys = zip(*table)
    return float(np.interp(m, xs, ys))


def _log_interp(m, table):
    xs, ys = zip(*table)
    return float(np.exp(np.interp(m, xs, np.log(ys))))


# Inharmonicity B of a small grand (Young 1952; Conklin 1996; Fletcher and Rossing ch. 12): lowest near the
# break from wound to plain strings, rising steeply to the top and again in the short wound bass.
B_TABLE = ((21, 4.0e-4), (28, 2.6e-4), (36, 1.8e-4), (45, 1.8e-4), (52, 2.6e-4), (60, 4.0e-4), (72, 1.0e-3),
           (84, 2.8e-3), (96, 8.0e-3), (108, 2.0e-2))
# Hammer mass per string (kg), felt stiffness K (N/m^p) and exponent p. The masses are Chaigne and
# Askenfelt's (1994: C2, C4, C7). Their exponents (2.3 to 3) leave the felt stiff even when barely
# squeezed, so the strings' impedance sets the contact and a harder blow hardly brightens it; measured
# hammers run from about 2.2 to 3.5 and more (Hall and Askenfelt 1988), and one more than theirs, with
# the felt as stiff as a fifth of theirs at 0.3 mm, behaves as a piano does: at C4 the contact is 3.3 ms
# at pp and 2.1 at ff (measured about 4 to 2, Askenfelt and Jansson 1990) and the pulse's peak sharpens
# with the blow, so the force at 2 kHz rises about 28 dB from pp to ff and at 4 kHz about 60.
MASS_TABLE = ((21, 6.5e-3), (36, 4.9e-3), (60, 2.97e-3), (96, 2.2e-3), (108, 2.0e-3))
K_TABLE = ((21, 1.0e11), (36, 2.67e11), (60, 3.0e12), (84, 3.0e13), (96, 1.15e14), (108, 3.5e14))
P_TABLE = ((21, 3.2), (36, 3.3), (60, 3.5), (84, 3.5), (96, 3.5), (108, 3.6))
# One string's wave impedance sqrt(T mu), kg/s: heavy wound strings in the bass, about 2 above.
Z_TABLE = ((21, 12.0), (36, 4.6), (48, 2.6), (60, 2.06), (96, 1.95), (108, 1.9))
# Where the hammer strikes, as a fraction of the speaking length.
STRIKE_TABLE = ((21, 0.118), (60, 0.122), (84, 0.1), (96, 0.075), (108, 0.058))
# T60 with the damper down, of the fundamental (s).
DAMPED_TABLE = ((21, 1.4), (36, 0.8), (48, 0.4), (60, 0.25), (72, 0.18), (84, 0.15), (89, 0.15))


def prompt_t60(freq):
    """T60 (s) of the prompt sound at a frequency, the same for a fundamental and for any key's partial there:
    7 s at 262 Hz, falling as f^-0.9 above (C5 3.8 s, C6 2.0, C7 1.1, C8 0.6: measured decay rates of
    about 16, 30, 55 and 100 dB/s) and as f^-0.55 below (C2 15 s, A0 24 s); a C4's partials above 3 kHz
    are gone in under a second (Martin 1947; Hundley, Benioff and Martin 1978). The aftersound rings
    longer (after_ratio)."""
    freq = np.asarray(freq, dtype=np.float64)
    return 7.0 * np.where(freq > 262.0, (262.0 / freq) ** 0.9, (262.0 / np.maximum(freq, 1.0)) ** 0.55)


def after_ratio(freq):
    """The aftersound's T60 against the prompt sound's at a frequency: about 2.6 at C4's fundamental,
    falling toward 1.15 above 2 kHz. Up there a unison's fraction of a cent is more hertz than the
    bridge couples, the strings ring each on its own, and each must still die as fast as a real
    piano's upper partials do: the double decay is a thing of the lower partials."""
    freq = np.asarray(freq, dtype=np.float64)
    return 1.15 + 1.85 / (1.0 + (freq / 500.0) ** 2)


HALO = 10.0 ** (-21.0 / 20.0)  # an open string's answer to a partial it shares, against that partial
CREST = 6.0  # the most a string's swing under the hammer may exceed its ring's RMS (the tenor's is 3 to 6)
HORIZONTAL = (10.0 ** (-18.0 / 20.0), 12)  # the plane along the soundboard: its level against the vertical, up to this partial
UNDAMPED = 90  # F#6 and above have no dampers
# the key's and hammer's knock on the frame: its RMS against the tone's at the attack (at vel 0.5)
KNOCK_TABLE = ((21, 0.05), (60, 0.08), (84, 0.16), (108, 0.35))


def strings_for(m: int) -> int:
    """Strings in the unison: single wound strings at the very bottom, pairs in the bass, then threes."""
    return 1 if m < 30 else 2 if m < 42 else 3


def _partial_cents(n: int, b: float) -> float:
    """How far a stiff string's nth partial sits above n times its fundamental, in cents."""
    return 600.0 * np.log2((1.0 + b * n * n) / (1.0 + b))


def stretch_cents(m: float, inharmonicity=None) -> float:
    """How far the tuner stretches a key from equal temperament, from the piano's own inharmonicity:
    nothing from C3 to C6; above, each octave tuned beatless to the stretched second partial of the
    one below (2:1); below, each tuned so its fourth partial meets the second of the octave above
    (4:2). Railsback's curve falls out: C7 about +12 cents, C8 about +38, A0 some -7 (more on a
    small piano's stiffer bass)."""
    b = inharmonicity or (lambda k: _log_interp(k, B_TABLE))
    cents = 0.0
    if m > 84:
        k = 84.0
        while k < m:
            step = min(12.0, m - k)
            cents += step / 12.0 * _partial_cents(2, b(k))
            k += step
    elif m < 48:
        k = 48.0
        while k > m:
            step = min(12.0, k - m)
            cents += step / 12.0 * (_partial_cents(2, b(k)) - _partial_cents(4, b(k - step)))
            k -= step
    return cents


MAX_PARTIAL_HZ = 12000.0
HAMMER_RATE = 4  # the contact is simulated at four times the sample rate


@njit(cache=True, nogil=True)
def hammer_force(v0, mass, stiff, power, z, delay_left, delay_right, loss, fs, max_t):
    """The force (N) a felt hammer arriving at v0 m/s puts on a string, one value per sample at fs.

    The string at the strike point is an ideal string seen from both sides
    (impedance 2z): whatever the force launches travels to the agraffe
    (delay_left, round trip, samples) and to the bridge (delay_right),
    comes back inverted (the bridge a little lossy) and moves the string
    under the felt. The felt pushes as stiff * compression**power while
    they touch."""
    n = int(max_t * fs)
    force = np.zeros(n)
    size = 1
    while size < int(delay_left + delay_right) + 8:
        size *= 2
    out_left = np.zeros(size)
    out_right = np.zeros(size)
    eta = 0.0  # the hammer's position (m), toward the string
    u = v0  # its velocity
    y = 0.0  # the string under the felt
    left_contact = 0
    touched = False
    for t in range(n):
        x = t - delay_left
        i = int(np.floor(x))
        f = x - i
        a = out_left[i % size] if i >= 0 else 0.0
        b = out_left[(i + 1) % size] if i + 1 >= 0 else 0.0
        in_left = -((1.0 - f) * a + f * b) if x >= 0 else 0.0
        x = t - delay_right
        i = int(np.floor(x))
        f = x - i
        a = out_right[i % size] if i >= 0 else 0.0
        b = out_right[(i + 1) % size] if i + 1 >= 0 else 0.0
        in_right = -loss * ((1.0 - f) * a + f * b) if x >= 0 else 0.0
        # the felt's push and the string's give are solved together (the push moves the string under
        # it at once, through its impedance): F = K (d0 - c F)^p, which stays stable however stiff the felt
        eta_next = eta + u / fs
        c = 1.0 / (2.0 * z * fs)
        d0 = eta_next - (y + (in_left + in_right) / fs)
        push = 0.0
        if d0 > 0.0:
            hi = d0 / c
            push = min(stiff * d0**power, hi)
            lo = 0.0
            for _ in range(40):
                d = d0 - c * push
                g = push - stiff * d**power if d > 0.0 else push
                if g > 0.0:
                    hi = push
                else:
                    lo = push
                slope = 1.0 + stiff * power * c * d ** (power - 1.0) if d > 0.0 else 1.0
                step = push - g / slope
                if step <= lo or step >= hi:
                    step = 0.5 * (lo + hi)
                if abs(step - push) <= 1e-12 * max(push, 1e-9):
                    push = step
                    break
                push = step
        if push > 0.0:
            touched = True
            left_contact = 0
        elif touched:
            left_contact += 1
        half = push / (2.0 * z)
        v_string = in_left + in_right + half
        out_left[t % size] = in_right + half
        out_right[t % size] = in_left + half
        y += v_string / fs
        u -= push / mass / fs
        eta = eta_next
        force[t] = push
        if touched and left_contact > int(0.004 * fs) and u < 0.0:
            return force[:t + 1]
    return force


@njit(cache=True, nogil=True)
def _spectrum(force, freqs, sr):
    """The force's Fourier sum at each mode's frequency, sum_t F[t] exp(-i 2 pi f t / sr)."""
    out = np.zeros(freqs.shape[0], dtype=np.complex128)
    for k in range(freqs.shape[0]):
        w = 2.0 * np.pi * freqs[k] / sr
        step_r, step_i = np.cos(w), -np.sin(w)
        pr, pi = 1.0, 0.0
        acc_r, acc_i = 0.0, 0.0
        for t in range(force.shape[0]):
            acc_r += force[t] * pr
            acc_i += force[t] * pi
            pr, pi = pr * step_r - pi * step_i, pr * step_i + pi * step_r
        out[k] = acc_r + 1j * acc_i
    return out


class Piano:
    """One machine's piano: its unisons, hammers and soundboard (from `make`), set up by the band settings."""

    def __init__(self, sr: int, make: np.random.Generator, settings: dict):
        self.sr = sr
        self.brightness = float(np.clip(settings.get("brightness", 0.5), 0.0, 1.0))
        self.wear = float(np.clip(settings.get("wear", 0.25), 0.0, 1.0))
        self.size = float(np.clip(settings.get("body", 1.0), 0.7, 1.35))
        keys = HIGH - LOW + 1
        # the tuner's unisons: each string a fraction of a cent from its neighbours, more on an old piano
        spread = 0.35 + 5.0 * self.wear
        self.unison = make.normal(0.0, spread, (keys, 3))
        self.unison -= self.unison.mean(axis=1, keepdims=True)
        self.offset = make.normal(0.0, 0.25 + 3.0 * self.wear, keys)  # each key's pitch, a little off
        # the hammers: felt that meets its strings a little unevenly, and voicing that differs key to key
        self.uneven = 1.0 + make.normal(0.0, 0.05 + 0.15 * self.wear, (keys, 3))
        self.voicing = np.exp(make.normal(0.0, 0.12, keys))
        self.b_scale = float(np.exp(make.normal(0.0, 0.08)))
        self.board = _balanced(body.impulse_response(SOUNDBOARD, sr, seed=int(make.integers(1 << 30)), size=self.size),
                               sr)
        # hardness: soft old felt to hard; the practice strip below 0.3 brightness
        self.hardness = 10.0 ** (2.4 * (self.brightness - 0.5)) * (1.0 + 1.2 * self.wear)
        self.felt_strip = float(np.clip((0.3 - self.brightness) / 0.3, 0.0, 1.0))
        # each string's plane along the soundboard sits a fraction of a cent above the one across it
        self.planes = make.uniform(0.2, 0.5, keys)
        # every key's fundamental, stretched as a tuner would for this piano's own inharmonicity
        self.fundamental = np.array([
            440.0 * 2.0 ** ((m - 69.0 + (stretch_cents(m, self.inharmonicity) + self.offset[m - LOW]) / 100.0) / 12.0)
            for m in range(LOW, HIGH + 1)])

    def key(self, m: int) -> int:
        return int(np.clip(m, LOW, HIGH)) - LOW

    def inharmonicity(self, m: float) -> float:
        bass = float(np.clip((60.0 - m) / 24.0, 0.0, 1.0))
        return _log_interp(m, B_TABLE) * self.b_scale * self.size ** (-2.5 * bass)

    def partial(self, m: int, n) -> np.ndarray:
        """Frequencies of key m's partials n (Hz)."""
        b = self.inharmonicity(m)
        n = np.asarray(n, dtype=np.float64)
        return n * self.fundamental[self.key(m)] * np.sqrt((1.0 + b * n * n) / (1.0 + b))


SOUNDBOARD = body.Body(  # a piano's soundboard: low, broad modes, then a dense even scatter; a quiet top
    modes=((58.0, 10.0, 1.0), (92.0, 12.0, 3.0), (128.0, 14.0, 3.5), (178.0, 16.0, 3.0), (236.0, 18.0, 2.5),
           (310.0, 18.0, 2.0), (420.0, 20.0, 1.5)),
    dense=(450.0, 9000.0, 120), tilt=-1.2, q=(24.0, 14.0), direct=0.35, lowcut=55.0, highcut=9500.0,
    length=0.5,
)


def _balanced(ir: np.ndarray, sr: int) -> np.ndarray:
    """A two-microphone body response with its channels brought to the same level in each third of an
    octave: they still hear different mixes of the plate's modes (the width), but neither hears a whole
    register louder than the other, which would pull notes across the player's image."""
    n = 1 << int(np.ceil(np.log2(len(ir) * 2)))
    spectra = np.fft.rfft(ir, n, axis=0)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    power = np.abs(spectra) ** 2
    smooth = np.empty_like(power)
    for ch in range(ir.shape[1]):
        cum = np.concatenate([[0.0], np.cumsum(power[:, ch])])
        lo = np.searchsorted(freqs, freqs * 2 ** (-1 / 6))
        hi = np.maximum(np.searchsorted(freqs, freqs * 2 ** (1 / 6), side="right"), lo + 1)
        smooth[:, ch] = (cum[hi] - cum[lo]) / (hi - lo)
    target = smooth.mean(axis=1, keepdims=True)
    out = np.fft.irfft(spectra * np.sqrt(target / np.maximum(smooth, 1e-30)), n, axis=0)[: len(ir)]
    fade = np.ones(len(ir))
    tail = len(ir) // 20
    fade[-tail:] = np.linspace(1.0, 0.0, tail)
    return out * fade[:, None]


def _loudness(vel: float) -> float:
    """Bridge-force RMS at the attack for a blow of velocity vel: about 17 dB from 0.3 to 1."""
    return 0.12 * max(vel, 0.02) ** 1.6


def _note(piano: Piano, note, sr: int, rng: np.random.Generator, until: float | None):
    """One struck key: the hammer's force and its modes (frequencies, complex gains, decays, damped decays),
    and when its damper lands (samples after the strike; -1 never)."""
    m = float(note.pitch)
    k = piano.key(int(round(m)))
    art = set(str(note.art).replace("+", " ").split())
    soft = "soft" in art
    n_strings = strings_for(int(round(m)))
    wear = piano.wear
    # --- the hammer ---------------------------------------------------------------------------
    vel = float(np.clip(note.vel, 0.0, 1.0))
    v0 = 0.35 * (5.5 / 0.35) ** vel * np.exp(rng.normal(0.0, 0.02))  # hammer speed, m/s
    hard = piano.hardness * piano.voicing[k]
    struck = n_strings
    if soft and n_strings > 1:
        struck = n_strings - 1
        hard *= 0.55  # the shifted hammer meets its strings with unworn felt
    strip = piano.felt_strip
    # Chaigne and Askenfelt's hammer is one string's share: the whole hammer is that many times heavier,
    # and its felt meets that many strings (fewer when shifted), each with its own impedance
    stiff = _log_interp(m, K_TABLE) * hard * (1.0 - 0.8 * strip) * struck
    power = _interp(m, P_TABLE) - 0.3 * strip
    mass = _log_interp(m, MASS_TABLE) * n_strings
    z = _log_interp(m, Z_TABLE) * struck
    x0 = _interp(m, STRIKE_TABLE)
    key = int(round(m))
    f0 = piano.fundamental[k] * 2.0 ** ((m - key) / 12.0)
    fs = sr * HAMMER_RATE
    force = hammer_force(v0, mass, stiff, power, z, x0 / f0 * fs, (1.0 - x0) / f0 * fs, 0.98, float(fs),
                         0.03)
    if strip > 0.0:  # the felt strip between hammer and strings: a soft layer that passes only the slow push
        cut = 1000.0 * 6.0 ** (1.0 - strip)
        force = sosfilt(butter(2, cut, fs=fs, output="sos"), np.concatenate([force, np.zeros(int(0.004 * fs))]))
    force = force[: len(force) // HAMMER_RATE * HAMMER_RATE].reshape(-1, HAMMER_RATE).mean(axis=1)
    # --- the partials ----------------------------------------------------------------------------
    b = piano.inharmonicity(m)
    top = int(min(90, MAX_PARTIAL_HZ / f0 + 1))  # a bass note's 90th partial is past 3.5 kHz, all but silent
    n = np.arange(1, top + 1)
    fn = n * f0 * np.sqrt((1.0 + b * n * n) / (1.0 + b))
    keep = fn < min(MAX_PARTIAL_HZ, 0.45 * sr)
    n, fn = n[keep], fn[keep]
    shape = np.sin(n * np.pi * x0) / np.sqrt(1.0 + b * n * n)  # where it was struck; what reaches the bridge
    # decays: the prompt sound (the strings moving together), the aftersound (against each other)
    prompt = prompt_t60(fn) * np.sqrt(piano.size)
    alpha_after = modal.LN1000 / (after_ratio(fn) * prompt)
    alpha_prompt = modal.LN1000 / prompt
    # the unison, coupled at the bridge: eig of diag(i w_k - a) - eps * ones, per partial
    cents = piano.unison[k, :n_strings] + rng.normal(0.0, 0.05, n_strings)
    w = 2.0 * np.pi * fn[:, None] * 2.0 ** (cents[None, :] / 1200.0)
    eps_re = (alpha_prompt - alpha_after) / n_strings
    eps = eps_re * (1.0 + 1j * rng.uniform(-0.15, 0.15, len(fn)))
    matrix = np.zeros((len(fn), n_strings, n_strings), dtype=complex)
    idx = np.arange(n_strings)
    matrix[:, idx, idx] = 1j * w - alpha_after[:, None]
    matrix -= eps[:, None, None]
    lam, vec = np.linalg.eig(matrix)
    excite = piano.uneven[k, :n_strings] * (1.0 + rng.normal(0.0, 0.02, n_strings))
    if struck < n_strings:
        excite = excite.copy()
        excite[0] *= 0.08  # the shifted hammer barely brushes the first string
    coeff = np.linalg.solve(vec, np.broadcast_to(excite, (len(fn), n_strings))[..., None])[..., 0]
    out_w = vec.sum(axis=1)  # each eigenmode's push on the bridge
    amp = coeff * out_w * shape[:, None]  # complex, per partial and eigenmode
    freqs = [(lam.imag / (2.0 * np.pi)).ravel()]
    rates = [np.maximum(-lam.real, 0.05).ravel()]
    gains = [(-1j * amp).ravel()]  # a string starts from rest: a sine
    index = [np.repeat(n, n_strings)]
    # the plane along the soundboard: barely struck, barely coupled, a fraction of a cent higher, ringing on
    level, upto = HORIZONTAL
    low = n <= upto
    freqs.append(fn[low] * 2.0 ** (piano.planes[k] / 1200.0))
    rates.append(alpha_after[low])
    gains.append(-1j * level * excite.sum() * shape[low])
    index.append(n[low])
    strings = sum(len(g) for g in gains)
    # the pedal's halo: the open strings whose partials lie within a few cents of this note's answer it,
    # building up over a few tenths of a second and ringing on while the pedal is down
    if "ped" in art:
        partial_amp = np.abs(amp.sum(axis=1))
        for i in range(min(8, len(fn))):
            for kk in range(1, 7):
                other = int(round(m + 12.0 * np.log2(n[i] / kk)))
                if other == key or not LOW <= other <= HIGH:
                    continue
                f2 = float(piano.partial(other, kk))
                off = 1200.0 * np.log2(f2 / fn[i])
                if abs(off) > 30.0:
                    continue
                # driven by a partial decaying at its prompt rate, an open string ringing longer builds up as
                # the difference of the two decays, peaking after a second or so (at HALO below the partial)
                slow = modal.LN1000 / (1.5 * prompt_t60(f2))
                fast = max(alpha_prompt[i], 1.3 * slow)
                crest = np.log(fast / slow) / (fast - slow)
                peak = np.exp(-slow * crest) - np.exp(-fast * crest)
                a = partial_amp[i] * HALO * strings_for(other) / 3.0 / (1.0 + (off / 8.0) ** 2) / peak
                freqs.append(np.array([f2, f2]))
                rates.append(np.array([slow, fast]))
                gains.append(np.array([-1j * a, 1j * a]))
                index.append(np.array([kk, kk]))
    freqs, rates, gains, index = (np.concatenate(x) for x in (freqs, rates, gains, index))
    # the force's spectrum at each mode: how much of the blow reaches it
    spectrum = _spectrum(np.ascontiguousarray(force), np.ascontiguousarray(freqs), float(sr))
    reach = np.abs(gains * spectrum)
    loud = np.sqrt(0.5 * np.sum(reach[:strings] ** 2))
    live = reach > reach[:strings].max() * 1e-3  # 60 dB under the strongest: inaudible, and half the cost at pp
    freqs, rates, gains, reach, index = freqs[live], rates[live], gains[live], reach[live], index[live]
    # the damper
    t60 = modal.LN1000 / rates
    damped = _interp(min(m, 89.0), DAMPED_TABLE) * (1.0 + 2.0 * wear) / np.sqrt(1.0 + 0.15 * (index - 1))
    damped = np.minimum(damped, t60)
    end = note.dur if until is None else min(note.dur, until)
    damp_at = -1
    if m < UNDAMPED or (until is not None and until < note.dur):
        damp_at = int(round(end * sr))
    if until is not None and until < note.dur:  # re-struck: the hammer stops what was ringing
        damped = np.minimum(damped, 0.08)
    # loudness: the attack's bridge-force RMS set by the velocity; the felt strip takes some away
    target = _loudness(vel) * (1.0 - 0.45 * strip) * (0.7 if soft else 1.0)
    scale = target / max(loud, 1e-12)
    # ...but no voicing can make a string ring louder than its blow can drive it. While the hammer pushes,
    # each mode follows the force almost statically; for partials far above what the blow reaches (the top
    # octaves, soft blows, the felt strip) that swing would dwarf the ring once scaled up to the target, so
    # the note stays as weak as its hammer makes it: the push at most CREST times the ring's RMS
    during = np.zeros((1, len(force) + 1))
    modal.ring(during, 0, force, freqs, np.ascontiguousarray(gains.real), np.ascontiguousarray(gains.imag), t60,
               t60, -1, 1.0, np.ones(1), float(sr), 0.0)
    push = float(np.abs(during).max())
    if push * scale > CREST * target:
        scale = CREST * target / push
    gains = gains * scale
    return force, freqs, gains, t60, damped, damp_at, float(reach.max() * scale)


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A piano part: stereo, dry, `length` samples, before placement and level."""
    if name not in SPEC:
        raise ValueError(f"no such instrument: {name}")
    piano = Piano(sr, make, settings)
    force = np.zeros((2, length))
    ordered = sorted(notes, key=lambda n: (n.start, n.pitch))
    # when each key is struck again: the hammer stops what the last blow left ringing
    next_strike = {}
    restrike = [None] * len(ordered)
    for i in range(len(ordered) - 1, -1, -1):
        key = int(round(ordered[i].pitch))
        if key in next_strike:
            restrike[i] = next_strike[key] - ordered[i].start
        next_strike[key] = ordered[i].start
    # the key and hammer knocking on the frame: a few short thuds, one chosen for each blow
    thump = int(0.025 * sr)
    thuds = sosfilt(butter(2, [70.0, 1400.0], btype="bandpass", fs=sr, output="sos"),
                    rng.standard_normal((8, thump + 64)), axis=1)[:, 64:]
    env = np.exp(-np.arange(thump) / (0.004 * sr)) * (1.0 - np.exp(-np.arange(thump) / (0.0006 * sr)))
    thuds *= env[None, :]
    thuds /= np.sqrt(np.mean(thuds**2, axis=1, keepdims=True)) + 1e-12
    for i, note in enumerate(ordered):
        start = int(round(note.start * sr))
        if start >= length or note.dur <= 0:
            continue
        until = restrike[i]
        exc, freqs, gains, t60, damped, damp_at, ringing = _note(piano, note, sr, rng, until)
        # a player's image: the bass to the left, the treble to the right
        pan = float(np.clip((note.pitch - 64.0) / 30.0, -1.0, 1.0)) * 0.45
        chan = np.array([np.cos((pan + 1.0) * np.pi / 4.0), np.sin((pan + 1.0) * np.pi / 4.0)]) * np.sqrt(2.0)
        modal.ring(force, start, exc, freqs, np.ascontiguousarray(gains.real), np.ascontiguousarray(gains.imag),
                   t60, damped, damp_at, float(0.012 * sr), chan, float(sr), ringing * 1e-4)
        # the knock into the soundboard, relatively louder in the treble (where the strings' tone is
        # thinnest) and in a harder blow
        vel = float(np.clip(note.vel, 0.0, 1.0))
        n = min(length - start, thump)
        thud = thuds[int(rng.integers(len(thuds)))][:n] * (1.0 if rng.random() < 0.5 else -1.0)
        level = _interp(note.pitch, KNOCK_TABLE) * (1.0 + 2.0 * piano.felt_strip) * (1.0 + 0.5 * piano.wear)
        level *= _loudness(vel) * (0.5 + vel)
        force[:, start:start + n] += (thud * level)[None, :] * chan[:, None]
    # each channel through the soundboard, oaconvolve's a few blocks at a time, then high-passed where it lies, a
    # stretch at a time (the filter's state carried: as along axis 0 of the whole)
    out = np.empty((length, 2))
    for ch in range(2):
        oa.convolve(force[ch], piano.board[:, ch], length, out=out[:, ch])
    del force
    sos = butter(1, 20.0, btype="highpass", fs=sr, output="sos")
    for ch in range(2):
        state = np.zeros((sos.shape[0], 2))
        for a in range(0, length, 1 << 16):
            out[a:a + (1 << 16), ch], state = sosfilt(sos, out[a:a + (1 << 16), ch], zi=state)
    return out
