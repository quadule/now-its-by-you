# Independent clips

A person may write a song of their own form: sections as clips that can be
added blank, duplicated, repeated as linked instances, deleted (the last
refrain too), reordered, lengthened and given another number of lines. This
is the additive path of [the structural boundary](STUDIO-COMPOSITION.md#the-structural-boundary).
A record without a clip arrangement takes the existing code path unchanged.

## Stored

One entry in the rendition's parameters, written by one edit path, `clips`:

    composition["clips"] = {
      "form":  ["intro", "verse", "refrain", "verse", "refrain", "bridge", "refrain"],
      "order": ["intro101", "verse102", "verse108", "refrain103", "refrain109"],
      "clips": {
        "intro101":   {"from": "intro:0"},
        "verse102":   {"from": "verse:0"},
        "verse108":   {"from": "verse:0"},
        "refrain103": {"from": "refrain:0", "lines": [{"of": 0}, {"of": 1}, {"bars": 2}]},
        "refrain109": {"role": "refrain", "sung": true, "lines": [{"bars": 2}, {"bars": 2}]}
      },
      "next": 110
    }

- `form` is the **source form**: the song's form as the program made it when
  the clips were made. It is held fixed while the clips exist (a child keeps it,
  as it keeps a person's `form.order`), so the bank still draws words for a form
  its rules accept, and every `from` keeps its meaning.
- `order` is the song as sung: clip ids, one per instance. An id that comes
  twice is a **linked repeat**: one clip, sung twice.
- `clips` holds every clip `order` names. `from` is a section of the source
  form by its arrangement id (`verse:0`); a **blank clip** has no `from` and
  names its `role` (intro, verse, refrain, turn, break, bridge, tag, outro)
  and whether it is `sung`.
- `lines` (optional; a blank clip's is required): the clip's lines, in order.
  `{"of": i}` is the source section's own line i (its tune line, its chords,
  its words as drawn); `{"bars": n}` is a blank line of n bars (1 to 8). Absent:
  the source section's own lines.
- `label` (optional, up to 24 characters): what the page calls it.
- `next`: the number the next new clip takes. Ids are never reused.

## Ids

A clip's id is its section's name in the resolved song: the source section's
name without digits, or a blank clip's role, then a number from 101 to 999
(`verse102`, `refrain109`). The letters give the band its role (`band._role`
reads a name without its digits), so a duplicated refrain is played as a
refrain, and the style's rules (the last refrain, the drop after a refrain,
which verse is in stop-time) follow the clips' order.

A song without clips reports **implicit clips** without storing anything: the
k-th section of its form is `<name><101 + k>` from that section (`verse:1` in
`intro verse refrain verse` is `verse104`). The first clip edit stores exactly
that arrangement with the change, so nothing moves when it is made.

Instances are the section ids the editor already uses: `verse102:0`, and a
linked repeat's `verse102:1`. Every existing path that names a section by its
arrangement id therefore names a clip and keeps naming it wherever it moves:

| what | path in a clip arrangement | kept by |
|---|---|---|
| words to the tune's count | `lyrics.verse102:0.<i>` | the clip (every instance) |
| words and notes (own count; a blank line's) | `line.verse102:0.<i>` | the clip |
| tune at one instance | `tune.verse102:0.<i>` | the instance (`:0` is the clip's: see linked) |
| chords at one instance | `chords.verse102:0.<i>` | the instance |
| a player's notes | `part.<player>.verse102:0.<i>` | the instance |
| length, played, build, round, players | `arrange.verse102:0.*` | the instance |
| a transition into it | `transition.verse102:0` | the instance |
| a tune line everywhere | `tune.v1`, `chords.v1` | the tune line, in every clip that sings it |
| a blank line everywhere | `tune.refrain109-0`, `chords.refrain109-0` | the clip's own line |

A blank line's tune line is `<clip>-<i>`, one rest as long as the line, with
the key's I chord in each bar.

## Words, tune, chords and parts on a clip

- **Generated layer.** A clip with `from` sings what that source section
  sings: the bank's words drawn for the source form, the tune line's variants
  and the singer's phrasing (they are kept by tune line), the band's choices
  for its role. These keep evolving down a lineage.
- **Authored layer.** Everything a person writes on a clip is kept by the
  clip id, never by a bank identity or by position: words survive whatever
  verses a descendant's bank draws, and move with the clip.
- A record's lines kept by verse identity (`lines["verse:wire"]`) or by round
  (`refrain:last`) still sing in the clip whose source section sings that key;
  a clip's own lines win over them.
- **Linked repeats** share the clip's words. A later instance's tune, chords,
  parts and arrangement are its first instance's unless it has its own: the
  view gives every instance the first instance's paths (`verse102:0`), so an
  edit on any instance edits the clip.
- **Duplicate** makes a new clip with the same `from` and `lines` and copies
  every authored entry of the original's first instance to the copy's id
  (words, lines of their own, a place's tune and chords, a blank line's chords,
  players' notes, its arrangement; not a transition, which is the seam's). The
  two share only the generated layer; editing either never touches the other.
- **Delete** takes an instance out of the order; a clip with none left goes,
  and the operation drops the edits that name it.
- **Old occurrence paths.** When clips are made, every entry the version holds
  under a source section id (`arrange.verse:1`, `part.fiddle.verse:1.2`,
  `tune.refrain:last.1`, `transition.verse:1`) is moved to the clip that
  section became, and an edit that still names a source section is refused
  ("the song is in clips: name the clip, verse104"). The editor's clip
  operations (`/api/clips`) hand back the edits rewritten that way.

## One timeline

`songbird.clips.resolved(genome, params, lyrics)` turns the arrangement into an
ordinary song once: a genome with a section per clip (and a tune line per blank
line), parameters whose form is `order`, every entry keyed as the clip
arrangement keys it, and the words for that form (each clip's from its source
section; a blank line's empty). Everything downstream reads that one
`(genome, params, lyrics)`: realize (singer, choir, band, played parts, sound
design), the clock, the studio's view, the arrangement grid, section previews,
the whole render, MIDI in and out, the lyric sheet (from the score), the piano
page, the stage plan and a section preview's window (`studio.window`, in the
native studio and the browser's). The function returns its arguments unchanged when
there is no arrangement, and an already resolved song unchanged. It is the
only place clips are interpreted.

Consequences, all from the ordinary engine running on the resolved form:

- **Seams and transitions** fall between clips; a transition is the clip
  instance's. Two different clips side by side are two sections to the band; a
  linked repeat right after its clip is one, as two verses in a row are (the
  view, the grid and the previews still show each instance).
- **The last refrain's rules** (its key lift, the canon couplet's place, the
  ending) belong to whichever refrain clip comes last. Deleting the source's
  last refrain leaves its canon unsung: the person chose that.
- **Rounds and builds** are an instance's (`arrange.<clip>:0.round`, `.build`),
  checked against its lines as before.
- **The band joining line by line**, stop-time, a bare verse, a drop: the
  program's own plan over the resolved form, by role and count.

## A blank clip

Its lines rest; the band plays the I chord under each bar for its role's
energy. A sung blank's line takes words and notes together (`line.`, the
existing `{words, notes}` format and its checks, the count free from 1 to 32);
an empty line is a rest. Chords (`chords.<clip>-<i>`, or one instance's),
players' notes and drum strokes (`part.`) and the arrangement (`arrange.`) are
written as anywhere else. No bank verse, couplet or stanza is drawn for it.

## Bounds

- 1 to 48 instances in `order`; at most 48 clips; ids 101 to 999.
- 1 to 16 lines a clip; a blank line 1 to 8 bars; a clip at most 64 bars;
  the song at most 768 bars (48 sections of 16).
- Each clip's id must fit its source or role; `from` must be a section of
  `form`, and `form` a form the song can sing.
- The existing bounds on notes, parts and words apply unchanged to each line.

## Inheritance

A child inherits the arrangement with the rest of the composition: the same
source form, clips and order, the authored layer as written. The generated
layer under it still evolves: the bank's words for the source form, the tune's
variants, the band, the style, the machine's tempo and key. `clips: null`
gives the song its form back: what the record keeps by a clip id waits,
unheard, and an edit that still names a clip is refused ("there is no section
called verse112").

## For the editor

Read (`/api/song`, `composition`):

- `clips`: `{"value": <the arrangement as stored, implicit or not>, "stored":
  bool, "clips": [{"id", "label", "role", "source" (a source section id or
  null), "sung", "bars", "lines" (each `{"phrase", "of", "bars"}`), "instances" (indexes in sections),
  "authored" (bool: the clip has words, notes, chords, parts or arrangement of
  a person's), "can": {"delete", "duplicate", "repeat", "lines"}: true, or why
  not}], "roles": [...], "bounds": {...}}`.
- each section: `id` (`verse102:0`), `clip` (`verse102`), `instance` (0, 1...),
  `label`, and its phrases with the fields the editor reads already
  (`own_path`, `lyric_path`, `place`, `chords_path`, `part_key`, `bounds`,
  `notes`, `chords`...). A blank line's `path` and `chords_path` name its own
  tune line.

Write:

- `clips`: the whole arrangement, as above (null: the song's own form).
- `POST /api/clips` with `{"edits": {...}, "op": ...}` answers `{"edits":
  <the whole edits map, rewritten>, "clip": <the clip made, if any>}`:
  - `{"op": "duplicate", "clip": "verse102", "at": 3}` (at: the place in
    `order`; default after the original)
  - `{"op": "repeat", "clip": "verse102", "at": 3}` (a linked instance)
  - `{"op": "delete", "at": 2}` (an instance; a clip with none left goes)
  - `{"op": "blank", "role": "verse", "sung": true, "bars": 8, "lines": 4, "at": 1}`
    (bars shared evenly over the lines, or `"line_bars": [2, 2, 2, 2]`; `sung`
    is true by default for a verse, refrain, bridge or tag)
  - `{"op": "move", "from": 4, "to": 1}`
  - `{"op": "lines", "clip": "refrain103", "lines": [{"of": 0}, {"bars": 2}]}`
    (`"lines": null`: a clip from a section sings that section's own lines again)
  - `{"op": "label", "clip": "verse102", "label": "The wire"}` (a name of its own; empty or null: its role's)
  - `{"op": "empty", "role": "verse", "sung": true, "bars": 8, "lines": 4}` (the song this one blank clip:
    every other clip goes, with the edits that name it; the rest of the record stays)

The first operation on a song without clips stores its implicit clips with the
change, and the edits that named the form's places name their clips (the
shape's `form.*` edits go: the source form is the shape they made).

A new song of three sections, as one edits map (H's seed has ten sections,
`intro101` to `tag110`; three `blank` operations and ten `delete`s make it, or
it is written by hand):

    {"clips": {"form": ["intro", "verse", "refrain", "turn", "verse", "refrain",
                        "turn", "bridge", "refrain", "tag"],
               "order": ["intro111", "verse112", "refrain113"],
               "clips": {"intro111":   {"role": "intro", "sung": false, "lines": [{"bars": 4}]},
                         "verse112":   {"role": "verse", "sung": true,
                                        "lines": [{"bars": 2}, {"bars": 2}, {"bars": 2}, {"bars": 2}]},
                         "refrain113": {"role": "refrain", "sung": true,
                                        "lines": [{"bars": 4}, {"bars": 4}]}},
               "next": 114},
     "line.verse112:0.0": {"words": "here is a new song",
                           "notes": [{"degree": 5, "onset": 0, "duration": 1},
                                     {"degree": 6, "onset": 1, "duration": 1},
                                     {"degree": 5, "onset": 2, "duration": 1},
                                     {"degree": 3, "onset": 3, "duration": 1},
                                     {"degree": 1, "onset": 4, "duration": 2}]},
     "chords.verse112-0": [["I"], ["IV"]],
     "part.harp.intro111:0.0": [[0, 96, 0, 100], [192, 96, 4, 90]]}

## In the studio

What the score (`songbird/studio/score.js`, its pure parts in `model.js`) does with the above:

- **Arrange's header row** is the clips in order: each section's label from the view, a linked repeat's instances
  with a chain mark and a colour of their own, a person's clips (blank, copied, repeated, moved: `model.js`
  `clipsYours`) in the second ink. **+** after the last section adds a blank section after the one selected (at the
  end when none is): an 8-bar sung verse of 4 lines, or what the column's **New section** says (role, sung or played,
  bars, lines).
- **The section's column** has **Duplicate**, **Repeat** and **Delete** (disabled, the engine's `can.*` sentence as
  the tooltip, where refused), **Lines** (each line's bars; a blank line's with − +; **+ line** adds a blank 2-bar
  line, **− line** takes the last away; **Reset** gives a clip from a section its own lines), **Name** (`op label`),
  and **Length**: a blank clip's is its lines' (`op lines`, the bars shared evenly over them, `model.js` `evenBars`,
  as op blank shares them); any other section's is the arrangement's `arrange.<id>.bars`, unchanged (a blank clip's
  tune has no sung notes, so `takeover.fit` gives it no other length: the two never apply to one section).
- **Keys** on a focused section header: ⌘/Ctrl D duplicates, Delete or Backspace deletes (never with a note, a cell
  or a field focused); ⌘/Ctrl ← → and Earlier / Later move.
- **A move** is one function, however it is made: without stored clips, the shape's `form.order` as before; where
  that order is refused (a verse past another) or the song has clips, `op move`.
- **Each operation** is one request (they run one after another, each on the edits the one before left) and one step
  of the history, labelled in words ("Duplicate Verse 2"); what it made, or moved, is selected, and keeps the keys
  when the keys made it.
- **A blank sung line** opens empty in the melody roll: a note drawn into it, or **Write words**, starts its draft;
  words written first get notes (`model.js` `blankTune`: a syllable a beat where there's room, from the third up to
  the fifth and home to the tonic). On the Page it is an empty field; its words take their notes with them
  (`line.`). The Page and its lyric sheet are the clips in order (the view's `words`, `explain.clip_words`), each
  line as it reads (no syllable hyphens, no says), a linked repeat written once; a clip that sings its source's
  lines as they are keeps the bank's choices of words.
- **Tools → Empty song** (`op empty`), once confirmed: one blank verse of 8 bars and 4 lines; key, tempo, style and
  band as they were.
- **The Shape** with clips is how many sections and their names in order, said to be Arrange's; its Reset is
  `clips: null`. **The words** card says whose words the sections sing: the song's, with lines of yours, your own,
  or none.
- **Section contents** paste only into a section of as many lines (refused, saying how many); a blank line's
  contents are its chords and players' notes.

## Not changed by clips

- The bank's choices of words (which verse, couplet and stanza each section
  draws) are the source form's: they choose the generated layer the clips sing
  from, and a clip that sings its source's lines offers its source's.
- A whole render's record keeps the source form in `params.form` and the
  arrangement beside it; its lyric sheet is read from the score, as a record
  with a person's lines has it.

## Out of scope

Per-track clips, automation lanes, audio clips; splitting a clip; inserting a
line in the middle of a clip with its content moved (content is kept by line
number: lines added or taken away at the end leave the others where they
are); a clip's own tempo, key or meter; a generated layer for a blank clip
(the program writes no words or tune into one).
