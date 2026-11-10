# Tools

None of these is needed to play, run or change the song: that is `songbird` (the program in songbird/) and the
studio. These are how the song was made and checked. Each says what it does at the top of the file and in
`--help`.

## Ships with the web studio

studio.itsby.you carries these as they are, so they stay where they are
(web/studio-wasm/tools/sing_bundle.py, build_site.py, build_render.py):

- phrasing.py, speech_to_song.py, align.py, takes.py, guides.py, intelligibility.py, wer_suite.py: the Sing view
  measures a sung take with them.
- karaoke_words.py, karaoke.js, karaoke-recorder.js: the words in time, the sing-along, the recorder.
- sets/h-now-its-by-you.json: what guides.py asks a singer to sing.

Beside them: released_guide.py and piano_score.py make webstudio/released.json and web/piano/score.json; released_record.py keeps the newest edition's record as webstudio/released-record.json (the web studio opens on it);
sing_site.py builds the page at now.itsby.you. The studio on your computer sings through karaoke.py (with
karaoke.html and everyone.py).

## Checking a render

- Sound: analyze.py, voiceview.py, mixview.py, mixcheck.py, mixmeter.py, hisscheck.py, stylemeter.py, discmeter.py.
- Words: wer_suite.py, intelligibility.py, pronounce.py.
- Listening: packet_review.py, excerpt.py, evolution.py, styles_examples.sh.
- Instruments: band_solos.py, instrument_solos.py, instrument_solos_b.py (with instrument_phrases_b/),
  instrument_levels.py.
- Time and memory: kernel_time.py, render_memory.py, part_memory.py.
- The tune: round_fit.py.
- video/: the filmed studio session (docs/history/STUDIO-EDM-TEST.md).

## How the voice was made

- throat/: the learned throat, trained on SoulX-Singer's renders of the project's own songs (its README says what
  it needs).
- phrasing_eval.py, recording_sets.py, delivery.py, fit_postures.py.

## The cover

- cover/: the album cover (now-its-by-you.png at the top of the repo). woodcut.py cuts the daisy, face.py prints
  the packets' faces, concrete.py makes the stone, scene.py builds and renders it all in Blender, finish.py
  makes the release sizes and reads the QR back; blender_link.py and send.py build it in an open Blender while
  you watch.

## Archive

archive/ keeps the record of how the first version was made; nothing runs it now.

- archive/reference-voices/: tts.py, reference.py, music_takes.py. Reference singers from ElevenLabs and Gemini
  for checking the phrasing extractor (docs/history/PHRASING-CALIBRATION.md). They need ELEVENLABS_API_KEY or
  GEMINI_API_KEY.
- archive/volunteers-2026/: hard_notes.py, volunteers.py, clean_takes.py. They read the takes people sang in
  September 2026, which were deleted on September 30, 2026. hard_notes.py's test runs with
  `uv run pytest tools/archive/volunteers-2026`.

Still in place until the singing site retires: invite.py, versions.py and measure.py, from the September 2026
invitations to sing.
