// The song's clock: every time in the film comes from timeline.json through this file.
//
//   const tl = await Timeline.load();
//   tl.section(t) -> {id, kind, t0, t1, k (0..1 through it)}
//   tl.line(t)    -> the sung line at t (from a little before its first syllable to a little after its last), or null
//   tl.bar(t), tl.beat(t) -> {i, t0, t1, k}
//   tl.human(t)   -> the record's human amount (a step at each line's start)
//   tl.paper(t)   -> human / 0.75, eased over PAPER_EASE seconds, 0..1: 0 is all stage, 1 all paper
//   tl.entry(part), tl.gain(part, t) (linear: null points silent, linear in gain between points, no curve 1),
//   tl.level(part, t) (dB, -Infinity where silent)
//   tl.byId(id), tl.lines (all), tl.daisy, tl.frames, tl.fps, tl.duration
import { smoothstep, clamp } from './math.js';

const PAPER_EASE = 0.8;      // seconds a step in the human amount takes to reach the ground
const PAPER_FULL = 0.75;     // the human amount that is all paper
const LINE_LEAD = 0.35;      // seconds a line shows before its first syllable
const LINE_TAIL = 0.6;       // and after its last

// the last index i with list[i] <= t (by key), or -1
export function below(list, t, key = (x) => x) {
  let lo = 0, hi = list.length - 1, at = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (key(list[mid]) <= t) { at = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return at;
}

export class Timeline {
  static async load(url = '/data/timeline.json') {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`timeline: ${url} ${r.status}`);
    return new Timeline(await r.json());
  }

  constructor(json) {
    this.json = json;
    this.duration = json.duration;
    this.fps = json.fps;
    this.frames = json.frames;
    this.bpm = json.tempo;
    this.barLength = json.bar;
    this.beatLength = json.bar / 4;
    this.tonic = json.tonic;
    this.key = json.key;
    this.sections = json.sections;
    this.lines = json.lines;
    this.bars = json.bars;
    this.beats = json.beats;
    this.daisy = json.daisy || [];
    this.humanSteps = (json.human || []).slice().sort((a, b) => a[0] - b[0]);
    this.entries = json.entries || [];
    this.levels = json.levels || {};
    this.fixture = !!json.fixture;
    this._ids = Object.fromEntries(this.sections.map((s) => [s.id, s]));
    this.syllables = [];
    for (const l of this.lines) for (const w of l.words) for (const s of w.syllables) this.syllables.push({ ...s, line: l, word: w });
  }

  time(frame) { return frame / this.fps; }
  frame(t) { return Math.round(t * this.fps); }

  byId(id) {
    const s = this._ids[id];
    if (!s) throw new Error(`timeline: no section ${id}`);
    return s;
  }

  section(t) {
    const i = clamp(below(this.sections, t, (s) => s.t0), 0, this.sections.length - 1);
    const s = this.sections[i];
    return { ...s, index: i, k: clamp((t - s.t0) / (s.t1 - s.t0)) };
  }

  // the sections a span covers, as [first, last] ids or one id
  span(ids) {
    const [a, b] = Array.isArray(ids) ? ids : [ids, ids];
    return { t0: this.byId(a).t0, t1: this.byId(b).t1 };
  }

  // the sung line around t; lines of a section by index with lineOf(section, i)
  line(t, lead = LINE_LEAD, tail = LINE_TAIL) {
    let best = null;
    for (const l of this.lines) if (t >= l.t0 - lead && t < l.t1 + tail) best = l;
    return best;
  }
  lineOf(section, i) { return this.lines.find((l) => l.section === section && l.i === i) || null; }
  linesOf(section) { return this.lines.filter((l) => l.section === section); }

  // the syllable sounding at t, or null
  syllable(t) {
    const i = below(this.syllables, t, (s) => s.t0);
    const s = this.syllables[i];
    return s && t < s.t1 ? s : null;
  }

  _grid(list, length, t) {
    const i = below(list, t);
    if (i < 0) return { i: -1, t0: list[0] - length, t1: list[0], k: clamp(1 - (list[0] - t) / length) };
    const t0 = list[i], t1 = list[i + 1] ?? t0 + length;
    return { i, t0, t1, k: clamp((t - t0) / (t1 - t0)) };
  }
  bar(t) { return this._grid(this.bars, this.barLength, t); }
  beat(t) { return this._grid(this.beats, this.beatLength, t); }
  // the bar line nearest t (for cuts on the bar)
  nearestBar(t) {
    let best = this.bars[0];
    for (const b of this.bars) if (Math.abs(b - t) < Math.abs(best - t)) best = b;
    return best;
  }

  human(t) {
    const i = below(this.humanSteps, t, (s) => s[0]);
    return i < 0 ? 0 : this.humanSteps[i][1];
  }

  paper(t) {
    let v = 0, prev = 0;
    for (const [ts, h] of this.humanSteps) {
      if (ts > t) break;
      v += (h - prev) * smoothstep(ts, ts + PAPER_EASE, t);
      prev = h;
    }
    return clamp(v / PAPER_FULL);
  }

  entry(part) { return this.entries.find((e) => e.part === part) || null; }

  // A part's stage level, as the engine plays it (stage.curve): each point [t, dB | null], null silent; linear
  // in gain (10^(dB/20), null 0) between points; the first and last held; a part with no curve is at 0 dB.
  gain(part, t) {
    const pts = this.levels[part];
    if (!pts || !pts.length) return 1;
    const g = (p) => (p[1] === null || p[1] === undefined ? 0 : 10 ** (p[1] / 20));
    const i = below(pts, t, (p) => p[0]);
    if (i < 0) return g(pts[0]);
    if (i >= pts.length - 1) return g(pts[pts.length - 1]);
    const [t0] = pts[i], [t1] = pts[i + 1];
    return t1 > t0 ? g(pts[i]) + (g(pts[i + 1]) - g(pts[i])) * (t - t0) / (t1 - t0) : g(pts[i + 1]);
  }
  // the same in dB (-Infinity where silent)
  level(part, t) {
    const v = this.gain(part, t);
    return v > 0 ? 20 * Math.log10(v) : -Infinity;
  }

  // the daisy's stage at t: how many of its notes have begun, and how far into the newest
  daisyStage(t) {
    let n = 0, k = 0;
    for (const d of this.daisy) if (t >= d.t) { n++; k = clamp((t - d.t) / d.dur); }
    return { n, k };
  }
}
