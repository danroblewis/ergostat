"""The repair loop's verification and revert (SPEC §12r): an applied fix judged by the runs of its block begun after it
(by seq), verified after ``verify`` good runs or regressed at a failed one, and a regressed fix's gated ``revert-fix``
(one ``git revert``, under the failure's lock, aborted and checked when git fails). These run without the OS sandbox:
the collector is not read-only and the template has no test, so a fix goes untested to its approval."""

import contextlib
import fcntl
import json
import os
import re
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.actions import gate
from ergostat.actions import record as actions
from ergostat.inbox import entries
from ergostat.repair import FAILURE
from ergostat.repair import apply as rapply
from ergostat.sandbox import git as sgit
from ergostat.spec import items as its
from ergostat.spec import read as read_spec
from ergostat.spec.counts import Counts
from ergostat.store import Project
from tests.test_repair2 import FIXED, broken, fixed, git, one, project

PY = sys.executable
BAD = json.dumps({"issues": [{"key": "DEMO-1"}]})            # the tracker's old answer: the fixed collector fails on it


@pytest.fixture(autouse=True)
def _quick(monkeypatch):
    monkeypatch.setenv("ERGOSTAT_IMPACT_SECONDS", "3")
    yield
    from ergostat import runner
    runner.STOPPING.clear()


@pytest.fixture
def made(tmp_path, monkeypatch):
    """A project whose collector failed, was fixed and the fix applied: (p, e, fid, root, base)."""
    engines = []

    def make(sub="a", **kw):
        p, e = project(tmp_path / sub, monkeypatch, read_only="false", **kw)
        engines.append(e)
        root = p.model.path.parent
        base = git("rev-parse", "HEAD", cwd=root)
        fid = broken(p, e)
        it = fixed(p, e, fid)
        assert it.state == "awaiting-approval", (it.state, it.fields.get("test"))
        gate.approve(p, p.model.spec, actions.about(p, fid)[0]["id"])
        assert one(p, fid).state == "applied", actions.about(p, fid)[0]
        return p, e, fid, root, base
    yield make
    for e in engines:
        e.close()


def run(p, ok=True, note="exited 1", code=1, at=None, block="collector") -> str:
    """One run of the block as the engine records it: its agent.started, and its end caused by it."""
    s = p.events.add("agent.started", item=block, source="engine", at=at)
    p.events.add("agent.ran" if ok else "agent.failed", item=block, source="engine", causedby=s["id"], at=at,
                 data={} if ok else {"exit": code, "note": note})
    return s["id"]


def moves(p, fid) -> list[str]:
    return [x["type"].rsplit(".", 1)[1] for x in p.events.query(n=None, item=fid) if x["type"].startswith(FAILURE)]


def reverts(p, fid) -> list[dict]:
    return [a for a in actions.about(p, fid) if a["action"] == "revert-fix"]


def regressed(made, sub="a"):
    """Applied, then the collector failed again on the old answer, and settle judged it: (p, e, fid, root, base, commit)."""
    p, e, fid, root, base = made(sub)
    (root / "answer.json").write_text(BAD)
    e.run_block(p.model.spec.blocks["collector"], "test")
    git("checkout", "--", "answer.json", cwd=root)
    rapply.settle("3", p)
    it = one(p, fid)
    assert it.state == "regressed", (it.state, it.fields.get("verdict"))
    return p, e, fid, root, base, it.fields["commit"]


def revert_commits(root, commit) -> list[str]:
    return git("log", "--format=%H", "-F", f"--grep=This reverts commit {commit}.", cwd=root).split()


def files(root: Path) -> dict[str, bytes]:
    return {f: (root / f).read_bytes() for f in [*git("ls-files", cwd=root).split(), "untracked.txt"]}


# ---- verification


