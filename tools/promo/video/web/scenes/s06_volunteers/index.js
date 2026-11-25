// The volunteers: what the song keeps from the people who sang it. Only the blended, public numbers: no
// recording of a person exists any more, so no waveform of a person is drawn and nothing here is per singer.
// The strand is the pitch line, and here it learns handwriting.
//   line 1  the strand opens into the Sing view's lane, large; the 79 takes as a wall of tallies
//   line 2  each note's bar becomes a ribbon in the shape of its nine numbers, the numbers set on the shape;
//           from "and" to the line's last word the tallies are struck out
//   line 3  the machine's pitch line with no people in it against the one sounding now, followed close
//   line 4  the tune's notes that moved to follow the singers, as an engraved page
import { ground, lyric, label } from '../../core/draw.js';
import { clamp, smoothstep, mix, ease } from '../../core/math.js';
import { LANE, page, barShape, drawBar, annotate, laneY } from './lane.js';
import { proofSetup, drawProof } from './proof.js';
import { movedSetup, drawMoved } from './moved.js';
import { tallyStrokes, drawTally } from './tally.js';

const SECTION = 'refrain2';
const S = {};

function setup(ctx) {
  const tl = ctx.timeline, text = ctx.data.get('text.json');
  S.lines = tl.linesOf(SECTION);
  S.sec = tl.byId(SECTION);
  S.beat = tl.beatLength;
  S.pages = [0, 1].map((i) => page(ctx, S.lines[i], text.gestures.lead.rows, text.phrases));
  S.takes = text.counts.takes;
  S.strokes = tallyStrokes(S.takes.value);
  const d = (n) => ctx.data.get(n);
  S.proof = proofSetup(ctx, S.lines[2], d('throat/lead-0.00-whole.lf0'), d('throat/lead-0.00-whole.flags'),
    d('throat/lead-0.60.lf0'), d('throat/lead-0.60.flags'),
    ctx.score.range('voice', S.lines[2].t0, S.lines[2].t1 + 1e-3));
  S.movedRows = text.moved;
  S.staves = movedSetup(ctx, text);
  S.goes = S.lines[1].words.find((w) => w.text === 'and');
  S.goesEnd = S.lines[1].words[S.lines[1].words.length - 1];
}

// how far the light has come back: from black over the section's first two beats
function returned(ctx, t) {
  const t0 = ctx.timeline.byId(SECTION).t0;
  return smoothstep(t0, t0 + 2 * ctx.timeline.beatLength, t);
}

// line 1's page gives way to line 2's over the beat where they meet: a short drift and a crossfade
function slide(t) {
  const a = S.lines[0].t1, b = S.lines[1].t0;
  const mid = (a + b) / 2, half = S.beat * 0.6;
  return ease.inOutCubic((t - (mid - half)) / (2 * half));
}

// where a note of line 1 lies on the strand at rest (core/draw.js strandPoints' frame)
function restPlace(ctx, t, m) {
  const w = ctx.size.w, at = 0.62, back = 4.5, ahead = 2.5;
  const X = (s) => w * (at + (s - t) / (back + ahead));
  return { x0: X(m.n.t), x1: X(m.n.t + m.n.d), y: 540 - (m.n.p - ctx.timeline.tonic) * 9 };
}

