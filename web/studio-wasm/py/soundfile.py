"""soundfile, for the browser: songbird.synth.master imports it at the top, but a preview in the browser never
writes a FLAC (section.wav_bytes writes a WAV with the standard library). Pyodide does ship soundfile
(libsndfile built for wasm); this stub saves loading it."""


def _absent(*args, **kwargs):
    raise RuntimeError("no soundfile in the browser build (load Pyodide's 'soundfile' package to write FLAC)")


write = read = info = SoundFile = _absent
