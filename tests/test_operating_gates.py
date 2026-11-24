"""Gates scheduled by the declared operating state in force, and the owner's bypass leases (SPEC §12k, *Gates by
declared state*): one resolution (``schedule.resolve``) at the request and again at the act, under the operating lock
from the re-check until the command has started. The lock tests order things by events and lists: a bounded wait
can only run out in the direction where the test passes."""

import itertools
import json
import math
import os
import textwrap
import threading
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import spec as spec_mod
from ergostat.actions import gate
from ergostat.actions import schedule as sch
from ergostat.actions.risk import ORDER
from ergostat.cli import main
from ergostat.intake import envelope
from ergostat.mcp import Server
from ergostat.operating import acts
from ergostat.operating import fold as op_fold
from ergostat.spec import items as its
from ergostat.spec.ir import Action
from ergostat.store import Project

MODEL = """
name: t
operating:
  incident: {rank: 3}
  freeze: {rank: 2}
actions:
  ship:
    run: "touch shipped.txt; echo ok"
    gate: {normal: auto, freeze: approve, else: deny}
    class: release
    in: .
  hold:
    run: "touch held.txt; echo ok"
    gate: {normal: approve, freeze: deny, else: deny}
    class: careful
    in: .
  plain:
    run: "touch plain.txt"
    gate: auto
    in: .
  slow:
    run: "sleep 30 >/dev/null 2>&1 & echo $! > bg.pid; wait"
    gate: auto
    timeout: 1s
    in: .
blocks:
  dev: {type: program, run: "true", actions: [ship, hold, plain, slow], every: 1h}
"""


@pytest.fixture(autouse=True)
def owner(monkeypatch):
    monkeypatch.delenv("ERGOSTAT_RUN", raising=False)     # the owner's shell: no run's mark


def project(d: Path, text: str = MODEL) -> Project:
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(d)
    assert not [x for x in m.problems if x.level == "error"], [x.message for x in m.problems]
    return Project(m)


def again(p) -> Project:
    """The same project opened afresh (its own connection), for another thread."""
    return Project(mdl.load(p.model.path.parent))


def ask(p, name: str, asker: str = "session") -> dict:
    return gate.request(p, p.model.spec, name, {}, {"block": "dev", "run": "r1", "workdir": str(p.model.path.parent)},
                        asker=asker)


def enter(p, state: str) -> None:
    acts.enter(p, p.model.spec, state, "test", env={})


def mark(p, name: str) -> bool:
    return (p.model.path.parent / f"{name}.txt").exists()


def held_approved(p, name: str) -> dict:
    """Asked, held, and approved by the owner while a waiter's marker keeps the approval from running it at once."""
    a = ask(p, name)
    assert a["state"] == "requested", a
    gate._marker(p, a["id"]).write_text(str(os.getpid()))
    a = gate.approve(p, p.model.spec, a["id"])
    assert a["state"] == "approved" and a["approved_by"] == "owner"
    return a


def bypass_events(p) -> list:
    return p.events.query(n=None, type="ergostat.bypass.*")


def cli(p, *argv) -> int:
    try:
        return main(["-C", str(p.model.path.parent), *argv])
    except SystemExit as e:
        return e.code


def refused(a: dict) -> bool:
    return a["state"] == "failed" and a["exit"] is None and a["seconds"] == 0 and bool(a.get("refused"))


# ---- gate maps and resolution

ONE = """
name: t
{ops}
actions:
  a: {{run: "true", gate: {gate}}}
"""
OPS = "operating:\n  incident: {rank: 3}\n  freeze: {rank: 2}"


def errors(tmp_path, gate_: str, ops: str = OPS) -> list:
    f = tmp_path / "ergostat.yaml"
    f.write_text(textwrap.dedent(ONE.format(ops=ops, gate=gate_)))
    _, problems = spec_mod.read(f)
    return [x for x in problems if x.level == "error"]


