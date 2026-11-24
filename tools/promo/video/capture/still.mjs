// Stills of the film as PNG, drawn exactly as render.mjs draws frames.
//
//   node tools/promo/video/capture/still.mjs --out DIR [--w 1920 --h 1080] [--scene id] [--subframes N] NAME=SECONDS ...
//   (or FRAME numbers: NAME=f900; a forced transition between two scenes: NAME=SECONDS@ink:s02_voice:s09_broadside:0.5[:SECONDS of the second scene])
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { launch, open, server } from './browser.mjs';

const args = process.argv.slice(2);
const opt = { out: 'renders/promo/video/out/stills', w: 1920, h: 1080, scene: '', subframes: 1, flags: 'vulkan', check: false };
const shots = [];
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a.startsWith('--')) {
    const k = a.slice(2);
    if (k === 'check') opt.check = true;
    else opt[k] = typeof opt[k] === 'number' ? Number(args[++i]) : args[++i];
  } else shots.push(a.split('='));
}
const out = resolve(opt.out);
mkdirSync(out, { recursive: true });
const srv = await server();
const browser = await launch(opt.flags);
try {
  const { page, errors } = await open(browser, { w: opt.w, h: opt.h, server: srv, query: opt.scene ? `&scene=${opt.scene}` : '' });
  for (const [name, spec] of shots) {
    const [at, tr] = spec.split('@');
    const test = tr ? (([kind, a, b, k, tb]) => ({ kind, a, b, k: Number(k), tb: tb === undefined ? undefined : Number(tb) }))(tr.split(':')) : null;
    const frame = at.startsWith('f') ? Number(at.slice(1)) : Math.round(Number(at) * 60);
    const b64 = await page.evaluate(async ({ frame, subframes, check, test }) => {
      const px = await window.film.capture(frame, { subframes, check, test });
      const [w, h] = window.film.info().size;
      const c = new OffscreenCanvas(w, h);
      c.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(px.buffer), w, h), 0, 0);
      const blob = await c.convertToBlob({ type: 'image/png' });
      const bytes = new Uint8Array(await blob.arrayBuffer());
      let s = '';
      for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      return btoa(s);
    }, { frame, subframes: opt.subframes, check: opt.check, test });
    const file = join(out, `${name}.png`);
    writeFileSync(file, Buffer.from(b64, 'base64'));
    console.log(`${file}  frame ${frame} (${(frame / 60).toFixed(3)} s)`);
  }
  if (errors.length) console.error('page errors:\n' + errors.join('\n'));
} finally {
  await browser.close();
  srv.close();
}
