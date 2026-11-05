// Songbird in a Web Worker: Pyodide, numpy and scipy, the program (dist/songbird.zip) and its kernels in JS
// (kernels/) or C/wasm (wasm/). The page asks for a section or the whole song; the worker answers with a
// WAV and what it cost. Off the main thread, so the page stays responsive while it sings.
import { loadPyodide } from './node_modules/pyodide/pyodide.mjs';
import * as kernels from './kernels/kernels.gen.mjs';
import * as rt from './kernels/rt.mjs';
import { loadWasmKernels, kernelsFile } from './wasm/kernels.mjs';

let py = null;
const say = (msg) => postMessage({ kind: 'log', msg });
const secs = (a, b) => ((b - a) / 1000).toFixed(2);

async function init(mode, times) {
  const t0 = performance.now();
  py = await loadPyodide({ indexURL: new URL('./node_modules/pyodide/', import.meta.url).href });
  const t1 = performance.now();
  await py.loadPackage(['numpy', 'scipy']);
  const t2 = performance.now();
  rt.setHeap(() => py._module.HEAPU8.buffer);
  const manifest = await (await fetch('./kernels/manifest.json')).text();
  py.registerJsModule('songbird_kernels', { kernels, rt, manifest });
  if (mode === 'wasm') {
    const bytes = await (await fetch(`./${kernelsFile()}`)).arrayBuffer();
    py.registerJsModule('songbird_wasm', await loadWasmKernels(bytes, py._module.memory));
  }
  const zip = new Uint8Array(await (await fetch('./dist/songbird.zip')).arrayBuffer());
  py.unpackArchive(zip, 'zip', { extractDir: '/app' });
  const t3 = performance.now();
  py.globals.set('WASM', mode === 'wasm');
  py.globals.set('TIMES', !!times);
  await py.runPythonAsync(`
import os, sys
os.environ["SONGBIRD_THREADS"] = "1"
os.environ["SONGBIRD_KERNEL_TIMES"] = "1" if TIMES else "0"
sys.path.insert(0, "/app")
os.chdir("/app")
if WASM:
    import wasm_kernels
    wasm_kernels.install()
import numba
import section as S
from songbird.synth import instruments, master
instruments.registry()
import web_patches
web_patches.install()
from collections import Counter
PORTED = str(dict(Counter(numba.PORTED.values())))
`);
  const t4 = performance.now();
  say(`loaded: pyodide ${secs(t0, t1)}s, numpy+scipy ${secs(t1, t2)}s, program ${secs(t2, t3)}s, ` +
      `import ${secs(t3, t4)}s; kernels ${py.globals.get('PORTED')}`);
}

function render(which) {
  let stageT = performance.now();
  py.registerJsModule('probe', {
    stage: (name) => {
      const now = performance.now();
      say(`  ${name} starts (the last part took ${secs(stageT, now)}s), wasm heap ${(py._module.HEAPU8.length / 2 ** 20).toFixed(0)} MiB`);
      stageT = now;
    },
  });
  const t0 = performance.now();
  py.runPython(`
import probe
numba.TIME.clear(); numba.CALLS.clear()
SONG = "songs/h-now-its-by-you.json"
PCM, INFO = S.whole(SONG, progress=probe.stage) if ${JSON.stringify(which)} == "whole" else S.section(SONG, int(${JSON.stringify(which)}), progress=probe.stage)
WAV = S.wav_bytes(PCM)
ID = master.pcm_sha256(PCM)
`);
  const t1 = performance.now();
  const wav = py.globals.get('WAV').toJs();
  const heap = py._module.HEAPU8.length / 2 ** 20;
  postMessage({
    kind: 'done', which, seconds: (t1 - t0) / 1000, id: py.globals.get('ID'),
    info: py.runPython('str({k: v for k, v in INFO.items()}) + ("  kernels %.2fs: " % sum(numba.TIME.values()) + ", ".join(f"{k} {v:.2f}" for k, v in sorted(numba.TIME.items(), key=lambda kv: -kv[1])[:6]) if numba.TIME else "")'), heap, wav,
  }, [wav.buffer]);
}

onmessage = async (e) => {
  try {
    if (e.data.cmd === 'init') await init(e.data.mode, e.data.times);
    if (e.data.cmd === 'render') render(e.data.which);
    postMessage({ kind: 'ready' });
  } catch (err) {
    postMessage({ kind: 'error', msg: String(err && err.message || err).split('\n').slice(-6).join('\n') });
  }
};
