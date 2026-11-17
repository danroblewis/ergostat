"""storage: in the YAML (SPEC §4b), and the page's answers bounded: none grows with the record, and a
client that went away is a quiet line, not a traceback."""

from __future__ import annotations

import json
import socket
import time
import urllib.request

import pytest

from ergostat.storage import RAW, TIERS, Storage, parse


def test_storage_defaults_and_what_it_says():
    s = parse(None, [])
    assert s == Storage() and s.raw == RAW and s.tiers == TIERS and s.horizon("x") == 7 * 86400
    wrong: list[str] = []
    s = parse({"events": "sqlite", "measurements": {"backend": "victoriametrics", "raw": "never", "tiers": {"5m": "1d", "1h": "30d"}},
               "rollup": {"after": "2d", "kinds": {"session": "1h", "case": "never"}, "every": "10m"}}, wrong)
    assert not wrong
    assert (s.events, s.measurements, s.url, s.raw, s.tiers) == ("sqlite", "victoriametrics", "http://127.0.0.1:8428", None,
                                                                 ((300.0, 86400.0), (3600.0, 30 * 86400.0)))
    assert (s.horizon("session"), s.horizon("case"), s.horizon("other"), s.every) == (3600.0, None, 2 * 86400, 600.0)
    parse({"events": "kafka", "measurements": {"tiers": {"7m": "1d", "10m": "2d"}}, "rollup": {"after": "soon"}, "x": 1}, wrong)
    assert len(wrong) == 4 and any("multiple" in w for w in wrong) and any("kafka" in w for w in wrong)


def test_storage_in_the_yaml_chooses_the_backends(tmp_path):
    from ergostat import model as mdl
    from ergostat.store import Project
    (tmp_path / "ergostat.yaml").write_text("storage:\n  events: sqlite\n  measurements: {raw: 1h, tiers: {1m: 1d}}\n")
    p = Project(mdl.load(tmp_path))
    assert p.events.name == "sqlite" and p.measurements.raw == 3600.0 and p.measurements.tiers == [(60.0, 86400.0)]
    (tmp_path / "ergostat.yaml").write_text("storage:\n  events: segments\n")
    assert Project(mdl.load(tmp_path)).events.name == "segments"
    (tmp_path / "ergostat.yaml").write_text("storage:\n  events: nope\n")
    with pytest.raises(mdl.ModelError, match="storage.events: 'nope' is not a backend"):
        mdl.load(tmp_path)


def test_answers_are_bounded_however_long_the_record(project):
    from ergostat.web import serve
    project.events.add_many([{"type": "x.y", "item": f"t/{i}", "data": {"i": i}, "at": time.time() - 3600 + i * 0.1}
                             for i in range(3000)])
    server, url = serve(project, 18791)
    try:
        def get(path):
            with urllib.request.urlopen(url + path, timeout=20) as r:
                return json.loads(r.read())
        assert len(get("/api/events?n=100000")) == 1000
        older = get("/api/events?n=10")
        assert [e["seq"] for e in get(f"/api/events?n=5&before={older[0]['seq']}")] == [e["seq"] - 5 for e in older[:5]]
        items = get("/api/items")
        assert items["total"] == 3000 and len(items["items"]) == 500
        assert len(get("/api/items?offset=2900")["items"]) == 100
    finally:
        server.shutdown()
        server.server_close()


def test_a_client_that_went_away_is_one_quiet_line(project, capsys):
    from ergostat.web import serve
    server, url = serve(project, 18792)
    try:
        port = int(url.rsplit(":", 1)[1])
        for _ in range(5):                   # ask for the page, and hang up before it is written
            s = socket.create_connection(("127.0.0.1", port))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
            s.sendall(f"GET /api/graph HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode())
            s.close()
        with urllib.request.urlopen(url + "/api/status", timeout=20) as r:     # and it still answers
            assert r.status == 200
        time.sleep(0.5)
    finally:
        server.shutdown()
        server.server_close()
    err = capsys.readouterr().err
    assert "Traceback" not in err


def test_send_to_a_gone_client_logs_one_line(capsys):
    from ergostat.web.server import went_away
    went_away("/api/graph?view=x", 4096 * 1024, BrokenPipeError(32, "Broken pipe"))
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "/api/graph was sent (4096 KB, BrokenPipeError)" in err and "Traceback" not in err


def test_one_snapshot_is_made_however_many_ask_at_once(project, monkeypatch):
    import threading

    from ergostat import state as st
    from ergostat.web.server import Live
    made = []
    real = st.snapshot

    def slow(*a, **k):
        made.append(1)
        time.sleep(0.3)
        return real(*a, **k)
    monkeypatch.setattr(st, "snapshot", slow)
    live = Live(project)
    got = []
    ts = [threading.Thread(target=lambda: got.append(live.snapshot(project, 3600.0, None))) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(made) == 1 and len(got) == 8 and all(g is got[0] for g in got)


def test_a_record_made_before_the_segmented_log_stays_on_sqlite(tmp_path):
    """Upgrading never hides a project's history: an existing events.db is read unless the YAML names a backend."""
    from ergostat.storage import Storage, events_backend, parse
    (tmp_path / "events.db").write_bytes(b"")
    assert events_backend(Storage(), tmp_path) == "sqlite"
    named = parse({"events": "segments"}, [])
    assert events_backend(named, tmp_path) == "segments"
    assert events_backend(Storage(), tmp_path / "fresh") == "segments"
