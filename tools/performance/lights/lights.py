"""The laptop's end of the lanterns: frames to the host board over USB, which broadcasts them over ESP-NOW.

    python3 tools/performance/lights/lights.py status          the lanterns' batteries and reception, once a second
    python3 tools/performance/lights/lights.py test            each lantern its own color, a dot running along it
    python3 tools/performance/lights/lights.py fade            every lantern a warm fade, 8 s from dark to full and back
    python3 tools/performance/lights/lights.py screens         the screens' shapes in turn, 8 s each, the strip glowing with them
    python3 tools/performance/lights/lights.py local-fade      the board on USB fades by itself (again to stop): no link involved
    python3 tools/performance/lights/lights.py id 2            set the id of the board on USB (0: host only)
    python3 tools/performance/lights/lights.py dark            every lantern dark
    python3 tools/performance/lights/lights.py rot             turn the board's screen upside down (kept)

--port picks the serial port (found on its own otherwise), --leds the LEDs in a lantern (20), --max the brightness
cap (0-255, kept by each lantern until it restarts). Needs pyserial.

From code: Lights().frame({1: [(r, g, b), ...], 2: [...]}) and Lights().screen({1: Scene(...), ...}) at the show's
frame rate; a lantern goes dark when frames stop for 2 s. The scenes are listed in firmware/src/scenes.h. The packet format is in firmware/src/main.cpp.
"""

from __future__ import annotations

import argparse
import colorsys
import glob
import math
import sys
import threading
import time
from dataclasses import dataclass

import serial
from serial.tools import list_ports

BAUD = 460800
MAX_PACKET = 250
KNOWN = {0x1A86, 0x10C4, 0x303A, 0x0403}  # WCH (CH9102/CH340), Silicon Labs, Espressif, FTDI


SCENES = ("dark", "glow", "ring", "ripples", "rays", "rise", "arch", "bands", "mouth", "face", "dot")


@dataclass
class Scene:
    """A lantern's screen: a shape in `color` over `ground`; a to k are the shape's own (scenes.h)."""

    kind: str = "dark"
    color: tuple[int, int, int] = (255, 255, 255)
    ground: tuple[int, int, int] = (0, 0, 0)
    a: int = 0
    b: int = 0
    c: int = 0
    d: int = 128
    e: int = 128
    f: int = 0
    g: int = 0
    h: int = 0
    i: int = 128
    j: int = 0
    k: int = 0
    backlight: int = 255

    def record(self, lantern: int) -> bytes:
        values = (lantern, SCENES.index(self.kind), *self.color, *self.ground, self.a, self.b, self.c, self.d, self.e,
                  self.f, self.g, self.h, self.i, self.j, self.k, self.backlight)
        return bytes(max(0, min(255, int(v))) for v in values)


def find_port() -> str:
    # Linux's vendor CH9102 driver names its port ttyCH343USB*, which pyserial's listing leaves out
    wch = sorted(glob.glob("/dev/ttyCH343USB*"))
    if wch:
        return wch[0]
    ports = [p for p in list_ports.comports() if p.vid in KNOWN]
    if not ports:
        sys.exit("no ESP32 board on USB (pass --port)")
    # the T-Display's CH9102 first: other USB-serial devices may be plugged in too
    ports.sort(key=lambda p: (p.vid != 0x1A86, p.device))
    return ports[0].device


