"""The web page: one page that draws the system and shows what the command line shows, from
``/api/*`` (read only). ``serve(project, port)`` starts it in a thread and returns (server, url)."""

from __future__ import annotations

import json
import socket
import threading
from http.server import ThreadingHTTPServer

from .server import handler

DEFAULT_PORT = 8781


def _free(port: int, host: str = "127.0.0.1") -> int:
    for p in range(port, port + 40):
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, p))
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

    def handle_error(self, request, client_address):
        """A client that went away (while its request was read, or its answer written) is a quiet line;
        anything else is the standard traceback."""
        import sys

        from .server import GONE, went_away
        e = sys.exc_info()[1]
        if isinstance(e, GONE) or isinstance(e, TimeoutError):
            went_away("a request", 0, e)
            return
        super().handle_error(request, client_address)

    def server_close(self):
        super().server_close()
        for _ in range(self.workers):
            self.jobs.put(None)


def record_fits(live, every: float = 300.0, stop: threading.Event | None = None) -> None:
    """Each version's fit kept in its history every few minutes, on the reference window, whether or
    not anyone opens the Model page (so the history compares versions on like spans of record)."""
    import time

    from .numbers_api import reference, spec_of
    stop = stop or threading.Event()
    while not stop.wait(every):
        try:
            p = live.get()
            if spec_of(p) is None:
                continue
            got = reference(live, p, {"at": time.time(), "live": True})
            from ..numbers import fit as ft
            ft.record(p, got["fit"])
        except Exception:                               # a bad moment is skipped; the page never depends on it
            continue


def serve(project, port: int | None = None):
    """The page on ``port`` (or the next free one), on this machine only unless ``intake: bind:`` says where else; from
    another machine only events may be pushed (``intake: allow:``). The push token is made now (``intake/token.py``)."""
    spec = getattr(project.model, "spec", None)
    host = getattr(getattr(spec, "intake", None), "bind", None) or "127.0.0.1"
    port = _free(port or DEFAULT_PORT, host)
    from ..intake.token import token
    token(project.dir)
    server = PooledServer((host, port), handler(project))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=record_fits, args=(server.RequestHandlerClass.live,), name="ergostat-fit-history", daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    (project.dir / "web.json").write_text(json.dumps({"url": url}))
    return server, url
