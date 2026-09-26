# How the song evolves: the tune and the words (2026-09-26)

The artist: "I'd like to see some examples of how the song can evolve too. We'll do our training with
static melody + lyrics but I do want to allow both to drift subtly, and for the final deliverable tool to
allow the user to explore the procedural generation and optionally edit the song before recording."

Everything else a rendition decides already moves with its machine and its day: the key, the mode, the
tempo, the form, the band, the singer, the mix (docs/HARVEST.md, BAND.md, MIX.md). This adds the last two
things a folk song changes as it is passed on: small departures from the written tune, and its words.
Both change a little at a time, both are handed down, and both leave the seed exactly as it was. The
code is `songbird/variants.py` (what a departure from the tune may be), `songbird/evolve.py` (when the
tune and the words change) and the holding of words in `songbird/arrange.py`.

## The tune

A **variant** is how one lineage has come to sing one note of the tune. The kinds:

- **Ornaments**, sung inside the note, so a syllable stays one note: a grace note from the next note of
  the song's scale above or below; a mordent (a quick flick a step up or down and back); a turn (a step
  above, the note, a step below, the note); a neighbour note a step away in the middle of a line's long
  last note; a passing tone, sliding through the one degree between a note and the next a third away; an
  anticipation, the next note's pitch arriving early on the tail of a weak note, so the strong syllable
  after it lands on a note already sounding.
- **A leap resized** within its contour class: a note moved a step or two (a third becomes a fourth or
  a fifth, or less), only to a tone of the chord under it and within the song's range.
- **Rhythm**: an even pair of notes made long-short (dotted), or an uneven weak pair evened. A stressed
  syllable never moves.

What a variant never changes, and `variants.problems()` checks every time:

- each phrase's contour string (holds stay holds, steps stay steps, leaps stay leaps, the same way);
- a phrase's last note, its target, in pitch and in time;
- the stress: stressed notes stay on their beats, a moved weak note stays weak and in its foot, and no
  note is left shorter than a grid unit (in H that rules out dotting its pairs of quavers, which would
  leave a syllable a sixteenth, fussy against the swing the band already has);
- the mode and the song's own scale: H is pentatonic, and every note and every held ornament tone keeps
  to its five notes. Only quick tones may touch fa or ti: a passing tone's waypoint of about 80 ms across
  a third, which folk singers do, and a mordent's or a turn's 75 ms step (a pentatonic turn, a third wide
  where the scale has a gap, sounds lopsided). Nothing is ever chromatic;
- the chord functions: a moved note is a tone of its chord;
- the hooks and the refrain's first line, sung as written, and the note leading into a hook (the approach
  is part of it; "and" before "now it's by you" is never moved, shifted or run on);
- how many: at most 12% of any section's notes carry a variant, never two on one note or on neighbouring
  notes. A phrase sung twice in a section counts twice. For H that is 5 notes of a verse's 44, 4 of the
  refrain's 40, 5 of the bridge's 42, and 1 of the tag's 11 (the tag, intro and outro sing the refrain's
  last lines, so those lines take few).

A variant belongs to a phrase, so it is sung wherever the phrase is: a variant on the verse's second line
is sung on the fourth line too, in every verse, and played by the band in an instrumental break. The
band's lead plays the same ornament where it states the tune (the intro, a break, a turn's quote, the
whistle in the tag), the choir's harmony follows a moved note, and harmony is sung plain. The lute that
doubles the singer under the words plays moved notes and moved onsets but not ornaments, as a plain
accompanist would.

How an ornament sounds: `Note.ornament` holds its shape as breakpoints (a fraction of the sung vowel,
semitones from the note), and the singer's pitch track turns to each tone with a quick raised cosine,
about 35 ms (50 ms for the learned throat, which never learned anything steeper). The voice starts the
glide to the next note from wherever the ornament left it, the phrase-start scoop and the overshoot give
way to it, vibrato eases off while it turns, and a vowel too short for its ornament (under two and a half
of its moves) sings the note plain, as singers swallow ornaments on crowded syllables. The shape is kept in
scale steps and fractions, so it follows a change of mode or tempo.

Where a variant came from is part of its record: `source` is `drift` (a machine's own way, chosen as
below), `edit` (a person, in the studio) or `sung:<name>` (learned from a singer's takes, per
docs/MAKING-IT-THEIR-OWN.md: a note shift or an ornament found again and again in their takes enters as
the same record), and `born` is the generation it came in.

### How it changes

A child keeps its parent's variants, forgets one now and then, and learns one of its machine's own now and
then:

