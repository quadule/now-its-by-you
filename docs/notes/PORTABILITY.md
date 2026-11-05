# Portability profile: where the compiled loops' time goes (2026-09-29)

*An engineering note, September 29, 2026, for the browser spike ([BROWSER-RENDER.md](BROWSER-RENDER.md)).*

For the browser spike: which numba kernels a port has to make fast, and which of them can't be turned
into whole-array operations. Without numba's compiler (`NUMBA_DISABLE_JIT=1`) every kernel runs as Python,
one sample at a time: H's refrain alone takes about three minutes on one thread instead of 2.7 s.

## How it was measured

- H's seed rendition (`cli.render_one`, as docs/notes/PERFORMANCE.md measures it), `SONGBIRD_THREADS=1`, Apple
  M1 Max, numba's cache warm, the tree of 2026-09-29 (after the memory work in docs/notes/PERFORMANCE.md).
- Every numba dispatcher in `songbird.synth.*` wrapped with a timer. A kernel called from inside another
  kernel counts in its caller (`fx._soft` in `fx._saturate`, `bowed._read` in `bowed.run`).
- "JIT": the whole song, 151 s of audio: **14.6 s**, of which **3.8 s (26%)** is inside the kernels. The rest
  is numpy and scipy (the vocoder's FFTs and complex exponentials about 4.5 s, the network 0.9 s, the bodies'
  and the room's FFT convolutions about 1.2 s, `sosfilt`/`lfilter`, per-note Python).
- "Interpreted": `NUMBA_DISABLE_JIT=1`, H with `form=("refrain",)` only (the machine was loaded by other
  work, so the absolute seconds are high; the shares are what matter): **194 s**, **98%** inside the kernels.
  The same refrain compiled: 2.7 s (0.70 s in kernels).
- `tools/kernel_time.py` makes these tables (`--form refrain`, `NUMBA_DISABLE_JIT=1` for the interpreted one).

## The kernels, by their share of the compiled render

"Recursive" means the loop carries state from one sample to the next (a filter's memory, a delay line
fed back, a phase, a running sum): it can't be split into whole-array operations along time, only run in
order (or parallelised across the channels, strings or modes it runs over, where noted). None of these
kernels uses `fastmath` (numba then keeps every operation in order, with no fused multiply-adds, which is
what keeps a render byte-identical to itself).

| # | kernel | where | compiled, whole song | interpreted, refrain | what it does | recursive per sample |
|---|---|---|---|---|---|---|
| 1 | `drum._ring` | songbird/synth/drum.py:62 | 0.49 s (3.3%), 207 calls | 17.4 s (9.0%) | the frame drum's modes: each a two-pole resonator (`y0 = c*y1 - d*y2`), the two lowest with a pitch glide (phase and `sin` per sample), summed; each mode stops when it has died away | yes, per mode (modes are independent: parallel across them) |
| 2 | `pluck._loop` | songbird/synth/pluck.py:73 | 0.40 s (2.8%), 2,440 calls | 25.7 s (13.3%) | one plane of a plucked string (Karplus-Strong): `y[n] = x[n] + g[n] * sum_k taps[k] y[n - whole - k]`, a fractional delay and loss filter in the loop, the loop gain gliding at the release | yes (feedback one period back) |
| 3 | `fx._four` | songbird/synth/fx.py:84 | 0.34 s (2.4%), 8 calls | 27.3 s (14.1%) | four biquads in cascade (transposed direct form II) over every channel: every equalizer of the mix | yes (IIR); channels independent |
| 4 | `pluck._bank` | songbird/synth/pluck.py:222 | 0.33 s (2.2%), 3 calls | 40.2 s (20.8%) | the sympathetic open strings (lute, guitar, harp): four to seven delay-line loops (the open strings on the tonic and fifth) driven by the bridge force, each with a short FIR in its loop, summed | yes (strings independent) |
| 5 | `master._weighted_hop_power` | songbird/synth/master.py:66 | 0.27 s (1.9%), 6 calls | 16.2 s (8.4%) | loudness (BS.1770): the K-weighting's two biquads and the power of each 100 ms hop | yes (IIR) |
| 6 | `fx._one` | songbird/synth/fx.py:125 | 0.27 s (1.9%), 8 calls | 6.8 s (3.5%) | one biquad (an equalizer's leftover section; the de-esser's and width's filters) | yes (IIR) |
| 7 | `fx._two` | songbird/synth/fx.py:109 | 0.22 s (1.5%), 4 calls | 9.7 s (5.0%) | two biquads in cascade | yes (IIR) |
| 8 | `pipe.run` | songbird/synth/pipe.py:33 | 0.15 s (1.1%), 1 call | 2.6 s (1.3%) | the whistle: a jet (`sin`, `tanh`) driving a bore (a delay line read with interpolation, a one-pole loss), turbulence through a one-pole | yes |
| 9 | `fx._apply` | songbird/synth/fx.py:436 | 0.15 s (1.0%), 11 calls | 8.2 s (4.3%) | a compressor's or de-esser's gain (given every 16 samples, linear between) applied to the signal or to one band of it | no (elementwise) |
| 10 | `fx._detect_every` | songbird/synth/fx.py:405 | 0.15 s (1.0%), 11 calls | 6.8 s (3.5%) | a dynamics detector: mean power over the channels through a one-pole average, every 16th value kept | yes (one-pole) |
| 11 | `bowed.run` | songbird/synth/bowed.py:49 | 0.13 s (0.9%), 1 call | 9.4 s (4.8%) | the fiddle: a bowed-string waveguide (two delay lines read with cubic interpolation, a one-pole bridge loss, the bow's friction table) | yes |
| 12 | `master._recover` | songbird/synth/master.py:281 | 0.11 s (0.8%), 4 calls | 1.0 s (0.5%) | the limiter's gain: down at once, back up exponentially | yes |
| 13 | `fx._saturate` | songbird/synth/fx.py:636 | 0.09 s (0.6%), 4 calls | 5.3 s (2.7%) | soft saturation (a rational tanh, `fx._soft`) and a DC blocker after it | yes (the DC blocker's one-pole) |
| 14 | `fx._block_power` | songbird/synth/fx.py:373 | 0.09 s (0.6%), 9 calls | 4.0 s (2.1%) | mean power of each 50 ms block (a stem's loud level) | no (a sum per block, in order) |
| 15 | `fx._block_peaks` | songbird/synth/fx.py:599 | 0.08 s (0.6%), 7 calls | 2.1 s (1.1%) | the peak of each 20 ms block | no (a maximum per block) |
| 16 | `fx._products` | songbird/synth/fx.py:216 | 0.05 s (0.3%), 9 calls | 6.0 s (3.1%) | L·L, R·R and L·R over a stem (is it one mono sound panned?) | no, but three running sums in sample order |
| 17 | `fx._follow` | songbird/synth/fx.py:567 | 0.05 s (0.3%), 1 call | 1.2 s (0.6%) | how much the voice is sounding (the band makes way): power through a one-pole, then an attack/release follower | yes |
| 18 | `reed._read` | songbird/synth/reed.py:84 | 0.03 s (0.2%), 18 calls | small | the drone's reeds: a wavetable read by a phase accumulator | yes (phase) |

Kernels added on 2026-09-29 to save memory (`fx._sliding_min`, `fx._running_mean`, `fx._hold`,
`instruments._placed`, `master._windows`, `master._abs_max`, `master._over`, `master._mean_ahead`; 0.3 s
together compiled) have numpy or scipy equivalents that give the same values; with the compiler off
(`fx.JIT` false) those are used instead, so they cost nothing interpreted and need no port.

Other styles and instruments bring their own kernels (91 in all under songbird/synth/, in 27 modules). None is
compiled with `fastmath` since 2026-09-29: the seven in songbird/synth/analog.py (the analog synths of the synth
styles) were, so their output depended on how the compiler reordered and fused their arithmetic, and they
leaked fastmath into `osc._blep4`'s cached code (docs/notes/BROWSER-RENDER.md); they are ordinary kernels now.

## What it means for a port

- The recursive kernels are the port's real work: a filter, a delay line or a phase must run sample after
  sample. In WebAssembly or JavaScript (typed arrays) such loops run within a small factor of native; as
  interpreted Python they are 50 to 100 times slower. The biquads (`fx._four`, `_two`, `_one`,
  `master._weighted_hop_power`) and the strings (`pluck._bank`, `_loop`) are half the interpreted time.
- Several can be spread across an axis that isn't time: channels (the biquads), strings (`pluck._bank`),
  modes (`drum._ring`), notes (`pluck._loop` runs once per note plane).
- The non-recursive ones (`fx._apply`, `_block_power`, `_block_peaks`, `_products`) are easy, but a
  vectorised sum adds in a different order than the loop does, so a port that must match the native render's
  bytes has to keep the loop's order.
- Matching the native render bit for bit also needs the same operations in the same order, no fused
  multiply-adds (WebAssembly and JavaScript never fuse on their own), and the same `sin`, `cos`, `exp`,
  `tanh` and `pow`: JavaScript's `Math` functions are not the macOS C library's, so the kernels that call them
  (`drum._ring`, `pipe.run`, `bowed.run`'s friction table, the reeds) will differ in their last bits.
