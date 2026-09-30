"""Set and check the new instruments' stem levels against the band's, and time them.

    uv run python tools/instrument_levels.py [--module piano mallets ...] [--only NAME ...] [--cpu] [--refs]

Every new instrument module (songbird/synth/piano.py, epiano.py, organ.py,
mallets.py, analog.py, chip.py, drummachine.py) has a SPEC giving each
instrument a role: comping, lead, bass, colour or percussion. This plays a
typical part for that role in D, at velocity 0.6, through the module's
render(), at the SPEC's level and place, and measures its loudness while it
plays (LUFS, BS.1770) against what the existing band does in H with the
seed's params:

    comping     -23.7 LUFS  the guitar's strum through the first refrain
    lead        -20.7       the whistle stating the tune in the intro
    bass        -24.1       the upright bass walking through the first refrain
    percussion  -28.4       the frame drum's full pattern in the last refrain
    colour      -26.5       a bell-like line over the band (glockenspiel, music box):
                            3 dB under the comping, since its top octaves read loud

(--refs measures the first four again from H.) A SPEC may name its own
target instead ("loudness": LUFS), where the role's would mislead: K-weighting
reads a 40-55 Hz sine 4-6 LU quieter than its energy, so a sub bass sits at
-27, not -24. It prints each instrument's loudness, how far it is from its
target, and the level that would put it there. With --cpu it also renders a
three-minute part of the same kind and times it.
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from songbird.score import Note  # noqa: E402
from songbird.synth import instruments, master  # noqa: E402

SR = 44100
MODULES = ("piano", "epiano", "organ", "mallets", "analog", "chip", "drummachine", "melodica")
TARGETS = {"comping": -23.7, "lead": -20.7, "bass": -24.1, "percussion": -28.4, "colour": -26.5}


def target_of(spec: dict) -> float:
    """The loudness an instrument's typical part should have at its SPEC level."""
    return float(spec.get("loudness", TARGETS[spec["role"]]))
SETTINGS = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0, maker=0, tonic=62)
BEAT = 60.0 / 96.0

# I V vi IV in D, as pitch classes from D (the root first)
PROGRESSION = ((0, 4, 7), (7, 11, 14), (9, 12, 16), (5, 9, 12))
# a comping bar: (beat, beats long)
COMP_RHYTHM = ((0.0, 1.5), (1.5, 0.5), (2.0, 1.0), (3.0, 1.0))
# an eight-bar tune in D: (beat, beats, degree above D)
TUNE = ((0, 1, 9), (1, 1, 7), (2, 1.5, 4), (3.5, 0.5, 2), (4, 2, 4), (6, 1, 7), (7, 1, 9),
        (8, 1, 11), (9, 1, 12), (10, 2, 14), (12, 1, 12), (13, 1, 9), (14, 2, 7),
        (16, 1, 9), (17, 1, 7), (18, 1.5, 4), (19.5, 0.5, 2), (20, 2, 0), (22, 1, 2), (23, 1, 4),
        (24, 1, 7), (25, 1, 4), (26, 1, 2), (27, 1, 4), (28, 4, 0))
# a two-bar groove: (beat, piece)
GROOVE = ((0, "kick"), (0, "hat"), (0.5, "hat"), (1, "snare"), (1, "hat"), (1.5, "hat"), (2, "kick"), (2, "hat"),
          (2.5, "kick"), (2.5, "hat"), (3, "snare"), (3, "hat"), (3.5, "hat"),
          (4, "kick"), (4, "hat"), (4.5, "hat"), (5, "clap"), (5, "hat"), (5.5, "hat"), (6, "kick"), (6, "hat"),
          (6.5, "hat"), (7, "snare"), (7, "hat"), (7.5, "hat-open"))


def centre(register) -> int:
    """Where a part for this register is written: its middle, kept off the extremes."""
    lo, hi = register
    return int(round((lo + hi) / 2.0))


def near(pc: int, around: float) -> int:
    """The pitch of pitch class (from D) nearest `around`."""
    base = 62 + pc
    return int(base + 12 * round((around - base) / 12.0))


