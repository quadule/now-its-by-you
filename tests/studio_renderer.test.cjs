// The renderer (songbird/studio/renderer.js): previews and recordings behind one interface. Run with node --test.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { create } = require("../songbird/studio/renderer.js");

function server(answers) {
  const asked = [];
  const ask = async (path, body) => { asked.push([path, body]); return answers.shift(); };
  return { ask, asked };
}
const now = () => Promise.resolve();

test("a preview waits its turn, is made, and ends with its file; each step is heard", async () => {
  const { ask, asked } = server([{ id: "j1", state: "queued", ahead: 2 }, { id: "j1", state: "running", progress: 0.5 },
    { id: "j1", state: "done", url: "/audio/a.flac", key: "k" }]);
  const heard = [];
  const task = create(ask, { wait: now }).preview({ edits: { tempo: 100 }, section: 2 }, (job) => heard.push(job.state));
  const job = await task.done;
  assert.equal(job.url, "/audio/a.flac");
  assert.deepEqual(heard, ["queued", "running"]);
  assert.deepEqual(asked[0], ["/api/listen", { edits: { tempo: 100 }, who: "you", section: 2 }]);
  assert.equal(asked[1][0], "/api/job/j1");
});

test("a recording asks /api/record; a failure comes back as the job", async () => {
  const { ask, asked } = server([{ id: "r", state: "failed", error: "busy" }]);
  const job = await create(ask, { wait: now }).record({ edits: {} }).done;
  assert.equal(job.state, "failed");
  assert.equal(asked[0][0], "/api/record");
});

test("cancelling drops a job still waiting its turn, and stops asking", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const { ask, asked } = server([{ id: "q", state: "queued" }]);
  const r = create(ask, { wait: () => gate });
  const task = r.preview({ edits: {}, section: null });
  await new Promise((resolve) => setImmediate(resolve));
  r.cancel(task);
  release();
  const job = await task.done;
  assert.equal(job.state, "queued");
  assert.deepEqual(asked.map((a) => a[0]), ["/api/listen", "/api/cancel"]);
});
