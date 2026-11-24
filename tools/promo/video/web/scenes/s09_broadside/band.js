// Line 4: the red band is rolled on across the top, left to right, from the line's first word to "now"; then the
// face's own title is cut out of it word by word: "Now" on the sung "now", the rest on "it by you", each word opening left to right from
// its syllable's start.
import { clamp, smoothstep } from '../../core/math.js';

export class Band {
  init(ctx, F) {
    this.F = F;
    const line = ctx.timeline.lineOf('refrain3', 3);
    this.line = line;
    const syl = line.words.flatMap((w) => w.syllables);
    // the title's words (Now, It's, by, You) on the sung "now", then the line's last "it", "by", "you"
    const plain = (w) => w.text.replace(/[^a-z]/gi, '').toLowerCase();
    const at = (word, from) => syl.find((s) => s.t0 >= from && plain(s) === word);
    const now = at('now', -Infinity), you = syl[syl.length - 1], by = syl[syl.length - 2], it = syl[syl.length - 3];
    const keyed = [now, it, by, you];
    this.words = F.json.title.words.map(([x0, x1], i) => ({ x0, x1, t: keyed[i].t0, d: Math.min(keyed[i].t1 - keyed[i].t0, 0.3) }));
    // the band is laid over the bar before "now"
    this.printT = Math.min(syl[0].t0, now.t0 - ctx.timeline.barLength / 2);
    this.handT = this.words[0].t;
    // the roller's way: across the band's columns (crop px), done as "now" is sung
    this.roll = { x0: 100, x1: 3590, t0: this.printT, t1: this.words[0].t - 0.05, edge: 14 };
  }

  plates(t, st) {
    st.band = smoothstep(this.printT, this.printT + 0.06, t);
    return st;
  }

  // the band lands a little out of register and settles (crop px)
  offset(t) {
    const k = clamp((t - this.printT) / 0.6);
    if (k <= 0 || k >= 1) return [0, 0];
    const d = Math.exp(-5 * k) * Math.cos(k * 10);
    return [10 * d, -6 * d];
  }

  // per crop column: the roller's lay (-1 not yet, 0 laid) and then the title's cut (0..1)
  fill(t) {
    const data = this.F.titleData, R = this.roll;
    const front = R.x0 + (R.x1 - R.x0) * clamp((t - R.t0) / (R.t1 - R.t0));
    for (let x = 0; x < data.length; x++) data[x] = -1 + clamp((front - x) / R.edge);
    for (const w of this.words) {
      if (t < w.t) continue;
      const k = clamp((t - w.t) / w.d);  // a cut opening across the word
      const span = w.x1 - w.x0 + 24;
      for (let x = w.x0 - 12; x <= w.x1 + 12; x++) {
        const f = (x - (w.x0 - 12)) / span;
        data[x] = clamp((k * 1.06 - f) / 0.06);
      }
    }
  }

  // the sung line steps back as the title takes the words
  lyricAlpha(t) {
    return 1 - smoothstep(this.words[0].t, this.words[1].t, t);
  }
}
