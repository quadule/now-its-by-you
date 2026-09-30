# How a song's words are drawn (2026-09-25)

A rendition's words come from its song's lyric bank. For H that is 38
verses, six refrain couplets, three bridge stanzas and three tag syllables,
each with slots for the words that can swap (songs/h-bank.md, for reading;
under `bank` in songs/h-now-its-by-you.json, for the program). The bank also
states the rules for putting a song together. `songbird/arrange.py` draws a
rendition's words from it with a seed: no network, no model, and the same
inputs always give the same words. The refrain stays the refrain; the verses
are where a rendition wanders.

## What gets drawn

The form comes first: the order of sections a rendition sings (intro, verse,
refrain, turn, verse, refrain, turn, bridge, refrain, tag for the seed). The
drift will choose it; for now it is the seed's, or `--form`. Every sung
section of that form is then filled:

- **Verses**, one for each verse section, two to four in a song. The first
  is a plain one (AABB, common, no phrase run over a line break), because it
  teaches the shape. At most one variant (ABAB, ABCB or enjambed) and at
  most one rare verse. Dated verses are sung earliest first, so the song
  reads as time passing; a verse with no year can go anywhere. A pair (wire
  and learned, wax and sample, mind and names...) is sung side by side when
  both are in. No two dark verses side by side, and at most one light verse.
  Each verse's swaps are chosen once: a girl, or a nun, and her pronouns
  with her.
- **The refrain**, each time round, with words of its own (since the
  artist asked for "different variations ... in each iteration of the
  chorus", 2026-09-26). Its first two lines are its head. The first and last
  refrains sing the song's own ("Who made this song? Nobody knows. / It's
  yours while you sing it, and then it goes."), so the hook is heard first
  and last. A refrain between them may sing another head instead, each at
  most once a song: for H, the artist's, sung as written, "Who wrote this
  song? Nobody, so / it's yours if you sing it and then who knows?" (in
  about half of the songs with three refrains, always the middle one). The
  first refrain asks who made it and the last who owns it; each refrain
  between asks something else (sang, heard, kept or wrote), a different word
  each time. A lone refrain asks who made it, as the fixed refrain does.
  "While" (or when, or if) is drawn afresh each time round, and so is "it
  goes" (or who knows, or it grows), but each refrain ends its own way
  while there are endings left: a song of three refrains sings all three.
  The artist's head always ends "and then who knows?", so no other refrain
  in that song says it as a statement. Its second couplet is different each
  time, never repeated, and the last refrain always sings the canon: "by
  everyone, no one, and now it's by you."
- **The bridge**: the first bridge section sings the canon, its swaps
  (water, mountain, border or desert; coal, spark or light; dark or cold)
  chosen once. If the form sings the bridge twice (bridge, bridge, or bridge
  and bridge2) the second is one extra stanza, coat or given, sung by the
  same choir on the same tune.
- **The tag**: la, loo or oo, one syllable on every note.

A form the rules can't fill is refused in a plain sentence rather than bent:
five verse sections, seven refrains, a third bridge. `forms()` says what the
bank can fill: for H, 2 to 4 verses, up to 6 refrains (one couplet each,
canon last) and up to 2 bridge sections. The bank's rules don't ask for a
refrain or a bridge, so arrange doesn't either; the genome's form template
does (three refrains and a bridge). A rule arrange doesn't know how to keep
is an error too, not a silence, so a rule added to the bank later can't be
skipped without anyone noticing.

## How the draw works

