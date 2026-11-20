"""Warm daemons (SPEC §9.7, *Warm*): ``warm: true`` is the owner's promise that the program keeps no state between
runs; its ``concurrency`` processes each hold one run at a time, so the CPU its group used while it held the run is
that run's. A process that misbehaves is restarted; one cancelled, or past ``recycle:``, replaced. Each test here is
a failure of the first attempt (branch ``warm``), made impossible."""

import json
import os
import subprocess
import sys

from ergostat.spec.engine import STOP_ASKED

from .test_daemons import alive, events, starts
from .test_leases import KIND, item, project, start, wait_for

WARM = r'''
import json, os, queue, subprocess, sys, threading, time
mode = sys.argv[1] if len(sys.argv) > 1 else ""
open("starts.log", "a").write(f"{os.getpid()}\n")
q, count, last, seen = queue.Queue(), 0, None, []
threading.Thread(target=lambda: [q.put(json.loads(x)) for x in sys.stdin] + [q.put({"op": "stop"})], daemon=True).start()
def say(**o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
while (m := q.get())["op"] != "stop":
    if m["op"] != "item":
        continue
    r, f, env = m["run"], m["input"]["item"]["fields"], m["env"]
    count += 1
    seen.append(m["item"])
    if "late" in mode and last:                  # the item before's done, again, late
        say(done=0, run=last)
    if "loose" in mode:
        say(done=0.0, run=r); say(done=True, run=r); say(done=0, run=r, extra=1)
    if "stateful" in mode:                       # keeps what it saw: the promise broken
        f = {**f, "seen": len(seen)}
    if "envleak" in mode:
        os.environ.update(env)
    say(event="ticket.started", run=r, data={"pid": 0 if "quiet" in mode else os.getpid(), "keys": sorted(env), "seen": f.get("seen"),
        "env_item": env.get("ERGOSTAT_ITEM"), "proc": sorted(k for k in os.environ if k.startswith("ERGOSTAT_I"))})
    if "burn" in mode:                           # a child that burns CPU, reaped before done
        subprocess.run([sys.executable, "-c", "import time\nt = time.process_time()\n"
                        "while time.process_time() - t < 0.6: pass"])
    if "leave" in mode and count == 1:
        k = subprocess.Popen(["sleep", "600"]); open("kid.pid", "w").write(str(k.pid))
    end = time.time() + float(f.get("sleep", 0.05))
    stopped = False
    while time.time() < end and not stopped:
        try:
            c = q.get(timeout=0.02)
            stopped = c.get("op") == "cancel" and c.get("run") == r
        except queue.Empty:
            pass
    if not stopped:
        say(event="ticket.done", run=r)
    say(done=1 if stopped else 0, run=r)
    last = r
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


def setup(tmp_path, daemon: str, **kw):
    (tmp_path / "w.py").write_text(WARM)
    return project(tmp_path, block(daemon, **kw))


def run_all(p, n: int, fields=None, seconds: float = 20.0):
    for i in range(n):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", data=(fields or {}).get(i, {}))
    e = start(p)
    try:
        assert wait_for(lambda: all(item(p, f"ticket/{i}").state == "done" for i in range(n)), seconds)
    finally:
        e.close()


def started(p) -> list[dict]:
    return [x["data"] for x in events(p, "ticket.started")]


def test_warm_processes_hold_one_item_at_a_time_and_are_reused(tmp_path):
    p = setup(tmp_path, "{run: python3 w.py, warm: true, concurrency: 2}")
    run_all(p, 8, {i: {"sleep": 0.2} for i in range(8)})
    assert len(starts(tmp_path)) == 2, "two processes served eight items"
    by = {}
    for r in events(p, "agent.started") + events(p, "agent.ran"):
        by.setdefault(r["causedby"] or r["id"], []).append(r["time"])
    ran = events(p, "agent.ran")
    assert len(ran) == 8 and all(r["data"]["resources"]["method"] == "warm" for r in ran)
    pids = [d["pid"] for d in started(p)]
    for pid in set(pids):                            # each process: its runs one after another, never two at once
        spans = sorted((s["time"], e["time"]) for s, d in zip(events(p, "ticket.started"), started(p), strict=True)
                       if d["pid"] == pid for e in events(p, "ticket.done") if e["item"] == s["item"])
        assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False))


def test_a_childs_cpu_is_charged_to_its_item(tmp_path):
    p = setup(tmp_path, "{run: python3 w.py burn, warm: true, concurrency: 1}")
    run_all(p, 2, seconds=30)
    for r in events(p, "agent.ran"):                 # (the child burned 0.6 s and was reaped before done)
        assert 0.55 <= r["data"]["resources"]["cpu"] < 1.5, r["data"]["resources"]


def test_no_items_environment_reaches_the_process_or_the_next_item(tmp_path):
    p = setup(tmp_path, "{run: python3 w.py, warm: true, concurrency: 1}")
    run_all(p, 3)
    got = started(p)
    assert len({d["pid"] for d in got}) == 1
    for d in got:
        assert d["proc"] == [], "no ERGOSTAT_ITEM in the process's own environment"
        assert {"ERGOSTAT_RUN", "ERGOSTAT_ITEM", "ERGOSTAT_LEASE"} <= set(d["keys"]), "each item's, complete, in its line"
    from ergostat.daemons.proc import SHARED
    assert not {"ERGOSTAT_WORKDIR", "ERGOSTAT_COMMAND", "ERGOSTAT_CONTEXT"} & SHARED, "per item: in its line only"
    assert sorted(d["env_item"] for d in got) == [f"ticket/{i}" for i in range(3)]


def test_a_late_or_loose_done_never_ends_the_next_item_and_recycles_the_process(tmp_path):
    p = setup(tmp_path, "{run: python3 w.py late-loose, warm: true, concurrency: 1, restart: {backoff: [0.1s, 1s]}}")
    run_all(p, 3, seconds=30)
    assert len(events(p, "ticket.done")) == 3, "each item ended by its own done, after its work"
    why = [x["data"]["why"] for x in events(p, "ergostat.daemon.restarted")]
    assert why and all("no run it holds" in w for w in why), why
    assert len(starts(tmp_path)) >= 2
    from ergostat import runner
    text = runner.log_path(p, "daemon-block.worker#1").read_text()
    assert '"done": 0.0' in text and '"done": true' in text, "loose dones dropped, never taken as exit 0"


def test_the_owners_stop_is_said_only_on_the_run_it_stopped(tmp_path):
    p = setup(tmp_path, "{run: python3 w.py, warm: true, concurrency: 2}")
    p.events.add("ticket.opened", item="ticket/0", source="t", data={"sleep": 0.05})
    p.events.add("ticket.opened", item="ticket/1", source="t", data={"sleep": 30})
    e = start(p)
    try:
        assert wait_for(lambda: item(p, "ticket/0").state == "done" and item(p, "ticket/1").state == "doing", 10)
        p.events.add(STOP_ASKED, item="worker", source="person", data={"note": ""})
        e.stop_run("worker")
        assert wait_for(lambda: len(events(p, "agent.ran") + events(p, "agent.failed")) >= 2, 10)
        assert wait_for(lambda: len(starts(tmp_path)) == 3, 5), "the stopped run's process replaced"
    finally:
        e.close()
    runs = {r["data"]["item"]: r["data"] for r in events(p, "agent.ran") + events(p, "agent.failed")}
    assert "note" not in runs["ticket/0"], "the run that finished well is not said stopped"
    assert runs["ticket/1"]["note"] == "stopped as the owner asked"
    assert not events(p, "ergostat.daemon.restarted"), "a cancelled run's process is replaced, uncounted"


def test_a_process_leaving_a_child_running_is_recycled_with_its_group(tmp_path):
    p = setup(tmp_path, "{run: python3 w.py leave, warm: true, concurrency: 1, restart: {backoff: [0.1s, 1s]}}")
    run_all(p, 2)
    kid = int((tmp_path / "kid.pid").read_text())
    assert wait_for(lambda: not alive(kid) or _zombie(kid), 15), "the child it left was killed with its group"
    first = events(p, "agent.ran")[0]["data"]["resources"]
    assert first["left_running"] == 1
    assert "left 1 process" in events(p, "ergostat.daemon.restarted")[0]["data"]["why"]
    assert len({d["pid"] for d in started(p)}) == 2, "the next item on a fresh process"


def _zombie(pid: int) -> bool:
    r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return r.stdout.strip().startswith("Z")


def test_processes_are_recycled_after_m_items_uncounted(tmp_path):
    p = setup(tmp_path, "{run: python3 w.py, warm: true, concurrency: 1, recycle: 2}")
    run_all(p, 5)
    pids = [d["pid"] for d in sorted(started(p), key=lambda d: d["env_item"])]
    assert len(set(pids)) == 3 and len(starts(tmp_path)) >= 3
    assert not events(p, "ergostat.daemon.restarted"), "recycling is not a restart: never counted toward giving up"


def test_the_check_finds_state_kept_between_items(tmp_path):
    (tmp_path / "w.py").write_text(WARM)
    given = tmp_path / "input.json"
    given.write_text(json.dumps({"item": {"id": "ticket/1", "fields": {}}}))
    out = {}
    for mode in ("quiet", "quiet-stateful"):
        project(tmp_path, block(f"{{run: python3 w.py {mode}, warm: true, concurrency: 1}}"))
        r = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "block", "worker", "--check-warm",
                            str(given)], capture_output=True, text=True, timeout=60,
                           env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")})
        out[mode] = (r.returncode, r.stdout)
    assert out["quiet"][0] == 0 and "no state kept" in out["quiet"][1], out
    assert out["quiet-stateful"][0] == 1 and "state kept between runs" in out["quiet-stateful"][1], out
    assert "four times" in out["quiet"][1]
    project(tmp_path, block("{run: python3 w.py, warm: true, concurrency: 1}"))      # (its pid in what it prints)
    r = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "block", "worker", "--check-warm",
                        str(given)], capture_output=True, text=True, timeout=60,
                       env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")})
    assert r.returncode == 2 and "not deterministic" in r.stdout


def test_warm_is_checked(tmp_path):
    from ergostat.spec import read

    def said(text: str) -> str:
        (tmp_path / "ergostat.yaml").write_text(text)
        return "\n".join(x.message for x in read(tmp_path / "ergostat.yaml")[1] if x.level == "error")
    bad = {"{run: x, warm: 1}": "warm: true or false", "{run: x, recycle: 5}": "recycle: only with it",
           "{run: x, warm: true, recycle: 0}": "recycle: a whole number"}
    for d, says in bad.items():
        assert says in said(block(d)), d
    assert said(block("{run: x, warm: true, recycle: 50}")) == ""
    assert "serves blocks' runs only" in said(KIND + """
daemons:
  w: {run: x, warm: true}
stocks:
  s:
    unit: things
    sensor: {daemon: w, every: 1m}
""")
