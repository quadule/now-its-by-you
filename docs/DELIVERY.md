# How the singer delivers a song

The voice stays synthetic. What should sound like a person is the delivery: how it gets from one
note to the next, how a held note moves, how loud each syllable is, when and how it breathes. Two
passes so far: the first (2026-09-25, below) against Milo's takes and the Eleven Music singers; the
second (2026-09-26, next) against a natural singer singing our own scores, note for note.

## Secondary stress stays stressed (2026-09-27)

Tried and not adopted: singing only a primary stress (1) as stressed, so a syllable the dictionary
marks 2 (the -one of everyone, the second half of a compound) keeps its full vowel but isn't leaned
on or told to the throat as stressed. English says many of those lightly, and the reviews had heard
"ev-ery-ONE". Dry, on H's refrain and five seed verses over three seeds, words misheard went from
12.9% to 14.3% (85 to 94 of 657), and not on those words: the throat was taught with 2 as stressed,
and telling it otherwise moved its singing everywhere. The rule stays; a word the dictionary marks 2
where English reduces it gets its own reading in the song's lexicon (tools/pronounce.py lists the
suspects; banjo, sunday, inside, misheard, whatever and fifteen joined H's today, via Gemini's review).

## Keeping learned timing singable (2026-09-27)

Opposing early and late gestures at the allowed extremes could put syllables
out of order and overlap their phonemes. H produced 89 overlapping boundaries
with an alternating -0.25/+0.25-beat phrasing. `realize.ordered_delivery` now
shares the smallest necessary timing correction among crowded notes, leaving
uncrowded notes and a phrase's overall lean unchanged. It reserves up to
100 ms between vowel onsets, never more than half the original spacing.
The scheduler fits consonants into the remaining space without the old 30%
minimum that could force them over the next vowel.

The regression check covers the lead and three harmony voices in H, B and L,
at their own tempo and 40% faster, through both engines' consonant schedules.
Every syllable stays in order and every phoneme boundary stays disjoint.

## Against a natural teacher (2026-09-26)

The artist: "I still want to make the voice less robotic (we don't need to *try* to make it sound
synthetic, i'm confident there will always be an uncanny valley)."

### The teacher, and how it was measured

SoulX-Singer, the open singing model the learned throat learns from, sings our own songs in the
throat's corpus (renders/throat/corpus/). Only the "house" singers were used to fit anything: SoulX
prompted with ten seconds of our own formant singer, in ten timbres. The singers prompted with
Eleven Music voices were a comparison only. They told us which of the house singers' habits came
from our own old singing leaking in through the prompt, and which were SoulX's own.

`tools/delivery.py` sings the teacher's exact notes with our singer and analyses both the same way:
WORLD's Harvest pitch every 5 ms, how periodic the voice is, and its level, overall and in octave
bands. It measures note by note:
- the moves between notes (when, how long, how far past, any dip first);
- the rise into a phrase;
- vibrato, drift and the modulation spectra of pitch and loudness;
- the pitch through consonants;
- line ends, syllable loudness, the envelope inside a held vowel;
- breaths and timing.

Every change was checked on songs and lines held out of the fitting: H and K whole, and a fifth of
the other items (99 segments, 4,400 notes).

A Fable review read the measurements and the plan before anything changed. It corrected several
readings:
- the teacher's bigger overshoot on the way down came from the measurement window;
- vibrato "extent" was diluted by each note's straight start;
- the house singers' early line endings, sparse vibrato and breaths were our own old delivery,
  learned from their prompts;
- a learned contour model had under 10% of the variance to learn, so rules with calibrated
  distributions won.

### What a natural singer did that ours didn't

- **Every move between notes was the same.** Ours moved at exactly the same moment every time
  (±5 ms around its place; the teacher ±30 ms). Every move then rang past the new note by 12% of the
  interval for 150 ms, like a spring. The teacher moves down earlier than up, often dips a little
  before moving up, and mostly just arrives.
