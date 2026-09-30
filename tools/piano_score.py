"""The released rendition's score, for learning it on the piano: web/piano/score.json (the public page).

    uv run python tools/piano_score.py                   # renders/review/contest.flac -> web/piano/score.json
    uv run python tools/piano_score.py --check           # ...and check the score against the recording itself
    uv run python tools/piano_score.py FILE.flac --out X.json

How it is derived. The release (renders/review/contest.flac, rendered by `tools/everyone.py --render ... --arrange
motif=bridge lift=false ending=ring`) is a packet (docs/PACKET.md): it carries the program that sang it, the
genome, the render record and the words. This lays the rendition's score again the way tools/sing_site.py
seed_words does (and `songbird render --replay`): realize() with the record's params, words and phrasings, then
variation.lay, with no audio. It runs the packet's *own* program (unzipped to a temporary folder and imported
ahead of this tree's songbird/, after checking it against the record's program_sha256), so later changes to
songbird/ can't move a note. The score is trusted only if its words come out exactly as the packet's lyrics.txt.

The packet's program is older than songbird.band.overheard, so this listens in on songbird.band.plan (handed the
band's Context) and songbird.band.arrange (handed realize()'s melody entries) by wrapping them, which is safe in
a one-off script. The score.json itself is written by this tree's songbird.piano.export, the same code the
studio's piano page is fed by (its docstring says what goes in); `--check` holds it up against the recording.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from songbird import piano  # noqa: E402  (this tree's, imported before the packet's program replaces songbird)

RELEASE = ROOT / "renders" / "review" / "contest.flac"
OUT = ROOT / "web" / "piano" / "score.json"
COMMAND = ("uv run python tools/everyone.py --render renders/review/contest.flac "
           "--arrange motif=bridge lift=false ending=ring")
NAMES_SHARP = piano.NAMES_SHARP


def unpack_program(flac: Path, into: Path) -> dict:
    """The packet's program, genome, words and record, unzipped into `into`; the program checked against the
    record's hash (as the packet's own bootstrap checks it) before anything imports it."""
    with zipfile.ZipFile(flac) as z:
        record = json.loads(z.read("manifest.json"))
        program = {n: z.read(n) for n in z.namelist() if n.startswith("program/") and not n.endswith("/")}
        h = hashlib.sha256()
        for name in sorted(program):
            h.update(name.encode() + b"\0" + hashlib.sha256(program[name]).digest())
        if record.get("program_sha256") and h.hexdigest() != record["program_sha256"]:
            raise SystemExit(f"{flac}: the program inside doesn't match its record's program_sha256")
        for name in ("genome.json", "lyrics.txt", *program):
            z.extract(name, into)
    return record


def lay(flac: Path, tmp: Path) -> dict:
    """The rendition laid again from its packet with the packet's program: the score, the band's Context,
    realize()'s melody entries and clock, and the record."""
    record = unpack_program(flac, tmp)
    sys.path.insert(0, str(tmp / "program"))
    for name in [m for m in sys.modules if m == "songbird" or m.startswith("songbird.")]:
        del sys.modules[name]
    import songbird
    from songbird import band, genome as G, pack as P, phrasing as PH, variation
    from songbird.arrange import Lyrics
    from songbird.realize import PREROLL, Params, realize, timeline

    assert Path(songbird.__file__).is_relative_to(tmp), songbird.__file__
    genome = G.load(tmp / "genome.json")
    params = Params.from_dict(record["params"])
    params = replace(params, singer=record.get("singer") or params.singer, mix=record.get("mix") or params.mix)
    lyrics = Lyrics.from_dict(record["lyrics"]) if record.get("lyrics") else None
    lead, choir = PH.inherited(genome.source, record)

    heard: dict = {}
    plan, arrange = band.plan, band.arrange

    def plan_listened(ctx):
        heard["ctx"] = ctx
        return plan(ctx)

    def arrange_listened(*args):
        heard["arrange"] = args
        return arrange(*args)

    band.plan, band.arrange = plan_listened, arrange_listened
    try:
        score = variation.lay(realize(genome, params, phrasing=PH.from_json(lead) if lead else None,
                                      choir=[PH.from_json(d) for d in choir], lyrics=lyrics), params)
    finally:
        band.plan, band.arrange = plan, arrange
    sung = (tmp / "lyrics.txt").read_text()
    if P.words_as_sung(score.to_dict(), genome.title) != sung:
        raise SystemExit(f"{flac}: the score laid again doesn't sing the packet's words; not trusting it")
    _genome, _params, _placed, lead_u, end_u, melody, seconds = heard["arrange"]
    return {"record": record, "genome": genome, "params": params, "score": score, "ctx": heard["ctx"],
            "melody": sorted(melody, key=lambda m: m["u"]), "seconds": seconds, "lead": lead_u, "end": end_u,
            "clock": timeline(genome, params), "preroll": PREROLL, "program": songbird.__file__}


