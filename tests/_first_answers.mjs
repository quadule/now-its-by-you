// The page's first answers as the studio's worker answers them, in Pyodide under node (tests/test_studio_quick_start.py):
// Python and numpy alone, the program unpacked, scipy and soundfile stood in for (py/lazy_imports.py), a studio started
// on each day named, and each first question answered as the worker's wire carries it (the answer's JSON text).
//
//   node tests/_first_answers.mjs PYODIDE_DIR SONGBIRD_ZIP OFFER_JSON CONFIG_JSON DAY... -> {day: {key: [status, text]}}
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const [pyDir, zip, offer, config, ...days] = process.argv.slice(2);
const { loadPyodide } = await import(pathToFileURL(`${pyDir}/pyodide.mjs`).href);
const py = await loadPyodide({ indexURL: `${pyDir}/`, packageCacheDir: `${pyDir}/`, stdout: (s) => console.error(s) });
await py.loadPackage(['numpy'], { messageCallback: () => {} });
py.unpackArchive(new Uint8Array(fs.readFileSync(zip)), 'zip', { extractDir: '/app' });
py.FS.mkdirTree('/kit');
py.FS.writeFile('/kit/offer.json', fs.readFileSync(offer));
py.globals.set('CONFIG', config);
py.globals.set('DAYS', JSON.stringify(days));
const out = py.runPython(`
import json, os, sys
os.environ["SONGBIRD_THREADS"] = "1"
os.environ["SONGBIRD_HOME"] = "/tmp/songbird-home"
os.environ["NUMBA_DISABLE_JIT"] = "1"
sys.path.insert(0, "/app")
os.chdir("/app")
import lazy_imports
lazy_imports.install(["scipy", "soundfile"])
import studio_device
said = {}
for day in json.loads(DAYS):
    device = studio_device.Device({**json.loads(CONFIG), "day": day, "home": f"/tmp/home-{day}"})
    said[day] = {k: [status, json.dumps(answer)] for k, (status, answer) in studio_device.first_answers(device).items()}
said["lazy"] = lazy_imports.lazy()
json.dumps(said)
`);
process.stdout.write(out + '\n');
