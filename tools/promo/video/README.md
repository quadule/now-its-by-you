# The music video

A film of the awards performance draft (`renders/release/now-its-by-you-awards-draft.flac`, audio id
eb8fb05eb2bb, 151.227 s) drawn from the program's own data. Every frame is a pure function of its
time in the song. The storyboard is `/home/milo/.claude/plans/sharded-fluttering-valley.md`.

## Rules for everyone building it

- Everything lives here (`tools/promo/video/`) and in `renders/promo/video/`. No edits to
  `songbird/`, `web/`, `webstudio/`, `tools/` outside this folder, or any other branch or worktree.
  No commits. Other sessions work in this checkout.
- Big files go under `renders/promo/video/` (on disk). `/tmp` is a 16 GB RAM disk: nothing large there.
- Never read anything under `renders/measured/` (private, per singer). `prep/` refuses such paths.
- Never run the full pytest suite. Targeted checks only.
- Every picture comes from the program's data at that moment of the song. If a shape is re-simulated
  in the browser, it uses the model's captured parameters and the README of the data says so.
- Words on screen: the sung lyric (from the score, never retyped) and labels from `web/copy.json`.
  A label is the simplest true statement, in capitals, a few words. No sentences, no flourish.
- Dates people read are US style (November 14, 2026).
- Code comments say what is. No history, no dates, no "no longer".

## Layout

```
prep/      Python that writes renders/promo/video/data/   (run with `uv run python tools/promo/video/prep/X.py`)
  DATA.md  every data file: what it is, where it came from, exact format
web/       the film: index.html (preview), core/, scenes/sNN_name/, copy.json
capture/   node: serve.mjs (the one local server), preflight.mjs, render.mjs, still.mjs, hash.mjs, check.mjs,
           browser.mjs (Chromium through playwright-core in capture/node_modules), fixture.py, studio_*.mjs
blender/   shot.py (the closing shot)
renders/promo/video/   data/  studio/  blender/  frames/  out/  scratch/
```

## Time

- 60 frames a second, 9,074 frames, frame i is at t = i / 60 seconds of the audio file.
- Sections (seconds): intro 0.9125, verse1 10.9125, refrain1 30.9125, turn1 50.9125, verse2 55.9125,
  refrain2 75.9125, turn2 95.9125, bridge 100.9125, refrain3 120.9125, tag 140.9125 to 146.5875;
  the file rings on to 151.227. A bar is 2.5 s (96 BPM, 4/4). B major (tonic MIDI 59).
- No scene writes a number of seconds. Times come from `core/timeline.js`, which reads `timeline.json`.

## Data contract (the two files the core needs; all others are specified in prep/DATA.md)

Binary arrays are `<name>.bin` (little-endian, C order) beside `<name>.json`:
`{"dtype": "uint8|int16|float32", "shape": [...], "rate": frames per second or null, "t0": seconds of row 0,
"scale": s, "offset": o, "about": "..."}`; a stored value v means `v * scale + offset`.

`data/timeline.json`
```
{ "duration": 151.227, "fps": 60, "frames": 9074, "tempo": 96, "bar": 2.5, "tonic": 59, "key": "B major",
  "sections": [{"id": "verse1", "kind": "verse", "t0": 10.9125, "t1": 30.9125}, ...],
      ids in order: intro verse1 refrain1 turn1 verse2 refrain2 turn2 bridge refrain3 tag ring
  "bars": [t, ...], "beats": [t, ...],
  "lines": [{"section": "verse1", "i": 0, "t0": s, "t1": s, "text": "They saved it as numbers and sent it by wire,",
             "human": 0.0,
             "words": [{"text": "They", "t0": s, "t1": s,
                        "syllables": [{"text": "They", "t0": s, "t1": s, "pitch": 54, "focus": false}]}]}],
  "human": [[t, h], ...],            the record's human amount, a step at each line's start
  "entries": [{"part": "harp", "t": 25.63, "kind": "player|twin|layer|voice|choir"}],   first sounding note
  "levels": {"<part>": [[t, dB|null], ...]},   the stage's level curves: null is silent; the engine fades
                                     linearly in amplitude (10^(dB/20), null 0) between points, first and last
                                     held; a part with no curve is at 0 dB throughout
  "daisy": [{"t": 110.92, "dur": 1.24, "pitch": 90, "degree": "so"}, ...]   the whistle's four notes
  "stems": ["lute", ..., "drummachine#"]   every part's name, in the replay's stem order
}
```

`data/score.json`
```
{ "parts": { "<part>": [{"t": start, "d": dur, "p": midi pitch, "v": vel 0..1, "syl": str|null, "word": str|null,
                         "sec": section id, "phrase": str, "art": str, "g": gesture object|null,
                         "a": the part's level over the note (most linear gain; 0: not heard),
                         "h": the take's human amount (voice only)}, ...] },
  "stems": [...] }     the same list as timeline.json's
```
Parts are the score's own (voice, choir1-3, lute, guitar, harp, bass, fiddle, whistle, drum, drone) plus the
stage's twins and layers under the stem names the replay gives them. A part's notes are all the notes its stem
plays, heard or not: a twin plays its player's notes the whole song and is heard only where its level is up
(`a`). `voice` is the lead as heard: in each span of the stage plan, the notes of the take sung there.

## Preview and render

- Preview: the `video` entry in `.claude/launch.json` (`node tools/promo/video/capture/serve.mjs`, port 8860),
  then `http://127.0.0.1:8860/`: the song is the clock, a scrubber, section buttons, a scene menu, space
  plays. `?t=SECONDS`, `?scene=sNN_name`, `?capture=1&w=&h=` (no chrome). It needs WebGL2 (Chrome, Firefox).
