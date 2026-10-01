// Measuring a sung take in Pyodide under node, as the browser does (py/sing_measure.py; docs/WEB-SINGING.md,
// "On the device"): Pyodide with numpy, scipy and soundfile, the program (dist/songbird.zip, tools/bundle.py) and
// the measuring's own files (dist/singing.zip, tools/sing_bundle.py), WORLD in wasm (world/world.wasm). Then a
// Python file runs in it, with host folders mounted where it asks.
//
//   node web/studio-wasm/node/sing_run.mjs --exec FILE.py [--mount HOST:GUEST ...] [--arg VALUE ...] [--dist DIR]
//
// The Python file finds its --arg values in ARGS, and HEAP() gives Pyodide's heap in bytes (it only grows, so its
// size is its peak); world_wasm.PEAK has WORLD's.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadPyodide } from 'pyodide';
import { loadWorld } from '../world/world.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const args = process.argv.slice(2);
const many = (name) => args.flatMap((a, i) => (a === name ? [args[i + 1]] : []));
const exec = many('--exec')[0];
const dist = many('--dist')[0] || path.join(root, 'dist');  // where songbird.zip and singing.zip are
if (!exec) throw new Error('--exec FILE.py');

const t0 = performance.now();
const py = await loadPyodide({ stdout: (s) => console.log(s), stderr: (s) => console.error(s) });
await py.loadPackage(['numpy', 'scipy', 'soundfile'], { messageCallback: () => {} });
py.registerJsModule('songbird_world', await loadWorld(fs.readFileSync(path.join(root, 'world/world.wasm'))));
for (const name of ['songbird.zip', 'singing.zip']) {
  py.unpackArchive(new Uint8Array(fs.readFileSync(path.join(dist, name))), 'zip', { extractDir: '/app' });
}
// tools/bundle.py ships py/soundfile.py, a stub for renders that never write FLAC; measuring reads WAVs with the
// real one (Pyodide's), as the bundle build_render.py makes does (it leaves the stub out)
if (py.FS.analyzePath('/app/soundfile.py').exists) py.FS.unlink('/app/soundfile.py');
for (const spec of many('--mount')) {
  const [host, guest] = spec.split(':');
  py.FS.mkdirTree(guest);
  py.FS.mount(py.FS.filesystems.NODEFS, { root: path.resolve(host) }, guest);
}
py.globals.set('ARGS', py.toPy(many('--arg')));
py.globals.set('HEAP', () => py._module.HEAPU8.length);
py.globals.set('LOAD_S', (performance.now() - t0) / 1000);
await py.runPythonAsync(`
import os, sys
os.environ["SONGBIRD_THREADS"] = "1"
sys.path.insert(0, "/app")
os.chdir("/app")
`);
try {
  await py.runPythonAsync(fs.readFileSync(exec, 'utf8'));
} catch (err) {
  console.error(String(err.message).split('\n').slice(-25).join('\n'));
  process.exit(1);
}
