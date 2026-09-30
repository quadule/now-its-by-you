#!/bin/sh
# The public studio's start: the synthesis the image compiled copied where it can be added to (a style
# nobody chose at build time compiles on first use, and is kept for the next start), then the studio.
# Its arguments come after these: --allow-host NAME, --machine, --limit NAME=N (docker-compose.yml).
set -e
export NUMBA_CACHE_DIR=/data/numba
mkdir -p "$NUMBA_CACHE_DIR"
cp -R /opt/numba-cache/. "$NUMBA_CACHE_DIR"/ 2>/dev/null || true
exec songbird studio --public --host 0.0.0.0 --port 8766 --no-open "$@"
