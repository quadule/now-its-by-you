"""The pedal steel and the slide guitar, measured as real ones are: in tune where the bar lands, the glide on the
beat, the pedal bend's rise, the volume pedal's swell, the long sustain, and the band's contract."""

import sys
import time
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import butter, hilbert, sosfiltfilt

from songbird.score import Note
from songbird.synth import instruments, steel
from songbird.theory import midi_to_hz

sys.path.insert(0, str(Path(__file__).parent))
from _fretted import cents, env_db, mono
from _fretted import render as _render
from _levels_b import TARGETS, loudness

SR = 44100


def render(name, notes, seconds, **settings):
    return _render(steel, name, notes, seconds, **{"wear": 0.0, "ornament": 0.0, **settings})


def note(pitch, start=0.1, dur=2.0, vel=0.6, art="", part="steel"):
    return Note(part, start, dur, float(pitch), vel, art=art)


def maker_where(test, name="steel"):
    """The first maker (by the registry's streams) whose instrument passes `test`."""
    from _levels_b import streams

    for m in range(40):
        seed = int(streams(name, 0, m)[1].integers(1 << 31))
        if test(steel._steel_built(seed) if name == "steel" else steel._slide_built(seed)):
            return m
    raise AssertionError("no such maker")


ET = maker_where(lambda d: d["thirds"] == 0.0)


def pitch_track(y, pitch, lo=-5.0, hi=5.0, smooth=0.01):
    """Cents against `pitch` of the partial near it, sample by sample (a band from lo to hi semitones)."""
    f = midi_to_hz(pitch)
    band = sosfiltfilt(butter(2, [f * 2 ** (lo / 12), f * 2 ** (hi / 12)], btype="bandpass", fs=SR, output="sos"),
                       mono(y))
    inst = np.diff(np.unwrap(np.angle(hilbert(band)))) * SR / (2 * np.pi)
    k = int(smooth * SR)
    return 1200 * np.log2(np.maximum(np.convolve(inst, np.ones(k) / k, mode="same"), 1.0) / f)


# --- the band's contract ---------------------------------------------------------------------------


def test_the_registry_plays_them_rather_than_their_stand_ins():
    for name in ("steel", "slide"):
        own, found = instruments.registered(name)
        assert own == name and found is not None and found[1] is steel
        info = instruments.spec(name)
        assert info["stand_in"] is None and set(steel.SPEC[name]["articulations"]) <= set(info["articulations"])
    assert instruments.spec("steel")["register"] == (47, 88)  # E9's low B to its highest string's 22nd fret
    notes = (note(69), note(73), note(76))
    band = instruments.render_other("steel", notes, SR, 3 * SR, {"maker": 0}, seed=5)
    rng = np.random.default_rng([5, 17, instruments.stream("steel")])
    make = np.random.default_rng([0, 29, instruments.stream("steel")])
    own = steel.render("steel", notes, SR, 3 * SR, rng, make, {**instruments.DEFAULTS, "maker": 0})
    assert np.allclose(band, instruments.place(own, *steel.SPEC["steel"]["place"]) * steel.SPEC["steel"]["level"])


@pytest.mark.parametrize("name", ["steel", "slide"])
def test_the_contract(name):
    silent = render(name, [], 1.0)
    assert silent.shape == (SR, 2) and not np.any(silent)
    notes = [note(64, start=0.3, dur=0.001, part=name), note(40, start=0.5, vel=1.0, part=name),
             note(99, start=0.7, vel=0.0, part=name), note(62, start=0.9, art="woodblock", part=name),
             note(60, start=5.0, part=name)]
    y = render(name, notes, 2.0)
    assert y.shape == (2 * SR, 2) and np.all(np.isfinite(y)) and np.any(y)
    assert np.max(np.abs(y[: int(0.29 * SR)])) < 1e-4 * np.max(np.abs(y))
    for ch in range(2):
        assert abs(y[:, ch].mean()) < 1e-3 * np.sqrt(np.mean(y[:, ch] ** 2))
    assert np.array_equal(y, render(name, notes, 2.0))
    assert not np.allclose(y, render(name, notes, 2.0, maker=3))


