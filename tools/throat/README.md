# The learned throat

How songbird/synth/throat.npz, the voice that sings the song, was made (docs/THROAT.md). Not needed to run the
song: every rendition carries the finished model.

The model was trained in three steps: SoulX-Singer singing our scores in ten house timbres prompted by our own
formant singer; one fine-tune on the volunteers' takes together (their recordings were deleted on September 30,
so that step can't be run again); and a retrain from that model with Scylla's Band singing our schedule beside the
house corpus.

To make a corpus you need, besides this checkout:

- SoulX-Singer (https://github.com/Soul-AILab/SoulX-Singer), a checkout with its venv and pretrained models,
  named by `SOULX`. It sings the house corpus; its venv's torch also trains the model.
- The Montreal Forced Aligner and its english_us_arpa model, named by `MFA_HOME` (or `MFA` for its wrapper), to
  label the house corpus.
- Scylla's Band (https://github.com/lowkeytea/scyllasband), a checkout with its venv, named by `SCYLLA`. Its
  labels are what it was told to sing, so it needs no aligner.

The house corpus, in order:

1. corpus.py: the plan, which house singer sings what.
2. soulx_batch.py (in SoulX-Singer's venv): the corpus, sung (soulx.py turns our notes into its metadata).
3. update.sh: features.py (WORLD analysis), phones.py (MFA), check.py, dataset.py.

Scylla's Band, and the model:

1. scylla.py: the plan; scylla_batch.py (in Scylla's venv): the corpus, sung.
2. features.py, check.py and dataset.py on it; subset.py and `folk.py merge` join it to the house corpus, keeping
   the shipped model's volunteers row by name.
3. train.py --init songbird/synth/throat.npz (with torch): the model. retire.py sets which singers a model draws.

To listen and measure: listen.py, judge.py, gemini_judge.py, copysynth.py, vocoder_eval.py, oracle.py,
stop_release.py, unseen.py and fit_unseen.py.
