"""Daemons (SPEC §9.7): long-lived processes that blocks' runs and sensors' readings are handed to as JSON lines, many
at once, supervised: restarted when they crash, go silent or stop reading their input; given up (an alarm and an
intervention) after too many restarts; ``cancel`` on a lease's expiry; drained and replaced on a model swap."""

import json
import os
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat.leases import ENDED, kill
from ergostat.leases.kill import KILLED

from .test_leases import KIND, item, project, start, wait_for

DAEMON = r'''
import json, os, sys, threading, time
mode = sys.argv[1] if len(sys.argv) > 1 else ""
open("starts.log", "a").write(f"{os.getpid()}\n")
out, cancelled, workers = threading.Lock(), set(), []
def say(**o):
    with out:
        sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
def beat():
    while True:
        say(heartbeat=True); time.sleep(0.2)
if "silent" not in mode:
    threading.Thread(target=beat, daemon=True).start()
if "kids" in mode:                          # a child that keeps its output open, left behind by the crash
    import subprocess; kid = subprocess.Popen(["sleep", "600"]); open("kid.pid", "w").write(str(kid.pid))
if "crash" in mode:
    time.sleep(0.3); os._exit(3)
if "noread" in mode:
    time.sleep(600)
def work(m):
    r, f = m["run"], m["input"]["item"]["fields"]
    say(event="ticket.started", run=r, data={"env_item": m["env"].get("ERGOSTAT_ITEM"), "proc_item": os.environ.get("ERGOSTAT_ITEM"),
                                             "lease": m["lease"]["fence"], "item": m["item"]})
    end, tick = time.time() + float(f.get("sleep", 0.2)), time.time()
    while time.time() < end:
        if r in cancelled and "stubborn" not in mode:
            say(done=1, run=r); return
        if f.get("tick") and time.time() - tick > 0.4:
            tick = time.time(); say(event="ticket.working", run=r)
        time.sleep(0.02)
    if "stray" in mode:
        print("not json at all", flush=True)
        say(event="ticket.done"); say(event="ticket.done", run="not-a-run"); say(done=0.0, run=r); say(done=True, run=r)
        say(done=0, run=r, extra=1)
    say(event="ticket.done", run=r)
    say(done=0, run=r)
for line in sys.stdin:
    m = json.loads(line)
    if m["op"] == "item":
        workers.append(threading.Thread(target=work, args=(m,))); workers[-1].start()
    elif m["op"] == "read":
        say(reading=int(m["sensor"].split(".")[0][1:]), request=m["request"])
    elif m["op"] == "cancel":
        cancelled.add(m["run"])
    elif m["op"] == "stop":
        break
for t in workers:
    t.join(10)
'''


def block(daemon: str, lease: str = "{ttl: 1m}", pool: int = 6) -> str:
    return KIND + f"""
blocks:
  worker:
    type: program
    takes: {{kind: ticket, at: ready}}
    pool: {pool}
    lease: {lease}
    daemon: {daemon}
"""


def setup(tmp_path, text: str):
    (tmp_path / "d.py").write_text(DAEMON)
    return project(tmp_path, text)


def starts(tmp_path) -> list[int]:
    f = tmp_path / "starts.log"
    return [int(x) for x in f.read_text().split()] if f.exists() else []


def events(p, t: str) -> list[dict]:
    return p.events.query(n=None, type=t)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def spawned(p) -> int:
    """Processes the supervisor spawned, by its log: one killed as soon as spawned (never in starts.log) counts too."""
    return (p.dir / "logs" / "daemon-block.worker.log").read_text().count(" starting: ")


def test_first_start_spawns_once(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py}"))
    e = start(p)
    try:
        assert wait_for(lambda: starts(tmp_path), 10)
        time.sleep(0.5)                                  # (the supervisor's first ticks, which once started it again)
    finally:
        e.close()
    assert spawned(p) == 1, "the engine's start and the supervisor's first tick both spawned it"
    assert len(events(p, "ergostat.daemon.started")) == 1


