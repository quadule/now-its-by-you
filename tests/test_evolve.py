"""Evolution: a lineage keeps nearly all of its parent's tune and words, changing a little a generation;
one machine's song holds for weeks and changes one thing at a time, never flickering day to day; the
words always keep the bank's rules; and without a machine or a date nothing moves at all."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import arrange as A
from songbird import cli
from songbird import drift as D
from songbird import evolve as E
from songbird import genome as G
from songbird import harvest as H
from songbird import variants as V
from songbird import variation
from songbird.realize import Params, choose_params

ROOT = Path(__file__).parent.parent
LEAD = ROOT / "songs" / "h-now-its-by-you.json"
MACHINES = ("ada", "bo", "cy", "dee")


@pytest.fixture(scope="module")
def h():
    return G.load(LEAD)


def sing_on(g, name, date, parent=None, log=None):
    voice = H.fictional(name)
    return choose_params(g, parent, voice, D.drift(D.parse(date) if isinstance(date, str) else date, voice.hash), log=log)


def lineage(g, n, generations, rng):
    """A lineage handed from machine to machine, two to five months apart."""
    parent = Params.from_dict(g.seed_params)
    t = D.parse("2026-10-01") + rng.uniform(0, 365)
    out = []
    for gen in range(generations):
        t += rng.uniform(60, 150)
        log: list = []
        child = sing_on(g, f"lineage{n}-{gen}", t, parent, log)
        out.append((parent, child, log))
        parent = child
    return out


def test_without_a_machine_or_a_date_nothing_moves(h):
    seed = Params.from_dict(h.seed_params)
    assert choose_params(h) == seed and cli.words(h, seed) is None  # the seed: its tune as written, its own words
    parent = sing_on(h, "ada", "2027-03-01")
    assert choose_params(h, parent) == parent  # a replay sings its record exactly
    neutral = choose_params(h, parent, H.Voice(salt="locked-down"))  # a locked-down machine and no date
    assert (neutral.variants, neutral.words) == (parent.variants, parent.words)
    assert neutral.generation == parent.generation + 1


def test_a_lineage_keeps_nearly_all_and_gathers_variants(h):
    rng = np.random.default_rng(11)
    kept, counts, swaps = [], [[] for _ in range(6)], []
    for n in range(40):
        for gen, (parent, child, log) in enumerate(lineage(h, n, 6, rng)):
            assert not V.problems(h, child.variants)
            assert child.generation == parent.generation + 1
            if parent.variants:
                kept.append(len({v.what for v in child.variants} & {v.what for v in parent.variants}) / len(parent.variants))
            counts[gen].append(len(child.variants))
            swaps.append(sum(e["change"] == "swapped" for e in log))
            assert sum(e["change"] == "learned" for e in log) <= 2
            for v in child.variants:  # each came in some generation and says so
                assert 1 <= v.born <= child.generation and v.source == "drift"
    assert np.mean(kept) >= 0.9, np.mean(kept)  # a child keeps nearly all of its parent's
    means = [np.mean(c) for c in counts]
    assert means[-1] > means[2] > means[0] > 0.2, means  # and they accumulate, a folk tune's way
    assert 0.1 <= np.mean(swaps) <= 0.6 and max(swaps) <= 1, np.mean(swaps)  # occasionally, one swap


def test_the_words_always_keep_the_rules(h):
    rng = np.random.default_rng(12)
    for n in range(25):
        for parent, child, log in lineage(h, n, 5, rng):
            assert not A.held_problem(h, child.form, child.words), (child.form, child.words)
            lyrics = A.sing(h, child.form, child.words)
            assert lyrics.held and lyrics.lines_for(h, child.form)
            assert not any(e["change"] == "drawn" for e in log)  # the held words never needed drawing afresh
            # a child's words are its parent's, but for the form's needs and at most one swap
            pv = [v["id"] for v in (parent.words or E.seed_words(h, parent))["verses"]]
            cv = [v["id"] for v in child.words["verses"]]
            swapped = [e for e in log if e["change"] == "swapped"]
            assert len(swapped) <= 1
            added = [e for e in log if e["change"] == "added" and e["where"].startswith("verse")]
            common = [v for v in cv if v in pv]
            assert len(cv) - len(common) <= len(added) + (1 if swapped and swapped[0]["where"].startswith("verse ") else 0)


@pytest.mark.parametrize("name", MACHINES)
def test_one_machine_holds_for_weeks_and_never_flickers(h, name):
    voice = H.fictional(name)
    days = np.arange(D.parse("2026-10-01"), D.parse("2028-10-01"), 1.0)
    rows = [choose_params(h, None, voice, D.drift(t, voice.hash)) for t in days]
    for label, key in (("tune", lambda p: tuple(v.what for v in p.variants)), ("words", lambda p: repr(p.words))):
        states = [key(p) for p in rows]
        changes = [i for i in range(1, len(states)) if states[i] != states[i - 1]]
        for i in changes:  # nothing changes back within a week, unless the form did (the season's call)
            back = any(states[j] == states[i - 1] for j in range(i + 1, min(i + 8, len(states))))
            forms = {rows[j].form for j in range(max(i - 1, 0), min(i + 8, len(states)))}
            assert not back or (label == "words" and len(forms) > 1), (label, D.when(days[i]).date())
        per_year = len(changes) / 2
        assert per_year <= (6 if label == "tune" else 14), (label, per_year)
    assert any(p.variants for p in rows)  # a machine does have its own way with the tune


def test_a_machine_singing_its_own_last_rendition_changes_only_when_a_clock_turns(h):
    voice = H.fictional("bo")
    t = D.parse("2027-02-01")
    first = choose_params(h, None, voice, D.drift(t, voice.hash))
    assert first.made == {"by": voice.hash[:12], "at": round(t, 6)}
    again = choose_params(h, first, voice, D.drift(t + 1, voice.hash))  # the next day, from its own last
    assert again.variants == first.variants and again.words == first.words
    counts = []
    parent = first
    for k in range(1, 157):  # every week for three years
        parent = choose_params(h, parent, voice, D.drift(t + 7 * k, voice.hash))
        counts.append(len(parent.variants))
    assert counts[-1] > counts[10]  # a same-machine chain gathers variants at the clocks' pace
    other = choose_params(h, first, H.fictional("cy"), D.drift(t + 1, H.fictional("cy").hash))
    assert other.generation == first.generation + 1  # a hand-off takes its turn at everything


def test_an_ornamenting_machine_ornaments_more():
    from songbird.variation import Character

    ornate = Character(known=frozenset({"identity", "richness"}), richness=1.0, hash="x")
    plain = Character(known=frozenset({"identity", "richness"}), richness=-1.0, hash="x")

    class Ctx:
        def __init__(self, c):
            self.c, self.drift = c, None

    assert E.appetite(Ctx(ornate), 0.0) > 0.6 > 0.4 > E.appetite(Ctx(plain), 0.0)
    a, b = E.kind_weights(ornate), E.kind_weights(plain)
    assert a["grace"] / a["leap"] > b["grace"] / b["leap"]


def test_the_clock_holds_for_a_stretch_and_never_repeats():
    t = np.arange(D.parse("2026-01-01"), D.parse("2031-01-01"), 0.25)
    k = [D.epoch(x, "abc", "swap", 40, 110)[0] for x in t]
    starts = sorted({D.epoch(x, "abc", "swap", 40, 110) for x in t})
    lengths = np.diff([s for _, s in starts])
    assert all(b == a or b == a + 1 for a, b in zip(k, k[1:]))  # stretches follow one another
    assert lengths.min() >= 20 and lengths.max() <= 165 and len(set(np.round(lengths, 3))) == len(lengths)
    assert all(abs(s - round(s)) > 1e-6 for _, s in starts)  # never at midnight, let alone a month's start
    other = {round(s, 6) for _, s in {D.epoch(x, "abd", "swap", 40, 110) for x in t}}
    assert not other & {round(s, 6) for _, s in starts}  # every machine's clocks turn at their own times
    for x in np.random.default_rng(0).uniform(D.parse("2026-01-01"), D.parse("2031-01-01"), 50):
        kk, start = D.epoch(x, "abc", "swap", 40, 110)
        assert start <= x and D.epoch(start, "abc", "swap", 40, 110) == (kk, start)
        assert D.epoch(start - 1e-6, "abc", "swap", 40, 110)[0] == kk - 1  # a stretch starts where the last ends


def test_old_records_and_flac_paths_give_their_words(h, tmp_path):
    drawn = A.arrange(h, tuple(h.seed_params["form"]), 7)
    record = {"params": Params.from_dict(h.seed_params).to_dict(), "lyrics": drawn.to_dict()}
    (tmp_path / "old.json").write_text(json.dumps(record))
    parent = cli._parent(str(tmp_path / "old.flac"), h)  # the .flac's record, beside it
    assert parent.words == A.hold(h, drawn) and A.sing(h, parent.form, parent.words).to_dict()["sections"] == \
        drawn.to_dict()["sections"]
    child = sing_on(h, "ada", "2027-01-05", parent)
    kept = {v["id"] for v in child.words["verses"]} & {v["id"] for v in parent.words["verses"]}
    assert kept  # the child keeps what its parent sang


def test_the_record_says_what_changed_and_why(h):
    log: list = []
    parent = sing_on(h, "ada", "2026-11-01")
    child = sing_on(h, "fox", "2027-03-15", parent, log)
    story = cli.evolution(h, child, parent, A.sing(h, child.form, child.words), log)
    assert (parent.generation, child.generation) == (0, 1)  # sung from the genome, then handed on: as the record counts
    assert story["changes"] == log
    assert all(e.get("why") for e in log) and all(e["what"] in ("tune", "words") for e in log)
    assert story["distance"]["seed"] >= 0 and len(story["variants"]) == len(child.variants)
    assert cli.evolution(h, Params.from_dict(h.seed_params), None) is None  # the seed's record is as it was
    assert E.diff(h, parent, parent) == []
    what = E.diff(h, parent, child)
    assert {d["what"] for d in what} <= {"tune", "words"}
    for entry in log:
        if entry["change"] in ("learned", "forgot"):
            assert any(d["about"] == E.V.describe(h, V.Variant.from_dict(entry["variant"])) for d in what)


def test_a_form_set_by_hand_fits_the_words_held(h):
    voice = H.fictional("dee")
    d = D.drift(D.parse("2027-06-01"), voice.hash)
    p = choose_params(h, None, voice, d)
    longer = ("verse", "refrain", "verse", "refrain", "verse", "refrain", "turn", "verse", "bridge", "refrain")
    words = cli.words(h, replace(p, form=longer), sung_by_a_machine=True, voice=voice, drift=d)
    assert words.held and len(words.verses) == 4 and not A.problem(h, longer)
    held = [v["id"] for v in p.words["verses"]]
    assert len(held) < 4 and [v for v in words.verses if v in held] == held  # the held verses, in their order, and more


def test_held_words_sing_exactly_what_was_drawn(h):
    for form in (tuple(h.seed_params["form"]),
                 ("verse", "refrain", "verse", "refrain", "turn", "verse", "refrain", "bridge", "bridge2", "refrain", "tag")):
        for seed in range(40):
            drawn = A.arrange(h, form, seed)
            held = A.hold(h, drawn)
            assert json.loads(json.dumps(held)) == held  # plain JSON, as a record keeps it
            again = A.sing(h, form, held)
            assert [s.to_dict() for s in again.sections] == [s.to_dict() for s in drawn.sections]
            assert A.hold(h, again) == held


def test_the_studio_can_check_an_edit_exactly_as_the_drift_is(h):
    p = sing_on(h, "cy", "2027-09-09")
    edit = json.loads(json.dumps(p.words))
    edit["refrain"]["rounds"][0]["id"] = "canon"
    assert A.check(h, p.form, edit) and not A.check(h, p.form, p.words)
    edit = json.loads(json.dumps(p.words))
    edit["verses"][0]["id"] = "trench"  # a rare variant verse can't open a song
    assert A.check(h, p.form, edit)
    assert variation.leanings(p.leanings) is not None


def test_words_held_before_each_refrain_had_its_own_sing_as_they_did(h):
    """Held words from before (the refrain's once-a-song words, a couplet for each refrain but the last, the
    question turning in order) are read as the refrains they sang, and a child fits them to the rules."""
    form = tuple(h.seed_params["form"])
    old = {"verses": [{"id": "wire", "slots": {}}, {"id": "screen", "slots": {"many": "mil-lion"}}],
           "refrain": {"slots": {"while": "when", "then": "it grows"},
                       "couplets": [{"id": "true", "slots": {}}, {"id": "blue", "slots": {}}]},
           "bridge": [{"id": "canon", "slots": {"place": "wa-ter", "ember": "coal", "where": "dark"}}], "tag": "la"}
    lyrics = A.sing(h, form, old)
    refrains = [s for s in lyrics.sections if s.block == "refrain"]
    assert [s.id for s in refrains] == ["true", "blue", "canon"] and lyrics.questions == ("made", "sang", "owns")
    assert all(s.slots["while"] == "when" and s.slots["then"] == "it grows" and s.head is None for s in refrains)
    main = A.refrain_heads(h)[0]
    assert A.hold(h, lyrics)["refrain"]["rounds"][1] == {
        "head": main, "words": {"question": "sang", "while": "when", "then": "it grows"}, "id": "blue", "slots": {}}
    lone = ("verse", "refrain", "verse", "bridge")  # a lone refrain asks what the first asks, and sings the canon
    assert A.sing(h, lone, old).questions == ("made",) and A.sing(h, lone, old).couplets == ("canon",)
    parent = Params.from_dict({**h.seed_params, "words": old})
    child = sing_on(h, "ada", "2027-01-05", parent)
    assert not A.held_problem(h, child.form, child.words) and "rounds" in child.words["refrain"]


def test_each_refrain_of_a_lineage_keeps_words_of_its_own(h):
    """Down lineages, refrains hand on their own words: other heads between the first and last now and
    then, questions that differ, and while and then that differ from refrain to refrain."""
    rng = np.random.default_rng(5)
    heads, questions, own = set(), set(), 0
    for n in range(12):
        for parent, child, log in lineage(h, 100 + n, 4, rng):
            rounds = A.rounds(h, child.words)
            heads.update(r["head"] for r in rounds[1:-1])
            questions.update(r["words"].get("question") for r in rounds[1:-1])
            own += len({(r["words"].get("while"), r["words"].get("then")) for r in rounds}) > 1
            assert rounds[0]["head"] == rounds[-1]["head"] == A.refrain_heads(h)[0]
            assert [r["words"]["question"] for r in (rounds[0], rounds[-1])] == ["made", "owns"]
    assert heads == {"knows", "so"} and len(questions) >= 3 and own > 24


def test_a_verse_held_before_the_bank_gave_it_swaps_keeps_its_place(h):
    """A lineage that held the skip verse before it swapped its girls and its yard keeps singing it, with
    the machine's picks for the words it now swaps, rather than leaving verses out."""
    parent = sing_on(h, "ada", "2027-01-05")
    words = json.loads(json.dumps(parent.words))
    at = 0 if words["verses"][0]["id"] != "skip" and all(v["id"] != "skip" for v in words["verses"]) else None
    if at is None:
        pytest.skip("this lineage already sings the skip verse")
    words["verses"][at] = {"id": "skip", "slots": {}}
    assert A.held_problem(h, parent.form, words)  # as held, it can't be sung: the verse has words to swap now
    log: list = []
    fitted = E.fit(h, parent.form, words, E.Picker(h), log)
    assert [v["id"] for v in fitted["verses"]] == [v["id"] for v in words["verses"]]
    assert set(fitted["verses"][at]["slots"]) == {"kids", "yard"} and not A.held_problem(h, parent.form, fitted)
    assert any(e["change"] == "added" and e["where"] == f"verse {at + 1}" for e in log)
