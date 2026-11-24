// Renders the film through headless Chromium on the GPU into a lossless intermediate, then a master with the song.
//
//   node tools/promo/video/capture/render.mjs [--from 0] [--to 9074] [--w 1920 --h 1080] [--subframes 1]
//        [--shards 3] [--out renders/promo/video/out/film.mp4] [--check] [--codec x265|x264] [--bits 10|8]
//        [--flags vulkan] [--keep] [--crf N] [--preset slow] [--shutter 0.5] [--reencode]
//
// Frames [from, to) (to is exclusive), frame i at t = i / 60. Each shard is a page of the film drawing its own
// frame range; a frame's pixels are read with gl.readPixels and POSTed as raw bytes to this process, which
// pipes them in order to ffmpeg. The intermediate is FFV1 (lossless, every frame a keyframe, planar RGB, so
// the film's exact 8-bit or 10-bit pixels are kept) under renders/promo/video/frames/<name>/. The shards are
// joined by stream copy, then the master is encoded with the FLAC's audio from the same time:
//   x265 (the default): Main 10, CRF 16, yuv420p10le, BT.709    x264: High, CRF 14, yuv420p, BT.709 (8-bit)
// --reencode makes a new master (--out names the render) from the intermediate a render left.
// --check stamps each frame's index in its top rows and reads every index back from the intermediate and
// the master (check.mjs), so a dropped or doubled frame fails the render.
import { spawn } from 'node:child_process';
import { mkdirSync, rmSync, writeFileSync, readFileSync, statSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { launch, open, server } from './browser.mjs';
import { ROOT } from './serve.mjs';
import { checkFile } from './check.mjs';

const FPS = 60;
const AUDIO = join(ROOT, 'renders/promo/capture-live-A/render.flac');

function args() {
  const o = { from: 0, to: null, w: 1920, h: 1080, subframes: 1, shards: 3, out: 'renders/promo/video/out/film.mp4', check: false,
    codec: 'x265', bits: null, flags: 'vulkan', keep: false, reencode: false, crf: null, preset: 'slow', inflight: 3, shutter: 0.5 };
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i++) {
    const k = a[i].replace(/^--/, '');
    if (k === 'check' || k === 'keep' || k === 'reencode') o[k] = true;
    else if (!(k in o)) throw new Error(`unknown option ${a[i]}`);
    else o[k] = a[++i];
  }
  for (const k of ['from', 'to', 'w', 'h', 'subframes', 'shards', 'bits', 'crf', 'inflight', 'shutter']) if (o[k] !== null) o[k] = Number(o[k]);
  o.bits = o.bits || (o.codec === 'x265' ? 10 : 8);
  return o;
}

function run(cmd, argv, { quiet = true } = {}) {
  return new Promise((ok, fail) => {
    const p = spawn(cmd, argv, { stdio: ['ignore', quiet ? 'ignore' : 'inherit', 'pipe'] });
    let err = '';
    p.stderr.on('data', (d) => { err += d; if (err.length > 20000) err = err.slice(-20000); });
    p.on('close', (code) => (code === 0 ? ok() : fail(new Error(`${cmd} ${argv.join(' ')}\n${err}`))));
  });
}

