"""Failures that cluster on a field hold only that group (SPEC §9.5, *Faults*): ``takes: {faults: {hold-by: [vpn]}}``.
All failures on ``vpn: prod`` hold that group while ``vpn: corp`` keeps running; a single failure holds nothing; a
probe after a back-off, one at a time: its success releases the group, its failure lengthens the back-off; held items
spend no attempts; a restart keeps the holds (they are events). An item with no value for the field is never held."""

from __future__ import annotations

import json
import textwrap
import time
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat.leases import ENDED, TAKEN, groups
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

RUN = ('v=${ERGOSTAT_ITEM#ticket/}; v=${v%%-*}; if [ -f "slow-$v" ]; then sleep 60; fi; '
       'if [ -f "down-$v" ]; then exit 1; fi; '
       'echo \'{"event": "ticket.done"}\'')

BODY = """
name: t
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        type: one of [ready, doing, done]
    events:
      ticket-done:
        when: type == 'ticket.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
blocks:
  worker:
    type: program
    takes: {projection: ticket, at: ready{faults}}
    pool: 3
    lease: {attempts: 9}
    run: {run}
"""

HOLD_BY = ", faults: {hold-by: [vpn]}"


def text(faults_: str = HOLD_BY) -> str:
    return BODY.replace("{faults}", faults_).replace("{run}", json.dumps(RUN))


def project(tmp_path, body: str | None = None) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(body or text()))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [x.message for x in m.problems]
    return Project(m)


def wait_for(cond, seconds=20.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.05)
    return cond()


class Looks:
    """The dispatcher's looks, counted: a wait on the next few, not on a clock."""

    def __init__(self, e):
        self.n, was = 0, e.dispatch.holds.open

        def counted(b):
            self.n += 1
            return was(b)
        e.dispatch.holds.open = counted

    def wait(self, more: int = 3) -> None:
        to = self.n + more
        assert wait_for(lambda: self.n >= to), "the dispatcher kept looking"


def start(p) -> tuple[Engine, Looks]:
    e = Engine(p, say=lambda s: None)
    looks = Looks(e)
    e.start_all()
    return e, looks


def opened(p, i: str, vpn: str | None) -> None:
    p.events.add("ticket.opened", item=i, source="t", data={} if vpn is None else {"vpn": vpn})


def item(p, i: str):
    return its.one(p.events, p.model.spec, i)


def events(p, t: str) -> list[dict]:
    return p.events.query(n=None, type=t)


def taken_after(p, seq: int, prefix: str) -> list[dict]:
    return [x for x in events(p, TAKEN) if x["seq"] > seq and x["item"].startswith(prefix)]


# ---- 1. all failures on vpn: prod hold that group; vpn: corp items keep running


def test_all_failures_on_one_value_hold_that_group_and_others_keep_running(tmp_path, monkeypatch):
    monkeypatch.setattr(groups, "BACKOFF", 600.0)                   # (no probe within the test)
    (tmp_path / "down-prod").write_text("")
    p = project(tmp_path)
    for i in range(3):
        opened(p, f"ticket/prod-{i}", "prod")
    e, looks = start(p)
    try:
        assert wait_for(lambda: events(p, groups.HELD)), "the prod group was held"
        h = events(p, groups.HELD)
        assert len(h) == 1 and h[0]["item"] == "worker"
        d = h[0]["data"]
        assert (d["block"], d["field"], d["value"]) == ("worker", "vpn", "prod")
        assert d["failed"] >= groups.FAILS and d["items"] >= groups.ITEMS and d["began"] >= d["since"]
        assert f"vpn=prod, {d['failed']} of {d['failed']} failed since " in d["why"] and "items held" in d["why"]
        for i in range(3):                                         # opened after the hold: corp flows
            opened(p, f"ticket/corp-{i}", "corp")
        assert wait_for(lambda: all(item(p, f"ticket/corp-{i}").state == "done" for i in range(3))), "corp kept running"
        looks.wait(4)
        assert not taken_after(p, h[0]["seq"], "ticket/prod"), "a held item is not taken"
        assert all(item(p, f"ticket/prod-{i}").state == "ready" for i in range(3)), "held, not dead"
        assert not events(p, groups.RELEASED)
    finally:
        e.close()


