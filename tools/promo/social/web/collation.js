// The collation, 1080 x 1920: draw(t) paints the frame at t seconds of synced/cut.wav. Pure in t.
//
// The half-line being heard, large, each syllable at the height of the note it is sung on; above it, the same
// notes as each of its ancestors sang them, the release at the top. A word or an ornament is red in the row
// where it entered the line and black in every row below that kept it. An ancestor's row is dark while that
// ancestor sings in the heard version's choir (its voice is one of the harmony), pale otherwise.

const W = 1080, H = 1920;
const C = { paper: '#f4ecdc', ink: '#2b231d', ink3: '#6b5c4b', rule: '#d6c8ae', red: '#a3361f' };
const SERIF = '"Cut Serif", Georgia, serif';
const LINE_Y = 1290;     // the heard line's baseline at the middle pitch
const LINE_SEMI = 13;    // its pixels per semitone
const ROW_GAP = 122, FIRST_GAP = 200;
const ROW_SIZE = 50, ROW_SEMI = 5;
const MID = 66;

const cv = document.getElementById('c');
const g = cv.getContext('2d');
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const ease = (x) => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
const plain = (s) => (s || '').replace(/\*/g, '');

let D;

function chunkAt(t) {
  let i = 0;
  for (let j = 0; j < D.chunks.length; j++) if (t >= D.chunks[j].t0) i = j;
  return i;
}

// the heard line's layout: syllables of a word run together, words a space apart, the whole centred and fitted
function layout(c) {
  const heard = c.rows[c.rows.length - 1].syl;
  let size = 124;
  const widths = () => {
    g.font = `${size}px ${SERIF}`;
    const ws = heard.map((s) => { g.font = `${plain(s.text) !== s.text.replace(/\*/g, '') ? '' : ''}${s.text.includes('*') ? 'italic ' : ''}${size}px ${SERIF}`; return g.measureText(plain(s.text)).width; });
    const space = size * 0.3;
    const total = ws.reduce((a, w, i) => a + w + (i < ws.length - 1 && !heard[i].cont ? space : 0), 0);
    return { ws, space, total };
  };
  let m = widths();
  while (m.total > 980 && size > 40) { size -= 2; m = widths(); }
  let x = W / 2 - m.total / 2;
  const cols = heard.map((s, i) => {
    const col = { x, w: m.ws[i], cx: x + m.ws[i] / 2 };
    x += m.ws[i] + (i < heard.length - 1 && !s.cont ? m.space : 0);
    return col;
  });
  return { size, cols };
}

function singing(row, t) {
  if (!row.voice) return 0;
  let a = 0;
  for (const [t0, t1] of row.voice) {
    if (t >= t0 - 0.03 && t < t1 + 0.18) a = Math.max(a, ease((t - t0 + 0.03) / 0.05) * ease((t1 + 0.18 - t) / 0.18));
  }
  return a;
}

function ornament(orn, cx, y, w, semi, color, alpha, width) {
  if (!orn) return;
  g.save();
  g.globalAlpha = alpha;
  g.strokeStyle = color;
  g.lineWidth = width;
  g.lineCap = 'round';
  g.lineJoin = 'round';
  g.beginPath();
  const x0 = cx - w / 2;
  orn.forEach(([f, st], i) => {
    const x = x0 + f * w, yy = y - st * semi;
    if (i === 0) g.moveTo(x, yy); else g.lineTo(x, yy);
  });
  const last = orn[orn.length - 1];
  g.lineTo(x0 + Math.min(1, last[0] + 0.3) * w, y - last[1] * semi);
  g.stroke();
  g.restore();
}