def test_a_daemon_is_running_when_the_engine_has_started_whichever_thread_wins_its_first_spawn(tmp_path, monkeypatch):
    """The supervisor's loop starts before the engine's own first spawn; were its first tick to claim the new slot,
    the engine's start returned with it still "starting", and the first reading asked failed (a sensor polled every
    minute then had no reading for a minute). Here the loop is given every chance to win: the engine's own spawn
    waits until the loop has begun one, and the loop's is slow."""
    from ergostat.daemons.supervise import Supervisor
    loop_spawning = threading.Event()
    spawn, start_ = Supervisor._spawn, Supervisor._start

    def slow_spawn(self, slot):
        if threading.current_thread().name == "ergostat-daemons":
            loop_spawning.set()
            time.sleep(0.5)
        spawn(self, slot)

    def late_start(self, slot):
        if threading.current_thread().name != "ergostat-daemons":
            loop_spawning.wait(1.0)
        start_(self, slot)

    monkeypatch.setattr(Supervisor, "_spawn", slow_spawn)
    monkeypatch.setattr(Supervisor, "_start", late_start)
    p = setup(tmp_path, block("{run: python3 d.py}"))
    e = start(p)
    try:
        state = e.daemons.slots["block.worker"].state
        time.sleep(0.7)                                  # (a spawn by the loop, had it claimed one, finished)
    finally:
        e.close()
    assert state == "running", f"the engine started with its daemon {state!r}"
    assert not loop_spawning.is_set(), "the supervisor's loop spawned a daemon the engine's start had claimed"
    assert spawned(p) == 1


def test_interleaved_items_are_attributed_to_their_runs(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py, concurrency: 6}"))
    for i, s in enumerate([0.9, 0.2, 0.6, 0.1, 0.4, 0.7]):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", data={"sleep": s})
    e = start(p)
    try:
        assert wait_for(lambda: all(item(p, f"ticket/{i}").state == "done" for i in range(6)), 15)
    finally:
        e.close()
    assert len(starts(tmp_path)) == 1, "one process served every item"
    runs = {x["id"]: x for x in events(p, "agent.started")}
    for ev in events(p, "ticket.started") + events(p, "ticket.done"):
        assert runs[ev["causedby"]]["data"]["item"] == ev["item"], "each line about the run's own item"
    for ev in events(p, "ticket.started"):
        assert ev["data"]["env_item"] == ev["item"] and ev["data"]["proc_item"] is None, "env per item, in its line"
        assert ev["data"]["item"] == ev["item"] and ev["data"]["lease"] == 1
    ran = events(p, "agent.ran")
    assert len(ran) == 6 and all(r["data"]["exit"] == 0 and r["data"]["daemon"] == "block.worker" for r in ran)
    assert all("resources" not in r["data"] for r in ran), "no per-item CPU claimed: wall time only"
    t = [x["time"] for x in ran]
    assert max(t) - min(t) < 1.5, "the items ran at once, not one after another"


def test_stray_and_unknown_tagged_lines_are_dropped(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py stray}"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    p.events.add("ticket.opened", item="ticket/2", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: item(p, "ticket/1").state == "done" and item(p, "ticket/2").state == "done", 10)
    finally:
        e.close()
    assert len([x for x in events(p, "ticket.done")]) == 2, "an untagged line, or one for no run, is never taken"
    assert all(r["data"]["exit"] == 0 for r in events(p, "agent.ran"))
    log = (p.dir / "logs" / "daemon-block.worker.log").read_text()
    assert log.count("dropped") == 12 and "not a JSON object" in log and "no run of that id held" in log
    assert "tagged with no run" in log


