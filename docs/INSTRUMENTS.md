# The new instruments (2026-09-26)

The band was a small acoustic folk band: plucked, bowed and blown strings, a
frame drum and a reed drone ([BAND.md](BAND.md)). The artist, having heard
it: "We should still strive for more variation in arrangement and genre
too." So the band can now also reach for keyboards (a piano, electric
pianos, a tonewheel organ, a harmonium), mallets (vibraphone, marimba,
glockenspiel, celesta, music box), an analog synthesizer, a game console's
sound chip and a drum machine. Everything is still synthesized in code from
the seeds, with numpy, scipy and numba, so the program stays the whole
artifact: no samples, no downloads.

As with the band, nobody but the artist can listen, so every model was
judged by measurement against what the real instrument does, and a Fable
advisor reviewed the plan before any of it was built and the instruments by
measurement after. The renders in `renders/production/instruments/` are for
the ears: each instrument alone, a short phrase in D written for it.

## How they plug in

Each family is a module in `songbird/synth/` with a `SPEC` and a `render()`:

```
SPEC[name] = dict(family, role, register=(lo, hi) MIDI or None, place=(position, width), level, poly,
                  articulations={art: meaning}, about, [loudness, brighter, dynamic])
render(name, notes, sr, length, rng, make, settings) -> dry mono or stereo, before placement and level
```

`notes` are the score's notes for the part (start, dur, pitch, vel, art);
`rng` is the performance's randomness and `make` the maker's (so a machine
keeps its instruments across renditions); `settings` is the band dict
(brightness, wear, ornament, body, maker, tonic). A stem is
`instruments.place(render(...), *place) * level * gain`. `role` says what
kind of part the instrument was levelled for; `register` is the sounding
compass; for unpitched instruments `art` names the piece.

The twenty-two, from their SPECs (articulations combine with "+" where an
instrument says so: `ped+soft`, `gospel fast`, `25+arp-min`):

| Name | Family | Role | Register | Poly | Articulations |
|---|---|---|---|---|---|
| piano | keys | comping | 21-108 | yes | `""`, `ped`, `soft`, `ped+soft` |
| epiano | keys | comping | 28-100 | yes | `""`, `ped` |
| epiano-reed | keys | comping | 33-96 | yes | `""`, `ped` |
| organ | keys | comping | 36-96 | yes | `""`, `ballad`, `jazz`, `gospel`, `full`, `soft`, `chime`, any nine drawbar digits (`888000000`), `default`, `fast`, `slow` |
| harmonium | keys | comping | 41-89 | yes | `""`, `swell` |
| vibraphone | mallets | comping | 53-89 | yes | `""`, `dead`, `roll`, `motor-off`, `motor-slow`, `motor-fast` |
| marimba | mallets | comping | 45-96 | yes | `""`, `dead`, `roll` |
| glockenspiel | mallets | colour | 79-108 | yes | `""`, `choke`, `roll` |
| celesta | mallets | colour | 60-108 | yes | `""`, `ped` |
| music-box | mallets | colour | 72-108 | yes | `""` |
| synth-pad | synth | comping | 36-91 | yes | `""`, `swell`, `stab` |
| synth-bass | synth | bass | 28-60 | no | `""`, `accent`, `short`, `glide` |
| synth-solo | synth | lead (-22 LUFS) | 48-96 | no | `""`, `accent`, `glide`, `bend`, `short` |
| synth-arp | synth | comping | 48-96 | yes | `""`, `accent`, `short` |
| sub-bass | synth | bass (-27 LUFS) | 24-50 | no | `""`, `short`, `glide`, `boom` |
| chip | chip | lead | 45-96 | no | `""`, `12`, `25`, `50`, `75`, `arp-maj`, `arp-min`, `arp-sus`, `arp-pow`, `arp-oct`, `pluck`, `glide` |
| chip-bass | chip | bass | 28-67 | no | `""`, `glide`, `arp-oct` |
| chip-drums | chip | percussion | unpitched | yes | `kick`, `snare`, `hat`, `hat-open`, `clap`, `crash`, `rim`, `cowbell`, `tom-hi`, `tom-mid`, `tom-lo` |
| drums-808 | drum machine | percussion | unpitched | yes | `kick`, `snare`, `clap`, `hat`, `hat-open`, `hat-pedal`, `tom-hi`, `tom-mid`, `tom-lo`, `rim`, `cowbell`, `crash`, `ride`, `clave`, `conga-hi`, `conga-mid`, `conga-lo`, `maracas` |
| drums-909 | drum machine | percussion | unpitched | yes | `kick`, `snare`, `clap`, `hat`, `hat-open`, `hat-pedal`, `tom-hi`, `tom-mid`, `tom-lo`, `rim`, `cowbell`, `crash`, `ride` |

An unknown articulation plays as the instrument's plain note (on the drum
machines, an unknown piece as the closed hat); none raises.

