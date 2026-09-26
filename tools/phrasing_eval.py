"""Does a phrasing learned from two takes beat one learned from one? (dev-only)

    uv run python tools/phrasing_eval.py songs/h-now-its-by-you.json --singer milo
    uv run python tools/phrasing_eval.py songs/h-now-its-by-you.json --reference formant say-daniel elevenlabs-george

A phrasing is learned: every note's gesture is an average over every time
someone sang that note. That only means something if the extractor
(tools/phrasing.py) finds what the singer did rather than noise, and then more
singing should make a better phrasing. Two ways to check:

--singer: real takes, whose truth nobody knows. Each sighting of a note
(one take, one time round) is held out in turn and predicted from n other
sightings of the same note, n = 1, 2, 3, 4. If the gestures are real,
prediction beats singing it plain (R2 > 0) and improves with n. Alongside,
how much of each gesture's spread belongs to the note rather than to the
moment (reliability: 0 is all noise, 1 all signal), and whether two takes
agree note by note.

--reference: takes by reference singers (tools/reference.py), whose every
gesture is known. How closely the extractor reads each gesture (correlation,
the slope it reads them at, the error), and how close a phrasing learned
from 1, 2 or 4 takes comes to what the singer meant, against the best any
extractor could do with the same takes (averaging what was actually sung).
Takes of different voices singing the same intent can be pooled with --pool.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import warnings
from dataclasses import astuple, fields
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message="pkg_resources")
warnings.filterwarnings("ignore", category=RuntimeWarning)
sys.path.insert(0, str(Path(__file__).parent))
import phrasing as T  # noqa: E402
import takes as K  # noqa: E402

from songbird import genome as G  # noqa: E402
from songbird import phrasing as P  # noqa: E402

FIELDS = [f.name for f in fields(P.Gesture)]
PLAIN = np.array([1.0 if f == "hold" else 0.0 for f in FIELDS])  # singing it plain: no gesture at all
LOW = np.array([0.0 if f == "vibrato" else getattr(P.LOW, f) for f in FIELDS])
HIGH = np.array(astuple(P.HIGH))
GENOME = None  # the song, for rules (T.ruled)
METHOD = "ruled"  # how a phrasing is made from sightings: "ruled" (T.ruled) or "shrunk" (T.shrunk)
WORDS: list[str] = []  # what each note of the guide is sung to (every take here was sung to the current guide)
RAW = dict.fromkeys(("timing", "level", "swell", "scoop", "bend", "fall", "vibrato", "tune"), 1.0)
UNITS = {"early": "ms", "hold": "", "level": "dB", "swell": "dB", "scoop": "c", "bend": "c", "fall": "c", "vibrato": "c",
         "tune": "c"}


def matrix(data: dict) -> np.ndarray:
    """A measured take as notes x fields, NaN where unmeasured, each sighting kept within a phrasing's bounds."""
    m = np.array([astuple(g) for g in T.gestures_of(data)], dtype=float)
    m[:, FIELDS.index("vibrato")] = np.where(m[:, FIELDS.index("vibrato")] < 0, np.nan, m[:, FIELDS.index("vibrato")])
    return np.clip(m, LOW, HIGH)


def by_name(names: list[str], rows: list) -> np.ndarray:
    """Rows of gesture values listed under names, as notes x FIELDS; a field a file doesn't have is plain."""
    out = np.tile(PLAIN, (len(rows), 1))
    for j, name in enumerate(names):
        if name in FIELDS:
            out[:, FIELDS.index(name)] = [r[j] for r in rows]
    return np.clip(out, LOW, HIGH)


def keys_of(data: dict) -> list[tuple[str, int]]:
    return [(n["phrase"], n["index"]) for n in data["notes"]]


def show(field: str, v: float, tempo: float) -> float:
    return v * 60000.0 / tempo if field == "early" else v


# --- real takes ------------------------------------------------------------------------


