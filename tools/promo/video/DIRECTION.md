# Direction

What the film looks like and what each scene shows. The contract (time, data, palette, the scene
interface) is README.md; how to write a scene is web/scenes/README.md; every data file is prep/DATA.md.
This file is the art direction. Where it and the storyboard in the plan differ, this file holds.

## The whole film

- **Truth.** Every mark is drawn from the program's data at that moment of the song: a note from the
  score, a frame of the voice, a model's captured parameters re-run, a byte of the file. No decoration,
  no idle loops, no invented numbers or ids. If you cannot draw it from data, leave it out.
- **One strand.** A single line runs through the whole film: the wire, the pitch line, a string, the
  bow's string, the file's bytes, the daisy's stem. Each scene takes the strand from its neighbour and
  hands it on. **Rest pose**: at a scene's first downbeat and at its last bar line the strand is one
  horizontal line across the full width at y = 540, 2.5 units wide, in the scene's line ink, carrying
  the lead's pitch as the core's `strandPoints` does. A scene pulls the strand out of rest into its
  picture within the first beats and returns it in its last beat, so any cut joins.
- **Line, not shape.** The look is fine line in great number: thousands of hairlines and points, crisp,
  layered in depth, moving with the music. Never a few fat shapes, never a chart with axes, never UI
  chrome. On the stage, line is light (cold blue for the machine alone, amber for a sounding note,
  bloom from the final pass). On paper, line is ink: hairlines, woodcut hatching, a red rubric, flat.
- **Light follows the people**, with three planned darknesses. Dark through verse 1 line 3; lamplight
  from 25.6 s; the lights come up onto paper at the frame drum's line (40.6 s). Verse 2 goes dark
  again for its screens and ends black. Refrain 2 returns to paper. The bridge's last line goes dark
  to one ember. The last refrain is full daylight paper, and the end is real sun. Scenes that go dark
  export `light(ctx, t)`.
- **Indigo** (`hand`) only for what a person did or chose: a line the artist wrote, the volunteers'
  numbers, a note that moved to follow the singers, a listener's choice in the studio.
- **Depth.** Use the core camera for anything that recedes (the voice's lines, the wall of screens,
  the drum skin, strings seen along their length). Slow, continuous camera moves driven by the bar,
  never a shake, never a zoom punch.
- **Motion.** Things arrive on the line where their part enters and move because a note sounds. Ease
  on beats. Hold still when the music holds. One idea per sung line (about 5 s): when a new line
  starts, the previous idea has finished and steps back.
- **Words.** The sung line sits where the core puts it (centred, y near 885) in every scene, the
  syllable being sung lit. A refrain's turning word (made, sang, owns) is set apart. Labels are small
  capitals at the upper left, at most two on screen, each up for at least two bars; a label names what
  is on screen in a few words and is in `web/copy.json` under your scene's key (edit only your key,
  with the Edit tool; the artist will revise the wording, so keep labels plain and true). No other text
  except text that is itself data (digits of the tune, phones, lines of the bank, code from the file).
- **Finish.** Look at your own frames at full size, critically, many times. Check edges, spacing,
  alignment to the lyric and labels, legibility at 1080p, and that nothing clips the frame or collides
  with the lyric. A frame that looks like a diagram or a placeholder is not finished. The film must be
  extremely impressive: aim for frames that could hang as prints.
- **Cost.** A 1080p frame should draw in well under 100 ms on the GPU after `init`; simulate once and
  cache. Keep each scene's own assets small enough to load in a few seconds.
- **Your folder.** Helpers you need that the core lacks go in your scene's folder. Do not edit `core/`,
  `capture/`, `prep/`, other scenes, or `web/scenes/index.js`; report what you wish the core had. New
  data you need: write a prep script named for your scene in `prep/` (it must use `common.guard`) and
  document its output in a file in your scene's folder.

## The daisy (shared by s08, s09, s10)

`core/daisy.js` draws it. From the bridge's third line it stands at the lower right: foot of the stem
at (1690, 1010), height 300 units. It grows one stage per whistle note (`timeline.daisy`), each stage
taking about three quarters of its note, and then never leaves the frame. No label, no word, no cue
points at it.

## Scenes

