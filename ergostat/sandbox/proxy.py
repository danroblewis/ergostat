"""The only way out of the sandbox: a filtering HTTP(S) proxy on 127.0.0.1 (or a Unix socket bwrap binds in) that
admits listed hosts only, resolves names itself, logs every connection, and holds a host to its methods for plain HTTP
(for HTTPS only whether the tunnel opens). SPEC §12q."""

from __future__ import annotations

import contextlib
import os
import socket
import tempfile
import threading
import time
from urllib.parse import urlsplit

HEAD_MAX = 65536
HELLO_MAX = 1 << 17
MOST = 64                          # connections served at once; more wait to be accepted
DROP = {"connection", "keep-alive", "proxy-connection", "proxy-authorization", "host", "te", "upgrade"}


def sni(msg: bytes) -> str | None:
    """The server name in a ClientHello handshake message (its 4-byte header first); None: none or unparseable."""
    try:
        if msg[0] != 1:
            return None
        i = 4 + 2 + 32
        i += 1 + msg[i]                                         # session id
        i += 2 + int.from_bytes(msg[i:i + 2], "big")            # cipher suites
        i += 1 + msg[i]                                         # compression
        end = i + 2 + int.from_bytes(msg[i:i + 2], "big")
        i += 2
        while i + 4 <= end:
            kind, n = int.from_bytes(msg[i:i + 2], "big"), int.from_bytes(msg[i + 2:i + 4], "big")
            if kind == 0:
                return msg[i + 9:i + 9 + int.from_bytes(msg[i + 7:i + 9], "big")].decode("ascii").lower() or None
            i += 4 + n
    except (IndexError, UnicodeDecodeError):
        return None
    return None


def hello(c: socket.socket, data: bytes) -> tuple[bytes, bytes] | None:
    """Read TLS records until the first handshake message is whole, across as many records as it was split into.
    Returns (the bytes read, the message); None if the stream is TLS but not a handshake, or ends first."""
    msg, i = b"", 0
    while len(msg) < 4 or len(msg) < 4 + int.from_bytes(msg[1:4], "big"):
        while len(data) < i + 5 or len(data) < i + 5 + int.from_bytes(data[i + 3:i + 5], "big"):
            chunk = c.recv(16384)
            if not chunk or len(data) > HELLO_MAX:
                return None
            data += chunk
        if data[i] != 0x16:
            return None
        n = int.from_bytes(data[i + 3:i + 5], "big")
        msg, i = msg + data[i + 5:i + 5 + n], i + 5 + n
    return data, msg


def _listen(family, address) -> socket.socket:
    s = socket.socket(family, socket.SOCK_STREAM)
    s.bind(address)
    s.listen(64)
    return s


