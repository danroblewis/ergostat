"""Calls from a step answered by the running engine over its socket (docs/proposals/latency.md): ``event --add``,
``act``, ``lease --renew`` and ``item ID --json`` from inside a run go to the engine (``ERGOSTAT_SOCKET``), answer as
they always did, and fall back to the old path when no engine listens; an ``act`` that waits for the owner is parked
and answered as soon as the owner answers; a command for another project is never answered by this engine."""

import json
import os
import shlex
import socket
import subprocess
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
projections:
  job:
    match:
      key: job/*
    states: [ready, done]
    events:
      job.arrived:
        state: set('ready')
      job.done:
        state: set('done')
    otherwise: rest
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
    takes: {projection: job, at: ready, to: [done]}
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


def test_the_socket_lists_items_as_the_command_does(engine, tmp_path):
    p, e = engine
    for n in (1, 2, 3):
        p.events.add("job.arrived", item=f"job/{n}", source="test")
    assert wait_for(lambda: all(its.one(p.events, p.model.spec, f"job/{n}").state == "done" for n in (1, 2, 3)))
    assert wait_for(lambda: not its.one(p.events, p.model.spec, "job/3").fields.get("lease", {}).get("holder"), 5)
    time.sleep(0.3)                                               # (the last run's ending recorded)
    got = client.call("items", path=e.socket, root=str(tmp_path), projection="job", state="done")
    r = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "item", "--projection", "job", "--state", "done",
                        "--json"], capture_output=True, text=True, env={**os.environ, "ERGOSTAT_NO_SOCKET": "1"})
    assert r.returncode == 0, r.stderr
    assert got == json.loads(r.stdout)
    assert sorted(i["id"] for i in got["items"]) == ["job/1", "job/2", "job/3"]
    assert client.call("items", path=e.socket, root=str(tmp_path), projection="job", state="ready")["items"] == []


def test_the_socket_pages_through_more_items_than_one_listing_holds(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: many\nprojections:\n  doc:\n    match: {key: doc/*}\n    states: [open]\n"
                                            "    events: {doc.opened: {state: set('open')}}\n    otherwise: rest\n")
    p = Project(mdl.load(tmp_path))
    for n in range(600):
        p.events.add("doc.opened", item=f"doc/{n}", source="test")
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        first = client.call("items", path=e.socket, root=str(tmp_path), projection="doc")
        rest = client.call("items", path=e.socket, root=str(tmp_path), projection="doc", offset=len(first["items"]))
    finally:
        e.close()
    assert first["total"] == 600 and len(first["items"]) == its.LISTED == 500
    assert len({i["id"] for i in first["items"] + rest["items"]}) == 600, "every one, once, over two pages"


def asking(fn) -> tuple[threading.Thread, dict]:
    """``fn`` called in a thread: what it answered (``out``) or raised (``err``)."""
    got = {}

    def go():
        try:
            got["out"] = fn()
        except Exception as e:
            got["err"] = e
    t = threading.Thread(target=go, daemon=True)
    t.start()
    return t, got


def started(p) -> Engine:
    e = Engine(p, say=lambda s: None)
    e.start_all()
    return e


NOTED = [{"event": "job.noted", "item": "job/1", "data": {"n": 1}}]


def test_a_call_reconnects_across_a_restart(tmp_path):
    p = project(tmp_path, f"{PY} -c pass")
    e = started(p)
    path = e.socket
    e.close()                                                     # the engine stops: its socket is gone
    assert not os.path.exists(path)
    t, got = asking(lambda: client.call("event", path=path, retry=30, root=str(tmp_path), events=NOTED))
    time.sleep(0.5)                                               # (it is trying again meanwhile)
    assert t.is_alive() and not got
    e = started(p)                                                # and starts again, at the same socket
    try:
        assert e.socket == path
        t.join(15)
        assert got.get("out", got)["recorded"] == 1
    finally:
        e.close()
    assert len(p.events.query(n=None, type="job.noted")) == 1


def test_a_call_waits_its_whole_bound_across_a_restart_slower_than_gone(tmp_path, monkeypatch):
    """``ergostat run`` restarting in place (its storage changed: the same name, so the same state folder and socket)
    leaves its socket's file, so a run's call waits its whole bound, not ``GONE`` (cut to 0.2 s here, where the
    restart takes seconds). Fails if the restart's close removes the socket (``Server.keep``): it gives up after GONE."""
    p = project(tmp_path, f"{PY} -c pass")
    path = str(path_for(p.dir))
    monkeypatch.setattr(client, "GONE", 0.2)
    down, once = [], client.once

    def timed(*a):
        try:
            return once(*a)
        except client.Unavailable:
            down.append((time.monotonic(), os.path.exists(path)))
            raise
    monkeypatch.setattr(client, "once", timed)
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "run", "--foreground", "--no-web"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_for(lambda: client.call("ping", path=path, retry=0) if os.path.exists(path) else None, 60)
        down.clear()
        main =tmp_path / "ergostat.yaml"
        main.write_text(main.read_text() + "storage:\n  logs: {runs: 49}\n")      # taken once it settles: a restart

        def stopped():
            try:
                return not once("ping", path, 5.0, {})
            except client.Unavailable:
                return True
        assert wait_for(stopped, 60), "it never restarted"
        t, got = asking(lambda: client.call("event", path=path, retry=60, root=str(tmp_path), events=NOTED))
        t.join(60)
        assert got.get("out", got)["recorded"] == 1
    finally:
        proc.terminate()
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            proc.kill()
    assert down and down[-1][0] - down[0][0] > client.GONE, f"the restart was not slower than GONE: {down}"
    assert all(kept for _, kept in down), "the socket's file was removed during the restart"
    assert len(p.events.query(n=None, type="job.noted")) == 1
    assert len(p.events.query(n=None, type="ergostat.started")) == 2, "one restart"


def test_long_keys_that_share_a_prefix_name_two_calls():
    """Fails if an over-long key is cut short (two calls merged as one, lesson-5) rather than hashed."""
    from ergostat.calls.ops import call_of
    a, b = "k" * 80 + "a", "k" * 80 + "b"
    assert call_of({"call": a}) != call_of({"call": b})
    assert call_of({"call": a}) == call_of({"call": a}) and len(call_of({"call": a})) <= 72
    assert call_of({"call": "abc"}) == "call-abc"


def test_a_call_in_flight_at_the_stop_is_recorded_once(tmp_path):
    from ergostat.calls.server import Server
    p = project(tmp_path, f"{PY} -c pass")
    e = started(p)
    dropped = threading.Event()

    def stopped_before_answering(conn, out):                      # recorded, then the engine stopped before it answered
        Server._close(conn)
        dropped.set()
    e.calls._answer = stopped_before_answering
    t, got = asking(lambda: client.call("event", path=e.socket, retry=30, root=str(tmp_path), events=NOTED))
    assert dropped.wait(10)
    assert len(p.events.query(n=None, type="job.noted")) == 1     # (it was recorded, unanswered)
    e.close()
    e = started(p)
    try:
        t.join(15)
        assert got.get("out", got)["recorded"] == 0, "asked again: already recorded"
    finally:
        e.close()
    assert len(p.events.query(n=None, type="job.noted")) == 1


def test_a_gated_action_in_flight_at_the_stop_is_asked_once(tmp_path):
    p = project(tmp_path, f"{PY} -c pass")
    cfg = tmp_path / "actions.json"                               # a run with no item: no request of its own is the same
    cfg.write_text(json.dumps({"block": "probe", "run": "r1", "actions": ["noop", "ask"], "runner": "ergostat"}))
    e = started(p)
    t, got = asking(lambda: client.call("act", path=e.socket, retry=30, name="ask", args={}, wait=20.0,
                                        env={"ERGOSTAT_ACTIONS": str(cfg)}))
    assert wait_for(lambda: e.calls.parked)                       # held for the owner, the call parked
    e.close()                                                     # the engine stops with it parked
    e = started(p)
    try:
        assert wait_for(lambda: e.calls.parked), "asked again of the new engine, and parked there"
        held = list(rec.stored(p).values())
        assert len(held) == 1 and held[0]["state"] == "requested", "one action, asked once"
        gate.approve(p, p.model.spec, held[0]["id"], by="owner")
        t.join(15)
        assert got.get("out", got)["full"]["state"] == "ran"
    finally:
        e.close()
    assert len(rec.stored(p)) == 1


def test_a_gated_action_parked_while_the_engine_stops_is_asked_again(tmp_path, monkeypatch):
    """The stop lands while the parked-call thread is partway through a pass (the call taken out of ``parked``): the
    call is not put back on the closed engine, its connection is closed, so its caller asks the new engine."""
    from ergostat.actions import program
    p = project(tmp_path, f"{PY} -c pass")
    cfg = tmp_path / "actions.json"
    cfg.write_text(json.dumps({"block": "probe", "run": "r1", "actions": ["noop", "ask"], "runner": "ergostat"}))
    e = started(p)
    settled, stopped = program.settled, threading.Event()

    def settling(*a, **k):
        out = settled(*a, **k)
        if threading.current_thread().name == "ergostat-socket-parked" and not stopped.is_set():
            stopped.set()
            e.close()                                             # the stop, in the middle of the pass
        return out
    monkeypatch.setattr(program, "settled", settling)
    t, got = asking(lambda: client.call("act", path=e.socket, retry=30, name="ask", args={}, wait=20.0,
                                        env={"ERGOSTAT_ACTIONS": str(cfg)}))
    assert wait_for(stopped.is_set)
    assert not e.calls.parked, "not put back on the stopped engine"
    monkeypatch.setattr(program, "settled", settled)
    e = started(p)
    try:
        assert wait_for(lambda: e.calls.parked), "its caller saw the stop and asked the new engine"
        held = list(rec.stored(p).values())
        assert len(held) == 1 and held[0]["state"] == "requested"
        gate.approve(p, p.model.spec, held[0]["id"], by="owner")
        t.join(15)
        assert got.get("out", got)["full"]["state"] == "ran"
    finally:
        e.close()


TWICE = """
import json, os
from ergostat.calls.client import call
env = {k: os.environ[k] for k in ("ERGOSTAT_ITEM", "ERGOSTAT_LEASE", "ERGOSTAT_RUN")}
run = os.environ["ERGOSTAT_RUN"]
out = [call("lease", how="renew", env=env, call=run + "r") for _ in range(2)]
out += [call("lease", how="nack", why="later", after=3600, count=False, env=env, call=run + "n") for _ in range(2)]
json.dump(out, open("twice.json", "w"))
"""


def test_a_lease_call_asked_again_is_recorded_once(tmp_path):
    (tmp_path / "twice.py").write_text(TWICE)
    p = project(tmp_path, f"{PY} twice.py")
    e = started(p)
    try:
        p.events.add("job.arrived", item="job/1", source="test")
        got = wait_for(lambda: written(tmp_path / "twice.json"))
    finally:
        e.close()
    assert got and got[0]["event"]["id"] == got[1]["event"]["id"] and got[2]["event"]["id"] == got[3]["event"]["id"]
    assert got[1]["event"] == got[0]["event"] and got[3]["event"] == got[2]["event"], "asked again: the one recorded"
    assert len([x for x in p.events.query(n=None, type="ergostat.lease.renewed") if x["data"].get("seen") == "asked"]) == 1
    assert len([x for x in p.events.query(n=None, type="ergostat.lease.ended") if x["data"].get("how") == "nack"]) == 1


HOLDS = ("import json, os, time; json.dump({k: os.environ[k] for k in ('ERGOSTAT_ITEM', 'ERGOSTAT_LEASE', "
         "'ERGOSTAT_RUN')}, open('held.json', 'w')); time.sleep(20)")


def test_a_call_the_stopped_engine_recorded_is_recorded_once_by_the_commands_fallback(tmp_path, monkeypatch):
    """Recorded, its answer lost, the engine stopped and not started again: the command records it itself (as with no
    engine), under the same key, so once (an event, a renewal, a no-item run's act)."""
    from ergostat.calls.server import Server
    from ergostat.cli import main
    p = project(tmp_path, f"{PY} -c {shlex.quote(HOLDS)}")
    cfg = tmp_path / "actions.json"
    cfg.write_text(json.dumps({"block": "probe", "run": "r1", "actions": ["noop", "ask"], "runner": "ergostat"}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(client, "GONE", 0.3)
    monkeypatch.setenv("ERGOSTAT_CALL_RETRY", "30")

    def lost(argv, seen, env=None):
        e = started(p)
        if env is not None:
            p.events.add("job.arrived", item="job/1", source="test")
            got = wait_for(lambda: written(tmp_path / "held.json"))
            for k, v in got.items():
                monkeypatch.setenv(k, v)
        monkeypatch.setenv("ERGOSTAT_SOCKET", e.socket)
        dropped = threading.Event()

        def stopped_before_answering(conn, out):                  # recorded, then the engine stopped before it answered
            Server._close(conn)
            dropped.set()
        e.calls._answer = stopped_before_answering
        t, out = asking(lambda: main(argv))
        assert dropped.wait(10)
        assert len(seen()) == 1, "recorded by the engine, unanswered"
        e.close()
        t.join(15)
        assert not t.is_alive()
        assert len(seen()) == 1, "and not again by the command's own fallback"
        return out.get("out", out)

    assert lost(["event", "--add", "job.noted", "--item", "job/9"], lambda: p.events.query(n=None, type="job.noted")) == 0
    monkeypatch.setenv("ERGOSTAT_ACTIONS", str(cfg))
    lost(["act", "ask"], lambda: list(rec.stored(p).values()))
    monkeypatch.delenv("ERGOSTAT_ACTIONS")
    assert lost(["lease", "--renew"], lambda: [x for x in p.events.query(n=None, type="ergostat.lease.renewed")
                                               if x["data"].get("seen") == "asked"], env=True) == 0


def test_a_call_past_the_bound_fails(tmp_path, monkeypatch, request):
    import shutil
    import tempfile

    from ergostat.cli import main
    short = tempfile.mkdtemp(prefix="rs-calls-", dir="/tmp")     # (a socket bound below: macOS's tmp_path is past its
    request.addfinalizer(lambda: shutil.rmtree(short, ignore_errors=True))         # 104-byte limit for a socket's path)
    nobody = os.path.join(short, "nobody.sock")
    began = time.monotonic()
    with pytest.raises(client.Unavailable):
        client.call("ping", path=nobody, retry=0.5)
    assert 0.5 <= time.monotonic() - began < 5
    began = time.monotonic()                                      # a socket whose folder is gone (another machine's,
    with pytest.raises(client.Unavailable):                       # inherited by a container): no engine comes back
        client.call("ping", path=str(tmp_path / "gone" / "e.sock"), retry=30)
    assert time.monotonic() - began < 1
    gone = tmp_path / "other-machine" / ("x" * LIMIT)            # an inherited run's: its socket in the shared short
    path_for(gone).parent.mkdir(parents=True, exist_ok=True)     # folder (which exists), its state folder not here
    monkeypatch.setenv("ERGOSTAT_STATE_DIR", str(gone))
    began = time.monotonic()
    with pytest.raises(client.Unavailable):
        client.call("ping", path=str(path_for(gone)), retry=30)
    assert time.monotonic() - began < 1
    monkeypatch.delenv("ERGOSTAT_STATE_DIR")
    monkeypatch.setattr(client, "GONE", 0.5)
    began = time.monotonic()                                      # removed (a clean stop) and not made again: GONE
    with pytest.raises(client.Unavailable):
        client.call("ping", path=nobody, retry=30)
    assert 0.5 <= time.monotonic() - began < 3
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)     # left behind (a killed engine): the whole bound
    stale.bind(nobody)
    stale.close()
    began = time.monotonic()
    with pytest.raises(client.Unavailable):
        client.call("ping", path=nobody, retry=1.5)
    assert time.monotonic() - began >= 1.5
    os.unlink(nobody)
    monkeypatch.delenv("ERGOSTAT_SOCKET", raising=False)
    assert client.bound() == 0                                    # a command from a shell: no waiting
    monkeypatch.setenv("ERGOSTAT_SOCKET", nobody)                 # a run's: the setting, default 2 minutes, at most an hour
    monkeypatch.delenv("ERGOSTAT_CALL_RETRY", raising=False)
    assert client.bound() == 120
    for said, bound in (("x", 120), ("1e9", 3600), ("nan", 120), ("-5", 0), ("0.4", 0.4)):
        monkeypatch.setenv("ERGOSTAT_CALL_RETRY", said)
        assert client.bound() == bound
    from ergostat.daemons.proc import SHARED
    assert "ERGOSTAT_CALL_RETRY" in SHARED, "a daemon's calls keep the setting (its other ERGOSTAT_ are dropped)"
    p = project(tmp_path, f"{PY} -c pass")
    monkeypatch.chdir(tmp_path)
    began = time.monotonic()
    assert main(["event", "--add", "job.noted", "--item", "job/1"]) == 0     # then it does what it does today
    assert time.monotonic() - began >= 0.4
    assert len(p.events.query(n=None, type="job.noted")) == 1


def test_a_call_accepted_as_the_engine_stops_is_closed_so_its_caller_asks_again(tmp_path):
    """The stop lands between the accept and the hand-over to a worker (queued behind the workers' stop markers, it
    would never be answered): its connection is closed, so its caller sees the stop at once, not after its timeout."""
    import ergostat.calls.server as srv
    p = project(tmp_path, f"{PY} -c pass")
    box, real = {}, srv.socket.socket

    class Stopping(real):
        def accept(self):
            got = super().accept()
            box["e"].calls.close()                                # the stop, in the gap
            return got
    srv.socket.socket = Stopping
    try:
        box["e"] = e = started(p)
    finally:
        srv.socket.socket = real
    try:
        began = time.monotonic()
        with pytest.raises(client.Unavailable):
            client.call("ping", path=e.socket, timeout=20, retry=0, root=str(tmp_path))
        assert time.monotonic() - began < 5, "closed, not left to its read timeout"
    finally:
        e.close()
