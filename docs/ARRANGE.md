# How a song's words are drawn

A rendition's words come from its song's lyric bank. For H that is 51 verses, the refrain's own head and eight
more, eight refrain couplets, five bridge stanzas and three tag syllables, each with slots for the words that can
swap (songs/h-bank.md, for reading; under `bank` in songs/h-now-its-by-you.json, for the program). The bank also
states the rules for putting a song together. `songbird/arrange.py` draws a rendition's words from it with a seed:
no network, no model, and the same inputs always give the same words. The refrain stays the refrain; the verses
are where a rendition wanders.

## What gets drawn

The form comes first: the order of sections a rendition sings (intro, verse, refrain, turn, verse, refrain, turn,
bridge, refrain, tag for the seed), the seed's or `--form`. Every sung section of that form is then filled:

- **Verses**, one for each verse section, two to four in a song. The first is a plain one (AABB, common, no phrase
  run over a line break), because it teaches the shape. At most one variant (ABAB, ABCB or enjambed) and at most
  one rare verse. Dated verses are sung earliest first, so the song reads as time passing; a verse with no year
  can go anywhere. A pair (wire and learned, wax and sample, mind and names...) is sung side by side when both
  are in. No two dark verses side by side, and at most one light verse. Each verse's swaps are chosen once: a
  girl, or a nun, and her pronouns with her.
- **The refrain**, each time round, with different words. Its first two lines are its head. The first and last
  refrains sing the song's head ("Who made this song? Nobody knows. / It's yours while you sing it, and then it
  goes."), so the hook is heard first and last. A refrain between them may sing another head instead, each at
  most once a song. The first refrain asks who made, wrote or sang it and the last who owns it; each refrain
  between asks something else, a different word each time. "While" (or when, or if) is drawn afresh each time
  round, and so is "it goes" (or who knows, or it grows), each refrain ending differently while there are endings
  left. A head that ends "and then who knows?" as a question keeps any other refrain in that song from saying it
  as a statement. Its second couplet is different each time, never repeated, and the last refrain always sings
  the canon: "by everyone, no one, and now it's by you."
- **The bridge**: the first bridge section sings the canon, its swaps (water, mountain, border or desert; coal,
  spark or light; dark or cold) chosen once. If the form sings the bridge twice (bridge, bridge, or bridge and
  bridge2) the second is one extra stanza (coat, owed, borrow or slow), sung by the same choir on the same tune.
- **The tag**: la, loo or oo, one syllable on every note.

A form the rules can't fill is refused in a plain sentence rather than bent: five verse sections, nine refrains,
a third bridge. `forms()` says what the bank can fill: for H, 2 to 4 verses, up to 8 refrains (one couplet each,
canon last) and up to 2 bridge sections. The bank's rules don't ask for a refrain or a bridge, so arrange doesn't
either; the genome's form template does. A rule arrange doesn't know how to keep is an error, so a rule added to
the bank later can't be skipped without anyone noticing.

## How the draw works

Verses are drawn by weight, one at a time. Pairs are call and answer: once one of a pair is drawn, its partner
answers it next half the time, where the rules would let the two be sung together (less often if the leanings
turn away from the partner; a rare partner isn't rationed as an answer). So that having a partner doesn't make a
verse commoner, a paired verse is drawn alone that much less often. When the drawn verses can't go together (two
light ones, say, or none plain enough to open with) the whole set is drawn again; when they can, one of the
orders the rules allow is chosen. Every other choice (each slot, the couplets, the extra stanza, the tag syllable)
is an even draw among its options unless a leaning tilts it.

Each part of the song draws from a separate stream of the seed, apart from the rest of the rendition's
randomness, so changing how many verses a form has doesn't change which couplets its refrains sing. The refrains'
heads and their questions have separate streams too.

The refrain's rules are data, as the rest are (`bank.rules.refrain`):

