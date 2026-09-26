# The seed packet (2026-09-26)

A rendition travels as one file. It is an ordinary FLAC that plays in any
player, and it is also a zip archive that carries the program that sang it,
the song's skeleton, the rendition's record and its words. Run it with Python
and it sings a new version of the song, on your computer and your day, as
that version's child. This is milestone 6 of docs/PLAN.md.

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
| `LICENSE` | CC0 |

The program adds about 0.2 MB, compressed; the learned voice's weights will add
a few MB more. A rendition's archive is deterministic: the same rendition
packs to the same bytes, with its entries dated by the rendition's own day.
Packing again replaces the archive rather than stacking a second one, and the
audio before it is never touched.

## Running it

The bootstrap needs nothing but Python. For `about` and `unpack` it only reads
the archive. For `new`, `studio` and the program's own commands it:

1. **Unpacks.** The packet goes into `~/.songbird/packets/<id>/`, or under
   `$SONGBIRD_HOME`.
2. **Makes an environment.** It asks first, because this fetches about 150 MB
   from PyPI into `~/.songbird/envs/<hash>/`; `--yes` skips the question.
   - *With uv on the path:* uv makes the environment, with the Python version
     the rendition was made with.
   - *Without uv:* this Python's venv and pip make it.
   - *If the pinned versions aren't available:* it tries the newest.
   - *`--here`:* skips all of this and uses the running Python as it is.
3. **Runs the program** with the packet as its parent. `new` renders with
   `--parent THIS_FILE --machine here --pack` into the current folder.

The first version made this way on a computer reads it quietly, only its
languages, size and screen (docs/HARVEST.md); `songbird harvest --show` reads
the rest and shows exactly what is kept.

`--parent` accepts a packet anywhere it accepted a render record, and the
child's record gets the next generation, the parent's id and the ancestry.

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
- the archive's contents and its manifest;
- packing is deterministic, and packing again replaces the archive;
- a record for other audio is refused;
- the lineage;
- the words, read from the score;
- running the file with Python (`about`, `songbird --help --here`, `unpack`);
- ffmpeg decoding the same samples.

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
