"""Our songs sung by Scylla's Band, with our own timing, as training material for the throat (dev only).

    uv run python tools/throat/scylla.py [--out renders/throat/scylla-plan.json] [--voices gwen felix ...]
        [--per-item 2] [--items h-now-its-by-you ...] [--prefix h-] [--after PLAN.json ...] [--seed 0]

Scylla's Band (https://github.com/lowkeytea/scyllasband, Apache-2.0 code and weights, a checkout named by
SCYLLA) is a 24 kHz text-to-speech and singing model with 14 fixed voices and no cloning. Unlike SoulX-Singer
it doesn't need a timbre prompt, and its singing graph takes what to sing frame by frame: the phones (its IPA
symbols), how many 512-sample frames each lasts and the melody. So it can sing our own schedule
(songbird.synth.voice.schedule, with the consonant lengths the throat sings with, throat.DURATIONS): every
phone starts where our program puts it, and the labels are what it was told, not what an aligner heard. No
MFA is needed, and the throat learns envelopes for the very timing it will be asked to sing.

What it is told, per phrase (at most 9.5 s of singing between rests of 0.25 s, with 0.12 s of lead-in and
release, as its own singing.py packs them):
- its phones in the layout of its training: <sil> between words (no frames when they join), a stress mark
  (no frames) before a stressed vowel, a diphthong as its two symbols, an affricate as its two;
- the frames of each, from our schedule's times rounded to the frame (21.3 ms), every sounding symbol at
  least one;
- the melody as its singing.py lays it out, (midi - 60) / 24, the phase through the note and 1 while a
  note sounds, each note running from its syllable's first sound to the next syllable's first (Scylla
  learned notes that begin with their words' consonants; ours put the vowel on the beat).

Each voice sings in its own register: the item moved by octaves so its mean pitch sits in [centre - 3,
centre + 5] of the voice's sung centre (the bundle's voice_midi_center), then a random -2..+2 semitones kept
inside that band.

Writes the plan for tools/throat/scylla_batch.py (run in SCYLLA's venv) and, under renders/throat/corpus/
<singer>/, each segment's label (as soulx_batch.py writes them, for features.py, check.py and judge.py), and
under renders/throat/align/<singer>/ its phones (as phones.py writes them, for check.py and dataset.py):
the singer is "scylla-<voice>" and its source "scyllasband".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import fields
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from corpus import THROAT, items  # noqa: E402
from soulx import ROOT  # noqa: E402

from songbird.score import Note  # noqa: E402
from songbird.synth import throat  # noqa: E402
from songbird.synth.voice import VoiceParams, schedule  # noqa: E402

SCYLLA = Path(os.environ.get("SCYLLA", Path.home() / "Code/scyllasband"))
BUNDLE = SCYLLA / "scyllasband/models/litert"
SR, HOP = 24000, 512
FPS = SR / HOP  # 46.875 frames a second
PAD = 0.12  # lead-in and release around each phrase
PHRASE_REST = 0.25  # a gap this long between phones ends a phrase
MAX_PHRASE = 9.5  # seconds of singing in one phrase (the bundle's graphs hold about 10.5)
SPLIT, LEAD, TAIL, LONGEST = 1.0, 0.3, 0.4, 34.0  # segments as soulx.segments cuts them
BELOW, ABOVE = 3.0, 5.0  # the band around the voice's sung centre its mean pitch is put in (its singing.py)

# songbird's phones as Scylla's symbols (its G2P's own, espeak-style American English), each with the share of
# the phone's time each symbol takes
VOWEL_IPA = {
    "AA": [("ɑ", 1.0), ("ː", 0)], "AE": [("æ", 1.0)], "AH": [("ʌ", 1.0)], "AX": [("ə", 1.0)],
    "AO": [("ɔ", 1.0), ("ː", 0)], "EH": [("ɛ", 1.0)], "IH": [("ɪ", 1.0)], "IY": [("i", 1.0), ("ː", 0)],
    "UH": [("ʊ", 1.0)], "UW": [("u", 1.0), ("ː", 0)],
    "EY": [("e", 0.65), ("ɪ", 0.35)], "AY": [("a", 0.65), ("ɪ", 0.35)], "OW": [("o", 0.65), ("ʊ", 0.35)],
    "AW": [("a", 0.65), ("ʊ", 0.35)], "OY": [("ɔ", 0.65), ("ɪ", 0.35)],
    "AYR": [("a", 0.45), ("ɪ", 0.2), ("ɚ", 0.35)], "AWR": [("a", 0.45), ("ʊ", 0.2), ("ɚ", 0.35)],
    "OYR": [("ɔ", 0.45), ("ɪ", 0.2), ("ɚ", 0.35)],
}
ER_STRESSED, ER_UNSTRESSED = [("ɜ", 1.0), ("ː", 0)], [("ɚ", 1.0)]
CONSONANT_IPA = {
    "B": "b", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h", "K": "k", "L": "l", "M": "m", "N": "n",
    "NG": "ŋ", "P": "p", "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t", "TH": "θ", "V": "v", "W": "w", "Y": "j",
    "Z": "z", "ZH": "ʒ",
}
AFFRICATES = {"CH": [("t", 0.35), ("ʃ", 0.65)], "JH": [("d", 0.35), ("ʒ", 0.65)]}
# How the corpus's labels spell songbird's phones for dataset.py (ARPAbet with a stress digit on vowels; a
# diphthong into r is the diphthong then R, which dataset.ours joins again)
LABEL_SPLIT = {"AYR": ("AY", "R"), "AWR": ("AW", "R"), "OYR": ("OY", "R")}


def symbols(phone: str, role: str, stressed: bool) -> list[tuple[str, float]]:
    if role == "vowel":
        if phone == "ER":
            out = ER_STRESSED if stressed else ER_UNSTRESSED
        elif phone == "AH" and not stressed:
            out = VOWEL_IPA["AX"]
        else:
            out = VOWEL_IPA[phone]
        return ([("ˈ", 0)] if stressed else []) + list(out)
    if phone in AFFRICATES:
        return list(AFFRICATES[phone])
    return [(CONSONANT_IPA[phone], 1.0)]


def label_phones(phone: str, role: str, stressed: bool, t0: float, t1: float, note: int) -> list[dict]:
    """A scheduled phone as phones.py's alignments spell it."""
    if role != "vowel":
        return [dict(phone=phone, start=round(t0, 4), end=round(t1, 4), note=note, role=role)]
    digit = "1" if stressed else "0"
    if phone == "AX":
        return [dict(phone="AH0", start=round(t0, 4), end=round(t1, 4), note=note, role=role)]
    if phone in LABEL_SPLIT:
        v, r = LABEL_SPLIT[phone]
        mid = t0 + 0.65 * (t1 - t0)
        return [dict(phone=v + digit, start=round(t0, 4), end=round(mid, 4), note=note, role=role),
                dict(phone=r, start=round(mid, 4), end=round(t1, 4), note=note, role="coda")]
    return [dict(phone=phone + digit, start=round(t0, 4), end=round(t1, 4), note=note, role=role)]


