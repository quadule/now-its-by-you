"""The instrumented replay: the release rendered again with wrappers around the models' own functions, each
keeping what the model was given (and, where it is cheap, what it gave back), the engine untouched.

    uv run python tools/promo/video/prep/replay.py

runs `songbird render performance/genome.json --replay performance/record-live-A.json --stems --out
renders/promo/video/scratch/replay/render.flac` with SONGBIRD_THREADS=2 and writes the captures to
renders/promo/video/scratch/replay/capture/. The audio id it prints must be eb8fb05eb2bb (the release's): the
proof that the wrappers changed nothing. The stems are written from the mix's own pass (render_one's `kept`
hook: each part's dry stem as the mix receives it) as <out>.<part>.wav, 32-bit float, exactly the files
--stems writes, so the song is synthesized once rather than twice.

Every wrapper is installed from outside (module attributes replaced before songbird.cli runs, as
tools/promo/capture.py does). Which stem a call belongs to is a thread-local stack of part names: each
stem's maker pushes its name while it runs (a twin's player made inside the twin's thread pushes its own).
"""
from __future__ import annotations

import os
import pickle
import sys
import threading
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, SCRATCH, guard  # noqa: E402

OUT = guard(SCRATCH / "replay")
CAP = guard(OUT / "capture")
SR = 44100
CHECKED = 4  # notes per stem whose loop outputs are kept whole, for physics.py's reference check

_local = threading.local()
_lock = threading.RLock()
caps: dict[str, list] = {}  # kind -> records


def stem() -> str | None:
    tags = getattr(_local, "tags", None)
    return tags[-1] if tags else None


def keep(kind: str, rec: dict) -> dict:
    with _lock:
        caps.setdefault(kind, []).append(rec)
    return rec


def tagged(name: str, make):
    def run():
        tags = _local.__dict__.setdefault("tags", [])
        tags.append(name)
        try:
            return make()
        finally:
            tags.pop()
    return run


def caller(depth: int = 2) -> dict:
    """The locals of the function that called the wrapper (a snapshot)."""
    return dict(sys._getframe(depth).f_locals)


def plain_note(n) -> dict:
    return {"start": float(n.start), "dur": float(n.dur), "pitch": float(n.pitch), "vel": float(n.vel),
            "art": str(n.art or ""), "section": getattr(n, "section", None)}


def a64(x) -> np.ndarray:
    return np.array(x, dtype=np.float64, copy=True)


# ---------------------------------------------------------------------------------------------- the stems


def install_stems() -> None:
    """Each stem's maker tagged with its name (the score's own band, a layer's band, and the outer jobs)."""
    from songbird import synth
    from songbird.synth import instruments

    band_parts = instruments.band_parts

    def tagged_parts(score, sr, seed):
        return [(name, tagged(name, make)) for name, make in band_parts(score, sr, seed)]

    instruments.band_parts = tagged_parts
    synth.band_parts = tagged_parts  # stem_jobs' own name for it
    stem_jobs = synth.stem_jobs

    def tagged_jobs(*a, **k):
        jobs, singers = stem_jobs(*a, **k)
        return [(name, tagged(name, make)) for name, make in jobs], singers

    synth.stem_jobs = tagged_jobs


def install_kept(out: Path) -> None:
    """The mix's pass hands each dry stem to `kept`, which writes it as --stems would; --stems' own second
    synthesis is skipped (render_stems returns nothing to write)."""
    import soundfile as sf

    from songbird import synth

    render = synth.render
    names: list[str] = []

    def kept(name, y):
        sf.write(str(out.with_name(f"{out.stem}.{name}.wav")), y, synth.SR, subtype="FLOAT")
        with _lock:
            names.append(name)

    def render_kept(*a, **k):
        assert k.get("kept") is None
        k["kept"] = kept
        return render(*a, **k)

    synth.render = render_kept
    synth.render_stems = lambda *a, **k: {}
    caps["stems"] = names


# ---------------------------------------------------------------------------------------------- plucked strings


