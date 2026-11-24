// What sounds under the tune, each on the grid's time axis (x is song time, as the digits' cells are), revealed
// up to now, in fine cold light behind the lead:
//   the lead's oscillogram: whistle~'s own samples (stems/whistle~.wav) hanging from its pitch line; each column is
//     two periods of the wave from an upward zero crossing (the period from the synth's pitch trace), so the saw's
//     shape and its filter opening read down the column, lit by the wave's level there
//   the floor: drone and synthpad, their summed band levels (stems/*.env, 96 bands) as hairlines receding by band
//   the synth bass (bass~): its synth's pitch trace as one slow low line, lit by its amp envelope
//   the arp on the harp's notes (harp~): a point at each note's start, a hairline for its length
import { clamp, smoothstep, mix } from '../../core/math.js';
import { GRID, gridX, gridHeight, traceOf } from './tune.js';

const RATE = 44100, COLS_PER_S = 120, ROWS = 96;
const FLOOR = { top: 948, bottom: 1070, bands: 24 };
const BASS = { y: 930, step: 4.5, low: 26 };
const ARP = { y: 700, step: 14.5, low: 37 };

async function wav(ctx, name, t1) {
  const buf = await ctx.data.bytes(name);
  const dv = new DataView(buf);
  // find the data chunk
  let off = 12, data = 44;
  while (off < 200) {
    const id = String.fromCharCode(dv.getUint8(off), dv.getUint8(off + 1), dv.getUint8(off + 2), dv.getUint8(off + 3));
    const len = dv.getUint32(off + 4, true);
    if (id === 'data') { data = off + 8; break; }
    off += 8 + len;
  }
  const n = Math.min(Math.ceil(t1 * RATE), (buf.byteLength - data) >> 1);
  return new Int16Array(buf.slice(data, data + n * 2));
}

export async function buildLayers(ctx, S) {
  const L = {};
  const sA = S.T0 - S.eighth, sB = S.T2;
  L.sA = sA; L.sB = sB;
  const x = await wav(ctx, 'stems/whistle~.wav', sB + 0.1);
  let peak = 1;
  for (let i = Math.floor(sA * RATE); i < x.length; i++) peak = Math.max(peak, Math.abs(x[i]));
  // the oscillogram: a data column and an empty one, so each column is a fine vertical
  const C = Math.round((sB - sA) * COLS_PER_S), W = C * 2;
  const tex = new Uint8Array(W * ROWS * 4);
  const tr = S.trace;
  for (let j = 0; j < C; j++) {
    const s = sA + (j + 0.5) / COLS_PER_S;
    const p = tr.pitch(s);
    if (p === null) continue;
    const P = RATE / (440 * 2 ** ((p - 69) / 12));
    let i0 = Math.round(s * RATE);
    const lim = i0 + Math.ceil(P) + 1;
    while (i0 < lim && !(x[i0 - 1] < 0 && x[i0] >= 0)) i0++;
    let amp = 0;
    for (let k = 0; k < 2 * P; k++) amp = Math.max(amp, Math.abs(x[i0 + k] || 0));
    if (amp < 1) continue;
    const lit = (amp / peak) ** 0.8;
    for (let r = 0; r < ROWS; r++) {
      const f = i0 + ((r + 0.5) / ROWS) * 2 * P, k = Math.floor(f), q = f - k;
      const v = ((x[k] || 0) * (1 - q) + (x[k + 1] || 0) * q) / amp;
      const a = Math.round(255 * clamp(v) ** 1.5 * lit);
      const o = (r * W + j * 2) * 4;
      tex[o] = tex[o + 1] = tex[o + 2] = tex[o + 3] = a;
    }
  }
  L.osc = ctx.g.texture({ width: W, height: ROWS, data: tex }, { filter: 'linear' });
  L.oscCols = C;
  // the floor: drone + synthpad band power at each video frame of the grid's span
  const dr = ctx.data.get('stems/drone.env'), pad = ctx.data.get('stems/synthpad.env');
  const f0 = Math.ceil(sA * 60), f1 = Math.floor(sB * 60), FC = f1 - f0 + 1, FB = FLOOR.bands, FH = FB * 2;
  const ftex = new Uint8Array(FC * FH * 4);
  for (let c = 0; c < FC; c++) {
    const a = dr.row(f0 + c), b = pad.row(f0 + c);
    for (let band = 0; band < FB; band++) {
      let pw = 0;
      for (let q = 0; q < 4; q++) { const k = 3 + band * 4 + q; pw += 10 ** (a[k] / 10) + 10 ** (b[k] / 10); }
      const db = 10 * Math.log10(pw + 1e-12);
      const v = Math.round(255 * clamp((db + 72) / 44) ** 2);
      // high bands far (top), low bands near (bottom); every other texel row empty, so each band is a hairline
      const row = (FB - 1 - band) * 2;
      const o = (row * FC + c) * 4;
      ftex[o] = ftex[o + 1] = ftex[o + 2] = ftex[o + 3] = v;
    }
  }
  L.floor = ctx.g.texture({ width: FC, height: FH, data: ftex }, { filter: 'linear' });
  L.floorT = [f0 / 60, f1 / 60];
  L.bass = traceOf(ctx, 'bass~', sA, sB);
  L.arp = ctx.score.notes('harp~').filter((n) => n.t >= sA - 0.05 && n.t < sB);
  return L;
}