def test_strict_done(tmp_path):
    from ergostat.daemons.proc import Handle, Process
    from ergostat.spec.ir import Daemon
    with open(tmp_path / "log", "a") as log:
        p = Process(Daemon("x", "cat > /dev/null"), tmp_path, dict(os.environ), log, lambda *a: False)
        h = Handle(take=lambda lines: None)
        p.hold("r1", h, {"op": "noop"})
        for bad in ('{"done": 1.0, "run": "r1"}', '{"done": true, "run": "r1"}', '{"done": "0", "run": "r1"}',
                    '{"done": 0, "run": "r1", "x": 1}'):
            p.line(bad)
            assert not h.done.is_set(), bad
        p.line('{"done": 2, "run": "r1"}')
        assert h.done.is_set() and h.code == 2
        p.stop()
        assert p.ended.wait(5)


def test_crash_restarts_the_daemon(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py crash, restart: {max: 50, backoff: [0.1s, 0.2s]}}"))
    e = start(p)
    try:
        assert wait_for(lambda: len(events(p, "ergostat.daemon.restarted")) >= 2, 10)
        assert wait_for(lambda: len(set(starts(tmp_path))) >= 3, 5)
    finally:
        e.close()
    r = events(p, "ergostat.daemon.restarted")[0]["data"]
    assert r["why"] == "exited 3" and r["exit"] == 3 and r["wait"] == 0.1
    assert events(p, "ergostat.daemon.restarted")[1]["data"]["wait"] == 0.2, "backed off, doubling to the most"


def test_silence_past_heartbeat_restarts(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py silent, heartbeat: 1s, restart: {backoff: [0.1s, 1s]}}"))
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "ergostat.daemon.restarted"), 6)
        assert wait_for(lambda: len(starts(tmp_path)) >= 2, 5)
    finally:
        e.close()
    assert "silent for" in events(p, "ergostat.daemon.restarted")[0]["data"]["why"]
    assert not alive(starts(tmp_path)[0]), "the silent one is stopped"


def test_restart_storm_gives_up_with_alarm_and_intervention(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py crash, restart: {max: 2, within: 1m, backoff: [0.1s, 0.1s]}}"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "ergostat.daemon.failed"), 10)
        time.sleep(1.0)
        n = len(starts(tmp_path))
        e.daemons.write()
    finally:
        e.close()
    assert n == 3, "started, restarted twice, then given up: no more"
    assert spawned(p) == 3, "each start spawned one process: none spawned and killed as a duplicate"
    f = events(p, "ergostat.daemon.failed")[0]
    assert f["item"] == "block.worker" and f["data"]["intervention"] is True
    assert f["data"]["class"] == "alarm:daemon:block.worker" and f["data"]["users"] == ["block.worker"]
    from ergostat import state as st
    att = [a for a in st.attention(st.snapshot(p)) if a["what"] == "daemon block.worker"]
    assert att and att[0]["level"] == "bad" and "given up after 3 restarts" in att[0]["says"]
    from ergostat.inbox import interventions
    got = [x for x in interventions.read(p, p.model.spec, 0, time.time() + 1) if x["class"] == "alarm:daemon:block.worker"]
    assert len(got) == 1 and got[0]["cause"] == "block.worker" and got[0]["answered"] is None, "counted as an intervention"


@pytest.mark.serial                                      # (its bound on the loop's latency holds on a quiet machine)
def test_stdin_not_read_restarts_and_alarms_without_blocking_the_engine(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py noread, stdin-timeout: 1s, restart: {max: 50, backoff: [0.1s, 0.2s]}}"))
    big = "x" * 300_000                                  # more than a pipe holds: the write waits
    for i in range(3):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", data={"blob": big})
    e = start(p)
    worst = 0.0
    try:
        end = time.time() + 8
        while time.time() < end and not events(p, "ergostat.daemon.restarted"):
            worst = max(worst, time.monotonic() - e.loop_beat)
            time.sleep(0.05)
        got = events(p, "ergostat.daemon.restarted")
    finally:
        e.close()
    assert got and got[0]["data"]["alarm"] is True and "standard input" in got[0]["data"]["why"]
    assert worst < 0.75, f"the engine's loop went {worst:.2f}s without a round: it waited on the daemon"


