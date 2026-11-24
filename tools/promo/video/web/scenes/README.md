# Writing a scene

A scene is a folder here, `sNN_name/`, whose `index.js` default-exports one object. The list of scenes in
song order is `index.js` in this folder. Each placeholder draws the same five things (the ground, the parts'
lanes, the strand, the sung line, its labels) with the shared helpers in `core/draw.js`: copy one to start.

```js
import { ground, lyric, strand } from '../../core/draw.js';

export default {
  id: 's02_voice',                 // the folder's name
  section: 'verse1',               // a section id from timeline.json, or [first, last]
  enter: { kind: 'cut' },          // how the film comes into this scene (below)
  assets: ['throat/envelope'],     // data files loaded before init: names ending .json as JSON, others as .bin arrays
  async init(ctx) {},              // build buffers, textures, caches (once)
  async prepare(ctx, t) {},        // optional: fetch what render(t) needs that is not loaded yet (an image frame)
  render(ctx, t, target) {         // draw song time t into target; pure in t
    ground(ctx, t, target);
    strand(ctx, t, target);
    lyric(ctx, t, target);
  },
  light(ctx, t) {},                // optional: the paper amount this scene wants at t (0 stage .. 1 paper)
  raw(ctx, t) {},                  // optional: 0..1, how much of the final grade, grain, bloom, vignette to bypass
  finish(ctx, t) {},               // optional: 0..1, the cover's finish (lens fall-off and grain, tools/cover/finish.py)
  anchor(ctx, t) {},               // optional: the strand's state where this scene hands over (points, width, colour)
  resize(ctx) {},                  // optional: rebuild what is sized to the frame (the preview resizes; renders do not)
};
```

## Light, raw frames, the cover's finish

- `light(ctx, t)` replaces `timeline.paper(t)` for this scene: verse 2 can go dark for its wall of screens,
  the bridge's last line dark to one ember. Read the amount with `ctx.k(t)` (never `timeline.paper`): every
  helper in `core/draw.js` does, and `palette.inks(ctx.k(t))` gives the inks for it. The final pass grades
  (bloom, vignette, fibre) by the drawing scenes' amounts, blended as the transition blends their pictures.
- `raw(ctx, t)` 1: the frame passes the final pass untouched but for dither (Blender frames, studio captures).
- `finish(ctx, t)` 1: the cover's finish over the frame: lens fall-off in light (`1 - 0.16 r^2.4`, r = 1 at
  the corners), then grain (Gaussian, blurred by sigma 0.6 px, std 0.006 in display values, the same in
  every channel, a new field each frame). Raw and finish blend across transitions like light.

## Images, meshes, depth, the daisy

- `await ctx.data.image('/art/front-color.png')` -> `{tex, width, height}` (PNG, JPEG, WebP; decoded once, cached;
  in `init` or `prepare`). `/art/` is renders/review/artwork/cover/, `/studio/` and `/blender/` the renders.
  Draw it with `ctx.g.rects(target, [{x, y, w, h}], {texture: img.tex, srgb: true})`.
- `ctx.data.images(dir, pattern, {count, proxy, keep})`: `await seq.texture(i)` (in `prepare`) -> `{tex, ...}`;
  the preview reads `proxy` (same file names) when given, capture always reads `dir`.
- `ctx.g.mesh(target, tex, grid, {cols, rows, alpha, tint, srgb = true, uv})`: grid is cols x rows points in
  design units, row by row from the top (a 17 x 21 grid: cols 17, rows 21); or exactly 4 corners (top left, top
  right, bottom right, bottom left) drawn in true perspective.
- `ctx.camera`: `new Camera({position, target, up = [0, -1, 0], fov, size: ctx.size})`, `cam.project(p)` ->
  `{x, y, depth, scale, visible}`; `stroke3(g, target, cam, points, {width, alpha, color, intensity, fog: [near, far]})`,
  `strokes3(g, target, cam, [{points, ...}])` (far to near), `points3(g, target, cam, [{p, r, color, ...}], {fog})`.
  Widths and radii are world units; fog fades alpha to 0 between its distances.
- `ctx.daisy.daisy(ctx, target, {x, y, height, growth, k, alpha})`: the cover's woodcut daisy, (x, y) the foot
  of its stem, `height` the whole woodcut (it reaches 0.19 x height below the foot), `growth` 0 (the crack) to 4
  (stem, leaves, back petals, front petals and disc), `k` the paper amount. Cached by growth in 1/120 steps:
  the same arguments give the same pixels. `ctx.daisy.daisyAnchor(ctx, {x, y, height})` -> root, stem top, disc.
