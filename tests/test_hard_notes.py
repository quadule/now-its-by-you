"""tools/hard_notes.py: the notes several singers independently sing as another."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import hard_notes as N  # noqa: E402  (tools/hard_notes.py)

from songbird import genome as G  # noqa: E402


def test_a_note_several_singers_sing_as_the_same_other_one_is_found_and_a_slip_is_not():
    g = G.load(N.H)
    seen = {
        ("v2", 5): {"ana": [-190.0, -210.0], "bo": [-180.0], "cy": [-80.0]},  # so sung as fa, by all three
        ("b2", 4): {"ana": [510.0], "bo": [520.0], "cy": [80.0]},  # re sung as so: as b1 has it there
        ("b3", 6): {"ana": [390.0], "bo": [420.0], "cy": [50.0]},  # a little apart, the same way: so
        ("r1", 3): {"ana": [700.0], "bo": [-20.0], "cy": [10.0]},  # one singer: a slip
        ("r2", 3): {"ana": [-150.0], "bo": [160.0], "cy": [5.0]},  # two, but opposite ways
    }
    found = {(c.phrase, c.index): c for c in N.changes(g, seen)}
    assert set(found) == {("v2", 5), ("b2", 4), ("b3", 6)}
    fa = found[("v2", 5)]
    assert (N.name(fa.written), N.name(fa.sung), sorted(fa.agree)) == ("so", "fa", ["ana", "bo", "cy"])
    assert N.name(found[("b2", 4)].sung) == "so" and "b1" in found[("b2", 4)].like
    assert N.name(found[("b3", 6)].sung) == "so" and "v3" in found[("b3", 6)].like
    assert list(found)[0] == ("v2", 5)  # all three agree: first
    assert (N.name(-2), N.name(0), N.name(1), N.name(8)) == ("so,", "ti,", "do", "do'")
