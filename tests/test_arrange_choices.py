"""A person's choices of words (arrange.keep, options, problem with chosen): every choice offered is kept in
its place, everything not chosen is drawn around it within the rules, every refusal says why in one sentence,
and drawing without choices is exactly as it was."""

import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

import pytest

from songbird import arrange as A, genome as G

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import recording_sets as R  # noqa: E402  (tools/recording_sets.py)

g = G.load(ROOT / "songs" / "h-now-its-by-you.json")
SETS = ROOT / "tools" / "sets" / "h-now-its-by-you.json"
SEED_FORM = tuple(g.seed_params["form"])
LONG = ("intro", "verse", "refrain", "turn", "verse", "refrain", "turn", "verse", "refrain", "bridge", "bridge2",
        "refrain", "tag")
FOUR = ("verse", "refrain", "verse", "verse", "refrain", "turn", "verse", "refrain", "bridge", "refrain", "tag", "outro")
GOLDEN = Path(__file__).parent / "golden" / "h-words.sha256"
HEADS = {g.source["bank"]["refrain"].get("id", "refrain"): g.source["bank"]["refrain"]} | {
    h["id"]: h for h in g.source["bank"]["refrain"].get("heads", [])}


def test_drawing_without_choices_is_as_it_was():
    """The words golden, over 600 draws with and without leanings, so the pin-free draw consumes chance
    exactly as before: computed before choices were added, and again when each refrain came to draw words
    of its own, when the skip and mind verses gained the artist's swaps, when each refrain came to end its
    own way, and when seven more heads came (2026-09-26; the refrain's own changes moved every verse, bridge
    and tag drawn as before), and when the artist dropped the go head (2026-09-26), and when the given stanza went and owed, borrow, slow and
    four verses came (mic, search, misheard, choir; 2026-09-26), and when the first refrain came to ask who
    made, wrote or sang it (question_first, 2026-09-27: only refrain questions moved), and when the bird verse's
    last two lines were rewritten with a carry swap, and the wind couplet, the bone and border verses and the lyric review's six came, and the refrain came to ask about this, that or the song (2026-09-27), and when the daisy verse and the grew
    head came, two heads asking the same question as written never sharing a song (2026-09-27)."""
    lean = A.Leanings(mood_weights={"light": 2.0, "dark": 0.5}, era_bias=-0.4, rarity_appetite=0.6,
                      vocabulary=frozenset({"sea", "ship", "fiddle", "bird"}))
    digest = hashlib.sha256()
    for form in (SEED_FORM, LONG, FOUR):
        for seed in range(100):
            for leanings in (None, lean):
                digest.update(json.dumps(A.arrange(g, form, seed, leanings).to_dict(), sort_keys=True).encode())
    assert digest.hexdigest() == GOLDEN.read_text().strip()
    assert A.arrange(g, SEED_FORM, 7, None, {}) == A.arrange(g, SEED_FORM, 7)


def test_a_refusal_says_the_rule_it_breaks():
    rules = A._song(g).checks
    verses = A._song(g).verses
    rng = random.Random(3)
    for _ in range(4000):
        chosen = rng.sample(verses, rng.choice([2, 3, 4]))
        why = rules.why(chosen)
        assert (why is None) == (rules.together(chosen) and rules.in_order(chosen))
        if why:
            assert why[0].islower() and not why.endswith(".") and len(why) < 200
    assert "sung already" in rules.why([verses[0], verses[0]])


def test_every_verse_offered_is_kept_in_its_place_and_the_rest_stay():
    for seed in range(40):
        drawn = A.arrange(g, LONG, seed)
        for i in range(3):
            options = A.options(g, drawn, "verse", i)
            assert any(c["id"] == drawn.verses[i] and c["allowed"] for c in options["choices"])
            for c in options["choices"]:
                if not c["allowed"]:
                    assert c["why"]
                    continue
                kept = A.arrange(g, LONG, seed, None, {"verses": {i: c["id"]}})
                assert kept.verses[i] == c["id"]
                # offered in place: nothing else moves
                assert [v for j, v in enumerate(kept.verses) if j != i] == [v for j, v in enumerate(drawn.verses) if j != i]
                assert kept.couplets == drawn.couplets and kept.bridges == drawn.bridges and kept.tag == drawn.tag