def test_gate_map_compiles_and_errors(tmp_path):
    p = project(tmp_path / "good")
    ship, plain = p.model.spec.actions["ship"], p.model.spec.actions["plain"]
    assert ship.states == {"normal": "auto", "freeze": "approve", "else": "deny"} and ship.gate == "auto"
    assert plain.states == {} and plain.gate == "auto" and "ergostat.bypass" in p.model.spec.items
    for g, code in (("{normal: auto, holiday: deny, else: deny}", "unknown-ref"),
                    ("{normal: auto, freeze: never, else: deny}", "bad-value"),
                    ("{normal: auto, freeze: deny}", "gate-uncovered")):
        got = errors(tmp_path, g)
        assert [x.code for x in got] == [code], (g, [x.message for x in got])
        assert got[0].where is not None and got[0].where.line, g
    got = errors(tmp_path, "{normal: auto, else: deny}", ops="")
    assert [x.code for x in got] == ["gate-needs-states"], [x.message for x in got]
    assert errors(tmp_path, "{normal: auto, freeze: deny, incident: deny}") == []
    assert errors(tmp_path, "approve", ops="") == []                                  # a plain gate, as before
    assert errors(tmp_path, "{normal: auto, freeze: deny}", ops="") == []             # a §12k column map, as before


def test_resolve_missing_state_or_cell_denies(tmp_path, monkeypatch):
    t = time.time()
    a = Action("x", "true", gate="auto", cls="c", states={"normal": "auto", "freeze": "auto"})   # no else, by hand
    for st in (None, "incident"):
        assert sch.resolve(a, st, {}, t)[0] == "deny", st
        assert sch.resolve(a, st, {"c": t + 3600}, t)[0] == "deny", st                # a bypass opens no unread cell
    p = project(tmp_path)
    monkeypatch.setattr(op_fold, "current", lambda p, spec: "holiday")              # a name the model does not declare
    assert sch.state(p, p.model.spec) is None
    assert sch.resolve(a, sch.state(p, p.model.spec), {}, t)[0] == "deny"


def test_resolve_never_looser():
    t, states = 1000.0, ("normal", "freeze", "incident")
    for cells in itertools.product(ORDER, repeat=3):
        m = dict(zip(states, cells, strict=True))
        a = Action("x", "true", gate=m["normal"], cls="c", states=m)
        for s in states:
            assert sch.resolve(a, s, {}, t)[0] == m[s]
            assert sch.resolve(a, s, {"c": t}, t)[0] == m[s]                         # until == now: not standing
            assert sch.resolve(a, s, {"other": t + 60}, t)[0] == m[s]                # another class's bypass
            got = sch.resolve(a, s, {"c": t + 60}, t)[0]
            assert got == ORDER[min(ORDER.index(m[s]), ORDER.index(m["normal"]))], (m, s, got)
            assert ORDER.index(got) >= min(ORDER.index(m[s]), ORDER.index(m["normal"]))  # never past the default's


# ---- the request, and the re-check at the act

def test_request_scheduled_by_state(tmp_path):
    p = project(tmp_path)
    a = ask(p, "ship")
    assert a["state"] == "ran" and mark(p, "shipped") and a["state"] == "ran" and a["gate"] == "auto"
    assert a["scheduled"]["state"] == "normal" and a.get("scheduled")["gate"] == "auto"
    (tmp_path / "shipped.txt").unlink()
    enter(p, "freeze")
    b = ask(p, "ship")
    assert b["state"] == "requested" and b["gate"] == "approve" and not mark(p, "shipped")
    assert b["scheduled"]["state"] == "freeze"
    enter(p, "incident")
    c = ask(p, "ship")
    assert c["state"] == "denied" and c["denied_by"] == "gate" and "under incident" in c["note"]
    assert c["scheduled"]["state"] == "incident" and not mark(p, "shipped")
    first = p.events.query(n=None, item=c["id"], type="ergostat.action.requested")[0]["data"]
    assert first["state"] == "incident" and first["scheduled"]["gate"] == "deny"


def test_released_then_state_changed_not_run(tmp_path):
    p = project(tmp_path)
    a = ask(p, "ship", asker="program")                   # approved by the gate, left for the engine to run
    assert a["state"] == "approved" and a["approved_by"] == "gate"
    enter(p, "freeze")                                    # ship's freeze cell: approve
    got = gate.run_once(p, p.model.spec, a["id"])
    assert refused(got) and "approve" in got["refused"] and not mark(p, "shipped")


