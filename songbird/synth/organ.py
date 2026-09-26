"""Organs: a tonewheel organ played through a rotary speaker, and a harmonium.

A tonewheel organ makes no sound of its own until a key closes a contact.
Under the keys a synchronous motor turns a shaft of 91 steel wheels, each
with a wavy edge that swings the flux in a pickup coil beside it: a
near-sine at one equal-tempered pitch (A 440), with a little 2nd and 3rd
harmonic from the wheel's shape. The wheels never stop, so a note never
starts its sines from zero: it switches them in wherever they happen to be.
Each key has nine contacts, one for each busbar, and each busbar carries one
drawbar's footage: 16', 5 1/3', 8', 4', 2 2/3', 2', 1 3/5', 1 1/3' and 1',
0.5, 1.5, 1, 2, 3, 4, 5, 6 and 8 times the note. Each is played by the
nearest wheel, so the quints (5 1/3', 2 2/3', 1 1/3') are tempered fifths,
2 cents flat of pure, and the 1 3/5' a tempered third, 14 cents sharp. The
generator runs out of wheels at both ends: the 16' of the lowest octave
folds up an octave (it doubles the 8'), and a footage that would need a
wheel above F#8 (5.9 kHz) folds down, as the 1' does over the top octave
and a half. A drawbar pulled out n steps (of 8) passes its busbar 3 dB
louder for each step.

As a key goes down, its nine contacts meet their busbars one after another
over 1.5 to 4.5 ms, each switching its sine on abruptly where the wheel is
and chattering as its wire wipes onto the bar (breaks tens of microseconds
long, for a millisecond or two): the key click, part of the instrument's
sound. Through the amplifier and speaker it stays within 20 dB of its peak
for 7 to 10 ms, and at the generator 73% of its energy lies above 1 kHz,
where the steady tone has almost none. A key rises more cleanly (the
contact's resistance climbs over a fraction of a millisecond), a click with
6 to 20 dB less above 2 kHz. The percussion (on some registrations) is a
single decaying envelope that the first key down after all keys were up
sets off: it adds the 4' or the 2 2/3' wheel of every key held, with a time
constant of 0.2 s (fast: gone in about a second) or 1 s (slow: about four),
and a legato phrase never sets it off again (a note held over into the next
gets it 19 dB down). It takes the 1' busbar for itself and, at normal
volume, drops the drawbars 3 dB.

The scanner vibrato is the organ's most-heard colour: the signal runs down
a delay line of coils and capacitors, and a rotating capacitor scans along
it and back 6.87 times a second, so the pitch swings between two values in
a rounded square wave, ±8, ±16 or ±24 cents (V1, V2, V3), with sidebands
6.87 Hz either side of every partial (4 dB under the partial at V3); the
chorus settings (C1, C2, C3) add the dry signal back at equal level, which
beats against the swung one. The percussion bypasses it. An organ has no
touch: a note's velocity is the swell pedal instead, the whole organ's
volume (24 dB from 0.2 to 1), with its loudness contour (the treble above
800 Hz falling further as it closes; the foot moves in a tenth of a second
or so). A bigger registration is played with the swell eased back a little,
1.2 dB for each doubling of the drawbars' power, so a full organ is 3 dB
louder than the house sound rather than 5.5, and the soft one 5 dB quieter.
Then the amplifier's tubes, an asymmetric soft clip: the house sound at the
typical swell is nearly clean (its distortion 36 dB under the tone), a
full organ wide open growls (14 to 18 dB under).

The rotary speaker splits the sound at 800 Hz: a horn above, a drum rotor
with a scoop below, spinning slowly (0.8 and 0.7 turns a second) or fast
(6.7 and 5.7), each machine's belts a few percent off. Each rotating source
is heard by two microphones at its sides as a delay that swings (the
Doppler shift) and a level that swings (the horn beams its sound), plus a
weaker reflection off the cabinet with the opposite swing, so the two paths
comb against each other as they turn. Measured on a steady tone: the horn's
pitch swings ±0.76% at speed (13 cents) and its level 9 dB, the drum's
±0.24% and 4 dB; at the slow speed the same swing of level and an eighth of
the Doppler. The horn spins up in about a second and the drum in about
four (time constants 0.33 and 1.3 s), and they coast down 2.5 times more
slowly.

Registrations are named by articulation, and the name holds from the note
that carries it until another is named (like pressing a preset key); "fast"
and "slow" switch the rotor the same way and combine with a registration
("gospel fast"). The drawbars, in footage order:

    ""        the house sound: 6 8 8 (4+4b) (3b) (4b) 0 0 (4b-2), from brightness b:
              68 8622 000 at 0.5, 68 8400 000 at 0, 68 8834 002 at 1; chorus C3, a little drive
    ballad    00 8530 000: round flutes for pads under a voice; chorus C2
    jazz      88 8000 000 with percussion on the 3rd harmonic, fast, normal; no vibrato
    gospel    88 8800 008: bright, a whistle on top; chorus C3, more drive
    full      88 8888 888: everything out; chorus C3, the most drive
    soft      00 6400 000: a quiet 8' and 4'; chorus C1
    chime     00 8000 000 with percussion on the 2nd harmonic, slow, soft; chorus C1
    808000000 any nine digits: those drawbars, with the house's chorus

A harmonium is a box of free reeds blown by a bellows the player pumps (a
thin wrapper on the band's drone, reed.py, with its reed box for a body):
an 8' rank of reeds, a softer second rank tuned 3 to 8 cents sharp so the
pair beats slowly (the celeste: the fundamental swings about 9 dB), and a
4' rank brought in with brightness (the 2nd harmonic from 18 to 8 dB under
the fundamental). A reed takes 20 to 50 ms to speak (to 90%: 53 ms at F2,
18 ms at F6), stops in a few hundredths once its pallet closes, and goes a
hair flat as the pumping hand swells the pressure a few percent every couple
of seconds. A key has no touch: velocity is how hard the bellows are pushed
(16 dB from 0.2 to 1), and a harder push is a little brighter. "" plays a
key as a harmonium player does; "swell" opens and closes the bellows over
the note, as the band's drone does.

make gives each machine its own organ: the wheels' levels and harmonics,
each key's contacts and how they chatter, the rotor's belts and motors;
and its own harmonium's reeds, celeste and pumping. wear adds contact
chatter and wheel scatter, puts the mains that turn the generator a few
cents off, and pulls reeds off pitch. brightness sets the house
registration's upper drawbars (and its drive) and the harmonium's 4'.
ornament isn't used: an organist's ornaments are in the notes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit
from scipy.signal import butter, sosfilt

from . import body, reed, touch

SPEC = {
    "organ": dict(
        family="keys",
        role="comping",
        register=(36, 96),
        place=(0.0, 0.85),
        level=0.0663,
        poly=True,
        articulations={
            "": "the house registration (68 8622 000 at brightness 0.5, chorus C3), or whatever was last named",
            "ballad": "from this note on: 00 8530 000, chorus C2: round flutes for pads under a voice",
            "jazz": "from this note on: 88 8000 000 with percussion (3rd harmonic, fast, normal), no vibrato",
            "gospel": "from this note on: 88 8800 008, chorus C3, more drive",
            "full": "from this note on: 88 8888 888, chorus C3, the most drive",
            "soft": "from this note on: 00 6400 000, chorus C1",
            "chime": "from this note on: 00 8000 000 with percussion (2nd harmonic, slow, soft), chorus C1: a bell "
                     "on each phrase's first note",
            "888000000": "any nine digits pull those drawbars (16' to 1', 0-8) from this note on, chorus C3",
            "fast": "the rotary speaker spins up from this note on (the horn in about 1 s, the drum in about 4)",
            "slow": "the rotary speaker coasts back down to its slow speed from this note on",
        },
        about="a tonewheel organ through a rotary speaker: drawbar registrations named by articulation, key "
              "click, single-trigger percussion, scanner vibrato and chorus; velocity is the swell pedal",
        brighter=0.0,
        dynamic=True,
    ),
    "harmonium": dict(
        family="keys",
        role="comping",
        register=(41, 89),
        place=(-0.25, 0.5),
        level=0.0978,
        poly=True,
        articulations={
            "": "a key played: the reeds speak in 20-60 ms and stop when it rises",
            "swell": "the bellows swell the note in and out over its length, as the band's drone does",
        },
        about="a harmonium: 8' reeds with a celeste rank and a 4' with brightness, a pumped bellows, in a reed box",
        dynamic=True,
    ),
}

DEFAULTS = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0)


def _settings(settings: dict) -> tuple[float, float, float, float]:
    s = {**DEFAULTS, **(settings or {})}
    return (float(np.clip(s["brightness"], 0.0, 1.0)), float(np.clip(s["wear"], 0.0, 1.0)),
            float(np.clip(s["ornament"], 0.0, 1.0)), float(np.clip(s["body"], 0.7, 1.35)))


def _hz(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69.0) / 12.0)


def _fold(m: float, lo: float, hi: float) -> float:
    """A pitch outside the keyboard played an octave (or more) in, where the keys are."""
    while m < lo - 0.5:
        m += 12.0
    while m > hi + 0.5:
        m -= 12.0
    return m


# --- the tonewheel generator ------------------------------------------------------------------------

DRAWBARS = ("16'", "5 1/3'", "8'", "4'", "2 2/3'", "2'", "1 3/5'", "1 1/3'", "1'")
OFFSETS = (-12, 7, 0, 12, 19, 24, 28, 31, 36)  # each drawbar's wheel, in semitones from the key
FIRST_WHEEL, LAST_WHEEL = 24, 114  # C1 (32.7 Hz) to F#8 (5.9 kHz): 91 wheels
MANUAL = (36, 96)  # C2 to C7: 61 keys
SCANNER_HZ = 6.87
SCANNER_CENTS = {"": 0.0, "V1": 8.0, "V2": 16.0, "V3": 24.0, "C1": 8.0, "C2": 16.0, "C3": 24.0}
PERC_TAU = {"fast": 0.2, "slow": 1.0}  # the percussion's time constant (s): gone in about 1 s or 4 s
PERC_LEVEL = {"normal": 1.4, "soft": 0.6}  # against a drawbar at full


def wheel_for(key: int, offset: int) -> int:
    """The wheel a key's drawbar plays: the nearest tempered pitch, folded back at the generator's ends."""
    p = key + offset
    if p < MANUAL[0]:
        p += 12  # the 16' of the lowest octave folds up
    while p > LAST_WHEEL:
        p -= 12  # the top footages fold down
    return p


def drawbar_gain(n: int) -> float:
    """A drawbar pulled n steps of 8: 3 dB louder each step, silent at 0."""
    return 0.0 if n <= 0 else 10.0 ** (-3.0 * (8 - n) / 20.0)


@dataclass(frozen=True)
class Registration:
    drawbars: tuple[int, ...]  # 16' to 1', 0..8
    scanner: str  # "", V1..V3, C1..C3
    percussion: str  # "" or "<2nd|3rd> <fast|slow> <normal|soft>"
    drive: float  # the amplifier's drive, 0..1


def registration(name: str, brightness: float = 0.5) -> Registration:
    """A named registration; "" is the house sound, its upper drawbars set by brightness; nine digits
    ("808000000") pull those drawbars, with the house's chorus."""
    b = brightness
    if len(name) == 9 and name.isdigit():
        return Registration(tuple(min(int(c), 8) for c in name), "C3", "", 0.45)
    if name == "chime":
        return Registration((0, 0, 8, 0, 0, 0, 0, 0, 0), "C1", "2nd slow soft", 0.2)
    if name == "ballad":
        return Registration((0, 0, 8, 5, 3, 0, 0, 0, 0), "C2", "", 0.25)
    if name == "jazz":
        return Registration((8, 8, 8, 0, 0, 0, 0, 0, 0), "", "3rd fast normal", 0.35)
    if name == "gospel":
        return Registration((8, 8, 8, 8, 0, 0, 0, 0, 8), "C3", "", 0.6)
    if name == "full":
        return Registration((8, 8, 8, 8, 8, 8, 8, 8, 8), "C3", "", 0.75)
    if name == "soft":
        return Registration((0, 0, 6, 4, 0, 0, 0, 0, 0), "C1", "", 0.15)
    upper = (int(round(4 + 4 * b)), int(round(3 * b + 1e-9)), int(round(4 * b)), 0, 0,
             int(max(0, round(4 * b - 2))))
    return Registration((6, 8, 8) + upper, "C3", "", 0.3 + 0.3 * b)


