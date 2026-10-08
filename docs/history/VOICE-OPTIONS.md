# Voice options: the artist's voice and generative models

*History: a research memo of September 25, 2026 that led to the learned voice ([THROAT.md](../THROAT.md)).*

Research memo, 2026-09-25. Question: the formant singer (`songbird/synth/voice.py`) is at about 27% word error on the dry Whisper suite (16–17% on the plainer pentatonic songs H and I) and feels like it is hitting a wall. Can we train on the artist's own voice (no singing talent) or bring in a generative model, without giving up what is ours: the score, pitch track with drift, vibrato, timing, phoneme schedule and per-machine `VoiceParams`? The constraints that decide this are principles 1 (the program is the artifact), 4 (the machine is the voice), 8 (nothing identifying leaves the machine) and 9 (offline replay), plus the Synthesis rule "no pretrained audio models" and the LLM-backend pattern for anything external (hosted with a sunset, local option, fallback, recorded).

## 1. The field, September 2026

**Voice conversion over our singer (the model as a throat, ours as the puppet).** RVC is the workhorse: MIT, trains a ~55 MB voice from ">=10min low noise speech", but inference also needs `hubert_base.pt` (190 MB; a HuBERT-family encoder trained on LibriSpeech audiobooks) and `rmvpe.pt` (181 MB), and its base models were trained on "nearly 50 hours ... from the VCTK open source dataset" [1][2][3]. Applio, the maintained fork, adds formant shifting and a "voice blender" that merges two models [4][5]. so-vits-svc is AGPL-3.0 and archived since Nov 2023 [6]. DDSP-SVC (MIT) is the CPU-friendly one but still needs ContentVec, RMVPE and the OpenVPI vocoder [7]. Seed-VC converts zero-shot from a 1–30 s reference through a 200M-parameter DiT plus a Whisper encoder and BigVGAN; GPL-3.0, GPU expected, archived Nov 2025 [8][9]. kNN-VC needs no training at all (5 min of target speech, MIT) but rides on WavLM-Large, 316M parameters trained on 94k h of others' speech [10]; kNN-SVC extended it to singing in 2025 [11]. CPU inference is feasible for all of these (purpose-built small converters reach 2.8x real time on a consumer CPU [42]) but a GPU is the norm.

**Small vocoders and DDSP models trained from scratch on one person.** Magenta's DDSP trained a 6M-parameter harmonic-plus-noise model on "13 minutes of expressive, solo violin", and reports 240k-parameter models that are "less realistic ... but still have fairly high quality" (Apache-2.0) [12][13]. SawSing, a DDSP singing vocoder, trained on "only 3 training recordings and a 3-hour training time" and beat GAN and diffusion vocoders in that low-resource setting [14]; GOLF (MIT) is a differentiable glottal-flow-plus-LPC vocoder, a cousin of our Klatt design, using 14.5–21% of the parameters of other DDSP vocoders and running "an order of magnitude faster" at inference [15][16]. Mel vocoders of the HiFi-GAN V3 (1.5M) or Vocos (13.5M, MIT) class are also routinely trained on about an hour of one speaker [17][18]. These are the only family whose weights are small enough to ship inside a rendition, and they contain nobody's voice but the artist's. They need a controller: what to say, when, at what pitch. We already have one.

**Latent timbre models.** RAVE runs "25x realtime on CPU" at 48 kHz and exposes a latent space you can bias per machine, but it wants 1–3 h of homogeneous audio, days to weeks of GPU training, has no phonetic conditioning (intelligibility rides on how close our input already is), and is licensed CC BY-NC 4.0, which does not sit inside a CC0 artifact [19][20][21].

