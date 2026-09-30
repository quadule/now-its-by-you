# The studio, redesigned: one score, one inspector (2026-09-29)

The artist: "Let's do everything we can to make the studio more flexible given the report without making
the UI look too busy — we can redesign anything if there are concepts we can combine or simplify or make
more like conventional DAW apps."

This page is the information architecture for that: what combines, what goes, where every current thing
lands, what is borrowed from a DAW and what is refused, and what is left for the artist to decide. The
clickable mockup beside it is `docs/design/studio-redesign.html` (one file, no network, fake but realistic
data from *Now It's by You* as Ada sings it today); its pictures are `docs/design/studio-redesign-*.png`.
Nothing in songbird/ changes with this page; it is a design, made before the engine work it is designed for
(per-section arrangement, sound design, transitions, wider tempo, sevenths, per-appearance scope, freer
melody editing) so that work has a place to land.

## The core idea

The studio today is a **tune book with four chapters** (Words, Tune, Sound, Other versions), each chapter a
pile of cards and panels, and every new ability (chords, stems, the piano, players over MIDI, singing in the
browser, playing a part in) has been another card on the pile. The EDM test found the *engine's* limits
(docs/STUDIO-EDM-TEST.md), but it also filmed the page's: 108 actions across four chapters, scrolling a lot,
a transport in one place and a player in another, the band in Sound and its parts in Tune, "the last
refrain starts stripped down" said in a card's fold and not choosable anywhere.

The redesign keeps the tune book and gives it a **score**. One page, three views of the same song, one
inspector:

- **A transport**, one bar across the top, fixed: play (sketch or sung), stop, loop, click, where we are
  (bar and section), tempo, key and scale, the dice, undo and redo, record. It replaces the header's
  toolbar, the "simple changes" row, the sketch's own transport and the player at the foot.
- **Three views** of the song, as a DAW has Arrange and Mix, plus the tune book's own **Page**:
  - **Page**, the words as sung, set as they are today: the visitor's first screen, and the reading view.
  - **Arrange**, a timeline: the sections as regions on a ruler of bars, and under them one track per
    player (the singer first, then the voices before, then the band). The cell where a track meets a
    section says whether that player plays there and how hard; a section's notes and chords open under
    the timeline when asked for. This is where the arrangement engine's new abilities land.
  - **Mix**, channel strips: one per player, gain, mute and solo, the pump (when the engine has it), the
    room and the voice as strips of their own.
- **One inspector**, a column on the right (a sheet from the foot on a phone), that shows *whatever is
  selected*: a section, a player, a cell, a chord, a note, a line of words, a seam between two sections,
  the singer, the room. It replaces the Sound cards, the note inspector, the chord card, the word chooser,
  the "write your own lines" fold, the Players panel and the style card's chips, each of which becomes one
  *state* of the same column. Every state has the same shape: **what it is** (its name, in a rubric), **what
  it's set to** (in the ink that chose it), **change it** (the controls), **why** (the program's reasons,
  folded, as the cards have them), and **the program's own** (a release, as Reset/Restore are now).
- **One door in and out**: *Your tools*, a sheet from the transport's end with two columns, *Take it
  out* (record, MIDI, the parts, the piano page, a draft file) and *Bring it in* (a MIDI file, play a part
  in, a draft file, sing it), replacing the finish panel, the export panel, the two "Learn it at the
  piano" links and the perform panel.
- **Time and other computers** become a drawer under the transport's version line (the line that already
  says "today, from the song as it began, sung by Ada"), not a chapter: they are ways of asking *which*
  version is on the page, and belong beside its name.

The identity stays: paper and two inks, the rubric red for section names and the playhead, the double
rule, index cards where a card is still a card, no textures, system fonts, no libraries, no build step. The
score borrows from a DAW what a non-musician already understands from any timeline (a ruler, regions,
tracks, a playhead, a fader) and refuses the rest (below).

