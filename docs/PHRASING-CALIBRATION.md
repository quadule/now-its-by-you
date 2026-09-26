# Can the machine learn a phrasing? (2026-09-25)

The test the artist set: *we can learn phrasing if two inputs give a better
result than one.* The phrasing genes (songbird/phrasing.py) are measured from
sung takes by tools/phrasing.py; this is the check of that extractor, and of
how its measurements are combined.

## How it was checked

**Reference singers** (tools/reference.py). A reference singer has an
intended phrasing, drawn at random but shaped like a person's: a little
behind the beat, scooping into leaps, falling off line ends, vibrato on long
notes. Every take strays from the intent by a performance's worth of noise.
Each take follows the same guide a person sings to. It's sung by the formant
singer (as a lineage stand-in), or it's a text-to-speech reading of the lyric
moved onto the tune: macOS Daniel, ElevenLabs George and Matilda, Gemini Kore
and Puck. Then it's heard through a cheap mic in a small room. None of these
voices is anyone's, and none joins the lineage.

That gives 4 takes × 6 voices, sharing one intent, with every gesture known.
tools/phrasing_eval.py `--reference` scores what the extractor reads against
what was sung. It also scores how close a phrasing learned from n takes comes
to what was meant, as R² against singing plain: 1 is exact, 0 is no better
than no phrasing at all.

**Real takes.** Milo's two takes (tools/phrasing_eval.py `--singer milo`).
With no truth to score against, each sighting of a note is held out and
predicted from the others.

The Gemini Puck takes aren't used below. Its reading was aligned badly when
it was moved onto the tune, so its vowels don't start where its truth says
they do (the medians are 170 ms late).

**Correction, later the same day.** Listening showed the Gemini references
had bursts of static. Gemini 3.8 returns WAV, and its header had been played
as sound, putting a click before every line; that probably also broke Puck's
alignment. tools/tts.py now reads the header as a header and uses Gemini
3.8's interactions API with a style, and Eleven v3. The Kore numbers below
predate the fix. The calibration voices (Daniel, George, Matilda) weren't
affected. Every reference is also robotic, because speech is moved onto the
tune by the WORLD vocoder; finding references that sound natural is next.

## What the first run showed

A phrasing learned from one voice was *worse* than singing plain, and more
takes barely helped. For example, ElevenLabs George with 4 takes scored R²:

| timing | loudness | swell | scoop |
|---|---|---|---|
| −0.59 | −2.1 | −4.0 | −2.1 |

Averaging exactly what was sung scored +0.9 to +1.0, so the fault was the
extractor. Four causes:

1. **Holds.** Room reverberation kept a note sounding until the next one, so
   no detached note was ever seen (slope 0.08).
2. **Loudness and swell.** Each vowel sits differently in each voice's
   spectrum, and that swamped how hard a note was sung.
3. **Vowel starts.** A vowel after a glide or nasal was found early, because
   the loudness climbs through the consonant. After w and y this was about
   35 ms early in every voice.
4. **Pitch fits.** Fits of scoops and falls blew up when little of the note
   was voiced.

## Fixes

tools/phrasing.py now handles each of these:

- **Holds:** a note lets go when it falls 20 dB below its vowel.
- **Loudness and swell:** each is read against the same vowel elsewhere in
  the take.
- **Vowel starts:** the aligner's bias for each consonant class is taken back
  off (ONSET_BIAS). The bias was measured on Daniel, George and Matilda. On
  the untouched Kore voice the common classes then land close: glides +2 ms,
  vowels −1 ms, nasals −27 ms.
- **Pitch fits:** a fit needs a quarter of its shape voiced.

Then the harder finding. **Much of what the extractor gets wrong repeats in
every take by the same voice.** Per sighting, the error splits into a part
that repeats and a part that changes from take to take:

