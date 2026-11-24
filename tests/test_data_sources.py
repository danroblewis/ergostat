"""Dashboard data sources (ergostat/datasources): a panel query in a source's own language, answered through the server
against a stub Prometheus; a fake type added by registering one module; the bounds, an unreachable source and a bad
query each refused in words; and no request but a read."""

from __future__ import annotations

import base64
import json
import ssl
import textwrap
import threading
import time
import types
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from ergostat import datasources
from ergostat import model as mdl
from ergostat.datasources import prometheus
from ergostat.store import Project
from ergostat.web.server import Live, api
from tests import tlscerts
from tests.ports import free_port

T = 1_795_400_400.0         # a multiple of 120
OWN = {"name": "model", "type": "model", "language": "model"}     # the model's own source, there undeclared
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


def test_the_most_points_and_the_longest_window_are_answered(p):
    [r] = ask(p, {"source": "prom", "text": "up"}, since=400 * 86400.0, until=T + 7, points=1000)
    assert "error" not in r, r
    assert len(r["times"]) == 1001 and all(len(s["values"]) == 1001 for s in r["series"])


def test_a_window_past_the_points_bound_is_refused_in_words(p, monkeypatch):
    monkeypatch.setattr(datasources, "MOST_POINTS", 3)
    [r] = ask(p, {"source": "prom", "text": "up"}, until=T + 7)
    assert r["error_kind"] == "limit" and "points, more than the 3 allowed" in r["error"]


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


@pytest.mark.parametrize("how", ["late", "stall", "trickle"])
def test_a_source_that_is_slow_to_answer_is_cut_off_at_the_time_bound(p, monkeypatch, how):
    monkeypatch.setattr(datasources, "MOST_SECONDS", 1.0)
    t0 = time.monotonic()
    [r] = ask(p, {"source": "prom", "text": how})
    took = time.monotonic() - t0
    assert r["error_kind"] == "limit" and "source 'prom' did not answer within 1 s" in r["error"], r
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
    p = project(tmp_path, f'proms: {{type: prometheus, url: "{proms}"}}')
    [ok] = ask(p, {"source": "proms", "text": "up"})
    assert "error" not in ok and len(ok["series"]) == 2, ok              # (the certificate is trusted: TLS is spoken)
    monkeypatch.setattr(datasources, "MOST_SECONDS", 1.0)
    t0 = time.monotonic()
    [r] = ask(p, {"source": "proms", "text": how})
    took = time.monotonic() - t0
    assert r["error_kind"] == "limit" and "source 'proms' did not answer within 1 s" in r["error"], r
    assert took < 2.5, took                                               # (the stub would go on for 30 s)


def test_a_source_query_takes_only_source_and_text(p):
    [r] = ask(p, {"source": "prom", "text": "up", "agg": "sum"})
    assert "'agg' is not a key of a data source's query" in r["error"]
    [r] = ask(p, {"source": "prom", "text": "up", "vars": {"k": "a"}})
    assert "vars must be" in r["error"]
    [r] = ask(p, {"source": "items", "field": "x", "x": {"type": "bins", "query": {"source": "prom", "text": "up"}}})
    assert "cannot be an X" in r["error"]


def test_the_fields_list_a_source_by_name_type_and_language_never_its_address(p, prom):
    got = api(Live(p), "query/fields", {})["datasources"]
    assert got == [datasources.ANALYSIS, {"name": "prom", "type": "prometheus", "language": "PromQL"},
                   {"name": "down", "type": "prometheus", "language": "PromQL"}, OWN]
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
    assert api(Live(p), "query/fields", {})["datasources"] == [datasources.ANALYSIS,
                                                               {"name": "f", "type": "fake", "language": "FakeQL"}, OWN]
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
    for name, mod in datasources.types().items():    # every type there is: only query (with suggest and values) offered
        own = {n for n, v in vars(mod).items() if not n.startswith("_") and callable(v)
               and getattr(v, "__module__", None) == mod.__name__}
        assert "query" in own and own <= {"query", "suggest", "values"}, name


PUBLIC = "dash.example.org"


def test_an_anonymous_public_reader_is_refused_a_source_and_nothing_is_sent(tmp_path, prom):
    from ergostat.web import serve
    (tmp_path / "ergostat.yaml").write_text(f"name: ds\nstocks:\n  queue: {{unit: tickets}}\nsources:\n"
                                            f"  prom: {{type: prometheus, url: \"{prom}\"}}\n"
                                            f"web:\n  names: [{PUBLIC}]\n  open: read\n")
    server, url = serve(Project(mdl.load(tmp_path)), free_port())
    try:
        body = {"since": 480.0, "until": T + 480, "points": 4,
                "queries": [{"id": "0", "source": "prom", "text": "up"}, {"id": "1", "source": "counts"}]}
        q = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")

        def get(path, host=None):
            req = urllib.request.Request(url + path, headers={"Host": host} if host else {})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        Stub.seen.clear()
        src, own = get(f"/api/query?q={q}", PUBLIC)["results"]
        assert src["error_kind"] == "refused" and "public name" in src["error"] and "series" not in src
        assert "error" not in own                                            # the model's own data is still read
        assert Stub.seen == []                                               # nothing was sent to the source
        assert get("/api/query/fields", PUBLIC)["datasources"] == [datasources.ANALYSIS, OWN]  # nothing reading outside
        body["queries"].append({"id": "r", "source": "analysis", "text": "raw(0)"})    # an analysis of it: refused too
        q2 = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
        *_, ana = get(f"/api/query?q={q2}", PUBLIC)["results"]
        assert ana["error_kind"] == "refused" and Stub.seen == []                      # and still nothing sent
        src, _ = get(f"/api/query?q={q}")["results"]                          # the owner, on this machine, as before
        assert "error" not in src and len(Stub.seen) == 1
        assert get("/api/query/fields")["datasources"] == [datasources.ANALYSIS,
                                                           {"name": "prom", "type": "prometheus", "language": "PromQL"}, OWN]
    finally:
        server.shutdown()
        server.server_close()


def test_prometheus_is_asked_by_get_on_query_range_only(p):
    Stub.seen.clear()
    ask(p, {"source": "prom", "text": "up"}, {"source": "prom", "text": "many"}, {"source": "prom", "text": "sum(up"})
    assert len(Stub.seen) == 3 and {(m, path) for m, path, _ in Stub.seen} == {("GET", "/api/v1/query_range")}
    assert prometheus._PATH == "/api/v1/query_range"