REGISTRATIONS = ("", "ballad", "jazz", "gospel", "full", "soft", "chime")


def _energy(reg: Registration) -> float:
    """The drawbars' power (the percussion's 1' taken away, but not its 3 dB drop, which is the organ's own)."""
    gains = [drawbar_gain(n) for n in reg.drawbars]
    if reg.percussion:
        gains[8] = 0.0
    return float(np.sum(np.square(gains)))


@njit(cache=True)
def _generator(n, sr, freqs, phases, h2, h3, ev_t, ev_w, ev_main, ev_perc, ev_ramp, trig_t, trig_decay):
    """The wheels, switched by the contacts: every event adds `ev_main` (busbars through the drawbars) or
    `ev_perc` (the percussion's keying) to wheel ev_w's gain at sample ev_t, over ev_ramp samples. A wheel's
    phase is where it would be had it run since the start. Returns the drawbars' signal and the
    percussion's, shaped by its envelope: each trigger in trig_t sets it back to 1, to fall by
    trig_decay (per sample) from there."""
    main = np.zeros(n)
    perc = np.zeros(n)
    w_count = freqs.shape[0]
    cur_m = np.zeros(w_count)
    tgt_m = np.zeros(w_count)
    step_m = np.zeros(w_count)
    cur_p = np.zeros(w_count)
    tgt_p = np.zeros(w_count)
    step_p = np.zeros(w_count)
    left = np.zeros(w_count, dtype=np.int64)
    c = np.zeros(w_count)
    s = np.zeros(w_count)
    cw = np.cos(2.0 * np.pi * freqs / sr)
    sw = np.sin(2.0 * np.pi * freqs / sr)
    active = np.zeros(w_count, dtype=np.int64)
    is_active = np.zeros(w_count, dtype=np.bool_)
    count = 0
    e = 0
    events = ev_t.shape[0]
    tr = 0
    triggers = trig_t.shape[0]
    env = 0.0
    decay = 1.0
    for t in range(n):
        while e < events and ev_t[e] <= t:
            w = ev_w[e]
            tgt_m[w] += ev_main[e]
            tgt_p[w] += ev_perc[e]
            ramp = max(ev_ramp[e], 1)
            step_m[w] = (tgt_m[w] - cur_m[w]) / ramp
            step_p[w] = (tgt_p[w] - cur_p[w]) / ramp
            left[w] = ramp
            if not is_active[w]:
                is_active[w] = True
                active[count] = w
                count += 1
                theta = phases[w] + 2.0 * np.pi * ((freqs[w] * t / sr) % 1.0)
                c[w] = np.cos(theta)
                s[w] = np.sin(theta)
            e += 1
        while tr < triggers and trig_t[tr] <= t:
            env = 1.0
            decay = trig_decay[tr]
            tr += 1
        acc_m = 0.0
        acc_p = 0.0
        j = 0
        while j < count:
            w = active[j]
            if left[w] > 0:
                left[w] -= 1
                if left[w] == 0:
                    cur_m[w] = tgt_m[w]
                    cur_p[w] = tgt_p[w]
                else:
                    cur_m[w] += step_m[w]
                    cur_p[w] += step_p[w]
            cc = c[w]
            ss = s[w]
            wave = cc + h2[w] * (cc * cc - ss * ss) + h3[w] * cc * (4.0 * cc * cc - 3.0)
            acc_m += cur_m[w] * wave
            acc_p += cur_p[w] * wave
            c[w] = cc * cw[w] - ss * sw[w]
            s[w] = ss * cw[w] + cc * sw[w]
            if left[w] == 0 and abs(tgt_m[w]) < 1e-12 and abs(tgt_p[w]) < 1e-12:
                cur_m[w] = 0.0
                tgt_m[w] = 0.0
                cur_p[w] = 0.0
                tgt_p[w] = 0.0
                is_active[w] = False
                count -= 1
                active[j] = active[count]
                continue
            j += 1
        main[t] = acc_m
        perc[t] = acc_p * env
        env *= decay
    return main, perc