- **Vibrato on every long note, and only those.** Ours put the same 28-cent, 5.3 Hz sine on every
  note of 0.9 s or more. That made a sharp spike in the pitch's modulation spectrum where a natural
  singer has a broad hump. Natural singers put vibrato on some notes: about 40% of 0.5-0.9 s notes
  and 57% of 0.9-1.5 s notes, going by the Eleven-prompted teacher. It grows in, drifts in speed
  and depth, and differs from note to note.
- **Held notes too still.** Below 3.5 Hz the teacher's pitch moves 8 dB more than ours did, and
  its loudness inside a held vowel 7-12 dB more at every rate.
- **Phrases all started the same way.** Ours scooped up 35 cents into every phrase. The teacher
  rises about 40 cents through an m, n, l, r, w or y, starts on pitch after an s or a t, and
  sometimes starts level.
- **Nothing happened at consonants.** Both teachers sag about 20 cents through a voiced stop or
  fricative between vowels, fall about 10 cents as the voice stops for a voiceless one, and start
  again about 5 cents high.
- **Line ends.** The teacher falls about 15 cents as it lets go of a line's last note. It also
  holds about 85% of the note; ours lets go 0.3 s early.
- **Breaths were whispered vowels.** The formant singer breathed aspiration through a schwa: vowel-
  coloured, 8-10 dB too loud, pressed against the next line's first sound, with digital silence
  around it. The learned throat's network "breath" was 15 dB too loud. The teacher's breath is a
  soft, bright hiss, strongest from 1 to 8 kHz, about 37 dB under the vowels, taking most of a
  short gap and up to 0.4 s of a long one.

### What changed

All of it is in `songbird/synth/voice.py`: `pitch_track`, `schedule`, `breaths`, `sway`, and the
settings below. Both engines use it (the learned throat through `throat.sing`). Each move, rise,
vibrato and fall draws its own values from streams of its own. A seed always sings the same, and
both engines sing the same pitch. The spreads in the table are at `spread` 1; the default, 0.7,
narrows them all.

| | Now | Setting |
|---|---|---|
| Moves between notes | the teacher's shape (aligned at its midpoint); each its own length (10-90% in half of `glide` for a step, 4 ms more a semitone), moment (up 10 ms and down 40 ms before the vowel, ±30 ms, a phrase leaning ±12 ms), overshoot (2.5% of the interval ±10 cents) and a small dip before moving up | `glide`, `glide_spread` 0.35, `overshoot` 0.025 |
| A phrase's first note | rises over the first tenth of a second of its first syllable: heard through a sonorant or at a vowel, hidden inside an s or a t, slight through a voiced stop; one phrase in four starts level | `scoop` 0.35 |
| Consonants | pitch sags 20 cents through a voiced stop or fricative between voiced sounds; falls 10 cents into a voiceless one; starts again 5 cents high | `SAG`, `STOP_FALL`, `RESTART` |
| Vibrato | on some notes: about 0.3 of 0.5-0.9 s notes, 0.6 of 0.9-1.5 s, 0.7 of longer, 0.15 more at a line's end, each phrase its own taste. Each its own depth (around 22 cents), rate (around 5.6 Hz), onset (around 0.25 s), growing in, drifting within the note, blooming at a line's end, ending with its vowel | `vibrato_from` 0.7, `vibrato_depth` 22, `vibrato_rate` 5.6, `vibrato_delay` 0.25 |
| Pitch drift | 1/f, 9 cents; fast wobble 0.4% | `wander` 9, `jitter` 0.4 |
| Loudness | a held vowel wavers about its own level (1/f to 1.5 Hz), swings a little with its vibrato, fades from a fifth of the way through | `waver` 2.2, `tremolo` 0.4, `taper` -4 |
| Line ends | the last vowel falls about 18 cents as it's let go; still let go as early as before (holding 85% cost the learned throat words) | `FINAL_FALL`, `line_release()` |
| Consonant lengths | each up to about 15% longer or shorter than its rule | `CONSONANT_SPREAD` |
| Breaths | shaped noise for both engines, from 0.12 s of gap: the teacher's spectrum, 30 ms rise, a slow fade, 0.1-0.4 s long, quiet again before the next line; deeper before a louder phrase or after a long rest; each its own tilt | `inhale` -36, `breathe` 0.12 |
| How unalike all of it is | 0 sings every move alike; 1 is the teacher's measured spread | `spread` 0.7 |

