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

No recording of any person was used.
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
2. **Spread (`Texture.spread` 0.15).** A fixed all-pass whose group delay wanders along frequency
   by 15% of each pulse's period (RMS), from 1.5 kHz, full above 3 kHz. It's the same for every
   pulse and every song (MELP's pulse dispersion, in effect). A pulse's upper harmonics now
   arrive spread through part of the period, still periodic. It's scaled to the period because
   a fixed delay smeared the altos and hardly touched the basses.
3. **Scatter (`Texture.scatter` 0.4).** A fresh random phase on every pulse (radians, smooth over
   300 Hz), rising in from harmonic 8 to 20. That's where harmonics stop being heard one by one,
   and it unlocks them from period to period.
4. **Sharpening (`sharpen`, `SHARPEN` 1.5, in `sing()` only).** A predicted envelope's peaks and
   valleys are pushed 1.5 times as far from its own trend (a Hann over 17 mel points), each
   frame's power kept: 1.9 dB of formant contrast becomes 2.6.

`throat.PLAIN` is WORLD's own synthesis, for comparison. `tools/throat/vocoder_eval.py
--variant NAME key=value` tries other settings.

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
- *Provenance:* every singer in the model's config has source "formant", and no ElevenLabs audio is
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
