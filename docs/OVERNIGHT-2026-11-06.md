# Overnight, 2026-11-06 to 07: Scylla's Band as the throat's teacher

The artist: "try to train against it to improve ours", then "take this as far as you can overnight", with Gemini
for listening (at most $5-10; this night and the next day, $1.16). Everything is on branch `claude/scylla-teacher` (from
`claude/singing-synthesis-exploration-c0bf8c`) in atomic commits; nothing is merged, pushed, deployed or shipped.
The shipped voice (songbird/synth/throat.npz) is unchanged. docs/THROAT.md "Scylla's Band as a teacher" has the
method and the numbers. The throat tests pass (27).

## Listen first

**renders/throat-scylla/listen/compare/** (dry, a minute of H from 0:30): `seed-N-*` is H's seed rendition,
`ada-N-*` a machine's own blend (fictional:ada), the same notes, timing and seed in each:
1 shipped, 2 A-160 (October), 3 C, 4 D, 5 S, 6 Cbl, 7 Dbl, 8 E16, 9 E16bl, 10 E8bl.

- C = October's blend A with Scylla's singing; D = blend B with it; S = Scylla's alone.
- Cbl, Dbl = C and D drawing only the blend singers: Scylla's rows taught the network but no voice uses them.
- E = the shipped voice's own house corpus with Scylla's, the shipped volunteers row kept (added the next morning,
  THROAT.md "E"); E16bl and E8bl draw exactly the shipped voice's singers, E16 Scylla's too (still 0.3 people).

**renders/throat-scylla/listen/full/**: complete songs with the band, H (2:31) and F (3:41), seed and ada, numbered
the same way (01-10).

The whole voice stems are in listen/; the models are
renders/throat-scylla/model-*-160.npz (`SONGBIRD_THROAT=` to sing with one).

## What the numbers say

- **Words:** C and D mishear 3.7% of H's words (1314 words over six seeds), the shipped voice 10.3%, A-160 7.7%.
  Cbl 5.5%, S 5.6%, Dbl 7.3%.
  Over every song's words (5002, two seeds): D 7.6%, C 8.7%, Cbl 9.8%, S 10.6%, A-160 11.4%, shipped 15.2%.
- **Sounding human (Gemini):** every new model beats the shipped voice; S by the most (+1.6 of 3), C and D
  +0.2 to +1.1, Cbl +0.3 to +1.0. Head to head they're within the judge's noise (it agrees with itself across
  the two orders only 59% of the time).
- **In the mix** with the band, Gemini hears no difference (Cbl -0.08, D +0.33 against the shipped voice): the
  gain is in the dry voice and the words.
- **Size and speed:** unchanged, 160 channels, 3.7 MB.
- **Variety:** Cbl's machines sit as close together as A-160's (0.61 and 0.65 dB from the default blend, the
  shipped voice's 1.10); drawing Scylla's singers widens it (C, D 0.8; S 1.09).

## The next morning: E

E16bl (the shipped corpus and Scylla's, drawing the shipped voice's singers at its 0.3 people) hears 7.9% over every
song, against Cbl's 9.8% and the shipped 15.2%; the same as Cbl on H (5.5%); Gemini can't tell it from Cbl. But the
volunteers' row, with no frames of its own, moved about 6.5 dB from how it sings today (the house rows 2.5).

## Decisions for the artist

- **The volunteers' share.** Scylla's singers carry none of the people's row. Drawing them (C, D) puts a machine's
  voice at about 0.1-0.35 people, below your 0.3-0.6; S, Csc and Dsc have none. **Cbl keeps the share** and still
  mishears about half as many of H's words as the shipped voice (two thirds over every song), so it's my pick to
  ship if your ears agree; C or D if their clearer words are worth a smaller share (the range is yours, not the
  consent's).
- **Scylla's training data isn't disclosed.** Its license (Apache-2.0) allows this use, but its fourteen fixed
  voices may be modelled on singers we know nothing about. Every Scylla singer is source `scyllasband`, so
  `dataset.py --without scyllasband` takes them all out again.
- **ink and tuesday** sang sharp (50 and 31 cents) and are out (ink) or nearly so (tuesday, 3 minutes).

## Not done

- Gemini on any song but H.
- Holding the volunteers' row in E: frames of the shipped model singing as the volunteers alone, added to its corpus.
- C's words with the people's share kept: the blend singers would need more of the people's row (up to 0.6 each)
  and `throat.machine_mix` a floor on the blend rows' part of every voice; not tried.

## The next afternoon: the contest version and the t's

The comparisons that count are now renders/throat-scylla/listen/contest/: the release (Now It's by You is a 2026 AI
Song Contest finalist) replayed exactly with each throat, choir and all. More of Scylla singing H (Cbl2, E8bl2)
didn't change much. The harsh t's are the burst's colour (4-5 kHz), not its level; A and B move it up, and the artist
chooses between them (THROAT.md "The contest version, more of H, and the t's").