@njit(cache=True)
def _scanner(x, sr, seg_t, seg_depth, seg_wet, seg_dry, phase0, lp):
    """The scanner: a delay line swept by a rounded triangle at 6.87 Hz. seg_*: from sample seg_t[i] on,
    the sweep's depth (samples each way), how much of the swept signal and of the dry one to mix; a
    change of setting glides over about 5 ms. Every setting, off included, hears the line's middle, so
    switching never shifts the signal in time."""
    n = x.shape[0]
    y = np.empty(n)
    size = 256
    line = np.zeros(size)
    base = 30.0
    eps = 0.08  # the rounding of the triangle's corners, as a fraction of its period
    inc = 6.87 / sr
    p = phase0
    wet_lp = 0.0
    k = 0
    depth, wet, dry = 0.0, 0.0, 1.0
    if seg_t.shape[0] > 0:  # it starts where the first setting puts it
        depth, wet, dry = seg_depth[0], seg_wet[0], seg_dry[0]
    depth_to, wet_to, dry_to = depth, wet, dry
    glide = 1.0 - np.exp(-1.0 / (0.005 * sr))
    segs = seg_t.shape[0]
    for t in range(n):
        while k < segs and seg_t[k] <= t:
            depth_to = seg_depth[k]
            wet_to = seg_wet[k]
            dry_to = seg_dry[k]
            k += 1
        depth += (depth_to - depth) * glide
        wet += (wet_to - wet) * glide
        dry += (dry_to - dry) * glide
        line[t % size] = x[t]
        dry_now = line[(t - int(base)) % size]  # the line's middle
        if wet < 1e-6 and wet_to == 0.0:
            y[t] = dry * dry_now
        else:
            # the rounded triangle, 1 at p = 0 and -1 at p = 0.5
            q = p if p < 0.5 else 1.0 - p  # 0..0.5
            if q < eps:
                tri = 1.0 - 2.0 * eps - 2.0 * q * q / eps
            elif q > 0.5 - eps:
                r = 0.5 - q
                tri = -1.0 + 2.0 * eps + 2.0 * r * r / eps
            else:
                tri = 1.0 - 4.0 * q
            d = base + depth * tri
            i = int(d)
            f = d - i
            # four-point Lagrange read, d samples back
            xm1 = line[(t - i + 1) % size]
            x0 = line[(t - i) % size]
            x1 = line[(t - i - 1) % size]
            x2 = line[(t - i - 2) % size]
            v = (x0 + f * (0.5 * (x1 - xm1) + f * (xm1 - 2.5 * x0 + 2.0 * x1 - 0.5 * x2
                                                    + f * (1.5 * (x0 - x1) + 0.5 * (x2 - xm1)))))
            wet_lp += lp * (v - wet_lp)  # the line's coils and capacitors: a gentle low-pass
            y[t] = wet * wet_lp + dry * dry_now
        p += inc
        if p >= 1.0:
            p -= 1.0
    return y


