// The 79 takes (text.json counts.takes) as a count kept by hand: tally groups of five, four strokes and a
// strike, the last group short by one. All alike: a count, not a picture of anyone's take. Drawn stroke by
// stroke, a group to each sixteenth note; struck out left to right, and gone.
import { clamp, smoothstep, mix, ease } from '../../core/math.js';

export const TALLY = { x0: 150, x1: 1770, top: 150, height: 64, step: 15, width: 3.2 };

// every stroke in drawing order: [x0, y0, x1, y1, group]
export function tallyStrokes(count) {
  const groups = Math.ceil(count / 5), gw = (TALLY.x1 - TALLY.x0) / groups;
  const out = [];
  let left = count;
  for (let gi = 0; gi < groups; gi++) {
    const n = Math.min(left, 5), x = TALLY.x0 + gi * gw + (gw - 4 * TALLY.step) / 2, y0 = TALLY.top, y1 = TALLY.top + TALLY.height;
    for (let s = 0; s < Math.min(n, 4); s++) out.push([x + s * TALLY.step, y0, x + s * TALLY.step - 3, y1, gi]);
    if (n === 5) out.push([x - 12, y1 - 14, x + 3 * TALLY.step + 14, y0 + 16, gi]);
    left -= n;
  }
  return out;
}

// t0: the first group's sixteenth; per: seconds a group; strike0..strike1: the strike-out
export function drawTally(ctx, t, target, strokes, { color, t0, per, strike0, strike1, alpha = 1 }) {
  const g = ctx.g;
  const groupsDone = new Map();
  const front = mix(TALLY.x0 - 20, TALLY.x1 + 130, ease.inOutQuad((t - strike0) / (strike1 - strike0)));
  const midY = TALLY.top + TALLY.height * 0.55;
  for (let i = 0; i < strokes.length; i++) {
    const [x0, y0, x1, y1, gi] = strokes[i];
    const k = (groupsDone.get(gi) || 0);
    groupsDone.set(gi, k + 1);
    const at = t0 + gi * per + k * per / 5;
    const draw = ease.outCubic((t - at) / (per * 0.9));
    if (draw <= 0) continue;
    // struck: the stroke is gone a moment after the strike's front has crossed it
    const xc = Math.max(x0, x1);
    const gone = clamp((front - xc) / 90);
    if (gone >= 1) continue;
    const len = draw * (1 - gone);
    const xe = mix(x0, x1, len), ye = mix(y0, y1, len);
    g.stroke(target, [[x0, y0], [xe, ye]], { width: TALLY.width, color, alpha });
  }
  // the strike through the wall, its tail eaten as the strokes go
  if (t > strike0 && front > TALLY.x0) {
    const a = Math.max(TALLY.x0 - 10, front - 140), b = Math.min(front, TALLY.x1 + 10);
    if (b > a) g.stroke(target, [[a, midY + 2], [b, midY - 2]], { width: TALLY.width * 0.8, color, alpha: alpha * (1 - smoothstep(TALLY.x1 - 60, TALLY.x1 + 20, front)) });
  }
}