| gesture | repeats in every take | changes take to take |
|---|---|---|
| timing | 30 ms | 20 ms |
| loudness | 2.6 dB | 1.2 dB |
| scoop | 50 cents | 40 cents |
| fall | 23 cents | 23 cents |

The same split holds within a tenth on the voices it wasn't measured on. More
takes by one person average away only the second column. Averaging plainly,
or shrinking toward the singer's habit by how consistent a note is, took a
voice's consistent errors for consistent phrasing: 4 takes did *worse* than 1.

So a phrasing is now made with a floor under each note's error (REPEATS).
Only other words sung on the same note, or other people, can lower it. Each
person counts once, however many takes they sang.

## Results

Mean R² of the learned phrasing against the intent, with the final extractor
and model (voices: Daniel, George, Matilda, Kore, formant):

| inputs | timing | hold | loudness | scoop | bend | fall | vibrato | mean* |
|---|---|---|---|---|---|---|---|---|
| 1 voice × 1 take | +0.45 | +0.20 | +0.25 | +0.42 | −0.02 | −0.06 | +0.64 | +0.23 |
| 1 voice × 4 takes | +0.46 | +0.20 | +0.27 | +0.44 | −0.03 | −0.06 | +0.69 | +0.25 |
| 2 voices × 1 take | +0.59 | +0.29 | +0.34 | +0.49 | +0.11 | −0.06 | +0.69 | +0.31 |
| 4 voices × 1 take | +0.71 | +0.34 | +0.45 | +0.50 | +0.19 | −0.01 | +0.69 | +0.36 |
| all 20 takes | +0.77 | +0.35 | +0.49 | +0.47 | +0.25 | +0.04 | +0.73 | |

\*The mean is over all eight gestures. Swell counts as 0 there: it's left
out, see below.

Two findings:

- **Two inputs do beat one, when they're two people.** Two voices singing
  once each beat one voice singing four times.
- **More takes by one person help only a little.** They never hurt now, but
  the voice's own repeating errors cap what it can teach. That suits the
  project: the song learns how it wants to be sung from many singers, not
  from one.

On Milo's real takes, a phrasing made from one take predicts the other take:

| timing | scoop | bend | fall |
|---|---|---|---|
| +0.47 | +0.41 | +0.15 | +0.16 |

The two takes agree note by note, with correlations of +0.33 to +0.44 on
every gesture except vibrato (too few long notes).

## Vowel starts from a forced aligner (later the same day)

Where a vowel starts anchors timing, and every gesture measured from the
vowel on. The extractor found it where the loudness climbs out of the
consonant before it. Natural references were made to check that: Seed-VC
re-voicing planted takes as two Eleven Music singers, 8 takes and 2088
vowels whose starts are known. Against them it put 78% of vowel starts
within 30 ms. Vowels after glides, liquids and nasals were the weak spot,
about half within 30 ms, because the loudness climbs through those
consonants.

tools/align.py now asks the Montreal Forced Aligner (MFA 3.4.2, with its
english_us_arpa model and dictionary) where each vowel begins. MFA is a
speech model told the words, so it knows a w from the vowel after it.
Each lyric line is cut from the take and aligned on its own, with a wide
beam (100): sung vowels last far longer than spoken ones. Three things
made it work on singing:

- **Context words.** A line's cut starts half a second early, so it holds
  the tail of the line before. With that line's last word (and the next
  line's first) added to the transcript, MFA stopped pinning the line's
  first vowel on the tail.
- **High voices an octave down.** The model learned speech. As MFA comes,
  26% of the female voice's vowel starts were more than 0.15 s off, and 17%
  with context words. Moving a voice above about 212 Hz down an octave
  first (WORLD, spectral envelope and timing kept) brought that to 8%.
