# The kit, hand percussion, strings and reeds

Beyond the ballad's eight ([BAND.md](BAND.md)) and the keyboards, mallets,
synthesizers and drum machines ([INSTRUMENTS.md](INSTRUMENTS.md)), a
rendition can be played by an acoustic drum kit, hand percussion (claps,
stomps, a shaker, a tambourine, a cajón), a banjo, a mandolin, a classical
guitar and a ukulele, an electric guitar through a pickup and a small valve
amp, an electric bass, a cello, a viola and a string section, a diatonic
harmonica, a pedal steel and a slide guitar, and an accordion and an English
concertina. Every one is synthesized from a physical model in code, nothing
is sampled, and every one is deterministic from its seeds, so a rendition's
FLAC still carries the whole program that played it.

Nobody but the artist can listen, so each instrument was judged by
measurement against what the real one does (its tuning, its modes and
decays, its spectrum, how it answers a harder stroke), and a Fable advisor
reviewed the plan and then each instrument by measurement.

## How they plug in

Each module under `songbird/synth/` that builds one of these exposes

    SPEC = {name: dict(family, register, place, level, poly, articulations, about)}
    render(name, notes, sr, length, rng, make, settings) -> dry mono or stereo

and the band's registry finds it by that (a module whose source defines both).
`notes` are the score's notes for that part; an instrument reads `Note.art`
for how each is played (the vocabulary is in each SPEC's `articulations` and
below) and never fails on an art it doesn't know: it plays its plain stroke.
`rng` is the part's performance randomness, `make` its maker's (the same
machine always owns the same instruments), and `settings` the band's:
brightness, wear, ornament, body (size), maker, tonic and capo, and `tempo`
where the arrangement passes it.

Levels were set against the ballad's stems in H, placed and at their levels,
by integrated loudness over the passage: a typical comping part at vel 0.6
sits where the guitar's strum does in the first refrain (-23.7 LUFS), a lead
where the whistle stating the tune does in the intro (-20.7), percussion
where the frame drum plays its full pattern (-28.4; its light pattern is
-31.5) and a bass line where the upright does (-24.1).
`tools/instrument_solos_b.py --levels --cpu` measures every instrument's
calibration part against its target, and the cost of playing it for three
minutes.

## Two engines they share