@njit(cache=True)
def _expression(x, sr, ev_t, ev_target, ev_gain, s0, g0, follow, gamma, contour_hz, contour_depth):
    """The swell pedal: the volume follows the pedal (which moves to each target, and to each gain, with
    time constant `follow` s) as pedal^gamma times the gain, and as it closes the treble above contour_hz
    falls further."""
    n = x.shape[0]
    y = np.empty(n)
    s = s0
    target = s0
    g = g0
    g_target = g0
    e = 0
    events = ev_t.shape[0]
    k = 1.0 - np.exp(-1.0 / (follow * sr))
    a = 1.0 - np.exp(-2.0 * np.pi * contour_hz / sr)
    low = 0.0
    for t in range(n):
        while e < events and ev_t[e] <= t:
            target = ev_target[e]
            g_target = ev_gain[e]
            e += 1
        s += (target - s) * k
        g += (g_target - g) * k
        level = g * np.exp(gamma * np.log(max(s, 0.02)))
        low += a * (x[t] - low)
        y[t] = level * (x[t] - contour_depth * (1.0 - s) * (x[t] - low))
    return y


def expression(y: np.ndarray, sr: int, swell) -> np.ndarray:
    """The swell pedal as set by Organ.swell(): 24 dB from velocity 0.2 to 1, the foot moving in about a
    tenth of a second, the treble above 800 Hz falling as much again as the pedal closes."""
    ev_t, ev_s, ev_g, s0, g0 = swell
    return _expression(y, float(sr), ev_t, ev_s, ev_g, s0, g0, 0.08, touch.exponent(24.0), 800.0, 0.85)


@njit(cache=True)
def _read(line, size, t, d):
    """Four-point Lagrange read from a circular line, d (>= 1) samples before sample t."""
    i = int(d)
    f = d - i
    xm1 = line[(t - i + 1) % size]
    x0 = line[(t - i) % size]
    x1 = line[(t - i - 1) % size]
    x2 = line[(t - i - 2) % size]
    return x0 + f * (0.5 * (x1 - xm1) + f * (xm1 - 2.5 * x0 + 2.0 * x1 - 0.5 * x2
                                             + f * (1.5 * (x0 - x1) + 0.5 * (x2 - xm1))))