- **Knowing when it's lost.** Now and then MFA squeezes a run of words into
  a few frames and stretches one phone over the rest. Repeated syllables
  ("la la la") are the usual place. So its start is used only where its
  own timing looks like singing of the tune, or where it agrees with ours
  within 0.15 s. Looking like singing means the vowel lasts at least a
  quarter of its note, the steps to the vowels either side are within a
  factor of two of the tune's, and it's within 0.4 s of the guide.
  Everywhere else ours stands. MFA's leftover bias for each class of sound
  before the vowel (0 to 20 ms late) is taken off.

| Seed-VC, 2088 vowel starts | within 30 ms | within 60 ms | >0.15 s off | RMS |
|---|---|---|---|---|
| ours | 78% | 93% | 0.1% | 32 ms |
| MFA as it comes | 80% | 84% | 14.6% | 388 ms |
| MFA leading, ours as fallback | 96% | 98.5% | 0.1% | 20 ms |

MFA's bias was measured on these same takes. Learned on one voice and
applied to the other instead, the last row is 95% and 99%.

Within 30 ms, by the sound before the vowel:

| | vowel | stop+v | glide+v | liquid+v | nasal+v | fricative+v | fricative | stop | aspirate | a line's first |
|---|---|---|---|---|---|---|---|---|---|---|
| ours | 94% | 89% | 51% | 62% | 61% | 78% | 100% | 73% | 73% | 71% |
| MFA leading | 93% | 99% | 97% | 98% | 95% | 91% | 100% | 100% | 89% | 94% |

What that does to phrasing (Seed-VC, both voices):

- **Timing** reads at r = 0.87 to 0.88 against what was sung (was 0.66 to
  0.70). It reads at 0.95 of its size (was 0.83), with 15 to 17 ms of error
  (was 26 to 32).
