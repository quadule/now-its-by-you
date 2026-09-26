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
from scipy.interpolate import PchipInterpolator
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
    vibrato_rate: float = 5.6  # Hz (each note's own, around this)
    vibrato_depth: float = 22.0  # cents, a held note's vibrato once grown in (each note's own, around this)
    vibrato_delay: float = 0.25  # seconds into a note before vibrato starts (each note's own, around this)
    glide: float = 0.11  # sets how fast the voice moves between notes: 10-90% in half of this for a step, 4 ms more a semitone
    glide_spread: float = 0.35  # how unalike two moves are: their length (log scale), when they happen and how far past they go
    overshoot: float = 0.025  # fraction of each interval sung past the new note before settling, on average
    scoop: float = 0.35  # semitones below the note a phrase starts from, through an m, n, l, r, w or y (less otherwise)
    jitter: float = 0.4  # percent, fast pitch wobble
    wander: float = 9.0  # cents, slow pitch drift (1/f, as natural singers' held notes drift)
    shimmer: float = 2.5  # percent, fast amplitude wobble
    articulation: float = 1.0  # consonant length scale
    cluster: float = 0.7  # length of each consonant in a cluster within a syllable, against alone
    across: float = 1.0  # length of consonants where one syllable's coda meets the next one's onset
    glides: float = 1.0  # length scale for the consonants w and y, which singers linger in
    liquids: float = 1.0  # length scale for l and r
    release: float = 0.05  # seconds over which the voice lets go at a phrase end
    dynamics: float = 15.0  # dB of loudness per unit of stress; an even singer is low, an expressive one high
    lean: float = 1.0  # dB a word's stressed syllable is sung above its others (and they below it)
    light: float = 1.0  # dB softer for the little words between the ones that mean (a, the, it, and, of...)
    ease: float = 0.75  # dB softer for a line's first syllable, eased into
    let_go: float = 1.0  # dB softer for its last, let go of
    climb: float = 0.5  # dB louder per semitone above the line's middle
    taper: float = -4.0  # dB a held vowel fades from a fifth of the way through to its end, as natural singers' do
    vibrato_from: float = 0.7  # seconds of note on which about four in ten notes get vibrato (more at a line's end; never all)
    breathe: float = 0.18  # seconds between lines needed for an audible breath
    inhale: float = -36.0  # dB of that breath's loudest moment against the sung vowels, as the natural singers breathe
    accent: float = 8.0  # cents a strongly leaned-on note is lifted
    tremolo: float = 0.4  # dB the loudness swings with a vibrato of vibrato_depth
    waver: float = 2.2  # dB of slow unsteadiness in a held note's loudness: breath pressure never holds still
    spread: float = 1.0  # how unalike the singer's moves are: transitions, rises, vibratos, falls, consonants (0 sings each alike)
    focus: float = 1.0  # dB more on a word the lyric marks as its line's focus (*word*), most on its stressed syllable (2 cost words)
    reduce: float = 0.0  # how far a little word's vowel off the beat moves toward "uh" (0.3 cost the words: WER 15% -> 18%)
    mouth: float = 1.0  # cm radius of the mouth opening: small keeps the upper resonances ringing
    air: float = 0.0  # noise above 3.5 kHz pulsing with the voicing, against the harmonics (real voices are part noise up there)
    engine: str = "formant"  # "formant" (Klatt cascade), "learned" (songbird.synth.throat) or "tube" (waveguide, experimental)
    timbre: str = ""  # the learned engine's singer: weights over its trained singers, "bright:2,alto:1" (default all evenly)


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


def _consonant_duration(c: str, in_cluster: bool, onset: bool, voice: VoiceParams | None = None,
                        table: dict[str, float] | None = None) -> float:
    if table:  # measured lengths, "N coda" or "S onset cluster", already as a singer clusters them
        key = f"{c} {'onset' if onset else 'coda'}"
        found = table.get(key + " cluster" if in_cluster else key, table.get(key))
        if found is not None:
            return found
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


