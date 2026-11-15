# The learned throat

The artist's direction: "use as many vocal sources as we need to train our own smaller voice
synthesis engine that is optimized for our use case", and adopt SoulX-Singer directly only if that
fails. This is the learned throat of docs/history/VOICE-OPTIONS.md §4. Our program decides everything
about the delivery:
- when each phone starts and ends (`voice.schedule`);
- the pitch, with its glides, vibrato and phrasing gestures (`voice.pitch_track`);
- how hard each syllable is leaned on.

The throat only decides how those sounds sound. The artist's aim for it: "we don't need to *try* to
make it sound synthetic, i'm confident there will always be an uncanny valley." Fable reviews checked
the plan before training and each change to the vocoder; their numbers are below where they were used.

## How it works

- **The network.** `songbird/synth/throat.py` holds a small network: about 0.9M parameters, a
  dilated convolution stack over 5 ms frames.
  - **In:** the phone and two neighbours either side, its role (onset, vowel or coda), how far
    through the phone and how long it is, the syllable's stress, the note's level, log f0 and its
    slope, and a singer embedding.
  - **Out:** a spectral envelope (log power at 128 mel-spaced points to 11.8 kHz) and
    aperiodicity (32 points), as Morise's WORLD vocoder analyses a voice.
- **The vocoder.** Our own, in numpy, in the manner of WORLD: minimum-phase pitch pulses plus a
  period of shaped noise each (below, "Vocoder").
- **Everything ships.** The network runs in numpy too, so what ships is the weights
  (songbird/synth/throat.npz, 3.1 MB: each array's float32 bytes in planes, throat.save, which
  deflate packs better and reads back bit for bit) and code.
- **Our source.**
  - An envelope learned from a singer already contains that singer's glottal source.
    Exciting it with our Liljencrants-Fant pulses as well would double the tilt. Fable measured
    −12 dB at 2–4 kHz: a woolly voice.
  - So the voice's `rd` and `tilt` act relative to a reference source (rd 0.8, tilt 0.4). They
    change only the voiced part: pressed (rd 0.5) +2.6 dB at 4 kHz, breathy (1.6) −5.9 dB.
- **The machine's voice.** A point among the trained singers' embeddings, never one singer alone,
  plus `tract` as a frequency warp of the envelope. The delivery settings, the phrasing and the
  vibrato are what listeners mostly tell singers apart by, and they work the same with either
  engine.

## Where the sound comes from

The shipped model was trained in three steps.

1. **The house singers.** SoulX-Singer (Apache-2.0; a 2.8 GB zero-shot singing model trained on
   42,000 hours of undisclosed singers) sings our own scores in ten timbres. Each timbre's
   ten-second prompt is our own formant singer, sung with different VoiceParams (longer and shorter
   tracts, pressed and breathy sources, high and low registers; `SINGERS` in
   `tools/throat/corpus.py`). SoulX sings our scores naturally in each of those timbres, about 143
   minutes in all, and the throat learns from that. The first shipped throat (886,260 parameters,
   160 channels, 14,000 steps) was trained on this house corpus alone.
2. **Everyone's voice** (September 28). That model fine-tuned once on eight volunteers' takes
   together, as one singer (below).
3. **Scylla's Band as a second teacher** (November). The throat retrained on the house corpus with
   152 minutes of Scylla's Band, another open model, singing our schedule (below). This is the
   performance voice in songbird/synth/throat.npz: 886,372 parameters, 3.1 MB. It draws the ten
   house singers and the volunteers' singer at 0.3; Scylla's 13 singers trained it but are never
   drawn.

Every singer in the model's config records where its timbre came from (`sources`: "formant" for
the house singers, "human" for the volunteers, "scyllasband" for Scylla's). The teachers run beside
the repo and never ship.

**The corpus.** `tools/throat/corpus.py` plans it:
- every song in songs/;
- all 38 verses, 6 refrain couplets and 3 bridges of H's bank;
- lines written for the English sounds our songs lack.

Each item is sung by two of the ten singers (H by all of them), at a tempo within ±10%. Low
singers sing in their own register (an octave down), not transposed. On a first test of two items
per singer (`tools/throat/judge.py`, Whisper on each segment), 92–100% of notes were within 50
cents and 7–12% of words misheard.

- **Rendering.** `tools/throat/soulx_batch.py` renders at 24 kHz; SoulX runs at about real time.
- **Analysis.**
  - `tools/throat/features.py`: WORLD analysis. Harvest f0, searched within a fifth of the
    notes.
  - `tools/throat/phones.py`: phone boundaries from the Montreal Forced Aligner. Its dictionary is
    exactly the phones SoulX was asked to sing. High voices are aligned an octave down by our
    vocoder, envelope and timing kept.
  - `tools/throat/check.py` scores each segment; `tools/throat/dataset.py` builds the frames.
    Lines with a misplaced word are masked out.

