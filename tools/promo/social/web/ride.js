// The ride, 1080 x 1920: draw(t) paints the frame at t seconds of synced/cut.wav. Pure in t.
//
// Every point is a version of the song as the program would choose it (synced/songspace.json: lineages from the
// release, each generation on another made-up machine, and the versions rendered for the cut). The points are
// laid out by one of the song's dimensions at a time and fly from one layout to the next as the sung lines
// change: descent from the release, the words they sing, their style, their singer's blend of voices, the
// machines they passed between, key by tempo by mode, that lattice turned through further dimensions, and
// last the title. The version being heard is the coal; its line of descent from the release is the bright
// thread, and an ancestor on it flares while its singer sings in the choir. A point's colour is its style.

const W = 1080, H = 1920;
const SERIF = '"Cut Serif", Georgia, serif';
const INK = '#efe6da', INK2 = '#c9bba4';
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const ease = (x) => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
const plain = (s) => (s || '').replace(/\*/g, '');
const mix = (a, b, e) => a + (b - a) * e;

function prng(seed) {
  let s = seed >>> 0;
  return () => { s = (s + 0x6D2B79F5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const gauss = (r) => Math.sqrt(-2 * Math.log(Math.max(r(), 1e-9))) * Math.cos(2 * Math.PI * r());

// a style's colour (linear, a little over 1 is fine: the frame is toned after)
const STYLE_COL = {
  ballad: [1.0, 0.84, 0.62], shanty: [0.36, 0.6, 1.0], stringband: [1.0, 0.56, 0.16], chamber: [1.0, 0.36, 0.5],
  songwriter: [0.5, 0.92, 0.5], lullaby: [0.72, 0.56, 1.0], country: [1.0, 0.9, 0.25], ambient: [0.3, 0.9, 0.85],
};
const OTHER_COL = [1, 1, 1];
const VOICES = ['house-bass', 'house-baritone', 'house-tenor', 'house-soft-tenor', 'house-rough', 'house-low-alto', 'house-alto',
  'house-mezzo', 'house-bright', 'house-breathy', 'volunteers'];
const VOICE_NAMES = ['bass', 'baritone', 'tenor', 'soft tenor', 'rough', 'low alto', 'alto', 'mezzo', 'bright', 'breathy', 'the volunteers'];
const KEY_NAMES = { 59: 'B', 60: 'C', 61: 'C♯', 62: 'D', 63: 'E♭', 64: 'E', 65: 'F' };
const MODE_Z = { ionian: 1, mixolydian: 0, aeolian: -1, dorian: -0.5 };

// the worlds, each from its time on; cam: distance, azimuth at its start, turning rate, elevation, how far the
// view follows the coal; lines: how bright the parent-to-child lines are
const COVER_T = 35.03;   // the last line's last half: the cloud turns into the cover's daisy
const WORLDS = [
  { t: 0, name: 'burst', cam: { d: [1.9, 6.1], az: 0.5, rate: 0.22, el: 0.2, follow: 0.15 }, lines: 0.22, gain: 0.42 },
  { t: 5.05, name: 'while', cam: { d: 6.4, az: 0, rate: 0, el: 0, follow: 0.05, sway: 0.16 }, lines: 0, gain: 0.26 },
  { t: 7.32, name: 'then', cam: { d: 6.4, az: 0, rate: 0, el: 0, follow: 0.05, sway: 0.16 }, lines: 0, gain: 0.26 },
  { t: 9.66, name: 'style', cam: { d: [7.2, 6.0], az: -0.3, rate: 0.13, el: 0.1, follow: 0.2 }, lines: 0.045, gain: 0.34 },
  { t: 14.29, name: 'singer', cam: { d: [7.0, 5.4], az: 0.25, rate: -0.12, el: 0.3, follow: 0.12 }, lines: 0.05, gain: 0.3 },
  { t: 19.18, name: 'machines', cam: { d: [5.6, 2.5], az: 0.0, rate: 0.34, el: 0.12, follow: 0.4 }, lines: 0.03, gain: 0.3 },
  { t: 23.80, name: 'lattice', cam: { d: [7.3, 6.3], az: -0.34, rate: 0.12, el: 0.1, follow: 0.1 }, lines: 0.03, gain: 0.42 },
  { t: 29.55, name: 'hyper', cam: { d: [6.3, 5.0], az: 0.0, rate: 0.34, el: 0.2, follow: 0.12 }, lines: 0.03, gain: 0.42 },
  { t: 32.75, name: 'burst', cam: { d: [4.6, 6.4], az: -0.3 * (COVER_T - 32.75), rate: 0.3, el: 0.2, follow: 0.05 }, lines: 0.2, gain: 0.42 },
  { t: COVER_T, name: 'cover', cam: { d: 6.4, az: 0, rate: 0, el: 0, follow: 0 }, lines: 0, gain: 0.36 },
];
const FOV = 38 * Math.PI / 180, SHIFT = 0.2;
const COVER_D = 6.4;                                        // the camera's distance when the cover fills the width
const SIDE = W * Math.tan(FOV / 2) * COVER_D / (H / 2);     // the photograph's side in the world, to do so
const MOVE = 0.7, STAGGER = 0.4;   // a point's flight to the next layout, and how far apart the points set off
const GROW0 = 0.05, GROW = 0.42;   // the first burst: a generation every GROW seconds

let D, N, rows, CHUNKS, LINES, COPY;
let L = {}, LABELS = {}, hyperC, gen, parent, hash, col, col2, byPath, COVER, DAISY, PHOTO, STEM, STEM_LEN, HEAD_R, ROT, FLOWER, isChain;
let gl, P, bufPos, bufB, vaoPts, vaoLines, nLines, vaoHi, bufHi, fbo = {};
const cv = document.getElementById('c');
const g2 = cv.getContext('2d');
const text = document.createElement('canvas').getContext('2d', { willReadFrequently: true });

// ---------------------------------------------------------------------------------------------- layouts

// points placed on the letters of words: groups [{text, cy, h, italic}] and each point's group
function dotText(groups, groupOf, seed) {
  const out = new Float32Array(N * 3);
  const r = prng(seed);
  const samples = groups.map((gp) => {
    const size = 220;
    text.canvas.width = 2400; text.canvas.height = 340;
    text.clearRect(0, 0, 2400, 340);
    text.font = `${gp.italic ? 'italic ' : ''}${size}px ${SERIF}`;
    text.textBaseline = 'alphabetic';
    text.fillStyle = '#fff';
    const w = Math.ceil(text.measureText(gp.text).width);
    text.fillText(gp.text, 20, 250);
    const img = text.getImageData(0, 0, Math.min(2400, w + 40), 340).data;
    const iw = Math.min(2400, w + 40), px = [];
    for (let y = 0; y < 340; y++) for (let x = 0; x < iw; x++) if (img[(y * iw + x) * 4 + 3] > 110) px.push(x, y);
    const scale = Math.min(gp.h / 170, (gp.maxW || 1.9) / w);
    return { px, scale, w, gp };
  });
  for (let i = 0; i < N; i++) {
    const s = samples[groupOf[i]];
    const k = Math.floor(r() * (s.px.length / 2)) * 2;
    out[i * 3] = (s.px[k] + r() - 20 - s.w / 2) * s.scale;
    out[i * 3 + 1] = s.gp.cy - (s.px[k + 1] + r() - 190) * s.scale;
    out[i * 3 + 2] = gauss(r) * 0.03;
  }
  return { pos: out, samples };
}

function fib(k, n) {
  const y = 1 - 2 * (k + 0.5) / n, rad = Math.sqrt(1 - y * y), a = k * 2.399963229728653;
  return [Math.cos(a) * rad, y, Math.sin(a) * rad];
}

function layouts() {
  const r = prng(7);
  // each version's first ancestor after the release: its lineage
  const chainOf = new Int32Array(N);
  const chains = [];
  for (let i = 1; i < N; i++) {
    if (parent[i] === 0) { chainOf[i] = chains.length; chains.push(i); } else chainOf[i] = chainOf[parent[i]];
  }
  // burst: a lineage leaves the release its own way; each generation a step further, a little off its parent's line
  {
    const order = chains.map((i, c) => c).sort((a, b) => (rows[chains[a]].style < rows[chains[b]].style ? -1 : rows[chains[a]].style > rows[chains[b]].style ? 1 : a - b));
    const dir = [];
    order.forEach((c, k) => { dir[c] = fib(k, chains.length); });
    const p = new Float32Array(N * 3);
    for (let i = 1; i < N; i++) {
      const d = dir[chainOf[i]], q = parent[i] * 3, step = 0.175 * (0.8 + 0.4 * r());
      p[i * 3] = p[q] + d[0] * step + gauss(r) * 0.022;
      p[i * 3 + 1] = p[q + 1] + d[1] * step + gauss(r) * 0.022;
      p[i * 3 + 2] = p[q + 2] + d[2] * step + gauss(r) * 0.022;
    }
    L.burst = p;
  }
  // the refrain's two words that vary: the points stand on the word their version sings
  {
    const words = ['while', 'if', 'when'];
    const t = dotText(words.map((w, k) => ({ text: w, cy: 0.62 - k * 0.6, h: 0.5 })), rows.map((x) => Math.max(0, words.indexOf(x.while || 'while'))), 11);
    L.while = t.pos;
    const thens = ['it goes', 'it grows', 'who knows'];
    const grp = rows.map((x) => Math.max(0, thens.indexOf(x.then || 'it goes')));
    const t2 = dotText(thens.map((w, k) => ({ text: w, cy: 0.62 - k * 0.6, h: 0.42 })), grp, 12);
    L.then = t2.pos;
    // a word few versions sing is set in type as well, so it can be read
    LABELS.then = [{ text: 'it goes', p: [0, 0.62 - 0.04, 0], size: 150, alpha: 0.2, center: true }];
    LABELS.while = [];
  }
  // styles: an island each, a version placed in it by its band's density, brightness and ornament
  {
    const count = {};
    rows.forEach((x) => { count[x.style] = (count[x.style] || 0) + 1; });
    const big = Object.keys(count).filter((s) => count[s] > 20).sort((a, b) => count[b] - count[a]);
    const small = Object.keys(count).filter((s) => count[s] <= 20).sort();
    const spots = [[-0.5, 0.98], [0.5, 0.8], [-0.52, 0.3], [0.55, 0.1], [-0.45, -0.35], [0.5, -0.42], [-0.15, -0.8], [0.42, -0.86], [0, -0.3]];
    const centre = {}, radius = {};
    big.forEach((s, k) => { centre[s] = [spots[k][0], spots[k][1], 0]; radius[s] = 0.16 + 0.42 * Math.sqrt(count[s] / N); });
    small.forEach((s, k) => { centre[s] = [-0.92 + 1.84 * (k + 0.5) / small.length, -1.14 - (k % 2) * 0.11, 0]; radius[s] = 0.02; });
    const p = new Float32Array(N * 3);
    const bi = (name) => D.band.indexOf(name);
    for (let i = 0; i < N; i++) {
      const x = rows[i], c = centre[x.style], rad = radius[x.style];
      const a = ((x.band[bi('density')] ?? 0.58) - 0.58) / 0.25, b = ((x.band[bi('brightness')] ?? 0.5) - 0.5) / 0.22, o = ((x.band[bi('ornament')] ?? 0.47) - 0.47) / 0.3;
      p[i * 3] = c[0] + clamp(a, -1.6, 1.6) * rad * 0.7 + gauss(r) * rad * 0.12;
      p[i * 3 + 1] = c[1] + clamp(b, -1.6, 1.6) * rad * 0.7 + gauss(r) * rad * 0.12;
      p[i * 3 + 2] = c[2] + clamp(o, -1.6, 1.6) * rad * 0.7 + gauss(r) * rad * 0.12;
    }
    L.style = p;
    LABELS.style = big.map((s) => ({ text: COPY.styles[s] || s, p: [centre[s][0], centre[s][1] - radius[s] - 0.07, 0], size: 38, italic: true, center: true }))
      .concat(small.map((s) => ({ text: COPY.styles[s] || s, p: [centre[s][0], centre[s][1] - 0.05, 0], size: 24, italic: true, center: true, alpha: 0.8 })));
  }
  // the singer: every version's singer is a blend of the house's voices and the volunteers'; a voice at each
  // corner, a version where its blend balances, raised by how deep its vibrato is
  {
    const anchors = VOICES.map((v, k) => { const a = Math.PI / 2 - (k / VOICES.length) * Math.PI * 2; return [Math.cos(a), Math.sin(a)]; });
    const raw = new Float32Array(N * 2);
    let mx = 0, my = 0, n = 0;
    const vi = D.singer.indexOf('vibrato_depth');
    for (let i = 0; i < N; i++) {
      let sx = 0, sy = 0, sw = 0;
      VOICES.forEach((v, k) => { const w = rows[i].timbre[v] || 0; sx += anchors[k][0] * w; sy += anchors[k][1] * w; sw += w; });
      if (sw > 0) { raw[i * 2] = sx / sw; raw[i * 2 + 1] = sy / sw; mx += raw[i * 2]; my += raw[i * 2 + 1]; n++; } else raw[i * 2] = NaN;
    }
    mx /= n; my /= n;
    const rad = [];
    for (let i = 0; i < N; i++) if (!Number.isNaN(raw[i * 2])) rad.push(Math.hypot(raw[i * 2] - mx, raw[i * 2 + 1] - my));
    rad.sort((a, b) => a - b);
    const gain = 0.8 / rad[Math.floor(rad.length * 0.985)];
    const p = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const none = Number.isNaN(raw[i * 2]);
      p[i * 3] = none ? 0 : (raw[i * 2] - mx) * gain;
      p[i * 3 + 1] = none ? 0 : (raw[i * 2 + 1] - my) * gain;
      p[i * 3 + 2] = clamp(((rows[i].singer[vi] ?? 21) - 21) / 22, -0.5, 1.0) * 0.6;
    }
    L.singer = p;
    LABELS.singer = VOICE_NAMES.map((name, k) => ({ text: name, p: [anchors[k][0] * 1.0, anchors[k][1] * 1.08, 0], size: 30, italic: true, center: true }));
  }
  // the machines: each on a sphere; a version stands at the machine that sang it, so a lineage is a path of
  // chords from the release at the centre
  {
    const names = new Map();
    const key = (x) => (x.machine !== null && x.machine !== undefined ? 'm' + x.machine : x.mname ? 'n' + x.mname : 'here');
    rows.forEach((x, i) => { if (i && !names.has(key(x))) names.set(key(x), names.size); });
    const p = new Float32Array(N * 3);
    for (let i = 1; i < N; i++) {
      const a = fib(names.get(key(rows[i])), names.size), s = 1.0 + 0.012 * gen[i];
      p[i * 3] = a[0] * s + gauss(r) * 0.012; p[i * 3 + 1] = a[1] * s + gauss(r) * 0.012; p[i * 3 + 2] = a[2] * s + gauss(r) * 0.012;
    }
    L.machines = p;
  }
  // key by mode: a column for each key, a row for each mode; within its cell a version is higher the faster it
  // is, and nearer the later its generation
  {
    const KX = (k) => (k - 61.8) * 0.42, MY = (m) => (MODE_Z[m] ?? 0) * 0.74;
    const p = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const x = rows[i];
      p[i * 3] = KX(x.tonic) + gauss(r) * 0.05;
      p[i * 3 + 1] = MY(x.mode) + (x.tempo - 92) / 46 * 0.27;
      p[i * 3 + 2] = (x.gen - 3) * 0.13 + gauss(r) * 0.03;
    }
    L.lattice = p;
    const keys = [...new Set(rows.map((x) => x.tonic))].sort((a, b) => a - b);
    LABELS.lattice = keys.map((k) => ({ text: KEY_NAMES[k] || String(k), p: [KX(k), -1.17, 0], size: 46, center: true }))
      .concat(['ionian', 'mixolydian', 'aeolian'].map((m) => ({ text: { ionian: 'major', mixolydian: 'mixolydian', aeolian: 'minor' }[m], p: [-0.76, MY(m) + 0.36, 0], size: 30, italic: true, center: true })));
    LABELS.lattice.forEach((l) => { if (l.italic) l.size = 34; });
  }
  // the lattice's three dimensions and three more it turns into: the singer's blend (two) and the generation
  hyperC = new Float32Array(N * 6);
  for (let i = 0; i < N; i++) {
    hyperC[i * 6] = L.lattice[i * 3]; hyperC[i * 6 + 1] = L.lattice[i * 3 + 1]; hyperC[i * 6 + 2] = L.lattice[i * 3 + 2];
    hyperC[i * 6 + 3] = L.singer[i * 3] * 1.1; hyperC[i * 6 + 4] = L.singer[i * 3 + 1] * 1.1; hyperC[i * 6 + 5] = (((rows[i].band[D.band.indexOf('density')] ?? 0.58) - 0.58) / 0.25) * 0.5;
  }
  L.hyper = new Float32Array(N * 3);
  // the cover's daisy. The burst and the line of the last version heard are the flower upside down: turned so
  // the line hangs straight down, the cloud is the head and the line the stem. Each point keeps its place round
  // the release (its angle, and how far out it is among its neighbours) and takes a place on a petal or the yellow
  // middle; the lowest hanging become the leaves; the line's versions lie along the stem, the release in the
  // middle of the head and the version heard at the stem's foot, in the crack.
  {
    const toW = (q) => [(q[0] - 0.5) * SIDE, (0.5 - q[1]) * SIDE, 0];
    DAISY = toW(COVER.daisy);
    STEM = COVER.stem.map(toW);
    HEAD_R = COVER.head * SIDE;
    const chain = CHUNKS[CHUNKS.length - 1].chain, coalI = chain[chain.length - 1];
    // the burst is set so that this line stands straight up (which way the burst faces is free): then the turn
    // is half a turn in the picture's plane, the camera square on
    const b = L.burst;
    const ul = Math.hypot(b[coalI * 3], b[coalI * 3 + 1], b[coalI * 3 + 2]);
    const u = [b[coalI * 3] / ul, b[coalI * 3 + 1] / ul, b[coalI * 3 + 2] / ul];
    let ax = [-u[2], 0, u[0]];        // u cross (0, 1, 0)
    const al = Math.hypot(ax[0], ax[1], ax[2]) || 1;
    ROT = { axis: [ax[0] / al, ax[1] / al, ax[2] / al] };
    const up = new Float32Array(N * 3);
    turn(b, up, Math.acos(clamp(u[1], -1, 1)), 0, N);
    b.set(up);
    ROT = { axis: [0, 0, 1], angle: Math.PI };
    const turned = new Float32Array(N * 3);
    turn(b, turned, ROT.angle, 0, N);
    isChain = new Uint8Array(N);
    chain.forEach((v) => { isChain[v] = 1; });
    const p = new Float32Array(N * 3);
    col2 = new Float32Array(N * 3);
    const set = (i, q) => { const w3 = toW(q); p[i * 3] = w3[0]; p[i * 3 + 1] = w3[1]; p[i * 3 + 2] = gauss(r) * 0.003; col2[i * 3] = q[2]; col2[i * 3 + 1] = q[3]; col2[i * 3 + 2] = q[4]; };
    const free = [];
    for (let i = 0; i < N; i++) if (!isChain[i]) free.push(i);
    // the leaves: the points hanging lowest, the lowest to the lowest of the leaves
    free.sort((i, j) => turned[i * 3 + 1] - turned[j * 3 + 1]);
    const nLeaf = Math.round(N * 0.07);
    const leaves = COVER.leaves.slice(0, nLeaf).sort((q1, q2) => q2[1] - q1[1]);
    for (let k = 0; k < nLeaf; k++) set(free[k], leaves[k]);
    // the head: angle kept, and rank outward within each narrow slice of angle
    const rest = free.slice(nLeaf);
    const nMid = Math.round(rest.length * 0.13);
    const places = COVER.middle.slice(0, nMid).concat(COVER.petals.slice(0, rest.length - nMid));
    const cu = COVER.daisy[0], cvv = COVER.daisy[1];
    const pa = rest.map((i) => ({ i, a: Math.atan2(turned[i * 3 + 1], turned[i * 3]), d: Math.hypot(turned[i * 3], turned[i * 3 + 1]) })).sort((x, y) => x.a - y.a);
    const ta = places.map((q) => ({ q, a: Math.atan2(cvv - q[1], q[0] - cu), d: Math.hypot(q[0] - cu, q[1] - cvv) })).sort((x, y) => x.a - y.a);
    const slice = Math.ceil(rest.length / 220);
    for (let k = 0; k < rest.length; k += slice) {
      const ps = pa.slice(k, k + slice).sort((x, y) => x.d - y.d), ts = ta.slice(k, k + slice).sort((x, y) => x.d - y.d);
      ps.forEach((pp, j) => set(pp.i, ts[j].q));
    }
    // the line's versions along the stem
    chain.forEach((v, j) => {
      const q = stemAt(j / (chain.length - 1));
      p[v * 3] = q[0]; p[v * 3 + 1] = q[1]; p[v * 3 + 2] = 0;
      col2[v * 3] = 0.6; col2[v * 3 + 1] = 0.65; col2[v * 3 + 2] = 0.43;
    });
    L.cover = p;
    const base = STEM[STEM.length - 1], top = DAISY[1] + HEAD_R;
    STEM_LEN = STEM.slice(1).reduce((a, q, i) => a + Math.hypot(q[0] - STEM[i][0], q[1] - STEM[i][1]), 0);
    FLOWER = { mid: [(DAISY[0] + base[0]) / 2, (top + base[1]) / 2, 0], h: top - base[1] };
  }
}

// a place on the stem, s from 0 (the middle of the head) to 1 (its foot)
function stemAt(s) {
  const x = clamp(s, 0, 1) * (STEM.length - 1), k = Math.min(Math.floor(x), STEM.length - 2), f = x - k;
  return [mix(STEM[k][0], STEM[k + 1][0], f), mix(STEM[k][1], STEM[k + 1][1], f), 0];
}

// points turned about the cover's axis through the release by an angle
function turn(src, dst, angle, from, to) {
  const [kx, ky, kz] = ROT.axis, c = Math.cos(angle), sn = Math.sin(angle);
  for (let i = from; i < to; i++) {
    const x = src[i * 3], y = src[i * 3 + 1], z = src[i * 3 + 2], dot = (kx * x + ky * y + kz * z) * (1 - c);
    dst[i * 3] = x * c + (ky * z - kz * y) * sn + kx * dot;
    dst[i * 3 + 1] = y * c + (kz * x - kx * z) * sn + ky * dot;
    dst[i * 3 + 2] = z * c + (kx * y - ky * x) * sn + kz * dot;
  }
}

// the first burst growing: a generation at a time, each from its parent
const burstGrow = new Float32Array(1);
function growth(t, g) { return g === 0 ? 1 : ease((t - GROW0 - (g - 1) * GROW) / (GROW * 1.3)); }

function layoutAt(name, t, out, wi) {
  if (name === 'hyper') {
    const tau = Math.max(0, t - WORLDS.find((w) => w.name === 'hyper').t);
    const k = tau * tau / (tau + 0.6);     // eases into the turn
    const a = 1.25 * k, b = 0.9 * k, c = 1.6 * k;
    const ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b), cc = Math.cos(c), sc = Math.sin(c);
    for (let i = 0; i < N; i++) {
      const o = i * 6;
      out[i * 3] = hyperC[o] * ca + hyperC[o + 3] * sa;
      out[i * 3 + 1] = hyperC[o + 1] * cb + hyperC[o + 4] * sb;
      out[i * 3 + 2] = hyperC[o + 2] * cc + hyperC[o + 5] * sc;
    }
    return out;
  }
  if (name === 'burst' && wi === 0 && t < GROW0 + 7 * GROW) {
    const p = L.burst;
    out[0] = out[1] = out[2] = 0;
    for (let i = 1; i < N; i++) {
      const e = growth(t, gen[i]), q = parent[i] * 3;
      out[i * 3] = out[q] + (p[i * 3] - p[q]) * e;
      out[i * 3 + 1] = out[q + 1] + (p[i * 3 + 1] - p[q + 1]) * e;
      out[i * 3 + 2] = out[q + 2] + (p[i * 3 + 2] - p[q + 2]) * e;
    }
    return out;
  }
  return L[name];
}