**Full singing-voice synthesis.** DiffSinger (OpenVPI, Apache-2.0 code) is the community standard: a labelled corpus of the target singer with hand-checked phoneme boundaries, ONNX export, CPU rendering by default in OpenUtau, and the user's own pitch curve as input, so the puppeteer survives; but its NSF-HiFiGAN vocoder weights are CC BY-NC-SA 4.0, fine-tuned on ~72–79 h of contributed singing [22][23][24][25]. NNSVS (MIT) is the small, honest version: time-lag, duration and acoustic models on WORLD features, trained from scratch on corpora the size of Tohoku Kiritan (50 songs, ~57 min) [26][27]. Both need the artist to sing in tune for an hour. The 2026 zero-shot models remove that: SoulX-Singer (Apache-2.0, "42,000+ hours of aligned vocals" from undisclosed singers) takes MIDI or an F0 contour plus lyrics plus a timbre reference [28][29]; YingMusic-Singer (727M parameters, CC BY 4.0 with its VAE under Stability's community license) takes a melody clip, lyrics and a timbre reference [30]. Our formant singer could literally be that melody clip. They are GPU diffusion models built on other people's voices, and none of it travels in a FLAC.

**Hosted APIs.** Eleven Music (about $0.15 per minute) and Google's Lyria 3.5, in the Gemini API since 4 Sept 2026, generate whole songs with vocals from text and lyrics; neither accepts a score, a pitch track or a timing grid [31][32][33]. Suno has no public API [34]. Voice changers are closer to a throat: ElevenLabs' Voice Changer converts 5-minute clips, though its professional clones "do not currently support singing" [35][36]; Kits.AI sells singing conversion from a 10-minute clone, with an API [37]. Any of these could follow the LLM-backend pattern, except that a voice cannot be stored and replayed the way a prompt can: when the server goes dark, the child sings in a different voice.

**No-weights baseline.** WORLD (modified BSD, `pyworld`) analyses speech into f0, spectral envelope and aperiodicity and resynthesises it with any of them changed [38]. UTAU voicebanks are built exactly this way, from a monotone recording list at three or four pitches "three to five semitones" apart [39]; Saitou's 2007 speech-to-singing system did the same with STRAIGHT, controlling f0, duration and spectral envelope [40].

| Approach | Artist records | Borrowed weights (whose voices) | Ships in a rendition? | CPU | License | Maturity | Keeps our puppeteer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RVC / Applio over our singer | 10–60 min speech | HuBERT (LibriSpeech), RMVPE, VCTK base | No: 55 MB + 371 MB | Slow but feasible; GPU norm | MIT | High | Pitch, timing yes; phones blurred |
| DDSP-SVC | ~1000 clips | ContentVec, RMVPE, NSF-HiFiGAN (CC BY-NC-SA) | No | Real-time capable | MIT | Medium, experimental | Same as RVC |
| Seed-VC | 1–30 s, or fine-tune | Whisper, BigVGAN, its own DiT | No: ~1 GB | GPU | GPL-3.0 | Archived 2025 | Same, diffusion seed |
| kNN-VC | 5 min speech | WavLM-Large (94k h), HiFiGAN | No: >1 GB | Slow | MIT | Research | Same |
| **Learned throat** (DDSP / WORLD-envelope model, from scratch) | 45–75 min speech + intoned vowels | None | **Yes: 1–5 MB** | Trivial (numpy) | Ours, CC0 | We build it | Everything, by design |
| RAVE timbre transfer | 1–3 h any audio | None (own training) | Marginal: tens of MB | 25x real time | CC BY-NC 4.0 | High | Pitch loosely; words at risk |
| DiffSinger (OpenVPI) | 1–3 h labelled singing | NSF-HiFiGAN (CC BY-NC-SA) | No: hundreds of MB | Yes (OpenUtau) | Apache-2.0 code | High | Yes via pitch/variance curves |
| NNSVS | ~1 h labelled singing | None with WORLD vocoder | Marginal: tens of MB | Yes | MIT | Medium | Yes if we bypass its predictors |
| SoulX-Singer / YingMusic-Singer | 10 s reference | Everything (42k / 33k h) | No: 2.8 GB | GPU | Apache-2.0 / CC BY 4.0 | New, 2026 | F0 + lyrics in; expression theirs |
| Hosted music APIs | Nothing | Everything | No | n/a | Terms of service | Products | No score, no replay |
| Hosted voice changers | 10 min clone | Everything | No | n/a | Terms of service | Products | Timing yes; not replayable |
| WORLD concatenative (UTAU-style) | 1–2 h monotone reclist | None | A full multi-pitch bank is 50–200 MB; a single-pitch diphone set, compressed, a few MB | Trivial | BSD | Old, proven | Everything |

