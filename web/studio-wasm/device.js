// The studio on the visitor's device (docs/WEB-STUDIO.md, "On the device"): the page's questions (/api/*) answered in
// this browser, by the studio's own Python in a worker (studio-worker.mjs running py/studio_device.py), instead of by
// a server. Only the static site (web/studio-wasm/tools/build_site.py) loads this, first among the page's scripts; a
// studio served by `songbird studio` never does. Plain JavaScript, no libraries.
//
// - window.fetch is wrapped: a request to this site's /api/... (but /api/versions, the hosting Worker's own) is
//   answered by the worker, with the server's statuses and JSON, so the page's other scripts don't know the
//   difference. Everything else goes to the network as ever (the page's files, the bundle, /api/versions).
// - The version the page is on: /v/<id> (a link someone shared: the file is fetched from the site, read here and
//   kept), or #version=<id> (a file the visitor brought, kept only in this browser). The page's token names it, as a
//   server's does, so every request says which version it is about.
// - A version's file is read as data, never run, in a worker of its own that is let go after; what is kept of it (the
//   record, the song, its timeline: never the audio) goes in this browser's IndexedDB, so it opens at once next time.
// - Files a server would offer at an address are kept as this browser keeps things: the MIDI file as a Blob, the
//   piano page's score in localStorage (the latest few), for the piano tab to read.
// - Singing (with the singing kit): the guide and its words are the kit's own files, fetched as they are; a take is
//   checked and queued by the studio's worker from where it was sung and its length alone, and its audio goes to a
//   measuring worker started for that take and ended after (studio-worker.mjs "measure"), which fetches the kit's
//   files the take needs and gives back only numbers. The take never reaches the studio's worker, or the network.
// - Nothing leaves this device but a version the visitor chooses to share (share(), POST /api/versions).
"use strict";

