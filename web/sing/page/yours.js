// The singer's own page (web/sing), at /y/<sid>: what they sent, their version and vocals once the
// artist has made them, the dates that matter, and the two ways to take things back: withdrawing
// (everything, and the numbers taken from it; until singing closes) and deleting recordings (the
// sound only; until DELETE_BY). The sid in the address is the key: whoever has the link sees the
// page. Everything shown comes from /api/yours/<sid> and goes into the page as text, never as HTML.

const $ = id => document.getElementById(id);
const PACIFIC = "America/Los_Angeles";
const KINDS = { version: "Your version of the song", vocals: "Your vocals, on their own" };
const S = { sid: location.pathname.split("/")[2] || "", data: null, lists: "", busy: false, loaded: 0, clear: 0 };

/* ---------- the data ---------- */

async function api(method, path = "") {
  let r;
  try {
    r = await fetch(`/api/yours/${S.sid}${path}`, { method, cache: "no-store" });
  } catch (e) {
    throw Object.assign(new Error("offline"), { offline: true });
  }
  const data = await r.json().catch(() => ({}));
  if (r.ok) return data;
  throw Object.assign(new Error(data.message
    || (r.status === 429 ? "That's a lot of requests at once. Wait a minute, then try again."
      : data.error === "withdrawn" ? "You've already withdrawn."
      : `Something went wrong on the server (${r.status}). Try again in a minute.`)), { status: r.status });
}

async function load(first = false) {
  let data;
  try {
    data = await api("GET");
  } catch (e) {
    const why = e.offline ? "The page couldn't reach the server. Check your connection and reload it."
      : e.status === 404 ? "This page doesn't exist. Check the link in your email." : e.message;
    return first || e.status === 404 || e.status === 410 ? problem(why) : status(why, "warn"); // 410: they've withdrawn
  }
  S.data = { ...data, takes: data.takes || [], files: data.files || [], words: data.words || [] };
  S.loaded = Date.now();
  draw();
}

function problem(text) {
  $("loading").hidden = true;
  $("page").hidden = true;
  $("thanks").hidden = true;
  $("problem").hidden = false;
  $("contact").hidden = false;
  $("problemText").textContent = text;
}

/* ---------- words for times and sizes ---------- */

function parts(date, zone) { // "Sunday, September 27" and "10 PM" in a time zone (undefined: the viewer's own)
  const day = new Intl.DateTimeFormat("en-US", { timeZone: zone, weekday: "long", day: "numeric", month: "long" }).format(date);
  const time = new Intl.DateTimeFormat("en-US", { timeZone: zone, hour: "numeric", minute: "2-digit" }).format(date);
  // "10:00 PM" is written "10 PM", with a space that never breaks it across two lines
  return { day, time: time.replace(":00", "").replace(/\s+/g, "\u00a0") };
}

function when(iso) { // a moment in Pacific time, as the artist writes it, and in the viewer's own when that differs
  const date = new Date(iso);
  if (!iso || isNaN(date)) return null;
  const there = parts(date, PACIFIC), here = parts(date);
  return { ...there, local: here.day === there.day && here.time === there.time ? "" : `${here.day} at ${here.time}` };
}

function stamp(iso) { // when something arrived, in the viewer's own time: "September 26 at 4:15 PM"
  const date = new Date(iso);
  if (!iso || isNaN(date)) return "";
  return `${new Intl.DateTimeFormat("en-US", { day: "numeric", month: "long" }).format(date)} at ${parts(date).time}`;
}

function dayOf(iso) { // DELETE_BY as a date in Pacific time: "September 30"
  const date = new Date(iso);
  return !iso || isNaN(date) ? "" : new Intl.DateTimeFormat("en-US", { timeZone: PACIFIC, day: "numeric", month: "long" }).format(date);
}

function until(ms) { // "in 5 hours": no seconds ticking
  const m = Math.floor(ms / 60000), h = Math.floor(m / 60), plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  return m < 1 ? "in less than a minute" : m < 60 ? `in ${plural(m, "minute")}`
    : h < 2 ? `in 1 hour${m % 60 ? ` and ${plural(m % 60, "minute")}` : ""}` : h < 48 ? `in ${h} hours` : `in ${Math.floor(h / 24)} days`;
}

function length(seconds) {
  const s = Math.round(seconds);
  return !(s >= 0) ? "" : s < 60 ? `${s} s` : `${Math.floor(s / 60)} min${s % 60 ? ` ${s % 60} s` : ""}`;
}

function size(bytes) {
  return bytes > 0 ? `${Math.max(0.1, bytes / 1e6).toFixed(1)} MB` : "";
}

function sameSite(href) { // sing_more is a path on this site; anything else isn't linked
  if (typeof href !== "string" || !href) return "";
  try { const u = new URL(href, location.href); return u.origin === location.origin ? u.href : ""; } catch (e) { return ""; }
}

/* ---------- drawing ---------- */

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function say(p, parts) { // a line made of text and {b: "bold"} parts; none hides it
  p.hidden = !parts;
  p.replaceChildren(...(parts || []).map(x => typeof x === "string" ? x : el("strong", "", x.b)));
}

