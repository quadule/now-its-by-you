"""Realization: genome + concrete parameters -> a timed score.

This is the only stage where the genome (what persists), the parent's
parameters (what was inherited), the voice (who is singing) and the drift
(when) meet. choose_params() combines the last three into concrete Params;
realize() walks the genome with them. Milestone 1 realizes fixed parameters;
inheritance, the voice pull and drift arrive with milestones 3 to 5.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace

import numpy as np

from . import band as band_mod
from .band import Band
from .genome import Genome, Phrase, sung_words, turn
from .phrasing import Gesture, Phrasing, gesture
from .score import Note, Score
from .theory import degree_semitones, harmony


@dataclass(frozen=True)
class Params:
    """Everything a rendition decided that the genome leaves open."""

    tonic: int  # MIDI pitch of scale degree 1 in the melody's register
    mode: str
    tempo: float  # beats per minute
    form: tuple[str, ...]  # concrete section order
    seed: int = 0  # seeds every random choice in the rendition
    accomp: str = "0 1 2 3 2 1"  # the harp's picking over the chord voicing, one token per step; . rests
    humanize: float = 0.006  # standard deviation of onset jitter, seconds
    ritardando: float = 0.35  # how much slower the final phrase ends than it began
    choir: int = 0  # voices from the lineage that join in harmony where the genome allows
    band: Band = field(default_factory=Band)  # who plays and how (songbird.band); absent in old params: the defaults

    @classmethod
    def from_dict(cls, data: dict) -> Params:
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        values["form"] = tuple(values["form"])
        if "band" in values:
            values["band"] = values["band"] if isinstance(values["band"], Band) else Band.from_dict(values["band"])
        return cls(**values)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["form"] = list(self.form)
        return data


def choose_params(genome: Genome, parent: Params | None = None) -> Params:
    """Inherit from the parent, pull toward the voice, apply drift.

    Milestone 1: the seed has no parent, so its parameters come from the
    genome's seed_params; a child simply repeats its parent.
    """
    return parent if parent is not None else Params.from_dict(genome.seed_params)


def sung_as(note: Note, g: Gesture | None, beat: float) -> Note:
    """A sung note the way a gesture sings it: g.early beats (of beat seconds)
    ahead of the grid, held for g.hold of its written length, and carrying the
    gesture on to the singer for loudness and pitch."""
    if g is None:
        return note
    start = max(0.0, note.start - g.early * beat)
    let_go = note.start + note.dur * g.hold
    return replace(note, start=start, dur=max(let_go - start, 0.05), gesture=g)


def realize(genome: Genome, params: Params, verses=None, phrasing: Phrasing | None = None,
            choir: list[Phrasing | None] | None = None) -> Score:
    """The timed score. With a phrasing, the voice sings each note its way:
    early or late against the grid, held longer or shorter, and carrying the
    note's gesture on to the singer for loudness and pitch. choir: a phrasing
    for each lineage voice that joins in (None, or missing: that voice follows
    the lead's timing with no gestures of its own)."""
    verses = verses if verses is not None else genome.seed_verses
    meter = genome.meter
    rng = np.random.default_rng(params.seed)

    # Lay the form out on the grid, phrase by phrase. Units count grid steps
    # from the first phrase's first bar line; pickups reach back before it.
    placed: list[tuple[str, Phrase, int, str | None]] = []
    t = 0
    verse_index = 0
    # how often each fixed block comes round, so a turning line knows which time it is
    rounds = {b: sum(genome.sections[n].lyrics == b for n in params.form) for b in genome.fixed}
    heard = dict.fromkeys(genome.fixed, 0)
    for name in params.form:
        section = genome.sections[name]
        lines: list = [None] * len(section.phrases)
        if section.lyrics == "verse" and verses:
            lines = list(verses[verse_index % len(verses)])
            verse_index += 1
        elif section.lyrics in genome.fixed:
            block = section.lyrics
            lines = [turn(line, heard[block], rounds[block]) for line in genome.fixed[block]]
            heard[block] += 1
        for pid, line in zip(section.phrases, lines):
            phrase = genome.phrases[pid]
            placed.append((name, phrase, t, line))
            t += phrase.bars * meter.bar
    lead = placed[0][1].pickup  # shift so the song's first pickup starts at zero
    end = t + lead

    seconds_per_unit = 60.0 / params.tempo / meter.beat
    rit_start = placed[-1][2] + lead
    preroll = 0.6  # room for a breath and the first consonants before the first note
    # Swing delays each beat's off-beat half, from straight (0) to a triplet lilt (1);
    # a compound beat (three to a beat) keeps its own lilt.
    swing = params.band.swing if meter.beat % 3 else 0.0
    ratio = 0.5 + swing / 6.0

    def swung(u: float) -> float:
        if not swing:
            return u
        b, x = divmod(u, meter.beat)
        half = meter.beat / 2.0
        x = x / half * ratio * meter.beat if x < half else ratio * meter.beat + (x - half) / half * (1.0 - ratio) * meter.beat
        return b * meter.beat + x

    def seconds(u: float) -> float:
        """Grid units to seconds, swung, slowing linearly through the final phrase."""
        u = swung(u)
        if u <= rit_start:
            return preroll + u * seconds_per_unit
        x = u - rit_start
        span = max(end - rit_start, 1)
        return preroll + (rit_start + x + params.ritardando * x * x / (2 * span)) * seconds_per_unit

    def jitter() -> float:
        return float(rng.normal(0.0, params.humanize))

    melody: list[dict] = []

    for section_name, phrase, start, line in placed:
        sung = phrase.sung
        words = sung_words(line) if line else [(None, None, 1)] * len(sung)
        for k, (note, (syllable, word, word_len)) in enumerate(zip(sung, words)):
            u = start + lead + note.onset
            stressed = note.onset % meter.foot == 0
            # the chord under this note, for any voices harmonizing it (a pickup takes the first bar's)
            bar = min(max(note.onset // meter.bar, 0), phrase.bars - 1)
            in_bar = phrase.chords[bar]
            chord = in_bar[min(max((note.onset - bar * meter.bar) * len(in_bar) // meter.bar, 0), len(in_bar) - 1)]
            melody.append(
                dict(
                    u=u,
                    u_end=u + note.dur,
                    pitch=params.tonic + degree_semitones(note.degree, params.mode, note.alter),
                    vel=(0.82 if stressed else 0.68) + rng.uniform(-0.04, 0.04),
                    syllable=syllable,
                    word=word,
                    word_len=word_len,
                    line_end=k == len(sung) - 1,
                    section=section_name,
                    phrase=phrase.id,
                    chord=chord,
                    choir=genome.sections[section_name].choir,
                    index=k,
                    gesture=gesture(phrasing, phrase.id, k),
                )
            )

    # The melody is one line: each note sounds until the next begins, which
    # also trims a held phrase ending where the next phrase's pickup starts.
    # Where there are words the voice sings it; where there are none, the band
    # decides who plays it (songbird.band).
    melody.sort(key=lambda m: m["u"])
    notes: list[Note] = []
    for i, m in enumerate(melody):
        u_end = min(m["u_end"], melody[i + 1]["u"]) if i + 1 < len(melody) else end
        start_s = max(0.0, seconds(m["u"]) + jitter())
        if m["syllable"]:
            beat = seconds_per_unit * meter.beat
            unphrased = Note(
                part="voice",
                start=start_s,
                dur=max(seconds(u_end) - start_s, 0.05),
                pitch=float(m["pitch"]),
                vel=float(m["vel"]),
                syllable=m["syllable"],
                word=m["word"],
                word_len=m["word_len"],
                line_end=m["line_end"],
                section=m["section"],
                phrase=m["phrase"],
            )
            sung_note = sung_as(unphrased, m["gesture"], beat)
            notes.append(sung_note)
            if m["choir"]:  # the lineage joins, each voice on its own harmony line
                for i in range(params.choir):
                    pitch = harmony(int(m["pitch"]), m["chord"], params.tonic, params.mode, i)
                    own = choir[i] if choir and i < len(choir) else None
                    if own:  # sung that voice's way, from its own phrasing
                        g = gesture(own, m["phrase"], m["index"])
                        base = replace(unphrased, part=f"choir{i + 1}", pitch=float(pitch), vel=0.9 * unphrased.vel)
                        notes.append(sung_as(base, g, beat))
                    else:  # together with the lead in time, but each with its own way with pitch
                        notes.append(replace(sung_note, part=f"choir{i + 1}", pitch=float(pitch),
                                             vel=0.9 * sung_note.vel, gesture=None))

    accomp, band_settings = band_mod.arrange(genome, params, placed, lead, end, melody, seconds)
    ring = 3.0  # the last chord rings out
    final = seconds(end)
    notes += accomp
    # plucked strings and voices ring on; a bow or a breath is held a moment longer, then let go
    held = {"fiddle": 1.0, "whistle": 0.8}
    notes = [
        replace(n, dur=n.dur + held.get(n.part, ring)) if n.start + n.dur >= final - 1e-3 and n.part != "voice" else n
        for n in notes
    ]

    section_spans = []
    for section_name, phrase, start, _ in placed:
        s0, s1 = seconds(start + lead), seconds(start + lead + phrase.bars * meter.bar)
        if section_spans and section_spans[-1][0] == section_name and abs(section_spans[-1][2] - s0) < 1e-9:
            section_spans[-1] = (section_name, section_spans[-1][1], s1)
        else:
            section_spans.append((section_name, s0, s1))

    notes.sort(key=lambda n: (n.start, n.part, n.pitch))
    return Score(tuple(notes), final + ring, tuple(section_spans), dict(genome.lexicon), band=band_settings)
