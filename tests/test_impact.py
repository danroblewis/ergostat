"""The impact report (numbers/impact.py, SPEC §12n): a block's runs made to fail in the record, and what the report
says broke, what the model projects without the fix and with it at each rollout time, the best time, and the fields."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.numbers import impact as im
from ergostat.store import Project

FACTORY = """\
name: f
stocks:
  queue:
    unit: jobs
    sensor: {manual: true}
flows:
  arrivals:
    to: queue
    sensor: {manual: true}
  served:
    from: queue
    sensor: {manual: true}
goals:
  queue-short:
    stock: queue
    hold: "<= 20"
actions:
  notify:
    run: echo {item}
    gate: approve
blocks:
  worker:
    type: program
    run: "true"
    in: [+stock.queue]
    every: 30s
    out: flow.served
    actions: [notify]
  watcher:
    type: program
    run: "true"
    in: [stock.queue]
    every: 1m
"""


def project_of(tmp_path, text: str = FACTORY) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


def record(p, now: float, hours: float = 4.0, failed_for: float = 1.0, step: float = 60.0, arrivals=lambda t: 10.0,
           tau: float = 0.5) -> float:
    """Arrivals into the queue, the worker draining it with a residence time of ``tau`` hours (by turns faster and slower), until it fails
    ``failed_for`` hours before ``now``: from then it moves nothing and every run fails. Returns when it began failing."""
    since = now - failed_for * 3600
    q = 5.0
    t = now - hours * 3600
    while t <= now:
        a = arrivals(t)
        out = q / tau * (1.6 if int(t // 600) % 2 else 0.4) if t < since else 0.0
        p.measurements.add("sensor/queue.main", q, at=t)
        p.measurements.add("sensor/arrivals.main", a, at=t)
        p.measurements.add("sensor/served.main", out, at=t)
        q = max(0.0, q + (a - out) * step / 3600)
        t += step
    t = now - hours * 3600
    while t <= now:
        p.events.add("agent.failed" if t >= since else "agent.ran", item="worker",
                     data={"exit": 1 if t >= since else 0, "seconds": 2.0}, at=t)
        t += 300
    return since


@pytest.fixture
def failing(tmp_path):
    p = project_of(tmp_path)
    now = time.time()
    since = record(p, now)
    return p, now, since


def test_a_synthetic_failure_names_the_broken_flows_and_the_stock_building_up(failing):
    p, now, since = failing
    r = im.report(p, "worker", since, at=now, runs=10)
    br = r["broken"]
    assert [x["ref"] for x in br["flows"]] == ["flow.served"]
    served = br["flows"][0]
    assert served["before"] > 5 and served["since"] == pytest.approx(0.0) and "stopped" in served["said"]
    assert br["share"] == 0.0
    q = next(s for s in br["stocks"] if s["ref"] == "stock.queue")
    assert q["building"] and q["now"] > q["at_failure"] + 5
    assert r["said"].startswith("worker has failed since") and "served" in r["said"]


def test_without_the_fix_the_goal_goes_off_and_with_it_now_it_recovers(failing):
    p, now, since = failing
    r = im.report(p, "worker", since, at=now, runs=20)
    g = r["goals"]["queue-short"]
    # the queue is at about 15 and grows at 10 an hour with nothing draining it: past 20 within about half an hour
    assert g["off_at"] is not None and 0.2 < (g["off_at"] - now) / 3600 < 1.0
    assert g["off_end"] and g["hours_off"] > r["horizon"] / 3600 * 0.6
    assert g["hours_off_fixed_now"] < 0.1                       # restored now, it drains before the goal goes off
    assert g["p_off_end"] > 0.8 and g["expected_off"] > 1.0 and len(g["p_off"]) == len(r["ptimes"])
    now_opt = r["rollout"]["options"][0]
    assert now_opt["at"] == now and now_opt["recovery"] is not None
    later = r["rollout"]["options"][-1]
    assert later["hours_off"] > now_opt["hours_off"] and later["peak"] > now_opt["peak"]   # waiting costs
    assert r["rollout"]["best"]["at"] == now and "now" in r["rollout"]["said"]
    ch = next(c for c in r["charts"] if c["ref"] == "stock.queue")
    assert ch["without"][-1] > ch["with"][-1] + 20


def test_the_failure_began_is_read_from_the_record(failing):
    p, now, since = failing
    got = im.failure_began(p, "worker", now)
    assert got == pytest.approx(since, abs=300)
    r = im.report(p, "block.worker", at=now, runs=0)
    assert r["broken"]["since"] == got
    with pytest.raises(im.ImpactError, match="did not fail"):
        im.report(p, "watcher", at=now, runs=0)


def test_the_ideal_rollout_time_avoids_a_planted_busy_period(tmp_path):
    p = project_of(tmp_path)
    now = time.time()
    busy = {time.localtime(now + h * 3600).tm_hour for h in (-0.5, 0, 0.5, 1)}   # the hours around now, every day
    since = record(p, now, hours=72, failed_for=0.25, step=300,
                   arrivals=lambda t: 30.0 if time.localtime(t).tm_hour in busy else 10.0, tau=0.3)
    r = im.report(p, "worker", since, at=now, within=6 * 3600, times=7, penalty=50.0, runs=0)
    ro = r["rollout"]
    assert ro["busy_from"] == ["flow.arrivals"]
    assert ro["options"][0]["busy"] == pytest.approx(1.0)
    best = ro["best"]
    assert best["busy"] < 0.5 and best["at"] > now
    assert time.localtime(best["at"]).tm_hour not in busy
    assert "avoids rolling out in a busy hour" in ro["said"]
    calm = im.report(p, "worker", since, at=now, within=6 * 3600, times=7, penalty=0.0, runs=0)
    assert calm["rollout"]["best"]["at"] == now                 # no penalty: the sooner the better


def test_the_report_is_bounded_in_time(failing):
    p, now, since = failing
    t0 = time.monotonic()
    r = im.report(p, "worker", since, at=now, times=500, runs=400, budget=1.0)
    assert time.monotonic() - t0 < 6.0
    assert len(r["rollout"]["options"]) <= im.MOST_TIMES
    assert r["stopped"] or len(r["rollout"]["options"]) == im.MOST_TIMES


def test_the_change_management_fields_say_what_it_touches_and_whether_it_writes(failing):
    p, now, since = failing
    r = im.report(p, "worker", since, at=now, runs=0, commit="abc123")
    f = r["fields"]
    assert f["touches"]["blocks"] == ["watcher"] and f["touches"]["goals"] == ["queue-short"]
    assert f["touches"]["actions"] == [{"name": "notify", "gate": "approve"}]
    assert not f["read_only"] and f["writes"] == ["notify"]
    assert f["rollback"]["how"] == "git revert abc123" and "notify" in f["rollback"]["said"]
    assert f["risk"]["level"] == "medium" and any("not run" in w for w in f["risk"]["why"])
    assert im.report(p, "worker", since, at=now, runs=0, tests="failed")["fields"]["risk"]["level"] == "high"
    assert f["confidence"]["level"] in ("low", "medium", "high") and any(x["ref"] == "worker" for x in f["confidence"]["parts"])


def test_a_failure_item_names_its_block(failing):
    p, now, since = failing
    p.events.add("ergostat.failure.opened", item="ergostat.failure/1", data={"block": "worker", "since": since, "tests": "passed"})
    r = im.report(p, "ergostat.failure/1", at=now, runs=0)
    assert r["broken"]["since"] == since and r["about"] == "block worker"
    assert not any("not run" in w for w in r["fields"]["risk"]["why"])


CHANGE = FACTORY.replace("    sensor: {manual: true}\ngoals:", "    sensor: {manual: true}\n    equation: stock.queue / drain-time\n"
                         "parameters:\n  drain-time:\n    value: 0.5h\ngoals:")


def test_a_model_change_gets_its_forecast_and_fields(tmp_path):
    from ergostat.numbers import proposals as pr
    p = project_of(tmp_path, CHANGE)
    now = time.time()
    record(p, now, failed_for=0.0)
    x = pr.propose_values(p, {"drain-time": "2h"}, {"at": now, "window": 4 * 3600})
    pid = x["id"]
    r = im.report(p, pid, at=now)
    assert r["kind"] == "change" and r["rollout"] is None and "revises its forecast" in r["notes"][0]
    assert r["fields"]["read_only"] and "revert" in r["fields"]["rollback"]["how"]


def test_the_cli_prints_the_report(failing, tmp_path):
    p, now, since = failing
    out = subprocess.run([sys.executable, "-m", "ergostat", "impact", "worker", "--since", str(since), "--runs", "5",
                          "-C", str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "worker has failed since" in out.stdout and "ROLL OUT" in out.stdout and "rollback" in out.stdout
    js = subprocess.run([sys.executable, "-m", "ergostat", "impact", "worker", "--since", str(since), "--runs", "0", "--json",
                         "-C", str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert js.returncode == 0, js.stderr
    got = json.loads(js.stdout)
    assert got["broken"]["flows"][0]["ref"] == "flow.served" and got["rollout"]["best"]
    bad = subprocess.run([sys.executable, "-m", "ergostat", "impact", "nothing", "-C", str(tmp_path)],
                         capture_output=True, text=True, timeout=60)
    assert bad.returncode == 2 and "not a block" in bad.stderr


def test_the_api_answers_once_worked_out(failing):
    from ergostat.web.server import Live, api
    p, now, since = failing
    live = Live(p)
    q = {"block": ["worker"], "began": [str(since)], "since": ["1h"]}
    got = api(live, "impact", q)
    for _ in range(300):
        if not got.get("working"):
            break
        time.sleep(0.1)
        got = api(live, "impact", q)
    assert got["broken"]["flows"][0]["ref"] == "flow.served" and got["rollout"]["best"] and got["charts"]
    assert api(live, "impact", {})["error"].startswith("say which")
    bad = {"block": ["nothing"]}
    for _ in range(100):
        x = api(live, "impact", bad)
        if not x.get("working"):
            break
        time.sleep(0.05)
    assert "not a block" in x["error"]