def test_choices_hold_as_chance_changes_and_the_rest_keep_every_rule():
    rules = A._song(g).checks
    by_id = {v.id: v for v in A._song(g).verses}
    rng = random.Random(11)
    for seed in range(150):
        drawn = A.arrange(g, FOUR, rng.randrange(10**6))
        i = rng.randrange(4)
        pick = rng.choice([c["id"] for c in A.options(g, drawn, "verse", i)["choices"] if c["allowed"]])
        for again in range(3):
            kept = A.arrange(g, FOUR, seed * 7 + again, None, {"verses": {i: pick}})
            assert kept.verses[i] == pick
            assert rules.why([by_id[v] for v in kept.verses]) is None


def test_refused_choices_say_why():
    assert "last refrain always sings the canon" in A.problem(g, LONG, {"couplets": {3: "true"}})
    assert "only the last" in A.problem(g, LONG, {"couplets": {0: "canon"}})
    assert "chosen refrain by refrain" in A.problem(g, LONG, {"refrain": {"question": "sang"}})
    assert "the first refrain asks who made, sang or wrote" in A.problem(g, LONG, {"refrains": {0: {"slots": {"question": "heard"}}}})
    assert A.problem(g, LONG, {"refrains": {0: {"slots": {"question": "wrote"}}}}) is None
    assert "only the last refrain asks who owns" in A.problem(g, LONG, {"refrains": {1: {"slots": {"question": "owns"}}}})
    assert "always sings the knows head" in A.problem(g, LONG, {"refrains": {0: {"head": "so"}}})
    assert "sings its while as if" in A.problem(g, LONG, {"refrains": {1: {"head": "so", "slots": {"while": "when"}}}})
    assert "chosen for two refrains" in A.problem(g, LONG, {"refrains": {1: {"head": "so"}, 2: {"head": "so"}}})
    assert "has no place to choose" in A.problem(g, LONG, {"refrains": {1: {"slots": {"place": "desert"}}}})
    assert "no verse 10" in A.problem(g, LONG, {"verses": {9: "wire"}})
    assert "not 'ha'" in A.problem(g, LONG, {"tag": "ha"})
    assert "at most one light verse" in A.problem(g, LONG, {"verses": {1: "hold", 2: "ring"}})
    assert "teaches the song's shape" in A.problem(g, LONG, {"verses": {0: "trench"}})
    assert "chosen for two places" in A.problem(g, LONG, {"verses": {0: "wire", 1: "wire"}})
    assert "sings the bridge once" in A.problem(g, SEED_FORM, {"bridge2": "coat"})
    assert A.problem(g, LONG, {"verses": {1: "wire"}}) is None


def test_couplets_trade_places_and_words_for_every_refrain_hold_everywhere():
    drawn = A.arrange(g, LONG, 3)
    third = drawn.couplets[2]
    kept = A.arrange(g, LONG, 3, None, {"couplets": {0: third}, "refrain": {"while": "if"},
                                        "bridge": {"place": "desert"}, "bridge2": "owed", "tag": "loo"})
    assert kept.couplets[0] == third and kept.couplets[2] == drawn.couplets[0]  # traded, not drawn again
    assert kept.couplets[-1] == "canon" and kept.couplets[1] == drawn.couplets[1]
    assert all("if you sing it" in s.lines[1] for s in kept.sections if s.block == "refrain" and "while" in s.slots)
    assert kept.questions == drawn.questions and kept.heads == drawn.heads
    assert "chosen refrain by refrain" in A.problem(g, LONG, {"refrain": {"then": "who knows"}})  # each ends its own way
    assert kept.bridges == ("canon", "owed") and "des-ert" in kept.sections[[s.block for s in kept.sections].index("bridge")].lines[0]
    assert kept.tag == "loo" and all(set(s.lines[0].rstrip(".").split()) == {"loo"} for s in kept.sections if s.block == "tag")
    # a verse's own swapped words, as written or as they read
    mind = A.arrange(g, SEED_FORM, 7, None, {"verses": {0: {"id": "mind", "slots": {"who": "nun"}}}})
    assert mind.sections[0].slots["who"]["noun"] == "nun" and "nun" in mind.sections[0].lines[0]
    assert "can be" in A.problem(g, SEED_FORM, {"verses": {0: {"id": "mind", "slots": {"who": "pope"}}}})


