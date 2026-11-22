"""T1: a run's reserve as its cap, its sessions' ledger, and the trip (SPEC §9.9): dev/records/run-budget-trip.md."""

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.costs import budget
from ergostat.spec import engine as eng_mod
from ergostat.spec.engine import Engine
from ergostat.store import Project

MODEL = """
name: t
{budget}
agents:
  bot: {{kind: program}}
blocks:
  thinker:
    type: ai
    prompt: "Think."
  scripted:
    type: ai
    prompt: "Think."
    run: "true"
  envy:
    type: program
    run: 'echo "x${{ERGOSTAT_MAX_COST}}x" > envy.txt'
  spender:
    type: program
    run: {spend}
  free:
    type: program
    agent: bot
    run: {spend}
  ledgered:
    type: program
    run: 'mkdir -p "$ERGOSTAT_STATE_DIR/budget" && touch "$ERGOSTAT_STATE_DIR/budget/$ERGOSTAT_RUN.jsonl" && echo "$ERGOSTAT_RUN" > run.txt'
"""
BUDGET = "budget: {daily: 5, max-cost: 1}"
SPEND = "'sleep 60 & echo $! > child.pid; cat line.json; wait'"


def project(tmp_path, bud: str = BUDGET) -> Project:
    (tmp_path / "ergostat.yaml").write_text(MODEL.format(budget=bud, spend=SPEND))
    return Project(mdl.load(tmp_path))


def line(cost, tokens: int = 0) -> str:
    return json.dumps({"event": "session.ran", "item": "session/x",
                       "data": {"ai": {"cost_usd": cost, "tokens": {"input": tokens}, "turns": 1}}}) + "\n"


def wait_for(cond, seconds=20.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if got := cond():
            return got
        time.sleep(0.05)
    return cond()


def gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    try:                                            # (a zombie no one has reaped yet: ended)
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        return False


# ---- 1. the run's cap given to it


def test_ai_block_given_max_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_MAX_COST", "7")                     # inherited: never passed on
    p = project(tmp_path)
    e, spec = Engine(p, say=lambda s: None), p.model.spec
    monkeypatch.setattr(eng_mod, "AI_COMMAND", "claude -p --max-budget-usd 99")
    cmd, _ = e.program(spec.blocks["thinker"], {}, spec)
    assert "--max-budget-usd 1.0" in cmd and "99" not in cmd, cmd      # the engine's value wins
    cmd, _ = e.program(spec.blocks["scripted"], {}, spec)
    assert "--max-budget-usd" not in cmd
    e.run_block(spec.blocks["envy"], "test")
    assert (tmp_path / "envy.txt").read_text().strip() == "x1.0x"

    p = project(tmp_path, "")                                         # no budget: neither, and none inherited
    e, spec = Engine(p, say=lambda s: None), p.model.spec
    monkeypatch.setattr(eng_mod, "AI_COMMAND", "claude -p")
    assert "--max-budget-usd" not in e.program(spec.blocks["thinker"], {}, spec)[0]
    e.run_block(spec.blocks["envy"], "test")
    assert (tmp_path / "envy.txt").read_text().strip() == "xx"


# ---- 2. sessions take from the run's ledger


FAKE = f"""#!{sys.executable}
import json, os, sys
with open(os.environ["FAKE_MARK"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
sys.stdin.read()
print(json.dumps({{"type": "result", "result": "done", "num_turns": 1,
                  "total_cost_usd": float(os.environ.get("FAKE_COST", "0.3"))}}))
"""


@pytest.fixture
def sess(tmp_path):
    state = project(tmp_path).dir
    fake = tmp_path / "fake_claude"
    fake.write_text(FAKE)
    fake.chmod(0o755)
    mark = tmp_path / "mark.jsonl"

    def run(run_id, max_cost="1", **more):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")}
        env.update({"ERGOSTAT_CLAUDE": str(fake), "FAKE_MARK": str(mark), "ERGOSTAT_STATE_DIR": str(state), **more})
        if run_id is not None:
            env["ERGOSTAT_RUN"] = run_id
        if max_cost is not None:
            env["ERGOSTAT_MAX_COST"] = max_cost
        r = subprocess.run([sys.executable, "-m", "ergostat", "session", "dev", "--no-live"], input="go", cwd=tmp_path,
                           env=env, capture_output=True, text=True, timeout=60)
        lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith('{"event"')]
        assert lines, (r.stdout, r.stderr[-3000:])
        return r.returncode, lines

    def calls():
        return [json.loads(x) for x in mark.read_text().splitlines()] if mark.exists() else []
    run.calls, run.state, run.mark = calls, state, mark
    return run


def given(args: list[str]) -> float:
    return float(args[args.index("--max-budget-usd") + 1])


def refused(rc, lines) -> bool:
    return rc == 1 and lines[0]["event"] == "session.failed" and lines[0]["data"]["note"].startswith("budget: ")


def test_session_capped_at_run_left(sess):
    run = uuid.uuid4().hex
    rc, lines = sess(run)
    assert rc == 0 and lines[0]["event"] == "session.ran", lines
    rc, _ = sess(run)
    assert rc == 0
    first, second = sess.calls()
    assert given(first) == pytest.approx(1.0) and given(second) == pytest.approx(0.7)


