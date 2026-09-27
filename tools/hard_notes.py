"""Where singers depart from the tune, and what they sing instead, from everyone's measured takes (dev-only).

    uv run python tools/hard_notes.py                  # the notes singers change, most agreed on first
    uv run python tools/hard_notes.py --line b4        # one line, note by note, singer by singer

Every take ticked to count, once measured (tools/phrasing.py; `invite.py sync --measure` measures
each as it arrives), says for each note of the tune how far the singer's pitch sat from the written
note, in the key and octave they sang in ("off", cents). Here each singer's notes at each place in
the tune become one number (their median), so a singer counts once however many takes they sent,
and a note is a candidate for changing when two or more singers independently sing the same other
note of the scale there, 70 cents or more away (docs/MAKING-IT-THEIR-OWN.md: a slip happens once; a
change that several people make is the folk process at work).

For each candidate it also says which other line of the tune has that note at that place, when
the two lines are otherwise alike: on 2026-09-26 most of what four singers changed was a line that
starts like a more familiar one and then turns (the bridge's lines against the verse's and the
refrain's), where they sang the familiar line. Measurement is noisiest on short, unstressed notes
and pickups: trust agreement, not any one number.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT))
import takes as K  # noqa: E402  (tools/takes.py)

from songbird.theory import degree_semitones  # noqa: E402

H = ROOT / "songs" / "h-now-its-by-you.json"
MEASURED = ROOT / "renders" / "measured"  # where tools/phrasing.py keeps each take's measurement
AWAY = 70.0  # cents from the written note before a singer's note counts as another note
NAMES = ["do", "re", "mi", "fa", "so", "la", "ti"]


@dataclass
class Change:
    """A note of the tune singers sing as another: where, what's written, what they sing, who."""
    phrase: str
    index: int
    written: int  # the tune's degree (1 do ... 7 ti; 0 and below, the octave under: -2 is low so)
    sung: int  # the degree they sing instead
    agree: dict[str, float]  # singer -> their median departure, cents, for those who sing it
    others: dict[str, float]  # everyone else who sang this note
    like: list[str]  # other lines, otherwise alike, that have this degree here
    category: str = "shift"  # what kind of change: "familiar" (as a line like it has it), "passing" (a step between
    # its neighbours), "pickup" (a phrase's first note), or a plain "shift" (Gemini's reading of the first results)


