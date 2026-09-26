"""Electric instruments: a solid-body electric guitar through a small valve amp, and an electric bass through a DI.

The guitar. Six steel strings on a solid body (standard tuning, 24 frets)
ring long: the body takes little of their energy, so a note's fundamental
falls 60 dB in 6 to 10 seconds in the middle of the neck, less high up, and
each partial dies faster by its frequency (b3 f^2), the top of the pick's
brightness gone in a second or two. A guitar's neck has its own dead spot
(a resonance that drinks one note's energy: H. Fleischer and T. Zwicker,
"Investigating dead spots of electric guitars", Acustica 85, 1999), each
maker's somewhere between G3 and C4. Each note's string is chosen as a
player's hand would (fretboard.py), and what reaches the amp is what the
magnetic pickup hears (its comb, its coil's resonance with the pots and
cable: amp.py): single coils near 4 kHz, humbuckers near 3, the player's
switch toward the neck for a warm sound and the bridge for a bright or driven
one.

The amp (amp.py) has three settings, one per name: "electric" clean, with a
modest spring reverb; "electric-crunch", the volume up so the second stage and
the power valves break up, the reverb off, the master down so it sits as loud
as the clean sound; "electric-tremolo", clean through the amp's tremolo
(a Fender's optical or a Vox-like bias tremolo by the maker, 4 to 7 Hz, locked
to the tempo when the band gives one, dipping the sound 11 to 16 dB). The three names are the same guitar and
the same amp on a machine (both drawn from its maker, whatever the name), so a
style that changes settings mid-song hears one rig. settings["amp"] may name a
setting ("clean", "crunch", "tremolo") or give a dict of {"setting", "drive"
0..1, "reverb" 0..1, "tremolo" depth 0..1, "rate" Hz}.

Articulations: "", "down" and "up" (pick strokes; notes struck together are
spread as a strum, low to high down and high to low up); "mute" (the palm on
the strings by the bridge: short and dark, the chug); "chop" (a fully muted
strum: a percussive scratch); "bend" (fretted a tone below and bent up to the
note in 100 to 200 ms); "slide" (picked two or three frets below, the finger
sliding up across the frets); "hammer" and "pull" (no pick: the ringing string
carries on at the new fret, with the finger's blow or pluck); "vibrato" (a
finger vibrato, bending up and back, its depth set by the ornament). Anything
else is a plain stroke.

The bass. Four long-scale (864 mm) roundwound strings: a long sustain whose
bright, zingy attack darkens within a fifth of a second (their damping grows
steeply with frequency), through a split-coil (P) or two single-coil (J)
pickups by the maker, straight into a DI: clean, with a touch of its preamp's
saturation. Articulations: "" (fingered: round), "pick" (brighter, with the
pick's click), "mute" (palm-muted, short), "slide" (slid into from two or three
frets below), "ghost" (a dead note: the left hand only touching the string).
"""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

import numpy as np
from scipy.signal import butter, oaconvolve, sosfilt

from ..score import Note
from ..theory import midi_to_hz
from . import amp, fretboard
from .fretboard import Strings
from .master import loudness

GUITAR_ARTS = {
    "": "a pick stroke (notes struck together are strummed, low to high)",
    "down": "a down stroke",
    "up": "an up stroke: the strum runs high to low",
    "mute": "palm-muted by the bridge: short, dark, the chug",
    "chop": "a fully muted strum: a percussive scratch",
    "bend": "bent up to the note from a tone below, in 100-200 ms",
    "slide": "picked two or three frets below and slid up to the note",
    "hammer": "a hammer-on: no pick, the ringing string carries on at the new fret",
    "pull": "a pull-off: no pick, the finger plucks as it lets go",
    "vibrato": "a finger vibrato, bending up and back; the ornament sets its depth",
}
BASS_ARTS = {
    "": "fingered: round",
    "pick": "played with a pick: brighter, with a click",
    "mute": "palm-muted: short and thumpy",
    "slide": "slid into from two or three frets below",
    "ghost": "a dead note: the fretting hand only touches the string",
}

