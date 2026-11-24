"""A stand-in timeline.json and score.json, in the README's schema, built from the capture's score.

    python3 tools/promo/video/capture/fixture.py

Writes renders/promo/video/scratch/fixture/{timeline,score}.json. serve.mjs answers /data/<file> from
renders/promo/video/data/ when the file is there and from this fixture otherwise. The human amounts and
level curves here are approximations (a step per line from the storyboard, a level from the notes);
the real ones come from prep/."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "renders/promo/capture/render.score.json"
OUT = ROOT / "renders/promo/video/scratch/fixture"
DURATION, FPS, BAR, TEMPO = 151.227, 60, 2.5, 96
NAMES = {"intro": "intro", "turn": "turn", "bridge": "bridge", "tag": "tag"}
# the storyboard's human amount per line, by section and line index
HUMAN = {"verse1": [0, 0, 0, 0.2], "refrain1": [0.3, 0.4, 0.45, 0.5], "verse2": [0.5, 0.5, 0.5, 0.5],
         "refrain2": [0.6, 0.6, 0.6, 0.6], "bridge": [0.7, 0.7, 0.7, 0.7], "refrain3": [0.75] * 4, "tag": [0.75]}


def main() -> None:
    src = json.loads(SRC.read_text())
    count, sections = {}, []
    for kind, t0, t1 in src["sections"]:
        count[kind] = count.get(kind, 0) + 1
        sid = kind if kind in ("intro", "bridge", "tag") else f"{kind}{count[kind]}"
        sections.append({"id": sid, "kind": kind, "t0": t0, "t1": t1})
    sections.append({"id": "ring", "kind": "ring", "t0": sections[-1]["t1"], "t1": DURATION})
    sec_of = lambda t: next((s["id"] for s in sections if s["t0"] <= t < s["t1"]), "intro")

    notes = sorted(src["notes"], key=lambda n: n["start"])
    voice = [n for n in notes if n["part"] == "voice"]
    lines, cur, i = [], [], 0
    while i < len(voice):
        group = voice[i: i + max(1, int(voice[i].get("word_len") or 1))]
        i += len(group)
        word = {"text": "".join(n["syllable"].replace("*", "") for n in group), "t0": group[0]["start"],
                "t1": group[-1]["start"] + group[-1]["dur"],
                "syllables": [{"text": n["syllable"].replace("*", ""), "t0": n["start"], "t1": n["start"] + n["dur"],
                               "pitch": n["pitch"], "focus": n["syllable"].startswith("*")} for n in group]}
        cur.append(word)
        if group[-1]["line_end"]:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    out_lines, per = [], {}
    for words in lines:
        sid = sec_of(words[0]["t0"] + 0.3)
        k = per.get(sid, 0)
        per[sid] = k + 1
        hs = HUMAN.get(sid, [0.75])
        out_lines.append({"section": sid, "i": k, "t0": words[0]["t0"], "t1": words[-1]["t1"],
                          "text": " ".join(w["text"] for w in words), "human": hs[min(k, len(hs) - 1)], "words": words})

    parts = {}
    for n in notes:
        parts.setdefault(n["part"], []).append(
            {"t": n["start"], "d": n["dur"], "p": n["pitch"], "v": n["vel"], "syl": n["syllable"], "word": n["word"],
             "sec": sec_of(n["start"] + 1e-6), "phrase": n["phrase"], "art": n["art"], "g": n["gesture"]})

    levels = {}
    for part, ns in parts.items():
        pts = [[0.0, -60.0]]
        for n in ns:
            db = -18 + 12 * n["v"]
            pts += [[n["t"], -60.0], [n["t"] + 0.01, db], [n["t"] + n["d"], db - 6], [n["t"] + n["d"] + 0.15, -60.0]]
        levels[part] = pts

    t0 = src["sections"][0][1]
    bars = [round(t0 + k * BAR, 6) for k in range(int((DURATION - t0) / BAR) + 1)]
    beats = [round(t0 + k * BAR / 4, 6) for k in range(int((DURATION - t0) / (BAR / 4)) + 1)]
    human = [[l["t0"], l["human"]] for l in out_lines]
    entries = [{"part": p, "t": ns[0]["t"], "kind": "voice" if p == "voice" else "choir" if p.startswith("choir") else "player"}
               for p, ns in parts.items()]
    degrees = {90: "so", 87: "mi", 83: "do", 78: "so"}
    daisy = [{"t": n["t"], "dur": n["d"], "pitch": n["p"], "degree": degrees.get(int(n["p"]), "?")}
             for n in parts.get("whistle", []) if 110 < n["t"] < 116 and n["d"] > 1]
    timeline = {"duration": DURATION, "fps": FPS, "frames": round(DURATION * FPS), "tempo": TEMPO, "bar": BAR,
                "tonic": 59, "key": "B major", "sections": sections, "bars": bars, "beats": beats, "lines": out_lines,
                "human": human, "entries": sorted(entries, key=lambda e: e["t"]), "levels": levels, "daisy": daisy,
                "fixture": "stand-in built by capture/fixture.py from renders/promo/capture/render.score.json"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "timeline.json").write_text(json.dumps(timeline))
    (OUT / "score.json").write_text(json.dumps({"parts": parts}))
    print(f"{len(out_lines)} lines, {len(parts)} parts, {len(daisy)} daisy notes -> {OUT}")


if __name__ == "__main__":
    main()
