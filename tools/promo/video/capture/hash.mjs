// The SHA-256 of frames' raw pixels, each drawn in this process's own Chromium: run it twice (or with frames in
// another order) and compare, to show a frame is a pure function of its index.
//
//   node tools/promo/video/capture/hash.mjs [--w 1920 --h 1080] [--subframes N] [--flags vulkan] FRAME ...
import { createHash } from 'node:crypto';
import { launch, open, server } from './browser.mjs';

const a = process.argv.slice(2);
const opt = { w: 1920, h: 1080, subframes: 1, flags: 'vulkan' };
const frames = [];
for (let i = 0; i < a.length; i++) {
  if (a[i].startsWith('--')) { const k = a[i].slice(2); opt[k] = k === 'flags' ? a[++i] : Number(a[++i]); }
  else frames.push(Number(a[i]));
}
const srv = await server();
const browser = await launch(opt.flags);
try {
  const { page } = await open(browser, { w: opt.w, h: opt.h, server: srv });
  for (const f of frames) {
    const b64 = await page.evaluate(async ({ f, subframes }) => (await window.film.capture(f, { subframes })).toBase64(), { f, subframes: opt.subframes });
    const px = Buffer.from(b64, 'base64');
    console.log(`frame ${f} ${opt.w}x${opt.h} sha256 ${createHash('sha256').update(px).digest('hex')} (pid ${process.pid})`);
  }
} finally {
  await browser.close();
  srv.close();
}
