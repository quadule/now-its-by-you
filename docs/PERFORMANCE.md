# Render performance (2026-09-27)

How long a render takes, where the time goes, and what was done about it. The rule for every change
here: **the output is byte-identical.** Each change was checked against the seed render's PCM hash
(`tests/golden/h-seed.sha256`, `b600b712e77a…`) and, where it touched one function, that function's
own output bit for bit against the code before it. A speed-up that changes even one sample's last bit
was not taken; those are listed at the end as options.

## In short

| | before | after |
|---|---|---|
| H's seed render (`cli.render_one`, 151 s of audio) | 18.6 to 20.3 s | 7.0 s |
| the same on one thread (`SONGBIRD_THREADS=1`) | 18.6 to 20.3 s | 16.0 s |
| `songbird render songs/h-now-its-by-you.json` (process, imports and all) | 19.4 s | 8.2 s |
| the dry voice (`voice.sing`, the learned throat, 147 s sung) | 7.9 s | 2.3 s (6.1 s on one thread) |
| peak memory | 4.7 GB | 4.4 GB |

The seed's PCM id is `b600b712e77a…` before and after every change, at any thread count; so is
`b-refrain`'s golden, and seven more renditions (a lineage choir with a parent, a bluegrass lineup,
a worn mix, four other seeds) render to the ids the original tree gives them, their records and FLAC
files byte for byte. The whole test suite passes (1,362 tests, `--ignore=tests/test_site.py`).

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
| The network's GELU worked out in place (no temporaries), 4,096 frames at a time on threads, each value by the same operations in the same order | `_gelu` 75 ms a layer, `predict` 0.86 s | `_gelu` 23 ms a layer, `predict` 0.52 s; dry voice 2.5 to 2.7 s (6.0 s on one thread) | yes; `_gelu` bit for bit against the old expression, infinities and NaN included |
| A long stereo signal's equalizer (every `fx.equalize`, the de-esser's split, the K-weighting of the loudness meter) filters its two channels at once, each a contiguous copy on its own thread | full 7.6 s (mix 2.49 s, master 1.34 s; a 5-section equalizer on 6.7 M stereo samples 0.135 s) | full 7.2 to 7.5 s (mix 2.40 s, master 1.26 s; that equalizer 0.074 s) | yes; the 7 renditions against the original tree too |
| `cli.render_one` writes the FLAC while it measures the rendition's loudness, loudness range and true peak for the record (threads.in_order), from one conversion of the PCM instead of three | full 7.2 to 7.5 s (master 1.26 s) | full 7.0 to 7.1 s (master 1.05 s) | yes; the whole record and the FLAC file byte for byte against the original on three renditions |
| The true-peak envelope reads each point's 65-sample window as a row of a sliding view over the signal reversed, instead of building a 65-column index array per stretch and gathering through it (the same matrix, value for value, into the same product) | envelope 0.15 s threaded, 0.42 s on one thread (3 M samples) | 0.12 s threaded, 0.26 s on one thread; full about 7.0 s | yes; envelope and limiter bit for bit against the original |

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
  it at 3.8 GB and renders in 10.1 s. (Brought to 1.1 to 1.3 GB on 2026-09-29: "Memory", below.)
- **Why each pulse comes out the same.** Every operation on a pulse's row is elementwise or along that
  row alone, so which block or thread makes it doesn't matter, with one catch found on the way: a
  row's sum depends on how the array is laid out in memory. numpy lays the FFT's output out column by
  column when its input came from `to_bins` (a fancy index along the second axis), and a sum along a
  row of that adds the values one after another, while a sum along a contiguous row adds them
  pairwise; the last bits differ. So the voiced-only periodic part is put into an array laid out as the
  FFT would have laid it out, and a block of one pulse is never made from a chunk of more (a single
  row is summed pairwise either way).

## Where the time goes now

