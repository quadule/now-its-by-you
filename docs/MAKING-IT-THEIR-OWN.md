# Making the song their own: what else to learn from a singer (plan, 2026-09-26)

The artist: "in addition to the timing+intonation, let's consider if we can learn any note shifts
by the singer and other ways they make the song their own."

Today a singer's phrasing (tools/phrasing.py) is how they sing *our* notes. It records how early,
how held and how loud each note is, and its scoop, bend, fall, vibrato and tuning. The folk
process goes further: people change the tune itself, decorate it, move its words, and choose where
to breathe. Each of the changes below can be measured from takes already recorded against the
guide, and travels the way the phrasing does: as a few numbers, never audio.

## What people change, and how each could be learned

1. **Note shifts.**
   - *What:* a different note from the tune's, sung on purpose. A third instead of a second, a
     flattened seventh, a line's top note taken down, a leap filled in.
   - *How to detect:* each note's median pitch rounds to a different scale degree. It must be
     70 cents or more off, stable through the note, and in the mode (or a passing note between
     chord tones). It must also happen again: in a second take, or where the same phrase comes
     round (every refrain). That is what tells a choice from a slip.
   - *Where it goes:* a new gesture field, the degree step, per phrase and note.
2. **Ornaments.**
   - *What:* grace notes, turns, cuts and rolls; a slide through a passing note; one syllable over
     two or three notes (a melisma); a flip up into falsetto.
   - *How to detect:* two or more steady pitches inside one syllable's span, 60 ms or more each.
   - *Where it goes:* an ornament shape per note (steps and timing fractions). The singer's pitch
     track can already follow any shape we give it.
3. **Rhythm.**
   - *What:* dotted where the tune is even, or even where it's dotted; two syllables squeezed onto
     one note or one stretched over two; a pickup added or dropped; a held note carried over the bar.
   - *How to detect:* early and hold already catch some of this. Forced alignment (MFA, now in the
     extractor) gives each syllable's own start, so splits and merges become visible.
4. **Breaths.**
   - *What:* where they breathe, including in the middle of a line, and where they don't.
   - *How to detect:* silence and breath noise between syllables in the take.
   - *Where it goes:* a breath gesture that schedule() honours.
5. **Words.**
   - *What:* a singer's own word ("and then it's gone" for "and then it goes"), sung the same way in
     more than one take.
   - *How to detect:* Whisper against the lyric.
   - *Where it goes:* a candidate for the bank, as a slot option or a variant line, for the artist
     to accept. People may change the words; the LLM only fills slots.
6. **Register and key.**
   - *What:* the key they're comfortable in, or a high phrase taken down an octave.
   - *How to detect:* the key the karaoke transposes to, and octave jumps against the tune.
7. **Shape of a line.**
   - *What:* rushing into a line's end or pulling back, and swelling toward its focus word.
   - *How to detect:* slopes across a line's timing and level, beyond the per-note values.

## How a change travels

A singer's own choices live in their phrasing: when their way leads, the machine sings their
variants. PLAN.md already says the genome itself mutates only through what people sing: "the
extracted contour ... replaces the genome contour wherever it differs confidently and the
difference survives the gate." That gives a natural rule:

- **One person's variant** is theirs. It is sung when they lead, and in the lineage choir as their
  voice.
- **A variant several singers make independently, or one that a lineage keeps passing on,** is the
  folk process at work. It may enter the song's genome for the renditions that descend from it,
  within the gate (the contour must still be recognizably the song).

## Where to start

Note shifts and ornaments first: both are pitch-only, and the extractor already has each note's
pitch track. Test on:

- the reference singers, where we can plant known shifts and see if they're found;
- Milo's two takes;
- the first commissioned singers.

Word variants next; they're cheap, since Whisper is already in the loop.

Guard against false positives:
- the synthetic references never shift a note, so on them the detector must report nothing;
- a slip that happens once is not a variant.

## The first note shifts the song took (2026-09-27)

After the first night online (four singers, 28 takes: Milo, an open-call singer, milo-test-fnrlhv
and gorman, who said parts were "harder to match"), `tools/hard_notes.py` pooled every measured
note, each singer counting once, and found the tune hard in pitch, not in time: every line was
sung 20 to 45 ms late about equally, but some notes were sung as other notes by nearly everyone.
Most were lines that start like a more familiar one and then turn, where singers sang the familiar
line. The artist heard the changes and took them all (15 notes of a whole song, rhythm untouched):

| where | the words | was | now | the singers |
|---|---|---|---|---|
| v2, pickup | *a* flicker of light | low so | low la | all three sang it higher: the drop was a fifth, to the song's lowest note |
| v2, 6th note | light, *and* as quick | so | fa | all three: a passing note down the scale |
| r2, 4th note | while *you* sing it | so | fa | three of four: the leap fell on a weak syllable |
| b2, 5th-6th | a-long *like a* coal | re mi | so la | two of three sang so, as the bridge's first line has it there |
| b3, 7th note | making *and* everyone's | re | so | two of three, as the verse's third line has it there |
| b4, 7th note | if *you* leave it alone | do | re | two of three (the third higher still) |
| b3, 9th note | and ev-*ery*-one's own | re | mi | three of four, the morning after, once a fifth singer had sung (2026-09-27 10:30) |
| r1, pickup | *Who* made this song | low so | low la | three of five (+1, +1.5 and +2 semitones); the artist: follow the people (2026-09-27 11:15) |

Each is now an exact copy of the line it was being mistaken for, or the note the singers chose. Guides
built from 2026-09-27 00:20 sing it; takes sung before are still measured against what they heard,
and a phrasing leaves out a changed note's tuning from takes sung to the old one (tools/phrasing.py).
Run `tools/hard_notes.py` as more people sing: a candidate is a note half the singers or more sing
as the same other note.

**After a tune change** (2026-09-27): a take's measured "off" is from the note of the guide it sang to,
so once the tune moves a note, tools/hard_notes.py adds the difference (the guide's note against the
tune's, in the song's own key) before pooling, and a singer who sang what the tune now says counts as
on it. tools/phrasing.py likewise keeps such a sighting's timing and loudness but drops its tuning.
Run hard_notes again after each change: what remains are new candidates, not the old ones repeated.
