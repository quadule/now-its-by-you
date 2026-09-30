#!/bin/sh
# Build wasm/kernels.wasm from wasm/kernels.c with any clang that targets wasm32 and has a wasm linker.
# Here: zig's (pip install ziglang; ZIG="python -m ziglang"), no libc, Pyodide's memory imported.
#   ZIG="path/to/python -m ziglang" sh web/studio-wasm/tools/build_wasm.sh [extra cflags, e.g. -msimd128]
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
${ZIG:-zig} cc -target wasm32-freestanding -O3 -nostdlib -fno-builtin-floor \
  -Wl,--no-entry -Wl,--import-memory -Wl,--export-dynamic -Wl,--strip-all \
  "$@" -o "$here/wasm/kernels.wasm" "$here/wasm/kernels.c"
ls -l "$here/wasm/kernels.wasm"
