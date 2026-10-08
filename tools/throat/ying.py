"""New house singers' timbre prompts, made from our own voice by YingMusic-Singer (dev only).

    uv run python tools/throat/ying.py clips [--only blend-bright blend-baritone]   # the throat sings each
                                                         # singer's two windows of the guide
    $YING/.venv/bin/python -I tools/throat/ying_batch.py renders/throat/ying/pass1.json   # from $YING
    uv run python tools/throat/ying.py pick 1            # each clip's best seed, by Whisper then pitch
    $YING/.venv/bin/python -I tools/throat/ying_batch.py renders/throat/ying/pass2.json   # (recipe e only)
    uv run python tools/throat/ying.py pick 2
    uv run python tools/throat/ying.py plan              # plan-blend*.json: the house plans, sung by the new singers

The old house singers' prompts were our formant singer, and the artist hears the corpus SoulX sang in
those timbres as the robotic part of the voice. The new singers start from the shipped throat instead, as
each machine's own voice does: a blend of several house rows, mixed with the volunteers' row (everyone
who sang, as one singer) at a share between 0.3 and 0.6. YingMusic-Singer (ASLP-lab, CC BY 4.0; its Stability VAE's license bars training a
"foundational" model on its output, which the throat isn't) re-sings that clip in its own timbre, which
keeps it on key (a real singer's clip as the timbre drifted 30-40 cents) and makes it sound more natural.
Recipe d re-sings once, e twice (the artist: e "a slight edge", d "maybe more natural"); the high
singers alternate, the lower ones are all d. Each pass sings three seeds and keeps the one Whisper hears best, then the one nearest the
throat's pitch. The result is the singer's ten-second prompt; SoulX sings the corpus in it, to the
score's timing (YingMusic's own timing drags at phrase ends, so it only makes the prompt).

YingMusic needs its timbre clip to be the same voice singing other words: each singer's clip of the
guide's first refrain couplet (the prompt window corpus.py cuts) is sung in the timbre of its clip of the
second couplet, and the second in the timbre of the first.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from corpus import GUIDE, H, PROMPT_AT, PROMPT_LEN, SINGERS, THROAT  # noqa: E402

OUT = THROAT / "ying"
SR = 44100
SEEDS = (1, 2, 3)
# The guide's second refrain couplet, right after the prompt window: the other clip of each voice.
REF_AT, REF_LEN = 40.45, 10.75
TEXT = {
    "prompt": "who made this song nobody knows|it's yours while you sing it and then it goes",
    "ref": "it's nobody's making it's old and it's new|by everyone no one and now it's by you",
}


def singers() -> dict[str, dict]:
    """The new singers, one in each house singer's register and keys. Each is a machine's kind of voice:
    a random blend of the trained house singers who sing near that register (throat.machine_mix, here never
    more than 0.45 of any one: the artist heard a single house row as a step backward, and the blend that
    won had at most 0.43 of one), with the volunteers' row at a share spread over 0.3-0.6 so high and low
    voices both get the whole range. Recipes d and e alternate among the voices that sing in H's own key;
    every lower voice is re-sung once (the artist, on a bass at 57%: once sounded most natural, twice less)."""
    from songbird.synth import throat

    model = throat.load()
    house = sorted((n for n, sp in SINGERS.items() if sp["source"] == "formant"),
                   key=lambda n: -model.config["registers"][n])
    shares = np.linspace(0.3, 0.6, len(house))[[9, 0, 7, 2, 5, 4, 3, 6, 1, 8][: len(house)]]
    out = {}
    for i, (name, share) in enumerate(zip(house, shares)):
        draw = throat.parse_mix(throat.machine_mix(i, model.config["registers"][name], model, most=0.45))
        synthetic = {n: w for n, w in draw.items() if n != "volunteers"}
        total = sum(synthetic.values())
        mix = {n: w / total * (1 - share) for n, w in synthetic.items()} | {"volunteers": float(share)}
        out[name.replace("house-", "blend-")] = dict(house=name, share=round(float(share), 3), recipe="de"[i % 2] if SINGERS[name]["shift"] == 0 else "d",
                                                     shift=SINGERS[name]["shift"], mix=throat.blend_spec(mix))
    return out


def clips(only: list[str] | None) -> None:
    from songbird import genome as G
    from songbird.score import Note
    from songbird.synth.voice import VoiceParams, sing

    score = json.loads(GUIDE.read_text())
    known = {f.name for f in fields(Note)}
    notes = [Note(**{k: v for k, v in n.items() if k in known and k != "gesture"})
             for n in score["notes"] if n["part"] == "voice"]
    lexicon = G.load(H).lexicon
    for name, s in singers().items():
        if only and name not in only:
            continue
        mix = s["mix"]
        y = sing(notes, SR, VoiceParams(shift=s["shift"], timbre=mix), seed=1, lexicon=lexicon)
        y = 0.5 * y / max(float(np.max(np.abs(y))), 1e-9)
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        for clip, at, length in (("prompt", PROMPT_AT, PROMPT_LEN), ("ref", REF_AT, REF_LEN)):
            sf.write(d / f"{clip}.throat.wav", y[int(at * SR): int((at + length) * SR)], SR, subtype="PCM_16")
        (d / "singer.json").write_text(json.dumps(s, indent=1))
        print(f"{name:18} {mix}  recipe {s['recipe']}")
    jobs(1)


def jobs(p: int) -> None:
    """The YingMusic jobs of a pass (pass 2: recipe e's singers only, from pass 1's picks)."""
    out = []
    for name, s in singers().items():
        d = OUT / name
        if (p == 2 and s["recipe"] != "e") or not (d / "prompt.throat.wav").exists():
            continue
        src = (lambda c: d / f"{c}.throat.wav") if p == 1 else (lambda c: d / f"{c}.pass1.wav")
        for clip, other in (("prompt", "ref"), ("ref", "prompt")):
            for seed in SEEDS:
                out.append(dict(out=str(d / f"{clip}.pass{p}.s{seed}.wav"), ref_audio=str(src(other)),
                                ref_text=TEXT[other], melody_audio=str(src(clip)), target_text=TEXT[clip], seed=seed,
                                singer=name, clip=clip))
    (OUT / f"pass{p}.json").write_text(json.dumps(out, indent=1))
    print(f"{len(out)} jobs -> {OUT / f'pass{p}.json'}")


def lag_p90(a: np.ndarray, sa: int, b: np.ndarray, sb: int) -> float:
    """How far a re-sing runs from the clip it re-sang: the 90th percentile of |lag| along a DTW path over
    40-band log spectra (10 ms hop), in seconds. SoulX places a prompt's phones by the guide's timing alone
    (control "score" gives it no f0), so a prompt that drifts from it is mislabelled."""
    from numba import njit
    from scipy.signal import resample_poly, stft

    def bands(y, sr):
        f, t, z = stft(resample_poly(y, 16000, sr), 16000, nperseg=400, noverlap=240)
        power = np.abs(z) ** 2
        edges = np.linspace(0, 4000, 41)
        s = np.log(np.array([power[(f >= lo) & (f < hi)].sum(axis=0) for lo, hi in zip(edges[:-1], edges[1:])]) + 1e-8)
        return s - s.mean(axis=1, keepdims=True), t

    @njit(cache=True)
    def path(d):
        n, m = d.shape
        c = np.full((n + 1, m + 1), np.inf)
        c[0, 0] = 0.0
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                c[i, j] = d[i - 1, j - 1] + min(c[i - 1, j], c[i, j - 1], c[i - 1, j - 1])
        i, j, out = n, m, []
        while i > 0 and j > 0:
            out.append((i - 1, j - 1))
            k = np.argmin(np.array([c[i - 1, j - 1], c[i - 1, j], c[i, j - 1]]))
            i, j = (i - 1, j - 1) if k == 0 else ((i - 1, j) if k == 1 else (i, j - 1))
        return out

    (x, tx), (y, ty) = bands(a, sa), bands(b, sb)
    d = ((x[:, :, None] - y[:, None, :]) ** 2).mean(axis=0)
    pairs = np.array(path(d))
    return float(np.percentile(np.abs(ty[pairs[:, 1]] - tx[pairs[:, 0]]), 90))


def pick(p: int) -> None:
    import pyworld as pw
    from faster_whisper import WhisperModel
    from scipy.signal import resample_poly

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from intelligibility import align, normalize

    model = WhisperModel("base.en", device="cpu", compute_type="int8")

    def mono(path):
        y, sr = sf.read(str(path))
        return (y.mean(axis=1) if y.ndim > 1 else y), sr

    def f0(y, sr):
        return pw.harvest(y.astype(np.float64), sr, f0_floor=60, f0_ceil=900, frame_period=10)[0]

    best: dict[tuple[str, str], tuple] = {}
    for j in json.loads((OUT / f"pass{p}.json").read_text()):
        y, sr = mono(j["out"])
        segs, _ = model.transcribe(resample_poly(y, 16000, sr).astype(np.float32), language="en", beam_size=5)
        heard = normalize(" ".join(s.text for s in segs))
        edits = align(normalize(j["target_text"].replace("|", " ")), heard)[0]
        # pitch kept: against the throat's own clip, octave-free, where both are voiced
        throat, st = mono(OUT / j["singer"] / f"{j['clip']}.throat.wav")
        lag = lag_p90(y, sr, throat, st)
        a, b = f0(y, sr), f0(throat, st)
        n = min(len(a), len(b))
        both = (a[:n] > 0) & (b[:n] > 0)
        c = 1200 * np.log2(a[:n][both] / b[:n][both])
        cents = float(np.median(np.abs(c - 1200 * np.round(c / 1200))))
        key = (j["singer"], j["clip"])
        print(f"{j['singer']:18} {j['clip']:6} seed {j['seed']}  {edits} words misheard, {cents:4.0f} cents, "
              f"lag p90 {lag * 1000:3.0f} ms", flush=True)
        score = (edits, lag > 0.12, cents)  # words first, then timing within 120 ms, then pitch
        if key not in best or score < best[key][0]:
            best[key] = (score, lag, j["out"])
    for (name, clip), ((edits, _, cents), lag, path) in sorted(best.items()):
        y, sr = mono(path)
        n = sf.info(str(OUT / name / f"{clip}.throat.wav")).frames * sr // 44100  # exactly the window's length
        y = np.pad(y[:n], (0, max(n - len(y), 0)))
        sf.write(OUT / name / f"{clip}.pass{p}.wav", y, sr, subtype="PCM_16")
        print(f"best {name:18} {clip:6} {Path(path).name}: {edits} misheard, {cents:.0f} cents, lag p90 {lag * 1000:.0f} ms")
    if p == 1:
        jobs(2)


def plan() -> None:
    """plan-house.json and plan-house-cover.json, sung by the new singers: the same items, keys, tempos and
    seeds, so the two corpora differ only in the timbre prompts. Each singer's prompt is its last pass; a
    singer without one yet is left out."""
    for old in ("plan-house.json", "plan-house-cover.json"):
        src = json.loads((THROAT / old).read_text())
        new = {"singers": {}, "items": []}
        for name, s in singers().items():
            d = OUT / name
            wav = d / ("prompt.pass2.wav" if s["recipe"] == "e" else "prompt.pass1.wav")
            if not wav.exists():  # a singer whose prompt isn't made yet sings nothing
                continue
            entry = json.loads(json.dumps(src["singers"][s["house"]]))
            entry.update(source="ying", voice=json.loads((d / "singer.json").read_text()))
            entry["meta"].update(wav=str(wav), index=f"prompt_{name}")
            new["singers"][name] = entry
        for it in src["items"]:
            name = it["singer"].replace("house-", "blend-")
            if name not in new["singers"]:
                continue
            seg_from = f"{it['singer']}."
            it = json.loads(json.dumps(it))
            it.update(id=it["id"].replace(seg_from, f"{name}.", 1), singer=name, source="ying")
            for seg in it["segments"]:
                seg["index"] = seg["index"].replace(seg_from, f"{name}.", 1)
            new["items"].append(it)
        dest = THROAT / old.replace("house", "blend")
        dest.write_text(json.dumps(new, indent=1))
        mins = sum(s["t1"] - s["t0"] for it in new["items"] for s in it["segments"]) / 60
        print(f"{dest}: {len(new['items'])} items, {mins:.1f} min")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["clips", "pick", "plan"])
    ap.add_argument("passno", nargs="?", type=int, default=1)
    ap.add_argument("--only", nargs="*", default=None, help="clips: only these singers (blend-bright ...)")
    args = ap.parse_args()
    {"clips": lambda: clips(args.only), "pick": lambda: pick(args.passno), "plan": plan}[args.step]()


if __name__ == "__main__":
    main()
