# Render performance (2026-09-27)

*An engineering note, September 27 to October 2, 2026: how long a render takes, and what made it quicker without changing a sample.*

How long a render takes, where the time goes, and what was done about it. The rule for every change
here: **the output is byte-identical.** Each change was checked against the seed render's PCM hash
(`tests/golden/h-seed.sha256`, now h-seed.darwin-arm64.sha256, `b600b712e77a…`) and, where it touched one function, that function's
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
| With `NUMBA_DISABLE_JIT=1` the new loops give way to the numpy and scipy operations they replace (`fx.JIT`) | no interpreted cost from them (docs/notes/PORTABILITY.md) | the same values |

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


# The heaviest parts (2026-09-30)

The public studio renders in a 2.5 GB container with a 2100 MB budget for a whole song (docs/history/web-studio-server-plan.md, "Before
launch"), and measured band by band the drum kit held about 9 MB for every second of song on its own: every style
with a kit was refused on the server past about 1.7 minutes, and country's and gospel's own defaults were past the
container. This made the heaviest parts lean by the rule above: **every change byte-identical**, at any thread count.

## In short

Each style's default H (`tools/render_memory.py`'s measure, `MallocLargeCache=0`), the tree before (02384c8) and after,
peak resident memory:

| | 2 threads, before → after | 1 thread, before → after |
|---|---|---|
| country (152 s, kit) | 2.36 → 1.43 GB | 2.09 → 1.29 GB |
| gospel (225 s, kit) | 2.90 → 1.90 GB | 2.77 → 1.41 GB |
| indie (128 s, kit) | 2.16 → 1.22 GB | 2.02 → 0.99 GB |
| chamber (189 s) | 2.16 → 1.30 GB | 1.91 → 1.26 GB |
| chamber, 4 verses, slowest, every part (413 s) | 4.27 → 2.53 GB | |
| lo-fi (186 s) | 1.98 → 1.45 GB | 1.97 → 1.36 GB |
| ambient (214 s) | 2.07 → 1.56 GB | 2.05 → 1.51 GB |
| lullaby (298 s) | 2.01 → 1.69 GB | 2.03 → 1.57 GB |
| blues (165 s) | 1.81 → 1.34 GB | 1.69 → 1.11 GB |
| shanty (151 s) | 1.66 → 1.13 GB | 1.56 → 1.10 GB |
| H's seed, the ballad, songwriter, string band, synth folk | unchanged (1.10 to 1.35 GB) | unchanged or a little less |
| gospel with a three-voice choir (`--choir 3 --seed 7`, the whole process) | 3.93 → 2.46 GB | 3.15 → 1.92 GB |
| country with `--stems` (the whole process) | 3.69 → 2.05 GB | 2.85 → 1.65 GB |

Rendering takes the same time to within the machine's noise (a second or two either way, the machine shared). What
that buys the server, in minutes of song a whole render may be (docs/WEB-STUDIO.md has the table): the kit's bands
1.7 → 3.8 to 4.0 minutes, chamber 2.8 → 4.9, lo-fi and blues 3.1 → 4.6 and 4.5, shanty 3.2 → 5.1, ambient 3.4 → 4.8,
the lullaby 4.8 → 6.1.

Each part made alone (its `band_parts` job in its style's H, one thread; the process's resident peak above where it
stood before the part began, which counts the part's stem and its kernels' first loading):

| part | before | after |
|---|---|---|
| gospel's kit (224 s) | 2.49 GB | 0.67 GB |
| country's kit (150 s) | 1.45 GB | 0.44 GB |
| indie's kit (126 s) | 1.46 GB | 0.39 GB |
| chamber's cello (187 s) | 1.43 GB | 0.60 GB |
| chamber's strings (187 s) | 1.17 GB | 0.55 GB |
| ambient's vibes (212 s) | 1.25 GB | 0.71 GB |
| lo-fi's vibes (184 s) | 1.06 GB | 0.62 GB |
| lullaby's synth pad (297 s) | 0.98 GB | 0.57 GB |
| shanty's concertina (150 s) | 0.91 GB | 0.32 GB |
| lullaby's voice (the learned throat, 297 s) | 0.83 GB | 0.55 GB |
| country's voice (150 s) | 0.45 GB | 0.34 GB |
| gospel's piano (224 s) | 0.71 GB | 0.47 GB |
| chamber's piano (187 s) | 0.61 GB | 0.42 GB |
| lullaby's celesta (297 s) | 0.71 GB | 0.61 GB |
| blues's harmonica (164 s) | 0.35 GB | 0.19 GB |
| country's steel (150 s) | 0.61 GB | 0.59 GB |
| lo-fi's epiano, gospel's organ | 0.55, 0.51 GB | the same (not touched) |

## How it was measured