- **Learning.** Each machine has two learning clocks. When one turns, the child learns a variant with
  chance 0.25 + 0.5 x appetite (the first clock) or 0.6 x (appetite - 0.5) (the second, so only a
  machine that ornaments more than most ever learns two at once). The machine's **appetite** is 0.5 for
  a typical machine, up to 0.25 more for a rich vocabulary and 0.2 for an ornate habit (both from its
  harvest), and moved up to 0.25 by the slow drift of the dimension "tune", read when the clock's stretch
  began. What it learns is its own pick for that stretch: the first variant, in its own weighted order of
  everything the tune allows, that the lineage has room for. The order weighs the kinds by its character
  (an ornamenting machine decorates, a plain one moves notes, a lilting one dots, one ahead of the beat
  anticipates), shares each kind's weight among its candidates but never lets one candidate weigh more
  than three grace notes (so a figure the tune offers only once, like H's one dotted pair, can't become
  every lineage's habit), prefers an ornament at a note's start on a stressed or longer note to one on a
  passing quaver, and weighs the places (a verse 1.3, the bridge 1, the refrain 0.7: verses are where a
  folk tune wanders, a refrain is what everyone knows).
- **Forgetting.** Each variant has a forgetting clock of its own; when it turns, the variant is forgotten
  with chance 0.03 + 0.04 x (1 - appetite), half that once it has lasted three generations (a lineage's
  settled way), and more as its section fills (0.3 x how far past 60% full).

### What that gives, for H

Measured over sixty lineages handed from machine to machine two to five months apart: a lineage carries
about half a variant after one generation, two after four and three and a half after eight, and a child
keeps 95% of its parent's. What they learn is mostly ornament (graces, mordents, turns, passing tones,
anticipations, neighbour notes, in that order) and now and then a moved note. One machine singing the same
parent (the seed, say) over three years holds one or two variants of its own at a time, which change two
to four times a year and never change back within a week. A machine that sings its own last rendition
gathers variants at the pace of its clocks: after three years of weekly renditions, three to nine. However
many a lineage gathers, its tune stays close to the seed's as the lineage gate will measure it (relative
moves by dynamic time warping, hooks weighted): 0.4 semitones a move for the fullest set, where every other
song in songs/ is 1.1 to 1.5 away.

## The words

Before this, a machine's words were drawn afresh from the bank every render, so they changed completely
from one day to the next. Now a lineage **holds** its words (`Params.words`): the verses it sang in order
with their slot words, the refrain's once-a-song words (while or when or if, it goes or who knows or it
grows), the couplet each refrain sang before the last, the bridge's stanzas with their slot words and the
tag's syllable. A child keeps its parent's, and the words change three ways:

- **The form.** When a machine's form grows (the form changes by the season), a new verse comes in: the
  machine's own pick, weighted as the bank's own draw weighs it with the machine's lyric leanings, at
  the end where the rules allow (else wherever they do). When the form shrinks, the last verse is left
  out: a child only learns what its parent sang. Couplets and the bridge's extra stanza follow the number
  of refrains and bridges the same way.
- **The rules.** The seed sings its fixed refrain, the canon couplet every time round; the bank's rules,
  which every drawn and held rendition keeps, want each refrain but the last to sing a couplet of its own.
  So a child of the seed takes other couplets for its first refrains, its machine's picks, and says so.
- **One swap, now and then.** When a machine's swap clock turns, with chance 0.3 + 0.2 x a restless habit
  + 0.2 x the slow drift of "words" (held between 0.1 and 0.6), one thing is swapped for one the machine
  likes: a verse (most often), a verse's slot word (a girl for a nun, with her pronouns), a couplet, the
  refrain's or the bridge's slot word, the tag's syllable, or the bridge's extra stanza. Where it falls
  is fixed for the machine and the generation of the song it is singing, so a machine singing one parent
  for months swaps in one place (it toggles, one change at a time), while a lineage swaps somewhere new
  each generation.

The machine's picks (which verse it takes in, which couplet) are fixed for the machine and the generation
it sings, weighed with its leanings without the season's drift: a singer has a verse they reach for when
the song runs long. A swap's pick is weighed with the leanings as they stood when its stretch began, so
the season's mood and era bear on it and it holds through the stretch.

Every change keeps the bank's rules, exactly as a drawn song keeps them (`arrange.held_problem()`), and
the record says what changed and why. With these rates the words of a lineage change about once every three
hand-offs by a swap, plus whatever the form asks. One machine singing one parent changes its words five to
nine times a year, mostly as its form grows and shrinks with the season, one verse or word at a time.

## Time: clocks, not coins

The drift field is stateless, and a choice made from a set (which variant, which verse) can't ride a
smooth field the way a number or an ordered category can. So each rides a **clock** (`drift.epoch`): a
machine's clock of a given name runs in stretches of weeks or months of its own length, on a grid nudged at
every boundary so no two stretches are alike and no clock repeats, from a phase of its own, so no two
clocks turn together and none turns on a calendar edge or at midnight. Anything chosen from (machine,
clock, stretch) holds through the stretch and changes only as the next begins: never overnight, and almost
always one thing at a time (the second learning clock's pick depends on the first's, so twice or so in
three years a machine changes two variants on one day). A clock's period is drawn between two bounds and
each stretch runs between half and one and a half of it: the learning clocks' periods are 60 to 150 days,
each variant's forgetting clock 90 to 220, the word swap clock 40 to 110.

A rendition records who made it and when (`Params.made`). A child sung on the machine that made its parent
changes only what a clock has turned on since then, so a machine re-singing its own last rendition the
next day sings it the same; a child sung on another machine takes its one turn at everything, so a lineage
changes about once a hand-off. No chance is ever read from the instant a render starts. (A Fable review
caught the first design's flaw here: coins keyed by the parent would have re-rolled on every render of a
machine's own chain.) `Params.generation` counts as the record does (the seed packet's lineage): a
machine singing from the genome with no parent rendition is generation 0, its child 1.

