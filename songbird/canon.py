"""A round: a section sung by voices coming in one after another on the same tune (docs/ARRANGE.md, "A round").

The singer starts the section; the lineage's voices (the choir, the parent's first), else the program's own, come
in after it on the same tune and the same words, each panned apart; at the end they drop out in turn, each
finishing its own last line, the band under them following the voice furthest along. A person asks for it
(arrange.<section>:<n>.round); nothing draws it.

A round needs a tune whose lines sit over each other's harmony, and most folk tunes don't at every distance.
fit() says where this one does, in the version's mode: each way of singing it scored by the clash between the
overlapping voices (a semitone or a tritone apart: on a strong beat or held a beat counted whole, a passing one
a third, as style.tune_clash counts) and between each later voice and the chords the band plays under it, beyond
what the tune has with its own chords. The whole section a line apart first, then two lines apart; where neither
fits, its last line as a round (the voices come in half a line apart on it, a tag over the section's end).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

VOICES = (2, 3, 4)  # how many may sing a round, the singer among them
DEFAULT = 3  # "a round" asked for without a number: the singer and two more, where the tune takes three
TAG_VOICES = 3  # its last line as a round: three voices half a line apart, the third ending a line after the singer
SLACK_VOICES = 1.0  # beats of semitone or tritone between the voices a round may have...
SHARE_VOICES = 1 / 16  # ...and at most this share of the beats they sing together
SLACK_BAND = 2.0  # beats of clash with the band's chords beyond the tune's own (as style.LOOP_SLACK)
DISTANCES = (1, 2)  # a whole section's voices come in a line or two lines apart


@dataclass(frozen=True)
class Round:
    """How a section is sung as a round: `voices` (the singer first), each coming in `distance` grid units after
    the one before, singing the section from its line `first` (0: all of it; its last: a tag over its end); and
    the lines the band plays after the section's own while the later voices finish (`under`)."""

    voices: int
    distance: int
    first: int
    under: tuple

    @property
    def whole(self) -> bool:
        return self.first == 0


def _lines(genome, name: str):
    return [genome.phrases[p] for p in genome.section(name).phrases]


def _sung(genome, pids, start: float, mode: str) -> list[list]:
    """Lines as one voice sings them from `start` (grid units): [onset, end, semitones from the tonic, strong], a
    held note giving way to the next line's pickup; strong: on a foot or a beat long or more (as tune_clash
    weighs a note)."""
    from .theory import degree_semitones

    notes, t0, m = [], start, genome.meter
    for pid in pids:
        p = genome.phrases[pid]
        for n in p.sung:
            notes.append([t0 + n.onset, t0 + n.onset + n.dur, degree_semitones(n.degree, mode, n.alter),
                          n.dur >= m.beat or n.onset % m.foot == 0])
        t0 += p.bars * m.bar
    notes.sort()
    for a, b in zip(notes, notes[1:]):
        a[1] = min(a[1], b[0])
    return notes


