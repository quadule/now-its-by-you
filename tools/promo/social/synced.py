"""A synced cut: the first refrain, the bridge's first two lines, and the last refrain's last two lines (a
semitone up), each half-line (or word) from a different version, every chunk time-warped with
rubberband so its sung onsets land on one grid. Pitch is never changed.

The grid is the release's own onsets for each section, scaled to TEMPO and placed bar by bar. Each chunk runs
from just before its first sung onset to where the next chunk starts. Writes renders/promo/social/synced/
cut.wav and cut.json (every chunk: version, section, notes, target times).
"""

import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[3]
S = ROOT / "renders/promo/social"
OUT = S / "synced"
RATE = 44100
TEMPO = 104.0
PRE = 0.07      # a cut lands this long before its first sung onset
XF = 0.025      # crossfade at each cut
RING = 3.5      # the last chunk rings this long after its last note ends
LEVEL = 0.12    # the RMS every version's section is brought to

# The keys: the first refrain all in D major; the bridge in D major with one turn to D minor ("like a coal");
# the last refrain all in E-flat major (no mixolydian: its flat seventh chord clashes across word-by-word cuts).
# (version, section, occurrence: 0 first or -1 last, first note, end note exclusive). Sections: refrain (40
# notes), bridge (its first two lines, 20 notes), lift (an instrumental bar: the last bar of the version's
# section named in place of the occurrence, that section's occurrence in place of the first note)
PLAN = [
    ("versions/release", "refrain", 0, 0, 4),        # Who made this song?
    ("versions/acappella", "refrain", 0, 4, 8),      # Nobody knows.
    ("versions/old78", "refrain", 0, 8, 10),         # It's yours
    ("lineages/c04/gen2", "refrain", 0, 10, 14),     # if you sing it,
    ("lineages/c00/gen5", "refrain", 0, 14, 18),     # and then who knows.
    ("versions/synthfolk", "refrain", 0, 18, 24),    # It's nobody's making,
    ("lineages/c05/gen3", "refrain", 0, 24, 29),     # it passes on through;
    ("lineages/c04/gen5", "refrain", 0, 29, 35),     # but somebody sang it,
    ("lineages/c09/gen1", "refrain", 0, 35, 40),     # and now it's by you.
    ("lineages/c04/gen5", "bridge", 0, 0, 5),        # Carry it over          (six voices)
    ("lineages/c09/gen4", "bridge", 0, 5, 10),       # the water and wire,
    ("lineages/c08/gen5", "bridge", 0, 10, 14),      # hand it along          (a slide on "a-", learned)
    ("lineages/c03/gen5", "bridge", 0, 14, 17),      # like a coal            (a flick on "coal", learned; D minor)
    ("lineages/c00/gen5", "bridge", 0, 17, 20),      # from the fire;
    ("lineages/c07/gen6", "refrain", -1, 18, 22),    # It's nobody's   (E-flat, where the bridge's third line would start)
    ("lineages/c08/gen4", "refrain", -1, 22, 24),    # making,
    ("lineages/c09/gen5", "refrain", -1, 24, 26),    # it's old
    ("lineages/c01/gen1", "refrain", -1, 26, 29),    # and it's new;
    ("lineages/c00/gen6", "refrain", -1, 29, 35),    # by everyone, no one,
    ("lineages/c04/gen3", "refrain", -1, 35, 40),    # and now it's by you.
]


def audio_of(v):
    return ROOT / "renders/release/now-its-by-you.flac" if v == "versions/release" else S / f"{v}.flac"


def section(score, name, occ):
    return [s for s in score["sections"] if s[0] == name][occ]


def notes(score, name, occ):
    _, a, b = section(score, name, occ)
    ns = [n for n in score["notes"] if n["part"] == "voice" and n["section"] == name and a - 2.0 <= n["start"] < b]
    if name == "bridge":
        ns = [n for n in ns if n["phrase"] in ("b1", "b2")]
    assert len(ns) == (40 if name == "refrain" else 20), (name, len(ns))
    return ns