def test_session_unknown_cost_counts_reserve(sess):
    run = uuid.uuid4().hex
    (sess.state / "budget").mkdir(parents=True)
    (sess.state / "budget" / f"{run}.jsonl").write_text(json.dumps({"id": "a", "reserve": 0.4}) + "\n"
                                                        + json.dumps({"id": "a", "cost": None}) + "\n")
    assert budget.take(sess.state, run, 1.0)[1] == pytest.approx(0.6)     # (unknown: its whole reserve)
    budget.settle(sess.state, run, json.loads((sess.state / "budget" / f"{run}.jsonl").read_text().splitlines()[-1])["id"],
                  float("nan"))                                           # (a NaN cost: unknown too)
    assert refused(*sess(run)) and sess.calls() == []


def test_session_refused_when_nothing_left(sess):
    rc, lines = sess(uuid.uuid4().hex, max_cost="0")
    assert refused(rc, lines) and "nothing is left" in lines[0]["data"]["note"]
    assert not sess.mark.exists()


def test_session_refuses_unreadable_ledger(sess):
    run = uuid.uuid4().hex
    (sess.state / "budget").mkdir(parents=True)
    (sess.state / "budget" / f"{run}.jsonl").write_text("{not json\n")
    assert refused(*sess(run))
    for bad in ("lots", "", "nan", "inf", "-inf", "-1"):
        assert refused(*sess(uuid.uuid4().hex, max_cost=bad)), bad
    assert refused(*sess(None, max_cost="1"))                              # a cap with no run
    assert refused(*sess(uuid.uuid4().hex, max_cost=None))                 # a run with no cap, in a model with budget:
    assert not sess.mark.exists()


def test_session_ledger_lock_spans_append(tmp_path, monkeypatch):
    run, got, read = uuid.uuid4().hex, [], threading.Event()
    real = budget._ledger_between

    def second():
        try:
            got.append(budget.take(tmp_path, run, 1.0)[1])
        except budget.Refused:
            got.append(0.0)

    def between():
        if threading.current_thread() is threading.main_thread() and not read.is_set():
            read.set()
            t = threading.Thread(target=second)
            t.start()
            t.join(1.0)                                   # (its read, if nothing holds it off: within the second)
            between.t = t
        real()
    monkeypatch.setattr(budget, "_ledger_between", between)
    got.append(budget.take(tmp_path, run, 1.0)[1])
    between.t.join(10)
    assert sorted(x > 0 for x in got) == [False, True], got


def test_ledger_path_validated(sess, tmp_path):
    for bad in ("../x", "ABC", "0" * 31, "g" * 32):
        assert refused(*sess(bad)), bad
    assert not sess.mark.exists()
    assert not (sess.state / "x.jsonl").exists() and not (sess.state / "budget").exists()
    p = project(tmp_path)
    neighbour = p.dir / "budget" / f"{uuid.uuid4().hex}.jsonl"
    neighbour.parent.mkdir(parents=True, exist_ok=True)
    neighbour.write_text("")
    Engine(p, say=lambda s: None).run_block(p.model.spec.blocks["ledgered"], "test")
    run = (tmp_path / "run.txt").read_text().strip()
    assert not (p.dir / "budget" / f"{run}.jsonl").exists() and neighbour.exists()
    budget.settle(p.dir, run, "late", 0.1)                       # (a session settling after the end: not made again)
    assert not (p.dir / "budget" / f"{run}.jsonl").exists()


# ---- 3. T1, the trip


def stopped(tmp_path, block: str, cost, tokens: int = 0):
    (tmp_path / "line.json").write_text(line(cost, tokens))
    p = project(tmp_path)
    e = Engine(p, say=lambda s: None)
    t = threading.Thread(target=e.run_block, args=(p.model.spec.blocks[block], "test"), daemon=True)
    t.start()
    end = wait_for(lambda: p.events.query(n=None, type="agent.failed,agent.ran"))
    t.join(10)
    assert end, "the run did not end within the bound"
    pid = int((tmp_path / "child.pid").read_text())
    assert wait_for(lambda: gone(pid), 10), "its child still runs"
    return p, end[-1]


def test_run_stopped_at_cap(tmp_path):
    _, end = stopped(tmp_path, "spender", 1.5)
    assert end["type"] == "agent.failed" and end["data"]["note"] == budget.T1, end["data"]


def test_charged_run_stopped_on_unknown_cost(tmp_path):
    _, end = stopped(tmp_path, "spender", None, tokens=10)
    assert end["type"] == "agent.failed" and end["data"]["note"] == budget.T1, end["data"]


def test_free_run_stopped_on_ai_use(tmp_path):
    _, end = stopped(tmp_path, "free", None, tokens=10)
    assert end["type"] == "agent.failed" and end["data"]["note"] == budget.T1, end["data"]


def test_trip_cost_charged(tmp_path):
    p, end = stopped(tmp_path, "spender", 1.5)
    assert end["data"]["ai"]["cost_usd"] == pytest.approx(1.5)
    assert budget.left(p, p.model.spec) == pytest.approx(5 - 1.5)
