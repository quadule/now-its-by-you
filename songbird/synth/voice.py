"""The singing voice: a formant synthesizer in the Klatt tradition.

Sung notes (with their syllables) go in; a mono voice comes out.

1. Fit each word's pronunciation to its notes.
2. Schedule phonemes: the vowel lands on the beat, onset consonants come just
   before it, coda consonants at the end of the note, a breath at each line end.
3. Keyframe each phoneme's targets and smooth them into control tracks, one
   value per block: formants, bandwidths, voicing, aspiration, nasality and
   glottal shape. Pitch gets glides, vibrato, drift and jitter.
4. Synthesize: LF pulses plus pulsed aspiration, through a nasal pole-zero
   pair and five cascaded formants, with a fixed branch in parallel for the
   tract above F5 (see tract.upper_branch); frication and bursts are shaped
   noise added in parallel.

Settings were tuned against a Whisper transcription suite (tools/wer_suite.py)
and a review of the design by a Fable advisor: where naturalness and machine
intelligibility pulled apart (dynamics, sonorant levels), the values sit in
between and the trade-off is a voice parameter.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, fftconvolve, sosfilt

from .. import phonetics as ph
from ..score import Note
from . import glottis, tract

BLOCK = 128
# F1-F3 move with the vowels; F4 and F5 sit close together (the singer's
# cluster). Everything above comes from a fixed parallel branch (tract.upper_branch).
HIGH_FORMANTS = (3300.0, 3900.0)
# Sung vowels have wider F1/F2 bandwidths than spoken ones; narrow ones ring and hoot.
BANDWIDTHS = np.array([100.0, 115.0, 140.0, 200.0, 220.0])
NASAL_POLE = 270.0
# Voicing of sonorant consonants relative to their vowel.
SONORANT_LEVELS = {"nasal": 0.5, "liquid": 0.7, "glide": 0.8}
NASAL_MURMUR_F1 = 260.0  # the murmur's first resonance sits low, near the nasal pole
CLOSURE = 0.055  # seconds a voiceless stop holds its closure before the release


@dataclass(frozen=True)
class VoiceParams:
    shift: int = 0  # semitones from written to sung pitch
    tract: float = 1.12  # formant scale: 1 an average adult male tract, 1.12 an alto's
    rd: float = 0.7  # glottal shape: 0.6 pressed, 1 modal, 1.8 breathy
    tilt: float = 0.4  # glottal closing speed: below 1 closes faster, a brighter voice
    breath: float = 0.05  # aspiration mixed into voicing
    vibrato_rate: float = 5.3  # Hz
    vibrato_depth: float = 28.0  # cents
    vibrato_delay: float = 0.28  # seconds into a note before vibrato starts
    glide: float = 0.11  # seconds to move between notes a step apart (wider leaps take longer)
    glide_spread: float = 0.3  # how much that varies from one note to the next (log scale)
    overshoot: float = 0.12  # fraction of each interval sung past the new note before settling
    scoop: float = 0.35  # semitones below the note that a phrase starts from
    jitter: float = 0.3  # percent, fast pitch wobble
    wander: float = 6.0  # cents, slow pitch drift
    shimmer: float = 2.5  # percent, fast amplitude wobble
    articulation: float = 1.0  # consonant length scale
    cluster: float = 0.7  # length of each consonant in a cluster within a syllable, against alone
    across: float = 1.0  # length of consonants where one syllable's coda meets the next one's onset
    glides: float = 1.0  # length scale for the consonants w and y, which singers linger in
    liquids: float = 1.0  # length scale for l and r
    release: float = 0.05  # seconds over which the voice lets go at a phrase end
    dynamics: float = 15.0  # dB of loudness per unit of stress; an even singer is low, an expressive one high
    lean: float = 1.0  # dB a word's stressed syllable is sung above its others (and they below it)
    light: float = 1.5  # dB softer for the little words between the ones that mean (a, the, it, and, of...)
    ease: float = 1.5  # dB softer for a line's first syllable, eased into
    let_go: float = 1.0  # dB softer for its last, let go of
    climb: float = 0.5  # dB louder per semitone above the line's middle
    taper: float = -4.0  # dB a held vowel fades from a third of the way through to its end
    vibrato_from: float = 0.9  # seconds a note must last before the singer puts vibrato on it (0.55 at a line's end)
    breathe: float = 0.18  # seconds between lines needed for an audible breath
    accent: float = 8.0  # cents a strongly leaned-on note is lifted
    reduce: float = 0.0  # how far a little word's vowel off the beat moves toward "uh" (0.3 cost the words: WER 15% -> 18%)
    mouth: float = 1.0  # cm radius of the mouth opening: small keeps the upper resonances ringing
    engine: str = "formant"  # "formant" (Klatt cascade) or "tube" (waveguide tract, experimental)


@dataclass
class Segment:
    t0: float
    t1: float
    phone: str  # ARPAbet, vowels without stress; "sil" or "breath"
    role: str  # onset, vowel, coda, sil, breath
    amp: float  # the syllable's loudness
    prev_vowel: str | None = None
    next_vowel: str | None = None
    swell: float = 0.0  # dB a vowel grows from its start to its end (a phrasing gesture)
    reduce: float = 0.0  # how far the vowel is sung toward "uh" (a little word, off the beat)


def _smooth(x: np.ndarray, width: int) -> np.ndarray:
    return uniform_filter1d(uniform_filter1d(x, width, axis=0, mode="nearest"), width, axis=0, mode="nearest")


def _consonant_duration(c: str, in_cluster: bool, onset: bool, voice: VoiceParams | None = None) -> float:
    manner, place, voiced = ph.CONSONANTS[c]
    if manner == "fricative":
        d = ph.FRICATIVE_DURATIONS[c]
    elif manner == "stop" and onset and not voiced:
        d = CLOSURE + ph.VOICE_ONSET[place]  # closure, then the aspiration that marks it voiceless
    else:
        d = ph.DURATIONS[manner]
    voice = voice or VoiceParams()
    return d * (voice.cluster if in_cluster else 1.0) * {"glide": voice.glides, "liquid": voice.liquids}.get(manner, 1.0)


def _vowel_formants(v: str) -> tuple[float, float, float]:
    return ph.VOWEL_FORMANTS[ph.DIPHTHONGS[v][0] if v in ph.DIPHTHONGS else v]


def schedule(notes: list[Note], voice: VoiceParams, lexicon: dict[str, str] | None = None) -> list[Segment]:
    """Place every phoneme of every sung note in time."""
    # Pronounce word by word, then hand syllables back to their notes.
    sylls: list[ph.Syllable] = []
    i = 0
    while i < len(notes):
        n = notes[i].word_len
        sylls += ph.fit(notes[i].word or notes[i].syllable or "ah", n, lexicon)
        i += n
    if len(sylls) != len(notes):
        raise ValueError("syllables and notes disagree")

    onset = [[_consonant_duration(c, len(s.onset) > 1, True, voice) * voice.articulation for c in s.onset] for s in sylls]
    coda = [[_consonant_duration(c, len(s.coda) > 1, False, voice) * voice.articulation for c in s.coda] for s in sylls]
    for k in range(len(sylls) - 1):  # a coda running into the next onset is sung as one cluster
        if coda[k] and onset[k + 1] and not notes[k].line_end and voice.across != 1.0:
            coda[k] = [d * voice.across for d in coda[k]]
            onset[k + 1] = [d * voice.across for d in onset[k + 1]]

    def limit(k: int) -> float:
        """When note k's last sound must end: its own end, a breath at a line end,
        and never after the next syllable's first consonant."""
        note = notes[k]
        end = note.start + note.dur
        if note.line_end:
            end -= line_release(note.dur)  # let go in time to breathe
        if k + 1 < len(notes):
            end = min(end, notes[k + 1].start - sum(onset[k + 1]) - (0.03 if note.line_end else 0.0))
        return end

    # Make room for consonants: squeeze them when a note is too short to keep
    # a vowel of at least 40% of the note (and 60 ms).
    for k, note in enumerate(notes):
        room = limit(k) - note.start - max(0.06, 0.4 * note.dur)
        if sum(coda[k]) > room or room < 0:
            nxt = sum(onset[k + 1]) if k + 1 < len(notes) else 0.0
            available = limit(k) + nxt - note.start - max(0.06, 0.4 * note.dur)
            scale = float(np.clip(available / max(sum(coda[k]) + nxt, 1e-9), 0.3, 1.0))
            coda[k] = [d * scale for d in coda[k]]
            if k + 1 < len(notes):
                onset[k + 1] = [d * scale for d in onset[k + 1]]

    # How hard each syllable is leaned on (dB), as a singer does it: the beat
    # (the score's stress), the word's stressed syllable over its others, the
    # words that mean over the little ones between them, a line eased into and
    # let go of, and louder as the voice climbs.
    line_median, line = {}, []
    for k, note in enumerate(notes):
        line.append(k)
        if note.line_end or k == len(notes) - 1:
            middle = float(np.median([notes[j].pitch for j in line]))
            line_median.update({j: middle for j in line})
            line = []

    first_of_line = [k == 0 or notes[k - 1].line_end for k in range(len(notes))]
    in_word, word_len, word = [], [], []
    k = 0
    while k < len(notes):
        n = notes[k].word_len
        for j in range(n):
            in_word.append(j)
            word_len.append(n)
            word.append((notes[k].word or "").replace("-", "").lower().strip(".,;:!?\"'"))
        k += n

    segs: list[Segment] = []
    for k, (note, syl) in enumerate(zip(notes, sylls)):
        loud_db = voice.dynamics * (note.vel - 0.75) + voice.climb * (note.pitch - line_median[k])
        if word_len[k] > 1:
            loud_db += voice.lean if syl.stressed else -voice.lean
        if word[k] in ph.FUNCTION_WORDS:
            loud_db -= voice.light
        if first_of_line[k]:
            loud_db -= voice.ease
        if note.line_end:
            loud_db -= voice.let_go
        if note.gesture is not None:
            loud_db += note.gesture.level
        amp = 0.9 * 10.0 ** (loud_db / 20.0)
        prev_v = sylls[k - 1].nucleus if k else None
        next_v = sylls[k + 1].nucleus if k + 1 < len(sylls) else None
        t = note.start - sum(onset[k])
        gap_before = t - (segs[-1].t1 if segs else 0.0)
        if gap_before > voice.breathe:  # a moment's quiet, then an audible in-breath before the phrase
            segs.append(Segment(t - min(0.2, gap_before - 0.12), t - 0.03, "breath", "breath", amp))
        for c, d in zip(syl.onset, onset[k]):
            segs.append(Segment(t, t + d, c, "onset", amp, prev_v, syl.nucleus))
            t += d
        v_end = max(limit(k) - sum(coda[k]), note.start + 0.04)
        light = word[k] in ph.FUNCTION_WORDS and note.vel < 0.75
        segs.append(Segment(note.start, v_end, syl.nucleus, "vowel", amp, prev_v, next_v,
                            note.gesture.swell if note.gesture is not None else 0.0, voice.reduce if light else 0.0))
        t = v_end
        for c, d in zip(syl.coda, coda[k]):
            segs.append(Segment(t, t + d, c, "coda", amp, syl.nucleus, next_v))
            t += d
    return segs


