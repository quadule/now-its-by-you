// The synced cut, 1080 x 1920: draw(t) paints the frame at t seconds of synced/cut.wav. Pure in t.
//
// Above, the family: every version rendered for this, grown from the release at the root; the one singing is
// the coal, its line of descent inked from the root to it. Below, the music as heard on the cut's clock: the
// lead at its sung pitch (a learned ornament in red), the earlier versions' singers in harmony as hairlines,
// the band fainter, each chunk's notes from the version that plays it. Then the sung line; a word that differs
// from the release's is red.

const W = 1080, H = 1920;
const C = { paper: '#f4ecdc', ink: '#2b231d', ink2: '#554737', ink3: '#6b5c4b', rule: '#d6c8ae', ruleStrong: '#8f7d66', red: '#a3361f' };
const SERIF = '"Cut Serif", Georgia, serif';
const DEG = Math.PI / 180;

// the tree
const ROOT = [540, 850];
const STEP = 100;         // one generation
const TWIG = 100;         // a version made straight from the release in another style
const FAN = [-158, -22];  // the directions the release's children leave in
// the music
const PLAY = W / 2, PX = 175;
const PITCH = { mid: 64, y: 1110, semi: 11 };
const BAND = { top: 925, bottom: 1290 };
const PERC_Y = 1302;
// the line
const LYRIC_Y = 1372;

const cv = document.getElementById('c');
const g = cv.getContext('2d');
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const ease = (x) => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
const plain = (s) => (s || '').replace(/\*/g, '');
const hash = (s) => { let h = 2166136261; for (const ch of s) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return ((h >>> 0) % 10000) / 10000; };

let D, T;

// the tree's layout: the release's children in a fan; a child that has children of its own leads a lineage,
// each generation a step on from its parent, turned a little by its own id and by a change of key
function layout() {
  const byId = new Map(D.tree.map((n) => [n.id, { ...n, kids: [] }]));
  let root;
  for (const n of byId.values()) {
    if (n.parent) byId.get(n.parent).kids.push(n);
    else root = n;
  }
  const depth = (n) => 1 + Math.max(0, ...n.kids.map(depth));
  // lineages and single children alternate round the fan, the longest lineages nearest the middle
  const kids = root.kids.slice().sort((a, b) => a.path.localeCompare(b.path));
  const long = kids.filter((k) => k.kids.length), short = kids.filter((k) => !k.kids.length);
  const order = [];
  const L = long.slice(), S = short.slice();
  while (L.length || S.length) {
    if (S.length) order.push(S.shift());
    if (L.length) order.push(L.shift());
  }
  root.x = ROOT[0]; root.y = ROOT[1];
  order.forEach((k, i) => {
    const a = (FAN[0] + (FAN[1] - FAN[0]) * (i + 0.5) / order.length) * DEG;
    place(k, root, a, k.kids.length ? STEP : TWIG);
  });
  function place(n, parent, dir, len) {
    n.dir = dir;
    n.x = clamp(parent.x + Math.cos(dir) * len, 60, W - 60);
    n.y = parent.y + Math.sin(dir) * len;
    n.from = parent;
    // a lineage climbs: each step turns toward upright, by its own id, and by its change of key
    for (const k of n.kids) {
      const toward = (-90 * DEG - dir) * 0.16;
      const own = (hash(k.id) - 0.5) * 16 * DEG;
      const key = (k.tonic - n.tonic) * 4 * DEG;
      place(k, n, dir + toward + own + key, STEP * (0.92 + 0.16 * hash(k.id + 'l')));
    }
  }
  const nodes = [...byId.values()];
  const byPath = new Map(nodes.map((n) => [n.path, n]));
  return { root, nodes, byPath };
}

// a branch from its parent: a gentle curve, bowed by the node's own id
function branch(n, upto = 1) {
  const p = n.from;
  const mx = (p.x + n.x) / 2, my = (p.y + n.y) / 2;
  const dx = n.x - p.x, dy = n.y - p.y, len = Math.hypot(dx, dy);
  const bow = (hash(n.id + 'b') - 0.5) * 0.35 * len;
  const cx = mx - dy / len * bow, cy = my + dx / len * bow;
  g.moveTo(p.x, p.y);
  if (upto >= 1) { g.quadraticCurveTo(cx, cy, n.x, n.y); return; }
  // part of the curve: de Casteljau to upto
  const ax = p.x + (cx - p.x) * upto, ay = p.y + (cy - p.y) * upto;
  const bx = cx + (n.x - cx) * upto, by = cy + (n.y - cy) * upto;
  g.quadraticCurveTo(ax, ay, ax + (bx - ax) * upto, ay + (by - ay) * upto);
}

