# How the song is mixed and mastered

A rendition should sound like a well-made record: a warm, intimate, modern
acoustic folk record with the voice clear and in front. Every stem has a
channel strip, the voice, the lineage choir and the band each have a bus, the
room is built from the harvest's numbers the way a room sounds, and the
master keeps the true peak under −1 dBTP. Nobody but the artist can listen;
everything here was judged by measurement, against a reference, against
natural singers, and by a read-only Fable review that measured the mix
itself. Listening decides; these are the guard rails.

## The path

`synth.mix()` (songbird/synth/mixing.py) takes the stems by name. A stem's
name gives its role (`mixing.role_of`): voice, choirN, lute (or melody),
guitar, harp, bass, fiddle, whistle, drum, drone, and the strips the wider
palette adds (keys, organ, kit, banjo, strings, steel and so on; see
docs/INSTRUMENTS-B.md, "For the mix"); anything else is treated as a plain
instrument. Only a whole name makes a stem a singer. Stems of any shape are
taken (mono, one column, a different length). The tools are in
songbird/synth/fx.py.

**The voice.** High-passed at 80 Hz, 2 dB less honk around 900 Hz, half a
dB of presence at 3.5 kHz (at 2 dB the top notes are harsh, set beside
natural singers: SoulX-Singer renders of the same score). Its air (7–14 kHz
against 0.5–2 kHz) is measured, and only a voice brighter than natural
singers is brought back, halfway. A de-esser that listens to the balance of
the highs against the voice's body, not to how loud the singer is (see "The
hiss"). A compressor that only leans on the syllables that stand out of
their phrase: its threshold rides 3 dB over the level of the three seconds
around each moment, so a syllable is evened against its neighbours but a
quiet verse stays quiet and a full refrain full (2:1, 15 ms attack). A
transient softener (`VOICE_SOFTEN`) takes the edge off consonant bursts that
jump more than 6 dB over the voice's recent level, which would otherwise
read as clipping. Then a light saturation (`VOICE_DRIVE` 0.05) and a peak
stage for the rarest peaks. The saturation is light because the throat's
crest factor is 13.7 dB: at a drive of 0.2 its loudest syllables ran 4-9 dB
further into the curve, distortion above 2 kHz sat 21 dB under the voice's
own highs with nothing in the band to mask it, and the artist heard it as a
roughness as the voice got loud; at 0.05 it is 33 dB under. Everything the
voice's tools react to is measured on the voice itself, so a quieter or
brighter singer is treated the same.

**The singers rise with the arrangement** (`mixing.lead_lift`). Brought to
`REFERENCE` in every sung section, the lead would come out at the same
loudness in a sparse verse and at the climax, and a 6 dB build in the band
would reach the record as half a dB. So the lead (after its strip) and the
choir group follow the band's energy per section (`songbird.band`, 0..1
arcing across the song): `LEAD_ARC` gives 6 dB per unit of energy above
0.55, held between −2 and +2.5 dB and smoothed over a second. `synth.render`
computes it from the score (`lift_of`); a score without the band's sections
sings level. On H's seed arrangement this makes verse 1 −15.5 LUFS, refrain
2 −12.8 and the last refrain −12.2, the whole still at −14 LUFS.

**The lineage choir** (the bridge and tag, `--choir N`) is one group:
thinner below 260 Hz and in the presence range than the lead, de-essed and
compressed together, 35% wider, 4 dB under the lead, and further back in
the room (a bigger send, reaching the room 20 ms later). A peak stage rounds
off its consonants, which would otherwise stand far over the rest and make
the master limiter work in the bridge. Its root voice sings no lower than E3
(`theory.FLOOR`): below about 160 Hz the learned throat's pulses are heard
one by one, like a finger tapping a microphone (docs/THROAT.md).

