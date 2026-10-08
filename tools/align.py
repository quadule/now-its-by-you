"""Where each sung syllable's vowel begins, heard by a forced aligner (dev-only).

    uv run python tools/align.py songs/h-now-its-by-you.json recordings/milo/h-now-its-by-you-*.wav

tools/phrasing.py finds a take's vowel starts two ways and keeps the better
of them. Its own way warps the tune onto the pitch sung and starts each vowel
where the loudness climbs out of the consonant before it. This way asks the
Montreal Forced Aligner (MFA), a speech recognizer's acoustic model told the
words, where each vowel begins. MFA tells consonants from vowels far better
than a loudness curve can, but singing can throw it: now and then it squeezes
a run of words into a few frames and stretches one phone over the rest. So
its start is used where its own timing looks like singing of this tune
(plausible()) or where it agrees with ours to within GATE, less the bias it
shows for each class of sound before the vowel (MFA_BIAS); elsewhere ours
stands (combine()). How well that does against singers whose every vowel
start is known: docs/history/PHRASING-CALIBRATION.md.

How a take is aligned. Each lyric line is cut from the take, from its first
note's start - 0.5 s to its last note's end + 0.4 s (moved by the take's
lag), and aligned on its own with MFA's english_us_arpa acoustic model and
dictionary, beam 100 (retry 400). The last word of the line before and the
first of the line after join each line's transcript: the cut holds a little
of both, and without them MFA pinned a line's first vowel on the tail of the
line before. A high voice (median pitch above about 212 Hz) is first moved
down by whole octaves with WORLD, its spectral envelope and timing kept: the
speech-trained model lost its place in a soprano's lines until then. A word
the dictionary lacks is read as songbird.phonetics reads it.

MFA lives outside the repo: /Users/milo/Code/mfa (a micromamba env, its
models in mfa_root, a wrapper at bin/mfa). $MFA names another wrapper, and
MFA=off goes without. Without MFA, tools/phrasing.py measures with its own
onsets alone, as it did before. MFA runs one at a time on this machine
(lock(): two at once unpack the model into the same folder). Each take's
alignment is kept in renders/measured/mfa/ until the take's audio, the guide
it was sung to, the words or the settings here change; never because the
singer, the voice or the rest of the extractor did. The line cuts and MFA's
work files go in a temporary folder that is removed afterwards, so a
person's voice goes nowhere else.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "renders" / "measured" / "mfa"
HOME = Path("/Users/milo/Code/mfa")  # where MFA was installed (micromamba env, models, wrapper)
MODEL = "english_us_arpa"  # acoustic model and dictionary, US English in ARPAbet (the phones songbird.phonetics uses)
SR = 16000  # what the acoustic model was trained at
BEAM, RETRY_BEAM = 100, 400  # wider than MFA's 10/40: sung vowels last far longer than spoken ones
BEFORE, AFTER = 0.5, 0.4  # seconds of the take cut either side of a line's notes
LOWER_ABOVE = 150.0  # Hz: a voice is moved down round(log2(median pitch / this)) octaves, when that is 1 or more
GATE = 0.15  # seconds within which the aligner and our own onsets count as agreeing
# Where MFA puts a vowel's start against where it truly began (seconds, late +), by what comes before the vowel
# (tools/phrasing.py Guide.before): medians over the 8 Seed-VC reference takes (errors under 0.1 s), aligned as here.
MFA_BIAS = {"affricate": 0.0067, "aspirate": 0.0063, "fricative": 0.0051, "fricative+v": 0.0121, "glide+v": 0.0087,
            "liquid+v": 0.0132, "nasal+v": 0.0204, "stop": 0.0057, "stop+v": 0.0133, "vowel": -0.0006}
SKIP = {"", "sil", "sp", "spn", "<eps>"}  # MFA's silences and unknowns: not words or phones of the lyric
# How a take is cut, lowered, given its words and read back (prepare(), run()): bump it when a change there would
# change what an alignment says, and every take is aligned again. Kept alignments survive any other edit.
FORMAT = 1


class AlignError(RuntimeError):
    pass


# --- where MFA is -------------------------------------------------------------------


def executable() -> Path | None:
    """The mfa command, or None if there isn't one: $MFA (off to go without), else the install at HOME."""
    name = os.environ.get("MFA", str(HOME / "bin" / "mfa")).strip()
    if name.lower() in ("", "off", "no", "none", "0"):
        return None
    path = Path(name).expanduser()
    return path if path.is_file() and os.access(path, os.X_OK) else None


