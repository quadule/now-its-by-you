"""The electric instruments' electronics, measured against their circuits and what real ones do."""

import numpy as np
import pytest
from scipy.signal import butter, sosfiltfilt, stft

from songbird.synth import amp

SR = 44100


def spectrum(y: np.ndarray, t0: float, t1: float) -> tuple[np.ndarray, np.ndarray]:
    seg = y[int(t0 * SR): int(t1 * SR)]
    seg = seg * np.blackman(len(seg))
    return np.fft.rfftfreq(len(seg), 1 / SR), np.abs(np.fft.rfft(seg)) ** 2


def level_at(freqs, power, f, width=12.0):
    return power[np.abs(freqs - f) < width].max()


def test_a_12ax7_stage_biases_and_gains_as_its_datasheet_says():
    """250 V supply, 100 k plate resistor, 1.5 k bypassed cathode resistor: about -1.2 V of bias, 0.8 mA,
    a plate near 170 V and a gain of about 60 (the RCA 12AX7 sheet's 100 k load gives 55 to 65)."""
    bias, plate = amp.operating_point(250.0, 100e3, 1500.0)
    current = amp.plate_current(bias, plate)
    assert -1.5 < bias < -0.9 and 0.6e-3 < current < 1.1e-3 and 150 < plate < 190
    chain = amp.Chain(amp.Amp(), SR)
    assert -70 < chain.gain < -50


def test_a_valve_stage_is_asymmetric_until_it_clips_both_ways():
    """A triode's gain grows with its current, so a volt of drive swings the plate further down than up: the
    second harmonic leads (about -25 dB, 10 dB and more over the third). Driven to 5 V it flattens toward
    cutoff and clamps where its grid conducts, and the odd harmonics take over."""
    curve, drop, bias = amp.stage_table(250.0, 100e3, 1500.0, 100e3)
    lo, hi, n = amp.TABLE
    v = np.linspace(lo, hi, n)

    def harmonics(drive):
        y = np.interp(bias + drive * np.sin(2 * np.pi * np.arange(4096) / 4096), v, curve)
        h = np.abs(np.fft.rfft(y))
        return y, 20 * np.log10(h[2] / h[1]), 20 * np.log10(h[3] / h[1])

    y, h2, h3 = harmonics(1.0)
    assert -y.min() > 1.15 * y.max()
    assert -32 < h2 < -18 and h2 > h3 + 10
    _, h2, h3 = harmonics(5.0)
    assert h3 > h2 + 10 and h3 > -15
    assert drop[np.searchsorted(v, -2.0)] < 1e-3 < drop[np.searchsorted(v, 1.0)]  # the grid conducts past 0 V


def test_the_tone_stack_is_the_circuit():
    """The analytic third-order transfer function equals the network solved node by node, and the bilinear
    version at the oversampled rate matches it within a hundredth of a dB."""
    from scipy.signal import sosfreqz

    f = np.array([40.0, 100.0, 300.0, 700.0, 1500.0, 3000.0, 6000.0, 12000.0])
    for voicing in ("fender", "marshall"):
        for knobs in ((0.5, 0.5, 0.5), (0.9, 0.2, 0.7), (0.1, 0.8, 0.1)):
            b, a = amp.stack_ba(*knobs, voicing)
            direct = amp.stack_response(f, *knobs, voicing)
            analytic = np.polyval(b, 2j * np.pi * f) / np.polyval(a, 2j * np.pi * f)
            assert np.max(np.abs(20 * np.log10(np.abs(analytic / direct)))) < 1e-6
            _, h = sosfreqz(amp.digital(b, a, 4 * SR, 1000.0), worN=f, fs=4 * SR)
            assert np.max(np.abs(20 * np.log10(np.abs(h / direct)))) < 0.01


def test_the_fender_stack_scoops_the_mids_and_the_marshall_less():
    """At noon a Fender stack's response dips between 300 Hz and 1 kHz, 6 dB and more under its bass and
    treble; turning the middle down deepens the scoop; a Marshall's (a lower slope resistor, driven by a
    cathode follower) is shallower."""
    f = np.exp(np.linspace(np.log(50.0), np.log(8000.0), 200))

    def scoop(voicing, middle=0.5):
        db = 20 * np.log10(np.abs(amp.stack_response(f, 0.5, middle, 0.5, voicing)))
        i = np.argmin(db)
        ends = min(db[np.argmin(np.abs(f - 100))], db[np.argmin(np.abs(f - 5000))])
        return f[i], ends - db[i]

    at, depth = scoop("fender")
    assert 300 < at < 1000 and depth > 6
    assert scoop("fender", 0.0)[1] > depth + 3
    assert scoop("marshall")[1] < depth


