# Can Songbird render in the browser? (2026-09-29)

A feasibility spike for the public web studio: can the program itself sing a
section preview (and ideally a whole recording) inside a visitor's browser,
instead of on the 8 GB server it shares with the mail? Targets: a section in
≤15 s, the song in ≤90 s, peak memory ≤1.5 GB, on a desktop browser.

**Short answer: yes for previews, today, and byte for byte.** The unmodified
`songbird/` package runs in Pyodide (CPython compiled to WebAssembly) with its
81 numba kernels replaced, in the browser only, by translations to JavaScript
(or, for the heaviest, C compiled to wasm). In Chrome, H's first refrain (25 s
of music) renders in **4.7-5.8 s**, and its 16-bit PCM is **identical** to the
native render's. The whole song renders in **32 s**, and its id is
`9b0766353b73…`, the golden id in `tests/golden/h-seed.sha256`. What misses
the targets is the whole song's **memory: a 3.1 GB wasm heap**, the same shape
as the native peak (4.7 GB RSS at one thread). Recommendation below:
**hybrid** now (previews in the browser, records on the server), whole songs
in the browser once the memory work lands.

The prototype is `web/studio-wasm/` (how to run it is at the end). Nothing in
`songbird/` changed; the goldens hold (`test_determinism`,
`test_styles::test_the_seed_of_h_renders_byte_identical`, the seed scores
and the words golden: 22 passed).

## What the time is spent on (native, one thread)

H's first refrain (form index 2), `SONGBIRD_THREADS=1`, M1 Max
(`bench/profile_kernels.py`):

| | total | in numba kernels | everything else |
|---|---|---|---|
| section, JIT (warm) | 2.23 s | 0.43 s (19%) | 1.79 s |
| section, `NUMBA_DISABLE_JIT=1` | 115 s | 112.7 s (98%) | 2.6 s |
| whole song, JIT (warm) | 15.4 s | 3.5 s (23%) | 11.9 s |