def test_an_item_with_no_value_for_the_field_is_never_held(tmp_path):
    (tmp_path / "down-none").write_text("")                         # (ticket/none-*: fails, no vpn field)
    p = project(tmp_path, text().replace("attempts: 9", "attempts: 3"))
    for i in range(3):
        opened(p, f"ticket/none-{i}", None)
    e, _ = start(p)
    try:
        assert wait_for(lambda: all(item(p, f"ticket/none-{i}").state == "dead" for i in range(3))), \
            "they fail as before, to dead letters"
        assert not events(p, groups.HELD)
    finally:
        e.close()
    assert groups.value({"vpn": ""}, "vpn") is None and groups.value({}, "vpn") is None
    assert groups.value({"vpn": None}, "vpn") is None and groups.value({"vpn": []}, "vpn") is None
    assert groups.value({"vpn": 3}, "vpn") == "3" and groups.value({"vpn": "prod"}, "vpn") == "prod"


def test_a_model_without_hold_by_holds_nothing(tmp_path):
    (tmp_path / "down-prod").write_text("")
    p = project(tmp_path, text(faults_="").replace("attempts: 9", "attempts: 2"))
    assert p.model.spec.blocks["worker"].takes.hold_by == []
    for i in range(3):
        opened(p, f"ticket/prod-{i}", "prod")
    e, _ = start(p)
    try:
        assert wait_for(lambda: all(item(p, f"ticket/prod-{i}").state == "dead" for i in range(3)))
        assert not events(p, groups.HELD)
    finally:
        e.close()


# ---- the breaker, driven directly (its clock passed in)


class Eng:
    def __init__(self, p):
        self.p, self.said = p, []

    def say(self, s):
        self.said.append(s)


def it(i: str, vpn: str | None, leased_by: str | None = None):
    f = {} if vpn is None else {"vpn": vpn}
    if leased_by:
        f["lease"] = {"holder": "r", "block": leased_by}
    return SimpleNamespace(id=i, state="ready", fields=f)


def breaker(tmp_path):
    p = project(tmp_path)
    return groups.Groups(Eng(p)), p.model.spec.blocks["worker"], p


QUEUE = [it("ticket/prod-0", "prod"), it("ticket/prod-1", "prod"), it("ticket/prod-2", "prod"),
         it("ticket/corp-0", "corp"), it("ticket/none-0", None)]


def ids(got) -> list[str]:
    return [x.id for x in got]


def fail(g, b, x, run="r0"):
    g.ended(b, x.fields, x.id, run, False)


# ---- 2. a single failure holds nothing


def test_a_single_failure_holds_nothing(tmp_path):
    g, b, p = breaker(tmp_path)
    fail(g, b, QUEUE[0])
    assert ids(g.only(b, QUEUE, QUEUE, time.time())) == ids(QUEUE)
    for _ in range(5):                                             # one item failing again and again: still nothing
        fail(g, b, QUEUE[0])
    assert ids(g.only(b, QUEUE, QUEUE, time.time())) == ids(QUEUE)
    fail(g, b, QUEUE[1])
    g.ended(b, QUEUE[1].fields, QUEUE[1].id, "r", True)            # a success between: the run starts again
    fail(g, b, QUEUE[2])
    assert ids(g.only(b, QUEUE, QUEUE, time.time())) == ids(QUEUE)
    assert not events(p, groups.HELD)


def test_failures_older_than_the_window_are_no_evidence(tmp_path, monkeypatch):
    g, b, p = breaker(tmp_path)
    for x in QUEUE[:3]:
        fail(g, b, x)
    assert ids(g.only(b, QUEUE, QUEUE, time.time() + groups.WINDOW + 1)) == ids(QUEUE)
    assert not events(p, groups.HELD) and not g.fails, "forgotten"


def test_failures_on_two_items_of_one_value_hold_it(tmp_path):
    g, b, p = breaker(tmp_path)
    now = time.time()
    fail(g, b, QUEUE[0])
    fail(g, b, QUEUE[1])
    fail(g, b, QUEUE[0])
    assert ids(g.only(b, QUEUE, QUEUE, now)) == ["ticket/corp-0", "ticket/none-0"]
    d = events(p, groups.HELD)[0]["data"]
    assert d["waiting"] == 3 and d["why"].startswith("3 items held: vpn=prod, 3 of 3 failed since ")