The phrasing extractor's template singer (tools/phrasing.py FLAT) sets `spread` to 0. A person's
gestures are measured against the machine's own deterministic delivery, and every take is measured
again, because the version hash covers voice.py. Ornaments from the drift are sung inside their
note as before: no overshoot into one, no rise before one that starts off the note, vibrato easing
while it turns, and the next move leaving from where it ended.

### The numbers

Held-out songs and lines. "Before" is the singer at d21fab4, "after" is now; brackets are the
interquartile range.

| | Teacher | Before | After |
|---|---|---|---|
| Move midpoint, up / down (ms from the vowel) | -13 / -36 | -16 / -10 | -7 / -33 |
| Its spread (IQR, all moves) | -55..+5 | -18..-9 | -37..+1 |
| Dip before moving up (cents) | -35 | -28 | -35 |
| Past the note after moving up (cents) | 19 | 27 | 18 |
| Vibrato on 0.5-0.9 s notes | 23% (Eleven 40%) | 2% | 16% |
| Vibrato on 0.9-1.5 s notes | 18% (Eleven 57%) | 100% | 52% |
| Vibrato rate between notes (SD) | 1.15 Hz | 0.93 | 0.96 |
| Pitch drift on held notes (cents) | 5.8-7.7 | 3.2-4.7 | 5.3-6.6 |
| Pitch modulation 0.5-2 / 2-3.5 / 7.5-10 Hz (dB) | 36.5 / 33.6 / 32.3 | 29.3 / 25.4 / 24.8 | 33.6 / 31.8 / 29.6 |
| Pitch modulation 4.5-6 Hz (the vibrato) | 35.1 | 38.1 | 34.4 |
| Loudness modulation in held vowels, 0.5-2 / 4.5-6 / 10-20 Hz (dB) | 23.7 / 14.0 / 12.5 | 16.1 / 4.3 / 3.5 | 19.0 / 8.5 / 5.7 |
| A held vowel's fade, last fifth against its first half (dB) | -8.4 | -7.9 | -8.1 |
| Breath peak against the vowels (dB) | -37 | -28.5 | -35.6 |
| Where in the gap the breath peaks | 43% | 86% | 24% |
| Silence between phrases (dB) | -53 | -104 | -55 |
| Pitch distance to the teacher, note by note, below 3 Hz (cents) | 35 (one teacher to another) | 34 | 36 |

Where it stands:
- **Moves and vibrato** are near the teacher.
- **The rise into a phrase** is heard earlier and a little deeper than the teacher's, which rises
  inside the first consonant.
- **Loudness inside held vowels** closed a third to a half of the gap. Pushing further cost
  words.
- **Breaths** peak a little earlier in their gap than the teacher's (24% of the way through
  against 43%).
- **The pitch distance to the teacher** doesn't move. It sits at the distance between two teachers
  singing the same notes, so it can't tell the deliveries apart.