SPEC = {
    "electric": dict(
        family="plucked", role="comping", register=(40, 88), place=(0.4, 0.6), level=0.224, poly=True,
        articulations=GUITAR_ARTS,
        about="a solid-body electric guitar through a small valve amp, clean, with a little spring reverb"),
    "electric-crunch": dict(
        family="plucked", role="comping", register=(40, 88), place=(0.4, 0.6), level=0.292, poly=True,
        articulations=GUITAR_ARTS,
        about="the same electric guitar with the amp turned up into crunch (its master volume down to match)"),
    "electric-tremolo": dict(
        family="plucked", role="comping", register=(40, 88), place=(0.4, 0.6), level=0.31, poly=True,
        articulations=GUITAR_ARTS,
        about="the same electric guitar, clean, through the amp's tremolo (locked to the tempo if there is one)"),
    "ebass": dict(
        family="bass", role="bass", register=(28, 60), place=(0.0, 0.0), level=0.217, poly=False,
        articulations=BASS_ARTS,
        about="an electric bass, long-scale roundwound strings, P or J pickups, through a DI"),
}

SETTING_OF = {"electric": "clean", "electric-crunch": "crunch", "electric-tremolo": "tremolo"}
EMF = 0.055  # volts at the pickup per unit of string velocity for a single coil: a strum peaks near 0.2 V
GUITAR_OUT = 2.7  # the stem's scale: the amp's output as the band's other stems are scaled
BASS_OUT = 3.0  # and the DI's
TUNING = (40.0, 45.0, 50.0, 55.0, 59.0, 64.0)  # E2 A2 D3 G3 B3 E4
BASS_TUNING = (28.0, 33.0, 38.0, 43.0)  # E1 A1 D2 G2
# each open string's inharmonicity B (pi^3 E d^4 / 64 T L^2 on its core, a third more for a winding): the
# wound strings' partials and the plain G's run sharp (the low E's 8th by 7 cents), the bass's far more
# (its E's 10th by a third of a semitone: the growl of a long, stiff roundwound string)
STIFFNESS = (1.2e-4, 6e-5, 3e-5, 1e-4, 4e-5, 1.3e-5)
BASS_STIFFNESS = (4e-4, 2e-4, 1e-4, 4e-5)


# --- the guitar and the amp, as a machine's maker built them ------------------------------------------


@lru_cache(maxsize=32)
def built(maker: int) -> dict:
    """Everything about the guitar and amp that doesn't change from song to song: drawn from the maker alone,
    so the three electric names are one rig on a machine."""
    g = np.random.default_rng([int(maker), 29, 4242])
    d: dict = {}
    d["humbucker"] = bool(g.random() < 0.45)
    d["scale"] = 0.628 if d["humbucker"] else 0.648
    d["lean"] = float(g.normal(0.0, 0.1))  # the player's taste for the neck or the bridge
    d["poles"] = tuple(g.normal(0.0, 1.0, 6))  # dB: each string's pole piece
    d["detune"] = tuple(g.standard_normal(6))  # each string's tuning error, scaled by wear
    d["cable"] = float(g.uniform(3.0, 6.0) * 100e-12)  # F: three to six metres of cable
    d["pick"] = float(g.uniform(0.12, 0.19))  # where the pick meets the open string
    d["tone_cap"] = 22e-9 if d["humbucker"] else float(g.choice([47e-9, 22e-9]))
    d["t60"] = float(g.uniform(6.0, 8.5))  # how long this guitar sustains at 220 Hz
    d["dead"] = (float(g.uniform(190.0, 262.0)), float(g.uniform(0.35, 0.6)))  # its dead spot: Hz, how much it drinks
    d["voicing"] = "fender" if g.random() < 0.6 else "marshall"
    d["knobs"] = (float(g.uniform(-0.1, 0.1)), float(g.uniform(0.35, 0.65)), float(g.uniform(-0.1, 0.1)))
    # how hard the player drives the second stage, clean and crunched: the volume plus the rig's own heat
    # (heat()), so a hot humbucker into a Marshall's stack sits lower on the knob than a single coil into a
    # Fender's for the same sound; a player dials the sound, not the knob
    d["clean"] = float(g.uniform(-38.0, -33.0))
    d["crunch"] = float(g.uniform(-17.0, -11.0))
    d["headroom"] = float(g.uniform(38.0, 52.0))
    d["sag"] = float(g.uniform(0.08, 0.18))
    d["tilt"] = float(g.uniform(0.0, 0.06))
    # the power valves: a pair with little feedback, or (some Fenders) a blackface's with negative feedback
    d["knee"] = 2 if (d["voicing"] == "marshall" or g.random() < 0.6) else 3
    d["reverb"] = float(g.uniform(0.12, 0.22))
    first = float(g.uniform(0.028, 0.034))
    springs = (first, first * float(g.uniform(1.12, 1.3))) + ((first * 1.45,) if g.random() < 0.3 else ())
    d["tank"] = amp.Tank(traversals=springs, t60=float(g.uniform(2.2, 3.2)), coef=float(g.uniform(0.58, 0.68)),
                         stretch=int(g.choice([5, 6])), seed=int(g.integers(1 << 30)))
    # the tremolo as players set it to be heard: a Fender's photocell dips the sound 13 to 19 dB, a bias
    # tremolo (it can only swing the power valves' bias so far) 11 to 16
    kind = "optical" if d["voicing"] == "fender" else "bias"
    deep = (0.78, 0.89) if kind == "optical" else (0.72, 0.84)
    d["tremolo"] = (kind, float(g.uniform(4.5, 6.5)), float(g.uniform(*deep)))
    ten = g.random() < 0.4
    d["cabinet"] = amp.Cabinet(
        fs=float(g.uniform(92.0, 110.0) if ten else g.uniform(75.0, 90.0)), q=float(g.uniform(1.3, 2.0)),
        presence=(float(g.uniform(2200.0, 3500.0)), float(g.uniform(3.0, 7.0)), float(g.uniform(1.0, 1.6))),
        rolloff=float(g.uniform(5500.0, 6500.0) if ten else g.uniform(4800.0, 5800.0)),
        order=int(g.choice([2, 4])) if ten else 4, back=float(g.uniform(2.0, 4.0)), breakup=3.5,
        # the reflections a close microphone also hears (the floor, the baffle's edge): 12 to 20 dB down
        mics=((float(g.uniform(0.00015, 0.00035)), float(g.uniform(0.1, 0.18)), 0.0),
              (float(g.uniform(0.0008, 0.0016)), float(g.uniform(0.15, 0.25)), float(g.uniform(-7.0, -3.0)))),
        seed=int(g.integers(1 << 30)))
    # the open back cancels below the cone's resonance, leaving its hump standing
    d["cabinet"] = replace(d["cabinet"], back_at=d["cabinet"].fs)
    return d


