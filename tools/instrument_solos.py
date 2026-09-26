"""Each new instrument alone, playing a short phrase in D written for it, so it can be heard.

    uv run python tools/instrument_solos.py [--out DIR] [--only NAME ...] [--plots] [--sketches]

Writes <out>/<instrument>.flac (default renders/production/instruments/) for
every instrument of the new modules (piano, epiano, organ, mallets, analog,
chip, drummachine) that exists: I, vi, IV, V and home in D at 96 bpm, about
twelve seconds, in the idiom of the instrument (a pedalled piano with the tune
on top, rootless voicings on the tine piano, held chords and a rotor
speeding up on the organ, rolled broken chords on the marimba, the tune two
octaves up on the glockenspiel, a pumping synth bass, sixteenth-note
arpeggios, a groove with a fill on the drum machines), at its SPEC level
and place, with the maker's defaults, in the song's room (synth.mix, as
tools/band_solos.py does), mastered to -18 LUFS so they can be compared, and
a README.txt that says what each file is. With --plots, a spectrogram and
level envelope of each beside it. With --sketches, a few genre sketches as
well (sketch-*.flac): the same phrases stacked into a small band (a piano
ballad, soul, synth-pop, a chiptune, a lullaby, lounge), to hear how the
instruments sit together. (--only with no names renders only the sketches.)
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from songbird import synth  # noqa: E402
from songbird.score import Note  # noqa: E402
from songbird.synth import instruments, master  # noqa: E402

SR = synth.SR
MODULES = ("piano", "epiano", "organ", "mallets", "analog", "chip", "drummachine")
SETTINGS = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0, maker=0, tonic=62)
BEAT = 60.0 / 96.0
BAR = 4 * BEAT
LEAD_IN = 0.3

# I vi IV V I in D: each chord's pitch classes above D, the root first
CHORDS = ((0, 4, 7), (9, 0, 4), (5, 9, 0), (7, 11, 2), (0, 4, 7))
# the tune over them: (bar, beat, beats, semitones above D4)
TUNE = ((0, 0, 1, 16), (0, 1, 1, 14), (0, 2, 1, 12), (0, 3, 1, 7), (1, 0, 1, 9), (1, 1, 1, 12), (1, 2, 2, 16),
        (2, 0, 1, 17), (2, 1, 1, 16), (2, 2, 1, 14), (2, 3, 1, 12), (3, 0, 2, 14), (3, 2, 1, 11), (3, 3, 1, 7),
        (4, 0, 4, 12))


def at(bar: float, beat: float = 0.0) -> float:
    return LEAD_IN + bar * BAR + beat * BEAT


def near(pc: int, around: float) -> int:
    """The pitch of pitch class `pc` (semitones above D) nearest `around`."""
    base = 62 + pc
    return int(base + 12 * round((around - base) / 12.0))


def voicing(chord, centre: float, count: int = 3) -> list[int]:
    """A close voicing of the chord's tones around `centre`."""
    notes = sorted(near(pc, centre + 4 * (i - 1)) for i, pc in enumerate(chord[:count]))
    return sorted(set(notes))


def tune(shift: int = 0, scale: float = 1.0, art: str = "", vel: float = 0.62, legato: float = 0.95) -> list[Note]:
    """The tune's notes (their part is "tune", so a sketch can leave them out of an accompaniment)."""
    out = []
    for bar, beat, beats, step in TUNE:
        v = vel + (0.08 if beat == 0 else 0.0) - (0.05 if beats < 1 else 0.0)
        out.append(Note("tune", at(bar, beat), beats * BEAT * legato * scale, 62.0 + step + shift, v, art=art))
    return out


def fit(pitch: float, register) -> float:
    lo, hi = register
    while pitch > hi:
        pitch -= 12
    while pitch < lo:
        pitch += 12
    return pitch


def pick(spec: dict, *wanted: str) -> str:
    """The first of the wanted articulations the instrument has ("" if none)."""
    for w in wanted:
        for art in spec["articulations"]:
            if art == w or (w and art.split() and art.split()[0] == w):
                return art
    return ""


def shift_for(register, lo_target: int) -> int:
    """Octaves (in semitones) that bring the tune (D4 to G5) into a register, as low as it comfortably goes."""
    lo, hi = register
    shift = 0
    while 62 + shift < max(lo, lo_target):
        shift += 12
    while 79 + shift > hi:
        shift -= 12
    return shift


# --- phrases -----------------------------------------------------------------------------------


