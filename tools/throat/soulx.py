"""Sung notes as SoulX-Singer metadata (dev only: SoulX-Singer is a reference and a teacher, never shipped).

SoulX-Singer (Apache-2.0, installed beside the repo at ~/Code/svs/SoulX-Singer with its own venv)
sings a score given, per note, its phones (ARPAbet), its length and its MIDI pitch, in the timbre of
a ten-second prompt. These helpers turn our notes (songbird.score.Note, or dicts with the same
fields) into its metadata. From renders/reference/svs/score_to_soulx.py, where they were first
written for the H reference renders.

Each note carries its own syllable (note_type 2); a note past the word's syllables holds the last
one (note_type 3). A line's last note gives up `breath` seconds to silence when the next line
follows at once, as a singer breathes there.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from songbird import phonetics as P  # noqa: E402


def plain(word: str) -> str:
    """A written word without focus marks or syllable hyphens."""
    return word.replace("*", "").replace("-", "")


def word_phones(word: str, n: int, lexicon: dict) -> list[str]:
    """The word's ARPAbet (with stress digits), fitted to n notes as songbird.phonetics.fit does."""
    readings = P.pronunciations(word.replace("*", ""), lexicon)
    if not readings:
        raise KeyError(f"no pronunciation for {word!r}")
    exact = [r for r in readings if P._vowel_count(r) == n]
    phones = list(exact[0] if exact else readings[0])
    while P._vowel_count(phones) > n:  # as fit(): fi-er -> fire, then drop unstressed vowels
        for i in range(1, len(phones)):
            if phones[i] == "ER0" and phones[i - 1].rstrip("012") in P.VOWELS:
                phones[i] = "R"
                break
        else:
            unstressed = [i for i, p in enumerate(phones) if p.endswith("0")]
            if not unstressed:
                break
            del phones[unstressed[-1]]
    return phones


def syllables(phones: list[str]) -> list[list[str]]:
    """Phones split into syllables, consonants to the following onset as far as English allows."""
    nuclei = [i for i, p in enumerate(phones) if p.rstrip("012") in P.VOWELS]
    bounds = []
    for left, right in zip(nuclei, nuclei[1:]):
        cluster = phones[left + 1 : right]
        split = len(cluster)
        for k in range(len(cluster) + 1):
            if not cluster[k:] or tuple(cluster[k:]) in P.LEGAL_ONSETS:
                split = k
                break
        bounds.append(left + 1 + split)
    return [phones[a:b] for a, b in zip([0] + bounds, bounds + [len(phones)])]


def note_phones(notes: list[dict], lexicon: dict) -> list[tuple[str, list[str], int]]:
    """(word, the note's phones, note_type) for each note, words grouped by word_len."""
    out = []
    i = 0
    while i < len(notes):
        n = notes[i]
        k = max(1, int(n["word_len"]))
        group = notes[i : i + k]
        if len(group) < k or any(g["word"] != n["word"] for g in group):  # the stretch cuts through a word
            k = 1
            while i + k < len(notes) and notes[i + k]["word"] == n["word"] and k < n["word_len"]:
                k += 1
            group = notes[i : i + k]
        sylls = syllables(word_phones(n["word"], n["word_len"], lexicon))
        for j, _ in enumerate(group):
            out.append((plain(n["word"]), sylls[min(j, len(sylls) - 1)], 3 if j >= len(sylls) else 2))
        i += len(group)
    return out


def segment(notes: list[dict], lexicon: dict, t0: float, t1: float, breath: float, index: str, shift: int = 0) -> dict:
    """One metadata segment singing these notes on [t0, t1), seconds on the notes' timeline.

    The notes kept in the segment are relative to t0, each with its phones and the stretch SoulX was
    told to sing it for (sung_start, sung_end), so the audio can be labelled afterwards."""
    tokens = note_phones(notes, lexicon)
    items = []  # (text, phoneme token, dur, pitch, type)
    kept = []
    cursor = t0
    for i, (n, (text, phones, ntype)) in enumerate(zip(notes, tokens)):
        start = n["start"]
        if start - cursor > 1e-4:
            items.append(("<SP>", "<SP>", start - cursor, 0, 1))
        elif start < cursor:  # overlapping notes: this one starts where the last ended
            start = cursor
        nxt = notes[i + 1]["start"] if i + 1 < len(notes) else None
        end = start + n["dur"] if nxt is None or nxt - (n["start"] + n["dur"]) > 0.1 else nxt
        end = min(end, t1)
        if n.get("line_end") and breath > 0 and nxt is not None and abs(nxt - end) < 1e-6:
            end -= min(breath, 0.35 * (end - start))
        pitch = int(round(n["pitch"])) + shift
        items.append((text, "en_" + "-".join(phones), end - start, pitch, ntype))
        kept.append({"start": n["start"] - t0, "dur": n["dur"], "sung_start": start - t0, "sung_end": end - t0,
                     "pitch": pitch, "phones": phones, "type": ntype, "syllable": n.get("syllable"),
                     "word": n["word"], "word_len": n["word_len"], "line_end": bool(n.get("line_end")),
                     "vel": n.get("vel", 0.75)})
        cursor = end
    if t1 - cursor > 1e-4:
        items.append(("<SP>", "<SP>", t1 - cursor, 0, 1))
    return {
        "index": index,
        "language": "English",
        "time": [int(round(t0 * 1000)), int(round(t1 * 1000))],
        "t0": t0,
        "t1": t1,
        "duration": " ".join(f"{x[2]:.5f}" for x in items),
        "text": " ".join(x[0] for x in items),
        "phoneme": " ".join(x[1] for x in items),
        "note_pitch": " ".join(str(x[3]) for x in items),
        "note_type": " ".join(str(x[4]) for x in items),
        "notes": kept,
    }


def segments(notes: list[dict], lexicon: dict, name: str, *, breath: float = 0.15, lead: float = 0.3,
             tail: float = 0.4, split: float = 1.0, longest: float = 34.0, shift: int = 0) -> list[dict]:
    """Stretches of continuous singing as segments: a gap longer than `split` seconds, or a stretch
    longer than `longest`, starts a new one (at a line's end)."""
    groups, cur = [], []
    for n in notes:
        if cur:
            gap = n["start"] - (cur[-1]["start"] + cur[-1]["dur"])
            too_long = n["start"] - cur[0]["start"] > longest and cur[-1].get("line_end")
            if gap > split or too_long:
                groups.append(cur)
                cur = []
        cur.append(n)
    if cur:
        groups.append(cur)
    out = []
    for k, g in enumerate(groups):
        t0 = max(0.0, g[0]["start"] - lead)
        t1 = g[-1]["start"] + g[-1]["dur"] + tail
        out.append(segment(g, lexicon, t0, t1, breath, f"{name}.{k:02d}", shift))
    return out