def test_options_offer_another_place_for_a_verse_refused_here():
    for seed in range(60):
        drawn = A.arrange(g, FOUR, seed)
        for c in A.options(g, drawn, "verse", 1)["choices"]:
            for j in c.get("elsewhere", []):
                assert A.problem(g, FOUR, {"verses": {j: c["id"]}}) is None
            if c.get("reorder"):
                order = c["reorder"]
                assert sorted(order) == sorted([*(v for k, v in enumerate(drawn.verses) if k != 1), c["id"]])
                assert A.problem(g, FOUR, {"verses": dict(enumerate(order))}) is None


@pytest.mark.parametrize("block,index", [("refrain", 0), ("refrain", 3), ("bridge", 0), ("bridge", 1), ("tag", 0)])
def test_options_for_the_fixed_blocks(block, index):
    options = A.options(g, A.arrange(g, LONG, 5), block, index)
    if block == "refrain" and index == 3:
        assert not any(c["allowed"] for c in options["choices"] if c["id"] != "canon")
        assert any(f["what"] == "couplet" for f in options["fixed"])
    if block == "refrain":  # the first and the last: the song's own head; the last asks who owns it, the first
        # who made, sang or wrote it, as a person chooses
        assert any(f["what"] == "head" for f in options["fixed"])
        assert [h["allowed"] for h in options["heads"]] == [True] + [False] * (len(options["heads"]) - 1)
        if index == 3:
            assert any(f["what"] == "question" for f in options["fixed"])
            assert {w["slot"] for w in options["words"]} == {"while", "then"}
        else:
            assert not any(f["what"] == "question" for f in options["fixed"])
            question = next(w for w in options["words"] if w["slot"] == "question")
            assert question["options"] == ["made", "sang", "wrote"]
    if block == "bridge" and index == 0:
        assert options["fixed"] and {w["slot"] for w in options["words"]} == {"place", "ember", "where"}
    if block == "bridge" and index == 1:
        assert {c["id"] for c in options["choices"]} == {"coat", "owed", "borrow", "slow"}
    if block == "tag":
        assert [c["id"] for c in options["choices"]] == ["la", "loo", "oo"]


def test_the_first_refrain_asks_who_made_sang_or_wrote_it_and_not_what_a_head_asks_again():
    """The first refrain draws its question (the rules' question_first), preferring one no head the song
    sings asks as written, so no question is heard twice where it can help it; the last asks who owns it.
    Words held from before, the first asking who made it while the swear head asks it too (Set B), still
    hold."""
    firsts, twice = Counter(), 0
    for seed in range(150):
        drawn = A.arrange(g, LONG, seed)
        firsts[drawn.questions[0]] += 1
        assert drawn.questions[-1] == "owns"
        heads_ask = {HEADS[h].get("fixed", {}).get("question") for h in drawn.heads[1:-1] if h}
        twice += drawn.questions[0] in heads_ask
    assert set(firsts) == {"made", "sang", "wrote"} and twice == 0
    b = next(s for s in json.loads(SETS.read_text())["sets"] if s["id"] == "b")
    assert [r["head"] for r in b["words"]["refrain"]["rounds"]][2] == "swear"  # asks who made, as the first does
    assert A.held_problem(g, R.singers_form(g, b["form"]), b["words"]) is None


