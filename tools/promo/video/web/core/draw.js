// Shared drawing for scenes: the ground, the sung line, labels, the strand, the parts' notes.
// Each takes ctx (the scene context), t, and the target, and draws with palette tokens for the scene's paper amount ctx.k(t).
import { clamp, smoothstep, mix } from './math.js';

// the ground at t: the stage, the paper, or a mix of the two
export function ground(ctx, t, target, k = ctx.k(t)) {
  const c = ctx.palette.inks(k).ground;
  ctx.g.clear(target, [c[0], c[1], c[2], 1]);
  ctx.g.ground = c;
  ctx.type.ground = c;
  return c;
}

// The sung line in the frame's top half and the labels along its foot, clear of the people on stage in front of the screen
export const LYRIC_Y = 96, LABEL_Y = 984;

// the line sung at t, set at (x, y) (top of its first row), the sung syllables lit
// focus: null | 'italic' | 'red' sets the line's leaned-on word apart (red: in the red ink)
export function lyric(ctx, t, target, { x = ctx.size.w / 2, y = LYRIC_Y, size = 46, align = 'center', maxWidth = 1500,
  alpha = 1, k = ctx.k(t), focus = null, hold = LYRIC_HOLD } = {}) {
  const { line, out, fade } = held(ctx.timeline, t, hold);
  if (!line) return null;
  const lay = ctx.type.lyric(line, { size, maxWidth, focus });
  const ink = ctx.palette.inks(k);
  // in with a short rise before its first syllable; out quickly as the next line comes in, or slowly `hold` seconds after its last
  const a = alpha * smoothstep(line.t0 - 0.35, line.t0 - 0.1, t) * (1 - smoothstep(out - fade, out, t));
  const box = ctx.type.drawLyric(target, lay, t, x, y, { ink: ink.ink2, lit: ink.sung, focusInk: ink.red, alpha: a, align });
  if (line.section === TITLED.section && line.i === TITLED.i) underline(ctx, t, target, lay, box, ink.red, a);
  return { line, lay, box, alpha: a };
}

// How long a sung line stays up after its last syllable when the next line isn't coming in sooner (seconds), so the words are
// easy to follow
const LYRIC_HOLD = 2.5;

// the line up at t, when it is gone and how long it takes to go: by the next line's rise (quickly), or `hold` (at least 0.6)
// after its last syllable (slowly)
function held(tl, t, hold) {
  const lines = tl.lines;
  for (let i = lines.length - 1; i >= 0; i--) {
    const l = lines[i];
    if (t < l.t0 - 0.35) continue;
    const next = lines[i + 1];
    const late = l.t1 + Math.max(hold, 0.6), swap = next ? next.t0 - 0.35 : Infinity;
    const out = Math.min(late, swap), fade = swap < late ? 0.08 : 0.35;
    return t < out ? { line: l, out, fade } : { line: null };
  }
  return { line: null };
}

// The song's title where it is first sung, refrain 1's last line ending "now it's by you": a red rule drawn under
// those words as they are sung, in whichever scene the line is drawn
const TITLED = { section: 'refrain1', i: 3, words: 4 };

function underline(ctx, t, target, lay, box, color, alpha) {
  const n = lay.line.words.slice(-TITLED.words).reduce((k, w) => k + w.syllables.length, 0);
  const syl = lay.syllables.slice(-n);
  if (!syl.length || t < syl[0].t0 || alpha <= 0) return;
  let x1 = syl[0].x;
  for (const s of syl) if (t >= s.t0) x1 = s.x + s.w * Math.min((t - s.t0) / Math.max(s.t1 - s.t0, 1e-3), 1);
  const x0 = syl[0].x, y = box.y + syl[0].y + lay.sprite.ascent + 9;
  ctx.g.rects(target, [{ x: box.x + x0, y, w: x1 - x0, h: 3, color, alpha }]);
}

// a label from copy.json at (x, y) baseline: letterspaced small capitals
export function label(ctx, t, target, key, { x = 96, y = LABEL_Y, size = 28, align = 'left', alpha = 1, color,
  k = ctx.k(t) } = {}) {
  const text = ctx.label(key);
  const s = ctx.type.text(text, { role: 'label', size });
  const ink = ctx.palette.inks(k);
  ctx.type.draw(target, s, x, y, { color: color || ink.red, alpha, align });
  return s;
}

