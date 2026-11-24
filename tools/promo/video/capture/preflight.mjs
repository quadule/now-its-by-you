// Which Chromium flags reach the GPU, and how fast the film draws there.
//
//   node tools/promo/video/capture/preflight.mjs [--sets vulkan,angle-gl,...] [--w 1920 --h 1080] [--from 600]
//
// For each flag set: the WebGL renderer string, the largest texture, float render targets, and the time for
// 60 frames drawn (film.render) and 60 frames drawn and read back (film.capture), at w x h.
import { FLAGS, launch, open, server } from './browser.mjs';

const a = process.argv.slice(2);
const opt = (k, d) => (a.includes(k) ? a[a.indexOf(k) + 1] : d);
const sets = opt('--sets', 'vulkan,angle-gl,angle-gl-egl,default,software').split(',');
const w = Number(opt('--w', 1920)), h = Number(opt('--h', 1080)), from = Number(opt('--from', 600));

const srv = await server();
const results = [];
for (const name of sets) {
  if (!FLAGS[name]) { console.log(`${name}: no such flag set`); continue; }
  let browser;
  try {
    browser = await launch(name);
    const { page, errors } = await open(browser, { w, h, server: srv });
    const r = await page.evaluate(async ({ from }) => {
      const info = window.film.info();
      const T = () => performance.now();
      await window.film.render(from);
      let t = T();
      for (let i = from; i < from + 60; i++) await window.film.render(i);
      const render = T() - t;
      t = T();
      for (let i = from; i < from + 60; i++) await window.film.capture(i);
      const capture = T() - t;
      return { ...info, render60: render, capture60: capture };
    }, { from });
    const gpu = /NVIDIA/i.test(r.renderer) && !/SwiftShader/i.test(r.renderer);
    results.push({ name, ...r, gpu });
    console.log(`${name.padEnd(13)} ${gpu ? 'GPU ' : 'SOFT'} ${r.renderer}`);
    console.log(`${''.padEnd(18)}max texture ${r.maxTexture}, float targets ${r.floatTargets}, float blend ${r.floatBlend}; ` +
      `60 frames at ${w}x${h}: drawn ${(r.render60 / 1000).toFixed(2)} s (${(60000 / r.render60).toFixed(0)} fps), ` +
      `drawn and read ${(r.capture60 / 1000).toFixed(2)} s (${(60000 / r.capture60).toFixed(0)} fps)` + (errors.length ? `; page errors: ${errors.length}` : ''));
  } catch (e) {
    console.log(`${name.padEnd(13)} FAILED ${e.message.split('\n')[0]}`);
  } finally {
    if (browser) await browser.close();
  }
}
srv.close();
const best = results.find((r) => r.gpu);
console.log(best ? `\nuse --flags ${best.name}` : '\nno flag set reached the NVIDIA GPU headless: try --sets headed (on the desktop session)');