def centres() -> dict[str, float]:
    manifest = json.loads((BUNDLE / "manifest.json").read_text())
    return {k: float(v) for k, v in manifest["controls"]["delivery_modes"]["singing"]["voice_midi_center"].items()}


def key_for(notes: list[dict], centre: float, rng: np.random.Generator) -> int:
    """Semitones to move the item by: octaves into the voice's band, then up to two semitones either way
    inside it."""
    mean = float(np.mean([n["pitch"] for n in notes]))
    lo, hi = centre - BELOW, centre + ABOVE
    octave = min((-36, -24, -12, 0, 12, 24), key=lambda s: (max(0.0, lo - (mean + s), (mean + s) - hi), -s))
    options = [octave + d for d in range(-2, 3) if lo - 0.5 <= mean + octave + d <= hi + 0.5] or [octave]
    return int(rng.choice(options))


def words_of(notes: list) -> list[int]:
    """The index of each note's word (notes grouped by word_len, as schedule groups them)."""
    out, i, w = [], 0, 0
    while i < len(notes):
        n = max(1, notes[i].word_len)
        out += [w] * min(n, len(notes) - i)
        i += n
        w += 1
    return out


def scheduled(notes: list, lexicon: dict, seed: int) -> list[dict]:
    """Our schedule as rows: phone, role, start, end, note index, stressed, word index."""
    segs = schedule(notes, VoiceParams(), lexicon, throat.DURATIONS, seed=seed)
    stressed = throat.stresses(notes, lexicon)
    word = words_of(notes)
    rows, k = [], -1
    for s in segs:
        if s.role == "breath":
            continue
        note = k + 1 if s.role == "onset" else k
        if s.role == "vowel":
            k += 1
            note = k
        rows.append(dict(phone=s.phone, role=s.role, t0=s.t0, t1=s.t1, note=note, stressed=stressed[note], word=word[note]))
    return rows