def _locus(c: str, seg: Segment) -> tuple[float, float, float]:
    """Formant targets at the constriction. Nasals share their place's locus
    with the stops (m with b, n with d, ng with g): the transitions into and
    out of a nasal are what tell them apart."""
    manner, place, _ = ph.CONSONANTS[c]
    if c in ph.SONORANT_FORMANTS and manner != "nasal":
        return ph.SONORANT_FORMANTS[c]
    neighbour = seg.next_vowel if seg.role == "onset" else seg.prev_vowel
    near = _vowel_formants(neighbour) if neighbour else ph.VOWEL_FORMANTS["AX"]
    if place == "velar":
        f2 = 0.6 * near[1] + 900.0
        return (300.0, f2, f2 + 400.0)
    if place == "glottal":
        return near
    return ph.LOCI[place]


def _stop_times(seg: Segment, voiced: bool) -> tuple[float, float]:
    """(release time, aspiration end) of a stop segment."""
    d = seg.t1 - seg.t0
    if seg.role == "onset":
        place = ph.CONSONANTS[seg.phone][1]
        asp = 0.0 if voiced else min(ph.VOICE_ONSET.get(place, 0.05), 0.6 * d)
        return seg.t1 - asp - 0.008, seg.t1
    return seg.t0 + 0.7 * d, seg.t1


