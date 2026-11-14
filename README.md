# Now It's by You

A folk song whose audio file is also the program that sings it. By The Volunteers; the program is called Songbird.

> *Now It's by You* is a folk song passed between people and computers that explores music's ability to take on a
> life of its own, in verse and by embedding the software that sang it.
>
> Run the program and you get a new version of the song, shaped by your computer and the season. Sing into it and it
> learns a little of your timing and inflection (your recording is deleted right after, and your voice is never
> cloned). The piece confronts the blurred authorship of AI music through the lens of folk music and oral
> tradition: it wonders who made it, and invites you to take part.
>
> — Milo Winningham

## What it is

A version is one FLAC file. A music player reads it from the front and plays it; a zip tool reads it from the back
and finds the program that sang it, the song's skeleton, the version's record and its words. Python runs it:

```
python3 now-its-by-you.flac          what this is, and what you can do
python3 now-its-by-you.flac new      sing a new version here, today
python3 now-its-by-you.flac studio   change it, and make your own version
```

It needs Python 3.11 or newer, or uv ([docs/RUNNING-THE-SONG.md](docs/RUNNING-THE-SONG.md)). The first run fetches
the program's libraries once (about 100 MB) and asks before it writes; after that nothing goes over the network.

Every run sings a new version. The shape of the tune, its stresses, its chords and the refrain's words never change.
The key, mode, tempo, form, style, band and singer are chosen each time from a few plain facts about the computer
(its languages, its size, its screen: `songbird harvest --show` prints what is kept) and from the date, through a
slow drift: a little day to day, most year to year. The new version is the child of the one it was run from: it
keeps its parent's choices, pulled part of the way toward its own machine's, and the singers of the versions before
it, up to six, sing harmony in the bridge. Small liberties with the tune and a swapped verse travel down a lineage
the same way. The words come from the song's own bank of verses; there is no language model in it, and it calls no
service.