**Struck things** (`struck.py`). A bank of modes, each a complex phasor
decaying at its own rate, driven by hits that each carry their own amplitude
for every mode: where a stick lands and how long it stays on decide how much
each mode gets, so no two strokes need sound alike, and a new stroke adds to
what is still ringing, with its phase (a roll builds; a re-strike can partly
cancel). Two tracks act on all the modes at once: a bend (a hard hit
stretches a skin, so every mode goes sharp in proportion to the energy, then
relaxes) and a damping (a hand on a skin, a hi-hat pedal, a choke). Modes
that have died are skipped block by block, and modes under a twentieth, a
tenth and a fifth of the sample rate run at an eighth, a quarter and a half of
it, the slowest group's sum doubled in rate and joined by the next through
one short filter a doubling (it matches the full-rate bank to -70 dB away
from each strike's first 2 ms). 150 modes struck four times a second for
three minutes cost about a second and a half.

**A string that can move** (`stringloop.py`). `pluck.py`'s strings hold their
pitch. This one reads its loop at a fractional delay that may change every
sample (a cubic Lagrange read), set so the loop and its loss filter are
exactly one period long at the fundamental wherever the pitch goes: in tune
within half a cent from 41 Hz to 1.3 kHz, and after a slide. Anything may be
fed into it while it rings (a pick landing on a sounding string, a
hammer-on) and its loop gain may move (a palm resting on it, a finger
lifting). The banjo, mandolin, electric guitar, bass, steel and slide use it
for slides, bends, the bar's glides, tremolo picking and twang.

## The drum kit

`kit`: a kick, a snare, three toms (a 12, 14 and 16-inch set as tuned by
default), a hi-hat, a ride and a crash, played with sticks, brushes, rods or
mallets (`kit.py`, `cymbals.py`).

**Drums.** Each drum is a batter head and a resonant head joined by the air
in the shell. The air pushes their round modes apart and barely touches the
others: a snare's lowest pair sits near 180 and 330 Hz though neither head is
tuned there (Rossing, Bork, Zhao and Fystrom's measurements of a 14-inch
snare), and a tom's other modes ring at each head's own tuning a little
apart and beat as they die. The air's mass also crowds a loaded head's modes
closer than an ideal membrane's. Where the stick lands decides which modes
speak (the middle the round ones, a boom; off-centre the ones with nodal
diameters, a drier ring), and how long it stays on the head filters off the
highest: a hard stroke is short and bright, a soft one long and dull, about
an octave of brightness between a ghost note and a rim shot. A hard hit
stretches the head: the pitch starts sharp and falls back as the energy goes
(about a semitone on a tom struck hard, falling in a tenth of a second or
two), and a roll bends further. The stick's click and the skin's slap are
short noises of their own, so a snare's first 2 ms centre near 3.4 kHz and a
tom's near 1.5 kHz; the kick's beater is felt (clicking at 1-3.5 kHz, its
first milliseconds centred near 400 Hz) or, on some makers' kits, plastic
(2-5.5 kHz). Measured: the kick's
fundamental at 48-59 Hz with its second peak at 75-91 Hz, ringing 0.36-0.59 s;
toms at 150, 118 and 83 Hz gliding down to 145, 110 and 76 Hz, ringing
0.69-0.99 s; a whole kit's tunings vary by maker within a few semitones.

**The snare's wires** are strands pressed against the snare-side head. While
the head moves gently they ride on it; when it pulls away faster than their
tension can pull them after it, they fly free and slap back into it, and
every collision is a grain of rattle. So the wires buzz at the head's own
rate, thin out on a ghost note, keep sizzling a moment after the head has
settled, and answer the kick and the toms too (the air pushing that head: the
sympathetic buzz of every kit). The snare's body dies in 0.21-0.22 s with the
wires on, and the buzz lasts 0.42-0.49 s to -40 dB; its first 50 ms centre at
1.3-1.6 kHz, rising from 0.7 to 3.1 kHz from the softest stroke to the
hardest. A ghost note sits 19 dB under an accent and an octave darker. A rim
shot strikes head and hoop at once, louder and with the hoop's ring (a metal
ring's bending modes); a cross-stick is the stick's own knock (a hickory
bar's modes, damped by the hand) on the hoop, with its butt resting on the
head. The toms answer every firm kick and snare stroke faintly, about 30 dB
under a stroke of their own, as undamped toms do.

**Cymbals.** A thin bronze plate's modes come evenly spread in frequency, about
one every 21 Hz on a 20-inch ride, 19 on an 18-inch crash and 26 on 14-inch
hats, spaced as a chaotic system's are (never two too close), and below a
kilohertz in near pairs split by a fraction of a percent (a crash's slow
wobble). A plate radiates its high modes better than its low ones, so the
sound tilts up. Below 3-3.5 kHz the modes ring explicitly; above, they are too
dense to tell apart and the plate is a reverberator: the wash is an
eight-line feedback delay network, damped more at the top, fed by each
strike's burst (as bright as the contact is short) and by the low modes'
motion squared and cubed, the plate's own nonlinearity. That feed grows much
faster than the stroke, so a hard crash's top swells 10-50 ms after the strike
and dies first, and the loud phase drains the low modes faster than they
otherwise would, while a soft stroke stays dark. A ride's bell has a few
partials of its own between 0.8 and 3 kHz, long and clear. Measured: the ride
rings 8.2, 5.8 and 4.1 s (300 Hz-1 kHz, 1-3 kHz, 4-10 kHz), centred at 4.2 kHz
as struck and 2.3 kHz half a second on, from 1.9 to 4.7 kHz from a soft stroke
to a hard one; a hard crash rings 4.8, 3.1 and 2.6 s, blooms at 28 ms to a
4.9 kHz centroid and settles to 3.5 kHz, while a soft one stays at 2.4-2.9 kHz.

**The hi-hat.** Its pedal is a damping track: closed, the clamped plates ring
84 ms, centred near 9 kHz; open, they ring about two seconds; an open hat
stays open until the next hi-hat note closes it (its own length only if none
follows), and when the foot brings the plates together they clap (the chick).
Half open, the plates rattle against each other: a stream of collisions,
most while the plates move most, fewer the wider the pedal lets them apart.

**Brushes, rods and mallets.** A brush tap is a cloud of bristle strikes spread
over a few milliseconds, together a third of a stick's force: softer, smeared,
the wires answering, and a brief spray of the bristles' own noise. A sweep is
the bristles catching and slipping on the coated head: a stream of tiny
catches, more of them and harder the faster the brush moves round its arc
(fastest a little past the middle of the sweep), which is what makes a sweep
"sh" rather than hiss; a few catches shake the head enough to be heard as
strokes. Rods are a bundle of dowels, a few strikes a fraction of a
millisecond apart, lighter than a stick. Mallets stay long on a head or a
cymbal: dark, no click; their rolls swell.

**The kit together.** It is heard from the drummer's seat: the hi-hat on the
left, the ride and the floor tom on the right, the kick and snare in the
middle, the toms across, the overhead pair hearing nearly the same mix. Each piece is levelled by the loudness of its first
tenth of a second against four medium strokes, so a maker's tunings change
the kit's colour but not its balance (a drummer's: kick and snare up front,
the toms nearly with them, the cymbals 8-9 dB under). A groove of kick on 1
and 3, snare on 2 and 4 and eighth-note hats at vel 0.6 sits at -29.3 to -29.8
LUFS across makers (the frame drum's -29.5). A three-minute groove renders in
about five seconds.

## Hand percussion

`claps` and `stomps` (`hand.py`), `shaker` and `tambourine` (`shaker.py`),
`cajon` (`cajon.py`); their shared collision machinery is `rattle.py`.

**Claps.** Two hands meeting squeeze out a burst of air, and the pocket
between the palms rings: low when cupped (about 0.7 kHz), high and broad when
flat (2 kHz and more), which is most of what tells one person's clap from
another's (Repp 1987; Peltola, Erkut, Cook and Välimäki 2007). A clap is two
to four bursts over a few milliseconds through that resonance, with a crack
and the palms' thump. A group is three to eight people, each with their own
hands, strength, place and timing, their onsets spread over 10 to 25 ms
(looser when worn); the first hands land on the note and the rest follow.

**Stomps.** A heel's hard edge, then the leg's weight through the sole over
several milliseconds, the sole slapping down after it (rising over 1.5 to 4
ms, 400 Hz to 2.5 kHz: a slap, not a click), and the floor booms: boards on
joists over an air space, its lowest modes at 45 to 75 Hz and a handful more
to 400, ringing a few tenths of a second, a few people stomping together.

**Shaker and tambourine** are particles in collision (Cook's PhISEM): a
shake gives the particles energy that bleeds away in hundredths of a second,
and while it lasts they collide, more often and harder the more there is,
each collision a click that rings the shell: a crowd of small impacts, never
a smooth hiss. The shaker is, by maker, an egg (its shell near 5 and 9.5
kHz), a gourd maraca (about 64 seeds, near 3.2 kHz) or a tube of grains; the
forward stroke on the eighths is the accented one. The tambourine's jingles
are pairs of cupped discs, each ringing its own inharmonic modes and
clashing with its twin; struck, its head thumps too.

**Cajón.** A plywood box whose air breathes through the hole in its back
(83 to 92 Hz) and pushes on its thin face (first mode near 120 to 160 Hz), so
the two split as a guitar's air and top do: the palm in the middle gives the
boom (70 to 85 Hz), the fingers at the top edge a crack and the loose
corners' slap, and the snare wires behind the face (or, by maker, guitar
strings, or nothing) ride it and rattle on collision.

## Banjo and mandolin

`banjo` (`banjo.py`) and `mandolin` (`mandolin.py`), on shared fretted-string
machinery (`fretwork.py`).

**Banjo.** Four long steel strings and the short fifth, the drone, on a
drumhead. The tuning is open-G style moved to the key (the four long strings
sound the key's major chord, a capo keeping the lowest near D3; keys from C#
to F take open D's shape, as banjo players play in D); the fifth string is
tuned to the key's tonic or fifth, whichever lies nearer G4 (A4 in D), and
every note of its pitch is played on it. In tune within 1.3 cents from D3 to
A5 (2.7 worn). The light head takes the strings' energy fast: an open string
falls 60 dB in one to two seconds (D3 1.7 s, D4 1.2, the A4 drone 1.0, A5
0.6). A hard pick stretches the string, so the pitch starts up to 15 cents
sharp and falls back in about a tenth of a second (the twang: 10 cents at
velocity 1, 2 at 0.6), and the swinging tension pulls the bridge at twice
each harmonic's frequency (Politzer 2015). A metal fingerpick lets a steel
string go at once: the corner of its stroke is kept to 9-12 kHz as a roll is
played, rounding to 4 kHz only at the softest touch (a plastic thumbpick a
little rounder), so a D4's first 50 ms has its 4-8 kHz octave 6 dB under the
loudest and 8-16 kHz 28 dB under. The head's modes lie at a membrane's ratios
from a (0,1) tuned as players tune it, a resonator's tight (380-430 Hz, the
G#4-A4 tap tone), an open back's slacker (290-360), Q 20-40, radiating most
between 400 and 1800 Hz and up to 12 kHz. A resonator (bluegrass) keeps the
lows and an air mode near 200 Hz; an open back (old time) cancels the lows
12 dB an octave below the head's first mode; which one follows the part's
style (clawhammer: open back; picks: resonator), and the other way round for
a few makers. One banjo may be played both ways in a song, as the string
band's clawhammer verses and rolled refrains are: each passage by the strokes
it names, so a clawhammer verse's thumb is the thumb's flesh and a rolled
refrain's a thumbpick. Of its open strings only the fifth, never fretted,
rings in sympathy with what shares its harmonics (a D string's third harmonic
is the A drone's second); a long string would ring on through the fretted
chords and chops that stop it on a real banjo, so a stopped note is 60 dB
down a quarter second on.

**Mandolin.** Four courses of paired steel strings, G3 D4 A4 E5, 1 to 6 cents
apart as it wears (so a held note beats: 1.7-3 cents at wear 0.25, a beat
every one to one and a half seconds), met up to 2 ms apart by the flat pick.
In tune within 1.5 cents. Short tight strings on a small stiff box ring
briefly (the open G course 1.5 s, the open E 0.7, E6 0.4), which is why
mandolinists tremolo. The flat pick lets a string go at 7-9 kHz as it is
usually played, sharper the harder: an A4's first 50 ms has 2-4 kHz 11 dB
under its loudest octave, 4-8 kHz 13, 8-16 kHz 30. The box follows Cohen and
Rossing's four mandolins (2003): an oval-hole A-style (lowest body mode near
209 Hz, warmer) or an f-hole F-style (near 313 Hz, the bluegrass chop's
bark), each maker's a few percent off, radiating fairly evenly to 4 kHz
(1-4 kHz within 3.5 dB of 400-800 Hz on average, maker by maker); the G
course's fundamental is weak, as on a real one. A run of eighths is picked
down and up in turn from about 80 bpm. The chop is a chord struck hard and
choked by the relaxing fretting hand: 40 to 70 ms of chord damped over some
50 ms (20 dB down 65 ms after its peak), the pick's scrape, the box's knock;
the hand lies across all four courses, so no open course rings on after it
in sympathy (a fifth of a second on, nothing is left).

## A classical guitar and a ukulele

`nylon` and `ukulele` (`nylon.py`), built beyond the list for bossa nova,
flamenco, waltzes and the ukulele's strum. Nylon's own friction takes a
note's upper partials within a few tenths of a second (a lowpass in the
string loop, set so the fundamental still rings its full length: plain
trebles most, wound basses least). Free and rest strokes, the thumb, sul
tasto and ponticello, rasgueado, golpe, slurs, harmonics and tremolo; open
strings ring in sympathy. The classical body's air mode sits near 98 Hz and
its top's first modes near 190 and 240 Hz; the ukulele (G4 C4 E4 A4, the
fourth re-entrant) is small and bright, down 20 dB in two seconds. Both in
tune within 2 cents; strummed at vel 0.6 they sit at -23.8 LUFS.

## Electric guitar and electric bass

`electric`, `electric-crunch`, `electric-tremolo` and `ebass` (`electric.py`,
with the circuits in `amp.py` and the fretting hand in `fretboard.py`).

Six steel strings on a solid body ring long (a fundamental falls 60 dB in 6 to
11 seconds, open high e to open low E, each partial faster by its frequency),
with each maker's neck having its own dead spot between G3 and C4 (Fleischer
and Zwicker 1999). Steel is stiff: allpasses in each string's loop stretch its
partials sharp of the harmonic series as its core does (the low E's 8th
partial 7 cents, the plain G's 5, the high e's under 1, more up the neck), the
fundamental still within a tenth of a cent; and a hard pluck starts a few
cents sharp and settles as the string's swing dies. The magnetic pickup hears
the string's velocity where it sits (a comb) through its coil's resonance with
the pots and cable, worked out from the circuit, the tone knob near the top:
single coils 3 to 6 dB up near 3.5 to 6 kHz, humbuckers 4.5 to 8.5 dB up near
2.8 to 3.8 kHz (Zollner). The amp: two 12AX7 stages solved on their load lines
from Koren's triode equations (asymmetric, clamped where the grid conducts,
the second stage's coupling capacitor charging under a hard attack: the pushed
amp's breath), the Fender or Marshall tone stack (Yeh and Smith's circuit,
matching their closed form to a thousandth of a dB), a spring reverb, a
push-pull power stage nearly linear up to its ceiling (the firmer with
negative feedback) and a close-miked open-back cabinet (the cone's resonance
standing at 75 to 110 Hz over what the open back cancels below it, a presence
rise at 2 to 4 kHz, the fall past 5 or 6 kHz). The three names are three
settings of one rig on a machine: clean (within 3% of linear on a hard strum)
with a modest spring; crunch (a strum 12 to 35% from linear), the master down
so it sits as loud as clean; tremolo, the amp's (optical or bias, by maker, 4
to 7 Hz, locked to the tempo when the band gives one, dipping 11 to 16 dB). A
player dials the sound, not the knob: each setting's volume is the maker's
drive less the rig's heat (a humbucker is 7 dB hotter than a single coil, a
Fender's stack 5 to 7 dB lossier than a Marshall's), so every rig's clean is
clean and every crunch crunches. `settings["amp"]` may name a setting or give
its knobs. The bass: long-scale roundwound strings, stiffer still (the open
E's 10th partial a third of a semitone sharp: its growl; a fingered note at
0.8 starts 13 cents sharp and settles within a third of a second), through a P
or J pickup (the J loaded by its two volume pots and its tone pot) into a DI,
fingered or picked.

