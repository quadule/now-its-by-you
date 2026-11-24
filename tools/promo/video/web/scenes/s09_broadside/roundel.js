// Line 2: the bank's 51 verses (text.json, kind verse) stand in a row above the sky like the edges of cards in a
// drawer, one mark each, its height the verse's length in letters, in the hand's indigo where a person wrote it.
// On the sung syllables they leave in order and each lands as one fifty-first of the roundel's ring; when the ring
// is whole the red plate prints it, the ring's inside clears, and MIN. 51 SEEDS prints.
import { clamp, smoothstep, ease } from '../../core/math.js';

const ROW_Y = 236, GAP = 26;

export class Roundel {
  init(ctx, F, grid) {
    const tl = ctx.timeline;
    const text = ctx.data.get('text.json');
    this.verses = text.bank.filter((v) => v.kind === 'verse');
    const n = this.verses.length;
    const letters = this.verses.map((v) => v.lines.join('').replace(/[^A-Za-z]/g, '').length);
    const lo = Math.min(...letters), hi = Math.max(...letters);
    const x0 = ctx.size.w / 2 - (GAP * (n - 1)) / 2;
    const line = tl.lineOf('refrain3', 1);
    this.line = line;
    const syl = line.words.flatMap((w) => w.syllables);
    // the ring's centre and its outer ring's radius, through the face's grid
    const R = F.json.roundel;
    const c = F.toDesign(grid, R.x, R.y), e = F.toDesign(grid, R.x + R.r[0], R.y);
    this.centre = c;
    this.radius = Math.hypot(e[0] - c[0], e[1] - c[1]);
    this.unit = this.radius / R.r[0];
    const from = syl.slice(1, -1);   // "yours" to "it": the last syllable prints the ring
    this.marks = this.verses.map((v, i) => {
      const s = from[Math.min(Math.floor((i * from.length) / n), from.length - 1)];
      const first = Math.ceil((from.indexOf(s) * n) / from.length);
      const by = v.by || '';
      return {
        x: x0 + i * GAP, h: 22 + 58 * (letters[i] - lo) / Math.max(hi - lo, 1),
        hand: /artist/.test(by) ? by : null,
        go: s.t0 + (i - first) * 0.05,
        angle: -Math.PI / 2 + (2 * Math.PI * i) / n,
      };
    });
    this.flight = 0.75;
    this.inT = line.t0;
    this.ringT = syl[syl.length - 1].t0;
    this.clearT = this.ringT + 0.25 * tl.beatLength;
    this.typeT = this.ringT + 1.0 * tl.beatLength;
  }

  // the plates this line prints at t
  plates(t, st) {
    st.rings = smoothstep(this.ringT, this.ringT + 0.12, t);
    st.ringErase = smoothstep(this.clearT, this.clearT + 0.2, t);
    st.grey = smoothstep(this.typeT, this.typeT + 0.12, t);
    st.n51 = smoothstep(this.typeT + 0.08, this.typeT + 0.2, t);
    return st;
  }

  // the plates' landing a little out of register: offset in crop px, settling
  offset(t, at, dx, dy) {
    const k = clamp((t - at) / 0.5);
    if (k <= 0 || k >= 1) return [0, 0];
    const d = Math.exp(-6 * k) * Math.cos(k * 9);
    return [dx * d, dy * d];
  }

  draw(ctx, t, target) {
    const ink = ctx.palette.inks(1);
    const b = ctx.timeline.beatLength;
    if (t < this.inT - 0.2 || t > this.ringT + 0.6) return;
    const red = ctx.palette.lin.red;
    const n = this.marks.length;
    const arc = (2 * Math.PI) / n;
    const fade = 1 - smoothstep(this.ringT + 0.05, this.ringT + 0.3, t);
    this.marks.forEach((m, i) => {
      // standing: each rises in turn as the line comes in
      const up = ease.outCubic(clamp((t - this.inT - (i / n) * 1.2 * b) / (0.6 * b)));
      if (up <= 0) return;
      const k = ease.inOutCubic(clamp((t - m.go) / this.flight));
      const col = m.hand ? ctx.palette.hand(m.hand) : ink.ink;
      const pts = [];
      const S = 12;
      // the mark, from the vertical stroke it stands as to its arc of the ring
      const [cx, cy] = this.centre, r = this.radius;
      const a0 = m.angle - arc / 2, a1 = m.angle + arc / 2;
      // the arc's own middle on the ring, where the mark's middle lands
      const tx = cx + Math.cos(m.angle) * r, ty = cy + Math.sin(m.angle) * r;
      // a path that lifts and curves in
      const sx = m.x, sy = ROW_Y - m.h * up / 2;
      const mx = (sx + tx) / 2, my = Math.min(sy, ty) - 120;
      const q = (1 - k) * (1 - k), w2 = 2 * k * (1 - k), k2 = k * k;
      const px = q * sx + w2 * mx + k2 * tx, py = q * sy + w2 * my + k2 * ty;
      for (let j = 0; j <= S; j++) {
        const u = j / S;
        const vy = ROW_Y - m.h * up * (1 - u);
        const ang = a0 + (a1 - a0) * u;
        const ax = cx + Math.cos(ang) * r, ay = cy + Math.sin(ang) * r;
        // in flight: the stroke carried along the path, turning into its arc as it lands
        pts.push([px + (ax - tx) * k, py + (vy - sy) * (1 - k) + (ay - ty) * k]);
      }
      const landed = smoothstep(0.85, 1, k);
      const c = col.map((v, ch) => v + (red[ch] - v) * landed);
      const width = 2.8 + (3.6 * this.unit - 2.8) * landed;
      ctx.g.stroke(target, pts, { width, color: c, alpha: fade });
    });
  }
}
