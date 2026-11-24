// Turn 2: every part that sounds in the turn as its own strand of sound, drawn back into one band, the release mix,
// and pressed into the one strand: the file. Used by s07_gather, and by s08_lineage while it dissolves in.
//
// Each part's strand is its stem's peak envelope (data/s08/turn, 240 a second) over the strand's window of the song
// (now at 0.62 of the width, 4.5 s behind, 2.5 s ahead), hatched in ink either side of its lane. The lanes lie on a
// sheet seen in perspective, the upper ones nearer and heavier; the camera rises over the turn, so the sheet tips
// away and the lanes close up in depth. Where they meet the knot, the mix leaves it as one heavy band.
import { Segs } from './lines.js';
import { clamp, smoothstep, mix, ease } from '../../core/math.js';

export const GATHER_ASSETS = ['s08/turn'];

const AT = 0.62, BACK = 4.5, AHEAD = 2.5;
// high to low, voices in the middle
const ORDER = ['whistle', 'whistle~', 'fiddle', 'fiddle~', 'harp', 'harp~', 'harp#', 'arp', 'lute', 'guitar', 'guitar~',
  'voice', 'choir1', 'choir2', 'choir3', 'synthpad', 'drone', 'drum', 'drum~', 'drummachine', 'drummachine#', 'bass', 'bass~', 'synthbass'];
const TOP = 170, BOTTOM = 800, Y = 540;
let G = null;

function prepare(ctx) {
  const turn = ctx.data.get('s08/turn');
  if (G && G.turn === turn) return G;
  const tl = ctx.timeline, t0 = tl.byId('turn2').t0, t1 = tl.byId('turn2').t1;
  const n = turn.shape[2], idx = (p) => turn.parts.indexOf(p);
  // the parts that sound in the turn: a stem whose peak passes -50 dB in it
  const heard = ORDER.filter((p) => {
    const i = idx(p);
    if (i < 0) return false;
    for (let f = Math.floor((t0 - turn.t0) * turn.rate); f < Math.min((t1 - turn.t0) * turn.rate, n); f++) if (turn.values[(i * 2) * n + f] > -50) return true;
    return false;
  });
  G = { turn, n, heard, idx, mixRow: turn.parts.indexOf('mix'), segs: new Segs(), edge: new Segs() };
  return G;
}

// the peak at song time s of part row r, as a height 0..1
function amp(G, r, s) {
  const f = (s - G.turn.t0) * G.turn.rate;
  if (f < 0 || f >= G.n - 1) return 0;
  const i = Math.floor(f), v = G.turn.values[(r * 2) * G.n + i];
  return clamp((v + 48) / 44) ** 1.4;
}

// lane i of n on the sheet at tilt d (0 face on .. 1 steep): its offset from the strand on screen and its nearness
function lane(i, n, d) {
  const v = n > 1 ? (i / (n - 1)) * 2 - 1 : 0;         // -1 top (near) .. 1 bottom (far)
  const z = 1 + v * mix(0.1, 0.35, d);                  // depth, 1 at the strand
  const y = (v - mix(0.12, 0.25, d)) / z;
  // fitted to TOP..BOTTOM about the strand
  const yTop = (-1 - mix(0.12, 0.25, d)) / (1 - mix(0.1, 0.35, d)), yBot = (1 - mix(0.12, 0.25, d)) / (1 + mix(0.1, 0.35, d));
  const s = Math.min((Y - TOP) / -yTop, (BOTTOM - Y) / Math.max(yBot, 1e-3));
  return { y: y * s, near: 1 / z };
}

