"""Send Python to a Blender session running blender_link.py, and print what it printed.

    python3 tools/cover/send.py -c 'print(bpy.data.filepath)'
    python3 tools/cover/send.py tools/cover/scene.py          # rebuild the cover in the open session
    python3 tools/cover/send.py tools/cover/scene.py --golf   # its arguments go along
"""

import socket
import sys
from pathlib import Path

PORT = 9876


def send(code: str) -> str:
    with socket.create_connection(("127.0.0.1", PORT), timeout=600) as s:
        s.sendall(code.encode("utf-8"))
        s.shutdown(socket.SHUT_WR)
        out = b""
        while chunk := s.recv(1 << 16):
            out += chunk
    return out.decode("utf-8")


if __name__ == "__main__":
    if sys.argv[1:2] == ["-c"]:
        code = sys.argv[2]
    else:
        path = Path(sys.argv[1]).resolve()
        # run the script as itself, with __file__ set and the live flag on
        argv = ["blender", "--", "--live", *sys.argv[2:]]
        code = (f"import sys\nsys.argv = {argv!r}\n__file__ = {str(path)!r}\n"
                f"exec(compile(open(__file__).read(), __file__, 'exec'))")
    print(send(code), end="")
