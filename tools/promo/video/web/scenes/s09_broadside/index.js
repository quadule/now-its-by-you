// The broadside: full daylight paper. The sheet printed is the seed packet's face, one plate a line, and the last
// frame is the closing shot's first (s10_cover): the face's frame-0 crop, flat, on the shot's own grid.
//   line 1  every line of the film comes back in ink out of the strand and settles into the sky's hatching
//   line 2  the bank's 51 verses gather into the roundel: MIN. 51 SEEDS prints
//   line 3  from the sung "grows", the daisy grows from its corner into its place on the face and takes its inks
//   line 4  the red band prints, its title cut out syllable by syllable as "now it's by you" is sung
import { lyric, cues } from '../../core/draw.js';
import { smoothstep } from '../../core/math.js';
import { loadFace, drawFace, UNPRINTED } from './face.js';
import { Lines, LINE_ASSETS } from './lines.js';
import { Halo, LYRIC } from './halo.js';
import { Roundel } from './roundel.js';
import { Daisy } from './daisy.js';
import { Band } from './band.js';
import { JOIN_GAIN } from './join.js';

const LYRIC_SKY_Y = 420;   // the top of line 4's lyric: the sky between the band and the daisy's petals

export default {
  id: 's09_broadside',
  section: 'refrain3',
  // the daylight spreads from the daisy, where the bridge left its one light, on the section's downbeat: the dark
  // holds through the pickup and the light breaks on "owns"
  enter: { kind: 'ink', beats: 2, align: 'start', from: [1688, 832] },
  assets: [...LINE_ASSETS, 'text.json', 'daisy.json'],
  async init(ctx) {
    this.F = await loadFace(ctx);
    this.grid = this.F.grid(this.F.first);
    this.halo = new Halo();
    this.lines = new Lines();
    await this.lines.init(ctx, this.F, this.grid);
    this.roundel = new Roundel();
    this.roundel.init(ctx, this.F, this.grid);
    this.daisy = new Daisy();
    this.daisy.init(ctx, this.F, this.grid);
    this.band = new Band();
    this.band.init(ctx, this.F);
  },
  plates(ctx, t) {
    const L = this.lines;
    const st = { ...UNPRINTED };
    st.sky = 1;
    st.concrete = 1;
    const s = L.settle[L.strandRow] + L.settleDur;
    st.rules = smoothstep(s, s + 0.4 * ctx.timeline.beatLength, t);
    this.roundel.plates(t, st);
    this.daisy.plates(t, st);
    this.band.plates(t, st);
    return st;
  },
  render(ctx, t, target) {
    const F = this.F, L = this.lines;
    L.fill(t);
    this.band.fill(t);
    const paper = ctx.palette.inks(1).ground;
    ctx.g.clear(target, [paper[0], paper[1], paper[2], 1]);
    ctx.g.ground = F.paper;
    ctx.type.ground = F.paper;
    const st = this.plates(ctx, t);
    const R = this.roundel;
    const look = { off: { band: this.band.offset(t), roundel: R.offset(t, R.ringT, 7, -5) }, gain: this.gain(ctx, t) };
    drawFace(ctx, target, F, this.grid, st, look);
    L.draw(ctx, t, target);
    this.roundel.draw(ctx, t, target);
    cues(ctx, t, target, 'refrain3', [{ line: 1, key: 'verses' }]);
    const under = this.daisy.mask(ctx, t, target);
    if (under) drawFace(ctx, target, F, this.grid, { ...st, sky: 0 }, { ...look, mask: under });
    this.daisy.draw(ctx, t, target);
    // the sung line, in a clearing cut through the hatching; it never crosses the daisy: lines 3 and 4 stand in the
    // sky above the flower as it grows into its place
    const { la, y } = this.lyricPlace(ctx, t);
    const mask = la > 0 ? this.halo.mask(ctx, t, target, { focus: 'italic', alpha: la, y }) : null;
    if (mask) drawFace(ctx, target, F, this.grid, { ...st, sky: 0 }, { ...look, mask });
    if (la > 0) lyric(ctx, t, target, { focus: 'italic', size: LYRIC.size, y, maxWidth: LYRIC.maxWidth, alpha: la, hold: 0.6 });
  },
  lyricPlace(ctx, t) {
    const line = ctx.timeline.line(t);
    if (line && line.section === 'refrain3' && line.i === 3) return { la: this.band.lyricAlpha(t), y: LYRIC_SKY_Y };
    if (line && line.section === 'refrain3' && line.i === 2) return { la: 1, y: LYRIC_SKY_Y };
    // the tag's line, whose lead begins before the cut, is s10's
    return { la: line && line.section === 'refrain3' ? 1 : 0, y: LYRIC.y };
  },
  // the face's colour comes to the photograph's paper (join.js) over the last line, so the cut to s10 is seamless
  gain(ctx, t) {
    const k = smoothstep(this.band.printT, this.end(ctx), t);
    return JOIN_GAIN.map((v) => 1 + (v - 1) * k);
  },
  // the last frame drawn: the one before the closing shot's first
  end(ctx) {
    const tl = ctx.timeline;
    return (Math.ceil(tl.byId('tag').t0 * tl.fps) - 1) / tl.fps;
  },
  // over the last bar the face leaves the film's grade for the photograph's: no fibre or shoulder, the cover's lens
  raw(ctx, t) {
    const e = this.end(ctx);
    return smoothstep(e - ctx.timeline.barLength, e, t);
  },
  finish(ctx, t) { return this.raw(ctx, t); },
  light() { return 1; },
};
