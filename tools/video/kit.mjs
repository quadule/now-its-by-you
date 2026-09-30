// The kit a filmed studio session is made with: a browser driven as a person would (a visible cursor that glides,
// clicks with a ripple, types, drags), captions in the page's own type and colours, native selects shown as the
// page's own list, sharp capture, and the action log tools/video/beatcut.py cuts to the beat.
//
//   import { session } from './kit.mjs';
//   const s = await session({ url, out, video: true, zoom: 1.2 });
//   await s.flash(); await s.phase('tempo', 'Intro', 'up to dance speed'); await s.click(loc, 'tempo'); ...
//   await s.finish();
//
// Capture: Chrome's own screencast (CDP Page.startScreencast), each compositor frame a JPEG at quality 95 with its
// timestamp, assembled by ffmpeg at the frames' real times into <out>/raw.mp4 (H.264, CRF 10, 30 fps) whose t = 0 is
// the log's t = 0. Playwright's recordVideo is VP8 at about 1 Mb/s, which blurs small text; this is about 20 times
// that and keeps it sharp. The page is shown at `zoom` (CSS zoom on the root: the same 1920x1080 frame, the page's
// text 1.2 times larger, laid out as a 1600 px window would be). Captions sit on an index card at the foot, left;
// `avoid` (a selector: the studio's words, '#page') keeps them to the gutter beside such a column when it shows.
//
// The log: <out>/actions.json, {t0, url, viewport, zoom, actions: [{t, kind, label, phase, weight 0-3, hold (beats),
// dur?}]}, t in seconds of the raw video. A white flash (kind "sync") lets beatcut.py check the offset to the frame.
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const FFMPEG = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/usr/bin/ffmpeg'].find((p) => fs.existsSync(p)) || 'ffmpeg';