// The gather at t. Returns the strand's points at y 540 (the rest pose) for the caller's own use.
export function gather(ctx, t, target, { alpha = 1 } = {}) {
  const P = prepare(ctx), tl = ctx.timeline, k = ctx.k(t), ink = ctx.palette.inks(k);
  const T0 = tl.byId('turn2').t0, T1 = tl.byId('turn2').t1, beat = tl.beatLength, bar = tl.barLength;
  const W = ctx.size.w;
  // out of rest over the first two beats; a knot sweeps from the right edge to the left over the second bar, the
  // parts converging into it and the mix leaving it; pressed into the line on the last beat
  const spread = ease.inOutCubic(clamp((t - T0) / (2 * beat)));
  const sweep = ease.inOutSine(clamp((t - (T0 + bar - 0.5 * beat)) / (bar - beat)));
  const K = mix(W + 260, -900, sweep);
  const press = 1 - ease.inOutCubic(clamp((t - (T1 - beat)) / beat));
  const flat = Math.min(spread, press);
  const tilt = ease.inOutSine(clamp((t - T0) / (T1 - T0)));
  const rest = ctx.draw.strandPoints(ctx, t, { y: Y });
  const restY = (x) => {
    const pts = rest.points, i = clamp(Math.round(((x - pts[0][0]) / (pts[pts.length - 1][0] - pts[0][0])) * (pts.length - 1)), 0, pts.length - 1);
    return pts[i][1];
  };
  const centre = (x) => mix(restY(x), Y, flat);
  const X = (s) => W * (AT + (s - t) / (BACK + AHEAD));
  const n = P.heard.length;
  P.segs.clear(); P.edge.clear();
  // a strand of sound: ink hatching between its edges, the edges as lines; y(x) its axis, w(x) its share there
  const band = (row, y, w, a, wide, weight, step) => {
    if (a <= 0.002) return;
    const ds = (step / W) * (BACK + AHEAD);
    let prev = null;
    for (let s = t - BACK; s <= t + AHEAD; s += ds) {
      const x = X(s), ww = w(x);
      const future = s > t ? 0.55 : 1;
      const h = amp(P, row, s) * ww * wide * press;
      const fade = smoothstep(0, 0.08, x / W) * smoothstep(0, 0.08, (W - x) / W);
      const aa = a * future * fade * Math.min(ww * 3, 1);
      const yy = y(x);
      if (h > 0.5 && aa > 0) P.segs.add(x, yy - h, x, yy + h, weight * 0.75, weight * 0.75, aa, aa);
      if (prev && (aa > 0 || prev[3] > 0)) {
        P.edge.add(prev[0], prev[1] - prev[2], x, yy - h, weight, weight, prev[3], aa);
        P.edge.add(prev[0], prev[1] + prev[2], x, yy + h, weight, weight, prev[3], aa);
      }
      prev = [x, yy, h, aa];
    }
  };
  // the parts fan out to the left of the knot, each on its lane, and close into it
  const fan = (x) => smoothstep(K, K - 1100, x);
  const into = (x) => smoothstep(K - 300, K + 30, x);
  P.heard.forEach((p, i) => {
    const L = lane(i, n, tilt);
    band(P.idx(p), (x) => centre(x) + L.y * spread * fan(x), (x) => 1 - into(x), alpha, 18 * L.near, 1.1 + 1.3 * (L.near - 0.6), 3.2);
  });
  // the mix: the one band they make
  band(P.mixRow, centre, (x) => into(x) * (sweep > 0 ? 1 : 0), alpha, 150, 2.2, 3.2);
  P.segs.draw(ctx, target, { color: ink.ink });
  P.edge.draw(ctx, target, { color: ink.ink });
  // the knot, where they become one
  if (sweep > 0 && sweep < 1 && K > -40 && K < W + 40) {
    const ky = centre(K);
    ctx.g.points(target, [{ x: K, y: ky, r: 4.5, color: ink.ink, alpha: alpha * press }]);
  }
  // the strand itself: the lead's line, there throughout, the axis each band is drawn about
  ctx.g.stroke(target, rest.points.map(([x]) => [x, centre(x)]), { width: 2.5, color: ink.cold, alpha });
  return rest;
}
