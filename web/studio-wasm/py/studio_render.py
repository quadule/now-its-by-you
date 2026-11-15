"""A render the studio's server specified, made here: in a visitor's browser (the worker, songbird/studio's
render worker: web/studio-wasm/studio-worker.mjs), or natively, where the tests check it against the server.

The spec is what the public studio hands its page (songbird/studio.py, "rendering in the visitor's browser":
Studio.render_spec): the song as a file, the version's resolved choices (params), its words, phrasing, the
voices before, the parent's record, the machine and the day, so nothing is worked out again here. This calls
what the server's own renders call: a section as Studio._section makes it (the score cut at the section's window,
brought up by the preview's gain, faded), the whole song as Studio._whole does (cli.render_one, packed: the
recording, one file with the program, the song and its record). The same inputs through the same functions: the
same samples (docs/notes/BROWSER-RENDER.md, "Byte identity"), and the same packet.

    run(spec_text, folder, progress=None) -> {"kind", "key", "flac": path, "id", "duration", "record"?}

progress(fraction, words), as the server's job reports it (Studio's Job.report and stages)."""

from __future__ import annotations

import contextlib
import gc
import hashlib
import io
import json
import os
import types
from pathlib import Path

from songbird.synth.cache import StemCache

_STEM_CACHE = StemCache(int(os.environ.get("SONGBIRD_STEM_CACHE_BYTES", 64 * 2**20)))

VERSION = 1  # the spec's shape; Studio.render_spec's RENDER_SPEC must match


class Refused(ValueError):
    """A spec this program can't make: another shape, or another program."""


def _job(key: str, kind: str, progress):
    """The server's own Job, for its progress (the same stages, weights and words), reporting here."""
    from songbird.studio import Job

    job = Job(id="browser", key=key, kind=kind, label="", work=None)
    if progress is None:
        return job
    report = job.report

    def told(name: str) -> None:
        report(name)
        progress(job.progress, job.stage)

    job.report = told
    return job


_GENOMES: dict[str, object] = {}  # the last few songs parsed, by their digest
GENOMES = 2


def load(spec: dict, folder: Path):
    """The song and the version's choices, as the spec gives them: the song's file written as it came (a
    recording packs these very bytes), everything else read back by its own class."""
    from songbird import genome as genome_mod
    from songbird.arrange import Lyrics
    from songbird.realize import Params

    folder.mkdir(parents=True, exist_ok=True)
    song = folder / "genome.json"
    raw = spec["genome"].encode("utf-8")
    song.write_bytes(raw)
    gkey = hashlib.sha256(raw).hexdigest()
    if gkey in _GENOMES:
        genome = _GENOMES[gkey] = _GENOMES.pop(gkey)
    else:
        genome = genome_mod.from_dict(json.loads(spec["genome"]))
        _GENOMES[gkey] = genome
        while len(_GENOMES) > GENOMES:
            del _GENOMES[next(iter(_GENOMES))]
    params = Params.from_dict(spec["params"])
    lyrics = Lyrics.from_dict(spec["lyrics"]) if spec.get("lyrics") else None
    return song, genome, params, lyrics


_SCORES: dict[str, object] = {}  # the last few versions laid out, by what laid them (_score_key)
SCORES = 2


def _score_key(spec: dict) -> str:
    """What a version's score is made from: the song, its choices but the mix's (realize and lay never read the mix,
    which only the synthesis does), its words, phrasing and choir."""
    made_of = [spec["genome"], {k: v for k, v in spec["params"].items() if k != "mix"}, spec.get("lyrics"),
               spec.get("phrasing"), spec.get("choir")]
    return hashlib.sha256(json.dumps(made_of, sort_keys=True, default=str).encode()).hexdigest()


def _score(genome, params, lyrics, spec: dict):
    """The version laid out, as Studio._score lays it. A section's edit of the mix alone (or one asked again) lays out
    the same score, so the last few are kept: a quarter of an edit's preview in the browser (0.75 of 3 s in node). A
    Score and its notes are frozen, and what reads them (window, cut, the synthesis) makes new ones."""
    from songbird import phrasing as phrasing_mod, stage

    key = _score_key(spec)
    if key in _SCORES:
        _SCORES[key] = _SCORES.pop(key)  # the most recent last
        return _SCORES[key]
    phrasing = phrasing_mod.from_json(spec["phrasing"]) if spec.get("phrasing") else None
    choir = [phrasing_mod.from_json(ph) for ph in spec.get("choir") or []]
    score = stage.laid(genome, params, phrasing=phrasing, choir=choir, lyrics=lyrics)  # (as cli.render_one)
    _SCORES[key] = score
    while len(_SCORES) > SCORES:
        del _SCORES[next(iter(_SCORES))]
    return score


