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


class PooledServer(ThreadingHTTPServer):
    """Requests served by a fixed pool of threads, so each keeps its database connections instead
    of opening and closing them for every request (the page polls every few seconds)."""

    def __init__(self, *a, **kw):
        from concurrent.futures import ThreadPoolExecutor
        super().__init__(*a, **kw)
        self.pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ergostat-web")

    def process_request(self, request, client_address):
        self.pool.submit(self.process_request_thread, request, client_address)

    def server_close(self):
        super().server_close()
        self.pool.shutdown(wait=False, cancel_futures=True)


def serve(project, port: int | None = None):
    port = _free(port or DEFAULT_PORT)
    server = PooledServer(("127.0.0.1", port), handler(project))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    (project.dir / "web.json").write_text(json.dumps({"url": url}))
    return server, url
