# The performance version (AI Song Contest 2026, Bangkok, 2026-11-29)

The contest version (the release, id 07ac74fb…, from https://now.itsby.you) moved to B major for the singers'
ranges, sung by the performance voice: the shipped throat retrained with Scylla's Band as its teacher (E8bl,
docs/THROAT.md "Scylla's Band as a teacher") and its t's softened (throat.T_CHOSEN).

- `genome.json`: the release's own genome, from its packet.
- `record-B.json`: the release's record with `params.tonic` 59 (B) instead of 62 (D). Nothing else changed.

    uv run python -m songbird render performance/genome.json --replay performance/record-B.json --out performance-B.flac

The replay says it "differs from the record's id": the id is the D major release's, and the program has moved on
since it was made. That is expected; exit status 1 means only that.

In B the lead sings F#3-G#4 and the band moves down three semitones, but the choir's floor (theory.FLOOR, E3) moves
its lowest voice to another chord tone for 10 notes of the bridge and 5 of the tag, and 2 of the bridge in choir 1.

A machine's own version for the day, on a laptop with its own voice (~/.songbird/voice.json):

    uv run python -m songbird render performance/genome.json --parent <the release's FLAC> --machine here --date 2026-11-29 --out on-the-day.flac

That one chooses its own key, singer and arrangement from the machine and the date, as every version does.
