// The home page's four studio pictures (web/sing/page/tab-page.webp, tab-arrange.webp, tab-mix.webp, tab-sing.webp),
// taken from the web studio served on this computer: one close crop of each view with something being changed in it.
//
//   uv run python web/studio-wasm/tools/build_site.py renders/studio-site
//   uv run python web/studio-wasm/tools/serve_site.py renders/studio-site --port 8820 &
//   node tools/site_pictures.mjs http://127.0.0.1:8820/ /tmp/pictures          # page.png, arrange.png, mix.png, sing.png, at 2x
//   uv run python tools/site_pictures.py /tmp/pictures                         # each to 860 x 645 WebP in web/sing/page/
//
// Needs Node >= 22 and playwright where Node resolves it from this file (as tools/video/kit.mjs does). CHROMIUM, if
// set, is the browser to run (a Chromium other than the one that playwright installed).
import { chromium } from "playwright";
const [url, out] = process.argv.slice(2);
if (!url || !out) { console.error("usage: node tools/site_pictures.mjs URL OUT_DIR"); process.exit(2); }
const browser = await chromium.launch({ ...(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {}), headless: true, args: ["--autoplay-policy=no-user-gesture-required", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] });
const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2, colorScheme: "light" });
const page = await context.newPage();
page.on("pageerror", (e) => console.log("pageerror", e.message));
const wait = (ms) => page.waitForTimeout(ms);
const settle = async () => { await page.waitForFunction(() => typeof state !== "undefined" && state.view && !state.busy, null, { timeout: 120000 }); await wait(600); };
const tab = async (name) => { await page.evaluate((n) => [...document.querySelectorAll("[role=tab]")].find((t) => t.textContent.includes(n)).click(), name); await wait(500); };
const shot = async (name, clip) => { await page.screenshot({ path: `${out}/${name}.png`, clip }); console.log(name, JSON.stringify(clip)); };
const box = (sel) => page.evaluate((s) => { const r = document.querySelector(s).getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; }, sel);

await page.goto(url);
await settle();
await page.waitForFunction(() => Object.keys(state.optionsByKey || {}).length > 3, null, { timeout: 120000 });

// Page: the first refrain being edited (its fields, the legend, its words to swap)
await page.evaluate(() => { const sec = [...document.querySelectorAll("#page .sec")].find((s) => /Refrain 1/i.test(s.querySelector(".rubric").textContent)); sec.querySelector(".editbtn").click(); });
await wait(1200);
await page.evaluate(() => { document.activeElement?.blur(); document.querySelector("#page .is-writing").scrollIntoView({ block: "start" }); window.scrollBy(0, -70); });
await wait(400);
let b = await box("#page .is-writing");
await shot("page", { x: b.x - 14, y: b.y - 8, width: Math.min(b.width + 28, 700), height: Math.min(b.width + 28, 700) * 0.75 });
await page.evaluate(() => document.querySelector("#page .editbtn.on").click());

// Arrange: the first refrain selected, everyone in it playing hard
await tab("Arrange");
await page.waitForSelector("#grid [role=row]", { timeout: 60000 });
await page.evaluate(() => { const r = [...document.querySelectorAll("#grid .region, #grid [data-key^='region:']")].find((x) => /Refrain 1/i.test(x.textContent) || /refrain:0/.test(x.dataset.key || "")); r.click(); });
await wait(800);
await page.evaluate(() => [...document.querySelectorAll("#inspector .chip")].find((c) => c.textContent === "hard")?.click());
await settle(); await wait(1500);
await page.evaluate(() => window.scrollTo(0, 0));
b = await box("#grid");
await shot("arrange", { x: b.x, y: b.y, width: 640, height: 480 });
await page.evaluate(() => document.querySelector("#inspector .close")?.click());

// Mix: the whistle's fader moved, the voice's strip beside the players
await tab("Mix");
await page.evaluate(() => { commitEdits({ "band.whistle": 1.39 }, "Whistle up"); });
await settle(); await wait(1500);
const strips = await page.evaluate(() => [...document.querySelectorAll("#mix .strip")].map((s) => { const r = s.getBoundingClientRect(); return { name: s.querySelector(".nm").textContent, x: r.x, y: r.y, right: r.right, bottom: r.bottom }; }));
const from = strips.find((s) => /fiddle/i.test(s.name)), to = strips.find((s) => /Voice/.test(s.name));
const width = to.right - from.x + 16;
await shot("mix", { x: from.x - 8, y: from.y - 8, width, height: width * 0.75 });

// Sing: the lane while the first verse's guide plays
await page.evaluate(() => commitEdits({}, "Reset song"));
await settle();
await tab("Sing");
await wait(2500);
await page.evaluate(() => { if (!document.getElementById("singConsent").hidden) { document.getElementById("singAgree").click(); [...document.querySelectorAll("#singConsent button")].find((x) => /Start/.test(x.textContent)).click(); } });
await page.waitForFunction(() => !document.getElementById("singWork").hidden && !/Making/.test(document.getElementById("singStatus").textContent) && !document.getElementById("singRehearse").disabled, null, { timeout: 180000 });
await wait(1500);
await page.evaluate(() => document.getElementById("singRehearse").click());
await wait(11000);
b = await box("#singStage");
const w = Math.min(b.width, 640);
await shot("sing", { x: b.x, y: b.y, width: w, height: w * 0.75 });
await browser.close();