## The anatomy of the page

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ SONGBIRD · STUDIO      Now It's by You                                          ? Help    │
│ ○─○─●  today, Tuesday 29 September 2026 · from the song as it began · Ada  [Time ▾]      │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ ▶ ■ ⟳ ♩  Refrain 1 · bar 13   ♩= 94  D major   ⚄ New performance   ↶ ↷   ● Record  Tools│  the transport
├───────────────────────────────────────────────────────────────┬──────────────────────────┤
│ Page · Arrange · Mix                     3 choices are yours  │ REFRAIN 1        (rubric)│
│                                                               │ 8 bars · sung · the      │
│  ruler   1        5      13      21  23      31      39  41   │ program's own            │
│  regions [Intro][Verse 1 ][Refrain 1][T][Verse 2 ][Refrain 2] │                          │
│  singer  ░░░░░░  ▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓▓▓ ░  ▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓▓▓ ..  │ Length  4 · 8 · 16 bars  │
│  voices  ······  ········ ········· ·  ········ ········· ..  │ Who sings  the singer ▾  │
│  chords  Bm G D A  D A D  D G A Bm  G  D A D    D G A Bm  ..  │ Energy  soft · plays · ▮ │
│  lute    ▮▮▮▮▮▮  ▮▮▮▮▮▮▮▮ ▮▮▮▮▮▮▮▮▮ ▮  ▮▮▮▮▮▮▮▮ ▮▮▮▮▮▮▮▮▮ ..  │ Moment  none · build ·   │
│  guitar  ▮▮▮▮▮▮  ▮▮▮▮▮▮▮▮ ▮▮▮▮▮▮▮▮▮ ▮  ▮▮▮▮▮▮▮▮ ▮▮▮▮▮▮▮▮▮ ..  │         drop · stripped  │
│  ...                                                          │ ▸ Why the program chose  │
│  ── the notes of Refrain 1 (opened) ─────────────────────────  │   this                   │
│  harmony  D          G     A        D        Bm   ...         │ Open the notes  ▶ Hear it│
│  roll     ▬ ▬▬  ▬       ▬▬ ▬  ▬▬▬                             │ The program's own        │
└───────────────────────────────────────────────────────────────┴──────────────────────────┘
```

The page is a single column of three fixed bands (masthead with the version line, transport, view tabs)
over a body that scrolls, with the inspector beside the body. Nothing is fixed at the foot any more: the
player's job (what is playing, how far, making it) moves into the transport's position field, and Record
moves to the transport's end where a DAW keeps it.

## The transport

One row, always in view, left to right:

| Control | What it is | Was |
|---|---|---|
| **▶ / ■** | Plays what is selected (a section, a phrase, the song) from the playhead. One button; a **Sketch / Sung** switch beside it says *how*: the sketch is instant (oscillators, chords, bass, the band's parts plainly, or over MIDI); sung makes the real thing and takes seconds. Space plays the sketch; Shift+Space the sung version. | Hear the song; Play sketch; Hear sung section; the ▶ beside each part; the foot player's play/pause |
| **⟳ Loop · ♩ Click** | The sketch's loop and metronome, as now, as toggles. | Loop, Click |
| **Position** | "Refrain 1 · bar 13 · 0:31", and while something is being made, the progress there ("making Refrain 1, the band, 40%", "waiting its turn, 2 ahead, about 3 minutes" in a public studio); click it to jump the playhead, drag the ruler to scrub. | The foot player's title, sub, bar and time |
| **♩ = 94** | Tempo, a number to type or drag; its bounds are the style's (the engine work: "wider/style-aware tempo"); when the person changed it, in the second ink with "was 94" on hover. | Tempo in the simple-changes row; the Tempo card; the sketch transport's 94 BPM |
| **D major** | Key and scale as one chip; opens a small popover of notes and modes (the chips the Key card has). | Key and Scale selects; the Key card |
| **⚄ New performance** | Chance drawn again for everything not pinned by a person. | New performance |
| **↶ ↷** | Undo and redo, with the last edit's name in the tooltip. | Undo, Redo |
| **● Record** | Records the whole rendition (opens the *Your tools* sheet on its *Take it out* side, with the recording's progress and the file when it is done). | Record it (three places) |
| **Tools** | Opens *Your tools*. | Sing, record & pass it on; Take it into your own tools; the Learn-at-the-piano links |

Under the masthead, the **version line** stays as it is ("Your version today, Tuesday 29 September 2026,
from the song as it began, sung by a made-up machine called Ada", with the lineage marks), and gains one
control at its end, **Time ▾**, which drops the *Through time* timeline and the *Other computers* table
down as a drawer over the body (the same six-year picture, the day slider and steps, the machine table with
▶ for theirs and "make one up"). It closes with Esc or the same button. The "N choices are yours · hear it
as the program would sing it · Reset song" bar also stays on the version line's right, in the second ink.

## The three views

The view tabs (Page · Arrange · Mix) sit under the transport, in the tune book's serif as the four tabs
are now. Keys 1, 2, 3 switch them.

### Page

The words as sung, as they are today and not busier: rubrics, the copybook margin rule, the serif, the
dashed underline under a word that can change, a person's lines in the second ink, ▶ beside each section.
Three things move out of it into the inspector: the "Song rules & alternatives" fold, the "Write your own
lines" editor, and the verse/couplet/head dropdowns' long lists. Clicking a section's rubric selects the
section (the inspector shows it: which verse, the couplet, the head, the refused alternatives and why,
*Write your own lines*); clicking an underlined word still opens its native dropdown in place, because that
is the fastest thing on the page and the mockup keeps it. Instrumental sections read as now ("the whistle
plays the tune in") and gain one word in the second ink when a person changed what plays there.

### Arrange

A timeline, the first thing a musician looks for and the thing the EDM test could not find. Its parts:

- **The ruler**: bars, numbered, with the section names as rubrics over their spans; the playhead in the
  red. Drag on the ruler to scrub; click to place the playhead.
- **The regions**: one per section, in proportion to its length (a 2-bar turn is narrow), each carrying
  its name, its length and a miniature of its melody (the overview's minis today). Drag to reorder (the
  backend checks, as now), or ← → in the inspector. A region's edge shows its length; drag it to 4, 8 or 16
  bars once the engine allows, or choose in the inspector.
- **The tracks**, one row per player, in this order: the singer (its cells show the first words of each
  sung section, italic "instrumental" where nobody sings), the voices before (the choir, where it joins),
  the chords (each section's chords by name, in the key), then the band: lute, guitar, harp, bass, fiddle,
  whistle, frame drum, drone for the ballad band, or the style's own players. Each track has a head at the
  left with its name, M and S, and a small route mark (here · MIDI · off) once Players are routed.
- **The cells**: where a track meets a section. A cell shows *whether* the player plays there and *how
  hard*, as a bar in the ink that decided it: out (empty), soft, plays, hard (the engine's "pattern/energy";
  three levels are enough for a cell, the inspector has the pattern's name). A cell the program drew is in
  the ink; one a person set is in the second ink with a small hand mark. Click a cell to select it (the
  inspector: that player in that section); click a track head for the player everywhere; click a region for
  the section.
- **The seams**: the thin line between two regions is a control too. Click it and the inspector offers the
  transition into the next section (the engine's risers, sweeps and rolls): none, a riser, a sweep, a snare
  roll, a stop. A seam with something set shows a small mark in the ruler.
- **The notes**: a region's "Open the notes" (or a double-click, or Enter) opens the piano roll under the
  timeline for that section, as the editor is today: the phrase strip, the harmony lane with its chord
  buttons, the roll with syllables, snap and zoom. Selecting a note or a chord puts it in the inspector.
  Only one section's notes are open at a time; the timeline above stays.

What the grid makes possible that the cards never could: reading the whole arrangement at a glance ("no
kick in the verse, everyone in the refrain"), *choosing* the entrances, breakdowns and stripped starts
that are drawn by chance today (the shape of the EDM test's kick table, made rather than found), an
instrumental drop (the singer's cell set to out in a refrain), a build (a section's *moment*), and a
16-bar drop.

### Mix

Channel strips, one per player, left to right in the track order, then three strips that are the room and
the singer: **Voice** (over the band: forward; how close: intimacy), **Room** (how much: space; how long it
rings: rt60; how soon it answers: predelay; how wide: width), and **Master** (the loudness, read-only, with
the program's reason). A strip has a fader (0 to 200 %, the value in the ink that set it, the program's
level as a faint tick when the person moved it), M and S, and where the engine has it a **Pump** knob
(sidechain from the kick, on pad and bass strips) and a **Patch** name that opens the player in the
inspector. No pan: the engine places players itself (width is the room's), and a fader that does nothing
is a lie; if the engine gains per-player placement, pan goes here and nowhere else.

## The inspector

One column, 320 px on a desktop, under the view tabs on the right, scrolling on its own. It has one shape
in every state, so a visitor learns it once:

```
 ┌───────────────────────────────┐
 │ RUBRIC  (what it is)      ✕   │  a section name, a player, "Bar 2 · chord 1 of 2", "Verse 2, line 3"
 │ what it is set to             │  in the ink that set it: the program's, or the second ink
 │ ─────────────────────────────  │
 │ change it                     │  the controls, few, the same kinds everywhere: chips, a slider, a select
 │ ...                           │
 │ ▸ Why the program chose this  │  folded: the reason tags (machine · time · chance · the version before ·
 │                               │  the song · you), as the cards' "How this choice works"
 │ ▶ Hear it     The program's own│  audition what is selected; release the person's choice
 └───────────────────────────────┘
