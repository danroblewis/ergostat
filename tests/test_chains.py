"""A kind's state stocks, chained (spec/chains.py): a stock per state with each move an outflow to a cloud is found,
with file and line, and each finding names the change that chains it; the changes, proposed as structure and applied,
leave one chain in both views. Shaped exactly like the owner's report: thirteen states of a feature-flag ramp, each
stock draining to a cloud, a goal and a block on each step but the last."""

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
STATES = ("requested triaged researched risk-assessed approved scheduled ramp-1 ramp-10 ramp-50 ramp-100 verified "
          "confirmed applied").split()
CHAIN = {"outflow-not-chained", "inflow-not-chained", "state-stock-without-inflow", "move-without-flow",
         "state-stocks-disconnected", "loops-not-connected"}


def owners_model(counted: str = "entering") -> str:
    """Thirteen stocks, one per state, each drained to a cloud: what the work agent wrote. ``counted``: each outflow
    measured as the items entering the next state, or leaving its own."""
    out = ["name: ff-ramp", "items:", "  ff-ticket:", "    id: ff/*", f"    states: [{', '.join(STATES)}]", "    on:"]
    out += [f"      ff.{s}: {s}" for s in STATES[1:]]
    out.append("stocks:")
    for s in STATES:
        out += [f"  ff-{s}:", "    unit: tickets", "    sensor:", "      items: ff-ticket", f"      state: {s}", "      every: 10s"]
    out.append("flows:")
    for i, s in enumerate(STATES):
        nxt = STATES[i + 1] if i + 1 < len(STATES) else None
        what = f"entering: {nxt}" if counted == "entering" and nxt else f"leaving: {s}"
        out += [f"  ff-from-{s}:", f"    from: ff-{s}", f"    driven-by: [+stock.ff-{s}]", "    sensor:", "      items: ff-ticket",
                f"      {what}", "      over: 1h"]
    out.append("goals:")
    for s in STATES[:-1]:
        out += [f"  {s}-clear:", f"    stock: ff-{s}", '    hold: "<= 0"']
    out.append("blocks:")
    for s in STATES[:-1]:
        out += [f"  do-{s}:", "    type: program", f"    goal: {s}-clear", "    run: 'true'", "    every: 1m", f"    out: flow.ff-from-{s}"]
    return "\n".join(out) + "\n"


