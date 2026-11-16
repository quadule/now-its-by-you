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
from . import heteronyms
from . import variants as variants_mod
from .band import Band
from .genome import Genome, Meter, Phrase, sung_words, turn
from .phrasing import Gesture, Phrasing, gesture, shape as note_shape, sung_gesture
from .score import Note, Score
from . import style as style_mod
from .style import Style
from .theory import choir_voicing, degree_semitones

if TYPE_CHECKING:
    from .drift import Drift
    from .harvest import Voice


SUNG_SYLLABLES = {"oo": "UW1"}  # what backing voices sing (songbird.idioms.backing), readable for every song


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
    loudness: float = -14.0  # the master's integrated loudness, LUFS (songbird.synth.master; -12 for listeners' players)
    band: Band = field(default_factory=Band)  # who plays and how (songbird.band); absent in old params: the defaults
    # Chosen by the machine and inherited; empty means the seed's own (VoiceParams' and MixParams' defaults).
    singer: dict = field(default_factory=dict)  # VoiceParams fields that differ from the seed singer's
    mix: dict = field(default_factory=dict)  # MixParams fields (synth.mixing), the machine's room's rt60 and tone among them
    leanings: dict = field(default_factory=dict)  # for songbird.arrange (variation.leanings): its Leanings' fields
    lay: float = 0.0  # beats the singers sit ahead of the beat, behind if negative (applied by variation.lay)
    inventory: str = ""  # phoneme inventory for the singer's vowels, "" the seed's (not yet read by the singer)
    # How this lineage has come to sing the song (docs/EVOLUTION.md). Inherited, and changed a little at a time
    # by songbird.evolve; empty for the seed, which sings its tune as written and its own words. Left out of
    # to_dict() while empty, so a record made without them reads (and seeds its children) the same.
    variants: tuple = ()  # songbird.variants.Variant: this lineage's departures from the written tune
    words: dict = field(default_factory=dict)  # the words this lineage holds (arrange.hold): {} the seed's own
    generation: int = 0  # renditions between this one and the seed: 0 the seed, 1 its child...
    made: dict = field(default_factory=dict)  # by (a machine's hash, its first 12 digits) and at (days): whose clocks it turned
    style: Style = field(default_factory=Style)  # the tradition it's played in and its arrangement (songbird.style)
    composition: dict = field(default_factory=dict)  # portable human arrangement and phrase notes (composition.py)
    # a person's sound design (songbird.sound): players' patches, kits, filters, pans, sends and sidechains, and
    # the transitions at section boundaries; handed down like the composition, left out of to_dict() while empty
    sound: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> Params:
        values = {k: v for k, v in data.items() if k in _PARAMS_FIELDS}
        values["form"] = tuple(values["form"])
        if data.get("room"):  # a record with a room and no mix: its room is the mix's rt60 and tone
            values["mix"] = {**data["room"], **(values.get("mix") or {})}
        band = values.get("band")
        if data.get("swing") and not isinstance(band, Band) and "swing" not in (band or {}):
            # a record with a swing of its own, outside the band: the fraction of the off-beat half pushed late,
            # a third being a triplet lilt, which is band.swing 1
            values["band"] = band = {**(band or {}), "swing": min(1.0, float(data["swing"]) / 0.333)}
        if "band" in values:
            values["band"] = band if isinstance(band, Band) else Band.from_dict(band)
        values["variants"] = variants_mod.parse(values.get("variants"))
        values["words"] = dict(values.get("words") or {})
        values["made"] = dict(values.get("made") or {})
        values["composition"] = dict(values.get("composition") or {})
        values["sound"] = dict(values.get("sound") or {})
        if "style" in values and not isinstance(values["style"], Style):  # absent in old records: the seed's
            values["style"] = Style.from_dict(values["style"])
        return cls(**values)

    def to_dict(self) -> dict:
        band = self.band.to_dict()
        if not self.band.lineup:
            del band["lineup"]
        data = {
            "tonic": self.tonic,
            "mode": self.mode,
            "tempo": self.tempo,
            "form": list(self.form),
            "seed": self.seed,
            "accomp": self.accomp,
            "humanize": self.humanize,
            "ritardando": self.ritardando,
            "choir": self.choir,
            "loudness": self.loudness,
            "band": band,
            "singer": _copy_dict(self.singer),
            "mix": _copy_dict(self.mix),
            "leanings": _copy_dict(self.leanings),
            "lay": self.lay,
            "inventory": self.inventory,
        }
        if self.variants:
            data["variants"] = [v.to_dict() for v in self.variants]
        if self.words:
            data["words"] = _copy_dict(self.words)
        if self.generation != 0:
            data["generation"] = self.generation
        if self.made:
            data["made"] = _copy_dict(self.made)
        # The seed's own style and band leave no trace, so a record (and the rendition seed a child draws
        # from its parent's record) is the same as one made without styles.
        if not self.style.seed:
            data["style"] = self.style.to_dict()
        if self.composition:
            data["composition"] = _copy_dict(self.composition)
        if self.sound:
            data["sound"] = _copy_dict(self.sound)
        return data

    @property
    def digest(self) -> str:
        d = getattr(self, "_digest", None)
        if d is None:
            import hashlib
            import json

            d = hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:16]
            object.__setattr__(self, "_digest", d)
        return d


