# Overnight, 2026-10-07 to 08: new house singers from our own voice

The artist, after choosing the recipe: "Train on my desktop with the 4080 Super", then "keep going with this
overnight". Everything is on branch `claude/singing-synthesis-exploration-c0bf8c` in atomic commits; nothing is
merged into main, pushed, deployed or shipped. The shipped voice (songbird/synth/throat.npz) is unchanged.
docs/THROAT.md "New house singers from our own voice" has the method and the numbers. Full suite on the branch:
2013 passed, 1 failed (tests/test_invite.py's time-dependent fixture, fixed on main since by 0ab1383; main has moved on,
so merging this branch takes that fix).

## Listen first

1. **renders/ym-listen/model-1..5** (dry, about a minute each): H's wire verse, refrain and screen verse, the same
   notes, timing and seed, sung by 1 the shipped voice, 2 A-320, 3 B-320, 4 A-160, 5 B-160.
   - A = trained on the old house corpus and the new one (the old rows kept for their consonants, never drawn).
   - B = the new corpus alone.
   - 320 = round 3's bigger network; 160 = today's size.
2. **renders/ym-listen/full/song-1..5**: the first published version in full, with the band, the same five voices.

The choice is by ear. The numbers below don't separate them.

## What the numbers say

- **Words:** all within noise of each other on H (8.0-9.1% misheard over 438 words, the shipped voice 9.1%).
- **Size:** the bigger network's weights are 13.8 MB against the packet's 8 MiB goal for program and model
  (6.63 MiB today). It costs only 23% more time on one core, but it won't travel in the FLAC unless its weights
  go to 8 bits. **If 2 or 3 isn't clearly better than 4 or 5, take a 160.**
- **Variety:** the new singers all carry 0.3-0.6 of the one people's row, so machines' blends in H's register sit
  closer together (0.44 dB median apart against 0.74; other per-machine settings unchanged). Low voices keep their
  distance.

## Decisions to reconsider

- **The volunteers' share, 0.3-0.6** (the artist's range) is spread across the ten singers so that high and low
  voices both get the whole range; Fable had suggested tying it to register (0.3 high, 0.6 low), and the artist's
  ears preferred 0.6 on a high voice, so I didn't.
- **Re-sung once for every lower voice**, once or twice alternating for the high ones (the artist: the bass re-sung
  twice "sounds less natural").
- **No volunteers row in the new models.** The people's share lives in every singer, so `HUMAN_SHARE` no longer
  applies; an older version whose blend names `volunteers` or a `house-*` row would sing the new default
  instead in B (in A, the house rows are still there, retired). To ship, the studio and the packet need nothing
  else: `throat.drawn` already keeps retired rows out of every blend.
- **The 0.45 cap** on any one house row in a new singer's blend: the single-row prompts were "a step backward";
  a higher cap would widen the high voices' variety. Untested.
- **The folk branch is merged into this branch** (for `train.py`'s critic, spread and widening); it touches only
  dev tools, docs and tests.

## Where things are

- **This Mac:** YingMusic-Singer at ~/Code/svs/YingMusic-Singer (its venv; scipy pinned 1.13.1; espeak-ng from
  Homebrew). New prompts in renders/throat/ying/; the corpus in renders/throat/corpus/blend-*; datasets
  renders/throat/dataset-blendA.npz (285 min) and dataset-blendB.npz (142 min); models and training logs in
  renders/throat/blend-models/.
- **The desktop (cachy):** the branch as a separate worktree at ~/Code/songbird-throat (the main checkout is
  untouched), a CUDA venv `.venv-train` there, the datasets and models in its renders/throat/. Its tmux sessions
  `throat` and `throat2` have finished.
- **Not committed:** renders (gitignored), the scratch scripts that made the listening files.

## Next, when the artist has listened

1. Pick a model; copy it to songbird/synth/throat.npz, regenerate the golden renders, run the full suite once.
2. If a 320 wins: weights to 8 bits and a check that it still sings the same.
3. Possibly widen the high voices (a higher cap, or tract warps in the prompts) and retrain.
4. Deploy the studio when the artist asks.
