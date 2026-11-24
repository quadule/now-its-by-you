# s09_broadside and s10_cover: their data

## data/s09/ (prep/s09_face.py)

`uv run --with segno python tools/promo/video/prep/s09_face.py` from the repo root (about 90 s, 4 GB).

The seed packet's front face, printed again by `tools/cover/face.py`'s and `woodcut.py`'s own functions in
`print_face()`'s order with its seed (1966; the woodcut's 11), and kept as its plates instead of one image. Cropped to
the closing shot's frame-0 crop (`blender/corners.json` `crop_uv_frame0`, 0.004 of the face wider on each side):
3684 x 2091 px at face.py's 3 px a face unit, crop origin `crop_px` in face.json.

| file | channels |
|---|---|
| `paper.png` | RGB, sRGB: the paper before any ink (formation, fibres, flecks) |
| `handling.png` | L: the handling's multiplier on the printed sheet, `0.75 + v / 255 * 0.25` (grime, the dog-ear, the creases' dirt) |
| `sky.png` | R the sky's black as printed; G the sky's lines inside the roundel (cleared when the roundel prints); B the sky's lines under the daisy's fills (cleared when the daisy prints) |
| `black.png` | R the rules (two borders, the panel's frame); G the 51; B the daisy's black |
| `tints.png` | R white; G yellow; B green |
| `red.png` | R the title band as printed (title cut out; the seed house's name at the crop's top edge); G the red inside the title's letters; B the roundel's rings |
| `grey.png` | R MIN. and SEEDS; G concrete (its specks) |
| `face.json` | the crop, inks and opacities, register offsets, the sky's 72 hatch rows as vectors (y and each stretch's centre line and widths, face units, before the ribbon's wobble), the title's four words as crop-px column spans, the roundel, and `check` |

Covers are each plate's cover after face.py's press and the creases' cracks, 8-bit. Black and red are shared out
among their parts by where each part's marks lie; the hidden covers (G and B of sky.png, G of red.png) are the parts'
masks pressed with the same noise fields as their plate. Composite (linear light, face.py's formulas): tints multiply
`1 + (ink / paper - 1) * cover`; white (0.8), grey, red, black (0.97) lie over as
`c * (1 - a) + ink * a * (c / paper)^0.35`; then the handling multiplies. Order: concrete, green, yellow, white,
grey, red, black. `check`: these files composited so equal `renders/review/artwork/cover/front-color.png` in the crop
to a mean of 0.21 and a maximum of 2.5 of 255 (the cover's own image rounds at 0.5).

## Also read

- `daisy.json` (core): the woodcut daisy's marks, cut here into plates for the daisy that travels.
- `/blender/corners.json`: the face's 17 x 21 grid at frame 8455 lays the face in s09 and lands the daisy;
  each frame's grid lays the flat face over the photograph for s10's first second.
- line 1: `throat/lead-heard.env`, `stems/<part>.env` and `stems/mix.env`, `physics/pluck-<part>` and its notes,
  `physics/strum.json` (which string each guitar note is on); line 2: `text.json` bank; s10: `text.json` credits.
