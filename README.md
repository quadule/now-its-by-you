# Songbird

A folk song whose real artifact is the program that sings it. Each rendition is
an audio file with this program embedded inside it; running the program on a
rendition sings a new one, in the voice of the machine it runs on, shaped by the
moment it was run. The design is in [docs/PLAN.md](docs/PLAN.md); the seed song
is still being written: every candidate, with lyrics, ratings and a bank of
lines to reuse, is in [songs/](songs/README.md).

Status: prototype. Milestone 1 (genome and deterministic plucked-string render)
is done; milestone 2 (the formant voice) sings and is being tuned.

```
uv sync
uv run songbird render songs/b-coal-from-the-fire.json            # renders/b-coal-from-the-fire.flac
uv run songbird render songs/b-coal-from-the-fire.json --form refrain --stems \
    --voice tract=1.0 shift=-12                                               # a lower singer, parts as WAVs
uv run songbird harvest --show                                     # this machine's voice, exactly what is kept
uv run songbird render songs/h-now-its-by-you.json --machine here --date 2026-12-25  # sung by this machine that day
uv run songbird render songs/h-now-its-by-you.json --machine fictional:ada           # by a made-up machine, now
uv run songbird year songs/h-now-its-by-you.json --machine fictional:ada             # its choices through a year
uv run songbird studio                         # your version today: see how it's made, change it, record it
uv run pytest
```

The studio ([docs/STUDIO.md](docs/STUDIO.md)) is a page on this computer
only: a whole-song timeline and melody editor, word alternates directly in the
lyrics, original lyric writing with syllable checks, a small mixer, instant melody
sketches, and the finished recording. Undo, saved drafts, and the song's musical
rules make room to experiment. Explore six years of the machine's song or compare
other machines; your edits travel with the audio.
A rendition opens it on itself: `python3 song.flac studio`.

## Layout

`songbird/` follows the pipeline: `genome` (the persistent skeleton; tunes are
written as scale degrees on a rhythmic grid), `harvest` (the machine's context
reduced to a voice: [docs/HARVEST.md](docs/HARVEST.md) lists exactly what is
read), `drift` (time as a smooth noise field), `realize` (genome plus
parameters to a timed score; `variation` is the table by which the parent's
parameters pull toward the voice as the drift moves them), `arrange` (the
words, drawn from the song's bank: [docs/ARRANGE.md](docs/ARRANGE.md)), `band`
(who in the band plays what, section by section: [docs/BAND.md](docs/BAND.md)),
`synth/` (the band's instruments: plucked, bowed, blown, struck and reed
models in their bodies; the singer: LF glottal source and Klatt-style tract,
or the learned throat of [docs/THROAT.md](docs/THROAT.md); room, mastering),
`phonetics` (CMU dictionary to sung syllables). `lyrics`, `gate` and `pack`
are the later milestones and only describe their interfaces so far.

## Singers

A person's phrasing comes from takes they sing along to a guide: the tune
alone on a whistle over a quiet pulse, the whole song, or the machine's singer.
`uv run python tools/karaoke.py songs/h-now-its-by-you.json` records them on
this computer; singers anywhere use the same page behind one-time links, on
Cloudflare ([docs/SING-ONLINE.md](docs/SING-ONLINE.md)). Takes stay in
`recordings/`, never in git; [docs/SINGERS.md](docs/SINGERS.md) is the brief
and release for singers.

## Checking a render without ears

- `tools/analyze.py renders/<name> [--part voice]` tracks pitch against the score and draws it.
- `tools/voiceview.py renders/<name>` draws the voice's spectrogram with every phoneme labelled.
- `tools/mixview.py renders/<name>.flac` shows mix balance and flags clicks.
- `tools/band_solos.py songs/<name>.json --plots` renders each instrument of the band alone, playing its part.
- `tools/wer_suite.py [--mix] [--seeds 3] [--set field=value]` sings every lyric in
  `songs/` and scores intelligibility with Whisper (dev-only; downloads the base.en model).

Code and seed are dedicated to the public domain (CC0).
