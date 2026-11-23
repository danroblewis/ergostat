"""What is going through the wires (item_sets.py): the items a stock counts and the items that went through a
flow in the window, from what the model says of each part; the Items API's filters for exactly those sets
(state, where, moved with its span), paged; and the side panel's list and link being the same set."""

import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.spec import item_sets
from ergostat.spec.item_sets import BadSet, ItemSet
from ergostat.store import Project

MODEL = """
name: wires
sources:
  prom: {type: prometheus, url: "http://127.0.0.1:1"}
items:
  ticket:
    id: ticket/*
    states: [new, awaiting, approved, done]
    on: {ticket.asked: awaiting, ticket.approved: approved, ticket.done: done}
    show: [title, area]
stocks:
  awaiting-approval:
    unit: tickets
    sensor: {items: ticket, state: awaiting, where: {area: flags}}
  approved:
    unit: tickets
    sensor: {items: ticket, state: [approved]}
  load:
    unit: requests
flows:
  completed:
    from: approved
    sensor: {items: ticket, entering: done, over: 1h}
  approving:
    from: awaiting-approval
    to: approved
  requests:
    to: load
    sensor: {query: {source: prom, promql: "sum(rate(http_requests_total[5m]))"}}
"""


@pytest.fixture
def p(tmp_path) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    return Project(mdl.load(tmp_path))


def seed(p: Project, now: float) -> None:
    """Six tickets: four about flags waiting for approval (one about something else), two approved an hour and
    more ago, three done in the last hour (one done two hours ago)."""
    t = now - 3 * 3600
    for i in range(1, 11):
        p.events.add("ticket.opened", item=f"ticket/{i}", data={"title": f"t{i}", "area": "flags" if i != 5 else "billing"},
                     at=t + i)
    for i in range(1, 6):
        p.events.add("ticket.asked", item=f"ticket/{i}", data={}, at=t + 100 + i)
    for i in range(6, 11):
        p.events.add("ticket.asked", item=f"ticket/{i}", data={}, at=t + 100 + i)
        p.events.add("ticket.approved", item=f"ticket/{i}", data={}, at=now - 2.5 * 3600 + i)
    p.events.add("ticket.done", item="ticket/6", data={}, at=now - 2 * 3600)
    for i in (7, 8, 9):
        p.events.add("ticket.done", item=f"ticket/{i}", data={}, at=now - 600 * (10 - i))


def test_a_stock_counted_from_items_is_its_items_now(p):
    now = time.time()
    seed(p, now)
    got = item_sets.of_part(p.model.spec, "stock", "awaiting-approval", now - 3600, now)
    assert got["set"] == {"kind": ["ticket"], "state": ["awaiting"], "where": ["area:flags"]}
    assert "awaiting" in got["says"] and "area = flags" in got["says"]
    s = item_sets.parse(got["set"])
    sel = item_sets.select(p.events, p.model.spec, s, until=now)
    assert sel["total"] == 4 and {i["id"] for i in sel["items"]} == {"ticket/1", "ticket/2", "ticket/3", "ticket/4"}


def test_a_flow_with_its_own_items_sensor_is_the_moves_it_counts_in_the_window(p):
    now = time.time()
    seed(p, now)
    got = item_sets.of_part(p.model.spec, "flow", "completed", now - 3600, now)
    s = item_sets.parse(got["set"])
    assert s.moved == ([], ["done"])
    sel = item_sets.select(p.events, p.model.spec, s, until=now)
    assert [i["id"] for i in sel["items"]] == ["ticket/9", "ticket/8", "ticket/7"]     # the latest move first
    assert sel["moves"] == 3 and all(len(i["moved_at"]) == 1 for i in sel["items"])
    assert "ticket/6" not in {i["id"] for i in sel["items"]}                           # done two hours ago


def test_a_flow_between_item_stocks_is_the_moves_from_the_ones_states_to_the_others(p):
    now = time.time()
    seed(p, now)
    got = item_sets.of_part(p.model.spec, "flow", "approving", now - 3 * 3600, now)
    s = item_sets.parse(got["set"])
    assert s.moved == (["awaiting"], ["approved"]) and s.where == {"area": ["flags"]}
    assert "awaiting-approval" in got["how"]
    sel = item_sets.select(p.events, p.model.spec, s, until=now)
    assert {i["id"] for i in sel["items"]} == {f"ticket/{i}" for i in range(6, 11)}
    narrow = item_sets.select(p.events, p.model.spec, item_sets.parse(
        item_sets.of_part(p.model.spec, "flow", "approving", now - 3600, now)["set"]), until=now)
    assert narrow["total"] == 0                                                         # none approved in the last hour


