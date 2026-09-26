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
