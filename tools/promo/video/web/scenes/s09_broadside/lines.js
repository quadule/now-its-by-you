// Line 1: every line the film has drawn comes back at once in ink, playing, out of the one strand; then each settles,
// top to bottom, on a note of the band, into one row of the sky's hatching on the face, and that row prints.
//
// The rows are the face's own hatch lines (woodcut.py's sky(), data/s09/face.json), placed by the face's grid. Each
// live line is real data at this moment of the song:
//   the voice's envelope   the heard lead's envelope (throat/lead-heard.env), one row per 5 ms frame back in time
//   the strand             the lead's pitch line (core strandPoints)
//   the strings            each sounding plucked note's string (physics/pluck-*), its loop re-run from the note's start:
//                          the shape is one period of bridge force summed (prep/DATA.md), the string's own travelling
//                          wave, sampled once a period (a strobe at the string's pitch)
//   the parts              each heard part's spectrum now (stems/<part>.env, 96 bands)
//   the file               the release file's own spectrum (stems/mix.env), one row per video frame back in time
import { strandPoints } from '../../core/draw.js';
import { clamp, smoothstep, ease } from '../../core/math.js';

const N = 320;                  // points along every line
const W = 1920;
const SR = 44100;
const PARTS = ['voice', 'lute', 'guitar', 'harp', 'bass', 'fiddle', 'whistle', 'drum', 'drone', 'arp', 'synthpad',
  'bass~', 'guitar~', 'drum~', 'fiddle~'];
const PLUCKED = ['guitar', 'bass', 'harp', 'lute'];
const SLOTS = { guitar: 6, bass: 1, harp: 4, lute: 2 };

export const LINE_ASSETS = ['throat/lead-heard.env', 'stems/mix.env', ...PARTS.map((p) => `stems/${p}.env`),
  ...PLUCKED.map((p) => `physics/pluck-${p}-notes.json`), ...PLUCKED.map((p) => `physics/pluck-${p}`), 'physics/strum.json'];

// one plane of a plucked string, its loop run from the note's start (y[n] = x[n] + g[n] sum_k taps[k] y[n - N - k])
function runPlane(pl, exc, samples) {
  const L = Math.min(pl.len, samples);
  const y = new Float32Array(Math.max(L, 1));
  const Nd = pl.N, taps = pl.taps;
  let g = pl.g;
  for (let n = 0; n < L; n++) {
    if (n >= pl.held) g = pl.rg + (g - pl.rg) * pl.smooth;
    let acc = 0;
    for (let k = 0; k < 5; k++) {
      const i = n - Nd - k;
      if (i >= 0) acc += taps[k] * y[i];
    }
    y[n] = (n < pl.xn ? exc[pl.x0 + n] : 0) + g * acc;
  }
  return y;
}

// the string's shape at sample n: one period of bridge force F, less its mean, summed (S); y(j) = S[n-P+j] - S[n-j]
function shapeAt(y, n, P, out) {
  const M = out.length;
  if (n < 2) { out.fill(0); return out; }
  P = Math.min(P, n);
  const w = new Float64Array(P);
  let mean = 0;
  for (let m = 0; m < P; m++) { w[m] = y[n - P + 1 + m]; mean += w[m]; }
  mean /= P;
  const C = new Float64Array(P);
  let s = 0;
  for (let m = 0; m < P; m++) { s += w[m] - mean; C[m] = s; }
  const half = P / 2;
  for (let i = 0; i < M; i++) {
    const j = (i / (M - 1)) * half;
    const j0 = Math.floor(j), f = j - j0;
    const at = (jj) => (jj - 1 >= 0 ? C[Math.min(jj - 1, P - 1)] : 0) - C[Math.max(P - 1 - jj, 0)];
    out[i] = at(j0) * (1 - f) + at(Math.min(j0 + 1, Math.floor(half))) * f;
  }
  return out;
}

