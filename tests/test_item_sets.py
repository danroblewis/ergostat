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