@pytest.mark.parametrize("name", ["steel", "slide"])
def test_every_articulation_renders_cleanly(name):
    arts = list(steel.SPEC[name]["articulations"]) + ["pizz", "chop", "no-such-art"]
    notes = []
    for k, art in enumerate(arts):
        t = 0.1 + 0.6 * k
        notes += [note(p, start=t, dur=0.55, vel=0.6, art=art, part=name) for p in ((62, 66, 69) if k % 2 else (57,))]
    y = render(name, notes, 0.6 * len(arts) + 1.0)
    placed = instruments.place(y, *steel.SPEC[name]["place"]) * steel.SPEC[name]["level"]
    assert np.all(np.isfinite(y)) and 0.01 < np.max(np.abs(placed)) < 2.0


@pytest.mark.parametrize("name", ["steel", "slide"])
def test_its_phrases_never_clip_and_its_amp_stays_clean(name):
    """Every phrase of the solo tool's, placed and levelled, peaks within 6 dB of full scale (a picked string's attack
    stands 20 dB over its loudness; the stems are floats, and the mix brings the band down to the voice); and the
    steel's amp is clean: a chord picked at 1.0 is as much louder than one at 0.36 as its strings are."""
    for phrase in phrases().PHRASES.values():
        for part, notes in phrase["parts"].items():
            if part != name:
                continue
            s = {k: v for k, v in (phrase.get("settings") or {}).items() if k != "tempo"}
            length = int((max(n.start + n.dur for n in notes) + 1.0) * SR)
            y = render(name, notes, length / SR, **s)
            placed = instruments.place(y, *steel.SPEC[name]["place"]) * steel.SPEC[name]["level"]
            assert np.all(np.isfinite(y)) and np.max(np.abs(placed)) < 2.0
    if name == "steel":
        soft, hard = (render("steel", [note(p, vel=v) for p in (69, 74, 78)], 1.5, maker=ET) for v in (0.36, 1.0))
        rise = 20 * np.log10(np.sqrt(np.mean(hard**2)) / np.sqrt(np.mean(soft**2)))
        assert 7.5 < rise < 12.0


# --- the pedal steel ------------------------------------------------------------------------------


def test_a_chord_no_bar_can_hold_is_played_as_far_as_it_reaches():
    """B2 with E6 can't be held at one bar position: the player leaves out the high note rather than fail."""
    keep, g = steel.reachable((47, 88), 5)
    assert keep == (0,) and steel.OPEN[g.strings[0]] + g.bar + g.change[g.strings[0]] == 47
    y = render("steel", [note(47), note(88), note(62, start=1.0, dur=1.0)], 2.5)
    assert np.all(np.isfinite(y)) and np.any(y)
    y = render("slide", [note(40, part="slide"), note(83, part="slide")], 2.5)
    assert np.all(np.isfinite(y)) and np.any(y)


def test_the_copedant():
    """E9 with the A, B and C pedals and four knee levers: A raises B to C#, B raises G# to A, the knee levers
    raise and lower the E's; two levers pulling one string opposite ways never go together."""
    names = {tuple(sorted(n)) for n, _ in steel.copedant()}
    assert ("A", "B") in names and ("LKL", "LKR") not in names and ("C", "LKR") not in names
    change = dict(zip(steel.ORDER, steel.change_of(("A", "B"))))
    assert change == {10: 2, 9: 0, 8: 0, 7: 0, 6: 1, 5: 2, 4: 0, 3: 1, 2: 0, 1: 0}
    # D at the tenth fret, then G with the A and B pedals down at the same fret: the steel's own move
    d = steel.grip((69, 74, 78), 10)
    g = steel.grip((71, 74, 79), d.bar, frozenset(d.strings), True)
    assert d.bar == g.bar == 10 and set(g.pedals) == {"A", "B"} and g.strings == d.strings


@pytest.mark.parametrize("pitch", [47, 52, 59, 66, 73, 80, 86])
def test_the_steel_is_in_tune_up_the_neck(pitch):
    y = render("steel", [note(pitch)], 2.5, maker=ET)
    assert abs(cents(y, pitch, 0.5, 2.0)) < 1.5


def test_a_player_who_tunes_the_thirds_flat():
    """Some players tune the G# strings (the open E chord's third) and the A pedal's C# flat, toward pure thirds."""
    assert steel.thirds_offset(steel.ORDER.index(3), 0, 10.0) == -10.0  # G#
    assert steel.thirds_offset(steel.ORDER.index(3), 1, 10.0) == 0.0  # the B pedal's A
    assert steel.thirds_offset(steel.ORDER.index(5), 2, 10.0) == -10.0  # the A pedal's C#
    assert steel.thirds_offset(steel.ORDER.index(4), 0, 10.0) == 0.0 and steel.thirds_offset(0, 0, 0.0) == 0.0