// ---------------------------------------------------------------------------------------------- time

function worldAt(t) {
  let k = 0;
  for (let j = 0; j < WORLDS.length; j++) if (t >= WORLDS[j].t) k = j;
  return k;
}
function chunkAt(t) {
  let i = 0;
  for (let j = 0; j < CHUNKS.length; j++) if (t >= CHUNKS[j].t0) i = j;
  return i;
}

const scratchA = { a: null, b: null };
// every point's place at t
// the cover's three beats, in seconds after it starts: the cloud tightens and the line straightens and reaches out
// of it (GATHER); the two turn over until the line hangs down (TURN: start, length); the cloud's points go to
// their places on the daisy's head and leaves (COMB: start, spread, length) and the line settles on the stem (STEM)
const GATHER = 0.75, TURN = [0.5, 0.95], COMB = [1.2, 0.3, 0.65], STEM_IN = [1.2, 0.6], TIGHT = 0.36;
function coverEase(t) { return ease((t - COVER_T - STEM_IN[0]) / STEM_IN[1]); }
function positions(t, pos) {
  const k = worldAt(t), w = WORLDS[k];
  if (w.name === 'cover') {
    const tt = t - w.t, eg = ease(tt / GATHER), er = ease((tt - TURN[0]) / TURN[1]), line = coverEase(t), to = L.cover, b = L.burst;
    const sc = mix(1, TIGHT, eg), src = scratchA.a;
    for (let i = 0; i < N * 3; i++) src[i] = b[i] * sc;
    // the line's versions: from where they are in the burst to evenly along a straight line as long as the stem
    const chain = CHUNKS[CHUNKS.length - 1].chain, far = chain[chain.length - 1];
    const fl = Math.hypot(b[far * 3], b[far * 3 + 1], b[far * 3 + 2]);
    chain.forEach((v, j) => {
      const along = STEM_LEN * j / (chain.length - 1) / fl;
      for (let a = 0; a < 3; a++) src[v * 3 + a] = mix(b[v * 3 + a], b[far * 3 + a] * along, eg);
    });
    turn(src, pos, ROT.angle * er, 0, N);
    for (let i = 0; i < N; i++) {
      const e = isChain[i] ? line : ease((tt - COMB[0] - hash[i] * COMB[1]) / COMB[2]);
      pos[i * 3] = mix(pos[i * 3] + DAISY[0] * eg, to[i * 3], e);
      pos[i * 3 + 1] = mix(pos[i * 3 + 1] + DAISY[1] * eg, to[i * 3 + 1], e);
      pos[i * 3 + 2] = mix(pos[i * 3 + 2], to[i * 3 + 2], e);
    }
    return;
  }
  const to = layoutAt(w.name, t, scratchA.b, k);
  if (k === 0 || t >= w.t + MOVE + STAGGER) { pos.set(to); return; }
  const from = layoutAt(WORLDS[k - 1].name, t, scratchA.a, k - 1);
  for (let i = 0; i < N; i++) {
    const e = ease((t - w.t - hash[i] * STAGGER) / MOVE);
    const ax = from[i * 3], ay = from[i * 3 + 1], az = from[i * 3 + 2];
    const dx = to[i * 3] - ax, dy = to[i * 3 + 1] - ay, dz = to[i * 3 + 2] - az;
    // it flies in an arc: off its straight line, round the upright axis
    const s = Math.sin(Math.PI * e) * 0.22;
    pos[i * 3] = ax + dx * e + dz * s;
    pos[i * 3 + 1] = ay + dy * e;
    pos[i * 3 + 2] = az + dz * e - dx * s;
  }
}

