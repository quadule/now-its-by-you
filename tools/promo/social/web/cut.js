// The social cut, 1080 x 1920: draw(t) paints the frame at t seconds of cut.wav. Pure in t.
//
// The lineage as a tree on paper. The release is the root (its stem is drawn as it sings); the versions
// rendered from it in other styles branch from the root; its descendants, each rendered from the one before,
// make the trunk. Each branch is drawn as the tune its version sings there: the line is bent off its course
// by each sung note's pitch, so every branch carries the same tune. The coal is on the version being heard.

const W = 1080, H = 1920;
const C = { paper: '#f4ecdc', ink: '#2b231d', ink2: '#554737', ink3: '#6b5c4b', rule: '#d6c8ae', red: '#a3361f' };
const SERIF = '"Cut Serif", Georgia, serif';
const ROOT = [540, 1290];
const STEM = 130;      // the release's stem, below the root
const TRUNK = 166;     // each generation's segment
const BEND = 6.5;      // pixels of bend per semitone
const DEG = Math.PI / 180;
// the style versions' directions, in the order they sing: out to both sides, the nearest to the trunk last
const FAN = [-168, -12, -148, -32, -128, -52, -110];

const cv = document.getElementById('c');
const g = cv.getContext('2d');
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const ease = (x) => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
const plain = (s) => (s || '').replace(/\*/g, '');

let D, B;

// every branch's course and its bent line, laid out once
function layout() {
  const out = [];
  let fan = 0, trunkTip = ROOT, trunkDir = -90 * DEG, prev = null;
  for (const c of D.chunks) {
    const notes = c.sung.map((s) => ({ t0: s.t0, t1: s.t1, p: c.voice[s.i].p }));
    const start = c.out0, end = notes[notes.length - 1].t1;
    let from, dir, len;
    if (c.version === 'release') {
      from = [ROOT[0], ROOT[1] + STEM]; dir = -90 * DEG; len = STEM;
    } else if (c.part === 'styles') {
      from = ROOT; dir = FAN[fan++] * DEG; len = clamp(180 + 70 * (c.out1 - c.out0), 240, 390);
    } else {
      from = trunkTip;
      const parent = prev && prev.part !== 'styles' ? prev : D.chunks[0];
      trunkDir = clamp(trunkDir + (c.tonic - parent.tonic) * 7 * DEG, -112 * DEG, -68 * DEG);
      dir = trunkDir; len = TRUNK;
    }
    const ax = [Math.cos(dir), Math.sin(dir)];
    let nrm = [-ax[1], ax[0]];
    if (nrm[1] > 0.1 || (Math.abs(nrm[1]) <= 0.1 && nrm[0] < 0)) nrm = [-nrm[0], -nrm[1]];
    const mean = notes.reduce((a, n) => a + n.p, 0) / notes.length;
    const u = (t) => clamp((t - start) / (end - start), 0, 1);
    // the pitch at each point of the branch: each note's own, glided into, held through a rest
    const N = 160, pts = [];
    for (let k = 0; k <= N; k++) {
      const f = k / N, t = start + f * (end - start);
      let p = notes[0].p;
      for (let j = 0; j < notes.length; j++) {
        if (t >= notes[j].t0) {
          const prevP = j ? notes[j - 1].p : notes[j].p;
          p = prevP + (notes[j].p - prevP) * ease((t - notes[j].t0) / 0.07);
        }
      }
      const taper = Math.sin(Math.PI * f) ** 0.6;
      const off = (p - mean) * BEND * taper;
      pts.push([from[0] + ax[0] * len * f + nrm[0] * off, from[1] + ax[1] * len * f + nrm[1] * off]);
    }
    // a name at the tip where the style is not its parent's
    const parent = c.part === 'styles' ? D.chunks[0] : prev && prev.part !== 'styles' ? prev : D.chunks[0];
    const named = c.version !== 'release' && c.style !== parent.style;
    out.push({ c, pts, tip: pts[N], start, end, u, dir, name: named ? D.copy.styles[c.style] || c.style : null });
    if (c.part !== 'styles') trunkTip = pts[N];
    prev = c;
  }
  return out;
}

function stroke(pts, upto, width, color, alpha) {
  const n = Math.floor(upto * (pts.length - 1));
  if (n < 1) return;
  g.save();
  g.globalAlpha = alpha;
  g.strokeStyle = color;
  g.lineWidth = width;
  g.lineCap = 'round';
  g.lineJoin = 'round';
  g.beginPath();
  g.moveTo(pts[0][0], pts[0][1]);
  for (let k = 1; k <= n; k++) g.lineTo(pts[k][0], pts[k][1]);
  const f = upto * (pts.length - 1) - n;
  if (n + 1 < pts.length && f > 0) {
    const a = pts[n], b = pts[n + 1];
    g.lineTo(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f);
  }
  g.stroke();
  g.restore();
}

function at(pts, u) {
  const x = u * (pts.length - 1), n = Math.min(Math.floor(x), pts.length - 2), f = x - n;
  return [pts[n][0] + (pts[n + 1][0] - pts[n][0]) * f, pts[n][1] + (pts[n + 1][1] - pts[n][1]) * f];
}

function dot(x, y, r, color, alpha = 1) {
  if (alpha <= 0) return;
  g.save();
  g.globalAlpha = alpha;
  g.fillStyle = color;
  g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
  g.restore();
}