def schedule(notes: list[Note], voice: VoiceParams, lexicon: dict[str, str] | None = None,
             durations: dict[str, float] | None = None) -> list[Segment]:
    """Place every phoneme of every sung note in time. durations: how long each consonant lasts, by
    phone and place in the syllable ("N coda", "S onset cluster"), instead of the formant singer's
    rules (the learned throat sings with the lengths its teacher sang)."""
    # Pronounce word by word, then hand syllables back to their notes.
    sylls: list[ph.Syllable] = []
    i = 0
    while i < len(notes):
        n = notes[i].word_len
        sylls += ph.fit(notes[i].word or notes[i].syllable or "ah", n, lexicon)
        i += n
    if len(sylls) != len(notes):
        raise ValueError("syllables and notes disagree")

    onset = [[_consonant_duration(c, len(s.onset) > 1, True, voice, durations) * voice.articulation for c in s.onset]
             for s in sylls]
    coda = [[_consonant_duration(c, len(s.coda) > 1, False, voice, durations) * voice.articulation for c in s.coda]
            for s in sylls]
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
            word.append((notes[k].word or "").replace("-", "").lower().strip(".,;:!?\"'*"))
        k += n

    segs: list[Segment] = []
    for k, (note, syl) in enumerate(zip(notes, sylls)):
        loud_db = voice.dynamics * (note.vel - 0.75) + voice.climb * (note.pitch - line_median[k])
        if word_len[k] > 1:
            loud_db += voice.lean if syl.stressed else -voice.lean
        if word[k] in ph.FUNCTION_WORDS:
            loud_db -= voice.light
        if "*" in (note.word or ""):  # the line's focus, marked in the lyric: leaned on hardest
            loud_db += voice.focus if (syl.stressed or word_len[k] == 1) else 0.5 * voice.focus
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
        if gap_before > voice.breathe:  # an audible in-breath before the phrase (see breaths())
            end = t - 0.04 - 0.1 * min(max(gap_before - 0.3, 0.0), 0.7)  # quiet again just before it starts
            segs.append(Segment(max(end - breath_length(gap_before), t - gap_before + 0.04), end, "breath", "breath", amp))
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
            # a held vowel fades from a fifth of the way through (voices tire and
            # let go), and a phrasing can have it grow or fade from start to end
            idx = np.arange(region.start, region.stop)
            x = np.clip((tb[idx] - s.t0) / max(d, 1e-3), 0.0, 1.0)
            fade = voice.taper * np.clip((x - 0.2) / 0.8, 0.0, 1.0) if d > 0.25 else 0.0
            swell = 10.0 ** ((fade + s.swell * x) / 20.0)
            av[idx] = s.amp * swell
            ah[region] = voice.breath * s.amp
            rd[region] = voice.rd - 0.8 * (s.amp - 0.9)
        elif s.role == "breath":
            pass  # a breath is shaped noise added after the tract (breaths()), the same for every engine
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
    sounds = [s for s in segs if s.role != "breath"]
    for k, seg in enumerate(sounds):
        gap_after = sounds[k + 1].t0 - seg.t1 if k + 1 < len(sounds) else 1.0
        if gap_after < 0.05:
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


# A breath between phrases as natural singers breathe (SoulX's house singers, measured by
# tools/delivery.py): noise whose density per hertz is highest from 1 to 8 kHz and falls away below
# 500 Hz, rising in about 30 ms, fading slowly through its middle, and quiet again just before the
# next line's first sound. (Hz, dB per hertz; the octave bands measured -24, -18, -12, -5, -7, 0, -5.5.)
BREATH_SPECTRUM = ((0.0, -26.0), (125.0, -18.0), (375.0, -7.5), (750.0, -4.5), (1500.0, 0.0), (3000.0, -8.0),
                   (6000.0, -1.0), (10000.0, -6.5), (14000.0, -14.0), (24000.0, -30.0))


def breath_length(gap: float) -> float:
    """Seconds an audible breath lasts in a gap of this many seconds between phrases: most of a short gap
    (0.12 s in 0.2), up to 0.4 s in a long rest (natural singers: 0.10, 0.18 and 0.35 s in gaps of 0.1-0.2,
    0.2-0.4 and 0.4-1 s)."""
    return float(np.clip(0.6 * gap, 0.1, 0.4))


