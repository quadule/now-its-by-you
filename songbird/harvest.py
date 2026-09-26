"""Harvest: reduce this machine's context to a voice vector (milestone 3).

    harvest(without: set[str]) -> Voice

A machine's voice is a handful of coarse numbers read from its context: its
languages, its size, how old its files are, the colour of its screen, the
common words in its person's documents, the rhythm of their typing, and (one
day) its room. Each signal is read by one small function that collapses it to
a few bucketed numbers before anything else sees it; the raw material (file
names, paths, document text, images, keystrokes) never leaves that function
and is never printed, logged, cached or committed. The mappings are
many-to-one, so a voice can't be turned back into what it was read from.
docs/HARVEST.md lists exactly what is read and what it becomes.

Every signal can be left out (`without`); a missing signal is neutral, so a
locked-down machine still sings, closer to its parent. The voice is cached
in ~/.songbird/voice.json (or $SONGBIRD_HOME) holding only the reduced
numbers, so it stays the same from run to run until it is harvested again.
Its hash, which seeds the drift and the singer's body, is a hash of those
numbers alone.

`fictional(name)` makes up a plausible machine, the same one every time for a
name, so two machines can be heard side by side without two computers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, fields, replace
from functools import lru_cache
from pathlib import Path

import numpy as np

SIGNALS = ("tongue", "machine", "ages", "colour", "words", "hand", "room")
ALIASES = {  # what a person might call a signal when opting out of it
    "locale": "tongue", "language": "tongue", "keyboard": "tongue",
    "hardware": "machine", "cpu": "machine", "ram": "machine", "uptime": "machine",
    "files": "ages", "file-ages": "ages",
    "screen": "colour", "wallpaper": "colour", "color": "colour",
    "documents": "words", "vocabulary": "words",
    "typing": "hand", "keys": "hand",
    "mic": "room", "microphone": "room",
}


def signal_name(name: str) -> str:
    name = name.strip().lower()
    name = ALIASES.get(name, name)
    if name not in SIGNALS:
        raise ValueError(f"no signal called {name!r}; the signals are {', '.join(SIGNALS)}")
    return name


def _q(x: float, step: float, lo: float | None = None, hi: float | None = None) -> float:
    """x clipped and rounded to a step: the bucketing every reduction ends with."""
    if lo is not None:
        x = max(lo, x)
    if hi is not None:
        x = min(hi, x)
    return round(float(round(x / step) * step), 4)


def _shares(masses, units: int = 4) -> tuple[float, ...]:
    """Masses as shares in 1/units steps that sum to exactly 1 (largest remainder;
    a tie goes to the middle entry first, so an even spread stays balanced)."""
    m = np.asarray(masses, dtype=float)
    m = m / m.sum() if m.sum() > 0 else np.full(len(m), 1.0 / len(m))
    base = np.floor(m * units).astype(int)
    rest = m * units - base
    order = sorted(range(len(m)), key=lambda i: (-round(rest[i], 9), abs(i - (len(m) - 1) / 2)))
    for i in order[: units - base.sum()]:
        base[i] += 1
    return tuple(round(float(b) / units, 4) for b in base)


# ---------------------------------------------------------------- the reduced signals


@dataclass(frozen=True)
class Tongue:
    """Locale, system languages and keyboard layout, reduced to a language group."""

    inventory: str  # the phoneme inventory the voice's vowels come from, one of INVENTORIES
    family: str  # the mode family the tune is realized in, one of MODE_FAMILIES


@dataclass(frozen=True)
class Machine:
    """CPU count, memory and uptime, each a coarse bucket from 0 to 1. Uptime is
    read afresh at every render (it is how long the machine has gone without
    rest, not what it is); the rest is cached."""

    cores: float  # 0, .25, .5, .75, 1: up to 2, 4, 8, 16, more
    memory: float  # 0, .2 ... 1: up to 4, 8, 16, 32, 64 GB, more
    uptime: float  # 0, .5, 1: up less than a day, less than a week, longer


@dataclass(frozen=True)
class Ages:
    """How old the files under the home directory are."""

    median: float  # log10 of the median age in days, in quarter steps (2.5 is about ten months)
    spread: float  # the interquartile range of log10 ages, in quarter steps


@dataclass(frozen=True)
class Colour:
    """The screen: how light it is and where its colour sits."""

    brightness: float  # 0 dark to 1 light, in quarter steps
    warm: float  # share of colour in reds, oranges and yellows (the three shares sum to 1, in quarters)
    green: float  # in greens
    cool: float  # in blues and purples


@dataclass(frozen=True)
class Words:
    """The person's common words, projected onto the song's public word lists."""

    themes: dict  # theme -> share of the common words that fall in it (sum 1, 0.05 steps)
    era: float  # -1 old-fashioned words to 1 new ones, in quarter steps
    richness: float  # 0 to 1: how varied the vocabulary is, in tenths


@dataclass(frozen=True)
class Hand:
    """The rhythm of a typed line: the time between keys."""

    interval: int  # mean milliseconds between keys, in 20 ms steps
    unevenness: float  # their coefficient of variation, in tenths
    skew: float  # their skewness (a few long gaps among quick runs), in quarter steps


@dataclass(frozen=True)
class Room:
    """The room the machine sits in (from a clap or a short capture)."""

    rt60: float  # seconds to decay by 60 dB, in tenths
    tone: tuple  # relative level in the five bands of synth.room.BANDS, in tenths


KINDS = {"tongue": Tongue, "machine": Machine, "ages": Ages, "colour": Colour, "words": Words, "hand": Hand, "room": Room}


@dataclass(frozen=True)
class Voice:
    """A machine's voice: each signal's reduced numbers, None where it was left
    out or couldn't be read, and a salt: a random number drawn once when the
    machine is first harvested. Nothing else is in it.

    The hash that seeds the drift and the singer's body comes from the salt
    alone, so it says nothing about the signals (a hash of a few coarse
    numbers could be reversed by trying them all), two machines that happen
    to read the same still sing as two people, and harvesting again later
    moves the signals' traits without changing who is singing."""

    tongue: Tongue | None = None
    machine: Machine | None = None
    ages: Ages | None = None
    colour: Colour | None = None
    words: Words | None = None
    hand: Hand | None = None
    room: Room | None = None
    salt: str = ""

    def signals(self) -> dict:
        """The reduced numbers, as plain data."""
        out = {}
        for name in SIGNALS:
            value = getattr(self, name)
            out[name] = None if value is None else _plain(asdict(value))
        return out

    @property
    def hash(self) -> str:
        """16 hex digits from the salt (or, for a voice made by hand without one, from its numbers)."""
        text = f"songbird-voice|{self.salt}" if self.salt else json.dumps(self.signals(), sort_keys=True)
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    @property
    def neutral(self) -> bool:
        """No signal at all: the machine sings as its parent did."""
        return all(getattr(self, name) is None for name in SIGNALS)

    def to_dict(self) -> dict:
        return {"songbird_voice": 1, "hash": self.hash, "salt": self.salt, "signals": self.signals()}

    @classmethod
    def from_dict(cls, data: dict) -> Voice:
        """From a voice file, the cache, or a render's record (its "voice" block)."""
        if "signals" not in data and isinstance(data.get("voice"), dict):
            data = data["voice"]
        signals = data.get("signals", data)
        values = {}
        for name, kind in KINDS.items():
            spec = signals.get(name)
            if spec is None:
                continue
            known = {f.name for f in fields(kind)}
            spec = {k: tuple(v) if isinstance(v, list) else v for k, v in spec.items() if k in known}
            values[name] = kind(**spec)
        return cls(**values, salt=str(data.get("salt", "")))