- The styles: `tools/render_memory.py`'s measure through `edits.resolve` with `{"style.name": ...}` (and the drawn-out
  versions with more verses, every optional part and the slowest tempo), each in a fresh process, on the tree before
  (a worktree at 02384c8) and after.
- A part alone: its job from `instruments.band_parts` (or `synth.stem_jobs` for the voice) in a fresh process, a
  sampler thread reading the resident size every 2 ms; where the memory went, memray's allocations at the high-water
  mark (`memray run`, then `FileReader.get_high_watermark_allocation_records`).

## Where it went, and what was done

| part | where the memory was | what was done | how it stays the same |
|---|---|---|---|
| A bank of modes (`struck.ring`: the kit's drums and cymbals, the cajon, shaker and hands) | every per-sample track padded whole for each rate and stacked; each group's sum doubled whole beside its copy, added to the next group's bank, then added to zeros for the result | tracks copied straight into their rate's length; each doubling a channel at a time and a stretch at a time (`_up2_into`: each stretch with the taps' reach either side, zeros past the ends, doubled by `_up2` itself); a group's bank made first and the sum below doubled into it where it lies; the sum returned as it lies (+ 0.0); its tracks let go before the last doublings; its channels given apart (`apart=`), or rung a channel at a time with the whole bank's floor (`floor=`) | the same products summed in the same order: a doubled stretch's every sample is the same 24 taps over the same values; `acc + y` added where `y` lies is `y + acc`; + 0.0 is what adding to zeros did (-0.0 to 0.0); a channel hears only its own modes (the others add 0.0 to a sum begun from 0.0) and drops each mode where the whole bank did |
| A cymbal (`cymbals.play`) | three channels, a second copy of the microphones, the motion, the feed and its bloom's temporaries, the wash's stereo filtered whole twice, the ticks as a whole stereo track | the microphones and the motion kept apart (`cymbals.microphones`), each handed on and let go once used; the bloom a stretch at a time; the wash's filters a channel at a time and a stretch at a time, their state carried; the ticks laid a touching run at a time | elementwise operations are the same on any stretch; a filter's state carried across stretches (`zi`) gives the samples of the whole along axis 0 (checked); outside the ticks' runs their track is 0.0, and the sum it's added to holds no -0.0 |
| The kit (`kit.render`) | a track and a motion for each of five drums whether played or not; every sum, pan and placement a new stereo copy; the snare's head and track copies | a drum not played is None; each track scaled where it lies; the others' push on the snare's head made a stretch at a time; the head handed to the wires whole; the toms' ringing a tom at a time; the drums panned and the cymbals placed into the kit's stereo a stretch at a time; the high-pass a channel at a time | the same expressions on each sample, the sums in the same order (kick, snare, toms, hat, ride, crash); a silent drum's pan would add 0.0 |
| The cello, viola and string section (`cello._bowed`, `_hiss`, `_section`) | the vibrato, the period through three fixes, the hair and hiss (scipy's running means, the gate, the motion, the noise) each a new copy; each desk's two-microphone body through `oaconvolve` whole | each step where the last left it; the weight read only at the fixes' grid; the hair's noise, the hiss's noise (drawn and filtered) and every elementwise step a stretch at a time; a desk through `oa.convolve_columns`: `oaconvolve(x[:, None], h, axes=0)`'s own blocks and shapes, a whole number of groups at a time | normal draws made a stretch at a time are the same draws; the interpolations' spacings (1 and 32) make their slopes exact whether numpy precomputes them or not; the two-column convolution against scipy's on the lengths used (tests) |
| The mallets (`mallets._bars`: vibes, celesta, marimba, glockenspiel) | the motor's tracks and the discs' gain and delay a dozen copies; the tube through the discs as a second pair of channels; the stem transposed and high-passed whole | the tracks where each step left the last; the tube through the discs added into the bars a stretch at a time; the stem a channel at a time (the celesta's case through `oa.convolve`) | as above |
| The concertina and accordion | a whole click track for each side, the hiss's noise, `oaconvolve` | the clicks as their short bursts, laid a touching run at a time; the hiss a stretch at a time with the filter's state; `oa.convolve`; each side let go when done | as above |
| The synth pad's chorus (`analog.chorus`) | the delay tracks' temporaries, the wet pair filtered whole, the mix a new pair | the tracks a stretch at a time and let go once read; the clock filters and the mix a stretch at a time where the wet lies | as above |
| The piano's soundboard, the harmonica's hands, the electric guitar's spring and cabinet | scipy's `oaconvolve` whole, a channel at a time into new arrays | `oa.convolve` into each channel's column; the piano's high-pass a stretch at a time | `oa.convolve` makes oaconvolve's blocks exactly (2026-09-29) |
| A worn mix (`mixing.wear`: blues, lo-fi, a machine's worn copy) | `fx.warp`'s positions, gathers and Hermite terms (a dozen copies of the stereo song); every step after a new copy | `fx.warp` a stretch at a time; the song handed to `wear` and let go once read; saturation, the tape's band and the hiss where they lie | each output sample from the same four neighbours by the same expression |
| The learned voice (`throat`) | each network layer's padded copy, product, gains and GELU each a new array; the pulses' whole-song phase, floors and differences; the envelopes kept through the vocoder; a padded copy before the pan | the three windows laid side by side without the padding; the layers' bias, gains, sums and GELU where they lie (the same matrices into the same products); `pulse_times` a stretch at a time (the running phase carried and added on in order, as `np.cumsum` adds); the envelopes let go once sung; the high-pass a stretch at a time | the matrices multiplied are the same arrays in the same layout; a cumulative sum carried into the next stretch adds the same numbers in the same order |

No kernel changed; the browser's translation needed only its references to the kernels' lines regenerated
(`web/studio-wasm/tools/transpile.py`).

## How it was verified

- The goldens: H's seed, `b-refrain`, `h-words`, at `SONGBIRD_THREADS=1` and the default.
- Every style's default H at 1 and 2 threads, the ballad and chamber drawn out (217 to 413 s): each rendition's PCM id
  the same as the tree before gave it. (The kit's bands drawn out to 345 to 507 s were measured after only: before,
  they were past the container.)
- A whole-song choir (gospel, `--choir 3 --seed 7`) and a `--stems` run (country, `--seed 7`) through the command line,
  at 1 and 2 threads: the records' ids and every stem's samples the same as before (the WAV files differ only in the
  PEAK chunk's timestamp libsndfile writes).
- Each part made alone in its style's band (18 of them, the table above): its samples' hash the same as before.
- `tests/test_lean_parts.py`: a bank of modes against the one it replaced (150 random banks: channels, bends, damping,
  phases, one rate or many), doubling a stretch at a time against the whole, the interpolated tracks against `np.interp`,
  the wash and the ticks against whole tracks, the two-column blockwise convolution against scipy's, the tape read
  against the whole expression, the voice's pulses against the whole tracks'; and against hashes the tree before made:
  four kits (every piece and implement, brushed, with no snare, cymbals alone), a cello, a viola and a section, two worn
  mixes, five mallets, a concertina and an accordion, three synthesizers, a piano, a harmonica and an electric guitar,
  and the throat's network.
- The suite: 1,624 passed, 12 skipped (`--ignore=tests/test_site.py`).

## Where it is now

On two threads a render holds the program (about 0.3 GB with the throat and the dictionary), the band's sums and the
voice's bus, and two parts being made at once, each now 2 to 4 MB a second at most (the kit 3, the cello 3.2, the
steel 3.9 with its spring's long convolution): 5 to 7.5 MB for every second of song, band by band. The heaviest left:

- **The steel's spring** (and the electric guitar's): a spring's impulse response is long enough that oaconvolve's
  block is a third of the song, so its three or four blocks are one call; made a block at a time, the FFT library
  would transform a lone row differently. Byte-identical only by keeping scipy's call.
- **A bowed part's control tracks**: `bowed.run_primed` reads seven per-sample tracks (period, bow position, speed,
  grip, hair, pole, damping); two are constant from note to note. A kernel that took them as runs would hold two
  fewer (a kernel change, and the browser's translation with it).
- **The voice's network**: its matrices are the whole song's frames at once; made a few thousand frames at a time,
  the BLAS might choose another kernel for the smaller matrices and sum in another order.
- **The mix's sums**: the voice's bus kept as its mono sound and two gains (above), and the parts' stems through their
  channel strips a stretch at a time where the strip allows, would each save a stereo copy of the song.


# Whole rendering pipeline (2026-10-02)

This pass covers native and browser rendering, voice control and prediction, instruments, dynamics,
loudness measurement, PCM hashing, and the browser's worker and audio cache. The audio remains unchanged:
H's recording still has PCM id `9b0766353b737cc66833d4e7b9423b136cedefeec15555d7f1931b38e6971beb`.
No sample rate, precision, model quality, or arrangement was reduced.

## Render measurements

Before is a clean snapshot of the checkout before this pass; after is the updated checkout. The machine
is the same Apple Silicon Mac, CPython 3.12.14, numpy 2.5.3, scipy 1.18.1, numba 0.67.0, and Pyodide 314.0.7.
Runs shared the host with other work, so these are observations rather than device performance guarantees.
Browser measurements use the actual Pyodide/numpy/scipy/JS/wasm renderer under node, not a simulated synth.
Native measurements include `cli.render_one`, mastering, record measurements and writing FLAC, with seed
phrasing. Two repeats after warm-up; `MallocLargeCache=0` in both trees, returning large freed buffers.

| Work | Before | After |
|---|---:|---:|
| Browser refrain, 25.1 s of audio, first render | 8.64 s | 5.61 s |
| Browser refrain, same worker warm | 6.78 s | 4.52 s |
| Browser whole H, 151.4 s of audio | 55.46 s | 33.61 s |
| Native whole H, one thread, warm repeats | 18.15–19.21 s | 16.50–17.11 s |
| Native whole H, two threads, warm repeats | 11.57–11.90 s | 10.79–10.96 s |
| Native peak RSS, one thread | 1.182 GB | 1.118 GB |
| Native peak RSS, two threads | 1.287 GB | 1.226 GB |

The browser section's heap remains 387 MiB. Whole H's heap remains about 1.1 GiB (1117 MiB before,
1145 MiB after); its large neural-network matrices still dominate. The instrument memory improvements
below help different arrangements without promising that this particular song's browser heap will fall.
Actual phone hardware and Safari were not measured in this pass.

## Where the work was saved

- **Browser neural prediction.** The existing BLAS patch accelerated input/output projection, but the
  convolution and residual matrices bypassed it and used Pyodide numpy's slow matrix multiplication.
  Every product now goes through `throat._matmul`, with scipy's BLAS on the browser path. The transpose
  layout avoids copies of inputs and returns a contiguous matrix. Native multiplication is unchanged;
  bias addition reuses the product buffer when its dtype matches.
- **Voice pitch and consonants.** Vibrato, gestures and consonant perturbations are evaluated over their
  own time spans. Transition splines keep their changing stretch; settled tails retain the original
  expression's rounding. Gaussian tails are cut only where they underflow to exactly zero. H's pitch
  control: 134.6 → 18.9 ms; B's: 43.0 → 9.9 ms. The vocoder allocates its correctly laid-out zero periodic
  response directly instead of transforming a zero spectrum: a 30 s case takes 563 → 513 ms on one thread.
- **Acoustic bodies.** `oa.convolve_shared` shares the bridge force's forward FFTs across microphones.
  Each response and inverse transform retains its previous row grouping and each overlap-add its order;
  batching inverse transforms across channels was rejected because it changed the bits.
- **Instrument temporaries.** Fiddle hair noise reuses the catch buffer. Electric pianos clip and apply
  tremolo in bounded stretches and release the oversampled result early. Organ releases its generator
  buffers before the speaker and clips an owned buffer in place. Harmonium makes pressure and hiss in
  stretches, retaining the original whole-track pressure average. Oscillator drift reuses its time buffer.
- **Mixing and mastering.** Gain application moves division and branching outside the per-sample loop.
  Stereo K-weighting uses scalar filter states while adding left then right power in the original order.
  On 3,000,077 stereo samples: split-band gain 8.04 → 6.34 ms; K-weighting 26.62 → 14.18 ms. PCM hashing reads
  the contiguous little-endian array's buffer directly, eliminating a second PCM-sized bytes allocation.

Standalone 150 s instrument workloads, one thread, median of three; traced peak allocations, decimal MB.
These are each piece's allocation peaks, not whole-process RSS or wasm heap measurements. Every output
hash matched before and after, including the random streams after chunked noise generation.

| Piece | Before peak | After peak | Before → after time |
|---|---:|---:|---:|
| Guitar body | 229 MB | 210 MB | 0.258 → 0.203 s |
| Fiddle bridge | 370 MB | 318 MB | 0.577 → 0.572 s |
| Electric piano | 425 MB | 160 MB | 1.142 → 1.081 s |
| Reed piano | 319 MB | 159 MB | 0.935 → 0.950 s |
| Organ | 323 MB | 159 MB | 1.097 → 1.104 s |
| Harmonium | 438 MB | 224 MB | 1.243 → 1.266 s |
| Oscillator drift | 370 MB | 56 MB | 0.0375 → 0.038 s |

## Browser memory after a render

Cached files are now least-recently-used and bounded by both counts and bytes: 64 MiB on phones or devices
reporting less than 4 GB of memory, 192 MiB otherwise. Eviction releases the blob URL. The newest result and
most recent actual recording are retained even when they exceed the budget, since the player's and the
visible recording's Download/Play controls still need them. Promoting a cached whole preview to a recording
also releases the previous recording's exception. The existing 16-section/3-whole count bounds still apply.

A section worker whose successful render reports a heap over 512 MiB on those constrained devices, or
768 MiB elsewhere, is terminated after its file is transferred. Small workers keep the existing reuse,
four-render and idle limits. Whole workers retain their existing one-render lifecycle. This changes only
retained memory, not which browser is permitted to render or how failures fall back to the server.

## Verification

- H's browser section and whole-song PCM match the pre-change files byte for byte (13,355,872 samples
  for the whole stereo song). The regenerated JS section also matches. Native H keeps its golden PCM id
  on one and two threads; the full run's other golden checks passed.
- All 60 registered instruments' native gauntlet stems match the pre-change stems byte for byte.
  All 60 also render with the browser's wasm path. Cross-platform float64 differences from transcendental
  functions remain, as documented in BROWSER-RENDER.md; these are distinct from before/after sample parity.
- Generated JS, type metadata, C ports, wasm binary and source stamps were updated together. Captured
  gain, detector and stereo meter calls match native output exactly through the updated browser ports.
- Focused regression tests cover original control-track/instrument hashes, convolution geometry, strided
  inputs, partial blocks, in-place ownership, mixed dtypes, BLAS routing and browser cache/worker lifecycle.
- Full run: 1935 passed and 13 skipped. Librosa initially could not write its numba cache outside the
  sandbox; the affected tests and the regenerated-kernel checks were rerun with a temporary cache:
  18 passed. Two unrelated assertions remain and fail identically in the pre-change snapshot: the invite
  test's October 1 fixture has become stale, and the piano grid test gets 648 of 721 notes against a 90%
  threshold. Final JavaScript run: 126 passed.

Repeat browser measurements with `node web/studio-wasm/node/run.mjs --section 2 --kernels wasm --stages`
and `--whole --reps 1`; rebuild its ignored `dist/songbird.zip` with `tools/bundle.py` after Python changes.
Use `tools/transpile.py --check` for generated-source freshness and `bench/gauntlet.py` for every instrument.

## Follow-up: memory, edit reuse, and Astra review

The second pass addresses the remaining five areas without changing sample rate, precision, model quality,
or exported PCM. Before below is the completed first pass above, not the original checkout.

| Work | First pass | Follow-up |
|---|---:|---:|
| Learned predictor, 30,280 frames, native traced peak | 204.5 MiB | 74.1 MiB |
| Owned preview gain/clip/limit/fade/quantization, 3,000,077 stereo frames, traced temporary peak | 148.4 MiB | 57.0 MiB |
| Stereo width, same frame count, traced temporary peak | 68.7 MiB | 24.4 MiB |
| Room sends, 60 s mix, traced stage peak | 60.6 MiB | 21.2 MiB |
| Room ducking, same mix, traced stage peak | 81.3 MiB | 21.7 MiB |
| Browser H vocal-phase heap (at next part's progress) | 1044 MiB | 660 MiB |
| Browser H whole render | 33.61 s | 31.95 s |
| Browser H whole heap | 1145 MiB | 1148 MiB |
| Browser refrain, first / warm | 5.61 / 4.52 s | 5.31 / 4.44 s |

These are desktop observations under the same native/Pyodide environments as above, with other work on
the host. Temporary peaks are allocations of the named operation, not whole-process memory. Whole-song
native RSS remains about 1.12 GB, with warm one-thread observations of 16.64–18.06 s; the remaining instrument
and mix phases still set its peak. The whole-song browser heap also remains about 1.1 GiB. Actual phones
and Safari remain unmeasured.

- **Voice:** inference processes 4096-frame blocks with the sum of all convolution dilations as context.
  Pitch slopes are calculated before slicing; global variance keeps its full-song reduction. Tiny final
  blocks are merged to retain the browser's BLAS routing. Input embeddings and final activations are
  released early; normalization reuses owned results. Mel/bin interpolation, spectral scatter geometry,
  and cepstrum folds use small bounded, read-only caches.
- **Mix and preview:** owned preview buffers are clipped, limited and faded in place, then released after
  quantization. Sends, delayed choir sends, return ducking, width scratch and scalar magnitude checks use
  bounded stretches. Singer-first rendering postpones the three empty band buses until an instrument is
  ready, removing roughly 306 MiB from H's vocal lifetime. Whistle turbulence and final high-pass filters
  carry SOS state across bounded stretches and retain the same RNG draws.
- **Edit reuse:** studio previews keep immutable dry-stem snapshots and return an owned copy to the mixer.
  Keys describe realized notes, timing, seed, instrument settings, lexicon and singer/choir context, rather
  than the edit request alone. Changed parts replace their older snapshots; admission favors synthesis
  work saved per byte. The cache is bounded to 32 MiB on constrained browsers, 128 MiB on other browsers,
  and 64 MiB in the native studio. Oversized stems bypass it. Whole renders clear/bypass it. Allocation
  failure during optional retention skips caching; failure copying a hit transfers ownership and clears
  retained entries.
- **Startup:** permanent control and packet-reader workers retain numpy/scipy/soundfile but omit renderer
  kernels and eager DSP initialization. They select vectorized fallback paths before importing the synth.
  The renderer alone marks its assets fetched. Actual-worker measurements: ready 5.45 → 2.17 s, but studio
  imports move to view creation, so time to usable view improves only 6.09 → 5.33 s and its resident heap
  remains 130 MiB. Timeline generation remains about 5 s; this is a separate future target.

The actual `studio-worker.mjs` also made an unchanged preview and a mix-width edit with the same PCM IDs as
the first-pass worker: warm edited preview 1.02 → 0.56 s; returning to the original 0.98 → 0.55 s. This is a
live device-studio section under its `machine: none` choices, distinct from the fixed H refrain benchmark.
Its renderer heap grows 187 → 224 MiB as it retains the bounded 32 MiB cache: a deliberate memory/latency
tradeoff. The control worker remains separate, so synthesis does not block studio requests.

**Verification:** Astra reviewed ownership/invalidation, convolution context and global statistics, filter
state/RNG order, bus ordering, layout/dtype boundaries and control initialization. Its two empty-convolution
findings were fixed, including float32/int16 empty outputs. Before/after H section and whole-song browser PCM
match byte for byte, and native H keeps its golden id. Native browser/server section and packed whole-render
identity pass. Final frozen-source regression/integration checks passed 128 Python tests, following the
broader voice, dynamics and mastering checks. All 123 JavaScript tests passed. The actual
lean worker answered timeline/arrangement/sound/render-spec requests and read/restored a packed rendition.
Generated kernel freshness and the portable program's 8 MiB goal pass (6,944,665 bytes).

Reproduce actual-worker startup, preview reuse and optional packet read/restore with
`node web/studio-wasm/node/preview_bench.mjs --bundle SITE/render/app-HASH/songbird.zip --cache-mib 32`
after `tools/build_site.py` creates a local site. Add `--full-control` for the former initialization path,
`--control-only` to omit audio, or `--read RENDITION.flac` for a packed rendition. The runner uses Node's
workers with Web Worker API adapters around the unchanged production worker; it does not simulate a phone.
The WAV/PCM prototype zip made by `tools/bundle.py` deliberately contains a soundfile stub and cannot be
used for this FLAC-worker benchmark. `node/run.mjs --bundle BEFORE.zip` supports isolated comparisons.

# The web studio's start, its edits and its voice (2026-11-05)

A fresh look at the browser's renders, with an advisor (Fable) reading the hot code beside the profiles. The rule is
the same: **no sample changes.** H's seed keeps `tests/golden/h-seed.sha256`; the device studio's refrain preview
keeps `14ec579ee295…` (its mix-width edit `f0bf9568c2ea…`), its whole song `351e1dfa89f7…`, before and after.

Measured in node 22 with Pyodide 314.0.7 on an x86 Linux container (4 cores, about 1.7x an M1 Max's times, so every
number is larger than the earlier sections'), from a built site (`tools/build_site.py --days 0`) through the actual
worker (`node/preview_bench.mjs --cache-mib 128`, the desktop's stem cache). Phones and Safari were not measured.

| | before | after |
|---|---:|---:|
| the studio's worker: usable (control ready + the studio's view) | 4.69 s | **1.73 s** (a later visit or worker) |
| a render worker: ready | 9.99 s | **4.15-4.5 s** (a later visit or worker) |
| a section's edit (the mix's width), its stems kept | 2.8 s | **2.3-2.45 s** |
| the whole song (the device's H, in its own worker) | 123.9 s | **119.6 s**, its heap 1598 → 1544 MiB |
| the first section, its worker started | 10.2-10.9 s | 10.3-11.3 s (within the run-to-run noise here) |

## Where the start went

A render worker took 10 s to be ready: Pyodide 2.2 s, numpy/scipy/soundfile 2.6 s, importing the program 5.6 s.
cProfile put 4.1 s of the import in `compile()`: **Pyodide's standard library and wheels carry no bytecode, and it
writes none** (`sys.dont_write_bytecode`), so every worker compiled about 680 modules from source: scipy 2.7 s, the
standard library 2.4 s (1.9 s of it inside `loadPyodide`, before any code of ours runs), the program 1.3 s, numpy
0.7 s. And every worker starts afresh: each whole song's, each fourth section's, one idle three minutes, the studio's.

- **Bytecode kept in the browser** (`py/bytecode.py`, `studio-worker.mjs` "bytecode kept in this browser"). A worker
  writes what it compiles under `sys.pycache_prefix` (as Python's import does; the prefix's top folder has to exist
  first, or import makes it relative to the working directory and fails silently), and once it has made something new
  and been idle two seconds, hands back archives that it keeps in Cache Storage (`songbird-bytecode`): Pyodide's
  packages' and the program's pycs, and the standard library's zip with bytecode for the modules it imported
  (compiled a few at a time, so a question asked meanwhile waits for one step). The next worker unpacks them before
  it imports, and starts Pyodide with the kept zip in place of the served one (`loadPyodide`'s `fsInit`, once
  Pyodide's own write of the served zip has landed: it is written as its fetch arrives, after the hook is called).
  Every pyc is **checked-hash** (PEP 552): Python runs it only for a source whose hash it carries, so nothing kept is
  ever run stale, whatever the cache holds (unpacked files' times can't be trusted: Pyodide gives them the time they
  were unpacked). The keys are the bundle's content-named folders, so a new program or Pyodide is a new key, and
  the older ones are let go when the new are kept. About 17 MB is kept (the standard library 8.1, the packages 6.5,
  the program 2.2). Without Cache Storage (a private window may refuse it), workers compile as before.
- **Why not shipped from the build.** The same bytecode, made at build time, is 9.5 MB on the wire for a render
  worker (5.5 for the studio's), against 14-28 MB today; pyc files are about four times the size of their sources
  compressed (without column tables, `PYTHONNODEBUGRANGES`, a fifth less). Kept in the browser, it costs nothing to
  fetch, and only the first worker of each kind on a first visit compiles.
- **scipy's docstrings left as they are** (`web_patches.plain_docs`, before scipy.signal is imported). scipy parses
  and rewrites about 800 docstrings as it is imported (array-API notes, the stats tests' parameters), with its
  numpydoc reader: its `FunctionDoc` and `ClassDoc` are stood in for by one that keeps each docstring as it was.
  Importing the program: 2.05 → 1.53 s with the bytecode kept. Only docstrings change.

## Where an edit went

With its stems kept (128 MiB), a section's mix edit took 2.8 s: laying out the score again 0.75 s (`band.arrange`'s
Python), the mix 2.2 s, the master and FLAC 0.4 s.

- **The score is kept across edits** (`studio_render._score`, the last two). It is made of the song, the version's
  choices but the mix's (realize and lay never read the mix), its words, phrasing and choir; a mix edit, or the same
  version asked again, lays out the same frozen Score, which window, cut and the synthesis only read.
- **The room's responses are made once for its numbers** (`room.responses`, `room.plate`: `lru_cache`, handed back
  read-only), natively too. About 0.1-0.2 s a render, within this machine's noise.

## The voice's vocoder

`throat.synthesize`'s blocks of pulses made about twenty temporaries the size of the block each (clips, wheres,
exps, the phase's chain, a roll), each an allocation and a pass in wasm. Now each is worked out in place where the
array is the block's own, every product and sum the same, in the same order (a product's operands swapped only where
IEEE multiplication commutes), the roll as two slice copies, the cepstrum folded in place: the same bits, natively at
any thread count (Fable checked 7,727 pulses with the texture and a source, and plain) and the goldens above. The
whole song: 4.3 s less in the browser and 54 MiB less heap; natively a 25 s voice 1.07 → 0.84 s on one thread.

## Measured and not taken

- **The CMU dictionary read a word at a time.** The profiler put `cmudict.dict()` at 1.6 s of the first section; it is
  0.51 s unprofiled (a Python loop, which cProfile inflates), and an exact lazy reader (a regular expression for each
  line's word, the first and last line of each by a dict, verified against every word) made it 0.31 s. Not worth a
  second reader of the dictionary. (phonetics.py's bytes are part of singing's measurement version,
  `tools/phrasing.py` `version()`: a change there would make every kept template stale, so any such change belongs
  in the browser's patches, not in it.)

## What's left, by size (the advisor's list, measured here)

1. **The network's products** (`web_patches._dgemm_matmul`): 1.3 s of a section, 20 s of the whole song, Pyodide's
   OpenBLAS without SIMD at about 7 GFLOP/s. A wasm-SIMD kernel ran 16 GFLOP/s in node (2.3x); to be taken only if it
   matches OpenBLAS's own order of sums bit for bit in Pyodide (its K blocking, to be found by experiment), with a
   fallback where wasm has no SIMD. About 0.7 s a section and 10 s a whole song.
   **Done** (below, "The voice's matrix product in wasm SIMD"): OpenBLAS's blocks are four of 120 for K = 480,
   not two, and the kernel equals `blas.dgemm` bit for bit; 1.22 to 0.62 s of a section, 7.35 to 3.78 s of a
   whole song, measured on 4 shared x86 cores.
2. **The treated stems kept, not the dry ones** (`mixing.mix_made`'s `instrument` and `lead`): an edit of the mix
   treats every stem again (0.6 s of channel strips, 0.3 s of the lead). A strip depends only on its stem, role, rate
   and length; keeping it would take an edit from 2.4 to about 1.5 s, with the stem cache's keys carried into the mix.
3. **The JS kernels to C/wasm**: `master._windows`, `fx._sliding_min`, `_follow`, `_running_mean`, `_abs_max`,
   `_placed`, `_mean_ahead`, `_saturate`, `_block_peaks` (0.35 s of a section or an edit, 4-6 s of a whole song), as
   the fourteen ported, checked by `check_kernels.py`.
4. **The stereo biquads two channels at a time** (`fx_two/_four/_one` in `wasm/kernels.c`, f64x2 lanes, each channel's
   arithmetic unchanged): bit-identical in node, 72 → 38 ms on 7.3 M stereo samples; 5.4 s of a whole song. Needs a
   `-msimd128` build beside the plain one.
5. **The true peak's taps** (`master.true_peak_envelope`'s `rows @ taps.T`, numpy's plain loop in Pyodide): a kernel in
   the same order, about 2 s of a whole song.
6. **The timeline** (`/api/timeline`): still 9.5 s in the studio's worker, a separate target (docs/WEB-STUDIO.md, "A
   quicker start", decision 4).

Reproduce: `node web/studio-wasm/node/preview_bench.mjs --bundle SITE/render/app-HASH/songbird.zip --cache-mib 128
--kept DIR`, twice (the second is a later visit: `--kept` stands in a folder for Cache Storage). Node's fetch
reaches Pyodide's CDN through a proxy only with `NODE_USE_ENV_PROXY=1`; where the CDN is refused, the release's
`pyodide-314.0.7.tar.bz2` from GitHub holds the same wheels (its lock is the npm package's), unpacked beside
`node_modules/pyodide`.

# The voice's matrix product in wasm SIMD (2026-11-05)

In the browser, the learned voice's matrix products (`throat._matmul`, x @ W.T in float64: (N, 480) @ (480, 160)
for each convolution and (N, 160) @ (160, 160) for each mix, N about 4096 plus context) went to scipy's OpenBLAS
`dgemm` (`py/web_patches.py`), at about 7 GFLOP/s in Pyodide. They now go to a C kernel built with `-msimd128`
(`wasm/kernels.c` `matmul_blas`, in a second build `wasm/kernels-simd.wasm`), at 14 to 17 GFLOP/s in node, with
the same bits.

**The same bits.** A product's last bits depend on the order its k terms are summed, so the kernel sums each
output in the order Pyodide's OpenBLAS does, found by experiment and then from its source. Pyodide 314.0.7's
`libopenblas.so` is OpenBLAS 0.3.31 built single-threaded for `RISCV64_GENERIC` (its config string): dgemm's Q is
120, its unroll 2, its kernel the generic 2x2. With beta 0 it zeroes C, then adds each block of k's partial sum
(each summed one product after another from zero) to C in turn. `driver/level3/level3.c` takes Q at a time while
at least 2Q remain, then the rest if no more than Q, else half of it rounded up to the unroll. So K = 480 is
((((0 + S[0:120]) + S[120:240]) + S[240:360]) + S[360:480]), not two blocks; K = 160 is (0 + S[0:80]) + S[80:160].
Against `blas.dgemm` on random inputs of every magnitude, only Q = 120 matched for K = 480 (Q = 60 to 512 tried),
and the rule matched every one of 100 shapes (K from 1 to 1000, odd N and M, zero rows). Each f64x2 lane is one
output, two of a row's outputs at a time, a 2 x 4 tile of lanes summed in registers; wasm has no fused
multiply-add, so each product rounds before it is added, as in OpenBLAS's C. The compiler's own vectorizing is
off in that build (`-fno-vectorize -fno-slp-vectorize`), so the other 14 ports are the same instructions as in
`kernels.wasm` (compared function by function in the assembly). `kernels.wasm` itself is unchanged, byte for byte.

**Guards.** `wasm/kernels.mjs` fetches `kernels-simd.wasm` where a 26-byte SIMD module validates
(`WebAssembly.validate`), else `kernels.wasm`, and then the products stay dgemm's. Before its first use at each
k and m, `web_patches` compares the kernel with `blas.dgemm` bit for bit on random inputs of every magnitude and
uses dgemm if they differ, so a Pyodide whose OpenBLAS sums otherwise would only be slower. `tools/check_kernels.py`
checks it against `blas.dgemm` (216 shapes, and every weight of the network), and `wasm/sources.json` records
`throat._matmul`'s source and the Pyodide version it was checked in: a change to either makes `transpile.py
--check` (tests/test_browser_kernels.py, and the site's build) ask for that check again, then `--stamp-wasm`.

**Measured** (node 22, 4 shared x86 cores, so ±15%): at the network's shapes, 4465 x 480 @ 480 x 160 took 99 ms
by dgemm and 49 ms by the kernel; 4465 x 160 @ 160 x 160, 33 and 15 ms. In H's refrain (section 2) the voice's 36
products of 64 rows or more (16 convolutions, 18 mixes, 2 outputs) took 1.22 s by dgemm and 0.62 s by the kernel (the section 8.2 to 7.8 s,
warm); over the whole song the 144 such products took 7.35 s and 3.78 s (the render 70.9 to 68.5 s). Section
and whole-song PCM are byte-identical to dgemm's (`node/run.mjs --section 2` / `--whole --kernels wasm`, and
`--no-simd` for the fallback), and the device studio's H keeps its ids (`preview_bench.mjs` on a
`build_site.py --days 0` site: section 14ec579ee295..., `device_run.mjs --whole`: 351e1dfa89f7...), as does H's
native golden (tests/test_styles.py).