def breaths(segs: list[Segment], n: int, sr: int, voice: VoiceParams, seed: int) -> np.ndarray:
    """Every breath in a schedule as shaped noise, n samples long, against sung vowels of RMS 1. A breath
    before a louder phrase is deeper (half its level in dB), a long rest's a little more; no two sound
    quite alike (each takes its own tilt of the spectrum). Its own random stream, so breathing never
    moves the rest of the voice."""
    out = np.zeros(n)
    rng = np.random.default_rng([seed, 0xB4EA7])
    freq, gain = (np.array(v) for v in zip(*BREATH_SPECTRUM))
    for k, s in enumerate(segs):
        if s.role != "breath":
            continue
        i0, i1 = max(int(s.t0 * sr), 0), min(int(s.t1 * sr), n)
        m = i1 - i0
        if m < 64:
            continue
        f = np.fft.rfftfreq(m, 1.0 / sr)
        tilt = rng.normal(0.0, 1.5) * np.log2(np.maximum(f, 60.0) / 2000.0)  # dB: a breath a little darker or brighter
        shaped = np.fft.irfft(np.fft.rfft(rng.standard_normal(m)) * 10.0 ** ((np.interp(f, freq, gain) + tilt) / 20.0), m)
        shaped /= np.sqrt(np.mean(shaped**2)) + 1e-12
        x = np.linspace(0.0, 1.0, m)
        rise = min(0.03 * sr / m, 0.3)
        env = 0.5 - 0.5 * np.cos(np.pi * np.clip(x / rise, 0.0, 1.0))
        env *= 1.0 - 0.15 * np.clip((x - rise) / max(0.6 - rise, 1e-3), 0.0, 1.0)
        env *= 0.5 + 0.5 * np.cos(np.pi * np.clip((x - 0.6) / 0.4, 0.0, 1.0))
        gap = (segs[k + 1].t0 if k + 1 < len(segs) else s.t1) - (segs[k - 1].t1 if k else 0.0)
        level = voice.inhale + 0.5 * 20.0 * np.log10(max(s.amp, 1e-3) / 0.9) + 2.0 * float(np.clip((gap - 0.3) / 0.5, 0.0, 1.0))
        out[i0:i1] += 10.0 ** (level / 20.0) * env * shaped
    return out


# How natural singers get from one legato note to the next (SoulX's house singers, measured by
# tools/delivery.py over 1,400 transitions, each aligned at its midpoint and timed in its own 10-90%
# duration): a little slower to leave the old note than to arrive at the new one. Around that shape each
# transition has its own moment, length and distance past the note (overshoot_bump), and a move up
# often dips a little first (preparation_dip).
GLIDE_TAU = np.arange(-1.5, 2.51, 0.25)
GLIDE_SHAPE = PchipInterpolator(GLIDE_TAU, [0.0, 0.0, 0.0, 0.012, 0.1, 0.265, 0.545, 0.812, 0.949, 0.99, 1.0,
                                            1.0, 1.0, 1.0, 1.0, 1.0, 1.0])


def glide_shape(tau: np.ndarray) -> np.ndarray:
    """0 to 1 across a transition, tau in its 10-90% durations from its midpoint."""
    return GLIDE_SHAPE(np.clip(tau, GLIDE_TAU[0], GLIDE_TAU[-1]))


def overshoot_bump(tau: np.ndarray) -> np.ndarray:
    """Where a transition overshoots: most one duration past its midpoint, gone by about two and a half."""
    return np.exp(-(((tau - 1.0) / 0.6) ** 2))


def preparation_dip(tau: np.ndarray) -> np.ndarray:
    """Where a move up dips first: most about a duration before its midpoint, gone as it rises."""
    return np.exp(-(((tau + 0.9) / 0.35) ** 2))


# A phrase's first note: natural singers rise into it over the first tenth of a second or so of its
# first syllable, heard through an m, n, l, r, w or y or at a vowel, hidden inside a voiceless consonant
# (the house singers come up about 40 cents through a sonorant and start a vowel after an s or a t
# on pitch), and hardly at all through a voiced stop or fricative; about one phrase in four starts flat
# or a little above.
FLAT_START = 0.25