## Checks

| | Result |
|---|---|
| Vocoder: our numpy WORLD against pyworld's, same features | equal level (±0.2 dB per frame); log-mel distance from the original 3.7 dB against WORLD's 4.0 on house singers |
| Features: 128/32-point mel grids against WORLD's full envelope | no measurable loss (5.30 vs 5.31 dB) |
| **Oracle**: SoulX's own envelopes, warped onto our schedule, at our pitch, through our vocoder (4 segments) | **11.8%** words misheard, against SoulX itself 10.5% and our formant singer 34.6% on the same notes |

The oracle was Fable's gate before training (`tools/throat/oracle.py`). It asks whether our
puppeteer, driving a perfect throat, still sounds right and is understood. It is, so the interface
holds. What remains is how close a small network gets to that throat.

## In the program

- **The default.** `VoiceParams.engine` is "learned". engine="formant" brings the formant singer
  back.
- **Tools that mean our formant singer ask for it by name:** the house singers' prompts, the
  reference singers, the phrasing extractor's template and the WORLD speech-to-song tool.
- **Without the weights,** the formant singer sings, with a warning.
- **Each machine has a singer.**
  - *The blend (`variation.choose_timbre`):* a machine's singer is a blend of the trained singers
    who sing near where it sings. It is drawn from the machine's identity (`throat.machine_mix`),
    pulled 0.6 of the way from the parent's blend as every trait is, and never more than 0.6 of any
    one singer (`throat.capped`). The people's share is set first (`throat.HUMAN_SHARE`, 0.3).
  - *The default blend (`throat.default_mix`):* the synthetic singers within a fifth of the pitch,
    the nearer the more, and the people's singer at 0.3.
  - *The lineage choir* sings through the throat whenever the lead does. Each earlier version the
    record remembers (up to six, the parent's first) sings in that version's voice. An ancestor that sang
    with the formant singer is heard as a throat singer drawn from its id.

## Vocoder

A WORLD-style vocoder is the classic source of a robotic buzz, so before changing ours we measured
what it loses against the voice it resynthesizes. `tools/throat/vocoder_eval.py` does it on copy
synthesis of 20 house-singer segments (two per singer, 12 s each, WORLD features through
`synthesize`, against SoulX's original), with the same measures on every signal:
- how alike consecutive periods are per band, once aligned (periodicity, as an HNR);
- how steady each harmonic's phase stays from one period to the next (coherence);
- how much of a band's energy falls in the loudest quarter of each period, and how peaky the
  band is (excess kurtosis);
- levels per band, a log-mel distance, UTMOS and DNSMOS.

### What plain WORLD synthesis loses

- **A click every period.** WORLD's pulses are minimum phase, so each pulse's upper harmonics
  arrive together. The teacher's 4–8 kHz energy is spread through the period: 46% of it in the
  loudest quarter of each period against plain synthesis's 61%. Its excess kurtosis at 5–8 kHz is
  1.4 against 3.1.
- **Upper harmonics locked from period to period.** Above 4 kHz plain synthesis is 1.3–1.7 dB more
  periodic than the teacher and each harmonic's phase step steadier (coherence .60 against .56 at
  4–6 kHz).
- **Too periodic below 4 kHz as well** (2.5–4 dB): what cycle-to-cycle jitter would fix, but see
  below.
- **Flattened formants in the learned engine.** A network's envelope is an average. On held-out
  segments the house model's envelope rises and falls 1.9 dB around its own trend (RMS, 200 Hz–5
  kHz); the natural envelope does 3.3 dB (3.1 averaged over 25 ms, all a 5 ms network can be asked
  for). The predicted aperiodicity is right: within 0.3 dB of D4C's in every band.
- **Not lost:**
  - The aperiodicity's resolution. D4C estimates aperiodicity at knots 3 kHz apart, so the 32
    mel points are already finer than their source.
  - The timing of the noise. The teacher's high band is *less* bursty than ours, so
    pitch-synchronous noise shaping would go the wrong way.
  - Onsets and offsets: the same steps in level at voicing boundaries.
  - Levels above 4 kHz: within 0.6 dB.
- **Left alone.** Below 4 kHz every resynthesis, pyworld's included, is 1.2–2.1 dB louder than
  the teacher, the most at 0–1 kHz. It's WORLD's own analysis bias, and it grows with pitch: on a
  synthetic voice Fable measured +0.3 dB at 0–1 kHz at 150 Hz and +2 dB at 350 Hz. A fixed
  correction would be wrong for every voice but the average.

