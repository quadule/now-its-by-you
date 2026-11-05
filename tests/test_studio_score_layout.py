"""The score's layout where a person's pointer needs room (docs/history/STUDIO-EDM-TEST.md, second attempt): a region's
length edge is a handle of its own, 10 px, above the next section's seam and not under it (bug 3: the seam
covered all but 1 to 3 px of it, and a drag beside it moved the section). Checked in headless Chrome by hand
(every pixel of each edge is the edge, of each seam the seam, a drag from the edge's middle gives "4 → 8 bars");
this keeps the rules that make it so."""

import re
from pathlib import Path

CSS = (Path(__file__).parent.parent / "songbird" / "studio" / "score.css").read_text()
JS = (Path(__file__).parent.parent / "songbird" / "studio" / "score.js").read_text()


def rule(selector: str) -> dict:
    """The first rule for exactly this selector, as {property: value}."""
    m = re.search(r"(?m)^\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, selector
    return {k.strip(): v.strip() for k, v in (d.split(":", 1) for d in m.group(1).split(";") if ":" in d)}


def px(value: str) -> float:
    return float(value.removesuffix("px"))


def test_a_regions_edge_is_its_own_handle_clear_of_the_next_seam():
    edge, seam = rule(".regioncell > .edge"), rule(".seam")
    assert edge["position"] == "absolute" and edge["right"] == "0" and px(edge["width"]) >= 10
    assert "resize" in edge["cursor"] and int(edge["z-index"]) > int(seam["z-index"])
    assert seam["left"] == "0" and "margin-left" not in seam  # the seam starts where its own cell does
    assert ".region .edge" not in CSS  # not inside the region, where a press began the region's drag
    assert 'region, edge);' in JS and 'edge.parentNode.querySelector(".region")' in JS
