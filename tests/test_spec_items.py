"""Items: the record folded by id into a kind, a state and fields; stocks that count them and flows
measured by items moving between states; the compiler refuses what does not fit."""

import json
import textwrap
import time

from ergostat import model as mdl
from ergostat.mcp import Server
from ergostat.spec import items as its
from ergostat.spec import read
from ergostat.spec.engine import read_sensor
from ergostat.spec.ir import Ref
from ergostat.store import Project

MODEL = """
projections:
  pr:
    match:
      key: github/pull_request/*
    states: [open, review, merged, closed]
    events:
      pr.review-asked:
        state: set('review')
      pr.merged:
        state: set('merged')
      pr.closed:
        state: set('closed')
    otherwise: rest
    show: [title]
stocks:
  in-review:
    unit: prs
    sensor:
      projection: pr
      state: review
      every: 10s
  open-bugs:
    unit: prs
    sensor:
      projection: pr
      state: [open, review]
      where:
        label: bug
  stuck:
    unit: hours
    sensor:
      projection: pr
      state: review
      measure: oldest
flows:
  merging:
    from: in-review
    sensor:
      projection: pr
      entering: merged
      over: 1h
auxiliaries:
  late:
    unit: prs
    driven-by: +stock.in-review
    sensor:
      projection: pr
      state: [open, review]
      where:
        late: "yes"
"""


