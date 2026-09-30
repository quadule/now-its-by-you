// Songbird in Pyodide under node: a section preview (or the whole song), timed, its PCM saved as .npy to
// compare with the native render's.
//
//   node web/studio-wasm/node/run.mjs [--section 2 | --whole] [--kernels js|python|wasm] [--out x.npy]
//        [--song songs/h-now-its-by-you.json] [--times] [--reps 2]
//
// Needs `npm install` in web/studio-wasm (pyodide) and dist/songbird.zip (tools/bundle.py). numpy and scipy
// are Pyodide's packages, fetched from its CDN the first time and cached beside it.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadPyodide } from 'pyodide';
import * as kernels from '../kernels/kernels.gen.mjs';
import * as rt from '../kernels/rt.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : dflt; };
const which = args.includes('--whole') ? 'whole' : opt('--section', '2');
const mode = opt('--kernels', 'js');
const out = opt('--out', null);
const song = opt('--song', 'songs/h-now-its-by-you.json');
const reps = Number(opt('--reps', '2'));
const log = (...a) => console.log(...a);

const t0 = performance.now();
const py = await loadPyodide({ stdout: (s) => log(s), stderr: (s) => log(s) });
const tPy = performance.now();
await py.loadPackage(['numpy', 'scipy'], { messageCallback: () => {} });
const tPk = performance.now();

rt.setHeap(() => py._module.HEAPU8.buffer);
let manifest = fs.readFileSync(path.join(root, 'kernels/manifest.json'), 'utf8');
if (mode === 'python') manifest = '{}';
const env = { SONGBIRD_THREADS: '1', SONGBIRD_WEB_DGEMM: args.includes('--no-dgemm') ? '0' : '1', SONGBIRD_KERNEL_TIMES: args.includes('--times') ? '1' : '0' };
// --fallbacks: numpy's and scipy's own operations where songbird has them for the loops written to save memory
// (fx.JIT false, as natively with NUMBA_DISABLE_JIT=1); the kernels themselves stay JS or wasm
if (args.includes('--fallbacks')) env.NUMBA_DISABLE_JIT = '1';
if (mode !== 'wasm') py.registerJsModule('songbird_kernels', { kernels, rt, manifest });
if (mode === 'wasm') {
  const { loadWasmKernels } = await import('../wasm/kernels.mjs');
  const wasm = await loadWasmKernels(fs.readFileSync(path.join(root, 'wasm/kernels.wasm')), py._module.memory);
  py.registerJsModule('songbird_kernels', { kernels, rt, manifest });
  py.registerJsModule('songbird_wasm', wasm);
}
const zip = fs.readFileSync(path.join(root, 'dist/songbird.zip'));
py.unpackArchive(new Uint8Array(zip), 'zip', { extractDir: '/app' });
const tZip = performance.now();
if (opt('--mount', null)) {  // host:guest, a host folder in Pyodide's file system (e.g. captured kernel calls)
  const [host, guest] = opt('--mount').split(':');
  py.FS.mkdirTree(guest);
  py.FS.mount(py.FS.filesystems.NODEFS, { root: host }, guest);
}

py.globals.set('ENV', py.toPy(env));
py.globals.set('WASM', mode === 'wasm');
await py.runPythonAsync(`
import os, sys, time
os.environ.update(ENV)
sys.path.insert(0, '/app')
os.chdir('/app')
if WASM:
    import wasm_kernels
    wasm_kernels.install()
t = time.perf_counter()
import numba
import section as S
from songbird.synth import instruments
instruments.registry()
import web_patches
web_patches.install(dgemm=os.environ.get("SONGBIRD_WEB_DGEMM", "1") == "1")
IMPORT_S = time.perf_counter() - t
`);
const tImp = performance.now();
log(`load: pyodide ${((tPy - t0) / 1000).toFixed(2)}s, numpy+scipy ${((tPk - tPy) / 1000).toFixed(2)}s, ` +
    `unzip ${((tZip - tPk) / 1000).toFixed(2)}s, import songbird ${((tImp - tZip) / 1000).toFixed(2)}s`);
log('ported:', py.runPython(`
from collections import Counter
str(dict(Counter(numba.PORTED.values())))`));

if (opt('--exec', null)) {  // a Python file run in the prepared Pyodide instead of a render
  const code = fs.readFileSync(opt('--exec'), 'utf8');
  try { await py.runPythonAsync(code); } catch (err) { log(String(err.message).split('\n').slice(-12).join('\n')); }
  process.exit(0);
}

// told each part's name as the render starts it: the wasm heap then (it only grows: its size is the peak)
let t = 0;
py.registerJsModule('probe', {
  stage: (name) => {
    const heap = py._module.HEAPU8.length / 2 ** 20;
    if (args.includes('--stages')) log(`    ${((performance.now() - t) / 1000).toFixed(2)}s ${name}: wasm heap ${heap.toFixed(0)} MiB`);
  },
});
for (let r = 0; r < reps; r++) {
  const a = performance.now();
  t = a;
  try {
    py.runPython(`
import probe
numba.TIME.clear(); numba.CALLS.clear()
PCM, INFO = S.whole(${JSON.stringify(song)}, progress=probe.stage) if ${JSON.stringify(which)} == 'whole' else S.section(${JSON.stringify(song)}, int(${JSON.stringify(which)}), progress=probe.stage)
`);
  } catch (err) {
    log(`FAILED after ${((performance.now() - a) / 1000).toFixed(2)}s, wasm heap ${(py._module.HEAPU8.length / 2 ** 20).toFixed(0)} MiB:`);
    log(String(err.message).split('\n').slice(-3).join('\n'));
    process.exit(1);
  }
  const b = performance.now();
  const heap = py._module.HEAPU8.length / 2 ** 20;
  const mu = process.memoryUsage();
  log(`render ${which} #${r + 1}: ${((b - a) / 1000).toFixed(2)}s  ${py.runPython('str(INFO)')}  ` +
      `wasm heap ${heap.toFixed(0)} MiB, rss ${(mu.rss / 2 ** 20).toFixed(0)} MiB, js arrays ${(mu.arrayBuffers / 2 ** 20).toFixed(0)} MiB`);
  if (args.includes('--times')) {
    log(py.runPython(`
tot = sum(numba.TIME.values())
lines = [f"  kernels {tot:.2f}s"]
for k, v in sorted(numba.TIME.items(), key=lambda kv: -kv[1])[:25]:
    lines.append(f"  {k:32s} {v:8.3f}s {numba.CALLS[k]:6d} calls  {numba.PORTED.get(k)}")
"\\n".join(lines)`));
  }
}
if (args.includes('--profile')) {  // where the Python side's time goes (cProfile, by own time)
  log(py.runPython(`
import cProfile, pstats, io
pr = cProfile.Profile()
pr.enable()
S.whole(${JSON.stringify(song)}) if ${JSON.stringify(which)} == 'whole' else S.section(${JSON.stringify(song)}, int(${JSON.stringify(which)}))
pr.disable()
buf = io.StringIO()
pstats.Stats(pr, stream=buf).sort_stats('tottime').print_stats(35)
buf.getvalue()`));
}
if (out) {
  py.runPython(`import numpy as np; np.save('/tmp/out.npy', PCM)`);
  fs.writeFileSync(out, py.FS.readFile('/tmp/out.npy'));
  log('saved', out);
}
