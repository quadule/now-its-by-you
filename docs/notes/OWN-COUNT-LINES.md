# A line with its own count

Built November 14, 2026, on the branch `claude/editable-notes-syllables-line-59bd88`.

A person may sing a line with more or fewer syllables than its tune line has
notes, by writing the line's words and its notes together. Everything else in
the studio keeps a tune line's count: a tune edit (`tune.<line>`, a place's
`tune.<section>:<n>.<i>`) moves notes and may add melismas, and a written line
(`lyrics.<key>.<i>`) is counted against the tune.

## Why the words and notes go together

The count is fixed because two things are counted against each tune line:

- every bank line drawn for it (`bank.check`), in every verse that sings it;
- the lineage's per-note data: variants keyed by (line, note), phrasing
  gestures keyed by (line, note index), the choir's phrasings likewise.

A line with its own count therefore can't be the line everywhere, and can't be
kept by place. A person's written words are kept by the verse they replace
(`verse:wire`), which moves as the lineage reorders verses; a place's tune is
kept by position (`verse:2.1`). If the notes were kept by place and the words by
verse, a reordering would put eight syllables on seven notes. So the line's
notes are kept with its words, under the same key: wherever the words are sung,
their notes are sung with them.

## The edit

    line.<section>:<which>.<i> = {"words": "...", "notes": [{degree, onset, duration, slur?}, ...]}

`<section>:<which>.<i>` is a lyric key, as `lyrics.` has it: a verse by name
(`verse:wire.2`), any other sung section by its round or `last`
(`refrain:0.1`, `refrain:last.1`). `null` releases it.

Checked as one thing (`composition.check_own`):

- the notes keep every fence a tune edit keeps (`composition.check_phrase`:
  range, leaps, no overlaps, inside the line, room before the next pickup,
  melismas of up to four notes), except the count: from 1 to `OWN_MAX` (32)
  syllables, a syllable being a note not slurred onto the one before;
- the words are checked as a written line is (`check_lyric`), against that
  count instead of the tune line's.

The record marks it with the words the program sang there and their count
(`"was": {"words": ..., "syllables": 11}`), and replays from the mark.

## Kept

    composition["own"] = {"verse:wire": {"2": {"words": "...", "tune": [[d, onset, dur], ...],
                                              "melisma": {...}}}}

Grid units and the melisma's packing as `tune` and `melisma` keep them. Beside
`lines`, never in it: `lines` and `tune` are left as they were.

## Sung

Wherever a section sings the key's words, line `i` there is sung from the own
entry: its words in place of the drawn (or written) line, its notes in place of
the tune line's and of any tune edit for that line or place. The place's chords
are unchanged (they are kept by bar, not by note). In code: `form_phrases` gives
that line a copy of the phrase whose `notes` are the person's, and whose
`own` names the key, so everything that reads the tune from `form_phrases`
(realize, the band keeping clear of the tune, the lead playing it, the hymn's
organ, the MIDI file, the page) reads the same notes. `form_phrases` finds the
lyric keys from the words its caller sang, or else the rendition's held words
(`params.words`, as `handed_down` reads them).

On a line with its own count:

- **variants**: none (as on any line with a person's tune);
- **phrasing gestures**: none; the line is sung with the singer's own timing,
  as an unphrased line is. (Mapping gestures by position would put a held,
  scooped note on the wrong syllable.)
- **the choir and backing voices**: harmonize the person's notes;
- **the lineage** hands the entry down by key, as `lines`: a child that sings the
  verse sings the line with its notes;
- **the gate and the lineage's own choices** read the song's own line.

## Interoperability

- A record without `own` is unchanged, byte for byte, and sung as before.
- A record with `own` opened by a program that doesn't know it (main) sings
  the song's own line there, or a person's same-count written line if the record
  has one: nothing is dropped from the record, nothing sings out of step.
- The `line.` edit on such a program is refused ("there's no such choice"), and
  the rest of the edits keep.
- `own` lines go out in a MIDI file as notes with their lyric, like any line,
  and come back as a line of its own (below).

A `lyrics.` edit for the same line (words to the tune's count) takes the line
back to its tune line's notes: the own entry goes.

## The studio

In the note inspector of a sung line, **New syllable** splits the note in two,
the second a syllable of its own, and **Merge** sings a note on the syllable
before (the note before holds on through its time). Once the count differs
from the tune line's, a card under the note asks for the line's words ("12
syllables; the tune's line has 11"), counting as typed; **Use these words**
sends one `line.` edit with the words and the notes, **Cancel** puts the notes
back. On a line of its own every later note change goes out as the same edit
with its words, its notes are marked yours, the "everywhere / only here" switch
is hidden (it is sung with its verse's words alone), and the note card's
release is **Use the tune's line**.

## Elsewhere in the song

- **A round** (`canon.plans`) is judged on the section's lines of their own, so
  the voices sing what was measured: a line that rubs against the next one
  takes fewer voices, or none. Every voice sings the line's syllables.
- **A section a person had played** (`arrange.<section>:<n>.sung` false)
  sings no words, so its lead plays the tune line's notes there.
- **Which words sing where.** realize, the page, the band (which lays out from
  realize's lines) and the MIDI file's chords (`idioms.chord_times`,
  `midi.from_score`: `lyrics`) all take the words the score sang. A round's
  judgment and the record's explanations read the words the rendition holds,
  which are the ones sung except in a render with `--lyrics-seed`.
- **A hymn** sets its chords to the line's own notes.
- **The jazz trio** keeps the song's chords under a line of its own, as under a
  place's own tune: its changes are fitted to the song's tune.
- **A MIDI file brought back** (`notesin`): a line the file sings with another
  count of syllables, as its lyrics show, comes back as a line of its own, its
  words read from the lyrics (each on its syllable's first note, as the export
  writes them) and a note without one slurred onto the one before. A line of
  its own comes back the same way, keeping its words where the file has no
  lyrics on it. A note added with no lyric is the tune line's, refused with the
  count as before.

## Not in this draft

- the everywhere edit (every verse's line 3 with eight syllables): it would need
  every bank verse rewritten for it;
- a take played on the keyboard that changes the count (a take has no words);
- carrying gestures across a count change.