def test_a_pure_rate_says_why_it_has_no_items(p):
    got = item_sets.of_part(p.model.spec, "flow", "requests", 0, 1)
    assert "query against prom" in got["none"] and "names no items" in got["none"]
    assert "nothing counts it" in item_sets.of_part(p.model.spec, "stock", "load", 0, 1)["none"]


def test_parse_reads_the_address_and_says_it_back():
    s = item_sets.parse({"kind": ["ticket"], "state": ["awaiting,approved"], "where": ["area:flags", "area:x"]})
    assert s.states == ["awaiting", "approved"] and s.where == {"area": ["flags", "x"]}
    m = item_sets.parse({"kind": ["ticket"], "moved": ["approved>done"], "moved_since": ["2026-11-18T10:00:00Z"],
                         "moved_until": ["1794999600"]})
    assert m.moved == (["approved"], ["done"]) and m.since == 1794996000.0 and m.until == 1794999600.0
    assert item_sets.parse(m.params()).params() == m.params()                  # the address round-trips
    for bad in ({"state": ["a,b"]}, {"kind": ["t"], "where": ["nofield"]}, {"kind": ["t"], "moved": [">"]},
                {"kind": ["t"], "moved": ["a>b"], "moved_since": ["yesterday"]}):
        with pytest.raises(BadSet):
            item_sets.parse(bad)


def test_an_empty_side_of_a_move_is_any_other_state_or_none():
    s = ItemSet("t", moved=(["a"], []), since=0, until=10)
    assert s.move_matches({"time": 5, "from": "a", "to": "b"}) and not s.move_matches({"time": 5, "from": "b", "to": "a"})
    arriving = ItemSet("t", moved=([], ["a"]), since=0, until=10)
    assert arriving.move_matches({"time": 5, "from": None, "to": "a"})
    assert not arriving.move_matches({"time": 11, "from": None, "to": "a"})


def test_the_items_api_returns_just_the_set_paged(p):
    from ergostat.web.server import Live, api
    now = time.time()
    seed(p, now)
    live = Live(p)
    got = api(live, "items", {"kind": ["ticket"], "state": ["awaiting"], "where": ["area:flags"], "shown": ["1"]})
    assert got["total"] == 4 and len(got["items"]) == 4 and got["set"]["says"].startswith("ticket")
    assert {k["name"] for k in got["kinds"]} >= {"ticket"}                        # the page's kinds and counts kept
    paged = api(live, "items", {"kind": ["ticket"], "state": ["awaiting,approved"], "n": ["3"], "offset": ["3"]})
    assert paged["total"] == 6 and len(paged["items"]) == 3
    moved = api(live, "items", {"kind": ["ticket"], "moved": [">done"], "moved_since": [str(now - 3600)],
                                "moved_until": [str(now)], "alone": ["1"]})
    assert moved["total"] == 3 and moved["moves"] == 3 and moved["kinds"] == []
    plain = api(live, "items", {"kind": ["ticket"], "state": ["awaiting"]})     # one state: the listing, with its set said
    assert plain["total"] == 5 and plain["set"]["params"] == {"kind": ["ticket"], "state": ["awaiting"]}
    with pytest.raises(BadSet):
        api(live, "items", {"kind": ["ticket"], "state": ["awaiting,nowhere"]})


def test_the_side_panel_list_and_its_link_are_the_same_set(p):
    """The part's answer names the set; the panel asks for it alone and links to the Items page with the same
    address: both answers list the same items."""
    from ergostat.web.server import Live, api
    now = time.time()
    seed(p, now)
    live = Live(p)
    for kind, name, n in (("stock", "awaiting-approval", 4), ("flow", "completed", 3), ("stock", "approved", 1)):
        part = api(live, f"part/{kind}/{name}", {"since": ["1h"]})
        q = part["items"]["set"]
        panel = api(live, "items", {**q, "alone": ["1"], "n": ["10"], "shown": ["1"]})
        page = api(live, "items", {**q, "shown": ["1"], "per_kind": ["300"]})
        assert panel["total"] == page["total"] == n, name
        assert [i["id"] for i in panel["items"]] == [i["id"] for i in page["items"]][:10]
        assert panel["kinds"] == [] and all(set(i["fields"]) <= {"title", "area", "lease"} for i in panel["items"])
        assert all("title" in i["fields"] for i in panel["items"])                   # the kind's columns kept
    flow = api(live, "part/flow/requests", {"since": ["1h"]})
    assert "names no items" in flow["items"]["none"]