// an ffmpeg taking raw frames on stdin into FFV1, frames handed in index order whatever order they arrive in
function intermediate(file, o, first) {
  const pix = o.bits === 10 ? 'x2bgr10le' : 'rgba';
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', pix, '-s', `${o.w}x${o.h}`, '-r', String(FPS),
    '-i', 'pipe:0', '-c:v', 'ffv1', '-level', '3', '-g', '1', '-slices', '24', '-slicecrc', '1', '-threads', '8',
    '-pix_fmt', o.bits === 10 ? 'gbrp10le' : 'gbrp', file], { stdio: ['pipe', 'ignore', 'pipe'] });
  let err = '';
  ff.stderr.on('data', (d) => { err += d; });
  const done = new Promise((ok, fail) => ff.on('close', (c) => (c === 0 ? ok() : fail(new Error(`ffmpeg ${file}: ${err}`)))));
  const waiting = new Map();
  let next = first, written = 0;
  const bytes = o.w * o.h * 4;
  const write = (buf) => new Promise((ok) => (ff.stdin.write(buf) ? ok() : ff.stdin.once('drain', ok)));
  return {
    done, get written() { return written; },
    async put(i, buf) {
      if (buf.length !== bytes) throw new Error(`frame ${i}: ${buf.length} bytes, expected ${bytes}`);
      if (waiting.has(i) || i < next) throw new Error(`frame ${i} arrived twice`);
      waiting.set(i, buf);
      while (waiting.has(next)) {
        const b = waiting.get(next);
        waiting.delete(next);
        next++;
        written++;
        await write(b);
      }
    },
    end() { ff.stdin.end(); return done; },
  };
}

// the master from the intermediate, with the song from frame `from` on; the audio is padded with silence
// to the last frame (the file rings to 151.227 s, the 9,074th frame starts at 151.217 s)
async function master(joined, out, o, from, total) {
  const vf = `scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=${o.codec === 'x265' ? 'yuv420p10le' : 'yuv420p'}`;
  const codec = o.codec === 'x265'
    ? ['-c:v', 'libx265', '-preset', o.preset, '-crf', String(o.crf ?? 16), '-profile:v', 'main10', '-tag:v', 'hvc1',
      '-x265-params', 'colorprim=bt709:transfer=bt709:colormatrix=bt709:range=limited:log-level=error']
    : ['-c:v', 'libx264', '-preset', o.preset, '-crf', String(o.crf ?? 14), '-profile:v', 'high', '-tune', 'film'];
  const seconds = (total / FPS).toFixed(6);
  await run('ffmpeg', ['-v', 'error', '-y', '-i', joined, '-ss', (from / FPS).toFixed(6), '-t', seconds, '-i', AUDIO,
    '-map', '0:v', '-map', '1:a', '-vf', vf, ...codec,
    '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv',
    '-r', String(FPS), '-af', 'apad', '-c:a', 'aac', '-b:a', '320k', '-ar', '48000', '-t', seconds, '-movflags', '+faststart', out]);
}

// --reencode: a new master (another codec, CRF) from the intermediate a render left, without rendering again
async function reencode(o, name, work, out) {
  const meta = JSON.parse(readFileSync(join(work, 'render.json'), 'utf8'));
  const joined = join(work, `${name}.mkv`);
  if (meta.bits !== o.bits) throw new Error(`the intermediate is ${meta.bits}-bit; pass --bits ${meta.bits}`);
  const t1 = Date.now();
  await master(joined, out, o, meta.from, meta.to - meta.from);
  console.log(`master ${out} (${(statSync(out).size / 1e6).toFixed(1)} MB) encoded in ${((Date.now() - t1) / 1000).toFixed(1)} s`);
  if (o.check) {
    const r = await checkFile(out, { from: meta.from, frames: meta.to - meta.from });
    console.log(`check ${basename(out)}: ${r.ok ? 'every frame once, in order' : 'FAILED'} (${r.read} frames read; ${r.problems.slice(0, 5).join('; ')})`);
    if (!r.ok) process.exitCode = 1;
  }
}

