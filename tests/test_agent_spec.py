"""An agent's answer carries what it is (dev/records/agent-spec-api.md): its block as written, its law, its machine, its
decisions, its rung's reason, its own module and its files, each file read only from inside the project."""

import json
import os
import shutil
import statistics
import sys
import textwrap
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.store import Project
from ergostat.web.server import Live, api

ROOT = Path(__file__).resolve().parent.parent

MODEL = """
name: t
stocks:
  todo: {sensor: {manual: true}}
  aside: {sensor: {manual: true}}
flows:
  done: {from: todo}
  sorted: {from: todo}
  classed: {from: todo}
  picked: {from: aside}
  built: {from: todo}
  ruled: {from: todo}
  asked: {from: todo}
  peeked: {from: todo}
goals:
  todo-low: {stock: todo, hold: "<= 0"}
  aside-low: {stock: aside, hold: "<= 0"}
items:
  ticket:
    id: ticket/*
    states: [new, done]
agents:
  ai: {kind: ai}
  small: {kind: narrow-ai}
  picker: {kind: decision, description: a short call}
blocks:
  work:
    type: ai
    agent: ai
    goal: todo-low
    prompt: prompts/work.md
    run: python3 bin/step.py work
    takes: {kind: ticket, at: new, to: [done]}
    out: flow.done
  inline:
    type: ai
    prompt: Sort the pile.
    run: "true"
    every: 1h
    out: flow.sorted
  narrow:
    type: ai
    agent: small
    prompt: Classify it.
    run: "true"
    every: 1h
    out: flow.classed
  pick:
    type: program
    agent: picker
    run: python3 bin/x.py
    every: 1h
    in: goal.aside-low.error
    out: flow.picked
  build: {type: program, run: python3 bin/x.py --fast, every: 1h, out: flow.built}
  ruler:
    type: program
    run: PY -m ergostat.library.run modelling rules
    every: 1h
    out: flow.ruled
  ex:
    type: expr
    in: {a: stock.todo}
    expr: "a * 2"
  lk:
    type: lookup
    in: block.ex
    table: {0: 0, 100: 10}
  approve:
    type: person
    ask: Is this ticket ready to ship?
    out: flow.asked
  peek:
    type: program
    run: python3 ../../etc/passwd /etc/hostname .ergostat/token bin/x.py
    every: 1h
    out: flow.peeked
"""


def project(tmp_path) -> Project:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "work.md").write_text("# Work\nDo the ticket.\n")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "step.py").write_text("print('step')\n")
    (tmp_path / "bin" / "x.py").write_text("print('x')\n")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace("PY", sys.executable))
    m = mdl.load(tmp_path)
    errors = [x for x in m.problems if x.level == "error"]
    assert not errors, errors
    return Project(m)


def spec_of(p, name):
    return api(Live(p), f"agents/{name}", {})["spec"]


def test_each_type_of_block_says_what_it_is(tmp_path):
    p = project(tmp_path)
    w = spec_of(p, "work")
    assert w["type"] == "ai" and w["implied"] is False and w["where"] == {"file": "ergostat.yaml", "line": w["where"]["line"]}
    assert w["source"].startswith("work:") and "prompt: prompts/work.md" in w["source"]
    assert w["params"]["takes"]["kind"] == "ticket" and w["params"]["run"] == "python3 bin/step.py work"
    assert {"name": "prompts/work.md", "role": "prompt", "format": "markdown"} in w["files"]
    assert {"name": "bin/step.py", "role": "wrapper", "format": "python"} in w["files"]
    assert w["prompt_text"] is None and w["machine"]["kind"] == "ai" and "declared ai" in w["rung_why"]
    assert w["law"]["says"] and w["law"]["rows"]
    assert spec_of(p, "inline")["prompt_text"] == "Sort the pile." and spec_of(p, "inline")["files"] == []
    assert spec_of(p, "narrow")["machine"]["kind"] == "narrow-ai"
    k = spec_of(p, "keep-todo-low")
    assert k["implied"] is True and k["implied_by"] == "work" and k["source"] is None and k["law"]["says"]
    assert k["params"]["goal"] == "todo-low" and "built-in onoff" in k["rung_why"]
    b = spec_of(p, "build")
    assert b["files"] == [{"name": "bin/x.py", "role": "program", "format": "python"}] and b["own"] is None
    assert spec_of(p, "ex")["params"]["expr"] == "a * 2" and spec_of(p, "ex")["law"]["says"]
    assert spec_of(p, "lk")["params"]["table"] == {0: 0, 100: 10}
    from ergostat.web.snapshot import _requests
    assert ("agents/work/files", {}) in _requests(p) and ("agents/work", {}) in _requests(p)
    a = spec_of(p, "approve")
    assert a["params"]["ask"] == "Is this ticket ready to ship?" and a["type"] == "person"


def test_ergostats_own_module_is_named_never_its_interpreter_path(tmp_path):
    p = project(tmp_path)
    r = spec_of(p, "ruler")
    assert r["own"]["module"] == "ergostat.library.run" and r["own"]["doc"]
    assert r["files"] == []
    text = json.dumps(api(Live(p), "agents/ruler", {})["spec"])
    assert sys.executable not in text and "/.venv/" not in text and str(tmp_path) not in text
    assert r["params"]["run"] == "python -m ergostat.library.run modelling rules"


def test_a_decision_agent_carries_its_decisions(tmp_path):
    p = project(tmp_path)
    for _ in range(3):
        p.events.add("controller.decided", item="aside-low", source="pick", data={"decision": "take 2"})
    d = spec_of(p, "pick")["decisions"]
    assert d["count"] == 3 and d["kinds"] == [["take #", 3]] and d["controllers"] == ["aside-low"]
    assert spec_of(p, "build")["decisions"] is None