// the floor's rows in perspective: band rows crowd toward the far (top) edge
function floorY(v) {
  return FLOOR.top + (FLOOR.bottom - FLOOR.top) * (v * v * 0.55 + v * 0.45);
}

export function drawLayers(ctx, t, target, ink, S, L, fade) {
  if (fade <= 0.002) return;
  const { T0, eighth } = S;
  const now = Math.min(t, L.sB);
  if (now <= L.sA) return;
  const X = (s) => gridX(s, T0, eighth);
  // the floor
  {
    const [a, b] = L.floorT, u1 = clamp((now - a) / (b - a));
    if (u1 > 0) {
      const xa = X(a), xb = X(a + (b - a) * u1), rows = 25, grid = [];
      for (let r = 0; r < rows; r++) { const y = floorY(r / (rows - 1)); grid.push([xa, y], [xb, y]); }
      ctx.g.mesh(target, L.floor, grid, { cols: 2, rows, alpha: fade * 0.5, tint: ink.cold, srgb: false, uv: [0, 0, u1, 1] });
    }
  }
  // the synth bass
  if (L.bass) {
    const pts = [], al = [];
    for (let s = Math.max(L.sA, L.bass.t0); s <= now; s += 1 / 60) {
      const p = L.bass.pitch(s);
      if (p === null) continue;
      pts.push([X(s), BASS.y - (p - BASS.low) * BASS.step]);
      al.push(clamp(0.35 + L.bass.amp(s) * 1.5));
    }
    if (pts.length > 1) ctx.g.stroke(target, pts, { width: 1.8, color: ink.cold, alpha: (i) => fade * al[i], intensity: 1.2 });
  }
  // the lead's oscillogram, hanging from its pitch line to the grid's line
  {
    const flat = S.flatAt(t);
    const C = L.oscCols, grid = [];
    let jmax = Math.floor((now - L.sA) * COLS_PER_S);
    jmax = Math.min(jmax, C - 1);
    if (jmax >= 1) {
      const tops = [], bots = [];
      for (let j = 0; j <= jmax; j++) {
        const s = L.sA + j / COLS_PER_S;
        const h = gridHeight(S.trace, s, t) * (1 - flat);
        tops.push([X(s), GRID.y - h]); bots.push([X(s), GRID.y]);
      }
      for (const p of tops) grid.push(p);
      for (const p of bots) grid.push(p);
      ctx.g.mesh(target, L.osc, grid, { cols: jmax + 1, rows: 2, alpha: fade * 0.62, tint: ink.cold, srgb: false,
        uv: [0, 0, (jmax + 1) / C, 1] });
    }
  }
  // the arp
  const dots = [];
  for (const n of L.arp) {
    if (n.t > now) break;
    const x = X(n.t), y = ARP.y - (n.p - ARP.low) * ARP.step;
    const since = t - n.t, ring = Math.exp(-since / 0.35);
    const xe = X(Math.min(n.t + n.d, now));
    if (xe > x + 1) ctx.g.stroke(target, [[x, y], [xe, y]], { width: 1.2, color: ink.cold, alpha: fade * 0.4 });
    dots.push({ x, y, r: 3.4 + 3.2 * ring, color: ink.cold, alpha: fade * (0.6 + 0.4 * ring), intensity: 1.2 + 2.2 * ring, soft: 0.6 * ring });
  }
  ctx.g.points(target, dots);
}
export { smoothstep, mix };