- `question` is "turn" (in order, as the fixed refrain turns, the last time round the last word) or "draw" (H's:
  the first refrain's word from `question_first`, the last last, the rest drawn between);
- `once_per_song` names head slots kept the same in every refrain (H's: none);
- `distinct` names slots each refrain sings a different word in while the words last, the ones a head fixes set
  aside for it (H's: then);
- `head_first` and `head_last` name the heads the first and last refrains sing, and `head_repeat: false` sings
  another head at most once a song, and never two heads that fix the same question (swear and grew both ask who
  made it, as written);
- `first` and `last` hold a slot to one word in the first and last refrains (H's: `{"this": "this"}` both, so
  those ask about this song and the ones between may ask about that song or the song), a head's fixed word
  winning.

A head is written like the refrain's lines, on the same phrases, singing the refrain's slots by name; its `fixed`
holds any slot to one word, sung as written. The rules a bank can't keep together are refused when it's read: a
distinct slot also kept once a song, a head fixing a word kept once a song, a head asking its own question that
may be sung twice. One function (`_round_words`) gives every refrain's words for a fresh draw, held words, the
drift and a person's choices alike, and one says why words break the rules.

The singer leans on a line's focus word, marked `*like this*`. Every line of the bank's verses, couplets and
bridges marks one ("A ship in the night picked it up on the *air*", "*Bor-row* it, wear it, and give it
a-way;"), on a written word, never a slot; the refrain's other heads mark the question and one word of their
second line. Where a bank entry is one of the seed's blocks (the five seed verses, the canon couplet, the canon
bridge) its marks are the seed's. The refrain's own first two lines mark nothing, and the seed lends them its
marks, on the same word in the same place, whatever the swaps: "Who *made* this song?", "It's *yours* when you
sing it". A mark never moves onto a swapped word; a mark the bank writes on a line wins over a lent one.

## What can steer it

The seed gives chance. The rest of the program can lean on the draw through `Leanings`, and a leaning only ever
changes how likely a choice is, never whether the rules allow it:

| Leaning | What it does | Neutral | Range |
|---|---|---|---|
| `mood_weights` | how much likelier a plain, light, dark or tender verse is | 1 each | 0.05 to 20 |
| `era_bias` | toward older verses (−1) or newer ones (+1), by year; a verse with no year is unaffected | 0 | −1 to 1: up to 3 times likelier or less likely |
| `rarity_appetite` | how often a rare verse comes alone: a third as often as a common one at 0, as often at +1, a ninth at −1 | 0 | −1 to 1 |
| `vocabulary` | common words a person uses; the verses, couplets, stanzas and swaps that use them are likelier, the more so the fewer others share the word | none | any words; the little ones (the, her, it) count for nothing |

A value past its range is held at the end and recorded that way, so a record says what bore on the draw. A
machine's traits set them (`variation.leanings`): its song darkens or brightens and wanders between old times and
new, and the vocabulary comes from what the harvest finds, so a person who writes about phones hears the ringtone
verse more often.

## What a rendition keeps

`arrange()` returns a `Lyrics`: the form, the seed, the leanings, and for each sung section which verse, couplet,
stanza or syllable it sings, the words chosen for its slots, and its lines as sung. It goes into the render's
record under `lyrics` and prints as a lyric sheet. Of a person's vocabulary it keeps only the words the bank has,
since no others can touch the draw: nothing more of them leaves the machine, and drawing again from the record
gives the same words. A rendition is replayed from the lines it recorded, not by drawing again, so it sings the
same even if a later numpy draws differently from the same seed.

## Using it

    uv run python -m songbird.arrange songs/h-now-its-by-you.json --seed 7
    uv run python -m songbird.arrange songs/h-now-its-by-you.json --forms
    uv run songbird render songs/h-now-its-by-you.json --lyrics-seed 7

The first prints a lyric sheet and what was chosen (add `--form ...` for another form, `--json` for the record).
The last sings it, with the lyric sheet written beside the render. Without `--lyrics-seed` a render sings the
seed's words; a machine or a date sings the words its lineage holds (`Params.words`), which change a verse or a
word at a time rather than being drawn afresh every render (docs/EVOLUTION.md). `hold()` keeps a rendition's words
for its lineage, `sing()` sings held words in a form, and `check()` says why they can't be.

In code: `arrange(genome, form, seed, leanings=None)` gives the `Lyrics`, and `realize(genome, params, ...,
lyrics=lyrics)` sings them. `forms(genome)` says how many of each section the bank can fill, and `problem(genome,
form)` says in a sentence why a form can't be filled (None if it can). `seed_lyrics(genome, form)` gives the
seed's words as a `Lyrics`, named for the bank entries they are.

## How it is checked

- Every rule, checked from the bank's data rather than through arrange's checks: thousands of seeds of the seed
  form with two, three and four verses; every form the bank can fill, twenty seeds each; a few forms out of the
  template's shape; extreme leanings; and the fallback search that takes over if drawing ever gives up.
- The same inputs give the same words, in separate processes with different hash seeds too.
- The seed's words given as a `Lyrics` sing the identical score to the seed's.
- Sung with drawn words, every syllable lands on its note in its phrase, the second bridge is sung by the choir,
  the focus marks reach the singer, and nothing else about the score moves. A render's record alone replays its
  words, its score and its lyric sheet exactly.

## What the bank can't do yet

- Three of the six pairs can never be sung together, because the rules forbid it: carve and ink are both dark (a
  pair must be side by side, two dark verses never are), hold and ring are both light (at most one light verse),
  kids and lullaby are both variants (at most one variant).
- A pair with no years (mind and names) has no order, so names comes first half the time; if one is the call and
  the other the answer, the bank could say which.
- The sample verse swaps "girl" and "her" as separate slots, so "a boy put a piece of it under a beat ... and
  nobody paid her" can be drawn; the bank's rule is that a pronoun follows its noun.
- The genome's form template has no second bridge, so the extra stanza is only sung in a form built outside it,
  and the template allows a single verse where the rules need two.

# Taking over the arrangement

The program's arrangement (how the song starts, the band joining line by line, a breakdown) is drawn by chance,
per machine and date. Those choices are the point of the piece, stay the default and stay visible; a person can
take any of them over, section by section and player by player, as the studio's grid of sections and players
does (docs/notes/STUDIO-REDESIGN.md). `songbird/takeover.py` holds it (`arrange.py` draws the words).

## The design

**One place the program's arrangement lives.** Both arrangers decide, section by section, what each player does
there: `band.plan` (the ballad) and `idioms.plan_style` (every other style) fill each `Section.parts` (player ->
idiom: "walk", "strum", "four", "half"...), and the style's options (`idioms.shape_plan`: entrances, a bare verse,
stop-time, a breakdown, a half-time bridge, a pad intro) then remove players or make them come in late
(`Plan.entrances`). A person's arrangement is laid over that by three calls in both arrangers: `takeover.prepare`
before the plan (which sections of the form each of the band's sections holds, and a section a person had played
marked so), `takeover.take_over` after the plan and the style's options (the program's decisions kept in
`ctx.taken`, then the person's put in their place) and `takeover.shape` on the notes written (entrances, levels, a
build, a played section's tune). The program decides first, always, and what it decided is kept beside the
person's, so the page shows both and a released choice goes back to it.

**The edits.** Flat paths, as every edit is (docs/STUDIO.md), by the arrangement's section ids (`verse:1`, the
second verse in story order, as `form.order` and `part.*` name them):

| Path | Value | What |
|---|---|---|
| `arrange.<section>:<n>.<player>.level` | out, soft, plays, hard | in or out, and how hard. out sits the player out there; soft keeps only its beats, 0.8 as loud, and plays what the style gives it with the band a little quieter (its busyness less 0.3), the ballad's players a step down from the program's (a walk to roots, a strum to a boom-chick); plays is the program's choice there (the style's for the section's energy where the program had it out); hard what the style gives a fuller band (busyness plus 0.3), a step up for the ballad's, 1.15 as loud. The section's energy itself doesn't move, so a hard refrain gets no fill it wasn't getting unless `fill` asks |
| `arrange.<section>:<n>.<player>.pattern` | an idiom of the player's | what it plays there: a kit's or a drum machine's groove, four on the floor, half time, toms, a boom-bap, winding down, a build; a bass's roots, two, walk, eighths, sub; a guitar's strum, boom-chick, Travis picking; "lead", the tune... The vocabulary (`takeover.patterns`): every idiom any style gives that instrument (or the part it stands in for), its family's, "lead" for a pitched player, and for the drums the grooves and a build; the ballad's eight players have their writers' idioms (`BALLAD`). One that plays the same as another is offered once (`takeover.ALIASES`: the drum machine's "machine" plays as "four", so an edit, a record or a lock that says "machine" reads as "four") |
| `arrange.<section>:<n>.<player>.from` | a line (0: from the start) | where it comes in: the band joining line by line, per player, per section, counted in the section's lines |
| `arrange.<section>:<n>.<player>.fill` | true, false | a drum fill in the section's last bar into the next, or none: a kit or a drum machine (`idioms.w_groove`); the frame drum plays none |
| `arrange.<section>:<n>.bars` | 2, 4, 8, 16 | the section's length. A played section (an intro, a break, an outro, or a sung one made played) is fitted from its tune lines, the last ones kept (the cadence) and repeated backwards: the eight-bar break (v1 v2 v3 v2) at four is v3 v2, at sixteen itself twice. A sung section is only lengthened: its lines sung, then the band plays its last lines again, the lead on the tune (a post-refrain drop); never shortened below its lines. A turn keeps its two bars (its tune is a line quoted to fit them). The jig plays a played section of four bars or less twice round (`style.rounds`, docs/STYLES.md "Two more"): its intro eight, its turns four; a person's length wins, and the section's own is said |
| `arrange.<section>:<n>.sung` | false | the section played: its words are still drawn (so no other section's words move, and a person's lines for it wait) but the singer, the lineage choir and the backing voices leave it, the fills between lines with them, and the band's lead plays the tune; the band keeps its weight under the lead (a drop rather than a break: `band.Context.vel` leaves off the dimming it gives an instrumental statement) |
| `arrange.<section>:<n>.build` | true | a build toward the next section: the players come in one after another at bar lines through its first half (the chords first, then the bass, the drums, the rest, as the band joins line by line), everything rises from 0.7 to 1.15 as loud, and a kit or a drum machine plays a build (`idioms.w_build`: a crash, the kick on every beat through the first half, the snare on beats, then half-beats, then the feel's finest steps, rising; the last beat empty) unless its pattern is set; the ballad's frame drum keeps its pattern and rises. Not on the song's last section (said) |
| `arrange.<section>:<n>.round` | true, or 2 to 4 | the section sung as a round ("A round", below) |

null releases any of them (and so do `sung: true` and `build: false`, the section's defaults). The style's options
have the rest of their edits: `style.intro`, `style.stops`, `style.alone`, `style.alone_with` and `style.bridge`,
beside `style.entrances`, `style.breakdown`, `style.lift` and `style.ending`, so how it starts, stop-time and the
breakdown can be chosen whole; a cell's `level` or `from` then overrides what they did to that player there (and
a player a person arranged in a stop-time verse plays as they chose). Choosing one of these options with no
machine to draw the rest keeps the others as the version had them (`style.choose_style`).

**A lock.** Keeping what chance drew is the same edit with the program's value (the page's padlock,
docs/notes/STUDIO-REDESIGN.md "Decided"): the record marks it `locked: true` beside its value and "was" in
`chosen_by_you`, the version is the same, and a new performance can't move it. For a cell, "was" is the program's
level, pattern, line and fill there (`takeover.program_cells`: the score laid out once, no audio, and kept for the
same parameters); a lock isn't counted as a change (`explain.Version.held`).

**Stored** as a person's composition is: `params.composition["arrange"]` = `{"verse:0": {"bars": 16, "sung":
false, "build": true, "players": {"drummachine": {"level": "hard", "pattern": "four"}}}}`, so the record's
parameters carry it and `--replay` renders from them byte for byte; `from_record` makes the edits again from the
marks. Absent when empty: a version with no such edits renders the same samples as one made without this module.

**Inherited** by place, as a played part is: a child keeps the person's arrangement (decision 1 in docs/STUDIO.md).
A choice for a section the version doesn't have, a player its band hasn't got (its style moved round the ring), a
pattern its player doesn't play, a `from` past the section's lines or a build at the end is kept, silent, and
waits for a version that has them; a new one is said and not kept (`takeover.silent`, `edits._taken_over`). A
played part (`part.*`) for a line a section's new length doesn't play is said and waits the same way
(`takeover.part_missing`).

**Validated** in two steps. `edits.check` (`takeover.check`): the path's grammar, the section one of the song's
(or `bridge2`) under 48, the player one the program knows, the level one of four, the pattern one that player
plays in some band, `from` under 16, `fill` only a kit's or a drum machine's, `bars` 2, 4, 8 or 16 and reachable
from the section's lines, `sung` only where there are words, `build` a boolean. Then with the rest of the edits
and what the version held (`Overrides._arrange`): a sung section shorter than its lines is refused ("to shorten
it, have it played rather than sung"), and a length held from before goes back to the section's default when a
person has it sung again; and after the version is resolved, what it can't play (above).

**Where the length acts.** Everything that lays the form out on the grid reads one list, a section occurrence's
tune lines and whether each is sung (`takeover.phrase_plan`: exactly the section's own when nobody changed it):
realize's layout and its clock (`realize.timeline`), the chord times (`idioms.chord_times`), the tune editor's view
(`composition.view`), the notes-in line windows and layout, a section's preview window and the MIDI file's markers
(both share a run of same-named sections by bars, so lengths may differ), and a style's repeated last line (the
last one sung, if the last lines were played). A section length is a list of the song's tune lines, so the
harmony, the chords a person changed, the variants and the lift all follow.

**A pair of sections in a row** (verses in pairs) is one section to the band's plan. A person's arrangement of
either splits it at the boundary only after the program's plan, the style's options and the backing voices have
run on the program's sections, so their indices (the first verse's table entry, stop-time's and a bare verse's
verse numbers, the oohs) are the program's; both halves keep the pair's role, energy and parts, its entrances go
with the half they fall in, stop-time and half-time with both, and no fill lands on the boundary unless a person
asks for one. Splitting first would move stop-time, the oohs and a fill onto the boundary.

**Tempo, by style.** A person's range (`edits.tempo_range`) is the style's range at its feel multiplied by 0.9 and
1.1, never narrower than 0.75 to 1.3 of the song's tempo, inside 0.4 to 1.6 of it: the ballad keeps 72 to 124.8
for H; synth folk reaches 134.1, indie 137.3, a string band 147.8; a lullaby's waltz goes down to 38 (its quarter
at 57). A tempo is checked against the widest (`edits.bounds`: 38.4 to 153.6) and held to its style's at the end,
once the style is chosen (a style or a feel chosen after it may hold it), said if it had to be, and marked as
sung so it replays. The tempo card carries its style's range. A person's own tempo, whatever the style, is
`tempo.free: true` beside the tempo: 40 to 220 (`edits.free_tempo_range`, never narrower than the 0.4 to 1.6 reach),
not held to the style's range; the page's tempo field writes it for a tempo outside the style's range.

**The rhythm section.** `idioms.DRUMS` holds both the drums and the drum machine families, and `PERCUSSION` holds
them with percussion: the drum machine plays through a breakdown, waits with the rhythm after a quoted intro,
joins with the drums in the band's entrances, goes half-time in a half-time bridge (which a style with a drum
machine may draw, as one with a kit can), and its last hit isn't held to the end. `idioms.is_bass` counts the
synth bass as the bass (it registers with the synths, family "synth", for the mixer), and `idioms.rhythmic` is
the rhythm section wherever the style arranger groups it (the breakdown's players, the entrances' order, the leads
it isn't, a half-time bridge's roots).

**Levels are relative to the section** (busyness less or more 0.3, a step down or up for the ballad) rather than
fixed tables. The ballad's plan takes no per-player busyness offset: a person's cell is taken as they set it, and
the ballad's players step along their idioms, so the harp doesn't follow a guitar a person changed as it follows
the program's.

**The API for the page**: `/api/arrangement` (docs/STUDIO.md, "Arrangement control").

## How it is checked

- tests/test_takeover.py: nothing arranged is the same song; the refusals with why, a sung section refused
  shorter and allowed once played, releases; four on the floor in the first verse of synth folk with nobody else
  moving; a player out, soft and hard, and the ballad's bass a step down; a played refrain (no singer or choir
  there, the synth lead on the tune, the band as heavy, the words drawn the same); lengths (the clock, the tune
  view and the spans agree; a short break keeps its cadence); a build (snares per bar rising to sixteenths, the
  last beat empty, players joining; at the song's end said); a player from a later line, a fill taken away and
  asked for; a pair split only where arranged; marks with the program's values, made again from the record,
  replayed the same, handed down, released, and a lock; silent and said where a version can't play it; the tempo
  by style; the style's options chosen whole, the rest kept with no machine.
- tests/test_studio.py: `/api/arrangement` draws the grid (every section and player, the person's cell with the
  program's beside it, reasons for every program's cell, the style's tempo range, a silent choice said, a lock
  kept and marked), and none of its words says the code's names.
- tests/test_edits.py: the tempo checked against the widest and held to the ballad's, said.

# A round

The song is about a song handed from person to person and changed; a round enacts it: the singer starts a
section, a second voice comes in a line later on the same tune and the same words, then a third, the song passed
from voice to voice. The voices are the lineage's (the choir), else the program's stand-ins.

## Where H's tune takes a round

A round needs a tune whose lines sit over each other's harmony, and most folk tunes don't at every distance.
`songbird/canon.py` scores every way of singing a section as a round, and `tools/round_fit.py` prints the tables:

- **the clash between the voices**: the beats where two of them are a semitone (or a major seventh) or a tritone
  apart, a note on a strong beat (a foot) or held a beat or more counted whole, a passing one a third, as
  `style.tune_clash` counts a loop against the tune (house's `fitting_loops`);
- **the clash with the band**: the beats where a later voice's note is a semitone off the chord the band plays
  under it (and not one of its tones), beyond what the tune has with its own chords; the band follows the voice
  furthest along, so after the section's lines it plays, line by line, the line that voice is singing;
- **whole tones** between the voices (milder: said, not counted), and how many beats they sing together.

Each overlap is weighed by its notes, and the singer's pickup is sung over its first bar's chord. The fit is
taken under a person's chords (`composition.harmonized`), which the band plays under the voices. A round **fits**
when its voices clash for at most a beat (and at most one beat in sixteen of what they sing together) and the
band no more than two beats beyond the tune's own (`style.LOOP_SLACK`). Distances: the whole section a line apart
(two bars), two lines apart (four), and half a line (one bar) for its last line only (below).

**H in its own mode (D ionian)**, each section's four lines:

| section | sung as | voices | band (the tune's own) | whole tones | together | fits |
|---|---|---|---|---|---|---|
| verse | the whole, 4 voices a line apart | 1.67 | 4.00 (1.50) | 22.7 | 82.3 | |
| verse | the whole, 3 voices a line apart | 1.00 | 3.50 (1.00) | 13.0 | 46.8 | |
| verse | the whole, 2 voices a line apart | 0.50 | 2.17 (0.50) | 6.5 | 17.5 | yes |
| verse | the whole, 2 voices 2 lines apart | 0.00 | 1.50 (0.50) | 0.0 | 11.8 | yes |
| verse | its last line, 3 voices half a line apart | 0.00 | 1.33 (0.33) | 2.7 | 7.5 | yes |
| refrain | the whole, 4 voices a line apart | 0.00 | 2.17 (1.00) | 25.3 | 95.7 | yes |
| refrain | the whole, 3 voices a line apart | 0.00 | 2.00 (0.67) | 15.3 | 54.2 | yes |
| refrain | the whole, 2 voices a line apart | 0.00 | 1.83 (0.33) | 6.5 | 20.2 | yes |
| refrain | the whole, 2 voices 2 lines apart | 0.00 | 0.17 (0.33) | 2.3 | 13.8 | yes |
| refrain | its last line, 3 voices half a line apart | 0.00 | 0.00 (0.00) | 1.0 | 7.5 | yes |
| bridge | the whole, 4 voices a line apart | 0.00 | 1.00 (0.50) | 23.3 | 83.0 | yes |
| bridge | the whole, 3 voices a line apart | 0.00 | 0.67 (0.33) | 13.5 | 47.3 | yes |
| bridge | the whole, 2 voices a line apart | 0.00 | 0.33 (0.17) | 4.7 | 17.7 | yes |
| bridge | the whole, 2 voices 2 lines apart | 0.00 | 0.17 (0.17) | 4.2 | 12.0 | yes |
| bridge | its last line, 3 voices half a line apart | 0.00 | 0.17 (0.33) | 0.7 | 7.5 | yes |

The refrain and the bridge go round with **no semitone or tritone between the voices at any distance**: in a
major mode H's tune is pentatonic (it sings 1, 2, 3, 5, 6 and touches 4 twice in passing), and a pentatonic tune
has neither interval in it. Half a line apart (one bar, the whole section) fits as cleanly (the bridge 0.00
between the voices, the refrain 0.67 for three); it isn't offered for a whole section because its tail would end
halfway through a line. What is left is whole tones: 15.3 beats of 54.2 in a three-voice refrain, the open,
ringing sound of a pentatonic round.

**The minor modes take it away.** The same degrees in D aeolian are D E F A B♭: two semitones (E F, A B♭) and a
tritone (E B♭) appear in the tune itself, and every whole-section round of the refrain and the bridge clashes:

| section | sung as | voices | band (the tune's own) | whole tones | together | fits |
|---|---|---|---|---|---|---|
| verse | the whole, 2 voices a line apart | 3.83 | 6.67 (1.83) | 5.2 | 17.5 | |
| verse | the whole, 2 voices 2 lines apart | 0.00 | 1.67 (1.83) | 0.0 | 11.8 | yes |
| verse | its last line, 3 voices half a line apart | 0.67 | 2.00 (1.00) | 2.0 | 7.5 | |
| refrain | the whole, 3 voices a line apart | 9.17 | 19.83 (5.33) | 6.5 | 54.2 | |
| refrain | the whole, 2 voices 2 lines apart | 2.17 | 6.33 (2.67) | 0.2 | 13.8 | |
| refrain | its last line, 3 voices half a line apart | 0.00 | 1.00 (1.00) | 1.0 | 7.5 | yes |
| bridge | the whole, 3 voices a line apart | 13.33 | 15.67 (4.33) | 0.5 | 47.3 | |
| bridge | its last line, 3 voices half a line apart | 0.67 | 3.17 (1.33) | 0.0 | 7.5 | |

What a round of H chooses in each mode a machine may sing it in (`tools/round_fit.py --summary`; "at 1": a line
apart):

| mode | verse | refrain | bridge |
|---|---|---|---|
| ionian | whole, 2 at 1 | whole, 3 at 1 | whole, 3 at 1 |
| mixolydian | whole, 2 at 1 | whole, 3 at 1 | whole, 3 at 1 |
| lydian | whole, 3 at 1 | whole, 2 at 1 | whole, 3 at 1 |
| dorian | none | last line, 3 at ½ | last line, 3 at ½ |
| aeolian | whole, 2 at 2 | last line, 3 at ½ | none |
| phrygian | whole, 2 at 2 | none | none |

The other sketches, each in its mode: B's refrain, K's refrain and L's verse take three voices; A, D, E, F, G, I
and J two, or the last line; C none.

## An arrangement option

A round is an arrangement option, `arrange.<section>:<n>.round`, for any style, the ballad among them. What
decides it is the tune, section by section and mode by mode: H's refrain and bridge take a round in the major
modes, its verse barely, a minor mode only the refrain's last line. A style would be a song sung round from
beginning to end, which this tune can't carry in half the modes a machine sings it in, and a round is a moment,
the last refrain or the bridge. Voices alone are already a style (the a cappella), and a round in an a cappella
goes where a person wants it.

## How it is sung

**The edit.** `arrange.<section>:<n>.round`: `true` (a round: three voices where the tune takes three, else two),
or a number of voices, 2 to 4, the singer among them; null gives the section back. Checked (`takeover.check`): a
section with words on two or more lines of one length, and a round that fits it in the song's mode; refused with
why otherwise ("the verse's tune doesn't sit over itself as a round"). With the rest of the edits
(`shape_problems`): not with a length set (`bars`) or played (`sung: false`), each said. Stored and handed down as
every arrangement choice is (`params.composition["arrange"]`); a version whose mode the round doesn't fit keeps
it, silent, said ("in this version's mode its tune doesn't sit over itself"), as a choice for a player its band
hasn't got waits.

    songbird render songs/h-now-its-by-you.json --machine fictional:ada --date 2026-09-27 --edits round.json

with `round.json` `{"arrange.refrain:3.round": true}`, or "Who sings: a round" in the section's inspector.

**The shape** (`canon.choose`, in the version's mode): the whole section a line apart if that fits, else two lines
apart, with the voices asked for (true: three, else two); where no whole round fits, **its last line as a round**:
the singer sings the section as always, and on its last line two more voices come in half a line apart, singing
that line ("by everyone, no one, and now it's by you"), a tag over the section's end, three voices whatever was
asked. That is the only round a minor mode leaves H.

**The ending: the voices drop out in turn.** Each voice sings the section once and stops at the end of its last
line, held as the singer holds it; the section is longer by the later voices' tail, `(voices - 1)` times the
distance (a three-voice refrain a line apart: 8 bars and 4 more, 12). Under the tail the band plays, line by line,
the line the voice furthest along is singing (`canon.under`; for the tag, its last line once), so each voice's
"now it's by you" lands on the chords it was written over, and the last one ends the section alone on the tonic,
with the band. A held chord at the end, everyone stopping at once, would cut the later voices off before their
last line, and the last line is the hook. In the layout (`takeover.phrase_plan`) the tail is lines the section
plays after its own, as a sung section made longer is (`bars`): the tune lines, chord times, spans, karaoke, MIDI
markers and the piano score all follow; the singer is silent there and no instrument plays the tune. Both
arrangers take the round's tail as the end of the singing (`canon.sung_until`), so a quote coda and the last
chord's hold come after it. On the song's last section the singer's last note ends where its line does.

**The voices.** The singer is first; each later entry is a choir part, the lineage's voices where it has them
(params.choir), else the program's stand-ins (as the a cappella's group is made up), panned as the choir is
(`synth.CHOIR_PANS`: the singer in the middle, then -0.45, 0.45, -0.25). The oldest comes in second and the
parent last (`choir1`), so the voice nearest the singer finishes the round, "now it's by you" (`canon.entries`).
The singer stays first because whoever starts sings over the written chords. Each sings the singer's notes in the
section (its variants, the words of that verse or refrain) at the written pitch, shifted by its entry, each a hair
off the beat (as backing voices are, `idioms.sung_notes`). A stand-in drawn "low" sings an octave down everywhere
else; in the round its notes are written an octave up so they sound where the tune is written (an octave down,
H's tune goes under the throat's floor, E3), and they are left out of its part's range. The entries are made as
backing voices are (`idioms.backing`), so the band keeps clear of their notes as it does of the backing. A
voice's last note rings three seconds where it ends the song; a round's last voice doesn't (the singer's doesn't
either), unless the style is voices alone.

**Everything else in a round section steps aside.** No backing voices there (the gang, thirds, oohs, an a
cappella's parts), no lineage harmony (a round of the bridge is the lineage passing its tune instead of
harmonizing it), no fills between the lines and no player on a line alone (a counter-melody, a descant, the tune
doubled: `takeover.LINES`); the band's chords, bass and drums play as the program has them. Held chords running
into a round (an a cappella's hum, oohs) stop where it begins. House's drop lengths (its hook bars) stay before a
round refrain; the tail follows them.

**How loud.** The entries sing on the choir's bus, which is brought to its loudness as a whole, so no gain is
applied to a round's notes alone (it would only pull the rest of the choir down).

**The page.** In the section's inspector, "Who sings": the singer · a round · nobody: played. "A round" has the
tooltip "the voices come in one after another" (where it is the last line: "on its last line"); where the tune
can't take one, it is disabled with why. A section with a length set refuses it (said: give it its default length
first); a played one goes round in the same click, the page asking for both. The region's label says "· a round",
and the grid's "Voices before" row shows the round. A line player's cell says why it rests ("a round, as you
chose: the voices carry the tune, so the fiddle rests").

**Nothing else moves.** With no round asked for, nothing here runs: every function gives back what it was given,
and every render is as it would be without canon.py. No kernel and no numba, so the browser's translation needs
nothing new.

The code: `songbird/canon.py` (the fit, the choice, the tail, the later voices), with small hooks in
`takeover.py` (the path, its checks, the layout's tail, a round section's players and fills, the grid's fields and
words), `realize.py` (the singer's notes marked in a round, none in its tail, no lineage harmony in it, the last
note, the ring), `idioms.backing` and the seed's ballad in `band.arrange` (the later voices made as backing voices;
nobody else's backing there), `band.fills` (none in a round), `synth.stem_jobs` and `matched` (a round's notes
where they are written; not counted in a part's range), and the page (`score.js`, `model.js`, `studio.js`). Tests:
tests/test_round.py and a grid test in tests/test_studio.py.

## Measured

**Tuning**, each note's f0 over its middle (pYIN on the dry stems) against its written pitch, in the round
sections of four renders (ada's ballad and a cappella, coral's a cappella in D aeolian with five voices, dmitri's
chamber version): every voice's median 1.3 cents flat (the measure's bias: the singer's too), and 97 to 100% of
notes within 25 cents, the singer and each later voice alike. The voices sound where the tune is written; a singer
who sings an octave down (dmitri's) stays an octave under them, a canon at the octave.

**Levels**, each voice against the singer where all sing at once, as the mix's buses set them: ada's ballad 4.7
to 5.9 dB under the singer in the bridge, 5.2 to 5.9 in the last refrain (with a single round in the song, 1.9 and
3.6: the choir's bus is set by everything it sings); ada's a cappella 4.3 and 7.8 dB under; dmitri's four-voice
bridge about level with his low voice (+2.5 to -2.7 dB).

**The words blur where the voices overlap.** Whisper (base.en, on the mix, a beat before each round section to its
end), counting the singer's words heard once against the same sections in the same versions without the round:
62% of the words heard in the rounds (173 of 280), 86% without (242 of 280). Word error rates aren't comparable
there: Whisper writes down several voices' words. By section: the ballad's bridge 52% of the words (82% plain)
and its last refrain 58% (88%); the a cappella's 64% (82%) and 86% (98%); coral's two-voice verse 72% (90%);
coral's last refrain, only its last line round, 91% (85%); dmitri's four-voice bridge 36% (85%) and three-voice
refrain 27% (79%). A round's first line is the singer alone and clear; from the second voice on, the words come
round three times over and the ear follows one voice at a time. A round is heard as the tune passed along more
than as a lyric.

**Memory** (tools/render_memory.py's measure, two threads, `MallocLargeCache=0`): the later voices sing in choir
stems a version already has or adds one at a time, so a round costs its tail's seconds rather than its overlap:
an a cappella with six voices, a refrain and the bridge as rounds, 255 s, 1.54 GB (the studio's estimate 1.83; in
`MEASURED`); four verses, every part, six voices, tempo 55, every refrain, verse and bridge a round, 712 s, 2.86
GB, against 2.78 for the same without the rounds (494 s): past the studio's 2100 MB either way, and refused. A
round adds about 4 bars a section (a line for a last-line round).

## Choices and open questions

1. **Singer first, parent last.** The other way (the ancestors starting, the singer ending it "and now it's by
   you") would put the singer's line over chords written for a line ahead, or move everything in the layout.
2. **Three voices by default**, a line apart; four are there to ask for. Four overlapping voices blur most (36%
   of the words heard).
3. **The minor modes** take only the refrain's last line as a round (three voices a bar apart), and the verse two
   voices two lines apart; the aeolian bridge none (said in the page). Offering the whole round "with its clash
   said" would go against the program's refusals elsewhere.
4. **Open: a refrain round before the tag** sings "now it's by you" three times, then the tag's "la" on the same
   line: four cadences in a row. The tag could make way after a round (or its harmony rest).
5. **Open: the levels.** The voices are the choir's bus, set as a whole: 2 to 8 dB under the singer, level with it
   in a four-voice round. A round could have a louder level (a mix balance over its span after the bus).
6. **Words**: about a quarter of them blur in a whole-section round. A round on the bridge (the lineage's section,
   which most listeners know by then) or the last refrain (heard three times before) costs the least.

# A stage edition

The awards stage mix ("arc-morph") renders from a record (`songbird/stage.py`): `songbird render
performance/genome.json --replay performance/record-arc-morph.json` (with `--stems` for its parts). Two layers of
data say what an edition is.

**The grid**, in the person's arrangement (`params.composition["arrange"]`, `songbird.takeover`), what the studio
can show and what a child inherits, as the rest of the arrangement:

| Path | Value | What |
|---|---|---|
| `arrange.<section>:<n>.human` | 0 to 1, or a list, one a line | how much of people is in the lead (`stage.amounts`): its phrasing's gestures and the singer's liveliness scaled by min(2h, 1), the people's share of its timbre 0.6 h. 0 the machine alone, 0.5 the performance voice as it is. A section with none keeps the amount before it |
| `arrange.<section>:<n>.<player>.synth` | all, until:<line>, under | the player's synth twin (`stage.TWINS`: harp and guitar an arpeggio, bass a synth bass, drum a drum machine, whistle and fiddle a synth lead) plays the player's notes, level with it: in its place, until that line (0 the first) and the player from there, or under the player at 7 dB below |

The arrangers never read these (`takeover.arranged` leaves them out), so a section with only these is, to them, a
section nobody arranged. Absent, the render is the program's, to the sample.

**The exact data**, `params.composition["exact"]`, the edition's and never inherited (`composition.handed_down`
drops it):

```json
{"twins": {"harp~": ["harp", "arp"], "harp#": ["harp", "chip"]},
 "layers": [{"style": "synthfolk", "parts": ["arp", "synthpad"],
             "copy": [{"part": "synthpad", "to": "verse:0", "from": "verse:1"}]}],
 "levels": {"harp~": [["verse:0.3", -3], ["refrain:0", null]], "harp": [["verse:0.3", null], ["refrain:0", 0]]},
 "human": {"verse:0": [0, 0, 0, 0.2]}}
