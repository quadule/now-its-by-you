# s09b_bass and s08b_harp: their data

## data/bass/ (prep/bass.py)

`uv run python tools/promo/video/prep/bass.py` from the repo root (a few seconds).

The bowed bass ("bowedbass", the stage's twin of the whistle two octaves down, plain) is synth/cello.py's upright bass
under the bow, on bowed.run_primed. The script lays the stage edition as the replay does (common.laid), runs
synth.stem_jobs' "bowedbass" job alone with run_primed's calls kept, asserts the stem equals the replay's
(scratch/replay/render.bowedbass.wav, audio id 8660c5b6af71) sample for sample, and asserts an instrumented copy of
run_primed gives the engine's output bit for bit. replay.py is unchanged.

| file | what |
|---|---|
| `bass.json` | per window (`breath3`, `tag`): t0, t1, frames, the samples where a stroke primed the string, the notes (song seconds, pitch as played) |
| `<window>-period` | float32 [frames, 16, 2, 96], 60 a second from t0: at each video frame 16 snapshots over one period, [displacement, velocity] at 96 places from the bridge (0) to the nut, as physics/bow-period is for the fiddle |
| `<window>-tracks` | float32 [rows, 5], 240 a second: bow velocity, bow force (grip), bow position (fraction of the loop from the bridge), pitch Hz, bridge force |

The waves are read off the two delay lines as physics.py's `string_at` reads the fiddle's, with the loss filter's
delay a track (run_primed's pole moves note by note) and the lines' contents as their reads find them (a stroke's
priming lays the motion down whole, so within one period before each primed sample the picture already shows it).

s08b_harp also reads `physics/pluck-harp` and its notes (re-run in the browser, strings.js), `s08/mix-bands` (the
ember's glow, as s08_lineage) and s08_lineage's tree (the ember's place).
