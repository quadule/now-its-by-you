"""Singing in the web studio: a visitor sings to a guide in the browser, the take is measured on the server and
its audio deleted, and the song is sung their way (docs/WEB-SINGING.md).

Not part of the song's program: nothing here goes into a packet (songbird/pack.py packs songbird/ alone), and
the studio imports it only when asked to take singing in the browser (`songbird studio --web-singing`). It
reuses the dev tools that measure a take (tools/phrasing.py, tools/guides.py, tools/karaoke.js), which need
the dev dependencies (pyworld, librosa), in a worker process of its own.

    kit.py       where the singing kit's files are (guides, words, the template singer's analyses)
    prepare.py   makes the kit, on a computer with the memory for it (python -m webstudio.prepare)
    worker.py    the measuring process: one take at a time, its audio only in a temporary file
    singing.py   the studio's side: the page's routes, the queue, the phrasings kept by fingerprint
    sing.js      the page's side, with sing.css: consent, singing to the guide, the take measured
"""