def test_cancel_on_lease_expiry_and_restart_when_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(kill, "GRACE", 1.0)
    p = setup(tmp_path, block("{run: python3 d.py}", "{ttl: 1s, attempts: 3}"))
    p.events.add("ticket.opened", item="ticket/1", source="t", data={"sleep": 30})
    e = start(p)
    try:
        assert wait_for(lambda: events(p, KILLED), 10)
        assert wait_for(lambda: events(p, "agent.failed"), 5)
    finally:
        e.close()
    k = events(p, KILLED)[0]["data"]
    assert k["signal"] == "cancel" and k["item"] == "ticket/1"
    assert events(p, "agent.failed")[0]["data"]["note"].startswith("killed: its lease on ticket/1 expired")
    assert not events(p, "ergostat.daemon.restarted"), "it answered its cancel: no restart"
    assert len(starts(tmp_path)) == 1


def test_a_daemon_ignoring_cancel_is_restarted_and_its_other_items_given_back(tmp_path, monkeypatch):
    monkeypatch.setattr(kill, "GRACE", 1.0)
    p = setup(tmp_path, block("{run: python3 d.py stubborn, restart: {backoff: [0.1s, 1s]}}", "{ttl: 1s, attempts: 3}"))
    p.events.add("ticket.opened", item="ticket/1", source="t", data={"sleep": 30})
    p.events.add("ticket.opened", item="ticket/2", source="t", data={"sleep": 30, "tick": True})
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "ergostat.daemon.restarted"), 12)
        assert wait_for(lambda: any(x["item"] == "ticket/2" for x in events(p, ENDED)), 5)
    finally:
        e.close()
    assert "after it was cancelled" in events(p, "ergostat.daemon.restarted")[0]["data"]["why"]
    two = [x for x in events(p, ENDED) if x["item"] == "ticket/2"][0]["data"]
    assert two["how"] == "nack" and two["count"] is False, "the other item given back, uncounted"


def test_a_swap_restarts_a_changed_daemon_gracefully(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py}"))
    p.events.add("ticket.opened", item="ticket/1", source="t", data={"sleep": 1.5})
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "ticket.started"), 5)
        first = starts(tmp_path)[0]
        (tmp_path / "ergostat.yaml").write_text(block("{run: python3 d.py v2}"))
        e.swap(mdl.load(tmp_path))
        assert wait_for(lambda: len(starts(tmp_path)) == 2, 5), "a new one started at once"
        assert wait_for(lambda: item(p, "ticket/1").state == "done", 5), "the old one finished what it held"
        assert wait_for(lambda: not alive(first), 5), "then it ended"
        p.events.add("ticket.opened", item="ticket/2", source="t")
        assert wait_for(lambda: item(p, "ticket/2").state == "done", 5)
    finally:
        e.close()
    assert not events(p, "ergostat.daemon.restarted") and len(events(p, "ergostat.daemon.started")) == 2
    assert [r["data"]["exit"] for r in events(p, "agent.ran")] == [0, 0]


SENSORS = """
name: s
daemons:
  shared: {run: python3 d.py, concurrency: 50}
stocks:
"""


def test_a_shared_sensor_daemon_serves_fifty_sensors(tmp_path):
    text = SENSORS + "".join(f"  s{i}:\n    unit: things\n    sensor: {{daemon: shared, every: 1s}}\n" for i in range(50))
    p = setup(tmp_path, text)
    e = start(p)
    try:
        def read():
            return all((got := p.measurements.latest(f"sensor/s{i}.main", time.time())) and got[1] == i for i in range(50))
        assert wait_for(read, 10), "each sensor's reading from the one daemon"
        time.sleep(2.5)
        n = p.measurements.count()
    finally:
        e.close()
    assert len(starts(tmp_path)) == 1, "one process for fifty sensors"
    assert n >= 150, "read again on their schedules"
    assert not events(p, "sensor.failed"), [x["data"] for x in events(p, "sensor.failed")][:3]


