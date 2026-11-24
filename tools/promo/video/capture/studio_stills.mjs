// The studio, photographed for s05_studio's wall of screens, opened on the stage version (its packed .flac, which
// carries its record, with render.json beside it), served on 127.0.0.1:8871 and shown in the light scheme at 2x on
// a 1600 x 900 CSS viewport (3200 x 1800 pixels). Two ways to open it (--studio):
//   local (the default): `songbird studio <flac>` from this checkout, the same pages as the web studio, opened on the
//     file as its parent. The deployed web build refuses this file: its reader takes a ritardando of 0 to 1 and the
//     stage record's is 1.5 (songbird/received.py, clean_params).
//   web: the deployed build (renders/studio-site, by serve_site.py), opening the file as a visitor does with
//     "Open someone's version": read in this browser, kept here, opened at /#version=<id>.
// Georgia is pinned by a style injected at capture time (the page's serif stack falls back to P052 here); the
// studio's files are untouched. Each view is a clean full-viewport PNG in renders/promo/video/scratch/s05/png/;
// prep with `--convert` writes the textures and index.json into renders/promo/video/studio/.
//
//   node tools/promo/video/capture/studio_stills.mjs            # serve, photograph, convert, stop the server
//   node tools/promo/video/capture/studio_stills.mjs --only time,notes
//   node tools/promo/video/capture/studio_stills.mjs --version path/to/version.flac --studio web
import { chromium } from 'playwright-core';
import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..');
const PNG = join(ROOT, 'renders/promo/video/scratch/s05/png');
const OUT = join(ROOT, 'renders/promo/video/studio');
const PORT = 8871;
const URL = `http://127.0.0.1:${PORT}`;
const W = 1600, H = 900, SCALE = 2;
const TEX_W = 2048;                       // the textures' width (the wall's screens), 16:9 but for the tall page

const args = process.argv.slice(2);
const only = args.includes('--only') ? args[args.indexOf('--only') + 1].split(',') : null;
const FLAC = resolve(ROOT, args.includes('--version') ? args[args.indexOf('--version') + 1] : 'renders/promo/capture-live-A/render.flac');
mkdirSync(PNG, { recursive: true });
mkdirSync(OUT, { recursive: true });

// which studio: `web`, the deployed build opening the file as a visitor does, or `local`, `songbird studio` opened on
// the file (its record beside it) as its parent, the same pages served by this checkout's program
const STUDIO = args.includes('--studio') ? args[args.indexOf('--studio') + 1] : 'local';
// Georgia pinned; and in the local studio the line naming where its exports go hidden (the web studio leaves it empty)
const PIN = ':root { --serif: Georgia, serif !important; }' + (STUDIO === 'web' ? '' : ' #toolsWhere { visibility: hidden; }');
const OUTDIR = join(ROOT, 'renders/promo/video/scratch/s05/studio-out');
mkdirSync(OUTDIR, { recursive: true });

const ABOUT = {};      // name -> what it shows
const server = STUDIO === 'web'
  ? spawn('uv', ['run', 'python', 'web/studio-wasm/tools/serve_site.py', 'renders/studio-site', '--port', String(PORT)],
    { cwd: ROOT, stdio: 'ignore' })
  : spawn('uv', ['run', 'songbird', 'studio', FLAC, '--song', 'performance/genome.json', '--machine', 'published',
    '--no-open', '--port', String(PORT), '--out', OUTDIR], { cwd: ROOT, stdio: ['ignore', 'inherit', 'inherit'] });
const stopServer = () => { try { server.kill('SIGTERM'); } catch { /* gone */ } };
process.on('exit', stopServer);
for (let i = 0; i < 1500; i++) {
  try { if ((await fetch(URL + '/')).ok) break; } catch { /* not yet */ }
  await new Promise((r) => setTimeout(r, 200));
}

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM || '/usr/bin/chromium', headless: true,
  args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required',
    '--force-color-profile=srgb', '--hide-scrollbars'],
});
const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: SCALE, colorScheme: 'light',
  bypassCSP: true, permissions: ['microphone'] });
const page = await context.newPage();
page.on('pageerror', (e) => console.log('pageerror', e.message));
page.on('console', (m) => { if (m.type() === 'error') console.log('console', m.text()); });
const wait = (ms) => page.waitForTimeout(ms);
const settle = async () => {
  await page.waitForFunction(() => typeof state !== 'undefined' && state.view && !state.busy, null, { timeout: 240000 });
  await wait(700);
};
const pin = async () => { await page.addStyleTag({ content: PIN }); await wait(200); };
const open = async (path) => { await page.goto('about:blank'); await page.goto(URL + path); await settle(); await pin(); };
const want = (name) => !only || only.includes(name);
const shot = async (name, about, opts = {}) => {
  await page.mouse.move(W - 2, H - 2);
  await wait(400);
  await page.screenshot({ path: join(PNG, `${name}.png`), ...opts });
  // the view's text, attributes and address, for the privacy check (hosts, user names, paths, emails)
  writeFileSync(join(PNG, `${name}.txt`), await page.evaluate(() => [location.href, document.body.innerText,
    ...[...document.querySelectorAll('[title],[aria-label],input,textarea')].map((e) => [e.title, e.getAttribute('aria-label'), e.value].filter(Boolean).join(' '))].join('\n')));
  ABOUT[name] = about;
  console.log('shot', name);
};
const tab = async (v) => { await page.click(`#tab-${v}`); await wait(1500); };
const key = async (k) => { await page.keyboard.press(k); await wait(500); };

