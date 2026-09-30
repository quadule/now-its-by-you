"""Make the singing kit the web studio takes takes with (webstudio/kit.py), on a computer with the memory.

    uv run python -m webstudio.prepare                                   # the lead song, into renders/sing-kit
    uv run python -m webstudio.prepare --song songs/h-now-its-by-you.json --keys -4 -2 0 2 4 --tempos 90 --kit DIR

For each version offered (a spec, tools/guides.py: the first recording set, each key asked for, each speed):
its score, the melody guide the visitor hears (the karaoke's default mix: the tune on a whistle over a pulse,
made from the score alone, so none of the band is rendered), its words for the page, and the template singer's
analysis of it in the guide's key and an octave either side (--octaves), which is the part that needs the
memory: 4 GB and about a minute each on an M-series Mac, each made in a process of its own. Every file is the
song's or the machine's; nobody's voice is in the kit.

Run it with the program the server will run: the templates are kept under the measuring code's version
(tools/phrasing.py version(), which hashes the singer), and a server whose code differs finds none and says
so rather than making them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .kit import ROOT, VERSION, Kit
from .worker import Tools, peak_mb

KEYS = (-4, -2, 0, 2, 4)  # the keys a visitor may choose, semitones from the song's own (tools/guides.py KEYS)
TEMPOS = (90,)  # a little slower than written, as the karaoke starts (tools/karaoke.py SLOWER)
OCTAVES = (-12, 0, 12)  # where a voice sings against the guide: in its key, or an octave either side


def melody(tools: Tools, score_path: Path, out: Path) -> int:
    """The melody guide for a spec's score, as tools/guides.py write_spec makes it, as a FLAC; its bytes. Mono at
    half the rate (22.05 kHz): a whistle and a pulse lose nothing a singer needs, and it downloads in a quarter
    of the bytes (about 5 MB for the whole song at 90%). Halving the rate keeps every sample's time."""
    import soundfile as sf
    from scipy.signal import resample_poly

    from songbird import synth
    from songbird.synth import master

    M = tools.M
    score, data = M.load_score(score_path)
    seed, sr = int(data.get("seed", 0)), synth.SR
    beats = [(float(t), bool(b)) for t, b in data["beats"]]
    mastered = master.master(M.render_melody(score, beats, sr, seed), sr)
    half = resample_poly(mastered.mean(axis=1) if mastered.ndim == 2 else mastered, 1, 2)
    pcm = master.to_pcm16(half, seed=seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part.flac")
    sf.write(str(part), pcm, sr // 2, format="FLAC", subtype="PCM_16")
    part.replace(out)
    return out.stat().st_size


def words(score_path: Path, title: str, digest: str) -> dict:
    """What the page shows while a visitor sings: tools/karaoke.py's words for the score, its guide's digest."""
    import karaoke as KA  # tools/karaoke.py (on the path Tools put there)

    data = json.loads(score_path.read_text())
    return {**KA.lyrics(data, title, data["tempo"]), "guide": digest, "spec": data["spec"]}


def prepare(song: Path, kit: Kit, keys=KEYS, tempos=TEMPOS, octaves=OCTAVES, set_id: str | None = None,
            say=print) -> dict:
    tools = Tools(kit)
    M, T, K = tools.M, tools.T, tools.K
    stem = song.stem
    kit.root.mkdir(parents=True, exist_ok=True)
    genome_path = kit.genome(stem)
    genome_path.parent.mkdir(parents=True, exist_ok=True)
    if not genome_path.exists() or genome_path.read_bytes() != song.read_bytes():
        shutil.copyfile(song, genome_path)
    path, genome = tools.genome(stem)
    sets = M.sets(path, genome)
    chosen = next((s for s in sets if s["id"] == set_id), None) if set_id else sets[0]
    if chosen is None:
        raise SystemExit(f"no set {set_id!r}; there are {', '.join(s['id'] for s in sets)}")
    specs = []
    for tempo in tempos:
        for key in keys:
            spec = M.Spec(chosen["id"], key, tempo)
            began = time.time()
            score = M.spec_score(path, spec)
            digest = K.keep_guide(stem, score)
            audio = kit.audio(spec.id)
            note = kit.root / "audio" / f"{spec.id}.json"
            made = json.loads(note.read_text()) if note.exists() else {}
            if not audio.exists() or made.get("score") != digest or made.get("recipe") != M.recipe():
                size = melody(tools, score, audio)
                note.write_text(json.dumps({"score": digest, "recipe": M.recipe()}) + "\n")
            else:
                size = audio.stat().st_size
            lyrics = words(score, genome.title, digest)
            kit.lyrics(spec.id).parent.mkdir(parents=True, exist_ok=True)
            kit.lyrics(spec.id).write_text(json.dumps(lyrics) + "\n")
            for octave in octaves:  # each in a process of its own, so its 4 GB is given back before the next
                kept = kit.measured / "templates" / f"{digest}.{octave:+d}.{tools.extractor}.npz"
                if not kept.exists():
                    subprocess.run([sys.executable, "-m", "webstudio.prepare", "--kit", str(kit.root), "--template",
                                    stem, digest, str(octave)], cwd=ROOT, check=True)
            specs.append({**spec.to_dict(), "guide": digest, "duration": round(float(lyrics["duration"]), 3),
                          "templates": list(octaves), "audio_bytes": size})
            say(f"  {spec.id}: guide {digest}, {lyrics['duration']:.0f} s, melody {size / 2**20:.1f} MB, "
                f"templates {list(octaves)} ({time.time() - began:.0f} s, peak {peak_mb()} MB)")
    default = next((s["id"] for s in specs if s["key"] == 0), specs[0]["id"])
    offer = {"kit": VERSION, "song": stem, "title": genome.title,
             "genome": hashlib.sha256(song.read_bytes()).hexdigest(), "extractor": tools.extractor,
             "made": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "set": {k: chosen[k] for k in ("id", "name", "about")}, "specs": specs, "default": default}
    kit.offer_path.write_text(json.dumps(offer, indent=1) + "\n")
    return offer


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m webstudio.prepare", description=__doc__.split("\n\n")[0])
    ap.add_argument("--song", default=str(ROOT / "songs" / "h-now-its-by-you.json"), help="the song's genome")
    ap.add_argument("--kit", help="where the kit goes (default $SONGBIRD_SING_KIT, else renders/sing-kit)")
    ap.add_argument("--keys", type=int, nargs="+", default=list(KEYS), help="keys offered, semitones from the song's")
    ap.add_argument("--tempos", type=int, nargs="+", default=list(TEMPOS), help="speeds offered, percent of the song's")
    ap.add_argument("--octaves", type=int, nargs="+", default=list(OCTAVES),
                    help="where a voice may sit against the guide (semitones): a template for each")
    ap.add_argument("--set", dest="set_id", help="the recording set to sing (default: the first)")
    ap.add_argument("--template", nargs=3, metavar=("SONG", "GUIDE", "KEY"), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    kit = Kit(args.kit)
    if args.template:  # one template singer's analysis, alone (prepare() runs each in a process of its own)
        song, digest, key = args.template
        tools = Tools(kit)
        g = tools.guide(song, digest)
        g.templates = {}  # making it is what this is for
        tools.T.template(g, int(key))
        return 0
    print(f"Making the singing kit in {kit.root}")
    offer = prepare(Path(args.song).resolve(), kit, args.keys, args.tempos, args.octaves, args.set_id)
    print(f"{len(offer['specs'])} versions to sing to, for {offer['title']}; the studio takes takes with "
          f"`songbird studio --web-singing` (--sing-kit {kit.root} if it's elsewhere)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