def install_pluck() -> None:
    """Every pluck.pluck call (one note: its stem, the score note, its arguments) and every _plane inside it
    (the loop's delay, taps, gains, release and the one-period excitation fed into it)."""
    from songbird.synth import body, pluck

    pluck_fn, plane_fn, sym_fn, ir_fn = pluck.pluck, pluck._plane, pluck.sympathetic, body.impulse_response
    seen: dict[str, int] = {}

    def pluck_kept(freq, dur, sr, rng, **kw):
        up = caller()
        note = up.get("note")
        name = stem()
        with _lock:
            k = seen[name] = seen.get(name, -1) + 1
        rec = {"stem": name, "k": k, "note": plain_note(note) if note is not None else None,
               "start_sample": up.get("start"), "tuning_cents": float(up.get("offset", 0.0)),
               "freq": float(freq), "dur": float(dur), **{a: (float(v) if not isinstance(v, bool) else v)
                                                          for a, v in kw.items()}, "planes": []}
        _local.pluck = rec
        try:
            y = pluck_fn(freq, dur, sr, rng, **kw)
        finally:
            _local.pluck = None
        rec["length"] = len(y)
        if k < CHECKED:
            rec["out"] = a64(y)
        keep("pluck", rec)
        return y

    def plane_kept(freq, excitation, sr, loss, t60, held, length, release_t60):
        up = caller()
        y = plane_fn(freq, excitation, sr, loss, t60, held, length, release_t60)
        rec = getattr(_local, "pluck", None)
        if rec is not None:
            whole, taps = pluck._cached_loop(round(sr / freq, 6), round(loss, 4))
            p = {"freq": float(freq), "period": sr / freq, "loss": float(loss), "t60": float(t60),
                 "held": int(held), "length": int(length), "release_t60": float(release_t60),
                 "whole": int(whole), "taps": list(taps), "gain": 10.0 ** (-3.0 / (t60 * freq)),
                 "release_gain": 10.0 ** (-3.0 / (release_t60 * freq)),
                 "smooth": float(np.exp(-1.0 / (0.004 * sr))), "lag": int(up.get("lag", 0)),
                 "cents": float(up.get("cents", 0.0)), "split": float(up.get("split", 0.0)),
                 "excitation": a64(excitation)}
            if rec["k"] < CHECKED:
                p["out"] = a64(y)
            rec["planes"].append(p)
        return y

    def sym_kept(force, sr, pitches, coupling=0.0015, decay=3.0, brightness=0.3):
        keep("sympathetic", {"stem": stem(), "pitches": [float(p) for p in pitches], "coupling": float(coupling),
                             "decay": float(decay), "brightness": float(brightness)})
        return sym_fn(force, sr, pitches, coupling=coupling, decay=decay, brightness=brightness)

    named = {id(getattr(body, n)): n for n in dir(body) if isinstance(getattr(body, n), body.Body)}

    def ir_kept(spec, sr, seed=0, size=1.0, channels=2, alike=0.0):
        ir = ir_fn(spec, sr, seed=seed, size=size, channels=channels, alike=alike)
        keep("body", {"stem": stem(), "body": named.get(id(spec)), "spec": spec, "seed": int(seed),
                      "size": float(size), "channels": int(channels), "alike": float(alike), "sr": int(sr),
                      "ir": ir.astype(np.float32)})
        return ir

    pluck.pluck, pluck._plane, pluck.sympathetic, body.impulse_response = pluck_kept, plane_kept, sym_kept, ir_kept


# ---------------------------------------------------------------------------------------------- the frame drum


def install_drum() -> None:
    """Every drum.hit (its note, stroke, strike place) and the _ring call inside it (each mode's frequency,
    initial amplitude and T60, the glide), with the gain hit() puts on the ring afterwards."""
    from songbird.synth import drum

    hit_fn, ring_fn = drum.hit, drum._ring

    def ring_kept(freqs, amps, t60s, glide, glide_time, n, sr):
        up = caller()
        y = ring_fn(freqs, amps, t60s, glide, glide_time, n, sr)
        _local.ring = ({"freqs": a64(freqs), "amps": a64(amps), "t60s": a64(t60s), "glide": float(glide),
                        "glide_time": float(glide_time), "n": int(n),
                        **{k: float(up[k]) for k in ("radius", "theta", "f0", "contact", "ring", "click", "lift",
                                                     "contact_ms", "pitch", "brightness", "wear") if k in up},
                        **{k: a64(up[k]) for k in ("shape", "spectrum", "radiate", "m", "j") if k in up}}, y)
        return y

    def hit_kept(stroke, vel, sr, rng, **kw):
        up = caller()
        _local.ring = None
        state = rng.bit_generator.state  # the hit's draws (its place, its modes' spread), for physics.py to repeat
        y = hit_fn(stroke, vel, sr, rng, **kw)
        rec, ring = _local.ring
        rec["rng_state"] = state
        lo = int(0.061 * sr)
        k = lo + int(np.argmax(np.abs(ring[lo:]))) if len(ring) > lo + 1 else len(ring) - 1
        rec["gain"] = float(y[k] / ring[k]) if ring[k] != 0 else 0.0
        k2 = min(len(ring) - 1, k + 37)
        rec["gain_check"] = float(y[k2] / ring[k2]) if ring[k2] != 0 else rec["gain"]
        note = up.get("note")
        rec.update({"stem": stem(), "stroke": stroke, "vel": float(vel), "note": plain_note(note) if note else None,
                    "length": len(y)})
        keep("drum", rec)
        return y

    drum.hit, drum._ring = hit_kept, ring_kept