class Proxy:
    def __init__(self, hosts: dict, tls_unchecked=(), unix: bool = False):
        self.rules = {self._key(h): (None if m is None else {x.upper() for x in m}) for h, m in hosts.items()}
        self.unchecked = {self._key(h) for h in tls_unchecked}
        self.log: list[dict] = []
        self.listeners = [_listen(socket.AF_INET, ("127.0.0.1", 0))]
        self.port = self.listeners[0].getsockname()[1]
        self.slots = threading.BoundedSemaphore(MOST)
        self.unix = os.path.join(tempfile.mkdtemp(), "proxy.sock") if unix else None
        if unix:
            self.listeners.append(_listen(socket.AF_UNIX, self.unix))
        for s in self.listeners:
            threading.Thread(target=self._accept, args=(s,), daemon=True).start()

    @staticmethod
    def _key(h: str) -> str:
        return h.lower().strip("[]")

    def allowed(self, host: str, port: int, method: str | None) -> tuple[bool, str]:
        host = self._key(host)
        rule = self.rules.get(f"{host}:{port}", self.rules.get(host, False) if port in (80, 443) else False)
        if rule is False:
            return False, "host not listed"
        if rule is None:
            return True, "listed"
        if method is None:
            ok = f"{host}:{port}" in self.unchecked or host in self.unchecked
            return ok, "listed; methods unchecked inside TLS" if ok else "methods cannot be checked inside TLS"
        return (method in rule), "listed" if method in rule else f"method {method} not allowed"

    def close(self):
        for s in self.listeners:
            s.close()
        if self.unix:
            try:
                os.unlink(self.unix)
                os.rmdir(os.path.dirname(self.unix))
            except OSError:
                pass

    def _accept(self, s: socket.socket):
        while True:
            self.slots.acquire()            # at most MOST connections served at once; the rest wait in the backlog
            try:
                c, _ = s.accept()
            except OSError:
                self.slots.release()
                return
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _note(self, method, host, port, ok, why):
        self.log.append({"time": round(time.time(), 3), "method": method, "host": host, "port": port,
                         "allowed": ok, "why": why})

    def _serve(self, c: socket.socket):
        c.settimeout(30)
        with c, contextlib.ExitStack() as done:
            done.callback(self.slots.release)
            head = b""
            while b"\r\n\r\n" not in head and len(head) < HEAD_MAX:
                chunk = c.recv(4096)
                if not chunk:
                    return
                head += chunk
            head, _, rest = head.partition(b"\r\n\r\n")
            lines = head.decode("latin-1").split("\r\n")
            try:
                method, target, version = lines[0].split(" ")
                if method == "CONNECT":
                    host, _, port = target.rpartition(":")
                    port = int(port)
                else:
                    u = urlsplit(target)
                    host, port = u.hostname or "", u.port or 80
                    if u.scheme != "http":
                        raise ValueError(target)
            except ValueError:
                c.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return
            ok, why = self.allowed(host, port, None if method == "CONNECT" else method)
            self._note(method, host, port, ok, why)
            if not ok:
                c.sendall(f"HTTP/1.1 403 Forbidden\r\nContent-Length: {len(why)}\r\n\r\n{why}".encode())
                return
            try:
                if method == "CONNECT":
                    self._tunnel(c, host, port, rest)
                else:
                    self._forward(c, method, u, version, lines[1:], rest)
            except OSError as e:
                self._note(method, host, port, False, f"upstream: {e}")

    def _tunnel(self, c, host, port, rest):
        c.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        first = rest or c.recv(16384)
        if first[:1] == b"\x16":              # TLS: the server name must be there, and be the CONNECT host
            got = hello(c, first)
            name = sni(got[1]) if got else None
            if name != self._key(host):
                self._note("CONNECT", name or "", port, False, f"TLS server name {name or 'missing'} is not {host}")
                return
            first = got[0]
        with socket.create_connection((host, port), timeout=30) as up:
            up.sendall(first)
            self._relay(c, up, both=True)

    def _forward(self, c, method, u, version, headers, rest):
        fields = [h for h in headers if h and h.split(":", 1)[0].strip().lower() not in DROP]
        named = [(h.split(":", 1)[0].strip().lower(), h.partition(":")[2].strip()) for h in fields]
        lengths = [v for k, v in named if k == "content-length"]
        if len(lengths) > 1 or "transfer-encoding" in dict(named):      # one body, one length: nothing smuggled
            c.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return
        need = int(lengths[0] if lengths else 0)
        while len(rest) < need:
            chunk = c.recv(65536)
            if not chunk:
                return
            rest += chunk
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        host = f"Host: {u.hostname}" + (f":{u.port}" if u.port else "")
        req = "\r\n".join([f"{method} {path} {version}", host, *fields, "Connection: close", "", ""])
        with socket.create_connection((u.hostname, u.port or 80), timeout=30) as up:
            up.sendall(req.encode("latin-1") + rest[:need])
            self._relay(c, up, both=False)

    @staticmethod
    def _relay(c, up, both: bool):
        def pipe(a, b):
            try:
                for chunk in iter(lambda: a.recv(65536), b""):
                    b.sendall(chunk)
                b.shutdown(socket.SHUT_WR)
            except OSError:
                pass
        if both:
            t = threading.Thread(target=pipe, args=(c, up), daemon=True)
            t.start()
        pipe(up, c)
