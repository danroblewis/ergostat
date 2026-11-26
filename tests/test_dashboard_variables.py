"""Acceptance (dashboard-variables, done 2 and the server half of done 1 and 3): a dashboard variable's values are
written into a query's text by its language's rules, so no value can change what the query means; a variable from a
query (``label_values``) is listed from the source; a language with no rules refuses every variable."""

from __future__ import annotations

import base64
import json
import re
import textwrap
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from ergostat import datasources
from ergostat import model as mdl
from ergostat.datasources._interpolate import interpolate, uses
from ergostat.store import Project
from ergostat.web.server import Live, api

T = 1_795_400_400.0

HOSTILE = ['a"} or vector(1) #', "x'", ".*", "a|b", "\\", '\\"', "a\n}", "$other", "`", "(?i)A", "]", "é ü", "",
           "a\\.b", "}[5m]) or up{x=\""]


def lex(text: str, quotes: str = "\"'`", comment: str | None = "#"):
    """A text as a language reads it: what lies outside its string literals (literals as ``S``), and each literal's
    decoded content. Two texts mean the same thing when what lies outside is the same."""
    out, lits, i = [], [], 0
    while i < len(text):
        c = text[i]
        if comment and c == comment:
            j = text.find("\n", i)
            i = len(text) if j < 0 else j
            continue
        if c in quotes:
            j, body = i + 1, []
            while text[j] != c:
                if text[j] == "\\" and c != "`":
                    nxt = text[j + 1]
                    if nxt == "u":
                        body.append(chr(int(text[j + 2:j + 6], 16)))
                        j += 6
                        continue
                    body.append(nxt)
                    j += 2
                    continue
                body.append(text[j])
                j += 1
            lits.append("".join(body))
            out.append("S")
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out), lits


def expand(template: str, groups: dict) -> str:
    """A label_replace replacement as Prometheus writes it (Go's regexp Expand): ``$$`` is ``$``, ``$name`` and
    ``${name}`` are the group's text (empty when there is no such group), and any other ``$`` is itself."""
    out, i = [], 0
    while i < len(template):
        if template[i] != "$":
            out.append(template[i])
            i += 1
            continue
        if template[i + 1:i + 2] == "$":
            out.append("$")
            i += 2
            continue
        m = re.match(r"\{(\w+)\}|(\w+)", template[i + 1:])
        if not m:
            out.append("$")
            i += 1
            continue
        out.append(groups.get(m.group(1) or m.group(2), ""))
        i += 1 + m.end()
    return "".join(out)


@pytest.mark.parametrize("value", HOSTILE)
def test_a_value_with_quotes_or_regex_characters_cannot_change_a_querys_meaning(value):
    """Done 2: each hostile value, in each place a value may go, leaves the query's shape as it was, and is read back
    as exactly itself (an equality's string, or label_replace's replacement once Prometheus expands its ``$``) or as
    matching exactly itself (a regex's, label_replace's regex among them)."""
    g = {"kind": [value], "other": ["zzz"]}
    for template, quotes, comment, lang in [
            ('sum(rate(ergostat_items{kind="$kind", state="review"}[5m]))', "\"'`", "#", "PromQL"),
            ("up{kind='${kind}'} # $kind", "\"'`", "#", "PromQL"),
            ('label_replace(up, "dst", "$kind", "src", "(.*)")', "\"'`", "#", "PromQL")]:
        got = interpolate(lang, template, g)
        shape, lits = lex(got, quotes, comment)
        want_shape, want_lits = lex(template, quotes, comment)
        assert shape == want_shape, (template, value, got)
        if template.startswith("label_replace"):
            lits[1] = expand(lits[1], {"1": "SRC", "0": "SRC", "other": "SRC"})
        assert lits == [x.replace("${kind}", value).replace("$kind", value) for x in want_lits], (template, got)
    for template in ('up{kind=~"$kind"}', "up{kind!~'$kind'}", "up{kind=~`$kind`}",
                     'label_replace(up, "d", "x", "s", "$kind")', "label_replace(sum by (a, b) (up), 'd', 'x', 's', '${kind}')",
                     "label_replace(up{c='1', e=\"2\"}, 'd', 'x', 's', '${kind}')"):
        if "`" in value and "`" in template:
            continue                                          # (refused: the next test)
        got = interpolate("PromQL", template, {"kind": [value, "b.c"]})
        shape, lits = lex(got)
        pattern = lits[-1]
        assert shape == lex(template)[0], got
        for s in (value, "b.c"):
            assert re.fullmatch(pattern, s), (pattern, s)
        for s in (value + "x", "bxc", "x" + value, "a"):
            if s not in (value, "b.c"):
                assert not re.fullmatch(pattern, s), (pattern, s)