def test_push_readings(tmp_path):
    (tmp_path / "p.py").write_text("import json, sys, time\nwhile True:\n"
                                   "    print(json.dumps({'reading': 7, 'sensor': 'q.main'}), flush=True)\n"
                                   "    print(json.dumps({'reading': 1, 'sensor': 'nope.main'}), flush=True)\n"
                                   "    time.sleep(0.2)\n")
    p = project(tmp_path, "name: s\nstocks:\n  q:\n    unit: things\n    sensor: {daemon: {run: python3 p.py}, push: true}\n")
    assert not p.model.spec.stocks["q"].sensors["main"].measured, "nothing asks it for readings"
    e = start(p)
    try:
        assert wait_for(lambda: (got := p.measurements.latest("sensor/q.main", time.time())) and got[1] == 7, 5)
    finally:
        e.close()
    assert "dropped" in (p.dir / "logs" / "daemon-sensor.q.main.log").read_text()


def test_daemons_are_checked(tmp_path):
    from ergostat.spec import read
    bad = KIND + """
daemons:
  d: {run: x, concurrency: 0, restart: {max: -1, backoff: [1s]}}
  e: {concurrency: 2}
stocks:
  a: {unit: n, sensor: {daemon: nope}}
  b: {unit: n, sensor: {run: echo 1, daemon: d}}
  c: {unit: n, sensor: {run: echo 1, push: true}}
blocks:
  w: {type: ai, prompt: hi, daemon: d}
  v: {type: program, run: x, daemon: d}
"""
    (tmp_path / "ergostat.yaml").write_text(bad)
    _, problems = read(tmp_path / "ergostat.yaml")
    said = "\n".join(x.message for x in problems if x.level == "error")
    for want in ("concurrency: a whole number", "restart.max", "restart.backoff", "daemon e: run:",
                 "sensor main.daemon: a map", "exactly one of run:, query:", "push: a daemon's sensor",
                 "block w: unknown key 'daemon'", "block v: daemon: is a program block's"):
        assert want in said, want


def test_daemons_on_the_agents_api(tmp_path):
    from ergostat.web import server
    p = setup(tmp_path, block("{run: python3 d.py}"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: item(p, "ticket/1").state == "done", 10)
        e.daemons.write()
        live = server.Live(p)
        ds = server.api(live, "daemons", {})
        one = server.api(live, "agents/worker", {})
    finally:
        e.close()
    d = ds["block.worker"]
    assert d["state"] == "running" and d["pid"] == starts(tmp_path)[0] and d["served"] == 1 and d["restarts"] == 0
    assert d["last_line"] and d["users"] == ["block.worker"]
    assert one["daemon"]["name"] == "block.worker" and one["daemon"]["state"] == "running"
    assert json.loads((p.dir / "daemons.json").read_text())["daemons"]["block.worker"]["state"] == "stopped"


def test_a_failed_daemon_gives_items_back_at_once_until_revived(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py crash, restart: {max: 1, within: 1m, backoff: [0.1s, 0.1s]}}"))
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "ergostat.daemon.failed"), 10)
        assert e.daemons.free("block.worker") == 0, "the dispatcher hands it nothing"
        from ergostat.leases.dispatch import Dispatcher
        p.events.add("ticket.opened", item="ticket/9", source="t")
        b = p.model.spec.blocks["worker"]
        t0 = time.time()
        out = e.run_block(b, "item", extra={}, item="ticket/9", fence=None, outcome=(o := {}))
        assert time.time() - t0 < 2 and out == [] and o["nack"]["count"] is False and o["nack"]["after"] > 0
        assert isinstance(e.dispatch, Dispatcher) and item(p, "ticket/9").state == "ready", "never taken while failed"
        (tmp_path / "ergostat.yaml").write_text(block("{run: python3 d.py, restart: {max: 1, within: 1m}}"))
        p.events.add("daemon.restart.requested", item="block.worker", source="person")
        e.daemons.revive("block.worker")
        assert e.daemons.slots["block.worker"].state in ("running", "starting")
    finally:
        e.close()