def test_a_fix_is_verified_after_verify_good_runs_begun_after_it(made):
    p, e, fid, root, base = made()
    seq = p.events.query(n=1, type=f"{FAILURE}.applied", item=fid)[0]["seq"]
    for _ in range(2):
        e.run_block(p.model.spec.blocks["collector"], "test")
    rapply.settle("3", p)
    assert one(p, fid).state == "applied", "two of three"
    e.run_block(p.model.spec.blocks["collector"], "test")
    rapply.settle("3", p)
    it = one(p, fid)
    ran = [x["id"] for x in p.events.query(n=None, type="agent.started", item="collector", after_seq=seq)]
    assert it.state == "verified" and it.fields["verdict"]["runs"] == ran and len(ran) == 3
    assert it.fields["verdict"]["after_seq"] == seq and it.fields["verdict"]["verify"] == \
        {"used": 3, "asked": "3", "clamped": False}


def test_a_failed_run_after_the_fix_regresses_it_and_asks_for_revert_fix_once(made):
    p, e, fid, root, base = made()
    count = one(p, fid).fields["count"]
    (root / "answer.json").write_text(BAD)
    e.run_block(p.model.spec.blocks["collector"], "test")
    it = one(p, fid)
    assert it.state == "applied" and it.fields["count"] == count + 1, "counted, not reopened"
    assert [m["to"] for m in it.moves][-1] == "applied" and [m["to"] for m in it.moves].count("open") == 1
    assert [r["type"] for r in it.refused] == [f"{FAILURE}.opened"], "the fold refused it: moves only from noted, ..."
    last = p.events.query(n=1, type=f"{FAILURE}.opened", item=fid)[0]
    assert "revert_key" not in last["data"], "an opened the fold refuses clears nothing"
    rapply.settle("3", p)
    it = one(p, fid)
    name, commit = fid.split("/")[1], it.fields["commit"]
    assert it.state == "regressed" and it.fields["revert_key"] == f"{name}-{commit}"
    v = it.fields["verdict"]
    assert v["same"] is True and v["failure"] == fid and v["note"].startswith("exited") and v["runs"] == []
    assert [(a["key"], a["state"]) for a in reverts(p, fid)] == [(f"{name}-{commit}", "requested")]
    rapply.settle("3", p)
    rapply.settle("3", p)
    assert len(reverts(p, fid)) == 1, "never asked twice"
    e.run_block(p.model.spec.blocks["collector"], "test")
    assert one(p, fid).state == "regressed", "a regressed failure is not reopened"


def test_a_run_ended_by_timeout_or_kill_counts_neither_way(made):
    p, e, fid, root, base = made()
    run(p, ok=False, note="stopped after its timeout of 2s", code=None)
    run(p, ok=False, note="killed: by the owner", code=-9)
    run(p, ok=False, note="", code=-15)                     # a signal
    run(p, ok=False, note="could not start: no such file", code=None)
    rapply.settle("3", p)
    assert one(p, fid).state == "applied" and moves(p, fid)[-1] == "applied"
    good = [run(p) for _ in range(3)]
    rapply.settle("3", p)
    it = one(p, fid)
    assert it.state == "verified" and it.fields["verdict"]["runs"] == good


FLOOD = 40                                                  # runs after the decisive ones: above 10 x verify (30)


def test_a_failed_first_run_regresses_the_fix_however_many_runs_follow_it(made):
    p, e, fid, root, base = made()
    first = run(p, ok=False)
    for _ in range(FLOOD):
        run(p)
    rapply.settle("3", p)
    it = one(p, fid)
    assert it.state == "regressed" and it.fields["verdict"]["run"] == first, it.fields.get("verdict")
    assert len(reverts(p, fid)) == 1


def test_three_good_first_runs_verify_the_fix_however_many_runs_follow_them(made):
    p, e, fid, root, base = made()
    good = [run(p) for _ in range(3)]
    for _ in range(FLOOD):
        run(p, ok=False)
    rapply.settle("3", p)
    it = one(p, fid)
    assert it.state == "verified" and it.fields["verdict"]["runs"] == good, it.fields.get("verdict")


def test_a_first_window_of_only_timeouts_is_not_verified_and_says_why(made, capsys):
    p, e, fid, root, base = made()
    for _ in range(30):
        run(p, ok=False, note="stopped after its timeout of 2s", code=None)
    for _ in range(3):
        run(p)
    rapply.settle("3", p)
    assert one(p, fid).state == "applied" and moves(p, fid)[-1] == "applied"
    assert "the first 30 runs begun since the fix decided nothing" in capsys.readouterr().err


