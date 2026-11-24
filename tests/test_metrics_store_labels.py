"""ergostat's own series queryable by PromQL with real labels (dev/records/metrics-store-with-labels.md): each series
under a name and bounded labels; the built-in ``ergostat`` data source over VictoriaMetrics, held to the project, and
over SQLite one that says what it needs; VictoriaMetrics supervised (``storage: measurements: run:``) and the default
for a new record when one answers; and ``ergostat migrate``, against a real VictoriaMetrics binary (skipped when there
is none: ERGOSTAT_TEST_VM_URL names a running one, ERGOSTAT_TEST_VM_BIN or PATH a binary started here), keeping every
reading, answering PromQL, and changing nothing the second time; with how its rate() and increase() differ from
Prometheus's."""

from __future__ import annotations

import contextlib
import json
import math
import os
import shutil
import subprocess
import textwrap
import threading
import time
import urllib.request
import uuid
from decimal import ROUND_DOWN, Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from ergostat import datasources, storage
from ergostat import model as mdl
from ergostat.daemons import supervise
from ergostat.daemons.config import STORE
from ergostat.migrate import UNTIL, migrate
from ergostat.query.buckets import grid
from ergostat.spec import read
from ergostat.store import Measurements, Project
from ergostat.victoria import OLD_METRIC, Victoria, promql_name
from tests.ports import free_port

VM_URL = os.environ.get("ERGOSTAT_TEST_VM_URL")      # (read at import: the home fixture clears ERGOSTAT_*)
VM_BIN = os.environ.get("ERGOSTAT_TEST_VM_BIN") or shutil.which("victoria-metrics") or shutil.which("victoria-metrics-prod")
SKIP = "set ERGOSTAT_TEST_VM_URL to run VictoriaMetrics"


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


def test_a_series_under_both_names_is_bucketed_whole_before_it_migrates(tmp_path, monkeypatch):
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


def test_over_sqlite_a_promql_panel_says_what_it_needs_and_the_rest_of_the_page_works(tmp_path):
    from tests.test_data_sources import ask
    p = project(tmp_path)
    assert p.measurements.name == "sqlite"
    own, old = ask(p, {"source": "ergostat", "text": "ergostat_sensor"}, {"source": "counts"})
    assert own["error_kind"] == "refused" and "only from VictoriaMetrics" in own["error"]
    assert "ergostat migrate" in own["error"] and "storage: measurements: victoriametrics" in own["error"]
    assert "error" not in old, old                                   # (the other panels are answered as before)
    named = [s["name"] for s in datasources.listed(p.model.spec, p.measurements)]
    assert "ergostat" not in named and "model" in named            # (not offered where it cannot answer)
    with pytest.raises(datasources.SourceError, match="only from VictoriaMetrics"):
        datasources.suggest(p.model.spec, "ergostat", "metrics", store=p.measurements)


def test_over_victoriametrics_the_builtin_source_asks_for_this_project_only(tmp_path, stub):
    p = project(tmp_path, f"storage:\n  measurements: {{backend: victoriametrics, url: '{stub}'}}\n")
    assert isinstance(p.measurements, Victoria)
    assert {"name": "ergostat", "type": "prometheus", "language": "PromQL"} in datasources.listed(p.model.spec, p.measurements)
    assert not datasources.own(p.model.spec, "ergostat")             # (it reads a server: never asked for a public reader)
    Stub.seen.clear()
    g = grid(1_795_400_000.0, 1_795_400_400.0, 4)
    got = datasources.query(p.model.spec, "ergostat", 'ergostat_sensor{project="another"}', g, store=p.measurements)
    assert [s["name"] for s in got["series"]] == ['ergostat_sensor{part="queue"}']
    [(path, a)] = Stub.seen
    assert path == "/api/v1/query_range" and a["extra_label"] == [f"project={p.dir.name}"]   # (the server holds it to one)


def test_a_model_source_named_ergostat_is_its_own(tmp_path, stub):
    p = project(tmp_path, f"sources:\n  ergostat: {{type: prometheus, url: '{stub}'}}\n")
    Stub.seen.clear()
    datasources.query(p.model.spec, "ergostat", "up", grid(1_795_400_000.0, 1_795_400_400.0, 4), store=p.measurements)
    [(_, a)] = Stub.seen
    assert "extra_label" not in a


