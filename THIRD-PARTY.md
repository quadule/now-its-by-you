# Third-party software

Now It's by You (Songbird) is dedicated to the public domain: see LICENSE (CC0). That covers the project's own
work. This file lists what is not the project's own: code this repository holds, and what the studio at
https://studio.itsby.you sends to a visitor's browser so the studio can run there. Each keeps its own licence.

## In this repository

- **WORLD**, Masanori Morise's speech analysis and synthesis system (Harvest and CheapTrick), as pyworld 0.3.5
  vendors it: web/studio-wasm/world/src/, and web/studio-wasm/world/harvest_lean.cpp (src/harvest.cpp changed to
  hold less memory). Modified BSD licence, Copyright (c) 2010 M. Morise: web/studio-wasm/world/LICENSE.txt.
  Source: https://github.com/mmorise/World (pyworld: https://github.com/JeremyCCHsu/Python-Wrapper-for-World-Vocoder).
  web/studio-wasm/world/world.wasm is built from them, with parts of zig's libc for WebAssembly (wasi-libc and
  musl, MIT: https://github.com/ziglang/zig).

## Served by studio.itsby.you

The studio's site (web/studio-wasm/tools/build_site.py) sends these to the browser as they are released, besides
the project's own code. Versions are those the site is built with (web/studio-wasm/package.json pins Pyodide, whose
lock file pins the packages). This file is served beside them as https://studio.itsby.you/licenses.txt.

- **Pyodide** 314.0.7 (pyodide.mjs, pyodide.asm.mjs, pyodide.asm.wasm, python_stdlib.zip, pyodide-lock.json).
  MPL-2.0: https://www.mozilla.org/en-US/MPL/2.0/. Source: https://github.com/pyodide/pyodide; its package
  recipes: https://github.com/pyodide/pyodide-recipes.
- **CPython** 3.14.2 and its standard library, compiled into Pyodide. PSF License Version 2:
  https://docs.python.org/3/license.html (which also gives the notices of the libraries CPython is built with:
  zlib, bzip2, XZ Utils' liblzma, libffi, Expat, libmpdec, HACL*, SQLite). Source: https://github.com/python/cpython.
- **Emscripten**'s runtime, compiled into Pyodide and the packages below: MIT or University of Illinois/NCSA,
  with musl libc (MIT) and LLVM's libc++, libc++abi and compiler-rt (Apache-2.0 WITH LLVM-exception).
  Source: https://github.com/emscripten-core/emscripten.
- **NumPy** 2.4.6. BSD-3-Clause, with parts under 0BSD, MIT, Zlib and CC0-1.0 (their texts are in the wheel's
  numpy-2.4.6.dist-info/licenses/). Source: https://github.com/numpy/numpy.
- **SciPy** 1.18.0. BSD-3-Clause, with the notices of the parts it bundles (Qhull, DOP, duccfft, uarray) in the
  wheel. Source: https://github.com/scipy/scipy.
  - **OpenBLAS** 0.3.31, in SciPy's wheel (scipy.libs/libopenblas.so). BSD-3-Clause.
    Source: https://github.com/OpenMathLib/OpenBLAS.
- **python-soundfile** 0.12.1. BSD-3-Clause. Source: https://github.com/bastibe/python-soundfile.
  Its compiled module (_soundfile.abi3.so) is linked with:
  - **libsndfile** 1.2.0. LGPL-2.1-or-later: https://github.com/libsndfile/libsndfile/blob/1.2.0/COPYING.
    Source: https://github.com/libsndfile/libsndfile/releases/tag/1.2.0.
  - **mpg123** 1.26.2. LGPL-2.1: https://www.mpg123.de/. Source:
    https://sourceforge.net/projects/mpg123/files/mpg123/1.26.2/.
  - **LAME** 3.100. LGPL-2.0-or-later: https://lame.sourceforge.io/. Source:
    https://sourceforge.net/projects/lame/files/lame/3.100/.
  - **libFLAC** 1.4.2, **libogg**, **libvorbis** 1.3.7 and **libopus** 1.3.1, by the Xiph.Org Foundation and
    contributors. BSD-3-Clause. Source: https://github.com/xiph/flac, https://github.com/xiph/ogg,
    https://github.com/xiph/vorbis, https://github.com/xiph/opus.

  To use the module with a changed or newer version of one of these libraries, build it again from Pyodide's
  recipes (above) with that library's source.
- **cffi** 2.0.0. MIT. Source: https://github.com/python-cffi/cffi.
- **pycparser** 3.0. BSD-3-Clause. Source: https://github.com/eliben/pycparser.
- **python-cmudict** 1.1.3, in the program's bundle (songbird.zip) with its licence (cmudict-1.1.3.dist-info).
  Its code is GPL-3.0-or-later (https://www.gnu.org/licenses/gpl-3.0.html; the source is what is served).
  Source: https://github.com/prosegrinder/python-cmudict. The **CMU Pronouncing Dictionary** it holds is
  BSD-2-Clause, Copyright (C) 1993-2015 Carnegie Mellon University (cmudict/data/LICENSE).
  Source: https://github.com/cmusphinx/cmudict.
- **WORLD**, as world/world.wasm with its licence beside it (world/LICENSE.txt): see above.

## Not redistributed

- A rendition (a song's .flac) carries only the project's own program, under CC0. Its requirements.txt names what
  the program needs (numpy, scipy, numba, soundfile, cmudict); running it fetches those from PyPI, under their own
  licences. A checkout installs its dependencies the same way (pyproject.toml, uv.lock).
- The tools that made the voice run outside the repository and aren't part of it: SoulX-Singer (Apache-2.0,
  https://github.com/Soul-AILab/SoulX-Singer), whose renders of the project's songs taught the learned throat
  (docs/THROAT.md), and the Montreal Forced Aligner (MIT, https://github.com/MontrealCorpusTools/Montreal-Forced-Aligner).
