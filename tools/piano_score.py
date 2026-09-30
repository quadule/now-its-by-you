"""The released rendition's score, for learning it on the piano: web/piano/score.json (dev-only).

    uv run python tools/piano_score.py                   # renders/review/contest.flac -> web/piano/score.json
    uv run python tools/piano_score.py --check           # ...and check the score against the recording itself
    uv run python tools/piano_score.py FILE.flac --out X.json

How it is derived. The release (renders/review/contest.flac, rendered by `tools/everyone.py --render ... --arrange
motif=bridge lift=false ending=ring`) is a packet (docs/PACKET.md): it carries the program that sang it, the
genome, the render record and the words. This lays the rendition's score again the way tools/sing_site.py
seed_words does (and `songbird render --replay`): realize() with the record's params, words and phrasings, then
variation.lay, with no audio. It runs the packet's *own* program (unzipped to a temporary folder and imported
ahead of this tree's songbird/, after checking it against the record's program_sha256), so later changes to
songbird/ can't move a note. The score is trusted only if its words come out exactly as the packet's lyrics.txt.

realize() works on a grid (here an eighth note a unit) and then turns it into seconds with the rendition's
clock, adding the phrasing's pushes and pulls and a little human jitter. For a player the grid is the truth,
so this takes the grid itself: it listens in on songbird.band.plan (which is handed the band's Context, the
song laid out in grid units: sections, the chord under every beat, the tune note by note) and
songbird.band.arrange (handed realize()'s melody entries, with each syllable). Nothing is changed; the
listening only keeps references.

What goes in (positions and lengths in beats, a beat a quarter note, 0 at the first bar line of the song; the
pickup before it is negative; bar n starts at beat 4(n-1)):
- tempo, time signature, key (the record's tonic and mode), and the final phrase's ritardando: the clock's
  seconds(b) = 60/bpm * (b + amount * x^2 / (2 * span)), x = beats past its start (songbird.realize.Clock);
- sections (name, bars) and the chords (roman numeral, root, quality, name in the song's key) as the band plays
  them: the genome's chords split evenly through each bar, as songbird.band lays them;
- the melody: every tune note with its syllable. Where nobody sings, the band's lead states the tune (the intro,
  on the whistle an octave up) and it is given at the sung pitch; the turns' instrumental quotes (the fiddle,
  then the lute, an octave above the voice) are taken from the band's notes, quantized back onto the grid (a
  sixteenth) through the inverse clock, their grace notes ("cut") left out, and given an octave down too;
- left-hand parts. The band has no keyboard (lute, guitar, harp, bass, fiddle, whistle, drum, drone), so:
  "bass": the band's bass line as heard, quantized the same way, an octave up (in reach of a 61-key keyboard);
  "fifths": root and fifth together at each chord and on beat 3 of a bar-long chord;
  "folk": a broken-chord pattern, root-fifth-octave-fifth in quarters (root-fifth over a two-beat chord);
  "block": the chord's triad held, each voiced nearest the last, between A2 and B3.
Every part is the notes as written, in the song's own key; the page transposes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).parent.parent
RELEASE = ROOT / "renders" / "review" / "contest.flac"
OUT = ROOT / "web" / "piano" / "score.json"
COMMAND = ("uv run python tools/everyone.py --render renders/review/contest.flac "
           "--arrange motif=bridge lift=false ending=ring")
NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
QUANT = 0.25  # beats: a sixteenth, what the band's notes are snapped back to


def unpack_program(flac: Path, into: Path) -> dict:
    """The packet's program, genome, words and record, unzipped into `into`; the program checked against the
    record's hash (as the packet's own bootstrap checks it) before anything imports it."""
    with zipfile.ZipFile(flac) as z:
        record = json.loads(z.read("manifest.json"))
        program = {n: z.read(n) for n in z.namelist() if n.startswith("program/") and not n.endswith("/")}
        h = hashlib.sha256()
        for name in sorted(program):
            h.update(name.encode() + b"\0" + hashlib.sha256(program[name]).digest())
        if record.get("program_sha256") and h.hexdigest() != record["program_sha256"]:
            raise SystemExit(f"{flac}: the program inside doesn't match its record's program_sha256")
        for name in ("genome.json", "lyrics.txt", *program):
            z.extract(name, into)
    return record


def lay(flac: Path, tmp: Path) -> dict:
    """The rendition laid again from its packet with the packet's program: the score, the band's Context,
    realize()'s melody entries and clock, and the record."""
    record = unpack_program(flac, tmp)
    sys.path.insert(0, str(tmp / "program"))
    for name in [m for m in sys.modules if m == "songbird" or m.startswith("songbird.")]:
        del sys.modules[name]
    import songbird
    from songbird import band, genome as G, pack as P, phrasing as PH, variation
    from songbird.arrange import Lyrics
    from songbird.realize import PREROLL, Params, realize, timeline

    assert Path(songbird.__file__).is_relative_to(tmp), songbird.__file__
    genome = G.load(tmp / "genome.json")
    params = Params.from_dict(record["params"])
    params = replace(params, singer=record.get("singer") or params.singer, mix=record.get("mix") or params.mix)
    lyrics = Lyrics.from_dict(record["lyrics"]) if record.get("lyrics") else None
    lead, choir = PH.inherited(genome.source, record)

    heard: dict = {}
    plan, arrange = band.plan, band.arrange

    def plan_listened(ctx):
        heard["ctx"] = ctx
        return plan(ctx)

    def arrange_listened(*args):
        heard["arrange"] = args
        return arrange(*args)

    band.plan, band.arrange = plan_listened, arrange_listened
    try:
        score = variation.lay(realize(genome, params, phrasing=PH.from_json(lead) if lead else None,
                                      choir=[PH.from_json(d) for d in choir], lyrics=lyrics), params)
    finally:
        band.plan, band.arrange = plan, arrange
    sung = (tmp / "lyrics.txt").read_text()
    if P.words_as_sung(score.to_dict(), genome.title) != sung:
        raise SystemExit(f"{flac}: the score laid again doesn't sing the packet's words; not trusting it")
    _genome, _params, _placed, lead_u, end_u, melody, seconds = heard["arrange"]
    return {"record": record, "genome": genome, "params": params, "score": score, "ctx": heard["ctx"],
            "melody": sorted(melody, key=lambda m: m["u"]), "seconds": seconds, "lead": lead_u, "end": end_u,
            "clock": timeline(genome, params), "preroll": PREROLL, "program": songbird.__file__}


