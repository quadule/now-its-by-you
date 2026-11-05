"""What a singer hears while they sing along: the guide mixes of the karaoke and the studio's Sing view.

    full     the song as the machine sings it: its singer and its band, mixed and mastered
    melody   the tune alone, on the band's whistle played plainly, over a quiet pulse: every sung
             note as the singer sings it, and where no one sings, the tune as the band plays it
             there, at the band's own octave and softer, so the singer hears their entry drop into
             their register; the pulse counts each entry in and steps back under the singing. The
             default for singers: they keep time and hear the tune without copying the machine's
             phrasing, which is what their takes are for.
    voice    the machine's singer alone, as it sounds in the full guide

Every mix comes from one score. tools/phrasing.py's write_guide renders the full
guide and writes the score it follows, with its tempo, seed and beats
(renders/guide/<song>.guide.score.json); the other mixes are rendered from that
file alone, so a take sung to any of them lines up with the same timeline and is
measured against the same guide, by the same digest. Each mix is kept beside the
full one (renders/guide/<song>.guide.<mix>.wav) with a note of the score digest
and recipe it was made from, and made again when either changes.

Specs. A singer chooses what to sing and how: a set (a recording script: which of
the bank's words, in which form; tools/sets/<song>.json, or until there is one the
song's own words and form, SONG), a key (semitones from the song's own, KEYS) and a
speed (percent of its tempo, TEMPOS). A spec names one of each, "a.k-2.t90", and has
a guide of its own: the seed's rendition in the singer's arrangement of the set's
form (a turn, two bars of the band alone, between every two sung sections, so no
two touch and a singer can come in again), at that key and speed, with no variants
drawn. Its score, every mix above, and two stems for making a singer's version:

    band     the full mix without the lead voice: the band, the room it plays in, and
             their share of the mix's glue and tone, unmastered, at the full mix's levels
    lead     the lead voice alone, with its own share of the room, the same way. band +
             lead is the full mix before mastering, to within rounding, so master(band +
             lead) is the full guide (split())

    renders/guide/<song>/<spec>.score.json           the score every mix of it follows ("spec" in it)
    renders/guide/<song>/<spec>.<mix>.wav            full, melody, voice: 16-bit, mastered
    renders/guide/<song>/<spec>.<band|lead>.wav      the stems: float, unmastered, when asked for
    renders/guide/<song>/<spec>.note.json            what they were made from

Each is made when first asked for and kept until what it was made from changes: the
genome, the set, the code (arranging(), recipe()), or a phrasing given to sing it
with. Writing a spec's score alone (the words and their windows, for the page) takes a
moment; its mixes about half a minute. A phrasing (tools/phrasing.py's, a person's or
everyone's) moves only the machine's singing in the full guide, the voice and the
lead: the score stays the grid, which the words on the page and every take's
measuring follow.

For tools/versions.py, a singer's version of the song:

    stems(genome_path, spec) -> (band_wav, lead_wav, score_json)   rendered if missing
    voice_strip(x, sr, seed) -> stereo    a dry mono voice through the strip and room the
                                          machine's lead gets in the full mix (as in the
                                          voice guide), unmastered: a take in its place

    uv run python tools/guides.py songs/h-now-its-by-you.json melody                  # the single guide
    uv run python tools/guides.py songs/h-now-its-by-you.json melody --spec a.k-2.t90 --stems
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import threading
import warnings
from dataclasses import fields, replace
from pathlib import Path
from typing import NamedTuple

import numpy as np

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import takes as K  # noqa: E402  (tools/takes.py)

from songbird.phrasing import Gesture  # noqa: E402
from songbird.score import Note, Score  # noqa: E402

ROOT = Path(__file__).parent.parent
GUIDES = ROOT / "renders" / "guide"
MIXES = ("melody", "full", "voice")
DEFAULT = "melody"

# The melody's instrument: the band's whistle (songbird.synth.pipe) played for a singer to follow.
# Measured on H's sung notes (harvest f0 against the score): within 5 cents at the 95th percentile,
# every note held (96% of each within 10 dB of its peak), 17 dB between repeated notes, breath hiss
# 39 dB under the tone. The lute was as clear but let long notes die (59% held); a pure tone
# was clean but isn't one of the song's instruments. So low (220-500 Hz) the model is nearly a sine
# (its 2nd and 3rd harmonics 16-20 dB down, whatever the brightness), which a singer's own voice
# covers in the headphones; a second whistle an octave up, 9 dB down, gives it a wooden flute's
# strong second harmonic and carries it over them, the pitch where it's written.
WHISTLE = dict(brightness=0.4, wear=0.0, breathiness=0.3, vibrato=0.3)
OCTAVE_DB = -9.0
STATED = 0.5  # the band's statement of the tune where no one sings, against the singer's level
MELODIC = ("whistle", "fiddle", "lute", "melody")  # parts that can state the tune ("melody": scores from before the band)
REST = 2.0  # seconds without singing before a line is counted in, and the band's statement is heard
# The pulse: a small woodblock. Nothing under 600 Hz, so it can't cover the tune's fundamentals; 27 ms
# long, a little to the right of the tune. Its levels (first 20 ms, against the tune's typical level):
# a beat, a downbeat (a major third higher), and the four beats that count in a line after a rest
# (higher, louder). Under the singing it steps back DUCK_DB: it keeps time without setting it, since
# a click to sing to would press the singer's own timing, which the takes are for, onto the grid.
TOCK = 1150.0  # Hz, the block's lowest mode
PULSE_DB = {"beat": -15.0, "downbeat": -12.0, "count": -9.0}
DUCK_DB = 6.0
COUNT = 4
PULSE_PAN = 0.2
ROOM = dict(rt60=0.7, wet=0.1)  # a small room around the whistle, so it isn't clinical; the pulse stays dry

# Specs: what a singer may choose.
SETS = ROOT / "tools" / "sets"  # <song>.json: the recording sets (tools/recording_sets.py)
KEYS = (-4, -2, 0, 2, 4)  # semitones from the song's own key
TEMPOS = (100, 90, 80)  # percent of the song's own tempo
STEMS = ("band", "lead")
TURN = "turn"  # what the singer's arrangement puts between two sung sections: the band alone, two bars
SONG = {"id": "song", "name": "The song", "about": "the song's own words, in its own form"}  # no sets file yet
SET_ID = re.compile(r"^[a-z0-9]{1,8}$")
SPEC_ID = re.compile(r"^([a-z0-9]{1,8})\.k(-?\d{1,2})\.t(\d{1,3})$")

_lock = threading.Lock()
_spec_locks: dict[tuple[str, str], threading.Lock] = {}
_registry = threading.Lock()


class Mix(NamedTuple):
    wav: Path  # the mix to sing to
    score: Path  # the score every mix follows
    digest: str  # the score's digest, when the mix was made from it


def full_paths(stem: str) -> tuple[Path, Path]:
    """The full guide's WAV and the score every mix follows."""
    return GUIDES / f"{stem}.guide.wav", GUIDES / f"{stem}.guide.score.json"


