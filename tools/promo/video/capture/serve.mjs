// The film's one local server: zero dependencies, nothing cached.
//
//   node tools/promo/video/capture/serve.mjs [--port 8860]
//
//   /            tools/promo/video/web/
//   /data/       renders/promo/video/data/ (a file missing there is answered from scratch/fixture/)
//   /blender/    renders/promo/video/blender/
//   /studio/     renders/promo/video/studio/
//   /art/        renders/review/artwork/cover/ (the packet face art: front-color.png ...)
//   /audio.flac  renders/promo/capture-live-A/render.flac (byte ranges, so the scrubber seeks)
//   /fonts/      Georgia from /usr/share/fonts/TTF/ (regular, italic, bold)
//   POST /sink/<name>   a frame's raw bytes, handed to the sink render.mjs registered under that name
//
// render.mjs imports `serve()` and starts its own instance on a free port with its sinks.
import { createServer } from 'node:http';
import { createReadStream, promises as fs } from 'node:fs';
import { extname, join, normalize, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
export const ROOT = resolve(HERE, '../../../..');
const VIDEO = join(ROOT, 'renders/promo/video');
const ROUTES = [
  ['/data/', [join(VIDEO, 'data'), join(VIDEO, 'scratch/fixture')]],
  ['/blender/', [join(VIDEO, 'blender')]],
  ['/studio/', [join(VIDEO, 'studio')]],
  ['/art/', [join(ROOT, 'renders/review/artwork/cover')]],
  ['/', [join(ROOT, 'tools/promo/video/web')]],
];
const FILES = {
  '/audio.flac': join(ROOT, 'renders/promo/capture-live-A/render.flac'),
  '/fonts/Georgia.ttf': '/usr/share/fonts/TTF/Georgia.TTF',
  '/fonts/Georgiai.ttf': '/usr/share/fonts/TTF/Georgiai.TTF',
  '/fonts/Georgiab.ttf': '/usr/share/fonts/TTF/Georgiab.TTF',
};
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json', '.css': 'text/css', '.md': 'text/markdown; charset=utf-8', '.bin': 'application/octet-stream',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.exr': 'application/octet-stream',
  '.flac': 'audio/flac', '.wav': 'audio/wav', '.ttf': 'font/ttf', '.svg': 'image/svg+xml',
};

async function locate(path) {
  if (FILES[path]) return FILES[path];
  for (const [prefix, dirs] of ROUTES) {
    if (!path.startsWith(prefix)) continue;
    let rest = normalize(decodeURIComponent(path.slice(prefix.length)));
    if (rest.startsWith('..')) return null;
    if (rest === '.' || rest.endsWith('/') || rest === '') rest = join(rest, 'index.html');
    for (const dir of dirs) {
      const file = join(dir, rest);
      try {
        const st = await fs.stat(file);
        if (st.isDirectory()) {
          const index = join(file, 'index.html');
          await fs.stat(index);
          return index;
        }
        return file;
      } catch { /* the next directory */ }
    }
    return null;
  }
  return null;
}

async function file(req, res, path) {
  const st = await fs.stat(path);
  const headers = {
    'Content-Type': TYPES[extname(path).toLowerCase()] || 'application/octet-stream',
    'Cache-Control': 'no-store', 'Accept-Ranges': 'bytes', 'Access-Control-Allow-Origin': '*',
  };
  const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || '');
  if (range) {
    let start = range[1] === '' ? st.size - Number(range[2]) : Number(range[1]);
    let end = range[1] !== '' && range[2] !== '' ? Number(range[2]) : st.size - 1;
    end = Math.min(end, st.size - 1);
    if (start > end || start < 0) {
      res.writeHead(416, { 'Content-Range': `bytes */${st.size}` });
      return res.end();
    }
    res.writeHead(206, { ...headers, 'Content-Range': `bytes ${start}-${end}/${st.size}`, 'Content-Length': end - start + 1 });
    if (req.method === 'HEAD') return res.end();
    return createReadStream(path, { start, end }).pipe(res);
  }
  res.writeHead(200, { ...headers, 'Content-Length': st.size });
  if (req.method === 'HEAD') return res.end();
  createReadStream(path).pipe(res);
}

// sinks: name -> async (Buffer, query) => void
export function serve({ port = 8860, host = '127.0.0.1', sinks = {}, quiet = false } = {}) {
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, 'http://x');
    try {
      if (req.method === 'POST' && url.pathname.startsWith('/sink/')) {
        const sink = sinks[url.pathname.slice(6)];
        if (!sink) { res.writeHead(404); return res.end(); }
        const chunks = [];
        for await (const c of req) chunks.push(c);
        await sink(Buffer.concat(chunks), url.searchParams);
        res.writeHead(204, { 'Cache-Control': 'no-store' });
        return res.end();
      }
      const path = await locate(url.pathname);
      if (!path) { res.writeHead(404, { 'Content-Type': 'text/plain' }); return res.end('not found\n'); }
      await file(req, res, path);
    } catch (e) {
      if (!quiet) console.error(req.method, url.pathname, e.message);
      if (!res.headersSent) res.writeHead(500, { 'Content-Type': 'text/plain' });
      res.end(String(e.message));
    }
  });
  return new Promise((ok, fail) => {
    server.once('error', fail);
    server.listen(port, host, () => {
      if (!quiet) console.log(`film at http://${host}:${server.address().port}/`);
      ok(server);
    });
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const i = process.argv.indexOf('--port');
  serve({ port: i > 0 ? Number(process.argv[i + 1]) : 8860 });
}