def piano_phrase(spec):
    ped = pick(spec, "ped")
    notes = []
    for bar, chord in enumerate(CHORDS):
        root = near(chord[0], 43)
        long = BAR * (1.0 if bar < 4 else 1.6)
        notes += [Note("x", at(bar), long, float(root), 0.6, art=ped), Note("x", at(bar), long, float(root + 12), 0.5, art=ped)]
        for p in voicing(chord, 64):
            notes.append(Note("x", at(bar, 1), long - BEAT, float(p), 0.45, art=ped))
            if bar < 4:
                notes.append(Note("x", at(bar, 2.5), long - 2.5 * BEAT, float(p), 0.4, art=ped))
    notes += tune(shift=12, art=ped, vel=0.66)
    return notes, "a pedalled accompaniment (bass octaves, chords after the beat) with the tune on top"


def epiano_phrase(spec):
    ped = pick(spec, "ped")
    # rootless voicings: the 3rd, 7th and 9th (Dmaj9, Bm9, Gmaj9, A13 and home)
    shells = ((4, 11, 14), (2, 9, 12), (11, 18, 21), (6, 11, 14), (4, 11, 14))
    roots = (38, 47, 43, 45, 38)
    notes = []
    for bar, (shell, root) in enumerate(zip(shells, roots)):
        notes.append(Note("x", at(bar), BAR * 0.9, float(root), 0.55, art=ped))
        top = [root + 12 + s for s in shell]
        top = [p - 12 if p > 72 else p for p in top]
        rhythm = ((0.0, 1.4), (1.5, 0.45), (2.5, 1.4)) if bar < 4 else ((0.0, 4.0),)
        for beat, beats in rhythm:
            for p in sorted(top):
                notes.append(Note("x", at(bar, beat), beats * BEAT, float(p), 0.5 + 0.08 * (beat == 0), art=ped))
    return notes, "rootless voicings (3rd, 7th, 9th) over a bass note, a comping rhythm"


def organ_phrase(spec):
    base = pick(spec, "gospel", "full", "")
    fast = pick(spec, f"{base} fast".strip(), "fast")
    notes = []
    for bar, chord in enumerate(CHORDS):
        art = fast if (bar >= 2 and fast) else base
        for p in voicing(chord, 64, 3) + [near(chord[0], 50)]:
            notes.append(Note("x", at(bar), BAR * (0.98 if bar < 4 else 1.5), float(p), 0.7, art=art))
    return notes, f"held chords with a moving top (registration {base or 'default'!r}), the rotor to fast from bar 3" if fast else \
        f"held chords (registration {base or 'default'!r})"


def keys_pad_phrase(spec):
    notes = []
    for bar, chord in enumerate(CHORDS):
        for p in voicing(chord, 62, 3) + [near(chord[0], 50)]:
            notes.append(Note("x", at(bar), BAR * (0.97 if bar < 4 else 1.4), float(p), 0.6))
    return notes, "held chords with the root below"


def vibraphone_phrase(spec):
    notes = []
    for bar, chord in enumerate(CHORDS):
        for p in voicing(chord, 62, 3):
            notes.append(Note("x", at(bar), BAR * 0.95, float(p), 0.45))
    notes += [Note("x", n.start, max(n.dur, 2 * BEAT), fit(n.pitch + 12, spec["register"]), n.vel)
              for n in tune(vel=0.6)]
    return notes, "the tune over let-ring chords, the motor on"


def marimba_phrase(spec):
    lo, hi = spec["register"]
    notes = []
    for bar, chord in enumerate(CHORDS):
        tones = voicing(chord, 60, 3)
        figure = [tones[0] - 12, tones[0], tones[1], tones[2], tones[1] + 12, tones[2], tones[1], tones[0]]
        for i, p in enumerate(figure if bar < 4 else figure[:1]):
            notes.append(Note("x", at(bar, i * 0.5), 0.5 * BEAT, fit(p, (lo, hi)), 0.55 + 0.1 * (i % 4 == 0)))
    # a roll on the last chord: alternating mallets, sixteenths
    for i in range(12):
        p = voicing(CHORDS[4], 67, 3)[i % 3]
        notes.append(Note("x", at(4, i * 0.25), 0.25 * BEAT, float(p), 0.45 + 0.05 * (i % 2)))
    return notes, "broken chords in eighths, then a roll on the last chord"