def test_the_files_route_reads_only_inside_the_project(tmp_path, monkeypatch):
    (tmp_path / ".state").mkdir()
    p = Project(project(tmp_path).model, directory=tmp_path / ".state")   # the state inside the model folder
    (Path(p.dir) / "token").write_text("secret")
    state = os.path.relpath(Path(p.dir) / "token", tmp_path)
    p.model.spec.blocks["peek"].params["run"] = f"python3 ../../etc/passwd /etc/hostname {state} bin/x.py"
    read: list[Path] = []
    real = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: (read.append(self.resolve()), real(self, *a, **k))[1])
    got = api(Live(p), "agents/peek/files", {})["files"]
    by = {f["name"]: f for f in got}
    assert by["../../etc/passwd"]["why"] == "not shown: outside the project" and "text" not in by["../../etc/passwd"]
    assert by["hostname"]["why"] == "not shown: outside the project"
    assert by[state]["why"] == "not shown: outside the project" and "secret" not in json.dumps(got)
    assert {"name": state, "role": "program", "format": None, "why": "not shown: outside the project"} in spec_of(p, "peek")["files"]
    assert by["bin/x.py"]["text"] == "print('x')\n"
    assert all(r == tmp_path.resolve() / "bin" / "x.py" or "etc" not in r.parts for r in read)
    assert not any(r.name in ("passwd", "hostname", "token") for r in read)
    w = {f["name"]: f for f in api(Live(p), "agents/work/files", {})["files"]}
    assert w["prompts/work.md"]["text"].startswith("# Work") and w["bin/step.py"]["role"] == "wrapper"
    monkeypatch.setattr("ergostat.web.server.FILE_LIMIT", 5)
    assert api(Live(p), "agents/build/files", {})["files"][0]["why"] == "not shown: too big"
    assert api(Live(p), "agents/build/elsewhere", {}) is None and api(Live(p), "agents/nobody/files", {}) is None


def test_a_prompt_outside_the_project_is_said_never_taken_as_inline(tmp_path, monkeypatch):
    (tmp_path / ".state").mkdir()
    p = Project(project(tmp_path).model, directory=tmp_path / ".state")
    (Path(p.dir) / "token").write_text("secret")
    state = os.path.relpath(Path(p.dir) / "token", tmp_path)
    read: list[Path] = []
    real = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: (read.append(self.resolve()), real(self, *a, **k))[1])
    for prompt, name in (("../../etc/passwd", "../../etc/passwd"), ("/etc/hostname", "hostname"), (state, state)):
        p.model.spec.blocks["inline"].params["prompt"] = prompt
        got = spec_of(p, "inline")
        assert got["prompt_text"] is None, prompt
        assert {"name": name, "role": "prompt", "format": None, "why": "not shown: outside the project"} in got["files"]
        row = api(Live(p), "agents/inline/files", {})["files"][0]
        assert row["why"] == "not shown: outside the project" and "text" not in row
    assert not any(r.name in ("passwd", "hostname", "token") for r in read)
    p.model.spec.blocks["inline"].params["prompt"] = "Sort the pile."
    assert spec_of(p, "inline")["prompt_text"] == "Sort the pile." and spec_of(p, "inline")["files"] == []


def test_at_most_eight_files_are_listed(tmp_path):
    p = project(tmp_path)
    for i in range(12):
        (tmp_path / "bin" / f"f{i}.py").write_text("")
    from ergostat.web import agent_spec
    b = p.model.spec.blocks["build"]
    b.params["run"] = " ".join(f"bin/f{i}.py" for i in range(12))
    assert len(agent_spec.files(p, "build")["files"]) == agent_spec.MOST_FILES == 8


def copied(tmp_path, example: str) -> Project:
    shutil.copytree(ROOT / "examples" / example, tmp_path / example, ignore=shutil.ignore_patterns(".ergostat"))
    return Project(mdl.load(tmp_path / example))


def test_the_ticket_factory_work_block_and_its_implied_rule(tmp_path):
    p = copied(tmp_path, "ticket-factory")
    w = spec_of(p, "work")
    assert {"name": "prompts/work.md", "role": "prompt", "format": "markdown"} in w["files"]
    assert any(f["name"] == "bin/step.py" for f in w["files"]) and w["params"]["takes"]["kind"] == "ticket"
    k = spec_of(p, "keep-located-worked")
    assert k["implied"] is True and k["implied_by"] == "work" and k["law"]["says"]


@pytest.mark.serial
def test_an_agents_answer_is_quick(tmp_path):
    """The live demos' ports are not reachable here: the same answer on the ticket factory, median of 10."""
    p = copied(tmp_path, "ticket-factory")
    live = Live(p)
    for name in ("work", "keep-located-worked"):
        took = []
        for _ in range(10):
            t = time.perf_counter()
            api(live, f"agents/{name}", {})
            took.append(time.perf_counter() - t)
        assert statistics.median(took) < 0.3, (name, took)


def test_docs_fresh_fixer_and_page_picker(tmp_path):
    p = copied(tmp_path, "docs-fresh")
    fixer = next(n for n in p.model.agents if n.endswith("fixer"))
    text = json.dumps(api(Live(p), f"agents/{fixer}", {})["spec"])
    assert json.loads(text)["own"]["module"].startswith("ergostat.")
    assert "/.venv/" not in text and "/private/" not in text and sys.executable not in text
    d = spec_of(p, "page-picker")["decisions"]
    assert set(d) >= {"count", "kinds"}
