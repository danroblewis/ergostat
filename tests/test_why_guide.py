"""The agent guide's section on models that answer "why isn't this done?" (docs/AGENT-GUIDE.md §3m) is real: its
worked example's model is loaded from the guide, three stalls are seeded on it as the described process would leave
them, and ``ergostat why`` names the true root of each (the scripted acceptance); every command in the section is run,
in order, on that record and exits 0; and ``check``'s ``wait-unexplained`` finding (spec/waits.py) is found for a kind
whose waiting nothing explains, and for no other."""

from __future__ import annotations

import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.leases import TAKEN
from ergostat.spec.waits import unexplained
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs" / "AGENT-GUIDE.md"
SKILL = ROOT / "docs" / "skills" / "ergostat-author" / "SKILL.md"
HEAD = "## 3m. "


def section() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index("\n" + HEAD) + 1
    return text[start:text.index("\n## ", start + 1)]


def model_text() -> str:
    got = re.findall(r"^<!-- why: the worked example's model -->\n```yaml\n(.*?)^```$", section(), re.S | re.M)
    assert len(got) == 1, "the worked example's model is marked once in the section"
    return got[0]


def commands() -> list[str]:
    blocks = re.findall(r"^```sh\n(.*?)^```$", section(), re.S | re.M)
    return [line for b in blocks for line in b.splitlines() if line.strip()]


def dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def project(tmp_path: Path, text: str | None = None) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text) if text else model_text())
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def seed(p: Project, pid: bool = True) -> None:
    """The three stalls of the worked example, as the process records them (the person's and the collector's
    events, the releaser's taking under the budget, its process since gone), and the readings the engine leaves (the
    build service's sensor, the gate's output)."""
    now, add = time.time(), p.events.add
    add("change.proposed", item="change/c1", at=now - 7200)
    add("change.held", item="change/c1", at=now - 7000)
    add("change.proposed", item="change/c2", at=now - 6000, data={"depends_on": "change/c1"})
    add("change.proposed", item="change/c3", at=now - 5000, data={"depends_on": "change/c2"})
    add("change.proposed", item="change/c5", at=now - 3000)
    for s in p.model.spec.auxiliaries["build-service-up"].sensors.values():
        p.measurements.add(s.series, 0.0, at=now - 60)
    p.measurements.add("block/build-open", 0.0, at=now - 60)
    for c in ("c6", "c7"):
        add("pr.opened", item=f"pr/{c}", at=now - 2800)
        add("pr.merged", item=f"pr/{c}", at=now - 2700)
        add("change.proposed", item=f"change/{c}", at=now - 2600, data={"pull_request": f"pr/{c}"})
        add("change.built", item=f"change/{c}", at=now - 2500)
        add("change.reviewed", item=f"change/{c}", at=now - 2400)
    add(TAKEN, item="change/c6", source="ergostat", at=now - 2300,
        data={"run": "r6", "block": "releaser", "fence": 1, "ttl": 3600.0, "max": 2,
              **({"pid": dead_pid()} if pid else {})})       # (the dispatcher records the pid only under a budget)


@pytest.fixture
def engine(tmp_path):
    """The worked example's project with an engine running, as ``why`` reads it: the run lock held, the heartbeat
    fresh."""
    p = project(tmp_path)
    with open(p.dir / "run.pid", "w") as f:
        f.write(str(os.getpid()))
        f.flush()
        fcntl.flock(f, fcntl.LOCK_EX)
        (p.dir / "heartbeat.json").write_text(json.dumps({"written": time.time(), "pid": os.getpid()}))
        yield p


def run(tmp_path, line: str, capsys) -> tuple[int, str]:
    argv = shlex.split(line)
    assert argv[0] == "ergostat", line
    capsys.readouterr()
    rc = main(["-C", str(tmp_path), *argv[1:]])
    return rc, capsys.readouterr().out


def why(tmp_path, item: str, capsys) -> dict:
    rc, out = run(tmp_path, f"ergostat why {item} --json", capsys)
    assert rc == 0, out
    return json.loads(out)