function draw() {
  const d = S.data, withdrawn = d.state === "withdrawn", deleted = d.state === "deleted";
  const has = d.takes.length + d.files.length > 0, deleteBy = dayOf(d.delete_by), closes = when(d.closes);
  const over = !d.can_withdraw; // singing has closed, by the server's clock rather than this device's
  $("loading").hidden = true;
  $("problem").hidden = true;
  $("page").hidden = false;
  $("thanks").hidden = false;
  $("contact").hidden = false;
  const name = String(d.name || "").trim();
  $("thanks").textContent = name ? `Thank you for singing, ${name}.` : "Thank you for singing.";

  say($("closes"), closes && !withdrawn && [`Singing ${over ? "closed" : "closes"} on `, { b: `${closes.day} at ${closes.time} Pacific` },
    closes.local && !over ? ` (${closes.local} your time)` : "", "."]);
  say($("deletes"), deleteBy && !withdrawn && !deleted && [`Your recordings${d.files.length ? ", version and vocals" : ""} are deleted by `,
    { b: deleteBy }, when(d.delete_by).local ? " (Pacific time)" : "", ".", has ? " Download anything you'd like to keep before then." : ""]);
  say($("stateNote"), withdrawn ? ["You've withdrawn. Everything you sent has been deleted, and the numbers taken from your singing are coming out of the song."]
    : deleted ? ["Your recordings and files have been deleted, as promised. Only the numbers taken from them remain, blended with everyone else's."]
    : null);
  const more = !withdrawn && sameSite(d.sing_more);
  $("singMore").hidden = !more;
  if (more) $("singMore").href = more;

  const lists = JSON.stringify([d.takes, d.files, d.words]);
  if (lists !== S.lists) { // redrawn only when they change, so a recording that's playing keeps playing
    S.lists = lists;
    drawTakes(d);
    drawFiles(d);
    drawWords(d);
  }
  $("takesBox").hidden = withdrawn || deleted;
  say($("takesNote"), !d.takes.length && [more ? "No takes yet. When you send one, it'll be here." : "No takes here."]);
  say($("limit"), more && d.limit > 0 && d.takes.length >= d.limit
    && [`You have ${d.takes.length} takes, the most you can keep at once. To sing another, delete one below first.`]);
  $("filesBox").hidden = withdrawn || deleted || !has;
  say($("filesNote"), !d.files.length && d.takes.length && [`Your version will appear here in a few days${deleteBy ? `, before ${deleteBy}` : ""}.`]);
  $("wordsBox").hidden = !d.words.length;

  $("mind").hidden = withdrawn;
  $("withdrawBox").hidden = !d.can_withdraw;
  $("deleteBox").hidden = !has;
  say($("mindText"), d.can_withdraw ? has && ["If you change your mind, there are two things you can do."]
    : ["Singing has closed and the song has been made from everyone's singing, so what you gave is part of it now."
      + (has && !deleted ? ` You can still delete your recordings${deleteBy ? ` until ${deleteBy}` : ""}.` : "")]);
  say($("deleteWhen"), d.can_withdraw && deleteBy && [`You can do this until ${deleteBy}, when they're deleted anyway.`]);
  $("private").hidden = withdrawn;
  countdown();
}

function drawTakes(d) {
  $("takes").replaceChildren(...d.takes.map(t => {
    const what = t.section == null ? "The whole song" : t.name || "Part of the song";
    const sent = stamp(t.received), title = sent ? `${what}, sent ${sent}` : what;
    const li = el("li"), head = el("p", "what", what);
    if (t.section != null && t.label) head.append(" ", el("span", "line", `“${t.label.replace(/[\s,;:.\u2013\u2014-]+$/, "")}…”`));
    li.append(head, el("p", "hint meta", [length(t.seconds), sent && `sent ${sent}`].filter(Boolean).join(" · ")));
    li.append(controls(`take/${encodeURIComponent(t.id)}`, title, () => removeTake(t, title)));
    return li;
  }));
}

function drawFiles(d) {
  $("files").replaceChildren(...d.files.map(f => {
    const what = f.about || KINDS[f.kind] || f.name, made = stamp(f.made);
    const type = (/\.(\w+)$/.exec(f.name) || ["", ""])[1].toUpperCase();
    const li = el("li");
    li.append(el("p", "what", what), el("p", "hint meta", [type, size(f.bytes), made && `made ${made}`].filter(Boolean).join(" · ")));
    li.append(controls(`file/${encodeURIComponent(f.name)}`, what));
    return li;
  }));
}

function drawWords(d) {
  $("words").replaceChildren(...d.words.map(w => {
    const li = el("li"), sent = stamp(w.at);
    li.append(el("p", "said", w.text));
    if (sent) li.append(el("p", "hint meta", `Sent ${sent}`));
    return li;
  }));
}

function button(text, label, onclick, cls = "") {
  const b = el("button", cls, text);
  b.type = "button";
  b.setAttribute("aria-label", label);
  b.onclick = onclick;
  return b;
}

