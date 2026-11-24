"""Each kind says which of its states are finished, from one function (dev/records/items-kinds-say-which-states-finish.md):
spec/finished.py finish_of, used by the Items listing, the relations (precedence.Kinds) and the estimates; the older
rule's own callers (process.py, series.py, messages/route.py) give what they gave before."""

from __future__ import annotations

import hashlib
import json
import shutil
import textwrap
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat import precedence as pr
from ergostat.spec import items as its
from ergostat.spec.finished import finish_of
from ergostat.spec.itemindex import done_states
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
PARITY = ROOT / "tests" / "fixtures" / "finished_parity.json"
DEMOS = ("first-loop", "image-squeeze", "roadmap", "software-factory", "the-job", "ticket-factory")

FACTORY = """
items:
  gap:
    id: gap/*
    states: [open, ready, building, in-review, merged, parked, closed]
    on: {gap.opened: open, gap.ready: ready, gap.started: building, gap.built: in-review, gap.merged: merged,
         gap.parked: parked, gap.closed: closed}
  pool:
    id: pool/*
    states: [held]
    on: {pool.measured: held}
  answer:
    id: answer/*
    states: [asked, answered]
    on: {answer.asked: asked, answer.given: answered}
messages:
  done: {gap: [merged, closed]}
  paused: {gap: [parked]}
"""


def factory(tmp_path) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(FACTORY))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def test_a_factory_shaped_gap_is_declared_and_its_pool_lives_on(tmp_path):
    spec = factory(tmp_path).model.spec
    gap = finish_of(spec, "gap", set())
    assert (gap["finished"], gap["paused"], gap["from"], gap["lives_on"]) == (["merged", "closed"], ["parked"], "declared", False)
    pool = finish_of(spec, "pool", {"held"})
    assert (pool["finished"], pool["from"], pool["lives_on"]) == ([], "none", True)
    assert finish_of(spec, "pool", set())["lives_on"]                       # one state: never done, left or not
    assert finish_of(spec, "nothing", set())["lives_on"]


def test_nothing_inferable_lives_on_where_the_older_rule_took_the_last_state(tmp_path):
    spec = factory(tmp_path).model.spec
    assert finish_of(spec, "answer", set())["finished"] == ["answered"]
    gone = finish_of(spec, "answer", {"asked", "answered"})
    assert (gone["finished"], gone["from"], gone["lives_on"]) == ([], "none", True)
    assert done_states(spec.items["answer"], {"asked", "answered"}) == ["answered"]   # the older rule, kept for its callers
    assert done_states(spec.items["pool"], set()) == ["held"]


def test_ticket_factory_kinds_say_where_their_finish_comes_from():
    """The definition named ticket-factory's ticket as inferred; it declares ``done: {ticket: [done]}``, so its okr
    (nothing declared) is the inferred one, and its report (one state) lives on."""
    spec = mdl.load(ROOT / "examples" / "ticket-factory").spec
    assert (finish_of(spec, "ticket", set())["finished"], finish_of(spec, "ticket", set())["from"]) == (["done"], "declared")
    okr = finish_of(spec, "okr", {"at-risk"})
    assert (okr["finished"], okr["from"], okr["lives_on"]) == (["off-track"], "inferred", False)
    assert finish_of(spec, "report", set())["lives_on"]


