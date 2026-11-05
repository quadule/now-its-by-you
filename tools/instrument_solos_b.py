"""The second set of instruments, each alone: a short phrase in D for the ears, its level and its cost.

    uv run python tools/instrument_solos_b.py [--only kit banjo ...] [--out DIR] [--levels] [--cpu] [--dry]

The phrases live in tools/instrument_phrases_b/, one file per family, each with
    MODULE  = {instrument: the songbird.synth module that plays it}
    PHRASES = {title: dict(parts={instrument: [Note, ...]}, about="what to listen for",
                           mix_as={instrument: an existing mix role}, optional)}
    LEVELS  = {instrument: (kind, [Note, ...])}, kind one of comping, lead, percussion, bass, colour:
              the instrument's typical part, whose placed loudness should meet that kind's target.
    LEADS   = {instrument: [Note, ...]}, optional: a comping instrument's break, played as a style's lead
              plays it, measured against the lead target too.

For every phrase, writes <out>/<title>.flac: its parts rendered, placed and levelled as their SPECs
say, through the house mix and its room (synth.mix), mastered to -18 LUFS so they can be compared
(--dry: no mix or room, just the placed stems); and <out>/README-b.txt listing them. The mix picks a
channel strip by a stem's name, and each of these now finds one that suits it (docs/INSTRUMENTS-B.md,
For the mix); mix_as names another strip a demo borrows, should one ever need to. --levels prints
each calibration part's loudness against its target (today's stems in H: the guitar's strum in the
first refrain, the whistle's intro, the frame drum's full pattern, the upright bass; the same targets
as tools/instrument_levels.py); --cpu the seconds its part takes to render when played for three minutes.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
import time
import hashlib
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from songbird import synth  # noqa: E402
from songbird.synth import instruments, master  # noqa: E402

SR = synth.SR
TARGETS = {"comping": -23.7, "lead": -20.7, "percussion": -28.4, "bass": -24.1, "colour": -26.5}
SETTINGS = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0, maker=0, tonic=62, capo=0)
PHRASE_DIR = Path(__file__).parent / "instrument_phrases_b"
OUT = ROOT / "renders" / "production" / "instruments"


def families() -> list:
    sys.path.insert(0, str(PHRASE_DIR))  # the phrase files share _common.py
    out = []
    for path in sorted(p for p in PHRASE_DIR.glob("*.py") if not p.name.startswith("_")):
        spec = importlib.util.spec_from_file_location(f"instrument_phrases_b.{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        out.append(module)
    return out


def module_for(family, name: str):
    return importlib.import_module(f"songbird.synth.{family.MODULE[name]}")


def streams(name: str, seed: int = 0, maker: int = 0) -> tuple[np.random.Generator, np.random.Generator]:
    """A part's performance stream and its maker's stream, as the band's registry gives them (instruments.stream)."""
    k = int.from_bytes(hashlib.sha256(f"instrument|{name}".encode()).digest()[:4], "little") % 1_000_000
    return np.random.default_rng([seed, 17, 1000 + k]), np.random.default_rng([maker, 29, 1000 + k])


def placed(module, name: str, notes, length: int, settings: dict | None = None, seed: int = 0) -> np.ndarray:
    s = {**SETTINGS, **(settings or {})}
    rng, make = streams(name, seed, int(s["maker"]))
    y = module.render(name, tuple(notes), SR, length, rng, make, s)
    position, width = module.SPEC[name]["place"]
    return instruments.place(y, position, width) * module.SPEC[name]["level"]


def span(notes) -> float:
    return max(n.start + n.dur for n in notes)


def render_phrase(family, parts: dict, dry: bool = False, settings: dict | None = None,
                  mix_as: dict | None = None) -> np.ndarray:
    length = int((max(span(notes) for notes in parts.values()) + 2.5) * SR)
    stems = {name: placed(module_for(family, name), name, notes, length, settings) for name, notes in parts.items()}
    if dry:
        return sum(stems.values())
    borrowed = {}
    for name, stem in stems.items():  # a stem mixed under the name of the strip it borrows (drum, drum2...)
        role = (mix_as or {}).get(name, name)
        key, k = role, 2
        while key in borrowed:
            key, k = f"{role}{k}", k + 1
        borrowed[key] = stem
    return synth.mix(borrowed, SR, 0)