(() => {
  if (typeof document === "undefined") return;
  const mode = document.querySelector('meta[name="studio-render"]');
  if (!mode || mode.content !== "device") return;

  const network = window.fetch.bind(window);
  const ID = /^[0-9a-f]{32}$/;
  const READY_MS = 180000;  // the most a worker may take to get ready (a first visit fetches ~30 MB) before it's given up
  const READ_MS = 360000;  // ... and to read a version's file (a slow phone: it is laid out, and its timeline drawn)
  const MEASURE_MS = 600000;  // ... and to measure a sung take (a whole song on a slow phone)
  const SPEC = /^[a-z0-9]{1,8}\.k-?\d{1,2}\.t\d{1,3}$/;  // a version to sing to (webstudio/kit.py SPEC)
  const MAX_TAKE_BYTES = 40 * 2 ** 20;  // a take's most, as a server takes it (webstudio/singing.py MAX_TAKE_BYTES)
  const PIANO = "songbird-piano-score:";  // the piano page's scores, by key (the latest few)
  const MAKING = "songbird-making-whole";  // set while a whole song is made here (renderer.js), for after a crash

  // ---------------------------------------------------------------- which version
  const linked = (location.pathname.match(/^\/v\/([0-9a-f]{32})\/?$/) || [])[1] || null;
  const brought = linked ? null : (new URLSearchParams(location.hash.slice(1)).get("version") || null);
  const version = linked || (brought && ID.test(brought) ? brought : null);
  const badPath = location.pathname.startsWith("/v/") && !linked;
  const token = document.querySelector('meta[name="studio-token"]');
  if (token) token.content = version ? `device.${version}` : "device";

  // ---------------------------------------------------------------- this browser's storage (a convenience: the
  // studio works without it, opening a version again each visit)
  let opened = null;
  function db() {
    if (!opened) {
      opened = new Promise((resolve) => {
        try {
          const r = indexedDB.open("songbird-studio", 1);
          r.onupgradeneeded = () => { for (const s of ["versions", "answers", "sung"]) r.result.createObjectStore(s); };
          r.onsuccess = () => resolve(r.result);
          r.onerror = r.onblocked = () => resolve(null);
        } catch (e) { resolve(null); }
      });
    }
    return opened;
  }
  async function stored(store, mode, act) {
    const d = await db();
    if (!d) return undefined;
    return new Promise((resolve) => {
      try {
        const t = d.transaction(store, mode);
        const r = act(t.objectStore(store));
        t.oncomplete = () => resolve(r ? r.result : undefined);
        t.onerror = t.onabort = () => resolve(undefined);
      } catch (e) { resolve(undefined); }
    });
  }
  const recall = (store, key) => stored(store, "readonly", (s) => s.get(key));
  const keep = (store, key, value) => stored(store, "readwrite", (s) => s.put(value, key));
  const forget = (store, key) => stored(store, "readwrite", (s) => s.delete(key));
  const everything = (store) => stored(store, "readonly", (s) => s.getAll());

  // ---------------------------------------------------------------- workers
  let bundle = null;
  const at = (folder) => new URL(`${bundle.base}${folder}/`, location.href).href;
  const deadline = (promise, ms, what) => Promise.race([promise, new Promise((_, reject) =>
    setTimeout(() => reject(new Error(`${what} took too long`)), ms))]);

  // A worker running the program: the studio (for the whole visit), or a reader (one file, then let go).
  function spawn(onLoading, lean = false) {
    const w = new Worker(`${at(bundle.app)}studio-worker.mjs`, { type: "module" });
    const pending = new Map();
    const said = {};
    let next = 1;
    const worker = { dead: false, heap: 0 };
    const stopped = (why) => {
      worker.dead = true;
      for (const p of [...pending.values(), said.ready, said.studio]) p?.reject(Object.assign(new Error(why), { stopped: true }));
      pending.clear();
    };
    worker.ready = new Promise((resolve, reject) => { said.ready = { resolve, reject }; });
    worker.made = new Promise((resolve, reject) => { said.studio = { resolve, reject }; });
    worker.ready.catch(() => {});
    worker.made.catch(() => {});
    w.onmessage = (e) => {
      const m = e.data || {};
      if (typeof m.heap === "number") worker.heap = m.heap;
      if (m.kind === "answer") { pending.get(m.id)?.resolve(m); pending.delete(m.id); }
      else if (m.kind === "loading") onLoading?.(m);
      else if (m.kind === "ready") { said.ready.resolve(m); }
      else if (m.kind === "studio") { said.studio.resolve(m); }
      else if (m.kind === "error") {
        const err = Object.assign(new Error(m.message), { memory: !!m.memory });
        said.ready.reject(err);
        said.studio.reject(err);
      }
    };
    w.onerror = (e) => { e?.preventDefault?.(); stopped(e?.message || "the studio stopped"); };
    w.onmessageerror = () => stopped("the studio's answer couldn't be read");
    worker.ask = (message, transfer = []) => {
      if (worker.dead) return Promise.reject(Object.assign(new Error("the studio stopped"), { stopped: true }));
      const id = next++;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        w.postMessage({ ...message, id }, transfer);
      });
    };
    worker.make = (config) => { w.postMessage({ cmd: "studio", config }); return worker.made; };
    worker.stop = () => { w.terminate(); stopped("let go"); };
    w.postMessage({ cmd: "init", pyodide: at(bundle.pyodide), app: at(bundle.app), bytes: bundle.bytes, lean });
    return worker;
  }

  // the worker's JSON, held to what it should be (it answers the page, so a strange answer is said, not used)
  function parsed(m) {
    let data = null;
    try { data = m.json ? JSON.parse(m.json) : null; } catch (e) { data = null; }
    return data;
  }

  // ---------------------------------------------------------------- the studio, started at once
  let first = true;
  function said(text) {  // before the page has its song: what's happening, where it will say what it's making
    const which = document.getElementById("which");
    if (which && !(window.StudioBridge && window.StudioBridge.snapshot && window.StudioBridge.snapshot().start)) which.textContent = text;
  }

  async function start() {
    if (!bundle) {
      const r = await network("/render/bundle.json", { cache: "no-cache" });
      if (!r.ok) throw new Error(`the studio's files aren't here (${r.status})`);
      bundle = await r.json();
    }
    if (typeof WebAssembly !== "object" || typeof Worker !== "function") {
      throw new Error("this browser can't run the studio (it needs WebAssembly and workers)");
    }
    const mb = (n) => Math.round((n || 0) / 2 ** 20);
    let fetched = false;  // this browser has these files already (from its cache: nothing to count)
    try { fetched = localStorage.getItem("songbird-singer-fetched") === bundle.app; } catch (e) { fetched = false; }
    said("Getting the studio ready…");
    const worker = spawn((m) => {
      if (first && !fetched && m.bytes && m.received) said(`Getting the studio ready (once: ${mb(Math.min(m.received, m.bytes))} of ${mb(m.bytes)} MB)…`);
    });
    await deadline(worker.ready, READY_MS, "getting the studio ready");
    // the singer's files are in this browser's cache now: the renderer's first song needn't say it fetches them
    try { localStorage.setItem("songbird-singer-fetched", bundle.app); } catch (e) { /* only a convenience */ }
    const config = { ...bundle.studio };
    if (config.kit) config.kit = new URL(`${bundle.base}${config.kit}`, location.href).href;
    const view = await worker.make(config);
    first = false;
    const studio = { worker, view };
    if (version) await openVersion(studio);
    restoreSinging(studio);
    return studio;
  }

  let running = null;
  function studio() {
    if (!running || running.failed) {
      running = start();
      running.catch((e) => { running.failed = true; if (e.gone) gone(e.message); });
    }
    return running.then((s) => {
      if (!s.worker.dead) return s;
      running = null;  // stopped (for want of memory, say): started again; what it knew is kept here and given back
      return studio();
    });
  }
  if (!badPath) studio();

  // ---------------------------------------------------------------- someone's version

  const isGone = (text) => Object.assign(new Error(text), { gone: true });

  async function openVersion({ worker, view }) {
    const kept = await recall("versions", version);
    if (kept && kept.program === view.program && kept.machine === view.machine) {
      const r = await worker.ask({ cmd: "restore", version: kept });
      if (r.status === 200) return;
    }
    if (!linked) {
      throw isGone("This version was opened from a file, and this browser doesn't keep it any more. Open the file again.");
    }
    said("Fetching that version…");
    let r;
    try { r = await network(`/api/versions/${linked}`); } catch (e) { throw isGone(`It couldn't be fetched: ${e.message}.`); }
    if (r.status === 404 || r.status === 410) throw isGone("This version isn't here (any more), or the link isn't whole.");
    if (!r.ok) throw isGone(`The site couldn't give it (${r.status}): try the link again in a moment.`);
    const bytes = await r.arrayBuffer();
    said("Reading that version (it's only read, never run)…");
    const read = await readApart(bytes, view, linked);
    if (read.status !== 200) throw isGone(`This version can't be continued here: ${read.error}`);
    const v = { ...read.data, program: view.program, machine: view.machine };
    const back = await worker.ask({ cmd: "restore", version: v });
    if (back.status !== 200) throw isGone("This version was read, but couldn't be opened.");
    keep("versions", v.id, v);
  }

  // a version's file read as data in a worker of its own, let go after: {status, data | error}
  async function readApart(bytes, view, id) {
    const reader = spawn();
    try {
      await deadline(reader.ready, READY_MS, "getting ready to read it");
      const m = await deadline(reader.ask({ cmd: "read", bytes, title: view.title, machine: view.machine, day: view.day,
        version: id }, [bytes]), READ_MS, "reading it");
      const data = parsed(m);
      if (m.status !== 200) return { status: m.status || 500, error: (data && data.error) || "it couldn't be read" };
      if (!data || !ID.test(data.id || "") || (id && data.id !== id) || typeof data.genome !== "string"
          || !data.record || typeof data.record !== "object") {
        return { status: 500, error: "it was read, but what came back wasn't a version" };
      }
      return { status: 200, data };
    } catch (e) {
      return { status: 422, error: e.stopped ? "reading it stopped the reader (it may be too large for this browser)" : e.message };
    } finally {
      reader.stop();
    }
  }

  async function bring(body, s) {  // POST /api/open: a file the visitor brought, read here and kept here only
    if (!body || !body.byteLength) return [411, { error: "Send the file whole." }];
    const read = await readApart(body, s.view, null);
    if (read.status !== 200) return [read.status === 500 ? 500 : 422, { error: read.error }];
    const v = { ...read.data, program: s.view.program, machine: s.view.machine };
    await keep("versions", v.id, v);
    return [200, { id: v.id, url: `/#version=${v.id}` }];
  }

  // the page as the server's "This version isn't here" says it, in place of the studio
  function gone(text) {
    const show = () => {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "/notice.css";
      document.head.append(css);
      const h1 = document.createElement("h1");
      h1.textContent = "This version isn't here";
      const p = document.createElement("p");
      p.textContent = text;
      const back = document.createElement("p");
      const a = document.createElement("a");
      a.href = "/";
      a.textContent = "Open the studio on the song as it began";
      back.append(a);
      document.body.className = "notice";
      document.body.replaceChildren(h1, p, back);
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", show);
    else show();
  }
  if (badPath) gone("This link isn't whole: a version's link ends in 32 letters and digits.");

  // ---------------------------------------------------------------- the ways of singing kept here
  async function restoreSinging({ worker }) {
    const ways = (await everything("sung")) || [];
    for (const phrasing of ways) {
      const body = new TextEncoder().encode(JSON.stringify({ phrasing })).buffer;
      worker.ask({ cmd: "request", method: "POST", path: "/api/sing/keep", query: {}, version: null, body, headers: {} }, [body]);
    }
  }

  // ---------------------------------------------------------------- singing, on this device

  // the guide and its words: the kit's own files (immutable: fetched once), never through the studio's worker
  async function sungFile(path, spec) {
    const kit = bundle.studio && bundle.studio.kit;
    if (!kit || !SPEC.test(spec || "")) return json(404, { error: "no such version to sing to" });
    const name = path === "/api/sing/lyrics" ? `lyrics/${spec}.json` : `audio/${spec}.melody.flac`;
    let r;
    try { r = await network(new URL(`${bundle.base}${kit}${name}`, location.href).href); }
    catch (e) { return json(503, { error: `It couldn't be fetched: ${e.message}.` }); }
    return r.ok ? r : json(404, { error: "no such version to sing to" });
  }

  // a WAV's length in seconds, from its header (the karaoke's recorder writes PCM); NaN if it isn't one
  function wavSeconds(bytes) {
    try {
      const v = new DataView(bytes), tag = (at) => String.fromCharCode(...new Uint8Array(bytes, at, 4));
      if (tag(0) !== "RIFF" || tag(8) !== "WAVE") return NaN;
      let at = 12, rate = 0, frame = 0;
      while (at + 8 <= bytes.byteLength) {
        const id = tag(at), size = v.getUint32(at + 4, true);
        if (id === "fmt ") { rate = v.getUint32(at + 12, true); frame = v.getUint16(at + 10, true) * v.getUint16(at + 22, true) / 8; }
        if (id === "data") return rate && frame ? Math.min(size, bytes.byteLength - at - 8) / (rate * frame) : NaN;
        at += 8 + size + (size % 2);
      }
    } catch (e) { /* not a WAV */ }
    return NaN;
  }

  // POST /api/sing/take: where it was sung and its length go to the studio's worker, which checks and queues it as
  // a server does; the audio stays here until its measuring worker takes it
  async function take(s, body, metaLength) {
    if (!body || !(metaLength > 0) || metaLength > body.byteLength - 44) return json(400, { error: "That take was cut short: send it again." });
    const meta = body.slice(0, metaLength), wav = body.slice(metaLength);
    const seconds = wavSeconds(wav);
    if (!(seconds > 0)) return json(400, { error: "That take couldn't be read as a WAV file." });
    if (wav.byteLength > MAX_TAKE_BYTES) return json(413, { error: "That take is too long to measure here." });  // the server's
    const m = await s.worker.ask({ cmd: "request", method: "POST", path: "/api/sing/take", query: {}, version: null,
      body: meta, headers: { "x-sing-meta": String(metaLength), "x-sing-seconds": String(seconds) } }, [meta]);
    const data = parsed(m);
    if (m.status === 200 && data && data.id) measuring = measuring.then(() => measureTake(s, data.id, wav)).catch(() => {});  // a take's failure is kept on its job
    return answer("/api/sing/take", m, data);
  }

  let measuring = Promise.resolve();  // one take at a time

  async function measureTake(s, job, wav) {
    const given = await s.worker.ask({ cmd: "handout", job });
    const what = parsed(given);
    if (given.status !== 200 || !what || !what.request) return;  // let go before its turn: the audio goes with it
    let measurer = null, said;
    try {  // whatever happens from here, the job is finished (measured), never left running
      measurer = spawn(null, true);
      await deadline(measurer.ready, READY_MS, "getting ready to measure it");
      const m = await deadline(measurer.ask({ cmd: "measure", kit: new URL(`${bundle.base}${bundle.studio.kit}`, location.href).href,
        request: JSON.stringify(what.request), take: wav }, [wav]), MEASURE_MS, "measuring it");
      wav = null;
      said = m.status === 200 && m.json ? m.json : JSON.stringify({ error: (parsed(m) || {}).error || "it went wrong on this device" });
    } catch (e) {
      said = JSON.stringify({ error: e.memory
        ? "this device ran out of memory measuring it (one section at a time may fit)"
        : e.stopped ? "the browser stopped measuring it, perhaps for want of memory (one section at a time may fit)"
        : `it went wrong on this device (${e.message})` });
    } finally {
      wav = null;
      measurer?.stop();  // its memory, and the take's bytes in it, go with it
    }
    await s.worker.ask({ cmd: "measured", job, answer: said }).catch(() => {});
  }

  // Forget my singing: every way this browser kept (an earlier take's too, not only the one named), here and in the
  // studio's worker
  async function forgetSinging(s, named) {
    const names = new Set([named, ...(await stored("sung", "readonly", (st) => st.getAllKeys()) || [])]);
    for (const name of names) {
      if (name !== named) {
        const body = new TextEncoder().encode(JSON.stringify({ name })).buffer;
        await s.worker.ask({ cmd: "request", method: "POST", path: "/api/sing/forget", query: {}, version: null, body, headers: {} }, [body]);
      }
      await forget("sung", name);
    }
  }

  // ---------------------------------------------------------------- the page's requests, answered here

  const json = (status, data) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

  function pianoScore(key, text) {  // the latest few, for the piano tab (it reads them by key)
    try {
      const keys = Object.keys(localStorage).filter((k) => k.startsWith(PIANO) && k !== PIANO + key);
      while (keys.length > 2) localStorage.removeItem(keys.shift());
      localStorage.setItem(PIANO + key, text);
      return true;
    } catch (e) { return false; }
  }

  function answer(path, m, data) {
    if (m.file && path === "/api/export" && data) {  // the MIDI file: saved from a Blob under its name
      data.url = URL.createObjectURL(new Blob([m.file.bytes], { type: m.file.type }));
      data.name = m.file.name;
    } else if (m.file && path === "/api/piano" && data && /^[0-9a-f]{16,64}$/.test(data.key || "")) {
      if (pianoScore(data.key, new TextDecoder().decode(m.file.bytes))) data.url = `/piano/?score=device/${data.key}.json`;
      else return json(507, { error: "This browser has no room to keep the score for the piano page." });
    } else if (m.file) {  // singing's words and guide: the file itself
      return new Response(m.file.bytes, { status: m.status, headers: { "Content-Type": m.file.type } });
    }
    if (path === "/api/song" && data && data.listen) {  // what this page has made already plays at once
      const made = window.SongbirdRenderer && window.SongbirdRenderer.shared && window.SongbirdRenderer.shared.cache;
      const keys = [data.listen.whole, ...(data.listen.sections || [])];
      data.listen.ready = made ? keys.filter((k) => made.has(k)) : [];
    }
    if (data === null) return json(m.status === 200 ? 500 : m.status, { error: "The studio's answer couldn't be read." });
    return json(m.status, data);
  }

  async function local(url, input, init) {
    const request = typeof Request === "function" && input instanceof Request ? input : null;
    const method = String(init.method || (request ? request.method : "GET")).toUpperCase();
    const headers = new Headers(init.headers || (request ? request.headers : undefined));
    const named = (headers.get("X-Studio") || "").split(".")[1] || null;
    let body = null;
    if (init.body !== undefined && init.body !== null) body = await new Response(init.body).arrayBuffer();
    else if (request && method !== "GET" && method !== "HEAD") body = await request.arrayBuffer();
    const path = url.pathname;
    let s;
    try {
      s = await studio();
    } catch (e) {
      if (e.gone) return new Promise(() => {});  // the page is the notice now: nothing more to answer
      return json(503, { error: `This browser couldn't start the studio: ${e.message}. Reload to try again.` });
    }
    try {
      if (path === "/api/open" && method === "POST") return json(...(await bring(body, s)));
      if (method === "GET" && (path === "/api/sing/lyrics" || path === "/api/sing/guide")) return await sungFile(path, url.searchParams.get("spec"));
      if (method === "POST" && path === "/api/sing/take") return await take(s, body, Number(headers.get("X-Sing-Meta")));
      const ask = { cmd: "request", method, path, query: Object.fromEntries(url.searchParams), version: named, body,
        headers: { "x-sing-meta": headers.get("X-Sing-Meta") || "" } };
      const timeline = path === "/api/timeline" && method === "GET"
        ? `timeline|${s.view.program}|${s.view.song}|${s.view.machine}|${s.view.day}|${named || ""}` : null;
      if (timeline) {
        const hit = await recall("answers", timeline);
        if (hit) return json(200, hit);
      }
      let forgetting = null;  // read before the body is handed over
      if (path === "/api/sing/forget" && body) {
        try { forgetting = JSON.parse(new TextDecoder().decode(body)).name || null; } catch (e) { forgetting = null; }
      }
      const m = await s.worker.ask(ask, body ? [body] : []);
      const data = parsed(m);
      if (timeline && m.status === 200 && data) keep("answers", timeline, data);
      if (m.status === 200 && data && path === "/api/sing/keep" && data.name && data.phrasing) keep("sung", data.name, data.phrasing);
      if (m.status === 200 && forgetting) await forgetSinging(s, String(forgetting));
      return answer(path, m, data);
    } catch (e) {
      if (e.stopped) {
        return json(503, { error: "The studio stopped in this browser (perhaps for want of memory); it is starting again: try once more in a moment." });
      }
      return json(500, { error: e.message });
    }
  }

  window.fetch = function fetch(input, init) {
    let url;
    try { url = new URL(typeof input === "string" || input instanceof URL ? String(input) : input.url, location.href); }
    catch (e) { return network(input, init); }
    if (url.origin !== location.origin || !url.pathname.startsWith("/api/") || /^\/api\/versions(\/|$)/.test(url.pathname)) {
      return network(input, init);
    }
    return local(url, input, init || {});
  };

  // ---------------------------------------------------------------- sharing a version (the only thing sent)
  async function share(blob) {
    // its SHA-256 said with it, so the site checks the bytes as it stores them rather than hashing 20 MB itself
    const bytes = await blob.arrayBuffer();
    const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
      .map((b) => b.toString(16).padStart(2, "0")).join("");
    let r;
    try {
      r = await network("/api/versions", { method: "POST", body: bytes,
        headers: { "Content-Type": "audio/flac", "X-Content-SHA256": digest } });
    } catch (e) {
      throw new Error(`it couldn't reach the site (${e.message})`);
    }
    let data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    if (!r.ok || !data || !ID.test(String(data.id || ""))) {
      throw new Error((data && typeof data.error === "string" && data.error) || `the site didn't take it (${r.status})`);
    }
    return { id: data.id, url: new URL(`/v/${data.id}`, location.href).href };
  }

  // after a whole song stopped this page (a tab the browser closed for memory never hears why): said once, next time
  function crashed() {
    try {
      const was = localStorage.getItem(MAKING);
      if (!was) return null;
      localStorage.removeItem(MAKING);
      return "The last time, this page stopped while making a whole song, perhaps for want of memory. A shorter " +
        "version (fewer verses, a quicker tempo) may fit, or a computer.";
    } catch (e) { return null; }
  }

  window.SongbirdDevice = {
    version, linked, share, crashed, MAKING,
    ready: () => studio().then((s) => ({ ...s.view, heap: s.worker.heap })),
    get heap() { return running ? running.then((s) => s.worker.heap) : Promise.resolve(0); },
  };
})();
