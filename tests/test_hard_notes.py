"""tools/hard_notes.py: the notes several singers independently sing as another."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import hard_notes as N  # noqa: E402  (tools/hard_notes.py)

from songbird import genome as G  # noqa: E402


def test_a_note_several_singers_sing_as_the_same_other_one_is_found_and_a_slip_is_not():
    g = G.load(N.H)
    seen = {
        ("v3", 1): {"ana": [-190.0, -210.0], "bo": [-180.0], "cy": [-80.0]},  # so sung as fa, by all three
        ("b2", 9): {"ana": [190.0], "bo": [220.0], "cy": [30.0]},  # re sung as mi: as b1 has it there
        ("b3", 8): {"ana": [270.0], "bo": [330.0], "cy": [50.0]},  # a little apart, the same way: so, as v3 (b3 #8 is mi since 2026-09-27)
        ("r1", 3): {"ana": [700.0], "bo": [-20.0], "cy": [10.0]},  # one singer: a slip
        ("r2", 3): {"ana": [-150.0], "bo": [160.0], "cy": [5.0]},  # two, but opposite ways
    }
    found = {(c.phrase, c.index): c for c in N.changes(g, seen)}
    assert set(found) == {("v3", 1), ("b2", 9), ("b3", 8)}
    fa = found[("v3", 1)]
    assert (N.name(fa.written), N.name(fa.sung), sorted(fa.agree)) == ("so", "fa", ["ana", "bo", "cy"])
    assert N.name(found[("b2", 9)].sung) == "mi" and "b1" in found[("b2", 9)].like
    assert N.name(found[("b3", 8)].sung) == "so" and "v3" in found[("b3", 8)].like
    assert list(found)[0] == ("v3", 1)  # all three agree: first
    assert [found[k].category for k in (("v3", 1), ("b2", 9), ("b3", 8))] == ["passing", "familiar", "familiar"]
    assert N.category([1, 5, 3], 1, 2, []) == "passing" and N.category([1, 5], 0, 2, []) == "pickup"
    assert N.category([1, 5, 3], 1, 6, []) == "shift"
    assert (N.name(-2), N.name(0), N.name(1), N.name(8)) == ("so,", "ti,", "do", "do'")
