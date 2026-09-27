"""The words a rendition draws from its song's bank keep every rule the bank
states, whatever the seed, the form or the leanings, and come out the same
for the same inputs. The rules are checked here from the bank as data, not
through arrange's own checks."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from songbird import arrange as A, bank as B, genome as G

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"
g = G.load(H)
BANK = g.source["bank"]
RULES = BANK["rules"]
VERSES = {v["id"]: v for v in BANK["verses"]}
COUPLETS = {c["id"]: c for c in BANK["refrain"]["couplets"]}
STANZAS = {b["id"]: b for b in BANK["bridges"]}
SEED_FORM = tuple(g.seed_params["form"])
MAIN = BANK["refrain"].get("id", "refrain")
HEADS = {MAIN: BANK["refrain"]} | {h["id"]: h for h in BANK["refrain"].get("heads", [])}


def shape(verses=2, refrains=3, bridges=1, tag=True, again="bridge2"):
    """A form in the template's shape: each verse followed by a refrain and a
    turn while the refrains last, then the bridge (a second time as `again`),
    the rest of the refrains, and the tag."""
    early = min(verses, max(refrains - 1, 0))
    form = ["intro"]
    for i in range(verses):
        form += ["verse"] + (["refrain", "turn"] if i < early else [])
    form += ["bridge"] * min(bridges, 1) + [again] * max(bridges - 1, 0) + ["refrain"] * (refrains - early)
    return tuple(form + (["tag"] if tag else []))


def options(slots, name):
    spec = slots[name]
    return [{c: col[i] for c, col in spec.items()} if isinstance(spec, dict) else spec[i]
            for i in range(B.width(slots, name))]


def sung(entry, chosen):
    """The lines an entry sings with the slot words a record says were chosen, marks aside."""
    slots = entry.get("slots", {})
    names = B.slot_names(entry["lines"])
    assert all(name in chosen for name in names)
    return B.fill(entry["lines"], slots, {name: options(slots, name).index(chosen[name]) for name in names})


def plain(lines):
    return [B.unmarked(line) for line in lines]


def check(form, lyrics):
    """Every rule of the bank, and every line on its phrase."""
    assert lyrics.form == form
    named = [n for n in form if g.section(n).lyrics]
    assert [s.section for s in lyrics.sections] == named
    assert [s.block for s in lyrics.sections] == [g.section(n).lyrics for n in named]
    for s in lyrics.sections:
        for line, pid in zip(s.lines, g.section(s.section).phrases, strict=True):
            assert len(G.syllables(line)) == len(g.phrases[pid].sung), (s.section, line)
            B.check_marks(line, s.section)

    vr = RULES["verses"]
    verses = [s for s in lyrics.sections if s.block == "verse"]
    entries = [VERSES[s.id] for s in verses]
    for s, v in zip(verses, entries):
        assert plain(s.lines) == sung(v, s.slots) and set(s.slots) == set(B.slot_names(v["lines"]))
    ids = [v["id"] for v in entries]
    assert vr["count"][0] <= len(ids) <= vr["count"][1] and len(set(ids)) == len(ids)
    assert all(entries[0].get(key, False if key == "enjambed" else None) == want for key, want in vr["first"].items())
    assert sum(v["scheme"] != "AABB" or v.get("enjambed", False) for v in entries) <= vr["max_variants"]
    assert sum(v["rarity"] == "rare" for v in entries) <= vr["max_rare"]
    for mood, most in vr["max_mood"].items():
        assert sum(v["mood"] == mood for v in entries) <= most
    eras = [v["era"] for v in entries if v["era"] is not None]
    assert eras == sorted(eras)
    for a, b in zip(entries, entries[1:]):
        assert not (a["mood"] == b["mood"] and a["mood"] in vr["never_adjacent"])
    for i, v in enumerate(entries):
        for partner in v.get("pairs_with", []):
            if partner in ids:
                assert abs(ids.index(partner) - i) == 1, ids

    rounds = [s for s in lyrics.sections if s.block == "refrain"]
    rr, n = RULES["refrain"], len(rounds)
    shared = BANK["refrain"]["slots"]
    heads = [s.head or MAIN for s in rounds]
    # the first and last refrains sing the heads the rules give them; another head is sung once a song
    assert heads[:1] in ([], [rr.get("head_first", MAIN)]) and (n < 2 or heads[-1] == rr.get("head_last", MAIN))
    others = [h for h in heads if h != MAIN]
    assert len(set(others)) == len(others)
    # a head that fixes its question asks it; else the first asks one of question_first (who made it, if
    # none), the last who owns it, and those between each ask a different one of the rest (with several
    # firsts, any word but owns; with one, any but it and owns)
    asked = shared["question"]
    firsts = rr.get("question_first") or asked[:1]
    middle = asked[:-1] if len(firsts) > 1 else asked[1:-1]
    questions = [s.slots["question"] for s in rounds]
    for i, (q, h) in enumerate(zip(questions, heads)):
        fixed = HEADS[h].get("fixed", {})
        if "question" in fixed:
            assert q == fixed["question"], (questions, heads)
        elif i == 0:  # a lone refrain asks as a first one does
            assert q in firsts, (questions, heads)
        elif i == n - 1:
            assert q == asked[-1], (questions, heads)
        else:
            assert q in middle, (questions, heads)
    assert len(set(questions)) == len(questions), (questions, heads)
    # a slot the rules hold to one word in the first and last refrains (H: this song), unless the head fixes it
    for rule, i in (("first", 0), ("last", n - 1)):
        for slot, word in rr.get(rule, {}).items():
            if n and slot in rounds[i].slots and slot not in HEADS[heads[i]].get("fixed", {}):
                assert rounds[i].slots[slot] == word, (rule, slot, rounds[i].slots)
    for name in rr.get("once_per_song", ()):
        assert len({s.slots[name] for s in rounds}) <= 1
    couplets = [s.id for s in rounds]
    assert couplets[-1:] in ([], [rr["couplet_last"]]) and len(set(couplets)) == len(couplets)
    for s, h in zip(rounds, heads):
        head = {"lines": HEADS[h]["lines"], "slots": shared}
        assert all(s.slots[k] == v for k, v in HEADS[h].get("fixed", {}).items())
        assert plain(s.lines) == plain(sung(head, s.slots) + sung(COUPLETS[s.id], s.slots))

    bridges = [s for s in lyrics.sections if s.block == "bridge"]
    assert len(bridges) <= 2 and [b.id for b in bridges[:1]] in ([], [RULES["bridge"]["always"]])
    assert all(b.id in RULES["bridge"]["extra"] for b in bridges[1:])
    for s in bridges:
        assert plain(s.lines) == sung(STANZAS[s.id], s.slots)

    tags = [s for s in lyrics.sections if s.block == "tag"]
    assert len({s.id for s in tags}) <= 1
    for s in tags:
        assert s.id in BANK["tag"]["syllables"]
        assert s.lines == tuple(" ".join([s.id] * len(g.phrases[p].sung)) + "." for p in g.section(s.section).phrases)


def test_the_seed_form_has_the_templates_shape():
    assert shape() == SEED_FORM


def test_forms_says_how_many_of_each_section_the_bank_can_fill():
    assert A.forms(g) == {"verse": (2, 3, 4), "refrain": (0, 1, 2, 3, 4, 5, 6, 7), "bridge": (0, 1, 2)}  # a refrain a couplet
    assert A.problem(g, SEED_FORM) is None and A.problem(g, shape(4, 6, 2)) is None
    assert A.problem(g, shape(5)).startswith("this form has 5 verse sections;")
    assert "no section 'chorus'" in A.problem(g, ("verse", "verse", "chorus"))
    assert "no lyric bank" in A.problem(G.load(ROOT / "songs" / "b-coal-from-the-fire.json"), ("refrain",))


@pytest.mark.parametrize("verses", [2, 3, 4])
def test_the_rules_hold_for_thousands_of_seeds(verses):
    form = shape(verses)
    for seed in range(1000):
        check(form, A.arrange(g, form, seed))


def test_the_rules_hold_in_every_supported_form():
    forms = [shape(v, r, b, t, again) for v in (2, 3, 4) for r in range(7) for b in (0, 1, 2) for t in (True, False)
             for again in (("bridge2", "bridge") if b == 2 else ("bridge2",))]
    forms += [("refrain", "verse", "verse", "bridge", "refrain"),  # the shape needn't be the template's
              ("verse", "bridge", "verse", "refrain", "bridge", "tag", "refrain", "tag"),
              ("intro", "verse", "verse", "verse", "verse", "refrain", "refrain", "refrain", "bridge", "bridge2")]
    for i, form in enumerate(forms):
        for seed in range(20):
            check(form, A.arrange(g, form, 1000 * i + seed))


LEANINGS = [
    A.Leanings(mood_weights={"light": 20, "dark": 20}),
    A.Leanings(mood_weights={"plain": 0, "tender": 20}, era_bias=-1, rarity_appetite=-1),
    A.Leanings(era_bias=1, rarity_appetite=1),
    A.Leanings(era_bias=3, rarity_appetite=-7),  # past the ends: held at them
    A.Leanings(vocabulary={"phone", "machine", "wire", "banjo", "monday", "sheep", "nun", "cold", "blue"}),
]


@pytest.mark.parametrize("leanings", LEANINGS, ids=range(len(LEANINGS)))
def test_leanings_never_break_a_rule(leanings):
    for form in (shape(2), shape(4, 6, 2)):
        for seed in range(250):
            check(form, A.arrange(g, form, seed, leanings))


def test_when_drawing_gives_up_the_search_keeps_the_rules(monkeypatch):
    monkeypatch.setattr(A, "ATTEMPTS", 0)
    for leanings in (None, LEANINGS[0], LEANINGS[4]):
        for seed in range(60):
            check(shape(3), A.arrange(g, shape(3), seed, leanings))


def test_the_same_inputs_give_the_same_words():
    leanings = A.Leanings({"tender": 3}, -0.5, 0.5, {"phone", "banjo"})
    for seed in range(40):
        assert A.arrange(g, shape(3, 4, 2), seed, leanings) == A.arrange(g, shape(3, 4, 2), seed, leanings)
    assert A.arrange(g, SEED_FORM, 3) == A.arrange(g, SEED_FORM, 3, None) == A.arrange(g, SEED_FORM, 3, A.Leanings())
    # and another seed, other words: a hundred seeds, a hundred songs
    assert len({tuple(s.lines for s in A.arrange(g, SEED_FORM, seed).sections) for seed in range(100)}) == 100


def test_the_words_dont_depend_on_the_hash_seed():
    script = (
        "import json; from songbird import arrange as A, genome as G\n"
        f"g = G.load({str(H)!r})\n"
        "lean = A.Leanings(vocabulary=['phone', 'machine', 'wire', 'banjo', 'monday', 'sheep', 'cold', 'girl', 'night'])\n"
        f"print(json.dumps([A.arrange(g, {shape(4, 5, 2)!r}, s, lean).to_dict() for s in range(30)]))\n"
    )
    runs = [subprocess.run([sys.executable, "-c", script], env={**os.environ, "PYTHONHASHSEED": h}, cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout for h in ("1", "2", "3")]
    assert runs[0] == runs[1] == runs[2] and json.loads(runs[0])


def test_the_question_turns_as_the_fixed_refrain_does():
    for n in range(1, 9):
        assert [A._turned(i, n, 6) for i in range(n)] == [int(G.turn("{0|1|2|3|4|5}", i, n)) for i in range(n)]


def test_the_seeds_focus_marks_come_with_its_words():
    for seed in range(60):
        lyrics = A.arrange(g, SEED_FORM, seed)
        for i, s in enumerate(r for r in lyrics.sections if r.block == "refrain"):
            if s.head is None:  # Who *made* this song? ..., the question marked as the seed marks it
                assert s.lines[0] == f"Who *{s.slots['question']}* {s.slots['this']} song? No-bo-dy knows."
                assert s.slots["this"] == "this" or 0 < i < lyrics.form.count("refrain") - 1  # this song first and last
                assert s.lines[1].startswith("It's *yours* ")
            else:  # another head marks its own: the question, and one word of its second line
                assert s.lines[0].startswith("Who *") and s.lines[1].count("*") == 2
            if s.id == "canon":
                assert s.lines[2:] == g.refrain[2:]
        bridge = next(s for s in lyrics.sections if s.block == "bridge")
        assert [line.split()[0] for line in bridge.lines] == ["*Car-ry*", "*hand*", "it's", "it"]
        assert bridge.lines[2].endswith("*own*,") and "*dies*" in bridge.lines[3]
        for s in lyrics.sections:
            if s.block == "verse" and s.id == "wire":
                assert s.lines == g.seed_verses[0]
            if s.block == "verse" and s.id not in ("wire", "screen", "mind", "ink", "mouth"):
                assert not any("*" in line for line in s.lines)  # the bank marks none of its own yet
    mind = next(v for v in (A.arrange(g, shape(3), s) for s in range(3000)) if "mind" in v.verses)
    verse = next(s for s in mind.sections if s.id == "mind")
    assert verse.lines[0].split()[3] == "*kept*" and "*slept*" in verse.lines[2]


def test_a_rare_verse_comes_less_often_than_a_common_one():
    counts = {vid: 0 for vid in VERSES}
    for seed in range(1500):
        for vid in A.arrange(g, shape(3), seed).verses:
            counts[vid] += 1
    common = [n for vid, n in counts.items() if VERSES[vid]["rarity"] == "common"]
    rare = [n for vid, n in counts.items() if VERSES[vid]["rarity"] == "rare"]
    assert max(rare) < sorted(common)[len(common) // 2] and min(common) > 0 and min(rare) > 0


def test_a_pair_answers_itself_about_half_the_time():
    def answered(call, answer, leanings=None):
        songs = [lyrics.verses for lyrics in (A.arrange(g, shape(3), seed, leanings) for seed in range(1500))]
        called = [verses for verses in songs if call in verses]
        return sum(answer in verses for verses in called) / len(called)

    assert answered("wax", "sample") > 0.35 and answered("mind", "names") > 0.35
    assert answered("wire", "learned") > 0.25  # learned is rare, but not as an answer
    assert answered("mind", "names", A.Leanings(mood_weights={"tender": 0.05})) < 0.1  # unless leaned away from


def share(leanings, measure, seeds=600, form=shape(3)):
    return sum(measure(A.arrange(g, form, seed, leanings)) for seed in range(seeds)) / seeds


def test_mood_weights_tilt_the_verses():
    dark = lambda lyrics: sum(VERSES[v]["mood"] == "dark" for v in lyrics.verses)  # noqa: E731
    tender = lambda lyrics: sum(VERSES[v]["mood"] == "tender" for v in lyrics.verses)  # noqa: E731
    assert share(A.Leanings(mood_weights={"dark": 6}), dark) > 2 * share(None, dark)
    assert share(A.Leanings(mood_weights={"tender": 0}), tender) < 0.2 * share(None, tender)


def test_the_era_bias_leans_older_or_newer():
    def mean_era(lyrics):
        eras = [VERSES[v]["era"] for v in lyrics.verses if VERSES[v]["era"] is not None]
        return sum(eras) / len(eras) if eras else 1950

    assert share(A.Leanings(era_bias=1), mean_era) > share(None, mean_era) + 15
    assert share(A.Leanings(era_bias=-1), mean_era) < share(None, mean_era) - 15


def test_the_rarity_appetite():
    rare = lambda lyrics: any(VERSES[v]["rarity"] == "rare" for v in lyrics.verses)  # noqa: E731
    high, neutral, low = (share(A.Leanings(rarity_appetite=a), rare) for a in (1, 0, -1))
    assert high > 1.6 * neutral and neutral > 2 * low  # (a rare verse answering its partner isn't rationed)


def test_a_persons_words_are_preferred():
    fiddle = lambda lyrics: "fiddle" in lyrics.verses  # noqa: E731
    banjo = A.Leanings(vocabulary={"banjo"})
    assert share(banjo, fiddle) > 1.5 * share(None, fiddle)
    played = [s.slots["instrument"] for seed in range(3000) for s in A.arrange(g, shape(3), seed, banjo).sections
              if s.id == "fiddle"]
    assert played.count("ban-jo") / len(played) > 0.35  # of four instruments
    # the little words everyone uses steer nothing: her, him, he, the ("she" sings in four verses of fifty, so it does)
    assert A.arrange(g, shape(4), 5, A.Leanings(vocabulary={"her", "him", "he", "the"})).sections == \
        A.arrange(g, shape(4), 5).sections


def test_only_the_bank_words_of_a_vocabulary_are_kept_and_they_replay_the_draw():
    lyrics = A.arrange(g, shape(3, 4, 2), 12, A.Leanings(vocabulary={"banjo", "zebra", "spreadsheet", "Phone,"}))
    assert lyrics.leanings.vocabulary == {"banjo", "phone"}
    again = A.Lyrics.from_dict(json.loads(json.dumps(lyrics.to_dict())))
    assert A.arrange(g, again.form, again.seed, again.leanings) == lyrics


def test_lyrics_round_trip_through_their_record():
    for lyrics in (A.arrange(g, shape(3, 4, 2), 5, A.Leanings({"dark": 2}, 0.3, -0.2, {"banjo"})),
                   A.arrange(g, SEED_FORM, 9), A.seed_lyrics(g, SEED_FORM)):
        record = json.loads(json.dumps(lyrics.to_dict()))
        assert A.Lyrics.from_dict(record) == lyrics and record["sections"][0]["lines"]


def test_the_seeds_own_words_are_named_for_their_bank_entries():
    lyrics = A.seed_lyrics(g, SEED_FORM)
    assert lyrics.seed is None and lyrics.form == SEED_FORM
    assert lyrics.verses == ("wire", "screen") and lyrics.couplets == ("canon", "canon", "canon")
    assert lyrics.questions == ("made", "sang", "owns") and lyrics.bridges == ("canon",) and lyrics.tag == "la"
    verse, refrain = lyrics.sections[:2]
    assert verse.lines == g.seed_verses[0] and refrain.lines == tuple(G.turn(line, 0, 3) for line in g.refrain)
    assert lyrics.sections[2].slots == {"many": "mil-lion"}
    assert refrain.slots == {"question": "made", "this": "this", "while": "while", "then": "it goes"}


@pytest.mark.parametrize("form, why", [
    (shape(5), "5 verse sections; the bank's rules sing 2, 3 or 4 verses"),
    (shape(1), "1 verse section;"),
    (shape(2, 8), "8 refrain sections; the bank's rules sing 0 to 7 refrains"),
    (shape(2, 3, 3), "3 bridge sections; the bank's rules sing 0, 1 or 2 bridge sections"),
    (("verse", "verse", "chorus", "refrain", "bridge"), "no section 'chorus'"),
])
def test_a_form_the_rules_cant_fill_is_refused_plainly(form, why):
    with pytest.raises(A.ArrangeError, match=why):
        A.arrange(g, form, 0)


def test_what_arrange_refuses():
    with pytest.raises(A.ArrangeError, match="no lyric bank"):
        A.arrange(G.load(ROOT / "songs" / "b-coal-from-the-fire.json"), ("refrain",), 0)
    with pytest.raises(ValueError, match="seed"):
        A.arrange(g, SEED_FORM, -1)
    data = json.loads(H.read_text())
    data["bank"]["rules"]["verses"]["max_tender"] = 1
    with pytest.raises(A.ArrangeError, match="max_tender"):
        A.arrange(G.from_dict(data), SEED_FORM, 0)
    data = json.loads(H.read_text())
    data["bank"]["rules"]["refrain"]["couplet_repeat"] = True
    with pytest.raises(A.ArrangeError, match="couplet_repeat"):
        A.arrange(G.from_dict(data), SEED_FORM, 0)
    data = json.loads(H.read_text())
    data["bank"]["rules"]["bridge"]["extra"] = ["coat", "cloak"]
    with pytest.raises(A.ArrangeError, match="cloak"):
        A.forms(G.from_dict(data))
    with pytest.raises(TypeError, match="one string"):
        A.arrange(g, "verse", 1)
    with pytest.raises(ValueError, match="moods"):
        A.Leanings(mood_weights={"sad": 2})
    with pytest.raises(ValueError, match="dark"):
        A.Leanings(mood_weights={"dark": -1})
    with pytest.raises(ValueError, match="era_bias"):
        A.Leanings(era_bias=float("nan"))
    with pytest.raises(TypeError):
        A.Leanings(vocabulary="banjo")
    with pytest.raises(TypeError):
        A.Leanings.from_dict({"vocabulary": "banjo"})
    assert A.Leanings(vocabulary=["Banjo,", "PHONE", "*num-bers*"]).vocabulary == {"banjo", "phone", "numbers"}
    assert A.Leanings(mood_weights=None, vocabulary=None) == A.Leanings()  # nothing to lean on is neutral
    # past its range a leaning is held at the end, and says so
    held = A.Leanings({"plain": 0, "dark": 99}, era_bias=3, rarity_appetite=-7)
    assert held.to_dict() == {"mood_weights": {"plain": 0.05, "dark": 20.0}, "era_bias": 1.0, "rarity_appetite": -1.0,
                              "vocabulary": []}


def test_the_arrange_command_prints_a_lyric_sheet(capsys):
    assert A.main([str(H), "--seed", "7"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Now It's by You\nwords drawn with seed 7; form: intro verse refrain")
    assert "[refrain: canon]\nWho owns this song? Nobody knows." in out and "*" not in out
    assert "\nrefrain  canon  (question owns, this this, while " in out
    assert A.main([str(H), "--seed", "7", "--form", "verse", "refrain", "bridge"]) == 1
    assert "1 verse section" in capsys.readouterr().err
    assert A.main([str(H), "--forms"]) == 0
    assert capsys.readouterr().out.startswith("verse: 2, 3 or 4\nrefrain: 0 to 7\nbridge: 0, 1 or 2\n")


# Singing them


def test_the_seed_arrangement_is_unchanged():
    """Without lyrics realize sings the seed's own words, as it always has, and
    those words given to it as a Lyrics sing exactly the same score."""
    from dataclasses import replace

    from songbird.realize import choose_params, realize

    score = realize(g, choose_params(g))
    refrain = [[G.turn(line, i, 3) for line in g.refrain] for i in range(3)]
    blocks = [g.seed_verses[0], refrain[0], g.seed_verses[1], refrain[1], g.fixed["bridge"], refrain[2], g.fixed["tag"]]
    assert [n.word for n in score.part("voice")] == [w for b in blocks for line in b for _, w, _ in G.sung_words(line)]
    for path in sorted((ROOT / "songs").glob("*.json")):
        song = G.load(path)
        params = choose_params(song)
        forms = [params.form, ("refrain",)] + ([tuple(params.form) + ("bridge2",)] if "bridge" in song.sections else [])
        for form in forms:
            q = replace(params, form=tuple(form), choir=2)
            assert realize(song, q, lyrics=A.seed_lyrics(song, q.form)) == realize(song, q), (path.stem, form)


def test_realize_sings_the_drawn_words_on_their_notes():
    from dataclasses import replace

    from songbird.realize import choose_params, realize

    form = shape(3, 4, 2)
    own = choose_params(g)
    params = replace(own, form=form, choir=2, style=replace(own.style, backing=""))  # no thirds behind the refrains
    seeded = realize(g, params)  # a second bridge section sings the seed's bridge again
    for seed in (4, 21, 30):
        lyrics = A.arrange(g, form, seed)
        score = realize(g, params, lyrics=lyrics)
        want = [(s.section, pid, syllable, word) for s in lyrics.sections
                for line, pid in zip(s.lines, g.section(s.section).phrases) for syllable, word, _ in G.sung_words(line)]
        assert [(n.section, n.phrase, n.syllable, n.word) for n in score.part("voice")] == want
        # the second bridge is the bridge again: its phrases, the choir singing with the lead
        assert {n.section for n in score.notes if n.part.startswith("choir")} == {"bridge", "bridge2", "tag"}
        # and the words change nothing else: the same parts, times and pitches as the seed's words
        assert [(n.part, n.start, n.dur, n.pitch) for n in score.notes] == \
            [(n.part, n.start, n.dur, n.pitch) for n in seeded.notes]
        # the focus marks reach the singer, as they do in the seed's words
        marked = {n.word for n in score.part("voice") if "*" in n.word}
        assert {"*yours*", "*own*,", "*you*."} <= marked


def test_realize_wont_sing_words_that_dont_fit():
    from dataclasses import replace

    from songbird.realize import choose_params, realize

    params = choose_params(g)
    lyrics = A.arrange(g, SEED_FORM, 1)
    with pytest.raises(ValueError, match="drawn for the form"):
        realize(g, replace(params, form=shape(3)), lyrics=lyrics)
    with pytest.raises(ValueError, match="not both"):
        realize(g, params, verses=g.seed_verses, lyrics=lyrics)
    record = lyrics.to_dict()
    record["sections"][0]["lines"][0] = "too few syl-la-bles"
    with pytest.raises(ValueError, match="syllables"):
        realize(g, params, lyrics=A.Lyrics.from_dict(record))


def test_the_render_command_says_plainly_when_it_cant_draw_words(tmp_path, capsys):
    from songbird import cli

    out = tmp_path / "h.flac"
    assert cli.main(["render", str(H), "--lyrics-seed", "3", "--form", "verse", "refrain", "bridge",
                     "--out", str(out)]) == 2
    assert "1 verse section" in capsys.readouterr().err and not out.exists()
