"""A run is an object (SPEC §9.1): ``ergostat.run``, one per run of a machine block, folded from its ``agent.started``
and ``agent.ran`` / ``agent.failed``: its outcome, cost and what it said (its log's last lines, kept on its end
event), browsable by its id, its block's runs listed a page at a time from the item index."""

from __future__ import annotations

import textwrap
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat import state, stuck
from ergostat.spec import items as its
from ergostat.spec import runitems
from ergostat.spec.engine import Engine
from ergostat.spec.item_sets import ItemSet, select
from ergostat.store import Project

MODEL = """\
name: t
blocks:
  drafter:
    type: program
    run: python3 drafter.py
  breaker:
    type: program
    run: python3 breaker.py
"""
DRAFTER = 'import sys\nsys.stdin.read()\nprint("starting", file=sys.stderr)\n' \
          'print("nothing to draft: 0 requests open", file=sys.stderr)\n'
BREAKER = 'import sys\nsys.stdin.read()\nprint("boom: no such table", file=sys.stderr)\nsys.exit(3)\n'


def project(tmp_path: Path, text: str = MODEL) -> Project:
    from ergostat import runner
    runner.STOPPING.clear()
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    (tmp_path / "drafter.py").write_text(DRAFTER)
    (tmp_path / "breaker.py").write_text(BREAKER)
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems if x.level == "error"]
    return Project(m)


def runs(p, block: str | None = None, n: int = 25, offset: int = 0) -> dict:
    return select(p.events, p.model.spec, ItemSet(runitems.RUN, where={"block": [block]} if block else {}),
                  n=n, offset=offset)


def test_a_run_is_an_object_with_its_outcome_and_what_it_said(tmp_path):
    p = project(tmp_path)
    e = Engine(p, say=lambda s: None)
    e.run_block(p.model.spec.blocks["drafter"], "by hand")
    (end,) = [x for x in p.events.query(n=None, type="agent.ran") if x["item"] == "drafter"]
    assert end["data"]["said"] == "starting\nnothing to draft: 0 requests open"     # on its end event, from its log
    got = runs(p, "drafter")
    assert got["total"] == 1
    (row,) = got["items"]
    assert row["id"] == f"ergostat.run/drafter/{end['causedby']}" and row["state"] == "ran"
    d = its.detail(p.events, p.model.spec, row["id"])
    f = d["fields"]
    assert f["block"] == "drafter" and f["outcome"] == "ran" and f["trigger"] == "by hand" and f["rung"] == "program"
    assert f["said"].endswith("nothing to draft: 0 requests open") and f["moved"] == "moved nothing"
    assert f["exit"] == 0 and isinstance(f["seconds"], float) and f["log"].startswith("file:logs/runs/drafter/")
    assert f["started"] <= f["ended"]
    assert [x["type"] for x in d["record"]] == ["agent.started", "agent.ran"]      # its own events, as recorded
    assert [m["to"] for m in d["moves"]] == ["running", "ran"]


def test_a_failed_runs_object_says_its_error(tmp_path):
    p = project(tmp_path)
    Engine(p, say=lambda s: None).run_block(p.model.spec.blocks["breaker"], "schedule")
    (row,) = runs(p, "breaker")["items"]
    f = its.detail(p.events, p.model.spec, row["id"])["fields"]
    assert row["state"] == "failed" and f["outcome"] == "failed" and f["error"] == "exited 3" and f["exit"] == 3
    assert "boom: no such table" in f["said"]
    assert runs(p, "drafter")["total"] == 0                                    # (another block's runs: not its)


def test_a_runs_cost_and_session_are_its_fields():
    start = {"id": "r1", "seq": 1, "time": 10.0, "type": "agent.started", "item": "writer", "data": {"trigger": "schedule"}}
    end = {"id": "r2", "seq": 2, "time": 12.0, "type": "agent.ran", "item": "writer", "causedby": "r1",
           "data": {"exit": 0, "seconds": 2.0, "openings": 1, "moved": {"done": 3},
                    "ai": {"cost_usd": 0.08, "cost": "reported", "tokens": {"total": 1200}, "model": "m",
                           "items": ["session/writer-r1"]},
                    "resources": {"cpu": 1.5, "memory_peak": 2048}}}
    it = its.fold("ergostat.run/writer/r1", runitems.derived([start, end]), runitems.run_kind())
    assert it.state == "ran"
    f = it.fields
    assert f["cost_usd"] == 0.08 and f["tokens"] == 1200 and f["cpu"] == 1.5 and f["memory"] == 2048
    assert f["sessions"] == ["session/writer-r1"] and f["moved"] == "moved 3 along flow.done; 1 openings"
    timed = {**end, "type": "agent.failed", "data": {"note": "stopped after its timeout of 5s"}}
    it = its.fold("ergostat.run/writer/r1", runitems.derived([start, timed]), runitems.run_kind())
    assert it.state == "failed" and it.fields["outcome"] == "timed-out"


def test_stuck_reads_what_the_last_run_said_from_its_end(tmp_path):
    p = project(tmp_path)
    end = {"type": "agent.ran", "causedby": "abc", "data": {"exit": 0, "said": "starting\nnothing to draft: none open",
                                                            "log": "logs/runs/drafter/gone.log"}}
    assert stuck.said_by(p, end) == "nothing to draft: none open"             # (its log long pruned: never read)
    assert stuck.run_link("drafter", end) == {"link": "/ergostat.run/drafter/abc"}