# The pitch around consonants, in cents (the house singers between two notes on the same pitch): it sags
# through a voiced stop or fricative and comes back a little high, falls a little as the voice stops for
# a voiceless one, and starts again a little high after it.
SAG, SAG_REBOUND, STOP_FALL, RESTART = -20.0, 5.0, -10.0, 5.0
FINAL_FALL = -18.0  # cents a line's last vowel falls as the voice lets go of it (natural singers: -11 to -23)


def phrase_starts(notes: list[Note]) -> list[bool]:
    """Whether each note starts a phrase: the first, after a rest, or a line's first."""
    return [k == 0 or n.start - (notes[k - 1].start + notes[k - 1].dur) > 0.05 or notes[k - 1].line_end
            for k, n in enumerate(notes)]


def syllable_starts(segs: list[Segment] | None, n_notes: int) -> list[float | None]:
    """When each note's syllable starts: its first consonant, else its vowel (None without a schedule)."""
    out: list[float | None] = [None] * n_notes
    k, first = 0, None
    for s in segs or ():
        if s.role == "onset" and first is None:
            first = s.t0
        elif s.role == "vowel":
            if k < n_notes:
                out[k] = first if first is not None else s.t0
            k, first = k + 1, None
    return out


def voiced_closure(segs: list[Segment] | None, n_notes: int) -> list[bool]:
    """Whether each note's syllable starts with a voiced stop or fricative (b, d, g, v, z, the...)."""
    out, k, first = [False] * n_notes, 0, None
    for s in segs or ():
        if s.role == "onset" and first is None:
            first = s.phone
        elif s.role == "vowel":
            if first is not None and k < n_notes:
                manner, _, voiced = ph.CONSONANTS[first]
                out[k] = voiced and manner in ("stop", "fricative", "affricate")
            k, first = k + 1, None
    return out


def consonant_pitch(segs: list[Segment], tb: np.ndarray) -> np.ndarray:
    """Cents the consonants move the pitch by (SAG and the rest), per block time."""
    out = np.zeros_like(tb)
    sounds = [s for s in segs if s.role != "breath"]

    def voiced_sound(s: Segment | None) -> bool:
        return s is not None and (s.role == "vowel" or ph.CONSONANTS[s.phone][2])

    for i, s in enumerate(sounds):
        if s.role not in ("onset", "coda"):
            continue
        manner, _, voiced = ph.CONSONANTS[s.phone]
        before = sounds[i - 1] if i and sounds[i - 1].t1 > s.t0 - 0.02 else None
        after = sounds[i + 1] if i + 1 < len(sounds) and sounds[i + 1].t0 < s.t1 + 0.02 else None
        if voiced and manner in ("stop", "fricative", "affricate") and voiced_sound(before):  # between voiced sounds
            mid, half = 0.5 * (s.t0 + s.t1), 0.5 * (s.t1 - s.t0) + 0.03
            out += SAG * (0.5 + 0.5 * np.cos(np.pi * np.clip((tb - mid) / half, -1.0, 1.0)))
            out += SAG_REBOUND * np.clip((tb - s.t1 + 0.01) / 0.03, 0.0, 1.0) * np.clip((s.t1 + 0.1 - tb) / 0.07, 0.0, 1.0)
        elif not voiced:
            if voiced_sound(before):  # the voice stopping: falls into it, then (unheard) back
                out += STOP_FALL * np.clip((tb - s.t0 + 0.06) / 0.06, 0.0, 1.0) * np.clip((s.t1 - tb) / max(s.t1 - s.t0, 0.02), 0.0, 1.0)
            if voiced_sound(after):  # starting again a little high, settling in 80 ms
                out += RESTART * np.clip((tb - s.t1 + 0.03) / 0.03, 0.0, 1.0) * np.clip((s.t1 + 0.08 - tb) / 0.08, 0.0, 1.0)
    return out


def vibrato_chance(dur: float, line_end: bool, half: float, lean: float = 0.0) -> float:
    """How likely a singer is to put vibrato on a note this long (seconds): natural singers on about 0.3
    of notes of 0.5-0.9 s, 0.55 of 0.9-1.5 s and 0.7 of longer ones, 0.15 more at a line's end, never all
    (`half` moves the curve; lean, in log-odds, is a phrase's own taste for it)."""
    if dur < 0.45:
        return 0.0
    return min(0.75 / (1.0 + np.exp(-(dur - half) / 0.25 - lean)) + (0.15 if line_end else 0.0), 0.9)