// the stage version: the local studio opens on it; the web studio reads the file, keeps it in this browser and
// opens on it at /#version=<id>, as this browser's own version continuing it
let HOME = '/';
await open('/');
if (STUDIO === 'web') {
  await page.setInputFiles('#versionFile', FLAC);
  for (let i = 0; !/#version=[0-9a-f]{32}/.test(page.url()); i++) {
    const note = await page.evaluate(() => document.getElementById('versionNote')?.textContent || '').catch(() => '');
    if (/Couldn't|isn't|too large/.test(note) || i > 600) { console.error('the version did not open:', note); process.exit(2); }
    if (i % 20 === 0) console.log('opening:', note);
    await wait(1000);
  }
  HOME = '/' + new URL(page.url()).hash;
  await open(HOME);
}
console.log('opened', HOME);
if (want('page')) await shot('page', 'Page: the words of the stage version, the column of its choices');
if (want('page-verse2')) {
  await page.evaluate(() => {
    const sec = [...document.querySelectorAll('#page .sec')].find((s) => /Verse 2/i.test(s.querySelector('.rubric')?.textContent || ''));
    sec.scrollIntoView({ block: 'start' }); window.scrollBy(0, -250);
  });
  await shot('page-verse2', 'Page: verse 2, the words being sung');
  await page.evaluate(() => window.scrollTo(0, 0));
}
if (want('page-tall')) await shot('page-tall', 'Page: the whole page, top to foot, for scrolling', { fullPage: true });
if (want('export')) {
  await page.click('#recordNow'); await wait(900);
  await shot('export', 'Export menu: song file, share, MIDI, stems, piano page, draft');
  await key('Escape');
}
if (want('key')) {
  await page.click('#keyBtn'); await wait(900);
  await shot('key', 'the key and scale');
  await key('Escape');
}
if (want('tools')) {
  await page.click('#toolsBtn'); await wait(1200);
  await shot('tools', 'Tools: export and import');
  await key('Escape');
}
if (want('help')) {
  await page.click('#helpOpen'); await wait(1200);
  await shot('help', 'Help: the whole studio in plain words');
  await key('Escape');
}
if (want('arrange')) { await tab('arrange'); await shot('arrange', 'Arrange: the sections over bars, a row for each player'); }
if (want('arrange-section')) {
  await tab('arrange');
  await page.click('#grid [data-key="region:verse:1"]'); await settle();
  await shot('arrange-section', 'Arrange: verse 2 selected, the column says why it is so');
}
if (want('notes')) {
  await tab('arrange');
  await page.dblclick('#grid [data-key="region:verse:1"]'); await settle(); await wait(1500);
  await page.evaluate(() => { const n = document.getElementById('notes'); n.scrollIntoView({ block: 'start' }); window.scrollBy(0, -60); });
  await shot('notes', "Notes: verse 2's tune and chords, the line's melody");
  await key('Escape'); await key('Escape');
  await page.evaluate(() => window.scrollTo(0, 0));
}
if (want('cell')) {
  await tab('arrange');
  await page.evaluate(() => [...document.querySelectorAll('#grid .cell')].find((c) => /fiddle/i.test(c.getAttribute('aria-label') || ''))?.click());
  await settle();
  await shot('cell', 'Arrange: one player in one section, how hard it plays');
  await key('Escape');
}
if (want('mix')) { await tab('mix'); await shot('mix', 'Mix: a strip for each player, the voice and the room'); }
if (want('style')) {
  await key('Escape'); await key('Escape');
  await tab('page');
  await page.evaluate(() => [...document.querySelectorAll('#inspector button, #inspector [role=button]')].find((b) => /^Style/.test(b.textContent.trim()))?.click());
  await settle(); await wait(800);
  await shot('style', 'the column: Style, its choices and why the program chose it');
  await key('Escape');
}
if (want('singer')) {
  await tab('page');
  await page.evaluate(() => [...document.querySelectorAll('#inspector button, #inspector [role=button]')].find((b) => /^Singer/.test(b.textContent.trim()))?.click());
  await settle(); await wait(800);
  await shot('singer', 'the column: Singer, its choices');
  await key('Escape');
}
if (want('sing')) {
  await tab('sing');
  await shot('sing-offer', 'Sing: what is kept of your singing');
  await page.evaluate(() => {
    const c = document.getElementById('singConsent');
    if (c && !c.hidden) { document.getElementById('singAgree').click(); [...c.querySelectorAll('button')].find((x) => /Start/.test(x.textContent)).click(); }
  });
  try {
    await page.waitForFunction(() => !document.getElementById('singWork').hidden && !/Making/.test(document.getElementById('singStatus').textContent)
      && !document.getElementById('singRehearse').disabled, null, { timeout: 240000 });
    await wait(1500);
    await page.evaluate(() => document.getElementById('singRehearse').click());
    await wait(9000);
    await shot('sing', 'Sing: the lane, the guide playing');
  } catch (e) { console.log('sing lane not reached:', e.message.split('\n')[0]); }
}
if (want('piano')) {
  await tab('page');
  await page.click('#recordNow'); await wait(800);
  const popup = page.waitForEvent('popup', { timeout: 120000 }).catch(() => null);
  await page.evaluate(() => [...document.querySelectorAll('#exportPop button, #exportPop a')].find((b) => /Piano/.test(b.textContent))?.click());
  const p = await popup;
  if (p) {
    await p.waitForLoadState('load'); await p.waitForTimeout(4000);
    await p.addStyleTag({ content: PIN }); await p.waitForTimeout(500);
    await p.mouse.move(W - 2, H - 2);
    await p.screenshot({ path: join(PNG, 'piano.png') });
    writeFileSync(join(PNG, 'piano.txt'), await p.evaluate(() => location.href + '\n' + document.body.innerText));
    ABOUT.piano = 'the piano page: learn it on a keyboard';
    console.log('shot piano', p.url().replace(/\?.*/, ''));
    await p.close();
  } else console.log('piano page did not open');
  await key('Escape');
}