function lineage(n) {
  const out = [];
  for (let m = n; m.from; m = m.from) out.unshift(m);
  return out;
}

function chunkAt(t) {
  let i = 0;
  for (let j = 0; j < D.chunks.length; j++) if (t >= D.chunks[j].t0) i = j;
  return i;
}

function tree(t, ci) {
  g.save();
  g.lineCap = 'round';
  // every version
  g.strokeStyle = C.ink3;
  g.globalAlpha = 0.42;
  g.lineWidth = 1.6;
  g.beginPath();
  for (const n of T.nodes) if (n.from) branch(n);
  g.stroke();
  g.globalAlpha = 1;
  for (const n of T.nodes) {
    g.fillStyle = C.ink3;
    g.globalAlpha = 0.6;
    g.beginPath(); g.arc(n.x, n.y, n.used ? 4 : 2.6, 0, Math.PI * 2); g.fill();
  }
  // the lines of descent heard so far, and the one singing now drawn in from the root
  const heard = new Set();
  for (let j = 0; j < ci; j++) heard.add(D.chunks[j].version);
  g.strokeStyle = C.ink2;
  g.globalAlpha = 0.75;
  g.lineWidth = 2.4;
  g.beginPath();
  const drawn = new Set();
  for (const path of heard) for (const m of lineage(T.byPath.get(path))) if (!drawn.has(m)) { drawn.add(m); branch(m); }
  g.stroke();
  const c = D.chunks[ci];
  const node = T.byPath.get(c.version);
  const steps = lineage(node);
  const grow = ease((t - c.t0) / 0.22) * steps.length;
  g.globalAlpha = 1;
  g.strokeStyle = C.ink;
  g.lineWidth = 4;
  g.beginPath();
  steps.forEach((m, k) => { if (grow > k) branch(m, Math.min(1, grow - k)); });
  g.stroke();
  for (const path of heard) { const m = T.byPath.get(path); g.fillStyle = C.ink2; g.beginPath(); g.arc(m.x, m.y, 5, 0, Math.PI * 2); g.fill(); }
  // the root
  g.fillStyle = C.ink;
  g.beginPath(); g.arc(T.root.x, T.root.y, 7, 0, Math.PI * 2); g.fill();
  // the coal and the version's style
  const arrived = grow >= steps.length;
  const k = Math.min(Math.floor(grow), steps.length - 1);
  const at = arrived || !steps.length ? node : steps[k];
  g.fillStyle = C.red;
  g.beginPath(); g.arc(at.x, at.y, 11, 0, Math.PI * 2); g.fill();
  if (arrived && node.style) {
    const right = node.x < W - 260;
    g.font = `italic 34px ${SERIF}`;
    g.fillStyle = C.ink;
    g.textAlign = right ? 'left' : 'right';
    g.textBaseline = 'middle';
    g.globalAlpha = ease((t - c.t0 - 0.2) / 0.15);
    g.fillText(D.copy.styles[node.style] || node.style, Math.round(node.x + (right ? 22 : -22)), Math.round(node.y - 2));
  }
  g.restore();
}

const yOf = (p) => PITCH.y - (p - PITCH.mid) * PITCH.semi;
const xOf = (t, now) => PLAY + (t - now) * PX;

