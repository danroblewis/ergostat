"""Mutual TLS for remote systems (SPEC §4c): ``web: mtls:`` serving the remote API on a listener of its own, and a
remote's ``tls:`` read over it. Every test runs on the wire with real certificates (``tests/tlscerts.py``)."""

import http.client
import json
import socket
import ssl
import threading
import time
import types
import urllib.request
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import spec as sp
from ergostat.remote import cache, client, listen, mtls, readings, tokens
from ergostat.spec.ir import Source
from ergostat.store import Project
from ergostat.web import serve as web_serve
from ergostat.web import server as page_server
from tests.ports import free_port
from tests.tlscerts import certs  # noqa: F401  (the session's certificates)

MODEL = """
name: incidents
stocks:
  open:
    unit: incidents
    sensor: {run: echo 3, every: 5s}
web:
  mtls:
    port: PORT
    bind: 127.0.0.1
    cert: CERT
    key: KEY
    client-ca: CA
"""


def write_model(d: Path, cs, port=8796, cert=None, key=None, ca=None) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    text = (MODEL.replace("PORT", str(port)).replace("CERT", str(cert or cs["server"]))
            .replace("KEY", str(key or cs["server_key"])).replace("CA", str(ca or cs["ca"])))
    (d / "ergostat.yaml").write_text(text)
    return d


def tls_of(cs, cert="client", ca="ca") -> dict:
    return {"cert": str(cs[cert]), "key": str(cs[f"{cert}_key"]), "ca": str(cs[ca])}


def until(what, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if what():
            return True
        time.sleep(0.05)
    return bool(what())


def mtls_threads() -> list[str]:
    return [t.name for t in threading.enumerate() if t.name.startswith("ergostat-mtls-") and t.is_alive()]


def eof(s, seconds: float) -> bool:
    """The server closed ``s`` (EOF or reset) within ``seconds``."""
    deadline = time.monotonic() + seconds
    s.settimeout(0.05)
    while time.monotonic() < deadline:
        try:
            if s.recv(4096) == b"":
                return True
        except (TimeoutError, ssl.SSLWantReadError):
            continue
        except OSError:                                # reset, or a TLS alert/EOF
            return True
    return False


def tls_sock(port: int, cs, cert: str | None = "client"):
    ctx = ssl.create_default_context(cafile=str(cs["ca"]))
    if cert:
        ctx.load_cert_chain(cs[cert], cs[f"{cert}_key"])
    return ctx.wrap_socket(socket.create_connection(("127.0.0.1", port), timeout=5), server_hostname="127.0.0.1")


def raw(port: int):
    return socket.create_connection(("127.0.0.1", port), timeout=5)


def https(port: int, path: str, token=None, cert="client", method="GET") -> tuple[int, bytes | None]:
    """A request as written (the path not normalised), over mutual TLS: (status, body), status 0 when refused."""
    ctx = ssl.create_default_context(cafile=_CERTS["ca"])
    if cert:
        ctx.load_cert_chain(_CERTS[cert], _CERTS[f"{cert}_key"])
    c = http.client.HTTPSConnection("127.0.0.1", port, context=ctx, timeout=10)
    try:
        c.putrequest(method, path, skip_accept_encoding=True)
        if token:
            c.putheader("Authorization", f"Bearer {token}")
        c.endheaders()
        r = c.getresponse()
        return r.status, r.read()
    except (OSError, http.client.HTTPException):
        return 0, None
    finally:
        c.close()


_CERTS: dict = {}


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch):
    """The loopback listener asked directly, whatever proxy this machine's environment names."""
    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")


@pytest.fixture
def page(tmp_path, certs):  # noqa: F811
    """The remote's page served with ``web: mtls:`` (its port 0, read back as ``server.mtls_port``), and a token."""
    _CERTS.update({k: str(v) for k, v in certs.items()})
    p = Project(mdl.load(write_model(tmp_path / "incidents", certs)))
    server, url = web_serve(p, free_port(), mtls_port=0)
    tok = tokens.issue(p.dir, f"support-{tmp_path.name}")
    yield types.SimpleNamespace(server=server, url=url, token=tok, project=p, port=server.mtls_port)
    server.shutdown()
    server.server_close()