def test_pickups_resonate_where_zollner_measures_them():
    """A single coil with its cable and pots resonates at 3.5 to 5 kHz, a humbucker at 2 to 3 kHz; a lightly
    loaded single coil's peak has a Q of 2 or more; rolling the tone knob back lowers and flattens it."""
    single = amp.resonance(*amp.pickup_ba(amp.SINGLE, pot=250e3, tone=None, tone_cap=47e-9, cable=450e-12))
    hum = amp.resonance(*amp.pickup_ba(amp.HUMBUCKER, pot=500e3, tone=500e3, tone_cap=22e-9, cable=450e-12))
    rolled = amp.resonance(*amp.pickup_ba(amp.HUMBUCKER, pot=500e3, tone=60e3, tone_cap=22e-9, cable=450e-12))
    assert 3500 < single[0] < 5000 and single[2] >= 2.0 and single[1] > 5
    assert 2000 < hum[0] < 3000
    assert rolled[0] < hum[0] and rolled[1] < hum[1] - 3


def test_the_spring_chirps_echoes_and_rings_down():
    """Välimäki, Parker and Abel's spring: the first arrival after one traversal, echoes a round trip apart,
    each a chirp whose highs (near the 4 kHz transition) arrive after its lows, ringing down in its T60."""
    tank = amp.Tank(traversals=(0.033,), t60=2.5)
    ir = amp.spring_ir(tank, SR)
    env = np.sqrt(np.convolve(ir**2, np.ones(64) / 64, mode="same"))
    first = np.argmax(env > 0.2 * env.max()) / SR
    assert abs(first - 0.033) < 0.004
    freqs, times, z = stft(ir, SR, nperseg=512, noverlap=480)
    early = times < 0.06

    def arrival(lo, hi):
        e = np.abs(z[(freqs >= lo) & (freqs <= hi)]).sum(axis=0)
        return times[early][np.argmax(e[early])]

    assert arrival(3200, 4000) - arrival(400, 800) > 0.004
    band = sosfiltfilt(butter(2, [300, 2000], btype="bandpass", fs=SR, output="sos"), ir)
    e = np.convolve(band**2, np.ones(441) / 441, mode="same")
    ac = np.correlate(e[: int(1.0 * SR)] - e[: int(1.0 * SR)].mean(), e[: int(1.0 * SR)] - e[: int(1.0 * SR)].mean(),
                      "full")[int(1.0 * SR) - 1:]
    lag = (np.argmax(ac[int(0.04 * SR): int(0.1 * SR)]) + int(0.04 * SR)) / SR
    assert abs(lag - 0.066) < 0.008  # a round trip
    hop = SR // 20
    lv = 10 * np.log10(np.convolve(ir**2, np.ones(hop) / hop, mode="valid")[::hop] + 1e-30)
    x = np.arange(len(lv)) / 20
    sel = (x > 0.2) & (x < 1.6)
    t60 = -60 / np.polyfit(x[sel], lv[sel], 1)[0]
    assert abs(t60 - 2.5) < 0.35


def test_the_cabinet_is_a_guitar_speaker():
    """Its cone's resonance at the bottom, a presence hump at 2 to 4 kHz, and above 5-6 kHz a fall of 20 dB
    and more by 10 kHz; two microphones that hear it alike but not the same."""
    cab = amp.Cabinet(fs=85.0, presence=(2800.0, 5.0, 1.2), rolloff=5500.0)
    ir = amp.cabinet_ir(cab, SR)
    f = np.fft.rfftfreq(1 << 15, 1 / SR)
    db = 20 * np.log10(np.abs(np.fft.rfft(ir[:, 0], 1 << 15)) + 1e-12)

    def at(x):
        return db[np.argmin(np.abs(f - x))]

    assert at(40) < at(85) - 8  # below the cone's resonance it hardly moves air
    top = f[(f > 1000) & (f < 8000)][np.argmax(db[(f > 1000) & (f < 8000)])]
    assert 1500 < top < 4500
    assert at(10000) < at(3000) - 20
    rho = np.corrcoef(ir[:, 0], ir[:, 1])[0, 1]
    assert 0.5 < rho < 0.97


def test_a_high_note_through_crunch_does_not_alias():
    """An E6 driven hard through the crunch amp, four times oversampled: nothing inharmonic within 60 dB
    of the fundamental, and next to nothing above 18 kHz once the cabinet has had it."""
    chain = amp.Chain(amp.Amp(volume=-4.0, voicing="marshall", headroom=38.0), SR, os_=4)
    f0 = 1318.51
    x = 0.8 * np.sin(2 * np.pi * f0 * np.arange(2 * SR) / SR)
    y = chain.run(x)
    freqs, p = spectrum(y, 0.5, 1.5)
    harmonic = np.zeros_like(freqs, bool)
    for k in range(1, 18):
        harmonic |= np.abs(freqs - k * f0) < 12
    fund = level_at(freqs, p, f0)
    assert 10 * np.log10(p[~harmonic & (freqs > 30)].max() / fund) < -60
    out = np.convolve(y, amp.cabinet_ir(amp.Cabinet(), SR)[:, 0])[: len(y)]
    freqs, p = spectrum(out, 0.5, 1.5)
    assert 10 * np.log10(p[freqs > 18000].sum() / p.sum()) < -60


