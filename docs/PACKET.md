# The seed packet (2026-09-26)

A rendition travels as one file. It is an ordinary FLAC that plays in any
player, and it is also a zip archive that carries the program that sang it,
the song's skeleton, the rendition's record and its words. Run it with Python
and it sings a new version of the song, on your computer and your day, as
that version's child. This is milestone 6 of docs/PLAN.md.

The record's `performance` now carries the lead and choir's rounded phrasing
gestures, without recordings or local paths. Children inherit them unless a
new phrasing is supplied; the studio uses them in previews and recordings.
`render --replay` restores these gestures and the final singer and mix,
including their overrides. Old records without a performance still use the
seed's phrasing and warn when an external contribution needs supplying.

The program and model aim for **8 MiB**, excluding the audio: a goal to keep
in mind while the model is trimmed, compressed or quantized (the artist,
2026-09-27), not a wall. It is measured before compression so it stays
meaningful as the model changes; packing warns past the goal and refuses only
absurd sizes (40 MiB, a stray render). It also measures the attached material,
including the genome, learned gestures, lineage and ZIP overhead.
`uv run songbird budget` shows the model, source and remaining room;
`uv run songbird budget --json` supplies exact counts for build checks. The
platform's separately installed Python dependencies are not embedded in this
budget (see setup below).

    uv run songbird render songs/h-now-its-by-you.json --pack --out seed.flac
    python3 seed.flac                 what this is, and what you can do
    python3 seed.flac new             sing a new version here, today (a packet too)
    python3 seed.flac studio          open the studio on this version (once the studio lands)
    python3 seed.flac unpack          unpack everything into a folder
    uv run songbird pack FLAC         attach a packet to a FLAC rendered without one
    uv run songbird unpack FLAC       unpack one

`render --pack` writes the one file and nothing beside it: the record and the
words travel inside. Without `--pack` a render still writes its sidecars
(.json, .score.json, .txt) as before.

## How it works

A zip archive is read from its end: a reader finds the archive's directory in
the last bytes of the file, and the directory says where each entry is. A FLAC
is read from its start, and players stop at the last audio frame. So the
archive is written onto the end of the audio, and each reader sees only its
own part. The archive's offsets are absolute (it is written in place), so
readers need no adjustment for the audio in front of it. Python runs a zip
that has an `__main__.py` at its root, which is why `python3 song.flac` works.

Inside:

| Entry | What it is |
|---|---|
| `__main__.py` | the bootstrap (songbird/bootstrap.py): standard library only |
| `README.txt` | what the file is, in plain words: what it reads, what it keeps, how to run it |
| `manifest.json` | the render record plus the lineage: `id` (SHA-256 of the samples), `generation`, `parent_id`, `ancestry`, and `path`, `gate`, `llm`, `python`, `program_sha256`, `name` |
| `genome.json` | the song's skeleton as sung: tune, refrain, chords, verse bank |
| `lyrics.txt` | the words as sung |
| `requirements.txt` | numpy, scipy, numba, soundfile and cmudict, pinned to the versions it ran with |
| `program/` | songbird/ (source and data: the learned voice's weights travel here) and pyproject.toml |
| `LICENSE` | CC0, with the legal code in full; it also travels as `program/LICENSE`, so every child carries it |

With everything merged (the learned voice's weights, the styles and the new
instruments), the program is 85 files, 5.3 MB unpacked and about 3.4 MB in the
archive. H's seed packet is 16 MB in all. Sung cold from it with `--here`, a
child took 38 s. A rendition's archive is deterministic: the same rendition
packs to the same bytes, with its entries dated by the rendition's own day.
Packing again replaces the archive rather than stacking a second one, and the
audio before it is never touched but for its cover (below).

## Running it

(What running it needs, and the first time as a person meets it:
docs/RUNNING-THE-SONG.md.)

The bootstrap needs nothing but Python (`py` on Windows). For `about` and
`unpack` it only reads the archive and writes nothing else. For `new`, `studio`
(offered only once the program has one) and the program's own commands it
does four things.

1. **Checks the program against its record.** The program inside must hash to
   the record's `program_sha256`, computed from the archive before anything is
   unpacked; otherwise it refuses. This catches a file changed after it was
   made, though not one that was changed consistently. `about` prints the
   program's version and hash. Every version a program sings carries the same
   hash, so a hash published beside the seed lets anyone check a descendant.
2. **Asks first.** It says what it will write and fetch, then asks. `--yes`
   answers in advance; the bootstrap's flags go before the command.
   - where it unpacks, and how much;
   - the dependencies: about 100 MB to download, 250 MB on disk, and with uv
     perhaps a Python too;
   - for `new`: that it reads the computer's languages, size and screen, keeps
     the reduced numbers in `~/.songbird/voice.json`, and writes one FLAC of
     about 15 MB into the current folder.
3. **Unpacks and sets up.** The archive goes into
   `~/.songbird/packets/<the file's own hash>/` (or under `$SONGBIRD_HOME`).
   - *A path of its own choosing.* No field of the record ever picks a path.
     A changed file never runs an old copy.
   - *Checked on the way out.* Every entry must land inside that folder, and
     the whole archive under 100 MB.
   - *Whole or not at all.* It unpacks into a temporary folder that is renamed
     when complete.
   - *The environment,* in `~/.songbird/envs/<hash>/`, with a lock so two runs
     don't build it at once:
     - with uv on the path, uv makes it, with the Python version the rendition
       was made with;
     - without uv, this Python's venv and pip do (Debian and Ubuntu need
       python3-venv);
     - if the pinned versions can't be installed, it tries the newest, and
       says it needs the network once;
     - `--here` skips all of this and uses the running Python as it is.
