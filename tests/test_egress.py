"""dev/agent/egress.py, the sessions' only way out: under `*` (the researcher's proxy) any name on 443 whose TLS server
name matches its CONNECT, unless an address it resolves to is not global; refused with the reason logged."""

from __future__ import annotations

import importlib.util
import socket
import threading
import time

import pytest

from tests.test_factory import ROOT


@pytest.fixture
def egress(monkeypatch):
    spec = importlib.util.spec_from_file_location("egress_under_test", ROOT / "dev" / "agent" / "egress.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.said = []
    monkeypatch.setattr(mod, "log", lambda *what: mod.said.append(" ".join(map(str, what))))
    mod.dialled = []

    def connect(addr, timeout=None):                   # never the network: the far end is a socket pair's
        here, mod.far = socket.socketpair()
        mod.dialled.append(addr)                       # (after far: ask() reads far once it sees this)
        return here
    monkeypatch.setattr(mod.socket, "create_connection", connect)
    return mod


def hello(name: str) -> bytes:
    """A TLS ClientHello naming ``name`` (RFC 6066 server_name), as sni() reads it."""
    n = name.encode()
    ext = (0).to_bytes(2, "big") + (len(n) + 5).to_bytes(2, "big") + (len(n) + 3).to_bytes(2, "big") + b"\x00" + \
        len(n).to_bytes(2, "big") + n
    body = b"\x03\x03" + b"\x00" * 32 + b"\x00" + b"\x00\x02\x13\x01" + b"\x01\x00" + len(ext).to_bytes(2, "big") + ext
    hs = b"\x01" + len(body).to_bytes(3, "big") + body
    return b"\x16\x03\x01" + len(hs).to_bytes(2, "big") + hs


def ask(egress, target: str, sni: str | None = None) -> bytes:
    """One CONNECT to ``target`` (host:port) with a hello naming ``sni`` (default: its host); what the client read."""
    host = target.rpartition(":")[0].strip("[]")
    client, server = socket.socketpair()
    client.settimeout(5)
    t = threading.Thread(target=egress.serve, args=(server,), daemon=True)
    t.start()
    client.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode() + hello(sni or host))
    got = client.recv(4096)
    for _ in range(500):                              # (the 200 is sent before the hello is read: wait for either)
        if egress.dialled or not t.is_alive() or b" 200 " not in got:
            break
        time.sleep(0.01)
    if b" 200 " in got and egress.dialled:            # a tunnel: the hello reached the far end; then closed
        egress.far.settimeout(5)
        assert egress.far.recv(65536) == hello(sni or host)
        egress.far.close()
    client.close()
    t.join(timeout=5)
    assert not t.is_alive()
    return got


ADDRS = {"public.example": ["93.184.215.14", "2606:2800:21f:cb07:6820:80da:af6b:8b2c"],
         "loop.example": ["127.0.0.1"], "ten.example": ["10.1.2.3"], "corp.example": ["172.20.0.5"],
         "home.example": ["192.168.1.10"], "meta.example": ["169.254.169.254"], "six.example": ["::1"],
         "mixed.example": ["93.184.215.14", "10.0.0.7"], "mapped.example": ["::ffff:127.0.0.1"],
         "127.0.0.1": ["127.0.0.1"], "::1": ["::1"], "none.example": [], "cast.example": ["233.252.0.1"]}


def resolver(name: str) -> list[str]:
    if name not in ADDRS:
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
    return ADDRS[name]


def test_star_allows_public_refuses_private(egress, monkeypatch):
    monkeypatch.setattr(egress, "ALLOWED", {"api.anthropic.com", "*"})
    asked = []
    monkeypatch.setattr(egress, "resolve", lambda name: asked.append(name) or resolver(name))
    # a public name: tunnelled, to the address checked (no second lookup), its hello passed on
    assert b"200 Connection established" in ask(egress, "public.example:443")
    assert egress.dialled == [("93.184.215.14", 443)] and asked == ["public.example"]
    assert egress.said[-1] == "tunnel public.example 93.184.215.14"
    # each private kind, and a name with one private address among public ones: refused, the reason logged
    why = {"loop.example": "127.0.0.1 (loopback)", "ten.example": "10.1.2.3 (private)",
           "corp.example": "172.20.0.5 (private)", "home.example": "192.168.1.10 (private)",
           "meta.example": "169.254.169.254 (link-local)", "six.example": "::1 (loopback)",
           "mixed.example": "10.0.0.7 (private)", "mapped.example": "::ffff:127.0.0.1 (loopback)",
           "127.0.0.1": "127.0.0.1 (loopback)", "cast.example": "233.252.0.1 (multicast)"}
    for name, reason in why.items():
        egress.dialled.clear()
        assert b"403 Forbidden" in ask(egress, f"{name}:443"), name
        assert not egress.dialled, name
        assert egress.said[-1] == f"refused CONNECT {name}:443 HTTP/1.1 (resolves to {reason})", name
    assert b"403" in ask(egress, "[::1]:443") and egress.said[-1].endswith("(resolves to ::1 (loopback))")
    # a name that resolves to nothing, or not at all: refused (never "fine")
    assert b"403" in ask(egress, "none.example:443") and egress.said[-1].endswith("(resolves to no address)")
    assert b"403" in ask(egress, "gone.example:443") and egress.said[-1].endswith("(does not resolve (gaierror))")
    # still 443 alone, and still CONNECT alone; `*` itself names no host; a listed host is not looked up
    asked.clear()
    for line in ("public.example:80", "*:443"):
        assert b"403" in ask(egress, line) and egress.said[-1] == f"refused CONNECT {line} HTTP/1.1"
    assert not asked
    egress.dialled.clear()
    assert b"200" in ask(egress, "api.anthropic.com:443")
    assert egress.dialled == [("api.anthropic.com", 443)] and not asked
    # without `*` (the first proxy): only the listed names, none looked up
    monkeypatch.setattr(egress, "ALLOWED", {"api.anthropic.com"})
    egress.dialled.clear()
    assert b"403" in ask(egress, "public.example:443") and not egress.dialled and not asked
    assert egress.said[-1] == "refused CONNECT public.example:443 HTTP/1.1"


def test_sni_mismatch_still_refused_under_star(egress, monkeypatch):
    monkeypatch.setattr(egress, "ALLOWED", {"api.anthropic.com", "*"})
    monkeypatch.setattr(egress, "resolve", resolver)
    for target, sni in (("public.example:443", "loop.example"), ("public.example:443", "api.anthropic.com"),
                        ("api.anthropic.com:443", "public.example")):
        egress.dialled.clear()
        got = ask(egress, target, sni)
        assert b"200" in got and not egress.dialled, (target, sni)        # (the hello read after the 200: never dialled)
        assert egress.said[-1] == f"refused CONNECT {target} HTTP/1.1 (TLS server name {sni!r})"


def test_the_real_resolver_reads_addresses():
    spec = importlib.util.spec_from_file_location("egress_resolve", ROOT / "dev" / "agent" / "egress.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "127.0.0.1" in mod.resolve("127.0.0.1")                      # (a literal: no lookup leaves the machine)
    assert mod.public("127.0.0.1") == (None, "resolves to 127.0.0.1 (loopback)")
    assert mod.public("8.8.8.8") == ("8.8.8.8", "")