function drawLane(ctx, t, target, ink, hand, handMoved) {
  const L = S.lines, sl = slide(t), DRIFT = 240, ty = ctx.type;
  const awayAll = 1 - smoothstep(L[2].t0 - 0.35, L[2].t0 + 0.05, t);
  // out of the strand: line 1's bars leave the rest pose over the section's first two beats
  const out = ease.inOutCubic((t - S.sec.t0) / (2 * S.beat));
  if (awayAll <= 0) return;
  const ra = awayAll * smoothstep(0.4, 1, out);
  for (let p = Math.ceil(LANE.lo); p <= LANE.hi; p++) {
    ctx.g.stroke(target, [[LANE.x0 - 40, laneY(p)], [LANE.x1 + 40, laneY(p)]], { width: 1, color: ink.rule, alpha: ra * 0.65 });
  }
  S.pages.forEach((P, pi) => {
    const vis = pi === 0 ? 1 - sl : sl;
    if (vis <= 0) return;
    const dx = (pi - sl) * DRIFT, away = awayAll * vis;
    const X = (s) => P.X(s) + dx;
    const shapes = P.notes.map((m) => barShape(m, X, pi === 1 ? ease.inOutCubic((t - m.n.t + 0.05) / 0.45) : 0));
    // where each syllable is set, so the numbers that stay keep off them
    const boxes = P.notes.map((m, q) => {
      const sp = ty.text(m.n.syl, { role: 'lyric', size: 28 }), sh = shapes[q];
      const x = Math.min(sh[0][0], X(m.w.t)), y = Math.max(...sh.map(([, y, th]) => y + th / 2)) + 32;
      return { x0: x, x1: x + sp.width, y0: y - sp.ascent, y1: y + sp.descent, y, x, sp };
    });
    for (const m of P.notes) {
      // line 2's notes take their gesture as each is sung
      const k = pi === 1 ? ease.inOutCubic((t - m.n.t + 0.05) / 0.45) : 0;
      let shape = shapes[m.i];
      if (pi === 0 && out < 1) {
        const sp = restPlace(ctx, t, m);
        shape = shape.map(([x, y, th], j) => {
          const f = j / (shape.length - 1);
          return [mix(mix(sp.x0, sp.x1, f), x, out), mix(sp.y, y, out), mix(2.5, th, out)];
        });
      }
      const done = t >= m.n.t + m.n.d;
      // a note the singers moved (text.json moved) is in the hand ink throughout
      const moved = S.movedRows.rows.some((r) => r.phrase === P.pid && r.notes.includes(m.i));
      if (k > 0) {
        // the written bar left hollow, the ribbon over it in the hand ink
        drawBar(ctx, target, barShape(m, X, 0), { color: ink.ink2, alpha: away * 0.7, fill: 0, edge: 1.2, white: S.white });
        drawBar(ctx, target, shape, { color: hand, alpha: away, pitch: 2.5, hatch: 1.5, white: S.white });
        // a note's nine numbers while it is sung, until the next note begins; then the ones that stay
        const next = P.notes[m.i + 1], until = next ? next.n.t : m.n.t + m.n.d + 0.8;
        const full = (1 - smoothstep(until - 0.04, until + 0.1, t)) * smoothstep(m.n.t - 0.1, m.n.t + 0.2, t);
        const rest = smoothstep(until, until + 0.3, t) * 0.75;
        annotate(ctx, target, m, shape, { color: hand, full: full * away, rest: rest * away, avoid: boxes });
      } else {
        drawBar(ctx, target, shape, { color: moved ? handMoved : ink.ink, alpha: away * (pi === 0 ? smoothstep(0, 0.35, out) : 1), hatch: 3, white: S.white });
      }
      const sa = away * smoothstep(0.3, 1, out);
      if (sa > 0) {
        const s = ty.text(m.n.syl, { role: 'lyric', size: 28 });
        const below = Math.max(...shape.map(([, y, th]) => y + th / 2));
        ty.draw(target, s, Math.min(shape[0][0], X(m.w.t)), below + 32, { color: done ? ink.ink2 : ink.ink, alpha: sa });
      }
    }
    // the playhead, a fine red hairline
    const ph = X(clamp(t, P.t0, P.t1));
    const pa = away * smoothstep(0.5, 1, out) * smoothstep(P.line.t0 - 0.4, P.line.t0, t) * (1 - smoothstep(P.line.t1 + 0.1, P.line.t1 + 0.4, t));
    if (pa > 0) ctx.g.stroke(target, [[ph, laneY(LANE.hi) - 24], [ph, laneY(LANE.lo) + 60]], { width: 1, color: ink.red, alpha: pa });
  });
}

// the strand at rest as core/draw.js strand() draws it, faded by `alpha`, reaching `reach` of the half-width from the centre
function restStrand(ctx, t, target, ink, alpha, reach = 1) {
  // before the downbeat, exactly the strand s04 draws (its anchor), which is the rest pose there
  const a = t < S.sec.t0 ? ctx.anchor('s04_bow', t) : null;
  const s = a && a.points ? { points: a.points, nowX: ctx.draw.strandPoints(ctx, t).nowX } : ctx.draw.strandPoints(ctx, t);
  const n = s.points.length, nowI = s.points.findIndex((p) => p[0] >= s.nowX);
  const cx = ctx.size.w / 2, half = cx * reach + 1;
  const pts = s.points.filter((p) => Math.abs(p[0] - cx) <= half);
  if (pts.length < 2) return;
  const first = s.points.indexOf(pts[0]);
  ctx.g.stroke(target, pts, {
    width: 2.5, color: ink.cold, intensity: mix(1.35, 1, ink.k),
    alpha: (j) => { const i = j + first; return alpha * (i <= nowI ? smoothstep(0, nowI * 0.6, i) : 0.28 * (1 - (i - nowI) / Math.max(n - nowI, 1))); },
  });
}

