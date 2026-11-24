// The lead and the three choir voices as four strands across the width, each on its own line of the page: the
// pitch its throat was told (throat/<call>.lf0, 200 a second) about the voice's own middle, 9 units a semitone, over
// the strand's window of the song (now at 0.62 of the width, 4.5 s behind, 2.5 s ahead), broken where the voice
// rests; its weight the voice's stem level (data/s08/bridge, RMS). The choir's lines come out of the lead's in turn
// as the line begins.
import { clamp, smoothstep, mix } from '../../core/math.js';

const CALLS = ['lead-0.70', 'choir2', 'choir1', 'choir3'];
const PARTS = ['voice', 'choir2', 'choir1', 'choir3'];
export const VOICE_ASSETS = [...CALLS.flatMap((c) => [`throat/${c}.lf0`, `throat/${c}.flags`]), 's08/bridge'];
const AT = 0.62, BACK = 4.5, AHEAD = 2.5, SEMI = 9;
const LANES = [300, 452, 592, 712];

const midi = (lf0) => 69 + 12 * Math.log2(Math.exp(lf0) / 440);
let MID = null;

export function drawVoices(ctx, t, target, ink, { alpha = 1, open = [1, 1, 1, 1] } = {}) {
  const W = ctx.size.w;
  const arr = CALLS.map((c) => ({ lf0: ctx.data.get(`throat/${c}.lf0`), flags: ctx.data.get(`throat/${c}.flags`) }));
  const rate = arr[0].lf0.rate, n = arr[0].lf0.rows;
  const B = ctx.timeline.byId('bridge');
  // each voice's middle over the bridge, so each sits on its own line
  if (!MID) MID = arr.map((a) => {
    let s = 0, c = 0;
    for (let f = Math.floor(B.t0 * rate); f < Math.min(B.t1 * rate, n); f++) {
      const fl = a.flags.raw[f], v = a.lf0.values[f];
      if (fl & 1 && !(fl & 2) && Number.isFinite(v)) { s += midi(v); c++; }
    }
    return s / Math.max(c, 1);
  });
  const env = ctx.data.get('s08/bridge'), en = env.shape[2];
  const level = (v, s) => {
    const f = Math.floor((s - env.t0) * env.rate), row = env.parts.indexOf(PARTS[v]);
    return f < 0 || f >= en ? 0 : clamp((env.values[(row * 2 + 1) * en + f] + 34) / 26);
  };
  const X = (s) => W * (AT + (s - t) / (BACK + AHEAD));
  const f0 = Math.max(Math.floor((t - BACK) * rate), 0), f1 = Math.min(Math.ceil((t + AHEAD) * rate), n - 1);
  const GAP = Math.round(0.14 * rate);
  CALLS.forEach((c, v) => {
    const a = arr[v], o = open[v];
    if (o <= 0) return;
    const lane = v ? mix(LANES[0], LANES[v], o) : LANES[0];
    const runs = [];
    let run = [], last = null, since = 0;
    for (let f = f0; f <= f1; f++) {
      const fl = a.flags.raw[f], val = a.lf0.values[f];
      let y = null;
      if (fl & 1 && !(fl & 2) && Number.isFinite(val)) { last = midi(val); since = 0; y = last; }
      else if (last !== null && !(fl & 2) && ++since <= GAP) y = last;
      else last = null;
      if (y === null) { if (run.length > 1) runs.push(run); run = []; continue; }
      run.push([X(f / rate), lane - (y - MID[v]) * SEMI, f / rate]);
    }
    if (run.length > 1) runs.push(run);
    const lead = v === 0;
    for (const r of runs) {
      const now = r.findIndex((p) => p[2] >= t);
      ctx.g.stroke(target, r.map((p) => [p[0], p[1]]), {
        width: (i) => (lead ? 2.2 + 5.5 * level(v, r[i][2]) : 1.5 + 4 * level(v, r[i][2])),
        color: ink.ink,
        alpha: (i) => alpha * o * (now < 0 || i <= now ? 1 : 0.3) * smoothstep(0, 0.1, r[i][0] / W) * smoothstep(0, 0.08, (W - r[i][0]) / W),
      });
    }
  });
}
