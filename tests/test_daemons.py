"""Daemons (SPEC §9.7): long-lived processes that blocks' runs and sensors' readings are handed to as JSON lines, many
at once, supervised: restarted when they crash, go silent or stop reading their input; given up (an alarm and an
intervention) after too many restarts; ``cancel`` on a lease's expiry; drained and replaced on a model swap."""

import json
import os
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
    f = events(p, "ergostat.daemon.failed")[0]
    assert f["item"] == "block.worker" and f["data"]["intervention"] is True
    assert f["data"]["class"] == "alarm:daemon:block.worker" and f["data"]["users"] == ["block.worker"]
    from ergostat import state as st
    att = [a for a in st.attention(st.snapshot(p)) if a["what"] == "daemon block.worker"]
    assert att and att[0]["level"] == "bad" and "given up after 3 restarts" in att[0]["says"]


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