// the cover's own camera: close on the daisy while the last line is sung, then back until the photograph fills
// the frame's width
function coverCam(t) {
  const tt = t - COVER_T, eg = ease(tt / GATHER), ec = ease((tt - COMB[0]) / 0.95), ep = ease((t - END - 0.25) / 1.6);
  const close = (H / 2) / (Math.tan(FOV / 2) * (1060 / FLOWER.h));     // the whole flower 1060 pixels tall
  // in on the cloud as it tightens and turns; on the flower as it forms; back for the photograph
  const on = [mix(DAISY[0] * eg, FLOWER.mid[0], ec), mix(DAISY[1] * eg, FLOWER.mid[1], ec)];
  return { d: mix(mix(mix(6.2, 3.3, eg), close, ec), COVER_D, ep), az: 0, el: 0, tgt: [mix(on[0], 0, ep), mix(on[1], 0, ep), 0] };
}

function camera(t, coal) {
  const k = worldAt(t), w = WORLDS[k];
  const one = (j) => {
    if (WORLDS[j].name === 'cover') return coverCam(t);
    const c = WORLDS[j].cam, tt = t - WORLDS[j].t, dur = (WORLDS[j + 1] ? WORLDS[j + 1].t : WORLDS[j].t + 6) - WORLDS[j].t;
    const d = Array.isArray(c.d) ? mix(c.d[0], c.d[1], j === 0 ? ease(tt / 3.2) : Math.min(1.25, tt / dur)) : c.d;
    return { d, az: c.az + c.rate * tt + (c.sway ? Math.sin(tt * 1.3) * c.sway : 0), el: c.el, tgt: [coal[0] * c.follow, coal[1] * c.follow, coal[2] * c.follow] };
  };
  const b = one(k);
  if (k === 0) return b;
  const a = one(k - 1), e = ease((t - w.t) / 1.0);
  return { d: mix(a.d, b.d, e), az: mix(a.az, b.az, e), el: mix(a.el, b.el, e), tgt: [0, 1, 2].map((i) => mix(a.tgt[i], b.tgt[i], e)) };
}

