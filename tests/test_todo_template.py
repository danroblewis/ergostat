"""``use: todo``: a person's own to-dos, with instructions, grouped by where they must be done (dev/records/
manual-todo-template.md): the batches by place, waiting on another to-do or on someone else, the status ``ergostat why``
gives a stakeholder, and that the template adds nothing that acts outside ergostat."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import textwrap
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat.library.expand import LIB
from ergostat.library.run import todo
from ergostat.spec import items as its
from ergostat.spec import read
from ergostat.store import Project
from ergostat.why import answer
from ergostat.why.words import summary

NOW = time.time()
UP = {"running": True, "pid": None, "beat": NOW, "said": "up"}
MODEL = """
name: t
uses:
  todo:
    use: todo
"""


def project(tmp_path, monkeypatch, text=MODEL) -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def add(p, iid, event, at, **data):
    p.events.add(event, item=iid, source="user", at=NOW - at, data=data)


def batcher(p, capsys, record=True) -> list[dict]:
    """One pass of the batcher, as its block runs it; what it says is recorded, as the engine records a block's lines."""
    assert todo.main(["batches", "--kind", "todo", "--batch-kind", "todo-batch", "--met", "done,answered",
                      "--flow", "flow.todo-freed"]) == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    for x in lines:
        if record and "event" in x:
            p.events.add(x["event"], item=x["item"], source="todo-batcher", data=x["data"])
    return lines


CERT = [{"do": "Open the certificate folder", "run": "cd /etc/ssl/site", "check": "ls shows site.pem"},
        {"do": "Renew it", "run": "renew-cert site", "check": "expiry is next year"}]


def three_places(p):
    add(p, "todo/cert", "todo.ready", 500, title="Renew the site certificate", where="bastion-a", due="2026-12-01",
        requester="Sam", instructions=CERT)
    add(p, "todo/logs", "todo.ready", 400, title="Rotate the logs", where="bastion-a", due="2026-11-28",
        instructions=["sudo logrotate -f /etc/logrotate.conf"])
    add(p, "todo/lab", "todo.ready", 300, title="Reset the lab switch", where="VPN: lab")
    add(p, "todo/note", "todo.ready", 200, title="Write the hand-over note")          # no place: anywhere
    add(p, "todo/later", "todo.added", 100, title="Not written up yet", where="bastion-a")


# ---- the batches

def test_ready_todos_are_grouped_by_where_each_in_the_order_to_do_them(tmp_path, monkeypatch, capsys):
    p = project(tmp_path, monkeypatch)
    three_places(p)
    said = {x["item"]: x for x in batcher(p, capsys) if "event" in x}
    lab = [k for k in said if k.startswith("todo-batch/vpn-lab-")]
    assert set(said) == {"todo-batch/bastion-a", "todo-batch/anywhere", *lab} and len(lab) == 1, said
    a = said["todo-batch/bastion-a"]["data"]
    assert a["todos"] == ["todo/logs", "todo/cert"], "the earliest due first; a new to-do is not ready"
    assert a["count"] == 2 and a["due"] == "2026-11-28" and a["where"] == "bastion-a"
    text = a["sitting"]
    assert text.index("todo/logs") < text.index("todo/cert") < text.index("1. Open the certificate folder") \
        < text.index("$ cd /etc/ssl/site") < text.index("check: ls shows site.pem") < text.index("2. Renew it")
    assert "(for Sam, due 2026-12-01)" in text and "Not written up yet" not in text
    assert said[lab[0]]["data"]["where"] == "VPN: lab" and said["todo-batch/anywhere"]["data"]["todos"] == ["todo/note"]
    it = {i.id: i for i in its.project(p.events, p.model.spec)}
    assert it["todo-batch/bastion-a"].state == "open"