def section(spec: dict, folder: Path, progress=None) -> dict:
    """One section's preview, as Studio._section makes it."""
    from songbird import explain, synth
    from songbird.cli import choir_of
    from songbird.studio import PREVIEW_GAIN_DB, cut, faded, stage_words, stages, window
    from songbird.synth import master
    from songbird.synth.mixing import MixParams

    job = _job(spec["key"], "preview", progress)
    job.stage = stage_words("score")
    _, genome, params, lyrics = load(spec, folder)
    index = int(spec["section"])
    score = _score(genome, params, lyrics, spec)
    t0, t1 = window(genome, params, score, params.form, index)
    part, lead_in = cut(score, t0, t1)
    job.plan = stages(part)
    singer = explain.singer_of(params)
    ancestors = choir_of(spec.get("parent"), singer)[1]
    mix = synth.render(part, seed=params.seed, voice=singer, mix_params=MixParams.from_dict(params.mix or {}),
                       ancestors=ancestors, progress=job.report, cache=_STEM_CACHE)
    job.report("master")
    ceiling = master.CEILING_DB - master.MARGIN_DB
    mix *= 10.0 ** (PREVIEW_GAIN_DB / 20.0)
    loud = master.limit(master.clip(mix, ceiling, inplace=True), synth.SR, ceiling, inplace=True)
    del mix
    loud = faded(loud, synth.SR, lead_in, inplace=True)
    pcm = master.to_pcm16(loud, seed=params.seed)
    del loud
    flac = folder / f"{spec['key']}.flac"
    master.write_flac(flac, pcm, synth.SR)
    return {"kind": "section", "key": spec["key"], "flac": str(flac), "id": master.pcm_sha256(pcm),
            "duration": round(len(pcm) / synth.SR, 2)}


@contextlib.contextmanager
def packed_as(packet: dict | None):
    """The packet says what the program runs with (its Python, its dependencies pinned): the server's, whose
    render this is, byte for byte, rather than the browser's stand-in (Pyodide, with no numba)."""
    from songbird import pack

    if not packet:
        yield
        return
    major, minor = (int(x) for x in str(packet["python"]).split(".")[:2])
    was_sys, was_requirements = pack.sys, pack.requirements
    shim = types.SimpleNamespace(**{k: getattr(was_sys, k) for k in ("stderr", "stdout")})
    shim.version_info = types.SimpleNamespace(major=major, minor=minor)
    pack.sys, pack.requirements = shim, (lambda: packet["requirements"])
    try:
        yield
    finally:
        pack.sys, pack.requirements = was_sys, was_requirements


def whole(spec: dict, folder: Path, progress=None) -> dict:
    """The whole rendition, as Studio._whole makes it: cli.render_one, packed. It is the recording."""
    from songbird import drift as drift_mod, harvest
    from songbird.cli import render_one
    from songbird.studio import stage_words, stages

    _STEM_CACHE.clear()
    job = _job(spec["key"], "record", progress)
    job.stage = stage_words("score")
    song, genome, params, lyrics = load(spec, folder)
    job.plan = stages(_score(genome, params, lyrics, spec))
    voice = harvest.Voice.from_dict(spec["voice"]) if spec.get("voice") else None
    drift = drift_mod.Drift.from_dict(spec["drift"]) if spec.get("drift") else None
    out = folder / "rendition.flac"
    with packed_as(spec.get("packet")), contextlib.redirect_stdout(io.StringIO()):
        record = render_one(genome, params, out, voice=voice, drift=drift, lyrics=lyrics,
                            phrasing_json=spec.get("phrasing"), choir_json=spec.get("choir") or [],
                            parent=spec.get("parent"), packet_genome=song, changes=spec.get("changes"),
                            chosen_by_you=spec.get("marks") or None, progress=job.report, name=spec.get("name"))
    from songbird import pack

    # the record as it travels (the packet's manifest: with the program's digest and what it runs with)
    return {"kind": "whole", "key": spec["key"], "flac": str(out), "id": record["id"],
            "duration": record["duration"], "record": pack.read_manifest(out) or record}