export class Lines {
  async init(ctx, F, grid) {
    const tl = ctx.timeline;
    this.F = F;
    const line = tl.lineOf('refrain3', 0);
    this.T0 = tl.byId('refrain3').t0;
    this.line = line;
    const b = tl.beatLength;
    // the rows: the face's hatch lines, as the grid lays them, sampled at N points across their reach
    const S = F.json.px_per_unit, [cx0, cy0] = F.json.crop_px;
    const rows = [];
    for (const r of F.json.sky.rows) {
      const pts = [];
      for (const st of r.stretches) for (let i = 0; i < st.x.length; i++) {
        const [x, y] = F.toDesign(grid, st.x[i], st.y[i]);
        pts.push([x, y, st.w[i] * 1.0]);
      }
      pts.sort((a, c) => a[0] - c[0]);
      const xa = pts[0][0], xb = pts[pts.length - 1][0];
      const ty = new Float32Array(N), tw = new Float32Array(N), tx = new Float32Array(N);
      let j = 0;
      for (let i = 0; i < N; i++) {
        const x = xa + (xb - xa) * i / (N - 1);
        while (j < pts.length - 2 && pts[j + 1][0] < x) j++;
        const p = pts[j], q = pts[j + 1] || p, f = q[0] > p[0] ? clamp((x - p[0]) / (q[0] - p[0])) : 0;
        tx[i] = x; ty[i] = p[1] + (q[1] - p[1]) * f;
        tw[i] = (p[2] + (q[2] - p[2]) * f);
      }
      // design units per face unit along the row
      const scale = (xb - xa) / Math.max(pts[pts.length - 1][0] - pts[0][0], 1) || 1;
      void scale;
      const mid = ty[N >> 1];
      rows.push({ face: r.y, cropY: r.y * S - cy0, y: mid, tx, ty, tw });
    }
    void cx0;
    // design units per face unit (the grid's scale across the face at the sky)
    const p0 = F.toDesign(grid, 300, 500), p1 = F.toDesign(grid, 1000, 500);
    this.unit = (p1[0] - p0[0]) / 700;
    for (const r of rows) for (let i = 0; i < N; i++) r.tw[i] *= this.unit;
    rows.sort((a, c) => a.y - c.y);
    // the boundaries between rows in crop px, for the printed rows' mask
    this.allRows = rows;
    this.rows = rows.filter((r) => r.y > -8 && r.y < ctx.size.h + 10);

    // the live lines, top to bottom: the voice's envelope, the strand, the strings, the parts, the file
    const n = this.rows.length;
    const strandRow = this.rows.reduce((best, r, i) => (Math.abs(r.y - 540) < Math.abs(this.rows[best].y - 540) ? i : best), 0);
    const kinds = new Array(n);
    for (let i = 0; i < strandRow; i++) kinds[i] = { kind: 'envelope', j: strandRow - 1 - i };
    kinds[strandRow] = { kind: 'strand' };
    let at = strandRow + 1;
    for (const part of ['guitar', 'bass', 'harp', 'lute']) for (let s = 0; s < SLOTS[part] && at < n; s++) kinds[at++] = { kind: 'string', part, slot: s };
    for (const part of PARTS) if (at < n) kinds[at++] = { kind: 'part', part };
    for (let j = 0; at < n; j++) kinds[at++] = { kind: 'file', j };
    this.kinds = kinds;
    this.strandRow = strandRow;

    // when each settles: on the band's notes after the first line's question, top to bottom; the strand last,
    // on the line's last word
    const last = line.words[line.words.length - 1].syllables[0];
    const from = line.words.find((w) => /song/.test(w.syllables[0].text)).syllables[0].t0;
    const until = last.t0 - 0.5 * b;
    const onsets = [];
    for (const part of ctx.score.parts) {
      if (part === 'voice') continue;
      for (const nt of ctx.score.range(part, from, until)) if (nt.a > 0 && nt.t >= from && nt.t <= until) onsets.push(nt.t);
    }
    onsets.sort((a, c) => a - c);
    const uniq = [];
    for (const o of onsets) if (!uniq.length || o - uniq[uniq.length - 1] > 0.02) uniq.push(o);
    // rows share out the onsets in order; rows on one onset follow each other a few milliseconds apart
    const others = n - 1;
    const times = [];
    let prev = -1, inGroup = 0;
    for (let i = 0; i < others; i++) {
      const o = Math.min(Math.floor(i * uniq.length / others), uniq.length - 1);
      inGroup = o === prev ? inGroup + 1 : 0;
      prev = o;
      times.push(uniq[o] + inGroup * 0.035);
    }
    let k = 0;
    this.settle = this.rows.map((_, i) => (i === strandRow ? last.t0 : times[k++]));
    this.settleDur = 0.8 * b;
    this.printDur = 0.25 * b;

    // the plucked strings: the notes on each slot over the line, their loops run once
    const strum = ctx.data.get('physics/strum.json');
    const t1 = last.t0 + 1.0;
    this.slots = {};
    for (const part of PLUCKED) {
      const meta = ctx.data.get(`physics/pluck-${part}-notes.json`);
      const exc = ctx.data.get(`physics/pluck-${part}`).values;
      const notes = meta.notes.filter((nt) => nt.t < t1 && nt.t + nt.len / SR > this.T0 - 0.5);
      const slots = Array.from({ length: SLOTS[part] }, () => []);
      notes.forEach((nt, i) => {
        let s = i % SLOTS[part];
        if (part === 'guitar') {
          const st = strum.strokes.find((x) => x.strings.some((y) => Math.abs(x.t + y.dt - nt.t) < 0.003 && y.p === nt.p));
          const y = st && st.strings.find((q) => Math.abs(st.t + q.dt - nt.t) < 0.003 && q.p === nt.p);
          if (y && y.string !== undefined) s = y.string;
        }
        const pl = nt.planes[0];
        const samples = Math.ceil((t1 - nt.t) * SR) + 8;
        const y = runPlane(pl, exc, samples);
        const P = Math.round(SR / pl.f);
        const probe = shapeAt(y, Math.min(P * 3 + pl.lag, y.length - 1), P, new Float32Array(64));
        let peak = 1e-9;
        for (const v of probe) peak = Math.max(peak, Math.abs(v));
        slots[s].push({ t: nt.t + pl.lag / SR, v: nt.v, y, P, peak });
      });
      this.slots[part] = slots;
    }
    this.buf = new Float32Array(N);
    this.pts = new Float32Array(N * 2);
    this.wid = new Float32Array(N);
  }

