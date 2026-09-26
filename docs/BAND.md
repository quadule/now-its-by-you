# The band (2026-09-25)

The accompaniment used to be three Karplus-Strong strings: one doubling the
singer at a quarter of her loudness, a harp picking the same pattern under
every section, and a bass on the root, each through four peaking EQs. It
sounded thin and mechanical because it was: one texture, one level, one
timbre, from the first bar to the last. It is now a small acoustic folk
band, eight instruments built from physical models, arranged section by
section so the song builds and breathes, with the choices a rendition can
vary gathered in one place (`Params.band`).

Nobody but the artist can listen. Everything below was judged by
measurement against what real instruments and arrangements do, and a Fable
advisor reviewed the band twice (its first review changed a great deal:
see "What the review changed"). The renders in `renders/production/band/`
are for the ears.

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
0.39 s (bass), which is what gives each pluck its woody knock.

**Plucked strings** (`pluck.py`: the lute, the guitar, the harp, the bass).
Extended Karplus-Strong, run sample by sample in numba. The pluck's force on
the bridge is a rectangular wave whose duty is the plucking point (which
notches the harmonics with a node there), softened by a fingertip or a pick,
roughened with a little noise, and scaled by its RMS so a pluck near the
bridge is as loud as one in the middle. Each string vibrates in two planes:
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
cents once the loop is shortened by the 0.28 samples by which a rounded
corner triggers the slip early. Three things a player does had to be put in:
the bow's weight must grow with its speed (too light a bow for its speed
flipped the string to its octave: Schelleng's minimum force); the hair
catches the string as it lands, a jolt a third of a Helmholtz corner high,
which cut the build-up from 60 to 80 periods (400 ms on the G string) to 44
to 120 ms, where real détaché attacks sit; and at a bow change the bow turns
round in 20 ms rather than sagging for 80, so a sustained line dips 5 to 13
dB for a moment instead of 20 to 25. Slurred notes keep the bow going; a
counter-line changes bow every two bars. Vibrato is a folk fiddler's, 6 to
16 cents at about 5.6 Hz, on long notes after a quarter second; slides
come up from a tone and a half below; when the bow lifts the string rings
down.

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
(0.08 s), rim. A frame drum has no back, so its lowest modes radiate as a
dipole, 12 dB an octave weaker below the fundamental than a closed drum's.
It isn't tuned to the key (a boom on the tonic under every chord muddied the
bass): each maker's skin sits somewhere within a quarter octave of 80 Hz.

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
| verse | 0.51 | a boom-chick guitar, a light drum, the fiddle's long notes above the singer, the lute's answers |
| refrain | 0.68 | the drum's full foot, the fiddle's counter-melody, the lute's answers |
| turn | 0.56 | the lute quotes |
| bridge | 0.51 | a different colour under the lineage choir: no guitar, harp chords rolled low to high, the drone, the fiddle's pad, a lub-dub on the drum, then a crescendo into... |
| refrain | 0.81 | everything: the whistle's descant, the lute doubling the singer, the fiddle's pad, the full drum |
| tag | 0.55 | winding down: the whistle doubles the la-la tune, one strum a chord left to ring, rolled harp, the drone, a last open stroke |

The rules, briefly:

- **Leave room for the voice.** Comping plays 2 dB softer under words and
  2.5 dB softer under an instrument stating the tune. Nothing but the
  doubling lute sits on the sung pitch (the harp takes such a note an octave
  down). Counter-lines, descants and pads take their register from the
  section's sung range (above its top), never within three semitones of the
  tune or of another line already written, and choose each note to avoid
  seconds and tritones against them. The bass keeps to its own octave (E1 to
  B2 in D), the drone to the tonic and a softer fifth below the singer.
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
  that suits the song's chords. A strum is one note per string, 18 to 40 ms
  across, low to high down and high to low up (catching only the top strings);
  a string sounds until the pick meets it again or the hand moves to another
  chord. The lilt puts a down stroke on every beat and an up on the off-beats
  inside each metrical foot (the long-short-short of H); the strum family is
  the old faithful; compound meters get a jig's; the light pattern is a
  boom-chick (the thumb on the bass string where a foot starts, a brush of
  the upper strings between). A chop falls on a backbeat, once a bar at
  most, and the hand comes straight back up.
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
  refrain, a triplet into a louder section, a crescendo into a much louder
  one, a lub-dub under the bridge, one open stroke on the last chord.
- **Every bar its own, and a drift that stays small.** Each part draws its
  choices from its own random stream, one per bar, and its timing from where
  a note sits, not from how many came before. So patterns vary bar by bar
  (dropped up-strokes, chops, ghost strokes, turned-round picking), and a small
  change to one setting changes only what it touches. Players also breathe with
  the phrase: a little fuller through each line's middle.

## The knobs

`Params.band` is a `Band` (`songbird/band.py`); old params without it load
with the defaults, unknown names are ignored and out-of-range values
clamped.

