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

(**Revised the same evening, after the artist listened**: the shape-note syllables are gone from the a
cappella, and the session is now **the jig**, always in six-eight, with no reel and no tradition's names.
See "A cappella and the jig, revised" at the end; this section is kept as it was built.)

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

# House and dub (2026-09-30)

The artist: "a real dance style, and dub." The two studio tests that made EDM through the page
(docs/STUDIO-EDM-TEST.md) ended the same way: "still a folk band in synths: no dance style, no clap
on two and four, no ride, no off-beat bass, no filter automation." And dub, because Jamaican version
culture is this song's own idea: the B-side that re-cuts the same song, the dub plate, the riddim
sung over again by the next singer. A version is a song passed on and remade.

## The design

### Where they sit: beside the ring, not on it

Every existing machine's home is an angle on the ring divided by the ring's length, so putting two
more styles on it would move every machine's home and change which style a child of any parent is
played in: lineages already made (the piece was submitted on 28 September) would wander differently.
So house and dub are **off the ring**: a person chooses them (`--style house`, the studio's style
list), or a parent played in one hands it down. Each has an **anchor** on the ring, the style it sits
beside (`OFF_RING`: house by synth folk, dub by lo-fi). A child of a house or dub parent is placed as
if its parent were at the anchor: where it would stay, it keeps its parent's style; where the drift
takes it a step, it steps to the anchor's neighbour (house to lo-fi or indie, dub to ambient or synth
folk), the rule a cappella and the session keep too (above, "Two more": `OFF_RING` is shared, and on
merging this was made one rule). So a lineage can leave, never wander in by itself. Where they would go on the ring (house between synth
folk and indie, dub between ambient and lo-fi) is a decision for the artist, below.

### House (about 124 bpm)

| | |
|---|---|
| lineup | drum machine (a **909**, the style's own kit), synth bass, piano stabs (an **organ** for about three machines in ten: the style swaps it in, as the shanty's accordion), synth pad, the arpeggio as a **pluck** |
| feel, tempo | straight; 1.22 to 1.33 of the song's (H: 117 to 128, centre 124) |
| harmony | added ninths, sixths, a seventh on V and vi, a suspension (0.6): the house piano's colours |
| leads | the piano (the tune in the intro, the break and the outro), then the pluck |

The patterns (new idioms in songbird/idioms.py):

- **drum machine**: `floor` (the kick on every beat, an open hat on every off-beat, a soft closed
  hat on the sixteenths between: the verse groove), `house` (floor and a clap on two and four, the
  closed hats a little firmer: the refrain), `drop` (house and the ride on every beat, a crash on the
  first one: the drop). Intro and outro `floor`, the first verse `floor`, later verses `floor` or
  `house` as the band fills, refrains `house`, the drop `drop`, the tag `end`. A fill into a bigger
  section is the groove's own (`w_groove`), a clap and snare roll into the drop is the transition's.
