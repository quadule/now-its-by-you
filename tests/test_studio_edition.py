"""A version made from a published edition (the studio's ?new, from the awards performance draft): it says it comes
from that edition by name, the edition's own lines are handed down rather than yours, and comparing machines shows
the words that differ between them."""

import tempfile
from pathlib import Path

import pytest

from songbird import explain
from songbird.studio import Studio

ROOT = Path(__file__).parent.parent
RECORD = ROOT / "webstudio" / "released-record.json"


@pytest.fixture(scope="module")
def studio():
    return Studio(parent=str(RECORD), song=str(ROOT / "songs" / "h-now-its-by-you.json"), machine="none",
                  home=tempfile.mkdtemp())


def test_it_comes_from_the_edition_by_name(studio):
    studio.context.parent_title = "Awards performance draft"
    try:
        assert studio.context.from_words() == "from the awards performance draft"
    finally:
        studio.context.parent_title = None


def test_the_editions_own_lines_are_handed_down(studio):
    assert studio.context.parent.composition.get("lines"), "the edition keeps the artist's screen lines"
    words = explain.words_view(studio.version({}, "you"))
    assert not any(w.get("mine") for w in words)
    screen = next(w for w in words if w.get("id") == "screen")
    assert "scrolled" in " ".join(screen["lines"])  # sung as the edition sings it, only not marked yours


def test_comparing_machines_shows_a_verse_that_differs(studio):
    rows = studio.compare({}, ["Ada", "Basil", "Eli"])["machines"]
    assert all("First line" not in m["rows"] for m in rows)
    seen = {m["rows"]["New verse"] for m in rows}
    assert len(seen) > 1
    assert all("They saved it as numbers" not in line for line in seen)  # the first verse is everyone's