# ---- 3. a probe: one at a time; its success releases, its failure lengthens the back-off


def test_a_probe_after_the_back_off_one_at_a_time(tmp_path):
    g, b, p = breaker(tmp_path)
    for x in QUEUE[:3]:
        fail(g, b, x)
    now = time.time()
    assert "ticket/prod-0" not in ids(g.only(b, QUEUE, QUEUE, now))
    later = now + groups.BACKOFF + 1
    assert ids(g.only(b, QUEUE, QUEUE, later)) == ["ticket/prod-0", "ticket/corp-0", "ticket/none-0"], "one probe"
    leased = [it("ticket/prod-0", "prod", leased_by="worker"), *QUEUE[1:]]
    assert ids(g.only(b, QUEUE[1:], leased, later + 10_000)) == ["ticket/corp-0", "ticket/none-0"], \
        "none while an item of it is leased"
    g.taken(b, QUEUE[0].fields, "probe-1")
    assert "ticket/prod-1" not in ids(g.only(b, QUEUE, QUEUE, later)), "the probe taken: no second one"
    fail(g, b, QUEUE[0], "probe-1")                                # the probe fails: the back-off doubles
    pr = events(p, groups.PROBED)
    assert len(pr) == 1 and pr[0]["data"]["backoff"] == 2 * groups.BACKOFF and pr[0]["data"]["ok"] is False
    assert pr[0]["causedby"] == events(p, groups.HELD)[0]["id"]
    t = time.time()
    assert "ticket/prod-0" not in ids(g.only(b, QUEUE, QUEUE, t + groups.BACKOFF + 1)), "a longer back-off now"
    assert "ticket/prod-0" in ids(g.only(b, QUEUE, QUEUE, t + 2 * groups.BACKOFF + 1))
    g.taken(b, QUEUE[0].fields, "probe-2")
    fail(g, b, QUEUE[1], "other")                                  # a failure that was not the probe: no longer
    assert len(events(p, groups.PROBED)) == 1
    g.ended(b, QUEUE[0].fields, QUEUE[0].id, "probe-2", True)      # the probe succeeds: released
    rel = events(p, groups.RELEASED)
    assert len(rel) == 1 and rel[0]["causedby"] == events(p, groups.HELD)[0]["id"] and rel[0]["data"]["item"] == "ticket/prod-0"
    assert ids(g.only(b, QUEUE, QUEUE, time.time())) == ids(QUEUE)


def test_the_back_off_has_a_ceiling(tmp_path):
    g, b, p = breaker(tmp_path)
    for x in QUEUE[:3]:
        fail(g, b, x)
    g.only(b, QUEUE, QUEUE, time.time())
    for n in range(12):
        g.taken(b, QUEUE[0].fields, f"p{n}")
        fail(g, b, QUEUE[0], f"p{n}")
    assert events(p, groups.PROBED)[-1]["data"]["backoff"] == groups.MOST


@pytest.mark.slow
def test_a_probe_s_failure_lengthens_and_its_success_releases_in_the_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(groups, "BACKOFF", 0.5)
    (tmp_path / "down-prod").write_text("")
    p = project(tmp_path)
    for i in range(4):
        opened(p, f"ticket/prod-{i}", "prod")
    e, _ = start(p)
    try:
        assert wait_for(lambda: events(p, groups.PROBED)), "a probe ran and failed"
        assert events(p, groups.PROBED)[0]["data"]["backoff"] == 1.0
        (tmp_path / "down-prod").unlink()
        assert wait_for(lambda: events(p, groups.RELEASED)), "a probe succeeded"
        assert wait_for(lambda: all(item(p, f"ticket/prod-{i}").state == "done" for i in range(4)))
        held, rel = events(p, groups.HELD)[0]["seq"], events(p, groups.RELEASED)[0]["seq"]
        out: set[str] = set()                                      # no probe while another prod run is out
        probes = 0
        for x in p.events.query(n=None, type="ergostat.lease.*"):
            if not x["item"].startswith("ticket/prod"):
                continue
            if x["type"] == TAKEN:
                if held < x["seq"] < rel:
                    assert not out, f"{x['item']} taken while {out} still ran"
                    probes += 1
                out.add(x["item"])
            elif x["type"] in (ENDED, "ergostat.lease.expired"):
                out.discard(x["item"])
        assert probes >= 2, "a failed probe and a successful one"
    finally:
        e.close()


