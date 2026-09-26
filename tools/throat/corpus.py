"""The learned throat's training corpus: our own songs sung by SoulX-Singer in synthetic timbres (dev only).

    uv run python tools/throat/corpus.py [--out renders/throat/plan.json] [--seed 0]

Writes a plan: for each item (a whole song from songs/, a verse from H's bank, a refrain couplet,
a bridge), which synthetic singer sings it, in which key and at what tempo, as SoulX-Singer
metadata segments. tools/throat/soulx_batch.py renders the plan in SoulX-Singer's own venv.

The singers are Eleven Music's synthetic voices (renders/reference/music/eleven-*/, a cappella
takes of H), used as ten-second timbre prompts: nobody real, and none of it ever ships. What ships
is what our own small model learns from the renders about how sung English sounds.
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

MUSIC = ROOT / "renders/reference/music"
GUIDE = ROOT / "renders/guide/h-now-its-by-you.guide.score.json"
H = ROOT / "songs/h-now-its-by-you.json"
THROAT = ROOT / "renders/throat"

# name: (Eleven take directory, keys to sing in, semitones from the written tune)
SINGERS = {
    "bright": ("eleven-clear-bright-female", (-3, 0, 3)),
    "husky": ("eleven-husky-mezzo-female", (-4, 0, 2)),
    "alto": ("eleven-low-warm-alto", (-5, -2, 0)),
    "breathy": ("eleven-soft-breathy-young", (-2, 0, 4)),
    "tenor": ("eleven-tender-tenor-male", (-7, -4, 0)),
    "baritone": ("eleven-warm-baritone-male", (-15, -12, -9)),
    "gravelly": ("eleven-gravelly-older-male", (-14, -12, -8)),
}
PROMPT_AT, PROMPT_LEN = 30.45, 10.10  # the first refrain on the guide: "Who made this song? ... and then it goes."


def voice_notes(score) -> list[dict]:
    return [dict(start=n.start, dur=n.dur, pitch=n.pitch, syllable=n.syllable, word=n.word, word_len=n.word_len,
                 line_end=n.line_end, vel=n.vel) for n in score.part("voice")]


def prompt(name: str, take_dir: str) -> dict:
    """A singer's ten-second prompt: the clip, cut from their first take, and its metadata from the guide score."""
    take = MUSIC / take_dir / "h-now-its-by-you-take1.wav"
    sidecar = json.loads(take.with_suffix(".json").read_text())
    window = next(r for r in sidecar["requests"]
                  if r["composition_plan"]["chunks"][0]["conditioning_ref"]["range"]["start_ms"] <= PROMPT_AT * 1000
                  < r["composition_plan"]["chunks"][0]["conditioning_ref"]["range"]["end_ms"])
    y, sr = sf.read(str(take), dtype="float32")
    y = y if y.ndim == 1 else y.mean(axis=1)
    clip = y[int(PROMPT_AT * sr): int((PROMPT_AT + PROMPT_LEN) * sr)]
    out = THROAT / "prompts" / f"{name}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), clip, sr, subtype="PCM_16")
    score = json.loads(GUIDE.read_text())
    notes = [dict(n, start=n["start"] - PROMPT_AT) for n in score["notes"]
             if n["part"] == "voice" and PROMPT_AT - 0.05 <= n["start"] < PROMPT_AT + PROMPT_LEN - 0.1]
    meta = segment(notes, G.load(H).lexicon, 0.0, PROMPT_LEN, breath=0.0, index=f"prompt_{name}", shift=window["key"])
    meta["wav"] = str(out)
    return {"take": str(take), "key": window["key"], "meta": meta}


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
    ap.add_argument("--coverage", type=Path, default=None,
                    help="instead: a JSON list of written lines ({'text': ...}) to sing to our phrases, one singer each")
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    singers = {name: prompt(name, take_dir) for name, (take_dir, _) in SINGERS.items()}
    names = list(SINGERS)
    plan = []
    load = dict.fromkeys(names, 0.0)  # seconds assigned so far, to keep the singers even
    if args.coverage:
        args.per_item = 1
    for it in (coverage(args.coverage, rng) if args.coverage else items(rng)):
        length = it["notes"][-1]["start"] + it["notes"][-1]["dur"] - it["notes"][0]["start"]
        if it["id"] == H.stem:
            who = names
        else:  # the least loaded singers, ties broken at random
            order = sorted(names, key=lambda n: (load[n], rng.random()))
            who = order[: args.per_item]
        for name in who:
            shift = int(rng.choice(SINGERS[name][1]))
            segs = segments(it["notes"], it["lexicon"], f"{name}.{it['id']}", shift=shift)
            plan.append(dict(id=f"{name}.{it['id']}", singer=name, item=it["id"], kind=it["kind"], shift=shift,
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