Every one's typical part measures within 0.1 dB of its target at its SPEC
level. A three-minute part costs, in CPU seconds on an idle machine: piano
2.9 (13 for the worst case, pedalled bass octaves every half bar), epiano
1.9, epiano-reed 1.5, organ 1.2, harmonium 2.1, vibraphone 1.8, marimba 1.3,
glockenspiel, celesta and music box 0.7 each, synth-pad 5.0, synth-bass 1.3,
synth-solo 1.6, synth-arp 2.8, sub-bass 0.2, chip 0.8, chip-bass 0.8,
chip-drums 1.0, drums-808 1.3, drums-909 1.0.

Levels were set the same way for all of them (`tools/instrument_levels.py`):
a typical part for the instrument's role, in D at velocity 0.6, rendered,
placed and at its SPEC level, measured in LUFS while it plays against the
band in H with the seed's params: comping sits where the guitar's strum sits
through the first refrain (-23.7 LUFS), a lead where the whistle states the
tune in the intro (-20.7), a bass where the upright walks (-24.1),
percussion where the frame drum plays its full pattern in the last refrain
(-28.4), and colour (a bell-like line over the band) 3 dB under comping
(-26.5). A SPEC may name its own target where the role's would mislead:
K-weighting reads a 40-55 Hz sine 4-6 LU quieter than its energy, so a sub
bass sits at -27.

`tests/test_instrument_specs.py` holds every instrument to one standard:
the contract's fields; a typical part that renders finite, replays exactly,
has nothing before its first note and no DC; its loudness within 1 dB of
its target; louder (and as much brighter as its SPEC says) when played
harder; in tune within 2 cents through the middle of its compass; and a
three-minute part well under 20 s. Each module has its own tests measuring
it against the real instrument.

Three pieces are shared:

- **Modes** (`modal.py`). A struck or plucked thing as a bank of damped
  resonances, each a complex one-pole resonator driven sample by sample by
  the contact's force (a hammer, a mallet, a pin), so every mode builds up
  from rest as it really would and an onset never clicks; a damper glides
  each mode to its damped decay; a mode is dropped once it has died. 200
  notes of 99 modes render in 0.18 s.
- **Oscillators** (`osc.py`). Sawtooth, pulse, triangle and stepped waves
  from frequency tracks, their jumps rounded by a four-point polyBLEP (a
  step band-limited by a cubic B-spline) and a triangle's corners by a
  polyBLAMP. Run at twice the rate and brought down by a 95-tap half-band,
  a sawtooth's folded partials sit 91 dB under its fundamental at 440 Hz
  and 80 dB at 2 kHz (45 dB at the plain rate with the usual two-point
  polyBLEP).
- **Touch** (`touch.py`). Velocity becomes amplitude as a power law set by
  the instrument's dynamic span (pp at 0.2 to ff at 1), the same way for
  every model; timbre is each model's own business.

## Piano

`piano.py`: "piano", from a small upright to a small grand (the `body`
setting).

**The hammer.** A felt hammer is thrown at two or three strings; the felt
is a nonlinear spring, F = K δ^p, stiffer the harder it is squeezed. The
hammer is simulated only while it touches the strings: a mass on that
spring against the strings' impedance, with the waves it launches coming
back from the agraffe and the bridge (they are what throws the hammer off
in the treble). The masses are Chaigne and Askenfelt's (1994). Their felt
exponents (2.3 to 3), in this model, leave the felt stiff even when barely
squeezed, so the strings' impedance sets the contact and a harder blow
hardly brightens it; measured hammers run from about 2.2 to 3.5 (Hall and
Askenfelt), and exponents of 3.2 in the bass and 3.5 from the tenor up, the
felt as stiff as a fifth of theirs at 0.3 mm, behave as a piano does. A
C4's contact lasts 3.0 ms at pp and 2.0 at ff (measured about 4 and 2), a
C2's 4.8 to 3.1, a C7's 0.96 to 0.58 (measured, under a millisecond); peak
forces run from about 7 N at pp to 80 N at ff at C4. The pulse's peak
sharpens with the blow, so a C4's energy above 3 kHz goes from 80 dB under
the note at pp to 35 at mf and 26 at ff. The felt's push and the string's
give are solved together each step, so no voicing, however hard, makes the
simulation unstable. The force drives the partials, weighted by where it
struck: about an eighth of the way along, which all but silences the eighth
partial.

Each note is levelled by its velocity (a power law spanning about 22 dB from
pp to ff), but no voicing makes a string ring louder than its blow can drive
it: while the hammer pushes, each partial follows the force almost
statically, and for partials far above what the blow reaches (soft blows in
the top octave and a half, the felt piano's treble) that swing would dwarf
the ring once scaled up, a click. A note's swing may be at most six times
its ring's RMS (the tenor's are three to six), so such a note stays as weak
as its hammer leaves it: a soft C7 some 9 dB under a soft C4, a felt C8 a
thud.