def control_tracks(segs: list[Segment], n_blocks: int, sr: int, voice: VoiceParams) -> dict[str, np.ndarray]:
    tb = (np.arange(n_blocks) + 0.5) * BLOCK / sr
    keys: list[tuple[float, tuple[float, float, float]]] = []
    av = np.zeros(n_blocks)
    ah = np.zeros(n_blocks)
    rd = np.full(n_blocks, voice.rd + 0.2)
    nasal = np.zeros(n_blocks)
    zero = np.full(n_blocks, NASAL_POLE)  # scaled by the tract length with the pole, in sing()

    def span(t0: float, t1: float) -> slice:
        return slice(int(np.searchsorted(tb, t0)), int(np.searchsorted(tb, t1)))

    for s in segs:
        d = s.t1 - s.t0
        region = span(s.t0, s.t1)
        if s.role == "vowel":
            tau = min(0.035, 0.25 * d)
            schwa = np.array(ph.VOWEL_FORMANTS["AX"])

            def toward(f):  # a little word off the beat, sung partway to "uh"
                return tuple((1 - s.reduce) * np.array(f) + s.reduce * schwa)

            if s.phone in ph.DIPHTHONGS:
                targets = [toward(ph.VOWEL_FORMANTS[q]) for q in ph.DIPHTHONGS[s.phone]]
                glide = min(0.15, 0.4 * d)
                if len(targets) == 3:  # fire, wire: hold the first quality, turn through the second, let the er ring
                    a, b, c = targets
                    tail, turn = min(0.3, 0.3 * d), min(0.1, 0.25 * d)
                    keys += [(s.t0 + tau, a), (s.t1 - tail - turn, a), (s.t1 - tail, b), (s.t1 - 0.6 * tail, c), (s.t1 - 0.01, c)]
                else:
                    a, b = targets
                    keys += [(s.t0 + tau, a), (s.t1 - glide, a), (s.t1 - 0.01, b)]
            else:
                f = toward(ph.VOWEL_FORMANTS[s.phone])
                keys += [(s.t0 + tau, f), (s.t1 - tau, f)]
            # a held vowel fades from a third of the way through (voices tire and
            # let go), and a phrasing can have it grow or fade from start to end
            idx = np.arange(region.start, region.stop)
            x = np.clip((tb[idx] - s.t0) / max(d, 1e-3), 0.0, 1.0)
            fade = voice.taper * np.clip((x - 0.3) / 0.7, 0.0, 1.0) if d > 0.35 else 0.0
            swell = 10.0 ** ((fade + s.swell * x) / 20.0)
            av[idx] = s.amp * swell
            ah[region] = voice.breath * s.amp
            rd[region] = voice.rd - 0.8 * (s.amp - 0.9)
        elif s.role == "breath":
            ah[region] = 0.05 * s.amp
            keys.append(((s.t0 + s.t1) / 2, ph.VOWEL_FORMANTS["AX"]))
        elif s.role in ("onset", "coda"):
            manner, place, voiced = ph.CONSONANTS[s.phone]
            loc = _locus(s.phone, s)
            if manner == "stop" or manner == "affricate":
                release, _ = _stop_times(s, voiced)
                keys.append((release, loc))
                if voiced:
                    av[span(s.t0, release)] = 0.06 * s.amp  # a faint voice bar through the closure
                else:
                    ah[span(release, s.t1)] = 0.3 * s.amp  # aspiration after the release
                if voiced:
                    av[span(release, s.t1)] = 0.6 * s.amp
            elif manner == "fricative":
                keys.append(((s.t0 + s.t1) / 2, loc))
                if voiced:
                    av[region] = 0.2 * s.amp
            elif manner == "aspirate":
                # /h/ hands over to a breathy vowel: voicing fades in under the
                # noise, and the noise lingers into the vowel. Voicing switched on
                # at full strength right after it sounds like a p.
                ah[region] = 0.4 * s.amp
                idx = np.arange(region.start, region.stop)
                av[idx] = 0.35 * s.amp * np.clip((tb[idx] - s.t0) / max(d, 1e-3) * 2.0 - 1.0, 0.0, 1.0)
                tail = span(s.t1, s.t1 + 0.06)
                ah[tail] += 0.25 * s.amp * np.linspace(1.0, 0.0, tail.stop - tail.start)
            else:  # nasal, liquid, glide: voiced with their own formants
                keys.append(((s.t0 + s.t1) / 2, loc))
                av[region] = SONORANT_LEVELS[manner] * s.amp
                if manner == "nasal":
                    nasal[region] = 1.0
                    zero[region] = ph.NASAL_ZERO[s.phone]
            if s.phone not in ("L", "R", "W", "Y") and manner != "nasal":
                rd[region] = voice.rd + 0.25

    # Phrase endings: singers let the voice go over about a tenth of a second,
    # getting breathier. Voicing cut off in one step sounds like a final d or t.
    for k, seg in enumerate(segs):
        gap_after = segs[k + 1].t0 - seg.t1 if k + 1 < len(segs) else 1.0
        if gap_after < 0.05 or seg.role == "breath":
            continue
        voiced_end = seg.t1
        fade = span(voiced_end - voice.release, voiced_end)
        idx = np.arange(fade.start, fade.stop)
        w = np.clip((voiced_end - tb[idx]) / max(voice.release, 1e-3), 0.0, 1.0)  # 1 where the fade starts, 0 at the end
        av[idx] *= 0.5 - 0.5 * np.cos(np.pi * w)
        ah[idx] += voice.breath * seg.amp * 2.0 * np.sin(np.pi * w)

    keys.sort(key=lambda k: k[0])
    times = np.array([k[0] for k in keys])
    values = np.array([k[1] for k in keys])
    formants = np.stack([np.interp(tb, times, values[:, j]) for j in range(3)], axis=1)
    formants = _smooth(formants, 5) * voice.tract
    formants = np.concatenate([formants, np.tile(np.array(HIGH_FORMANTS) * voice.tract, (n_blocks, 1))], axis=1)

    nasal = _smooth(nasal, 4)
    zero = _smooth(zero, 4)
    bws = np.tile(BANDWIDTHS, (n_blocks, 1))
    bws[:, 0] += 60.0 * nasal
    bws[:, 1:3] += 160.0 * nasal[:, None]
    formants[:, 0] = formants[:, 0] * (1.0 - nasal) + NASAL_MURMUR_F1 * voice.tract * nasal
    return {
        "formants": formants,
        "bandwidths": bws,
        "av": _smooth(av, 5),  # voicing fades over ~15 ms; a hard edge sounds like a stop
        "ah": _smooth(ah, 3),
        "rd": _smooth(rd, 8),
        "nasal_zero": zero * voice.tract,
        "tb": tb,
    }


