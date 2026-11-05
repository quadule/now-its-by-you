"""Words spelt alike and said two ways (songbird.heteronyms): the rules over lines like a song's, a person's
say in braces, a line written in the studio sung, stored and replayed with them, and the song's own lines
sung exactly as before."""

import json
import os
from pathlib import Path

import pytest

from songbird import composition as C, drift as D, edits as E, harvest as HV, heteronyms as H, pack
from songbird import phonetics as ph
from songbird.genome import load, sung_words, syllables
from songbird.realize import Params, choose_params, realize
from songbird.synth.voice import VoiceParams, schedule

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).parent / "golden"
SONG = ROOT / "songs/h-now-its-by-you.json"
G = load(SONG)
ADA = HV.fictional("ada")
DAY = D.drift(D.parse("2026-09-27"), ADA.hash)
PATH = "lyrics.verse:wire.0"  # an 11-syllable line every version of H sings

# (line, the heteronym in it, the sense the rules choose)
CASES = [
    ("The bass is a heartbeat that nobody wrote", "bass", "low"),
    ("The fish was a bass", "bass", "fish"),
    ("he caught a bass down by the lake", "bass", "fish"),
    ("turn up the bass and let it ring", "bass", "low"),
    ("the wind took it down to the farms in the vale,", "wind", "air"),
    ("gone with the wind", "wind", "air"),
    ("I wind the clock", "wind", "turn"),
    ("we wind it up", "wind", "turn"),
    ("the road winds down to the sea", "winds", "turns"),
    ("the winds of March", "winds", "air"),
    ("we live in your head", "live", "verb"),
    ("to live and die", "live", "verb"),
    ("a live wire humming", "live", "alive"),
    ("they played it live music all night", "live", "alive"),
    ("the night the show went live.", "live", "alive"),
    ("all of our lives", "lives", "plural"),
    ("the song lives on", "lives", "verb"),
    ("she lives by the sea", "lives", "verb"),
    ("lead me home", "lead", "guide"),
    ("heavy as lead", "lead", "metal"),
    ("a pencil of lead and a page", "lead", "metal"),
    ("I'll read you a story", "read", "now"),
    ("I read all your papers and dropped every name;", "read", "past"),
    ("I had read it before", "read", "past"),
    ("yesterday I read it", "read", "past"),
    ("don't read it", "read", "now"),
    ("a tear in my eye", "tear", "crying"),
    ("don't tear it apart", "tear", "rip"),
    ("wear and tear", "tear", "rip"),
    ("and why there were tears;", "tears", "crying"),
    ("she tears it apart", "tears", "rips"),
    ("take a bow", "bow", "bend"),
    ("bow down", "bow", "bend"),
    ("the fiddle and the bow", "bow", "ribbon"),
    ("a bow in her hair", "bow", "ribbon"),
    ("close your eyes", "close", "shut"),
    ("so close and so safe that it never was said.", "close", "near"),
    ("hold me close", "close", "near"),
    ("close to the fire", "close", "near"),
    ("the close of day", "close", "shut"),
    ("a wound that won't heal", "wound", "injury"),
    ("wound up tight", "wound", "turned"),
    ("you reap what you sow", "sow", "plant"),
    ("the sow and her piglets", "sow", "pig"),
    ("a white dove", "dove", "bird"),
    ("she dove into the sea", "dove", "dived"),
    ("wait a minute", "minute", "time"),
    ("a minute detail", "minute", "tiny"),
    ("the record plays on", "record", "noun"),
    ("I want to record it", "record", "verb"),
    ("what's the use", "use", "noun"),
    ("use me", "use", "verb"),
    ("I used to sing", "used", "habit"),
    ("I used it all", "used", "used"),
    ("a perfect day", "perfect", "perfect"),
    ("so content to stay", "content", "happy"),
    ("the content of the box", "content", "inside"),
    ("across the desert sand", "desert", "sand"),
    ("don't desert me", "desert", "leave"),
    ("the Polish girl", "polish", "poland"),
    ("Polish the silver", "polish", "shine"),
    ("the house on the hill", "house", "noun"),
    ("row on row", "row", "line"),
    ("a blazing row", "row", "fight"),
    ("what does it mean", "does", "does"),
]


@pytest.mark.parametrize("line,word,sense", CASES)
def test_the_rules_choose_from_the_words_around(line, word, sense):
    found = [c for c in H.choices(line) if c["word"] == word]
    assert found and found[0]["chosen"] == sense and found[0]["by"] == "rules", (line, H.choices(line))


def test_the_cause_the_dictionary_lists_the_fish_first_and_the_songs_own_lines_still_take_it():
    """What the singer did before, and still does for a line the song itself sings: the first reading."""
    assert ph.pronunciations("bass")[0] == ["B", "AE1", "S"]
    assert [s.nucleus for s in ph.fit("bass", 1)] == ["AE"]
    assert [s.nucleus for s in ph.fit("bass{low}", 1)] == ["EY"]
    assert [s.nucleus for s in ph.fit("wind", 1)] == ["AY"]  # the dictionary's first "wind" turns a clock


