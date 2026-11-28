// Turn 2: the whistle, a pipe. The strand opens into the whistle's bore, drawn from the instrumented pipe model
// (data/turn2, prep/turn2.py): the bore is one delay line a period long, so its length on screen is the note's
// period and the wave in it is the bore's own contents, newest at the mouth; the jet at the mouth flips across the
// labium with its captured deflection, its weight the captured breath; breath runs down the windway. Beneath, the
// fiddle's held string, quiet, its true shape from the instrumented bowed model.
//
// Slow motion, as s04_bow: the bore's wave goes round once a beat, the fiddle's corner once every two beats; each
// frame shows that frame's own period, read at that phase from its sixteen snapshots.
//
// In the last bar the bore closes back into the strand and every part gathers into one band, the file
// (s08_lineage/gather.js, which the bridge draws through its dissolve in).
import { ground, label, lyric, strand } from '../../core/draw.js';
import { clamp, smoothstep, mix, ease } from '../../core/math.js';
import { GATHER_ASSETS, gather } from '../s08_lineage/gather.js';

const CY = 540;            // the bore's axis: the strand's rest height
const R = 80;              // the bore's radius
const MX = 250;            // the mouth: where the bore begins
const WIND = 170;          // the windway's length, left of the mouth
const SLOT = 24;           // the windway's height, under the bore's top wall
const WINDOW = 84;         // the window from the windway's end to the labium's edge
const PX = 17;             // design units per sample of the bore's length
const FIDDLE = { y: 800, x0: 250, x1: 1760, scale: 2.6 };  // the string: nut (left) to bridge (right)