def name(degree: int) -> str:
    base = NAMES[(degree - 1) % 7]
    return base + ("," * ((7 - degree) // 7) if degree < 1 else "'" * ((degree - 1) // 7))


def measured(take: K.Take) -> Path:
    """Where tools/phrasing.py keeps a take's measurement (measured())."""
    rel = take.path.relative_to(ROOT).as_posix() if take.path.is_relative_to(ROOT) else take.path.as_posix().lstrip("/")
    return MEASURED / (rel.replace("/", "__").removesuffix(".wav") + ".json")


def sightings(song: str, genome_path: Path, genome) -> dict[tuple[str, int], dict[str, list[float]]]:
    """Every measured note of every take ticked to count: (phrase, index) -> singer -> cents off the
    tune as it is now. A take's "off" is from the note of the guide it sang to; where the tune has
    changed that note since (2026-09-27: v2, r2, b2, b3, b4), the difference is added, so a singer
    who sang what the tune now says counts as on it."""
    import phrasing as T  # tools/phrasing.py: each take's guide score, and the tune as written now

    seen: dict[tuple[str, int], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    now, tonic = T.written(genome), T.choose_params(genome).tonic
    for t in K.takes(song):
        f = measured(t)
        if not t.use or not f.exists():
            continue
        d = json.loads(f.read_text())
        sung_to = T.guide(genome_path, genome, d["stamp"]["guide"]).notes
        shift = T.transposed(genome_path, d["stamp"]["guide"])
        for n, note in zip(d["notes"], sung_to):
            if n.get("gesture") is not None and n.get("off") is not None:
                key = (n["phrase"], n["index"])
                then = round(note.pitch) - tonic - shift  # the guide's note, semitones above the tonic
                moved = 100.0 * (then - now[key]) if key in now else 0.0
                seen[key][t.who].append(float(n["off"]) + moved)
    return seen


def nearest(genome, written: int, cents: float, mode: str) -> int:
    """The degree of the scale nearest where a note was sung, cents from the written one."""
    at = degree_semitones(written, mode) + cents / 100.0
    return min(range(written - 7, written + 8), key=lambda d: (abs(degree_semitones(d, mode) - at), abs(d - written)))


def alike(genome) -> dict[str, list[str]]:
    """For each line, the others of its length that share most of its notes, place for place."""
    tunes = {pid: [n.degree for n in p.sung] for pid, p in genome.phrases.items() if p.sung}
    out = {}
    for a, ta in tunes.items():
        out[a] = [b for b, tb in tunes.items()
                  if b != a and len(tb) == len(ta) and sum(x == y for x, y in zip(ta, tb)) >= 0.6 * len(ta)]
    return out


def changes(genome, seen: dict, mode: str = "ionian", least: int = 2) -> list[Change]:
    """The notes that `least` or more singers independently sing as another note, most agreed first: of
    those who sing a note AWAY or more from the tune, the ones who go the same way make a group, and the
    degree nearest their median is what they sing; each of them must be within a semitone and a half of
    it (two people can sing the same wrong note a little apart)."""
    tunes = {pid: [n.degree for n in p.sung] for pid, p in genome.phrases.items() if p.sung}
    similar = alike(genome)
    found = []
    for (pid, k), singers in seen.items():
        if pid not in tunes or k >= len(tunes[pid]):
            continue
        written = tunes[pid][k]
        each = {who: float(np.median(v)) for who, v in singers.items() if v}
        for sign in (1, -1):
            group = {w: c for w, c in each.items() if c * sign >= AWAY}
            if len(group) < least:
                continue
            d = nearest(genome, written, float(np.median(list(group.values()))), mode)
            if d == written:
                continue
            target = (degree_semitones(d, mode) - degree_semitones(written, mode)) * 100
            agree = {w: c for w, c in group.items() if abs(c - target) <= 150}
            if len(agree) >= least:
                like = [b for b in similar.get(pid, []) if tunes[b][k] == d]
                others = {w: c for w, c in each.items() if w not in agree}
                found.append(Change(pid, k, written, d, agree, others, like, category(tunes[pid], k, d, like)))
    return sorted(found, key=lambda c: (-len(c.agree) / (len(c.agree) + len(c.others)), -len(c.agree),
                                        -float(np.mean([abs(x) for x in c.agree.values()]))))


def category(tune: list[int], k: int, sung: int, like: list[str]) -> str:
    """What kind of change singers made: a familiar line's note, a passing tone between the note's neighbours
    (stepwise where the tune leapt), a pickup lifted or dropped, or a plain shift."""
    if like:
        return "familiar"
    if k == 0:
        return "pickup"
    if 0 < k < len(tune) - 1 and (tune[k - 1] > sung > tune[k + 1] or tune[k - 1] < sung < tune[k + 1]):
        return "passing"
    return "shift"


def words(genome) -> dict[tuple[str, int], str]:
    """A syllable for each note of the tune: the song's own words, where each line is first sung."""
    from songbird.realize import choose_params, realize

    voice = sorted(realize(genome, choose_params(genome)).part("voice"), key=lambda n: n.start)
    out, k = {}, 0
    for i, n in enumerate(voice):
        out.setdefault((n.phrase, k), (n.syllable or "").replace("*", ""))
        k = 0 if n.line_end else k + 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--song", default=str(H))
    ap.add_argument("--line", help="one line of the tune (a phrase id: v1, r2, b4...), singer by singer")
    ap.add_argument("--least", type=int, help="singers who must agree (default half of them, and at least 2)")
    ap.add_argument("--json", action="store_true", help="the changes as JSON (phrase, index, word, written, sung, category, who)")
    args = ap.parse_args()

    from songbird import genome as G

    genome = G.load(args.song)
    song = Path(args.song).stem
    seen = sightings(song, Path(args.song).resolve(), genome)
    said = words(genome)
    singers = sorted({w for s in seen.values() for w in s})
    print(f"{len(singers)} singers: {', '.join(singers)}\n")
    if args.line:
        for k, note in enumerate(genome.phrases[args.line].sung):
            cells = "  ".join(f"{w} {np.median(v) / 100:+.1f}" for w, v in sorted(seen.get((args.line, k), {}).items()))
            print(f"  #{k:<2d} {said.get((args.line, k), ''):10s} {name(note.degree):4s} {cells}")
        return
    found = changes(genome, seen, least=args.least or max(2, (len(singers) + 1) // 2))
    if args.json:
        print(json.dumps([{"phrase": c.phrase, "index": c.index, "word": said.get((c.phrase, c.index), ""),
                           "written": name(c.written), "sung": name(c.sung), "category": c.category,
                           "agree": c.agree, "others": c.others, "like": c.like} for c in found], indent=1))
        return
    if not found:
        print("No note that two singers sing as the same other one.")
    for c in found:
        agree = ", ".join(f"{w} {x / 100:+.1f}" for w, x in c.agree.items())
        others = ", ".join(f"{w} {x / 100:+.1f}" for w, x in c.others.items())
        like = f"  (as in {', '.join(c.like)})" if c.like else ""
        kind = f" [{c.category}]" if c.category != "shift" else ""
        print(f"{c.phrase} #{c.index} \"{said.get((c.phrase, c.index), '')}\": {name(c.written)} -> {name(c.sung)}{kind}: "
              f"{len(c.agree)} of {len(c.agree) + len(c.others)} singers ({agree}{'; ' + others if others else ''}){like}")


if __name__ == "__main__":
    main()