def stems(spec: dict, folder: Path, out: str | Path) -> list[str]:
    """Every part of a whole spec's rendition alone and dry, as float64 (synth.render_stems), into an .npz: where two
    renders of the same spec part (bench/stems_diff.py compares the browser's with the server's)."""
    import numpy as np

    from songbird import explain, synth
    from songbird.cli import choir_of

    _, genome, params, lyrics = load(spec, folder)
    singer = explain.singer_of(params)
    parts = synth.render_stems(_score(genome, params, lyrics, spec), seed=params.seed, voice=singer,
                               ancestors=choir_of(spec.get("parent"), singer)[1])
    np.savez(out, **parts)
    return list(parts)


CEILING = 0.989  # the stems' loudest sample: Studio._stems' gain is min(1, CEILING / the loudest part's peak)


def stems_gain(peak: float) -> float:
    return min(1.0, CEILING / peak) if peak > 0 else 1.0


class Stems:
    """The stems of a spec of kind "stems", as Studio._stems packs them (every part alone and dry, padded to bar 1 of
    the MIDI file, one gain for all, 24-bit FLAC with the song's artwork; the MIDI file and the note beside them), in
    steps the page schedules, so several render workers can each make some of the parts, and each holds one part's
    samples at a time: make(part) makes it and says its peak; encode(gain) packs it at the gain the page says (the
    one every peak heard so far gives) and lets it go; rescale turns a part packed at a gain a louder part later
    lowered down from its file (its 24-bit samples times the ratio, packed again: within a step of 24 bits of the
    server's, not the server's to the byte); finish(gain) is the MIDI file and the note. recording: the file name and
    id of the recording of this version, if the page has it."""

    def __init__(self, spec: dict, folder: Path, recording: tuple[str, str] | None = None):
        from songbird import explain, midi, synth
        from songbird.cli import choir_of
        from songbird.studio import stages

        _STEM_CACHE.clear()
        self.spec, self.recording = spec, tuple(recording) if recording else None
        _, self.genome, self.params, lyrics = load(spec, folder)
        self.score = _score(self.genome, self.params, lyrics, spec)
        self.weights = dict([p for p in stages(self.score) if p[0] not in ("mix", "master")] + [("master", 1.0)])
        self.midi, self.lead_in = midi.from_score(self.genome, self.params, self.score, title=self.genome.title,
                                                  lyrics=lyrics)
        self.singer = explain.singer_of(self.params)
        self.ancestors = choir_of(spec.get("parent"), self.singer)[1]
        jobs, singers = synth.stem_jobs(self.score, seed=self.params.seed, voice=self.singer, ancestors=self.ancestors)
        names = [name for name, _ in jobs]
        self.order = sorted(names, key=lambda p: (p != "voice", not p.startswith("choir"), names.index(p)))
        self.singers = [p for p in self.order if p in singers]
        self.band = [p for p in names if p not in singers]
        self.makes, self.used = dict(jobs), set()
        self.stem = self.recording[0][: -len(".flac")] if self.recording else spec["stem"]
        self.pad = int(round(-self.lead_in * synth.SR))
        self.part = self.y = None

    def plan(self) -> dict:
        """What the page schedules: the parts in the zip's order, the band and the singers (the slowest), each part's
        share of the time and what the player says it is doing."""
        from songbird.studio import stage_words

        return {"parts": self.order, "band": self.band, "singers": self.singers, "name": self.stem,
                "weights": {p: self.weights.get(p, 1.0) for p in self.order},
                "words": {p: stage_words(p) for p in self.order}}

    def make(self, part: str) -> float:
        """The part made (and held until encode), and its peak."""
        import numpy as np

        from songbird import synth

        if part in self.used:  # each maker makes its part once (a player's stem is handed over to its twins' level)
            self.makes = dict(synth.stem_jobs(self.score, seed=self.params.seed, voice=self.singer,
                                              ancestors=self.ancestors)[0])
            self.used.clear()
        self.used.add(part)
        self.part, self.y = None, None
        y = self.makes[part]()
        self.part, self.y = part, y
        return float(np.max(np.abs(y))) if y.size else 0.0

    def _file(self, part: str, out) -> tuple[int, str, bytes, int]:
        import zlib

        import soundfile as sf

        from songbird import artwork, synth

        buffer = io.BytesIO()
        sf.write(buffer, out, synth.SR, format="FLAC", subtype="PCM_24")
        del out
        flac = artwork.embed(buffer.getvalue(), self.genome.title)
        i = self.order.index(part) + 1
        return i, f"{self.stem}/{i:02d}-{part}.flac", flac, zlib.crc32(flac)

    def encode(self, gain: float) -> tuple[int, str, bytes, int]:
        """The part made last, packed at gain (as Studio._stems packs it), and let go."""
        import numpy as np

        y, part = self.y, self.part
        self.part = self.y = None
        out = np.zeros((self.pad + len(y), y.shape[1]), y.dtype)  # padded where it's made: one copy more, not two
        np.multiply(y, gain, out=out[self.pad:])
        del y
        try:
            return self._file(part, out)
        finally:
            del out
            gc.collect()

    def rescale(self, part: str, data: bytes, was: float, gain: float) -> tuple[int, str, bytes, int]:
        """A part's file packed at gain `was`, turned to `gain`: its samples read back, times the ratio, packed again."""
        import soundfile as sf

        out, _ = sf.read(io.BytesIO(data), dtype="float64", always_2d=True)
        out *= gain / was
        try:
            return self._file(part, out)
        finally:
            del out
            gc.collect()

    def finish(self, gain: float) -> dict:
        import zlib

        from songbird.studio import stems_note

        note = stems_note(self.genome.title, self.params, -self.lead_in, gain, self.order,
                          recording=self.recording).encode("utf-8")
        return {"name": self.stem, "parts": self.order, "gain": gain,
                "midi": [f"{self.stem}/{self.stem}.mid", self.midi, zlib.crc32(self.midi)],
                "readme": [f"{self.stem}/README.txt", note, zlib.crc32(note)]}