def test_a_batch_is_said_again_only_when_it_changes_and_cleared_once_done(tmp_path, monkeypatch, capsys):
    p = project(tmp_path, monkeypatch)
    three_places(p)
    batcher(p, capsys)
    assert [x for x in batcher(p, capsys) if "event" in x] == [], "a batch as the record has it is not said again"
    add(p, "todo/logs", "todo.done", 50)
    add(p, "todo/cert", "todo.started", 40)
    got = {x["item"]: x for x in batcher(p, capsys) if "event" in x}
    assert list(got) == ["todo-batch/bastion-a"] and got["todo-batch/bastion-a"]["data"]["todos"] == ["todo/cert"]
    assert "(for Sam, due 2026-12-01, in-progress)" in got["todo-batch/bastion-a"]["data"]["sitting"]
    add(p, "todo/cert", "todo.done", 30)
    got = {x["item"]: x for x in batcher(p, capsys) if "event" in x}
    assert got["todo-batch/bastion-a"]["event"] == "todo-batch.cleared"
    assert got["todo-batch/bastion-a"]["data"]["todos"] == [] and got["todo-batch/bastion-a"]["data"]["count"] == 0
    add(p, "todo/later", "todo.ready", 20, instructions=["do it"])         # the same place again: the same id, made anew
    got = {x["item"]: x for x in batcher(p, capsys) if "event" in x}
    d = got["todo-batch/bastion-a"]["data"]
    assert got["todo-batch/bastion-a"]["event"] == "todo-batch.grouped" and d["todos"] == ["todo/later"] and d["due"] is None


def test_places_written_alike_never_share_a_batch():
    assert todo.key_of("bastion-a") == "bastion-a"
    keys = {todo.key_of(w) for w in ("VPN lab", "vpn-lab", "vpn lab", "VPN: lab")}
    assert len(keys) == 4 and all(k.startswith("vpn-lab") for k in keys)
    assert todo.key_of("¿?").startswith("place-")


def test_instructions_that_cannot_be_read_are_said_not_dropped(tmp_path, monkeypatch, capsys):
    p = project(tmp_path, monkeypatch)
    add(p, "todo/x", "todo.ready", 10, title="x", where="h", instructions="not a list")
    add(p, "todo/y", "todo.ready", 5, title="y", where="h")
    text = batcher(p, capsys)[0]["data"]["sitting"]
    assert "its instructions cannot be read" in text and "(no instructions written)" in text


# ---- waiting

def test_a_waiting_todo_is_freed_once_everything_it_waits_on_is_finished(tmp_path, monkeypatch, capsys):
    p = project(tmp_path, monkeypatch)
    add(p, "todo/access", "todo.ready", 300, title="Ask for access", where="anywhere")
    add(p, "todo-wait/sign-off", "todo-wait.asked", 290, title="Security's sign-off", who="the security team")
    add(p, "todo/open", "todo.waiting", 280, title="Open the port", where="bastion-b",
        waits_on=["todo/access", "todo-wait/sign-off"])
    add(p, "todo/ghost", "todo.waiting", 270, title="Waits on nothing recorded", waits_on="todo-wait/never")
    add(p, "todo/bare", "todo.waiting", 260, title="Waits on nothing named")
    lines = batcher(p, capsys)
    assert not [x for x in lines if x.get("event") == "todo.freed"] and {"out": "flow.todo-freed", "moved": 0} in lines
    assert all(x["item"] != "todo-batch/bastion-b" for x in lines if "event" in x), "a waiting to-do is in no batch"
    add(p, "todo/access", "todo.done", 200)
    assert not [x for x in batcher(p, capsys) if x.get("event") == "todo.freed"], "one of the two is still unanswered"
    add(p, "todo-wait/sign-off", "todo-wait.answered", 100)
    lines = batcher(p, capsys)
    assert [x["item"] for x in lines if x.get("event") == "todo.freed"] == ["todo/open"]
    assert {"out": "flow.todo-freed", "moved": 1} in lines
    assert [x["data"]["todos"] for x in batcher(p, capsys) if x.get("item") == "todo-batch/bastion-b"] == [["todo/open"]]


def test_a_todo_whose_prerequisite_was_dropped_stays_waiting_and_says_why(tmp_path, monkeypatch, capsys):
    """Dropped is finished but did not happen: the person is not sent to a place they cannot reach."""
    p = project(tmp_path, monkeypatch)
    add(p, "todo/access", "todo.ready", 300, title="Request access to build-host")
    add(p, "todo/clean", "todo.waiting", 290, title="Clean the cache", where="build-host", waits_on="todo/access")
    add(p, "todo/access", "todo.dropped", 200, notes="access refused")
    lines = batcher(p, capsys)
    assert not [x for x in lines if x.get("event") == "todo.freed"] and {"out": "flow.todo-freed", "moved": 0} in lines
    assert all(x["item"] != "todo-batch/build-host" for x in lines if "event" in x)
    stuck = [x for x in lines if x.get("event") == "todo.stuck"]
    assert [x["item"] for x in stuck] == ["todo/clean"] and "todo/access ended dropped" in stuck[0]["data"]["stuck"]
    assert [x for x in batcher(p, capsys) if "event" in x] == [], "said once, not every pass"
    c = {i.id: i for i in its.project(p.events, p.model.spec)}["todo/clean"]
    assert c.state == "waiting" and "todo/access ended dropped" in c.fields["stuck"]
    w = why(p, "todo/clean")
    assert not w["done"] and w["root"]["kind"] == "work" and w["root"]["item"] == "todo/clean"
    assert "what it waits on is finished (todo/access); stuck: todo/access ended dropped" in w["summary"], w["summary"]
    next_is_ready(w, "todo/clean")
    add(p, "todo/access2", "todo.done", 100)                     # waited again, on a new prerequisite, which happened
    add(p, "todo/clean", "todo.waiting", 90, waits_on={"set": ["todo/access2"]})
    lines = batcher(p, capsys)
    assert [x["item"] for x in lines if x.get("event") == "todo.freed"] == ["todo/clean"]
    c = {i.id: i for i in its.project(p.events, p.model.spec)}["todo/clean"]
    assert c.state == "ready" and c.fields["stuck"] is None


