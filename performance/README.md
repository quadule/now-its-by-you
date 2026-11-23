# The stage version (AI Song Contest 2026, Bangkok, November 29, 2026)

The song as it is performed: the band moving from synths to players as the lead moves from machine to people, the
artist's own words in the refrains and the screen verse, a breath before each refrain, and a played tag. It is sung
by the performance voice: the shipped throat retrained with Scylla's Band as its teacher (docs/THROAT.md), carrying
the phrasing of ten singers.

- `genome.json`: the song's genome (`songs/h-now-its-by-you.json`, the same file).
- `record-final-A.json`: the stage version in A major, for singing.
- `record-live-A.json`: the same, mixed for singing over on a concert PA: −12 LUFS, a drier room (`space` 0.6) for a
  real hall, a fuller, wider band (`forward` 6.5, `width` 1.3), the synthetic lead 1.2 dB back after the first verse
  so live voices own the front while it stays a clear guide, the 808 back at −2 dB in the last refrain with the
  guitar eased 2 dB, and the bowed bass of the tag trimmed a little.
- `record-final.json`: the stage version in B major.

    uv run python -m songbird render performance/genome.json --replay performance/record-final-A.json --out final-A.flac
    uv run python -m songbird render performance/genome.json --replay performance/record-live-A.json --out live-A.flac

## What it plays

- **The intro**: the tune on a hollow square lead without the whistle's grace notes, an electric piano an octave
  under it, and the 808 as a soft, worn kit.
- **The band**: the first verse a synth band (synth folk's arpeggio and pad, then its drum machine, then its bass, a
  line each); then the players come in one a line (the harp, the bass, the guitar, the drum), each where the lead
  takes its next step toward people (docs/ARRANGE.md, "A stage edition").
- **The breaths and turns**: a breath before each refrain (the form's `breath`), and each of the five breaths and
  turns has its own players: the synth lead, the lute, the fiddle over the whistle, the whistle over a held fiddle,
  the bowed bass.
- **The tag**: played, not sung (`arrange.tag:0.sung` false): a bowed upright bass (`bowedbass`) on the whistle's
  tune two octaves down, its last phrase slowing to less than half its speed (`ritardando` 1.5).

## Its words

The refrains ask who made, wrote and owns the song; their lines and the screen verse's are the artist's
(composition "lines", handed down to a version that sings them):

> The whole world was tuned in and *watching* one day, / a million bright faces all lit the *same* way, / they
> laughed and they wept, and they *scrolled* on and on, / but nobody *sang* it, so then it was gone.
>
> It's *yours* when you sing it, and then it goes.
>
> Who *wrote* this song? Nobody, so / it's *yours* if you sing it and then who knows? / It's yours for the *taking*,
> so take it, and do / whatever you like, but leave some of *you* too.
>
> It's *yours* if you sing it, and then it *grows*. ... and now that you know it, go make it by *you*.

## Its place in the lineage

Generation 2: the child of the awards draft (eb8fb05e…), itself from the first version (07ac74fb…). A version sung
from it is generation 3, for example a laptop's own version on the day:

    uv run python -m songbird render performance/genome.json --replay performance/record-final-A.json --out final-A.flac
    uv run python -m songbird render performance/genome.json --parent final-A.json --machine here --date 2026-11-29 --out on-the-day.flac

It chooses its key, singer and arrangement from the machine and the date, as every version does.

`record-arc-morph.json` (the awards draft) and `record-B.json` stay here for the draft's released file
(web/sing/editions.json).