def _plain(value):
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    return value


# ---------------------------------------------------------------- tongue: languages

# Language (ISO 639-1) -> the phoneme inventory, a broad group of vowel systems.
INVENTORIES = ("english", "germanic", "celtic", "romance", "slavic", "west_asian", "south_asian", "east_asian", "other")
LANGUAGES = {
    "en": "english",
    **dict.fromkeys(("de", "nl", "sv", "da", "no", "nb", "nn", "is", "af", "lb", "fy", "fo", "yi"), "germanic"),
    **dict.fromkeys(("ga", "gd", "cy", "br", "gv", "kw"), "celtic"),
    **dict.fromkeys(("fr", "it", "es", "pt", "ca", "ro", "gl", "oc", "eu", "el", "mt"), "romance"),
    **dict.fromkeys(("ru", "uk", "be", "pl", "cs", "sk", "sl", "hr", "sr", "bs", "bg", "mk", "lt", "lv"), "slavic"),
    **dict.fromkeys(("ar", "he", "fa", "tr", "ku", "az", "hy", "ka", "ps", "am", "kk", "uz"), "west_asian"),
    **dict.fromkeys(("hi", "bn", "ur", "pa", "gu", "mr", "ne", "si", "ta", "te", "kn", "ml", "or"), "south_asian"),
    **dict.fromkeys(("zh", "ja", "ko", "vi", "th", "lo", "km", "my", "id", "ms", "tl", "mn"), "east_asian"),
}
# Which modes each group's voice realizes the tune in, brightest first, and its home among them.
# Every family can reach the seed's own ionian, so no machine is shut out of how the song began.
MODE_FAMILIES = {
    "bright": (("lydian", "ionian", "mixolydian"), "ionian"),
    "folk": (("ionian", "mixolydian", "dorian", "aeolian"), "ionian"),
    "dark": (("ionian", "dorian", "aeolian", "phrygian"), "aeolian"),
}
FAMILY_OF = {
    "english": "folk", "celtic": "folk", "south_asian": "folk", "other": "folk",
    "germanic": "bright", "romance": "bright", "east_asian": "bright",
    "slavic": "dark", "west_asian": "dark",
}
# Keyboard layouts that name a language (macOS input source ids, X11 layouts), by fragment.
LAYOUTS = {
    "us": "en", "british": "en", "abc": "en", "australian": "en", "canadian": "en", "irish": "en", "gb": "en",
    "german": "de", "swiss": "de", "austrian": "de", "dutch": "nl", "swedish": "sv", "danish": "da",
    "norwegian": "no", "icelandic": "is", "french": "fr", "belgian": "fr", "italian": "it", "spanish": "es",
    "portuguese": "pt", "brazilian": "pt", "romanian": "ro", "greek": "el", "russian": "ru",
    "ukrainian": "uk", "polish": "pl", "czech": "cs", "slovak": "sk", "croatian": "hr", "serbian": "sr",
    "bulgarian": "bg", "lithuanian": "lt", "latvian": "lv", "finnish": "fi", "estonian": "et",
    "hungarian": "hu", "turkish": "tr", "arabic": "ar", "hebrew": "he", "persian": "fa",
    "hindi": "hi", "devanagari": "hi", "bengali": "bn", "tamil": "ta", "japanese": "ja", "kotoeri": "ja",
    "korean": "ko", "chinese": "zh", "scim": "zh", "tcim": "zh", "pinyin": "zh", "vietnamese": "vi",
    "thai": "th", "welsh": "cy", "gaelic": "gd", "irishextended": "ga",
}