4. **Runs the program** with the packet as its parent. `new` renders with
   `--parent THIS_FILE --machine here --pack` into the current folder.

The first version made this way on a computer reads it quietly, only its
languages, size and screen (docs/HARVEST.md).
`python3 THIS_FILE.flac songbird harvest --show` reads the rest and shows
exactly what is kept.

**Parents.** `--parent` accepts a packet anywhere it accepted a render record.
A packet is accepted as a parent only if its audio decodes to the samples its
record's id names, so a lineage is never taken on faith. The child's record
gets the next generation, the parent's id and the ancestry. A packet also
packs again from what it carries (`songbird pack PACKET.flac`), and
`songbird pack --parent FILE` supplies a lineage that a record lacks.

**Replaying.** The same program and record give the same samples on the same
platform; on another platform the samples may differ, too little to hear, and
a difference is never carried into later versions: a child's choices come from
its parent's record, not its audio (see variation.Chance). The record's id is
read as written, never decoded again, so a replay elsewhere changes no child.
`songbird render GENOME --replay RECORD` renders again and says how it
compares with the recording (the packet's own audio, or the FLAC beside a
.json record): `matches`, sample for sample; `matches within N steps (largest
difference −X dB)`, at most 64 steps (−54 dB) apart; or where it `differs`,
and then it exits 1.

**Tags.** A rendered FLAC carries Vorbis comments that players show: the song's
title, "The Volunteers" as the artist (songbird/cli.py ARTIST), the day it was sung, and a comment giving its
generation and id and saying the file is also a program. They don't touch the
samples, so the id is unchanged.

**Cover.** Every FLAC the program writes (a render, a packet, the studio's
previews, recording and stems, the browser's render) carries the song's cover as
its front-cover PICTURE block: songbird/cover.jpg (600 by 600, 68 KB, so every
child can embed it too), written by songbird/artwork.py after the Vorbis
comments and before the first audio frame, and before the archive is appended,
so the archive's offsets and the id are untouched (a packet carries about 140 KB
for it: the block and program/songbird/cover.jpg). `pack.with_cover` gives an
older file the cover, its archive kept byte for byte and only moved along;
that is how tools/sing_site.py makes the public seed file from the submitted
render. ffprobe shows it as an attached picture and metaflac lists it; macOS's
Finder and QuickLook show no art for any FLAC (not even one made by metaflac),
so there it shows as a plain audio file.

## Checked

For the seed as a packet, and for a child sung by running the seed cold with a
fresh `SONGBIRD_HOME` (51 s, including setting up the environment from uv's
cache):

- **Players decode every sample, identically.**
  - libsndfile (soundfile);
  - ffmpeg: it prints a complaint about the bytes after the last frame, but the
    samples' SHA-256 is the rendition's id;
  - CoreAudio (afinfo reads it).
- **Unzip tools open it:** Info-ZIP unzip, bsdtar (libarchive), and Python's
  zipfile.
- **Python runs it.**
- **The lineage is right:** the child's manifest has generation 1, the seed's id
  as its parent, and its ancestry.

tests/test_pack.py checks:
- the audio is kept byte for byte;
- the cover: exactly one front cover, the same samples, record and id, the
  studio's strict reader (songbird/received.py) taking the file, a replay
  matching, and an older file given the cover with its archive intact;
- the archive's contents and its manifest;
- packing is deterministic, and packing again replaces the archive;
- a record for other audio is refused;
- the lineage;
- the words, read from the score;
- running the file with Python (`about`, `songbird --help --here`, `unpack`);
- ffmpeg decoding the same samples.

A Fable review (2026-09-26) found the first version's weak points, all fixed
since:
- the unpacked program was keyed by the record's id, so a changed file could
  run an old copy, and a hostile id chose a path;
- it unpacked before asking;
- the prompt understated what it fetches;
- it advertised a studio that didn't exist yet;
- children lost the license text;
- a parent's lineage wasn't checked against its audio.

## Caveats to reconsider

- **The FLAC reference tools object.** `flac -t` and `flac -d` decode every
  sample, then report the archive as lost sync and exit with an error (`flac -d`
  won't write its output unless given `-F`). The players above don't mind.
  - *The plan's alternative:* hold the archive in a FLAC APPLICATION metadata
    block. That is strictly valid FLAC, but it is no longer a zip or a Python
    program, so only `songbird unpack` could open it.
  - *Choice:* the file stays a polyglot.
- **macOS `ditto -x -k` won't open it.** It wants the zip at the file's start;
  Archive Utility may behave the same if the file is renamed to .zip. unzip,
  bsdtar, 7-Zip and Python all read it.
- **Setting up needs the network once.** It fetches the dependencies from PyPI.
  A packet that also carried wheels would be tied to one platform and grow by
  about 100 MB, so it doesn't.
- **Nothing in the file can vouch for itself.** The program hash only proves
  consistency. For trust from outside:
  - *A published hash:* the artist could publish the seed and its program hash
    somewhere stable (songbird.quadule.com, say), plus one line in README.txt
    saying where, so a careful stranger can look it up before running
    anything.
  - *Signing:* signing the program would let the bootstrap refuse modified
    programs, but it sits awkwardly with CC0 and with anyone packing their own
    changes. That's the artist's call.
- **Whether the seed carries its day.** A seed rendered without `--date` has no
  `rendered_at`, so its archive's entries are dated 1980 and its README names
  no day.
