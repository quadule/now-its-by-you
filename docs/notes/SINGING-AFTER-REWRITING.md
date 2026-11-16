# Singing after rewriting

A person's recorded way of singing (a phrasing: rounded numbers per note, `songbird/phrasing.py`) is kept by tune
line and note: `{tune line id: one gesture per note}`. The studio lets a person write lines of their own (their own
words and notes, `line.<key>`: docs/notes/OWN-COUNT-LINES.md) and blank clips (docs/notes/STUDIO-CLIPS.md). This
note is how a take keeps following the song through those.

## What was broken

- A take sung to a version with a line of its own measured that line's notes under its tune line's id and their
  places in the line (the guide's notes carry only `phrase`). Its notes up to the tune line's count became sightings
  of the tune line, one syllable off after a split, averaged with the other verses' (tests: a take of the own line
  alone gave `v1` eleven gestures); the notes past the count were dropped (`webstudio/worker.py fitted`).
- A blank clip's line (`<clip>-<i>`, not a phrase of the song) was dropped whole.
- At render time a line of its own took no gesture at all.
- The refusal "That way of singing is for another song" did not happen: `gather` only makes rows of the song's
  phrases, at their counts. A tune edited with the same count still keeps its gestures by place (unchanged here).

## The format, added to

A phrasing file keeps `fields`, `phrases` and its description as before, and may carry two more fields:

    "lines":  {"verse:wire.0": {"notes":    [[onset, length, pitch], ...],
                                "gestures": [[...] | null, ...]}}
    "habits": {"*": [...], "first.short": [...], "inside.long.up": [...], ...}

- `lines` is keyed by the key the line's words and notes are kept under (`phrase.own`: `verse:wire.0`,
  `refrain:last.1`, a clip's `verse112:0.0`). `notes` is each note's shape as the take sang it: onset and length in
  beats, to 1/48 of a beat, and pitch in whole semitones above the tonic. `gestures` has a row per note, null where
  the take didn't sing it. At most 64 lines of 1 to 32 notes.
- `habits` has a row for each kind of note heard often enough, from 22 kinds at most (`phrasing.HABITS`): a line's
  first note by its length (short under 3/4 of a beat, medium under 1.5 beats, long), any other note by its place
  (inside, last), its length and the step into it (within two semitones, a leap up, a leap down); `*` is any note.
- Every row is rounded and bounded as any gesture is (`reduce`); every shape is bounded; anything else is refused
  (`phrasing.checked_extras`, by `from_json`, the studio's Store and `received`).

A file without `lines` or `habits` reads as the plain dict it always was. With them, `from_json` gives a `Way` (a
dict of phrases with `.lines` and `.habits`), which everything that takes a phrasing takes.

## The lookup order (`phrasing.sung_gesture`, called by `realize`)

For each sung note of the lead:

1. a tune line's note: its row in `phrases`, by place (as ever);
2. a line a person wrote: its `lines` entry. If the line is sung now in exactly the shapes it was sung in, each note
   takes its own row. If it was changed since, a note takes the row of the note sung then at the same onset for the
   same length (its `tune` dropped if its pitch moved); any other note has none;
3. failing that, the singer's habit for its kind of note, else their `*` habit;
4. failing that, none: the singer's own timing.

A plain phrasing stops after 1, and gives a line of its own nothing, as before. `realize(..., told=[])` reports
each note's line, shape and which of these it took.

## Where it is made

- **The guide says what each note is.** `webstudio/guide.py score_for` keeps, beside the notes, `lines` (every line
  sung: the key of a line a person wrote, or null, and its notes' shapes) and `line_of` (each voice note's line and
  place). The released guide doesn't, and its notes are the tune's.
- **Measuring** (`tools/phrasing.py sightings`, `guide_lines`): a sighting on a line a person wrote is kept under
  `line:<key>` and never counts for the tune line; the latest take's shapes of that line win, and an earlier take's
  sightings of an older shape of it are left out. Those sightings join the singer's rules as any note does
  (`ruled`, its features read from the shapes), so they're shrunk the same way. `worker.fitted` keeps them.
- **Habits** (`tools/phrasing.py habits`): from every sighting, by kind, each person counting once; a kind needs 8
  sightings of at least 4 different notes; each field is its mean shrunk toward no habit by how far it stands out
  from the noise of one sighting (fewer with more) and the extractor's error at one note (`REPEATS`, fewer with more
  notes): `default + d * max(0, 1 - error / d²)`. Vibrato is the kind's vote. A row of no habit at all is left out.
- **The renderer only looks up.** Nothing is learned at render time.

## Turning the habits off

The studio keeps each way twice (`Store.keep_both`): with its habits, and without (its `exact` name). The Sing view
has a box, "Your way on notes you didn't sing", which picks one; a phrasing file without `habits` is the same thing
anywhere (`phrasing.without_habits`).

## Everyone's way, the choir

`blend` (everyone who has sung it, the lineage voices) combines phrases only and gives a plain phrasing: a line one
person wrote and one person's habits are theirs, and "everyone" is offered so that no single singer's way is
exposed. A choir voice takes its exact gestures only, as before.

## Telling the person

`webstudio/guide.py applies(guide, way)` counts a version's notes by where their gestures come from: `sung`,
`matched`, `habit`, `none`. A take's result carries it for the guide it was sung to (`applies`); `POST
/api/sing/guide` with `"way": <name>` carries it for the version on the page. The Sing view says it: "In this
version: 120 notes as you sang them, 4 as you sang them before the line changed, 230 the way you sing notes like
them."

## Consent

What is kept changes in kind (a summary over notes), so the consent's second line says so and its version moved
(the server's 3 to 5, the device's 4 to 6), so pages ask again:

- device: "What is kept, in this browser, is a set of numbers for each note: when you came in, how long you held it,
  how loud it was and how you slid into it, and their averages over notes alike." (tooltip: "The averages sing the
  notes you didn't sing. They stay in this browser until you choose Forget my singing.")
- server: the same first sentence without "in this browser".

## Old records

A record's `performance` holding an old phrasing sings exactly as before: no new field, no new lookup. Checked by
hand against the base commit: the score and every gesture of a version with a line of its own, a song of clips and
the song as it is, sung with a plain phrasing, whole and through a stage edition's scaling, hash the same.

## Not here

- A tune line edited with its count kept still keeps its gestures by place, whatever its notes became.
- A habit isn't conditioned on words, the beat or the section.