@pytest.mark.parametrize("backend", ["sqlite", "segments"])
def test_the_store_reads_the_oldest_first_events(tmp_path, backend):
    from ergostat.segments import Segments
    from ergostat.store import Events
    ev = Events(tmp_path) if backend == "sqlite" else Segments(tmp_path, seal=4)
    ids = [ev.add("agent.started", item="b")["id"] for _ in range(11)]
    ev.add("agent.started", item="other")
    assert backend == "sqlite" or len(ev._state()[0]) >= 2, "read across sealed segments and the head"
    after = ev.query(n=None, item="b")[1]["seq"]            # the second one's
    assert [x["id"] for x in ev.query(first=3, type="agent.started", item="b")] == ids[:3]
    assert [x["id"] for x in ev.query(first=6, type="agent.started", item="b", after_seq=after)] == ids[2:8]
    assert [x["id"] for x in ev.query(first=50, type="agent.started", item="b")] == ids
    assert ev.query(first=0, item="b") == []


def test_settle_asks_the_revert_again_when_it_was_lost(made, monkeypatch):
    p, e, fid, root, base = made()
    run(p, ok=False)
    real, lost = gate.request, []

    def crash_once(*a, **kw):
        if not lost:
            lost.append(1)
            raise RuntimeError("crashed between the two writes")
        return real(*a, **kw)
    monkeypatch.setattr(gate, "request", crash_once)
    with pytest.raises(RuntimeError):
        rapply.settle("3", p)
    assert one(p, fid).state == "regressed" and not reverts(p, fid)
    rapply.settle("3", p)
    assert len(reverts(p, fid)) == 1 and reverts(p, fid)[0]["key"] == one(p, fid).fields["revert_key"]


# ---- the revert


def test_the_approved_revert_reverts_with_one_commit(made):
    p, e, fid, root, base, commit = regressed(made)
    gate.approve(p, p.model.spec, reverts(p, fid)[0]["id"])
    assert reverts(p, fid)[0]["state"] == "ran", reverts(p, fid)[0]
    it = one(p, fid)
    head = git("rev-parse", "HEAD", cwd=root)
    assert it.state == "reverted" and it.fields["revert"] == {"revert_commit": head, "of": commit}
    assert git("rev-parse", "HEAD~1", cwd=root) == commit and revert_commits(root, commit) == [head]
    assert git("rev-list", "--count", f"{base}..HEAD", cwd=root) == "2"
    assert git("log", "-1", "--format=%an", cwd=root) == "ergostat"


def test_the_revert_restores_the_programs_text_and_changes_nothing_else(made):
    p, e, fid, root, base, commit = regressed(made)
    gate.approve(p, p.model.spec, reverts(p, fid)[0]["id"])
    assert one(p, fid).state == "reverted"
    assert git("rev-parse", "HEAD^{tree}", cwd=root) == git("rev-parse", f"{base}^{{tree}}", cwd=root)
    tracked = git("ls-files", cwd=root).split()
    assert tracked == git("ls-tree", "-r", "--name-only", base, cwd=root).split()
    for f in tracked:
        was = subprocess.run(["git", "show", f"{base}:{f}"], cwd=root, capture_output=True, check=True).stdout
        assert (root / f).read_bytes() == was, f
    assert not git("status", "--porcelain", "--untracked-files=no", cwd=root)


def test_the_inbox_says_what_approving_a_revert_does(made):
    p, e, fid, root, base, commit = regressed(made)
    got = [x for x in entries.entries(p, p.model.spec) if x["kind"] == "action" and x["action"] == "revert-fix"]
    assert len(got) == 1
    assert got[0]["warn"] == entries.REVERTS.format(commit=commit[:12]) and commit[:12] in got[0]["warn"]
    assert "merges" not in got[0]["warn"].lower() and "merges" not in got[0]["why"].lower()
    assert entries.MERGES not in json.dumps(got[0])
    assert entries.warning(p, p.model.spec, {"item": fid, "action": "apply-fix"}) == entries.MERGES


