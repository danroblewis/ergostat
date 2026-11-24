"""Each kind says which of its states are finished, from one function (dev/records/items-kinds-say-which-states-finish.md):
spec/finished.py finish_of, used by the Items listing, the relations (precedence.Kinds), the estimates, the state
counts over time (series.py), and with dead (ends_of) the process map (process.py) and message routing
(messages/route.py), whose outputs change only where the parity test lists
(dev/records/finished-rule-in-series-and-routing.md)."""

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
    src = {f: (ROOT / "ergostat" / f).read_text() for f in ("precedence.py", "spec/items.py", "numbers/etamodel.py",
                                                         "process.py", "series.py")}
    assert not [f for f, s in src.items() if "done_states" in s]        # none decides it but finish_of
    assert "itemindex import done_states" not in (ROOT / "ergostat" / "messages" / "route.py").read_text()
    assert [str(f.relative_to(ROOT)) for f in sorted((ROOT / "ergostat").rglob("*.py"))
            if "def done_states" in f.read_text()] == ["ergostat/spec/itemindex.py"]


T0 = 1_700_000_000.0


def _factory_record(tmp_path) -> Project:
    """gap: declared (a merged, b parked); answer: inferred (1 answered, 2 asked); pool: one state (x held)."""
    p = factory(tmp_path)
    for i, (e, it) in enumerate((("gap.opened", "gap/a"), ("gap.merged", "gap/a"), ("gap.opened", "gap/b"),
                                 ("gap.parked", "gap/b"), ("answer.asked", "answer/1"), ("answer.given", "answer/1"),
                                 ("answer.asked", "answer/2"), ("pool.measured", "pool/x"))):
        p.events.add(e, item=it, at=T0 + 10 * i)
    return p


def test_the_process_maps_end_is_where_the_items_list_says_items_end(tmp_path):
    from ergostat import process
    p = _factory_record(tmp_path)
    for kind, ended in (("gap", ["gap/a"]), ("answer", ["answer/1"]), ("pool", [])):
        assert sorted(process.items_through(p.events, p.model.spec, kind, T0 - 10, T0 + 100, "states", "$")) == ended, kind
    assert process._done(p.model.spec, p.events, p.model.spec.items["pool"]) == set()   # the older rule: {held}


def test_the_state_counts_over_time_finish_where_finish_of_says(tmp_path):
    from ergostat import series
    p = _factory_record(tmp_path)
    snap = {"at": T0 + 100, "window": 200}
    got = {k: series.items_flow(p, snap, k, 10) for k in ("gap", "answer", "pool")}
    assert {k: g["finished_states"] for k, g in got.items()} == {"gap": ["merged", "closed"], "answer": ["answered"], "pool": []}
    assert [f["id"] for f in got["gap"]["finished"]] == ["gap/a"] and got["pool"]["finished"] == []


def test_message_routing_keeps_its_own_rule_for_where_a_message_goes(tmp_path):
    """Declared and inferred as finish_of says; a kind's one state, and a state items rest in that none has gone on
    from, are its own (SPEC §5a, *Which states are finished*)."""
    from ergostat.messages import route
    p = _factory_record(tmp_path)
    spec = p.model.spec
    ids = ["gap/a", "gap/b", "answer/1", "answer/2", "pool/x"]
    work = {w["id"]: w for w in route.work_items(p, spec, ids=ids)}
    assert {i: work[i]["finished"] for i in ids} == {"gap/a": True, "gap/b": False, "answer/1": True, "answer/2": False,
                                                     "pool/x": True}                # finish_of: a pool lives on
    to, finished = route.targets(p, spec, ids, [], work, [])
    assert finished == ["gap/a", "answer/1", "pool/x"] and [t["item"] for t in to] == ["gap/b", "answer/2"]
    gap = spec.items["gap"]
    assert route.route_done_states(spec, gap) == {"merged", "closed"}
    from types import SimpleNamespace
    rv = SimpleNamespace(name="review", states=["requested", "briefed", "answered"])     # one review briefed
    assert route.route_done_states(spec, rv, left={"requested"}, reached={"requested", "briefed"}) == {"answered"}
    assert route.route_done_states(spec, rv, left={"requested"}, reached={"briefed", "answered"}) == {"briefed", "answered"}


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
    out, said = {}, {}            # said: the finished states items-flow names
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
            if k.states:
                said[f"{demo}/{name}/series"] = out[f"{demo}/{name}/series"]["finished_states"]
    return {k: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest() for k, v in out.items()}, said


# What the change to finish_of changed, per demo, kind and output (and why); everything else stays byte-identical.
# Only series changed: its finished_states (and so its finished items and median) read no ``messages: {done:}`` and
# took ``leased`` and ``dead`` as finished, being states no item had left; now finish_of's. The process map's end
# (ends_of) is what it was on every demo; routing keeps its own rule (route_done_states), so none of its targets moves.
_TAKEN = {"action": "done", "alert": "commented", "ci": "upgraded", "doc": "approved", "mention": "answered",
          "pr": "closed", "secret": "rotated", "team-pr": "moving", "ticket": "answered", "update": "sent"}
CHANGED: dict[str, str] = {
    "image-squeeze/hypothesis/series": "[leased, dropped, dead] -> [kept, dropped] (declared)",
    "roadmap/epic/series": "[underway, shipped] -> [shipped] (declared)",
    "roadmap/ticket/series": "[leased, done, dead] -> [done] (declared)",
    "the-job/ramp/series": "[leased, proved-fine, dead] -> [approved, rejected, broke, proved-fine] (declared)",
    "the-job/review/series": "[leased, answered, dead] -> [answered] (declared)",
    "ticket-factory/report/series": "[written] -> [] (one state: it lives on)",
    "ticket-factory/ticket/series": "[leased, stopped, dead] -> [done] (declared)",
    **{f"the-job/{k}/series": f"[leased, {s}, dead] -> [{s}] (inferred)" for k, s in _TAKEN.items()},
}


def test_the_process_map_the_state_counts_and_routing_change_only_where_listed(tmp_path):
    """The parity test: the outputs as main gave them before these callers took finish_of (written by this test when
    missing, which then fails until it is committed), byte-identical but for ``CHANGED``, each of which did change."""
    got, said = parity_outputs(tmp_path)
    if not PARITY.exists():
        PARITY.write_text(json.dumps(got, sort_keys=True, indent=1) + "\n")
        raise AssertionError(f"{PARITY} written: check it and commit it")
    before = json.loads(PARITY.read_text())
    assert sorted(got) == sorted(before) and len(got) > 100
    changed = sorted(k for k in got if got[k] != before[k])
    assert changed == sorted(CHANGED), "\n".join(changed)
    for k, why in CHANGED.items():                       # each change is what it says (the states before: git history)
        assert "[" + ", ".join(said[k]) + "]" == why.split("-> ")[1].split(" (")[0], k
