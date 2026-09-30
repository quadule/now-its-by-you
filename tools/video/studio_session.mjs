// A recorded studio session, driven as a person would: clicks, typing, drags, with a visible cursor and
// a log of every action's moment in the raw footage. Used for the EDM test (docs/STUDIO-EDM-TEST.md), on the page
// before the redesign, which the studio keeps at /classic; the second attempt, on the score, is edm2_session.mjs
// (with kit.mjs: sharper capture, captions, native selects drawn).
//
//   node tools/video/studio_session.mjs --url http://127.0.0.1:8791/classic --out renders/video [--no-video] [--script edm]
//
// Needs Node >= 22 and the playwright package (npm i playwright; npx playwright install chromium): run it from a
// folder where playwright is installed, or with NODE_PATH pointing at one. Writes <out>/raw.webm, <out>/actions.json
// (every action: t in seconds of the raw video, kind, label, phase, weight 1-3, hold in beats) and any downloads.
//
// The log's clock is the video's: a white flash is drawn at t0 (kind "sync") so tools/video/beatcut.py can find the
// offset between the log and the footage to the frame.
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const arg = (name, dflt) => { const i = process.argv.indexOf('--' + name); return i > 0 ? process.argv[i + 1] : dflt; };
const URL = arg('url', 'http://127.0.0.1:8791/classic');
const OUT = path.resolve(arg('out', 'renders/video'));
const VIDEO = !process.argv.includes('--no-video');
const SKIP_RECORD = process.argv.includes('--skip-record');
fs.mkdirSync(OUT, { recursive: true });

const W = 1920, H = 1080;
const browser = await chromium.launch({ headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
const ctx = await browser.newContext({
  viewport: { width: W, height: H }, colorScheme: 'dark', acceptDownloads: true,
  ...(VIDEO ? { recordVideo: { dir: path.join(OUT, 'raw-tmp'), size: { width: W, height: H } } } : {}),
});
// the cursor and the caption, drawn in the page so they are in the footage
await ctx.addInitScript(() => {
  const install = () => {
    if (document.getElementById('pw-cursor')) return;
    const c = document.createElement('div');
    c.id = 'pw-cursor';
    c.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M3 2 L3 22 L8.5 17 L12.5 26 L16 24.5 L12 15.8 L19.5 15.8 Z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: 'fixed', left: '0px', top: '0px', zIndex: 2147483647, pointerEvents: 'none',
      transform: 'translate(-3px,-2px)', filter: 'drop-shadow(0 1px 2px rgba(0,0,0,.5))' });
    document.documentElement.appendChild(c);
    const cap = document.createElement('div');
    cap.id = 'pw-caption';
    Object.assign(cap.style, { position: 'fixed', left: '34px', top: '440px', width: '200px', zIndex: 2147483646,
      pointerEvents: 'none', fontFamily: 'var(--serif)', color: 'var(--ink)', opacity: '0', transition: 'opacity .35s' });
    document.documentElement.appendChild(cap);
    window.addEventListener('mousemove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    window.addEventListener('mousedown', (e) => {
      const r = document.createElement('div');
      Object.assign(r.style, { position: 'fixed', left: e.clientX - 18 + 'px', top: e.clientY - 18 + 'px', width: '36px', height: '36px',
        borderRadius: '50%', border: '3px solid #e0664d', zIndex: 2147483646, pointerEvents: 'none', transition: 'all .45s ease-out', opacity: '1' });
      document.documentElement.appendChild(r);
      requestAnimationFrame(() => { r.style.transform = 'scale(1.8)'; r.style.opacity = '0'; });
      setTimeout(() => r.remove(), 600);
    }, true);
  };
  window.__toasts = [];
  new MutationObserver(() => {
    for (const el of document.querySelectorAll('[role=alert], [role=status]')) {
      const t = el.innerText.trim();
      if (t && window.__toasts[window.__toasts.length - 1] !== t) window.__toasts.push(t);
    }
  }).observe(document, { subtree: true, childList: true, characterData: true });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install); else install();
});

const page = await ctx.newPage();
const T0 = Date.now();
const log = [];
let phase = 'open';
const now = () => (Date.now() - T0) / 1000;
function mark(kind, label, o = {}) {
  const e = { t: +now().toFixed(3), kind, label, phase, weight: 1, hold: 2, ...o };
  log.push(e);
  console.log(e.t.toFixed(2).padStart(8), phase.padEnd(10), kind.padEnd(7), label);
  fs.writeFileSync(path.join(OUT, 'actions.json'), JSON.stringify({ t0: T0, url: URL, viewport: [W, H], actions: log }, null, 1));
  return e;
}
const pause = (ms) => page.waitForTimeout(ms);