  // live offsets (design units, up is negative) for a line kind at t, into out (N values across the full width)
  live(ctx, t, kd, out) {
    out.fill(0);
    if (kd.kind === 'envelope') {
      const env = ctx.data.get('throat/lead-heard.env');
      const row = env.at(t - kd.j * (1 / env.rate) * 10);
      for (let i = 0; i < N; i++) {
        const f = (i / (N - 1)) * (env.rowLength - 1), i0 = Math.floor(f), fr = f - i0;
        const db = row[i0] * (1 - fr) + row[Math.min(i0 + 1, env.rowLength - 1)] * fr;
        out[i] = -60 * clamp((db + 95) / 80) ** 1.6;
      }
    } else if (kd.kind === 'part' || kd.kind === 'file') {
      const name = kd.kind === 'file' ? 'stems/mix.env' : `stems/${kd.part}.env`;
      const env = ctx.data.get(name);
      const row = env.at(t - (kd.j || 0) / env.rate * 2);
      const on = kd.kind === 'file' ? 1 : ctx.timeline.gain(kd.part, t) > 0 ? 1 : 0;
      for (let i = 0; i < N; i++) {
        const f = 3 + (i / (N - 1)) * 95, i0 = Math.floor(f), fr = f - i0;
        const db = row[i0] * (1 - fr) + row[Math.min(i0 + 1, 98)] * fr;
        out[i] = -on * (kd.kind === 'file' ? 34 : 30) * clamp((db + 90) / 75) ** 1.5;
      }
    } else if (kd.kind === 'string') {
      const notes = this.slots[kd.part][kd.slot];
      let nt = null;
      for (const x of notes) if (x.t <= t) nt = x;
      if (nt) {
        // seen as a strobe at the string's own period sees it: the shape at the last whole period, so it stands
        // still within a frame and turns slowly as the loop's fraction of a sample carries the wave round
        const n = Math.floor((t - nt.t) * SR / nt.P) * nt.P;
        if (n > 1 && n < nt.y.length) {
          shapeAt(nt.y, n, nt.P, out);
          // the ring's decay drawn compressed (its amplitude to the 0.4 power) so a string stays visible as it rings
          let now = 1e-9;
          for (let i = 0; i < N; i++) now = Math.max(now, Math.abs(out[i]));
          const k = -70 * Math.min(nt.v, 1) * Math.min(now / nt.peak, 1) ** 0.4 / now;
          for (let i = 0; i < N; i++) out[i] *= k;
        }
      }
    }
    return out;
  }

