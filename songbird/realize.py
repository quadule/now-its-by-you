"""Realization: genome + concrete parameters -> a timed score.

This is the only stage where the genome (what persists), the parent's
parameters (what was inherited), the voice (who is singing) and the drift
(when) meet. choose_params() combines the last three into concrete Params;
realize() walks the genome with them. Milestone 1 realizes fixed parameters;
inheritance, the voice pull and drift arrive with milestones 3 to 5.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace

import numpy as np

from .genome import Genome, Phrase, sung_words, turn
from .phrasing import Gesture, Phrasing, gesture
from .score import Note, Score
from .theory import chord_tones, degree_semitones, harmony


@dataclass(frozen=True)
class Params:
    """Everything a rendition decided that the genome leaves open."""

    tonic: int  # MIDI pitch of scale degree 1 in the melody's register
    mode: str
    tempo: float  # beats per minute
    form: tuple[str, ...]  # concrete section order
    seed: int = 0  # seeds every random choice in the rendition
    accomp: str = "0 1 2 3 2 1"  # arpeggio over the chord voicing, one token per step; . rests
    humanize: float = 0.006  # standard deviation of onset jitter, seconds
    ritardando: float = 0.35  # how much slower the final phrase ends than it began
    choir: int = 0  # voices from the lineage that join in harmony where the genome allows

    @classmethod
    def from_dict(cls, data: dict) -> Params:
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        values["form"] = tuple(values["form"])
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

    def seconds(u: float) -> float:
        """Grid units to seconds, slowing linearly through the final phrase."""
        if u <= rit_start:
            return preroll + u * seconds_per_unit
        x = u - rit_start
        span = max(end - rit_start, 1)
        return preroll + (rit_start + x + params.ritardando * x * x / (2 * span)) * seconds_per_unit

    def jitter() -> float:
        return float(rng.normal(0.0, params.humanize))

    melody: list[dict] = []
    accomp: list[Note] = []
    steps = params.accomp.split()
    beats_per_bar = meter.bar // meter.beat

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

        for b, chords in enumerate(phrase.chords):
            bar_u = start + lead + b * meter.bar
            step_u = meter.bar / len(steps)
            steps_per_beat = len(steps) / beats_per_bar
            starts = [round(round(k * beats_per_bar / len(chords)) * steps_per_beat) for k in range(len(chords))]
            spans = list(zip(starts, starts[1:] + [len(steps)]))
            for symbol, (s0, s1) in zip(chords, spans):
                root, third, fifth = chord_tones(symbol, params.mode)
                low = params.tonic - 22  # the bass root lands in the octave above this
                bass = low + (params.tonic + root - low) % 12
                voicing = [bass, bass + (fifth - root), bass + 12, bass + 12 + (third - root), bass + 12 + (fifth - root)]
                chord_end = seconds(bar_u + s1 * step_u)
                for s in range(s0, s1):
                    token = steps[s - s0]
                    if token == ".":
                        continue
                    index = int(token)
                    onset = max(0.0, seconds(bar_u + s * step_u) + jitter())
                    accomp.append(
                        Note(
                            part="bass" if index == 0 else "harp",
                            start=onset,
                            dur=max(chord_end - onset, 0.05),
                            pitch=float(voicing[index]),
                            # players comp softer (and so darker) under a singer
                            vel=((0.75 if s == 0 else 0.5) + rng.uniform(-0.05, 0.05)) * (0.65 if line else 1.0),
                            section=section_name,
                            phrase=phrase.id,
                        )
                    )

    # The melody is one line: each note sounds until the next begins, which
    # also trims a held phrase ending where the next phrase's pickup starts.
    # Where there are words the voice takes the line and the plucked string
    # drops back to doubling it.
    melody.sort(key=lambda m: m["u"])
    notes: list[Note] = []
    for i, m in enumerate(melody):
        u_end = min(m["u_end"], melody[i + 1]["u"]) if i + 1 < len(melody) else end
        start_s = max(0.0, seconds(m["u"]) + jitter())
        note = Note(
            part="melody",
            start=start_s,
            dur=max(seconds(u_end) - start_s, 0.05),
            pitch=float(m["pitch"]),
            vel=float(m["vel"]) * (0.25 if m["syllable"] else 1.0),
            syllable=m["syllable"],
            word=m["word"],
            word_len=m["word_len"],
            line_end=m["line_end"],
            section=m["section"],
            phrase=m["phrase"],
        )
        notes.append(note)
        if m["syllable"]:
            beat = seconds_per_unit * meter.beat
            unphrased = replace(note, part="voice", vel=float(m["vel"]))
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

    ring = 3.0  # the last chord rings out
    final = seconds(end)
    notes += accomp
    notes = [
        replace(n, dur=n.dur + ring) if n.start + n.dur >= final - 1e-3 and n.part != "voice" else n for n in notes
    ]

    section_spans = []
    for section_name, phrase, start, _ in placed:
        s0, s1 = seconds(start + lead), seconds(start + lead + phrase.bars * meter.bar)
        if section_spans and section_spans[-1][0] == section_name and abs(section_spans[-1][2] - s0) < 1e-9:
            section_spans[-1] = (section_name, section_spans[-1][1], s1)
        else:
            section_spans.append((section_name, s0, s1))

    notes.sort(key=lambda n: (n.start, n.part, n.pitch))
    return Score(tuple(notes), final + ring, tuple(section_spans), dict(genome.lexicon))
