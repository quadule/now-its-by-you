"""tools/pronounce.py: how the singer says a song's words, and which it may stress wrongly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import pronounce as P  # noqa: E402  (tools/pronounce.py)

from songbird import genome as G  # noqa: E402


def test_the_song_says_its_own_readings_and_the_suspects_leave_them_out():
    g = G.load(P.H)
    assert P.said("no-bo-dy", None).split()[0] == "NO-BO-DY"  # the dictionary's secondary stresses count
    assert P.said("no-bo-dy", g.lexicon).split()[0] == "NO-bo-dy"  # the song's own reading
    assert P.said("per-fect", g.lexicon).split()[0] == "PER-fect" and P.said("per-fect", None).split()[0] == "per-FECT"
    several, two_ways = P.suspects(g)
    assert "no-bo-dy" not in several and "per-fect" not in two_ways and "rec-ord" not in two_ways
    assert "rail-way" in several and "fif-teen" in two_ways  # still there, for a person to judge
    assert "who" in P.words(g) and "refrain" in P.words(g)["who"]
