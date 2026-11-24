"""timeline.json and score.json (tools/promo/video/README.md, "Data contract"), from the stage edition as a render
lays it out (common.laid()): its score, the stage plan's takes, twins, layers and levels, and the song's clock.

    uv run python tools/promo/video/prep/timeline.py"""
from __future__ import annotations

import re

import numpy as np

import common
from common import r

PLAYERS = ("lute", "guitar", "harp", "bass", "fiddle", "whistle", "drum", "drone")
DEGREES = {0: "do", 2: "re", 4: "mi", 5: "fa", 7: "so", 9: "la", 11: "ti"}
PICKUP = 2.5  # s a note may come before its section's start and still be that section's (a pickup, one bar)


def kind_of(part: str, layers: set) -> str:
    if part == "voice":
        return "voice"
    if part.startswith("choir"):
        return "choir"
    if part.endswith(("~", "#")):
        return "twin"
    if part in layers:
        return "layer"
    return "player"


def sec_of(spans: list[dict], name: str, t: float) -> str:
    """A note's section id: the section of its own kind that holds it, or the next one of that kind within a bar
    (a pickup), else the one it falls in."""
    for s in spans:
        if s["kind"] == name and s["t0"] - PICKUP <= t < s["t1"]:
            return s["id"]
    return common.section_at(spans, t)


def clean(s: str) -> str:
    return re.sub(r"\{[^{}]*\}", "", s).replace("*", "")


def heard_lead(score):
    """The lead as heard: in each span of the stage plan, the notes of the take sung there (stage.spliced joins
    the takes' audio at the same times). [(note, human)]."""
    st = score.stage
    plan = st["plan"]
    outs = []
    for k, (t, h) in enumerate(plan):
        a = t if k else -1e9
        b = plan[k + 1][0] if k + 1 < len(plan) else 1e9
        outs += [(n, h) for n in st["takes"][h]["notes"] if a <= n.start < b]
    return sorted(outs, key=lambda x: x[0].start)


def gains(score):
    """Each staged part's level as (times, linear gains), stage.curve()'s points."""
    return {name: (np.array(ts), np.array(gs)) for name, (ts, gs) in (score.stage.get("levels") or {}).items()}


def all_parts(score) -> dict:
    """Every stem's notes, by the stem's name (synth.stem_jobs's order): the score's players and singers, the
    layered parts (with their copies: stage.copied_all), and each twin playing its player's notes."""
    from songbird import stage

    st = score.stage
    parts = {}
    for n in score.notes:
        parts.setdefault(n.part, []).append(n)
    parts["voice"] = [n for n, _ in heard_lead(score)]
    layered = {}
    for layer in st.get("layers") or []:
        for name in layer["parts"]:
            layered[name] = list(stage.copied_all(layer["score"], name, layer["copies"]).part(name))
    parts.update(layered)
    for twin, (player, *_) in (st.get("twins") or {}).items():
        parts[twin] = list(layered.get(player) or score.part(player))
    return parts, set(layered)


def stem_order(score, params) -> list[str]:
    from songbird import synth

    jobs, _ = synth.stem_jobs(score, seed=params.seed)
    return [name for name, _ in jobs]


def level_at(curve, a: float, b: float) -> float:
    """The most a part's level reaches over a note (a to b), linear gain; 1 where the part has no curve."""
    if curve is None:
        return 1.0
    ts, gs = curve
    inside = gs[(ts > a) & (ts < b)]
    return float(max(np.interp(a, ts, gs), np.interp(b, ts, gs), *(inside if len(inside) else [0.0])))


def gesture(g) -> dict | None:
    if g is None:
        return None
    return {k: r(getattr(g, k), 4) for k in ("early", "hold", "level", "swell", "scoop", "bend", "fall", "tune",
                                            "vibrato")}


