"""The only way out of the sandbox: a filtering HTTP(S) proxy on 127.0.0.1 (a free system port), or a Unix socket that
bwrap binds in. It admits a listed host only: by the CONNECT host, which the TLS ClientHello's server name must agree
with, or by a plain request's absolute URL, whose ``Host`` it rewrites. It resolves names itself (no DNS inside), logs
every connection asked for, and holds a host to its methods: for plain HTTP each request (one per connection; bodies by
``Content-Length`` only), for HTTPS only whether the tunnel opens, since what runs inside TLS cannot be seen. A
method-limited host gets no tunnel unless the policy lists it in ``tls_unchecked``."""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
from urllib.parse import urlsplit

HEAD_MAX = 65536
DROP = {"connection", "keep-alive", "proxy-connection", "proxy-authorization", "host", "te", "upgrade"}


def sni(hello: bytes) -> str | None:
    """The server name in a TLS ClientHello (None: not TLS, or no name)."""
    try:
        if hello[0] != 0x16 or hello[5] != 1:
            return None
        i = 9 + 2 + 32
        i += 1 + hello[i]                                       # session id
        i += 2 + int.from_bytes(hello[i:i + 2], "big")          # cipher suites
        i += 1 + hello[i]                                       # compression
        end = i + 2 + int.from_bytes(hello[i:i + 2], "big")
        i += 2
        while i + 4 <= end:
            kind, n = int.from_bytes(hello[i:i + 2], "big"), int.from_bytes(hello[i + 2:i + 4], "big")
            if kind == 0:
                return hello[i + 9:i + 9 + int.from_bytes(hello[i + 7:i + 9], "big")].decode("ascii").lower()
            i += 4 + n
    except (IndexError, UnicodeDecodeError):
        return None
    return None


class Proxy:
    def __init__(self, hosts: dict, tls_unchecked=(), unix: bool = False):
        self.rules = {self._key(h): (None if m is None else {x.upper() for x in m}) for h, m in hosts.items()}
        self.unchecked = {self._key(h) for h in tls_unchecked}
        self.log: list[dict] = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(64)
        self.port = self.sock.getsockname()[1]
        self.listeners = [self.sock]
        self.unix = None
        if unix:
            self.unix = os.path.join(tempfile.mkdtemp(), "proxy.sock")
            u = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            u.bind(self.unix)
            u.listen(64)
            self.listeners.append(u)
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
            try:
                c, _ = s.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _note(self, method, host, port, ok, why):
        self.log.append({"time": round(time.time(), 3), "method": method, "host": host, "port": port,
                         "allowed": ok, "why": why})

    def _serve(self, c: socket.socket):
        c.settimeout(30)
        with c:
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
        while first[:1] == b"\x16" and len(first) < min(5 + int.from_bytes(first[3:5] or b"\0\0", "big"), 16389):
            chunk = c.recv(16384)              # the whole ClientHello: its name may not be split away from the check
            if not chunk:
                return
            first += chunk
        name = sni(first)
        if name is not None and name != self._key(host):
            self._note("CONNECT", name, port, False, f"TLS server name {name} is not {host}")
            return
        with socket.create_connection((host, port), timeout=30) as up:
            up.sendall(first)
            self._relay(c, up, both=True)

    def _forward(self, c, method, u, version, headers, rest):
        fields = [h for h in headers if h and h.split(":", 1)[0].strip().lower() not in DROP]
        names = {h.split(":", 1)[0].strip().lower(): h.split(":", 1)[1].strip() for h in fields if ":" in h}
        if "transfer-encoding" in names:
            c.sendall(b"HTTP/1.1 411 Length Required\r\n\r\n")
            return
        need = int(names.get("content-length", "0") or 0)
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
            except OSError:
                pass
            try:
                b.shutdown(socket.SHUT_WR)
            except OSError:
                pass
        if both:
            t = threading.Thread(target=pipe, args=(c, up), daemon=True)
            t.start()
        pipe(up, c)
