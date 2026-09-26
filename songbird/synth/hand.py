"""Body percussion: hands clapping, and feet stomping on a wooden floor.

Claps. Two hands meeting squeeze the air out from between them in a burst
of a millisecond or so, and the pocket of air between the palms rings as a
resonator whose pitch depends on how the hands are held: cupped hands ring
low (about 0.7 kHz), flat palms high and broad (2 kHz and more), which is
most of what tells one person's clap from another's (Repp, "The sound of
two hands clapping", JASA 81(4), 1987; Peltola, Erkut, Cook and Valimaki,
"Synthesis of hand clapping sounds", IEEE TASLP 15(3), 2007, whose
resonators sit between about 0.7 and 2.1 kHz with bandwidths of a few
hundred hertz). The hands don't meet all at once (fingers, palm, heel of the
hand), so a clap is two to four bursts over a few milliseconds, each through
that resonance, with a broadband crack (more of it from flat hands) and a
soft thump of the palms' flesh. A group is three to eight people, each with
their own hands, strength, place in the room and habit of timing; clapping
along to a band, their onsets spread over 10 to 25 ms (Repp, "Sensorimotor
synchronization", Psychonomic Bulletin & Review 12(6), 2005: taps wander
by about 10 ms around the beat), more for a looser, more worn group, which
now and then drops a clap. The first hands meet on the note's time and the
rest follow, since the notes carry the part's own timing and nothing may
sound before them.

Stomps. A foot comes down on a wooden stage or porch: the heel lands first,
a hard edge for a millisecond, then the leg's weight through the sole over
several (the softer and longer the contact, the more of the energy goes low),
and the sole slaps down after it. The floor booms: boards on joists over an
air space, a big stiff plate whose modes (the lowest at 45 to 75 Hz, a
handful more up to 400) ring for a few tenths of a second, with the air under
it (the cavity's lengthwise and crosswise modes) and the frame holding it up
along. The modes that change the floor's volume (odd in both directions)
radiate best; the others mostly cancel themselves (Fletcher and Rossing, The
Physics of Musical Instruments, on radiation from plates). Under each foot,
the board it lands on knocks: a plank between two joists is a clamped beam, modes at 1, 2.76, 5.40,
8.93 and 13.3 times the first, 180 to 320 Hz here, gone in a tenth of a
second. Two to five people stomp together, each on their own board and place
on the floor, which rings for all of them at once (the struck bank adds
their strokes with their phases). A worn floor has a loose board that knocks
again just after.

Every stroke is levelled by its first 30 ms (rattle.py), so the group, its
size and its hands don't move the level: a single person (clap-solo,
stomp-solo) sits 3 dB under the group.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.signal import butter, lfilter, sosfilt

from . import struck
from .rattle import add, burst, contact, early_power, modal_weights, onsets, pan, vel_gain

SPEC = {
    "claps": dict(
        family="percussion", role="percussion", register=None, place=(-0.2, 0.5), level=1.0, poly=True,
        articulations={
            "clap": "the group claps together (3 to 8 people, by maker)",
            "clap-solo": "one person claps, 3 dB under the group",
            "snap": "finger snaps: one or two people, 3 dB under the group's claps",
        },
        about="hand claps: a small group, each person's cupped or flat hands their own resonance, "
              "their onsets spread 10 to 25 ms",
    ),
    "stomps": dict(
        family="percussion", role="percussion", register=None, place=(0.0, 0.3), level=0.76, poly=True,
        articulations={
            "stomp": "two to five people stomp together on a wooden floor (by maker)",
            "stomp-solo": "one person stomps, 3 dB under the group",
        },
        about="feet on a wooden stage: the heel's knock, the floor's boom (35 to 250 Hz, a few tenths of a "
              "second), the boards and the sole's slap",
    ),
}

EARLY = 0.25  # a stroke's early RMS (K-weighted, first 30 ms) at full velocity, before the stem's level
SOLO = 10.0 ** (-3.0 / 20.0)  # one person against the group


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A part's dry stem, stereo (length, 2): see SPEC."""
    s = dict(settings or {})
    if name == "claps":
        return claps(notes, sr, length, rng, make, s)
    if name == "stomps":
        return stomps(notes, sr, length, rng, make, s)
    raise ValueError(f"hand.py plays claps and stomps, not {name}")