```

Its states, and what each one gathers up:

| Selected | Shows | Change it | Gathers up (today) |
|---|---|---|---|
| **Nothing** | the song: style, band, shape, singer in one card each as *summaries*, each a button into its state | the style's chips (style, feel, ending, backing, lift) | the Style card; the Shape card's "Use the song's shape"; the Voices-before and Machine cards as lines |
| **A section** (a region, or a rubric on the Page) | its name, length, sung or not, its words (first line), which verse or couplet | length 4 · 8 · 16; who sings (the singer · nobody: an instrumental); energy for everyone (soft · plays · hard); moment (none · build · drop · breakdown · stripped start); ← Earlier / Later →; the verse/couplet/head choosers and the refused alternatives with why; *Write your own lines*; Open the notes | the section strip's Earlier/Later; the Shape card's verses and parts (as "add a part" chips in the empty state and here); the Words chooser, the rules fold, the author fold; the style's chance-drawn "entrances / breakdown / stripped" options, now choosable |
| **A player** (a track head or a strip) | its name, its instrument, where it plays (a row of the sections), its level | level; pattern where the style has one; patch / kit / filter (engine work); route (here · MIDI channel n · off); program change; *Sit out everywhere* | the Band card's players and mixer strips; the Players panel's per-player selects; "Who leads where nobody sings" (on the lead player) |
| **A cell** (player × section) | "lute in Verse 1: plays, medium, the program's" | out · soft · plays · hard; the pattern here; *Everywhere this player* / *Everyone in this section* shortcuts | nothing today: this is the arrangement engine's new surface |
| **A seam** | "Into Refrain 1" | transition: none · riser · sweep · roll · stop; length in beats | nothing today |
| **A chord** (in the harmony lane) | "Bar 2 · chord 1 of 2: G, the song's own" with its rubs | in the key (one-press chips), root, quality (with 7, maj7, add9 when the engine has them), bass, chords in this bar; **scope: here only · everywhere this line is sung** (engine work) | the chord card |
| **A note** | "Note 3 of 11: num, F♯4, degree 3" | pitch, start, length; the phrase tools (step up/down, soften leaps, even rhythm to the snap, restore phrase); split, tie, add, delete when the engine allows; the same scope switch | the note inspector; Shape phrase; the health line |
| **A line of words** (on the Page) | "Verse 2, line 3", the line, its syllables | the writing box with the live count and the pronunciation check; *Use the song's line* | Write your own lines |
| **The singer / Voice** | a high voice, clear...; the phrasing | whose way (the song's own · a person's · everyone's); forward and intimacy | the Singer card; the Mix card's voice sliders |
| **The room** | a room like a living room | space, rt60, predelay, width | the Mix card's room sliders |
| **Time** (the drawer) | the timeline and the machines | the day slider, the steps, the machine table, make one up | Other versions |

Two rules keep it from becoming the pile of cards again: **the inspector never shows two things** (the
song summary is a list of doors, not a stack of cards), and **anything with more than six controls folds
the rest under "more"** (the room's rt60 and predelay; a player's program change; a note's split and tie).

## Your tools: in and out

One sheet, from the transport's end, in two columns, so the musician who wants to leave with files and the
one who wants to bring some in find them in the same place:

| Take it out | Bring it in |
|---|---|
| **● Record it**: one FLAC, the program inside, the person's choices marked; the progress, then the file (or *Download it* in a public studio, with how long it keeps) | **A MIDI file**: notes for a phrase or a part (the merging perform.js): drop it here or choose it; it says what it found (a melody, a bass part) and where it will go |
| **MIDI**: the score as a format 1 file, at once | **Play a part in**: a MIDI keyboard, live, into the selected track or phrase, with the sketch as the guide |
| **The parts (stems)**: each part alone and dry, zipped with the MIDI, a render's wait | **A draft file**: a saved `.songbird.json` |
| **The piano page**: your version to learn on a keyboard, in a tab | **Sing it**: the singing page in a tab (a checkout), or the browser's own singing (the web studio), and the phrasing it made offered on the singer |
| **A draft file**: save the changes, no audio, for later | |

The sheet's foot says where files land ("into renders/ on this computer") and the public studio's limits
(the "open to the public" sentences studio.js has). Players' routing (here · MIDI · off), Connect MIDI,
Panic and "everyone to MIDI, as the file" live on the *player* inspector and on the track heads, not here:
they are how a player sounds, not a file.

## What is borrowed from a DAW, and what is refused

Borrowed, because a person who has seen any timeline (a video editor, a phone's voice memos) reads it
without being told:

- **One transport at the top**, with play, stop, loop, click, position, tempo, key, record.
- **A ruler of bars and a playhead** that is the same red line in every view (the rubric red, as today).
- **Regions on a timeline** for the sections, dragged to reorder, with an edge to drag for length.
- **Tracks with heads** (name, mute, solo) and a **track × section grid**, as a drum machine's pattern
  page or a session view: the cheapest way to say who plays where.
- **Channel strips** with faders for the mix, a *Voice* and a *Room* strip where a DAW has a bus.
- **An inspector that shows the selection**, as every DAW's right-hand panel does.
- **Keyboard habits**: Space for play, ⌘Z, arrows to nudge, M and S, Enter to open, Esc to close.
- **Snap and zoom** on the roll, as now.

Refused, because the studio is for a visitor who may not be a musician, and because the point of the
page is what the program chose and why:

- **No empty project.** The page opens on a finished song, always; nothing is ever blank, and there is no
  "new track". The players are the style's; a person can sit one out, not add a synth from a menu.
- **No audio clips, no waveforms, no automation lanes.** The regions are *sections of a song* with names
  in the rubric red and a miniature of their tune, not blocks of audio; a cell says *plays, hard*, not a
  curve. (The stems are how a person gets waveforms: in their own DAW.)
- **No plug-in racks, no routing matrix, no buses.** The sound design that the engine will add (patch,
  filter, kit, pump) is three or four named choices on the player's inspector, in words ("a pluck", "a
  saw stack", "a pumping pad"), never a rack of knobs.
- **No pan, no EQ, no meters** until the engine has them; a control that does nothing is refused (the
  Mix view's Master strip is read-only for this reason).
- **No grey-on-black.** The score is on paper, in ink; the dark scheme is the page by lamplight. No icon
  toolbars: buttons keep their words (▶ Hear it, not a glyph alone), and the few glyphs used (▶ ■ ⟳ ♩ ⚄
  ● ↶ ↷) have their names in the tooltip and for a screen reader.
- **No hidden modes.** No tool palette (pencil, scissors); dragging a note moves it, dragging its edge
  lengthens it, and the inspector has the numbers.
- **The "why" stays.** A DAW never says why a fader is where it is; here every value carries its reason,
  folded, in every state of the inspector, and a person's choices are in a second ink everywhere,
  including on a fader and in a cell. That is the studio's identity and it is not traded for a cleaner
  strip.

## How chance and a person's choices coexist, view by view

The rule is the one the studio already has (docs/STUDIO.md, "How edits flow"): the program chooses
everything; a person's choice is one entry in a flat map that pins one thing, and everything else keeps
moving with the day, the machine and the dice. The redesign shows that rule the same way everywhere:

| View | The program's choice looks like | A person's looks like | Drawing chance again |
|---|---|---|---|
| **Transport** | tempo 94, D major in the ink | 125, D minor in the second ink, "was 94" on hover | leaves them |
| **Page** | the words in the ink, a dashed line under a word that can change, "new this time" tags | the word, the line, the whole verse in the second ink, a hand mark by the rubric | draws the words again around the ones pinned |
| **Arrange** | cells as bars in the ink, with a faint chance mark (⚄) on a cell the style drew by chance (an entrance, a stripped start); regions in the program's order | cells in the second ink with a hand mark; a moved region with the hand mark by its name; a seam's transition mark | draws the cells with the chance mark again and leaves the person's; the program's arrangement decisions are no longer random once *set* (the engine's "deterministic instead of random") |
| **Notes** | notes in the ink, chords in the ink | the moved notes and the person's chords in the second ink, as today; a rub outlined in the red | leaves them |
| **Mix** | the fader at the program's level, the reason under it | the fader in the second ink with the program's level as a faint tick beside it | leaves them |
| **Inspector** | the value in the ink; "Why the program chose this" with its tags | the value in the second ink; "you" first among the reasons; *The program's own* offered | |

And one new affordance, because the grid makes many small choices cheap: a person can **pin what the
program drew** (a cell's ⚄ becomes a hand mark without changing the value: "keep this"), so a lucky
arrangement survives the next New performance. It is the same edit map (the value written explicitly),
so nothing new travels in the record.

## On a phone

The same page, folded (the mockup's "Phone" button shows it; the CSS is container queries, so a narrow
window and the framed phone lay out the same):

- **The transport is one row**: ▶, the position (tapping it is the sketch/sung switch and the loop and
  click, in a small popover), ♩94 · D as one chip, ● and *Tools*. Undo and redo and the dice go under
  *Tools*' first row. The version line folds to one line ("today · Ada · Time ▾").
- **The views are a bottom bar** (Page · Arrange · Mix), where a thumb is.
- **The inspector is a sheet from the foot**, opening when something is selected, half height, with a
  handle to pull it up; Esc or the ✕ closes it. Nothing is selected on arrival, so the Page reads as the
  tune book it is.
- **Arrange scrolls sideways** with the track heads stuck to the left and the ruler stuck to the top; the
  cells are 28 px tall and a section is at least 44 px wide (a turn included), so the grid is a little
  wider than the song's proportions on a phone. The notes open full-width under the grid, read-only
  below 600 px (dragging a 9 px note with a thumb is not editing; the inspector's pitch, start and length
  steppers are, and they work), which is the decision flagged below.
- **Mix strips scroll sideways**, each 72 px wide, faders vertical and tall; Voice and Room after the
  players.
- **Your tools** is a full-height sheet with the two columns stacked.

## Keyboard

| Key | Does |
|---|---|
| Space · Shift+Space | play or stop the sketch · the sung version, of what is selected |
| L · K | loop · click |
| ⌘/Ctrl Z · ⌘/Ctrl ⇧ Z | undo · redo (outside a text field, as now) |
| 1 · 2 · 3 | Page · Arrange · Mix |
| ← → | select the previous or next section (in Arrange and on the Page); in the roll with a note selected, nudge it; ⇧ ← → its length (as now) |
| ↑ ↓ | select the track above or below; in the roll, a note's pitch |
| Enter | open the selected section's notes; Esc closes them, then the inspector, then a drawer |
| M · S | mute · solo the selected track |
| ⌘/Ctrl ← → | move the selected section earlier or later |
| R | record |
| T | the Time drawer |
| ? | help |

Every shortcut is written beside its control in the help dialog, and none fires inside a text field.

## Accessibility

- **The grid is a grid**: `role="grid"` with the track heads as row headers and the section names as
  column headers, each cell a button named in words ("lute in Verse 1: plays, medium; the program's
  choice"), so a screen reader reads the arrangement as a table and arrow keys move through it.
- **The inspector is a landmark** (`complementary`, labelled by its rubric); selecting something moves
  focus to its heading only when the person asked with the keyboard, never on a click.
- **Nothing is said by colour alone**: the second ink is always paired with a hand mark (✎) on a cell, a
  region, a fader and a rubric; energy is a bar *and* a word; the playhead is a line and a position in
  words; a rub is an outline and a sentence.
- **Contrast** stays at 4.5:1 for text in both schemes (the tokens are identity.css's, unchanged); the
  cells' energy bars are at 3:1 against the paper as UI components.
- **Live regions** announce what changed after an edit ("Verse 1: the lute now plays hard"), a render's
  progress in the position field, and a refusal with its reason and its alternative, as the toast and the
  problems bar do now.
- **Touch targets** are 44 px on a phone (cells 28 px tall but 44 wide, and a cell's row is one tap
  target with the arrow keys as the fine tool); drags have keyboard twins (Earlier/Later, the note's
  steppers, the fader's arrows).
- **Reduced motion** turns off the sheet's slide and the playhead's smoothing, as the identity does.

## Behind "more"

Kept, but folded, so the first look at every state is short:

- On the transport: the sketch's *Chords* and *Bass* ticks (under the Sketch/Sung switch's popover).
- On a player: program change, the MIDI channel, Panic, "everyone to MIDI / everyone here / as at first".
- On the room: rt60 and predelay. On the singer: whose way (when only the song's own exists, the select
  is hidden).
- On a note: soften leaps, even rhythm, split, tie, delete.
- On a section: the couplet/head/verse choosers when there is only one allowed choice; the refused
  alternatives (a fold, as now).
- The **Loudness**, **Your machine**, **Voices before** and **The melody (variants)** cards become lines in
  the empty inspector's song summary with a "?" each, not cards: none has a control a person needs often.
- The help "?" beside each area becomes one "?" on each view tab and one on the inspector's rubric, with
  the same two or three sentences; the Help dialog and the four-step tour stay (the tour's steps become:
  hear it, change something in the transport, select a section, record it).

## Every current feature, and where it goes

Read from songbird/studio/index.html and the scripts (studio.js, composer.js, author.js, players.js,
export.js, learn.js, drafts.js, help.js, and perform.js as it merges). "Same" means the control is kept as
it is; the home is where it sits on the new page.

### The header and the simple changes

| Today | New home |
|---|---|
| Songbird · studio kicker, title, Help | the masthead, same |
| the version line, the lineage marks, its "?" | the version line, same, with **Time ▾** at its end |
| Hear the song (primary) | transport ▶ with nothing selected (the song), Sung |
| Sing or record / Record it (header) | transport ● Record; Sing under *Tools › Bring it in* |
| Undo, Redo, "Your edits stay in this browser" | transport ↶ ↷; the sentence in the Tools sheet's foot |
| Tempo, Key, Scale (selects and number) | transport ♩ and the key chip |
| Length 3:33 | the position field's right end |
| New performance, the draw's hint | transport ⚄ |
| "N choices are yours · hear it as the program would · Reset song" | the version line's right, same |
| the problems bar ("Couldn't keep your…") | a line in the inspector's state for that thing, and the live region |
| Shared preview / open-to-the-public badge and sentences | the masthead badge, same; the sentences in the Tools sheet's foot and the position field |

### Words

| Today | New home |
|---|---|
| the sections as sung, rubrics, margin rule, serif | **Page**, same |
| ▶ beside each section | same on the Page; and the region's ▶ in Arrange |
| the verse / couplet / head dropdown by the rubric | the **section** inspector (the dropdown stays by the rubric too, as the fastest path) |
| in-line word dropdowns (dashed) | same, in place |
| Song rules & alternatives (the refused, with why and where else) | the **section** inspector, folded |
| Write your own lines, syllable counts, Use these lines, Use the song's line | the **line** inspector (click a line); the section inspector's *Write your own lines* opens the first line |
| Reset words | the section inspector's *The program's own* |
| "handed down", "new this time", "kept" tags | same, by the rubric |

### Tune (Arrange)

| Today | New home |
|---|---|
| Play sketch, ■ Stop sketch, Play: this phrase / this section / the song | transport ▶ ■ with the Sketch/Sung switch; *what* plays is the selection |
| Loop, Click, Chords, Bass | transport ⟳ ♩; Chords and Bass ticks under the switch's popover |
| 94 BPM in the sketch bar | transport ♩ |
| Hear sung section | transport ▶ Sung with the section selected; the inspector's ▶ Hear it |
| the whole-song overview (minis, in proportion) | the **regions** on the ruler (they are the overview, with the tracks under them) |
| the section strip (cards with bar numbers), drag to reorder, Earlier / Later, Restore order | the regions, drag; the section inspector's ← →; *The program's own* on the section (order) |
| "Intro / Melody · Edit a phrase once; every appearance follows" | the notes' heading, with the **scope** switch (here only · everywhere) when the engine has it |
| the phrase strip | same, over the roll |
| Snap, Zoom | same, at the roll's right |
| the harmony lane's chord buttons, rubs marked | same, in the roll |
| the chord card (in the key, root, quality, bass, chords in this bar, ♪, Restore chords) | the **chord** inspector, plus 7 / maj7 / add9 and scope when the engine has them |
| the piano roll: drag pitch, time, length; keys column; the note inspector's pitch, start, duration; audition | same roll; the **note** inspector |
| Shape phrase: ↓ Step, ↑ Step, Soften leaps, Even rhythm, Restore phrase | the note inspector's *Phrase* row (step up/down); soften, even rhythm (to the snap: the bug), split, tie under *more*; *The program's own* |
| the health line (syllables preserved, range, leaps, shared appearances) | one line under the notes' heading |
| Learn it at the piano ↗ | *Tools › Take it out › The piano page* |
| MIDI and the parts, for your own tools ↓ | *Tools › Take it out* |
| Players panel: MIDI out select, Connect MIDI, Panic, program changes tick, per-player here/MIDI/off, Everyone to MIDI / here / As at first | the **player** inspector (route, channel; *more*: program change, Panic, everyone…); a route mark on each track head; Connect MIDI once, on the first route set to MIDI |

### Sound

| Today | New home |
|---|---|
| The style card: style, feel, how it ends, backing voices, the last refrain (lift) | the **empty** inspector's first card (the song's style), same chips |
| Key card (note, mode, "a minor mode leans the words darker") | the transport's key chip and its popover, the note kept |
| Tempo card (slider, slower/quicker) | the transport's ♩ (type, drag, or the popover's slider) |
| Shape card: verses, parts of the shape (intro, turn, break, tag, outro, bridge twice), Open Tune, Use the song's shape | the empty inspector's *Shape* card: "add a part" chips and the verse count; *The program's own* (order and parts); the regions are the rest |
| The melody card (variants) | a line in the song summary; the notes' heading says "the tune as it was written / with the lineage's variants" |
| The band card: how the band plays (pattern), who leads where nobody sings, how busy, how bright | the empty inspector's *Band* card (busy, bright, pattern where the style has one, lead); the **player** inspector for the lead; per-section pattern in the **cell** inspector once the engine has it |
| the band mixer strips: level, M, S | **Mix** strips; M and S on the track heads too |
| The room and the mix: space, width, forward, intimacy, rt60, predelay | the **Room** strip (space, width; rt60 and predelay under *more*) and the **Voice** strip (forward, intimacy); the same as inspector states |
| The singer card: whose way (phrasings) | the **singer** inspector (click the singer's track head or the Voice strip) |
| The words card (lean, changes this time, the rules) | the Page's tags and the section inspector's *why*; the lean as one line in the song summary |
| Voices before (choir) | the *voices before* track and its head's inspector; its lines in the song summary |
| Loudness, Your machine | lines in the song summary with "?" |
| "How this choice works" on every card, its reason tags | *Why the program chose this* in every inspector state, the same tags |
| Reset on a changed card | *The program's own* in every inspector state |

### Other versions

| Today | New home |
|---|---|
| Through time: the six-year timeline, the day slider, the steps (‹ year … year ›) | the **Time** drawer, same |
| Other computers: the table, ▶ theirs, "make one up" | the Time drawer, same |

### Sing, record & pass it on

| Today | New home |
|---|---|
| Sing it: open the singing page; the web studio's singing on its own page | *Tools › Bring it in › Sing it* |
| Record it, the saved file, the packet note, Download it (public) | transport ●; the progress and the file in *Tools › Take it out* |
| Download MIDI, Download the parts (stems), the export note | *Tools › Take it out* |
| Learn it at the piano (second link) | *Tools › Take it out › The piano page* (one link, not two) |
| Save your changes as a file, Open a saved file | *Tools*, both columns |
| "Made here. Heard anywhere." / "Nothing on this page leaves this computer." | the page's foot, same |

### The player, help, and the rest

| Today | New home |
|---|---|
| the foot player: play/pause, title, sub, progress bar, time, Record it | the transport's ▶ ■ and **position** field (title, progress, time); ● Record |
| "waiting its turn (2 ahead, about 3 minutes)", the public limits' sentences, Download it | the position field while making; the Tools sheet's foot; the recording's row |
| the toast | same |
| the "?" beside each area, the Help dialog, the tour | one "?" per view tab and on the inspector; the dialog and the tour, with the steps re-aimed |
| perform.js: Play a part in (MIDI keyboard live), import a MIDI file, merging into a phrase or part | *Tools › Bring it in*; the target is the selection (a phrase, a track) and the sheet says so |
| drafts in browser storage under the song's fingerprint; date and chance not kept | same, unchanged |

Nothing on the current page is dropped. Two things are demoted to a fold on purpose (rt60 and predelay;
program changes) and four cards become lines (loudness, machine, voices before, the melody's variants).

## Where the engine work lands

Designed for, so the page doesn't grow another card when each arrives:

| Engine work (in parallel) | Its place on the page | Its edit path (a guess, for the map) |
|---|---|---|
| which players play each section, their pattern and energy | the **cells** of the Arrange grid; the cell inspector | `arrangement.<section-id>.<player>` = `{energy, pattern}` |
| section length 4 / 8 / 16 bars | the region's edge; the section inspector's *Length* | `arrangement.<section-id>.bars` |
| instrumental sections and drops | the singer's cell set to out; the section's *Who sings* | `arrangement.<section-id>.singer` |
| builds, breakdowns, stripped starts, entrances (deterministic instead of random) | the section's *Moment*; a ⚄ mark on what was drawn by chance, a hand mark when set or pinned | `arrangement.<section-id>.moment` |
| risers, sweeps, rolls as transitions | the **seams** between regions; the seam inspector | `arrangement.<section-id>.into` |
| sidechain pump | the **Pump** control on the pad's and bass's Mix strip and player inspector, in words ("none · gentle · pumping") | `band.<player>.pump` |
| synth patch and filter, drum kits | the **player** inspector's *Sound*: patch, filter, kit as named choices | `band.<player>.patch`, `.filter`, `.kit` |
| wider, style-aware tempo | the transport's ♩ shows the style's range ("72 to 158 for this style") and refuses with it | `tempo` (bounds change) |
| sevenths and add9 | the **chord** inspector's *Quality* row grows `7`, `maj7`, `add9`; the key chips include V7 | `chords.<line>` (the grammar) |
| per-appearance scope for chord and melody edits | the **scope** switch on the notes' heading, the chord and note inspectors: *here only · everywhere this line is sung*; a per-place edit is shown with the section's name beside the hand mark | `chords.<line>@<section-id>`, `tune.<line>@<section-id>` |
| freer melody editing (add, split, tie, delete) | the **note** inspector under *more*; the roll's double-click on empty space adds a note where the engine allows | `tune.<line>` (the shape changes) |
| bugs: even rhythm off the grid; stale note name; unexplained asterisks; the stems' id | even rhythm evens to the snap; the note's name follows its degree; the asterisks become "the *stressed* word" in the line inspector's hint; the stems' zip takes the recording's id | |

## Decisions for the artist

1. **The first screen.** The mockup opens on **Page** (the tune book), as today, with the transport over
   it. The alternative is opening on **Arrange**, which says "this is a studio" at once but greets a
   non-musician with a grid. Page is recommended: a visitor reads the song first; a musician presses 2.
2. **One play button with a Sketch / Sung switch**, or two buttons as today (Play sketch, Hear sung)?
   The switch is recommended (one transport, one Space), with the switch defaulting to *Sketch* for a
   section or phrase and *Sung* for the whole song, and the position field saying which is playing.
3. **Names.** *Page · Arrange · Mix* (a DAW's words, short) or *The words · The score · The sound*
   (the tune book's)? The mockup uses the first; the tabs are one word each either way.
4. **Energy in a cell: three levels or a slider?** Three words (soft · plays · hard, with out) are
   proposed for the cell and the grid; the engine may have a finer number, which the inspector could
   expose as a slider. Fewer is recommended: a grid of 130 cells with sliders is a spreadsheet.
5. **The scope default** for a chord or melody edit once per-appearance exists: *everywhere this line is
   sung* (as today, the folk-tune answer: a line is a unit) or *here only* (the DAW answer). Everywhere is
   recommended, with the switch visible on the heading so the other is one click away.
6. **The notes on a phone**: read-only under 600 px with the inspector's steppers as the editor (proposed),
   or draggable with big notes? Read-only is honest about thumbs.
7. **M and S on the track heads** in Arrange (proposed, as a DAW has them) or only in Mix? Both is
   proposed; it duplicates two buttons per track, but a person arranging wants to hear one player alone
   without leaving the grid.
8. **No pan.** The Mix view refuses a pan control until the engine places players per part. If the
   artist wants the strips to *look* complete, a pan knob that is the room's width for every strip is a
   lie and is not proposed.
9. **Pinning what chance drew** ("keep this" on a ⚄ cell): proposed, because it is the same edit map.
   It does make a person's record carry values they didn't *choose* so much as *kept*; the mark could say
   "kept by you" rather than "chosen by you" (`chosen_by_you` gains a `kept: true`).
10. **The Time drawer** replaces the Other versions chapter. Alternative: a fourth view tab. The drawer
    is proposed because time and other machines change *which version is on the page*, which is what the
    version line says, and because a fourth tab is one more chapter to wander into.
11. **The seams as controls.** Transitions (riser, sweep, roll) could instead be a section's *Into the
    next* field in its inspector, with no clickable seam. The seam is proposed because a 6 px line between
    regions is what a musician reaches for and the field can exist as well.
12. **What "Tools" is called.** *Your tools*, *In and out*, *Pass it on* (the finish panel's old title)?
    The mockup says *Tools* on the button and *Your tools: take it out, bring it in* on the sheet.

## Decided (the artist, 2026-09-29)

All twelve recommendations above are taken: **Page** first; **one play button** with the Sketch / Sung
switch; the tabs named **Page · Arrange · Mix**; **three energy words** in a cell (out · soft · plays ·
hard); scope defaults to **everywhere this line is sung**, the switch on the heading; notes **read-only on a
phone**; **M and S on the track heads** as well as in Mix; **Time as a drawer**; **the seams as controls**;
the button is **Tools**. Pan: the sound-design work gives each player a real pan and reverb send, so the Mix
strips carry pan after all (decision 8's reason is gone).

Two changes from the mockup:

- **No dice mark.** ⚄ doesn't read at a cell's size. What chance drew is shown by the cell's own drawing
  instead (a dashed outline in the program's ink, "drawn by chance" in the legend and the inspector), and
  the transport's button is words only: *New performance*.
- **Locked, not kept.** Pinning what chance drew is **Lock**: a small padlock (an inline SVG, not an
  emoji) on the cell, the section or the value, in the second ink; the inspector says "locked by you", and
  the record marks it `locked: true` under `chosen_by_you` (a lock keeps the program's value; a choice
  sets another). *New performance* redraws everything not locked or chosen.

## The mockup

`docs/design/studio-redesign.html`: one file, no network, plain HTML, CSS and JavaScript, the studio's own
tokens copied from identity.css (both schemes: the system's, or the Light / Dark buttons), Ada's version of
*Now It's by You* today as its data (13 sections, 82 bars, the ballad band's eight players, the song's
chords in D, the words as sung). It shows:

- the transport, the version line with Time ▾, the three views;
- **Page** with the words, the section rubrics selectable;
- **Arrange** with the ruler, the regions, the tracks and cells (two cells and one region set by "a
  person" in the second ink; ⚄ marks on cells the style drew by chance), a seam, and Refrain 1's notes
  open under the grid with the harmony lane and a roll;
- **Mix** with the strips, Voice, Room and Master;
- the **inspector** in its states: nothing (the song), a section, a player, a cell, a seam, a chord, a
  note, a line of words, the room; each with *Why the program chose this* folded;
- **Your tools** as a sheet, **Time** as a drawer;
- **Phone**, a 390 px frame of the same page with the bottom bar and the inspector as a sheet.

A state can be put in the address, so any view and selection can be linked to or pictured:
`studio-redesign.html#s={"view":"arrange","sel":{"kind":"cell","id":"drum","sec":"refrain:0"},"theme":"dark"}`
(`view`, `sel`, `theme`, `open` tools or drawer, `frame` phone, `scroll`).

