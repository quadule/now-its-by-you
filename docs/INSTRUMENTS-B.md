# More instruments: a kit, hand percussion, fretted and electric strings, bowed strings and reeds (2026-09-26)

The band had eight instruments, all from a small acoustic folk band. After
hearing it the artist asked for "more variation in arrangement and genre", so
a rendition can now also be played by an acoustic drum kit, hand percussion
(claps, stomps, a shaker, a tambourine, a cajón), a banjo, a mandolin, a
classical guitar and a ukulele, an electric guitar through a pickup and a
small valve amp, an electric bass, a cello, a viola and a string section, a
diatonic harmonica, a pedal steel and a slide guitar. (An accordion and a
concertina were begun and are not here: their builders were cut off before
committing them. Another set, the piano,
electric piano, organ, mallets, synthesizers and a drum machine, is described
elsewhere.) Every one is synthesized from a physical model in code, nothing
is sampled, and every one is deterministic from its seeds, so a rendition's
FLAC still carries the whole program that played it.

As with the band, nobody but the artist can listen, so each instrument was
judged by measurement against what the real one does (its tuning, its modes
and decays, its spectrum, how it answers a harder stroke), and a Fable
advisor reviewed the plan and then each instrument by measurement; what the
reviews changed is at the end. The renders in `renders/production/instruments/`
(listed in its README-b.txt) are for the ears.

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

Levels were set against today's stems in H, placed and at their levels, by
integrated loudness over the passage: a typical comping part at vel 0.6 sits
where the guitar's strum does in the first refrain (-23.7 LUFS), a lead where
the whistle stating the tune does in the intro (-20.7), percussion where the
frame drum does (-29.5, from -31.5 light to -28.4 full) and a bass line where
the upright does (-24.0). `tools/instrument_solos_b.py --levels --cpu` measures
every instrument's calibration part against its target, and the cost of
playing it for three minutes.

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
short noises of their own; the kick's beater is felt (clicking at 1-3.5 kHz)
or, on some makers' kits, plastic (2-5.5 kHz). Measured: the kick's
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
middle, the toms across. Each piece is levelled by the loudness of its first
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
several milliseconds, and the floor booms: boards on joists over an air
space, its lowest modes at 45 to 75 Hz and a handful more to 400, ringing a
few tenths of a second, a few people stomping together.

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

