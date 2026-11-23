"""The page server never piles up requests (dev/records/perf-web-requests-never-pile-up.md): a request whose client
has left is dropped before it is answered, the API queue is bounded (503 past it), static files and the page have a
fast lane the API never fills, every slow answer is one line in the log, and a POST read is always answered."""

from __future__ import annotations

import json
import re
import resource
import socket
import threading
import time

import pytest

from ergostat import web
from ergostat.web import server as ws


@pytest.fixture(autouse=True)
def _enough_files():
    """A few hundred sockets each side: more than macOS's default 256 open files."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    want = min(hard, 4096) if hard != resource.RLIM_INFINITY else 4096
    if soft < want:
        resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))
    yield
    resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))


@pytest.fixture
def site(project, monkeypatch):
    """The page served, its ``_answer`` replaced: ``/api/hold*`` waits for ``release``, ``/api/sleep-S`` sleeps S
    seconds, anything else answers at once; every path answered is in ``called``."""
    called, release = [], threading.Event()
    real = ws._answer

    def answer(live, path, q, project=None):
        called.append(path)
        if path.startswith("hold"):
            release.wait(30)
            return {"held": path}
        if path.startswith("sleep-"):
            time.sleep(float(path.split("-")[1].split("/")[0]))
            return {"slept": path}
        if path.startswith("echo"):
            return {"echo": path}
        return real(live, path, q, project)
    monkeypatch.setattr(ws, "_answer", answer)
    server, url = web.serve(project, 0)
    port = server.server_address[1]

    class Site:
        pass
    s = Site()
    s.server, s.port, s.called, s.release = server, port, called, release
    yield s
    release.set()
    server.shutdown()
    server.server_close()


def ask(port: int, path: str, method: str = "GET", extra: str = "", body: bytes = b"") -> socket.socket:
    c = socket.create_connection(("127.0.0.1", port), timeout=30)
    c.sendall(f"{method} {path} HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n{extra}\r\n".encode() + body)
    return c


def answer_of(c: socket.socket) -> bytes:
    got = b""
    while chunk := c.recv(65536):
        got += chunk
    c.close()
    return got


def until(cond, within: float = 20.0, what: str = "") -> None:
    end = time.monotonic() + within
    while not cond():
        if time.monotonic() > end:
            raise AssertionError(f"not within {within}s: {what}")
        time.sleep(0.01)


def hold_all(s, n: int | None = None) -> list[socket.socket]:
    """Every API worker busy on a held request."""
    n = n or s.server.workers
    held = [ask(s.port, f"/api/hold{i}") for i in range(n)]
    until(lambda: sum(p.startswith("hold") for p in s.called) >= n, what="the workers all taken")
    return held


def test_cheap_requests_take_the_fast_lane():
    assert web.cheap(b"GET /static/style.css?v=1 HTTP/1.1\r\n")
    assert web.cheap(b"GET / HTTP/1.1\r\n") and web.cheap(b"GET /items?x=1 HTTP/1.1\r\n")
    assert web.cheap(b"GET /api/projects HTTP/1.1\r\n")
    assert not web.cheap(b"GET /api/status HTTP/1.1\r\n") and not web.cheap(b"POST /static/x HTTP/1.1\r\n")
    assert not web.cheap(b"GET /file/a.md HTTP/1.1\r\n") and not web.cheap(b"GE") and not web.cheap(b"\r\n")


def test_a_client_that_asked_and_left_while_every_worker_was_busy_is_never_answered(site, capfd):
    """The measured CLOSE_WAIT case: a full GET sent, the write side shut, the socket closed, all before a worker is
    free. Its bytes still wait on the server's side, so only the peek for the end after reading finds it gone."""
    held = hold_all(site)
    c = ask(site.port, "/api/echo-left")
    c.shutdown(socket.SHUT_WR)
    c.close()
    until(lambda: site.server.jobs.qsize() == 1, what="the left request queued")
    time.sleep(0.2)                                    # its FIN arrives
    site.release.set()
    for h in held:
        assert b"200 OK" in answer_of(h)
    late = ask(site.port, "/api/echo-after")           # queued behind it: answered once it is dropped
    assert b'"echo": "echo-after"' in answer_of(late)
    assert "echo-left" not in site.called
    assert re.search(r"web: dropped GET /api/echo-left: the client left after \d+\.\ds in the queue", capfd.readouterr().err)


