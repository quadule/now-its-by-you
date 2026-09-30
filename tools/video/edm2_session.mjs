// The second EDM version, made only through the studio's page (the score: Page · Arrange · Mix, one inspector,
// Tools), filmed: docs/STUDIO-EDM-TEST.md, "Second attempt (2026-09-30)". The first attempt's session, on the
// page before (now at /classic), is tools/video/studio_session.mjs.
//
//   uv run songbird studio --no-open --port 8851 --machine fictional:vela
//   node tools/video/edm2_session.mjs --url http://127.0.0.1:8851/ --out renders/video [--no-video] [--until PHASE]
//     [--skip-record] [--no-wait]
//
// --no-wait: the hand doesn't wait for the page's answer to an edit before reaching for the next control, nor follow
// one that moved (it says so): a quick person. The page keeps its controls still and each click builds on the last,
// so the session runs the same either way (the first filmed takes lost their snare rolls before it did).
//
// Needs Node >= 22 and playwright (npm i playwright; npx playwright install chromium) where Node resolves it from
// this file (a node_modules beside or above it). Writes <out>/raw.mp4 (tools/video/kit.mjs), <out>/actions.json
// and the MIDI file (<out>/edm2.mid); the recording lands in the studio's renders/ as always.
//
// The phases follow the song, so the cut can put each on the section it made (tools/video/beatcut.py --phases):
// the style, tempo, key and shape over the intro; verse 1's new words over verse 1; the refrain's words and its
// build over refrain 1; the drop's arrangement and sound over the drop; verse 2's words over the breakdown; the
// breakdown, the second build and a lock over the bridge; chords and tune over the second drop; the record at the end.
import { session } from './kit.mjs';
import path from 'node:path';

const arg = (name, dflt) => { const i = process.argv.indexOf('--' + name); return i > 0 ? process.argv[i + 1] : dflt; };
const URL = arg('url', 'http://127.0.0.1:8851/');
const OUT = path.resolve(arg('out', 'renders/video'));
const UNTIL = arg('until', null);
const VIDEO = !process.argv.includes('--no-video');
const SKIP_RECORD = process.argv.includes('--skip-record');
const WAIT = !process.argv.includes('--no-wait');

const s = await session({ url: URL, out: OUT, video: VIDEO, zoom: 1.2, avoid: '#page', wait: WAIT });
const { page, pause, mark, click, dbl, choose, type, dragTo, show } = s;
const byRole = (role, name, exact = false) => page.getByRole(role, { name, exact }).first();
const insp = () => page.getByRole('complementary').first();
const chip = (group, name) => insp().getByRole('group', { name: group, exact: true }).getByRole('button', { name, exact: true });
const region = (label) => page.getByRole('button', { name: new RegExp(`^${label}, \\d+ bars`) }).first();
const cell = (player, section) => page.locator(`[role=gridcell][aria-label^="${player} in ${section}:"]`).first();
const seam = (section) => page.getByRole('button', { name: new RegExp(`^The seam into ${section}:`) }).first();
const track = (player) => page.locator('[role=rowheader]').filter({ hasText: player }).getByRole('button').first();
const notes = () => page.getByRole('region', { name: 'The notes of the open section' });
const phraseTab = (k) => notes().getByRole('button', { name: new RegExp(`^Phrase ${k} `) }).first();
const laneChord = (bar, slot = 0) => notes().locator(`button[aria-label^="Bar ${bar}, chord"]`).nth(slot);
const note = (syllable, nth = 0) => notes().locator(`button[aria-label^="${syllable}, "]`).nth(nth);
const view = (name) => byRole('tab', name, true);
async function until(p) {
  if (UNTIL !== p) return;
  console.log('stopping before', p);
  await page.screenshot({ path: path.join(OUT, 'until.png') });
  console.log(JSON.stringify(await page.evaluate(() => ({
    regions: [...document.querySelectorAll('.region')].map((r) => r.getAttribute('aria-label')),
    toasts: window.__toasts, choices: document.body.innerText.match(/\d+ choices? (is|are) yours[^\n]*/)?.[0] })), null, 1));
  await s.finish(); process.exit(0);
}
async function phase(p, kicker, text, where) { await until(p); await s.setPhase(p, kicker, text, where); }

