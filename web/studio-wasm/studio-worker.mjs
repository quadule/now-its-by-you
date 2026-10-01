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
//
// The same script is also the studio itself, on the visitor's device (songbird/studio/device.js starts one, for the
// whole visit, apart from the render workers: docs/WEB-STUDIO.md, "On the device"): after "init",
//
//   → { cmd: "studio", config: { song, machine, runs_with, sing_kit? } }  ← { kind: "studio", program, song, machine, day, title, heap }
//   → { cmd: "request", id, method, path, query, version, body (ArrayBuffer or null), headers }
//   → { cmd: "restore", id, version: { id, record, genome, timeline, shared } }   a version read before, kept again
//   → { cmd: "read", id, bytes, title, machine, day, version? }  a version's file, read as data in a worker of its own
//     (no "studio" asked of it, and let go after): { id, url, shared, record, genome, timeline } to keep, or { error }
//   ← { kind: "answer", id, status, json (text), file?: { bytes (ArrayBuffer), type, name }, heap }
//
// Requests are answered one at a time, in order, except the timeline (the heaviest question: seconds), which waits
// while anything else is waiting. A job the studio took (a sung take's measuring) is made once nothing is.

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

// ---------------------------------------------------------------- the studio on the device (py/studio_device.py)

const LATER = new Set(['/api/timeline']);  // asked after everything else that's waiting

async function studio({ config }) {
  if (config.kit) {  // the singing kit (build_site.py --sing-kit), unpacked where the studio's singing reads it
    const zip = new Uint8Array(await (await fetch(config.kit)).arrayBuffer());
    py.unpackArchive(zip, 'zip', { extractDir: '/kit' });
    config = { ...config, sing_kit: '/kit' };
  }
  py.globals.set('CONFIG', JSON.stringify(config));
  const view = py.runPython(`
import json, studio_device
DEVICE = studio_device.Device(json.loads(CONFIG))
json.dumps(DEVICE.view)
`);
  postMessage({ kind: 'studio', ...JSON.parse(view), heap: heapMiB() });
}

// The device's answer ({status, json as text, file?: {path, type, name}}) as the page's shim takes it: a file's bytes
// copied out of Pyodide's memory and moved, not copied again, to the page. What goes in comes through a file in
// Pyodide's own memory file system (a request's body, a version's file), so nothing is converted twice.
const BODY = '/tmp/device-body';

function answered(id, wire) {
  const out = JSON.parse(wire);
  const said = { kind: 'answer', id, status: out.status, json: out.json, heap: heapMiB() };
  const moved = [];
  if (out.file) {
    const bytes = py.FS.readFile(out.file.path);
    said.file = { bytes: bytes.buffer, type: out.file.type, name: out.file.name || '' };
    moved.push(bytes.buffer);
  }
  postMessage(said, moved);
}

function call(method, ...args) {
  py.globals.set('ARGS', JSON.stringify(args));
  return py.runPython(`import json\nDEVICE.${method}_wire(*json.loads(ARGS))`);
}

function request(m) {
  py.FS.writeFile(BODY, m.body ? new Uint8Array(m.body) : new Uint8Array(0));
  answered(m.id, call('handle', m.method || 'GET', m.path, m.query || {}, m.version || null, BODY, m.headers || {}));
}

function read(m) {
  py.FS.writeFile(BODY, new Uint8Array(m.bytes));
  py.globals.set('ARGS', JSON.stringify([BODY, m.title, m.machine, m.day, m.version || null]));
  answered(m.id, py.runPython('import json, studio_device\nstudio_device.examine_wire(*json.loads(ARGS))'));
}

function restore(m) {
  const v = m.version || {};
  answered(m.id, call('restore', v.id, v.record, v.genome, v.timeline || null, !!v.shared));
}

function work() {  // the jobs the studio took, made now that nothing is waiting
  if (py && py.globals.has('DEVICE')) py.runPython('DEVICE.work()');
}

function failedAnswer(id, err) {
  const message = String((err && err.message) || err);
  const said = message.trim().split('\n').slice(-3).join(' ').slice(0, 600);
  const memory = /MemoryError|out of memory|Out of memory|memory access out of bounds|Array buffer allocation|RangeError/i.test(message);
  postMessage({ kind: 'answer', id, status: 500, memory,
    json: JSON.stringify({ error: memory ? 'This browser ran out of memory answering that.' : said }) });
}

// ---------------------------------------------------------------- one message at a time

const waiting = [];
let pumping = false;

async function handle(m) {
  if (m.cmd === 'init') return init(m);
  if (m.cmd === 'render') return render(m.spec);
  if (m.cmd === 'studio') return studio(m).catch((err) => failed(err));
  if (m.cmd === 'request') return request(m);
  if (m.cmd === 'read') return read(m);
  if (m.cmd === 'restore') return restore(m);
}

async function pump() {
  if (pumping) return;
  pumping = true;
  try {
    while (waiting.length) {
      let i = waiting.findIndex((m) => !(m.cmd === 'request' && LATER.has(m.path)));
      if (i < 0) i = 0;
      const [m] = waiting.splice(i, 1);
      try {
        await handle(m);
      } catch (err) {
        if (m.id !== undefined) failedAnswer(m.id, err);
        else failed(err);
      }
      if (!waiting.length && m.cmd === 'request') {
        try { work(); } catch (err) { /* a job's failure is kept on the job */ }
      }
    }
  } finally {
    pumping = false;
  }
}

onmessage = (e) => {
  waiting.push(e.data);
  pump();
};
