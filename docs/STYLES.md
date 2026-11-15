# Styles: the song carried into other traditions

A rendition is played in a style: a tradition the song has been carried into, with a band, a feel and a way of
arranging a folk song. The genome's tune, words, chord functions and form stay the song's; a style is flesh,
re-realized every generation (principle 3). The default band is the seed's acoustic folk band (docs/BAND.md).

Thirteen styles sit on a ring that lineages travel round. Seven more sit beside it and are reached only by a
person's choice or a parent handing one down: a cappella, the jig, house, dub, a jazz trio, a hymn and an old 78.

## What a style is

A style (songbird/style.py, `STYLES`) is a coherent bundle:

- **a lineup of instruments in roles**: bass, chords, lead and counter-lines, pads, percussion, and the lineage's
  voices as backing singers;
- **idiomatic parts for each**, section by section (songbird/idioms.py): what each player does in an intro, a verse,
  a refrain, a turn, a break, the bridge and the tag, and how that changes as the band gets fuller;
- **a feel and a tempo range**: straight, swung, a shuffle, twelve-eight, half or double time, or the song re-barred
  in three (a waltz or a slow six-eight); its tempo is a share of the song's own (the seed's 96);
- **a harmony vocabulary**: the colours it may add to the genome's chords (a sixth, a seventh, an added ninth, a
  suspension, a minor iv, an open fifth), and how much;
- **leanings for the singer**, gentle ones on habits the singer already has: brightness (tilt), breathiness (rd,
  breath), vibrato depth, scoops and glides, dynamics;
- **a mix aesthetic**: offsets to how much room is heard, how close the singer stands, how wide the record is, the
  plate, a lo-fi tape's wear and a darker top, and how loud the backing voices are. Never the room itself, which is
  the machine's (principle 4);
- **its arrangement's leanings**: how it likes to start and end, whether it bares a verse, plays one in stop-time,
  breaks down before the last refrain, lifts the last refrain a step, and what its backing voices sing.

The seed's own band is the first style, the **ballad**. With no style chosen (the seed, and every record from before
styles), a rendition is exactly what it was: every song's seed score matches tests/golden/seed-scores.json and H's
seed renders to its golden id (tests/test_styles.py).

## The palette

The thirteen on the ring, in the ring's order:

**Synth folk.** An analog arpeggio ticking in sixteenths above the voice, a strummed acoustic guitar, a sub bass in
eighths, a pad, a drum machine's four on the floor (half-time in the first verse), a synth lead taking the breaks.
Straight, about 110 bpm. Added ninths and suspensions.

**Indie.** Indie folk and folk rock: a kit on the floor toms in the verses and four to the floor in the last refrain,
an electric bass in eighths, a strummed acoustic and a tremolo electric guitar, an organ underneath, a glockenspiel
ringing the refrain's strong notes two octaves up, claps in the last refrain, gang vocals. About 112 bpm. Open fifths
and added ninths.

**Gospel.** Twelve-eight at about 66. The piano plays a chord on every beat, and the last triplet of the backbeats
pushes into the next, its left hand's octaves on the strong beats; an organ holds and swells; claps and a tambourine
on two and four; the electric bass walks. The backing voices answer the singer's lines, and the song ends on a plagal
amen: two more bars, IV then I, the voices singing "a-men", moving six to five and four to three over the tonic.
Sixths, sevenths, added ninths, and a minor iv where the tune allows (under H's singing that is mostly the turns and
the amen). A big room, more plate, the voices 2 dB forward.

**Blues.** Country blues in a shuffle at about 86: the guitar's boogie on its low strings (the root under each beat,
a fifth or a sixth on the lilt), a slide and a harmonica answering the voice, a foot stomping every beat. Dominant
sevenths on I, IV and V wherever the tune allows (under H's singing, about a third of the time). Stop-time verses are
its habit. Dry and a little worn.

**Country.** A shuffle or a waltz: the pedal steel swelling in the alto register under the voice and answering
between lines, a piano's comping, a strummed guitar, brushes in the verses and a groove in the refrains, the upright
walking up into each new chord. Sixths and V7. A third above and below on the refrains; a key change up a step is its
habit.

**String band.** Old-time and bluegrass in one style. Clawhammer banjo when the band is quiet (bum-ditty: a note
struck with the nail, a brush, the thumb on the high fifth string, which is exactly the long-short-short of H's feet);
forward rolls when it drives (thumb, index, middle, thumb, index, middle, thumb, middle, the thumb coming back to the
fifth string as the banjo is tuned: A4 in D). The mandolin chops on the backbeat (the chord struck and choked by the
fretting hand); a boom-chick guitar runs on its bass strings where the singer holds a line's last note; the fiddle
takes breaks and fills and a counter-line in the last refrain; the upright plays one and three with walk-ups.
Straight at about 117 (up to 134), sometimes a waltz. A tenor harmony on the refrains.

**Shanty.** A sea shanty or work song: the shantyman sings the first verse alone (or over the concertina), then the
gang (every lineage voice) joins on the refrains; feet stamping on one and three and hands on two and four; a
concertina's oom-pah (oom-pa-pa in six-eight); the fiddle leading the intro and taking counter-lines. For about three
machines in ten the squeezebox is an accordion, its oom-pah on the Stradella bass and chord buttons (a lineage keeps
the one it had). Straight or a slow six-eight. Open fifths. A big, wide room.

**Ballad.** The seed's own band, arranged by songbird/band.py: harp, cittern, whistle, fiddle, guitar, upright bass,
frame drum and reed drone, the pattern and lead the machine and the drift choose. Chosen as a style, it also takes
the arrangement's options (a bare verse, a breakdown, entrances, a lift, a ritardando, backing voices).

**Chamber.** Chamber folk: a string section holding the harmony under the voice, a cello with a line of its own below
the tune, the piano's broken chords; no drums; rubato (the players' time looser, a broader ritardando). Straight or a
waltz. Major sevenths, added ninths, suspensions.

**Songwriter.** A Travis-picked guitar (the thumb alternating between two bass strings on every beat, the fingers on
the treble between, a pinch on the one), a harmonica in the intro, the breaks and between lines, an upright bass
coming in later. Plain (no ornaments), close and dry. Added ninths.

**Lullaby.** A music box picking the chord out high above the voice, a harp's broken chords, a celesta on the
refrains, a soft pad. A waltz or a slow six-eight where the song allows. Breathy and soft, close, with a plate.

**Ambient.** A synth pad and slow bowed swells over a held drone, a vibraphone's scattered notes; no drums;
half-time. The voice far off in a big space: the most room of any style.

**Lo-fi.** Bedroom lo-fi: an electric piano's lazy chords (the colour without the root, struck on the one and
answered on an off-beat, never the same twice), a soft swung drum machine (a boom-bap), a round sub bass, a
vibraphone now and then. Swung, about 78. Major and minor sevenths. Worn tape and a dark top (the mix's wear and
tilt).

## How styles travel

**The ring.** The styles sit on a ring, in the order above, each between two that share its instruments or its feel:
synth folk and indie (drums and synths), indie and gospel (organ, claps, a crowd), gospel and blues (sevenths, the
twelve-eight and the shuffle), blues and country, country and the string band (guitar, the two-beat bass, a fiddle
or a steel), the string band and the shanty (fiddles and feet), the shanty and the ballad (the Celtic sea songs), the
ballad and chamber (harp and strings), chamber and the songwriter (quiet acoustic), the songwriter and the lullaby,
the lullaby and ambient, ambient and lo-fi, lo-fi and synth folk (the machines). The ring runs once round a plane of
*machine* (from tradition to electronics) against *drive* (from hushed to loud).

**A machine's home.** A machine is at home somewhere on the ring: its point on that plane, read from its harvest
(newer words and younger files lean toward the machine's end, older ones toward tradition; a brisk, busy, rested
machine toward the loud styles, a slow, tired, free one toward the hushed), scattered by its identity so machines
that read alike still differ. Over 150 made-up machines every style is some machines' home, 4% to 12% each.

**A child's style.** A child starts from its parent's style and moves a tenth of the way round the ring toward its
machine's home (`PULL_STYLE`), and by the slow drift (`STYLE_SPAN`, the slow view of the drift dimension "style").
The style is the one that place falls in, held with the same stateless Schmitt trigger as the band's pattern (within
0.2 of a boundary it keeps the style the drift last sat firmly in), and never more than one step from the parent's.
A machine that gave nothing keeps its parent's style.

**The rates** (tests/test_styles.py checks them loosely):

| | |
|---|---|
| a child keeps its parent's style | about 59% of generations (over machines, dates and parents in every style) |
| otherwise | one step round the ring, toward its machine's home or where the drift leans |
| a machine singing one parent, day after day | changes style about twice a year, never back and forth within a fortnight |

So in a lineage the genre changes about two generations in five, more often than the melody's variants or the words,
while a child usually still sounds like its parent's band. With a drift of 1 moving 1.1 steps and a pull of a tenth,
a machine can't drag a lineage across the ring: the ring is walked a step at a time, like the folk process. Raising
`PULL_STYLE` (0.1) or `STYLE_SPAN` (1.1) gives more genre change. From the seed's ballad a first generation can only
reach the shanty or chamber (its neighbours); every other style is several generations away.

**What a style brings when chosen** (`variation.choose_style`, the last decision, once the form, the choir and every
number are chosen):