def bell_phrase(spec, what):
    shift = shift_for(spec["register"], spec["register"][0])
    notes = tune(shift=shift, legato=0.6, vel=0.6)
    if what == "music-box":  # the comb plays the accompaniment too, as its cylinder's pins do
        for bar, chord in enumerate(CHORDS):
            for i, pc in enumerate((chord[0], chord[2], chord[1], chord[2])):
                p = fit(near(pc, 62 + shift - 10), spec["register"])
                notes.append(Note("x", at(bar, i), 0.9 * BEAT, float(p), 0.45))
        return notes, "the tune with the cylinder's arpeggio underneath"
    if what == "celesta":
        ped = pick(spec, "ped")
        for bar, chord in enumerate(CHORDS):
            for p in voicing(chord, 62 + shift - 12, 3):
                notes.append(Note("x", at(bar), BAR * 0.9, fit(p, spec["register"]), 0.4, art=ped))
        return notes, "the tune over soft chords"
    return notes, "the tune, as a glockenspiel doubles it two octaves up"


def pad_phrase(spec):
    notes = []
    for bar, chord in enumerate(CHORDS):
        for p in voicing(chord, 64, 3) + [near(chord[0], 55)]:
            notes.append(Note("x", at(bar), BAR * (1.0 if bar < 4 else 1.6), float(p), 0.6))
    return notes, "whole-note chords, voice-led"


def synth_bass_phrase(spec):
    glide = pick(spec, "glide", "legato", "slide")
    notes = []
    for bar, chord in enumerate(CHORDS):
        root = fit(near(chord[0], 38), spec["register"])
        if bar == 4:
            notes.append(Note("x", at(bar), BAR, float(root), 0.7))
            break
        for i in range(8):
            p = root + (12 if i in (3, 6) else 0)
            art = glide if i == 7 else ""
            notes.append(Note("x", at(bar, i * 0.5), 0.45 * BEAT if i != 7 else 0.55 * BEAT, float(p), 0.6 + 0.12 * (i % 2 == 0), art=art))
    return notes, "pumping eighths with octave jumps"


def sub_phrase(spec):
    notes = []
    for bar, chord in enumerate(CHORDS):
        root = fit(near(chord[0], 33), spec["register"])
        notes.append(Note("x", at(bar), 1.9 * BEAT, float(root), 0.65))
        if bar < 4:
            notes.append(Note("x", at(bar, 2.5), 1.3 * BEAT, float(root), 0.55))
    return notes, "roots on the one and the and of three"


def solo_phrase(spec):
    shift = shift_for(spec["register"], 60)
    notes = tune(shift=shift, legato=1.04, vel=0.65)  # overlapping: a mono synth glides between them
    return notes, "the tune, legato (gliding), the last note long enough for its vibrato"


def arp_phrase(spec):
    notes = []
    for bar, chord in enumerate(CHORDS):
        tones = voicing(chord, 66, 3)
        cycle = tones + [tones[0] + 12] + [tones[2], tones[1]]
        for i in range(16 if bar < 4 else 4):
            p = fit(cycle[i % len(cycle)], spec["register"])
            notes.append(Note("x", at(bar, i * 0.25), 0.22 * BEAT, float(p), 0.55 + 0.12 * (i % 4 == 0)))
    return notes, "sixteenth-note arpeggios through the chords"


def chip_phrase(spec):
    duty_a = pick(spec, "25", "50")
    duty_b = pick(spec, "12", "50")
    arp = pick(spec, "arp-maj")
    notes = []
    for n in tune(shift=shift_for(spec["register"], 60), legato=0.85, vel=0.65):
        art = arp if (n.dur > 1.5 * BEAT and arp) else (duty_b if int((n.start - LEAD_IN) / BAR) % 2 else duty_a)
        notes.append(Note("x", n.start, n.dur, n.pitch, n.vel, art=art))
    return notes, "the tune, the duty changing bar by bar, a chord arpeggio on the long notes"


def chip_bass_phrase(spec):
    notes = []
    for bar, chord in enumerate(CHORDS):
        root = fit(near(chord[0], 45), spec["register"])
        for i, off in enumerate((0, 12, 7, 12, 0, 12, 7, 12) if bar < 4 else (0,)):
            notes.append(Note("x", at(bar, i * 0.5), (0.45 if bar < 4 else 3.5) * BEAT, float(root + off), 0.7))
    return notes, "a bouncing eighth-note bass"


