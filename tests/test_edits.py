"""A person's edits on top of the program's choices (songbird.edits): with none, nothing changes; each edit
takes the place of the choice it names within its bounds, inside the table so a decision that reads it reads
the person's; one that can't be kept is left out and said why; the record marks each as a person's."""

import json
from pathlib import Path

from songbird import drift as D, edits as E, harvest as H, variation as V
from songbird.genome import load
from songbird.realize import Params, choose_params

ROOT = Path(__file__).parent.parent
g = load(ROOT / "songs" / "h-now-its-by-you.json")
b = load(ROOT / "songs" / "b-coal-from-the-fire.json")
ADA = H.fictional("ada")
DAY = D.drift(D.parse("2026-09-26"), ADA.hash)


def test_no_edits_change_nothing():
    for genome in (g, b):
        for voice, drift in ((None, None), (ADA, DAY), (H.Voice(), DAY)):
            plain = choose_params(genome, None, voice, drift)
            assert choose_params(genome, None, voice, drift, overrides={}) == plain
            assert choose_params(genome, None, voice, drift, overrides=E.Overrides(genome, {})) == plain


def test_each_edit_takes_its_place_within_bounds():
    edits, problems = E.check(g, {"tempo": 400, "tonic": 50, "mode": "aeolian", "band.pattern": "air",
                                  "band.lead": "fiddle", "band.density": 1.7, "band.drum": 0, "mix.space": 1.25,
                                  "mix.forward": 30, "roll": 1})
    assert not problems
    assert edits["tempo"] == 124.8 and edits["tonic"] == 57 and edits["band.density"] == 1.0 and edits["mix.forward"] == 15
    o = E.Overrides(g, edits)
    p = choose_params(g, None, ADA, DAY, overrides=o)
    plain = choose_params(g, None, ADA, DAY)
    assert (p.tempo, p.tonic, p.mode) == (124.8, 57, "aeolian")
    assert (p.band.pattern, p.band.lead, p.band.density, p.band.drum) == ("air", "fiddle", 1.0, 0.0)
    assert p.mix["space"] == 1.25 and p.mix["forward"] == 15 and p.mix["rt60"] == plain.mix["rt60"]
    assert p.seed == E.rolled(plain.seed, 1) != plain.seed
    assert set(o.applied) == {"tempo", "tonic", "mode", "band.pattern", "band.lead", "band.density", "band.drum",
                              "mix.space", "mix.forward", "roll"}
    # everything not edited is the program's own
    same = {k: v for k, v in plain.to_dict().items() if k not in ("tempo", "tonic", "mode", "band", "mix", "seed", "leanings")}
    # the learned singer's blend follows where the song sits, so a new key may bring other singers into it
    unblended = lambda d: {**d, "singer": {k: v for k, v in d.get("singer", {}).items() if k != "timbre"}}  # noqa: E731
    assert unblended({k: v for k, v in p.to_dict().items() if k in same}) == unblended(same)


def test_a_chosen_minor_mode_leans_the_words_darker_as_the_machines_own_would():
    plain = choose_params(g, None, ADA, DAY)
    assert plain.mode == "ionian"
    minor = choose_params(g, None, ADA, DAY, overrides={"mode": "aeolian"})
    before, after = plain.leanings["mood_weights"], minor.leanings["mood_weights"]
    assert after["dark"] / after["light"] > before["dark"] / before["light"]


def test_edits_without_a_machine_or_a_day():
    p = choose_params(g, overrides={"tempo": 80, "form.verses": 3})
    assert p.tempo == 80 and sum(n == "verse" for n in p.form) == 3


def test_refused_edits_say_why():
    edits, problems = E.check(g, {"mode": "lydian", "band.pattern": "polka", "colour": "red", "phrasing": "nobody",
                                  "tempo": "fast"})
    why = {p["path"]: p["why"] for p in problems}
    assert "keep their shape only in ionian, mixolydian, aeolian" in why["mode"]
    assert "lilt, strum, pick, air" in why["band.pattern"]
    assert why["colour"] == "there's no such choice"
    assert "no such phrasing" in why["phrasing"]
    assert "isn't a value" in why["tempo"]
    assert not edits


def test_the_shape_changes_part_by_part_and_holds_as_the_day_moves():
    generated = choose_params(g, None, ADA, DAY).form
    parts = E.shape(g, generated)
    assert E.build(g, parts) == tuple(generated)
    o = E.Overrides(g, {"form.verses": 4, "form.intro": False, "form.pairs": True})
    p = choose_params(g, None, ADA, DAY, overrides=o)
    got = E.shape(g, p.form)
    assert (got["verses"], got["intro"], got["pairs"]) == (4, False, True)
    assert not o.problems
    # a year on the machine's own shape moves, the person's parts hold
    later = D.drift(D.parse("2027-09-26"), ADA.hash)
    q = choose_params(g, None, ADA, later, overrides={"form.verses": 4, "form.intro": False})
    assert E.shape(g, q.form)["verses"] == 4 and not E.shape(g, q.form)["intro"]
    # five verses are refused, and the rest of the shape kept
    o = E.Overrides(g, {"form.verses": 5, "form.tag": True})
    p = choose_params(g, None, ADA, DAY, overrides=o)
    assert o.problems[0]["path"] == "form.verses" and "2 to 4 verses" in o.problems[0]["why"]
    assert E.shape(g, p.form)["tag"] and E.shape(g, p.form)["verses"] == parts["verses"]
    for choice in E.shapes(g, generated):
        assert choice["allowed"] == (E.form_problem(g, E.build(g, dict(parts, **{choice["part"]: choice["value"]}))) is None)


