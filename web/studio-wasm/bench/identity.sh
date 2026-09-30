#!/bin/sh
# The browser's renders against the server's, for several versions: each spec made and rendered natively (the
# server's way, bench/spec_native.py), then rendered from the built bundle in Pyodide under node (node/spec_run.mjs,
# the same Python, kernels and packages as the worker in Chrome), and the two compared sample by sample.
#
#   sh web/studio-wasm/bench/identity.sh BUNDLE_DIR OUT_DIR
set -e
BUNDLE=$1
OUT=$2
mkdir -p "$OUT"
cd "$(dirname "$0")/../../.."
run() {  # name song which edits
  uv run python web/studio-wasm/bench/spec_native.py "$2" "$3" "$4" --spec "$OUT/$1.json" --out "$OUT/$1.native.flac" > "$OUT/$1.native.txt"
  node web/studio-wasm/node/spec_run.mjs "$BUNDLE" "$OUT/$1.json" --out "$OUT/$1.browser.flac" > "$OUT/$1.browser.txt"
  echo "== $1 ($2 $3 $4)"
  grep "made in" "$OUT/$1.browser.txt"
  uv run python web/studio-wasm/tools/pcm_diff.py "$OUT/$1.native.flac" "$OUT/$1.browser.flac" | sed -n 2,4p
}
run h-turn h-now-its-by-you.json 2 '{}'
run h-refrain1-92 h-now-its-by-you.json 1 '{"tempo": 92}'
run h-turn2-roll2 h-now-its-by-you.json 5 '{"roll": 2}'
run b-section1 b-coal-from-the-fire.json 1 '{}'
run h-whole h-now-its-by-you.json whole '{}'
run h-whole-roll2 h-now-its-by-you.json whole '{"roll": 2}'
run b-whole b-coal-from-the-fire.json whole '{}'
run b-whole-70 b-coal-from-the-fire.json whole '{"tempo": 70, "band.pattern": "pick"}'
run h-refrain1-synthfolk h-now-its-by-you.json 1 '{"style.name": "synthfolk"}'
run b-whole-synthfolk b-coal-from-the-fire.json whole '{"style.name": "synthfolk"}'