def export(laid: dict) -> dict:
    """The page's score.json (songbird.piano.export), saying it is the release laid again with its own program."""
    record = laid["record"]
    source = {
        "file": "renders/review/contest.flac", "id": record.get("id"), "program_sha256": record.get("program_sha256"),
        "rendered": COMMAND, "exporter": "tools/piano_score.py",
        "note": "laid again from the packet with its own program (grid positions, before the phrasing and the "
                "human jitter); see the exporter's docstring",
    }
    return piano.export(laid, source, record.get("duration"))


# --- checking the score against the recording ---------------------------------------------------------------


def chroma(audio, rate: int, hop: float = 0.05, size: int = 8192):
    """Pitch-class energy every `hop` seconds (a plain STFT folded onto 12 classes, 60 Hz to 2 kHz)."""
    import numpy as np

    step = int(rate * hop)
    window = np.hanning(size)
    freqs = np.fft.rfftfreq(size, 1 / rate)
    band = (freqs > 60) & (freqs < 2000)
    pcs = np.round(12 * np.log2(freqs[band] / 440.0) + 69).astype(int) % 12
    frames = []
    for i in range(0, len(audio) - size, step):
        mag = np.abs(np.fft.rfft(audio[i:i + size] * window))[band]
        frames.append(np.bincount(pcs, weights=mag, minlength=12))
    return np.array(frames), step / rate + 0.0, size / 2 / rate


