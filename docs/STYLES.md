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
