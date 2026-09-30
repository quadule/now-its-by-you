// A render spec made in Pyodide under node, from a built bundle, as the studio's render worker makes it
// (studio-worker.mjs): for checking the bundle without a browser, and timing it.
//
//   node web/studio-wasm/node/spec_run.mjs BUNDLE_DIR SPEC.json [--out x.flac]
//
// SPEC.json: the answer of POST /api/render/spec (or web/studio-wasm/bench/spec_native.py --spec).
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [dir, specFile] = process.argv.slice(2);
const out = process.argv.includes('--out') ? process.argv[process.argv.indexOf('--out') + 1] : null;
const bundle = JSON.parse(fs.readFileSync(path.join(dir, 'bundle.json'), 'utf8'));
const pyDir = path.join(dir, bundle.pyodide) + '/';
const appDir = path.join(dir, bundle.app) + '/';
const answer = JSON.parse(fs.readFileSync(specFile, 'utf8'));
const t0 = performance.now();
const { loadPyodide } = await import(pathToFileURL(pyDir + 'pyodide.mjs').href);
const py = await loadPyodide({ indexURL: pyDir, packageCacheDir: pyDir });
await py.loadPackage(['numpy', 'scipy', 'soundfile'], { messageCallback: () => {} });
const kernels = await import(pathToFileURL(appDir + 'kernels/kernels.gen.mjs').href);
const rt = await import(pathToFileURL(appDir + 'kernels/rt.mjs').href);
const { loadWasmKernels } = await import(pathToFileURL(appDir + 'wasm/kernels.mjs').href);
rt.setHeap(() => py._module.HEAPU8.buffer);
py.registerJsModule('songbird_kernels', { kernels, rt, manifest: fs.readFileSync(appDir + 'kernels/manifest.json', 'utf8') });
py.registerJsModule('songbird_wasm', await loadWasmKernels(fs.readFileSync(appDir + 'wasm/kernels.wasm'), py._module.memory));
py.unpackArchive(new Uint8Array(fs.readFileSync(appDir + 'songbird.zip')), 'zip', { extractDir: '/app' });
await py.runPythonAsync(`
import os, sys
os.environ["SONGBIRD_THREADS"] = "1"
os.environ["SONGBIRD_HOME"] = "/tmp/songbird-home"
sys.path.insert(0, "/app")
os.chdir("/app")
import wasm_kernels
wasm_kernels.install()
import numba
from songbird import pack
from songbird.synth import instruments
instruments.registry()
import web_patches
web_patches.install()
import studio_render
PROGRAM = pack.program_sha256(pack.program_files())
`);
const t1 = performance.now();
console.log(`ready in ${((t1 - t0) / 1000).toFixed(1)} s; program ${py.globals.get('PROGRAM').slice(0, 12)}`);
let last = performance.now();
py.globals.set('SPEC', answer.spec);
py.globals.set('PROGRESS', (f, stage) => {
  const now = performance.now();
  console.log(`  ${((now - t1) / 1000).toFixed(2)} s  ${(f * 100).toFixed(0)}%  ${stage}  (+${((now - last) / 1000).toFixed(2)}), heap ${(py._module.HEAPU8.length / 2 ** 20).toFixed(0)} MiB`);
  last = now;
});
if (process.argv.includes('--trace')) {  // the wasm heap before and after each heavy step of a recording
  py.globals.set('HEAP', (what) => console.log(`    ${what}: heap ${(py._module.HEAPU8.length / 2 ** 20).toFixed(0)} MiB`));
  py.runPython(`
from songbird import pack, synth
from songbird.synth import master
def traced(module, name):
    f = getattr(module, name)
    def call(*a, **k):
        HEAP(name + " starts")
        try:
            return f(*a, **k)
        finally:
            HEAP(name + " ends")
    setattr(module, name, call)
for m, n in ((master, "master"), (master, "loudness"), (master, "loudness_range"), (master, "true_peak"),
             (master, "write_flac"), (master, "to_pcm16"), (pack, "pack"), (pack, "samples_id"), (synth, "render")):
    traced(m, n)
import songbird.cli as cli
cli.synth = synth
`);
}
if (process.argv.includes('--stems')) {  // every part alone, dry, float64: bench/stems_diff.py compares them
  const into = process.argv[process.argv.indexOf('--stems') + 1];
  // this checkout's studio_render.py over the bundle's, so a bundle built before it had stems() still does this
  py.FS.writeFile('/app/studio_render.py', fs.readFileSync(new URL('../py/studio_render.py', import.meta.url)));
  py.runPython('import importlib, json; from pathlib import Path; importlib.reload(studio_render); '
    + 'studio_render.stems(json.loads(SPEC), Path("/tmp/render"), "/tmp/stems.npz")');
  fs.writeFileSync(into, py.FS.readFile('/tmp/stems.npz'));
  console.log(`stems in ${((performance.now() - t1) / 1000).toFixed(1)} s: ${into}`);
  process.exit(0);
}
py.runPython('OUT = studio_render.run(SPEC, "/tmp/render", PROGRESS, PROGRAM)');
const t2 = performance.now();
console.log(`made in ${((t2 - t1) / 1000).toFixed(1)} s, heap ${(py._module.HEAPU8.length / 2 ** 20).toFixed(0)} MiB, id ${py.runPython('OUT["id"]')}`);
if (py.runPython('"record" in OUT')) console.log('record', py.runPython('import json; json.dumps({k: OUT["record"].get(k) for k in ("id", "program_sha256", "generation", "rendered_at", "python")})'));
if (out) fs.writeFileSync(out, py.FS.readFile(py.runPython('OUT["flac"]')));