def _past_1024(sock: socket.socket) -> socket.socket:
    """The same socket, numbered 1100 (select() refuses any numbered 1024 or more)."""
    import os
    fd = os.dup2(sock.fileno(), 1100)
    sock.close()
    return socket.socket(fileno=fd)


def test_left_works_on_a_socket_numbered_past_1024():
    a, b = socket.socketpair()
    a = _past_1024(a)
    a.settimeout(10)                                   # as the handler's: the peek must not wait for it
    try:
        assert a.fileno() >= 1024
        t0 = time.monotonic()
        assert not ws.left(a)                          # nothing sent, still there
        assert time.monotonic() - t0 < 1 and a.gettimeout() == 10
        b.sendall(b"GET / HTTP/1.1\r\n\r\n")
        assert not ws.left(a)                          # a pipelined request's bytes are no end
        a.recv(65536)
        b.shutdown(socket.SHUT_WR)
        b.close()
        assert ws.left(a)                              # FIN: gone
    finally:
        a.close()
    assert not ws.left(a)                              # a check that cannot run (closed) serves the GET


def test_a_get_on_a_connection_numbered_past_1024_is_answered(site, monkeypatch):
    """Under a pile-up the server's sockets pass 1023: the check before _answer must still let the GET through."""
    import os
    seen, real = [], ws.left
    monkeypatch.setattr(ws, "left", lambda conn: (seen.append(conn.fileno()), real(conn))[1])
    fill = []
    try:
        while not fill or fill[-1] < 1060:
            fill.append(os.open(os.devnull, os.O_RDONLY))
        for f in [f for f in fill if f > 1024]:        # only numbers past 1024 free: the accepted socket takes one
            os.close(f)
        fill = [f for f in fill if f <= 1024]
        c = ask(site.port, "/api/echo-high")
        got = answer_of(c)
        assert seen and seen[0] >= 1024, seen          # the window this test is for
        assert b'"echo": "echo-high"' in got
    finally:
        for f in fill:
            os.close(f)


def test_a_reception_step_that_raises_closes_that_connection_only(site, monkeypatch, capfd):
    real = web.cheap

    def cheap(head):
        if b"/api/echo-bad" in head:
            raise RuntimeError("bad head")
        return real(head)
    monkeypatch.setattr(web, "cheap", cheap)
    assert answer_of(ask(site.port, "/api/echo-bad")) == b""
    assert b'"echo": "echo-next"' in answer_of(ask(site.port, "/api/echo-next"))
    assert "web: reception closed a connection: RuntimeError('bad head')" in capfd.readouterr().err
    assert site.server._waker.getblocking() is False   # a full buffer raises, never blocks serve_forever


def test_a_get_that_waited_too_long_is_dropped(site, monkeypatch, capfd):
    held = hold_all(site)
    monkeypatch.setattr(ws, "WAITED_MOST", 0.2)
    c = ask(site.port, "/api/echo-old")
    until(lambda: site.server.jobs.qsize() == 1)
    time.sleep(0.4)
    site.release.set()
    for h in held:
        answer_of(h)
    assert answer_of(c) == b""                         # closed unanswered
    assert "echo-old" not in site.called
    assert "web: dropped GET /api/echo-old: too old after" in capfd.readouterr().err


@pytest.mark.serial
def test_with_every_api_worker_held_static_answers_fast_and_a_full_queue_is_503_at_once(site):
    held = hold_all(site)
    t0 = time.monotonic()
    got = answer_of(ask(site.port, "/static/style.css"))
    assert b"200 OK" in got and time.monotonic() - t0 < 0.2, f"{time.monotonic() - t0:.3f}s"
    queued = [ask(site.port, f"/api/hold-q{i}") for i in range(site.server.queue_most)]
    until(lambda: site.server.jobs.qsize() == site.server.queue_most, what="the queue full")
    t0 = time.monotonic()
    busy = answer_of(ask(site.port, "/api/echo-one-too-many"))
    assert busy.startswith(b"HTTP/1.0 503") and b"Retry-After: 2" in busy, busy
    assert time.monotonic() - t0 < 0.5
    t0 = time.monotonic()                              # the fast lane still answers past a full API queue
    assert b"200 OK" in answer_of(ask(site.port, "/static/style.css")) and time.monotonic() - t0 < 0.2
    site.release.set()
    for c in held + queued:
        c.close()
    assert "echo-one-too-many" not in site.called


