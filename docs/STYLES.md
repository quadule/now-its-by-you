# Styles: the song carried into other traditions (2026-09-26)

The artist, after hearing a lineage of five renditions: "This is exactly what I
was hoping for between generations melodically ... We should still strive for
more variation in arrangement and genre too." Until now every rendition was
played by the same small acoustic folk band (docs/BAND.md); only its balance,
its pattern and its lead instrument moved. Now a rendition is played in a
style: a tradition the song has been carried into, with its own band, its own
feel and its own way of arranging a folk song. The genome's tune, words,
chord functions and form stay the song's; a style is flesh, re-realized every
generation (principle 3).

Nobody but the artist can listen. Everything here was judged by measurement
(tools/stylemeter.py), by tests, and by a read-only Fable review of the design
before it was built, which changed a great deal of it (below, "What the review
changed").

## What a style is

A style (songbird/style.py, `STYLES`) is a coherent bundle:

- **a lineup of instruments in roles**: bass, chords, lead and counter-lines,
  pads, percussion, and the lineage's voices as backing singers;
- **idiomatic parts for each**, section by section (songbird/idioms.py): what
  each player does in an intro, a verse, a refrain, a turn, a break, the
  bridge and the tag, and how that changes as the band gets fuller;
- **a feel and a tempo range**: straight, swung, a shuffle, twelve-eight, half
  or double time, or the song re-barred in three (a waltz or a slow six-eight);
  its tempo is a share of the song's own (the seed's 96);
- **a harmony vocabulary**: the colours it may add to the genome's chords (a
  sixth, a seventh, an added ninth, a suspension, a minor iv, an open fifth),
  and how much;
- **leanings for the singer**, gentle ones on habits the singer already has:
  brightness (tilt), breathiness (rd, breath), vibrato depth, scoops and glides,
  dynamics;
- **a mix aesthetic**: offsets to how much room is heard, how close the singer
  stands, how wide the record is, the plate, a lo-fi tape's wear and a darker
  top, and how loud the backing voices are; never the room itself, which is
  the machine's (principle 4);
- **its arrangement's leanings**: how it likes to start and end, whether it
  bares a verse, plays one in stop-time, breaks down before the last refrain,
  lifts the last refrain a step, and what its backing voices sing.

The seed's own band is the first style, the **ballad**. With no style chosen
(the seed, and every record from before styles), a rendition is exactly what
it was: every song's seed score hashes as before and H's seed renders
441dc83b1d1e, byte for byte (tests/test_styles.py).

## The palette

Thirteen styles, in the order of the ring they travel on. Every style's band
renders today; the instruments marked * are played by a stand-in from the
seed's band until the instrument modules being built alongside this land (see
"Instruments").

**Synth folk.** An analog arpeggio* ticking in sixteenths above the voice, a
strummed acoustic guitar, a sub bass* in eighths, a pad*, a drum machine's*
four on the floor (half-time in the first verse), a synth lead* taking the
breaks. Straight, about 110 bpm. Added ninths and suspensions.

**Indie.** Indie folk and folk rock: a kit* on the floor toms in the verses and
four to the floor in the last refrain, an electric bass* in eighths, a
strummed acoustic and a tremolo electric guitar*, an organ* underneath, a
glockenspiel* ringing the refrain's strong notes two octaves up, claps* in the
last refrain, gang vocals. About 112 bpm. Open fifths and added ninths.

