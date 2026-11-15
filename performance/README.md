# The performance version (AI Song Contest 2026, Bangkok, November 29, 2026)

The contest version is the release (id 07ac74fb…, from https://now.itsby.you) in B major for the singers' ranges,
sung by the performance voice: the shipped throat retrained with Scylla's Band as its teacher (E8bl, docs/THROAT.md),
its stops released as articulate makes them (tE's t).

- `genome.json`: the release's genome, from its packet.
- `record-B.json`: the release's record with `params.tonic` 59 (B) instead of 62 (D). Nothing else changed.
- `record-arc-morph.json`: the stage mix, arc-morph: record-B with the lead's arc and the twins in the grid, and
  synth folk's arp and pad (docs/ARRANGE.md, "A stage edition").

    uv run python -m songbird render performance/genome.json --replay performance/record-B.json --out performance-B.flac
    uv run python -m songbird render performance/genome.json --replay performance/record-arc-morph.json --out arc-morph.flac

The replay of record-B gives id c1ab7b6a262e. It says it "differs from the record's id": the id in the record is
the D major release's. That is expected, and exit status 1 means only that.

In B the lead sings F#3-G#4 and the band moves down three semitones. The choir's floor (theory.FLOOR, E3) moves
its lowest voice to another chord tone for 10 notes of the bridge and 5 of the tag, and 2 of the bridge in choir 1.

A machine's own version for the day, on a laptop with its own voice (~/.songbird/voice.json):

    uv run python -m songbird render performance/genome.json --parent <the release's FLAC> --machine here --date 2026-11-29 --out on-the-day.flac

It chooses its key, singer and arrangement from the machine and the date, as every version does.
