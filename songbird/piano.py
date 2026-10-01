"""A rendition's score for learning it at the piano: the page in songbird/studio/piano/ (docs/PIANO.md).

    lay(genome, params, ...)       the rendition laid out again, as the grid has it (no audio)
    export(laid, source)           the page's score.json: tempo, key, sections, chords, the tune with its words,
                                   the lines, and left-hand parts, in beats from the first bar line

Two things feed it. tools/piano_score.py writes the released rendition's score for the public page, laying it
with the release's own program (so later changes can't move a note) and checking it against the recording.
The studio (songbird/studio.py, /api/piano) writes the version on its page, with the person's key, tempo,
chords, words, form and tune, from this program. Both hand `export` the same things.

realize() works on a grid (an eighth note a unit in H) and then turns it into seconds with the rendition's
clock, adding the phrasing's pushes and pulls and a little human jitter. For a player the grid is the truth,
so this takes the grid itself: the band's Context (songbird.band.overheard: the song laid out in grid units,
sections, the chord under every beat, the tune note by note) and realize()'s melody entries, each with its
syllable. Nothing is changed; listening only keeps references.

What goes in (positions and lengths in beats, a beat a quarter note, 0 at the first bar line of the song; the
pickup before it is negative; bar n starts at beat 4(n-1)):
- tempo, time signature, key (the rendition's tonic and mode), and the final phrase's ritardando: the clock's
  seconds(b) = 60/bpm * (b + amount * x^2 / (2 * span)), x = beats past its start (songbird.realize.Clock);
- sections (name, bars) and the chords (roman numeral, root, quality, name in the song's key; a bass other than
  the root, for a person's inversion) as the band plays them: each tune line's chords split evenly through
  each bar, as songbird.band lays them;
- the melody: every tune note with its syllable. Where nobody sings, the band's lead states the tune (H's
  intro, on the whistle an octave up) and it is given at the sung pitch; the turns' instrumental quotes (the
  fiddle, then the lute, an octave above the voice) are taken from the band's notes, quantized back onto the
  grid (a sixteenth) through the inverse clock, their grace notes ("cut") left out, and given an octave down;
- left-hand parts. The band has no keyboard (lute, guitar, harp, bass, fiddle, whistle, drum, drone), so:
  "bass": the band's bass line as heard, quantized the same way, an octave up (in reach of a 61-key keyboard);
  "fifths": root and fifth together at each chord and on beat 3 of a bar-long chord;
  "folk": a broken-chord pattern, root-fifth-octave-fifth in quarters (root-fifth over a two-beat chord);
  "block": the chord's triad held, each voiced nearest the last, between A2 and B3.
  An inversion's bass (a person's G/B) is the lowest note of "fifths" and "folk".
- a style's lift (the last refrain a whole step up) is in the notes and chords, and said as `lift`.
Every part is the notes as written, in the rendition's own key; the page transposes.

Standard library only (and the package).
"""

from __future__ import annotations

# bound when this module loads: tools/piano_score.py imports it before the release's own (older) program takes
# the songbird name, and the spelling is this tree's (the release's theory has no key_signature)
from .theory import chord_bass, chord_tones, key_signature, spelling

NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
QUANT = 0.25  # beats: a sixteenth, what the band's notes are snapped back to
QUALITY = {(4, 7): "maj", (3, 7): "min", (3, 6): "dim", (4, 8): "aug", (5, 7): "sus4", (2, 7): "sus2",
           # a person's chords with a fourth tone (theory.QUALITIES), by their tones above the root
           (4, 7, 10): "7", (4, 7, 11): "maj7", (3, 7, 10): "m7", (3, 6, 10): "m7b5", (3, 6, 9): "dim7",
           (4, 7, 9): "6", (3, 7, 9): "m6", (4, 7, 2): "add9", (3, 7, 2): "madd9", (5, 7, 10): "7sus4",
           (2, 7, 10): "7sus2"}
SUFFIX = {"maj": "", "min": "m", "dim": "dim", "aug": "+", "sus4": "sus4", "sus2": "sus2", "7": "7", "maj7": "maj7",
          "m7": "m7", "m7b5": "m7b5", "dim7": "dim7", "6": "6", "m6": "m6", "add9": "add9", "madd9": "m(add9)",
          "7sus4": "7sus4", "7sus2": "7sus2"}