def reduce_tongue(codes: list[str]) -> Tongue | None:
    """Language codes (en_US, de-CH, fr, ...) to one language group by vote;
    a tie goes to whichever came first (the system's own language)."""
    groups = []
    for code in codes:
        lang = re.split(r"[-_.@]", code.strip().lower())[0]
        if len(lang) in (2, 3) and lang.isalpha() and lang not in ("c", "posix"):
            groups.append(LANGUAGES.get(lang, "other"))
    if not groups:
        return None
    best = max(groups, key=lambda g: (groups.count(g), -groups.index(g)))
    return Tongue(inventory=best, family=FAMILY_OF[best])


def _run(*cmd: str) -> str | None:
    """A system command's output, or None; never a shell, a short timeout."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _languages() -> list[str]:
    """The system's languages, its locale and its keyboard layout, most telling first."""
    codes: list[str] = []
    if sys.platform == "darwin":
        out = _run("defaults", "read", "-g", "AppleLanguages") or ""
        codes += re.findall(r'"?([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*)"?\s*,?\s*\n', out)[:2]
        codes += [(_run("defaults", "read", "-g", "AppleLocale") or "").strip()]
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(var):
            codes.append(os.environ[var])
            break
    layout = _keyboard_layout()
    if layout:
        codes.append(layout)
    return [c for c in codes if c]


def _keyboard_layout() -> str | None:
    """The keyboard layout's language, if the layout names one."""
    text = None
    if sys.platform == "darwin":
        text = _run("defaults", "read", "com.apple.HIToolbox", "AppleCurrentKeyboardLayoutInputSourceID")
    elif sys.platform.startswith("linux"):
        out = _run("setxkbmap", "-query") or ""
        found = re.search(r"layout:\s*(\S+)", out)
        text = found.group(1).split(",")[0] if found else None
    elif sys.platform == "win32":
        try:
            import ctypes
            import locale

            langid = ctypes.windll.user32.GetKeyboardLayout(0) & 0xFFFF
            return locale.windows_locale.get(langid)
        except Exception:
            return None
    return layout_language(text) if text else None


def layout_language(text: str) -> str | None:
    """A keyboard layout's name (com.apple.keylayout.German, an X11 'de') to a language code."""
    text = text.strip().lower()
    if len(text) == 2 and text.isalpha():  # an X11 layout is often a country or language code already
        return LAYOUTS.get(text, text)
    for fragment, lang in sorted(LAYOUTS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"(?<![a-z]){fragment}(?![a-z])", text.replace("-", ".")):
            return lang
    return None


def tongue() -> Tongue | None:
    """Reads: the system's preferred languages and region (macOS preferences via
    `defaults`, or the LANG environment), and the keyboard layout's name.
    Keeps: one language group and its mode family."""
    return reduce_tongue(_languages())


# ---------------------------------------------------------------- machine: size and uptime


def reduce_machine(cores: int | None, memory: int | None, uptime: float | None) -> Machine | None:
    """Core count, memory in bytes and uptime in seconds to three coarse buckets."""
    if not cores and not memory:
        return None
    c = 0.5 if not cores else [n for n, top in enumerate((2, 4, 8, 16, 10**9)) if cores <= top][0] / 4
    gb = (memory or 0) / 2**30
    m = 0.5 if not memory else [n for n, top in enumerate((4, 8, 16, 32, 64, 10**9)) if gb <= top * 1.05][0] / 5
    u = 0.5 if uptime is None else (0.0 if uptime < 86400 else 0.5 if uptime < 7 * 86400 else 1.0)
    return Machine(cores=_q(c, 0.25), memory=_q(m, 0.2), uptime=u)


def _memory() -> int | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("page", ctypes.c_ulonglong), ("apage", ctypes.c_ulonglong),
                            ("virtual", ctypes.c_ulonglong), ("avirtual", ctypes.c_ulonglong), ("ext", ctypes.c_ulonglong)]

            status = Status(length=ctypes.sizeof(Status))
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return int(status.total)
        except Exception:
            return None
    return None