- **synth bass**: `offbeat` (the root on every off-beat, short; an octave up on the last off-beat of a
  bar now and then, a step into a new chord), `rolling` (three sixteenths after each kick, the root,
  the root, the octave or the fifth: the drop's).
- **piano / organ**: `stab` (the chord, its colour, short, on the off-beats of a bar, or a 3-3-2
  across it; which, bar by bar, from the part's own stream; above the bass and under the tune as
  comping is). The organ plays it on its percussive registration.
- **pad**: held chords (`pad`), pumping.
- **pluck** (the arpeggio's own pluck patch): `pluck`, a one-bar figure of chord tones on the
  sixteenths' off-beats above the tune, in the refrains.

Its **program sound** (a style's own sound design, under a person's, `StyleDef.sound`): the drum
machine on its 909 kit; a sidechain on the pad (classic, 8 dB), the synth bass, the stabs and the
pluck (subtle, 4 dB), all keyed on the kick; so where the kick drops out, nothing pumps. A person's
`sound.*` and `mix.<player>.*` edits sit over it path by path, and `/api/sound` shows it as the
program's.

Its **habits**, drawn by chance per machine and season as every style's options are:

- **a breakdown and a drop** (`Style.drop`, new: which refrain the breakdown follows, 0 none; house
  draws it 0.8 of the time): after the second refrain (the first where the song has two), every
  section before the next refrain is the breakdown: the drums, the bass, the stabs and the pluck drop
  out, the singer (and in H's bridge the lineage) is left with the pad; over the breakdown the band's
  **low-pass opens** from 350 Hz to wide open (a new sweep, `open`, spanning the breakdown), a
  **riser** over its last two bars and a **snare and clap roll** over its last one or two (two when
  the breakdown is eight bars or more), and the refrain after it is **the drop**: the parts' `drop`
  key (the ride), everyone at full weight, a crash on the one. Any style can take it (`--arrange
  drop=2`, the studio's style options); only house draws it.
- **the filtered intro**: where the form has an intro, the band's low-pass opens across it (the same
  `open` sweep) into the first verse: kick, pad and the piano on the tune, dark, then bright.
- a **lift** now and then (0.15), **entrances** (the band joining line by line: house builds in
  layers, 0.5), endings cold, the last line again, or ringing; backing voices echoing the lines' ends
  or oohs (the house vocal's answers).

The singer is kept: a house vocal, a little less vibrato, a plate. Mix: a little drier room, wider,
the plate up.

### Dub (about 75 bpm)

| | |
|---|---|
| lineup | the kit, an electric bass, an electric guitar (the skank), the organ (the bubble), a **melodica** (new) |
| feel, tempo | swung (0.65) or straight; 0.72 to 0.86 of the song's (H: 69 to 83, centre 75). A 140 half-time is the same pulse at 70: the singer's quarter is the tempo, so 70 to 80 is the one groove |
| harmony | triads, a minor seventh on vi and ii (0.2): roots reggae keeps its chords plain |
| leads | the melodica (the tune in the intro and the breaks, answers between the lines), then the organ |

The patterns:

- **kit**: `onedrop` (nothing on the one; the kick and a cross-stick together on three; the closed
  hat on the eighths, an open hat on the last off-beat of a bar now and then), `steppers` (the kick on
  every beat, a rim shot on three: the last refrain's drive). A fill of a few rim shots and toms into
  a bigger section, the groove's own.
- **bass**: `dubbass`, the riddim: the root long on the one, a chord tone on the off-beat of two,
  nothing on three (the drop is the drums'), the octave or fifth on its off-beat and a step into the
  next chord on four; low (it sits an octave under the guitar's bass), round, with space.
- **guitar**: `skank`, a three-note chord on the top strings, struck and choked at once on every
  off-beat (the "and"s), up strokes; the electric's `mute` for the choke's damping.
- **organ**: `bubble`, the organ shuffle: per beat the chord low on its second sixteenth, high on the
  off-beat (with the skank), low again on its last sixteenth, soft and short.
- **melodica**: `fills` (the answers between lines the band's fills give every style) and the tune
  where nobody sings.

The **melodica** is a new instrument (songbird/synth/melodica.py): free reeds blown through a tube,
one reed a key (no bends, chromatic, chords possible), the reed tables and read kernel the harmonica
already uses (reed.tables, reed._read_mix: no new kernel), a plastic case's hollow body, breath noise
strongest as each note is tongued; placed and levelled as a lead, held to the instrument contract
(tests/test_instrument_specs.py).

The **mixing desk as an instrument** (the style's `desk`, new; the choices drawn from each part's own
random stream, so a render replays exactly):

- **drop-outs** (the dub): bar by bar, in the sections the desk works (the intro, the turns, the
  break, the version most; a verse or a refrain now and then, never its first bar), the band cut to
  the drums and bass alone, the bass out (the drums alone), or the drums out for a bar, and back;
- **echo throws**: a tape echo (a delay of a dotted eighth, its repeats fed back at 0.6, each repeat
  darker and a little saturated, as a Roland Space Echo's tape and heads do) that the engineer sends
  a moment to: the **singer's line ends** (the last word of about a third of the lines, more in the
  refrains), a **cross-stick or snare** hit before a drop-out or a section's end, the **skank's** last
  chop before the band drops out; the repeats land in the gap after the line, at the delay's time;
- **spring splashes**: a hit on the snare (every eight bars or so, and at the version's start) sent
  hard into a spring tank (amp.spring_ir: the same springs the electric's amp has), its crash and
  boing on the return;
- **the version** (`ending: version`, new; dub draws it 0.65 of the time): after the last line, the
  band plays the last refrain's chords again, eight bars, with nobody singing: the singer's last line
  thrown into the echo as it ends, the riddim (drums and bass) steady, the skank, the bubble and the
  melodica's fragments of the tune dropping in and out, a splash at its start, and the song ends on
  the echo's tail. A discomix: the vocal, then its dub. It's an ending any style can take.

Throws and splashes are made in the mix (songbird/synth/dub.py, numpy and scipy only: the echo's
feedback a delay's length at a time, the spring by oa.convolve; no new kernel), each over its window
and its tail only, from the score's `sound["throws"]` (the arranger's choices, in seconds), added to
the band's bus and its send to the room. Dub's mix otherwise: a little tape wear, a darker top, more
room, and the plate.

### What a style may now bring (both new, both empty for the thirteen)

- `StyleDef.sound`: the style's own sound design ({"players": {player: {kit, patch, sidechain...}}}),
  merged under a person's by songbird/sound.py (`program_sound`), so with none (every other style)
  `produce()` returns what it was given, exactly as before.
- `StyleDef.desk`: the dub desk's habits (drop-out, throw and splash rates by section, the echo's
  time and feedback); empty: no drop-outs, no throws.
- `Style.drop` (an int) and the ending `version`. Records keep `drop` out while it is 0, so a record's
  digest (and the seed its child draws) is as it was.
- the sweep type `open` (a low-pass rising, 350 Hz to 16 kHz), also for a person's transitions.
- new idioms: floor, house, drop, offbeat, rolling, stab, pluck (house); onedrop, steppers, dubbass,
  skank, bubble (dub); each with its page label, so the arrangement grid offers them to those players
  in every style (they're the vocabulary of that player, as every idiom is).

### The page, and the words

The style list offers both (explain.STYLE_NAMES, beside the ring's); the arrangement grid gives each
player its patterns; the section's options show the drop (on the breakdown's first section) and the
version (in the style card's endings); the sound inspector shows the house's 909 and pumps as the
program's; a cell sitting out the breakdown says why ("the breakdown before the drop: the drums and
bass drop out and the singer is left with the pad"). explain's words for the style card: "a breakdown
after the second refrain, and the drop", "the band plays a dub version after the song".

### Byte for byte

The thirteen styles' renders are unchanged: none draws `drop` or `version`, none has a sound or a
desk, the new idioms are only called where a table names them, and `choose_options` draws from coins
of their own names (a new coin never moves an old one). The goldens (tests/golden/*.sha256, the seed
scores) hold; a few renders in other styles are checked against the tree before by their PCM ids.
`--replay` renders a house or dub record exactly (every choice is in its params, every random one
from the render's seed).

### Memory

Each style's default measured with tools/render_memory.py (H, two threads); the melodica's rate by
tools/part_memory.py into songbird/public.py's RATES. The echo holds only a throw's window and its
tail (a few seconds), the spring the same; the version adds eight bars (about 25 s of song at 75).

### Decisions for the artist

1. **Off the ring**: chosen, or inherited; a lineage steps off them onto the ring, never onto them.
   Putting them on the ring (house between synth folk and indie, dub between ambient and lo-fi)
   would let machines wander into them, and move every lineage's future.
2. **House's drop is after the second refrain**, a breakdown with the singer and the pad alone, and
   the filter opening across it; a riser and a roll into it.
3. **The version** is eight bars after the song, the last refrain's chords; it could be sixteen, or a
   version of the verse.
4. **The melodica** is new; the whistle could have taken the answers.

## What the review changed

A read-only Fable review of the design above, before it was built. Its points, and what was done:

1. **The version would have dragged under the ritardando** (the slowing runs from the last line's first bar to
   the song's end, which the version's bars join). A version holds its tempo and slows through its last two bars
   only (`style.slowing`); the last line isn't slowed at all.
2. **The version is a section of its own** (role "version"), not the last section stretched as the amen is: a
   tag's winding-down parts would have played it, and a version counted as a refrain would have taken the "last"
   parts and the lift from the sung refrain. It is left out of the band's sections the mix pairs with the score's
   (the singer's arc), and out of the arrangement grid; a key lift still carries it.
3. **`drop` in every record would have moved every child's seed** (`Style.to_dict` is every field, and a child's
   seed hashes its parent's record): it is left out while 0 (`QUIET_OFF`), held to 0..8, and `version` and
   `drop` are among a person's style options.
4. **The ring is indexed by name in three places and pinned by a test**: `place()` and `neighbours()` find an
   off-ring style's anchor first; the page's style list is built from every style (the ring's, then house and
   dub), and the style card says where one sits; the palette's test is the ring and the styles beside it.
5. **A person couldn't take the style's sound away**: a pump's preset **off**, and **false** at a boundary for
   none of the style's transitions there; `/api/sound` and the record's "was" read the style's as the program's.
6. **The style's transitions stay out of the person's table** (a breakdown's sweep is ten bars, which a person's
   can't be): they are made in the score, under the person's, and the opening filter is a third sweep kind.
7. **A drop needs a refrain after it**, and the old breakdown (the last refrain stripped to the rhythm) would
   contradict it: house draws that one never, and the page words them apart ("the breakdown before the drop").
8. **The grid checked**: kicks on the beats, claps on two and four, bass and skank on the odd eighths, the one
   drop's kick on three, the bubble on the sixteenths. With dub's swing the bubble and the skank shuffle (the
   off-beats land late, as the clock swings them): as reggae's do. House's soft hats are set over the velocity
   below which a sparse band thins them, so the machine keeps its pattern.
9. **Drop-outs belong to the score** (the notes left out, bar by bar), so the stems, the piano score, the browser
   and a replay all agree: as designed; only the echo and the spring are the mix's.
10. **No song-long throw bus**: each throw's return is added where it lands, window and tail only; and a version's
    last chord rings six seconds, not three, so its last echoes aren't cut.
11. **Each throw names its part**, cut from that part's channel while the mix has it in hand (the singer's from its
    bus, before the record's sum).
12. **The melodica as a harmonica patch** was weighed: the harmonica's player is a Richter harp's (holes, bends,
    a harp's key chosen per part); a melodica shares only its reeds, so it is a small module of its own on the
    harmonica's pieces (reed tables and their read kernel), with no new kernel.

Two more came from measuring what was built: a style may set the odds of its half-time bridge (house and dub never:
a half-time one drop is a crawl), and the desk's returns were set by mixing a render's stems with its throws and
without (below). And one from reading a render's arrangement: where a breakdown holds a section nobody sings (a turn,
a break), the lead plays the tune there over the pad (a piano breakdown), not eight bars of the pad alone.

## As built

| Where | What |
|---|---|
| songbird/style.py | `HOUSE`, `DUB`, `DESK`, `OFF_RING` in a block of their own; `Style.drop`, the ending `version`, `StyleDef.sound` and `.desk`; `coda`, `slowing` and `ring` for a version; `desk_of`, `on_ring`; `place` and `neighbours` by the anchor; a style's odds of a half-time bridge (`options["half"]`) |
| songbird/idioms.py | the patterns (floor, house, drop, offbeat, rolling, stab, pluck; onedrop, steppers, dubbass, skank, bubble), in a block of their own; `mark_drop`, `add_version`, `dubbed` (the desk); the drop in `plan_style` and `shape_plan`; a version's chords in `chord_times` |
| songbird/sound.py | a style's sound under a person's (`program_players`, `merged_players`), its transitions (`style_transitions`), the desk's throws for the mix (`thrown`); the pump preset off, a boundary false |
| songbird/synth/sweeps.py, dub.py, mixing.py | the opening sweep; the tape echo and the spring; each throw cut from its part (`Design.throw`) |
| songbird/synth/melodica.py | the melodica (built by a helper agent to the instrument contract, on the harmonica's pieces) |
| songbird/takeover.py, explain.py, edits.py, cli.py, public.py | the grid's patterns and words, the drop's option and reasons; the style list, the drop and the version in words; `style.drop` and `ending: version` as a person's; the melodica's memory rate |
| tests/test_house_dub.py | where every part lands, the program's sound and a person's over it, the drop, the version and its throws, the echo and the spring, the opening filter, the record, the anchor, the studio's page |

No new numba kernel: the echo is scipy's filters a repeat at a time, the spring the electric's own
(amp.spring_ir, oa.convolve), the melodica the harmonica's reed tables and their read kernel. The browser's
kernels are as they were (tests/test_browser_kernels.py).

## Measured (2026-09-30)

Renders for listening, in `renders/styles/` of the main checkout (gitignored), H as made-up machines sing it:

| render | tempo | what chance drew | length | id |
|---|---|---|---|---|
| house-ada-2026-09-30 | 124.6 | the tune on the piano to begin, the filter opening; a drop after the second refrain (the breakdown a turn and a verse); the last line again | 167.8 s | f1326f4d51db |
| house-juno-2026-10-15 | 122.5 | a pad swelling in alone, filtered; a drop after the second refrain (the breakdown a turn, the break and the bridge, 35 s: the pluck on the tune in the break); a cold stop | 133.2 s | 9b4aecbd376e |
| house-otto-2026-09-30 | 118.0 | a short shape (two verses, an outro), no drop; a cold stop | 117.9 s | 32f101111ad7 |
| dub-juno-2026-09-30 | 75.1 | the band joining line by line; the last refrain starting on the riddim alone; the version | 245.8 s | fb893109e68e |
| dub-vela-2026-09-30 | 82.6 | a count-in on the rim; the voices echoing the lines' ends; the version | 244.4 s | f968e42743a3 |
| dub-ada-2026-09-30 | 75.4 | three verses, the bridge twice; a cold stop, no version | 265.4 s | fb6e426a1234 |

What they play (the stems, dry, and the scores):

- **House**: a kick on every beat of every refrain (132 of 132, 93 of 93: the kick's band jumps 9 dB within 80 ms
  of the beat), of every verse but the breakdown's, of the intro unless a pad begins it alone; the open hat on 129 of
  136 off-beats of ada's refrains (otto: 94 of 96); claps on two and four only (50 and 50); the ride only in the
  drop (32 strokes, eight bars); the synth bass starting a note on every off-beat of the refrains (104 of 104) and on
  no beat (0 of 101). The breakdown: the drum machine, the bass and the pluck silent (under -125 dB) until the roll,
  the pad at -37 dB, the piano on the turn's quote; the mix's spectral centroid rising through it as the filter
  opens, 446 Hz, 1.4 kHz, 1.5 kHz, 6.4 kHz (juno's 35 s one: 415 Hz to 5.0 kHz). The pumps: 1152 triggers on the
  kicks for the pad, bass, stabs and pluck (none in the breakdown: no kick).
- **Dub**: the kick only on three (the score: 47 of 48 bars of ada's verses and refrains, the other dropped out by the
  desk, with the cross-stick on every one; nothing on the one); the skank struck on the (swung) off-beats, never on a
  beat (173 of 192 off-beats, 0 of 186 beats: the rest dropped out; vela's 192 of 192); the bass starting a note on the
  one (40 of 42) and the fourth beat (37 of 48), never on two or three. The desk: 17 to 26 throws a song (a third of
  the voice's line ends, the skank or the drums before a drop-out), 5 to 14 splashes. Mixed with and without them,
  the difference (the returns) has its first repeat at the echo's time (a dotted eighth: 0.60 s at 75, 0.54 at 82.6),
  a median 9 to 11 dB under the mix around it (one skank in vela's version 9 dB over it, the band dropped out), each
  next repeat 4.5 dB under the last (feedback 0.6), 14 to 34 dB of quiet between the repeats of a short throw; a
  splash 11 to 39 dB under the mix over the second after. The version: eight bars after the last line (juno: 211.9 to
  238.0 s), the riddim with the skank, the bubble and the melodica dropping in and out, the last line thrown into it.
- **The voice over the band** (tools/stylemeter.py, ada, 2026-09-27, a verse and a refrain, three voices): house 7.7
  to 10.9 dB, Whisper mishearing 21.5% of the words (synth folk on the same meter: 30%); dub 7.5 to 10.0 dB, 7.1%;
  true peaks -1.9 dBTP; nothing on a sung pitch.
- **Memory** (tools/render_memory.py, two threads, `MallocLargeCache=0`, the style chosen with no machine): house,
  118.4 s, 0.97 GB (estimated 1.10); dub with its version, 221.0 s, 1.89 GB (estimated 2.02). In the VPS's 2100 MB a
  house song fits up to 4.5 minutes, a dub one 3.9: H's own shape in dub with its version (3.7 minutes) fits; a
  machine's longer shape (three verses, the bridge twice: ada's, 4.4 to 5 minutes) is refused on the server as
  gospel's long ones are ("shorten it").
- **Nothing else moved**: nine renders in six styles and the seed (lo-fi, synth folk, indie, gospel, the string
  band, chamber for ada; juno's own style; lo-fi for vela; H's seed) render to the ids they did before; the goldens
  hold; `--replay` of a house and a dub record renders them to the same ids. Merged with main's a cappella and
  session: seven renders (lo-fi, synth folk, gospel, a cappella and the session for ada, juno's own, the seed)
  render to main's ids, the house and dub renders above replay to theirs ("replay: matches"), and the suite passes
  (1697).

## Decisions for the artist (as built)

1. **Off the ring** (above): chosen, or handed down; a lineage steps off to the anchor's neighbour. Putting them on the ring
   would move every lineage's future.
2. **House's drop after the second refrain**, drawn 0.8 of the time; its breakdown is every section before the next
   refrain, which in a machine's shape can be long (juno's: 35 s). A cap (the breakdown's last eight bars only) is a
   line in `mark_drop`.
3. **The version** (0.65 of dub's renditions) is eight bars; sixteen would be `VERSION_BARS`. It makes dub the
   longest style but one (a whole song at 75 with its version is 3.7 to 5 minutes).
4. **The desk's loudness**: the returns' levels (`DESK`: level 2, the singer's 0.5, the spring 3) were set by
   measurement, not by ear; a louder desk is one number.
5. **The melodica** is new, not the whistle.
6. **The drop and the version are any style's** (`--arrange drop=2`, `ending=version`, and the studio's options):
   only house and dub draw them.
7. **A preview** (a section heard alone) keeps the throws whose windows it plays; one that begins inside an echo's
   tail doesn't hear the tail.

# A cappella and the jig, revised (2026-09-30, evening)

The artist listened to the renders of "Two more": "A cappella is just okay. fa, sol, la, mi sounds seem a bit like
gibberish." And: "Celtic sounds better to me, but maybe we just call it jig? Open to ideas, just don't want to claim
any false authenticity." The page says the simplest thing that's true; details go in its tooltips and here.

## A cappella: the words, not the notes

**What went.** The shape-note syllables, everywhere: `SHAPE_SYLLABLES`, the readings they pinned ("fa" F AA1, "sol"
S OW1 L: nothing else used them), `shape_note`, the "notes" intro. A record or a draft whose intro is "notes" is read
as "lead" (`style.RENAMED`).

**How it sings now**, section by section:

- *Where a band would play the tune* (an intro, a break, an outro): the lead hums it on "oo" and the group hums the
  chords under it (the under voice and the alto, each chord's root and fifth; the treble rests, so the tune stays the
  top line and the treble's entrance at the refrain is heard). Or, a third of the time (`intro=pad`), the group's
  chords swell in alone on "oo" and the lead comes in with the words.
- *The first verse*: often the lead alone (lined out), as before.
- *The verses*: the lead with the group humming (`hum`), on "oo"s (`oohs`), or answering the line ends
  (`echo`), which is now the group **joining the lead on each line's last word, in parts**. The old echo sang the
  word again after the line, and in H there is room for that once or twice a verse: ada's, bob's and dmitri's
  verses (all three drew `echo`) were the lead alone.
- *The refrains*: everyone on the words, homophonic, the parts' own notes on each syllable (as built); the last
  refrain everyone.
- *A turn*: its chords held by everyone on "oo". As built, a turn with the next verse's pickup in it was silent
  (in ada's, five seconds of nothing, twice).
- *The bridge and the tag*: the lineage's harmony, with the program's voices under it (as built).
- A held chord is never in unison with a note of the tune it sits under.

**What stays**: the group (three voices at least), the parts (treble, under voice, alto; open, a third about a
third of the time), the matching of singers to parts, the feet and hands by chance, the room. **No true bass**: the
learned throat still thins below E3, and nothing here changes that; a bass waits for a throat that sings there.

**Measured** (ada, 2026-09-27, the whole song with its stems; pYIN over each note's middle): every part in tune,
the median within 0.1 cent, 98% (the lead) to 99% (the three parts) of notes within 25 cents. Where the parts sing
with the lead: fifths 20%, fourths 16%, octaves 14% (open: 50%), thirds 27% (minor 16, major 11), sixths 12%,
seconds and sevenths 10%: as built (48% and 29%). **Words misheard** (Whisper base.en on the mix, a verse that
isn't bare and a refrain, four machines: ada, bob, coral, dmitri on their dates): the verse hummed 14.2% (41 of
289 words), the line ends joined 17.3% (50 of 289), the ballad in the same run 10.7% (30 of 280). The joined
last words cost a little: their consonants arrive from four voices a hair apart. **Memory** (tools/render_memory.py,
two threads, `MallocLargeCache=0`): with no machine, a waltz, three voices of its own, 225 s, 1.54 GB (the studio's
estimate 1.65); six lineage voices, 1.53 GB; four verses, every part, six voices, tempo 55, 450 s, 2.56 GB
(estimated 3.00). In the studio's 2100 MB, about five minutes of an a cappella in one go, as before.

**The feet clicked** (the artist heard "some clicking/clipping in the bass drums" in coral's five voices; the mix
never clipped, peak 0.886). Each stomp's sole slap was noise at full strength from its first sample, through 700 Hz
to 5 kHz: a step, heard as a click in every stomp (above 6 kHz, 51 spikes over 12 times the mix's 46 ms RMS, each
within 60 ms of a stomp). Now the slap rises over 1.5 to 4 ms (a hard heel brought down hard to a soft sole,
gently) through 400 Hz to 2.5 kHz and a 3 kHz low-pass, at the same level (`hand._slap`): in the stem, the energy
above 6 kHz is 18 dB down a stomp (its peak 21), the energy under 200 Hz the same (+0.1%); in the mix, no spikes
(the loudest by a stomp 10.9 times the RMS, the median 3.8, was 13.0). Only the stomps change, wherever they
play (the a cappella, the shanty, the blues); every other part is sample for sample as it was.

## The jig

**The name.** The style's id and name are **jig** (the page: "jig, in six-eight"). It was `celtic`, "a Celtic
session". Everywhere a name is read, "celtic" is read as "jig" (`style.RENAMED`: a record's name and lineage, a
person's edits and drafts, `--style celtic`; the takeover's old names for the drum's patterns, `bodhran` and
`bodhran-light`, are `tipped` and `tipped-light`), so yesterday's renders and records load.

**Always a jig.** Six-eight, the song re-barred (H's long-short-short feet are a jig's dotted beat), at 1.35 to
1.6 of the song's tempo (a dotted beat at 65 to 77). The reel and its double time are gone: a jig-named style
can't honestly carry one. A song that can't be re-barred keeps its beats and plays each in three: its own time
where it is already in six-eight (b, l), twelve-eight otherwise (a, c, f: a dotted beat at 0.75 of the song's
tempo); `feels_for` says so for a style whose only feel is six-eight, and no other style has one.

**The words on the page** claim no tradition: the frame drum is a frame drum, played with a tipper (no bodhrán),
the drone a reed drone (no pipes), the guitar an open-tuned guitar (DADGAD is in the style's detail and here, as a
tuning), the slow air "the tune slow and free to begin, the lead alone", the singer's own ornaments "turns" (no
sean-nós), and no "session": the whistle and the fiddle play the tune round twice. The code's comments say the same.

**What it plays**, as built but for the reel: the whistle and the fiddle (and a concertina, 0.45) on the tune
together where nobody sings, round twice, the lead and the guitar the first time and everyone the second; the drum
tipped, down-up-down on each dotted beat, the bar's first stroke open (in twelve-eight or a song's own six-eight,
the same on each of its beats); the guitar's DADGAD strum down-down-up; a reed drone (0.35); the slow air (0.25 of
intros). The reel's sixteenth strokes and its back-hand-high stroke ("top") went with it; the drum model keeps the
stroke's one row of data, unused (no kernel changed).

**Measured** from the four renders' scores: tempo 137 to 150 (a dotted beat at 69 to 75); the drum's strokes a
median 1.01 to 1.02 eighths apart, about a fifth of them open; the whistle cuts 12 to 26 of its notes, the fiddle 5 to 18;
the singer's own turns on 6 to 15 notes of 250 to 387. **Words misheard**: 21.1% (59 of 280, the same four
machines) beside the ballad's 10.7%: a jig sings the song half as fast again (as built: 17.1% in one run). **Memory**:
H's jig with no machine, 112 s, 0.99 GB (estimated 1.12); four verses, every part, tempo 130, 213 s, 1.56 GB
(estimated 1.86).

## Byte for byte, and yesterday's records

Every other style is as it was: the scores of the seed, four machines' own choices (ada, bob, coral, dmitri on
their dates) and every other style for each (with three voices for ada), 80 in all, are identical before and after
both changes; five renders made on main before them (the seed; gospel, lo-fi and synth folk for ada; indie for
vela) replay to their ids ("replay: matches"); the goldens pass.

**The two styles' own renders from before this change now render differently**, as expected: they were a day old
and unreleased. Their records still load (the eight in renders/styles, acappella-* and celtic-*): an a cappella's
intro "notes" is read as "lead", a Celtic one's name and lineage as "jig"; a record made as a reel keeps its
recorded feel (double time) when replayed, under the jig's name, its drum on the triplet strokes. `--replay` of any
of them says "differs".

## Renders for the artist

In renders/styles/ (ids in ids-acappella2-jig.txt), the same machines and dates as before, each as its machine
chooses unless named:

- acappella2-ada-2026-09-27 (228 s): the tune hummed over the group to begin, verse 1 lined out, the line ends
  joined, the voices coming in a line apart, the last line again. Id ef4e10a46970.
- acappella2-bob-2026-03-14 (142 s): the same way, a shorter shape with an outro hummed. Id 9722a2cbfa3a.
- acappella2-coral-2026-11-02-five-voices-pad-hum (222 s): five lineage voices, `--arrange intro=pad backing=hum`:
  the chords swelling in alone, the verses hummed, the lineage's own harmony in the bridges and the tag.
  Id 7ca8f0e8ad80.
- acappella3-coral-2026-11-02-five-voices-pad-hum (222 s): the same, its feet without the click. Id e72e88900ff6.
- acappella2-dmitri-2026-06-21 (208 s): dmitri's own choice, the verses on "oo"s. Id ae4508d32a26.
- jig-ada-2026-09-27 (166 s, 143.5): a slow air to begin. Id 604f8504cc67.
- jig-bob-2026-03-14 (108 s, 150.4): a slow air, harmony in thirds from the one lineage voice. Id 9922285407fe.
- jig-coral-2026-11-02-slow-air (156 s, 137.2): `--arrange intro=air` (its own choice too). Id 66c9026b5950.
- jig-dmitri-2026-06-21 (154 s, 143.5): the tune played to begin, the concertina with the whistle and the fiddle
  (dmitri's was the reel). Id 2d0736279ef7.

## Left open

- **The answered line ends** cost about three words in a hundred against a hummed verse. If the artist hears it
  too, the join can be the last syllable only, or the answer after the line where there is room (as before).
- **The jig's words**: a fifth of them misheard, twice the ballad's, from the pace. Its tempo floor (1.35 of the
  song's) is one number; lower is a slower jig.
- **The slow air**: three of the four machines drew it (0.25 of intros; the draws moved with the name, which is
  part of every choice's material). Nothing to change, but the renders show it more than it will be.

# House and dub, again: reinterpretations, not a folk band in new clothes (2026-09-30, evening)

**Hidden for now (2026-09-30, night).** The artist listened: "they haven't convinced me like the others yet".
Neither is offered in the studio's style picker (`style.HIDDEN`, `style.offered`); a record, a draft or
`--style` still plays them, and a version already in one still shows its own name. The code stays. House was
offered again the same night, once its hook was fixed (below): "I like it now!" Dub stays hidden.

The artist, on the renders above: "House is a fun reinterpretation but I don't know if it's really that
recognizable." "Dub has some cool elements but doesn't seem like enough of a transformation." Both styles kept
the folk song's form, its harmony and its phrasing, and changed only the band. A genre lives as much in its
harmony, its form and what it does with a voice: house is a loop, a groove that builds and drops, and a hook
chopped out of a vocal; dub is a version, the song taken apart on the desk. This is the design for making both
real reinterpretations while the song stays recognizable (its hook, its tune in pieces, its words where sung).
Both are a day old and unreleased: house's and dub's records made before this still load, and may render
differently (said below, with the ids).

## The design

### What a style may now bring (both new, both empty for every other style)

- `StyleDef.loops`: chord loops of the style's own, by name, each a list of scale degrees a bar (`(6, 4)`: vi,
  then IV, round again), with whether they are voiced as sevenths. The chords are the mode's own on those degrees
  (vi in a major key is a minor chord, in aeolian the major VI), their added tone the mode's seventh; so a loop
  follows the key and the mode as the song's own chords do. Which sections take the loop is the style's (house:
  every section but the bridge; dub: the version).
- `Style.loop`: the rendition's loop (a name of the style's, "song" for the song's own chords, "" for the style's
  default: the best-fitting loop for the key and mode). Left out of a record while "", as `drop` is.
- `StyleDef.form`: the style's own section lengths and the bars it plays after a sung section (house's 16-bar
  intro and outro, its four-bar turns, eight bars of the hook after the drop's refrain and the last), laid out by
  `takeover.phrase_plan` as a session's rounds are: the style's own length, a person's `arrange.*.bars` over it.
- `StyleDef.hook`: a vocal chop (house): which words of the song, the rhythms it may take, where it sings.
- `Style.dissolve` (dub): the refrain after which the song dissolves into its version; 0 none. Left out while 0.
- the desk's new habits (dub): fragments' echoes with a longer feedback, the whole band's filter swept, the
  spring kicked more often, in the dissolved sections.

A plain `Style()` and every one of the thirteen, the a cappella and the session have none of them: nothing moves
(the goldens; a few renders' PCM ids against the tree before).

### The loop, and fitting it to the tune

A loop is chosen per rendition from the style's, by how it sits under the tune in the rendition's key and mode:
each candidate is laid under every sung line of the verse and the refrain (the loop restarts with each section,
so a line of two bars sits on the loop's first or second half), and each sung note that is not a tone of its
chord and is a semitone from one (a minor second, or a major seventh) counts its length, a long or strong note
(a beat or more, or on a foot) fully and a passing one a third. The song's own chords score about 0.75 beats
of the 101 H sings in a verse and a refrain (ionian and mixolydian), 4 in aeolian. A loop fits if it scores no
more than the song's own chords do and two beats more; the rendition draws one of the fitting loops (a coin of
its own, as every style option is), and where none fits (aeolian), takes the closest. So the loop is chosen per
key to fit, and the band's own rules deal with what rubs (the comping holds a chord tone through a sung note that
isn't one of its tones; a colour steps aside where it would rub).

What H gives (clashing beats of 101, triads; degrees, sevenths as the mode has them):

| loop | chords (D major) | ionian | mixolydian | aeolian |
|---|---|---|---|---|
| vamp: vi7, IVmaj7 | Bm7, Gmaj7 | 0.4 | 0.4 | 9.5 |
| lift: IVmaj7, Imaj7 | Gmaj7, Dmaj7 | 0.0 | 0.0 | 29.3 |
| home: Imaj7, IVmaj7 | Dmaj7, Gmaj7 | 0.4 | 0.4 | 16.5 |
| deep: ii7, V7, Imaj7, vi7 | Em7, A7, Dmaj7, Bm7 | 2.6 | 4.4 | 27.4 |
| royal: IVmaj7, V7, iii7, vi7 | Gmaj7, A7, F♯m7, Bm7 | 2.7 | 5.4 | 24.7 |
| pop: vi7, IVmaj7, I, V | Bm7, Gmaj7, D, A | 8.6 | 0.6 | 9.2 |
| minor: VII, iv7, i7, v7 | (aeolian: C, Gm7, Dm7, Am7) | | | 6.4 |

So in D major house plays one of vamp, lift and home (Bm7 to Gmaj7 is the deep-house two-chord vamp), in
mixolydian also pop, in aeolian the minor loop. A loop's seventh is its colour: the chord's own (the MIDI file
names Bm7, Gmaj7), but where a sung note is a semitone from it the players leave it out there, as they do a
style's colour (so a maj7's C♯ never grinds against a sung D). A person's chords for a line or a place win over
the loop there; `style.loop` chooses another, or the song's own.

### House (122 to 126)

- **Harmony**: the loop under everything but the bridge (the breakdown's heart keeps the song's own chords: the
  folk harmony comes back in the breakdown, and the drop slams back into the loop).
- **Form** (the style's lengths, a person's over them): a **16-bar intro** (the kick and hats alone for four bars,
  the bass in at five, the pad and the stabs at nine, and at thirteen the piano's tune, or the chop where the
  intro is the pad's; the band's filter opening across all sixteen), the verses and refrains as the song has
  them, every **turn four bars of the hook** (the chop over the full groove, the lead's quote left out), the
  **drop's refrain** followed by **eight bars of the hook**, the **last refrain** too (so every house version ends
  on the hook), and a **16-bar outro** where the form has one (the hook over the groove for eight bars, then the
  band leaving layer by layer, the drums alone last). The break stays the piano's (or organ's) solo on the verse
  tune: the tune's plainest statement, over the loop.
- **The vocal hook**: the singer sings a chop, a short phrase of the song's own words on the grid: the first
  refrain's first line's last words ("No-bo-dy knows", on its own notes la so mi so) and, in the last hook, the
  last refrain's last words ("now it's by you"). Short and staccato (each syllable a sixteenth or an eighth, the
  last held a beat), on a two-bar rhythm drawn per rendition from a few (the call on the beat, one on the
  off-beats, a stutter "no, no, no-bo-dy knows"), over and over. In a breakdown's turn it sings once in two bars,
  soft. The singer's own voice, not a sample: the program sings it (voice notes in the score, so the stems, the
  MIDI file, a preview and a replay all have it). Not pitched up: an octave up is past what the throat sings
  (it is measured to B4; la is B4 already); the chop's pitch is the tune's.
- **The bassline as a riff**: the off-beat bass in the verses, an **octave** riff in the refrains and the hook
  bars (the root on the beat's second sixteenth and its octave on the off-beat, eighths, the disco-house octave
  bass: new idiom `octave`), the rolling sixteenths in the drop. The stabs voice the loop's sevenths.
- **Tempo**: 1.27 to 1.31 of the song's (122 to 126 for H), centre 124.
- **The breakdown, build and drop**: as built (after the second refrain, the pad and the singer, the filter
  opening, a riser and the snare roll), and now the drop is the refrain over the loop with the ride, the singer
  on the hook line, then the chop's eight bars. The breakdown holds the song's own harmony (the bridge) and the
  hook turn before it softly.
- Endings: cold or ringing on the last chop (repeating the last line is left out: the hook is the tag).

### Dub (70 to 78)

- **The version is the song's second half**: `Style.dissolve` (drawn 0.9 of the time) is the refrain after which the
  song dissolves: half the refrains, at least the first (H's three refrains: after the first; four: after the
  second). Up to there the song is sung straight, over the song's own chords, with the desk working as before.
  After it every section is the version:
  - the **riddim**: the style's loop, two chords (dub's: roots, I and IV; minor, vi and IV; or the song's own
    chords as triads), no colour; the bass leading (its notes a little louder, the others' a little softer);
  - the **singer's lines reduced to fragments**: each line, by its own coin, keeps its last word, its first half
    or its second half (a half line), all of it now and then, or nothing; a refrain's first line always keeps at
    least "nobody knows" (its second half) and the last refrain's last line its last half ("now it's by you"),
    so the hook stays recognizable in pieces. A fragment is sung where it falls in the tune, on its own notes;
    the rest of the line is not sung;
  - **every fragment thrown**: its last word (or the whole fragment, up to a second and a half) into the tape
    echo with a longer tail (feedback 0.72 against the song's 0.6, a little louder), and now and then into the
    spring;
  - the **melodica takes the tune in pieces**: it plays the notes the singer left out (the lead where nobody
    sings, `lead`), a line's pieces resting now and then (the desk's coin), so voice and melodica answer each
    other;
  - **the desk harder**: bars dropping out at 0.45 (the riddim alone, the drums alone, the band without drums),
    the snare kicked into the spring every few bars, the whole band's **low-pass swept** closed and open again
    over four bars now and then (sweeps on the band's bus: `sweep-lp` then `sweep-open`, the transitions the mix
    already has);
  - **one drop into steppers**: the last refrain (in the version) goes to the kick on every beat, as built.
- The **dub-out** after the song (ending `version`, drawn 0.75 now) stays: the riddim's eight bars, the last
  fragment thrown into it.
- **Tempo**: 0.73 to 0.81 of the song's (70 to 78 for H), centre 75.
- The lyric sheet is the whole lyric (the words were drawn for every section); the score sings the fragments.

### What is the style's own (fixed) and what chance draws per machine

| | house | dub |
|---|---|---|
| fixed | the loop's use and where; the lengths (16-bar intro and outro, four-bar hook turns, eight hook bars after the drop and the last refrain); the chop and its words; the octave bass; the tempo range | the version's form (fragments, throws, melodica pieces, riddim) whenever it dissolves; the tempo range; steppers in the last refrain |
| drawn | which fitting loop; the chop's rhythm; the drop (0.8) and the rest of the options as before; the intro's piano tune or the chop | whether it dissolves (0.9); which fitting riddim; each line's fragment; each drop-out, throw, splash and sweep; the dub-out (0.75) |

### Byte for byte, the records, memory

- Every other style: none of the new fields, so nothing new is called; checked by the goldens and PCM ids (the
  seed, lo-fi, synth folk, gospel and the session for ada, juno's own, indie for vela).
- House's and dub's records from before: they load, and replay as far as they carry their choices: a house record
  has no `loop` (the default: the best-fitting loop) and gets the lengths and the chop; a dub record has no `dissolve`
  (not dissolved) and gets the riddim nowhere but the dub-out. Their ids change; said so.
- Memory: house's shape is longer (ada's with a drop about 3.5 minutes at 124), dub's about as long as before;
  measured with tools/render_memory.py, and MEASURED updated.

## What the review changed (2026-09-30, evening)

A read-only Fable review of the design above, before it was built (the loop table recomputed in its own scripts).
Its points, and what was done:

1. **The loop's sevenths must be the mode's own**: a named quality is fixed whatever the mode (`vi7` is B-D♯-F♯-A),
   so a loop is spelled per rendition from its degrees in the rendition's mode (`vim7`, `IVmaj7`, `V7`; in aeolian
   `VImaj7`, `ivm7`), as the chord card's row of the key's sevenths is. Built so (`style.loop_symbols`), and tested.
2. **The tonic's maj7 grinds under the singer's home note**: I is voiced `Iadd9`, not `Imaj7` (a loop's other
   sevenths stay). The fit counts a sung note on a chord's seventh as a chord tone (the tune on a maj7 is its
   colour), a semitone from its triad as a clash; the table above is recomputed so (vamp 0.5, lift 0, home 0.5,
   deep 1.3, royal 2.7 in D major: all five fit; pop 8.5 and minor 12.2 don't).
3. **A droppable seventh needs a mechanism**: the band's `tones()` leaves a loop chord's seventh out wherever a sung
   note is a semitone from it (its symbol one of the rendition's loop's), as a style's colour steps aside; the
   MIDI file and the page still name the chord. Tested (Gmaj7's F♯ never under a sung G).
4. **Where nothing fits, the song's own chords**, not the closest loop (which in aeolian puts iv under a sung 5):
   `fitting_loops` gives "song" then, and the style's form, bass and hook carry it. For H, house in aeolian still
   has two that fit (vamp 5.3 and pop 6.3 against the song's 4.3 and two); dub's riddims are allowed four beats of
   slack (a riddim under fragments), and in aeolian none fits: the song's own.
5. **Inject the loop in `composition.form_phrases`**, between a person's everywhere chords and a place's own, so the
   band, the choir's and backing voices' chords (melody's chord), the MIDI file's chords and the page follow from one
   place: as built. The page shows the loop's chords in the lane, in the program's ink (a person's are marked by
   their edits, not by differing from the song's).
6. **Drop on the hook, not on a sung folk refrain**: the drop's refrain now opens with **eight bars of the chop over
   the full groove** (the ride, the rolling bass, the pluck: the drop), and the singer's refrain follows as the
   release; the last refrain keeps its eight hook bars after it. The chop's rhythm changes at the drop (the next of
   the three figures), and there the call alternates with the answer ("now it's by you"). The hook's bars are laid
   on the song's turn line (a line with no tune), so no lead plays a tune under the chop; the sung lines take the
   refrain's words in order after them (realize, the page's words and places count the lines a style laid first:
   `takeover.leading`, `own_line`).
7. **The chop is a part of its own** (`chop`), not the singer's `voice`: the lyric sheet and the synced words don't
   gain its syllables, `variation.lay` doesn't move it off the grid, it draws on no rendition stream but its own,
   and it has its own stem and channel (the singer's voice as one of the band's instruments: its low end cleared, a
   gentle compressor, a little more room; `mixing.ROLES["chop"]`). Its memory rate is the voice's.
8. **The voice would breathe before every chop syllable** (an in-breath wherever a gap passes 0.12 s): the chop is
   sung by the singer's own settings with breaths off, each syllable held 85% of its slot (a tenth of a second at
   least), each "knows" the phrase's end. Whisper hears "Nobody knows, nobody knows" in the chop's stem.
9. **The style's lengths in `phrase_plan`**, under a person's (`own_lines`, as a session's rounds): `arranged_plan`
   returns them so realize lays the lines as the style does; `takeover.value` and the page's grid give the style's
   length as the program's own. A person's entry for a section that doesn't set its bars (a player's level, say)
   keeps the style's length.
10. **A turn's length a person can't change** (the turn's own line quotes a sung one to fit two bars): left as it
    was: house lays its turns at four bars itself; a person's `bars` on a turn is still refused. Said below.
11. **The pad intro would strip house's layered intro**: in a style that builds its intro in layers the pad-only
    intro is not applied; `intro=pad` in house means the chop takes the intro's last four bars instead of the
    piano's tune. The layers: `plan.entrances` at their bars (scaled with a person's length), and the outro's layers
    leave by `plan.exits` (a field the plan had and nothing used).
12. **Dub's fragments**: a fragment's last syllable is marked a line's end (the singer releases it; the desk finds
    it); fragments keep whole words (they break at word boundaries); the melodica takes the version's sections as
    `lead` (a `dubbed` key in the parts, set by `mark_dissolved` as the drop's is by `mark_drop`), rests half its
    lines (the desk's coin), and the dissolved sections keep their weight under it (`played`).
13. **The bridge comes back whole** in the version: sung, with the lineage's choir, on the song's own chords (the
    vocal dropping back in is itself a dub's move; the bridge is the song's idea). The chop's words stay the first
    refrain's last words ("nobody knows") rather than `genome.hooks` (whose first hook is the question: the chop
    is the answer).
14. **Replay**: the loop's name is stored when drawn (`""` only in records from before: the best fit); the chop's
    rhythm and each fragment come from the rendition's seed, each by a stream of its own; drop-outs, throws, sweeps
    by the desk's streams by bar. `Style.dub` was renamed `dissolve`. With `dissolve` 0 the desk's choices are as
    they were (a version after the song in any style: the same throws).
15. **Desk sweeps mid-section** go to `produce()` as transitions of their own (`sweep-lp`, then `sweep-open`),
    applied to the band's bus as a person's sweeps are; the echo's returns join the band before it, so a sweep
    darkens them too.
16. **Memory**: the outro is sixteen bars only where the form has one; the last refrain's hook bars are laid only
    where the form ends on a refrain. Measured below.
17. Small ones: house draws `repeat` never (the hook is its tag; `repeat` stays valid); the octave bass has its page
    label; tempo ranges as designed. Coupling a thrown fragment to a drop-out after it (the throw into silence) is
    left for later.

## As built, and measured (2026-09-30, evening)

| Where | What |
|---|---|
| songbird/style.py | `Style.loop`, `Style.dissolve` (both left out of a record while off); `StyleDef.loops`, `.looped`, `.form`, `.hook`; house's loops, lengths, layers and chop rhythms; dub's riddims and the version's desk (`DUB_DESK["dissolved"]`); the fit (`tune_clash`, `loop_clash`, `fitting_loops`, `loop_symbols`, `loop_of`); the lengths (`own_lines`, `hook_lines`); the chop (`hook_bars`, `hook_words`, `chops`); the version (`dissolved_from`, `dissolves`, `fragments`); both drawn in `choose_options` by coins of their own |
| songbird/composition.py | the loop laid in `form_phrases` (`_looped`), under a person's chords; a line a style lays before a section's own has no place (`at_place`, `view`) |
| songbird/takeover.py | the style's lengths in `phrase_plan`/`arranged_plan` under a person's; `leading`, `own_line`; the style's length as the program's own on the page |
| songbird/realize.py | the sung lines take the words in order; a dub's fragments; the chop's notes |
| songbird/idioms.py | a loop's seventh left out where it rubs; `w_octave`; the layers (`layers`, `plan.exits`); no quote in a hooked turn, no tune in its outro; `mark_dissolved` and the `dubbed` parts; the desk in the version (drop-outs, the bass leading, the melodica's rests, the fragments' long throws and the spring, the sweeps) |
| songbird/sound.py | a throw's longer feedback; the desk's sweeps as transitions |
| songbird/synth (\_\_init\_\_, instruments, mixing), midi.py, studio.py, public.py | the chop as a part: sung without breaths, its channel, its MIDI track, its preview, its memory rate |
| songbird/explain.py, edits.py | the loop and the dissolving in words; `style.loop` and `style.dissolve` as a person's |
| tests/test_house_dub.py | the loop and where it plays, the lengths, the chop, the octave bass and layers, dub dissolving, the options' traces, an old record singing |

No new numba kernel (the browser's kernels as they were: tests/test_browser_kernels.py); the packet 6.35 MiB of 8.

**Nothing else moved.** Seven renders against the tree before, to the bit: H's seed (9b0766353b73), lo-fi
(bcce8df33538), synth folk (9b6962b8c7f0), gospel (68d78e888360) and the session (0bf8ab5ce7ba) for ada on
30 September, juno's own style on 15 October (a4e81b19490a), indie for vela (a4d33d7a148b); the goldens hold and
the suite passes (1697 before these tests).

**Replay.** A new house and dub record replay to themselves (house2-otto, dub2-juno: "replay: matches"). The records
from this morning load: a dub record (no `dissolve`) even replays to its own id (dub-juno, fb893109e68e: its desk's
choices are as they were); a house record renders differently, as said: house-otto's is 170.7 s now (117.9 s
then: the 16-bar intro and outro, the loop, the chop).

### The renders, for listening

In `renders/styles/` of the main checkout (gitignored), H as the same made-up machines sing it:

| render | tempo | what the program chose | length | id |
|---|---|---|---|---|
| house2-ada-2026-09-30 | 124.6 | the home loop (Dadd9, Gmaj7); the piano's tune in the intro's last four bars; a drop after the second refrain (its breakdown a hook turn and the third verse); the last refrain's eight hook bars | 229.5 s | e50ed3ac0179 |
| house2-juno-2026-10-15 | 122.5 | the deep loop (Em7, A7, Dadd9, Bm7); the chop teasing the intro's last four bars; a drop after the second refrain (a turn, the break, the bridge); a cold stop after the tag | 180.2 s | ea3dd6966ff2 |
| house2-otto-2026-09-30 | 121.9 | the royal loop (Gmaj7, A7, F♯m7, Bm7); two verses, no drop; a 16-bar outro, the chop for eight bars and the band leaving in layers | 165.4 s | 476f84b160b6 |
| dub2-juno-2026-09-30 | 74.1 | dissolving after the first refrain (the version 73% of the song) over the plagal riddim (G, D); the dub-out | 249.0 s | f2353ce33e3d |
| dub2-vela-2026-09-30 | 77.8 | a count-in; three verses sung straight to the second refrain, then the version (57%) over the roots riddim (D, G); the dub-out | 259.0 s | 0d7214151808 |
| dub2-ada-2026-09-30 | 74.4 | dissolving after the second of four refrains (54%), plagal; both bridges whole; a cold stop | 269.0 s | e99be44058d2 |

### What they play (the scores, the stems, the MIDI files)

- **House's loop.** The MIDI files' chord track names the loop: ada 50 Dadd9 and 50 Gmaj7, and in the bridges 6
  each of Bm, D and A (the song's own); juno 20 to 21 each of Em7, A7, Dadd9, Bm7; otto 18 to 19 each of Gmaj7,
  A7, F♯m7, Bm7. The stabs sit on the chord under them: 996 of 1040 of ada's piano notes (the rest the piano's tune
  in the intro and break), all 638 of juno's, 626 of 648 of otto's.
- **The lengths.** ada: intro 16 bars, turns 4, the drop's refrain 16 (eight bars of the hook, then sung), the last
  refrain 16 (sung, then eight of the hook). The layered intro: the drum machine from its first beat, the bass from
  bar five, the pad and stabs from nine, the tune (or the chop) from thirteen (tested).
- **The hook.** The chop sings 127 syllables in ada (59 in otto, 85 in juno): each four-bar turn "nobody knows" three
  or four times, the drop's eight bars the call three times and "now it's by you" four, the last refrain's eight the
  same; in a breakdown's turn once in two bars, soft. Every note on a sixteenth of the clock (no jitter, no lay), none
  over a sung note. Whisper, listening to the finished mix two bars at a time, hears "nobody knows" in 21 of the
  30 two-bar stretches of the three house renders (10 of 14, 6 of 10, 5 of 6); where it doesn't, the drop's full
  band is as loud as the chop (the chop's stem 0.4 to 3 dB over the band's dry stems there, 4 to 9 in the turns).
- **Dub's version.** It dissolves after the first refrain of three (juno: 65.8 s into 241.4, the version 73% of
  the song) or the second of four (ada 54%, vela 57%). The singer keeps 37 to 56 syllables of the version's lines
  (outside the bridge), in 11 to 13 fragments, e.g. juno's: "The whole world was watching", "way", "along", "but
  nobody hummed", "Nobody knows", "grows", "through", "Nobody knows", "It's yours while you sing", "one, and now
  it's by you" (and the tag's "la"); Whisper, on the mix, writes 7 of those 11 as sung and the rest near ("brows"
  for grows, "one and now it's fire"). The bridge comes back whole with the choir. 8 to 11
  fragments a song are thrown into the echo with the version's feedback (0.72: 19 repeats to 50 dB down, about 11.5 s
  of tail at 74, against the song's 13 repeats, 7.9 s), two of ada's into the spring too; the band's low-pass is
  swept closed and open two to four times; the melodica takes the notes the singer left out, half its lines resting
  (56 to 123 melodica notes a song).
  The riddim: juno's and ada's the plagal (IV, I), vela's the roots (I, IV); the minor (vi, IV) was drawn by none of
  the three.
- **Memory** (tools/render_memory.py, two threads, `MallocLargeCache=0`, the style chosen with no machine): house
  163 s, 1.27 GB (estimated 1.40); dub dissolving with its dub-out 222 s, 1.91 GB (estimated 2.04); MEASURED
  updated. In the VPS's 2100 MB a house version fits to 4.5 minutes (ada's long shape is 3.8), a dub one to 3.9
  (H's own shape fits; a machine's long shape, ada's 4.5 minutes, is refused on the server as before).

## Decisions for the artist (house and dub, again)

1. **The loops** (house: vamp, lift, home, deep, royal, pop, minor; dub: roots, minor, plagal) and the fit's
   slack (two beats for house, four for dub). In D major every loop but pop and minor fits; in aeolian house has two
   and dub none (the song's own chords). `style.loop` picks one, or `song`.
2. **The bridge keeps the song's own chords** in house (the breakdown's heart) and comes back whole in dub's
   version: the folk song surfacing inside the reinterpretation. Either could go the other way.
3. **The drop is the hook first**, eight bars, then the sung refrain; the last refrain ends on eight bars of the
   hook. The chop in a full drop is about as loud as the band (Whisper misses it there more than in the turns); a
   louder chop is one number (`CHOP_GAIN`, or the hook's `drop` level).
4. **The chop's words** are the first refrain's last words ("nobody knows") and the last refrain's ("now it's by
   you"), at their own pitches; not pitched up (the throat stops at B4).
5. **Dub dissolves 0.9 of the time**, after half the refrains; the lyric sheet still prints every line (the words
   were drawn for them). Coupling a throw to a drop-out after it (the throw into silence) is left for later.
6. **Verses stay** in house: the bank needs two at least, and each has its story; a shorter house would need the
   form to change (and so the words), which a style doesn't do.
7. **A turn's length** stays the style's (four bars in house); a person can't set it, as before.
8. **The records from this morning** render differently for house (not for dub without `dissolve`); none was
   released.

## The chop's turns: whole words, a deliberate stutter, the answer (2026-09-30, night)

**What the artist heard.** On house2-ada: "the chopped hook doesn't work well around 0:55-1:00 - later on it's
better though." Nothing is chopped at 0:55 to 1:00 in that file: the singer is on the first refrain's last two
lines, and the chop first comes in with the turn at 1:02.5 (ada's intro is the piano's tune, so this turn is the
first time the hook is heard). Whisper over 0:50 to 1:10 hears the singer, then "...some of you too Nobody knows,
nobody knows": the chop's first word runs straight on from the singer's "too". So the place is the turn's entrance
just after it, as the score shows.

**The cause.** The turn opened "bo-dy knows. knows. knows." with no "No". Nothing fell before the turn: the chop
leaves out any syllable with a sung note under it, and the singer's last note ("too.") ends on the turn's
downbeat, and ending there counted as under it. So the figure's first syllable was dropped and the rest was sung.
This happened at the start of every hook bar that follows a sung note: every turn after a refrain, the drop, and
the last hook (5 of ada's 26 figures, 1 of juno's 18). The stutter figure (ada's turns and last hook, juno's drop)
then repeats "knows" twice more, each a sixteenth right after the last (0.1 s long), which sounds like a glitch.
Whisper heard it as "no body nose, no body nose".

**The fix** (house's chop only: `style.chops`, `hook_bars`, `HOUSE_HOOK`):
- A sung note that ends exactly as a figure starts no longer counts as under it. A figure is sung from a word's
  first syllable to a word's last, or not at all. A sung note cutting into a figure ends the figure at its last
  whole word, and the figure never starts again after it. Every turn, the drop and the last hook now open on
  their downbeat with "No". This was the most musical of the three options: the hook arrives with the turn.
  Dropping the figure, or moving it a bar later, would leave the turn's first bar empty.
- The stutter repeats the whole word on eighths: "No-bo-dy knows, knows, knows", the repeats on beat 3 and the
  "and" after it, as the drop's "you, you" (which the artist likes). The beat and off-beat figures are unchanged.
- The turns use the drop's call and answer: each turn alternates "No-bo-dy knows" with "now it's by you", at the
  turn's level (0.85; the drop is 1.0). A breakdown's turn still sings only the call, once every two bars, softly.
  Whether the answer belongs in the early turns is the artist's call. To keep the turns as before, set
  `HOUSE_HOOK["answered"]` to `("drop", "last")`.

**Measured** on the three house renders (ada, juno, otto; replays of their house2 records). Whisper base.en
transcribed the finished mix two bars at a time over every hook bar.

| | before (house2) | turns call only | as built (house3) |
|---|---|---|---|
| "nobody knows" heard, of 30 stretches | 16 (ada 5 of 14, juno 6 of 10, otto 5 of 6) | 24 (11, 8, 5) | 25 (12, 8, 5) |
| figures starting mid-word | 6 (ada 5, juno 1) | 0 | 0 |
| a syllable repeated a sixteenth after itself | 14 (ada 10, juno 4) | 0 | 0 |

The 21 of 30 measured earlier (above) does not reproduce today for ada: the same file now gives 5 of 14 (it gave
10), while juno's 6 and otto's 5 do reproduce. Whisper is a jumpy judge; the same chop under a mix 0.01 dB louder
can change a window's text. Whisper writes "now it's by you" as "now that I need to give you" and similar, and
counts it once in 30. Otto has no turns or stutter, so its chop is unchanged.

**For listening** (`renders/styles/` of the main checkout; times are file time):

| render | id | the hook |
|---|---|---|
| house3-ada-2026-09-30 | a0919e2b3ac5 | turns at 1:02.5, 1:41.0 (the breakdown's, soft) and 2:34.9; the drop at 2:04.1; the last hook at 3:28.9 |
| house3-juno-2026-10-15 | 31470a6d2e89 | the intro's tease at 0:24.6; turns at 1:03.5 (from 1:03.8, the off-beat figure) and 1:42.7 (soft); the drop at 2:21.9 |

Nothing else moved: every other style renders as before (goldens, the suite). House's own renders change where
the chop changes: ada and juno, as above; otto replays to its own id.


**The last word let go (2026-09-30, night).** The hook fix's agent found the singer's last "*you*." in ada's last
refrain held 16.9 s, under the whole last hook: `realize` holds the song's last sung note to where the lines end,
and house's eight hook bars after the last refrain are laid as lines (played). A style with lengths of its own
(StyleDef.form: house) now holds it only to the end of its own line; nothing else moves (the score's one note: 16.91
s to 0.73 s). The singer's small random variations are drawn over the whole voice part's length, so the voice stem
is a fresh take of the same notes from its first word (every other stem identical). house4-ada-2026-09-30
(6af016bc9bb3), a replay of house3-ada's record.

# A jazz trio (September 30, 2026)

**Hidden for now (2026-09-30, night).** The artist listened: "everything sounds great except jazz - not sure the
vocals fit there." The folk singer's straight delivery over a trio is the mismatch, not the trio. It's no longer
offered in the studio's picker (`style.HIDDEN`); a record, a draft or `--style jazz` still plays it.

The artist, after the jig and the a cappella convinced and house and dub didn't: a style convinces when a singer
delivers the folk tune straight over instruments the program synthesizes well, and fails when it needs another kind of
singer or heavy sound design. A **jazz trio** is that kind of style: a piano, an upright bass and brushes, all three
instruments the program already plays well (the modelled piano, the upright, the kit's swept brushes), the singer on
the tune as written, and the change carried by the harmony, the comping and the time feel. The page calls it "jazz
trio" and says what plays, "piano, upright bass and brushes"; it claims no tradition beyond that.

(What follows is the design as it went to review; "What the review changed" and "As built" below say where the
build differs.)

## The design

**Where it sits.** Beside the ring, at chamber's place (`OFF_RING["jazz"] = "chamber"`: the piano, the waltz, the
sevenths), as the a cappella, the jig, house and dub do. A person chooses it (`--style jazz`, the studio's style card);
nothing steps into it by chance; a child of a jazz version keeps it or steps to chamber's neighbours. The artist
decides later whether it joins the ring.

**The feel and the tempo.** A jazz waltz (the song re-barred in three, as chamber's and country's waltzes already are:
every stressed syllable on a downbeat), 0.55, or a ballad swung, 0.45. The waltz at 0.72 to 0.88 of the song's tempo
(centre 0.8: 77 for H, a waltz quarter at 115), the ballad at 0.7 to 0.88 (centre 0.78: 75, swung). Slow enough that
the singer's words sit as they do in the ballad; the waltz makes the song half again as long, as chamber's does.

**The trio's changes** (`style.trio_changes`; new, and empty for every other style). The song's chords stay the
song's functions (I is still I), played as a jazz pianist would read them off a lead sheet, and fitted to the tune the
way house's loops are, but stricter: a chord the trio plays may rub a semitone against **no sung note that the song's
own chord there doesn't** (`style.sits`: the song's own passing notes, such as the 4 over I in the second verse line,
rub as they always did; the trio adds no rub of its own). What is sung over a chord is every note of the line in its
span, and over a line's last chord the pickups of whatever line follows it in this form.

- **Colour, always where it sits.** Each chord the richest of its colours that sits: a major chord its maj7, else a
  6, else an added ninth, else the triad; a dominant its 7, else an added ninth; a minor chord its m7, else an added
  ninth. In the mode's own spelling (`trio_chord`, as house's loops are spelled: vim7, IVmaj7, V7; in aeolian im7,
  ivm7, VImaj7, vm7).
- **Passing chords, as often as `Style.harmony` says** (0.7 for the style, a machine's richness and the season moving
  it as for every style; each chord its own coin from the rendition's seed, so one's choice moves no other's):
  - *ii-V*: a V that resolves to I, or ends a line (a half cadence), takes its ii for its first half (two beats of
    a bar, or one of a half bar: `iim7 V7 I6`);
  - *a fifth above*: a chord held a whole bar before another gives its second half to the chord a fifth above what
    the next one starts on, the mode's own seventh or else a dominant (I7 before IV, iiim7 before vi, vim7 before a
    ii-V's ii: the circle of fifths walking into the cadence).
  The lines are decided from the end back, so a chord approaches what the next one actually plays.
- A chord held over two shares of a bar is written twice (`I6 I6 iim7 V7`), as the genome writes a bar of four
  chords; the players hold it as one.
- **Where it goes in.** Between a person's chords and the band, in `composition.form_phrases` (after a style's loop,
  which the trio has none of), so the band, the choir's and backing voices' harmony, the MIDI file's chord track and
  the page's chord lane all read the same changes. A line whose chords a person set (everywhere, or at its place)
  keeps theirs exactly; a line whose chords aren't plain numerals keeps them.

What H gets in D major with every passing chord taken (harmony 1; ionian):

| line | the song's | the trio's (harmony 1) |
|---|---|---|
| v1 | I \| I V | D6 \| D6 Em7 A7 |
| v2 | I \| V I | D6 \| Aadd9 D6 |
| v3 | I \| IV V | Dmaj7 D7 \| Gmaj7 Em7 A7 |
| r1 | I \| IV V | D6 D7 \| Gmaj7 Aadd9 |
| r2 | I vi \| V I | Dmaj7 Bm7 \| Aadd9 D6 |
| r3 | vi IV \| I V | Bm7 Gmaj7 \| Dmaj7 Aadd9 |
| r4 | I \| V I | Dmaj7 E7 \| Aadd9 D6 |
| b1 | vi \| I | Bm7 \| Dmaj7 |
| b2 | vi \| V | Bm7 \| Aadd9 |
| b3 | I \| vi V | Dmaj7 F♯m7 \| Bm7 Aadd9 |
| b4 | I \| V | Dmaj7 Bm7 \| Em7 A7 |
| t1 | IV \| V | Gmaj7 Bm7 \| Em7 A7 |

H's V is mostly an Aadd9, not an A7: the tune sings F♯ over it (the 13th), and the seventh's G would rub it; where
nothing is sung over the V's second half (a line's end, a turn) it is A7, and its ii comes before it. The I is a D6
where the tune sings D over it (a maj7's C♯ would rub), a Dmaj7 where it doesn't.

**The players.**

- *Piano* (`rootless`, new): comping in rootless chords, the third and the seventh (or sixth) with the fifth and a
  ninth where they sit (the ninth only where the mode's scale has it a whole step over the root and nothing sung
  rubs it), four notes close round middle C (about an octave under the tonic up to a fourth over the low end of the
  singer's line), led smoothly from the last (the program's `voicing`, which keeps off every sung pitch). The rhythm:
  struck as the chord comes and held, or answered: in a waltz on two and three (the bass has one), or on the
  off-beat after two; in four on the off-beat after two (the Charleston) or the backbeats; now and then pushed an
  off-beat early. `rootless-light` (the first verse when the band is sparse): held chords only.
- *Piano with the tune* (`solo`, new): where the piano has the tune (the intro, a turn's quote, the break, an outro),
  its right hand plays it an octave up and its left hand keeps the chords, the third and seventh under it, in the
  comping's rhythm. In the break, the piano's chorus on the verse tune, a held note at a line's end is answered after
  its first beat by a few of the chord's tones. A style's table naming "solo" for the lead's own section turns the
  lead's "lead" or "quote" into it (`plan_style`; no other style names it).
- *Upright bass* (`walking`, `twofeel`, new): walking a note a beat, the root as the chord comes, its tones between,
  moving toward the next chord's root, and on the last beat a step into it: a scale step or a half step, whichever
  rubs against nothing sung there, else the chord's fifth. Two to a bar in the first verse, the bridge and the tag (a
  root on one, a fifth on three; in a waltz one a bar), stepping into the next chord now and then; walking in the
  refrains, the break and the turns, and in the verses once the band is fuller.
- *Brushes* (`swept`, `swept-light`, new): the kit's own brush sweep (the bristles' stream of catches, circling when
  one sweep follows another) round the snare, two sweeps a bar in four and one a bar in a waltz; the right hand taps
  the backbeat (two and four; a waltz's two and three) and the swung off-beat after it now and then; the bass drum
  feathered on one (and three). Light: the sweeps and the bass drum, the taps barely there. A tap pickup into a
  fuller section; the last chord one sweep and a tap. No sticks, no cymbals.

**The form.** Room for the piano's chorus: where the rendition's form has no break and the song's template has a
place for one, the trio adds it, 0.8 of the time by a coin of its own (`style.with_break`, `SOLO_BREAK`): H's break is
the verse tune, eight bars, before the bridge. A form a person set (`--form`, the studio's order, an edit) is kept as
it is. A child of a jazz version inherits the form as any child does.

**The rest of what a style brings.** The band's ornament down (no grace notes in the piano's tune). The singer: a
little less vibrato (-3 cents), nothing else: the tune stays the singer's, sung straight. The mix: a little closer
(intimacy +0.15), a smaller room (space -0.05), a little narrower. Options: the intro the piano's (0.85) or, with no
intro, the singer alone first (0.35); a verse with the piano alone or bare 0.15; stop-time 0.1; a breakdown 0.15; a
lift 0.1; endings a broad ritardando 0.5, ringing 0.4, cold 0.1; entrances 0.25; backing voices rarely (oohs 0.15);
no half-time bridge.

**What's new, and what stays as it was.** style.py: the trio's block (its StyleDef, `CHANGES`, `SOLO_BREAK`,
`trio_changes`, `sits`, `changed`, `with_break`), and one hook in `choose_style` (the break). composition.py: one hook
(`_changed`) after the loop. variation.py: a form set by hand is put back after the style decides as well as after the
form does (a no-op for every other style). idioms.py: the trio's writers in a block of their own, and the "solo" turn
in `plan_style`. No numba kernel added or changed. Every other style passes none of the new code's conditions, so
every other render stays byte-identical (the goldens, every style's scores for four machines, and six renders' PCM
ids, before and after).

**Decisions for the artist** (at the end, "As built").

## What the review changed (September 30, 2026)

A read-only Fable review of the design above, with the first build in the tree to check it against (it re-derived the
whole table of changes, ran 206 tests including the goldens, and measured). Its points, and what was done:

1. **A bar the changes can't write crashed.** `_bars` wrote a bar on 1, 2 or 4 shares only, so a ii-V on a quarter-bar
   V, or any bar of three chords, had no way to be written (a person's `I IV V I`, `vi ii V`). Now a bar keeps as many
   shares as its own has where those hold it, and where a passing chord can't be written at all the line takes its
   colours alone (tested).
2. **A line with a tune of its own at its place** was fitted against the line's own tune. It now keeps the song's
   chords there (the changes are fitted to the line as the song has it).
3. **The dominant's seventh under the tune's sixth.** The semitone test is symmetric, which is right for a maj7 under
   a sung tonic (C♯ a semitone under D: a minor ninth when voiced under it) but also forbids A7's G under a sung F♯, a
   major seventh under it: A13, the style's most idiomatic sound. So H's V is mostly an Aadd9. **Kept as it is** (the
   brief: nothing grinds a semitone against the melody), and **left for the artist** (below): a directional rule
   (`(sung - tone) % 12 == 1` rubs, `== 11` doesn't) would let the V be A7 under the F♯, kept symmetric where the
   lineage's choir sings (the choir takes any chord tone under the tune, and would sing the G a major seventh under).
4. **The only chord outside the tune's world** is r4's E7 (V of V, its G♯), where the harmony knob draws it. Good
   jazz, and the singer never sings G♯; flagged for the artist.
5. **Passing chords never cross a line** (the changes are by line, so the chord lane and every verse agree): accepted.
6. **A waltz splits a whole bar's V only**: a quarter-bar ii-V re-barred is a ii on one and a V on two and three;
   playable, but a waltz player splits a bar's V into a bar of ii and a bar of V. Done (`rebarred`).
7. **The comping sat low** (C3 to E4, under middle C and over the bass's top): now from a seventh under the tonic to a
   third over the singer's low end (for H in D: E3 to F♯4), its mean pitch measured at B3 to C4.
8. **The chorus's left hand** took an added ninth for a seventh (Vadd9's shell was its third and ninth): now the third
   and the seventh or sixth, else the third and fifth.
9. **The walking line** used chord tones only: it now takes a scale step on a weak beat, toward where it is going; two
   to a bar puts the fifth on the other strong beat, as designed.
10. **The brushes** tapped the backbeat and its skip, a folk brush figure: now every beat (the backbeat strongest) and
    the skip after two and four (a waltz's after two), the ride's figure on the snare.
11. **Nothing else moves**: the render paths are gated by the style's name and the goldens pass. What a person sees
    elsewhere: the new patterns are offered for the piano, the bass and the kit in every style's menus (by
    `takeover.style_patterns`' design, each with its words). A chord written twice to fill a bar's shares showed as two
    in the piano score's head ("D6 then D6") and was struck twice in the MIDI file: now one held chord in both, for the
    trio only (`style.held_chords`; a person's repeated chord is still struck again).
12. **The style card** said nothing of the chords: it now says "the song's chords with sevenths and sixths, and passing
    chords into the cadences" (the last part where the version has any).
13. **The form.** Adding the break in `choose_style` lets the options read a form with the break where a hand-set form
    is put back after; the options read only the verses and refrains, which a break doesn't change, so it was left
    there (it also covers a style chosen with no machine, which never reaches `choose_form`).
14. **The waltz is not half again as long**: the tempo counts the song's beats, each foot a bar of three, so at the same
    tempo a waltz is the song's length (ada's waltz 261.7 s at 76.6, her swing 268.6 s at 74.6). Corrected above in the
    code's comment and below.
15. **Memory is the real risk**: the kit's rate (7.1 MB a second) and the estimate allow about 4 minutes in 2100 MB, and
    machines' long shapes are longer. The tempo centres went up (the waltz 0.85 of the song's, the ballad 0.83); the
    break stays a style's choice, never the server's (a version's music doesn't depend on what a server can hold).
16. **Measure** as the review defined it (below): the chord under a note's middle, the minor ninth apart from the
    major seventh, seconds as well as notes, the comping's register; Whisper on the mix with the ballad and a swung
    version beside it.

## As built, and measured (September 30, 2026)

`songbird render --style jazz`, or "jazz trio" in the studio's style card (after the ring's, beside chamber). Nobody
has listened; everything here is measured.

| Where | What |
|---|---|
| songbird/style.py | the trio's block at the end: `JAZZ` (beside the ring at chamber's place), `CHANGES`, `SOLO_BREAK`, `trio_chord`, `sits`, `trio_changes`, `_bars`, `changed`, `held_chords`, `with_break`; the break's hook in `choose_style` |
| songbird/composition.py | `_changed` after the loop in `form_phrases` |
| songbird/variation.py | a hand-set form put back after `choose_style` as after `choose_form` |
| songbird/idioms.py | the trio's writers in a block of their own (`rootless`, `rootless-light`, `solo`, `walking`, `twofeel`, `swept`, `swept-light`); a lead's "solo" in `plan_style` where a style's table names it |
| songbird/takeover.py, explain.py | the patterns' words; "jazz trio", its players ("upright bass", "brushes"), its feels ("a waltz", "a ballad, swung"), the card's line on the chords (`changes_words`) |
| songbird/midi.py, piano.py | a held chord one chord in the MIDI file's chord track and the piano score (the trio only) |
| tests/test_jazz.py | the place, the changes in every mode and harmony, a bar it can't write, a person's chords, the break, the players, the page, the share on the chord |

**As built, where it differs from the design**: the review's changes above; the tempo a little brisker (the waltz
0.76 to 0.94 of the song's, centre 0.85, its quarter about 122 for H; the ballad 0.74 to 0.92, centre 0.83, about 80);
the lineup piano 1.0, bass 0.85, kit 1.25 (the brushes' stem sat 17 dB under country's kit at first: now about 8);
the comping's tones it can spare (a fifth, a ninth) left out where they'd rub a sung note on a strong beat or a long
one; no new numba kernel, so the browser's translation is as it was.

**Nothing else moved.** Every other style's score for four machines (ada, bob, coral, dmitri on their dates; every
style for each, with three voices too for ada; the seed; 90 in all) is identical before and after; six renders made
before the change render to the same PCM ids after it: the seed (9b0766353b73), ada's own (8e8c9e92fc61), chamber for
ada (8e10c6ee39a0), the songwriter for bob (1d7413323129), country for coral (72a357a11dd0), gospel for dmitri
(fbe73c7054ad). The goldens pass. A jazz render replays to itself (bob's: "replay: matches").

**The changes, as the four machines drew them** (the harmony knob 0.57 to 0.71): ada's waltz in D major has the verse
lines D6 | D6 A7, D6 | Aadd9 D6, Dmaj7 | Gmaj7 A7, the refrain's last line Dmaj7 E7 | Aadd9 D6, the turn Gmaj7 Em7 |
A7, the bridge's end Dmaj7 | Em7 A7 (in a waltz only a whole bar's V takes its ii; swung, the half-bar Vs do too); in minor (bob, coral) im7, ivm7,
VI6, iim7♭5 vm7. By construction no chord the trio plays rubs a semitone against a note sung over it that the song's
own chord there doesn't (tested in four modes at three harmonies).

**The notes** (each piano or bass note against the chord under its middle; a sung note is the singer's or a lineage
voice's, sounding with it for 20 ms or more):

| | piano on the chord (its ninth) | bass on the chord (a step into the next) | piano a minor ninth under a sung note | piano a semitone over one | comping's mean pitch, under C4 |
|---|---|---|---|---|---|
| ada, a waltz, D major | 84.5% (14.4%) | 91.5% (8.2%) | 1.3% of notes | 0 | B3, 55% |
| bob, swung, D minor | 92.4% (5.0%) | 86.2% (11.6%) | 5.2% | 5.4% | B3, 49% |
| coral, a waltz, E♭ minor | 91.8% (6.9%) | 90.1% (8.3%) | 3.8% | 4.5% | A3, 69% |
| dmitri, a waltz, E♭ major | 90.6% (8.3%) | 91.7% (8.3%) | 2.0% | 0.3% | C♯4, 31% |

So 98% to 99% of the piano's notes are its chord's tones or its ninth, and the bass's other notes are its steps into
the next chord. Where a note rubs, it is almost always a tone of the song's own triad held under a passing sung note:
counted the same way for every chord and bass note of the band, the trio rubs on 1.4% (ada), 10.9% (bob), 7.8%
(coral) and 2.8% (dmitri) of them, the tones of its own (sevenths, sixths, ninths, steps) on 0.2% to 1.5%; the
ballad's band, the song's own, on 3.8%, 10.4%, 12.4% and 3.6%. In a minor key the tune's 2 and 6 pass over the minor
triad's third and fifth in either band.

**Words misheard** (Whisper base.en, `tools/intelligibility.py`, a verse with the band and a refrain, 70 words each,
four machines, 280 words): the ballad 10.7% on the mix (30 words), the trio as each machine chose it 10.4% (29), the
trio swung 12.1% (34); the dry voice 8.9%, 7.5% and 8.2%. The trio costs the words nothing as the machines choose it;
swung, about two words in a hundred.

**Memory** (tools/render_memory.py, two threads, `MallocLargeCache=0`): H's own shape with its break, a waltz, 201 s,
1.74 GB; swung, 206 s, 1.78 GB; four verses, every part, the slowest tempo, 372 s, 2.51 to 3.06 GB over four runs on a
busy machine (the kit's sweeps and taps beside the voice: about the kit's own rate, 7.1 MB a second). In the VPS's
2100 MB about 4 minutes in one go: H's own shape (3.4 minutes) fits; a machine's longer shape (ada's and coral's, 4.1
and 4.5 minutes) is made in the browser, as other styles' long shapes are. `MEASURED` updated.

### The renders, for listening

In `renders/styles/` (ids in ids-jazz.txt; the main checkout's renders/styles has them too), each as its machine
chooses:

| render | what it is | length | id | listen for |
|---|---|---|---|---|
| jazz-ada-2026-09-27 | a waltz at 81 (a waltz's quarter 122), D major, three verses, the bridge twice, no break (its coin) | 248 s | e1f6e7d4a6bf | the piano's intro (0:01) its left hand under the tune; the first verse with the bass two to a bar and the brushes light, the refrain at 0:36 walking; the turns' Gmaj7 Em7 \| A7 (1:00, 1:53); the bridge's Em7 A7 into the last refrain |
| jazz-bob-2026-03-14 | a ballad swung at 83, D minor; the second verse with the piano alone; the piano's chorus | 183 s | 87655a873ec8 | the second verse, the singer and the piano alone (0:59); the break, the verse tune an octave up with the left hand's chords (1:45 to 2:08); the cold stop |
| jazz-coral-2026-11-02 | a waltz at 78, E♭ minor; the band joining line by line; the second verse bare, the third in stop-time; the chorus; the bridge twice; a broad ending | 272 s | 01a9bbbb7a9b | the entrances (0:13); the bare verse (1:03); stop-time (1:52); the break (2:41 to 3:06) |
| jazz-dmitri-2026-06-21 | a waltz at 81, E♭ major; the band joining line by line; one backing voice on oohs; an outro | 232 s | 0b89d37c4c47 | the first refrain's walk (0:36); the turns; the outro, the piano's tune over the brushes (3:39) |
| jazz-ada-2026-09-27-swing | ada's as a swung ballad (`--arrange feel=swing`), to hear the other feel in a major key | 254 s | 20919b894039 | the swing against the waltz above |

## Decisions for the artist (the jazz trio)

1. **On the ring or beside it.** Beside it, at chamber's place, as the four before it.
2. **The dominant: A7 or Aadd9.** The rule is symmetric: no trio tone a semitone from a sung note, either way. That
   rules out A7's G under the tune's F♯ (A13, a major seventh under the singer, the most idiomatic sound in the style),
   so H's V is mostly Aadd9, and A7 only where nothing is sung over it (a line's end, a turn). A directional rule
   (only a minor ninth under the tune rubs) would let A7 sound under the tune; the lineage choir would then sing the
   G a major seventh under the F♯ in the bridge, unless the choir's lines keep the symmetric rule.
3. **E7 (V of V) in the refrain's last line**, where the knob draws it: the one chord outside the tune's pentatonic
   world.
4. **The break** is added 0.8 of the time where the form has none (the piano's chorus on the verse tune). A form a
   person sets is kept.
5. **The feel**: a waltz 0.55, a ballad swung 0.45 (three of the four machines drew the waltz). Swung costs about two
   words in a hundred.
6. **The tempo**: the waltz at 0.85 of the song's (122 a quarter), the ballad at 0.83 (80). Slower is more of a
   ballad, and longer: a machine's long shape already passes the studio's 4 minutes.
7. **Passing chords stay inside a line** (the changes are by line, so every verse and the chord lane agree).
8. **The patterns' menus**: the trio's patterns (rootless comping, the chorus, walking, two to a bar, the swept
   brushes) are offered to the piano, the bass and the kit in every style's arrangement view, as every style's are.

# A hymn (2026-09-30, night)

The artist asked for a hymn version: an organ under everyone singing the tune in four-part harmony. What
convinced (the jig, the a cappella) was a singer delivering the folk tune straight over instruments we
synthesize well; what didn't (house, dub) needed another kind of singer or heavy sound design. A hymn is the
first kind: the song's own tune, sung plainly, by the lineage and the program's voices together (the song is
about everyone singing it), over sustained chords. The page's words claim no tradition or denomination: the
style is **hymn**, "organ, and everyone singing in parts".

## The design (as it went to review)

### Where it sits

Beside the ring (`OFF_RING["hymn"] = "chamber"`): no drums, sustained, stately and broadening, a ritardando;
a lineage that leaves it steps to chamber's neighbours (the ballad, the singer-songwriter), the folk tune
going home. Chosen by a person (`--style hymn`, the studio's style card), never drawn by a machine; the artist
decides later whether it joins the ring. Its block in songbird/style.py is its own, as house's and dub's are.

### The band: an organ, and everyone

- **The organ** (`pipeorgan`, a new instrument: songbird/synth/pipeorgan.py), or for about a third of machines a
  **harmonium** (the reed organ organ.py already plays: `swaps`, kept down a lineage). No rhythm section.
- **The singers**: the lead on the tune, and a group of at least three (`group=3`, as the a cappella: the
  lineage's voices first, then the program's own), each matched to its part by range and held to a choir's
  vibrato at synthesis (`synth.matched`, the a cappella's; the band settings' `parts: "voices"` now set for any
  style that sings as a group).

### The pipe organ (a new instrument, no new kernel)

A pipe organ is a sum of steady pipes, which is what additive synthesis does well (unlike a voice or a plucked
string): each rank a pipe per key with a fixed spectrum, and the life in the attack, the wind and the room.

- **Ranks** (each pipe its own table: a period with that rank's spectrum, the machine's voicing a little
  different pipe to pipe): an open diapason 8' (harmonics falling about 6 dB an octave, a strong second), an
  octave 4' and a fifteenth 2' (the diapason's spectrum an octave and two up), a stopped flute 8' (odd harmonics:
  the third about 15 dB down, little even), a flute 4', a mixture (II ranks, 1 1/3' and 1', breaking back an
  octave in the top two octaves). Pedal: a bourdon 16' (stopped: odd harmonics) and an octave 8'.
- **Registrations** by articulation, as organ.py names its own: `""` diapason 8' and octave 4' (the plain hymn
  sound), `flutes` stopped flute 8' and flute 4' (soft, for verses in parts and the turns), `full` diapason,
  octave, fifteenth and mixture (the giving out and the last refrain), `pedal` the pedal's bourdon and octave.
- **Each pipe** speaks the way flue pipes do: the upper harmonics first and the fundamental building over 25
  to 90 ms (longer for a bigger pipe), a little chiff (a burst of noise around the 2nd to 4th harmonic, 20 to
  40 ms, more on the flutes), wind noise under it at about -45 dB while it sounds, a few cents of tuning per
  pipe (a machine's `wear` more), and a 40 to 80 ms release. The ranks beat gently against each other (their
  pipes' tunings differ), which is an organ's chorus; no tremulant. Velocity is not touch (an organ has none):
  it is the swell box, a gentle level and a darker top as it closes.
- **Built from the kernels the harmonium already uses** (`reed._read_mix`: the attack's period cross-faded into
  the steady one, sample by sample), scipy filters and numpy; so no numba kernel is added or changed and the
  browser's translation (docs/BROWSER-RENDER.md) is as it was. The pipes' chests alternate C side and C♯ side,
  so the stem is a little wide.

### The harmony: a setting of the style's own

A hymn sets its tune with a chord to a beat or a half bar, plain triads and their first inversions, a bass
that moves by step where it can, and cadences that close the lines. The style makes **its own harmonization of
the tune** (songbird/hymn.py, `setting`), laid in `composition.form_phrases` beside a style's loop (so the
organ, the voices' chords, the MIDI file, the chord lane and karaoke all follow from one place), under every
line that has a tune; a line whose chords a person set (everywhere, or at its place) keeps theirs; a line with
no tune (H's turn) keeps the song's chords. For each phrase, a dynamic programme over its beats:

- **candidates**: the mode's own triads on 1 to 6 (and 7 where it is major, mixolydian's ♭VII), root position
  or first inversion (`IV/3`); no second inversions; no sevenths;
- **the tune's fit**: a sung note on the beat (or a beat long) that isn't a chord tone costs a lot, a passing
  eighth between beats a little, a non-chord tone a semitone from a chord tone more (the voices and the organ
  then leave that tone out there);
- **the song's own chords as the backbone**: a chord other than the song's at that beat costs a little (it is
  the same song: I, IV, V and vi where the genome has them, with passing chords and inversions between);
- **progressions**: the strong ones (down a fifth, up a step, down a third) cheap, the retrogressions (V to
  IV, V to ii) dear; changes on the strong beats rather than the weak, so mostly a half bar's harmonic rhythm,
  a beat's where the tune asks;
- **the bass**: steps cheap, leaps of a fourth or fifth fine in root position, tritones dear; parallel fifths
  and octaves between the bass and the tune dear;
- **cadences**: the phrase's last chord is the song's own (I, V, or the bridge's vi), in root position; before
  a final I, V (authentic) or IV (plagal).

The result is per bar, one to four chords (`("I", "V/3", "vi", "IV")`), the beats with the same chord merged.

### The parts (songbird/hymn.py, `parts`; the a cappella's ranges and singer matching)

The tune is the top line, as a hymn sets it (the lead's tune runs A3 to B4 in D). Under it, from the setting:

- **the bass** is the organ's pedal (the chord's bass, D2 to D3, led by step): the throat thins below E3, so
  no voice sings it; the program says so plainly ("the organ's pedal takes the bass");
- **the alto and the tenor** (the a cappella's "under" voice, between E3 and the tune), each syllable a chord
  tone, chosen together: the missing tones of the triad first (the third never doubled over a bass on the
  third), each held where the chord keeps it (common tones), else to the nearest; never a semitone from the
  tune, no parallel fifths or octaves between any two of the four, spacing within an octave between the upper
  three. Where the tune dips too low to fit two parts under it (H's pickups on A3), the alto sings with the tune
  in unison, never above it;
- **the treble** voices (every third voice, as the a cappella's) sing the tune with the lead, as most of a
  congregation does; over the **last refrain** they sing a **descant** (about two renditions in three, drawn
  by the rendition's seed): a line above the tune on the same words, a chord tone a third to an octave over it,
  moving by step and holding through the tune's moving notes, at most E5 (the a cappella's treble ceiling).

### Section by section

- **Intro** (`intro=lead`): the organ **gives out** the tune alone: the intro's lines (H's: the refrain's last
  two) in four parts with the pedal, on the `full` registration, nobody singing.
- **Verses**: the first in **unison** (everyone on the tune, the organ in parts under it), the next in
  **harmony**, and so on alternately; the organ on `""` under unison, `flutes` under parts.
- **Refrains**: everyone in harmony; the **last refrain** on `full`, with the descant when it comes.
- **Turns**: the organ alone, the turn's chords held in four parts with the pedal (`flutes`), an interlude.
- **Break, outro**: the organ gives the tune out again, as the intro.
- **Bridge and tag** (the genome's own lineage harmony): the lineage's voices sing it as always; the program's
  own voices sing the tenor under it; the organ on `flutes`.
- **The end**: the last chord held and released together (`ring`), a broad ritardando (`rit`), or the **amen**
  (the existing plagal coda: IV then I, two bars, the organ in parts, and every voice of the group on "a-men",
  6 to 5, 4 to 3, the tonic held: the gospel's amen sung by the whole group, not only the lineage's voices).

### Feel, tempo, the singer, the mix

Straight only (a hymn tune in the song's own four), at 0.66 to 0.84 of the song's tempo (centre 0.75: 72 for
H), a broader ritardando (feel `ritardando` +0.15) and a congregation's looseness (humanize x1.3). No colour
(plain triads: `colours` empty, `harmony` 0). The singer plainer (vibrato -6 cents, rd -0.03). The mix: a big
room (space +0.3, width +0.1, intimacy -0.08), the group 1 dB forward (`mix.choir`). Options: intro lead (1.0);
ending ring 0.25, rit 0.35, amen 0.4; backing `gang` (1.0: "everyone sings along", the congregation) or a
person's "" (the lead alone with the organ); no alone, no stop-time, no breakdown, no lift, no entrances.

### What changes in shared code (each only for the hymn)

- style.py: the hymn's block (`HYMN`, `OFF_RING`).
- composition.py: one line in `_looped` hands the phrases to `hymn.setting` (the same list for every other style).
- idioms.py: `backing` hands a hymn's voices to `hymn.parts`; the organ's writers (`hymn`, `givingout`) in
  `WRITERS`; the octave-down rule ("the singer's notes are nobody else's") exempts them (the organ doubles the
  singers, as a hymn's does); the amen sung by the group where the style has one; `parts: "voices"` for any
  style that sings as a group (the a cappella's as before).
- synth: the new instrument module (registered by its SPEC); public.py its memory rate.
- explain.py, takeover.py: the names and pattern labels.

### Byte for byte, memory

Every other style: the hymn's code runs only where `params.style.name == "hymn"`; checked by the goldens, the
suite, and PCM ids before and after (the seed, gospel, chamber and the a cappella for ada, the jig for bob,
coral's own). Memory: a choir voice is the heaviest part (5.7 MB a second); H's hymn is about 240 to 280 s at
72, so about 1.9 GB on two threads, under 2100; measured with tools/render_memory.py, six voices and the longest
shape, and MEASURED updated.

### Measures

pYIN on each part's stem (each note's middle against its written pitch), the voice-leading counts from the
score (parallel fifths and octaves between any two of bass, tenor, alto, tune; the share of sung part-notes
that are chord tones; any semitone against the tune), and Whisper's word errors on the mix (a unison verse, a
verse in parts and a refrain), beside the ballad's in the same run.

## What the review changed (2026-09-30, night)

A read-only Fable review of the design above, before it was built (its numbers computed from H and public.py).
Its points, and what was done:

1. **The pipe organ would have been mixed as a whistle**: `mixing.role_of` matches names by substring when the
   whole name isn't known, and "pipe" is the whistle's (a 250 Hz high-pass: no pedal). `pipeorgan` is named in the
   organ's role by its whole name (no other stem's role moves).
2. **The organ, not the voices, sets the memory**, and the length was overestimated: H's default form is 58 bars,
   193 s at 72 (220 s at the floor), not 240 to 280. The organ is measured (tools/part_memory.py: 6.8 MB a second
   for the ballad's whistle, so RATES 7.1, as the instruments measured that way are 0.3 over), made lean (one array
   the length of the song: the wind is made note by note), and the worst cases measured (below).
3. **The sung descant would have been pinned**: the tune reaches B4, and a part a third to an octave over it under
   E5 leaves one chord tone or none for 37% of H's notes, above the throat's measured B4. **The descant is the
   organ's**, over the last refrain, to A5; the treble voices sing the tune there as everywhere.
4. **The pickups**: realize gives a pickup the next line's first chord, while the organ holds the line before's
   cadence through it (H's B3 pickups fit neither I nor V). The parts read the chord the band plays at each moment
   (`ctx.chord_at`), never the melody's `chord`; the lineage's own harmony (`choir_voicing`) is left as it is. The
   setting leaves a pickup out of a line's beats, so it is harmonized by the line before's last chord. Tested: every
   sung part note a tone of the band's chord there, or the tune's own note.
5. **The harmonization fits the machinery** (a bar's chords on its beats: one, two or four in 4/4, as `chords_per_bar`
   allows; the band, `chord_times`, the MIDI file's chords and the page's lane all take four), with three changes:
   it **sets the line as it is sung** (`composition.played`: the lineage's variants, and a person's own tune for the
   line or its place, so a person's tune is harmonized, not left on the song's chords); a person's chords still win;
   and the harmonic rhythm was measured: 2.0 chord changes a bar in H (the tune's moving eighths ask for them; the
   cost of staying put changed nothing), a chord a beat or a half bar as asked.
6. **The tune on top is right for H** (the pedal is the bass, so nothing needs to go over the tune); the alto meets
   the tune in unison about 2% of the time in D, more in the low keys (A: 20%), as the review predicted. Unison
   verses are measured for words (below).
7. **The organ doubles the singers**: exempt from the octave-down rule, and its writer never uses the band's
   `voicing`, which drops any pitch being sung. The pipe organ's level was set against the harmonium on the same
   notes (equal); the words are measured with it. The 16' bourdon under a D2 pedal sounds D1, under the organ
   strip's 55 Hz high-pass: the pedal's weight is its 8'.
8. **The amen** takes the group's size only for the hymn (gospel's is as it was: its PCM id with `ending=amen` and
   three voices checked); the organ plays the coda's IV and I (the voicing runs to the song's end).
9. **Backing "" is the lead alone with the organ**, on the card too ("the singer alone with the organ"); the
   descant's draw is the same function for the score and the card; chamber stays the anchor; the words added
   (STYLE_NAMES, PLAYERS, the patterns' labels; the intro's "an instrument states the tune" is true as it stands).
10. **Byte for byte**: every shared change gated by the hymn's name (or, for `parts: "voices"`, by a group, which only
    the a cappella had); `stream("pipeorgan")` collides with no other instrument's.
11. **Measure** the words on a unison verse, a verse in parts and a refrain beside the ballad's; pYIN on each part;
    the parallels and chord tones from the score; chords a bar: below.

## As built, and measured (2026-09-30, night)

`songbird render --style hymn`, or the studio's style card ("hymn, stately"; its detail "organ, and everyone
singing in parts", then what it does). Nobody has listened; everything here is measured.

| Where | What |
|---|---|
| songbird/hymn.py | the setting (`harmonize`, `setting`), the lines (`voicing`: the tune, alto, tenor, the pedal, the organ's descant), the group's notes (`parts`), the organ's (`w_hymn`), how each section is sung (`kinds`) and registered (`registration`) |
| songbird/synth/pipeorgan.py | the pipe organ (no kernel of its own: `reed._read_mix`) |
| songbird/style.py | `HYMN`, `OFF_RING["hymn"] = "chamber"` |
| songbird/composition.py | `_looped` hands the phrases to `hymn.setting` first (the same list for any other style) |
| songbird/idioms.py | `backing` hands a hymn's voices to `hymn.parts`; `plan_style` leaves the hymn's organ its own table (no "lead" forced into its intro, no "quote" into its turns); the writers `hymn` and `givingout`, exempt from the octave-down rule; the amen sung by the hymn's whole group; `parts: "voices"` for any style with a group |
| songbird/explain.py, takeover.py, cli.py | the words: "hymn", "stately", "pipe organ", `hymn_words`, the patterns' labels, `--style hymn` |
| songbird/synth/mixing.py, public.py | `pipeorgan` mixed as an organ; its memory rate |
| tests/test_hymn.py | 14 tests (the list is in its commit) |

Beyond the design as reviewed: **the unison verses** (below, the words) are sung by the lead with two voices in
three, the lowest third resting, over the organ's flutes; the verses in parts are on the flutes too, the refrains
on the diapasons, the last refrain and the giving out on the full chorus.

**Nothing else moved.** Against the tree before (renders of the same commands, PCM ids): gospel a6676cca96b8,
chamber 8e10c6ee39a0 and the a cappella ef4e10a46970 for ada on 27 September, the jig 9922285407fe for bob on 14
March, coral's own style 803edf536f8e on 2 November, and gospel with an amen and three lineage voices for ada
b6739a4b557f (the amen's one shared line), each the same after every change; the goldens and the style tests pass;
no numba kernel added or changed (tests/test_browser_kernels.py).

**The setting.** In H, 2.0 to 2.2 chord changes a bar (a chord a beat where the tune's eighths move, a half bar or
a bar where they don't); each line closes on the song's own chord in root position; more than nine in ten of the
tune's notes struck on a beat are tones of their chord. In D major the verse's first line is I, V/3, I, I | I, ii,
V, V (the V6 a passing chord between two tonics); the refrain's "now it's by you" I, IV, I, V | V, I, I, I.

**The lines**, from the four renders below (1581 slices): parallel fifths or octaves between any two lines in 18
(1.1%), most in the low keys (in A and C, the alto and the tenor share the fifth between E3 and the tune); the
alto meets the tune in unison in 3.2% of slices; of the 4419 sung part-notes with the lead, 99.6% are tones of the
chord the organ plays there or the tune's own note (34.6% the tune: the treble voices, and the unison verses). Not
one part a semitone from the lead outside the lineage's own harmony in the bridges and the tag (`choir_voicing`, as
in every style: 41 notes in the four, coral's five voices 37 of them; coral's ballad with the same five, 49).

**In tune** (pYIN over each note's middle, on the dry stems of the four): the parts, 4435 notes, median -2.5 cents,
99.8% within 25 cents; the lead the same for ada and coral; bob's and dmitri's leads sing an octave down (their
machines' own low singers, as in every style: -1202.5 cents, so in tune an octave under), where the tune stays on
top in the treble voices and the organ.

**The words** (Whisper base.en on the mix, a verse, the next verse and the first refrain, the four machines, the
same windows as the ballad's): the hymn 15.9% misheard (70 of 440: the unison verse 16.4%, the verse in parts
15.4%, the refrain 15.9%); the ballad 15.4% (67 of 434). Before the unison verses were thinned: 36.2% on them (the
pipe organ's diapasons doubling the tune at pitch, and five voices on every word).

**Memory** (two threads, `MallocLargeCache=0`; docs/WEB-STUDIO.md's table): H's hymn of 201 s 1.18 GB with three
voices of its own, 1.20 with six, 1.21 with the lead alone; four verses, every part, six voices at 63.4 (394 s)
1.77 GB with the pipe organ, 2.46 with a harmonium (its song-long arrays). The studio's estimate is set by the
choir (5.7 MB a second) or the harmonium (6.9): a hymn fits the 2100 MB to about 5.0 minutes with the pipe organ and
4.1 with a harmonium. ada's (289 s, the pipe organ) fits; coral's (289 s, a harmonium) goes to the browser or is
refused on the server, as a long version of the a cappella is. The estimate is pessimistic for the pipe organ's
long version (2.66 against 1.77) and a short harmonium one: those two are in the table, not in MEASURED.

### The renders, for listening

In `renders/styles/` of the main checkout (gitignored; ids in ids-hymn.txt), each with its record, score and lyric
sheet beside it. Three of the four machines drew the harmonium (0.35 of machines); a fifth render is ada again with
`--seed 2`, for the pipe organ with its descant.

| render | key, tempo | what it chose | length | id |
|---|---|---|---|---|
| hymn-ada-2026-09-27 | D major, 71.8 | the pipe organ; three verses, the bridge twice; an amen | 289.2 s | 92f1b496ac4f |
| hymn-bob-2026-03-14 | D minor, 75.2 | a harmonium; two verses, an outro; a ritardando | 179.9 s | 5a7da722aee5 |
| hymn-coral-2026-11-02-five-voices | E♭ minor, 68.6 | a harmonium; five lineage voices; the organ's descant over the last refrain; an amen | 288.6 s | d67abdf5a83b |
| hymn-dmitri-2026-06-21 | E♭ major, 71.8 | a harmonium; three verses, an outro; the last chord rings | 262.0 s | 2f31bcdde0c9 |
| hymn-ada-2026-09-27-seed-2-descant | D major, 71.8 | the pipe organ with its descant; an amen | 289.2 s | 1181aa849321 |

Where to listen: the giving out (the first 14 s of each: the organ alone, the refrain's last two lines in four
parts with the pedal); the first verse in unison against the second in parts (ada: 14 s and 75 s); a turn, the
organ holding IV and V (ada, 68 s); the bridge, the lineage's harmony over the program's tenors (ada, 195 s); the
last refrain and the amen (ada, 248 s to the end; the seed-2 render for the pipe organ's descant over it; coral's
from 239 s for the harmonium's).

## Decisions for the artist (a hymn)

1. **On the ring or beside it** (at chamber's place, as built): beside it, only a person reaches it.
2. **The pipe organ or a harmonium**: a third of machines draw a harmonium (three of these four did). The pipe organ
   is the new instrument and the one the style was designed around; the harmonium is the reed organ already built.
   Either could be the only one.
3. **The unison verses** are the lead with two voices in three (the lowest rest): all of them on every word cost
   the words (Whisper 27% against 15%). Fewer voices, or all of them softer, is one number (`hymn.UNISON_ROLES`).
4. **The descant is the organ's**, about two renditions in three, by the seed (not a person's choice yet): sung, it
   would sit at D5 and E5, past where the throat is measured. Always, never, or a person's option.
5. **The giving out** is the intro as the form has it (H's: the refrain's last two lines). The whole refrain given
   out would need the intro's own length (house's way); a form with no intro starts with the singers.
6. **The organ doubles the singers' parts** at pitch, as a hymn's organ does, with the pedal under; the bass is the
   pedal's alone (no voice sings under E3).
7. **The harmonization** keeps the song's chords as its backbone and adds a chord a beat where the tune moves (I, V6,
   I; ii before V). A plainer setting (a chord a half bar at most) is one cost (`hymn.WEAK`, `STAY`).

# An old 78 (2026-09-30, night)

The song says of itself "Nobody knows who made this song." This version sounds found: a singer with a parlour
piano (or a guitar), now and then a fiddle, recorded as an acoustic-era 78. It is built the way the a cappella and
the jig convinced: the singer delivers the tune straight, over instruments the program synthesizes well (piano,
guitar, fiddle); what makes it old is the recording, a deterministic stage at the end of the mix, not a different
kind of singer. Nobody has listened; everything below is measured.

**On the page**: "old 78"; its detail "a parlour piano, recorded as a 78" (or "a guitar", and "and a fiddle" when one
comes); the mix card begins "recorded as a 78". "A 78" names a format, not a provenance: no label, artist, year or
recording is claimed anywhere (the page, the docs, the code's comments; the studio test forbids the decades).

## The design

- **Beside the ring**, by the songwriter (`OFF_RING["old78"] = "songwriter"`: a singer and one accompanist, close;
  its neighbours chamber and the lullaby). Chosen by a person (`--style old78`, the studio's style card), never
  drawn; a lineage in it keeps it or steps to the songwriter's neighbours. Whether it joins the ring is the artist's.
- **The band**: a parlour piano (1.0), a guitar in its place for about a third of machines (`swaps`, a lineage keeping
  its own), a fiddle half the time (`optional`). No bass and no drums: an acoustic horn took neither; the piano's left
  hand (the guitar's thumb) is the bass.
- **The piano's oom-pah** (`idioms.w_stride`): on the strong beats the root, then the fifth, **in the tenor**
  (from 19 semitones under the tonic: G2 to F♯3 for H in D), on the others a short chord above it under the tune
  (oom-pah-pah in a waltz); where a sung line holds its end and the chord changes, about a third of the time the
  bass walks two steps into the next root. The bridge: broken chords; the tag: one chord left to ring.
- **The tune over its own hand** (`idioms.w_parlour`): where the piano or the guitar plays the tune (an intro, the
  break, an outro), its own oom-pah (or Travis thumb) keeps going under it, a little softer. A style's table may now
  name the idiom a player takes the tune with (`"solo"`, read by `plan_style`); no other style has one, so every
  other lead plays "lead" as before. The fiddle, when it comes, leads the intro and the outro, rests in the first
  verse and the break (the piano's solo), answers the lines in fuller verses, plays a counter-line in the refrains
  and a held tone in the bridge.
- **The form**: an intro and a break always (`StyleDef.shape`), put into the machine's form after the style is
  chosen (`style.shaped`, by edits.reshape), never into a form set by hand or a person's own order; a person's
  `form.intro` and `form.break` are pinned over it, and where the shape card explains a difference it says "the old
  78 style always has one". Neither has words, so the words are the machine's as they would be.
- **Feel and tempo**: straight 0.6, a waltz 0.25 (re-barred where the song allows), swung 0.15 (a foxtrot's lilt);
  straight or swung at 0.86 to 1.0 of the song's tempo (H at 83 to 96, centre 88), a waltz 0.64 to 0.8. Sixths on I
  and IV, V7 and ii7 at 0.4, always fitted to the sung note. Options: the intro played, no bare verse, no stop-time,
  no breakdown, a lift now and then (0.1), endings ring or rit (0.45 each) or cold, backing voices in thirds 0.2.
- **Leans**: the singer a little more vibrato (+6 cents) and pressed a little (rd -0.06: projected into a horn); the
  band a little older (wear +0.1: the upright's unisons wider) and darker; the mix a dead room (space -0.25; the room
  itself stays the machine's), the singer close, no plate, no tape's wear, and the disc.

### The recording: `MixParams.disc`, a mix stage any style can have

`disc` (0 to 1, new; left out of a record while 0, so records and every child's draws are as they were) puts the
whole mix on an acoustic 78 (songbird/synth/disc.py), after the glue and the tilt. Nothing else enters the stage.
In order:

1. **Mono**: the mid, written to both channels.
2. **The horn**, each record's own (drawn): a 2nd-order high-pass at 130 to 150 Hz and a 4th-order low-pass at 4.6
   to 5.2 kHz; a honk at 450 to 700 Hz (+4 to 6 dB), a little more at 1.1 to 1.6 kHz (+2 to 4), a dip of 3 dB at 1.8
   to 2.1 kHz, the recording diaphragm at 2.4 to 3.2 kHz (+3 to 5, Q at most 3); the cutting stylus's slight
   saturation.
3. **The turntable**: the disc a little off centre, so the pitch wavers once a revolution (78.26 rpm: 1.30 Hz), 0.1
   to 0.3% at its peak (each record its own), with a second harmonic a quarter as deep; flutter 0.02% RMS.
4. **The surface**, scaled by `disc`: the groove's noise through the playback's band (150 Hz to 1 kHz above the
   horn's top), 38 LU under the music, swelling ±20% once a revolution (a worn arc, in step with the wow) and
   drifting ±10% across the side; a fine crackle (25 small ticks a second); scratches, each heard once a revolution
   for 2 to 20 turns (exactly the rotation's period, from the disc's own angle), and a pop now and then.
5. **The needle**: dropped into the lead-in groove where the mix begins in silence (a whole song's 0.6 s preroll:
   the drop at 0.05 s, the noise in over 0.15 s); at the end, where the music has died 50 dB away, the run-out
   groove's swish and click once a revolution, three seconds of it added after the song, then lifted. A section heard
   alone (it begins and ends in the music) gets neither.

Every draw is the rendition's (its seed, a stream of its own, a fixed stretch at a time); numpy, scipy and fx's
existing filters, saturation and warp: **no new numba kernel**, so the browser's translation is as it was.

## What the review changed

A read-only Fable review of the design, before it was built. Its points, and what was done:

1. **The horn would have taken the accompaniment away**: the piano's left hand sat at 65 to 123 Hz, and the
   proposed 4th-order high-pass at 200 Hz is 17 to 39 dB down there. The horn's low end is now a 2nd-order
   high-pass at 130 to 150 Hz, and the oom-pah's bass sits in the tenor (98 to 185 Hz), a parlour upright's, not a
   stride's low octaves (dropped).
2. **`--mix disc=1` would have been refused** (MixParams.parse checked keys against `to_dict`, which leaves disc out
   at 0) and **a replay would have differed** (the run-out was to be added to the score's length from params.mix,
   while `--mix` is applied after the score is made). Parse checks the fields; the score never knows about the disc:
   the stage appends its own run-out.
3. **No new clock preroll**: the lead-in is the 0.6 s every song has (0.78 of a revolution), the needle dropped only
   where the mix begins in silence, so a section preview gets no needle and no run-out.
4. **`disc` in RANGES and out of `to_dict` at 0** (a `"disc": 0.0` in every record would reseed every child's coins).
   The lean: keeping the style 1, entering it 1, leaving it 0.
5. **No special case for tape wear**: the style leans `mix.wear` to -1 (a knob that isn't handed down, so the record
   says 0 and a child in another style gets its machine's own back); `--mix wear=0.2 disc=1` still works.
6. **Not inside choose_style**: the shape is put in after the style is chosen, in `variation.choose`, only where no
   form was set by hand, and the shape card names the style rather than the machine's habit.
7. **"parlour" beside "lead"** in `LINES` (idioms and takeover), the octave-down rule now reading `LINES`, the
   takeover's played sections, its fallback idioms and the piano score's tune; labels for both idioms.
8. **No new pattern needed for the oom-pah** (w_oompah's), but the walk needs its own writer, so `stride` is the
   style's own, in its own block.
9. **The chain's numbers**: a 4th-order low-pass (kinder to the consonants), the diaphragm's peak capped at +5 dB and
   Q 3, an eccentricity drawn per record (some records audibly wobble), the noise heard through the playback's band
   (white noise to 8 kHz over music stopping at 5 kHz is the giveaway of pasted-on noise). Clicks stay under the
   limiter's notice (their peaks about 14 dB under the music's loud peaks).
10. **Memory**: the stage writes the mono back where the stereo mix lies; measured below.
11. **The mix card** says "recorded as a 78" (and no width: it's mono) and why.
12. **What `disc` between 0 and 1 means**: how worn the surface is (its noise and clicks); the horn, the mono and the
    turntable are the same at any amount. Said so in MixParams and the module.

## As built, and measured

| Where | What |
|---|---|
| songbird/synth/disc.py | the recording (new) |
| songbird/synth/mixing.py | `MixParams.disc` (RANGES, left out of `to_dict` at 0, parsed by its fields); the stage after the tilt |
| songbird/style.py | `OLD78` in a block of its own, `OFF_RING`, `StyleDef.shape`, `shaped` |
| songbird/variation.py | the style's shape after the style is chosen, where no form was set by hand |
| songbird/idioms.py, takeover.py, piano.py | `w_stride`, `w_parlour`, the `"solo"` key, `"parlour"` in `LINES`, labels |
| songbird/explain.py | "old 78", its detail by who plays, "recorded as a 78" on the mix card, the shape card's reason |
| songbird/public.py | the voice's, piano's, guitar's and fiddle's memory rates (below) |
| tools/discmeter.py | the measurements below |
| tests/test_old78.py | the stage (off, the same samples, mono, the band, the wow, the clicks a revolution apart, the needle and the run-out, a section without either) and the style (its band, the oom-pah, the shape and a person's over it, beside the ring, the disc handed down, the studio's words, grid and sound) |

**Nothing else moved.** Six renders made on main before any of this render to the same ids after it: H's seed
(9b0766353b73, the golden), lo-fi for ada on 30 September (bcce8df33538), the songwriter for ada on 27 September
(0dc4245d4a5d), gospel for bob on 14 March (3e1e9cafe3c9), the jig for coral on 2 November (6bbecafc3236), dmitri's
own on 21 June (c123ecde58e1). The goldens hold; `--replay` of bob's old 78 says "matches".

**The renders** (`renders/styles/old78-<machine>-<date>.flac` in the main checkout, gitignored, with their records,
scores and words; ids in `ids-old78.txt`):

| render | what the machine drew | tempo | length | id |
|---|---|---|---|---|
| old78-ada-2026-09-27 | the piano and the fiddle; swung; three verses, the break, the bridge twice; a broad rit | 88.0 | 254.7 s | c80fc6bcd64a |
| old78-bob-2026-03-14 | the piano alone; swung; two verses, the break, an outro; the last chord rings | 92.2 | 169.8 s | c23cd44e4683 |
| old78-coral-2026-11-02 | the piano and the fiddle; a waltz; three verses, the bridge twice, the tag; a cold stop | 64.0 | 329.1 s | bc0fdadeea47 |
| old78-dmitri-2026-06-21 | a guitar alone, Travis-picked; straight; three verses, the break, an outro; a rit | 88.0 | 239.8 s | a9993bf934b0 |

Moments to listen to: the first second of any (the needle's drop and the lead-in groove); the intro (ada's and
coral's: the fiddle over the oom-pah; bob's: the piano with the tune over its own hand); each break (the piano's solo;
dmitri's, the guitar's tune over its thumb); a held piano chord (the record's wow); the last five seconds (the run-out
groove's click once a revolution, then the needle lifted).

**What the recording measures** (tools/discmeter.py on the four renders: their mixes made again without the disc
and through it, the samples checked to be the renders' own):

- **The band the horn passed** (the music after the horn against before it, the whole song): -6 dB at 108 to 124 Hz
  and 4.7 to 5.1 kHz; -10 dB at 86 to 92 Hz and 5.5 to 5.8 kHz; 80 Hz 11 dB down, 8 kHz 22 dB, 12 kHz 43 dB. Each
  horn its own: ada's honk at 468 Hz, bob's at 688 Hz, coral's at 582 Hz, dmitri's at 565 Hz.
- **The wow**: each record's eccentricity 0.12% (dmitri) to 0.26% (coral); a steady 1 kHz tone through the same
  turntable wavers 0.21 to 0.36% at its peak (with the second harmonic and the flutter), at 1.3 Hz.
- **The surface**: 37.8 to 38.1 LU under the music; in the finished files the lead-in groove is 39 to 41 dB under the
  music's mean level, the run-out groove 32 to 35 dB (3.6 to 5.7 s of it, the music's last ring included).
- **The clicks**: 0.38 to 0.93 a second (64 to 222 a song); 66 to 82% of them heard again exactly a revolution later.
- **Loudness**: -14.0 LUFS, true peaks -1.05 to -1.6 dBTP (the limiter never chases a click); loudness range 6.6 to
  14.6 LU (ada's 14.6, 12.5 without the disc: its sparse piano verses against the full refrains).

**Words misheard** (Whisper base.en on the finished mix, every sung section, the same four machines and dates):

| | ada | bob | coral | dmitri | all |
|---|---|---|---|---|---|
| the old 78 | 18.8% | 10.3% | 25.9% | 16.4% | **18.6%** (202 of 1088) |
| the old 78 without the disc (`--mix disc=0`) | 18.1% | 6.4% | 18.6% | 8.8% | 13.7% (149) |
| the ballad | 11.7% | 17.2% | 16.9% | 16.8% | 15.4% (168) |
| lo-fi | 10.0% | 12.7% | 12.0% | 10.6% | 11.2% (122) |

So the arrangement is about as clear as the ballad's, and the recording costs about five words in a hundred (the
jig, for comparison, is at 21%). Taking the stage apart on coral and dmitri (21.4% as built): a silent surface 17.2%,
the band to 6.4 kHz 17.9%, no resonances 19.3%, no wow 19.1% (Whisper's own spread is a few points: no one part of the
recording dominates).

**Memory** (tools/render_memory.py, two threads, `MallocLargeCache=0`): H's own shape with no machine (a parlour piano
alone, a waltz), 243 s, 1.14 GB; four verses, every part, a fiddle, tempo 58, 471 s, 1.95 GB. The lightest band yet:
3.3 MB a second against the voice's own 4.7, so the voice's, piano's, guitar's and fiddle's rates are now 4.5 (every
measurement at or under its estimate and within 1.3 of it, tests/test_studio_public.py; no other band's estimate
moves but the a cappella's, a little lower). In the studio's 2100 MB an old 78 fits to 6.3 minutes; coral's 5.5 fits.

## Recommended: the recording as a choice for any style

`disc` is already any style's at the command line (`--mix disc=1`: a jig, a ballad, the songwriter on a 78), and a
record keeps it. The studio's mix card offers only the room (`edits.MIX`); offering "recorded as a 78" for every
style is one more entry there, a toggle on the mix card and its bounds. I recommend it: the recording is the part of
this style that is most its own, and a ballad found on a 78 is as true as this one. The style stays (its band, its
oom-pah and its break are what a 78 of the song would have had). For now only the old 78 sets it.

## Decisions for the artist (an old 78)

1. **On the ring or beside it**: beside the songwriter for now; on the ring it would move every lineage's future.
2. **"Recorded as a 78" for any style** in the studio's mix card (above).
3. **The surface's level**: 38 LU under the music, clicks about 0.6 a second. Quieter costs nothing but some of its
   age; a silent surface took four words in a hundred back on two machines. One number each (`disc.NOISE_DB`,
   `SCRATCHES`, `CRACKLE`), or a person's `--mix disc=0.5` for a cleaner shellac.
4. **The band**: about 140 Hz to 5 kHz. Narrower is older (and costs words); wider is an electrical recording.
5. **Its length**: a ten-inch 78 held about three minutes a side; these are 2.8 to 5.5 minutes (the machine's form,
   with the break). A shorter old 78 would mean fewer verses, which changes the words, which a style doesn't do.
6. **The guitar instead of the piano** for about a third of machines, and the fiddle half the time; or the piano
   always.
7. **An intro and a break always** (a person can still take either out).