### s01_writing: intro (0 to 10.9 s). Dark.
Sounding: `whistle~` (the synth lead on the whistle's notes), `harp~`, `bass~`, the drone, `synthpad`;
the chip's drums (`drummachine#`) from 5.88 s.
- **Before the first note**: black, then one point of cold light that draws the strand across the frame.
- **To 5.9 s, the tune as written.** The genome writes each phrase's tune as scale degrees on an
  eighth-note grid (`text.json` phrases, e.g. `6, | 1 - 1 - 5 - - - | 6 - 5 3 5 - - -`). Set the phrase
  the lead is playing in the numeral role on its bar grid, as type being composed; as each note sounds
  its digit lifts from the baseline to its pitch and becomes a point on the strand, which bends through
  the lifted notes: digits become contour. Check which phrase the intro states by comparing pitches to
  the phrases; set only digits that match what is played.
- **5.9 to 10.9 s, the bank.** The 51 verses of the bank (`text.json`, each with its `by`) as lines of
  small type receding in depth like a drawer of cards; the four lines of the verse about to be sung
  come forward and settle while others pass. Lines a person wrote take the hand ink. At the chip
  drums' entry, the chip's 15-bit noise register appears as a row of fifteen cells shifting on every
  hit from its captured seed (`physics/chip`).
- Hands over a taut strand at rest.

### s02_voice: verse 1 (10.9 to 30.9 s). Dark, lamplight on line 4.
- **Line 1, "They saved it as numbers and sent it by wire"**: the line's words break into the phones
  the throat is told (`throat/` phone segments), each phone a bead on the strand, with the numbers it
  is given beneath it (position, duration, stress, level, log f0) as tiny numerals. The strand is the
  pitch line of the human-0 take: dead straight steps. On "sent it by wire" pulses of light run along
  it. Behind, faint, the arp's and pad's real waveforms from their stems.
- **Line 2, "a flicker of light, and as quick as a fire"**: the hero image of the dark half. The
  throat's spectral envelope, one line every 5 ms, receding in depth through the camera (the picture of
  tools/promo/throat_line.py remade for 16:9 and light: renders/promo/frames/line-4.6.png): the newest
  line bright and cold, harmonics as fine amber stalks where the voice is pitched, breath as scattered
  points where it is not, hundreds of lines behind it fading with distance; the camera drifts slowly
  along the ridge. Label: 200 lines a second.
- **Line 3, "Each copy was perfect in every last part"**: the lines fall flat into rows and become
  every weight of the singer, one point each, lit by what each adds at this moment (`throat/weights`,
  `act-verse1`; the picture of tools/promo/singer_picture.py). Then the camera pulls back and the
  picture is one of many identical copies in a grid, each lit the same on every frame, the file's id
  set small under each. Label: 886,372 numbers.
- **Line 4, "but not one machine ever knew it by heart"**: the copies go out, leaving one strand. The
  real harp enters: the first plucked string, in amber, the strand itself ringing with the model's own
  shape (`physics/pluck-harp`, formula in DATA.md). The light warms. The pitch line, straight until
  now, loosens for the first time (the heard take's f0 against the human-0 take's).
- Synth entries are felt, not explained: the drum machine's hits (15.6 s) and the synth bass (20.6 s)
  pulse the light of what is on screen.

### s03_instruments: refrain 1 (30.9 to 50.9 s). Lamplight, then paper at 40.6 s.
Each player takes over from its synth twin on its own line: the twin's waveform (its stem's real
samples) relaxes into the string.
- **Line 1, "Who made this song? Nobody knows."**: the harp's strings and the bass. Each sounding note is
  a string drawn across the frame, displaced by its model's own travelling wave re-run from the
  captured loop, both planes, so a string seen in slight perspective whirls as its two polarizations
  beat. The bass is one long string, low in the frame, its wave slow enough to see. *made* set apart.
- **Line 2, "It's yours while you sing it, and then it goes."**: the guitar: six strings, and the
  strumming hand as the score has it: each stroke a slanted mark crossing the strings, down one way
  and up the other, heavier on accents, each string ringing from the instant it is met.
- **Line 3, "It's nobody's making, it's old and it's new;"**: the frame drum, and the lights come up
  onto paper. The skin seen at an angle through the camera, drawn as fine concentric and radial
  woodcut lines displaced by the sum of its 196 modes with each hit's captured amplitudes
  (`physics/drum`); bass, tip and mute strokes land where they were struck and look different.
- **Line 4, "by everyone, no one, and now it's by you."**: the four together, composed as one print;
  as the line ends the title is set: THE VOLUNTEERS as a kicker, *Now It's by You* in ink with a red rule.

### s04_bow: turn 1 (50.9 to 55.9 s). Paper.
The fiddle enters. One string across the whole frame in ink, and the bow crossing it at its captured
position, moving with its captured velocity. The string's true shape at this instant (`physics/bow`):
two straight lines meeting at a corner that runs round the string; behind it, the sixteen snapshots of
the current period as a fan of hairlines, so the lens the corner sweeps is visible. Engraving-like:
this should be the most elegant five seconds of the film. Label: fiddle, a bowed string.

