"""Calls from a step answered by the running engine over its socket (docs/proposals/latency.md): ``event --add``,
``act``, ``lease --renew`` and ``item ID --json`` from inside a run go to the engine (``ERGOSTAT_SOCKET``), answer as
they always did, and fall back to the old path when no engine listens; an ``act`` that waits for the owner is parked
and answered as soon as the owner answers; a command for another project is never answered by this engine."""

import json
import os
import shlex
import sys
import textwrap
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat.actions import gate
from ergostat.actions import record as rec
from ergostat.calls import client
from ergostat.calls.server import LIMIT, path_for
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

PY = shlex.quote(sys.executable)

MODEL = """
name: calls
items:
  job:
    id: job/*
    states: [ready, done]
    on: {job.arrived: ready, job.done: done}
actions:
  noop:
    run: "echo did it"
    gate: auto
  ask:
    run: "echo asked"
    gate: approve
blocks:
  probe:
    type: program
    run: {run}
    takes: {kind: job, at: ready, to: [done]}
    pool: 2
    actions: [noop, ask]
"""

PROBE = """
import json, os, shlex, subprocess, sys, time
cmd = shlex.split(os.environ["ERGOSTAT_CMD"])
item = os.environ["ERGOSTAT_ITEM"]
def run(*args):
    t = time.perf_counter()
    r = subprocess.run(cmd + list(args), capture_output=True, text=True)
    return {"code": r.returncode, "out": r.stdout, "err": r.stderr, "s": time.perf_counter() - t}
out = {"socket": os.environ.get("ERGOSTAT_SOCKET")}
out["event"] = run("event", "--add", "job.noted", "--item", item, "--data", json.dumps({"n": 1}), "--json")
out["renew"] = run("lease", "--renew", "--json")
out["act"] = run("act", "noop", "--json")
out["item"] = run("item", item, "--json")
out["bad"] = run("event", "--add", "agent.ran", "--item", item)
json.dump(out, open("probe-" + item.replace("/", "-") + ".json", "w"))
print(json.dumps({"event": "job.done"}))
"""


def project(tmp_path, run: str) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL.replace("{run}", json.dumps(run))))
    return Project(mdl.load(tmp_path))


def written(path):
    """The probe's JSON once it is whole: it is written in place, so it may be seen empty or half written."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def wait_for(cond, seconds=15.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.05)
    return cond()


@pytest.fixture
def engine(tmp_path):
    (tmp_path / "probe.py").write_text(PROBE)
    p = project(tmp_path, f"{PY} probe.py")
    e = Engine(p, say=lambda s: None)
    e.start_all()
    yield p, e
    e.close()


def test_a_steps_calls_are_answered_by_the_engine_over_its_socket(engine, tmp_path):
    p, e = engine
    assert e.socket and os.path.exists(e.socket)
    p.events.add("job.arrived", item="job/1", source="test")
    got = wait_for(lambda: written(tmp_path / "probe-job-1.json"))
    assert got["socket"] == e.socket
    assert got["event"]["code"] == 0 and json.loads(got["event"]["out"])["type"] == "job.noted"
    assert got["renew"]["code"] == 0 and json.loads(got["renew"]["out"])["type"] == "ergostat.lease.renewed"
    act = json.loads(got["act"]["out"])
    assert got["act"]["code"] == 0 and act["state"] == "ran" and act["output"].strip() == "did it"
    assert json.loads(got["item"]["out"])["id"] == "job/1"
    assert got["bad"]["code"] == 2 and "not ergostat's own" in got["bad"]["err"]
    assert e.calls.calls >= 4                                     # each went to the engine (the bad one, refused before)
    noted = p.events.query(n=None, type="job.noted")
    assert noted and noted[0]["causedby"] == p.events.query(n=None, type="ergostat.lease.taken")[0]["data"]["run"]
    assert wait_for(lambda: its.one(p.events, p.model.spec, "job/1").state == "done")


def test_an_act_that_waits_for_the_owner_is_answered_when_the_owner_answers(engine, tmp_path):
    p, e = engine
    cfg = tmp_path / "actions.json"
    cfg.write_text(json.dumps({"block": "probe", "run": "r1", "actions": ["noop", "ask"], "runner": "ergostat"}))
    got = {}

    def ask():
        got["a"] = client.call("act", path=e.socket, name="ask", args={}, wait=20.0, env={"ERGOSTAT_ACTIONS": str(cfg)})
    t = threading.Thread(target=ask)
    t.start()
    held = wait_for(lambda: [a for a in rec.stored(p).values() if a["state"] == "requested"])
    assert held and t.is_alive()                                   # parked: its call waits, no thread of the pool held
    began = time.monotonic()
    gate.approve(p, p.model.spec, held[0]["id"], by="owner")
    t.join(10)
    assert got["a"]["full"]["state"] == "ran" and got["a"]["exit"] == 0
    assert time.monotonic() - began < 3.0


def test_a_call_for_another_project_or_with_no_engine_is_not_answered_here(engine, tmp_path):
    p, e = engine
    with pytest.raises(client.Unavailable):
        client.call("ping", path=e.socket, root=str(tmp_path / "elsewhere"))
    assert client.call("ping", path=e.socket, root=str(tmp_path))["project"] == "calls"
    with pytest.raises(client.Unavailable):
        client.call("ping", path=str(tmp_path / "nobody.sock"))
    with pytest.raises(client.Refused) as no:
        client.call("lease", path=e.socket, how="renew", env={})
    assert no.value.code == 1 and "no lease here" in str(no.value)


def test_the_command_line_finds_the_engine_from_its_folder_and_falls_back_without_one(tmp_path, monkeypatch):
    from ergostat.cli import main
    (tmp_path / "probe.py").write_text("print('{\"event\": \"job.done\"}')")
    p = project(tmp_path, f"{PY} probe.py")
    monkeypatch.delenv("ERGOSTAT_SOCKET", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["event", "--add", "job.arrived", "--item", "job/7"]) == 0          # no engine: written as before
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        assert client.find(tmp_path) == e.socket
        before = e.calls.calls
        assert main(["event", "--add", "job.noted", "--item", "job/8", "--data", '{"x": 1}']) == 0
        assert e.calls.calls == before + 1
        assert p.events.query(n=None, type="job.noted")[0]["data"] == {"x": 1}
    finally:
        e.close()
    assert not os.path.exists(e.socket)
    assert client.find(tmp_path) is None


def test_a_state_directory_too_deep_for_a_socket_names_one_elsewhere(tmp_path):
    deep = tmp_path / ("d" * 120)
    assert len(str(path_for(deep))) <= LIMIT and path_for(deep).parent != deep
    assert path_for(tmp_path / "x") == tmp_path / "x" / "engine.sock" or len(str(tmp_path / "x" / "engine.sock")) > LIMIT
