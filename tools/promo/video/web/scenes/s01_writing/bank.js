// The bank: the genome's 51 verses (text.json bank, kind verse, in its order) as a deep field of type, two walls
// of verses receding to the strand's centre, each verse with its id and its `by` set small in the margin beside it.
// The viewer travels in depth toward the vanishing point, a step each beat, easing to a stop on the beat. The verse
// the song sings first (sings.entries' first verse) waits at the far centre, comes forward out of the field and
// settles large; as it settles its syllable hyphens close, so the bank's syllables become the words to be sung.
// Lines a person wrote take the hand ink: lines `by` names as the artist's, and the record's rewritten lines
// (sings.rewritten, the artist's own). A verse written with the artist where the lines are not told apart has its
// margin note in the hand ink.
import { clamp, smoothstep, smootherstep, mix, ease } from '../../core/math.js';

const F = 1000;            // the viewer's focal length, design units
const PLANE = 1;          // the floor and the ceiling, this far below and above the eye (the strand is the horizon)
const S = 0.19;           // a verse's type size on its plane
const RASTER = 40;        // the size its lines are set at (drawn in perspective)
const LEAD = 1.5;         // line spacing, in type sizes
const NOTE = 0.62;        // the margin note's size, in type sizes
const GAP = 2.2;          // space between verses in a column, in type sizes
const LANE = [0.08, 0.215];  // the clear lane's half-width at world depth Z: LANE[0] + LANE[1] * Z (the register's)
const Z0 = 1.05;          // the nearest verse when the field opens
const TRAVEL = 3.2;       // how far the viewer glides
const FOG = [3.2, 8.5];   // depths over which the field fades into the horizon
const SUNG = 46;          // the sung verse's type once settled
const SUNG_TOP = 236;     // and its first baseline