def _setting(name: str, s: dict) -> tuple[str, dict]:
    """The amp setting a part asks for (its name, or settings["amp"]) and any knob overrides."""
    setting = SETTING_OF.get(name, "clean")
    option = s.get("amp")
    extra: dict = {}
    if isinstance(option, str) and option in ("clean", "crunch", "tremolo"):
        setting = option
    elif isinstance(option, dict):
        if option.get("setting") in ("clean", "crunch", "tremolo"):
            setting = option["setting"]
        extra = {k: option[k] for k in ("drive", "reverb", "tremolo", "rate") if isinstance(option.get(k), (int, float))}
    return setting, extra


def pickups(d: dict, brightness: float, setting: str) -> tuple[list[str], tuple, amp.Coil, dict]:
    """Which pickups the player selects (toward the neck for warmth, the bridge for brightness or drive),
    their sensing points on the strings, their coil and its circuit."""
    b = brightness + d["lean"] + (0.3 if setting == "crunch" else 0.0)
    if d["humbucker"]:
        where = {"neck": 0.150, "bridge": 0.045}
        chosen = ["neck"] if b < 0.4 else ["neck", "bridge"] if b < 0.7 else ["bridge"]
        comb = tuple(((where[p] + side) / d["scale"], 0.5 / len(chosen)) for p in chosen for side in (-0.009, 0.009))
        coil, pot = amp.HUMBUCKER, 500e3
    else:
        where = {"neck": 0.160, "middle": 0.100, "bridge": 0.046}
        chosen = (["neck"] if b < 0.3 else ["neck", "middle"] if b < 0.45 else ["middle"] if b < 0.6
                  else ["middle", "bridge"] if b < 0.75 else ["bridge"])
        comb = tuple((where[p] / d["scale"], 1.0 / len(chosen)) for p in chosen)
        coil, pot = amp.SINGLE, 250e3
    if len(chosen) == 2:
        coil = amp.parallel(coil)
    # the guitar's tone knob: most players leave it near the top (8 to 10), where the coil's resonance sings
    position = 0.85 + 0.15 * float(np.clip(brightness, 0.0, 1.0))
    tone = None if (not d["humbucker"] and chosen == ["bridge"]) else pot * (81.0 ** position - 1.0) / 80.0
    return chosen, comb, coil, dict(pot=pot, tone=tone, tone_cap=d["tone_cap"], cable=d["cable"])


