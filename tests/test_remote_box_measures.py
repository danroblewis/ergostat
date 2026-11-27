"""A remote's closed box (SPEC §4c): the measures it shows, in the remote's own names, and each marked stale when the
remote or the reading is not current (ergostat/remote/measures.py)."""

import json
import time
import urllib.request

from ergostat import model as mdl
from ergostat import spec as sp
from ergostat.remote import cache, measures
from ergostat.store import Project
from ergostat.web import serve as web_serve
from tests.ports import free_port
from tests.test_remote import served_into, write

REMOTE = """
name: incidents
systems:
  triage: {description: arriving, show: [stock.open, stock.backlog]}
  triage-intake: {description: arriving first, within: triage, show: [stock.depth]}
  response: {description: worked, show: [flow.resolved, stock.open]}
stocks:
  open:
    unit: incidents
    system: triage
    sensor: {run: ls queue | wc -l, every: 5s}
  backlog: {system: triage, description: no sensor}
  depth:
    system: triage-intake
    sensor: {run: echo 1, every: 1m}
flows:
  opened: {to: open, system: triage}
  resolved:
    from: open
    system: response
    sensor: {run: echo 1, every: 30s}
goals:
  few-open: {stock: open, hold: "<= 6", system: response}
"""

NO_SHOW = REMOTE.replace(", show: [stock.open, stock.backlog]", "").replace(", show: [stock.depth]", "") \
    .replace(", show: [flow.resolved, stock.open]", "")

LOCAL = """
name: support
systems:
  incidents:
    remote:
      url: http://127.0.0.1:1
      token-file: incidents.token
{extra}
stocks:
  tickets:
    sensor: {{run: echo 3}}
{stocks}
flows:
  filed: {{to: tickets}}
{blocks}
"""

STAND_IN = """
blocks:
  watcher:
    type: program
    in: goal.incidents-gone-goal.error
    run: echo 1
    out: flow.filed
"""

READER = """
blocks:
  reader: {type: program, in: stock.incidents-open, run: echo 1, out: flow.filed}
"""


def local_model(tmp_path, extra="", stocks="", blocks=""):
    local = tmp_path / "support"
    write(local, LOCAL.format(extra=extra, stocks=stocks, blocks=blocks))
    return local


def status(local, **kw):
    """The remote's status.json, as a refresh or a reading would leave it."""
    d = cache.folder("support", local, "incidents")
    st = {**cache.status(d), **kw}
    (d / cache.STATUS).write_text(json.dumps(st))


def graph(local, query="", reading=None):
    """The page's /graph answer; ``reading``: (series, value, age in s) recorded first."""
    p = Project(mdl.load(local))
    for series, value, age in reading or []:
        p.measurements.add(series, value, at=time.time() - age)
    server, url = web_serve(p, free_port())
    try:
        with urllib.request.urlopen(f"{url}/api/graph{query}", timeout=30) as r:
            return json.loads(r.read())
    finally:
        server.shutdown()
        server.server_close()


def box(g, name="incidents"):
    n = next(x for x in g["nodes"] if x.get("kind") == "system" and x["label"] == name)
    return n.get("charted") if g.get("kind") == "dynamics" else n["measures"]


def by_part(g, name="incidents"):
    return {m["part"]: m for m in box(g, name)}


def problems_of(local):
    spec, problems = sp.read(local / "ergostat.yaml", extremes=False)
    return spec, problems


def test_a_remote_box_shows_its_top_systems_show_in_served_order_once(tmp_path):
    local = local_model(tmp_path)
    served_into(local, tmp_path, text=REMOTE)
    spec, problems = problems_of(local)
    assert not [p for p in problems if p.level == "error"], problems
    want = ["stock:incidents-open", "stock:incidents-backlog", "flow:incidents-resolved"]
    assert measures.refs(spec, "incidents") == want                      # not depth (nested), open once, served order
    assert measures.refs(spec, "incidents-triage-intake") == ["stock:incidents-depth"]
    for q in ("", "?view=dynamics"):
        assert [m["part"] for m in box(graph(local, q))] == want, q
    g = graph(local, "?open=incidents,incidents-triage")
    assert [m["part"] for m in box(g, "incidents-triage-intake")] == ["stock:incidents-depth"]


def test_with_no_show_a_remote_box_shows_only_goals_the_remote_serves(tmp_path):
    local = local_model(tmp_path, blocks=STAND_IN)
    served_into(local, tmp_path, text=NO_SHOW)
    spec, problems = problems_of(local)
    assert "incidents-gone-goal" in spec.goals                           # the stand-in is there
    for q in ("", "?view=dynamics"):
        parts = [m["part"] for m in box(graph(local, q))]
        assert parts == ["stock:incidents-open"], (q, parts)


