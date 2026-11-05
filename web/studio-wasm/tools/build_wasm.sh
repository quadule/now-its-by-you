#!/bin/sh
# Build wasm/kernels.wasm and wasm/kernels-simd.wasm from wasm/kernels.c with any clang that targets wasm32 and
# has a wasm linker. Here: zig's (pip install ziglang; ZIG="python -m ziglang"), no libc, Pyodide's memory imported.
#   ZIG="path/to/python -m ziglang" sh web/studio-wasm/tools/build_wasm.sh [extra cflags for both]
# The committed modules were built by ziglang 0.16.0 (uv run --with ziglang==0.16.0 python -m ziglang).
#
# kernels-simd.wasm is the same kernels with -msimd128, which adds the one written for SIMD (matmul_blas, under
# __wasm_simd128__) and nothing else: the compiler's own vectorizing is off, so every other kernel is the same
# instructions as in kernels.wasm. A browser without wasm SIMD gets kernels.wasm (wasm/kernels.mjs).
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
build() {
  out=$1
  shift
  ${ZIG:-zig} cc -target wasm32-freestanding -O3 -nostdlib -fno-builtin-floor \
    -Wl,--no-entry -Wl,--import-memory -Wl,--export-dynamic -Wl,--strip-all \
    "$@" -o "$here/wasm/$out" "$here/wasm/kernels.c"
  ls -l "$here/wasm/$out"
}
build kernels.wasm "$@"
build kernels-simd.wasm -msimd128 -fno-vectorize -fno-slp-vectorize "$@"