def _uptime() -> float | None:
    if sys.platform == "darwin":
        found = re.search(r"sec = (\d+)", _run("sysctl", "-n", "kern.boottime") or "")
        return time.time() - int(found.group(1)) if found else None
    if sys.platform.startswith("linux"):
        try:
            return float(Path("/proc/uptime").read_text().split()[0])
        except (OSError, ValueError, IndexError):
            return None
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
            return ctypes.windll.kernel32.GetTickCount64() / 1000.0
        except Exception:
            return None
    return None


def machine() -> Machine | None:
    """Reads: the number of CPU cores, the installed memory, the time since boot.
    Keeps: a bucket for each."""
    return reduce_machine(os.cpu_count(), _memory(), _uptime())


# ---------------------------------------------------------------- walking the home directory

PRIVATE = ("Desktop", "Documents", "Downloads")  # the home folders macOS asks permission for
MEDIA = ("Pictures", "Movies", "Music", "Videos")  # media libraries: never walked
SKIP_DIRS = {
    "Library", "Applications", "AppData", "OneDrive", "iCloudDrive", "Creative Cloud Files", "snap",
    "node_modules", "__pycache__", "site-packages", "venv", "env", "build", "dist", "target", "vendor",
    "Pods", "DerivedData", "Caches", "cache", "tmp", "temp",
}
BUNDLES = (".app", ".photoslibrary", ".bundle", ".framework", ".plugin", ".kext", ".xcodeproj", ".xcworkspace",
           ".musiclibrary", ".tvlibrary", ".imovielibrary", ".fcpbundle", ".lrlibrary", ".pkg", ".sparsebundle",
           ".vmwarevm", ".pvm", ".utm", ".photolibrary", ".aplibrary", ".logicx", ".band")


def _walk(root: Path, *, max_depth: int, private: bool, deadline: float, limit: int, top_level: bool = True):
    """Regular files under root, as os.DirEntry, depth first. Never follows a
    link, never enters hidden, system, media or package folders, stops at the
    deadline or the limit. Names are only used to decide where to go next."""
    stack = [(Path(root), 0)]
    seen = 0
    while stack:
        folder, depth = stack.pop()
        try:
            with os.scandir(folder) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            if time.monotonic() > deadline or seen >= limit:
                return
            name = entry.name
            if name.startswith(".") or entry.is_symlink():
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth >= max_depth or name in SKIP_DIRS or name.lower().endswith(BUNDLES):
                        continue
                    if top_level and depth == 0 and folder == Path(root):
                        if name in MEDIA or (name in PRIVATE and not private):
                            continue
                    stack.append((Path(entry.path), depth + 1))
                elif entry.is_file(follow_symlinks=False):
                    seen += 1
                    yield entry
            except OSError:
                continue


# ---------------------------------------------------------------- ages: how old the files are


def reduce_ages(ages_days) -> Ages | None:
    """File ages in days to the median and interquartile spread of their log10."""
    a = np.asarray(list(ages_days), dtype=float)
    if len(a) < 20:
        return None
    logs = np.log10(np.maximum(a, 1.0 / 24))
    q1, q2, q3 = np.quantile(logs, [0.25, 0.5, 0.75])
    return Ages(median=_q(q2, 0.25, -1.0, 5.0), spread=_q(q3 - q1, 0.25, 0.0, 4.0))


def ages(root: Path | None = None, *, private: bool = True, max_depth: int = 8, limit: int = 50_000,
         seconds: float = 4.0) -> Ages | None:
    """Reads: the modification time of up to 50,000 files under the home
    directory (hidden, system, media, package and code-dependency folders
    skipped; Desktop, Documents and Downloads only if private). Keeps: the
    median and spread of their ages. No name or path is kept."""
    root = Path(root) if root is not None else Path.home()
    now = time.time()
    deadline = time.monotonic() + seconds
    found = []
    for entry in _walk(root, max_depth=max_depth, private=private, deadline=deadline, limit=limit):
        try:
            found.append((now - entry.stat(follow_symlinks=False).st_mtime) / 86400.0)
        except OSError:
            continue
    return reduce_ages(found)


# ---------------------------------------------------------------- colour: the screen


def reduce_colour(rgb) -> Colour:
    """Pixels (any shape ending in 3, values 0..1) to mean brightness and the
    colour's mass in three hue bins, weighted by how saturated each pixel is."""
    px = np.asarray(rgb, dtype=float).reshape(-1, 3)
    r, g, b = px[:, 0], px[:, 1], px[:, 2]
    brightness = float(np.mean(0.2126 * r + 0.7152 * g + 0.0722 * b))
    hi, lo = px.max(axis=1), px.min(axis=1)
    chroma = hi - lo
    safe = np.where(chroma > 0, chroma, 1.0)
    hue = np.where(hi == r, ((g - b) / safe) % 6, np.where(hi == g, (b - r) / safe + 2, (r - g) / safe + 4)) * 60.0
    weight = chroma  # grey pixels carry no hue
    warm = weight[(hue < 75) | (hue >= 330)].sum()
    green = weight[(hue >= 75) & (hue < 165)].sum()
    cool = weight[(hue >= 165) & (hue < 330)].sum()
    shares = _shares((warm, green, cool)) if weight.sum() > 0.01 * len(px) else _shares((1, 1, 1))
    return Colour(_q(brightness, 0.25, 0.0, 1.0), *shares)