def lines_of(lead, spans, stage_mod):
    """The heard lead's lines: words and syllables with their times and pitches, the line's human amount."""
    lines, cur = [], []
    for n, h in lead:
        cur.append((n, h))
        if n.line_end:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    outs, count = [], {}
    for ln in lines:
        start = ln[0][0].start - stage_mod.SPLICE  # stage.line_starts: where the line (and its take) begins
        sid = sec_of(spans, ln[0][0].section, ln[0][0].start)
        i = count[sid] = count.get(sid, -1) + 1
        words, k = [], 0
        while k < len(ln):
            n = ln[k][0]
            group = [m for m, _ in ln[k: k + max(1, int(n.word_len or 1))]]
            focus = "*" in (n.word or "")
            words.append({"text": clean(n.word or n.syllable).replace("-", ""), "t0": r(group[0].start),
                          "t1": r(group[-1].start + group[-1].dur),
                          "syllables": [{"text": clean(m.syllable), "t0": r(m.start), "t1": r(m.start + m.dur),
                                         "pitch": int(m.pitch), "focus": focus} for m in group]})
            k += len(group)
        outs.append({"section": sid, "i": i, "t0": r(start), "t1": r(ln[-1][0].start + ln[-1][0].dur),
                     "text": " ".join(w["text"] for w in words), "human": float(ln[0][1]), "words": words})
    return outs


def main() -> None:
    from songbird import realize, stage

    genome, params, score = common.laid()
    spans = common.section_spans(score.sections)
    tonic = int(score.band.get("tonic", 59))

    beats = realize.timeline(genome, params).beats()
    lead = heard_lead(score)
    lines = lines_of(lead, spans, stage)
    human = [[0.0, lines[0]["human"]]]
    for ln in lines:
        if ln["human"] != human[-1][1]:
            human.append([ln["t0"], ln["human"]])

    parts, layered = all_parts(score)
    order = stem_order(score, params)
    assert set(order) == set(parts), (set(order) ^ set(parts))
    curves = gains(score)

    entries = []
    for name in order:
        first = next((n for n in sorted(parts[name], key=lambda n: n.start)
                      if level_at(curves.get(name), n.start, n.start + n.dur) > 0), None)
        if first is not None:
            entries.append({"part": name, "t": r(first.start), "kind": kind_of(name, layered)})
    entries.sort(key=lambda e: e["t"])

    levels = {name: [[r(t), None if g <= 0 else r(20 * np.log10(g), 2)] for t, g in zip(ts, gs)]
              for name, (ts, gs) in curves.items()}

    daisy = []
    for n in score.part("whistle"):
        if sec_of(spans, n.section, n.start) == "bridge":
            daisy.append({"t": r(n.start), "dur": r(n.dur), "pitch": int(n.pitch),
                          "degree": DEGREES.get(int(n.pitch - tonic) % 12, str(int(n.pitch - tonic) % 12))})

    timeline = {"duration": common.DURATION, "fps": common.FPS, "frames": int(np.ceil(common.DURATION * common.FPS)),
                "tempo": float(params.tempo), "bar": r(60 / params.tempo * 4), "tonic": tonic, "key": ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][tonic % 12] + " major",
                "sections": spans,
                "bars": [r(t) for t, bar in beats if bar], "beats": [r(t) for t, _ in beats],
                "lines": lines, "human": human, "entries": entries, "levels": levels, "daisy": daisy,
                "stems": order}
    common.write_json("timeline.json", timeline)

    heard_h = {id(n): h for n, h in lead}
    out = {}
    for name in order:
        curve = curves.get(name)
        rows = []
        for n in sorted(parts[name], key=lambda n: n.start):
            row = {"t": r(n.start), "d": r(n.dur), "p": r(n.pitch, 2), "v": r(n.vel, 3),
                   "syl": clean(n.syllable) if n.syllable else None, "word": n.word,
                   "sec": sec_of(spans, n.section, n.start), "phrase": n.phrase, "art": n.art,
                   "g": gesture(n.gesture), "a": r(level_at(curve, n.start, n.start + n.dur), 3)}
            if id(n) in heard_h:
                row["h"] = heard_h[id(n)]
            rows.append(row)
        out[name] = rows
    common.write_json("score.json", {"stems": order, "parts": out})
    common.say(f"timeline.json: {len(lines)} lines, {len(timeline['bars'])} bars, {len(entries)} entries; "
               f"score.json: {len(order)} parts, {sum(map(len, out.values()))} notes")


if __name__ == "__main__":
    main()