def _lowpassed_noise(rng: np.random.Generator, n: int, cutoff: float, rate: float) -> np.ndarray:
    x = sosfilt(butter(2, cutoff, fs=rate, output="sos"), rng.standard_normal(n))
    return x / (np.std(x) + 1e-12)


def line_release(dur: float) -> float:
    """How long before a line's last note ends the singer lets go of it, to breathe."""
    return min(0.3, 0.35 * dur)


def pitch_track(notes: list[Note], n_blocks: int, sr: int, voice: VoiceParams, rng, sounding=None,
                accents=None) -> np.ndarray:
    """f0 in Hz per block: glides between notes, a scoop into each phrase, vibrato, drift and jitter.
    sounding: when each note's vowel ends, so a phrasing's bends and falls happen while it can be heard.
    accents: cents to lift each note by, for the syllables leaned on hardest."""
    tb = (np.arange(n_blocks) + 0.5) * BLOCK / sr
    target = np.full(n_blocks, notes[0].pitch + voice.shift, dtype=float)
    vib_env = np.zeros(n_blocks)
    gestures = np.zeros(n_blocks)  # cents from a phrasing: scoops, bends and falls
    for k, note in enumerate(notes):
        p = note.pitch + voice.shift
        prev = notes[k - 1] if k else None
        g = note.gesture
        phrase_start = prev is None or note.start - (prev.start + prev.dur) > 0.05 or prev.line_end
        # a wider leap takes longer to sing across, and no two are sung alike
        glide = voice.glide * float(np.clip(0.76 + 0.06 * (abs(p - prev.pitch - voice.shift) - 2), 0.6, 1.8)) if prev else voice.glide
        glide *= float(np.exp(voice.glide_spread * rng.standard_normal()))
        glide = min(glide, 0.6 * prev.dur) if prev else glide
        t_on = note.start - 0.7 * glide
        if phrase_start and prev is not None:
            # move while the voice is silent: just after the last line let go
            breath = line_release(prev.dur) if prev.line_end else 0.0
            t_on = min(t_on, prev.start + prev.dur - breath + 0.01)
        after = tb >= t_on
        if phrase_start:
            # start a little under the note and rise into it; a phrasing's scoop is added below instead,
            # so that it always means how far off the note the vowel begins
            scoop = 0.0 if g is not None and g.scoop else voice.scoop
            rise = np.clip((tb - note.start + 0.12) / 0.2, 0.0, 1.0)
            target[after] = p - scoop * (1.0 - 0.5 * (1 - np.cos(np.pi * rise[after])))
        else:
            q = prev.pitch + voice.shift
            w = np.clip((tb - t_on) / glide, 0.0, 1.0)
            target[after] = q + (p - q) * 0.5 * (1 - np.cos(np.pi * w[after]))
            # Voices overshoot a new note a little and settle, like a damped
            # spring; a glide that lands dead on target sounds mechanical.
            t_arrive = t_on + glide
            x = tb[after] - t_arrive
            ring = np.where(x > 0, np.sin(np.pi * x / 0.13) * np.exp(-x / 0.07), 0.0)
            target[after] += voice.overshoot * (p - q) * ring
        end = note.start + note.dur
        v = np.clip((tb - note.start - voice.vibrato_delay) / 0.25, 0.0, 1.0)
        v *= np.clip((end - tb) / 0.08, 0.0, 1.0)
        inside = (tb >= note.start) & (tb < end)
        if g is not None and g.vibrato >= 0:
            v *= g.vibrato / max(voice.vibrato_depth, 1.0)
        elif note.dur < (0.55 if note.line_end else voice.vibrato_from):
            v *= 0.0  # a singer keeps vibrato for the notes they hold; the rest are sung straight
        vib_env[inside] = v[inside]
        if accents is not None and accents[k]:  # a note leaned on is lifted a little, eased in and out
            lift = accents[k] * np.clip((tb - note.start) / 0.05, 0.0, 1.0) * np.clip((end - tb) / 0.05, 0.0, 1.0)
            gestures[inside] += lift[inside]
        if g is not None:
            heard = min(sounding[k], end) if sounding is not None else end  # the vowel's own end
            dur = max(heard - note.start, 0.05)
            x = np.clip((tb - note.start) / dur, 0.0, 1.0)
            approach = min(0.12, 0.3 * dur)
            letgo = min(0.12, 0.35 * dur)
            into = np.clip((tb - note.start) / approach, 0.0, 1.0)
            out = np.clip((tb - (heard - letgo)) / letgo, 0.0, 1.0)
            shape = g.scoop * 0.5 * (1 + np.cos(np.pi * into))  # the vowel begins off the note and settles onto it
            shape = shape + g.bend * np.clip((x - 0.3) / 0.6, 0.0, 1.0)  # drifts while held
            shape = shape + g.fall * 0.5 * (1 - np.cos(np.pi * out))  # falls or lifts letting go
            # the note held a little sharp or flat, eased in and out so the glides between notes stay whole
            shape = shape + g.tune * np.clip((tb - note.start) / 0.03, 0.0, 1.0) * np.clip((end - tb) / 0.03, 0.0, 1.0)
            gestures[inside] += np.broadcast_to(shape, tb.shape)[inside]

    rate = sr / BLOCK
    vib_rate = voice.vibrato_rate * (1.0 + 0.05 * _lowpassed_noise(rng, n_blocks, 0.5, rate))
    vib_phase = 2 * np.pi * np.cumsum(vib_rate) / rate
    cents = voice.vibrato_depth * vib_env * np.sin(vib_phase) + gestures
    cents += voice.wander * _lowpassed_noise(rng, n_blocks, 1.0, rate)
    cents += 17.3 * voice.jitter * _lowpassed_noise(rng, n_blocks, 25.0, rate)
    return 440.0 * 2.0 ** ((target + cents / 100.0 - 69.0) / 12.0)