def mix_path(stem: str, mix: str) -> Path:
    if mix not in MIXES:
        raise ValueError(f"no guide mix {mix!r}; there are {', '.join(MIXES)}")
    return full_paths(stem)[0] if mix == "full" else GUIDES / f"{stem}.guide.{mix}.wav"


def recipe() -> str:
    """What a derived mix depends on beyond its score: this file, the synthesis it calls (the
    learned throat's weights too), the phonetics."""
    h = hashlib.sha256(Path(__file__).read_bytes())
    synth = ROOT / "songbird" / "synth"
    for f in [*sorted(synth.glob("*.py")), *sorted(synth.glob("*.npz")), ROOT / "songbird" / "phonetics.py"]:
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


def arranging() -> str:
    """What a spec's score depends on beyond the genome and its set: this file and the rest of
    songbird (the realization, the arranging of its words, the band's parts)."""
    h = hashlib.sha256(Path(__file__).read_bytes())
    for f in sorted((ROOT / "songbird").glob("*.py")):
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


def load_score(path: Path) -> tuple[Score, dict]:
    """A guide score as written by write_guide: the Score, and the file's data (tempo, seed, beats...)."""
    data = json.loads(Path(path).read_text())
    known = {f.name for f in fields(Note)}
    notes = []
    for n in data["notes"]:
        n = {k: v for k, v in n.items() if k in known}
        if n.get("gesture"):
            n["gesture"] = Gesture(**n["gesture"])
        notes.append(Note(**n))
    score = Score(tuple(notes), float(data["duration"]), tuple(tuple(s) for s in data["sections"]),
                  data.get("lexicon") or {}, data.get("band") or {})
    return score, data