def reliability(values: list[np.ndarray]) -> tuple[float, float, float]:
    """(between-note variance, within-note variance, the share that is the note's own) from every note's sightings."""
    between, within = T.components(values)
    return between, within, between / (between + within) if between + within > 0 else np.nan


def learning_curve(sightings: dict, f: int, sizes=(1, 2, 3, 4), draws: int = 12) -> dict:
    """R2 of predicting each held-out sighting from n others of the same note
    (their mean), against singing it plain; the same for the singer's overall
    habit (every other sighting of every note) and for each note's mean shrunk
    toward that habit as far as the notes' reliability says. Every n is scored
    on the same held-out sightings: those of notes sung at least max(sizes) + 1 times."""
    rng = np.random.default_rng(0)
    groups = [np.array([v[f] for _, v in ss]) for ss in sightings.values()]
    groups = [g[np.isfinite(g)] for g in groups]
    allv = np.concatenate(groups)
    total, count = allv.sum(), len(allv)
    between, within, _ = reliability(groups)
    lam = (lambda n: n * between / (n * between + within)) if between + within > 0 else (lambda n: 0.0)
    plain = np.mean((allv - PLAIN[f]) ** 2)
    out = {"habit": 1 - np.mean([(x - (total - x) / (count - 1)) ** 2 for x in allv]) / plain}
    common = [g for g in groups if len(g) > max(sizes)]
    plain_common = np.mean((np.concatenate(common) - PLAIN[f]) ** 2) if common else np.nan
    for n in sizes:
        errs, shrunk = [], []
        for g in common:
            for i, x in enumerate(g):
                pool = np.delete(g, i)
                habit = (total - x) / (count - 1)
                combos = list(itertools.combinations(range(len(pool)), n))
                if len(combos) > draws:
                    combos = [combos[j] for j in rng.choice(len(combos), draws, replace=False)]
                for c in combos:
                    mean = pool[list(c)].mean()
                    errs.append((x - mean) ** 2)
                    shrunk.append((x - (habit + lam(n) * (mean - habit))) ** 2)
        out[n] = (1 - np.mean(errs) / plain_common, 1 - np.mean(shrunk) / plain_common) if errs else None
    out["held_out"] = sum(len(g) for g in common)
    return out


def evaluate_singer(genome_path: Path, genome, who: str) -> None:
    chosen = [t for t in K.takes(genome_path.stem, who) if t.use]
    if not chosen:
        raise SystemExit(f"no takes by {who}")
    data = [T.measured(genome_path, genome, t) for t in chosen]
    sightings: dict = {}
    for ti, d in enumerate(data):
        for key, row in zip(keys_of(d), matrix(d)):
            sightings.setdefault(key, []).append((ti, row))
    print(f"{who}: {len(data)} take(s), {sum(len(d['notes']) for d in data)} sightings of {len(sightings)} notes\n")
    print("Held out one sighting at a time, predicted from n other sightings of the same note. R2 against singing it")
    print("plain: above 0 the phrasing predicts the singer; 'shrunk' pulls each note's mean toward the singer's habit.\n")
    print(f"{'':8} {'reliab.':>7} {'habit':>6}   " + "   ".join(f"n={n}: mean  shrunk" for n in (1, 2, 3, 4)))
    for f, name in enumerate(FIELDS):
        share = reliability([np.array([v[f] for _, v in ss]) for ss in sightings.values()])[2]
        curve = learning_curve(sightings, f)
        cells = []
        for n in (1, 2, 3, 4):
            c = curve.get(n)
            cells.append(f"{c[0]:+10.2f} {c[1]:+6.2f}" if c else f"{'':>10} {'':>6}")
        print(f"{name:8} {share:7.2f} {curve['habit']:+6.2f}   " + "   ".join(cells) + f"   ({curve['held_out']} held out)")
    if len(data) >= 2:
        print("\nA new take, predicted by the phrasing made (as tools/phrasing.py makes it) from n of the others:")
        print(f"{'':8} " + " ".join(f"{'n=' + str(n):>8}" for n in range(1, len(data))))
        for f, name in enumerate(FIELDS):
            cells = []
            for n in range(1, len(data)):
                scores = []
                for held in range(len(data)):
                    others = [i for i in range(len(data)) if i != held]
                    for c in itertools.combinations(others, n):
                        made = phrasing_made([data[i] for i in c], RAW)
                        y = matrix(data[held])[:, f]
                        pred = np.array([made[k][f] for k in keys_of(data[held])])
                        ok = np.isfinite(y) & np.isfinite(pred)
                        scores.append(1 - np.sum((y[ok] - pred[ok]) ** 2) / np.sum((y[ok] - PLAIN[f]) ** 2))
                cells.append(f"{np.mean(scores):+8.2f}")
            print(f"{name:8} " + " ".join(cells))
        print("\nDo the takes agree? Every note's mean in one take against the same note in another (correlation):")
        for (a, da), (b, db) in itertools.combinations(enumerate(data), 2):
            ma, mb = mean_by_key(da), mean_by_key(db)
            both = [k for k in ma if k in mb]
            rs = []
            for f, name in enumerate(FIELDS):
                x = np.array([ma[k][f] for k in both])
                y = np.array([mb[k][f] for k in both])
                ok = np.isfinite(x) & np.isfinite(y)
                rs.append(f"{name} {np.corrcoef(x[ok], y[ok])[0, 1]:+.2f}" if ok.sum() >= 8 else f"{name}   -  ")
            print(f"  take {a + 1} vs take {b + 1}: " + ", ".join(rs))


