# The learned throat (2026-09-25)

The artist's direction: "use as many vocal sources as we need to train our own smaller voice
synthesis engine that is optimized for our use case", and adopt SoulX-Singer directly only if that
fails. This is the learned throat of docs/VOICE-OPTIONS.md §4, trained on synthetic singers
rather than the artist's speech. Our program still decides everything about the delivery:
- when each phone starts and ends (`voice.schedule`);
- the pitch, with its glides, vibrato and phrasing gestures (`voice.pitch_track`);
- how hard each syllable is leaned on.

The throat only decides how those sounds sound. A Fable review checked the plan before any
training. Its numbers and decisions are below where they were used.

## How it works

- **The network.** `songbird/synth/throat.py` holds a small network: about 0.6M parameters, a
  dilated convolution stack over 5 ms frames.
  - **In:** the phone and two neighbours either side, its role (onset, vowel or coda), how far
    through the phone and how long it is, the syllable's stress, the note's level, log f0 and its
    slope, and a singer embedding.
  - **Out:** a spectral envelope (log power at 128 mel-spaced points to 11.8 kHz) and
    aperiodicity (32 points), as Morise's WORLD vocoder analyses a voice.
- **The vocoder.** Our own, in numpy, in the manner of WORLD: minimum-phase pitch pulses plus a
  period of shaped noise each.
- **Everything ships.** The network runs in numpy too, so what ships is the weights (a few MB)
  and code.
- **Our source.**
  - An envelope learned from a singer already contains that singer's glottal source.
    Exciting it with our Liljencrants-Fant pulses as well would double the tilt. Fable measured
    −12 dB at 2–4 kHz: a woolly voice.
  - So the voice's `rd` and `tilt` act relative to a reference source (rd 0.8, tilt 0.4). They
    change only the voiced part: pressed (rd 0.5) +2.6 dB at 4 kHz, breathy (1.6) −5.9 dB.
- **The machine's voice.** A point among the trained singers' embeddings (by default all of
  them evenly; never one alone), plus `tract` as a frequency warp of the envelope. The
  delivery settings, the phrasing and the vibrato are what listeners mostly tell singers apart
  by, and they keep working as before.

## Where the sound comes from

No recording of any person was used for the house model. Since 2026-09-28 the shipped model is that
model fine-tuned once on the volunteers' takes together (below, "Everyone's voice").
- **The teacher.** SoulX-Singer (Apache-2.0; a 2.8 GB zero-shot singing model trained on 42,000
  hours of undisclosed singers) sings our own scores. It runs beside the repo and never ships.
