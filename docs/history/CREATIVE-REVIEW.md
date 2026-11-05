# Now It's by You: creative and technical review, 2026-09-27

*History: a review of the song and its production on September 27, 2026, the day before the first version.*

The song's strongest idea is already in its form: one voice asks who made it;
other voices can eventually help pass it on. The fifth on “song,” the answering
“nobody knows,” and the cadence into “you” are the things to protect. The most
useful production work is to make those moments arrive differently each time.

## The words and the dramatic shape

The seed's wire/screen sequence gives a clear contemporary argument. Its weakness
is that both verses make much the same argument before the bridge answers it.
The larger bank already contains more tactile possibilities: the damaged music
box, a skipping rope, a cook who keeps whistling after the radio fades. Those
actions let the idea happen instead of explaining it again.

The **Hand to Hand** edition selects the existing `box` then `wire` verses.
Children repair an imperfect mechanism by singing; perfect copies later fail to
be known by heart. The chronology still follows the bank's rules. That contrast
earns the bridge's instruction to carry the song, with no new exposition and no
changes to its fixed refrain. The original seed remains available for comparison.

I would keep the last “owns” question bare enough to register, then allow the
answer and the wordless tag to become communal. The long instrumental opening
can still be an acquired taste; retain it for the full piece, and use the
studio's section auditions when introducing the refrain to a new singer.

## Arrangement, instruments and singers

**Open Door** is the first production candidate: harp supports the opening line,
the other players enter in stages, and the upper band leaves the first half of
the last refrain before returning. This exposed a small arrangement bug: the
entrance planner preferred a guitarist who wasn't playing that verse, so bass
entered first. It now finds the chord player actually present.

**Night Wire** explores the more electric side: a slightly faster pulse, guitars,
organ, glockenspiel, kit, claps and echo parts. Its three audition singers are
synthetic stand-ins, explicitly requested with `--choir 3`. The ordinary seed
does not acquire fictitious ancestors. The arrangement needs the same empty
spaces as the acoustic version; a countermelody on every line would weaken the
hook.

The separate **Open Door / volunteers** study uses 28 currently enabled cached
takes from four singers. Its lead pools reduced gestures with each singer
weighted equally at each sung occurrence. Three backing parts use the individual
delivery learned from the three singers with multiple takes. Their vocal timbres
remain synthetic. No new acoustic model was trained and no donated recording
was reprocessed, copied into the worktree or embedded in an audition packet.
The caches came from their original guides and preserve their extractor stamps.
This is an audition of the current learner against existing measurements, not
an assertion that every extracted gesture is correct.

Render commands and repeatable edit files are in [editions](../../editions/README.md).

## Timing, pronunciation and inflection

The immediate failure was mechanical: alternating legal early/late gestures
could reverse close syllables and overlap their consonants. A stress test on H
produced 89 overlapping phoneme boundaries. The realizer now adjusts conflicting
onsets together, in lyric order, while leaving an uncrowded phrase's lean alone.
The phoneme scheduler fits consonants to the space actually available. Tests
cover lead and three harmonies in H, B and L, at normal and 140% tempo, for both
rule-based and learned consonant durations.

Learning also mishandled missing gesture fields, different-length guides and
unequal take counts. Missing fields now fall back individually; vibrato votes
use singer weights and never treat the “machine decides” sentinel as a measured
depth. The uncertainty estimate respects the actual weights of repeated words.

The dry-voice regression check remains **62 errors in 438 words (14.2%)**, before
and after these changes, over two deterministic voice seeds and H's refrain and
five seed verses. This verifies continuity; it is not an intelligibility gain.
Whisper errors such as “ever/never,” “bright/right” and final consonant omissions
are useful listening targets, not automatic reasons to change the dictionary.
Secondary stress and vowel identity must be considered separately: flattening
every secondary stress can accidentally change an English vowel to schwa.

The highest-value next pronunciation work is a short, fixed listening set of
those difficult words in their actual lines, alongside the existing all-lyrics
WER check. Judge the phrase in the mix as well as the isolated word. Prefer
local pronunciation or consonant fixes with matched before/after renders over
raising articulation globally. More vibrato and larger pitch bends are not
synonyms for a more convincing singer.

## What the volunteer evidence says

Whole performances are held out: none of a test take's notes train its own
prediction. The evaluator samples bounded training subsets, so collecting more
takes no longer requires constructing every possible combination. Each report
keeps prediction counts and extractor versions, with null for insufficient
evidence. Four cached takes marked not to use were excluded.