def mean_by_key(d: dict) -> dict:
    out: dict = {}
    for key, row in zip(keys_of(d), matrix(d)):
        out.setdefault(key, []).append(row)
    return {k: np.nanmean(np.array(v), axis=0) for k, v in out.items()}


# --- reference singers ------------------------------------------------------------------


def reference_takes(genome_path: Path, genome, voice: str):
    """(measured, truth) for every take of a reference voice."""
    folder = T.ROOT / "renders" / "reference" / voice
    out = []
    for wav in sorted(folder.glob(f"{genome_path.stem}-take*.wav")):
        truth = json.loads(wav.with_suffix(".truth.json").read_text())
        out.append((T.measured(genome_path, genome, wav), truth))
    if not out:
        raise SystemExit(f"no reference takes in {folder}: make some with tools/reference.py")
    return out


def phrasing_from(rows: list[tuple[list, np.ndarray]]) -> dict:
    """A phrasing as a plain average: each note's mean over every sighting."""
    pooled: dict = {}
    for keys, m in rows:
        for key, row in zip(keys, m):
            pooled.setdefault(key, []).append(row)
    return {k: np.nanmean(np.array(v), axis=0) for k, v in pooled.items()}


def phrasing_made(takes: list[dict], scale: dict | None = None, floor: bool = True, who: list | None = None,
                  method: str | None = None) -> dict:
    """A phrasing as tools/phrasing.py makes one (scaled as a phrasing keeps it, bounded, shrunk toward the
    singer's habit), before rounding. scale: T.SUNG, or RAW to stay in the extractor's own units. who: the
    voice of each take, when they're not all one singer's (the extractor's repeating error is each voice's
    own, so different voices average it away). Every take here must have been sung to the guide in WORDS."""
    scale = scale or T.SUNG
    seen: dict = {}
    words: dict = {}
    weights: dict = {}
    for i, d in enumerate(takes):
        share = 1.0 / (who.count(who[i]) if who else len(takes))  # each singer counts once
        for n, ge, w in zip(d["notes"], T.gestures_of(d), WORDS):
            key = (n["phrase"], n["index"])
            seen.setdefault(key, []).append(T.bounded(T.scaled(ge, scale)))
            words.setdefault(key, []).append(f"{who[i] if who else ''}|{w}")
            weights.setdefault(key, []).append(share)
    floor_ = T.floor_for(scale) if floor else None
    if (method or METHOD) == "ruled":
        made = T.ruled(GENOME, seen, words, floor_, weights)
    else:
        made = T.shrunk(seen, words, floor_, weights)
    out = {k: np.array(astuple(v[0]), dtype=float) for k, v in made.items()}
    for v in out.values():
        v[FIELDS.index("vibrato")] = max(v[FIELDS.index("vibrato")], 0.0)  # "the machine's own" reads as none here
    return out