// the music: each chunk's notes drawn only over the span its version is heard
function music(t, k) {
  g.save();
  g.lineCap = 'round';
  for (let j = 0; j < D.chunks.length; j++) {
    const c = D.chunks[j];
    const xa = xOf(c.t0, t), xb = xOf(c.t1, t);
    if (xb < 0 || xa > W) continue;
    g.save();
    g.beginPath(); g.rect(Math.max(xa, 0), BAND.top - 40, Math.min(xb, W) - Math.max(xa, 0), PERC_Y - BAND.top + 60); g.clip();
    const fade = (x) => ease(Math.min(x - 20, W - 20 - x) / 160);
    // the band
    for (const [part, t0, t1, p, v, perc] of c.band) {
      const x0 = xOf(t0, t), x1 = xOf(t1, t);
      if (x1 < xa - 2 || x0 > xb + 2) continue;
      const on = t >= t0 && t < t1;
      if (perc) {
        const hit = t >= t0 && t - t0 < 0.3 ? 1 - (t - t0) / 0.3 : 0;
        g.globalAlpha = k * fade(x0) * (0.35 + 0.6 * hit);
        g.strokeStyle = hit ? C.red : C.ink3;
        g.lineWidth = 2 + 2 * hit;
        g.beginPath(); g.moveTo(x0, PERC_Y); g.lineTo(x0, PERC_Y - 10 - 26 * v - 18 * hit); g.stroke();
        continue;
      }
      const y = yOf(p);
      if (y < BAND.top || y > BAND.bottom) continue;
      g.globalAlpha = k * fade((x0 + x1) / 2) * (on ? 0.75 : 0.28 + 0.2 * v);
      g.strokeStyle = on ? C.ink2 : C.ink3;
      g.lineWidth = on ? 2.4 : 1.4;
      g.beginPath(); g.moveTo(x0, y); g.lineTo(Math.max(x1, x0 + 1.5), y); g.stroke();
    }
    // the earlier versions' singers
    for (const [, t0, t1, p] of c.choir) {
      const x0 = xOf(t0, t), x1 = xOf(t1, t), y = yOf(p);
      if (x1 < xa || x0 > xb || y < BAND.top || y > BAND.bottom) continue;
      const sung = t >= t0;
      g.globalAlpha = k * fade((x0 + x1) / 2) * (sung ? 0.85 : 0.35);
      g.strokeStyle = C.ink2;
      g.lineWidth = 1.6;
      g.beginPath(); g.moveTo(x0 + 2, y); g.lineTo(Math.max(x1 - 2, x0 + 3), y); g.stroke();
    }
    // the lead
    for (const [t0, t1, p, orn] of c.voice) {
      const x0 = xOf(t0, t), x1 = xOf(t1, t), y = yOf(p);
      if (x1 < xa || x0 > xb) continue;
      const sung = t >= t0, on = t >= t0 && t < t1;
      g.globalAlpha = k * fade((x0 + x1) / 2) * (sung ? 1 : 0.32);
      g.strokeStyle = C.ink;
      g.lineWidth = on ? 9 : 7;
      g.beginPath(); g.moveTo(x0 + 4, y); g.lineTo(Math.max(x1 - 4, x0 + 5), y); g.stroke();
      if (orn) {
        // the learned ornament: its own shape over the note, in red
        g.strokeStyle = C.red;
        g.lineWidth = 4;
        g.beginPath();
        const span = Math.max(x1 - x0, 30);
        orn.forEach(([f, st], i) => {
          const x = x0 + 4 + f * span, yy = y - st * PITCH.semi;
          if (i === 0) g.moveTo(x, yy); else g.lineTo(x, yy);
        });
        g.lineTo(x0 + 4 + Math.min(1, orn[orn.length - 1][0] + 0.25) * span, y - orn[orn.length - 1][1] * PITCH.semi);
        g.stroke();
      }
    }
    g.restore();
    // the cut
    if (j > 0 && xa > 0 && xa < W) {
      g.globalAlpha = k * 0.5 * fade(xa);
      g.strokeStyle = C.ruleStrong;
      g.lineWidth = 1;
      g.beginPath(); g.moveTo(Math.round(xa) + 0.5, BAND.top - 30); g.lineTo(Math.round(xa) + 0.5, PERC_Y + 8); g.stroke();
    }
  }
  // the playhead
  g.globalAlpha = k * 0.6;
  g.strokeStyle = C.red;
  g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(PLAY, BAND.top - 30); g.lineTo(PLAY, PERC_Y + 8); g.stroke();
  g.restore();
}