@pytest.fixture
def lst(tmp_path, certs):  # noqa: F811
    """``listen.start`` on port 0 with the page's handler, for the tests of the listener alone."""
    _CERTS.update({k: str(v) for k, v in certs.items()})
    p = Project(mdl.load(write_model(tmp_path / "incidents", certs)))
    tok = tokens.issue(p.dir, f"support-{tmp_path.name}")
    made = []

    def start(cert="server"):
        conf = mtls.Mtls(0, "127.0.0.1", str(certs[cert]), str(certs[f"{cert}_key"]), str(certs["ca"]))
        h = listen.handler(page_server.handler(p))
        got = listen.start(h, "127.0.0.1", 0, mtls.server_context(conf, None))
        made.append(got)
        return types.SimpleNamespace(lst=got, port=got.server_address[1], token=tok, handler=h)
    yield start
    for m in made:
        m.stop()


def test_a_remote_is_read_over_mutual_tls_end_to_end(page, certs, tmp_path):  # noqa: F811
    assert page.server.mtls is not None and page.server.mtls_said.endswith(f"https://127.0.0.1:{page.port}")
    url = f"https://127.0.0.1:{page.port}"
    (tmp_path / "t.token").write_text(page.token)
    d = tmp_path / "cache"
    d.mkdir()
    st = cache.refresh(d, url, "t.token", tmp_path, 60.0, force=True, tls=tls_of(certs))
    assert st["ok"] is True, st
    assert cache.model(d)["name"] == "incidents"
    src = Source("incidents", "ergostat", url, None, "t.token", tls_of(certs))
    spec = types.SimpleNamespace(root=tmp_path, remotes={}, sensors=lambda: [])
    readings._kept.clear()
    body, why = readings.answer(spec, src, 60.0)
    assert body is not None and why == "", why
    code, st, _, why = client.get(url, "status", page.token, tls=tls_of(certs))
    assert code == 200 and st["name"] == "incidents", why


def test_a_client_without_a_certificate_or_with_another_cas_is_refused(page, certs):  # noqa: F811
    assert https(page.port, "/api/remote/v1/status", page.token, cert=None) == (0, None)
    code, body, _, why = client.get(f"https://127.0.0.1:{page.port}", "status", page.token,
                                    tls=tls_of(certs, cert="stranger"))
    assert code == 0 and body is None and why
    code, body, _, _ = client.get(f"https://127.0.0.1:{page.port}", "status", page.token, tls=tls_of(certs))
    assert code == 200 and body["name"] == "incidents"


def test_a_server_whose_certificate_names_another_host_is_refused(lst, certs):  # noqa: F811
    wrong = lst("wrong")
    code, body, _, why = client.get(f"https://127.0.0.1:{wrong.port}", "status", wrong.token, tls=tls_of(certs))
    assert code == 0 and body is None and "mismatch" in why.lower(), why
    right = lst("server")
    code, body, _, why = client.get(f"https://127.0.0.1:{right.port}", "status", right.token, tls=tls_of(certs))
    assert code == 200, why


def test_both_contexts_require_tls_1_2_and_verification(certs):  # noqa: F811
    conf = mtls.Mtls(1, "127.0.0.1", str(certs["server"]), str(certs["server_key"]), str(certs["ca"]))
    s = mtls.server_context(conf, None)
    assert s.minimum_version >= ssl.TLSVersion.TLSv1_2 and s.verify_mode == ssl.CERT_REQUIRED
    c = mtls.client_context(tls_of(certs))
    assert c.minimum_version >= ssl.TLSVersion.TLSv1_2 and c.check_hostname is True
    assert c.verify_mode == ssl.CERT_REQUIRED
    c = mtls.client_context({k: v for k, v in tls_of(certs).items() if k != "ca"})   # the system's trust, as strict
    assert c.minimum_version >= ssl.TLSVersion.TLSv1_2 and c.check_hostname and c.verify_mode == ssl.CERT_REQUIRED


