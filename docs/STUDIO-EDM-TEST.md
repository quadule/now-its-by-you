# How flexible is the studio? An EDM version, made only through its page (2026-09-29)

The artist: "Make an EDM version of the song with significantly different lyrics and melody but still a
recognizable connection. Record a video of the process and condense it to the length of the song while
snapping actions to the beat."

The version was made only through `songbird studio`'s page, in a real browser (headless Chromium driven by
Playwright: clicks, typing, drags, as a person would), with a made-up machine (`--machine fictional:juno`),
nothing in songbird/ or songs/ changed and nothing made from the command line. There is no EDM style; getting
as close as the studio allows was part of the test, and where it couldn't go is the point of this page.

## What was made

`renders/now-its-by-you.2026-09-29.5beef0.flac` (gitignored; a copy at `renders/video/edm-rendition.flac`), 2:22 (142.226 s), −14.0 LUFS, recorded from the studio, with its MIDI and
stems exported from *Take it into your own tools*. 36 choices are marked as the person's in its record.

| | The song today (Juno) | The EDM version |
|---|---|---|
| Tempo | 95.5 | **124.8** (the ceiling; 128 refused) |
| Key | D major | **D minor** |
| Style | the ballad band (whistle, harp, fiddle, frame drum…) | **synth folk**, guitar muted: drum machine 170 %, synth bass 150 %, arp 110 %, synth pad, synth lead; busier and brighter (85 %) |
| Mix | a living room, voice 8.5 dB over | a dry room (25 %), wide, the voice 6.5 dB over (in the band) |
| Form | Intro · V1 · R1 · Turn · V2 · R2 · Turn · Break · Bridge · R3 · Tag | Intro · V1 · R1 · **Break · Bridge · R2** · V2 · **Bridge 2** · R3 (a whole step up, stripped at its start) · Tag · **Outro**, a cold stop |
| Chords (tune lines) | I–IV–V world (Dm · Gm Am in minor) | refrain: **B♭ \| F**, **Csus4 \| Dm**, **B♭ \| F C**; verse line 1: **Dm \| B♭ C** (i–VI–III–VII) |
| Melody | as written | verse lines 1 and 3 a step up and down, the verse's peak to the octave; refrain line 2 a step up; refrain line 3 climbing to the octave twice |
| Words | "They saved it as numbers…", "The whole world was watching…" | verse 1 the bank's **"A girl put a piece of it under a beat, / two seconds of somebody's voice, on repeat"**; verse 2 and two refrains' last three lines **written in the studio** (below); bridge "like a *spark* from the fire" |
| Backing voices | none | echo the lines' ends |

The lines written in the studio:

> *Verse 2.* A kid in a club heard it under the lights, / a sample of somebody singing at night; / she
> looped it and pitched it and gave it a drop, / and nine hundred people would not let it stop.
>
> *Refrain 1.* Who made this song? Nobody knows. / It's ours on the floor now, so turn it loud. / The bass is
> a heartbeat that nobody wrote; / we dance to it now, and tonight it's by you.
>
> *Refrain 2.* Who made this song? Nobody knows; / it came through the speakers, and still it grows. / It's
> nobody's record and nobody's crew, / no money for spinning it; spin it right through.