# ---- the scripted acceptance: the worked example's three stalls, each named at its true root

def test_the_worked_example_names_the_true_root_of_each_of_three_stalls(engine, tmp_path, capsys):
    seed(engine)
    a = why(tmp_path, "change/c3", capsys)["root"]
    assert (a["kind"], a["item"], a["path"]) == ("parked", "change/c1", ["change/c3", "change/c2", "change/c1"]), a
    assert "on-hold" in a["says"] and a["owner"] == "the owner"
    b = why(tmp_path, "change/c5", capsys)["root"]
    assert b["kind"] in ("closed", "gate") and b.get("gate") == "build-open" and b["item"] == "change/c5", b
    assert "auxiliary.build-service-up" in b["owner"] and "up is 0" in b["says"]
    c = why(tmp_path, "change/c7", capsys)["root"]
    assert (c["kind"], c["item"], c.get("via")) == ("lease", "change/c6", "releaser"), c
    assert "is gone" in c["says"] and "ERGOSTAT_ITEM=change/c6 " in c["command"] and "--nack" in c["command"]
    rc, out = run(tmp_path, "ergostat held-up --json", capsys)
    h = json.loads(out)
    assert rc == 0 and h["unknown"] == 0 and h["stall"], h["line"]
    got = {(r["kind"], r["item"]) for r in h["roots"]}
    assert {("parked", "change/c1"), ("lease", "change/c6")} <= got, got
    assert any(r["kind"] == b["kind"] and "build-open" in r["says"] for r in h["roots"]), h["roots"]
    assert all(r["kind"] != "unknown" for r in h["roots"])


def test_without_the_budget_the_dead_lease_cannot_be_told_from_live_work(tmp_path, capsys):
    """The guide's reason for ``budget:``: with it left out, the same dead run is said as not known."""
    text = model_text().replace("budget: {daily: 5, max-cost: 1}", "")
    assert "budget:" not in text
    p = project(tmp_path, text)
    with open(p.dir / "run.pid", "w") as f:
        f.write(str(os.getpid()))
        f.flush()
        fcntl.flock(f, fcntl.LOCK_EX)
        (p.dir / "heartbeat.json").write_text(json.dumps({"written": time.time(), "pid": os.getpid()}))
        seed(p, pid=False)
        a = why(tmp_path, "change/c7", capsys)
    assert a["root"]["kind"] == "pool-full" and any("not recorded" in m for m in a["missing"]), a["root"]


def test_a_working_state_names_whoever_records_the_move_on_to_the_next_state(tmp_path):
    """The review is a person's working state: ``why`` names the event that moves it on to the next state
    (change.reviewed), before a side exit or a move back (change.dropped, change.held, change.proposed)."""
    from ergostat.why import answer
    p = project(tmp_path)
    p.events.add("change.proposed", item="change/c9")
    p.events.add("change.built", item="change/c9")
    r = answer(p, "change/c9")["root"]
    assert r["kind"] == "work" and r["owner"] == "whoever records change.reviewed", r
    assert "recorded: change.reviewed, change.released, change.held, change.dropped, change.proposed" in r["says"], r


# ---- every command in the section runs

def test_every_command_in_the_section_runs_on_the_worked_example(engine, tmp_path, capsys):
    seed(engine)
    lines = commands()
    assert len(lines) >= 10, lines
    said = []
    for line in lines:
        rc, out = run(tmp_path, line, capsys)
        assert rc == 0, f"{line}\n{out}"
        said.append((line, out))
    todo = [out for line, out in said if line == "ergostat why todo/t1"]
    assert len(todo) == 2
    assert "It waits on batch/lab-1124" in todo[0] and "Next: whoever records batch.opened" in todo[0], todo[0]
    assert "Next: whoever records todo.done" in todo[1] and "batch/lab-1124" not in todo[1].split("\n")[0], todo[1]
    upd = why(tmp_path, "todo/u48", capsys)
    assert upd["root"]["kind"] == "work" and upd["root"]["path"] == ["todo/u48"], "covers says, never waits"
    held = next(json.loads(out) for line, out in said if line == "ergostat held-up --json")
    assert held["unknown"] == 0
    rc, out = run(tmp_path, "ergostat check --json", capsys)
    assert rc == 0 and not [f for f in json.loads(out)["found"] if f["code"] == "wait-unexplained"]