def _chords(genome, pids, start: float) -> list[tuple]:
    out, t0, m = [], start, genome.meter
    for pid in pids:
        p = genome.phrases[pid]
        for b, in_bar in enumerate(p.chords):
            for k, symbol in enumerate(in_bar):
                a = t0 + b * m.bar + k * m.bar // len(in_bar)
                out.append((a, a + m.bar // len(in_bar), symbol))
        t0 += p.bars * m.bar
    if out:  # a pickup before the first bar line sings over the first bar's chord (as tune_clash has it)
        out[0] = (float("-inf"), *out[0][1:])
    return out


def _weight(meter, a: float, b: float, strong: bool) -> float:
    """Beats of an overlap from a to b, counted whole where a note in it is strong, a third where none is."""
    w = (b - a) / meter.beat
    return w if strong else w / 3.0


def _against(meter, notes, chords, mode: str) -> float:
    """Beats of notes a semitone from their chord's triad and not its tones (style.tune_clash's measure)."""
    from .style import _chord_pcs

    bad = 0.0
    for a0, a1, p, strong in notes:
        for c0, c1, symbol in chords:
            s, e = max(a0, c0), min(a1, c1)
            if e <= s:
                continue
            triad, whole = _chord_pcs(symbol, mode), _chord_pcs(symbol, mode, triad=False)
            pc = p % 12
            if pc in whole or not any(min((pc - t) % 12, (t - pc) % 12) == 1 for t in triad):
                continue
            bad += _weight(meter, s, e, strong)
    return bad


def under(genome, name: str, voices: int, lines_apart: int) -> tuple:
    """A whole section's tail: the lines the band plays after the section's own while the later voices finish,
    each the line the voice furthest along is singing (for three voices a line apart, the last line twice)."""
    own = list(genome.section(name).phrases)
    out = []
    for j in range((voices - 1) * lines_apart):
        e = j // lines_apart + 1  # the first voice still singing
        out.append(own[len(own) - e * lines_apart + j])
    return tuple(out)


def candidates(genome, name: str) -> list[Round]:
    """Every way the section could be sung as a round, in the order a choice prefers them: the whole section a
    line apart and two lines apart (four voices, three, two), then its last line, three voices half a line apart."""
    own = list(genome.section(name).phrases)
    line = genome.phrases[own[0]].bars * genome.meter.bar
    out = []
    for voices in sorted(VOICES, reverse=True):
        for apart in DISTANCES:
            if (voices - 1) * apart < len(own):
                out.append(Round(voices, apart * line, 0, under(genome, name, voices, apart)))
    half = genome.phrases[own[-1]].bars // 2 * genome.meter.bar
    if half and genome.phrases[own[-1]].bars % 2 == 0:
        out.append(Round(TAG_VOICES, half, len(own) - 1, (own[-1],) * ((TAG_VOICES - 1) * half // line)))
    return out


def clash(genome, name: str, plan: Round, mode: str) -> dict:
    """A round's clash in a section (the band playing the section's lines, then plan.under). {"voices": beats of
    semitones and tritones between the voices, "band": beats of the later voices' notes a semitone off the band's
    chords, "own": the same for the lines they sing under their own chords (as many times as they sing them),
    "seconds": beats a whole tone apart (milder: said, not counted), "overlap": beats sung together}."""
    meter = genome.meter
    own = list(genome.section(name).phrases)
    starts = [0]
    for pid in own:
        starts.append(starts[-1] + genome.phrases[pid].bars * meter.bar)
    sung = [_sung(genome, own, 0, mode)]
    sung += [_sung(genome, own[plan.first:], starts[plan.first] + e * plan.distance, mode)
             for e in range(1, plan.voices)]
    band = _chords(genome, own + list(plan.under), 0)
    between = seconds = overlap = 0.0
    for i in range(plan.voices):
        for j in range(i + 1, plan.voices):
            for a0, a1, pa, strong_a in sung[i]:
                for b0, b1, pb, strong_b in sung[j]:
                    s, e = max(a0, b0), min(a1, b1)
                    if e <= s:
                        continue
                    w = _weight(meter, s, e, strong_a or strong_b)
                    overlap += w
                    interval = (pa - pb) % 12
                    if interval in (1, 11, 6):
                        between += w
                    elif interval in (2, 10):
                        seconds += w
    alone = _against(meter, _sung(genome, own[plan.first:], starts[plan.first], mode),
                     _chords(genome, own[plan.first:], starts[plan.first]), mode)
    later = sum(_against(meter, sung[e], band, mode) for e in range(1, plan.voices))
    return {"voices": round(between, 3), "band": round(later, 3), "own": round(alone * (plan.voices - 1), 3),
            "seconds": round(seconds, 3), "overlap": round(overlap, 3)}


def fits(score: dict) -> bool:
    """A round that sits: its voices a semitone or a tritone apart for at most a beat, and at most one beat in
    sixteen of what they sing together (a tag's short overlap allows a third of a beat); the band's chords under the
    later voices no more than SLACK_BAND beats worse than the tune's own."""
    allowed = min(SLACK_VOICES, SHARE_VOICES * score["overlap"])
    return score["voices"] <= allowed + 1e-9 and score["band"] - score["own"] <= SLACK_BAND + 1e-9


def roundable(genome, name: str) -> bool:
    """A section a round can sing at all: words, on two lines or more of one length, each with a tune."""
    section = genome.section(name)
    lines = _lines(genome, name)
    return bool(section.lyrics) and len(lines) >= 2 and len({p.bars for p in lines}) == 1 \
        and all(p.sung for p in lines)


_FITS: dict = {}  # fit()'s answers, by the section's lines and the mode


def fit(genome, name: str, mode: str | None = None) -> list[Round]:
    """The ways this section's tune takes a round in this mode (the song's own by default), in the order a
    choice prefers them; [] where none fits (or the section isn't one a round can sing)."""
    if not roundable(genome, name):
        return []
    mode = mode or genome.seed_params.get("mode", "ionian")
    key = (genome.meter, tuple((p.tune, p.chords) for p in _lines(genome, name)), mode)
    if key not in _FITS:
        if len(_FITS) > 256:
            _FITS.clear()
        _FITS[key] = [plan for plan in candidates(genome, name) if fits(clash(genome, name, plan, mode))]
    return list(_FITS[key])


def choose(genome, name: str, asked, mode: str | None = None) -> Round | None:
    """The round a person's choice asks for in a section: the whole section with that many voices (true: three,
    else two), a line apart where that fits, else two lines; where no whole round fits, its last line as a round
    (three voices, whatever the number asked). None where nothing fits."""
    found = fit(genome, name, mode)
    wanted = (DEFAULT, 2) if asked is True else (int(asked),)
    for voices in wanted:
        plan = next((p for p in found if p.whole and p.voices == voices), None)
        if plan is not None:
            return plan
    return next((p for p in found if not p.whole), None)


# ---------------------------------------------------------------- in a version (songbird.takeover, realize, idioms)


def plans(genome, params) -> list[Round | None]:
    """Each section of the form's round, as a person asked for it (arrange.<section>:<n>.round) and this
    version's mode and chords let it be sung; None where there is none (and everywhere, with nobody asking)."""
    from .takeover import arranged

    held = arranged(params)
    if not held or not any("round" in entry for entry in held.values()):
        return [None] * len(params.form)
    from .composition import harmonized, section_ids

    genome = harmonized(genome, params)  # a person's chords, which the band plays under the voices
    own = params.composition.get("own")
    keys = None
    out = []
    for k, (sid, name) in enumerate(zip(section_ids(params.form), params.form)):
        entry = held.get(sid) or {}
        asked = entry.get("round")
        if not asked or entry.get("bars") is not None or entry.get("sung") is False:
            out.append(None)
            continue
        if own and keys is None:
            from .composition import own_keys

            keys = own_keys(genome, params)
        song, names = _with_own(genome, name, own.get(keys[k]) if own and keys[k] else None)
        plan = choose(song, name, asked, params.mode)
        out.append(replace(plan, under=tuple(names.get(p, p) for p in plan.under)) if plan and names else plan)
    return out


def _with_own(genome, name: str, lines: dict | None):
    """The song with a section's lines of their own (composition["own"]: {line: entry}) as its tune lines, so a
    round is judged on the notes the voices will sing, and the names those lines are given there ({given: the
    tune line's}); the song itself and {} where it has none. Each line of its own is a tune line of its own name,
    so a section that sings one tune line twice (a verse's v2, v3, v2) has it judged only where it's sung."""
    if not lines:
        return genome, {}
    import json

    from .composition import own_notes

    section = genome.section(name)
    phrases, sections, names, laid = dict(genome.phrases), dict(genome.sections), {}, []
    for j, pid in enumerate(section.phrases):
        entry = lines.get(str(j))
        if entry is None:
            laid.append(pid)
            continue
        given = f"{pid}#own{j}"
        phrases[given] = replace(phrases[pid], id=given, notes=own_notes(entry),
                                 tune="own:" + json.dumps(entry["tune"]))
        names[given] = pid
        laid.append(given)
    sections[name] = replace(section, phrases=tuple(laid))
    return replace(genome, phrases=phrases, sections=sections), names


def lines(genome, name: str, plan: Round, laid=None) -> list[tuple[str, bool]]:
    """A round section's tune lines, as takeover.phrase_plan lays them: its own (or as its style lays them,
    `laid`: house's drop), then the lines the band plays while the later voices finish (no melody there:
    realize lays none)."""
    own = laid if laid is not None else [(pid, True) for pid in genome.section(name).phrases]
    return list(own) + [(pid, False) for pid in plan.under]


VEL = 0.95  # an entry's notes against the singer's (a backing voice's are 0.8 of them: an entry sings the tune)


def entries(ctx, melody: list[dict]) -> list:
    """The later voices of every round in the version, as backing voices (idioms.Sung, voice v the part
    choir{v+1}): the singer's own notes in the section from the round's first line, each voice `distance` later
    than the one before, on the same words and pitches. The oldest comes in first and the parent last (choir1),
    so the voice nearest the singer finishes the round. realize marks the singer's notes in a round (m["round"]:
    the section's place in the form, m["line"]: which of its own lines)."""
    from .idioms import Sung

    rounds = plans(ctx.genome, ctx.params)
    if not any(rounds):
        return []
    out = []
    for k, plan in enumerate(rounds):
        if plan is None:
            continue
        mine = sorted((m for m in melody if m.get("round") == k and m["syllable"] and m["line"] >= plan.first),
                      key=lambda m: m["u"])
        for e in range(1, plan.voices):
            shift, voice = e * plan.distance, plan.voices - 1 - e
            for j, m in enumerate(mine):
                u1 = min(m["u_end"], mine[j + 1]["u"]) if j + 1 < len(mine) else m["u_end"]
                out.append(Sung(voice, m["u"] + shift, u1 + shift, int(m["pitch"]), VEL * float(m["vel"]),
                                m["syllable"], m["word"], m["word_len"], m["line_end"], m["section"], m["phrase"],
                                "round"))
    return out


def spans(ctx) -> list[tuple[float, float]]:
    """Where the version's rounds are sung, in grid units: from the section's first pickup to the end of its
    tail."""
    rounds = plans(ctx.genome, ctx.params)
    out = []
    for k, plan in enumerate(rounds):
        if plan is None:
            continue
        _sid, name, a, b = ctx.spans[k]
        first = ctx.genome.phrases[ctx.genome.section(name).phrases[0]]
        out.append((a - first.pickup, b))
    return out


def sung_until(ctx, sung_end: float) -> float:
    """Where the singing ends: the singer's last note, or a round's last voice after it."""
    return max([sung_end] + [b for _a, b in spans(ctx)]) if any(plans(ctx.genome, ctx.params)) else sung_end


def with_round(ctx, melody: list[dict], sung: list) -> list:
    """Backing voices (idioms.backing's) with the version's rounds in them: nobody else's backing in a round
    section (a held chord running into one stops where it begins), and the round's later voices there. The same
    list where there is no round."""
    if not any(plans(ctx.genome, ctx.params)):
        return sung
    from dataclasses import replace

    where = spans(ctx)
    kept = []
    for s in sung:
        if any(a - 1e-9 <= s.u0 < b - 1e-9 for a, b in where):
            continue
        into = min((a for a, b in where if s.u0 < a < s.u1 - 1e-9), default=None)
        if into is not None:
            if into - s.u0 < ctx.sub - 1e-9:
                continue
            s = replace(s, u1=into)
        kept.append(s)
    return sorted(kept + entries(ctx, melody), key=lambda x: (x.u0, x.voice))
