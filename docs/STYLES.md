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

**String band.** Old-time and bluegrass: clawhammer banjo* (bum-ditty: a note,
a brush, the thumb on the high fifth string, which is exactly the long-short-
short of H's feet) when the band is quiet, forward rolls when it drives; the
mandolin's* chop on the backbeat; a boom-chick guitar with a run on its bass
strings where the singer holds a line's last note; fiddle breaks and fills, a
counter-line in the last refrain; the upright on one and three with walk-ups.
Straight at about 117 (up to 134), sometimes a waltz. A tenor harmony on the
refrains.

**Shanty.** A sea shanty or work song: the shantyman sings the first verse
alone (or over the concertina*), then the gang (every lineage voice) joins on
the refrains; feet stamping* on one and three and hands* on two and four; a
concertina's* oom-pah; the fiddle leading the intro and taking counter-lines.
Straight or a slow six-eight. Open fifths. A big, wide room.

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
  line;
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
| intro | lead, pad, count, voice; "" as the form has it |
| alone, alone_with | which verse (1 the first) is bare, and the one instrument under it ("" a cappella) |
| stops | which verse is in stop-time |
| breakdown | the last refrain starts stripped |
| bridge | "half": a half-time bridge |
| lift | the last refrain a whole step up |
| ending | rit, cold, amen, repeat; "" the last chord rings |
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
reeds and harmonicas, strings without the fiddle's high-pass, synths, and the
percussion names on the drum strip).

## Measurements

(filled in below as the examples are rendered)

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