def _colored(rng: np.random.Generator, n: int, rate: float, corner: float, top: float, steep: int = 4) -> np.ndarray:
    """Unit-SD noise, flat below `corner` Hz, its power falling as 1/f up to `top` Hz and faster after: the
    slow, unsteady drift of a held pitch, or of breath pressure."""
    f = np.fft.rfftfreq(n, 1.0 / rate)
    gain = 1.0 / np.sqrt((1.0 + f / corner) * (1.0 + (f / top) ** steep))
    x = np.fft.irfft(np.fft.rfft(rng.standard_normal(n)) * gain, n)
    return x / (np.std(x) + 1e-12)


def pitch_track(notes: list[Note], n_blocks: int, sr: int, voice: VoiceParams, rng, sounding=None,
                accents=None, segs: list[Segment] | None = None, parts: dict | None = None) -> np.ndarray:
    """f0 in Hz per block: transitions between notes, a rise into each phrase, vibrato on some held
    notes, the pitch around consonants, a fall as a line lets go, drift and jitter.
    sounding: when each note's vowel ends, so a phrasing's bends and falls happen while it can be heard.
    accents: cents to lift each note by, for the syllables leaned on hardest.
    segs: the schedule (schedule()), for when each syllable starts and where its consonants are; without
    it, phrases rise from their vowels and consonants leave the pitch alone.
    parts: a dict to receive "tremolo", the vibrato's swing in loudness per block (1 at a vibrato of
    vibrato_depth, with each note's own phase), for the engines to apply.

    No two transitions, rises or vibratos come out alike: each draws its own moment, length, overshoot and
    preparation, depth, rate, extent and onset, and each phrase its own lean in time and taste for vibrato,
    all scaled by voice.spread (0 sings every one alike). The draws come from streams spawned off rng, so
    the engines, which call this first, sing the same pitch."""
    tb = (np.arange(n_blocks) + 0.5) * BLOCK / sr
    n = len(notes)
    s = voice.spread
    note_rng, phrase_rng, vib_rng, drift_rng = rng.spawn(4)
    z = note_rng.standard_normal((n, 10))
    u = note_rng.random((n, 3))
    starts = phrase_starts(notes)
    phrase = np.cumsum(starts) - 1
    zp = phrase_rng.standard_normal((int(phrase[-1]) + 1, 2))  # a phrase's lean in time, and its taste for vibrato
    begins = syllable_starts(segs, n)
    closes = voiced_closure(segs, n)
    target = np.full(n_blocks, notes[0].pitch + voice.shift, dtype=float)
    vib_env = np.zeros(n_blocks)  # cents of vibrato
    vib_rate = np.full(n_blocks, voice.vibrato_rate)
    trem_phase = np.zeros(n_blocks)
    gestures = np.zeros(n_blocks)  # cents from a phrasing (scoops, bends and falls) and the machine's own lifts and falls
    for k, note in enumerate(notes):
        p = note.pitch + voice.shift
        prev = notes[k - 1] if k else None
        g = note.gesture
        end = note.start + note.dur
        heard = min(sounding[k], end) if sounding is not None else end  # the vowel's own end
        zk = z[k]
        if starts[k]:
            # rise into the phrase over its first syllable's first tenth of a second; a phrasing's scoop is
            # added below instead, so that it always means how far off the note the vowel begins
            if g is not None and g.scoop:
                depth = 0.0
            elif u[k, 0] < FLAT_START * min(s, 1.0):
                depth = 0.08 * voice.scoop * s * float(zk[4])  # about level, either way
            else:  # (a voiced stop or fricative starts the voice near the note already)
                depth = voice.scoop * float(np.exp(0.6 * s * zk[4])) * (0.3 if closes[k] else 1.0)
            dur = 0.05 * float(np.exp(0.3 * s * zk[0]))
            t50 = (begins[k] if begins[k] is not None else note.start) + 1.5 * dur
            t_on = t50 - 1.5 * dur
            if prev is not None:  # move while the voice is silent: just after the last line let go
                t_on = min(t_on, prev.start + prev.dur - (line_release(prev.dur) if prev.line_end else 0.0) + 0.01)
            after = tb >= t_on
            target[after] = p - depth * (1.0 - glide_shape((tb[after] - t50) / dur))
        else:
            # a wider leap takes a little longer (about 4 ms a semitone); each move has its own length, its
            # own moment (upward ones near the vowel's start, downward ones sooner, a phrase leaning one way
            # or the other), its own distance past the new note, and a move up its own little dip first
            d = p - (prev.pitch + voice.shift)
            dur = voice.glide * (0.45 + 0.04 * abs(d)) * float(np.exp(voice.glide_spread * s * zk[0]))
            dur = min(dur, 0.35 * prev.dur, 0.5 * note.dur)
            when = 0.012 * s * zp[phrase[k], 0] + min(0.03 * s, 0.1 * min(prev.dur, note.dur)) * zk[1]
            t50 = note.start + (-0.01 if d > 0 else -0.04) + when
            lo, hi = prev.start + 0.5 * prev.dur + 0.75 * dur, note.start + 0.3 * note.dur
            t50 = float(np.clip(t50, lo, hi)) if lo < hi else note.start - 0.2 * dur
            t_on = t50 - 2.0 * dur
            after = tb >= t_on
            q = float(target[min(int(np.searchsorted(tb, t_on)), n_blocks - 1)])  # wherever the voice is as it leaves
            tau = (tb[after] - t50) / dur
            past = voice.overshoot * (p - q) + 0.1 * s * zk[2]  # semitones past the note, at most
            dip = -(0.03 * (p - q) + 0.04) * float(np.exp(0.5 * s * zk[3])) if p > q else 0.0
            target[after] = q + (p - q) * glide_shape(tau) + past * overshoot_bump(tau) + dip * preparation_dip(tau)
        inside = (tb >= note.start) & (tb < end)
        # vibrato on some held notes: likelier the longer the note and at a line's end, and in some phrases
        # more than others; each its own depth, rate and onset, growing in over a few tenths of a second and
        # a little more through a long note, and at a line's end blooming, slower and wider, as it lets go
        chance = vibrato_chance(note.dur, note.line_end, voice.vibrato_from, 0.8 * s * zp[phrase[k], 1])
        wants = (u[k, 1] if s > 0 else 0.5) < chance
        extent = voice.vibrato_depth * float(np.clip(np.exp(0.35 * s * zk[5]), 0.4, 2.0))
        delay = min(voice.vibrato_delay * float(np.exp(0.5 * s * zk[6])), 0.35 * max(heard - note.start, 0.0))
        rate_k = voice.vibrato_rate + 0.4 * s * float(zk[7])
        if g is not None and g.vibrato >= 0:
            wants, extent = g.vibrato > 0, g.vibrato
        if wants:
            x = np.maximum(tb - note.start - delay, 0.0)
            v = (1.0 - np.exp(-x / 0.12)) * (0.85 + 0.15 * np.clip((x - 0.4) / 0.8, 0.0, 1.0))
            v *= np.clip((end - tb) / 0.08, 0.0, 1.0)
            here = np.full(n_blocks, rate_k)
            if note.line_end:
                bloom = np.clip((tb - (heard - 0.3)) / 0.3, 0.0, 1.0)
                v, here = v * (1.0 + 0.3 * bloom), here * (1.0 - 0.1 * bloom)
            vib_env[inside] = extent * v[inside]
            vib_rate[inside] = here[inside]
            trem_phase[inside] = 2 * np.pi * u[k, 2]
        if accents is not None and accents[k]:  # a note leaned on is lifted a little, eased in and out
            lift = accents[k] * np.clip((tb - note.start) / 0.05, 0.0, 1.0) * np.clip((end - tb) / 0.05, 0.0, 1.0)
            gestures[inside] += lift[inside]
        if note.line_end and heard - note.start > 0.15:  # the voice falls a little as it lets go of the line
            letgo = min(0.1, 0.4 * (heard - note.start))
            fall = FINAL_FALL * float(np.exp(0.4 * s * zk[9]))
            drop = fall * (0.5 - 0.5 * np.cos(np.pi * np.clip((tb - (heard - letgo)) / letgo, 0.0, 1.0)))
            gestures[inside] += drop[inside]
        if g is not None:
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
    # a vibrato's rate and extent both drift within the note (natural singers: rate CV ~0.2, extent ~0.6)
    vib_rate = vib_rate * (1.0 + 0.2 * s * _lowpassed_noise(vib_rng, n_blocks, 2.0, rate))
    vib_phase = 2 * np.pi * np.cumsum(vib_rate) / rate
    vib_env = vib_env * np.maximum(1.0 + 0.8 * s * _lowpassed_noise(vib_rng, n_blocks, 2.0, rate), 0.15)
    cents = vib_env * np.sin(vib_phase) + gestures
    if segs is not None:
        cents += consonant_pitch(segs, tb)
    cents += voice.wander * _colored(drift_rng, n_blocks, rate, 1.0, 4.0)
    cents += 17.3 * voice.jitter * _lowpassed_noise(drift_rng, n_blocks, 25.0, rate)
    if parts is not None:
        parts["tremolo"] = vib_env / max(voice.vibrato_depth, 1.0) * np.sin(vib_phase + trem_phase)
    return 440.0 * 2.0 ** ((target + cents / 100.0 - 69.0) / 12.0)