## What never changes

- The genome: the tune as written, its contour, stress, targets, chords, hooks and refrain text.
- The seed: with no machine and no date, nothing here runs. The seed's render, record and score are byte
  for byte what they were (H's seed id 441dc83b1d1e; the golden hash).
- The karaoke guide and every training corpus: they sing the seed's parameters, so the static tune and the
  seed's words.
- A replay: a record's parameters sing the same rendition again.

## The examples

`renders/production/evolution/` (README.txt there lists every file and what changed, with a piano roll of
each rendition's tune against the seed's and its lyric sheet), made by `uv run python tools/evolution.py`:

- `lineage/`: the seed, then four generations on four made-up machines, each singing the one before, a few
  months apart. Picked from a couple of thousand orderings of twelve made-up machines as a lively lineage
  that shows every kind of change on top of the key, mode, tempo, form, band and singer (a typical lineage
  carries two variants by its fourth generation; this one five).
- `timeline/`: one made-up machine singing the seed every four months for three years: time alone.
- `own/`: the same machine singing its own last rendition every nine months.

## For the studio

The interfaces a tool that explores and edits the song before recording should use:

- `Params.variants`: a tuple of `variants.Variant(phrase, note, kind, degree, steps, shift, source, born)`.
  Offer choices from `variants.candidates(genome)` (every single variant the tune allows), check a set
  with `variants.problems(genome, variants)` (plain sentences, empty if sound) or one addition with
  `variants.fits(genome, current, v)`, name one with `variants.describe(genome, v, lyrics)`, and measure
  how far a tune has come with `variants.distance(genome, a, b)`. A person's own choice is `source="edit"`.
- `Params.words`: the held words, plain JSON (see the comment above `arrange.hold`). Sing them with
  `arrange.sing(genome, form, words)` and check an edit with `arrange.check(genome, form, words)` (the
  first thing wrong, exactly what the drift's own changes are checked against). To offer one change at a
  time, `evolve.places(genome, words)` lists every place a swap could fall and
  `evolve.alternatives(genome, words, place)` what could stand there keeping the rules (`evolve.label`
  names a place); for a wider view, `arrange.verse_ids`, `slot_words(bank_entry(genome, kind, id))`,
  `couplet_ids`, `bridge_ids`, `tag_syllables` and `verse_order`. A held entry a person chose may carry
  `"source": "edit"`; the words keep it for as long as the entry stands.
- `Params.generation` (as the record counts it) and `Params.made` (`{"by": the machine's hash, 12
  digits, "at": days}`).
- `choose_params(genome, parent, voice, drift, log=[], form=None)` fills the list with what changed and
  why, one dict each: `what` (tune or words), `change` (learned, forgot or dropped for the tune; added, left
  out, swapped, rule or drawn for the words), `about` and `variant` (the variant as a dict) for the tune,
  `where`, `from` and `to` for the words, and `why`. `form` is a form set by hand: the words are fitted to
  it and the fitting logged. `evolve.diff(genome, parent, child)` gives the what of any two, for reading.
- To record an edit, render the edited Params as any other (`cli.render_one`), after setting
  `params.words` to the words to be sung (`arrange.hold` of a Lyrics, or the edited dict). An edited
  rendition is a new one: give it its parent's generation plus one and a `made` of the machine and the
  moment it was edited (or `{}`), or a later child on that machine will misjudge which clocks have turned.
- The render's record has an `evolution` block: each variant with its description, the changes, and the
  tune's contour distance to its parent and to the seed. A record without it is the seed's, or from before.

## For the artist to decide

- **How fast.** The rates are the constants at the top of `songbird/evolve.py`. Now: about half a variant
  and a third of a word swap a hand-off; one machine's own song changes its tune two to four times a year.
- **Fa and ti.** H's grace notes, neighbour notes, anticipations and moved notes keep to its five notes;
  passing tones (an 80 ms slide through fa or ti across a third) and mordents and turns (a 75 ms step) may
  touch them. Banning them would leave H's passing tones to mi-do and do-la, and its mordents and turns to
  notes with a scale step on both sides.
- **The seed's refrain.** A child of the seed sings other couplets before its last refrain (the bank's rule
  for drawn words), so the first hand-off always changes those couplets. Holding the seed's canon until a
  swap changes it is the alternative.
- **Anticipation** is a pitch anticipation, the syllable still on its beat (the stress guard forbids moving a
  stressed syllable); a true rhythmic anticipation, the syllable an eighth early, would need that guard
  relaxed.
- **A machine that ornaments a lot**, singing its own renditions for years, can fill the song's room for
  variants (about fourteen notes in H). The second learning clock and the crowding term keep it from
  going further; a lower cap would keep such a machine plainer.
- **The form still flips back within a week now and then** (the season's form choice has no hold), and the
  words follow it: a verse can come and go within days a couple of times in three years. Holding the form
  as the band's pattern is held would stop it.