def test_the_listing_the_relations_and_the_estimates_say_the_same(tmp_path):
    p = factory(tmp_path)
    ev, spec, t = p.events, p.model.spec, time.time() - 100
    ev.add("gap.opened", item="gap/a", at=t)
    ev.add("gap.merged", item="gap/a", at=t + 1)
    ev.add("pool.measured", item="pool/x", at=t + 2)
    ev.add("answer.asked", item="answer/1", at=t + 3)
    ev.add("answer.given", item="answer/1", at=t + 4)
    kinds = {k["name"]: k for k in its.listing(ev, spec)["kinds"]}
    assert {f: kinds["gap"][f] for f in ("finished", "paused", "dead", "finished_from", "lives_on")} == \
        {"finished": ["merged", "closed"], "paused": ["parked"], "dead": False, "finished_from": "declared", "lives_on": False}
    assert kinds["pool"]["lives_on"] and kinds["pool"]["finished"] == [] and kinds["pool"]["finished_from"] == "none"
    assert kinds["answer"]["finished"] == ["answered"] and kinds["answer"]["finished_from"] == "inferred"
    from ergostat.spec.itemindex import index_for
    info = pr.Kinds(spec, index_for(ev, spec, False))
    assert info["gap"]["finished"] == ["merged", "closed"] and info["gap"]["paused"] == ["parked"]
    assert info["pool"]["finished"] == []
    src = {f: (ROOT / "ergostat" / f).read_text() for f in ("precedence.py", "spec/items.py", "numbers/etamodel.py")}
    assert not [f for f, s in src.items() if "done_states" in s]        # none decides it but finish_of


T0 = 1_700_000_000.0


def _seed(p) -> float:
    """Per kind, one item through every state its events name, one left in its first and one in its second; returns
    when the last move was."""
    t = T0
    for k in p.model.spec.items.values():
        if not k.states or "*" not in k.id:
            continue
        on = sorted(((e, s) for e, s in k.on.items() if "*" not in e and s in k.states), key=lambda x: k.states.index(x[1]))
        for n, steps in (("p1", on), ("p2", on[:1]), ("p3", on[:2])):
            for i, (e, _) in enumerate(steps):
                p.events.add(e, item=k.id.replace("*", n, 1).replace("*", "x"), at=t + 10 * i)
            t += 100
    return t


def parity_outputs(tmp_path) -> dict:
    """Per demo and kind, on a seeded record: the process map (``process.process``, by states), the state counts over
    time and their finished items (``series.items_flow``, ``/api/items-flow``), and message routing's targets for a
    message about each item (``route.targets`` over ``route.work_items``)."""
    from ergostat import process, series
    from ergostat.messages import route
    out = {}
    for demo in DEMOS:
        d = tmp_path / demo
        shutil.copytree(ROOT / "examples" / demo, d, ignore=shutil.ignore_patterns("run", "reports", "__pycache__"))
        p = Project(mdl.load(d))
        spec = p.model.spec
        until = _seed(p) + 100
        snap = {"at": until, "window": until - T0 + 100}
        for name, k in spec.items.items():
            ids = sorted({e["item"] for e in p.events.query(n=None, since=T0 - 1) if k.matches(e.get("item") or "")})
            work = {w["id"]: w for w in route.work_items(p, spec, ids=ids) if w["kind"] == name}
            out[f"{demo}/{name}/process"] = process.process(p.events, spec, [name], T0 - 100, until, by="states")
            out[f"{demo}/{name}/series"] = series.items_flow(p, snap, name, 20) if k.states else None
            out[f"{demo}/{name}/route"] = route.targets(p, spec, ids, [], work, [])
    return {k: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest() for k, v in out.items()}


# What the change to finish_of changed, per demo, kind and output (and why); everything else stays byte-identical.
CHANGED: dict[str, str] = {}


def test_the_process_map_the_state_counts_and_routing_change_only_where_listed(tmp_path):
    """The parity test: the outputs as main gave them before these callers took finish_of (written by this test when
    missing, which then fails until it is committed), byte-identical but for ``CHANGED``, each of which did change."""
    got = parity_outputs(tmp_path)
    if not PARITY.exists():
        PARITY.write_text(json.dumps(got, sort_keys=True, indent=1) + "\n")
        raise AssertionError(f"{PARITY} written: check it and commit it")
    before = json.loads(PARITY.read_text())
    assert sorted(got) == sorted(before) and len(got) > 100
    assert sorted(k for k in got if got[k] != before[k]) == sorted(CHANGED)
