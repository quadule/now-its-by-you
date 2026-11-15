"""The learned throat's training corpus: our own songs sung by SoulX-Singer in synthetic timbres (dev only).

    uv run python tools/throat/corpus.py [--out renders/throat/plan.json] [--seed 0]

Writes a plan: for each item (a whole song from songs/, a verse from H's bank, a refrain couplet,
a bridge), which synthetic singer sings it, in which key and at what tempo, as SoulX-Singer
metadata segments. tools/throat/soulx_batch.py renders the plan in SoulX-Singer's own venv.

The singers are the house singers: our own formant singer, sung with ten different VoiceParams, gives
SoulX-Singer a ten-second timbre prompt each, and SoulX sings our scores naturally in that timbre.
Nobody real is in it, and none of it ships. What ships is what our own small model learns from the
renders about how sung English sounds.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from soulx import ROOT, segment, segments  # noqa: E402

from songbird import bank as B, genome as G  # noqa: E402
from songbird.realize import choose_params, realize  # noqa: E402

GUIDE = ROOT / "renders/guide/h-now-its-by-you.guide.score.json"
H = ROOT / "songs/h-now-its-by-you.json"
THROAT = ROOT / "renders/throat"

# Every singer the corpus can use, with where its ten-second timbre prompt comes from, so a whole
# source can be left out and the throat retrained without it (dataset.py --without SOURCE):
#   formant       our own formant singer, sung with the given VoiceParams: a timbre made by this program
# keys: semitones from the written tune the singer sings in (low voices an octave down).
SINGERS = {
    # house singers: our formant singer as the timbre, SoulX's natural singing as the delivery
    "house-alto": dict(source="formant", voice=dict(), shift=0, keys=(-3, 0, 2)),
    "house-bright": dict(source="formant", voice=dict(tract=1.2, rd=0.6, tilt=0.3), shift=0, keys=(-1, 0, 3)),
    "house-breathy": dict(source="formant", voice=dict(tract=1.16, rd=1.2, breath=0.12), shift=0, keys=(-4, -2, 0)),
    "house-tenor": dict(source="formant", voice=dict(tract=1.04, rd=0.8), shift=-7, keys=(-9, -7, -5)),
    "house-baritone": dict(source="formant", voice=dict(tract=0.98, rd=0.9, tilt=0.5), shift=-12, keys=(-14, -12, -9)),
    "house-bass": dict(source="formant", voice=dict(tract=0.93, rd=0.7, tilt=0.45), shift=-12, keys=(-15, -13, -11)),
    "house-mezzo": dict(source="formant", voice=dict(tract=1.08, rd=0.75, tilt=0.35), shift=0, keys=(-5, -3, 0)),
    "house-low-alto": dict(source="formant", voice=dict(tract=1.1, rd=0.95, breath=0.08), shift=-5, keys=(-7, -5, -3)),
    "house-rough": dict(source="formant", voice=dict(tract=0.97, rd=0.6, tilt=0.25), shift=-12, keys=(-13, -11, -9)),
    "house-soft-tenor": dict(source="formant", voice=dict(tract=1.02, rd=1.1, breath=0.1), shift=-7, keys=(-9, -7, -4)),
}
PROMPT_AT, PROMPT_LEN = 30.45, 10.10  # the first refrain on the guide: "Who made this song? ... and then it goes."


def voice_notes(score) -> list[dict]:
    return [dict(start=n.start, dur=n.dur, pitch=n.pitch, syllable=n.syllable, word=n.word, word_len=n.word_len,
                 line_end=n.line_end, vel=n.vel) for n in score.part("voice")]


def prompt(name: str) -> dict:
    """A singer's ten-second prompt: the clip (sung here by our formant singer) and its metadata from the
    guide score."""
    spec = SINGERS[name]
    score = json.loads(GUIDE.read_text())
    out = THROAT / "prompts" / f"{name}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    # our formant singer sings the guide's own notes, in the singer's register
    from dataclasses import fields as dfields

    from songbird.score import Note
    from songbird.synth.voice import VoiceParams, sing as formant_sing

    key = spec["shift"]
    known = {f.name for f in dfields(Note)}
    notes = [Note(**{k: v for k, v in n.items() if k in known and k != "gesture"})
             for n in score["notes"] if n["part"] == "voice"]
    sr = 44100
    y = formant_sing(notes, sr, replace(VoiceParams(engine="formant"), shift=key, **spec["voice"]), seed=1,
                     lexicon=G.load(H).lexicon).astype(np.float32)
    y = 0.5 * y / max(float(np.max(np.abs(y))), 1e-9)
    clip = y[int(PROMPT_AT * sr): int((PROMPT_AT + PROMPT_LEN) * sr)]
    sf.write(str(out), clip, sr, subtype="PCM_16")
    notes = [dict(n, start=n["start"] - PROMPT_AT) for n in score["notes"]
             if n["part"] == "voice" and PROMPT_AT - 0.05 <= n["start"] < PROMPT_AT + PROMPT_LEN - 0.1]
    meta = segment(notes, G.load(H).lexicon, 0.0, PROMPT_LEN, breath=0.0, index=f"prompt_{name}", shift=key)
    meta["wav"] = str(out)
    return {"source": spec["source"], "take": str(spec.get("take", "")), "voice": spec.get("voice"), "key": key, "meta": meta}


def sung(genome, form, *, tempo_scale: float, verses=None, fixed=None) -> list[dict]:
    """The voice notes of the genome sung in this form (verses and fixed blocks as given)."""
    params = choose_params(genome)
    params = replace(params, form=tuple(form), tempo=round(params.tempo * tempo_scale), choir=0)
    if fixed:
        genome = replace(genome, fixed={**genome.fixed, **fixed})
    return voice_notes(realize(genome, params, verses=verses))


def items(rng: np.random.Generator) -> list[dict]:
    """Everything to sing, before choosing singers: (id, kind, notes, lexicon)."""
    out = []
    tempo = lambda: float(rng.uniform(0.9, 1.1))  # noqa: E731
    for path in sorted((ROOT / "songs").glob("*.json")):
        g = G.load(path)
        form = g.seed_params["form"]
        out.append(dict(id=path.stem, kind="song", notes=sung(g, form, tempo_scale=tempo()), lexicon=g.lexicon))
    h = G.load(H)
    bank = h.source["bank"]
    pick = lambda lines, slots: list(B.expansions(lines, slots))[int(rng.integers(B.ways(lines, slots)))]  # noqa: E731
    for v in bank["verses"]:
        lines = pick(v["lines"], v.get("slots", {}))
        out.append(dict(id=f"h-verse-{v['id']}", kind="verse", lexicon=h.lexicon,
                        notes=sung(h, ["verse"], tempo_scale=tempo(), verses=[lines])))
    head, head_slots = bank["refrain"]["lines"], bank["refrain"].get("slots", {})
    for c in bank["refrain"]["couplets"]:
        lines = pick(head + c["lines"], {**head_slots, **c.get("slots", {})})
        out.append(dict(id=f"h-refrain-{c['id']}", kind="refrain", lexicon=h.lexicon,
                        notes=sung(h, ["refrain"], tempo_scale=tempo(), fixed={"refrain": tuple(lines)})))
    for b in bank["bridges"]:
        lines = pick(b["lines"], b.get("slots", {}))
        out.append(dict(id=f"h-bridge-{b['id']}", kind="bridge", lexicon=h.lexicon,
                        notes=sung(h, ["bridge"], tempo_scale=tempo(), fixed={"bridge": tuple(lines)})))
    return out


def hyphenate(word: str, n: int) -> str:
    """A word written with n syllables, as the genome's lyrics are (the split points only label notes)."""
    if n <= 1:
        return word
    step = len(word) / n
    cuts = [round(step * k) for k in range(1, n)]
    return "-".join(word[a:b] for a, b in zip([0] + cuts, cuts + [len(word)]))