## 2. Keeping the randomness and the drift

Only two families leave the puppeteer intact. A from-scratch model driven by our control tracks (phoneme schedule, f0, loudness) *is* a throat and nothing else: drift lives in the f0 we hand it, randomness in our noise seeds, and the output is deterministic for a given machine, date and parent, which keeps the golden-render tests. WORLD concatenation is the same with recordings instead of weights. Voice conversion keeps timing exactly (frame-aligned) and pitch closely (RMVPE re-extracts our drifting f0 and follows it), but re-decides phoneme identity through an encoder that has never heard our singer; RVC is deterministic, Seed-VC's diffusion adds a seed we can pin. SVS acoustic models keep our score if we feed them our durations and pitch curve and skip their predictors, which DiffSinger and NNSVS allow; the zero-shot models accept our F0 and lyrics but supply their own ornaments, breaths and dynamics. Hosted song generators discard the genome entirely; drift would exist only in the prompt.

## 3. Fit with the principles

*The program is the artifact.* A 3-minute rendition is about 15 MB of FLAC. A 1–5 MB weight file the program itself trained, with the training code and a provenance record in the manifest, is defensible cargo; 400 MB of third-party encoders is not, and 2.8 GB is a different artwork. PLAN-2026-09-24.md's "no pretrained audio models" should be sharpened to: no third-party weights, ever; weights this program trained on the artist's own voice may ship if small, and the formant voice stays as the fallback throat so every rendition can still be re-sung without them.

*Offline replay.* Anything shipped replays; anything hosted does not, and unlike lyrics the voice cannot be cached as text.

*The machine is the voice.* With a learned throat the machine's vector keeps its current knobs (our LF source: `rd`, `tilt`, `breath`; `tract` becomes a frequency warp of the predicted envelope, exactly as it scales formants today) and gains new ones: an articulation bias on the phoneme embeddings (an accent), and if the artist records two or three deliberate personas, a point in that persona simplex (speaker interpolation within one person). Drift can move these slowly, so a machine's singer ages. RAVE offers latent offsets; RVC offers transpose, Applio's formant shift and model blending, but every conversion tends back toward one target, so two machines risk sounding like one machine on two settings. DiffSinger's voice-colour mixing works but only from recorded modes.

*Nothing identifying leaves the machine.* Pretrained encoders and vocoders are other people's recordings in compressed form (LibriSpeech readers, 109 VCTK speakers, 72 h of contributed singing); they should not travel in every copy of a CC0 song. The artist's own voice model travelling is their choice, consistent with principle 12, and an envelope model that only works when driven by our synthetic source is a far weaker cloning tool than an RVC model, which converts anyone's speech into the artist's. Listener recordings on the ear path must never become training or adaptation data, and the manifest should say so.

## 4. Recommendation

