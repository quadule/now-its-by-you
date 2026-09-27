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
sing, and `head_repeat: false` sings another head at most once a song;
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