def stems_zipped(spec: dict, folder: Path, emit, progress=None, recording: tuple[str, str] | None = None) -> dict:
    """The stems made by one worker, a part at a time, every file the server's to the byte: the band first and the
    singers (the slowest) last, each part packed at the gain the peaks so far give and handed to emit(index, name,
    data, crc32) at once; a part a louder one after it turned down is made again, quieter. The page's pool of workers
    (renderer.js) schedules a Stems' steps itself; this is the reference it is held to (tests/test_studio_device.py).

    -> Stems.finish's, and "again": the parts made again"""
    from songbird.studio import stage_words

    stems = Stems(spec, folder, recording)
    job = _job(spec["key"], "export", progress)
    job.plan = list(stems.weights.items())
    peak, made_at = 0.0, {}

    def make(part: str) -> None:
        nonlocal peak
        peak = max(peak, stems.make(part))
        made_at[part] = stems_gain(peak)
        emit(*stems.encode(made_at[part]))

    making = stems.band + stems.singers
    for part in making:
        job.report(part)
        make(part)
    again = [part for part in making if made_at[part] != stems_gain(peak)]
    for part in again:  # a louder part came after it: made again at the gain every part shares
        job.stage = f"{stage_words(part)} again, quieter"
        if progress is not None:
            progress(job.progress, job.stage)
        make(part)
    job.report("master")
    return {**stems.finish(stems_gain(peak)), "again": again}


def check(spec: dict, program: str | None = None) -> None:
    """Refused, saying why, unless this program can make this spec: its shape, and the program it names (a
    recording carries the program's digest, so the program here must be the server's, file for file)."""
    if spec.get("v") != VERSION:
        raise Refused(f"a render spec of shape {spec.get('v')!r}; this renderer makes shape {VERSION}")
    if spec.get("kind") not in ("section", "whole", "stems"):
        raise Refused("a render spec makes a section, the whole song or its stems")
    if program is None:
        from songbird import pack

        program = pack.program_sha256(pack.program_files())
    if spec.get("program") != program:
        raise Refused(f"the server sings program {str(spec.get('program'))[:12]}, this one is {program[:12]}")


def run(spec_text: str, folder: str | Path, progress=None, program: str | None = None) -> dict:
    spec = json.loads(spec_text)
    check(spec, program)
    folder = Path(folder)
    if spec["kind"] == "stems":
        raise Refused("the stems are made by run_stems")
    return section(spec, folder, progress) if spec["kind"] == "section" else whole(spec, folder, progress)


def run_stems(spec_text: str, folder: str | Path, emit, progress=None, program: str | None = None,
              recording: list | None = None) -> dict:
    spec = json.loads(spec_text)
    check(spec, program)
    if spec["kind"] != "stems":
        raise Refused("this spec doesn't make the stems")
    return stems_zipped(spec, Path(folder), emit, progress, tuple(recording) if recording else None)