def test_the_bar_glides_onto_the_beat_and_lands_in_tune():
    """A glide takes a tenth or two of a second, half of it before the beat, and every note it lands on is in
    tune (within 2 cents, measured over the note once it has landed)."""
    notes = [note(69, dur=1.0), note(71, start=1.1, dur=1.0, art="glide"), note(74, start=2.1, dur=1.4, art="slur")]
    y = render("steel", notes, 4.0, maker=ET)
    for n, t0, t1 in ((notes[0], 0.3, 0.95), (notes[1], 1.3, 2.0), (notes[2], 2.35, 3.4)):
        assert abs(cents(y, n.pitch, t0, t1)) < 2.0
    c = pitch_track(y, 71)
    at = lambda t: c[int(t * SR)]
    assert -170 < at(1.1) < -30  # on the beat it is part way there
    assert abs(at(1.25)) < 25 and at(1.0) < -170  # a tenth of a second before, still on A; soon after, on B


def test_a_pedal_bend_rises_into_the_note():
    """Picked with its pedal or lever up and pressed in: the note starts a semitone or a tone under and rises
    to the pitch in 0.1 to 0.4 s, along an S-shaped curve (slow to start, easing onto the stop)."""
    y = render("steel", [note(61, start=0.2, art="bend")], 2.0, maker=ET)
    c = pitch_track(y, 61, -4, 3)
    start = np.median(c[int(0.21 * SR): int(0.23 * SR)])
    assert -220 < start < -80
    landed = np.flatnonzero(np.abs(c[int(0.2 * SR): int(1.0 * SR)]) < 15)
    assert len(landed) and 0.12 < landed[0] / SR < 0.45
    assert abs(cents(y, 61, 0.8, 1.9)) < 2.0


def test_the_volume_pedal_swells_a_note_in():
    """A swelled note's pick is 25 dB or more under where the swell arrives, a quarter to a whole second
    later; a plain one is loudest at its pick."""
    swell = env_db(render("steel", [note(66, start=0.2, dur=2.5, art="swell")], 3.0, maker=ET))
    plain = env_db(render("steel", [note(66, start=0.2, dur=2.5)], 3.0, maker=ET))
    top = int(np.argmax(swell))
    assert swell[21] < swell[top] - 25 and 0.25 < (top - 20) * 0.01 < 1.3
    assert int(np.argmax(plain)) < 26


def test_the_strings_ring_long_and_their_partials_die_by_their_frequency():
    """A steel's rigid body and a steel bar: a mid-register string's fundamental falls 60 dB in 7 to 13 s
    (as its pickup hears it, no amp), its fifth partial much sooner."""
    d = steel._steel_built(12345)
    strings, coil, circuit = steel._steel_strings(d, 0.5, 0.0)
    rng = np.random.default_rng(1)
    segs, bar, pedals, vib, _ = steel._bar_tracks(steel._groups([note(57, dur=9.0)]), SR, rng, d, 0.0, 10 * SR)
    steel._finish(segs, strings, SR, 10 * SR, bar, pedals, vib)
    v = steel._voltage(segs, strings, coil, circuit, SR, 10 * SR, rng)

    def t60(f, t0, t1):
        band = sosfiltfilt(butter(2, [f * 0.94, f * 1.06], btype="bandpass", fs=SR, output="sos"), v)
        env = 20 * np.log10(np.sqrt(np.convolve(band**2, np.ones(2205) / 2205, mode="valid"))[::2205] + 1e-12)
        x = np.arange(len(env)) / 20
        sel = (x >= t0) & (x <= t1)
        return -60 / np.polyfit(x[sel], env[sel], 1)[0]

    fund = t60(midi_to_hz(57), 0.5, 8.0)
    assert 7.0 < fund < 13.0 and t60(5 * midi_to_hz(57), 0.3, 3.0) < 0.6 * fund


def test_a_block_and_a_mute():
    """A muted note is blocked right after its pick: by 0.3 s only the amp's spring still rings, 10 dB and more
    under the plain note."""
    mute = env_db(render("steel", [note(64, dur=1.5, art="mute")], 2.0, maker=ET))
    plain = env_db(render("steel", [note(64, dur=1.5)], 2.0, maker=ET))
    assert np.mean(mute[30:60]) < np.mean(plain[30:60]) - 10 and plain[40] > plain.max() - 12


