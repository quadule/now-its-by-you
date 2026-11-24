// The bridge: the file as one strand of bytes to scale (the song, then at its byte the program that sings it); the
// file passing machine to machine as a tree of versions with the coal on its newest branch; the three choir voices
// beside the lead's; the light going until one ember is left. The daisy comes up at the lower right on the
// whistle's four notes.
import { ground, lyric, label } from '../../core/draw.js';
import { Camera } from '../../core/camera.js';
import { clamp, smoothstep, mix, ease } from '../../core/math.js';
import { FILE_ASSETS, model, drawFile } from './file.js';
import { GATHER_ASSETS, gather } from './gather.js';
import { tree, drawTree, coalAt } from './tree.js';
import { VOICE_ASSETS, drawVoices } from './voices.js';
import { drawRecord, cornerFor } from './record.js';
import { drawJoin, RULE } from './join.js';

const LOG = Math.log;
// the daisy: foot of the stem, height (s09_broadside draws it at the same place, full grown)
export const DAISY = { x: 1690, y: 1010, height: 300 };

const lines = (tl) => [0, 1, 2, 3].map((i) => tl.lineOf('bridge', i));

// The camera along the strand through line 1: the whole file face on, margin to margin; from two beats in, one
// continuous move down into the join, the join's place on screen easing to the rule's place on the page; the page
// of the join grows out of the byte as the camera nears it and is whole on the second bar line, held there.
export function fileView(ctx, t) {
  const m = model(ctx), tl = ctx.timeline, B0 = tl.byId('bridge').t0, bar = tl.barLength, beat = tl.beatLength;
  const focal = (ctx.size.h / 2) / Math.tan((35 * Math.PI) / 360);
  const Z0 = (focal * (m.end - m.start)) / (ctx.size.w - 80), ZL = 30;
  const go = ease.inOutCubic(clamp((t - (B0 + 2 * beat)) / (bar - 2 * beat)));
  const Z = Math.exp(mix(LOG(Z0), LOG(ZL), go));
  const x0 = ctx.size.w / 2 + (focal * (0 - (m.start + m.end) / 2)) / Z0;
  const xj = mix(x0, RULE[0], go);
  const target = [((ctx.size.w / 2 - xj) * Z) / focal, 0, 0];
  const cam = new Camera({ position: [target[0], 0, Z], target, fov: 35, size: ctx.size, near: Z * 1e-3 });
  return { cam, H: Z * 0.11, Z, join: [xj, 540], s: ZL / Z };
}

// The view of the tree: through line 2 close on the coal (ZC), the coal held near ANCHOR, so each hand-over moves
// the picture; over line 2's last three beats opening to the whole tree, which fills the frame from then on.
const ZC = 1.75, ANCHOR = [700, 600];
function treeView(ctx, t) {
  const tl = ctx.timeline, T = tree(ctx), L3 = tl.lineOf('bridge', 2), beat = tl.beatLength;
  const b = 1 - ease.inOutCubic(clamp((t - (L3.t0 - 0.3 - 3 * beat)) / (3 * beat)));
  if (b <= 0) return { O: [0, 0], Z: 1 };
  // the focus: the coal's place over the last 0.4 s, so the camera eases after it
  let fx = 0, fy = 0;
  for (let i = 0; i < 8; i++) { const c = coalAt(T, t - (0.4 * i) / 7); fx += c.x / 8; fy += c.y / 8; }
  return { O: [b * (ANCHOR[0] - fx * ZC), b * (ANCHOR[1] - fy * ZC)], Z: mix(1, ZC, b) };
}

// how far the light has gone: 0 through line 3, 1 from a bar into line 4 to the end
function dark(ctx, t) {
  const L4 = ctx.timeline.lineOf('bridge', 3);
  return ease.inOutSine(clamp((t - (L4.t0 - 0.2)) / (1.2 * ctx.timeline.barLength)));
}

