// The tag and ring: the Blender photograph of the seed packet on the kerb in the sun, the camera pulling back from
// its face. For the first second the flat face of s09 lies over the bowed sheet on the shot's own grid and dissolves
// into the photograph; at the end, the credits in the shade across the paving. No lyric is set over the photograph:
// at the lyric's place the moving shot puts the daisy, its stem and the slab under the line for most of the tag.
import { smoothstep, clamp } from '../../core/math.js';
import { loadFace, drawFace, PRINTED } from '../s09_broadside/face.js';
import { JOIN_GAIN } from '../s09_broadside/join.js';

export default {
  id: 's10_cover',
  section: ['tag', 'ring'],
  enter: { kind: 'cut' },
  assets: ['text.json'],
  async init(ctx) {
    this.F = await loadFace(ctx);
    const first = this.F.first, count = this.F.corners.frames.length;
    this.seq = ctx.data.capture
      ? ctx.data.images('/blender/frames-1080/', 'frame_%06d.png', { count, first, keep: 6 })  // the shot's 8-bit copy
      : ctx.data.images('/blender/proxy/', 'frame_%06d.jpg', { count, first, keep: 12 });
    this.shown = new Map();
  },
  // the photograph for frame t, fetched before render; a frame not rendered yet shows the last one that is
  async prepare(ctx, t) {
    const i = this.index(ctx, t);
    if (this.shown.has(i)) return;
    let tex = null;
    try {
      tex = await this.seq.texture(i);
    } catch {
      let lo = 0, hi = i;
      while (hi - lo > 1) {
        const mid = (lo + hi) >> 1;
        try { await this.seq.texture(mid); lo = mid; } catch { hi = mid; }
      }
      tex = await this.seq.texture(lo).catch(() => null);
    }
    if (tex) this.shown.set(i, tex);
    while (this.shown.size > 4) this.shown.delete(this.shown.keys().next().value);
  },
  // the shot's first frame is on the tag's cut
  index(ctx, t) {
    const fps = ctx.timeline.fps;
    return clamp(Math.floor(t * fps + 1e-6) - Math.round(ctx.timeline.byId('tag').t0 * fps), 0, this.F.corners.frames.length - 1);
  },
  render(ctx, t, target) {
    const F = this.F, tl = ctx.timeline, fps = tl.fps;
    const i = this.index(ctx, t), frame = F.first + i;
    ctx.g.clear(target, [0, 0, 0, 1]);
    const img = this.shown.get(i);
    if (img) ctx.g.rects(target, [{ x: 0, y: 0, w: ctx.size.w, h: ctx.size.h }], { texture: img.tex, srgb: true });
    // the flat face over the sheet, on the shot's grid, dissolving into the photograph over the first second
    const a = this.overlay(ctx, t);
    if (a > 0 || !img) {
      F.rowsData.fill(1);
      F.titleData.fill(1);
      // between video frames the face rides the grid of the frame before and the one after
      const g0 = F.grid(frame), g1 = F.grid(frame + 1), k = t * fps - Math.floor(t * fps + 1e-6);
      const grid = new Float32Array(g0.length);
      for (let j = 0; j < grid.length; j++) grid[j] = g0[j] + (g1[j] - g0[j]) * k;
      drawFace(ctx, target, F, grid, PRINTED, { gain: JOIN_GAIN, alpha: img ? a : 1, feather: 8 });
    }
    this.credits(ctx, t, target);
  },
  // the flat face's opacity: whole on the cut, then gone by the second beat, before the crop's edges come in
  overlay(ctx, t) {
    const t0 = ctx.timeline.byId('tag').t0, b = ctx.timeline.beatLength;
    return 1 - smoothstep(t0 + 0.2 * b, t0 + 1.6 * b, t);
  },
  credits(ctx, t, target) {
    const tl = ctx.timeline, b = tl.beatLength, end = tl.duration;
    const at = end - 3.5;
    const a0 = smoothstep(at, at + 3 * b, t);
    if (a0 <= 0) return;
    const text = ctx.data.get('text.json');
    const ink = ctx.palette.lin.stageInk, ink2 = ctx.palette.lin.stageInk2;
    // the shade on the paving across the lower quarter (renders/promo/video/blender/look/frame_009073.png, rows 900
    // to 1080: about #0f2434), set to the shade's colour for the letters' edges
    const ground = [15, 36, 52].map((v) => ctx.palette.toLinear(v / 255));
    const cx = ctx.size.w / 2;
    const lines = [
      { s: ctx.type.text(ctx.label('title'), { role: 'lyric', size: 30 }), y: 878, color: ink, d: 0 },
      { s: ctx.type.text(ctx.label('volunteers'), { role: 'label', size: 15 }), y: 912, color: ink2, d: 1 },
      { s: ctx.type.text(text.credits.names.join('    ·    '), { role: 'lyric', size: 21 }), y: 950, color: ink, d: 2 },
      { s: ctx.type.text(text.credits.uncredited, { role: 'lyric', size: 17 }), y: 986, color: ink2, d: 2.5 },
      { s: ctx.type.text(ctx.label('site'), { role: 'lyric', size: 18 }), y: 1020, color: ink2, d: 3.5 },
    ];
    for (const l of lines) {
      const a = smoothstep(at + l.d * 0.5 * b, at + l.d * 0.5 * b + 3 * b, t);
      ctx.type.draw(target, l.s, cx, l.y, { color: l.color, alpha: a, align: 'center', ground });
    }
  },
  raw() { return 1; },
  finish() { return 1; },
  light() { return 1; },
};