// what a verse's `by` says the artist wrote: 'all' lines, a list of line indices, 'shared' (not told apart), or none
export function artistLines(entry) {
  const by = entry.by || '';
  if (!/artist/.test(by)) return null;
  if (/after the artist's/.test(by)) return null;           // written by another after the artist's draft
  if (/^artist \(first line\)/.test(by)) return [0];
  if (/last line the artist's/.test(by)) return [entry.lines.length - 1];
  if (/^artist$/.test(by)) return 'all';
  return 'shared';
}

// a bank line as the genome writes it, its focus marks dropped (syllable breaks and slots kept: they are the bank's)
const clean = (line) => line.replace(/\*/g, '');

// a margin note's lines: the id, then `by` broken at about 30 characters
function noteLines(id, by) {
  const out = [id];
  let row = '';
  for (const w of (by || '').split(' ')) {
    if (row && (row + ' ' + w).length > 30) { out.push(row); row = w; } else row = row ? row + ' ' + w : w;
  }
  if (row) out.push(row);
  return out;
}

// the sung verse's syllables laid out twice: as the bank writes them (hyphens) and closed up into words
function syllableLayout(ctx, lines) {
  const sp = (s) => ctx.type.text(s, { role: 'lyric', size: SUNG });
  const space = sp('a a').width - sp('aa').width, hy = sp('-');
  return lines.map((l) => {
    const pieces = [];
    let xo = 0, xc = 0;
    l.text.split(' ').forEach((word, wi) => {
      if (wi) { xo += space; xc += space; }
      const syl = word.split('-');
      syl.forEach((s, si) => {
        const spr = sp(s);
        pieces.push({ spr, xo, xc });
        xo += spr.width; xc += spr.width;
        if (si < syl.length - 1) { pieces.push({ spr: hy, xo, xc, hyphen: true }); xo += hy.width; }
      });
    });
    return { pieces, wo: xo, wc: xc, hand: l.hand };
  });
}

export function buildBank(ctx) {
  const text = ctx.data.get('text.json');
  const verses = text.bank.filter((e) => e.kind === 'verse');
  const first = (text.sings.entries.find((e) => e.startsWith('verse:')) || '').split(':')[1];
  const rewritten = text.sings.rewritten || {};
  const cards = verses.map((e, index) => {
    const mine = artistLines(e);
    const re = rewritten[`verse:${e.id}`] || {};
    const lines = e.lines.map((l, i) => {
      const own = re[String(i)];
      const hand = own !== undefined || mine === 'all' || (Array.isArray(mine) && mine.includes(i));
      return { text: clean(own !== undefined ? own : l), hand: hand ? (own !== undefined ? 'record' : e.by) : null };
    });
    return { id: e.id, by: e.by, index, lines, note: noteLines(e.id, e.by), noteHand: mine ? e.by : null, sung: e.id === first };
  });
  const sung = cards.find((c) => c.sung);
  // the others in the bank's order, nearest first, dealt to four columns: floor and ceiling, left and right of the lane
  const depth = S * (NOTE * 1.6 + 4 * LEAD + GAP);
  cards.filter((c) => !c.sung).forEach((c, j) => {
    c.plane = j % 4 < 2 ? 1 : -1;
    c.side = j % 2 ? 1 : -1;
    c.z = Z0 + Math.floor(j / 4) * depth + (j % 4) * depth / 4;
  });
  if (sung) {
    sung.layout = syllableLayout(ctx, sung.lines);
    sung.z = TRAVEL + 1.6;
  }
  return { cards, sung, count: verses.length };
}

// a sprite's baseline-left at (x, y), drawn at scale sc
function drawAt(ctx, target, spr, x, y, sc, opts) {
  const p = spr.pad;
  ctx.type.draw(target, spr, x - p * sc + p, y - (p + spr.ascent) * sc + p, { ...opts, valign: 'top', scale: sc, snap: false });
}

// the viewer's travel at t: a step each beat, eased so it comes to rest on the beat
function travel(ctx, t, T) {
  const beats = ctx.timeline.beats.filter((b) => b >= T.start - 1e-6 && b < T.stream1 - 1e-6);
  let done = 0;
  // each step eased over most of its beat: the nearest lines move under about 10 px a frame at the frame's edge
  for (const b of beats) done += ease.inOutSine(clamp((t - b) / (ctx.timeline.beatLength * 0.85)));
  return TRAVEL * done / Math.max(beats.length, 1);
}

// a point on a plane (1 the floor, -1 the ceiling) at world x X and depth z from the viewer
const onPlane = (X, z, plane) => [960 + (X * F) / z, 540 + (plane * PLANE * F) / z];

// a sprite lying on a plane: its box from X0 across, from depth z0 back; letters' feet toward the viewer on the
// floor and toward the horizon on the ceiling, so both read upright
function planeQuad(spr, X0, z0, plane, size) {
  const w = spr.w * size / RASTER, h = spr.h * size / RASTER;
  const near = z0, far = z0 + h;
  const [topZ, botZ] = plane > 0 ? [far, near] : [near, far];
  return [onPlane(X0, topZ, plane), onPlane(X0 + w, topZ, plane), onPlane(X0 + w, botZ, plane), onPlane(X0, botZ, plane)];
}

const lane = (Z) => LANE[0] + LANE[1] * Z;

// The field at t. T: {start, stream1 (the viewer stops), rise0, rise1 (the sung verse settles), close0, close1, out0, out1}
export function drawBank(ctx, t, target, ink, bank, T) {
  const open = ease.outCubic(clamp((t - T.start) / ctx.timeline.beatLength));
  if (open <= 0) return;
  const cam = travel(ctx, t, T);
  const settle = ease.inOutCubic(clamp((t - T.rise0) / (T.rise1 - T.rise0)));
  const fieldA = open * (1 - smoothstep(T.rise0 + (T.rise1 - T.rise0) * 0.3, T.rise1, t));
  const draw = (spr, quad, color, alpha) => ctx.g.mesh(target, spr.tex, quad.flat(), { alpha, tint: color, srgb: true });
  if (fieldA > 0.002) {
    const items = [];
    for (const c of bank.cards) {
      if (c.sung) continue;
      // the column, from its heading (the margin note) through its four lines; the floor's read away from the viewer
      const rows = [{ note: true }, ...c.lines.map((l, i) => ({ l, i }))];
      rows.forEach((r, k) => {
        const off = k === 0 ? 0 : S * (NOTE * 1.6 + (k - 1) * LEAD);
        // floor: heading farthest, line 4 nearest; ceiling: heading nearest
        const Zw = c.plane > 0 ? c.z + S * (NOTE * 1.6 + 4 * LEAD) - off - (k === 0 ? S * NOTE : S) : c.z + off;
        items.push({ c, r, Zw, z: Zw - cam });
      });
    }
    items.sort((a, b) => b.z - a.z);
    for (const { c, r, Zw, z } of items) {
      if (z < 0.42) continue;
      // the ceiling's left column stays clear of the label at the upper left
      const clear = c.plane < 0 && c.side < 0 ? smoothstep(2.9, 3.4, z) : 1;
      const a = fieldA * clear * smoothstep(0.42, 0.75, z) * (1 - smoothstep(FOG[0], FOG[1], z));
      if (a <= 0.004) continue;
      const edge = lane(Zw);
      if (r.note) {
        const spr = ctx.type.text(c.note.map((n, i) => (i ? n : n.toUpperCase())).join(' · '), { role: 'label', size: RASTER, oversample: 1.001 });
        const size = S * NOTE, w = spr.w * size / RASTER;
        const X0 = c.side < 0 ? -edge - w : edge;
        const color = c.noteHand ? ctx.palette.hand(c.noteHand, ink.k) : ink.red;
        draw(spr, planeQuad(spr, X0, z, c.plane, size), color, a * 0.85);
      } else {
        const spr = ctx.type.text(r.l.text, { role: 'lyric', size: RASTER, oversample: 1.001 });
        const w = spr.w * S / RASTER;
        const X0 = c.side < 0 ? -edge - w : edge;
        const color = r.l.hand ? ctx.palette.hand(r.l.hand, ink.k) : ink.ink2;
        draw(spr, planeQuad(spr, X0, z, c.plane, S), color, a * (r.l.hand ? 1 : 0.9));
      }
    }
  }
  // the sung verse: it lies on the ceiling in the lane, clear of the register below the strand, comes down, turns to
  // face the viewer and settles above the strand
  const c = bank.sung;
  if (!c) return;
  const outA = 1 - smoothstep(T.out0, T.out1, t);
  if (outA <= 0) return;
  const close = ease.inOutCubic(clamp((t - T.close0) / (T.close1 - T.close0)));
  const lead = SUNG * LEAD * 0.95;
  const widestO = Math.max(...c.layout.map((l) => l.wo));
  if (settle < 1) {
    // narrow enough to lie in the lane
    const size = S * 0.55;
    c.lines.forEach((l, i) => {
      const spr = ctx.type.text(l.text, { role: 'lyric', size: SUNG, oversample: 1.001 });
      const w = spr.w * size / RASTER * (RASTER / SUNG);
      const zl = c.z - cam + i * size * LEAD;
      const flat = planeQuad({ w: spr.w * RASTER / SUNG, h: spr.h * RASTER / SUNG }, -w / 2, Math.max(zl, 0.5), -1, size);
      const left = 960 - widestO / 2 - spr.pad, top = SUNG_TOP + i * lead - spr.ascent - spr.pad;
      const up = [[left, top], [left + spr.w, top], [left + spr.w, top + spr.h], [left, top + spr.h]];
      // it squares up early in the move, so the type does not lean as it turns
      const sq = ease.outCubic(settle);
      const quad = flat.map((p, k) => [mix(p[0], up[k][0], sq), mix(p[1], up[k][1], sq)]);
      // it shows on the ceiling for the beat before it comes down
      const za = smoothstep(T.rise0 - ctx.timeline.beatLength, T.rise0, t);
      const color = l.hand ? ctx.palette.hand(l.hand, ink.k) : ink.ink;
      draw(spr, quad, color, open * outA * mix(za, 1, settle));
    });
    return;
  }
  const widest = Math.max(...c.layout.map((l) => mix(l.wo, l.wc, close)));
  const left = 960 - widest / 2;
  c.layout.forEach((l, i) => {
    const y = SUNG_TOP + i * lead;
    const color = l.hand ? ctx.palette.hand(l.hand, ink.k) : ink.ink;
    for (const p of l.pieces) {
      const pa = p.hyphen ? 1 - close : 1;
      if (pa <= 0.003) continue;
      ctx.type.draw(target, p.spr, Math.round(left + mix(p.xo, p.xc, close)), Math.round(y), { color, alpha: outA * pa });
    }
  });
}