def test_each_refrain_has_words_of_its_own():
    """A refrain between the first and the last can sing another head, ask its own question and choose its
    own words; the rest stay as drawn, and a head or question another refrain had trades or is asked afresh."""
    heads_seen, words_seen = set(), set()
    for seed in range(200):
        drawn = A.arrange(g, LONG, seed)
        heads_seen.add(drawn.heads)
        words_seen.update((s.slots["while"], s.slots["then"]) for s in drawn.sections
                          if s.block == "refrain" and {"while", "then"} <= set(s.slots))
        refrains = [s for s in drawn.sections if s.block == "refrain"]
        assert len({(s.slots.get("while"), s.slots.get("then")) for s in refrains}) > 1 or seed % 7  # they vary
        options = A.options(g, drawn, "refrain", 1)
        assert {h["id"] for h in options["heads"]} == set(HEADS)
        # every head may be chosen here but one asking, as written, what a head another refrain sings asks
        asked = {HEADS[o].get("fixed", {}).get("question") for i, o in enumerate(drawn.heads) if i != 1 and o} - {None}
        twins = {h for h in HEADS if HEADS[h].get("fixed", {}).get("question") in asked and h not in drawn.heads}
        assert {h["id"] for h in options["heads"] if not h["allowed"]} == twins, (drawn.heads, twins)
        question = next((w for w in options["words"] if w["slot"] == "question"), None)
        if question:  # never a word another refrain's head asks as written, nor the first refrain's
            given = {HEADS[h].get("fixed", {}).get("question") for i, h in enumerate(drawn.heads) if i != 1 and h}
            given.add(drawn.questions[0])
            assert question["options"] == [w for w in ("made", "sang", "heard", "kept", "wrote") if w not in given]
        # another head in refrain 2: its fixed words as written, the rest as drawn
        kept = A.arrange(g, LONG, seed, None, {"refrains": {1: {"head": "so"}}})
        so = [s for s in kept.sections if s.block == "refrain"][1]
        assert kept.heads[1] == "so" and so.lines[0] == f"Who *wrote* {so.slots['this']} song? No-bo-dy, so" and so.slots["while"] == "if"
        assert kept.couplets == drawn.couplets and "so" not in [h for i, h in enumerate(kept.heads) if i != 1]
        assert len(set(kept.questions[1:-1])) == len(kept.questions[1:-1])  # a clashing question is asked afresh
        # one refrain's own words, the others' as drawn
        mine = A.arrange(g, LONG, seed, None, {"refrains": {0: {"slots": {"while": "when", "then": "it grows"}}}})
        mine_refrains = [s for s in mine.sections if s.block == "refrain"]
        assert mine_refrains[0].slots["while"] == "when" and mine_refrains[0].slots["then"] == "it grows"
        assert [(s.id, s.head, s.slots["question"], s.slots.get("while")) for s in mine_refrains[1:]] == \
            [(s.id, s.head, s.slots["question"], s.slots.get("while")) for s in refrains[1:]]
        stayed = [a == b for a, b in zip(mine_refrains[1:], refrains[1:])]
        assert sum(stayed) >= len(stayed) - 1  # only a refrain that ended the same way ends another way now
    assert len(heads_seen) > 2 and len(words_seen) == 9  # every way of while and then


def test_a_person_can_ask_a_question_in_a_refrain_between():
    free = lambda h: "question" not in HEADS[h or "knows"].get("fixed", {})  # noqa: E731
    seed = next(s for s in range(5000) if all(free(h) for h in A.arrange(g, LONG, s).heads))
    drawn = A.arrange(g, LONG, seed)
    at, other = 1, drawn.questions[2]
    kept = A.arrange(g, LONG, seed, None, {"refrains": {at: {"slots": {"question": other}}}})
    assert kept.questions[at] == other and kept.questions[2] != other  # the other refrain asks something else
    so = next(s for s in range(5000) if A.arrange(g, LONG, s).heads[1:3] == (None, "so"))
    with pytest.raises(A.ArrangeError, match="asks who wrote already"):  # the so head's question is its own
        A.arrange(g, LONG, so, None, {"refrains": {1: {"slots": {"question": "wrote"}}}})


