#!/bin/sh
# Build world/world.wasm (WORLD's Harvest and CheapTrick: glue.cpp and pyworld 0.3.5's own sources in src/) with
# zig's clang for wasm32-wasi: zig's libc for the maths, an allocator of its own (alloc.h), its own memory (not
# Pyodide's), no C++ runtime.
#   ZIG="uv run --with ziglang==0.16.0 python -m ziglang" sh web/studio-wasm/world/build.sh
# Then record what it was built from: uv run python web/studio-wasm/tools/world_sources.py --write
set -e
here=$(cd "$(dirname "$0")" && pwd)
out="$here/world.wasm"
${ZIG:-zig} cc -target wasm32-wasi -O2 -fno-exceptions -fno-rtti -I"$here" -I"$here/src" \
  -mexec-model=reactor -Wl,--strip-all -Wl,-z,stack-size=1048576 \
  -o "$out" "$here/glue.cpp" "$here/src/harvest.cpp" "$here/src/common.cpp" "$here/src/fft.cpp" \
  "$here/src/matlabfunctions.cpp"
ls -l "$out"