def _knobs(s: dict) -> tuple[float, float, float]:
    return (float(np.clip(s.get("brightness", 0.5), 0.0, 1.0)), float(np.clip(s.get("wear", 0.25), 0.0, 1.0)),
            float(np.clip(s.get("body", 1.0), 0.5, 2.0)))


def _playing(notes, length: int, sr: int):
    """The notes that start inside the part, in their order."""
    return [n for n in notes if 0 <= int(round(n.start * sr)) < length]


# --- claps ------------------------------------------------------------------------------------


CUPPED, FLAT = 700.0, 2400.0  # Hz: the pocket between the palms, cupped to flat


def _clappers(make: np.random.Generator, size: float) -> list[dict]:
    """The group, as its maker made it: each person's hands, strength, place and timing habit."""
    people = []
    for _ in range(int(make.integers(3, 9))):
        cup = float(make.beta(2.0, 2.0))  # 0 flat palms, 1 well cupped
        people.append(dict(
            cup=cup,
            fc=float(np.exp(np.log(FLAT) + cup * np.log(CUPPED / FLAT)) * np.exp(make.normal(0.0, 0.08))
                     / np.sqrt(size)),
            q=float(np.clip(5.0 + 2.5 * cup + make.normal(0.0, 0.6), 3.5, 9.0)),
            crack=0.06 + 0.24 * (1.0 - cup),  # the crack's energy against the pocket's: flat hands crack more
            thump=float(make.uniform(0.1, 0.3)),
            touches=int(make.integers(2, 5)),  # how many places the hands meet, habitually
            gain=float(10.0 ** (make.normal(0.0, 2.0) / 20.0)),
            lag=float(make.normal(0.0, 0.004)),  # early or late, habitually
            pan=float(make.uniform(-0.7, 0.7)),
            snap=float(2600.0 * np.exp(make.normal(0.0, 0.12)) / np.sqrt(size)),  # the pocket under a snapping finger
        ))
    return people


@lru_cache(maxsize=16)
def _crack_band(sr: int, top: float) -> np.ndarray:
    """The air's crack: above 1 kHz, falling 6 dB an octave past `top` and 18 past twice that (a jet of
    air from a gap that closes in a fraction of a millisecond has little above 10 kHz)."""
    return np.vstack([butter(2, 1000.0, btype="highpass", fs=sr, output="sos"),
                      butter(1, min(top, 0.45 * sr), fs=sr, output="sos"),
                      butter(2, min(2.0 * top, 0.45 * sr), fs=sr, output="sos")])


def _unit(x: np.ndarray) -> np.ndarray:
    return x / (np.sqrt(np.sum(x**2)) + 1e-30)


def _resonate(x: np.ndarray, fc: float, q: float, sr: int) -> np.ndarray:
    """A two-pole resonance at fc with zeros at DC and Nyquist, unity at its peak."""
    r = np.exp(-np.pi * fc / q / sr)
    g = 0.5 * (1.0 - r * r)
    return lfilter([g, 0.0, -g], [1.0, -2.0 * r * np.cos(2.0 * np.pi * fc / sr), r * r], x)


def _clap(p: dict, vel: float, sr: int, rng: np.random.Generator, bright: float) -> np.ndarray:
    """One person's clap, at unit early loudness."""
    n = int(0.045 * sr)
    exc = np.zeros(n)
    tau = (0.8 - 0.55 * vel) * 1e-3 * (1.25 - 0.5 * bright) * np.exp(rng.normal(0.0, 0.15))  # harder: shorter
    t, amp = 0.0, 1.0
    for _ in range(max(1, p["touches"] + int(rng.integers(-1, 2)))):
        add(exc, amp * burst(rng, tau, sr), int(t * sr))
        t += rng.uniform(0.3, 1.3) * 1e-3
        amp *= rng.uniform(0.35, 0.95)
    y = _unit(_resonate(exc, p["fc"] * np.exp(rng.normal(0.0, 0.04)), p["q"] * np.exp(rng.normal(0.0, 0.08)), sr))
    # the crack's energy against the pocket's: hands brought together harder squeeze the air out faster
    crack = p["crack"] * (0.25 + 1.5 * vel**2) * (0.6 + 0.8 * bright)
    y += np.sqrt(crack) * _unit(sosfilt(_crack_band(sr, 3000.0 + 3000.0 * bright), exc))
    # the palms' flesh: a soft push of a few milliseconds (its derivative, as the air hears it)
    m = int(rng.uniform(2.0, 3.5) * 1e-3 * sr)
    y[:m] += p["thump"] * np.max(np.abs(y)) * np.cos(np.pi * np.arange(m) / m) * np.hanning(m)
    y[-int(0.005 * sr):] *= np.linspace(1.0, 0.0, int(0.005 * sr)) ** 2  # the pocket's last ring, let go
    return y / np.sqrt(early_power(y, sr) + 1e-30)