def test_a_value_that_cannot_go_where_it_is_used_is_refused():
    refused = [("sum by ($l) (up)", ["a) or (b"]), ("sum by ($l) (up)", ["or"]), ("up offset $l", ["5m or up"]),
               ('up{k="$l"}', ["a", "b"]), ('up{k="$l"}', []), ("up{k=`$l`}", ["a`b"]), ("up{k=~`$l`}", ["`"]),
               ('label_replace(up, "d", "$l", "s", "(.*)")', ["a", "b"])]
    for text, values in refused:
        with pytest.raises(datasources.SourceError) as e:
            interpolate("PromQL", text, {"l": values})
        assert e.value.kind == "refused", text
    assert interpolate("PromQL", "sum by ($l) (up[$w]) offset ${w}", {"l": ["job"], "w": ["5m"]}) == \
        "sum by (job) (up[5m]) offset 5m"
    assert interpolate("PromQL", 'up{k="$nope"} # $l', {"l": ["x)"]}) == 'up{k="$nope"} # $l'   # unknown, a comment
    assert uses('up{a="$a", b="${b}"} $c_d $1') == {"a", "b", "c_d"}
    lr = 'label_replace(up, "$l", "$l-$1", "s", "$l(.*)") + label_join(up, "d", "$l", "s")'
    assert interpolate("PromQL", lr, {"l": ["a.$b"]}) == \
        'label_replace(up, "a.$b", "a.$$b-$1", "s", "a\\\\.\\\\$b(.*)") + label_join(up, "d", "a.$b", "s")'


def test_a_language_with_no_rules_refuses_every_variable():
    with pytest.raises(datasources.SourceError, match="no rules"):
        interpolate("SQL", "select * from items where kind = '$k'", {"k": ["x"]})
    assert interpolate("SQL", "select 1", {"k": ["x"]}) == "select 1"          # a text naming none is untouched


class Stub(BaseHTTPRequestHandler):
    """A Prometheus that answers a range query with one series named by its text, and the ``kind`` label's values."""
    seen: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        a = {k: v[0] for k, v in parse_qs(u.query).items()}
        type(self).seen.append((u.path, a))
        if u.path == "/health":
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")
            return
        if u.path == "/api/v1/query_range":
            data = {"resultType": "matrix", "result": [{"metric": {"q": a["query"]}, "values": [[float(a["start"]), "1"]]}]}
        elif u.path == "/api/v1/label/kind/values":
            data = ["a", 'b"c', "ticket"] if a.get("match[]") != "none" else [f"v{i}" for i in range(201)]
        else:
            data = None
        body = json.dumps({"status": "success", "data": data}).encode()
        self.send_response(200 if data is not None else 404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def prom():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def p(tmp_path, prom):
    """A project whose readings are on a stub VictoriaMetrics: what ``promql`` asks."""
    (tmp_path / "ergostat.yaml").write_text("name: dv\nstocks:\n  queue: {unit: tickets}\n")
    got = Project(mdl.load(tmp_path))
    got.measurements.base = prom
    return got


def enc(body: dict) -> list:
    return [base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")]


def test_the_source_is_sent_the_text_with_its_variables_written_in_safely(p):
    Stub.seen.clear()
    queries = [{"id": "a", "source": "promql", "text": 'sum(up{kind=~"$kind"})', "vars": {"kind": ['b"c', "a.b"]}},
               {"id": "b", "source": "promql", "text": "sum by ($l) (up)", "vars": {"l": ["x) or vector(1"]}},
               {"id": "c", "source": "sql", "text": "select count(*) as n from transitions where kind = '$kind'",
                "vars": {"kind": ["a"]}}]
    got = api(Live(p), "query", {"q": enc({"since": 480, "until": T + 480, "points": 4, "queries": queries})})["results"]
    assert [q for path, a in Stub.seen for q in [a["query"]]] == ['sum(up{kind=~"(?:b\\"c|a\\\\.b)"})']
    assert "error" not in got[0], got[0]
    assert got[1]["error_kind"] == "refused" and "only go inside quotes" in got[1]["error"]
    assert got[2]["error_kind"] == "refused" and "no rules" in got[2]["error"]


def test_a_variable_from_a_query_lists_its_labels_values_from_the_source(p):
    Stub.seen.clear()
    ask = lambda **b: api(Live(p), "query/values", {"q": enc({"source": "promql", "since": 3600, "until": T, **b})})  # noqa: E731
    assert ask(text='label_values(ergostat_items{state="$s"}, kind)', vars={"s": ['re"view']}) == \
        {"values": ["a", 'b"c', "ticket"]}
    [(path, a)] = Stub.seen
    assert path == "/api/v1/label/kind/values" and a["match[]"] == 'ergostat_items{state="re\\"view"}'
    assert (float(a["start"]), float(a["end"])) == (T - 3600, T)
    assert ask(text="label_values(kind)") == {"values": ["a", 'b"c', "ticket"]}
    over = ask(text="label_values(none, kind)")
    assert over["error_kind"] == "limit" and "201 values" in over["error"]
    bad = ask(text="sum(up)")
    assert bad["error_kind"] == "refused" and "label_values" in bad["error"]
    fake = api(Live(p), "query/values", {"q": enc({"source": "sql", "text": "label_values(kind)"})})
    assert fake["error_kind"] == "refused" and "cannot list" in fake["error"]
    Stub.seen.clear()
    from ergostat.web.server import _query
    refused = _query(Live(p), p, ["query", "values"], {"q": enc({"source": "promql", "text": "label_values(kind)"})}, True)
    assert refused["error_kind"] == "refused" and Stub.seen == []                # a reader: nothing is sent
