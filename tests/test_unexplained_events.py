"""The modelling subsystem's third loop (SPEC §12e, *Unexplained events*): the events no projection takes, counted
incrementally and grouped into requests; the owner's ignores; the drafter (a stand-in for the AI session) proposing a
projection, judged by what it takes (passed when the unexplained events it targets fall, failed when it adds events
with no key); the change waiting for the owner, and Accept writing it; nothing of it with ai off."""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat.numbers import drafter as dr
from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.numbers import requests as rq
from ergostat.numbers import unexplained as ux
from ergostat.spec import read
from ergostat.store import Project

MODEL = """\
name: t
projections:
  alert:
    query: key.startswith('alert/')
    description: an alert from the pager
    fields:
      state:
        values: [new, closed]
    events:
      alert-fired:
        when: type == 'alert.fired'
        '...': data
        state: set('new')
      other:
        when: true
        '...': data
stocks:
  new-alerts:
    unit: alerts
    description: alerts not yet closed
    sensor: {projection: alert, state: new, every: 2s}
uses:
  modelling:
    use: modelling
    with:
      ai: true
      ignore-events: ['debug.*']
"""

DEPLOY = """\
query: type == 'deploy.finished'
key: [service]
fields:
  state:
    values: [done]
  service: text
events:
  deploy-finished:
    when: type == 'deploy.finished'
    service: data.service
    state: set('done')
"""

NO_KEY = DEPLOY.replace("service: data.service", "service: data.nowhere")


def project(tmp_path: Path, text: str = MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems if x.level == "error"]
    return Project(m)


def again(p: Project) -> Project:
    return Project(mdl.load(Path(p.model.path).parent))


def emit(p: Project, n: int = 3, at: float | None = None) -> None:
    t = at or time.time() - 60
    for i in range(n):
        p.events.add("deploy.finished", source="deployer", data={"service": f"s{i}", "seconds": 30 + i}, at=t + i)
    p.events.add("alert.fired", item="alert/1", source="pager", data={"title": "x"}, at=t)     # taken by alert
    p.events.add("debug.tick", source="deployer", data={}, at=t)                              # ignored by the owner
    p.events.add("agent.ran", item="agent/x", source="ergostat", data={}, at=t)               # ergostat's own
    p.events.add("deploy.noted", source="projection:deploy", data={}, at=t)                   # a projection's own


def test_the_measure_counts_what_no_projection_takes_and_groups_it(tmp_path):
    p = project(tmp_path)
    emit(p)
    got = ux.sync(p)
    assert got["events"] == 3 and got["ignored"] == 1 and got["groups"] == 1
    gs = {g["type"]: g for g in ux.groups(p)}
    assert set(gs) == {"deploy.finished", "debug.tick"}                   # never agent.ran, nor a projection's own
    assert gs["debug.tick"]["ignored"] == "debug.*" and gs["deploy.finished"]["by"] == {"unread": 3}
    (r,) = [r for r in rq.current(p) if r.get("source") == "events"]
    assert r["code"] == ux.CODE and r["tier"] == "events" and r["group"] == {"source": "deployer", "type": "deploy.finished"}
    assert r["unexplained"]["count"] == 3 and len(r["unexplained"]["examples"]) == 3 and r["unexplained"]["first"]
    assert rq.evidence_of(r) == f"request:{r['id']}"
    assert not [x for x in rq.for_ai(p, 2) if x.get("source") == "events"]    # the modeller never takes them
    got = ux.sync(p)                                                           # nothing new: nothing moves
    assert got["raised"] == 0 and got["events"] == 3


def test_a_type_that_tells_nothing_is_grouped_by_the_envelopes_shape(tmp_path):
    p = project(tmp_path)
    for i in range(4):
        p.events.add("log", source="lines", data={"msg": "x", "level": "info"} if i % 2 else {"path": "/", "status": 200})
    gs = ux.groups(p)
    assert sorted(g.get("shape") for g in gs) == ["level,msg", "path,status"] and all(g["count"] == 2 for g in gs)


def test_it_reads_only_the_new_events_each_time(tmp_path, monkeypatch):
    p = project(tmp_path)
    emit(p, 50)
    ux.update(p)
    read = []
    real = p.events.query

    def counted(*a, **k):
        got = real(*a, **k)
        read.append(len(got))
        return got
    monkeypatch.setattr(p.events, "query", counted)
    emit(p, 2)
    st = ux.update(p)
    assert sum(read) == 2 + 4                                  # the two new deploys and the four others, nothing older
    assert ux.total(ux.groups(p, st=st)) == 52


def test_it_falls_when_a_projection_takes_them(tmp_path):
    p = project(tmp_path)
    emit(p)
    ux.sync(p)
    text = p.model.path.read_text().replace("projections:\n", "projections:\n  deploy:\n"
                                            + textwrap.indent(DEPLOY, "    "), 1)
    p.model.path.write_text(text)
    p = again(p)
    got = ux.sync(p)
    assert got["events"] == 0 and got["answered"] == 1
    assert [r["state"] for r in rq.stored(p).values() if r.get("source") == "events"] == ["answered"]


def stand_in(tmp_path: Path, body: str) -> str:
    """An AI session's stand-in (ERGOSTAT_AI): it answers with a draft of ``body`` for every request it is given."""
    f = tmp_path / "drafter-standin.py"
    f.write_text(textwrap.dedent(f"""\
        #!{sys.executable}
        import json, re, sys
        text = sys.stdin.read()
        ids = re.findall(r'^{{"id": "([0-9a-f]+)", "group"', text, re.M)
        line = json.dumps({{"draft": {{"name": "deploy", "yaml": {body!r}, "requests": ids,
                                       "review": {{"read": 3, "taken": 3, "no_key": 0}}}}}})
        print(json.dumps({{"result": "looked, drafted, reviewed\\n" + line, "total_cost_usd": 0.02,
                          "usage": {{"input_tokens": 10, "output_tokens": 5}}}}))
        """))
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    return str(f)