_PARAMS_FIELDS = frozenset(f.name for f in fields(Params))


def _copy_dict(d: dict) -> dict:
    if not d:
        return {}
    return {k: (_copy_dict(v) if isinstance(v, dict) else _copy_seq(v) if isinstance(v, (list, tuple)) else v)
            for k, v in d.items()}


def _copy_seq(seq):
    return type(seq)(_copy_dict(v) if isinstance(v, dict) else _copy_seq(v) if isinstance(v, (list, tuple)) else v
                     for v in seq)


def choose_params(genome: Genome, parent: Params | None = None, voice: Voice | None = None,
                  drift: Drift | None = None, seed: int | None = None, log: list | None = None,
                  form: tuple | None = None, overrides=None, style: str | None = None,
                  arrange: dict | None = None) -> Params:
    """Inherit from the parent, pull toward the voice, apply drift.

    With no voice and no drift, the parent's parameters (the seed's, from the
    genome, if there is no parent) come back unchanged. Otherwise each
    parameter pulls from the parent's toward the machine's own value as the
    drift moves it today (variation.KNOBS and DECISIONS), and the rendition's
    seed comes from (voice, instant, parent), or from `seed` if given: the same
    machine, instant and parent always give the same child. log: a list to
    which what changed from the parent in the tune and the words is added,
    each with why (songbird.evolve), for the render's record. form: a form set
    by hand (--form), in place of the one the drift would choose, and the words
    fitted to it.

    overrides: a person's choices (songbird.edits: an edits map, or an
    edits.Overrides, which also says which took effect and why any didn't),
    each put in place of the choice it names, inside the table so a decision
    that reads it reads the person's. None or none at all: as without.

    A parent from before a person's lines were kept by verse hands them down
    by verse (composition.handed_down).
    """
    if parent is not None:
        from .composition import handed_down

        exact = parent.composition.get("exact")
        parent = handed_down(genome, parent)
        if (exact is not None and overrides is None and voice is None and drift is None and style is None
                and not arrange and form is None):  # the version itself, as it was: its exact data with it
            parent = replace(parent, composition={**parent.composition, "exact": exact})
    if overrides is not None:
        from .edits import Overrides

        overrides = overrides if isinstance(overrides, Overrides) else Overrides(genome, overrides)
        asked, options = overrides.style()  # a style a person chose goes in by name, bringing its band and tempo
        style = style or asked
        arrange = {**(arrange or {}), **options} or None
    if voice is None and drift is None and style is None and not arrange:
        chosen = parent if parent is not None else Params.from_dict(genome.seed_params)
        chosen = chosen if form is None else replace(chosen, form=tuple(form))
        chosen = chosen if seed is None else replace(chosen, seed=seed)
        return overrides.params(chosen) if overrides is not None else chosen
    from .variation import choose  # the table reads the singer's fields, so it brings the synth with it

    if overrides is None:
        return choose(genome, parent, voice, drift, seed, log=log, form=form, style=style, arrange=arrange)
    if voice is None and drift is None:  # a style with no machine: the parent played in it, then the person's
        return overrides.params(choose(genome, parent, voice, drift, seed, log=log, form=form, style=style,
                                       arrange=arrange))
    return overrides.finish(choose(genome, parent, voice, drift, seed, log=log, form=form, pin=overrides.pin,
                                   style=style, arrange=arrange))


