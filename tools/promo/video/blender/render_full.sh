#!/bin/sh
# The closing shot's full render, detached: 1920x1080, 16-bit PNG, raw, resumable; and its JPEG proxies.
#   setsid nohup sh tools/promo/video/blender/render_full.sh > /dev/null 2>&1 &
cd "$(dirname "$0")/../../../.." || exit 1
B=renders/promo/video/blender
export TMPDIR="$PWD/$B/tmp"
blender -b renders/review/artwork/cover-golf.blend -P tools/promo/video/blender/shot.py -- \
  --res 1920x1080 --samples 384 --frames 8455:9073 --format png16 --out $B/frames --resume >> $B/render.log 2>&1 &
RPID=$!
echo "blender pid $RPID started $(date -Is)" >> $B/render.log
python3 tools/promo/video/blender/proxy.py $RPID >> $B/proxy.log 2>&1
wait $RPID
echo "blender exited $? at $(date -Is)" >> $B/render.log