def test_every_command_named_in_the_section_is_one_it_runs():
    """A command written inline (``ergostat why ITEM``) matches one the section's blocks run, its placeholders (words
    in capitals) standing for their arguments: so every command the section names is run by the test above."""
    ran = commands()
    named = re.findall(r"`(ergostat [^`]+)`", re.sub(r"^```.*?^```$", "", section(), flags=re.S | re.M))
    assert named
    for n in named:
        pat = r"\s+".join(r"\S+" if re.fullmatch(r"[A-Z]+", w) else re.escape(w) for w in n.split())
        assert any(re.fullmatch(pat, r) for r in ran), f"`{n}` is named in the section but no block runs it"


def test_the_skill_sends_every_agent_setting_up_a_model_to_the_section():
    text = SKILL.read_text(encoding="utf-8")
    assert "section 3m" in text and "ergostat why" in text and "held-up" in text


# ---- check's wait-unexplained

KIND = """
items:
  todo:
    id: todo/*
    states: @STATES@
    on: @ON@
    @REL@
messages:
  done: {todo: [done]}
@BLOCKS@
"""


def kinds_text(states="[todo, done]", on="{todo.added: todo, todo.done: done}", relations="", blocks="") -> str:
    return KIND.replace("@STATES@", states).replace("@ON@", on).replace("@REL@", relations).replace("@BLOCKS@", blocks)


def kinds(tmp_path, states="[todo, done]", on="{todo.added: todo, todo.done: done}", relations="", blocks="") -> dict:
    p = project(tmp_path, kinds_text(states, on, relations, blocks))
    return {k.name: bad for k, bad in unexplained(p.model.spec)}


def test_a_kind_whose_waiting_nothing_explains_is_found(tmp_path, capsys):
    assert kinds(tmp_path) == {"todo": ["todo"]}, "its first state: where items wait to be taken, and nothing takes"
    rc, out = run(tmp_path, "ergostat check --json", capsys)
    got = [f for f in json.loads(out)["found"] if f["code"] == "wait-unexplained"]
    assert rc == 0 and len(got) == 1 and got[0]["level"] == "finding" and got[0]["about"] == "items.todo"
    assert "todo" in got[0]["message"] and got[0]["line"]
    assert kinds(tmp_path, states="[new, todo, done]", on="{todo.added: todo}") == {"todo": ["todo"]}, \
        "a later state no event moves it out of: no one is named to act"


def test_a_block_a_relation_or_a_working_state_explains_it(tmp_path):
    assert kinds(tmp_path, blocks="blocks:\n  doer: {type: program, run: 'true', takes: {kind: todo, at: todo}}") == {}
    assert kinds(tmp_path, relations="relations: {after: todo}") == {}
    assert kinds(tmp_path, relations="relations: {mentions: todo}") == {"todo": ["todo"]}, "not precedence: says only"
    assert kinds(tmp_path, states="[new, todo, done]") == {}, "a working state, moved on by todo.done"


def test_only_declared_finished_kinds_are_judged(tmp_path):
    """A kind whose finished states are inferred from the record is finished as the record shows: not judged."""
    text = kinds_text(on="{todo.added: todo}").replace("messages:\n  done: {todo: [done]}\n", "")
    p = project(tmp_path, text)
    assert unexplained(p.model.spec) == []


def test_the_guides_example_and_the_shipped_examples_have_no_unexplained_wait(tmp_path):
    assert unexplained(project(tmp_path).model.spec) == []
    for f in [ROOT / "ergostat.yaml", *sorted(ROOT.glob("examples/*/ergostat.yaml"))]:   # and the factory's own
        m = mdl.load(f.parent)
        assert m.spec is None or unexplained(m.spec) == [], f.parent.name
