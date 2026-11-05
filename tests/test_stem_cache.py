"""Preview reuse stays bounded, owns its audio, and invalidates musical inputs."""

from dataclasses import replace
from threading import Event, Thread

import numpy as np
import pytest

from songbird import synth
from songbird.score import Note, Score
from songbird.synth import mixing
from songbird.synth.cache import Cached, StemCache, keys
from songbird.synth.mixing import MixParams
from songbird.synth.voice import VoiceParams


def test_cache_hits_own_their_samples_and_admission_is_a_snapshot():
    cache = StemCache(64)
    raw = np.arange(8.0)
    made = cache.make("a", lambda: raw)
    made[:] = -1
    heard = cache.make("a", lambda: pytest.fail("cached stem was synthesized again"))
    np.testing.assert_array_equal(heard, np.arange(8.0))
    heard[:] = 99
    np.testing.assert_array_equal(cache.make("a", lambda: None), np.arange(8.0))
    assert cache.bytes == 64 and cache.hits == 2


def test_changed_part_replaces_its_old_take_even_after_expensive_first_synthesis(monkeypatch):
    import songbird.synth.cache as module

    ticks = iter([0, 100, 100, 101])
    monkeypatch.setattr(module.time, "perf_counter", lambda: next(ticks))
    cache = StemCache(64)
    cache.make("old", lambda: np.ones(8), part="voice")
    cache.make("edited", lambda: np.full(8, 2.0), part="voice")
    np.testing.assert_array_equal(cache.make("edited", lambda: pytest.fail("edit was not cached")), 2.0)
    assert cache.bytes == 64


def test_large_stems_are_bypassed_and_clear_discards_inflight_admission():
    cache = StemCache(64)
    cache.make("huge", lambda: np.ones(9))
    assert cache.bytes == 0
    entered, finish = Event(), Event()
    def make():
        entered.set()
        assert finish.wait(5)
        return np.ones(8)
    thread = Thread(target=lambda: cache.make("pending", make))
    thread.start()
    assert entered.wait(5)
    cache.clear()
    finish.set()
    thread.join(5)
    assert not thread.is_alive() and cache.bytes == 0


def test_snapshot_allocation_failure_does_not_fail_a_successful_render():
    class NoCopy(np.ndarray):
        def copy(self):
            raise MemoryError("no room for optional snapshot")
    raw = np.ones(8).view(NoCopy)
    cache = StemCache(64)
    assert cache.make("a", lambda: raw) is raw
    assert cache.bytes == 0


def test_hit_copy_failure_transfers_snapshot_ownership_and_releases_cache():
    class SecondCopyFails(np.ndarray):
        calls = 0
        def copy(self):
            type(self).calls += 1
            if type(self).calls > 1:
                raise MemoryError("no room to copy cached audio")
            return np.ndarray.copy(self)
    cache = StemCache(64)
    cache.make("a", lambda: np.arange(8.0).view(SecondCopyFails))
    heard = cache.make("a", lambda: pytest.fail("cached audio should still be heard"))
    np.testing.assert_array_equal(heard, np.arange(8.0))
    assert cache.bytes == 0 and heard.flags.writeable


def test_small_cache_keeps_costly_singer_instead_of_cheap_band_stems(monkeypatch):
    import songbird.synth.cache as module

    ticks = iter([0, 10, 10, 10.1])
    monkeypatch.setattr(module.time, "perf_counter", lambda: next(ticks))
    cache = StemCache(64)
    cache.make("singer", lambda: np.ones(8), part="voice")
    cache.make("bass", lambda: np.zeros(8), part="bass")
    cache.make("singer", lambda: pytest.fail("cheap band displaced the costly singer"), part="voice")
    assert cache.bytes == 64


def score():
    return Score((Note("bass", 0.05, 0.18, 48, 0.6),
                  Note("voice", 0.05, 0.18, 62, 0.6, syllable="la", word="la")), 0.6, ())


