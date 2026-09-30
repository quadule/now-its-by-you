// The studio's render worker: the song made in the visitor's browser (songbird/studio/renderer.js starts it,
// docs/WEB-STUDIO.md "Made in the visitor's browser"). Pyodide, numpy, scipy and soundfile, the program itself
// (songbird.zip: the same files the server runs, so a recording carries the same program), and its kernels in JS
// and C/wasm (docs/BROWSER-RENDER.md). It makes what the server's render spec says (py/studio_render.py) and
// hands back the FLAC: a section's preview, or the whole song as its recording (the packet).
//
//   → { cmd: "init", pyodide: URL of py-<hash>/, app: URL of app-<hash>/, bytes: what a first visit fetches }
//   ← { kind: "loading", received, bytes, step }  ...  { kind: "ready", seconds, heap }
//   → { cmd: "render", spec: the spec as JSON text }
//   ← { kind: "progress", progress, stage }  ...  { kind: "done", id, duration, flac (ArrayBuffer), seconds, heap, record }
//   ← { kind: "error", message, memory } at any point: the renderer then asks the server instead
//
// One render at a time; the renderer terminates the worker after a whole song (wasm memory never shrinks).

let py = null;
let received = 0;
let total = 0;
let step = '';
let lastSaid = 0;

const heapMiB = () => (py ? py._module.HEAPU8.length / 2 ** 20 : 0);
const loading = (force = false) => {
  const now = performance.now();
  if (force || now - lastSaid > 200) {
    lastSaid = now;
    postMessage({ kind: 'loading', received, bytes: total, step });
  }
};

// Everything fetched is counted as it arrives, for "getting the singer ready" on a first visit (from the HTTP
// cache after that: the bundle's names are its contents' hashes, so it is kept for good).
const fetched = globalThis.fetch.bind(globalThis);
globalThis.fetch = async (...args) => {
  const response = await fetched(...args);
  if (!response.body || !response.ok) return response;
  const counting = new TransformStream({
    transform(chunk, out) { received += chunk.byteLength; loading(); out.enqueue(chunk); },
  });
  return new Response(response.body.pipeThrough(counting),
    { status: response.status, statusText: response.statusText, headers: response.headers });
};

// something the policy blocked (WebAssembly compiled without 'wasm-unsafe-eval', say): Pyodide only warns and waits,
// so say so, and the renderer asks the server at once rather than after a stall
addEventListener('securitypolicyviolation', (e) => {
  postMessage({ kind: 'error', message: `blocked by the page's policy (${e.violatedDirective})`, memory: false });
});

async function init({ pyodide, app, bytes }) {
  const t0 = performance.now();
  total = bytes || 0;
  step = 'Python';
  loading(true);
  const { loadPyodide } = await import(`${pyodide}pyodide.mjs`);
  py = await loadPyodide({ indexURL: pyodide, stdout: () => {}, stderr: () => {} });
  step = 'numpy, scipy';
  loading(true);
  await py.loadPackage(['numpy', 'scipy', 'soundfile'], { messageCallback: () => {}, errorCallback: () => {} });
  step = 'the program';
  loading(true);
  const kernels = await import(`${app}kernels/kernels.gen.mjs`);
  const rt = await import(`${app}kernels/rt.mjs`);
  const { loadWasmKernels } = await import(`${app}wasm/kernels.mjs`);
  rt.setHeap(() => py._module.HEAPU8.buffer);
  const manifest = await (await fetch(`${app}kernels/manifest.json`)).text();
  py.registerJsModule('songbird_kernels', { kernels, rt, manifest });
  const wasm = await (await fetch(`${app}wasm/kernels.wasm`)).arrayBuffer();
  py.registerJsModule('songbird_wasm', await loadWasmKernels(wasm, py._module.memory));
  const zip = new Uint8Array(await (await fetch(`${app}songbird.zip`)).arrayBuffer());
  py.unpackArchive(zip, 'zip', { extractDir: '/app' });
  step = 'getting the singer ready';
  loading(true);
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
instruments.registry()  # every instrument's module, so every kernel is declared
import web_patches
web_patches.install()
import studio_render
PROGRAM = pack.program_sha256(pack.program_files())
`);
  postMessage({ kind: 'ready', seconds: (performance.now() - t0) / 1000, heap: heapMiB(), received,
    program: py.globals.get('PROGRAM') });
}

function render(spec) {
  const t0 = performance.now();
  let told = 0;
  const progress = (fraction, stage) => {
    const now = performance.now();
    if (now - told > 100) { told = now; postMessage({ kind: 'progress', progress: fraction, stage }); }
  };
  py.globals.set('SPEC', spec);
  py.globals.set('PROGRESS', progress);
  py.runPython(`
import gc, json, shutil
shutil.rmtree("/tmp/render", ignore_errors=True)
OUT = studio_render.run(SPEC, "/tmp/render", PROGRESS, PROGRAM)
RECORD = OUT.pop("record", None)
SUMMARY = json.dumps({**{k: OUT[k] for k in ("kind", "key", "id", "duration")},
                      "record": {"generation": RECORD.get("generation"), "rendered_at": RECORD.get("rendered_at"),
                                 "yours": len(RECORD.get("chosen_by_you") or {}), "title": RECORD.get("title"),
                                 "program_sha256": RECORD.get("program_sha256")} if RECORD else None})
del RECORD
gc.collect()
`);
  const summary = JSON.parse(py.globals.get('SUMMARY'));
  const path = py.runPython('OUT["flac"]');
  const flac = py.FS.readFile(path);  // a copy, out of Pyodide's memory
  py.runPython('shutil.rmtree("/tmp/render", ignore_errors=True); del OUT, SPEC; gc.collect()');
  py.globals.delete('PROGRESS');
  postMessage({ ...summary, kind: 'done', made: summary.kind, seconds: (performance.now() - t0) / 1000, heap: heapMiB(),
    flac: flac.buffer }, [flac.buffer]);
}

function failed(err) {
  const message = String((err && err.message) || err);
  // the last lines of a Python traceback say what went wrong
  const said = message.trim().split('\n').slice(-3).join(' ').slice(0, 600);
  postMessage({ kind: 'error', message: said,
    memory: /MemoryError|out of memory|Out of memory|memory access out of bounds|Maximum call stack|Array buffer allocation|RangeError/i.test(message) });
}

onmessage = async (e) => {
  try {
    if (e.data.cmd === 'init') await init(e.data);
    else if (e.data.cmd === 'render') render(e.data.spec);
  } catch (err) {
    failed(err);
  }
};