def test_a_question_another_refrains_head_asks_as_written_cant_be_chosen():
    """The Fable review's case: with the so head in refrain 3, choosing "wrote" for refrain 2 is refused, not
    sung twice."""
    seed = next(s for s in range(5000) if A.arrange(g, LONG, s).heads == (None, None, "so", None))
    with pytest.raises(A.ArrangeError, match="refrain 3 asks who wrote already"):
        A.arrange(g, LONG, seed, None, {"refrains": {1: {"slots": {"question": "wrote"}}}})
    assert "wrote" not in next(w for w in A.options(g, A.arrange(g, LONG, seed), "refrain", 1)["words"]
                               if w["slot"] == "question")["options"]


def test_each_refrain_ends_its_own_way():
    """Then is distinct: every song of three refrains sings it goes, who knows and it grows, and a song with the
    so head never sings "and then who knows." as a statement beside its question."""
    for seed in range(300):
        for form in (SEED_FORM, LONG):
            lyrics = A.arrange(g, form, seed)
            refrains = [s for s in lyrics.sections if s.block == "refrain"]
            thens = [s.slots["then"] for s in refrains if "then" in s.slots]  # the heads that end on then
            assert len(set(thens)) == min(len(thens), 3)
            if "so" in lyrics.heads:
                assert thens.count("who knows") == 1 and refrains[lyrics.heads.index("so")].slots["then"] == "who knows"


def test_couplets_chosen_for_two_refrains_at_once_trade_without_singing_one_twice():
    """Found by fuzzing: choosing refrain 2's couplet and refrain 3's at once, where refrain 3 was singing the
    one chosen for refrain 2, once left that couplet in two refrains."""
    five = ("intro", "verse", "refrain", "verse", "refrain", "verse", "refrain", "bridge", "refrain", "refrain", "tag")
    for seed in range(60):
        drawn = A.arrange(g, five, seed)
        a, b = drawn.couplets[1], drawn.couplets[2]
        for pins in ({1: {"id": b}, 2: {"id": a}}, {1: {"id": b}, 2: {"id": drawn.couplets[0]}},
                     {2: {"id": drawn.couplets[3]}, 1: {"id": drawn.couplets[2]}}):
            kept = A.arrange(g, five, seed, None, {"refrains": pins})
            assert len(set(kept.couplets)) == len(kept.couplets) and kept.couplets[-1] == "canon"
            assert all(kept.couplets[i] == p["id"] for i, p in pins.items())
            assert A.held_problem(g, five, A.hold(g, kept)) is None


def test_two_heads_that_ask_the_same_question_as_written_are_never_sung_in_one_song():
    """swear and grew both ask who made it, as written (grew, 2026-09-27): a song sings at most one of them,
    so no question is heard twice; choosing the other for another refrain is refused, and the options say
    which head already asks it."""
    twins = {}
    for hid, h in HEADS.items():
        q = h.get("fixed", {}).get("question")
        if q:
            twins.setdefault(q, []).append(hid)
    pair = next(ids for ids in twins.values() if len(ids) > 1)
    assert set(pair) == {"swear", "grew"}
    both = 0
    for seed in range(200):
        drawn = A.arrange(g, LONG, seed)
        assert not set(pair) <= set(drawn.heads), (seed, drawn.heads)
        i = next((k for k, h in enumerate(drawn.heads) if h in pair), None)
        if i is not None:
            both += 1
            other = next(h for h in pair if h != drawn.heads[i])
            entry = next(h for h in A.options(g, drawn, "refrain", 3 - i)["heads"] if h["id"] == other)
            assert not entry["allowed"] and drawn.heads[i] in entry["why"], entry
    assert both > 20
    assert "both ask who made" in A.problem(g, LONG, {"refrains": {1: {"head": "swear"}, 2: {"head": "grew"}}})
    assert A.problem(g, LONG, {"refrains": {1: {"head": "grew"}}}) is None
    assert A.problem(g, LONG, {"refrains": {1: {"head": "swear"}}}) is None
