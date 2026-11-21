# The performance version (AI Song Contest 2026, Bangkok, November 29, 2026)

The contest version is the release (id 07ac74fb…, from https://now.itsby.you) in B major for the singers' ranges,
sung by the performance voice: the shipped throat retrained with Scylla's Band as its teacher (E8bl, docs/THROAT.md),
its stops released as articulate makes them (tE's t).

- `genome.json`: the release's genome, from its packet, its bank's lines marked with their focus words as the song's are (`songs/h-now-its-by-you.json`, the same file).
- `record-B.json`: the release's record with `params.tonic` 59 (B) instead of 62 (D). Nothing else changed.
- `record-arc-morph.json`: the stage mix, arc-morph ("Awards performance draft" on the home page): record-B with
  the lead's arc and the twins in the grid (docs/ARRANGE.md, "A stage edition"). The band begins as synths: the
  intro's on its own notes, a game console's drums joining at its third bar; the first verse a synth band of synth
  folk's own (an arpeggio and pad, then its drum machine, then its bass, a line each); then the band itself, one
  player a line (the harp, the bass, the guitar, the drum), each where the lead takes its next step of people.
  The screen verse ends in the artist's own lines (composition "lines", handed down to a child that sings it):
  "they laughed and they wept, and they *scrolled* on and on, / but nobody *sang* it, and then it was gone."

- `record-final.json`: the stage version, arc-morph with the stage's own words and ending. The refrains ask who
  made, wrote and owns the song, and their lines and the screen verse's are the artist's (composition "lines"):
  "It's *yours* when you sing it, and then it goes." / "Who *wrote* this song? Nobody, so / it's *yours* if you
  sing it and then who knows? / It's yours for the *taking*, so take it, and do / whatever you like, but leave some
  of *you* too." / "It's *yours* if you sing it, and then it *grows*. ... and now that you know it, go make it by
  *you*." The tag is played, not sung (`arrange.tag:0.sung` false): a bowed upright bass (`bowedbass`) on the
  whistle's tune two octaves down, the twin "bowedbass" with its levels along the tag, and the last phrase slows
  to less than half its speed (`ritardando` 1.5).

    uv run python -m songbird render performance/genome.json --replay performance/record-final.json --out final.flac
    uv run python -m songbird render performance/genome.json --replay performance/record-B.json --out performance-B.flac
    uv run python -m songbird render performance/genome.json --replay performance/record-arc-morph.json --out arc-morph.flac

The replay of record-B gives id c1ab7b6a262e. It says it "differs from the record's id": the id in the record is
the D major release's. That is expected, and exit status 1 means only that.

In B the lead sings F#3-G#4 and the band moves down three semitones. The choir's floor (theory.FLOOR, E3) moves
its lowest voice to another chord tone for 10 notes of the bridge and 5 of the tag, and 2 of the bridge in choir 1.

A machine's own version for the day, on a laptop with its own voice (~/.songbird/voice.json):

    uv run python -m songbird render performance/genome.json --parent <the release's FLAC> --machine here --date 2026-11-29 --out on-the-day.flac

It chooses its key, singer and arrangement from the machine and the date, as every version does.