# ---- 4. held items spend no attempts


def test_held_items_spend_no_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(groups, "BACKOFF", 0.3)
    (tmp_path / "down-prod").write_text("")
    p = project(tmp_path)
    for i in range(3):
        opened(p, f"ticket/prod-{i}", "prod")
    e, _ = start(p)
    try:
        assert wait_for(lambda: len(events(p, groups.PROBED)) >= 2), "probes ran and failed"
        hseq = events(p, groups.HELD)[0]["seq"]
        after = [x for x in events(p, ENDED) if x["seq"] > hseq]
        assert after and all(x["data"].get("count") is False and x["data"]["fault"].startswith("held: vpn=prod")
                             for x in after), after
        before = sum(1 for x in events(p, ENDED) if x["seq"] < hseq)
        spent = sum(int(item(p, f"ticket/prod-{i}").fields["lease"].get("attempts") or 0) for i in range(3))
        assert spent == before, "only the ends before the hold were counted"
        assert all(item(p, f"ticket/prod-{i}").state != "dead" for i in range(3))
    finally:
        e.close()


def test_a_held_group_s_probe_that_goes_silent_expires_uncounted(tmp_path, monkeypatch):
    monkeypatch.setattr(groups, "BACKOFF", 0.2)
    (tmp_path / "slow-prod").write_text("")
    p = project(tmp_path, text().replace("attempts: 9", "ttl: 2s, attempts: 9"))
    opened(p, "ticket/prod-0", "prod")
    e = Engine(p, say=lambda s: None)
    g, b = e.dispatch.groups, p.model.spec.blocks["worker"]
    for x in QUEUE[:3]:                                            # (the evidence, as earlier runs would leave it)
        fail(g, b, x)
    e.start_all()
    try:
        assert wait_for(lambda: events(p, groups.HELD))
        assert wait_for(lambda: events(p, "ergostat.lease.expired"), 30), "the probe went silent and expired"
        d = events(p, "ergostat.lease.expired")[0]["data"]
        assert d.get("count") is False and d["fault"].startswith("held: vpn=prod") and d["state"] == "ready", d
        assert wait_for(lambda: events(p, groups.PROBED)), "its expiry is a failed probe"
        assert not item(p, "ticket/prod-0").fields["lease"].get("attempts")
    finally:
        e.close()


def test_a_held_group_s_failure_is_not_counted(tmp_path):
    g, b, p = breaker(tmp_path)
    for x in QUEUE[:3]:
        fail(g, b, x)
    g.only(b, QUEUE, QUEUE, time.time())
    assert g.fault(b, QUEUE[0].fields).startswith("held: vpn=prod (3 items held")
    assert g.fault(b, QUEUE[3].fields) is None and g.fault(b, QUEUE[4].fields) is None


# ---- 5. a restart keeps the holds


def test_a_restart_keeps_the_holds(tmp_path, monkeypatch):
    monkeypatch.setattr(groups, "BACKOFF", 600.0)
    (tmp_path / "down-prod").write_text("")
    p = project(tmp_path)
    for i in range(3):
        opened(p, f"ticket/prod-{i}", "prod")
    e, _ = start(p)
    try:
        assert wait_for(lambda: events(p, groups.HELD))
    finally:
        e.close()
    (tmp_path / "down-prod").unlink()                              # (up again: a take now would succeed)
    p2 = project(tmp_path)
    seq = p2.events.last_seq()
    opened(p2, "ticket/corp-0", "corp")
    e2, looks = start(p2)
    try:
        assert wait_for(lambda: item(p2, "ticket/corp-0").state == "done")
        looks.wait(4)
        assert not taken_after(p2, seq, "ticket/prod"), "still held after the restart"
        assert ("worker", "vpn", "prod") in e2.dispatch.groups.on
        assert len(events(p2, groups.HELD)) == 1 and not events(p2, groups.RELEASED)
    finally:
        e2.close()