def blended(phrasings: list[dict]) -> dict:
    """Several singers' phrasings averaged note by note, each singer once (as P.blend does, before rounding)."""
    return {k: np.nanmean([ph[k] for ph in phrasings if k in ph], axis=0) for k in phrasings[0]}


def closeness(est: dict, intent: dict, f: int) -> float:
    """R2 of a learned phrasing against what the singer meant, for one field (0: no better than plain)."""
    ks = [k for k in intent if k in est and np.isfinite(est[k][f]) and (f != 7 or est[k][f] >= 0)]
    want = np.array([intent[k][f] for k in ks])
    got = np.array([est[k][f] for k in ks])
    return 1 - np.sum((got - want) ** 2) / np.sum((want - PLAIN[f]) ** 2)


def intent_of(truth: dict) -> dict:
    intent = {}
    for k, g in truth["intended"].items():
        phrase, index = k.rsplit("#", 1)
        intent[(phrase, int(index))] = by_name(truth["fields"], [g])[0]
    return intent


def onsets(genome_path: Path, genome, runs: dict) -> None:
    """Where the aligner put each vowel's start against where the reference singer began it, by the sound before."""
    from songbird.realize import sung_as
    from songbird.synth import voice as V

    g = T.guide(genome_path, genome)
    beat = 60.0 / g.tempo
    print("Vowel starts found against sung (ms; median, and root mean square), by what comes before the vowel:")
    table: dict = {}
    for v, takes in runs.items():
        for d, truth in takes:
            notes = [sung_as(n, P.Gesture(**dict(zip(truth["fields"], s))), beat) for n, s in zip(g.notes, truth["sung"])]
            starts = [seg.t0 for seg in V.schedule(notes, T.FLAT, g.lexicon) if seg.role == "vowel"]
            for n, t, before in zip(d["notes"], starts, g.before):
                table.setdefault(before, {}).setdefault(v, []).append(1000 * (n["onset"] - d["lag"] - t))
    print(f"  {'':12} " + " ".join(f"{v:>20}" for v in runs))
    for before, cells in sorted(table.items()):
        row = []
        for v in runs:
            e = np.array(cells.get(v, []))
            row.append(f"{np.median(e):+5.0f} / {np.sqrt(np.mean(e**2)):4.0f} ({len(e):3})" if len(e) else f"{'':>20}")
        print(f"  {before:12} " + " ".join(f"{c:>20}" for c in row))
    print()