```

`twins`: a synth (any instrument) on a player's notes or a layered part's, named, level with it by the whole stems' RMS;
`layers`: another style's players on the same song (its key, tempo, form and chords), a section of a part played
as it plays another; `levels`: each named part's level along the song as points (where, dB or null for silent)
joined by straight fades, the first and last held, a point at the place of the one before it 0.12 s after it;
`human`: amounts finer than the grid's. A place is `<section>:<n>` (its start), `<section>:<n>.<line>` (where the
lead's line begins, its pickup with it), `<section>:<n>.end` or `<section>:<n>@<f>` (that far through it, 0 to 1). Where the exact data gives `twins` or `levels`,
they are the whole table: what the grid's synth cells would make of them is left aside.

**The render.** `stage.prepare` lays the plan out in the score (`Score.stage`, never written to the score's file):
the lead realized again at each amount the song names, which take is heard from which line, the twins, the
layered scores and the levels in seconds. `synth.stem_jobs` makes the stems from it (`stage.jobs`): the lead sung
whole at each amount and the takes joined where its lines begin (30 ms fades); the twins; the layered parts; each
named part times its level. The stem cache keeps none of these under the program's key. The mix and the master
are the program's. The throat is quiet after a singer's last note (throat.LAST_SILENCE), so a stage edition adds
no release.

**Measured** against the stems of the script that first made the mix: every stem within float rounding (-149 dB
or less, relative to the stem), the mix -150 dB, the FLAC -79 dB (the 16-bit dither; against the script's mix
mastered and dithered as the program does, -115 dB). record-B with none of these renders the same samples as
without stage.py.
