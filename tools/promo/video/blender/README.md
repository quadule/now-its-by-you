# The closing shot (Blender)

The tag and ring, film frames 8455 to 9073 (140.9125 s to the end of the file): the camera starts square on the
seed packet's face, the paper filling the 16:9 frame (the title band and the daisy's head), and pulls back in
one move with a slight arc to the right and a drop, to the released cover widened to 16:9. It eases in from rest
over about a second, travels through the eleven "la"s, settles by 148.0 s and holds still to the end.

The set is the released cover's: `renders/review/artwork/cover-golf.blend` (the golf setting; `now-its-by-you.png`
is its finished render). It is opened, saved at once as `renders/promo/video/blender/shot.blend`, and only that
copy is changed. The cover's files are never written.

## Files

- `shot.py`: builds the camera and its move, extends the set, sets Cycles, saves `shot.blend`, writes
  `corners.json`, renders. Options are in its docstring.
- `contact.py`: twelve previz frames across the move on one sheet.
- `finish_look.py`: the cover's after-Blender finish (fall-off and grain), for judging look frames only.
- `render_full.sh`, `proxy.py`: the detached full render and its JPEG proxies.
- `flicker.py`: frame-to-frame change in a run of frames.

Outputs in `renders/promo/video/blender/`: `shot.blend`, `corners.json` (1920x1080; other sizes write
`corners-WxH.json`), `previz/` (every 6th frame, 960x540, and `contact.png`), `look/` (frames 8455, 8630, 9073
at 1920x1080, final samples, raw and `-finished`), `frames/` (the final render), `tmp/` (Blender's temporary files).

## The full render

`render_full.sh` runs it detached (it survives the shell), 1920x1080, 16-bit PNG, raw, resumable, logging to
`renders/promo/video/blender/render.log`, with `proxy.py` writing 960x540 JPEG proxies (quality 90) to
`renders/promo/video/blender/proxy/` as frames finish:

```
cd /home/milo/Code/songbird && setsid nohup sh tools/promo/video/blender/render_full.sh > /dev/null 2>&1 < /dev/null &
```

It runs:

```
TMPDIR=$PWD/renders/promo/video/blender/tmp \
  blender -b renders/review/artwork/cover-golf.blend -P tools/promo/video/blender/shot.py -- \
  --res 1920x1080 --samples 384 --frames 8455:9073 --format png16 \
  --out renders/promo/video/blender/frames --resume
```

That writes `renders/promo/video/blender/frames/frame_008455.png` … `frame_009073.png` (619 frames, about
13 MB each, 8 GB). `--resume` skips frames already there, so running it again picks up where it stopped. For
2160p, `--res 3840x2160 --out renders/promo/video/blender/frames-2160` (it also writes `corners-3840x2160.json`);
`--format exr` gives half-float DWAA EXRs instead.

Settings: 384 samples, adaptive at 0.006, OpenImageDenoise on the GPU with albedo and normal passes and the
accurate prefilter, one fixed noise seed for every frame, motion blur over half a frame. f/16 at frame 0 opening
to f/4.5 at rest, so the background is as soft as the cover's (whose camera stood at half the distance at f/8).
On the RTX 4080 SUPER, about 5 GB of VRAM: 1080p 10 to 18 s a frame, about 2.3 h for the shot; 2160p 30 to 41 s
a frame, about 6 h.

`flicker.py` measures frame-to-frame change in a run of consecutive frames; `look/run-mid-8615.mp4` and
`look/run-hold-8990.mp4` are two such 30-frame runs.

## Colour and finish

Rendered as the cover was: Khronos PBR Neutral, exposure -0.35, white balance 6800 K tint 8, no look. The frames
are raw: the cover's after-Blender steps (`tools/cover/finish.py`) are left to the 2D compositor, to match the
cover:

1. Lens fall-off in linear light: multiply by `1 - 0.16 * r^2.4`, `r = hypot((x - w/2)/(w/2), (y - h/2)/(h/2)) / sqrt(2)`
   (1 at the corners).
2. Grain after the return to sRGB: a unit normal field, Gaussian-blurred by sigma 0.6 px, scaled to std 0.006
   (of full scale), the same in every channel. For video, a new field each frame.

## corners.json

Per film frame: `corners_px`, the face's corners (u,v) = (0,0), (1,0), (1,1), (0,1) in pixels (x right, y down
from the top-left), and `H_uv_to_px`, the homography from the face's UV square (u = x/3825, v = y/4950 of
`renders/review/artwork/cover/front-color.png`) to pixels. The paper bows by a few millimetres, so at frame 0 the
homography is off by up to 15 px (mean 5 px) inside the frame; for the first 2 s `grid_px` gives the face's true
points on a 17 x 21 UV grid for a mesh warp. Also: `frame_size`, `fov_h_deg` and `fov_v_deg` (50 mm on a 36 mm
sensor), `crop_uv_frame0` (the UV under the frame's corners at frame 0, about u 0.024 to 0.975, v 0.072 to
0.486), and the move's timing.

## Credits space

At rest, the lower quarter of the frame, below the packets' feet, is paving in soft shade across the full width
(the shade of something out of frame behind the camera, its edge creeping 12 mm toward the packets over the
shot). Set credits there, centred.