def warp(x, src_pts, dst_pts, dur):
    """Stretch x (source time 0 at its first sample) so source time src_pts[j] lands at dst_pts[j]."""
    with tempfile.TemporaryDirectory(dir=S) as td:
        td = Path(td)
        sf.write(td / "in.wav", x, RATE, subtype="FLOAT")
        with open(td / "map.txt", "w") as f:
            last = -1
            for s, d in zip(src_pts, dst_pts):
                si = int(round(s * RATE))
                if si > last:
                    f.write(f"{si} {int(round(d * RATE))}\n")
                    last = si
        subprocess.run(["rubberband", "-q", "-3", "-M", str(td / "map.txt"), "-D", f"{dur:.6f}", str(td / "in.wav"), str(td / "out.wav")],
                       check=True, capture_output=True)
        y, _ = sf.read(td / "out.wav", dtype="float32", always_2d=True)
    n = int(round(dur * RATE))
    return np.pad(y, ((0, max(0, n - len(y))), (0, 0)))[:n]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rel = json.loads((S / "versions/release.score.json").read_text())
    k = 96.0 / TEMPO
    bar = 4 * 60.0 / TEMPO

    # where each section's downbeat lands: the first refrain's pickup at 0.5 s; the bridge where the refrain's
    # following bar would be; the last refrain placed so its third line ("It's nobody's making") comes where the
    # bridge's third line ("it's nobody's making and everyone's own") would
    r1 = section(rel, "refrain", 0)
    TA = 0.5 + (r1[1] - notes(rel, "refrain", 0)[0]["start"]) * k
    TBr = TA + 8 * bar
    TL = TBr + 4 * bar
    TB = TL - 4 * bar
    down = {("refrain", 0): (TA, r1[1]), ("bridge", 0): (TBr, section(rel, "bridge", 0)[1]),
            ("refrain", -1): (TB, section(rel, "refrain", -1)[1])}

    def grid(name, occ):
        T, start = down[(name, occ)]
        return [(n["start"] - start) * k + T for n in notes(rel, name, occ)]

    cache = {}

    def load(v):
        if v not in cache:
            x, sr = sf.read(audio_of(v), dtype="float32", always_2d=True)
            assert sr == RATE
            cache[v] = (x, json.loads((S / f"{v}.score.json").read_text()), json.loads((S / f"{v}.json").read_text()))
        return cache[v]

    # each chunk's anchors (source and target times) and where it starts on the target
    items = []
    for v, name, occ, i0, i1 in PLAN:
        x, score, rec = load(v)
        if name == "lift":
            line = section(score, occ, i0)[2]
            local = TEMPO / rec["params"]["tempo"]     # source seconds per target second
            items.append({"v": v, "name": name, "sp": [line - bar * local, line], "dp": [TL, TL + bar],
                          "start": TL, "local": local, "ns": None})
            continue
        ns = notes(score, name, occ)
        g = grid(name, occ)
        sp = [ns[i]["start"] for i in range(i0, i1)]
        dp = [g[i] for i in range(i0, i1)]
        if i1 < len(ns):   # the next onset of the same version keeps the ratio true to the end of the chunk
            sp.append(ns[i1]["start"])
            dp.append(g[i1])
        local = (sp[-1] - sp[0]) / (dp[-1] - dp[0]) if len(sp) > 1 else TEMPO / rec["params"]["tempo"]
        items.append({"v": v, "name": name, "occ": occ, "i0": i0, "i1": i1, "sp": sp, "dp": dp, "ns": ns, "g": g,
                      "start": dp[0] - PRE - (0.12 if not items else 0), "local": local})
    tail = items[-1]
    end_all = tail["g"][tail["i1"] - 1] + tail["ns"][tail["i1"] - 1]["dur"] / tail["local"] + RING

    mix = np.zeros((int((end_all + 1) * RATE), 2), np.float32)
    chunks = []
    for j, it in enumerate(items):
        x, score, rec = load(it["v"])
        d0 = it["start"]
        d1 = items[j + 1]["start"] if j + 1 < len(items) else end_all
        local = it["local"]
        sp, dp = it["sp"], it["dp"]
        # the anchors, extended linearly to the chunk's edges (with the crossfade margins)
        s0 = sp[0] - (dp[0] - (d0 - XF)) * local
        s1 = sp[-1] + ((d1 + XF) - dp[-1]) * local
        seg = x[int(round(s0 * RATE)):int(round(s1 * RATE))]
        inside = [(p, q) for p, q in zip(sp, dp) if s0 < p < s1]
        pts_s = [0.0] + [p - s0 for p, _ in inside] + [len(seg) / RATE]
        pts_d = [0.0] + [q - (d0 - XF) for _, q in inside] + [(d1 + XF) - (d0 - XF)]
        y = warp(seg, pts_s, pts_d, pts_d[-1])
        # level: the version's section at LEVEL (its last refrain for a lift bar), within 6 dB
        ns = it["ns"] or notes(score, "refrain", -1)
        span = x[int(ns[0]["start"] * RATE):int((ns[-1]["start"] + ns[-1]["dur"]) * RATE)]
        y *= float(np.clip(LEVEL / max(float(np.sqrt((span ** 2).mean())), 1e-6), 0.5, 2.0))
        if it["name"] == "lift":   # a turn is played softer than a sung refrain: bring the bar up to its neighbours
            y *= float(np.clip(LEVEL * 0.6 / max(float(np.sqrt((y ** 2).mean())), 1e-6), 1.0, 4.0))
        n = int(XF * 2 * RATE)
        ramp = np.linspace(0, 1, n, dtype=np.float32)[:, None]
        if j > 0:
            y[:n] *= ramp
        if j + 1 == len(items):
            m = int(2.5 * RATE)
            y[-m:] *= np.linspace(1, 0, m, dtype=np.float32)[:, None] ** 2
        else:
            y[-n:] *= ramp[::-1]
        at = int(round((d0 - XF) * RATE))
        mix[at:at + len(y)] += y
        p = rec["params"]
        entry = {"version": it["v"], "section": it["name"], "t0": round(d0, 4), "t1": round(d1, 4),
                 "style": (p.get("style") or {}).get("name"), "tonic": p["tonic"], "mode": p["mode"], "tempo": p["tempo"],
                 "generation": rec["generation"], "id": rec["id"][:12], "parent": (rec.get("parent_id") or "")[:12],
                 "ratio": round(1 / local, 3), "words": "", "sung": [],
                 # the warp: source times (in the version's file) and where they land; linear beyond, at local
                 "map": {"src": [round(v, 4) for v in sp], "dst": [round(v, 4) for v in dp], "local": round(local, 5),
                         "s0": round(s0, 4), "s1": round(s1, 4)}}
        if it["ns"]:
            entry.update({"occ": it["occ"], "i0": it["i0"], "i1": it["i1"],
                          "words": " ".join(it["ns"][i]["syllable"].replace("*", "") for i in range(it["i0"], it["i1"])),
                          "sung": [{"i": i, "syl": it["ns"][i]["syllable"], "t0": round(it["g"][i], 4),
                                    "t1": round(it["g"][i] + it["ns"][i]["dur"] / local, 4), "p": it["ns"][i]["pitch"],
                                    "orn": it["ns"][i].get("ornament")} for i in range(it["i0"], it["i1"])]})
        chunks.append(entry)
        print(f"{d0:6.2f}-{d1:6.2f} {it['name']:7} {it['v']:20} {entry['style']!s:10} t{p['tonic']} {p['mode'][:5]} "
              f"{p['tempo']:5.1f} x{1 / local:4.2f}  {entry['words']}")
    mix = mix[:int((end_all + 0.05) * RATE)]
    mix *= 0.93 / float(np.abs(mix).max())
    sf.write(OUT / "cut.wav", mix, RATE, subtype="PCM_24")
    (OUT / "cut.json").write_text(json.dumps({"tempo": TEMPO, "bar": bar, "duration": len(mix) / RATE, "chunks": chunks},
                                             ensure_ascii=False))
    print("duration", round(len(mix) / RATE, 2))


if __name__ == "__main__":
    main()