def test_lyric_edit_keeps_band_but_pronunciation_singer_and_duration_invalidate():
    original = score()
    singer = VoiceParams()
    def identify(value, voice=singer, seed=3, sr=44100):
        return keys(value, sr, seed, voice, [], ["bass", "voice"])
    base = identify(original)
    lyric = replace(original, notes=(original.notes[0], replace(original.notes[1], word="love", syllable="love")))
    assert identify(lyric)["bass"] == base["bass"]
    assert identify(lyric)["voice"] != base["voice"]
    assert identify(replace(original, lexicon={"la": "L AA"}))["voice"] != base["voice"]
    assert identify(original, voice=replace(singer, tract=1.1))["voice"] != base["voice"]
    for changed in (replace(original, duration=0.7), replace(original, band={"brightness": 0.3}),
                    replace(original, notes=(replace(original.notes[0], art="mute"), original.notes[1]))):
        assert identify(changed)["bass"] != base["bass"]
    assert identify(original, seed=4) != base and identify(original, sr=48000) != base


def test_choir_range_and_round_entry_invalidate_other_choir_singers():
    original = Score((Note("choir1", 0, 0.2, 62, 0.6, syllable="la", art="round"),
                      Note("choir2", 0.1, 0.2, 50, 0.6, syllable="la", art="round")), 0.6, (),
                     band={"parts": "voices"})
    singer = VoiceParams()
    identify = lambda value, ancestors=[]: keys(value, 44100, 3, singer, ancestors, ["choir1", "choir2"])
    base = identify(original)
    changed = replace(original, notes=(original.notes[0], replace(original.notes[1], pitch=75, start=-0.1)))
    assert identify(changed)["choir1"] != base["choir1"]
    assert identify(original, [replace(singer, tract=1.2)]) != base


def test_mix_edits_reuse_dry_audio_without_changing_uncached_output():
    original = score()
    cache = StemCache(8 * 2**20)
    dry = synth.render(original, seed=3, cache=cache)
    np.testing.assert_array_equal(dry, synth.render(original, seed=3))
    mix = MixParams.from_dict({"balance": {"bass": -2}})
    edited = synth.render(original, seed=3, mix_params=mix, cache=cache)
    assert cache.hits == 2
    np.testing.assert_array_equal(edited, synth.render(original, seed=3, mix_params=mix))
    assert not np.array_equal(dry, edited)
    lyric = replace(original, notes=(original.notes[0], replace(original.notes[1], word="love", syllable="love")))
    changed = synth.render(lyric, seed=3, cache=cache)
    assert cache.hits == 3
    np.testing.assert_array_equal(changed, synth.render(lyric, seed=3))


def test_a_treated_stem_is_kept_with_its_span_and_given_back_as_a_copy():
    cache = StemCache(64)
    made = cache.make("a", lambda: (slice(2, 10), np.arange(8.0)))
    made[1][:] = -1
    where, heard = cache.make("a", lambda: pytest.fail("treated stem was made again"))
    assert where == slice(2, 10) and heard.flags.writeable
    np.testing.assert_array_equal(heard, np.arange(8.0))
    assert cache.bytes == 64 and cache.make("silent", lambda: None) is None and cache.bytes == 64


def test_mix_edits_keep_each_stem_treated_in_place_of_dry_and_finish_it_the_same():
    sr, length = 44100, 2 * 44100
    t = np.arange(length) / sr
    bass = np.stack([np.sin(2 * np.pi * 110 * t), 0.5 * np.sin(2 * np.pi * 110 * t)], axis=1) * (t > 0.8)[:, None]
    voice = np.stack([np.sin(2 * np.pi * 330 * t) * np.sin(2 * np.pi * 3 * t)] * 2, axis=1) * 0.2
    sound = {"players": {"bass": {"sidechain": {"depth": 6.0, "release": 0.2, "attack": 0.003}}},
             "triggers": [[1.0, "bass"], [1.5, "bass"]]}
    lift = np.linspace(-2.0, 2.0, length)
    def makers():
        return [("bass", lambda: bass.copy()), ("voice", lambda: voice.copy())]
    cache = StemCache(64 * 2**20)
    edits = ({}, {"balance": {"bass": -3.0, "voice": 2.0}}, {"voices": 0.0}, {})  # muted, then sung again
    for edit in edits:
        params = MixParams.from_dict(edit)
        kept = [(name, Cached(cache, name, make, name)) for name, make in makers()]
        heard = mixing.mix_made(kept, length, sr, params=params, lift=lift, sound=sound)
        np.testing.assert_array_equal(heard, mixing.mix_made(makers(), length, sr, params=params, lift=lift,
                                                             sound=sound))
    assert cache.misses == 2 and cache.hits == 6 and len(cache._entries) == 2
    assert cache.bytes < bass.nbytes + voice.nbytes  # the bass where it sounds, and no dry stem besides