**The thread kept:** the refrain's first line, "Who made this song? Nobody knows.", sung to its own tune
(untouched) at the head of every refrain, now over B♭ | F; "…it's by you" still ends the first and last
refrains; the last refrain is the song's own ("by everyone, no one, and now it's by you"); and the tune's
contour stays under the new notes (the shared phrases, the pickups, every line's cadence degree).

## Findings, by impact

What the drum machine actually plays, measured on the exported drum stem (a kick within 60 ms of the beat):

| Section | Intro | V1 | R1 | Break | Bridge | R2 | V2 | Bridge 2 | R3 | Tag | Outro |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Beats with a kick | 0 % | 0 % | 97 % | 100 % | 50 % | 100 % | 97 % | 50 % | 53 % | 12 % | 80 % |

So the shape does read as build-and-drop, but by luck as much as by choice: the synth-folk style happens to
play half time in its bridge (a build of sorts), and chance drew its "entrances" (the band joining line by
line in the first verse, so no kick there), "a pad swells in to begin" and "the last refrain starts stripped
down" (a breakdown). None of those three could be chosen.

### 1. There is no electronic sound to reach for (highest impact)

(Since answered by edits, the engine and its API: patches and a filter, kits, a sidechain pump, pan and
sends, risers, rolls, sweeps, stops, impacts and downlifters at a boundary; docs/SOUND-DESIGN.md and
docs/STUDIO.md, "Sound design".)

Synth folk is the ceiling: an analog arpeggio, a sub/eighths synth bass, a pad, a synth lead, a drum machine,
and a strummed acoustic guitar (muted here). What a producer expects first, and could not find:

- **no sidechain pump.** The mixer's ducking is keyed on the voice (the band makes way for the singer), not
  on the kick, and nothing exposes it. The pumping pad/bass is the most recognizable EDM sound there is.
- **no patches.** Nothing chooses a synth's sound (saw stack, pluck, supersaw, reese); only one global
  "How bright". No filter, no cutoff automation, so no filter sweep into a drop.
- **no FX tracks**: risers, noise sweeps, impacts, reverse cymbals, snare rolls, reverb/delay throws. The
  closest is "backing voices echo the lines" (the line's last word again), used here as a stand-in for a
  vocal delay throw.
- **the drum machine's kit is fixed** (kick, snare, hats, open hat); no clap on 2 and 4, no ride, no
  offbeat-bass house pattern.

What would do most: a style of its own ("dance" or "house": pluck/supersaw, sidechained pad and bass, a
kick-keyed duck amount in the mix card, a riser into the last refrain), built on the synth/ instruments that
exist.

### 2. The arrangement's dynamics are drawn by chance, not chosen

The studio lets a person reorder sections and switch parts of the shape (turns, outro, bridge twice, verse
count), and that worked well: dragging the break and bridge before the second refrain turned them into a
breakdown and a build before a "drop" in three drags, each checked and accepted at once. But:

- **how it starts, entrances, stop-time, the breakdown** are style options drawn by chance; the style card's
  *How this choice works* names them ("the last refrain starts stripped down; the band joins line by line…")
  but only the ending, the backing voices and the lift can be set. Rolling *New performance* until they come
  up is the only workaround.
- **no per-section pattern**: which sections play four on the floor and which half time is the style's
  (the ballad has a "How the band plays" chooser; synth folk has none). A musician wants to say "drop =
  four on the floor, verse = kick only, build = half time into a snare roll".
- **no instrumental drop.** The EDM drop is the hook without the singer; the only instrumental sections are
  the intro, the turn, the break (a verse's tune) and the outro. A refrain can't be played by the lead alone.
- **fixed lengths**: every section is its eight bars (the intro four); no sixteen-bar drop, no eight-bar
  build, no repeating a section.

### 3. The tempo stops at 124.8

A person may choose 0.75 to 1.3 times the song's 96 (edits.py), so 128 is refused ("Choose a tempo from 72 to
124.8 BPM"). 124.8 is deep-house/tech-house speed and passes, but 126 to 128 is the genre's centre, and the
bound doesn't follow the style (synth folk's own range tops out at 122). Halftime/double-time genres (140,
170-174) are out of reach too. A style-aware bound (the style's range, and a person's ×1.3 of that) would fix it.

### 4. The melody can be moved, not rewritten

Worked: steps up and down on a phrase, dragging notes to new pitches (the verse's peak and the refrain's third
line up to the octave), the sketch hearing it at once over the new chords, validation that never refused a
sensible edit. Limits for this brief:

- **the syllables fix the rhythm's skeleton**: a phrase keeps its notes, their count and order, and its ending's
  degree class. An EDM topline's repeated-note hooks, chopped syllables and melismas need notes added,
  split or tied; none of that is possible, so the new melody is the old one's contour moved.
- **"Even rhythm" is off the grid**: on the verse's first line it put the notes at 1.2727, 2.0455, 2.8182…
  beats (an even division of the phrase's span, not of the beat). On grid music that is the one thing it must
  not do; undo was needed. It should even the rhythm to the snap (eighths).
- **a phrase edit changes every appearance**, the instrumental intro and break included: the drop's topline
  can't differ from the verse that shares its line.
- small: after a drag the announcement read "num, B♭4, scale degree 8" (the degree moved, the note name was
  the old one).

### 5. The words: the most flexible part

The bank gave the version its best line at once (verse 1, "A girl put a piece of it under a beat, / two
seconds of somebody's voice, on repeat"), and **Write your own lines** took ten new lines (verse 2 whole,
and three lines of each of the first two refrains) with a live syllable count, a pronunciation check and one
undoable apply; none was refused. The first refrain line was left as the bank's (only changed lines are
authored), which is how the hook "Who made this song? Nobody knows." stayed. Limits: a line's syllable count
is its tune's (so the words' rhythm is the folk tune's anapests); the prefilled text marks a stressed word
with `*asterisks*` without saying what they mean; lines belong to the bank verse under them (verse 2's are
`verse:screen`), so choosing another bank verse there later would drop them.

### 6. Chords: quick and clear, triads only

Reharmonizing to i–VI–III–VII took under a minute of clicks: a chord in the lane, a one-press chord from *In
the key*, *Chords in this bar* to join or split, *Quality* for a Csus4; the sketch played it at once and the
card named every rub. For EDM: no sevenths or added ninths to choose (the style adds some colour on its own),
and a line's chords change everywhere it is sung, so the intro's and the break's harmony changed with the
refrain's. The modes on offer for this song were major, mixolydian and minor (no dorian or phrygian).

### 7. Smaller things

- **Previews were fast** (a section in 1.8 to 2.5 s, instant once made; the sketch immediate), and the
  recording was instant because the same choices had been rendered before (the cache): the loop hear, change,
  hear again is quick enough to play with.
- **The stems' folder and file name carry another id** (`now-its-by-you.2026-09-29.8beb3d`) than the recording
  (`…5beef0`), so matching the parts to the recording is by date only.
- **Automation-friendly**: every control has a plain accessible name, so a script could drive all of it like a
  person; only the native selects' popups don't show in a headless browser's footage (the value changes).

## How the video was made

- **Driving and recording**: `tools/video/studio_session.mjs` (Playwright, headless Chromium, 1920×1080, the
  page's dark scheme, `recordVideo`), after a rehearsal of the same steps without video. It draws a cursor and
  a click ripple into the page, and a small caption per phase in the left margin in the page's serif; it
  writes `renders/video/actions.json` (108 actions: every click, select, slider, drag, typed line, play, the
  refusal, the record and the downloads, with the phase, a weight and how long to hold) and flashes the page
  white once so the log's clock can be found in the footage to the frame.
- **The cut**: `tools/video/beatcut.py` (raw video + action log + audio → a beat-snapped cut). The beat grid is
  the exported MIDI's tempo map and section markers (bar 1 at −1.083 s in the audio, as the stems' README
  says; fitting the onsets said −1.068). Each phase starts on its section's first downbeat (tempo on verse 1,
  the band on refrain 1, the form on the break, chords through the bridge, the new chords heard on the drop,
  refrain 2's downbeat, the words on bridge 2 and refrain 3, the sung verse on the tag, Record on the outro);
  inside a section the actions keep their order and spacing, squeezed to fit, weight 3 on bar lines and 2 on
  half bars; the waits are held, run fast (to 8×) or cut on a beat; typing runs at most 2.5× and holds.
  `--phases` and `--pin` make it reusable for any run and any song.
- **Result**: `renders/video/edm-process.mp4`, H.264 1080p30 + AAC, 142.226 s, exactly the rendition's
  length (the audio is the rendition). 82 of the 108 actions are anchored on beats (the rest play inside
  their neighbours); the moments are off their beat by 8.5 ms on average and 16.4 ms at most, which is the
  30 fps frame grid. Frames checked for legibility (typing, chord card, arrangement, record panel).
- **Awkward**: Playwright's recording is VP8 at about 1 Mb/s (text sharp once still, soft while scrolling); a
  headless browser doesn't draw native select popups; the page scrolls a lot at 1080p, so the cut shows the
  jumps; the caption's small capitals didn't pick up the page's red.

Files (gitignored, under `renders/video/`): `raw.webm` (4:21), `actions.json`, `edm-process.mp4`,
`edm-rendition.flac`, `edm.mid`, `edm-stems.zip`, `cut-report.json` (each anchor's beat and frame),
`session.log`, `frames/`.

## Second attempt (2026-09-30)

The artist: "Try another EDM video." Since the first attempt the studio gained the arrangement engine (a cell
for every player in every section, section lengths, played sections, builds, the style's chance-drawn options
choosable and lockable: docs/ARRANGE.md), sound design (patches, a filter, kits, a sidechain pump, transitions
at the seams, pan and sends: docs/SOUND-DESIGN.md), sevenths with *here only* or *everywhere*, melisma and a
freer tune (docs/STUDIO.md), and a new page, the score (one transport; Page · Arrange · Mix; one inspector; a
Tools sheet: docs/STUDIO-REDESIGN.md). The rules were the first attempt's: only the page, as a person uses it
(headless Chromium driven by Playwright: clicks, typing, drags), a made-up machine (`--machine
fictional:vela`), nothing from the command line. This time the brief asked for a convincing EDM track, not the
nearest the studio could get.

### What was made

`renders/now-its-by-you.2026-09-30.562cea.flac` (gitignored; a copy at `renders/video/edm2-rendition.flac`),
2:37 (157.4 s), −14.0 LUFS, recorded from the page, its MIDI from *Tools → MIDI*. 52 choices are marked as the person's
in its record (four of the entries are the two locks' values: a cell's lock keeps three).

| | The song today (Vela) | The EDM version |
|---|---|---|
| Tempo | 86 | **128** (synth folk allows 72 to 134.1; typed, accepted) |
| Key | C♯ major | **C♯ minor**; the last refrain a whole step up (the style's lift, kept) |
| Style | chamber folk (strings, cello, piano, no drums, rubato) | **synth folk**: the drum machine on its **909** kit, a **reese** synth bass pumping (*classic*, 8 dB), a **wide** pad pumping (*heavy*, 14 dB), a **supersaw** lead, the arpeggio; the guitar sits out; it stops dead |
| Form | V1 · R1 · Turn · V2 · R2 · Turn · V3 · R3 · Turn · Bridge · R4 · Tag (72 bars) | **Intro 8** (the lead plays the tune in; no drums) · **V1 8** (the band joins line by line) · **R1 8, a build** · **R2 16, the drop**: nobody sings, the lead on the tune, everyone hard, four on the floor · **V2 8, the breakdown**: no drums, no bass · **Bridge 8, a build** · **R3 16, the second drop**: sung, then the drop again · Tag 2 · **Outro 8** (82 bars) |
| Seams | none | into R2: a **riser** and a **snare roll** over 2 bars, an **impact** on the downbeat; into V2: a **sweep** falling (the top closes); into R3: riser, roll, impact |
| Chords | the song's triads | verse line 1 **C♯m7 \| Amaj7** (i7 · VImaj7); refrain line 1 **Amaj7 \| E** (VImaj7 · III), line 2 **B7sus4 \| C♯m7** (VII7sus4 · i7); everywhere those lines are sung |
| Melody | as written | refrain line 1's "knows" a **melisma**, B4 falling to G♯4; line 3's "speak-" up to the octave (C♯5); the verse's "tune" up to the octave; the last refrain's second line a step higher **there only** |
| Words | the bank's verses and refrains | **thirteen lines written in the column** (below); the refrains' first lines, the bridge and the last line kept |
| Locks | | the synth pad's entrance in verse 1 (soft, held chords, from line 2: chance drew it); "the last refrain starts stripped down: no" (chance drew it; locked so the second drop lands whole) |

The words written in the studio:

> *Verse 1.* The lights on the ceiling went blue in the smoke, / a hum in the floorboards before someone
> spoke; / a girl at the decks found a tune in a file, / and played it to strangers who stayed for a while.
>
> *Refrain 1 (the build).* Who made this song? Nobody knows. / It's down in the bass now, and up it goes. /
> so turn up the speakers and let it come through, / and dance till the morning, and now it's by you.
>
> *Verse 2 (the breakdown).* Now somebody's brother is humming it low, / and somebody's mother is singing it
> slow; / the floor is a field and the dark is in bloom, / and every last stranger is singing the tune.
>
> *Refrain 3 (the second drop).* Who owns this song? Nobody knows. / It's yours on the floor now, and on it
> goes. / a beat that was borrowed, a voice that was true, / by everyone, no one, and now it's by you.

**The thread kept:** "Who made this song? Nobody knows." opens the build on its own tune (only its last word
now turns over two notes), and the drop that follows is that refrain played by the supersaw with nobody
singing, the hook as a lead line; the second drop sings "Who owns this song? Nobody knows." and ends on the
song's own last line, "by everyone, no one, and now it's by you"; the bridge ("Carry it over the water and
wire") is the song's own; and every changed line keeps its tune's anapests and cadence degrees.

What the version plays, from its MIDI file (the beats with a kick on them, within an eighth of a beat), set
beside the first attempt's table above:

| Section | Intro | V1 | R1, build | R2, drop | V2, breakdown | Bridge, build | R3, drop | Tag | Outro |
|---|---|---|---|---|---|---|---|---|---|
| Bars | 8 | 8 | 8 | 16 | 8 | 8 | 16 | 2 | 8 |
| Beats with a kick | 0 % | 0 % | 59 % | 100 % | 0 % | 63 % | 98 % | 0 % | 94 % |
| Synth bass notes | 1 | 10 | 57 | 127 | 0 | 13 | 127 | 4 | 63 |

This time the shape is chosen, not found: the builds' kicks thicken through their bars (the drum machine's
build pattern), both drops are four on the floor throughout, and the breakdown has neither drums nor bass.

### The first findings, now

| First finding (2026-09-29) | Now | |
|---|---|---|
| 1. No electronic sound: no pump, no patches, no filter, no FX, one kit | Patches by name (the bass's analog, sub, **reese**, pluck; the lead's saw, square, **supersaw**; the pad's warm, glass, **wide**), a filter under *more*, kits (808, **909**, lofi, acoustic) and their pieces, a **pump** on every synth (subtle, classic, heavy), pan and sends; risers, sweeps (rising or falling), snare rolls, stops, impacts and downlifters at any seam, over 1, 2 or 4 bars | **fixed** |
| ... no dance style; the guitar is synth folk's | Synth folk is still the base: the strummed guitar has to be sat out, the arpeggio and the lead play the folk tune's lines; no clap on 2 and 4, no ride, no offbeat bass | **still missing** |
| 2. Dynamics drawn by chance: entrances, breakdown, stripped start | Each is a row of its own in the section's column, with a Lock, and each player's cell (out · soft · plays · hard, what it plays, the line it comes in at, a fill) | **fixed** |
| ... no per-section pattern | four on the floor, half time, a groove, a boom-bap, a build, winding down: per cell | **fixed** |
| ... no instrumental drop | *Who sings: nobody: played*; the lead takes the tune and the band keeps its weight | **fixed** |
| ... fixed lengths | 2, 4, 8, 16 bars per section (a sung one only lengthened: its lines, then the drop again) | **fixed** (a turn keeps its 2 bars; nothing past 16) |
| ... (a breakdown) | made cell by cell (drums and bass out), and a *build* is a Moment; a breakdown isn't | **better** |
| 3. Tempo stops at 124.8 | the style's own range: synth folk 72 to 134.1; 128 typed and taken | **fixed** (140/170 half-time genres still out of reach) |
| 4. Melody moved, not rewritten: no melisma, even rhythm off the grid, a phrase edit everywhere, the old note name after a drag | *Split* and *Join* (a syllable over up to four notes), *Free the ending*, a wider range, *even rhythm* on the grid, **here only / everywhere / the last refrain** for a tune edit, the right name after a drag | **better** (no added or deleted syllable notes: a line's rhythm is still its words'; no repeated-note chops) |
| 5. Words: flexible, rhythm the tune's, asterisks unexplained | the same, written a line at a time in the column (the typing kept per line, one *Use* for all), the stars explained beside it | **better** |
| 6. Chords: triads only, a line's chords everywhere | a row of the key's sevenths, qualities down to 7sus4 and add9, *here only · everywhere · the last refrain* | **fixed** |
| 7. Previews fast | the 16-bar drop made to hear in 2.1 s; the whole song recorded in 11 to 12 s | **same** |
| ... the stems' id | the stems named after the recording they go with | **fixed** (not retested) |
| ... native selects don't show headless | fewer: most choices are chips now; the style, the pump, *Chords in this bar*, *Quality*, snap, zoom, and the words' own dropdowns are still selects | **better** |
| ... the page scrolls a lot at 1080p | one transport stays; Arrange and the inspector fit a 1600-wide window; the Page and the notes still scroll | **better** |

### New findings, by impact

1. **It can make the track now.** Every part of the brief was reachable from the page, with nothing chosen by
   rolling the dice: a 128 BPM minor-key track with a real form (intro, verse, build, a 16-bar instrumental
   drop, a breakdown, a second build, a 16-bar second drop, an outro), a 909, a pumping reese and pad, a
   supersaw, risers, rolls and impacts at the seams, sevenths, a melisma, a line changed in one place only,
   thirteen new lines, and two locks. The session was 161 actions over six and a half minutes of page time,
   against the first attempt's 108 over four and a half for far less; the 16-bar drop was made to hear in
   2.1 s (0.3 s once made) and the whole song recorded in 11 to 12 s.
2. **It is still a folk band in synths.** Synth folk is the only electronic style, so the strummed guitar has
   to be sat out, the arpeggio and lead play the tune's lines, and the drop's hook is the refrain's melody
   note for note (a *here only* tune edit on the played refrain would give it a topline of its own; nothing
   offers that as "the drop's hook"). No clap on 2 and 4, no ride, no offbeat bass, no chord stabs or pluck
   patterns to choose, no filter automation (a sweep at a seam is the only movement), no vocal chop. A
   "dance" style built on these same pieces is still the first thing a producer would ask for.
3. **Quick clicks in the inspector are fragile** (see *Bugs* 1 and 2). An edit's answer takes about 0.7 s
   to come back (eight requests), and until it does the column shows the old state: a second click composed
   from that state (a seam's riser, then its roll) undid the first, and when the answer lands the column
   reflows (a chip grows its ✎, the *Over* row appears) under a pointer already on its way. Both takes
   filmed before this was understood lost the snare rolls without the page saying so; only the record showed
   it.
4. **Lengths by the edge are hard to grab** (*Bugs* 3): the next seam covers most of the 7-pixel edge, and a
   drag from beside it moves the section instead. The column's Length chips always work.
5. **What the page calls yours is noisy once the form changes** (*Bugs* 4): after the shape and one drag,
   every region carries the second-ink edge, so "yours" stops meaning anything in the region row.
6. **Sitting a player out after arranging it reads as an error** (*Bugs* 5): "Couldn't keep your guitar in
   refrain 2: this version's band has no guitar" in the masthead, in red, for a guitar the person just sat out.
7. **The minor key is spelled in flats** (*Bugs* 6): in C♯ minor the page writes A♭m, E♭°, E♭4 and A♭4 for
   G♯m, D♯°, D♯4 and G♯4 (the chord lane, the chord chips, the pitch keys, the notes).
8. **"was" is sometimes the wrong thing** (*Bugs* 7): the tempo says "the program's was 86" (chamber folk's)
   after the style changed to synth folk, whose tempo is 122; a sat-out guitar reads "0% (was 0%)" in the
   column and `was: 0.0` in the record.
9. **Words: one *Use* for all the lines typed**, which is quicker than the first attempt's textareas, but the
   button says *Use this line*, the column stays on the line just typed, and a refusal of one line (here my
   `*some*-bo-dy's`, a star inside a hyphenated word) refuses them all, the reason said in the column only.
10. **The seam's *Over* is one length for everything before it**: a 4-bar riser with a 1-bar roll, the usual
    pairing, can't be made.
11. **The pump**: offered on the drum machine's own column (a drum machine ducking on its own kick) but not
    on its Mix strip, and where it pumps (`sections` in the API) isn't on the page: it pumps wherever the kick
    plays, so the breakdown doesn't pump only because it has no kick.
12. **Track heads truncate** ("synth …", "drum …", "arpegg…") with room to spare at 1920 px (1600 zoomed),
    and three of the six start with "synth", so the grid's rows can't be told apart without the tooltip.
13. **Smaller**: *everywhere it's sung (4)* counts the played refrain; the Moment is *none · a build* (a
    breakdown is made cell by cell, which worked, but isn't named); native selects remain for the style, the
    pump, *Chords in this bar*, *Quality*, *Root*, *Bass*, snap, zoom and the words' own choosers; a stray
    "null" under the tempo (fixed here); the masthead's "4 locked" for two padlocks (a cell's lock counts
    as three: its level, what it plays and its line).

### Bugs found

Seen in headless Chromium at 1920×1080 on `--machine fictional:vela`: in the filmed takes (the page at
1.2×) and again by hand in a second browser at 1×.

1. **A seam's second quick click undoes the first** (fixed in this branch: `score.js`, `seamState`). Steps:
   Arrange → click the seam into any section → *a riser*, then within about half a second *a snare roll*.
   Expected: a riser and a roll. Got: `{"roll": 1}`: every chip composed its value from the answer drawn
   before the first click (`seam.value`), not from the edit just made. The fix composes on the latest edit
   (`state.edits[path]` when present). The same shape (a control that composes an object from the drawn
   value) is worth checking elsewhere.
2. **The column reflows under the pointer after an answer.** Steps: the same seam, *a riser*, then move to
   *a snare roll* and click about a second later. Expected: the roll. Got (both filmed takes before the kit
   waited for answers): *Over: 2 bars*, which had appeared where the roll's row had been, so the drop had a
   riser and an impact and no roll, and nothing said so. Not fixed (a layout matter: reserve the *Over* row,
   or don't add ✎ to a chip's width).
3. **A section's length edge is mostly covered by the next seam.** Steps: Arrange, press the middle of a
   region's right edge (the 7 px `.edge`) and drag right. Expected: "4 → 8 bars". Got: the press lands on the
   next section's `.seam` (10 px, `margin-left: -6px`, `z-index: 2`), or just inside it on the region, whose
   native drag then moves the section: the first rehearsal's intro moved after verse 1 (the rendition played
   verse 1 before the intro). Only the edge's first 1 to 3 px work. Not fixed.
4. **Every region is marked yours after the shape changes and one move.** Steps: The shape → 2 verses, an
   intro, no turns, an outro; Arrange → drag Verse 2 onto Refrain 2. Expected: Verse 2 (and at most the
   section it passed) with the second-ink edge. Got: all nine regions "…; yours". `score.js` `moved()`
   compares each section's index with `marks["form.order"].was`, which is the song's original order
   (`verse:0, refrain:0, turn:0, …, refrain:3, tag:0`), not the program's order for the shape now chosen, so
   every index differs. Not fixed (the program's order for the chosen shape is the server's to say).
5. **"Couldn't keep your guitar" for a guitar sat out.** Steps: synth folk; Refrain 2 → *Everyone: hard*;
   the guitar's track head → *Sit out everywhere*. Expected: the guitar silent everywhere, no complaint.
   Got, in the masthead: "Couldn't keep your guitar in refrain 2: this version's band has no guitar; the
   choice waits for one that has. let it go". It looks as if a level of 0 is taken for the band not having
   the player. The session lets it go. Not fixed.
6. **Sharp keys spelled flat.** Steps: the key → minor (C♯ minor). Expected: G♯m, D♯°, G♯4. Got: A♭m in the
   chord lane and the Chords track, E♭° and E♭m7♭5 among the chord chips, A♭4 and E♭4 on the pitch keys and
   in the notes' names (`… A♭4, scale degree 5`). Not fixed.
7. **The wrong "was".** Steps: the style → synth folk, then the tempo → 128. Expected: "yours; the program's
   was 122". Got: "the program's was 86" (the chamber folk it replaced); the record's `tempo.was` is 86.2.
   And: the guitar → *Sit out everywhere*. Expected "0% (was 66%)". Got "0% (was 0%)", and `band.guitar.was`
   0.0 in the record. Not fixed.
8. **A stray "null" in the tempo and key popovers** whenever the value was the program's: `replaceChildren`
   was given the missing release row as `null` and printed it. Fixed in this branch (`score.js`).

### Fixed after the test (2026-09-30)

Each of the bugs above and the findings that were the page's, with a test; seen in the built-in browser and in
headless Chrome at 1600 px; the goldens unchanged.

- **Quick clicks** (*Bugs* 1, 2; finding 3): the column, the grid and the Mix are drawn again in place
  (`studio.js` `morph`: a node the new drawing has in the same place is kept and given its attributes, text,
  value and listeners), so an answer landing mid-click neither replaces the button pressed nor moves what didn't
  change. Nothing grows as an answer lands: a chip's weight is drawn, its ✎ sits on its corner, the line saying
  what's set keeps two lines, rows that come and go (a cell's pattern, a pump's sections, a section's options)
  are drawn always or drawn last. What a click builds on is the latest edit, not the answer drawn before it:
  chip rows, a seam's kinds, ← Earlier twice, M twice, a shape's part twice, a drum piece's knobs. Quick clicks
  on a seam, a cell, a section and a player move nothing between the first click and the last answer.
- **The length edge** (*Bugs* 3; finding 4): a 10 px handle of its own at the cell's right end, over the
  region and clear of the next seam, with a resize cursor; a drag from its middle lengthens.
- **Yours after a shape change** (*Bugs* 4; finding 5): the record's `form.order` "was" is the program's order
  for the shape chosen, and a region is marked moved only if it's one of the fewest whose moves make the order
  (`model.js` `movedIds`).
- **A player sat out** (*Bugs* 5; finding 6): its cells are kept, silent, and nothing is said to be wrong
  (`takeover.sat_out`).
- **Spelling** (*Bugs* 6; finding 7): by the key's signature everywhere (`theory.py` `spelling`: chord names,
  the chord card's roots, the pitch keys and notes, the key's name, the MIDI key signature and names, the piano
  page); every major and minor key tested. C♯ major now reads E♯m and B♯° where it read Fm and C°.
- **"was"** (*Bugs* 7; finding 8): the program's own for the style and shape chosen: "the program's was 122",
  "0% (was 66%)".
- **Use this line** (finding 9): one line at a time, as the column is: its own Use, its own refusal, a line used
  while the one before is checked waits its turn, and the column moves on to the next line.
- **A seam's lengths** (finding 10): each kind its own (the engine already took them): a 4-bar riser with a 1-bar
  roll.
- **The pump** (finding 11): not offered on the drummer (it's the key), and *Where* in its row: everywhere, or
  the sections chosen.
- **Track heads** (finding 12): the whole name ("synth bass", "drum machine"), a wider head that wraps.
- **The lock count** (finding 13): padlocks, not paths ("2 locked").

`tools/video/edm2_session.mjs` runs without its workarounds (the edge taken by its left pixels, "let it go",
the one Use for all), and with `--no-wait` its hand doesn't wait for answers or follow a control that moved.

### How the video was made

- **Driving**: `tools/video/edm2_session.mjs`, on `tools/video/kit.mjs` (the hand, the captions, the capture
  and the log, apart from any one session so the next film starts from them). Headless Chromium at 1920×1080,
  the page's light scheme (paper and its two inks), the page at 1.2× (CSS zoom on the root: laid out as a
  1600×900 window, drawn at 1920×1080, so its small text is a fifth larger in the film). The cursor glides and
  ripples in the rubric red; before reaching for a control the hand waits for the page's answer to the last
  edit (it counts the requests in flight) and follows a control that moved while it travelled. After two
  rehearsals without video, three filmed takes: the first two lost the snare rolls (*Bugs* 1 and 2); the
  third is the film.
- **Sharper capture**: Chrome's own screencast (`Page.startScreencast`), every compositor frame a JPEG at
  quality 95 with its timestamp (about 32 a second), put together by ffmpeg at the frames' real times into
  `raw.mp4` (H.264, CRF 10, 30 fps), whose t = 0 is the log's; the JPEGs (3 GB for a take) are deleted
  once it is made. Playwright's own `recordVideo` is VP8 at about 1 Mb/s; its text was soft.
- **Captions** in the page's own type and colours: an index card at the foot, left, on the card colour with a
  hairline border and a red double rule on top, the kicker in the rubric's red small capitals ("THE DROP ·
  REFRAIN 2"), the line in the page's serif at 31 px; on the Page view it narrows into the gutter beside the
  words instead of covering them.
- **Native selects** (the style, the pump, *Chords in this bar*, *Quality*) are drawn as the page's own list
  under the select, in its sans, the current value ticked, the pointer travelling to the choice and the
  choice lit in the second ink before the list closes; the value is set as a person's choice would set it.
- **The log** is the first attempt's format (`t`, `kind`, `label`, `phase`, `weight`, `hold`, `dur`), with
  the zoom beside the viewport, so `beatcut.py` reads either.
- **The cut**: `tools/video/beatcut.py`, the beat grid from the exported MIDI file (its bar 1 fitted to the
  onsets at −1.028 s), each phase pinned to the section it made: the style, tempo, key and shape on the intro;
  verse 1's words on verse 1 (typed as they are sung); the refrain's words and its build on refrain 1; the
  drop's arrangement on the drop's downbeat and its sound halfway through it; verse 2's words on the
  breakdown; the breakdown's cells, the second build and the lock on the bridge; the chords, the tune and the
  last refrain's words through the second drop; the record on the tag and outro. Changed in `beatcut.py` for
  this (it stays generic): the flash that syncs the log is found as a rising edge to all-white (the light
  page's paper is luma 237, and the old test, any frame over 200, took the first frame for it and put every
  action 1.6 s early); the pieces between are near lossless (CRF 4) and the result's quality is a flag
  (`--crf`, 16 by default, x264's still-image tuning; the film used 12); the report gives the bitrate and
  how many moments land on a bar line.
- **Result**: `renders/video/edm2-process.mp4`, H.264 1080p30 + AAC 256k, 157.424 s, exactly the rendition's
  length, its sound the rendition. 108 of the 161 actions are anchored on beats (30 on a bar line; the
  rest play between them), off their beat by 8.6 ms on average and 15.8 ms at most (the 30 fps frame grid).
  At CRF 12 the whole file is 1.3 Mb/s (the picture 1.0 on average, 6.5 in its busiest second): the page is
  still paper most of the time, and a constant quality spends the bits where it moves. Frames pulled at
  the typing, the grid, the chord chips, a native list, both locks, the melisma and the recording read
  cleanly at 1:1 (`renders/video/frames/`).
- **Awkward**: captions are drawn into the footage, so changing one means filming again; a take is six
  minutes of page time and 3 GB of frames before they're assembled; the page's own waits (an edit's answer,
  a preview, the recording) are short now, so most of the compression is the hand's travel and typing.

Files (gitignored, under `renders/video/`): `raw.mp4` (6:31), `actions.json`, `session.log`,
`edm2-process.mp4`, `edm2-rendition.flac`, `edm2.mid`, `cut-report.json`, `frames/`.
