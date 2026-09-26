from dataclasses import replace
from pathlib import Path

import numpy as np

from songbird import genome as G
from songbird.realize import choose_params, realize
from songbird.synth.voice import VoiceParams, schedule, sing

SKETCH = Path(__file__).parent.parent / "songs" / "b-coal-from-the-fire.json"


def refrain_notes():
    g = G.load(SKETCH)
    score = realize(g, replace(choose_params(g), form=("refrain",)))
    return sorted(score.part("voice"), key=lambda n: n.start)


def test_vowels_land_on_the_beat_and_nothing_overlaps():
    notes = refrain_notes()
    segs = schedule(notes, VoiceParams())
    vowels = [s for s in segs if s.role == "vowel"]
    assert [round(v.t0, 9) for v in vowels] == [round(n.start, 9) for n in notes]
    for a, b in zip(segs, segs[1:]):
        assert b.t0 >= a.t1 - 1e-9, (a, b)
        assert a.t1 > a.t0


def test_onset_consonants_come_before_the_beat():
    notes = refrain_notes()
    segs = schedule(notes, VoiceParams())
    first_k = next(s for s in segs if s.phone == "K" and s.role == "onset")
    assert first_k.t1 <= notes[0].start + 1e-9


def test_sing_is_finite_and_deterministic():
    notes = refrain_notes()[:6]
    a = sing(notes, 44100, VoiceParams(), seed=3)
    b = sing(notes, 44100, VoiceParams(), seed=3)
    assert np.all(np.isfinite(a)) and np.array_equal(a, b)
    assert 0.05 < np.sqrt(np.mean(a**2)) < 0.5


def test_little_words_and_unstressed_syllables_are_sung_lighter():
    from songbird import phonetics as ph

    g = G.load(Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json")
    score = realize(g, replace(choose_params(g), form=("verse", "refrain")))
    notes = sorted(score.part("voice"), key=lambda n: n.start)
    vowels = [s for s in schedule(notes, VoiceParams(), g.lexicon) if s.role == "vowel"]
    little = [s.amp for s, n in zip(vowels, notes) if n.word.replace("-", "").lower().strip(".,;:!?'") in ph.FUNCTION_WORDS]
    others = [s.amp for s, n in zip(vowels, notes) if n.word.replace("-", "").lower().strip(".,;:!?'") not in ph.FUNCTION_WORDS]
    assert np.median(little) < 0.85 * np.median(others)


def test_breaths_between_lines_are_quiet_bright_noise_and_move_nothing_else():
    g = G.load(Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json")
    score = realize(g, replace(choose_params(g), form=("verse",)))
    notes = sorted(score.part("voice"), key=lambda n: n.start)
    sr, voice = 24000, VoiceParams()
    segs = schedule(notes, voice, g.lexicon)
    breaths = [s for s in segs if s.role == "breath"]
    assert len(breaths) >= 3
    for s in breaths:  # each in the quiet between the voice letting go and the next line's first sound
        before = [x for x in segs if x.role != "breath" and x.t1 <= s.t0 + 1e-9]
        after = [x for x in segs if x.role != "breath" and x.t0 >= s.t1 - 1e-9]
        assert (not before or s.t0 - before[-1].t1 >= 0.04 - 1e-9) and after and after[0].t0 - s.t1 >= 0.04 - 1e-9
    y = sing(notes, sr, voice, seed=2, lexicon=g.lexicon)
    plain = sing(notes, sr, replace(voice, inhale=-200.0), seed=2, lexicon=g.lexicon)
    b = y - plain  # breathing is added on its own: everything else is exactly as it was
    assert np.array_equal(y[: int(breaths[0].t0 * sr)], plain[: int(breaths[0].t0 * sr)])
    vowels = np.concatenate([plain[int(s.t0 * sr): int(s.t1 * sr)] for s in segs if s.role == "vowel"])
    ref = np.sqrt(np.mean(vowels**2))
    win = int(0.03 * sr)
    for s in breaths:
        x = b[int(s.t0 * sr): int(s.t1 * sr)]
        peak = max(np.sqrt(np.mean(x[i: i + win] ** 2)) for i in range(0, len(x) - win, win // 3))
        assert -44.0 < 20 * np.log10(peak / ref) < -28.0
    x = np.concatenate([b[int(s.t0 * sr): int(s.t1 * sr)] for s in breaths])
    power = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    assert power[(f > 2000) & (f < 10000)].sum() > 3 * power[f < 1000].sum()  # a breath's hiss, not a vowel


def test_vibrato_is_kept_for_held_notes():
    from songbird.synth.voice import BLOCK, pitch_track

    notes = refrain_notes()
    voice = VoiceParams(jitter=0.0, wander=0.0)
    n_blocks = int((notes[-1].start + notes[-1].dur + 1.0) * 44100 / BLOCK)
    f0 = pitch_track(notes, n_blocks, 44100, voice, np.random.default_rng(0))
    tb = (np.arange(n_blocks) + 0.5) * BLOCK / 44100
    for n in notes:
        inside = (tb > n.start + 0.4) & (tb < n.start + n.dur - 0.1)
        if inside.sum() < 20:
            continue
        cents = 1200 * np.log2(f0[inside] / (440 * 2 ** ((n.pitch - 69) / 12)))
        wobble = np.std(cents)  # past the glide in, a straight note holds its pitch
        held = n.dur >= (0.55 if n.line_end else voice.vibrato_from)
        assert (wobble > 5) == held, (n.syllable, n.dur, wobble)