# ---------------------------------------------------------------------------------------------- bow, pipe, reeds


def install_waveguides() -> None:
    """bowed.run and pipe.run are compiled: their inputs (the control tracks, whole) and output are written
    to capture/<kind>-<stem>.npz for physics.py's instrumented copies, which must reproduce the output."""
    from songbird.synth import bowed, pipe

    bow_run, pipe_run = bowed.run, pipe.run

    def bow_kept(period, bridge_len, bow_v, grip, noise, pole, gain):
        y = bow_run(period, bridge_len, bow_v, grip, noise, pole, gain)
        np.savez(guard(CAP / f"bow-{stem()}.npz"), period=period, bridge_len=bridge_len, bow_v=bow_v, grip=grip,
                 noise=noise, pole=pole, gain=gain, out=y)
        keep("bow", {"stem": stem(), "notes": [plain_note(n) for n in caller().get("notes", ())]})
        return y

    def pipe_kept(freq, breath, chiff, drive, aim, noise, feedback, damping, sr):
        y = pipe_run(freq, breath, chiff, drive, aim, noise, feedback, damping, sr)
        np.savez(guard(CAP / f"pipe-{stem()}.npz"), freq=freq, breath=breath, chiff=chiff, drive=drive, aim=aim,
                 noise=noise, feedback=feedback, damping=damping, sr=sr, out=y)
        keep("pipe", {"stem": stem(), "notes": [plain_note(n) for n in caller().get("notes", ())]})
        return y

    bowed.run, pipe.run = bow_kept, pipe_kept


