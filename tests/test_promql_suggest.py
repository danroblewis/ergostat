"""The names a PromQL editor completes (ergostat/datasources ``suggest``, ``GET /api/query/suggest``), from a stub
Prometheus's metadata API: metrics, a metric's labels and a label's values, each narrowed by what is typed; bounded on a
source of 100,000 series, even one that ignores ``limit`` and ``match[]``; and a parse error's place, as the source
said it, in the query's result (``error_at``)."""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from ergostat import datasources
from ergostat.datasources import promql
from ergostat.web.server import Live, api
from tests.test_data_sources import Stub, ask, project

SERIES = 100_000


def starts(sel: str, name: str) -> str | None:
    """The prefix ``name=~"P.*"`` asks for in a selector, its escapes undone; None if it does not ask."""
    m = re.search(name + r'=~"((?:\\.|[^"\\])*)\.\*"', sel)
    return re.sub(r"\\(.)", r"\1", json.loads(f'"{m[1]}"')) if m else None


class Meta(Stub):
    """A Prometheus with metadata: ``up`` (job: api, worker; instance) and ``http_requests_total`` (job, code), and,
    when ``big``, 100,000 series of their own metric ``m_00000`` ... with a unique ``id`` each. ``obeys``: it honours
    ``limit`` and ``match[]``, as Prometheus 2.49 and later do; one that does not sends every name. Its parse errors
    say the line and column of the first ``$``, as Prometheus says them."""
    big = False
    obeys = True
    seen: list = []

    def do_GET(self):
        u = urlparse(self.path)
        a = parse_qs(u.query)
        one = {k: v[0] for k, v in a.items()}
        type(self).seen.append(("GET", u.path, one))
        if u.path == "/api/v1/query_range" and "$" in one.get("query", ""):
            text = one["query"].encode()                  # Prometheus counts the column in bytes
            line = text[:text.index(b"$")].count(b"\n") + 1
            col = text.index(b"$") - (text.rfind(b"\n", 0, text.index(b"$")) + 1) + 1
            return self.answer(400, {"status": "error", "errorType": "bad_data",
                                     "error": f"{line}:{col}: parse error: unexpected character: '$'"})
        if u.path == "/api/v1/query_range":
            return super().do_GET()
        sel = (a.get("match[]") or [""])[0] if self.obeys else ""
        limit = int(one["limit"]) if self.obeys and "limit" in one else None
        metric = sel.split("{")[0]
        if u.path == "/api/v1/labels":
            names = (["__name__", "id"] if metric.startswith("m_") else
                     ["__name__", "code", "job"] if metric == "http_requests_total" else
                     ["__name__", "instance", "job"] if metric == "up" else ["__name__", "code", "id", "instance", "job"])
            return self.answer(200, {"status": "success", "data": names[:limit]})
        m = re.fullmatch(r"/api/v1/label/([^/]+)/values", u.path)
        if not m:
            return self.answer(404, {"status": "error", "error": "not found"})
        if m[1] == "slow":
            return self.slow("trickle")
        label, want = m[1], starts(sel, m[1]) or ""
        every = {"job": ["api", "worker"], "instance": ["host-1:9100", "host-2:9100"], "code": ["200", "500"]}.get(label, [])
        if label == "__name__":
            every = ["http_requests_total", "up"]
        if self.big and label in ("__name__", "id"):
            every = every + [f"{'m_' if label == '__name__' else ''}{i:05d}" for i in range(SERIES)]
        got = [v for v in every if v.startswith(want)]
        self.stream(got if limit is None else got[:limit])

    def stream(self, names: list) -> None:
        """A long answer, sent as it is made (a client that has read enough hangs up)."""
        body = json.dumps({"status": "success", "data": names}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            for i in range(0, len(body), 65536):
                self.wfile.write(body[i:i + 65536])
        except OSError:
            pass


def serve(cls):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


@pytest.fixture(scope="module")
def metas():
    """Three stubs: small; 100,000 series that honour limit and match[]; 100,000 series that ignore both."""
    made = [serve(type("Small", (Meta,), {"seen": []})), serve(type("Big", (Meta,), {"big": True, "seen": []})),
            serve(type("Rude", (Meta,), {"big": True, "obeys": False, "seen": []}))]
    yield {name: (url, srv.RequestHandlerClass) for name, (srv, url) in zip(("small", "big", "rude"), made, strict=True)}
    for srv, _ in made:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def p(tmp_path, metas):
    return project(tmp_path, metas["small"][0])


def suggest(p, on, what, prefix="", metric="", label="", source="promql"):
    """Names suggested by ``promql``, its VictoriaMetrics the stub ``on`` (small, big or rude)."""
    if on in METAS:
        p.measurements.base = METAS[on][0]
    q = {"source": [source], "what": [what], "prefix": [prefix], "metric": [metric], "label": [label]}
    return api(Live(p), "query/suggest", q)


METAS: dict = {}


@pytest.fixture(autouse=True)
def _metas(metas):
    METAS.update(metas)
    yield


def test_metrics_labels_and_values_are_suggested_from_the_source_narrowed_by_what_is_typed(p, metas):
    assert suggest(p, "small", "metrics") == {"suggestions": ["http_requests_total", "up"], "more": False}
    assert suggest(p, "small", "metrics", "ht")["suggestions"] == ["http_requests_total"]
    assert suggest(p, "small", "labels", metric="up")["suggestions"] == ["__name__", "instance", "job"]
    assert suggest(p, "small", "labels", "j", metric="up")["suggestions"] == ["job"]
    assert suggest(p, "small", "values", "w", metric="up", label="job")["suggestions"] == ["worker"]
    seen = metas["small"][1].seen
    assert {path for _, path, _ in seen} == {"/api/v1/label/__name__/values", "/api/v1/labels", "/api/v1/label/job/values"}
    asked = {path: a for _, path, a in seen}
    assert asked["/api/v1/label/job/values"]["match[]"] == 'up{job=~"w.*"}'        # narrowed by the source itself
    assert all(a["limit"] == str(datasources.MOST_SUGGESTIONS + 1) for _, _, a in seen)


def test_what_is_typed_is_escaped_in_the_selector_it_is_asked_with(p, metas):
    metas["small"][1].seen.clear()
    suggest(p, "small", "values", 'a.b"(c', label="job")
    [(_, _, a)] = metas["small"][1].seen
    assert starts(a["match[]"], "job") == 'a.b"(c'
    assert a["match[]"] == '{job=~"a\\\\.b\\"\\\\(c.*"}'


@pytest.mark.parametrize("source", ["big", "rude"])
def test_autocomplete_stays_bounded_on_a_source_of_100000_series(p, metas, source, monkeypatch):
    read = []
    real = promql._ask
    monkeypatch.setattr(promql, "_ask", lambda *a: read.append(len((got := real(*a))[1])) or got)
    t0 = time.monotonic()
    every = suggest(p, source, "metrics", "m_")
    some = suggest(p, source, "metrics", "m_123")
    ids = suggest(p, source, "values", "", metric="m_00001", label="id")
    took = time.monotonic() - t0
    assert len(every["suggestions"]) == datasources.MOST_SUGGESTIONS and every["more"] is True
    assert every["suggestions"][:2] == ["m_00000", "m_00001"]
    assert len(ids["suggestions"]) == datasources.MOST_SUGGESTIONS and ids["more"] is True
    assert all(n.startswith("m_123") for n in some["suggestions"]) and some["suggestions"][:1] == ["m_12300"]
    assert len(json.dumps([every, some, ids])) < 30_000                         # what reaches the page
    assert max(read) <= promql._MOST_NAME_BYTES + 1, read                   # what is read of the source
    assert took < 5, took


def test_a_source_that_answers_too_many_names_is_cut_to_the_bound_and_one_with_none_says_so(p, monkeypatch):
    every = lambda src, what, prefix, metric, label, seconds, most: ([f"n{i:05d}" for i in range(SERIES)], False)  # noqa: E731
    monkeypatch.setattr(promql, "suggest", every)
    got = suggest(p, "small", "metrics", "n0")
    assert len(got["suggestions"]) == datasources.MOST_SUGGESTIONS and got["more"] is True
    assert suggest(p, "small", "metrics", "n00001")["suggestions"] == ["n00001"]
    monkeypatch.delattr(promql, "suggest")
    assert suggest(p, "small", "metrics")["error_kind"] == "refused"


def test_a_source_that_trickles_its_names_is_cut_off_at_the_suggestion_time_bound(p, monkeypatch):
    monkeypatch.setattr(datasources, "SUGGEST_SECONDS", 1.0)
    t0 = time.monotonic()
    got = suggest(p, "small", "values", label="slow")
    took = time.monotonic() - t0
    assert got["error_kind"] == "limit" and "did not answer within 1 s" in got["error"] and got["suggestions"] == []
    assert took < 2.5, took                                                     # (the stub would go on for 30 s)


def test_a_suggestion_asks_nothing_but_a_name_and_says_why_it_is_refused(p, metas):
    metas["small"][1].seen.clear()
    bad = [suggest(p, "small", "labels", metric='up"}) or vector(1'), suggest(p, "small", "series"),
           suggest(p, "small", "values", "x"), suggest(p, "small", "metrics", source="nowhere"),
           suggest(p, "small", "metrics", "x" * 201)]
    assert [b["error_kind"] for b in bad] == ["refused", "refused", "refused", "unknown", "limit"]
    assert all(b["suggestions"] == [] for b in bad)
    assert metas["small"][1].seen == []                                         # none of them was sent


def test_a_reader_under_a_public_name_is_refused_suggestions(p, metas):
    from ergostat.web.server import _query
    metas["small"][1].seen.clear()
    got = _query(Live(p), p, ["query", "suggest"], {"source": ["promql"], "what": ["metrics"]}, reader=True)
    assert got["error_kind"] == "refused" and got["suggestions"] == [] and metas["small"][1].seen == []
    got = api(Live(p), "query/suggest", {"source": ["promql"], "what": ["metrics"]}, reader=True)
    assert got["error_kind"] == "refused" and metas["small"][1].seen == []


def test_a_parse_error_says_where_the_source_said_it_is(p):
    [one, two, old] = ask(p, {"source": "promql", "text": "sum(up) $ 2"}, {"source": "promql", "text": "sum(\n  up $ 2)"},
                          {"source": "promql", "text": "sum(up"})
    assert one["error_kind"] == "refused" and one["error_at"] == [1, 9] and "unexpected character" in one["error"]
    assert two["error_at"] == [2, 6]
    assert old["error_at"] == [1, 5]                       # (the old stub's words: "1:5: parse error: ...")
    [wide] = ask(p, {"source": "promql", "text": 'up{job="café"} $'})
    assert wide["error_at"] == [1, 17]                     # a column in bytes, as Prometheus says it: "é" is two
    assert promql._at("parse error at char 7: unexpected") == (1, 7)
    assert promql._at("bad_data: no place said") is None