// --- the hand: glide, click, type ------------------------------------------------------------------------
let mx = W / 2, my = H / 2;
async function glide(x, y, ms = 420) {
  const n = Math.max(8, Math.round(ms / 16)), x0 = mx, y0 = my;
  for (let k = 1; k <= n; k++) {
    const u = k / n, e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
    await page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e);
    await pause(16);
  }
  mx = x; my = y;
}
async function show(loc) {
  await loc.waitFor({ state: 'visible', timeout: 60000 });
  const inView = await loc.evaluate((el) => { const r = el.getBoundingClientRect(); return r.top >= 70 && r.bottom <= innerHeight - 90; });
  if (!inView) {
    await loc.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
    await pause(750);
  }
  return loc.boundingBox();
}
async function over(loc, fx = 0.5, fy = 0.5) {
  const b = await show(loc);
  await glide(b.x + b.width * fx, b.y + b.height * fy);
  return b;
}
async function click(loc, label, o = {}) {
  await over(loc, o.fx ?? 0.5, o.fy ?? 0.5);
  await pause(120);
  mark(o.kind || 'click', label, o);
  await page.mouse.down(); await pause(60); await page.mouse.up();
  await pause(o.after ?? 450);
}
async function choose(loc, value, label, o = {}) {  // a native select: point at it, then the value changes
  await over(loc, 0.8, 0.5);
  await pause(150);
  mark('select', label, o);
  await page.mouse.down(); await page.mouse.up();
  await loc.selectOption(value);
  await page.keyboard.press('Escape').catch(() => {});
  await pause(o.after ?? 900);
}
async function type(loc, text, label, o = {}) {
  await over(loc, 0.3, 0.5);
  await page.mouse.down(); await page.mouse.up();
  await page.keyboard.press('Meta+A');
  const e = mark('type', label, { hold: 3, ...o });
  await page.keyboard.type(text, { delay: o.delay ?? 38 });
  e.dur = +(now() - e.t).toFixed(3);
  await pause(o.after ?? 350);
}
async function slide(loc, value, label, o = {}) {  // drag a range input's thumb to a value
  const b = await show(loc);
  const [mn, mxv, v0] = await loc.evaluate((el) => [+el.min, +el.max, +el.value]);
  const pad = 8, xOf = (v) => b.x + pad + (b.width - 2 * pad) * (v - mn) / (mxv - mn);
  await glide(xOf(v0), b.y + b.height / 2);
  await page.mouse.down();
  await glide(xOf(value), b.y + b.height / 2, 520);
  mark('slider', label, o);
  await page.mouse.up();
  await pause(o.after ?? 700);
}
async function dragTo(from, x, y, label, o = {}) {
  const b = await over(from, o.fx ?? 0.5, 0.5);
  await page.mouse.down();
  await glide(x, y, o.ms ?? 650);
  mark('drag', label, o);
  await page.mouse.up();
  await pause(o.after ?? 1200);
}
async function caption(kicker, text) {
  await page.evaluate(([k, t]) => {
    const c = document.getElementById('pw-caption'); if (!c) return;
    c.style.opacity = '0';
    setTimeout(() => {
      c.innerHTML = `<div style="font-variant:small-caps;letter-spacing:.14em;text-transform:lowercase;color:var(--red);font-size:18px;border-bottom:1px solid var(--red-rule);padding-bottom:6px;margin-bottom:8px">${k}</div><div style="font-size:26px;line-height:1.2">${t}</div>`;
      c.style.opacity = '1';
    }, 380);
  }, [kicker, text]);
}
function setPhase(p, kicker, text) { phase = p; mark('phase', text || p, { weight: 0 }); return caption(kicker, text); }

