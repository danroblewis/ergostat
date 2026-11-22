"""The remote API over mutual TLS (SPEC §4c, ``web: mtls:``): a listener of its own beside the loopback page, sharing
its ``Live``, bounded by hard constants (never config). A connection takes a slot without waiting, or is closed at
once; its handshake runs in its own thread and must be done within ``HANDSHAKE`` in all, however slowly the peer's
bytes come (``ssl`` takes a socket's timeout as the handshake's total since 3.5); after it, the socket times out
when ``IDLE`` passes without a byte (a peer with a certificate from ``client-ca`` that keeps sending a byte now and
then keeps its slot). The handler serves ``GET /remote/v1/<endpoint>...`` only, on decoded path segments; anything
else is 404 (or 405) without reaching the page's routes. Stopping closes every open connection and joins its thread."""

from __future__ import annotations

import itertools
import socket
import socketserver
import threading
import time
from urllib.parse import unquote, urlsplit

MOST = 16                 # connections at once
HANDSHAKE = 10.0          # seconds a TLS handshake may take
IDLE = 10.0               # seconds a connection may stay quiet after it
JOIN = 2.0                # seconds a stop waits for the connections' threads, in all
ENDPOINTS = frozenset({"status", "model", "events", "items", "counts", "readings", "series", "process"})


def allowed(raw_path: str) -> bool:
    """``/remote/v1/<endpoint>[/...]``: decoded segments, none of them ``.``, ``..``, empty (but a trailing one) or
    holding a slash."""
    path = raw_path.split("?", 1)[0].split("#", 1)[0]
    segs = [unquote(s) for s in path.split("/")]
    if segs[0] != "":
        return False
    segs = segs[1:]
    if len(segs) > 3 and segs[-1] == "":
        segs = segs[:-1]
    return (len(segs) >= 3 and segs[0] == "remote" and segs[1] == "v1" and segs[2] in ENDPOINTS
            and all(s not in ("", ".", "..") and "/" not in s and "\\" not in s for s in segs))


def handler(page):
    """The page's handler class, narrowed to the remote API."""
    class Remote(page):
        @property
        def timeout(self):                               # (read at use, so a test's shorter IDLE takes)
            return IDLE

        def _refuse(self):
            return self._send(405, b'{"error": "the remote API is read only: GET"}', "application/json")

        do_HEAD = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_TRACE = do_CONNECT = _refuse

        def __getattr__(self, name):                     # any other method: 405 as well, never 501
            if name.startswith("do_"):
                return self._refuse
            raise AttributeError(name)

        def do_GET(self):
            if not allowed(self.path):
                return self._send(404, b'{"error": "only /remote/v1/ is served here"}', "application/json")
            return self._remote(urlsplit(self.path))
    return Remote


def _shut(sock) -> None:
    try:
        socket.socket.shutdown(sock, socket.SHUT_RDWR)  # the fd itself: never SSLSocket.shutdown under a handshake
    except OSError:
        pass


class Listener(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, addr, handler_cls, ctx):
        self.ctx = ctx
        self.slots = threading.BoundedSemaphore(MOST)
        self.lock = threading.Lock()
        self.open: dict = {}                             # accepted socket: [its thread, the socket holding its fd now]
        self.stopping = self.stopped = False
        self.accepted = 0
        self._n = itertools.count(1)
        self.address_family = socket.AF_INET6 if ":" in addr[0] else socket.AF_INET
        super().__init__(addr, handler_cls)

    def process_request(self, request, client_address):
        with self.lock:
            self.accepted += 1
        if not self.slots.acquire(blocking=False):      # full: closed now, never queued
            request.close()
            return
        with self.lock:
            if self.stopping:
                self.slots.release()
                request.close()
                return
            t = threading.Thread(target=self._serve, args=(request, client_address), daemon=True,
                                 name=f"ergostat-mtls-{next(self._n)}")
            self.open[request] = [t, request]
            try:
                t.start()
            except RuntimeError:
                del self.open[request]
                self.slots.release()
                request.close()

    def held(self) -> int:
        with self.lock:
            return len(self.open)

    def _swap(self, raw, sock) -> bool:
        """The socket now holding the connection's fd, so a stop shuts that one; False when a stop began."""
        with self.lock:
            self.open[raw][1] = sock
            return not self.stopping

    def _serve(self, raw, addr):
        sock = raw
        try:
            raw.settimeout(HANDSHAKE)    # the handshake's total time, not each wait (ssl docs: do_handshake, 3.5)
            sock = self.ctx.wrap_socket(raw, server_side=True, do_handshake_on_connect=False)
            if not self._swap(raw, sock):
                return
            sock.do_handshake()
            sock.settimeout(IDLE)
            self.RequestHandlerClass(sock, addr, self)
        except Exception:                                 # a failed handshake, a timeout, a handler's error: closed
            pass
        finally:
            with self.lock:
                self.open.pop(raw, None)
            _shut(sock)
            sock.close()
            self.slots.release()

    def stop(self) -> None:
        """Stop accepting, shut every open connection (mid-handshake or idle), join their threads (JOIN in all)."""
        with self.lock:
            if self.stopped:
                return
            self.stopping = self.stopped = True
        self.shutdown()
        with self.lock:
            held = list(self.open.values())
        for _, s in held:
            _shut(s)
        end = time.monotonic() + JOIN
        for t, _ in held:
            t.join(max(0.0, end - time.monotonic()))
        for _, s in held:
            s.close()
        self.server_close()


def start(handler_cls, bind: str, port: int, ctx) -> Listener:
    """The listener on ``bind:port`` (0: any free port; ``server_address`` says which), accepting in a thread."""
    lst = Listener((bind, port), handler_cls, ctx)
    threading.Thread(target=lst.serve_forever, kwargs={"poll_interval": 0.2}, name="ergostat-tls-accept",
                     daemon=True).start()
    return lst


def serve(conf, root, page, port: int | None = None) -> tuple[Listener | None, str]:
    """``web.mtls`` started beside the page (handler class ``page``): the listener and what to say, or None and why
    not. ``port`` overrides the configured one (0 in the tests, so no two take the same)."""
    from . import mtls
    try:
        ctx = mtls.server_context(conf, root)
        lst = start(handler(page), conf.bind, conf.port if port is None else port, ctx)
    except (mtls.MtlsError, OSError) as e:
        return None, f"remote API over mutual TLS: not listening: {e}"
    host, bound = lst.server_address[:2]
    return lst, f"remote API over mutual TLS: https://{host}:{bound}"