**The strings.** Stiff strings stretch their partials, f_n = n f1
sqrt((1 + B n²) / (1 + B)), B about 0.0002 in the tenor, 0.001 at C5, 0.008
at C7 and 0.02 at C8, higher in a small piano's short bass (`body` 0.8
raises it two and a half times there). Each note's partials measure within
1 cent of that. The tuner stretches the octaves to match, from the piano's
own B: equal temperament from C3 to C6, each octave above tuned beatless to
the stretched second partial of the one below, each octave below so its
fourth partial meets the second of the one above. Railsback's curve falls
out of it: A0 7 cents flat, C2 2, C7 8 sharp, A7 24. Every key sounds within
0.7 cents of its stretched target.

**Unisons, prompt sound and aftersound.** A note is one string at the very
bottom, two in the bass, three from F#2 up, a fraction of a cent apart (0.35
cents rms from the maker, and up to five more with wear). For each partial
the strings are coupled through the bridge they share (Weinreich 1977) and
solved for their eigenmodes: moving together they push the bridge and lose
their energy fast (the prompt sound), moving against each other they barely
move it and ring on (the aftersound). The hammer excites mostly the first;
the unisons' mistuning and the felt's unevenness feed the second. Each
string's plane along the soundboard adds a quieter, slower mode (18 dB
down), which a single bass string needs for its own double decay. A
partial's prompt sound decays by its frequency, 7 s at 262 Hz and falling as
f^-0.9 above and f^-0.55 below (C2 15 s, C5 3.8, C6 2.0, C7 1.1, C8 0.6:
measured decay rates of about 16, 30, 55 and 100 dB/s above C4), the
aftersound 2.6 times as long at C4 falling to 1.2 above 2 kHz, where a
unison's fraction of a cent is more hertz than the bridge couples and the
strings ring each on its own. Measured on the render: a C4's fundamental
falls 8.3 dB/s for the first second and about 4.6 later (real pianos: 8-10,
then about 3); C2 3.9, C6 30 dB/s at first; the partials above 3 kHz fall 40
dB within a second; upper partials beat as their strings drift apart.

**Dampers and the pedal.** When a key rises its damper lands: 30 dB off a C4
in about 0.15 s, off a C2 in 0.4 s (the heavy strings take longer); the keys
from F#6 up have no dampers and ring on. A key struck again stops what its
last blow left ringing. The sustain pedal (art `ped`) holds the dampers for
the note's whole written length and lets the open strings whose partials lie
within a few cents of the note's answer it: each builds up over about a
second, as a string driven by a decaying partial does, to 21 dB under the
partial it shares, which lifts a held D4's sustain by about 1 dB. Una corda
(art `soft`) shifts the hammer so it misses one string and meets the others
with unworn felt: 2 dB softer at the attack, with more of the aftersound.

**The soundboard and the room's image.** Every string drives a soundboard
built like the band's bodies (body.py): broad low modes from 58 to 420 Hz,
then a dense even scatter to 9 kHz, radiating poorly below 55 Hz, its two
microphones brought to the same level in each third of an octave (so the
scatter gives width without pulling a register to one side). The key and
hammer knock on the frame as they land, a short thud relatively louder in
the treble. The image is a player's: the bass to the left, the treble to the
right.