With the JIT the kernels are a fifth of the time; without it they are all of
it (50-100x slower as plain Python, before Pyodide's own 1.5-3x). So every
kernel a render touches has to be ported, but once they are, the kernels stop
being the bottleneck: numpy, scipy and Python are.

H's seed touches 20 of the 81 kernels. Whole song, JIT, by time:
`drum._ring` 0.49 s, `pluck._bank` 0.45, `pluck._loop` 0.41 (2440 calls),
`fx._two` 0.37, `fx._four` 0.35, `fx._one` 0.28, `fx._detect` 0.16,
`pipe.run` 0.15, `fx._apply` 0.14, `bowed.run` 0.13, `master._recover` 0.11,
`fx._saturate` 0.09, `fx._block_power` 0.09, `fx._block_peaks` 0.08,
`fx._products` 0.05, `fx._follow` 0.05, `master._hop_power` 0.03,
`reed._read` 0.03, `fx._ballistics`, `fx._span`. Ten cover 85%. Other
styles and lineups bring in the rest (every instrument is exercised by
`bench/gauntlet.py`, below). (docs/PORTABILITY.md, when it lands on main, has
the other agent's table; it wasn't there when this was written.)

## What was built

1. **A translator, not a port** (`tools/transpile.py`). It reads every
   `@njit` function's own source (Python's `ast`) and writes JavaScript
   (`kernels/kernels.gen.mjs`), typed as **numba itself typed it**:
   `tools/kernel_types.py` renders natively and asks each dispatcher for its
   argument, local and return types (`cres.type_annotation.typemap`). It keeps
   numba's semantics where JS differs: Python's floored `%` and `//`
   (CPython's float algorithm), integer powers by numba's unrolled squaring
   (`x**3` is `x*x*x`, not `pow`), `min`/`max` as Python picks, `int()`
   truncating, range loops whose variable the body can't disturb, numba's
   negative-index wrap, module constants frozen at translation as numba
   freezes them at compile time, integer arrays truncating on store, `uint64`
   generators as BigInt wrapped to 64 bits, elementwise array expressions
   (`np.cos(2 * np.pi * freqs / sr)`) as numba's ufunc loops do them.
   **79 of 81 kernels translate automatically**; the two that use complex
   numbers (`piano._spectrum`, `struck._bank`) are ported by hand
   (`kernels/hand.mjs`, 90 lines, numba's complex multiply and `cmath.exp`
   spelled out).
2. **A numba shim** (`py/numba/__init__.py`), first on `sys.path` in Pyodide
   only: `njit` looks the kernel up by module and name and hands back a
   caller that passes numpy arrays to JS **as views of Pyodide's own memory
   (no copy)** (`{d, n0, n1, s0, s1}` descriptors built from
   `__array_interface__`), so in-place kernels write into numpy's arrays as
   numba does; results made in JS are copied into new numpy arrays; numba's
   return type decides int/float/tuple/uint64. A kernel with no port stays
   plain Python.
3. **C/wasm for the heaviest 14** (`wasm/kernels.c`, 300 lines, built with
   `zig cc -target wasm32-freestanding`; `tools/build_wasm.sh`). The module
   **imports Pyodide's own `WebAssembly.Memory`** and JS's `Math`, has no
   data segment and never touches the linear-memory stack (checked in the
   assembly), so its pointers are numpy arrays' data addresses: zero copy,
   no allocator, 6 KB. `py/wasm_kernels.py` adapts them (numba's allocations
   done with numpy first). This is what a proper Pyodide package built with
   emscripten would be, without the package.
4. **Two browser-only patches**, same numbers (`py/web_patches.py`):
   - `master.true_peak_envelope` gathers rows from a `sliding_window_view`;
     over a whole song that view is a virtual 6.7 M x 65 float64 array, and
     numpy on wasm32 refuses any array over 2 GiB ("array is too big"). A
     stand-in gathers the same elements directly.
   - Pyodide's numpy has **no BLAS**: its matmul is a plain loop (~1
     GFLOP/s). The learned voice's 26 matmuls (`throat._linear`, 4465x480 @
     480x160 in a section) took 3.2 s of a 7.5 s section. scipy's OpenBLAS
     `dgemm` in Pyodide is 4x faster (80 ms vs 311 ms each), and the output
     stayed identical.
5. **Runners**: `node/run.mjs` (Pyodide under node, for measurement),
   `index.html` + `worker.mjs` (the browser: a Web Worker loads Pyodide,
   numpy, scipy, `dist/songbird.zip` and the kernels, renders, posts back a
   WAV written with the standard library's `wave`), `section.py` (a section
   exactly as `Studio._section` makes it; the whole song as `render_one`
   masters it), `tools/compare.py`, `tools/check_kernels.py`,
   `bench/gauntlet.py`, `bench/all.sh`.

## The numbers

M1 Max, one thread everywhere, H's seed, section = form index 2 (the first
refrain, 25.1 s of audio). Node 26 (V8) and the built-in browser (Chrome 152).
Pyodide 314.0.7 (Python 3.14.2, numpy 2.4.6, scipy 1.18.0); native: Python
3.12, numpy 2.5.3, scipy 1.18.1, numba 0.67. The machine was shared with
other agents; `bench/all.sh` was run at a quiet moment (load 2-14), and the
browser runs repeat within ±20% of node.

| | native (numba) | Pyodide + JS kernels | Pyodide + wasm (14) + JS |
|---|---|---|---|
| section, first render | 3.19 s | 6.46 s (Chrome 6.8) | 5.16 s (Chrome 5.8) |
| section, again | 2.29 s | 4.96 s | 4.44 s (Chrome 4.7) |
| of which kernels | 0.43 s | 1.04 s | 0.52 s |
| whole song | 14.6 s | 37.9 s (Chrome 40.9) | 32.4 s (Chrome 32.3) |
| of which kernels | 3.5 s | 8.3-11 s | 5.2 s |
| memory, section | 1.04 GB RSS | 660 MiB wasm heap (node RSS 1.5 GB) | 691 MiB heap (RSS 1.16 GB) |
| memory, whole song | 4.67 GB RSS | 3.07 GB heap (RSS 4.46 GB) | 3.07 GB heap (RSS 3.80 GB) |
| PCM vs native, section | - | identical | identical |
| PCM vs native, song | - | identical (id = golden) | identical (id = golden) |

