# Listening editions

Three authored starting points for **Now It's by You**, retaining the written
tune, key and turning refrain. Their choices are carried in each packet's
`chosen_by_you` record. The original seed and its default rendering stay intact.

**Open Door** is the seed's own arrangement since 2026-09-27 (`seed_params` in the genome carries it,
with the mix review's tweaks: forward 7.5, width 1.25, drum 1.5; the file here spells the same choices out).
It starts with harp under the first line, lets the rhythm and answering
instruments join gradually, then removes the upper band for the first half of the
last refrain. Guitar and the other players return under its answer. The lead sits
a little further into the band, with a closer, less reverberant room. This is the
first production candidate to audition.

**Night Wire** is the electric alternative: 102 BPM, kit, bass, acoustic and
electric guitar, organ, glockenspiel and claps. The same entrance and breakdown
shape gives the hook space. Echo backing parts and a wider room put more of the
ensemble around the lead. The command below adds three **synthetic audition
singers**; these are stand-ins, not donated voices or invented ancestors.

**Hand to Hand** uses Open Door's arrangement and pairs the bank's existing `box`
and `wire` verses, in that order. Children fill the gaps in a damaged music box;
later, perfect digital copies arrive that nobody knows by heart. The contrast
gives the bridge a human action to call back to and keeps the bank's chronological
order. Credit for both verses stays with their bank entries.

From the repository root:

```sh
uv run songbird render songs/h-now-its-by-you.json --edits editions/open-door.json --out renders/review/open-door.flac --pack
uv run songbird render songs/h-now-its-by-you.json --edits editions/night-wire.json --choir 3 --out renders/review/night-wire-ensemble.flac --pack
uv run songbird render songs/h-now-its-by-you.json --edits editions/hand-to-hand.json --out renders/review/hand-to-hand.flac --pack
```

All three use the existing learned throat. Neither new samples nor another model
are needed. Since 2026-09-27 the seed masters to -14 LUFS (it was -12 for a day: the artist heard the louder master as tapping and clipping on small speakers, and the limiter was working 3.5 dB on the bridge) (`loudness` in seed_params, not an edit; the contest's
submission guide says nothing about normalizing, so it is heard as played), still under the -1 dBTP ceiling;
judge the changes at equal playback volume. A fuller band need not have a larger
whole-song loudness range: listen for changes of texture and the final question's
space as well as the meter.

For a contribution made by `tools/phrasing.py`, add `--phrasing path/to/lead.json`.
For individually learned backing delivery, use `--choir-phrasing` followed by the
files for those singers. The packet now carries the reduced lead and choir
gestures, so replay and children do not need those local files. No recording goes
into the packet. To audition the packet exactly:

```sh
uv run songbird render songs/h-now-its-by-you.json --replay renders/review/open-door.flac --out renders/review/open-door-replay.flac --pack
uv run songbird budget
```

Production choices and remaining questions are in
[the creative review](../docs/CREATIVE-REVIEW.md); the continuing measurement
workflow is in [phrasing calibration](../docs/PHRASING-CALIBRATION.md).

Compare finished packets before accepting a new production or volunteer batch:

```sh
uv run python tools/packet_review.py renders/review/open-door.flac renders/review/night-wire-ensemble.flac --wer --out renders/review/comparison.json
```

The optional word check uses a locally cached Whisper model (or `--model` with
its directory); omit `--wer` for signal and size checks only. It verifies the
audio's recorded identity and reads the packet's genome and gestures, without
executing the embedded program. Word recognition is an audition aid: a choir
can be musically effective while making a speech recognizer less certain.
