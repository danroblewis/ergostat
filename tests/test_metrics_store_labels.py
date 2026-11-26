"""ergostat's own series queryable by PromQL with real labels (dev/records/metrics-store-with-labels.md): each series
under a name and bounded labels; the built-in ``ergostat`` data source, held to the project; VictoriaMetrics the only
store of the readings (NOTES.md, 2026-11-25): each home's records under project labels of their own, none answering
said with how to start one, and the server supervised (``storage: measurements: run:``); against this test process's
own VictoriaMetrics (tests/conftest.py, ``vm``), with how its rate() and increase() differ from Prometheus's."""

from __future__ import annotations

import json
import math
import textwrap
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from ergostat import datasources, storage
from ergostat import model as mdl
from ergostat.daemons import supervise
from ergostat.daemons.config import STORE
from ergostat.query.buckets import grid
from ergostat.spec import read
from ergostat.store import Project
from ergostat.victoria import OLD_METRIC, Victoria, VictoriaError, promql_name
from tests.ports import free_port

# ---- names and labels


def test_each_series_has_a_name_and_bounded_labels_a_person_can_query():
    # (with no model: a part's sensor under the part's own name, its sensor's as a label; promnames.py names by the model)
    assert promql_name("sensor/queue.depth") == {"__name__": "queue", "sensor": "depth"}
    assert promql_name("sensor/disk") == {"__name__": "disk"}
    assert promql_name("sensor/fill.set") == {"__name__": "fill", "sensor": "set"}
    assert promql_name("run/builder/cost_usd") == {"__name__": "ergostat_run_cost_usd", "block": "builder"}
    assert promql_name("observer/q/innovation") == {"__name__": "ergostat_observer_innovation", "observer": "q"}
    assert promql_name("valve/inflow") == {"__name__": "ergostat_valve_position", "valve": "inflow"}
    assert promql_name("block/hold") == {"__name__": "ergostat_block_output", "block": "hold"}
    assert promql_name("Cost Usd/x") == {"__name__": "ergostat_cost_usd", "name": "x"}
    assert promql_name("plain") == {"__name__": "ergostat_series", "name": "plain"}


def test_a_reading_is_written_under_its_name_labels_project_and_series(tmp_path, monkeypatch):
    sent = []
    v = Victoria("http://127.0.0.1:9", tmp_path, project="p1")
    monkeypatch.setattr(v, "_req", lambda path, params=None, body=None: sent.append((path, body)) or b"")
    v._import([("run/builder/seconds", 100.0, 2.5), ("sensor/queue.depth", 100.0, 3.0)])
    lines = [json.loads(x) for x in sent[0][1].decode().splitlines()]
    assert sent[0][0] == "/api/v1/import" and [x["metric"] for x in lines] == [
        {"__name__": "ergostat_run_seconds", "block": "builder", "project": "p1", "series": "run/builder/seconds"},
        {"__name__": "queue", "sensor": "depth", "project": "p1", "series": "sensor/queue.depth"}]
    assert v._sel("sensor/queue.depth") == '{__name__=~".+",project="p1",series="sensor/queue.depth"}'


def test_a_series_under_both_names_is_bucketed_whole(tmp_path, monkeypatch):
    v = Victoria("http://127.0.0.1:9", tmp_path, project="p1")
    two = {"status": "success", "data": {"resultType": "matrix", "result": [
        {"metric": {"project": "p1", "series": "s"}, "values": [[100, "1"], [160, "2"]]},                  # the old name's
        {"metric": {"project": "p1", "series": "s", "name": "s"}, "values": [[220, "3"], [280, "4"]]}]}}   # its labels'
    monkeypatch.setattr(v, "_req", lambda *a, **k: json.dumps(two).encode())
    assert v._range("last_over_time({x}[60s])", 100, 280, 60) == {100.0: 1.0, 160.0: 2.0, 220.0: 3.0, 280.0: 4.0}


# ---- the built-in data source