def chord_info(ctx, symbol: str) -> dict:
    from songbird.theory import chord_tones

    r, t, f = chord_tones(symbol, ctx.mode)
    quality = {(4, 7): "maj", (3, 7): "min", (3, 6): "dim", (4, 8): "aug"}.get(((t - r) % 12, (f - r) % 12), "maj")
    return {"root": (ctx.tonic + r) % 12, "quality": quality}


def chord_name(root: int, quality: str, flats: bool) -> str:
    return (NAMES_FLAT if flats else NAMES_SHARP)[root % 12] + {"maj": "", "min": "m", "dim": "dim", "aug": "+"}[quality]


def r4(x: float) -> float:
    return round(x * 4) / 4 if abs(x * 4 - round(x * 4)) < 1e-6 else round(x, 4)


def export(laid: dict) -> dict:
    ctx, clock, params, genome = laid["ctx"], laid["clock"], laid["params"], laid["genome"]
    lead, beat, bar = laid["lead"], ctx.beat, ctx.bar  # grid units: a beat is 2, a bar 8
    per_beat = bar // beat

    def b(u: float) -> float:  # grid units -> beats from the first bar line
        return (u - lead) / beat

    seconds = laid["seconds"]

    def unit_at(t: float) -> float:  # seconds -> grid units (the clock's inverse; it only ever moves forward)
        lo, hi = -4.0 * bar, laid["end"] + 4.0 * bar
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if seconds(mid) < t else (lo, mid)
        return (lo + hi) / 2

    def q(x: float) -> float:
        return round(x / QUANT) * QUANT

    tonic_pc = params.tonic % 12
    flats = tonic_pc in (5, 10, 3, 8, 1)  # F, Bb, Eb, Ab, Db
    names = NAMES_FLAT if flats else NAMES_SHARP
    mode = {"ionian": "major", "aeolian": "minor"}.get(params.mode, params.mode)

    sections = [{"name": s.name, "role": s.role, "start": b(s.u0), "end": b(s.u1),
                 "bars": [int(b(s.u0) // per_beat) + 1, int(b(s.u1) // per_beat)], "parts": s.parts}
                for s in ctx.sections]
    chords = []
    for c in ctx.chords:
        info = chord_info(ctx, c.symbol)
        chords.append({"start": b(c.u0), "end": b(c.u1), "roman": c.symbol, **info,
                       "name": chord_name(info["root"], info["quality"], flats)})

    # The tune: realize()'s melody entries (the same notes as the band's Context has them, with their words).
    melody, lines = [], []
    k, line = 0, None
    for m, t in zip(laid["melody"], ctx.tune):
        assert abs(m["u"] - t.u0) < 1e-9 and int(m["pitch"]) == t.pitch
        note = {"pitch": int(t.pitch), "start": b(t.u0), "dur": r4((t.u1 - t.u0) / beat), "section": ctx.sections[t.section].name}
        if t.first:  # a phrase's first note: before its bar line, a pickup (a loop starts there)
            note["phraseStart"] = True
        if m["syllable"]:
            text = m["syllable"].replace("*", "")
            word_end = k == m["word_len"] - 1
            k = 0 if word_end else k + 1
            note.update(lyric=text + ("" if word_end else "-"), wordEnd=word_end)
            if line is None:
                line = {"start": note["start"], "words": []}
            line["words"].append(text + ("" if word_end else "-"))
            if m["line_end"]:
                note["lineEnd"] = True
                line["end"] = note["start"] + note["dur"]
                lines.append({"start": line["start"], "end": line["end"],
                              "text": " ".join(line["words"]).replace("- ", "")})
                line = None
        else:
            k = 0
            played = [p for p, what in ctx.sections[t.section].parts.items() if what == "lead"]
            note["by"] = played[0] if played else "band"
            note["octave"] = 12 if played and played[0] in ("whistle", "fiddle", "lute") else 0
        melody.append(note)

    # The turns: no tune of their own; an instrument quotes a line (songbird.band's "quote"), which the right
    # hand takes, an octave down, snapped back onto the grid.
    score_notes = laid["score"].notes
    for i, s in enumerate(ctx.sections):
        quoting = [p for p, what in s.parts.items() if what == "quote"]
        if not quoting:
            continue
        part = quoting[0]
        tune = [(t.u0, t.u1) for t in ctx.tune if t.section == i]  # the next section's pickup may sit here
        found = [n for n in score_notes if n.part == part and n.section == s.name and n.art != "cut" and n.dur > 0.08
                 and s.u0 - 0.5 <= unit_at(n.start) < s.u1]
        for n in found:
            u0 = unit_at(n.start)
            if any(a - 0.5 <= u0 < z for a, z in tune):
                continue
            start = q(b(u0))
            dur = max(QUANT, q(b(unit_at(n.start + n.dur)) - b(u0)))
            melody.append({"pitch": int(round(n.pitch)) - 12, "start": start, "dur": dur, "section": s.name,
                           "by": part, "octave": 12, **({"phraseStart": True} if n is found[0] else {})})
    melody.sort(key=lambda n: n["start"])

    # Left hand: the band's bass as heard, an octave up.
    bass = []
    for n in score_notes:
        if n.part != "bass" or n.art == "cut":
            continue
        start = q(b(unit_at(n.start)))
        dur = max(QUANT, q(b(unit_at(n.start + n.dur)) - b(unit_at(n.start))))
        bass.append({"pitch": int(round(n.pitch)) + 12, "start": start, "dur": dur})
    end_beat = b(ctx.end)
    for n in bass:  # the last notes ring to the end, not into the ring-out's seconds
        n["dur"] = r4(min(n["dur"], end_beat - n["start"])) or QUANT

    # ...and parts made from the chords.
    def root_in(pc: int, lo: int = 43) -> int:  # the root between G2 and F#3
        return lo + (pc - lo) % 12

    fifths, folk, block = [], [], []
    prev = None
    for c in chords:
        root = root_in(c["root"])
        third = root + (3 if c["quality"] in ("min", "dim") else 4)
        fifth = root + (6 if c["quality"] == "dim" else 8 if c["quality"] == "aug" else 7)
        span = c["end"] - c["start"]
        hits = [c["start"]] + ([c["start"] + 2] if span >= 4 else [])
        for i, h in enumerate(hits):
            d = (hits[i + 1] if i + 1 < len(hits) else c["end"]) - h
            fifths += [{"pitch": root, "start": h, "dur": d}, {"pitch": fifth, "start": h, "dur": d}]
        pattern = [root, fifth, root + 12, fifth] if span >= 4 else [root, fifth]
        for j in range(int(span)):
            folk.append({"pitch": pattern[j % len(pattern)], "start": c["start"] + j, "dur": 1})
        # block: the triad's inversion nearest the last chord's, between A2 and B3 (under the tune's low A3-B3)
        options = []
        for inv in range(3):
            tones = sorted([root, third, fifth])
            for _ in range(inv):
                tones = tones[1:] + [tones[0] + 12]
            for shift in (-12, 0, 12):
                v = [p + shift for p in tones]
                if 45 <= v[0] and v[-1] <= 59:
                    options.append(v)
        voicing = min(options, key=lambda v: (sum(abs(a - p) for a, p in zip(v, prev)) if prev else abs(v[0] - 50), v[0]))
        prev = voicing
        block += [{"pitch": p, "start": c["start"], "dur": span} for p in voicing]
    for part in (fifths, folk, block):
        for n in part:
            n["dur"] = r4(n["dur"])

    rit = {"from": b(clock.rit_start), "to": b(clock.end), "amount": params.ritardando}
    record = laid["record"]
    first_bar = clock.seconds(clock.lead)
    return {
        "title": genome.title,
        "source": {
            "file": "renders/review/contest.flac", "id": record.get("id"), "program_sha256": record.get("program_sha256"),
            "rendered": COMMAND, "exporter": "tools/piano_score.py",
            "note": "laid again from the packet with its own program (grid positions, before the phrasing and the "
                    "human jitter); see the exporter's docstring",
        },
        "tempo": params.tempo,
        "timeSignature": [per_beat, 4],
        "key": {"tonic": names[tonic_pc], "tonicPc": tonic_pc, "tonicMidi": params.tonic, "mode": mode,
                "flats": flats},
        "ritardando": rit,
        "tempos": [[r4(x), round(params.tempo / (1 + rit["amount"] * (x - rit["from"]) / (rit["to"] - rit["from"])), 2)]
                   for x in [rit["from"] + i for i in range(int(rit["to"] - rit["from"]) + 1)]],
        "audio": {"firstBarSeconds": round(first_bar, 4), "duration": record.get("duration"),
                  "ring": round(laid["score"].duration - clock.seconds(clock.end), 3)},
        "bars": int(round(end_beat / per_beat)),
        "pickup": -melody[0]["start"] if melody and melody[0]["start"] < 0 else 0,
        "end": end_beat,
        "sections": sections,
        "chords": chords,
        "melody": melody,
        "lines": lines,
        "left": {
            "bass": {"label": "Bass line (the band's, an octave up)", "notes": bass},
            "fifths": {"label": "Root and fifth", "notes": fifths},
            "folk": {"label": "Broken chords (root, fifth, octave)", "notes": folk},
            "block": {"label": "Block chords", "notes": block},
        },
    }


# --- checking the score against the recording ---------------------------------------------------------------


def chroma(audio, rate: int, hop: float = 0.05, size: int = 8192):
    """Pitch-class energy every `hop` seconds (a plain STFT folded onto 12 classes, 60 Hz to 2 kHz)."""
    import numpy as np

    step = int(rate * hop)
    window = np.hanning(size)
    freqs = np.fft.rfftfreq(size, 1 / rate)
    band = (freqs > 60) & (freqs < 2000)
    pcs = np.round(12 * np.log2(freqs[band] / 440.0) + 69).astype(int) % 12
    frames = []
    for i in range(0, len(audio) - size, step):
        mag = np.abs(np.fft.rfft(audio[i:i + size] * window))[band]
        frames.append(np.bincount(pcs, weights=mag, minlength=12))
    return np.array(frames), step / rate + 0.0, size / 2 / rate


def check(flac: Path, laid: dict, data: dict) -> bool:
    """Does the recording bear the score out? Its key, chords, tune and tempo, each against the same score
    moved up or down (a wrong key would score better somewhere else)."""
    import numpy as np
    import soundfile as sf

    audio, rate = sf.read(str(flac), dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    frames, hop, centre = chroma(audio, rate)
    times = np.arange(len(frames)) * hop + centre
    seconds, lead, beat = laid["seconds"], laid["lead"], laid["ctx"].beat

    def at(b: float) -> float:  # beats -> seconds in the recording (the score's own clock)
        return seconds(lead + b * beat)

    def span(t0: float, t1: float):
        sel = (times >= t0) & (times < t1)
        return frames[sel].mean(axis=0) if sel.any() else np.zeros(12)

    ok = True
    print(f"recording: {len(audio) / rate:.3f} s; the record says {laid['record'].get('duration')} s; "
          f"the score's last note ends (rings out) at {laid['score'].duration:.3f} s")

    # the key: the whole recording's chroma against the score's own pitch classes (every pitched note, weighted
    # by how long it sounds), moved by -6..+6 semitones. (A key profile alone can't tell a major pentatonic tune
    # from the major key a fifth above, which lacks nothing the tune uses; it is printed for what it's worth.)
    total = frames.sum(axis=0)
    content = np.zeros(12)
    for n in laid["score"].notes:
        if n.part not in ("drum",):
            content[int(round(n.pitch)) % 12] += n.dur
    fits = {k: float(np.corrcoef(total, np.roll(content, k))[0, 1]) for k in range(-6, 7)}
    major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    profile = max(range(12), key=lambda k: np.corrcoef(total, np.roll(major, k))[0, 1])
    print(f"key: the recording's pitch classes fit the score's notes as written with r={fits[0]:.2f}, moved by a "
          f"semitone or more at best r={max(v for k, v in fits.items() if k):.2f} (the score: "
          f"{data['key']['tonic']} {data['key']['mode']}; a major-key profile alone says {NAMES_SHARP[profile]})")
    ok &= fits[0] > max(v for k, v in fits.items() if k) + 0.1

    # the chords: each chord's span, which of the 24 major and minor triads fits it best, the score moved by
    # -6..+6 semitones
    triads = [(r, qual, np.isin(np.arange(12), [r, (r + (4 if qual == "maj" else 3)) % 12, (r + 7) % 12]).astype(float))
              for r in range(12) for qual in ("maj", "min")]
    spans = [span(at(c["start"]) + 0.05, at(c["end"])) for c in data["chords"]]
    fitted = [max(triads, key=lambda t: float(v @ t[2])) for v in spans]
    agree = {shift: sum(f[0] == (c["root"] + shift) % 12 and f[1] == c["quality"] for c, f in zip(data["chords"], fitted))
             / len(spans) for shift in range(-6, 7)}
    print(f"chords: the recording's best-fitting triad is the score's in {agree[0]:.0%} of {len(spans)} chord spans; "
          f"moved by a semitone or more, at most {max(v for s, v in agree.items() if s):.0%}")
    ok &= agree[0] > 0.6 and agree[0] > max(v for s, v in agree.items() if s) + 0.3

    # the tune: each sung note's pitch class among the recording's strongest while it is sung (the voice's own
    # timing, from the score's voice part)
    voice = [n for n in laid["score"].notes if n.part == "voice" and n.dur >= 0.3]
    ranks = {}
    for shift in range(-6, 7):
        top = 0
        for n in voice:
            v = span(n.start + 0.08, n.start + n.dur)
            top += (int(round(n.pitch)) + shift) % 12 in np.argsort(v)[-3:]
        ranks[shift] = top / len(voice)
    print(f"tune: a sung note's pitch class is among the recording's three strongest in {ranks[0]:.0%} of "
          f"{len(voice)} notes; moved by a semitone or more, at most {max(v for s, v in ranks.items() if s):.0%}")
    ok &= ranks[0] > 0.7

    # the rhythm: the recording's onsets (spectral flux, every 10 ms) repeat at the score's beat, and fall on
    # its beats rather than between them
    size, step = 2048, rate // 100
    window = np.hanning(size)
    spectra = np.array([np.log1p(np.abs(np.fft.rfft(audio[i:i + size] * window))[:size // 4])
                        for i in range(0, len(audio) - size, step)])
    onset = np.maximum(np.diff(spectra, axis=0), 0).sum(axis=1)
    onset -= onset.mean()
    ac = np.correlate(onset, onset, "full")[len(onset) - 1:]
    lo, hi = int(0.4 * 100), int(1.0 * 100)
    i = lo + int(np.argmax(ac[lo:hi]))
    a, b0, c = ac[i - 1], ac[i], ac[i + 1]  # the peak between samples, by a parabola through three
    period = (i + 0.5 * (a - c) / (a - 2 * b0 + c)) / 100
    print(f"tempo: the recording's onsets repeat every {period:.3f} s ({60 / period:.1f} bpm); the score says "
          f"{data['tempo']:g} bpm ({60 / data['tempo']:.3f} s)")
    ok &= abs(60 / period - data["tempo"]) < 2
    flux = onset
    hop, centre = 0.01, size / 2 / rate
    on = [flux[int((at(x) - centre) / hop)] for x in np.arange(0, data["ritardando"]["from"], 1.0)]
    off = [flux[int((at(x + 0.5) - centre) / hop)] for x in np.arange(0, data["ritardando"]["from"], 1.0)]
    print(f"beats: onset strength on the score's beats {np.mean(on):.3f}, halfway between them {np.mean(off):.3f}")
    ok &= np.mean(on) > np.mean(off)
    print("the score matches the recording" if ok else "THE SCORE AND THE RECORDING DISAGREE somewhere above")
    return bool(ok)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("flac", nargs="?", default=str(RELEASE), help="a packed render (default: the release)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true", help="check the score against the recording's audio")
    args = ap.parse_args()
    flac = Path(args.flac)
    with tempfile.TemporaryDirectory() as tmp:
        laid = lay(flac, Path(tmp))
        data = export(laid)
        if args.check and not check(flac, laid, data):
            raise SystemExit(1)
    if flac.resolve() != RELEASE.resolve():
        data["source"]["file"] = str(flac)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n")
    sung = sum(1 for n in data["melody"] if "lyric" in n)
    print(f"{out}: {data['title']}, {data['key']['tonic']} {data['key']['mode']}, {data['tempo']:g} bpm, "
          f"{data['bars']} bars, {len(data['sections'])} sections, {len(data['melody'])} tune notes ({sung} sung), "
          f"{len(data['chords'])} chords, {len(data['lines'])} lines")


if __name__ == "__main__":
    main()