### What the vocoder does

All of it is in `songbird/synth/throat.py`; a seed gives one voice.

1. **The DC remover is centred on each pulse,** as WORLD's is.
2. **Spread (`Texture.spread` 0.25).** A fixed all-pass whose group delay wanders along frequency
   by that fraction of each pulse's period (RMS), from 1.5 kHz, full above 3 kHz. It's the same for
   every pulse and every song (MELP's pulse dispersion, in effect). A pulse's upper harmonics
   arrive spread through part of the period, still periodic. It's scaled to the period because a
   fixed delay smeared the altos and hardly touched the basses.
3. **Scatter (`Texture.scatter` 0.5).** A fresh random phase on every pulse (radians, smooth over
   300 Hz), rising in from harmonic 8 to 20. That's where harmonics stop being heard one by one,
   and it unlocks them from period to period.
4. **Sharpening (`sharpen`, `SHARPEN` 1.5, in `sing()` only).** A predicted envelope's peaks and
   valleys are pushed 1.5 times as far from its own trend (a Hann over 17 mel points), each
   frame's power kept: 1.9 dB of formant contrast becomes 2.6.

Spread 0.25 with scatter 0.5 lands steady vowels' 4–8 kHz on the teacher's (0.3 and 0.6
overshoot: kurtosis 0.8). It matters most in a low voice, where the pulse rate falls into the
roughness band. `throat.PLAIN` is WORLD's own synthesis, for comparison.
`tools/throat/vocoder_eval.py --variant NAME key=value` tries other settings.

### The numbers

Copy synthesis, 20 house-singer segments (the teacher, plain WORLD synthesis, and the vocoder with
spread 0.15 and scatter 0.4, the first settings):

| | Teacher | Plain | Spread and scatter |
|---|---|---|---|
| 4–8 kHz energy in the loudest quarter of each period | .46 | .61 | .52 |
| above 8 kHz | .41 | .53 | .45 |
| excess kurtosis 3–5 kHz / 5–8 kHz | 0.8 / 1.4 | 1.5 / 3.1 | 1.1 / 1.2 |
| periodicity 4–6 kHz (dB) | 1.0 | 2.5 | 1.7 |
| coherence 4–6 / 6–8 / 8+ kHz | .556 / .474 / .400 | .603 / .519 / .441 | .585 / .499 / .425 |
| UTMOS | 2.08 | 1.92 | 1.98 |
| DNSMOS SIG / OVRL | 3.21 / 2.94 | 3.19 / 2.90 | 3.18 / 2.89 |

- The UTMOS gain is almost all the spread: +0.065 ± 0.016 paired, better on 18 of 20 segments.
  The scatter adds +0.003.
- DNSMOS is flat within its noise. DNSMOS SIG is a speech enhancer's distortion score, so it may
  count added phase irregularity as distortion.

The house model singing H's refrain and seed verses (122 s, dry, seed 1):

| | UTMOS | Words misheard | 4–8 kHz in the loudest quarter | kurtosis 5–8 kHz |
|---|---|---|---|---|
| plain vocoder | 1.72 | 14.2% | .79 | 4.0 |
| + spread and scatter | 1.80 | 14.2% | .69 | 2.3 |
| + sharpening 1.5 | 1.89 | 12.8% | .65 | 2.1 |

The learned engine is buzzier than copy synthesis: .79 of its high band falls in the loudest
quarter of each period, where the teacher has .46. The vocoder closes about 40% of that gap. What
remains is the model's smooth envelope, without the frame-to-frame flutter of a real one (2.7 dB
per frame against 4.1).

### Tried and left out

- **Cycle-to-cycle jitter** (`Texture.jitter`, kept at 0). At 0.4–0.5% of the period it brought
  the lower bands' periodicity toward the teacher's and UTMOS up in the learned render (+0.014).
  But it cost DNSMOS (SIG −0.013 in copy synthesis) and did nothing for UTMOS in copy synthesis.
  voice.pitch_track already has a slow 0.3% wobble.
- **Per-pulse level flutter** (1–2 dB, above 1 kHz), standing in for a real envelope's
  frame-to-frame flutter. UTMOS fell, and DNSMOS with it.
- **A fixed spectral tilt** fitted to the mean 0–1 kHz excess. It moved the levels onto the
  teacher's but UTMOS didn't follow, and the bias depends on pitch (above).
- **Interpolating the grid in power instead of log power.** It recovers 0.3 dB above 6 kHz but
  cost UTMOS (−0.019 ± 0.004), and it would change the space the model is trained in.
