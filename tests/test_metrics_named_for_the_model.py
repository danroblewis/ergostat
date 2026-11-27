"""metrics-named-for-the-model (dev/records/metrics-named-for-the-model.md): a model's projections and parts are
top-level PromQL metrics under their own names (``gap_items``, ``gaps_approved``), and only the engine's internals keep
``ergostat_``. Each test that needs a server runs against a small Prometheus-compatible stand-in here (what it was sent,
and the names it holds) and against a real VictoriaMetrics too (this test process's own: tests/conftest.py, ``vm``)."""

from __future__ import annotations

import json
import re
import textwrap
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from ergostat import datasources
from ergostat import itemmetrics as im
from ergostat import model as mdl
from ergostat.promnames import Names, convert, item_labels
from ergostat.query.buckets import grid
from ergostat.spec import read
from ergostat.store import Project
from ergostat.victoria import Victoria

ROOT = Path(__file__).resolve().parent.parent
OLD_GENERIC = {"ergostat_sensor", "ergostat_items", "ergostat_item_transitions_total", "ergostat_item_field_total",
               "ergostat_item_last_transition_timestamp_seconds", "ergostat_item_time_in_state_seconds_bucket",
               "ergostat_item_time_in_state_seconds_sum", "ergostat_item_time_in_state_seconds_count"}
# the engine's own, an allowlist: a run's and an observer's measures, valves, block outputs, the index's counters and
# the built-in projections (ergostat.model-change, ...)
ENGINE = re.compile(r"ergostat_(run_\w+|observer_\w+|valve_position|block_output|events_total|item_index_rebuilds_total"
                    r"|(model_change|modelling_request|claim|message)_\w+)")


# ---- a Prometheus-compatible stand-in: what is imported, the names it holds, the queries asked


class Prom(BaseHTTPRequestHandler):
    held: list = []          # each imported series' labels
    asked: list = []         # each query's text

    def log_message(self, *a):
        pass

    def _send(self, body: bytes, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if urlparse(self.path).path == "/api/v1/import":
            type(self).held += [json.loads(x)["metric"] for x in body.decode().splitlines() if x.strip()]
        self._send(b"")

    def do_GET(self):
        u = urlparse(self.path)
        a = parse_qs(u.query)
        project = a.get("extra_label", ["project="])[0].split("=", 1)[1]
        if u.path == "/api/v1/label/__name__/values":
            m = re.fullmatch(r'\{__name__=~(".*")\}', (a.get("match[]") or ['{__name__=~".*"}'])[0])
            names = sorted({x["__name__"] for x in type(self).held if x.get("project") == project
                            and re.fullmatch(json.loads(m[1]), x["__name__"])})
            return self._send(json.dumps({"status": "success", "data": names}).encode())
        if u.path == "/api/v1/query_range":
            type(self).asked.append(a["query"][0])
            return self._send(json.dumps({"status": "success", "data": {"resultType": "matrix", "result": []}}).encode())
        self._send(b"")


@pytest.fixture(scope="module")
def prom():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Prom)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def factory():
    spec, problems = read(ROOT / "ergostat.yaml")
    assert not [str(p) for p in problems if p.level == "error"]
    return spec


def _store(url: str, d: Path, spec) -> Victoria:
    v = Victoria(url, d, project=f"test-{uuid.uuid4().hex[:10]}")
    v.spec_of = lambda: spec
    return v


def _metrics(spec, v: Victoria, prefix: str) -> list[str]:
    return datasources.suggest("promql", "metrics", prefix=prefix, store=v)["suggestions"]


# ---- done item 1: the factory


def test_the_factory_names_its_items_and_parts_for_themselves(factory):
    n = Names(factory)
    assert n.clashes == []
    assert n.labels("sensor/gaps-approved.main") == {"__name__": "gaps_approved"}      # (one sensor: no label)
    assert n.labels("sensor/merges-per-hour.main") == {"__name__": "merges_per_hour"}
    assert item_labels({"__name__": im.ITEMS, "kind": "gap", "state": "ready"}) == {"__name__": "gap_items", "state": "ready"}
    for s in factory.sensors():                          # every part's readings under a name of the model's own
        assert not n.labels(s.series)["__name__"].startswith("ergostat_"), s.series
    for engine in ("run/implementor/cost_usd", "block/queue-when", "valve/x", "observer/q/innovation"):
        assert ENGINE.fullmatch(n.labels(engine)["__name__"]), engine
    assert item_labels({"__name__": im.EVENTS, "type": "gap.merged"})["__name__"] == im.EVENTS     # the index's own
    assert item_labels({"__name__": im.ITEMS, "kind": "ergostat.model-change"})["__name__"] == "ergostat_model_change_items"