def test_sets_are_read_from_the_item_index_not_from_every_fold(p, monkeypatch):
    """A state's set is counted and paged by the index, a span's moves read there alone: never every item of
    the kind folded (items.project)."""
    from ergostat.spec import items as its
    now = time.time()
    seed(p, now)
    assert its._index(p.events, p.model.spec, False) is not None
    monkeypatch.setattr(its, "project", lambda *a, **k: (_ for _ in ()).throw(AssertionError("folded every item")))
    s = item_sets.parse({"kind": ["ticket"], "state": ["awaiting"]})
    got = item_sets.select(p.events, p.model.spec, s, until=now, n=2, offset=1)
    assert got["total"] == 5 and len(got["items"]) == 2
    flows = item_sets.select(p.events, p.model.spec, item_sets.parse(
        item_sets.of_part(p.model.spec, "flow", "completed", now - 3600, now)["set"]), until=now)
    assert flows["total"] == 3
    where = item_sets.select(p.events, p.model.spec, item_sets.parse(
        item_sets.of_part(p.model.spec, "stock", "awaiting-approval", 0, now)["set"]), until=now)
    assert where["total"] == 4


def test_a_flow_measured_by_events_lists_its_openings_and_their_items(p):
    now = time.time()
    run = p.events.add("agent.started", item="approver", data={}, at=now - 120)
    rid = run if isinstance(run, str) else run["id"]
    p.events.add("ticket.approved", item="ticket/42", data={}, causedby=rid, at=now - 100)
    p.events.add("valve.opened", item="approver", data={"amount": 1, "flow": "approving"}, causedby=rid, at=now - 90)
    got = item_sets.events_items(p.events, {"valve": "approver"}, now - 3600, now)
    assert got["total"] == 1 and got["rows"][0]["items"] == ["ticket/42"] and got["rows"][0]["amount"] == 1


TAKES = """
name: taken
items:
  job:
    id: job/*
    states: [new, doing, done]
    on: {job.started: doing, job.done: done}
    show: [title]
stocks:
  todo: {unit: jobs, sensor: {items: job, state: new}}
  made: {unit: jobs}
flows:
  started: {from: todo, to: made}
blocks:
  developer: {type: program, run: 'true', takes: {kind: job, at: new, to: [done]}, out: flow.started}
"""


def test_an_item_taken_then_moved_on_by_its_run_is_counted_as_taken(tmp_path):
    """A valve's panel (SPEC §9.5): an item is taken while its lease has a holder, whatever state its run moved it to;
    one acked (its lease ended) is not; those in the block's ``at`` states, not taken, wait. The set opens exactly
    the taken ones on the Items page."""
    from ergostat.web.server import Live, api
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(TAKES))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for i in range(1, 5):
        p.events.add("job.opened", item=f"job/{i}", data={"title": f"j{i}"}, at=now - 600 + i)
    lease = {"block": "developer", "fence": 1, "ttl": 600, "max": 2, "back": "new", "tier": "program"}
    for i in (1, 2):
        p.events.add("ergostat.lease.taken", item=f"job/{i}", data={**lease, "run": f"run{i}"}, at=now - 300 + i)
        p.events.add("job.started", item=f"job/{i}", data={}, causedby=f"run{i}", at=now - 200 + i)   # out of leased
    p.events.add("job.done", item="job/2", data={}, causedby="run2", at=now - 100)
    p.events.add("ergostat.lease.ended", item="job/2", data={"run": "run2", "fence": 1, "how": "ack"}, at=now - 99)
    got = item_sets.leased_by(p.events, p.model.spec, "started", now)
    assert [(x["block"], x["taken"], x["waiting"], x["at"]) for x in got] == [("developer", 1, 2, ["new"])]
    live = Live(p)
    panel = api(live, "items", {**got[0]["set"], "alone": ["1"], "n": ["10"], "shown": ["1"]})
    assert [(i["id"], i["state"]) for i in panel["items"]] == [("job/1", "doing")] and panel["total"] == 1
    assert panel["items"][0]["fields"]["lease"]["holder"] == "run1"
    assert "being worked by developer" in panel["set"]["says"]
    part = api(live, "part/flow/started", {})
    assert [(x["taken"], x["waiting"]) for x in part["leases"]] == [(1, 2)]
    with pytest.raises(BadSet):
        item_sets.parse({"kind": ["job"], "taken": ["developer"], "moved": ["new>doing"]})


