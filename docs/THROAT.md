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
| Vocoder: our numpy WORLD against pyworld's, same features | equal level (±0.2 dB per frame); log-mel distance from the original 5.9 dB vs WORLD's 5.3 |
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