BASS_LEFT = "Bass line (the band's, an octave up)"


def lay(genome, params, phrasing=None, choir=(), lyrics=None) -> dict:
    """The rendition laid out again with this program, as `export` wants it: the score (realize, then
    variation.lay, as a render has it), the band's Context, realize()'s melody entries and clock."""
    from . import band, variation
    from .realize import realize, timeline

    with band.overheard() as heard:
        score = variation.lay(realize(genome, params, phrasing=phrasing, choir=list(choir), lyrics=lyrics), params)
    if "ctx" not in heard:
        raise RuntimeError("the band didn't lay the song out; there is no score to learn from")
    return {"genome": genome, "params": params, "score": score, "ctx": heard["ctx"],
            "melody": sorted(heard["melody"], key=lambda m: m["u"]), "seconds": heard["seconds"],
            "lead": heard["lead"], "end": heard["end"], "clock": timeline(genome, params)}


def chord_info(ctx, symbol: str) -> dict:
    """A chord's root (a pitch class) and quality; its bass too, where a person put another tone there."""
    tones = chord_tones(symbol, ctx.mode)
    r = tones[0]
    info = {"root": (ctx.tonic + r) % 12, "quality": QUALITY.get(tuple((x - r) % 12 for x in tones[1:]), "maj")}
    bass = chord_bass(symbol, ctx.mode)
    if bass % 12 != r % 12:
        info["bass"] = (ctx.tonic + bass) % 12
    return info


def ascii_spelling(tonic: int, mode: str) -> list[str]:
    """The key's twelve names (theory.spelling: G♯ in C♯ minor, E♯ in C♯ major) as the piano page writes them."""

    return [n.replace("𝄪", "x").replace("𝄫", "bb").replace("♯", "#").replace("♭", "b") for n in spelling(tonic, mode)]


def chord_name(root: int, quality: str, flats: bool | list, bass: int | None = None) -> str:
    names = flats if isinstance(flats, list) else NAMES_FLAT if flats else NAMES_SHARP
    return names[root % 12] + SUFFIX[quality] + (f"/{names[bass % 12]}" if bass is not None else "")


def r4(x: float) -> float:
    return round(x * 4) / 4 if abs(x * 4 - round(x * 4)) < 1e-6 else round(x, 4)


def bass_part(parts) -> str | None:
    """Which of the band's parts plays the bass line: the ballad's bass, or a style's (an electric bass, a
    synth bass)."""
    from .synth.instruments import spec

    if "bass" in parts:
        return "bass"
    for part in parts:
        try:
            if spec(part)["family"] == "bass":
                return part
        except (ValueError, KeyError):
            continue
    return None


