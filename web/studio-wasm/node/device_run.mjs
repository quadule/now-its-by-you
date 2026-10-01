// The studio on the device, in Pyodide under node, from a built site (web/studio-wasm/tools/build_site.py): the
// studio's worker answering the page's questions, a reader worker reading a version's file, and render workers making
// a section and the whole song, each a Pyodide of its own as in the browser; the time each takes and each one's wasm
// heap. For measuring without a browser (docs/WEB-STUDIO.md, "On the device"); Chrome is within ~20% of node.
//
//   node web/studio-wasm/node/device_run.mjs SITE [--edits JSON] [--section N] [--whole] [--read FILE.flac] [--out x.flac]
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [site] = process.argv.slice(2);
const flag = (name, fallback = null) => (process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : fallback);
const edits = JSON.parse(flag('--edits', '{}'));
const section = flag('--section') === 'none' ? 1 : Number(flag('--section', '1'));
const bundle = JSON.parse(fs.readFileSync(path.join(site, 'render', 'bundle.json'), 'utf8'));
const pyDir = path.join(site, 'render', bundle.pyodide) + '/';
const appDir = path.join(site, 'render', bundle.app) + '/';
const secs = (t) => ((performance.now() - t) / 1000).toFixed(2);

async function pyodide() {  // as studio-worker.mjs's init
  const t = performance.now();
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
  py.heap = () => (py._module.HEAPU8.length / 2 ** 20).toFixed(0);
  console.log(`  ready in ${secs(t)} s, heap ${py.heap()} MiB`);
  return py;
}

console.log('the studio (the page\'s questions)');
const studio = await pyodide();
let t = performance.now();
py_set(studio, 'CONFIG', JSON.stringify({ ...bundle.studio }));
studio.runPython('import json, studio_device\nDEVICE = studio_device.Device(json.loads(CONFIG))');
console.log(`  the studio made in ${secs(t)} s`);
function py_set(py, k, v) { py.globals.set(k, v); }
function ask(method, p, body = null) {
  const t0 = performance.now();
  py_set(studio, 'ARGS', JSON.stringify([method, p, body]));
  const out = JSON.parse(studio.runPython(`import json
m, p, b = json.loads(ARGS)
json.dumps(DEVICE.handle(m, p, {}, None, json.dumps(b).encode() if b is not None else b"", {}))`));
  console.log(`  ${method} ${p}: ${out.status} in ${secs(t0)} s, heap ${studio.heap()} MiB`);
  return out.json;
}
ask('GET', '/api/start');
ask('POST', '/api/song', { edits });
ask('POST', '/api/arrangement', { edits });
ask('POST', '/api/sound', { edits });
ask('POST', '/api/song', { edits: { ...edits, roll: 1 } });
ask('GET', '/api/timeline');
const sectionSpec = ask('POST', '/api/render/spec', { edits, section });
const wholeSpec = ask('POST', '/api/render/spec', { edits, section: null });
if (wholeSpec.warn) console.log(`  warned: ${wholeSpec.warn}`);

if (flag('--read')) {
  console.log('a reader (a version\'s file, read as data)');
  const reader = await pyodide();
  const view = JSON.parse(studio.runPython('json.dumps(DEVICE.view)'));
  reader.FS.writeFile('/tmp/brought.flac', new Uint8Array(fs.readFileSync(flag('--read'))));
  t = performance.now();
  py_set(reader, 'ARGS', JSON.stringify(['/tmp/brought.flac', view.title, view.machine, view.day, null]));
  const out = JSON.parse(reader.runPython('import json, studio_device\nstudio_device.examine_wire(*json.loads(ARGS))'));
  const got = out.json ? JSON.parse(out.json) : {};
  console.log(`  read in ${secs(t)} s: ${out.status} ${got.id || got.error}, heap ${reader.heap()} MiB`);
}

const sections = flag('--section') === 'none' ? null : sectionSpec;  // --section none: no section made
for (const [what, answer] of [['a section', sections], ['the whole song', process.argv.includes('--whole') ? wholeSpec : null]]) {
  if (!answer) continue;
  console.log(`${what} (a render worker of its own)`);
  const render = await pyodide();
  t = performance.now();
  py_set(render, 'SPEC', answer.spec);
  render.runPython('OUT = studio_render.run(SPEC, "/tmp/render", None, PROGRAM)');
  console.log(`  made in ${secs(t)} s, heap ${render.heap()} MiB, id ${render.runPython('OUT["id"]')}`);
  if (what === 'the whole song' && flag('--out')) fs.writeFileSync(flag('--out'), render.FS.readFile(render.runPython('OUT["flac"]')));
}
console.log(`the studio's heap at the end: ${studio.heap()} MiB`);
