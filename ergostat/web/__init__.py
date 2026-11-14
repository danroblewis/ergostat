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
    """Requests served by a fixed pool of daemon threads, so each keeps its database connections
    instead of opening and closing them for every request (the page polls every few seconds), and
    an idle browser connection never keeps the process from exiting."""

    workers = 24          # browsers open idle connections ahead of time: enough threads that they never starve a request

    def __init__(self, *a, **kw):
        import queue
        super().__init__(*a, **kw)
        self.jobs: queue.Queue = queue.Queue()
        for i in range(self.workers):
            threading.Thread(target=self._work, name=f"ergostat-web-{i}", daemon=True).start()

    def _work(self):
        while True:
            job = self.jobs.get()
            if job is None:
                return
            self.process_request_thread(*job)

    def process_request(self, request, client_address):
        self.jobs.put((request, client_address))

    def server_close(self):
        super().server_close()
        for _ in range(self.workers):
            self.jobs.put(None)


def serve(project, port: int | None = None):
    port = _free(port or DEFAULT_PORT)
    server = PooledServer(("127.0.0.1", port), handler(project))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    (project.dir / "web.json").write_text(json.dumps({"url": url}))
    return server, url