def _write(d: Path, text: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(text)
    return d


def _chain_findings(d: Path) -> list:
    _, problems = read(d / "ergostat.yaml")
    return [x for x in problems if x.code in CHAIN]


def _components(nodes: list[dict], edges: list[dict]) -> int:
    parent = {n["id"]: n["id"] for n in nodes}

    def root(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for e in edges:
        a, b = e.get("from") or e.get("source"), e.get("target") or e.get("to")
        if a in parent and b in parent:
            parent[root(a)] = root(b)
    return len({root(x) for x in parent})


def _views(d: Path) -> dict[str, int]:
    from ergostat.web.server import Live, api
    live = Live(Project(mdl.load(d)))
    return {v: _components(g["nodes"], g["edges"]) for v in ("dynamics", "blocks")
            for g in [api(live, "graph", {"view": [v], "open": ["*"]})]}


@pytest.mark.parametrize("counted", ["entering", "leaving"])
def test_the_owners_model_is_found_with_each_fix_named_where_it_is_written(tmp_path, counted):
    d = _write(tmp_path / "ff", owners_model(counted))
    got = _chain_findings(d)
    codes = sorted(x.code for x in got)
    assert codes == sorted(["state-stock-without-inflow"] + ["outflow-not-chained"] * 12 +
                           ["state-stocks-disconnected", "loops-not-connected"])
    for x in got:                                                 # each with its file and line
        assert x.where is not None and x.where.file.name == "ergostat.yaml" and x.where.line > 0
    by = {x.about: x for x in got if x.code == "outflow-not-chained"}
    first = by["flow.ff-from-requested"].message
    assert "write to: ff-triaged on flow ff-from-requested" in first
    assert ("counts them entering triaged" if counted == "entering" else "the kind's states, requested before triaged") in first
    assert "flow.ff-from-applied" not in by                       # the last one's outflow is the completions: right
    arrive = next(x for x in got if x.code == "state-stock-without-inflow")
    assert arrive.about == "stock.ff-requested" and \
        "flow ff-requested-arriving from outside to ff-requested, measured as items of ff-ticket entering requested" in arrive.message
    pieces = next(x for x in got if x.code == "state-stocks-disconnected")
    assert "13 pieces" in pieces.message and len(chains.analyse(read(d / "ergostat.yaml")[0], {})[-2].fixes) == 13
    assert "12 groups that share no stock" in next(x for x in got if x.code == "loops-not-connected").message


def test_the_proposed_chain_applied_joins_both_views_into_one(tmp_path):
    d = _write(tmp_path / "ff", owners_model())
    assert _views(d) == {"dynamics": 13, "blocks": 12}            # what the owner saw: 13 stocks apart, 12 loops apart
    p = Project(mdl.load(d))
    out, not_made = structural.find(p, p.model.spec, None)
    assert not not_made
    mine = [x for x in out if x["code"] in CHAIN]
    assert sorted(x["code"] for x in mine) == sorted(["state-stock-without-inflow"] + ["outflow-not-chained"] * 12 +
                                                     ["state-stocks-disconnected"])
    assert all(x["rewires"] for x in mine)                        # each waits for the owner, whatever the judge's policy
    whole = next(x for x in mine if x["code"] == "state-stocks-disconnected")
    assert whole["title"] == "Chain the state stocks of ff-ticket"
    for f, text in ye.apply_together(tr.edits_of(whole)).items():
        Path(f).write_text(text)
    assert _chain_findings(d) == []
    spec = mdl.load(d).spec
    assert [spec.flows[f"ff-from-{s}"].target for s in STATES[:-1]] == [f"ff-{s}" for s in STATES[1:]]
    assert spec.flows["ff-from-applied"].target is None           # completions leave at the end
    assert spec.flows["ff-requested-arriving"].target == "ff-requested" and spec.flows["ff-requested-arriving"].inferred
    assert _views(d) == {"dynamics": 1, "blocks": 1}


def test_try_change_takes_a_chain_finding_as_evidence(tmp_path):
    d = _write(tmp_path / "ff", owners_model())
    p = Project(mdl.load(d))
    r = im.trial(p, {"kind": "structure", "parts": ["flow.ff-from-requested", "stock.ff-triaged"],
                     "title": "requested goes on to triaged",
                     "edit": {"file": "ergostat.yaml", "replace": "  ff-from-requested:\n    from: ff-requested",
                              "with": "  ff-from-requested:\n    from: ff-requested\n    to: ff-triaged"},
                     "reasons": [{"says": "its items go on to triaged",
                                  "evidence": "finding:outflow-not-chained@flow.ff-from-requested"}]})
    assert r["would"] == "be proposed", r
    assert "outflow-not-chained@flow.ff-from-requested" in r["findings"]["answered"]


RECORDED = """
name: approvals
items:
  req:
    id: req/*
    states: [new, checked, approved, done]
    on: {req.checked: checked, req.approved: approved, req.reopened: new, req.done: done}
stocks:
  waiting: {unit: reqs, sensor: {items: req, state: new, every: 10s}}
  checked: {unit: reqs, sensor: {items: req, state: checked, every: 10s}}
  approved: {unit: reqs, sensor: {items: req, state: approved, every: 10s}}
flows:
  arriving: {to: waiting, sensor: {items: req, entering: new, over: 1h}}
  checking: {from: waiting, to: checked, sensor: {items: req, entering: checked, over: 1h}}
  approvals:
    to: approved
    sensor: {run: echo 1, every: 1m}
  closing: {from: approved, sensor: {items: req, entering: done, over: 1h}}
"""


def test_the_record_s_moves_find_a_flow_from_outside_and_a_move_no_flow_carries(tmp_path):
    d = _write(tmp_path / "rq", textwrap.dedent(RECORDED))
    assert _chain_findings(d) == []                               # the structure alone says nothing is wrong
    p = Project(mdl.load(d))
    for i in range(3):
        it = f"req/{i}"
        p.events.add("req.created", item=it, source="t")
        p.events.add("req.checked", item=it, source="t")
        p.events.add("ergostat.lease.taken", item=it, source="ergostat",
                     data={"run": f"r{i}", "block": "approver", "fence": 1, "back": "checked", "attempt": 1})
        p.events.add("req.approved" if i else "req.reopened", item=it, source="approver")
    chains._CACHE.clear()
    moves = chains.recorded(p.model.spec)["req"]
    assert moves[("checked", "approved")] == 2 and moves[("checked", "new")] == 1   # the lease's hold taken out
    assert not any("leased" in m for m in moves)
    got = {f"{x.code}@{x.about}": x for x in _chain_findings(d)}
    assert set(got) == {"inflow-not-chained@flow.approvals", "move-without-flow@stock.waiting",
                        "state-stocks-disconnected@stock.waiting"}         # approved: a piece of its own
    assert "from: checked on flow approvals" in got["inflow-not-chained@flow.approvals"].message
    assert "flow checked-to-waiting from checked to waiting, measured as items of req entering new" in \
        got["move-without-flow@stock.waiting"].message
    assert "2 moves in the record" in got["inflow-not-chained@flow.approvals"].message


def test_a_stock_gathering_from_every_state_and_a_stage_between_are_chained(tmp_path):
    """The ticket factory's stopped (filled from outside by every item entering it, from many steps), and the steps
    template's work in progress (a stock of the items leased at a state, between it and the next), are a chain."""
    text = textwrap.dedent("""
        items:
          job:
            id: job/*
            states: [new, built, shipped, stopped]
            on: {job.built: built, job.shipped: shipped, job.stopped: stopped}
        stocks:
          new: {unit: jobs, sensor: {items: job, state: new}}
          building: {unit: jobs, sensor: {items: job, state: leased, where: {lease.back: new}}}
          built: {unit: jobs, sensor: {items: job, state: built}}
          stopped: {unit: jobs, sensor: {items: job, state: stopped}}
        flows:
          arriving: {to: new, sensor: {items: job, entering: new}}
          taken: {from: new, to: building}
          made: {from: building, to: built, sensor: {items: job, entering: built}}
          shipping: {from: built, sensor: {items: job, entering: shipped}}
          stopping: {to: stopped, sensor: {items: job, entering: stopped}}
          unsticking: {from: stopped, sensor: {items: job, leaving: stopped}}
        blocks:
          build: {type: program, run: 'true', takes: {kind: job, at: new, to: [built, stopped]}, out: flow.made}
          ship: {type: program, run: 'true', takes: {kind: job, at: built, to: [shipped, stopped]}, out: flow.shipping}
    """)
    d = _write(tmp_path / "jobs", text)
    assert _chain_findings(d) == []
    from collections import Counter                               # a record: one stopped job sent back to one step
    moves = Counter({("new", "built"): 4, ("built", "shipped"): 3, ("new", "stopped"): 1, ("stopped", "new"): 1})
    assert chains.analyse(read(d / "ergostat.yaml")[0], {"job": moves}) == []


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_no_example_is_found_unchained(example):
    assert [str(x) for x in _chain_findings(example)] == []


def test_where_drawn_says_the_pieces_each_view_falls_into(tmp_path):
    from ergostat.library import author
    head = "systems:\n  ff:\n    description: the ramp\ndefaults:\n  system: ff\n"
    d = _write(tmp_path / "ff", head + owners_model())
    s = author.shape(Project(mdl.load(d)), "ff")
    assert (s["dynamics_pieces"], s["blocks_pieces"]) == (13, 12)
    assert any(x.startswith("outflow-not-chained (flow.ff-from-requested)") for x in s["chain_findings"])
