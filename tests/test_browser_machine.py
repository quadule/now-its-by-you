"""A visitor's browser as the machine (2026-11-09): read as a computer is read quietly (harvest.here: its languages,
size and screen; never its files, documents or typing), from what any page may ask (device.js browserFacts), reduced by
the same functions to the same coarse buckets, with a salt the page keeps so it's the same singer from visit to visit.
The web studio then works as the standalone does: the machine moves the song, its style on the ring among it."""

import importlib.util
import sys
from pathlib import Path

import pytest

from songbird import explain, harvest as Hv, studio as S
from songbird.variation import character

ROOT = Path(__file__).resolve().parents[1]
LEAD = ROOT / "songs" / "h-now-its-by-you.json"
SALT = "0123456789abcdef"
FACTS = {"languages": ["de-CH", "de", "en-GB"], "cores": 8, "memory": 4, "dark": True}


def _device():
    spec = importlib.util.spec_from_file_location("studio_device", ROOT / "web" / "studio-wasm" / "py" / "studio_device.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["studio_device"] = module
    spec.loader.exec_module(module)
    return module


def test_a_browser_is_reduced_as_a_computer_is():
    v = Hv.browser(FACTS, SALT)
    assert v.tongue == Hv.reduce_tongue(["de-CH", "de", "en-GB"])  # the vote, as a computer's locales
    assert (v.machine.cores, v.machine.memory, v.machine.uptime) == (0.5, 0.0, None)  # no uptime: a page can't see it
    assert v.colour == Hv.reduce_appearance(True, None)  # dark, no accent colour read
    assert (v.ages, v.words, v.hand, v.room) == (None, None, None, None)  # never files, documents, typing or a room
    assert v.hash == Hv.Voice(salt=SALT).hash  # who sings is the salt alone, as for a computer
    # Chromium's deviceMemory stopped at 8 for years: "at least 8", so unknown (the middle), not a small machine's;
    # what later ones say past it is taken as said
    assert Hv.browser({**FACTS, "memory": 8}, SALT).machine.memory == Hv.reduce_machine(8, None, None).memory
    assert Hv.browser({**FACTS, "memory": 32}, SALT).machine.memory == Hv.reduce_machine(8, 32 * 2**30, None).memory
    bare = Hv.browser({}, SALT)  # a browser that says nothing: no signals, but still a machine of its own
    assert bare.neutral and bare.salt == SALT
    with pytest.raises(ValueError):
        Hv.browser(FACTS, "not a salt")
    junk = Hv.browser({"languages": [3, None, "fr"], "cores": True, "memory": "lots", "dark": "yes"}, SALT)
    assert junk.tongue == Hv.reduce_tongue(["fr"]) and junk.machine is None and junk.colour is None


def test_its_spec_is_its_voice_and_the_machine_reads_musically():
    v = Hv.browser(FACTS, SALT)
    spec = Hv.browser_spec(v)
    assert spec.startswith("browser:") and Hv.machine_voice(spec) == v
    c = character(v)
    assert {"identity", "density", "brightness", "warmth", "family", "inventory"} <= c.known
    assert "tired" not in c.known and c.tired == 0.0  # unknown, not middling
    words = explain.machine_words(v)
    assert any("small machine" in w for w in words) and not any("up for" in w or "restarted" in w for w in words)
    assert "a dark screen" in words  # no accent colour read: no colour said


def test_the_web_studio_sings_as_the_visitor_s_browser(tmp_path):
    D = _device()
    config = {"song": str(LEAD), "machine": "browser", "home": str(tmp_path), "browser": {"facts": FACTS, "salt": SALT}}
    assert D.machine_of(config) == Hv.browser_spec(Hv.browser(FACTS, SALT))
    assert D.machine_of({**config, "browser": {"facts": FACTS, "salt": "x"}}) == "none"  # unreadable: time alone
    assert D.machine_of({**config, "browser": None}) == "none"
    assert D.machine_of({"machine": "fictional:wren"}) == "fictional:wren"  # the build's own, as before
    device = D.Device(config)
    s = device.studio
    assert s.voice == Hv.browser(FACTS, SALT) and s.context.machine_label() == "this browser"
    # as the standalone: a machine that is someone moves the style (the ring, the options, the motif's chance),
    # where time alone (none) keeps the parent's style as it was
    mine = s.version({}).params.style
    neutral = S.Studio(machine="none", home=tmp_path / "neutral").version({}).params.style
    assert mine.lineage and neutral.lineage
    if mine.name in ("", "ballad"):
        assert mine.motif == "chance"
    assert mine != neutral



# --- the published version first (2026-11-09: "start with the currently published version's lyrics and settings but
# have a prominent button to switch to the new version")

RECORD = ROOT / "webstudio" / "released-record.json"


def test_the_released_record_is_the_newest_edition_s():
    """webstudio/released-record.json is the packet's own manifest of the edition the home page offers
    (tools/released_record.py), so the studio opens on what was published and nothing else."""
    import json

    edition = json.loads((ROOT / "web" / "sing" / "editions.json").read_text())["editions"][0]
    record = json.loads(RECORD.read_text())
    assert record["id"] == edition["audio"] and record["program_sha256"] == edition["program"]


def test_the_published_view_is_the_release_as_it_was_and_the_new_one_continues_it(tmp_path):
    import json

    D = _device()
    config = {"song": str(LEAD), "parent": str(RECORD), "home": str(tmp_path / "a"), "released_on": "2026-09-28"}
    published = D.Device({**config, "machine": "published"})
    s = published.studio
    v = s.version({})
    assert v.params.to_dict() == json.loads(RECORD.read_text())["params"]  # its settings exactly, nothing chosen
    assert v.drift is None and s.context.published
    start = s.start_view()
    assert start["published"] == {"which": "the first version", "made": "Monday, September 28, 2026",
                                  "id": json.loads(RECORD.read_text())["id"]}
    assert start["generation"] == 0 and start["machine"]["label"] == "as it was published"
    assert "published_offer" not in start
    assert s.version({"tempo": 100}).params.tempo == 100  # a person's changes go on top of it, as on any version
    # every first question is answered on it, as the build makes them ahead
    assert all(status in (200, 404) for status, _ in D.first_answers(published).values())
    # this browser's: the published version's next, moved by the browser and today, and the way back offered
    new = D.Device({**config, "home": str(tmp_path / "b"), "machine": "browser", "browser": {"facts": FACTS, "salt": SALT}})
    n = new.studio
    assert n.start_view()["generation"] == 1 and n.start_view().get("published_offer") is True
    assert "published" not in n.start_view() and n.context.machine_label() == "this browser"
    assert n.version({}).params.to_dict() != v.params.to_dict()


def test_the_published_words_can_be_chosen_among(tmp_path):
    """The published version sings the song's own words (its record keeps none): a verse's options are the bank's,
    the one sung its own, and choosing another keeps the rest as published."""
    D = _device()
    config = {"song": str(LEAD), "parent": str(RECORD), "home": str(tmp_path / "a"), "released_on": "2026-09-28"}
    s = D.Device({**config, "machine": "published"}).studio
    assert s.version({}).lyrics is None
    assert all(w["changeable"] for w in s.song({})["words"] if w.get("sung"))
    options = s.options({}, "verse", 0)
    assert options["sung"] == "wire" and sum(c["allowed"] for c in options["choices"]) > 3
    chosen = s.version({"words.verse.0": {"id": "box"}})
    assert [x.id for x in chosen.lyrics.sections if x.block == "verse"] == ["box", "screen"]