def test_crunch_distorts_and_clean_barely_does():
    """A 0.2 V pickup signal: the clean amp's harmonics stay 25 dB and more down; turned up, they come within
    15 dB of the fundamental."""
    t = np.arange(SR) / SR
    x = 0.2 * np.sin(2 * np.pi * 220.0 * t)

    def worst(volume):
        y = amp.Chain(amp.Amp(volume=volume), SR).run(x)
        freqs, p = spectrum(y, 0.4, 1.0)
        fund = level_at(freqs, p, 220.0)
        return max(10 * np.log10(level_at(freqs, p, 220.0 * k) / fund) for k in range(2, 6))

    assert worst(-22.0) < -25
    assert worst(-5.0) > -15


def test_a_pushed_amp_breathes_after_a_hard_attack():
    """After a loud burst the second stage's coupling capacitor holds charge and the supply sags: a quiet
    tone right after is quieter than the same tone once the amp has recovered."""
    chain = amp.Chain(amp.Amp(volume=-5.0), SR)
    t = np.arange(int(1.5 * SR)) / SR
    x = 0.02 * np.sin(2 * np.pi * 440.0 * t)
    x[: int(0.3 * SR)] += 1.0 * np.sin(2 * np.pi * 110.0 * t[: int(0.3 * SR)])
    y = chain.run(x)
    probe = sosfiltfilt(butter(2, [380, 500], btype="bandpass", fs=SR, output="sos"), y)
    right_after = np.sqrt(np.mean(probe[int(0.32 * SR): int(0.37 * SR)] ** 2))
    later = np.sqrt(np.mean(probe[int(1.2 * SR): int(1.45 * SR)] ** 2))
    assert right_after < 0.8 * later


def test_the_tremolo_pulses_at_its_rate_locked_to_the_tempo():
    """An optical tremolo at the amp's own 5.5 Hz becomes the tempo's nearest subdivision in 4 to 7 Hz: at
    100 BPM, sixteenths (6.67 Hz) or eighth triplets (5 Hz)."""
    assert amp.synced(5.5, 100.0) in (5.0, 100.0 / 60.0 * 4)
    assert 4.0 <= amp.synced(5.5, 72.0) <= 7.0
    chain = amp.Chain(amp.Amp(volume=-22.0, tremolo=("optical", 5.5, 0.6)), SR)
    t = np.arange(3 * SR) / SR
    y = chain.run(0.2 * np.sin(2 * np.pi * 330.0 * t))
    env = np.sqrt(np.convolve(y**2, np.ones(441) / 441, mode="same"))[int(0.5 * SR): int(2.9 * SR)]
    spec = np.abs(np.fft.rfft((env - env.mean()) * np.hanning(len(env)), 1 << 20))
    f = np.fft.rfftfreq(1 << 20, 1 / SR)
    band = (f > 2) & (f < 12)
    assert abs(f[band][np.argmax(spec[band])] - 5.5) < 0.1
    assert env.min() < 0.6 * env.max()  # a deep, audible pulse


def test_the_amp_is_deterministic_causal_and_without_dc():
    """Nothing comes out before something goes in, and a driven, asymmetric amp leaves no offset: its
    coupling capacitors, transformer and speaker pass none."""
    chain = amp.Chain(amp.Amp(volume=-8.0, reverb=0.2), SR)
    t = np.arange(4 * SR) / SR
    x = 0.3 * np.sin(2 * np.pi * 196.0 * t) * np.sin(np.pi * np.clip((t - 0.5) / 2.0, 0.0, 1.0)) ** 2
    a = amp.play(chain, x)
    b = amp.play(chain, x)
    assert np.array_equal(a, b)
    assert np.max(np.abs(a[: int(0.5 * SR) - int(0.005 * SR)])) < 1e-4 * np.max(np.abs(a))
    for ch in range(2):
        assert abs(a[:, ch].mean()) < 1e-3 * np.sqrt(np.mean(a[:, ch] ** 2))


@pytest.mark.parametrize("os_", [2, 4])
def test_the_chain_is_cheap(os_):
    import time

    chain = amp.Chain(amp.Amp(volume=-8.0), SR, os_=os_)
    x = 0.2 * np.random.default_rng(0).standard_normal(10 * SR)
    chain.run(x[:1000])
    t = time.process_time()
    chain.run(x)
    assert time.process_time() - t < (0.6 if os_ == 2 else 1.0)  # ten seconds of guitar
