# How the singer delivers a song (2026-09-25)

The voice stays synthetic. What should sound like a person is the delivery:
how hard each syllable is leaned on, how a held note moves, when the voice
breathes, how it gets from one note to the next. A Fable review, run
read-only against Milo's two takes and the Eleven Music singers, found the
formant singer (songbird/synth/voice.py) wrong in all of these. This is
what changed, and how each change was checked. Listening decides; these
are the guard rails.

## What was wrong

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

## What changed

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

## Checks

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

## Phrasings and the new delivery

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

## Next

- A forced aligner (Montreal Forced Aligner) in place of the loudness-climb
  onset heuristic, if it measures better.
- Score-following singing synthesis (SoulX-Singer or DiffSinger) for
  natural references with known timing.
- An automatic naturalness score (a MOS predictor) as a relative number,
  with WER as the floor.
- Human recordings: the honest test of every phrasing number.