// --- waiting on the studio ----------------------------------------------------------------------------------
async function audioPlaying(timeout = 180000) {
  const t = Date.now();
  while (Date.now() - t < timeout) {
    const ok = await page.evaluate(() => [...document.querySelectorAll('audio')].some((a) => !a.paused && a.currentTime > 0.05));
    if (ok) return true;
    await pause(150);
  }
  return false;
}
async function listen(button, label, seconds, o = {}) {
  await page.evaluate(() => document.querySelectorAll('audio').forEach((a) => a.pause()));
  await click(button, label, { kind: 'play', weight: 2, hold: 4, ...o, after: 100 });
  const tw = now();
  if (await audioPlaying()) mark('hear', label + ' (sounding)', { weight: o.weight ?? 2, hold: 4, waited: +(now() - tw).toFixed(2) });
  await pause(seconds * 1000);
  await click($('#playPause'), 'pause', { weight: 1, hold: 1, after: 300 });
}
async function sketch(label, seconds, o = {}) {  // the page's own Web Audio sketch: no render, heard at once
  await click(byRole('button', '▶ Play sketch'), label, { kind: 'play', weight: 2, hold: 4, ...o, after: 100 });
  mark('hear', label + ' (sounding)', { weight: o.weight ?? 2, hold: 4 });
  await pause(seconds * 1000);
  const stop = byRole('button', '■ Stop sketch');
  if (await stop.isVisible().catch(() => false)) await click(stop, 'stop the sketch', { hold: 1, after: 300 });
}
const $ = (sel) => page.locator(sel).first();
const byRole = (role, name, exact = false) => page.getByRole(role, { name, exact }).first();
const card = (name) => page.getByRole('button', { name: new RegExp('^\\d+\\. ' + name + ',') }).first();
const phraseTab = (k) => page.getByRole('button', { name: new RegExp('^Phrase ' + k + '\\b') }).first();
const laneChord = (bar, slot = 0) => page.locator(`button[aria-label^="Bar ${bar}, chord"]`).nth(slot);
const inKey = (name) => page.getByRole('group', { name: 'Chords in the key' }).getByRole('button', { name, exact: true });
async function barSlots(bar) { return page.locator(`button[aria-label^="Bar ${bar}, chord"]`).count(); }
async function setChords(bar, names) {  // one bar's chords, from the lane and the chord card, as a person would
  await click(laneChord(bar, 0), `bar ${bar}: open the chord`, { after: 600 });
  if ((await barSlots(bar)) !== names.length) {
    await choose($('#sbc-chord-count'), String(names.length), `bar ${bar}: ${names.length} chord(s) in the bar`, { after: 900 });
  }
  for (let s = 0; s < names.length; s++) {
    if (s > 0) await click(laneChord(bar, s), `bar ${bar}: chord ${s + 1}`, { after: 500 });
    const [name, quality] = names[s].split(':');
    await click(inKey(name), `bar ${bar}: ${name}`, { weight: 2, hold: 2, after: 800 });
    if (quality) await choose($('#sbc-chord-quality'), { label: quality }, `bar ${bar}: ${name}${quality}`, { weight: 2, after: 900 });
  }
}
async function noteTo(index, degree, label, o = {}) {  // drag a note of the open phrase to a scale degree's row
  const note = page.locator('.sbc-note').nth(index);
  const key = page.locator(`button[aria-label$="scale degree ${degree}"]`).first();
  await show(note);
  const kb = await key.boundingBox(), nb = await note.boundingBox();
  await dragTo(note, nb.x + Math.min(24, nb.width / 3) + (o.dx || 0), kb.y + kb.height / 2, label, { fx: Math.min(24, nb.width / 3) / nb.width, weight: 2, ...o });
}

// ============================================================================================================
// the session
// ============================================================================================================
await page.goto(URL);
await pause(1200);
// sync flash: the log's t is the footage's t once this frame is found
await page.evaluate(() => {
  const f = document.createElement('div');
  Object.assign(f.style, { position: 'fixed', inset: '0', background: '#fff', zIndex: 2147483647 });
  document.documentElement.appendChild(f);
  setTimeout(() => f.remove(), 240);
});
mark('sync', 'white flash', { weight: 0 });
await pause(900);

// 1. open, the tour skipped, the song as it is
await setPhase('open', 'the song today', 'a folk song, as the machine sings it');
const skip = page.getByRole('button', { name: 'Skip' });
if (await skip.isVisible().catch(() => false)) await click(skip, 'skip the tour');
await listen(byRole('button', 'Play Refrain 1'), 'hear refrain 1 as it is (the ballad)', 7, { weight: 3 });

// 2. tempo and mode
await setPhase('tempo', 'tempo', 'up to dance speed');
const tempo = page.getByLabel('Tempo in beats per minute');
await type(tempo, '128', 'tempo 128', { delay: 120 });
await page.keyboard.press('Enter');
mark('refused', 'the studio refuses: 72 to 124.8 BPM', { weight: 2, hold: 4 });
await pause(2600);
await type(tempo, '124.8', 'tempo 124.8, the ceiling', { delay: 120, weight: 2 });
await page.keyboard.press('Enter');
await pause(1200);
await setPhase('mode', 'key', 'D minor');
await choose(page.getByLabel('Scale', { exact: true }), { label: 'minor' }, 'scale: minor', { weight: 2 });

