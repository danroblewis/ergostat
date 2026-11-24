"""The ladder's lower rungs for ``apply-fix`` (SPEC §12r, ``approver: program`` and ``rule``): behind the same guard as
the AI's, answered by the owner's program (exit 0 and ``"approve": true`` only) or by a rule over the block's last 10
answered fixes, by seq; recorded through the AI's path, re-checked under the failure's lock. Neither calls an AI."""

import json
import subprocess
import time

import pytest

from ergostat import model as mdl
from ergostat.actions import gate
from ergostat.actions import record as actions
from ergostat.repair import approve
from tests.test_repair2 import BROKEN, FIXED, MODEL, PY, calls, project
from tests.test_repair_approver import approvals, opened, proposed, run_fix


def rung(approver, approve_with=None):
    return type("A", (), {"model": "haiku", "budget": 0.25, "daily": 2.0, "timeout": 40.0, "approver": approver,
                          "approve_with": approve_with})


def review(p, fid, a, program=FIXED):
    name, passed, action = proposed(p, fid, program=program)
    return approve.review(p, a, fid, name, "collect.py", BROKEN, program, ["answer.json", "collect.py"], passed,
                          action), action


def script(tmp_path, body: str, name="approver.py") -> str:
    f = tmp_path / name
    f.write_text(body)
    return f"{PY} {f}"


def history(p, n: int, bad: dict | None = None, at: dict | None = None) -> list[int]:
    """``n`` apply-fix actions of the collector's failures, answered in this order (by seq); ``bad[i]``: denied or
    regressed; ``at[i]``: the time written on that fix's events. Returns the seqs of their answers."""
    bad, at, seqs = bad or {}, at or {}, []
    for i in range(n):
        fid, t = f"ergostat.failure/collector-{i:08x}", at.get(i, 1_000_000.0 + i)
        add = lambda what, d, fid=fid, t=t: p.events.add(f"ergostat.failure.{what}", item=fid, source="ergostat",  # noqa: E731
                                                          data=d, at=t)
        add("opened", {"block": "collector", "program": "collect.py"})
        add("passed", {"fix": f"{i:040x}"})
        aid = actions.new_id("apply-fix")
        req = {"action": "apply-fix", "item": fid, "block": "collector", "key": f"collector-{i:08x}-{i:040x}"}
        p.events.add("ergostat.action.requested", item=aid, source="repair-fix", data=req, at=t)
        if bad.get(i) == "denied":
            seqs.append(p.events.add("ergostat.action.denied", item=aid, source="owner",
                                     data={"denied_by": "owner"}, at=t)["seq"])
            continue
        seqs.append(p.events.add("ergostat.action.approved", item=aid, source="owner",
                                 data={"approved_by": "owner"}, at=t)["seq"])
        p.events.add("ergostat.action.ran", item=aid, source="ergostat", data={"exit": 0}, at=t)
        add("applied", {})
        if bad.get(i) == "regressed":
            add("regressed", {})
    return seqs


# ---- check


def test_check_refuses_program_without_approve_with(tmp_path, monkeypatch):
    d = tmp_path / "x"
    d.mkdir()
    (d / "ergostat.yaml").write_text(MODEL.format(run="python3 c.py", read_only="true", extra="", approver="program",
                                                  with_=""))
    with pytest.raises(mdl.ModelError, match="with.approve-with: repair needs it"):
        mdl.load(d)
    p, e = project(tmp_path / "y", monkeypatch, approver="program", with_=", approve-with: ./ok.sh")
    e.close()
    assert "--approver program --approve-with ./ok.sh" in p.model.spec.blocks["repair-fix"].params["run"]


# ---- program


@pytest.mark.parametrize("out,code,approved", [('{"approve": true}', 1, False), ("not json", 0, False),
                                               ('{"approve": "yes"}', 0, False), ('{"approve": true}', 0, True)])
def test_program_approves_only_on_exit_0_and_true(tmp_path, monkeypatch, out, code, approved):
    p, fid = opened(tmp_path, monkeypatch)
    seen = tmp_path / "stdin.json"
    cmd = script(tmp_path, f"import sys\nopen({str(seen)!r}, 'w').write(sys.stdin.read())\n"
                           f"print({out!r})\nsys.exit({code})\n")
    ap, action = review(p, fid, rung("program", cmd))
    got = json.loads(seen.read_text())
    assert got == {"program": "collect.py", "diff": approve.shown("collect.py", BROKEN, FIXED), "test": "passed"}
    assert not [c for c in calls(tmp_path) if c["prompt"].startswith("You review")], "no AI asked"
    a = actions.get(p, action["id"])
    if approved:
        assert ap["verdict"] == "approve" and ap["by"] == f"program approver ({PY})" and "model" not in ap
        assert a["state"] == "approved" and a["approved_by"] == ap["by"]
    else:
        assert ap["verdict"] == "escalate" and a["state"] == "requested" and not approvals(p, action["id"])
        assert ap["by"].startswith("program approver")


