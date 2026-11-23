"""Remote systems (SPEC §4c): what a remote serves, its tokens, and a remote's model composed into a local one."""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ergostat import spec as sp
from ergostat.remote import cache, compose, readings, serve, tokens
from tests.ports import free_port

REMOTE = """
name: incidents
sources:
  prom: {type: prometheus, url: http://secret.example:9090}
systems:
  triage: {description: arriving}
  response: {description: worked}
stocks:
  open:
    unit: incidents
    system: triage
    sensor: {run: ls queue | wc -l, every: 5s}
  depth:
    system: triage
    sensor: {query: {source: prom, promql: 'sum(secret_metric)'}, every: 1m}
flows:
  opened: {to: open, system: triage}
  resolved: {from: open, system: response}
goals:
  few-open: {stock: open, hold: "<= 6", system: response}
agents:
  on-call: {kind: ai}
blocks:
  pager: {type: program, system: triage, every: 3s, run: ./secret-pager.sh, out: flow.opened}
  responder: {type: ai, system: response, goal: few-open, prompt: "secret prompt words", agent: on-call, out: flow.resolved}
"""


def write(d, text):
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(text)
    return d / "ergostat.yaml"


def test_the_served_model_is_redacted_and_versioned(tmp_path):
    path = write(tmp_path / "incidents", REMOTE)
    got = serve.model(path)
    text = json.dumps(got)
    for secret in ("secret-pager", "secret prompt", "secret_metric", "secret.example", "prom"):
        assert secret not in text
    assert got["format"] == "ergostat-model/1" and len(got["version"]) == 16
    assert got["sections"]["stocks"]["open"]["sensors"]["main"] == {"every": "5s", "kind": "run"}
    assert got["sections"]["blocks"]["responder"]["goal"] == "few-open"
    assert serve.model(path)["version"] == got["version"]                     # the same model, the same version
    write(tmp_path / "incidents", REMOTE.replace("arriving", "arriving fast"))
    assert serve.model(path)["version"] != got["version"]


def test_tokens_are_kept_as_hashes(tmp_path):
    tok = tokens.issue(tmp_path, "support")
    assert tok not in (tmp_path / tokens.FILE).read_text()
    assert tokens.who(tmp_path, tok) == "support"
    assert tokens.who(tmp_path, tok + "x") is None and tokens.who(tmp_path, None) is None
    assert tokens.revoke(tmp_path, "support") and tokens.who(tmp_path, tok) is None