def groove_phrase(spec):
    arts = spec["articulations"]
    has = lambda p: p in arts  # noqa: E731
    notes = []

    def hit(bar, beat, piece, vel):
        if has(piece):
            notes.append(Note("x", at(bar, beat), 0.2, 60.0, vel, art=piece))

    for bar in range(4):
        for i in range(8):
            beat = i * 0.5
            accent = 0.72 if i % 2 == 0 else 0.5
            if bar == 3 and beat >= 2.0:
                continue
            hit(bar, beat, "hat-open" if (i == 7 and bar % 2 == 1) else "hat", accent)
        hit(bar, 0, "kick", 0.85)
        hit(bar, 2.5 if bar % 2 else 2.0, "kick", 0.7)
        hit(bar, 1, "snare", 0.75)
        if bar < 3:
            hit(bar, 3, "snare", 0.78)
        if bar >= 2:
            hit(bar, 1, "clap", 0.6)
        if bar == 1:
            hit(bar, 3.5, "cowbell", 0.5)
            hit(bar, 1.75, "rim", 0.45)
    for i, piece in enumerate(("tom-hi", "tom-hi", "tom-mid", "tom-mid", "tom-lo", "tom-lo")):
        hit(3, 2 + i / 3, piece, 0.6 + 0.05 * i)
    hit(4, 0, "kick", 0.95)
    hit(4, 0, "crash", 0.8) if has("crash") else hit(4, 0, "hat-open", 0.8)
    return notes, "four bars: kick, snare and clap, hats with an open one, a rim and a cowbell, a tom fill, the one"


def phrase_for(name: str, spec: dict):
    if spec["register"] is None:
        return groove_phrase(spec)
    table = {
        "piano": piano_phrase, "epiano": epiano_phrase, "epiano-reed": epiano_phrase,
        "organ": organ_phrase, "harmonium": keys_pad_phrase,
        "vibraphone": vibraphone_phrase, "marimba": marimba_phrase,
        "glockenspiel": lambda s: bell_phrase(s, "glockenspiel"), "music-box": lambda s: bell_phrase(s, "music-box"),
        "celesta": lambda s: bell_phrase(s, "celesta"),
        "synth-pad": pad_phrase, "synth-bass": synth_bass_phrase, "sub-bass": sub_phrase,
        "synth-solo": solo_phrase, "synth-arp": arp_phrase,
        "chip": chip_phrase, "chip-bass": chip_bass_phrase,
    }
    if name in table:
        return table[name](spec)
    role = spec["role"]  # anything new: by its role
    if role == "bass":
        return synth_bass_phrase(spec)
    if role in ("lead", "colour"):
        return solo_phrase(spec)
    return keys_pad_phrase(spec)


def keep_in(notes, register) -> tuple[Note, ...]:
    if register is None:
        return tuple(notes)
    return tuple(Note(n.part, n.start, n.dur, fit(n.pitch, register), n.vel, art=n.art) for n in notes)


def solo(module, name: str) -> tuple[np.ndarray, str, tuple[Note, ...]]:
    spec = module.SPEC[name]
    notes, what = phrase_for(name, spec)
    notes = keep_in(notes, spec["register"])
    length = int(np.ceil((max(n.start + n.dur for n in notes) + 2.5) * SR))
    rng = np.random.default_rng([0, 17, 99])
    make = np.random.default_rng([SETTINGS["maker"], 29, 99])
    y = module.render(name, notes, SR, length, rng, make, dict(SETTINGS))
    position, width = spec["place"]
    stem = instruments.place(y, position, width) * spec["level"]
    fade = min(length, int(0.3 * SR))
    stem[length - fade:] *= np.linspace(1.0, 0.0, fade)[:, None]
    return synth.mix({name: stem}, SR, 0), what, notes


# Genre sketches: the same phrases stacked (they share the progression and the tempo), each part at
# a gain against its SPEC level and with the band settings the style would choose.
SKETCHES = {
    "ballad": ("a piano ballad: the pedalled piano and its tune, a pad beneath, a sub bass",
               dict(brightness=0.45), {"piano": 1.0, "synth-pad": 0.7, "sub-bass": 0.8}),
    "soul": ("soul: the organ's held chords with the rotor speeding up, the tine piano comping, synth bass, "
             "the 909-style kit", dict(brightness=0.55),
             {"organ": 0.8, "epiano": 0.9, "synth-bass": 1.0, "drums-909": 1.0}),
    "synthpop": ("synth-pop: arpeggios, a pad, pumping synth bass, the 808-style kit and the tune on the mono synth",
                 dict(brightness=0.6), {"synth-arp": 0.8, "synth-pad": 0.7, "synth-bass": 1.0, "drums-808": 1.0,
                                        "synth-solo": 0.9}),
    "chiptune": ("a game console's tune: the pulse channel's tune and arpeggios, the triangle bass, the noise drums",
                 dict(), {"chip": 1.0, "chip-bass": 1.0, "chip-drums": 1.0}),
    "lullaby": ("a lullaby: the music box's tune, the celesta's chords, a felt piano's accompaniment",
                dict(brightness=0.2, wear=0.1), {"music-box": 1.0, "celesta": (0.7, "comp"), "piano": (0.6, "comp")}),
    "lounge": ("lounge: the vibraphone's tune, the tine piano's voicings, a sub bass and the 808-style kit played soft",
               dict(brightness=0.4), {"vibraphone": 1.0, "epiano": 0.8, "sub-bass": 0.8, "drums-808": 0.6}),
}


