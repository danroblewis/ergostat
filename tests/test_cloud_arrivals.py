"""The boundary, crossed once (spec/chains.py, SPEC §12): a kind's items brought in from clouds into several states
is found (``projection-enters-many-times``), with the exact rewiring from the record's moves or, with no record, the kind's
order; a state the record shows items arriving in directly is a note, not a fault; and a model with many inflows from
clouds for its stocks gets ``many-cloud-inflows``."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.numbers import improve as im
from ergostat.numbers import structural
from ergostat.numbers import trial as tr
from ergostat.numbers import yamledit as ye
from ergostat.spec import chains, read
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted(p for p in (ROOT / "examples").iterdir() if (p / "ergostat.yaml").exists())

TICKETS = """
name: tickets
projections:
  ticket:
    id: ticket/*
    states: [open, triaged, doing, done]
    on: {ticket.triaged: triaged, ticket.started: doing, ticket.done: done}
stocks:
  backlog: {unit: tickets, sensor: {projection: ticket, state: open, every: 10s}}
  triaged: {unit: tickets, sensor: {projection: ticket, state: triaged, every: 10s}}
  wip: {unit: tickets, sensor: {projection: ticket, state: doing, every: 10s}}
flows:
  filed: {to: backlog, sensor: {projection: ticket, entering: open, over: 1h}}
  triaging: {from: backlog, to: triaged, sensor: {projection: ticket, entering: triaged, over: 1h}}
  started:
    to: wip
    sensor: {projection: ticket, entering: doing, over: 1h}
  finished: {from: wip, sensor: {projection: ticket, entering: done, over: 1h}}
"""


def _write(d: Path, text: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))
    return d


def _found(d: Path, *codes: str) -> dict:
    _, problems = read(d / "ergostat.yaml")
    return {f"{x.code}@{x.about}": x for x in problems if x.code in codes}


def _record(d: Path, histories: list[list[str]]) -> None:
    p = Project(mdl.load(d))
    for i, events in enumerate(histories):
        for e in events:
            p.events.add(e, item=f"ticket/{i}", source="t")
    chains._CACHE.clear()


def test_two_arrivals_without_a_record_are_chained_by_the_kind_s_order(tmp_path):
    d = _write(tmp_path / "t", TICKETS)
    got = _found(d, *structural.CHAIN_CODES)
    assert list(got) == ["projection-enters-many-times@projections.ticket"]          # one finding, not one per flow
    x = got["projection-enters-many-times@projections.ticket"]
    assert x.where.file.name == "ergostat.yaml" and x.where.line > 0
    assert "filed into open; started into doing" in x.message
    assert "counts the same items twice" in x.message and "only through information links" in x.message
    assert "Keep the arrival into open" in x.message
    assert "flow started into doing: its items come from triaged (the projection's states, triaged before doing): write " \
        "from: triaged on flow started" in x.message


def test_with_a_record_the_moves_say_where_they_come_from_and_the_proposal_rewires_it(tmp_path):
    d = _write(tmp_path / "t", TICKETS)
    _record(d, [["ticket.created", "ticket.started", "ticket.done"]] * 3)    # straight from open to doing, not triaged
    x = _found(d, "projection-enters-many-times")["projection-enters-many-times@projections.ticket"]
    assert "its items come from open (3 moves from open in the record): write from: backlog on flow started" in x.message
    assert "the state the record sees them arrive in" in x.message
    assert [(f.op, f.flow, f.key, f.stock) for f in chains.analyse(read(d / "ergostat.yaml")[0])[0].fixes] == \
        [("retarget", "started", "from", "backlog")]
    p = Project(mdl.load(d))
    out, not_made = structural.find(p, p.model.spec, None)
    mine = [x for x in out if x["code"] == "projection-enters-many-times"]
    assert len(mine) == 1 and mine[0]["rewires"] and mine[0]["title"].startswith("One arrival for ticket")
    for f, text in ye.apply_together(tr.edits_of(mine[0])).items():
        Path(f).write_text(text)
    chains._CACHE.clear()
    assert _found(d, *structural.CHAIN_CODES) == {}
    assert mdl.load(d).spec.flows["started"].source == "backlog"


def test_items_arriving_already_in_the_later_state_make_it_a_note(tmp_path):
    """Reopened in the outside system: the first event puts each ticket straight into doing."""
    d = _write(tmp_path / "t", TICKETS)
    _record(d, [["ticket.created", "ticket.triaged"]] * 2 + [["ticket.started", "ticket.done"]] * 3)
    got = _found(d, *structural.CHAIN_CODES)
    x = got["projection-enters-many-times@projections.ticket"]
    assert "A note, not a fault" in x.message and "3 items whose first event puts them in doing" in x.message
    assert "write from:" not in x.message and "counts the same items twice" not in x.message
    assert chains.analyse(read(d / "ergostat.yaml")[0])[0].fixes == []
    p = Project(mdl.load(d))
    out, _ = structural.find(p, p.model.spec, None)
    assert not [x for x in out if x["code"] == "projection-enters-many-times"]   # nothing to rewire: no proposal


def test_a_move_through_a_state_with_no_stock_gets_the_stock(tmp_path):
    """A working day: briefed has no stock, so the brief drains the started stock to a cloud and the day's end
    arrives from another: the move started → briefed → ended drawn as a departure and an arrival."""
    d = _write(tmp_path / "day", """
        projections:
          day: {id: day/*, states: [started, briefed, ended, recorded]}
        stocks:
          days-to-brief: {unit: days, sensor: {projection: day, state: started}}
          days-to-record: {unit: days, sensor: {projection: day, state: ended}}
        flows:
          days-starting: {to: days-to-brief, sensor: {run: echo 1, every: 1m}}
          briefs-written:
            from: days-to-brief
            sensor: {projection: day, entering: briefed}
          days-ending:
            to: days-to-record
            sensor: {projection: day, entering: ended}
          ledgers-written: {from: days-to-record, sensor: {projection: day, entering: recorded}}
    """)
    x = _found(d, "projection-enters-many-times")["projection-enters-many-times@projections.day"]
    assert "Give briefed its stock: stock day-briefed, counting the items of day in briefed; to: day-briefed on flow " \
        "briefs-written; from: day-briefed on flow days-ending" in x.message
    p = Project(mdl.load(d))
    out, not_made = structural.find(p, p.model.spec, None)
    mine = next(x for x in out if x["code"] == "projection-enters-many-times")
    for f, text in ye.apply_together(tr.edits_of(mine)).items():
        Path(f).write_text(text)
    spec = mdl.load(d).spec
    assert (spec.flows["briefs-written"].target, spec.flows["days-ending"].source) == ("day-briefed", "day-briefed")
    assert spec.stocks["day-briefed"].unit == "days" and spec.stocks["day-briefed"].inferred
    assert _found(d, *structural.CHAIN_CODES) == {}


def test_a_stock_gathering_from_every_state_is_not_a_second_arrival(tmp_path):
    d = _write(tmp_path / "j", """
        projections:
          job: {id: job/*, states: [new, built, stopped]}
        stocks:
          new: {unit: jobs, sensor: {projection: job, state: new}}
          built: {unit: jobs, sensor: {projection: job, state: built}}
          stopped: {unit: jobs, sensor: {projection: job, state: stopped}}
        flows:
          arriving: {to: new, sensor: {projection: job, entering: new}}
          made: {from: new, to: built, sensor: {projection: job, entering: built}}
          shipping: {from: built}
          stopping: {to: stopped, sensor: {projection: job, entering: stopped}}
          unsticking: {from: stopped, sensor: {projection: job, leaving: stopped}}
        blocks:
          build: {type: program, run: 'true', takes: {projection: job, at: new, to: [built, stopped]}, out: flow.made}
          ship: {type: program, run: 'true', takes: {projection: job, at: built, to: [stopped]}, out: flow.shipping}
    """)
    assert _found(d, "projection-enters-many-times") == {}


def test_try_change_takes_it_as_evidence(tmp_path):
    d = _write(tmp_path / "t", TICKETS)
    p = Project(mdl.load(d))
    r = im.trial(p, {"kind": "structure", "parts": ["flow.started", "stock.triaged"], "title": "doing comes from triaged",
                     "edit": {"file": "ergostat.yaml", "replace": "  started:\n    to: wip",
                              "with": "  started:\n    from: triaged\n    to: wip"},
                     "reasons": [{"says": "tickets are triaged before they are started",
                                  "evidence": "finding:projection-enters-many-times@projections.ticket"}]})
    assert "projection-enters-many-times@projections.ticket" in r["findings"]["answered"], r


def _clouds(n_stocks: int, n_in: int) -> str:
    out = ["stocks:"] + [f"  s{i}: {{unit: things, sensor: {{run: echo 1, every: 1m}}}}" for i in range(n_stocks)]
    out += ["flows:"] + [f"  in{i}: {{to: s{i % n_stocks}}}" for i in range(n_in)]
    out += [f"  out{i}: {{from: s{i}, driven-by: +stock.s{i}}}" for i in range(n_stocks)]
    return "\n".join(out) + "\n"


@pytest.mark.parametrize("stocks,inflows,said", [(8, 5, True), (8, 4, False), (12, 6, False), (3, 3, False)])
def test_many_inflows_from_clouds_for_the_stocks_is_a_note_on_the_boundary(tmp_path, stocks, inflows, said):
    d = _write(tmp_path / "m", _clouds(stocks, inflows))
    got = _found(d, "many-cloud-inflows")
    assert bool(got) == said
    if said:
        x = got["many-cloud-inflows@model"]
        assert f"{inflows} inflows from outside (clouds) for its {stocks} stocks" in x.message
        assert "boundary chart" in x.message and "decide what is really outside" in x.message


def test_each_kind_s_one_arrival_and_two_way_flows_are_not_counted(tmp_path):
    kinds = [f"k{i}" for i in range(6)]
    text = ["projections:"] + [f"  {k}: {{id: {k}/*, states: [new, done]}}" for k in kinds] + ["stocks:"]
    text += [f"  {k}-new: {{unit: things, sensor: {{projection: {k}, state: new}}}}" for k in kinds]
    text += ["  level: {unit: things, sensor: {run: echo 1, every: 1m}}", "flows:"]
    text += [f"  {k}-arriving: {{to: {k}-new, sensor: {{projection: {k}, entering: new}}}}" for k in kinds]
    text += [f"  {k}-done: {{from: {k}-new, sensor: {{projection: {k}, entering: done}}}}" for k in kinds]
    text += [f"  level-{i}: {{to: level, two-way: true}}" for i in range(6)]
    d = _write(tmp_path / "k", "\n".join(text) + "\n")
    assert _found(d, "many-cloud-inflows", "projection-enters-many-times") == {}


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_no_example_is_found_crossing_its_boundary_more_than_once(example):
    assert [str(x) for x in _found(example, "projection-enters-many-times", "many-cloud-inflows").values()] == []
