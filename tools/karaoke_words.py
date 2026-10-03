"""The karaoke's words: a guide's words, line by line and section by section, with every syllable's time and
pitch, the beats, and each sung section's window for recording it alone. tools/karaoke.py's own (it imports them
from here), kept apart so that the web studio, on a server or in a visitor's browser, can lay a guide's words out
without the karaoke's server and the tools it loads (webstudio/guide.py).
"""

from __future__ import annotations

import bisect

import numpy as np


def lyrics(score: dict, title: str, tempo: float) -> dict:
    """The guide's words, line by line, with every syllable's time and pitch, the beats
    (seconds) its notes were placed on, to count each line in, and its sections (sections())."""
    notes = sorted((n for n in score["notes"] if n["part"] == "voice"), key=lambda n: n["start"])
    lines, current, left = [], [], 0
    for n in notes:
        left = left or n["word_len"]  # syllables still to come in this word
        left -= 1
        current.append({"text": n["syllable"].replace("*", ""), "start": n["start"], "end": n["start"] + n["dur"], "pitch": n["pitch"],
                        "word_end": left == 0})
        if n["line_end"]:
            lines.append((n["section"], current))
            current = []
    return {
        "title": title,
        "tempo": tempo,
        "duration": score["duration"],
        "sections": sections(score),
        "lines": [{"section": section, "start": line[0]["start"], "end": line[-1]["end"], "syllables": line}
                  for section, line in lines],
        "beats": [round(t, 4) for t, _ in score.get("beats", [])],
    }


def sections(score: dict) -> list[dict]:
    """The guide's sections in order, {"index", "name", "start", "end", "sung"}, and for each sung
    one, which of its kind it is ("nth": verse 1, verse 2..., bridge2 the second bridge), its
    first line as plain words ("label", written()), and the window for recording it alone
    ("window": [from, to], seconds): from the downbeat two bars before its first sung note (a
    pickup's bar line counts: after a turn, the turn's first downbeat), never before the song's
    start, to a bar after its last sung note ends, so the last word's fall isn't cut off, never
    after the song's end."""
    beats = [(float(t), bool(bar)) for t, bar in score.get("beats") or []]
    duration = float(score["duration"])
    spans = score["sections"]
    # each sung note is its section's, by name and time: a pickup reaches back into what comes before, a bar at most
    times = [t for t, _ in beats]
    reach = per_bar(beats) * float(np.median(np.diff(times))) if len(times) > 1 else 2.0
    sung: dict[int, list[dict]] = {}
    for n in sorted((n for n in score["notes"] if n["part"] == "voice"), key=lambda n: n["start"]):
        mine = [i for i, (name, a, b) in enumerate(spans) if name == n["section"] and a - reach <= n["start"] < b]
        if mine:
            sung.setdefault(mine[-1], []).append(n)
    out, seen = [], {}
    for i, (name, a, b) in enumerate(spans):
        entry = {"index": i, "name": name, "start": a, "end": b, "sung": i in sung}
        if i in sung:
            kind = name.rstrip("0123456789") or name  # bridge2 is the second bridge
            seen[kind] = seen.get(kind, 0) + 1
            entry.update(nth=seen[kind], label=first_line(sung[i], score.get("lexicon")),
                         window=window(sung[i], beats, duration))
        out.append(entry)
    return out


def first_line(notes: list[dict], lexicon: dict | None = None) -> str:
    """The first line some sung notes sing, as plain words (written()): no *focus* marks, no
    syllable hyphens."""
    words, left = [], 0
    for n in notes:
        if not left:  # a word's first syllable: the whole word, as written
            words.append(n.get("word") or n["syllable"])
            left = n["word_len"]
        left -= 1
        if n["line_end"]:
            break
    return " ".join(written(w, lexicon) for w in words)


def written(word: str, lexicon: dict | None = None) -> str:
    """A word as it's read. The bank's hyphens split syllables and a compound's real hyphen alike
    ("half-in-vent-ed"), so they're told apart as songbird.phonetics tells them apart to say the
    word: closed up if the dictionary (or the song's lexicon) knows the whole word, or it's a
    regular inflection of one ("in-vent-ed": invented); else kept only between the fewest words
    it knows that cover the syllables (half-invented, ninety-odd, half-asleep)."""
    from songbird import phonetics as ph

    pieces = [p for p in ph.shown(word).replace("*", "").split("-") if p]  # without its say, bass{fish}
    if len(pieces) < 2:
        return "".join(pieces)
    words, own = ph._dictionary(), {ph.clean(k.replace("-", "")) for k in lexicon or {}}
    whole = ph.clean("".join(pieces))
    if whole in words or whole in own or ph._inflected(whole):
        return "".join(pieces)
    best: list[list[tuple[int, int]] | None] = [[]] + [None] * len(pieces)  # the fewest words to cover pieces[:k]
    for end in range(1, len(pieces) + 1):
        for start in range(end):
            chunk = ph.clean("".join(pieces[start:end]))
            if (best[start] is not None and chunk and (chunk in words or chunk in own)
                    and (best[end] is None or len(best[start]) + 1 < len(best[end]))):
                best[end] = best[start] + [(start, end)]
    return "-".join("".join(pieces[a:b]) for a, b in best[-1]) if best[-1] else "".join(pieces)


def window(notes: list[dict], beats: list[tuple[float, bool]], duration: float, bars: int = 2) -> list[float]:
    """Where to start playing to record some sung notes alone, and where to stop (sections())."""
    times, bar = [t for t, _ in beats], per_bar(beats)
    first, last = notes[0]["start"], notes[-1]["start"] + notes[-1]["dur"]
    # the beat the first note is on, or a pickup's beat before it; back two bars less a beat, to a bar line
    k = bisect.bisect_right(times, first + 0.05) - 1 - (bars * bar - 1)
    while k > 0 and not beats[k][1]:
        k -= 1
    start = times[k] if k >= 0 and beats[k][1] else 0.0
    # a bar of the beats around the last note's end
    j = min(max(bisect.bisect_right(times, last) - 1, 0), max(len(times) - 2, 0))
    beat = times[j + 1] - times[j] if len(times) > 1 else 0.5
    return [round(max(start, 0.0), 4), round(min(last + bar * beat, duration), 4)]


def per_bar(beats: list[tuple[float, bool]]) -> int:
    """Beats to a bar, from where the bars begin."""
    downbeats = [k for k, (_, bar) in enumerate(beats) if bar]
    return int(np.median(np.diff(downbeats))) if len(downbeats) > 1 else 4