@njit(cache=True)
def _rotors(x, sr, ev_t, ev_fast, fast0, speeds, times, horn, drum, mics, angles, low_sos, high_sos, horn_sos,
            out_sos):
    """The rotary speaker. x: the amplifier's output. The crossover (low_sos, high_sos: second-order
    sections, each run twice, a Linkwitz-Riley pair) splits it between the drum and the horn (whose driver
    rolls off: horn_sos). ev_t, ev_fast: from sample ev_t[i] on the rotors head for fast (1) or slow (0)
    speed; fast0: where they start. speeds: horn slow, horn fast, drum slow, drum fast (Hz); times: horn
    up, horn down, drum up, drum down (time constants, s). horn, drum: (radius in samples, the level it
    beams away from a microphone, the reflection's gain, its extra delay in samples). mics: the
    microphones' angles; angles: the rotors' at the start; out_sos: a high-pass on each microphone.
    Returns (n, 2): what each microphone hears. Coefficients are (b0, b1, b2, 1, a1, a2)."""
    n = x.shape[0]
    out = np.zeros((n, 2))
    size = 1024
    line_h = np.zeros(size)
    line_d = np.zeros(size)
    fast = fast0
    wh = 2.0 * np.pi * (speeds[1] if fast else speeds[0])
    wd = 2.0 * np.pi * (speeds[3] if fast else speeds[2])
    ch, sh = np.cos(angles[0]), np.sin(angles[0])
    cd, sd = np.cos(angles[1]), np.sin(angles[1])
    ku = 1.0 - np.exp(-1.0 / (times[0] * sr))
    kd = 1.0 - np.exp(-1.0 / (times[1] * sr))
    dku = 1.0 - np.exp(-1.0 / (times[2] * sr))
    dkd = 1.0 - np.exp(-1.0 / (times[3] * sr))
    rh, bh, gh, xh = horn[0], horn[1], horn[2], horn[3]
    rd, bd, gd, xd = drum[0], drum[1], drum[2], drum[3]
    # the directivities average 1 over a turn: b + (1 - b)(1 + cos)/2 averages (1 + b) / 2
    nh = 2.0 / (1.0 + bh) / (1.0 + gh)
    nd = 2.0 / (1.0 + bd) / (1.0 + gd)
    cm = np.cos(mics)
    sm = np.sin(mics)
    base = 3.0
    e = 0
    events = ev_t.shape[0]
    z = np.zeros((9, 2))  # the biquads' states: low x2, high x2, horn, two microphones' high-passes
    for t in range(n):
        while e < events and ev_t[e] <= t:
            fast = ev_fast[e]
            e += 1
        # the crossover, sample by sample (transposed direct form II)
        v = x[t]
        for k in range(2):
            y = low_sos[0] * v + z[k, 0]
            z[k, 0] = low_sos[1] * v - low_sos[4] * y + z[k, 1]
            z[k, 1] = low_sos[2] * v - low_sos[5] * y
            v = y
        low = v
        v = x[t]
        for k in range(2, 4):
            y = high_sos[0] * v + z[k, 0]
            z[k, 0] = high_sos[1] * v - high_sos[4] * y + z[k, 1]
            z[k, 1] = high_sos[2] * v - high_sos[5] * y
            v = y
        y = horn_sos[0] * v + z[4, 0]
        z[4, 0] = horn_sos[1] * v - horn_sos[4] * y + z[4, 1]
        z[4, 1] = horn_sos[2] * v - horn_sos[5] * y
        line_h[t % size] = -y  # a Linkwitz-Riley pair sums flat with the high side flipped
        line_d[t % size] = low
        # the rotors' speeds follow their motors; their angles turn (a rotation, renormalized now and then)
        target_h = 2.0 * np.pi * (speeds[1] if fast else speeds[0])
        target_d = 2.0 * np.pi * (speeds[3] if fast else speeds[2])
        wh += (target_h - wh) * (ku if target_h > wh else kd)
        wd += (target_d - wd) * (dku if target_d > wd else dkd)
        a = wh / sr
        ca, sa = 1.0 - 0.5 * a * a, a - a * a * a / 6.0
        ch, sh = ch * ca - sh * sa, sh * ca + ch * sa
        a = wd / sr
        ca, sa = 1.0 - 0.5 * a * a, a - a * a * a / 6.0
        cd, sd = cd * ca - sd * sa, sd * ca + cd * sa
        if t % 512 == 0:
            r = 1.0 / np.sqrt(ch * ch + sh * sh)
            ch *= r
            sh *= r
            r = 1.0 / np.sqrt(cd * cd + sd * sd)
            cd *= r
            sd *= r
        for m in range(2):
            # the horn: straight to the microphone, and off the cabinet's back (the opposite swing)
            c = ch * cm[m] + sh * sm[m]  # cos of the angle between where it points and the microphone
            v = bh + (1.0 - bh) * 0.5 * (1.0 + c)
            y = v * _read(line_h, size, t, base + rh * (1.0 - c))
            v = bh + (1.0 - bh) * 0.5 * (1.0 - c)
            y += gh * v * _read(line_h, size, t, base + xh + rh * (1.0 + c))
            y *= nh
            c = cd * cm[m] + sd * sm[m]
            v = bd + (1.0 - bd) * 0.5 * (1.0 + c)
            w = v * _read(line_d, size, t, base + rd * (1.0 - c))
            v = bd + (1.0 - bd) * 0.5 * (1.0 - c)
            w += gd * v * _read(line_d, size, t, base + xd + rd * (1.0 + c))
            v = y + w * nd
            k = 5 + m
            y = out_sos[0] * v + z[k, 0]
            z[k, 0] = out_sos[1] * v - out_sos[4] * y + z[k, 1]
            z[k, 1] = out_sos[2] * v - out_sos[5] * y
            out[t, m] = y
    return out


# --- the organ -----------------------------------------------------------------------------------------