class Stub(BaseHTTPRequestHandler):
    """A Prometheus-compatible server: query_range answers one series; /health says OK."""
    seen: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        a = parse_qs(u.query)
        type(self).seen.append((u.path, a))
        if u.path == "/health":
            body = b"OK"
        else:
            start = float(a["start"][0])
            body = json.dumps({"status": "success", "data": {"resultType": "matrix", "result": [
                {"metric": {"__name__": "ergostat_sensor", "part": "queue"}, "values": [[start, "4"]]}]}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):                                  # (what is deleted or imported: recorded, and answered empty)
        u = urlparse(self.path)
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        type(self).seen.append((u.path, parse_qs(u.query)))
        self.send_response(204)
        self.end_headers()


@pytest.fixture(scope="module")
def stub():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def project(tmp_path, more: str = "") -> Project:
    (tmp_path / "ergostat.yaml").write_text("name: own\nstocks:\n  queue: {unit: tickets}\n" + textwrap.dedent(more))
    return Project(mdl.load(tmp_path))


def test_over_victoriametrics_the_promql_source_asks_for_this_project_only(tmp_path, stub):
    p = project(tmp_path, f"storage:\n  measurements: {{url: '{stub}'}}\n")
    assert isinstance(p.measurements, Victoria)
    datasources._ANSWERS.clear()
    assert {"name": "promql", "type": "promql", "language": "PromQL", "available": True} in \
        datasources.listed(p.measurements, p)
    Stub.seen.clear()
    g = grid(1_795_400_000.0, 1_795_400_400.0, 4)
    for name in ("promql", "ergostat"):                              # (a saved panel's old name for it: the same source)
        got = datasources.query(p.model.spec, name, 'ergostat_sensor{project="another"}', g, store=p.measurements)
        assert [s["name"] for s in got["series"]] == ['ergostat_sensor{part="queue"}']
    (path, a), _ = Stub.seen
    assert path == "/api/v1/query_range" and a["extra_label"] == [f"project={p.measurements.project}"]   # (the server holds it to one)


# ---- one store, each home's own labels, and the supervised process


def test_each_home_has_its_own_project_label_and_the_default_home_the_plain_key(tmp_path, monkeypatch):
    """A record under the default home is labelled with its state key alone; one under any other home (a script's, a
    demo's, a test's throwaway ERGOSTAT_HOME) with a digest of where that home is too, so two homes sharing one
    VictoriaMetrics never read or delete each other's series."""
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    own = tmp_path / "user" / ".ergostat" / "repo-1"
    own.mkdir(parents=True)
    assert storage.metrics_project(own) == "repo-1"
    a, b = tmp_path / "a" / "repo-1", tmp_path / "b" / "repo-1"
    assert storage.metrics_project(a).startswith("repo-1@") and storage.metrics_project(a) != storage.metrics_project(b)
    assert storage.metrics_project(a) == storage.metrics_project(tmp_path / "a" / "x" / ".." / "repo-1")


def test_the_metrics_url_is_the_models_then_the_environments_then_the_default(monkeypatch):
    monkeypatch.delenv("ERGOSTAT_METRICS_URL")
    assert storage.metrics_url(storage.Storage()) == storage.VM_URL
    monkeypatch.setenv("ERGOSTAT_METRICS_URL", "http://127.0.0.1:1/")
    assert storage.metrics_url(None) == "http://127.0.0.1:1"
    assert storage.metrics_url(storage.parse({"measurements": {"url": "http://h:2"}}, [])) == "http://h:2"


def test_storage_measurements_is_victoriametrics_only(tmp_path):
    for raw, word in (({"measurements": "sqlite"}, "VictoriaMetrics only"), ({"measurements": {"tiers": {"1m": "1d"}}},
                      "no longer"), ({"measurements": {"raw": "2d"}}, "no longer"), ({"measurements": {"x": 1}}, "unknown")):
        problems: list = []
        storage.parse(raw, problems)
        assert len(problems) == 1 and word in problems[0], problems
    problems = []
    got = storage.parse({"measurements": {"backend": "victoriametrics", "url": "http://h:1", "run": "victoria-metrics"}}, problems)
    assert problems == [] and (got.url, got.run) == ("http://h:1", "victoria-metrics")


def test_no_server_answering_fails_early_and_says_how_to_start_one(tmp_path, monkeypatch, capsys):
    """``ergostat run`` refuses to start, and a command that reads the readings fails, each saying how to start
    VictoriaMetrics: the readings are kept nowhere else, never written somewhere else instead."""
    from ergostat.cli import main
    monkeypatch.setenv("ERGOSTAT_METRICS_URL", f"http://127.0.0.1:{free_port()}")
    repo = tmp_path / "repo"
    repo.mkdir()
    p = project(repo)
    assert main(["-C", str(repo), "run", "--foreground", "--no-web"]) == 1
    err = capsys.readouterr().err
    assert "no VictoriaMetrics answers" in err and "brew install victoriametrics" in err and "run:" in err
    with pytest.raises(VictoriaError, match="brew install victoriametrics"):
        p.measurements.latest("sensor/queue")
    assert main(["-C", str(repo), "reset", "--yes"]) == 1
    assert "brew install victoriametrics" in capsys.readouterr().err
    assert not list(p.dir.glob("measurements.*"))                                # (nothing kept anywhere else)


def test_reset_of_a_victoriametrics_record_deletes_its_series_in_the_server(tmp_path, stub, capsys):
    """On VictoriaMetrics, ``ergostat reset --yes`` deletes this project's series in the server (every name, the old
    single one too) and the backfill ledger, so the record that starts from nothing reads nothing old back; a server
    that is away refuses the reset, and nothing local is deleted."""
    from ergostat.cli import main
    repo = tmp_path / "repo"
    repo.mkdir()
    p = project(repo, f"storage:\n  measurements: {{url: '{stub}'}}\n")
    assert isinstance(p.measurements, Victoria)
    for n in ("measurements.backfilled.db", "measurements.forgotten.json"):
        (p.dir / n).write_bytes(b"")
    Stub.seen.clear()
    assert main(["-C", str(repo), "reset"]) == 0                               # (says so, deletes nothing)
    assert f"every reading of project {p.measurements.project} in VictoriaMetrics" in capsys.readouterr().out and Stub.seen == []
    assert main(["-C", str(repo), "reset", "--yes"]) == 0
    assert Stub.seen == [("/api/v1/admin/tsdb/delete_series", {"match[]": [p.measurements._sel()]})]
    assert '__name__=~".+"' in p.measurements._sel()                           # (OLD_METRIC and the old names included)
    assert not (p.dir / "measurements.backfilled.db").exists() and not (p.dir / "measurements.forgotten.json").exists()
    away = tmp_path / "away"
    away.mkdir()
    q = project(away, f"storage:\n  measurements: {{url: 'http://127.0.0.1:{free_port()}'}}\n")
    (q.dir / "measurements.forgotten.json").write_bytes(b"")
    capsys.readouterr()
    assert main(["-C", str(away), "reset", "--yes"]) == 1
    assert "VictoriaMetrics" in capsys.readouterr().err and (q.dir / "measurements.forgotten.json").exists()


def _spec(tmp_path, text: str):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    spec, problems = read(tmp_path / "ergostat.yaml")
    return spec, [x for x in problems if x.level == "error"]


def test_storage_run_is_a_daemon_ergostat_supervises(tmp_path, monkeypatch):
    spec, errors = _spec(tmp_path, """\
        name: s
        stocks: {queue: {unit: tickets}}
        storage:
          measurements: {run: victoria-metrics -storageDataPath vm -httpListenAddr 127.0.0.1:8428}
        """)
    assert not errors, errors
    assert spec.daemons[STORE].run.startswith("victoria-metrics -storageDataPath vm") and spec.daemons[STORE].concurrency == 1
    started = []
    eng = type("E", (), {"own": lambda self, n, s: True})()
    sup = supervise.Supervisor(eng)
    monkeypatch.setattr(sup, "_spawn_claimed", lambda slot: started.append(slot.d.name))
    monkeypatch.setattr(sup, "_loop", lambda: None)
    sup.sync(spec)
    assert started == [STORE]                       # started though no block or sensor names it
    _, errors = _spec(tmp_path, """\
        name: s
        stocks: {queue: {unit: tickets}}
        daemons: {victoriametrics: {run: ./mine}}
        storage:
          measurements: {backend: victoriametrics, run: victoria-metrics}
        """)
    assert [e.code for e in errors] == ["bad-daemon"]
    _, errors = _spec(tmp_path, "name: s\nstocks: {queue: {unit: tickets}}\nstorage: {measurements: {run: victoria-metrics}}\n")
    assert errors == []                             # (run: needs nothing else: the store is VictoriaMetrics)


# ---- a real VictoriaMetrics


def _vm(url, d):
    return Victoria(url, d, project=f"test-{uuid.uuid4().hex[:10]}")



def test_a_record_under_the_old_single_name_is_read_with_the_new(tmp_path, vm):
    dst = _vm(vm, tmp_path)
    now = time.time()
    lines = [{"metric": {"__name__": OLD_METRIC, "project": dst.project, "series": "sensor/q.n"},
              "values": [1.0, 2.0, 3.0], "timestamps": [round((now - 3600 + i) * 1000) for i in range(3)]}]
    try:
        dst._req("/api/v1/import", body="".join(json.dumps(x) + "\n" for x in lines).encode())
        dst._req("/internal/force_flush")
        dst.add_many([("sensor/q.n", now - 1800, 4.0)])                  # (written after the upgrade, under its labels)
        [s] = dst.series()
        assert (s["n"], s["value"]) == (4, 4.0)                          # both names read
        assert [v for _, v in dst.range("sensor/q.n", now - 7200)] == [1.0, 2.0, 3.0, 4.0]
        assert dst.newest() == {"sensor/q.n": dst.latest("sensor/q.n")} and dst.latest("sensor/q.n")[1] == 4.0
    finally:
        dst.drop()


def _prometheus_increase(pts: list, start: float, end: float) -> float | None:
    """Prometheus's increase() (promql/functions.go, extrapolatedRate): the samples in (start, end], at least two, their
    change (counter resets added back) extrapolated toward the window's edges, never past where the counter was zero."""
    s = [(t, v) for t, v in pts if start < t <= end]
    if len(s) < 2:
        return None
    result = s[-1][1] - s[0][1] + sum(a for (_, a), (_, b) in zip(s, s[1:], strict=False) if b < a)
    to_start, to_end, sampled = s[0][0] - start, end - s[-1][0], s[-1][0] - s[0][0]
    avg = sampled / (len(s) - 1)
    if result > 0 and s[0][1] >= 0:
        to_start = min(to_start, sampled * (s[0][1] / result))
    extended = sampled + (to_start if to_start < avg * 1.1 else avg / 2) + (to_end if to_end < avg * 1.1 else avg / 2)
    return result * extended / sampled


def test_rate_and_increase_differ_from_prometheus_as_recorded(tmp_path, vm):
    """A counter read every minute that rises by one between two readings. Prometheus extrapolates the change in the
    window toward its edges (1.125 here) and has no answer for a window holding one sample; VictoriaMetrics counts from
    the last sample before the window and does not extrapolate (exactly 1), and answers the one-sample window."""
    dst = _vm(vm, tmp_path)
    t0 = math.floor((time.time() - 86400) / 60) * 60
    pts = [(t0 + 60 * i, 0.0 if i <= 16 else 1.0) for i in range(21)]
    at = pts[20][0] + 30
    try:
        dst.add_many([("sensor/c.total", t, v) for t, v in pts])
        sel = f'c{{project="{dst.project}"}}'
        [(_, inc)] = dst._query(f"increase({sel}[300s])", at)
        [(_, rate)] = dst._query(f"rate({sel}[300s])", at)
        prom = _prometheus_increase(pts, at - 300, at)
        assert prom == pytest.approx(1.125)
        assert inc == pytest.approx(1.0) and rate == pytest.approx(1 / 300)       # Prometheus: 1.125 and 0.00375
        assert _prometheus_increase(pts, at - 60, at) is None                     # one sample: Prometheus has none
        got = dst._query(f"increase({sel}[60s])", at)
        assert [v for _, v in got] == [pytest.approx(0.0)]                         # VictoriaMetrics: from the one before
    finally:
        dst.drop()


def test_the_unit_test_of_the_prometheus_reference_itself():
    pts = [(60.0 * i, 10.0 * i) for i in range(21)]
    assert _prometheus_increase(pts, 60 * 15 + 30, 60 * 20 + 30) == pytest.approx(50.0)   # linear: edges filled in
    assert _prometheus_increase([(0.0, 5.0), (60.0, 1.0)], -30, 60) == pytest.approx(1.0 * 90 / 60)   # a reset added back


@pytest.fixture(autouse=True)
def _no_network_but_here(monkeypatch):
    """Nothing here reaches past localhost (a test's urlopen, should one leak)."""
    real = urllib.request.urlopen

    def local(req, *a, **k):
        url = req.full_url if isinstance(req, urllib.request.Request) else req
        assert urlparse(url).hostname in ("127.0.0.1", "localhost"), url
        return real(req, *a, **k)
    monkeypatch.setattr(urllib.request, "urlopen", local)
