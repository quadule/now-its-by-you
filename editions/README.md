# Listening editions

Three arrangements of **Now It's by You** made by hand, each a file of choices
the program applies on top of its own (`songbird render --edits`). Each keeps the
song's tune, key and refrain, and a version made from one carries its choices
in its record (`chosen_by_you`).

**Open Door** is the song's default arrangement (`seed_params` in the genome carry
it; the file spells the same choices out). The harp plays alone under the first
line, and the rhythm and the answering instruments join a few at a time. The
upper band drops out for the first half of the last refrain, and the guitar and
the others come back under its answer. The lead sits a little into the band, in
a closer, drier room.

**Night Wire** is the electric one: 102 BPM, kit, bass, acoustic and electric
guitar, organ, glockenspiel and claps, with the same entrances and breakdown,
which give the hook room. Echoing backing parts and a wider room put more of the
band around the lead. The command below adds three synthetic singers in harmony:
stand-ins, not anyone's voice.

**Hand to Hand** is Open Door's arrangement with two verses from the bank, `box`
and then `wire`. Children fill the gaps in a damaged music box; later, perfect
digital copies arrive that nobody knows by heart. The contrast gives the bridge
a human act to call back to.

To hear them, from the repository's root:

```sh
uv run songbird render songs/h-now-its-by-you.json --edits editions/open-door.json --out renders/open-door.flac --pack
uv run songbird render songs/h-now-its-by-you.json --edits editions/night-wire.json --choir 3 --out renders/night-wire.flac --pack
uv run songbird render songs/h-now-its-by-you.json --edits editions/hand-to-hand.json --out renders/hand-to-hand.flac --pack
```

All three are sung by the program's own voice; nothing more is fetched. The
song masters to -14 LUFS with peaks under -1 dBTP, so compare them at the same
volume, and listen for changes of texture and for the room around the last
question as much as for loudness.

`--replay` makes a version again from its file's record, sample for sample on
the same kind of computer (docs/PACKET.md):

```sh
uv run songbird render songs/h-now-its-by-you.json --replay renders/open-door.flac --out renders/open-door-again.flac --pack
```

How they were made and judged:
[the creative review](../docs/history/CREATIVE-REVIEW.md) and
[phrasing calibration](../docs/history/PHRASING-CALIBRATION.md). To compare
finished files by their numbers, see "Checking a render without ears" in
[the README](../README.md#checking-a-render-without-ears).
