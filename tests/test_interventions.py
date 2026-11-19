"""Interventions as a stock under control (SPEC §12p): every approval, request, advised command, alarm and notification
read with its class and cause; the `interventions` template's loop drawn in all three views; recurring classes made
modelling requests with their remedies; suppression recorded and never counted as a reduction; graduation with its
evidence; resolution only after the verification window with the process running; a trend tolerant of a planned
rise; and the alarm-management measures."""

from __future__ import annotations

import time

import pytest

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
    in: flow.arrivals
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
    p.events.add(deliver.SENT, source="ergostat", data={"channel": "log", "entries": ["person/reviewer@1"], "state": "ran"})
    got = {x["class"]: x for x in iv.read(p, p.model.spec, now - DAY, time.time())}
    assert set(got) == {"outward", "person:reviewer", "advise:pusher", "steptest", "change:parameter", "alarm:hot"}
    assert got["outward"]["cause"] == "block pusher" and got["person:reviewer"]["cause"] == "block reviewer"
    assert got["alarm:hot"]["cause"] == "flow.arrivals" and got["alarm:hot"]["answered"] == now - 3600 + 300
    assert got["steptest"]["cause"] == "goal queue-short"                       # a notification is not one of its own
    assert got["outward"]["answered"] is None


def test_the_interventions_loop_is_drawn_in_all_three_views(tmp_path):
    from ergostat.web.server import Live, api
    p, _ = project(tmp_path, LOOP)
    spec = p.model.spec
    assert {"interventions-waiting", "open-requests", "suppressed-requests", "resolved-requests"} == set(
        x for x in spec.stocks if x != "queue")
    assert {"interventions-per-day", "intervention-trend"} <= set(spec.auxiliaries) and spec.goals["interventions-falling"].hold.op == "<="
    assert spec.blocks["remedies"].type == "program"
    assert MODEL_REQUEST in spec.items and "interventions" in spec.systems
    assert not [x for x in p.model.problems if x.code == "missing-feedback" and "interventions" in str(x.about)]
    live = Live(p)
    for view, want in (("dynamics", ("interventions-waiting", "open-requests")), ("blocks", ("remedies",))):
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
    assert reqs["alarm:hot"]["state"] == "open" and reqs["alarm:hot"]["cause"] == "flow.arrivals"
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
    p = reload(tmp_path, LOOP.replace("    above: 50\n", "    above: 500\n").replace("gate: approve", "gate: auto"))
    got = iv.requests(p, p.model.spec)
    assert sorted(got["said"]) == ["alarm:hot: suppressed", "outward: suppressed"]   # auto with no evidence
    r = iv.requests_now(p)["alarm:hot"]
    assert r["state"] == "suppressed" and r["before"]["above"] == 50 and r["after"]["above"] == 500 and r["rate"] > 0
    assert measures.measure(p, "ergostat.interventions.per-day") >= before > 0   # never counted as a reduction
    p = reload(tmp_path, LOOP.replace("gate: approve", "gate: auto"))             # the alarm back as it was
    iv.requests(p, p.model.spec)
    assert iv.requests_now(p)["alarm:hot"]["state"] == "open"


def test_tightening_or_editing_a_guard_is_neither(tmp_path):
    p, snap = project(tmp_path, LOOP.replace("gate: approve", "gate: auto"))
    iv.requests(p, p.model.spec)
    tight = LOOP.replace("    ask: review the queue", "    ask: review the queue twice").replace("above: 50", "above: 40")
    for text in (tight, tight.replace("gate: approve", "gate: deny")):           # auto → approve → deny, an edit
        p = reload(tmp_path, text)
        assert iv.requests(p, p.model.spec)["said"] == []
    p = reload(tmp_path, tight.replace("gate: approve", "gate: deny").replace("  push:\n    run: \"echo pushed >> "
                                                                              "pushed.txt\"\n    gate: deny\n", "  push:\n"
                                                                              "    run: \"echo pushed >> pushed.txt\"\n"
                                                                              "    gate: auto\n"))
    assert iv.requests(p, p.model.spec)["said"] == []                             # deny to auto: never asked anyone


