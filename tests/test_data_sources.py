"""Ergostat's two data sources (ergostat/datasources; NOTES.md, 2026-11-25): ``promql`` and ``sql``, always listed,
each saying whether it can be asked and why not; a panel query in a source's own language, answered through the server
against a stub VictoriaMetrics standing in for the project's own (its measurements' ``base``); the bounds, an
unreachable server and a bad query each refused in words; no request but a read; and no source declared."""

from __future__ import annotations

import base64
import json
import ssl
import textwrap
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from ergostat import datasources
from ergostat import model as mdl
from ergostat.datasources import promql
from ergostat.store import Project
from ergostat.web.server import Live, api
from tests import tlscerts
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
        if u.path == "/health":                     # (VictoriaMetrics answering: what the listing asks)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")
            return None
        if u.path == "/api/v1/query":               # (the store's own reads of its newest readings: there are none)
            return self.answer(200, {"status": "success", "data": {"resultType": "vector", "result": []}})
        type(self).seen.append(("GET", u.path, a))
        if u.path != "/api/v1/query_range":
            return self.answer(404, {"status": "error", "error": "not found"})
        text, start, end, step = a["query"], float(a["start"]), float(a["end"]), float(a["step"])
        if text in ("stall", "trickle", "late"):
            return self.slow(text)
        if text.count("(") != text.count(")"):
            return self.answer(400, {"status": "error", "errorType": "bad_data",
                                     "error": "1:5: parse error: unclosed left parenthesis"})
        n = int(round((end - start) / step)) + 1
        names = [f"w{i}" for i in range(51)] if text == "many" else ["a", "b"]
        result = [{"metric": {"__name__": "up", "job": name},
                   "values": [[start + i * step, str(10 * j + i)] for i in range(n)]} for j, name in enumerate(names)]
        return self.answer(200, {"status": "success", "data": {"resultType": "matrix", "result": result}})

    def slow(self, how: str) -> None:
        """``late``: no headers for 30 s; ``stall``: headers, then nothing for 30 s; ``trickle``: a byte every 0.1 s,
        each well inside any one read's timeout, until ergostat hangs up."""
        if how == "late":
            time.sleep(30)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(10**6))
        self.end_headers()
        try:
            for _ in range(300 if how == "trickle" else 0):
                self.wfile.write(b" ")
                self.wfile.flush()
                time.sleep(0.1)
            time.sleep(0 if how == "trickle" else 30)
        except OSError:
            pass

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


def project(tmp_path, url: str, more: str = "") -> Project:
    """A project whose readings are on the VictoriaMetrics at ``url`` (here a stub): what ``promql`` asks."""
    (tmp_path / "ergostat.yaml").write_text("name: ds\nstocks:\n  queue: {unit: tickets}\n" + textwrap.dedent(more))
    p = Project(mdl.load(tmp_path))
    p.measurements.base = url
    datasources._ANSWERS.clear()
    return p


def ask(p, *queries, since=480.0, until=T + 480, points=4) -> list[dict]:
    body = {"since": since, "until": until, "points": points, "queries": [{"id": str(i), **x} for i, x in enumerate(queries)]}
    q = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    return api(Live(p), "query", {"q": [q]})["results"]


@pytest.fixture
def p(tmp_path, prom):
    return project(tmp_path, prom)


def test_a_promql_range_query_answers_as_series_on_the_window(p):
    Stub.seen.clear()
    [r] = ask(p, {"source": "promql", "text": "sum by (job) (up)"})
    assert "error" not in r, r
    assert r["times"] == [T, T + 120, T + 240, T + 360] and r["step"] == 120
    assert {s["name"]: s["values"] for s in r["series"]} == {'up{job="a"}': [0.0, 1.0, 2.0, 3.0],
                                                             'up{job="b"}': [10.0, 11.0, 12.0, 13.0]}
    [(_, _, a)] = Stub.seen
    assert (float(a["start"]), float(a["end"]), a["step"]) == (T, T + 360, "120")


def test_the_most_points_and_the_longest_window_are_answered(p):
    [r] = ask(p, {"source": "promql", "text": "up"}, since=400 * 86400.0, until=T + 7, points=1000)
    assert "error" not in r, r
    assert len(r["times"]) == 1001 and all(len(s["values"]) == 1001 for s in r["series"])


def test_a_window_past_the_points_bound_is_refused_in_words(p, monkeypatch):
    monkeypatch.setattr(datasources, "MOST_POINTS", 3)
    [r] = ask(p, {"source": "promql", "text": "up"}, until=T + 7)
    assert r["error_kind"] == "limit" and "points, more than the 3 allowed" in r["error"]