Getting ready (before the first render): Pyodide 1.1 s, numpy + scipy
0.9 s, unzipping the program 0.05 s, importing songbird (and every
instrument module, so every kernel is declared) 3.0 s: **~5-6 s from a local
server**, the same in Chrome. (Natively, a fresh process spends ~9 s importing
numba and songbird and loading numba's cache before its first section.)

**First-load size** (`tools/sizes.py`; raw / gzip / brotli, MiB): Pyodide
core (`pyodide.asm.wasm` 9.2, `.asm.mjs` 1.2, stdlib 2.4) 12.9 / 6.0 / 5.2;
numpy 2.8 / 2.8; **scipy 13.4 / 13.2**; the program `songbird.zip` 4.7 (the
learned voice `throat.npz` is 3.4 of it); the kernels 0.16 / 0.04; the wasm
6 KB. **34.0 MiB raw, 26.7 gzip, 25.9 brotli** on a first visit, cached after.
scipy is half of it and songbird uses four of its subpackages (signal, fft,
ndimage, linalg.blas): a trimmed scipy build could halve the download.

Where the browser's time goes (a warm section, wasm kernels, ~4.4 s): the
voice's matmuls by BLAS ~0.85 s, FFTs (numpy's pocketfft and scipy's ducc)
~1 s, the kernels 0.5 s, the rest Python and numpy's elementwise work (in
Pyodide 1.5-3.5x native, as expected). The kernels are no longer the story.

### Every instrument (`bench/gauntlet.py`)

Every one of the 58 instrument names the band can play, a 4-bar part each,
rendered natively (reference, 7.3 s in all) and in Pyodide with all 81
kernels in JS: **all 58 render; 19.0 s in all, 2.6x native** (most 1.6-3x;
organ 6x, tambourine 8x, shaker 5x and the analog synths 4-4.6x, the last from
BigInt arithmetic in a per-sample noise generator: a 32-bit-pair or C port
fixes that). Every stem is within **-174 dB of peak** of the native one, most
within -250 dB: float64 differences, nothing a 16-bit file can show.

## Byte identity

Three levels, measured:

1. **Kernels, float64, bit for bit** (`tools/check_kernels.py` replays real
   numba calls captured natively). Every kernel made of `+ - * /`,
   comparisons and `floor`/`sqrt` is **bit-identical** in JS and in C/wasm:
   28 of the 42 kernels captured (all 14 C ports, `pluck`, `fx`, `master`, `bowed`,
   `fretboard`, `kit`, `organ._rotors`/`_scanner`, `piano.hammer_force`,
   `reed`, `struck._up2`, `amp._run`, `accordion._arm`, ...). So yes: **C
   compiled to wasm with strict IEEE doubles matches numba bit for bit**
   (wasm has no fused multiply-add and nothing reorders), as does plain JS.
   The 14 that differ all use `sin`/`cos`/`exp`/`log`/`pow`/`tanh` (numba
   calls the system's libm; the browser has V8's fdlibm; Pyodide's own Python
   has musl's, and differs from both), or are `fastmath=True` (the 7 in
   `analog.py`: LLVM may fuse and reorder there), or call `osc._blep4`, which
   the native cache had compiled with fastmath (`chip._staircase`,
   `drummachine._bank`: the bug below). The worst: 1.3e-13 of peak.
2. **Stems**: within -174 dB of peak for all 58 instruments. The rest of the
   pipeline in Pyodide (numpy 2.4 on musl, no BLAS, no SIMD dispatch) differs
   in the last bits too.