- **Pitch-synchronous noise shaping.** It goes the wrong way (above).
- **A neural vocoder.** Not tried. A vocoder trained on spectral losses alone (DDSP, NSF, a Vocos
  generator without its discriminator) can't learn the phase texture that is the buzz, and a GAN
  would meet the same gap between natural and predicted features that makes the learned engine
  buzzier than copy synthesis. The design with a head start is a small network refining this
  vocoder's STFT, adversarially trained, fine-tuned on the model's own predictions. It should ship
  only if, from predicted features, it beats this vocoder by ear and on these measures.

Every measure here compares against SoulX, a neural vocoder's texture, not a human's. Its high band
is smoother than a person's voice probably is, so the settings stop short of it.

## The consonants, sharpened

The artist heard word ends lost: "saved" heard "seh", "part" too close to "par", "old" without its
d, "lit" and "light" without enough t, "laughed" trying to say a g and missing its -ed, "song" not
enunciating its ng. Measured on the dry lead, coda t, k and p had no release at all above 3 kHz,
coda d was no different from the m or l before it, and coda f was a low rumble (the "g").

The teacher's word-final consonants are soft (singers let them go) and the network's are softer, at
5 ms a frame with a median coda t of 50 ms. What tells a listener a stop is its closure and its
release, and a weak fricative its hiss, and those are what the formant singer makes by rule. So
`throat.articulate` lays them over the throat's own:
- through each stop's closure the throat's output is dipped (to 20% for a voiceless stop, 50% for
  a voiced one, whose voice bar stays);
- then the formant singer's burst (`phonetics.BURSTS`, by place, 3 dB under its levels, each burst
  a level and length within 1.5 dB and 15% so no two are alike; a velar's following the
  vowel's F2) and, after a voiceless one, its aspiration fading to the stop's end;
- f, th, v and dh get the formant singer's frication 4 to 6 dB over its levels, the voiceless ones
  with the throat's rumble dipped to half under it;
- a coda nasal comes up 2 dB.