With threads, the render is three stages one after another: the stems (the voice is the longest part,
and gates the stage), the mix, the master. On H (the stage marks of the render's progress):

| stage | before | now |
|---|---|---|
| stems: every part at once, the voice last to finish | 13.7 to 14.1 s | about 3.5 s |
| mix | 3.6 to 4.4 s | about 2.4 s |
| master, the record's measures, the FLAC | 1.5 s | about 1.0 s |

- **The voice beside the band.** Alone, the voice takes 2.3 to 2.6 s; beside the band's parts, about
  3.5 s. Its pitch track is the clearest case: 0.12 s alone, about 1.0 s beside the band, of which
  0.29 s is its own work and the rest waiting for the interpreter lock. It makes a few thousand
  small numpy operations over the whole song's 27,500 blocks, and each lets go of the lock and has to
  win it back from the band's per-note Python. A pitch track that worked each note over its own
  stretch of blocks would do a tenth of the work in calls under numpy's threshold for letting go of
  the lock; it can be made exact (every block outside a note's stretch provably gets what it got), but
  it is a careful rewrite of `voice.pitch_track`, left for now.
- **The mix's buses.** After the channel strips, the band bus (equalizer, compressor, what steps back,
  the ride, the carve), the room (0.26 s of convolution, already on 4 fixed FFT threads), the return's
  peak stage, the glue and the tone run one after another, each on the whole song: about 1.2 s.
- **One thread.** `SONGBIRD_THREADS=1`: about 16 s (18.6 to 20.3 s before). What's left on one core is
  mostly the vocoder's complex exponentials and FFTs (4.3 s), the band's own loops and bodies (5 s)
  and the mix (3.4 s).

## Options declined: they would change the bytes

Each of these would save time and sound the same to anyone, but moves some samples' last bits, so
the seed's id would change. Taking any of them is a decision for the artist (and a new golden).

- **One complex exponential per voiced pulse** instead of two: `exp(log spectrum + i·turn)` in place of
  `exp(log spectrum) · exp(i·turn)`. About 0.7 s of the vocoder's 4.3 s on one core. Rounding differs.
- **Skip the vocoder where the voice is hushed.** 18,235 of H's 60,708 pulses are unvoiced, many in
  rests that `throat.hush` multiplies by zero. Not made at all, they would save a quarter of the
  vocoder, but the 60 Hz high-pass after the resampler carries a little of every sample into what
  follows, so the sung stretches' last bits would move.
- **FFT workers for the bodies' convolutions** (`scipy.fft.set_workers` around `body.resonate`, as the
  room already does with a fixed 4): tried, and the bytes change (scipy splits the work differently
  with more workers), so the bodies stay on one worker each.
- **The frame drum's modes all at once.** `drum.hit` works its 196 modes one at a time in Python
  (0.3 s of H's drum). Vectorized, `(2 f contact) ** 2` goes through numpy's array square instead of
  the C library's `pow` that a numpy scalar uses, and the two differ in the last bit for about 1 value
  in 1,500 (53 of 600 test strokes changed). Keeping `pow` per mode would keep most of the loop.
- **float32** anywhere (the network, the vocoder, the mix): faster and half the memory, but different
  bytes everywhere.

## Further ideas that keep the bytes

- `voice.pitch_track` per note over its own stretch (above): the voice's critical path under the band,
  perhaps 0.7 s.
- A body's two channels convolve the same bridge force: sharing its forward FFTs would halve the
  bodies' convolutions (1.4 s on one core), but only by reproducing `scipy.signal.oaconvolve`'s own
  block choice, which could drift from scipy's in a later version.
- The pronouncing dictionary's first load (0.5 s, `cmudict.dict()`) happens once per process; the
  studio pays it once, the command line every time.
- Imports: 1.4 s before `songbird render` does anything (scipy.signal alone 0.74 s).


# Memory (2026-09-29)

The studio is going on the web. The server is an 8 GB machine beside a mail server, a render's container
capped near 2.5 GB and shared with a speech model, so a whole song rendered on two threads has to peak at
1.5 GB or less; a browser tab gets about 2 GB. H's seed peaked at 3.2 GB (4.2 to 4.9 GB as macOS counts
it). The rule stayed: **every change is byte-identical**, at any thread count.

## In short

H's seed rendition (`cli.render_one`, 151 s of audio), M1 Max, before (10dc1e0) and after, run alternately
(the machine was shared with other work, so times vary by half a second either way).

| | before | after |
|---|---|---|
| peak, one thread (freed memory returned: `MallocLargeCache=0`, as Linux returns large blocks) | 3.18 GB | **1.13 GB** |
| peak, two threads (the same) | 3.21 GB | **1.33 GB** |
| peak, six threads (the same) | 3.23 GB | 1.92 GB |
| heap high-water (memray, every allocation; one thread / two) | 3.06 GB / – | 1.01 GB / 1.28 GB |
| resident peak as macOS's own allocator leaves it (1 / 2 / 6 threads) | 4.9 / 4.2 / 4.6 GB | 2.0 / 2.2 / 2.7 GB |
| `songbird render songs/h-now-its-by-you.json` (the whole process, `MallocLargeCache=0`, 1 / 2 threads) | 3.18 / 3.21 GB | 1.13 / 1.33 GB |
| time, one thread (macOS allocator / `MallocLargeCache=0`) | 16.5 / 22.5 s | 15.7 / 19.7 s |
| time, two threads | 8.8 to 9.5 / 12.3 to 13.1 s | 10.4 to 10.7 / 12.6 to 13.2 s |
| time, six threads (the default here) | 7.6 / 10.7 s | 6.8 to 7.0 / 8.7 to 9.0 s |

