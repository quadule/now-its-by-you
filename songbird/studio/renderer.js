// The renderer: how a section's preview and a whole recording are made, behind one small interface, so the page
// doesn't care where the singing is made. Either the studio's server (its one queue: /api/listen, /api/record,
// /api/job, /api/cancel), or, where a public studio serves the bundle for it (songbird studio --browser-render),
// the visitor's own browser: a worker running the program itself (web/studio-wasm/studio-worker.mjs, Pyodide),
// given the server's render spec (/api/render/spec: the version resolved there), so it makes the same samples and
// the same recording. The server is the fallback for anything the browser can't do. Plain JavaScript, no libraries.
//
//   const r = SongbirdRenderer.create(ask)        ask(path, body) -> Promise of the answer (the page's api())
//   const task = r.preview({ edits, who, section }, onProgress)    a section (a number) or the whole song (null)
//   const task = r.record({ edits }, onProgress)                   the whole rendition, as one file
//   r.cancel(task)                                                 stop waiting; a job still queued is dropped
//   task.done    -> Promise of the last job: { state: "done", url, key, label, result, where } or { state: "failed", error }
//                (a whole song's result has bar_seconds: each bar line of the score's ruler, in seconds of its audio)
//   task.job     the job as last heard; onProgress(job) hears each: { state: "queued" | "running", ahead, eta, stage,
//                progress 0..1 } (ahead and eta only where the queue is shared: a public studio)
//   job.where    "browser" or "server": which made it (SongbirdRenderer.made lists every render, for the page and tests)
//
// Where (docs/WEB-STUDIO.md, "Made in the visitor's browser"): the Tools sheet's setting, "auto" by default: in this
// browser if the studio serves the bundle and this is a desktop browser with WebAssembly, workers and (where it says)
// 4 GB of memory or more; not on phones and tablets. A whole song is made in a worker of its own, terminated after
// (wasm memory never shrinks); sections in one worker kept for a few, then replaced. Any failure, a timeout, running
// out of memory, the worker stopped: that render is made by the server, said quietly in the progress; after two
// failures (or a whole song's memory), the server makes them for the rest of the visit.
//
// On the device (the static site: docs/WEB-STUDIO.md, "On the device"; the page says studio-render "device"), there
// is no server: every render is made in this browser, whatever the browser (phones too: no gating), and the render
// spec is asked of the studio running in the page's own worker (web/studio-wasm/device.js). A failure is said as it
// is, with what may help (a shorter version, a computer). A whole song being made is marked in localStorage, so a page
// the browser stopped for memory can say so when it's opened again (SongbirdDevice.crashed).
"use strict";