3. **The 16-bit PCM, which is what the id hashes: identical**, for the
   section and the whole song (13.4 M samples), JS or wasm, node or Chrome. A
   float difference of at most ~1e-13 of full scale flips a sample's rounding
   with a probability of at most ~1e-13 x 32768 x 2 per sample: at most ~0.1
   expected flips in a whole song: identical most of the time, **not guaranteed**. When it does
   flip, one sample moves by 1 LSB (-96 dBFS): inaudible, but a different id.

So the artist's question ("may the web version differ in the last bits?")
comes to this: as built, it doesn't, for H's seed; it could, rarely, and
inaudibly. To make identity *guaranteed* rather than probable:

- Drop `fastmath=True` from `analog.py`'s 7 kernels (their speed cost
  natively is to be measured; they're the synth voices, not the seed band).
- Give the kernels deterministic transcendental functions: `sin`, `cos`,
  `exp`, `log`, `tanh`, `pow` written as njit Python from plain arithmetic
  (an fdlibm or CORE-MATH port), used natively and translated like the rest.
  This changes the native output once (new goldens: the artist's call) and
  makes it the same on macOS, Linux and the browser, which it isn't today
  either: native renders on another OS already use another libm.
- The same for the few numpy ufuncs on the hot path outside kernels, if the
  stems' -250 dB differences ever flip a sample.

**A native determinism bug found on the way.** numba compiles `osc._blep4`
differently depending on who asks first: compiled as a callee of a
`fastmath` kernel (`analog._wave`, the synths), it inherits fastmath, and that
machine code is written to `songbird/synth/__pycache__` and used by every
later process. Measured: with a fresh cache, `_blep4` matches its Python
source at 20000 of 20000 points; after rendering the `arp` first, it differs
at 10863 of 20000 (1-2 ulp), for good. So on a machine whose first render
used a synth, the chip, drum-machine and analog instruments sing slightly
different bits than on one whose first render didn't. H's seed doesn't use
them (the goldens hold either way), but a lineage that picks those
instruments could get different ids on two machines. Removing `fastmath`
from `analog.py` fixes it.

## The effort to port all 81

| approach | done here | all 81 | upkeep |
|---|---|---|---|
| **JS by translation** (this) | 79 automatic + 2 by hand, every instrument checked | done: 821-line translator, 90 lines by hand | regenerate on every kernel change (a build step); a new construct may need the translator taught |
| **C/wasm by hand** | 14 kernels, ~300 lines C + 155 lines adapters, ~1 hour | ~2800 lines of kernel Python: ~3500 lines C, 2-4 agent-days with the check harness | two sources for every kernel; the artist edits Python, the C drifts unless CI replays captured calls |
| **C/wasm by translation** (not built) | - | the same translator with a C back end: numba's types are already known for 68 of 81 (the rest are helpers compiled inside their callers, or kernels no instrument uses), ~1-2 days | as JS, plus a C toolchain in the build (zig or emsdk) |
| **Pyodide package** (emscripten side module, `ctypes`) | - | as either C route; loads like numpy | needs pyodide-build/emsdk; the zero-copy import-memory trick here already gets its speed |

The kernels are 12% of the browser's section time with wasm, 21% with JS:
porting more to C buys at most ~0.5 s a section. JS by translation is the one
to keep; the hand C ports are worth it only for the few hottest if whole
songs need every second.

## Risks

- **Memory (the real one).** wasm32 caps a page at 4 GB; the whole song
  peaks at 3.1 GB, and Pyodide's heap never shrinks (after one whole song
  the worker holds 3 GB until it is terminated; the prototype should render a
  whole song in a worker it then throws away). The heap tracks what native
  Python allocates, so the parallel work cutting the native peak to ≤1.5 GB
  should carry over nearly one for one. A section is ~700 MB. Also: numpy
  refuses views over 2 GiB (patched), and Pyodide's own `assign_to` breaks on
  addresses past 2 GiB (worked around by copying by address).
