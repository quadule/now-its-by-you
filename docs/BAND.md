# The band

The seed's band is the **ballad**: a small acoustic folk band of eight
instruments built from physical models, arranged section by section so the
song builds and breathes, with the choices a rendition can vary gathered in
one place (`Params.band`). It is the first of the styles a rendition can be
played in; the others (a string band, country, gospel, a shanty, synth folk,
lo-fi and more) each have their own lineup and idioms (docs/STYLES.md). With
no style chosen a rendition is played as described here.

Nobody but the artist can listen, so the models and the arrangement were
judged by measurement against what real instruments and arrangements do,
and reviewed by a Fable advisor who measured as it went.

## The instruments

Each is its own module in `songbird/synth/`, and each stem is dry, panned
and at a level that sits with the others (`synth/instruments.py`).

**Bodies** (`body.py`). A string barely radiates; what we hear is the box it
drives. A body is an impulse response built from modes: the family's named
low modes (a guitar's air mode near 100 Hz and top plate near 200, a
violin's A0 near 275 and B1 pair near 470 and 540 with a bridge hill near
2.6 kHz, an upright bass's air mode near 60) plus a seeded scatter of 60 to
110 plate modes whose exact places differ from maker to maker. Two
microphones hear different mixes of the scatter, which gives each
instrument its width. The responses ring down 60 dB in 0.12 s (fiddle) to
0.39 s (bass), which gives each pluck its woody knock, and radiate up to
8 kHz (harp) to 13 kHz (cittern); an upright bass radiates little below its
60 Hz air mode, so its lowest fundamentals are weak.

**Plucked strings** (`pluck.py`: the lute, the guitar, the harp, the bass).
Extended Karplus-Strong, run sample by sample in numba. The pluck's force on
the bridge is a rectangular wave whose duty is the plucking point (which
notches the harmonics with a node there), softened by a fingertip or a pick,
roughened with a little noise, and scaled by its RMS so a pluck near the
bridge is as loud as one in the middle; a pick adds a click of a few
milliseconds, bright up past 10 kHz. Each string vibrates in two planes:
across the top it drives the body and dies fast, along it rings on quietly,
a fraction of a cent apart, so a note has a loud start, a long soft tail and
a slow beat (a D3 falls 14 dB/s at first and 9 dB/s later). The lute's
paired courses are two strings a few cents apart met a few milliseconds
apart by the pick. When a note ends a finger lands on the string: the loop
loses its energy in 80 ms and the touch makes a small noise. A guitar's
muted chop is its strings stopped at once plus the pick's scrape. Open
strings tuned to the song (the harp's and the lute's tonic and fifth, the
guitar's six) answer whatever shares their harmonics. Tuning is within 0.5
cent; a 3 s note costs 2.6 ms.

**Bowed string** (`bowed.py`: the fiddle). A digital waveguide: two delay
lines meeting at the bow, velocity waves adding up at the bow point, and a
friction curve (the STK bow table) that grips the string while bow and
string move together and lets it slip when they don't. The Helmholtz
motion comes out of that alone. Measured across G3 to B5: harmonics fall as
1/n (-6.0, -9.5, -11.9 dB for the 2nd to 4th: a sawtooth at the bridge)
with the notch at n = 1/β that the bow position makes; in tune within 2
cents, the loop shortened by the 0.28 samples by which a rounded corner
triggers the slip early. Three things a player does are modelled: the bow's
weight grows with its speed (too light a bow for its speed flips the string
to its octave: Schelleng's minimum force); the hair catches the string as it
lands, a jolt a third of a Helmholtz corner high, so a note builds up in 44
to 120 ms, where real détaché attacks sit; and at a bow change the bow turns
round in 20 ms, so a sustained line dips 8 to 10 dB for a moment. Slurred
notes keep the bow going; a counter-line changes bow every two bars. Vibrato
is a folk fiddler's, 6 to 16 cents at about 5.6 Hz, on long notes after a
quarter second; slides come up from a tone and a half below; when the bow
lifts the string rings down.

**Blown pipe** (`pipe.py`: the whistle, a wooden flute or low whistle).
Physically inspired: the air jet's split at the labium is a saturating
function of its swing, which turns a sinusoidal flip into a few harmonics
(more when blown harder, even ones when aimed off the edge); the jet's
turbulence is a hiss, loudest while the jet goes in; both ring in a bore
resonator tuned to the fingered note, which gathers the noise into harmonic
bands. Measured: 2nd harmonic -17 to -20 dB, 3rd -15 to -24 dB, breath noise
about 30 dB under the tone and nothing below 350 Hz, tongued notes speaking
in 22 to 36 ms with a puff of noise and a slightly sharp start, fingered
slurs with a short dip. Cuts, taps and rolls are short notes in the score.

**Struck skin** (`drum.py`: the frame drum). Modal: every mode of an ideal
membrane up to 16 times the fundamental (196 of them, at the zeros of Bessel
functions), weighted by where the tipper lands (a boom near the middle, a
drier knock near the rim), filtered by the stick's contact time, with a hard
hit's pitch glide, the skin's slap above the modes, and the stick's click.
Strokes: bass (T60 0.35 s), tip (0.22 s, the back hand on the skin), mute
(0.08 s), rim, and top (the back hand pressed high, the pitch up and drier;
no style plays it). Each is scaled by the loudness of its first 30 ms (not
its peak, which the click would set), the tips 9 dB and the mutes 12 dB
under the open boom, as a bodhrán player plays them. A frame drum has no
back, so its lowest modes radiate as a dipole, 12 dB an octave weaker below
the fundamental than a closed drum's. It isn't tuned to the key (a boom on
the tonic under every chord muddies the bass): each maker's skin sits
somewhere within a quarter octave of 80 Hz.

**Drone** (`reed.py`: free reeds). Band-limited reed tones, two or three
reeds a note a few cents apart (more when worn) so they beat, a bellows swell
in and out and a pumping hand's breathing, air hissing past the reeds, and a
reed box's broad resonances as its body. The tonic and a softer fifth, below
the singer.

## The arrangement

`songbird/band.py` decides who plays what. Each section has a role and an
energy; with the default arc, H runs:

| Section | Energy | What the band does |
|---|---|---|
| intro | 0.42 | the whistle states the refrain's last two lines, with cuts; harp picking; the bass holds; the drone swells in |
| verse | 0.36 | sparse: harp picking (every other note), bass roots, a lute or harp answer between some lines |
| refrain | 0.55 | the guitar strums the lilt, the harp moves up above the tune, the bass walks, the drum comes in lightly |
| turn | 0.49 | the fiddle quotes the refrain phrase that best fits the turn's chords |
| verse | 0.51 | a boom-chick guitar, a light drum, one held fiddle tone a line above the singer, the lute's answers |
| refrain | 0.68 | the drum's pulse on the foot, the fiddle's counter-melody, the lute's answers |
| turn | 0.56 | the lute quotes |
| bridge | 0.51 | a different colour under the lineage choir: no guitar, harp chords rolled low to high, the drone, the fiddle's pad, a lub-dub on the drum, then a crescendo into... |
| refrain | 0.81 | everything: the whistle's descant, the lute doubling the singer, the fiddle's pad, the full drum |
| tag | 0.55 | winding down: the whistle doubles the la-la tune, one strum a chord left to ring, rolled harp, the drone, a last open stroke |

When the arrangement's intro is a quote (`--arrange intro=quote`,
docs/STYLES.md), the whistle alone plays a line of an older song the genome
names, over the drone, in bars cleared before the song the way a count-in's
are (`prelude_part`). H's `quote` is the first line of the chorus of Daisy
Bell (Harry Dacre, 1892), the first song a computer sang (Bell Labs, 1961),
re-barred from its waltz into the song's 4/4. The song itself starts later
by those bars and is otherwise unchanged, so the recording sets' guides,
which don't quote, keep their timing.

The rules, briefly:

- **Leave room for the voice, and for the lineage choir.** Comping plays 2
  dB softer under words and 3 dB softer under an instrument stating the tune.
  Nothing but the doubling lute sits on a sung pitch, the choir's included
  (the harp takes such a note an octave down). Counter-lines, descants, pads
  and fills take their register from the section's sung range (above its
  top), never within three semitones of the tune, the choir or another line
  already written, and choose each note to avoid seconds and tritones against
  them. When the choir sings, the whistle doubling the tune holds its chord
  tones over the passing notes rather than clash with the harmony. The bass
  keeps to its own octave (E1 to B2 in D), the drone to the tonic and a softer
  fifth below the singer.
- **Speak between lines.** A fill starts an eighth after a line's last note
  lands, while the singer holds it, and runs by scale steps toward the next
  line's first note, an octave up, stopping one step short so the singer
  completes it. About half the line ends get one at the default density.
  Counter-lines move there too.
- **Bass.** Roots in the first verse; a root and a fifth where the energy is
  low; walking quarter notes elsewhere, through chord tones, with an
  approach note into each new chord (a scale step, now and then a half step,
  never a half step or tritone from the sung note), and now and then the
  next root pushed an eighth early and tied over.
- **Guitar.** Open shapes found by searching every fingering within three
  frets (the root lowest, the third present, open strings welcome) and a capo
  that suits the song's chords. Where it strums, it is a strumming hand
  (songbird/strumming.py, shared with the styles' guitars): a home groove for
  the song from a library of grooves (the lilt's D.DUD.DU, the old faithful
  D.DU.UDU, calypso, sparse, half, drive, waltzes and six-eights, sixteenths
  in a song under 85 bpm), chosen by the band's pattern and density, and held
  through each section as a player holds it. A section's energy moves how
  many strings a down stroke crosses and how hard before it moves the groove
  a step; a bridge sometimes changes it. Accents lean on 2 and 4. A phrase's
  last bar may leave its last beat to ring or fill a rest with a light up; an
  up is now and then a ghost on the top two strings; the up just before a
  chord change is often the open strings (the fretting hand lifting), or left
  out. A down on 1 or where a chord starts crosses every string, one on a
  backbeat or between beats the upper four or five, one on 3 the lower; an up
  catches the top two to four. A stroke meets its strings 4 to 7 ms apart
  (quicker when hard or fast, never more than 30% of a slot), starts before
  the beat so its weight lands on it, and its ups sit a few ms late in the
  lazier grooves. A string sounds until the pick meets it again or the hand
  moves to another chord. The light pattern is a boom-chick (the thumb on the
  bass string where a foot starts, a brush of the upper strings between; the
  thumb takes the root wherever a chord starts). The guitar's renderer adds
  the pick's noise crossing the strings once a stroke, brighter on an up.
- **Harp.** `Params.accomp` is its picking pattern, varied bar by bar (a half
  turned round, passing notes, a rolled chord and quiet at some line ends);
  in the refrains it climbs from just above the tune; rolled chords in the
  bridge and tag. Its strings ring until they are plucked again or the
  harmony leaves them.
- **Tune statements.** The lead (the whistle by default) opens and closes;
  breaks and turns rotate through the others. Each plays in its own octave: a
  whistle cuts repeated and strong notes and rolls long ones, a fiddle slurs
  steps and slides into some long notes.
- **Drum.** A low stroke where each foot starts, the tipper on the rest; light
  in the first refrain and second verse, the full pattern in the last
  refrain, a lub-dub under the bridge, one open stroke on the last chord.
  There are no fills into a louder section: three even taps on a synthesized
  skin sound like a finger on a microphone.
- **Every bar its own, and a drift that stays small.** Each part draws its
  choices from its own random stream, one per bar, and its timing from where
  a note sits, not from how many came before. So patterns vary bar by bar
  (dropped up-strokes, chops, ghost strokes, turned-round picking), and a
  small change to one setting changes only what it touches: nudging density
  from 0.5 to 0.62 keeps 80% of the notes exactly (97% counting notes moved
  by under 20 ms), dropping the lute keeps 96%, and moving wear, brightness
  or the arc keeps 98 to 100%. Players also breathe with the phrase: a
  little fuller through each line's middle.

## The knobs

`Params.band` is a `Band` (`songbird/band.py`); params without it load
with the defaults, unknown names are ignored and out-of-range values
clamped.

| Field | Range | Default | What it does |
|---|---|---|---|
| lute, guitar, harp, bass, fiddle, whistle, drum, drone | 0..2 | 1 | each instrument's stem gain; 0 sits it out (its part isn't written, and the next lead takes over) |
| brightness | 0..1 | 0.5 | fingertips, gut, a breathy pipe (0) to picks, steel, an edgy bow (1): loop loss, pluck hardness, jet drive, reed spectrum |
| pattern | lilt, strum, pick, air | lilt | the accompaniment family: the melody's foot; a steady strum in the player's own groove; fingerpicking (no strums, harp rolls); a slow air (rolled chords, held bass, drone, no drum) |
| density | 0..1 | 0.5 | roots, boom-chick or a strum a chord (0) to eighth-note picking, walking bass, extra ups and many fills (1) |
| swing | 0..1 | 0 | straight to a triplet lilt on each beat's off-beat half, for the singer too (compound meters keep their own lilt) |
| wear | 0..1 | 0.25 | a new, tight band (0) to an old, loose one (1): courses and reeds 1.5 to 7.5 cents apart, strings up to 4.5 cents off, timing wobble 6 to 15 ms, more bow and breath noise, a lower skin |
| ornament | 0..1 | 0.5 | plain (0) to much ornamented (1): how often cuts, rolls and slides come, and the vibrato's depth |
| arc | 0..1 | 0.75 | every section alike (0) to a strong build from the first verse to the last refrain (1) |
| lead | whistle, fiddle, lute | whistle | who states the tune where nobody sings |
| body | 0.8..1.25 | 1 | the instruments' size: a bigger body resonates lower |
| maker | any integer | 0 | seeds the instruments themselves (body modes, string quirks, the drum's skin), so a machine keeps its band across renditions |
| lineup | instrument -> 0..2 | empty | who plays when a style sets the band (any instrument synth/instruments.known() names), and each one's gain; empty: the eight fields above. Pattern, lead and the harp's picking are the ballad's; the other knobs apply to every style (docs/STYLES.md) |

`pattern` and `lead` are categories, so a continuous drift value maps onto
them with hysteresis (below). A gain that falls below 0.02 removes the part,
which can move other parts' roles (another instrument takes the intro), a
bigger step than the gain itself suggests.

## What a machine and the drift choose

`choose_params()` (the table is `songbird/variation.py`) sets the band as it
sets everything else: the machine's own value, from its harvest
([HARVEST.md](HARVEST.md)), moved by the drift, and the child pulled 0.6 of
the way there from its parent. With no machine and no date the seed's
defaults stand.

| Field | The machine's own | Drift (view) | Range kept |
|---|---|---|---|
| brightness | 0.5 + 0.25 screen brightness - 0.1 warmth | sheen (daily), ±0.15 | 0.1..0.9 |
| density | 0.5 + 0.25 cores and memory | texture (weeks), ±0.2 | 0.1..0.9 |
| swing | 0.18 + 0.18 the typing's skew | feel (daily), ±0.09 | 0..0.6 |
| wear | 0.25 + 0.2 file ages + 0.05 uptime | none | 0..0.7 |
| ornament | 0.5 + 0.25 the vocabulary's richness | feel (daily), ±0.1 | 0.1..0.9 |
| arc | 0.75 ± 0.12 by the machine | arc (weeks), ±0.12 | 0.4..1 |
| body | 1 ± 0.1, bigger with a bigger-built singer, ± 0.04 more; the machine's own, never inherited | none | 0.85..1.2 |
| maker | an integer from the voice hash, the machine's own, never inherited | none | |
| each gain | 1 × 2^(±0.35) by the machine | balance (weeks), ±30% each machine's own way; ensemble (weeks), ±25% plucked strings against bowed and blown | 0.5..1.5 |
| pattern | lilt ± 1.1 steps by the machine, + 0.4 toward the strum for a busy one, along air, pick, lilt, strum | pattern (weeks), 1.2 steps, held | |
| lead | fiddle ± 1.3 steps by the machine, along whistle, fiddle, lute | lead (year), 1.2 steps, held | |

A gain never falls below 0.5, since one under 0.02 would drop the part and
hand its role to another. pattern and lead are held against flicker: a
stateless Schmitt trigger, which within 0.2 of a boundary keeps the choice
the drift last sat firmly in, read back from the drift field day by day.
Over 16 made-up machines and four years the pattern changed about 2.5 times
a year (never back within 13 days) and the lead about once in three years;
the gains stayed within 0.70..1.44.

## Stems

`render_stems()` returns a stem for each instrument that plays, named by role
(lute, guitar, harp, bass, fiddle, whistle, drum, drone, and in another style
any instrument of its lineup: banjo, piano, kit...), then the voice and the
choir: dry, stereo, all the same length, each fading over its last 0.3 s.
Positions: bass centre, drum just right, guitar right and lute left of
centre, harp a little left, fiddle further right and whistle left of centre;
plucked instruments carry their bodies' two-microphone width (left/right
correlation about 0.8), the drone and the drum are near mono.

The levels are set against the formant singer as `render_stems()` delivers
it (the voice at about -10.5 LUFS while singing). Measured in H with the
default arc, the band as a whole sits, in LUFS while it plays:

| Section | Band | Voice over band |
|---|---|---|
| intro | -18.6 | (no voice) |
| verse 1 | -22.2 | 12.1 dB |
| refrain 1 | -19.2 | 8.1 |
| turn | -17.5 | |
| verse 2 | -20.0 | 9.8 |
| refrain 2 | -16.8 | 5.6 |
| turn | -18.5 | |
| bridge | -20.0 | 9.3 |
| refrain 3 | -16.1 | 5.0 |
| tag | -19.2 | 13.3 |

The band arcs from an intimate first verse to a full last refrain and falls
back under the bridge. A new singer, or the mix's buses, will move the
voice; the band's own contour is the part that belongs to the arrangement.
Its spectrum falls about 4 dB an octave from the low mids to 8 kHz, and its
top octave (8 to 20 kHz) sits 26 dB under 250 to 500 Hz (a whole acoustic
record, singer included, is usually 20 to 25).

## Checks

`tests/test_band.py`, `test_pluck.py` and `test_instruments.py` measure each
model against the numbers above (tuning, the bowed string's 1/n harmonics and
attack, the pipe's spectrum and tonguing, the drum's modes, the reeds'
beating, the strings' two-stage decay, courses and sympathetic strings), the
band's knobs (old params load, clamping, density and pattern change the
playing, swing moves only off-beats, a zeroed instrument sits out, a small
change keeps most notes), the arrangement's arc, and that every song is
arranged in range and replays exactly.

## Limits

- The artist judges the band by ear. The models are right by the measures
  above, but the measures are not the ear: the whistle in particular is physically inspired
  rather than a jet-bore waveguide, and the drone is additive.
- The fiddle speaks slowest on the G string (about 115 ms), where it rarely
  plays in this arrangement. Keeping every line above the tune has a price: in
  H the fiddle lives between C#5 and D6, never down in its warm low strings.
- Counter-lines are chord tones that move where the singer holds; they are
  lines, but not composed tunes.
- The band's timing is humanized and each part has its habit (the bass sits a
  hair behind, the fiddle starts early), but there is no deeper groove
  model: no push and pull that a band develops over a song.
- The last refrain carries seven instruments; it is the climax, but it is
  full.
