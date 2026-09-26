# How the song is mixed and mastered (2026-09-26)

A rendition should sound like a well-made record: a warm, intimate, modern
acoustic folk record with the voice clear and in front. Before this, the
stems were summed at fixed gains, sent into one room, and brought to −14 LUFS
under a sample-peak limiter. Now every stem has a channel strip, the voice,
the lineage choir and the band each have a bus, the room is built from the
harvest's numbers the way a room sounds, and the master keeps the true peak
under −1 dBTP. Nobody but the artist can listen; everything here was judged
by measurement, against a reference, against the singer's own design, and
by a read-only Fable review that measured the mix itself. Listening
decides; these are the guard rails.

## The path

`synth.mix()` (songbird/synth/mixing.py) takes the stems by name. A stem's
name gives its role: voice, choirN, lute (or melody), guitar, harp, bass,
fiddle, whistle, drum, drone; anything else is treated as a plain
instrument. Stems of any shape are taken (mono, one column, a different
length). The tools are in songbird/synth/fx.py.

**The voice.** High-passed at 80 Hz, 2 dB less honk around 900 Hz, 2 dB of
presence at 3.5 kHz (set beside natural singers: SoulX-Singer renders of the
same score). Its air (7–14 kHz against 0.5–2 kHz) is measured, and only a
voice brighter than natural singers is brought back, halfway. A de-esser
that listens to the balance of the highs against the rest of the voice,
not to how loud the singer is. A compressor that only leans on the
syllables that stand out of their phrase: its threshold rides 3 dB over the
level of the three seconds around each moment, so a syllable is evened
against its neighbours but a quiet verse stays quiet and a full refrain
full (2:1, 15 ms attack; on H it works on 30% of the sung time, by more
than 2 dB on 4%). Then a touch of saturation, and a peak stage for its
rarest peaks. Everything the voice's tools react to is measured on the
voice itself, so a quieter or brighter singer (the learned one) is treated
the same.

**The lineage choir** (the bridge and tag, `--choir N`) is one group:
thinner below 260 Hz and in the presence range than the lead, compressed
together, 35% wider, 4 dB under the lead, and further back in the room (a
bigger send, reaching the room 20 ms later). Its consonants jumped far over
the rest and made the master limiter work 5 dB in the bridge; a peak stage
rounds them off now.

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
band is ridden up 3 dB, as an engineer rides the fader in the breaks, and
back down before the voice returns.

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

**Mastering** (songbird/synth/master.py) brings it to −14 LUFS integrated
with the true peak under −1 dBTP, measured with 4× oversampling as BS.1770-4
annex 2 asks: a player's reconstruction filter, or a lossy decoder, swings
between the samples. A soft clip rounds off the sharpest peaks (the top
2 dB, about 0.1% of the samples), then a limiter that looks ahead 5 ms and
lets go over 80 ms catches the rest. Then seeded TPDF dither to 16 bits, as
before.

## What a rendition can vary

`MixParams` (passed to `render()` and `mix()`; `songbird render --mix
rt60=2.2 wear=0.5`; the render starts from `params.room` and records the
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

**Wear** is the plan's "how worn the arrangement sounds", off by default.
Toward 1: the tape's speed wanders (wow, about 0.2% at 0.5–0.8 Hz) and
trembles (flutter, 5–14 Hz), so held notes waver by up to 2.3 cents RMS;
the tape saturates (distortion on loud tones from 0.9% at 0.1 to 5.8% at 1);
the band narrows (the top falls from 20 kHz to 7.6 kHz, the bottom rises to
80 Hz, with a small head bump); hiss rises from 74 to 46 dB under the music;
and from 0.35 the surface crackles, sparse clicks up to 15 a second. All of
it is made from the render's seed. The band's own `wear` (detuning, looser
time) is the arrangement's; this is the recording's.

## Measurements

H, "Now It's by You", 150 s, mastered. "Before" is the code this branch
started from (the old instruments, one room, fixed gains); "band, its mix"
is the new band as its own branch mixed it; "band, new mix" is the same
stems through this mix (the merged sound), with and without the lineage
choir. The reference is one Eleven Music folk instrumental (dev-only,
renders/production/mix/reference/, never shipped).

| | Loudness | True peak | LRA | PLR | Crest | L/R correlation | Side/mid |
|---|---|---|---|---|---|---|---|
| before | −14.0 LUFS | −3.8 dBTP | 7.0 LU | 10.2 dB | 13.5 dB | +0.90 | −12.5 dB |
| after (old instruments) | −14.0 | −1.1 | 5.1 | 13.0 | 16.2 | +0.93 | −14.4 |
| band, its mix | −14.0 | −3.9 | 7.3 | 10.1 | 13.0 | +0.84 | −10.2 |
| band, new mix | −14.0 | −1.1 | 7.5 | 13.0 | 15.9 | +0.93 | −13.9 |
| band and choir, new mix | −14.0 | −1.0 | 8.8 | 13.0 | 15.9 | +0.83 | −12.8 |
| reference | −12.0 | −0.8 | 3.8 | 11.2 | 13.6 | +0.87 | −11.2 |

The old mix never reached its ceiling (its true peak sat 3 dB under it):
the new master uses that headroom for the peaks rather than squashing
anything, and keeps the band's arc (LRA as the band's own mix, higher with
the choir). The before-and-after spectra at equal loudness, against the
reference: the old mix had almost nothing under 150 Hz (63 Hz −39 dB,
125 Hz −20 dB against the reference); with the new band and this mix it is
63 Hz −6, 125 Hz −8, the rest of the difference being the voice, which a
vocal record has and an instrumental doesn't (500 Hz–1 kHz +5 to +9 dB).