def test_a_todo_waiting_again_is_not_freed_by_the_wait_it_had_before(tmp_path, monkeypatch, capsys):
    """The same to-do waits a second time with only a note: the earlier, finished waits_on is not this wait."""
    p = project(tmp_path, monkeypatch)
    add(p, "todo/a", "todo.ready", 300, title="a")
    add(p, "todo/b", "todo.waiting", 290, title="b", waits_on="todo/a")
    add(p, "todo/a", "todo.done", 280)
    assert [x["item"] for x in batcher(p, capsys) if x.get("event") == "todo.freed"] == ["todo/b"]
    add(p, "todo/b", "todo.waiting", 100, notes="waiting on a phone call")
    for _ in range(2):
        lines = batcher(p, capsys)
        assert not [x for x in lines if x.get("event") == "todo.freed"], lines
    b = {i.id: i for i in its.project(p.events, p.model.spec)}["todo/b"]
    assert b.state == "waiting" and b.fields["waits_on"] == ["todo/a"]
    assert b.fields["stuck"].startswith("nothing it waits on was named when it last entered waiting")
    w = why(p, "todo/b")
    assert "stuck: nothing it waits on was named when it last entered waiting or since" in w["summary"], w["summary"]
    next_is_ready(w, "todo/b")
    add(p, "todo/b", "todo.noted", 50, waits_on="todo/c")           # a wait named after it entered waiting counts
    add(p, "todo/c", "todo.done", 40)
    lines = batcher(p, capsys)
    assert [x["item"] for x in lines if x.get("event") == "todo.freed"] == ["todo/b"]


def next_is_ready(w, iid):
    """A waiting to-do with nothing unfinished to wait on: next, record it ready, never re-added nor the batcher's."""
    assert w["next"]["owner"] == "whoever records todo.ready", w["next"]
    assert w["next"]["command"] == f"ergostat event --add todo.ready --item {iid}"
    assert "todo.added" not in w["summary"] and "(`ergostat event --add todo.ready" in w["summary"], w["summary"]


def test_a_todo_waiting_on_nothing_named_says_so_and_what_happens_next(tmp_path, monkeypatch, capsys):
    p = project(tmp_path, monkeypatch)
    add(p, "todo/n", "todo.waiting", 300, title="Wait for the window")
    assert not [x for x in batcher(p, capsys) if x.get("event") == "todo.freed"]
    w = why(p, "todo/n")
    assert w["root"]["kind"] == "work" and "it waits on nothing recorded; stuck: nothing it waits on was named" \
        in w["summary"], w["summary"]
    next_is_ready(w, "todo/n")


def test_a_todo_dropped_while_the_batcher_frees_it_stays_dropped(tmp_path, monkeypatch, capsys):
    """The person's drop lands between the batcher's read and its write: the freeing moves only out of waiting."""
    p = project(tmp_path, monkeypatch)
    add(p, "todo/a", "todo.ready", 300, title="a")
    add(p, "todo/b", "todo.waiting", 200, title="b", waits_on="todo/a")
    add(p, "todo/a", "todo.done", 100)
    lines = batcher(p, capsys, record=False)              # read while b waits
    add(p, "todo/b", "todo.dropped", 50)                  # the person drops it, in the gap
    for x in lines:
        if "event" in x:
            p.events.add(x["event"], item=x["item"], source="todo-batcher", data=x["data"])
    assert [x["event"] for x in lines if x.get("item") == "todo/b"] == ["todo.freed"]
    b = {i.id: i for i in its.project(p.events, p.model.spec)}["todo/b"]
    assert b.state == "dropped" and "moves only from waiting" in b.refused[-1]["why"]