def models() -> Path:
    """MFA's own folder of saved models (as the wrapper sets it)."""
    exe = executable()
    base = exe.resolve().parent.parent if exe else HOME
    return Path(os.environ.get("MFA_ROOT_DIR") or base / "mfa_root")


def model_files() -> tuple[Path, Path]:
    saved = models() / "pretrained_models"
    return saved / "acoustic" / f"{MODEL}.zip", saved / "dictionary" / f"{MODEL}.dict"


def available() -> bool:
    """Whether MFA and its model are here to use."""
    return executable() is not None and all(f.exists() for f in model_files())


def lock_path() -> Path:
    exe = executable()
    return Path(os.environ.get("MFA_LOCK") or (exe.resolve().parent.parent if exe else HOME) / ".lock")


@contextlib.contextmanager
def lock():
    """Hold MFA for one run at a time on this machine; anything else that runs MFA should take it too.
    Two runs at once unpack the acoustic model into the same folder and one of them fails."""
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


@functools.cache
def mfa_version() -> str:
    """MFA's version, from its conda metadata (asking MFA itself takes seconds)."""
    exe = executable()
    if exe is None:
        return ""
    meta = sorted((exe.resolve().parent.parent / "env" / "conda-meta").glob("montreal-forced-aligner-*.json"))
    if meta:
        return meta[-1].name.removeprefix("montreal-forced-aligner-").rsplit("-", 1)[0]
    run = subprocess.run([str(exe), "version"], capture_output=True, text=True, check=False)
    return run.stdout.strip().splitlines()[-1] if run.stdout.strip() else "unknown"


# --- the lyric, as MFA reads it ----------------------------------------------------------


def token(word: str) -> str:
    """A written word as MFA reads it: lower case, no hyphens, only letters and apostrophes."""
    return re.sub(r"[^a-z']", "", (word or "").replace("-", "").replace("’", "'").lower()).strip("'")


def words(notes, lines) -> list[list[tuple[str, list[int]]]]:
    """Every line's words as MFA reads them, each with the indices of the notes it's sung on."""
    out = []
    for line in lines:
        row, i = [], 0
        while i < len(line):
            n = max(notes[line[i]].word_len, 1)
            row.append((token(notes[line[i]].word or notes[line[i]].syllable or ""), line[i : i + n]))
            i += n
        out.append(row)
    return out


def dictionary(wanted: set[str], path: Path, lexicon: dict) -> list[str]:
    """The stock dictionary's readings of the song's words (with MFA's own probabilities), and
    songbird.phonetics' reading of any it lacks, written to path. Returns the words it lacked."""
    from songbird import phonetics as ph

    keep, have = [], set()
    for line in model_files()[1].read_text().splitlines():
        w = line.split("\t", 1)[0]
        if w in wanted:
            keep.append(line)
            have.add(w)
    missing = sorted(wanted - have)
    for w in missing:
        for reading in ph.pronunciations(w, lexicon)[:2]:
            keep.append(f"{w}\t{' '.join(reading)}")
    path.write_text("\n".join(keep) + "\n")
    return missing


# --- the take ------------------------------------------------------------------------------


def load(wav: Path) -> np.ndarray:
    """The take as mono at SR, peak 0.9."""
    import soundfile as sf
    from scipy.signal import resample_poly

    y, sr = sf.read(str(wav), always_2d=True)
    y = y.mean(axis=1)
    y = resample_poly(y, SR, sr) if sr != SR else y
    return y / max(float(np.max(np.abs(y))), 1e-9) * 0.9


def octaves_down(y: np.ndarray) -> int:
    import pyworld

    f0, _ = pyworld.dio(y.astype(np.float64), SR, f0_floor=60.0, f0_ceil=1100.0, frame_period=10.0)
    v = f0[f0 > 0]
    return max(round(float(np.log2(np.median(v) / LOWER_ABOVE))), 0) if len(v) else 0