## Cello, viola and the string section; the harmonica

`cello`, `viola` and `strings` (`cello.py`, on `bowed.py`'s waveguide with a
primed start), and `harmonica` (`harmonica.py`).

**Bowed strings.** Left to the friction alone a cello's C string takes a
quarter of a second to settle into Helmholtz motion; a player's takes under a
tenth (Guettler and Askenfelt 1997), so once the bow has gathered speed the
string is set moving as that speed sustains. Brightness moves the bow from
over the fingerboard (0.13 of the string) toward the bridge (0.06), `tasto`
and `pont` further, the bow's weight following Schelleng's window so the level
holds while the tone moves. The bow is not clean: a hiss that pulses with each
slip sits 30 to 40 dB under the harmonics between 1 and 4 kHz (27 on the C
string), and a fresh stroke lands with a scratch, its first 30 ms of 2 to 6
kHz 6 to 8 dB over the held note's on the G and D strings; a bow change turns
round in 25 to 30 ms. A cellist's vibrato is 5 to 6 Hz and 20 to 35 cents (a
violist's 5.5 to 6.3 and 14 to 26), one motion of the hand through a phrase:
half there 0.1 to 0.2 s into a note after a rest and whole by 0.3, carried at
its width through slurs and bow changes, narrower on short notes, easing
before a rest. Shifts slide slower than a fiddler's; `swell` grows from 9 dB
down and dies back; `trem` reverses the bow 11 to 15 times a second. When the
bow leaves a stopped note before a rest the finger damps it (a T60 of 0.9 s);
an open string rings on. `pizz` plucks the string over the fingerboard through
the same body and lets it ring until that string is played again, so an
arpeggio's notes sound together. The bodies follow the published modes (a
cello's air near 100 Hz and its B1 pair near 180 and 215, a viola's near 230
and 400-460), with no hole after the B1 pair: a cello radiates well through
250 to 500 Hz, its principal formant. The section gives each line of a chord
to violins, violas or cellos by register, two or three players each, a few
cents apart and a few tens of milliseconds early or late, each with a vibrato
of their own, narrower than a soloist's and started in their own time; each
desk is heard through a stereo pair, so a chord's channels correlate 0.4 to
0.55, as a pair on a real section hears it.