**Words.** Whisper, tools/wer_suite.py:
- On H, four seeds: 17.1% of words misheard before, 17.8% now.
- All twelve songs, four seeds (G's made-up words left out, since Whisper invents text for them):
  23.8% before, 24.1% now (song by song, within about ±2 points either way).
- Getting there took a bisect of every commit. Three things had cost words:
  - the tract no longer resting on a schwa through a breath, so a line's first vowel slid in from
    the last and "a" was heard as "the";
  - vibrato running on through the consonants;
  - the loudness waver moving whole syllables.
  All three are fixed. At the teacher's full spread (1.0), H was still 20.0% misheard; 0.7 is the
  default (18.4%).
- A fourth cost only the learned throat: holding a line's last note to 85% (H 16.0% against 13.7%).
  It was reverted.
- The learned throat (house model) on H, two seeds: 12.6% before, 13.7% now (noise about ±1.5).

**UTMOS**, an artifact check only (speech-trained, blind to delivery), on the listening files:
- formant 1.50 before, 1.48 after;
- learned v1 2.04, 1.97;
- learned house 1.87, 1.85.
All three shifts are within the spread between the files' 8-second windows (0.08-0.18). DNSMOS
overall rose for all three (2.54 to 2.78, 2.60 to 2.75, 2.61 to 2.74). No new artifact.

### Listen

renders/production/delivery/: H's first verse and refrain, dry, before and after, the same seed,
peak-normalized alike:
- 1-2: the formant singer;
- 3-4: learned v1 (benchmark only);
- 5-6: learned house.
README.txt there says what to listen for.

### For the style and variation tables

These settings are new or have a new meaning, and a machine could vary them:
- `spread` (0-1: how unalike its moves are);
- `vibrato_from` (how readily it uses vibrato);
- `waver`, `tremolo`, `inhale`, `breathe`;
- `glide_spread`, `overshoot`, `scoop`.

The variation table's existing bounds for `vibrato_depth` (14-44), `wander` (3-10) and `glide`
still make sense.

### For the artist to reconsider

- **`spread` 0.7, not 1.0.** The teacher's variety cost Whisper about 1.5 points on H; 1.0 is the
  natural spread, if variety matters more than words. The vibrato share on long notes sits between
  the house and Eleven teachers. Say if it should be sparser (`vibrato_from` up) or richer.
- **Syllable contrasts are unchanged.** Measured against our own beat markings, the teacher leans
  about 3 dB per unit where ours leans 15 (`dynamics`). Easing ours toward it (dynamics 10, lean
  0.7, light 0.8, ease 0.5) cost 0.5 points of WER on H and left the other songs about the same.
  It's left for the artist's ear.
- **Breaths** are at the teacher's level (-36 dB). In the mix they will be quiet; `inhale` -30 would
  make them a feature.
- **Line ends are let go early, as before.** Natural singers hold about 85% of a line's last note.
  Held that long, the learned throat lost words. Worth trying again once the throat has been
  trained on it (`line_release()`).
- **The learned throat** (either model) scored a little lower on UTMOS after the change. It's
  within noise, but worth a listen: files 3-6.
- **Every take's phrasing is measured again** (the extractor's version hash covers voice.py). Its
  template singer sings without the new variety (`spread` 0).

## The first pass (2026-09-25)

A Fable review, run read-only against Milo's two takes and the Eleven Music singers, found the formant
singer (songbird/synth/voice.py) wrong in all of these. This is what changed then, and how each change
was checked; several of its settings were revised by the second pass above (vibrato, slides, taper,
breaths, line ends).

### What was wrong

- **Loudness barely moved.** The glottal pulse tables were peak-normalized.
  The singer presses harder on the syllables it leans on, and a pressed
  pulse has about 0.17 of the power of a breathy one, so the leaned-on
  syllables came out quietest. Stressed and unstressed syllables differed
  by about 0.8 dB, and the dynamics setting did almost nothing. In Milo's
  takes, syllables vary about 5 dB.
- **Nothing knew a word.** Only the beat set loudness. A word's stressed
  syllable (known from CMUdict) went unused. "The" on a downbeat was sung
  like "heart".
- **Held notes swelled in the middle.** Milo's taper steadily: about −7 to
  −9 dB by the end of a long note, the same in both takes.
- **Vibrato on everything.** Every note past half a second had 28 cents.
  People keep vibrato for the notes they hold.
- **Almost no breathing.** Three breaths in the song, and the voice was
  never quiet between lines.
- **Every slide between notes took 80 ms**, whatever the interval. A
  person's slides take longer over wider leaps and are never twice alike.

### What changed

