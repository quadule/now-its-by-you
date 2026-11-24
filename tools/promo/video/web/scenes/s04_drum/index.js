// Breath 2: the frame drum, a struck skin. The voice rests and the drum plays its boom-tak: the open bass stroke on
// beats 1 and 3, the back hand's pressed top stroke on the eighth after each. The skin is re-run from its captured
// modes (physics/drum.json, physics/drum-modes; s03_instruments/skin.js) and drawn as refrain 1 draws it, an engraver's
// rings, with the top stroke's two lowest modes gliding down from sharp, and its pressing hand stopping what the boom
// still rings where it lands (the hit's choke, as the synth plays it).
//
// Time: the rings' decay and the chokes run on refrain 1's slow motion (Skin.shown: each hit's first moments slowed
// DRUM_RATE times, the rest of its ring passing quickly so the true time meets the next hit with the song). The modes'
// phases turn DRUM_RATE times slower than the skin throughout, a strobe, so the boom's fundamental is seen rising and
// falling as a dome (once across the eighth before the top stroke) instead of flickering as the ring runs fast.
// Each hit is scaled by its own gain, so the hard top strokes stand as loud as the part plays them; as its ring fades
// it is drawn larger (at most GROW times, so its size reads as at least FLOOR): the shape is the data's, only its size
// is raised, and a choke still takes away what it takes from the ring.
//
// The strand curls into the drum's rim over the first eighth, and opens back out to its rest line as s06 comes in.
import { ground, lyric, label, strandPoints } from '../../core/draw.js';
import { smoothstep, mix, clamp } from '../../core/math.js';
import { Camera } from '../../core/camera.js';
import { Skin, drawSkin } from '../s03_instruments/skin.js';
import { DRUM_RATE, P3, FOV, FOCAL } from '../s03_instruments/index.js';

const Y = 540;   // the strand's rest height
const FLOOR = 3, GROW = 16;
// refrain 1's drum, where it stood there: clear of the sung line's place below it
const D = P3.drum;

export default {
  id: 's04_drum',
  section: 'breath2',
  enter: { kind: 'cut' },
  assets: ['physics/drum.json', 'physics/drum-modes'],

  async init(ctx) {
    this.sec = ctx.timeline.byId('breath2');
    this.skin = new Skin(ctx.data.get('physics/drum.json'), ctx.data.get('physics/drum-modes'), { rate: DRUM_RATE });
    // each hit's gain against the median of the hits in the breath
    const g = this.skin.hits.filter((h) => h.t >= this.sec.t0 - 1e-3 && h.t < this.sec.t1).map((h) => h.gain).sort((a, b) => a - b);
    const ref = g.length ? g[g.length >> 1] : 1;
    this.gainOf = (hit, tau, h) => {
      const g = hit.gain / ref;
      return g * clamp(FLOOR / Math.max(g * this.skin.size(h, tau), 1e-9), 1, GROW);
    };
  },

  // refrain 1's frontal camera on the frame, drifting a little each bar
  camera(ctx, t) {
    const drift = (t - this.sec.t0) / ctx.timeline.barLength;
    const dx = -30 + 10 * drift;
    return new Camera({ position: [960 + dx, 540 - 0.12 * FOCAL, FOCAL], target: [960 + dx * 0.4, 540, 0], fov: FOV, size: ctx.size });
  },

  render(ctx, t, target) {
    const k = ctx.k(t), ink = ctx.palette.inks(k);
    ground(ctx, t, target);
    const beat = ctx.timeline.beatLength, t0 = this.sec.t0, t1 = this.sec.t1;
    // the strand into the rim over the first eighth; out of it to its rest line over the first beat of s06's dissolve,
    // so the two scenes draw the one rest strand (this scene's anchor) through the rest of it. The skin fades with
    // the dissolve's last beat, its own rim drawn as the strand leaves it.
    const into = smoothstep(t0, t0 + 0.5 * beat, t);
    const pull = into * (1 - smoothstep(t1 - 2 * beat, t1 - beat, t));
    const skin = into * (1 - smoothstep(t1 - beat, t1, t));
    const phaseOf = (hit) => Math.max(t - hit.t, 0) / DRUM_RATE;
    const rim = drawSkin(ctx, t, target, this.camera(ctx, t), this.skin, ink, skin, D, { gainOf: this.gainOf, phaseOf, rimAlpha: 1 - pull });

    // the strand: its rest line carried onto the rim, its two ends meeting at the rim's near side
    const rest = strandPoints(ctx, t, { y: Y });
    const n = rest.points.length, nowI = rest.points.findIndex((p) => p[0] >= rest.nowX);
    const M = rim.points.length - 1, pts = [], wid = [];
    for (let i = 0; i < n; i++) {
      const s = ((0.25 + i / (n - 1)) % 1) * M, a = Math.min(Math.floor(s), M - 1), w = s - a;
      const q = rim.points[a], q1 = rim.points[a + 1], r = rest.points[i];
      pts.push([mix(r[0], mix(q[0], q1[0], w), pull), mix(r[1], mix(q[1], q1[1], w), pull)]);
      wid.push(mix(2.5, 3.4 * mix(rim.scale[a], rim.scale[a + 1], w), pull));
    }
    // at rest it fades as core strand() fades it (into the past behind now, dim ahead); on the rim it is whole
    const restAlpha = (i) => (i <= nowI ? smoothstep(0, nowI * 0.6, i) : 0.28 * (1 - (i - nowI) / Math.max(n - nowI, 1)));
    ctx.g.stroke(target, pts, {
      width: (i) => wid[i], color: ctx.palette.mix(ink.cold, ink.ink, pull),
      intensity: mix(mix(1.35, 1, k), 1, pull), alpha: (i) => mix(restAlpha(i), 1, pull),
    });

    label(ctx, t, target, 'drum', { alpha: smoothstep(t0, t0 + beat, t) * (1 - smoothstep(t1 - beat, t1, t)) });
    lyric(ctx, t, target);
  },

  // the strand where s06 takes it: the rest line
  anchor(ctx, t) {
    return { points: strandPoints(ctx, t, { y: Y }).points, width: 2.5, color: ctx.palette.inks(ctx.k(t)).cold };
  },
};