// drawn in the page, in a layer that undoes the page's zoom so its numbers are the frame's pixels
function overlay([Z, avoid]) {
  const install = () => {
    if (document.getElementById('pw-layer')) return;
    if (Z !== 1) document.documentElement.style.zoom = String(Z);
    const layer = document.createElement('div');
    layer.id = 'pw-layer';
    layer.setAttribute('aria-hidden', 'true');
    Object.assign(layer.style, { position: 'fixed', inset: '0', zoom: String(1 / Z), pointerEvents: 'none', zIndex: 2147483640 });
    document.documentElement.appendChild(layer);
    const css = document.createElement('style');
    css.textContent = `
      #pw-layer { font-family: var(--sans); }
      #pw-cursor { position: fixed; left: 0; top: 0; transform: translate(-3px,-2px); filter: drop-shadow(0 1px 2px rgba(0,0,0,.45)); z-index: 5; }
      .pw-ripple { position: fixed; width: 40px; height: 40px; margin: -20px 0 0 -20px; border-radius: 50%;
        border: 3px solid var(--red); opacity: .9; transition: transform .5s ease-out, opacity .5s ease-out; z-index: 4; }
      #pw-caption { position: fixed; left: 36px; bottom: 34px; max-width: 640px; padding: 14px 22px 16px;
        background: var(--card); color: var(--ink); border: 1px solid var(--rule); border-top: 3px double var(--red);
        box-shadow: 0 8px 28px rgba(43,35,29,.18); border-radius: 2px;
        opacity: 0; transform: translateY(8px); transition: opacity .35s ease, transform .35s ease; z-index: 3; }
      #pw-caption.on { opacity: 1; transform: none; }
      #pw-caption.narrow { padding: 12px 16px 14px; }
      #pw-caption.narrow .k { font-size: 16px; }
      #pw-caption.narrow .t { font-size: 23px; }
      #pw-caption .k { font-family: var(--serif); font-variant: small-caps; text-transform: lowercase; letter-spacing: .16em;
        color: var(--red); font-size: 21px; line-height: 1; margin-bottom: 8px; }
      #pw-caption .k b { font-weight: 400; color: var(--ink); opacity: .55; letter-spacing: .08em; }
      #pw-caption .t { font-family: var(--serif); font-size: 31px; line-height: 1.18; }
      #pw-caption .t em { color: var(--hand); font-style: italic; }
      #pw-list { position: fixed; background: var(--card); color: var(--ink); border: 1px solid var(--rule-strong);
        box-shadow: 0 10px 30px rgba(43,35,29,.25); border-radius: 2px; padding: 4px 0; z-index: 2;
        font-family: var(--sans); opacity: 0; transition: opacity .18s ease; }
      #pw-list.on { opacity: 1; }
      #pw-list div { padding: 6px 16px; white-space: nowrap; }
      #pw-list div.cur { font-weight: 600; }
      #pw-list div.cur::before { content: '✓'; position: absolute; left: 4px; }
      #pw-list div.hot { background: var(--hand); color: var(--card); }
      #pw-list div.off { opacity: .45; }
    `;
    document.head.appendChild(css);
    const c = document.createElement('div');
    c.id = 'pw-cursor';
    c.innerHTML = '<svg width="30" height="30" viewBox="0 0 28 28"><path d="M3 2 L3 22 L8.5 17 L12.5 26 L16 24.5 L12 15.8 L19.5 15.8 Z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    layer.appendChild(c);
    const cap = document.createElement('div');
    cap.id = 'pw-caption';
    layer.appendChild(cap);
    // the pointer's place, in the frame's pixels (a zoomed page's clientX is the frame's too)
    window.addEventListener('mousemove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    window.__pwRipple = (x, y) => {
      const r = document.createElement('div');
      r.className = 'pw-ripple';
      Object.assign(r.style, { left: x + 'px', top: y + 'px' });
      layer.appendChild(r);
      requestAnimationFrame(() => requestAnimationFrame(() => { r.style.transform = 'scale(1.9)'; r.style.opacity = '0'; }));
      setTimeout(() => r.remove(), 650);
    };
    window.addEventListener('mousedown', (e) => window.__pwRipple(e.clientX, e.clientY), true);
    // the caption keeps to the gutter beside a column it would cover (the studio's Page: the words)
    setInterval(() => {
      const col = avoid && [...document.querySelectorAll(avoid)].find((el) => el.getClientRects().length && el.getBoundingClientRect().width > 0);
      const room = col ? col.getBoundingClientRect().left - 36 - 18 : Infinity;
      cap.classList.toggle('narrow', room < 640);
      cap.style.maxWidth = room < 640 ? Math.max(220, room) + 'px' : '';
    }, 200);
    window.__pwCaption = (kicker, text, where) => {
      cap.classList.remove('on');
      setTimeout(() => {
        if (!text) return;
        cap.innerHTML = `<div class="k">${kicker}</div><div class="t">${text}</div>`;
        cap.style.left = where === 'right' ? 'auto' : '36px';
        cap.style.right = where === 'right' ? '36px' : 'auto';
        cap.classList.add('on');
      }, 360);
    };
    // a native select's list, drawn as the page would (a headless browser draws none)
    window.__pwList = (rect, options, current, fontPx) => {
      document.getElementById('pw-list')?.remove();
      const l = document.createElement('div');
      l.id = 'pw-list';
      l.style.fontSize = fontPx + 'px';
      l.style.minWidth = rect.width + 'px';
      l.innerHTML = options.map((o, i) => `<div data-i="${i}" class="${i === current ? 'cur' : ''}${o.disabled ? ' off' : ''}" style="position:relative">${o.text.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</div>`).join('');
      layer.appendChild(l);
      const h = l.getBoundingClientRect().height, below = innerHeight - rect.bottom - 12;
      l.style.left = rect.left + 'px';
      l.style.top = (h <= below ? rect.bottom + 2 : Math.max(8, rect.top - h - 2)) + 'px';
      requestAnimationFrame(() => l.classList.add('on'));
      return [...l.children].map((d) => { const r = d.getBoundingClientRect(); return { x: r.left + Math.min(r.width / 2, 120), y: r.top + r.height / 2 }; });
    };
    window.__pwHot = (i) => document.querySelectorAll('#pw-list div').forEach((d, k) => d.classList.toggle('hot', k === i));
    window.__pwListOff = () => { const l = document.getElementById('pw-list'); if (!l) return; l.classList.remove('on'); setTimeout(() => l.remove(), 250); };
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install); else install();
  // requests in flight: an edit's answer redraws the page (chips grow a mark, rows appear), so the hand waits
  // for it before reaching for the next control, as an eye would
  window.__pwPending = 0;
  const f0 = window.fetch;
  window.fetch = function (...a) { window.__pwPending++; return f0.apply(this, a).finally(() => { window.__pwPending--; }); };
  window.__toasts = [];
  new MutationObserver(() => {
    for (const el of document.querySelectorAll('#toast, [role=alert]')) {
      const t = el.innerText.trim();
      if (t && window.__toasts[window.__toasts.length - 1] !== t) window.__toasts.push(t);
    }
  }).observe(document, { subtree: true, childList: true, characterData: true });
}