**Gospel.** Twelve-eight at about 66: the piano* plays a chord on every beat
and the last triplet of the backbeats pushes into the next, its left hand's
octaves on the strong beats; an organ* holds and swells; claps* and a
tambourine* on two and four; the electric bass* walks. The backing voices
answer the singer's lines, and the song ends on a plagal amen: two more bars,
IV then I, the voices singing "a-men", moving six to five and four to three
over the tonic. Sixths, sevenths, added ninths, a minor iv where the tune
allows (it rarely does under H's singing: it lives in the turns and the amen).
A big room, more plate, the voices 2 dB forward.

**Blues.** Country blues in a shuffle at about 86: the guitar's boogie on its
low strings (the root under each beat, a fifth or a sixth on the lilt), a
slide* and a harmonica* answering the voice, a foot stomping* every beat.
Dominant sevenths on I, IV and V wherever the tune allows (under H's singing,
about a third of the time). Stop-time verses are its habit. Dry and a little
worn.

**Country.** A shuffle or a waltz: the pedal steel* swelling in the alto
register under the voice and answering between lines, a piano's* comping, a
strummed guitar, brushes* in the verses and a groove in the refrains, the
upright walking up into each new chord. Sixths and V7. A third above and
below on the refrains; a key change up a step is its habit.

**String band.** Old-time and bluegrass: clawhammer banjo* (bum-ditty: a note
struck with the nail, a brush, the thumb on the high fifth string, which is
exactly the long-short-short of H's feet) when the band is quiet, forward
rolls when it drives (thumb, index, middle, thumb, index, middle, thumb,
middle, the thumb coming back to the fifth string as the banjo is tuned: A4 in
D), one banjo played both ways in a song; the mandolin's* chop on the backbeat
(the chord struck and choked by the fretting hand); a boom-chick guitar with a
run on its bass strings where the singer holds a line's last note; fiddle
breaks and fills, a counter-line in the last refrain; the upright on one and
three with walk-ups. Straight at about 117 (up to 134), sometimes a waltz. A
tenor harmony on the refrains.

**Shanty.** A sea shanty or work song: the shantyman sings the first verse
alone (or over the concertina), then the gang (every lineage voice) joins on
the refrains; feet stamping* on one and three and hands* on two and four; a
concertina's oom-pah (oom-pa-pa in six-eight); the fiddle leading the intro
and taking counter-lines. For about three machines in ten the crew's
squeezebox is an accordion instead, its oom-pah on the Stradella bass and
chord buttons (a lineage keeps the one it had). Straight or a slow six-eight.
Open fifths. A big, wide room.

**Ballad.** The seed's own band, arranged by songbird/band.py exactly as
before: harp, cittern, whistle, fiddle, guitar, upright bass, frame drum and
reed drone, the pattern and lead the machine and the drift choose. As a style
it can also take the arrangement's options (a bare verse, a breakdown,
entrances, a lift, a ritardando, backing voices).

**Chamber.** Chamber folk: a string section* holding the harmony under the
voice, a cello* with its own line below the tune, the piano's* broken chords;
no drums; rubato (the players' time looser, a broader ritardando). Straight
or a waltz. Major sevenths, added ninths, suspensions.

**Songwriter.** A Travis-picked guitar (the thumb alternating between two
bass strings on every beat, the fingers on the treble between, a pinch on the
one), a harmonica* in the intro, the breaks and between lines, an upright
bass coming in later. Plain (no ornaments), close and dry. Added ninths.

**Lullaby.** A music box* picking the chord out high above the voice, a
harp's broken chords, a celesta* on the refrains, a soft pad*. A waltz or a
slow six-eight where the song allows. Breathy and soft, close, with a plate.

**Ambient.** A synth pad* and slow bowed swells* over a held drone, a
vibraphone's* scattered notes; no drums; half-time. The voice far off in a big
space: the most room of any style.

**Lo-fi.** Bedroom lo-fi: an electric piano's* lazy chords (the colour
without the root, struck on the one and answered on an off-beat, never the
same twice), a soft swung drum machine* (a boom-bap), a round sub bass*, a
vibraphone* now and then. Swung, about 78. Major and minor sevenths. Worn
tape and a dark top (the mix's wear and tilt).

## How styles travel

**The ring.** The styles sit on a ring, in the order above, each between two
that share its instruments or its feel: synth folk and indie (drums and
synths), indie and gospel (organ, claps, a crowd), gospel and blues (sevenths,
the twelve-eight and the shuffle), blues and country, country and the string
band (guitar, the two-beat bass, a fiddle or a steel), the string band and the
shanty (fiddles and feet), the shanty and the ballad (the Celtic sea songs),
the ballad and chamber (harp and strings), chamber and the songwriter (quiet
acoustic), the songwriter and the lullaby, the lullaby and ambient, ambient
and lo-fi, lo-fi and synth folk (the machines). The ring runs once round a
plane of *machine* (from tradition to electronics) against *drive* (from
hushed to loud).

**A machine's home.** A machine is at home somewhere on the ring: its point on
that plane, read from its harvest (newer words and younger files lean toward
the machine's end, older ones toward tradition; a brisk, busy, rested machine
toward the loud styles, a slow, tired, free one toward the hushed), scattered
by its identity so machines that read alike still differ. Over 150 made-up
machines every style is some machines' home, 4% to 12% each.

**A child's style.** A child starts from its parent's style and moves a tenth
of the way round the ring toward its machine's home (`PULL_STYLE`), and by the
slow drift (`STYLE_SPAN`, the slow view of a new drift dimension, "style");
the style is the one that place falls in, held with the same stateless Schmitt
trigger as the band's pattern (within 0.2 of a boundary it keeps the style
the drift last sat firmly in), and never more than one step from the
parent's. A machine that gave nothing keeps its parent's style.

**The rates, measured** (tests/test_styles.py checks them loosely; the
harness that tuned them is in the commit history):

| | |
|---|---|
| a child keeps its parent's style | about 59% of generations (over machines, dates and parents in every style) |
| otherwise | one step round the ring, toward its machine's home or where the drift leans |
| a machine singing one parent, day after day | changes style about twice a year, never back and forth within a fortnight |

So in a lineage the genre changes about two generations in five, more often
than the melody's variants or the words, as the artist asked, while a child
usually still sounds like its parent's band. With a drift of 1 moving 1.1
steps and a pull of a tenth, a machine can't drag a lineage across the ring:
the ring is walked a step at a time, like the folk process.

**What a style brings when chosen** (`variation.choose_style`, the last
decision, once the form, the choir and every number are chosen):

- the arrangement's options, drawn afresh for each rendition from the style's
  leanings and turned slowly by the season's drift (a new dimension,
  "arrange"), fixed by the machine and the parent, so renders a minute apart
  agree; the feel is kept from the parent three times in five when the style
  is;
- the lineup, as loud as the style has each, each machine's balance its own
  way (and the slow balance drift), pulled from the parent's gains where the
  parent had the instrument;
- the tempo: the parent's tempo as a share of its own style's centre, pulled
  toward the machine's pace as always, taken as that share of the new style's
  centre and held to its range;
