"""The web page: one page that draws the system and shows what the command line shows, from
``/api/*`` (read only). ``serve(project, port)`` starts it in a thread and returns (server, url)."""

from __future__ import annotations

import json
import socket
import threading
from http.server import ThreadingHTTPServer

from .server import handler

DEFAULT_PORT = 8781


def _free(port: int) -> int:
    for p in range(port, port + 40):
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise OSError("no free port near " + str(port))


def serve(project, port: int | None = None):
    port = _free(port or DEFAULT_PORT)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler(project))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    (project.dir / "web.json").write_text(json.dumps({"url": url}))
    return server, url