def sway(n: int, rate: float, voice: VoiceParams, seed: int, tremolo: np.ndarray | None = None,
         slow: bool = True) -> np.ndarray:
    """The voice's loudness moving under a held note, in dB per point (n points at `rate` a second): the
    vibrato's own swing (voice.tremolo, from pitch_track's parts) and, if slow, breath pressure that never
    quite holds still (voice.waver, 1/f to 1.5 Hz and falling after, as natural singers' held notes move).
    Its own random stream."""
    db = np.zeros(n)
    if tremolo is not None:
        db += voice.tremolo * tremolo[:n]
    if slow and voice.waver:
        db += voice.waver * voice.spread * _colored(np.random.default_rng([seed, 0x5A7]), n, rate, 0.5, 1.5, steep=2)
    return db


def sing(notes: list[Note], sr: int, voice: VoiceParams, seed: int = 0, lexicon: dict[str, str] | None = None) -> np.ndarray:
    """Render sung notes to a mono signal, vowels peaking near 0.3."""
    if voice.engine == "tube":
        from . import tubevoice

        return tubevoice.sing(notes, sr, voice, seed, lexicon)
    if voice.engine == "learned":
        from . import throat

        return throat.sing(notes, sr, voice, seed, lexicon, mix=voice.timbre)
    notes = sorted(notes, key=lambda n: n.start)
    rng = np.random.default_rng(seed)
    segs = schedule(notes, voice, lexicon)
    duration = max(s.t1 for s in segs) + 0.5
    n_blocks = int(np.ceil(duration * sr / BLOCK))
    n = n_blocks * BLOCK
    tracks = control_tracks(segs, n_blocks, sr, voice)
    vowels = [s for s in segs if s.role == "vowel"]
    accents = [voice.accent * float(np.clip(20 * np.log10(s.amp / 0.9) / 3.0, 0.0, 1.0)) for s in vowels]
    parts: dict = {}
    f0_blocks = pitch_track(notes, n_blocks, sr, voice, rng, [s.t1 for s in vowels], accents, segs, parts)
    tracks["av"] = tracks["av"] * 10.0 ** (sway(n_blocks, sr / BLOCK, voice, seed, parts["tremolo"]) / 20.0)

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
    if voice.air > 0:  # turbulence at the folds: the top of a real voice is part noise, pulsing with the flow
        air = sosfilt(butter(2, 3500.0, btype="highpass", fs=sr, output="sos"), rng.standard_normal(n))
        excitation += voice.air * av * (0.3 + 0.7 * flow) * air

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

    y += ref * breaths(segs, n, sr, voice, seed)
    y = sosfilt(butter(1, 60.0, btype="highpass", fs=sr, output="sos"), y)
    return 0.3 * y / ref / np.sqrt(2.0)
