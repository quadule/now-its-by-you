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
uv run pytest
```

## Layout

`songbird/` follows the pipeline: `genome` (the persistent skeleton; tunes are
written as scale degrees on a rhythmic grid), `realize` (genome plus parameters
to a timed score), `synth/` (plucked string, LF glottal source, Klatt-style
tract, singing voice, room, mastering), `phonetics` (CMU dictionary to sung
syllables). `harvest`, `drift`, `lyrics`, `gate` and `pack` are the later
milestones and only describe their interfaces so far.

## Checking a render without ears

- `tools/analyze.py renders/<name> [--part voice]` tracks pitch against the score and draws it.
- `tools/voiceview.py renders/<name>` draws the voice's spectrogram with every phoneme labelled.
- `tools/mixview.py renders/<name>.flac` shows mix balance and flags clicks.
- `tools/wer_suite.py [--mix] [--seeds 3] [--set field=value]` sings every lyric in
  `songs/` and scores intelligibility with Whisper (dev-only; downloads the base.en model).

Code and seed are dedicated to the public domain (CC0).