  // how far each row has settled (0..1) and printed (0..1) at t
  state(i, t) {
    const s = this.settle[i];
    const k = ease.inOutCubic(clamp((t - s) / this.settleDur));
    const p = clamp((t - s - this.settleDur * 0.85) / this.printDur);
    return { k, p };
  }

  // the printed rows into F.rowsData (one value per crop px row)
  fill(t) {
    const F = this.F, data = F.rowsData, rows = this.allRows, H = data.length;
    // rows outside the frame print with their nearest neighbour inside it
    const amt = rows.map((r) => {
      const i = this.rows.indexOf(r);
      const j = i >= 0 ? i : (r.y < this.rows[0].y ? 0 : this.rows.length - 1);
      return this.state(j, t).p;
    });
    let r = 0;
    for (let y = 0; y < H; y++) {
      while (r < rows.length - 1 && y > (rows[r].cropY + rows[r + 1].cropY) / 2) r++;
      data[y] = amt[r];
    }
  }

  draw(ctx, t, target) {
    const ink = ctx.palette.inks(1).ink;
    const T0 = this.T0, b = ctx.timeline.beatLength;
    // the strand alone at rest until the first downbeat; then every line comes out of it
    const strand = strandPoints(ctx, t, { y: 540, x0: 0, x1: W });
    const sp = strand.points;
    const strandOff = new Float32Array(N);
    let j = 0;
    for (let i = 0; i < N; i++) {
      const x = (i / (N - 1)) * W;
      while (j < sp.length - 2 && sp[j + 1][0] < x) j++;
      const p = sp[j], q = sp[j + 1] || p, f = q[0] > p[0] ? clamp((x - p[0]) / (q[0] - p[0])) : 0;
      strandOff[i] = p[1] + (q[1] - p[1]) * f - 540;
    }
    const n = this.rows.length;
    for (let r = 0; r < n; r++) {
      const row = this.rows[r], kd = this.kinds[r];
      const { k, p } = this.state(r, t);
      if (p >= 1) continue;
      const isStrand = r === this.strandRow;
      // out of the strand: each line leaves y = 540 for its row over the first two beats, nearer rows first
      const d = Math.abs(row.y - 540) / 540;
      const e = isStrand ? 1 : ease.outCubic(clamp((t - T0 - d * 0.75 * b) / (2 * b)));
      if (!isStrand && e <= 0) continue;
      const off = isStrand ? strandOff : this.live(ctx, t, kd, this.buf);
      const base = 540 + (row.y - 540) * e;
      const pts = this.pts, wid = this.wid;
      for (let i = 0; i < N; i++) {
        const lx = (i / (N - 1)) * W, ly = base + off[i] * e + (isStrand ? 0 : strandOff[i] * (1 - e));
        pts[i * 2] = lx + (row.tx[i] - lx) * k;
        pts[i * 2 + 1] = ly + (row.ty[i] - ly) * k;
        wid[i] = (isStrand ? 2.5 : 1.25) * (1 - k) + row.tw[i] * k;
      }
      const alpha = (1 - p) * (isStrand ? 1 : smoothstep(0, 0.35, e));
      ctx.g.stroke(target, pts, { width: (i) => wid[i], alpha, color: ink });
    }
  }
}