def drafted(tmp_path, monkeypatch, body: str):
    p = project(tmp_path)
    emit(p)
    ux.sync(p)
    monkeypatch.setenv("ERGOSTAT_AI", stand_in(tmp_path, body))
    out = dr.run(p, daily=1.0)
    return p, out


def test_the_drafters_projection_passes_when_it_explains_them_and_waits_for_the_owner(tmp_path, monkeypatch):
    p, out = drafted(tmp_path, monkeypatch, DEPLOY)
    assert len(out["proposed"]) == 1, out
    (pid,) = out["proposed"]
    x = pr.stored(p)[pid]
    assert x["kind"] == "structure" and x["made_by"] == "drafter" and x["drafted"]["deploy"].startswith("query:")
    assert x["explains"] and x["projections_changed"] == ["deploy"]
    (r,) = [r for r in rq.stored(p).values() if r.get("source") == "events"]
    assert ux.sync(p)["proposed"] == 1                                         # its change cites it
    assert "1 groups have a draft waiting for the owner" in dr.run(p, daily=1.0)["said"]   # not "no events wait"
    got = jd.run(p, "judge")
    x = pr.stored(p)[pid]
    assert x["state"] == "passed", (x["state"], got["verdicts"])
    assert x["verdict"]["on"] == "events" and x["verdict"]["evidence"]["targeted"] == {"read": 3, "before": 3, "after": 0}
    assert x["explained"] == 3                                                 # what events-taken sums once written
    assert got["accepted"] == 0                                                # structure: the owner's by default
    assert "deploy:" not in p.model.path.read_text()
    pr.accept(p, pid, {"at": time.time(), "window": 600})                     # the owner accepts it: written
    assert "  deploy:" in p.model.path.read_text()
    assert f"# inferred: ergostat.model-change/{pid}" in p.model.path.read_text()    # drafted, not declared
    p = again(p)
    assert ux.sync(p)["events"] == 0
    assert rq.stored(p)[r["id"]]["state"] == "answered"
    from ergostat.numbers import modeller_spend as sp
    assert sp.spent(p) > 0                                                     # counted in the AI tier's day


def test_a_draft_that_leaves_events_with_no_key_fails(tmp_path, monkeypatch):
    p, out = drafted(tmp_path, monkeypatch, NO_KEY)
    (pid,) = out["proposed"]                                                   # checked: it compiles
    jd.run(p, "judge")
    x = pr.stored(p)[pid]
    assert x["state"] == "failed" and "no key" in x["verdict"]["why"], x["verdict"]
    assert x["verdict"]["evidence"]["projections"]["deploy"]["after"]["no_key"] == 3
    (r,) = [r for r in rq.stored(p).values() if r.get("source") == "events"]
    ux.sync(p)
    assert rq.stored(p)[r["id"]]["state"] == "held"                            # its change failed: held, with why


def test_the_drafter_spends_nothing_past_the_day(tmp_path, monkeypatch):
    p = project(tmp_path)
    emit(p)
    ux.sync(p)
    monkeypatch.setenv("ERGOSTAT_AI", "/nonexistent")
    out = dr.run(p, daily=0.1, budget=0.5)
    assert out.get("capped") and not out["proposed"]


def test_with_ai_off_nothing_of_it_runs(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: t\nuses:\n  modelling:\n    use: modelling\n")
    spec, ps = read(tmp_path / "ergostat.yaml")
    assert not [x for x in ps if x.level == "error"]
    assert "drafter" not in spec.blocks and "unexplained-events" not in spec.stocks
    assert "events-explained" not in spec.goals
    from ergostat.sensing import command
    runs = [command(spec, s) for x in [*spec.stocks.values(), *spec.flows.values()] for s in x.sensors.values() if s.commands]
    assert runs and not [r for r in runs if "modelling events" in r]
    (tmp_path / "on").mkdir()
    (tmp_path / "on" / "ergostat.yaml").write_text("name: t\nuses:\n  modelling:\n    use: modelling\n    with: {ai: true}\n")
    spec, ps = read(tmp_path / "on" / "ergostat.yaml")
    assert spec.blocks["drafter"].type == "ai" and spec.goals["events-explained"].of.name == "unexplained-events"
    assert "modelling draft" in spec.blocks["drafter"].params["run"]


def test_an_empty_install_has_no_drafter(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: t\n")
    spec, _ = read(tmp_path / "ergostat.yaml")
    assert not spec.blocks and "unexplained-events" not in spec.stocks


def test_the_inbox_offers_the_draft_in_the_workbench(tmp_path, monkeypatch):
    from ergostat.inbox import entries
    p = project(tmp_path, MODEL.replace("      ai: true\n", "      ai: true\n      review: {when: off}\n"))
    emit(p)
    ux.sync(p)
    monkeypatch.setenv("ERGOSTAT_AI", stand_in(tmp_path, DEPLOY))
    (pid,) = dr.run(p, daily=1.0)["proposed"]
    jd.run(p, "judge")
    (e,) = [e for e in entries._changes(p, p.model.spec, time.time()) if e["id"] == f"change/{pid}"]
    assert e["workbench"] == [{"projection": "deploy", "link": f"/?workbench=deploy&proposal={pid}"}]


def test_the_sensor_prints_the_unexplained_events(tmp_path, monkeypatch, capsys):
    from ergostat.library.run import modelling as ml
    p = project(tmp_path)
    emit(p, 4)
    monkeypatch.chdir(tmp_path)
    assert ml.events([]) == 0
    assert capsys.readouterr().out.strip() == "4"