def test_a_crash_ends_the_daemons_whole_group_even_when_a_child_holds_its_output(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py kids-crash, restart: {max: 50, backoff: [5s, 5s]}}"))
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "ergostat.daemon.restarted"), 5), "the crash is seen though its child holds stdout"
        kid = int((tmp_path / "kid.pid").read_text())
        assert wait_for(lambda: not alive(kid), 5), "what it started goes with it"
    finally:
        e.close()


def test_runs_handed_over_while_the_daemon_is_swapped_are_never_stranded(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py, concurrency: 3}", pool=8))
    for i in range(12):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", data={"sleep": 0.3})
    e = start(p)
    try:
        for v in ("v2", "v3", "v4"):                 # swapped while items are being handed over
            time.sleep(0.4)
            (tmp_path / "ergostat.yaml").write_text(block(f"{{run: python3 d.py {v}, concurrency: 3}}", pool=8))
            e.swap(mdl.load(tmp_path))
        assert wait_for(lambda: all(item(p, f"ticket/{i}").state == "done" for i in range(12)), 30)
        assert max(len(x.proc.runs) for x in e.daemons.slots.values() if x.proc) <= 3
    finally:
        e.close()
    assert not [x for x in events(p, "agent.failed") if "stranded" in str(x["data"])]


def test_blocks_sharing_a_daemon_share_its_room(tmp_path):
    two = KIND + """
daemons:
  shared: {run: python3 d.py, concurrency: 2}
blocks:
  a: {type: program, takes: {kind: ticket, at: ready, where: {team: a}}, pool: 5, daemon: shared}
  b: {type: program, takes: {kind: ticket, at: ready, where: {team: b}}, pool: 5, daemon: shared}
"""
    p = setup(tmp_path, two)
    for i in range(6):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", data={"sleep": 0.8, "team": "ab"[i % 2]})
    e = start(p)
    most = 0
    try:
        end = time.time() + 15
        while time.time() < end and not all(item(p, f"ticket/{i}").state == "done" for i in range(6)):
            most = max(most, len(e.dispatch.going.get("a", {})) + len(e.dispatch.going.get("b", {})))
            time.sleep(0.02)
    finally:
        e.close()
    assert all(item(p, f"ticket/{i}").state == "done" for i in range(6)) and most <= 2


def test_a_failed_shared_sensor_daemon_is_said_once_not_per_sensor(tmp_path):
    text = """
name: s
daemons:
  shared: {run: python3 d.py crash, restart: {max: 0, backoff: [0.1s, 0.1s]}}
stocks:
""" + "".join(f"  s{i}:\n    unit: things\n    sensor: {{daemon: shared, every: 1s}}\n" for i in range(20))
    p = setup(tmp_path, text)
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "ergostat.daemon.failed"), 10)
        time.sleep(1)                                # (readings asked during its back-off, failed before it gave up)
        n = len(events(p, "sensor.failed"))
        time.sleep(3)
    finally:
        e.close()
    assert len(events(p, "ergostat.daemon.failed")) == 1 and len(events(p, "sensor.failed")) == n, "no failure per sensor"


