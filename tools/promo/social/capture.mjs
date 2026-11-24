// Serves the social cut's page and renders it.
//
//   node tools/promo/social/capture.mjs serve [--port 8861]            preview at http://127.0.0.1:8861/
//   node tools/promo/social/capture.mjs stills --out DIR T1 T2 ...      PNG stills at those seconds
//   node tools/promo/social/capture.mjs render [--fps 60] [--shards 4] [--out renders/promo/social/out/cut.mp4]
//   any mode: --page synced.html (the synced cut's page) --audio renders/promo/social/synced/cut.wav
//
// render draws every frame in headless Chromium (Canvas 2D), saves PNGs under renders/promo/social/frames/,
// and encodes H.264 High, yuv420p, BT.709 with cut.wav as AAC 320k: what Instagram and X take without
// re-encoding badly.
import { createServer } from 'node:http';
import { readFile, mkdir, rm } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { join, resolve, extname, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '../video/capture/node_modules/playwright-core/index.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '../../..');
const DATA = join(ROOT, 'renders/promo/social/data');
const FONTS = { '/fonts/Georgia.ttf': '/usr/share/fonts/TTF/Georgia.TTF', '/fonts/Georgiai.ttf': '/usr/share/fonts/TTF/Georgiai.TTF' };
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.wav': 'audio/wav', '.ttf': 'font/ttf', '.jpg': 'image/jpeg', '.png': 'image/png' };

function serve(port) {
  const srv = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    if (path === '/favicon.ico') { res.writeHead(204); res.end(); return; }
    let file = FONTS[path];
    if (!file && path.startsWith('/data/')) file = join(DATA, path.slice(6));
    if (!file && path.startsWith('/synced/')) file = join(ROOT, 'renders/promo/social/synced', path.slice(8));
    if (!file) file = join(HERE, 'web', path === '/' ? 'index.html' : path);
    if (file.includes('..')) { res.writeHead(403); res.end(); return; }
    try {
      const body = await readFile(file);
      res.writeHead(200, { 'content-type': TYPES[extname(file).toLowerCase()] || 'application/octet-stream', 'cache-control': 'no-store' });
      res.end(body);
    } catch {
      res.writeHead(404); res.end();
    }
  });
  return new Promise((ok) => srv.listen(port, '127.0.0.1', () => ok(srv)));
}

function opts() {
  const a = process.argv.slice(3), o = { _: [] };
  for (let i = 0; i < a.length; i++) {
    if (a[i] === '--gpu') o.gpu = true;
    else if (a[i].startsWith('--')) o[a[i].slice(2)] = a[++i];
    else o._.push(a[i]);
  }
  return o;
}

async function page(browser, port) {
  const p = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  const errors = [];
  p.on('pageerror', (e) => errors.push(e.message));
  p.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await p.goto(`http://127.0.0.1:${port}/${PAGE}?capture=1`);
  await p.evaluate(() => window.cutReady);
  if (errors.length) throw new Error(errors.join('\n'));
  return p;
}

async function shot(p, t, file) {
  await p.evaluate((t) => window.cut.draw(t), t);
  await p.screenshot({ path: file, clip: { x: 0, y: 0, width: 1080, height: 1920 }, type: 'png' });
}

function run(cmd, args) {
  return new Promise((ok, fail) => {
    const c = spawn(cmd, args, { stdio: ['ignore', 'inherit', 'inherit'] });
    c.on('close', (code) => (code === 0 ? ok() : fail(new Error(`${cmd} exited ${code}`))));
  });
}

const mode = process.argv[2];
const o = opts();
const PAGE = o.page || '';
const srv = await serve(Number(o.port || (mode === 'serve' ? 8861 : 0)));
const port = srv.address().port;
if (mode === 'serve') {
  console.log(`http://127.0.0.1:${port}/`);
} else {
  // --gpu: the flags that reach the graphics card (as tools/promo/video/capture/browser.mjs), for a WebGL page
  const gpu = 'gpu' in o ? ['--headless=new', '--use-gl=angle', '--use-angle=vulkan', '--enable-features=Vulkan', '--ignore-gpu-blocklist'] : [];
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/usr/bin/chromium',
    ignoreDefaultArgs: gpu.length ? ['--headless'] : [],
    args: [...gpu, '--force-color-profile=srgb', '--disable-lcd-text', '--font-render-hinting=none'] });
  try {
    if (mode === 'stills') {
      await mkdir(o.out, { recursive: true });
      const p = await page(browser, port);
      for (const t of o._) await shot(p, Number(t), join(o.out, `t${Number(t).toFixed(2)}.png`));
    } else if (mode === 'render') {
      const fps = Number(o.fps || 60), shards = Number(o.shards || 4);
      const out = resolve(ROOT, o.out || 'renders/promo/social/out/cut.mp4');
      const frames = join(ROOT, 'renders/promo/social/frames');
      await rm(frames, { recursive: true, force: true });
      await mkdir(frames, { recursive: true });
      await mkdir(dirname(out), { recursive: true });
      const probe = await page(browser, port);
      const dur = await probe.evaluate(() => window.cut.duration);
      await probe.close();
      const n = Math.ceil(dur * fps);
      let done = 0;
      await Promise.all(Array.from({ length: shards }, async (_, s) => {
        const p = await page(browser, port);
        for (let i = s; i < n; i += shards) {
          await shot(p, i / fps, join(frames, `f${String(i).padStart(5, '0')}.png`));
          if (++done % 300 === 0) console.log(`${done}/${n}`);
        }
      }));
      await run('ffmpeg', ['-v', 'error', '-y', '-framerate', String(fps), '-i', join(frames, 'f%05d.png'), '-i', join(ROOT, o.audio || 'renders/promo/social/data/cut.wav'),
        '-c:v', 'libx264', '-profile:v', 'high', '-preset', 'slow', '-crf', String(o.crf || 16), '-pix_fmt', 'yuv420p',
        '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-vf', 'scale=out_color_matrix=bt709',
        '-af', 'loudnorm=I=-14:TP=-1.0:LRA=11', '-ar', '48000', '-c:a', 'aac', '-b:a', '320k', '-movflags', '+faststart', '-shortest', out]);
      console.log(out);
    }
  } finally {
    await browser.close();
    srv.close();
  }
}