function tipName(b, a) {
  if (!b.name || a <= 0) return;
  const cx = Math.cos(b.dir), cy = Math.sin(b.dir);
  const trunk = b.c.part !== 'styles';
  g.save();
  g.globalAlpha = a;
  g.font = `italic 31px ${SERIF}`;
  g.fillStyle = C.ink3;
  g.textBaseline = 'middle';
  if (trunk) {
    g.textAlign = 'left';
    g.fillText(b.name, Math.round(b.tip[0] + 22), Math.round(b.tip[1]));
  } else {
    g.textAlign = cx < -0.25 ? 'right' : cx > 0.25 ? 'left' : 'center';
    g.fillText(b.name, Math.round(b.tip[0] + cx * 18), Math.round(b.tip[1] + cy * 18 - (Math.abs(cx) <= 0.25 ? 8 : 0)));
  }
  g.restore();
}

function tree(t, k) {
  let cur = 0;
  for (let i = 0; i < B.length; i++) if (t >= B[i].c.out0) cur = i;
  for (let i = 0; i <= cur; i++) {
    const b = B[i];
    const u = b.u(t);
    const live = i === cur;
    stroke(b.pts, u, live ? 4.2 : 2.6, C.ink, k * (live ? 1 : 0.6));
    if (u >= 1) dot(b.tip[0], b.tip[1], live ? 4 : 3.5, C.ink2, k);
    tipName(b, k * ease((t - b.end) / 0.35) * (live ? 1 : 0.8));
  }
  dot(ROOT[0], ROOT[1], 5, C.ink, k * ease(B[0].u(t) * 3 - 2));
  const b = B[cur];
  const [x, y] = at(b.pts, b.u(t));
  dot(x, y, 10, C.red, k);
}

function lyric(t, k) {
  const line = D.lines.find((l) => t >= l.t0 - 0.05 && t < l.t1 + 0.05);
  if (!line) return;
  const fade = ease((t - line.t0 + 0.05) / 0.12) * ease((line.t1 + 0.05 - t) / 0.12) * k;
  const words = [];
  let cur = null;
  for (const s of line.syl) {
    if (!cur) { cur = { parts: [], italic: false, changed: false }; words.push(cur); }
    cur.parts.push(s);
    if (s.syl.includes('*')) cur.italic = true;
    if (s.changed) cur.changed = true;
    if (!s.cont) cur = null;
  }
  const size = 52, space = size * 0.28;
  const measure = (w) => { g.font = `${w.italic ? 'italic ' : ''}${size}px ${SERIF}`; return g.measureText(w.parts.map((p) => plain(p.syl)).join('')).width; };
  const halves = new Set(line.syl.map((s) => s.row)).size > 1;
  const rows = [[]];
  let rowW = 0;
  for (const w of words) {
    const ww = measure(w);
    const last = rows[rows.length - 1];
    const brk = halves ? last.length && last[0][0].parts[0].row !== w.parts[0].row : last.length && rowW + space + ww > 880;
    if (brk) { rows.push([]); rowW = 0; }
    rows[rows.length - 1].push([w, ww]);
    rowW += (rowW ? space : 0) + ww;
  }
  const y0 = rows.length === 1 ? 1540 : 1505;
  g.save();
  rows.forEach((row, ri) => {
    const total = row.reduce((a, [, ww], i) => a + ww + (i ? space : 0), 0);
    let x = W / 2 - total / 2;
    for (const [w] of row) {
      g.font = `${w.italic ? 'italic ' : ''}${size}px ${SERIF}`;
      g.fillStyle = w.changed ? C.red : C.ink;
      for (const p of w.parts) {
        const txt = plain(p.syl);
        g.globalAlpha = fade * (t >= p.t0 ? 1 : 0.3);
        g.fillText(txt, Math.round(x), Math.round(y0 + ri * 68));
        x += g.measureText(txt).width;
      }
      x += space;
    }
  });
  g.restore();
}

function endCard(t) {
  const last = D.chunks[D.chunks.length - 1];
  return ease((t - last.sung[last.sung.length - 1].t1 - 0.5) / 1.0);
}

export function draw(t) {
  g.globalAlpha = 1;
  g.fillStyle = C.paper;
  g.fillRect(0, 0, W, H);
  const e = endCard(t);
  tree(t, 1 - 0.8 * e);
  lyric(t, 1);
  if (e > 0) {
    g.save();
    g.globalAlpha = e * 0.7;
    g.fillStyle = C.paper;
    g.fillRect(0, 760, W, 260);
    g.globalAlpha = e;
    g.textAlign = 'center';
    g.font = `italic 88px ${SERIF}`;
    g.fillStyle = C.ink;
    g.fillText(D.copy.title, W / 2, 890);
    g.font = `32px ${SERIF}`;
    g.fillStyle = C.red;
    g.fillText(D.copy.site, W / 2, 965);
    g.restore();
  }
}

async function init() {
  const faces = [['/fonts/Georgia.ttf', 'normal'], ['/fonts/Georgiai.ttf', 'italic']];
  for (const [url, style] of faces) document.fonts.add(await new FontFace('Cut Serif', `url(${url})`, { style }).load());
  D = await (await fetch('/data/cut.json')).json();
  B = layout();
  window.cut = { draw, duration: D.duration };
  const q = new URLSearchParams(location.search);
  if (q.has('capture')) { document.body.classList.add('capture'); draw(Number(q.get('t') || 0)); return; }
  const slider = document.getElementById('t'), tt = document.getElementById('tt');
  slider.max = D.duration;
  const audio = new Audio('/data/cut.wav');
  const show = (t) => { draw(t); tt.textContent = t.toFixed(2); };
  slider.oninput = () => { audio.currentTime = Number(slider.value); show(Number(slider.value)); };
  document.getElementById('play').onclick = () => (audio.paused ? audio.play() : audio.pause());
  const loop = () => { if (!audio.paused) { slider.value = audio.currentTime; show(audio.currentTime); } requestAnimationFrame(loop); };
  loop();
  show(Number(q.get('t') || 0));
}
window.cutReady = init();
