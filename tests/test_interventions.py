"""Interventions as a stock under control (SPEC §12p): every approval, request, advised command, alarm and notification
read with its class and cause; the `interventions` template's loop drawn in all three views; recurring classes made
modelling requests with their remedies; suppression recorded and never counted as a reduction; graduation with its
evidence; resolution only after the verification window with the process running; a trend tolerant of a planned
rise; and the alarm-management measures."""

from __future__ import annotations

import time

from ergostat import model as mdl
from ergostat.actions import gate, record
from ergostat.cli import main as cli
from ergostat.inbox import answer, deliver
from ergostat.inbox import interventions as iv
from ergostat.numbers import measures
from ergostat.spec.ir import MODEL_REQUEST
from ergostat.store import Project

from .test_inbox import MODEL, project, seed

DAY = 86400.0
LOOP = MODEL.replace("blocks:\n", """uses:
  interventions:
    use: interventions
blocks:
  hot:
    type: alarm
    in: stock.queue
    above: 50
""", 1)


def raise_alarm(p, at: float, minutes: float = 5) -> None:
    p.measurements.add("block/hot", 1.0, at=at)
    p.measurements.add("block/hot", 0.0, at=at + minutes * 60)


def reload(tmp_path, text: str) -> Project:
    (tmp_path / "ergostat.yaml").write_text(text)
    p = Project(mdl.load(tmp_path))
    assert not [x for x in p.model.problems if x.level == "error"], [str(x) for x in p.model.problems if x.level == "error"]
    return p


def test_interventions_carry_class_and_cause_from_every_kind(tmp_path):
    p, snap = project(tmp_path, LOOP)
    now = time.time()
    seed(p, snap)
    raise_alarm(p, now - 3600)
    p.events.add(deliver.SENT, source="ergostat", data={"channel": "log", "entries": ["person/reviewer"], "state": "ran"})
    got = {x["class"]: x for x in iv.read(p, p.model.spec, now - DAY, time.time())}
    assert set(got) == {"outward", "person:reviewer", "advise:pusher", "steptest", "change:parameter", "alarm:hot",
                        "notify:log"}
    assert got["outward"]["cause"] == "block pusher" and got["person:reviewer"]["cause"] == "block reviewer"
    assert got["alarm:hot"]["cause"] == "stock.queue" and got["alarm:hot"]["answered"] == now - 3600 + 300
    assert got["steptest"]["cause"] == "goal queue-short" and got["notify:log"]["cause"] == "person/reviewer"
    assert got["outward"]["answered"] is None


def test_the_interventions_loop_is_drawn_in_all_three_views(tmp_path):
    from ergostat.web.server import Live, api
    p, _ = project(tmp_path, LOOP)
    spec = p.model.spec
    assert {"interventions-per-day", "open-requests", "resolved-requests"} <= set(spec.stocks)
    assert "intervention-trend" in spec.auxiliaries and spec.goals["interventions-falling"].hold.op == "<="
    assert spec.blocks["remedies"].type == "program"
    assert MODEL_REQUEST in spec.items and "interventions" in spec.systems
    assert not [x for x in p.model.problems if x.code == "missing-feedback" and "interventions" in str(x.about)]
    live = Live(p)
    for view, want in (("dynamics", ("interventions-per-day", "open-requests")), ("blocks", ("remedies",))):
        g = api(live, "graph", {"view": [view], "open": ["*"]})
        names = " ".join(str(n.get("name") or n.get("id")) for n in g["nodes"])
        assert all(w in names for w in want), (view, names)
    cli(["-C", str(tmp_path), "inbox", "--requests"])
    seed(p, _)
    for _i in range(3):
        raise_alarm(p, time.time() - 3600 * (_i + 1))
    assert cli(["-C", str(tmp_path), "inbox", "--requests"]) == 0
    g = api(Live(Project(mdl.load(tmp_path))), "graph", {"view": ["process"], "since": ["1d"],
                                                                   "system": ["ergostat"]})
    assert MODEL_REQUEST in {k["name"] for k in g["kinds"]}


def test_a_recurring_class_becomes_a_request_with_remedies_ranked_by_time_blocked(tmp_path, capsys):
    p, snap = project(tmp_path, LOOP)
    spec, now = p.model.spec, time.time()
    for i in range(3):
        raise_alarm(p, now - 3600 * (i + 2), minutes=30)                         # 1.5h blocked in all
        p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 1}, at=now - 3600 * (i + 2))
        p.events.add("agent.ran", item="reviewer", source="person", data={"done": 1}, at=now - 3600 * (i + 2) + 60)
    gate.request(p, spec, "push", {}, {"block": "pusher"})                        # once: it does not recur
    got = iv.requests(p, spec, now)
    assert got["made"] == 2
    reqs = iv.requests_now(p)
    assert set(reqs) == {"alarm:hot", "person:reviewer"} and reqs["alarm:hot"]["rank"] == 1          # blocked longest
    assert reqs["alarm:hot"]["state"] == "open" and reqs["alarm:hot"]["cause"] == "stock.queue"
    assert "add the missing loop: a goal and a controller on what hot watches" in reqs["alarm:hot"]["remedies"][0]
    assert reqs["person:reviewer"]["remedies"][0].startswith("automate the person's step with a block")
    assert iv.requests(p, spec, now)["made"] == 0                                 # one request a class
    assert cli(["-C", str(tmp_path), "inbox", "--requests"]) == 0 and capsys.readouterr().out.strip() == "0"


