"""Leases (SPEC §9.5) and workspaces (SPEC §12k) together, end to end, in a running engine: a block that takes items
with ``workspace:`` leases an item and works in its own worktree; given back (nack), it gets the same worktree on the
retry, its work in progress with it; moved on to review, the workspace is held for it; done, it is cleaned. A gated
action its session asked for is held for the owner's approval, runs after it, and is fenced once a later lease is
taken on its item."""

import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat.actions import gate, record
from ergostat.leases import ENDED, EXPIRED, TAKEN
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project
from ergostat.workspaces import leases as wl
from ergostat.workspaces import pool as pl

PY = sys.executable

MODEL = """
name: t
items:
  ticket:
    id: ticket/*
    states: [open, review, done]
    on: {ticket.review: review, ticket.done: done}
    show: [title]
stocks:
  open-tickets:
    sensor: {items: ticket, state: open, every: 5s}
flows:
  closed:
    from: open-tickets
    sensor: {items: ticket, entering: done, over: 10m}
workspaces:
  code:
    repo: product
    pool: pool
    size: 2
    branch: "{kind}/{id}-{slug}"
    base: main
actions:
  push:
    run: "echo pushed {branch} >> pushed.txt; echo pushed {branch}"
    gate: approve
    wait: 1s
    in: .
blocks:
  dev:
    type: ai
    prompt: "Fix it."
    takes: {kind: ticket, at: open, to: review}
    lease: {ttl: 5m, attempts: 3}
    workspace: code
    tools: [Read, Edit, Bash]
    actions: [push]
"""

# A stand-in for ``claude -p`` in the session's folder. Its first attempt leaves work in progress, uncommitted, and gives
# the item back; its second finds that work where it left it, commits it, asks for the push through the session's MCP
# server (the gate holds it for the owner), and moves the item to review.
SESSION = """
import json, os, subprocess, sys
sys.stdin.read()
log = {log!r}
here = os.getcwd()
cfg = json.load(open(os.environ["ERGOSTAT_SANDBOX"]))
seen = {{"cwd": here, "item": os.environ.get("ERGOSTAT_ITEM"), "lease": os.environ.get("ERGOSTAT_LEASE"),
        "branch": os.environ.get("ERGOSTAT_BRANCH"), "found": os.path.exists("work.txt"), "cfg_lease": cfg.get("lease")}}
if not seen["found"]:
    open("work.txt", "w").write("half done\\n")
    print(json.dumps({{"nack": "not finished: more to do"}}))
else:
    git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "add", "work.txt"], check=True)
    subprocess.run([*git, "commit", "-qm", "the fix"], check=True)
    from ergostat.actions.server import Server
    got = Server(cfg, session="session/dev-x").call("push", {{}})
    seen["push"] = json.loads(got["content"][0]["text"])
    print(json.dumps({{"event": "ticket.review"}}))
open(log, "a").write(json.dumps(seen) + "\\n")
"""


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def make_repo(d: Path) -> Path:
    d.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=d)
    (d / "app.py").write_text("print('hi')\n")
    git("add", "app.py", cwd=d)
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init", cwd=d)
    return d


def wait_for(cond, seconds=15.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.05)
    return cond()


def slot(p, n=1) -> dict:
    spec = p.model.spec
    return pl.slots(p, spec, spec.workspaces["code"])[n]


