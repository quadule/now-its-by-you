# The learned throat

How songbird/synth/throat.npz, the voice that sings the song, was made (docs/THROAT.md). Not needed to run the
song: every rendition carries the finished model.

To make it again you need, besides this checkout:

- SoulX-Singer (https://github.com/Soul-AILab/SoulX-Singer), a checkout with its venv and pretrained models,
  named by `SOULX`. It sings the corpus; its venv's torch also trains the model.
- The Montreal Forced Aligner and its english_us_arpa model, named by `MFA_HOME` (or `MFA` for its wrapper).

In order:

1. corpus.py: the plan, which synthetic singer sings what.
2. soulx_batch.py (in SoulX-Singer's venv): the corpus, sung (soulx.py turns our notes into its metadata).
3. update.sh: features.py (WORLD analysis), phones.py (MFA), check.py, dataset.py.
4. train.py (with torch): the model.

To listen and measure: listen.py, judge.py, copysynth.py, vocoder_eval.py, oracle.py.