def looped(notes, seconds: float = 180.0):
    """The part played again and again for `seconds`."""
    period = np.ceil(span(notes) / 0.5) * 0.5
    out = []
    k = 0
    while k * period < seconds:
        out += [replace(n, start=n.start + k * period) for n in notes if n.start + k * period < seconds]
        k += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="instruments (or phrase titles) to render")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--levels", action="store_true", help="print each calibration part's loudness against its target")
    ap.add_argument("--cpu", action="store_true", help="time a three-minute part of each instrument")
    ap.add_argument("--dry", action="store_true", help="placed stems only: no mix, no room")
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args()
    wanted = set(args.only or [])
    out = Path(args.out)
    readme = []
    for family in families():
        if args.levels or args.cpu:
            for name, (kind, notes) in family.LEVELS.items():
                if wanted and name not in wanted:
                    continue
                module = module_for(family, name)
                length = int((span(notes) + 1.0) * SR)
                lufs = master.loudness(placed(module, name, notes, length), SR)
                target = float(module.SPEC[name].get("loudness", TARGETS[kind]))  # a SPEC may name its own
                row = f"{name:18s} {kind:10s} {lufs:6.1f} LUFS  target {target:6.1f}  ({lufs - target:+.1f})"
                if args.cpu:  # this process's CPU time: a busy machine doesn't count against it
                    part = looped(notes)
                    rng, make = streams(name)
                    t = time.process_time()
                    module.render(name, tuple(part), SR, int((span(part) + 1.0) * SR), rng, make, dict(SETTINGS))
                    row += f"  3-minute part {time.process_time() - t:5.1f} s CPU ({len(part)} notes)"
                print(row, flush=True)
            for name, notes in getattr(family, "LEADS", {}).items():  # a family's breaks, as a style's lead plays them
                if wanted and name not in wanted:
                    continue
                length = int((span(notes) + 1.0) * SR)
                lufs = master.loudness(placed(module_for(family, name), name, notes, length), SR)
                print(f"{name:18s} {'lead':10s} {lufs:6.1f} LUFS  target {TARGETS['lead']:6.1f}  "
                      f"({lufs - TARGETS['lead']:+.1f})", flush=True)
        if args.no_render:
            continue
        for title, phrase in family.PHRASES.items():
            if wanted and title not in wanted and not wanted & set(phrase["parts"]):
                continue
            out.mkdir(parents=True, exist_ok=True)
            t = time.perf_counter()
            mix = render_phrase(family, phrase["parts"], args.dry, phrase.get("settings"), phrase.get("mix_as"))
            pcm = master.to_pcm16(master.master(mix, SR, target=-18.0), seed=1)
            path = out / f"{title}.flac"
            master.write_flac(path, pcm, SR)
            print(f"{path}  {len(pcm) / SR:.1f}s  rendered in {time.perf_counter() - t:.1f}s", flush=True)
            strips = "".join(f" ({n} through the mix's {r} strip)" for n, r in (phrase.get("mix_as") or {}).items())
            readme.append(f"{title}.flac\n    {', '.join(phrase['parts'])}: {phrase['about']}{strips}\n")
    if readme and not wanted:
        (out / "README-b.txt").write_text(
            "The second set of instruments, each alone (tools/instrument_solos_b.py): a short phrase in D,\n"
            "placed and levelled as the band would have it, through the house mix and its room, mastered\n"
            "to -18 LUFS so they can be compared. Everything is synthesized; nothing is sampled. Each goes\n"
            "through the mix's channel strip for its name (a demo that borrows another says so below).\n\n"
            + "\n".join(readme))


if __name__ == "__main__":
    main()