def _snap(p: dict, vel: float, sr: int, rng: np.random.Generator, bright: float) -> np.ndarray:
    """A finger snap: the middle finger knocking into the palm, one short burst into a small pocket, at unit loudness."""
    n = int(0.03 * sr)
    exc = np.zeros(n)
    tau = (0.3 - 0.12 * vel) * 1e-3 * (1.2 - 0.4 * bright)
    add(exc, burst(rng, tau, sr), 0)
    add(exc, rng.uniform(0.1, 0.3) * burst(rng, tau, sr), int(rng.uniform(0.2, 0.6) * 1e-3 * sr))
    y = _unit(_resonate(exc, p["snap"] * np.exp(rng.normal(0.0, 0.05)), 3.5 * np.exp(rng.normal(0.0, 0.1)), sr))
    y += np.sqrt(0.3 + 0.3 * bright) * _unit(sosfilt(_crack_band(sr, 4000.0 + 4000.0 * bright), exc))
    y[-int(0.004 * sr):] *= np.linspace(1.0, 0.0, int(0.004 * sr)) ** 2
    return y / np.sqrt(early_power(y, sr) + 1e-30)


def claps(notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
          s: dict) -> np.ndarray:
    bright, wear, size = _knobs(s)
    people = _clappers(make, size)
    group = np.sqrt(sum(p["gain"] ** 2 for p in people))
    snappers = people[: 1 + int(len(people) > 4)]
    out = np.zeros((length, 2))
    jitter = 0.003 + 0.008 * wear  # seconds: a clap's own scatter about the person's habit
    for note in _playing(notes, length, sr):
        art = note.art if note.art in SPEC["claps"]["articulations"] else "clap"
        if art == "clap":
            who, norm = people, 1.0 / group
        else:  # one person, or the one or two who snap, 3 dB under the group
            who = people[:1] if art == "clap-solo" else snappers
            norm = SOLO / np.sqrt(sum(p["gain"] ** 2 for p in who))
        # the first hands meet on the note, the others over the next 10 to 25 ms
        for p, offset in zip(who, onsets(rng, [p["lag"] for p in who], jitter)):
            if art == "clap" and rng.random() < 0.01 + 0.05 * wear:
                continue  # someone misses one
            vel = float(np.clip(note.vel * 10.0 ** (rng.normal(0.0, 1.2) / 20.0), 0.0, 1.0))
            y = (_snap if art == "snap" else _clap)(p, vel, sr, rng, bright)
            y *= EARLY * vel_gain(vel) * p["gain"] * norm
            add(out, y[:, None] * pan(p["pan"])[None, :], int(round((note.start + offset) * sr)))
    return out


# --- stomps -----------------------------------------------------------------------------------


BEAM = np.array([1.0, 2.756, 5.404, 8.933, 13.345])  # a clamped-clamped beam's modes against its first