def lowered(x: np.ndarray, octaves: int) -> np.ndarray:
    """x moved down by whole octaves, its spectral envelope and timing kept (WORLD)."""
    import pyworld

    x = x.astype(np.float64)
    f0, t = pyworld.harvest(x, SR, f0_floor=60.0, f0_ceil=1100.0, frame_period=5.0)
    sp, ap = pyworld.cheaptrick(x, f0, t, SR), pyworld.d4c(x, f0, t, SR)
    y = pyworld.synthesize(f0 / 2**octaves, sp, ap, SR, frame_period=5.0)[: len(x)]
    y = np.pad(y, (0, max(len(x) - len(y), 0)))
    return y * (np.max(np.abs(x)) / max(np.max(np.abs(y)), 1e-9))


def textgrid(path: Path) -> dict[str, list[tuple[float, float, str]]]:
    """A TextGrid's interval tiers: words and phones, each [(start, end, label)]."""
    tiers = {}
    for block in re.split(r"item \[\d+\]:", path.read_text())[1:]:
        name = re.search(r'name = "(.*?)"', block).group(1)
        ivs = re.findall(r'xmin = ([\d.eE+-]+)\s*\n\s*xmax = ([\d.eE+-]+)\s*\n\s*text = "(.*?)"', block, re.DOTALL)
        tiers[name.split(" - ")[-1]] = [(float(a), float(b), t) for a, b, t in ivs]
    return tiers


def prepare(wav: Path, g, lag: float, work: Path) -> dict:
    """A take made ready for MFA in the folder work: its lines cut (lowered, for a high voice), each with its
    words, and a dictionary of the song's words. Nothing here needs the lock."""
    import soundfile as sf

    lyric = words(g.notes, g.lines)
    y = load(wav)
    octaves = octaves_down(y)
    corpus = work / "corpus" / "take"
    corpus.mkdir(parents=True)
    cuts = []
    for li, line in enumerate(g.lines):
        t0 = g.notes[line[0]].start - BEFORE + lag
        t1 = g.notes[line[-1]].start + g.notes[line[-1]].dur + AFTER + lag
        a, b = max(round(t0 * SR), 0), min(round(t1 * SR), len(y))
        chunk = y[a:b] if octaves == 0 else lowered(y[a:b], octaves)
        pre = [w for w, _ in lyric[li - 1][-1:]] if li else []
        post = [w for w, _ in lyric[li + 1][:1]] if li + 1 < len(g.lines) else []
        name = f"line{li:02d}"
        sf.write(str(corpus / f"{name}.wav"), (np.clip(chunk, -1, 1) * 32767).astype(np.int16), SR, subtype="PCM_16")
        (corpus / f"{name}.lab").write_text(" ".join(pre + [w for w, _ in lyric[li]] + post) + "\n")
        cuts.append((name, a / SR, len(pre), len(post)))
    missing = dictionary({w for row in lyric for w, _ in row}, work / "song.dict", g.lexicon)
    return {"work": work, "lyric": lyric, "cuts": cuts, "lag": lag, "notes": len(g.notes), "lowered": octaves,
            "missing": missing}