class Organ:
    """One machine's tonewheel organ and rotary speaker (from `make`), set up by the band settings."""

    def __init__(self, sr: int, make: np.random.Generator, settings: dict):
        self.sr = sr
        self.brightness, self.wear, self.ornament, self.size = _settings(settings)
        wear = self.wear
        wheels = np.arange(FIRST_WHEEL, LAST_WHEEL + 1)
        self.detune = make.normal(0.0, 3.0 * wear)  # the mains that turn the motor: the whole organ a hair off
        self.freqs = 440.0 * 2.0 ** ((wheels - 69.0 + self.detune / 100.0) / 12.0)
        # each wheel's level (its magnet and coil) and the generator's taper toward the top
        taper = np.minimum(1.0, (1500.0 / self.freqs) ** 0.25)
        self.level = np.exp(make.normal(0.0, 0.07 + 0.12 * wear, len(wheels))) * taper
        # a near-sine: a little 2nd and 3rd harmonic, filtered away toward the top
        shape = np.clip(1200.0 / self.freqs, 0.1, 1.0)
        self.h2 = 0.018 * np.exp(make.normal(0.0, 0.3, len(wheels))) * shape
        self.h3 = 0.028 * np.exp(make.normal(0.0, 0.3, len(wheels))) * shape
        # each key's nine contacts: when in the key's travel each meets its busbar, how often it bounces
        self.order = make.uniform(0.0, 1.0, (128, 9))
        self.bouncy = make.uniform(0.0, 1.0, (128, 9))
        # the rotary speaker's belts and motors
        belt = np.exp(make.normal(0.0, 0.03, 4))
        self.speeds = np.array([0.8, 6.7, 0.7, 5.7]) * belt
        self.times = np.array([0.33, 0.8, 1.3, 3.2]) * np.exp(make.normal(0.0, 0.08, 4))

    def plan(self, notes):
        """Each note's key, registration and rotor speed, as the names on the notes set them."""
        ordered = sorted(notes, key=lambda n: (n.start, n.pitch))
        current, fast = "", False
        plan = []
        speed_changes = []
        for note in ordered:
            words = str(note.art).replace("+", " ").split()
            for word in words:
                if word in REGISTRATIONS or (len(word) == 9 and word.isdigit()):
                    current = word
                elif word == "default":
                    current = ""
                elif word in ("fast", "slow"):
                    if (word == "fast") != fast or not speed_changes:
                        speed_changes.append((note.start, word == "fast"))
                    fast = word == "fast"
            key = int(round(_fold(float(note.pitch), *MANUAL)))
            plan.append((note, key, current))
        return plan, speed_changes

    def contacts(self, plan, rng: np.random.Generator, click: bool = True):
        """The busbar contacts' events (sample, wheel index, drawbar gain, percussion gain) and the
        percussion's triggers (samples)."""
        sr = self.sr
        ev = []
        triggers = []
        held_until = -1.0  # when the last key held so far rises
        for note, key, name in plan:
            reg = registration(name, self.brightness)
            if note.dur <= 0.0:
                continue
            gains = [drawbar_gain(n) for n in reg.drawbars]
            perc_wheel, perc_gain = -1, 0.0
            if reg.percussion:
                harmonic, decay, volume = reg.percussion.split()
                gains[8] = 0.0  # the percussion takes the 1' busbar
                if volume == "normal":
                    gains = [g * 10 ** (-3.0 / 20.0) for g in gains]
                perc_wheel = wheel_for(key, 12 if harmonic == "2nd" else 19)
                perc_gain = PERC_LEVEL[volume]
                # single trigger: only a key pressed with every other key up sets the envelope off
                if held_until <= note.start + 1e-9:
                    triggers.append((note.start, np.exp(-1.0 / (PERC_TAU[decay] * sr))))
            held_until = max(held_until, note.start + note.dur)
            travel = rng.uniform(1.5e-3, 4.5e-3)  # how long the key takes to pass its nine contacts
            smooth = int(0.004 * sr)
            for d in range(9):
                pg = perc_gain if (d == 8 and perc_wheel >= 0) else 0.0
                if gains[d] <= 0.0 and pg <= 0.0:
                    continue
                wheel = wheel_for(key, OFFSETS[d]) if d < 8 or pg == 0.0 else perc_wheel
                if pg > 0.0:
                    g_main, g_perc = 0.0, pg * self.level[wheel - FIRST_WHEEL]
                else:
                    g_main, g_perc = gains[d] * self.level[wheel - FIRST_WHEEL], 0.0
                w = wheel - FIRST_WHEEL
                if not click:  # a key without contacts: each footage faded in and out over 4 ms (for tests)
                    ev.append((note.start, w, g_main, g_perc, smooth))
                    ev.append((note.start + note.dur, w, -g_main, -g_perc, smooth))
                    continue
                on = note.start + travel * self.order[key, d] + rng.uniform(0.0, 2e-4)
                off = note.start + note.dur + travel * 0.6 * (1.0 - self.order[key, d])
                ev.append((on, w, g_main, g_perc, 1))
                # the contact chatters as its wire wipes onto the busbar, for a millisecond or two (a worn,
                # dirty one more): a burst of breaks tens of microseconds long
                chatter = self.bouncy[key, d] * (0.5 + self.wear)
                t = on
                for _ in range(min(2 + rng.poisson(2.0 + 6.0 * chatter), 14)):
                    t_open = t + rng.uniform(0.03e-3, 0.3e-3)
                    t = t_open + rng.uniform(0.01e-3, 0.09e-3)
                    ev.append((t_open, w, -g_main, -g_perc, 1))
                    ev.append((t, w, g_main, g_perc, 1))
                # it leaves more cleanly: its resistance rises over a fraction of a millisecond as it lifts
                ev.append((off, w, -g_main, -g_perc, int(rng.uniform(0.3e-3, 1.0e-3) * sr)))
        ev.sort(key=lambda e: e[0])
        if ev:
            times = np.array([e[0] for e in ev])
            ev_t = np.round(times * sr).astype(np.int64)
            ev_w = np.array([e[1] for e in ev], dtype=np.int64)
            ev_main = np.array([e[2] for e in ev])
            ev_perc = np.array([e[3] for e in ev])
            ev_ramp = np.array([e[4] for e in ev], dtype=np.int64)
        else:
            ev_t = np.zeros(0, dtype=np.int64)
            ev_w = np.zeros(0, dtype=np.int64)
            ev_main = np.zeros(0)
            ev_perc = np.zeros(0)
            ev_ramp = np.zeros(0, dtype=np.int64)
        trig = np.array([int(round(t * sr)) for t, _ in triggers], dtype=np.int64)
        trig_decay = np.array([d for _, d in triggers], dtype=np.float64)
        return ev_t, ev_w, ev_main, ev_perc, ev_ramp, trig, trig_decay

    def generator(self, plan, length: int, rng: np.random.Generator, click: bool = True):
        """The wheels through the contacts and drawbars: (drawbars' signal, percussion's signal)."""
        phases = rng.uniform(0.0, 2.0 * np.pi, len(self.freqs))  # wherever the wheels are when the part starts
        ev_t, ev_w, ev_main, ev_perc, ev_ramp, trig, trig_decay = self.contacts(plan, rng, click)
        return _generator(length, float(self.sr), self.freqs, phases, self.h2, self.h3, ev_t, ev_w, ev_main,
                          ev_perc, ev_ramp, trig, trig_decay)

    def scanner(self, x: np.ndarray, plan, rng: np.random.Generator) -> np.ndarray:
        """The vibrato and chorus, set by each registration from the note that names it."""
        sr = self.sr
        seg_t, seg_depth, seg_wet, seg_dry = [], [], [], []
        last = None
        for note, key, name in plan:
            mode = registration(name, self.brightness).scanner
            if mode == last:
                continue
            cents = SCANNER_CENTS[mode]
            depth = cents / 1731.234 * sr / (4.0 * SCANNER_HZ)  # the delay's sweep each way, in samples
            wet, dry = (0.0, 1.0) if not mode else ((1.0, 0.0) if mode[0] == "V" else (0.5, 0.5))
            seg_t.append(0 if last is None else int(round(note.start * sr)))  # the first is set before playing
            last = mode
            seg_depth.append(depth)
            seg_wet.append(wet)
            seg_dry.append(dry)
        order = np.argsort(np.array(seg_t), kind="stable")
        lp = 1.0 - np.exp(-2.0 * np.pi * 6000.0 / sr)
        return _scanner(x, float(sr), np.array(seg_t, dtype=np.int64)[order], np.array(seg_depth)[order],
                        np.array(seg_wet)[order], np.array(seg_dry)[order], rng.uniform(0.0, 1.0), lp)

    def swell(self, plan) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
        """Where the foot puts the swell pedal: each chord's velocity (the notes starting within 30 ms of
        its first), from its first note on; and how far the player eases it back for a bigger
        registration (a registration twice as powerful is played 1.2 dB further back, so pulling out every
        drawbar is louder than the house sound, but not by 5.5 dB). Returns the events' samples, pedal
        positions and gains, and where the pedal and gain start."""
        sr = self.sr
        reference = _energy(registration("", 0.5))
        ev_t, ev_s, ev_g = [], [], []
        i = 0
        while i < len(plan):
            start = plan[i][0].start
            j = i
            while j < len(plan) and plan[j][0].start - start < 0.03:
                j += 1
            reg = registration(plan[i][2], self.brightness)
            ev_t.append(int(round(start * sr)))
            ev_s.append(float(np.clip(np.mean([plan[k][0].vel for k in range(i, j)]), 0.0, 1.0)))
            ev_g.append(float((reference / max(_energy(reg), 1e-6)) ** 0.2))
            i = j
        return (np.array(ev_t, dtype=np.int64), np.array(ev_s), np.array(ev_g), (ev_s[0] if ev_s else 0.6),
                (ev_g[0] if ev_g else 1.0))

    def speaker(self, y: np.ndarray, speed_changes, first: float, rng: np.random.Generator) -> np.ndarray:
        """The rotary speaker, its rotors switched as the notes say: (n, 2), its two microphones."""
        sr = self.sr
        ev_t = np.array([int(round(t * sr)) for t, _ in speed_changes], dtype=np.int64)
        ev_fast = np.array([f for _, f in speed_changes], dtype=np.bool_)
        fast0 = bool(speed_changes and speed_changes[0][1] and speed_changes[0][0] <= first + 1e-9)
        horn = np.array([0.0065 * sr / (2.0 * np.pi * self.speeds[1]), 0.45, 0.15, 0.0011 * sr])
        drum = np.array([0.0013 * sr / (2.0 * np.pi * self.speeds[3]), 0.6, 0.1, 0.0009 * sr])
        angles = rng.uniform(0.0, 2.0 * np.pi, 2)
        return _rotors(y, float(sr), ev_t, ev_fast, fast0, self.speeds, self.times, horn, drum, MICS, angles,
                       _sos(800.0, "lowpass", sr), _sos(800.0, "highpass", sr), _sos(7500.0, "lowpass", sr),
                       _sos(35.0, "highpass", sr))

    def render(self, notes, length: int, rng: np.random.Generator) -> np.ndarray:
        sr = self.sr
        plan, speed_changes = self.plan(notes)
        main, perc = self.generator(plan, length, rng)
        y = self.scanner(main, plan, rng) + perc
        y = expression(y, sr, self.swell(plan))
        # the amplifier's tubes: the registrations' drive, and more of it the fuller the swell
        drive = float(np.mean([registration(name, self.brightness).drive for _, _, name in plan])) if plan else 0.4
        y = tubes(y, drive)
        return self.speaker(y, speed_changes, plan[0][0].start if plan else 0.0, rng)


