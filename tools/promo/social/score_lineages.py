"""Summarizes each candidate lineage in renders/promo/social/lineages/: per generation its machine, date, style,
key, tempo, the bridge's second line (length in seconds, choir voices), the tune variants it carries (new ones
marked +), and the program's own change log. Ends with a ranking by variety."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from songbird.style import HIDDEN  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
LIN = ROOT / "renders/promo/social/lineages"
NAMES = {62: "D", 63: "Eb", 64: "E", 59: "B", 61: "C#", 60: "C", 65: "F", 66: "F#", 67: "G", 57: "A", 58: "Bb", 56: "Ab", 68: "Ab", 69: "A", 55: "G"}


def bridge_line2(score):
    br = [s for s in score["sections"] if s[0] == "bridge"]
    if not br:
        return None
    _, a, b = br[0]
    ns = [n for n in score["notes"] if n["part"] == "voice" and n["section"] == "bridge" and a - 1 <= n["start"] < b and n["phrase"] == "b2"]
    if not ns:
        return None
    t0, t1 = ns[0]["start"], ns[-1]["start"] + ns[-1]["dur"]
    choir = sorted({n["part"] for n in score["notes"] if n["part"].startswith("choir") and t0 <= n["start"] < t1})
    orn = [n["syllable"] for n in ns if n.get("ornament")]
    return {"dur": t1 - t0, "choir": len(choir), "text": " ".join(n["syllable"] for n in ns), "orn": orn}


def main():
    ranks = []
    for folder in sorted(p for p in LIN.iterdir() if p.is_dir() and (p / "plan.json").exists()):
        plan = json.loads((folder / "plan.json").read_text())
        print(f"\n===== {folder.name}")
        styles, keys, tempos, durs, new_var, words, hidden = [], [], [], [], 0, 0, False
        for step in plan:
            g = step["gen"]
            rec = json.loads((folder / f"gen{g}.json").read_text())
            sc = json.loads((folder / f"gen{g}.score.json").read_text())
            p = rec["params"]
            style = (p.get("style") or {}).get("name")
            hidden |= style in HIDDEN
            styles.append(style)
            keys.append(p["tonic"])
            tempos.append(p["tempo"])
            b2 = bridge_line2(sc)
            if b2:
                durs.append(b2["dur"])
            var = [(v["phrase"], v["note"], v["kind"], v["born"]) for v in p.get("variants") or []]
            new = [v for v in var if v[3] == g]
            new_var += len(new)
            ch = (rec.get("evolution") or {}).get("changes") or []
            words += sum(1 for c in ch if c.get("what") == "words" and c.get("change") == "added")
            vs = " ".join(f"{'+' if v[3] == g else ''}{v[0]}.{v[1]}:{v[2]}" for v in var)
            print(f" g{g} {step['machine']:5} {step['date']} {style!s:11}{'(HIDDEN)' if style in HIDDEN else ''} "
                  f"{NAMES.get(p['tonic'], p['tonic'])} {p['mode'][:5]} {p['tempo']:5.1f} "
                  f"b2 {b2['dur'] if b2 else 0:4.1f}s choir {b2['choir'] if b2 else '-'} orn {b2['orn'] if b2 else '-'} | {vs}")
            for c in ch:
                print("      ", c.get("what"), c.get("change"), c.get("where", ""), c.get("about") or c.get("to") or c.get("from") or "", "|", c.get("why", "")[:90])
        score = (len(set(styles)) * 2 + len(set(keys)) + (max(tempos) - min(tempos)) / 15 + new_var * 1.5 + words
                 + (max(durs) / min(durs) if durs else 0)) * (0 if hidden else 1)
        ranks.append((score, folder.name, styles, hidden))
    print("\n===== ranking")
    for s, name, styles, hidden in sorted(ranks, reverse=True):
        print(f" {name} {s:5.1f} {'HIDDEN ' if hidden else ''}{' > '.join(map(str, styles))}")


if __name__ == "__main__":
    main()