// labels at the upper left, one at a time, each for its idea
const LABELS = [
  { key: 'file', slot: 0, from: (tl) => tl.byId('turn2').t0, to: (tl) => tl.byId('bridge').t0 + tl.beatLength },
  { key: 'song', slot: 0, from: (tl) => tl.byId('bridge').t0 + tl.beatLength + 0.05, to: (tl) => tl.byId('bridge').t0 + tl.barLength },
  { key: 'program', slot: 0, from: (tl) => tl.byId('bridge').t0 + tl.barLength + 0.05, to: (tl) => tl.byId('bridge').t0 + 2 * tl.barLength },
  // while the root is alone: once a child exists, the card's own generation carries it
  { key: 'generation', slot: 0, from: (tl) => tl.byId('bridge').t0 + 2 * tl.barLength + 0.05, to: (tl, ctx) => tree(ctx).nodes[1].t + 0.3 },
];

// when each version goes out in the dark: from the tips inward (by height, then deepest first), spread over line 4
// from its first syllable to its last; the root never
let OUT = null;
function outTimes(ctx) {
  const T = tree(ctx);
  if (OUT && OUT.T === T) return OUT.map;
  const L4 = ctx.timeline.lineOf('bridge', 3);
  const syl = ctx.score.range('voice', L4.t0 - 0.05, L4.t1).filter((n) => n.a > 0);
  const h = new Map();
  const height = (n) => {
    if (h.has(n.i)) return h.get(n.i);
    const v = n.kids.length ? 1 + Math.max(...n.kids.map((c) => height(T.nodes[c]))) : 0;
    h.set(n.i, v);
    return v;
  };
  const order = T.nodes.filter((n) => n.i > 0).sort((a, b) => height(a) - height(b) || b.gen - a.gen || b.t - a.t);
  const a = syl[0].t, b = syl[syl.length - 1].t;
  const map = new Map();
  order.forEach((n, i) => map.set(n.i, a + ((b - a) * i) / Math.max(order.length - 1, 1)));
  OUT = { T, map };
  return map;
}

