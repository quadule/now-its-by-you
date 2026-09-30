"""Sound design (docs/SOUND-DESIGN.md): a person's patch, filter and kit for a player, its pan, send and sidechain,
and the transitions at a section boundary, as edits. With none, nothing changes (the goldens say so too). Values
are made canonical and refused with why; the patches sit where the program's own sit; a kit is its module, its
pieces their character; the pump ducks a channel on the drum player's kicks (or every beat) and only where asked;
a riser ends on the downbeat and rises; a roll takes the snare's place; a sweep filters only its bars; marked in
the record, made again from it, replayed the same, handed down; a section's preview moves it all with the notes;
the studio says each player's sound and each boundary's transition, whose it is."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from songbird import composition as C, drift as D, edits as E, harvest as H, midi, sound as S
from songbird import studio as ST
from songbird.genome import load
from songbird.realize import Params, choose_params, realize, timeline
from songbird.score import Note
from songbird.synth import analog, drummachine, instruments, master, mixing, sweeps

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import instrument_levels as L  # noqa: E402

G = load(ROOT / "songs" / "h-now-its-by-you.json")
ADA = H.fictional("ada")
DAY = D.drift(D.parse("2026-09-26"), ADA.hash)
SR = 44100
SYNTH = {"style.name": "synthfolk"}
EDM = {**SYNTH, "tempo": 124, "sound.synthbass.patch": "reese", "sound.drummachine.kit": "909",
       "mix.synthpad.sidechain": "classic", "mix.synthbass.sidechain": {"depth": 6, "release": 0.4},
       "mix.synthpad.pan": -0.3, "mix.arp.send": 2.0,
       "transition.refrain:0": {"riser": 2, "roll": 1, "sweep": 2, "impact": True}}


def resolved(edits, parent=None, voice=None, drift=None):
    clean, problems = E.check(G, edits)
    assert not problems, problems
    return E.resolve(G, parent, voice, drift, clean)


def centroid(y):
    m = y.mean(axis=1) if y.ndim == 2 else y
    f = np.fft.rfftfreq(len(m), 1 / SR)
    p = np.abs(np.fft.rfft(m)) ** 2
    return float(np.sum(f * p) / np.sum(p))


# --- nothing without it --------------------------------------------------------------------------------------


def test_no_sound_design_is_the_song_as_it_was():
    p = choose_params(G)
    assert p.sound == {} and "sound" not in p.to_dict()
    score = realize(G, p)
    assert score.sound == {} and "sound" not in score.to_dict()
    r = resolved(SYNTH)
    assert "sound" not in r.params.to_dict() and realize(G, r.params).sound == {}
    assert analog.patched("synth-pad", {}) is analog.PRESETS["synth-pad"]  # the preset itself, the same object


# --- checking -------------------------------------------------------------------------------------------------


def test_values_are_made_canonical():
    clean, problems = E.check(G, {
        "mix.synthpad.sidechain": "heavy",
        "mix.synthbass.sidechain": {"release": 0.5, "depth": 6.04, "sections": ["refrain", "bridge"]},
        "transition.refrain:1": {"impact": True, "sweep": 4, "riser": 2},
        "transition.bridge:0": {"sweep": {"bars": 1, "type": "lowpass"}, "down": 0},
        "sound.drummachine.snare": {"snappy": 1.5, "tune": -2},
        "sound.synthbass.cutoff": 99999, "sound.synthlead.resonance": 0.456,
        "mix.guitar.pan": -3, "mix.arp.send": 1.234,
    })
    assert not problems, problems
    assert clean["mix.synthpad.sidechain"] == {"depth": 14.0, "release": 0.85, "key": "kick", "sections": None}
    bass = clean["mix.synthbass.sidechain"]
    assert list(bass) == ["depth", "release", "key", "sections"] and bass["depth"] == 6.0
    assert bass["sections"] == ["bridge", "refrain"]
    assert list(clean["transition.refrain:1"]) == ["riser", "sweep", "impact"]
    assert clean["transition.refrain:1"]["sweep"] == {"bars": 4, "type": "highpass"}
    assert clean["transition.bridge:0"] == {"sweep": {"bars": 1, "type": "lowpass"}}
    assert list(clean["sound.drummachine.snare"]) == ["tune", "snappy"]
    assert clean["sound.synthbass.cutoff"] == 16000 and clean["sound.synthlead.resonance"] == 0.46
    assert clean["mix.guitar.pan"] == -1.0 and clean["mix.arp.send"] == 1.23


@pytest.mark.parametrize("path, value, why", [
    ("sound.synthbass.patch", "wobble", "patches are analog, sub, reese, pluck"),
    ("sound.fiddle.patch", "reese", "no patches"),
    ("sound.guitar.kit", "909", "no kits"),
    ("sound.chip.cutoff", 400, "no filter"),
    ("sound.drummachine.kick", {"punch": 1}, "not punch"),
    ("sound.theremin.patch", "saw", "no player called theremin"),
    ("mix.synthpad.sidechain", "huge", "presets are subtle, classic, heavy"),
    ("mix.synthpad.sidechain", {"key": "snare"}, "on the kick or on every beat"),
    ("transition.chorus:0", {"riser": 1}, "no section called chorus"),
    ("transition.refrain:0", {"riser": 3}, "lasts 1, 2, 4 bars"),
    ("transition.refrain:0", {"drop": True}, "not drop"),
])
def test_refusals_say_why(path, value, why):
    clean, problems = E.check(G, {path: value})
    assert path not in clean and why in problems[0]["why"], problems


def test_a_player_the_band_hasnt_got_a_section_it_doesnt_sing_and_the_first_are_refused():
    r = E.resolve(G, None, None, None, E.check(G, {"sound.synthbass.patch": "reese"})[0])
    assert "no such player" in r.problems[0]["why"] and "sound" not in r.params.to_dict()
    form = choose_params(G, style="synthfolk").form
    first = C.section_ids(form)[0]
    edits = {**SYNTH, f"transition.{first}": {"riser": 2}, "transition.refrain:9": {"impact": True},
             "transition.refrain:0": {"impact": True}}
    r = E.resolve(G, None, None, None, E.check(G, edits)[0])
    said = {p["path"]: p["why"] for p in r.problems}
    assert "begins there" in said[f"transition.{first}"]
    assert "doesn't sing that section" in said["transition.refrain:9"]
    assert r.params.sound == {"transitions": {"refrain:0": {"impact": True}}}
    ok = E.resolve(G, None, None, None, E.check(G, {**SYNTH, f"transition.{first}": {"impact": True}})[0])
    assert not ok.problems  # an impact on the first downbeat is fine


# --- the sounds -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("synth", list(analog.PATCHES))
def test_the_patches_sit_where_the_programs_own_sits(synth):
    spec = analog.SPEC[synth]
    notes = L.typical_part(spec)
    levels, sounds = {}, {}
    for patch in analog.PATCHES[synth]:
        y = L.render_placed(analog, synth, notes, {**L.SETTINGS, "patch": patch})
        levels[patch] = L.loudness_while_playing(y, notes)
        sounds[patch] = y
    own = next(iter(levels))
    for patch, lufs in levels.items():
        assert abs(lufs - levels[own]) < (2.5 if patch == "sub" else 1.0), (patch, lufs, levels[own])
        if patch != own:
            assert not np.array_equal(sounds[patch], sounds[own])
    assert np.array_equal(sounds[own], L.render_placed(analog, synth, notes))  # the program's own, to the bit


def test_the_filter_is_the_persons_and_the_brightness_no_longer_moves_it():
    spec = analog.SPEC["synth-bass"]
    notes = L.typical_part(spec)
    dark = L.render_placed(analog, "synth-bass", notes, {**L.SETTINGS, "cutoff": 150})
    open_ = L.render_placed(analog, "synth-bass", notes, {**L.SETTINGS, "cutoff": 3000})
    assert centroid(open_) > 1.5 * centroid(dark)
    a = L.render_placed(analog, "synth-bass", notes, {**L.SETTINGS, "cutoff": 600, "brightness": 0.1})
    b = L.render_placed(analog, "synth-bass", notes, {**L.SETTINGS, "cutoff": 600, "brightness": 0.9})
    assert np.array_equal(a, b)


def test_the_chip_takes_a_width():
    notes = L.typical_part({"role": "lead", "register": (45, 96)})
    from songbird.synth import chip

    own = chip.render("chip", notes, SR, int(12 * SR), None, np.random.default_rng(0), dict(L.SETTINGS))
    hollow = chip.render("chip", notes, SR, int(12 * SR), None, np.random.default_rng(0),
                         {**L.SETTINGS, "patch": "hollow"})
    assert not np.array_equal(own, hollow) and centroid(hollow) < centroid(own)


def _kit_part():
    spec = drummachine.SPEC["drums-808"]
    return tuple(Note("drummachine", n.start, n.dur, n.pitch, n.vel, art=n.art) for n in L.typical_part(spec))


def test_a_kit_is_its_module_and_the_pieces_their_character():
    notes = _kit_part()
    length = int(np.ceil((max(n.start for n in notes) + 2.0) * SR))
    band = {"maker": 0}

    def stem(sound=None):
        return instruments.render_part("drummachine", notes, SR, length, band, 7, sound)

    own, t909 = stem(), stem({"kit": "909"})
    assert np.array_equal(own, stem({}))  # nothing chosen: its own
    assert not np.array_equal(own, t909)
    lofi, acoustic = stem({"kit": "lofi"}), stem({"kit": "acoustic"})
    assert centroid(lofi) < 0.7 * centroid(own) and not np.array_equal(acoustic, own)
    # the 909's level is its module's, calibrated as the band's percussion: the two sit within 3 dB
    assert abs(master.loudness(t909, SR) - master.loudness(own, SR)) < 3.0
    long = stem({"kick": {"decay": 3.0}})
    kicks = [n.start for n in notes if n.art == "kick"]
    tail = lambda y: sum(float(np.sum(y[int((t + 0.3) * SR): int((t + 0.45) * SR)] ** 2)) for t in kicks)  # noqa: E731
    assert tail(long) > 2.0 * tail(own)
    # a drummer's strokes named for a machine and a machine's for a drummer
    mapped = instruments._restroke((Note("kit", 0, 0.1, 38, 0.5, art="brush-sweep"),
                                    Note("kit", 0.5, 0.1, 38, 0.5, art="snare-ghost")), instruments.KIT_TO_MACHINE)
    assert [(n.art, n.vel) for n in mapped] == [("snare", 0.2)]
    mapped = instruments._restroke((Note("dm", 0, 0.1, 60, 0.5, art="clap"),), instruments.MACHINE_TO_KIT)
    assert mapped[0].art == "snare"


# --- the sidechain --------------------------------------------------------------------------------------------


def test_the_pump_dips_on_each_trigger_and_comes_back():
    length = 3 * SR
    t = np.arange(length) / SR
    tone = np.stack([np.sin(2 * np.pi * 220 * t)] * 2, axis=1) * 0.1
    sound = {"players": {"synthpad": {"sidechain": {"depth": 8.0, "release": 0.25, "attack": 0.003}}},
             "triggers": [[0.5, "synthpad"], [1.0, "synthpad"], [2.0, "synthpad"]]}
    design = mixing.Design(sound, SR)
    gain = design.gain("synthpad", 0, length)
    db = 20 * np.log10(gain)
    assert db[int(0.49 * SR)] == 0.0 and abs(db[int(0.5035 * SR)] + 8.0) < 0.05
    assert -8.0 < db[int(0.6 * SR)] < -1.0 and db[int(0.76 * SR)] == 0.0
    assert design.gain("guitar", 0, length) is None
    taps = {}
    mixing.mix_made([("synthpad", lambda: tone.copy()), ("guitar", lambda: tone.copy())], length, SR, taps=taps,
                    sound=sound)
    where, pad = taps["synthpad"]
    _, guitar = taps["guitar"]
    env = lambda x, s: float(np.sqrt(np.mean(x[int(s * SR) - where.start:][:int(0.02 * SR)] ** 2)))  # noqa: E731
    assert env(pad, 0.51) < 0.5 * env(pad, 0.4)  # 8 dB down just after the trigger
    assert abs(env(guitar, 0.51) / env(guitar, 0.4) - 1) < 0.05  # the unpumped channel isn't


def test_the_key_track_is_the_drummers_kicks_and_the_sections_asked():
    r = resolved({**SYNTH, "mix.synthpad.sidechain": {"sections": ["refrain"]},
                  "mix.synthbass.sidechain": {"preset": "subtle", "key": "beat"}})
    score = realize(G, r.params)
    kicks = sorted(n.start for n in score.notes if n.part == "drummachine" and n.art == "kick")
    pad = [t for t, p in score.sound["triggers"] if p == "synthpad"]
    refrains = [(a, b) for name, a, b in score.sections if name == "refrain"]
    assert pad and all(any(a - 0.01 <= t < b for a, b in refrains) for t in pad)
    assert set(round(t, 6) for t in pad) <= set(round(t, 6) for t in kicks)
    beats = [t for t, _ in timeline(G, r.params).beats()]
    bass = [t for t, p in score.sound["triggers"] if p == "synthbass"]
    assert len(bass) == len(beats)
    assert score.sound["players"]["synthbass"]["sidechain"]["depth"] == 4.0
    # the release, in beats, follows the tempo: seconds at this version's
    assert abs(score.sound["players"]["synthbass"]["sidechain"]["release"] - 0.35 * 60 / r.params.tempo) < 1e-6


# --- the transitions ------------------------------------------------------------------------------------------


def test_the_transitions_land_on_the_boundary():
    r = resolved(EDM)
    params = r.params
    score = realize(G, params)
    clock = timeline(G, params)
    at = C.beat_clock(clock)
    k = C.section_ids(params.form).index("refrain:0")
    # the section's first bar line, as the band counts it: the song's lead, then every section before it
    u0 = clock.lead + sum(G.phrases[pid].bars for name in params.form[:k] for pid in G.section(name).phrases) \
        * G.meter.bar
    downbeat = at(u0)
    bar = G.meter.bar
    kinds = {t["kind"]: t for t in score.sound["transitions"]}
    assert set(kinds) == {"riser", "sweep-hp", "impact"}  # the roll is the drum player's
    assert abs(kinds["riser"]["end"] - downbeat) < 1e-9 and abs(kinds["riser"]["start"] - at(u0 - 2 * bar)) < 1e-9
    assert kinds["sweep-hp"]["start"] == kinds["riser"]["start"] and kinds["sweep-hp"]["end"] == downbeat
    assert abs(kinds["impact"]["start"] - downbeat) < 1e-9 and kinds["impact"]["kick"]
    roll_start = at(u0 - bar)
    in_roll = [n for n in score.notes if n.part == "drummachine" and roll_start - 1e-6 <= n.start < downbeat - 1e-6]
    snares = [n for n in in_roll if n.art == "snare"]
    assert len(snares) == 1 + 2 + 4 + 8  # quarters, eighths, sixteenths, thirty-seconds over the bar's four beats
    assert all(n.art in ("snare", "kick") or "hat" in n.art for n in in_roll)
    vels = [n.vel for n in sorted(snares, key=lambda n: n.start)]
    assert vels == sorted(vels) and vels[0] < 0.4 and vels[-1] > 0.9


def test_a_riser_rises_and_a_sweep_filters_only_its_bars():
    y = sweeps.riser(int(4 * SR), SR, np.random.default_rng(1))
    quarters = [centroid(y[q * len(y) // 4:(q + 1) * len(y) // 4]) for q in range(4)]
    assert quarters == sorted(quarters) and quarters[-1] > 5 * quarters[0]
    rms = [float(np.sqrt(np.mean(y[q * len(y) // 4:(q + 1) * len(y) // 4] ** 2))) for q in range(4)]
    assert rms == sorted(rms)
    x = np.random.default_rng(2).standard_normal((3 * SR, 2))
    dry = x.copy()
    sweeps.sweep([x], SR, [("sweep-hp", SR // 2, 2 * SR)])
    assert np.array_equal(x[: SR // 2], dry[: SR // 2]) and np.array_equal(x[2 * SR + 200:], dry[2 * SR + 200:])
    low = lambda s: float(np.sum(np.abs(np.fft.rfft(s[:, 0]))[: len(s) // 2 * 200 // SR] ** 2))  # noqa: E731
    end = slice(int(1.8 * SR), 2 * SR)
    assert low(x[end]) < 0.01 * low(dry[end])  # under 200 Hz, 20 dB down as the corner nears 1.5 kHz


def test_the_mix_sweeps_the_band_and_not_the_transitions():
    length = 3 * SR
    noise = np.random.default_rng(3).standard_normal((length, 2)) * 0.05
    sound = {"transitions": [{"kind": "sweep-hp", "start": 0.5, "end": 2.0, "level": 1.0, "key": 2}]}
    plain, swept = {}, {}
    parts = [("guitar", lambda: noise.copy()), ("fx", lambda: noise.copy())]
    a = mixing.mix_made(parts, length, SR, taps=plain)
    b = mixing.mix_made(parts, length, SR, taps=swept, sound=sound)
    assert not np.array_equal(a, b)
    assert np.array_equal(plain["fx"][1], swept["fx"][1])  # the transitions' own stem joins unswept
    # a stop: the band silent over its beats, back at the downbeat, the transitions going on
    stop = {"transitions": [{"kind": "stop", "start": 1.0, "end": 1.5, "level": 1.0, "key": 6}]}
    band = np.zeros((length, 2))
    x = noise.copy()
    sweeps.sweep([x, band], SR, sweeps.sweep_spans(stop["transitions"], SR))
    assert not np.any(x[int(1.01 * SR): int(1.5 * SR)]) and np.array_equal(x[int(1.5 * SR):], noise[int(1.5 * SR):])
    assert np.array_equal(x[:SR], noise[:SR])
    clean, problems = E.check(G, {"transition.refrain:0": {"stop": 2}, "transition.refrain:1": {"stop": 3}})
    assert clean["transition.refrain:0"] == {"stop": 2} and "lasts 1, 2, 4 beats" in problems[0]["why"]


# --- the record ------------------------------------------------------------------------------------------------


def test_marked_made_again_from_the_record_replayed_and_handed_down():
    r = E.resolve(G, None, ADA, DAY, E.check(G, EDM)[0])
    assert not r.problems, r.problems
    assert r.marks["sound.synthbass.patch"] == {"value": "reese", "was": "analog"}
    assert r.marks["sound.drummachine.kit"] == {"value": "909", "was": "808"}
    assert r.marks["mix.synthpad.sidechain"]["was"] is None
    assert r.marks["transition.refrain:0"]["value"]["sweep"] == {"bars": 2, "type": "highpass"}
    record = json.loads(json.dumps({"params": r.params.to_dict(), "chosen_by_you": r.marks}))
    again = E.resolve(G, None, ADA, DAY, E.from_record(record))
    assert again.params == r.params
    replayed = Params.from_dict(record["params"])  # as --replay reads it: the same score, so the same samples
    assert realize(G, replayed) == realize(G, r.params)
    child = choose_params(G, replayed, H.fictional("basil"), DAY)
    assert child.sound == r.params.sound  # a person's sound passes on
    released = E.resolve(G, child, None, None, {"sound.synthbass.patch": None})
    assert "patch" not in released.params.sound["players"]["synthbass"]
    assert released.marks["sound.synthbass.patch"] == {"value": None, "was": "reese"}


def test_a_preview_moves_the_key_track_and_the_transitions_with_the_notes():
    r = resolved(EDM)
    score = realize(G, r.params)
    riser = next(t for t in score.sound["transitions"] if t["kind"] == "riser")
    t0 = (riser["start"] + riser["end"]) / 2  # a preview beginning in the middle of the riser
    part, lead_in = ST.cut(score, t0, t0 + 10.0)
    moved = next(t for t in part.sound["transitions"] if t["kind"] == "riser")
    start = max(0.0, t0 - 1.0)
    assert abs(moved["start"] - (riser["start"] - start)) < 1e-9 and moved["start"] < 0 < moved["end"]
    triggers = [t for t, _ in part.sound["triggers"]]
    assert triggers and min(triggers) >= 0 and max(triggers) < 10.0 + lead_in
    # the riser in the preview is the whole song's, from where the preview begins
    whole = sweeps.make_fx(score.sound["transitions"], SR, int((riser["end"] + 2) * SR), r.params.seed)
    cut = sweeps.make_fx(part.sound["transitions"], SR, int((moved["end"] + 2) * SR), r.params.seed)
    i = int(round(riser["start"] * SR)) - int(round(moved["start"] * SR))  # where the preview's zero is in the song
    n = int(0.5 * SR)
    assert np.max(np.abs(cut[SR: SR + n] - whole[i + SR: i + SR + n])) < 1e-9


def test_nothing_leaks_into_the_notes_the_midi_file_or_the_stems_it_shouldnt():
    r = resolved(EDM)
    score = realize(G, r.params)
    assert {n.part for n in score.notes} == {p["part"] for p in midi.layout(score)}
    assert not {"fx", "sidechain"} & {n.part for n in score.notes}
    names = [name for name, _ in instruments.band_parts(score, SR, r.params.seed)]
    assert names[-1] == "fx"  # risers and impacts: a stem of their own, among --stems too


# --- the studio -----------------------------------------------------------------------------------------------


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    return ST.Studio(None, str(ROOT / "songs" / "h-now-its-by-you.json"), "fictional:ada", out=tmp_path / "out")


def test_the_studio_says_each_players_sound_and_whose_it_is(studio):
    view = studio.sound(EDM)
    players = {p["player"]: p for p in view["players"]}
    bass = players["synthbass"]
    assert bass["patch"]["value"] == "reese" and bass["patch"]["yours"] and bass["patch"]["program"] == "analog"
    assert [o["name"] for o in bass["patch"]["options"]] == ["analog", "sub", "reese", "pluck"]
    assert bass["filter"]["cutoff"]["value"] == bass["filter"]["cutoff"]["patch"] and not bass["filter"]["cutoff"]["yours"]
    assert bass["sidechain"]["value"]["depth"] == 6.0 and bass["sidechain"]["yours"] and bass["sidechain"]["has_kick"]
    drums = players["drummachine"]
    assert drums["kit"]["value"] == "909" and drums["kit"]["program"] == "808" and drums["pieces"]["kick"]["knobs"]
    assert drums["sidechain"]["is_key"] and not bass["sidechain"]["is_key"]  # the page offers no pump on the key
    where = {p["player"]: p for p in studio.sound({**EDM, "mix.synthpad.sidechain": {"preset": "heavy", "sections": [
        "refrain:1", "refrain:2"]}})["players"]}["synthpad"]["sidechain"]["value"]  # the page's "where" choice
    assert where["sections"] == ["refrain:1", "refrain:2"] and where["depth"] == 14.0
    assert players["synthpad"]["pan"] == {**players["synthpad"]["pan"], "value": -0.3, "yours": True}
    assert players["guitar"]["patch"] is None and players["guitar"]["kit"] is None and not players["guitar"]["send"]["yours"]
    into = {b["id"]: b for b in view["boundaries"]}
    assert into["refrain:0"]["yours"] and into["refrain:0"]["value"]["riser"] == 2 and into["refrain:0"]["name"] == "Refrain 1"
    assert not view["boundaries"][0]["before"] and view["problems"] == []
    plain = studio.sound({})
    assert all(not v["yours"] for p in plain["players"] for k, v in p.items()
               if isinstance(v, dict) and "yours" in v)
