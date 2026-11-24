// Line 4: the tune's notes that moved to follow the singers (text.json `moved`, the table in
// docs/history/MAKING-IT-THEIR-OWN.md), set as one engraved page: every phrase with a moved note, in the order
// the song first sings it, as a staff of fine rules with its notes as the tune now writes them (text.json
// phrases); the note as it was written hollow, the note the singers chose solid in the hand ink, a hairline
// between. The words beneath are the phrase's syllables where the song first sings it (score.json voice).
import { clamp, smoothstep, mix, ease } from '../../core/math.js';

const SOLFA = { do: 1, re: 2, mi: 3, fa: 4, so: 5, la: 6, ti: 7 };
// "re mi" -> [2, 3] scale steps; "low so" -> [-2]
function steps(names) {
  const out = [];
  let low = false;
  for (const w of names.trim().split(/\s+/)) {
    if (w === 'low') { low = true; continue; }
    out.push(SOLFA[w] - (low ? 7 : 0));
    low = false;
  }
  return out;
}
const degreeStep = (d) => Number(d.replace(/[,']/g, '')) + 7 * ((d.match(/'/g) || []).length - (d.match(/,/g) || []).length);

// the page from just under the label to just over the sung line; each staff as tall as its phrase's compass
export const PAGE = { x0: 130, x1: 1790, cols: 2, colGap: 110, top: 160, bottom: 772, bar: 10, words: 23, under: 36, gap: 34 };

export function movedSetup(ctx, text) {
  const voice = ctx.score.notes('voice');
  const first = (pid) => voice.findIndex((n) => n.phrase === pid);
  const pids = [...new Set(text.moved.rows.map((r) => r.phrase))].sort((a, b) => first(a) - first(b));
  const staves = pids.map((pid, i) => {
    const rows = text.moved.rows.filter((r) => r.phrase === pid);
    const k0 = first(pid);
    const notes = text.phrases[pid].notes.map((n, j) => ({ ...n, s: degreeStep(n.degree), syl: voice[k0 + j]?.syl ?? '' }));
    for (const row of rows) {
      const from = steps(row.from), to = steps(row.to);
      row.notes.forEach((j, q) => { notes[j].was = notes[j].s - (to[q] - from[q]); });
    }
    const all = notes.flatMap((n) => [n.s, n.was ?? n.s]);
    return { pid, rows, notes, lo: Math.min(...all), hi: Math.max(...all), i };
  });
  // two columns of staves, read down the left then the right; one step size for the page, the largest that fits
  const per = Math.ceil(staves.length / PAGE.cols), colW = (PAGE.x1 - PAGE.x0 - PAGE.colGap * (PAGE.cols - 1)) / PAGE.cols;
  let step = 22;
  for (let c = 0; c < PAGE.cols; c++) {
    const col = staves.slice(c * per, (c + 1) * per);
    const fixed = col.length * (PAGE.bar + PAGE.under) + (col.length - 1) * PAGE.gap;
    step = Math.min(step, (PAGE.bottom - PAGE.top - fixed) / col.reduce((a, st) => a + (st.hi - st.lo), 0));
  }
  for (let c = 0; c < PAGE.cols; c++) {
    let y = PAGE.top;
    for (const st of staves.slice(c * per, (c + 1) * per)) {
      st.step = step;
      st.x0 = PAGE.x0 + c * (colW + PAGE.colGap);
      st.x1 = st.x0 + colW;
      st.top = y + PAGE.bar / 2;
      st.base = st.top + (st.hi - st.lo) * step + PAGE.bar / 2 + PAGE.under - 8;
      y = st.base + 8 + PAGE.gap;
    }
  }
  return staves;
}

export function drawMoved(ctx, t, target, staves, { ink, hand, t0, stagger, alpha, white }) {
  if (alpha <= 0) return;
  const g = ctx.g, ty = ctx.type;
  for (const st of staves) {
    const at = t0 + st.i * stagger;
    const show = alpha * ease.outCubic((t - at) / 0.45);
    if (show <= 0) continue;
    const rule = ease.inOutCubic((t - at + 0.15) / 0.6);
    const move = ease.inOutCubic((t - at - 0.4) / 0.5);
    const Y = (s) => st.top + (st.hi - s) * st.step, ex = (st.x1 - st.x0) / 17;
    // the staff: a fine rule on every other step through the phrase's compass
    for (let s = st.lo; s <= st.hi; s += 1) {
      g.stroke(target, [[st.x0 - 14, Y(s)], [mix(st.x0 - 14, st.x1 + 14, rule), Y(s)]], { width: 1, color: ink.rule, alpha: alpha * 0.9 });
    }
    const rects = [];
    let right = -Infinity, dropped = false;
    for (const n of st.notes) {
      const x0 = st.x0 + (n.at + 1) * ex, w = n.units * ex - 5;
      if (n.was === undefined) {
        rects.push({ x: x0, y: Y(n.s) - PAGE.bar / 2, w, h: PAGE.bar, color: ink.ink, alpha: show });
      } else {
        const yWas = Y(n.was), yNow = mix(yWas, Y(n.s), move);
        g.stroke(target, [[x0, yWas - PAGE.bar / 2], [x0 + w, yWas - PAGE.bar / 2], [x0 + w, yWas + PAGE.bar / 2], [x0, yWas + PAGE.bar / 2]],
          { width: 1.6, color: ink.ink, alpha: show, closed: true });
        // an arrow from the written note to the sung one
        const ax = x0 + Math.min(w / 2, 40), dir = Math.sign(yNow - yWas);
        if (move > 0 && Math.abs(yNow - yWas) > PAGE.bar) {
          const y0 = yWas + dir * (PAGE.bar / 2 + 2), y1 = yNow - dir * (PAGE.bar / 2 + 2);
          g.stroke(target, [[ax, y0], [ax, y1]], { width: 1.4, color: hand, alpha: show });
          g.stroke(target, [[ax - 5, y1 - dir * 7], [ax, y1], [ax + 5, y1 - dir * 7]], { width: 1.4, color: hand, alpha: show });
        }
        rects.push({ x: x0, y: yNow - PAGE.bar / 2, w, h: PAGE.bar, color: hand, alpha: show * smoothstep(0, 0.25, move) });
      }
      // its syllable beneath the staff
      if (n.syl) {
        const s = ty.text(n.syl, { role: 'lyric', size: PAGE.words, italic: n.was !== undefined });
        // a syllable that would run into the one before it is set a line lower
        dropped = x0 < right + 6 && !dropped;
        right = x0 + s.width;
        ty.draw(target, s, x0, st.base + (dropped ? PAGE.words : 0), { color: n.was !== undefined ? hand : ink.ink2, alpha: show });
      }
    }
    g.rects(target, rects, { texture: white, snap: true });
  }
}