def test_program_sees_no_secrets(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    env = tmp_path / "env.json"
    monkeypatch.setenv("ERGOSTAT_TEST_SECRET", "secret-value-1234")
    cmd = script(tmp_path, f"import json, os, sys\nsys.stdin.read()\njson.dump(dict(os.environ), open({str(env)!r}, 'w'))\n"
                           "print('{\"approve\": false}')\n")
    review(p, fid, rung("program", cmd))
    seen = json.loads(env.read_text())
    assert "ERGOSTAT_TEST_SECRET" not in seen and "ERGOSTAT_AI" not in seen, sorted(seen)
    assert set(seen) <= set(approve.KEEP) | {"PATH", "PWD", "SHLVL", "_", "OLDPWD", "LC_CTYPE"}, sorted(seen)


def _alive(pid: int) -> bool:
    r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(r.stdout.strip()) and not r.stdout.strip().startswith("Z")


def test_program_timeout_kills_group_and_holds(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    pidf = tmp_path / "child.pid"
    cmd = script(tmp_path, f"import subprocess, sys, time\nsys.stdin.read()\n"
                           f"c = subprocess.Popen(['sleep', '30'])\nopen({str(pidf)!r}, 'w').write(str(c.pid))\n"
                           "time.sleep(30)\nprint('{\"approve\": true}')\n")
    monkeypatch.setattr(approve, "SECONDS", 2.0)
    started = time.time()
    ap, action = review(p, fid, rung("program", cmd))
    assert time.time() - started < 20
    assert ap["verdict"] == "escalate" and "did not answer within 2s" in ap["reasons"][0]
    assert actions.get(p, action["id"])["state"] == "requested" and not approvals(p, action["id"])
    child = int(pidf.read_text())
    for _ in range(50):
        if not _alive(child):
            break
        time.sleep(0.1)
    assert not _alive(child), "the approver's child was killed with it"


def test_program_that_cannot_start_holds(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    ap, action = review(p, fid, rung("program", str(tmp_path / "missing-approver")))
    assert ap["verdict"] == "escalate" and actions.get(p, action["id"])["state"] == "requested"


# ---- the guard first


@pytest.mark.parametrize("which", ["program", "rule"])
def test_guard_reason_never_reaches_program_or_rule(tmp_path, monkeypatch, which):
    bad = FIXED + "import shutil\nshutil.rmtree('x')\n"
    p, fid = opened(tmp_path, monkeypatch, program=bad)
    ran = tmp_path / "ran"
    cmd = script(tmp_path, f"import sys\nsys.stdin.read()\nopen({str(ran)!r}, 'w').write('x')\nprint('{{\"approve\": true}}')\n")
    history(p, 10)
    ap, action = review(p, fid, rung(which, cmd), program=bad)
    assert ap["verdict"] == "escalate" and ap["guard"] and ap["reasons"] == ap["guard"]
    assert not ran.exists(), "the program was never run"
    assert actions.get(p, action["id"])["state"] == "requested" and not approvals(p, action["id"])
    assert "earned" not in ap


# ---- rule


def test_rule_needs_ten_clean_answers_by_seq(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    history(p, 9)
    ap, action = review(p, fid, rung("rule"))
    assert ap["verdict"] == "escalate" and "fewer than 10" in ap["reasons"][0]
    assert actions.get(p, action["id"])["state"] == "requested"


@pytest.mark.parametrize("case", ["oldest-bad-written-newest", "newest-bad-written-oldest", "regressed", "denied"])
def test_rule_needs_ten_clean_answers_by_seq_shuffled(tmp_path, monkeypatch, case):
    """11 answered fixes. By seq the last 10 decide; each history's ``at`` is set so that ordering by it decides
    the other way."""
    p, fid = opened(tmp_path, monkeypatch)
    if case == "oldest-bad-written-newest":          # by seq: the bad one is the 11th back (approve); by at: newest
        seqs = history(p, 11, bad={0: "regressed"}, at={0: 9_000_000.0})
    elif case == "newest-bad-written-oldest":        # by seq: the bad one is the newest (held); by at: the oldest
        seqs = history(p, 11, bad={10: "denied"}, at={10: 1.0})
    else:                                            # 10, one of them bad
        seqs = history(p, 10, bad={4: case})
    ap, action = review(p, fid, rung("rule"))
    a = actions.get(p, action["id"])
    if case == "oldest-bad-written-newest":
        assert ap["verdict"] == "approve" and ap["by"] == "rule approver" and ap["earned"] == seqs[1:], ap
        assert a["state"] == "approved" and a["approved_by"] == "rule approver"
        assert gate.sweep(p, p.model.spec) == 1
    else:
        assert ap["verdict"] == "escalate" and a["state"] == "requested" and not approvals(p, action["id"]), ap
        assert "earned" not in ap


def test_rule_ten_clean_approves(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    seqs = history(p, 10, at={i: 2_000_000.0 - i for i in range(10)})
    ap, action = review(p, fid, rung("rule"))
    assert ap["verdict"] == "approve" and ap["earned"] == seqs and "model" not in ap
    assert actions.get(p, action["id"])["approved_by"] == "rule approver"
    assert not calls(tmp_path)[1:], "only the fixer of opened() ran: the rule asks no AI"


@pytest.mark.parametrize("what", ["another-fix", "this-fix"])
def test_rule_denial_in_the_gap_wins(tmp_path, monkeypatch, what):
    p, fid = opened(tmp_path, monkeypatch)
    history(p, 10)
    other = actions.new_id("apply-fix")
    p.events.add("ergostat.action.requested", item=other, source="repair-fix",
                 data={"action": "apply-fix", "item": "ergostat.failure/collector-0000ffff", "block": "collector"})
    name, passed, action = proposed(p, fid)
    real = approve.rule

    def denied_in_between(p_, a, fid_, asked):                     # the rule read and decided; then a person denies
        got = real(p_, a, fid_, asked)
        assert got[0] == "approve"
        gate.deny(p, other if what == "another-fix" else action["id"], by="owner", note="not this one")
        return got
    monkeypatch.setitem(approve.RUNGS, "rule", denied_in_between)
    ap = approve.review(p, rung("rule"), fid, name, "collect.py", BROKEN, FIXED, ["collect.py"], passed, action)
    assert ap["verdict"] == "stale" and "earned" not in ap
    a = actions.get(p, action["id"])
    assert a["state"] == ("requested" if what == "another-fix" else "denied") and not approvals(p, action["id"])
    assert gate.sweep(p, p.model.spec) == 0


def test_rule_unreadable_record_holds(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    history(p, 10)
    name, passed, action = proposed(p, fid)
    real = p.events.query

    def broken_record(*a, **k):
        if k.get("type") == "ergostat.action.*":
            raise OSError("the record cannot be read")
        return real(*a, **k)
    monkeypatch.setattr(p.events, "query", broken_record)
    ap = approve.review(p, rung("rule"), fid, name, "collect.py", BROKEN, FIXED, ["collect.py"], passed, action)
    monkeypatch.setattr(p.events, "query", real)
    assert ap["verdict"] == "escalate" and "cannot be read" in ap["reasons"][0]
    assert actions.get(p, action["id"])["state"] == "requested" and not approvals(p, action["id"])


@pytest.mark.parametrize("which", ["program", "rule"])
def test_rung_answers_counted_apart(tmp_path, monkeypatch, which):
    """An approval by a rung is an agent's, never a person's: never evidence for promoting apply-fix to gate: auto."""
    from ergostat.inbox import stats
    p, fid = opened(tmp_path, monkeypatch)
    history(p, 10)
    cmd = script(tmp_path, "import sys\nsys.stdin.read()\nprint('{\"approve\": true}')\n")
    before = stats.by_class(p, p.model.spec).get("apply-fix") or {"by_agent": 0, "approved": 0}
    assert review(p, fid, rung(which, cmd))[0]["verdict"] == "approve"
    r = stats.by_class(p, p.model.spec)["apply-fix"]
    assert (r["by_agent"] - before["by_agent"], r["approved"] - before["approved"]) == (1, 0), (before, r)
    assert "apply-fix" not in stats.asked_today(p, p.model.spec)


# ---- through fix.run


def test_fix_run_with_approver_program(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    cmd = script(tmp_path, "import sys\nsys.stdin.read()\nprint('{\"approve\": true}')\n")
    monkeypatch.setattr(approve, "named", lambda a: f"program approver ({a.approve_with})")    # (what main was given)
    monkeypatch.setitem(approve.RUNGS, "program", lambda p_, a, f, asked: ("approve", [a.approve_with], {}))
    from ergostat.repair import fix
    real = fix.main
    monkeypatch.setattr(fix, "main", lambda argv: real([*argv, "--approve-with", cmd]))
    it = run_fix(p, monkeypatch, fid, approver="program")
    ap = it.fields["approval"]
    assert ap["verdict"] == "approve" and ap["reasons"] == [cmd] and ap["by"] == f"program approver ({cmd})"
    assert actions.about(p, fid)[0]["approved_by"] == ap["by"]