Anonymous timing results, R² against the plain score:

| Enabled takes | From one training take | From all other takes |
|---:|---:|---:|
| 10 | -0.335 | -0.062 (9) |
| 9 | +0.036 | +0.508 (8) |
| 8 | +0.297 | +0.466 (7) |
| 1 | insufficient evidence | insufficient evidence |

More takes helped all three measurable timing curves, but the first still does
not beat plain timing. Holds, scoops, fades and pitch bends also vary by singer;
there is no defensible single “humanization improved” score. The measurements
share one older extractor fingerprint; the scheduling fix changed the current
fingerprint, so these are explicitly cached-measurement results. They test the
learner, not the accuracy of a fresh extraction or listener preference.

For each new volunteer batch: keep its original guide, respect each take's use
flag, run [the held-out evaluation](PHRASING-CALIBRATION.md), regenerate the
compact phrasing, then audition the same refrain and difficult verse at equal
loudness. Compare support counts when a batch includes partial takes. Archive
the anonymous report with the candidate; training data and heavyweight analysis
dependencies stay outside the portable packet.

## Mixing, mastering and the traveling artifact

The editions use the existing -14 LUFS master and -1 dBTP ceiling. Open Door puts
the lead slightly further into a drier band; Night Wire widens the ensemble.
Arrangement creates the contrast before the limiter sees it. The default master
already protects peaks and preserves substantial range, so there is no reason
to increase its loudness target.

Finished-packet checks, one deterministic rendition of each:

| Rendition | LUFS | Range, LU | True peak, dBTP | Section word errors |
|---|---:|---:|---:|---:|
| Original | -14.00 | 7.83 | -1.68 | 19/206 (9.2%) |
| Open Door | -14.00 | 7.07 | -1.34 | 18/206 (8.7%) |
| Hand to Hand | -14.00 | 7.18 | -1.05 | 18/210 (8.6%) |
| Night Wire, three backing singers | -14.05 | 6.32 | -1.05 | 26/206 (12.6%) |
| Open Door, volunteer ensemble | -14.02 | 8.82 | -1.05 | 34/206 (16.5%) |
| Open Door, half volunteer gestures | -14.01 | 9.03 | -1.05 | 27/206 (13.1%) |

These use local Whisper base.en and the repository's section scorer, including
its repetition and hallucination handling. The dry check above sings a different
set of sections and two seeds; its percentage is not directly comparable. One
word separates Original and Open Door, far too little to call a general
recognition improvement. Hand to Hand has different words. The acoustic editions
lose about 0.13 dB of mean power when folded to mono; Night Wire loses 0.60 dB.

Two controls separate the volunteer result: the learned lead alone scores
29/206 (14.1%), and the plain lead with three plain synthetic backing singers
scores 25/206 (12.1%). Both delivery and ensemble density matter. The half-strength
study blends learned deviations equally with neutral gestures using `P.blend`,
leaving vibrato to the machine. It improves this ensemble's recognition while
retaining a larger loudness range, but still does not match the solo baseline.
Keep it as a listening alternative; do not silently promote full volunteer
strength as a universal quality improvement.

`tools/packet_review.py` reproduces the finished-packet comparison, including
audio identity, actual loudness and peaks, mono power, archive size and optional
WER. It reports whether the current program matches the packet whose section
times it reconstructs. A complete learned lead/three-voice ensemble also replayed
to the **identical PCM hash** using its embedded program from outside the
repository, without the original phrasing JSON files being supplied.

The larger portability defect was that a packet remembered a contribution's
description but not its actual phrasing. Lead and choir gestures now travel in
the record, are used by studio previews, and pass to children. Replay restores
the final voice and mix too. A regression test deletes the local phrasing file
and verifies an identical replayed audio hash, including a choir.

The **8 MiB** budget is a goal, measured before compression (the artist later made it a goal that warns, not a wall). The program and
model currently occupy about **5.20 MiB**, including a **3.40 MiB** throat, leaving
about **2.80 MiB** for improvements. Packing additionally checks the rendition's
metadata and archive size before replacing an existing file. The FLAC audio and
separately installed Python runtime dependencies are outside that budget.

These are production candidates supported by code, score and signal checks.
They still need an artistic listening decision; recognition and loudness metrics
cannot make that decision.
