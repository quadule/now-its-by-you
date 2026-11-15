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


def stems_zipped(spec: dict, folder: Path, emit, progress=None, recording: tuple[str, str] | None = None) -> dict:
    """The stems, as Studio._stems packs them (every part alone and dry, padded to bar 1 of the MIDI file, one gain
    for all, 24-bit FLAC with the song's artwork; the MIDI file and the note beside them), made one part at a time so
    only one part's samples are held at once: each part's file is handed to emit(index, name, data, crc32) as soon as
    it is made, then let go; the page zips them. The gain that keeps every part from clipping is known only once all
    are made, so a part made at a gain the parts after it lowered is made again at the last one: the band is made
    first and the singers (the slowest) last, so it is the quick parts that are made again (H's band before its
    drum). recording: the file name and id of the recording of this version, if the page has it.

    -> {"name": the zip's folder, "parts": the order, "gain", "midi": (name, data, crc), "readme": (name, text, crc)}"""
    import zlib

    import numpy as np
    import soundfile as sf

    from songbird import artwork, explain, midi, synth
    from songbird.cli import choir_of
    from songbird.studio import stages, stage_words, stems_note

    _STEM_CACHE.clear()
    job = _job(spec["key"], "export", progress)
    job.stage = stage_words("score")
    _, genome, params, lyrics = load(spec, folder)
    score = _score(genome, params, lyrics, spec)
    job.plan = [p for p in stages(score) if p[0] not in ("mix", "master")] + [("master", 1.0)]
    data, lead_in = midi.from_score(genome, params, score, title=genome.title, lyrics=lyrics)
    singer = explain.singer_of(params)
    ancestors = choir_of(spec.get("parent"), singer)[1]

    def makers() -> dict:  # each maker makes its part once (a player's stem is handed over to its twins' level)
        return dict(synth.stem_jobs(score, seed=params.seed, voice=singer, ancestors=ancestors)[0])

    jobs, singers = synth.stem_jobs(score, seed=params.seed, voice=singer, ancestors=ancestors)
    names = [name for name, _ in jobs]
    order = sorted(names, key=lambda p: (p != "voice", not p.startswith("choir"), names.index(p)))
    # the band before the singers: the slowest made last, so a louder part after them seldom has them made again
    making = [p for p in names if p not in singers] + [p for p in order if p in singers]
    makes = dict(jobs)
    stem = recording[0][: -len(".flac")] if recording else spec["stem"]
    pad = int(round(-lead_in * synth.SR))
    peak, made_at = 0.0, {}

    def gain_now() -> float:
        return min(1.0, 0.989 / peak) if peak > 0 else 1.0

    def make(i: int, part: str) -> None:
        nonlocal peak
        y = makes[part]()
        if y.size:
            peak = max(peak, float(np.max(np.abs(y))))
        gain = gain_now()
        out = np.zeros((pad + len(y), y.shape[1]), y.dtype)  # padded where it's made: one copy more, not two
        np.multiply(y, gain, out=out[pad:])
        del y
        buffer = io.BytesIO()
        sf.write(buffer, out, synth.SR, format="FLAC", subtype="PCM_24")
        del out
        flac = artwork.embed(buffer.getvalue(), genome.title)
        del buffer
        emit(i, f"{stem}/{i:02d}-{part}.flac", flac, zlib.crc32(flac))
        del flac
        made_at[part] = gain
        gc.collect()

    for part in making:
        job.report(part)
        make(order.index(part) + 1, part)
    again = [part for part in making if made_at[part] != gain_now()]
    if again:
        makes = makers()
    for part in again:  # a louder part came after it: made again at the gain every part shares
        job.stage = f"{stage_words(part)} again, quieter"
        if progress is not None:
            progress(job.progress, job.stage)
        make(order.index(part) + 1, part)
    job.report("master")
    gain = gain_now()
    note = stems_note(genome.title, params, -lead_in, gain, order,
                      recording=tuple(recording) if recording else None).encode("utf-8")
    return {"name": stem, "parts": order, "gain": gain, "again": again,
            "midi": [f"{stem}/{stem}.mid", data, zlib.crc32(data)],
            "readme": [f"{stem}/README.txt", note, zlib.crc32(note)]}


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
