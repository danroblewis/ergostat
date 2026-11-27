"""Gated actions asked for by a program block's run (SPEC §12k): ``$ERGOSTAT_CMD act NAME --arg K=V``. The gate takes
it as it takes a session's (auto, approve, deny), every answer an event; an auto or approved one is run by ergostat's
engine, with its environment, never by the program; the same request again is the same action (held, it is taken over
by the asking run's lease; ran, never run again); it is fenced by the lease; and a program block may work in its
item's workspace."""

import json
import sys
import textwrap
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import spec as spec_mod
from ergostat.actions import gate, program, record
from ergostat.cli import main as cli
from ergostat.leases import TAKEN
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

PY = sys.executable

MODEL = """
name: t
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        type: one of [open, review, done]
    events:
      ticket-review:
        when: type == 'ticket.review'
        '...': data
        state: set('review')
      ticket-done:
        when: type == 'ticket.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
    show: [title]
stocks:
  open-tickets:
    sensor: {projection: ticket, state: open, every: 5s}
flows:
  closed:
    from: open-tickets
    sensor: {projection: ticket, entering: done, over: 10m}
actions:
  note:
    run: "echo noted {text} secret=$SECRET >> noted.txt; echo noted {text} secret=$SECRET"
    gate: auto
    args: {text: what to note}
    in: .
  push:
    run: "echo pushed {branch} from $(pwd) >> {pushed}; echo pushed {branch}"
    gate: approve
    args: {pushed: where to say so}
  nuke:
    run: "touch nuked.txt"
    gate: deny
    in: .
blocks:
  step:
    type: program
    run: "true"
    actions: [note, push, nuke]
    every: 1h
"""


def project(tmp_path, model=MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(model))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [x.message for x in m.problems]
    return Project(m)


def cfg(tmp_path, p, **kw) -> dict:
    c = {"block": "step", "run": "run1", "item": "ticket/1", "lease": None, "workdir": str(tmp_path),
         "branch": "ticket/1-x", "actions": ["note", "push", "nuke"], "runner": "here", **kw}
    f = tmp_path / f"given-{c['run']}.json"
    f.write_text(json.dumps(c))
    return {**c, "file": str(f)}