Verses are drawn by weight, one at a time. Pairs are call and answer: once
one of a pair is drawn, its partner answers it next half the time, where
the rules would let the two be sung together (less often if the leanings
turn away from the partner; a rare partner isn't rationed as an answer). So
that having a partner doesn't make a verse commoner, a paired verse is
drawn on its own that much less often. When the drawn verses can't go
together (two light ones, say, or none plain enough to open with) the whole
set is drawn again; when they can, one of the orders the rules allow is
chosen. Every other choice (each slot, the couplets, the extra stanza, the
tag syllable) is an even draw among its options unless a leaning tilts it.

Each part of the song draws from its own stream of the seed, separate from
the rest of the rendition's randomness, so changing how many verses a form
has doesn't change which couplets its refrains sing. The refrains' heads and
their questions have streams of their own too.

The refrain's rules are data, as the rest are (`bank.rules.refrain`):
`question` is "turn" (in order, as the fixed refrain turns, the last time
round the last word) or "draw" (H's: the first word first, the last last,
the rest drawn between); `once_per_song` names head slots kept the same in
every refrain (H's had while and then until 2026-09-26; none now);
`distinct` names slots each refrain sings its own word in while the words
last, the ones a head fixes set aside for it (H's: then);
`head_first` and `head_last` name the heads the first and last refrains
sing, and `head_repeat: false` sings another head at most once a song, and never two
heads that fix the same question (swear and grew both ask who made it, as
written);
`first` and `last` hold a slot to one word in the first and last refrains
(H's: `{"this": "this"}` both, so those ask about this song and the ones
between may ask about that song or the song), a head's own fixed word
winning. A
head is written like the refrain's own lines, on the same phrases, singing
the refrain's slots by name; its `fixed` holds any slot to one word, sung as
written. The rules a bank can't keep together are refused when it's read:
a distinct slot also kept once a song, a head fixing a word kept once a
song, a head asking its own question that may be sung twice. One function
(`_round_words`) gives every refrain's words for a fresh draw, held words,
the drift and a person's choices alike, and one says why words break the
rules. With H's rules as they were before, this draw gives exactly the
words the old one gave (the words golden, unchanged); the new rules change
only the refrains (every verse, bridge and tag drawn over the golden's 600
draws is as before).

What that gives, over 3,000 seeds. With the seed's two verses: 603
different pairs of verses (769 counting their order); every one of the 29
verses that may open a song opens some; a common verse is in 3 to 7% of
songs, most near 6% (the variants, which share one place a song, lower:
hold, light and a variant, 3%); the rare ones less (learned 1.8%; trench,
rare, dark, a variant and dated 1916, 0.5%); partners are sung together in
6% of songs. With four verses: 2,945 different songs, partners together in
14%. When one of a pair is sung, its partner answers it 29 to 76% of the
time. The rules turn a drawn set back about once in twelve songs of two
verses, and a song of four never took more than seven draws.

Era order has a consequence worth hearing: most songs open in the 1800s
or out of time (with four verses, 43% open on a verse from the 1800s and
32% on one with no year), and the newest verses close. The era bias is how
time moves that.

The singer leans on a line's focus word, marked `*like this*`. The bank
marks none of its own verses yet; the artist's refrain head carries its
own marks, on the question and on "yours", as the song's own head has them. Where a bank entry is one of the seed's own
blocks (the five seed verses, the refrain's first two lines, the canon
couplet, the canon bridge) the seed's marks come with it, on the same word
in the same place, whatever the swaps: "It's *yours* when you sing it",
"*hand* it along like a spark from the fire". A mark never moves onto a
swapped word. Everything else is sung without a focus word until the bank
marks it; a mark the bank adds to a line wins over a lent one.

## What can steer it

The seed gives chance. The rest of the program can lean on the draw through
`Leanings`, and a leaning only ever changes how likely a choice is, never
whether the rules allow it:

| Leaning | What it does | Neutral | Range |
|---|---|---|---|
| `mood_weights` | how much likelier a plain, light, dark or tender verse is | 1 each | 0.05 to 20 |
| `era_bias` | toward older verses (−1) or newer ones (+1), by year; a verse with no year is unaffected | 0 | −1 to 1: up to 3 times likelier or less likely |
| `rarity_appetite` | how often a rare verse comes on its own: a third as often as a common one at 0, as often at +1, a ninth at −1 | 0 | −1 to 1 |
| `vocabulary` | common words a person uses; the verses, couplets, stanzas and swaps that use them are likelier, the more so the fewer others share the word | none | any words; the little ones (the, her, it) count for nothing |

A value past its range is held at the end and recorded that way, so a
record says what bore on the draw. The drift is meant to set the first
three from time, so a machine's song darkens or brightens and wanders
between old times and new over the months; the harvest gives the
vocabulary, so a person who writes about phones hears the ringtone verse
more often, and one who plays the banjo hears it in the busker's hands.

## What a rendition keeps

`arrange()` returns a `Lyrics`: the form, the seed, the leanings, and for
each sung section which verse, couplet, stanza or syllable it sings, the
words chosen for its slots, and its lines as sung. It goes into the
render's record under `lyrics` and prints as a lyric sheet. Of a person's
vocabulary it keeps only the words the bank has, since no others can touch
the draw: nothing more of them leaves the machine, and drawing again from
the record gives the same words. A rendition is replayed from the lines it
recorded, not by drawing again, so it sings the same even if a later numpy
draws differently from the same seed.

## Using it

    uv run python -m songbird.arrange songs/h-now-its-by-you.json --seed 7
    uv run python -m songbird.arrange songs/h-now-its-by-you.json --forms
    uv run songbird render songs/h-now-its-by-you.json --lyrics-seed 7

The first prints a lyric sheet and what was chosen (add `--form ...` for
another form, `--json` for the record). The last sings it, with the lyric
sheet written beside the render. Without `--lyrics-seed` a render sings the
seed's own words exactly as before; a machine or a date sings the words its
lineage holds (`Params.words`), which change a verse or a word at a time
rather than being drawn afresh every render (docs/EVOLUTION.md). `hold()`
keeps a rendition's words for its lineage, `sing()` sings held words in a
form, and `check()` says why they can't be.

In code: `arrange(genome, form, seed, leanings=None)` gives the `Lyrics`,
and `realize(genome, params, ..., lyrics=lyrics)` sings them. `forms(genome)`
says how many of each section the bank can fill, and `problem(genome, form)`
says in a sentence why a form can't be filled (None if it can).
`seed_lyrics(genome, form)` gives the seed's own words as a `Lyrics`, named
for the bank entries they are.

## How it was checked

- Every rule, checked from the bank's own data rather than through
  arrange's checks: three thousand seeds of the seed form with two, three
  and four verses; every form the bank can fill (2 to 4 verses, 0 to 6
  refrains, 0 to 2 bridge sections, with and without a tag), twenty seeds
  each; a few forms out of the template's shape; five sets of extreme
  leanings; and the fallback search that takes over if drawing ever gives
  up.
- The same inputs give the same words, in separate processes with
  different hash seeds too; a hundred seeds give a hundred different songs.
- Without drawn words, every song renders exactly as before: the seed's
  own words given as a `Lyrics` sing the identical score for all twelve
  songs, and the previous `realize()` and this one give identical scores.
  The golden render is unchanged.
- Sung with drawn words, every syllable lands on its note in its phrase,
  the second bridge is sung by the choir, the focus marks reach the singer,
  and nothing else about the score moves. A render's record alone replays
  its words, its score and its lyric sheet exactly.
- A Fable review, read-only, tried to break the rules with odd forms and
  extreme leanings and found no violation; its findings on pairs, leanings
  and the interface are in.

## What the bank can't do yet

Found while building this; the bank is the other thread's to change:

- Three of the six pairs can never be sung together, because the rules
  forbid it: carve and ink are both dark (a pair must be side by side, two
  dark verses never are), hold and ring are both light (at most one light
  verse), kids and lullaby are both variants (at most one variant).
- A pair with no years (mind and names) has no order, so names comes first
  half the time; if one is the call and the other the answer, the bank
  could say which.
- The sample verse swaps "girl" and "her" as separate slots, so "a boy put
  a piece of it under a beat ... and nobody paid her" can be drawn; the
  bank's own rule is that a pronoun follows its noun. Shepherd and goatherd,
  sheep and goats are separate too (a goatherd singing to sheep).
- The bank's lines carry no focus marks, so only the seed's own verses,
  refrain and bridge are sung with a focus word; a song that draws one of
  the seed's verses and one of the others leans on one and not the other.
- Small ones: the ink verse is dated 1800 but can lie in a drawer "a
  thousand-odd years"; the probe can pass Pluto, which no probe carrying a
  record did; shell, deaf and nurse give pronoun columns no line uses.
- The genome's form template has no second bridge, so the extra stanza is
  only sung in a form built outside it, and the template allows a single
  verse where the rules need two.

# Taking over the arrangement (2026-09-29)

The studio test that made an EDM version through the page (docs/STUDIO-EDM-TEST.md) found that the
arrangement's dynamics came from chance, not from the person: how the song starts, the band joining line
by line, the breakdown were drawn and couldn't be set; there was no per-section drum pattern, no
instrumental drop, sections were fixed at their bars; and the tempo stopped at 1.3 times the song's,
whatever the style. The artist: the program's own choices (drawn by chance, per machine and date) are the
point of the piece, stay the default and stay visible; a person can take any of them over. This is the
engine and the API a DAW-like page needs (sections as regions, players as tracks, a track x section grid,
one inspector: docs/STUDIO-REDESIGN.md); the page itself is designed there. `songbird/takeover.py` holds it
(not `arrange.py`, which draws the words).

## The design, as built

**One place the program's arrangement lives.** Both arrangers already decide, section by section, what
each player does there: `band.plan` (the ballad) and `idioms.plan_style` (every other style) fill each
`Section.parts` (player -> idiom: "walk", "strum", "four", "half"...), and the style's options
(`idioms.shape_plan`: entrances, a bare verse, stop-time, a breakdown, a half-time bridge, a pad intro)
then remove players or make them come in late (`Plan.entrances`). A person's arrangement is laid over that
by three calls in both arrangers: `takeover.prepare` before the plan (which sections of the form each of
the band's sections holds, and a section a person had played marked so), `takeover.take_over` after the
plan and the style's options (the program's decisions kept in `ctx.taken`, then the person's put in their
place) and `takeover.shape` on the notes written (entrances, levels, a build, a played section's tune).
The program decides first, always, and what it decided is kept beside the person's, so the page shows
both and a released choice goes back to it.

**The edits.** Flat paths, as every edit is (docs/STUDIO.md), by the arrangement's own section ids
(`verse:1`, the second verse in story order, as `form.order` and `part.*` name them):

| Path | Value | What |
|---|---|---|
| `arrange.<section>:<n>.<player>.level` | out, soft, plays, hard | in or out, and how hard (the page's words: docs/STUDIO-REDESIGN.md). out sits the player out there; soft keeps only its beats, 0.8 as loud, and plays what the style gives it with the band a little quieter (its busyness less 0.3), the ballad's players a step down from the program's (a walk to roots, a strum to a boom-chick); plays is the program's own there (the style's for the section's energy where the program had it out); hard what the style gives a fuller band (busyness plus 0.3), a step up for the ballad's, 1.15 as loud. The section's energy itself doesn't move, so a hard refrain gets no fill it wasn't getting unless `fill` asks |
| `arrange.<section>:<n>.<player>.pattern` | an idiom of the player's | what it plays there: a kit's or a drum machine's groove, four on the floor, half time, toms, a boom-bap, winding down, a build; a bass's roots, two, walk, eighths, sub; a guitar's strum, boom-chick, Travis picking; "lead", the tune... The vocabulary (`takeover.patterns`): every idiom any style gives that instrument (or the part it stands in for), its family's own, "lead" for a pitched player, and for the drums the grooves and a build; the ballad's eight have their own writers' idioms (`BALLAD`). One that plays the same as another is offered once (`takeover.ALIASES`: the drum machine's "machine", its own four on the floor until 2026-09-30, is "four"; an edit, a record or a lock that says "machine" reads as "four") |
| `arrange.<section>:<n>.<player>.from` | a line (0: from the start) | where it comes in: the band joining line by line, per player, per section, counted in the section's own lines |
| `arrange.<section>:<n>.<player>.fill` | true, false | a drum fill in the section's last bar into the next, or none: a kit or a drum machine (`idioms.w_groove`); the frame drum's fills were taken out on 2026-09-27 and stay out |
| `arrange.<section>:<n>.bars` | 2, 4, 8, 16 | the section's length. A played section (an intro, a break, an outro, or a sung one made played) is fitted from its own tune lines, the last ones kept (the cadence) and repeated backwards: the eight-bar break (v1 v2 v3 v2) at four is v3 v2, at sixteen itself twice. A sung section is only lengthened: its lines sung, then the band plays its last lines again, the lead on the tune (a post-refrain drop); never shortened below its lines. A turn keeps its two bars (its tune is a line quoted to fit them). The jig's own length for a played section of four bars or less is twice round (`style.rounds`, docs/STYLES.md "Two more"): its intro eight, its turns four; a person's length wins, and says the section's own |
| `arrange.<section>:<n>.sung` | false | the section played, not sung: its words are still drawn (so no other section's words move, and a person's lines for it wait) but the singer, the lineage choir and the backing voices leave it, the fills between lines with them, and the band's lead plays the tune; the band keeps its weight under the lead (a drop, not a break: `band.Context.vel` leaves off the dimming it gives an instrumental statement) |
| `arrange.<section>:<n>.build` | true | a build toward the next section: the players come in one after another at bar lines through its first half (the chords first, then the bass, the drums, the rest, as the band joins line by line), everything rises from 0.7 to 1.15 as loud, and a kit or a drum machine plays a build (`idioms.w_build`: a crash, the kick on every beat through the first half, the snare on beats, then half-beats, then the feel's finest steps, rising; the last beat empty) unless its pattern is set; the ballad's frame drum keeps its pattern and rises. Not on the song's last section (said) |

null releases any of them (and so do `sung: true` and `build: false`, the section's own). The style's
own options have the rest of their edits: `style.intro`, `style.stops`, `style.alone`,
`style.alone_with` and `style.bridge`, beside the existing `style.entrances`, `style.breakdown`,
`style.lift` and `style.ending`, so how it starts, stop-time and the breakdown can be chosen whole; a
cell's `level` or `from` then overrides what they did to that player there (and a player a person
arranged in a stop-time verse plays as they chose). Choosing one of these options with no machine to draw
the rest now keeps the others as the version had them (`style.choose_style`); before, they were all drawn
again.

**A lock.** Keeping what chance drew is the same edit with the program's own value (the page's padlock,
docs/STUDIO-REDESIGN.md "Decided"): the record marks it `locked: true` beside its value and "was" in
`chosen_by_you`, the version is the same, and a new performance can't move it. For a cell, "was" is the
program's own level, pattern, line and fill there (`takeover.program_cells`: the score laid out once, no
audio, and kept for the same parameters); a lock isn't counted as a change (`explain.Version.held`).

**Stored** as a person's composition is: `params.composition["arrange"]` = `{"verse:0": {"bars": 16,
"sung": false, "build": true, "players": {"drummachine": {"level": "hard", "pattern": "four"}}}}`, so the
record's parameters carry it and `--replay` renders from them byte for byte; `from_record` makes the
edits again from the marks. Absent when empty: a version with no such edits is the version as before,
byte for byte (the goldens are unchanged).

**Inherited** by place, as a played part is: a child keeps the person's arrangement (decision 1 in
docs/STUDIO.md). A choice for a section the version doesn't have, a player its band hasn't got (its style
moved round the ring), a pattern its player doesn't play, a `from` past the section's lines or a build
at the end is kept, silent, and waits for a version that has them; a new one is said and not kept
(`takeover.silent`, `edits._taken_over`). A played part (`part.*`) for a line a section's new length no
longer plays is said and waits the same way (`takeover.part_missing`).

**Validated** in two steps. `edits.check` (`takeover.check`): the path's grammar, the section one of the
song's (or `bridge2`) under 48, the player one the program knows, the level one of four, the pattern one
that player plays in some band, `from` under 16, `fill` only a kit's or a drum machine's, `bars` 2, 4, 8 or
16 and reachable from the section's lines, `sung` only where there are words, `build` a boolean. Then with
the rest of the edits and what the version held (`Overrides._arrange`): a sung section shorter than its
lines is refused ("to shorten it, have it played rather than sung"), a length held from before goes back
to the section's own when a person has it sung again; and after the version is resolved, what it can't
play (above).

**Where the length acts.** Everything that lays the form out on the grid reads one list, a section
occurrence's tune lines and whether each is sung (`takeover.phrase_plan`: exactly the section's own when
nobody changed it): realize's layout and its clock (`realize.timeline`), the chord times
(`idioms.chord_times`), the tune editor's view (`composition.view`), the notes-in line windows and layout,
a section's preview window and the MIDI file's markers (both share a run of same-named sections by bars,
not evenly, once their lengths differ), and a style's repeated last line (the last one sung, if the last
lines were played). A section length is a list of the song's own tune lines, so the harmony, the chords a
person changed, the variants and the lift all follow.

**A pair of sections in a row** (verses in pairs) is one section to the band's plan. A person's
arrangement of either splits it at the boundary only after the program's plan, the style's options and
the backing voices have run on the program's own sections, so their indices (the first verse's table
entry, stop-time's and a bare verse's verse numbers, the oohs) are the program's; both halves keep the
pair's role, energy and parts, its entrances go with the half they fall in, stop-time and half-time with
both, and no fill lands on the boundary unless a person asks for one.

**Tempo, by style.** A person's range was 0.75 to 1.3 times the song's tempo, whatever the style. Now
(`edits.tempo_range`) it is the style's own range at its feel multiplied by 0.9 and 1.1, never narrower
than 0.75 to 1.3 of the song's, inside 0.4 to 1.6 of it: the ballad keeps 72 to 124.8 for H; synth folk
reaches 134.1, indie 137.3, a string band 147.8; a lullaby's waltz goes down to 38 (its quarter at 57). A
tempo is checked against the widest (`edits.bounds`: 38.4 to 153.6) and held to its style's at the end,
once the style is chosen (a style or a feel chosen after it may hold it), said if it had to be, and marked
as sung so it replays. The tempo card carries its style's range, and the page's tempo input and slider
use it.

**A drum machine is the rhythm, as a kit is** (2026-09-30). Its module gives it a family of its own ("drum
machine"), and the style arranger counted only "drums" (with percussion and bass) as the rhythm, so a
chance-drawn breakdown held the drum machine back with the pads and leads until the last refrain's third line:
half that refrain went without its kick (the arrangement agent measured it in a synth folk render).
`idioms.DRUMS` is both families now, and `PERCUSSION` holds it: the drum machine plays through a breakdown,
waits with the rhythm after a quoted intro, joins with the drums in the band's entrances, goes half-time in a
half-time bridge (which a style with a drum machine may now draw, as one with a kit could), and its last hit
isn't held to the end. That changes default renders of synth folk and lo-fi where those options fall (for
three machines on three days, ten of eighteen: seven of synth folk's nine, three of lo-fi's); the ballad, H's seed and the goldens are unchanged.
**So is the synth bass the bass** (2026-09-30, the artist: fix the bugs). Its module registers it with the
synths (family "synth", for the mixer), so it sat out the first half of a breakdown's last refrain (synth folk:
0 + 32 notes across its halves; now 32 + 32). `idioms.is_bass` counts it, and `idioms.rhythmic` is the rhythm
section wherever the style arranger groups it (the breakdown's players, the entrances' order, the leads it
isn't, a half-time bridge's roots). Synth folk's and lo-fi's renders change again where those options fall.

**The API for the page**: `/api/arrangement` (docs/STUDIO.md, "Arrangement control").

## What the review changed

A read-only Fable review of the design before it was built; its points are in: the pair split after the
program's plan, not before it (splitting first would have moved stop-time, the oohs and a fill onto the
pair's boundary), both halves copying what the program gave the pair; the layout sites the design missed
(the previews' and the MIDI markers' even share of a same-named run, the notes-in layout's sung flag, the
repeated last line, parts in lines a length drops); a played section's lead and its loudness (the band's
dimming under a lead left off); the backing voices' oohs, which sing by section, kept out of a played one;
validation in two steps, the second with the rest of the edits, the version's own and the form; levels
relative to the section (busyness less or more 0.3, a step down or up for the ballad) rather than fixed
tables; a build as players coming in at bar lines with a rise, not notes left out at random, and refused
at the song's end; `from` counted in the occurrence's own lines; the notes of the pass kept in the order
written; the tempo rule multiplied, per feel, known only once the style is chosen, and marked as sung; the
module named apart from `arrange.py`; the page's words. Its suggestion that the ballad's plan take a
per-player busyness offset (so the harp would follow a guitar a person changed, as it follows the
program's) is left: a person's cell is taken as they set it, and the ballad's players step along their own
idioms.

## How it was checked

- tests/test_takeover.py: nothing arranged is the same song (three versions, and an empty arrangement);
  thirteen kinds of refusal with why, a sung section refused shorter and allowed once played, releases;
  four on the floor in the first verse of synth folk (a kick on every beat but the fill's) with nobody
  else moving; a player out, soft (fewer, softer notes) and hard (harder), and the ballad's bass a step
  down; a played refrain (no singer or choir there, the synth lead on the tune, the band as heavy, the
  words drawn the same, the singer elsewhere as sung); lengths (a 16-bar break, an 8-bar intro, a 16-bar
  last refrain sung then played; the clock, the tune view and the spans agree; a short break keeps its
  cadence); a 16-bar build (snares per bar rising to sixteenths, the last beat empty, players joining, the
  weight rising; at the song's end said); a player from a later line, a fill taken away and asked for; a
  pair split only where arranged, the rest of the score untouched; marks with the program's values, made
  again from the record, replayed the same, handed down, released, and a lock (the same version, marked
  locked); silent and said where a version can't play it, and inherited ones waiting; the tempo by style;
  the style's options chosen whole, the rest kept with no machine.
- tests/test_studio.py: `/api/arrangement` draws the grid (every section and player, the person's cell
  with the program's beside it, a played 16-bar refrain with the lead on the tune, reasons for every
  program's cell, the style's tempo range, a silent choice said, a lock kept and marked), and none of its
  words says the code's names.
- tests/test_edits.py: the tempo checked against the widest and held to the ballad's, said.
- The goldens (tests/test_determinism.py, test_styles.py, test_lean_render.py, test_variation.py) are
  unchanged.