// 3. the sound: the most electronic band there is
await setPhase('sound', 'style', 'synth folk, the most electronic style');
await click(byRole('tab', 'Sound'), 'Sound area');
await choose($('select[aria-label="The style"]'), { label: 'synth folk' }, 'style: synth folk', { weight: 3, hold: 4, after: 2200 });
await setPhase('band', 'the band', 'no guitar; drums, bass and arp up');
await click(byRole('button', 'Mute guitar'), 'mute the acoustic guitar', { weight: 2 });
await slide(page.getByLabel('drum machine level'), 1.7, 'drum machine 170%');
await slide(page.getByLabel('synth bass level'), 1.5, 'synth bass 150%');
await slide(page.getByLabel('arpeggiated synth level'), 1.1, 'arp 110%');
await slide(page.getByLabel('How busy'), 0.85, 'busier');
await slide(page.getByLabel('How bright'), 0.85, 'brighter');
await setPhase('mix', 'the room', 'dry and wide; the voice in the mix');
await slide(page.getByLabel('How much of the room'), 0.25, 'drier room');
await slide(page.getByLabel('The voice over the band'), 6.5, 'voice among the band');
await choose($('select[aria-label="How it ends"]'), { label: 'it stops dead' }, 'ending: stops dead');
await choose($('select[aria-label="Backing voices"]'), { label: 'backing voices echo the lines' }, 'backing voices echo the lines');
await choose($('select[aria-label="The last refrain"]'), { label: 'a whole step up' }, 'last refrain a whole step up', { weight: 2 });
await setPhase('shape', 'shape', 'no turns; an outro; the bridge twice');
const shape = page.locator('section[aria-label="Shape"]');
await click(shape.getByRole('button', { name: 'a turn after the refrains' }), 'no turns', { after: 1200 });
await click(shape.getByRole('button', { name: 'an outro' }), 'an outro', { after: 1200 });
await click(shape.getByRole('button', { name: 'the bridge twice' }), 'the bridge twice', { weight: 2, after: 1500 });

// 4. hear it
await setPhase('hear1', 'listen', 'the refrain, electronic');
await click(byRole('tab', 'Tune'), 'Tune area');
await click(card('Refrain 1'), 'select refrain 1');
await listen(byRole('button', 'Hear sung section'), 'hear refrain 1, synth folk at 124.8', 8, { weight: 3 });

// 5. the form: a breakdown and a build before the drop
await setPhase('form', 'arrangement', 'break and bridge before the drop');
async function move(from, to, label) {
  const b = await show(card(to));
  await dragTo(card(from), b.x + b.width * 0.3, b.y + b.height / 2, label, { weight: 2, ms: 900, after: 1500 });
}
await move('Break', 'Verse 2', 'drag the break before verse 2');
await move('Bridge', 'Verse 2', 'drag the bridge before verse 2');
await move('Refrain 2', 'Verse 2', 'drag refrain 2 before verse 2 (the drop)');

// 6. new chords: i VI III VII
await setPhase('chords', 'chords', 'Dm · B♭ · F · C');
await click(card('Refrain 1'), 'select refrain 1');
await click(phraseTab(1), 'phrase 1: Who made this song?');
await setChords(1, ['B♭']);
await setChords(2, ['F']);
await click(phraseTab(2), 'phrase 2');
await setChords(1, ['C:sus4']);
await setChords(2, ['Dm']);
await click(phraseTab(3), 'phrase 3');
await setChords(1, ['B♭']);
await setChords(2, ['F', 'C']);
await choose($('#sbc-play-scope'), 'section', 'sketch: this section');
await sketch('play sketch: the new chords', 8, { weight: 3 });
await click(card('Verse 1'), 'select verse 1');
await click(phraseTab(1), 'verse phrase 1');
await setChords(2, ['B♭', 'C']);

// 7. the tune
await setPhase('tune', 'melody', 'a new verse line, a higher refrain');
await click(byRole('button', '↑ Step', true), 'verse phrase 1: a step up', { weight: 2, after: 1200 });
await noteTo(4, 8, 'verse: "num-" up to the octave');
await click(phraseTab(3), 'verse phrase 3');
await click(byRole('button', '↓ Step', true), 'verse phrase 3: a step down', { weight: 2, after: 1200 });
await click(card('Refrain 1'), 'select refrain 1');
await click(phraseTab(3), 'refrain phrase 3');
await noteTo(1, 8, 'refrain: "no-" up to the octave');
await noteTo(4, 8, 'refrain: "mak-" up to the octave');
await click(phraseTab(2), 'refrain phrase 2');
await click(byRole('button', '↑ Step', true), 'refrain phrase 2: a step up', { weight: 2, after: 1200 });
await sketch('play sketch: new tune over new chords', 8, { weight: 2 });