# ---- the stakeholder update

def why(p, iid):
    return answer(p, iid, now=NOW, engine=UP)


def test_why_says_its_status_what_it_waits_on_and_what_happens_next(tmp_path, monkeypatch):
    p = project(tmp_path, monkeypatch)
    add(p, "todo/access", "todo.ready", 7200, title="Ask for access", where="anywhere")
    add(p, "todo/new", "todo.added", 3600, title="Not written up")
    add(p, "todo-wait/sign-off", "todo-wait.asked", 3600, title="Security's sign-off")
    add(p, "todo/open", "todo.waiting", 1800, title="Open the port", waits_on="todo/access")
    add(p, "todo/port", "todo.waiting", 1800, title="Close the port", waits_on="todo-wait/sign-off")
    add(p, "todo/gone", "todo.waiting", 1800, title="x", waits_on="todo-wait/never")
    add(p, "todo/old", "todo.ready", 900, title="Done already")
    add(p, "todo/old", "todo.done", 600)

    a = why(p, "todo/access")
    assert a["root"]["kind"] == "person" and a["next"]["owner"] == "a person (todo-do)"
    assert a["next"]["command"] == "ergostat event --add todo.done --item todo/access"
    assert a["summary"] == (
        "todo/access has been in ready for 2h. The cause, a person: in ready, for a person to do: todo-do (a person) is "
        "asked while goal todo-none-ready is off, and stock.todo-ready counts todo items in ready; it moves on when one "
        "of these is recorded: todo.done, todo.waiting, todo.dropped. Next: a person (todo-do) to do it and record it "
        "(todo.done), then report it in the inbox (ergostat inbox person/todo-do --done N) "
        "(`ergostat event --add todo.done --item todo/access`).")
    assert why(p, "todo/access")["summary"] == a["summary"], "the same record, the same words"

    n = why(p, "todo/new")
    assert n["root"]["kind"] == "person" and n["next"]["owner"] == "a person (todo-write-up)"
    assert n["next"]["command"] == "ergostat event --add todo.ready --item todo/new"

    o = why(p, "todo/open")
    assert [x["item"] for x in o["chain"]] == ["todo/open", "todo/access"] and o["root"]["item"] == "todo/access"
    assert o["summary"].startswith("todo/open has been in waiting for 30m. It waits on todo/access. The cause, a person")

    w = why(p, "todo/port")
    assert w["root"]["item"] == "todo-wait/sign-off" and w["root"]["kind"] == "work"
    assert "It waits on todo-wait/sign-off" in w["summary"] and "todo-wait.answered" in w["summary"]

    g = why(p, "todo/gone")
    assert g["root"]["kind"] == "missing" and g["root"]["item"] == "todo-wait/never"

    d = why(p, "todo/old")
    assert d["done"] and d["summary"].endswith("which its kind counts as finished: it is done.")
    assert summary(d) == d["summary"]


ASKED = """
name: t
items:
  note:
    id: note/*
    states: [new, open, shut]
    on: {note.opened: open, note.shut: shut}
    finished: [shut]
stocks:
  open-notes:
    unit: notes
    sensor: {items: note, state: open, every: 1m{where}}
goals:
  none-open: {stock: open-notes, hold: "<= 0"}
blocks:
  reader: {type: person, goal: none-open, ask: read them}
"""


def test_a_person_is_the_cause_only_when_their_goal_counts_every_item_in_its_state(tmp_path, monkeypatch):
    p = project(tmp_path / "a", monkeypatch, ASKED.replace("{where}", ""))
    add(p, "note/1", "note.opened", 60)
    r = why(p, "note/1")["root"]
    assert r["kind"] == "person" and r["command"] == "ergostat event --add note.shut --item note/1"
    p = project(tmp_path / "b", monkeypatch, ASKED.replace("{where}", ", where: {team: a}"))
    add(p, "note/1", "note.opened", 60, team="a")
    assert why(p, "note/1")["root"]["kind"] == "work", "a goal counting only some of them is not this item's"