- The lyric's turning word: `draw.lyric(ctx, t, target, {focus: 'italic' | 'red'})` (or `type.lyric(line,
  {focus})` with `drawLyric(..., {focusInk})`) sets the timeline's `focus` syllables apart; off by default.

## Transitions

`enter: {kind, beats | bars, align, from}`. `kind` is `cut` (on the bar line nearest the section's start),
`dissolve` (even to the eye) or `ink` (a front spreading from `from`, design units, bottom left by default,
its edge shaped by noise). `align` places the transition against the section's first downbeat: `end` (the
default: the new scene is whole on the downbeat), `center` or `start`. The film draws a scene from its own
transition's start to the end of the next scene's, so a scene must look right a bar either side of its section.

## The context

| | |
|---|---|
| `ctx.g` | `core/gl.js`: `stroke(target, points, {width, alpha, color, intensity, blend})` (the strand and every curve: width and alpha may be functions of the point index), `points(target, [{x, y, r, color, alpha, intensity, soft}])`, `rects(target, [...], {texture, srgb})` (untextured rects read a 1x1 white texture, never the target), `mesh(target, tex, grid, {cols, rows})`, `target(w, h)`, `program(key, frag)`, `pass(target, program, uniforms)`, `texture(canvasOrBitmap, {mips, anisotropy})` (anisotropy N: mipmaps with anisotropic filtering where the extension exists; off by default), `g.gl` (raw WebGL2) |
| `ctx.type` | `text(str, {role, size})` (roles `lyric`, `label`, `numeral`), `draw(target, sprite, x, y, {color, align, valign})`, `lyric(line, {size, maxWidth})`, `drawLyric(target, lay, t, x, y, {ink, lit})`, `current(lay, t)` (the syllable sung now, with its rect) |
| `ctx.palette` | `inks(k)` (ground, ink, ink2, red, rule, sung, cold, card for paper amount k), `lin.<token>`, `hand(datum)`, `light(k)`, `side(k)`, `mix(a, b, k)` |
| `ctx.timeline` | `section(t)`, `byId(id)`, `line(t)`, `lineOf(section, i)`, `syllable(t)`, `bar(t)`, `beat(t)`, `human(t)`, `paper(t)`, `entry(part)`, `gain(part, t)` (the stage's level as the engine plays it: a null point is silent, the first and last points held, linear in gain between points, 1 for a part with no curve; `capture/check_levels.mjs` checks it), `level(part, t)` (the same in dB, -Infinity where silent), `daisyStage(t)`, `barLength`, `beatLength` |
| `ctx.score` | `notes(part)`, `sounding(part, t, release)`, `range(part, t0, t1)`, `last(part, t)`, `lead(t)`, `parts` |
| `ctx.data` | `get(name)` (an asset loaded for this scene), `json(name)`, `array(name)`, `image(url)`, `images(dir, pattern, {count, proxy})` (await `texture(i)` in `prepare`) |
| `ctx.k(t)` | the paper amount this scene draws with (its `light`, else the record's) |
| `ctx.camera`, `ctx.daisy` | `core/camera.js`, `core/daisy.js` (above) |
| `ctx.label(key)` | this scene's label from `web/copy.json` (a missing key throws) |
| `ctx.anchor(id, t)` | the neighbour scene `id`'s `anchor` at t, so the strand continues across the cut |
| `ctx.draw` | `core/draw.js`: `ground`, `lyric`, `label`, `cues`, `title`, `strand` (`alpha` option, default 1), `strandPoints`, `lanes` |
| `ctx.math`, `ctx.prng(seed)`, `ctx.hash(...)`, `ctx.rand(...)` | eases, smoothstep, spline; seeded randomness |
| `ctx.size` | `{w, h}` the frame in design units (1920 x 1080 at 16:9), `px` device pixels per unit, `W, H` device pixels |

Coordinates are design units, y down, so a 4K render is the same frame at twice the detail. Colours are
linear light; a value over 1 is light and blooms while the ground is dark. Draw the ground first
(`ground(ctx, t, target)`): edges of lines, dots and letters are blended over it as ink on a page.

## Rules

- The paper amount comes from `ctx.k(t)`; nothing in a scene reads `timeline.paper(t)`.
- Times come from `ctx.timeline` and the score: no number of seconds in a scene. Durations of fades are
  beats or bars (`ctx.timeline.beatLength`).
- Banned: `Math.random`, `Date`, `performance.now`, `requestAnimationFrame`, timers, CSS animation, `<video>`,
  DOM for pixels, and any state carried from one `render` call to the next. A frame is drawn at any time in
  any order and must come out the same. Something with a past (a ringing string) is simulated from its
  note's start at a fixed step and cached by note.
- Words: the sung lyric from the timeline, labels from `copy.json`. Colours: palette tokens only;
  `palette.hand(datum)` only for what a person chose. On paper: flat ink, hairlines, no glow (the final
  pass blooms only on the stage).
- Allocate in `init` (targets, textures, typed arrays), not per frame.

## Looking at one scene

- Preview: `http://127.0.0.1:8860/?scene=s02_voice&t=12.5` (the `video` entry in `.claude/launch.json`, or
  `node tools/promo/video/capture/serve.mjs`). Space plays; arrows step a frame (shift: a bar).
- Stills, exactly as rendered: `node tools/promo/video/capture/still.mjs --out renders/promo/video/out/stills-s02 --scene s02_voice a=12.5 b=f900`
- A transition between any two scenes: `still.mjs ... "x=13@ink:s02_voice:s09_broadside:0.5:125"`
  (kind, from, to, how far, the second scene's own time).
- A clip: `node tools/promo/video/capture/render.mjs --from 600 --to 1200 --out renders/promo/video/out/s02.mp4`