class Lights:
    def __init__(self, port: str | None = None, on_line=None):
        self.port = serial.Serial()
        self.port.port, self.port.baudrate, self.port.timeout = port or find_port(), BAUD, 0.1
        self.port.dtr = self.port.rts = False  # DTR and RTS are the board's boot and reset lines
        self.port.open()
        self.on_line = on_line or (lambda line: None)
        self._ready = threading.Event()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        # opening the port still resets the board on some drivers: wait for its first line, or a moment if it
        # was already running
        self.command("status")
        self._ready.wait(3)

    def _read(self):
        buf = b""
        while True:
            try:
                buf += self.port.read(256)
            except serial.SerialException:
                return
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode(errors="replace").strip()
                if text.startswith(("lantern firmware", "host ")):
                    self._ready.set()
                if text.isprintable() and text:
                    self.on_line(text)

    def send(self, kind: int, body: bytes = b""):
        packet = bytes([ord("S"), ord("B"), 1, kind, 0, 0]) + body
        assert len(packet) <= MAX_PACKET
        x = 0
        for b in packet:
            x ^= b
        self.port.write(bytes([0xA5, len(packet)]) + packet + bytes([x]))

    def frame(self, lanterns: dict[int, list[tuple[int, int, int]]]):
        """Every lantern's colors, as few packets as they fit in."""
        body = b""
        for lantern, colors in lanterns.items():
            for start in range(0, len(colors), 60):
                part = colors[start:start + 60]
                segment = bytes([lantern, start, len(part)]) + bytes(c for rgb in part for c in rgb)
                if 6 + len(body) + len(segment) > MAX_PACKET:
                    self.send(1, body)
                    body = b""
                body += segment
        if body:
            self.send(1, body)

    def screen(self, lanterns: dict[int, Scene]):
        """Every lantern's screen, in one packet (20 lanterns fit)."""
        self.send(4, b"".join(scene.record(lantern) for lantern, scene in lanterns.items()))

    def brightness(self, level: int, lantern: int = 255):
        self.send(2, bytes([lantern, level]))

    def dark(self):
        self.send(3)

    def command(self, text: str):
        self.port.write(b"\n" + text.encode() + b"\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["status", "test", "fade", "screens", "local-fade", "id", "dark", "rot"])
    ap.add_argument("value", nargs="?", type=int)
    ap.add_argument("--port")
    ap.add_argument("--leds", type=int, default=20)
    ap.add_argument("--lanterns", type=int, default=5)
    ap.add_argument("--max", type=int)
    ap.add_argument("--fps", type=float, default=50)
    ap.add_argument("--say", action="append", default=[], help="a text command for the board first, e.g. radio")
    args = ap.parse_args()

    lights = Lights(args.port, on_line=print)
    for text in args.say:
        lights.command(text)
    if args.max is not None:
        lights.brightness(args.max)
    if args.what == "id":
        lights.command(f"id {args.value or 0}")
        time.sleep(0.5)
    elif args.what == "dark":
        lights.dark()
        time.sleep(0.2)
    elif args.what == "status":
        try:
            while True:
                lights.command("status")
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    elif args.what == "rot":
        lights.command("rot")
        time.sleep(0.5)
    elif args.what == "screens":
        demo(lights, args)
    elif args.what == "local-fade":
        lights.command("fade")  # the board fades on its own until this is sent again (or it restarts)
        time.sleep(0.5)
    elif args.what in ("test", "fade"):
        print("Ctrl-C to stop")
        t0 = time.monotonic()
        n = 0
        try:
            while True:
                t = time.monotonic() - t0
                frames = {}
                for lantern in range(1, args.lanterns + 1):
                    r, g, b = colorsys.hsv_to_rgb((lantern - 1) / args.lanterns, 1, 0.35)
                    base = (int(r * 255), int(g * 255), int(b * 255))
                    if args.what == "fade":  # warm, dark to full and back in 8 s
                        v = 0.5 - 0.5 * math.cos(t / 8 * 2 * math.pi)
                        frames[lantern] = [(int(255 * v), int(140 * v), int(40 * v))] * args.leds
                    else:
                        dot = int(t * 10) % args.leds
                        frames[lantern] = [(255, 255, 255) if i == dot else base for i in range(args.leds)]
                lights.frame(frames)
                n += 1
                if n % round(args.fps) == 0:
                    lights.command("status")
                time.sleep(max(0, t0 + n / args.fps - time.monotonic()))
        except KeyboardInterrupt:
            lights.dark()
            time.sleep(0.2)


def shown(t: float, hue: float) -> tuple[Scene, tuple[int, int, int]]:
    """The demo at t seconds: each shape for 8 s, moving, in the lantern's color; and the strip's color with it."""
    kind = SCENES[1 + int(t // 8) % (len(SCENES) - 1)]
    u = t % 8 / 8  # 0-1 through this shape's turn
    breath = 0.5 - 0.5 * math.cos(u * 2 * math.pi)
    r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 1)
    color = (r * 255, g * 255, b * 255)
    ground = tuple(v * 0.06 for v in color)
    scene = Scene(kind, color, ground)
    if kind == "glow":
        scene.a, scene.b = 40 + 130 * breath, 60
    elif kind == "ring":
        scene.a, scene.b = 30 + 150 * u, 24
    elif kind == "ripples":
        scene.b, scene.c = 40, t * 64
    elif kind == "rays":
        scene.a, scene.b, scene.c = 120 + 80 * breath, 60, t * 16
    elif kind == "rise":
        scene.a, scene.b = 255 * breath, 30
    elif kind == "arch":
        scene.a, scene.b, scene.c = 20, 30, 120 * breath
    elif kind == "bands":
        scene.b, scene.c = 48, t * 40
    elif kind in ("mouth", "face"):
        scene.a, scene.b, scene.c, scene.f, scene.g = 20 + 120 * breath, 150, 120, 90, 170
        scene.d = 128 + 50 if kind == "face" else 128
        scene.h, scene.i, scene.j, scene.k = 255 * (u % 0.25 > 0.02), 128 + 120 * math.sin(u * 6.3), 140, 120
    elif kind == "dot":
        scene.a, scene.b, scene.c = 60, 20, 200
        scene.d, scene.e = 128 + 100 * math.sin(u * 6.3), 128 + 80 * math.cos(u * 12.6)
    level = 0.15 + 0.6 * breath
    return scene, tuple(int(v * level) for v in color)


def demo(lights: Lights, args):
    print("Ctrl-C to stop")
    t0 = time.monotonic()
    n = 0
    last = None
    try:
        while True:
            t = time.monotonic() - t0
            screens, strips = {}, {}
            for lantern in range(1, args.lanterns + 1):
                screens[lantern], glow = shown(t, (lantern - 1) / args.lanterns)
                strips[lantern] = [glow] * args.leds
            if screens[1].kind != last:
                print(screens[1].kind)
                last = screens[1].kind
            lights.frame(strips)
            lights.screen(screens)
            n += 1
            if n % round(args.fps) == 0:
                lights.command("status")
            time.sleep(max(0, t0 + n / args.fps - time.monotonic()))
    except KeyboardInterrupt:
        lights.dark()
        time.sleep(0.2)


if __name__ == "__main__":
    main()
