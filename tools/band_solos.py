"""Each instrument of the band alone, playing its own part from a song's arrangement.

    uv run python tools/band_solos.py songs/h-now-its-by-you.json --out renders/band [--plots]

Writes <out>/solo-<instrument>.flac for the lute, guitar, harp, bass, fiddle,
whistle, drum and drone: the passage where that instrument has the most to
do (the melody instruments state the tune, as in an intro or a break), in the
song's room, mastered to -18 LUFS so they can be compared. With --plots, a
spectrogram and level envelope of each beside it.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import numpy as np

from songbird import genome as genome_mod, synth
from songbird.band import INSTRUMENTS, Band
from songbird.realize import choose_params, realize
from songbird.synth import instruments, master

# The section(s) each instrument is heard in, and how the band is set so it plays there.
PASSAGES = {
    "lute": (("break",), dict(lead="lute")),
    "guitar": (("refrain",), {}),
    "harp": (("verse",), {}),
    "bass": (("refrain",), {}),
    "fiddle": (("break",), dict(lead="fiddle")),
    "whistle": (("intro", "break"), dict(lead="whistle")),
    "drum": (("refrain",), dict(density=0.7)),
    "drone": (("bridge",), {}),
}


def solo(genome, name: str) -> tuple[np.ndarray, object]:
    form, settings = PASSAGES[name]
    params = choose_params(genome)
    alone = {other: 0.0 for other in INSTRUMENTS if other != name}
    band = Band.from_dict({**params.band.to_dict(), **alone, **settings})
    params = replace(params, form=tuple(f for f in form if f in genome.sections) or (params.form[0],), band=band)
    score = realize(genome, params)
    length = int(np.ceil(score.duration * synth.SR))
    stem = instruments.render_part(name, score.part(name), synth.SR, length, score.band, params.seed)
    return synth.mix({name: stem}, synth.SR, params.seed), score


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("genome")
    ap.add_argument("--out", default="renders/band")
    ap.add_argument("--only", nargs="*", default=list(INSTRUMENTS))
    ap.add_argument("--plots", action="store_true")
    args = ap.parse_args()
    genome = genome_mod.load(args.genome)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in args.only:
        mix, score = solo(genome, name)
        pcm = master.to_pcm16(master.master(mix, synth.SR, target=-18.0), seed=1)
        path = out / f"solo-{name}.flac"
        master.write_flac(path, pcm, synth.SR)
        print(f"{path}  {len(pcm) / synth.SR:.1f}s  {len(score.part(name))} notes")
        if args.plots:
            plot(pcm / 32768.0, path.with_suffix(".png"), name)


def plot(x: np.ndarray, path: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.signal import stft

    mono = x.mean(axis=1)
    f, t, z = stft(mono, synth.SR, nperseg=2048, noverlap=1536)
    db = 20 * np.log10(np.abs(z) + 1e-9)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(14, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    a1.pcolormesh(t, f, db, vmin=db.max() - 80, vmax=db.max(), cmap="magma", shading="auto")
    a1.set_yscale("symlog", linthresh=250)
    a1.set_ylim(30, 16000)
    a1.set_title(title)
    hop = int(0.01 * synth.SR)
    frames = mono[: len(mono) // hop * hop].reshape(-1, hop)
    a2.plot(np.arange(len(frames)) * 0.01, 20 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-9), lw=0.7)
    a2.set_ylim(-70, 0)
    a2.set_ylabel("dBFS")
    a2.set_xlabel("seconds")
    fig.tight_layout()
    fig.savefig(path, dpi=70)
    plt.close(fig)


if __name__ == "__main__":
    main()