def test_auto_runs_deny_never_and_the_request_is_checked(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET", "s3")
    p = project(tmp_path)
    spec = p.model.spec
    a = program.ask(p, spec, cfg(tmp_path, p), "note", {"text": "hi"})
    assert a["state"] == "ran" and a["output"] == "noted hi secret=s3" and a["asker"] == "program"
    assert a["deliveries"][0]["how"] == "run" and program.exit_code(a) == 0
    d = program.ask(p, spec, cfg(tmp_path, p), "nuke", {})
    assert d["state"] == "denied" and program.exit_code(d) == 4 and not (tmp_path / "nuked.txt").exists()
    with pytest.raises(program.AskError, match="no action 'rm'"):
        program.ask(p, spec, cfg(tmp_path, p), "rm", {})
    with pytest.raises(program.AskError, match="takes no colour"):
        program.ask(p, spec, cfg(tmp_path, p), "note", {"text": "x", "colour": "red"})
    with pytest.raises(program.AskError, match="needs text"):
        program.ask(p, spec, cfg(tmp_path, p, run="run2"), "note", {})
    with pytest.raises(program.AskError, match="no action 'nuke' for block step"):
        program.ask(p, spec, cfg(tmp_path, p, actions=["note"]), "nuke", {})


def test_the_same_request_is_the_same_action_held_once_and_run_once(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    out = str(tmp_path / "pushed.txt")
    a = program.ask(p, spec, cfg(tmp_path, p), "push", {"pushed": out})
    assert a["state"] == "requested" and program.exit_code(a) == 3 and not Path(out).exists()
    again = program.ask(p, spec, cfg(tmp_path, p, run="run2"), "push", {"pushed": out})
    assert again["id"] == a["id"], "asked again: the same action, still held"
    other = program.ask(p, spec, cfg(tmp_path, p, item="ticket/2"), "push", {"pushed": out})
    assert other["id"] != a["id"], "another item's is its own"
    gate.approve(p, spec, a["id"])                                   # no one waits: it runs at the owner's approval
    got = program.ask(p, spec, cfg(tmp_path, p, run="run3"), "push", {"pushed": out})
    assert got["id"] == a["id"] and got["state"] == "ran" and got["output"] == "pushed ticket/1-x"
    got = program.ask(p, spec, cfg(tmp_path, p, run="run4"), "push", {"pushed": out})
    assert Path(out).read_text().count("pushed") == 1, "never run twice"
    assert [d["run"] for d in got["deliveries"]] == ["run3", "run4"]
    gate.deny(p, other["id"])                                         # the owner's denial stands
    assert program.ask(p, spec, cfg(tmp_path, p, item="ticket/2", run="run5"), "push", {"pushed": out})["id"] == other["id"]
    keyed = [program.ask(p, spec, cfg(tmp_path, p, item=None, run=f"k{i}"), "note", {"text": "daily"}, key="day-1")
             for i in range(2)]
    assert keyed[0]["id"] == keyed[1]["id"], "no item: the same --key is the same act"
    loose = [program.ask(p, spec, cfg(tmp_path, p, item=None, run=f"l{i}"), "note", {"text": "daily"}) for i in range(2)]
    assert loose[0]["id"] != loose[1]["id"], "no item and no key: each run's own"


def test_a_gate_promoted_from_deny_asks_anew_and_a_failure_is_asked_anew(tmp_path):
    p = project(tmp_path)
    assert program.ask(p, p.model.spec, cfg(tmp_path, p), "nuke", {})["state"] == "denied"
    y = tmp_path / "ergostat.yaml"
    y.write_text(y.read_text().replace('run: "touch nuked.txt"\n    gate: deny', 'run: "touch nuked.txt; exit 3"\n    gate: auto'))
    p = Project(mdl.load(tmp_path))
    a = program.ask(p, p.model.spec, cfg(tmp_path, p), "nuke", {})
    assert a["state"] == "failed" and a["exit"] == 3 and program.exit_code(a) == 1
    b = program.ask(p, p.model.spec, cfg(tmp_path, p, run="r2"), "nuke", {})
    assert b["id"] != a["id"] and b["state"] == "failed", "a failure is tried again, as a new action"


def test_it_is_fenced_by_the_lease_and_taken_over_by_the_next(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    out = str(tmp_path / "pushed.txt")
    p.events.add("ticket.opened", item="ticket/1", source="watch", data={"title": "x"})

    def lease(fence, run):
        p.events.add(TAKEN, item="ticket/1", source="ergostat", data={"item": "ticket/1", "run": run, "block": "step",
                     "fence": fence, "ttl": 300, "max": 3, "back": "open", "tier": "program", "attempt": fence})
        p.events.add("ergostat.lease.ended", item="ticket/1", source="ergostat", causedby=run,
                     data={"run": run, "fence": fence, "how": "nack", "why": "waits", "count": False})
    lease(1, "r1")
    a = program.ask(p, spec, cfg(tmp_path, p, run="r1", lease=1), "push", {"pushed": out})
    assert a["state"] == "requested" and a["lease"] == 1
    lease(2, "r2")
    stale = program.ask(p, spec, cfg(tmp_path, p, run="r1", lease=1), "note", {"text": "late"})
    assert stale["state"] == "denied" and "fenced" in stale["note"], "a run whose lease is over is refused"
    b = program.ask(p, spec, cfg(tmp_path, p, run="r2", lease=2), "push", {"pushed": out})
    assert b["id"] == a["id"] and b["fence"] == 2 and b["run"] == "r2", "taken over by the later lease"
    assert p.events.query(n=None, item=a["id"], type="ergostat.action.reasked")
    assert gate.approve(p, spec, a["id"])["state"] == "ran", "approved: runs, under the lease that asked last"


def test_the_cli_exits_by_how_the_gate_took_it(tmp_path, monkeypatch, capsys):
    p = project(tmp_path)
    c = cfg(tmp_path, p)
    monkeypatch.setenv("ERGOSTAT_ACTIONS", c["file"])
    monkeypatch.setenv("ERGOSTAT_RUN", "run1")
    monkeypatch.setenv("SECRET", "s3")
    assert cli(["-C", str(tmp_path), "act", "note", "--arg", "text=hello world"]) == 0
    got = capsys.readouterr()
    assert got.out.strip() == "noted hello world secret=s3" and "ran" in got.err
    assert cli(["-C", str(tmp_path), "act", "push", "--arg", f"pushed={tmp_path / 'x'}"]) == 3
    assert "held for the owner's approval" in capsys.readouterr().err
    assert cli(["-C", str(tmp_path), "act", "nuke"]) == 4
    capsys.readouterr()
    assert cli(["-C", str(tmp_path), "act", "nuke", "--json"]) == 4
    assert json.loads(capsys.readouterr().out)["state"] == "denied"
    assert cli(["-C", str(tmp_path), "act", "rm"]) == 2
    monkeypatch.setenv("ERGOSTAT_RUN", "someone-else")
    assert cli(["-C", str(tmp_path), "act", "note", "--arg", "text=x"]) == 2
    assert "not this run's" in capsys.readouterr().err


def test_program_blocks_may_name_actions_and_a_workspace_and_are_checked(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        name: t
        actions:
          a: {run: "x"}
        blocks:
          ok: {type: program, run: "true", actions: [a], every: 1h}
          bad: {type: program, run: "true", actions: [b], workspace: code, every: 1h}
          sess: {type: program, run: "true", tools: [Read], every: 1h}
          wrapped: {type: ai, prompt: w, run: ./wrap.sh, actions: [a], every: 1h}
    """))
    msgs = [x.message for x in spec_mod.read(tmp_path / "ergostat.yaml")[1] if x.level == "error"]
    assert any("block bad.actions: 'b'" in m for m in msgs) and any("block bad.workspace" in m for m in msgs)
    assert any("tools" in m and "sess" in m for m in msgs)
    assert not any("block ok" in m or "wrapped" in m for m in msgs), msgs


def test_a_held_result_goes_to_the_next_run_on_the_same_item_only(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    a = program.ask(p, spec, cfg(tmp_path, p), "push", {"pushed": str(tmp_path / "x")})
    gate.approve(p, spec, a["id"])
    assert gate.for_context(p, "step", "r9", item="ticket/2") == []
    got = gate.for_context(p, "step", "r9", item="ticket/1")
    assert [x["id"] for x in got] == [a["id"]] and got[0]["state"] == "ran"


LEASED = MODEL.replace("""blocks:
  step:
    type: program
    run: "true"
    actions: [note, push, nuke]
    every: 1h
""", """workspaces:
  code: {repo: product, pool: pool, size: 1, branch: "{kind}/{id}-{slug}", base: main}
blocks:
  step:
    type: program
    takes: {projection: ticket, at: open, to: review}
    lease: {ttl: 5m, attempts: 3}
    workspace: code
    actions: [note, push]
    run: "env -u SECRET {py} step.py"
""")

# The step: notes (auto: run by the engine, which has SECRET; the step has not), asks for the push (approve: held for
# the owner), gives the ticket back while it waits, and once the push has run moves the ticket to review.
STEP = """
import json, os, subprocess, sys
sys.stdin.read()
cmd = os.environ["ERGOSTAT_CMD"]
def act(*a):
    r = subprocess.run(cmd + " act " + " ".join(a), shell=True, capture_output=True, text=True)
    return r.returncode, r.stdout.strip()
seen = {{"cwd": os.getcwd(), "ws": os.environ.get("ERGOSTAT_WORKSPACE"), "secret": os.environ.get("SECRET"),
        "note": act("note", "--arg", "text=hi"), "push": act("push", "--arg", "pushed={pushed}")}}
open({log!r}, "a").write(json.dumps(seen) + "\\n")
if seen["push"][0] == 0:
    print(json.dumps({{"event": "ticket.review"}}))
else:
    print(json.dumps({{"nack": {{"why": "waits for the push", "after": "1s", "count": False}}}}))
"""


def test_in_a_running_engine_the_engine_runs_them_with_its_environment_in_the_items_workspace(tmp_path, monkeypatch):
    from tests.test_leased_workspaces import make_repo, wait_for
    monkeypatch.setenv("SECRET", "s3")
    make_repo(tmp_path / "product")
    log, pushed = tmp_path / "runs.jsonl", tmp_path / "pushed.txt"
    (tmp_path / "step.py").write_text(textwrap.dedent(STEP.format(log=str(log), pushed=str(pushed))))
    p = project(tmp_path, LEASED.replace("{py}", PY))
    spec = p.model.spec
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        p.events.add("ticket.opened", item="ticket/1", source="watch", data={"title": "Fix it"})
        held = wait_for(lambda: [a for a in record.stored(p).values() if a["action"] == "push"])
        assert held and held[0]["state"] == "requested"
        assert cli(["-C", str(tmp_path), "actions", record.short(held[0]["id"]), "--approve"]) == 0
        assert wait_for(lambda: its.one(p.events, spec, "ticket/1").state == "review", 20)
    finally:
        e.close()
    runs = [json.loads(x) for x in log.read_text().splitlines()]
    ws = str((tmp_path / "pool" / "1").resolve())
    assert all(r["cwd"] == str(tmp_path) and r["ws"] == ws and r["secret"] is None for r in runs)
    assert runs[0]["note"] == [0, "noted hi secret=s3"], "run by the engine, with its environment, not the step's"
    assert runs[0]["push"][0] == 3 and runs[-1]["push"] == [0, "pushed ticket/1-fix-it"]
    assert (tmp_path / "noted.txt").read_text().count("noted") == 1, "the same note asked by every run: run once"
    assert pushed.read_text() == f"pushed ticket/1-fix-it from {ws}\n", "in the item's workspace, once"
    notes = [a for a in record.stored(p).values() if a["action"] == "note"]
    assert len(notes) == 1 and notes[0]["asker"] == "program" and notes[0]["approved_by"] == "gate"


def test_a_full_pool_puts_the_item_off_uncounted(tmp_path):
    from ergostat.leases import ENDED
    from ergostat.workspaces import pool as pl
    from tests.test_leased_workspaces import make_repo, wait_for
    make_repo(tmp_path / "product")
    (tmp_path / "step.py").write_text("print('{}')\n")
    p = project(tmp_path, LEASED.replace("{py}", PY))
    spec = p.model.spec
    p.events.add("ticket.opened", item="ticket/9", source="watch", data={"title": "Other"})
    pl.acquire(p, spec, "code", "ticket/9", {"title": "Other"}, "r9", None)   # the only workspace, someone else's
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        p.events.add("ticket.opened", item="ticket/1", source="watch", data={"title": "Fix it"})
        ended = wait_for(lambda: p.events.query(n=None, type=ENDED, item="ticket/1"))
    finally:
        e.close()
    d = ended[0]["data"]
    assert d["how"] == "nack" and d["count"] is False and d["after"] == 10.0 and "none free" in d["why"]
    it = its.one(p.events, spec, "ticket/1")
    assert it.state == "open" and it.fields["lease"]["attempts"] == 0
    assert not p.events.query(n=None, type="agent.failed", item="step"), "a full pool is not the run's failure"


def test_a_workspace_items_lease_number_folds_as_plain_data(tmp_path):
    p = project(tmp_path)
    for n, lease in enumerate([1, 1, 2, None], 1):
        p.events.add("ergostat.workspace.acquired", item="ergostat.workspace/code-1", source="ergostat",
                     data={"item": "ticket/1", "lease": lease, "n": n})
    it = its.one(p.events, p.model.spec, "ergostat.workspace/code-1")
    assert it.fields["lease"] is None and it.fields["n"] == 4, "each event's lease, as it said it"