def test_a_leased_item_keeps_its_workspace_through_a_retry_and_review_and_it_is_cleaned_at_done(tmp_path, monkeypatch):
    import ergostat.spec.engine as eng
    make_repo(tmp_path / "product")
    log = tmp_path / "sessions.jsonl"
    fake = tmp_path / "fake-claude.py"
    fake.write_text(textwrap.dedent(SESSION.format(log=str(log))))
    monkeypatch.setattr(eng, "AI_COMMAND", f"{PY} {fake}")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], m.problems
    p = Project(m)
    spec = p.model.spec
    ws = (tmp_path / "pool" / "1").resolve()

    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        p.events.add("ticket.opened", item="ticket/1", source="watch", data={"title": "Fix the login page"})
        assert wait_for(lambda: its.one(p.events, spec, "ticket/1").state == "review"), "leased, retried, moved on"
        assert wait_for(lambda: len(p.events.query(n=None, type=ENDED, item="ticket/1")) == 2)
        assert wait_for(lambda: slot(p)["state"] == "held")
    finally:
        e.close()

    runs = [json.loads(x) for x in log.read_text().splitlines()]
    assert len(runs) == 2
    first, second = runs
    assert first["cwd"] == second["cwd"] == str(ws), "the same worktree on the retry"
    assert first["branch"] == second["branch"] == "ticket/1-fix-the-login-page"
    assert (first["item"], first["lease"], first["found"]) == ("ticket/1", "1", False)
    assert (second["item"], second["lease"], second["found"]) == ("ticket/1", "2", True), "its work as it left it"
    assert second["cfg_lease"] == 2

    taken = p.events.query(n=None, type=TAKEN, item="ticket/1")
    ended = p.events.query(n=None, type=ENDED, item="ticket/1")
    assert [t["data"]["fence"] for t in taken] == [1, 2]
    assert [(x["data"]["how"], x["data"]["state"], x["data"]["terminal"]) for x in ended] == \
        [("nack", "open", False), ("ack", "review", False)]
    held = [x for x in p.events.query(n=None, type="ergostat.workspace.*") if x["data"].get("item") == "ticket/1"]
    assert [x["type"].rsplit(".", 1)[1] for x in held] == ["acquired", "held", "acquired", "held"], \
        "acquired once per lease, held between (no event twice for one lease)"
    assert [x["data"].get("lease") for x in held] == [1, 1, 2, 2]
    assert held[1]["causedby"] == ended[0]["id"] and held[3]["causedby"] == ended[1]["id"], "released by the lease's end"
    s = slot(p)
    assert s["state"] == "held" and s["item"] == "ticket/1" and s["lease"] == 2, "kept while its item is in review"
    assert git("log", "-1", "--format=%s", cwd=ws) == "the fix"

    # the push its session asked for: held for the owner (its wait ran out), then approved, and run
    push = second["push"]
    assert push["state"] == "requested" and "held for the owner" in push["note"]
    a = record.get(p, push["id"])
    assert a["state"] == "requested" and a["lease"] == 2 and a["item"] == "ticket/1" and a["run"] == taken[1]["data"]["run"]
    assert not (tmp_path / "pushed.txt").exists(), "nothing ran before the owner approved it"
    a = gate.approve(p, spec, push["id"])
    assert a["state"] == "ran" and a["output"] == "pushed ticket/1-fix-the-login-page"
    assert (tmp_path / "pushed.txt").read_text().strip() == "pushed ticket/1-fix-the-login-page"

    # done: the workspace is cleaned (by the engine's clock, which sweeps the pools), its branch left in the repository
    p.events.add("ticket.done", item="ticket/1", source="owner")
    assert wl.finished(p, spec, "ticket/1")
    wl.sweep(p, spec, e.lease_seq)
    s = slot(p)
    assert s["state"] == "free" and pl.counts(p, spec)["held"] == 0
    assert git("rev-parse", "--abbrev-ref", "HEAD", cwd=ws) == "HEAD"
    assert git("branch", "--list", "ticket/1-fix-the-login-page", cwd=tmp_path / "product")

    # an action asked for under the first lease, after the second was taken: fenced, never run
    late = gate.request(p, spec, "push", {}, {"block": "dev", "run": taken[0]["data"]["run"], "item": "ticket/1",
                                              "workdir": str(ws), "branch": "ticket/1-fix-the-login-page", "lease": "1"})
    assert late["state"] == "denied" and "fenced" in late["note"]


def test_a_lease_that_expires_while_its_run_goes_on_fences_its_workspace(tmp_path):
    make_repo(tmp_path / "product")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    p = Project(mdl.load(tmp_path))
    spec = p.model.spec
    p.events.add("ticket.opened", item="ticket/2", source="watch", data={"title": "Slow"})
    e = Engine(p, say=lambda s: None)
    b = spec.blocks["dev"]
    it = its.one(p.events, spec, "ticket/2")
    run = "r" * 32
    ev = p.events.add(TAKEN, item="ticket/2", source="ergostat",
                      data={"item": "ticket/2", "run": run, "block": "dev", "fence": 1, "ttl": 1, "max": 3, "back": "open"})
    p.events.add("agent.started", item="dev", source="ergostat", id=run, causedby=ev["id"], data={"item": "ticket/2"})
    got = pl.acquire(p, spec, "code", it.id, {"title": "Slow"}, run=run, lease=1)
    assert slot(p)["state"] == "in-use"
    asked = gate.request(p, spec, "push", {}, {"block": "dev", "run": run, "item": "ticket/2", "workdir": got["dir"],
                                               "branch": got["branch"], "lease": 1})
    assert asked["state"] == "requested"
    e.dispatch.watch(now=time.time() + 5)                          # silent past its TTL: expired, its run still going
    exp = p.events.query(n=None, type=EXPIRED, item="ticket/2")
    assert exp and exp[-1]["data"]["terminal"] is False
    s = slot(p)
    assert s["state"] == "held" and s["fenced"] == {"run": run, "fence": 1} and "fenced" in s["why"]
    a = gate.approve(p, spec, asked["id"])                         # approved too late: its lease is over
    assert a["state"] == "failed" and "fenced" in a["output"]
    assert not (tmp_path / "pushed.txt").exists()
    again = pl.acquire(p, spec, "code", "ticket/2", {}, run="s" * 32, lease=2)
    assert again["dir"] == got["dir"] and slot(p)["lease"] == 2, "the next lease takes the same workspace"
    p.events.add(ENDED, item="ticket/2", source="ergostat", causedby=run,                 # the old run's end, late
                 data={"item": "ticket/2", "run": run, "fence": 1, "how": "ack", "state": "done", "terminal": True})
    wl.sweep(p, spec)
    assert slot(p)["state"] == "in-use" and slot(p)["lease"] == 2, "an older lease's end changes nothing"
    assert b.takes.kind == "ticket"