def sung_as(note: Note, g: Gesture | None, beat: float) -> Note:
    """A sung note the way a gesture sings it: g.early beats (of beat seconds)
    ahead of the grid, held for g.hold of its written length, and carrying the
    gesture on to the singer for loudness and pitch."""
    if g is None:
        return note
    start = max(0.0, note.start - g.early * beat)
    let_go = note.start + note.dur * g.hold
    return replace(note, start=start, dur=max(let_go - start, 0.05), gesture=g)


def ordered_delivery(pairs: list[tuple[Note, Note]]) -> list[Note]:
    """Keep syllables in lyric order when learned gestures crowd two notes.

    Project the requested onsets onto an ordered timeline with room for a
    short vowel and its consonants (up to 100 ms, at most half the written
    spacing). Adjacent conflicts share the correction equally; other notes
    and a whole phrase's push or pull stay exactly as sung. This is the
    least-squares monotone fit after taking the minimum spacings away.
    """
    if len(pairs) < 2:
        return [sung for _, sung in pairs]
    original = np.array([plain.start for plain, _ in pairs])
    starts = np.array([sung.start for _, sung in pairs])
    gaps = np.minimum(0.1, np.maximum(np.diff(original), 0.0) * 0.5)
    if np.all(np.diff(starts) >= gaps):
        return [sung for _, sung in pairs]
    offsets = np.r_[0.0, np.cumsum(gaps)]
    blocks = []  # [mean, number of onsets], pooled while adjacent means cross
    for value in starts - offsets:
        blocks.append([float(value), 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            b, nb = blocks.pop()
            a, na = blocks.pop()
            blocks.append([(a * na + b * nb) / (na + nb), na + nb])
    fitted = np.repeat([v for v, _ in blocks], [n for _, n in blocks]) + offsets
    return [replace(sung, start=max(float(start), 0.0),
                    dur=max(sung.start + sung.dur - max(float(start), 0.0), 0.05))
            for (_, sung), start in zip(pairs, fitted)]


PREROLL = 0.6  # seconds before the first note: room for a breath and the first consonants


@dataclass(frozen=True)
class Clock:
    """A rendition's clock: grid units, counted from the song's first pickup,
    to seconds. The final phrase slows by `ritardando`; swing delays each
    beat's off-beat half, from straight (0) to a triplet lilt (1)."""

    meter: Meter
    tempo: float  # beats per minute
    lead: int  # units from the first pickup to the first bar line
    end: int  # units from the first pickup to the song's last bar line
    rit_start: int  # units to the final phrase's first bar line
    swing: float = 0.0
    ritardando: float = 0.0
    triple: str = ""  # "waltz" or "six": the song re-barred in three (songbird.style), each foot three even pulses
    # a slow air before the song (songbird.style.air): (units from the first pickup to where it ends, how many times
    # slower, how much each line broadens toward its end, a line's units); () none, the clock as it always ran
    air: tuple = ()

    @property
    def unit(self) -> float:
        """Seconds per grid unit at the song's tempo."""
        return 60.0 / self.tempo / self.meter.beat

    def swung(self, u: float) -> float:
        # The beats fall on the bar lines' grid, which starts `lead` units in (after the song's first
        # pickup), not at u = 0: counted from there, the beats never move and only each beat's off-beat
        # half is delayed, whatever the pickup's length.
        if not self.swing:
            return u
        beat = self.meter.beat
        ratio = 0.5 + self.swing / 6.0
        b, x = divmod(u - self.lead, beat)
        half = beat / 2.0
        x = x / half * ratio * beat if x < half else ratio * beat + (x - half) / half * (1.0 - ratio) * beat
        return self.lead + b * beat + x

    def seconds(self, u: float) -> float:
        """Grid units to seconds, swung (or re-barred in three), slowing linearly through the final phrase."""
        u = style_mod.rebar(u, self.lead) if self.triple else self.swung(u)
        if self.air:  # the slow air's units, drawn out, and everything after it later by as much
            return self._timed(u) + self.aired(u) * self.unit
        return self._timed(u)

    def _timed(self, u: float) -> float:
        if u <= self.rit_start:
            return PREROLL + u * self.unit
        x = u - self.rit_start
        span = max(self.end - self.rit_start, 1)
        return PREROLL + (self.rit_start + x + self.ritardando * x * x / (2 * span)) * self.unit

    def aired(self, u: float) -> float:
        """Units a slow air adds by u (swung or re-barred units): out of time, `slow` times as slow, each line
        (bar line to bar line) broadening toward its end, the pickup before its first bar line as slow."""
        end, slow, broaden, line = self.air
        end = style_mod.rebar(end, self.lead) if self.triple else self.swung(end)
        y = min(max(u, 0.0), end)
        if y <= self.lead:
            return (slow - 1.0) * y
        n, r = divmod(y - self.lead, line)
        drawn = self.lead + n * line * (1.0 + broaden / 3.0) + r + broaden * r ** 3 / (3.0 * line * line)
        return slow * drawn - y

    def beats(self) -> list[tuple[float, bool]]:
        """Every beat of the song in seconds, and whether it begins a bar: the
        pulse the notes were placed on, from the first beat after the song's
        start (there is one before an eighth-note pickup, in the preroll) to the
        final bar line, where the last note ends."""
        m = self.meter
        if self.triple:  # re-barred: three beats a foot (0, 2, 3 before the re-barring), a bar a foot or two
            out = []
            for f in range(-1, (self.end - self.lead) // m.foot + 1):
                for x in (0, 2, 3):
                    u = self.lead + f * m.foot + x
                    t = self.seconds(u)
                    if t >= 0.0 and u <= self.end:
                        bar = x == 0 and (self.triple == "waltz" or (f * m.foot) % m.bar == 0)
                        out.append((t, bar))
            return out
        first = -((self.lead * self.unit + PREROLL) // (m.beat * self.unit))  # as far back as time zero
        out = []
        for k in range(int(first), (self.end - self.lead) // m.beat + 1):
            t = self.seconds(self.lead + k * m.beat)
            if t >= 0.0:
                out.append((t, (k * m.beat) % m.bar == 0))
        return out


def timeline(genome: Genome, params: Params) -> Clock:
    """The clock realize() puts a rendition's notes on: its form laid out on
    the grid, phrase after phrase, the song's first pickup at zero."""
    from .clips import resolved

    genome, params, _ = resolved(genome, params)  # a person's clips, as one song (songbird.clips)
    meter = genome.meter
    from .takeover import phrase_ids

    # each section's tune lines: its own, or as long as a person made it (songbird.takeover)
    phrases = [genome.phrases[pid] for pid in phrase_ids(genome, params)]
    phrases += style_mod.repeated_phrases(genome, params)  # a style's ending may sing the last line again
    lead = phrases[0].pickup + style_mod.count_in(genome, params)  # after a count-in bar, if the style has one
    sung = sum(p.bars for p in phrases) * meter.bar + lead
    end = sung + style_mod.coda(genome, params)  # and a plagal amen's bars after the last line, if it has one
    # a compound beat (three to a beat) keeps its own lilt; a style's feel sets the swing (songbird.style)
    swing = style_mod.swing(params) if meter.beat % 3 else 0.0
    rit_start = style_mod.slowing(genome, params, sung - phrases[-1].bars * meter.bar, end)  # (a dub version holds)
    return Clock(meter, params.tempo, lead, end, rit_start, swing, params.ritardando,
                 style_mod.triple(genome, params), style_mod.air(genome, params, phrases, lead))


def realize(genome: Genome, params: Params, verses=None, phrasing: Phrasing | None = None,
            choir: list[Phrasing | None] | None = None, lyrics=None, told: list | None = None) -> Score:
    """The timed score. With a phrasing, the voice sings each note its way:
    early or late against the grid, held longer or shorter, and carrying the
    note's gesture on to the singer for loudness and pitch. choir: a phrasing
    for each lineage voice that joins in (None, or missing: that voice follows
    the lead's timing with no gestures of its own). lyrics: words drawn from
    the song's bank for this form (arrange.Lyrics), sung in place of the seed's
    verses and fixed blocks; without them the seed's own words are sung. told: a
    list given each sung note of the lead, in the order they are sung, as
    {phrase, index, line (the key a line a person wrote is kept under, or None),
    shape (phrasing.shape), of (every shape of its line), how (where its gesture came
    from: sung_gesture)}."""
    if lyrics is not None and verses is not None:
        raise ValueError("realize sings verses or lyrics, not both")
    from .clips import resolved
    from .composition import harmonized

    genome, params, lyrics = resolved(genome, params, lyrics)  # a person's clips, as one song (songbird.clips)

    # a person's chords in place of a tune line's own (songbird.composition), for everything that sounds from
    # them: the band, the choir's harmony, the backing voices; the same genome when nobody changed one
    genome = harmonized(genome, params)
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
    from .composition import authored, form_phrases, tune_key

    # a person's own lines, each in the verse (or time round) it was written for (songbird.composition)
    patches = authored(genome, params, lyrics)
    from .takeover import arranged_plan

    # each section's tune lines, and whether each is sung, where a person arranged it (its length, or played
    # rather than sung: songbird.takeover; None: the section's own); a line played sings no words
    lined = arranged_plan(genome, params)
    # each line of the form as its place sings it: its own chords and tune where a person gave it some, else the
    # line everywhere (the very phrase objects, where no place has its own)
    at_places = iter(form_phrases(genome, params, lyrics))
    from .canon import plans

    # a section sung as a round (songbird.canon): for each line laid, (its section's place in the form, its line
    # there), and the lines after its own where its later voices finish (the singer silent, no tune played)
    rounds_ = plans(genome, params)
    in_round: dict[int, tuple[int, int]] = {}
    tails: set[int] = set()
    for j, (name, patch) in enumerate(zip(params.form, patches)):
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
        if patch:  # a person's line, each heteronym in it said as the words around it say (songbird.heteronyms)
            lines = [heteronyms.decide(patch[str(i)]) if isinstance(patch.get(str(i)), str) else patch.get(str(i), line)
                     for i, line in enumerate(lines)]
        # the sung lines take the section's words in order (a style may lay played bars before them: house's drop)
        laid = zip(section.phrases, lines) if lined[j] is None else \
            [(pid, lines[k] if sung and k < len(lines) else None)
             for pid, sung, k in zip([p for p, _ in lined[j]], [s for _, s in lined[j]],
                                     np.cumsum([bool(s) for _, s in lined[j]]) - 1)]
        laid = list(laid)
        for k, (pid, line) in enumerate(laid):
            phrase = next(at_places)
            if rounds_[j] is not None:
                from .takeover import own_line

                ahead = len(laid) - len(rounds_[j].under)  # its lines, then its tail
                own = own_line(genome, name, lined[j][:ahead], k) if k < ahead else None
                if own is not None:
                    in_round[len(placed)] = (j, own)
                elif k >= ahead:
                    tails.add(len(placed))
            placed.append((name, phrase, t, line))
            t += phrase.bars * meter.bar
    for name, phrase, line in style_mod.repeated(genome, params, placed):  # a style's ending may sing the last line again
        placed.append((name, phrase, t, line))
        t += phrase.bars * meter.bar
    clock = timeline(genome, params)  # the same layout, as time
    lead, end, seconds, seconds_per_unit = clock.lead, clock.end, clock.seconds, clock.unit
    sung_end = end - style_mod.coda(genome, params)  # where the last line ends, before a style's amen
    own_form = style_mod.STYLES.get(params.style.name) if params.style.name else None
    if own_form is not None and own_form.form:  # bars a style lays after the last line (house's last hook) aren't the
        sung_end = min(sung_end, max((at + phrase.bars * meter.bar for _, phrase, at, line in placed if line),
                                     default=sung_end))  # singer's to hold its last note through

    def jitter() -> float:
        return float(rng.normal(0.0, params.humanize))

    melody: list[dict] = []
    vocal = style_mod.vocalise(params)  # "" but for a style of voices alone (songbird.style)
    # the lineage's variants, and a singer's own ornaments where its style leans that way (the jig's)
    sung_variants = params.variants + style_mod.sung_ornaments(genome, params)

    # a dub's version (songbird.style.fragments): the lines after the song dissolves sung in fragments; {} otherwise
    kept = style_mod.fragments(genome, params, placed)
    for j, (section_name, phrase, start, line) in enumerate(placed):
        if j in tails:  # a round's later voices finish here: nobody else sings or plays the tune
            continue
        sung = phrase.sung
        words = sung_words(line) if line else [(None, None, 1)] * len(sung)
        if j in kept:  # the rest of the line isn't sung: the band's lead may play it (songbird.idioms)
            words = [w if k in kept[j] else (None, None, 1) for k, w in enumerate(words)]
        # the lineage's variants: a note moved to another degree, a weak note's onset moved, an ornament
        composed = bool(phrase.own) or tune_key(phrase) in params.composition.get("tune", {})
        if composed:
            from .composition import played as composed_notes

            played = composed_notes(phrase, params)
        else:
            played = variants_mod.realized(phrase, sung_variants) if sung_variants else None
        # each note's shape as it is sung here (onset and length in beats, semitones above the tonic): what a
        # gesture of a line a person wrote, and a habit, are found by
        shapes = [note_shape((played[k] if played else n).onset / meter.beat, (played[k] if played else n).dur / meter.beat,
                             degree_semitones(played[k].degree if played else n.degree, params.mode, n.alter))
                  for k, n in enumerate(sung)]
        for k, (note, (syllable, word, word_len)) in enumerate(zip(sung, words)):
            v = played[k] if played else None
            u = start + lead + (v.onset if v else note.onset)
            onset = v.onset if composed else note.onset
            stressed = onset % meter.foot == 0
            # the chord under this note, for any voices harmonizing it (a pickup takes the first bar's)
            bar = int(min(max(onset // meter.bar, 0), phrase.bars - 1))
            in_bar = phrase.chords[bar]
            chord = in_bar[int(min(max((onset - bar * meter.bar) * len(in_bar) // meter.bar, 0), len(in_bar) - 1))]
            degree = v.degree if v else note.degree
            if syllable is None and vocal and not (params.style.intro == "pad" and section_name == placed[0][0]):
                syllable = word = vocal  # an a cappella's lead hums the tune where a band would play it (not
                word_len = 1  # under an intro whose chords swell in alone)
            turns = getattr(v, "melisma", ()) if v else ()  # a person's melisma: (grid units after the onset, degree)
            melody.append(
                dict(
                    u=u,
                    u_end=u + (v.dur if v else note.dur),
                    pitch=params.tonic + degree_semitones(degree, params.mode, note.alter),
                    ornament=variants_mod.semitones(v.ornament, degree, params.mode, note.alter) if v and v.ornament else (),
                    vel=(0.82 if stressed else 0.68) + rng.uniform(-0.04, 0.04),
                    syllable=syllable,
                    word=word,
                    word_len=word_len,
                    line_end=k == len(sung) - 1 or (j in kept and k == max(kept[j], default=-1)),  # a fragment ends
                    section=section_name,
                    phrase=phrase.id,
                    chord=chord,
                    # (a round's voices are the lineage there, singing its tune, not harmonizing it)
                    choir=genome.section(section_name).choir and j not in in_round,
                    index=k,
                    composed=composed,
                    # a tune line's note takes its gesture by its place; a line of its own takes one only from a
                    # take of that line (songbird.phrasing.sung_gesture); either, failing that, the singer's habit
                    **dict(zip(("gesture", "how"), sung_gesture(phrasing, phrase.id, phrase.own, k, shapes))),
                    own=bool(phrase.own),
                    wrote=phrase.own,
                    shape=shapes[k],
                    of=tuple(shapes),
                    **({"melisma": tuple((off, params.tonic + degree_semitones(d, params.mode)) for off, d in turns)}
                       if turns else {}),
                    **({"round": in_round[j][0], "line": in_round[j][1]} if j in in_round else {}),
                )
            )

    # The melody is one line: each note sounds until the next begins, which
    # also trims a held phrase ending where the next phrase's pickup starts.
    # Where there are words the voice sings it; where there are none, the band
    # decides who plays it (songbird.band).
    melody.sort(key=lambda m: m["u"])
    deliveries: dict[str, list[tuple[Note, Note]]] = {"voice": []}
    choirs = choir_voicing(melody, params.choir, params.tonic, params.mode)  # the band keeps clear of the same
    for i, m in enumerate(melody):
        u_end = min(m["u_end"], melody[i + 1]["u"]) if i + 1 < len(melody) else (  # (a round's later voices
            min(m["u_end"], sung_end) if m["composed"] or "round" in m else sung_end)  # sing on after the singer)
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
                ornament=m["ornament"],
                # its turns at their own moments on the grid, as seconds after the note's written start
                melisma=tuple((seconds(m["u"] + off) - seconds(m["u"]), float(p - m["pitch"]))
                              for off, p in m.get("melisma", ())),
            )
            sung_note = sung_as(unphrased, m["gesture"], beat)
            deliveries["voice"].append((unphrased, sung_note))
            if told is not None:
                told.append({"phrase": m["phrase"], "index": m["index"], "line": m["wrote"], "shape": m["shape"],
                             "how": m["how"], "of": m["of"]})
            # the lineage joins, each voice on its own harmony line, plain as harmony is sung
            for v, pitch in enumerate(choirs[i]):
                own = choir[v] if choir and v < len(choir) else None
                if own:  # sung that voice's way, from its own phrasing
                    g = None if m["own"] else gesture(own, m["phrase"], m["index"])
                    base = replace(unphrased, part=f"choir{v + 1}", pitch=float(pitch), vel=0.9 * unphrased.vel,
                                   ornament=(), melisma=())
                    deliveries.setdefault(base.part, []).append((base, sung_as(base, g, beat)))
                else:  # together with the lead in time, but each with its own way with pitch
                    part = f"choir{v + 1}"
                    deliveries.setdefault(part, []).append((unphrased,
                        replace(sung_note, part=part, pitch=float(pitch),
                                vel=0.9 * sung_note.vel, gesture=None, ornament=(), melisma=())))

    notes = [n for pairs in deliveries.values() for n in ordered_delivery(pairs)]
    notes += style_mod.chops(genome, params, placed, clock, melody)  # a style's vocal chop (house's), [] otherwise
    accomp, band_settings = band_mod.arrange(genome, params, placed, lead, end, melody, seconds)
    from .composition import played_in

    # a person's own notes for a player, played in where the band made room (docs/STUDIO.md, "Notes in")
    accomp += played_in(genome, params, placed, clock)
    ring = style_mod.ring(params)  # the last chord rings out (3 s; a cold ending stops short)
    final = seconds(end)
    notes += accomp
    # plucked strings and voices ring on; a bow or a breath is held a moment longer, then let go
    held = {"fiddle": 1.0, "whistle": 0.8}
    notes = [
        replace(n, dur=n.dur + held.get(n.part, ring))
        if n.start + n.dur >= final - 1e-3 and (n.part != "voice" and n.art != "round" or vocal) else n  # voices
        # alone: the lead holds too (and a round's last voice, which ends as the singer would, songbird.canon)
        for n in notes
    ]

    section_spans = []
    for section_name, phrase, start, _ in placed:
        s0, s1 = seconds(start + lead), seconds(start + lead + phrase.bars * meter.bar)
        if section_spans and section_spans[-1][0] == section_name and abs(section_spans[-1][2] - s0) < 1e-9:
            section_spans[-1] = (section_name, section_spans[-1][1], s1)
        else:
            section_spans.append((section_name, s0, s1))

    # a person's sound design (songbird.sound): a roll's strokes into the notes; each player's sound, the
    # sidechain's key track and the transitions for the synthesis. The notes as they were, and {}, with none.
    from . import sound as sound_mod

    desk = band_settings.pop("desk", None) if isinstance(band_settings, dict) else None  # a dub desk's (idioms)
    notes, sound = sound_mod.produce(genome, params, placed, clock, notes, desk)
    notes.sort(key=lambda n: (n.start, n.part, n.pitch))
    # the score's own words: the song's lexicon, and the syllables the backing voices sing ("oo", which no
    # dictionary has: without it a machine choosing oohs for a song without its own reading would fail)
    score = Score(tuple(notes), final + ring, tuple(section_spans), {**SUNG_SYLLABLES, **genome.lexicon}, band=band_settings,
                  sound=sound)
    return style_mod.finish(score, genome, params)  # a style's key lift for the last refrain, if it has one