**The band.** The arrangement sets each instrument's level and place (and
the drift turns each up or down), so the mix keeps them: an instrument's
strip only shapes its sound (a high-pass, boxiness and boom out, a dip where
the voice's consonants live, compression on the guitar, bass, fiddle and
drum, saturation on the bass so small speakers hear its pitch) and may
trim it. The band as a whole gets a little warmth (2.5 dB under 200 Hz) and
less boxiness (2 dB at 600 Hz, where the voice's vowels sit), and is set
`forward` dB under the voice, measured where the voice sings. On top of
that, while the voice sings, the band's presence range (around 2.6 kHz)
dips by up to 6 dB and the lute, which doubles the tune under the words,
steps back 3 dB (fiddle and whistle 2 dB); both clear within 20 ms of the
voice's first consonant and come back over 0.9 s after it stops, so
nothing breathes. Where the voice rests a while (the intro, the turns) the
band is ridden up (`RIDE`, 5 dB at `duck` 1), as an engineer rides the
fader in the breaks, and back down before the voice returns.

**The room** (songbird/synth/room.py) is regenerated from the harvest's
RT60, five-band tone and predelay, and only from them: the same numbers give
the same room, echo for echo, every rendition on a machine. Its early
reflections are mirror images (to the second bounce) of a player a little
left or right of centre in a room as large as the RT60 suggests (0.3 s is
about 5 m, 2.5 s about 18 m), with Sabine's absorption and a softer floor,
each echo smeared by the surface it met, coloured by the tone and arriving
from its side. The tail is noise decaying octave by octave (highs first),
coloured by the tone, heard alike by the two ears below a few hundred hertz
and independently above, as in a real diffuse field. There is no delay
network in it, so nothing rings metallic. Long rooms get a little less of
each send, so a church is heard as long, not as loud. The voice also has a
plate (1.5 s, bright, wide, no low end). The returns reach from 120 Hz to
12 kHz, so a harvested tone's ends are heard, give way 3 dB while the voice
sings (not where the choir sings with it: that is its space), and have a
peak stage of their own.

**The whole** is glued lightly (1.5:1 on what stands out of its
surroundings, never the song's arc), given a little weight (2 dB under
180 Hz), tilted if asked, and worn if asked (below).

**Mastering** (songbird/synth/master.py) brings it to the rendition's
`loudness` (Params; −14 LUFS by default, −12 for listeners' players that
don't normalize) integrated, with the true peak under −1 dBTP, measured with
4× oversampling as BS.1770-4 annex 2 asks: a player's reconstruction filter,
or a lossy decoder, swings between the samples. A soft clip rounds off the
sharpest peaks (the top 2 dB, about 0.1% of the samples), then a limiter
that looks ahead 5 ms and lets go over 80 ms catches the rest. Then seeded
TPDF dither to 16 bits.

## What a rendition can vary

`MixParams` (passed to `render()` and `mix()`; `songbird render --mix
rt60=2.2 wear=0.5`; the render starts from `params.mix` and records the
mix in its JSON). Values outside a range are held to it.

| Knob | Range | Default | What it does | Might map from |
|---|---|---|---|---|
| `rt60` | 0.3–2.5 s | 1.1 | how long the room rings, mid band | the harvested room |
| `tone` | 5 × 0–2 | 1, 1, 1, 0.9, 0.7 | the room's level in five bands, 40 Hz–16 kHz | the harvested room |
| `predelay` | 0.005–0.08 s | 0.012 | how soon the room answers | room size, or drift |
| `space` | 0–1.5 | 1 | how much of the room is heard: 0 dry | drift |
| `intimacy` | 0–1 | 0.5 | how close the singer is: 0 twice the voice's reverb, 1 half | the singer, drift |
| `width` | 0–1.4 | 1 | stereo width of band, choir and room; the low end stays centred | screen, drift |
| `forward` | 5–15 dB | 10 | how far the voice stands above the band while it sings | drift (a little) |
| `duck` | 0–2 | 1 | how much band and room make way for the voice (and the band rides up in its rests) | drift |
| `tilt` | −2–+2 dB | 0 | the record darker or brighter: ±this at 60 Hz and 12 kHz against 1 kHz | screen brightness |
| `wear` | 0–1 | 0 | how worn the recording sounds (below) | file ages |
| `balance` | name or role: ±12 dB | none | an instrument up or down, e.g. `balance=fiddle:2` | drift |
| `voices` | 0–1 | 1 | how much of the singers is heard: 0 takes the lead and the lineage choir out of the record, its room and its plate, and leaves the band as it was mixed for them, still making way where they sing (a backing track; the studio's **M** on the voice) | a person only |

**Wear** is how worn the recording sounds, off by default. Toward 1: the
tape's speed wanders (wow, about 0.2% at 0.5–0.8 Hz) and trembles (flutter,
5–14 Hz), so held notes waver by up to 2.3 cents RMS; the tape saturates
(distortion on loud tones from 0.9% at 0.1 to 5.8% at 1); the band narrows
(the top falls from 20 kHz to 7.6 kHz, the bottom rises to 80 Hz, with a
small head bump); hiss rises from 74 to 46 dB under the music; and from 0.35
the surface crackles, sparse clicks up to 15 a second. All of it is made
from the render's seed. The band's own `wear` (detuning, looser time) is the
arrangement's; this is the recording's.

## What a machine and the drift choose

`choose_params()` (the table is `songbird/variation.py`) sets the mix in
`params.mix`, which `songbird render` turns into MixParams before any
`--mix` changes: the machine's own value from its harvest
([HARVEST.md](HARVEST.md)), moved by the drift, and the child pulled 0.6 of
the way there from its parent. With no machine and no date the mix is the
seed's. A record with `room` in place of `mix` loads it as `mix`.

| Knob | The machine's own | Drift (view), at a drift of 1 | Kept within |
|---|---|---|---|
| rt60, tone | the harvested room, the machine's own (else its parent's) | none | as measured |
| predelay | 0.012 × (rt60 / 1.1)^0.8, ±19% by the machine; part of the room, never inherited | none | 0.005–0.04 s |
| space | 1 ± 0.12 by the machine | space (weeks), ±0.3 | 0.7–1.3 |
| intimacy | 0.5 ± 0.12 by the machine | near (weeks), ±0.12 | 0.3–0.7 |
| width | 1 − 0.08 the screen's warmth, ±0.05 by the machine | sheen (weeks), ±0.12 | 0.9–1.25 |
| forward | 10 ± 0.6 dB by the machine | voice (daily), ±0.5 dB | 8.5–11 dB |
| duck | the parent's | duck (weeks), ±0.4 | 0.6–1.4 |
| tilt | 0.8 dB × the screen's brightness (−1 dark to 1 light) | sheen (daily), ±0.5 dB | ±1.2 dB |
| wear | 0.12 + 0.24 × file-age wear + 0.03 × tiredness, 0 for young files; the machine's own | none | 0–0.4 |
| balance | not set: the band's own gains carry the balance (docs/BAND.md) | | |

The recording's wear crackles from 0.35, which only machines whose files are
some eight years old or more reach. Over 16 made-up machines and four years:
space 0.77–1.23, duck 0.76–1.24, intimacy 0.38–0.64, width 0.90–1.09,
forward 9.4–10.5 dB, tilt ±0.55 dB, wear 0–0.33 (none crackled), each barely
moving from one day to the next.

**H's seed** (songs/h-now-its-by-you.json) sets `forward` 7.5, `space` 0.8,
`width` 1.25 and `intimacy` 0.65, and the band's `drum` 1.5, from a mix
review of the contest renders. At `forward` 7.5 the band sits a decibel
closer and the 125-250 Hz region comes up to 8 dB under 500-1000 Hz (9 at
10). At width 1 the verses read L/R correlation 0.97 against a folk record's
0.87 (the voice centred 8-12 dB over everything keeps them narrow whatever
the width). At gain 1 the drum sits at −39 LUFS where it plays, 10 dB under
the bass and guitar, so the patterns that mark the build are barely there.
Left alone, with reasons: `duck` below 1 (clarity −1 dB), `balance bass:+2`
(the low-mid deficit is the guitar's and harp's body, not the bass).

## Measurements

H, "Now It's by You", 150 s, mastered to −14 LUFS at the design defaults
(`forward` 10), the eight-piece band, with and without the lineage choir.
The reference row is a folk instrumental from a music generator, measured
only for comparison.

| | Loudness | True peak | LRA | PLR | Crest | L/R correlation | Side/mid |
|---|---|---|---|---|---|---|---|
| band | −14.0 LUFS | −1.1 dBTP | 7.5 LU | 13.0 dB | 15.9 dB | +0.93 | −13.9 dB |
| band and choir | −14.0 | −1.0 | 8.8 | 13.0 | 15.9 | +0.83 | −12.8 |
| reference | −12.0 | −0.8 | 3.8 | 11.2 | 13.6 | +0.87 | −11.2 |

The master uses the headroom up to the ceiling for the peaks rather than
squashing anything, and keeps the band's arc. At equal loudness against the
reference the spectrum is 6 dB under it at 63 Hz and 8 dB under at 125 Hz;
500 Hz–1 kHz is 5 to 9 dB over, the voice, which a vocal record has and an
instrumental doesn't.

**Words understood.** Whisper base.en on the finished mix
(`tools/wer_suite.py --mix --sketch h`) gets about 32% of H's words wrong
over 3 to 5 seeds; on the dry voice alone, 15%.

**The delivery kept.** Per sung vowel on H, the level after the voice's
strip against its dry level: 82% of the singer's syllable-to-syllable
contrast is kept by the strip, 78% as finally heard (glue and limiter
too); the equalizer alone keeps 93% (vowels differ in how much of them sits
at 900 Hz), the dynamics 85% of what they are given. The loud half of the
singer's intended syllables stands 4.0 dB over the soft half dry, 3.4 dB as
heard.

**The room.** T30 per octave within a few percent of what was asked at
every octave, rt60 0.3 to 2.5 s; the ears' coherence 0.8 at 125 Hz, under
0.1 above 1 kHz; echo density Gaussian by 50 ms. Clarity through the room
(dry plus room plus plate, a centred source): the voice's C50 about +18 dB
at every size (a close singer), the band's +18 dB in a 0.3 s room to +13 dB
in a 2.5 s one, the choir's +6 to +8 dB (further back).

**The checks** (`tools/mixcheck.py`, H with the band and the choir, at
`forward` 10): the room 3.3 dB under the band in the gaps; clarity (voice
over band and room, 1–4 kHz, while singing) +6.7 dB; what the mix adds to
the band's own dip under the words +0.3 dB (the band already comps 5 dB
softer there by arrangement); clip and limiter at most 1.3 dB over any 10
ms, more than 1 dB on 0.1% of loud stretches; correlation never under +0.1
in any 400 ms window, the mono fold costing 0.4 LU; no clicks the stems
didn't bring (the stems carry 23 sharp high-band jumps, the whistle's and
bass's attacks; the master 11); nothing under 30 Hz (−47 dB). The master's
clip and limiter engage only in a dense bridge with a choir (0.3% of the
bridge's samples in the knee); in the default arrangement they take nothing.

**Time.** The mix and master of H take about 3.5 s and its whole render
about 7 s, the channel strips and a long signal's two channels worked on
threads, the same bytes whatever the thread count (docs/notes/PERFORMANCE.md).
The numba kernels compile once, about 1.5 s, and are cached.

## The hiss

Two things can put a hiss or a murmur into a mix that the reverb then
carries: an "s" the de-esser misses, and a singer sounding where it doesn't
sing. The room and plate add nothing of their own; they return what they
are sent.

**The de-esser** (`fx.deess`) weighs the highs over the split (4.5 kHz,
where this singer's "s" centres) against the voice's body, the voice an
octave under the split, where no "s" reaches: an "s" stands 5-11 dB over
the body, a vowel 24-34 dB under. It splits the voice without phase (its
low-passes run forward and back): the part turned down is −14 dB half an
octave under the split, −6 dB at it and all of the voice above, adds back to
the voice exactly, and is never turned up. `excess` +3 dB over the body,
`ratio` 3, at most 8 dB. The choir group goes through the same de-esser
after its equalizer. On the learned singer (4-hana) it works 12.0% of the
sung time (more than 2 dB on 7.4%), takes 4.7 dB (median; 2.3-5.1 dB, 10th
to 90th percentile) off the loud "s" sounds, the hardest from −3.3 dB at 4-5
kHz to −7.3 at 8-9 kHz, and moves the vowels' 150-2000 Hz by 0.002 dB (99th
percentile). A de-esser that compares an "s" with the rest of the voice
above a second-order high-pass reads it as mostly its own reference and
barely acts; that is why the body is the voice an octave under the split.

**The singers are silent where they don't sing.** The throat's network
learned from phrases whose silences were short (half under 0.07 s, 99% under
0.51 s, none as long as 1 s). Told of a long rest as one silence, it guesses
an envelope far louder than silence, which the vocoder fills with noise: a
murmur coloured like a vowel, up to 8 dB under the singing at the start of a
220 s wait, and through the choir's room send the room runs level with the
band in the intro. So `throat.timeline` tells the network of a silence
longer than 0.6 s (`SILENCE`) as one 0.6 s long, its first and last halves at
their own pace and its middle held; and `throat.hush` silences the vocoder
where nothing is sung, from 60 ms before a sung phone to 150 ms after one,
with a 30 ms fade (`HUSH`). A phone's release has fallen 70 dB within 50 ms,
before the murmur's return at about 100 ms; the gate opens 45-75 ms before
an onset, where the murmur's foot lies 47-58 dB under the vowel; inside sung
stretches nothing changes. The breaths are added after. Where a singer
rests it sits 53-63 dB under its singing (the breaths), and a note after a
60 s wait is within 1 dB of the same note after a 1 s one.

**Across the styles renders** (`tools/hisscheck.py`): what remains is
consonants on a sparse texture (an "s" over a dark electric piano can stand
22 dB over the mids for 100 ms), as in any record, and the kit's cymbals. A
voiced "z" loses only about 1 dB, its voicing counting as the body (see
Doubts).

## Doubts and next

- **The balance is a judgment.** `forward` 10 puts the voice well on top.
  Whisper wants it; the review thought 6–7 would sound warmer and more like a
  band. At 7–8 the low end comes up about 3 dB and Whisper loses 2–4 points.
  H's seed sits at 7.5.
- **Whisper is a jumpy judge.** One section it mishears can move H's score
  by several points, so single changes under about 4 points were read as
  noise, settings were chosen on what a mix engineer would do, and Whisper
  kept as the floor.
- **One reference.** The spectral and dynamic targets came from one
  generated folk instrumental and from SoulX-Singer renders for the voice. A
  vocal folk reference would say more about the voice's level and
  brightness.
- **The learned singer's presence** (its 3.5 kHz) hasn't been looked at on
  its own.
- **The de-esser's depth is a judgment.** About 5 dB off a loud "s", at most
  8 (`excess` +3 over the body, `ratio` 3, `most` 8). A voiced "z" loses
  about 1 dB: `excess` 0 takes 1.9, −3 takes 3.0, and change little else.
  A de-essed "s" still stands 17.8 dB over the lead's low mids in the stem;
  a close-miked singer is nearer 10-15, and `most` 10 or `ratio` 4 would go
  there. It also dips bright vowels by more than a decibel 8% of the time (an
  HF warble); a hold above threshold would target that better than `excess`.
- **The plate is bright by design:** its top decays at 0.87 of its middle
  (the room's at 0.55), so a 120 ms "s" rings within 10 dB for 0.23 s.
  `PLATE_AIR` (0.75, 0.95, 1.0, 0.85, 0.6) would darken its top (6-12 kHz
  RT60 1.24 to 0.97 s, the vowels' tails unchanged): a matter of taste.
- **Line ends are as sudden as the throat makes them**: it lets go of a
  phone 54 dB in 50 ms. If a line's last note sounds clipped, that is the
  network's release, not the hush.
- **Verses are narrow** at width 1 (L/R correlation about 0.95 while the
  voice carries a sparse verse), wide in the bridge; the band's own placement
  decides most of it. `width` 1.2–1.3 opens the verses.
- **The stems' own attacks.** The whistle's and the bass's note starts have
  sharp high-band jumps (tools/mixcheck.py counts 23 in H's stems); the mix
  doesn't add any, but they may be heard as clicks.
- **Across machines.** A render is byte-identical run to run on one machine
  (the FFTs use a fixed number of threads); FFT and libm rounding differ
  across CPU architectures, so the hash that names a rendition won't.
- **Wiring.** render_stems' `VOICE_GAIN` and `CHOIR_GAIN` don't set the
  balance (the voice and choir are set by loudness in the mix); they only
  scale `--stems`.
