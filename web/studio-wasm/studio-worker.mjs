// The studio's render worker: the song made in the visitor's browser (songbird/studio/renderer.js starts it,
// docs/WEB-STUDIO.md "Made in the visitor's browser"). Pyodide, numpy, scipy and soundfile, the program itself
// (songbird.zip: the same files the server runs, so a recording carries the same program), and its kernels in JS
// and C/wasm (docs/notes/BROWSER-RENDER.md). It makes what the server's render spec says (py/studio_render.py) and
// hands back the FLAC: a section's preview, or the whole song as its recording (the packet).
//
//   → { cmd: "init", pyodide: URL of py-<hash>/, app: URL of app-<hash>/, bytecode?: URL of bc-<hash>/,
//       bytes: what a first visit fetches }
//   ← { kind: "loading", received, bytes, step }  ...  { kind: "ready", seconds, heap }
//   → { cmd: "render", spec: the spec as JSON text, keep?: { song, day } }
//   ← { kind: "progress", progress, stage }  ...  { kind: "done", id, duration, flac (ArrayBuffer), seconds, heap, record,
//       stems? }
//   (keep, for a whole song: its stems kept as it is made, named after it (studio_render.Kept): stems is
//    { name, parts, gain, again, seconds, files: [{ index, name, crc, bytes }], midi: { name, crc, bytes }, readme })
//   ← { kind: "error", message, memory } at any point: the renderer then asks the server instead
//
// One render at a time; the renderer terminates the worker after a whole song (wasm memory never shrinks).
//
// The same script is also the studio itself, on the visitor's device (songbird/studio/device.js starts one, for the
// whole visit, apart from the render workers: docs/WEB-STUDIO.md, "On the device"): after "init" with control (numpy
// alone: scipy and soundfile stood in for until used, py/lazy_imports.py),
//
//   → { cmd: "studio", config: { song, machine, runs_with, day, singing?, browser? } }  ← { kind: "studio", program, song, machine, day, title, heap }
//     (day: the page's, YYYY-MM-DD; singing: the site carries singing's measuring, so the studio offers it)
//   → { cmd: "request", id, method, path, query, version, body (ArrayBuffer or null), headers }
//   → { cmd: "restore", id, version: { id, record, genome, timeline, shared } }   a version read before, kept again
//   → { cmd: "read", id, bytes, title, machine, day, version? }  a version's file, read as data in a worker of its own
//     (no "studio" asked of it, and let go after): { id, url, shared, record, genome, timeline } to keep, or { error }
//   ← { kind: "answer", id, status, json (text), file?: { bytes (ArrayBuffer), type, name }, heap }
//
//   → { cmd: "handout", id, job }            a sung take's job: what to measure ({request}: the server's, but the audio)
//   → { cmd: "measured", id, job, answer }   what its measuring worker answered (JSON text): the job finished here
//
// Requests are answered one at a time, in order, except the timeline (the heaviest question: seconds), which waits
// while anything else is waiting. A job the studio took is made once nothing is; a sung take's never is (below).
//
// And a sung take is measured in a worker of its own (device.js starts one for each take and ends it after, so the
// measuring's memory, and the take's freed bytes in it, go with it; docs/WEB-SINGING.md "On the device"), and a
// guide's melody and the template singer's analyses are made in another, a singing worker (the full one: the
// whistle needs the kernels), let go when it has been idle a while:
//
//   → { cmd: "init", ..., lean: true }   Pyodide and the program, without the renderer's kernels (measuring)
//   → { cmd: "kit", id, files: { path in the kit: bytes } }   the guides sung to and the templates kept, from storage
//   → { cmd: "sing", id, op: "parts" | "melody" | "template", request (JSON text) }
//   ← { kind: "answer", id, status: 200, json: sing_measure.op_json's ({ok} | {refused} | {error}), file?: the melody
//       (a WAV), made?: { template file name: bytes } (those it made, for storage), heap }
//   → { cmd: "measure", id, request (JSON text), take (ArrayBuffer: the WAV, moved here) }
//   ← { kind: "answer", id, status: 200, json: sing_measure.answer's ({ok} | {refused} | {error}), made?, heap }