MICS = np.array([-1.2, 1.2])  # the rotary speaker's two microphones, either side of the cabinet (radians)
TUBE_GAIN = 0.065


def _sos(freq: float, kind: str, sr: int) -> np.ndarray:
    """One second-order Butterworth section: (b0, b1, b2, 1, a1, a2)."""
    return np.ascontiguousarray(butter(2, freq, btype=kind, fs=sr, output="sos")[0])


def tubes(y: np.ndarray, drive: float) -> np.ndarray:
    """The amplifier's tubes: an asymmetric soft clip, even harmonics as well as odd. The input, scaled by
    the drive and biased, goes through 1.5 x - 0.5 x^3 inside ±1 and flat beyond (it meets the flat with
    zero slope): a cubic, so its harmonics stop at the 3rd and nothing folds back below 22 kHz for
    anything the organ plays, until a very loud full organ reaches the knee."""
    k = TUBE_GAIN * (0.6 + 0.8 * drive)
    b = 0.12
    x = np.clip(k * y + b, -1.0, 1.0)
    p = x * (1.5 - 0.5 * x * x)
    return (p - b * (1.5 - 0.5 * b * b)) / (k * 1.5 * (1.0 - b * b))


# --- the harmonium ----------------------------------------------------------------------------------

SPEAK_TABLE = ((41, 0.06), (53, 0.045), (65, 0.035), (77, 0.026), (89, 0.02))  # s for a reed to speak


