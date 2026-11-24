# s03_instruments: its own data

Written by `prep/s03_twins.py` (`uv run python tools/promo/video/prep/s03_twins.py` from the repo root), under
`renders/promo/video/data/s03/`.

- `twin-synthbass`, `twin-arp`, `twin-drummachine` (`.bin` + `.json`, int16, `scale` 1/32768, `rate` 44100,
  `t0` the first sample's time): the outgoing synth's own stem samples (`stems/<part>.wav`) from a bar before to a
  bar after the moment its level falls silent on refrain 1's first three lines (the bass comes in as the layer's
  synth bass stops, the guitar as the arp stops, the frame drum as the drum machine stops). Extra keys: `player`,
  `synth`, `silent_at` (the level curve's null point, seconds).
- `twins.json`: the same three as a list.

The scene re-runs everything else in the browser from `physics/` (prep/DATA.md): the pluck loops of the harp, bass and
guitar (`pluck.js`), the drum's 196 modes (`skin.js`), the strumming hand's strokes (`strum.json`).