def test_owner_approval_refused_when_state_denies(tmp_path):
    p = project(tmp_path)
    enter(p, "freeze")
    a = held_approved(p, "ship")                          # held in freeze, approved by the owner
    enter(p, "incident")                                  # ship's incident: else, deny
    got = gate.run_once(p, p.model.spec, a["id"])
    assert refused(got) and "deny" in got["refused"] and not mark(p, "shipped")


@pytest.mark.parametrize("how", ["raises", "undeclared"])
def test_unreadable_state_refuses_owner_approved(tmp_path, monkeypatch, how):
    p = project(tmp_path)
    a = held_approved(p, "hold")                          # held in normal (approve), approved by the owner

    def current(p, spec):
        if how == "raises":
            raise OSError("record unreadable")
        return "holiday"
    monkeypatch.setattr(op_fold, "current", current)
    got = gate.run_once(p, p.model.spec, a["id"])
    assert refused(got) and "cannot be read" in got["refused"] and not mark(p, "held")
    b = ask(p, "ship")                                    # auto in normal, but the state cannot be read
    assert b["state"] == "denied" and b["scheduled"]["state"] is None and not mark(p, "shipped")


# ---- the lock

def test_state_entry_waits_for_command_start(tmp_path, monkeypatch):
    p = project(tmp_path)
    a = ask(p, "ship", asker="program")
    order, done, real = [], threading.Event(), gate._spawn
    other = again(p)

    def spawn(command, cwd, env):
        def go():
            enter(other, "freeze")
            order.append("entered")
            done.set()
        th = threading.Thread(target=go)
        th.start()
        threads.append(th)
        done.wait(2)                                      # (with the lock held it cannot end: the wait runs out)
        order.append("spawned")
        return real(command, cwd, env)
    threads: list = []
    monkeypatch.setattr(gate, "_spawn", spawn)
    got = gate.run_once(p, p.model.spec, a["id"])
    threads[0].join(10)
    assert order == ["spawned", "entered"], order
    assert got["state"] == "ran" and mark(p, "shipped")   # re-checked in normal
    assert sch.state(p, p.model.spec) == "freeze"         # and the entry landed, once the lock was let go


def test_act_waits_for_state_entry(tmp_path, monkeypatch):
    p = project(tmp_path)
    a = held_approved(p, "hold")                          # normal: approve, freeze: deny
    other, res, threads = again(p), [], []
    real = other.events.add

    def add(*args, **kw):                                 # inside enter's exclusive lock, before its write
        th = threading.Thread(target=lambda: res.append(gate.run_once(again(p), p.model.spec, a["id"])))
        th.start()
        threads.append(th)
        th.join(2)                                        # (the act waits for the lock: the join runs out)
        res.append("written")
        return real(*args, **kw)
    monkeypatch.setattr(other.events, "add", add)
    enter(other, "freeze")
    threads[0].join(10)
    assert res[0] == "written", res                       # run_once returned after the write
    assert refused(res[1]) and not mark(p, "held")


def test_bypass_end_waits_for_command_start(tmp_path, monkeypatch):
    p = project(tmp_path)
    enter(p, "freeze")
    assert cli(p, "bypass", "careful", "--for", "1h") == 0
    a = held_approved(p, "hold")                          # freeze: deny, but the bypass gives normal's approve
    order, done, real, threads = [], threading.Event(), gate._spawn, []

    def spawn(command, cwd, env):
        def go():
            assert cli(p, "bypass", "careful", "--end") == 0
            order.append("ended")
            done.set()
        th = threading.Thread(target=go)
        th.start()
        threads.append(th)
        done.wait(2)
        order.append("spawned")
        return real(command, cwd, env)
    monkeypatch.setattr(gate, "_spawn", spawn)
    got = gate.run_once(p, p.model.spec, a["id"])
    threads[0].join(10)
    assert order == ["spawned", "ended"], order
    assert got["state"] == "ran" and mark(p, "held") and sch.standing(p, time.time()) == {}


# ---- bypass leases