function eyeOf(cam) {
  return [cam.tgt[0] + cam.d * Math.sin(cam.az) * Math.cos(cam.el), cam.tgt[1] + cam.d * Math.sin(cam.el), cam.tgt[2] + cam.d * Math.cos(cam.az) * Math.cos(cam.el)];
}

// ---------------------------------------------------------------------------------------------- GL

const VS_POINT = `#version 300 es
in vec3 aPos; in vec3 aCol; in float aSize; in float aB; in vec3 aCol2;
uniform mat4 uVP; uniform float uRef; uniform float uShift; uniform float uGain; uniform float uColMix;
out vec3 vCol;
void main() {
  vec4 p = uVP * vec4(aPos, 1.0);
  p.y += uShift * p.w;
  gl_Position = p;
  float s = aSize * uRef / max(p.w, 0.05);
  float k = 1.0;
  if (s < 1.8) { k = (s * s) / 3.24; s = 1.8; }
  if (s > 34.0 && aSize < 12.0) { k *= 34.0 / s; s = 34.0; }
  k *= smoothstep(0.08, 0.5, p.w);
  gl_PointSize = s;
  vCol = mix(aCol, aCol2, uColMix) * aB * k * uGain;
}`;
const FS_POINT = `#version 300 es
precision highp float;
in vec3 vCol; out vec4 o;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r2 = dot(d, d) * 4.0;
  float a = exp(-r2 * 3.2) * smoothstep(1.0, 0.6, r2);
  o = vec4(vCol * a, 1.0);
}`;
const VS_LINE = `#version 300 es
in vec3 aPos; in vec3 aCol; in float aB;
uniform mat4 uVP; uniform float uShift; uniform float uGain;
out vec3 vCol;
void main() {
  vec4 p = uVP * vec4(aPos, 1.0);
  p.y += uShift * p.w;
  gl_Position = p;
  vCol = aCol * min(aB, 1.0) * uGain;
}`;
const FS_LINE = `#version 300 es
precision highp float;
in vec3 vCol; out vec4 o;
void main() { o = vec4(vCol, 1.0); }`;
const VS_QUAD = `#version 300 es
out vec2 uv;
void main() { vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2)); uv = p; gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }`;
const FS_BLUR = `#version 300 es
precision highp float;
in vec2 uv; out vec4 o; uniform sampler2D uTex; uniform vec2 uDir;
void main() {
  vec3 c = texture(uTex, uv).rgb * 0.227027;
  c += (texture(uTex, uv + uDir * 1.3846).rgb + texture(uTex, uv - uDir * 1.3846).rgb) * 0.316216;
  c += (texture(uTex, uv + uDir * 3.2308).rgb + texture(uTex, uv - uDir * 3.2308).rgb) * 0.070270;
  o = vec4(c, 1.0);
}`;
const FS_OUT = `#version 300 es
precision highp float;
in vec2 uv; out vec4 o; uniform sampler2D uA, uB1, uB2, uB3;
void main() {
  vec3 c = texture(uA, uv).rgb + texture(uB1, uv).rgb * 0.55 + texture(uB2, uv).rgb * 0.7 + texture(uB3, uv).rgb * 0.9;
  float m = max(max(c.r, c.g), c.b);
  c *= (1.0 - exp(-m * 1.2)) / max(m, 1e-4);
  c = mix(c, vec3(1.0), smoothstep(3.0, 14.0, m) * 0.55);
  vec2 q = uv - vec2(0.5, 0.56);
  vec3 bg = vec3(0.070, 0.052, 0.040) * max(0.3, 1.0 - 1.1 * dot(q, q));
  o = vec4(bg + c * (1.0 - bg), 1.0);
}`;

