"""Each kind says which of its states are finished, from one function (dev/records/items-kinds-say-which-states-finish.md):
spec/finished.py finish_of, used by the Items listing, the relations (precedence.Kinds), the estimates, the state
counts over time (series.py) and, with dead (ends_of), the process map and the item detail's final (process.py);
message routing (messages/route.py) keeps its own rule. Their outputs change only where the parity test lists
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
projections:
  gap:
    match:
      key: gap/*
    states: [open, ready, building, in-review, merged, parked, closed]
    events:
      gap.opened:
        state: set('open')
      gap.ready:
        state: set('ready')
      gap.started:
        state: set('building')
      gap.built:
        state: set('in-review')
      gap.merged:
        state: set('merged')
      gap.parked:
        state: set('parked')
      gap.closed:
        state: set('closed')
    otherwise: rest
  pool:
    match:
      key: pool/*
    states: [held]
    events:
      pool.measured:
        state: set('held')
    otherwise: rest
  answer:
    match:
      key: answer/*
    states: [asked, answered]
    events:
      answer.asked:
        state: set('asked')
      answer.given:
        state: set('answered')
    otherwise: rest
  task:
    match:
      key: task/*
    states: [todo, doing, waiting, done]
    events:
      task.made:
        state: set('todo')
      task.begun:
        state: set('doing')
      task.waits:
        state: set('waiting')
      task.done:
        state: set('done')
    otherwise: rest
messages:
  done: {gap: [merged, closed]}
  paused: {gap: [parked], task: [waiting]}
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




def test_the_listing_the_relations_and_the_estimates_say_the_same(tmp_path):
    p = factory(tmp_path)
    ev, spec, t = p.events, p.model.spec, time.time() - 100
    ev.add("gap.opened", item="gap/a", at=t)
    ev.add("gap.merged", item="gap/a", at=t + 1)
    ev.add("pool.measured", item="pool/x", at=t + 2)
    ev.add("answer.asked", item="answer/1", at=t + 3)
    ev.add("answer.given", item="answer/1", at=t + 4)
    kinds = {k["name"]: k for k in its.listing(ev, spec)["projections"]}
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


def _seed(p, every_left: bool = False) -> float:
    """Per kind, one item through every state its events name but the paused, one left in its first and one in its
    second; a taken kind's one dead-lettered (taken, handed back unfinished: its one attempt) and one leased now; one
    in each paused state, which no item has left. ``every_left``: instead one item through every state and back to the
    first, so each state is left, and one through every state, resting in the last. Returns when the last move was."""
    from ergostat.leases import ENDED, TAKEN
    from ergostat.spec.ir import DEAD
    spec, t = p.model.spec, T0
    for k in spec.items.values():
        if not k.states or "*" not in k.id:
            continue
        on = sorted(((e, s) for e, s in k.on.items() if "*" not in e and s in k.states), key=lambda x: k.states.index(x[1]))
        taken = DEAD in k.states and on
        lease = {"run": "r", "block": "b", "fence": 1, "ttl": 60, "max": 1}
        paused = [x for s in (spec.messages.paused or {}).get(k.name) or [] for x in on if x[1] == s]
        seeds = [("p1", on + on[:1]), ("p2", on)] if every_left else [
            ("p1", [x for x in on if x not in paused]), ("p2", on[:1]), ("p3", on[:2]),
            *([("p4", [*on[:1], (TAKEN, lease), (ENDED, {"fence": 1, "run": "r", "how": "nack"})]),
               ("p5", [*on[:1], (TAKEN, lease)])] if taken else []),
            *[(f"p6{i}", [*on[:1], x]) for i, x in enumerate(paused)]]
        for n, steps in seeds:
            for i, (e, data) in enumerate(steps):
                p.events.add(e, item=k.id.replace("*", n, 1).replace("*", "x"), at=t + 10 * i,
                             data=data if isinstance(data, dict) else None)
            t += 100
    return t


def parity_outputs(tmp_path) -> dict:
    """Per demo (and the factory-shaped fixture) and kind, on each seeded record (``@left``: every state left): the
    process map (``process.process``, by states) and its end, as the item detail's ``kind_of.final`` gives it
    (``web/server.py``), the state counts over time and their finished items (``series.items_flow``,
    ``/api/items-flow``), and message routing's targets for a message about each item (``route.targets`` over
    ``route.work_items``). Returns their hashes, and what each says is finished (``said``: final and series)."""
    from ergostat import process, series
    from ergostat.messages import route
    out, said = {}, {}
    for demo in (*DEMOS, "factory"):
        for every_left, tag in ((False, ""), (True, "@left")):
            d = tmp_path / f"{demo}{tag}"
            if demo == "factory":
                d.mkdir()
                (d / "ergostat.yaml").write_text(textwrap.dedent(FACTORY))
            else:
                shutil.copytree(ROOT / "examples" / demo, d, ignore=shutil.ignore_patterns("run", "reports", "__pycache__"))
            p = Project(mdl.load(d))
            spec = p.model.spec
            until = _seed(p, every_left) + 100
            snap = {"at": until, "window": until - T0 + 100}
            for name, k in spec.items.items():
                key = f"{demo}{tag}/{name}"
                ids = sorted({e["item"] for e in p.events.query(n=None, since=T0 - 1) if k.matches(e.get("item") or "")})
                work = {w["id"]: w for w in route.work_items(p, spec, ids=ids) if w["kind"] == name}
                out[f"{key}/process"] = process.process(p.events, spec, [name], T0 - 100, until, by="states")
                ends = process._done(spec, p.events, k)                 # as web/server.py's /api/items/<id> reads it
                out[f"{key}/final"] = said[f"{key}/final"] = [s for s in k.states if s in ends]
                out[f"{key}/series"] = series.items_flow(p, snap, name, 20) if k.states else None
                out[f"{key}/route"] = route.targets(p, spec, ids, [], work, [])
                if k.states:
                    said[f"{key}/series"] = out[f"{key}/series"]["finished_states"]
    return {k: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest() for k, v in out.items()}, said


# What the callers taking finish_of changed, per demo (``@left``: its every-state-left record), kind and output, with
# the finished states before and after (``final``: the process map's end and the item detail's ``kind_of.final``;
# ``series``: /api/items-flow's finished_states, and so its finished items and median). Everything else, and every
# routing target (route_done_states keeps its rule), is byte-identical.
def _rows(keys, outs: str, before: str, after: str, why: str) -> dict[str, str]:
    return {f"{k}/{o}": f"{before} -> {after} ({why})" for k in keys for o in outs.split()}


_TAKEN = {"action": "done", "alert": "commented", "ci": "upgraded", "doc": "approved", "mention": "answered",
          "pr": "closed", "secret": "rotated", "team-pr": "moving", "ticket": "answered", "update": "sent"}
_DECLARED_TAKEN = {"image-squeeze/hypothesis": ("[kept, dropped]", "[dropped, dead]"),
                   "roadmap/ticket": ("[done]", "[done, dead]"),
                   "the-job/ramp": ("[approved, rejected, broke, proved-fine]", "[proved-fine, dead]"),
                   "the-job/review": ("[answered]", "[answered, dead]"),
                   "ticket-factory/ticket": ("[done]", "[stopped, dead]")}
_BUILT_IN = {"claim": "unchecked", "context": "failed", "correction": "dismissed", "decision": "dismissed",
             "message": "answered", "model-change": "inconclusive", "modelling-request": "dismissed",
             "report": "dismissed", "verdict": "missed"}
_LAST = {**{f"{d}@left/ergostat.{k}": s for d in (*DEMOS, "factory") for k, s in _BUILT_IN.items()},
         "ticket-factory@left/ergostat.workspace": "quarantined", "factory@left/answer": "answered",
         "factory@left/task": "done", "image-squeeze@left/case": "met", "image-squeeze@left/session": "lost",
         "software-factory@left/pr": "deployed", "software-factory@left/ticket": "dropped", "the-job@left/day": "recorded",
         "the-job@left/outage": "reviewed", "the-job@left/session": "lost", "ticket-factory@left/okr": "off-track"}
CHANGED: dict[str, str] = {
    # a declared taken kind: a dead letter now ends on the map, as the Items list hides it (the old rule read the
    # declared states alone); the state counts read the declared states, where they took those no item had left
    **{k: v for kind, (f, s) in _DECLARED_TAKEN.items() for k, v in {
        **_rows([kind], "final process", f, f"{f[:-1]}, dead]", "declared, taken: a dead letter ends"),
        **_rows([f"{kind.replace('/', '@left/', 1)}"], "final", f, f"{f[:-1]}, dead]", "declared, taken: a dead letter ends"),
        **_rows([kind], "series", s, f, "declared"),
        **_rows([kind.replace("/", "@left/", 1)], "series", "[leased, dead]", f, "declared")}.items()},
    **_rows(["factory/gap"], "series", "[parked, closed]", "[merged, closed]", "declared"),
    **_rows(["factory@left/gap"], "series", "[closed]", "[merged, closed]", "declared"),
    **_rows(["roadmap/epic", "roadmap@left/epic"], "series", "[underway, shipped]", "[shipped]", "declared"),
    # an inferred taken kind: a dead letter is no finished work in the state counts (the map's end keeps it)
    **{k: v for t, s in _TAKEN.items() for k, v in _rows([f"the-job/{t}"], "series", f"[{s}, dead]", f"[{s}]",
                                                          "inferred: dead is no finish").items()},
    # one state: a pool lives on, it never ends (factory's pool has an item, so its map changes too)
    **_rows(["factory/pool", "factory@left/pool"], "final process series", "[held]", "[]", "one state: lives on"),
    **_rows(["ticket-factory/report", "ticket-factory@left/report"], "final series", "[written]", "[]", "one state: lives on"),
    # a paused state no item has left is not finished (an item resting there no longer ends on the map)
    **_rows(["factory/task"], "final process series", "[waiting, done]", "[done]", "paused is never finished"),
    # every state left, nothing declared: nothing is inferable, so the kind lives on (the old rule took its last state)
    **{k: v for kind, s in _LAST.items() for k, v in _rows([kind], "final process series", f"[{s}]", "[]",
                                                            "every state left: lives on").items()},
    **{k: v for t in _TAKEN for k, v in {**_rows([f"the-job@left/{t}"], "final", "[dead]", "[]", "every state left: lives on"),
                                         **_rows([f"the-job@left/{t}"], "series", "[leased, dead]", "[]",
                                                 "every state left: lives on")}.items()},
}


def test_the_process_map_the_state_counts_and_routing_change_only_where_listed(tmp_path):
    """The parity test: the outputs as main gave them before these callers took finish_of (written by this test when
    missing, which then fails until it is committed), byte-identical but for ``CHANGED``, each of which did change."""
    got, said = parity_outputs(tmp_path)
    if not PARITY.exists():
        PARITY.write_text(json.dumps({"hashes": got, "said": said}, sort_keys=True, indent=1) + "\n")
        raise AssertionError(f"{PARITY} written: check it and commit it")
    fixture = json.loads(PARITY.read_text())
    before, was = fixture["hashes"], fixture["said"]
    assert sorted(got) == sorted(before) and len(got) > 400
    show = lambda xs: "[" + ", ".join(xs) + "]"           # noqa: E731
    at = lambda k: k.rsplit("/", 1)[0] + ("/series" if k.endswith("/series") else "/final")   # noqa: E731
    changed = sorted(k for k in got if got[k] != before[k])
    assert changed == sorted(CHANGED), "\n".join(f"{k}: {show(was[at(k)])} -> {show(said[at(k)])}" for k in changed)
    for k, why in CHANGED.items():                       # each change is what it says, before and after
        assert f"{show(was[at(k)])} -> {show(said[at(k)])}" == why.split(" (")[0], (k, was[at(k)], said[at(k)])