def test_bypass_lets_class_through_until_end(tmp_path):
    p = project(tmp_path)
    enter(p, "freeze")
    assert ask(p, "hold")["state"] == "denied"
    assert cli(p, "bypass", "careful", "--for", "1h", "--note", "hotfix") == 0
    a = ask(p, "hold")
    assert a["state"] == "requested" and "bypass" in a["scheduled"]["why"]
    a = gate.approve(p, p.model.spec, a["id"])
    assert a["state"] == "ran" and mark(p, "held")
    it = its.one(p.events, p.model.spec, "ergostat.bypass/careful")
    assert it.state == "granted" and it.fields["note"] == "hotfix" and it.fields["by"] == "owner"
    assert cli(p, "bypass", "careful", "--end") == 0
    assert its.one(p.events, p.model.spec, "ergostat.bypass/careful").state == "ended"
    assert ask(p, "hold")["state"] == "denied"


@pytest.mark.parametrize("how", ["end", "clock"])
def test_bypass_ended_before_start_fails_unrun(tmp_path, monkeypatch, how):
    p = project(tmp_path)
    enter(p, "freeze")
    assert cli(p, "bypass", "careful", "--for", "1h") == 0
    a = held_approved(p, "hold")
    if how == "end":
        assert cli(p, "bypass", "careful", "--end") == 0
    else:
        until = sch.standing(p, time.time())["careful"]
        monkeypatch.setattr(sch, "now", lambda: until + 1)
    got = gate.run_once(p, p.model.spec, a["id"])
    assert refused(got) and not mark(p, "held")


GRANT = "ergostat.bypass.granted"


@pytest.mark.parametrize("data", [[1, 2], "soon", {"by": "owner"}, {"until": "soon"}, {"until": math.nan},
                                  {"until": math.inf}, {"until": True}, "query-raises", "good-then-bad"])
def test_bypass_corrupt_counts_as_none(tmp_path, monkeypatch, data):
    p = project(tmp_path)
    enter(p, "freeze")
    t = time.time()
    if data == "query-raises":
        p.events.add(GRANT, item="ergostat.bypass/careful", source="owner", data={"until": t + 3600})
        real = p.events.query

        def query(**kw):
            if str(kw.get("type") or "").startswith("ergostat.bypass"):
                raise OSError("unreadable")
            return real(**kw)
        monkeypatch.setattr(p.events, "query", query)
    elif data == "good-then-bad":
        p.events.add(GRANT, item="ergostat.bypass/careful", source="owner", data={"until": t + 3600})
        p.events.add_many([{"type": GRANT, "item": "ergostat.bypass/careful", "source": "owner", "data": {"until": None}}])
    else:
        p.events.add_many([{"type": GRANT, "item": "ergostat.bypass/careful", "source": "owner", "data": data}])
    assert sch.standing(p, t) == {}
    assert ask(p, "hold")["state"] == "denied" and not mark(p, "held")


def test_bypass_ceiling(tmp_path):
    p = project(tmp_path)
    for dur in ("25h", "0", "0s", "-1h", "soon", "5y", "1e9h", "9" * 400 + "d", "inf"):
        assert cli(p, "bypass", "careful", f"--for={dur}") == 2, dur     # (=: a leading - reaches the check)
    assert bypass_events(p) == []
    t = time.time()
    e = p.events.add(GRANT, item="ergostat.bypass/careful", source="owner", data={"until": t + 48 * 3600})
    assert sch.standing(p, e["time"] + 86400 - 1) == {"careful": e["time"] + 86400}
    assert sch.standing(p, e["time"] + 86400) == {}
    with pytest.raises(sch.BypassError):
        sch.grant(p, p.model.spec, "careful", 86401.0)