function program(vs, fs, attribs) {
  const mk = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
  const p = gl.createProgram();
  gl.attachShader(p, mk(gl.VERTEX_SHADER, vs)); gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fs));
  (attribs || []).forEach((a, i) => gl.bindAttribLocation(p, i, a));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const u = {};
  const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < n; i++) { const info = gl.getActiveUniform(p, i); u[info.name] = gl.getUniformLocation(p, info.name); }
  return { p, u };
}

function target(w, h) {
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  const f = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, f);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
  if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw new Error('no float framebuffer');
  return { f, tex, w, h };
}

const HI_MAX = 9000;
function initGL() {
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  gl = c.getContext('webgl2', { antialias: false, alpha: false, preserveDrawingBuffer: true });
  if (!gl) throw new Error('no WebGL2');
  if (!gl.getExtension('EXT_color_buffer_float')) throw new Error('no float colour buffers');
  P = { pt: program(VS_POINT, FS_POINT, ['aPos', 'aCol', 'aSize', 'aB', 'aCol2']), ln: program(VS_LINE, FS_LINE, ['aPos', 'aCol', 'aSize', 'aB']),
    blur: program(VS_QUAD, FS_BLUR), out: program(VS_QUAD, FS_OUT) };
  bufPos = gl.createBuffer(); bufB = gl.createBuffer();
  const bufCol = gl.createBuffer(), bufSize = gl.createBuffer();
  const sizes = new Float32Array(N);
  for (let i = 0; i < N; i++) sizes[i] = i === 0 ? 0 : 4.6 + 2.2 * hash[i];
  gl.bindBuffer(gl.ARRAY_BUFFER, bufCol); gl.bufferData(gl.ARRAY_BUFFER, col, gl.STATIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, bufSize); gl.bufferData(gl.ARRAY_BUFFER, sizes, gl.STATIC_DRAW);
  const bind = () => {
    gl.bindBuffer(gl.ARRAY_BUFFER, bufPos); gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, bufCol); gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, bufSize); gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, 1, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, bufB); gl.enableVertexAttribArray(3); gl.vertexAttribPointer(3, 1, gl.FLOAT, false, 0, 0);
  };
  vaoPts = gl.createVertexArray(); gl.bindVertexArray(vaoPts); bind();
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer()); gl.bufferData(gl.ARRAY_BUFFER, col2, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(4); gl.vertexAttribPointer(4, 3, gl.FLOAT, false, 0, 0);
  vaoLines = gl.createVertexArray(); gl.bindVertexArray(vaoLines); bind();
  const idx = new Uint32Array((N - 1) * 2);
  for (let i = 1; i < N; i++) { idx[(i - 1) * 2] = parent[i]; idx[(i - 1) * 2 + 1] = i; }
  nLines = idx.length;
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer()); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.STATIC_DRAW);
  // the coal, the thread and the ancestors: a few points of their own, written each frame (x y z r g b size b)
  vaoHi = gl.createVertexArray(); gl.bindVertexArray(vaoHi);
  bufHi = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, bufHi); gl.bufferData(gl.ARRAY_BUFFER, HI_MAX * 32, gl.DYNAMIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 32, 0);
  gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 32, 12);
  gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, 1, gl.FLOAT, false, 32, 24);
  gl.enableVertexAttribArray(3); gl.vertexAttribPointer(3, 1, gl.FLOAT, false, 32, 28);
  gl.bindVertexArray(null);
  fbo.acc = target(W, H);
  fbo.t1 = target(W / 2, H / 2); fbo.b1 = target(W / 2, H / 2);
  fbo.t2 = target(W / 4, H / 4); fbo.b2 = target(W / 4, H / 4);
  fbo.t3 = target(W / 8, H / 8); fbo.b3 = target(W / 8, H / 8);
}