def sketch(owners: dict, parts: dict, settings: dict) -> np.ndarray | None:
    """The parts' phrases stacked, each a stem at its level times its gain, in the song's room.
    A part given as (gain, "comp") plays its accompaniment without the tune."""
    if not all(name in owners for name in parts):
        return None
    rendered, gains = {}, {}
    for name, how in parts.items():
        spec = owners[name].SPEC[name]
        notes, _ = phrase_for(name, spec)
        gain, variant = how if isinstance(how, tuple) else (how, "")
        if variant == "comp":
            notes = [n for n in notes if n.part != "tune"]
        rendered[name], gains[name] = keep_in(notes, spec["register"]), gain
    length = int(np.ceil((max(n.start + n.dur for ns in rendered.values() for n in ns) + 2.5) * SR))
    stems = {}
    for i, name in enumerate(parts):
        gain = gains[name]
        spec = owners[name].SPEC[name]
        rng = np.random.default_rng([0, 17, i])
        make = np.random.default_rng([0, 29, i])
        y = owners[name].render(name, rendered[name], SR, length, rng, make, {**SETTINGS, **settings})
        stem = instruments.place(y, *spec["place"]) * spec["level"] * gain
        fade = min(length, int(0.3 * SR))
        stem[length - fade:] *= np.linspace(1.0, 0.0, fade)[:, None]
        stems[name] = stem
    return synth.mix(stems, SR, 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent.parent / "renders" / "production" / "instruments"))
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--plots", action="store_true")
    ap.add_argument("--sketches", action="store_true", help="also render the genre sketches (sketch-*.flac)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    owners = {}
    for mod_name in MODULES:
        try:
            module = importlib.import_module(f"songbird.synth.{mod_name}")
        except ModuleNotFoundError:
            continue
        for name, spec in module.SPEC.items():
            owners[name] = module
            if args.only is not None and name not in args.only:
                continue
            mix, what, notes = solo(module, name)
            pcm = master.to_pcm16(master.master(mix, SR, target=-18.0), seed=1)
            path = out / f"{name}.flac"
            master.write_flac(path, pcm, SR)
            print(f"{path}  {len(pcm) / SR:.1f}s  {len(notes)} notes", flush=True)
            lines.append((path.name, f"{spec['about']}: {what}."))
            if args.plots:
                from band_solos import plot

                plot(pcm / 32768.0, path.with_suffix(".png"), name)
    if args.sketches:
        for genre, (what, settings, parts) in SKETCHES.items():
            mix = sketch(owners, parts, settings)
            if mix is None:
                continue
            pcm = master.to_pcm16(master.master(mix, SR, target=-16.0), seed=1)
            path = out / f"sketch-{genre}.flac"
            master.write_flac(path, pcm, SR)
            print(f"{path}  {len(pcm) / SR:.1f}s", flush=True)
            lines.append((path.name, f"{what} (mastered to -16 LUFS)."))
    if args.only is None:
        width = max(len(f) for f, _ in lines) + 2
        readme = ["The new instruments, each alone (see docs/INSTRUMENTS.md for how each is built and measured).",
                  "Every file plays a short phrase in D (I, vi, IV, V and home, 96 bpm) written for the instrument,",
                  "at its default settings (brightness 0.5, wear 0.25, ornament 0.5, body 1, maker 0), in the song's",
                  "room, mastered to -18 LUFS so they can be compared. Made by tools/instrument_solos.py.", ""]
        readme += [f"{f:<{width}}{text}" for f, text in lines]
        (out / "README.txt").write_text("\n".join(readme) + "\n")


if __name__ == "__main__":
    main()