def test_an_old_query_still_answers_beside_a_source_query(p):
    r = ask(p, {"source": "counts"}, {"source": "promql", "text": "up"})
    assert "error" not in r[0] and "error" not in r[1]


def test_over_the_series_bound_unreachable_and_bad_each_say_so(p, tmp_path):
    many, bad, long_, nobody, old = ask(p, {"source": "promql", "text": "many"}, {"source": "promql", "text": "sum(up"},
                                        {"source": "promql", "text": "x" * (datasources.MOST_TEXT + 1)},
                                        {"source": "nowhere", "text": "up"}, {"source": "prom", "text": "up"})
    assert many["error_kind"] == "limit" and "51 series, more than the 50" in many["error"]
    assert bad["error_kind"] == "refused" and "parse error: unclosed left parenthesis" in bad["error"]
    assert long_["error_kind"] == "limit" and "characters" in long_["error"]
    assert nobody["error_kind"] == "unknown" and "two data sources, promql and sql; 'nowhere' is neither" in nobody["error"]
    assert "neither" in old["error"]                                      # a source once declared is no source now
    p.measurements.base = f"http://127.0.0.1:{free_port()}"
    [down] = ask(p, {"source": "promql", "text": "up"})
    assert down["error_kind"] == "unreachable" and "could not reach source 'promql'" in down["error"]
    assert "127.0.0.1" not in down["error"]                               # never the address


@pytest.mark.parametrize("how", ["late", "stall", "trickle"])
def test_a_source_that_is_slow_to_answer_is_cut_off_at_the_time_bound(p, monkeypatch, how):
    monkeypatch.setattr(datasources, "MOST_SECONDS", 1.0)
    t0 = time.monotonic()
    [r] = ask(p, {"source": "promql", "text": how})
    took = time.monotonic() - t0
    assert r["error_kind"] == "limit" and "source 'promql' did not answer within 1 s" in r["error"], r
    assert took < 2.5, took                                               # (the stub would go on for 30 s)


@pytest.fixture(scope="module")
def certs(tmp_path_factory):
    return tlscerts.make(tmp_path_factory.mktemp("tls"))


@pytest.fixture(scope="module")
def proms(certs):
    """The stub Prometheus over https, its certificate a test CA's (``tests/tlscerts``)."""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    tls = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    tls.load_cert_chain(certs["server"], certs["server_key"])
    srv.socket = tls.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"https://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


@pytest.mark.parametrize("how", ["stall", "trickle"])
def test_an_https_source_that_trickles_is_cut_off_at_the_time_bound(tmp_path, proms, certs, monkeypatch, how):
    monkeypatch.setattr(ssl, "_create_default_https_context", lambda: ssl.create_default_context(cafile=certs["ca"]))
    p = project(tmp_path, proms)
    [ok] = ask(p, {"source": "promql", "text": "up"})
    assert "error" not in ok and len(ok["series"]) == 2, ok              # (the certificate is trusted: TLS is spoken)
    monkeypatch.setattr(datasources, "MOST_SECONDS", 1.0)
    t0 = time.monotonic()
    [r] = ask(p, {"source": "promql", "text": how})
    took = time.monotonic() - t0
    assert r["error_kind"] == "limit" and "source 'promql' did not answer within 1 s" in r["error"], r
    assert took < 2.5, took                                               # (the stub would go on for 30 s)


def test_a_source_query_takes_only_source_and_text(p):
    [r] = ask(p, {"source": "promql", "text": "up", "agg": "sum"})
    assert "'agg' is not a key of a data source's query" in r["error"]
    [r] = ask(p, {"source": "promql", "text": "up", "vars": {"k": "a"}})
    assert "vars must be" in r["error"]
    [r] = ask(p, {"source": "items", "field": "x", "x": {"type": "bins", "query": {"source": "promql", "text": "up"}}})
    assert "cannot be an X" in r["error"]