def test_bypass_regrant_and_same_second_order(tmp_path):
    p = project(tmp_path)
    t = time.time()
    u = {"until": t + 3600, "by": "owner", "note": None, "ended": None, "ended_by": None}
    end = {"ended": t, "ended_by": "owner"}

    def write(cls, *evs):
        p.events.add_many([{"type": f"ergostat.bypass.{k}", "item": f"ergostat.bypass/{cls}", "source": "owner",
                            "at": at, "data": u if k == "granted" else end} for k, at in evs])
    write("careful", ("granted", t), ("ended", t), ("granted", t))       # all in one second: by seq
    assert "careful" in sch.standing(p, t)
    it = its.one(p.events, p.model.spec, "ergostat.bypass/careful")
    assert it.state == "granted" and it.fields.get("ended") is None and it.fields.get("ended_by") is None
    write("release", ("granted", t), ("ended", t))
    assert "release" not in sch.standing(p, t)
    write("a", ("granted", t), ("ended", t - 5))          # the later in seq stamped earlier: still the later
    assert "a" not in sch.standing(p, t)
    write("b", ("ended", t), ("granted", t - 5))
    assert "b" in sch.standing(p, t)


def test_bypass_refused_from_a_run(tmp_path, monkeypatch):
    p = project(tmp_path)
    monkeypatch.setenv("ERGOSTAT_RUN", "run-1")
    assert cli(p, "bypass", "careful", "--for", "1h") == 2
    assert cli(p, "bypass", "careful", "--end") == 2
    assert bypass_events(p) == []


def test_bypass_events_refused_from_agents(tmp_path):
    p = project(tmp_path)
    assert cli(p, "event", "--add", GRANT, "--item", "ergostat.bypass/careful", "--data", json.dumps({"until": 1e12})) != 0
    out = Server(tmp_path).call("record_event", {"type": GRANT, "item": "ergostat.bypass/careful",
                                                 "data": {"until": 1e12}})
    assert out.get("isError"), out
    with pytest.raises(envelope.Refused):
        for e in envelope.parse(json.dumps({"event": GRANT, "item": "ergostat.bypass/careful", "data": {"until": 1e12}})):
            envelope.check(e)
    assert bypass_events(p) == []


def test_bypass_class_allowlist(tmp_path):
    p = project(tmp_path)
    for cls in ("nosuch", "plain", "../x", "Careful", "a" * 65):
        assert cli(p, "bypass", cls, "--for", "1h") == 2, cls
        assert cli(p, "bypass", cls, "--end") == 2, cls
    assert bypass_events(p) == []
    assert cli(p, "bypass", "careful", "--end") == 2      # nothing standing: nothing to end
    assert bypass_events(p) == []


def test_bypass_never_runs_on_the_fallback(tmp_path, capsys):
    from ergostat.goodmodel import keep
    p = project(tmp_path)
    assert keep(p) is None
    with open(tmp_path / "ergostat.yaml", "a") as f:
        f.write("\nbroken: [\n")
    for argv in (["bypass", "careful", "--for", "1h"], ["bypass"]):
        assert cli(p, *argv) == 2
        assert "acts, so it never runs on the last good model" in capsys.readouterr().err
    assert bypass_events(p) == []


# ---- status, and the run step

def test_actions_table_shows_gate_in_force(tmp_path, monkeypatch, capsys):
    p = project(tmp_path)
    enter(p, "freeze")
    assert cli(p, "bypass", "careful", "--for", "1h") == 0
    ask(p, "hold")
    capsys.readouterr()
    assert cli(p, "actions") == 0
    row = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("careful"))
    assert "approve (bypass until" in row, row
    assert cli(p, "bypass") == 0 and "careful" in capsys.readouterr().out
    monkeypatch.setattr(sch, "resolve", lambda *a: ("SENTINEL", "x"))
    assert cli(p, "actions") == 0
    row = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("careful"))
    assert "SENTINEL" in row, row


def gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        try:
            return stat.read_text().rsplit(")", 1)[1].split()[0] in ("Z", "X")     # a zombie is gone
        except (OSError, IndexError):
            return True
    import subprocess
    got = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return not got.stdout.strip() or got.stdout.strip().startswith("Z")


def test_run_timeout_stops_its_group(tmp_path):
    p = project(tmp_path)
    a = ask(p, "slow")
    assert a["state"] == "failed" and a["exit"] is None and "stopped after its timeout of 1s" in a["output"]
    pid = int((tmp_path / "bg.pid").read_text())
    end = time.monotonic() + 10
    while not gone(pid):
        assert time.monotonic() < end, f"the background sleep {pid} outlived its action's timeout"
        time.sleep(0.05)
