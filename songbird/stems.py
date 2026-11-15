"""The stems as a studio packs them (Studio._stems; the web studio's studio_render.Stems): every part alone and dry,
padded to bar 1 of the MIDI file, one gain for all (min(1, CEILING / the loudest part's peak), so none clips and they
keep their balance), as 24-bit FLAC with the song's artwork; in the zip the singer first, then the voices before,
then the band.

Kept keeps them as a whole song is made (cli.render_one's `kept`): the mix is handed each part dry, which is packed at
the gain the peaks heard so far give; at the end, a part packed before a louder one is turned down from its file (its
24-bit samples times the ratio, packed again: within a step of 24 bits of a part packed at the last gain from the
start). So the stems come with the song, no part made twice."""

from __future__ import annotations

import io
import threading
import time

import numpy as np

CEILING = 0.989  # the stems' loudest sample
BLOCK = 1 << 16  # samples a part is packed in at a time


def gain_of(peak: float) -> float:
    return min(1.0, CEILING / peak) if peak > 0 else 1.0


def peak_of(y: np.ndarray) -> float:
    return float(np.max(np.abs(y))) if y.size else 0.0


def in_order(names: list[str]) -> list[str]:
    """The zip's order: the singer, the voices before, then the rest as they come."""
    return sorted(names, key=lambda p: (p != "voice", not p.startswith("choir"), names.index(p)))


def packed(write, title: str) -> bytes:
    """A part's file: write(the open file) writes its samples."""
    import soundfile as sf

    from . import artwork, synth

    buffer = io.BytesIO()
    with sf.SoundFile(buffer, "w", synth.SR, 2, "PCM_24", format="FLAC") as f:
        write(f)
    return artwork.embed(buffer.getvalue(), title)


def padded(y: np.ndarray, pad: int, gain: float):
    """What writes a part's samples at gain after `pad` samples of silence, a block at a time (no copy of the part)."""
    def write(f) -> None:
        if pad:
            f.write(np.zeros((pad, y.shape[1])))
        for a in range(0, len(y), BLOCK):
            f.write(y[a:a + BLOCK] * gain)
    return write


def turned(data: bytes, was: float, gain: float, title: str) -> bytes:
    """A part's file packed at gain `was`, turned to `gain`."""
    import soundfile as sf

    out, _ = sf.read(io.BytesIO(data), dtype="float64", always_2d=True)
    out *= gain / was
    return packed(lambda f: f.write(out), title)


class Kept:
    """The stems kept as a whole song is made: call it with each part's dry stem as the mix is handed it (from any
    thread), then finished(). seconds: the time spent packing, in all threads together."""

    def __init__(self, parts: list[str], pad: int, title: str):
        self.parts, self.pad, self.title = list(parts), pad, title
        self.files: dict[str, tuple[float, bytes]] = {}
        self.peak = 0.0
        self.seconds = 0.0
        self.lock = threading.Lock()

    def __call__(self, part: str, y: np.ndarray) -> None:
        if part not in self.parts:
            return
        peak = peak_of(y)
        with self.lock:
            if part in self.files:
                return
            self.peak = max(self.peak, peak)
            gain = gain_of(self.peak)
            self.files[part] = (gain, b"")
        t0 = time.perf_counter()
        data = packed(padded(y, self.pad, gain), self.title)
        with self.lock:
            self.files[part] = (gain, data)
            self.seconds += time.perf_counter() - t0

    def finished(self) -> tuple[float, dict[str, bytes], list[str]] | None:
        """(the gain, each part's file, the parts turned down at the end), or None if a part wasn't handed over."""
        if set(self.files) != set(self.parts):
            return None
        t0 = time.perf_counter()
        gain = gain_of(self.peak)
        files, again = {}, []
        for part in self.parts:
            was, data = self.files.pop(part)
            if was != gain:
                again.append(part)
                data = turned(data, was, gain, self.title)
            files[part] = data
        self.seconds += time.perf_counter() - t0
        return gain, files, again
