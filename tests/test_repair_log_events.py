"""A good run's error-level log lines are noted as swallowed failures, never opened (SPEC §12r, *Swallowed errors*;
dev/records/repair-log-events.md)."""

import hashlib
import json

import pytest

from ergostat import model as mdl
from ergostat.repair import FAILURE, capture, traces
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

MODEL = """\
name: log-events-demo
projections:
  issue: {match: {key: issue/*}, states: [open, closed], events: {issue.seen: {state: set('open')}}, otherwise: rest}
stocks:
  open-issues: {unit: issues, cumulative: true, sensor: {projection: issue, state: open, every: 1h}}
blocks:
  collector:
    type: program
    run: python3 collect.py
    every: 1h
uses:
  repair:
    use: repair
    with: {count-every: 1h, approver: person}
"""
LOGS = """\
import logging, sys
logging.basicConfig()
logging.getLogger("fetch").info("starting")
logging.getLogger("fetch").error("the feed gave no rows")
sys.exit(0)
"""
R = "0123456789abcdef0123"


@pytest.fixture
def proj(tmp_path):
    from ergostat import runner
    runner.STOPPING.clear()
    d = tmp_path / "proj"
    d.mkdir()
    (d / "ergostat.yaml").write_text(MODEL)
    (d / "collect.py").write_text(LOGS)
    m = mdl.load(d)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems]
    yield Project(m)
    runner.STOPPING.clear()


def spec(p):
    return p.model.spec


def block(p):
    return spec(p).blocks["collector"]


def one(p, fid):
    return its.one(p.events, spec(p), fid)


def begun(p):
    return p.events.add("agent.started", item="collector", source="ergostat")


def swallow(p, tail):
    row = capture.swallowed(p, spec(p), block(p), begun(p), tail, "in")
    return row and row["item"]


def fail(p, stderr):
    return capture.failed(p, spec(p), block(p), begun(p), {"exit": 1, "note": "exited 1"}, "in", stderr)["item"]


def at(level, logger):
    return f"{FAILURE}/collector-" + capture.signature("collector", "collect.py", None, log={"level": level, "logger": logger})


def kinds(p, fid):
    return [e["type"] for e in p.events.query(n=None, item=fid)]


def test_python_and_json_error_lines_noted(proj):
    e = Engine(proj, say=lambda s: None)          # a real run: logging's default form on its standard error
    try:
        e.run_block(block(proj), "test")
    finally:
        e.close()
    fid = at("ERROR", "fetch")
    it = one(proj, fid)
    assert it is not None and it.state == "noted", its.project(proj.events, spec(proj), FAILURE)
    assert it.fields["error"] == "the feed gave no rows" and it.fields["swallowed"] == 1 and it.fields["count"] == 0
    assert kinds(proj, fid) == ["ergostat.run.swallowed"]

    rows = [json.dumps({"level": "error", "logger": "db", "message": "first"}),
            json.dumps({"severity": "Fatal", "name": "db.pool", "msg": "x" * 500}),
            "plain output"]
    jid = swallow(proj, "\n".join(rows) + "\n")
    assert jid == at("FATAL", "db.pool"), "the last error-level line is the one used"
    j = one(proj, jid)
    assert j.state == "noted" and j.fields["error"] == "x" * 300 and j.fields["traceback"] is None
    crit = swallow(proj, "CRITICAL:root:disk: full\n")
    assert crit == at("CRITICAL", "root") and one(proj, crit).fields["error"] == "disk: full"
    assert len(its.project(proj.events, spec(proj), FAILURE)) == 3

    assert swallow(proj, "ERROR:fetch:again\n") == fid           # the same signature: counted, never opened
    fail(proj, "ERROR:fetch:again\n")                            # (a failed run is signed by how it ended)
    it = one(proj, fid)
    assert it.state == "noted" and it.fields["swallowed"] == 2 and it.fields["error"] == "the feed gave no rows"
    assert kinds(proj, fid) == ["ergostat.run.swallowed"] * 2


@pytest.mark.parametrize("tail", [
    "INFO:fetch:started\nWARNING:fetch:slow\n",
    'ERROR is not a log line\n{"level": "error", "logger": "db", "message": "cut off\n',
    '{"level": "warning", "logger": "db", "message": "slow"}\n{"levelname": "ERROR", "message": "no logger"}\n',
    '["level", "error"]\n{"level": 3, "logger": "db", "message": "not a level"}\n',
])
def test_info_and_bad_json_ignored(proj, tail):
    assert traces.log_event(tail) is None
    assert swallow(proj, tail) is None
    assert not proj.events.query(n=None, type="ergostat.run.swallowed")
    long = "ERROR:fetch:" + "y" * 8000
    assert traces.log_event(long) is None
    assert traces.log_event(long + "\nERROR:fetch:short") == {"level": "ERROR", "logger": "fetch", "message": "short"}


def test_trace_wins_over_log(proj):
    r = spec(proj).root
    trace = (f'Traceback (most recent call last):\n  File "{r}/collect.py", line 4, in look\n    d["x"]\n'
             "KeyError: 'x'\n")
    fid = swallow(proj, trace + "ERROR:fetch:after the trace\n")
    tb = traces.last(trace, r)
    assert fid == f"{FAILURE}/collector-" + capture.signature("collector", "collect.py", tb)
    assert one(proj, fid).fields["traceback"]["type"] == "KeyError"
    assert one(proj, at("ERROR", "fetch")) is None


def test_existing_leased_failure_untouched(proj):
    fid = at("ERROR", "fetch")
    tb = {"language": "python", "type": "KeyError", "message": "x", "file": "collect.py", "line": 4,
          "function": "look", "frames": []}
    b = begun(proj)
    proj.events.add("ergostat.run.failed", item=fid, source="ergostat", causedby=b["id"],
                    data={"block": "collector", "run": b["id"], "program": "collect.py", "error": "KeyError: x",
                          "traceback": tb, "stderr": "kept", "count": 1, "began": b["time"]})
    proj.events.add(f"{FAILURE}.opened", item=fid, source="ergostat")
    proj.events.add("ergostat.lease.taken", item=fid, source="ergostat", data={
        "run": R, "block": "repair-fix", "fence": 1, "ttl": 600, "max": 3, "back": "open"})
    before = one(proj, fid)
    assert before.state == "leased"
    assert swallow(proj, "ERROR:fetch:the feed gave no rows\n") == fid
    after = one(proj, fid)
    assert after.state == "leased"
    assert (after.fields["lease"]["holder"], after.fields["lease"]["fence"]) == (
        before.fields["lease"]["holder"], before.fields["lease"]["fence"])
    for f in ("error", "traceback", "stderr", "count", "began"):
        assert after.fields.get(f) == before.fields.get(f), f
    assert after.fields["swallowed"] == 1 and not after.refused
    assert set(proj.events.query(n=1, item=fid)[-1]["data"]) == {"swallowed", "last_swallowed"}


def test_failed_run_signature_unchanged(proj):
    fid = fail(proj, "ERROR:fetch:the feed gave no rows\n")
    old = hashlib.sha1(repr(("collector", "collect.py", "exited 1")).encode()).hexdigest()[:8]    # as before this
    assert fid == f"{FAILURE}/collector-{old}"
    assert fid != at("ERROR", "fetch") and one(proj, fid).state == "open"