def sing(notes: list[Note], sr: int, voice: VoiceParams, seed: int = 0, lexicon: dict[str, str] | None = None) -> np.ndarray:
    """Render sung notes to a mono signal, vowels peaking near 0.3."""
    if voice.engine == "tube":
        from . import tubevoice

        return tubevoice.sing(notes, sr, voice, seed, lexicon)
    notes = sorted(notes, key=lambda n: n.start)
    rng = np.random.default_rng(seed)
    segs = schedule(notes, voice, lexicon)
    duration = max(s.t1 for s in segs) + 0.5
    n_blocks = int(np.ceil(duration * sr / BLOCK))
    n = n_blocks * BLOCK
    tracks = control_tracks(segs, n_blocks, sr, voice)
    vowels = [s for s in segs if s.role == "vowel"]
    accents = [voice.accent * float(np.clip(20 * np.log10(s.amp / 0.9) / 3.0, 0.0, 1.0)) for s in vowels]
    f0_blocks = pitch_track(notes, n_blocks, sr, voice, rng, [s.t1 for s in vowels], accents)

    # Singers raise the first formant to stay above a high fundamental.
    formants = tracks["formants"]
    formants[:, 0] = np.maximum(formants[:, 0], 1.1 * f0_blocks * (tracks["av"] > 0.3))
    for j in range(1, formants.shape[1]):
        formants[:, j] = np.maximum(formants[:, j], formants[:, j - 1] + 150.0)
    formants = np.minimum(formants, 0.45 * sr)

    t = (np.arange(n) + 0.5) / sr
    per_sample = lambda x: np.interp(t, tracks["tb"], x)  # noqa: E731
    f0 = per_sample(f0_blocks)
    av = per_sample(tracks["av"]) * (1.0 + 0.01 * voice.shimmer * _lowpassed_noise(rng, n, 30.0, sr))
    ah = per_sample(tracks["ah"])
    rd = per_sample(tracks["rd"])

    pulses, flow = glottis.source(f0, rd, sr, voice.tilt)
    voicing = np.clip(av / 0.6, 0.0, 1.0)  # when the folds vibrate, breath noise pulses with them
    breath = sosfilt(butter(1, 400.0, btype="highpass", fs=sr, output="sos"), rng.standard_normal(n))
    breath *= voicing * (0.25 + 0.75 * flow) + (1.0 - voicing)
    excitation = pulses * av + 0.6 * breath * ah

    zero = tracks["nasal_zero"]
    pole = NASAL_POLE * voice.tract
    excitation = tract.cascade(excitation, np.full((n_blocks, 1), pole), np.full((n_blocks, 1), 100.0), BLOCK, sr)
    excitation = tract.antiresonator(excitation, zero, np.full(n_blocks, 100.0), BLOCK, sr)
    y = tract.cascade(excitation, formants, tracks["bandwidths"], BLOCK, sr)
    y += fftconvolve(excitation, tract.upper_branch(sr, voice.tract, voice.mouth))[:n]

    # Reference level: the median vowel RMS, so noise levels are relative to singing.
    vowel_mask = np.zeros(n, dtype=bool)
    for s in segs:
        if s.role == "vowel":
            vowel_mask[int(s.t0 * sr) : int(s.t1 * sr)] = True
    ref = np.sqrt(np.mean(y[vowel_mask] ** 2)) if vowel_mask.any() else 1.0

    noise = rng.standard_normal(n)
    for s in segs:
        if s.role not in ("onset", "coda"):
            continue
        manner, place, voiced = ph.CONSONANTS[s.phone]
        events = []
        if manner == "fricative":
            ramp = 0.02 if s.phone in ("S", "Z", "SH", "ZH") else 0.035  # weak fricatives creep in
            events.append((s.t0, s.t1, *ph.FRICATION[s.phone], ramp))
        elif manner in ("stop", "affricate"):
            release, _ = _stop_times(s, voiced)
            shape, level = ph.BURSTS[place]
            if place == "velar":
                f2 = _locus(s.phone, s)[1]  # noise_band shapes are scaled by the tract below
                shape = [(f2, 900.0, 0.0), (3600.0, 1500.0, -8.0)]
            events.append((release, release + (0.008 if voiced else 0.012), shape, level - (3.0 if voiced else 0.0), 0.002))
            if manner == "affricate":
                sh_shape, sh_level = ph.FRICATION["ZH" if voiced else "SH"]
                events.append((release, s.t1, sh_shape, sh_level, 0.01))
        for t0, t1, shape, level, ramp in events:
            i0, i1 = int(t0 * sr), int(t1 * sr)
            if i1 <= i0:
                continue
            pad = int(0.01 * sr)
            lo, hi = max(i0 - pad, 0), min(i1 + pad, n)
            shaped = tract.noise_band(noise[lo:hi], [(c * voice.tract, b, g) for c, b, g in shape], sr)
            shaped /= np.sqrt(np.mean(shaped[i0 - lo : i1 - lo] ** 2)) + 1e-12
            env = np.clip(np.minimum((t[lo:hi] - t0) / ramp, (t1 - t[lo:hi]) / ramp), 0.0, 1.0)
            y[lo:hi] += ref * 10.0 ** (level / 20.0) * s.amp * env * shaped

    y = sosfilt(butter(1, 60.0, btype="highpass", fs=sr, output="sos"), y)
    return 0.3 * y / ref / np.sqrt(2.0)