def _get(url, token=None, etag=None, method="GET"):
    h = {**({"Authorization": f"Bearer {token}"} if token else {}), **({"If-None-Match": f'"{etag}"'} if etag else {})}
    req = urllib.request.Request(url, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null"), r.headers.get("ETag")
    except urllib.error.HTTPError as e:
        return e.code, None, None


def test_the_remote_api_answers_with_a_token_only_and_pages_by_cursor(tmp_path):
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web import serve as web_serve
    write(tmp_path / "incidents", REMOTE)
    p = Project(mdl.load(tmp_path / "incidents"))
    for i in range(5):
        p.events.add("incident.opened", item=f"incident/{i}", source="pager", data={})
    p.measurements.add("sensor/open.main", 4.0)
    server, url = web_serve(p, free_port())
    try:
        assert _get(f"{url}/remote/v1/status")[0] == 404                    # off until a token is made
        tok = tokens.issue(p.dir, "support")
        assert _get(f"{url}/remote/v1/status")[0] == 401
        assert _get(f"{url}/remote/v1/status", "wrong")[0] == 401
        code, st, _ = _get(f"{url}/remote/v1/status", tok)
        assert code == 200 and st["name"] == "incidents" and st["last_seq"] >= 5
        code, m, etag = _get(f"{url}/remote/v1/model", tok)
        assert code == 200 and etag == f'"{m["version"]}"'
        assert _get(f"{url}/remote/v1/model", tok, m["version"])[0] == 304   # unchanged: nothing sent
        code, page, _ = _get(f"{url}/remote/v1/events?after=0&n=2", tok)
        assert code == 200 and [e["seq"] for e in page["events"]] == [1, 2] and page["next"] == 2 and page["more"]
        code, page2, _ = _get(f"{url}/remote/v1/events?after={page['next']}&n=2", tok)
        assert [e["seq"] for e in page2["events"]] == [3, 4]
        code, r, _ = _get(f"{url}/remote/v1/readings?series=sensor/open.main&ref=stock.open,stock.nothing", tok)
        assert r["series"]["sensor/open.main"]["value"] == 4.0 and r["refs"]["stock.open"]["value"] == 4.0
        assert r["refs"]["stock.nothing"].get("missing") and r["version"] == m["version"]
        assert _get(f"{url}/remote/v1/counts", tok)[0] == 200
        assert _get(f"{url}/remote/v1/model", tok, method="POST")[0] in (403, 405)   # read only
    finally:
        server.shutdown()
        server.server_close()


def served_into(local, home_root, remote="incidents", text=REMOTE, ok=True):
    """The remote's model put in this project's cache, as a refresh would have left it (no network)."""
    d = cache.folder("support", local, remote)
    body = serve.model(write(home_root / "remote-src", text))
    (d / cache.MODEL).write_text(json.dumps({**body, "fetched": time.time()}))
    st = {"checked": time.time(), "ok": ok, "version": body["version"], "next": time.time() + 3600}
    if not ok:
        st.update(why="unreachable (refused)", failing_since=time.time() - 30, fails=1)
    (d / cache.STATUS).write_text(json.dumps(st))
    return body


LOCAL = """
name: support
remotes:
  incidents:
    url: http://127.0.0.1:1
    token-file: incidents.token
stocks:
  tickets:
    sensor: {run: echo 3}
flows:
  filed:
    to: tickets
    driven-by: [+stock.incidents-open]
goals:
  calm:
    stock: incidents-open
    hold: "<= 8"
"""


def test_a_remote_is_a_system_of_external_parts_read_from_there(tmp_path):
    local = tmp_path / "support"
    write(local, LOCAL)
    served_into(local, tmp_path)
    spec, problems = sp.read(local / "ergostat.yaml", extremes=False)
    assert not [p for p in problems if p.level == "error"], problems
    assert spec.within["incidents-triage"] == "incidents" and spec.stocks["incidents-open"].system == "incidents-triage"
    s = spec.stocks["incidents-open"].sensors["main"]
    assert s.query == {"source": "incidents", "series": "sensor/open.main"} and s.every == 60.0
    assert spec.sources["incidents"].type == "ergostat" and spec.sources["incidents"].token_file == "incidents.token"
    for b in ("incidents-pager", "incidents-responder"):
        assert spec.blocks[b].type == "external"                                  # never run here
    assert "goal.incidents-few-open.error" in [str(r) for r in spec.blocks["incidents-responder"].inputs.values()]
    assert spec.agents["incidents-on-call"].external and spec.agents["incidents-on-call"].kind == "ai"
    assert spec.flows["incidents-resolved"].sensors["remote"].query == {"source": "incidents", "ref": "flow.resolved"}
    assert "stock.incidents-depth" in spec.remotes["incidents"]["parts"]
    assert str(spec.stocks["incidents-open"].where).endswith("(remote incidents)")


def test_a_reference_the_remote_no_longer_serves_is_a_finding_not_a_crash(tmp_path):
    local = tmp_path / "support"
    write(local, LOCAL.replace("stock: incidents-open", "stock: incidents-waiting"))
    served_into(local, tmp_path)
    spec, problems = sp.read(local / "ergostat.yaml", extremes=False)
    assert not [p for p in problems if p.level == "error"], problems
    found = [p for p in problems if p.code == "remote-reference-unresolved"]
    assert found and "incidents-waiting" in found[0].message and "has no stock waiting" in found[0].message
    assert "incidents-waiting" in spec.stocks and not spec.stocks["incidents-waiting"].sensors
    assert spec.remotes["incidents"]["missing"][0]["name"] == "incidents-waiting"


def test_a_local_block_may_read_a_remote_part_but_never_act_on_it(tmp_path):
    local = tmp_path / "support"
    write(local, LOCAL + """
blocks:
  meddler:
    type: program
    in: stock.incidents-open
    run: echo 1
    out: flow.incidents-resolved
""")
    served_into(local, tmp_path)
    _, problems = sp.read(local / "ergostat.yaml", extremes=False)
    assert [p for p in problems if p.code == "remote-output" and p.level == "error"]


def test_systems_narrows_what_is_brought_in(tmp_path):
    local = tmp_path / "support"
    write(local, LOCAL.replace("    token-file: incidents.token\n", "    token-file: incidents.token\n    systems: [triage]\n"))
    served_into(local, tmp_path)
    spec, problems = sp.read(local / "ergostat.yaml", extremes=False)
    assert not [p for p in problems if p.level == "error"], problems
    assert "incidents-open" in spec.stocks and "incidents-resolved" not in spec.flows
    assert "incidents-few-open" not in spec.goals and "incidents-response" not in spec.systems


def test_an_unreachable_remote_is_drawn_from_its_cache_with_a_finding(tmp_path):
    local = tmp_path / "support"
    write(local, LOCAL)
    served_into(local, tmp_path, ok=False)
    spec, problems = sp.read(local / "ergostat.yaml", extremes=False)
    assert "incidents-open" in spec.stocks
    assert [p for p in problems if p.code == "remote-unreachable" and "did not answer" in p.message]


def _plant(local, **reads):
    """The remote's status as readings would leave it (``cache.note``), on top of what the model fetch wrote."""
    d = cache.folder("support", local, "incidents")
    st = {k: v for k, v in cache.status(d).items() if not k.startswith("read")}
    (d / cache.STATUS).write_text(json.dumps({**st, **reads}))


def _checked(local, monkeypatch):
    """The model read as ``ergostat check`` reads it (``fresh()``), the remote's model answering unchanged."""
    monkeypatch.setattr(cache, "refresh", lambda d, *a, **k: cache.status(d))
    with compose.fresh():
        _, problems = sp.read(local / "ergostat.yaml", extremes=False)
    return problems


def test_remote_stale_finding(tmp_path, monkeypatch):
    local = tmp_path / "support"
    write(local, LOCAL)
    served_into(local, tmp_path)
    now = time.time()
    _plant(local, read=now - 600, read_ok=False, read_why="unreachable (timed out)", read_failing_since=now - 300)
    problems = _checked(local, monkeypatch)
    stale = [p for p in problems if p.code == "remote-stale"]
    assert len(stale) == 1 and stale[0].about == "system.incidents" and stale[0].level == "finding"
    assert stale[0].message == ("remote incidents: its readings fail (unreachable (timed out)) since 5m ago; "
                                "its measures here are 10m old"), stale[0].message
    assert not [p for p in problems if p.code == "remote-unreachable"]
    _plant(local, answered=now - 60, read_ok=False, read_why="refused", read_failing_since=now - 300)   # never read
    stale = [p for p in _checked(local, monkeypatch) if p.code == "remote-stale"]
    assert len(stale) == 1 and stale[0].message.endswith("; none of its measures has been read here"), stale
    _plant(local, read=now, read_ok=True)
    assert not [p for p in _checked(local, monkeypatch) if p.code == "remote-stale"]
    _plant(local)                                                      # never read: nothing to say of its readings
    assert not [p for p in _checked(local, monkeypatch) if p.code == "remote-stale"]


def test_unreachable_wins_over_stale(tmp_path, monkeypatch):
    local = tmp_path / "support"
    write(local, LOCAL)
    served_into(local, tmp_path, ok=False)
    _plant(local, read_ok=False, read_why="unreachable (refused)", read_failing_since=time.time() - 30)
    problems = _checked(local, monkeypatch)
    assert [p.code for p in problems if p.code in ("remote-unreachable", "remote-stale")] == ["remote-unreachable"]


def test_a_remote_never_read_still_loads(tmp_path, monkeypatch):
    local = tmp_path / "support"
    write(local, LOCAL)
    monkeypatch.setattr(compose, "EVERY", 60.0)
    spec, problems = sp.read(local / "ergostat.yaml", extremes=False)      # 127.0.0.1:1 answers nothing
    assert not [p for p in problems if p.level == "error"], problems
    assert "incidents" in spec.systems and [p for p in problems if p.code == "remote-unreachable"]
    assert [p for p in problems if p.code == "remote-reference-unresolved"]


def test_plain_http_to_another_machine_is_refused(tmp_path):
    local = tmp_path / "support"
    write(local, LOCAL.replace("http://127.0.0.1:1", "http://incidents.example:8781"))
    _, problems = sp.read(local / "ergostat.yaml", extremes=False)
    assert [p for p in problems if p.code == "remote-insecure"]


class _Src:
    name, url, token_file = "incidents", "http://127.0.0.1:1", ""


class _S:
    def __init__(self, q, every=10.0):
        self.query, self.every = q, every


def test_a_stale_or_missing_remote_reading_is_not_taken(tmp_path, monkeypatch):
    local = tmp_path / "support"
    write(local, LOCAL)
    served_into(local, tmp_path)
    (local / "incidents.token").write_text("tok")
    spec, _ = sp.read(local / "ergostat.yaml", extremes=False)
    now = time.time()
    asked = []

    def fake(url, path, token, params=None, etag=None, timeout=5.0, tls=None):
        asked.append(params)
        return 200, {"now": now, "version": spec.remotes["incidents"]["version"],
                     "series": {"sensor/open.main": {"value": 4, "time": now - 3600}},
                     "refs": {"flow.resolved": {"value": 2.5, "time": now}}}, None, ""
    monkeypatch.setattr(readings.client, "get", fake)
    readings._kept.clear()
    src = spec.sources["incidents"]
    v, why = readings.read(spec, src, _S({"source": "incidents", "series": "sensor/open.main"}))
    assert v is None and "old" in why
    v, why = readings.read(spec, src, _S({"source": "incidents", "ref": "flow.resolved"}))
    assert v == 2.5 and not why
    assert len(asked) == 1                                       # one request for every sensor of the remote
    monkeypatch.setattr(readings.client, "get", lambda *a, **k: (0, None, None, "unreachable (refused)"))
    readings._kept.clear()
    v, why = readings.read(spec, src, _S({"source": "incidents", "ref": "flow.resolved"}))
    assert v is None and "unreachable" in why


def test_a_remote_part_is_never_edited_here(tmp_path):
    from ergostat.numbers import yamledit
    via = compose.RemoteVia(tmp_path / "ergostat.yaml", 3, "incidents", "http://127.0.0.1:8794")
    with pytest.raises(yamledit.EditError, match="belongs to remote incidents"):
        yamledit.own(via, "flow incidents-resolved")


def test_explain_marks_remote_part(tmp_path):
    from ergostat.spec.explain import explain
    local = tmp_path / "support"
    write(local, LOCAL)
    body = served_into(local, tmp_path)
    st = cache.folder("support", local, "incidents") / cache.STATUS
    st.write_text(json.dumps({**json.loads(st.read_text()), "answered": time.time() - 120}))
    spec, _ = sp.read(local / "ergostat.yaml", extremes=False)
    v = body["version"][:7]
    said = f"remote incidents's (runs at http://127.0.0.1:1, model v{v}, read 2m ago)"
    assert explain(spec, "stock.incidents-open").startswith(f"{said} stock incidents-open (incidents).")
    block = explain(spec, "block.incidents-pager")
    assert block.startswith(f"{said} block incidents-pager:") and "It is never run here: remote incidents runs it." in block
    system = explain(spec, "system.incidents")
    assert system.count("remote incidents's") == 1 and f"It is {said}: its parts are read here" in system
    assert system.startswith("System incidents") and "  Holds " in system and "stock.incidents-open → flow.filed" in system
    goal = explain(spec, "goal.calm")                       # a local goal on a remote's measure
    assert "Its loop reads a remote's parts (crosses remote incidents: stock.incidents-open, flow.incidents-" in goal
    assert "never an actuator" in goal and not goal.startswith("remote")
    assert "remote" not in explain(spec, "stock.tickets")
    served_into(local, tmp_path, ok=False)
    spec, _ = sp.read(local / "ergostat.yaml", extremes=False)
    assert explain(spec, "stock.incidents-open").startswith(
        f"remote incidents's (runs at http://127.0.0.1:1, model v{v}, not answering for 30s · never read)")


def test_explain_loop_crossing_remote(tmp_path):
    from ergostat.spec.explain import explain
    local = tmp_path / "support"
    write(local, LOCAL.replace("goals:\n  calm:\n    stock: incidents-open\n    hold: \"<= 8\"\n", """
  escalated: {from: tickets, to: incidents-open}
goals:
  few-tickets: {stock: tickets, hold: "<= 4"}
blocks:
  escalator: {type: program, goal: few-tickets, run: echo 1, out: flow.escalated}
"""))
    served_into(local, tmp_path)
    spec, problems = sp.read(local / "ergostat.yaml", extremes=False)
    assert not [p for p in problems if p.level == "error"], problems
    lines = [x for x in explain(spec).splitlines() if "flow.escalated → stock.incidents-open → flow.filed" in x]
    assert lines and lines[0].endswith(" (crosses remote incidents: stock.incidents-open)"), lines
    goal = explain(spec, "goal.few-tickets")
    assert "crosses remote incidents: stock.incidents-open" in goal and "never an actuator" in goal


GOLDEN = Path(__file__).parent / "golden" / "explain-alert-triage.txt"


def _every_explanation(spec):
    from ergostat.spec.explain import explain
    out = [explain(spec)]
    for kind, table in (("goal", spec.goals), ("block", spec.blocks), ("stock", spec.stocks), ("flow", spec.flows),
                        ("auxiliary", spec.auxiliaries), ("system", spec.systems)):
        out += [explain(spec, f"{kind}.{n}") for n in sorted(table)]
    # this host's interpreter and checkout paths (library/expand.py PY, library/templates.py HERE) become placeholders
    from ergostat.library.expand import PY
    from ergostat.library.templates import HERE
    return _own_text("\n\n".join(out).replace(PY, "<python>").replace(str(HERE), "<templates>")) + "\n"


def _own_text(text):
    # explain's own words only: the Items line keeps the model's own kinds (ergostat's built-in kinds and their
    # states come from spec/ir.py, which main changes on its own), and the Modes sections go (eigenvalue and
    # elasticity numbers whose signs, ties and order can differ with a host's maths library)
    out, cut = [], None
    for line in text.split("\n"):
        depth = len(line) - len(line.lstrip(" "))
        if cut is not None and line.strip() and depth > cut:
            continue
        cut = None
        if line.lstrip(" ").startswith("Modes"):
            cut = depth
            continue
        if line.startswith("Items: "):
            own = [k for k in line[len("Items: "):].rstrip(".").split("; ") if not k.startswith("ergostat.")]
            line = "Items: " + "; ".join(own) + "."
        out.append(line)
    return "\n".join(out)


def _alert_triage_without_uses(tmp_path):
    # the example's own parts only: its `uses:` system is library template text, which main rewords on its own
    import shutil
    shutil.copytree(Path(__file__).parent.parent / "examples/alert-triage", tmp_path / "alert-triage")
    path = tmp_path / "alert-triage/ergostat.yaml"
    text = path.read_text()
    assert "\nuses:\n" in text
    path.write_text(text[:text.index("\nuses:\n") + 1])
    return sp.load(path)


def test_explain_without_remotes_unchanged(tmp_path):
    spec = _alert_triage_without_uses(tmp_path)
    assert not spec.remotes and not any("modelling" in n for n in spec.systems)
    assert _every_explanation(spec) == GOLDEN.read_text()     # written from main's explain, before this gap
