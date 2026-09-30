// The renderer: how a section's preview and a whole recording are made, behind one small interface, so the page
// doesn't care where the singing is made. Today it is the studio's server (its one queue: /api/listen, /api/record,
// /api/job, /api/cancel); a later step can make a section in the visitor's own browser (web/studio-wasm,
// docs/BROWSER-RENDER.md) and fall back to this one. Plain JavaScript, no libraries.
//
//   const r = SongbirdRenderer.create(ask)        ask(path, body) -> Promise of the answer (the page's api())
//   const task = r.preview({ edits, who, section }, onProgress)    a section (a number) or the whole song (null)
//   const task = r.record({ edits }, onProgress)                   the whole rendition, as one file
//   r.cancel(task)                                                 stop waiting; a job still queued is dropped
//   task.done    -> Promise of the last job: { state: "done", url, key, label, result } or { state: "failed", error }
//   task.job     the job as last heard; onProgress(job) hears each: { state: "queued" | "running", ahead, eta, stage,
//                progress 0..1 } (ahead and eta only where the queue is shared: a public studio)
"use strict";

(() => {
  const POLL = { preview: 450, record: 600 };  // ms between asking how a job is going
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function create(ask, options = {}) {
    const pause = options.wait || wait;
    function follow(kind, path, body, onProgress) {
      const task = { kind, job: null, cancelled: false };
      task.done = (async () => {
        let job = await ask(path, body);
        for (;;) {
          task.job = job;
          if (task.cancelled) return job;
          if (job.state === "done" || job.state === "failed") return job;
          onProgress?.(job);
          await pause(POLL[kind]);
          if (task.cancelled) return job;
          job = await ask(`/api/job/${job.id}`);
        }
      })();
      return task;
    }
    return {
      where: "server",
      preview: ({ edits, who = "you", section = null }, onProgress) =>
        follow("preview", "/api/listen", { edits, who, section }, onProgress),
      record: ({ edits }, onProgress) => follow("record", "/api/record", { edits }, onProgress),
      cancel(task) {
        if (!task || task.cancelled) return;
        task.cancelled = true;
        // a job still waiting its turn is dropped; one being made finishes into the cache (the next ask is instant)
        if (task.job?.state === "queued" && task.job.id) Promise.resolve(ask("/api/cancel", { job: task.job.id })).catch(() => {});
      },
    };
  }

  const api = { create };
  if (typeof window !== "undefined") window.SongbirdRenderer = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})();