- **Its timbre prompts.** Ten-second clips of seven synthetic singers that Eleven Music made
  for H (ElevenLabs' terms allow training on outputs). The throat's timbres are second-hand
  statistics of two generative models.
- **The corpus.** `tools/throat/corpus.py` plans it:
  - every song in songs/;
  - all 38 verses, 6 refrain couplets and 3 bridges of H's bank;
  - lines written for the English sounds our songs lack.
  Each item is sung by two of the seven singers (H by all seven), at a tempo within ±10%. Low
  singers sing in their own register (an octave down), not transposed.
- **Rendering.** `tools/throat/soulx_batch.py` renders at 24 kHz; SoulX runs at about real time
  here.
- **Analysis.**
  - `tools/throat/features.py`: WORLD analysis. Harvest f0, searched within a fifth of the
    notes.
  - `tools/throat/phones.py`: phone boundaries from the Montreal Forced Aligner. Its dictionary is
    exactly the phones SoulX was asked to sing. High voices are aligned an octave down by our
    vocoder, envelope and timing kept.
  - `tools/throat/check.py` scores each segment; `tools/throat/dataset.py` builds the frames.
    Lines with a misplaced word are masked out.

## Checks so far

| | Result |
|---|---|
| Vocoder: our numpy WORLD against pyworld's, same features | equal level (±0.2 dB per frame); log-mel distance from the original 5.9 dB vs WORLD's 5.3 (since the DC fix below, 3.7 against WORLD's 4.0 on house singers) |
| Features: 128/32-point mel grids against WORLD's full envelope | no measurable loss (5.30 vs 5.31 dB) |
| Pitch of the corpus | 98% of notes within 50 cents |
| Alignment | every note's vowel found; 93% where the note is sung (first 14 segments) |
| **Oracle**: SoulX's own envelopes, warped onto our schedule, at our pitch, through our vocoder (4 segments, 3 singers) | **11.8%** words misheard, against SoulX itself 10.5% and our formant singer 34.6% on the same notes |

The oracle was Fable's gate before training. It asks whether our puppeteer, driving a perfect
throat, still sounds right and is understood. It is, so the interface holds. What remains is
how close a small network gets to that throat.

## The network, as the corpus grows

Whisper on H's refrain and seed verses, dry, one render each (the WER suite's method; the formant
singer on the same notes and seed: 16.9%):

| Corpus | Held-out loss (L1, normalized) | Words misheard on H |
|---|---|---|
| 14 min (v0) | 0.33, rising after 1,000 steps: too little to generalize | 21.0% |
| 39 min (v0b) | 0.29, still falling at 6,000 steps | 17.4% (16.4% with the teacher's consonant lengths) |
| 100 min (v1, 0.89M parameters, 12,000 steps) | 0.26 | **11.9%** |

More data is what it wants. v1, on the whole first corpus, is the first learned voice clearly
understood better than the formant singer. It is also the benchmark: its seven voices are the Eleven
Music ones, so it will never ship (see below).

## Taking ElevenLabs out (2026-09-25, late)

The artist found that ElevenLabs' terms likely don't allow training on its output. So the seven
Eleven Music voices are a benchmark only, and nothing trained on them will ship. Every corpus
singer now records where its timbre came from (`source` in tools/throat/corpus.py's SINGERS,
carried into every label, the dataset and the model's config). The fix is then a switch, not an
excavation: `tools/throat/dataset.py --without eleven-music` builds a training set with none of
their voices, and training on that gives a throat with no Eleven lineage.

The replacement is the **house singers**. SoulX-Singer is prompted with our own formant singer,
sung with ten different VoiceParams (longer and shorter tracts, pressed and breathy sources, high
and low registers). SoulX sings our scores naturally in each of those timbres, and the throat
learns from that.

- **Every timbre starts in this program.** SoulX's natural delivery is laid over it. The artist's
  direction since (2026-09-26) is to aim for as natural a voice as we can: "we don't need to *try*
  to make it sound synthetic, i'm confident there will always be an uncanny valley."
- **First test, two items per singer** (`tools/throat/judge.py`, Whisper on each segment):

  | Timbre prompt | Notes within 50 cents | Words misheard |
  |---|---|---|
  | house singers (6) | 92–100% | 7–12% |
  | Eleven Music, same items | 91–100% | 0–6% |

  House singers are a little less clear, but they're good training material. Their spectra keep a
  trace of the formant singer's clean upper harmonics under natural consonants and transitions.

Consenting human singers (docs/SINGERS.md) are the next source. Each of them is a prompt for
unlimited SoulX singing as well as direct training data. They'd enter the same way,
`source="human"`.

## In the song (2026-09-26, night)

**Heard in the band, the learned voice is far clearer than the formant singer.** Whisper on H's
finished mix (instruments, room, master; `tools/wer_suite.py --sketch h --mix`), the same seed and
notes:

| Singer | Words misheard in the mix |
|---|---|
| formant singer | 34.7% |
| learned throat (the v1 benchmark) | **15.1%** |

Automatic naturalness (UTMOS, a speech-trained predictor: a rough guide on singing), dry, on H:

| Voice | UTMOS |
|---|---|
| formant | 1.47 |
| v0b | 1.68 |
| v1 | 1.95 |
| SoulX itself on H's lines | 2.4 to 2.7 |
| our vocoder resynthesizing SoulX's own features (the ceiling) | about 0.25 below SoulX |

So most of what is left is in the network and the delivery, not the vocoder.

**Each machine sings with a singer of its own.**
- *The blend (`variation.choose_timbre`):* when the learned throat sings, a machine's singer is a
  blend of the trained singers who sing near where it sings. It is drawn from the machine's
  identity (`throat.machine_mix`), pulled 0.6 of the way from the parent's blend as every trait is,
  and never more than 0.6 of any one singer (`throat.capped`), so no rendition is ever one of the
  synthetic singers the throat learned from.
- *The lineage choir:* it sings through the throat too. Each earlier version the record remembers
  (up to six, the parent's first) sings in its own voice. An ancestor that sang with the formant
  singer is heard as a throat singer of its own, drawn from its id.
- *While the formant singer is the default, none of this changes anything.*

## Vocoder (2026-09-26)

The artist: "I still want to make the voice less robotic (we don't need to *try* to make it sound
synthetic, i'm confident there will always be an uncanny valley)." A WORLD-style vocoder is the
classic source of a robotic buzz, so before changing ours I measured what it loses against the
voice it resynthesizes. `tools/throat/vocoder_eval.py` does it on copy synthesis of 20 house-singer
segments (two per singer, 12 s each, WORLD features through `synthesize`, against SoulX's
original), with the same measures on every signal:
- how alike consecutive periods are per band, once aligned (periodicity, as an HNR);
- how steady each harmonic's phase stays from one period to the next (coherence);
- how much of a band's energy falls in the loudest quarter of each period, and how peaky the
  band is (excess kurtosis);
- levels per band, a log-mel distance, UTMOS and DNSMOS.

A Fable review checked the diagnosis and the plan before any change, and its experiments shaped
two of them.

### What was lost

- **A bug.** The DC remover took each pulse's DC away over the 43 ms after it instead of
  around it, as WORLD's does. It left a slow wobble under the voice and a bump after every
  phrase's last pulse: most of copysynth.py's log-mel distance, which is dominated by its lowest
  band. Little of it was audible after sing()'s 60 Hz high-pass.
- **A click every period.** WORLD's pulses are minimum phase, so each pulse's upper harmonics
  arrive together. The teacher's 4-8 kHz energy is spread through the period: 46% of it in the
  loudest quarter of each period against our 61%. Its excess kurtosis at 5-8 kHz is 1.4 against
  our 3.1.
- **Upper harmonics locked from period to period.** Above 4 kHz ours was 1.3-1.7 dB more
  periodic than the teacher and each harmonic's phase step steadier (coherence .60 against .56 at
  4-6 kHz).
- **Too periodic below 4 kHz as well** (2.5-4 dB): what cycle-to-cycle jitter would fix, but see
  below.
- **Flattened formants in the learned engine.** A network's envelope is an average. On its two
  held-out segments the house model's envelope rises and falls 1.9 dB around its own trend
  (RMS, 200 Hz-5 kHz); the natural envelope does 3.3 dB (3.1 averaged over 25 ms, all a 5 ms
  network can be asked for). The predicted aperiodicity is right: within 0.3 dB of D4C's in
  every band.
- **Not lost:**
  - The aperiodicity's resolution. D4C estimates aperiodicity at knots 3 kHz apart, so the 32
    mel points are already finer than their source. The feature grid needn't change and
    nothing needs retraining.
  - The timing of the noise. The teacher's high band is *less* bursty than ours, not more, so
    pitch-synchronous noise shaping would have gone the wrong way.
  - Onsets and offsets: the same steps in level at voicing boundaries.
  - Levels above 4 kHz: within 0.6 dB.
- **Left alone.** Below 4 kHz every resynthesis, pyworld's included, is 1.2-2.1 dB louder than
  the teacher, the most at 0-1 kHz. It's WORLD's own analysis bias, and it grows with pitch: on a
  synthetic voice Fable measured +0.3 dB at 0-1 kHz at 150 Hz and +2 dB at 350 Hz. A fixed
  correction would be wrong for every voice but the average, and 2 dB of warmth isn't what
  "robotic" means.

### What changed

All of it is in `songbird/synth/throat.py`; `synthesize()` keeps its signature and a seed still
gives one voice.

1. **The DC remover is centred on each pulse,** with room laid out before the pulse.
2. **Spread (`Texture.spread` 0.25; 0.15 until 2026-09-27).** A fixed all-pass whose group delay wanders along frequency
   by that fraction of each pulse's period (RMS), from 1.5 kHz, full above 3 kHz. It's the same for every
   pulse and every song (MELP's pulse dispersion, in effect). A pulse's upper harmonics now
   arrive spread through part of the period, still periodic. It's scaled to the period because
   a fixed delay smeared the altos and hardly touched the basses.
3. **Scatter (`Texture.scatter` 0.5; 0.4 until 2026-09-27).** A fresh random phase on every pulse (radians, smooth over
   300 Hz), rising in from harmonic 8 to 20. That's where harmonics stop being heard one by one,
   and it unlocks them from period to period.
4. **Sharpening (`sharpen`, `SHARPEN` 1.5, in `sing()` only).** A predicted envelope's peaks and
   valleys are pushed 1.5 times as far from its own trend (a Hann over 17 mel points), each
   frame's power kept: 1.9 dB of formant contrast becomes 2.6.

`throat.PLAIN` is WORLD's own synthesis, for comparison. `tools/throat/vocoder_eval.py
--variant NAME key=value` tries other settings.

### Spread and scatter raised (2026-09-27)

A review of the voice's roughness measured steady vowels' 4-8 kHz still bunched at the pulse: excess
kurtosis 2.8 against the teacher's 1.3, 83% of the band's energy in the loudest quarter of each period
against 75% (the periodic part carries it, not the noise; the predicted aperiodicity in vowels sits 3-4
dB under the teacher's). In a low voice (a stand-in shifted down an octave, 189 Hz) the pulse rate falls
into the roughness band and the >2 kHz envelope's 150-400 Hz modulation read 45% against the teacher's
27-30%. Spread 0.25 with scatter 0.5 lands on the teacher (0.3/0.6 overshoots: kurtosis 0.8); the same
scripts are in the session's scratch, `probe_low.py`, and `tools/throat/vocoder_eval.py --variant` tries
other settings. Raising the predicted aperiodicity 3 dB helps the low voice a little more and was left
for a listening test.

### The numbers

Copy synthesis, 20 house-singer segments (teacher / old vocoder / new):

| | Teacher | Old | New |
|---|---|---|---|
| 4-8 kHz energy in the loudest quarter of each period | .46 | .61 | .52 |
| above 8 kHz | .41 | .53 | .45 |
| excess kurtosis 3-5 kHz / 5-8 kHz | 0.8 / 1.4 | 1.5 / 3.1 | 1.1 / 1.2 |
| periodicity 4-6 kHz (dB) | 1.0 | 2.5 | 1.7 |
| coherence 4-6 / 6-8 / 8+ kHz | .556 / .474 / .400 | .603 / .519 / .441 | .585 / .499 / .425 |
| log-mel distance (copysynth.py's) | | 4.53 dB | 3.68 dB (pyworld 4.04) |
| the same high-passed at 50 Hz | | 3.26 dB | 3.17 dB |
| UTMOS | 2.08 | 1.92 | 1.98 |
| DNSMOS SIG / OVRL | 3.21 / 2.94 | 3.19 / 2.90 | 3.18 / 2.89 |

- The UTMOS gain is almost all the spread: +0.065 ± 0.016 paired, better on 18 of 20 segments.
  The scatter adds +0.003.
- DNSMOS is flat within its noise here, and a little lower in the learned engine (below).
  DNSMOS SIG is a speech enhancer's distortion score, so the lower figure may count added phase
  irregularity as distortion. That's a reading, not a finding.

The learned engine singing H's refrain and seed verses (122 s, dry, seed 1). The house model is
the one to judge; model-v1, the Eleven benchmark, was listened to only:

| | UTMOS | DNSMOS SIG / OVRL | Words misheard | 4-8 kHz in the loudest quarter | kurtosis 5-8 kHz |
|---|---|---|---|---|---|
| house model, plain vocoder | 1.72 | 3.22 / 2.63 | 14.2% | .79 | 4.0 |
| + spread and scatter | 1.80 | 3.19 / 2.60 | 14.2% | .69 | 2.3 |
| + sharpening 1.5 (new) | 1.89 | 3.17 / 2.59 | 12.8% | .65 | 2.1 |
| v1, plain | 1.92 | 3.18 / 2.53 | 11.9% | .70 | 2.9 |
| v1, new | 2.04 | 3.17 / 2.52 | | .62 | 2.2 |

The listening pair below (the vocoder as it was against the new one, loudness-matched) scores
UTMOS 1.74 against 1.88, DNSMOS SIG 3.19 against 3.18.

The learned engine is buzzier than copy synthesis: .79 of its high band falls in the loudest
quarter of each period, where the teacher has .46. The vocoder changes close about 40% of that
gap. What remains is the model's smooth envelope, without the frame-to-frame flutter of a
real one (2.7 dB per frame against 4.1). The vocoder costs no more time: 30 s of voice in about
a second, and H's two minutes sing in 6-8 s with the network.

### Tried and left out

- **Cycle-to-cycle jitter** (`Texture.jitter`, kept at 0). At 0.4-0.5% of the period it brought
  the lower bands' periodicity toward the teacher's and UTMOS up in the learned render (+0.014).
  But it cost DNSMOS (SIG −0.013 in copy synthesis) and did nothing for UTMOS in copy synthesis.
  voice.pitch_track already has a slow 0.3% wobble.
- **Per-pulse level flutter** (1-2 dB, above 1 kHz), standing in for a real envelope's
  frame-to-frame flutter. UTMOS fell (2.04 to 2.00 at 1 dB, 1.94 at 2 dB) and DNSMOS with it.
- **A fixed spectral tilt** fitted to the mean 0-1 kHz excess. It moved the levels onto the
  teacher's but UTMOS didn't follow, and the bias depends on pitch (above).
- **Interpolating the grid in power instead of log power.** It recovers 0.3 dB above 6 kHz but
  cost UTMOS (−0.019 ± 0.004), and it would change the space the model is trained in.
- **Pitch-synchronous noise shaping.** It went the wrong way (above).
- **A neural vocoder.** Not tried. A vocoder trained on spectral losses alone (DDSP, NSF, a Vocos
  generator without its discriminator) can't learn the phase texture that is the buzz. A GAN on
  2.4 hours of house singers wouldn't converge reliably in the few hours of shared GPU left
  tonight. And it would meet the same gap between natural and predicted features that makes the
  learned engine buzzier than copy synthesis.

  If it's tried later, the design with a head start is a small network refining this vocoder's
  STFT, adversarially trained, fine-tuned on the house model's own predictions. It should ship
  only if, from predicted features, it beats this vocoder by ear and on these measures.

### For the lead and the artist

- **Nothing to retrain.** The vocoder reads the same features, and the feature grids are fine.
- **Measures and teacher.** Every measure above compares against SoulX, a neural vocoder's
  texture, not a human's. Its high band is smoother than a person's voice probably is, so the
  settings stop short of it rather than copying it.
- **Listening files.** `renders/production/vocoder/` (README.txt there) has them:
  original, old vocoder and new for three house segments, then the house model singing H
  through the old vocoder and the new.

## Shipped: the house model sings by default (2026-09-26, morning)

songbird/synth/throat.npz is renders/throat/model-house.npz: 886,260 parameters, 3.6 MB, trained for
14,000 steps (160 channels) on the house corpus alone.
- *The corpus:* SoulX-Singer (Apache-2.0) singing our own scores (every song, H's verse bank, the
  coverage lines; about 143 minutes) in ten timbres. Each timbre was prompted by our own formant
  singer.
- *Provenance (as first shipped; see "Everyone's voice" for the fine-tune):* every singer in the model's config has source "formant", and no ElevenLabs audio is
  anywhere in its lineage.

| On H | Formant singer | House model |
|---|---|---|
| Words misheard, dry | 16.9% | 14.2%, and 12.8% with the new vocoder |
| Words misheard, in the mix | 34.7% | 14.2% |
| UTMOS | 1.47 | 1.75, and 1.89 with the new vocoder |

The ElevenLabs benchmark (v1, 11.9% dry) is still a little clearer. More house singing, and human
singers when they come, should close that gap.

- **The default:** VoiceParams.engine is now "learned". engine="formant" brings the formant singer
  back.
- **Tools that mean our formant singer ask for it by name:** the house singers' prompts, the
  reference singers, the phrasing extractor's template and the WORLD speech-to-song tool. The
  extractor's version hash and cached measurements are unchanged.
- **The choir** sings through the throat whenever the lead does.
- **Without the weights,** the formant singer sings, with a warning, so a program that lost its
  weights still sings.

## The consonants, sharpened (2026-09-27, evening)

The artist, on the contest render sung everyone's way: "saved" heard "seh", "part" too close to
"par", "old" without its d, "lit" and "light" without enough t, "laughed" trying to say a g and
missing its -ed, "scrolled" and "hummed" missing theirs, "song" not enunciating its ng, "own"
missing its n. Measured on the dry lead (each consonant's RMS against its vowel's, and above 3 kHz):

| | Level under the vowel | Above 3 kHz |
|---|---|---|
| coda t, k, p ("lit", "part", "quick", "laughed") | 10 to 48 dB | 30 to 51 dB: no release at all |
| coda d ("saved", "old", "hummed") | 8 to 18 dB | 28 to 36 dB: no different from the m or l before it |
| coda f ("laughed") | 18 dB | 35 dB: a low rumble, which is the "g" |
| coda n, ng | 8 to 14 dB | |

The teacher's word-final consonants are soft (singers let them go) and the network's are softer, at
5 ms a frame with a median coda t of 50 ms. What tells a listener a stop is its closure and its
release, and a weak fricative its hiss, and those are exactly what the formant singer always made
by rule. So `throat.articulate` lays them over the throat's own: through each stop's closure the
throat's output is dipped (to 20% for a voiceless stop, 50% for a voiced one, whose voice bar stays),
then the formant singer's burst (`phonetics.BURSTS`, by place, 3 dB under its levels, each burst its
own level and length within 1.5 dB and 15% so no two are alike; a velar's following the vowel's F2)
and, after a voiceless one, its aspiration fading to the stop's end; f, th, v and dh get the formant
singer's frication 4 to 6 dB over its levels, the voiceless ones with the throat's rumble dipped to
half under it; a coda nasal comes up 2 dB. s, sh, z and zh are left to the throat, which sings them
well. `VoiceParams.crisp` scales all of it (1 as described; 0 the throat alone, as before). The
first version dipped deeper (6% and 30%) with the bursts at full level; it read the same to Whisper
(7.3% against 7.1 to 8.2% over the softer settings tried, all within the suite's noise) and the
artist heard it as better but wanting "to soften or blend them slightly with measured
pronunciations", so the teacher's own consonant now stays audible under the rule-made one.

Whisper on H, the WER suite's method, two seeds dry and one in the finished mix:

| | crisp 0 (before) | crisp 1 |
|---|---|---|
| Words misheard, dry | 14.2% | **7.3%** |
| Words misheard, in the mix | 13.2% | **9.1%** |

"laughed", "scrolled", "part" and "saved" are heard now; "lit" (heard "only") and "hummed" (heard
"hung") still aren't. The choir sings through the same layer. Dry before-and-after excerpts of the
lines with these words are in renders/review/consonants-*.mp3.

The same evening, the lineage choir's bass voice was heard as "tapping a mic" through the bridge:
below about 160 Hz the vocoder's pulses are heard one by one (35 thumps a second at E2, 10 at D3, 2 at E3,
none from A3 up, counted as 5 ms frames jumping 12 dB over their surroundings). The choir's root now
keeps to E3 and above (`theory.FLOOR`); the bass instrument has the register below.

## The top notes' harshness (2026-09-27, night)

The artist, on the refrain: "a kind of harshness", the first o of "nobody" (B4, the tune's top) the
clearest case. Measured against SoulX-Singer singing the same syllable at the same pitch, the dry
voice sat 4.5 dB hotter at 2 to 5 kHz and 5.6 dB at 3 to 4 kHz; the same "no" an octave lower was
not. The mix added about 4 dB more there (the lead's +2 dB presence peak at 3.5 kHz, the saturation,
the band). Sharpening (SHARPEN 1.0) and the level fed to the network changed nothing measurable; a
darker source did: `VoiceParams.rd` 0.7 -> 0.9 and `tilt` 0.4 -> 0.7 take 2 to 3 dB off each band,
and the presence peak at 0.5 dB the rest, landing the mixed "no" 5.8 dB down at 2 to 5 kHz, level with
the reference. Whisper reads the darker voice the same (7.8% of H's words misheard, dry). The artist
chose it while saying the difference was hard to hear.

## Breath at the top (2026-09-28, small hours)

A spectrogram of one phrase at every stage of the mix and master (renders/review/stages-*.png) showed the
chain changing the voice hardly at all, and the dry voice's harmonics standing as clean lines to 10 kHz
with nothing between them: the buzz the artist kept hearing as "robotic". The natural reference is half
noise up there (aperiodicity 0.32 to 0.65 from 2 to 8 kHz against the throat's 0.18 to 0.48). So
`VoiceParams.air` now floors the learned throat's aperiodicity, rising from 0 at 2.5 kHz to `air` at 8 kHz
and above (`throat.air_floor`); 0.4 by default, chosen by ear ("a bit better, not perfect"). Whisper dry:
7.5% of H's words without, 8.9% at 0.4, 9.6% at 0.6.

## Everyone's voice (2026-09-28, 01:30)

The consent lets the recordings train the voice once, after singing closed, blended from everyone and
never set to sound like one person. So: `tools/throat/volunteers.py` and `clean_takes.py` cut the 79
takes into sung lines by their guides' scores, cancelled the melody guide where it leaked from a speaker,
gated the room, and kept what the check passed: 13.7 minutes by eight singers, the largest share 26%
(David), then an open-call singer, Milo, essqao, Gorman, Talia, Geoff and another open-call singer. All
of them are ONE singer to the network, "volunteers", source "human": there is no per-person embedding
to find. The house model was fine-tuned 14,000 steps on the house corpus plus those frames (a 4080,
about 15 minutes; volunteers' held-out loss 0.39) and shipped as songbird/synth/throat.npz.

The people's share is fixed: `throat.HUMAN_SHARE` 0.3 of the machine's default blend and of every
machine's own draw (`default_mix`, `machine_mix`), the other 0.7 the synthetic singers' as before.
Against the house voice on H, everyone's way: Whisper dry 8.9% -> 8.7% of words, in the mix 11.0% ->
10.5%, and the refrain's B4s 2.7 dB softer at 2 to 5 kHz. Measured inside the model (no recording read):
the shipped blend's vowel envelope sits 0.9 dB RMS from the all-synthetic blend and 2.7 dB from the
volunteers' singer alone, while each synthetic singer alone sits 1.8 to 2.8 dB from that blend; the
people's singer alone is 3.4 dB from it. The shipped voice is nearer the synthetic blend than any one
synthetic singer is, and the people's contribution is itself an average of eight. The training material
(cut lines, features, datasets, the desktop's copies) is deleted with the recordings by 2026-09-30.

## Sound, not sund (2026-09-30)

The artist: "sound" is heard "more like 'sund'". Measured on the dry voice (the learned throat's own
envelope, fictional:ada's singer, F1/F2 as peaks over the envelope's broad trend): AW before a nasal
coda held its first target, F1 800-900 Hz and F2 1700-1800, almost to the nasal, and closed toward
[ʊ] only in the nasal's own frames, where its murmur hides it. So the vowel heard ended on AH. In
"as the sound of a ring" (a 0.48 s vowel) F2 went 1820 -> 1450 and F1 stayed at 780 to the end, where
the throat's AH is 810/1450. Over pitches 62-69 and notes of 0.62 and 0.95 s, the last third of
"sound"'s vowel sat 3.6 dB RMS from the throat's own "sund" (S AH N D) and 8.3 dB from its open AW
(S AW). "round", "down" and "town" were less bad (5.7-6.7 dB from AH, 6.0-6.7 from the open AW). An
open AW ("now", "how") or one before a stop ("out", "loud") glides inside the vowel: "now it's by
you" ends at 480/910. It wasn't the first target (the throat's AW starts fronted, F2 about 1800, as
American AW before a nasal does), and it wasn't the timing: the vowel keeps 53-77% of its note,
and the nasal 0.09-0.14 s.

So `throat.told` tells the network that the last fifth of an AW before n, m or ng is UW
(`GLIDE_TAILS`). The throat sings UW before a nasal as [ʊ], F1 about 450 and F2 1150-1300; its UH
there is AH-like (F1 800) and didn't close the vowel. The schedule, the pitch and the loudness are
as before; only what the network hears changes. Measured the same way, "sound"'s vowel now ends
7.2 dB from "sund" and 4.8 dB from the open AW; "round", "down" and "town" end 4.5-5.7 dB from the
open AW. In the lines (F1/F2 at 10, 50, 70 and 90% of the vowel):

| Word, line | Before | After |
|---|---|---|
| "as the **sound** of a ring" | 780/1820, 780/1710, 780/1550, 780/1450 | 810/1760, 840/1500, 990/1190, 260/1310 |
| "they learned it as **sound**" | 880/1820, 910/1820, 910/1760, 880/1600 | 910/1820, 1020/1550, 1020/1745, 510/1320 |
| "from their mothers, and **sound**" | 740/1820, 810/1610, 770/1500, 560/1270 | 810/1760, 840/1400, 680/1190, 240/1310 |
| "sung in their **town**" | 780/1820, 840/1500, 590/1320, 600/1190 | 910/1700, 915/1270, 680/1180, 220/1310 |
| "handed on **down**" | 810/1820, 840/1600, 620/1270, 590/1230 | 910/1760, 880/1360, 650/1190, 250/1310 |

The vowel now closes a little further than an open AW does (F1 about 250 at its very end, against
480 in "now it's"), just before the nasal's own murmur at about the same F1. Whisper doesn't
separate the two: it heard every line the same before and after, "sound" included, because the
words around it lead it there. On the words cut out alone it heard "Sam" then "Sounds" for the
first "sound", "Sound" then "So" for the second, and "They're down" then "Their town" for "town".

Nothing else changes. H's seed sings AW only in "now", three times, so it is byte-identical
(golden/h-seed.sha256), as are b-refrain, h-words and every seed score. In a render that sings one
of these words, the lead differs at those words (1 to 13 dB under the voice there) and about 60 dB
under it elsewhere. The network's global variance and the voice's reference level are taken over
the whole song, so they move slightly. Before/after excerpts (fictional:ada, the same seed) are
renders/say/sound-{before,after}-{tongue,ring,town-down}.flac.

OW before a nasal ("own", "alone", "phone") may have the same fault: its vowel ends 4.6 dB from
the throat's AO ("fawn") and 7.2 dB from its open OW. The seed sings "own", "alone" and "owns", so
a fix would change the seed's audio. That's left for the artist to decide. AY and EY before a nasal
end as their open forms do (3.8 and 2.9 dB from them).

## Folk singers (2026-10-01, an experiment, not shipped)

The artist: "try training our voice model on real public domain folk songs", to learn how much better the
throat could get with more singers, not to publish the result. Real people's recordings, then, where the
recording itself is free: singers who released their own singing (LibriVox volunteers' sung hymns, carols and
ballads, public domain; Makemi's traditional songs and Michael O'Donnell's folk singing, CC BY-SA, usable here
only because nothing trained on them travels; VocalSet's "Row, Row, Row Your Boat" by 20 trained singers and
vocadito's public-domain songs, CC BY). Commercial records made before 1926, public domain by age, were allowed
too, but unaccompanied solo singing of that time is almost all male quartets: none were used. No field recordings.

- **Labelled without a score** (`tools/throat/folk.py`). Every recording is heard through Demucs and left out if
  accompanied (`separate`); Whisper large-v3 times its words (`transcribe`; run on a Colab A100, 154 recordings in
  4 minutes); `cut` corrects them against printed lyrics where there are some, cuts lines at pauses in the audio,
  aligns them with MFA and makes each syllable a note at the pitch actually sung. Lines that aren't sung (the
  LibriVox announcements), have a word no dictionary has or a word Whisper doubted are left out or masked. Run on
  the house corpus's own audio, it agrees with the scored labels on 93.5% of frames, 94% of phone starts within
  20 ms, 95% of pitches exact; with 64 kbps MP3 93.8%, with noise 28 dB down 93.3% (half the takes left out by
  the noise gate), with an RT60 of 0.7 s 85.4% (reverb isn't gated).
- **The corpus:** 147 minutes by 73 performers, each a singer of their own (source "folk", not "human": the
  volunteers' share stays theirs). 9 performers (15 minutes, men and women, studio and home) are held out of every run.
- **The runs** (Colab A100, about 4.5 minutes each against 40 on this Mac), all from model-house.npz with the
  volunteers' recipe (14,000 steps, lr 1e-3): **control**, the house corpus alone; **small**, 8 performers and 13.5
  minutes, the volunteers' size; **half**, 30 and 66; **all**, 64 and 132.

**How near each model gets to a real singer it never heard** (`tools/throat/unseen.py`: the best voice it can
make for each held-out singer, fitted on half their singing, envelope error on the other half, mean dB; also with
each stretch's own average spectrum taken out of both, the room's and the microphone's colouring):

| | Error | Without the room and microphone |
|---|---|---|
| control (no people) | 10.05 dB | 8.11 dB |
| the shipped model (8 volunteers, 13.7 min) | 9.57 | 7.73 |
| small (8 folk singers, 13.5 min) | 8.31 | 6.94 |
| half (30, 66 min) | 7.41 | 6.49 |
| all (64, 132 min) | **7.21** | **6.30** |

The house singers' own held-out segments stay at 5.0 dB in every model. Hearing real singers makes the throat
much better at a real voice it has never heard, about a fifth less error. Most of it came from the first eight
singers; after that, singers recorded a new way helped (VocalSet's improved only once VocalSet singers trained,
and they sang the same song) and more of the same kind hardly did.

**On H** it costs nothing, once the voice is blended as the studio blends it (`default_mix`, by register; dry, two
seeds; a Fable review re-rendered these): control 10.3% of words misheard, UTMOS 1.89; all 10.5%, 1.88. Blending
the house rows evenly instead (11.6-14.8% in the folk runs) was misleading: a new singer's row starts at the house
singers' mean and the folk rows hardly moved from it (64 rows spread 0.7 in the 8-number space, the house rows
2.7), so the house singers' mean *is* the folk voice there. For the same reason the volunteers' UTMOS 1.82 on H
was mostly the register blend, not their row: the control sung that way scores 1.89.

**It hasn't yet made our song sound better.** The 64 voices sit in one corner of the singer space, and their
envelopes are flatter than real ones (formant contrast 1.3 dB in the folk rows, 2.2 in the house rows, 3.3 in the
real singing); blending them in at 30% dilutes the voice (UTMOS 1.88 -> 1.67), and more sharpening doesn't help.
Next, in this order:
1. Keep the singers apart, and the singer apart from the recording: new rows started spread like the house rows,
   the singer table learned faster (lr 1e-2, no weight decay), 16 numbers a singer, and a table of recordings (one
   row per recording, one shared row for all the house audio) beside it in every layer, singing through the house
   row at synthesis (it folds into the FiLM biases, so throat.py needn't change).
2. A loss that keeps the folk rows' own contrast (L1 on the envelope less its 17-point trend).
3. A bigger network only if (1) spreads the singers and the held-out error stays above 6.5 dB.

The recordings, labels, datasets and models are in a session scratch directory, not kept; folk.py rebuilds them
from public sources.

### Round 2: the singers kept apart (2026-10-01)

The artist, on round 1: "fire and wire just sound like fi and wi". Two causes:
- **The labels.** folk.py read "fire" as the dictionary's fi-er, two syllables, so the folk corpus had no AYR at
  all (the program sings fire on one note, AYR). It now reads a diphthong's -er in one syllable with it.
- **The singing.** Most of it is non-rhotic (hymn and art-song diction, British and Irish singers): the third
  formant under a coda R sits at 2.66 kHz in it against 2.31 in the house corpus, and ER at 2.66 against 2.38. Trained
  on it as one voice, the network learns that an R after a vowel is nothing. With the labels fixed and round 1's
  recipe, H's "fire" and "wire" still dropped F3 only 120 Hz at their end (the control: 1,017).

Round 2 (`train.py --singer-dim 16 --spread --singer-lr 1e-2 --channel-dim 8`: 16 numbers a singer, new singers
started spread as the house singers are and learned ten times faster, a room for every recording beside the singer,
the house audio one "studio" room the model sings through) keeps the singers apart, so the folk singers' dropped
Rs stay theirs. On H, dry, two seeds, the studio's register blend, F3's fall at the end of fire and wire:

| | Words misheard | UTMOS | F3 drop in fire/wire |
|---|---|---|---|
| control, singers kept apart | 8.2% | 1.89 | 1,017 Hz |
| 64 folk singers, round 1's recipe (labels fixed) | 14.8% | 1.88 | 120 Hz |
| 64 folk singers kept apart | 10.5% | 1.91 | 954 Hz |
| the same, 30% folk in the blend | 10.5% | 1.92 | 917 Hz |
| kept apart, with the contrast loss (`--contrast 1.0`) | 8.7% | 1.90 | 992 Hz |
| the same, 30% folk in the blend | 9.8% | 1.91 | 981 Hz |

The artist: "that fixed fire+wire". Blending the folk singers in no longer dilutes the voice (round 1's folk blend:
UTMOS 1.67).

Unseen singers, the same test: control 10.35 dB (8.46 without the room), 8 singers 9.89 (8.06), 30: 8.63 (7.11),
64: 8.06 (6.76), with the contrast loss 8.31 (6.85); round 1's recipe on the same data 7.14 (6.26). The curve is the
same; the level is higher because a model that sings through the studio room can't make a real recording's room,
which round 1's model had learned into its voices. A fair test would fit a room for the unseen singer too: the
model written keeps only the room table, not the room's FiLM weights; keep those next time. The folk-trained
envelopes are still flatter than the control's (formant contrast 1.65-1.71 dB against 2.48; real singing 3.32).

The data for these runs went through Google Drive (the house dataset, 608 MB, and the folk one, 635 MB, merged on
the Colab machine), so the next runs need no upload.

### Round 3: against the average, and what's synthetic (2026-10-01, afternoon)

The folk-trained envelopes were still flat: formant contrast 1.5 dB on real singers the model never heard, 2.2 on the
house singers' own held-out takes, against 3.3-3.5 in real singing. Even a singer's own training audio came out
flatter once the network had learned them (1.6 against the 2.1 of rows it had never trained), so it was averaging over
the folk labels' noise as much as running out of size. Round 3 tried both cures (`train.py`):
- **A critic** (`--adversarial 0.1`): a small spectrally normalised 2-D convolution over frames and grid points of the
  envelope (to 5.6 kHz, which nearly every folk recording reaches) learns to tell real envelopes from the throat's,
  and the throat learns to fool it (least squares, and the critic's features matched). Only training changes.
- **A bigger throat** (`--channels 320`, 3.5M parameters against 0.93M), widened from the house model so it starts
  singing exactly as it did.
- The room's FiLM weights are now written beside the folded model, so the unseen-singer test fits a room as well as
  a singer (`tools/throat/fit_unseen.py`, by gradient, scored by `unseen.py --fitted`): round 2's test, which sang
  every unseen recording through the studio, was unfair to the models that keep rooms apart.

All from model-house.npz, 14,000 steps, round 2's recipe (`--singer-dim 16 --spread --singer-lr 1e-2 --channel-dim 8
--contrast 1.0`); H dry, two seeds, the studio's register blend:

| | Unseen singers (singer + room fitted) | Contrast, unseen (real 3.32) | H, house rows: WER | H, 30% folk: WER |
|---|---|---|---|---|
| control, round 2's recipe | 8.65 dB | 1.95 | 9.1% | |
| 64 folk singers, round 2's recipe | **7.00** | 1.47 | 9.1% | 7.3% |
| + critic | 7.01 | 2.11 | 8.2% | 8.2% |
| + critic at 0.3 | 7.10 | 2.16 | 10.3% | 7.3% |
| bigger | 7.17 | 1.68 | 8.2% | 6.8% |
| bigger + critic | 7.28 | 1.99 | **5.0%** | **5.7%** |
| control, bigger + critic | 9.88 | | 5.5% | |

With rooms fitted, keeping singers apart costs nothing on unseen singers (7.00, round 1's pooled recipe 7.14), and
the folk singers take a fifth to a quarter off the error. The critic raises contrast and flutter toward real
singing at no cost in fit (on the house singers' held-out takes 2.17 -> 2.82 dB contrast, flutter 1.07 -> 1.59 on
unseen singers, real 2.96); bigger + critic halves the words misheard on H, mostly by the recipe (the control has
it too). Fire and wire keep their R in every model (F3 drop 760-1,020 Hz). Two retrainings of one recipe differ by
1.5-2 points of WER.

The artist: 4 and 5 (bigger + critic) "are better but smaller differences than I expected at this point. Feels like
we're overfitting to something synthetic." A ladder on real singers the model never heard, from their recording to
the program's voice one step at a time (UTMOS):

| | Kalynda | Chris Tierney | VocalSet f2 |
|---|---|---|---|
| 0 the recording | 2.18 | 2.22 | 1.51 |
| 1 WORLD's own analysis and resynthesis | 1.75 | 1.72 | 1.38 |
| 2 its envelope on our grid, through our vocoder | 1.75 | 1.84 | 1.36 |
| 3 the model as that singer (singer and room fitted), their pitch and timing | 1.48 | 1.41 | 1.56 |
| 5 the house blend, their pitch and timing | 2.04 | 2.13 | 1.80 |

UTMOS scores the house voice as high as real singers or higher, and a real studio singer under our renders: it
prefers the synthetic voice, and the blends and recipes chosen by it were pulled that way. By ear (the artist, on
Kalynda): 2 "is not robotic" (some static in one word), 3 "is garbled but not quite robotic", 5 "is the most robotic
definitely". The robotic part is the house corpus, not the vocoder.

And the room: every model so far sings through the "studio" row, which the network learned from the house corpus's
SoulX renders. Bigger + critic on H with the folk singers' rows alone through the studio: WER 10.5%, "still really
robotic"; through VocalSet's real studio instead (the mean of its trained rooms' rows, folded into the FiLM biases
in the studio's place): WER 5.5%, and "so much better". From here voices are judged as the folk singers through a
real room, by WER and by ear; UTMOS is reported only as a number that favours the synthetic.

### The rest of VocalSet (2026-10-01)

VocalSet's 20 singers were in the corpus only through "Row, Row, Row Your Boat". The rest of it (CC BY 4.0), labelled by
`folk.py`: its two other songs, "Caro mio ben" and "Dona nobis pacem" (Italian and church Latin, read by their
spelling with pure vowels, Whisper large-v3 in their languages; 22 minutes, half of it unmasked, the aligner unsure of
Italian's clusters), and its vowel exercises (`folk.py exercises`: scales, arpeggios and long tones on a, i and u,
straight, vibrato, slow, belted and breathy, 3.1 hours; e and o left out, since English sings them as glides). One
room per VocalSet singer (the recording name's part before "~"). Through a real room, the folk rows alone, H's WER:

| round 2's recipe | WER |
|---|---|
| without VocalSet's rest (two seeds) | 8.2%, 8.0% |
| + the songs | 8.0% |
| + the songs, exercises 5% of every batch | 9.1% |
| + the songs, exercises 15% (two seeds) | 11.0%, 11.0% |

The songs cost nothing; the exercises cost intelligibility in proportion to their share (steady vowels with no
consonant either side, a context the program never sings). None of it moved the unseen-singer error (7.02 against
7.00; the four VocalSet singers held out 7.21 against 7.08): it adds hours, not people.

## New house singers from our own voice (2026-10-07 and 08)

The artist hears the house corpus as the robotic part of the voice (round 3 above). Its timbres came from our old
formant singer, so the throat learned SoulX's natural delivery in timbres that were never natural. This replaces
those timbres with ones made from the shipped voice itself, made more natural by a second open singing model.

**YingMusic-Singer** (ASLP-lab, CC BY 4.0; 727M parameters: an F5-TTS-style flow-matching DiT, SOME's melody encoder,
Stable Audio 2's VAE, whose license bars training a "foundational" model on its output; our 3.5M-parameter throat
isn't one) sings new words to the tune of a sung clip in the timbre of another. It runs beside the repo, never ships,
at about real time on this Mac (MPS; its own venv: `tools/throat/ying_batch.py` says how). What the artist heard, on
two of H's couplets:
- YingMusic with the same Eleven Music prompt as SoulX: SoulX better.
- YingMusic re-singing the shipped voice in its own timbre: better than the shipped voice. It keeps the tune
  (14-19 cents median from the clip) and the words (the throat's volunteers row alone, misheard on 9 of 17 words of
  "copy", is heard right after it).
- A real singer's clip as the timbre (VocalSet f2 and f7, CC BY 4.0): "too off-key" (31-41 cents). Staying in one
  voice is what keeps it on key, so people come in through the throat's own rows, not through recordings.
- SoulX prompted with YingMusic's version of our voice ("B"): "the best blend". The volunteers' share in the throat's
  mix at 30, 60 and 100%: all on key; SoulX prompted from one YingMusic pass ("d", "more natural") or two ("e",
  "a slight edge") were "definitely best". YingMusic's own timing drags at phrase ends ("ever knew it by heart"), so
  it only ever makes the ten-second prompt; SoulX sings the corpus to the score's timing.
- New singers from a single old house row each: "a step backward", old and new alike; from a blend of rows, as a
  machine's own voice is drawn: "better all around" in both registers. A bass re-sung twice "sounds less natural";
  once was best, with the volunteers at 57% or 30% close.

**The volunteers' share.** The consent (web/sing/consent.md) promises a voice trained on everyone's takes at once and
never set to sound like one person; HUMAN_SHARE's 0.3 was our choice, not the consent's. The artist, whose
volunteers are close family and friends: retraining is fine "as long as no result sounds like an individual", with
the share kept within 0.3-0.6. The people's row is itself an average of eight (the largest 26%), so at 0.6 no one
person is more than about 16% of any voice. Their recordings were deleted on September 30 and none is used here: the
new singers are renders of the shipped model's row.

**The recipe** (`tools/throat/ying.py`): ten new singers, one in each old house singer's register and keys. Each is
a random blend of the house rows that sing near that register (`throat.machine_mix`, at most 0.45 of any one) with
the volunteers' row at a share spread over 0.3-0.6 so high and low voices both get the whole range. The shipped
throat sings the guide's prompt window and the couplet after it in that voice; YingMusic re-sings each in the
other's timbre, once (the high voices alternate once and twice), three seeds a pass, keeping the one Whisper hears
best, then the one within 120 ms of the throat's timing (SoulX places a prompt's phones by the guide's timing alone;
Fable's review), then the one nearest its pitch; trimmed to the window. SoulX sings the old house plans (the same
126 + 93 items, keys, tempos and seeds) in the new prompts: `plan-blend.json`, `plan-blend-cover.json`, 143 minutes,
333 segments, 2 h 15 on this Mac; 328 kept by `check.py`.

Formant contrast of the corpus itself (dB about the envelope's 17-point trend, 200 Hz-5 kHz, voiced frames, every
segment against the old singer's render of it): old 3.40, new 3.18, the new higher in 22% of segments (the mezzo
and baritone higher, the tenors and bright lower). The artist preferred the new corpus by ear in both registers, so
this measure, like UTMOS, doesn't follow what is heard as natural here.

**Training** (the desktop's RTX 4080 Super, `train.py --init songbird/synth/throat.npz --steps 14000 --singer-dim 16
--spread --singer-lr 1e-2 --contrast 1.0 --adversarial 0.1`): A, the old house corpus with the new (`--retire
house-*`: their rows train and keep the consonants' coverage but no voice draws them), and B, the new corpus alone;
each at 320 channels (3.45M parameters, 16 minutes) and at the shipped 160. A model trained on these has no
volunteers row: the people's share is in every singer it draws, 0.3-0.6 by construction, and `HUMAN_SHARE` no
longer applies (`throat.humans` finds no people's row). `throat.drawn` and `train.py --retire` are new.

**Results** (models in renders/throat/blend-models/, not shipped; the artist chooses by ear: renders/ym-listen/
model-1..5 dry, full/song-1..5 the first published version in the mix):

| | WER on H, `wer_suite.py --sketch h --seeds 2` (438 words) | One core, 62 s of singing | Weights | Drawn singers alone vs the default blend (dB, median, range) |
|---|---|---|---|---|
| shipped | 9.1% | 2.17 s | 3.6 MB | 2.84, 1.8-5.7 |
| A-320 (old + new) | 8.0% | | 13.8 MB | 1.96, 0.8-4.8 |
| B-320 (new only) | 8.9% | 2.66 s | 13.8 MB | 2.23, 1.2-4.4 |
| A-160 (old + new) | 8.0% | | 3.7 MB | 1.91, 0.9-4.3 |
| B-160 (new only) | 8.7% | | 3.7 MB | 2.38, 0.8-4.2 |

- **Words** hold: every model is within a few words of the shipped voice on H.
- **Size** decides the bigger network more than speed does: a 320-channel model costs 23% more time on one core but
  13.2 MiB, against `songbird budget`'s 8 MiB goal for program and model together (6.63 MiB today, the model 3.40).
  At float16 it would still be about 9.9 MiB; only 8-bit weights would fit.
- **Variety narrows among the high voices.** Every new singer carries 0.3-0.6 of one shared row, so the high ones sit
  0.8-1.9 dB from the blend (the shipped house rows 1.8-4.0); the low ones keep their distance (3-5 dB). Machines
  singing in H's register would sound more alike than today's. If that matters, the high singers need more apart
  prompts (a higher cap than 0.45, or tract warps in the prompts), and a measure of it in the gate.
- The people's share now lives in the singers: no model here has a volunteers row (`throat.humans` is empty).

## Scylla's Band as a teacher (2026-11-06, overnight; an experiment, not shipped)

**Scylla's Band** (lowkeytea, Apache-2.0; a flow-matching speech and singing model with 14 fixed voices, run here on
its LiteRT CPU bundle beside the repo, never shipped; its training data isn't disclosed) has a singing graph that
takes IPA phones, a frame count for each (512 samples at 24 kHz) and a melody track directly. So it sings our own
schedule: `tools/throat/scylla.py` plans what the throat would sing (`voice.schedule` with `throat.DURATIONS`, the
same seed), turns its phones into Scylla's (diphthongs and affricates two symbols at fixed shares, a `<sil>` at each
word boundary), and writes the labels as what Scylla was told rather than what MFA heard. That takes MFA (not on
this Linux desktop) out of the corpus: the sibilants' energy lines up with the labels best at 0 ms. Scylla sang
better than our throat on the same notes, timing and seed (Gemini, below: +2.0 of 3 both on sounding human and on
words). Our throat sung on Scylla's own f0 was no better than on ours (-0.5), so the gap is the envelope, not the
pitch track: what training on it can teach.

**The corpus** (`scylla.py --per-item 2`, `scylla_batch.py` in Scylla's venv): 76 of `corpus.py`'s items, each sung
by two of the voices in a key moved into that voice's range (an octave shift into 3 below to 5 above its centre,
then ±2 semitones), H by all fourteen; 239 renditions, 423 segments, 70.6 min on 24 CPU threads (about 2x real
time). `check.py` kept 361: all but one or two of every voice's, except ink (0 of 31: sharp, 50 cents median) and
tuesday (7 of 31: 31 cents sharp); 151.5 minutes, 13 singers.

**Training**, the October A-160 recipe (`train.py --init songbird/synth/throat.npz --steps 14000 --channels 160
--singer-dim 16 --spread --singer-lr 1e-2 --contrast 1.0 --adversarial 0.1`, the 4080 Super, 14 min each;
`renders/throat-scylla/train-all.sh`): C, blend A (October's old and new house corpus, `--retire house-*`) with
Scylla's; D, blend B (the new corpus alone) with Scylla's; S, Scylla's alone. `tools/throat/retire.py` copies a
model drawing only some of its singers, the weights unchanged: Cbl and Dbl draw the blend singers alone (Scylla's
rows trained, never drawn), Csc and Dsc Scylla's alone. Held-out loss: C 0.253, D 0.249, S 0.242 (A-160 0.257).

**Gemini as a listener** (`tools/throat/gemini_judge.py`, gemini-3.8-flash): two renders of the same notes, timing
and seed, the dry voice stem cut into the same six 20-second windows of H's seed rendition (or a machine's own
blend, fictional:ada), loudness-matched, each pair asked in both orders; which sounds more like a person singing
and whose words are clearer, -3 to +3. It picks the same clip in both orders only 59% (human) and 65% (words) of
the time, so a score under about ±0.5 is noise. About $0.004 a call; this whole night $0.78.

**Results** (models in renders/throat-scylla/, listening in renders/throat-scylla/listen/compare/):

| | WER on H, `wer_suite.py --sketch h --seeds 6` (1314 words) | Gemini against shipped, human / words (seed; ada) | People's share of a voice |
|---|---|---|---|
| shipped | 10.3% | | 0.3 (`HUMAN_SHARE`) |
| A-160 | 7.7% | +0.75 / +0.50 (two windows) | 0.3-0.6 |
| C (blend A + Scylla) | **3.7%** | +0.17 / +0.67; +0.67 / +0.83 | about 0.1-0.35 |
| D (blend B + Scylla) | **3.7%** | +0.75 / +0.58; +1.08 / +0.92 | about 0.1-0.35 |
| S (Scylla alone) | 5.6% | **+1.58 / +1.42; +1.67 / +1.58** | none |
| Cbl (C, blend singers drawn) | 5.5% | +1.00 / +0.50; +0.33 / +0.33 | 0.3-0.6 |
| Dbl (D, blend singers drawn) | 7.3% | +0.75 / +0.67 | 0.3-0.6 |
| Csc, Dsc (Scylla's drawn) | 5.3%, 5.5% (two seeds) | | none |

Head to head (seed): C over A-160 +0.58 / +0.50; S over A-160 +0.75 / +1.17; S over C -0.25 / +0.25; S over D
-0.50 / 0.00; Cbl over C -0.25 / -0.17; Cbl over A-160 +0.33 / +0.17. What it hears: the shipped voice "buzzy",
"muffled", "metallic buzz on sustained vowels"; C and S "slight metallic grain on higher sustained vowels",
"mechanical stiffness" in the transitions.

- **Words improve most.** Every model trained with Scylla's singing hears better than the shipped voice and A-160:
  C and D mishear a third as many of H's words as the shipped voice does. Most of what's left is the lexicon's
  ("hundredodd", "quay" heard as "key", "a" as "the"), not the voice.
- **Sounding human:** the new models all beat the shipped voice; among themselves, within the judge's noise. S beats
  the shipped voice by the most, but not C or D head to head.
- **The volunteers' share decides between them.** The artist's 0.3-0.6 (a choice, not the consent's) puts the people
  in every voice. Scylla's singers carry none of it, so wherever a voice draws them the share falls: in
  C and D a machine's voice in H's register is 37-56% blend rows (median; `machine_mix` over 300 seeds, pitches
  55-65), so 0.1-0.35 people; S, Csc and Dsc have none. Only Cbl and Dbl keep the share, Scylla's singing still
  teaching the shared network: Cbl hears 5.5% (the shipped 10.3%) and Gemini prefers it to the shipped voice and
  to A-160, a little.
- **Not measured:** the variety among machines (October's spread from the default blend), the mix with the band
  (listen/ has the full mixes, unjudged), any song but H.
- Scylla's voices are fixed singers. No machine in C draws more than 0.41 of one (300 seeds; `machine_mix`'s cap 0.6, and
  more singers near each register); S and Csc would make every machine a blend of only Scylla's voices.