def check(flac: Path, laid: dict, data: dict) -> bool:
    """Does the recording bear the score out? Its key, chords, tune and tempo, each against the same score
    moved up or down (a wrong key would score better somewhere else)."""
    import numpy as np
    import soundfile as sf

    audio, rate = sf.read(str(flac), dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    frames, hop, centre = chroma(audio, rate)
    times = np.arange(len(frames)) * hop + centre
    seconds, lead, beat = laid["seconds"], laid["lead"], laid["ctx"].beat

    def at(b: float) -> float:  # beats -> seconds in the recording (the score's own clock)
        return seconds(lead + b * beat)

    def span(t0: float, t1: float):
        sel = (times >= t0) & (times < t1)
        return frames[sel].mean(axis=0) if sel.any() else np.zeros(12)

    ok = True
    print(f"recording: {len(audio) / rate:.3f} s; the record says {laid['record'].get('duration')} s; "
          f"the score's last note ends (rings out) at {laid['score'].duration:.3f} s")

    # the key: the whole recording's chroma against the score's own pitch classes (every pitched note, weighted
    # by how long it sounds), moved by -6..+6 semitones. (A key profile alone can't tell a major pentatonic tune
    # from the major key a fifth above, which lacks nothing the tune uses; it is printed for what it's worth.)
    total = frames.sum(axis=0)
    content = np.zeros(12)
    for n in laid["score"].notes:
        if n.part not in ("drum",):
            content[int(round(n.pitch)) % 12] += n.dur
    fits = {k: float(np.corrcoef(total, np.roll(content, k))[0, 1]) for k in range(-6, 7)}
    major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    profile = max(range(12), key=lambda k: np.corrcoef(total, np.roll(major, k))[0, 1])
    print(f"key: the recording's pitch classes fit the score's notes as written with r={fits[0]:.2f}, moved by a "
          f"semitone or more at best r={max(v for k, v in fits.items() if k):.2f} (the score: "
          f"{data['key']['tonic']} {data['key']['mode']}; a major-key profile alone says {NAMES_SHARP[profile]})")
    ok &= fits[0] > max(v for k, v in fits.items() if k) + 0.1

    # the chords: each chord's span, which of the 24 major and minor triads fits it best, the score moved by
    # -6..+6 semitones
    triads = [(r, qual, np.isin(np.arange(12), [r, (r + (4 if qual == "maj" else 3)) % 12, (r + 7) % 12]).astype(float))
              for r in range(12) for qual in ("maj", "min")]
    spans = [span(at(c["start"]) + 0.05, at(c["end"])) for c in data["chords"]]
    fitted = [max(triads, key=lambda t: float(v @ t[2])) for v in spans]
    agree = {shift: sum(f[0] == (c["root"] + shift) % 12 and f[1] == c["quality"] for c, f in zip(data["chords"], fitted))
             / len(spans) for shift in range(-6, 7)}
    print(f"chords: the recording's best-fitting triad is the score's in {agree[0]:.0%} of {len(spans)} chord spans; "
          f"moved by a semitone or more, at most {max(v for s, v in agree.items() if s):.0%}")
    ok &= agree[0] > 0.6 and agree[0] > max(v for s, v in agree.items() if s) + 0.3

    # the tune: each sung note's pitch class among the recording's strongest while it is sung (the voice's own
    # timing, from the score's voice part)
    voice = [n for n in laid["score"].notes if n.part == "voice" and n.dur >= 0.3]
    ranks = {}
    for shift in range(-6, 7):
        top = 0
        for n in voice:
            v = span(n.start + 0.08, n.start + n.dur)
            top += (int(round(n.pitch)) + shift) % 12 in np.argsort(v)[-3:]
        ranks[shift] = top / len(voice)
    print(f"tune: a sung note's pitch class is among the recording's three strongest in {ranks[0]:.0%} of "
          f"{len(voice)} notes; moved by a semitone or more, at most {max(v for s, v in ranks.items() if s):.0%}")
    ok &= ranks[0] > 0.7

    # the rhythm: the recording's onsets (spectral flux, every 10 ms) repeat at the score's beat, and fall on
    # its beats rather than between them
    size, step = 2048, rate // 100
    window = np.hanning(size)
    spectra = np.array([np.log1p(np.abs(np.fft.rfft(audio[i:i + size] * window))[:size // 4])
                        for i in range(0, len(audio) - size, step)])
    onset = np.maximum(np.diff(spectra, axis=0), 0).sum(axis=1)
    onset -= onset.mean()
    ac = np.correlate(onset, onset, "full")[len(onset) - 1:]
    lo, hi = int(0.4 * 100), int(1.0 * 100)
    i = lo + int(np.argmax(ac[lo:hi]))
    a, b0, c = ac[i - 1], ac[i], ac[i + 1]  # the peak between samples, by a parabola through three
    period = (i + 0.5 * (a - c) / (a - 2 * b0 + c)) / 100
    print(f"tempo: the recording's onsets repeat every {period:.3f} s ({60 / period:.1f} bpm); the score says "
          f"{data['tempo']:g} bpm ({60 / data['tempo']:.3f} s)")
    ok &= abs(60 / period - data["tempo"]) < 2
    flux = onset
    hop, centre = 0.01, size / 2 / rate
    on = [flux[int((at(x) - centre) / hop)] for x in np.arange(0, data["ritardando"]["from"], 1.0)]
    off = [flux[int((at(x + 0.5) - centre) / hop)] for x in np.arange(0, data["ritardando"]["from"], 1.0)]
    print(f"beats: onset strength on the score's beats {np.mean(on):.3f}, halfway between them {np.mean(off):.3f}")
    ok &= np.mean(on) > np.mean(off)
    print("the score matches the recording" if ok else "THE SCORE AND THE RECORDING DISAGREE somewhere above")
    return bool(ok)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("flac", nargs="?", default=str(RELEASE), help="a packed render (default: the release)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true", help="check the score against the recording's audio")
    args = ap.parse_args()
    flac = Path(args.flac)
    with tempfile.TemporaryDirectory() as tmp:
        laid = lay(flac, Path(tmp))
        data = export(laid)
        if args.check and not check(flac, laid, data):
            raise SystemExit(1)
    if flac.resolve() != RELEASE.resolve():
        data["source"]["file"] = str(flac)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n")
    sung = sum(1 for n in data["melody"] if "lyric" in n)
    print(f"{out}: {data['title']}, {data['key']['tonic']} {data['key']['mode']}, {data['tempo']:g} bpm, "
          f"{data['bars']} bars, {len(data['sections'])} sections, {len(data['melody'])} tune notes ({sung} sung), "
          f"{len(data['chords'])} chords, {len(data['lines'])} lines")


if __name__ == "__main__":
    main()
