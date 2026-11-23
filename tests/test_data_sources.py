"""Dashboard data sources (ergostat/datasources): a panel query in a source's own language, answered through the server
against a stub Prometheus; a fake type added by registering one module; the bounds, an unreachable source and a bad
query each refused in words; and no request but a read."""

from __future__ import annotations

import base64
import json
import textwrap
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from ergostat import datasources
from ergostat import model as mdl
from ergostat.datasources import prometheus
from ergostat.store import Project
from ergostat.web.server import Live, api
from tests.ports import free_port

T = 1_795_400_400.0         # a multiple of 120
ROOT = Path(__file__).resolve().parent.parent


class Stub(BaseHTTPRequestHandler):
    """A Prometheus that answers query_range: ``up`` two series, ``many`` 51, anything with ``(`` unclosed a parse error."""
    seen: list = []

    def log_message(self, *a):
        pass

    def answer(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        a = {k: v[0] for k, v in parse_qs(u.query).items()}
        type(self).seen.append(("GET", u.path, a))
        if u.path != "/api/v1/query_range":
            return self.answer(404, {"status": "error", "error": "not found"})
        text, start, end, step = a["query"], float(a["start"]), float(a["end"]), float(a["step"])
        if text.count("(") != text.count(")"):
            return self.answer(400, {"status": "error", "errorType": "bad_data",
                                     "error": "1:5: parse error: unclosed left parenthesis"})
        n = int(round((end - start) / step)) + 1
        names = [f"w{i}" for i in range(51)] if text == "many" else ["a", "b"]
        result = [{"metric": {"__name__": "up", "job": name},
                   "values": [[start + i * step, str(10 * j + i)] for i in range(n)]} for j, name in enumerate(names)]
        return self.answer(200, {"status": "success", "data": {"resultType": "matrix", "result": result}})

    def do_POST(self):
        type(self).seen.append(("POST", self.path, {}))
        self.answer(405, {"status": "error"})

    do_PUT = do_DELETE = do_POST


@pytest.fixture(scope="module")
def prom():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def project(tmp_path, sources: str) -> Project:
    (tmp_path / "ergostat.yaml").write_text("name: ds\nstocks:\n  queue: {unit: tickets}\nsources:\n"
                                            + textwrap.indent(textwrap.dedent(sources).strip() + "\n", "  "))
    return Project(mdl.load(tmp_path))


def ask(p, *queries, since=480.0, until=T + 480, points=4) -> list[dict]:
    body = {"since": since, "until": until, "points": points, "queries": [{"id": str(i), **x} for i, x in enumerate(queries)]}
    q = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    return api(Live(p), "query", {"q": [q]})["results"]


@pytest.fixture
def p(tmp_path, prom):
    return project(tmp_path, f"""
        prom: {{type: prometheus, url: "{prom}"}}
        down: {{type: prometheus, url: "http://127.0.0.1:{free_port()}"}}
        """)


def test_a_promql_range_query_answers_as_series_on_the_window(p):
    Stub.seen.clear()
    [r] = ask(p, {"source": "prom", "text": "sum by (job) (up)"})
    assert "error" not in r, r
    assert r["times"] == [T, T + 120, T + 240, T + 360] and r["step"] == 120
    assert {s["name"]: s["values"] for s in r["series"]} == {'up{job="a"}': [0.0, 1.0, 2.0, 3.0],
                                                             'up{job="b"}': [10.0, 11.0, 12.0, 13.0]}
    [(_, _, a)] = Stub.seen
    assert (float(a["start"]), float(a["end"]), a["step"]) == (T, T + 360, "120")


def test_an_old_query_still_answers_beside_a_source_query(p):
    r = ask(p, {"source": "counts"}, {"source": "prom", "text": "up"})
    assert "error" not in r[0] and "error" not in r[1]


def test_over_the_series_bound_unreachable_and_bad_each_say_so(p):
    many, down, bad, long_, nobody = ask(p, {"source": "prom", "text": "many"}, {"source": "down", "text": "up"},
                                         {"source": "prom", "text": "sum(up"},
                                         {"source": "prom", "text": "x" * (datasources.MOST_TEXT + 1)},
                                         {"source": "nowhere", "text": "up"})
    assert many["error_kind"] == "limit" and "51 series, more than the 50" in many["error"]
    assert down["error_kind"] == "unreachable" and "could not reach source 'down'" in down["error"]
    assert "127.0.0.1" not in down["error"]                               # never the address
    assert bad["error_kind"] == "refused" and "parse error: unclosed left parenthesis" in bad["error"]
    assert long_["error_kind"] == "limit" and "characters" in long_["error"]
    assert "no source named 'nowhere'" in nobody["error"]


def test_a_source_query_takes_only_source_and_text(p):
    [r] = ask(p, {"source": "prom", "text": "up", "agg": "sum"})
    assert "'agg' is not a key of a data source's query" in r["error"]
    [r] = ask(p, {"source": "items", "field": "x", "x": {"type": "bins", "query": {"source": "prom", "text": "up"}}})
    assert "cannot be an X" in r["error"]


def test_the_fields_list_a_source_by_name_type_and_language_never_its_address(p, prom):
    got = api(Live(p), "query/fields", {})["datasources"]
    assert got == [{"name": "prom", "type": "prometheus", "language": "PromQL"},
                   {"name": "down", "type": "prometheus", "language": "PromQL"}]
    assert prom not in json.dumps(api(Live(p), "query/fields", {}))


def fake_query(src, text, w):
    return [(f"{src.options['table']}:{text}", [(w.start + i * w.step, float(i * 2)) for i in range(w.points)])]


@pytest.fixture
def fake():
    datasources.register(types.SimpleNamespace(TYPE="fake", KEYS={"table"}, LANGUAGE="FakeQL", query=fake_query))
    yield
    datasources.unregister("fake")


def test_a_new_type_is_one_module_and_panels_do_not_change(tmp_path, fake):
    p = project(tmp_path, "f: {type: fake, table: t1}")
    [r] = ask(p, {"source": "f", "text": "count it"})
    assert r["series"] == [{"name": "t1:count it", "values": [0.0, 2.0, 4.0, 6.0]}]
    assert api(Live(p), "query/fields", {})["datasources"] == [{"name": "f", "type": "fake", "language": "FakeQL"}]
    static = ROOT / "ergostat" / "web" / "static"
    for js in ("panels.js", "panel-editor.js", "dashboard.js"):              # nothing in the page names a type
        text = (static / js).read_text().lower()
        assert "prometheus" not in text and "promql" not in text and "fakeql" not in text


def test_a_fake_type_over_the_series_bound_is_refused_whatever_its_type(tmp_path, fake, monkeypatch):
    monkeypatch.setattr(datasources, "MOST_SERIES", 0)
    p = project(tmp_path, "f: {type: fake, table: t1}")
    [r] = ask(p, {"source": "f", "text": "x"})
    assert r["error_kind"] == "limit" and "1 series, more than the 0" in r["error"]


def test_an_unknown_type_is_refused_by_check(tmp_path):
    with pytest.raises(Exception, match="type: one of"):
        project(tmp_path, "f: {type: nosuch}")


def test_a_type_offers_query_and_nothing_else():
    def write(src, text):
        pass
    with pytest.raises(TypeError, match="offers only query"):
        datasources.register(types.SimpleNamespace(TYPE="w", KEYS=set(), LANGUAGE="W", query=fake_query, write=write))
    assert "w" not in datasources.types()
    for name, mod in datasources.types().items():                          # every type there is: only query is offered
        own = {n for n, v in vars(mod).items() if not n.startswith("_") and callable(v)
               and getattr(v, "__module__", None) == mod.__name__}
        assert own == {"query"}, name


def test_prometheus_is_asked_by_get_on_query_range_only(p):
    Stub.seen.clear()
    ask(p, {"source": "prom", "text": "up"}, {"source": "prom", "text": "many"}, {"source": "prom", "text": "sum(up"})
    assert len(Stub.seen) == 3 and {(m, path) for m, path, _ in Stub.seen} == {("GET", "/api/v1/query_range")}
    assert prometheus._PATH == "/api/v1/query_range"