def test_a_local_show_names_the_remotes_own_parts_never_local_ones(tmp_path):
    local = local_model(tmp_path, extra="    show: [stock.open, stock.incidents-open]", stocks="  open: {}")
    served_into(local, tmp_path, text=REMOTE)
    spec, problems = problems_of(local)
    assert not [p for p in problems if p.level == "error"], problems
    assert "open" in spec.stocks                                         # the local one, never shown there
    assert measures.refs(spec, "incidents") == ["stock:incidents-open", "stock:incidents-incidents-open"]
    found = [p for p in problems if p.code == "remote-show-unresolved"]
    assert len(found) == 1 and "stock.incidents-open" in found[0].message
    assert "names in show: are the remote's own: stock.open" in found[0].message
    got = box(graph(local))
    assert [m["part"] for m in got] == ["stock:incidents-open", "stock:incidents-incidents-open"]   # no backlog
    assert not got[0].get("missing") and got[1]["missing"] and got[1]["value"] == "not served"


def test_an_unresolved_show_reference_says_what_it_was_checked_against(tmp_path):
    local = local_model(tmp_path, extra="    show: [stock.waiting]")
    body = served_into(local, tmp_path, text=REMOTE)
    spec, problems = problems_of(local)
    assert not [p for p in problems if p.level == "error"], problems
    found = [p for p in problems if p.code == "remote-show-unresolved"]
    assert len(found) == 1 and found[0].level == "finding"
    f = found[0]
    assert body["version"][:7] in f.message and "serves no stock waiting" in f.message
    assert "no longer" not in f.message and "went missing" not in f.message
    assert f.about == "system.incidents"
    lines = (local / "ergostat.yaml").read_text().splitlines()
    assert f.where.line == 1 + next(i for i, x in enumerate(lines) if x.strip().startswith("show:"))
    m = by_part(graph(local))["stock:incidents-waiting"]
    assert m["missing"] and m["stale"] and m["value"] == "not served"

    local = local_model(tmp_path, extra="      systems: [triage]\n    show: [flow.resolved]")
    _, problems = problems_of(local)
    found = [p for p in problems if p.code == "remote-show-unresolved"]
    assert found and "left out by systems: [triage]" in found[0].message, problems

    for bad in ("    show: [queue.x]", "    show: open"):
        local = local_model(tmp_path, extra=bad)
        _, problems = problems_of(local)
        assert [p for p in problems if p.code == "bad-remote" and p.level == "error"], (bad, problems)


def test_a_shown_part_the_remote_stops_serving_is_a_finding_at_the_next_load(tmp_path):
    local = local_model(tmp_path, extra="    show: [stock.backlog]")
    v1 = served_into(local, tmp_path, text=REMOTE)
    spec, problems = problems_of(local)
    assert not [p for p in problems if p.code == "remote-show-unresolved"]
    assert spec.remotes["incidents"]["show"] == [{"part": "stock:incidents-backlog", "missing": False}]
    v2 = served_into(local, tmp_path, text=REMOTE.replace("  backlog: {system: triage, description: no sensor}\n", "")
                     .replace("[stock.open, stock.backlog]", "[stock.open]"))
    assert v1["version"][:7] != v2["version"][:7]
    spec, problems = problems_of(local)                                  # the next load
    found = [p for p in problems if p.code == "remote-show-unresolved"]
    assert len(found) == 1 and v2["version"][:7] in found[0].message and v1["version"][:7] not in found[0].message
    assert "incidents-backlog" not in spec.stocks
    assert spec.remotes["incidents"]["show"] == [{"part": "stock:incidents-backlog", "missing": True}]
    m = by_part(graph(local))["stock:incidents-backlog"]
    assert m["missing"] and m["value"] == "not served"


OPEN = ("sensor/incidents-open.main", 4.0, 30)


def _all_stale(local, why):
    bare = next(n for n in graph(local, "?open=*", [OPEN])["nodes"] if n["id"] == "stock:incidents-open")["valueText"]
    for q in ("", "?view=dynamics"):
        got = by_part(graph(local, q))
        assert got, (why, q)
        for m in got.values():
            assert m["stale"] is True, (why, q, m)
            assert m["value"] != bare and not m["value"].startswith(bare), (why, q, m)
        assert got["stock:incidents-open"]["value"].startswith(f"last {bare} · "), (why, got)
        assert got["stock:incidents-open"]["value"].endswith(" old"), (why, got)
        assert got["stock:incidents-backlog"]["value"] == "never read", (why, got)   # no sensor, nothing read here
    return got


