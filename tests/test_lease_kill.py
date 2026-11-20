"""A run whose lease expired is killed (SPEC §9.5, *Fencing*; the owner, 2026-11-18): its process tree gets SIGTERM,
then SIGKILL after the grace; ``ergostat.run.killed`` says why; the run's cost is recorded as any run's; its item
goes back and is taken again. A run that renews its lease is never killed."""

import os

from ergostat.leases import EXPIRED, kill
from ergostat.leases.kill import KILLED

from .test_leases import item, model, project, start, wait_for

FIRST = 'if [ ! -f first ]; then touch first; {silent}; fi; echo "{{\\"event\\": \\"ticket.done\\"}}"'


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def pid_in(path) -> int:
    assert wait_for(lambda: path.exists() and path.read_text().strip(), 5)
    return int(path.read_text())


def one(tmp_path, silent: str, lease: str = "{ttl: 1s, attempts: 3}"):
    p = project(tmp_path, model(FIRST.format(silent=silent), lease).replace("pool: 2", "pool: 1"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    return p


def test_an_expired_run_is_killed_with_its_children(tmp_path):
    kid = ("python3 -c 'import os, time; os.setsid(); open(\"kid.pid\", \"w\").write(str(os.getpid())); "
           "time.sleep(60)' & sleep 60 & echo $! > sleep.pid; wait")
    p = one(tmp_path, kid)
    e = start(p)
    try:
        own, other = pid_in(tmp_path / "sleep.pid"), pid_in(tmp_path / "kid.pid")
        got = wait_for(lambda: p.events.query(n=None, type=KILLED), 10)
        assert got, "killed once its lease expired"
        assert wait_for(lambda: not alive(own) and not alive(other), 5), "its children too, even in a session of their own"
    finally:
        e.close()
    k = got[0]
    assert k["item"] == "worker" and k["data"]["item"] == "ticket/1" and k["data"]["fence"] == 1
    assert k["data"]["signal"] == "TERM" and "expired" in k["data"]["why"]
    assert {own, other} <= set(k["data"]["pids"])
    assert k["causedby"] == p.events.query(n=None, type=EXPIRED)[0]["data"]["run"]


def test_a_run_that_ignores_term_is_killed_after_the_grace(tmp_path, monkeypatch):
    monkeypatch.setattr(kill, "GRACE", 1.0)
    p = one(tmp_path, "trap '' TERM; sleep 60 & echo $! > sleep.pid; wait; sleep 60")
    e = start(p)
    try:
        pid = pid_in(tmp_path / "sleep.pid")
        got = wait_for(lambda: p.events.query(n=None, type=KILLED), 12)
        assert got and got[0]["data"]["signal"] == "KILL" and got[0]["data"]["grace"] == 1.0
        assert not alive(pid)
    finally:
        e.close()


def test_a_renewing_run_is_not_killed(tmp_path):
    renew = ('for i in 1 2 3 4 5 6; do $ERGOSTAT_CMD lease --renew; sleep 0.4; done; '
             'echo "{\\"event\\": \\"ticket.done\\"}"')
    p = project(tmp_path, model(renew, "{ttl: 1s}"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: item(p, "ticket/1").state == "done", 20)
    finally:
        e.close()
    assert not p.events.query(n=None, type=KILLED)
    assert [h["how"] for h in item(p, "ticket/1").fields["lease"]["history"]] == ["ack"]


def test_the_killed_runs_item_returns_and_its_cost_is_recorded(tmp_path):
    p = one(tmp_path, "sleep 60")
    e = start(p)
    try:
        assert wait_for(lambda: item(p, "ticket/1").state == "done", 15), "taken again, and done by the next run"
        assert wait_for(lambda: p.events.query(n=None, type="agent.failed", item="worker"), 5)
    finally:
        e.close()
    lease = item(p, "ticket/1").fields["lease"]
    assert [h["how"] for h in lease["history"]] == ["expired", "ack"], "not ended again when the killed run ended"
    failed = p.events.query(n=None, type="agent.failed", item="worker")[0]["data"]
    assert failed["note"].startswith("killed: its lease on ticket/1 expired")
    assert failed["resources"]["processes_peak"] >= 1 and "cpu" in failed["resources"], "its cost measured as any run's"
    assert failed["seconds"] < 30, "stopped, not left to run its minute"


def test_a_run_this_engine_did_not_start_is_not_signalled(tmp_path):
    """A lease held by a run left behind (another engine's, or a process the test started) expires; nothing is killed."""
    import subprocess

    from .test_leases import take
    p = project(tmp_path, model('echo "{\\"event\\": \\"ticket.done\\"}"', "{ttl: 1s}"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    outsider = subprocess.Popen(["sleep", "30"], start_new_session=True)
    take(p, "ticket/1", "left-behind", 1, ttl=1.0)
    e = start(p)
    try:
        assert wait_for(lambda: p.events.query(n=None, type=EXPIRED), 10)
        assert wait_for(lambda: item(p, "ticket/1").state == "done", 10), "taken again and done"
        assert not kill.kill(e, "left-behind", "a test"), "nothing of this engine's to stop"
    finally:
        e.close()
    try:
        assert outsider.poll() is None and not p.events.query(n=None, type=KILLED)
    finally:
        outsider.kill()
        outsider.wait()


def test_the_grace_is_read_at_each_kill_with_a_safe_fallback(monkeypatch):
    for raw, want in (("2.5", 2.5), ("soon", 10.0), ("-1", 10.0), ("", 10.0)):
        monkeypatch.setenv("ERGOSTAT_KILL_GRACE", raw)
        assert kill.grace() == want
