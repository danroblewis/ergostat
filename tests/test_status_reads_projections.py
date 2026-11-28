"""The status snapshot reads the item index's tables (dev/records/status-reads-the-projections.md), on a copy of the
factory-size fixture (``factory_state``) with ergostat's own items added at the factory's rate: gated actions held and
answered, messages, reports, model changes, modelling requests and model requests, a person block's asks, breakers.

- once the index is current, none of the status's reads (those items, the inbox's asks and the actions' work items,
  loop crossings, breakers, step tests, daemons, expired leases, each agent's and loop's newest events, the window's
  tallies and openings, the items changed since a reading) reaches the event log's segments, and the answer is made in
  under 100 ms; the old code, counted the same way, reads them all from the log;
- the answer equals, field by field, the old code's on that record (tests/status_before.py: each module's own fold of
  the record, put back in place of the tables');
- the answer says how old it is."""

from __future__ import annotations

import random
import shutil
import time

import pytest

from ergostat import model as mdl
from ergostat import segments, state
from ergostat.inbox import entries, interventions, stats
from ergostat.spec import itemindex, projections
from ergostat.spec.ir import ACTION, MESSAGE, MODEL_CHANGE, INTERVENTION_CLASS, MODELLING_REQUEST
from ergostat.store import Project
from tests import status_before

pytestmark = pytest.mark.slow

TABLED = tuple(f"{pre}." for pre, *_ in projections.FAMILIES.values()) + tuple(
    m[:-1] if m.endswith("*") else m for m in projections.MARKS) + tuple(projections.CHAINS) + projections.LATEST


def _seed(p, now: float) -> int:
    """Ergostat's own items over the last 20 hours, about as many as the factory's record holds: what the status's
    inbox, messages, reports, leases and interventions read."""
    from ergostat.numbers import version as ver
    spec, r, evs = p.model.spec, random.Random("status"), []
    t = lambda: now - r.uniform(60, 20 * 3600)                     # noqa: E731
    add = lambda ty, item, at, data=None, source="ergostat": evs.append(  # noqa: E731
        {"type": ty, "item": item, "at": at, "data": data or {}, "source": source})
    block = next(b for b in spec.blocks.values() if b.params.get("actions"))
    for i in range(400):
        a, t0 = f"{ACTION}/a{i:04d}", t()
        add(f"{ACTION}.requested", a, t0, {"action": "ship", "class": "ship", "gate": "approve", "block": block.name,
                                           "item": f"gap/{i % 430}", "command": f"ship {i}", "args": {"n": i}}, block.name)
        x = r.random()
        if x < 0.6:
            add(f"{ACTION}.approved", a, t0 + 30, {"approved_by": "owner"}, "owner")
            add(f"{ACTION}.ran" if x < 0.5 else f"{ACTION}.failed", a, t0 + 40, {"exit": 0 if x < 0.5 else 1})
        elif x < 0.75:
            add(f"{ACTION}.denied", a, t0 + 20, {"denied_by": "owner", "note": "not now"}, "owner")
    for i in range(80):
        m, t0 = f"{MESSAGE}/m{i:03d}", t()
        add(f"{MESSAGE}.received", m, t0, {"by": "owner", "text": f"message {i}"}, "owner")
        add(f"{MESSAGE}.unrouted" if i % 3 else f"{MESSAGE}.routed", m, t0 + 5, {"why": "no work matched"})
    for i in range(15):
        add("ergostat.report.drafted", f"ergostat.report/r{i:02d}", t(), {"title": f"report {i}", "origin": "crash"})
    for i in range(60):
        c, t0 = f"{MODEL_CHANGE}/c{i:03d}", t()
        add(f"{MODEL_CHANGE}.made", c, t0, {"kind": "parameter", "title": f"change {i}", "created": t0,
                                            "version": ver.version(spec)})
        add(f"{MODEL_CHANGE}.checked", c, t0 + 10)
        if i % 3 == 1:                                    # passed by the judge: the owner's to approve
            add(f"{MODEL_CHANGE}.passed", c, t0 + 60)
        if i % 3 == 0:
            add(f"{MODEL_CHANGE}.accepted" if i % 2 else f"{MODEL_CHANGE}.dismissed", c, t0 + 600, {}, "owner")
    for i in range(50):
        q, t0 = f"{MODELLING_REQUEST}/q{i:03d}", t()
        add(f"{MODELLING_REQUEST}.raised", q, t0, {"code": f"code-{i % 7}", "about": "goal.gap-prompt",
                                                  "says": f"request {i}", "source": "check"})
        add(f"{MODELLING_REQUEST}.held", q, t0 + 60, {"why": "no tier has a change for it"})
        if i % 4 == 0:
            add(f"{MODELLING_REQUEST}.dismissed", q, t0 + 900, {"note": "later"}, "owner")
    for i in range(12):
        add(f"{INTERVENTION_CLASS}.opened", f"{INTERVENTION_CLASS}/k{i:02d}", t(), {"class": f"action:c{i}", "rate": 1.0})
    for b in [b for b in spec.blocks.values() if b.type == "person"][:12]:
        for j in range(6):
            t0 = now - 3600 * (j + 1) - r.uniform(0, 1800)
            add("person.asked", b.name, t0, {"command": 1})
            if j:
                add("agent.ran", b.name, t0 + 300, {"done": 1}, "person")
    for b in [b for b in spec.blocks.values() if b.on is not None][:3]:
        add("trigger.tripped", b.name, now - 900, {"runs": 40, "most": 20})
    for i in range(0, 60, 3):                             # work items an action asks about: their impact and tests
        add("gap.noted", f"gap/{i}", t(), {"impact": f"impact {i}", **({"tests": "2 failed"} if i % 2 else {})})
    evs.sort(key=lambda e: e["at"])
    return p.events.add_many(evs)