# ---- the default for new installs, and the supervised process


def test_a_new_record_takes_victoriametrics_when_one_answers_and_an_old_one_keeps_sqlite(tmp_path, monkeypatch, stub):
    monkeypatch.delenv("ERGOSTAT_DEFAULT_MEASUREMENTS")
    monkeypatch.setattr(storage, "VM_URL", stub)
    monkeypatch.setenv("HOME", str(tmp_path))                                 # (records under the default home)
    own = tmp_path / ".ergostat"
    fresh, old, said = own / "fresh", own / "old", own / "said"
    for d in (fresh, old, said):
        d.mkdir(parents=True)
    (old / "measurements.db").write_bytes(b"")
    cfg = storage.Storage()
    assert storage.measurements_backend(cfg, old) == "sqlite"                 # an existing SQLite install, until it migrates
    assert storage.measurements_backend(cfg, fresh) == "victoriametrics"      # a new install, VictoriaMetrics answering
    assert (fresh / "measurements.backend").read_text().strip() == "victoriametrics"
    monkeypatch.setattr(storage, "VM_URL", f"http://127.0.0.1:{free_port()}")
    assert storage.measurements_backend(cfg, fresh) == "victoriametrics"      # kept when it is away: never SQLite unasked
    assert storage.measurements_backend(cfg, said) == "sqlite"                # none answering: SQLite, and no mark
    assert not (said / "measurements.backend").exists()
    named = storage.parse({"measurements": "sqlite"}, [])
    assert storage.measurements_backend(named, fresh) == "sqlite"             # the YAML decides
    monkeypatch.setenv("ERGOSTAT_DEFAULT_MEASUREMENTS", "sqlite")
    monkeypatch.setattr(storage, "VM_URL", stub)
    assert storage.measurements_backend(cfg, said) == "sqlite"


def test_a_fresh_ergostat_home_never_writes_to_a_server_answering_unless_asked(tmp_path, monkeypatch, stub):
    """A script's, demo's or benchmark's throwaway ERGOSTAT_HOME, with a live VictoriaMetrics answering at the default
    address and no backend in the YAML: its record is SQLite, the server is not even asked, and nothing reaches it."""
    monkeypatch.delenv("ERGOSTAT_DEFAULT_MEASUREMENTS")
    monkeypatch.setattr(storage, "VM_URL", stub)
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "throwaway"))
    repo = tmp_path / "repo"
    repo.mkdir()
    Stub.seen.clear()
    p = project(repo)
    p.measurements.add_many([("sensor/queue.depth", time.time() - 60, 1.0)])
    assert not storage.in_default_home(p.dir)
    assert p.measurements.name == "sqlite" and (p.dir / "measurements.db").exists()
    assert not (p.dir / "measurements.backend").exists() and Stub.seen == []
    monkeypatch.setenv("ERGOSTAT_DEFAULT_MEASUREMENTS", "victoriametrics")    # asked: then it does
    assert storage.measurements_backend(storage.Storage(), tmp_path / "throwaway" / "other") == "victoriametrics"


