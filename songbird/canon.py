"""A round: a section sung by voices coming in one after another on the same tune (docs/ARRANGE.md, "A round",
2026-09-30).

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

from dataclasses import dataclass

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
    """Lines as one voice sings them from `start` (grid units): [onset, end, semitones from the tonic], a held
    note giving way to the next line's pickup."""
    from .theory import degree_semitones

    notes, t0 = [], start
    for pid in pids:
        p = genome.phrases[pid]
        for n in p.sung:
            notes.append([t0 + n.onset, t0 + n.onset + n.dur, degree_semitones(n.degree, mode, n.alter)])
        t0 += p.bars * genome.meter.bar
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
    return out


def _weight(meter, a: float, b: float) -> float:
    w = (b - a) / meter.beat
    return w if (b - a) >= meter.beat or a % meter.foot == 0 else w / 3.0


def _against(meter, notes, chords, mode: str) -> float:
    """Beats of notes a semitone from their chord's triad and not its tones (style.tune_clash's measure)."""
    from .style import _chord_pcs

    bad = 0.0
    for a0, a1, p in notes:
        for c0, c1, symbol in chords:
            s, e = max(a0, c0), min(a1, c1)
            if e <= s:
                continue
            triad, whole = _chord_pcs(symbol, mode), _chord_pcs(symbol, mode, triad=False)
            pc = p % 12
            if pc in whole or not any(min((pc - t) % 12, (t - pc) % 12) == 1 for t in triad):
                continue
            bad += _weight(meter, s, e)
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
            for a0, a1, pa in sung[i]:
                for b0, b1, pb in sung[j]:
                    s, e = max(a0, b0), min(a1, b1)
                    if e <= s:
                        continue
                    w = _weight(meter, s, e)
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