def test_every_sense_is_a_reading_the_singer_can_sing():
    for word, entry in H.TABLE["words"].items():
        names = [s["name"] for s in entry["senses"]]
        assert len(names) == len(set(names)), word
        for s in entry["senses"]:
            phones = s["phones"].split()
            assert all(p.rstrip("012") in ph.VOWELS | set(ph.CONSONANTS) for p in phones), (word, s)
            assert all(p[-1] in "012" for p in phones if p.rstrip("012") in ph.VOWELS), (word, s)
            assert H.problem(f"{word}{{{s['name']}}}", len(ph.fit(f"{word}{{{s['name']}}}", 9))) is None
        for rule in entry["rules"]:
            assert rule["sense"] in names, (word, rule)


def test_decide_gives_each_heteronym_its_sense_and_leaves_every_other_word():
    assert H.decide("The *bass*, the drum") == "The *bass{low}*, the drum"
    assert H.decide("The fish was a bass.") == "The fish was a bass{fish}."
    assert H.decide("the bass{fish} is a heart-beat") == "the bass{fish} is a heart-beat"  # a say is kept
    assert H.decide("no heteronym here, car-ry on") == "no heteronym here, car-ry on"
    assert H.decide("wind — the wind") == "wind{air} — the wind{air}"


def test_a_say_in_braces_is_a_sense_a_word_it_sounds_like_or_arpabet():
    assert ph.pronunciations("bass{fish}") == [["B", "AE1", "S"]]
    assert ph.pronunciations("bass{base}") == [["B", "EY1", "S"]]
    assert ph.pronunciations("bass{B.EY1.S}") == [["B", "EY1", "S"]]
    assert ph.pronunciations("*bass{low}*,") == [["B", "EY1", "S"]]
    assert [s.nucleus for s in ph.fit("min-ute{my-newt}", 2)] == ["AY", "UW"]
    assert ph.pronunciations("hello{HH.AH0.L.OW1}") == [["HH", "AH0", "L", "OW1"]]  # any word, not only heteronyms
    # a say is the last word: over the song's lexicon too
    assert ph.pronunciations("record{verb}", {"record": "R EH1 K ER0 D"}) == [["R", "IH0", "K", "AO1", "R", "D"]]
    assert H.normalized("bass{B EY1 S} and more") == "bass{B.EY1.S} and more"


def test_a_say_the_singer_cant_read_is_refused_in_plain_words():
    assert H.problem("bass{fish}", 1) is None
    assert "can't read {zzz}: try bass{low}, bass{fish}, or a word" in H.problem("bass{zzz}", 1)
    assert "can't read {B.XX1.S}" in H.problem("bass{B.XX1.S}", 1)
    assert "right after its word" in H.problem("{fish}", 1)
    assert "one say" in H.problem("bass{fish}{low}", 1)
    assert "one say" in H.problem("bass{fish", 1)
    assert H.problem("min-ute{min}", 2) == "{min} says 1 syllable; 'min-ute' is sung on 2"


def test_says_are_never_syllables_or_shown():
    assert syllables("The bass{fish} is a heart-beat") == ["The", "bass", "is", "a", "heart", "beat"]
    assert syllables("min-ute{my-newt} to go") == ["min", "ute", "to", "go"]
    assert sung_words("the bass{fish},") == [("the", "the", 1), ("bass,", "bass{fish},", 1)]
    assert ph.shown("bass{fish},") == "bass," and ph.shown("bass,") == "bass,"


LINE = "The bass is a heart-beat that no-bo-dy wrote"
FISH = "The fish that he caught was a bass by the sea"


def _bass(params, lyrics=None):
    """The phones the singer sings "bass" with in the wire verse's first line."""
    score = realize(G, params, lyrics=lyrics)
    notes = [n for n in score.part("voice") if n.phrase == "v1"][:11]
    segs = schedule(notes, VoiceParams(), G.lexicon)
    k = next(i for i, n in enumerate(notes) if ph.shown(n.word).startswith("bass"))
    start, end = notes[k].start, notes[k + 1].start
    return notes, [s.phone for s in segs if s.role == "vowel" and start - 0.2 <= s.t0 < end]


@pytest.mark.parametrize("text,vowel,stored", [
    (LINE, "EY", LINE),  # the low note, by the rules
    (FISH, "AE", FISH),  # the fish, by the rules
    (LINE.replace("bass", "bass{fish}"), "AE", LINE.replace("bass", "bass{fish}")),  # a person's say
    (LINE.replace("bass", "bass{B AE1 S}"), "AE", LINE.replace("bass", "bass{B.AE1.S}")),  # ARPAbet, spaces as dots
])
def test_a_line_written_in_the_studio_is_sung_stored_and_replayed_with_its_say(text, vowel, stored):
    changed = E.resolve(G, None, ADA, DAY, {PATH: text})
    assert not changed.problems, changed.problems
    assert changed.params.composition["lines"] == {"verse:wire": {"0": stored}}  # the line as written, says and all
    notes, vowels = _bass(changed.params, changed.lyrics)
    assert vowels[0] == vowel
    assert " ".join(n.syllable for n in notes) == stored.replace("-", " ").replace("{fish}", "").replace(
        "{B.AE1.S}", "")  # shown without its say
    words = pack.words_as_sung(realize(G, changed.params, lyrics=changed.lyrics).to_dict())
    assert "{" not in words and ("The bass is" in words or "a bass by" in words)
    # replayed from its record, and inherited by a child, exactly
    record = json.loads(json.dumps(changed.params.to_dict()))
    assert Params.from_dict(record) == changed.params
    replay = E.resolve(G, None, ADA, DAY, E.from_record({"chosen_by_you": changed.marks}))
    assert replay.params == changed.params
    assert _bass(replay.params, replay.lyrics)[1] == vowels
    child = choose_params(G, Params.from_dict(record), HV.fictional("basil"), D.drift(D.parse("2029-03-14"), ADA.hash))
    assert child.composition["lines"] == {"verse:wire": {"0": stored}}


