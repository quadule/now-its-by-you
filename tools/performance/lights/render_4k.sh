#!/bin/bash
# The film at 3840x2160 in four parts (a 4K intermediate for the whole film is about 70 GB, twice that while
# its shards are joined): each part rendered once (10-bit FFV1), encoded on the GPU to H.265 10-bit and to
# H.264 (NVENC, constant quantizer 10), its intermediate deleted; then the parts joined (stream copy) and the
# live mix laid under them.
set -euo pipefail
cd /home/milo/Code/songbird
R=renders/performance/lights/4k
N=10159
AUDIO=renders/promo/capture-live-A/render.flac
mkdir -p $R/hevc $R/h264
for k in 0 1 2 3; do
  a=$(( k * 2540 )); b=$(( (k + 1) * 2540 )); (( b > N )) && b=$N
  if [ ! -f renders/promo/video/frames/part$k/part$k.mkv ]; then
    node tools/promo/video/capture/render.mjs --from $a --to $b --w 3840 --h 2160 --codec hevc_nvenc --bits 10 --crf 10 --out $R/hevc/part$k.mp4
  else
    node tools/promo/video/capture/render.mjs --reencode --codec hevc_nvenc --bits 10 --crf 10 --out $R/hevc/part$k.mp4
  fi
  node tools/promo/video/capture/render.mjs --reencode --codec h264_nvenc --bits 10 --crf 10 --out $R/h264/part$k.mp4
  rm -r renders/promo/video/frames/part$k
done
for c in hevc h264; do
  printf "file '%s'\n" $PWD/$R/$c/part{0,1,2,3}.mp4 > $R/$c/parts.txt
  ffmpeg -v error -y -f concat -safe 0 -i $R/$c/parts.txt -i $AUDIO -map 0:v -map 1:a -c:v copy \
    -af apad -c:a aac -b:a 320k -ar 48000 -t 169.316667 -movflags +faststart $R/../film-4k-$c.mp4
done
mv $R/../film-4k-h264.mp4 $R/../film-4k.mp4
echo done