function collation(t, k) {
  const ci = chunkAt(t);
  const c = D.chunks[ci];
  const { size, cols } = layout(c);
  const n = c.rows.length;
  const heard = c.rows[n - 1];
  // the ancestors, the release at the top; they arrive top first, a moment apart, as the line is handed down
  for (let d = 0; d < n - 1; d++) {
    const row = c.rows[d];
    const up = n - 1 - d;     // rows above the heard line
    const base = LINE_Y - FIRST_GAP - (up - 1) * ROW_GAP;
    const arrive = ease((t - c.t0 - d * 0.06) / 0.16);
    if (arrive <= 0) continue;
    const s = singing(row, t);
    const yShift = (1 - arrive) * -26;
    g.save();
    g.textAlign = 'center';
    // whole words, each centred over the syllables it is sung on, at its first syllable's pitch
    let start = 0;
    row.syl.forEach((sy, i) => {
      if (sy.cont && i + 1 < row.syl.length) return;
      const parts = row.syl.slice(start, i + 1);
      const cx = (cols[start].x + cols[i].x + cols[i].w) / 2;
      const y = base - (parts[0].p - MID) * ROW_SEMI + yShift;
      const red = parts.some((q) => q.entered);
      g.font = `${parts.some((q) => q.text.includes('*')) ? 'italic ' : ''}${ROW_SIZE}px ${SERIF}`;
      g.fillStyle = red ? C.red : C.ink;
      g.globalAlpha = k * arrive * (red ? 0.95 : 0.2 + 0.78 * s);
      g.fillText(parts.map((q) => plain(q.text)).join(''), Math.round(cx), Math.round(y));
      parts.forEach((q, j) => {
        if (!q.orn) return;
        const col = cols[start + j];
        ornament(q.orn, col.cx, y - ROW_SIZE * 0.95, Math.max(col.w * 0.5, 40), 6, q.orn_entered ? C.red : C.ink, k * arrive * (q.orn_entered ? 1 : 0.35 + 0.6 * s), 3.5);
      });
      start = i + 1;
    });
    // the row's style, just after the row (or before it, where there is no room): red where the lineage took it up
    const prev = d > 0 ? c.rows[d - 1].style : null;
    const took = prev !== null && row.style !== prev;
    const name = D.copy.styles[row.style] || row.style;
    g.font = `${ROW_SIZE}px ${SERIF}`;
    const lastW = g.measureText(plain(row.syl.map((q) => q.text).join(''))).width;
    g.font = `italic 28px ${SERIF}`;
    const nw = g.measureText(name).width;
    const firstX = cols[0].x, lastX = cols[cols.length - 1].x + cols[cols.length - 1].w;
    const yName = Math.round(base - (row.syl[row.syl.length - 1].p - MID) * ROW_SEMI + yShift);
    let nx = null;
    if (lastX + 28 + nw < W - 24) { g.textAlign = 'left'; nx = lastX + 28; }
    else if (firstX - 28 - nw > 24) { g.textAlign = 'right'; nx = firstX - 28; }
    if (nx !== null && lastW >= 0) {
      g.fillStyle = took ? C.red : C.ink3;
      g.globalAlpha = k * arrive * (took ? 0.95 : 0.6);
      g.fillText(name, Math.round(nx), yName);
    }
    g.restore();
  }
  // the heard line
  g.save();
  g.textAlign = 'left';
  const sung = c.sung;
  heard.syl.forEach((sy, i) => {
    const col = cols[i];
    const y = LINE_Y - (sy.p - MID) * LINE_SEMI;
    const st = sung[i];
    const on = t >= st.t0;
    g.font = `${sy.text.includes('*') ? 'italic ' : ''}${size}px ${SERIF}`;
    g.fillStyle = sy.entered ? C.red : C.ink;
    g.globalAlpha = k * (on ? 1 : 0.28);
    g.fillText(plain(sy.text), Math.round(col.x), Math.round(y));
    if (sy.orn) {
      ornament(sy.orn, col.cx, y - size * 0.92, Math.max(col.w * 0.7, 60), 9, sy.orn_entered ? C.red : C.ink, k * (on ? 1 : 0.35), 5);
    }
  });
  g.restore();
}

function lastNote() {
  const c = D.chunks[D.chunks.length - 1];
  return c.sung[c.sung.length - 1].t1;
}

export function draw(t) {
  g.globalAlpha = 1;
  g.fillStyle = C.paper;
  g.fillRect(0, 0, W, H);
  const end = lastNote();
  const out = ease((t - end - 0.3) / 0.6), title = ease((t - end - 0.9) / 0.8);
  collation(t, 1 - out);
  if (title > 0) {
    g.save();
    g.globalAlpha = title;
    g.textAlign = 'center';
    g.font = `italic 92px ${SERIF}`;
    g.fillStyle = C.ink;
    g.fillText(D.copy.title, W / 2, 860);
    g.font = `36px ${SERIF}`;
    g.fillStyle = C.red;
    g.fillText(D.copy.site, W / 2, 945);
    g.restore();
  }
}

async function init() {
  const faces = [['/fonts/Georgia.ttf', 'normal'], ['/fonts/Georgiai.ttf', 'italic']];
  for (const [url, style] of faces) document.fonts.add(await new FontFace('Cut Serif', `url(${url})`, { style }).load());
  D = await (await fetch('/synced/collation.json')).json();
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