def test_an_unreadable_client_ca_fails_the_read_and_never_uses_the_systems_trust(lst, certs, tmp_path,  # noqa: F811
                                                                                  monkeypatch):
    srv = lst()
    calls = []
    real_default, real_certs = ssl.create_default_context, ssl.SSLContext.load_default_certs

    def default(*a, **kw):
        calls.append(("create_default_context", kw.get("cafile") or (a[1] if len(a) > 1 else None)))
        return real_default(*a, **kw)

    def default_certs(self, *a, **kw):
        calls.append(("load_default_certs", None))
        return real_certs(self, *a, **kw)
    monkeypatch.setattr(ssl, "create_default_context", default)
    monkeypatch.setattr(ssl.SSLContext, "load_default_certs", default_certs)
    (tmp_path / "not.pem").write_text("not a certificate\n")
    (tmp_path / "adir").mkdir()
    url = f"https://127.0.0.1:{srv.port}"
    for bad in (tmp_path / "missing.pem", tmp_path / "adir", tmp_path / "not.pem"):
        code, body, _, why = client.get(url, "status", srv.token, tls={**tls_of(certs), "ca": str(bad)})
        assert code == 0 and body is None and why.startswith("tls: ca "), why
    for which in ("cert", "key"):
        for bad in (tmp_path / "missing.pem", tmp_path / "not.pem"):
            code, body, _, why = client.get(url, "status", srv.token, tls={**tls_of(certs), which: str(bad)})
            assert code == 0 and body is None and why.startswith(f"tls: {which} "), why
    assert srv.lst.accepted == 0                                # nothing was sent: never a weaker try
    assert not [c for c in calls if c[1] is None], calls        # never the system's trust


@pytest.mark.parametrize("which,how", [(w, h) for w in ("cert", "key", "client-ca") for h in ("missing", "dir", "notpem")]
                         + [("key", "mismatch")])
def test_an_unreadable_server_file_binds_nothing_and_the_page_still_serves(tmp_path, certs, monkeypatch, capsys,  # noqa: F811
                                                                         which, how):
    from ergostat.cli import main, running
    (tmp_path / "not.pem").write_text("not a certificate\n")
    (tmp_path / "adir").mkdir()
    bad = {"missing": tmp_path / "missing.pem", "dir": tmp_path / "adir", "notpem": tmp_path / "not.pem",
           "mismatch": certs["client_key"]}[how]
    hold = socket.socket()                    # the configured port, held bound and not listening: nothing else takes it
    hold.bind(("127.0.0.1", 0))
    port = hold.getsockname()[1]
    try:
        d = write_model(tmp_path / "m", certs, port=port, **{{"client-ca": "ca"}.get(which, which): bad})
        assert main(["-C", str(d), "check", "--json"]) != 0
        found = json.loads(capsys.readouterr().out)["found"]
        assert [f for f in found if f["code"] == "mtls-unreadable" and f"web.mtls.{which} " in f["message"]], found
        starts = []
        monkeypatch.setattr(listen, "start", lambda *a, **kw: starts.append(a))
        server, url = web_serve(Project(mdl.load(d)), free_port())
        try:
            with urllib.request.urlopen(f"{url}/api/status", timeout=10) as r:
                assert r.status == 200
            with pytest.raises(ConnectionRefusedError):
                socket.create_connection(("127.0.0.1", port), timeout=5).close()
            assert server.mtls is None and server.mtls_port is None and not starts
            assert "not listening" in server.mtls_said and f"web.mtls.{which} {bad}: " in server.mtls_said
        finally:
            server.shutdown()
            server.server_close()

        def stop(_):
            raise KeyboardInterrupt
        monkeypatch.setattr(running, "time", types.SimpleNamespace(sleep=stop, time=time.time))
        assert main(["-C", str(d), "web", "--port", str(free_port())]) == 0
        out = capsys.readouterr().out
        assert f"remote API over mutual TLS: not listening: web.mtls.{which} {bad}: " in out, out
    finally:
        hold.close()


def _problems(d: Path, text: str):
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(text)
    return sp.read(d / "ergostat.yaml", extremes=False)