def test_an_unreachable_remote_keeps_its_show_from_the_cache_every_measure_stale(tmp_path):
    local = local_model(tmp_path)
    served_into(local, tmp_path, text=REMOTE, ok=False)                  # the model failing
    spec, problems = problems_of(local)
    assert not [p for p in problems if p.code == "remote-show-unresolved"]
    assert [p for p in problems if p.code == "remote-unreachable"]
    got = _all_stale(local, "model failing")
    assert list(got) == ["stock:incidents-open", "stock:incidents-backlog", "flow:incidents-resolved"]
    assert got["flow:incidents-resolved"]["value"] == "never read"

    local = local_model(tmp_path, extra="    show: [stock.open, stock.backlog]")     # a local show, kept from the cache
    spec, problems = problems_of(local)
    assert not [p for p in problems if p.code == "remote-show-unresolved"]
    assert list(_all_stale(local, "model failing, local show")) == ["stock:incidents-open", "stock:incidents-backlog"]

    status(local, ok=True, failing_since=None, answered=time.time(), read=time.time() - 30, read_ok=False,
           read_why="refused", read_failing_since=time.time() - 20)     # the readings failing
    _all_stale(local, "readings failing")

    status(local, ok=True, answered=None, read=None, read_ok=None)      # never answered
    assert measures.refs(problems_of(local)[0], "incidents")
    _all_stale(local, "never answered")


def test_a_never_read_remote_draws_its_local_show_as_never_read_and_no_goal_fallback(tmp_path):
    local = local_model(tmp_path, extra="    show: [stock.open]", blocks=READER)   # (it names a part: the box is drawn)
    spec, problems = problems_of(local)                                  # nothing cached: 127.0.0.1:1 answers nothing
    assert [p for p in problems if p.code == "remote-unreachable"]
    assert not [p for p in problems if p.code == "remote-show-unresolved"]
    for q in ("", "?view=dynamics"):
        got = box(graph(local, q))
        assert len(got) == 1 and got[0]["part"] == "stock:incidents-open", (q, got)
        assert got[0]["unchecked"] and got[0]["stale"] and got[0]["value"] == "never read"

    local = local_model(tmp_path, blocks=STAND_IN)
    spec, _ = problems_of(local)
    assert "incidents-gone-goal" in spec.goals                           # a stand-in goal, there to fall back on
    for q in ("", "?view=dynamics"):
        assert box(graph(local, q)) == [], q


def test_a_fresh_remote_measure_is_not_stale_and_an_old_or_missing_reading_is(tmp_path):
    local = local_model(tmp_path, extra="    show: [stock.open, stock.depth, flow.resolved, stock.backlog]")
    served_into(local, tmp_path, text=REMOTE)
    status(local, answered=time.time(), read=time.time())                # the box ok
    reads = [("sensor/incidents-open.main", 4.0, 10), ("sensor/incidents-depth.main", 7.0, 3600)]
    bare = next(n for n in graph(local, "?open=*", reads)["nodes"] if n["id"] == "stock:incidents-open")["valueText"]
    assert bare and "4" in bare
    got = by_part(graph(local))
    assert got["stock:incidents-open"]["stale"] is False and got["stock:incidents-open"]["value"] == bare
    assert got["stock:incidents-depth"]["stale"] is True and got["stock:incidents-depth"]["value"].endswith(" · 1h old")
    assert got["flow:incidents-resolved"]["stale"] is True and got["flow:incidents-resolved"]["value"] == "never read here"
    assert got["stock:incidents-backlog"]["stale"] is False

    status(local, ok=False, why="refused", failing_since=time.time() - 60, fails=2)      # failing,
    assert by_part(graph(local))["stock:incidents-open"]["stale"] is True
    now = time.time()                                                    # then ok again, as a refresh leaves it
    status(local, checked=now, ok=True, why="", fails=0, answered=now, failing_since=None, next=now + 3600)
    p = Project(mdl.load(local))
    p.measurements.add("sensor/incidents-open.main", 5.0, at=time.time() - 5)
    got = by_part(graph(local))
    assert got["stock:incidents-open"]["stale"] is False, got




def test_a_sensor_with_no_every_is_bounded_by_the_least(tmp_path):
    """A sensor whose ``every`` is missing or 0 is held to ``readings.STALE_LEAST``: never fresh with no bound."""
    local = local_model(tmp_path, extra="    show: [stock.open]")
    served_into(local, tmp_path, text=REMOTE)
    status(local, answered=time.time(), read=time.time())
    spec, _ = problems_of(local)
    spec.stocks["incidents-open"].sensors["main"].every = 0
    b = {"label": "incidents", "remote": {"name": "incidents", "state": "ok"},
         "measures": [{"part": "stock:incidents-open", "value": "4"}]}
    at = 10_000.0
    measures.mark(spec, b, {"at": at, "times": {"sensor/incidents-open.main": at - measures.STALE_LEAST - 1}})
    assert b["measures"][0]["stale"] is True and b["measures"][0]["value"] == "last 4 · 2m01s old"
    b["measures"] = [{"part": "stock:incidents-open", "value": "4"}]
    measures.mark(spec, b, {"at": at, "times": {"sensor/incidents-open.main": at - measures.STALE_LEAST + 1}})
    assert b["measures"][0]["stale"] is False and b["measures"][0]["value"] == "4"
    b["measures"] = [{"part": "stock:incidents-open", "value": "4"}]
    measures.mark(spec, b, None)                                         # no reading times at all: never read here
    assert b["measures"][0]["stale"] is True and b["measures"][0]["value"] == "never read here"