let py = null;
let appURL = '';
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

// The studio's worker and a reader ("control") load numpy alone: the program imports scipy and soundfile but their
// questions never run them (py/lazy_imports.py stands in for both), so neither is fetched unless one is used; then it
// is, and the question asked again (needing, below). A render or a measuring worker loads all three.
const LAZY = ['scipy', 'soundfile'];

// The packages' wheels fetched while Python starts, rather than after it (into the HTTP cache: they're immutable,
// where loadPackage then finds them); not counted here, but when loadPackage reads them
function warm(pyodide, packages) {
  fetched(`${pyodide}pyodide-lock.json`).then((r) => r.json()).then((lock) => {
    const names = new Set();
    const todo = [...packages];
    while (todo.length) {
      const name = todo.pop();
      if (names.has(name) || !lock.packages[name]) continue;
      names.add(name);
      todo.push(...(lock.packages[name].depends || []));
    }
    for (const name of names) fetched(`${pyodide}${lock.packages[name].file_name}`).then((r) => r.arrayBuffer()).catch(() => {});
  }).catch(() => {});
}

async function init({ pyodide, app, bytecode, bytes, lean, control, stemCacheBytes }) {
  const t0 = performance.now();
  appURL = app;
  total = bytes || 0;
  step = 'Python';
  loading(true);
  // the program is fetched beside Python and its packages, not after them
  const program = fetch(`${app}songbird.zip`).then((r) => {
    if (!r.ok) throw new Error(`the program couldn't be fetched (${r.status})`);
    return r.arrayBuffer();
  });
  program.catch(() => {});
  const packages = control ? ['numpy'] : ['numpy', 'scipy', 'soundfile'];
  warm(pyodide, packages);
  const { loadPyodide } = await import(`${pyodide}pyodide.mjs`);
  const code = shippedCode(bytecode, app, packages);
  py = await loadPyodide({ indexURL: pyodide, stdout: () => {}, stderr: () => {}, stdLibURL: code.stdlib });
  step = packages.join(', ');
  loading(true);
  await py.loadPackage(packages, { messageCallback: () => {}, errorCallback: () => {} });
  step = 'the program';
  loading(true);
  if (lean || control) return initLean(new Uint8Array(await program), t0, control, await code.modules);
  const [kernels, rt, { loadWasmKernels, kernelsFile }, manifest, zipBuf] = await Promise.all([
    import(`${app}kernels/kernels.gen.mjs`),
    import(`${app}kernels/rt.mjs`),
    import(`${app}wasm/kernels.mjs`),
    fetch(`${app}kernels/manifest.json`).then((r) => r.text()),
    program,
  ]);
  rt.setHeap(() => py._module.HEAPU8.buffer);
  py.registerJsModule('songbird_kernels', { kernels, rt, manifest });
  const wasm = await (await fetch(`${app}${kernelsFile()}`)).arrayBuffer();  // with SIMD where it validates
  py.registerJsModule('songbird_wasm', await loadWasmKernels(wasm, py._module.memory));
  const zip = new Uint8Array(zipBuf);
  py.unpackArchive(zip, 'zip', { extractDir: '/app' });
  unpackCode(await code.modules);
  step = 'getting the singer ready';
  loading(true);
  await py.runPythonAsync(`
import os, sys
os.environ["SONGBIRD_THREADS"] = "1"
os.environ["SONGBIRD_HOME"] = "/tmp/songbird-home"
os.environ["SONGBIRD_STEM_CACHE_BYTES"] = ${JSON.stringify(String(stemCacheBytes ?? 64 * 2 ** 20))}
sys.path.insert(0, "/app")
os.chdir("/app")
import bytecode
bytecode.start()
import web_patches
web_patches.plain_docs()
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

// A measuring worker's start: the program unpacked, but none of the renderer's kernels or instruments (the measuring
// imports what it needs itself)
async function initLean(zip, t0, control = false, code = []) {
  py.unpackArchive(zip, 'zip', { extractDir: '/app' });
  unpackCode(code);
  await py.runPythonAsync(`
import os, sys
os.environ["SONGBIRD_THREADS"] = "1"
os.environ["SONGBIRD_HOME"] = "/tmp/songbird-home"
${control ? 'os.environ["NUMBA_DISABLE_JIT"] = "1"' : ''}
sys.path.insert(0, "/app")
os.chdir("/app")
import bytecode
bytecode.start()
${control ? `import lazy_imports\nlazy_imports.install(${JSON.stringify(LAZY)})` : 'import web_patches\nweb_patches.plain_docs()'}
`);
  postMessage({ kind: 'ready', seconds: (performance.now() - t0) / 1000, heap: heapMiB(), received });
}

function render(spec, keep = null) {
  const t0 = performance.now();
  let told = 0;
  const progress = (fraction, stage) => {
    const now = performance.now();
    if (now - told > 100) { told = now; postMessage({ kind: 'progress', progress: fraction, stage }); }
  };
  py.globals.set('SPEC', spec);
  py.globals.set('PROGRESS', progress);
  py.globals.set('KEEP', keep ? JSON.stringify(keep) : null);
  py.runPython(`
import gc, json, shutil
shutil.rmtree("/tmp/render", ignore_errors=True)
OUT = studio_render.run(SPEC, "/tmp/render", PROGRESS, PROGRAM, json.loads(KEEP) if KEEP else None)
del KEEP
KEPT = OUT.pop("stems", None)
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
  const moved = [flac.buffer];
  let stems;
  const kept = py.runPython('KEPT');
  if (kept) {
    const out = kept.toJs({ dict_converter: Object.fromEntries });  // the files copied out of Pyodide's memory
    kept.destroy();
    const own = (data) => (data.byteLength === data.buffer.byteLength ? data.buffer : data.slice().buffer);
    const file = (index, name, data, crc) => ({ index, name, crc: crc >>> 0, bytes: own(data) });
    stems = { name: out.name, parts: out.parts, gain: out.gain, again: out.again, seconds: out.seconds,
      files: out.files.map((f) => file(...f)), midi: file(0, ...out.midi), readme: file(0, ...out.readme) };
    moved.push(...stems.files.map((f) => f.bytes), stems.midi.bytes, stems.readme.bytes);
  }
  py.runPython('shutil.rmtree("/tmp/render", ignore_errors=True); del OUT, SPEC, KEPT; gc.collect()');
  py.globals.delete('PROGRESS');
  postMessage({ ...summary, kind: 'done', made: summary.kind, seconds: (performance.now() - t0) / 1000, heap: heapMiB(),
    flac: flac.buffer, ...(stems ? { stems } : {}) }, moved);
}

// The stems, in the steps the page schedules over a few of these workers (py/studio_render.py Stems; renderer.js
// stems): each worker lays the song once, then makes the parts it is given one at a time, holding one part's samples:
//   → { cmd: "stems", id, op: "open", spec, recording?: [file name, id] }  ← plan: { parts, band, singers, weights, words, name }
//   → { cmd: "stems", id, op: "make", part }       ← { peak, seconds }   (the part held until it is encoded)
//   → { cmd: "stems", id, op: "encode", gain }     ← { index, name, crc, bytes (ArrayBuffer) }, and let go
//   → { cmd: "stems", id, op: "rescale", part, bytes, was, gain }   a part's file turned down: the same answer
//   → { cmd: "stems", id, op: "finish", gain }     ← { name, parts, gain, midi: { name, crc, bytes }, readme: { ... } }
// each as { kind: "stems", id, ok, heap } or { kind: "stems", id, error, memory }
function stemsFile([index, name, data, crc]) {
  const bytes = data.toJs();  // a copy, out of Pyodide's memory
  data.destroy?.();
  return { index, name, crc: crc >>> 0, bytes: bytes.buffer };
}

function stemsStep(m) {
  const t0 = performance.now();
  const said = (ok, moved = []) => postMessage({ kind: 'stems', id: m.id, ok, heap: heapMiB(),
    seconds: (performance.now() - t0) / 1000 }, moved);
  try {
    if (m.op === 'open') {
      py.globals.set('SPEC', m.spec);
      py.globals.set('RECORDING', m.recording ? JSON.stringify(m.recording) : null);
      const plan = py.runPython(`
import json, shutil
from pathlib import Path
shutil.rmtree("/tmp/stems", ignore_errors=True)
_spec = json.loads(SPEC)
studio_render.check(_spec, PROGRAM)
if _spec["kind"] != "stems":
    raise studio_render.Refused("this spec doesn't make the stems")
STEMS = studio_render.Stems(_spec, Path("/tmp/stems"), json.loads(RECORDING) if RECORDING else None)
del SPEC, RECORDING, _spec
json.dumps(STEMS.plan())
`);
      return said(JSON.parse(plan));
    }
    if (m.op === 'make') {
      py.globals.set('PART', m.part);
      return said({ peak: py.runPython('STEMS.make(PART)') });
    }
    if (m.op === 'encode' || m.op === 'rescale') {
      py.globals.set('GAIN', m.gain);
      let out;
      if (m.op === 'encode') out = py.runPython('STEMS.encode(GAIN)');
      else {
        py.globals.set('PART', m.part);
        py.globals.set('DATA', new Uint8Array(m.bytes));
        py.globals.set('WAS', m.was);
        out = py.runPython('_out = STEMS.rescale(PART, DATA.to_bytes(), WAS, GAIN)\ndel DATA\n_out');
      }
      const file = stemsFile(out.toJs({ depth: 1 }));
      out.destroy();
      return said(file, [file.bytes]);
    }
    if (m.op === 'finish') {
      py.globals.set('GAIN', m.gain);
      const done = py.runPython('STEMS.finish(GAIN)');
      const out = done.toJs({ dict_converter: Object.fromEntries });
      done.destroy();
      const file = ([name, data, crc]) => ({ name, crc: crc >>> 0, bytes: new Uint8Array(data).buffer });
      const ok = { name: out.name, parts: out.parts, gain: out.gain, midi: file(out.midi), readme: file(out.readme) };
      py.runPython('del STEMS\nimport gc\ngc.collect()');
      return said(ok, [ok.midi.bytes, ok.readme.bytes]);
    }
    throw new Error(`no stems step ${m.op}`);
  } catch (err) {
    const message = String((err && err.message) || err);
    postMessage({ kind: 'stems', id: m.id, error: message.trim().split('\n').slice(-3).join(' ').slice(0, 600),
      memory: /MemoryError|out of memory|Out of memory|memory access out of bounds|Array buffer allocation|RangeError/i.test(message) });
  }
}

function failed(err) {
  const message = String((err && err.message) || err);
  // the last lines of a Python traceback say what went wrong
  const said = message.trim().split('\n').slice(-3).join(' ').slice(0, 600);
  postMessage({ kind: 'error', message: said,
    memory: /MemoryError|out of memory|Out of memory|memory access out of bounds|Maximum call stack|Array buffer allocation|RangeError/i.test(message) });
}

// ---------------------------------------------------------------- the studio on the device (py/studio_device.py)

// Python run with what it needs: if it used scipy or soundfile, which a control worker hasn't fetched
// (lazy_imports.Needed), the package is fetched and the same thing run again. What ran is the studio's answering, which
// keeps nothing of a question it didn't finish.
const NEEDED = /lazy_imports\.Needed: (\w+)/;
async function needing(run) {
  for (let tries = 0; ; tries++) {
    try {
      return run();
    } catch (err) {
      const need = NEEDED.exec(String((err && err.message) || err));
      if (!need || !LAZY.includes(need[1]) || tries >= LAZY.length) throw err;
      await py.loadPackage([need[1]], { messageCallback: () => {}, errorCallback: () => {} });
      py.runPython(`import lazy_imports\nlazy_imports.real(${JSON.stringify(need[1])})`);
    }
  }
}

const LATER = new Set(['/api/timeline']);  // asked after everything else that's waiting

// a file of the singing kit, put where the measuring reads it (Pyodide's memory: never storage)
function kitWrite(name, bytes) {
  if (!/^(guides|measured\/parts)\/[A-Za-z0-9._+-]+\.(json|npz)$/.test(name) || name.includes('..')) throw new Error(`not a kit file: ${name}`);
  py.FS.mkdirTree(`/kit/${name.split('/').slice(0, -1).join('/')}`);
  py.FS.writeFile(`/kit/${name}`, new Uint8Array(bytes));
}

async function studio({ config }) {
  if (config.singing) config = { ...config, sing_kit: '/kit' };  // its guides kept here, in Pyodide's memory
  py.globals.set('CONFIG', JSON.stringify(config));
  const view = await needing(() => py.runPython(`
import json, studio_device
DEVICE = studio_device.Device(json.loads(CONFIG))
json.dumps(DEVICE.view)
`));
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

async function request(m) {
  answered(m.id, await needing(() => {
    py.FS.writeFile(BODY, m.body ? new Uint8Array(m.body) : new Uint8Array(0));  // (again, if asked again)
    return call('handle', m.method || 'GET', m.path, m.query || {}, m.version || null, BODY, m.headers || {});
  }));
}

async function read(m) {
  answered(m.id, await needing(() => {
    py.FS.writeFile(BODY, new Uint8Array(m.bytes));
    py.globals.set('ARGS', JSON.stringify([BODY, m.title, m.machine, m.day, m.version || null]));
    return py.runPython('import json, studio_device\nstudio_device.examine_wire(*json.loads(ARGS))');
  }));
}

async function restore(m) {
  const v = m.version || {};
  answered(m.id, await needing(() => call('restore', v.id, v.record, v.genome, v.timeline || null, !!v.shared)));
}

async function handout(m) {
  answered(m.id, await needing(() => call('handout', m.job)));
}

async function measured(m) {
  answered(m.id, await needing(() => call('measured', m.job, m.answer)));
}

// ---------------------------------------------------------------- a sung take measured, in a worker of its own

let singing = null;  // WORLD and the measuring's own files, once
function singingReady() {
  if (!singing) {
    singing = (async () => {
      const { loadWorld } = await import(`${appURL}world/world.mjs`);
      py.registerJsModule('songbird_world', await loadWorld(await (await fetch(`${appURL}world/world.wasm`)).arrayBuffer()));
      py.unpackArchive(new Uint8Array(await (await fetch(`${appURL}singing.zip`)).arrayBuffer()), 'zip', { extractDir: '/app' });
      py.runPython('import sing_measure');
    })();
  }
  return singing;
}

// the template analyses a request used that the kit wasn't given: made here, for the page to keep
function madeFiles(said, given) {
  const out = {};
  const moved = [];
  for (const name of (said.ok && said.ok.templates) || []) {
    const path = `/kit/measured/parts/${name}`;
    if (given.has(name) || !py.FS.analyzePath(path).exists) continue;
    const bytes = py.FS.readFile(path);
    out[name] = bytes.buffer;
    moved.push(bytes.buffer);
  }
  return [out, moved];
}

const given = new Set();  // the template files storage gave this worker

async function kit(m) {
  await singingReady();
  for (const [name, bytes] of Object.entries(m.files || {})) {
    kitWrite(name, bytes);
    if (name.startsWith('measured/parts/')) given.add(name.slice('measured/parts/'.length));
  }
  postMessage({ kind: 'answer', id: m.id, status: 200, json: '{"ok": {}}', heap: heapMiB() });
}

async function sing(m) {
  const t0 = performance.now();
  await singingReady();
  py.globals.set('OP', m.op);
  py.globals.set('REQUEST', m.request);
  const json = py.runPython('_said = sing_measure.op_json(OP, REQUEST)\ndel OP, REQUEST\n_said');
  const said = JSON.parse(json);
  const out = { kind: 'answer', id: m.id, status: 200, json, heap: heapMiB(), seconds: (performance.now() - t0) / 1000 };
  const moved = [];
  if (said.ok && said.ok.file) {
    const bytes = py.FS.readFile(said.ok.file);
    py.FS.unlink(said.ok.file);
    out.file = { bytes: bytes.buffer, type: 'audio/wav' };
    moved.push(bytes.buffer);
  }
  const [made, more] = madeFiles(said, given);
  out.made = made;
  postMessage(out, [...moved, ...more]);
}

async function measure(m) {
  const t0 = performance.now();
  await singingReady();
  const ready = (performance.now() - t0) / 1000;
  py.globals.set('TAKE', new Uint8Array(m.take));
  py.globals.set('REQUEST', m.request);
  const json = py.runPython(`
import json
_request = json.loads(REQUEST)
_request["kit"] = "/kit"
_said = sing_measure.answer_json(TAKE, _request)
del TAKE, _request, REQUEST
_said
`);
  const [made, moved] = madeFiles(JSON.parse(json), given);
  postMessage({ kind: 'answer', id: m.id, status: 200, json, made, heap: heapMiB(), ready,
    seconds: (performance.now() - t0) / 1000 }, moved);
}

async function work() {  // the jobs the studio took, made now that nothing is waiting
  if (py && py.globals.has('DEVICE')) await needing(() => py.runPython('DEVICE.work()'));
}

function failedAnswer(id, err) {
  const message = String((err && err.message) || err);
  const said = message.trim().split('\n').slice(-3).join(' ').slice(0, 600);
  const memory = /MemoryError|out of memory|Out of memory|memory access out of bounds|Array buffer allocation|RangeError/i.test(message);
  postMessage({ kind: 'answer', id, status: 500, memory,
    json: JSON.stringify({ error: memory ? 'This browser ran out of memory answering that.' : said }) });
}

// ---------------------------------------------------------------- the bundle's bytecode (py/bytecode.py)

// Made with the bundle (tools/bytecode.mjs), so this worker compiles only what the build didn't import: the standard
// library's zip with its modules' bytecode (Pyodide is started with it in place of the one it serves), and the pyc
// files of the packages this worker loads and of the program, unpacked under /pycache before anything is imported.
// Each pyc is checked against its source's hash as it's imported. Without them (a bundle built without them, or an
// archive that couldn't be fetched) the modules are compiled as they're imported.
function shippedCode(bytecode, app, packages) {
  const get = (url) => fetch(url).then((r) => (r.ok ? r.arrayBuffer() : null)).catch(() => null);
  // the standard library: Pyodide fetches it as it would its own (beside its wasm); undefined, its own
  const stdlib = bytecode ? `${bytecode}stdlib.zip` : undefined;
  const names = ['numpy', 'scipy', 'soundfile'].filter((n) => packages.includes(n));
  const modules = Promise.all([...(bytecode ? names.map((n) => get(`${bytecode}${n}.zip`)) : []),
    bytecode ? get(`${app}bytecode.zip`) : null]);
  return { stdlib, modules };
}

function unpackCode(archives) {  // before bytecode.start()
  for (const archive of archives) {
    if (!archive) continue;
    try { py.unpackArchive(archive, 'zip', { extractDir: '/' }); } catch { /* compiled as it's imported */ }
  }
}

// ---------------------------------------------------------------- one message at a time

const waiting = [];
let pumping = false;

async function handle(m) {
  if (m.cmd === 'init') return init(m);
  if (m.cmd === 'render') return render(m.spec, m.keep);
  if (m.cmd === 'stems') return stemsStep(m);
  if (m.cmd === 'studio') return studio(m).catch((err) => failed(err));
  if (m.cmd === 'request') return request(m);
  if (m.cmd === 'read') return read(m);
  if (m.cmd === 'restore') return restore(m);
  if (m.cmd === 'handout') return handout(m);
  if (m.cmd === 'measured') return measured(m);
  if (m.cmd === 'measure') return measure(m);
  if (m.cmd === 'kit') return kit(m);
  if (m.cmd === 'sing') return sing(m);
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
        try { await work(); } catch (err) { /* a job's failure is kept on the job */ }
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