Levels at vel 0.6, by each instrument's own groove: claps -28.7 LUFS, stomps
-28.6, cajón -28.3 (the frame drum's full pattern is -28.4); the shaker and
tambourine sit quieter by their SPECs' own targets (-31.4 and -30.4), at
-30.3 each.

## Banjo and mandolin

`banjo` (`banjo.py`) and `mandolin` (`mandolin.py`), on shared fretted-string
machinery (`fretwork.py`).

**Banjo.** Four long steel strings and the short fifth, the drone, on a
drumhead. The tuning is open-G style moved to the key (the four long strings
sound the key's major chord, a capo keeping the lowest near D3; keys from C#
to F take open D's shape, as banjo players play in D); the fifth string is
tuned to the key's tonic or fifth, whichever lies nearer G4 (A4 in D), and
every note of its pitch is played on it. The light head takes the strings'
energy fast: an open string falls 60 dB in one to two seconds. A hard pick
stretches the string, so the pitch starts up to 15 cents sharp and falls back
in about a tenth of a second (the twang), and the swinging tension pulls the
bridge at twice each harmonic's frequency (Politzer 2015). The head's modes
lie at a membrane's ratios from a (0,1) of 300-400 Hz, Q 20-40, radiating
most between 400 and 1800 Hz and up to 12 kHz. A resonator (bluegrass) keeps
the lows and an air mode near 200 Hz; an open back (old time) cancels the
lows 12 dB an octave below the head's first mode; which one follows the
part's style (clawhammer: open back; picks: resonator), and the other way
round for a few makers.

**Mandolin.** Four courses of paired steel strings, G3 D4 A4 E5, 1 to 6 cents
apart as it wears (so a held note beats), met up to 2 ms apart by the flat
pick. Short tight strings on a small stiff box ring briefly (the open G
course 1.5 s, the high E half a second), which is why mandolinists tremolo.
The box follows Cohen and Rossing's four mandolins (2003): an oval-hole
A-style (lowest body mode near 209 Hz, warmer) or an f-hole F-style (near 313
Hz, the bluegrass chop's bark), each maker's a few percent off; the G course's
fundamental is weak, as on a real one. The chop is a chord struck hard and
choked at once: 30 to 60 ms of chord, the pick's scrape, the box's knock.

Levels at vel 0.6: a forward roll -25.2 LUFS, the chop -24.1 (comping,
-23.7).

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

Six steel strings on a solid body ring long (a fundamental falls 60 dB in 6
to 10 seconds mid-neck, each partial faster by its frequency), with each
maker's neck having its own dead spot between G3 and C4 (Fleischer and
Zwicker 1999). The magnetic pickup hears the string's velocity where it sits
(a comb) through its coil's resonance with the pots and cable, worked out from
the circuit: single coils near 4 kHz, humbuckers near 3 (Zollner). The amp:
two 12AX7 stages solved on their load lines from Koren's triode equations
(asymmetric, clamped where the grid conducts, the second stage's coupling
capacitor charging under a hard attack: the pushed amp's breath), the Fender
or Marshall tone stack (Yeh and Smith's transfer function), a spring reverb, a
push-pull power stage and a speaker cabinet. The three names are three
settings of one rig on a machine: clean with a modest spring; crunch, the
second stage and power valves breaking up, the master down so it sits as
loud as clean; tremolo, the amp's (optical or bias, by maker, 4-7 Hz, locked
to the tempo when the band gives one). `settings["amp"]` may name a setting
or give its knobs. The bass: long-scale roundwound strings through a pickup
into a DI, fingered or picked.

Levels at vel 0.6: clean -24.1, crunch -23.4, tremolo -24.1 LUFS (comping),
the bass's root-fifth line -23.3 (-24.1).

## Cello, viola and the string section; the harmonica

`cello`, `viola` and `strings` (`cello.py`, on `bowed.py`'s waveguide, which
gained a primed start without changing its old outputs), and `harmonica`
(`harmonica.py`).

**Bowed strings.** Left to the friction alone a cello's C string takes a
quarter of a second to settle into Helmholtz motion; a player's takes under a
tenth (Guettler and Askenfelt 1997), so once the bow has gathered speed the
string is set moving as that speed sustains. Brightness moves the bow from
over the fingerboard (0.13 of the string) toward the bridge (0.06), `tasto`
and `pont` further, the bow's weight following Schelleng's window so the
level holds while the tone moves. A cellist's vibrato is 5 to 6 Hz and 20 to
35 cents (a violist's 5.5 to 6.3 and 14 to 26); shifts slide slower than a
fiddler's; `trem` reverses the bow 11 to 15 times a second; `pizz` plucks the
string over the fingerboard through the same body. The bodies follow the
published modes (a cello's air near 100 Hz and its B1 pair near 180 and 215,
a viola's near 230 and 400-460). The section gives each line of a chord to
violins, violas or cellos by register, two or three players each, a few cents
apart and a few tens of milliseconds early or late, each with its own vibrato.

**Harmonica.** A ten-hole Richter harp: the major chord on every blow hole,
the full scale only in holes 4 to 7, the gaps filled by bending (draw bends
in holes 1-6 of 1, 2, 3, 1, ½ and 1 semitones, blow bends in 8-10 of 1, 1
and 2: Bahnson, Antaki and Beery 1998), overblows beyond. For each part the
harp is chosen that plays its notes with the fewest bends: first position
for a major tune, second (the blues harp, a fourth above) only when the tune
has the flat seventh, third for a dorian one. The reed's tone brightens with
the breath, speaks in 10 to 30 ms, and differs drawing and blowing; a bent
note is approached from the unbent reed, darker; the tongue slaps chords and
splits octaves, and the hands wah and tremble.

Levels: a cello's held bass line -23.0 LUFS and the section's pad -23.8
(comping, -23.7); the harmonica's melody -21.0 (a lead, -20.7).

## Pedal steel and slide guitar

`steel` and `slide` (`steel.py`, on `fretboard.py`'s strings and `amp.py`).
They replace the stand-ins (the bowed fiddle model had played both): the
country style's steel and the blues style's slide are these now.

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
instrument's, so it takes whatever else rings with it. The bar's vibrato rocks both ways about the fret
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
with). In the tour's country rendition (ada, 2026-09-27)
the steel reads -17.9 LUFS in the intro, -20.0 in the verse's fills and -21.3
under the refrain, where its stand-in read -13.7, -16.5 and -19.5, and the
guitar -25.2, -24.1 and -22.6. In the blues rendition the slide's three
two-note answers are at their loudest (400 ms) -25.8 to -25.0 LUFS, the
harmonica's -22.3 and -20.9: a picked note dies, a reed sustains.

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
D); a note of its pitch plays on it.

- Scruggs's forward roll: eighths, thumb-index-middle repeating across a
  bar (T I M T I M T M), the thumb on the low notes and the drone (`thumb`),
  fingers plain (`""` or `pick`); change the shape with the chord.
- Clawhammer ("bum-ditty"): each beat a struck tune note (`claw`, an eighth),
  a brush across two or three strings on the and (`brush`, notes sharing a
  start), and the thumb on the drone on the last sixteenth (`thumb`).
- `hammer` and `pull` sound a note without a pick (the left hand); `slide`
  comes up from two frets below; `mute` or `chop` for a choked strike.

**Mandolin.**

- The chop: the whole chord (three or four notes sharing a start, art `chop`)
  on 2 and 4, vel 0.6-0.75; nothing else needed for a bluegrass backbeat.
- Tremolo: a long melody note with art `tremolo` is filled with picks, nine to
  fourteen a second; quick notes `down` and `up` alternating.
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
`bend` on a note approached from above (the blues third and fifth), `wah` on
a long note (the hands opening), `trem` (hand tremolo), `slap` and `chord`
for tongue-blocked chords (three notes sharing a start), `octave` for a
tongue-split octave, `slur` to join notes on one breath.

## Levels and cost

Each instrument's calibration part at vel 0.6, rendered, placed and levelled
by its SPEC (integrated loudness; targets from today's stems in H:
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
| banjo | forward roll | -25.2 | -23.7 | 1.1 |
| mandolin | chop on 2 and 4 | -24.1 | -23.7 | 1.3 |
| nylon | strummed chords | -23.8 | -23.7 | 5.1 |
| ukulele | island strum | -23.8 | -23.7 | 4.5 |
| electric | strummed and picked | -24.1 | -23.7 | 2.4 |
| electric-crunch | riff | -23.4 | -23.7 | 3.1 |
| electric-tremolo | held chords | -24.1 | -23.7 | 2.4 |
| ebass | root and fifth | -23.3 | -24.1 | 1.0 |
| cello | held bass line | -23.0 | -23.7 | 1.4 |
| strings | four-note pad | -23.8 | -23.7 | 6.1 |
| harmonica | melody | -21.0 | -20.7 | 0.7 |
| steel | the country style's line under a singer | -23.1 | -23.7 | 2.6 |
| slide | answers at the ends of lines | -19.9 | -20.7 (lead) | 1.1 |

The other new set's test measures every instrument with one generic part per
role (a four-note comping chord four times a bar, a kit groove for all
percussion). By it the kit, mandolin, electric clean, bass, harmonica and
cajón are within 1 LU, but a cello and a viola asked to play four-note chords
read 5 and 7 LU hot, the string section 2.5, the banjo 2.4, crunch and
tremolo 2.1-2.3, and claps, stomps and tambourine given every hat eighth 3.4
to 4.9: those parts aren't what these instruments play. A single test for
both sets should use each instrument's own typical part (as `LEVELS` in
`tools/instrument_phrases_b/` does) or its SPEC's own loudness.

## For the mix

The mix (`mixing.py`) gives each stem a channel strip by its name, and has
none yet for most of these, so today they fall where their names happen to
point:

- `kit` falls to the generic strip, whose 60 Hz high-pass takes about 5 dB off
  a 50 Hz kick. It wants a strip of its own: a high-pass near 30 Hz, a
  compressor slower to grab than the frame drum's (a kit's transients are its
  point), a send to the room of about half the band's.
- `cello`, `viola` and `strings` fall to the fiddle's strip, whose 180 Hz
  high-pass removes a cello's two lowest octaves; they want the fiddle's
  treatment with a high-pass near 50 Hz (35 for a section with cellos).
- `stomps` and `cajon` fall to the generic strip, thinning a stomp's boom
  (40-150 Hz) and a cajón's bass; the frame drum's (a 40 Hz high-pass) suits
  them, as it already suits the shaker and tambourine; the claps too.
- `banjo` and `mandolin` fall to the lute's strip, which ducks 3 dB under the
  voice as for a doubling of the tune: right when they double it, a little
  shy when they comp.
- `electric`, `harmonica`, `accordion` and `concertina` fall to the generic
  strip, which does them no harm; `ebass` to the bass strip.
- `steel` and `slide` have strips of their own. They had fallen to the
  fiddle's, whose 180 Hz high-pass took the steel's low strings (B2 is 123 Hz)
  and whose 2 dB duck under the voice fought the steel's own volume pedal:
  the steel's high-passes at 70 Hz, clears the voice's presence (2.6 kHz, -2
  dB), sends to the room generously (1.2) and neither compresses nor ducks;
  the slide's keeps the guitar's weight (70 Hz), clears its box and the
  voice's presence and steps back 1.5 dB under the voice, as a lead line
  answering it does.

The solo tool's demos borrow a suitable strip where the mix has none (the
README says which), so they sound as these will once the mix has its own.

## What the reviews changed

A Fable advisor reviewed the plan before anything was built, with numbers of
its own. The cymbals were to have had a wash of band-limited noise whose
power followed the strokes; it warned that would read as hiss, since a
plate's top is hundreds of partials beating against each other, and
suggested the reverberator fed by the low modes' nonlinearity, which gives
the bloom for free and a harder stroke a brighter one. It also asked for the
near pairs of low modes, the radiation tilt, the two-stage decay, snare wires
driven by collisions rather than by a smooth envelope of the head's speed
(a rattle, not an amplitude-modulated hiss), the measured snare head pairs
in place of one ratio for every mode, the half-open hi-hat as a stream of
collisions, the brush sweep as a stream of bristle catches, and the hi-hat
staying open until its next note; each is in. Its targets (tom and kick
tunings and decays, a crash's bloom of 20-50 ms, cymbal centroids, the snare
body's 0.15-0.25 s with its wires on) are what the numbers above were
measured against.

A second review measured the kit and found: cymbal mallet rolls 15-50 dB
under a stick crash (a mallet's contact had been set as on a skin, and the
bloom was measured against the part's loudest stroke); no stick click on any
drum (the clicks sat 25-30 dB under the modes); snare wires that rattled for
a tenth of a second and then hissed; half-open hats reduced to sparse clicks
after 50 ms; a ride whose ping never rang down into its wash; overheads
whose channels hardly correlated (0.14-0.40); brush sweeps that dipped 20 dB
inside every beat; press rolls with 70 ms holes; a crash at time zero for
rolls; and an art vocabulary where "floor-tom", "splash" or "open-hat" became
snare strokes. All are fixed: a snare's first 2 ms now centre near 3.4 kHz
and a tom's near 1.5 kHz (a felt-beater kick's stays low, near 400 Hz), the
wires collide on and ring as their own strands, the ride's high partials
drain into the wash, the overhead pair hears nearly the same mix, sweeps flow
when they follow one another. The builders' own reviews did not run: the
session's limit stopped them.

The pedal steel and the slide were reviewed by measurement by a Fable
advisor, given the models, the measurements and the solo renders. For the
steel it found: notes that decayed like a guitar's, where a player's foot
rides the volume pedal in after every pick (in the intro the tune's first
phrase was 25 dB down in 1.2 s); a Stratocaster's pickup, where a steel's is
wound to 15-19 kohm and, on a pot pedal, resonates near 1.5-2 kHz (the whole
chain had stood 14 dB higher at 3 kHz than at 1 kHz, so the attack was
over-bright and the sustain, by contrast, dark); partials above 1.5 kHz dying
at an electric guitar's rate; the Fender stack set as a guitarist sets it,
where steel players turn the middle up and the bass down (the held A3's 3rd
and 4th harmonics had sat 14 dB under its fundamental through the amp, 1-3 dB
in the string); swells too quick, a 14 dB pull-back step before one, and
thirds a little short of Newman's chart. For the slide: a resonator darker
than the flat-top, where the cone is the bright one; notes dying too soon on
every body, since a bottleneck is a hard stop, not a soft one; a fretted
guitar's vibrato depth where a slide player's is two or three times it; no
sympathetic ringing of the open strings, much of an open tuning's sound;
slides into notes never lazier than 0.15 s; and an electric hearing the string
behind the slide, which its pickup can't. All of it is in, as described
above; the amp is now also levelled on its reference chords' sustain, which
halved the makers' spread on picked parts once the pickups differed. It
judged the glides, bends, vibrato rates, pickup position, scrape, swell slope,
spring and levels in range, and the wobble in the pitch tracks of bends and
glides to be the two planes beating under the pitch tracker, not the model.

## Limits

- Nobody has listened. The models are right by the measures above, but the
  measures are not the ear.
- The accordion and the concertina are not here: their builders ran out of
  session before committing them. The
  banjo, mandolin, electric, bowed and harmonica builders' own reviews never
  ran; their instruments pass their tests and the other set's contract test
  (but for the loudness of its generic parts), and want a review by
  measurement next.
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
- The kit is at the frame drum's level, as the brief asked: a rock or pop
  arrangement will want it several dB louder (the mix's balance).
- The kit is heard from the drummer's seat (hi-hat left); an audience's view
  is the mirror image.
- A felt-beater kick's first milliseconds stay dark (a centroid near 400 Hz);
  a plastic beater (some makers') clicks brighter.
- The mix has no strips of its own for most of these yet (see For the mix).
- Two modal engines now exist: this set's `struck.py` (modes driven by
  strikes, each with its own amplitudes, multirate) and the other set's
  `modal.py` (resonators driven by a signal). They could be one.