def test_a_kind_declares_its_own_finished_states(tmp_path, monkeypatch):
    """Without them, a state no item has left yet would read as finished: every ready to-do would be done."""
    p = project(tmp_path, monkeypatch)
    add(p, "todo/a", "todo.ready", 60, title="a")
    assert p.model.spec.items["todo"].finished == ["done", "dropped"]
    assert not why(p, "todo/a")["done"]
    bad = MODEL + "items:\n  x:\n    id: x/*\n    states: [a, b]\n    finished: [a, c]\n    on: {x.b: b}\n"
    for more, code in (("", "bad-finished"), ("    moves-from: {x.b: [c]}\n", "bad-moves-from"),
                       ("    moves-from: {x.z: [a]}\n", "bad-moves-from")):
        (tmp_path / "ergostat.yaml").write_text(bad + more)
        assert code in {x.code for x in read(tmp_path / "ergostat.yaml")[1] if x.level == "error"}, more
    assert p.model.spec.items["todo"].moves_from == {"todo.freed": ("waiting",)}


# ---- nothing outside ergostat

def test_the_template_adds_no_action_that_writes_to_any_outside_system(tmp_path, monkeypatch):
    text = MODEL + "    with:\n      command: cat todos.jsonl\n"
    p = project(tmp_path, monkeypatch, text)
    spec = p.model.spec
    assert not spec.actions and not spec.workspaces and not getattr(spec, "daemons", None)
    mine = {n: b for n, b in spec.blocks.items() if b.system == "todo"}
    assert set(mine) == {"todo-do", "todo-write-up", "todo-batcher", "keep-todo-none-ready", "keep-todo-written-up"}
    for n, b in mine.items():   # an allowlist: a person, the batcher reading the record, or ergostat's own on-off
        assert b.type == "person" or (b.type == "program" and b.params["run"].startswith(f"{LIB} todo batches ")) \
            or (b.implied and b.type == "onoff" and "run" not in b.params), n
        assert not b.takes and not b.params.get("actions") and not b.params.get("workspace"), n
    runs = [s.run for s in spec.sensors() if s.of.name.startswith("todo-") and (s.run or s.query or s.daemon)]
    assert runs and all(r and r.startswith(f"{LIB} collect ") for r in runs), runs
    tree = ast.parse(Path(todo.__file__).read_text())
    mods = {(n.level, n.module) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    mods |= {(0, a.name) for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert mods <= {(0, "__future__"), (0, "argparse"), (0, "hashlib"), (0, "re"), (0, "sys"), (1, "common"),
                    (3, "spec"), (3, "spec.finished"), (3, "spec.relations")}, mods
    used = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "common" for a in n.names}
    assert used == {"items", "project", "say"}
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not calls & {"open", "exec", "eval", "compile", "__import__"}, calls


def test_the_demo_batches_its_todos_across_three_places(tmp_path, monkeypatch):
    """The demo as its model runs it: its collector's command and its batcher's, each as compiled, one pass each."""
    root = Path(__file__).resolve().parent.parent / "examples" / "todo-list"
    for f in ("ergostat.yaml", "todos.jsonl"):
        shutil.copy(root / f, tmp_path / f)
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    p = Project(mdl.load(tmp_path))
    spec = p.model.spec
    collect = spec.flows["todo-added"].sensors["main"].run
    batch = spec.blocks["todo-batcher"].params["run"]

    def run(cmd):
        r = subprocess.run(cmd, shell=True, cwd=tmp_path, capture_output=True, text=True, env={**os.environ})
        assert r.returncode == 0, r.stderr
        for x in (json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")):
            if "event" in x:
                p.events.add(x["event"], item=x["item"], source="demo", data=x["data"])
    run(collect)
    run(batch)
    got = {i.id: i for i in its.project(p.events, spec)}
    assert got["todo/clean-cache"].state == "waiting" and got["todo/update-runbook"].state == "new"
    batches = {k: i.fields for k, i in got.items() if k.startswith("todo-batch/") and i.state == "open"}
    assert set(batches) == {"todo-batch/bastion-1", "todo-batch/lab-vpn", "todo-batch/anywhere"}, batches
    assert batches["todo-batch/bastion-1"]["todos"] == ["todo/rotate-logs", "todo/renew-cert"]
    assert why(p, "todo/clean-cache")["root"]["item"] == "todo/request-access"
    p.events.add("todo.done", item="todo/request-access", source="user")
    run(batch)                                     # the wait is over: ready again, and in its place's batch next pass
    run(batch)
    got = {i.id: i for i in its.project(p.events, spec)}
    assert got["todo/clean-cache"].state == "ready" and got["todo-batch/build-host"].fields["todos"] == ["todo/clean-cache"]
    assert got["todo-batch/anywhere"].state == "clear"
