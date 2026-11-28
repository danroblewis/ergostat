"""Where a goal off is stuck (SPEC §8, *Where a goal off is stuck*): its loop followed from the stock to the blocks that
act for it, the first place it stops said in one line on its attention entry: a block that never ran, one whose last
run failed, one whose runs produce nothing; and modelling's changes followed through their states, from the changes
store: sent back by the reviewer (with its latest finding), waiting for the owner."""

from __future__ import annotations

import textwrap
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat import state
from ergostat.store import Project

MODEL = """\
name: t
stocks:
  backlog:
    unit: items
    sensor: {run: "echo 5", every: 1m}
flows:
  cleared:
    from: backlog
goals:
  backlog-empty:
    stock: backlog
    hold: "<= 0"
blocks:
  clearer:
    type: program
    goal: backlog-empty
    run: "true"
    every: 1m
    out: flow.cleared
"""


def project(tmp_path: Path, text: str = MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems if x.level == "error"]
    return Project(m)


def off(p: Project, stock: str = "backlog", value: float = 5) -> None:
    (s,) = p.model.spec.stocks[stock].sensors.values()
    t = time.time() - 120
    p.events.add("ergostat.started", source="ergostat", at=t)
    p.measurements.add(s.series, value, at=t + 10)
    p.measurements.add(s.series, value, at=time.time() - 5)


def entry(p: Project, goal: str) -> dict:
    snap = state.snapshot(p)
    (e,) = [a for a in state.attention(snap, True, p.model) if a.get("goal") == goal]
    return e


def test_a_goal_whose_block_never_ran_says_so(tmp_path):
    p = project(tmp_path)
    off(p)
    e = entry(p, "backlog-empty")
    assert e["state"] == "off"
    assert e["stuck"] == "the clearer has never run (every 1m)" and e["stuck_link"] == "/agents/clearer"


def test_a_goal_whose_block_fails_says_why(tmp_path):
    p = project(tmp_path)
    off(p)
    p.events.add("agent.failed", item="clearer", source="ergostat", at=time.time() - 20,
                 data={"exit": 3, "note": "exited 3: no such table"})
    e = entry(p, "backlog-empty")
    assert e["stuck"].startswith("the clearer's last run failed (") and e["stuck"].endswith("): exited 3: no such table")


def test_a_goal_whose_block_runs_and_produces_nothing_says_what_it_said(tmp_path):
    p = project(tmp_path)
    off(p)
    for i in range(3):
        p.events.add("agent.ran", item="clearer", source="ergostat", at=time.time() - 50 + i * 10,
                     data={"exit": 0, "seconds": 1, "openings": 0, "events": 0,
                           **({"log": "logs/runs/clearer/1.log"} if i == 2 else {})})
    d = Path(p.dir) / "logs" / "runs" / "clearer"
    d.mkdir(parents=True, exist_ok=True)
    (d / "1.log").write_text('starting\n{"x": 1}\nnothing older than a day to clear\n')
    e = entry(p, "backlog-empty")
    assert e["stuck"] == "the clearer's last 3 runs produced nothing: nothing older than a day to clear"


def drafted(tmp_path, monkeypatch, review: bool = True):
    """Modelling's events-explained off, the stand-in drafter's projection proposed and passed by the judge."""
    from ergostat.numbers import drafter as dr
    from ergostat.numbers import judge as jd
    from ergostat.numbers import unexplained as ux
    from tests import test_unexplained_events as tu
    text = tu.MODEL if review else tu.MODEL.replace("      ai: true\n", "      ai: true\n      review: {when: off}\n")
    p = tu.project(tmp_path, text)
    p.events.add("agent.ran", item="drafter", source="ergostat", at=time.time() - 100, data={"exit": 0, "seconds": 1})
    tu.emit(p)
    ux.sync(p)
    monkeypatch.setenv("ERGOSTAT_AI", tu.stand_in(tmp_path, tu.DEPLOY))
    (pid,) = dr.run(p, daily=1.0)["proposed"]
    jd.run(p, "judge")
    off(p, "unexplained-events", 3)
    return p, pid


def test_modellings_drafts_sent_back_by_the_reviewer_say_so_with_its_latest_finding(tmp_path, monkeypatch):
    import json

    from ergostat.numbers import reviewer as rv
    p, pid = drafted(tmp_path, monkeypatch)
    finding = "State modifying has no exit: nothing leaves it"

    def call(text, model, timeout=None):
        return {"result": json.dumps({"review": {"verdict": "revise", "findings": [{"check": "chain", "says": finding}]}}),
                "usd": 0.01, "tokens_in": 10, "tokens_out": 5, "seconds": 0.1}
    assert rv.run(p, call=call)["verdicts"] == [{"id": pid, "verdict": "revise"}]
    e = entry(p, "events-explained")
    assert e["stuck"] == (f"1 change the drafter made over the last day: 1 sent back by the reviewer "
                          f"(latest: “{finding}”)"), e
    assert e["stuck_link"] == "/ergostat.model-change?state=sent-back&finished=show&q=drafter"
    lp = state.snapshot(p)["loops"]["events-explained"]
    (ch,) = [s for s in lp["stuck"]["steps"] if s["step"] == "changes"]
    assert [(c["what"], c["n"]) for c in ch["counts"]] == [("sent-back", 1)]


def test_modellings_drafts_waiting_for_the_owner_say_so(tmp_path, monkeypatch):
    p, pid = drafted(tmp_path, monkeypatch, review=False)
    e = entry(p, "events-explained")
    assert e["stuck"] == "1 change the drafter made over the last day: 1 waits for you", e
    assert e["stuck_link"] == "/inbox"