def test_the_bar_vibrato_rolls_both_ways():
    """The bar rocks either side of the fret (a finger can only push a string sharp): 5 to 6.5 Hz."""
    y = render("steel", [note(69, dur=3.0, art="vibrato")], 3.5, maker=ET, ornament=0.5)
    c = pitch_track(y, 69, -2, 2, smooth=0.02)[int(0.9 * SR): int(2.9 * SR)]
    assert c.min() < -5 and c.max() > 5 and abs(np.median(c)) < 4
    spec = np.abs(np.fft.rfft((c - c.mean()) * np.hanning(len(c)), 1 << 18))
    fr = np.fft.rfftfreq(1 << 18, 1 / SR)
    band = (fr > 2) & (fr < 10)
    assert 4.8 < fr[band][np.argmax(spec[band])] < 6.8


# --- the slide guitar -----------------------------------------------------------------------------


@pytest.mark.parametrize("kind", steel.KINDS)
@pytest.mark.parametrize("pitch", [50, 57, 66, 74])
def test_the_slide_lands_in_tune_on_every_body(kind, pitch):
    y = render("slide", [note(pitch, dur=2.0, part="slide")], 2.5, slide=kind)
    assert abs(cents(y, pitch, 0.4, 1.9)) < 2.0


def test_the_open_tuning_follows_the_key():
    assert steel.open_tuning(62, "open D")[0] == tuple(float(p) for p in steel.OPEN_D)
    assert steel.open_tuning(64, "open D")[0] == tuple(float(p + 2) for p in steel.OPEN_D)  # open E
    _, name, shift, capo = steel.open_tuning(67, "open D")
    assert name == "open G" and shift == 0 and capo == 0
    assert max(abs(s) for s in (steel.open_tuning(k, "open G")[2] for k in range(60, 72))) <= 3


def test_a_slide_note_lands_a_touch_flat_and_is_slid_into_from_below():
    plain = pitch_track(render("slide", [note(69, dur=1.5, part="slide")], 2.0, ornament=1.0), 69, -4, 3)
    slid = pitch_track(render("slide", [note(69, dur=1.5, art="slide", part="slide")], 2.0), 69, -5, 3)
    assert -45 < np.median(plain[int(0.11 * SR): int(0.13 * SR)]) < -5  # lands flat
    assert abs(np.median(plain[int(0.35 * SR): int(0.45 * SR)])) < 6  # and settles
    assert np.median(slid[int(0.11 * SR): int(0.13 * SR)]) < -120  # two or three semitones under
    assert abs(np.median(slid[int(0.4 * SR): int(0.5 * SR)])) < 6


def test_the_slide_glides_between_notes_without_a_pick():
    notes = [note(64, dur=1.0, part="slide"), note(69, start=1.1, dur=1.2, art="glide", part="slide")]
    y = render("slide", notes, 2.8)
    assert abs(cents(y, 69, 1.4, 2.2)) < 2.0
    c = pitch_track(y, 69, -7, 3)
    assert -400 < c[int(1.1 * SR)] < -100  # half way on the beat


def test_the_string_behind_the_slide():
    """The part between the slide and the nut is 1 - 2^(-x/12) of the string: an octave up at the twelfth fret,
    a twelfth up at the seventh; it falls as the slide climbs."""
    assert abs(steel.behind_semitones(12.0) - 12.0) < 1e-9 and abs(steel.behind_semitones(7.0) - 19.06) < 0.01
    assert steel.behind_semitones(5.0) > steel.behind_semitones(9.0)


# --- levels and cost ---------------------------------------------------------------------------------


def phrases():
    sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "instrument_phrases_b"))
    import steel as family

    return family


@pytest.mark.parametrize("name", ["steel", "slide"])
def test_a_typical_part_sits_at_its_target(name):
    kind, notes = phrases().LEVELS[name]
    length = int((max(n.start + n.dur for n in notes) + 1.0) * SR)
    for maker in (0, 1, 2):
        assert abs(loudness(steel, name, notes, length, maker=maker) - TARGETS[kind]) < 2.5


def test_a_typical_part_is_cheap():
    """Forty seconds of the steel's swelled line in well under three seconds of CPU."""
    _, notes = phrases().LEVELS["steel"]
    part = notes + [n.__class__(**{**n.__dict__, "start": n.start + 20.0}) for n in notes]
    render("steel", part[:3], 1.0)  # compile
    t = time.process_time()
    render("steel", part, 40.0)
    assert time.process_time() - t < 3.0