def typical_part(spec: dict, bars: int = 8, rng: np.random.Generator | None = None, vel: float = 0.6,
                 art: str = "") -> tuple[Note, ...]:
    """A part of `bars` bars for the instrument's role, at velocity `vel` (±0.04)."""
    rng = rng or np.random.default_rng(0)
    role = spec["role"]
    notes = []

    def v():
        return float(np.clip(vel + rng.uniform(-0.04, 0.04), 0.0, 1.0))

    if role == "percussion":
        for rep in range(bars // 2):
            for beat, piece in GROOVE:
                notes.append(Note("x", (rep * 8 + beat) * BEAT + 0.2, 0.25 * BEAT, 60.0, v(), art=piece))
        return tuple(notes)
    lo, hi = spec["register"]
    if role == "comping":
        mid = centre(spec["register"]) + 2
        for bar in range(bars):
            chord = PROGRESSION[bar % 4]
            top = [near(pc, mid + i * 4 - 4) for i, pc in enumerate(chord)]
            voicing = sorted(set([min(top) - 12 if min(top) - 12 >= lo else min(top)] + top))
            voicing = [p for p in voicing if lo <= p <= hi]
            for beat, beats in COMP_RHYTHM:
                for p in voicing:
                    notes.append(Note("x", (bar * 4 + beat) * BEAT + 0.2, beats * BEAT * 0.95, float(p), v(), art=art))
        return tuple(notes)
    if role == "bass":
        low = lo + 5 if hi - lo > 18 else lo
        for bar in range(bars):
            root = PROGRESSION[bar % 4][0]
            r = near(root, low + 7)
            fifth = r + 7 if r + 7 <= hi else r - 5
            for beat, beats, p in ((0, 1.5, r), (1.5, 0.5, r), (2, 1.5, fifth), (3.5, 0.5, r)):
                notes.append(Note("x", (bar * 4 + beat) * BEAT + 0.2, beats * BEAT * 0.9, float(p), v(), art=art))
        return tuple(notes)
    # lead or colour: the tune, an octave placed so it sits in the upper middle of the register
    target = centre(spec["register"]) + 3
    shift = 12 * round((target - (62 + 6)) / 12.0)
    for rep in range(max(1, bars // 8)):
        for beat, beats, degree in TUNE:
            p = 62 + degree + shift
            while p > hi:
                p -= 12
            while p < lo:
                p += 12
            notes.append(Note("x", (rep * 32 + beat) * BEAT + 0.2, beats * BEAT * 0.92, float(p), v(), art=art))
    return tuple(notes)


def render_placed(module, name: str, notes, settings: dict | None = None, seed: int = 0) -> np.ndarray:
    """The part rendered, placed and at the SPEC's level, as the band's stems are."""
    spec = module.SPEC[name]
    end = max(n.start + n.dur for n in notes) + 2.5
    length = int(np.ceil(end * SR))
    rng = np.random.default_rng([seed, 17, 99])
    make = np.random.default_rng([int((settings or SETTINGS).get("maker", 0)), 29, 99])
    y = module.render(name, tuple(notes), SR, length, rng, make, {**SETTINGS, **(settings or {})})
    position, width = spec["place"]
    return instruments.place(y, position, width) * spec["level"]


def loudness_while_playing(y: np.ndarray, notes) -> float:
    s0 = min(n.start for n in notes)
    s1 = max(n.start + n.dur for n in notes) + 0.5
    return float(master.loudness(y[int(s0 * SR): int(s1 * SR)], SR))


def reference_levels() -> dict[str, float]:
    """The band's loudness in H, measured again (as TARGETS were)."""
    from songbird import genome as genome_mod
    from songbird.realize import choose_params, realize

    g = genome_mod.load(str(Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json"))
    params = choose_params(g)
    score = realize(g, params)
    length = int(np.ceil(score.duration * SR))
    sections = [s for s in score.sections]
    out = {}
    for role, name, which in (("comping", "guitar", ("refrain", 0)), ("lead", "whistle", ("intro", 0)),
                              ("bass", "bass", ("refrain", 0)), ("percussion", "drum", ("refrain", 2))):
        stem = instruments.render_part(name, score.part(name), SR, length, score.band, params.seed)
        spans = [(a, b) for s, a, b in sections if s == which[0]]
        a, b = spans[which[1]]
        notes = [n for n in score.part(name) if a <= n.start < b]
        s0, s1 = min(n.start for n in notes), min(b, max(n.start + n.dur for n in notes) + 0.5)
        out[role] = float(master.loudness(stem[int(s0 * SR): int(s1 * SR)], SR))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", nargs="*", default=list(MODULES))
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--cpu", action="store_true", help="also time a three-minute part")
    ap.add_argument("--refs", action="store_true", help="measure the band's references in H again")
    args = ap.parse_args()
    if args.refs:
        for role, lufs in reference_levels().items():
            print(f"{role:11s} {lufs:6.1f} LUFS (TARGETS has {TARGETS[role]})")
    for mod_name in args.module:
        try:
            module = importlib.import_module(f"songbird.synth.{mod_name}")
        except ModuleNotFoundError:
            continue
        for name, spec in module.SPEC.items():
            if args.only and name not in args.only:
                continue
            notes = typical_part(spec)
            y = render_placed(module, name, notes)
            lufs = loudness_while_playing(y, notes)
            target = target_of(spec)
            level = spec["level"] * 10 ** ((target - lufs) / 20.0)
            line = (f"{mod_name:11s} {name:14s} {spec['role']:10s} {lufs:6.1f} LUFS  target {target:6.1f}  "
                    f"off {lufs - target:+5.1f} dB  level {spec['level']:.4g} -> {level:.4g}")
            if args.cpu:  # CPU time of this process (the machine may be busy; wall time says less)
                long = typical_part(spec, bars=int(np.ceil(180.0 / (4 * BEAT))))
                t, wall = time.process_time(), time.perf_counter()
                render_placed(module, name, long)
                line += (f"  3-min part {time.process_time() - t:5.2f} s cpu ({time.perf_counter() - wall:5.2f} s wall,"
                         f" {len(long)} notes)")
            print(line, flush=True)


if __name__ == "__main__":
    main()