def run(job: dict, jobs: int | None = None) -> dict:
    """MFA over a prepared take (the caller holds lock()): every note's vowel start and end, its word's start
    and end (seconds on the guide's timeline; None where MFA gave nothing), and the phones MFA heard."""
    exe = executable()
    if exe is None:
        raise AlignError("MFA isn't installed")
    work, lag = job["work"], job["lag"]
    out = work / "aligned"
    cmd = [str(exe), "align", str(work / "corpus"), str(work / "song.dict"), MODEL, str(out), "-t", str(work / "tmp"),
           "-j", str(jobs or min(os.cpu_count() or 4, 8)), "--clean", "--single_speaker",
           "--beam", str(BEAM), "--retry_beam", str(RETRY_BEAM), "-q"]  # never --verbose: it asks GitHub first
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise AlignError(f"mfa align failed: {(done.stderr or done.stdout).strip()[-800:]}")

    heard = {k: [None] * job["notes"] for k in ("vowel_start", "vowel_end", "word_start", "word_end", "phones")}
    for li, (name, offset, pre, post) in enumerate(job["cuts"]):
        path = out / "take" / f"{name}.TextGrid"
        if not path.exists():
            continue
        tg = textgrid(path)
        got = [w for w in tg["words"] if w[2] not in SKIP]
        got = got[pre : len(got) - post]
        phones = [p for p in tg["phones"] if p[2] not in SKIP]
        i = 0
        for w, ix in job["lyric"][li]:  # in order; a word MFA didn't give back is skipped
            j = i
            while j < len(got) and got[j][2] != w:
                j += 1
            if j == len(got):
                continue
            a, b, _ = got[j]
            i = j + 1
            inside = [p for p in phones if p[0] >= a - 1e-6 and p[1] <= b + 1e-6]
            vowels = [p for p in inside if p[2][-1:].isdigit()]  # ARPAbet vowels carry a stress digit
            for m, k in enumerate(ix):  # a word's vowels go to its notes in order
                heard["word_start"][k], heard["word_end"][k] = round(offset + a - lag, 4), round(offset + b - lag, 4)
                heard["phones"][k] = " ".join(p[2] for p in inside)
                if m < len(vowels):
                    heard["vowel_start"][k] = round(offset + vowels[m][0] - lag, 4)
                    heard["vowel_end"][k] = round(offset + vowels[m][1] - lag, 4)
    return {"lowered": job["lowered"], "not_in_dictionary": job["missing"], **heard}


# --- kept per take -------------------------------------------------------------------------


def settings() -> dict:
    """What an alignment depends on besides the take and its guide."""
    acoustic, lexicon = model_files()
    return {"mfa": mfa_version(), "model": MODEL, "model_bytes": acoustic.stat().st_size if acoustic.exists() else 0,
            "dictionary_bytes": lexicon.stat().st_size if lexicon.exists() else 0, "beam": BEAM,
            "retry_beam": RETRY_BEAM, "cut": [BEFORE, AFTER], "lower_above": LOWER_ABOVE, "sr": SR, "format": FORMAT}


def fingerprint() -> str | None:
    """Which aligner a measurement had: None without MFA."""
    if not available():
        return None
    return hashlib.sha256(json.dumps(settings(), sort_keys=True).encode()).hexdigest()[:12]


def key(wav: Path, g, lag: float) -> dict:
    """Everything one take's alignment depends on: its audio, the guide and words it was sung to, the settings."""
    audio = hashlib.sha256(Path(wav).read_bytes()).hexdigest()[:16]
    lyric = hashlib.sha256(json.dumps(words(g.notes, g.lines)).encode()).hexdigest()[:12]
    return {"audio": audio, "guide": g.digest, "words": lyric, "lag": round(float(lag), 3), **settings()}


def sung_to(wav: Path) -> str | None:
    """The digest of the guide a take was sung to, as its sidecar says (a kept take's .json, a reference's
    .truth.json); None: the guide as it is now."""
    for side in (Path(wav).with_suffix(".truth.json"), Path(wav).with_suffix(".json")):
        if side.exists():
            digest = json.loads(side.read_text()).get("guide")
            if digest:
                return digest
    return None


def cache_path(wav: Path) -> Path:
    wav = Path(wav).resolve()
    name = wav.relative_to(ROOT).as_posix() if wav.is_relative_to(ROOT) else wav.as_posix().lstrip("/")
    return CACHE / (name.replace("/", "__").removesuffix(".wav") + ".json")


def aligned(wav: Path, g, lag: float = 0.0) -> dict | None:
    """One take as MFA heard it (see run()), aligned once and kept; None without MFA, or if it failed.
    g: the guide it was sung to (tools/phrasing.guide); lag: seconds the take runs behind it."""
    if not available():
        return None
    want = key(wav, g, lag)
    cache = cache_path(wav)

    def kept() -> dict | None:
        if cache.exists():
            data = json.loads(cache.read_text())
            if data.get("key") == want:
                return data
        return None

    data = kept()
    if data is not None:
        return data
    try:
        with tempfile.TemporaryDirectory(prefix="songbird-mfa-") as work:  # the take's cuts go when it closes
            job = prepare(Path(wav), g, lag, Path(work))
            with lock():
                data = kept()  # another process may have aligned it while this one waited
                if data is not None:
                    return data
                data = {"key": want, **run(job)}
    except (AlignError, OSError, subprocess.SubprocessError) as e:
        print(f"tools/align.py: {Path(wav).name}: {e}; its vowel starts are our own", file=sys.stderr)
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    part = cache.with_name(f"{cache.stem}.{os.getpid()}.part")
    part.write_text(json.dumps(data) + "\n")
    os.replace(part, cache)
    return data