export async function session({ url, out, video = true, zoom = 1.2, width = 1920, height = 1080, scheme = 'light', quality = 95, avoid = null }) {
  fs.mkdirSync(out, { recursive: true });
  const framesDir = path.join(out, 'frames-raw');
  if (video) { fs.rmSync(framesDir, { recursive: true, force: true }); fs.mkdirSync(framesDir, { recursive: true }); }
  const browser = await chromium.launch({ headless: true, args: ['--autoplay-policy=no-user-gesture-required', '--hide-scrollbars'] });
  // bypassCSP: the studio's content policy refuses inline <style>, and the overlay's is one (the page's own is untouched)
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: scheme, acceptDownloads: true, bypassCSP: true });
  await ctx.addInitScript(overlay, [zoom, avoid]);
  const page = await ctx.newPage();
  const T0 = Date.now();
  const log = [];
  const frames = [];
  let phase = 'open', cdp = null, writing = 0;
  if (video) {
    cdp = await ctx.newCDPSession(page);
    cdp.on('Page.screencastFrame', (f) => {
      const n = frames.length, file = path.join(framesDir, `${String(n).padStart(6, '0')}.jpg`);
      frames.push({ t: f.metadata.timestamp * 1000 - T0, file });  // ms after T0
      writing++;
      fs.writeFile(file, Buffer.from(f.data, 'base64'), () => { writing--; });
      cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {});
    });
    await cdp.send('Page.startScreencast', { format: 'jpeg', quality, everyNthFrame: 1 });
  }
  const now = () => (Date.now() - T0) / 1000;
  const logFile = path.join(out, 'actions.json');
  function mark(kind, label, o = {}) {
    const e = { t: +now().toFixed(3), kind, label, phase, weight: 1, hold: 2, ...o };
    log.push(e);
    console.log(e.t.toFixed(2).padStart(8), phase.padEnd(10), kind.padEnd(7), label);
    fs.writeFileSync(logFile, JSON.stringify({ t0: T0, url, viewport: [width, height], zoom, actions: log }, null, 1));
    return e;
  }
  const pause = (ms) => page.waitForTimeout(ms);

  // ---------------------------------------------------------------------------------------------- the hand
  let mx = width / 2, my = height / 2;
  async function glide(x, y, ms = 420) {
    const n = Math.max(8, Math.round(ms / 16)), x0 = mx, y0 = my;
    for (let k = 1; k <= n; k++) {
      const u = k / n, e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
      await page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e);
      await pause(16);
    }
    mx = x; my = y;
  }
  const TOP = 110 * zoom, BOTTOM = 190;  // under the sticky transport; above the caption
  async function show(loc, o = {}) {
    await loc.waitFor({ state: 'visible', timeout: 60000 });
    const inView = await loc.evaluate((el, [top, bottom]) => { const r = el.getBoundingClientRect(); return r.top >= top && r.bottom <= innerHeight - bottom; }, [TOP, o.bottom ?? BOTTOM]);
    if (!inView) {
      await loc.evaluate((el, block) => el.scrollIntoView({ behavior: 'smooth', block }), o.block || 'center');
      await pause(750);
    }
    return loc.boundingBox();
  }
  async function settle(timeout = 8000) {  // no request in flight for a moment: the page has drawn its answer
    const t = Date.now();
    let quiet = 0;
    while (Date.now() - t < timeout && quiet < 3) {
      quiet = (await page.evaluate(() => window.__pwPending || 0).catch(() => 0)) ? 0 : quiet + 1;
      await pause(100);
    }
  }
  async function over(loc, fx = 0.5, fy = 0.5, o = {}) {
    await settle();
    let b = await show(loc, o);
    await glide(b.x + b.width * fx, b.y + b.height * fy, o.ms);
    const again = await loc.boundingBox();  // it moved while the hand travelled (a late redraw): follow it
    if (again && (Math.abs(again.x - b.x) > 2 || Math.abs(again.y - b.y) > 2)) {
      b = again;
      await glide(b.x + b.width * fx, b.y + b.height * fy, 200);
    }
    return b;
  }
  async function click(loc, label, o = {}) {
    await over(loc, o.fx ?? 0.5, o.fy ?? 0.5, o);
    await pause(o.before ?? 120);
    mark(o.kind || 'click', label, o);
    await page.mouse.down(); await pause(60); await page.mouse.up();
    await pause(o.after ?? 500);
  }
  async function dbl(loc, label, o = {}) {
    await over(loc, o.fx ?? 0.5, o.fy ?? 0.5, o);
    await pause(120);
    mark('click', label, o);
    await page.mouse.dblclick(mx, my);
    await pause(o.after ?? 700);
  }
  // a native select: its list drawn as the page's own, the pointer to the choice, the value set
  async function choose(loc, want, label, o = {}) {
    const b = await over(loc, 0.75, 0.5, o);
    await pause(150);
    const info = await loc.evaluate((el, want) => {
      const opts = [...el.options].map((op) => ({ text: op.text, value: op.value, disabled: op.disabled }));
      const i = opts.findIndex((op) => (typeof want === 'object' ? op.text === want.label || op.text.startsWith(want.label) : op.value === String(want)));
      return { opts, i, cur: el.selectedIndex, font: parseFloat(getComputedStyle(el).fontSize) * (parseFloat(document.documentElement.style.zoom) || 1) };
    }, want);
    if (info.i < 0) throw new Error(`${label}: no option ${JSON.stringify(want)} in ${info.opts.map((x) => x.text).join(' | ')}`);
    await page.evaluate(([x, y]) => window.__pwRipple(x, y), [mx, my]);
    const rect = { left: b.x, top: b.y, bottom: b.y + b.height, width: b.width };
    const spots = await page.evaluate(([r, opts, cur, f]) => window.__pwList(r, opts, cur, Math.max(15, f + 1)), [rect, info.opts, info.cur, info.font]);
    await pause(380);
    const s = spots[info.i];
    await glide(s.x, s.y, 480);
    await page.evaluate((i) => window.__pwHot(i), info.i);
    await pause(260);
    mark('select', label, o);
    await page.evaluate(([x, y]) => window.__pwRipple(x, y), [s.x, s.y]);
    await loc.selectOption(typeof want === 'object' ? { index: info.i } : String(want));
    await pause(160);
    await page.evaluate(() => window.__pwListOff());
    await pause(o.after ?? 800);
  }
  async function type(loc, text, label, o = {}) {
    await over(loc, 0.3, 0.5, o);
    await page.mouse.down(); await page.mouse.up();
    await page.keyboard.press('Meta+A');
    const e = mark('type', label, { hold: 3, ...o });
    await page.keyboard.type(text, { delay: o.delay ?? 42 });
    e.dur = +(now() - e.t).toFixed(3);
    await pause(o.after ?? 350);
  }
  async function slide(loc, value, label, o = {}) {  // drag a range input's thumb to a value
    const b = await show(loc, o);
    const [mn, mxv, v0] = await loc.evaluate((el) => [+el.min, +el.max, +el.value]);
    const vert = b.height > b.width * 1.5;
    const pad = 8, at = (v) => {
      const u = (v - mn) / (mxv - mn);
      return vert ? [b.x + b.width / 2, b.y + b.height - pad - (b.height - 2 * pad) * u] : [b.x + pad + (b.width - 2 * pad) * u, b.y + b.height / 2];
    };
    await glide(...at(v0));
    await page.mouse.down();
    await glide(...at(value), 560);
    mark('slider', label, o);
    await page.mouse.up();
    await pause(o.after ?? 700);
  }
  async function dragTo(from, x, y, label, o = {}) {
    await over(from, o.fx ?? 0.5, o.fy ?? 0.5, o);
    await page.mouse.down();
    await pause(80);
    await glide(x, y, o.ms ?? 700);
    mark('drag', label, o);
    await page.mouse.up();
    await pause(o.after ?? 1200);
  }
  async function caption(kicker, text, where) { await page.evaluate(([k, t, w]) => window.__pwCaption?.(k, t, w), [kicker, text, where]); }
  async function setPhase(p, kicker, text, where) { phase = p; mark('phase', text || p, { weight: 0 }); await caption(kicker, text, where); }
  async function flash() {  // the log's t is the footage's t once this frame is found
    await page.evaluate(() => {
      const f = document.createElement('div');
      Object.assign(f.style, { position: 'fixed', inset: '0', background: '#fff', zIndex: 2147483647 });
      document.documentElement.appendChild(f);
      setTimeout(() => f.remove(), 240);
    });
    mark('sync', 'white flash', { weight: 0 });
    await pause(900);
  }

  async function finish(extra = {}) {
    fs.writeFileSync(path.join(out, 'page-state.json'), JSON.stringify(await page.evaluate(() => ({ toasts: window.__toasts || [] })).catch(() => ({})), null, 1));
    mark('end', 'end', { weight: 0 });
    const tEnd = now();
    if (cdp) await cdp.send('Page.stopScreencast').catch(() => {});
    await ctx.close();
    await browser.close();
    if (!video) return;
    while (writing) await new Promise((r) => setTimeout(r, 50));
    assemble(frames, tEnd, out, extra.fps || 30);
  }
  return { page, ctx, browser, mark, pause, settle, glide, show, over, click, dbl, choose, type, slide, dragTo, caption, setPhase, flash, finish,
    now, get phase() { return phase; }, set phase(p) { phase = p; } };
}