def test_a_revert_whose_event_was_lost_is_found_not_made_again(made):
    p, e, fid, root, base, commit = regressed(made)
    git("-c", "user.email=t@t", "-c", "user.name=t", "revert", "--no-edit", commit, cwd=root)   # git done, no event
    head = git("rev-parse", "HEAD", cwd=root)
    aid = reverts(p, fid)[0]["id"]
    assert rapply.revert(p, aid, fid) == 0
    it = one(p, fid)
    assert it.state == "reverted" and it.fields["revert"]["revert_commit"] == head and it.fields["revert"]["found"]
    assert git("rev-parse", "HEAD", cwd=root) == head and revert_commits(root, commit) == [head]


# ---- lesson-1: read, decide, write under the failure's lock


def test_l1_an_approved_revert_run_twice_makes_one_revert_commit_and_stays_reverted(made):
    p, e, fid, root, base, commit = regressed(made)
    aid = reverts(p, fid)[0]["id"]
    gate.approve(p, p.model.spec, aid)
    head = git("rev-parse", "HEAD", cwd=root)
    again = subprocess.run([PY, "-m", "ergostat.repair", "revert"], cwd=root, capture_output=True, text=True,
                           env={**os.environ, "ERGOSTAT_ACTION": aid, "ERGOSTAT_ITEM": fid})
    assert again.returncode == 0 and "already reverted" in again.stdout, again.stderr
    assert revert_commits(root, commit) == [head] and git("rev-parse", "HEAD", cwd=root) == head
    assert one(p, fid).state == "reverted" and "revert-failed" not in moves(p, fid)


def test_l1_two_reverts_at_once_make_one_commit(made, monkeypatch):
    p, e, fid, root, base, commit = regressed(made)
    aid, name = reverts(p, fid)[0]["id"], fid.split("/")[1]
    held = open(p.dir / "repair" / "locks" / f"{name}.lock", "a")
    fcntl.flock(held, fcntl.LOCK_EX)
    real, waiting = fcntl.flock, threading.Semaphore(0)

    def flock(f, op):                                       # (each thread says it reached the lock)
        if threading.current_thread() is not threading.main_thread():
            waiting.release()
        return real(f, op)
    monkeypatch.setattr(fcntl, "flock", flock)
    rcs: list = []
    ts = [threading.Thread(target=lambda: rcs.append(rapply.revert(p, aid, fid))) for _ in range(2)]
    for t in ts:
        t.start()
    assert waiting.acquire(timeout=60) and waiting.acquire(timeout=60)
    real(held, fcntl.LOCK_UN)
    held.close()
    for t in ts:
        t.join(timeout=120)
    assert sorted(rcs) == [0, 0]
    assert len(revert_commits(root, commit)) == 1
    assert moves(p, fid).count("reverted") == 1 and "revert-failed" not in moves(p, fid)


@pytest.mark.parametrize("competing", ["applied-again", "moved-out"])
def test_l1_settle_rereads_inside_the_lock(made, monkeypatch, competing):
    p, e, fid, root, base = made()
    commit = one(p, fid).fields["commit"]
    for _ in range(3):
        run(p)
    real = rapply.locked

    @contextlib.contextmanager
    def in_between(p_, name):                               # between settle's listing and its lock
        if competing == "applied-again":                    # a newer applied (the fold: applied stays applied)
            p.events.add(f"{FAILURE}.applied", item=fid, source="ergostat", data={"commit": commit})
        else:                                               # moved out of applied (a person dismissing it)
            p.events.add(f"{FAILURE}.dismissed", item=fid, source="ergostat", data={})
        with real(p_, name):
            yield
    monkeypatch.setattr(rapply, "locked", in_between)
    rapply.settle("3", p)
    assert one(p, fid).state == ("applied" if competing == "applied-again" else "dismissed")
    assert not {"verified", "regressed"} & set(moves(p, fid)), moves(p, fid)


