"""The song evolving, to listen to: a lineage handed from machine to machine, and one machine's song over
three years, each rendition drawn against the seed's tune and written up.

    uv run python tools/evolution.py                  # everything, into renders/production/evolution/
    uv run python tools/evolution.py --only lineage   # one set: lineage, timeline or own
    uv run python tools/evolution.py --no-render      # redraw the pictures and the README from the records there

Every rendition is made by the command line itself (songbird render --machine fictional:NAME --date DATE
[--parent FILE]), so a file here is exactly what a person would get. Beside each .flac: its record (.json),
its score (.score.json), its lyric sheet (.txt) and a piano roll (.png) of the sung tune, phrase by phrase,
against the seed's. README.txt says what each file is and what changed from its parent or its earlier date.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from songbird import arrange, cli, evolve, genome as genome_mod, variants as V  # noqa: E402
from songbird.realize import Params  # noqa: E402
from songbird.theory import degree_semitones  # noqa: E402

SONG = ROOT / "songs" / "h-now-its-by-you.json"
OUT = ROOT / "renders" / "production" / "evolution"
NOTE = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
LETTERS = {"intro": "i", "verse": "V", "refrain": "R", "turn": "t", "break": "k", "bridge": "B", "bridge2": "b",
           "tag": "g", "outro": "o"}

# The lineage: the seed, then four made-up machines a few months apart, each singing the one before. These four
# were picked from a couple of thousand orderings of twelve made-up machines as a lively lineage that shows every
# kind of change; a typical one gathers about two variants by its fourth generation, this one five.
LINEAGE = (("wren", "2027-01-19"), ("badger", "2027-05-08"), ("stoat", "2027-08-27"), ("marten", "2027-12-14"))
# One machine over three years: kite singing the seed every four months (time alone), and kite singing its own
# last rendition every nine (a person who keeps singing their own version).
TIMELINE = ("kite", ("2026-10-04", "2027-02-04", "2027-06-04", "2027-10-04", "2028-02-04", "2028-06-04",
                     "2028-10-04", "2029-02-04", "2029-06-04", "2029-10-04"))
OWN = ("kite", ("2026-10-04", "2027-07-04", "2028-04-04", "2029-01-04", "2029-10-04"))
ROWS = (("verse", ("v1", "v2", "v3")), ("refrain", ("r1", "r2", "r3", "r4")), ("bridge", ("b1", "b2", "b3", "b4")))
COLOURS = {"plain": "#2b6cb0", "leap": "#dd6b20", "rhythm": "#2f855a", "ornament": "#805ad5", "seed": "#cbd5e0"}


def render(genome_path: Path, out: Path, machine: str | None = None, date: str | None = None,
           parent: Path | None = None) -> dict:
    args = ["render", str(genome_path), "--out", str(out)]
    if machine:
        args += ["--machine", f"fictional:{machine}"]
    if date:
        args += ["--date", date]
    if parent:
        args += ["--parent", str(parent)]
    if cli.main(args) != 0:
        raise SystemExit(f"render failed: {' '.join(args)}")
    return json.loads(out.with_suffix(".json").read_text())


def lyric_sheet(genome, record: dict, out: Path) -> None:
    """The lyric sheet beside a render (render writes one for drawn or held words; the seed sings its own)."""
    if not out.with_suffix(".txt").exists():
        params = Params.from_dict(record["params"])
        out.with_suffix(".txt").write_text(arrange.seed_lyrics(genome, params.form).sheet(genome.title))


def roll(genome, record: dict, out: Path, title: str) -> None:
    """The sung tune, phrase by phrase, in grid units and semitones above the tonic (in this rendition's
    mode), over the seed's in grey: a moved note in orange, a moved onset in green, an ornament's tones as
    thin purple strokes inside their note."""
    params = Params.from_dict(record["params"])
    seed = Params.from_dict(genome.seed_params)
    fig, axes = plt.subplots(3, 4, figsize=(12.5, 5.2), dpi=100, sharey=True)
    for r, (label, phrases) in enumerate(ROWS):
        for c in range(4):
            ax = axes[r][c]
            ax.set_facecolor("white")
            if c >= len(phrases):
                ax.axis("off")
                continue
            phrase = genome.phrases[phrases[c]]
            for p in V.realized(phrase, ()):
                y = degree_semitones(p.degree, seed.mode, p.alter)
                ax.add_patch(plt.Rectangle((p.onset, y - 0.45), p.dur - 0.08, 0.9, color=COLOURS["seed"], lw=0))
            for p in V.realized(phrase, params.variants):
                y = degree_semitones(p.degree, params.mode, p.alter)
                kind = p.variant.kind if p.variant is not None else "plain"
                colour = COLOURS["leap"] if kind == "leap" else COLOURS["rhythm"] if kind in V.RHYTHM else COLOURS["plain"]
                ax.add_patch(plt.Rectangle((p.onset, y - 0.3), p.dur - 0.08, 0.6, color=colour, lw=0, alpha=0.9))
                if p.ornament:  # the voice's path through the ornament, a step line over the note
                    points = list(V.semitones(p.ornament, p.degree, params.mode, p.alter))
                    if points[0][0] > 0:
                        points.insert(0, (0.0, 0.0))
                    xs, ys = [], []
                    for i, (f, s) in enumerate(points):
                        a = p.onset + f * (p.dur - 0.08)
                        b = p.onset + (points[i + 1][0] if i + 1 < len(points) else 1.0) * (p.dur - 0.08)
                        xs += [a, b]
                        ys += [y + s, y + s]
                    ax.plot(xs, ys, color=COLOURS["ornament"], lw=1.6, solid_joinstyle="miter")
                    ax.text(p.onset, y + 1.6, kind, fontsize=6, color=COLOURS["ornament"])
                elif kind != "plain":
                    ax.text(p.onset, y + 1.2, kind, fontsize=6, color=colour)
            ax.set_xlim(-1.5, phrase.bars * genome.meter.bar + 0.5)
            ax.set_ylim(-9, 13)
            for bar in range(phrase.bars + 1):
                ax.axvline(bar * genome.meter.bar, color="#edf2f7", lw=0.8, zorder=0)
            ax.set_xticks([])
            ax.tick_params(labelsize=6)
            ax.set_title(f"{label} {phrases[c]}", fontsize=7, loc="left")
    axes[0][0].set_ylabel("semitones above the tonic", fontsize=7)
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOURS[k]) for k in ("seed", "plain", "leap", "rhythm", "ornament")]
    fig.legend(handles, ["the seed's tune", "sung as written", "a note moved", "an onset moved", "an ornament's tones"],
               loc="lower right", fontsize=7, frameon=False, ncol=5)
    fig.suptitle(title, fontsize=9, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    fig.savefig(out.with_suffix(".png"))
    plt.close(fig)


# ---------------------------------------------------------------- the README


def _key(params: Params) -> str:
    return f"{NOTE[params.tonic % 12]} {params.mode}"


def _form(params: Params) -> str:
    return "".join(LETTERS.get(n, n[:1]) for n in params.form)


def _singer(params: Params) -> str:
    low = params.singer.get("shift", 0) == -12
    return f"{'a low' if low else 'a high'} singer (tract {params.singer.get('tract', 1.12):g})"


def summary(record: dict, from_parent: bool = True) -> list[str]:
    p = Params.from_dict(record["params"])
    verses = sum(n == "verse" for n in p.form)
    lines = [f"   {_key(p)}, {p.tempo:g} bpm; form {_form(p)} ({verses} verses); the band's {p.band.pattern} with the "
             f"{p.band.lead} leading; {_singer(p)}; {p.choir} lineage voice{'s' if p.choir != 1 else ''} in the bridge"]
    lyrics = record.get("lyrics")
    if lyrics:
        sung = arrange.Lyrics.from_dict(lyrics)
        lines.append(f"   words: verses {', '.join(sung.verses)}; refrain couplets {', '.join(sung.couplets)}; "
                     f"bridge {', '.join(sung.bridges)}" + (f"; tag on {sung.tag}" if sung.tag else ""))
    else:
        lines.append("   words: the seed's own (verses wire and screen; the canon couplet every refrain)")
    story = record.get("evolution") or {}
    if story.get("variants"):
        lines.append("   tune: " + "; ".join(v["about"] for v in story["variants"]))
    else:
        lines.append("   tune: as written")
    if story.get("distance"):
        d = story["distance"]
        parent = f"{d['parent']:.2f} from its parent, " if from_parent else ""
        lines.append(f"   the tune's contour, as the lineage gate will measure it (pitch, not rhythm): {parent}"
                     f"{d['seed']:.2f} from the seed (semitones a move; another song is 1.1 to 1.5)")
    return lines


def changelog(genome, before: dict | None, record: dict, from_parent: bool = True) -> list[str]:
    """What changed from the parent (with why, from the record), or from the earlier date (what the two sing
    differently): the song's settings, then the tune and the words."""
    if before is None:
        return []
    a, b = Params.from_dict(before["params"]), Params.from_dict(record["params"])
    out = []
    if (a.tonic, a.mode) != (b.tonic, b.mode):
        out.append(f"key {_key(a)} -> {_key(b)}")
    if abs(a.tempo - b.tempo) >= 0.5:
        out.append(f"tempo {a.tempo:g} -> {b.tempo:g}")
    if a.form != b.form:
        out.append(f"form {_form(a)} -> {_form(b)}")
    if (a.band.pattern, a.band.lead) != (b.band.pattern, b.band.lead):
        out.append(f"band {a.band.pattern}/{a.band.lead} -> {b.band.pattern}/{b.band.lead}")
    if a.singer.get("shift", 0) != b.singer.get("shift", 0) or a.singer.get("tract") != b.singer.get("tract"):
        out.append(f"singer {_singer(a)} -> {_singer(b)}")
    lines = ["   changed: " + ("; ".join(out) if out else "none of key, tempo, form, band or singer")]
    if not from_parent:  # the record's own changes are against its parent (the seed); against the last date:
        for d in evolve.diff(genome, a, b):
            if d["what"] == "tune":
                lines.append(f"   - the tune {'now sings' if d['change'] == 'gained' else 'no longer sings'} {d['about']}")
            else:
                lines.append(f"   - the words, {d['where'] if d.get('where') else d['change']}: {d.get('from') or '-'} -> "
                             f"{d.get('to') or '-'}")
        return lines
    for entry in (record.get("evolution") or {}).get("changes", []):
        if entry["what"] == "tune":
            lines.append(f"   - the tune {entry['change']} {entry['about']}; why: {entry['why']}")
        else:
            what = f"{entry.get('from')} -> {entry.get('to')}" if entry.get("from") and entry.get("to") else \
                (entry.get("to") or entry.get("from") or "")
            lines.append(f"   - the words, {entry['change']}{' ' + entry['where'] if entry.get('where') else ''}"
                         f"{': ' + what if what else ''}; why: {entry['why']}")
    return lines


