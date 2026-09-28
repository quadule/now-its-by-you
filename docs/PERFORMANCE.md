# Render performance (2026-09-27)

How long a render takes, where the time goes, and what was done about it. The rule for every change
here: **the output is byte-identical.** Each change was checked against the seed render's PCM hash
(`tests/golden/h-seed.sha256`, `b600b712e77a…`) and, where it touched one function, that function's
own output bit for bit against the code before it. A speed-up that changes even one sample's last bit
was not taken; those are listed at the end as options.

## How it was measured

- Machine: Apple M1 Max (10 cores), macOS, CPython 3.12, numpy 2.5.3, numba as locked in `uv.lock`.
- The full render: H's seed rendition as `tests/test_styles.py` makes it (`cli.render_one` on
  `songs/h-now-its-by-you.json` with its seed phrasing: 151.4 s of audio), wall time in one process,
  numba's cache warm. `songbird render songs/h-now-its-by-you.json` takes the same time to within a
  second (it adds the process start and imports, about 1.4 s).
- The dry voice: `voice.sing` on that score's voice part (the learned throat: 147 s of singing).
- Profiles: `cProfile`, sorted by inclusive time. numba functions are C calls to cProfile, so their
  time shows up in whoever calls them.

## Where the time went (before)

Full render: **20.3 s** wall. By stage (the render's own progress marks):

| stage | s |
|---|---|
| lute, guitar, harp, bass (plucked, with sympathetic strings and bodies) | 1.20 + 1.03 + 0.97 + 0.49 |
| fiddle, whistle, drum, drone | 0.80 + 0.48 + 1.03 + 0.54 |
| voice (the learned throat) | 7.81 |
| mix (channel strips, buses, room, glue) | 4.36 |
| master (limiter, true peak, loudness, PCM) | 1.52 |

Top functions by inclusive time (cProfile, full render, 20.8 s under the profiler):

| function | inclusive s | own s | calls | what it is |
|---|---|---|---|---|
| `synth.render_stems` | 14.39 | | 1 | every part, dry |
| `throat.sing` | 8.05 | | 1 | the learned voice |
| `synth.instruments.render_band` | 6.32 | | 1 | the eight instruments |
| `throat.synthesize` | 6.01 | 2.54 | 1 | the vocoder: 60,708 pulses, 42,473 voiced |
| `mixing.mix` | 3.40 | 0.58 | 1 | |
| `numpy.fft` (all calls) | 2.45 | 2.45 | 2,735 | mostly the vocoder's |
| `throat.min_phase` | 2.00 | 0.63 | 60 | two per 2,048 pulses |
| `pluck.pluck` | 1.99 | | 1,180 | one per plucked note |
| `scipy.signal.oaconvolve` | 1.62 | | 17 | bodies and the room |
| `body.resonate` | 1.44 | | 6 | |
| `fx._biquads` | 1.15 | 1.08 | 26 | every equalizer (numba) |
| `scipy.signal.butter` | 1.12 | | 3,283 | filter design, the same few designs again and again |
| `drum.play` | 1.04 | | 1 | 215 strokes |
| `master.limit` | 1.00 | | 5 | |
| `throat.predict` | 0.84 | 0.19 | 1 | the network (`_gelu` 0.50 of it) |
| `master.master` | 0.84 | | 1 | |
| `master.true_peak_envelope` | 0.80 | | 7 | |
| `pluck._plane` | 0.71 | | 2,440 | |
| imports | 1.4 | | | scipy.signal alone 0.74 |

Inside `throat.synthesize` (5.9 s, timed block by block):

| block | s |
|---|---|
| minimum phase of the periodic part | 1.21 |
| minimum phase of the aperiodic part | 1.22 |
| `exp(1j * turn)` (each pulse's delay, spread and scatter) | 0.69 |
| inverse FFT of the periodic part | 0.58 |
| noise drawn and shaped | 0.46 + 0.38 |
| responses assembled | 0.44 |
| envelope and aperiodicity to FFT bins, source change, power | 0.20 + 0.20 + 0.13 |
| scatter, turn | 0.21 + 0.05 |
| overlap-add | 0.06 |

A complex `exp` of a 2,048 × 513 block takes 15 ms against 6 ms for its inverse FFT: most of
`min_phase` is the exponential, not the FFTs.

Dry voice: **7.9 s** (`throat.synthesize` 5.9, `predict` 0.86, the pronouncing dictionary's first load
0.5, `articulate` 0.29).

## What was done

| change | before | after | hash unchanged |
|---|---|---|---|
| Vocoder: an unvoiced pulse's periodic part is no longer made (it was multiplied by 0); the pulses' responses made 512 at a time on up to 8 threads, the random values still drawn 2,048 pulses at a time in the old order, laid into the output in pulse order | voice 7.89 s, synthesize 5.9 s, full 20.3 s | voice 2.80 s (6.16 on one thread), synthesize 0.86 s, full 13.4 s | yes (`b600b712e77a…`; synthesize's output bit for bit on H and 13 edge cases) |
| Filter designs remembered: `songbird/synth/iir.py`'s `butter` is scipy's, cached by its arguments (a fresh copy each call), imported by every synth module in scipy's place; 3,283 designs in H came down to a few dozen | full 13.4 s (lute 1.20, guitar 1.03, harp 0.97, drone 0.54) | full 12.8 s (lute 0.62, guitar 0.82, harp 0.85, drone 0.48) | yes; `b-refrain` golden too |
| Every part at once: the band's parts, the voice and the lineage voices made on threads (`threads.made`; the singers started first), put in the stems dict in the old order; every numba kernel compiled `nogil=True` so its loop runs beside the others | full 12.8 s (stems 7.8 s) | full 8.9 s (stems about 4 s; `SONGBIRD_THREADS=1` 16.1 s) | yes, at 1, 2, 3, 4, 6 and 8 threads; `b-refrain` too |
| The mix's lead bus, choir bus and every instrument's channel strip treated at once (`threads.in_order`: at most twice the threads' worth of results held), then summed into the band, its send and what steps back under the voice one at a time in the old order | full 8.9 s (mix 3.45 s) | full 7.8 s (mix 2.55 s) | yes; and 7 more renditions (a lineage choir with a parent, a bluegrass lineup, a worn mix, four other seeds) against the original tree |
| The true-peak envelope (the limiter's, the peak stages', the master's) worked out 65,536 samples at a time on threads, each stretch exactly as before | full 7.8 s (master 1.51 s) | full 7.6 s (master 1.35 s; the envelope 0.42 s to 0.15 s on 3 M samples) | yes; the envelope and the limiter bit for bit against the original on a test signal |

### Notes on the changes

- **Threads.** `songbird/synth/threads.py`: `workers()` is how many, `SONGBIRD_THREADS` if set, else the
  machine's cores, at most 6 (on this 10-core Mac 4 to 6 render fastest: 8.9 and 8.8 s at 4 and 6;
  9.4 s at 8, where the parts only contend). `SONGBIRD_THREADS=1` renders on one thread, with the same
  bytes. numpy's FFTs and large elementwise operations, and numba's loops once compiled `nogil`, let go
  of the interpreter lock, so the threads run side by side; the plucked parts' per-note Python still
  takes turns.
- **Why it stays the same.** Every part draws on its own random streams (seeded by the song's seed and
  the part), so which thread makes it, and when, can't change it; the stems are gathered into the dict
  in the order they always were, and everything after (the mix) sees exactly what it saw.
- **Memory.** Peak resident memory of the seed render: 4.7 GB before any of this, 3.7 to 4.5 GB now depending on the
  threads (most of it is the mix's full-length stereo buffers, 107 MB each). `SONGBIRD_THREADS=2` keeps
  it at 3.8 GB and renders in 10.1 s.
- **Why each pulse comes out the same.** Every operation on a pulse's row is elementwise or along that
  row alone, so which block or thread makes it doesn't matter, with one catch found on the way: a
  row's sum depends on how the array is laid out in memory. numpy lays the FFT's output out column by
  column when its input came from `to_bins` (a fancy index along the second axis), and a sum along a
  row of that adds the values one after another, while a sum along a contiguous row adds them
  pairwise; the last bits differ. So the voiced-only periodic part is put into an array laid out as the
  FFT would have laid it out, and a block of one pulse is never made from a chunk of more (a single
  row is summed pairwise either way).