# --- MFA's starts and ours, together ------------------------------------------------------------


def plausible(notes, vowel: np.ndarray, vowel_end: np.ndarray) -> np.ndarray:
    """Where MFA's own timing looks like singing of this tune: its vowel lasts at least a quarter of the note,
    the steps to the vowels either side (within the line) are within a factor of two of the tune's, and it is
    within 0.4 s of where the guide puts it. Where MFA has lost its place, one of these gives it away."""
    start = np.array([n.start for n in notes])
    dur = np.array([n.dur for n in notes])
    span = np.array([notes[k + 1].start - n.start if k + 1 < len(notes) and not n.line_end else n.dur
                     for k, n in enumerate(notes)])
    first = np.array([k == 0 or notes[k - 1].line_end for k in range(len(notes))])
    nxt = np.array([vowel[k + 1] if k + 1 < len(notes) and not notes[k].line_end else np.nan for k in range(len(notes))])
    with np.errstate(invalid="ignore"):
        step = (nxt - vowel) / span
        prev = np.concatenate([[np.nan], step[:-1]])
        prev[first] = np.nan
        ok = np.isfinite(vowel) & ((vowel_end - vowel) / dur >= 0.25) & (np.abs(vowel - start) <= 0.4)
        for x in (step, prev):
            ok &= ~np.isfinite(x) | ((x >= 0.5) & (x <= 2.0))
    return ok


def combine(ours: np.ndarray, heard: dict, notes, before: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Every note's vowel start (seconds on the guide's timeline) and whether it is MFA's: MFA's, less its bias
    for the sound before the vowel, where MFA is plausible or agrees with ours to within GATE; ours elsewhere."""
    vowel = np.array([np.nan if v is None else v for v in heard["vowel_start"]], dtype=float)
    end = np.array([np.nan if v is None else v for v in heard["vowel_end"]], dtype=float)
    mfa = vowel - np.array([MFA_BIAS.get(b, 0.0) for b in before])
    with np.errstate(invalid="ignore"):
        use = np.isfinite(mfa) & (plausible(notes, vowel, end) | (np.abs(mfa - ours) <= GATE))
    return np.where(use, mfa, ours), use


# --- by hand -------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    ap.add_argument("takes", nargs="+", help="WAVs sung along to the guide (a kept take, or a reference take)")
    ap.add_argument("--lag", default="0", help="seconds each take runs behind its guide, or 'measured' (tools/phrasing)")
    args = ap.parse_args()
    if not available():
        raise SystemExit(f"no MFA at {os.environ.get('MFA', HOME / 'bin' / 'mfa')} (or its {MODEL} model isn't saved)")
    sys.path.insert(0, str(Path(__file__).parent))
    import phrasing as T
    import takes as K

    from songbird import genome as G

    genome_path = Path(args.genome).resolve()
    genome = G.load(genome_path)
    for name in args.takes:
        wav = Path(name).resolve()
        g = T.guide(genome_path, genome, sung_to(wav))
        if args.lag == "measured":  # measuring the take aligns it too, at the lag it finds
            take = K.load(wav) if wav.is_relative_to(K.RECORDINGS) else wav
            lag = T.measured(genome_path, genome, take)["lag"]
        else:
            lag = float(args.lag)
        data = aligned(wav, g, lag)
        if data is None:
            continue
        vowel = np.array([np.nan if v is None else v for v in data["vowel_start"]], dtype=float)
        end = np.array([np.nan if v is None else v for v in data["vowel_end"]], dtype=float)
        ok = plausible(g.notes, vowel, end)
        print(f"{cache_path(wav).relative_to(ROOT)}: {len(g.notes)} notes, a vowel found for {np.isfinite(vowel).sum()},"
              f" plausible {ok.sum()}" + (f", lowered {data['lowered']} octave(s)" if data["lowered"] else ""))


if __name__ == "__main__":
    main()