export default {
  id: 's07_gather',
  section: 'turn2',
  enter: { kind: 'cut' },
  assets: ['turn2/turn2.json', 'turn2/pipe-period', 'turn2/pipe-jet', 'turn2/pipe-tracks', 'turn2/fiddle-period', ...GATHER_ASSETS],

  async init(ctx) {
    const d = (n) => ctx.data.get(n);
    this.meta = d('turn2/turn2.json');
    this.bore = d('turn2/pipe-period');
    this.jet = d('turn2/pipe-jet');
    this.tracks = d('turn2/pipe-tracks');
    this.string = d('turn2/fiddle-period');
    [, this.S, this.NB] = this.bore.shape;
    this.NS = this.string.shape[2];
    this.amp = (0.8 * R) / this.meta.whistle.peak;
    this.wave = new Float32Array(this.NB);
    this.shape = new Float32Array(this.NS);
    // the breath's travel down the windway: its integral over the turn (tracks column 0), so the marks carried in
    // it move as fast as the player blows
    const tr = this.tracks, n = tr.rows, rl = tr.rowLength;
    this.travel = new Float64Array(n + 1);
    for (let i = 0; i < n; i++) this.travel[i + 1] = this.travel[i] + (tr.values[i * rl] * 260) / tr.rate;
    const rnd = ctx.prng(7107);
    this.marks = Array.from({ length: 26 }, () => ({ u: rnd() * WIND, v: rnd(), r: 0.7 + 0.8 * rnd() }));
  },

  frame(arr, t) { return arr.index(t); },

  // a track's value at t (linear between rows)
  track(t, c) {
    const tr = this.tracks, rl = tr.rowLength;
    const p = clamp((t - tr.t0) * tr.rate, 0, tr.rows - 1), i = Math.min(Math.floor(p), tr.rows - 2), w = p - i;
    return tr.values[i * rl + c] * (1 - w) + tr.values[(i + 1) * rl + c] * w;
  },

  // The bore at t into this.wave: frame f's period at the shown phase. Snapshot s is the bore s/S of a period on; between
  // two snapshots the delay line has moved on by a fraction u of a step, so the earlier one is read u steps back
  // and the few newest points come from the later one.
  boreAt(ctx, t) {
    const f = this.frame(this.bore, t), S = this.S, NB = this.NB, step = NB / S;
    const phi = ((((t - this.sec(ctx).t0) / ctx.timeline.beatLength) % 1) + 1) % 1;
    const q = phi * S, s0 = Math.floor(q) % S, u = q - Math.floor(q);
    const snap = (s) => this.bore.values.subarray((f * S + s) * NB, (f * S + s + 1) * NB);
    const read = (d, x) => {
      const i = clamp(Math.floor(x), 0, NB - 2), w = clamp(x - i, 0, 1);
      return d[i] * (1 - w) + d[i + 1] * w;
    };
    const a = snap(s0), b = snap((s0 + 1) % S), sh = u * step;
    for (let p = 0; p < NB; p++) this.wave[p] = p - sh >= 0 ? read(a, p - sh) : read(b, p - sh + step);
    const j = (s) => this.jet.values.subarray((f * S + s) * 3, (f * S + s + 1) * 3);
    const ja = j(s0), jb = j((s0 + 1) % S);
    return { f, jet: mix(ja[0], jb[0], u), flow: mix(ja[1], jb[1], u), period: ja[2] };
  },

  // the fiddle's string at t into this.shape: a period in slow motion, once every two beats
  stringAt(ctx, t) {
    const f = this.frame(this.string, t), S = this.S, NS = this.NS;
    const phi = ((((t - this.sec(ctx).t0) / (2 * ctx.timeline.beatLength)) % 1) + 1) % 1;
    const q = phi * S, s0 = Math.floor(q) % S, s1 = (s0 + 1) % S, u = q - Math.floor(q);
    const base = (s) => (f * S + s) * NS;
    for (let p = 0; p < NS; p++) this.shape[p] = mix(this.string.values[base(s0) + p], this.string.values[base(s1) + p], u);
    return this.shape;
  },

  sec(ctx) { return ctx.timeline.byId('turn2'); },

  render(ctx, t, target) {
    const tl = ctx.timeline, k = ctx.k(t), ink = ctx.palette.inks(k), g = ctx.g;
    const { t0: T0 } = this.sec(ctx), beat = tl.beatLength, bar = tl.barLength;
    ground(ctx, t, target, k);
    // out of the strand over the first beat; back into it over the last bar's second and third beats, as the
    // parts gather
    const open = ease.inOutCubic(clamp((t - T0) / beat)) * (1 - ease.inOutCubic(clamp((t - (T0 + bar + beat)) / (1.5 * beat))));
    const gat = smoothstep(T0 + bar + 0.5 * beat, T0 + bar + 2 * beat, t);

    // the strand, giving way to the bore where the bore lies
    const st = ctx.draw.strandPoints(ctx, t, { y: CY });
    const b = this.boreAt(ctx, t);
    const L = Math.max(b.period, 1) * PX * open, xEnd = MX + L;
    const restY = (x) => {
      const pts = st.points, i = clamp(Math.round(((x - pts[0][0]) / (pts[pts.length - 1][0] - pts[0][0])) * (pts.length - 1)), 0, pts.length - 1);
      return pts[i][1];
    };
    const sa = (1 - open) * (1 - gat);
    if (sa > 0) strand(ctx, t, target, { y: CY, width: 2.5, alpha: sa, k });

    if (open > 0.001) {
      const r = R * open, top = CY - r, bot = CY + r, slot = SLOT * open, wx = MX - WIND * open;
      const wall = { width: 2, color: ink.ink, alpha: open };
      // the bore's walls; the window in the top wall from the windway's end to the labium, the far end open
      g.stroke(target, [[MX + WINDOW * open, top], [xEnd, top]], wall);
      g.stroke(target, [[wx, bot], [xEnd, bot]], wall);
      // the windway over the plug, the labium's edge a wedge facing the jet
      g.stroke(target, [[wx, top], [MX, top]], wall);
      g.stroke(target, [[wx, top + slot], [MX, top + slot], [MX, bot]], { ...wall, width: 1.4 });
      g.stroke(target, [[wx, top + slot], [wx, bot]], { ...wall, width: 1.4 });
      const lx = MX + WINDOW * open;
      g.stroke(target, [[lx + 30 * open, top + 9 * open], [lx, top]], { ...wall, width: 1.4 });

      // the breath down the windway: marks carried at its integral, as many as it is strong
      const breath = this.track(t, 0), chiff = this.track(t, 1);
      const tr = this.tracks, p = clamp((t - tr.t0) * tr.rate, 0, tr.rows - 1), pi = Math.floor(p);
      const travel = this.travel[pi] + (this.travel[Math.min(pi + 1, tr.rows)] - this.travel[pi]) * (p - pi);
      const dots = [];
      for (const m of this.marks) {
        const x = wx + ((((m.u + travel) % WIND) + WIND) % WIND) * open;
        const fade = smoothstep(wx, wx + 20, x) * smoothstep(MX + 4, MX - 24, x);
        dots.push({ x, y: top + slot * (0.2 + 0.6 * m.v), r: m.r, color: ink.ink2, alpha: open * fade * clamp(breath / 0.6) * 0.8 });
      }
      g.points(target, dots);

      // the jet across the window: a sheet leaving the windway, swinging further the further it goes, the captured
      // deflection at its edge; heavier with breath, rough at the attack (chiff)
      const jy = top + slot / 2, N = 16, jet = [];
      for (let i = 0; i < N; i++) {
        const s = i / (N - 1);
        jet.push([MX + (WINDOW + 14) * open * s, jy + b.jet * 24 * open * s * s]);
      }
      g.stroke(target, jet, { width: (0.8 + 3.2 * clamp(breath)) * open, color: ink.cold, alpha: open * clamp(breath * 4) });
      if (chiff > 0.01) {
        const rnd = ctx.prng(Math.floor(t * 60) + 31);
        const puff = [];
        for (let i = 0; i < 14; i++) {
          const s = rnd();
          puff.push({ x: MX + (WINDOW + 14) * open * s, y: jy + (rnd() - 0.5) * 30 * chiff * 4 * s + b.jet * 24 * s * s, r: 0.9, color: ink.ink2, alpha: open * clamp(chiff * 5) });
        }
        g.points(target, puff);
      }

      // the wave in the bore: the period's sixteen snapshots as hairlines (the space it sweeps), the shown one bold
      const NB = this.NB, at = (i) => MX + (L * i) / (NB - 1);
      const y = (x, v) => mix(restY(x), CY, open) - v * this.amp * open;
      for (let s = 0; s < this.S; s++) {
        const d = this.bore.values.subarray((b.f * this.S + s) * NB, (b.f * this.S + s + 1) * NB), pts = [];
        for (let i = 0; i < NB; i++) pts.push([at(i), y(at(i), d[i])]);
        g.stroke(target, pts, { width: 0.8, color: ink.ink, alpha: 0.22 * open });
      }
      const pts = [];
      for (let i = 0; i < NB; i++) pts.push([at(i), y(at(i), this.wave[i])]);
      g.stroke(target, pts, { width: 3, color: ink.cold, alpha: open });
    }

    // the fiddle beneath: its held string, quiet
    const fa = smoothstep(T0, T0 + beat, t) * (1 - gat) * clamp(tl.gain('fiddle', t) / 0.5);
    if (fa > 0.002) {
      const d = this.stringAt(ctx, t), F = FIDDLE, NS = this.NS, pts = [];
      // place 0 is the bridge, on the right
      for (let i = 0; i < NS; i++) pts.push([mix(F.x1, F.x0, i / (NS - 1)), F.y - d[i] * F.scale]);
      g.stroke(target, [[F.x1, F.y], ...pts, [F.x0, F.y]], { width: 1.4, color: ink.ink2, alpha: 0.75 * fa });
      g.stroke(target, [[F.x0, F.y - 9], [F.x0, F.y + 9]], { width: 1.4, color: ink.ink2, alpha: 0.75 * fa });
      g.stroke(target, [[F.x1, F.y - 9], [F.x1, F.y + 9]], { width: 1.4, color: ink.ink2, alpha: 0.75 * fa });
    }

    // the gather: every part as its own strand of sound, drawn into one band
    if (gat > 0) gather(ctx, t, target, { alpha: gat });

    const la = smoothstep(T0 + 0.5 * beat, T0 + beat, t) * (1 - smoothstep(T0 + bar + 0.5 * beat, T0 + bar + 1.2 * beat, t));
    if (la > 0) label(ctx, t, target, 'whistle', { alpha: la, k });
    lyric(ctx, t, target, { k });   // refrain 2's last line, held into the turn
  },
};