def test_a_restart_takes_up_the_back_off_and_the_release(tmp_path):
    p = project(tmp_path)
    b = p.model.spec.blocks["worker"]
    h = p.events.add(groups.HELD, item="worker", source="ergostat", data={
        "block": "worker", "field": "vpn", "value": "prod", "why": "x", "began": 1.0, "backoff": 60, "probe_at": 61})
    p.events.add(groups.PROBED, item="worker", source="ergostat", causedby=h["id"], data={
        "field": "vpn", "value": "prod", "backoff": 120, "probe_at": 9e12})
    p.events.add(groups.HELD, item="worker", source="ergostat", data={      # (unreadable: the worst case, held)
        "block": "worker", "field": "vpn", "value": "corp", "backoff": "x", "probe_at": None})
    g = groups.Groups(Eng(p))
    assert ids(g.only(b, QUEUE, QUEUE, time.time())) == ["ticket/none-0"]
    assert g.on[("worker", "vpn", "prod")]["backoff"] == 120 and g.on[("worker", "vpn", "corp")]["backoff"] == groups.MOST
    p.events.add(groups.RELEASED, item="worker", source="ergostat", causedby=h["id"], data={"field": "vpn", "value": "prod"})
    g = groups.Groups(Eng(p))
    assert ids(g.only(b, QUEUE, QUEUE, time.time())) == [x.id for x in QUEUE if x.fields.get("vpn") != "corp"]


def test_a_hold_on_a_field_taken_out_of_the_model_is_released(tmp_path):
    g, b, p = breaker(tmp_path)
    for x in QUEUE[:3]:
        fail(g, b, x)
    g.only(b, QUEUE, QUEUE, time.time())
    b.takes.hold_by = []
    assert ids(g.only(b, QUEUE, QUEUE, time.time())) == ids(QUEUE)
    assert "not in the model now" in events(p, groups.RELEASED)[0]["data"]["why"]


# ---- the model: hold-by is checked


@pytest.mark.parametrize("faults_, ok", [
    ({"hold-by": ["vpn"]}, True), ({"hold-by": "vpn"}, True), ({"healthy": "sensor.reviewers", "hold-by": ["vpn"]}, True),
    ({"hold-by": []}, False), ({"hold-by": 3}, False), ({"hold-by": [""]}, False), ({"hold-by": list("abcdefghi")}, False),
])
def test_the_schema_reads_hold_by(faults_, ok):
    from pathlib import Path
    yaml, jsonschema = pytest.importorskip("yaml"), pytest.importorskip("jsonschema")
    root = Path(__file__).parent.parent
    v = jsonschema.Draft202012Validator(json.loads((root / "schema/ergostat.schema.json").read_text()))
    model = yaml.safe_load((root / "docs/spec-examples/relations.yaml").read_text())
    model["blocks"]["reviewer"]["takes"]["faults"] = faults_
    assert (not list(v.iter_errors(model))) == ok


@pytest.mark.parametrize("raw, ok", [
    ("{hold-by: [vpn]}", ["vpn"]),
    ("{hold-by: vpn}", ["vpn"]),
    ("{hold-by: [vpn, bastion, vpn]}", ["vpn", "bastion"]),
    ("{hold-by: []}", None),
    ("{hold-by: 3}", None),
    ("{hold-by: [vpn, 3]}", None),
    ("{hold-by: [a, b, c, d, e, f, g, h, i]}", None),
    ("{}", None),
    ("{hold-by: [vpn], nope: 1}", None),
])
def test_check_reads_hold_by(tmp_path, raw, ok):
    from ergostat import spec as sp
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text(faults_=f", faults: {raw}")))
    s, problems = sp.read(tmp_path / "ergostat.yaml", extremes=False)
    errors = [x for x in problems if x.level == "error"]
    if ok is None:
        assert errors, raw
        return
    assert not errors, [x.message for x in errors]
    assert s.blocks["worker"].takes.hold_by == ok and s.blocks["worker"].takes.healthy is None