# ---- lesson-2, -3, -4, -5


def test_l2_runs_are_counted_after_the_applied_event_by_seq_not_time(made):
    p, e, fid, root, base = made()
    commit = one(p, fid).fields["commit"]
    now = time.time()
    early_seq_late_time = run(p, at=now + 1000)             # (recorded before the applied event below)
    p.events.add(f"{FAILURE}.applied", item=fid, source="ergostat", at=now, data={"commit": commit})
    late_seq_early_time = run(p, at=now - 1000)
    same_time = run(p, at=now)
    rapply.settle("2", p)
    it = one(p, fid)
    assert it.state == "verified" and it.fields["verdict"]["runs"] == [late_seq_early_time, same_time]
    assert early_seq_late_time not in it.fields["verdict"]["runs"]


@pytest.mark.parametrize("case", ["no-applied-event", "block-gone", "a-run-not-ended"])
def test_l3_a_failure_whose_runs_cannot_be_read_is_not_verified(made, monkeypatch, capsys, case):
    p, e, fid, root, base = made()
    if case == "a-run-not-ended":
        p.events.add("agent.started", item="collector", source="engine")
    for _ in range(3):
        run(p)
    if case == "no-applied-event":
        real = p.events.query
        monkeypatch.setattr(p.events, "query", lambda **kw: [] if kw.get("type") == f"{FAILURE}.applied" else real(**kw))
    if case == "block-gone":
        monkeypatch.delitem(p.model.spec.blocks, "collector")
    before = len(p.events.query(n=None, item=fid))
    rapply.settle("3", p)
    assert one(p, fid).state == "applied" and len(p.events.query(n=None, item=fid)) == before
    said = capsys.readouterr().err
    assert {"no-applied-event": "no applied event", "block-gone": "no longer in the model",
            "a-run-not-ended": "has not ended"}[case] in said, said


def test_l4_check_refuses_verify_out_of_range(tmp_path, monkeypatch):
    for i, bad in enumerate(("0", "51", "x")):
        with pytest.raises(mdl.ModelError, match="verify"):
            project(tmp_path / f"bad{i}", monkeypatch, read_only="false", with_=f", verify: {bad}")
    for i, good in enumerate(("1", "50")):
        p, e = project(tmp_path / f"good{i}", monkeypatch, read_only="false", with_=f", verify: {good}")
        e.close()
        assert p.model.spec.blocks["repair-settle"].params["run"].endswith(f"--verify {good}")


def test_l4_settle_clamps_verify_from_a_compiled_model_that_bypassed_check(made, monkeypatch):
    p, e, fid, root, base = made()
    b = e.spec.blocks["repair-settle"]
    monkeypatch.setattr(b, "params", {**b.params, "run": b.params["run"].replace("--verify 3", "--verify 5000")})
    assert "--verify 5000" in b.params["run"]
    for _ in range(3):
        run(p)
    e.run_block(b, "test")
    assert p.events.query(n=1, item="repair-settle", type="agent.ran"), "settle ran"
    assert one(p, fid).state == "applied", "5000 is not 3: still unverified"
    for _ in range(47):
        run(p)
    e.run_block(b, "test")
    it = one(p, fid)
    assert it.state == "verified" and len(it.fields["verdict"]["runs"]) == 50
    assert it.fields["verdict"]["verify"] == {"used": 50, "asked": "5000", "clamped": True}
    assert rapply.bounded("-3") == {"used": 1, "asked": "-3", "clamped": True}
    assert rapply.bounded("x")["used"] == 50 and rapply.bounded("x")["clamped"] is True


