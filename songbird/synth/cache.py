"""Bounded stem reuse for interactive previews (a dry stem, or what the mix's own treatment makes of it); never
part of a recorded rendition."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict

import numpy as np


def _audio(value):
    """The samples a cacheable value holds: a stem, or a treated stem's (span, samples); None for anything else."""
    if isinstance(value, np.ndarray):
        return value
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], slice) and isinstance(value[1], np.ndarray):
        return value[1]
    return None


def _copy(value):
    return value.copy() if isinstance(value, np.ndarray) else (value[0], value[1].copy())


class StemCache:
    """Keep expensive stems within a byte budget, returning an owned copy to the mixer.

    The mixer treats stems in place. Stored snapshots are read-only, and cannot be lent to it.
    Prefer work saved per byte over cheap instrument stems so a small cache does not repeatedly
    evict the singer as it visits the band. All entries belong to this running program only.
    A value is a stem (an array) or a treated stem's (span, samples): only the samples are counted and copied.
    """

    def __init__(self, budget: int = 64 * 2**20):
        self.budget = max(0, int(budget))
        self.bytes = 0
        self.hits = self.misses = 0
        self._entries = {}
        self._clock = 0
        self._lock = threading.Lock()
        self._generation = 0

    def clear(self):
        with self._lock:
            self._entries.clear()
            self.bytes = 0
            self._generation += 1  # a maker already running must not repopulate a cleared cache

    def make(self, key: str, maker, part: str | None = None):
        with self._lock:
            self._clock += 1
            entry = self._entries.get(key)
            if entry is not None:
                self.hits += 1
                entry[2] = self._clock
                try:
                    return _copy(entry[0])
                except MemoryError:
                    # Transfer this snapshot instead of requiring another allocation to hear it.
                    saved = entry[0]
                    self._entries.clear()
                    self.bytes = 0
                    self._generation += 1
                    _audio(saved).flags.writeable = True
                    return saved
            self.misses += 1
            generation = self._generation
        start = time.perf_counter()
        result = maker()
        cost = max(time.perf_counter() - start, 1e-9)
        audio = _audio(result)
        if audio is None or not audio.nbytes or audio.nbytes > self.budget:
            return result
        size = audio.nbytes
        del audio
        with self._lock:
            if generation != self._generation or key in self._entries:
                return result
            # Plan eviction before copying. An inexpensive new stem cannot displace better reuse.
            # An edited part replaces its older take even when the first take included JIT startup.
            victims = [old for old, saved in self._entries.items() if part is not None and saved[3] == part]
            available = self.budget - self.bytes + sum(self._entries[old][4] for old in victims)
            candidates = [(old, saved) for old, saved in self._entries.items() if old not in victims]
            for old, saved in sorted(candidates, key=lambda item: (item[1][1], item[1][2])):
                if available >= size:
                    break
                if saved[1] > cost / size:
                    return result
                victims.append(old)
                available += saved[4]
            for old in victims:
                self.bytes -= self._entries.pop(old)[4]
            try:
                saved = _copy(result)
            except MemoryError:
                return result  # optional reuse must not make an otherwise successful preview fail
            _audio(saved).flags.writeable = False
            self._clock += 1
            self._entries[key] = [saved, cost / size, self._clock, part, size]
            self.bytes += size
        return result


class Cached:
    """A stem's maker through a StemCache (synth.render's, for each stem its key gives). Called, it gives the dry
    stem, kept under that key. A mix that treats the stem the same way on every render asks treated() instead,
    and the cache keeps that treatment in the dry stem's place, never both: a mix edit then neither sings nor
    treats it again, and holds no more than before."""

    def __init__(self, cache: StemCache, key: str, make, part: str):
        self.cache, self.key, self.make, self.part = cache, key, make, part

    def __call__(self):
        return self.cache.make(self.key, self.make, part=self.part)

    def treated(self, how, treat):
        """treat(the dry stem, its own): a treated stem, or its (span, samples), or None. how names everything
        else treat reads (its role, the mix's length and rate...), as JSON: with the dry stem's key, the key
        the treatment is kept under. treat may return the dry stem's own samples: a kept copy is taken."""
        key = hashlib.sha256(json.dumps([self.key, how], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.cache.make(key, lambda: treat(self.make()), part=self.part)


def keys(score, sr, seed, voice, ancestors, names):
    """Hash the realized inputs a dry maker reads, independently of mix/master choices.

    Choir assignment and round placement read other choir parts, so vocal keys deliberately
    include the complete choir context. Band keys omit lyrics and vocal notes, allowing a word
    edit to keep the same instruments. Section timing and length come from the cut score itself.
    """
    notes = {}
    for note in score.notes:
        notes.setdefault(note.part, []).append(asdict(note))
    common = {"sr": sr, "seed": seed, "length": int(np.ceil(score.duration * sr))}
    choir = {name: part for name, part in notes.items() if name.startswith("choir")}
    vocal = {"voice": asdict(voice), "ancestors": [asdict(v) for v in ancestors or []],
             "lexicon": score.lexicon, "choir": choir, "band": score.band}
    out = {}
    for name in names:
        data = {**common, "name": name, "notes": notes.get(name, [])}
        if name in ("voice", "chop") or name.startswith("choir"):
            data.update(vocal)
        else:
            data.update(band=score.band, sound=score.sound)
        try:
            encoded = json.dumps(data, sort_keys=True, separators=(",", ":"),
                                 default=lambda value: value.item() if isinstance(value, np.generic) else asdict(value))
        except (TypeError, ValueError):
            continue  # unusual user-supplied settings still render, without caching
        out[name] = hashlib.sha256(encoded.encode()).hexdigest()
    return out