def _write_factory(spec, v: Victoria, t: float) -> None:
    v.add_many([(s.series, t, 1.0) for s in spec.sensors()] + [("run/implementor/cost_usd", t, 0.5),
                                                                ("block/queue-when", t, 1.0)])
    tally = im.Tally()
    tally.move(1, "gap", t - 120, None, "ready")
    tally.move(1, "gap", t - 60, "ready", "merged")
    tally.add(im.EVENTS, {"type": "gap.merged", "source": "queue"}, 1)
    tally.add(im.REBUILT, {}, 0)
    v.put([({"__name__": n, **dict(lb)}, t, x) for (n, lb), x in tally.v.items()])


def _lists_the_factory(spec, v: Victoria) -> None:
    assert "gap_items" in _metrics(spec, v, "gap_")
    assert {"gap_transitions_total", "gap_last_transition_timestamp_seconds"} <= set(_metrics(spec, v, "gap_"))
    assert "gaps_approved" in _metrics(spec, v, "gaps_")
    assert "merges_per_hour" in _metrics(spec, v, "merges")
    own = _metrics(spec, v, "ergostat_")
    assert own and not set(own) & OLD_GENERIC
    assert [x for x in own if not ENGINE.fullmatch(x)] == []          # the old generic names: only engine internals


def test_autocomplete_on_the_factory_lists_its_own_metrics(factory, prom, tmp_path):
    """Done item 1, over the stand-in (what ergostat writes and asks: runs everywhere)."""
    v = _store(prom, tmp_path, factory)
    _write_factory(factory, v, time.time() - 60)
    _lists_the_factory(factory, v)


def test_autocomplete_on_the_factory_in_a_real_victoriametrics(factory, vm, tmp_path):
    """Done item 1, in a real VictoriaMetrics."""
    v = _store(vm, tmp_path, factory)
    try:
        _write_factory(factory, v, time.time() - 60)
        _lists_the_factory(factory, v)
    finally:
        v.drop()


# ---- done item 2: two projections and a sensor