export default {
  id: 's08_lineage',
  section: 'bridge',
  enter: { kind: 'dissolve', beats: 2 },
  assets: ['packet.json', ...FILE_ASSETS, ...GATHER_ASSETS, ...VOICE_ASSETS],
  async init(ctx) { model(ctx); tree(ctx); },

  light(ctx, t) {
    return ctx.timeline.paper(t) * (1 - dark(ctx, t));
  },

  render(ctx, t, target) {
    const tl = ctx.timeline, k = ctx.k(t), ink = ctx.palette.inks(k), B0 = tl.byId('bridge').t0, beat = tl.beatLength;
    const [, L2, L3, L4] = lines(tl);
    ground(ctx, t, target, k);
    if (t < B0) {
      // before the downbeat: the turn's gather, as s07_gather draws it, so the dissolve joins
      gather(ctx, t, target);
    } else {
      // line 1: the file, then the join; on line 2 the whole shrinks into the tree's root, the file being its own generation
      const v = fileView(ctx, t), T0 = tree(ctx).nodes[0], tv = treeView(ctx, t);
      const shrink = ease.inOutCubic(clamp((t - (L2.t0 - 0.35)) / (2 * beat)));
      if (shrink < 1) {
        const grow = ease.outCubic(clamp((t - B0) / beat));
        const fileA = 1 - smoothstep(0.12, 0.55, v.s);
        if (fileA > 0) drawFile(ctx, target, v.cam, v.H, ink, { grow, alpha: fileA, program: 1 - smoothstep(0.002, 0.012, v.s) });
        if (grow < 1) {
          // the rest strand the band opens out of
          const rest = ctx.draw.strandPoints(ctx, t, { y: 540 });
          ctx.g.stroke(target, rest.points, { width: 2.5, color: ink.cold, alpha: 1 - grow });
        }
        const js = Math.min(v.s, 1) * Math.exp(mix(0, LOG(0.004), shrink));
        const at = [mix(v.join[0], tv.O[0] + T0.x * tv.Z, shrink), mix(v.join[1], tv.O[1] + T0.y * tv.Z, shrink)];
        drawJoin(ctx, target, ink, { s: js, at, alpha: smoothstep(0.004, 0.03, v.s) * (1 - smoothstep(0.75, 1, shrink)) });
      }
      // lines 2 to 4: the tree of versions
      const D = dark(ctx, t);
      const treeA = smoothstep(L2.t0 - 0.05, L2.t0 + 0.1, t) * mix(1, 0.05, smoothstep(L3.t0 - 0.3, L3.t0 + 0.5, t) * (1 - D));
      if (treeA > 0) {
        const T = tree(ctx), out = outTimes(ctx), tip = T.trunk[T.trunk.length - 1];
        const c = drawTree(ctx, t, target, ink, {
          alpha: treeA, glow: D, view: tv,
          out: (n) => (n.i === 0 ? 0 : smoothstep(out.get(n.i), out.get(n.i) + 0.45, t)),
          coal: 1 - smoothstep(out.get(tip.i), out.get(tip.i) + 0.3, t),
        });
        // the record of the version the coal is on, through line 2 until the view opens to the whole tree
        const open = L3.t0 - 0.3 - 3 * beat;
        const recA = treeA * smoothstep(L2.t0 - 0.1, L2.t0 + 0.4, t) * (1 - smoothstep(open - 0.1, open + 0.4, t));
        if (recA > 0) {
          const i = T.trunk.indexOf(c.node), leave = (n) => Math.min(T.trunk[T.trunk.indexOf(n) + 1]?.t ?? Infinity, open);
          const k = cornerFor(ctx, T, c.node, leave(c.node), (s) => treeView(ctx, s));
          const k0 = i > 0 ? cornerFor(ctx, T, T.trunk[i - 1], leave(T.trunk[i - 1]), (s) => treeView(ctx, s)) : k;
          drawRecord(ctx, t, target, ink, c, recA, k, k0, i > 0 ? T.trunk[i - 1] : null);
        }
        // the ember: the root, this file, glowing with the song's level as the rest go out
        if (D > 0) {
          const e = clamp((ctx.data.get('s08/mix-bands').at(t)[0] + 40) / 30), root = T.nodes[0];
          ctx.g.points(target, [{ x: root.x, y: root.y, r: 4.6 + 1.6 * D, color: ink.red, alpha: D, intensity: 1.6 + 1.4 * e * D, soft: D }]);
        }
      }
      // line 3: the three choir voices beside the lead's
      const vA = smoothstep(L3.t0 - 0.35, L3.t0 + 0.1, t) * (1 - smoothstep(L4.t0 + 0.2, L4.t0 + 2.2, t));
      if (vA > 0) drawVoices(ctx, t, target, ink, { alpha: vA, open: [0, 1, 2, 3].map((i) => (i ? ease.inOutCubic(clamp((t - (L3.t0 + (i - 1) * 0.5 * beat)) / (1.5 * beat))) : 1)) });
      // the rest pose on the last beat: the strand drawn out of the ember, faint in the dark
      const end = tl.byId('bridge').t1, r = smoothstep(end - beat, end, t);
      if (r > 0) {
        const rest = ctx.draw.strandPoints(ctx, t, { y: 540 });
        ctx.g.stroke(target, rest.points, { width: 2.5, color: ink.cold, alpha: r * 0.5 });
      }
    }
    // the daisy: one stage per whistle note, each taking three quarters of its note; full grown from the last on
    const ds = tl.daisyStage(t);
    if (ds.n > 0) {
      const first = tl.daisy[0];
      ctx.daisy.daisy(ctx, target, { ...DAISY, growth: ds.n - 1 + clamp(ds.k / 0.75), k,
        alpha: smoothstep(first.t, first.t + 0.12, t) * mix(1, 0.34, dark(ctx, t)) });
    }
    for (const L of LABELS) {
      const from = L.from(tl, ctx), to = L.to(tl, ctx);
      const a = smoothstep(from, from + 0.4, t) * (1 - smoothstep(to - 0.4, to, t));
      if (a > 0) label(ctx, t, target, L.key, { alpha: a, y: 120 + L.slot * 40, k });
    }
    lyric(ctx, t, target, { k });
  },
};