def _floor(make: np.random.Generator, size: float) -> dict:
    """A wooden stage: boards on joists over an air space. Its modes (an orthotropic plate's, simply
    supported: stiff along the joists, softer across them), what each radiates, the air under it
    and the frame holding it up."""
    f0 = 58.0 * 2.0 ** make.uniform(-0.35, 0.35) / size  # 45 to 74 Hz
    aspect = make.uniform(1.3, 2.2)  # the stage's length over its depth
    across = make.uniform(0.05, 0.25)  # the floor's stiffness across the joists against along them
    twist = np.sqrt(across)
    base = 1.0 + 2.0 * twist * aspect**2 + across * aspect**4
    modes = []
    for m in range(1, 10):
        for n in range(1, 10):
            f = f0 * np.sqrt((m**4 + 2.0 * twist * (m * n * aspect) ** 2 + across * (n * aspect) ** 4) / base)
            if f < 400.0:
                modes.append((m, n, f))
    m_, n_, f_ = (np.array(v) for v in zip(*modes))
    freqs = f_ * np.exp(make.normal(0.0, 0.05, len(f_)))  # nails, joists, knots
    radiate = np.where((m_ % 2 == 1) & (n_ % 2 == 1), 1.0, np.where((m_ % 2 == 1) | (n_ % 2 == 1), 0.4, 0.15))
    t60 = 0.5 * (f0 / freqs) ** 0.5 * np.exp(make.normal(0.0, 0.15, len(f_)))
    span = make.uniform(2.5, 4.5) * size  # metres: the air space's length, and its depth
    air = np.array([343.0 / (2.0 * span), 343.0 / (2.0 * span / aspect)])
    frame = np.exp(make.uniform(np.log(1.2 * f0), np.log(400.0), 6))  # joists, legs and bracing
    return dict(f0=f0, m=m_, n=n_, freqs=freqs, radiate=radiate, t60=t60, air=air,
                air_t60=np.array([0.4, 0.3]) * np.exp(make.normal(0.0, 0.1, 2)),
                air_gain=float(make.uniform(0.3, 0.7)), frame=frame,
                frame_t60=0.25 * (f0 / frame) ** 0.3 * np.exp(make.normal(0.0, 0.2, len(frame))),
                knock=float(make.uniform(0.1, 0.18)), loose=float(make.uniform(0.0, 1.0)))


def _stompers(make: np.random.Generator, size: float) -> list[dict]:
    people = []
    for _ in range(int(make.integers(2, 6))):
        people.append(dict(
            x=float(make.uniform(0.25, 0.75)), y=float(make.uniform(0.25, 0.75)),  # where on the floor
            board=float(240.0 * 2.0 ** make.uniform(-0.4, 0.4) / np.sqrt(size)),  # the board underfoot's first mode
            spot=float(make.uniform(0.2, 0.8)),  # where along that board
            heel=float(make.uniform(0.0, 1.0)),  # a soft sneaker (0) to a hard boot heel (1)
            gain=float(10.0 ** (make.normal(0.0, 2.0) / 20.0)),
            lag=float(make.normal(0.0, 0.005)),
            pan=float(make.uniform(-0.6, 0.6)),
        ))
    return people


@lru_cache(maxsize=4)
def _sole_band(sr: int) -> np.ndarray:
    return butter(2, [700.0, 5000.0], btype="bandpass", fs=sr, output="sos")


@lru_cache(maxsize=4)
def _dc(sr: int) -> np.ndarray:
    return butter(2, 25.0, btype="highpass", fs=sr, output="sos")


BOOM = 0.1  # seconds: a stomp is levelled by its first tenth of a second (its boom is slow to speak)


