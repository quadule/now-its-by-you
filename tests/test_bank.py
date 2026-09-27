from pathlib import Path

import pytest

from songbird import bank as B, genome as G

SONGS = sorted(Path(__file__).parent.parent.joinpath("songs").glob("*.json"))
H = Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json"


@pytest.mark.parametrize("path", SONGS, ids=lambda p: p.stem)
def test_every_way_a_bank_line_can_be_sung_fits_the_tune(path):
    g = G.load(path)
    if "bank" not in g.source:
        pytest.skip("no bank")
    summary = B.check(g)
    assert summary["verses"] >= len(g.seed_verses) and summary["couplets"] >= 1


def test_coupled_slots_are_chosen_together():
    slots = {"who": {"noun": ["man", "girl"], "he": ["he", "she"]}, "day": ["Mon-day", "Fri-day"]}
    lines = ["A {who.noun} kept it on {day};", "{who.he} kept it well."]
    assert list(B.expansions(lines, slots)) == [
        ["A man kept it on Mon-day;", "he kept it well."],
        ["A man kept it on Fri-day;", "he kept it well."],
        ["A girl kept it on Mon-day;", "she kept it well."],
        ["A girl kept it on Fri-day;", "she kept it well."],
    ]
    assert B.ways(lines, slots) == 4
    with pytest.raises(ValueError, match="coupled"):
        B.fill(["{who} kept it"], slots, {"who": 0})
    with pytest.raises(ValueError, match="doesn't define"):
        list(B.expansions(["{when} it was"], slots))


def test_a_slot_option_that_breaks_the_count_or_the_dictionary_is_caught():
    g = G.load(H)
    wax = next(v for v in g.source["bank"]["verses"] if v["id"] == "wax")
    verse = g.sections["verse"].phrases
    B.check_block(wax["lines"], wax["slots"], verse, g.phrases, g.lexicon, "wax")
    with pytest.raises(ValueError, match="syllables"):
        B.check_block(wax["lines"], {"day": ["Sat-ur-day"]}, verse, g.phrases, g.lexicon, "wax")
    with pytest.raises(ValueError, match="can't sing"):
        B.check_block(wax["lines"], {"day": ["Qzx-day"]}, verse, g.phrases, g.lexicon, "wax")
    with pytest.raises(ValueError, match="never used"):
        B.check_block(wax["lines"], {"day": ["Tues-day"], "moon": ["June"]}, verse, g.phrases, g.lexicon, "wax")


def test_a_lines_problem_is_named_for_its_caller_to_say():
    g = G.load(H)
    wax = next(v for v in g.source["bank"]["verses"] if v["id"] == "wax")
    line = B.fill(wax["lines"], wax["slots"], {name: 0 for name in wax["slots"]})[0]
    notes = len(g.phrases[g.sections["verse"].phrases[0]].sung)
    assert B.line_problem(line, notes, g.lexicon) is None
    assert B.line_problem(line, notes + 1, g.lexicon) == ("count", notes)
    first = line.split()[0]
    assert B.line_problem(line.replace(first, f"*{first}", 1), notes, g.lexicon) == ("mark", f"*{first}")
    assert B.line_problem(line.replace(first, "Qzx", 1), notes, g.lexicon)[:2] == ("unknown", "Qzx")
    assert B.misplaced_mark(line.replace(first, f"*{first}*", 1)) is None


def test_the_banks_question_words_are_the_fixed_refrains():
    g = G.load(H)
    assert [B.unmarked(l) for l in G.turns(g.refrain[0])] == [
        f"Who {w} this song? No-bo-dy knows." for w in g.source["bank"]["refrain"]["slots"]["question"]]


def test_a_focus_mark_wraps_a_whole_word():
    g = G.load(H)
    wax = next(v for v in g.source["bank"]["verses"] if v["id"] == "wax")
    verse = g.sections["verse"].phrases
    marked = [wax["lines"][0].replace("wax", "*wax*")] + wax["lines"][1:]
    B.check_block(marked, wax["slots"], verse, g.phrases, g.lexicon, "wax")  # counts and pronunciation ignore the mark
    B.check_marks("but not one ma-chine ev-er knew it by *heart*.", "wire")
    B.check_marks("Who {*made*|*sang*} this song?".replace("{*made*|*sang*}", "*made*"), "refrain")
    for bad in ("knew it by *heart.", "knew it by he*art*", "knew it by **heart**", "knew it by *", "*num-*bers"):
        with pytest.raises(ValueError, match="focus mark"):
            B.check_marks(bad, "wire")


def test_a_refrains_other_heads_are_checked_like_its_own():
    import json

    data = json.loads(H.read_text())
    B.check(G.from_dict(data))
    so = data["bank"]["refrain"]["heads"][0]
    for change, why in ((lambda h: h["fixed"].update(question="whistled"), "isn't one of the question"),
                        (lambda h: h["fixed"].update(place="desert"), "which its lines don't sing"),
                        (lambda h: h["lines"].__setitem__(0, "Who {question} this song? No-bo-dy, so then"), "syllables"),
                        (lambda h: h.update(id="knows"), "ids repeat"),
                        (lambda h: h["lines"].__setitem__(1, "it's {yours} if you sing it and then who knows?"), "no slots")):
        broken = json.loads(json.dumps(data))
        change(broken["bank"]["refrain"]["heads"][0])
        with pytest.raises(ValueError, match=why):
            B.check(G.from_dict(broken))
    assert so["id"] == "so" and so["by"] == "artist"
    # and the rules with them: a head can't fix a word kept once a song, a head asking its own question is sung
    # once a song, and a distinct slot is one the refrain's own lines sing
    for change, why in ((lambda d: d["bank"]["rules"]["refrain"].update(once_per_song=["while"], distinct=["then"]), "once a song"),
                        (lambda d: d["bank"]["rules"]["refrain"].pop("head_repeat"), "head_repeat false"),
                        (lambda d: d["bank"]["rules"]["refrain"].update(distinct=["question"]), "distinct slots")):
        broken = json.loads(json.dumps(data))
        change(broken)
        with pytest.raises(ValueError, match=why):
            B.check(G.from_dict(broken))


def test_the_rules_may_hold_a_slot_to_one_word_first_and_last():
    """H's first and last refrains ask about *this* song; the ones between may ask about *that* song or *the*
    song, so the one song stands for all of them. The rules name the slot and a word it has; nothing else."""
    g = G.load(Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json")
    refrain, rules = g.source["bank"]["refrain"], g.source["bank"]["rules"]["refrain"]
    assert rules["first"] == rules["last"] == {"this": "this"} and B.refrain_rules_problem(refrain, rules) is None
    assert "isn't one of its words" in B.refrain_rules_problem(refrain, {**rules, "first": {"this": "those"}})
    assert "question_first" in B.refrain_rules_problem(refrain, {**rules, "last": {"question": "owns"}})
    assert "don't sing" in B.refrain_rules_problem(refrain, {**rules, "first": {"place": "wa-ter"}})
