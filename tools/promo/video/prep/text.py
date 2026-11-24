"""text.json: the song as written (the genome's phrases, form, refrain, bank with each entry's `by`), which bank
entries this version sings, the record's blended gesture rows, the tune's notes that moved to follow the singers,
the credits as CREDITS.md writes them, and every count shown on screen with the file it comes from.

    uv run python tools/promo/video/prep/text.py"""
from __future__ import annotations

import re

import common

GENOME_PATH = "performance/genome.json"
RECORD_PATH = "performance/record-live-A.json"
HISTORY = common.ROOT / "docs/history/MAKING-IT-THEIR-OWN.md"
CREDITS = common.ROOT / "CREDITS.md"
DEGREE_NAMES = {"do": "1", "re": "2", "mi": "3", "fa": "4", "so": "5", "la": "6", "ti": "7"}


def tune_notes(tune: str) -> list[dict]:
    """A phrase's tune as the genome writes it, one entry per note: its digit (with "," below, "'" above), the
    unit it starts on (eighths from the phrase's first bar line; a pickup's are negative) and its length in units.
    A "-" holds the note before, a "." is a rest, "|" a bar line."""
    bars = tune.split("|")
    pickup, body = bars[0].split(), " ".join(bars[1:]).split()
    notes, u = [], -len(pickup)
    for tok in pickup + body:
        if tok == "-":
            if notes:
                notes[-1]["units"] += 1
        elif tok != ".":
            notes.append({"degree": tok, "at": u, "units": 1})
        u += 1
    return notes


def plain(s: str) -> str:
    s = s.lower().replace("*", "").replace("-", "")
    return re.sub(r"[^a-z' {}._]", " ", s)


def pattern(line: str) -> re.Pattern:
    parts = re.split(r"(\{[^{}]+\})", re.sub(r"\s+", " ", plain(line)).strip())
    rx = "".join(r"([a-z' ]+?)" if p.startswith("{") else re.escape(p) for p in parts)
    return re.compile(r"\s*" + re.sub(r"(\\ )+", r"\\s+", rx) + r"\s*$")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", plain(s)).strip()


def matches(lines: list[str], sung: list[str]) -> list[int]:
    """Which sung lines (indices) each bank line matches, slots as any words."""
    found = []
    for ln in lines:
        rx = pattern(ln)
        found.append(next((i for i, s in enumerate(sung) if rx.match(norm(s))), None))
    return found


def moved_notes(genome: dict) -> dict:
    """The table under "The first note shifts the song took" in the history doc, each row checked against the
    genome's tune: the note it names now holds the "now" degree."""
    text = common.read_text(HISTORY)
    start = text.index("## The first note shifts the song took")
    rows, intro = [], text[start: text.index("| where |", start)]
    for line in text[start:].splitlines():
        if line.startswith("| ") and not line.startswith("| where") and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 5:
                continue
            where, words, was, now, singers = cells
            pid, pos = [x.strip() for x in where.split(",", 1)]
            if pos == "pickup":
                idx = [0]
            else:
                m = re.match(r"(\d+)\w*(?:-(\d+)\w*)?", pos)
                a, b = int(m.group(1)), int(m.group(2) or m.group(1))
                idx = list(range(a - 1, b))
            tune = tune_notes(genome["phrases"][pid]["tune"])
            now_digits = [DEGREE_NAMES[w] for w in now.replace("low ", "").split()]
            held = [tune[i]["degree"].rstrip(",'") for i in idx]
            rows.append({"phrase": pid, "position": pos, "notes": idx, "words": words.replace("*", ""),
                         "focus": re.findall(r"\*([^*]+)\*", words), "from": was, "to": now,
                         "tune_now": [tune[i]["degree"] for i in idx], "agrees": held == now_digits,
                         "singers": singers})
        elif rows and not line.startswith("|"):
            break
    said = re.search(r"\((\d+) notes of a whole song", intro)
    return {"source": "docs/history/MAKING-IT-THEIR-OWN.md, the table under \"The first note shifts the song took\"",
            "count_said": int(said.group(1)) if said else None, "rows": rows}


def sung_instances(rows: list[dict], form: list[str], genome: dict) -> dict:
    """How many sung notes each moved phrase note is in this version's form."""
    per = {}
    for name in form:
        for pid in genome["sections"][name]["phrases"]:
            per[pid] = per.get(pid, 0) + 1
    return {f"{r['phrase']}:{i}": per.get(r["phrase"], 0) for r in rows for i in r["notes"]}


def credits() -> dict:
    text = common.read_text(CREDITS)
    names = re.findall(r"^- (.+)$", text.split("Credited, as they asked:")[1].split("\n\n\n")[0], re.M)
    rest = text.split("Credited, as they asked:")[1]
    uncredited = next(ln.strip() for ln in rest.splitlines() if "without credit" in ln)
    people = re.search(r"shaped by (\w+) people", text).group(1)
    return {"source": "CREDITS.md", "byline": text.splitlines()[2].strip(), "heading": "Credited, as they asked:",
            "names": names, "uncredited": uncredited, "people": people,
            "record_line": next(ln.strip() for ln in text.splitlines() if "record counts" in ln)}