def rig(name: str, s: dict, sr: int) -> tuple[Strings, amp.Coil, dict, amp.Amp]:
    """The strings, pickup and amp for this part: the maker's rig, set by the band's settings."""
    d = built(int(s.get("maker", 0)))
    bright = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
    wear = float(np.clip(s.get("wear", 0.25), 0.0, 1.0))
    size = float(np.clip(s.get("body", 1.0), 0.8, 1.25))
    setting, extra = _setting(name, s)
    chosen, comb, coil, circuit = pickups(d, bright, setting)
    strings = Strings(
        open=TUNING, comb=comb,
        offsets=tuple(z * (0.5 + 4.0 * wear) for z in d["detune"]),
        gains=tuple(10.0 ** (p / 20.0) for p in d["poles"]),
        damping=(7e-6 + 5e-6 * wear) * (1.4 - 0.8 * bright),  # new strings ring bright, old ones go dull
        t60=d["t60"] * (1.0 - 0.3 * wear), along=1.3, heard=0.4, driven=0.5, pick=d["pick"], hardness=0.85,
        click=0.25, touch=0.0, frets=24, glide=6.0, glide_time=0.08, stiffness=STIFFNESS, stiff_sections=2)
    treble, middle, bass = d["knobs"]
    treble = float(np.clip(0.45 + 0.35 * bright + treble + (0.05 if setting == "crunch" else 0.0), 0, 1))
    bass = float(np.clip(0.55 - 0.15 * bright + bass, 0, 1))
    # the volume knob turned to the sound the player wants, as far as it goes
    volume = min(0.0, d["crunch" if setting == "crunch" else "clean"] - heat(coil, treble, middle, bass, d["voicing"]))
    if "drive" in extra:
        volume = -26.0 + 23.0 * float(np.clip(extra["drive"], 0.0, 1.0))
    reverb = 0.0 if setting == "crunch" else d["reverb"]
    if "reverb" in extra:
        reverb = 0.35 * float(np.clip(extra["reverb"], 0.0, 1.0))
    kind, rate, depth = d["tremolo"]
    depth = depth if setting == "tremolo" else 0.0
    if "tremolo" in extra:
        depth = float(np.clip(extra["tremolo"], 0.0, 0.95))
    if "rate" in extra:
        rate = float(np.clip(extra["rate"], 2.0, 10.0))
    cab = d["cabinet"]
    cab = replace(cab, fs=cab.fs / size ** 0.5, back_at=cab.back_at / size ** 0.5)
    rig_amp = amp.Amp(
        voicing=d["voicing"], treble=treble, middle=middle, bass=bass, volume=volume, headroom=d["headroom"],
        knee=d["knee"], tilt=d["tilt"], sag=d["sag"], reverb=reverb, tank=d["tank"], tremolo=(kind, rate, depth),
        cabinet=cab)
    return strings, coil, circuit, rig_amp


@lru_cache(maxsize=256)
def _stack_heat(treble: float, middle: float, bass: float, voicing: str) -> float:
    f = np.exp(np.linspace(np.log(150.0), np.log(1500.0), 24))
    return float(10.0 * np.log10(np.mean(np.abs(amp.stack_response(f, treble, middle, bass, voicing)) ** 2)))


def heat(coil: amp.Coil, treble: float, middle: float, bass: float, voicing: str) -> float:
    """How hot a rig reaches the volume knob, in dB: the pickup's output (a humbucker's is 7 dB over a
    single coil's) and what the tone stack lets through where a strum's energy is (150 Hz to 1.5 kHz: a
    Fender's stack loses 5 to 7 dB more there than a Marshall's)."""
    return 20.0 * np.log10(coil.sensitivity) + _stack_heat(round(treble, 4), round(middle, 4), round(bass, 4), voicing)


def _dead_spot(segments: list, strings: Strings, dead: tuple[float, float]) -> None:
    """Notes whose fundamental sits on the neck's resonance lose their energy to it: a shorter ring."""
    hz, depth = dead
    for seg in segments:
        f = midi_to_hz(seg.base)
        seg.decay = 1.0 - depth * float(np.exp(-0.5 * (np.log2(f / hz) / 0.035) ** 2))


