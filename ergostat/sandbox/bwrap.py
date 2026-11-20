"""Linux: ``bwrap`` with an empty root that binds only what is allowed, every namespace unshared (no network at all),
a new session, ``--die-with-parent``, and a pid namespace whose end kills everything in it. With hosts listed, the
proxy's Unix socket is bound in and a forwarder inside the sandbox serves it on 127.0.0.1 at the same port."""

from __future__ import annotations

import glob
import os

# Inside the sandbox: listen on 127.0.0.1:PORT, relay each connection to the proxy's socket, then run the program.
FORWARD = r"""
import socket, subprocess, sys, threading
sock, port, argv = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
def pipe(a, b):
    try:
        for chunk in iter(lambda: a.recv(65536), b""):
            b.sendall(chunk)
        b.shutdown(socket.SHUT_WR)
    except OSError:
        pass
def serve(c):
    u = socket.socket(socket.AF_UNIX)
    u.connect(sock)
    threading.Thread(target=pipe, args=(c, u), daemon=True).start()
    pipe(u, c)
s = socket.socket()
s.bind(("127.0.0.1", port))
s.listen(64)
threading.Thread(target=lambda: [threading.Thread(target=serve, args=(s.accept()[0],), daemon=True).start()
                                 for _ in iter(int, 1)], daemon=True).start()
sys.exit(subprocess.call(argv))
"""


def argv(cmd: list[str], work: str, tmp: str, reads: list[str], libs: list[str], cwd, unix: str | None,
         port: int | None, python: str) -> list[str]:
    out = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--proc", "/proc", "--dev", "/dev",
           "--hostname", "localhost"]
    shared = sorted(f for d in libs for f in glob.glob(os.path.join(d, "*.so*")) if os.path.isfile(f))
    for r in [*reads, *shared]:
        out += ["--ro-bind", r, r]
    for d in ("/bin", "/lib", "/lib64", "/sbin"):         # merged /usr: the top-level names are links into it
        if os.path.islink(d) and os.path.realpath(d) in reads:
            out += ["--symlink", os.readlink(d), d]
    out += ["--bind", work, work, "--bind", tmp, tmp]
    git = os.path.join(work, ".git")
    if os.path.lexists(git):
        out += ["--ro-bind", git, git]
    out += ["--chdir", str(cwd)]
    if unix:
        out += ["--ro-bind", unix, unix, "--", python, "-I", "-c", FORWARD, unix, str(port), *cmd]
    else:
        out += ["--", *cmd]
    return out
