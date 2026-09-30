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
