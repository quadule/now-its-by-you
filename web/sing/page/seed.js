// The seed page's words, as the file sings them: a slim strip of the stage under the cover and the pitch, folded
// until the song plays. Playing, it shows the line being sung (each syllable filled as it is sung, as on the
// singing page) and the next under it, dimmed, at the same size; the next scrolls up into the first's place when
// its turn comes. Paused, it is a taller window to read and scroll. The words and their times are the render's
// own (tools/sing_site.py seed_words: /seed/words.json). And the song's name,
// who it's by and its cover for the phone's lock screen and the browser's media controls. And the steps to run
// the file as tabs, one for each kind of computer, opening on the visitor's own.

const HOLD = 0.1; // seconds a line stays once sung, before the next takes its place

const audio = document.getElementById("player");
const box = document.getElementById("lyric");

if (audio && box && box.dataset.words) {
  fetch(box.dataset.words)
    .then(r => (r.ok ? r.json() : null))
    .then(words => { if (words && Array.isArray(words.lines) && words.lines.length) follow(words.lines); })
    .catch(() => {}); // no words: the song plays as before
}

if (audio && "mediaSession" in navigator && typeof MediaMetadata === "function") {
  audio.addEventListener("play", () => {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: document.querySelector(".masthead h1").textContent.trim(),
      artist: document.querySelector(".masthead .kicker").textContent.trim(),
      artwork: [{ src: "/cover.jpg", sizes: "800x800", type: "image/jpeg" }],
    });
  });
}

// lines: [[start, end, [[text, start, end, wordEnd], ...]], ...], in seconds
// Every line is set once, one under another at one size, in a window that scrolls. Playing, the window is two lines
// tall, the line being sung at its top, lit, and the next under it, dimmed; when a line is done the window scrolls
// down by it, so the next rises into its place: always in order, and never changing size. A visitor who scrolls
// the words themselves is left to read for a few seconds before they follow the song again. The strip opens when
// the song starts, unless the visitor folded it while it played.
function follow(lines) {
  const view = document.createElement("div"), reel = document.createElement("div");
  view.className = "view";
  view.tabIndex = 0; // scrolled with the keys too
  view.setAttribute("aria-label", "The words, as they are sung");
  reel.className = "roll";
  const rows = lines.map(([, , syllables]) => {
    const p = document.createElement("p");
    p.className = "line";
    for (const [text, , , wordEnd] of syllables) {
      const s = document.createElement("span");
      s.className = "syl";
      s.textContent = text;
      p.append(s);
      if (wordEnd) p.append(" ");
    }
    reel.append(p);
    return p;
  });
  view.append(reel);
  box.append(view);
  let shown = -1, frame = 0, folded = false, reading = -Infinity;
  const READ = 4000; // ms a visitor's own scrolling holds the words still
  const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;

  // the line being sung, or the next to be (through the intro and between verses); the last once all are sung
  const at = t => {
    let i = 0;
    while (i < lines.length - 1 && lines[i][1] + HOLD < t) i++;
    return i;
  };

  // the window's height: two lines (line i and the one after) while the song plays, more to read while it doesn't
  const size = i => {
    if (audio.paused) return Math.min(reel.offsetHeight, Math.max(160, Math.round(innerHeight * 0.4)));
    const row = rows[i], after = rows[i + 1] || row;
    return after.offsetTop === row.offsetTop ? 2 * row.offsetHeight : after.offsetTop + after.offsetHeight - row.offsetTop;
  };

  // line i lit, the window sized, and scrolled to it unless the visitor is reading on their own
  const place = (i, jump) => {
    rows.forEach((r, k) => r.classList.toggle("on", k === i));
    if (!box.open) return;
    view.style.height = `${size(i)}px`;
    if (performance.now() - reading > READ) view.scrollTo({ top: rows[i].offsetTop, behavior: smooth && !jump ? "smooth" : "auto" });
  };

  const draw = () => {
    const t = audio.currentTime, i = at(t);
    if (i !== shown) {
      shown = i;
      place(i);
    }
    const spans = rows[i].children;
    lines[i][2].forEach(([, a, b], k) => {
      const p = Math.max(0, Math.min(1, (t - a) / Math.max(b - a, 0.05)));
      spans[k].style.setProperty("--p", `${(p * 100).toFixed(1)}%`);
    });
  };

  const run = () => {
    draw();
    frame = audio.paused ? 0 : requestAnimationFrame(run);
  };
  for (const ev of ["wheel", "touchmove", "keydown"]) view.addEventListener(ev, () => { reading = performance.now(); }, { passive: true });
  box.addEventListener("toggle", () => {
    if (box.open) { folded = false; reading = -Infinity; place(shown, true); }
    else if (!audio.paused) folded = true;
  });
  audio.addEventListener("play", () => {
    if (!box.open && !folded) box.open = true; // its toggle places the words
    reading = -Infinity;
    place(shown);
    if (!frame) frame = requestAnimationFrame(run);
  });
  audio.addEventListener("pause", () => place(shown));
  for (const ev of ["seeked", "ended", "loadedmetadata"]) audio.addEventListener(ev, () => { reading = -Infinity; draw(); place(shown, true); });
  addEventListener("resize", () => { if (shown >= 0) place(shown, true); }); // the lines wrap anew at another width

  box.hidden = false;
  draw();
}

// Running the file: the steps for Windows and for a Mac or Linux as tabs (the page has both, one after the other,
// for a browser without this script). It opens on the kind of computer the visitor is on; the arrow keys move
// between the tabs, as tabs do.
const os = document.getElementById("os");
if (os) {
  const tabs = [...os.querySelectorAll('[role="tab"]')];
  const show = (tab, focus) => {
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    }
    if (focus) tab.focus();
  };
  for (const [i, t] of tabs.entries()) {
    t.addEventListener("click", () => show(t));
    t.addEventListener("keydown", e => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      show(tabs[(i + step + tabs.length) % tabs.length], true);
    });
  }
  const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
  os.querySelector('[role="tablist"]').hidden = false;
  os.classList.add("tabbed");
  show(document.getElementById(/win/i.test(platform) ? "tab-windows" : "tab-unix"));
}

// The command to type, copied at a press: a button beside it where the browser can copy (shown only then), which
// says so for a moment once it has.
for (const cmd of document.querySelectorAll(".cmd")) {
  const button = cmd.querySelector(".copy"), text = cmd.querySelector("pre");
  if (!button || !text || !navigator.clipboard || !navigator.clipboard.writeText) continue;
  button.hidden = false;
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text.textContent.trim());
      button.textContent = "Copied";
    } catch (e) {
      button.textContent = "Couldn't copy";
    }
    clearTimeout(button.timer);
    button.timer = setTimeout(() => { button.textContent = "Copy"; }, 2000);
  });
}