### s05_studio: verse 2 (55.9 to 75.9 s). Goes dark; ends black.
Real captures of the studio as the public sees it (the web studio built from main, light scheme, the
awards draft open), taken at 2x with the capture folder's Playwright into `renders/promo/video/studio/`.
Check every capture for anything private (a host name, a user name, a path) and for the serif falling
back to P052 (pin Georgia at capture time with an injected style; never edit the studio's files).
- **Line 1, "The whole world was watching it all in a day,"**: the paper page we are on is the studio's
  Page view of this song; it draws back and is a lit screen in a darkening room.
- **Line 2, "a million bright faces all lit the same way;"**: a wall of identical screens receding to
  the vanishing point, every one the same page, their light the only light.
- **Line 3, "they laughed and they wept, and they scrolled on and on,"**: every screen scrolls together.
  As they scroll they stop being the same: each becomes something the studio does (Arrange, Mix, Sing,
  the six-year timeline, the styles, the notes of a line, Export), and the camera travels across them
  close enough to read.
- **Line 4, "but nobody sang it, and then it was gone."**: the screens go out, the last on "gone".
  Black, and the strand alone. (The last two lines of this verse are the artist's own.)

### s06_volunteers: refrain 2 (75.9 to 95.9 s). Paper returns.
Only the public, blended numbers. There is no volunteer audio and no per-singer data, so no waveform
of a person is ever drawn.
- **Line 1, "Who sang this song? Nobody knows."**: light returns. The line as the Sing view shows it
  (notes as bars with their syllables, the lane of tools/karaoke.js in ink). Seventy-nine short marks
  in the hand ink assemble above it, one per take. Label: 79 takes, eight people. *sang* set apart.
- **Line 2, "It's yours while you sing it, and then it goes."**: under each note of the line its nine
  numbers appear (early, hold, level, swell, scoop, bend, fall, vibrato, tune: `text.json` gesture
  rows) and each note's bar takes the shape those numbers describe: shifted, lengthened, swelling,
  scooped into, bent, falling away, shaken. On "and then it goes" the seventy-nine marks are gone and
  the numbers stay. Label: nine numbers a note; then: the recordings were deleted.
- **Line 3, "It's nobody's making, it's old and it's new;"**: the proof, across the full width: the
  machine's pitch line with no people in it (`throat/lead-0.00-whole.lf0`) in grey ink, and the line
  sounding now over it in ink, the space between them filled with the hand ink.
- **Line 4, "by everyone, no one, and now it's by you."**: the tune's notes that moved to follow the
  singers (`text.json`): the written note hollow, the sung note solid in the hand ink, a hairline
  between. If there is room, the singer's eight numbers leaning toward the people's row.

### s07_gather and s08_lineage: turn 2 and the bridge (95.9 to 120.9 s). Paper; dark on the last line.
- **Turn 2**: everything on the page is drawn into the strand, which thickens into a band: the file.
  Label: one file.
- **Line 1, "Carry it over the water and wire,"**: the file as one strand of bytes across the frame,
  to scale: three quarters of it the song (the release mix's real level and spectrum, `stems/mix.env`,
  drawn as the band's edge), then at byte 12,588,764 the program: real source set in tiny type along
  the strand (`packet-text.json`), its 129 files as divisions sized by their bytes (`packet.json`),
  the voice's weights the largest. The camera travels along the strand and through the join.
  Labels: the song; the program that sings it.
- **Line 2, "hand it along like a coal from the fire;"**: the file passes from machine to machine: each
  hand-over makes a child one generation on, its parent's id in its ancestry. Draw what a child's
  record holds (`generation`, `parent`, `ancestry`) with the one real id, eb8fb05eb2bb, for generation
  0 and no invented ids for children (their ids do not exist yet: a rule of dots). A tree of versions
  grows across the frame, the coal a red point moving along its newest branch. Label: generation 0.
- **Line 3, "it's nobody's making and everyone's own,"**: the three choir voices enter as three more
  strands beside the lead's (their pitch lines from `throat/`). The daisy grows, wordless, on the
  whistle's four notes.
- **Line 4, "it dies in the dark if you leave it alone."**: the light goes; the tree's points go out
  from the tips inward until one ember is left, and the daisy just visible by it.

### s09_broadside: refrain 3 (120.9 to 140.9 s). Full daylight paper.
The sheet being printed is the seed packet's face, and its last frame is exactly the first frame of
the closing shot: the crop of `/art/front-color.png` given in `/blender/corners.json` (u 0.024 to
0.975, v 0.072 to 0.486: the red title band, the 51 seeds roundel, the hatched sky, the daisy's head).
- **Line 1, "Who owns this song? Nobody knows."**: every line the film has drawn (the wire, the pitch
  lines, the voice's envelope lines, the strings, the file's strand) returns at once, in ink, playing,
  and they settle one by one into the horizontal hatching of the face's sky. *owns* set apart.
- **Line 2, "It's yours while you sing it, and then it goes."**: the bank's 51 verses gather as 51
  marks into the red roundel: MIN. 51 SEEDS prints.
- **Line 3, "It's nobody's making, it's old and it's new;"**: the daisy leaves its corner for its place
  on the face and takes its inks, yellow then green, each block landing a little out of register and
  settling.
- **Line 4, "by everyone, no one, and now it's by you."**: the red band prints across the top, and the
  face's own title appears in it syllable by syllable exactly as "now it's by you" is sung.

### s10_cover: tag and ring (140.9 to 151.2 s). Sun.
The Blender frames (`/blender/frames/`, proxies in `/blender/proxy/`), shown raw with the cover's
finish. For about the first second the flat face from s09 is laid over the bowed sheet with the grid
in `corners.json` and dissolves into the photograph. No lyric over the photograph. In the last three
seconds, credits in the shaded paving across the lower quarter, small and centred, from `text.json`
(the title, The Volunteers, the names exactly as CREDITS.md gives them, now.itsby.you).
