// Line 3: the proof. The pitch line the machine sings with no people in it (throat/lead-0.00-whole.lf0, the
// human-0 take) in ink2, and the line sounding now (throat/lead-0.60.lf0, the take the stage plan has here) in
// full ink over it, the area between them filled in the hand ink, one column per frame of the data (200 a
// second). Both are the log f0 the throat was told, drawn where the frame is voiced (flags bit 0) and not silence
// or breath (bit 1). The whole sung line across the frame, both lines at one scale; the syllables under the
// sounding line where each begins, the one sounding now in ink, with the playhead through it.
import { clamp, smoothstep, mix, ease } from '../../core/math.js';

export const PROOF = { x0: 60, x1: 1860, top: 186, bottom: 744, pad: 0.04, floor: 806 };

const midi = (lf0) => 69 + 12 * Math.log2(Math.exp(lf0) / 440);

export function proofSetup(ctx, line, machineLf0, machineFlags, heardLf0, heardFlags, notes) {
  const rate = machineLf0.rate;
  const t0 = line.t0 - PROOF.pad, t1 = line.t1 + PROOF.pad;
  const i0 = Math.floor(t0 * rate), i1 = Math.ceil(t1 * rate);
  const count = i1 - i0 + 1;
  const A = new Float32Array(count), B = new Float32Array(count), va = new Uint8Array(count), vb = new Uint8Array(count);
  let lo = Infinity, hi = -Infinity;
  for (let j = 0; j < count; j++) {
    const i = i0 + j;
    A[j] = midi(machineLf0.values[i]); B[j] = midi(heardLf0.values[i]);
    va[j] = (machineFlags.raw[i] & 1) && !(machineFlags.raw[i] & 2) ? 1 : 0;
    vb[j] = (heardFlags.raw[i] & 1) && !(heardFlags.raw[i] & 2) ? 1 : 0;
    if (va[j]) { lo = Math.min(lo, A[j]); hi = Math.max(hi, A[j]); }
    if (vb[j]) { lo = Math.min(lo, B[j]); hi = Math.max(hi, B[j]); }
  }
  const X = (s) => PROOF.x0 + (s - t0) / (t1 - t0) * (PROOF.x1 - PROOF.x0);
  const Y = (p) => PROOF.bottom - (p - lo) / (hi - lo) * (PROOF.bottom - PROOF.top);
  return { line, rate, i0, count, A, B, va, vb, lo, hi, t0, t1, X, Y, notes };
}

function at(P, arr, s) {
  const f = s * P.rate - P.i0, j = Math.floor(f);
  if (j < 0) return arr[0];
  if (j >= P.count - 1) return arr[P.count - 1];
  return mix(arr[j], arr[j + 1], f - j);
}

function runs(P, arr, v, upTo) {
  const out = [];
  let cur = null;
  for (let j = 0; j < P.count; j++) {
    const s = (P.i0 + j) / P.rate;
    if (s > upTo || s < P.line.t0 || s > P.line.t1) { cur = null; continue; }
    if (v[j]) {
      if (!cur) { cur = []; out.push(cur); }
      cur.push([P.X(s), P.Y(arr[j])]);
    } else cur = null;
  }
  return out;
}

export function drawProof(ctx, t, target, P, { ink, hand, alpha, sweep, white }) {
  if (alpha <= 0) return;
  const g = ctx.g, ty = ctx.type, L = P.line, now = clamp(t, L.t0, L.t1);
  // the semitones, ruled across the page
  for (let p = Math.ceil(P.lo); p <= Math.floor(P.hi); p++) {
    g.stroke(target, [[PROOF.x0 - 30, P.Y(p)], [PROOF.x1 + 30, P.Y(p)]], { width: 1, color: ink.rule, alpha: alpha * 0.7 * sweep });
  }
  // the area between, as far as the line has been sung
  const rects = [], dx = P.X(1 / P.rate) - P.X(0);
  for (let j = 0; j < P.count; j++) {
    const s = (P.i0 + j) / P.rate;
    if (s < L.t0 || s > now || !P.va[j] || !P.vb[j]) continue;
    const ya = P.Y(P.A[j]), yb = P.Y(P.B[j]);
    if (Math.abs(ya - yb) < 0.4) continue;
    rects.push({ x: P.X(s) - dx / 2, y: Math.min(ya, yb), w: dx + 0.15, h: Math.abs(ya - yb), color: hand, alpha });
  }
  g.rects(target, rects, { texture: white });
  // the machine alone, whole, drawn in at the line's start; the line sounding now, as far as it has sounded
  for (const r of runs(P, P.A, P.va, mix(L.t0, L.t1, sweep))) g.stroke(target, r, { width: 2, color: ink.ink2, alpha });
  for (const r of runs(P, P.B, P.vb, now)) g.stroke(target, r, { width: 4, color: ink.ink, alpha });
  // the syllables, each under the line where it begins
  for (const n of P.notes) {
    const x = P.X(n.t);
    const low = Math.max(P.Y(at(P, P.A, n.t + 0.05)), P.Y(at(P, P.B, n.t + 0.05)));
    const sung = t >= n.t, sounding = sung && t < n.t + n.d;
    const s = ty.text(n.syl, { role: 'lyric', size: 26, italic: sounding });
    ty.draw(target, s, x, Math.min(low + 40, PROOF.floor - 10), {
      color: sounding ? ink.red : sung ? ink.ink : ink.ink2, alpha: alpha * smoothstep(0, 0.6, sweep) * (sung ? 1 : 0.55),
    });
  }
  // the playhead
  if (t >= L.t0 - 0.1 && t <= L.t1 + 0.1) {
    const x = P.X(now), a = alpha * smoothstep(L.t0 - 0.1, L.t0, t) * (1 - smoothstep(L.t1, L.t1 + 0.1, t));
    g.stroke(target, [[x, PROOF.top - 20], [x, PROOF.floor - 4]], { width: 1, color: ink.red, alpha: a });
    g.points(target, [{ x, y: P.Y(at(P, P.B, now)), r: 5, color: ink.red, alpha: a }]);
  }
}