class Harmonium:
    """One machine's harmonium: its reeds' tuning, its celeste, its pumping (from `make`)."""

    def __init__(self, sr: int, make: np.random.Generator, settings: dict):
        self.sr = sr
        self.brightness, self.wear, self.ornament, self.size = _settings(settings)
        wear = self.wear
        self.cents = make.normal(0.0, 0.3 + 4.0 * wear, 128)
        self.celeste = (3.0 + 5.0 * wear) * np.exp(make.normal(0.0, 0.2, 128))  # cents sharp, the beating rank
        self.pump = make.uniform(1.6, 2.6)  # seconds per stroke of the pumping hand
        self.box_seed = int(make.integers(1 << 30))
        self.tables: dict = {}

    def wave(self, key: int, rank: int, freq: float, bright: float) -> np.ndarray:
        """One reed's tone (a period, band-limited for its pitch): each reed of each machine its own."""
        q = round(bright * 20.0) / 20.0
        wave = self.tables.get((key, rank, q))
        if wave is None:
            wave = reed.table(freq, self.sr, np.random.default_rng([self.box_seed, key, rank]), q)
            wave = wave / (np.sqrt(2.0 * np.mean(wave**2)) + 1e-12)  # by its power, not its peak: ranks mix as voiced
            self.tables[(key, rank, q)] = wave
        return wave

    def pressure(self, length: int, rng: np.random.Generator) -> np.ndarray:
        """The bellows' pressure (1 on average): each stroke pushes it up a few percent, and it sags between."""
        t = np.arange(length) / self.sr
        phase = (t / self.pump + rng.uniform(0.0, 1.0)) % 1.0
        stroke = np.where(phase < 0.25, np.sin(np.pi * phase / 0.5), np.exp(-(phase - 0.25) * 2.2))
        return 1.0 + 0.05 * (stroke - np.mean(stroke))

    def render(self, notes, length: int, rng: np.random.Generator) -> np.ndarray:
        sr = self.sr
        out = np.zeros(length)
        air = np.zeros(length)
        swells = []
        press = self.pressure(length, rng)
        lo, hi = SPEC["harmonium"]["register"]
        for note in sorted(notes, key=lambda n: (n.start, n.pitch)):
            if note.dur <= 0.0 or note.start * sr >= length:
                continue
            if "swell" in str(note.art).split():
                swells.append(note)
                continue
            m = _fold(float(note.pitch), lo, hi)
            key = int(round(m))
            i0 = int(round(note.start * sr))
            speak = float(np.interp(m, *zip(*SPEAK_TABLE))) * np.exp(rng.normal(0.0, 0.1))
            release = 0.035
            i1 = min(length, i0 + int(round((note.dur + 5.0 * release) * sr)))
            n = i1 - i0
            if n < 4:
                continue
            t = np.arange(n) / sr
            # the reed speaks after the air reaches it, then settles; the pallet closes and it stops
            rise = np.clip((t - 0.2 * speak) / (0.8 * speak), 0.0, 1.0)
            env = (0.5 - 0.5 * np.cos(np.pi * rise)) ** 1.5
            env *= np.where(t < note.dur, 1.0, np.exp(-(t - note.dur) / release))
            env *= touch.gain(float(np.clip(note.vel, 0.0, 1.0)), 16.0) * press[i0:i1] ** 0.8
            f = _hz(m + self.cents[key] / 100.0)
            # the pressure pulls the pitch a hair flat as it rises, as it does a free reed's
            bend = 2.0 ** (-8.0 * (press[i0:i1] - 1.0) / 1200.0)
            bright = float(np.clip(0.35 + 0.4 * self.brightness + 0.25 * (note.vel - 0.5), 0.0, 1.0))
            ranks = [(0, f, 0.5), (1, f * 2.0 ** (self.celeste[key] / 1200.0), 0.24)]
            if self.brightness > 0.05:
                ranks.append((2, 2.0 * f * 2.0 ** (self.cents[min(127, key + 12)] / 1200.0), 0.5 * self.brightness))
            for rank, freq, gain in ranks:
                if freq >= 0.45 * sr:
                    continue
                wave = self.wave(key, rank, _hz(m + 12.0 * (rank == 2)), bright)
                reed._read(wave, freq * bend / sr, env * gain, out, i0, rng.random())
            air[i0:i1] += env
        if swells:
            drone = reed.drone(swells, sr, length, rng, brightness=self.brightness, wear=self.wear)
            out += drone * 1.4
        # air hissing past the reeds, as much as is blowing through them
        hiss = sosfilt(butter(2, [300.0, 2500.0], btype="bandpass", fs=sr, output="sos"), rng.standard_normal(length))
        out += hiss * air * 0.012 * (1.0 + 2.0 * self.wear)
        ir = body.impulse_response(body.REED_BOX, sr, seed=self.box_seed, size=self.size)
        return body.resonate(out, ir)


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """An organ or harmonium part: stereo, dry, `length` samples, before placement and level."""
    if name == "organ":
        return Organ(sr, make, settings or {}).render(notes, length, rng)
    if name == "harmonium":
        return Harmonium(sr, make, settings or {}).render(notes, length, rng)
    raise ValueError(f"no such instrument: {name}")