def _pickup_voltage(segs: list, strings: Strings, coil: amp.Coil, circuit: dict, sr: int, length: int,
                    rng: np.random.Generator) -> np.ndarray:
    emf = np.zeros(length)
    for seg in segs:
        if seg.start >= length:
            continue
        y = fretboard.sound(seg, strings, sr, rng)
        end = min(length, seg.start + len(y))
        emf[seg.start:end] += y[: end - seg.start]
    b, a = amp.pickup_ba(coil, **circuit)
    return sosfilt(amp.digital(b, a, sr, amp.resonance(b, a)[0]), emf * EMF * coil.sensitivity)


def _prepare(notes, sr: int, length: int) -> list[Note]:
    last = length / sr
    return sorted((n for n in notes if 0.0 <= n.start < last and n.dur > 0), key=lambda n: (n.start, n.pitch))


def guitar(name: str, notes, sr: int, length: int, rng: np.random.Generator, s: dict) -> np.ndarray:
    """The electric guitar's stem as the amp's two microphones hear it: (length, 2)."""
    notes = _prepare(notes, sr, length)
    if not notes:
        return np.zeros((length, 2))
    strings, coil, circuit, rig_amp = rig(name, s, sr)
    ornament = float(np.clip(s.get("ornament", 0.5), 0.0, 1.0))
    played = fretboard.strum(notes, rng)
    placed = fretboard.fret(played, strings)
    segs = fretboard.segments(placed, strings, sr, rng, ornament=ornament)
    _dead_spot(segs, strings, built(int(s.get("maker", 0)))["dead"])
    emf = _pickup_voltage(segs, strings, coil, circuit, sr, length, rng)
    for note in notes:  # a chop's scratch, once for each muted strum
        if note.art == "chop":
            i = int(round(note.start * sr))
            burst = fretboard.chop_noise(sr, rng, note.vel) * EMF * coil.sensitivity * 3.0
            j = min(length, i + len(burst))
            emf[i:j] += burst[: j - i]
    chain = _chain(rig_amp, s, sr, _setting(name, s)[0] == "crunch")
    chain.p[21] = master_volume(name, s, sr)
    return amp.play(chain, emf) * GUITAR_OUT


def _chain(rig_amp: amp.Amp, s: dict, sr: int, crunch: bool) -> amp.Chain:
    """The amp ready to play; the driven settings oversample four times (their harmonics reach far up), a
    clean amp twice."""
    tempo = s.get("tempo")
    return amp.Chain(rig_amp, sr, tempo=float(tempo) if isinstance(tempo, (int, float)) and tempo > 0 else None,
                     os_=4 if crunch or rig_amp.volume > -15.0 else 2)


def _rig_key(name: str, s: dict) -> tuple:
    setting, extra = _setting(name, s)
    return (int(s.get("maker", 0)), setting, tuple(sorted(extra.items())),
            *(round(float(s.get(k, d)), 6) for k, d in (("brightness", 0.5), ("wear", 0.25), ("body", 1.0))))


REFERENCE_LUFS = -20.0


def master_volume(name: str, s: dict, sr: int) -> float:
    """The amp's master volume, set as a player sets it: the rig's own strum (an A chord, down, at 0.6) comes
    out of the cabinet at the same loudness whatever the guitar, the pickup, the amp or its setting, so a crunch
    sits about as loud as the clean sound it was turned up from."""
    return _master(_rig_key(name, s), sr)


@lru_cache(maxsize=64)
def _master(key: tuple, sr: int) -> float:
    maker, setting, extra, bright, wear, size = key
    s = dict(maker=maker, brightness=bright, wear=wear, body=size, amp=dict(setting=setting, **dict(extra)))
    strings, coil, circuit, rig_amp = rig("electric", s, sr)
    rng = np.random.default_rng([maker, 71])
    notes = []
    for t, art, until in ((0.0, "down", 0.6), (0.6, "down", 0.3), (0.9, "up", 0.6), (1.5, "up", 0.3),
                          (1.8, "down", 0.3), (2.1, "up", 0.9)):  # a bar of the folk strum on an A chord
        chord = (45.0, 52.0, 57.0, 61.0, 64.0) if art == "down" else (57.0, 61.0, 64.0)
        notes += [Note("electric", t, until, p, 0.6 if art == "down" else 0.54, art=art) for p in chord]
    placed = fretboard.fret(fretboard.strum(notes, rng), strings)
    segs = fretboard.segments(placed, strings, sr, rng)
    emf = _pickup_voltage(segs, strings, coil, circuit, sr, int(3.0 * sr), rng)
    chain = _chain(rig_amp, {}, sr, setting == "crunch")
    return float(10.0 ** ((REFERENCE_LUFS - loudness(amp.play(chain, emf), sr)) / 20.0))