**Settings.** brightness is the hammers' voicing, from soft needled felt to
hard lacquered felt (the felt's stiffness over a 250-fold range); below 0.3
the hammers are wrapped in a strip of felt, as upright players do for quiet
practice, which passes only the slow push: a dark, close "felt piano" whose
energy above 3 kHz sits 62 dB under the note at mf (a hard-voiced piano's,
24). wear widens the unisons toward a honky-tonk, pulls single keys off
pitch, hardens the hammers (compacted felt) and lets the dampers leak.
make gives each machine its own piano: the unisons, each key's pitch, the
hammers' unevenness and voicing, the soundboard's modes.

**Cost.** A three-minute comping part (1152 notes) costs 3.5 s of CPU; the
worst case, pedalled bass octaves and six-note chords every half bar for
three minutes, 13 s. Partials 60 dB under a note's strongest are never
rendered, nor past the 90th (a bass note's is above 3.5 kHz).

## Electric pianos

`epiano.py`: "epiano" (a tine piano) and "epiano-reed" (a reed piano).

**The tine piano.** Each key is a small tuning fork on its side: a thin
steel tine clamped to a heavier tonebar tuned to the same note, struck near
its clamp by a neoprene-tipped hammer whose push lasts about 3.6 ms in the
bass and half a millisecond at the top, halving from a soft blow to a hard
one as the rubber stiffens. The tine rings in a cantilever's modes, 1 : 6.27
: 17.55, the second pulled toward 5.2 in the bass by its tuning spring; the
upper modes are the bell of a hard blow, at middle C 21 dB under the
fundamental at velocity 0.3 and 10 dB under at 0.9, gone in 0.12 to 0.35 s.
The fundamental is the fork's slow mode, ringing 10 s × (262/f0)^0.8
(measured 17.5 s at C3, 10.0 at C4, 5.75 at C5), after a first drop of about
3 dB from the fork's quick mode. The tip swings past an electromagnetic
pickup whose flux across the pole is a bell curve, (1 + u²)^-3/2, voiced
0.35 off the axis, and the voltage is its rate of change: a small swing
gives a nearly pure tone, a big one sweeps over the crest and barks. Each
note's tine goes through its own pickup, at twice the rate, before the
notes are summed: at middle C the second harmonic is 22 dB under the
fundamental at velocity 0.3, 12 under at 0.5 and 4 over at 0.9, falling 13
dB a second later; the centroid rises almost an octave (330 to 640 Hz at E4).
A soft-clipping preamp, and a stereo tremolo at the machine's 4 to 6 Hz as
deep as ornament asks (±43% at 0.5, none at 0). Felt dampers stop a note in
0.1 to 0.2 s.

**The reed piano.** Felt hammers strike steel reeds tuned by solder on their
tips (the second mode at four to five times the fundamental, dying in a
tenth or two); each reed is one plate of a capacitor, and the current into
the preamp follows a capacitance that goes as 1/(d - x): strong odd and even
harmonics together, and a nasal bark when played hard (at middle C the
second harmonic 17 dB under the fundamental at velocity 0.3 and 4 under at
0.9). It rings 4 s at C3 and 1 s at C6, mono, with an amplitude tremolo at
5.5 to 6.5 Hz. Both pianos are within 0.4 cent, every onset at most 2.8
times the ring's RMS, and a three-minute part costs about 2 s.

## Organs

`organ.py`: "organ" (a tonewheel organ through a rotary speaker) and
"harmonium".

**The generator.** 91 steel wheels turning continuously, each a near-sine at
one equal-tempered pitch; a key switches them in wherever they happen to be.
Nine drawbars (16', 5⅓', 8', 4', 2⅔', 2', 1⅗', 1⅓', 1'), each played by the
nearest tempered wheel: the quints 1.96 cents flat of pure, the 1⅗' 13.7
sharp, a step 3.0 dB. The 16' folds up in the lowest octave, anything above
F#8 folds down. As a key goes down its nine contacts meet their busbars over
1.5 to 4.5 ms, each switching a sine on abruptly and chattering: a click
within 20 dB of its peak for 7 to 10 ms, most of it above 1 kHz. The
percussion is one envelope fired only by a key pressed with every key up
(single trigger), adding the 4' or 2⅔' with a time constant of 0.2 or 1 s,
taking the 1' and dropping the drawbars 3 dB.

**Scanner, swell, tubes, rotor.** The scanner sweeps a delay line at 6.87
Hz: ±8, ±16 or ±24 cents (V1-V3), the chorus settings adding the dry signal
back. Velocity is the swell pedal (24 dB from 0.2 to 1, the treble falling
further as it closes), and each chord's velocity moves the whole organ. The
tubes are nearly clean at a typical swell (distortion 36 dB under the tone)
and growl for a full organ wide open (14 to 18 dB under). The rotary speaker
splits at 800 Hz between a horn and a drum spinning 0.8 and 0.7 turns a
second slow, 6.7 and 5.7 fast: at speed the horn's pitch swings ±0.76% and
its level 9 dB, the drum's ±0.24% and 4 dB, heard by two microphones with a
cabinet reflection; the horn spins up in about a second, the drum in about
four, and both coast down about 2.5 times more slowly. Everything is within
0.34 cent through the whole chain; a three-minute part costs 1.4 s.

**The harmonium.** A thin wrapper on the band's reeds (reed.py) with the
reed box as its body: an 8' rank, a celeste rank 3 to 8 cents sharp (the
fundamental shimmers about 9 dB), a 4' brought in with brightness; reeds
speak in 53 ms at F2 to 18 at F6, and a pumping hand swells the pressure a
few percent every couple of seconds.

## Mallets

`mallets.py`: "vibraphone", "marimba", "glockenspiel", "celesta",
"music-box", one modal-bar model with a parameter set for each.

**Bars and mallets.** A free bar rings at 1 : 2.756 : 5.404 : 8.933 (a
glockenspiel's steel bars, a celesta's plates), a little lower in a short
thick bar (a glockenspiel's C8 measures 1 : 2.67 : 4.97); a marimba's and a
vibraphone's bars are undercut to 1 : 4 : 10 (a marimba's top bars can't
hold the third, which falls toward 9.2). The second mode is silent at the
bar's centre, so each stroke lands somewhere 5 to 15% off it. The mallet's
push is a smooth pulse, flat to about 1/2τ: yarn on a marimba touches 5 ms
at A2 to 1.1 ms at C7, cord on a vibraphone 2 to 1 ms, felt on a celesta 2 to
0.9, brass on a glockenspiel 0.5 to 0.25; a harder stroke is shorter and
sharper, so from pp to ff a marimba's fourth partial gains 8 to 9 dB on its
fundamental and its tenth 13 to 20. The force drives the modes through
modal.ring; what radiates is the bar's acceleration, as a dipole below a
corner set by its width. A chord's mallets land up to 3 ms apart.

**Resonators.** A tube (a box, under a celesta's plates) is a second mode
coupled to the bar's first: it shortens the bar's ring (a marimba's A2 from
3.2 s bare to 2.0) and radiates what the bar cannot, lifting the fundamental
26 dB at A2 and 11 at C7, blooming 0.2 s after the stroke at A2 and 40 ms at
C5 while the upper partials sound at once.

**The five.** marimba (A2-C7): the fundamental rings 2.0 s at A2 to 0.3 at
C7; `dead` holds the mallet on the bar, `roll` spells out a two-mallet roll
(8.7 strokes a second in the bass to 15.6 at the top). vibraphone (F3-F6):
rings 13 s at F3 to 3.5 at F6; a note's length is how long before the damper
lands (T60 0.2 to 0.1 s after); the motor is one shaft of discs across every
tube, its phase continuous through the part, swinging the resonated
fundamental 11 dB and the note 9 (±2 to 3 cents of pitch); its speed is 2.5 +
4 × ornament Hz (off at 0), or `motor-slow` (3.5 Hz), `motor-fast` (6.5 Hz),
`motor-off` from a note on. glockenspiel (G5-C8 sounding): no damper, 5 s at
G5 to 3 at C8 unless `choke`. celesta (C4-C8): felt hammers 13% off centre,
where the third mode is nearly silent, over wooden boxes: a strong, soft
fundamental ringing 2.0 s at C4 to 1.0 at C8, piano-like dampers, `ped`.
music-box (C5-C8): a comb of cantilever teeth, the bass teeth with lead
lumps that bring the second mode down to about 4.7; a pin bends a tooth and
lets go (no contact filter, a tick), teeth ring 4 s at C5 to 2 at C8, a tooth
plucked again while sounding is stopped with a short buzz by its damper,
and the small box radiates little below 300 Hz; velocity moves it 4 dB at
most.

make gives each machine its bars' tuning (within 1 cent at wear 0), its
resonators, the motor's speed; wear pulls bars off pitch, detunes the
resonators and makes loose bars buzz faintly.

## Analog synthesizer

`analog.py`: "synth-pad", "synth-bass", "synth-solo", "synth-arp",
"sub-bass".

**Oscillators.** Sawtooths and pulses (osc.py's four-point polyBLEP, drawn
inside each voice's loop at twice the rate) whose tuning wanders with a
slow drift of 0.1 to 0.3 Hz: within 1.2 cents at wear 0, ±3 to 4 cents at the
default wear, ±5 to 9 at wear 1. A detuned pair always sits under an
oscillator on the note, so the fundamental never loses its pitch to a beat's
null. The pad's pulse is width-modulated symmetrically, so its width moves
and its pitch doesn't.

**The ladder.** Four one-pole stages with zero-delay feedback and a
saturating input pair, the loop's nonlinear equation solved each sample:
21 to 23 dB an octave above the cutoff, a resonant peak of +24.6 dB at 0.9,
the Moog's bass loss half given back, and at full resonance, key-tracked,
it sings within 0.05 cents of the note from C3 to C7. At C7 wide open the
solo's and arp's folded content sits at -74 and -78 dB.

**Envelopes, glide, chorus.** RC envelope segments; releases of 0.8 s (pad),
83 ms (bass), 183 (solo), 162 (arp). The mono voices glide between legato
notes (90% of the interval in 39 ms on the bass, 62 on the solo) with no new
attack; a detached note starts again on its own pitch. The solo's vibrato
comes in after 0.3 s, ±30 cents at about 5.5 Hz at ornament 1. The pad goes
through a bucket-brigade chorus: two lines swept by LFOs near 0.5 and 0.85
Hz in antiphase, 3.2 to 4.7 ms, ±3.6 cents. The sub bass is a sine with its
2nd and 3rd harmonics 15 and 30 dB down, its phase reset at every attack so
every attack is the same waveform and every kick-and-sub sums alike.
Velocity 0.3 to 0.9 is 8 to 10 dB louder and 0.3 to 0.5 octave brighter. A
three-minute part costs 0.3 s (sub) to 5 s (pad).

## Game console

`chip.py`: "chip", "chip-bass", "chip-drums", after the NES's sound chip.

Its two pulse channels step an 8-step duty sequence (12.5, 25, 50, 75%)
with a 4-bit volume; its triangle steps a 32-step table of 4-bit values with
no volume at all; its noise channel shifts a 15-bit register at one of
sixteen rates from 440 Hz to 447 kHz (a 32767-step sequence, or a 93-step,
pitched buzz). Two nonlinear resistor networks mix them, and the console's
high-passes at 90 and 440 Hz and low-pass at 14 kHz filter the sum. Each
channel here is the list of moments its level changes, drawn at twice the
rate with every step band-limited (even the register's at 447 kHz). A game's
sound driver moves envelopes, arpeggios, vibrato and slides once a video
frame (60.1 Hz), counted from each note's start. Measured: duty nulls under
-160 dB, register periods 32767 and 93, fifteen volume steps on the mixer's
curve, pitch exact (the chip's own timer rounding, which puts a C7 14.5
cents sharp, is left out), a C7 pulse folding under -80 dB, the triangle's
steps putting its 31st and 33rd harmonics 30 dB under the fundamental (the
chip's buzz), and the console's filters taking 14.5 dB off a 110 Hz
triangle's fundamental: the thin NES bass. Each channel plays one sound at a
time: a later noise hit cuts the one sounding. A three-minute part costs
under 1.1 s.

## Drum machine

`drummachine.py`: "drums-808" and "drums-909", built the way the two
classic machines' circuits make their sounds.

**The 808.** Most of its drums are one circuit: a bridged-T resonator struck
by a millisecond pulse, ringing on as a decaying sine. The bass drum rings
near 50 Hz with a decay from a short thud to over a second; for its first 4
to 6 ms it rings 2.6 times higher (punch, not pitch), and while its swing is
big it starts a few percent sharp and sighs down (58 to 48 Hz over 300 ms,
as measured on the real circuit). The snare is two rings (173 and 336 Hz)
and noise high-passed at 2.75 kHz; the toms and congas bend down as they
die; the rim shot is two short rings through a distorting transistor. Its
hats, cymbal and cowbell come from six square waves always running (205,
304, 370, 523, and 540 and 800 Hz trimmed), summed and band-passed at 3.44
and 7.1 kHz, a clang of beating overtones, through "swing" VCAs that get
grittier as they decay; a closed hat chokes a ringing open one. The clap is
band-passed noise struck three times about 11 ms apart over a short tail.

**The 909.** Its drums are oscillators: the bass drum a rounded triangle
swept down about two octaves in its first 30 to 60 ms, with a click and a
little saturation; the snare two oscillators (190 and 345 Hz) bent sharp for
20 ms and noise; the toms the same with a deeper sweep. Its hats, crash and
ride are 6-bit recordings of real cymbals; here each recording is made by
striking a modal model of a cymbal (a few hundred inharmonic modes) and
storing it the same way.

**Playing.** Pitch and duration are ignored; art names the piece. Velocity
is the trigger's size, 18 dB from 0.2 to 1; above 0.8 the accent comes in (5
dB more by 0.9), driving the circuits harder: a deeper sigh and more click
on the kick, a further bend on the toms, more snap. make gives each machine
its parts' tolerances and knobs; wear makes pitch wander and adds hiss;
brightness turns the tone knobs; body retunes the drums. The kit comes back
in stereo as a machine's separate outputs would be panned: kick, snare, clap
and rim in the middle, the hats a little right, the toms high right to low
left.

## The palette

`palette.py` gathers all 22 by name: `palette.SPEC[name]`,
`palette.render(name, ...)` and `palette.stem(name, ..., gain)` (the render
placed and at its SPEC level, times the band's balance for it).

## For the part-writer

The idioms each instrument is used in, its ranges and articulations, and
what to avoid.

**Piano** (21-108; comping). Left hand: a root, a root and fifth, or an
octave from D2 to D3 (38-50), never a close chord below C3, which muddies.
Right hand: close triads and sevenths from about C4 to A5 (60-81), the tune
on top an octave above the singer when it doubles her. Pedal (`ped`) through
each harmony, writing each note's duration to the next change of chord
(the pedal lifts there); leave it off for a dry, detached comp. Patterns: a
chord on the beat and the bass alone on it (pop ballad), the chord after the
beat (a gentle lift), broken chords in eighths (a lullaby or a folk
accompaniment), a stride's bass on one and three and chords on two and four.
Velocity carries a great deal: 0.3-0.45 for an intimate verse (dark), 0.6-0.7
for a refrain, 0.8 and more only for the climax (the hammers go bright and
clangy). `soft` for a hushed verse or a coda. Avoid thick chords in the
singer's register while she sings, and the keys above A7 (thin, very short,
tuned 30 cents sharp).

**Tine piano** (`epiano`, 28-100; comping). Comp between F3 and C5, where
the bark lives; the left hand on roots or fifths C2-C3, or leave the root to
the bass. Rootless voicings (3-7-9, 7-3-13) from about E3 up; shells (root
and 7th, root and 3rd) for sparse ballads; below A2 thirds go muddy.
Velocity is timbre: 0.3-0.5 glassy, 0.6-0.75 a moderate bark, 0.85-1 the
growl, for accents and soul stabs. `ped` with notes lengthened to the pedal
change. The tremolo follows ornament. Avoid dense low clusters played hard.

**Reed piano** (`epiano-reed`, 33-96; comping). Comp around F3-C5. It
decays in 1-4 s, so rhythmic comping and soul or pop ballads rather than
pads; it barks nasally from velocity 0.8.

**Organ** (36-96; comping). Pads: three- or four-note voicings in C3-C5,
held legato with slight overlaps (the organ doesn't decay: every gap is
heard), the top voice moving smoothly. Stabs: short chords for gospel and
soul; a reggae bubble is staccato off-beat eighths on `jazz` or `888000000`.
Registrations hold from the note that names them: `""` the house sound for
general comping, `ballad` or `soft` under a voice, `chime` for a folk bell
on each phrase's first note (it needs detached phrase starts), `gospel` for
choruses, `full` for climaxes, `jazz` for percussive single-note lines (the
percussion fires only when every key was up), any nine digits for
drawbars, `default` back to the house sound. `fast` a bar before a chorus or
build (the drum takes about 4 s), `slow` to settle; combine them
(`gospel fast`); don't flip the rotor every bar. Velocity is the swell pedal
and moves the whole organ: keep it steady within a phrase. The house sound
already has a 16': don't double the bass at C2. Notes below C2 play an
octave up.

**Harmonium** (41-89; comping). Legato chords and tonic-and-fifth drones
(`swell` for slow bellows swells); not for fast rhythmic comping, the reeds
take 20-50 ms to speak.

**Vibraphone** (53-89; comping). Let-ring chords (write the duration to the
next change: the note's length is the pedal), a tune an octave above the
singer between her lines, four-mallet voicings (close triads and sevenths
from A3 to A5). The motor from ornament, or `motor-slow` for ballads,
`motor-fast` for a shimmering climax, `motor-off` for a dry, jazzy line;
`dead` for staccato accents. Avoid many let-ring notes a step apart (they
blur for seconds).

**Marimba** (45-96; comping). Broken chords in eighths, ostinatos, and
`roll` for any long note (a marimba can't sustain otherwise); four-mallet
chords spread an octave or more in the low register, close above C5. `dead`
for a dry, muted figure. The low bars bloom 0.2 s after the stroke: write
bass notes on the beat, not ahead of it.

**Glockenspiel** (79-108 sounding; colour). Double the tune two octaves up
in the refrains, or ring single notes on strong beats; it doesn't damp, so
keep lines sparse and diatonic (seconds ring into each other); `choke` stops
a note. Softer than it reads (-26.5 LUFS target): don't raise it into a lead.

**Celesta** (60-108; colour). A tune an octave up, soft broken chords, a
counter-line in the top octave; `ped` for let-ring figures. Sweet and short
(1-2 s): good for lullabies and codas.

**Music box** (72-108; colour). The tune with an arpeggio underneath, as a
cylinder plays it, in quarter or eighth notes; velocity barely matters
(a machine), so shape phrases by density. A tooth struck again while
ringing buzzes briefly: avoid fast repeated notes.

**Synth pad** (36-91; comping). Three- or four-note voicings from C3 to C5,
open below C3, whole-bar or longer chords, voice-led with common tones held
(a restruck key re-attacks its filter, a soft "wah"); `swell` to enter,
`stab` for off-beat hits. Keep it out of the singer's register.

**Synth bass** (28-60; bass). Roots, fifths and octaves around E1-C3;
pumping eighths and octave jumps. Leave small gaps unless you want a glide
(touching notes glide 45 ms with no new attack); `glide` slides into a
detached note, `accent` on downbeats and syncopations, `short` for
staccato. Velocity is brightness as much as level.

**Synth solo** (48-96; lead, -22 LUFS). Lines around C4-C6; overlap notes to
slur them (a 70 ms glide), long notes get vibrato after 0.3 s, `bend` into
long notes; avoid long legato runs of fast notes (every one glides).

**Synth arp** (48-96; comping). One-note sixteenth arpeggios through chord
tones, C4-C6, each about 90% of its step; `accent` on the first of each
group, `short` for tighter blips. Levelled on block chords, so a one-note
arpeggio sits a few dB lower: raise its gain if it is the main bed.

**Sub bass** (24-50; bass, -27 LUFS). Roots on downbeats, long notes, below
D3; its identical attacks sit well under a kick on the same beat. `boom`
for 808-style notes, `glide` for slides. No fast runs; pair it with
something higher for small speakers.

**Chip** (45-96; lead). The tune, one note at a time (overlaps cut each
other); chords only as `arp-maj`, `arp-min`, `arp-sus`, `arp-pow`,
`arp-oct` on held notes of a quarter or longer (the note is the chord's
root). Duty by phrase or section: `25` the lead, `12` a thin echo or
countermelody, `50` a hollow, softer line (`75` sounds as `25`); `pluck` for
harp-like figures, `glide` for slides; combine with "+" (`25+arp-min`).
Fast runs and trills are idiomatic, but nothing shorter than a frame (17 ms).

**Chip bass** (28-67; bass, no dynamics). Bouncing root-octave eighths,
written higher than an acoustic bass (about A1-A3: below A1 the console's
filter leaves mostly buzz). Staccato is note length (the triangle stops
dead); `arp-oct` thickens a held note.

**Chip drums** (percussion). kick, snare, hat, hat-open, clap, crash, rim,
cowbell, tom-hi, tom-mid, tom-lo. One noise sound at a time: a hat on the
snare's beat is dropped, a hat after a crash cuts it (give the crash
space); kick and toms share the triangle. Kick on 1 and 3, snare on 2 and 4,
eighth-note hats, toms high to low for fills.

**Drum machines** (`drums-808`, `drums-909`; percussion). Pieces: kick,
snare, clap, hat, hat-open, hat-pedal, tom-hi, tom-mid, tom-lo, rim,
cowbell, crash, ride (the 808 also clave, conga-hi, conga-mid, conga-lo,
maracas; the 909 plays the 808's where it has none). At a folk song's tempi:
a backbeat (kick on 1 and 3, snare or clap on 2 and 4, eighth-note hats with
an open hat on the and of 4, closed by the next hat); four on the floor
(kick every beat, clap on 2 and 4, open hats on the off-beats) for a dance
refrain; half time (kick on 1, snare on 3, soft hats) under a ballad; the
808's long kick as the bass line with syncopated kicks and sixteenth hats.
Velocity shapes the groove: hats alternating about 0.5 and 0.7, ghost snares
at 0.3, accents (0.85 and up) on downbeats and pushes only, not every beat.
An open hat rings until a closed or pedal hat chokes it: always close it.
Duration and pitch are ignored.

## What the reviews changed

A Fable advisor read the plan before anything was built, measuring against
the house code as it went, and changed a good deal of it. The piano's
treble would have rung far too long (C7 2.3 s where real ones fall 50 dB a
second); its decays now follow measured rates, partial by partial, by
frequency. A single bass string can't have a unison's double decay, so each
string's second plane was added. The pedal's halo was to be a bank of
harmonic string loops, which would have beaten against the piano's
stretched partials; it is modes at the open strings' own partials instead.
It set the levels of what K-weighting misreads (a sub bass 3 dB under the
upright's reading, bells 3 dB under comping, the mono synth's line between
comping and a lead), asked for the tonewheel organ's scanner vibrato and
chorus (the sound most heard from one), and for one SPEC-driven test and one
touch curve so that five builders would meet one standard.

Measuring the piano against real ones then changed its hammer. Chaigne and
Askenfelt's felt, in this model, left the contact to the strings'
impedance: 2.5 ms at pp and 1.9 at ff at C4, and a hard blow hardly
brighter than a soft one; a softer felt with a steeper exponent gives the
measured contact times and a hard blow 45 dB more above 3 kHz. The
per-partial decay first let the unisons decouple into slow single strings
in the upper partials (a C7 fell 26 dB a second, not 56); the aftersound now
shortens toward the prompt sound above 2 kHz. Levelling each note by its
velocity let soft top notes, which their blows barely reach, click at 30 to
5000 times their ring; a note's swing under the hammer is now held to six
times its ring. A hard voicing made the explicit contact unstable; it is
solved implicitly. The soundboard's two microphones differed by up to 8 dB
in some registers, pulling notes across the player's image; they are
balanced third-octave by third-octave.

## Limits

- Nobody has listened. The models are right by the measures above, but the
  measures are not the ear.
- The piano has no longitudinal ("phantom") partials, no damper noise, no
  pedal thump or key release noise, and its halo answers only the partials
  a note shares with an open string (not the whole undamped wash a real
  pedal lets loose on the attack). Its hammer is simulated against an ideal
  string, stiffness left to the modes.
- The organ has no tonewheel leakage or hum and no pedalboard (notes below
  C2 play an octave up), and its velocity is the swell for the whole organ.
  The mixer (mixing.role_of) sends "organ", "harmonium" and "synth-pad" to
  its drone strip (a 6 kHz low-pass, -3 dB at 2.5 kHz), which suits the
  harmonium and the pad but dulls the organ's click and horn; "synth-bass",
  "sub-bass" and "chip-bass" go to the bass strip, "chip-drums" and the drum
  machines to the drum strip, everything else to the plain band strip. A
  name with "lead" in it would go to the voice bus, which is why the mono
  synth is "synth-solo".
- The tine piano's centroid rises 0.96 octave from pp to ff, not quite the
  octave asked for; the reed piano is mono, as the real one's speakers are.
- The pad's detune at the default wear is 3.75 cents, under the 5-12 of a
  classic pad (it starts at 1 cent so wear 0 stays in tune).
- The chip leaves out its timers' pitch rounding and counts frames from each
  note's start (a free 60 Hz clock would add up to 17 ms of jitter); its bass
  is as thin as a front-loading console's (a Famicom's would be fuller).
- The 909's cymbal "recordings" are modal models stored at 6 bits, not
  recordings. The drum machines' docstrings name the machines they model.
- Comping instruments were levelled on block chords at velocity 0.6; a
  one-note arpeggio or a single line on them sits a few dB lower.
