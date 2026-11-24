// Reads the frame index stamped by a --check render (16 cells in the top rows, then a white and a black guard)
// from every frame of a video, and says whether each frame appears once, in order.
//
//   node tools/promo/video/capture/check.mjs FILE --from F [--frames N]
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

function probe(file) {
  return new Promise((ok, fail) => {
    const p = spawn('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', file]);
    let s = '';
    p.stdout.on('data', (d) => { s += d; });
    p.on('close', (c) => (c === 0 ? ok(s.trim().split(',').map(Number)) : fail(new Error(`ffprobe ${file}`))));
  });
}

export async function checkFile(file, { from = 0, frames = null } = {}) {
  const [w] = await probe(file);
  const rows = 4;
  const ff = spawn('ffmpeg', ['-v', 'error', '-i', file, '-map', '0:v:0', '-vf', `crop=iw:${rows}:0:2,format=gray`, '-f', 'rawvideo', '-'],
    { stdio: ['ignore', 'pipe', 'pipe'] });
  const size = w * rows, cell = Math.floor(w / 18);
  const got = [];
  let buf = Buffer.alloc(0);
  const read = (f) => {
    const at = (k) => {
      let s = 0, n = 0;
      for (let y = 1; y < rows - 1; y++) for (let x = Math.floor(cell * (k + 0.3)); x < Math.floor(cell * (k + 0.7)); x++) { s += f[y * w + x]; n++; }
      return s / n;
    };
    const white = at(16), black = at(17), mid = (white + black) / 2;
    if (white - black < 100) return -1;
    let v = 0;
    for (let k = 0; k < 16; k++) v = v * 2 + (at(k) > mid ? 1 : 0);
    return v;
  };
  ff.stdout.on('data', (d) => {
    buf = Buffer.concat([buf, d]);
    while (buf.length >= size) {
      got.push(read(buf.subarray(0, size)));
      buf = buf.subarray(size);
    }
  });
  await new Promise((ok, fail) => ff.on('close', (c) => (c === 0 ? ok() : fail(new Error(`ffmpeg decode ${file}`)))));
  const problems = [];
  got.forEach((v, i) => { if (v !== from + i) problems.push(`frame ${i} reads ${v}, expected ${from + i}`); });
  if (frames !== null && got.length !== frames) problems.unshift(`${got.length} frames, expected ${frames}`);
  return { ok: problems.length === 0, read: got.length, first: got[0], last: got[got.length - 1], problems };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const a = process.argv.slice(2);
  const opt = (k, d) => (a.includes(k) ? Number(a[a.indexOf(k) + 1]) : d);
  const r = await checkFile(a[0], { from: opt('--from', 0), frames: a.includes('--frames') ? opt('--frames') : null });
  console.log(JSON.stringify({ ...r, problems: r.problems.slice(0, 10), problemCount: r.problems.length }, null, 1));
  process.exit(r.ok ? 0 : 1);
}
