"""Realization: genome + concrete parameters -> a timed score.

This is the only stage where the genome (what persists), the parent's
parameters (what was inherited), the voice (who is singing) and the drift
(when) meet. choose_params() combines the last three into concrete Params
(the table of how is in variation.py); realize() walks the genome with them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
from typing import TYPE_CHECKING

import numpy as np

from . import band as band_mod
from .band import Band
from .genome import Genome, Phrase, sung_words, turn
from .phrasing import Gesture, Phrasing, gesture
from .score import Note, Score
from .style import Style
from .theory import degree_semitones, harmony

if TYPE_CHECKING:
    from .drift import Drift
    from .harvest import Voice


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
    # Chosen by the machine and inherited; empty means the seed's own (VoiceParams' and MixParams' defaults).
    singer: dict = field(default_factory=dict)  # VoiceParams fields that differ from the seed singer's
    mix: dict = field(default_factory=dict)  # MixParams fields (synth.mixing), the machine's room's rt60 and tone among them
    leanings: dict = field(default_factory=dict)  # for songbird.arrange (variation.leanings): its Leanings' fields
    lay: float = 0.0  # beats the singers sit ahead of the beat, behind if negative (applied by variation.lay)
    inventory: str = ""  # phoneme inventory for the singer's vowels, "" the seed's (not yet read by the singer)
    style: Style = field(default_factory=Style)  # the tradition it's played in and its arrangement (songbird.style)

    @classmethod
    def from_dict(cls, data: dict) -> Params:
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        values["form"] = tuple(values["form"])
        if data.get("room"):  # a record from before the mix: its room was the mix's rt60 and tone
            values["mix"] = {**data["room"], **(values.get("mix") or {})}
        band = values.get("band")
        if data.get("swing") and not isinstance(band, Band) and "swing" not in (band or {}):
            # a record from before the band: its swing was the fraction of the off-beat half pushed late,
            # a third being a triplet lilt, which is band.swing 1
            values["band"] = band = {**(band or {}), "swing": min(1.0, float(data["swing"]) / 0.333)}
        if "band" in values:
            values["band"] = band if isinstance(band, Band) else Band.from_dict(band)
        if "style" in values and not isinstance(values["style"], Style):  # absent in old records: the seed's
            values["style"] = Style.from_dict(values["style"])
        return cls(**values)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["form"] = list(self.form)
        # The seed's own style and band leave no trace, so a record (and the rendition seed a child draws
        # from its parent's record) is as it was before styles existed.
        if self.style.seed:
            del data["style"]
        else:
            data["style"] = self.style.to_dict()
        if not self.band.lineup:
            del data["band"]["lineup"]
        return data


def choose_params(genome: Genome, parent: Params | None = None, voice: Voice | None = None,
                  drift: Drift | None = None, seed: int | None = None) -> Params:
    """Inherit from the parent, pull toward the voice, apply drift.

    With no voice and no drift, the parent's parameters (the seed's, from the
    genome, if there is no parent) come back unchanged. Otherwise each
    parameter pulls from the parent's toward the machine's own value as the
    drift moves it today (variation.KNOBS and DECISIONS), and the rendition's
    seed comes from (voice, instant, parent), or from `seed` if given: the same
    machine, instant and parent always give the same child.
    """
    if voice is None and drift is None:
        chosen = parent if parent is not None else Params.from_dict(genome.seed_params)
        return chosen if seed is None else replace(chosen, seed=seed)
    from .variation import choose  # the table reads the singer's fields, so it brings the synth with it

    return choose(genome, parent, voice, drift, seed)


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
            choir: list[Phrasing | None] | None = None, lyrics=None) -> Score:
    """The timed score. With a phrasing, the voice sings each note its way:
    early or late against the grid, held longer or shorter, and carrying the
    note's gesture on to the singer for loudness and pitch. choir: a phrasing
    for each lineage voice that joins in (None, or missing: that voice follows
    the lead's timing with no gestures of its own). lyrics: words drawn from
    the song's bank for this form (arrange.Lyrics), sung in place of the seed's
    verses and fixed blocks; without them the seed's own words are sung."""
    if lyrics is not None and verses is not None:
        raise ValueError("realize sings verses or lyrics, not both")
    verses = verses if verses is not None else genome.seed_verses
    meter = genome.meter
    rng = np.random.default_rng(params.seed)

    # Lay the form out on the grid, phrase by phrase. Units count grid steps
    # from the first phrase's first bar line; pickups reach back before it.
    placed: list[tuple[str, Phrase, int, str | None]] = []
    t = 0
    verse_index = 0
    # how often each fixed block comes round, so a turning line knows which time it is
    rounds = {b: sum(genome.section(n).lyrics == b for n in params.form) for b in genome.fixed}
    heard = dict.fromkeys(genome.fixed, 0)
    drawn = lyrics.lines_for(genome, params.form) if lyrics is not None else None  # per section, None if no words
    for j, name in enumerate(params.form):
        section = genome.section(name)  # bridge2: the bridge again, same phrases and choir
        lines: list = [None] * len(section.phrases)
        if drawn is not None:
            lines = list(drawn[j] or lines)
        elif section.lyrics == "verse" and verses:
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
                    choir=genome.section(section_name).choir,
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
