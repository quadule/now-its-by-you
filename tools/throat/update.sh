#!/bin/sh
# Bring the learned throat's training set up to date with whatever the corpus render has finished:
# WORLD features, MFA alignment, the quality check, then the frame-by-frame dataset (dev only).
#
#   tools/throat/update.sh [--jobs N]
set -e
cd "$(dirname "$0")/../.."
JOBS=${1:-6}
uv run --no-sync python -B -W ignore tools/throat/features.py --jobs "$JOBS" | tail -1
uv run --no-sync python -B -W ignore tools/throat/align.py --jobs "$JOBS" | tail -1
uv run --no-sync python -B -W ignore tools/throat/check.py | head -1
uv run --no-sync python -B -W ignore tools/throat/dataset.py | head -1