GAPS = """
name: gaps
items:
  gap:
    id: gap/*
    states: [open, building, merged, parked, closed, dead]
    on: {gap.opened: open, gap.started: building, gap.merged: merged, gap.parked: parked, gap.closed: closed,
         gap.died: dead}
  pool:
    id: pool/*
    states: [held]
    on: {pool.measured: held}
messages:
  done: {gap: [merged, closed]}
  paused: {gap: [parked]}
stocks:
  landed:
    unit: gaps
    sensor: {items: gap, state: merged}
  every-gap:
    unit: gaps
    sensor: {items: gap}
"""


@pytest.fixture
def gaps(tmp_path):
    """Gaps in merged, closed, parked, dead and open (two open), and a pool that lives on."""
    from ergostat.web.server import Live
    (tmp_path / "ergostat.yaml").write_text(GAPS)
    p = Project(mdl.load(tmp_path))
    t = time.time() - 600
    for i, end in enumerate(("merged", "closed", "parked", "died", None, None), 1):
        p.events.add("gap.opened", item=f"gap/g{i}", data={"title": f"gap {i}"}, at=t + i)
        if end:
            p.events.add(f"gap.{end}", item=f"gap/g{i}", at=t + 10 + i)
    p.events.add("pool.measured", item="pool/p1", at=t + 1)
    return Live(p)


def listed(got: dict, kind: str = "gap") -> dict[str, str]:
    return {i["id"]: i["state"] for i in got["items"] if i["kind"] == kind}


@pytest.mark.parametrize("q", [{}, {"per_kind": ["25"], "shown": ["1"]}, {"kind": ["gap"]}, {"n": ["2"]}])
def test_the_list_leaves_out_finished_and_dead_items_by_default_and_keeps_parked(gaps, q):
    """items-list-hides-finished-by-default: by default open and parked, paged after leaving the rest out; each kind
    says what it left out, and the counts stay whole. A lives-on kind hides nothing."""
    from ergostat.web.server import api
    got = api(gaps, "items", q)
    want = {"gap/g3": "parked", "gap/g5": "open", "gap/g6": "open"}
    assert listed(got) == (want if "n" not in q else {"gap/g3": "parked", "gap/g6": "open"})   # the newest two left
    gap = next(k for k in got["kinds"] if k["name"] == "gap")
    assert gap["hidden"] == {"merged": 1, "closed": 1, "dead": 1}
    assert gap["counts"] == {"open": 2, "merged": 1, "closed": 1, "parked": 1, "dead": 1}
    assert "kind" in q or "n" in q or listed(got, "pool") == {"pool/p1": "held"}
    shown = api(gaps, "items", {**q, "finished": ["show"]})
    assert len(listed(shown)) == min(6, int(q.get("n", ["6"])[0]))
    if not q:
        assert len(listed(shown)) == 6 and shown["total"] == 7 and got["total"] == 4


def test_a_chosen_state_or_a_search_is_never_hidden(gaps):
    from ergostat.web.server import api
    assert listed(api(gaps, "items", {"kind": ["gap"], "state": ["closed"]})) == {"gap/g2": "closed"}
    found = api(gaps, "items", {"q": ["gap/g1"], "per_kind": ["25"]})
    assert listed(found) == {"gap/g1": "merged"} and found["finished_matched"] == {"gap": 1}
    with pytest.raises(BadSet):
        api(gaps, "items", {"finished": ["all"]})


def test_a_stocks_link_lists_as_many_items_as_it_counts_finished_or_not(gaps):
    """Story F4: the page a stock's 'Show them on the Items page' opens lists exactly as many as the stock counts,
    a finished state's or every state's."""
    from ergostat.spec.items import in_states
    from ergostat.web.server import api
    p, spec = gaps.p, gaps.p.model.spec
    for stock, states in (("landed", ["merged"]), ("every-gap", None)):
        q = api(gaps, f"part/stock/{stock}", {"since": ["1h"]})["items"]["set"]
        page = api(gaps, "items", {**q, "shown": ["1"], "per_kind": ["300"]})
        count = in_states(p.events, spec, "gap", states)[0]
        assert len(listed(page)) == count and count == (1 if states else 6), stock