def test_items_given_back_by_a_failed_daemon_are_taken_at_once_when_it_is_revived(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py crash, restart: {max: 0, backoff: [0.1s, 0.1s]}}"))
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "ergostat.daemon.failed"), 10)
        p.events.add("ticket.opened", item="ticket/9", source="t")
        e.dispatch.take(p.model.spec.blocks["worker"], item(p, "ticket/9"))   # (one on its way as it gave up)
        assert wait_for(lambda: [x for x in events(p, ENDED) if x["item"] == "ticket/9"], 5)
        assert (item(p, "ticket/9").fields["lease"].get("not_before") or 0) > time.time() + 30, "put off"
        e.daemons.revive("block.worker")             # (as d.py crashes still: revived with a working one)
        (tmp_path / "ergostat.yaml").write_text(block("{run: python3 d.py, restart: {max: 0}}"))
        e.swap(mdl.load(tmp_path))
        assert wait_for(lambda: item(p, "ticket/9").state == "done", 10), "taken at once, not after its put-off"
    finally:
        e.close()


def test_a_draining_daemon_whose_child_holds_its_output_is_seen_ended(tmp_path, monkeypatch):
    monkeypatch.setattr(kill, "GRACE", 30.0)         # (not the idle grace: its exit is what ends it)
    p = setup(tmp_path, block("{run: python3 d.py kids}"))
    e = start(p)
    try:
        assert wait_for(lambda: (tmp_path / "kid.pid").exists() and (tmp_path / "kid.pid").read_text(), 5)
        kid = int((tmp_path / "kid.pid").read_text())
        (tmp_path / "ergostat.yaml").write_text(block("{run: python3 d.py v2}"))
        e.swap(mdl.load(tmp_path))                   # drained: it ends on stop, its child still holding its output
        assert wait_for(lambda: not alive(kid), 8), "its exit seen, its group ended"
        assert not e.daemons.draining
    finally:
        e.close()


def test_a_run_whose_lease_ends_while_it_waits_for_room_is_never_handed_over(tmp_path):
    """Its lease is read when there is room; the room is taken before it is held; it waits, and its lease ends."""
    from ergostat.daemons.proc import Handle
    from ergostat.leases import TAKEN
    p = setup(tmp_path, block("{run: python3 d.py, concurrency: 1}", "{ttl: 2s, attempts: 3}", pool=1))
    p.events.add("ticket.opened", item="ticket/2", source="t", data={"sleep": 0.1})
    p.events.add(TAKEN, item="ticket/2", source="ergostat", data={"run": "r2", "block": "worker", "fence": 1, "ttl": 2.0,
                                                                   "max": 3, "back": "ready"})   # (held: not dispatched)
    e = start(p)
    out: dict = {}
    sup, real, taken = e.daemons, e.daemons._leased, []

    def leased_then_room_taken(*a):                  # read while still its own; then the room is taken before it is held
        ok = real(*a)
        if ok and not taken:
            pr = sup.slots["block.worker"].proc
            with pr.lock:
                pr.runs["filler"] = taken.append(1) or Handle()
            threading.Timer(4.0, lambda: pr.runs.pop("filler", None)).start()   # (past its lease's TTL)
        return ok
    sup._leased = leased_then_room_taken
    try:
        e.run_block(p.model.spec.blocks["worker"], "item", extra={"item": {"id": "ticket/2", "fields": {"sleep": 0.1}},
                                                                   "lease": {"fence": 1}},
                    item="ticket/2", fence=1, run_id="r2", outcome=out)
    finally:
        e.close()
    assert taken, "its lease was read while its own, and the room taken after"
    assert out["note"] == "its lease ended before it was handed over", out
    assert not [x for x in events(p, "ticket.started") if x["causedby"] == "r2"], "the daemon never got it"


def test_a_simple_command_is_execd_and_anything_else_left_to_its_shell():
    from ergostat.daemons.proc import execd
    assert execd("python3 d.py crash") == "exec python3 d.py crash"
    assert execd('./run.sh "a b" \'c;d\'') == 'exec ./run.sh "a b" \'c;d\''
    assert execd("python3 d.py\n") == "exec python3 d.py"            # a YAML block scalar's newline
    assert execd("prog a#b") == "exec prog a#b"
    for left in ("A=1 prog", "cd x && prog", "a | b", "prog > log", "prog &", "if true; then p; fi", "a\nb",
                 "echo $(x)", "echo `x`", '"unbalanced', "", "exec prog", "source env.sh",
                 "prog a#b; other", "prog # c; other", "read x", "pushd d", "let x=1", "declare -x A=1"):
        assert execd(left) == left, left