def test_a_graduation_with_evidence_is_not_suppression(tmp_path):
    p, snap = project(tmp_path, LOOP.replace("in: flow.arrivals", "in: stock.queue"))
    spec = p.model.spec
    for _ in range(5):
        a = gate.request(p, spec, "push", {}, {"block": "pusher"})
        answer.answer(p, spec, f"action/{record.short(a['id'])}", "approve")
    iv.requests(p, spec)
    p = reload(tmp_path, LOOP.replace("in: flow.arrivals", "in: stock.queue").replace("gate: approve", "gate: auto")
               .replace("above: 50", "above: 60"))                                # a goal holds what the alarm watches
    got = iv.requests(p, p.model.spec)
    assert sorted(got["said"]) == ["alarm:hot: graduated", "outward: graduated"]
    assert iv.requests_now(p)["outward"]["state"] == "verifying" and iv.requests_now(p)["outward"]["evidence"]["approved"] == 5


def test_a_request_is_resolved_only_after_the_verification_window_with_the_process_running(tmp_path):
    p, snap = project(tmp_path, LOOP)
    spec, t0 = p.model.spec, time.time() - 20 * DAY
    for i in range(3):                                                            # one every two days
        p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 1}, at=t0 + i * 2 * DAY)
        p.events.add("block.approved", item="pusher", source="owner", data={}, at=t0 + i * 2 * DAY + 30)
    assert iv.requests(p, spec, t0 + 4.1 * DAY)["made"] == 1
    p.events.add("agent.ran", item="pusher", source="pusher", data={}, at=t0 + 4.2 * DAY)
    assert iv.requests(p, spec, t0 + 8 * DAY)["resolved"] == 0                    # 4 days: under three intervals (6)
    assert iv.requests(p, spec, t0 + 10.5 * DAY)["resolved"] == 0                 # quiet long enough, but not run since
    p.events.add("agent.ran", item="pusher", source="pusher", data={}, at=t0 + 10.6 * DAY)
    assert iv.requests(p, spec, t0 + 10.7 * DAY)["resolved"] == 1
    assert iv.requests_now(p)["advise:pusher"]["state"] == "resolved"
    p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 1}, at=t0 + 11 * DAY)
    iv.requests(p, spec, t0 + 11.1 * DAY)
    assert iv.requests_now(p)["advise:pusher"]["state"] == "open"                 # it came back: reopened


def test_the_trend_is_off_only_on_a_significant_rise():
    import random
    rng = random.Random(7)

    def poisson(lam):
        n, t = 0, rng.expovariate(1.0)
        while t < lam:
            n, t = n + 1, t + rng.expovariate(1.0)
        return n
    off = 0
    for _ in range(400):                                                          # flat, 5 a day, three weeks
        b, se = iv.slope([poisson(5) for _ in range(21)])
        off += b - 2 * se > 0
    assert off / 400 < 0.05
    b, se = iv.slope([5 + d // 2 for d in range(21)])
    assert b - 2 * se > 0                                                         # a steady rise is seen


def test_a_class_being_worked_on_counts_at_its_rate_before_for_a_while(tmp_path):
    p, snap = project(tmp_path, LOOP)
    spec, now = p.model.spec, time.time()
    for d in range(1, 15):                                                        # one a day, two weeks
        p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 1}, at=now - d * DAY)
        p.events.add("block.approved", item="pusher", source="owner", data={}, at=now - d * DAY + 30)
    iv.requests(p, spec, now - 0.5 * DAY)
    assert cli(["-C", str(tmp_path), "inbox", "--invest", "advise:pusher"]) == 0
    for k in range(6):                                                            # the fix's own approvals: six today
        p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 1}, at=now + 60 + k * 120)
        p.events.add("block.approved", item="pusher", source="owner", data={}, at=now + 90 + k * 120)
    later = now + 2 * 3600
    assert iv.daily(p, spec, later, 3)[-1] == pytest.approx(1.0)                  # counted at its rate before
    for k in range(6):                                                            # after invest-for (14d): as they are
        p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 1}, at=now + 15 * DAY + k * 120)
        p.events.add("block.approved", item="pusher", source="owner", data={}, at=now + 15 * DAY + 30 + k * 120)
    assert iv.daily(p, spec, now + 15 * DAY + 3600, 3)[-1] == 6.0
    assert iv.measures(p, spec, later)["trend"] == 0.0


def test_alarm_management_measures_and_the_stats(tmp_path, capsys):
    p, snap = project(tmp_path, LOOP)
    spec, now = p.model.spec, time.time()
    for i in range(3):
        raise_alarm(p, now - 3000 + i * 20, minutes=0.1)                          # chattering: 3 in a minute
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
    from ergostat import state as st
    lp = st.snapshot(p)["loops"]["interventions-falling"]
    assert lp["interventions"]["chattering"] == 1                                 # on the goal's panel