function mat4mul(a, b) {
  const o = new Float32Array(16);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
  return o;
}

function viewProj(eye, tgt) {
  const f = 1 / Math.tan(FOV / 2), near = 0.1, far = 60;
  const proj = new Float32Array([f / (W / H), 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) / (near - far), -1, 0, 0, 2 * far * near / (near - far), 0]);
  let zx = eye[0] - tgt[0], zy = eye[1] - tgt[1], zz = eye[2] - tgt[2];
  const zl = Math.hypot(zx, zy, zz); zx /= zl; zy /= zl; zz /= zl;
  let xx = zz, xy = 0, xz = -zx;       // up (0,1,0) cross z
  const xl = Math.hypot(xx, xy, xz); xx /= xl; xz /= xl;
  const yx = zy * xz - zz * xy, yy = zz * xx - zx * xz, yz = zx * xy - zy * xx;
  const view = new Float32Array([xx, yx, zx, 0, xy, yy, zy, 0, xz, yz, zz, 0,
    -(xx * eye[0] + xy * eye[1] + xz * eye[2]), -(yx * eye[0] + yy * eye[1] + yz * eye[2]), -(zx * eye[0] + zy * eye[1] + zz * eye[2]), 1]);
  return mat4mul(proj, view);
}
function project(vp, p) {
  const x = vp[0] * p[0] + vp[4] * p[1] + vp[8] * p[2] + vp[12], y = vp[1] * p[0] + vp[5] * p[1] + vp[9] * p[2] + vp[13];
  const w = vp[3] * p[0] + vp[7] * p[1] + vp[11] * p[2] + vp[15];
  return [(x / w * 0.5 + 0.5) * W, (1 - ((y / w + SHIFT) * 0.5 + 0.5)) * H, w];
}

// ---------------------------------------------------------------------------------------------- a frame

const SUB = 4, SHUTTER = 0.6 / 60;
let pos, bri, hi;

