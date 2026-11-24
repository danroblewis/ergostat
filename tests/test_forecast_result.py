"""Acceptance (forecast-is-a-core-result): the completion estimates as one stable, versioned result, ``forecast/v1``
(numbers/forecast.py), per item, group and stage, worked out off the request path and read by the Timeline, a
dashboard panel's SQL views and the remote API.

Done 1: ``test_the_timeline_reads_the_forecast_and_shows_the_same_answers``. Done 2:
``test_a_panel_queries_forecast_rows_and_aggregates_through_the_sql_views``. Done 3:
``test_a_model_read_as_a_remote_exposes_its_forecast_to_the_model_reading_it`` (two instances). Done 4:
``test_each_answer_states_its_basis_sample_and_when_computed`` and ``test_no_estimate_is_said_never_read_as_none``."""

from __future__ import annotations

import base64
import json
import textwrap
import time
import types
import urllib.error
import urllib.request
from collections import OrderedDict
from urllib.parse import quote

import pytest

from ergostat import model as mdl
from ergostat.numbers import eta, etamodel, forecast
from ergostat.numbers.closedloop import parse_whatif
from ergostat.numbers.etamodel import _unscheduled
from ergostat.store import Project
from ergostat.web import eta_api

from .eta_synthetic import MODEL, generate
from .test_eta import inputs, paused_inputs

NOW = 1_790_000_000.0 + 8 * 3600
GROUPED = MODEL.replace("blocked_by: ticket", "blocked_by: ticket\n      parent: {kind: ticket, group: true}")