TWO = """
name: two
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        values: [open, done]
    events:
      ticket-opened:
        when: type == 'ticket.opened'
        '...': data
        state: set('open')
      ticket-closed:
        when: type == 'ticket.closed'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
  review:
    query: key.startswith('review/')
    fields:
      state:
        values: [asked, given]
    events:
      review-asked:
        when: type == 'review.asked'
        '...': data
        state: set('asked')
      review-given:
        when: type == 'review.given'
        '...': data
        state: set('given')
      other:
        when: true
        '...': data
stocks:
  backlog:
    unit: tickets
    sensor: {projection: ticket, state: open, every: 1m}
"""
T0 = float(int(time.time()) // 60 * 60 - 7200)          # (two hours ago, on a minute: within the day
                                                       # VictoriaMetrics lists names from by default)


def _two(tmp_path, url, req=None):
    (tmp_path / "m").mkdir(parents=True)
    (tmp_path / "state").mkdir()
    (tmp_path / "m" / "ergostat.yaml").write_text(textwrap.dedent(TWO))
    m = mdl.load(tmp_path / "m")
    p = Project(m, directory=tmp_path / "state")
    for i in range(3):
        p.events.add("ticket.opened", item=f"ticket/t{i}", source="intake", at=T0 + 1 + i)
    p.events.add("ticket.closed", item="ticket/t0", source="desk", at=T0 + 30)
    p.events.add("review.asked", item="review/r1", source="desk", at=T0 + 40)
    v = _store(url, p.dir, m.spec)
    if req is not None:                                     # (what is sent, kept here)
        v._req = req
    rec = SimpleNamespace(events=p.events, dir=p.dir, measurements=v, spec=m.spec)
    im.keep(rec, m.spec, now=T0 + 70)
    v.add_many([("sensor/backlog.main", T0 + 60, 2.0)])
    return rec, v


def _each_its_own(rec, v: Victoria) -> None:
    names = set(_metrics(rec.spec, v, ""))
    assert {"ticket_items", "review_items", "ticket_transitions_total", "review_transitions_total",
            "ticket_last_transition_timestamp_seconds", "backlog"} <= names
    assert not names & OLD_GENERIC


def test_two_kinds_and_a_sensor_are_each_their_own_metric(tmp_path, prom):
    """Done item 2, over the stand-in."""
    rec, v = _two(tmp_path, prom)
    _each_its_own(rec, v)


def test_two_kinds_and_a_sensor_in_a_real_victoriametrics(tmp_path, vm):
    """Done item 2: each its own metric, and each answers its own PromQL."""
    rec, v = _two(tmp_path, vm)
    try:
        _each_its_own(rec, v)
        at = T0 + 60
        assert [x for _, x in v._query(f'sum(ticket_items{{project="{v.project}",state="open"}})', at)] == [2.0]
        assert [x for _, x in v._query(f'sum(review_items{{project="{v.project}"}})', at)] == [1.0]
        assert [x for _, x in v._query(f'backlog{{project="{v.project}"}}', at)] == [2.0]
        assert v.range("sensor/backlog.main", T0) == [(T0 + 60, 2.0)]                 # (read back by its series)
        got = v._query(f'time() - max(ticket_last_transition_timestamp_seconds{{project="{v.project}",to="done"}})', at)
        assert [x for _, x in got] == [pytest.approx(30.0)]
    finally:
        v.drop()


# ---- done item 3: a collision refused at check, and no item id a label


def test_a_part_whose_name_another_takes_is_refused_at_check_with_the_fix(tmp_path, capsys):
    from ergostat.cli import main
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""\
        name: clash
        projections:
          ticket:
            query: key.startswith('ticket/')
            fields:
              state:
                values: [open]
            events:
              ticket-opened:
                when: type == 'ticket.opened'
                '...': data
                state: set('open')
              other:
                when: true
                '...': data
        stocks:
          ticket-items: {unit: tickets}
"""))
    spec, problems = read(tmp_path / "ergostat.yaml")
    [p] = [x for x in problems if x.level == "error"]
    assert p.code == "metric-clash" and "ticket_items" in p.message and "rename it, or put it in a system" in p.message
    assert main(["-C", str(tmp_path), "check"]) != 0
    out, err = capsys.readouterr()
    assert "metric-clash" in out + err or "ticket_items is taken" in out + err
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""\
        name: apart
        systems: {desk: {description: the help desk}}
        projections:
          ticket:
            query: key.startswith('ticket/')
            fields:
              state:
                values: [open]
            events:
              ticket-opened:
                when: type == 'ticket.opened'
                '...': data
                state: set('open')
              other:
                when: true
                '...': data
        stocks:
          ticket-items: {unit: tickets, system: desk, sensor: {projection: ticket, state: open, every: 1m}}
          ergostat-load: {unit: jobs, system: desk}
          queue: {unit: jobs, sensors: {depth: {manual: true}, age: {manual: true}}}
"""))
    spec, problems = read(tmp_path / "ergostat.yaml")
    assert not [str(x) for x in problems if x.level == "error"]
    n = Names(spec)                                         # its system prepended, only where needed
    assert n.labels("sensor/ticket-items.main") == {"__name__": "desk_ticket_items"}
    assert n.labels("sensor/ergostat-load.x")["__name__"] == "desk_ergostat_load"
    assert n.labels("sensor/queue.depth") == {"__name__": "queue", "sensor": "depth"}     # several: the sensor a label
    assert n.labels("sensor/backlog.main") == {"__name__": "backlog", "sensor": "main"}  # (not in the model: its own)


