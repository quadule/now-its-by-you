// Every note of the record, by part, from score.json.
//
//   score.parts                -> part names
//   score.notes(part)          -> [{t, d, p, v, syl, word, sec, phrase, art, g}] in time order
//   score.sounding(part, t)    -> the notes of a part sounding at t (t <= time < t + d + release)
//   score.lead(t)              -> {part, notes}: the part the strand follows at t
//   score.range(part, t0, t1)  -> notes starting in [t0, t1)
import { below } from './timeline.js';

// the parts the strand follows, in order of preference: the sung lead, the stage's lead synth, the whistle
const LEAD = [/^voice$/, /lead/i, /^whistle/];

export class Score {
  constructor(json) {
    this.json = json;
    this.byPart = {};
    for (const [part, notes] of Object.entries(json.parts)) {
      this.byPart[part] = notes.slice().sort((a, b) => a.t - b.t);
      // the longest note so far, to bound the search for sounding notes
      let longest = 0;
      for (const n of this.byPart[part]) longest = Math.max(longest, n.d);
      this.byPart[part].longest = longest;
    }
    this.parts = Object.keys(this.byPart);
    this.leadParts = [];
    for (const rx of LEAD) for (const p of this.parts) if (rx.test(p) && !this.leadParts.includes(p)) this.leadParts.push(p);
  }

  notes(part) { return this.byPart[part] || []; }

  sounding(part, t, release = 0) {
    const ns = this.byPart[part];
    if (!ns) return [];
    const out = [];
    const lo = below(ns, t - ns.longest - release, (n) => n.t) + 1, hi = below(ns, t, (n) => n.t);
    for (let i = Math.max(lo, 0); i <= hi; i++) if (t < ns[i].t + ns[i].d + release) out.push(ns[i]);
    return out;
  }

  range(part, t0, t1) {
    const ns = this.byPart[part] || [];
    const out = [];
    for (let i = below(ns, t0 - 1e-9, (n) => n.t) + 1; i < ns.length && ns[i].t < t1; i++) out.push(ns[i]);
    return out;
  }

  // the latest note of a part to start at or before t
  last(part, t) {
    const ns = this.byPart[part] || [];
    const i = below(ns, t, (n) => n.t);
    return i < 0 ? null : ns[i];
  }

  // the lead at t: the first lead part with a note sounding within `hold` seconds either side
  lead(t, hold = 1.5) {
    for (const part of this.leadParts) {
      const near = this.range(part, t - hold - this.notes(part).longest, t + hold).filter((n) => n.t + n.d + hold > t);
      if (near.length) return { part, notes: this.notes(part) };
    }
    const part = this.leadParts[0] || this.parts[0];
    return { part, notes: this.notes(part) };
  }
}