def install_reed() -> None:
    """The drone: each note's wavetable (reed.table) and each reed's read of it (reed._read: its phase
    increments and amplitude, the bellows curve times the reed's speaking, kept at 240 a second)."""
    from songbird.synth import reed

    table_fn, read_fn = reed.table, reed._read

    def table_kept(freq, sr, rng, brightness=0.5):
        up = caller()
        wave = table_fn(freq, sr, rng, brightness)
        note = up.get("note")
        _local.reed = keep("reed", {"stem": stem(), "note": plain_note(note) if note else None, "freq": float(freq),
                                    "brightness": float(brightness), "wave": wave.astype(np.float32),
                                    "i0": int(up.get("i0", 0)), "pump": float(up.get("pump", 0.0)),
                                    "env": a64(up["env"])[:: SR // 240].astype(np.float32), "reeds": []})
        return wave

    def read_kept(wave, increments, amplitude, out, offset, phase):
        rec = getattr(_local, "reed", None)
        if rec is not None and wave is not None and len(wave) == reed.TABLE:
            up = caller()
            rec["reeds"].append({"phase0": float(phase), "cents0": float(up.get("cents", 0.0)),
                                 "hz": (np.asarray(increments) * SR)[:: SR // 240].astype(np.float32),
                                 "amp": np.asarray(amplitude)[:: SR // 240].astype(np.float32)})
        return read_fn(wave, increments, amplitude, out, offset, phase)

    reed.table, reed._read = table_kept, read_kept


# ---------------------------------------------------------------------------------------------- synths and chips


def install_analog() -> None:
    """Every analog voice phrase (analog._voice, compiled): all its arguments but the buffer, the phrase's
    notes and the machine's preset, for physics.py's traced copy of the voice."""
    from songbird.synth import analog

    voice_fn = analog._voice
    names = ("at", "n", "on", "off", "pitch", "retrig", "glide", "bend", "amp", "env", "famt", "fbase", "kinds",
             "levels", "shifted", "ratio", "pw", "phases", "gcoef", "bcoef", "vib", "track", "pref", "k", "drive",
             "noise", "seed", "inv_sr2")

    def voice_kept(buf, *args):
        up = caller()
        machine = up.get("machine")
        rec = {"stem": stem(), "machine": machine.name if machine is not None else None,
               "preset": dict(machine.p) if machine is not None else None,
               "notes": [plain_note(n) for n, _, _ in up.get("phrase", ())],
               "args": {k: (np.array(v, copy=True) if isinstance(v, np.ndarray) else v) for k, v in zip(names, args)}}
        r = voice_fn(buf, *args)
        rec["sounded"] = int(r)
        keep("analog", rec)
        return r

    analog._voice = voice_kept


def install_chip() -> None:
    """The chip's channels as their event lists are made (chip._pulse_events, _triangle_events,
    _noise_events, compiled): their frames in, their level changes out, and the hits or notes behind them."""
    from songbird.synth import chip

    pulse_fn, tri_fn, noise_fn = chip._pulse_events, chip._triangle_events, chip._noise_events

    def pulse_kept(t0, t1, hz, vol, reset, lo, hi, table):
        up = caller()
        et, el = pulse_fn(t0, t1, hz, vol, reset, lo, hi, table)
        keep("chip", {"stem": stem(), "channel": "pulse", "notes": [plain_note(n) for n in up.get("notes", ())],
                      "driver": {k: up.get(k) for k in ("default", "sag", "vib_rate", "vib_delay", "depth")},
                      "frames": {"t0": a64(t0), "t1": a64(t1), "hz": a64(hz), "vol": np.array(vol), "reset": np.array(reset),
                                 "lo": a64(lo), "hi": a64(hi)}, "events": (a64(et), a64(el))})
        return et, el

    def tri_kept(t0, t1, hz, phase):
        up = caller()
        tt, tv, ph = tri_fn(t0, t1, hz, phase)
        keep("chip", {"stem": stem(), "channel": "triangle", "phase0": float(phase),
                      "frames": {"t0": a64(t0), "t1": a64(t1), "hz": a64(hz)}, "events": (a64(tt), a64(tv)),
                      "tri_hits": [(float(s), p, float(v)) for s, p, v in up.get("tri", [])]})
        return tt, tv, ph

    def noise_kept(t0, t1, rate, short, vol, reg):
        up = caller()
        nt, nv, r = noise_fn(t0, t1, rate, short, vol, reg)
        keep("chip", {"stem": stem(), "channel": "noise", "reg0": int(reg),
                      "frames": {"t0": a64(t0), "t1": a64(t1), "rate": a64(rate), "short": np.array(short),
                                 "vol": a64(vol)}, "events": (a64(nt), a64(nv)),
                      "noise_hits": [(float(s), p, float(v)) for s, p, v in up.get("noise", [])],
                      "shift": dict(up.get("shift", {})), "kick_scale": up.get("kick_scale")})
        return nt, nv, r

    chip._pulse_events, chip._triangle_events, chip._noise_events = pulse_kept, tri_kept, noise_kept


def plain_value(v):
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if isinstance(v, (np.floating, np.integer)):
        return v.item()
    if isinstance(v, (tuple, list)) and all(isinstance(x, (int, float, np.floating, np.integer)) for x in v):
        return [float(x) for x in v]
    if isinstance(v, np.ndarray) and v.size <= 64 and v.dtype.kind in "fiu":
        return v.astype(float).tolist()
    if isinstance(v, dict) and all(isinstance(x, (int, float, str)) for x in v.values()):
        return dict(v)
    return None


def install_drummachine() -> None:
    """Every drum machine hit: the piece (the circuit voice), its trigger (Hit: size, accent, detune, cut) and
    the machine's own settings (its parts' tolerances and knobs), once per machine."""
    from songbird.synth import drummachine as dm

    machines: dict[int, dict] = {}

    for cls in (dm.TR808, dm.TR909):
        for piece in dm.PIECES:
            attr = piece.replace("-", "_")
            fn = getattr(cls, attr, None)
            if fn is None:
                continue

            def kept(self, hit, fn=fn, piece=piece, cls=cls):
                y = fn(self, hit)
                up = caller()
                note = up.get("note")
                if id(self) not in machines:
                    with _lock:
                        machines[id(self)] = keep("drummachine_kit", {
                            "stem": stem(), "machine": cls.__name__,
                            "settings": {k: pv for k, v in vars(self).items() if (pv := plain_value(v)) is not None}})
                keep("drummachine", {"stem": stem(), "machine": cls.__name__, "piece": piece,
                                     "note": plain_note(note) if note is not None else None,
                                     "i": int(hit.i), "t": float(hit.t), "vel": float(hit.vel), "size": float(hit.size),
                                     "accent": float(hit.accent), "cents": float(hit.cents), "loose": float(hit.loose),
                                     "cut": None if hit.cut is None else int(hit.cut), "cut_tau": float(hit.cut_tau),
                                     "mix": float(up["mix"][piece]) if "mix" in up else None,
                                     "length": int(len(y)), "peak": float(np.max(np.abs(y))) if len(y) else 0.0})
                return y

            setattr(cls, attr, kept)


# ---------------------------------------------------------------------------------------------- the strumming hand


def install_strum() -> None:
    """Every stroke of the guitar's strumming hand (band._hand_stroke) as the score is realized: the hand's
    stroke (kind, accent, flag, slot), the strings it met in order and their velocities and offsets. Each
    realization of the guitar part (band.guitar_part: the score's own first, then the stage's takes) is kept
    as its own list."""
    from songbird import band, strumming

    part_fn, stroke_fn, voiced_fn = band.guitar_part, band._hand_stroke, strumming.Hand.voiced
    runs: list[list] = []

    def part_kept(ctx, capo):
        with _lock:
            runs.append([])
            _local.strokes = runs[-1]
        try:
            return part_fn(ctx, capo)
        finally:
            _local.strokes = None

    def voiced_kept(self, stroke, hit, vel, slot, rng, late=0.0):
        out = voiced_fn(self, stroke, hit, vel, slot, rng, late=late)
        _local.voiced = {"hit": [list(h) if isinstance(h, tuple) else h for h in hit], "slot": float(slot),
                         "vel": float(vel), "late": float(late),
                         "played": [(p if not isinstance(p, tuple) else list(p), float(v), float(s)) for p, v, s in out]}
        return out

    def stroke_kept(ctx, hand, played, u, c, voicing, capo, rng, ringing, beat_s):
        _local.voiced = None
        evs = stroke_fn(ctx, hand, played, u, c, voicing, capo, rng, ringing, beat_s)
        st, span, late = played
        strokes = getattr(_local, "strokes", None)
        if strokes is not None:
            strokes.append({"u": float(u), "kind": st.kind, "accent": float(st.accent), "flag": st.flag,
                            "slot": int(st.slot), "slots": int(st.slots), "at": float(st.at), "span": float(span),
                            "late": float(late), "chord": getattr(c, "symbol", None), "beat_s": float(beat_s),
                            "voiced": _local.voiced,
                            "events": [{"pitch": float(e.pitch), "vel": float(e.vel), "shift": float(e.shift),
                                        "art": e.art} for e in evs]})
        return evs

    band.guitar_part, band._hand_stroke, strumming.Hand.voiced = part_kept, stroke_kept, voiced_kept
    caps["strum_runs"] = runs


# ---------------------------------------------------------------------------------------------- the run


def install(out: Path) -> None:
    install_stems()
    install_kept(out)
    install_pluck()
    install_drum()
    install_waveguides()
    install_reed()
    install_analog()
    install_chip()
    install_drummachine()
    install_strum()


def save() -> None:
    for kind, recs in caps.items():
        with open(guard(CAP / f"{kind}.pkl"), "wb") as f:
            pickle.dump(recs, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"capture {kind}: {len(recs)}", file=sys.stderr)


def main(argv=None) -> None:
    os.chdir(ROOT)
    CAP.mkdir(parents=True, exist_ok=True)
    out = guard(OUT / "render.flac")
    os.environ.setdefault("SONGBIRD_THREADS", "2")
    install(out)
    from songbird.cli import main as cli

    sys.argv = ["songbird", "render", "performance/genome.json", "--replay", "performance/record-live-A.json",
                "--out", str(out.relative_to(ROOT)), "--stems", *(argv or [])]
    try:
        cli()
    finally:
        save()


if __name__ == "__main__":
    main(sys.argv[1:])
