# s02_voice's own data

`uv run python tools/promo/video/prep/s02_voice.py` writes `renders/promo/video/data/s02/`:

- `phones-line1.json`: verse 1 line 1's phones from `throat/lead-0.00.phones.json` (the take heard there), each with
  the throat's continuous inputs from the captured call (`renders/promo/capture/sing-000.pkl`, `t`): `pos0`/`pos1`
  (position through the phone at its first and last 5 ms frame), `dur` (natural log of seconds), `stress`, `level`,
  `lf0` (natural log of Hz) at the phone's middle frame. The scene shows these raw, as the throat receives them.
- `wave-arp`, `wave-synthpad`: int16 samples of `stems/<part>.wav` from 8.4125 to 33.4125 s (scale 1/32768).
- `weights-index` uint16 [984, 1020]: for each pixel of `throat/weights`, the column of `throat/act-verse1` its weight
  is multiplied by (inp/out/convs/mixes: the weight's column; phone/role: its row; films: the singer number);
  65535 a bias (times 1), 65534 `singer.weight` (times 0), 65533 no weight.
- `weights-array` uint8 [984, 1020] and `weights-arrays.json`: each pixel's array, and per array `light`
  (act-verse1's `light_scale`; a bias's own 99.5th percentile of |bias|) and `size` (99.5th percentile of |weight|).

In the browser: the harp's strings are re-run from `physics/pluck-harp` with the loop and shape formula in
prep/DATA.md (harp.js); the weights are lit per frame on the GPU as `weight x act-verse1[row, column]`
(weights.js), with singer_picture.py's amount and colours.