def phrases_of(rows: list[dict]) -> list[list[dict]]:
    """Rows cut at gaps of PHRASE_REST, then packed up to MAX_PHRASE seconds; a run longer than that is cut at a
    word boundary near its middle."""
    runs, cur = [], []
    for r in rows:
        if cur and r["t0"] - cur[-1]["t1"] >= PHRASE_REST:
            runs.append(cur)
            cur = []
        cur.append(r)
    if cur:
        runs.append(cur)

    def cut(run):
        if run[-1]["t1"] - run[0]["t0"] <= MAX_PHRASE or len(run) < 2:
            return [run]
        middle = (run[0]["t0"] + run[-1]["t1"]) / 2
        at = [i for i in range(1, len(run)) if run[i]["word"] != run[i - 1]["word"]] or [len(run) // 2]
        i = min(at, key=lambda i: abs(run[i]["t0"] - middle))
        return cut(run[:i]) + cut(run[i:])

    out, cur = [], []
    for run in (p for r in runs for p in cut(r)):
        if cur and run[-1]["t1"] - cur[0]["t0"] > MAX_PHRASE:
            out.append(cur)
            cur = []
        cur += run
    if cur:
        out.append(cur)
    return out


def phrase_input(rows: list[dict], notes: list[dict], t0: float) -> tuple[dict, list[dict]]:
    """One phrase as Scylla's singing graph takes it, and the rows as sung (times on the segment's clock,
    rounded to its frames). t0: where the phrase's audio starts on the segment's clock (lead-in included)."""
    tokens, frames, starts = ["<sil>"], [0], []
    bounds = []  # (token index range, row) to read the rounded times back
    edge = lambda t: int(round((t - t0) * FPS))  # noqa: E731
    cursor = edge(rows[0]["t0"])
    frames[0] = cursor
    for i, r in enumerate(rows):
        if i and r["word"] != rows[i - 1]["word"]:
            gap = max(0, edge(r["t0"]) - cursor)
            tokens.append("<sil>")
            frames.append(gap)
            starts.append(len(tokens))
            cursor += gap
        elif i:  # a gap inside a word (it shouldn't happen): the phone before it takes it
            gap = max(0, edge(r["t0"]) - cursor)
            frames[-1] += gap
            cursor += gap
        syms = symbols(r["phone"], r["role"], r["stressed"])
        total = max(edge(r["t1"]) - cursor, sum(1 for _, w in syms if w))
        first = len(tokens)
        given, acc = 0, 0.0
        sounding = [k for k, (_, w) in enumerate(syms) if w]
        for k, (sym, w) in enumerate(syms):
            if not w:
                tokens.append(sym)
                frames.append(0)
                continue
            acc += w
            n = total - given if k == sounding[-1] else max(1, int(round(acc * total)) - given)
            n = max(1, min(n, total - given - (len(sounding) - 1 - sounding.index(k))))
            tokens.append(sym)
            frames.append(n)
            given += n
        bounds.append((first, len(tokens), r, cursor, cursor + total))
        cursor += total
    release = int(round(PAD * FPS))
    tokens.append("<sil>")
    frames.append(release)
    total = cursor + release
    # the melody: each note from its syllable's first sound to the next syllable's first sound (or its own end)
    melody = []
    by_note: dict[int, list[tuple[int, int]]] = {}
    for _, _, r, a, b in bounds:
        by_note.setdefault(r["note"], []).append((a, b))
    ks = sorted(by_note)
    for j, k in enumerate(ks):
        a = min(x for x, _ in by_note[k])
        b = min(x for x, _ in by_note[ks[j + 1]]) if j + 1 < len(ks) else max(y for _, y in by_note[k])
        melody.append(dict(pitch=int(notes[k]["pitch"]), a=a, b=max(b, a + 1)))
    sung = [dict(r, t0=t0 + a / FPS, t1=t0 + b / FPS) for _, _, r, a, b in bounds]
    return dict(phones=tokens, frames=frames, word_starts=starts, total=int(total), melody=melody), sung


def segment_rows(rows: list[dict]) -> list[list[dict]]:
    """Rows grouped into segments as soulx.segments groups notes: a gap over SPLIT, or a stretch over LONGEST
    seconds at a word's end."""
    out, cur = [], []
    for r in rows:
        if cur and (r["t0"] - cur[-1]["t1"] > SPLIT or (r["t0"] - cur[0]["t0"] > LONGEST and r["word"] != cur[-1]["word"]
                                                          and r["role"] != "coda")):
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out


def plan_item(item: dict, voice: str, shift: int, seed: int) -> list[dict]:
    known = {f.name for f in fields(Note)}
    raw = [dict(n, pitch=n["pitch"] + shift) for n in item["notes"]]
    notes = [Note(**{"part": "voice", **{k: v for k, v in n.items() if k in known}}) for n in raw]
    order = sorted(range(len(notes)), key=lambda i: notes[i].start)
    notes, raw = [notes[i] for i in order], [raw[i] for i in order]
    rows = scheduled(notes, item["lexicon"], seed)
    singer = f"scylla-{voice}"
    segs = []
    for s, group in enumerate(segment_rows(rows)):
        seg_t0 = max(0.0, group[0]["t0"] - LEAD)
        seg_t1 = group[-1]["t1"] + TAIL
        local = [dict(r, t0=r["t0"] - seg_t0, t1=r["t1"] - seg_t0) for r in group]
        phrases, sung = [], []
        for p in phrases_of(local):
            start = p[0]["t0"] - PAD
            inp, done = phrase_input(p, raw, start)
            phrases.append(dict(inp, start=round(start, 5)))
            sung += done
        kept = sorted({r["note"] for r in group})
        index = {k: i for i, k in enumerate(kept)}
        label_notes = []
        for k in kept:
            mine = [r for r in sung if r["note"] == k]
            vowel = next(r for r in mine if r["role"] == "vowel")
            n = raw[k]
            label_notes.append(dict(start=n["start"] - seg_t0, dur=n["dur"], sung_start=round(vowel["t0"], 4),
                                    sung_end=round(max(r["t1"] for r in mine), 4), pitch=int(n["pitch"]),
                                    phones=[r["phone"] for r in mine], type=2, syllable=n.get("syllable"), word=n["word"],
                                    word_len=n["word_len"], line_end=bool(n.get("line_end")), vel=n.get("vel", 0.75)))
        align = []
        for r in sung:
            align += label_phones(r["phone"], r["role"], r["stressed"], r["t0"], r["t1"], index[r["note"]])
        found = []
        for i, k in enumerate(kept):
            v = next(r for r in sung if r["note"] == k and r["role"] == "vowel")
            found.append(dict(found=True, vowel_start=round(v["t0"], 4), vowel_end=round(v["t1"], 4),
                              offset=round(v["t0"] - label_notes[i]["sung_start"], 4), plausible=True))
        name = f"{singer}.{item['id']}.{s:02d}"
        segs.append(dict(index=name, t0=seg_t0, t1=seg_t1, notes=label_notes, phrases=phrases,
                         align=dict(segment=name, singer=singer, lowered=False, phones=align, notes=found)))
    return segs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=THROAT / "scylla-plan.json")
    ap.add_argument("--root", type=Path, default=THROAT, help="where corpus/ and align/ labels go")
    ap.add_argument("--voices", nargs="*", default=None, help="Scylla's voices to use (all 14 by default)")
    ap.add_argument("--per-item", type=int, default=2, help="voices per item (H itself is sung by all)")
    ap.add_argument("--items", nargs="*", default=None, help="only these items (ids such as h-verse-wire)")
    ap.add_argument("--prefix", default=None, help="only items whose ids start with this (h- for H's own)")
    ap.add_argument("--after", type=Path, nargs="*", default=[],
                    help="plans already sung: a voice that sang an item there isn't chosen for it again")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    centre = centres()
    voices = args.voices or sorted(centre)
    pool = items(rng)
    if args.items:
        pool = [it for it in pool if it["id"] in args.items]
    if args.prefix:
        pool = [it for it in pool if it["id"].startswith(args.prefix)]
    sung = {(p["voice"], p["item"]) for plan_path in args.after for p in json.loads(plan_path.read_text())["items"]}
    load = dict.fromkeys(voices, 0.0)
    plan = []
    h = "h-now-its-by-you"
    for it in pool:
        length = it["notes"][-1]["start"] + it["notes"][-1]["dur"] - it["notes"][0]["start"]
        fresh = [v for v in voices if (v, it["id"]) not in sung]  # a second plan's voices are new to the item
        who = fresh if it["id"] == h else sorted(fresh, key=lambda v: (load[v], rng.random()))[: args.per_item]
        for voice in who:
            shift = key_for(it["notes"], centre[voice], rng)
            seed = int(rng.integers(1 << 30))
            try:
                segs = plan_item(it, voice, shift, seed)
            except (KeyError, ValueError, StopIteration) as e:
                print(f"  skipped {voice}.{it['id']}: {e!r}")
                continue
            for seg in segs:
                singer = f"scylla-{voice}"
                for kind, body in (("corpus", dict(index=seg["index"], t0=seg["t0"], t1=seg["t1"], notes=seg["notes"],
                                                    singer=singer, source="scyllasband", voice=voice, shift=shift)),
                                   ("align", seg["align"])):
                    dest = args.root / kind / singer / f"{seg['index']}.json"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(json.dumps(body, indent=1))
            plan.append(dict(id=f"scylla-{voice}.{it['id']}", voice=voice, item=it["id"], kind=it["kind"], shift=shift,
                             seed=seed, segments=[dict(index=s["index"], t0=s["t0"], t1=s["t1"], phrases=s["phrases"])
                                                  for s in segs]))
            load[voice] += length
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dict(items=plan), indent=None))
    total = sum(s["t1"] - s["t0"] for p in plan for s in p["segments"])
    print(f"{len(plan)} items, {sum(len(p['segments']) for p in plan)} segments, {total / 60:.1f} min -> {args.out}")
    for v in voices:
        print(f"  {v:9} {load[v] / 60:5.1f} min")


if __name__ == "__main__":
    main()
