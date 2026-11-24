# s08 data (prep/s08_file.py → renders/promo/video/data/s08/)

Run `uv run python tools/promo/video/prep/s08_file.py` from the repo root. It reads the release FLAC, the stems, `stems/mix.env`,
`packet.json` and `throat/weights`, all through `common.guard`.

- `file.json`: the release file. `frames`: each of the 1,629 FLAC frames' byte offsets, found in order by their headers
  (fixed blocking, frame number checked, CRC-8 checked; the first equals the audio's offset, 70,260); `block` 4096 samples.
  `entries`: all 129 zip entries (name, offset, data_offset, compressed, size, method), `header` the local header's
  bytes as hex, `text` the first 2,400 characters of each text entry as the zip holds it (null for cover.jpg and
  throat.npz). `manifest`: packet.json's identity fields.
- `mix-bands` uint8 [9074, 9], 60 a second: the release mix's RMS (column 0) and eight bands (each the power sum of
  12 of mix.env's 96), dB = v / 2.55 - 100.
- `turn` uint8 [25, 2, 3360], 240 a second from 90.4 s: each stem's peak and RMS (stem order, then the FLAC's own mix).
- `bridge` uint8 [4, 2, 5040], 240 a second from 100.4 s: voice, choir1-3 stems' peak and RMS.
- `weights` uint8 [492, 510]: the throat's weights as ink, |w| over its tile's 99.5th percentile, clipped, ** 0.8,
  the max of each 2 x 2.