def main() -> None:
    genome = common.read_json(common.ROOT / GENOME_PATH)
    rec = common.record()
    sung_text = [ln for ln in common.read_text(common.CAPTURE / "render.txt").splitlines()[2:] if ln.strip()]
    bank = genome["bank"]

    phrases = {pid: {"tune": p["tune"], "chords": p["chords"], "notes": tune_notes(p["tune"])}
               for pid, p in genome["phrases"].items()}
    form_sung = rec["params"]["form"]

    # the bank, each entry with the sung lines it matches
    def entry(e, kind):
        found = matches(e["lines"], sung_text)
        return {"kind": kind, "id": e["id"], "by": e.get("by"), "lines": e["lines"], "slots": e.get("slots"),
                **({k: e[k] for k in ("era", "mood", "scheme", "rarity") if k in e}), "sung_lines": found}

    rf = bank["refrain"]
    entries = [entry({"id": rf["id"], "lines": rf["lines"], "slots": rf["slots"], "by": rf.get("by")}, "head")]
    entries += [entry(h, "head") for h in rf["heads"]]
    entries += [entry(c, "couplet") for c in rf["couplets"]]
    entries += [entry(v, "verse") for v in bank["verses"]]
    entries += [entry(b, "bridge") for b in bank["bridges"]]
    changed = rec["params"]["composition"].get("lines") or {}
    for e in entries:  # a verse whose lines the record rewrites: the rest of it matched is enough
        own = changed.get(f"{'verse' if e['kind'] == 'verse' else e['kind']}:{e['id']}", {})
        for k, line in own.items():
            e.setdefault("rewritten", {})[k] = line
            e["sung_lines"][int(k)] = next((i for i, s in enumerate(sung_text) if norm(s) == norm(line)), None)
    for e in entries:
        hits = [i for i in e["sung_lines"] if i is not None]
        e["sung"] = len(hits) == len(e["lines"])
    sung_ids = [(e["kind"], e["id"]) for e in entries if e["sung"]]

    lead_rows = rec["performance"]["lead"]
    choir_rows = rec["performance"]["choir"]

    def rows_of(block):
        return {"fields": block["fields"],
                "rows": [{"phrase": pid, "note": i, "degree": phrases[pid]["notes"][i]["degree"]
                          if i < len(phrases[pid]["notes"]) else None, "g": row}
                         for pid, rows in block["phrases"].items() for i, row in enumerate(rows)]}

    moved = moved_notes(genome)
    moved["sung_in_this_form"] = sung_instances(moved["rows"], form_sung, genome)
    cr = credits()

    from songbird.synth import throat
    model = throat.load()
    counts = {
        "takes": {"value": int(re.match(r"(\d+) sung takes", rec["phrasing"]["source_detail"]).group(1)),
                  "source": f"{RECORD_PATH} phrasing.source_detail: \"{rec['phrasing']['source_detail']}\""},
        "people": {"value": cr["people"], "source": "CREDITS.md: \"shaped by eight people who sang along to it online\""},
        "record_singers": {"value": int(re.search(r"by (\d+) singers", rec["phrasing"]["source_detail"]).group(1)),
                           "source": f"{RECORD_PATH} phrasing.source_detail; CREDITS.md: \"{cr['record_line']}\""},
        "credited_names": {"value": len(cr["names"]), "source": "CREDITS.md, the list under \"Credited, as they asked:\""},
        "choir_takes": {"value": [c["source_detail"] for c in rec["choir_phrasings"]],
                        "source": f"{RECORD_PATH} choir_phrasings[].source_detail"},
        "verses": {"value": len(bank["verses"]), "source": f"{GENOME_PATH} bank.verses"},
        "bridges": {"value": len(bank["bridges"]), "source": f"{GENOME_PATH} bank.bridges"},
        "heads": {"value": 1 + len(rf["heads"]), "source": f"{GENOME_PATH} bank.refrain (its own lines and heads)"},
        "couplets": {"value": len(rf["couplets"]), "source": f"{GENOME_PATH} bank.refrain.couplets"},
        "questions": {"value": rf["slots"]["question"], "source": f"{GENOME_PATH} bank.refrain.slots.question"},
        "gesture_rows_lead": {"value": len(rows_of(lead_rows)["rows"]), "source": f"{RECORD_PATH} performance.lead"},
        "weights": {"value": int(model.config["params"]), "source": "songbird/synth/throat.npz (model.config params)"},
        "moved_rows": {"value": len(moved["rows"]), "source": moved["source"]},
        "moved_said": {"value": moved["count_said"], "source": moved["source"] + ": \"15 notes of a whole song\""},
    }

    out = {
        "title": genome["title"],
        "meter": genome["meter"], "sketch": genome["sketch"],
        "phrases": phrases,
        "sections": genome["sections"],
        "form": {"genome": genome["form"], "sung": form_sung},
        "refrain": {"lines": genome["refrain"], "turning_word": rf["slots"]["question"],
                    "sung": [ln for ln in sung_text if ln.lower().startswith("who ")]},
        "bridge": genome["bridge"], "tag": genome["tag"], "quote": genome["quote"],
        "bank": entries,
        "sings": {"entries": [f"{k}:{i}" for k, i in sung_ids],
                  "rewritten": {k: v for k, v in changed.items()},
                  "rewritten_source": f"{RECORD_PATH} params.composition.lines"},
        "gestures": {"source": f"{RECORD_PATH} performance (lead, choir); songbird/phrasing.py",
                     "lead": rows_of(lead_rows), "choir": [rows_of(c) for c in choir_rows]},
        "moved": moved,
        "credits": cr,
        "counts": counts,
    }
    common.write_json("text.json", out, indent=1)
    common.say(f"text.json: {len(entries)} bank entries, sings {out['sings']['entries']}; "
               f"{len(moved['rows'])} moved rows; credits {cr['names']}")


if __name__ == "__main__":
    main()