**Harmonica.** A ten-hole Richter harp: the major chord on every blow hole,
the full scale only in holes 4 to 7, the gaps filled by bending (draw bends in
holes 1-6 of 1, 2, 3, 1, ½ and 1 semitones, blow bends in 8-10 of 1, 1 and 2:
Bahnson, Antaki and Beery 1998), overblows beyond. For each part the harp is
chosen that plays its notes with the fewest bends: first position for a major
tune; second (the cross harp, a fourth above) when it bends less, and in the
blues unless it bends more than half a semitone a note beyond the straight
harp; third for a dorian one. Notes that follow straight on are joined as a
player's mouth joins them: across the holes on one breath the lips slide (the
old reed dying away as the new one speaks, dips of 2-6 dB), a breath turning
from blow to draw dips 12-18 dB, the same reed again is tongued. The reed is
bright and buzzy, its harmonics within 20 dB to 6-9 kHz in the middle holes
and as bright drawing as blowing (the mouth's resonance follows the note),
brightening with the breath (from -10 dB an octave of harmonics soft to -5
hard); it speaks in 15-25 ms at mezzo-forte in the middle holes, 40 soft, 10
hard, twice as slowly an octave down. Harps are tuned sharp and sag as the
breath presses them (mezzo-forte 0-2 cents over the band, soft 4 over, hard
2-7 under), each maker's in equal temperament or a compromise one (the blow
chord's third 5 cents low), a blues player's sometimes the old Marine Band's
(its thirds 12 cents low). The throat's vibrato pulses the breath by 3-6 dB
and dips the pitch only on a reed that bends. A bent note is attacked 20-45
cents high and held by ear, 1.5-2 dB a semitone weaker and darker; a blues
`bend` holds the unbent reed, then draws down; `slide` scoops a reed that
bends or crosses the next hole onto one that doesn't; the tongue slaps chords
and splits octaves (only where there is one); the cupped hands wah and
tremble. A singer-songwriter's harp sits in a neck rack, with no hands on it.

## Pedal steel and slide guitar

`steel` and `slide` (`steel.py`, on `fretboard.py`'s strings and `amp.py`):
the country style's steel and the blues style's slide.

**The pedal steel.** Ten strings tuned to E9 (F#4 D#4 G#4 E4 B3 G#3 F#3 E3 D3
B2), stopped by a steel bar, with the standard three pedals and four knee
levers: A raises the B strings a tone to C#, B the G# strings a semitone to A,
C the E and B strings a tone; the left knee raises or lowers the E strings a
semitone, the right knee raises the F#s and lowers the D# and D. Each chord
is found as a player finds it: the bar's fret, the fewest pedals and levers,
the tightest grip, the bar near where it was; so D at the tenth fret becomes
G by pressing the A and B pedals at the same fret, the instrument's own
sound. A glide (or a bowed line's slur) is the bar sliding with no pick,
every ringing string moving with it and the pedals moving the strings that
must go by other intervals; half the glide comes before the beat, so it lands
near it (a tenth or two of a second for a few frets). A pedal bend picks a
note with its pedal or lever up and presses it in, the pitch rising a
semitone or a tone along an S over 0.15 to 0.3 s. The player blocks a ringing
string with the palm before the bar or a pedal moves under it, and picks a
slurred note again once it has rung two and a half seconds (a slur that long
would be heard fading, not moving). The volume pedal is never still. It rests
about half way down, 14 dB under its top, while the player picks, and after
each pick of a held note the foot rides it in as the string decays, so the
note stays within a few dB of its pick for a second or two (the instrument's
mark as much as its bends). A swell pulls it back 45 dB over a fifth of a
second before the pick and pushes it to the top along a raised cosine in
decibels over a third of a second to 1.2 s; the pedal is the whole
instrument's, so it takes whatever else rings with it. The bar's vibrato
rocks both ways about the fret
(5 to 6.5 Hz), which a fretting finger cannot. The strings are metal finger
picks and a thumb pick on the low ones, a chord pinched a few milliseconds
apart; the bar whirs and hisses along the wound strings as it moves (the
whir at its speed over the windings' 0.4 mm pitch), about 25 dB under a note.
Some makers' players tune the major thirds (the G# strings, the A pedal's C#)
6 to 14 cents flat toward pure thirds, the D# a little less and the F# a
third as much, as Jeff Newman's chart has them; the rest tune equal. The
pickup sits 38 to 50 mm from the bridge, single coil or humbucker, and is
wound as a steel's are, far hotter than a guitar's (15 to 19 kohm, 9 to 12 H):
on a pot volume pedal (six makers in ten), which loads it, it resonates near
1.5 to 2 kHz; on a buffered pedal a little higher. The strings keep their
highs longer than a guitar's (heavier plain strings, a steel bar and the
changer: half the electric's partial damping). The amp is clean with plenty
of headroom, set as steel players set a Twin (the middle up, the bass down,
undoing the Fender stack's scoop), with a spring reverb and a 12 or 15 inch
speaker; it is switched on a quarter of a second before it plays, and its
master volume is set on two held chords' sustain.

Measured: an equal-tempered steel in tune within 0.5 cent from B2 to D6, and
where each glide lands (within 0.3 cent); on the beat a glide from A4 to B4 is
half way (-109 cents) and it is there 40 ms later. A bend rises from -100
cents to the note in 0.27 s. A swell's pick is 34 dB under its top, which
comes 1.4 s later for a note of 2.5 s; a plain held A3 or F#4 stays within
2.5 dB of its pick for a second and a half (an E5, whose string dies faster,
falls 14 dB). The strings ring long: the fundamental's T60 is 16.8 s at B2,
11.9 at A3, 10.2 at F#5 (a solid electric's is 6-10), the fifth partial's 5.7,
5.2 and 1.9 s. An A3 through the amp is centred at 0.74 kHz at the pick and
0.43 kHz a second on, its 3rd and 4th harmonics 6 and 7 dB under the 2nd; the
pick's place and the pickup's notch its harmonics near the 6th and 9th. A
chord picked at 1.0 is 8.7 dB louder than at 0.36 (the amp stays clean). The
bar vibrato asked for (ornament 0.5) swings -21 to +13 cents about the note.

**The slide guitar.** A bottleneck on a guitar tuned open to the key (open D
or open G, retuned up to three semitones or capoed): an acoustic flat-top, a
resonator (a spun cone's few strong, ringing modes from 190 Hz to 2.3 kHz), or
an electric through the maker's small valve amp pushed a little, by the maker
(4 in 10, 3.5, 2.5) or `settings["slide"]`. The resonator's thin cone radiates
1 to 4 kHz far better than a spruce top: its body is the bright one (a hill
near 1.8 kHz, no fall above), with little below 150 Hz. The slide stops every
string at any pitch, so the steel's glide machinery moves it; a note lands 6
to 35 cents flat (with the ornament) and settles in 50 to 100 ms, a "slide"
comes up from two or three semitones under, lazily (up to 0.3 s), the vibrato
is a slide player's, wide and even either side of the note (4.8 to 6 Hz, 10
to 30 cents with the ornament, twice that asked for, on anything held 0.4 s),
and a "fall" slides away down as the note ends. A glass or brass bottleneck is
a hard stop, so the strings ring about as a fretted guitar's do (T60 2.6 to
3.4 s at 220 Hz on the flat-top, 2 to 2.6 on the resonator, whose cone takes
more); a string pressed too lightly rattles on it as a note starts; it scrapes
the wound strings as it moves, whichever are ringing. The string behind the
slide, between it and the nut, rings too: the energy that leaks past the
slide sounds it at 1/(1 - 2^(-x/12)) of the open pitch (an octave up at the
twelfth fret, a twelfth up at the seventh), falling as the slide climbs, 26 to
36 dB under the note until the player's trailing finger damps it, in 0.06 to
0.4 s by the maker's player; an electric's pickup, under the sounding length,
doesn't hear it. In an open tuning every string is a tone of the chord, so a
note picked on an open string sets the other open strings ringing in
sympathy, about 28 dB under it, until each is next picked. Each maker's slide
is levelled by a reference lick, so the body, the slide and the amp change its
colour and not its balance.

Measured: in tune within 0.7 cent on every body once landed; a plain note
lands 43 cents flat (ornament 1) and is there in 0.1 s; a slid note comes from
-180 cents and is there in 0.4 s; the vibrato asked for swings -37 to +42
cents. An E4 is centred at 0.83 kHz at the pick on the flat-top, 0.92 on the
resonator (its first four harmonics within 4 dB of each other) and 1.5 kHz on
the electric; its fundamental's T60 is 2.9 s on the acoustic bodies and 4.2
on the electric.

Levels. Each steel's amp is set as a player sets it, on the same two held
chords (an A high on the strings, a D low, the bar from the fifth fret, their
sustain after the pick), and the steel is levelled on the country style's
line under the singer as the style writes it for H's first refrain (low, D3
to B3, at half a comping part's velocity so it sits under the words): across
thirteen makers it averages -23.7 LUFS (-26.4 to -22.2, sd 1.3; comping,
-23.7), and the same rendition's picked intro, the tune an octave up, -19.8
(sd 1.3; a lead, -20.7). The slide's answers, as the blues writes them, sit
at -19.7 to -21.6 by body (a lead, -20.7, beside the harmonica it answers
with). Over a short answer a picked slide note reads a few dB under the
harmonica's, since a picked note dies and a reed sustains.

## The accordion and the concertina

`accordion` and `concertina` (`accordion.py`, their boxes in `body.py`).

**The reed.** A steel tongue riveted over a slot: the air sets it swinging
and it chops the stream into pulses. The radiated sound follows the rate of
change of that flow, so its harmonics fall slowly (an accordion reed's fifth
harmonic can stand over its fundamental): at A4 the accordion's centroid is
0.9 kHz (2.1 times its fundamental, harmonics 2 to 5 within 7 to 14 dB of
it), the concertina's 1.1 kHz. Pressed harder the pulses sharpen: from
velocity 0.2 to 1 the level rises 20 dB, the centroid goes from 0.65 to 1.2
kHz, and the pitch sags 5 cents (a free reed goes flat as the pressure rises:
Cottingham's G# reed near 421 Hz falls about 2 Hz from 0.05 to 0.85 kPa),
more for low reeds. Every note has a push and a pull reed, each tuned by hand
(a cent or two apart, more when worn), the pull reed in the reed block's small
chamber a shade darker. A low reed's pulses are heard as pulses, which is the
bass buttons' growl: its harmonics start in phase below D3 (a D2 reed's period
has a crest of 20 dB), scattering by D4, where the ear can't hear their
phase. The boxes are broad humps (the box near 240 Hz, the reed chambers'
nasal humps near 1.1 and 2.6 kHz, the concertina's near 1.6 and 3.2) with no
deep notches, and the accordion's bass side is a bigger box.

**Speaking.** A reed at rest is started by the puff of air as its pallet
lifts, and its swing grows exponentially until the slot limits it: a
logistic from 2% of full swing whose rate follows the pressure. Its
brightness follows its swing, so the fundamental comes first and the buzz as
the swing reaches through the slot, and it starts a few cents sharp. The puff
itself is heard, rushing through the slot until the tongue swings and chokes
it; after that the air past the reeds sits about 40 dB under a mezzo-forte
note and 35 under a soft one. To nine tenths at velocity 0.6, the bellows
already pressed: the accordion's A6 in 14 ms, A4 in 26, A3 in 39, D3 in 65, a
Stradella bass button in 61; the concertina's reeds 40% quicker (A4 in 16 ms,
A6 in 8). Harder is quicker (A4: 38 ms at 0.3, 22 at 0.9). When the pad
shuts the note is gone in 6 to 25 ms, with the pad's thud; a key's click is
about 28 dB under the note.

**The bellows.** One bellows drives every reed that sounds, so the pressure
follows the player's arm (the notes' velocities, held over rests shorter than
a second, a swell shaped through its note from a third of its pressure), not
the keys. Every reed drinks air, a chord more than a note and the big bass
reeds most (a bass button's reeds 1.5 litres a second at full pressure, a
middle treble reed 0.2), from a stroke of 6 to 9 litres (an accordion) or 2
to 3.2 (a concertina). The player turns the bellows at a rest once the stroke
has run 3 to 6 seconds (a concertina's 1.2 to 2.8), waiting for a strong note
if one comes soon (the oom of an oom-pah, so the new stroke accents it); at a
note's start once most of the air is used or before a held chord would run
it out; and wherever they must once all of it is. The first stroke opens
them. A turn takes 40 to 70 ms (a concertina's 30 to 50) with the pressure
dipping to a quarter, and a note held through it hands over to its other
reed, which must speak again. Measured: the calibration oom-pah turns every
3.1 to 4.3 s on the accordion and 2 to 3.2 on the concertina, every turn just
before an oom; held chords turn at their changes, a break of about 30 ms and
20 dB. 'shake' turns them on the subdivision of the beat nearest 6.5 a second
(sixteenths at 100 bpm: 6.7 Hz, 20 dB deep).

**The accordion's treble**, F3 to A6. The maker's box: two middle reeds, a
bassoon with two (LMM), a piccolo too (LMMH, the commonest), or a musette box
of three middle reeds (MMM, LMMM). Its tremolo is one of the regional tunings
(Liberty Bellows' table, the cents between the tremolo reeds and the true one
at A4: dry 0, swing 4, Irish 7, Cajun 10, Alpine 12, German and Italian 15,
French 18, old French 22, Scottish 25; a musette box 10 or more), along the
tuners' curve: 1.3 times A4's cents at A3 and below, 2/3 at A5, 4/9 at A6, so
the beats quicken toward the top, but less than the pitch does. Measured on a
French musette box (17.4 cents): the reeds at -22.0/0/+22.0 cents at A3,
-17.1/0/+17.4 at A4, -11.7/0/+12.0 at A5, -8.1/0/+7.9 at A6; its two reeds
of the violin register beat 2.8 Hz at A3 and 4.4 at A4. The player's
register: ornament sounds one middle reed (clarinet), two (violin, the
band's default) or three (musette); brightness under 0.4 adds the bassoon,
over 0.6 the piccolo. Three makers in ten set the middle and bassoon reeds in
a tone chamber (cassotto): darker.

**The accordion's left hand.** A Stradella bass button sounds its note's
pitch class on the bass (C2-B2), tenor (C3-B3) and, lighter, contralto (F#3-F4)
ranks and the chord reeds' octave, wherever it was written (a D is D2, D3 and
D4 from any octave), so a bass line breaks between B and C as a real one does;
a chord button's notes sound in the contralto's octave, F#3 to F4, and the one
above (the ranks of a professional 120-bass, after Wikipedia's Stradella bass
system). 'bass' and 'chord' name them, and the oom-pah idiom writes them for
an accordion; a plain note below the treble keyboard is a bass button alone
and a chord button when struck with others. The oom sits about 3 dB over the
pah.

**The concertina.** An English concertina, a tenor-treble (C3 to C7; the
48-key treble starts at G3): one reed a note each way, sounding the same note
pushed or pulled. The scale alternates between the hands (the notes on the
treble staff's lines at the left end, those in its spaces at the right, an
accidental with its natural, as Wheatstone laid it out), each end a small
hexagonal box of its own a little left or right. Three makers in four fit
concertina reeds, quicker and more cutting; the rest make hybrids with
accordion reeds.

**Where they play.** The concertina is the shanty's (oom-pah in the verses
and refrains, held chords in the bridge and tag, the tune in its breaks and
turns). A style may name a player another can stand in for
(`StyleDef.swaps`): for about three machines in ten the shanty crew's
squeezebox is an accordion, playing the concertina's parts with its oom-pah
on the Stradella buttons, and a lineage keeps the one it had. Sailors and
shanty crews played both.

Levels at vel 0.6: the oom-pah -23.7 LUFS on both (comping, -23.7; -23.5 to
-24.1 across six makers on the accordion, -22.7 to -23.7 on the concertina);
a slow air -22.0 and -24.2; held chords 2 to 5 dB over the oom-pah, as a
held chord is louder than a vamp. A pad pressed as hard as 0.9 peaks near
full scale placed (their low reeds' pulses give the oom-pah a crest of 16 to
18 dB).

## Idioms for the part-writer

**The kit.** An art names the piece and stroke: `kick`, `snare`, `snare-rim`
(`rim`), `snare-cross` (`cross`), `snare-ghost` (`ghost`), `snare-roll`,
`hat`, `hat-open`, `hat-half`, `hat-foot`, `ride`, `ride-bell` (`bell`),
`ride-crash`, `ride-roll`, `crash`, `crash-choke`, `crash-roll`, `tom-hi`,
`tom-mid`, `tom-lo` (and `-roll` on each), `brush-tap`, `brush-sweep`. After
any piece, `:brush`, `:rod` or `:mallet` says what plays it (`ride:brush`,
`hat:rod`, `tom-lo:mallet`); sticks otherwise. With no art, General MIDI's
percussion keys name the piece by the note's pitch (36 kick, 38 snare, 42
hat, 46 open hat, 49 crash, 51 ride...). Pitch is otherwise ignored, and a
note's length matters only for a sweep, a roll, a choke and an open hat with
nothing after it.

- Velocity is the stroke: accents 0.8-1, a backbeat 0.7-0.85, hats and ride
  0.4-0.6 with the beat stronger than its off-beats, ghost notes 0.1-0.3 (or
  `ghost` at any velocity). Vary it: the kit makes each stroke land a little
  differently, but only the part can phrase a groove.
- Rock or pop: `kick` on 1 and 3 (and the and of 3), `snare` 0.8 on 2 and 4,
  `hat` eighths (0.55 on the beat, 0.4 off), `crash` with a `kick` on the
  first beat of a section, a fill on `tom-hi`, `tom-mid`, `tom-lo` in
  sixteenths into it. An open hat on the and of 4 (`hat-open`, closed by the
  next `hat` or `hat-foot`) lifts a bar.
- A country train beat: `snare` sixteenths at 0.3-0.45 with accents 0.7 on 2
  and 4, `kick` on 1 and 3, `hat-foot` on 2 and 4; on brushes, `brush-tap`.
- Folk and quiet songs: rods (`snare-cross:rod` or `snare-cross` on 2 and 4,
  `hat:rod` eighths, a `kick:rod` on 1), or a `tom-lo:mallet` pulse.
- A brush ballad: a `brush-sweep` a beat (or two) long starting on every beat,
  vel 0.5; `brush-tap` 0.55 on 2 and 4; `kick` 0.3 on 1 and 3 (feathered);
  `hat-foot` on 2 and 4; `ride:brush` in the ride's rhythm for a lift.
- Jazz or swing: `ride` in the spang-a-lang (1, 2 and its swung and, 3, 4 and
  its swung and), `hat-foot` on 2 and 4, a feathered `kick`, `snare` ghosts
  and comps; `ride-bell` for a chorus.
- Soul and funk: ghost notes (`snare` 0.15-0.25) on the e's and a's around a
  0.85 backbeat, sixteenth hats with the accents on the beat.
- Builds and endings: `crash-roll` (a mallet swell) over a bar into the
  downbeat, `tom-lo-roll:mallet` under it, `snare-roll` over the last beat;
  `crash-choke` for a stop, its note's length the time until the hand grabs it.
  Tom rolls hold steady; write a swell with rising velocities. `kick-dead`
  buries the beater (a short, choked kick).

**Hand percussion.** Pitch is ignored; the art names the stroke, and an
instrument given another's art plays its own plain stroke.

- A stomp-clap: `stomps` (`stomp`) on 1 and 3, `claps` (`clap`) on 2 and 4,
  vel 0.7-0.85; a lone clapper is `clap-solo`, a finger snap `snap`.
- `shaker` in steady eighths or sixteenths, vel 0.5-0.6 with the beat a
  little stronger (the forward stroke falls on the eighths when the band
  passes a tempo); `shaker-roll` for a held shake.
- `tambourine` (the palm on the head) on 2 and 4, `tambourine-shake` in
  eighths between or held through a chorus, `tambourine-tap` for light
  fingertip jingles, `tambourine-roll` for a thumb roll.
- `cajon`: `cajon-bass` on 1 and the and of 2, `cajon-slap` on 2 and 4,
  `cajon-tap` ghosts on the sixteenths between, `cajon-mid` for a tone
  between bass and slap.

**Banjo.** The drone string is the key's tonic or fifth nearest G4 (A4 in
D; `banjo.fifth_string(tonic)` says which); a note of its pitch plays on it.

- Scruggs's forward roll: eighths, thumb-index-middle repeating across a
  bar (T I M T I M T M, over strings 3 2 1 5 2 1 5 1), the thumb on the low
  notes and the drone (`thumb`, or `pick`: the fifth string is the thumb's),
  fingers `pick`; the thumb's notes (the 3-3-2) a little stronger; change the
  shape with the chord.
- Clawhammer ("bum-ditty"): a struck tune note on the beat (`claw`), a brush
  across two or three strings on the next (`brush`, notes sharing a start, or
  spread 10 ms apart low to high), and the thumb on the drone on its and
  (`thumb`); in a slow tune the same in eighths and sixteenths.
- A part may do both: each passage is played by the strokes it names.
- `hammer` and `pull` sound a note without a pick (the left hand); `slide`
  comes up from two frets below; `mute` or `chop` for a choked strike.

**Mandolin.**

- The chop: the whole chord (three or four notes sharing a start, art `chop`)
  on 2 and 4, vel 0.55-0.7; nothing else needed for a bluegrass backbeat.
- Tremolo: a long melody note with art `tremolo` is filled with picks, nine to
  fourteen a second; quick notes plain (picked down and up in turn from about
  80 bpm) or `down` and `up`. A style's lead, quote or counter-line on the
  mandolin tremolos its notes of a beat and a half or more itself.
- Chords strummed `down` on the beat and `up` between; `hammer`, `pull`,
  `slide` as on the banjo.

**Classical guitar and ukulele.** A bossa: the `thumb` on the root and fifth
on 1 and 3, the fingers pinching the chord (plain notes sharing a start) in
the syncopation between; a waltz: `thumb` on 1, a chord on 2 and 3; flamenco:
`rasgueado` on the accents, `down` and `up` between, a `golpe` on the
offbeats; a melody in `rest` strokes over plain arpeggio notes; `harmonic`
for a last note. The ukulele's island strum: down, down-up, up-down-up (arts
`down`, `up`).

**Electric guitar and bass.** Clean arpeggios (`electric`, plain notes,
ringing), a crunch riff (`electric-crunch`, root-fifth power chords with
`mute` on the chugged eighths and open accents), tremolo chords held a bar
(`electric-tremolo`). `bend` bends up to the written pitch from a tone below,
`slide` comes up from two or three frets below, `vibrato` on a long lead
note, `chop` a fully muted strum on 2 and 4 for a funk or reggae backbeat.
The bass: root and fifth, or walking quarters; `pick` for a brighter attack,
`mute` for short staccato notes, `ghost` a dead note, `slide` into a root.

**Bowed strings.** `cello` and `viola` are monophonic (a double stop goes to a
second string); `strings` takes chords, so write a pad as the chord's notes
held together (`swell` on the first to fade it in). `slur` continues the bow
over a new note, `slide` shifts up into a note, `swell` swells through it,
`pizz` plucks, `trem` bows a tremolo, `tasto` and `pont` move the bow away
from or to the bridge for a note. Keep the cello low (C2-D4 is its voice).

**Pedal steel.** Swells in the alto under the singer (`swell` on each long
note or chord: two or three notes of a grip sharing a start ring best), the
moves between them `slur` (or `glide`), so the bar and pedals carry them; a
chord change the pedals can make at one fret is the steel's own sound (D
A4 D5 F#5 to G B4 D5 G5). `slide` slides a note in from a fret or two under,
`bend` bends it in with a pedal, `vibrato` for a deeper bar vibrato, `fall`
for the bar leaving a last note, `mute` for a blocked one. Keep it B2 to E6.

**Slide guitar.** Answers and a held tone: `slide` into the long notes,
`glide` (or `slur`) between notes of a run, `vibrato` on a held one, `fall` to
end, `swell` for a note let bloom. It plays one line (a chord shares one
slide position or open strings); the open strings of its tuning (the key's
root and fifth) ring free under it.

**Harmonica.** Write the tune in the song's key; the harp is chosen for it.
Notes written one after another are played legato across the holes, so `slur`
is only needed to keep a repeated reed swinging. `bend` on a note approached
from above (the blues third and fifth), `wah` on a long note (the hands
opening), `trem` (hand tremolo), `slap` and `chord` for tongue-blocked chords
(on the top note alone or on all the chord's notes starting together: one
breath either way), `octave` for a tongue-split octave; `wah` and `trem` are
ignored in the songwriter's rack.

**Accordion and concertina.** One bellows plays everything, so velocity is the
bellows' pressure: all the notes sounding together share the loudest one's.
- Oom-pah: a bass note on the strong beats (root, then fifth) and a short
  chord between; in six-eight each dotted beat an oom and a chord on its other
  two eighths (oom-pa-pa), in a waltz oom-pah-pah. On the accordion write the
  oom `bass` and the pah `chord` (the idiom does): the left hand's buttons,
  whatever octave they are written in.
- Held chords: the notes together, `swell` on a phrase's first to press into
  it; the bellows turn where the chords change if they can.
- A tune on the accordion's treble (F3 up; below it the left hand plays), or
  anywhere on the concertina; `slur` for legato, `shake` on a long note for a
  bellows shake. The accordion's register comes from the band: ornament for
  the tremolo reeds (0.7 and up a musette, on a box that has three), brightness
  for the bassoon and piccolo.

## Levels and cost

Each instrument's calibration part at vel 0.6, rendered, placed and levelled
by its SPEC (integrated loudness; targets from the ballad's stems in H:
comping -23.7, lead -20.7, bass -24.1, percussion -28.4), and the CPU seconds
a three-minute part costs on the M1 Max:

| Instrument | Part | LUFS | Target | 3 minutes, CPU s |
|---|---|---|---|---|
| kit | kick 1 and 3, snare 2 and 4, eighth hats | -29.5 | -28.4 | 3.4 |
| claps | 2 and 4 | -28.7 | -28.4 | 0.1 |
| stomps | 1 and 3 | -28.6 | -28.4 | 0.4 |
| shaker | sixteenths | -30.3 | -31.4 (its own) | 0.2 |
| tambourine | 2 and 4 with shakes | -30.3 | -30.4 (its own) | 0.5 |
| cajon | bass, slaps, ghosts | -28.3 | -28.4 | 0.7 |
| banjo | forward roll | -23.8 | -23.7 | 1.3 |
| banjo | a break (the tune inside rolls, as a lead) | -21.4 | -20.7 | |
| mandolin | strums, chops on 2 and 4 | -23.7 | -23.7 | 1.8 |
| mandolin | an air in tremolo (as a lead) | -22.6 | -20.7 | |
| nylon | strummed chords | -23.8 | -23.7 | 5.1 |
| ukulele | island strum | -23.8 | -23.7 | 4.5 |
| electric | strummed and picked | -23.8 | -23.7 | 2.9 |
| electric-crunch | riff | -23.1 | -23.7 | 3.4 |
| electric-tremolo | held chords | -23.3 | -23.7 | 2.7 |
| ebass | root and fifth | -23.3 | -24.1 | 1.1 |
| cello | held bass line | -23.3 | -23.7 | 1.6 |
| viola | held line | -23.6 | -23.7 | 1.5 |
| strings | four-note pad | -23.1 | -23.7 | 8.8 |
| harmonica | melody | -21.4 | -20.7 | 0.8 |
| steel | the country style's line under a singer | -23.1 | -23.7 | 2.6 |
| slide | answers at the ends of lines | -19.9 | -20.7 (lead) | 1.1 |
| accordion | oom-pah on the bass and chord buttons | -23.7 | -23.7 | 2.1 |
| concertina | oom-pah | -23.7 | -23.7 | 1.3 |

These instruments are not in `tests/test_instrument_specs.py`: its one
generic part per role (a four-note comping chord four times a bar, a kit
groove for all percussion) isn't what they play (a cello or a viola asked for
four-note chords reads 5 to 7 LU hot, claps given every hat eighth 3 to 5).
Each is levelled on its own typical part (`LEVELS` in
`tools/instrument_phrases_b/`), and `tools/instrument_solos_b.py --levels`
checks them.

## For the mix

The mix (`mixing.py`) gives each stem a channel strip by its name:

- `kit` has its own: a 30 Hz high-pass (the frame drum's 40 took 0.6-1.3 dB
  more off a kick's 40-80 Hz), the frame drum's cut of boxiness at 420 Hz but
  not its dip of the top (the cymbals' air), a compressor slower to grab (20
  ms against 4: a kit's transients are its point), half the band's room.
- `banjo` and `mandolin` have their own: they comp, so unlike the lute's
  strip, which steps back 3 dB under the voice as for a doubling of the tune,
  they don't duck. The banjo: a 90 Hz high-pass, 1 dB out at 2.8 kHz where
  the voice's consonants are (the band's own dip does the rest while the
  voice sings), a compressor slow to grab (15 ms) that leans only on what
  stands 5 dB out of its bar, so the picks keep their edge and a roll its
  accents; a little less room. The mandolin: a 110 Hz high-pass and a gentle,
  slow compressor (20 ms), nothing taken from its bark.
- `cello`, `viola` and `strings` take the strings' strip: the fiddle's
  treatment with a 45 Hz high-pass in place of its 180 Hz, so a cello keeps
  its low octaves, and its 1.5 dB cut for boxiness at the cello's B1 boom
  (190 Hz), not in the formant above it.
- `stomps`, `cajon`, `claps`, `shaker` and `tambourine` take the frame drum's
  strip (a 40 Hz high-pass: a stomp's boom and a cajón's bass kept).
- `harmonica` has its own: a 180 Hz high-pass, 1.5 dB of honk out near 1 kHz,
  its breath's top softened, 2 dB back under the voice like a lead line, and
  nothing taken from its presence near 3 kHz, which its reed makes itself
  (the free reeds' strip takes 2 dB there).
- `electric`, `nylon` and `ukulele` take the guitar's strip, `ebass` the
  bass's.
- `steel` and `slide` have strips of their own, since the fiddle's 180 Hz
  high-pass would take the steel's low strings (B2 is 123 Hz) and its 2 dB
  duck under the voice would fight the steel's own volume pedal. The steel's
  high-passes at 70 Hz, clears the voice's presence (2.6 kHz, -2
  dB), sends to the room generously (1.2) and neither compresses nor ducks;
  the slide's keeps the guitar's weight (70 Hz), clears its box and the
  voice's presence and steps back 1.5 dB under the voice, as a lead line
  answering it does.
- `accordion` and `concertina` have a strip of their own (`squeezebox`, as do
  a melodeon and a bandoneon by name): the free reeds' strip would
  high-pass them at 140 Hz, taking the Stradella bass's two lowest octaves
  (65-123 Hz) and thinning the concertina's oom; theirs is the reed treatment
  with a 50 Hz high-pass, the box's hump near 250 Hz eased, and a 1 dB step
  back under the voice (they mostly comp; the harmonica steps back 2).

## Limits

- Nobody has listened. The models are right by the measures above, but the
  measures are not the ear.
- The pedal steel's level differs by maker by up to 4 dB on its swelled line
  (sd 1.3: how slowly each player swells, which pickup and pedal), and a
  picked
  note's attack stands about 20 dB over its loudness, so a picked steel line's
  placed stem peaks near full scale (the stems are floats; the mix brings the
  band down to the voice). Its pedals move no other string (a real steel's
  "cabinet drop" flattens the others a few cents), and it plays E9 only (no
  B6 or universal neck). The slide plays one line at a time (a chord shares
  one slide position or open strings), and nobody has heard how loud the
  ring behind the slide or the slide's scrape should be: they are set by
  judgement, 26-36 and 20-30 dB under a note.
- In the indie style the electric guitar sits well under the acoustic guitar:
  its parts are two or three strings at 0.5-0.58. Firmer velocities, or the
  verse on the amp's tremolo (`electric-tremolo`, held chords) as the style's
  own description has it, would bring it up; that is the artist's choice.
- The electric's stiffness allpasses are matched at one partial (the one
  nearest 900 Hz): those below come within a fifth of a real string's
  stretch, those above fall short (the bass E's 20th is 66 cents sharp, a
  real one's about 128), where they have mostly died away. The Fender voicing
  is the '59 Bassman's stack driven from a plate as a blackface's is, not a
  blackface Deluxe's own parts: its scoop sits near 800 Hz rather than 400.
- The harmonica's lowest holes (1-3) keep their fundamental as the strongest
  harmonic, where a real harp's third and fourth lead, and its bent notes are
  somewhat darker than a real one's. No style yet writes its bends, wahs or
  chords.
- The string section is two or three players to a line, a chamber group's
  sound more than an orchestra's: its held notes beat by 6-7 dB over a couple
  of seconds.
- A bowed note ends with the bow lifted, never stopped on the string, the
  open strings don't ring in sympathy, and a shift's glide isn't S-shaped.
- The banjo's top octave: a metal-picked D4's 8-16 kHz is 28 dB under its
  loudest octave in its first 50 ms, where a real banjo's is perhaps 18-24;
  the string's own loss per trip takes the rest, and making it less lossy
  moves it only 1 dB.
- The mandolin's chop falls 40 dB in about 90 ms, where a real box's air
  mode (Q 15-25) should carry a quiet thunk on to 140-180 ms: the modelled
  box's low modes stand far under its upper ones in time, and a knock three
  times as strong doesn't change it. The chop's onset is only 2.5 dB over a
  roll's pick (a real chop leads by 5-7) while its loudness sits 3.5 dB under
  the guitar, as it should: both at once want a chop shorter and sharper
  than 40-70 ms.
- The banjo has no note-to-note unevenness (a partial on a head mode dies
  fast and loud, one between rings on quieter: ±2-3 dB), no slow wander in
  the rolls' timing (only their jitter, 6-8 ms as a Scruggs-style picker's)
  and no clawhammer lilt (55:45). Its and the mandolin's microphone pair
  hears half the body's upper modes alike (`body.impulse_response(alike=)`),
  so the mono sum keeps level with one channel above 1.25 kHz, but a
  third-octave can still stand 4 dB apart (2 would be better); the other
  bodies, the ballad's among them, hear every mode their own way.
- The kit is at the frame drum's level: a rock or pop arrangement will want
  it several dB louder (the mix's balance).
- The kit is heard from the drummer's seat (hi-hat left); an audience's view
  is the mirror image.
- The concertina is an English one only: no Anglo, whose buttons sound one
  note pushed and another pulled, so its bellows follow the tune (the bounce
  of Anglo oom-pah); no duet. The accordion is a piano accordion with a
  Stradella bass: no chromatic button box, no one-row Cajun melodeon, no free
  bass. A chord button's notes are the notes written, folded into its octave,
  not a fixed triad, seventh or diminished button.
- An accordion's register is the band's (ornament and brightness) for the
  whole part; a player switches between sections. The bellows' push is no
  stronger than their pull, and there is no bellows vibrato or bellows noise.
  A concertina or accordion in a country waltz (the 1940s Opry bands had one
  where later ones had a steel) would want a swap of country's own.
- A low reed's pulses give the squeezeboxes a crest of 16 to 18 dB: a loud pad
  peaks near full scale in its stem (the mix's compressors and the master's
  limiter take it).
- There are two modal engines: `struck.py` (modes driven by strikes, each
  with its own amplitudes, multirate) and `modal.py` (resonators driven by a
  signal, INSTRUMENTS.md). They could be one.