The pictures, under docs/design/: `studio-redesign-desktop-light.png` (Arrange, a cell selected, the notes
open), `studio-redesign-desktop-dark.png` (the same by lamplight, a chord selected), `studio-redesign-phone.png`
(the Page with a section's sheet) and `studio-redesign-phone-arrange.png`, taken in the built-in browser
(its pane is about 1070 px wide, so the desktop pictures are scaled; the phone ones are at the phone's own
size); the desktop `-2x` files beside them are the same states at full resolution from headless Chrome
(1440 px wide, 2×), with `-page-`, `-mix-`, `-tools-` and `-time-` for the other views (no headless phone
pictures: Chrome won't make a window narrower than about 500 px, so those came out cropped). To serve the mockup for a browser, `.claude/launch.json` has `design-mockups`
(a static server on docs/design, port 8798) and `studio-ada` (the studio itself, Ada, port 8799).

Clicking in the mockup selects and switches; nothing is edited for real and nothing is heard. It is for
looking at and reacting to, not for testing.


## Built (2026-09-30)

The score is the studio's page now: `songbird studio` opens it at `/` (and at `/v/<id>` on someone's
version); the tune book of four chapters it replaces is kept, unchanged, at `/classic` (and `/v/<id>/classic`)
until the artist signs the new one off, on the same API. Help links to it. Pictures of the built page, taken
with headless Chrome from the page's own address (a view and a selection can be put in it:
`#view=arrange&sel=cell:drummachine:refrain:2&open=refrain:0&panel=tools`, with `e=` an edit map, as the
classic page's links had), are `docs/design/studio-built-*.png`: the Page, Arrange (light, with the notes of a
refrain open; dark, a chord selected), Mix, the Tools sheet, the Time drawer, and a phone (the Page with a
section's sheet; Arrange with a cell's).