export default {
  id: 's06_volunteers',
  section: SECTION,
  // a dissolve over the two beats before the downbeat, through which s05's strand holds the rest pose: one strand
  enter: { kind: 'dissolve', beats: 2 },
  assets: ['text.json', 'throat/lead-0.00-whole.lf0', 'throat/lead-0.00-whole.flags', 'throat/lead-0.60.lf0', 'throat/lead-0.60.flags'],
  async init(ctx) {
    // an untextured rects call samples whatever unit 0 holds, which can be the target being drawn (a feedback
    // loop that drops the draw): hatching is drawn through this white texel instead
    S.white = ctx.g.texture({ width: 1, height: 1, data: new Uint8Array([255, 255, 255, 255]) }, { filter: 'nearest' });
    setup(ctx);
  },
  light(ctx, t) {
    return clamp(ctx.timeline.human(t) / 0.75) * returned(ctx, t);
  },
  render(ctx, t, target) {
    const k = ctx.k(t), ink = ctx.palette.inks(k), L = S.lines, B = S.beat, end = S.sec.t1;
    ground(ctx, t, target, k);
    const hand = ctx.palette.hand(S.takes, ink.side), handMoved = ctx.palette.hand(S.movedRows, ink.side);
    // the strand at rest at the first downbeat, drawn out into the lane's bars
    const rest = 1 - smoothstep(S.sec.t0, S.sec.t0 + 2 * B, t);
    if (rest > 0) restStrand(ctx, t, target, ink, rest);
    drawLane(ctx, t, target, ink, ctx.palette.hand(S.pages, ink.side), handMoved);
    // the tallies: a group to each sixteenth from the third beat; struck out from "and" to "goes"
    drawTally(ctx, t, target, S.strokes, { color: hand, t0: S.sec.t0 + 2 * B, per: B / 4, strike0: S.goes.t0, strike1: S.goesEnd.t0 });
    // line 3: the whole sung line across the frame
    const L3 = L[2], L4 = L[3];
    const pin = smoothstep(L3.t0 - 0.3, L3.t0, t), pout = 1 - smoothstep(L4.t0 + B * 0.6, L4.t0 + B * 1.5, t);
    drawProof(ctx, t, target, S.proof, { ink, hand, alpha: pin * pout, white: S.white,
      sweep: ease.inOutCubic((t - (L3.t0 - 0.3)) / (B * 1.2)) });
    // line 4, until the strand comes back to rest in the section's last beat
    const mAlpha = 1 - smoothstep(end - 1.3 * B, end - 0.5 * B, t);
    drawMoved(ctx, t, target, S.staves, { ink, hand: handMoved, t0: L4.t0 + 1.5 * B, stagger: 0.42, alpha: mAlpha, white: S.white });
    const back = smoothstep(end - B, end, t);
    if (back > 0) restStrand(ctx, t, target, ink, back, ease.outCubic(back));
    // labels: in after t0, out before t1, so one ending where the next begins never overlaps it
    const cue = (key, t0, t1, opts = {}) => {
      const a = smoothstep(t0, t0 + 0.4, t) * (1 - smoothstep(t1 - 0.4, t1, t));
      if (a > 0) label(ctx, t, target, key, { alpha: a, size: 24, ...opts });
    };
    cue('takes', L[0].t0 + B, L[0].t1 + 0.06);
    cue('numbers', L[1].t0, L[2].t0);
    cue('machine', L[2].t0, L[3].t0 + B, { color: ink.ruleStrong });
    cue('moved', L[3].t0 + B, end - 0.3);
    lyric(ctx, t, target, { focus: ctx.timeline.line(t) === L[0] && t >= S.sec.t0 ? 'italic' : null });
  },
};