def test_l5_a_reopened_failure_clears_its_verdict_and_counts_from_the_newest_apply(made):
    p, e, fid, root, base = made()
    commit = one(p, fid).fields["commit"]
    for _ in range(3):
        run(p)
    rapply.settle("3", p)
    assert one(p, fid).state == "verified"
    (root / "answer.json").write_text(BAD)
    e.run_block(p.model.spec.blocks["collector"], "test")
    git("checkout", "--", "answer.json", cwd=root)
    it = one(p, fid)
    assert it.state == "open" and moves(p, fid)[-1] == "opened", "after verified, it comes back: reopened"
    assert (it.fields.get("verdict"), it.fields.get("revert"), it.fields.get("revert_key")) == (None, None, None)
    for _ in range(2):
        run(p)                                              # before the fix is applied again: not counted
    p.events.add(f"{FAILURE}.applied", item=fid, source="ergostat", data={"commit": commit})
    first = run(p)
    rapply.settle("3", p)
    assert one(p, fid).state == "applied", "the runs before the newest apply do not count"
    rest = [run(p) for _ in range(2)]
    rapply.settle("3", p)
    assert one(p, fid).fields["verdict"]["runs"] == [first, *rest]


def test_l5_an_old_cycles_revert_approval_cannot_revert_a_new_fix(made):
    p, e, fid, root, base, commit = regressed(made)
    name = fid.split("/")[1]
    old = gate.request(p, p.model.spec, "revert-fix", {}, {"block": "repair-settle", "item": fid}, asker="program",
                       key=f"{name}-{'a' * 40}")
    head, before = git("rev-parse", "HEAD", cwd=root), moves(p, fid)
    assert rapply.revert(p, old["id"], fid) == 1
    assert git("rev-parse", "HEAD", cwd=root) == head and moves(p, fid) == before and one(p, fid).state == "regressed"


# ---- lesson-6: a revert that fails or hangs


def test_l6_a_conflicting_revert_is_aborted_leaves_nothing_half_done_and_stays_regressed(made):
    p, e, fid, root, base, commit = regressed(made)
    (root / "collect.py").write_text(FIXED.replace('answer["values"]', 'answer.get("values", [])'))
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "the owner's own change", cwd=root)
    head, was = git("rev-parse", "HEAD", cwd=root), files(root)
    gate.approve(p, p.model.spec, reverts(p, fid)[0]["id"])
    assert reverts(p, fid)[0]["state"] == "failed"
    it = one(p, fid)
    assert it.state == "regressed" and it.fields["revert"]["aborted"] is True
    assert moves(p, fid)[-2:] == ["regressed", "revert-failed"] and "git" in it.fields["revert"]["why"]
    assert not (root / ".git" / "REVERT_HEAD").exists() and not (root / ".git" / "sequencer").exists()
    assert git("rev-parse", "HEAD", cwd=root) == head and files(root) == was
    assert not git("status", "--porcelain", "--untracked-files=no", cwd=root)


def test_l6_a_revert_whose_git_times_out_is_aborted_and_frees_the_lock(made, monkeypatch):
    p, e, fid, root, base, commit = regressed(made)
    real, seen = sgit._git, []

    def hangs(args, env, cwd, check, input=None):
        if "revert" in args:
            seen.append("--abort" if "--abort" in args else "revert")
            if "--no-edit" in args:
                raise subprocess.TimeoutExpired(["git", *args], 120)
        return real(args, env, cwd, check, input)
    monkeypatch.setattr(sgit, "_git", hangs)
    head = git("rev-parse", "HEAD", cwd=root)
    assert rapply.revert(p, reverts(p, fid)[0]["id"], fid) == 1
    it = one(p, fid)
    assert seen == ["revert", "--abort"], seen
    assert it.state == "regressed" and it.fields["revert"]["aborted"] is True, it.fields["revert"]
    assert "within 120s" in it.fields["revert"]["why"] and git("rev-parse", "HEAD", cwd=root) == head
    with open(p.dir / "repair" / "locks" / f"{fid.split('/')[1]}.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)        # at once: raises if it were still held


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    try:                                                    # (a zombie no one reaped has stopped too)
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
        return not r.stdout.strip() or r.stdout.strip().startswith("Z")


def test_l6_an_action_past_its_timeout_has_its_whole_process_group_killed(tmp_path):
    (tmp_path / "fork.py").write_text(textwrap.dedent("""\
        import os, subprocess
        c = subprocess.Popen(["sleep", "60"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        open("pid.tmp", "w").write(str(c.pid))
        os.rename("pid.tmp", "pid")
        null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null, 1)
        os.dup2(null, 2)                       # (nothing holds the action's output open: a kill of one is seen at once)
        c.wait()
        """))
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(f"""\
        name: pg
        actions:
          slow: {{run: "{PY} fork.py", gate: approve, in: ., timeout: 1s}}
        """))
    m = mdl.load(tmp_path)
    p = Project(m)
    a = gate.request(p, m.spec, "slow", {}, {}, asker="program")
    started = time.monotonic()
    got = gate.approve(p, m.spec, a["id"])
    assert time.monotonic() - started < 30, "run_once came back long after the action's timeout"
    assert got["state"] == "failed" and got["output"].startswith("stopped after its timeout"), got
    deadline = time.monotonic() + 30
    while not (tmp_path / "pid").exists():
        assert time.monotonic() < deadline, "the grandchild never started"
        time.sleep(0.05)
    pid = int((tmp_path / "pid").read_text())
    deadline = time.monotonic() + 10
    while not _gone(pid):
        if time.monotonic() > deadline:
            os.kill(pid, 9)                                 # (the test's own grandchild)
            pytest.fail("the action's grandchild outlived its timeout")
        time.sleep(0.05)


