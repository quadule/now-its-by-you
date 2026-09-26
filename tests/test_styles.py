"""Styles: the record, the palette, the map they travel on, the harmony they may add, and that the seed is untouched."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from songbird import genome as G
from songbird.band import Band
from songbird.realize import Params, choose_params, realize
from songbird.style import Style

ROOT = Path(__file__).parent.parent
SONGS = sorted((ROOT / "songs").glob("*.json"))
H = ROOT / "songs" / "h-now-its-by-you.json"
GOLDEN = Path(__file__).parent / "golden"


# --- the seed is untouched ---------------------------------------------------------------------------


def score_hash(g) -> str:
    score = realize(g, choose_params(g))
    return hashlib.sha256(json.dumps(score.to_dict(), sort_keys=True).encode()).hexdigest()[:16]


def test_every_seed_is_arranged_exactly_as_before():
    """With no style the band plays every song's seed note for note as it did before styles existed
    (golden/seed-scores.json; regenerate only for an intended change to the seed's arrangement)."""
    import os

    path = GOLDEN / "seed-scores.json"
    got = {p.stem: score_hash(G.load(p)) for p in SONGS}
    if os.environ.get("SONGBIRD_UPDATE_GOLDEN") or not path.exists():
        path.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
    assert got == json.loads(path.read_text())


def test_the_seed_of_h_renders_byte_identical(tmp_path):
    """H's seed rendition, audio and all: its id is golden/h-seed.sha256 (441dc83b1d1e... when styles came)."""
    import os

    from songbird import cli

    g = G.load(H)
    record = cli.render_one(g, choose_params(g), tmp_path / "h.flac", phrasing_json=g.source.get("seed_phrasing"))
    path = GOLDEN / "h-seed.sha256"
    if os.environ.get("SONGBIRD_UPDATE_GOLDEN") or not path.exists():
        path.write_text(record["id"] + "\n")
    assert record["id"] == path.read_text().strip()


# --- the record ----------------------------------------------------------------------------------------


def test_old_params_load_with_the_seeds_style_and_band():
    g = G.load(H)
    record = Params.from_dict(g.seed_params).to_dict()
    # the seed's own style and band leave no trace in a record, as in every record from before styles
    assert "style" not in record and "lineup" not in record["band"]
    p = Params.from_dict(record)
    assert p.style == Style() and p.style.seed and p.band.lineup == {} and p.band == Band()
    assert choose_params(g) == p


def test_a_style_and_a_lineup_survive_the_record():
    g = G.load(H)
    style = Style(name="bluegrass", lineage=("ballad", "oldtime", "bluegrass"), feel="double", harmony=0.4,
                  intro="count", alone=2, alone_with="banjo", breakdown=True, lift=True, ending="cold",
                  entrances=True, backing="thirds", voices=2)
    band = replace(Band(), lineup={"banjo": 1.1, "mandolin": 0.9, "fiddle": 1.0, "guitar": 1.0, "bass": 1.0})
    p = replace(Params.from_dict(g.seed_params), style=style, band=band)
    again = Params.from_dict(json.loads(json.dumps(p.to_dict())))
    assert again == p and isinstance(again.style, Style) and again.style.lineage == style.lineage
    assert again.band.plays("banjo") and not again.band.plays("lute") and again.band.gain("mandolin") == 0.9


def test_style_values_are_held_to_their_options():
    s = Style.from_dict({"feel": "polka", "harmony": 3, "ending": "explode", "voices": 99, "future": 1,
                         "lineage": ["a"] * 40, "bridge": "double"})
    assert (s.feel, s.harmony, s.ending, s.voices, s.bridge) == ("", 1.0, "", 6, "")
    assert len(s.lineage) == 16
    assert Band.from_dict({"lineup": [["banjo", 5.0], ["kit", -1]]}).lineup == {"banjo": 2.0, "kit": 0.0}