def test_a_kind_that_would_read_as_the_engines_is_refused(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: k\nprojections:\n  ergostat-jobs:\n    query: key.startswith('job/')\n    fields:\n      state:\n        values: [open]\n    events:\n      job-opened:\n        when: type == 'job.opened'\n        '...': data\n        state: set('open')\n      other:\n        when: true\n        '...': data\n")
    _, problems = read(tmp_path / "ergostat.yaml")
    [p] = [x for x in problems if x.level == "error"]
    assert p.code == "metric-clash" and "ergostat_jobs_items" in p.message and p.message.endswith("rename it")


@pytest.mark.parametrize("path", sorted(str(p.relative_to(ROOT)) for p in (ROOT / "examples").rglob("ergostat.yaml")))
def test_no_example_has_a_metric_clash(path):
    """The rule refuses nothing that ran before: no shipped example's part loses its name to another."""
    spec, problems = read(ROOT / path)
    assert not [str(x) for x in problems if x.code == "metric-clash"]


def test_no_item_id_becomes_a_label(tmp_path):
    sent = []
    rec, v = _two(tmp_path, "http://127.0.0.1:9", lambda path, params=None, body=None: sent.append(body) or b"")
    rec.events.add("ticket.opened", item="ticket/t9", source="intake", at=T0 + 75)
    im.keep(rec, rec.spec, now=T0 + 130)                  # (and the next minute, an item more)
    lines = [json.loads(x) for b in sent if b for x in b.decode().splitlines()]
    ids = {f"ticket/t{i}" for i in (0, 1, 2, 9)} | {"review/r1"}
    assert {x["metric"]["__name__"] for x in lines} >= {"ticket_items", "review_items", "backlog"}
    for x in lines:
        assert not set(x["metric"].values()) & ids, x["metric"]
        assert set(x["metric"]) <= {"__name__", "project", "series", "sensor", "state", "from", "to", "le", "field",
                                    "type", "source", "milestone"}, x["metric"]
    with pytest.raises(im.Refused):
        im.Tally().add(im.ITEMS, {"kind": "ticket", "id": "ticket/t1"}, 1)


# ---- done item 4: the default dashboards, and queries saved under the old names


DOCUMENTED = [   # (an old query, as docs/DASHBOARDS.md wrote it, and the new)
    ('ergostat_sensor{part="backlog", sensor="count"}', 'backlog{sensor="count"}'),
    ('sum by (state) (ergostat_items{kind="gap"})', "sum by (state) (gap_items)"),
    ('sum(increase(ergostat_item_transitions_total{kind="gap",to="merged"}[1d]))',
     'sum(increase(gap_transitions_total{to="merged"}[1d]))'),
    ('time() - max(ergostat_item_last_transition_timestamp_seconds{kind="gap",to="merged"})',
     'time() - max(gap_last_transition_timestamp_seconds{to="merged"})'),
    ('histogram_quantile(0.85, sum by (le) (rate(ergostat_item_time_in_state_seconds_bucket{kind="gap",state="building"}[7d])))',
     'histogram_quantile(0.85, sum by (le) (rate(gap_time_in_state_seconds_bucket{state="building"}[7d])))'),
]


def test_the_default_dashboards_ask_no_old_name(factory):
    from ergostat.web.dashboard_api import default
    d = default(factory)                                   # the model's default: its systems' measures and goals, by ref
    assert d.panels and all(p.panel in ("chart", "goals") for p in d.panels)
    texts = json.dumps([p.params for p in d.panels]) + "".join(
        x.read_text() for x in sorted((ROOT / "ergostat" / "web" / "ui" / "src" / "pages" / "dashboard").rglob("*.ts*")))
    texts += "".join(x.read_text() for x in (ROOT / "dev" / "model").glob("*.yaml"))
    assert not [x for x in OLD_GENERIC if x in texts]
    docs = (ROOT / "docs" / "DASHBOARDS.md").read_text()
    for old, new in DOCUMENTED:
        assert old not in docs and new in docs, new


def test_a_query_saved_under_an_old_name_asks_the_new(prom, tmp_path):
    for old, new in DOCUMENTED:                            # (no model: a part's sensor kept as a label)
        got, said = convert(old, Names())
        assert got == new and said, old
    n = Names(read_two(tmp_path))
    assert convert('ergostat_sensor{part="backlog",sensor="main"}', n)[0] == "backlog"   # (one sensor: no label)
    assert convert("sum by (kind) (ergostat_items)", n) == ("sum by (kind) (ergostat_items)", [])   # (no kind: as written)
    v = _store(prom, tmp_path, None)
    Prom.asked.clear()
    g = grid(1_795_400_000.0, 1_795_400_400.0, 4)
    got = datasources.query(None, "promql", 'sum by (state) (ergostat_items{kind="gap"})', g, store=v)
    assert Prom.asked == ['sum by (state) ({__name__=~"gap_items|ergostat_items",kind=~"gap|"})']   # (both names)
    assert [w[0] for w in got["warnings"]] == ["old-name"] and 'ergostat_items{kind="gap"} -> gap_items' in got["warnings"][0][1]


_MATCHER = re.compile(r'\s*([A-Za-z_]\w*)\s*(=~|!=|=)\s*("(?:[^"\\]|\\.)*")\s*')


def _selects(selector: str, labels: dict) -> bool:
    """Whether a PromQL selector ``{...}`` takes a series of these labels (an absent label reads as "")."""
    for m in _MATCHER.finditer(selector.strip()[1:-1]):
        k, op, v = m[1], m[2], json.loads(m[3])
        got = labels.get(k, "")
        if not (re.fullmatch(v, got) if op == "=~" else (got == v) == (op == "=")):
            return False
    return True


def test_a_saved_old_query_asks_the_record_under_either_name(tmp_path):
    """A query saved under the old names reads the record under the old names and under the new, and nothing of
    another part or kind (done item 4: it answers as before)."""
    n = Names(read_two(tmp_path))
    for old, before, after, other in [
        ('ergostat_sensor{part="backlog",sensor="main"}',
         {"__name__": "ergostat_sensor", "part": "backlog", "sensor": "main", "series": "sensor/backlog.main"},
         {"__name__": "backlog", "series": "sensor/backlog.main"},
         {"__name__": "ergostat_sensor", "part": "backlog2", "sensor": "main"}),
        ('ergostat_items{kind="ticket",state="open"}',
         {"__name__": "ergostat_items", "kind": "ticket", "state": "open"},
         {"__name__": "ticket_items", "state": "open"},
         {"__name__": "ergostat_items", "kind": "review", "state": "open"}),
        ('ergostat_item_time_in_state_seconds_bucket{kind="ticket",le="60"}',
         {"__name__": "ergostat_item_time_in_state_seconds_bucket", "kind": "ticket", "le": "60"},
         {"__name__": "ticket_time_in_state_seconds_bucket", "le": "60"},
         {"__name__": "ticket_items", "le": "60"})]:
        sel, said = convert(old, n, both=True)
        assert said and _selects(sel, before) and _selects(sel, after), sel
        assert not _selects(sel, other), sel
        new = convert(old, n)[0]                            # (the new name alone misses the record under the old)
        assert not _selects("{" + f'__name__="{new.partition("{")[0]}",' + new.partition("{")[2].rstrip("}") + "}", before)
        for k in {"state", "le"} & set(after):              # (its other matchers kept)
            assert not _selects(sel, {**after, k: "x"}), sel


def _one_series_under_two_names(v: Victoria, t: float, old_later: bool = False):
    """``sensor/backlog.main`` under the old name (7, at t) and its new one (2, at t + 30); ``old_later``: the other way
    round (the old name's reading the later)."""
    a, b = (t + 30, t) if old_later else (t, t + 30)
    return [{"metric": {"__name__": "ergostat_sensor", "part": "backlog", "sensor": "main", "project": v.project,
                        "series": "sensor/backlog.main"}, "values": [7.0], "timestamps": [round(a * 1000)]},
            {"metric": {"__name__": "backlog", "project": v.project, "series": "sensor/backlog.main"},
             "values": [2.0], "timestamps": [round(b * 1000)]}]


def test_a_series_under_both_names_shows_its_latest_value(tmp_path):
    """A series' value is its latest reading's, under whichever name, not the one with more labels (lesson 2): over a stand-in answering as VictoriaMetrics does, in either order."""
    v = _store("http://127.0.0.1:9", tmp_path, read_two(tmp_path / "m"))
    t = 1_795_400_000.0
    for old_later, order in [(o, h) for o in (False, True) for h in (_one_series_under_two_names(v, t, o),
                                                                     _one_series_under_two_names(v, t, o)[::-1])]:
        def query(q, at, order=order):
            if q.startswith("sum by (series)"):
                return [({"series": "sensor/backlog.main"}, 2.0)]
            if q.startswith("max by (series)"):
                return [({"series": "sensor/backlog.main"}, t + 30)]
            assert q.endswith("keep_metric_names"), q        # (each name's own, not merged into one)
            pick = (lambda x: x["timestamps"][0] / 1000) if q.startswith("tlast") else (lambda x: x["values"][0])
            return [(dict(x["metric"]), pick(x)) for x in order]
        v._query, v._sync_reads = query, lambda: None
        assert v.series() == [{"series": "sensor/backlog.main", "n": 2, "last": t + 30, "value": 7.0 if old_later else 2.0}]


def test_a_series_under_both_names_in_a_real_victoriametrics(tmp_path, vm):
    v = _store(vm, tmp_path, read_two(tmp_path / "m"))
    t = time.time() - 600
    try:
        v._req("/api/v1/import", body="".join(json.dumps(x) + "\n" for x in _one_series_under_two_names(v, t)).encode())
        v._req("/internal/force_flush")
        [got] = v.series()
        assert got["value"] == 2.0 and got["n"] == 2 and got["last"] == pytest.approx(t + 30)
    finally:
        v.drop()


def read_two(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(TWO))
    spec, _ = read(tmp_path / "ergostat.yaml")
    return spec


