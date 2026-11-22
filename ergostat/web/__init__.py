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


BUSY = b"HTTP/1.0 503 Service Unavailable\r\nRetry-After: 2\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


def cheap(head: bytes) -> bool:
    """A request (its first bytes) for the fast lane: a GET of a static file, of the page (``/``, ``/items``...) or of
    an answer that needs no snapshot (``/api/projects``). Everything else goes to the API queue."""
    from .server import is_page_path
    line = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ")
    path = line[1].split("?", 1)[0] if len(line) > 1 and line[0] == "GET" else ""
    return path.startswith("/static/") or path == "/api/projects" or (path[:1] == "/" and is_page_path(path))


class PooledServer(ThreadingHTTPServer):
    """Requests served by fixed pools of daemon threads, so each keeps its database connections instead of opening
    and closing them for every request (the page polls every few seconds), and an idle browser connection never keeps
    the process from exiting. One thread (a selector) holds each connection until its request's bytes arrive, then
    queues it by what it asks (``cheap``): the fast lane never waits behind the API. A full queue is a 503 at once."""

    workers = 24          # the API's
    fast_workers = 4      # static files and the page: a lane the API queue never fills
    queue_most = 256      # each queue's most waiting; past it, 503 with Retry-After
    held_most = 512       # connections open with no request yet (a browser opens some ahead of time); past it, 503
    held_for = 10.0       # a connection that sends nothing for this long is closed (the handler's own timeout)
    request_queue_size = 128   # the listen backlog (the standard 5 makes a burst of connects wait 1-3 s on SYN retries)

    def __init__(self, *a, **kw):
        import queue
        super().__init__(*a, **kw)
        self.jobs: queue.Queue = queue.Queue(self.queue_most)
        self.fast: queue.Queue = queue.Queue(self.queue_most)
        self.local = threading.local()                 # the job a worker is on: when it was queued, when taken
        self._new: list = []
        self._wake, self._waker = socket.socketpair()
        self._stopping = False
        for q, n, name in ((self.jobs, self.workers, "web"), (self.fast, self.fast_workers, "web-fast")):
            for i in range(n):
                threading.Thread(target=self._work, args=(q,), name=f"ergostat-{name}-{i}", daemon=True).start()
        threading.Thread(target=self._reception, name="ergostat-web-reception", daemon=True).start()

    def _work(self, q):
        import time
        while (job := q.get()) is not None:
            self.local.queued, self.local.taken = job[2], time.monotonic()
            self.process_request_thread(job[0], job[1])

    def process_request(self, request, client_address):
        self._new.append((request, client_address))   # (list.append is atomic; the reception swaps the list)
        try:
            self._waker.send(b"x")
        except OSError:                                # (its buffer full: the reception is already woken)
            pass

    def _busy(self, request):
        """503 with Retry-After, written without waiting; what was sent is read first, so closing sends FIN, not RST."""
        try:
            request.setblocking(False)
            try:
                request.recv(65536)
            except OSError:
                pass
            request.send(BUSY)
        except OSError:
            pass
        self.shutdown_request(request)

    def _reception(self):
        """Each connection held until its request's bytes arrive, then queued; one closed having sent nothing, or
        silent for ``held_for``, is closed."""
        import queue
        import selectors
        import time
        sel = selectors.DefaultSelector()
        sel.register(self._wake, selectors.EVENT_READ)
        while not self._stopping:
            for key, _ in sel.select(1.0):
                if key.fileobj is self._wake:
                    self._wake.recv(4096)
                    new, self._new = self._new, []
                    for request, addr in new:
                        if len(sel.get_map()) > self.held_most:
                            self._busy(request)
                        else:
                            sel.register(request, selectors.EVENT_READ, (request, addr, time.monotonic()))
                    continue
                sel.unregister(key.fileobj)
                request, addr, _ = key.data
                try:
                    head = request.recv(1024, socket.MSG_PEEK | socket.MSG_DONTWAIT)
                except OSError:
                    head = b""
                if not head:
                    self.shutdown_request(request)
                    continue
                try:
                    (self.fast if cheap(head) else self.jobs).put_nowait((request, addr, time.monotonic()))
                except queue.Full:
                    self._busy(request)
            now = time.monotonic()
            for key in [k for k in sel.get_map().values() if k.data and (self._stopping or now - k.data[2] > self.held_for)]:
                sel.unregister(key.fileobj)
                self.shutdown_request(key.data[0])
        sel.close()
        self._wake.close()

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

    def _stop_mtls(self):
        if getattr(self, "mtls", None) is not None:   # the remote API's listener stops with the page (web: mtls:)
            self.mtls.stop()

    def shutdown(self):
        super().shutdown()
        self._stop_mtls()

    def server_close(self):
        super().server_close()
        self._stop_mtls()
        if getattr(self, "jobs", None) is None:     # (none yet when the port could not be bound: the bind error is the news)
            return
        import queue
        self._stopping = True
        self._waker.send(b"x")
        self._waker.close()
        for q, n in ((self.jobs, self.workers), (self.fast, self.fast_workers)):
            try:
                for _ in range(n):
                    q.put(None, timeout=1)             # (a queue still full: its workers end with the process)
            except queue.Full:
                pass


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


def serve(project, port: int | None = None, mtls_port: int | None = None):
    """The page on ``port`` (or the next free one), on this machine only unless ``intake: bind:`` says where else; from
    another machine only events may be pushed (``intake: allow:``). The push token is made now (``intake/token.py``).
    With ``web: mtls:``, the remote API's own listener beside it (``remote/listen.py``; ``mtls_port`` overrides its
    port, 0 for any): ``server.mtls_said`` says where it listens, or why not, and the page serves either way."""
    spec = getattr(project.model, "spec", None)
    host = getattr(getattr(spec, "intake", None), "bind", None) or "127.0.0.1"
    port = _free(port or DEFAULT_PORT) if host == "127.0.0.1" else _free(port or DEFAULT_PORT, host)
    from ..intake.token import token
    token(project.dir)
    server = PooledServer((host, port), handler(project))
    server.daemon_threads = True
    server.mtls, server.mtls_said, server.mtls_port = None, "", None
    conf = getattr(getattr(spec, "web", None), "mtls", None)
    if conf is not None:
        from ..remote import listen
        server.mtls, server.mtls_said = listen.serve(conf, spec.root, server.RequestHandlerClass, mtls_port)
        server.mtls_port = server.mtls.server_address[1] if server.mtls else None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=record_fits, args=(server.RequestHandlerClass.live,), name="ergostat-fit-history", daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    (project.dir / "web.json").write_text(json.dumps({"url": url}))
    return server, url