def grouped(tmp_path, extra: str = "", now: float = NOW) -> Project:
    """Eight hours of record up to ``now`` (``time.time()`` where the worker reads the real clock), and a group: the
    parent ticket/g0 and its three members."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(GROUPED.replace("{pool}", "3")) + extra)
    p = Project(mdl.load(tmp_path))
    generate(p, now - 8 * 3600, 8, rate=4, pool=3, backlog=12, seed=5)
    p.events.add("ticket.opened", item="ticket/g0", data={"title": "a group"}, at=now - 600)
    for n in (1, 2, 3):
        p.events.add("ticket.opened", item=f"ticket/g{n}", data={"parent": "ticket/g0"}, at=now - 500 + n)
    return p


@pytest.fixture
def fresh(monkeypatch):
    for name in ("_CACHE", "_WANT", "_CAL", "_CAL_WANT"):
        monkeypatch.setattr(eta_api, name, OrderedDict())


def at_now(monkeypatch):
    monkeypatch.setattr(eta_api, "time", types.SimpleNamespace(time=lambda: NOW, monotonic=time.monotonic))


def before(p, spec, kinds, w) -> dict:
    """The answer as the Timeline was given it before the forecast: the simulation's, with reasons' words."""
    inp = etamodel.read(p, spec, kinds, NOW)
    ans = eta.simulate(inp, pools=w.pools, failures=w.failures)
    why = eta.reasons(inp, w.pools)
    for i, x in ans["items"].items():
        r = dict(why.get(i) or {})
        if x.get("unscheduled"):
            r["said"] = x["why"]
        if x.get("unscheduled") and not r.get("why", "").startswith(x["why"]):
            r["why"] = f"not scheduled: {x['why']}" + (f"; {r['why']}" if r.get("why") else "")
        elif x.get("out"):
            r["why"] = "; ".join(filter(None, [r.get("why"), x["why"]]))
        x.update(r)
    ans["assumed"] = {b.name: b.assumed for b in inp.blocks if b.assumed}
    ans["sources"] = {b.name: eta_api._source(b, w.pools, getattr(spec.blocks.get(b.name), "pool_now", None))
                      for b in inp.blocks}
    ans["whatif"] = w.said()
    return ans


def test_the_timeline_reads_the_forecast_and_shows_the_same_answers(tmp_path, monkeypatch):
    p = grouped(tmp_path)
    spec, kinds = p.model.spec, eta_api.kinds_of(p.model.spec)
    at_now(monkeypatch)
    for whatif in ("", "block.dev.pool:6"):
        w = parse_whatif(spec, {k: v for k, v in (x.split(":", 1) for x in whatif.split(",") if ":" in x)})[1]
        fc, _ = eta_api._work(p, spec, kinds, w, (p.events.last_seq(),))
        assert fc["schema"] == forecast.SCHEMA and fc["runs"] == eta.RUNS and fc["seq"] == p.events.last_seq()
        old = before(p, spec, kinds, w)
        graph = {"items": [{"id": i} for i in sorted(old["items"])], "edges": []}
        new_t, old_t = eta_api.merge(graph, fc), eta_api.merge(graph, old)
        assert len(new_t["items"]) == len(old["items"]) >= 12
        for a, b in zip(new_t["items"], old_t["items"], strict=True):
            assert {k: a["eta"][k] for k in b["eta"]} == b["eta"], a["id"]          # every answer as before
            assert a.get("projected") == b.get("projected"), a["id"]                  # its bars too
        said = {k: v for k, v in old_t["eta"].items() if k not in ("schema", "version", "computed", "kinds")}
        assert {k: new_t["eta"][k] for k in said} == said                            # capacity, calibration...
        for k, v in old_t["eta"]["kinds"].items():                                   # each kind's last finish
            assert {x: new_t["eta"]["kinds"][k][x] for x in v} == v, k
        assert new_t["eta"]["schema"] == "forecast/v1" and new_t["eta"]["computed"] == NOW


def test_each_answer_states_its_basis_sample_and_when_computed(tmp_path, monkeypatch):
    p = grouped(tmp_path)
    inp = etamodel.read(p, p.model.spec, ["ticket"], NOW)
    assert inp.groups == {"ticket/g0": ["ticket/g0", "ticket/g1", "ticket/g2", "ticket/g3"]}   # from the relation
    at_now(monkeypatch)
    w = parse_whatif(p.model.spec, {})[1]
    fc, _ = eta_api._work(p, p.model.spec, ["ticket"], w)
    assert fc["basis"]["since"] == NOW - etamodel.HISTORY and fc["basis"]["horizon"] == eta.HORIZON
    for i, e in fc["items"].items():
        b = e["basis"]
        assert e["computed"] == NOW and e["runs"] == eta.RUNS and e["kind"] == "ticket", i
        assert b["from"] in ("block", "state") and isinstance(b["sample"], int) and b["sample"] >= 0, i
        x = inp.items[i]
        if x.state == "new":                                            # taken by dev: its recorded runs
            dev = next(b_ for b_ in inp.blocks if b_.name == "dev")
            assert b == {"from": "block", "name": "dev", "sample": len(dev.attempts), "of": "recorded runs"}, i
        if x.state == "review":                                         # no block: its state's stays
            assert b["from"] == "state" and b["sample"] == inp.kinds["ticket"].km["review"].n, i
    g = fc["groups"]["ticket/g0"]
    assert g["basis"]["members"] == 4 and g["runs"] == eta.RUNS and g["computed"] == NOW
    assert g["p50"] >= max(fc["items"][f"ticket/g{n}"]["p50"] for n in range(4))   # its last member's finish
    assert g["p50"] <= fc["kinds"]["ticket"]["p50"]
    st = fc["stages"]["ticket/new"]
    assert st["open"] == sum(x.state == "new" for x in inp.items.values()) and st["computed"] == NOW
    assert st["p50"] >= max(e["p50"] for i, e in fc["items"].items() if inp.items[i].state == "new")
    assert fc["kinds"]["ticket"]["basis"]["open"] == len(inp.items) and fc["kinds"]["ticket"]["runs"] == eta.RUNS


def test_no_estimate_is_said_never_read_as_none():
    inp = paused_inputs()                                    # t/0 paused: not scheduled
    _unscheduled(inp)
    inp.groups = {"t/1": ["t/1", "t/2", "t/3"]}

    def made(runs):
        sets, left = forecast.sets(inp)
        return forecast.build(inp, eta.simulate(inp, runs=runs, sets=sets), eta.reasons(inp), 5.0, 9, [], {}, left)
    fc = made(40)
    assert fc["items"]["t/0"]["none"] == "not scheduled: paused in parked" and fc["items"]["t/0"]["p50"] is None
    assert "none" not in fc["items"]["t/1"] and fc["items"]["t/1"]["p50"] is not None
    assert fc["stages"]["t/parked"]["none"] == "none of its open items can move"
    assert fc["stages"]["t/parked"]["unscheduled"] == 1 and "none" not in fc["stages"]["t/todo"]
    assert "none" not in fc["groups"]["t/1"] and "none" not in fc and fc["seq"] == 9
    few = made(5)                                            # too few runs for a p90: said, not left blank
    assert few["items"]["t/1"]["p90"] is None and few["items"]["t/1"]["p90_none"].startswith("5 runs, fewer than")
    nothing = made(0)                                        # no run: no estimate at all, said at the top
    assert nothing["items"] == {} and nothing["none"].startswith("no run of the simulation finished")
    beyond = inputs(n=2)                                     # never finishes within the horizon
    beyond.blocks[0].attempts = [etamodel.Attempt(eta.HORIZON * 2, "ack", "done")]
    beyond.blocks[0].run = etamodel.KM([eta.HORIZON * 2])
    got = forecast.build(beyond, eta.simulate(beyond, runs=20), {}, 1.0, 1, [], {})
    assert got["items"]["t/0"]["none"].startswith("not finished within the 90 days") and got["kinds"]["t"]["none"]
    bad = forecast.failed("KeyError: 'how'", 1.0, 3)
    assert bad["none"] == "the simulation failed: KeyError: 'how'" and bad["items"] == {} and bad["error"]


def test_the_forecast_is_reused_until_what_it_reads_changes(tmp_path, monkeypatch):
    p = grouped(tmp_path)
    at_now(monkeypatch)
    w = parse_whatif(p.model.spec, {})[1]
    fc, fp = eta_api._work(p, p.model.spec, ["ticket"], w)
    kept = {"ans": fc, "fp": fp}
    p.events.add("note.made", item="elsewhere", data={"x": 1}, at=NOW - 1)    # the record changed, not where it reads
    again, fp2 = eta_api._work(p, p.model.spec, ["ticket"], w, (p.events.last_seq(),), kept)
    assert again is fc and fp2 == fp                                          # reused, unrun: its version kept
    p.events.add("ticket.implemented", item="ticket/g1", at=NOW - 1)        # an item moved: worked out again
    moved, fp3 = eta_api._work(p, p.model.spec, ["ticket"], w, (p.events.last_seq(),), kept)
    assert moved is not fc and fp3 != fp and moved["items"]["ticket/g1"]["state"] == "review"
    monkeypatch.setattr(eta_api, "time", types.SimpleNamespace(time=lambda: NOW + eta_api.KEPT,
                                                               monotonic=time.monotonic))
    assert eta_api._work(p, p.model.spec, ["ticket"], w, (None,), kept)[0] is not fc   # past KEPT: always again


def test_the_worker_versions_each_forecast_it_works_out(tmp_path, fresh):
    p = grouped(tmp_path, now=time.time())
    first = eta_api.estimates(p, p.model, wait=30)
    assert first["schema"] == "forecast/v1" and isinstance(first["version"], int)
    assert eta_api.estimates(p, p.model)["version"] == first["version"]       # the same answer, read again
    other = eta_api.estimates(p, p.model, "block.dev.pool:6", wait=30)
    assert other["version"] > first["version"]


SQL = "\nsources:\n  record: {type: sql}\n"


def ask(p, text: str) -> dict:
    from ergostat.web.server import Live, api
    body = {"since": 3600.0, "until": time.time() + 3600, "points": 4, "queries": [{"id": "a", "source": "record", "text": text}]}
    q = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    [r] = api(Live(p), "query", {"q": [q]})["results"]
    return r


def test_a_panel_queries_forecast_rows_and_aggregates_through_the_sql_views(tmp_path, fresh, monkeypatch):
    p = grouped(tmp_path, SQL, time.time())
    r = ask(p, "select kind, p50 from forecast_kinds")                       # none yet: refused, never empty rows
    assert r.get("error_kind") == "unknown" and "being worked out" in r["error"], r
    fc = eta_api.estimates(p, p.model, wait=30)
    r = ask(p, "select id, state, basis, p50, p90, runs, sample, computed, estimate from forecast_items order by id")
    assert r["shape"] == "table" and len(r["rows"]) == len(fc["items"]), r
    for row in r["rows"]:
        e = fc["items"][row[0]]
        assert row[1:] == [e["state"], f"{e['basis']['from']} {e['basis']['name']}", e["p50"], e["p90"], e["runs"],
                           e["basis"]["sample"], e["computed"], 1]
    r = ask(p, "select state, open, p90, runs from forecast_stages order by state")     # by bounded labels
    assert [x[0] for x in r["rows"]] == sorted({e["state"] for e in fc["items"].values()})
    assert all(x[3] == fc["runs"] for x in r["rows"])
    r = ask(p, "select parent, open, p50 from forecast_groups")
    assert r["rows"] == [["ticket/g0", 4, fc["groups"]["ticket/g0"]["p50"]]]
    r = ask(p, "select kind, count(*) as n, max(p90) as last from forecast_items group by kind")
    assert r["rows"] == [["ticket", len(fc["items"]), max(e["p90"] for e in fc["items"].values())]]
    assert ask(p, "delete from forecast_items").get("error_kind") == "refused"            # read only
    monkeypatch.setattr(eta_api, "current", lambda *a: forecast.failed("KeyError: 'how'", NOW, 1))
    r = ask(p, "select kind, p50 from forecast_kinds")
    assert r.get("error_kind") == "unknown" and "no forecast: the simulation failed" in r["error"], r


def _get(url, token=None):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def test_a_model_read_as_a_remote_exposes_its_forecast_to_the_model_reading_it(tmp_path, fresh):
    from ergostat.remote import items as remote_items
    from ergostat.remote import tokens
    from ergostat.web import serve as web_serve
    from tests.ports import free_port
    there = grouped(tmp_path / "shop", now=time.time())
    a, a_url = web_serve(there, free_port())
    b = None
    try:
        tok = tokens.issue(there.dir, "reader")
        assert _get(f"{a_url}/remote/v1/forecast", tok)[0] in (200, 503)        # never worked out on the request
        fc = eta_api.estimates(there, there.model, wait=30)
        here_dir = tmp_path / "reader"
        here_dir.mkdir()
        (here_dir / "shop.token").write_text(tok)
        (here_dir / "ergostat.yaml").write_text(textwrap.dedent(f"""
            name: reader
            remotes:
              shop:
                url: {a_url}
                token-file: shop.token
                every: 60s
            stocks:
              queue:
                sensor: {{run: echo 1}}
            """))
        here = Project(mdl.load(here_dir))
        b, b_url = web_serve(here, free_port())
        ids = ["ticket/g1", "ticket/g2"]
        code, got = _get(f"{b_url}/api/forecast?remote=shop&" + "&".join(f"item={quote(i, safe='')}" for i in ids))
        assert code == 200 and got["ok"] and got["remote"] == "shop", got
        read, fc = got["forecast"], eta_api.estimates(there, there.model)       # (the one it served: asked again, kept)
        assert read["schema"] == "forecast/v1" and read["version"] == fc["version"] and read["computed"] == fc["computed"]
        assert read["items"] == {i: fc["items"][i] for i in ids}                  # as the remote worked them out
        assert read["groups"]["ticket/g0"] == fc["groups"]["ticket/g0"] and "schedule" not in read
        code, whole = _get(f"{b_url}/api/forecast?remote=shop&kinds=ticket")
        assert code == 200 and whole["forecast"]["items"] == fc["items"]
        assert whole["forecast"]["kinds"] == fc["kinds"]
        code, own = _get(f"{a_url}/api/forecast?item=ticket/g1")               # the same answer read locally there
        assert code == 200 and own["items"] == {"ticket/g1": fc["items"]["ticket/g1"]}
        assert _get(f"{b_url}/api/forecast?remote=nope")[0] == 400
        assert _get(f"{a_url}/remote/v1/forecast?" + "&".join(f"item=t/{n}" for n in range(201)), tok)[0] == 400
        with pytest.raises(remote_items.RemoteRefused):
            remote_items.forecast(here.model.spec, "shop", ["../events"])
    finally:
        for s in (a, b):
            if s is not None:
                s.shutdown()
                s.server_close()
        remote_items._state.clear()