**Words understood** (Whisper base.en on the finished mix,
`tools/wer_suite.py --mix --sketch h`):

| | 3 seeds | 5 seeds |
|---|---|---|
| before (old instruments, old mix) | 44.9% | 45.8% |
| old instruments, new mix | 42.6% | 43.3% |
| new band, its own mix | 36.7% | 36.7% |
| new band, new mix | | 32.0% |
| merged main (the band, the variation table, the new mix) | 31.8% | |

The dry voice alone is 15%.

**The delivery kept.** Per sung vowel on H, the level after the voice's
strip against its dry level: 82% of the singer's syllable-to-syllable
contrast is kept by the strip, 78% as finally heard (glue and limiter
too); the equalizer alone keeps 93% (vowels differ in how much of them sits
at 900 Hz), the dynamics 85% of what they are given. The loud half of the
singer's intended syllables stands 4.0 dB over the soft half dry, 3.4 dB as
heard. The de-esser works 4.6% of the sung time, never more than 1.7 dB.

**The room.** T30 per octave within a few percent of what was asked at
every octave, rt60 0.3 to 2.5 s; the ears' coherence 0.8 at 125 Hz, under
0.1 above 1 kHz; echo density Gaussian by 50 ms. Clarity through the room
(dry plus room plus plate, a centred source): the voice's C50 about +18 dB
at every size (a close singer), the band's +18 dB in a 0.3 s room to +13 dB
in a 2.5 s one, the choir's +6 to +8 dB (further back).

**The checks** (`tools/mixcheck.py`, H with the new band and the choir): the
room 3.3 dB under the band in the gaps; clarity (voice over band and room,
1–4 kHz, while singing) +6.7 dB; what the mix adds to the band's own dip
under the words +0.3 dB (the band already comps 5 dB softer there by
arrangement); clip and limiter at most 1.3 dB over any 10 ms, more than
1 dB on 0.1% of loud stretches; correlation never under +0.1 in any 400 ms
window, the mono fold costing 0.4 LU; no clicks the stems didn't bring
(the stems carry 23 sharp high-band jumps, the whistle's and bass's
attacks; the master 11); nothing under 30 Hz (−47 dB). One stays open: the
low end, 125–250 Hz, sits 10.7 dB under 500–1000 Hz, where 8 would be
warmer; the voice at `forward` 10 dominates the middle (see Doubts).

**Time.** Mixing and mastering 12 stems of 150 s takes about 6 s (the
numba kernels compile once, about 1.5 s, and are cached). A full `songbird
render` of H: 17 s on the old instruments, 26 s with the band.

## Doubts and next

- **The balance is a judgment.** `forward` 10 dB puts the voice well on top
  (the old mix had it about 14 dB over a much quieter band; the new band's
  own mix about 7). Whisper wants it; the review thought 6–7 would sound
  warmer and more like a band. At 7–8 the new band's low end comes up about
  3 dB and Whisper loses 2–4 points (still at or under the band's own mix);
  on the old instruments it lost 7–14. If the voice sounds too far in
  front, `forward` 8 is the first thing to try.
- **Whisper is a jumpy judge.** One section it mishears can move H's score
  by several points, so single changes under about 4 points were read as
  noise, settings were chosen on what a mix engineer would do, and Whisper
  kept as the floor.
- **One reference.** The spectral and dynamic targets came from one Eleven
  Music folk instrumental and from SoulX-Singer renders for the voice. A
  vocal folk reference would say more about the voice's level and
  brightness.
- **The learned singer** (engine "learned") wasn't tried: its weights
  weren't in any tree. Everything the voice's tools react to is relative to
  the voice itself, its air shelf is measured, and its equalizer is gentle,
  but its de-esser and presence should be looked at when it sings.
- **Verses are narrow** (L/R correlation about 0.95 while the voice carries
  a sparse verse), wide in the bridge; the band's own placement decides
  most of it. `width` 1.2–1.3 opens the verses.
- **The stems' own attacks.** The whistle's and the bass's note starts have
  sharp high-band jumps (tools/mixcheck.py counts 23 in H's stems); the mix
  doesn't add any, but they may be heard as clicks.
- **Across machines.** A render is byte-identical run to run on one machine
  (the FFTs use a fixed number of threads); FFT and libm rounding differ
  across CPU architectures, so the hash that names a rendition won't.
- **Wiring.** The drift and harvest can move any MixParams field within its
  range (the table above has what each might map from); `params.room`
  already reaches the mix. render_stems' VOICE_GAIN and CHOIR_GAIN no
  longer set the balance (the voice and choir are set by loudness in the
  mix); they only scale `--stems`.