def test_mtls_config_is_checked(tmp_path, certs):  # noqa: F811
    good = MODEL.replace("CERT", str(certs["server"])).replace("KEY", str(certs["server_key"])).replace("CA", str(certs["ca"]))
    _, problems = _problems(tmp_path / "ok", good.replace("PORT", "8796"))
    assert not [p for p in problems if p.level == "error"], problems
    for i, text in enumerate([good.replace("PORT", "8796").replace(f"    client-ca: {certs['ca']}\n", ""),
                              good.replace("PORT", "0"), good.replace("PORT", "70000"),
                              good.replace("PORT", "8796").replace("bind: 127.0.0.1", "bind: somewhere"),
                              good.replace("PORT", "8796").replace("bind: 127.0.0.1", "bind: 127.0.0.1\n    most: 64")]):
        _, problems = _problems(tmp_path / f"web{i}", text)
        assert [p for p in problems if p.code == "bad-web"], (i, problems)
    remote = """
name: support
systems:
  incidents:
    remote:
      url: URL
      token-file: incidents.token
      tls: TLS
stocks:
  tickets:
    sensor: {run: echo 3}
"""
    tls = f"{{cert: {certs['client']}, key: {certs['client_key']}, ca: {certs['ca']}}}"
    for i, (url, t) in enumerate([("http://127.0.0.1:1", tls), ("https://127.0.0.1:1", tls.replace(", key:", ", nokey:")),
                                  ("https://127.0.0.1:1", tls.replace("}", ", pin: x}"))]):
        _, problems = _problems(tmp_path / f"remote{i}", remote.replace("URL", url).replace("TLS", t))
        assert [p for p in problems if p.code == "bad-remote" and "tls" in p.message], (i, problems)
    spec, problems = _problems(tmp_path / "remote-ok", remote.replace("URL", "https://127.0.0.1:1").replace("TLS", tls))
    assert not [p for p in problems if p.level == "error"], problems
    want = {"cert": str(certs["client"]), "key": str(certs["client_key"]), "ca": str(certs["ca"])}
    assert spec.remotes["incidents"]["tls"] == want and spec.sources["incidents"].tls == want
    spec, problems = _problems(tmp_path / "remote-bad-file",
                               remote.replace("URL", "https://127.0.0.1:1").replace("TLS", tls.replace(str(certs["ca"]),
                                                                                                         "missing.pem")))
    assert [p for p in problems if p.code == "mtls-unreadable" and "tls.ca" in p.message], problems


NOT_SERVED = ["/api/remote/v1x/status", "/api/remote/v1/../../api/status", "/api/remote/v1/%2e%2e/%2e%2e/api/status",
              "/api/remote/v1/status/../../../api/status", "/api/remote//v1/status", "/api/status", "/", "/static/app.js",
              "/api/file?path=ergostat.yaml", "/api/remote/v1/status%2F..%2F..%2Fapi%2Fstatus", "/api/remote/v1/", "/api/remote/v2/status"]


def test_only_get_of_the_remote_api_is_served(page, monkeypatch):
    reached = []
    h = page.server.mtls.RequestHandlerClass
    real = h._remote

    def counted(self, u):
        reached.append(self.path)
        return real(self, u)
    monkeypatch.setattr(h, "_remote", counted)
    with urllib.request.urlopen(f"{page.url}/api/status", timeout=10) as r:
        page_status = r.read()
    for path in NOT_SERVED:
        code, body = https(page.port, path, page.token)
        assert code == 404 and body != page_status and b'"stocks"' not in body, (path, code, body)
    for method in ("HEAD", "POST", "PUT", "DELETE", "OPTIONS"):
        assert https(page.port, "/api/remote/v1/status", page.token, method=method)[0] == 405, method
    assert reached == []                                        # none of them reached the remote API, nor the page
    assert https(page.port, "/api/remote/v1/status")[0] == 401
    code, body = https(page.port, "/api/remote/v1/status", page.token)
    assert code == 200 and json.loads(body)["name"] == "incidents"
    assert https(page.port, "/api/remote/v1/events?after=0&n=2", page.token)[0] == 200    # the query string is no segment
    assert len(reached) == 3


def test_connections_past_sixteen_are_closed_at_once(lst):
    srv = lst()
    assert listen.MOST == 16
    problems = []
    mtls.parse({"port": 1, "cert": "c", "key": "k", "client-ca": "a", "most": 64}, problems)
    assert problems and "most" in problems[0]                  # no setting raises it
    held = [raw(srv.port) for _ in range(listen.MOST)]
    seen = []
    try:
        assert until(lambda: srv.lst.held() == listen.MOST, 10)
        extra = raw(srv.port)
        t0 = time.monotonic()
        assert eof(extra, 1.0), "the 17th connection was not closed at once"
        assert time.monotonic() - t0 < 1.0
        extra.close()
        for _ in range(10):
            seen.append(len(mtls_threads()))
            time.sleep(0.02)
        assert max(seen) <= listen.MOST and srv.lst.held() == listen.MOST
    finally:
        for s in held:
            s.close()


