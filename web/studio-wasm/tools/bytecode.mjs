// The bundle's bytecode (py/bytecode.py build()), made in Pyodide itself so it is its interpreter's own: numpy, scipy
// and soundfile loaded from Pyodide's wheels beside it (node_modules/pyodide, as build_render.py has them), the
// program unpacked at /app as a worker unpacks it, every module it can import imported, and each one's bytecode
// written into OUT. Column tables left out (PYTHONNODEBUGRANGES), as the worker never shows them.
//
//   node web/studio-wasm/tools/bytecode.mjs PROGRAM.zip OUT
import fs from 'node:fs';
import path from 'node:path';
import { loadPyodide } from 'pyodide';

const [zip, out] = process.argv.slice(2);
if (!zip || !out) throw new Error('usage: node tools/bytecode.mjs PROGRAM.zip OUT');
fs.mkdirSync(out, { recursive: true });
const said = [];
const py = await loadPyodide({ env: { PYTHONNODEBUGRANGES: '1', HOME: '/home/pyodide', SONGBIRD_THREADS: '1' },
  stdout: (s) => said.push(s), stderr: (s) => said.push(s) });
await py.loadPackage(['numpy', 'scipy', 'soundfile'], { messageCallback: () => {}, errorCallback: () => {} });
py.unpackArchive(new Uint8Array(fs.readFileSync(zip)), 'zip', { extractDir: '/app' });
py.FS.mkdirTree('/out');
py.FS.mount(py.FS.filesystems.NODEFS, { root: path.resolve(out) }, '/out');
const made = py.runPython(`
import json, os, sys
sys.path.insert(0, "/app")
os.chdir("/app")
import web_patches
web_patches.plain_docs()  # scipy imported as the worker imports it
import bytecode
json.dumps(bytecode.build("/out"))
`);
console.log(made);