- the leans on the band (density, brightness, wear, ornament, arc), the
  performance (a chamber group's looser time and broader ritardando), the
  singer and the mix, each applied so it never compounds: a child takes back
  the share of its parent's style's lean it inherited, so generations in one
  style settle at exactly the style's lean.

`songbird render --style NAME` plays a rendition in a style of your choosing
(still the machine's in everything else) and `--arrange FIELD=VALUE` sets any
of its options.

## The arrangement's options

Any style can take them (the ballad too, when it is chosen as a style); each
style leans toward some (`StyleDef.options`):

- **how it starts**: an instrument states the tune (the lead, as the seed
  does), or a pad swells in alone, where the form has an intro; where it
  doesn't, a count-in (four clicks on the sticks, the hands or a muted chop, a
  bar before the song) or the singer alone, the band coming in on the second
  line; or a quote: the lead instrument alone, over the drone, plays a line of
  an older song the genome names (`quote` in the genome, its tune on the
  song's grid; H's is the chorus of Daisy Bell, 1892, the first song a computer
  sang, at Bell Labs in 1961) in bars cleared before the song as a count-in's
  are; a genome with no quote starts as the form has it;
- **a bare verse**: one verse sung a cappella, or over one instrument (a
  shanty's first; for others a later one);
- **stop-time**: a verse where everyone keeping time hits each bar's one
  together and leaves the words bare (a line or a fill may go on);
- **a breakdown**: the last refrain starts with only the rhythm section and
  the rest of the band comes back at its third line;
- **a half-time bridge** (styles with drums);
- **entrances**: the first verse builds, the chords first, then the bass,
  the drums, the rest, a line at a time;
- **a lift**: the last refrain (and the tag after it) a whole step up, the
  singer, the voices and the band together (a truck driver's modulation);
- **the ending**: the last chord ringing (the seed's), a broad ritardando, a
  cold stop (the last chord short, 0.9 s of ring), the last line sung again,
  or a plagal amen;
- **backing voices**: the gang on the tune (unison, the low voices an octave
  down), a harmony above and below (the chord tones a third or more from the
  tune, as the lineage choir sings in the bridge), answers at the ends of
  lines (the line's last word again while the singer holds it), or oohs on
  the chords under the singer. Only ever the lineage's own voices, as many as
  the lineage has (params.choir): at the first generation a shanty's gang is
  one sailor, by the sixth the crew has arrived. Never where the genome gives
  the lineage its own harmony (the bridge and the tag); fills keep off the
  lines the voices answer.

## The harmony

The genome's chord functions persist: I is always I. A style's colours are
chosen per chord, as often as its harmony knob says, and then placed only
where they sit with the tune:

- a colour is dropped for a moment if it would be a minor second (or major
  seventh) from any note sung then;
- where it lands in a voicing, it may not be a major second, minor seventh
  or tritone within an octave of a note sung on a strong beat (a foot's
  start) or held a beat or more; a ninth or more away is an ordinary
  extension (an added ninth under the tune). A guitar leaves such a string
  unplayed, a pad or a piano moves the tone an octave down or plays the third;
- chords never sit on the pitch being sung (an octave down instead), and a
  banjo's fifth string and a guitar's bass run are stopped where they would rub.

H's tune is major pentatonic and never sings 4 or 7, so most of what is
refused is a maj7 under a sung tonic, a b7 under a sung sixth, or an added
ninth right against a sung third. tests/test_styles.py plays seven styles with
the harmony knob at 1 and checks every added tone against every sung note.

## Feels, and the song in three

Swing is the band's own for the seed and the ballad; for another style its feel
decides: straight (a machine's own lilt, at most 0.25), swing (0.35 to 0.7), a
shuffle and twelve-eight (a full triplet lilt, so the grid's quarter-beats land
on triplets and the band plays twelve-eight), half and double time (the drums
and bass), all counted from the bar line (realize's Clock).

A waltz or a slow six-eight re-bars the song in three. H's feet are
strong-weak-weak on units 0, 2 and 3 of four; the Clock moves them to three
even pulses, so each foot becomes a bar of a waltz (or a dotted beat of six-
eight) and every stressed syllable lands on a downbeat, with the tune's pitches
and order untouched ("Who | MADE this | SONG? | NO-bo-dy | KNOWS"). It is
offered only where every sung note of a song starts on those positions (H's
do; tests/test_styles.py checks every syllable against the waltz's beats).
Tempo keeps meaning the song's beats a minute, so a waltz's quarter is 1.5
times it, and waltz styles have their own, slower, ranges.

## The record, for the studio

`Params.style` (songbird/style.py `Style`), each field off by default:

| field | what it is |
|---|---|
| name | the style (`STYLES`); "" the seed's own arrangement, exactly |
| lineage | the styles this rendition's line was sung in, one a generation, oldest first, this one last (up to 16) |
| feel | straight, swing, shuffle, twelve, half, double, waltz, six; "" the style's own |
| harmony | 0..1, how much of the style's vocabulary colours the chords |
| intro | lead, pad, count, voice, quote; "" as the form has it |
| alone, alone_with | which verse (1 the first) is bare, and the one instrument under it ("" a cappella) |
| stops | which verse is in stop-time |
| breakdown | the last refrain starts stripped |
| bridge | "half": a half-time bridge |
| lift | the last refrain a whole step up |
| ending | rit, cold, amen, repeat; "" the last chord rings |
| coda | quote: the lead alone plays the genome's quote's first notes over the last chord as it rings two bars on (H: Daisy, Daisy); "" none |
| motif | bridge: the lead instrument (H: the whistle) plays the quote's first notes over the bridge's third phrase, the fiddle's pad resting, where they sit in the chords (H: so mi over I, do over vi, so, over V); chance: about a third of renditions, by seed; "" none. Played about 3 dB under the intro's statement of the tune (it sat 8.6 dB under it and went unnoticed, 2026-09-27) |
| entrances | the first verse builds line by line |
| backing, voices | what the backing voices sing (oohs, echo, thirds, gang) and how many sang it |

`Band.lineup` (songbird/band.py): instrument -> gain, 0..2, for whoever plays
when a style sets the band; empty for the eight fixed gains, as before.
`MixParams.plate` (0..2) scales the singers' plate. All load from older
records (missing: the seed's), and the seed's own style and an empty lineup
leave no trace in a record, so a parent's digest (and the rendition seed its
child draws) is as it was.

## Instruments

songbird/synth/instruments.py has a registry: any module under songbird/synth/
that exposes a `SPEC` and a `render()` (the contract the instrument agents
build to) adds its instruments by name, placed and levelled by its SPEC and
scaled by the lineup's gain. The eight keep their exact code path. An
instrument no module provides yet is played by a stand-in from the eight under
its own name, place and level (banjo and mandolin by the cittern, piano and
the mallets by the harp, organ, pads, strings and free reeds by the reed box,
cello and pedal steel by the fiddle, basses by the upright, the kit and hand
percussion by the frame drum taking the nearest stroke, harmonica and synth
lead by the whistle), each levelled so a typical part at velocity 0.6 sits as
its kind's reference does. Stand-ins make every timbre Celtic: until the real
instruments land, the styles differ in rhythm, harmony, form and texture, not
in sound. The mix finds each stem's channel strip by its name (keys, organ,
reeds and harmonicas, strings without the fiddle's high-pass, synths, the
percussion names on the drum strip, and a kit, a banjo and a mandolin on their
own; docs/INSTRUMENTS-B.md, For the mix).

## Measurements

Measured with tools/stylemeter.py on one made-up machine (ada, 2026-09-27), three lineage voices, a verse and
a refrain in each style with no bare verse, stand-in instruments, the formant singer; the band's level is
its bus at master level, and the voice over the band is measured where the voice sings (as MIX.md does).
Every master is -14.0 LUFS integrated, and no sample reaches full scale.

| Style | Feel | Tempo | Band in the verse | Band in the refrain | Voice over band, verse | refrain | True peak | Words misheard |
|---|---|---|---|---|---|---|---|---|
| synthfolk | straight | 110 | -30.4 LUFS | -25.9 LUFS | 14.0 dB | 8.8 dB | -1.05 dBTP | 43% |
| indie | straight | 112 | -32.6 LUFS | -27.1 LUFS | 14.3 dB | 8.2 dB | -1.05 dBTP | 33% |
| gospel | twelve | 66 | -28.7 LUFS | -24.6 LUFS | 12.9 dB | 7.7 dB | -1.05 dBTP | 34% |
| blues | shuffle | 86 | -26.0 LUFS | -23.8 LUFS | 12.3 dB | 9.2 dB | -1.22 dBTP | 41% |
| country | shuffle | 96 | -26.7 LUFS | -23.7 LUFS | 13.0 dB | 9.2 dB | -1.36 dBTP | 20% |
| stringband | straight | 117 | -26.5 LUFS | -24.3 LUFS | 12.8 dB | 9.7 dB | -1.84 dBTP | 16% |
| shanty | six | 115 | -42.4 LUFS | -31.0 LUFS | 23.4 dB | 11.4 dB | -1.05 dBTP | 40% |
| ballad | straight | 96 | -25.7 LUFS | -24.3 LUFS | 11.8 dB | 9.6 dB | -1.6 dBTP | 29% |
| chamber | waltz | 60 | -26.1 LUFS | -24.0 LUFS | 11.9 dB | 9.0 dB | -1.82 dBTP | 71% |
| songwriter | swing | 90 | -27.3 LUFS | -22.6 LUFS | 13.3 dB | 8.2 dB | -1.05 dBTP | 26% |
| lullaby | six | 79 | -26.5 LUFS | -26.7 LUFS | 9.9 dB | 10.0 dB | -1.05 dBTP | 46% |
| ambient | half | 67 | -27.7 LUFS | -29.3 LUFS | 9.5 dB | 10.3 dB | -1.05 dBTP | 60% |
| lofi | swing | 78 | -25.1 LUFS | -23.4 LUFS | 11.1 dB | 8.8 dB | -1.06 dBTP | 23% |

- **The singer is always the loudest.** The voice stands 7.7 to 12.9 dB over the band in the refrains
  (the seed's own band: 9.6) and more in the verses, where every style is sparser. The shanty's first
  verse is the shantyman almost alone, by the style's design.
- **Peaks** stay under the master's ceiling: the true peak is -1.1 dBTP or lower everywhere.
- **Nothing sits on a sung pitch.** Counting comping notes that start on the pitch being sung finds none
  in any style but the ballad and synth folk. The ballad's 24 are its lute doubling the last refrain by
  design. Synth folk's 2 are the arpeggiator's. tests/test_styles.py checks every coloured tone against
  every sung note.
- **The words are the open problem.** Whisper base.en mishears 16% to 71% of the words (the ballad's own
  band: 29% here, 17% in its tour excerpt with an intro). Whisper is a jumpy judge on about 70 words;
  single runs differ by 10 points. The string band and country are as clear as the ballad; chamber,
  ambient and the lullaby are much worse.
  - Chamber stays near 50% even a cappella with the ballad's singer and mix. So its trouble is not the
    band or the leans; it is somewhere in the slow tempo, the looser timing and the re-barring. That
    is the first thing to look at.
  - The rest likely come from sustained textures (pads, a reed-box stand-in, harp stand-ins ringing
    4.5 s) sitting in the voice's range. The real instruments may change this.

## Examples

renders/production/styles/ (README.txt describes each; tools/styles_examples.sh
regenerates them): a genre tour (one machine, one day, every style, a verse and
a refrain), four full songs, and a lineage of six generations that wanders from
the ballad through the shanty, the string band, country (twice), the blues and
gospel.

## What the review changed

A Fable advisor reviewed the design before it was built, reading the code and
measuring. It changed:

- **The map.** The draft put the styles on a plane with a pull of 0.4; its
  harness measured 27% of children keeping their parent's style and five style
  changes a year. A one-dimensional arrangement through the band's own
  hysteresis, with a small pull, gives the rates above.
- **The harmony rule.** The draft refused a second against a sung note in any
  octave, which forbade the ordinary chords half the palette is made of (an
  added ninth under a sung third, V7 under a sung fifth). The rule now judges
  where the colour lands.
- **Backing voices.** Only the lineage's own, never a stand-in group: "a
  shanty at generation 1 is one sailor; by generation 4 the crew has arrived."
- **The record.** The seed's style leaves no trace in a record, so existing
  lineages keep their rendition seeds.
- **The mix.** A stem named "synthlead" would have gone to the voice bus, a
  cello through the fiddle's 180 Hz high-pass, the kit and hand percussion
  through a plain strip; all fixed. Styles lean on the mix but never touch the
  room, which is the machine's.
- **The palette.** Build first the styles whose identity is rhythm and
  arrangement, since stand-ins sound alike; merge old-time and bluegrass (the
  band's density picks clawhammer or rolls); fold a Celtic session into the
  ballad (the seed already is one).
- **The swing and the tempo.** The feel chooses the grid and the band's swing
  is only how much within a swung one, so a twelve-eight can't decay to a
  shuffle down a lineage; tempo is taken as a share of each style's centre.

## Decisions to reconsider

- **The rates**: a child keeps its parent's style about 59% of the time
  (`PULL_STYLE` 0.1, `STYLE_SPAN` 1.1). Raise the pull or the span for more
  genre change, lower them for less.
- **The palette's thirteen**, and the ring's order. Each is one entry in
  `STYLES` and `RING`; removing one from both takes it out of circulation.
- **The seed's first children**: from the seed's ballad a first generation can
  only reach the shanty or chamber (its neighbours); every other style is
  several generations away.
- **Backing voices are the lineage's own**, so early generations have thin
  groups. The tour renders with three voices to show them.
- **Styles lean on the singer** (brightness, breath, vibrato, scoops) and on
  the mix (room heard, closeness, width, plate, a lo-fi style's worn tape and
  dark top). Each is a line in the style's entry.
- **The key lift** is a transposition after the arrangement: the harp's and
  guitar's sympathetic strings stay tuned to the old key for the last refrain.
- **A waltz or six-eight** makes the song half again as long at the same
  tempo; waltz styles take a slower tempo to compensate.
- **Stand-ins** until the instrument modules land; see "Instruments".

## Measured again with the learned voice and the real instruments (2026-09-26, morning)

This is the same tour (ada on 2026-09-27, a verse and a refrain each), after the instrument
modules and the learned voice landed on main. Whisper's words misheard on the finished mix
(`tools/stylemeter.py --files renders/production/styles/tour --wer`):

| Style | Now | Before (stand-ins, formant voice) |
|---|---|---|
| ballad | 1.4% | 29% |
| lofi | 1.4% | 23% |
| blues | 5.7% | 41% |
| songwriter | 5.7% | 26% |
| gospel | 8.6% | 34% |
| stringband | 10.0% | 16% |
| lullaby | 10.0% | 46% |
| chamber | 10.0% | 71% |
| shanty | 11.4% | 40% |
| ambient | 11.4% | 60% |
| synthfolk | 12.7% | 43% |
| country | 15.7% | 20% |
| indie | 17.7% | 33% |

Every master is -14.0 LUFS with true peak at -1.1 dBTP or below. What was the open problem is
mostly the old voice. Indie and country, with the kit and electric guitar under the voice, are
where to look next.

# Two more: a cappella and a Celtic session (2026-09-30)

The artist asked for two traditions the song was always close to: **a cappella** (shape-note and folk
harmony singing: the song's idea, communal singing, with nothing but voices) and a **Celtic session**
(Irish traditional: whistle and fiddle on the tune together, a bodhrán, an open-tuned guitar). The ballad
is already a Celtic ballad band, and the first review folded "a Celtic session" into it; this one is the
session itself, played the way a session plays: the tune in unison, round twice, ornamented, in a jig's
six-eight or a reel's drive.

(What follows is the design as it went to review; "What the review changed" and "As built, and measured",
at the end, say where the build differs: the parts are a treble, an under voice and an alto, not a bass;
the jig is quicker, the reel in double time, the slow air the first time round.)

## Where they sit: beside the ring, not on it

Every style is on the ring, and a machine's home is an angle on the ring's plane (`home()`, one slot a
style). Putting two more on it would move every slot, and so the style every existing lineage steps into
next: renders that are byte-identical today would not be tomorrow. So the two sit **beside** the ring
(`OFF_RING`), each at a ring style's place: a cappella at the shanty's (the gang, the crowd singing), the
session at the ballad's. They are reached by a person choosing them (`--style`, the studio's style card,
which lists them after the ring's) and a lineage in one of them travels from its anchor's place: a child
that would have kept the anchor's style keeps its own (a session's child stays a session), one that moves
steps to the anchor's neighbour. Nothing ever steps *into* them by chance, which is the one thing to decide
(below). The other agent's house and dub can sit the same way; `OFF_RING` is shared.

## A cappella (`acappella`)

**The band is the choir.** The lead sings the tune (as in shape-note singing, the tune is the tenor: the
middle of the sound, with a part above it) and a **group** of voices sings the rest: the lineage's own
voices first (params.choir), then the program's own harmony voices (the stand-ins `lineage_voices()`
already draws) to make at least three parts, up to six (`Style.voices`, which already said "stand-ins
where a style wants a group"). No instruments. Hand claps or foot stomps come by chance (about a third of
renditions stomp, a quarter clap), in the refrains; a style's player that doesn't come sits in the lineup
at gain 0 (a new `StyleDef.optional`: part -> the chance it plays, drawn per machine and parent, a lineage
keeping what it had), so the lineup is never empty (empty is the seed's eight) and the studio can bring
one in.

**The parts** (a new writer, `idioms.shape_parts`), each voice a role in turn (bass, alto, treble; a
fourth voice doubles the bass, a fifth the alto...), homophonic, every voice on the lead's syllables:

- *bass*: the chord's root, else its fifth, as low as the learned throat sings cleanly (theory.FLOOR, E3:
  below it its pulses come apart), under the tune;
- *alto*: the open fifth over the bass (or the root), between the bass and the tune; a third only where
  neither fits;
- *treble*: above the tune, a fourth or fifth up on the chord's root or fifth (open), the third only where
  those don't fit; at most G5;
- every part led from its last note (the nearest that fits), parallel fifths allowed (they are the
  sound), never a semitone from the tune's note or on it.

**Section by section:**

- *intro, break, outro* (no words): **singing the notes**: the lead and the parts sing the tune on its
  shape-note syllables (four-shape fa, sol, la, mi, from each note's degree in the relative major; each
  part its own note's), as a Sacred Harp class sings a tune through once before the words (`intro=notes`);
  or hummed on "oo" (`intro=lead`);
- *verse 1*: lined out, the lead alone (`alone=1`, often), or with the pads;
- *verses*: under the lead, by the drawn **backing**: `hum` (a new kind: the bass and alto hold each
  chord's root and fifth on "oo", an open-fifth drone), `oohs` (all the parts on "oo", a chord each), or
  `echo` (the group answers the end of each line: call and response); in the first verse the group sings,
  the voices come in a line apart (bass, then alto, then treble: `entrances`);
- *refrains*: all the parts, on the words;
- *turns*: the group holds the turn's chords on "oo" (there is no line to quote);
- *bridge and tag* (the genome's own lineage harmony): the lineage's voices sing it as always; the
  program's own voices (those past params.choir) add the bass under it;
- *the end*: the final chord held, the lead with it (a fermata: the ring), or the last line again.

**Who sings which part.** A lineage stand-in drawn "low" sings everything an octave down (VoiceParams.shift
-12), so a treble part would land under the tune and a bass part below what the throat can sing. In an a
cappella score (its band settings say so) the singers are matched to the parts by range at synthesis: the
lowest voices (a low stand-in, the longest tract) to the lowest part, each at the written pitch
(`shift` 0). Nothing changes for any other style.

**Feel, tempo, mix.** Straight (0.7) or a waltz (0.3); shape-note singing is brisk: straight at 0.85 to
1.1 of the song's tempo (centre 0.95), a waltz at 0.6 to 0.76. The harmony vocabulary is the open fifth.
The singer leans plainer (less vibrato, pressed a little: rd -0.05); the mix a big room (space +0.25, the
plate +0.2, width +0.15) with the group 1.5 dB forward of where a choir sits (`mix.choir`). Its options:
the intro sung on the notes (0.6) or hummed (0.4); verse 1 lined out (0.6); entrances (0.6); the backing
hum (0.4), oohs (0.35) or echo (0.25); the ending ring (0.6), the last line again (0.25) or broad (0.15);
no breakdown, no lift, no stop-time.

**Its cost.** Each voice is a learned-throat part; the group sings the whole song where a lineage choir
sings the bridge, so a render is slower (about one voice's time per part, on two threads two at once).
Memory is set by the heaviest part (a choir voice: 5.7 MB a second on two threads) and should sit near a
light band's, to be measured with tools/render_memory.py (a whole song, three and six voices).

## A Celtic session (`celtic`)

**The lineup**: the whistle and the fiddle (the tune), the frame drum played as a **bodhrán** (tipper
patterns), a guitar in an **open tuning** (DADGAD, moved to the song's key), and by chance a
**concertina** (0.45: on the tune with the others) and the pipes' **drones** (0.35: the reed drone, the
tonic and fifth, under the tunes and the bridge).

**Feels.** A **jig** (the song re-barred in six-eight: H's long-short-short feet are already a jig's
dotted beat, da-da-da, the "six" feel) at 1.25 to 1.5 of the song's tempo (centre 1.38: 132 for H, a
dotted beat at 66: a sung jig, not a dance's 116), 0.55; or a **reel** (straight, a machine's small lilt
at most) at 1.1 to 1.4 (centre 1.25), 0.45.

**The tunes as a set.** Where nobody sings (the intro, the turns, an outro), everyone on the tune plays it
together in unison (each in its own octave: the whistle an octave up, the fiddle and the concertina where
they sit), a heterophony: the whistle cuts and rolls, the fiddle slides and slurs, the concertina plays it
plain. A played section of four bars or less goes **round twice** (the intro's four bars become eight, a
turn's two four, the second time the turn's line is quoted again): the first time the lead with the
guitar, the second the others join and the bodhrán comes in. The break (already eight bars) goes round
once. A person's `arrange.<section>.bars` wins over it.

**Or a slow air** (`intro=air`, 0.25 of intros): the lead alone (the whistle, or the fiddle), over the
drones if they came, plays the intro's tune out of time: about 1.8 times as slow, each line broadening
towards its end; the band comes in with the singer. The clock (realize.Clock) gets an optional stretched
span at the start; every other rendition's clock is as it was.

**The players, section by section**: the guitar's DADGAD strum (a new idiom `dadgad`: the open strings
ringing the tonic and fifth under every chord, fretted to the chord tones within four frets, an open
string that would rub a chord tone or the sung note fretted to the nearest chord tone; the jig's
down-down-up per dotted beat, the reel's down-up eighths, accents on the beats); the bodhrán (a new idiom
`bodhran`: in the jig, down-up-down on each dotted beat, the bar's first stroke open and low, the
others the tipper; in the reel, down-up eighths, the open stroke on one and three, the backbeat's up
stroke accented with the back hand high on the skin (a new stroke, `top`: the drum's own model, the hand
pressed high: pitch up a third, drier), ghost strokes left out when the band is sparse; `light` in the
verses); in the verses the fiddle and the whistle take turns at fills between the lines, sitting out the
first verse; the refrains the fiddle's counter-line and the whistle's descant in the last; the bridge the
fiddle's held tone and the drone.

**The singer.** Kept, with a sean-nós lean: plainer vibrato (-8 cents), a little pressed, and a few
ornaments of its own: on some long stressed notes with no ornament of the lineage's, a turn or a grace
from the song's own ornament vocabulary (variants.candidates: always a degree of the song's scale,
long enough to hold it), about one note in eight, fixed by the rendition's seed and not handed down
(the lineage's own variants are). The band's doubling follows the singer's ornaments as it always has.

**Its leans**: the band a little brighter and much more ornamented (ornament +0.3: cuts and rolls come
twice as often), wear +0.05; a pub's room, not a hall (space -0.1, intimacy +0.08). Options: intro lead
(0.75) or air (0.25), verse 1 alone 0.1, entrances 0.3, a lift 0.1, endings ring 0.4, cold 0.35 (a
session stops together), rit 0.25; backing voices thirds (0.3) or none; no stop-time, no breakdown. Its
colours: sus2 and the open fifth (the drones' sound).

## What's new, and what stays as it was

- style.py: the two entries, in their own block, `OFF_RING` and the step from an anchor; `StyleDef.optional`;
  `INTROS` + "notes", "air"; `BACKINGS` + "hum". No new Style field.
- idioms.py: `shape_parts` (the a cappella's voices), `w_dadgad`, `w_bodhran`, the set's unison and its
  round-twice entrances; band.quote takes a span shorter than its section (a turn round twice).
- realize.py: the shape-note syllables in an a cappella's unsung sections; the lead's last note held with
  the group's; the slow air's stretch in the Clock; the sean-nós ornaments merged with the lineage's for
  the singer. Each only for its style or option.
- takeover.py: a Celtic set's default length for a short played section (a person's length wins).
- synth: the drum's `top` stroke (one row of data, no new kernel); the guitar's open strings at DADGAD
  when the style says so (its sympathetic strings); an a cappella's singers matched to parts.
- explain.py: the names (a cappella, voices alone; a Celtic session), the backing, the intros, the
  optional players, the group; the style card lists every style, the ring's and those beside it.
- No numba kernel is added or changed, so the browser's translation (docs/BROWSER-RENDER.md) is as it was.

Every existing render stays byte-identical: the seed and the goldens, and each style's own renders (a few
machines and dates, compared by PCM id against the tree before); `--replay` exact; the packet within 8 MiB.

## Decisions for the artist

- **On the ring or beside it.** Beside it keeps every lineage where it was going; on it, one line in `RING`
  each, every lineage's next step would be redrawn once.
- **The program's own voices in an a cappella**: at least three parts even at the first generation, where
  the other styles' backing is only ever the lineage's own. Communal singing needs a group; the lineage's
  voices take the parts first.
- **Singing the notes** (fa-sol-la) before the words in the intro, or humming.

## What the review changed (2026-09-30)

A read-only Fable review of the design above, before a line was built. Its points, and what they changed:

- **The lexicon.** The seed scores' golden hashes each score's lexicon, so the shape-note syllables (fa, sol,
  la, mi) go only into an a cappella's score, never into `SUNG_SYLLABLES`; "fa" has no dictionary reading and
  "sol" two, so both are pinned (F AA1; S OW1 L, as Sacred Harp singers say it).
- **Off the ring, everywhere.** `place()` and the style card index `RING` directly; every such place maps an
  off-ring style to its anchor first, and the card lists the styles beside the ring.
- **Round twice is the style's own length**, inside `takeover.phrase_plan` (so the layout, the chord times,
  the spans, karaoke and the piano score agree), past `fit`'s "a turn keeps its bars" only for that default:
  a person still can't lengthen a turn. The quote's choice of line is seeded from the section's start both
  times round, so the same line is played twice (its ornaments differ).
- **The group is read**: `Style.voices` was recorded but the backing read only params.choir; the a cappella's
  parts read the larger.
- **No bass on roots.** The lead's lowest note is about a fourth under the tonic, and the throat's floor is
  E3: under H's A3 there is no room for a bass. The parts are the **treble** (a fourth, fifth or octave over
  the tune: the sound of shape-note singing when the tenor has the tune), the **under** voice (the root where
  it fits between the floor and the tune, else a chord tone there) and the **alto** (between, or over the
  tune where there is no room under it); the third is allowed about a third of the time, never at a line's
  cadence, so it is open but not organum. The treble tops out at E5 (the throat is measured to B4).
- **The jig's tempo.** A dotted beat at 66 is a march, not a jig; the six-eight is now 1.35 to 1.6 of the
  song's tempo (centre 1.5: a dotted beat at 72, the eighths 0.28 s apart, a sung jig, still singable).
  The palette's ceiling rises from 1.5 to 1.6 of the song's tempo, which is the studio's own bound.
- **The reel is double time**: at 115 quarter notes a straight strum is a folk strum, not a reel; the reel is
  the "double" feel, the bodhrán's down-up and the guitar's strokes on the sixteenths (a reel's eighths at
  230), the singer at the song's pace over it.
- **The slow air is the first time round**: the intro's first pass out of time, its second in time with the
  band joining (an air into a tune), then the singer; never eight bars of solo whistle.
- **DADGAD stays DADGAD**: an open D tuning with a capo up to six frets, or tuned down up to five, never
  retuned so its low string falls under what a guitar has; its sus4 on V is its sound (fitted away from a
  sung third, as every colour is).
- **The stand-ins in a group**: their vibrato (15 to 40 cents), scoops and slow wander churn against open
  fifths held a whole song; an a cappella's singers are held to a choir's (vibrato at most 14 cents, a
  later onset, scoops at most 0.2) at synthesis, as the singer matching is.
- **Its cost** is to be measured with six voices over a whole song, and the a cappella built first (voices
  only), the session second.

## As built, and measured (2026-09-30)

`songbird render --style acappella` or `--style celtic`, or the studio's style card (it lists them after the
ring's). Nobody has listened; everything here is measured.

**What stays as it was.** The seed, both machines' own renditions (ada on 2026-09-27, bob on 2026-03-14),
gospel, the string band, the ballad, the shanty and lo-fi render to the PCM ids they rendered to before
(after each of the three builds), and a gospel choir of three too after the choir's bus was made lean; the
goldens and the whole suite pass. The packet: 6.31 MiB of 8.

**A cappella**, measured on ada's (2026-09-27) with its stems: every part in tune with its written notes
(each note's f0 over its middle, against the note: the median 0.8 to 1.3 cents flat, 95% to 97% within 25
cents, for the lead and all three parts: the choir's vibrato held to 14 cents does what it was for); the
parts where they sing with the lead: fifths 19%, fourths 16%, octaves 13%, thirds 29% (minor 17, major 12),
sixths 12%, and the passing tones' seconds and sevenths 11%: open, with thirds. Every part between E3 and
E5, never on the lead's note or a semitone from it (tests/test_acappella.py). Words misheard (Whisper, a
verse and a refrain, three voices): 15.2%, beside the ballad's 14.3% in the same run.

**A Celtic session**, measured from its scores and stems: a reel (ada: double time at 114.8, its eighths at
230 a minute) has the bodhrán's strokes a median 1.09 sixteenths apart (148 open, 575 tipped, 83 with the
back hand high), 780 onsets heard in its stem against 806 written; a jig (bob: 150.4, a dotted beat at 75)
has them 1.03 eighths apart, the bar down-up-down, down-up-down. The whistle cuts 16 to 26 of its notes, the
fiddle 5 to 18; the singer's own ornaments sit on 6 of 376 and 9 of 250 notes. The voice stands 14 dB over
the band in a verse and 8 in a refrain (the ballad: 10.6 and 7.8); words misheard 17.1%. With a slow air,
the whistle alone over the drones plays the intro's first four bars in about twice their time, and the
session comes in on the second four.

**Memory**, on two threads (tools/render_memory.py's measure, `MallocLargeCache=0`), every one under the
studio's estimate (`public.render_mb`) and within 1.3 of it (tests/test_studio_public.py, MEASURED):

| version | length | peak |
|---|---|---|
| a cappella, three voices of the program's own (a waltz) | 226 s | 1.51 GB (1.85 before the choir's bus was made lean) |
| a cappella, six lineage voices | 226 s | 1.51 GB (2.33 before) |
| a cappella, straight | 159 s | 1.20 GB |
| a cappella, four verses, every part, six voices, tempo 55 | 496 s | 2.79 GB |
| a Celtic session, a jig with a slow air | 120 s | 1.07 GB |
| a Celtic session, four verses, every part, a reel at 91 | 347 s | 2.34 GB |

The group's bus used to hold every voice until the last was sung, so an a cappella's peak grew with its
voices; now it sums them as they come, in the same order (the same bits). In 2100 MB the studio makes about
5.0 minutes of an a cappella in one go and 4.1 of a session. A render of the a cappella takes about 25 s for
226 s of song (40 s with six voices), a session about 10 s for 120 s.

**For the artist**: renders/styles/acappella-*.flac (ada and bob as their machines choose; coral with five
lineage voices, the notes and a hum; dmitri answering the lines) and celtic-*.flac (ada's reel, bob's jig
with the concertina, coral's slow air into a jig, dmitri's reel), each with its record and score beside it.

**Left open**

- On the ring or beside it (above). Beside it, they are reached only by a person's choice, and a lineage
  in one stays in it or steps to its anchor's neighbours.
- The a cappella's under voice is an under voice, not a bass: the learned throat thins below E3. A real bass
  (roots an octave down, D3 and under) waits for a throat that sings there.
- The bodhrán is the frame drum's model with a fifth stroke; its tipper's roll (the triplet "treble") is
  left out, as the ballad's triplet fills were (three even taps on a synthesized skin read as a finger on a
  microphone).
- The session's jig is a sung jig (a dotted beat at 65 to 77), not a dance's; the singer sets its pace.