s, sh, z and zh are left to the throat, which sings them well. The teacher's own consonant stays
audible under the rule-made one, as the artist asked ("soften or blend them slightly with measured
pronunciations"). `VoiceParams.crisp` scales all of it: 0.6 by default, with the mix's transient
softener, chosen by ear (1 reads as clipping; 0 is the throat alone, which loses the ends of words).
On the house model, crisp 1 took H's words misheard from 14.2% to 7.3% dry and from 13.2% to 9.1% in
the mix. The t's own release and the physical stops are below, "The t's" and "Physical stops, after
Chimera".

**The choir's floor.** Below about 160 Hz the vocoder's pulses are heard one by one, like tapping a
microphone (35 thumps a second at E2, 10 at D3, 2 at E3, none from A3 up, counted as 5 ms frames
jumping 12 dB over their surroundings). So the choir keeps to E3 and above (`theory.FLOOR`); the
bass instrument has the register below.

## The top notes' harshness

The artist heard "a kind of harshness" in the refrain, the first o of "nobody" (B4, the tune's top)
the clearest case. Against SoulX-Singer singing the same syllable at the same pitch, the dry voice
sat 4.5 dB hotter at 2 to 5 kHz and 5.6 dB at 3 to 4 kHz; the same "no" an octave lower did not.
Sharpening and the level fed to the network changed nothing measurable; a darker source did:
`VoiceParams.rd` 0.9 and `tilt` 0.7 (from 0.7 and 0.4) take 2 to 3 dB off each band, and the lead's
presence peak at 0.5 dB the rest, landing the mixed "no" level with the reference at 2 to 5 kHz.
Whisper reads the darker voice the same.

## Breath at the top

A spectrogram of one phrase at every stage of the mix showed the chain changing the voice hardly at
all, and the dry voice's harmonics standing as clean lines to 10 kHz with nothing between them: the
buzz the artist heard as "robotic". The natural reference is half noise up there (aperiodicity 0.32
to 0.65 from 2 to 8 kHz against the throat's 0.18 to 0.48). So `VoiceParams.air` floors the learned
throat's aperiodicity, rising from 0 at 2.5 kHz to `air` at 8 kHz and above (`throat.air_floor`);
0.4 by default, chosen by ear ("a bit better, not perfect").

## Everyone's voice

The consent lets the recordings train the voice once, after singing closed, blended from everyone and
never set to sound like one person. `tools/archive/volunteers-2026/volunteers.py` and `clean_takes.py`
cut the 79 takes into sung lines by their guides' scores, cancelled the melody guide where it leaked
from a speaker, gated the room, and kept what the check passed: 13.7 minutes by eight singers (six
credited by name in CREDITS.md, two without credit), none more than 26% of it. All of them are one
singer to the network, "volunteers", source "human": there is no per-person embedding to find. The
house model was fine-tuned 14,000 steps on the house corpus plus those frames (volunteers' held-out
loss 0.39).

The people's share is fixed: `throat.HUMAN_SHARE` 0.3 of the default blend and of every machine's
own draw (`default_mix`, `machine_mix`), the other 0.7 the synthetic singers'. The artist allows
0.3–0.6; 0.3 is our choice, not the consent's. Against the house voice on H: Whisper dry 8.9% ->
8.7% of words, in the mix 11.0% -> 10.5%, and the refrain's B4s 2.7 dB softer at 2 to 5 kHz. Inside
that model, the shipped blend's vowel envelope sat 0.9 dB RMS from the all-synthetic blend and 2.7 dB
from the volunteers' singer alone, while each synthetic singer alone sat 1.8 to 2.8 dB from that
blend. The voice is nearer the synthetic blend than any one synthetic singer is, and the people's
contribution is itself an average of eight. The recordings and everything made from them (cut lines,
features, datasets) were deleted on September 30.

## Sound, not sund

The artist heard "sound" "more like 'sund'". On the dry voice, AW before a nasal coda held its first
target, F1 800–900 Hz and F2 1700–1800, almost to the nasal, and closed toward [ʊ] only in the nasal's
own frames, where its murmur hides it. So the vowel heard ended on AH: over pitches 62–69 and notes
of 0.62 and 0.95 s, the last third of "sound"'s vowel sat 3.6 dB RMS from the throat's own "sund"
(S AH N D) and 8.3 dB from its open AW. An open AW ("now", "how") or one before a stop ("out",
"loud") glides inside the vowel. It isn't the first target (the throat's AW starts fronted, as
American AW before a nasal does), nor the timing.

So `throat.told` tells the network that the last fifth of an AW before n, m or ng is UW
(`GLIDE_TAILS`). The throat sings UW before a nasal as [ʊ], F1 about 450 and F2 1150–1300; its UH
there is AH-like (F1 800) and doesn't close the vowel. The schedule, the pitch and the loudness are
unchanged; only what the network hears changes. "sound"'s vowel ends 7.2 dB from "sund" and 4.8 dB
from the open AW. In the lines (F1/F2 at 10, 50, 70 and 90% of the vowel):

| Word, line | Without the tail | With it |
|---|---|---|
| "as the **sound** of a ring" | 780/1820, 780/1710, 780/1550, 780/1450 | 810/1760, 840/1500, 990/1190, 260/1310 |
| "they learned it as **sound**" | 880/1820, 910/1820, 910/1760, 880/1600 | 910/1820, 1020/1550, 1020/1745, 510/1320 |
| "from their mothers, and **sound**" | 740/1820, 810/1610, 770/1500, 560/1270 | 810/1760, 840/1400, 680/1190, 240/1310 |
| "sung in their **town**" | 780/1820, 840/1500, 590/1320, 600/1190 | 910/1700, 915/1270, 680/1180, 220/1310 |
| "handed on **down**" | 810/1820, 840/1600, 620/1270, 590/1230 | 910/1760, 880/1360, 650/1190, 250/1310 |

The vowel closes a little further than an open AW does (F1 about 250 at its very end, against 480 in
"now it's"), just before the nasal's own murmur at about the same F1. Whisper doesn't separate the
two in the lines, because the words around it lead it there.

OW before a nasal ("own", "alone", "phone") may have the same fault: its vowel ends 4.6 dB from the
throat's AO ("fawn") and 7.2 dB from its open OW. The seed sings "own", "alone" and "owns", so a fix
would change the seed's audio; that's the artist's call. AY and EY before a nasal end as their open
forms do (3.8 and 2.9 dB from them).

## Folk singers

An experiment, not shipped. The artist asked to "try training our voice model on real public domain
folk songs", to learn how much better the throat could get with more singers, not to publish the
result. The recordings were ones whose singers released them freely: LibriVox volunteers' sung hymns,
carols and ballads (public domain); Makemi's traditional songs and Michael O'Donnell's folk singing
(CC BY-SA, usable only because nothing trained on them travels); VocalSet's 20 trained singers and
vocadito's songs (CC BY). No field recordings.

- **Labelled without a score** (`tools/throat/folk.py`). Every recording is heard through Demucs and
  left out if accompanied (`separate`); Whisper large-v3 times its words (`transcribe`); `cut`
  corrects them against printed lyrics where there are some, cuts lines at pauses, aligns them with
  MFA and makes each syllable a note at the pitch actually sung. Run on the house corpus's own audio,
  it agrees with the scored labels on 93.5% of frames.
- **The corpus:** 147 minutes by 73 performers, each a singer of their own (source "folk"). 9
  performers are held out of every run.
- **The test** (`tools/throat/unseen.py`, with `fit_unseen.py` fitting a singer and a room by
  gradient): the best voice a model can make for each held-out singer, fitted on half their singing,
  envelope error on the other half.

Hearing real singers makes the throat much better at a real voice it has never heard: about a fifth
less error (10.05 dB with no people, 9.57 with the volunteers, 7.21 with all 64 folk singers). Most
of it comes from the first eight singers; after that, singers recorded a new way help and more of
the same kind hardly does. It didn't make our song sound better: blended in as one pool, the folk
singers flattened the voice and dropped its Rs.

### Round 2: the singers kept apart

The artist: "fire and wire just sound like fi and wi". Two causes. folk.py read "fire" as two
syllables (it reads a diphthong's -er in one syllable with it); and most of the folk singing is
non-rhotic, so a network trained on it as one voice learns that an R after a vowel is nothing.
`train.py --singer-dim 16 --spread --singer-lr 1e-2 --channel-dim 8` keeps the singers apart (16
numbers a singer, new singers started spread as the house singers are and learned ten times faster,
a room for every recording beside the singer), so the folk singers' dropped Rs stay theirs: F3's fall
at the end of H's "fire" and "wire" is 954 Hz against 120 pooled (the control 1,017). The artist:
"that fixed fire+wire". `--contrast 1.0` adds a loss that keeps the envelope's formant contrast.

### Round 3: against the average, and what's synthetic

The folk-trained envelopes were still flat (formant contrast 1.5 dB on unseen singers, against 3.3–3.5
in real singing). Round 3 tried a critic (`train.py --adversarial 0.1`: a small spectrally normalised
2-D convolution learns to tell real envelopes from the throat's, and the throat learns to fool it;
only training changes) and a bigger throat (`--channels 320`). The critic raises contrast and
flutter toward real singing at no cost in fit; bigger with the critic halves the words misheard on H,
mostly by the recipe (the control has it too).

The artist heard those as "better but smaller differences than I expected at this point. Feels like
we're overfitting to something synthetic." A ladder on real singers the model never heard, from their
recording to the program's voice one step at a time, showed why: UTMOS scores the house voice as high
as real singers or higher. It prefers the synthetic voice, so choices made by it were pulled that way.
By ear (the artist, on one singer): WORLD's resynthesis "is not robotic", the model fitted to that
singer "is garbled but not quite robotic", the house blend "is the most robotic definitely". The
robotic part is the house corpus, not the vocoder. Voices since are judged by WER and by ear, with
UTMOS reported only as a number that favours the synthetic.

VocalSet's other songs ("Caro mio ben", "Dona nobis pacem") cost nothing; its vowel exercises
(`folk.py exercises`) cost intelligibility in proportion to their share, a context the program never
sings. Neither moved the unseen-singer error: they add hours, not people.

The recordings, labels, datasets and models are not kept; folk.py rebuilds them from public sources.

## New house singers from our own voice

An experiment, not shipped. The house corpus's timbres came from our formant singer, so the throat
learned SoulX's natural delivery in timbres that were never natural. This tried new timbres made from
the shipped voice itself by a second open singing model.

**YingMusic-Singer** (ASLP-lab, CC BY 4.0; 727M parameters, an F5-TTS-style flow-matching DiT with
Stable Audio 2's VAE, whose license bars training a "foundational" model on its output; our small
throat isn't one) sings new words to the tune of a sung clip in the timbre of another. It runs beside
the repo and never ships (`tools/throat/ying_batch.py` says how). The artist heard YingMusic
re-singing the shipped voice as better than the shipped voice, and SoulX prompted with that as "the
best blend". A real singer's clip as the timbre was "too off-key", so people come in through the
throat's own rows, not through recordings.

**The recipe** (`tools/throat/ying.py`): ten new singers, one in each house singer's register. Each
is a random blend of the house rows near that register with the volunteers' row at a share spread
over 0.3–0.6 (the artist: fine "as long as no result sounds like an individual"; the people's row is
itself an average of eight, so at 0.6 no one person is more than about 16% of any voice). The shipped
throat sings the prompt in that voice and YingMusic re-sings it; SoulX then sings the house plans in
the new prompts (143 minutes). The volunteers' recordings were not used: the new singers are renders
of the shipped model's row.

**Training** (`train.py --init songbird/synth/throat.npz --steps 14000 --singer-dim 16 --spread
--singer-lr 1e-2 --contrast 1.0 --adversarial 0.1`): A, the old house corpus with the new
(`--retire house-*`: their rows train and keep the consonants' coverage, but no voice draws them;
`throat.drawn`), and B, the new corpus alone, each at 320 and 160 channels. All held H's words
(8.0–8.9% against the shipped 9.1%). A 320-channel model is 13.8 MB, over `songbird budget`'s 8 MiB
for program and model together. Every new singer carries 0.3–0.6 of one shared row, so the high voices
sit closer together than the house singers do. A-160 is the base of the next experiments.

## Scylla's Band as a teacher

**Scylla's Band** (lowkeytea, Apache-2.0; a flow-matching speech and singing model with 14 fixed
voices, run on its LiteRT CPU bundle beside the repo and never shipped; its training data isn't
disclosed) has a singing graph that takes IPA phones, a frame count for each (512 samples at 24 kHz)
and a melody track directly. So it sings our own schedule: `tools/throat/scylla.py` plans what the
throat would sing (`voice.schedule` with `throat.DURATIONS`, the same seed), turns its phones into
Scylla's (diphthongs and affricates two symbols at fixed shares, a `<sil>` at each word boundary), and
writes the labels as what Scylla was told rather than what MFA heard. Scylla sang better than our
throat on the same notes, timing and seed (Gemini, below: +2.0 of 3 both on sounding human and on
words). Our throat sung on Scylla's own f0 was no better than on ours, so the gap is the envelope,
which training on it can teach.

**The corpus** (`scylla.py --per-item 2`, `scylla_batch.py` in Scylla's venv): 76 of `corpus.py`'s
items, each sung by two of the voices in a key moved into that voice's range, H by all fourteen; 423
segments on 24 CPU threads (about 2x real time). `check.py` kept 361, 151.5 minutes by 13 singers
(ink, 50 cents sharp, kept none).

**Gemini as a listener** (`tools/throat/gemini_judge.py`): two renders of the same notes, timing and
seed, the dry voice stem cut into the same six 20-second windows of H, loudness-matched, each pair
asked in both orders which sounds more like a person singing and whose words are clearer, −3 to +3.
It picks the same clip in both orders only 59% (human) and 65% (words) of the time, so a score under
about ±0.5 is noise.

**Training**, the A-160 recipe (`train.py --init songbird/synth/throat.npz --steps 14000 --channels
160 --singer-dim 16 --spread --singer-lr 1e-2 --contrast 1.0 --adversarial 0.1`; 14 minutes on an
RTX 4080 Super). `tools/throat/retire.py` copies a model drawing only some of its singers, the weights
unchanged. `tools/throat/subset.py` cuts the shipped voice's house corpus out of a dataset, and
`folk.py merge` adds Scylla's to it, keeping the shipped model's `volunteers` row by name. The models
tried (WER from `tools/wer_suite.py`, H 1314 words, every song 5002):

| | Corpus | Draws | WER on H | Every song |
|---|---|---|---|---|
| Everyone's voice | house + volunteers | house, volunteers 0.3 | 10.3% | 15.2% |
| A-160 | October's house and blend corpora | blend singers | 7.7% | 11.4% |
| C | A's with Scylla's | blend and Scylla's singers | 3.7% | 8.7% |
| S | Scylla's alone | Scylla's | 5.6% | 10.6% |
| Cbl | C | blend singers | 5.5% | 9.8% |
| E16bl | the house corpus with Scylla's, 16 numbers a singer | house, volunteers 0.3 | 5.5% | 7.9% |
| **E8bl (shipped)** | the same, 8 numbers a singer | house, volunteers 0.3 | 5.5% | 9.1% |

- **Words improve most.** Every model trained with Scylla's singing hears better than the September
  voice. Most of what's left is the lexicon's ("hundredodd", "quay" heard as "key"), not the voice.
  The corpora sing these songs' own words, so the every-song figure is partly in-domain.
- **Sounding human:** Gemini prefers every new model to the September voice (E16bl +0.67 / +0.33)
  and can't tell the new ones apart. In the mix it can't tell any of them apart; the gain is heard
  dry, and in the words. What it hears in the September voice: "buzzy", "muffled", "metallic buzz on
  sustained vowels".
- **The volunteers' share decides between them.** Scylla's singers carry none of it, so wherever a
  voice draws them the share falls (in C, to about 0.1–0.35). E8bl and E16bl draw what the September
  voice drew, the ten house singers and the volunteers at 0.3, with Scylla's singing teaching the
  shared network: the smallest change to what ships. The artist chose E8bl, with the t below, as the
  performance voice.
- **The volunteers' row moves.** With no frames in the new dataset, the row sings 6.49 dB
  from what the September model's row sang (the house rows 2.4–2.6 dB; the throat's predicted
  envelope on H's first item, voiced frames, mean |dB|). In the shipped voice the people's 0.3 is the
  September row read by a new network: still never one person, but not quite how the volunteers'
  takes sounded. Holding it would take frames for it: the September model singing as the
  volunteers alone, added to the corpus.

### The t's

The artist heard the t's as harsh; turning their bursts down "just sorta turns down the volume". Each
band's level over the t and 30 ms after, against that band in the segment's vowels, put the excess
at 2–5 kHz, and it is `articulate`'s burst, not the network. Fable's review: the alveolar burst
(phonetics.BURSTS, at the default tract centred 4.7 kHz) through second-order band-passes is only 4 dB
down at 3 kHz and mostly cancels at 6.5 kHz, so the stock t is one 4–5 kHz peak; the lead's de-esser
(`fx.deess`, split 4.5 kHz) turns down what's above 4.5 kHz on every burst and leaves the 2.7–4.5 kHz
part; and the burst is a flat 12 ms block where a release falls away from its first instant.

`throat.T_RELEASE` sets a t's noise shape, level, rise, length, decay, aspiration and how much of the
throat's own t is left after the release. Scylla's line-end t's are a release 11–17 dB under the
vowel, mostly above 4.5 kHz with 2–4.5 kHz about 13 dB under that, falling away over 15–40 ms.
`throat.T_CHOSEN` (tE, the artist's pick: "tE sounds best") gives that, and is the default: 6–10 kHz
with 3–4 kHz 12 dB under, a 0.5 ms rise falling away over 10 ms, about 30 ms long, +8 dB. After the
lead chain, "part" sits 17 dB under the word and "heart" 13. `T_RELEASE.update(T_AS_WAS)` sings the
plain t.

The contest version in B major, for the singers' ranges, is in performance/ (performance/README.md).

## Physical stops, after Chimera

[Chimera](https://github.com/jamesondh/chimera-vocal-synth) (MIT) is a physical airway model, not a
neural voice: an FDTD tract, a glottis and articulators in a 2D head. On H's lead in B Whisper loses
30.6% of the words, against E8bl's 8.3%, so it is no teacher; its stops are quiet clicks. What it
taught is how a stop is made: pressure behind the closure lets go in a spike, the opening is briefly
too wide to hiss, and then breath through the folds, coloured by the tract it passes (the vowel the
mouth is moving to).

`tools/throat/stop_release.py` measures each release from the audio (the quietest 10 ms near the
label, then the sharpest rise of 2–9 kHz after it) as three bands' envelopes (1.5–2.7, 2.7–4.5,
4.5–9 kHz) re the vowel level, over Scylla's labelled H items and ours on the same notes. Scylla's
3,400 stops: a broadband spike, ~10 dB down 5 ms later in 1.5–4.5 kHz, then an even breath ~27 dB
under the vowel for 30–40 ms in a coda, and a t's onset hiss above 4.5 kHz ~10 dB under it until the
vowel.

`throat.STOP_RELEASE` makes a release that way for each phone (spike, gap, a breath coloured by the
vowel's formants with the place's own regions; an affricate's hiss instead of the breath; a voiced
stop's folds voicing on), and `throat.STOP_PHYSICAL` holds the settings tuned to Scylla's. They are
not the default. The artist heard them as the harshness left in the voice, "too much like an audio
artifact rather than primitive speech synthesis" (the performance voice's first verse, sung by the
machine alone, with each part of the consonants turned off in turn: only these releases changed it).
So `STOP_AS_WAS` (every release as articulate makes it, tE's t included) is the default, and
`throat.STOP_RELEASE.update(throat.STOP_PHYSICAL)` sings the physical ones. Mean |difference| from
Scylla's envelopes over the first 40 ms, dry, at the default tract:

| | t onset | t coda | k onset | k coda | p onset | p coda | ch onset | b onset | d onset | d coda | g onset |
|---|---|---|---|---|---|---|---|---|---|---|---|
| as articulate makes them (tE) | 7.9 | 9.3 | 4.4 | 8.7 | 9.3 | 10.0 | 5.4 | 11.9 | 9.7 | 13.2 | 5.7 |
| physical | 2.8 | 3.8 | 3.3 | 4.9 | 6.0 | 5.8 | 4.7 | 10.8 | 6.0 | 9.7 | 4.0 |

Two things found on the way. The throat starts a ch hiss ~25 ms before `voice._stop_times`'s
release, so a ch's release is lost in a hiss already rising; a release's `closure` holds the closure
shut as given, because `voice.crisp` scales every other dip. And after b and d our vowels are 10–15 dB
duller at 1.5–4.5 kHz than Scylla's for 60 ms: that is the throat's own voiced onset, which no
release noise can give; a fine-tune that weights those transitions is the way to it.