On two threads the render is a second slower with macOS's allocator: the voice is sung before the band's
sums begin, and the second thread waits for it (see "Order", below). Letting the band's first parts be
made beside the voice, as on three threads or more, gives 9.1 s at 1.40 GB.

## How it was measured

- `tools/render_memory.py`: the PCM id, the wall time, the process's resident high-water mark and each
  stage's (the render's progress marks). macOS's allocator keeps freed large blocks for reuse (a freed
  107 MB array stays resident, and differently sized ones fragment), so its resident peak runs far above
  what is ever in use at once; `MallocLargeCache=0` makes it return them at once, as glibc does for anything
  over 32 MB. That is the figure a Linux server's limit sees (it costs macOS about a fifth in time: every
  large array is fresh pages).
- memray (`uv run --with memray memray run`, then `memray summary`) and tracemalloc snapshots taken where a
  stage peaks, for where the memory is.

## Where it went (before)

One thread, `MallocLargeCache=0`: 0.23 GB after the imports; every part's stem kept until the mix (nine
stereo stems, 107 MB each, about 1 GB), each part making several more copies of the song while it was made
(a plucked part 420 MB: its open strings kept their whole history, 8 strings x 6.7 M samples; its body's
`oaconvolve` about 250 MB of blocks and spectra; the stereo placement, level and fade each a new copy); the
mix 3.2 GB at its peak (the stems, the buses, and each treatment's result a new copy of the song:
equalizers, compressors, detectors keeping every sample, the room's padded blocks); the master 1.1 GB (a
filtered copy for every loudness measurement, a padded copy for every true-peak envelope, the clip's and the
limiter's copies, three copies for the dither).

## What was done

| change | effect | how it stays the same |
|---|---|---|
| The stems are made as the mix comes to them (`mixing.mix_made`): each part made, treated through its channel strip and summed into the band, its send and what steps back, then let go; `synth.render` uses it, and `mix()` of given stems is the same function | peak 3.2 to 2.1 GB | every sum is made in the same order (the parts' names); the singers' buses are made before any part that steps back under the voice needs them |
| Long signals let go once used, and treated in place when nothing else holds them: `fx.equalize`, `compress`, `apply_gain`, `dynamic_dip`, `saturate`, `soften`, `deess`, `width`, `master.limit` and `clip` take `inplace`; the compressors' detectors keep only the values they read (`fx._detect_every`) | 2.1 to 1.4 GB | each kernel reads a sample before it writes it; the same ufuncs on the same values |
| Parts placed straight into their stereo stem (`instruments._placed`), level, gain and fade in place; a treated mono part panned back into its stem | a part 420 to 280 MB | the same expressions sample by sample (numba adds no fused multiply-adds without fastmath: checked) |
| The open strings keep a ring of their last few hundred samples (`pluck._bank`) | 420 MB less in a plucked part | the loop only ever read that far back |
| `oaconvolve` a few blocks at a time (`synth/oa.py`): the bodies, and the room as on its four FFT threads | a body 250 MB less, the room about 200 MB less | the same blocks, FFTs, products and overlap-adds. The FFT library transforms rows a SIMD width at a time from a call's first row, and a row alone differently, so each call starts on a multiple of 8 blocks; scipy's workers divide the rows as `np.array_split` does, each worker's stretch from its own first row, so the room's four stretches are made that way (on the render's threads) |
| `uniform_filter1d` and `minimum_filter1d` over a whole song as scipy computes them, without its two copies of the line (`fx.running_mean`, `fx.sliding_min`), in place | the voice's articulation 360 to 200 MB; the ride; the limiter | scipy's uniform filter is a running sum divided at each sample (found by trying the candidates against it bit for bit); a minimum is the same value however found (its mode, "nearest" or "reflect", honoured) |
| The voice's articulation, hush, breaths and scaling in place; the bowed and blown parts' tracks held through rests where they lie (`fx.hold`) | the voice 450 to about 300 MB | the same products and sums; a held value is a copy |
| The master: loudness K-weighted and summed sample by sample (`master._weighted_hop_power`, no filtered copy); the true-peak windows gathered from the signal (no padded copy); the limiter's need, hold, recovery and look-ahead mean in place (`_mean_ahead`: `np.cumsum`'s running sum); the clip and the dither in place (the second draw and the scaled signal added a stretch at a time); `render_one` lets go of the mix once mastered | the master 1.1 to 0.65 GB, and 1.0 to 0.3 s | the same filter and sums in the same order; the same matrix into the same product; `np.cumsum` adds in order (checked); the same draws in the same order |
| Order: on one or two threads the voice first (the least memory); on three or more, the band's parts before the first that steps back under the voice are made and summed while the voice is sung | six threads 7.6 to 6.9 s | the band's sums are in the same order either way |
| The frame drum's 196 modes at once, the powers through `np.power` with an array of exponents | `drum.hit` a quarter faster | an array `** 2` squares, which differs from the C library's `pow` (why the loop was kept, above); `np.power(x, array of 2.0)` calls `pow`, as a scalar `**` does (checked) |
| With `NUMBA_DISABLE_JIT=1` the new loops give way to the numpy and scipy operations they replace (`fx.JIT`) | no interpreted cost from them (docs/PORTABILITY.md) | the same values |

### How it was verified

- The goldens: H's seed (`9b0766353b73…`), `b-refrain` (`2bdb6de271be…`) and `h-words`, after every change,
  at `SONGBIRD_THREADS=1` and the default.
- Eleven more renditions through the command line against the original tree, at 1 and 6 threads, each
  FLAC decoded back to its id: a choir with a worn, wide, tilted mix; stringband, synthfolk, country, chamber
  (with `--stems`: the stems' samples compared too), blues, lofi, gospel with a three-voice choir, a machine
  with a date, K, and G with wear and space.
- Each piece against what it replaced, bit for bit (`tests/test_lean_render.py`: the blockwise convolution
  against `oaconvolve` on one thread and on the room's four, the running filters against scipy's, the ring
  against the whole history, placement and width against their old expressions, the in-place treatments
  against the copies, `mix_made` against `mix` with a lift, a choir and taps at 1 and 3 threads, the caller's
  stems left untouched); the master's functions against the original's on noise, tones and silence, with
  the compiler and without.
- The suite: 1,388 passed, 11 skipped, 1 failed
  (`test_composition.py::test_lines_an_older_record_kept_by_place_are_sung_there_and_handed_down_by_verse`,
  which fails the same way on the tree before these changes).

## Where it is now

One thread, `MallocLargeCache=0`: the voice 0.71 GB, the band's parts 0.8 to 1.13 GB, the mix 0.94 GB, the
master 0.63 GB. The band's stage holds the process itself (0.26 GB: Python, numpy, scipy, numba's kernels,
the pronouncing dictionary, the throat's network), the band's three sums (the band, its send to the room,
what steps back under the voice: 3 x 107 MB), the voice's bus (107 MB, and its activity, 53 MB) and the part
being made (100 to 400 MB: a whistle's five control tracks and its noise, a fiddle's). On two threads two
parts are made at once.

For the server: glibc returns blocks over 32 MB to the system at once, but smaller ones (the FFT blocks, the
vocoder's) stay in its arenas, one per thread. For a render worker `MALLOC_ARENA_MAX=2` and a fixed
`MALLOC_MMAP_THRESHOLD_=1048576` should keep the resident size near the heap figure; not measured here (no
Linux at hand): `tools/render_memory.py` measures it. A browser (one thread; WebAssembly memory only grows)
needs the one-thread heap high-water, about 1.0 GB, plus its allocator's fragmentation.

## Further ideas that keep the bytes

- The voice's bus kept as its mono sound and two gains until the room and the sum (53 MB through the band's
  stage).
- A part's control tracks made a note at a time inside its loop (the whistle's and the fiddle's five tracks,
  265 MB while they play).
- A body's two channels share the bridge force's forward FFTs: `synth/oa.py` makes oaconvolve's own blocks,
  so one stretch's spectra can serve both ears (the bodies' convolutions nearly halved).
- The singers and the band's first parts side by side on two threads too (9.1 s instead of 10.5 s, at
  1.40 GB instead of 1.33 GB): a choice for the server's budget (`steps_back` in `mixing.mix_made`).

## Options declined: they would change the bytes

- **float32** for the stems, the sums and the buses (the network and the vocoder too): every buffer halved,
  a peak near 0.6 GB, and faster where memory bandwidth bounds it; every sample's last bits move.
- **The mix in blocks** (a stretch of the song at a time through every strip, bus and the room): memory
  independent of the song's length (a few hundred MB), but the loud levels, percentiles and loudness each
  strip measures over its whole stem would need a first pass, and the room's convolution other blocks.
- **fastmath** on the biquads and the strings' loops (a quarter to a third off their time, 1.5 s of kernel
  time on one thread): the compiler may reorder and fuse their arithmetic.
- **The vocoder's pulse delay as `cos` and `sin`** in place of `exp(1j * turn)`: equal on this Mac (checked)
  and 30% faster for that step, but whether numpy's complex exponential and its real `cos` and `sin` agree
  to the bit depends on the platform's builds, so it could split a server's renders from a Mac's.
