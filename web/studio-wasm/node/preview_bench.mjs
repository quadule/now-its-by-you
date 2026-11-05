// Exercise the actual studio worker in Node with Web Worker API adapters. This measures desktop
// Pyodide, not phone performance. Use the FLAC-capable songbird.zip from tools/build_site.py.
// node web/studio-wasm/node/preview_bench.mjs --bundle SITE/render/app-HASH/songbird.zip [--full-control]
//   [--section 2] [--cache-mib 32] [--out preview.flac] [--read rendition.flac] [--control-only] [--no-bytecode]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { Worker, isMainThread, parentPort, workerData } from 'node:worker_threads';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
if (!isMainThread) {
  const listeners = new Map();
  globalThis.addEventListener = (kind, listener) => {
    const group = listeners.get(kind) || [];
    group.push(listener);
    listeners.set(kind, group);
  };
  globalThis.postMessage = (message, transfer) => parentPort.postMessage(message, transfer);
  globalThis.onmessage = null;
  parentPort.on('message', (data) => {
    globalThis.onmessage?.({ data });
    for (const listener of listeners.get('message') || []) listener({ data });
  });
  const network = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    if (!String(url).startsWith('file:')) return network(url, options);
    let filename = fileURLToPath(url);
    if (filename === path.join(root, 'songbird.zip')) filename = workerData.bundle;
    else if (filename.startsWith(root + path.sep) && !fs.existsSync(filename)) {  // the app folder's own (bytecode.zip)
      filename = path.join(path.dirname(workerData.bundle), path.relative(root, filename));
    }
    if (!fs.existsSync(filename)) return new Response(null, { status: 404 });
    return new Response(fs.readFileSync(filename));
  };
  await import('../studio-worker.mjs');
  parentPort.postMessage({ kind: 'boot' });
} else {
  const args = process.argv.slice(2);
  const option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
  const supplied = option('--bundle', null);
  if (!supplied) throw new Error('--bundle requires the FLAC-capable songbird.zip from tools/build_site.py');
  const zipped = path.resolve(supplied);
  const section = Number(option('--section', '2'));
  // the site's bytecode folder (bundle.json's, beside the app folder), unless --no-bytecode: a worker compiling all
  const site = JSON.parse(fs.readFileSync(path.join(path.dirname(path.dirname(zipped)), 'bundle.json'), 'utf8'));
  const bytecode = site.bytecode && !args.includes('--no-bytecode')
    ? pathToFileURL(path.join(path.dirname(path.dirname(zipped)), site.bytecode)).href + '/' : undefined;
  const cacheBytes = Number(option('--cache-mib', '32')) * 2 ** 20;
  const seconds = (start) => ((performance.now() - start) / 1000).toFixed(3);
  const open = async (control) => {
    const worker = new Worker(new URL(import.meta.url), { workerData: { bundle: zipped } });
    let next = 0;
    const pending = new Map();
    worker.on('message', (message) => {
      if (message.kind === 'progress') console.log(`  ${message.stage}`);
      const key = pending.has(message.id) ? message.id : message.kind;
      const awaiting = pending.get(key);
      if (awaiting) { pending.delete(key); awaiting.resolve(message); }
      if (message.kind === 'error') {
        for (const entry of pending.values()) entry.reject(new Error(message.message));
        pending.clear();
      }
    });
    worker.on('error', (error) => { for (const entry of pending.values()) entry.reject(error); });
    const wait = (key) => new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(key); reject(new Error(`worker did not answer ${key}`)); }, 180000);
      pending.set(key, { resolve(value) { clearTimeout(timer); resolve(value); },
        reject(error) { clearTimeout(timer); reject(error); } });
    });
    await wait('boot');
    const ready = wait('ready');
    worker.postMessage({ cmd: 'init', pyodide: path.join(root, 'node_modules/pyodide') + '/',
      app: pathToFileURL(root + '/').href, bytecode, control, stemCacheBytes: cacheBytes });
    const loaded = await ready;
    console.log(`${control ? 'control' : 'renderer'} ready ${loaded.seconds.toFixed(3)}s, heap ${loaded.heap.toFixed(0)} MiB`);
    return { worker, wait, call(message) { const id = ++next; const answer = wait(id); worker.postMessage({ ...message, id }); return answer; } };
  };
  let control, renderer;
  try {
    const start = performance.now();
    control = await open(!args.includes('--full-control'));
    let mark = performance.now();
    const started = control.wait('studio');
    control.worker.postMessage({ cmd: 'studio', config: { song: 'songs/h-now-its-by-you.json', machine: 'none' } });
    const view = await started;
    if (view.kind === 'error' || view.status >= 400) throw new Error(view.json || view.message);
    console.log(`studio view ${seconds(mark)}s, time to usable ${seconds(start)}s, heap ${view.heap?.toFixed(0)} MiB`);
    const request = async (route, body, method = 'POST') => {
      const answer = await control.call({ cmd: 'request', method, path: route,
        body: new TextEncoder().encode(JSON.stringify(body)), query: {}, headers: {} });
      if (answer.status !== 200) throw new Error(`${route}: ${answer.json}`);
      return JSON.parse(answer.json);
    };
    for (const route of ['/api/timeline', '/api/arrangement', '/api/sound']) {
      mark = performance.now();
      await request(route, {}, route === '/api/timeline' ? 'GET' : 'POST');
      console.log(`${route} ${seconds(mark)}s`);
    }
    const spec = await request('/api/render/spec', { edits: {}, section });
    if (args.includes('--read')) {
      const bytes = fs.readFileSync(option('--read'));
      const read = await control.call({ cmd: 'read', bytes: new Uint8Array(bytes),
        title: view.title, machine: view.machine, day: view.day });
      if (read.status !== 200) throw new Error(`packet read: ${read.json}`);
      const restored = await control.call({ cmd: 'restore', version: JSON.parse(read.json) });
      if (restored.status !== 200) throw new Error(`packet restore: ${restored.json}`);
      console.log('packet read and restore passed');
    }
    if (!args.includes('--control-only')) {
      renderer = await open(false);
      const make = async (answer, label) => {
        const done = renderer.wait('done');
        mark = performance.now();
        renderer.worker.postMessage({ cmd: 'render', spec: answer.spec });
        const result = await done;
        console.log(`${label} ${seconds(mark)}s, heap ${result.heap.toFixed(0)} MiB, id ${result.id}`);
        if (args.includes('--out') && label === 'initial') fs.writeFileSync(option('--out'), new Uint8Array(result.flac));
        return result;
      };
      await make(spec, 'initial');
      const changed = await request('/api/render/spec', { edits: { 'mix.width': 0.3 }, section });
      if (changed.key === spec.key) throw new Error('mix edit did not change render spec');
      await make(changed, 'mix edit');
      await make(spec, 'original again');
      console.log(`control heap remains ${view.heap?.toFixed(0)} MiB; cache budget ${cacheBytes / 2 ** 20} MiB`);
    }
  } finally {
    await renderer?.worker.terminate();
    await control?.worker.terminate();
  }
}