def test_the_fields_list_exactly_the_two_sources_each_saying_whether_it_answers(p, prom, tmp_path):
    """Always both, in order, never an address: an unavailable one is listed with why and how to make it available."""
    got = api(Live(p), "query/fields", {})["datasources"]
    views = got[1].pop("views")                     # the SQL views and their columns, what its editor completes
    assert got == [{"name": "promql", "type": "promql", "language": "PromQL", "available": True},
                   {"name": "sql", "type": "sql", "language": "SQL", "available": True}]
    assert views["transitions"][:3] == ["id", "projection", "at"] and "item_list" in views
    assert prom not in json.dumps(api(Live(p), "query/fields", {}))
    p.measurements.base = f"http://127.0.0.1:{free_port()}"
    datasources._ANSWERS.clear()
    promql_, sql_ = datasources.listed(p.measurements, p)
    assert promql_["name"] == "promql" and promql_["available"] is False
    assert "no VictoriaMetrics answers at" in promql_["reason"] and "brew install victoriametrics" in promql_["reason"]
    assert sql_ == {"name": "sql", "type": "sql", "language": "SQL", "available": True}
    nowhere = datasources.listed(None, None)
    assert [x["name"] for x in nowhere] == ["promql", "sql"] and not any(x["available"] for x in nowhere)
    assert all(x["reason"] for x in nowhere)


@pytest.mark.parametrize("entry", ["record: {type: sql}", "m: {type: model}", "a: {type: analysis}",
                                   "promql: {type: prometheus, url: 'http://x'}", "q: {type: promql}"])
def test_a_dashboard_source_declared_under_sources_is_a_model_error_that_says_why(tmp_path, entry):
    (tmp_path / "ergostat.yaml").write_text(f"name: ds\nstocks:\n  queue: {{unit: tickets}}\nsources:\n  {entry}\n")
    with pytest.raises(Exception, match="exactly two, promql .* and sql") as e:
        mdl.load(tmp_path)
    assert "sources: holds only the external systems a sensor reads" in str(e.value)


def test_a_sensor_still_reads_an_external_system_under_sources_and_no_panel_asks_it(tmp_path, prom):
    p = project(tmp_path, prom, f"""
        sources:
          ext: {{type: prometheus, url: "{prom}"}}
        auxiliaries:
          load:
            sensor: {{query: {{source: ext, promql: up}}, every: 30s}}
        """)
    assert p.model.spec.sources["ext"].type == "prometheus"
    [r] = ask(p, {"source": "ext", "text": "up"})
    assert r["error_kind"] == "unknown" and "'ext' is neither" in r["error"]
    assert [x["name"] for x in api(Live(p), "query/fields", {})["datasources"]] == ["promql", "sql"]
    for ts in sorted((ROOT / "ergostat" / "web" / "ui" / "src" / "pages" / "dashboard").rglob("*.ts*")):
        text = ts.read_text().lower()                                       # nothing in the page names a type
        assert "prometheus" not in text, ts


def test_each_source_offers_query_and_reads_only():
    for name in datasources.NAMES:
        mod = datasources._module(name)
        own = {n for n, v in vars(mod).items() if not n.startswith("_") and callable(v)
               and getattr(v, "__module__", None) == mod.__name__}
        assert "query" in own and own <= {"query", "suggest", "values", "rows"}, name


PUBLIC = "dash.example.org"


def test_an_anonymous_public_reader_is_refused_a_source_and_nothing_is_sent(tmp_path, prom):
    from ergostat.web import serve
    p = project(tmp_path, prom, f"web:\n  names: [{PUBLIC}]\n  open: read\n")
    server, url = serve(p, free_port())
    try:
        body = {"since": 480.0, "until": T + 480, "points": 4,
                "queries": [{"id": "0", "source": "promql", "text": "up"}, {"id": "1", "source": "counts"}]}
        q = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")

        def get(path, host=None):
            req = urllib.request.Request(url + path, headers={"Host": host} if host else {})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        Stub.seen.clear()
        src, own = get(f"/api/query?q={q}", PUBLIC)["results"]
        assert src["error_kind"] == "refused" and "public name" in src["error"] and "series" not in src
        assert "error" not in own                                            # a built-in shortcut still answers
        assert Stub.seen == []                                               # nothing was sent to the source
        listed = get("/api/query/fields", PUBLIC)["datasources"]
        assert [x["name"] for x in listed] == ["promql", "sql"] and not any(x["available"] for x in listed)
        assert all("public name" in x["reason"] for x in listed)
        src, _ = get(f"/api/query?q={q}")["results"]                          # the owner, on this machine, as before
        assert "error" not in src and len(Stub.seen) == 1
        assert all(x["available"] for x in get("/api/query/fields")["datasources"])
    finally:
        server.shutdown()
        server.server_close()


def test_promql_is_asked_by_get_on_query_range_only(p):
    Stub.seen.clear()
    ask(p, {"source": "promql", "text": "up"}, {"source": "promql", "text": "many"}, {"source": "promql", "text": "sum(up"})
    assert len(Stub.seen) == 3 and {(m, path) for m, path, _ in Stub.seen} == {("GET", "/api/v1/query_range")}
    assert promql._PATH == "/api/v1/query_range"