@pytest.fixture(scope="module")
def record(factory_state, tmp_path_factory):
    """A copy of the factory-size state directory (the shared one is never written), seeded, its index current."""
    d = tmp_path_factory.mktemp("status") / "state"
    shutil.copytree(factory_state.record, d)
    p = Project(mdl.load(factory_state.model), d, note=False)
    _seed(p, time.time())
    state.snapshot(p)                                     # the index caught up (built for this layout), caches warm
    return p


def _uncached() -> None:
    for c in (entries._CACHE, stats._CACHE, interventions._CACHE, state._CYCLES, state._FINDINGS):
        c.clear()


def _reads(monkeypatch) -> list[tuple]:
    """Each query of the record's segments (``Segments._scan``) but the index's own catch-up with what is new, as
    (type, item, whether it tests every item: ``of_items``) asked."""
    got, real, follow, catching = [], segments.Segments._scan, itemindex.Index.catch_up, []

    def scan(self, **kw):
        if not catching:
            got.append((kw.get("type"), kw.get("item"), kw.get("item_test") is not None))
        return real(self, **kw)

    def catch_up(self, events):
        catching.append(1)
        try:
            return follow(self, events)
        finally:
            catching.pop()
    monkeypatch.setattr(segments.Segments, "_scan", scan)
    monkeypatch.setattr(itemindex.Index, "catch_up", catch_up)
    return got


def _tabled(type: str | None, item, items: bool) -> bool:
    """A read of what the tables hold: of their types, or of every item's events (a fold of the record)."""
    if type is None:
        return items
    return any(t.startswith(TABLED) for t in type.split(","))


def test_once_the_index_is_current_the_status_reads_none_of_the_tables_from_the_log(record, monkeypatch):
    p = record
    assert projections.stored(p, "action") and projections.stored(p, "message")        # (the seeded items are there)
    p.events.add("probe.tick", item="probe", source="test")      # a new event: the index follows it, the caches go
    reads = _reads(monkeypatch)
    snap = state.snapshot(p)
    assert snap["inbox"] and snap["messages"] and snap["agents"] and snap["loops"]
    assert reads == [], reads[:20]
    with monkeypatch.context() as m:                     # the old code, counted the same way: it reads them all
        status_before.old(m)
        p.events.add("probe.tick", item="probe", source="test")
        state.snapshot(p)
    assert {t.split(",")[0] for t, i, x in reads if _tabled(t, i, x)} >= {
        "loop.*", f"{ACTION}.*", f"{MESSAGE}.*", f"{MODEL_CHANGE}.*", f"{MODELLING_REQUEST}.*", "person.asked",
        "ergostat.lease.expired", "agent.ran", "agent.failed", "agent.started", "controller.decided", "valve.opened",
        "ergostat.claim.contradicted"}, sorted({str(t) for t, _, _ in reads})
    one = [i for t, i, _ in reads if t is None and i is not None]          # and one item's events, folded: an action's
    assert len(one) > 20, len(one)                                         # work item, an item changed since a reading


@pytest.mark.serial                                       # (a time bound: held only on a machine not under the suite)
def test_a_status_request_makes_no_segment_query_and_answers_in_100_ms(record, monkeypatch):
    p = record
    p.events.add("probe.tick", item="probe", source="test")
    reads = _reads(monkeypatch)
    t0 = time.perf_counter()
    state.snapshot(p)
    took = time.perf_counter() - t0
    assert reads == [] and took < 0.1, (len(reads), took)


def test_the_answer_equals_the_old_codes_field_by_field(record, monkeypatch):
    p = record
    now = time.time()
    _uncached()
    new = state.snapshot(p, now=now)
    _uncached()
    with monkeypatch.context() as m:
        status_before.old(m)
        was = state.snapshot(p, now=now)
    _uncached()
    assert new["inbox"] and new["messages"] and new["reports"]
    assert any("impact" in (e.get("why") or "") for e in new["inbox"] if e["kind"] == "action")   # (its work item's)
    breakers = {"breaker"} if any(b.on is not None for b in p.model.spec.blocks.values()) else set()
    assert {e["kind"] for e in new["inbox"]} >= {"action", "person", "change", "request", *breakers}, \
        {e["kind"] for e in new["inbox"]}
    for k in sorted(set(new) | set(was)):
        if k == "as_of":                                  # (made apart: its time is its own)
            continue
        assert new.get(k) == was.get(k), k
    for x in (new, was):
        x.pop("as_of")
    assert new == was


def test_the_answer_says_how_old_it_is(record):
    p = record
    seq, t0 = p.events.last_seq(), time.time()
    snap = state.snapshot(p)
    assert snap["as_of"]["seq"] == seq and t0 <= snap["as_of"]["made"] <= time.time()
    assert state.age(snap, snap["as_of"]["made"] + 4)["age"] == 4
    from ergostat.web.server import Live, api
    said = api(Live(p), "status", {})["as_of"]
    assert said["seq"] == p.events.last_seq() and 0 <= said["age"] < 60, said