HEADER = """Songbird's lead song, H "Now It's by You", evolving: its melody and words drift a little at a time, on top
of everything else a machine and the drift already change (key, mode, tempo, form, band, singer, mix).

Beside each .flac: its record (.json: every parameter, the words and the tune's variants, what changed from the
parent and why), its score (.score.json), its lyric sheet (.txt) and a piano roll (.png) of the sung tune,
phrase by phrase, over the seed's in grey (orange: a note moved; green: an onset moved; purple: an ornament's
tones inside its note). docs/EVOLUTION.md explains how the tune and the words drift and at what rates.

Regenerate everything (about ten minutes):  uv run python tools/evolution.py
Redraw the pictures and this file only:      uv run python tools/evolution.py --no-render
Finish an interrupted run:                   uv run python tools/evolution.py --keep
Any one of them by hand, e.g. the second generation:
    uv run songbird render songs/h-now-its-by-you.json --machine fictional:badger --date 2027-05-08 \\
        --parent renders/production/evolution/lineage/1-wren.json --out renders/production/evolution/lineage/2-badger.flac
"""

SETS = {
    "lineage": ("lineage/: the seed, then four generations on four made-up machines a few months apart, each\n"
                "singing the one before (songbird render --parent). The machines were picked from a couple of\n"
                "thousand orderings of twelve as a lively lineage that shows every kind of change; a typical one\n"
                "carries about two variants by its fourth generation, this one five."),
    "timeline": ("timeline/: one made-up machine, kite, singing the seed every four months for three years: time\n"
                 "alone. Its tune carries at most one or two variants of its own at a time, changing with the\n"
                 "seasons; its words hold for weeks and change a verse or a word at a time. Each is sung from the\n"
                 "seed, so below, what changed is against the date before (its record's own changes are against\n"
                 "the seed)."),
    "own": ("own/: kite singing its own last rendition every nine months: a person who keeps singing their own\n"
            "version. Variants gather at the pace of its clocks, as they do down a lineage."),
}


