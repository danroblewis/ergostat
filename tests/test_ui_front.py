"""The page's front (dev/bin/ui.py): it streams, keeps the Host, moves between servers, and staging writes nothing."""

from __future__ import annotations

import http.client
import http.server
import socketserver
import sys
import threading
import time
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "dev" / "bin"
if str(BIN) not in sys.path:
    sys.path.append(str(BIN))          # appended: dev/bin/queue.py must not shadow the standard lib

import ui  # noqa: E402


class Backend(http.server.BaseHTTPRequestHandler):
    name = b"a"
    seen: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.seen.append(self.headers.get("Host"))
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"first\n")
            self.wfile.flush()
            time.sleep(1.0)
            self.wfile.write(b"second\n")
            self.close_connection = True
            return
        self.send_response(200)
        self.send_header("Content-Length", "1")
        self.end_headers()
        self.wfile.write(self.name)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        got = self.rfile.read(n)
        self.send_response(200)
        self.send_header("Content-Length", str(len(got)))
        self.end_headers()
        self.wfile.write(got)


class Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def up(server) -> int:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


def backend(name: bytes) -> int:
    return up(Srv(("127.0.0.1", 0), type("B", (Backend,), {"name": name, "seen": []})))


def ask(port: int, method="GET", path="/", body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    got = r.status, r.read()
    c.close()
    return got


def test_it_moves_to_the_new_server_with_no_gap():
    a, b = backend(b"a"), backend(b"b")
    now = [a]
    port = up(ui.front(0, lambda: now[0], True))
    assert ask(port) == (200, b"a")
    now[0] = b
    assert ask(port) == (200, b"b")


def test_a_post_reaches_the_real_page():
    port = up(ui.front(0, lambda: backend(b"a"), True))
    assert ask(port, "POST", "/api/x", b"hello") == (200, b"hello")


def test_staging_refuses_every_write():
    port = up(ui.front(0, lambda: backend(b"a"), False))
    assert ask(port, "POST", "/api/x", b"hello")[0] == 403
    assert ask(port)[0] == 200


def test_the_answer_is_streamed_as_it_comes():
    b = backend(b"a")
    port = up(ui.front(0, lambda: b, True))
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", "/stream")
    r = c.getresponse()
    began = time.time()
    assert r.read1(6) == b"first\n"
    assert time.time() - began < 0.8
    assert r.read().endswith(b"second\n")


def test_the_host_is_kept_for_the_pages_origin_check():
    Seen = type("B", (Backend,), {"seen": []})
    b = up(Srv(("127.0.0.1", 0), Seen))
    port = up(ui.front(0, lambda: b, True))
    ask(port, headers={"Host": "factory.example"})
    assert Seen.seen == ["factory.example"]


def test_a_local_request_is_addressed_to_the_server_behind():
    got = ui.addressed({"Host": "127.0.0.1:8798", "Origin": "http://127.0.0.1:8798", "X": "1"}, 8791)
    assert got == {"Host": "127.0.0.1:8791", "Origin": "http://127.0.0.1:8791", "X": "1"}
    assert "Origin" not in ui.addressed({"Host": "localhost:8798"}, 8791)


def test_a_public_name_is_left_as_it_came():
    head = {"Host": "factory.example", "Origin": "https://factory.example"}
    assert ui.addressed(head, 8791) == head


def test_no_server_is_said_not_hung():
    port = up(ui.front(0, lambda: 0, True))
    assert ask(port)[0] == 503


def test_only_python_restarts_the_server():
    assert not ui.needs_restart(["ergostat/web/static/pages.js", "tests/test_x.py", "docs/a.md"])
    assert ui.needs_restart(["ergostat/web/server.py"])
    assert ui.needs_restart(["uv.lock"])


def test_each_page_has_a_second_port_for_its_next_server():
    assert len(ui.REAL_BACKENDS) == 2 and len(ui.STAGING_BACKENDS) == 2
    assert not set(ui.REAL_BACKENDS) & set(ui.STAGING_BACKENDS)


def test_the_fronts_address_replaces_the_servers_once_written(tmp_path, monkeypatch):
    (tmp_path / "web.json").write_text('{"url": "http://127.0.0.1:8793"}')
    monkeypatch.setattr(ui.lv, "state_dir", lambda cfg: tmp_path)
    site = ui.Site.__new__(ui.Site)
    site.cfg, site.keep_address = {}, "http://127.0.0.1:8798"
    site.address_kept(8793)
    assert "8798" in (tmp_path / "web.json").read_text()
