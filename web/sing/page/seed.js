// The seed page's words, as the file sings them: under the player, a slim strip of the stage with the line
// being sung (each syllable filled as it is sung, as on the singing page) and the next, dimmed. The words and
// their times are the render's own (tools/sing_site.py seed_words: /seed/words.json). And the song's name,
// who it's by and its cover for the phone's lock screen and the browser's media controls.

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
function follow(lines) {
  const now = box.querySelector(".now"), next = box.querySelector(".next");
  let shown = -1, frame = 0;

  // a line as syllables to fill, a space after each word's last
  const line = i => {
    const out = document.createDocumentFragment();
    for (const [text, , , wordEnd] of lines[i][2]) {
      const s = document.createElement("span");
      s.className = "syl";
      s.textContent = text;
      out.append(s);
      if (wordEnd) out.append(" ");
    }
    return out;
  };

  // the line being sung, or the next to be (through the intro and between verses); the last once all are sung
  const at = t => {
    let i = 0;
    while (i < lines.length - 1 && lines[i][1] + HOLD < t) i++;
    return i;
  };

  const draw = () => {
    const t = audio.currentTime, i = at(t);
    if (i !== shown) {
      shown = i;
      now.replaceChildren(line(i));
      next.replaceChildren(i + 1 < lines.length ? line(i + 1) : "");
    }
    const spans = now.children;
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

  box.hidden = false;
  draw();
}