async function main() {
  const o = args();
  const name = basename(o.out).replace(/\.[^.]+$/, '');
  const out = resolve(ROOT, o.out);
  const work = join(ROOT, 'renders/promo/video/frames', name);
  mkdirSync(work, { recursive: true });
  mkdirSync(dirname(out), { recursive: true });
  if (o.reencode) return reencode(o, name, work, out);

  const sinks = {}, shardFiles = [];
  const srv = await server(sinks);
  const browser = await launch(o.flags);
  const browsers = [browser];
  const t0 = Date.now();
  let total = 0, frames = 0;
  try {
    // the frame range and the page count, then each shard's slice
    const probe = await open(browser, { w: 64, h: 36, server: srv });
    const filmFrames = await probe.page.evaluate(() => window.film.frames);
    await probe.page.close();
    const to = Math.min(o.to ?? filmFrames, filmFrames), from = Math.max(o.from, 0);
    total = to - from;
    if (total <= 0) throw new Error('no frames');
    const K = Math.max(1, Math.min(o.shards, total));
    const per = Math.ceil(total / K);
    console.log(`${name}: frames ${from}..${to - 1} (${total}) at ${o.w}x${o.h}, ${o.subframes} subframe(s), ${K} shard(s), ${o.bits}-bit`);
    const jobs = [];
    for (let k = 0; k < K; k++) {
      const a = from + k * per, b = Math.min(a + per, to);
      if (a >= b) continue;
      const file = join(work, `shard-${String(k).padStart(2, '0')}.mkv`);
      shardFiles.push(file);
      const sink = intermediate(file, o, a);
      sinks[`s${k}`] = (buf, q) => sink.put(Number(q.get('i')), buf);
      jobs.push((async () => {
        // each shard in its own browser: uploads from one browser share one network process
        const own = k === 0 ? browser : await launch(o.flags);
        browsers.push(own);
        const { page, errors } = await open(own, { w: o.w, h: o.h, server: srv });
        const started = Date.now();
        const r = await page.evaluate(({ a, b, opts }) => window.film.send(a, b, `/sink/s${opts.k}`, opts),
          { a, b, opts: { k, subframes: o.subframes, shutter: o.shutter, check: o.check, bits: o.bits, inflight: o.inflight } });
        await sink.end();
        if (sink.written !== b - a) throw new Error(`shard ${k}: ${sink.written} frames written of ${b - a}`);
        if (errors.length) console.error(`shard ${k} page errors:\n${errors.join('\n')}`);
        frames += b - a;
        const s = (Date.now() - started) / 1000;
        console.log(`  shard ${k}: frames ${a}..${b - 1} in ${s.toFixed(1)} s (${((b - a) / s).toFixed(1)} fps; page ${(r.ms / 1000).toFixed(1)} s)`);
        await page.close();
      })());
    }
    await Promise.all(jobs);
    const renderS = (Date.now() - t0) / 1000;
    console.log(`rendered ${frames} frames in ${renderS.toFixed(1)} s: ${(frames / renderS).toFixed(1)} fps overall`);

    // join the shards (stream copy), then the master with the song from the same moment
    const joined = join(work, `${name}.mkv`);
    const list = join(work, 'shards.txt');
    writeFileSync(list, shardFiles.map((f) => `file '${f}'`).join('\n') + '\n');
    await run('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list, '-c', 'copy', joined]);
    if (!o.keep) for (const f of [...shardFiles, list]) rmSync(f);
    const t1 = Date.now();
    await master(joined, out, o, from, total);
    const encS = (Date.now() - t1) / 1000;
    console.log(`master ${out} (${(statSync(out).size / 1e6).toFixed(1)} MB) encoded in ${encS.toFixed(1)} s; ` +
      `intermediate ${joined} (${(statSync(joined).size / 1e9).toFixed(2)} GB)`);
    if (o.check) {
      for (const f of [joined, out]) {
        const r = await checkFile(f, { from, frames: total, w: o.w, h: o.h });
        console.log(`check ${basename(f)}: ${r.ok ? 'every frame once, in order' : 'FAILED'} (${r.read} frames read; ${r.problems.slice(0, 5).join('; ')})`);
        if (!r.ok) process.exitCode = 1;
      }
    }
    writeFileSync(join(work, 'render.json'), JSON.stringify({ ...o, from, to, frames, renderSeconds: renderS, encodeSeconds: encS,
      fps: frames / renderS, intermediate: joined, master: out }, null, 2));
  } finally {
    for (const b of new Set(browsers)) await b.close();
    srv.close();
  }
}

main().catch((e) => { console.error(e.stack || e); process.exit(1); });