**How it is made.** No libraries, no build step, system fonts; it travels in the packet.

| File | What it is |
|---|---|
| `songbird/studio/index.html` | the page: masthead and version line, transport, view tabs, the three views, the inspector, the Tools sheet, the Time drawer, help |
| `songbird/studio/score.css` | its look: the mockup's, on identity.css's tokens; the phone layout by container queries |
| `songbird/studio/score.js` | the views (Page, the Arrange grid, the Mix strips), the inspector's fourteen states, the transport, the sheets, the keyboard |
| `songbird/studio/model.js` | the pure parts: the grid from the studio's answers, a cell's look and words, a lock, moving a section in story order, a seam's transitions, the scope switch, what plays, the keyboard's table (tests/studio_model.test.cjs) |
| `songbird/studio/renderer.js` | previews and recordings behind one interface (`preview`, `record`, `cancel`, progress), the server's queue today; the place a later step makes a section in the visitor's browser (docs/BROWSER-RENDER.md), the server as its fallback (tests/studio_renderer.test.cjs) |
| `songbird/studio/classic.html` | the page before, served at /classic |

The core is shared, not copied: studio.js keeps the edit map, undo and redo, the drafts in this browser,
listening and recording exactly as they were (both pages load it; it skips what a page hasn't got and tells
the score through `window.SongbirdScore`), and its words, choosers, mute and solo, the words kept, the
timeline, other computers and someone's version are the score's too. composer.js gained a notes mode (the
heading with the scope switch, the phrase strip, the roll) whose note and chord cards are states of the
inspector, and sketch controls the transport drives (a section, a phrase, or the song from the playhead);
author.js one line of words for the line's state; players.js what the player's column needs to route the
sketch's players; perform.js a file dropped on the Tools sheet; help.js the tour's four steps re-aimed (hear
it, the transport, select a section, record it). The server adds only the pages' routes and, on
`/api/arrangement`, where the voices before sing in each section (`choir`). Everything else it drives was on
main: `/api/arrangement` for the grid (cells, lengths, drops, builds, the style's options, locks, the tempo's
range), `/api/sound` for the Mix and the player's sound (patch, filter, kit and its pieces, pan, send, pump) and
the seams (transitions), the chord and tune scopes and the melisma through the composition view.