async function toView(name) {
  if ((await view(name).getAttribute('aria-selected')) !== 'true') await click(view(name), `the ${name} view`, { after: 900 });
  await page.evaluate(() => scrollTo({ top: 0, behavior: 'smooth' })); await pause(400);
}
async function audioPlaying(timeout = 240000) {
  const t = Date.now();
  while (Date.now() - t < timeout) {
    if (await page.evaluate(() => { const a = document.getElementById('audio'); return a && !a.paused && a.currentTime > 0.05; })) return true;
    await pause(150);
  }
  return false;
}
async function hearSung(label, seconds, o = {}) {  // the selection, sung: made (a wait), then heard
  if ((await byRole('button', 'Sung', true).getAttribute('aria-pressed')) !== 'true') await click(byRole('button', 'Sung', true), 'Sung, not the sketch', { after: 300 });
  await click(page.locator('#tPlay'), label, { kind: 'play', weight: 2, hold: 4, ...o, after: 100 });
  const tw = s.now();
  if (await audioPlaying()) mark('hear', `${label} (sounding)`, { weight: o.weight ?? 2, hold: 4, waited: +(s.now() - tw).toFixed(2) });
  await pause(seconds * 1000);
  await click(page.locator('#tPlay'), 'stop', { weight: 1, hold: 1, after: 300 });
}
async function sketch(label, seconds, o = {}) {  // the page's own sketch: at once
  if ((await byRole('button', 'Sketch', true).getAttribute('aria-pressed')) !== 'true') await click(byRole('button', 'Sketch', true), 'the sketch', { after: 300 });
  await click(page.locator('#tPlay'), label, { kind: 'play', weight: 2, hold: 4, ...o, after: 100 });
  mark('hear', `${label} (sounding)`, { weight: o.weight ?? 2, hold: 4 });
  await pause(seconds * 1000);
  await click(page.locator('#tPlay'), 'stop', { weight: 1, hold: 1, after: 300 });
}
// a section's words, written in the column a line at a time, each used as it's written (the column moves on)
async function writeLines(section, lines, label) {
  await toView('Page');
  await click(page.getByRole('tabpanel', { name: 'Page' }).getByRole('button', { name: section, exact: true }), `${section}: select it`, { after: 600 });
  await click(byRole('button', 'Edit its words', true), `${section}: edit its words`, { after: 900 });
  for (const [k, text] of lines) {
    if ((await chip('Line', String(k)).getAttribute('aria-pressed')) !== 'true') await click(chip('Line', String(k)), `${section} line ${k}`, { after: 350 });
    await type(insp().getByRole('textbox'), text, `${label} line ${k}: ${text.replace(/-/g, '').replace(/\*/g, '')}`, { weight: 2 });
    const status = insp().locator('.author-status');
    await click(insp().getByRole('button', { name: 'Use this line', exact: true }), `${section} line ${k}: use it`, { weight: 1, hold: 2, after: 300 });
    await page.waitForFunction(() => !/Checking|Waiting/.test(document.querySelector('#inspector .author-status')?.textContent || ''), null, { timeout: 30000 });
    const said = await status.innerText().catch(() => '');
    if (/Line \d+:|isn't|can't|doesn't|needs|changed while/i.test(said)) { console.log('REFUSED', said); throw new Error(`${section} line ${k}: refused: ${said}`); }
    await pause(900);
  }
}
async function openNotes(section) {
  await toView('Arrange');
  await click(region(section), `${section}: select`, { after: 500 });
  if (!(await notes().isVisible().catch(() => false)) || !(await notes().innerText()).startsWith(section))
    await click(byRole('button', 'Edit its notes', true), `${section}: edit its notes`, { after: 1500 });
  await show(notes().locator('.sbc-roll-scroll, [class*=roll]').first(), { block: 'start', bottom: 60 }).catch(() => {});
}
async function setChord(bar, slot, name, o = {}) {  // a chord in the lane, then a one-press chord from the key's
  await click(laneChord(bar, slot), `bar ${bar}: chord ${slot + 1}`, { after: 600 });
  const seventh = insp().getByRole('group', { name: 'Seventh chords in the key' }).getByRole('button', { name, exact: true });
  const triad = insp().getByRole('group', { name: 'Chords in the key' }).getByRole('button', { name, exact: true });
  await click((await seventh.count()) ? seventh : triad, `bar ${bar}: ${name}`, { weight: 2, after: 900, ...o });
}
async function chordsInBar(bar, n) {
  await click(laneChord(bar, 0), `bar ${bar}: its chords`, { after: 600 });
  await choose(insp().getByRole('combobox', { name: 'Chords in this bar' }), String(n), `bar ${bar}: ${n} chord${n > 1 ? 's' : ''} in the bar`, { after: 1100 });
}
async function noteTo(syllable, nth, noteName, label, o = {}) {  // drag a note of the open phrase to a pitch's row
  const n = note(syllable, nth);
  const key = notes().locator(`button[aria-label^="Hear ${noteName},"]`).first();
  await show(n, { bottom: 60 });
  const kb = await key.boundingBox(), nb = await n.boundingBox();
  const fx = Math.min(22, nb.width / 3) / nb.width;
  await dragTo(n, nb.x + nb.width * fx, kb.y + kb.height / 2, label, { fx, weight: 2, bottom: 60, ...o });
}

// ============================================================================================================
await page.goto(URL);
await pause(1500);
await s.flash();

// ---- the intro: the song today, then synth folk at 128 in C sharp minor, and its shape
await phase('open', 'songbird · studio', 'The song today, as a made-up machine sings it');
const skip = page.getByRole('button', { name: 'Skip' });
if (await skip.isVisible().catch(() => false)) await click(skip, 'skip the tour', { weight: 1 });
await pause(600);

await phase('style', 'the style', 'Synth folk: the most electronic band the studio has');
await click(byRole('button', /^The style /), 'the style', { after: 800 });
await choose(insp().getByRole('combobox', { name: 'The style' }), { label: 'synth folk' }, 'style: synth folk', { weight: 3, hold: 3, after: 2500 });
await click(byRole('button', /^Tempo /), 'the tempo', { after: 600 });
await type(page.locator('#tempoNumber'), '128', 'tempo 128', { delay: 140, weight: 2 });
await page.keyboard.press('Enter');
mark('click', 'tempo 128: this style goes to 134', { weight: 2, hold: 3 });
await pause(2000);
await page.keyboard.press('Escape');
await click(byRole('button', /^Key: /), 'the key', { after: 600 });
await click(page.getByRole('group', { name: 'Scale' }).getByRole('button', { name: 'minor', exact: true }), 'C sharp minor', { weight: 2, after: 1600 });
await page.keyboard.press('Escape');

await phase('shape', 'the shape', 'Two verses, an intro and an outro, no turns');
if (!(await byRole('button', /^The shape /).isVisible().catch(() => false))) await click(insp().getByRole('button', { name: 'Close (Esc)' }), 'back to the song', { after: 700 });
await click(byRole('button', /^The shape /), 'the shape', { after: 700 });
await click(chip('Verses', '2'), 'two verses', { after: 1400 });
await click(insp().getByRole('button', { name: 'an intro', exact: true }), 'an intro', { after: 1400 });
await click(insp().getByRole('button', { name: 'a turn after the refrains' }), 'no turns', { after: 1400 });
await click(insp().getByRole('button', { name: 'an outro', exact: true }), 'an outro', { weight: 2, after: 1600 });
await toView('Arrange');
{ // the second verse dropped on the second refrain: it goes after it, a drop before the breakdown
  const to = await show(region('Refrain 2'));
  await dragTo(region('Verse 2'), to.x + to.width * 0.3, to.y + to.height / 2, 'drag verse 2 after refrain 2', { weight: 3, ms: 1000, after: 2000 });
}
{ // the intro twice as long, by the middle of its edge (a handle of its own now, clear of the next seam); the outro
  // from the column
  const edge = page.locator('[data-region="intro:0"] .edge').first();
  const r = await show(region('Intro'));
  const e = await edge.boundingBox();
  await dragTo(edge, r.x + r.width * 2, e.y + e.height / 2, 'the intro: drag its edge to 8 bars', { weight: 2, ms: 800, after: 1800 });
  const bars = await region('Intro').getAttribute('aria-label');
  if (!/^Intro, 8 bars/.test(bars)) throw new Error(`the intro's edge: ${bars}`);
  await click(region('Outro'), 'the outro: select', { after: 600 });
  await click(chip('Length', '8 bars'), 'the outro: 8 bars', { weight: 2, after: 1600 });
}

// ---- verse 1: new words
await phase('verse1', 'verse 1 · your own lines', 'New words, typed in the column: the tune checks every syllable', 'left');
await writeLines('Verse 1', [
  [1, 'The lights on the *ceil-ing* went blue in the smoke,'],
  [2, 'a hum in the floor-boards be-fore some-one spoke;'],
  [3, 'a girl at the decks found a *tune* in a file,'],
  [4, 'and played it to strang-ers who stayed for a *while*.'],
], 'verse 1');

// ---- refrain 1: the hook kept, three new lines, and a build
await phase('refrain1', 'refrain 1 · the build', '“Who made this song? Nobody knows.” kept; three new lines');
await writeLines('Refrain 1', [
  [2, "It's *down* in the bass now, and up it goes."],
  [3, 'so turn up the speak-ers and let it come *through*,'],
  [4, "and dance till the *morn-ing*, and now it's by you."],
], 'refrain 1');
await toView('Arrange');
await click(region('Refrain 1'), 'refrain 1: select', { after: 600 });
await click(chip('Moment', 'a build'), 'refrain 1: a build', { weight: 3, after: 1800 });

// ---- the drop: refrain 2 played, sixteen bars, a riser, a roll and an impact into it; then its sound
await phase('drop', 'the drop · refrain 2', 'Nobody sings: sixteen bars, the lead on the tune, everyone hard');
await click(region('Refrain 2'), 'refrain 2: select', { after: 600 });
await click(chip('Who sings', 'nobody: played'), 'refrain 2: nobody sings, a drop', { weight: 3, after: 1800 });
await click(chip('Length', '16 bars'), 'refrain 2: sixteen bars', { weight: 2, after: 1800 });
await click(chip('Everyone', 'hard'), 'everyone plays hard', { weight: 2, after: 1600 });
await click(cell('drum machine', 'Refrain 2'), 'drum machine in the drop', { after: 600 });
{ // four on the floor, whatever the program had it play here
  const four = insp().getByRole('group', { name: 'Plays', exact: true }).getByRole('button', { name: /^four on the floor/ });
  if ((await four.getAttribute('aria-pressed')) !== 'true') await click(four, 'drum machine: four on the floor', { weight: 2, after: 1200 });
  else { await s.over(four); mark('click', 'drum machine: four on the floor, hard', { weight: 2 }); await pause(900); }
}
await click(seam('Refrain 2'), 'the seam into the drop', { after: 600 });
await click(chip('Before it', 'a riser'), 'a riser', { weight: 2, after: 900 });
await click(chip('Before it', 'a snare roll'), 'a snare roll', { weight: 2, after: 900 });
await click(chip('a riser: how long', '4 bars'), 'the riser over four bars', { after: 900 });  // each its own length
await click(chip('a snare roll: how long', '1 bar'), 'the roll over the last bar', { after: 900 });
await click(insp().getByRole('button', { name: 'an impact', exact: true }), 'an impact on the downbeat', { weight: 2, after: 1200 });

await phase('sound', 'the sound · the drop', 'A 909, a reese bass, a supersaw, the pad and bass pumping');
await click(track('drum machine'), 'the drum machine', { after: 700 });
await click(chip('Kit', '909'), 'the 909 kit', { weight: 3, after: 1100 });
await click(track('synth bass'), 'the synth bass', { after: 700 });
await click(chip('Sound', 'reese'), 'a reese bass', { weight: 2, after: 1100 });
await choose(insp().getByRole('combobox', { name: 'synth bass: pump' }), 'classic', 'the bass pumps: classic', { weight: 2, after: 1000 });
await click(track('synth pad'), 'the synth pad', { after: 700 });
await click(chip('Sound', 'wide'), 'a wide pad', { after: 1000 });
await choose(insp().getByRole('combobox', { name: 'synth pad: pump' }), 'heavy', 'the pad pumps: heavy', { weight: 2, after: 1000 });
await click(track('synth lead'), 'the synth lead', { after: 700 });
await click(chip('Sound', 'supersaw'), 'a supersaw lead', { weight: 3, after: 1100 });
await click(track('guitar'), 'the guitar', { after: 700 });
await click(insp().getByRole('button', { name: 'Sit out everywhere' }), 'the guitar sits out', { weight: 2, after: 1600 });
{ // the drop's "everyone hard" set the guitar there too; sat out, it's silent there, and nothing is said to be wrong
  await pause(1500);
  const said = await page.locator('#problemsBar').innerText().catch(() => '');
  if (/guitar/.test(said)) throw new Error(`sitting the guitar out: ${said}`);
}
await click(region('Refrain 2'), 'refrain 2: select', { after: 500 });
await hearSung('hear the drop', 7, { weight: 3 });

// ---- verse 2: the breakdown's words
await phase('verse2', 'verse 2 · the breakdown', 'Four more lines of new words', 'left');
await writeLines('Verse 2', [
  [1, "Now some-bo-dy's *broth-er* is hum-ming it low,"],
  [2, "and some-bo-dy's moth-er is sing-ing it *slow*;"],
  [3, 'the floor is a *field* and the dark is in bloom,'],
  [4, 'and ev-ery last strang-er is sing-ing the *tune*.'],
], 'verse 2');

// ---- the bridge: the breakdown made, the second build, a lock
await phase('build2', 'the breakdown · the second build', 'No drums or bass in verse 2; the bridge builds');
await toView('Arrange');
await click(cell('drum machine', 'Verse 2'), 'drum machine in verse 2', { after: 600 });
await click(chip('Here', 'out'), 'no drums in the breakdown', { weight: 2, after: 1100 });
await click(cell('synth bass', 'Verse 2'), 'synth bass in verse 2', { after: 600 });
await click(chip('Here', 'out'), 'no bass in the breakdown', { weight: 2, after: 1100 });
await click(seam('Verse 2'), 'the seam into the breakdown', { after: 600 });
await click(chip('Before it', 'a sweep'), 'a sweep into it', { after: 1200 });
await click(insp().getByRole('group', { name: 'The sweep', exact: true }).getByRole('button', { name: /^falling/ }), 'the sweep falling: the top closes', { weight: 2, after: 1100 });
await click(region('Bridge'), 'the bridge: select', { after: 600 });
await click(chip('Moment', 'a build'), 'the bridge: a build', { weight: 3, after: 1800 });
await click(seam('Refrain 3'), 'the seam into the second drop', { after: 600 });
await click(chip('Before it', 'a riser'), 'a riser', { weight: 2, after: 900 });
await click(chip('Before it', 'a snare roll'), 'a snare roll', { after: 900 });
await click(chip('a riser: how long', '2 bars'), 'the riser over two bars', { after: 900 });
await click(chip('a snare roll: how long', '2 bars'), 'the roll over two bars', { after: 900 });
await click(insp().getByRole('button', { name: 'an impact', exact: true }), 'an impact', { weight: 2, after: 1200 });
await s.caption('a lock', 'What chance drew for verse 1, locked: a new performance can’t move it');
{
  const drawn = page.locator('[role=gridcell][aria-label*=" in Verse 1:"][aria-label*="drawn by chance"]').first();
  const who = ((await drawn.getAttribute('aria-label')) || '').split(' in Verse 1')[0];
  await click(drawn, `the ${who} in verse 1: drawn by chance`, { weight: 2, after: 900 });
}
await click(insp().getByRole('button', { name: 'Lock', exact: true }), 'Lock', { weight: 3, hold: 4, after: 1800 });

// ---- the second drop: sevenths, a freer tune, the last refrain's words
await phase('chords', 'the chords · sevenths', 'i7 · VImaj7 in the verse; VImaj7 · III and VII7sus4 · i7 in the refrain');
await openNotes('Verse 1');
await click(phraseTab(1), 'verse 1, phrase 1', { after: 700 });
await setChord(1, 0, 'C♯m7');
await chordsInBar(2, 1);
await setChord(2, 0, 'Amaj7');
await openNotes('Refrain 1');
await click(phraseTab(1), 'refrain phrase 1: Who made this song?', { after: 700 });
await setChord(1, 0, 'Amaj7');
await chordsInBar(2, 1);
await setChord(2, 0, 'E');
await click(phraseTab(2), 'refrain phrase 2', { after: 700 });
await chordsInBar(1, 1);
await setChord(1, 0, 'B');
await choose(insp().getByRole('combobox', { name: 'Quality' }), { label: '7sus4' }, 'bar 1: B7sus4', { weight: 2, after: 1100 });
await chordsInBar(2, 1);
await setChord(2, 0, 'C♯m7');

await phase('tune', 'the tune · a melisma', '“knows” sung over two notes; the refrain climbs; the last one differs');
await click(phraseTab(1), 'refrain phrase 1', { after: 700 });
await click(note('knows.', 0), '“knows.”', { after: 700 });
await click(insp().getByRole('group', { name: 'Notes on one syllable' }).getByRole('button', { name: 'Split' }), 'split it: a melisma', { weight: 3, after: 1600 });
await noteTo('knows.', 0, 'B4', '“knows” rises to B, then falls');
await click(phraseTab(3), 'refrain phrase 3', { after: 700 });
await noteTo('speak', 0, 'C♯5', '“speak-” up to the octave');
await openNotes('Refrain 3');
await click(phraseTab(2), 'refrain 3, phrase 2', { after: 700 });
await click(notes().getByRole('button', { name: /^here only/ }).first(), 'here only: refrain 3', { weight: 2, after: 800 });
await click(note('yours', 0), 'refrain 3: “yours”', { after: 600 });
await click(insp().getByRole('button', { name: '↑ Step', exact: true }), 'a step up, in refrain 3 only', { weight: 3, after: 1600 });
await openNotes('Verse 1');
await click(phraseTab(3), 'verse phrase 3', { after: 700 });
await noteTo('tune', 0, 'C♯5', '“tune” up to the octave');

await phase('last', 'refrain 3 · the second drop', 'Sixteen bars: sung, then the drop again; new lines');
await toView('Arrange');
await click(region('Refrain 3'), 'refrain 3: select', { after: 600 });
await click(chip('Length', '16 bars'), 'refrain 3: sixteen bars', { weight: 2, after: 1800 });
{ // chance drew "the last refrain starts stripped down: no"; the drop should land whole, so keep it
  const opt = insp().getByText(/starts stripped down/).first();
  if (await opt.isVisible().catch(() => false)) {
    await s.caption('a lock', 'Chance drew “the last refrain starts stripped down: no”. Locked, so the second drop lands whole');
    await click(insp().getByRole('button', { name: 'Lock', exact: true }).first(), 'Lock: the last refrain not stripped down', { weight: 3, hold: 4, after: 1800 });
    await s.caption('refrain 3 · the second drop', 'Sixteen bars: sung, then the drop again; new lines');
  }
}
await writeLines('Refrain 3', [
  [2, "It's yours on the floor now, and *on* it goes."],
  [3, 'a beat that was bor-rowed, a voice that was *true*,'],
], 'refrain 3');

// ---- what the page now holds, said before the record (a quick hand's clicks each as meant)
{
  await s.settle();
  const held = await page.evaluate(() => ({ edits: state.edits, problems: document.getElementById('problemsBar')?.innerText || '',
    locks: document.getElementById('yoursBar')?.innerText || '', mine: [...document.querySelectorAll('.region.mine')].map((r) => r.dataset.key) }));
  console.log('CHECK into the drop:', JSON.stringify(held.edits['transition.refrain:1']), '· into the second drop:', JSON.stringify(held.edits['transition.refrain:2']));
  console.log('CHECK the breakdown:', JSON.stringify(held.edits['transition.verse:1']), '· masthead:', held.locks.replace(/\n/g, ' · '), '· problems:', JSON.stringify(held.problems));
  console.log('CHECK regions marked yours:', held.mine, '· controls moved under the hand:', s.moves.length);
}

// ---- record it, and take the MIDI
await phase('record', 'record it', 'One file: the song, the program that sang it, your choices marked');
await click(page.locator('#recordNow'), 'Record', { kind: 'record', weight: 3, hold: 4, after: 400 });
if (!SKIP_RECORD) {
  const saved = page.locator('#saved');
  await saved.getByText(/^Saved /).waitFor({ timeout: 1800000 });
  await show(saved);
  mark('saved', (await saved.innerText()).split('\n')[0], { weight: 3, hold: 4 });
  await pause(2500);
  const dl = page.waitForEvent('download', { timeout: 120000 });
  await click(page.locator('#exportMidi'), 'MIDI', { weight: 2 });
  const midi = await dl;
  await midi.saveAs(path.join(OUT, 'edm2.mid'));
  mark('download', 'MIDI saved', { weight: 1 });
  await pause(1500);
  await click(saved.getByRole('button', { name: 'Play the recording' }), 'play the recording', { kind: 'play', weight: 3, hold: 4, after: 5000 });
}
await s.finish();
console.log('done', OUT);