def export(laid: dict, source: dict, duration: float | None = None) -> dict:
    """The page's score.json from a laid rendition (`lay`, or tools/piano_score.py's from a packet).
    source: where it came from, as the page says it; duration: the audio's, if there is a recording."""
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

    flats = key_signature(params.tonic, params.mode) < 0  # spelt by the key's signature (theory.spelling)
    names = ascii_spelling(params.tonic, params.mode)
    mode = {"ionian": "major", "aeolian": "minor"}.get(params.mode, params.mode)
    score_notes = laid["score"].notes

    # a style's lift: from the last refrain's first bar line (its pickup too) everything is a whole step up
    lift = None
    if getattr(getattr(params, "style", None), "lift", False):
        from .style import lifted

        at = lifted(genome, laid["score"])
        if at is not None:
            lift = r4(b(unit_at(at)))
    lifted_names = {s.name for s in ctx.sections if lift is not None and b(s.u0) >= lift - 1e-6}

    def up(start: float, section: str | None = None, sung: bool = False) -> int:
        if lift is None:
            return 0
        return 2 if start >= lift - 1e-6 or (sung and section in lifted_names and start >= lift - 1.5) else 0

    sections = [{"name": s.name, "role": s.role, "start": b(s.u0), "end": b(s.u1),
                 "bars": [int(b(s.u0) // per_beat) + 1, int(b(s.u1) // per_beat)], "parts": s.parts}
                for s in ctx.sections]
    chords = []
    for c in ctx.chords:
        info = chord_info(ctx, c.symbol)
        shift = up(b(c.u0))
        if shift:
            info = {k: (v + shift) % 12 if k in ("root", "bass") else v for k, v in info.items()}
        chords.append({"start": b(c.u0), "end": b(c.u1), "roman": c.symbol, **info,
                       "name": chord_name(info["root"], info["quality"], names, info.get("bass"))})

    # The tune: realize()'s melody entries (the same notes as the band's Context has them, with their words).
    melody, lines = [], []
    k, line = 0, None
    for m, t in zip(laid["melody"], ctx.tune):
        assert abs(m["u"] - t.u0) < 1e-9 and int(m["pitch"]) == t.pitch
        section = ctx.sections[t.section].name
        # (a pickup is its own line's, which a lift takes up with it: realize's section, not where it sits)
        note = {"pitch": int(t.pitch) + up(b(t.u0), m.get("section"), True), "start": b(t.u0),
                "dur": r4((t.u1 - t.u0) / beat), "section": section}
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
            played = [p for p, what in ctx.sections[t.section].parts.items() if what in ("lead", "parlour")]
            note["by"] = played[0] if played else "band"
            note["octave"] = 12 if played and played[0] in ("whistle", "fiddle", "lute") else 0
        melody.append(note)

    # The turns: no tune of their own; an instrument quotes a line (songbird.band's "quote"), which the right
    # hand takes, an octave down, snapped back onto the grid.
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
    playing = list(dict.fromkeys(n.part for n in score_notes))
    low = bass_part(playing)
    bass = []
    for n in score_notes:
        if n.part != low or n.art == "cut":
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
        r, t, f = chord_tones(c["roman"], ctx.mode)[:3]  # the triad, a person's seventh named on the chord
        third, fifth = root + (t - r) % 12, root + (f - r) % 12
        under = root_in(c["bass"]) if "bass" in c else root  # an inversion's bass, below the chord
        span = c["end"] - c["start"]
        hits = [c["start"]] + ([c["start"] + 2] if span >= 4 else [])
        for i, h in enumerate(hits):
            d = (hits[i + 1] if i + 1 < len(hits) else c["end"]) - h
            fifths += [{"pitch": under, "start": h, "dur": d}, {"pitch": fifth, "start": h, "dur": d}]
        pattern = [under, fifth, root + 12, fifth] if span >= 4 else [under, fifth]
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
    first_bar = clock.seconds(clock.lead)
    left = {}
    if bass:
        left["bass"] = {"label": BASS_LEFT if low == "bass" else f"Bass line (the band's {low.replace('-', ' ')}, "
                                                                 "an octave up)", "notes": bass}
    left |= {
        "fifths": {"label": "Root and fifth", "notes": fifths},
        "folk": {"label": "Broken chords (root, fifth, octave)", "notes": folk},
        "block": {"label": "Block chords", "notes": block},
    }
    out = {
        "title": genome.title,
        "source": source,
        "tempo": params.tempo,
        "timeSignature": [per_beat, 4],
        "key": {"tonic": names[tonic_pc], "tonicPc": tonic_pc, "tonicMidi": params.tonic, "mode": mode,
                "flats": flats},
        "ritardando": rit,
        "tempos": [[r4(x), round(params.tempo / (1 + rit["amount"] * (x - rit["from"]) / (rit["to"] - rit["from"])), 2)]
                   for x in [rit["from"] + i for i in range(int(rit["to"] - rit["from"]) + 1)]]
        if rit["to"] > rit["from"] else [],
        "audio": {"firstBarSeconds": round(first_bar, 4), "duration": duration,
                  "ring": round(laid["score"].duration - clock.seconds(clock.end), 3)},
        "bars": int(round(end_beat / per_beat)),
        "pickup": -melody[0]["start"] if melody and melody[0]["start"] < 0 else 0,
        "end": end_beat,
        "sections": sections,
        "chords": chords,
        "melody": melody,
        "lines": lines,
        "left": left,
    }
    if lift is not None:
        out["lift"] = {"at": lift, "by": 2}
    return out