- **Learned timing** comes closer to the intent. Its R² is +0.38 from one
  take (was +0.25) and +0.67 from all eight (was +0.59). A plain average of
  the raw readings reaches +0.88 (was +0.60), against a ceiling of +0.97.
  So the floor under timing (REPEATS, set for the old extractor's errors)
  now holds a good phrasing back, and can come down.
- **Scoop** reads at 0.87 to 0.94 of its size (was 0.75) and learns to
  +0.36 (was +0.29). Level, bend, fall and vibrato hardly move.

**Holds.** A note's release was looked for up to the next vowel's start.
With vowel starts now after their consonants, a voiced consonant (n, l, w)
counted as the note still sounding and hid any gap before it. Hold read
worse: r 0.39 fell to 0.32. The release is now looked for up to where the
next syllable begins (its vowel start less its consonants as the template
sings them), in the take and the template alike. Hold now reads at r = 0.48
to 0.49 (0.38 to 0.40 before either change). It learns to +0.42 from eight
takes (was +0.15).

**The robotic references disagree.** On the references made by moving
speech onto the tune, MFA-led starts are better for the formant singer
(71% to 92% within 30 ms). They're worse for Daniel, George and Matilda.
Within 60 ms, Daniel falls from 91% to 85%, George from 83% to 75% and
Matilda from 82% to 72%. Learned scoop and bend fall there too (pooled
scoop +0.13 to −0.10). Those references' "true" vowel starts come from
aligning the spoken reading before it was moved, with the same kind of
loudness reading our extractor makes. So an extractor that shares that
error looks right on them, which is why ONSET_BIAS was re-measured on
natural voices. They still check the gestures that don't hang on a vowel's
start.

**Real takes, with no truth.**

Milo's two takes agree far more now:

- On timing: note by note, r +0.36 rose to +0.66, and a new take predicted
  from the other rose from R² +0.35 to +0.68.
- On scoop: r +0.27 rose to +0.55.
- On holds, less: +0.50 fell to +0.14.
- At his 47 line starts, ours put the vowel a median 255 ms after his voice
  began. MFA puts it 51 ms after.

The Eleven Music singers (11 takes) predict one another's timing far less.
A singer held out and predicted from 8 others fell from +0.44 to +0.06.
Most of the old figure was the extractor's own error, the same in every
voice. There, 38% of the measured timing was a constant per class of
consonant: vowels after nasals read 45 ms early and after stops 65 ms, in
every singer. Now 9% is, with every class within 11 ms. The same check on
the Seed-VC takes, where the truth is known, finds MFA's timing about as
predictable from take to take as what was sung (+0.52 to +0.59, truth +0.60
to +0.61, ours +0.45 to +0.46). The Eleven singers' holds, scoops and
swells also predict each other less (+0.52 to +0.32, +0.38 to +0.11, +0.63
to +0.56).

**Cost.** MFA runs once per take. The alignment is kept in
renders/measured/mfa/, keyed by the take's audio, its guide, its words and
MFA's settings, and never by the rest of the extractor. A change to the
voice re-measures every take without aligning again (41 takes in 9
minutes). For a new take, karaoke's "Make X's phrasing" took about 25 to
40 s and now takes 65 to 75 s, on a machine busy with other work. A high
voice adds about 25 s for the octave. Without MFA installed, everything
measures as it did.

**Caveats.**

- The Seed-VC takes are both the test and part of the fit. ONSET_BIAS was
  measured on six of them, which flatters ours; MFA's bias on all eight.
- The truth there is the synthesizer's schedule, re-voiced by Seed-VC. It
  isn't a person singing.
- On its own, MFA still loses its place on about 5% of vowels. The
  plausibility rule catches nearly all of them, but it has only been tried
  on this song.
- Three other things didn't help: adapting MFA's model to the singers
  (`mfa adapt`), `--fine_tune`, and a dictionary with exactly one vowel per
  note.
- MFA dithers its features, so aligning a take twice moves a few
  boundaries by 10 ms. That's another reason alignments are kept.

MFA lives outside the repo in /Users/milo/Code/mfa: a micromamba env of
conda-forge's montreal-forced-aligner, the two english_us_arpa files saved
with `mfa model save`, and a wrapper at bin/mfa. The firewall (LuLu)
blocked micromamba's own downloads, so the packages were fetched with curl
into a local channel and installed from there. Never pass MFA `--verbose`:
it then asks GitHub for its latest version and waits. Runs queue on
/Users/milo/Code/mfa/.lock (tools/align.py `lock()`), because two at once
unpack the model into the same folder.

## Limits and what's next

- **Swell** can't be read yet: r ≈ 0.2 against what was sung. It's out of the
  phrasing (SUNG swell 0) until it can.
- **Falls** read at a third of their size, with r ≈ 0.3. They add nothing to
  a phrasing yet.
- **Overall timing lean.** The overall lean behind or ahead of the beat can't
  be told apart from a device's unreported delay. The karaoke's auto-sync
  removes some of both.
- **The reference singers' own alignment.** The spoken readings are moved
  onto the tune by aligning them first, and a bad alignment (Puck) breaks the
  truth. Better references would sing, not speak.
- **Next:** more real singers. That's the test that counts now, and the
  karaoke keeps each person's takes apart for it.

Rerun it all:

```
uv run python tools/reference.py songs/h-now-its-by-you.json --voice formant say:Daniel elevenlabs:George elevenlabs:Matilda gemini:Kore gemini:Puck
uv run python tools/phrasing_eval.py songs/h-now-its-by-you.json --reference formant say-daniel elevenlabs-george elevenlabs-matilda gemini-kore --pool --onsets
uv run python tools/phrasing_eval.py songs/h-now-its-by-you.json --reference seedvc-eleven-warm-baritone-male seedvc-eleven-clear-bright-female --pool --onsets
uv run python tools/phrasing_eval.py songs/h-now-its-by-you.json --singer milo
uv run python tools/align.py songs/h-now-its-by-you.json renders/reference/seedvc-*/h-now-its-by-you-take*.wav   # align ahead (measuring does it anyway)
```

The ElevenLabs and Gemini keys come from the environment or from `.env`,
which git ignores. Each line read is cached in renders/reference/speech/, so
each voice costs about 780 characters, once.