For musicians, the studio (`studio` above, or https://studio.itsby.you in a browser) puts the whole song on one
page: melody, words and their alternatives, key, tempo, style and mix. At studio.itsby.you you can also sing
along: your version takes your timing, holds, loudness and the way your pitch moves, never your voice, and the
recording is measured on your device and deleted. What you export is a file like the one you started from, program
inside, so anyone can run it, or open it in the studio by a link, and carry on.

For programmers, `songbird/` follows the pipeline: genome, harvest, drift, realization, words, band, synthesis
(physical models for the instruments; a small learned voice in numpy), phonetics and packing. It runs on numpy,
scipy, numba, soundfile and cmudict, fits in a few megabytes beside the audio, and the same record renders the same
samples again on the same kind of computer. The rest of this README says how to build, run and test it.

## Listen, make your own, read the code

- **Listen:** https://now.itsby.you plays the current version, to listen to or take; the first, from
  September 28, 2026, is kept there too.
- **Read about it:** https://now.itsby.you/about says why it is a folk song, how it was made and who is in it.
- **Make your own:** https://studio.itsby.you, with nothing to install: the whole studio runs in your browser, on
  your device. Or `python3 now-its-by-you.flac studio` on your own computer.
- **Read the code:** this repository. [docs/README.md](docs/README.md) is the map of the documentation:
  [what the file is](docs/PACKET.md), [what the program reads from a computer](docs/HARVEST.md),
  [how versions drift](docs/EVOLUTION.md), [how the voice was made](docs/THROAT.md), and more.

## How it was made

The program and the song were written by the artist with commercial AI models as collaborators, in conversation.
Claude (Anthropic's Opus 5.5 and Fable 5.1, through Claude Code) wrote most of the code and drafted most of the
documents; each commit it helped write says so in a Co-Authored-By line. Gemini reviewed the lyrics, contributed
verses and a couplet on a branch and mocked up the cover; Codex contributed a branch (performances travelling inside
the file). The voice was taught, not recorded: SoulX-Singer, an open singing model, sang the project's own scores in
timbres the program itself proposed, a small model learned from that, and it was then fine-tuned once on the eight
volunteers' takes together, as one singer. For the performance version (November 2026) it was taught again, with
Scylla's Band, another open model, as a second teacher ([docs/THROAT.md](docs/THROAT.md)). Synthetic voices from ElevenLabs were used only as a benchmark; nothing
trained on them ships. Whisper and the Montreal Forced Aligner scored intelligibility and aligned syllables during
development; none of these tools is in the file. What ships runs offline on an ordinary computer.

## Credits

Eight people sang into the first version, in September 2026; [CREDITS.md](CREDITS.md) names the six who asked to be
named. Their recordings were deleted by September 30, 2026; what the song keeps from them is how they sang, as
numbers, and what its voice learned of the words from them.

## License

The song, the program and every version are dedicated to the public domain under [CC0 1.0](LICENSE). The license
travels inside every file the program writes. The exception is WORLD, in web/studio-wasm/world/, under its own
modified BSD license (its LICENSE.txt); [THIRD-PARTY.md](THIRD-PARTY.md) lists what studio.itsby.you serves beside
the program, and under which licenses.

## Contact

Questions, or something to report (a shared version included): milo@winningham.net.

---

## Running it from this repository

You need [uv](https://docs.astral.sh/uv/), which fetches Python and the libraries.

```
uv sync                                                                      # the libraries and the development tools
uv run songbird render songs/h-now-its-by-you.json                           # renders/h-now-its-by-you.flac: the seed, no computer's or day's choices
uv run songbird render songs/h-now-its-by-you.json --machine fictional:ada   # sung by a made-up computer, today
uv run songbird render songs/h-now-its-by-you.json --machine here --date 2026-12-25 --pack   # by this one on a day, program inside
uv run songbird harvest --show                                               # what it reads from this computer: all that is kept
uv run songbird year songs/h-now-its-by-you.json --machine fictional:ada     # one computer's choices through a year
uv run songbird studio                                                       # the studio, on this computer only
uv run songbird budget                                                       # the program and its voice against the 8 MiB goal
uv run songbird --help                                                       # every command, among them pack and unpack
```

Every song in [songs/](songs/README.md) renders the same way, and [editions/](editions/README.md) has three
arrangements of the song made by hand. The program and its voice are meant to fit in 8 MiB beside the audio;
`songbird budget` reports their size (6.63 MiB on October 7, 2026), and packing warns past it.

## The studio, here and on the web

`uv run songbird studio` opens today's version in a page on this computer (127.0.0.1 only): the whole song as one
score, its words and their alternatives, key, tempo, style, band and mix, six years of how it drifts, and an export
that makes a version with the program inside ([docs/STUDIO.md](docs/STUDIO.md)). Give it a version's file to carry
on from: `uv run songbird studio song.flac`. With `--web-singing` it takes singing too, measured on this computer
([docs/WEB-SINGING.md](docs/WEB-SINGING.md)).

At https://studio.itsby.you the same studio is the program's own Python under Pyodide, its compiled loops
translated to JavaScript and WebAssembly. To build that site and try it here (with Node; the build fetches Pyodide
once):

```
uv run python web/studio-wasm/tools/build_site.py renders/studio-site
uv run python web/studio-wasm/tools/serve_site.py renders/studio-site        # http://127.0.0.1:8820
```

[docs/WEB-STUDIO.md](docs/WEB-STUDIO.md) says how it works and how it is hosted (web/studio-site, a Cloudflare Worker).

## Tests

```
uv run pytest                                                # the program, the studio and the tools
node --test tests/*.test.cjs tests/test_studio_drafts.cjs    # the studio's page
(cd web/studio-site && npm test)                             # the Worker behind studio.itsby.you
(cd web/sing && npm test)                                    # the Worker behind now.itsby.you
```

Some tests skip unless something more is here:

- **Node and Pyodide** (`npm ci` in web/studio-wasm): measuring a sung take and answering the studio's first
  questions under Pyodide, as the browser does (test_sing_measure.py, test_studio_quick_start.py); Node alone runs
  test_world_wasm.py.
- **ffmpeg**: another player decoding a version to the same samples (test_pack.py), and the singing site's guides
  (test_sing_site.py).
- **The first version's file**, from https://now.itsby.you, saved as renders/review/contest.flac: its piano score
  made again byte for byte (test_piano_score.py).
- **The home page's seed** (web/sing/public/seed/, built by tools/sing_site.py), or `SONGBIRD_SEED=path/to/a.flac`
  for `npm test` in web/studio-site: the Worker reading a real version.

The golden tests (tests/golden/) hold the program to the samples it made on the artist's Mac; on another kind of
computer the samples may differ in the last bit ([docs/PACKET.md](docs/PACKET.md), "Replaying").

## The code

- `songbird/`: the program, which travels inside every version. `genome` is the song's skeleton (tunes as scale
  degrees on a rhythmic grid); `harvest` reduces a computer's facts to a voice ([docs/HARVEST.md](docs/HARVEST.md));
  `drift` is time as a smooth noise field; `realize` and `variation` pull the parent's choices toward this
  computer's as the drift moves them; `evolve` and `variants` change the tune and words down a line
  ([docs/EVOLUTION.md](docs/EVOLUTION.md)); `arrange` draws the words from the bank
  ([docs/ARRANGE.md](docs/ARRANGE.md)); `band` and `style` say who plays what, and how
  ([docs/BAND.md](docs/BAND.md), [docs/STYLES.md](docs/STYLES.md)); `synth/` holds the instruments, physical models
  in their bodies, the voice and its learned throat ([docs/THROAT.md](docs/THROAT.md)), the room and the master;
  `phonetics` turns the CMU dictionary into sung syllables; `pack` and `bootstrap` make the file that plays and runs
  ([docs/PACKET.md](docs/PACKET.md)); `studio.py` and `studio/` are the studio.
- `songs/`: the song and the candidates it was chosen from. `editions/`: three arrangements made by hand.
- `webstudio/`: singing in the studio, measuring a take; it never travels in a version.
- `web/studio-wasm/`: the program in the browser (the Pyodide build, the compiled loops in JavaScript and
  WebAssembly, the static site's build). `web/studio-site/`: the Worker that serves studio.itsby.you. `web/sing/`:
  now.itsby.you, and the site singers used in September 2026. `web/piano/`: the piano page
  ([docs/PIANO.md](docs/PIANO.md)).
- `tools/`: what was used to make and check the song and its voice ([tools/README.md](tools/README.md)). `tests/`.
- `deploy/studio/`: a container for serving the studio from a server, the first plan, never deployed.
- `docs/`: the documentation ([docs/README.md](docs/README.md)).

## Checking a render without ears

- `tools/analyze.py renders/<name> [--part voice]` tracks pitch against the score and draws it.
- `tools/voiceview.py renders/<name>` draws the voice's spectrogram with every phoneme labelled.
- `tools/mixview.py renders/<name>.flac` shows mix balance and flags clicks.
- `tools/band_solos.py songs/<name>.json --plots` renders each instrument of the band alone, playing its part.
- `tools/wer_suite.py [--mix] [--seeds 3] [--set field=value]` sings every lyric in `songs/` and scores
  intelligibility with Whisper (it downloads the base.en model).
- `tools/packet_review.py PACKET.flac ... [--wer] [--out report.json]` compares finished versions: loudness,
  range, true peak, mono power, payload size, and optionally word recognition with a cached local Whisper model.