# --- the bass --------------------------------------------------------------------------------------------


def bass(notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator, s: dict) -> np.ndarray:
    """The electric bass through its DI: mono, `length` samples."""
    notes = _prepare(notes, sr, length)
    if not notes:
        return np.zeros(length)
    bright = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
    wear = float(np.clip(s.get("wear", 0.25), 0.0, 1.0))
    precision = bool(make.random() < 0.55)
    scale = 0.864
    poles = make.normal(0.0, 0.8, 4)
    detune = make.standard_normal(4)
    finger = float(make.uniform(0.13, 0.2))  # where the fingers pluck: over the pickups
    t60 = float(make.uniform(3.8, 5.2))
    cable = float(make.uniform(3.0, 6.0) * 100e-12)
    if precision:  # the split coil sits about 150 mm from the bridge
        comb = ((0.150 / scale, 1.0),)
        coil = amp.BASS_P
        circuit = dict(pot=250e3, tone=250e3 * (81.0 ** (0.85 + 0.15 * bright) - 1.0) / 80.0, tone_cap=47e-9,
                       cable=cable)
    else:  # two single coils, the neck's and the bridge's, blended toward the bridge for a brighter sound
        blend = float(np.clip(0.35 + 0.3 * bright + make.normal(0.0, 0.08), 0.1, 0.9))
        comb = ((0.153 / scale, 1.0 - blend), (0.085 / scale, blend))
        coil = amp.parallel(amp.BASS_J)
        # each pickup's own 250k volume pot, both loading the pair at full volume, and the tone pot
        circuit = dict(pot=125e3, tone=250e3 * (81.0 ** (0.85 + 0.15 * bright) - 1.0) / 80.0, tone_cap=47e-9,
                       cable=cable)
    strings = Strings(
        open=BASS_TUNING, comb=comb, offsets=tuple(z * (0.5 + 4.0 * wear) for z in detune),
        gains=tuple(10.0 ** (p / 20.0) for p in poles),
        damping=(6e-5 + 5e-5 * wear) * (1.3 - 0.6 * bright),  # roundwound: the zing is gone in a fifth of a second
        t60=t60 * (1.0 - 0.3 * wear), along=1.2, heard=0.5, driven=0.6, pick=finger, hardness=0.35, click=0.2,
        touch=0.3, frets=20,
        kinds=(("pick", (0.75, 2.6, 1.0, 1.0)), ("finger", (1.0, 1.0, 1.0, 0.0))),
        glide=20.0, glide_time=0.12,  # a long string plucked wide: sharp by a sixth of a semitone, settling
        stiffness=BASS_STIFFNESS, stiff_sections=4)
    placed = fretboard.fret(notes, strings)
    segs = fretboard.segments(placed, strings, sr, rng, ornament=float(s.get("ornament", 0.5)))
    picked = {int(round(n.start * sr)) for n, _, _ in placed if n.art == "pick"}
    for seg in segs:  # plain notes are fingered, "pick" notes picked
        seg.picks = [(at, vel, ("pick" if seg.start + at in picked else "finger") if kind == "pick" else kind)
                     for at, vel, kind in seg.picks]
    emf = _pickup_voltage(segs, strings, coil, circuit, sr, length, rng)
    ref = 0.2 * coil.sensitivity
    y = amp.preamp(emf / ref, drive=1.1, tilt=0.12) * BASS_OUT  # the DI's preamp, set for this bass's level
    return sosfilt(butter(1, 25.0, btype="highpass", fs=sr, output="sos"), y)


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A part's dry stem: the guitar's (length, 2), the bass's (length,)."""
    s = dict(settings or {})
    if name == "ebass":
        return bass(notes, sr, length, rng, make, s)
    return guitar(name, notes, sr, length, rng, s)