def project(tmp_path, text=MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


def test_an_item_is_its_events_folded(tmp_path):
    p = project(tmp_path)
    t = time.time() - 600
    p.events.add("pr.opened", item="github/pull_request/1", data={"title": "fix the thing", "label": "bug"}, at=t)
    p.events.add("pr.review-asked", item="github/pull_request/1", data={"reviewer": "a"}, at=t + 60)
    p.events.add("pr.merged", item="github/pull_request/1", data={"title": "fix the thing, really"}, at=t + 120)
    p.events.add("loop.off", item="inbox-short", data={"value": 3})          # a part, never an item
    it = its.one(p.events, p.model.spec, "github/pull_request/1")
    assert it.kind == "pr" and it.state == "merged" and it.entered == t + 120
    assert it.fields == {"title": "fix the thing, really", "label": "bug", "reviewer": "a"}
    assert [(m["from"], m["to"]) for m in it.moves] == [(None, "open"), ("open", "review"), ("review", "merged")]
    got = its.listing(p.events, p.model.spec)
    assert [i["id"] for i in got["items"]] == ["github/pull_request/1"]
    assert got["projections"][0]["counts"] == {"merged": 1}
    assert [i["item"] for i in p.events.items()] == ["github/pull_request/1"]


def test_stocks_count_items_and_flows_count_their_moves(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    now = time.time()
    for n in range(1, 6):
        p.events.add("pr.opened", item=f"github/pull_request/{n}", data={"label": "bug" if n % 2 else "feature"},
                     at=now - 7200 + n)
    for n in (1, 2, 3):
        p.events.add("pr.review-asked", item=f"github/pull_request/{n}", at=now - 3 * 3600 if n == 1 else now - 600)
    p.events.add("pr.merged", item="github/pull_request/2", at=now - 300)
    p.events.add("pr.merged", item="github/pull_request/4", at=now - 2 * 3600)     # outside the hour
    read = lambda stock_or_flow, kind="stock": read_sensor(spec, spec.sensor(Ref(kind, stock_or_flow, "main")), p.events)[0]  # noqa: E731
    assert read("in-review") == 2                                   # 1 and 3
    assert read("open-bugs") == 3                                   # 1, 3 (review) and 5 (open): odd ones are bugs
    assert 2.9 < read("stuck") < 3.1                                # 1 has waited 3 hours
    assert read("merging", "flow") == 1.0                           # one merged in the last hour
    p.events.add("pr.late", item="github/pull_request/3", data={"late": "yes"})
    p.events.add("pr.late", item="github/pull_request/2", data={"late": "yes"})      # merged: no longer counted
    assert read("late", "auxiliary") == 1                           # an auxiliary counts the items now, as a stock does


def test_the_compiler_refuses_what_does_not_fit(tmp_path):
    bad = """
    projections:
      ticket:
        match:
          key: tickets
        states: [open, done]
        events:
          ticket.closed:
            state: set('shut')
        otherwise: rest
    stocks:
      a:
        sensor:
          projection: tickit
      b:
        sensor:
          projection: ticket
          state: doing
          entering: done
    flows:
      f:
        to: a
        sensor:
          projection: ticket
          state: open
    """
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(bad))
    _, problems = read(tmp_path / "ergostat.yaml")
    codes = {x.code for x in problems if x.level == "error"}
    assert {"bad-id", "unknown-state", "unknown-ref", "items-on-stock", "items-on-flow"} <= codes, problems
    msgs = " ".join(x.message for x in problems)
    assert "did you mean ticket" in msgs and "'doing' is not a state of ticket" in msgs


def test_the_engine_reads_item_counts_and_the_api_lists_them(tmp_path):
    from ergostat.spec.engine import Engine
    from ergostat.web.server import Live, api
    p = project(tmp_path)
    p.events.add("pr.opened", item="github/pull_request/9", data={"title": "x"})
    p.events.add("pr.review-asked", item="github/pull_request/9")
    e = Engine(p, say=lambda s: None)
    e._read(p.model.spec.sensor(Ref("stock", "in-review", "main")))
    assert p.measurements.latest("sensor/in-review.main")[1] == 1
    live = Live(p)
    d = api(live, "items", {"projection": ["pr"], "state": ["review"]})
    assert d["total"] == 1 and d["items"][0]["state"] == "review" and d["projections"][0]["show"] == ["title"]
    one = api(live, "items/github%2Fpull_request%2F9", {})
    assert one["projection_of"]["name"] == "pr" and len(one["moves"]) == 2 and len(one["record"]) == 2 and one["events"] == 2


def test_an_items_kind_names_its_endings_as_the_process_map_counts_them(tmp_path):
    """The item API's projection_of.final (what the lifecycle strip sets apart): the states after the first that no item
    has left, in the kind's own order; a state an item has left is no ending."""
    from ergostat.web.server import Live, api
    p = project(tmp_path)
    for n, ev in ((9, "pr.review-asked"), (9, "pr.merged"), (8, "pr.review-asked")):
        p.events.add(ev, item=f"github/pull_request/{n}", data={"title": "x"})
    one = api(Live(p), "items/github%2Fpull_request%2F9", {})
    assert one["projection_of"]["states"] == ["open", "review", "merged", "closed"]
    assert one["projection_of"]["final"] == ["merged", "closed"], one["projection_of"]


def test_an_agent_records_events_and_reads_items_over_mcp(tmp_path):
    project(tmp_path)
    s = Server(tmp_path)
    out = s.call("record_event", {"type": "pr.opened", "item": "github/pull_request/3", "data": {"title": "t"}})
    assert "recorded" in out["content"][0]["text"]
    assert s.call("record_event", {"type": "loop.off", "item": "x"}).get("isError")
    got = json.loads(s.call("items", {"projection": "pr"})["content"][0]["text"])
    assert got["items"][0]["id"] == "github/pull_request/3" and got["items"][0]["state"] == "open"


LONG_WAY = """
stocks:
  bugs:
    unit: ops
    sensor:
      manual: true
  backlog:
    unit: tickets
    sensor:
      manual: true
  ready:
    unit: tickets
    sensor:
      manual: true
flows:
  filed:
    to: backlog
  built:
    from: backlog
    to: ready
  deployed:
    from: ready
  fixed:
    from: bugs
    driven-by: flow.deployed
goals:
  no-bugs:
    stock: bugs
    hold: "<= 0"
  backlog-empty:
    stock: backlog
    hold: "<= 0"
  shipped:
    stock: ready
    hold: "<= 0"
blocks:
  support:
    type: program
    run: echo 1
    in: stock.bugs
    out: flow.filed
  dev:
    type: program
    goal: backlog-empty
    run: echo 1
    out: flow.built
  deployer:
    type: program
    goal: shipped
    run: echo 1
    out: flow.deployed
"""


def test_a_loop_closes_the_long_way_through_queues_and_an_influence(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(LONG_WAY))
    spec, problems = read(tmp_path / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"], problems
    lp = spec.loop("no-bugs")
    assert lp.closes and not lp.actuators
    assert lp.through == ["block.support", "flow.filed", "stock.backlog", "block.dev", "flow.built", "stock.ready",
                          "block.deployer", "flow.deployed", "flow.fixed"]
    assert "missing-feedback" not in {x.code for x in problems if x.about == "goal.no-bugs"}
    m = mdl.load(tmp_path)
    assert m.loop("no-bugs").closes and m.flows["fixed"].driven_by == ["deployed"]
    from ergostat.spec.explain import explain
    assert "Closes the long way" in explain(spec, "no-bugs")


def test_the_item_answer_sends_history_only_when_asked_and_sizes_its_files(tmp_path, monkeypatch):
    """/api/items/ID: the counts always, ``history`` only with history=FIELD or all; ``file_sizes`` for a file in the
    project, none for one in the state folder or outside the project."""
    from urllib.parse import quote

    from ergostat.web.server import Live, api
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    (tmp_path / "ergostat.yaml").write_text(MODEL)
    (tmp_path / "b.md").write_text("12345")
    p = Project(mdl.load(tmp_path))
    (p.dir / "secret.md").write_text("in the state folder")
    (tmp_path.parent / "outside.md").write_text("outside")
    item = "github/pull_request/9"
    assert p.dir.resolve().is_relative_to(tmp_path.resolve()), "the state folder is reachable from the project's root"
    p.events.add("pull_request.opened", item=item, data={"title": "a", "brief": "file:b.md", "more": [
        {"s": f"file:{p.dir.resolve().relative_to(tmp_path.resolve())}/secret.md"}, {"o": "file:../outside.md"}]})
    p.events.add("pull_request.reviewed", item=item, data={"title": "b"})
    live, at = Live(p), quote(item, safe="")
    plain = api(live, f"items/{at}", {})
    assert "history" not in plain and plain["changes"]["title"] == 2
    assert plain["file_sizes"] == {"b.md": 5}
    assert list(api(live, f"items/{at}", {"history": ["title"]})["history"]) == ["title"]
    assert {"title", "brief"} <= set(api(live, f"items/{at}", {"history": ["all"]})["history"])


def test_the_same_value_again_is_no_change(tmp_path):
    """A field written again with the value it has (a program printing its whole item every run) is no change: each
    event stays on the record, but the field's history and count say only what changed. 1 then True is a change."""
    p = project(tmp_path)
    for i in range(5):
        p.events.add("pr.seen", item="github/pull_request/2", data={"title": "same", "n": 1 if i < 4 else True,
                                                                   "step": i})
    d = its.detail(p.events, p.model.spec, "github/pull_request/2")
    assert d["changes"]["title"] == 1 and d["changes"]["step"] == 5 and d["changes"]["n"] == 2
    assert d["fields"]["title"] == "same"