| | Now | Setting |
|---|---|---|
| Glottal tables | equal power: pressing changes brightness, not loudness | songbird/synth/glottis.py |
| The beat | ±1 dB | `dynamics` 15 |
| A word's stressed syllable | 1 dB above its others | `lean` 1.0 |
| Little words (a, the, it, and, of…) | 1.5 dB softer | `light` 1.5, `phonetics.FUNCTION_WORDS` |
| A line's first syllable | 1.5 dB softer, eased into | `ease` 1.5 |
| A line's last syllable | 1 dB softer, let go of | `let_go` 1.0 |
| Pitch | 0.5 dB louder per semitone above the line's middle, as the natural singers measured | `climb` 0.5 |
| A line's focus word | 1 dB more, marked in the lyric (`*num-bers*`, `{*made*|*sang*|…}`) | `focus` 1.0 |
| Leaned-on notes | lifted up to 8 cents | `accent` 8 |
| Held vowels | fade from a third of the way through | `taper` −4 dB |
| Vibrato | only on notes of 0.9 s or more (0.55 s at a line's end) | `vibrato_from` |
| Breaths | a moment's quiet, then an audible breath, at every line with 0.18 s to spare; line ends let go sooner | `breathe`, `line_release()` |
| Slides | about 50 ms (10–90%) for a step, 80 ms for an octave, each varied | `glide` 0.11, `glide_spread` 0.3 |

Some settings exist but are left off. Vowels of little words reduced toward
"uh" (`reduce`) cost words. The consonant settings (`cluster`, `across`,
`glides`, `liquids`) keep their old values: the review found consonant
timing already matches natural singers.

### Checks

- **Words understood.** Whisper, tools/wer_suite.py, H, two seeds:
  - 16.4% misheard before.
  - 14.8% now.
  - Changes that raised it were backed out: vowel reduction (18.0%), and
    focus at 2 dB with its lift (16.7%).
- **Syllables.** Stressed syllables now sound about 2.7 dB above average and
  unstressed ones about 2 dB below (plain RMS). Function words are 1.4 dB
  down.
- **Vibrato.** Present on every note of 0.9 s or more, and on about 10% of
  shorter ones.
- **Slides.** They lengthen by 5 ms per semitone, with a 23 ms spread.
- **Breathing.**
  - 25 breaths, where there were 3.
  - 79% of line boundaries have at least 0.15 s of quiet before the breath.

The focus words were first suggested by a Haiku pass over the lyric, word by
word (renders/reference/emphasis-h.json). The song-bank thread then marked
them, with two changes of its own: both *went* and *slept* in the mind
verse, and *same* rather than *sang* in the sailor's.

### Phrasings and the new delivery

A phrasing gesture is what a person did that the machine wouldn't have done
anyway. So every change to the delivery changes every gesture, and every
take is re-measured (tools/phrasing.py `version()` hashes voice.py).

Two related changes:
- **Swell is learned again.** It had been dropped after the robotic
  references. Measured against the same vowel elsewhere, it now keeps the
  singer's habit: the baritone swells held notes about 2 dB, and Milo fades
  them a little more than the machine.
- **Vowel starts are recalibrated on natural voices.** Seed-VC re-voicings
  of planted takes put every onset class within 15 ms. The robotic
  references had put vowels after glides, nasals and stops 20–35 ms early.
  With the new calibration, a singer's own takes predict each other's
  timing better:

  | Take predicted from other takes | Timing R² |
  |---|---|
  | Eleven baritone | +0.38 (was +0.17) |
  | Milo | +0.48 |

  These two figures predate the forced aligner, which has since changed
  how timing is measured. Some of the agreement between takes was the old
  extractor's own repeating error: docs/PHRASING-CALIBRATION.md.

### Next

- Vowel starts now come from a forced aligner (Montreal Forced Aligner)
  where its timing can be trusted, with the loudness-climb heuristic as the
  fallback. On the natural references, 96% land within 30 ms, up from 78%
  (docs/PHRASING-CALIBRATION.md). Next there: lower the floor under timing
  (REPEATS), which was set for the old extractor's errors, and check holds
  on more real singers.
- Score-following singing synthesis (SoulX-Singer or DiffSinger) for
  natural references with known timing.
- An automatic naturalness score (a MOS predictor) as a relative number,
  with WER as the floor.
- Human recordings: the honest test of every phrasing number.