// The strand: the lead's pitch line through a window of the song, `now` at x = at * width.
// Each note is a level stretch; as the human amount rises it loosens by the note's own gesture
// (its scoop into the note, its vibrato, its fall), as the record sings it.
export function strandPoints(ctx, t, { x0 = 0, x1 = ctx.size.w, at = 0.62, back = 4.5, ahead = 2.5, y = 540,
  semitone = 9, step = 1 / 60, part = null, human = ctx.timeline.human(t) } = {}) {
  const lead = part ? { part, notes: ctx.score.notes(part) } : ctx.score.lead(t);
  const notes = ctx.score.range(lead.part, t - back - 4, t + ahead);
  const tonic = ctx.timeline.tonic;
  const pts = [];
  const X = (s) => x0 + (x1 - x0) * (at + (s - t) / (back + ahead));
  let held = null;
  for (let s = t - back; s <= t + ahead + 1e-9; s += step) {
    let n = null;
    for (const m of notes) if (s >= m.t && s < m.t + m.d) n = m;
    if (n) held = n;
    const m = n || held;
    let p = m ? m.p : tonic;
    if (m && human > 0 && m.g) {
      const into = s - m.t, g = m.g;
      const scoop = (g.scoop || 0) / 100 * Math.exp(-Math.max(into, 0) / 0.06);
      const vib = g.vibrato > 0 ? (g.vibrato / 100) * Math.sin(into * 2 * Math.PI * 5.4) * smoothstep(0.18, 0.4, into) : 0;
      const fall = -(g.fall || 0) / 100 * smoothstep(m.d - 0.12, m.d, into);
      p += human * (scoop + vib + fall);
    }
    pts.push([X(s), y - (p - tonic) * semitone]);
  }
  return { points: pts, part: lead.part, nowX: X(t) };
}

export function strand(ctx, t, target, opts = {}) {
  const { width = 3, k = ctx.k(t), alpha = 1 } = opts;
  const s = strandPoints(ctx, t, opts);
  const ink = ctx.palette.inks(k);
  const color = opts.color || ink.cold;
  const n = s.points.length;
  // ahead of now is unsung: dimmer; behind, the line fades into the past
  const nowI = s.points.findIndex((p) => p[0] >= s.nowX);
  ctx.g.stroke(target, s.points, {
    width, color, intensity: opts.intensity ?? mix(1.35, 1, k),
    alpha: (i) => alpha * (i <= nowI ? smoothstep(0, nowI * 0.6, i) : 0.28 * (1 - (i - nowI) / Math.max(n - nowI, 1))),
  });
  return s;
}

// one lane per part that has entered: a hairline, and a dot for each note sounding on it now
export function lanes(ctx, t, target, { parts = null, x0 = 120, x1 = ctx.size.w - 120, y0 = 170, gap = 25, k = ctx.k(t),
  release = 0.4, low = 36, high = 96 } = {}) {
  const ink = ctx.palette.inks(k);
  const list = (parts || ctx.score.parts).filter((p) => {
    const e = ctx.timeline.entry(p);
    return e && t >= e.t - 0.25;
  });
  const dots = [];
  list.forEach((part, row) => {
    const y = y0 + row * gap, e = ctx.timeline.entry(part);
    const a = smoothstep(e.t - 0.25, e.t + 0.5, t);
    ctx.g.stroke(target, [[x0, y], [x1, y]], { width: 1, color: ink.rule, alpha: a });
    for (const n of ctx.score.sounding(part, t, release)) {
      const into = t - n.t, off = t - (n.t + n.d);
      const v = (n.v ?? 0.7) * Math.exp(-Math.max(into, 0) / 1.2) * (off > 0 ? 1 - off / release : 1);
      dots.push({ x: x0 + (x1 - x0) * clamp((n.p - low) / (high - low)), y, r: 3 + 3 * v, color: ink.sung, alpha: clamp(0.35 + v),
        intensity: mix(1.5, 1, k), soft: (1 - k) * 0.8 });
    }
  });
  ctx.g.points(target, dots);
  return list;
}

// labels cued by the lines of a section: [{line: i, key}] shows `key` through line i of `section`
export function cues(ctx, t, target, section, list, opts = {}) {
  for (const c of list) {
    const l = ctx.timeline.lineOf(section, c.line);
    if (!l) continue;
    const a = smoothstep(l.t0 - 0.4, l.t0, t) * (1 - smoothstep(l.t1 + 0.3, l.t1 + 0.8, t));
    if (a > 0) label(ctx, t, target, c.key, { ...opts, ...c.opts, alpha: a });
  }
}

// a title from copy.json in the book face (not capitals): the song's name, the kicker, the site
export function title(ctx, t, target, key, { x = ctx.size.w / 2, y = 540, size = 84, align = 'center', alpha = 1, italic = false,
  color, k = ctx.k(t) } = {}) {
  const s = ctx.type.text(ctx.label(key), { role: 'lyric', size, italic });
  ctx.type.draw(target, s, x, y, { color: color || ctx.palette.inks(k).ink, alpha, align });
  return s;
}