Build the learned throat: a small model of the artist's vocal tract, trained from scratch on their speech, driven by our schedule, our pitch track and our glottal source. Concretely: analyse the recordings with WORLD (pyworld) into f0, spectral envelope and aperiodicity; train a network of 0.3–1M parameters (LSTM or small TCN, torch as a dev-only dependency) mapping per 5 ms frame [current, previous, next phone; position in segment; log f0; loudness] to a 40–60 coefficient envelope plus band aperiodicity; ship the weights as an `.npz` and run inference in numpy behind `VoiceParams(engine="learned")`, since `sing()` already dispatches on `engine`. Excite the predicted envelope with our LF pulses and shaped noise, keeping the rule that raises F1 above a high f0 as a warp. NNSVS proves the recipe (WORLD features, small nets, an hour of one voice); Saitou proved speech-to-singing by envelope and f0 control. RVC is a dev-only yardstick for "how good could it sound", not a component; hosted APIs are out of scope for the voice. Whatever the outcome, WORLD-measured formants and consonant spectra from the recordings can retune the Klatt tables in `phonetics.py`: data, not weights, and a cheap win.

**First experiment.** Record in one quiet room, same microphone, 48 kHz/24-bit mono, 15–20 cm, no processing, keeping raw files. (A) 45–60 min of read speech: the CMU Arctic prompts, 1132 phonetically balanced sentences that take about an hour, set A alone about half [41]. (B) 15 min intoned: each vowel sustained and glided at four reference pitches 3–5 semitones apart across the comfortable range, the program playing the tone; off-key is fine, f0 is measured, not assumed. (C) 10 min: the refrain and seed verses spoken plainly, then intoned on one pitch. About 90 minutes in two sessions; no singing skill enters. Then: day one, a zero-training WORLD baseline that re-pitches and re-times (C) onto our melody, to hear the artist's vowels at sung pitches before any model exists; weeks one and two, align (A)+(B) (Montreal Forced Aligner at dev time, or DTW against our own formant synth as the no-weights aligner), train, export, wire `engine="learned"` and render the refrain on two machine vectors; in parallel, RVC on (A) over the formant voice as the yardstick. Judge with `tools/wer_suite.py --set engine=learned` (dry, then `--mix`) against the formant voice on the same songs (27% across A to G, 16–17% on H and I), aiming to halve it; blind listening with six to ten people on three questions: which of two renditions is the person, transcribe the refrain by ear, and the milestone-3 test, two people or one machine on two settings; plus byte-identical golden renders and under a minute of render time per song on a laptop CPU. Adopt if it wins on error rate and preference and passes the two-machines test; otherwise fold the measurements back into the formant voice.

## Sources

