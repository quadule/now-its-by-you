"""A cappella: the voices are the band (docs/STYLES.md, "Two more: a cappella and a Celtic session")."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import genome as G, style as S
from songbird.realize import SUNG_SYLLABLES, choose_params, realize
from songbird.style import Style
from songbird.theory import FLOOR

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"


def sung(name="acappella", choir=0, **arrange):
    g = G.load(H)
    p = replace(choose_params(g, style=name, arrange=arrange or None), choir=choir)
    return g, p, realize(g, p)


def test_voices_alone_are_the_band():
    """No instrument plays but feet or hands by chance; a group of at least three sings from the first generation,
    the lineage's voices first and the program's own after them."""
    g, p, score = sung()
    assert p.band.lineup and set(p.band.lineup) == {"stomps", "claps"}  # never empty: empty is the seed's eight
    assert p.style.voices >= 3
    parts = {n.part for n in score.notes}
    assert parts - {"stomps", "claps"} == {"voice", "choir1", "choir2", "choir3"}
    assert score.band["parts"] == "voices"
    g, p, score = sung(choir=5)
    assert {n.part for n in score.notes if n.part.startswith("choir")} == {f"choir{k}" for k in range(1, 6)}


def test_the_parts_are_open_and_keep_clear_of_the_tune():
    """Every part at or above the throat's floor and under E5; never on the lead's note or a semitone from it
    where they sing together; the treble over the tune; open fifths and fourths more often than thirds."""
    g, p, score = sung(backing="oohs")
    lead = [n for n in score.notes if n.part == "voice"]
    together = {}
    for n in score.notes:
        if not n.part.startswith("choir"):
            continue
        assert FLOOR <= n.pitch <= 76, n
        at = next((v for v in lead if abs(v.start - n.start) < 0.05), None)
        if at is not None and n.syllable == at.syllable:
            d = int(abs(n.pitch - at.pitch))
            assert d != 0 and d % 12 not in (1, 11), (n, at)
            together[d % 12] = together.get(d % 12, 0) + 1
    assert sum(together.get(k, 0) for k in (5, 7, 0)) > sum(together.get(k, 0) for k in (3, 4))


def test_the_notes_are_sung_before_the_words():
    """Where the band would play the tune, the lead and the parts sing it on its shape-note syllables (each part its
    own note's), and only an a cappella's score reads them."""
    g, p, score = sung(intro="notes")
    intro = [n for n in score.notes if n.section == "intro" and (n.part == "voice" or n.part.startswith("choir"))]
    assert intro and {n.syllable for n in intro} <= {"fa", "sol", "la", "mi"}
    for n in intro:
        assert n.syllable == S.shape_note(n.pitch, p.tonic, p.mode)
    assert S.shape_note(p.tonic, p.tonic, "ionian") == "fa" and S.shape_note(p.tonic, p.tonic, "aeolian") == "la"
    assert {"fa", "sol"} <= set(score.lexicon)
    g, p, score = sung(intro="lead")
    assert {n.syllable for n in score.notes if n.section == "intro" and n.part == "voice"} == {"oo"}
    seed = realize(g, choose_params(g))
    assert "fa" not in seed.lexicon and set(SUNG_SYLLABLES) <= set(seed.lexicon)


def test_the_verses_hum_and_the_voices_come_in_by_line():
    g, p, score = sung(backing="hum", alone=1, entrances=True)
    spans = {name: (a, b) for name, a, b in score.sections}
    first = [s for s in score.sections if s[0] == "verse"]
    bare, then = first[0], first[1]
    under_bare = [n for n in score.notes if n.part.startswith("choir") and bare[1] <= n.start < bare[2] - 0.05]
    assert not under_bare  # lined out: the lead alone
    hum = [n for n in score.notes if n.part.startswith("choir") and then[1] <= n.start < then[2] - 0.05]
    assert hum and {n.syllable for n in hum} == {"oo"}
    starts = {part: min(n.start for n in hum if n.part == part) for part in {n.part for n in hum}}
    assert len(set(round(t, 1) for t in starts.values())) == len(starts)  # a line apart
    assert spans


def test_the_last_chord_is_held_by_everyone():
    g, p, score = sung()
    ends = {part: max(n.start + n.dur for n in score.notes if n.part == part)
            for part in ("voice", "choir1", "choir2", "choir3")}
    assert all(score.duration - e < 0.5 for e in ends.values()), (ends, score.duration)


def test_the_singers_are_matched_to_the_parts():
    from songbird.synth import matched, lineage_voices

    g, p, score = sung()
    parts = ["choir1", "choir2", "choir3"]
    singers = lineage_voices(3, p.seed, learned=True)
    singers = [replace(x, shift=0) for x in singers]
    singers[0] = replace(singers[0], tract=1.2)
    singers[2] = replace(singers[2], shift=-12)
    out = matched(score, parts, singers)
    middle = {q: np.median([n.pitch for n in score.part(q)]) for q in parts}
    lowest = min(parts, key=middle.get)
    assert out[parts.index(lowest)].tract == singers[2].tract
    assert all(v.shift == 0 and v.vibrato_depth <= 14 and v.scoop <= 0.2 for v in out)


def test_a_style_beside_the_ring_travels_from_its_anchor():
    """Nothing steps into a style beside the ring; a lineage in one keeps it where it would keep its anchor's,
    and otherwise steps to its anchor's neighbour."""
    from songbird import drift as D, harvest as HV, variation as V

    assert set(S.OFF_RING) <= set(S.STYLES) and not set(S.OFF_RING) & set(S.RING)
    parent = Style(name="acappella", lineage=("ballad", "acappella"))
    seen = set()
    for k in range(6):
        voice = HV.fictional(f"m{k}")
        c = V.character(voice)
        for t in np.arange(D.parse("2026-01-01"), D.parse("2027-01-01"), 7.0):
            seen.add(S.place(parent, c, D.drift(t, voice.hash)))
            assert S.place(Style(), c, D.drift(t, voice.hash)) not in S.OFF_RING
    assert seen <= {"acappella", *S.neighbours("shanty")} and "acappella" in seen


@pytest.mark.parametrize("machine", ["ada", "basil"])
def test_a_machines_child_of_an_a_cappella_parent(machine):
    from songbird import drift as D, harvest as HV

    g = G.load(H)
    parent = choose_params(g, style="acappella")
    child = choose_params(g, parent=parent, voice=HV.fictional(machine), drift=D.drift(D.parse("2026-10-01"),
                                                                                         HV.fictional(machine).hash))
    assert child.style.name in {"acappella", *S.neighbours("acappella")}
    if child.style.name == "acappella":
        assert set(child.band.lineup) == {"stomps", "claps"}
