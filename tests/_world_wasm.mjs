// For tests/test_world_wasm.py: WORLD in wasm (web/studio-wasm/world) on a signal, without Pyodide, as
// py/world_wasm.py drives it: harvest, then cheaptrick a chunk of frames at a time (and all at once, which must
// give the same bits), and the allocator's own check.
//
//   node tests/_world_wasm.mjs IN.f64 OUT_DIR
// writes OUT_DIR/f0.f64, sp.f64 (chunked), sp_whole.f64, and prints {selftest, memory_mib, peak_mib} as JSON.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWorld } from '../web/studio-wasm/world/world.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const [input, out] = process.argv.slice(2);
const world = await loadWorld(fs.readFileSync(path.join(here, '../web/studio-wasm/world/world.wasm')));
const raw = fs.readFileSync(input);
const x = new Float64Array(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.length));
const fs_ = 44100;

const w = world.instance();
const view = (p, n) => new Float64Array(w.memory.buffer, p, n);
const n = x.length;
const m = w.world_harvest_length(fs_, n, 5.0);
const px = w.world_alloc(8 * n), pt = w.world_alloc(8 * m), pf = w.world_alloc(8 * m);
view(px, n).set(x);
w.world_harvest(px, n, fs_, 60.0, 900.0, 5.0, pt, pf);
const f0 = view(pf, m).slice();
fs.writeFileSync(path.join(out, 'f0.f64'), Buffer.from(f0.buffer));

const size = w.world_cheaptrick_fft_size(fs_, 71.0);
const bins = size / 2 + 1;
for (const [name, chunk] of [['sp.f64', 97], ['sp_whole.f64', m]]) {
  const ps = w.world_alloc(8 * chunk * bins);
  const sp = new Float64Array(m * bins);
  w.world_cheaptrick_begin(fs_, size, -0.15);
  for (let i = 0; i < m; i += chunk) {
    const k = Math.min(chunk, m - i);
    w.world_cheaptrick_frames(px, n, fs_, pt + 8 * i, pf + 8 * i, k, ps);
    sp.set(view(ps, k * bins), i * bins);
  }
  w.world_cheaptrick_end();
  w.world_free(ps);
  fs.writeFileSync(path.join(out, name), Buffer.from(sp.buffer));
}
const memory = w.memory.buffer.byteLength, peak = w.world_peak_bytes();

const t = world.instance();
const pg = t.world_alloc(16);
const selftest = [11, 12, 13].map((seed) => t.world_alloc_selftest(seed, 3000, pg));
console.log(JSON.stringify({ selftest, memory_mib: memory / 2 ** 20, peak_mib: peak / 2 ** 20, frames: m, bins }));