- **Safari and iOS (not tested here).** Pyodide supports Safari 16.4+. iOS
  Safari kills tabs around 1-1.5 GB (it varies by device) and wasm memory
  growth past ~1 GB often fails: a section (700 MB) is plausible on recent
  iPhones, the whole song isn't. JavaScriptCore's typed-array JIT is good;
  BigInt is slow (the synth noise generators). The wasm path avoids both.
  Needs a real test on a Mac and an iPhone before promising anything.
- **First visit is ~26 MB** and 5-6 s of setup before the first note; phones
  on mobile data will feel it. Cache it (HTTP caching; a service worker
  keeps it offline), trim scipy, and render the first preview while the
  page is read.
- **One thread.** Browsers can run workers in parallel, but each would need
  its own Pyodide (and heap). Not pursued.
- **Keeping it in step.** Every change to a kernel needs the translation
  regenerated and checked; every change to the pipeline could meet a wasm32
  limit (a >2 GiB view, a dependency with no Pyodide build). CI should run
  `bench/gauntlet.py` and `tools/check_kernels.py` in Pyodide.
- **Records need more than rendering.** A recording is a FLAC packet (the
  program, the song, the record: `pack.py`). Pyodide ships `soundfile`
  (libsndfile for wasm, contrary to what was assumed) and `zipfile` works, so
  it's likely feasible, but not tried.

## Recommendation: hybrid now, the browser for more later

- **Section previews in the browser.** Measured at 4.7-6.8 s in Chrome, well
  under the 15 s target, at ~700 MB, identical to the server's render. That
  takes the most frequent, most interactive work off the shared VPS, and the
  visitor hears their edit without waiting in a queue.
- **Records (whole songs) on the server**, for now. They work in Chrome (32 s)
  but at 3 GB, beyond Safari, iOS and modest laptops; they also make the
  packet. Revisit after the memory work: at ≤1.5 GB natively, whole songs in
  a desktop browser become reasonable, and the server only has to take the
  visitors whose browsers can't.
- **Server-only** remains the fallback for browsers without enough memory or
  wasm (detect and fall back per visitor).
- Keep the kernels as translated JS, generated in the build from
  `songbird/synth`, checked by the gauntlet; port only the hottest to C if
  needed. Before relying on ids matching across server and browser, decide on
  the byte-identity work above (fastmath, deterministic libm), and fix the
  numba cache bug either way.

## Running the prototype

    cd web/studio-wasm && npm install && cd ../..                 # pyodide (numpy/scipy come from its CDN, cached beside it)
    uv run python web/studio-wasm/tools/kernel_types.py songs/h-now-its-by-you.json web/studio-wasm/kernels/types.json --whole --gauntlet
                                                                  # (only after kernels change; set NUMBA_CACHE_DIR to an empty folder so numba compiles and keeps types)
    uv run python web/studio-wasm/tools/transpile.py              # kernels/kernels.gen.mjs + manifest.json
    uv run python web/studio-wasm/tools/bundle.py                 # dist/songbird.zip
    ZIG="python -m ziglang" sh web/studio-wasm/tools/build_wasm.sh  # wasm/kernels.wasm (pip install ziglang)

    node web/studio-wasm/node/run.mjs --section 2 [--kernels js|wasm|python] [--times] [--stages] [--out x.npy]
    node web/studio-wasm/node/run.mjs --whole --kernels wasm --out whole.npy
    uv run python web/studio-wasm/tools/compare.py native.npy whole.npy
    sh web/studio-wasm/bench/all.sh OUTDIR                        # the table above

    python3 -m http.server 8790 --bind 127.0.0.1 --directory web/studio-wasm   # (launch.json: studio-wasm)
    # then http://127.0.0.1:8790/ : Load, Render section / whole song (?times shows the kernels' times)

Checks: `bench/native_section.py` makes the native PCM; `bench/gauntlet.py`
(natively with an output path, then in Pyodide with `--mount DIR:/ref
--exec`) compares every instrument; `tools/kernel_types.py ... CALLS_DIR`
(with `CAPTURE_INSTRUMENTS=a,b` for other instruments) captures numba calls
that `tools/check_kernels.py` replays in Pyodide (`--mount CALLS_DIR:/calls`).