def fresh(genome_path: Path) -> bool:
    """Whether the full guide on disk is current: written since the genome last changed, by a
    write_guide that keeps the beats (older ones don't)."""
    wav, score = full_paths(genome_path.stem)
    if not (wav.exists() and score.exists()) or wav.stat().st_mtime < Path(genome_path).stat().st_mtime:
        return False
    return '"beats"' in score.read_text()


def ensure(genome_path: Path, genome=None, mix: str = "full", rebuild: bool = False) -> Mix:
    """The guide mix to sing to, the score it follows and that score's digest, rendering whatever
    is missing or stale. genome: what to render if the full guide must be written (default: the
    genome file as it is now). A guide written transposed stays transposed. rebuild: write the
    full guide again from the current code (the other mixes follow)."""
    import phrasing as T  # tools/phrasing.py, imported late: it brings the aligner and whisper with it

    from songbird import genome as G

    genome_path = Path(genome_path)
    out = mix_path(genome_path.stem, mix)
    with _lock:
        wav, score = full_paths(genome_path.stem)
        if rebuild or not fresh(genome_path):
            transpose = json.loads(score.read_text()).get("transpose", 0) if score.exists() else 0
            with contextlib.redirect_stdout(io.StringIO()):
                T.write_guide(genome_path, genome if genome is not None else G.load(genome_path), transpose)
        digest = K.digest(score)
        if mix != "full":
            stamp = {"score": digest, "recipe": recipe()}
            note = out.with_suffix(".json")
            if not out.exists() or not note.exists() or json.loads(note.read_text()) != stamp:
                write_mix(score, mix, out)
                note.write_text(json.dumps(stamp) + "\n")
        return Mix(out, score, digest)