def test_a_dirty_tree_or_a_revert_in_progress_is_refused_not_touched(made):
    for sub, how in (("a", "staged"), ("b", "revert-head")):
        p, e, fid, root, base, commit = regressed(made, sub)
        if how == "staged":
            (root / "notes.txt").write_text("the owner's own work in progress")
            git("add", "notes.txt", cwd=root)
        else:
            (root / ".git" / "REVERT_HEAD").write_text(base + "\n")
        head, was = git("rev-parse", "HEAD", cwd=root), files(root)
        assert rapply.revert(p, reverts(p, fid)[0]["id"], fid) == 1
        it = one(p, fid)
        assert it.state == "regressed" and it.fields["revert"]["aborted"] is False
        assert ("not committed" if how == "staged" else "a revert is in progress") in it.fields["revert"]["why"]
        assert git("rev-parse", "HEAD", cwd=root) == head and files(root) == was
        assert how == "staged" or (root / ".git" / "REVERT_HEAD").read_text() == base + "\n"


# ---- fixes-hold: no fix regressed in the last 14 days (on the window, not on the stock)

DAY = 86400.0


def fixes_hold(p, e, at=None) -> tuple[str, float]:
    """fixes-hold as the engine works it out, fixes-regressed-recent (and the stock regressed-fixes) read at ``at``
    (default now): the record counted directly and through what the engine keeps of it (counts.py), which must agree.
    Returns the goal's status and the auxiliary's reading."""
    spec = p.model.spec
    at = time.time() if at is None else at
    got = {}
    for part in (spec.auxiliaries["fixes-regressed-recent"], spec.stocks["regressed-fixes"]):
        s = next(iter(part.sensors.values()))
        direct, _ = its.measure(p.events, spec, s, now=at)
        c = Counts(False)
        assert c.follow(p.events, spec, [s], now=at)
        assert c.value(spec, s, now=at) == (direct, ""), part.name
        p.measurements.add(s.series, direct)
        got[part.name] = direct
    e.evaluate()
    return e.status.get("fixes-hold"), got["fixes-regressed-recent"]


def test_the_template_has_fixes_hold_and_check_finds_it_served(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch)
    try:
        spec = p.model.spec
        g = spec.goals["fixes-hold"]
        assert str(g.of) == "auxiliary.fixes-regressed-recent" and f"{g.hold.op} {g.hold.value:g}" == "<= 0"
        assert g.tolerance == 0 and g.on_stale == "off"
        s = next(iter(spec.auxiliaries["fixes-regressed-recent"].sensors.values()))
        assert s.items["entering"] == "regressed" and s.items["over"] == 14 * DAY
        about = {"goal.fixes-hold", "auxiliary.fixes-regressed-recent"}
        mine = [f"{x.level} {x.code} {x.message}" for x in p.model.problems if x.about in about and x.level != "note"]
        assert not mine, mine
        assert spec.loop("fixes-hold").closes and "repair-settle" in spec.loop("fixes-hold").controllers
    finally:
        e.close()