def test_reset_keeps_a_sqlite_record_on_sqlite(tmp_path, monkeypatch, stub):
    """``ergostat reset --yes`` deletes measurements.db; under the default home with a server answering, the record
    it leaves is still SQLite, never silently VictoriaMetrics-backed."""
    from ergostat.cli import main
    monkeypatch.delenv("ERGOSTAT_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "user"))                       # the default home
    monkeypatch.setattr(storage, "VM_URL", stub)                             # a server answering there
    repo = tmp_path / "repo"
    repo.mkdir()
    p = project(repo)                                                        # (made SQLite: the fixture's default)
    p.measurements.add_many([("sensor/queue.depth", time.time() - 60, 1.0)])
    assert storage.in_default_home(p.dir) and (p.dir / "measurements.db").exists()
    monkeypatch.delenv("ERGOSTAT_DEFAULT_MEASUREMENTS")
    assert main(["-C", str(repo), "reset", "--yes"]) == 0
    assert not (p.dir / "measurements.db").exists()
    assert storage.measurements_backend(storage.Storage(), p.dir) == "sqlite"
    assert project(repo).measurements.name == "sqlite"
    fresh = p.dir.parent / "fresh-0"                                         # (whereas a new record here is asked)
    fresh.mkdir()
    assert storage.measurements_backend(storage.Storage(), fresh) == "victoriametrics"


def test_reset_of_a_victoriametrics_record_deletes_its_series_in_the_server(tmp_path, stub, capsys):
    """On VictoriaMetrics, ``ergostat reset --yes`` deletes this project's series in the server (every name, the old
    single one too) and the backfill ledger, so the record that starts from nothing reads nothing old back; a server
    that is away refuses the reset, and nothing local is deleted."""
    from ergostat.cli import main
    repo = tmp_path / "repo"
    repo.mkdir()
    p = project(repo, f"storage:\n  measurements: {{backend: victoriametrics, url: '{stub}'}}\n")
    assert isinstance(p.measurements, Victoria)
    for n in ("measurements.backfilled.db", "measurements.forgotten.json"):
        (p.dir / n).write_bytes(b"")
    Stub.seen.clear()
    assert main(["-C", str(repo), "reset"]) == 0                               # (says so, deletes nothing)
    assert f"every reading of project {p.dir.name} in VictoriaMetrics" in capsys.readouterr().out and Stub.seen == []
    assert main(["-C", str(repo), "reset", "--yes"]) == 0
    assert Stub.seen == [("/api/v1/admin/tsdb/delete_series", {"match[]": [p.measurements._sel()]})]
    assert '__name__=~".+"' in p.measurements._sel()                           # (OLD_METRIC and the old names included)
    assert not (p.dir / "measurements.backfilled.db").exists() and not (p.dir / "measurements.forgotten.json").exists()
    away = tmp_path / "away"
    away.mkdir()
    q = project(away, f"storage:\n  measurements: {{backend: victoriametrics, url: 'http://127.0.0.1:{free_port()}'}}\n")
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
          measurements: {backend: victoriametrics, run: victoria-metrics -storageDataPath vm -httpListenAddr 127.0.0.1:8428}
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
    assert [e.code for e in errors] == ["bad-storage"]


# ---- the migration's own logic, over an in-memory stand-in for the server (what runs without a binary)


def _cut(v: float) -> float:
    """A value as a lossy server keeps it: 12 significant digits, the rest cut (not rounded, unlike Python's .12g)."""
    if v == 0 or not math.isfinite(v):
        return v
    d = Decimal(v)
    return float(d.quantize(Decimal(1).scaleb(d.adjusted() - 11), rounding=ROUND_DOWN))


class Mem(Victoria):
    """A Victoria whose server is a dict: what is exported, imported and deleted, by the selectors migrate uses. Its
    values are kept as ``_cut`` keeps them, and with ``keep`` (seconds) a reading older than that is dropped unsaid,
    as VictoriaMetrics drops one older than its -retentionPeriod."""

    def __init__(self, d):
        super().__init__("http://127.0.0.1:9", d, project="mem")
        self.new: dict[str, list] = {}
        self.old: dict[str, list] = {}
        self.keep: float | None = None

    def _rows(self, sel, start=None, end=None):
        if 'kind!=""' in sel:                                    # (the old item metrics: none here)
            return []
        assert 'series!=""' in sel, sel                          # (every series, under each name it is held)
        return ([({"__name__": OLD_METRIC, "series": s}, list(p)) for s, p in self.old.items()]
                + [({**self.labels(s), "series": s}, sorted(p)) for s, p in self.new.items()])

    def _export(self, series, start=None, end=None, sel=None):
        if sel is None:                                          # (every series this project holds)
            return {s: sorted(p) for s, p in self.new.items()}
        s = json.loads(sel.split("series=", 1)[1].rstrip("}"))    # (_held: one series under its current name)
        assert f'__name__="{self.labels(s)["__name__"]}"' in sel, sel
        return {s: sorted(self.new[s])} if s in self.new else {}

    def add_many(self, rows):
        for s, t, v in rows:
            if self.keep is None or t >= time.time() - self.keep:
                self.new.setdefault(s, []).append((round(t * 1000) / 1000, _cut(v)))

    def _req(self, path, params=None, body=None):
        assert path == "/api/v1/admin/tsdb/delete_series" and OLD_METRIC in params["match[]"]
        del self.old[json.loads(params["match[]"].split("series=", 1)[1].rstrip("}"))]
        return b""


def test_the_migration_sends_each_reading_once_and_renames_the_old_name(tmp_path):
    now = time.time()
    src = _record(tmp_path, now)
    dst = Mem(tmp_path)
    dst.old = {"sensor/q.n": [(now - 60, 1.0), (now - 30, 2.0)], "plain": [(now - 600 + 1, 1.5)]}   # (one held already)
    want = {s: [(round(t * 1000), v) for t, v in src.range(s, 0, UNTIL)] for s in SERIES}
    assert 0 < len(want["sensor/old.many"]) < 2000                           # (rolled: each bucket's last reading stands)
    assert any(_cut(v) != v for _, v in want["run/builder/cpu"])             # (values the server keeps cut)
    n = sum(map(len, want.values()))
    first = migrate(tmp_path, dst, src.tiers)
    assert first == {"series": 6, "readings": n, "sent": n + 2, "renamed": 2, "missing": 0, "lost": {}} and dst.old == {}
    held = _held(dst)
    _same(held, {**want, "sensor/q.n": [(round((now - 60) * 1000), 1.0), (round((now - 30) * 1000), 2.0)]})
    assert migrate(tmp_path, dst, src.tiers, dry=True)["sent"] == 0
    assert migrate(tmp_path, dst, src.tiers) == {**first, "sent": 0, "renamed": 0}
    assert _held(dst) == held                                                # twice: nothing changed, long floats too
    src.add("plain", 7.0, now)                                               # (written after: sent by the next run)
    assert migrate(tmp_path, dst, src.tiers)["sent"] == 1


def test_readings_the_server_does_not_keep_are_named_not_counted_as_sent(tmp_path):
    now = time.time()
    src = _record(tmp_path, now)
    dst = Mem(tmp_path)
    dst.keep = 86400.0                                       # (as -retentionPeriod=1d: the record's day-old readings go)
    dst.old = {"sensor/q.n": [(now - 3 * 86400, 1.0), (now - 30, 2.0)]}
    want = {s: src.range(s, 0, UNTIL) for s in SERIES}
    gone = {s: [t for t, _ in p if t < now - 86400] for s, p in want.items()}
    gone = {s: ts for s, ts in gone.items() if ts} | {"sensor/q.n": [now - 3 * 86400]}
    assert set(gone) == set(SERIES) - {"plain"} | {"sensor/q.n"}
    n_gone = sum(map(len, gone.values()))
    got = migrate(tmp_path, dst, src.tiers)
    assert (got["missing"], got["sent"], got["renamed"]) == (n_gone, sum(map(len, want.values())) + 2 - n_gone, 0)
    assert got["lost"] == {s: {"n": len(ts), "first": min(ts), "last": max(ts)} for s, ts in gone.items()}
    assert dst.old["sensor/q.n"]                             # (not all held under the new name: the old one stays)
    again = migrate(tmp_path, dst, src.tiers)
    assert (again["sent"], again["missing"]) == (0, n_gone)  # (sent again, still not kept: never said to be held)


def test_ergostat_migrate_says_what_it_sent_and_a_server_away_fails_it(tmp_path, monkeypatch, capsys):
    import ergostat.victoria
    from ergostat.cli import main
    p = project(tmp_path)
    p.measurements.add_many([("sensor/queue.depth", time.time() - 60 * i, float(i)) for i in range(5)])
    assert main(["-C", str(tmp_path), "migrate", "--url", f"http://127.0.0.1:{free_port()}"]) == 1
    assert "VictoriaMetrics at" in capsys.readouterr().err
    mem = Mem(p.dir)
    monkeypatch.setattr(ergostat.victoria, "Victoria", lambda url, d: mem)
    assert main(["-C", str(tmp_path), "--json", "migrate", "--dry-run"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert (got["sent"], got["dry_run"], got["url"], mem.new) == (5, True, "http://127.0.0.1:8428", {})
    assert main(["-C", str(tmp_path), "migrate"]) == 0
    assert "5 readings read from SQLite; sent 5" in capsys.readouterr().out and len(mem.new["sensor/queue.depth"]) == 5
    p.measurements.add_many([("sensor/queue.depth", time.time() - 3 * 86400, 9.0)])
    mem.keep = 86400.0                                                # (the server drops it, unsaid)
    assert main(["-C", str(tmp_path), "migrate"]) == 1
    out, err = capsys.readouterr()
    assert "sent 0" in out and "To read them from there" not in out  # (never told to switch over a loss)
    assert "1 readings sent were not kept" in err and "sensor/queue.depth: 1 readings" in err and "-retentionPeriod" in err
    assert main(["-C", str(tmp_path), "--json", "migrate"]) == 1
    assert json.loads(capsys.readouterr().out)["lost"]["sensor/queue.depth"]["n"] == 1


# ---- a real VictoriaMetrics


@pytest.fixture(scope="module")
def vm(tmp_path_factory):
    if VM_URL:
        yield VM_URL.rstrip("/")
        return
    if not VM_BIN:
        pytest.skip(SKIP)
    with _server(tmp_path_factory.mktemp("vm"), "100y") as url:
        yield url


@contextlib.contextmanager
def _server(d, retention: str):
    """A VictoriaMetrics started here from VM_BIN, keeping ``retention``, stopped after."""
    d.mkdir(exist_ok=True)
    port = free_port()
    with open(d / "vm.log", "w") as log:
        proc = subprocess.Popen([VM_BIN, f"-storageDataPath={d / 'data'}", f"-httpListenAddr=127.0.0.1:{port}",
                                 f"-retentionPeriod={retention}", "-search.disableCache", "-loggerLevel=ERROR"],
                                stdout=subprocess.DEVNULL, stderr=log, start_new_session=True,
                                env={**os.environ, "GOMAXPROCS": "2"})
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(300):
            if storage._answers(url):
                break
            assert proc.poll() is None, (d / "vm.log").read_text()[-2000:]
            time.sleep(0.1)
        else:
            pytest.fail("VictoriaMetrics did not answer within 30 s")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)


def _vm(url, d):
    return Victoria(url, d, project=f"test-{uuid.uuid4().hex[:10]}")


def _held(dst: Victoria) -> dict:
    return {s: [(round(t * 1000), v) for t, v in pts] for s, pts in dst._export(None, 0, UNTIL).items()}


def _same(got: dict, want: dict) -> None:
    """The same series, times and number of readings; the values to the digits the server keeps."""
    g, w = (sorted((s, t, v) for s, p in x.items() for t, v in p) for x in (got, want))
    assert [x[:2] for x in g] == [x[:2] for x in w]
    assert [x[2] for x in g] == pytest.approx([x[2] for x in w], rel=1e-10, abs=0)


SERIES = ("sensor/queue.depth", "run/builder/cost_usd", "valve/inflow", "plain", "sensor/old.many", "run/builder/cpu")
LONG = [1 / 3, 2 / 3, 0.1 + 0.2, 1e-7, 123456.789012345, math.pi * 1e9, 2 / 3 * 1e-12, -1 / 7, 0.0]


def _record(d, now: float) -> Measurements:
    """A SQLite record: raw readings of five series (one of long floats), and a day of one rolled into 1-minute buckets."""
    src = Measurements(d, raw=3600.0, tiers=[(60.0, 30 * 86400.0)])
    t0 = math.floor((now - 2 * 86400) / 60) * 60
    rows = [("sensor/queue.depth", t0 + 60 * i + 0.5, float(i % 7)) for i in range(300)]
    rows += [("run/builder/cost_usd", t0 + 600 * i + 0.25, 0.01 * i) for i in range(40)]
    rows += [("valve/inflow", t0 + 300 * i, float(i % 2)) for i in range(50)]
    rows += [("plain", now - 600 + i, 1.5 * i) for i in range(30)]            # (raw: inside the last hour)
    rows += [("sensor/old.many", t0 + 10 * i, float(i)) for i in range(2000)]  # (six to a minute: rolled to each one's last)
    rows += [("run/builder/cpu", t0 + 900 * i + 0.125, v) for i, v in enumerate(LONG)]
    src.add_many(rows)
    src.roll(now)
    return src


def test_a_record_is_migrated_with_every_reading_and_answers_promql(tmp_path, vm):
    now = time.time()
    src = _record(tmp_path, now)
    dst = _vm(vm, tmp_path)
    try:
        got = migrate(tmp_path, dst, src.tiers)
        want = {s: [(round(t * 1000), v) for t, v in src.range(s, 0, UNTIL)] for s in SERIES}
        assert len(want["sensor/old.many"]) < 2000 and want["sensor/old.many"]   # (the buckets' last readings stand)
        n = sum(map(len, want.values()))
        assert got == {"series": 6, "readings": n, "sent": n, "renamed": 0, "missing": 0, "lost": {}}
        _same(_held(dst), want)                                                   # every reading, its time and value
        g = grid(now - 3 * 86400, now, 3)
        ask = lambda text: datasources.query(None, "ergostat", text, g, store=dst)["series"]   # noqa: E731
        [s] = ask('count_over_time(queue{sensor="depth"}[10d])')
        assert s["name"].startswith("{") and 'sensor="depth"' in s["name"] and s["values"][-1] == 300.0
        [s] = ask("sum by (block) (count_over_time(ergostat_run_cost_usd[10d]))")
        assert s["name"] == '{block="builder"}' and s["values"][-1] == 40.0
        [s] = ask('max_over_time(ergostat_valve_position{valve="inflow"}[10d])')
        assert s["values"][-1] == 1.0
        other = Victoria(vm, tmp_path, project=f"test-{uuid.uuid4().hex[:10]}")
        other.add_many([("sensor/queue.depth", now - 86400, 9.0)])
        try:                                                                     # (another project's series is not seen)
            [s] = ask('count_over_time(queue{sensor="depth"}[10d])')
            assert s["values"][-1] == 300.0
        finally:
            other.drop()
    finally:
        dst.drop()


def test_migrating_twice_changes_nothing(tmp_path, vm):
    src = _record(tmp_path, time.time())
    dst = _vm(vm, tmp_path)
    try:
        first = migrate(tmp_path, dst, src.tiers)
        held = _held(dst)
        again = migrate(tmp_path, dst, src.tiers)
        assert first["sent"] > 0 and first["missing"] == 0 and again == {**first, "sent": 0}
        assert _held(dst) == held                                    # (the long floats too, as the server returns them)
        assert migrate(tmp_path, dst, src.tiers, dry=True)["sent"] == 0
    finally:
        dst.drop()


def test_readings_a_real_server_drops_are_named_not_counted_as_sent(tmp_path):
    """A server keeping one day (-retentionPeriod=1d): the record's two-day-old readings are sent, not kept, and named."""
    if not VM_BIN:
        pytest.skip(SKIP)
    now = time.time()
    src = _record(tmp_path, now)
    with _server(tmp_path / "vm", "1d") as url:
        dst = _vm(url, tmp_path)
        got = migrate(tmp_path, dst, src.tiers)
        n_plain = len(src.range("plain", 0, UNTIL))
        assert got["sent"] == n_plain and set(got["lost"]) == set(SERIES) - {"plain"}
        assert got["missing"] == got["readings"] - n_plain
        assert migrate(tmp_path, dst, src.tiers)["missing"] == got["missing"]


def test_a_record_under_the_old_single_name_is_renamed_once(tmp_path, vm):
    dst = _vm(vm, tmp_path)
    now = time.time()
    lines = [{"metric": {"__name__": OLD_METRIC, "project": dst.project, "series": "sensor/q.n"},
              "values": [1.0, 2.0, 3.0], "timestamps": [round((now - 3600 + i) * 1000) for i in range(3)]}]
    try:
        dst._req("/api/v1/import", body="".join(json.dumps(x) + "\n" for x in lines).encode())
        dst._req("/internal/force_flush")
        dst.add_many([("sensor/q.n", now - 1800, 4.0)])                  # (written after the upgrade, under its labels)
        [s] = dst.series()
        assert (s["n"], s["value"]) == (4, 4.0)                          # both names read, before it migrates
        assert migrate(tmp_path, dst)["renamed"] == 1
        assert migrate(tmp_path, dst) == {"series": 0, "readings": 0, "sent": 0, "renamed": 0, "missing": 0, "lost": {}}
        got = dst._export(None, 0, UNTIL, sel="{" + f'project="{dst.project}"' + "}")
        assert [v for _, v in got["sensor/q.n"]] == [1.0, 2.0, 3.0, 4.0]
        assert dst._query(f'count({OLD_METRIC}{{project="{dst.project}"}})', now) == []
        assert dst.range("sensor/q.n", now - 7200) == got["sensor/q.n"]
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