1. [RVC WebUI README](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/blob/main/docs/en/README.en.md): data, VCTK base models, latency
2. [RVC model files and sizes](https://huggingface.co/lj1995/VoiceConversionWebUI/tree/main); [RVC license (MIT)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/blob/main/LICENSE)
3. [HuBERT](https://arxiv.org/abs/2106.07447), [ContentVec](https://arxiv.org/abs/2204.09224), [RMVPE](https://arxiv.org/abs/2306.15412)
4. [Applio documentation](https://docs.applio.org/); [Applio guide with formant shift and voice blender](https://docs.aihub.gg/rvc/local/applio/)
5. [TITAN pretrained (Expresso, 11.15 h)](https://huggingface.co/blaise-tk/TITAN)
6. [so-vits-svc (AGPL-3.0, archived)](https://github.com/svc-develop-team/so-vits-svc)
7. [DDSP-SVC README](https://github.com/yxlllc/DDSP-SVC/blob/master/README.md); [license](https://github.com/yxlllc/DDSP-SVC/blob/master/LICENSE)
8. [Seed-VC README](https://github.com/Plachtaa/seed-vc/blob/main/README.md); [license](https://github.com/Plachtaa/seed-vc/blob/main/LICENSE)
9. [Seed-VC checkpoints and sizes](https://huggingface.co/Plachta/Seed-VC/tree/main)
10. [kNN-VC](https://github.com/bshall/knn-vc); [WavLM](https://arxiv.org/abs/2110.13900)
11. [kNN-SVC (2025)](https://arxiv.org/abs/2504.05686)
12. [DDSP paper](https://arxiv.org/abs/2001.04643)
13. [magenta/ddsp (Apache-2.0)](https://github.com/magenta/ddsp)
14. [SawSing](https://arxiv.org/abs/2208.04756)
15. [GOLF, TISMIR](https://transactions.ismir.net/articles/10.5334/tismir.210)
16. [GOLF code (MIT)](https://github.com/yoyololicon/golf)
17. [HiFi-GAN](https://arxiv.org/abs/2010.05646)
18. [Vocos (MIT, 13.5M)](https://github.com/gemelo-ai/vocos)
19. [RAVE license (CC BY-NC 4.0)](https://github.com/acids-ircam/RAVE/blob/master/LICENSE); [RAVE README](https://github.com/acids-ircam/RAVE)
20. [ACIDS projects: 25x realtime on CPU](https://acids-ircam.github.io/projects/)
21. [IRCAM tutorial on training RAVE](https://forum.ircam.fr/article/detail/training-rave-models-on-custom-data/); [Neural Analog RAVE notes](https://neuralanalog.com/docs/rave-model-ircam)
22. [OpenVPI DiffSinger (Apache-2.0)](https://github.com/openvpi/DiffSinger); [Best Practices](https://github.com/openvpi/DiffSinger/blob/main/docs/BestPractices.md)
23. [OpenVPI community vocoders, CC BY-NC-SA 4.0, training data](https://openvpi.github.io/vocoders/)
24. [OpenVPI dataset tools](https://github.com/openvpi/dataset-tools)
25. [OpenUtau DiffSinger support: CPU rendering, pitch curve, voice colours](https://github.com/stakira/OpenUtau/wiki/DiffSinger-support)
26. [NNSVS (MIT)](https://github.com/nnsvs/nnsvs); [NNSVS paper](https://arxiv.org/abs/2210.15987)
27. [Tohoku Kiritan singing database](https://www.jstage.jst.go.jp/article/ast/42/3/42_E2074/_pdf)
28. [SoulX-Singer paper](https://arxiv.org/html/2602.07803); [code and weights](https://github.com/Soul-AILab/SoulX-Singer)
29. [SoulX-Singer checkpoints](https://huggingface.co/Soul-AILab/SoulX-Singer/tree/main)
30. [YingMusic-Singer paper](https://arxiv.org/html/2603.24589v3); [code, weights, license](https://github.com/ASLP-lab/YingMusic-Singer-Plus)
31. [Eleven Music pricing](https://help.elevenlabs.io/hc/en-us/articles/37821528996497-How-much-does-Eleven-Music-cost); [composition plan API](https://elevenlabs.io/docs/api-reference/music/create-composition-plan)
32. [Lyria 3.5 in the Gemini API](https://ai.google.dev/gemini-api/docs/music-generation)
33. [Lyria 3 for developers](https://blog.google/innovation-and-ai/technology/developers-tools/lyria-3-developers/)
34. [Suno API partner programme](https://www.digitalmusicnews.com/2026/07/03/suno-is-opening-an-api-partner-program/)
35. [ElevenLabs Voice Changer](https://elevenlabs.io/docs/eleven-creative/playground/voice-changer)
36. [ElevenLabs professional voice cloning: speech only](https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning/professional-voice-cloning)
37. [Kits.AI API](https://www.kits.ai/api)
38. [WORLD vocoder (modified BSD)](https://github.com/mmorise/World)
39. [UTAU multipitch recording](https://utau.us/multipitch.html)
40. [Saitou et al., speech-to-singing with STRAIGHT (Interspeech 2007)](https://www.isca-archive.org/interspeech_2007/saitou07_interspeech.html); [AlignSTS (2023)](https://arxiv.org/abs/2305.04476)
41. [CMU ARCTIC databases](http://festvox.org/cmu_arctic/cmu_arctic_report.pdf)
42. [Singing Voice Conversion Challenge 2025](https://arxiv.org/pdf/2509.15629); [LLVC: real-time VC on CPU](https://arxiv.org/pdf/2311.00873)
