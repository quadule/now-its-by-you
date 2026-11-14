"""The singing voice through a tube: postures instead of formant tables.

The same schedule, pitch, loudness and glottal source as the formant voice
(voice.py); only the tract differs. Vowels are tongue-and-lip postures fitted
to their formant targets; consonants lay a constriction over them at their
place of articulation, closed for stops and nasals and narrow for fricatives,
where turbulence is injected so the cavity in front colours the hiss. The
tongue keeps gliding from vowel to vowel underneath the consonants, which is
how coarticulation happens in a mouth (Ohman 1966).

Status: experimental, selected with VoiceParams(engine="tube").
Static vowels are right (postures fitted per vowel within its anatomical
region reproduce F1-F3 within a few percent), and the spectrum is full to the
top with no truncation. Sung words are not yet intelligible: about 76% word
error on the Whisper suite against about 27% for the formant voice. Already
ruled out: vowel quality (an LPC reading of it on high notes is misleading),
breath level, pitch, and the turbulence (switching it off makes things
worse, 94%). Leading suspect: closures. When a section's area goes to zero
the flow waves stored in it are not rescaled, so they keep bouncing inside,
leak back out at twice their amplitude through the r = 1 junction, and burst
out on release, which would blur every stop ("carry" is heard as "harry").
Pink Trombone never lets a closed section reflect perfectly (r = 0.999);
rescaling stored waves as areas shrink is the principled fix. After that:
the in-breath level and glide/liquid postures.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import resample_poly, sosfilt

from .. import phonetics as ph
from ..score import Note
from . import glottis, tube
from . import voice as V
from .iir import butter

OPEN = 1.2  # radius of an unconstricted section, cm
NASAL_PORT = 0.5  # velar opening for a nasal, cm^2
PALATAL, LATERAL = 12.8, 15.6  # fixed places of the approximants' extra constrictions
TURBULENCE = 1.0  # gain on all injected frication and bursts (0 silences them, for diagnosis)

# Approximants are postures too: tongue and lips, plus how far the palatal and
# lateral channels close.
APPROXIMANTS = {
    "W": ((4.0, 0.20, 0.15), OPEN, OPEN),
    "Y": ((14.5, 0.18, 0.85), OPEN, OPEN),
    "R": ((4.0, 0.45, 0.50), 0.12, OPEN),
    "L": ((4.25, 0.95, 0.55), OPEN, 0.30),
}


def _is_front(v: str | None) -> bool:
    return v is not None and V._vowel_formants(v)[1] > 1500.0


def _consonant(seg: V.Segment) -> tuple[float, float] | None:
    """(place cm, radius cm) of the oral constriction a consonant makes, if any."""
    manner, place, _ = ph.CONSONANTS[seg.phone]
    if manner in ("liquid", "glide", "aspirate"):
        return None
    if place == "velar":
        near = seg.next_vowel if seg.role == "onset" else seg.prev_vowel
        return (13.0 if _is_front(near) else 11.0), 0.0
    at, radius = ph.CONSTRICTIONS[place]
    if manner == "fricative":
        radius = ph.FRICATIVE_RADIUS[seg.phone]
    return at, radius


def articulation(segs: list[V.Segment], tb: np.ndarray) -> dict[str, np.ndarray]:
    """Per-block tongue, lips, constrictions and velum."""
    keys = []  # (time, tongue_at, tongue_radius, lips, palatal radius, lateral radius)
    for s in segs:
        d = s.t1 - s.t0
        if s.role == "vowel":
            tau = min(0.035, 0.25 * d)
            postures = [ph.POSTURES[p] for p in ph.DIPHTHONGS.get(s.phone, (s.phone,))]
            if len(postures) == 2:  # hold the first quality, turn to the second at the end
                glide = min(0.15, 0.4 * d)
                timed = [(s.t0 + tau, postures[0]), (s.t1 - glide, postures[0]), (s.t1 - 0.01, postures[1])]
            else:
                timed = [(s.t0 + tau, postures[0]), (s.t1 - tau, postures[0])]
            for when, (at, narrow, lips, extra) in timed:
                keys.append((when, at, narrow, lips, extra[1] if extra else OPEN, OPEN))
        elif s.role in ("onset", "coda") and s.phone in APPROXIMANTS:
            (at, narrow, lips), palatal, lateral = APPROXIMANTS[s.phone]
            keys.append(((s.t0 + s.t1) / 2, at, narrow, lips, palatal, lateral))
    keys.sort(key=lambda k: k[0])
    k = np.array(keys)
    tongue_at, tongue_radius, lips, palatal, lateral = (np.interp(tb, k[:, 0], k[:, j]) for j in range(1, 6))

    # Consonant constrictions: close (or narrow) quickly, release a little slower.
    radius_keys, place = [], np.full(len(tb), 15.6)
    for s in segs:
        if s.role not in ("onset", "coda"):
            continue
        c = _consonant(s)
        if c is None:
            continue
        at, radius = c
        manner, _, voiced = ph.CONSONANTS[s.phone]
        release = V._stop_times(s, voiced)[0] if manner in ("stop", "affricate") else s.t1
        radius_keys += [(s.t0 - 0.012, OPEN), (s.t0 + 0.004, radius), (release, radius), (release + 0.018, OPEN)]
        if manner == "affricate":  # the closure opens into a postalveolar fricative
            radius_keys[-2:] = [(release, radius), (release + 0.004, ph.FRICATIVE_RADIUS["SH"]),
                                (s.t1, ph.FRICATIVE_RADIUS["SH"]), (s.t1 + 0.018, OPEN)]
        span = (tb >= s.t0 - 0.03) & (tb <= s.t1 + 0.03)
        place[span] = at
    radius_keys.sort(key=lambda q: q[0])
    rk = np.array(radius_keys) if radius_keys else np.array([[0.0, OPEN]])
    constriction = np.interp(tb, rk[:, 0], rk[:, 1])

    velum = np.zeros(len(tb))
    for s in segs:
        if s.role in ("onset", "coda") and ph.CONSONANTS[s.phone][0] == "nasal":
            velum[(tb >= s.t0 - 0.08) & (tb < s.t0)] = np.maximum(velum[(tb >= s.t0 - 0.08) & (tb < s.t0)], 0.15)
            velum[(tb >= s.t0 - 0.015) & (tb <= s.t1 + 0.015)] = NASAL_PORT
    velum = uniform_filter1d(velum, 5, mode="nearest")

    smooth = lambda x: uniform_filter1d(uniform_filter1d(x, 5, mode="nearest"), 5, mode="nearest")  # noqa: E731
    return {
        "tongue_at": smooth(tongue_at), "tongue_radius": smooth(tongue_radius), "lips": smooth(lips),
        "palatal": smooth(palatal), "lateral": smooth(lateral),
        "place": place, "constriction": constriction, "velum": velum,
    }


def sing(notes: list[Note], sr: int, voice: V.VoiceParams, seed: int = 0, lexicon=None) -> np.ndarray:
    """Render sung notes through the tube; vowels peak near 0.3 like the formant voice."""
    notes = sorted(notes, key=lambda n: n.start)
    rng = np.random.default_rng(seed)
    segs = V.schedule(notes, voice, lexicon)
    n_blocks = int(np.ceil((max(s.t1 for s in segs) + 0.5) * sr / V.BLOCK))
    tracks = V.control_tracks(segs, n_blocks, sr, voice)
    tb = tracks["tb"]
    # each vowel's end, so an ornament (and a gesture's bend or fall) happens while it can be heard
    f0_blocks = V.pitch_track(notes, n_blocks, sr, voice, rng, [s.t1 for s in segs if s.role == "vowel"])
    art = articulation(segs, tb)

    sections = tube.sections(voice.tract, sr)
    shapes = tube.profile(sections, art["tongue_at"], art["tongue_radius"], art["lips"],
                          [(np.full(len(tb), PALATAL), art["palatal"]), (np.full(len(tb), LATERAL), art["lateral"]),
                           (art["place"], art["constriction"])])
    areas = np.ascontiguousarray(np.pi * shapes**2)

    rate = tube.OVERSAMPLE * sr
    block = V.BLOCK * tube.OVERSAMPLE
    n = n_blocks * block
    t = (np.arange(n) + 0.5) / rate
    per_sample = lambda x: np.interp(t, tb, x)  # noqa: E731
    f0 = per_sample(f0_blocks)
    av = per_sample(tracks["av"]) * (1.0 + 0.01 * voice.shimmer * V._lowpassed_noise(rng, n, 30.0, rate))
    ah = per_sample(tracks["ah"])
    rd = per_sample(tracks["rd"])
    pulses, flow = glottis.source(f0, rd, rate, voice.tilt)
    voicing = np.clip(av / 0.6, 0.0, 1.0)
    breath = sosfilt(butter(1, 400.0, btype="highpass", fs=rate, output="sos"), rng.standard_normal(n))
    breath *= voicing * (0.25 + 0.75 * flow) + (1.0 - voicing)
    source = pulses * av + 0.6 * breath * ah

    nose = tube.nose_areas(sections)
    nose_start = int(round(tube.VELUM_AT / tube.REFERENCE_LENGTH * sections))
    quiet = np.full(n_blocks, -1.0)
    y = tube.run(source, np.zeros(n), quiet, areas, art["velum"], nose, nose_start, block)

    vowel = np.zeros(n, dtype=bool)
    for s in segs:
        if s.role == "vowel":
            vowel[int(s.t0 * rate) : int(s.t1 * rate)] = True
    ref = np.sqrt(np.mean(y[vowel] ** 2)) if vowel.any() else 1.0

    # Turbulence: noise injected where the air is forced through the
    # constriction, one event at a time, each scaled to its level relative to
    # the vowels once the tract has shaped it.
    turbulence = sosfilt(butter(2, 300.0, btype="highpass", fs=rate, output="sos"), rng.standard_normal(n))
    for s in segs:
        if s.role not in ("onset", "coda"):
            continue
        manner, place, voiced = ph.CONSONANTS[s.phone]
        c = _consonant(s)
        events = []
        if manner == "fricative":
            events.append((s.t0, s.t1, ph.FRICATION[s.phone][1], 0.02 if s.phone in ("S", "Z", "SH", "ZH") else 0.035))
        elif manner in ("stop", "affricate"):
            release = V._stop_times(s, voiced)[0]
            events.append((release, release + (0.008 if voiced else 0.012), ph.BURSTS[place][1] - (3.0 if voiced else 0.0), 0.002))
            if manner == "affricate":
                events.append((release, s.t1, ph.FRICATION["ZH" if voiced else "SH"][1], 0.01))
        for t0, t1, level, ramp in events:
            i0, i1 = int(t0 * rate), int(t1 * rate)
            if i1 <= i0 or c is None:
                continue
            # simulate only this event's stretch, from silence, with room to ring out
            b0 = max(i0 - int(0.005 * rate), 0) // block
            b1 = min((i1 + int(0.03 * rate)) // block + 1, n_blocks)
            lo, hi = b0 * block, b1 * block
            envelope = np.clip(np.minimum((t[lo:hi] - t0) / ramp, (t1 - t[lo:hi]) / ramp), 0.0, 1.0)
            # the jet strikes just in front of the constriction, not inside it
            front = min(c[0] + 0.6, tube.REFERENCE_LENGTH - 0.2)
            at = np.full(b1 - b0, front / tube.REFERENCE_LENGTH * sections)
            hiss = tube.run(np.zeros(hi - lo), turbulence[lo:hi] * envelope, at, areas[b0:b1],
                            art["velum"][b0:b1], nose, nose_start, block)
            # level over the whole window, so a closure that muffles the start
            # can't make the normalization blow up what escapes after it
            rms = np.sqrt(np.mean(hiss**2) * (hi - lo) / max(i1 - i0, 1)) + 1e-12
            y[lo:hi] += TURBULENCE * ref * 10.0 ** (level / 20.0) * s.amp * hiss / rms

    y = resample_poly(y, 1, tube.OVERSAMPLE)
    y = sosfilt(butter(1, 60.0, btype="highpass", fs=sr, output="sos"), y)
    return 0.3 * y / ref / np.sqrt(2.0)