- the arrangement's options, drawn afresh for each rendition from the style's leanings and turned slowly by the
  season's drift (the dimension "arrange"), fixed by the machine and the parent, so renders a minute apart agree; the
  feel is kept from the parent three times in five when the style is;
- the lineup, as loud as the style has each, each machine's balance its own way (and the slow balance drift), pulled
  from the parent's gains where the parent had the instrument;
- the tempo: the parent's tempo as a share of its style's centre, pulled toward the machine's pace as always, taken as
  that share of the new style's centre and held to its range;
- the leans on the band (density, brightness, wear, ornament, arc), the performance (a chamber group's looser time
  and broader ritardando), the singer and the mix, each applied so it never compounds: a child takes back the share
  of its parent's style's lean it inherited, so generations in one style settle at exactly the style's lean.

The feel chooses the grid, and the band's swing is only how much within a swung one, so a twelve-eight can't decay to
a shuffle down a lineage.

`songbird render --style NAME` plays a rendition in a style of your choosing (still the machine's in everything else)
and `--arrange FIELD=VALUE` sets any of its options.

## Beside the ring

A machine's home is an angle on the ring's plane, one slot a style, so adding a style to the ring would move every
slot and change the style every existing lineage steps into next. The styles beside the ring (`OFF_RING`) each sit at
a ring style's place, their anchor:

| style | anchor | why |
|---|---|---|
| a cappella | shanty | the gang, the crowd singing |
| jig | ballad | the seed's whistle, fiddle, frame drum and drone |
| house | synth folk | the machines' end, the drum machine and the synths |
| dub | lo-fi | slow, worn, the bass and the room |
| hymn | chamber | no drums, sustained, stately |
| jazz trio | chamber | the piano, the waltz, the sevenths |
| old 78 | songwriter | a singer and one accompanist, close |

A person chooses one (`--style`, the studio's style card, which lists them after the ring's), or a parent hands one
down. A child of such a parent is placed as if its parent were at the anchor: where it would keep the anchor's style
it keeps its parent's, and where the drift moves it a step it steps to the anchor's neighbour. So a lineage can leave
these styles but never wanders into one. `place()` and `neighbours()` map an off-ring style to its anchor first.

Dub and the jazz trio are hidden from the studio's picker (`style.HIDDEN`, `style.offered`): the artist heard dub as
not enough of a transformation, and the folk singer's straight delivery as a poor fit over a jazz trio. A record, a
draft or `--style` still plays them, and a version already in one still shows its name.

## The arrangement's options

Any style can take them (the ballad too, when it is chosen as a style); each style leans toward some
(`StyleDef.options`):

- **how it starts**: an instrument states the tune (the lead, as the seed does), or a pad swells in alone, where the
  form has an intro. Where it doesn't, a count-in (four clicks on the sticks, the hands or a muted chop, a bar before
  the song) or the singer alone, the band coming in on the second line. Or a quote: the lead instrument alone, over
  the drone, plays a line of an older song the genome names (`quote` in the genome, its tune on the song's grid; H's
  is the chorus of Daisy Bell, 1892, the first song a computer sang, at Bell Labs in 1961) in bars cleared before the
  song as a count-in's are. A genome with no quote starts as the form has it. The jig adds a slow air (below);
- **a bare verse**: one verse sung a cappella, or over one instrument (a shanty's first; for others a later one);
- **stop-time**: a verse where everyone keeping time hits each bar's one together and leaves the words bare (a line
  or a fill may go on);
- **a breakdown**: the last refrain starts with only the rhythm section and the rest of the band comes back at its
  third line;
- **a half-time bridge** (styles with drums; a style may set its odds, and house and dub never take one: a
  half-time one drop is a crawl);