def write_mix(score_path: Path, mix: str, out: Path) -> Path:
    """Render one mix from a guide score to a 16-bit WAV at out (whole or not at all)."""
    import soundfile as sf

    from songbird import synth
    from songbird.synth import master

    score, data = load_score(score_path)
    seed = int(data.get("seed", 0))
    if mix == "melody":
        if "beats" not in data:
            raise ValueError(f"{score_path} keeps no beats: write the guide again (tools/phrasing.py --guide)")
        x = render_melody(score, [(float(t), bool(b)) for t, b in data["beats"]], synth.SR, seed)
    elif mix == "voice":
        x = render_voice(score, synth.SR, seed)
    else:
        raise ValueError(f"the {mix} guide is written by tools/phrasing.py --guide")
    pcm = master.to_pcm16(master.master(x, synth.SR), seed=seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(f"{out.stem}.{os.getpid()}.part.wav")
    sf.write(str(part), pcm, synth.SR, subtype="PCM_16")
    os.replace(part, out)
    return out


# --- specs: a set, a key, a speed ---------------------------------------------------------------


class Spec(NamedTuple):
    """What a singer chose to sing to: a set, a key (semitones from the song's own) and a speed
    (percent of its tempo). Its id, "a.k-2.t90", names its guide everywhere (no "+": it would
    break a query string)."""

    set: str
    key: int = 0
    tempo: int = 100

    @property
    def id(self) -> str:
        return f"{self.set}.k{self.key}.t{self.tempo}"

    def to_dict(self) -> dict:
        return {"id": self.id, "set": self.set, "key": self.key, "tempo": self.tempo}

    @classmethod
    def parse(cls, text) -> Spec:
        """A spec from its id, one of the keys and speeds on offer; ValueError if it isn't."""
        if isinstance(text, Spec):
            return text
        m = SPEC_ID.match(str(text or ""))
        spec = cls(m[1], int(m[2]), int(m[3])) if m else None
        if spec is None or spec.id != text:
            raise ValueError(f"no spec {text!r}: a spec is <set>.k<key>.t<tempo>, as a.k-2.t90")
        if spec.key not in KEYS or spec.tempo not in TEMPOS:
            raise ValueError(f"no spec {text!r}: the keys are {', '.join(map(str, KEYS))} and the speeds "
                             f"{', '.join(map(str, TEMPOS))}")
        return spec


def sets(genome_path: Path, genome=None) -> list[dict]:
    """The song's recording sets, in order, each {"id", "name", "about", "form", "words"}: from
    tools/sets/<song>.json, or while there is none the song itself (SONG), its own words (words
    None) in its own form. A set without words sings the song's own; one without a form, the
    song's."""
    path = SETS / f"{Path(genome_path).stem}.json"
    data = json.loads(path.read_text()) if path.exists() else {"sets": [SONG]}
    out = []
    for s in data.get("sets") or []:
        if not SET_ID.match(str(s.get("id", ""))):
            raise ValueError(f"{path.name}: a set's id is 1 to 8 lowercase letters and digits, not {s.get('id')!r}")
        if not s.get("form"):
            from songbird import genome as G
            from songbird.realize import choose_params

            genome = genome if genome is not None else G.load(genome_path)
            s = {**s, "form": list(choose_params(genome).form)}
        out.append({"id": s["id"], "name": s.get("name") or f"Set {s['id'].upper()}", "about": s.get("about", ""),
                    "form": [str(name) for name in s["form"]], "words": s.get("words") or None})
    ids = [s["id"] for s in out]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError(f"{path.name}: {'no sets' if not ids else 'two sets with one id'}")
    return out


def find_set(genome_path: Path, name: str, genome=None) -> dict:
    """One of the song's sets, by id; ValueError if it has none by that name."""
    for s in sets(genome_path, genome):
        if s["id"] == name:
            return s
    raise ValueError(f"no set {name!r} for {Path(genome_path).stem}")


def variants(genome_path: Path) -> dict:
    """What a singer may choose between, and what they hear if they don't choose (the first set,
    in the song's own key and speed, the melody)."""
    have = sets(genome_path)
    return {"sets": [{k: s[k] for k in ("id", "name", "about")} for s in have], "keys": list(KEYS),
            "tempos": list(TEMPOS), "mixes": list(MIXES),
            "default": {"set": have[0]["id"], "key": 0, "tempo": 100, "mix": DEFAULT}}


def arrangement(genome, form) -> tuple[str, ...]:
    """The singer's arrangement of a form: a turn (TURN, the band alone) between every two sung
    sections, so no two touch; where something unsung already stands between them (an existing
    turn, a break), nothing is added."""
    if TURN not in genome.sections:
        raise ValueError(f"{genome.title} has no {TURN} section to put between sung ones")
    out: list[str] = []
    for name in form:
        if out and genome.section(name).lyrics and genome.section(out[-1]).lyrics:
            out.append(TURN)
        out.append(name)
    return tuple(out)


def realized(genome, chosen: dict, spec: Spec) -> dict:
    """A spec's score as its file keeps it (write_guide's, plus "spec"): the seed's rendition, no
    variants drawn, in the singer's arrangement of the set's form, the key moved and the tempo
    scaled; the set's words (arrange.sing) or the song's own."""
    from songbird import arrange
    from songbird.realize import choose_params, realize, timeline

    seed = choose_params(genome)
    form = arrangement(genome, chosen["form"])
    params = replace(seed, form=form, tempo=seed.tempo * spec.tempo / 100.0, tonic=seed.tonic + spec.key, variants=())
    lyrics = arrange.sing(genome, form, chosen["words"]) if chosen.get("words") else None
    score = realize(genome, params, lyrics=lyrics)
    beats = [[t, int(bar)] for t, bar in timeline(genome, params).beats()]  # [seconds, 1 if it begins a bar]
    return {**score.to_dict(), "tempo": params.tempo, "seed": params.seed, "transpose": spec.key, "beats": beats,
            "spec": spec.to_dict()}


def spec_path(stem: str, spec, part: str) -> Path:
    """A spec's file: its score ("score"), a mix (full, melody, voice), a stem (band, lead), or the
    note of what they were made from ("note")."""
    spec = Spec.parse(spec).id
    if part in ("score", "note"):
        return GUIDES / stem / f"{spec}.{part}.json"
    if part not in MIXES + STEMS:
        raise ValueError(f"no guide mix {part!r}; there are {', '.join(MIXES)}")
    return GUIDES / stem / f"{spec}.{part}.wav"


def _spec_lock(stem: str, spec: str) -> threading.Lock:
    with _registry:
        return _spec_locks.setdefault((stem, spec), threading.Lock())


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _write(path: Path, text: str) -> None:
    """Whole or not at all, whoever else is writing it (the karaoke and a site build may both be)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.part")
    part.write_text(text)
    os.replace(part, path)


def _inputs(genome_path: Path, chosen: dict, spec: Spec) -> str:
    """What a spec's score is made from: the genome as it is on disk, the set's form and words,
    the key and speed, and the code that arranges and realizes it."""
    h = hashlib.sha256(Path(genome_path).read_bytes())
    h.update(json.dumps({"form": chosen["form"], "words": chosen.get("words"), "spec": spec.id}, sort_keys=True).encode())
    h.update(arranging().encode())
    return h.hexdigest()[:12]


def _current(genome_path: Path, spec: Spec) -> tuple[Path | None, dict]:
    """A spec's score if it is current (and the note), else None."""
    from songbird import genome as G

    genome = G.load(genome_path)
    path, note = spec_path(genome_path.stem, spec, "score"), _read(spec_path(genome_path.stem, spec, "note"))
    want = _inputs(genome_path, find_set(genome_path, spec.set, genome), spec)
    fresh = path.exists() and note.get("inputs") == want and note.get("score") == K.digest(path)
    return (path if fresh else None), {**note, "inputs": want}


def _score(genome_path: Path, spec: Spec, rebuild: bool = False) -> Path:
    """A spec's score, written if missing or stale (the caller holds its lock). Written again the
    same, it keeps what was made from it."""
    from songbird import genome as G

    path, note = _current(genome_path, spec)
    if path is not None and not rebuild:
        return path
    genome = G.load(genome_path)
    path = spec_path(genome_path.stem, spec, "score")
    _write(path, json.dumps(realized(genome, find_set(genome_path, spec.set, genome), spec)) + "\n")
    digest = K.digest(path)
    made = note.get("audio") if note.get("score") == digest and not rebuild else None
    _write(spec_path(genome_path.stem, spec, "note"),
           json.dumps({"inputs": note["inputs"], "score": digest, **({"audio": made} if made else {})}) + "\n")
    return path


def spec_score(genome_path: Path, spec) -> Path:
    """A spec's score, the words and beats the page shows and every take of it is measured
    against, written if missing or stale: quick, with no audio."""
    genome_path, spec = Path(genome_path), Spec.parse(spec)
    path, _ = _current(genome_path, spec)
    if path is not None:  # while its mixes render, it's current: nothing waits for them
        return path
    with _spec_lock(genome_path.stem, spec.id):
        return _score(genome_path, spec)


def ensure_spec(genome_path: Path, spec, mix: str = DEFAULT, stems: bool = False, phrasing: Path | None = None,
                rebuild: bool = False) -> Mix:
    """A spec's mix (or stem) to sing to, the score it follows and that score's digest, rendering
    whatever is missing or stale: every mix at once (they share the band), and the stems too if
    asked for (or if the one asked for is a stem). phrasing: a phrasing file the machine's lead
    sings with in the full guide, the voice and the lead stem (None: the grid's own way). rebuild:
    write the score and render everything again from the current code."""
    genome_path, spec = Path(genome_path), Spec.parse(spec)
    stem = genome_path.stem
    out = spec_path(stem, spec, mix)
    stems = stems or mix in STEMS
    with _spec_lock(stem, spec.id):
        score = _score(genome_path, spec, rebuild)
        digest = K.digest(score)
        note_path = spec_path(stem, spec, "note")
        note = _read(note_path)
        stamp = made_from(score, phrasing)
        made = note.get("audio") or {}
        wanted = [*MIXES, *(STEMS if stems else ())]
        if (rebuild or {k: made.get(k) for k in stamp} != stamp or (stems and not made.get("stems"))
                or not all(spec_path(stem, spec, p).exists() for p in wanted)):
            write_spec(score, stem, spec.id, stems=stems or bool(made.get("stems")) and not rebuild, phrasing=phrasing)
            note = {**_read(note_path), "audio": {**stamp, "stems": stems or bool(made.get("stems")) and not rebuild}}
            _write(note_path, json.dumps(note) + "\n")
        return Mix(out, score, digest)


def made_from(score: Path, phrasing: Path | None = None) -> dict:
    """What a spec's audio is made from: its score (by digest), the code that renders it, and the
    phrasing its lead sings with. Anything made from its mixes (an MP3) is current while this is."""
    return {"score": K.digest(score), "recipe": recipe(), "phrasing": K.digest(phrasing) if phrasing else None}


def stems(genome_path: Path, spec, phrasing: Path | None = None) -> tuple[Path, Path, Path]:
    """A spec's band and lead stems and its score, rendered if missing or stale (split())."""
    band = ensure_spec(genome_path, spec, "band", stems=True, phrasing=phrasing)
    return band.wav, spec_path(Path(genome_path).stem, spec, "lead"), band.score


def write_spec(score_path: Path, stem: str, spec: str, stems: bool = False, phrasing: Path | None = None) -> None:
    """Render a spec's guides from its score: full, melody and voice, mastered, as 16-bit WAVs;
    with stems, the band and the lead, unmastered, as float WAVs (split()). Each file whole or
    not at all."""
    from songbird import synth
    from songbird.synth import master, mixing

    score, data = load_score(score_path)
    seed, sr = int(data.get("seed", 0)), synth.SR
    parts = synth.render_stems(phrased(score, data, phrasing) if phrasing else score, sr, seed)
    taps: dict = {}
    full = mixing.mix(parts, sr, seed, taps=taps)
    alone: dict = {}
    voice = mixing.mix({"voice": parts["voice"]}, sr, seed, taps=alone) if "voice" in parts else np.zeros((1, 2))
    beats = [(float(t), bool(b)) for t, b in data["beats"]]
    for mix, x in (("full", full), ("voice", voice), ("melody", render_melody(score, beats, sr, seed))):
        _write_wav(spec_path(stem, spec, mix), master.to_pcm16(master.master(x, sr), seed=seed), sr, "PCM_16")
    if stems:
        band, lead = split(full, taps, voice, alone, sr)
        _write_wav(spec_path(stem, spec, "band"), band.astype(np.float32), sr, "FLOAT")
        _write_wav(spec_path(stem, spec, "lead"), lead.astype(np.float32), sr, "FLOAT")
    else:  # stems from an earlier render no longer match
        for name in STEMS:
            spec_path(stem, spec, name).unlink(missing_ok=True)


def _write_wav(path: Path, x: np.ndarray, sr: int, subtype: str) -> None:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.part.wav")
    sf.write(str(part), x, sr, subtype=subtype)
    os.replace(part, path)


def split(full: np.ndarray, taps: dict, voice: np.ndarray, alone: dict, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """The full mix (mixing.mix, taps from it) as band + lead. The lead: the voice bus and its own
    share of the room (the voice mixed alone: the same strip, the same sends, the same room, which
    gives way to it the same), through the full mix's glue and tone. The mix's last stage is
    linear once the glue's gain is known, so the lead is the voice's part of the full mix; the
    band is the rest. What the room's peak stage rounds off in one and not the other is all
    that can leak between them. Checked by the voice mix itself: the same last stage, with its
    own glue, must give it back, or mixing.mix has changed and this with it."""
    from songbird.synth import fx, mixing

    def last(x, glue):
        return fx.equalize(fx.apply_gain(x, glue), fx.design(mixing.WARMTH, sr))

    lead = alone["wet"].copy()
    lead[: len(alone["voice"])] += alone["voice"]
    if len(lead) != len(full) or np.max(np.abs(last(lead, alone["glue"]) - voice)) > 1e-6 * max(np.max(np.abs(voice)), 1e-9):
        raise RuntimeError("songbird.synth.mixing.mix no longer ends as guides.split() takes it apart: update split()")
    lead = last(lead, taps["glue"])
    return full - lead, lead


def voice_strip(x: np.ndarray, sr: int = 44100, seed: int = 0) -> np.ndarray:
    """A dry mono voice (a take) through the strip and room the machine's lead gets in the full mix,
    as its voice guide has them: stereo, unmastered, brought to the level the lead is, and as long
    as the voice plus the room's tail."""
    from songbird import synth

    mono = np.asarray(x, dtype=np.float64).reshape(len(x), -1).mean(axis=1)
    return synth.mix({"voice": synth.pan(mono, 0.0) * synth.VOICE_GAIN}, sr, seed)


def phrased(score: Score, data: dict, phrasing: Path) -> Score:
    """The score with its lead singing a phrasing's way, each note as realize() sings it with that
    phrasing (sung_as: early or late, held longer or shorter, its gesture carried to the singer);
    the band as it was. Only for the sound: the score file stays the grid."""
    from songbird import phrasing as P
    from songbird.realize import sung_as

    ways = P.from_json(json.loads(Path(phrasing).read_text()))
    beat = 60.0 / float(data["tempo"])
    sung, k = [], 0
    for n in sorted(score.part("voice"), key=lambda n: n.start):  # k: the note's place in its line, its phrase's
        sung.append(sung_as(n, P.gesture(ways, n.phrase, k), beat))
        k = 0 if n.line_end else k + 1
    notes = [n for n in score.notes if n.part != "voice"] + sung
    return replace(score, notes=tuple(sorted(notes, key=lambda n: (n.start, n.part, n.pitch))))


# --- the melody ------------------------------------------------------------------------------


def rests(sung: list[Note], duration: float, rest: float = REST) -> list[tuple[float, float]]:
    """Every stretch of `rest` seconds or more without singing: before the first sung note, between
    two, after the last."""
    bounds = [0.0] + [t for n in sung for t in (n.start, n.start + n.dur)] + [duration]
    return [(a, b) for a, b in zip(bounds[0::2], bounds[1::2]) if b - a >= rest]


def entries(sung: list[Note], rest: float = REST) -> list[float]:
    """Where the singer comes in: the first sung note, and every one after a rest of `rest` seconds or more."""
    out = [n.start for k, n in enumerate(sung) if k == 0 or n.start - (sung[k - 1].start + sung[k - 1].dur) >= rest]
    return out


def one_line(notes: list[Note]) -> list[Note]:
    """Notes as one line: each ends by the time the next begins."""
    notes = sorted(notes, key=lambda n: (n.start, n.pitch))
    return [replace(n, dur=max(min(n.dur, m.start - n.start), 0.01)) for n, m in zip(notes, notes[1:])] + notes[-1:]


def melody_line(score: Score) -> list[Note]:
    """The tune for the whistle: every sung note ("sung"), tongued, as the singer sings it; and in
    each stretch of REST seconds or more where no one sings, the notes of the band's part that
    states the tune there (the one with most notes) at the band's own octave, with the players'
    dynamics at STATED of the singer's level ("stated"). Each is one line: a note ends by the time
    the next begins."""
    sung = sorted(score.part("voice"), key=lambda n: n.start)
    stated = []
    if sung:
        loud = float(np.median([n.vel for n in sung]))
        for a, b in rests(sung, score.duration):
            # a statement starts after the last sung note ends (give or take the players' timing) and
            # leaves the next line's start to the singer
            found = {p: [n for n in score.part(p) if a - 0.05 <= n.start < b - 0.1] for p in MELODIC}
            part = max(found, key=lambda p: len(found[p]))
            notes = found[part]
            if not notes:
                continue
            scale = STATED * loud / max(float(np.median([n.vel for n in notes])), 1e-3)
            stated += [replace(n, part="stated", vel=float(min(1.0, n.vel * scale)), dur=min(n.dur, b - n.start))
                       for n in notes]
    line = one_line([replace(n, part="sung", art="") for n in sung]) + (one_line(stated) if stated else [])
    return sorted(line, key=lambda n: (n.start, n.pitch))


def tock(downbeat: bool, sr: int) -> np.ndarray:
    """One stroke on a small woodblock: three damped modes and the knock of the stick, 90 ms, peak 1."""
    from scipy.signal import butter, sosfilt

    n = int(0.09 * sr)
    t = np.arange(n) / sr
    base = TOCK * (1.26 if downbeat else 1.0)
    y = np.zeros(n)
    for ratio, t60, amp in ((1.0, 0.06, 1.0), (2.21, 0.03, 0.35), (3.73, 0.015, 0.12)):
        y += amp * np.sin(2 * np.pi * base * ratio * t) * np.exp(-6.9 * t / t60)
    knock = sosfilt(butter(2, [800.0, min(5000.0, 0.45 * sr)], btype="bandpass", fs=sr, output="sos"),
                    np.random.default_rng(11).standard_normal(n))
    y += 0.3 * knock * np.exp(-t / 0.0015)
    rise = int(0.001 * sr)
    y[:rise] *= np.linspace(0.0, 1.0, rise)
    return y / np.max(np.abs(y))


def strokes(beats: list[tuple[float, bool]], sung: list[Note] = ()) -> list[tuple[float, str, float]]:
    """What the pulse plays on each beat: (seconds, "count", "downbeat" or "beat", dB against a
    downbeat). The COUNT beats before each entry (before it by more than the players' timing) count
    it in; a beat under the singing steps back DUCK_DB."""
    sung = sorted(sung, key=lambda n: n.start)
    counted = set()
    for e in entries(sung):
        counted.update([t for t, _ in beats if t < e - 0.05][-COUNT:])
    spans = [(n.start - 0.05, n.start + n.dur) for n in sung]
    out = []
    for t, bar in beats:
        kind = "count" if t in counted else "downbeat" if bar else "beat"
        db = PULSE_DB[kind] - PULSE_DB["downbeat"]
        if kind != "count" and any(a <= t < b for a, b in spans):
            db -= DUCK_DB
        out.append((t, kind, db))
    return out


def pulse(beats: list[tuple[float, bool]], sr: int, length: int, sung: list[Note] = ()) -> np.ndarray:
    """The pulse as a mono track `length` samples long, a downbeat's stroke peaking at 1 (strokes())."""
    sounds = {"count": tock(True, sr), "downbeat": tock(True, sr), "beat": tock(False, sr)}
    out = np.zeros(length)
    for t, kind, db in strokes(beats, sung):
        i = int(round(t * sr))
        if 0 <= i < length:
            y = sounds[kind][: length - i] * 10.0 ** (db / 20.0)
            out[i : i + len(y)] += y
    return out


def typical_level(x: np.ndarray, sr: int, notes: list[Note]) -> float:
    """The tune's typical level: the median RMS of 20 ms windows inside its notes."""
    w = int(0.02 * sr)
    levels = []
    for n in notes:
        a, b = int(n.start * sr), int((n.start + n.dur) * sr)
        for i in range(a, b - w, w):
            levels.append(np.sqrt(np.mean(x[i : i + w] ** 2)))
    return float(np.median(levels)) if levels else 0.0


def render_melody(score: Score, beats: list[tuple[float, bool]], sr: int, seed: int = 0) -> np.ndarray:
    """The melody guide, unmastered stereo: the whistle (and its octave, on the sung line) in the
    middle of a small room, the pulse dry beside it at PULSE_DB against the sung line's level."""
    from songbird.synth import pipe, room
    from songbird.synth.instruments import place

    length = int(np.ceil(score.duration * sr))
    line = melody_line(score)
    sung = [n for n in line if n.part == "sung"]
    stated = [n for n in line if n.part == "stated"]
    # the octave plays from the same seed, so its tuning and breath move with the line's
    tune = pipe.blow(sung, sr, length, np.random.default_rng([seed, 23]), **WHISTLE)
    tune += pipe.blow([replace(n, pitch=n.pitch + 12) for n in sung], sr, length, np.random.default_rng([seed, 23]),
                      **WHISTLE) * 10.0 ** (OCTAVE_DB / 20.0)
    level = typical_level(tune, sr, sung)
    if stated:
        tune += pipe.blow(stated, sr, length, np.random.default_rng([seed, 29]), **WHISTLE)
    click = pulse(beats, sr, length, sung)
    if level > 0:
        click *= level * 10.0 ** (PULSE_DB["downbeat"] / 20.0) / np.sqrt(np.mean(tock(True, sr)[: int(0.02 * sr)] ** 2))
    dry = place(tune, 0.0, 0.0) + place(click, PULSE_PAN, 0.0)
    ir = room.impulse_response(sr, rt60=ROOM["rt60"], seed=room.seed_of(ROOM["rt60"]))
    return room.apply(dry, ir, send=place(tune, 0.0, 0.0), wet=ROOM["wet"])


def render_voice(score: Score, sr: int, seed: int = 0) -> np.ndarray:
    """The machine's singer alone, through the voice's own strip and room, unmastered."""
    from songbird import synth
    from songbird.synth.voice import VoiceParams, sing

    length = int(np.ceil(score.duration * sr))
    y = sing(list(score.part("voice")), sr, VoiceParams(), seed, score.lexicon)[:length]
    stem = synth.pan(np.pad(y, (0, length - len(y))), 0.0) * synth.VOICE_GAIN
    return synth.mix({"voice": stem}, sr, seed)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    ap.add_argument("mix", nargs="?", default=DEFAULT, choices=MIXES + STEMS)
    ap.add_argument("--spec", help="a spec's guide, as a.k-2.t90 (default: the single guide)")
    ap.add_argument("--stems", action="store_true", help="with --spec: the band and lead stems too")
    ap.add_argument("--phrasing", help="with --spec: a phrasing file the machine's lead sings with (the score stays the grid)")
    ap.add_argument("--rebuild", action="store_true", help="render the full guide again from the current code first")
    args = ap.parse_args()
    if args.spec:
        mix = ensure_spec(Path(args.genome), args.spec, args.mix, args.stems, args.phrasing and Path(args.phrasing),
                          args.rebuild)
    elif args.mix in STEMS or args.stems or args.phrasing:
        raise SystemExit("stems and phrasings are made for a spec's guide: give --spec")
    else:
        mix = ensure(Path(args.genome), None, args.mix, args.rebuild)
    print(f"{mix.wav}  (score {mix.digest})")


if __name__ == "__main__":
    main()