ACCENTS = {  # an accent colour's hue masses (warm, green, cool)
    "red": (1, 0, 0), "orange": (1, 0, 0), "yellow": (1, 0, 0), "pink": (1, 0, 0), "green": (0, 1, 0),
    "teal": (0, 1, 1), "blue": (0, 0, 1), "purple": (0, 0, 1), "slate": (1, 1, 1), "graphite": (1, 1, 1),
}
_MAC_ACCENTS = {"-1": "graphite", "0": "red", "1": "orange", "2": "yellow", "3": "green", "4": "blue", "5": "purple",
                "6": "pink"}


def reduce_appearance(dark: bool, accent: str | None) -> Colour:
    """Dark or light mode and the accent colour's name to the same shape as an image."""
    shares = _shares(ACCENTS.get(accent or "", (1, 1, 1)))
    return Colour(0.25 if dark else 0.75, *shares)


def _appearance() -> Colour | None:
    if sys.platform == "darwin":
        dark = (_run("defaults", "read", "-g", "AppleInterfaceStyle") or "").strip() == "Dark"
        accent = _MAC_ACCENTS.get((_run("defaults", "read", "-g", "AppleAccentColor") or "").strip())
        return reduce_appearance(dark, accent)
    if sys.platform.startswith("linux"):
        scheme = _run("gsettings", "get", "org.gnome.desktop.interface", "color-scheme")
        if scheme is None:
            return None
        accent = (_run("gsettings", "get", "org.gnome.desktop.interface", "accent-color") or "").strip("'\n ")
        return reduce_appearance("dark" in scheme, accent or None)
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            light = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
            return reduce_appearance(not light, None)
        except Exception:
            return None
    return None