- `/data/` serves `renders/promo/video/data/`; a file not there yet is answered from
  `renders/promo/video/scratch/fixture/` (`capture/fixture.py` builds a stand-in timeline and score).
  `/art/` serves renders/review/artwork/cover/ (the packet face art), `/studio/` and `/blender/` the renders.
- `node tools/promo/video/capture/preflight.mjs`: which Chromium flags reach the GPU, and its speed.
- `node tools/promo/video/capture/render.mjs --from F --to F --out FILE [--w --h --subframes N --shards K --check --codec x265]`
  (frames [from, to), to exclusive): FFV1 intermediate in `renders/promo/video/frames/<name>/`, master with the
  FLAC's audio (x265 Main 10 by default; `--codec x264` for 8-bit). `--check` stamps the frame index and reads
  it back from both files. `--reencode` makes a new master from a render's intermediate.
- `capture/still.mjs` (PNG stills, as rendered), `capture/hash.mjs` (a frame's SHA-256, for determinism).

## Colour, type, look (tokens live in core/palette.js and core/type.js; scenes use tokens only)

| Token | Hex | Use |
|---|---|---|
| stage | #1b1611 | the dark ground |
| stageInk | #efe6da | light on the dark |
| cold | #8cafeb | the wire, the machine alone |
| sung | #f2b25c | amber: a sounding note, the coal |
| stageRed | #e0664d | red on the dark |
| paper | #f4ecdc | the light ground |
| card | #fbf7ee | a sheet lying on paper |
| ink | #2b231d | print |
| red | #a3361f | rubrics, the title band |
| hand | #2b4474 | indigo: only what a person chose (`palette.hand(datum)` demands the datum) |
| rule | #d6c8ae / #8f7d66 | hairlines |
| daisyYellow, daisyGreen | #dea833, #98a36b | the cover's inks, used by the daisy alone |
| stageHand, stageInk2, stageRule | #a9c2ea, #c9bba4, #3d3429 | indigo, second ink and hairline on the dark (docs/IDENTITY.md's dark scheme) |
| ink2, ink3, wash, ruleStrong | #554737, #6b5c4b, #ebe0c9, #8f7d66 | the house's lighter inks and wash |

- `paper(t)` in `core/timeline.js` is the record's human amount over 0.75, eased across about 0.8 s:
  0 is all stage, 1 is all paper. A scene may set its own (`light`); scenes read theirs with `ctx.k(t)` and
  choose inks with `palette.inks(ctx.k(t))`.
- The ground does not pass through grey. Below `palette.FLIP` (0.6: human 0.45, the frame drum's line at
  40.6 s) the stage warms like a page under a lamp; across it the light comes up onto paper; above it the
  paper whitens. The inks change sides at the flip, so text is legible at every amount the record holds.
  `palette.light(paper)` is the ground's lightness; the final pass grades with it (bloom and vignette as it
  is low, the paper's fibre as it is high).
- Glow and bloom exist only where `paper(t)` is low. On paper: flat ink, hairlines, woodcut line,
  2 px corners at most, no gradients, shadows or rounded pills.
- Type is Georgia, loaded from the system files as the private family `Film Serif` (regular, italic,
  bold). Roles: `lyric` (the sung line), `label` (letterspaced small capitals, as the house sets kickers and
  rubrics: Georgia's old-style figures sit at their height), `numeral` (figures in equal-width cells).
  Letters are rasterised at the frame's device size and placed on whole pixels.
- One strand runs through the film: the wire, the string, the pitch line, the file's bytes, the
  daisy's stem. A scene receives the strand's state from its neighbour through its `anchor`.

## Scene contract

`web/scenes/sNN_name/index.js` default-exports

```js
{ id, section,            // a section id from timeline.json, or [first, last]
  enter: {kind, beats | bars, align, from},  // the transition into it: 'cut' (on the bar), 'dissolve', 'ink'
  assets: [...],          // data files it needs, loaded by core/data.js before init
  async init(ctx) {},     // build buffers, textures, caches
  async prepare(ctx, t),  // optional: fetch what render(t) needs (an image frame)
  render(ctx, t, target), // draw the frame at song time t into target (a framebuffer); pure in t
  light(ctx, t),          // optional: its own paper amount (default timeline.paper); read it with ctx.k(t)
  raw(ctx, t), finish(ctx, t),  // optional 0..1: bypass the final grade (photographs); the cover's lens and grain
  anchor(ctx, t)          // optional: the strand's state where it hands over; a neighbour reads ctx.anchor(id, t)
}
```

A scene draws from its own transition's start to the end of the next scene's (this replaces `pre`/`post`).
`ctx` gives `g` (core/gl.js: strokes, points, rects, meshes), `gl`, `timeline`, `score`, `palette`, `type`, `data`
(JSON, arrays, images, image sequences), `draw` (core/draw.js), `camera` (core/camera.js), `daisy` (core/daisy.js),
`k(t)` (the scene's paper amount), `math`, `prng(seed)`, `label(key)`, `anchor(id, t)`, `size`. The final pass
grades by the drawing scenes' paper, raw and finish amounts, blended with the transition. `web/scenes/README.md` has the details.
Banned inside a scene: `Math.random`, `Date`, `performance.now`, `requestAnimationFrame`, CSS animation,
`<video>`, and any state carried from one `render` call to the next. Anything that needs a past
(a string ringing) is simulated from its note's start at a fixed step and cached by note.
A scene's folder belongs to its builder; `core/` is shared and changes only through the core's owner.