function controls(path, title, remove) { // Play (an audio element made only when asked for), Download, and Delete for a take
  const url = `/api/yours/${S.sid}/${path}`;
  const box = el("div"), row = el("div", "row"), save = el("a", "button", "Download");
  save.href = `${url}?download=1`;
  save.setAttribute("download", "");
  save.setAttribute("aria-label", `Download ${title}`);
  const play = button("Play", `Play ${title}`, () => {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.preload = "none";
    audio.src = url;
    audio.setAttribute("aria-label", title);
    audio.onerror = () => {
      audio.remove();
      play.hidden = false;
      status("That recording didn't load. Reload the page to see what's here now.", "warn");
    };
    box.prepend(audio);
    play.hidden = true;
    audio.focus();
    audio.play().catch(() => {}); // pressed Play: if the browser wants another tap, the controls are there
  });
  row.append(play, save);
  if (remove) row.append(button("Delete", `Delete ${title}`, remove, "end"));
  box.append(row);
  return box;
}

document.addEventListener("play", e => { // one recording at a time
  for (const a of document.querySelectorAll("audio")) if (a !== e.target) a.pause();
}, true);

/* ---------- the countdown to when withdrawal closes ---------- */

function countdown() { // "Withdrawal closes in 5 hours, at 10 PM Pacific on Sunday, September 27."; how long is left
  const d = S.data, c = d && d.can_withdraw && when(d.closes);
  $("countdown").hidden = !c;
  if (!c) return Infinity;
  const left = new Date(d.closes) - Date.now();
  $("countdown").textContent = `Withdrawal closes ${left > 0 ? until(left) : "now"}, at ${c.time} Pacific on ${c.day}.`;
  return left;
}

// once a minute; past the deadline, the server says whether it has closed (at most once a minute, too)
setInterval(() => { if (countdown() <= 0 && !S.busy) load(); }, 60000);
document.addEventListener("visibilitychange", () => { // a phone pauses timers; a page left open for long is asked again
  if (document.hidden || !S.data || S.busy) return;
  if (countdown() <= 0 || Date.now() - S.loaded > 10 * 60000) load();
});

/* ---------- deleting and withdrawing ---------- */

function ask(title, text, yes) { // asked before anything is deleted; Cancel is where the focus starts
  const box = $("ask");
  if (typeof box.showModal !== "function") return Promise.resolve(confirm(`${title}\n\n${text}`));
  $("askTitle").textContent = title;
  $("askText").textContent = text;
  $("askYes").textContent = yes;
  box.showModal();
  return new Promise(resolve => { // the buttons answer it themselves, not through the dialog's close event
    const answer = sure => { box.onclose = null; if (box.open) box.close(); resolve(sure); };
    $("askYes").onclick = () => answer(true);
    $("askNo").onclick = () => answer(false);
    box.onclose = () => { if (!box.open) answer(false); }; // Esc, or a tap outside it
  });
}

function busy(on) {
  S.busy = on;
  $("page").setAttribute("aria-busy", String(on));
  for (const b of document.querySelectorAll("#page button")) b.disabled = on;
}

function status(text, kind = "") { // the line at the foot of the screen; what went well fades after a while
  const s = $("status");
  clearTimeout(S.clear);
  s.textContent = text;
  s.className = kind ? `toast ${kind}` : "toast";
  if (kind === "done") S.clear = setTimeout(() => { s.textContent = ""; }, 8000);
}

async function act(question, method, path, doing, done) {
  if (S.busy || !(await ask(...question))) return;
  busy(true);
  status(doing);
  try {
    await api(method, path);
    status(done, "done");
  } catch (e) {
    status(e.offline ? "The page couldn't reach the server. Check your connection and try again." : e.message, "warn");
    if (e.offline) return busy(false);
  }
  await load(); // whatever the server said, show what's there now
  busy(false);
}

function removeTake(t, title) {
  const files = S.data.files.length ? " Your version and vocals are deleted with it." : "";
  act(["Delete this take?", `${title}. Deleting it can't be undone, and the numbers already taken from it stay part of the song.${files}`, "Delete it"],
    "DELETE", `/take/${encodeURIComponent(t.id)}`, "Deleting that take…", "That take is deleted.");
}

$("deleteAll").onclick = () => {
  const d = S.data;
  act(["Delete all your recordings?", `Every take you sent${d.files.length ? ", and your version and vocals," : ""} will be deleted. This can't be undone. `
    + `The numbers already taken from your singing stay part of the song${d.can_withdraw ? " (withdrawing is what takes those out)" : ""}.`
    + (d.words.length ? " The words you sent are kept." : ""), "Delete them all"],
    "POST", "/delete", "Deleting your recordings…", "Your recordings are deleted.");
};

$("withdraw").onclick = () => act(["Withdraw from the song?", "Everything you sent will be deleted (your recordings, your version and vocals, "
  + "and your words), and the numbers taken from your singing will come out of the song. This can't be undone.", "Withdraw"],
  "POST", "/withdraw", "Withdrawing…", "You've withdrawn.");

if (/^[A-Za-z0-9_-]{24}$/.test(S.sid)) load(true);
else problem("This page doesn't exist. Check the link in your email.");
