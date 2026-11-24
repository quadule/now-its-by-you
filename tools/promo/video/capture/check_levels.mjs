// Checks timeline.gain/level against known moments of the stage's level curves.
//   node tools/promo/video/capture/check_levels.mjs
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { ROOT } from './serve.mjs';
import { Timeline } from '../web/core/timeline.js';

const file = join(ROOT, 'renders/promo/video/data/timeline.json');
const tl = new Timeline(JSON.parse(readFileSync(existsSync(file) ? file : join(ROOT, 'renders/promo/video/scratch/fixture/timeline.json'), 'utf8')));
const cases = [
  ['drummachine#', 0.9, 0], ['drummachine#', 5.8, 0], ['drummachine#', 10, 1], ['drummachine#', 20, 0],
  ['whistle', 5, 0], ['whistle', 10.9, 0], ['harp', 10, 0], ['harp', 25.6, 0], ['harp', 30, 1],
  ['voice', 50, 1],                      // no curve: 0 dB
];
let bad = 0;
for (const [part, t, want] of cases) {
  const g = tl.gain(part, t), ok = Math.abs(g - want) < 1e-6;
  if (!ok) bad++;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${part} at ${t} s: gain ${g.toFixed(4)} (${tl.level(part, t).toFixed(1)} dB), expected ${want}`);
}
// between points the fade is linear in gain
const [a, b] = tl.levels['drummachine#'].slice(0, 2);
const mid = tl.gain('drummachine#', (a[0] + b[0]) / 2);
console.log(`${Math.abs(mid - 0.5) < 1e-6 ? 'ok  ' : 'FAIL'} drummachine# halfway up its first fade: ${mid.toFixed(4)}, expected 0.5`);
if (Math.abs(mid - 0.5) >= 1e-6) bad++;
process.exit(bad ? 1 : 0);
