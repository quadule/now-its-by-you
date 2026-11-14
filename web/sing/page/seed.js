// The seed page's words, as the file sings them: under the player, a slim strip of the stage with the line being
// sung (each syllable filled as it is sung, as on the singing page) and the next under it, dimmed, at the same
// size; the next slides up into the first's place when its turn comes. The words and
// their times are the render's own (tools/sing_site.py seed_words: /seed/words.json). And the song's name,
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
// Every line is set once, one under another at one size, in a reel behind a window two lines tall: the line being
// sung at the top, lit, and the next under it, dimmed. When a line is done the reel slides up by that line, so
// the next rises into its place as it brightens: always in order, top to bottom, and never changing size.
function follow(lines) {
  const view = document.createElement("div"), reel = document.createElement("div");
  view.className = "view";
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
  box.replaceChildren(view);
  let shown = -1, frame = 0;

  // the line being sung, or the next to be (through the intro and between verses); the last once all are sung
  const at = t => {
    let i = 0;
    while (i < lines.length - 1 && lines[i][1] + HOLD < t) i++;
    return i;
  };

  // the reel moved so line i is at the top of the window, the window as tall as that line and the one after
  const place = i => {
    const row = rows[i], after = rows[i + 1] || row;
    rows.forEach((r, k) => r.classList.toggle("on", k === i));
    reel.style.transform = `translateY(${-row.offsetTop}px)`;
    view.style.height = `${after.offsetTop === row.offsetTop ? 2 * row.offsetHeight : after.offsetTop + after.offsetHeight - row.offsetTop}px`;
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
  audio.addEventListener("play", () => { if (!frame) frame = requestAnimationFrame(run); });
  for (const ev of ["pause", "seeked", "ended", "loadedmetadata"]) audio.addEventListener(ev, draw);
  addEventListener("resize", () => { if (shown >= 0) place(shown); }); // the lines wrap anew at another width

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