(() => {
  const POLL = { preview: 450, record: 600 };  // ms between asking how a job is going
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const MODES = ["auto", "browser", "server"];
  const SETTING = "songbird-make-where";  // this browser's choice (a convenience: auto if it's lost)
  const FETCHED = "songbird-singer-fetched";  // the app folder this browser has fetched once (so it's cached)
  const SECTION_USES = 4;  // sections one worker makes before it's replaced (its heap only grows)
  const IDLE = 180000;  // ms a section worker waits unused before it's let go
  // ms a worker may go without a word before it's given up on (a hidden tab's worker runs several times slower, so
  // these watch for a stall, not the whole time), and the most a render may take in all
  const TIMEOUT = { ready: 180000, section: 300000, whole: 600000, total: 2400000 };
  const KEEP = { section: 16, whole: 3 };  // songs made here, kept to play again at once
  const MiB = 2 ** 20;

  // ---------------------------------------------------------------- where a song is made

  function environment() {
    const nav = typeof navigator === "object" ? navigator : {};
    const ua = nav.userAgent || "";
    const mobile = nav.userAgentData?.mobile ?? /Android|iPhone|iPad|iPod|Mobile|Silk|Kindle/i.test(ua);
    const ipad = /Macintosh/.test(ua) && (nav.maxTouchPoints || 0) > 1;  // an iPad says it's a Mac
    const small = typeof screen === "object" && Math.min(screen.width || 1e4, screen.height || 1e4) < 600;
    return { wasm: typeof WebAssembly === "object", worker: typeof Worker === "function",
      mobile: !!mobile || ipad || small, memory: typeof nav.deviceMemory === "number" ? nav.deviceMemory : null };
  }

  // Whether this browser should make the song, and why not: pure, for the tests.
  function capable(env, bundle) {
    if (!bundle) return { ok: false, why: "this studio makes every song itself" };
    if (!env.wasm || !env.worker) return { ok: false, why: "this browser can't run the singer" };
    if (env.mobile) return { ok: false, why: "phones and tablets have the server make it" };
    if (env.memory !== null && env.memory < 4) return { ok: false, why: "this computer has little memory to spare" };
    return { ok: true, why: "" };
  }

  // Where one render goes: "browser" or "server", with the reason (the setting, then what the browser can do,
  // then what went wrong earlier in the visit).
  function choose(mode, env, bundle, failures, size) {
    if (mode === "server") return { where: "server", why: "you chose the server" };
    if (!bundle) return { where: "server", why: "this studio makes every song itself" };
    if (!env.wasm || !env.worker) return { where: "server", why: "this browser can't run the singer" };
    if (failures.visit) return { where: "server", why: "this browser couldn't make it earlier" };
    if (size === "whole" && failures.whole) return { where: "server", why: "a whole song didn't fit in this browser" };
    if (mode === "browser") return { where: "browser", why: "you chose this browser" };
    const can = capable(env, bundle);
    return can.ok ? { where: "browser", why: "" } : { where: "server", why: can.why };
  }

  // On the device: what went wrong, in the simplest true words, and what may help (never "your phone can't").
  const MAKING = "songbird-making-whole";
  function plainly(e) {
    const message = String((e && e.message) || e || "");
    if (e && e.memory) return "it ran out of memory in this browser. A shorter version (fewer verses, a quicker tempo) may fit, or a computer.";
    if (e && e.timeout) return "it stopped making progress. Try again, or a shorter version, or a computer.";
    if (/worker (was )?stopped/i.test(message)) return "the browser stopped it, perhaps for want of memory. A shorter version (fewer verses, a quicker tempo) may fit, or a computer.";
    return `it went wrong in this browser (${message.slice(0, 200)}). Try again, or a shorter version, or a computer.`;
  }
  function onDevice() {
    if (typeof document === "undefined") return false;
    try { return document.querySelector('meta[name="studio-render"]')?.content === "device"; } catch (e) { return false; }
  }

  // ---------------------------------------------------------------- the browser's workers
  // One render at a time. A section's worker is kept for a few sections, then replaced; a whole song gets a worker
  // of its own (and the section's goes first: two heaps at once is too much), terminated when it's done.

  const later = (f, ms) => { const t = setTimeout(f, ms); t?.unref?.(); return t; };  // (node: never held open)

  function workers({ spawn, bundle, timeouts = TIMEOUT, uses = SECTION_USES, idle = IDLE, schedule = later,
                     unschedule = clearTimeout, storage = null, maxHeap = 768, stemCacheBytes = 64 * 2 ** 20 }) {
    let kept = null;  // the section worker: { w, ready, uses, timer }
    let current = null;  // what is being made: { entry, reject }
    let chain = Promise.resolve();
    const origin = typeof location === "object" && location.href ? location.href : "http://localhost/";
    const at = (folder) => new URL(`${bundle.base}${folder}/`, origin).href;
    const fetchedBefore = () => { try { return storage?.getItem(FETCHED) === bundle.app; } catch (e) { return false; } };

    function open() {
      const w = spawn(`${at(bundle.app)}studio-worker.mjs`);
      const entry = { w, uses: 0, timer: null, listener: null, dead: false };
      w.onmessage = (e) => entry.listener?.(e.data);
      w.onerror = (e) => entry.listener?.({ kind: "error", message: e?.message || "the worker stopped", memory: false });
      w.onmessageerror = w.onerror;
      entry.ready = new Promise((resolve, reject) => {
        entry.listener = (m) => {
          if (m.kind === "loading") entry.onLoading?.(m);
          else if (m.kind === "ready") {
            try { storage?.setItem(FETCHED, bundle.app); } catch (e) { /* only a convenience */ }
            resolve(m);
          } else if (m.kind === "error") reject(Object.assign(new Error(m.message), { memory: !!m.memory }));
        };
      });
      entry.ready.catch(() => {});
      w.postMessage({ cmd: "init", pyodide: at(bundle.pyodide), app: at(bundle.app), bytes: bundle.bytes, stemCacheBytes });
      return entry;
    }

    function close(entry) {
      if (!entry || entry.dead) return;
      entry.dead = true;
      unschedule(entry.timer);
      entry.w.terminate();
      if (kept === entry) kept = null;
    }

    // a promise that fails if poke() isn't called for ms (or ever, past total): a worker stalled or gone
    function watch(ms, what, total = timeouts.total || Infinity) {
      let timer, fail;
      const began = Date.now();
      const stalled = new Promise((_, reject) => { fail = reject; });
      stalled.catch(() => {});
      const poke = () => {
        unschedule(timer);
        const left = Math.min(ms, total - (Date.now() - began));
        timer = schedule(() => fail(Object.assign(new Error(`${what} took too long`), { timeout: true })), Math.max(0, left));
      };
      poke();
      return { stalled, poke, stop: () => unschedule(timer) };
    }

    async function make(spec, size, hear, task) {
      if (task?.cancelled) throw Object.assign(new Error("cancelled"), { cancelled: true });
      let entry;
      if (size === "whole") {
        close(kept);
        entry = open();
      } else {
        if (!kept || kept.uses >= uses) { close(kept); kept = open(); }
        entry = kept;
        unschedule(entry.timer);
      }
      const first = !fetchedBefore();
      const loading = watch(timeouts.ready, "getting the singer ready");
      entry.onLoading = (m) => { loading.poke(); hear({ kind: "loading", first, received: m.received, bytes: m.bytes }); };
      let making = null;
      const stopped = new Promise((_, reject) => { current = { entry, reject, task }; });
      stopped.catch(() => {});
      try {
        const ready = await Promise.race([entry.ready, loading.stalled, stopped]);
        loading.stop();
        hear({ kind: "ready", seconds: ready.seconds });
        making = watch(timeouts[size], "making it");
        entry.uses += 1;
        const made = new Promise((resolve, reject) => {
          entry.listener = (m) => {
            if (m.kind === "progress") { making.poke(); hear(m); }
            else if (m.kind === "done") resolve(m);
            else if (m.kind === "error") reject(Object.assign(new Error(m.message), { memory: !!m.memory }));
          };
        });
        entry.w.postMessage({ cmd: "render", spec });
        const out = await Promise.race([made, making.stalled, stopped]);
        // wasm heaps never shrink: an unusually large section mustn't keep its heap for the next few previews.
        if (out.heap > maxHeap) close(entry);
        out.ready = ready.seconds;
        return out;
      } catch (e) {
        close(entry);  // whatever went wrong, this worker is done
        throw e;
      } finally {
        loading.stop();
        making?.stop();
        current = null;
        if (size === "whole") close(entry);
        else if (!entry.dead) entry.timer = schedule(() => close(entry), idle);
      }
    }

    return {
      render(spec, size, hear, task) {
        const run = chain.then(() => make(spec, size, hear, task));
        chain = run.catch(() => {});
        return run;
      },
      // stop what is being made (a whole song cancelled; or, for the tests, the worker killed mid-render)
      kill(why = "the worker was stopped", task = null) {
        if (!current || (task && current.task !== task)) return false;
        const { entry, reject } = current;
        close(entry);
        reject(new Error(why));
        return true;
      },
      busy: () => current !== null,
      close() { close(kept); },
    };
  }

  // ---------------------------------------------------------------- the renderer the page uses

  const shared = {  // one per page: the bundle, the workers, what went wrong, what was made here
    bundle: undefined, found: null, browser: null, failures: { count: 0, whole: false, visit: false },
    made: [], cache: new Map(), recording: null, playing: null, retired: new Set(), mode: null, listeners: new Set(),
  };

  function storageOf(options) {
    if (options.storage !== undefined) return options.storage;
    try { return typeof localStorage === "object" ? localStorage : null; } catch (e) { return null; }
  }

  function modeOf(storage) {
    if (shared.mode) return shared.mode;
    try {
      const saved = storage?.getItem(SETTING);
      return MODES.includes(saved) ? saved : "auto";
    } catch (e) { return "auto"; }
  }

  // whether the studio serves the browser's bundle at all (the server marks its page: studio.py); a local studio
  // doesn't, and isn't asked
  function offered() {
    if (typeof document === "undefined") return true;  // not a page (the tests): ask as told
    try { return !!document.querySelector('meta[name="studio-render"]'); } catch (e) { return false; }
  }
  function discover(get) {  // the bundle the studio serves, asked once
    if (!shared.found) {
      shared.found = Promise.resolve().then(get).then((b) => (b && b.app && b.pyodide ? b : null), () => null)
        .then((b) => { shared.bundle = b; changed(); return b; });
    }
    return shared.found;
  }

  function changed() { for (const f of shared.listeners) { try { f(); } catch (e) { /* a view's own trouble */ } } }

  function note(entry) {
    shared.made.push(entry);
    if (shared.made.length > 50) shared.made.shift();
    changed();
  }

  function forget(key) {
    const job = shared.cache.get(key);
    if (!job) return;
    shared.cache.delete(key);
    if (shared.recording === job) shared.recording = null;
    // the page's player may still be on it (a seek in a revoked file stalls without a word): let go when it moves on
    if (job.url === shared.playing) shared.retired.add(job.url);
    else revoke(job.url);
  }

  function revoke(url) {
    try { URL.revokeObjectURL(url); } catch (e) { /* already gone */ }
  }

  // The page says which file its player has (studio.js's play()); one forgotten while it played is released now.
  function playing(url) {
    shared.playing = url || null;
    for (const old of shared.retired) {
      if (old !== shared.playing) { shared.retired.delete(old); revoke(old); }
    }
  }

  function remember(key, job, size, budget, recording) {
    forget(key);
    shared.cache.set(key, job);
    if (recording) shared.recording = job;  // the visible recording's Download and Play buttons still use this URL
    trim(key, size, budget);
  }

  function trim(key, size, budget) {
    const mine = [...shared.cache].filter(([, j]) => j.size === size);
    while (mine.length > KEEP[size]) {
      const at = mine.findIndex(([, j]) => j !== shared.recording);
      const [old] = mine.splice(at, 1)[0];
      forget(old);
    }
    // Counts alone let long recordings hold hundreds of MB. Keep the newest result and visible recording usable
    // even when they exceed the budget, and let go of older files in least-recently-used order across both kinds.
    let bytes = [...shared.cache.values()].reduce((n, j) => n + (j.bytes || 0), 0);
    while (bytes > budget && shared.cache.size > 1) {
      const candidate = [...shared.cache].find(([old, j]) => old !== key && j !== shared.recording);
      if (!candidate) break;
      const [old, j] = candidate;
      bytes -= j.bytes || 0;
      forget(old);
    }
  }

  function create(ask, options = {}) {
    const pause = options.wait || wait;
    const env = options.env || environment();
    const constrained = env.mobile || (env.memory !== null && env.memory < 4);
    const cacheBytes = options.cacheBytes ?? (constrained ? 64 : 192) * MiB;
    const storage = storageOf(options);
    const spawn = options.spawn || (typeof Worker === "function" ? (url) => new Worker(url, { type: "module" }) : null);
    const blob = options.blob || ((bytes) => URL.createObjectURL(new Blob([bytes], { type: "audio/flac" })));
    const device = options.device ?? onDevice();  // no server: every song is made here

    function follow(task, path, body, onProgress) {
      return (async () => {
        let job = await ask(path, body);
        for (;;) {
          task.job = job;
          if (task.cancelled) return job;
          if (job.state === "done" || job.state === "failed") return Object.assign(job, { where: "server" });
          onProgress?.(job);
          await pause(POLL[task.kind]);
          if (task.cancelled) return job;
          job = await ask(`/api/job/${job.id}`);
        }
      })();
    }

    async function decide(size) {
      if (!spawn || !env.worker) return { where: "server", why: "this browser can't run the singer" };
      const mode = modeOf(storage);
      if (mode === "server") return { where: "server", why: "you chose the server" };
      const bundle = offered() ? await discover(() => ask("/render/bundle.json")) : null;
      return choose(mode, env, bundle, shared.failures, size);
    }

    async function inBrowser(task, body, size, onProgress) {
      const answer = await ask("/api/render/spec", body);
      // the server has made it already (it plays at once from there), or it's too long for a browser's memory
      // and the server can make it: the server's, as ever
      if (!device && (answer.made || answer.server)) return null;
      // too long for a browser and for the server: said, and made nowhere (never sent to the server to fail there)
      if (!device && answer.too_long) return { state: "failed", error: answer.too_long, key: answer.key, where: "browser", size };
      const hit = shared.cache.get(answer.key);
      if (hit) {  // a file heard again stays ahead of an older one when the cache needs room
        shared.cache.delete(answer.key);
        shared.cache.set(answer.key, hit);
        if (task.kind === "record") shared.recording = hit;
        trim(answer.key, hit.size, cacheBytes);
        return hit;
      }
      if (!answer.spec) throw new Error("the studio didn't say what to make");
      if (!shared.browser) shared.browser = workers({ spawn, bundle: shared.bundle, storage,
        maxHeap: constrained ? 512 : 768, stemCacheBytes: (constrained ? 32 : 128) * MiB, ...(options.workers || {}) });
      const label = answer.label || (size === "whole" ? "The whole song" : "Song section");
      // on the device, a whole song estimated past a browser's memory is made all the same, with a word of warning
      const warn = device && answer.warn ? ` (${answer.warn})` : "";
      const say = (job) => { task.job = warn ? { ...job, stage: `${job.stage}${warn}` } : job; if (!task.cancelled) onProgress?.(task.job); };
      say({ state: "running", progress: 0, stage: "getting the singer ready", label, where: "browser" });
      const out = await shared.browser.render(answer.spec, size, (m) => {
        if (m.kind === "loading") {
          const mb = (n) => Math.round((n || 0) / 2 ** 20);
          const fetching = m.first && m.bytes ? ` (once: ${mb(Math.min(m.received, m.bytes))} of ${mb(m.bytes)} MB)` : "";
          say({ state: "running", progress: 0, stage: `getting the singer ready${fetching}`, label, where: "browser" });
        } else if (m.kind === "ready") {
          say({ state: "running", progress: 0.01, stage: "singing in this browser", label, where: "browser" });
        } else if (m.kind === "progress") {
          say({ state: "running", progress: m.progress, stage: m.stage, label, where: "browser" });
        }
      }, task);
      // the file itself is kept too, for a recording someone shares (device.js: sent as it is)
      const file = !options.blob && typeof Blob === "function" ? new Blob([out.flac], { type: "audio/flac" }) : null;
      const url = file ? URL.createObjectURL(file) : blob(out.flac);
      const clock = answer.bar_seconds ? { bar_seconds: answer.bar_seconds } : {};  // a whole song's, as the server's job ends
      const job = { state: "done", progress: 1, url, key: answer.key, label, where: "browser", id: out.id, size,
        seconds: out.seconds, heap: out.heap, bytes: out.flac.byteLength, result: { duration: out.duration, ...clock } };
      if (size === "whole" && out.record) {
        const n = answer.name || {};
        const name = `${n.song || "song"}.${(out.record.rendered_at || n.day || "").slice(0, 10)}.${out.id.slice(0, 6)}.flac`;
        job.result = { recorded: { flac: name, name, id: out.id, duration: out.duration, shared: true, browser: true,
          generation: out.record.generation, yours: out.record.yours, next: `python3 ${name} studio`, download: url,
          program: out.record.program_sha256, device, file }, ...clock };
      }
      remember(answer.key, job, size, cacheBytes, task.kind === "record");
      return job;
    }

    // On the device: always here, every browser trying; what went wrong said plainly (there's no server to ask)
    function onThisDevice(task, body, size, onProgress) {
      task.where = "browser";
      const failed = (error) => (task.job = { state: "failed", error, where: "browser", size });
      task.done = (async () => {
        if (!spawn || !env.worker || !env.wasm) {
          return failed("this browser can't run the singer (it needs WebAssembly and workers). Another browser, or a computer, may.");
        }
        const began = Date.now();
        const marking = size === "whole";
        try {
          if (!shared.bundle) await discover(() => ask("/render/bundle.json"));
          if (!shared.bundle) return failed("the singer's files couldn't be fetched. Reload the page to try again.");
          if (marking) { try { storage?.setItem(MAKING, String(began)); } catch (e) { /* only a convenience */ } }
          const job = await inBrowser(task, { edits: body.edits, who: body.who || "you", section: body.section ?? null },
            size, onProgress);
          note({ kind: task.kind, size, key: job.key, where: "browser", id: job.id, seconds: job.seconds, at: began });
          return (task.job = job);
        } catch (e) {
          if (task.cancelled || e.cancelled) return task.job || failed("cancelled");
          note({ kind: task.kind, size, where: "browser", failed: String(e.message || e), at: began });
          return failed(plainly(e));
        } finally {
          if (marking) { try { storage?.removeItem(MAKING); } catch (e) { /* only a convenience */ } }
        }
      })();
      return task;
    }

    function run(kind, path, body, size, onProgress) {
      const task = { kind, size, job: null, cancelled: false, where: null };
      const server = async (instead = false) => {
        // after the browser couldn't, what the server is doing says it's the server's doing
        const hear = instead && onProgress
          ? (job) => onProgress({ ...job, stage: `${job.stage || "making it"} on the server` }) : onProgress;
        const job = await follow(task, path, kind === "record" ? { edits: body.edits } : body, hear);
        if (job.state === "done") {
          if (kind === "record" && shared.recording) forget(shared.recording.key);
          note({ kind, size, key: job.key, where: "server", at: Date.now() });
        }
        return job;
      };
      if (device) return onThisDevice(task, body, size, onProgress);
      // settled already (no worker here, the server chosen, or no bundle served): asked at once, as ever
      if (!spawn || !env.worker || modeOf(storage) === "server" || shared.bundle === null) {
        task.where = "server";
        task.done = server();
        return task;
      }
      task.done = (async () => {
        const choice = await decide(size);
        task.where = choice.where;
        if (choice.where === "browser" && !task.cancelled) {
          const began = Date.now();
          try {
            const job = await inBrowser(task, { edits: body.edits, who: body.who || "you", section: body.section ?? null },
              size, onProgress);
            if (job?.state === "failed") return (task.job = job);  // too long to make anywhere: said
            if (job) {
              note({ kind, size, key: job.key, where: "browser", id: job.id, seconds: job.seconds, at: began });
              return (task.job = job);
            }
          } catch (e) {
            if (task.cancelled || e.cancelled) return task.job || { state: "failed", error: "cancelled" };
            const f = shared.failures;
            f.count += 1;
            if (e.memory && size === "whole") f.whole = true;
            if (f.count >= 2) f.visit = true;
            note({ kind, size, where: "browser", failed: String(e.message || e), at: began });
            task.where = "server";
            onProgress?.({ state: "running", progress: 0, where: "server",
              stage: "this browser couldn't make it, so the server is" });
            return server(true);
          }
        }
        return server();
      })();
      return task;
    }

    return {
      get where() { return modeOf(storage); },
      preview: ({ edits, who = "you", section = null }, onProgress) =>
        run("preview", "/api/listen", { edits, who, section }, section === null ? "whole" : "section", onProgress),
      record: ({ edits }, onProgress) => run("record", "/api/record", { edits, who: "you", section: null }, "whole", onProgress),
      cancel(task) {
        if (!task || task.cancelled) return;
        task.cancelled = true;
        // in this browser: a whole song being made is stopped (a section finishes, and is kept to play at once)
        if (task.where === "browser") {
          if (task.size === "whole") shared.browser?.kill("cancelled", task);
          return;
        }
        // on the server: a job still waiting its turn is dropped; one being made finishes into the cache
        if (task.job?.state === "queued" && task.job.id) Promise.resolve(ask("/api/cancel", { job: task.job.id })).catch(() => {});
      },
    };
  }

  // ---------------------------------------------------------------- the setting, in the Tools sheet
  // "Make the song: automatically · in this browser · on the server", shown only where the studio serves the
  // bundle, with a line saying where the last one was made. Kept here, so the rest of the page is as it was.

  function setMode(mode, storage = storageOf({})) {
    if (!MODES.includes(mode)) return;
    shared.mode = mode;
    try { storage?.setItem(SETTING, mode); } catch (e) { /* this visit only */ }
    changed();
  }

  function status(env = environment()) {
    const bundle = shared.bundle;
    if (!bundle) return "";
    const last = shared.made[shared.made.length - 1];
    const mode = modeOf(storageOf({}));
    const choice = choose(mode, env, bundle, shared.failures, "section");
    const now = choice.where === "browser"
      ? `This browser makes the song (the first time, it fetches the singer: about ${Math.round((bundle.transfer || bundle.bytes || 0) / 2 ** 20)} MB).`
      : `The server makes the song${choice.why ? `: ${choice.why}` : ""}.`;
    if (!last) return now;
    const what = last.size === "whole" ? "The last whole song" : "The last section";
    const said = last.failed ? `${what} couldn't be made in this browser, so the server made it.`
      : `${what} was made ${last.where === "browser" ? `in this browser${last.seconds ? ` (${last.seconds.toFixed(1)} s)` : ""}` : "on the server"}.`;
    return `${now} ${said}`;
  }

  function mount(doc = document) {
    const box = doc.getElementById?.("makeWhere");
    if (!box || typeof fetch !== "function") return;
    const show = () => {
      box.hidden = !shared.bundle || onDevice();  // on the device there's no choice: it's always made here
      const mode = modeOf(storageOf({}));
      for (const input of box.querySelectorAll("input[name=makeWhere]")) input.checked = input.value === mode;
      const line = doc.getElementById("makeWhereNote");
      if (line) line.textContent = status();
    };
    shared.listeners.add(show);
    box.addEventListener("change", (e) => { if (e.target?.name === "makeWhere") setMode(e.target.value); });
    if (offered()) discover(() => fetch("/render/bundle.json", { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : null)));
    show();
  }

  const api = { create, capable, choose, environment, workers, setMode, status, mount, shared, plainly, playing, MAKING,
    get made() { return shared.made; },
    debug: { kill: () => shared.browser?.kill() || false, busy: () => !!shared.browser?.busy() },
    reset() {  // a fresh page, for the tests
      shared.browser?.close();
      for (const key of shared.cache.keys()) forget(key);
      playing(null);
      Object.assign(shared, { bundle: undefined, found: null, browser: null, mode: null, made: [], cache: new Map(), recording: null,
        playing: null, retired: new Set(), failures: { count: 0, whole: false, visit: false } });
      shared.listeners.clear();
    } };
  if (typeof window !== "undefined") {
    window.SongbirdRenderer = api;
    if (typeof document === "object" && document.addEventListener) {
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => mount());
      else if (document.readyState) mount();
    }
  }
  if (typeof module === "object" && module.exports) module.exports = api;
})();