| Field | Range | Default | What it does |
|---|---|---|---|
| lute, guitar, harp, bass, fiddle, whistle, drum, drone | 0..2 | 1 | each instrument's stem gain; 0 sits it out (its part isn't written, and the next lead takes over) |
| brightness | 0..1 | 0.5 | fingertips, gut, a breathy pipe (0) to picks, steel, an edgy bow (1): loop loss, pluck hardness, jet drive, reed spectrum |
| pattern | lilt, strum, pick, air | lilt | the accompaniment family: the melody's foot; the old faithful strum; fingerpicking (no strums, harp rolls); a slow air (rolled chords, held bass, drone, no drum) |
| density | 0..1 | 0.5 | roots, boom-chick or a strum a chord (0) to eighth-note picking, walking bass, extra ups and many fills (1): H's band plays 796, 1666 and 2007 notes at 0, 0.5 and 1 |
| swing | 0..1 | 0 | straight to a triplet lilt on each beat's off-beat half, for the singer too (compound meters keep their own lilt) |
| wear | 0..1 | 0.25 | a new, tight band (0) to an old, loose one (1): courses and reeds 1.5 to 7.5 cents apart, strings up to 4.5 cents off, timing wobble 6 to 15 ms, more bow and breath noise, a lower skin |
| ornament | 0..1 | 0.5 | plain (0) to much ornamented (1): how often cuts, rolls and slides come, and the vibrato's depth |
| arc | 0..1 | 0.75 | every section alike (0) to a strong build from the first verse to the last refrain (1) |
| lead | whistle, fiddle, lute | whistle | who states the tune where nobody sings |
| body | 0.8..1.25 | 1 | the instruments' size: a bigger body resonates lower |
| maker | any integer | 0 | seeds the instruments themselves (body modes, string quirks, the drum's skin), so a machine keeps its band across renditions |

Plausible mappings from the plan's harvest: wear from file ages, brightness
from the screen's hue and brightness, density from CPU count and memory,
swing from typing rhythm, maker from the voice hash, and the instrument gains,
pattern and ornament from the drift field. Two cautions for that work:
`pattern` and `lead` are categories, so a continuous drift value should map
onto them with some hysteresis or they will flip back and forth near a
boundary; and a gain that falls below 0.02 removes the part, which can move
other parts' roles (another instrument takes the intro), a bigger step than
the gain itself suggests.

## Stems

`render_stems()` returns a stem for each instrument that plays, named by role
(lute, guitar, harp, bass, fiddle, whistle, drum, drone), then the voice and
the choir: dry, stereo, all the same length, each fading over its last 0.3 s.
Positions: bass centre, drum just right, guitar right and lute left of
centre, harp a little left, fiddle further right and whistle left of centre;
plucked instruments carry their bodies' two-microphone width (left/right
correlation about 0.8), the drone and the drum are near mono.

The levels are set against the formant singer as `render_stems()` delivers
it (the voice at about -10.5 LUFS while singing). Measured in H, the band as a
whole sits, in LUFS while it plays:

| Section | Band before | Band now | Voice over band, before | now |
|---|---|---|---|---|
| intro | -17.1 | -17.9 | (no voice) | |
| verse 1 | -24.0 | -21.8 | 13.9 dB | 11.7 dB |
| refrain 1 | -24.3 | -18.7 | 13.1 | 7.6 |
| turn | -23.0 | -16.9 | | |
| verse 2 | -23.9 | -19.0 | 13.8 | 8.8 |
| refrain 2 | -24.3 | -16.9 | 13.2 | 5.8 |
| turn | -22.9 | -17.5 | | |
| bridge | -24.0 | -20.7 | 13.2 | 10.0 |
| refrain 3 | -24.4 | -15.7 | 13.2 | 4.6 |
| tag | -24.6 | -19.4 | 18.7 | 13.4 |

The old band sat at the same level under every sung line; the new one arcs
from an intimate first verse to a full last refrain and falls back under the
bridge. A new singer, or the mix's buses, will move the voice; the band's own
contour is the part that belongs to the arrangement.

## What the review changed

A Fable advisor reviewed the first version and measured what it found. The
changes it led to: comping was too soft under words and the tune statements
too loud, so instrumental passages were the band's loudest moments; the high
harp, a fiddle pad and the drone's D4 sat in the singer's range, and the
harp picked the sung note on the beat; every bowed slur sagged about 12 dB
and every pad note restarted from a still bow (20 to 25 dB holes); plucks were
scaled by their peak, leaving the lute at a third of the harp's loudness; the
drum rang the tonic under every chord; and, most structurally, one random
stream fed the whole band, so nudging density from 0.5 to 0.62 kept 3% of
the notes. Now each part and bar has its own stream: the same nudge keeps
86% of the notes exactly (98% if a note that moved by less than 20 ms counts
as kept), dropping the lute keeps 96%, and moving wear, brightness or the
arc keeps 98 to 100% of the notes and changes only their timing wobble, tone
or loudness.

## Checks

- `uv run pytest`: 111 tests pass. New ones measure each model against the
  numbers above (tuning, the bowed string's 1/n harmonics and attack, the
  pipe's spectrum and tonguing, the drum's modes, the reeds' beating, the
  strings' two-stage decay, courses and sympathetic strings), the band's
  knobs (old params load, clamping, density and pattern change the playing,
  swing moves only off-beats, a zeroed instrument sits out, a small change
  keeps most notes), the arrangement's arc, and that every song is arranged
  in range and replays exactly.
- Every genome in `songs/` renders from its seed params (12 of 12).
- The golden hash was updated with each change of sound, and renders stay
  byte-identical across processes.
- A full render of H takes about 16 to 20 s (it took 8.5 s with the old band;
  the budget is 40). The band is about 7.5 s of it; the drum's 196 modes are
  its costliest part.

## Limits

- Nobody has listened. The models are right by the measures above, but the
  measures are not the ear: the whistle in particular is physically inspired
  rather than a jet-bore waveguide, and the drone is additive.
- The fiddle speaks slowest on the G string (about 115 ms), where it rarely
  plays in this arrangement.
- Counter-lines are chord tones that move where the singer holds; they are
  lines, but not composed tunes.
- The band's timing is humanized and each part has its habit (the bass sits a
  hair behind, the fiddle starts early), but there is no deeper groove
  model: no push and pull that a band develops over a song.
- The last refrain carries seven instruments; it is the climax, but it is
  full.