def test_a_slow_answer_is_one_line_with_its_wait_and_work_and_status_counts_it(site, monkeypatch, capfd):
    monkeypatch.setattr(ws, "SLOW_S", 0.3)
    status = json.loads(answer_of(ask(site.port, "/api/status")).split(b"\r\n\r\n", 1)[1])
    assert "web" not in status
    capfd.readouterr()
    assert b"200 OK" in answer_of(ask(site.port, "/api/sleep-0.5"))
    err = capfd.readouterr().err
    lines = [x for x in err.splitlines() if "slow GET" in x]
    assert len(lines) == 1, err
    assert re.search(r"web: slow GET /api/sleep-0\.5: waited \d+\.\ds in the queue, 0\.[5-9]s working, 0 KB", lines[0])
    assert b"200 OK" in answer_of(ask(site.port, "/api/echo-quick"))
    assert "GET /api/echo-quick" not in capfd.readouterr().err
    status = json.loads(answer_of(ask(site.port, "/api/status")).split(b"\r\n\r\n", 1)[1])
    assert status["web"]["slow"] == {"/api/sleep-0.5": 1}


def test_slow_counts_last_ten_minutes(monkeypatch):
    log, now = ws.WebLog(), [1000.0]
    monkeypatch.setattr(ws.time, "monotonic", lambda: now[0])
    log.note("dropped", "/api/a?x=1", "gone")
    assert log.recent() is None                        # nothing slow: no ``web`` in status
    log.note("slow", "/api/a?x=1", "w")
    log.note("slow", "/api/a", "w")
    assert log.recent() == {"slow": {"/api/a": 2}, "dropped": {"/api/a": 1}}
    now[0] += 601
    assert log.recent() is None


def test_a_post_read_is_never_dropped(site, monkeypatch):
    """A POST whose client half-closed after sending it, queued past WAITED_MOST: still answered."""
    from ergostat.web import numbers_api
    page = answer_of(ask(site.port, "/")).decode()
    token = re.search(r'name="ergostat-token" content="([^"]+)"', page).group(1)
    done = []
    monkeypatch.setattr(numbers_api, "post", lambda live, path, w, q: (done.append(path) or 200, {"ok": path}))
    held = hold_all(site)
    monkeypatch.setattr(ws, "WAITED_MOST", 0.0)
    c = ask(site.port, "/api/estimate", "POST", f"X-Ergostat-Token: {token}\r\nContent-Length: 2\r\n", b"{}")
    c.shutdown(socket.SHUT_WR)
    until(lambda: site.server.jobs.qsize() == 1)
    time.sleep(0.3)
    site.release.set()
    assert b'"ok": "estimate"' in answer_of(c)
    assert done == ["estimate"]
    for h in held:
        h.close()


@pytest.mark.slow
@pytest.mark.serial
def test_slow_requests_and_clients_that_hang_up_the_server_works_for_those_still_waiting(site, capfd):
    """24 requests of 5 s each, and 30 more whose clients send and hang up after 1 s: only the 24 are worked, and
    the log names each: 24 slow lines and 30 dropped."""
    t0 = time.monotonic()
    slow = [ask(site.port, f"/api/sleep-5/{i}") for i in range(24)]
    until(lambda: len(site.called) == 24, what="the 24 taken")
    gone = [ask(site.port, f"/api/echo-gone{i}") for i in range(30)]
    time.sleep(1)
    for c in gone:
        c.shutdown(socket.SHUT_WR)
        c.close()
    assert time.monotonic() - t0 < 4.5, "the hang-ups came after a worker was free: not the case this test is for"
    assert site.called == [p for p in site.called if p.startswith("sleep")]
    for c in slow:
        assert b"200 OK" in answer_of(c)
    until(lambda: site.server.jobs.qsize() == 0)
    late = answer_of(ask(site.port, "/api/echo-last"))   # behind them all: once it answers, every one was handled
    assert b"echo-last" in late
    assert sorted(site.called) == sorted([f"sleep-5/{i}" for i in range(24)] + ["echo-last"])
    err = capfd.readouterr().err
    assert len(re.findall(r"web: slow GET /api/sleep-5/\d+: waited", err)) == 24
    assert len(re.findall(r"web: dropped GET /api/echo-gone\d+: the client left", err)) == 30
