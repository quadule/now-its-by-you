"""The social cut: which version sings each half-line, the joined audio, and what the page draws.

Reads renders/promo/social/versions/<name>.{flac,json,score.json} (render-versions.sh makes them) and
writes renders/promo/social/data/cut.json and cut.wav.

A chunk is a run of the lead's notes in one refrain of one version, given by note index (0..39: the
refrain's forty sung notes, the same forty in every version). It is cut from that version's audio a
little before its first note and a little before the note after its last, so each cut lands on a pickup.

Time on the page is the release's time in its first refrain: each version's note onsets are mapped onto
the release's, so the tune is drawn in the same place whatever the tempo.
"""

import json
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[3]
VER = ROOT / "renders/promo/social/versions"
OUT = ROOT / "renders/promo/social/data"
RELEASE_AUDIO = ROOT / "renders/release/now-its-by-you.flac"
COPY = Path(__file__).with_name("copy.json")

PRE = 0.09  # seconds before a chunk's first note
XFADE = 0.03
RATE = 44100

# (version, refrain occurrence: 0 first, -1 last, first note, end note exclusive, part of the cut)
CHUNKS = [
    ("release", 0, 0, 4, "styles"),
    ("jig", 0, 4, 8, "styles"),
    ("acappella", 0, 8, 14, "styles"),
    ("house", 0, 14, 18, "styles"),
    ("old78", 0, 18, 24, "styles"),
    ("stringband", 0, 24, 29, "styles"),
    ("shanty", 0, 29, 35, "styles"),
    ("synthfolk", 0, 35, 40, "styles"),
    ("gen1", 0, 8, 18, "lineage"),
    ("gen2", 0, 18, 24, "lineage"),
    ("gen3", 0, 24, 29, "lineage"),
    ("gen4", 0, 29, 34, "lineage"),
    ("gen5", 0, 34, 40, "lineage"),
    ("gen6", -1, 35, 40, "end"),
]
LINES = [(0, 8), (8, 18), (18, 29), (29, 40)]  # the refrain's four lines, by note index
TAIL = 0.35  # after the last note of a run that no chunk of its own follows
END_RING = 3.2  # the last chunk rings this long after its last note ends, fading over its final 2 s

NAMES = {62: "D", 63: "E♭", 64: "E", 59: "B", 61: "C♯", 60: "C", 65: "F", 66: "F♯", 67: "G", 57: "A", 58: "B♭", 56: "A♭"}
MODES = {"ionian": "major", "aeolian": "minor", "mixolydian": "mixolydian", "dorian": "dorian"}
LEAD = {"voice"}
SKIP = {"voice"} | {f"choir{i}" for i in range(1, 7)}


def plain(s):
    return "".join(c for c in (s or "") if c.isalpha() or c == "'").lower()


def cont(ns, k):
    """Whether note k's syllable runs on into the next note's (one word sung over both)."""
    n = ns[k]
    if k + 1 >= len(ns) or n["word_len"] < 2 or ns[k + 1]["word"] != n["word"]:
        return False
    run = 0
    j = k
    while j > 0 and ns[j - 1]["word"] == n["word"] and run < n["word_len"] - 1:
        j -= 1
        run += 1
    return run < n["word_len"] - 1


def load(name):
    rec = json.loads((VER / f"{name}.json").read_text())
    score = json.loads((VER / f"{name}.score.json").read_text())
    audio = RELEASE_AUDIO if name == "release" else VER / f"{name}.flac"
    return rec, score, audio


def refrain_notes(score, occ):
    refs = [s for s in score["sections"] if s[0] == "refrain"]
    _, a, b = refs[occ]
    ns = [n for n in score["notes"] if n["part"] == "voice" and n["section"] == "refrain" and a - 2.0 <= n["start"] < b]
    assert len(ns) == 40, len(ns)
    return ns


def mapper(src, dst):
    """Piecewise-linear map from one version's onsets to the release's, extended at the ends by the
    local slope."""
    xs = np.array(src, float)
    ys = np.array(dst, float)

    def f(t):
        t = np.asarray(t, float)
        y = np.interp(t, xs, ys)
        lo = t < xs[0]
        hi = t > xs[-1]
        k0 = (ys[1] - ys[0]) / (xs[1] - xs[0])
        k1 = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        y = np.where(lo, ys[0] + (t - xs[0]) * k0, y)
        y = np.where(hi, ys[-1] + (t - xs[-1]) * k1, y)
        return y

    return f