// the frames at their real times, t = 0 the log's t = 0 (the first frame held back to it), into a constant-rate video
export function assemble(frames, tEnd, out, fps = 30) {
  const list = frames.filter((f) => fs.existsSync(f.file)).sort((a, b) => a.t - b.t);
  if (!list.length) throw new Error('no frames');
  const lines = ['ffconcat version 1.0'];
  for (let i = 0; i < list.length; i++) {
    const t0 = i === 0 ? 0 : list[i].t / 1000;
    const t1 = i + 1 < list.length ? list[i + 1].t / 1000 : tEnd;
    const d = Math.max(0.001, t1 - t0);
    lines.push(`file '${list[i].file}'`, `duration ${d.toFixed(4)}`);
  }
  lines.push(`file '${list[list.length - 1].file}'`);  // the concat demuxer's last duration needs a file after it
  const lst = path.join(out, 'frames.ffconcat');
  fs.writeFileSync(lst, lines.join('\n') + '\n');
  fs.writeFileSync(path.join(out, 'frames.json'), JSON.stringify(list.map((f) => [+(f.t / 1000).toFixed(4), path.basename(f.file)])));
  const r = spawnSync(FFMPEG, ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-fps_mode', 'cfr', '-r', String(fps),
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '10', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', path.join(out, 'raw.mp4')], { stdio: 'inherit' });
  if (r.status !== 0) throw new Error('ffmpeg failed assembling the frames');
  console.log(`raw.mp4: ${list.length} frames over ${tEnd.toFixed(1)} s`);
  // the JPEGs are some 3 GB for five minutes; raw.mp4 at CRF 10 keeps what they show (SONGBIRD_KEEP_FRAMES=1 keeps them)
  if (!process.env.SONGBIRD_KEEP_FRAMES) fs.rmSync(path.join(out, 'frames-raw'), { recursive: true, force: true });
}