// 8. the words
await setPhase('words', 'words', 'a sample, a club, a drop');
await click(byRole('tab', 'Words'), 'Words area');
await choose($('select[aria-label="Verse 1: verse"]'), 'sample', 'verse 1: "A girl put a piece of it under a beat"', { weight: 3, hold: 4, after: 1800 });
await choose($('select[aria-label="Refrain 1: question"]'), 'made', 'refrain 1: "Who made this song?"', { weight: 2 });
async function author(sec, lines, label) {
  const d = page.locator(`details.lyric-author[data-author-section="${sec}"]`);
  if ((await d.getAttribute('open')) === null) await click(d.locator('summary'), `${label}: write your own lines`, { after: 600 });
  const ta = d.locator('textarea');
  for (let k = 0; k < lines.length; k++) if (lines[k]) await type(ta.nth(k), lines[k], `${label} line ${k + 1}: ${lines[k]}`);
  await click(d.getByRole('button', { name: 'Use these lines' }), `${label}: use these lines`, { weight: 2, hold: 3, after: 2200 });
}
await author('refrain:0', [null, "It's ours on the floor now, so turn it loud.", 'The bass is a heart-beat that no-bo-dy wrote;',
  "we dance to it now, and to-night it's by you."], 'refrain 1');
await setPhase('words2', 'your own lines', 'verse 2, written here');
await author('verse:1', ['A kid in a club heard it un-der the lights,', 'a sam-ple of some-bo-dy sing-ing at night;',
  'she looped it and pitched it and gave it a drop,', 'and nine hun-dred peo-ple would not let it stop.'], 'verse 2');
await author('refrain:1', [null, 'it came through the speak-ers, and still it grows.', "It's no-bo-dy's rec-ord and no-bo-dy's crew,",
  'no mon-ey for spin-ning it; spin it right through.'], 'refrain 2');
await choose($('select[aria-label="Bridge: ember"]'), 'spark', 'bridge: "like a spark from the fire"');
await setPhase('hear2', 'listen', 'the new words, sung');
await listen(byRole('button', 'Play Verse 2'), 'hear verse 2 sung, the new lines', 9, { weight: 3 });

// 9. record it
await setPhase('record', 'record', 'one file: the song and its program');
await click($('#recordNow'), 'Record it', { kind: 'record', weight: 3, hold: 4, after: 400 });
if (!SKIP_RECORD) {
  const saved = page.locator('#saved');
  await saved.getByText(/^Saved /).waitFor({ timeout: 900000 });
  await saved.scrollIntoViewIfNeeded();
  mark('saved', (await saved.innerText()).split('\n')[0], { weight: 3, hold: 4 });
  await pause(2500);
  await listen(saved.getByRole('button', { name: 'Play the recording' }), 'play the recording', 6, { weight: 3 });
  // take it into your own tools
  const dl = page.waitForEvent('download', { timeout: 120000 });
  await click($('#exportMidi'), 'Download MIDI', { weight: 2 });
  const midi = await dl;
  await midi.saveAs(path.join(OUT, 'edm.mid'));
  mark('download', 'MIDI saved', { weight: 1 });
  await pause(2000);
  if (process.argv.includes('--stems')) {
    const dl2 = page.waitForEvent('download', { timeout: 900000 });
    await click($('#exportStems'), 'Download the parts (stems)', { weight: 1 });
    const stems = await dl2;
    await stems.saveAs(path.join(OUT, 'edm-stems.zip'));
    mark('download', 'stems saved', { weight: 0 });
  }
}
fs.writeFileSync(path.join(OUT, 'page-state.json'), JSON.stringify(await page.evaluate(() => ({
  toasts: window.__toasts || [], storage: Object.fromEntries(Object.keys(localStorage).map((k) => [k, localStorage.getItem(k)])) })), null, 1));
mark('end', 'end', { weight: 0 });
await ctx.close();
if (VIDEO) {
  const v = await page.video().path();
  fs.renameSync(v, path.join(OUT, 'raw.webm'));
  fs.rmSync(path.join(OUT, 'raw-tmp'), { recursive: true, force: true });
}
await browser.close();
console.log('done', OUT);
