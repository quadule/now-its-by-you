"""The modal renderer: struck modes ring at their frequency, decay as asked, and stop when damped."""

import numpy as np

from songbird.synth import modal

SR = 44100


def one_mode(t60=1.0, damped=0.1, damp_at=-1, force=None, channels=(1.0,)):
    out = np.zeros((len(channels), 3 * SR))
    force = np.hanning(90) if force is None else force
    modal.ring(out, 100, force, np.array([440.0]), np.array([0.0]), np.array([-1.0]), np.array([t60]),
               np.array([damped]), damp_at, int(0.01 * SR), np.array(channels), float(SR), 1e-9)
    return out


def rms(y, t0, t1):
    return np.sqrt(np.mean(y[int(t0 * SR): int(t1 * SR)] ** 2))


def test_a_mode_rings_at_its_frequency_and_falls_60_db_in_its_t60():
    y = one_mode()[0]
    seg = y[int(0.2 * SR): int(1.2 * SR)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 20))
    freqs = np.fft.rfftfreq(1 << 20, 1 / SR)
    assert abs(1200 * np.log2(freqs[np.argmax(spec)] / 440.0)) < 0.1
    assert abs(20 * np.log10(rms(y, 0.2, 0.3) / rms(y, 1.2, 1.3)) - 60.0) < 0.5


def test_a_driven_mode_starts_from_rest_without_a_click():
    y = one_mode()[0]
    assert np.all(y[:101] == 0.0)
    assert np.max(np.abs(np.diff(y[100:200]))) < 0.2 * np.max(np.abs(y))


def test_the_damper_takes_over_the_decay_and_channels_scale():
    out = one_mode(t60=10.0, damped=0.2, damp_at=int(0.5 * SR), channels=(0.5, 1.0))
    y = out[1]
    assert abs(20 * np.log10(rms(y, 0.6, 0.65) / rms(y, 0.7, 0.75)) - 30.0) < 1.0
    assert abs(20 * np.log10(rms(y, 0.1, 0.2) / rms(y, 0.3, 0.4)) - 1.2) < 0.3  # before it lands, a 10 s ring
    assert np.allclose(out[0], 0.5 * out[1])


def test_initial_amplitudes_ring_without_a_force():
    out = np.zeros((1, SR))
    modal.ring(out, 0, np.zeros(0), np.array([1000.0]), np.array([0.0]), np.array([1.0]), np.array([1.0]),
               np.array([1.0]), -1, 1.0, np.array([1.0]), float(SR), 1e-9)
    # z starts at i: its real part is -sin, a mode starting from zero displacement at full swing
    assert abs(out[0, 0]) < 1e-12 and abs(np.max(np.abs(out[0, :100])) - 1.0) < 0.01
    assert abs(out[0, 1] + np.sin(2 * np.pi * 1000 / SR) * np.exp(-6.9078 / SR)) < 1e-6
