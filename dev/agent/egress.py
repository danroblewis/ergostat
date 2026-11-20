"""The agents' only way out: an HTTP CONNECT proxy that tunnels to the hosts it is given (port 443 only) and refuses
everything else. It runs in a container of its own on two networks, the agents' internal one (no route out) and an
ordinary one; a session's container is on the internal network alone, with HTTPS_PROXY pointing here.

    python3 egress.py PORT HOST [HOST ...]       (dev/bin/agents.py starts it: docker container ergostat-egress)

A tunnel is opened only when the client's TLS hello names the same host as its CONNECT (its SNI), so a CONNECT to an
allowed name cannot be pointed elsewhere. Each request is logged to standard error: when, what, allowed or why not."""

from __future__ import annotations

import socket
import sys
import threading
import time

ALLOWED: set[str] = set()


def log(*what) -> None:
    print(time.strftime("%H:%M:%S"), *what, file=sys.stderr, flush=True)


def sni(hello: bytes) -> str | None:
    """The server name of a TLS ClientHello (RFC 6066), or None."""
    try:
        if hello[0] != 0x16 or hello[5] != 0x01:
            return None
        i = 9 + 2 + 32                                   # record and handshake headers, version, random
        i += 1 + hello[i]                                # session id
        i += 2 + int.from_bytes(hello[i:i + 2], "big")   # cipher suites
        i += 1 + hello[i]                                # compression
        end = i + 2 + int.from_bytes(hello[i:i + 2], "big")
        i += 2
        while i + 4 <= end:
            kind, size = int.from_bytes(hello[i:i + 2], "big"), int.from_bytes(hello[i + 2:i + 4], "big")
            if kind == 0:                                # server_name: list, type, length, name
                n = int.from_bytes(hello[i + 7:i + 9], "big")
                return hello[i + 9:i + 9 + n].decode("ascii", "replace").lower()
            i += 4 + size
    except IndexError:
        return None
    return None


def pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while data := a.recv(65536):
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def serve(c: socket.socket) -> None:
    try:
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 8192:
            got = c.recv(4096)
            if not got:
                return
            head += got
        line = head.split(b"\r\n", 1)[0].decode("latin-1")
        method, target, *_ = (line.split() + ["", ""])[:3]
        host, _, port = target.rpartition(":")
        host = host.strip("[]").lower()
        if method != "CONNECT" or port != "443" or host not in ALLOWED:
            log("refused", line)
            c.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            return
        c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        hello = head.split(b"\r\n\r\n", 1)[1] or c.recv(65536)
        name = sni(hello)
        if name != host:
            log("refused", line, f"(TLS server name {name!r})")
            return
        up = socket.create_connection((host, 443), timeout=30)
        up.settimeout(None)
        up.sendall(hello)
        log("tunnel", host)
        t = threading.Thread(target=pipe, args=(up, c), daemon=True)
        t.start()
        pipe(c, up)
        t.join(timeout=5)
    except OSError as e:
        log("error", type(e).__name__, e)
    finally:
        c.close()


def main(argv: list[str]) -> int:
    port, hosts = int(argv[0]), argv[1:]
    ALLOWED.update(h.lower() for h in hosts)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.listen(64)
    log("allowing", ", ".join(sorted(ALLOWED)), "on", port)
    while True:
        c, _ = s.accept()
        threading.Thread(target=serve, args=(c,), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
