"""Fit a tube posture to every vowel's formant targets.

    uv run python tools/fit_postures.py

For each vowel in phonetics.VOWEL_FORMANTS, search tongue place, tongue
narrowing and lip opening on the reference (17.5 cm) tract for the shape whose
first three resonances best match the targets, measured in log frequency with
F1 and F2 weighted most. Each vowel is searched only where a tongue can make
it (front vowels near the palate, back vowels near the velum, low vowels in
the pharynx): many shapes share a vowel's formants, but only the anatomical
one moves sensibly into its neighbours. Prints a POSTURES table to paste into phonetics.py,
so the shapes the voice uses are plain numbers anyone can read and change.
"""

from __future__ import annotations

import itertools

import numpy as np

from songbird.phonetics import VOWEL_FORMANTS
from songbird.synth import tube

N = 44
WEIGHTS = np.array([1.0, 1.0, 0.5])
# Where the tongue may narrow the tract for each vowel (cm from the glottis),
# and whether the lips round.
REGIONS = {
    "IY": (11.0, 14.5, False), "IH": (10.5, 14.0, False), "EH": (9.5, 13.5, False), "AE": (4.0, 9.0, False),
    "AA": (3.0, 6.0, False), "AO": (4.0, 7.5, True), "OH": (6.5, 10.5, True), "AH": (5.0, 9.0, False),
    "AX": (3.0, 15.0, False), "UH": (7.5, 11.5, True), "UW": (8.0, 12.0, True), "ER": (3.0, 6.0, True),
}


def error(found: list[float], target) -> float:
    if len(found) < 3:
        return np.inf
    return float(np.sum(WEIGHTS * np.log(np.array(found[:3]) / np.array(target)) ** 2))


def main() -> None:
    places = np.arange(3.0, 15.01, 0.25)
    narrowings = np.arange(0.2, 1.21, 0.05)
    lips = np.arange(0.15, 1.21, 0.1)
    grid = []
    for at, radius, lip in itertools.product(places, narrowings, lips):
        shape = tube.Shape(tongue_at=float(at), tongue_radius=float(radius), lips=float(lip))
        grid.append((shape, tube.formants(shape, N)))
    print(f"# {len(grid)} shapes searched")
    print("POSTURES = {  # vowel: (tongue_at cm, tongue_radius cm, lips cm) -> fitted F1 F2 F3 vs target")
    for vowel, target in VOWEL_FORMANTS.items():
        lo, hi, rounded = REGIONS[vowel]
        allowed = [g for g in grid if lo <= g[0].tongue_at <= hi and (g[0].lips <= 0.6) == rounded]
        shape, found = min(allowed, key=lambda g: error(g[1], target))
        got = " ".join(f"{f:.0f}" for f in found[:3])
        want = " ".join(str(f) for f in target)
        print(f'    "{vowel}": ({shape.tongue_at:.2f}, {shape.tongue_radius:.2f}, {shape.lips:.2f}),  # {got}  vs {want}')
    print("}")


if __name__ == "__main__":
    main()