function lyric(t, k) {
  const line = D.lines.find((l) => t >= l.t0 - 0.05 && t < l.t1 + 0.05);
  if (!line) return;
  const fade = ease((t - line.t0 + 0.05) / 0.1) * ease((line.t1 + 0.05 - t) / 0.1) * k;
  const words = [];
  let cur = null;
  for (const s of line.syl) {
    if (!cur) { cur = { parts: [], italic: false, changed: false, chunk: s.chunk }; words.push(cur); }
    cur.parts.push(s);
    if (s.syl.includes('*')) cur.italic = true;
    if (s.changed) cur.changed = true;
    if (!s.cont) cur = null;
  }
  const size = 54, space = size * 0.28;
  const measure = (w) => { g.font = `${w.italic ? 'italic ' : ''}${size}px ${SERIF}`; return g.measureText(w.parts.map((p) => plain(p.syl)).join('')).width; };
  // two rows when long: broken between words where one version hands over to the next, nearest the middle
  const widths = words.map(measure);
  const total = widths.reduce((a, w) => a + w, 0) + space * (words.length - 1);
  const rows = [words.map((w, i) => [w, widths[i]])];
  if (total > 860) {
    const cands = [];
    let acc = 0;
    for (let i = 0; i < words.length - 1; i++) {
      acc += widths[i] + space;
      cands.push({ i, d: Math.abs(acc - total / 2), fits: acc - space <= 900 && total - acc <= 900, hand: words[i + 1].chunk !== words[i].chunk });
    }
    const pool = cands.filter((c) => c.hand && c.fits);
    const best = (pool.length ? pool : cands).reduce((a, c) => (c.d < a.d ? c : a)).i;
    rows.splice(0, 1, rows[0].slice(0, best + 1), rows[0].slice(best + 1));
  }
  const y0 = rows.length === 1 ? LYRIC_Y + 34 : LYRIC_Y;
  g.save();
  rows.forEach((row, ri) => {
    const rw = row.reduce((a, [, ww], i) => a + ww + (i ? space : 0), 0);
    let x = W / 2 - rw / 2;
    for (const [w] of row) {
      g.font = `${w.italic ? 'italic ' : ''}${size}px ${SERIF}`;
      g.fillStyle = w.changed ? C.red : C.ink;
      for (const p of w.parts) {
        const txt = plain(p.syl);
        g.globalAlpha = fade * (t >= p.t0 ? 1 : 0.3);
        g.fillText(txt, Math.round(x), Math.round(y0 + ri * 70));
        x += g.measureText(txt).width;
      }
      x += space;
    }
  });
  g.restore();
}

// when the last note ends
function endCard() {
  const c = D.chunks[D.chunks.length - 1];
  const s = c.sung[c.sung.length - 1];
  return s.t1;
}

export function draw(t) {
  g.globalAlpha = 1;
  g.fillStyle = C.paper;
  g.fillRect(0, 0, W, H);
  const ci = chunkAt(t);
  // the end: the music and the line go after the last note, then the title comes
  const end = endCard();
  const out = ease((t - end - 0.2) / 0.5), e = ease((t - end - 0.8) / 0.8);
  tree(t, ci);
  music(t, 1 - out);
  lyric(t, 1 - out);
  if (e > 0) {
    g.save();
    g.globalAlpha = e;
    g.textAlign = 'center';
    g.font = `italic 90px ${SERIF}`;
    g.fillStyle = C.ink;
    g.fillText(D.copy.title, W / 2, 1130);
    g.font = `34px ${SERIF}`;
    g.fillStyle = C.red;
    g.fillText(D.copy.site, W / 2, 1210);
    g.restore();
  }
}

async function init() {
  const faces = [['/fonts/Georgia.ttf', 'normal'], ['/fonts/Georgiai.ttf', 'italic']];
  for (const [url, style] of faces) document.fonts.add(await new FontFace('Cut Serif', `url(${url})`, { style }).load());
  D = await (await fetch('/synced/picture.json')).json();
  T = layout();
  window.cut = { draw, duration: D.duration };
  const q = new URLSearchParams(location.search);
  if (q.has('capture')) { document.body.classList.add('capture'); draw(Number(q.get('t') || 0)); return; }
  const slider = document.getElementById('t'), tt = document.getElementById('tt');
  slider.max = D.duration;
  const audio = new Audio('/synced/cut.wav');
  const show = (t) => { draw(t); tt.textContent = t.toFixed(2); };
  slider.oninput = () => { audio.currentTime = Number(slider.value); show(Number(slider.value)); };
  document.getElementById('play').onclick = () => (audio.paused ? audio.play() : audio.pause());
  const loop = () => { if (!audio.paused) { slider.value = audio.currentTime; show(audio.currentTime); } requestAnimationFrame(loop); };
  loop();
  show(Number(q.get('t') || 0));
}
window.cutReady = init();