def test_a_goal_whose_block_produces_nothing_links_its_last_run(tmp_path):
    from tests import test_goal_stuck as tg
    p = tg.project(tmp_path)
    tg.off(p)
    for i in range(3):
        p.events.add("agent.ran", item="clearer", source="ergostat", at=time.time() - 50 + i * 10, causedby=f"run{i}",
                     data={"exit": 0, "seconds": 1, "openings": 0, "events": 0, "said": f"nothing to clear ({i})"})
    e = tg.entry(p, "backlog-empty")
    assert e["stuck"] == "the clearer's last 3 runs produced nothing: nothing to clear (2)"
    assert e["stuck_link"] == "/ergostat.run/clearer/run2"


def test_a_thousand_runs_are_paged_by_their_block_and_the_index_keeps_each_blocks_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(runitems, "KEPT", 300)
    p = project(tmp_path)
    t0 = time.time() - 5000
    rows = []
    for i in range(1000):
        b = "drafter" if i % 4 else "breaker"
        rows.append({"type": "agent.started", "item": b, "source": "ergostat", "id": f"{i:032x}", "at": t0 + i * 2,
                     "data": {"trigger": "schedule"}})
        rows.append({"type": "agent.failed" if b == "breaker" else "agent.ran", "item": b, "source": "ergostat",
                     "causedby": f"{i:032x}", "id": f"e{i:031x}", "at": t0 + i * 2 + 1,
                     "data": {"exit": 0, "seconds": 1.0, "said": f"run {i}"}})
    p.events.add_many(rows)
    got = runs(p, "drafter", n=25)
    assert got["total"] == 300 and len(got["items"]) == 25                     # (750 run: the newest 300 indexed)
    assert got["items"][0]["fields"]["said"] == "run 999"                      # newest first
    page2 = runs(p, "drafter", n=25, offset=25)
    assert page2["items"][0]["fields"]["said"] == "run 966" and not {i["id"] for i in page2["items"]} & \
        {i["id"] for i in got["items"]}
    assert runs(p, "breaker")["total"] == 250
    from ergostat.spec.itemindex import index_for, table_of
    ix = index_for(p.events, p.model.spec, False)
    assert ix.db.execute(f"select count(*) from {table_of(runitems.RUN)}").fetchone()[0] == 550   # bounded, per block
    old = its.detail(p.events, p.model.spec, f"ergostat.run/drafter/{1:032x}")   # an older run: read from the record
    assert old["state"] == "ran" and old["fields"]["said"] == "run 1"
    from ergostat.spec import itemindex          # a page reads its id range alone: never every run's body
    read: list[int] = []
    real = itemindex.Index.items

    def counted(self, *a, **k):
        out = real(self, *a, **k)
        read.append(len(out))
        return out
    monkeypatch.setattr(itemindex.Index, "items", counted)
    runs(p, "drafter", n=25, offset=200)
    assert read and max(read) <= 25, read


def test_a_run_goes_when_its_start_is_pruned_from_the_record(tmp_path):
    p = project(tmp_path)
    t0 = time.time() - 10 * 86400
    p.events.add("agent.started", item="drafter", source="ergostat", id="a" * 32, at=t0, data={"trigger": "schedule"})
    p.events.add("agent.ran", item="drafter", source="ergostat", causedby="a" * 32, at=t0 + 1, data={"exit": 0})
    p.events.add("agent.started", item="drafter", source="ergostat", id="b" * 32, data={"trigger": "schedule"})
    assert runs(p, "drafter")["total"] == 2
    assert p.events.prune(time.time() - 86400) >= 2
    got = runs(p, "drafter")
    assert got["total"] == 1 and got["items"][0]["state"] == "running"


def test_the_agents_page_asks_its_runs_from_the_api_and_a_run_has_its_page(tmp_path):
    from ergostat.web.server import Live, api
    p = project(tmp_path)
    e = Engine(p, say=lambda s: None)
    for _ in range(3):
        e.run_block(p.model.spec.blocks["drafter"], "by hand")
    e.run_block(p.model.spec.blocks["breaker"], "schedule")
    live = Live(p)
    got = api(live, "items", {"projection": ["ergostat.run"], "where": ["block:drafter"], "n": ["2"], "offset": ["0"]})
    assert got["total"] == 3 and len(got["items"]) == 2
    assert all(i["id"].startswith("ergostat.run/drafter/") and i["fields"]["said"] for i in got["items"])
    from urllib.parse import quote
    one = api(live, "items/" + quote(got["items"][0]["id"], safe=""), {})
    assert one["state"] == "ran" and one["fields"]["block"] == "drafter" and one["fields"]["log"]


def test_block_now_says_what_its_run_said_and_names_its_run(tmp_path, capsys):
    from ergostat.cli import main
    p = project(tmp_path)
    assert main(["-C", str(tmp_path), "block", "drafter", "--now"]) == 0
    out = capsys.readouterr().out
    (end,) = p.events.query(n=None, type="agent.ran")
    assert "said: nothing to draft: 0 requests open" in out
    assert f"its run: ergostat.run/drafter/{end['causedby']}" in out