def test_removing_an_alarm_or_a_gate_is_suppression_and_does_not_lower_the_measure(tmp_path):
    p, snap = project(tmp_path, LOOP)
    now = time.time()
    for i in range(4):
        raise_alarm(p, now - DAY * i - 3600)
    iv.requests(p, p.model.spec, now)                                             # the surface as it was
    before = measures.measure(p, "ergostat.interventions.per-day")
    p = reload(tmp_path, LOOP.replace("    above: 50\n", "    above: 500\n").replace("gate: approve", "gate: deny"))
    got = iv.requests(p, p.model.spec)
    assert sorted(got["said"]) == ["alarm:hot: suppressed", "outward: suppressed"]
    r = iv.requests_now(p)["alarm:hot"]
    assert r["state"] == "suppressed" and r["before"]["above"] == 50 and r["after"]["above"] == 500 and r["rate"] > 0
    assert measures.measure(p, "ergostat.interventions.per-day") >= before > 0   # never counted as a reduction
    p = reload(tmp_path, LOOP.replace("gate: approve", "gate: deny"))             # the alarm back as it was
    iv.requests(p, p.model.spec)
    assert iv.requests_now(p)["alarm:hot"]["state"] == "open"


def test_a_graduation_with_evidence_is_not_suppression(tmp_path):
    p, snap = project(tmp_path, LOOP)
    spec = p.model.spec
    for _ in range(5):
        a = gate.request(p, spec, "push", {}, {"block": "pusher"})
        answer.answer(p, spec, f"action/{record.short(a['id'])}", "approve")
    iv.requests(p, spec)
    p = reload(tmp_path, LOOP.replace("gate: approve", "gate: auto").replace("    goal: queue-short\n    run: \"true\"",
                                                                             "    goal: queue-short\n    run: \"true\"", 1))
    got = iv.requests(p, p.model.spec)
    assert got["said"] == ["outward: graduated"] and iv.requests_now(p)["outward"]["state"] == "verifying"
    assert iv.requests_now(p)["outward"]["evidence"]["approved"] == 5


def test_a_request_is_resolved_only_after_the_verification_window_with_the_process_running(tmp_path):
    p, snap = project(tmp_path, LOOP)
    spec, t0 = p.model.spec, time.time() - 10 * DAY
    for i in range(3):
        p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 1}, at=t0 + i * 60)
        p.events.add("block.approved", item="pusher", source="owner", data={}, at=t0 + i * 60 + 30)
    assert iv.requests(p, spec, t0 + DAY)["made"] == 1
    assert iv.requests(p, spec, t0 + 9 * DAY)["resolved"] == 0                    # quiet, but pusher never ran since
    p.events.add("agent.ran", item="pusher", source="pusher", data={}, at=t0 + 8.5 * DAY)
    assert iv.requests(p, spec, t0 + 9 * DAY)["resolved"] == 1
    assert iv.requests_now(p)["advise:pusher"]["state"] == "resolved"
    p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 1}, at=t0 + 9.5 * DAY)
    iv.requests(p, spec, t0 + 9.6 * DAY)
    assert iv.requests_now(p)["advise:pusher"]["state"] == "open"                 # it came back: reopened


def test_the_trend_tolerates_a_planned_rise():
    falling = [10, 9, 9, 8, 7, 7, 6, 5, 5, 4, 3, 3, 2, 2]
    valley = falling[:6] + [12, 14, 13] + falling[9:]                             # a fix's own approvals, three days
    w = [1.0] * 6 + [iv.INVESTING_WEIGHT] * 3 + [1.0] * 5
    assert iv.slope(falling, [1.0] * 14) < 0
    assert iv.slope(valley, [1.0] * 14) > iv.slope(valley, w)
    assert iv.slope(valley, w) < 0 < iv.slope([1, 2, 3, 4], [1.0] * 4)


def test_alarm_management_measures_and_the_stats(tmp_path, capsys):
    p, snap = project(tmp_path, LOOP)
    spec, now = p.model.spec, time.time()
    for i in range(3):
        raise_alarm(p, now - 3000 + i * 120, minutes=1)                           # chattering: 3 in 10 minutes
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 1}, at=now - 2 * DAY)
    m = iv.measures(p, spec, now)
    assert m["chattering"] == 1 and m["chattering_classes"] == ["alarm:hot"] and m["standing"] == 1
    assert m["per-day"] == 3 and m["top"][0]["class"] == "person:reviewer"         # 48h blocked ranks it first
    assert 0 < m["top-share"] < 1 and m["blocked-hours"] > 24
    assert measures.measure(p, "interventions.chattering") == 1.0
    assert cli(["-C", str(tmp_path), "inbox", "--stats"]) == 0
    out = capsys.readouterr().out
    assert "interventions (ISA-18.2): 3 over the last day" in out and "person:reviewer: 1 (25%)" in out
    iv.requests(p, spec, now)
    assert cli(["-C", str(tmp_path), "inbox", "--invest", "alarm:hot"]) == 0
    assert iv.requests_now(p)["alarm:hot"]["state"] == "investing"
    _, w = iv.daily(p, spec, time.time() + 60, 3)
    assert w[-1] == iv.INVESTING_WEIGHT
    from ergostat import state as st
    lp = st.snapshot(p)["loops"]["interventions-falling"]
    assert lp["interventions"]["chattering"] == 1                                 # on the goal's panel