def stomps(notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           s: dict) -> np.ndarray:
    bright, wear, size = _knobs(s)
    floor = _floor(make, size)
    people = _stompers(make, size)
    kf, ka, kx = len(floor["freqs"]), len(floor["air"]), len(floor["frame"])
    shared = kf + ka + kx  # the modes everyone on the floor shares
    boards = [p["board"] * BEAM * np.exp(make.normal(0.0, 0.03, len(BEAM))) for p in people]
    freqs = np.concatenate([floor["freqs"], floor["air"], floor["frame"], *boards])
    t60s = np.concatenate([floor["t60"], floor["air_t60"], floor["frame_t60"],
                           *[0.15 * (b[0] / b) ** 0.5 for b in boards]])
    mix = np.ones((len(freqs), 2))  # the floor booms in the middle; each board knocks where its stomper stands
    for i, p in enumerate(people):
        mix[shared + i * len(BEAM): shared + (i + 1) * len(BEAM)] = pan(p["pan"])
    heard = modal_weights(freqs, t60s, sr, BOOM, np.sqrt((mix**2).sum(axis=1)))
    omega = 2.0 * np.pi * freqs[:shared]
    out = np.zeros((length, 2))
    times, rows = [], []
    jitter = 0.003 + 0.009 * wear
    for note in _playing(notes, length, sr):
        who = people[:1] if note.art == "stomp-solo" else people
        feet = []
        offsets = onsets(rng, [p["lag"] for p in who], jitter)  # the first foot lands on the note
        for i, p in enumerate(who):
            vel = float(np.clip(note.vel * 10.0 ** (rng.normal(0.0, 1.2) / 20.0), 0.0, 1.0))
            t = note.start + offsets[i]
            # the heel: its hard edge for about a millisecond, then the leg's weight through the sole
            weight = (8.0 - 4.0 * vel) * 1e-3 * (1.2 - 0.4 * bright) * (1.15 - 0.3 * p["heel"])
            edge = (1.3 - 0.6 * p["heel"]) * 1e-3 * (1.2 - 0.4 * vel)
            push = contact(freqs, weight) + (0.05 + 0.15 * p["heel"]) * (0.4 + vel) * contact(freqs, edge)
            x = np.clip(p["x"] + rng.normal(0.0, 0.03), 0.02, 0.98)
            y = np.clip(p["y"] + rng.normal(0.0, 0.03), 0.02, 0.98)
            amp = np.zeros(len(freqs))
            amp[:kf] = np.sin(floor["m"] * np.pi * x) * np.sin(floor["n"] * np.pi * y) * floor["radiate"]
            amp[kf:kf + ka] = floor["air_gain"] * np.cos(np.pi * np.array([x, y]))
            amp[kf + ka:shared] = 0.3 * rng.standard_normal(kx)
            amp[:shared] *= freqs[:shared] / floor["f0"]  # a floor radiates its velocity's rate of change
            b = slice(shared + i * len(BEAM), shared + (i + 1) * len(BEAM))
            along = np.clip(p["spot"] + rng.normal(0.0, 0.05), 0.05, 0.95)
            amp[b] = floor["knock"] * np.sin(np.arange(1, len(BEAM) + 1) * np.pi * along) * BEAM**0.5
            amp *= push * rng.uniform(0.85, 1.15, len(freqs)) * vel_gain(vel) / vel_gain(max(note.vel, 1e-3))
            # the sole slapping down after the heel: its energy 14 to 21 dB under the stroke's
            delay = int(rng.uniform(2.0, 10.0) * 1e-3 * sr)
            sole = sosfilt(_sole_band(sr), burst(rng, (0.4 + 1.0 * (1.0 - p["heel"])) * 1e-3, sr, int(0.02 * sr)))
            ratio = (0.01 + 0.03 * p["heel"]) * (0.6 + 0.8 * bright) * (0.4 + 0.6 * vel)
            sole *= np.sqrt(ratio * float(amp**2 @ heard) / (2.0 * early_power(np.pad(sole, (delay, 0)), sr, BOOM)))
            feet.append((p, t, amp * p["gain"], sole * p["gain"], delay, b))
        # the group levelled as one stroke: the floor's modes add with each foot's phase, boards and soles don't
        t0 = min(f[1] for f in feet)
        floor_sum = sum(f[2][:shared] * np.exp(-1j * omega * (f[1] - t0)) for f in feet)
        power = float(np.abs(floor_sum) ** 2 @ heard[:shared])
        for p, t, amp, sole, delay, b in feet:
            power += float(amp[b] ** 2 @ heard[b]) + early_power(np.pad(sole, (delay, 0)), sr, BOOM) * 2.0
        scale = EARLY * vel_gain(note.vel) * (SOLO if note.art == "stomp-solo" else 1.0) / np.sqrt(power + 1e-30)
        for p, t, amp, sole, delay, b in feet:
            times.append(t)
            rows.append(amp * scale)
            add(out, (sole * scale)[:, None] * pan(p["pan"])[None, :], int(round(t * sr)) + delay)
            if rng.random() < 0.6 * wear * floor["loose"]:  # a loose board knocks again as it settles
                times.append(t + rng.uniform(0.015, 0.04))
                knock = np.zeros(len(freqs))
                knock[b] = amp[b] * scale * rng.uniform(0.2, 0.45)
                rows.append(knock)
    if times:
        out += struck.ring(freqs, t60s, times, np.array(rows), sr, length, mix=mix)
    return sosfilt(_dc(sr), out, axis=0)
