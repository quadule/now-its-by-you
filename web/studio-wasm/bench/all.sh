#!/bin/sh
# The numbers in docs/BROWSER-RENDER.md, one after another on one machine: native (numba, one thread) and
# Pyodide under node with the JS kernels and with the wasm ones, a section (H's first refrain) and the
# whole song, each with the process's peak memory. PCM goes to $OUT for tools/compare.py.
#   sh web/studio-wasm/bench/all.sh OUTDIR
set -e
OUT=${1:-/tmp/songbird-bench}
mkdir -p "$OUT"
cd "$(dirname "$0")/../../.."
SONG=songs/h-now-its-by-you.json
peak() { grep "maximum resident" | awk '{printf "  peak RSS %.0f MiB\n", $1 / 1048576}'; }
echo "== native section"; SONGBIRD_THREADS=1 /usr/bin/time -l uv run python web/studio-wasm/bench/native_section.py $SONG 2 "$OUT/native_2.npy" > "$OUT/native_2.log" 2>&1
grep -E "cold|warm" "$OUT/native_2.log"; peak < "$OUT/native_2.log"
echo "== native whole"; SONGBIRD_THREADS=1 /usr/bin/time -l uv run python web/studio-wasm/bench/native_section.py $SONG whole "$OUT/native_whole.npy" > "$OUT/native_whole.log" 2>&1
grep -E "cold|warm" "$OUT/native_whole.log"; peak < "$OUT/native_whole.log"
for k in js wasm; do
  echo "== pyodide $k section"; /usr/bin/time -l node web/studio-wasm/node/run.mjs --kernels $k --section 2 --reps 3 --out "$OUT/${k}_2.npy" > "$OUT/${k}_2.log" 2>&1
  grep -E "^load|^render" "$OUT/${k}_2.log" | cut -c1-160; peak < "$OUT/${k}_2.log"
  echo "== pyodide $k whole"; /usr/bin/time -l node web/studio-wasm/node/run.mjs --kernels $k --whole --reps 1 --out "$OUT/${k}_whole.npy" > "$OUT/${k}_whole.log" 2>&1
  grep -E "^render" "$OUT/${k}_whole.log" | cut -c1-160; peak < "$OUT/${k}_whole.log"
done
for k in js wasm; do
  echo "== compare $k section"; uv run python web/studio-wasm/tools/compare.py "$OUT/native_2.npy" "$OUT/${k}_2.npy" | grep -E "identical|differing"
  echo "== compare $k whole"; uv run python web/studio-wasm/tools/compare.py "$OUT/native_whole.npy" "$OUT/${k}_whole.npy" | grep -E "identical|differing"
done
uptime