def test_the_studio_view_says_which_way_each_line_sings_its_heteronyms():
    base = E.resolve(G, None, ADA, DAY, {})
    view = C.view(G, base.params, base.lyrics)
    assert view["say"] is H.TABLE and "bass" in view["say"]["words"]
    changed = E.resolve(G, None, ADA, DAY, {PATH: FISH})
    view = C.view(G, changed.params, changed.lyrics)
    line = next(p for s in view["sections"] for p in s["phrases"] if p["lyric_path"] == PATH)
    assert line["said"] == [{"index": 7, "word": "bass", "chosen": "fish", "by": "rules"}]


def _own_lines():
    for path in sorted((ROOT / "songs").glob("*.json")):
        song = load(path)
        yield path.stem, song, set(_lines(song))


def _lines(song):
    """Every line a song can sing: its bank's in every way, its seed verses, its fixed blocks each time round."""
    from songbird.bank import expansions, head_slots
    from songbird.genome import turns

    bank = song.source.get("bank") or {}
    out = []
    for v in bank.get("verses", []):
        out += [line for sung in expansions(v["lines"], v.get("slots", {})) for line in sung]
    r = bank.get("refrain")
    if r:
        out += [line for sung in expansions(r["lines"], r.get("slots", {})) for line in sung]
        for h in r.get("heads", []):
            out += [line for sung in expansions(h["lines"], head_slots(h, r.get("slots", {}))) for line in sung]
        for c in r.get("couplets", []):
            out += [line for sung in expansions(c["lines"], c.get("slots", {})) for line in sung]
    for b in bank.get("bridges", []):
        out += [line for sung in expansions(b["lines"], b.get("slots", {})) for line in sung]
    out += [line for v in song.seed_verses for line in v]
    out += [sung for block in song.fixed.values() for line in block for sung in turns(line)]
    return out


def test_the_songs_own_lines_say_their_words_as_the_rules_would():
    """Every line a song can sing says its words said two ways as the rules would, its own says (wind{air})
    where the dictionary's first reading was wrong (docs/STUDIO.md, "Words said two ways")."""
    differ, says = set(), set()
    for stem, song, lines in _own_lines():
        for line in lines:
            for c in H.as_sung(line, song.lexicon, authored=False):
                assert c["by"] == "song"
                rules = next(x for x in H.choices(line) if x["index"] == c["index"])["chosen"]
                if "{" in line:
                    says.add((stem, c["word"], c["chosen"]))
                if rules != c["chosen"]:
                    differ.add((stem, c["word"], c["chosen"], rules))
    assert not differ, sorted(differ)
    assert says == {
        ("a-nobody-knows", "perfect", "perfect"),  # "Each copy was perfect": was per-FECT (H has its own)
        ("d-in-by-the-ear", "live", "verb"),  # "I live in your head": was LYVE
        ("e-nothing-of-you", "live", "verb"),  # "colours that live on your screen"
        ("h-now-its-by-you", "tears", "crying"),  # "why there were tears": was TAIRS
        ("h-now-its-by-you", "used", "habit"),  # "used to sing it", "used to hum it": was YOOZD
        ("h-now-its-by-you", "wind", "air"),  # "the wind took it down": was WYND
        ("k-still-you-grew", "sowed", "planted"),  # "No one sowed her": was as the pig, SOWD
        ("k-still-you-grew", "wind", "air"),  # "half was wind and half was shoe"
        ("l-sticky-burr", "wind", "air"),  # "In March the wind blew down the sleeve"
    }, sorted(says)


def test_the_table_is_pinned_for_the_words_editor():
    """The table and some lines decided, as the words editor's node test reads them (tests/golden/say-*.json;
    regenerate with SONGBIRD_UPDATE_GOLDEN=1 after an intended change to the rules)."""
    lines = {line: H.decide(line) for line, _, _ in CASES}
    lines.update({t: H.decide(t) for t in ["The *bass*, the drum", "wind — the wind", "bass{fish} and bass",
                                              "Close, the door; close the door", "a (live) wire", "“Wind” the clock up"]})
    for name, data in (("say-table.json", H.table()), ("say-lines.json", lines)):
        path = GOLDEN / name
        if os.environ.get("SONGBIRD_UPDATE_GOLDEN"):
            path.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        assert data == json.loads(path.read_text()), name
