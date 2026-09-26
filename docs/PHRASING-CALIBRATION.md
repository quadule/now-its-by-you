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
uv run python tools/phrasing_eval.py songs/h-now-its-by-you.json --singer milo
```

The ElevenLabs and Gemini keys come from the environment or from `.env`,
which git ignores. Each line read is cached in renders/reference/speech/, so
each voice costs about 780 characters, once.