def test_an_auxiliary_counts_moves_over_its_window_and_refuses_over_alone(tmp_path):
    head = "name: t\nitems:\n  issue: {id: issue/*, states: [open, closed], on: {issue.seen: open}}\nauxiliaries:\n"
    for sensor, error in (("{items: issue, entering: open, over: 1d}", None),
                          ("{items: issue, state: open, over: 1d}", "items-on-stock")):
        d = tmp_path / str(bool(error))
        d.mkdir()
        (d / "ergostat.yaml").write_text(head + f"  seen-lately: {{unit: issues, sensor: {sensor}}}\n")
        _, problems = read_spec(d / "ergostat.yaml", extremes=False)
        assert [x.code for x in problems if x.level == "error"] == ([error] if error else []), problems
    p = Project(mdl.load(tmp_path / "False"))
    for i in range(3):
        p.events.add("issue.seen", item=f"issue/{i}", source="t")
    s = next(iter(p.model.spec.auxiliaries["seen-lately"].sensors.values()))
    assert its.measure(p.events, p.model.spec, s) == (3.0, ""), "how many, not a rate per hour"
    assert its.measure(p.events, p.model.spec, s, now=time.time() + 2 * DAY) == (0.0, "")


def test_specs_parts_table_matches_the_template():
    """SPEC §12r's parts table names every part the template has, and no other."""
    import yaml
    t = yaml.safe_load((Path(mdl.__file__).parent / "library/templates/repair/template.yaml").read_text())
    spec = (Path(__file__).parents[1] / "docs/SPEC.md").read_text()
    table = spec[spec.index("| Part | What |", spec.index("## 12r.")):]
    table = table[:table.index("\n\n")]
    rows = {r.split("|")[1].strip(): r.split("|")[2] for r in table.splitlines()[2:]}
    assert set(rows) == {"stocks", "auxiliaries", "flows", "goals", "actions"}
    for k, row in rows.items():                         # the names outside brackets; what is in them says more
        assert set(re.findall(r"`([a-z-]+)`", re.sub(r"\([^)]*\)", "", row))) == set(t[k]), k


def test_a_regressed_fix_turns_fixes_hold_off(made):
    p, e, fid, root, base = made()
    assert fixes_hold(p, e) == ("holding", 0.0), "an applied fix not yet judged"
    (root / "answer.json").write_text(BAD)
    e.run_block(p.model.spec.blocks["collector"], "test")
    git("checkout", "--", "answer.json", cwd=root)
    rapply.settle("3", p)
    assert one(p, fid).state == "regressed"
    assert fixes_hold(p, e) == ("off", 1.0)
    assert p.events.query(n=1, type="loop.off", item="fixes-hold")


def test_fixes_hold_recovers_after_the_window(made):
    p, e, fid, root, base, commit = regressed(made)
    now = time.time()
    assert fixes_hold(p, e, now) == ("off", 1.0)
    assert fixes_hold(p, e, now + 13 * DAY) == ("off", 1.0), "still inside the 14 days"
    assert fixes_hold(p, e, now + 15 * DAY) == ("holding", 0.0), "a window passed with no new regression"
    assert p.events.query(n=1, type="loop.holding", item="fixes-hold")


def test_a_denied_revert_does_not_hold_it_off_for_good(made):
    p, e, fid, root, base, commit = regressed(made)
    gate.deny(p, reverts(p, fid)[0]["id"])
    rapply.settle("3", p)
    assert one(p, fid).state == "regressed" and reverts(p, fid)[0]["state"] == "denied"
    spec, at = p.model.spec, time.time() + 15 * DAY
    stock = next(iter(spec.stocks["regressed-fixes"].sensors.values()))
    assert its.measure(p.events, spec, stock, now=at) == (1.0, ""), "the stock keeps it: a goal there never recovers"
    assert fixes_hold(p, e, time.time()) == ("off", 1.0)
    assert fixes_hold(p, e, at) == ("holding", 0.0)
