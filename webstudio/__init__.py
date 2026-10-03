"""Singing in the web studio: a visitor sings the version on the page to a guide, the take is measured (in their
own browser on the device, or on the server) and its audio let go, and the song is sung their way
(docs/WEB-SINGING.md).

Not part of the song's program: nothing here goes into a packet (songbird/pack.py packs songbird/ alone), and
the studio imports it only when asked to take singing in the browser (`songbird studio --web-singing`, or the
site built for the device). It reuses the dev tools that measure a take (tools/phrasing.py, tools/guides.py,
tools/karaoke.js), which need the dev dependencies (pyworld, librosa), in a worker process of its own.

    guide.py     what is sung to: the version on the page (or the released one) as a guide, its words, its melody
    kit.py       where what measuring needs is kept: guides, the template singer's analyses, made as needed
    worker.py    the measuring process: one take at a time, its audio only in a temporary file
    singing.py   the studio's side: the page's routes, the queue, the phrasings kept by fingerprint
    sing.js      the page's side, with sing.css: the Sing view, consent, singing to the guide, the take measured
    released.json  the released version's guide (tools/released_guide.py)
"""
