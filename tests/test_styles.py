"""Styles: the record, the palette, the map they travel on, the harmony they may add, and that the seed is untouched."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
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


# --- the palette and the ring ---------------------------------------------------------------------------


def test_the_palette_is_whole():
    from songbird import style as S
    from songbird.synth import instruments

    assert set(S.RING) == set(S.STYLES) and len(S.RING) == len(set(S.RING))
    known = set(instruments.known())
    for s in S.STYLES.values():
        assert set(s.lineup) <= known, s.name
        assert set(s.parts) <= set(s.lineup) and all(lead in s.lineup for lead in s.leads), s.name
        assert abs(sum(s.feels.values()) - 1.0) < 1e-9 and set(s.feels) <= set(S.FEELS), s.name
        for feel in s.feels:
            lo, centre, hi = s.centre(feel)
            assert 0.4 <= lo < centre < hi <= 1.5, (s.name, feel)
        for key in ("intro", "ending", "backing"):
            assert sum(s.options.get(key, {"": 1}).values()) > 0, (s.name, key)


def machines(n):
    from songbird import harvest as HV

    return [HV.fictional(f"m{k}") for k in range(n)]


def test_styles_move_one_step_at_most_and_never_flicker():
    """A machine singing the same parent day after day changes style now and then, never back and forth
    within a week, and only ever to its parent's style or a neighbour's on the ring."""
    from songbird import drift as D, style as S, variation as V

    seed = Style()
    per_year = []
    for voice in machines(6):
        c = V.character(voice)
        days = np.arange(D.parse("2026-01-01"), D.parse("2028-01-01"), 1.0)
        chosen = [S.place(seed, c, D.drift(t, voice.hash)) for t in days]
        assert set(chosen) <= {"ballad", *S.neighbours("ballad")}
        changes = [i for i in range(1, len(chosen)) if chosen[i] != chosen[i - 1]]
        assert all(b - a >= 7 for a, b in zip(changes, changes[1:])), changes
        per_year.append(len(changes) / 2)
    assert 0 < np.mean(per_year) <= 4, per_year


def test_a_child_usually_keeps_its_parents_style():
    """Across machines, dates and parents in every style: most children keep their parent's style, the
    rest take one step; every style is some machines' home."""
    from collections import Counter

    from songbird import drift as D, style as S, variation as V

    kept = total = 0
    homes = Counter()
    for voice in machines(24):
        c = V.character(voice)
        homes[S.RING[int(np.floor(S.home(c) + 0.5)) % len(S.RING)]] += 1
        for k, name in enumerate(S.RING):
            t = D.parse("2026-03-01") + 53.0 * k + 11.0 * len(homes)
            child = S.place(Style(name=name), c, D.drift(t, voice.hash))
            assert child == name or child in S.neighbours(name)
            kept += child == name
            total += 1
    assert 0.45 <= kept / total <= 0.8, kept / total
    assert len(homes) >= 8  # machines are at home all round the ring


def test_a_machine_that_gave_nothing_keeps_its_parents_style():
    from songbird import harvest as HV

    g = G.load(H)
    parent = replace(Params.from_dict(g.seed_params), style=Style(name="gospel", lineage=("ballad", "gospel"),
                                                                   feel="twelve", backing="echo", voices=1))
    child = choose_params(g, parent, HV.Voice(salt="locked-down"))
    assert child.style.name == "gospel" and child.style.lineage == ("ballad", "gospel", "gospel")
    assert (child.style.feel, child.style.backing) == ("twelve", "echo")


def test_a_style_leans_the_singer_and_the_mix_without_compounding():
    """Generation after generation in one style on one machine, the singer's lean settles at the style's
    offset from what the machine would sing without it: it never grows."""
    from songbird import drift as D, harvest as HV, style as S

    g = G.load(H)
    voice = HV.fictional("ada")
    drift = D.drift(D.parse("2026-09-26"), voice.hash)
    plain = choose_params(g, None, voice, drift, style="ballad")
    p = choose_params(g, None, voice, drift, style="shanty")
    for _ in range(12):  # both settle where the machine and the style put them
        plain = choose_params(g, plain, voice, drift, style="ballad")
        p = choose_params(g, p, voice, drift, style="shanty")
    lean = S.STYLES["shanty"].singer["vibrato_depth"]
    got = p.singer.get("vibrato_depth", 28.0) - plain.singer.get("vibrato_depth", 28.0)
    assert abs(got - lean) < 1.0, got
    space = p.mix.get("space", 1.0) - plain.mix.get("space", 1.0)
    assert abs(space - S.STYLES["shanty"].mix["space"]) < 0.05, space
    assert p.style.lineage[-3:] == ("shanty",) * 3 and len(p.style.lineage) <= 16


def test_a_style_takes_the_song_at_its_own_tempo():
    from songbird import style as S

    g = G.load(H)
    song = Params.from_dict(g.seed_params).tempo
    for name, sdef in S.STYLES.items():
        p = choose_params(g, style=name)
        lo, _centre, hi = sdef.centre(p.style.feel)
        assert lo * song - 0.1 <= p.tempo <= hi * song + 0.1, (name, p.tempo)
        assert p.style.name == name and p.style.lineage == ("ballad", name)
        assert (p.band.lineup == {}) == (name == "ballad")