function scene(t, gain) {
  positions(t, pos);
  const k = worldAt(t), w = WORLDS[k];
  const ci = chunkAt(t), c = CHUNKS[ci];
  // where the coal is: it crosses from the last version to this one as the cut lands
  const cur = c.chain[c.chain.length - 1], prev = ci ? CHUNKS[ci - 1].chain[CHUNKS[ci - 1].chain.length - 1] : cur;
  const ce = ease((t - c.t0) / 0.3);
  const coal = [mix(pos[prev * 3], pos[cur * 3], ce), mix(pos[prev * 3 + 1], pos[cur * 3 + 1], ce), mix(pos[prev * 3 + 2], pos[cur * 3 + 2], ce)];
  const now = [pos[cur * 3], pos[cur * 3 + 1], pos[cur * 3 + 2]];
  // each point's light: grown yet (the first burst), and the ring that leaves the new version at a cut
  const first = k === 0 && t < GROW0 + 7 * GROW;
  const since = t - c.t0, ring = since * 2.6, ringAmp = ci ? 2.2 * Math.exp(-since / 0.45) : 0;
  const we = k ? ease((t - w.t) / 0.9) : 1;
  const wg = k ? mix(WORLDS[k - 1].gain, w.gain, we) : w.gain;
  for (let i = 0; i < N; i++) {
    let b = wg;
    if (first) b *= growth(t, gen[i]);
    if (ringAmp > 0.02) {
      const d = Math.hypot(pos[i * 3] - now[0], pos[i * 3 + 1] - now[1], pos[i * 3 + 2] - now[2]) - ring;
      b *= 1 + ringAmp * Math.exp(-d * d / 0.012);
    }
    bri[i] = b;
  }
  const cam = camera(t, coal);
  const vp = viewProj(eyeOf(cam), cam.tgt);

  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo.acc.f);
  gl.viewport(0, 0, W, H);
  gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
  gl.bindBuffer(gl.ARRAY_BUFFER, bufPos); gl.bufferData(gl.ARRAY_BUFFER, pos, gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, bufB); gl.bufferData(gl.ARRAY_BUFFER, bri, gl.DYNAMIC_DRAW);
  // the parent-to-child lines
  const le = k ? ease((t - w.t) / 1.0) : 1;
  // the lines stay through the cover's turn (they are the petals to come) and go as the points take their places
  const la = w.name === 'cover' ? WORLDS[k - 1].lines * (1 - ease((t - w.t - COMB[0] + 0.1) / 0.4)) : k ? mix(WORLDS[k - 1].lines, w.lines, le) : w.lines;
  if (la > 0.002) {
    gl.useProgram(P.ln.p);
    gl.uniformMatrix4fv(P.ln.u.uVP, false, vp); gl.uniform1f(P.ln.u.uShift, SHIFT); gl.uniform1f(P.ln.u.uGain, gain * la * 0.5);
    gl.bindVertexArray(vaoLines);
    gl.drawElements(gl.LINES, nLines, gl.UNSIGNED_INT, 0);
  }
  gl.useProgram(P.pt.p);
  gl.uniformMatrix4fv(P.pt.u.uVP, false, vp); gl.uniform1f(P.pt.u.uShift, SHIFT); gl.uniform1f(P.pt.u.uRef, cam.d); gl.uniform1f(P.pt.u.uGain, gain);
  const toCover = w.name === 'cover' ? ease((t - w.t - COMB[0] - 0.05) / 0.8) : 0;
  gl.uniform1f(P.pt.u.uColMix, toCover);
  gl.bindVertexArray(vaoPts);
  gl.drawArrays(gl.POINTS, 0, N);

  // the thread from the release to the version heard, the ancestors on it, the coal
  let n = 0;
  const put = (x, y, z, r, g, b, size, br) => { if (n >= HI_MAX) return; const o = n * 8; hi[o] = x; hi[o + 1] = y; hi[o + 2] = z; hi[o + 3] = r; hi[o + 4] = g; hi[o + 5] = b; hi[o + 6] = size; hi[o + 7] = br; n++; };
  const cover = w.name === 'cover', stemE = cover ? coverEase(t) : 0, gatherE = cover ? ease((t - w.t) / GATHER) : 0;
  if (stemE > 0) { const q = stemAt(1); coal[0] = mix(coal[0], q[0], stemE); coal[1] = mix(coal[1], q[1], stemE); coal[2] = mix(coal[2], 0, stemE); }
  const out = cover ? 1 : 1 - ease((t - END - 0.2) / 0.8);
  const chain = c.chain;
  const drawn = ease((t - c.t0) / 0.3) * (chain.length - 1);
  for (let s = 0; s < chain.length - 1; s++) {
    if (drawn <= s) break;
    const a = chain[s] * 3, b = chain[s + 1] * 3, part = Math.min(1, drawn - s);
    const len = Math.hypot(pos[b] - pos[a], pos[b + 1] - pos[a + 1], pos[b + 2] - pos[a + 2]);
    const m = Math.max(4, Math.min(700, Math.ceil(len * 420)));
    for (let j = 0; j <= m * part; j++) {
      const f = j / m;
      let x = mix(pos[a], pos[b], f), y = mix(pos[a + 1], pos[b + 1], f), z = mix(pos[a + 2], pos[b + 2], f);
      if (stemE > 0) { const q = stemAt((s + f) / (chain.length - 1)); x = mix(x, q[0], stemE); y = mix(y, q[1], stemE); z = mix(z, 0, stemE); }
      // the line is amber; as the stem it takes the stem's green
      put(x, y, z, mix(1.0, 0.6, stemE), mix(0.66, 0.68, stemE), mix(0.3, 0.4, stemE), mix(5.5, 9, Math.max(stemE, gatherE)), mix(0.5, 0.7, Math.max(stemE, gatherE)) * out);
    }
  }
  chain.forEach((v, s) => {
    if (s === chain.length - 1) return;
    // an ancestor: brighter while its singer sings in the choir
    let sing = 0;
    for (const [t0, t1] of c.rows[s].voice || []) if (t >= t0 - 0.03 && t < t1 + 0.2) sing = Math.max(sing, ease((t - t0 + 0.03) / 0.05) * ease((t1 + 0.2 - t) / 0.2));
    put(pos[v * 3], pos[v * 3 + 1], pos[v * 3 + 2], 1.0, 0.8, 0.5, s === 0 ? 20 : 15, (s === 0 ? 1.1 : 0.7) * (1 + 3.0 * sing) * out * (1 - stemE));
  });
  // the release, always
  put(pos[0], pos[1], pos[2], 1, 0.95, 0.85, 22, 1.2 * (1 - stemE));
  // the coal: it swells on each sung note
  let beat = 0;
  for (const s of c.sung) if (t >= s.t0) beat = Math.max(beat, Math.exp(-(t - s.t0) / 0.16));
  const ember = cover ? 1 - 0.45 * stemE : out;
  put(coal[0], coal[1], coal[2], 1.0, 0.3, 0.12, 46 + 16 * beat, (2.2 + 2.4 * beat) * ember);
  put(coal[0], coal[1], coal[2], 1.0, 0.9, 0.75, 16, 2.5 * ember);
  gl.bindVertexArray(vaoHi);
  gl.uniform1f(P.pt.u.uColMix, 0);
  gl.bindBuffer(gl.ARRAY_BUFFER, bufHi); gl.bufferSubData(gl.ARRAY_BUFFER, 0, hi.subarray(0, n * 8));
  gl.drawArrays(gl.POINTS, 0, n);
  gl.bindVertexArray(null);
  return { vp, coal: now, k, cam };
}

function post() {
  gl.disable(gl.BLEND);
  const blur = (src, dst, dx, dy) => {
    gl.bindFramebuffer(gl.FRAMEBUFFER, dst.f); gl.viewport(0, 0, dst.w, dst.h);
    gl.useProgram(P.blur.p);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, src.tex); gl.uniform1i(P.blur.u.uTex, 0);
    gl.uniform2f(P.blur.u.uDir, dx, dy);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
  blur(fbo.acc, fbo.t1, 1 / fbo.t1.w, 0); blur(fbo.t1, fbo.b1, 0, 1 / fbo.b1.h);
  blur(fbo.b1, fbo.t2, 1 / fbo.t2.w, 0); blur(fbo.t2, fbo.b2, 0, 1 / fbo.b2.h);
  blur(fbo.b2, fbo.t3, 1 / fbo.t3.w, 0); blur(fbo.t3, fbo.b3, 0, 1 / fbo.b3.h);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, W, H);
  gl.useProgram(P.out.p);
  [fbo.acc, fbo.b1, fbo.b2, fbo.b3].forEach((f, i) => { gl.activeTexture(gl.TEXTURE0 + i); gl.bindTexture(gl.TEXTURE_2D, f.tex); });
  gl.uniform1i(P.out.u.uA, 0); gl.uniform1i(P.out.u.uB1, 1); gl.uniform1i(P.out.u.uB2, 2); gl.uniform1i(P.out.u.uB3, 3);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
}

let END = 1e9;

function labels(t, s) {
  const k = s.k, w = WORLDS[k];
  const show = (j, a) => {
    for (const lb of LABELS[WORLDS[j].name] || []) {
      const [x, y, ww] = project(s.vp, lb.p);
      if (ww <= 0) continue;
      const size = lb.size * s.cam.d / ww * (6 / s.cam.d);
      g2.globalAlpha = a * (lb.alpha ?? 0.92);
      g2.font = `${lb.italic ? 'italic ' : ''}${size.toFixed(1)}px ${SERIF}`;
      g2.fillStyle = INK;
      g2.textAlign = 'center';
      g2.textBaseline = 'middle';
      g2.fillText(lb.text, x, y);
    }
  };
  const next = WORLDS[k + 1];
  const a = ease((t - w.t - 0.65) / 0.45) * (next ? 1 - ease((t - next.t + 0.15) / 0.2) : 1);
  g2.save();
  if (a > 0) show(k, a);
  g2.restore();
}