def write_readme(out: Path, genome, done: dict[str, list[tuple[str, dict, dict | None]]]) -> None:
    text = [HEADER]
    for name in ("lineage", "timeline", "own"):
        if name not in done:
            continue
        text += ["", SETS[name], ""]
        for path, record, before in done[name]:
            who = record.get("voice", {}) or {}
            at = (record.get("rendered_at") or "")[:10]
            label = f"generation {record.get('generation', 0)}" + (f", {at}" if at else ", no machine, no date")
            text.append(f"{path}  {label}, {record['duration']:.0f} s, id {record['id'][:12]}"
                        + (f", voice {who.get('hash')}" if who else ""))
            text += summary(record, name != "timeline")
            text += changelog(genome, before, record, name != "timeline")
            text.append("")
    (out / "README.txt").write_text("\n".join(text).rstrip() + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--only", choices=("lineage", "timeline", "own"), nargs="+")
    parser.add_argument("--no-render", action="store_true", help="draw and write up the records already there")
    parser.add_argument("--keep", action="store_true", help="keep any rendition already rendered, render the rest")
    args = parser.parse_args(argv)
    out = Path(args.out)
    genome = genome_mod.load(SONG)
    sets = args.only or ["lineage", "timeline", "own"]
    done: dict = {}

    def make(path: Path, machine=None, date=None, parent=None) -> dict:
        path.parent.mkdir(parents=True, exist_ok=True)
        done_already = args.no_render or (args.keep and path.with_suffix(".json").exists() and path.exists())
        record = json.loads(path.with_suffix(".json").read_text()) if done_already else \
            render(SONG, path, machine, date, parent)
        lyric_sheet(genome, record, path)
        return record

    seed_path = out / "lineage" / "0-seed.flac"
    seed = make(seed_path)
    if "lineage" in sets:
        rows = [(seed_path.relative_to(out), seed, None)]
        parent, before = seed_path, seed
        for k, (machine, date) in enumerate(LINEAGE, 1):
            path = out / "lineage" / f"{k}-{machine}.flac"
            record = make(path, machine, date, parent.with_suffix(".json"))
            rows.append((path.relative_to(out), record, before))
            parent, before = path, record
        done["lineage"] = rows
    if "timeline" in sets:
        machine, dates = TIMELINE
        rows, before = [], seed
        for date in dates:
            path = out / "timeline" / f"{machine}.{date}.flac"
            record = make(path, machine, date)
            rows.append((path.relative_to(out), record, before))
            before = record
        done["timeline"] = rows
    if "own" in sets:
        machine, dates = OWN
        rows, parent, before = [], None, seed
        for date in dates:
            path = out / "own" / f"{machine}.{date}.flac"
            record = make(path, machine, date, parent.with_suffix(".json") if parent else None)
            rows.append((path.relative_to(out), record, before))
            parent, before = path, record
        done["own"] = rows
    for rows in done.values():
        for path, record, _ in rows:
            p = Params.from_dict(record["params"])
            title = (f"{path}: generation {record.get('generation', 0)}, {_key(p)}, {p.tempo:g} bpm, "
                     f"{len(p.variants)} variant{'s' if len(p.variants) != 1 else ''}")
            roll(genome, record, out / path, title)
    if set(done) == {"lineage", "timeline", "own"} or args.no_render:
        write_readme(out, genome, done)
    return 0


if __name__ == "__main__":
    sys.exit(main())