def read_bmp(data: bytes) -> np.ndarray:
    """An uncompressed 24- or 32-bit BMP to RGB pixels in 0..1."""
    if data[:2] != b"BM":
        raise ValueError("not a BMP")
    offset = int.from_bytes(data[10:14], "little")
    width = int.from_bytes(data[18:22], "little", signed=True)
    height = abs(int.from_bytes(data[22:26], "little", signed=True))
    bpp = int.from_bytes(data[28:30], "little")
    if bpp not in (24, 32) or int.from_bytes(data[30:34], "little") not in (0, 3):
        raise ValueError("unsupported BMP")
    row = ((bpp * width + 31) // 32) * 4
    rows = np.frombuffer(data, np.uint8, count=row * height, offset=offset).reshape(height, row)
    px = rows[:, : width * (bpp // 8)].reshape(height, width, bpp // 8)
    return px[:, :, 2::-1] / 255.0  # stored blue, green, red


def _thumbnail(path: Path) -> np.ndarray | None:
    """A small copy of an image as RGB pixels: with macOS's sips, or Pillow if it happens to be installed."""
    path = Path(path)
    if sys.platform == "darwin":
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "t.bmp"
            if _run("sips", "-s", "format", "bmp", "-Z", "64", str(path), "--out", str(out)) is not None and out.exists():
                return read_bmp(out.read_bytes())
    try:
        from PIL import Image  # optional; not a dependency

        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((64, 64))
            return np.asarray(im, dtype=float) / 255.0
    except Exception:
        return None


def _wallpaper_path() -> Path | None:
    """Where the desktop picture is, on systems that say so without asking permission."""
    if sys.platform.startswith("linux"):
        uri = (_run("gsettings", "get", "org.gnome.desktop.background", "picture-uri") or "").strip("'\n ")
        return Path(uri.removeprefix("file://")) if uri.startswith("file://") else None
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop")
            value = winreg.QueryValueEx(key, "WallPaper")[0]
            return Path(value) if value else None
        except Exception:
            return None
    return None  # macOS keeps it in a Library database; pass --wallpaper instead


def colour(wallpaper: Path | None = None) -> Colour | None:
    """Reads: the desktop picture (a file given with --wallpaper, or where the
    system names it), shrunk to 64 pixels; failing that, whether the screen is
    in dark mode and its accent colour. Keeps: brightness and three hue shares."""
    path = Path(wallpaper) if wallpaper else _wallpaper_path()
    if path is not None and path.is_file():
        pixels = _thumbnail(path)
        if pixels is not None and pixels.size:
            return reduce_colour(pixels)
    return _appearance()


# ---------------------------------------------------------------- words: the person's common words

# Public word lists the person's common words are projected onto. A word only
# ever counts toward these; no other word, and no count of it, leaves.
THEMES = {
    "sea": "sea seas ocean water waters ship ships boat boats sail sailing sailor sailors harbor harbour quay dock "
           "shore beach wave waves tide island river lake fish fishing deck port coast bay anchor swim rain storm",
    "fire": "fire fires flame flames coal spark sparks ember embers candle candles light lights lamp burn burning "
            "burned warm warmth heat smoke glow sun sunlight bright dawn hearth stove",
    "machines": "phone phones screen screens computer computers email emails internet online app apps data code "
                "file files software digital video videos record records recording tape radio signal wire wires "
                "wireless machine machines network device devices battery download laptop server numbers camera "
                "disc message messages text stream speaker",
    "earth": "field fields farm farms farmer hill hills mountain mountains stone stones garden gardens tree trees "
             "grass soil mud sheep goats flock shepherd harvest village road roads desert valley border mine mines "
             "wind weather snow winter spring summer autumn forest wood woods rock dust land earth seed seeds bird "
             "birds flower flowers",
    "home": "home homes mother mothers father fathers child children kid kids baby babies family families sister "
            "brother grandmother grandfather grandparents grandkids bed sleep kitchen house door window table wife "
            "husband daughter son parents cook dinner bread milk soap cradle",
    "town": "town towns street streets city cities crowd crowds people train trains railway traffic market shop "
            "shops company work office job jobs bus station church churches school hall party game games football "
            "team club pub bar neighbours neighbors strangers newspaper newspapers postman nurse ward",
    "music": "song songs sing singing sang sung music tune tunes voice voices choir band fiddle banjo guitar piano "
             "drum drums note notes melody dance dancing danced hum humming whistle bell bells play played playing "
             "singer singers concert lyrics verse chorus",
    "past": "old years remember remembered memory memories forget forgot forgotten past history age ages ancient "
            "letter letters photo photos name names story stories once ago",
}
# No mood is read from the documents: a person's grief or worry is not the
# song's business. Mood comes from the screen, the mode and the drift.
ERA = {
    "new": "phone phones email emails online internet app apps screen video computer digital data wifi laptop text "
           "texts stream streaming podcast download social website password login zoom update upload cloud tweet "
           "selfie charger battery",
    "old": "letter letters candle candles horse horses church cart well kettle ink telegram stamp stamps wireless "
           "gramophone typewriter parish lantern hearth sermon carriage chapel harvest mill shepherd spinning cellar",
}
STOPWORDS = set(
    "a about above after again against all almost also although am among an and another any anyone anything are "
    "around as at back be became because become been before being below between both but by can cannot could did "
    "do does doing done down during each either else enough even ever every few for from further get gets getting "
    "give go goes going got had has have having he her here hers herself him himself his how however i if in into "
    "is it its itself just know last least less let like made make many may me might more most much must my myself "
    "need never new next no nor not now of off often on once one only or other others our ours ourselves out over "
    "own per perhaps put quite rather really said same say see seem shall she should since so some something still "
    "such take than that the their theirs them themselves then there these they thing things think this those "
    "though through thus to too two under until up upon us use used using very want was way we well were what "
    "when where whether which while who whom whose why will with within without would yes yet you your yours "
    "yourself yourselves".split()
)
TEXT_SUFFIXES = (".txt", ".md", ".markdown", ".text", ".rtf", ".tex", ".org", ".rst", ".html", ".htm", ".docx", ".odt")


@lru_cache(maxsize=1)
def _dictionary() -> frozenset[str]:
    import cmudict

    return frozenset(cmudict.words())


def _lexicon(spec: dict) -> dict[str, frozenset[str]]:
    return {name: frozenset(words.split()) for name, words in spec.items()}


def mattr(tokens: list[str], window: int = 400) -> float | None:
    """Moving-average type-token ratio: how varied a vocabulary is, fairly
    across texts of any length."""
    if len(tokens) < window:
        return None
    step = max(1, (len(tokens) - window) // 50)
    ratios = [len(set(tokens[i:i + window])) / window for i in range(0, len(tokens) - window + 1, step)]
    return float(np.mean(ratios))


def reduce_words(common: list[str], richness: float | None) -> Words | None:
    """The person's most common words to theme shares, an era lean and
    richness. Each list counts the distinct common words it holds, so a
    handful of everyday words can't swamp the rest."""
    present = set(common)
    themes = {name: len(present & words) / len(words) for name, words in _lexicon(THEMES).items()}
    if sum(themes.values()) == 0 or richness is None:
        return None
    era_words = {name: len(present & words) for name, words in _lexicon(ERA).items()}
    era_total = era_words["new"] + era_words["old"]
    era = (era_words["new"] - era_words["old"]) / era_total if era_total else 0.0
    return Words(
        themes=dict(zip(THEMES, _shares(list(themes.values()), units=20))),
        era=_q(era, 0.25, -1.0, 1.0),
        richness=_q((richness - 0.45) / 0.3, 0.1, 0.0, 1.0),
    )


def _text(path: str, suffix: str, limit: int) -> str:
    """A document's words as plain text (markup stripped); nothing is kept."""
    if suffix in (".docx", ".odt"):
        with zipfile.ZipFile(path) as z:
            inner = "word/document.xml" if suffix == ".docx" else "content.xml"
            raw = z.read(inner)[: limit * 4].decode("utf-8", "ignore")
        return re.sub(r"<[^>]+>", " ", raw)
    with open(path, "rb") as f:
        raw = f.read(limit).decode("utf-8", "ignore")
    if suffix == ".rtf":
        raw = re.sub(r"\\[a-z]+-?\d* ?|[{}]", " ", raw)
    elif suffix in (".html", ".htm"):
        raw = re.sub(r"<[^>]+>", " ", raw)
    return raw


_TOKEN = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")


def words(roots=None, *, max_files: int = 600, per_file: int = 256_000, total: int = 30_000_000,
          seconds: float = 6.0) -> Words | None:
    """Reads: the text of up to 600 plain-text, Markdown, RTF, HTML, Word and
    OpenDocument files in Documents and Desktop (256 KB of each at most).
    Keeps: nothing but reduce_words' numbers. In between, in memory only: the
    lowercase dictionary words that appear in at least two documents, not
    counting capitalized ones (names) or function words, of which the 200 most
    frequent are projected onto the public lists above."""
    home = Path.home()
    roots = [Path(r) for r in roots] if roots is not None else [home / "Documents", home / "Desktop"]
    deadline = time.monotonic() + seconds
    counts: dict[str, int] = {}
    docs: dict[str, int] = {}
    tokens: list[str] = []
    read = n_docs = 0
    dictionary = _dictionary()
    for root in roots:
        if not root.is_dir():
            continue
        for entry in _walk(root, max_depth=6, private=True, deadline=deadline, limit=20 * max_files, top_level=False):
            suffix = os.path.splitext(entry.name)[1].lower()
            if suffix not in TEXT_SUFFIXES:
                continue
            if n_docs >= max_files or read >= total or time.monotonic() > deadline:
                break
            try:
                text = _text(entry.path, suffix, per_file)
            except (OSError, zipfile.BadZipFile, KeyError, ValueError):
                continue
            read += len(text)
            n_docs += 1
            found = _TOKEN.findall(text)
            del text
            if len(tokens) < 200_000:
                tokens += [w.lower() for w in found]
            seen = set()
            for w in found:
                if w.islower() and len(w) >= 3:
                    counts[w] = counts.get(w, 0) + 1
                    seen.add(w)
            for w in seen:
                docs[w] = docs.get(w, 0) + 1
            del found
    if n_docs < 3:
        return None
    common = [w for w in counts if docs.get(w, 0) >= 2 and w not in STOPWORDS and w in dictionary]
    common = sorted(common, key=lambda w: (-counts[w], w))[:200]
    result = reduce_words(common, mattr(tokens))
    for held in (counts, docs, tokens, common):
        held.clear()
    return result


# ---------------------------------------------------------------- hand: typing rhythm

PROMPT = "who made this song? nobody knows"


def reduce_hand(intervals) -> Hand | None:
    """Seconds between keys to their mean, spread and skew. Pauses over 1.5 s
    (thinking) and gaps under 20 ms (one key's several bytes) are dropped."""
    x = np.asarray([i for i in intervals if 0.02 <= i <= 1.5], dtype=float)
    if len(x) < 12:
        return None
    mean, std = float(x.mean()), float(x.std())
    skew = float(np.mean(((x - mean) / std) ** 3)) if std > 1e-6 else 0.0  # a perfectly even hand has none
    return Hand(
        interval=int(_q(mean * 1000, 20, 60, 600)),
        unevenness=_q(std / mean, 0.1, 0.0, 1.5),
        skew=_q(skew, 0.25, -2.0, 4.0),
    )


def typing_sample(line: str = PROMPT, stream=None) -> list[float] | None:
    """Ask the person to type a line and time their keys. Only when a person
    is at a terminal and runs `songbird harvest`; never in the background. The
    keys themselves are not kept, only when they came; a dot answers each."""
    out = stream or sys.stdout
    if not (sys.stdin.isatty() and out.isatty()):
        return None
    out.write("\nThe singer can take its rhythm from your hands. Type this line at your own pace,\n"
              "then press Enter (or Esc to skip). Only the time between keys is kept, never the keys.\n\n"
              f"    {line}\n    ")
    out.flush()
    times: list[float] = []
    try:
        if sys.platform == "win32":
            import msvcrt

            while True:
                ch = msvcrt.getwch()
                if ch in "\r\n":
                    break
                if ch == "\x1b":
                    times = []
                    break
                times.append(time.perf_counter())
                out.write(".")
                out.flush()
        else:
            import termios
            import tty

            fd = sys.stdin.fileno()
            saved = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                while True:
                    ch = os.read(fd, 1)
                    if not ch or ch in (b"\r", b"\n"):
                        break
                    if ch == b"\x1b":
                        times = []
                        break
                    times.append(time.perf_counter())
                    out.write(".")
                    out.flush()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    except (OSError, ImportError, KeyboardInterrupt):
        times = []
    out.write("\n")
    return list(np.diff(times)) if len(times) > 1 else None


# ---------------------------------------------------------------- room: not yet


def room() -> Room | None:
    """A stub: capturing the room needs a microphone library the program
    doesn't have yet. The plan: a clap or a two-second capture, its decay
    measured by Schroeder integration to an RT60, and its energy in the five
    bands of synth.room.BANDS relative to their mean as the tone; the capture
    deleted at once. Until then every machine's room is its parent's."""
    return None


# ---------------------------------------------------------------- harvesting and the cache


def new_salt() -> str:
    """A random number for a new machine's voice: not derived from anything."""
    return os.urandom(8).hex()


def harvest(without=(), *, home: Path | None = None, private: bool = True, wallpaper: Path | None = None,
            typing: bool = False, salt: str | None = None) -> Voice:
    """Read every signal not left out. A signal that fails is missing, never an error."""
    skip = {signal_name(s) for s in without}
    readers = {
        "tongue": tongue,
        "machine": machine,
        "ages": lambda: ages(home, private=private),
        "colour": lambda: colour(wallpaper),
        "words": lambda: words(None if home is None else [Path(home) / "Documents", Path(home) / "Desktop"]),
        "hand": lambda: reduce_hand(typing_sample() or []) if typing else None,
        "room": room,
    }
    values = {}
    for name in SIGNALS:
        if name in skip:
            continue
        try:
            values[name] = readers[name]()
        except Exception:  # a signal that can't be read is simply absent
            values[name] = None
    return Voice(**values, salt=salt or new_salt())


def home_dir() -> Path:
    """Where the program keeps its cache: $SONGBIRD_HOME, or ~/.songbird."""
    return Path(os.environ.get("SONGBIRD_HOME") or Path.home() / ".songbird")


def cache_path() -> Path:
    return home_dir() / "voice.json"


def load() -> Voice | None:
    try:
        return Voice.from_dict(json.loads(cache_path().read_text()))
    except (OSError, ValueError, TypeError, KeyError):
        return None


def save(voice: Voice) -> Path:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(voice.to_dict(), indent=2, sort_keys=True) + "\n")
    return path


def rested(voice: Voice) -> Voice:
    """The voice with its uptime read now: the one part of it that is live."""
    if voice.machine is None:
        return voice
    fresh = reduce_machine(1, 1, _uptime())
    return replace(voice, machine=replace(voice.machine, uptime=fresh.uptime if fresh else voice.machine.uptime))


def here() -> Voice:
    """This machine's voice: the cached one, or a fresh harvest (without the
    typing prompt) cached for next time; its uptime read now."""
    voice = load()
    if voice is None:
        voice = harvest()
        save(voice)
    return rested(voice)


def machine_voice(spec: str) -> Voice:
    """--machine: 'here', 'none' (a neutral voice), 'fictional:NAME', or a voice
    file (a render's record works too, replaying its voice)."""
    if spec == "here":
        return here()
    if spec in ("none", "neutral"):
        return Voice()
    if spec.startswith("fictional:"):
        return fictional(spec.split(":", 1)[1])
    return Voice.from_dict(json.loads(Path(spec).read_text()))


# ---------------------------------------------------------------- fictional machines

_FICTIONAL_LANGUAGES = ("en", "en", "en", "en", "de", "fr", "es", "it", "pt", "nl", "sv", "ga", "pl", "ru", "uk",
                        "cs", "tr", "ar", "he", "hi", "bn", "ja", "zh", "ko", "vi", "fi", "el")


def fictional(name: str) -> Voice:
    """A made-up machine, drawn from plausible ranges and reduced the same way
    a real one is; the same machine every time for the same name."""
    seed = hashlib.sha256(f"fictional:{name}".encode()).digest()
    rng = np.random.default_rng(int.from_bytes(seed[:8], "little"))
    lang = str(rng.choice(_FICTIONAL_LANGUAGES))
    cores = int(rng.choice((2, 4, 8, 10, 12, 16, 24)))
    memory = int(rng.choice((4, 8, 16, 32, 64))) * 2**30
    uptime = float(rng.choice((0.3, 3.0, 20.0))) * 86400
    median = rng.uniform(1.4, 3.4)
    spread = rng.uniform(0.4, 2.2)
    file_ages = 10 ** rng.normal(median, spread / 1.35, 400)
    hue = rng.dirichlet((0.8, 0.8, 0.8))
    themes = rng.dirichlet(np.full(len(THEMES), 0.6))
    mean = rng.uniform(0.11, 0.32)
    intervals = rng.gamma(shape=rng.uniform(1.5, 6.0), scale=1.0, size=40)
    intervals = intervals / intervals.mean() * mean
    rt60 = float(np.exp(rng.uniform(np.log(0.35), np.log(2.2))))
    tone = [rng.uniform(0.8, 1.2), rng.uniform(0.85, 1.15), rng.uniform(0.85, 1.1), rng.uniform(0.6, 1.0),
            rng.uniform(0.35, 0.85)]
    return Voice(
        tongue=reduce_tongue([lang]),
        machine=reduce_machine(cores, memory, uptime),
        ages=reduce_ages(file_ages),
        colour=Colour(_q(rng.uniform(0.1, 0.9), 0.25), *_shares(hue)),
        words=Words(
            themes=dict(zip(THEMES, _shares(themes, units=20))),
            era=_q(rng.uniform(-1, 1), 0.25),
            richness=_q(rng.uniform(0, 1), 0.1),
        ),
        hand=reduce_hand(intervals),
        room=Room(rt60=_q(rt60, 0.1), tone=tuple(_q(t, 0.1) for t in tone)),
        salt=seed[8:16].hex(),
    )