def syllabified(text: str) -> str | None:
    """A plain line in the genome's notation (hyphens between syllables), or None if a word is unknown."""
    from songbird import phonetics as P

    out = []
    for word in text.split():
        readings = P.pronunciations(word)
        if not readings:
            return None
        out.append(hyphenate(word, P._vowel_count(readings[0])))
    return " ".join(out)


def coverage(lines_path: Path, rng: np.random.Generator) -> list[dict]:
    """Lines written for the sounds our songs lack, sung to our songs' own phrases: each group of
    lines takes the place of a section whose phrases have the same numbers of notes."""
    pool: dict[int, list[str]] = {}
    for item in json.loads(lines_path.read_text()):
        line = syllabified(item["text"])
        if line:
            pool.setdefault(len(G.syllables(line)), []).append(line)
    for lines in pool.values():
        rng.shuffle(lines)
    sections = []
    for path in sorted((ROOT / "songs").glob("*.json")):
        g = G.load(path)
        for name, sec in g.sections.items():
            if sec.lyrics:
                sections.append((path, g, name, sec, [len(g.phrases[p].sung) for p in sec.phrases]))
    out, k = [], 0
    stalled = 0
    while stalled < len(sections):
        path, g, name, sec, pattern = sections[int(rng.integers(len(sections)))]
        if any(len(pool.get(n, [])) < pattern.count(n) for n in set(pattern)):
            stalled += 1
            continue
        stalled = 0
        lines = [pool[n].pop() for n in pattern]
        tempo = float(rng.uniform(0.9, 1.1))
        if sec.lyrics == "verse":
            notes = sung(g, [name], tempo_scale=tempo, verses=[lines])
        else:
            notes = sung(g, [name], tempo_scale=tempo, fixed={sec.lyrics: tuple(lines)})
        out.append(dict(id=f"cover-{k:03d}-{path.stem[:1]}-{name}", kind="cover", notes=notes, lexicon=g.lexicon))
        k += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=THROAT / "plan.json")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--per-item", type=int, default=2, help="singers per item (H itself is sung by all)")
    ap.add_argument("--singers", nargs="*", default=None, help="plan only for these singers")
    ap.add_argument("--items", nargs="*", default=None, help="only these items (ids such as h-verse-wire)")
    ap.add_argument("--budget", type=float, default=None,
                    help="with --singers: minutes each, drawn from every item (H first) instead of the usual split")
    ap.add_argument("--coverage", type=Path, default=None,
                    help="instead: a JSON list of written lines ({'text': ...}) to sing to our phrases, one singer each")
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    names = args.singers or list(SINGERS)
    singers = {name: prompt(name) for name in names}
    plan = []
    load = dict.fromkeys(names, 0.0)  # seconds assigned so far, to keep the singers even
    if args.coverage:
        args.per_item = 1
    pool = coverage(args.coverage, rng) if args.coverage else items(rng)
    if args.items:
        pool = [it for it in pool if it["id"] in args.items]
    if args.budget:  # every item is a candidate; H first, the rest in random order, until each singer has enough
        pool = sorted(pool, key=lambda it: (it["id"] != H.stem, rng.random()))
        args.per_item = 1
    for it in pool:
        length = it["notes"][-1]["start"] + it["notes"][-1]["dur"] - it["notes"][0]["start"]
        if args.budget and min(load.values()) >= args.budget * 60:
            break
        if args.budget and it["id"] != H.stem:
            who = [n for n in sorted(names, key=lambda n: (load[n], rng.random())) if load[n] < args.budget * 60][:1]
        elif it["id"] == H.stem:
            who = names
        else:  # the least loaded singers, ties broken at random
            order = sorted(names, key=lambda n: (load[n], rng.random()))
            who = order[: args.per_item]
        for name in who:
            shift = int(rng.choice(SINGERS[name]["keys"]))
            segs = segments(it["notes"], it["lexicon"], f"{name}.{it['id']}", shift=shift)
            plan.append(dict(id=f"{name}.{it['id']}", singer=name, source=SINGERS[name]["source"], item=it["id"],
                             kind=it["kind"], shift=shift,
                             seed=int(rng.integers(1 << 30)), segments=segs))
            load[name] += length
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"singers": singers, "items": plan}, indent=1))
    total = sum(s["t1"] - s["t0"] for p in plan for s in p["segments"])
    print(f"{len(plan)} items, {sum(len(p['segments']) for p in plan)} segments, {total / 60:.1f} min -> {args.out}")
    for name in names:
        mine = [p for p in plan if p["singer"] == name]
        secs = sum(s["t1"] - s["t0"] for p in mine for s in p["segments"])
        print(f"  {name:9} {len(mine):3} items {secs / 60:5.1f} min  prompt key {singers[name]['key']:+d}")


if __name__ == "__main__":
    main()