- **entrances**: the first verse builds, the chords first, then the bass, the drums, the rest, a line at a time;
- **a lift**: the last refrain (and the tag after it) a whole step up, the singer, the voices and the band together
  (a truck driver's modulation). It is a transposition after the arrangement, so the harp's and guitar's sympathetic
  strings stay tuned to the old key;
- **the ending**: the last chord ringing (the seed's), a broad ritardando, a cold stop (the last chord short, 0.9 s of
  ring), the last line sung again, a plagal amen, or a dub version after the song (below);
- **a drop**: house's breakdown and drop after a refrain (below);
- **backing voices**: the gang on the tune (unison, the low voices an octave down), a harmony above and below (the
  chord tones a third or more from the tune, as the lineage choir sings in the bridge), answers at the ends of lines
  (the line's last word again while the singer holds it), or oohs on the chords under the singer. Only the lineage's
  own voices, as many as the lineage has (params.choir): at the first generation a shanty's gang is one sailor, by
  the sixth the crew has arrived. Never where the genome gives the lineage its own harmony (the bridge and the tag);
  fills keep off the lines the voices answer. The a cappella and the hymn add the program's own voices to make a
  group (below).

## The harmony

The genome's chord functions persist: I is always I. A style's colours are chosen per chord, as often as its harmony
knob says, and then placed only where they sit with the tune:

- a colour is dropped for a moment if it would be a minor second (or major seventh) from any note sung then;
- where it lands in a voicing, it may not be a major second, minor seventh or tritone within an octave of a note sung
  on a strong beat (a foot's start) or held a beat or more; a ninth or more away is an ordinary extension (an added
  ninth under the tune). A guitar leaves such a string unplayed, a pad or a piano moves the tone an octave down or
  plays the third;
- chords never sit on the pitch being sung (an octave down instead), and a banjo's fifth string and a guitar's bass
  run are stopped where they would rub.

H's tune is major pentatonic and never sings 4 or 7, so most of what is refused is a maj7 under a sung tonic, a b7
under a sung sixth, or an added ninth right against a sung third. tests/test_styles.py plays seven styles with the
harmony knob at 1 and checks every added tone against every sung note.

## Feels, and the song in three

Swing is the band's own for the seed and the ballad; for another style its feel decides: straight (a machine's own
lilt, at most 0.25), swing (0.35 to 0.7), a shuffle and twelve-eight (a full triplet lilt, so the grid's quarter-beats
land on triplets and the band plays twelve-eight), half and double time (the drums and bass), all counted from the
bar line (realize's Clock).

A waltz or a slow six-eight re-bars the song in three. H's feet are strong-weak-weak on units 0, 2 and 3 of four; the
Clock moves them to three even pulses, so each foot becomes a bar of a waltz (or a dotted beat of six-eight) and every
stressed syllable lands on a downbeat, with the tune's pitches and order untouched ("Who | MADE this | SONG? |
NO-bo-dy | KNOWS"). It is offered only where every sung note of a song starts on those positions (H's do;
tests/test_styles.py checks every syllable against the waltz's beats). Tempo keeps meaning the song's beats a minute,
so a waltz's quarter is 1.5 times it and, at the same tempo, a waltz is as long as the song; waltz styles have their
own ranges.

## The record, for the studio

`Params.style` (songbird/style.py `Style`), each field off by default:

| field | what it is |
|---|---|
| name | the style (`STYLES`); "" the seed's own arrangement, exactly |
| lineage | the styles this rendition's line was sung in, one a generation, oldest first, this one last (up to 16) |
| feel | straight, swing, shuffle, twelve, half, double, waltz, six; "" the style's own |
| harmony | 0..1, how much of the style's vocabulary colours the chords |
| intro | lead, pad, count, voice, quote, air; "" as the form has it |
| alone, alone_with | which verse (1 the first) is bare, and the one instrument under it ("" a cappella) |
| stops | which verse is in stop-time |
| breakdown | the last refrain starts stripped |
| bridge | "half": a half-time bridge |
| lift | the last refrain a whole step up |
| ending | rit, cold, amen, repeat, version; "" the last chord rings |
| coda | quote: the lead alone plays the genome's quote's first notes over the last chord as it rings two bars on (H: Daisy, Daisy); "" none |
| motif | bridge: the lead instrument (H: the whistle) plays the quote's first notes over the bridge's third phrase, the fiddle's pad resting, where they sit in the chords (H: so mi over I, do over vi, so, over V); chance: about a third of renditions, by seed, and every drawn ballad's default where the song names a quote unless a person or the version handed down chose; "" none. Only where it fits the version, whole or not at all: every note in the lead's reach above the singers (REGISTER), the lead with no line of its own in the bridge and not entering late there (a pad of its own rests). Played about 3 dB under the intro's statement of the tune (8.6 dB under went unnoticed) |
| entrances | the first verse builds line by line |
| backing, voices | what the backing voices sing (oohs, echo, thirds, gang, hum) and how many sang it |
| drop | house: which refrain the breakdown and drop follow; 0 none |
| loop | house and dub: the rendition's chord loop by name, "song" for the song's own chords, "" the best fit |
| dissolve | dub: the refrain after which the song dissolves into its version; 0 none |

`Band.lineup` (songbird/band.py): instrument -> gain, 0..2, for whoever plays when a style sets the band; empty for
the seed's eight fixed gains. `MixParams.plate` (0..2) scales the singers' plate; `MixParams.disc` (0..1) records the
mix as a 78 (below, "An old 78"). All load from older records (missing: the seed's). The seed's own style, an empty
lineup, and `drop`, `loop`, `dissolve` and `disc` while off leave no trace in a record, so a parent's digest (and the
rendition seed its child draws) is unchanged by them. Old names are read as current ones (`style.RENAMED`: the intro
"notes" as "lead", the style "celtic" as "jig").

## Instruments

songbird/synth/instruments.py has a registry: any module under songbird/synth/ that exposes a `SPEC` and a `render()`
adds its instruments by name, placed and levelled by its SPEC and scaled by the lineup's gain. The seed's eight keep
their exact code path. Every instrument a style names has a module; an instrument named in `KNOWN` without one would
be played by a stand-in from the eight under its own name, place and level. The mix finds each stem's channel strip by
its name (keys, organ, reeds and harmonicas, strings without the fiddle's high-pass, synths, the percussion names on
the drum strip, and a kit, a banjo and a mandolin on their own; docs/INSTRUMENTS-B.md, For the mix). The pipe organ
is named in the organ's role by its whole name, since "pipe" alone is the whistle's.

## Measurements

The ring's styles, measured with tools/stylemeter.py on one made-up machine (ada, 2026-09-27), a verse and a refrain
in each style, with the instrument modules and the learned voice. Whisper's words misheard on the finished mix
(`--wer`):

| Style | Words misheard |
|---|---|
| ballad | 1.4% |
| lofi | 1.4% |
| blues | 5.7% |
| songwriter | 5.7% |
| gospel | 8.6% |
| stringband | 10.0% |
| lullaby | 10.0% |
| chamber | 10.0% |
| shanty | 11.4% |
| ambient | 11.4% |
| synthfolk | 12.7% |
| country | 15.7% |
| indie | 17.7% |

Every master is -14.0 LUFS with true peak at -1.1 dBTP or below. Indie and country, with the kit and electric guitar
under the voice, are the least clear. Whisper is a jumpy judge on about 70 words: single runs differ by several
points. These numbers, and the measurements in each style's section below, were taken when the styles were built
(late September 2026); the singer has changed since.

`tools/styles_examples.sh` renders a genre tour (one machine, one day, every style, a verse and a refrain), four full
songs, and a lineage of six generations into renders/production/styles/.

# Two more: a cappella and the jig

Two traditions the song was always close to: singing with nothing but voices (the song's idea, communal singing),
and the tune played in unison by whistle and fiddle, round twice, as a session plays it. Both sit beside the ring
("Beside the ring", above).

## A cappella (`acappella`)

**The band is the choir.** The lead sings the tune (as in shape-note singing, the tune is the tenor, the middle of the
sound, with a part above it) and a **group** sings the rest: the lineage's own voices first (params.choir), then the
program's harmony voices (the stand-ins `lineage_voices()` draws), at least three parts and up to six (`group`,
`Style.voices`; the parts read the larger of the two and the choir). Communal singing needs a group, so the program's
voices fill it even at the first generation, where every other style's backing is only the lineage's own. No
instruments. Feet stomp in about a third of renditions and hands clap in about a quarter, in the refrains. A player
that doesn't come sits in the lineup at gain 0 (`StyleDef.optional`: part -> the chance it plays, drawn per machine
and parent, a lineage keeping what it had), so the lineup is never empty (empty is the seed's eight) and the studio
can bring one in.

**The parts** (`idioms.shape_parts`), each voice a role in turn, homophonic, every voice on the lead's syllables:

- the **treble**: a fourth, fifth or octave over the tune (the sound of shape-note singing when the tenor has the
  tune), at most E5 (the throat is measured to B4);
- the **under** voice: the chord's root where it fits between the throat's floor (theory.FLOOR, E3) and the tune,
  else a chord tone there;
- the **alto**: between, or over the tune where there is no room under it;
- the third is allowed about a third of the time (`THIRD`), never at a line's cadence, so the sound is open without
  being organum; every part is led from its last note, parallel fifths allowed, never on the tune's note or a
  semitone from it.

There is no true bass. The lead's lowest note is about a fourth under the tonic, and the learned throat thins below
E3, so under H's A3 there is no room for one; a bass waits for a throat that sings there.

**Section by section:**

- *where a band would play the tune* (an intro, a break, an outro): the lead hums it on "oo" and the group hums the
  chords under it (the under voice and the alto on each chord's root and fifth; the treble rests, so the tune stays
  the top line and the treble's entrance at the refrain is heard). Or (`intro=pad`) the group's chords swell in alone
  on "oo" and the lead comes in with the words. The lead never sings shape-note syllables (fa, sol, la, mi): sung by
  this throat they are heard as gibberish;
- *the first verse*: often the lead alone, lined out;
- *the verses*: the lead with the group humming (`hum`: an open-fifth drone on "oo"), on "oo"s (`oohs`), or joining
  the lead on each line's last word, in parts (`echo`); in the first verse the voices come in a line apart (the
  under voice, then the alto, then the treble: `entrances`);
- *the refrains*: everyone on the words, each part on its own notes; the last refrain everyone;
- *a turn*: its chords held by everyone on "oo";
- *the bridge and the tag*: the lineage's harmony, with the program's voices under it;
- *the end*: the final chord held, the lead with it (`ring`), or the last line again;
- a held chord is never in unison with a note of the tune it sits under.

**Who sings which part.** A lineage stand-in drawn "low" sings everything an octave down (VoiceParams.shift -12), so a
treble part would land under the tune. In an a cappella score the singers are matched to the parts by range at
synthesis (`synth.matched`): the lowest voices (a low stand-in, the longest tract) to the lowest part, each at the
written pitch. The stand-ins' vibrato (15 to 40 cents), scoops and slow wander would churn against open fifths held a
whole song, so the group's singers are held to a choir's (vibrato at most 14 cents, a later onset, scoops at most 0.2).

**Feel, tempo, mix.** Straight (0.7) or a waltz (0.3), brisk as shape-note singing is: straight at 0.85 to 1.1 of the
song's tempo (centre 0.95), a waltz at 0.6 to 0.76. The harmony vocabulary is the open fifth. The singer leans plainer
(less vibrato, pressed a little: rd -0.05); the mix a big room (space +0.25, plate +0.2, width +0.15) with the group
1.5 dB forward of where a choir sits (`mix.choir`). Options: the intro hummed (`lead`, 0.65) or the chords swelling in
(`pad`, 0.35); verse 1 lined out (0.6); entrances (0.6); the backing hum (0.4), oohs (0.35) or echo (0.25); the ending
ring (0.6), the last line again (0.25) or broad (0.15); no breakdown, no lift, no stop-time.

**The stomps.** Each stomp's sole slap rises over 1.5 to 4 ms through 400 Hz to 2.5 kHz and a 3 kHz low-pass
(`hand._slap`), so it doesn't click; the same stomps play in the shanty and the blues.

**Measured** (ada, the whole song with its stems; pYIN over each note's middle): every part in tune, the median
within 0.1 cent, 98% (the lead) to 99% (the parts) of notes within 25 cents. Where the parts sing with the lead:
fifths 20%, fourths 16%, octaves 14%, thirds 27%, sixths 12%, seconds and sevenths 10%. Words misheard (Whisper base.en
on the mix, a verse that isn't bare and a refrain, four machines): the verse hummed 14.2%, the line ends joined 17.3%,
the ballad in the same run 10.7%; the joined last words arrive from four voices a hair apart. Memory (tools/
render_memory.py, two threads, `MallocLargeCache=0`): a waltz with three voices, 225 s, 1.54 GB; six lineage voices,
1.53 GB; four verses, every part, six voices, tempo 55, 450 s, 2.56 GB. The group's bus sums the voices as they come,
so the peak doesn't grow with the group. In the studio's 2100 MB, about five minutes in one go.

## The jig (`jig`)

The page says "jig, in six-eight" and claims no tradition: the frame drum is a frame drum played with a tipper, the
drone a reed drone, the guitar an open-tuned guitar (DADGAD is in the style's detail as a tuning), the slow air "the
tune slow and free to begin, the lead alone", the singer's ornaments "turns".

**The lineup**: the whistle and the fiddle (the tune), the frame drum tipped, a guitar in DADGAD, and by chance a
concertina (0.45, on the tune with the others) and a reed drone (0.35, the tonic and fifth under the tunes and the
bridge).

**Always a jig.** Six-eight, the song re-barred (H's long-short-short feet are a jig's dotted beat), at 1.35 to 1.6 of
the song's tempo (centre 1.5: a dotted beat at about 72 for H, a sung jig rather than a dance's). A song that can't be
re-barred keeps its beats and plays each in three: its own time where it is already in six-eight, twelve-eight
otherwise (a dotted beat at 0.7 to 0.8 of the song's tempo); `feels_for` says so for a style whose only feel is
six-eight.

**The tunes as a set.** Where nobody sings (the intro, the turns, an outro), everyone on the tune plays it together in
unison, each in its octave (the whistle an octave up, the fiddle and the concertina where they sit), a heterophony:
the whistle cuts and rolls, the fiddle slides and slurs, the concertina plays it plain. A played section of four bars
or less (`SET_BARS`) goes **round twice** (`StyleDef.rounds`: the intro's four bars become eight, a turn's two four,
the turn's line quoted both times, the same line with different ornaments): the first time the lead with the guitar,
the second the others join and the drum comes in. The break (eight bars) goes round once. Round twice is the style's
length inside `takeover.phrase_plan`, so the layout, the chord times, karaoke and the piano score agree; a person's
`arrange.<section>.bars` wins over it.

**Or a slow air** (`intro=air`, 0.25 of intros): the intro's first time round played out of time by the lead alone
(the whistle or the fiddle), over the drone if it came, 1.7 times as slow and each line broadening toward its end
(`AIR_SLOW`, `AIR_BROADEN`); the second time round in time, the band joining, then the singer. The clock
(realize.Clock) gets a stretched span at the start for it.

**The players**: the guitar's DADGAD strum (`dadgad`: the open strings ringing the tonic and fifth under every chord,
fretted to the chord tones within four frets, an open string that would rub a chord tone or the sung note fretted to
the nearest chord tone, down-down-up per dotted beat; an open D tuning with a capo up to six frets or tuned down up to
five, its sus4 on V fitted away from a sung third); the frame drum (`tipped`: down-up-down on each dotted beat, the
bar's first stroke open and low, the others the tipper; `tipped-light` in the verses). In the verses the fiddle and the
whistle take turns at fills between the lines, sitting out the first; in the refrains the fiddle's counter-line and
the whistle's descant in the last; in the bridge the fiddle's held tone and the drone.

**The singer** keeps the song, with a few turns of its own: on some long stressed notes the lineage hasn't
ornamented, a grace, a mordent or a turn from the song's ornament vocabulary (variants.candidates: always a degree of
the song's scale, on a note long enough to hold it), about one note in eight, fixed by the rendition's seed and not
handed down. Plainer vibrato (-8 cents), a little pressed.

**Its leans**: the band a little brighter and much more ornamented (ornament +0.3: cuts and rolls come twice as
often), wear +0.05; a pub's room rather than a hall (space -0.1, intimacy +0.08). Options: intro lead (0.75) or air
(0.25), verse 1 alone 0.1, entrances 0.3, a lift 0.1, endings ring 0.4, cold 0.35, rit 0.25; backing voices thirds
(0.3) or none; no stop-time, no breakdown. Its colours: sus2 and the open fifth.

**Measured** from four machines' scores: tempo 137 to 150 (a dotted beat at 69 to 75); the drum's strokes a median
1.01 to 1.02 eighths apart, about a fifth of them open; the whistle cuts 12 to 26 of its notes, the fiddle 5 to 18;
the singer's turns on 6 to 15 notes of 250 to 387. Words misheard 21.1% beside the ballad's 10.7%: a jig sings the song
half as fast again. Its tempo floor (1.35 of the song's) is one number. Memory: H's jig, 112 s, 0.99 GB; four verses,
every part, tempo 130, 213 s, 1.56 GB.

## A cappella and the jig, revised

The names and the sung syllables follow the artist's listening. Shape-note syllables before the words were heard as
gibberish, so the a cappella hums where a band would play. "A Celtic session" claimed an authenticity the program
doesn't have, so the style is named for what it plays; a jig-named style can't honestly carry a reel, so it has none.
Records and edits from before are read by their current names (`style.RENAMED`: the intro "notes" as "lead", "celtic"
as "jig", the drum's `bodhran` and `bodhran-light` as `tipped` and `tipped-light`); a record made as a reel keeps its
recorded feel (double time) when replayed.

# House and dub

A dance style, and dub, because Jamaican version culture is this song's idea: the B-side that re-cuts the same song,
the riddim sung over again by the next singer. A version is a song passed on and remade. Both sit beside the ring.
House draws its loop, form and hook, and dub its dissolving version, from "House and dub, again" below; this part is
their bands and the desk.

## House (122 to 126)

| | |
|---|---|
| lineup | drum machine (a **909**), synth bass, piano stabs (an **organ** for about three machines in ten: `swaps`), synth pad, the arpeggio as a **pluck** |
| feel, tempo | straight; 1.27 to 1.31 of the song's (H: 122 to 126, centre 124) |
| harmony | added ninths, sixths, a seventh on V and vi, a suspension (0.6), over its loop |
| leads | the piano (the tune in the intro, the break and the outro), then the pluck |

The patterns:

- **drum machine**: `floor` (the kick on every beat, an open hat on every off-beat, a soft closed hat on the
  sixteenths between: the verse groove), `house` (floor and a clap on two and four, the closed hats a little firmer:
  the refrain), `drop` (house and the ride on every beat, a crash on the first one). The soft hats sit over the
  velocity below which a sparse band thins them, so the machine keeps its pattern. A fill into a bigger section is the
  groove's (`w_groove`); a clap and snare roll into the drop is the transition's.
- **synth bass**: `offbeat` (the root on every off-beat, short; an octave up on the last off-beat of a bar now and
  then, a step into a new chord) in the verses, `octave` (the root on the beat's second sixteenth and its octave on
  the off-beat, the disco-house octave bass) in the refrains and the hook bars, `rolling` (three sixteenths after each
  kick: the root, the root, the octave or the fifth) in the drop.
- **piano / organ**: `stab` (the chord, its colour, short, on the off-beats of a bar, or a 3-3-2 across it; above the
  bass and under the tune), voicing the loop's sevenths. The organ plays it on its percussive registration.
- **pad**: held chords (`pad`), pumping.
- **pluck** (the arpeggio's pluck patch): a one-bar figure of chord tones on the sixteenths' off-beats above the tune.

Its **program sound** (`StyleDef.sound`, under a person's): the drum machine on its 909 kit; a sidechain on the pad
(classic, 8 dB), the synth bass, the stabs and the pluck (subtle, 4 dB), all keyed on the kick, so where the kick drops
out nothing pumps. A person's `sound.*` and `mix.<player>.*` edits sit over it path by path; a pump's preset `off`
takes it away, and `/api/sound` shows it as the program's.

**The breakdown and the drop** (`Style.drop`: which refrain the breakdown follows, 0 none; house draws it 0.8 of the
time; any style can take it with `--arrange drop=2`). After the second refrain (the first where the song has two),
every section before the next refrain is the breakdown: the drums, the bass, the stabs and the pluck drop out and the
singer (and in H's bridge the lineage) is left with the pad. Where it holds a section nobody sings, the lead plays the
tune there over the pad. Over the breakdown the band's low-pass opens from 350 Hz to wide open (the sweep `open`), a
riser plays over its last two bars and a snare and clap roll over its last one or two. The drop's refrain follows with
the ride, the rolling bass and everyone at full weight (its form in "House and dub, again"). A drop needs a refrain
after it, so house never draws the last-refrain breakdown, and the page words the two apart ("the breakdown before the
drop"). The style's transitions are made in the score under a person's, since a breakdown's sweep runs longer than a
person's transition can.

**The filtered intro**: the band's low-pass opens across the intro (the same `open` sweep) into the first verse.

Its other habits: a lift now and then (0.15), entrances (0.5), endings cold or ringing, backing voices echoing the
lines' ends or oohs, never the last line again (the hook is its tag), no half-time bridge. The singer: a little less
vibrato, a plate. The mix a little drier, wider, the plate up.

## Dub (70 to 78)

| | |
|---|---|
| lineup | the kit, an electric bass, an electric guitar (the skank), the organ (the bubble), a **melodica** |
| feel, tempo | swung (0.65) or straight; 0.73 to 0.81 of the song's (H: 70 to 78, centre 75). A 140 half-time is the same pulse at 70: the singer's quarter is the tempo |
| harmony | triads, a minor seventh on vi, ii and iii (0.2): roots reggae keeps its chords plain |
| leads | the melodica (the tune in the intro and the breaks, answers between the lines), then the organ |

The patterns:

- **kit**: `onedrop` (nothing on the one; the kick and a cross-stick together on three; the closed hat on the eighths,
  an open hat on the last off-beat of a bar now and then), `steppers` (the kick on every beat, a rim shot on three: the
  last refrain). A fill of a few rim shots and toms into a bigger section.
- **bass**: `dubbass`, the riddim: the root long on the one, a chord tone on the off-beat of two, nothing on three, the
  octave or fifth on its off-beat and a step into the next chord on four; low, round, with space.
- **guitar**: `skank`, a three-note chord on the top strings struck and choked at once on every off-beat, up strokes;
  the electric's `mute` for the choke.
- **organ**: `bubble`, the organ shuffle: per beat the chord low on its second sixteenth, high on the off-beat (with
  the skank), low again on its last sixteenth, soft and short. With dub's swing the bubble and the skank shuffle, as
  reggae's do.
- **melodica**: `fills` (the answers between lines) and the tune where nobody sings.

The **melodica** (songbird/synth/melodica.py): free reeds blown through a tube, one reed a key (no bends, chromatic,
chords possible), on the harmonica's reed tables and read kernel (reed.tables, reed._read_mix: no new kernel), a
plastic case's hollow body, breath noise strongest as each note is tongued; placed and levelled as a lead. The
harmonica's player is a Richter harp's (holes, bends, a harp's key per part), so the melodica is a small module of its
own on the harmonica's pieces.

**The mixing desk as an instrument** (`StyleDef.desk`, `DESK`; each choice from a part's own random stream, so a render
replays exactly):

- **drop-outs**: bar by bar, in the sections the desk works (the intro, the turns, the break, the version most; a
  verse or a refrain now and then, never its first bar), the band cut to the drums and bass alone, the drums alone, or
  the drums out for a bar, and back. Drop-outs are the score's (the notes left out), so the stems, the piano score, the
  browser and a replay agree;
- **echo throws**: a tape echo (a dotted eighth, its repeats fed back at 0.6, each darker and a little saturated, as a
  Space Echo's tape and heads do) that the engineer sends a moment to: the last word of about a third of the singer's
  lines (more in the refrains), a cross-stick or snare hit before a drop-out or a section's end, the skank's last chop
  before the band drops out;
- **spring splashes**: a snare hit (every eight bars or so, and at the version's start) sent hard into a spring tank
  (amp.spring_ir, the springs the electric's amp has);
- **the version** (`ending: version`, 0.75 of dub's renditions; any style can take it): after the last line the band
  plays the last refrain's chords again, eight bars (`VERSION_BARS`), nobody singing, the singer's last line thrown
  into the echo, the riddim steady, the skank, the bubble and the melodica dropping in and out, a splash at its start,
  the song ending on the echo's tail. The version is a section of its own (role "version"): it holds its tempo and
  slows through its last two bars only (`style.slowing`), and its last chord rings six seconds so its echoes aren't
  cut. A key lift carries it. In a style without a desk the version gets `VERSION_DESK` (drop-outs in the version and
  the last line thrown).

Throws and splashes are made in the mix (songbird/synth/dub.py, numpy and scipy only: the echo's feedback a delay's
length at a time, the spring by oa.convolve; no new kernel), each over its window and tail only, from the score's
`sound["throws"]`. Each throw is cut from its part's channel (the singer's from its bus) and added to the band's bus and
its send to the room. The returns' levels (`DESK`: level 2, the singer's 0.5, the spring 3) were set by measurement.
A preview of a section keeps the throws whose windows it plays. Dub's mix otherwise: a little tape wear, a darker top,
more room, the plate.

**What the shared code offers every style**: `StyleDef.sound` and `.desk` (empty for every other style, so `produce()`
returns what it was given), `Style.drop` and the ending `version`, the sweep `open` (also for a person's transitions),
and the patterns, each with a page label, which the arrangement grid offers to those players in every style.

**Measured** (the first house and dub band, before the loop and the version): house's kick on every beat of every
refrain, claps on two and four only, the ride only in the drop, the synth bass on every off-beat of the refrains and on
no beat; through the breakdown the mix's spectral centroid rising from about 450 Hz to 5 to 6 kHz as the filter opens.
Dub's kick only on three, the skank on the off-beats and never on a beat, the bass on the one and the fourth beat and
never on two or three; 17 to 26 throws and 5 to 14 splashes a song, the first repeat at the echo's time (0.60 s at 75), a
median 9 to 11 dB under the mix around it, each next repeat 4.5 dB under the last. The voice stands 7.7 to 10.9 dB over
house's band and 7.5 to 10.0 over dub's (tools/stylemeter.py); true peaks -1.9 dBTP.

## House and dub, again: the loop, the form, the hook and the version

Keeping the folk song's form, harmony and phrasing and changing only the band did not make either recognizable. A
genre lives as much in its harmony, its form and what it does with a voice: house is a loop, a groove that builds and
drops, and a hook chopped out of a vocal; dub is a version, the song taken apart on the desk. These are what make both
reinterpretations while the song stays recognizable (its hook, its tune in pieces, its words where sung).

**What a style may bring** (all empty for every other style):

- `StyleDef.loops`: chord loops by name, each a list of scale degrees a bar (`(6, 4)`: vi, then IV, round again),
  with whether they are voiced as sevenths. `StyleDef.looped` says which sections take the loop (house: every section
  but the bridge; dub: the version).
- `Style.loop`: the rendition's loop (a name of the style's, "song" for the song's own chords, "" in records from
  before: the best fit).
- `StyleDef.form`: the style's section lengths and the bars it plays after a sung section, laid out by
  `takeover.phrase_plan` as the jig's rounds are; a person's `arrange.*.bars` over it, and a person's entry for a
  section that doesn't set its bars keeps the style's length. A turn's length stays the style's.
- `StyleDef.hook`: a vocal chop: which words of the song, the rhythms it may take, where it sings.
- `Style.dissolve` (dub): the refrain after which the song dissolves into its version; 0 none.

### The loop, and fitting it to the tune

A loop is spelled per rendition from its degrees in the rendition's mode (`style.loop_symbols`: `vim7`, `IVmaj7`,
`V7`; in aeolian `VImaj7`, `ivm7`), so it follows the key and mode as the song's own chords do. A major tonic is voiced
`Iadd9` rather than `Imaj7`, since the maj7's leading tone would sit a semitone under the singer's home note.

Each candidate is laid under every sung line of the verse and the refrain (the loop restarts with each section). Each
sung note that is a semitone from its chord's triad counts its length, a long or strong note (a beat or more, or on a
foot) fully and a passing one a third; a sung note on the chord's seventh counts as a chord tone. A loop fits if it
scores no more than the song's own chords plus the style's slack (two beats for house, four for dub: a riddim sits
under fragments). The rendition draws one of the fitting loops (`fitting_loops`), and where none fits it plays the
song's own chords. For H in D major (clashing beats of the 101 H sings in a verse and a refrain): vamp 0.5, lift 0,
home 0.5, deep 1.3, royal 2.7 fit; pop 8.5 and minor 12.2 don't. In aeolian house has two that fit (vamp and pop) and
dub none.

| house's loops | chords (D major) |
|---|---|
| vamp: vi7, IVmaj7 | Bm7, Gmaj7 (the deep-house two-chord vamp) |
| lift: IVmaj7, I | Gmaj7, Dadd9 |
| home: I, IVmaj7 | Dadd9, Gmaj7 |
| deep: ii7, V7, I, vi7 | Em7, A7, Dadd9, Bm7 |
| royal: IVmaj7, V7, iii7, vi7 | Gmaj7, A7, F♯m7, Bm7 |
| pop: vi7, IVmaj7, I, V | Bm7, Gmaj7, D, A |
| minor: VII, iv7, i7, v7 | (aeolian) |

Dub's riddims are triads: roots (I, IV), minor (vi, IV), plagal (IV, I).

The loop is laid in `composition.form_phrases`, between a person's everywhere chords and a place's own, so the band,
the choir's and backing voices' chords, the MIDI file's chords and the page's chord lane follow from one place. A
person's chords for a line or a place win over the loop there. Where a sung note is a semitone from a loop chord's
seventh, the band's `tones()` leaves the seventh out there, as a style's colour steps aside; the MIDI file and the page
still name the chord.

### House's form and hook

- **Harmony**: the loop under everything but the bridge, which keeps the song's own chords (the folk harmony comes
  back in the breakdown, and the drop slams back into the loop).
- **A 16-bar intro** in layers: the kick and hats alone for four bars, the bass in at five, the pad and the stabs at
  nine, and at thirteen the piano's tune, or the chop where the intro is the pad's (`intro=pad` in house means the chop
  takes the intro's last four bars); the filter opening across all sixteen (`plan.entrances`, scaled with a person's
  length).
- **Every turn four bars of the hook**: the chop over the full groove, the lead's quote left out.
- **The drop's refrain opens with eight bars of the hook** over the full groove (the ride, the rolling bass, the
  pluck), and the singer's refrain follows as the release. The hook's bars are laid on the song's turn line (a line
  with no tune), so no lead plays a tune under the chop, and the sung lines take the refrain's words in order after
  them (`takeover.leading`, `own_line`).
- **The last refrain is followed by eight bars of the hook**, so every house version ends on it.
- **A 16-bar outro** where the form has one: the hook over the groove for eight bars, then the band leaving layer by
  layer, the drums alone last (`plan.exits`).
- The break stays the piano's (or organ's) solo on the verse tune, over the loop.
- Endings: cold or ringing on the last chop. The song's last sung note is held only to the end of its line, not under
  the hook bars after it.

**The vocal hook** (`chop`, a part of its own; `style.chops`, `hook_bars`, `HOUSE_HOOK`). The singer sings a chop, a
short phrase of the song's own words on the grid: "No-bo-dy knows" (the first refrain's first line's last words, on its
notes la so mi so), answered by "now it's by you" (the last refrain's last words). The chop is the answer to the song's
question, so it uses these rather than `genome.hooks`. Each syllable is a sixteenth or an eighth, the last held a beat,
on a two-bar rhythm drawn per rendition from three (the call on the beat, one on the off-beats, a stutter), changing to
the next figure at the drop. The stutter repeats the whole word on eighths ("No-bo-dy knows, knows, knows", the repeats
on beat 3 and the "and" after it). In the turns, the drop and the last hook every other bar is the answer
(`HOUSE_HOOK["answered"]`); in a breakdown's turn the chop sings only the call, once in two bars, softly (0.6; the
turns 0.85, the drop 1.0).

A figure is sung from a word's first syllable to a word's last, or not at all. A sung note that ends exactly as a
figure starts doesn't count as under it, so every turn, the drop and the last hook open on their downbeat with "No";
a sung note cutting into a figure ends the figure at its last whole word.

The chop is the singer's voice, not a sample: the program sings it, as notes in the score, so the stems, the MIDI file,
a preview and a replay all have it. It is not pitched up, since an octave up is past what the throat sings (measured to
B4; la is already B4). As its own part it stays off the lyric sheet and the synced words, `variation.lay` doesn't move
it off the grid, it draws on its own stream, and it has its own stem and channel (`mixing.ROLES["chop"]`: low end
cleared, a gentle compressor, a little more room). It is sung with breaths off, each syllable held 85% of its slot (a
tenth of a second at least), at the lead's level (`CHOP_GAIN`).

### Dub's version

**The version is the song's second half.** `Style.dissolve` (drawn 0.9 of the time) is the refrain after which the song
dissolves: half the refrains, at least the first (H's three refrains: after the first; four: after the second). Up to
there the song is sung straight over its own chords, the desk working as above. After it every section is the
version (`mark_dissolved`, the `dubbed` parts, `DUB_DESK["dissolved"]`):

- the **riddim**: the style's loop, two chords, no colour; the bass leading (its notes a little louder, the others a
  little softer);
- the **singer's lines reduced to fragments**: each line, by its own coin, keeps its last word, its first half or its
  second half, all of it now and then, or nothing, breaking at word boundaries. A refrain's first line always keeps at
  least "nobody knows" and the last refrain's last line "now it's by you", so the hook stays recognizable in pieces. A
  fragment is sung where it falls in the tune, on its own notes, and its last syllable is a line's end;
- **every fragment thrown** into the tape echo with a longer tail (feedback 0.72 against the song's 0.6, a little
  louder), now and then into the spring too;
- the **melodica takes the tune in pieces**: it plays the notes the singer left out (`lead`), resting half its lines,
  so voice and melodica answer each other;
- **the desk harder**: bars dropping out at 0.45, the snare kicked into the spring more often, the whole band's
  low-pass swept closed and open again now and then (`sweep-lp` then `sweep-open`, transitions on the band's bus; the
  echo's returns join the band before it, so a sweep darkens them too);
- **the bridge comes back whole**, sung with the lineage's choir on the song's own chords: the vocal dropping back in
  is itself a dub's move, and the bridge is the song's idea;
- **steppers** in the last refrain.

The dub-out after the song (ending `version`) follows, the last fragment thrown into it. The lyric sheet prints the
whole lyric; the score sings the fragments. With `dissolve` 0 the desk's choices are as they would be without it.

| | house | dub |
|---|---|---|
| fixed | the loop's use and where; the lengths; the chop and its words; the octave bass; the tempo range | the version's form whenever it dissolves; the tempo range; steppers in the last refrain |
| drawn | which fitting loop; the chop's rhythm; the drop (0.8); the intro's piano tune or the chop | whether it dissolves (0.9); which fitting riddim; each line's fragment; each drop-out, throw, splash and sweep; the dub-out (0.75) |

The verses stay in house: the bank needs two at least, and a shorter house would need the form (and so the words) to
change, which a style doesn't do.

**Measured.** The stabs sit on the loop chord under them (all but the piano's tune). Whisper, on the finished mix two
bars at a time, hears "nobody knows" in 25 of 30 hook stretches over three machines; in a full drop the chop is about
as loud as the band (its stem 0.4 to 3 dB over the band's dry stems there, 4 to 9 in the turns), and a louder chop is
one number (`CHOP_GAIN`, or the hook's `drop` level). Dub dissolves after the first refrain of three (the version 73% of
the song) or the second of four (54 to 57%); the singer keeps 37 to 56 syllables of the version's lines in 11 to 13
fragments; 8 to 11 fragments a song are thrown with the version's feedback (19 repeats to 50 dB down, about 11.5 s of
tail at 74); the low-pass is swept two to four times; the melodica plays 56 to 123 notes. Memory (two threads,
`MallocLargeCache=0`): house 163 s, 1.27 GB; dub dissolving with its dub-out 222 s, 1.91 GB. In the VPS's 2100 MB a
house version fits to 4.5 minutes and a dub one to 3.9; a machine's long dub shape is refused on the server.

# A jazz trio

A piano, an upright bass and brushes, three instruments the program plays well (the modelled piano, the upright, the
kit's swept brushes), the singer on the tune as written, and the change carried by the harmony, the comping and the
time feel. The page calls it "jazz trio" and says what plays, "piano, upright bass and brushes". It sits beside the
ring at chamber's place and is hidden from the studio's picker ("Beside the ring").

**The feel and the tempo.** A jazz waltz (the song re-barred in three) 0.55, or a ballad swung 0.45. The waltz at 0.76
to 0.94 of the song's tempo (centre 0.85, its quarter about 122 for H), the ballad at 0.74 to 0.92 (centre 0.83, about
80). Lineup: piano 1.0, bass 0.85, kit 1.25.

**The trio's changes** (`style.trio_changes`, for the styles in `CHANGES`). The song's chords keep their functions (I
is still I), played as a jazz pianist would read them off a lead sheet, and fitted to the tune strictly: a chord the
trio plays may rub a semitone against no sung note that the song's own chord there doesn't (`style.sits`). The song's
own passing notes, such as the 4 over I in the second verse line, rub as they always did; the trio adds no rub. What is
sung over a chord is every note of the line in its span, and over a line's last chord the pickups of the line after it.

- **Colour, always where it sits.** Each chord the richest of its colours that sits: a major chord its maj7, else a 6,
  else an added ninth, else the triad; a dominant its 7, else an added ninth; a minor chord its m7, else an added
  ninth. In the mode's spelling (`trio_chord`: vim7, IVmaj7, V7; in aeolian im7, ivm7, VImaj7, vm7).
- **Passing chords, as often as `Style.harmony` says** (0.7 for the style; each chord its own coin from the rendition's
  seed): *ii-V*, a V that resolves to I or ends a line takes its ii for its first half (`iim7 V7 I6`); *a fifth above*,
  a chord held a whole bar before another gives its second half to the chord a fifth above what the next one starts on
  (I7 before IV, iiim7 before vi, vim7 before a ii-V's ii). The lines are decided from the end back, so a chord
  approaches what the next one plays. In a waltz only a whole bar's V takes its ii, as a bar of ii and a bar of V
  (`rebarred`); swung, the half-bar Vs do too. Passing chords never cross a line, so every verse and the chord lane
  agree.
- A bar keeps as many shares as it has where those hold it; where a passing chord can't be written, the line takes
  its colours alone. A chord held over two shares is written twice (`I6 I6 iim7 V7`) and played, shown in the piano
  score and written in the MIDI file as one held chord (`style.held_chords`).
- **Where it goes in**: after a style's loop in `composition.form_phrases` (`_changed`), so the band, the voices'
  harmony, the MIDI file and the chord lane read the same changes. A line whose chords a person set keeps theirs, a
  line whose chords aren't plain numerals keeps them, and a line with a tune of its own at its place keeps the song's.

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

H's V is mostly an Aadd9: the tune sings F♯ over it, and the semitone test is symmetric, so A7's G a major seventh under
the F♯ (A13, the style's most idiomatic sound) is ruled out as a maj7 under a sung tonic is. Where nothing is sung over
the V's second half (a line's end, a turn) it is A7, with its ii before it. A directional rule (only a minor ninth
under the tune rubs) would let A7 sound under the tune; the lineage choir, which takes any chord tone under the tune,
would then need to keep the symmetric rule. The I is a D6 where the tune sings D over it and a Dmaj7 where it doesn't.
The one chord outside the tune's pentatonic world is r4's E7 (V of V, its G♯), where the knob draws it.

**The players.**

- *Piano* (`rootless`): comping in rootless chords, the third and the seventh (or sixth) with the fifth and a ninth
  where they sit (the ninth only where the mode has it a whole step over the root), four notes close, from a seventh
  under the tonic to a third over the singer's low end (for H in D: E3 to F♯4), led smoothly from the last (the band's
  `voicing`, which keeps off every sung pitch). The tones it can spare (a fifth, a ninth) are left out where they'd rub
  a sung note on a strong beat or a long one. Struck as the chord comes and held, or answered: in a waltz on two and
  three, or on the off-beat after two; in four on the off-beat after two (the Charleston) or the backbeats; now and then
  pushed an off-beat early. `rootless-light` (the first verse when the band is sparse): held chords only.
- *Piano with the tune* (`solo`): where the piano has the tune (the intro, a turn, the break, an outro), its right hand
  plays it an octave up and its left hand keeps the third and seventh (or sixth; else the third and fifth) under it in
  the comping's rhythm. In the break, the piano's chorus on the verse tune, a held note at a line's end is answered by a
  few of the chord's tones. A style's table naming "solo" for the lead's section turns the lead's "lead" or "quote" into
  it (`plan_style`).
- *Upright bass* (`walking`, `twofeel`): walking a note a beat, the root as the chord comes, its tones and scale steps
  on weak beats between, moving toward the next chord's root, and on the last beat a step into it (a scale step or a
  half step, whichever rubs against nothing sung there, else the chord's fifth). Two to a bar in the first verse, the
  bridge and the tag (a root on one, a fifth on three; in a waltz one a bar); walking in the refrains, the break and the
  turns, and in the verses once the band is fuller.
- *Brushes* (`swept`, `swept-light`): the kit's brush sweep round the snare, two sweeps a bar in four and one in a
  waltz; the right hand taps every beat (the backbeat strongest) and the skip after two and four (a waltz's after two),
  the ride's figure on the snare; the bass drum feathered on one (and three). Light: the sweeps and the bass drum, the
  taps barely there. A tap pickup into a fuller section; the last chord one sweep and a tap. No sticks, no cymbals.

**The form.** Where the rendition's form has no break and the song's template has a place for one, the trio adds the
piano's chorus 0.8 of the time by a coin of its own (`style.with_break`, `SOLO_BREAK`): H's break is the verse tune,
eight bars, before the bridge. A form a person set is kept (variation.py puts a hand-set form back after the style
decides). The break is a style's choice and never the server's: a version's music doesn't depend on what a server can
hold.

**The rest.** The band's ornament down (no grace notes in the piano's tune). The singer: a little less vibrato (-3
cents), nothing else. The mix a little closer (intimacy +0.15), a smaller room (space -0.05), a little narrower.
Options: the intro the piano's (0.85) or, with no intro, the singer alone first (0.35); a verse with the piano alone or
bare 0.15; stop-time 0.1; a breakdown 0.15; a lift 0.1; endings a broad ritardando 0.5, ringing 0.4, cold 0.1;
entrances 0.25; backing voices rarely (oohs 0.15); no half-time bridge. The style card says "the song's chords with
sevenths and sixths, and passing chords into the cadences" (the last part where the version has any).

**Measured** (four machines, the harmony knob 0.57 to 0.71; each piano or bass note against the chord under its
middle): 98% to 99% of the piano's notes are its chord's tones or its ninth, and the bass's other notes are its steps
into the next chord. Where a note rubs, it is almost always a tone of the song's own triad held under a passing sung
note: counted the same way, the trio rubs on 1.4% to 10.9% of its chord and bass notes and the ballad's band on 3.6% to
12.4%; the trio's own tones (sevenths, sixths, ninths, steps) on 0.2% to 1.5%. The comping's mean pitch is A3 to C♯4.
Words misheard (Whisper base.en, `tools/intelligibility.py`, a verse and a refrain, four machines): the ballad 10.7%,
the trio as each machine chose it 10.4%, the trio swung 12.1%. Memory (two threads): H's shape with its break, a waltz,
201 s, 1.74 GB; swung, 206 s, 1.78 GB; four verses, every part, the slowest tempo, 372 s, 2.51 to 3.06 GB (the kit's
sweeps and taps, about 7.1 MB a second). In the VPS's 2100 MB about 4 minutes in one go: H's own shape (3.4 minutes)
fits; a machine's longer shape is made in the browser.

# A hymn

An organ under everyone singing the tune in parts: the song's tune sung plainly by the lineage and the program's
voices together (the song is about everyone singing it), over sustained chords. The page's words claim no tradition or
denomination: the style is **hymn**, "organ, and everyone singing in parts". It sits beside the ring at chamber's
place: a lineage that leaves it steps to the ballad or the songwriter, the folk tune going home.

## The band: an organ, and everyone

- **The organ** (`pipeorgan`, songbird/synth/pipeorgan.py), or for about a third of machines (0.35) a **harmonium**
  (the reed organ organ.py plays: `swaps`, kept down a lineage). No rhythm section.
- **The singers**: the lead on the tune, and a group of at least three (`group=3`, the lineage's voices first, then
  the program's), each matched to its part by range and held to a choir's vibrato at synthesis (`synth.matched`, the
  band settings' `parts: "voices"`, set for any style that sings as a group).

## The pipe organ

A pipe organ is a sum of steady pipes, which additive synthesis does well: each rank a pipe per key with a fixed
spectrum, the life in the attack, the wind and the room.

- **Ranks** (each pipe a period with that rank's spectrum, the machine's voicing a little different pipe to pipe): an
  open diapason 8' (harmonics falling about 6 dB an octave, a strong second), an octave 4' and a fifteenth 2', a
  stopped flute 8' (odd harmonics: the third about 15 dB down), a flute 4', a mixture (II ranks, 1 1/3' and 1',
  breaking back an octave in the top two octaves). Pedal: a bourdon 16' (stopped) and an octave 8'. The bourdon under a
  D2 pedal sounds D1, under the organ strip's 55 Hz high-pass, so the pedal's weight is its 8'.
- **Registrations** by articulation: `""` diapason 8' and octave 4' (the plain hymn sound), `flutes` stopped flute 8'
  and flute 4' (soft), `full` diapason, octave, fifteenth and mixture, `pedal` the bourdon and octave.
- **Each pipe** speaks as flue pipes do: the upper harmonics first and the fundamental building over 25 to 90 ms
  (longer for a bigger pipe), a little chiff (noise around the 2nd to 4th harmonic, 20 to 40 ms, more on the flutes),
  wind noise at about -45 dB while it sounds, a few cents of tuning per pipe (a machine's `wear` more), and a 40 to 80
  ms release. The ranks beat gently against each other, an organ's chorus; no tremulant. Velocity is the swell box (a
  gentle level and a darker top as it closes), since an organ has no touch.
- **Built from the harmonium's kernel** (`reed._read_mix`: the attack's period cross-faded into the steady one), scipy
  filters and numpy, so no numba kernel is added and the browser's translation (docs/notes/BROWSER-RENDER.md) holds.
  The wind is made note by note, so the module keeps one array the length of the song. The chests alternate C side and
  C♯ side, so the stem is a little wide. Its level was set against the harmonium on the same notes (equal).

## The harmony: a setting of the style's own

A hymn sets its tune with a chord to a beat or a half bar, plain triads and their first inversions, a bass that moves
by step where it can, and cadences that close the lines. The style makes its own harmonization (songbird/hymn.py,
`setting`), laid in `composition.form_phrases` beside a style's loop (so the organ, the voices, the MIDI file, the
chord lane and karaoke follow from one place). It sets each line as it is sung (`composition.played`: the lineage's
variants, and a person's own tune for the line); a line whose chords a person set keeps theirs; a line with no tune
(H's turn) keeps the song's chords. For each phrase, a dynamic programme over its beats:

- **candidates**: the mode's triads on 1 to 6 (and 7 where it is major, mixolydian's ♭VII), root position or first
  inversion (`IV/3`); no second inversions, no sevenths;
- **the tune's fit**: a sung note on the beat (or a beat long) that isn't a chord tone costs a lot, a passing eighth
  between beats a little, a non-chord tone a semitone from a chord tone more;
- **the song's chords as the backbone**: a chord other than the song's at that beat costs a little;
- **progressions**: the strong ones (down a fifth, up a step, down a third) cheap, retrogressions (V to IV, V to ii)
  dear; changes on strong beats rather than weak (`WEAK`, `STAY`);
- **the bass**: steps cheap, leaps of a fourth or fifth fine in root position, tritones dear; parallel fifths and
  octaves between the bass and the tune dear;
- **cadences**: the phrase's last chord is the song's (I, V, or the bridge's vi), in root position; before a final I,
  V (authentic) or IV (plagal).

The result is per bar, one, two or four chords (`("I", "V/3", "vi", "IV")`), as `chords_per_bar` allows. A pickup is
left out of a line's beats, so it is harmonized by the line before's last chord, which the organ holds through it.

## The parts (songbird/hymn.py, `parts`)

The tune is the top line, as a hymn sets it (H's lead runs A3 to B4 in D). Under it, from the setting:

- **the bass** is the organ's pedal (the chord's bass, D2 to D3, led by step): the throat thins below E3, so no voice
  sings it, and the program says so ("the organ's pedal takes the bass");
- **the alto and the tenor** (between E3 and the tune), each syllable a chord tone, chosen together: the triad's
  missing tones first (the third never doubled over a bass on the third), each held where the chord keeps it, else to
  the nearest; never a semitone from the tune, no parallel fifths or octaves between any two of the four, within an
  octave between the upper three. Where the tune dips too low for two parts under it (H's pickups on A3), the alto
  sings with the tune in unison, never above it;
- **the treble** voices (every third voice) sing the tune with the lead, as most of a congregation does;
- the parts read the chord the band plays at each moment (`ctx.chord_at`), never the melody's `chord`; the lineage's
  harmony (`choir_voicing`) is left as it is;
- **the descant is the organ's**, over the last refrain in about two renditions in three (`DESCANT`, by the seed), up
  to A5 (`TOP`). A sung descant a third to an octave over the tune would sit at D5 and E5, past the throat's measured
  B4, and leave one chord tone or none for a third of H's notes.

The organ doubles the singers at pitch, as a hymn's organ does: its writers (`hymn`, `givingout`) are exempt from the
octave-down rule and never use the band's `voicing`, which drops any pitch being sung.

## Section by section

- **Intro** (`intro=lead`): the organ **gives out** the tune alone, the intro's lines (H's: the refrain's last two) in
  four parts with the pedal, on `full`, nobody singing.
- **Verses**: the first in **unison**, the next in **harmony**, and so on alternately. A unison verse is the lead with
  the alto and treble voices (`UNISON_ROLES`), the tenors resting: everyone on every word, with the diapasons doubling
  the tune at pitch, cost the words. The verses are on `flutes`.
- **Refrains**: everyone in harmony, on the diapasons; the **last refrain** on `full`, with the organ's descant when it
  comes.
- **Turns**: the organ alone, the turn's chords held in four parts with the pedal (`flutes`).
- **Break, outro**: the organ gives the tune out again.
- **Bridge and tag**: the lineage's voices sing the genome's harmony as always, the program's voices the tenor under
  it, the organ on `flutes`.
- **The end**: the last chord held and released together (`ring`), a broad ritardando (`rit`), or the **amen** (IV
  then I, two bars, the organ in parts and every voice of the group on "a-men"; the group's size takes part only for
  the hymn).

**Feel, tempo, the singer, the mix.** Straight only, at 0.66 to 0.84 of the song's tempo (centre 0.75: 72 for H), a
broader ritardando (+0.15) and a congregation's looseness (humanize x1.3). No colour (plain triads). The singer plainer
(vibrato -6 cents, rd -0.03). The mix a big room (space +0.3, width +0.1, intimacy -0.08), the group 1 dB forward.
Options: intro lead (1.0); ending ring 0.25, rit 0.35, amen 0.4; backing `gang` (1.0, the congregation) or a person's
"" (the singer alone with the organ); no bare verse, stop-time, breakdown, lift or entrances.

**Measured** (four machines): 2.0 to 2.2 chord changes a bar (a chord a beat where the tune's eighths move, a half bar
or a bar where they don't); each line closes on the song's chord in root position; more than nine in ten of the tune's
notes struck on a beat are tones of their chord. In D major the verse's first line is I, V/3, I, I | I, ii, V, V; the
refrain's "now it's by you" I, IV, I, V | V, I, I, I. Parallel fifths or octaves between any two lines in 1.1% of
slices, most in the low keys; the alto in unison with the tune in 3.2%; 99.6% of sung part-notes are tones of the
organ's chord there or the tune's note. In tune: the parts' median -2.5 cents, 99.8% within 25 cents. Words misheard
(Whisper base.en, a verse, the next verse and the first refrain): the hymn 15.9% (the unison verse 16.4%, the verse in
parts 15.4%), the ballad 15.4%. Memory (two threads; docs/WEB-STUDIO.md's table): H's hymn of 201 s, 1.18 GB with three
voices, 1.20 with six; four verses, every part, six voices at 63.4 (394 s), 1.77 GB with the pipe organ, 2.46 with a
harmonium. The studio's estimate is set by the choir (5.7 MB a second) or the harmonium (6.9): a hymn fits the 2100 MB
to about 5.0 minutes with the pipe organ and 4.1 with a harmonium; a longer one goes to the browser.

# An old 78

The song says of itself "Nobody knows who made this song." This version sounds found: a singer with a parlour piano
(or a guitar), now and then a fiddle, recorded as an acoustic-era 78. The singer delivers the tune straight over
instruments the program plays well; what makes it old is the recording, a deterministic stage at the end of the mix.

**On the page**: "old 78"; its detail "a parlour piano, recorded as a 78" (or "a guitar", and "and a fiddle" when one
comes); the mix card begins "recorded as a 78" (and shows no width: it's mono). "A 78" names a format, not a
provenance: no label, artist, year or recording is claimed anywhere (the studio test forbids the decades).

## The design

- **Beside the ring**, by the songwriter (a singer and one accompanist, close); a lineage in it keeps it or steps to
  chamber or the lullaby.
- **The band**: a parlour piano (1.0), a guitar in its place for about a third of machines (`swaps`, a lineage keeping
  its own), a fiddle half the time (`optional`). No bass and no drums: an acoustic horn took neither, and the piano's
  left hand (the guitar's thumb) is the bass.
- **The piano's oom-pah** (`idioms.w_stride`): on the strong beats the root, then the fifth, in the tenor (from 19
  semitones under the tonic: G2 to F♯3 for H in D, a parlour upright's, so the horn's high-pass keeps it), on the others
  a short chord above it under the tune (oom-pah-pah in a waltz); where a sung line holds its end and the chord changes,
  about a third of the time the bass walks two steps into the next root. The bridge: broken chords; the tag: one chord
  left to ring.
- **The tune over its own hand** (`idioms.w_parlour`, the table's `"solo"`): where the piano or the guitar plays the
  tune (an intro, the break, an outro), its oom-pah (or Travis thumb) keeps going under it, a little softer. The fiddle,
  when it comes, leads the intro and the outro, rests in the first verse and the break, answers the lines in fuller
  verses, plays a counter-line in the refrains and a held tone in the bridge.
- **The form**: an intro and a break always (`StyleDef.shape`), put into the machine's form after the style is chosen
  (`style.shaped`, by edits.reshape, in `variation.choose`), never into a form set by hand or a person's own order; a
  person's `form.intro` and `form.break` are pinned over it, and the shape card says "the old 78 style always has one".
  Neither has words, so the words are the machine's.
- **Feel and tempo**: straight 0.6, a waltz 0.25, swung 0.15 (a foxtrot's lilt); straight or swung at 0.86 to 1.0 of the
  song's tempo (H at 83 to 96, centre 88), a waltz 0.64 to 0.8. Sixths on I and IV, V7 and ii7 at 0.4. Options: the
  intro played, no bare verse, no stop-time, no breakdown, a lift now and then (0.1), endings ring or rit (0.45 each) or
  cold, backing voices in thirds 0.2.
- **Leans**: the singer a little more vibrato (+6 cents) and pressed a little (rd -0.06, projected into a horn); the
  band a little older (wear +0.1) and darker; the mix a dead room (space -0.25; the room itself stays the machine's),
  the singer close, no plate, no tape's wear (`mix.wear` -1, a knob that isn't handed down, so a child in another style
  gets its machine's own back), and the disc.

## The recording: `MixParams.disc`

`disc` (0 to 1; left out of a record while 0, so records and every child's draws are unchanged by it) puts the whole
mix on an acoustic 78 (songbird/synth/disc.py), after the glue and the tilt. The amount is how worn the surface is (its
noise and clicks); the horn, the mono and the turntable are the same at any amount. In order:

1. **Mono**: the mid, written to both channels, back where the stereo mix lies.
2. **The horn**, each record its own (drawn): a 2nd-order high-pass at 130 to 150 Hz and a 4th-order low-pass at 4.6 to
   5.2 kHz; a honk at 450 to 700 Hz (+4 to 6 dB), a little more at 1.1 to 1.6 kHz (+2 to 4), a dip of 3 dB at 1.8 to
   2.1 kHz, the recording diaphragm at 2.4 to 3.2 kHz (+3 to 5, Q at most 3); the cutting stylus's slight saturation.
3. **The turntable**: the disc a little off centre, so the pitch wavers once a revolution (78.26 rpm: 1.30 Hz), 0.1 to
   0.3% at its peak (each record its own), with a second harmonic a quarter as deep; flutter 0.02% RMS.
4. **The surface**, scaled by `disc`: the groove's noise through the playback's band (150 Hz to 1 kHz above the horn's
   top), 38 LU under the music (`NOISE_DB`), swelling ±20% once a revolution (a worn arc, in step with the wow) and
   drifting ±10% across the side; a fine crackle (25 small ticks a second, `CRACKLE`); scratches (`SCRATCHES`), each
   heard once a revolution for 2 to 20 turns, and a pop now and then. Clicks stay under the limiter's notice.
5. **The needle**: dropped into the lead-in groove where the mix begins in silence (the 0.6 s preroll every song has:
   the drop at 0.05 s, the noise in over 0.15 s); at the end, where the music has died 50 dB away, the run-out groove's
   swish and click once a revolution, three seconds of it added after the song by the stage itself, then lifted. A
   section heard alone (it begins and ends in the music) gets neither.

Every draw is the rendition's (its seed, a stream of its own); numpy, scipy and fx's filters, saturation and warp, so
no new numba kernel. `MixParams.parse` checks keys against the fields, so `--mix disc=1` works in any style (a jig, a
ballad, the songwriter on a 78) and a record keeps it. The studio's mix card offers only the room (`edits.MIX`);
"recorded as a 78" for every style would be one more entry there. Only the old 78 sets it by itself.

## Measured

On four machines (tools/discmeter.py: their mixes made again without the disc and through it):

- **The band the horn passes**: -6 dB at 108 to 124 Hz and 4.7 to 5.1 kHz; 80 Hz 11 dB down, 8 kHz 22 dB, 12 kHz 43 dB;
  each horn's honk between 468 and 688 Hz.
- **The wow**: eccentricity 0.12% to 0.26%; a steady 1 kHz tone wavers 0.21 to 0.36% at its peak, at 1.3 Hz.
- **The surface**: 37.8 to 38.1 LU under the music; the lead-in groove 39 to 41 dB under the music's mean level, the
  run-out 32 to 35 dB.
- **The clicks**: 0.38 to 0.93 a second; 66 to 82% of them heard again exactly a revolution later.
- **Loudness**: -14.0 LUFS, true peaks -1.05 to -1.6 dBTP; loudness range 6.6 to 14.6 LU.
- **Words misheard** (Whisper base.en, every sung section): the old 78 18.6%, without the disc 13.7%, the ballad 15.4%,
  lo-fi 11.2%. The arrangement is about as clear as the ballad's and the recording costs about five words in a hundred;
  no one part of the recording dominates that cost.
- **Memory** (two threads): H's shape, a parlour piano alone, a waltz, 243 s, 1.14 GB; four verses, every part, a
  fiddle, tempo 58, 471 s, 1.95 GB. The lightest band: the voice's, piano's, guitar's and fiddle's memory rates are 4.5
  MB a second. In the studio's 2100 MB an old 78 fits to 6.3 minutes.

A ten-inch 78 held about three minutes a side; these versions run 2.8 to 5.5 minutes (the machine's form, with the
break). A shorter one would mean fewer verses, which changes the words, which a style doesn't do.
