"""Let an agent build the cover in this Blender session while you watch. Run it once, from Blender's Python
console:

    exec(open("/home/milo/Code/songbird/tools/cover/blender_link.py").read())

It listens on 127.0.0.1:9876 (this machine only) for Python and runs it on Blender's main thread between
redraws, sending back whatever it printed. tools/cover/send.py is the other end. To stop it, run
bpy.app.driver_namespace["songbird_link"].stop() or close Blender.
"""

import contextlib
import io
import queue
import socket
import threading
import traceback

import bpy

PORT = 9876


class Link:
    def __init__(self):
        self.jobs = queue.Queue()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", PORT))
        self.sock.listen(2)
        self.running = True
        threading.Thread(target=self.serve, daemon=True).start()
        bpy.app.timers.register(self.pump, first_interval=0.1, persistent=True)

    def serve(self):
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            with conn:
                data = b""
                while chunk := conn.recv(1 << 16):
                    data += chunk
                done, box = threading.Event(), {}
                self.jobs.put((data.decode("utf-8"), box, done))
                done.wait()
                conn.sendall(box["out"].encode("utf-8"))

    def pump(self):
        if not self.running:
            return None
        while not self.jobs.empty():
            code, box, done = self.jobs.get()
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    exec(compile(code, "<link>", "exec"), {"__name__": "__songbird_link__", "bpy": bpy})
            except Exception:
                out.write(traceback.format_exc())
            box["out"] = out.getvalue()
            done.set()
        return 0.1

    def stop(self):
        self.running = False
        self.sock.close()


old = bpy.app.driver_namespace.get("songbird_link")
if old is not None:
    old.stop()
bpy.app.driver_namespace["songbird_link"] = Link()
print(f"songbird link: listening on 127.0.0.1:{PORT}")