function lyric(t) {
  const line = LINES.find((l) => t >= l.t0 - 0.05 && t < l.t1 + 0.05);
  if (!line) return;
  const fade = ease((t - line.t0 + 0.05) / 0.1) * ease((line.t1 + 0.05 - t) / 0.1) * (1 - ease((t - END - 0.3) / 0.6));
  const words = [];
  let cur = null;
  for (const s of line.syl) {
    if (!cur) { cur = { parts: [], italic: false, chunk: s.chunk }; words.push(cur); }
    cur.parts.push(s);
    if (s.syl.includes('*')) cur.italic = true;
    if (!s.cont) cur = null;
  }
  const size = 50, space = size * 0.28;
  const measure = (w) => { g2.font = `${w.italic ? 'italic ' : ''}${size}px ${SERIF}`; return g2.measureText(w.parts.map((p) => plain(p.syl)).join('')).width; };
  const widths = words.map(measure);
  const total = widths.reduce((a, w) => a + w, 0) + space * (words.length - 1);
  const rows2 = [words.map((w, i) => [w, widths[i]])];
  if (total > 900) {
    const cands = [];
    let acc = 0;
    for (let i = 0; i < words.length - 1; i++) { acc += widths[i] + space; cands.push({ i, d: Math.abs(acc - total / 2), hand: words[i + 1].chunk !== words[i].chunk }); }
    const pool = cands.filter((c) => c.hand);
    const best = (pool.length ? pool : cands).reduce((a, c) => (c.d < a.d ? c : a)).i;
    rows2.splice(0, 1, rows2[0].slice(0, best + 1), rows2[0].slice(best + 1));
  }
  const y0 = rows2.length === 1 ? 1420 : 1388;
  g2.save();
  g2.textAlign = 'left'; g2.textBaseline = 'alphabetic';
  g2.shadowColor = 'rgba(10,7,5,0.9)'; g2.shadowBlur = 14;
  rows2.forEach((row, ri) => {
    const rw = row.reduce((a, [, ww], i) => a + ww + (i ? space : 0), 0);
    let x = W / 2 - rw / 2;
    for (const [w] of row) {
      g2.font = `${w.italic ? 'italic ' : ''}${size}px ${SERIF}`;
      g2.fillStyle = INK;
      for (const p of w.parts) {
        const txt = plain(p.syl);
        g2.globalAlpha = fade * (t >= p.t0 ? 1 : 0.38);
        g2.fillText(txt, Math.round(x), Math.round(y0 + ri * 64));
        x += g2.measureText(txt).width;
      }
      x += space;
    }
  });
  g2.restore();
}

export function draw(t) {
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo.acc.f);
  gl.viewport(0, 0, W, H);
  gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);
  let s;
  for (let j = 0; j < SUB; j++) s = scene(Math.max(0, t + ((j + 0.5) / SUB - 0.5) * SHUTTER), 1 / SUB);
  post();
  s = Object.assign(s, { vp: s.vp });
  g2.globalAlpha = 1;
  g2.drawImage(gl.canvas, 0, 0);
  // labels and words are set at the frame's own time
  labels(t, s);
  lyric(t);
  // the album cover: the photograph comes up exactly where the points have drawn its packet
  const ph = ease((t - END - 0.7) / 1.3);
  if (ph > 0) {
    const cam = coverCam(t), vp = viewProj(eyeOf(cam), cam.tgt);
    const a = project(vp, [-SIDE / 2, SIDE / 2, 0]), b = project(vp, [SIDE / 2, -SIDE / 2, 0]);
    g2.save();
    g2.globalAlpha = ph;
    g2.imageSmoothingQuality = 'high';
    g2.drawImage(PHOTO, a[0], a[1], b[0] - a[0], b[1] - a[1]);
    g2.restore();
  }
  const e = ease((t - END - 1.9) / 0.8);
  if (e > 0) {
    g2.save();
    g2.globalAlpha = e;
    g2.textAlign = 'center';
    g2.font = `40px ${SERIF}`;
    g2.fillStyle = '#f2b25c';
    g2.fillText(COPY.site, W / 2, 1396);
    g2.restore();
  }
}

async function init() {
  const faces = [['/fonts/Georgia.ttf', 'normal'], ['/fonts/Georgiai.ttf', 'italic']];
  for (const [url, style] of faces) document.fonts.add(await new FontFace('Cut Serif', `url(${url})`, { style }).load());
  const [space, coll, pic, cover] = await Promise.all(['songspace', 'collation', 'picture', 'cover'].map(async (n) => (await fetch(`/synced/${n}.json`)).json()));
  COVER = cover;
  PHOTO = new Image(); PHOTO.src = '/synced/cover-1080.jpg'; await PHOTO.decode();
  D = space; rows = D.rows; N = rows.length; COPY = pic.copy; LINES = pic.lines;
  gen = new Uint8Array(N); parent = new Int32Array(N); hash = new Float32Array(N); col = new Float32Array(N * 3);
  const r = prng(3);
  byPath = new Map();
  rows.forEach((x, i) => {
    gen[i] = x.gen; parent[i] = Math.max(0, x.parent); hash[i] = r();
    const c = STYLE_COL[x.style] || OTHER_COL;
    col[i * 3] = c[0]; col[i * 3 + 1] = c[1]; col[i * 3 + 2] = c[2];
    if (x.path) byPath.set(x.path, i);
  });
  CHUNKS = coll.chunks.map((c) => ({ t0: c.t0, t1: c.t1, sung: c.sung, rows: c.rows, chain: c.rows.map((q) => byPath.get(q.path)) }));
  const last = CHUNKS[CHUNKS.length - 1];
  END = last.sung[last.sung.length - 1].t1;
  layouts();
  scratchA.a = new Float32Array(N * 3); scratchA.b = new Float32Array(N * 3);
  pos = new Float32Array(N * 3); bri = new Float32Array(N); hi = new Float32Array(HI_MAX * 8);
  initGL();
  window.cut = { draw, duration: pic.duration };
  const q = new URLSearchParams(location.search);
  if (q.has('capture')) { document.body.classList.add('capture'); draw(Number(q.get('t') || 0)); return; }
  const slider = document.getElementById('t'), tt = document.getElementById('tt');
  slider.max = pic.duration;
  const audio = new Audio('/synced/cut.wav');
  const show = (t) => { draw(t); tt.textContent = t.toFixed(2); };
  slider.oninput = () => { audio.currentTime = Number(slider.value); show(Number(slider.value)); };
  document.getElementById('play').onclick = () => (audio.paused ? audio.play() : audio.pause());
  const loop = () => { if (!audio.paused) { slider.value = audio.currentTime; show(audio.currentTime); } requestAnimationFrame(loop); };
  loop();
  show(Number(q.get('t') || 0));
}
window.cutReady = init();