PIDS = "import os, time; open({out!r}, 'w').write(str(os.getpid())); time.sleep(30)"


def test_the_pid_recorded_is_the_programs_and_a_kill_reaches_it_through_a_shell(tmp_path):
    """Debian's sh (dash) forks for ``sh -c CMD`` where macOS's execs: ``execd`` makes the pid the program's on both;
    a command its shell must stay for still has the program killed, by the session's group."""
    import subprocess
    import sys

    from ergostat.costs.sampler import Measured
    from ergostat.daemons.proc import execd
    from ergostat.daemons.supervise import killpg

    def started(cmd, out):
        p = Measured(execd(cmd), shell=True, start_new_session=True, stdin=subprocess.DEVNULL)
        assert wait_for(lambda: out.exists() and out.read_text(), 10)
        return p, int(out.read_text())

    exe = sys.executable
    p, pid = started(f'"{exe}" -c "{PIDS.format(out=str(tmp_path / "a"))}"', tmp_path / "a")
    try:
        assert pid == p.pid
    finally:
        killpg(p.pid, 1.0)
        p.wait(5)
    p, pid = started(f'true && "{exe}" -c "{PIDS.format(out=str(tmp_path / "b"))}"', tmp_path / "b")
    killpg(p.pid, 1.0)
    p.wait(5)
    assert wait_for(lambda: not alive(pid), 5), "the program in the shell's group is killed with it"


def test_a_short_lived_daemon_is_sampled_before_it_ends(tmp_path):
    (tmp_path / "short.py").write_text("import time\ntime.sleep(4)\n")
    p = project(tmp_path, "name: s\nstocks:\n  q:\n    unit: things\n    sensor: {daemon: {run: python3 short.py}, push: true}\n")
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "ergostat.daemon.started"), 5)
        slot = next(iter(e.daemons.slots.values()))
        seen = []

        def sampled():
            t, proc = slot.tracked, slot.proc
            if t is not None and proc is not None and t.samples >= 1:
                seen.append(proc.proc.poll() is None)        # (alive at the moment its count is read)
                return True
            return False
        assert wait_for(sampled, 3), "sampled within 3 s of its start, not only every 30 s"
        assert seen[-1], "while it was still running"
    finally:
        e.close()


MANY = r'''
import json, sys
for line in sys.stdin:
    m = json.loads(line)
    if m["op"] == "item":
        r = m["run"]
        sys.stdout.write("".join(json.dumps({"event": "x.seen", "item": m["item"], "data": {"i": n}, "run": r}) + "\n"
                                 for n in range(1200)) + json.dumps({"event": "ticket.done", "run": r}) + "\n"
                         + json.dumps({"done": 0, "run": r}) + "\n")      # (done: the item leaves ready, never taken again)
        sys.stdout.flush()
    elif m["op"] == "stop":
        break
'''


def test_a_daemon_runs_1200_lines_are_all_recorded_in_order(tmp_path):
    (tmp_path / "many.py").write_text(MANY)
    p = project(tmp_path, block("{run: python3 many.py}"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "agent.ran"), 20)
    finally:
        e.close()
    assert events(p, "agent.ran")[0]["data"]["exit"] == 0
    started = events(p, "agent.started")
    assert len(started) == 1, "one run of the item (a second take would print its 1,200 lines again)"
    seen = events(p, "x.seen")
    assert [x["data"]["i"] for x in seen] == list(range(1200)), "every line, in the order printed"
    assert {x["causedby"] for x in seen} == {started[0]["id"]} and {x["item"] for x in seen} == {"ticket/1"}