**The parity table, as built.** Every row above has its home; these are the ones to know about.

- *Kept as they were, moved*: the words and their dropdowns (the Page), the rules and refused alternatives, the
  verse, couplet and head choosers, Write your own lines, Reset words (the section's state, and a line's);
  the sketch, loop, click, chords and bass (the transport; chords and bass under ▾); Hear sung section
  (Sung, or ▶ Hear it); the overview and the section strip (the regions), Earlier and Later (the section's
  state, ⌘/Ctrl ← →), Restore order (the section's *The program's own* gives its move back with it); the
  phrase strip, the roll, snap and zoom, the harmony lane, the chord card (with the sevenths and the scope),
  the note card (split and join for a melisma, free the ending), the phrase tools (↑↓ Step; soften and even
  under *more*), the health line; the Style, Band, Shape, Singer and Room cards (states of the inspector,
  reached from the song's summary); the mixer (Mix, and M and S on every track head); Players (the player's
  column: here · over MIDI · off, the channel, and under *more* the MIDI out, Panic, the programs, everyone to
  MIDI, everyone here, as at first, and the sketch's own tune, chords and bass); time and other computers,
  and opening someone's version (the Time drawer); singing, recording, the MIDI, the parts, the piano page,
  notes in, the drafts (the Tools sheet); the player's title, progress and time (the transport's position,
  which says a public studio's queue too); the toast, the help dialog and the tour.
- *Lines, not cards*: the melody (its variants' ticks inside its ?), voices before, the words (*Keep these
  words* inside its ?), loudness, your machine.
- *New, from the engine*: the grid's cells (out · soft · plays · hard, what it plays, which line it comes in
  at, a fill), a section's length, who sings (a drop), a build and the style's options where they live (the
  band joining line by line, the last refrain's stripped start, the intro, stop-time, a bare verse, a
  half-time bridge), each lockable; the seams (a riser, a sweep, a roll, a stop, an impact, a downlifter,
  over 1, 2 or 4 bars); a player's sound (patch, filter, kit and pieces), pan, send and pump; the chord and
  tune scope (everywhere it's sung, here only, and at the last of several the last one however many).
- *Not built, and why*: adding, tying or deleting a note (the tune keeps a note for each syllable; only a
  melisma, split and join, is the engine's); pan on the Voice and Room strips (the engine places the voice
  itself; the room's width is its own control); a finer energy than three words (decision 4).

**How it was checked.**

- Tests: tests/studio_model.test.cjs and tests/studio_renderer.test.cjs (new), the existing node tests with
  the renderer loaded (tests/studio_state.test.cjs), tests/test_studio.py (the score and /classic served,
  both pages' stylesheets, every place the shared scripts write to present on both pages, the voices before in
  the grid), tests/test_studio_received.py (/v/<id>/classic). The full suite and every node test pass; the
  goldens are unchanged. The editor that travels in the packet is 153 KB compressed with the classic page
  beside the score (the cap is raised to 160 KB until the classic page goes, about 137 then); the program is
  6.16 MiB of 8 (`songbird budget`).
- In the built-in browser (a studio on this Mac, Ada, 8811; public, Wren, 8812; with web singing, 8813): every
  view, state and sheet; the keyboard (arrows through the grid, Enter and the Esc chain, M, ⌘Z, 1 2 3, T, L,
  Shift+Space); light, dark and a phone's width; /v/<id> on a version someone brought; a public studio's
  queue in the position field ("waiting its turn", "Yours is being made now…") and its limits in the Tools
  sheet's foot. The EDM brief, done through the page's own controls: synth folk at 128 in D minor; the verse's
  first line reharmonized i · VImaj7 | III · VII everywhere it's sung (three places); the last refrain's second
  line changed there only (`chords.refrain:last.1`); four on the floor in every refrain; Verse 3 made 16 bars
  and a build; Refrain 3 played, not sung (a drop); a riser over 2 bars and an impact into it; the drum
  machine's 909; the pad pumping (classic); a new first line for Verse 2; a melisma in the verse's third
  line; a chance-drawn entrance locked, kept through a new performance. Refrain 3 heard sung and in the
  sketch, the whole song recorded: 2:54, its record marking the 17 choices (the transition, the kit, the pump,
  the length and build, the words among them).

**After a Fable review** (read-only, of the built page against this page and the mockup), its points are in:
Space presses the button it's on (above); the switch starts on Sung with nothing selected (decision 2), and the
regions' ▶ say which; on a phone the column stops above the views' bar and the song's summary has a way in
(*This version's choices* on the version line), the seams are 24 px wide and the section's column has *Into
it* as their twin; a sweep's direction said and kept; the grid's arrow keys start from the focused cell, one
cell in the tab order; the ruler's bars are buttons (the playhead by keyboard); Esc's order said as it is;
the keyboard's focus moved to the column only for the selection that key made; a note's state no longer
outlives the section whose notes were closed; a refusal said once (the masthead, not also under the grid);
the stars out of a played section's words; the pan's words follow the drag.

**Decisions for the artist (the built page's own).**

1. **Space plays from the page, the grid and ▶ ■**; on any other button, a link or a field it presses it, as a
   keyboard user expects (a Fable review found it pressing nothing but play). In the grid, Enter selects a cell
   and Space plays.
2. **A section's Moment** is *none · a build*, and the style's options that live in that section are rows of
   their own (yes · no, and Lock), rather than one row of *drop · breakdown · stripped start*: in the engine
   a drop is *Who sings: nobody* and a stripped start is the style's whole-song option shown on the last
   refrain.
3. **A lock keeps a cell as chance drew it**: its level, what it plays and the line it comes in at, one
   padlock; *Unlock* (or *The program's own*) gives all three back. The header counts locks apart from
   choices ("17 choices are yours · 3 locked").
4. **Sketch or Sung follows the selection** (the sketch for a section, a phrase, a note; sung for the whole
   song) until the person flips it; then it stays as they set it for the visit.
5. **The classic page stays at /classic** until signed off, and the packet's editor cap is 160 KB until then.