def read(path):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    assert sr == RATE, (path, sr)
    return x


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    copy = json.loads(COPY.read_text())
    _, rscore, _ = load("release")
    rel = refrain_notes(rscore, 0)
    rel_on = [n["start"] for n in rel]

    cache = {}
    chunks = []
    pieces = []
    t_out = 0.0
    for ci, (name, occ, i0, i1, part) in enumerate(CHUNKS):
        if name not in cache:
            cache[name] = load(name) + (None,)
        rec, score, apath, _ = cache[name]
        ns = refrain_notes(score, occ)
        on = [n["start"] for n in ns]
        src0 = ns[i0]["start"] - PRE
        last = ns[i1 - 1]
        follows = ci + 1 < len(CHUNKS) and CHUNKS[ci + 1][0:2] != (name, occ) and CHUNKS[ci + 1][2] == i1
        if part == "end":
            src1 = last["start"] + last["dur"] + END_RING
        elif i1 < 40 and follows:
            src1 = ns[i1]["start"] - PRE
        else:
            src1 = last["start"] + last["dur"] + TAIL
        x = read(apath)
        a, b = int(round(src0 * RATE)), int(round(src1 * RATE))
        seg = x[a:b].copy()
        n = int(XFADE * RATE)
        ramp = np.linspace(0, 1, n, dtype=np.float32)[:, None]
        if ci > 0:
            seg[:n] *= ramp
        if part == "end":
            m = int(2.0 * RATE)
            seg[-m:] *= np.linspace(1, 0, m, dtype=np.float32)[:, None] ** 2
        else:
            seg[-n:] *= ramp[::-1]
        pieces.append(seg)

        f = mapper(on, rel_on)
        tonic = rec["params"]["tonic"]
        style = (rec["params"].get("style") or {}).get("name") or score["band"].get("style")
        # the band's notes near the chunk, pitch from the version's tonic, time on the page's clock
        band = []
        for nn in score["notes"]:
            if nn["part"] in SKIP or nn["pitch"] is None:
                continue
            if src0 - 8 < nn["start"] < src1 + 8:
                t0 = float(f(nn["start"]))
                t1 = float(f(nn["start"] + nn["dur"]))
                band.append([nn["part"], round(t0, 4), round(max(t1 - t0, 0.02), 4), round(nn["pitch"] - tonic, 2),
                             round(nn["vel"], 3)])
        voice = []
        for k, nn in enumerate(ns):
            vt0 = float(f(nn["start"]))
            vt1 = float(f(nn["start"] + nn["dur"]))
            voice.append({"i": k, "t0": round(vt0, 4), "t1": round(vt1, 4), "p": round(nn["pitch"] - tonic, 2),
                          "syl": nn["syllable"], "orn": (nn.get("gesture") or {}).get("ornament")
                          if isinstance(nn.get("gesture"), dict) else None})
        dur = (b - a) / RATE - (XFADE if ci + 1 < len(CHUNKS) else 0)
        chunks.append({
            "version": name, "part": part, "i0": i0, "i1": i1,
            "out0": round(t_out, 4), "out1": round(t_out + dur, 4),
            "src0": round(src0, 4),
            "page0": round(float(f(src0)), 4),
            # page time at out time t: map(src0 + (t - out0))
            "map": {"src": [round(v, 4) for v in on], "page": [round(v, 4) for v in rel_on]},
            "generation": rec["generation"], "style": style, "tonic": tonic, "tempo": round(rec["params"]["tempo"]),
            "key": f"{NAMES.get(tonic, tonic)} {MODES.get(rec['params']['mode'], rec['params']['mode'])}",
            "id": rec["id"][:12], "parent": (rec.get("parent_id") or "")[:12],
            "band": band, "voice": voice,
            "sung": [{"i": k, "syl": ns[k]["syllable"], "t0": round(t_out + ns[k]["start"] - src0, 4),
                      "t1": round(t_out + ns[k]["start"] + ns[k]["dur"] - src0, 4),
                      "changed": plain(ns[k]["syllable"]) != plain(rel[k]["syllable"]),
                      "cont": cont(ns, k)} for k in range(i0, i1)],
        })
        t_out += dur

    # each line of the refrain as it is heard: every half sung by the chunk that sings it
    lines = []
    for ci, c in enumerate(chunks):
        for (a, b) in LINES:
            if a <= c["i0"] < b:
                lo, hi = a, b
        if lines and lines[-1]["lo"] == lo and lines[-1]["part"] == c["part"]:
            line = lines[-1]
        else:
            line = {"lo": lo, "hi": hi, "part": c["part"], "t0": c["out0"], "syl": {}}
            lines.append(line)
        row = len({x["row"] for x in line["syl"].values()})
        for s in c["sung"]:
            s["row"] = row
            line["syl"][s["i"]] = s
        line["t1"] = c["out1"]
    for line in lines:
        # syllables not sung in this pass (a line begun by a chunk that starts mid-line) are shown unlit
        line["syl"] = [line["syl"].get(k) for k in range(line["lo"], line["hi"]) if k in line["syl"]]

    audio = np.concatenate(pieces)
    peak = float(np.abs(audio).max())
    if peak > 0.97:
        audio *= 0.97 / peak
    sf.write(OUT / "cut.wav", audio, RATE, subtype="PCM_24")
    rel_voice = [{"i": k, "t0": n["start"], "t1": n["start"] + n["dur"], "p": n["pitch"] - 62} for k, n in enumerate(rel)]
    data = {"duration": round(len(audio) / RATE, 4), "chunks": chunks, "lines": lines, "tune": rel_voice, "copy": copy}
    (OUT / "cut.json").write_text(json.dumps(data, ensure_ascii=False))
    for c in chunks:
        print(f"{c['out0']:6.2f}-{c['out1']:6.2f} {c['version']:9} g{c['generation']} {c['style']!s:10} {c['tempo']:4} {c['key']:14} "
              + " ".join(s["syl"] + ("*" if s["changed"] else "") for s in c["sung"]))
    print("duration", data["duration"])


if __name__ == "__main__":
    main()
