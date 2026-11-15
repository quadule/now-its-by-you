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
// - Singing: the studio's worker makes a guide from the version on the page (its score, kept here in IndexedDB);
//   a singing worker makes its melody and the template singer's analyses ahead (studio-worker.mjs "sing"), kept
//   here too, and is let go when idle; a take is checked and queued by the studio's worker from where it was sung
//   and its length alone, and its audio goes to a measuring worker started for that take and ended after
//   (studio-worker.mjs "measure"), handed the guides and templates it needs, which gives back only numbers (and
//   any template it made, to keep). The take never reaches the studio's worker, storage, or the network.
// - Nothing leaves this device but a version the visitor chooses to share (share(), POST /api/versions).
// - The page's first questions, on the song as it began (no edits saved here, no version, nothing sung here), are
//   answered at once from a small file the build made for this day (bundle.json's "first": build_site.py, from the
//   studio's own studio_device.first_answers), while the worker gets ready; then the worker answers everything. So
//   the song is on the page in a second or two, before Python is fetched. Anything else asked before the worker is
//   ready waits for it, and the page says so where someone asked. The page's day (this browser's date) is the
//   worker's too, so both answer for the same day.
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
  const GUIDE = /^[0-9a-f]{12}$/;  // a guide's name (webstudio/guide.py digest)
  const SINGER_IDLE_MS = 45000;  // a singing worker with nothing to do this long is let go (its memory with it)...
  const SINGER_DONE_MS = 10000;  // ... or this long, once it has made what a section wants ahead (melody, templates)
  const MAX_TAKE_BYTES = 40 * 2 ** 20;  // a take's most, as a server takes it (webstudio/singing.py MAX_TAKE_BYTES)
  const PIANO = "songbird-piano-score:";  // the piano page's scores, by key (the latest few)
  const MAKING = "songbird-making-whole";  // set while a whole song is made here (renderer.js), for after a crash
  const FETCHED = "songbird-studio-fetched";  // the app folder this browser's studio has fetched once (so it's cached)
  const pad = (n) => String(n).padStart(2, "0");
  const now = new Date();
  const DAY = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;  // this browser's date, for the visit
  const SALT = "songbird-machine-salt";  // this browser's random number, drawn once: who it sings as (harvest.browser)

  // ---------------------------------------------------------------- this browser, as the studio reads a machine
  // Where the build says "browser", the song is shaped by this browser as a computer is read quietly: its languages,
  // its size (cores, and memory where Chromium says), and whether its screen is dark; nothing else, and only the
  // studio's worker reduces it (studio_device.machine_of: coarse buckets, docs/HARVEST.md). A random salt, kept here,
  // makes it the same singer from visit to visit; without storage, the same for this visit.
  function browserMachine() {
    const n = navigator;
    const languages = Array.isArray(n.languages) && n.languages.length ? [...n.languages] : (n.language ? [n.language] : []);
    const prefers = (scheme) => { try { return matchMedia(`(prefers-color-scheme: ${scheme})`).matches; } catch (e) { return false; } };
    const dark = prefers("dark") ? true : prefers("light") ? false : null;
    const facts = { languages: languages.slice(0, 8), cores: n.hardwareConcurrency || null, memory: n.deviceMemory || null, dark };
    let salt = null;
    try { salt = localStorage.getItem(SALT); } catch (e) { salt = null; }
    if (!/^[0-9a-f]{16}$/.test(salt || "")) {
      salt = Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0")).join("");
      try { localStorage.setItem(SALT, salt); } catch (e) { /* this visit's alone */ }
    }
    return { facts, salt };
  }

  // ---------------------------------------------------------------- which version
  const linked = (location.pathname.match(/^\/v\/([0-9a-f]{32})\/?$/) || [])[1] || null;
  const brought = linked ? null : (new URLSearchParams(location.hash.slice(1)).get("version") || null);
  const version = linked || (brought && ID.test(brought) ? brought : null);
  const badPath = location.pathname.startsWith("/v/") && !linked;
  // ?new: this browser's new version (studio.js offers it from the published version the page opens on); a version
  // someone brought is continued by this browser too
  const NEW = new URLSearchParams(location.search).has("new") || !!version;
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
  let bundled = null;  // the bundle's manifest, fetched once (asked again each visit: it names what's current)
  function manifest() {
    if (!bundled) {
      bundled = network("/render/bundle.json", { cache: "no-cache" }).then(async (r) => {
        if (!r.ok) throw new Error(`the studio's files aren't here (${r.status})`);
        bundle = await r.json();
        return bundle;
      });
      bundled.catch(() => { bundled = null; });
    }
    return bundled;
  }
  const at = (folder) => new URL(`${bundle.base}${folder}/`, location.href).href;
  const deadline = (promise, ms, what) => Promise.race([promise, new Promise((_, reject) =>
    setTimeout(() => reject(new Error(`${what} took too long`)), ms))]);

  // A worker running the program: the studio (for the whole visit), or a reader (one file, then let go).
  function spawn(onLoading, lean = false, control = false, bytes = bundle.bytes) {
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
    w.postMessage({ cmd: "init", pyodide: at(bundle.pyodide), app: at(bundle.app),
      ...(bundle.bytecode ? { bytecode: at(bundle.bytecode) } : {}), bytes, lean, control });
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
  let ready = false;  // the studio's worker is ready: from then on it answers everything
  // Before the page has its song: what's happening, where it will say what it's making. Not while the first answers
  // give it the song; but if they can't (an edit saved here), until the header is drawn from the worker's answer.
  function said(text) {
    const which = document.getElementById("which");
    if (!which) return;
    if (answers === null ? window.StudioBridge?.snapshot?.().start : !missed || which.firstElementChild) return;
    which.textContent = text;
    const short = document.getElementById("whichShort");  // what a narrow screen shows in its place
    if (short) short.textContent = text;
  }

  async function start() {
    await manifest();
    if (typeof WebAssembly !== "object" || typeof Worker !== "function") {
      throw new Error("this browser can't run the studio (it needs WebAssembly and workers)");
    }
    let fetched = false;  // this browser has these files already (from its cache: nothing to count)
    try { fetched = localStorage.getItem(FETCHED) === bundle.app; } catch (e) { fetched = false; }
    const total = bundle.studio_bytes || bundle.bytes;
    const worker = spawn((m) => {
      if (first && !fetched && total && m.received) said(`Getting the studio ready (${Math.min(99, Math.round(100 * m.received / total))}%)…`);
    }, false, true, total);
    try {
      await deadline(worker.ready, READY_MS, "getting the studio ready");
    } catch (e) {
      worker.stop();  // never a second one beside it when the page asks again
      throw e;
    }
    // where the build opens on the published version, that's the machine until this browser's is asked for (?new)
    const published = bundle.studio.opens === "published" && !NEW;
    const config = { ...bundle.studio, day: DAY, ...(published ? { machine: "published" } : {}),
                     ...(!published && bundle.studio.machine === "browser" ? { browser: browserMachine() } : {}) };
    const view = await worker.make(config);
    try { localStorage.setItem(FETCHED, bundle.app); } catch (e) { /* only a convenience */ }
    first = false;
    const studio = { worker, view };
    if (version) await openVersion(studio);
    restoreSinging(studio);
    ready = true;
    return studio;
  }

  // ---------------------------------------------------------------- the first answers, while the worker gets ready
  // The day's file (bundle.json "first"), if this page is on the song as it began: no version, nothing sung in this
  // browser (the ways of singing kept here change the studio's answers), a day the build made, and a browser that can
  // unpack it. Each answer is the worker's own for that question that day (tests/test_studio_quick_start.py); a
  // question asked differently (an edit saved here, another day chosen) isn't in it, and waits for the worker.
  let answers = undefined;  // undefined: not known yet; null: none (the worker answers everything); else key -> [status, data]
  let firstUsed = false;  // a first answer was given: the page has its song before the worker
  let missed = false;  // a question the file couldn't answer was asked before the worker was ready
  const firstAnswers = (async () => {
    try {
      if (version || badPath || typeof DecompressionStream !== "function") return null;
      const b = await manifest();
      if (NEW && b && b.studio && b.studio.opens === "published") return null;  // made for the published version
      const f = b && b.first;
      if (!f || !/^first-[0-9a-f]{8,}\/$/.test(f.folder || "") || !(f.from <= DAY && DAY <= f.to)) return null;
      const sung = await stored("sung", "readonly", (s) => s.count());
      if (sung) return null;
      const r = await network(`${b.base}${f.folder}${DAY}.gzip`);
      if (!r.ok || !r.body) return null;
      const day = JSON.parse(await new Response(r.body.pipeThrough(new DecompressionStream("gzip"))).text());
      return day && day.v === 1 && day.day === DAY && day.answers && typeof day.answers === "object" ? day.answers : null;
    } catch (e) {
      return null;
    }
  })().then((a) => { if (answers === undefined) answers = a; return answers; });

  // a request's key, as studio_device.question makes it: the method, the path, the JSON body with its keys sorted
  function canonical(v) {
    if (Array.isArray(v)) return `[${v.map(canonical).join(",")}]`;
    if (v && typeof v === "object") return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${canonical(v[k])}`).join(",")}}`;
    return JSON.stringify(v);
  }
  function question(method, path, body) {
    return `${method} ${path} ${body === undefined ? "" : canonical(body)}`;
  }

  // what changes the studio's answers to what follows (a way of singing kept or forgotten, a version opened): once
  // asked, the first answers are done with, and every question waits for the worker, in order
  const CHANGES = /^\/api\/(sing(\/|$)|open$|cancel$)/;

  async function answeredFirst(method, url, body, named) {
    if (ready || named || url.search) return null;
    if (answers === undefined) await firstAnswers;
    const a = answers;  // as it is now: a change asked while the file was coming ends it for what follows
    if (!a || ready) return null;
    let data;
    try { data = method === "GET" ? undefined : JSON.parse(new TextDecoder().decode(body || new ArrayBuffer(0))); }
    catch (e) { data = null; }
    const said = data === null ? null : a[question(method, url.pathname, data)];
    if (!said) {
      if (method !== "GET" && CHANGES.test(url.pathname)) answers = null;
      missed = true;
      if (firstUsed) waiting();
      return null;
    }
    firstUsed = true;
    const copy = typeof structuredClone === "function" ? structuredClone(said[1]) : JSON.parse(JSON.stringify(said[1]));
    return answer(url.pathname, { status: said[0] }, copy);
  }

  // asked of the worker before it's ready, on a page that has its song already, just after someone did something
  // (pressed, clicked, typed): said where it was asked, briefly. What the page asks of its own accord (its song with
  // the edits saved here, as it opens) isn't someone's doing: the header says how it's getting on instead (said).
  let told = 0, acted = 0;
  for (const kind of ["pointerdown", "keydown"]) {
    try { document.addEventListener(kind, () => { acted = Date.now(); }, true); } catch (e) { /* no events: no words */ }
  }
  function waiting() {
    const at = Date.now();
    if (at - acted > 1500 || at - told < 4000) return;
    told = at;
    try { window.songbirdStudio?.toast?.("The studio is still getting ready: one moment."); } catch (e) { /* only words */ }
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
  if (!badPath) studio().catch(() => {});  // said where it's asked for (the page's first question fails with why)

  // ---------------------------------------------------------------- someone's version

  const isGone = (text) => Object.assign(new Error(text), { gone: true });

  function stillShared() {
    // a version this browser keeps opens from here, but its link is kept for others only while it is opened:
    // an uncached HEAD says so to the site (no audio), and says if the link has gone
    network(`/api/versions/${linked}`, { method: "HEAD", cache: "no-store" }).then((r) => {
      if (r.status === 404 || r.status === 410) {
        window.songbirdStudio?.toast?.("This version's link no longer works for others. Share it again for a new one.");
      }
    }).catch(() => {});
  }

  async function openVersion({ worker, view }) {
    const kept = await recall("versions", version);
    if (kept && kept.program === view.program && kept.machine === view.machine) {
      const r = await worker.ask({ cmd: "restore", version: kept });
      if (r.status === 200) {
        if (linked) stillShared();
        return;
      }
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
    const reader = spawn(null, false, true);
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

  // What singing makes is kept in its own database, apart from the studio's: the guides' scores (by name), their
  // melodies (by program, guide and stretch) and the template singer's analyses (by file name). All of it is the
  // song's and the machine's, never the singer's: Forget my singing clears it all the same.
  let singingDB = null;
  function sdb() {
    if (!singingDB) {
      singingDB = new Promise((resolve) => {
        try {
          const r = indexedDB.open("songbird-singing", 2);
          r.onupgradeneeded = () => {  // 2: when each thing was last used, apart from it ("used", "<store>|<key>")
            for (const s of ["guides", "melodies", "parts", "used"]) {
              if (!r.result.objectStoreNames.contains(s)) r.result.createObjectStore(s);
            }
          };
          r.onsuccess = () => resolve(r.result);
          r.onerror = r.onblocked = () => resolve(null);
        } catch (e) { resolve(null); }
      });
    }
    return singingDB;
  }
  async function sstore(store, mode, act) {
    const d = await sdb();
    if (!d) return undefined;
    return new Promise((resolve) => {
      try {
        const tx = d.transaction(store, mode);
        const r = act(tx.objectStore(store));
        tx.oncomplete = () => resolve(r ? r.result : undefined);
        tx.onerror = tx.onabort = () => resolve(undefined);
      } catch (e) { resolve(undefined); }
    });
  }
  const sget = (store, key) => sstore(store, "readonly", (s) => s.get(key));
  const skeys = (store) => sstore(store, "readonly", (s) => s.getAllKeys());
  // kept with when it was last used, in a store of its own (small: a time each), so finding the longest unused never
  // reads a melody; past MOST in a store, the longest unused go (but the guides earlier takes were sung to, which the
  // way of singing made from them needs)
  const MOST = { guides: 40, melodies: 24, parts: 60 };
  const used = (store, key) => sstore("used", "readwrite", (s) => s.put(Date.now(), `${store}|${key}`));
  async function sput(store, key, value) {
    const d = await sdb();
    if (!d) return;
    await new Promise((resolve) => {
      try {
        const tx = d.transaction([store, "used"], "readwrite");
        tx.objectStore(store).put(value, key);
        tx.objectStore("used").put(Date.now(), `${store}|${key}`);
        tx.oncomplete = tx.onerror = tx.onabort = () => resolve();
      } catch (e) { resolve(); }
    });
    const count = await sstore(store, "readonly", (s) => s.count());
    if (!(count > MOST[store])) return;
    let sung = new Set();
    try {
      const k = JSON.parse(localStorage.getItem("songbird-web-singing")) || {};
      sung = new Set((k.measurements || []).map((m) => m && m.stamp && m.stamp.guide));
    } catch (e) { /* none kept */ }
    const when = new Map();  // key -> when last used, read with one cursor (each a number)
    await new Promise((resolve) => {
      try {
        const tx = d.transaction("used", "readonly");
        const r = tx.objectStore("used").openCursor(IDBKeyRange.bound(`${store}|`, `${store}|\uffff`));
        r.onsuccess = () => {
          const c = r.result;
          if (!c) return;
          when.set(String(c.key).slice(store.length + 1), Number(c.value) || 0);
          c.continue();
        };
        tx.oncomplete = tx.onerror = tx.onabort = () => resolve();
      } catch (e) { resolve(); }
    });
    const keys = new Set((await skeys(store)) || []);
    const old = [...keys].filter((k) => !(store === "guides" && sung.has(k))).sort((x, y) => (when.get(x) || 0) - (when.get(y) || 0));
    const gone = old.slice(0, keys.size - MOST[store]);
    await new Promise((resolve) => {
      try {
        const tx = d.transaction([store, "used"], "readwrite");
        for (const k of gone) { tx.objectStore(store).delete(k); tx.objectStore("used").delete(`${store}|${k}`); }
        tx.oncomplete = tx.onerror = tx.onabort = () => resolve();
      } catch (e) { resolve(); }
    });
  }

  const guides = new Map();  // name -> {song, bytes}: this visit's, before storage (a private window has none)
  async function guideFile(name) {
    if (guides.has(name)) return guides.get(name);
    const kept = await sget("guides", name);
    if (kept && kept.bytes) { guides.set(name, kept); used("guides", name); }  // used: kept longer
    return kept || null;
  }

  // POST /api/sing/guide: the studio's worker lays the guide out; its score is kept here, its words go to the page
  async function makeGuide(s, ask, body) {
    const m = await s.worker.ask(ask, body ? [body] : []);
    const data = parsed(m);
    if (m.status === 200 && data && GUIDE.test(data.guide || "") && m.file) {
      const kept = { song: data.song, bytes: m.file.bytes };
      guides.set(data.guide, kept);
      sput("guides", data.guide, kept);
    }
    return data === null ? json(500, { error: "The studio's answer couldn't be read." }) : json(m.status, data);
  }

  // The singing worker: the full one (the whistle needs the kernels), started when a guide's melody is first wanted
  // and let go when it has had nothing to do for a while, or before a take is measured (its memory is wanted then)
  let singer = null, singerIdle = null, singerQueue = Promise.resolve();
  const singing = {};  // the last heaps (MiB) and times singing's workers said, for anyone measuring them (SongbirdDevice)
  function singerStop() {
    clearTimeout(singerIdle);
    if (singer) singer.then((w) => w.stop(), () => {});
    singer = null;
  }
  function singerWork(job, idle = SINGER_IDLE_MS) {  // one thing at a time, in order
    const run = singerQueue.then(async () => {
      clearTimeout(singerIdle);
      if (!singer) {
        const w = spawn(null, false, false);
        singer = deadline(w.ready, READY_MS, "getting ready to make the guide").then(() => w, (e) => { w.stop(); throw e; });
      }
      let w;
      try { w = await singer; } catch (e) { singer = null; throw e; }
      try { return await job(w); } finally {
        singing.singer = w.heap;  // its heap (MiB) after the job: what it holds (wasm memory only grows)
        singerIdle = setTimeout(singerStop, idle);
      }
    });
    singerQueue = run.catch(() => {});
    return run;
  }
  async function singerAsk(w, op, request, files = {}) {
    const transfer = Object.values(files);
    if (transfer.length) await w.ask({ cmd: "kit", files }, transfer);
    const m = await w.ask({ cmd: "sing", op, request: JSON.stringify(request) });
    const said = parsed(m) || {};
    if (said.ok) return { ...said.ok, file: m.file, made: m.made || {} };
    throw Object.assign(new Error(said.refused || said.error || "it went wrong on this device"), { refused: !!said.refused });
  }
  const guideKit = (g, name) => ({ [`guides/${g.song}.${name}.score.json`]: g.bytes.slice(0) });

  // GET /api/sing/melody?guide=&from=&to=[&ahead=KEY]: a stretch of the guide's melody, made by the singing worker
  // and kept; with ahead, the template singer's analyses for that stretch in that key are made next, while you
  // rehearse, so measuring a take sung there needn't make them
  async function melody(query) {
    const name = query.get("guide") || "", a = Number(query.get("from")), b = Number(query.get("to"));
    const g = GUIDE.test(name) ? await guideFile(name) : null;
    if (!g || !(a >= 0 && b > a)) return json(404, { error: "No such guide to sing to: reload the page." });
    const key = `${bundle.app}|${name}|${a.toFixed(3)}-${b.toFixed(3)}`;
    let wav = ((await sget("melodies", key)) || {}).bytes;
    try {
      if (wav) used("melodies", key);
      else {
        wav = await singerWork(async (w) => (await singerAsk(w, "melody", { song: g.song, guide: name, from_s: a, to_s: b },
          guideKit(g, name))).file.bytes);
        sput("melodies", key, { bytes: wav });
      }
    } catch (e) {
      return json(e.refused ? 404 : 500, { error: e.stopped ? "The guide couldn't be made: the browser stopped it, perhaps for want of memory."
        : `The guide couldn't be made: ${e.message}` });
    }
    const ahead = query.get("ahead");
    if (ahead !== null && /^-?\d{1,2}$/.test(ahead)) templatesAhead(g, name, a, Number(query.get("until") || b), Number(ahead)).catch(() => {});
    return new Response(wav.slice(0), { status: 200, headers: { "Content-Type": "audio/wav" } });
  }

  async function templatesAhead(g, name, a, b, key) {
    const request = { song: g.song, guide: name, from_s: a, to_s: b, key };
    await singerWork(async (w) => {
      const wanted = (await singerAsk(w, "parts", request, guideKit(g, name))).parts || [];
      const have = new Set((await skeys("parts")) || []);
      if (wanted.every((f) => have.has(f))) return;
      const made = (await singerAsk(w, "template", request)).made;
      for (const [file, bytes] of Object.entries(made)) await sput("parts", file, { bytes });
    }, SINGER_DONE_MS);
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
    const request = what.request;
    singerStop();  // the guide is made: its memory is the measuring's now
    let measurer = null, said;
    try {  // whatever happens from here, the job is finished (measured), never left running
      measurer = spawn(null, true);
      await deadline(measurer.ready, READY_MS, "getting ready to measure it");
      // the guides sung to (this take's, and each earlier one's this browser still has), then the templates kept for
      // the pieces this take is measured in, in any key
      const files = {};
      const names = [request.guide, ...(request.earlier || []).map((e) => e && e.stamp && e.stamp.guide)];
      for (const name of new Set(names.filter((n) => GUIDE.test(n || "")))) {
        const g = await guideFile(name);
        if (g) Object.assign(files, guideKit({ ...g, song: request.song }, name));
      }
      await measurer.ask({ cmd: "kit", files }, Object.values(files));
      const parts = parsed(await measurer.ask({ cmd: "sing", op: "parts", request: JSON.stringify(request) })) || {};
      const prefixes = (parts.ok && parts.ok.parts) || [];
      const kept = {};
      for (const file of (await skeys("parts")) || []) {
        if (prefixes.some((p) => String(file).startsWith(p))) {
          const part = await sget("parts", file);
          if (part && part.bytes) { kept[`measured/parts/${file}`] = part.bytes; used("parts", file); }
        }
      }
      if (Object.keys(kept).length) await measurer.ask({ cmd: "kit", files: kept }, Object.values(kept));
      const m = await deadline(measurer.ask({ cmd: "measure", request: JSON.stringify(request), take: wav }, [wav]),
        MEASURE_MS, "measuring it");
      Object.assign(singing, { measuring: m.heap, seconds: m.seconds, made: Object.keys(m.made || {}).length });
      wav = null;
      for (const [file, bytes] of Object.entries(m.made || {})) await sput("parts", file, { bytes });
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
    for (const store of ["guides", "melodies", "parts", "used"]) await sstore(store, "readwrite", (st) => st.clear());
    guides.clear();
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
    const early = await answeredFirst(method, url, body, named);
    if (early) return early;
    let s;
    try {
      s = await studio();
    } catch (e) {
      if (e.gone) return new Promise(() => {});  // the page is the notice now: nothing more to answer
      return json(503, { error: `This browser couldn't start the studio: ${e.message}. Reload to try again.` });
    }
    try {
      if (path === "/api/open" && method === "POST") return json(...(await bring(body, s)));
      if (method === "GET" && path === "/api/sing/melody") return await melody(url.searchParams);
      if (method === "POST" && path === "/api/sing/take") return await take(s, body, Number(headers.get("X-Sing-Meta")));
      const ask = { cmd: "request", method, path, query: Object.fromEntries(url.searchParams), version: named, body,
        headers: { "x-sing-meta": headers.get("X-Sing-Meta") || "" } };
      if (method === "POST" && path === "/api/sing/guide") return await makeGuide(s, ask, body);
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
    version, linked, share, crashed, MAKING, singing,
    renderStarts: singerStop,  // a song made here: singing's worker gives its memory back first (renderer.js)
    ready: () => studio().then((s) => ({ ...s.view, heap: s.worker.heap })),
    get heap() { return running ? running.then((s) => s.worker.heap) : Promise.resolve(0); },
  };
})();