def test_stalled_connections_time_out_and_a_new_client_is_served(lst, certs, monkeypatch):  # noqa: F811
    monkeypatch.setattr(listen, "HANDSHAKE", 3.0)
    monkeypatch.setattr(listen, "IDLE", 3.0)
    srv = lst()
    url = f"https://127.0.0.1:{srv.port}"
    quiet = [tls_sock(srv.port, certs) for _ in range(8)]          # handshakes done, then nothing sent
    stalled = [raw(srv.port) for _ in range(8)]                     # nothing sent at all
    try:
        assert until(lambda: srv.lst.held() == 16, 2.0)
        code, _, _, why = client.get(url, "status", srv.token, tls=tls_of(certs))
        assert code == 0, "a 17th was served while 16 were held"
        assert until(lambda: client.get(url, "status", srv.token, tls=tls_of(certs))[0] == 200, 10.0)
        for s in quiet + stalled:
            assert eof(s, 10.0), "a stalled connection was never closed by the server"
    finally:
        for s in quiet + stalled:
            s.close()


def test_a_handshake_trickled_a_byte_at_a_time_loses_its_slot_at_the_deadline(lst, certs, monkeypatch):  # noqa: F811
    """HANDSHAKE bounds the handshake as a whole, not each wait for a byte: a real ClientHello sent one byte every
    0.2 s (so no single wait comes near the limit) is cut off once HANDSHAKE has passed since the accept."""
    monkeypatch.setattr(listen, "HANDSHAKE", 1.5)
    srv = lst()
    ctx = ssl.create_default_context(cafile=str(certs["ca"]))
    inc, out = ssl.MemoryBIO(), ssl.MemoryBIO()
    obj = ctx.wrap_bio(inc, out, server_hostname="127.0.0.1")
    with pytest.raises(ssl.SSLWantReadError):
        obj.do_handshake()
    hello = out.read()
    assert len(hello) > 100                                      # a hello long enough to outlast the deadline
    s = raw(srv.port)
    t0 = time.monotonic()
    cut = None
    try:
        assert until(lambda: srv.lst.held() == 1, 5.0)
        for b in hello:
            if time.monotonic() - t0 > 6.0:
                break
            try:
                s.sendall(bytes([b]))
            except OSError:
                cut = time.monotonic() - t0
                break
            time.sleep(0.2)
            if srv.lst.held() == 0:
                cut = time.monotonic() - t0
                break
        assert cut is not None, "a trickled handshake kept its slot past HANDSHAKE"
        assert 1.4 <= cut < 1.5 + 3.0                            # at the deadline, not when the hello ran out
        assert eof(s, 5.0)
        assert until(lambda: srv.lst.held() == 0, 5.0)
    finally:
        s.close()


def test_slots_come_back_after_failed_handshakes_and_handler_errors(lst, certs, monkeypatch):  # noqa: F811
    srv = lst()
    url = f"https://127.0.0.1:{srv.port}"
    for _ in range(20):                                          # no client certificate: each handshake refused
        assert https(srv.port, "/api/remote/v1/status", srv.token, cert=None) == (0, None)
    assert until(lambda: srv.lst.held() == 0, 5.0)
    assert client.get(url, "status", srv.token, tls=tls_of(certs))[0] == 200

    def boom(self, u):
        raise RuntimeError("a handler's error")
    with monkeypatch.context() as m:
        m.setattr(srv.handler, "_remote", boom)
        for _ in range(20):
            assert client.get(url, "status", srv.token, tls=tls_of(certs))[0] == 0
    assert until(lambda: srv.lst.held() == 0, 5.0)
    code, _, _, why = client.get(url, "status", srv.token, tls=tls_of(certs))
    assert code == 200, why


@pytest.mark.slow
def test_stopping_the_page_with_connections_open_returns_promptly(tmp_path, certs):  # noqa: F811
    assert listen.HANDSHAKE == 10.0 and listen.IDLE == 10.0
    p = Project(mdl.load(write_model(tmp_path / "incidents", certs)))
    server, _ = web_serve(p, free_port(), mtls_port=0)
    port, ctx = server.mtls_port, server.mtls.ctx
    mid = raw(port)                                              # mid-handshake
    idle = tls_sock(port, certs)                                  # after it, quiet
    try:
        assert until(lambda: server.mtls.held() == 2, 5.0)
        t0 = time.monotonic()
        server.shutdown()
        server.server_close()
        assert time.monotonic() - t0 < 3.0
        again = listen.start(listen.handler(server.RequestHandlerClass), "127.0.0.1", port, ctx)
        again.stop()
        assert until(lambda: not mtls_threads(), 2.0), mtls_threads()
        assert eof(mid, 2.0) and eof(idle, 2.0)
    finally:
        mid.close()
        idle.close()


def test_a_remote_without_tls_is_read_as_before(page):
    code, body, _, why = client.get(page.url, "status", page.token)
    assert code == 200 and body["name"] == "incidents", why
