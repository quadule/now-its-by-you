"""Authored listening editions stay reproducible and keep the seed's tune."""

import json
from pathlib import Path

import pytest

from songbird import edits as E, genome as G
from songbird.realize import choose_params, realize

ROOT = Path(__file__).resolve().parents[1]
H = ROOT / "songs/h-now-its-by-you.json"


@pytest.mark.parametrize("name", ["open-door", "night-wire"])
def test_editions_apply_every_choice_and_survive_as_recorded_edits(name):
    genome = G.load(H)
    wanted = json.loads((ROOT / "editions" / f"{name}.json").read_text())
    clean, problems = E.check(genome, wanted)
    assert clean == wanted and not problems
    resolved = E.resolve(genome, None, None, None, clean)
    assert not resolved.problems
    assert set(resolved.applied) == set(wanted)
    assert E.from_record({"chosen_by_you": resolved.marks}) == wanted
    params = resolved.params
    assert params.style.entrances and params.style.breakdown and not params.style.lift
    assert params.mix["forward"] < 10 and params.band.arc >= 0.9
    plain, edition = realize(genome, choose_params(genome)), realize(genome, params)
    assert [(n.pitch, n.syllable) for n in edition.part("voice")] == [(n.pitch, n.syllable) for n in plain.part("voice")]


def test_ballad_builds_from_harp_and_returns_after_the_last_question():
    genome = G.load(H)
    edits = json.loads((ROOT / "editions/open-door.json").read_text())
    params = E.resolve(genome, None, None, None, edits).params
    score = realize(genome, params)
    verse = next(s for s in score.sections if s[0] == "verse")
    start, end = verse[1:]
    line = (end - start) / 4
    assert any(n.part == "harp" and start <= n.start < start + line for n in score.notes)
    assert not any(n.part == "bass" and start <= n.start < start + line - 0.05 for n in score.notes)
    final = [s for s in score.sections if s[0] == "refrain"][-1]
    start, end = final[1:]
    third_line = start + (end - start) / 2
    upper_band = {"harp", "guitar", "lute", "whistle", "fiddle"}
    assert not any(n.part in upper_band and start + 0.05 <= n.start < third_line - 0.05 for n in score.notes)
    assert any(n.part == "guitar" and third_line - 0.05 <= n.start < end for n in score.notes)


def test_hand_to_hand_changes_the_story_without_changing_the_tune_or_refrain():
    genome = G.load(H)
    wanted = json.loads((ROOT / "editions/hand-to-hand.json").read_text())
    clean, problems = E.check(genome, wanted)
    assert clean == wanted and not problems
    resolved = E.resolve(genome, None, None, None, clean)
    assert not resolved.problems and set(resolved.applied) == set(wanted)
    assert resolved.lyrics.verses == ("box", "wire")
    plain = realize(genome, resolved.params, lyrics=resolved.generated_lyrics)
    edition = realize(genome, resolved.params, lyrics=resolved.lyrics)
    assert [(n.start, n.pitch) for n in edition.part("voice")] == [(n.start, n.pitch) for n in plain.part("voice")]
    assert [n.syllable for n in edition.part("voice") if n.section != "verse"] == [
        n.syllable for n in plain.part("voice") if n.section != "verse"]


def test_one_seed_verse_can_be_edited_without_redrawing_the_other_words():
    genome = G.load(H)
    resolved = E.resolve(genome, None, None, None, {"words.verse.0": {"id": "ship"}})
    assert not resolved.problems and resolved.lyrics.verses == ("ship", "screen")
    assert resolved.lyrics.sections[1:] == resolved.generated_lyrics.sections[1:]