// the Time drawer, on this browser's version continuing the stage version (the web studio only: the local studio
// opened on a file as published has no other days or machines, so no Time)
if (STUDIO === 'web' && (want('time') || want('new'))) {
  await open(STUDIO === 'web' ? HOME : '/?new');
  if (want('new')) await shot('new', "Page: this browser's own version, the stage version's child");
  if (want('time')) {
    await page.click('#timeBtn');
    await page.waitForFunction(() => document.querySelector('#timeline')?.getBoundingClientRect().height > 50, null, { timeout: 120000 });
    await wait(5000);
    await shot('time', 'Time: the six-year timeline, other computers, someone\'s version');
    for (let i = 0; i < 5; i++) await page.evaluate(() => [...document.querySelectorAll('#drawer button')].find((b) => /^year\s*›/.test(b.textContent.trim()))?.click()), await settle();
    await wait(3000);
    await shot('time-later', 'Time: the song five years on');
  }
}

await browser.close();
stopServer();

// the privacy check: no view's text may name this computer, its user or a path on it (only the page's own address)
const PRIVATE = [/milo/i, /winningham/i, /\/home\//, /\/Users\//, /[\w.+-]+@[\w-]+\.[\w.]+/, new RegExp(`\\b${(await import('node:os')).hostname()}\\b`, 'i')];
for (const name of Object.keys(ABOUT)) {
  const f = join(PNG, `${name}.txt`);
  if (!existsSync(f)) continue;
  const text = (await (await import('node:fs/promises')).readFile(f, 'utf8')).split('\n').slice(1).join('\n');
  for (const re of PRIVATE) if (re.test(text)) { console.error(`PRIVATE: ${name} matches ${re}`); process.exitCode = 3; }
}

// textures: JPEG quality 92, 2048 wide (the tall page as tall as its width keeps, at most 8192)
const index = [];
const names = Object.keys(ABOUT);
for (const name of names) {
  const src = join(PNG, `${name}.png`);
  if (!existsSync(src)) continue;
  const dst = join(OUT, `${name}.jpg`);
  spawnSync('magick', [src, '-resize', `${TEX_W}x8192`, '-quality', '92', '-sampling-factor', '4:4:4', dst], { stdio: 'inherit' });
  const [w, h] = spawnSync('magick', ['identify', '-format', '%w %h', dst]).stdout.toString().split(' ').map(Number);
  index.push({ file: `${name}.jpg`, shows: ABOUT[name], width: w, height: h });
}
const prev = existsSync(join(OUT, 'index.json')) && only ? JSON.parse(await (await import('node:fs/promises')).readFile(join(OUT, 'index.json'), 'utf8')).images : [];
const merged = [...prev.filter((p) => !index.find((q) => q.file === p.file)), ...index];
writeFileSync(join(OUT, 'index.json'), JSON.stringify({
  about: `The studio (${STUDIO === 'web' ? 'renders/studio-site, the deployed web build' : 'songbird studio from this checkout, the same pages as the web studio'}) opened on the stage version, ${FLAC.slice(ROOT.length + 1)}, light scheme, a 1600 x 900 CSS viewport at 2x, Georgia pinned; by tools/promo/video/capture/studio_stills.mjs. Each image is a JPEG (quality 92) 2048 wide.`,
  images: merged,
}, null, 1));
console.log(`${merged.length} images in ${OUT}`);