def evaluate_reference(genome_path: Path, genome, voices: list[str], pool: bool, show_onsets: bool) -> None:
    runs = {v: reference_takes(genome_path, genome, v) for v in voices}
    tempo = T.guide(genome_path, genome).tempo
    if show_onsets:
        onsets(genome_path, genome, runs)
    print("How the extractor reads each gesture, sighting by sighting (every take of the voice): the")
    print("correlation with what was sung, the slope it reads it at (1 is true to size), and the error.")
    print(f"  {'':18} " + " ".join(f"{name:>15}" for name in FIELDS))
    print(f"  {'':18} " + " ".join(f"{'r  slope  err':>15}" for _ in FIELDS))
    slopes = {}
    for v, takes in runs.items():
        cells = []
        for f, name in enumerate(FIELDS):
            m = np.concatenate([matrix(d)[:, f] for d, _ in takes])
            s = np.concatenate([by_name(t["fields"], t["sung"])[:, f] for _, t in takes])
            ok = np.isfinite(m) & np.isfinite(s)
            if ok.sum() < 8 or np.std(s[ok]) == 0:
                cells.append(f"{'-':>15}")
                continue
            r = np.corrcoef(m[ok], s[ok])[0, 1]
            slope = np.polyfit(s[ok], m[ok], 1)[0]
            slopes.setdefault(name, []).append(slope)
            err = show(name, np.sqrt(np.mean((m[ok] - s[ok]) ** 2)), tempo)
            cells.append(f"{r:+.2f} {slope:5.2f} {err:4.0f}" if abs(err) >= 10 else f"{r:+.2f} {slope:5.2f} {err:4.1f}")
        print(f"  {v:18} " + " ".join(cells))
    print(f"  (err in {', '.join(f'{k} {u}' for k, u in UNITS.items() if u)}; hold as a fraction)")
    print("  median slope over these voices: " + ", ".join(f"{k} {np.median(x):.2f}" for k, x in slopes.items()) + "\n")

    print("How close a phrasing learned from n takes comes to what the singer meant (R2; 1 is exact, 0 no better")
    print("than singing plain): as tools/phrasing.py makes it now (scaled, bounded, shrunk toward the singer's habit),")
    print("[a plain average of the raw readings], and (the ceiling: averaging exactly what was sung).\n")
    sets = {v: [(d, t, v) for d, t in takes] for v, takes in runs.items()}
    if pool and len(runs) >= 2:
        sets["every voice together"] = [x for v in sets for x in sets[v]]
    for v, takes in sets.items():
        intent = intent_of(takes[0][1])
        print(f"  {v}")
        print(f"    {'takes':6} " + " ".join(f"{name:>20}" for name in FIELDS))
        sizes = sorted({1, 2, 4, len(takes)} & set(range(1, len(takes) + 1)))
        for n in sizes:
            made, plain, ceiling = [], [], []
            combos = list(itertools.combinations(range(len(takes)), n))
            if len(combos) > 30:
                combos = [combos[j] for j in np.random.default_rng(0).choice(len(combos), 30, replace=False)]
            for c in combos:
                rows = [(keys_of(takes[i][0]), matrix(takes[i][0])) for i in c]
                sung = [(keys_of(takes[i][0]), by_name(takes[i][1]["fields"], takes[i][1]["sung"])) for i in c]
                est = phrasing_made([takes[i][0] for i in c], who=[takes[i][2] for i in c])
                raw, best = phrasing_from(rows), phrasing_from(sung)
                made.append([closeness(est, intent, f) for f in range(len(FIELDS))])
                plain.append([closeness(raw, intent, f) for f in range(len(FIELDS))])
                ceiling.append([closeness(best, intent, f) for f in range(len(FIELDS))])
            made, plain, ceiling = (np.mean(x, axis=0) for x in (made, plain, ceiling))
            print(f"    {n:<6} " + " ".join(f"{a:+5.2f} [{b:+5.2f}] ({c:+.2f})" for a, b, c in zip(made, plain, ceiling)))
        print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--singer", help="a singer's folder name in recordings/")
    who.add_argument("--reference", nargs="+", metavar="VOICE", help="reference voices' folder names in renders/reference/")
    ap.add_argument("--pool", action="store_true", help="with --reference: also pool every voice's takes")
    ap.add_argument("--onsets", action="store_true", help="with --reference: where vowel starts were found, by consonant")
    ap.add_argument("--method", choices=("ruled", "shrunk"), default="ruled", help="how a phrasing is made from sightings")
    args = ap.parse_args()
    genome_path = Path(args.genome).resolve()
    genome = G.load(genome_path)
    WORDS[:] = [(n.syllable or "").lower() for n in T.guide(genome_path, genome).notes]
    global GENOME, METHOD
    GENOME, METHOD = genome, args.method
    if args.singer:
        evaluate_singer(genome_path, genome, K.slug(args.singer))
    else:
        evaluate_reference(genome_path, genome, args.reference, args.pool, args.onsets)


if __name__ == "__main__":
    main()