def test_words_are_kept_or_said_why_and_the_record_marks_the_choices():
    edits, _ = E.check(g, {"date": "2027-01-05", "tempo": 90, "words.verse.1": {"id": "wire"},
                           "words.verse.7": {"id": "ink"}, "words.tag": "loo", "words.refrain": {"while": "if"}})
    d = D.drift(D.parse("2027-01-05"), ADA.hash)
    r = E.resolve(g, None, ADA, d, edits, day_chosen=True)
    assert r.lyrics.verses[1] == "wire"
    why = {p["path"]: p["why"] for p in r.problems}
    assert "no verse 8" in why["words.verse.7"]
    if "tag" not in r.params.form:
        assert "no tag" in why["words.tag"]
    assert {"date", "tempo", "words.verse.1", "words.refrain"} <= set(r.applied)
    marks = r.marks
    assert marks["tempo"] == {"value": 90.0, "was": r.generated.tempo}
    assert marks["words.verse.1"]["value"]["id"] == "wire"
    assert marks["words.verse.1"]["was"]["id"] == r.generated_lyrics.verses[1]
    assert marks["words.refrain"] == {"value": {"while": "if"}, "was": {"while": r.generated_lyrics.sections[1].slots["while"]}}
    refused = E.resolve(g, None, ADA, d, {"words.refrain": {"then": "it grows"}}, day_chosen=True)
    assert "chosen refrain by refrain" in refused.problems[0]["why"]  # each refrain ends its own way
    assert marks["date"]["value"] == "2027-01-05"
    # replaying the marks as edits makes the same rendition
    again = E.resolve(g, None, ADA, d, E.check(g, E.from_record({"params": {}, "chosen_by_you": marks}))[0],
                      day_chosen=True)
    assert again.params == r.params and again.lyrics == r.lyrics


def test_a_phrasing_is_marked_by_what_it_is_never_whose():
    phrasing = {"source": "song", "source_detail": "2 sung take(s)", "phrases": {"r1": []}}
    mark = E.phrasing_mark(phrasing)
    assert mark["value"] == "a person's way" and mark["detail"] == "2 sung take(s)" and len(mark["digest"]) == 16
    assert E.phrasing_mark({"source_detail": "5 sung takes by 3 singers"})["value"] == "everyone's way"
    edits = {"phrasing": "milo-winningham"}
    r = E.resolve(g, None, ADA, DAY, edits, phrasing_json=phrasing)
    assert "milo" not in json.dumps(r.marks).lower()


def test_keep_these_words_holds_them_through_a_roll():
    p = choose_params(g, None, ADA, DAY)
    r = E.resolve(g, None, ADA, DAY, {})
    kept = E.keep_words(g, r.lyrics)
    rolled = E.resolve(g, None, ADA, DAY, {**kept, "roll": 3})
    assert rolled.params.seed != p.seed
    assert [s.lines for s in rolled.lyrics.sections] == [s.lines for s in r.lyrics.sections]
    assert not rolled.problems


def test_old_records_still_load():
    old = {"tonic": 62, "mode": "ionian", "tempo": 96, "form": list(g.seed_params["form"]), "room": {"rt60": 0.8}}
    assert Params.from_dict(old).mix["rt60"] == 0.8
    assert V.choose(g, None, None, None) == Params.from_dict(g.seed_params)


def test_a_refrains_own_head_and_words_are_marked_and_replay():
    r = E.resolve(g, None, ADA, DAY, {})
    first = next(s for s in r.lyrics.sections if s.block == "refrain")
    other = "when" if first.slots["while"] != "when" else "if"
    edits = {"words.refrain.1": {"head": "so"}, "words.refrain.0": {"slots": {"while": other}}}
    done = E.resolve(g, None, ADA, DAY, edits)
    refrains = [s for s in done.lyrics.sections if s.block == "refrain"]
    assert not done.problems and refrains[1].head == "so" and refrains[1].lines[0].startswith("Who *wrote*")
    assert refrains[0].slots["while"] == other and refrains[1].slots["then"] == "who knows"
    thens = [s.slots["then"] for s in refrains if "then" in s.slots]
    assert len(set(thens)) == min(len(thens), 3)  # each ends its own way
    assert done.marks["words.refrain.1"]["value"] == {"head": "so"}
    assert done.marks["words.refrain.0"] == {"value": {"slots": {"while": other}}, "was": {"slots": {"while": first.slots["while"]}}}
    again = E.resolve(g, None, ADA, DAY, E.check(g, E.from_record({"params": {}, "chosen_by_you": done.marks}))[0])
    assert again.lyrics == done.lyrics
    refused = E.resolve(g, None, ADA, DAY, {"words.refrain.0": {"head": "so"}})
    assert refused.problems and "always sings the knows head" in refused.problems[0]["why"]
