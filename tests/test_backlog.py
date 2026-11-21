"""The backlog of gaps groomed and ranked (docs/roadmap/overnight/backlog.md): the solver, `takes: {order: rank}`, the
groomer with a stand-in AI and its gated proposal, closes, the intake's done rule, backlog.py on a fixture instance,
and the Items page's graph of the gaps' dependencies."""

from __future__ import annotations

import json
import shutil
import sys
import time

from ergostat import model as mdl
from ergostat import precedence as pr
from ergostat.store import Project
from tests.test_factory import BIN, ROOT, module
from tests.test_factory_knowledge import Instance

solve = module("solve")


def intake():
    """dev/bin/intake.py, its neighbours importable as the factory runs it."""
    if str(BIN) not in sys.path:
        sys.path.insert(0, str(BIN))
    return module("intake")


def rows(got: dict) -> list[str]:
    return [r["id"] for r in got["order"]]


# ---- the solver


def test_solver_orders_topologically_by_wsjf_with_a_bonus_for_unblocking():
    gaps = {"small": {"value": 4, "size": "S"},                      # WSJF 4
            "base": {"value": 2, "size": "S"},                       # WSJF 2, x1.5 for the two after it: 3
            "mid": {"value": 2, "size": "M", "depends_on": ["base"]},
            "top": {"value": 5, "size": "S", "depends_on": ["mid", "gap/merged-already"]},
            "big": {"value": 5, "size": "L", "risk": "high"},        # 5 / (8 x 1.5): 0.42
            "plain": {}}                                             # never groomed: value 3, size M, said
    got = solve.solve(gaps)
    assert got["refused"] is None and rows(got) == ["small", "base", "plain", "mid", "top", "big"]
    why = {r["id"]: r["why"] for r in got["order"]}
    assert why["base"] == "WSJF 2/S = 2.00, x1.5 for unblocking 2"
    assert "x1.5 risk" in why["big"] and "(value and size assumed)" in why["plain"]
    assert [r["rank"] for r in got["order"]] == [1, 2, 3, 4, 5, 6]   # (mid, 0.83, after plain, 1.0)
    assert solve.solve(gaps) == got                                    # deterministic
    tie = solve.solve({"b": {"rank": 1}, "a": {"rank": 2}, "c": {}})
    assert rows(tie) == ["b", "a", "c"]                                # equals: the earlier rank, then the id
    assert solve.points(6) == 1.5 and solve.points("l") == 8


def test_solver_holds_pins_and_pulls_their_dependencies_ahead():
    gaps = {"a": {"value": 5, "size": "S"}, "b": {"value": 4, "size": "S"}, "c": {"value": 1, "size": "L", "rank_pin": 1},
            "d": {"value": 1, "size": "S", "depends_on": ["e"], "rank_pin": 2}, "e": {"value": 1, "size": "L"}}
    got = solve.solve(gaps)
    assert rows(got) == ["c", "e", "d", "a", "b"]                       # e pulled ahead of d, pinned at 2
    why = {r["id"]: r["why"] for r in got["order"]}
    assert why["c"] == "pinned at 1" and "pulled ahead of d, pinned at 2" in why["e"]
    assert got["findings"] == ["d: pinned at 2, placed 3 (its dependencies come first)"]


def test_solver_refuses_a_cycle_with_a_finding():
    got = solve.solve({"a": {"depends_on": ["b"]}, "b": {"depends_on": ["c"]}, "c": {"depends_on": ["a"]}, "d": {}})
    assert got["order"] == [] and got["refused"] == "a -> b -> c -> a"
    assert got["findings"] == ["refused: a cycle, a -> b -> c -> a"]


# ---- the factory's model


def test_the_factory_takes_gaps_by_rank():
    from ergostat.spec import read
    spec, _ = read(ROOT / "ergostat.yaml")
    for name in ("implementor", "planner"):
        assert spec.blocks[name].takes.order == ["rank"] and spec.blocks[name].takes.unblocked
    assert "closed" in spec.items["gap"].states and spec.items["gap"].on["gap.closed"] == "closed"
    assert spec.actions["groom-backlog"].gate == "approve" and spec.blocks["groomer"].agent == "opus"


def test_the_items_graph_draws_gap_dependencies(tmp_path):
    """The Items page's Graph (precedence.build) on the factory's own model: a gap's depends_on is an edge."""
    shutil.copy(ROOT / "ergostat.yaml", tmp_path / "ergostat.yaml")
    (tmp_path / "dev").symlink_to(ROOT / "dev")
    m = mdl.load(tmp_path)
    assert m.spec is not None
    p = Project(m)
    now = time.time()
    p.events.add("gap.found", item="gap/a", data={"title": "A", "rank": 1}, at=now - 60)
    p.events.add("gap.found", item="gap/b", data={"title": "B", "rank": 2}, at=now - 50)
    p.events.add("gap.groomed", item="gap/b", data={"depends_on": {"add": ["gap/a"]}}, at=now - 40)
    g = pr.build(p.events, m.spec, ["gap"], now, now - 3600)
    assert [(e["from"], e["to"], e["rel"], e["kind"]) for e in g["edges"]] == [("gap/a", "gap/b", "depends_on", "precedence")]


# ---- the intake's done rule

GAPS = """\
# Known gaps

## Things

- **Plain done** (done, abc1234): landed.
- **Done on a branch** (done on `x`; SPEC §1): it.
- **Done comma on** (done, on `eta`; SPEC): it.
- **Bold done** (**done**, 1234567): it.
- **Across lines** (done, `churn`; owner, 2026-11-19: a long
  parenthetical (with a nested one) that goes on): it.
- **Old warm**: superseded by daemons (branch `daemons`): the rest.
- **First slice** (first slice done, 72da4e1; what is left is open): open.
- **Partly** (partly done, `churn`): open.
- **Computed** (computed measures done on `architecture`; design in
  `docs/x.md`): open.
- **Done later in the clause** (open; the first part done in 0f7f870): open.
- **Parked one** (parked on `y`, *Where it stopped*): stopped.
- **Landing** (landing, `modelling-core`): soon.
- **No paren**: done is a word here but not the head's start? It is: done.
- **Undone** (undone): open.

## Done recently

- **Gone**: done.
"""


def test_intake_done_rule_on_a_gaps_fixture():
    says = {e["title"]: e["gaps_says"] for e in intake().gaps_md(GAPS)}
    assert says == {"Plain done": "done", "Done on a branch": "done", "Done comma on": "done", "Bold done": "done",
                    "Across lines": "done", "Old warm": "superseded", "First slice": "open", "Partly": "open",
                    "Computed": "open", "Done later in the clause": "open", "Parked one": "parked",
                    "Landing": "in progress", "No paren": "done", "Undone": "open"}
    assert [e["line"] for e in intake().gaps_md(GAPS)][:2] == [5, 6]


def test_intake_done_rule_on_the_real_gaps_md():
    entries = intake().gaps_md((ROOT / "docs" / "GAPS.md").read_text())
    got = {e["title"]: e["gaps_says"] for e in entries}
    known = {"Identifying existing controllers": "done", "Built-in join": "done", "Craft notes in `check`": "done",
             "Poor identifications proposed, projections drawn as sure": "done",       # its parenthetical spans lines
             "Extreme-conditions tests and calibration per part of the model": "done",
             "A run whose lease expired is killed": "done", "Warm workers instead of a process per item": "superseded",
             "Remote systems": "open", "System architecture review": "open", "Proposals superseded by any edit": "open",
             "Relations, what is left": "open", "Shared libraries": "parked"}
    for title, want in known.items():                  # (each, while GAPS.md still lists it)
        if title in got:
            assert got[title] == want, title
    assert sum(1 for x in got.values() if x == "done") >= 5
    assert all(not e["head"].startswith("done") for e in entries if e["gaps_says"] != "done")


def test_intake_closes_gaps_marked_done(tmp_path):
    f = Instance(tmp_path)
    f.opened()
    (f.checkout / "docs" / "GAPS.md").write_text((f.checkout / "docs" / "GAPS.md").read_text().replace(
        "**Alpha thing** (open; the first gap)", "**Alpha thing** (done, abc1234; the first gap)").replace(
        "- **Delta**", "- **Epsilon** (**done**, 123): never taken.\n- **Delta**"))
    from tests.test_factory import git
    git(f.checkout, "commit", "-qam", "done")
    said, lines = f.run("intake.py")
    assert said == ["gap.closed"]                                   # Epsilon is not found: done already
    a = f.item("gap/alpha-thing")
    assert a["state"] == "closed" and a["fields"]["end"] == "done" and "GAPS.md:5 marks it done" in a["fields"][
        "closed_reason"]
    assert f.item("gap/delta")["state"] == "parked" or f.item("gap/delta")["state"] == "open"


# ---- backlog.py and the groomer


def seeded(tmp_path) -> Instance:
    f = Instance(tmp_path)
    f.opened()
    f.fold([{"event": "gap.requested", "item": f"gap/{n}", "data": {"title": n.title(), "source": "request",
                                                                     "branch": n, **d}}
            for n, d in [("one", {"value": 2, "size": "S"}), ("two", {"value": 5, "size": "S"}),
                         ("three", {"value": 3, "size": "M"}), ("four", {})]], None)
    return f


def test_backlog_commands_on_a_fixture_instance(tmp_path):
    f = seeded(tmp_path)
    out = f.tool("backlog.py", "propose").stdout
    assert out.splitlines()[0].startswith("  1 (now -) gap/two: WSJF 5/S")
    assert f.drain() == []                                              # propose writes nothing
    f.tool("backlog.py", "dep", "add", "two", "one")
    f.drain()
    assert f.item("gap/two")["fields"]["depends_on"] == ["gap/one"]
    ranks = {g: f.item(g)["fields"]["rank"] for g in ("gap/one", "gap/two", "gap/three")}
    assert ranks["gap/one"] < ranks["gap/two"]                          # it comes first now
    r = f.tool("backlog.py", "dep", "add", "one", "two", ok=False)     # a cycle: refused, nothing written
    assert "closes a cycle" in r.stderr and f.drain() == []
    f.tool("backlog.py", "pin", "four", "1")
    f.drain()
    assert f.item("gap/four")["fields"]["rank"] == 1 and f.item("gap/four")["fields"]["rank_pin"] == 1
    show = f.tool("backlog.py", "show").stdout.splitlines()
    assert show[1].split()[:2] == ["1*", "gap/four"] and "gap/one" in show[-1] or "gap/one" in "".join(show)
    f.tool("backlog.py", "dep", "rm", "two", "one")
    f.drain()
    assert f.item("gap/two")["fields"]["depends_on"] == [] and f.item("gap/two")["fields"]["depends_on_removed"] == [
        "gap/one"]
    f.tool("backlog.py", "pin", "four", "--off")
    f.drain()
    assert f.item("gap/four")["fields"]["rank_pin"] is None
    f.run("intake.py")                                                   # the intake keeps a link taken away
    assert "gap/one" not in (f.item("gap/two")["fields"].get("depends_on") or [])


def test_close_done_and_duplicate_repoints_dependents(tmp_path):
    f = seeded(tmp_path)
    f.tool("backlog.py", "dep", "add", "three", "two")
    f.drain()
    f.tool("backlog.py", "close", "two", "--duplicate-of", "one", "--why", "the same work")
    f.drain()
    two, three = f.item("gap/two"), f.item("gap/three")
    assert two["state"] == "closed" and two["fields"]["end"] == "duplicate" and two["fields"]["duplicates"] == ["gap/one"]
    assert three["fields"]["depends_on"] == ["gap/one"]                 # waits on what it duplicated instead
    f.tool("backlog.py", "close", "four", "--done", "--why", "landed in abc1234")
    f.drain()
    assert f.item("gap/four")["state"] == "closed" and f.item("gap/four")["fields"]["closed_reason"] == "landed in abc1234"
    f.fold([{"event": "gap.started", "item": "gap/three", "data": {}}], None)
    r = f.tool("backlog.py", "close", "three", "--done", "--why", "x", ok=False)   # started: not closed
    assert "close gap/three: building" in r.stderr and f.item("gap/three")["state"] == "building"
    assert "gap/two" not in f.tool("backlog.py", "show").stdout


PROPOSAL = {"links_add": [["gap/three", "gap/one", "it builds on one"], ["gap/one", "gap/three", "a cycle"],
                          ["gap/one", "gap/nope", "no gap"]],
            "grooming": {"gap/three": {"value": 5, "size": "S", "risk": "low", "groomed_why": "unblocks the rest"},
                         "gap/four": {"value": 1, "size": "L", "risk": "high", "why": "large"},
                         "gap/one": {"rank": 1, "rank_pin": 9, "value": 1}},
            "closes": [{"gap": "gap/two", "end": "duplicate", "of": "gap/one", "reason": "superseded by one"},
                       {"gap": "gap/delta", "end": "done", "reason": "parked: not closed"}],
            "splits": [{"gap": "gap/alpha-thing", "into": [{"title": "First half", "why": "x"},
                                                           {"title": "Second half", "why": "y"}]}]}


def test_groomer_proposes_and_apply_writes_the_events(tmp_path):
    f = seeded(tmp_path)
    f.tool("backlog.py", "pin", "four", "2")
    f.drain()
    f.fold([{"event": "gap.parked", "item": "gap/delta", "data": {}}], None)
    said, _ = f.run("backlog.py", argv=("groom",), FACTORY_STANDIN_GROOMER="```json\n" + json.dumps(PROPOSAL) + "\n```")
    assert said == []                                                   # nothing written: asked for, held
    act = f.db()["acts"][-1]
    assert act[:2] == ["act", "groom-backlog"]
    args = dict(a.split("=", 1) for a in act[act.index("--arg") + 1::2])
    assert args["summary"].startswith("1 links added, 0 removed, 1 closes, 1 splits, 3 groomed")
    md = (f.model / args["summary"].rsplit(": ", 1)[1]).read_text()
    assert "+ gap/three waits on gap/one: it builds on one" in md and "x close gap/two (duplicate of gap/one)" in md
    assert "! refused: link gap/one -> gap/three: closes a cycle" in md and "close gap/delta: parked" in md
    assert "/ split gap/alpha-thing into 2: First half; Second half" in md and "pinned at 2" in md
    said, _ = f.run("backlog.py", argv=("groom",), FACTORY_STANDIN_GROOMER="```json\n{}\n```")
    assert len(f.db()["acts"]) == 1 and "waits for the coordinator" in f.stderr     # one proposal at a time
    f.tool("backlog.py", "apply", args["proposal"])                     # the approved action
    f.drain()
    three, one = f.item("gap/three"), f.item("gap/one")
    assert three["fields"]["depends_on"] == ["gap/one"] and three["fields"]["value"] == 5
    assert three["fields"]["groomed_by"] == "groomer" and three["fields"]["groomed_why"] == "unblocks the rest"
    assert "rank_pin" not in one["fields"] and one["fields"]["value"] == 1   # its value, never its rank or pin
    assert f.item("gap/two")["state"] == "closed" and f.item("gap/delta")["state"] == "parked"
    assert f.item("gap/four")["fields"]["rank"] == 2                    # its pin held
    assert f.item("gap/alpha-thing")["state"] == "split"
    kids = [f.item("gap/alpha-thing-1"), f.item("gap/alpha-thing-2")]
    assert kids[1]["fields"]["depends_on"] == ["gap/alpha-thing-1"] and kids[0]["fields"]["parent"] == ["gap/alpha-thing"]
    ranks = sorted((g["fields"]["rank"], g["id"]) for g in f.db()["items"].values() if g["fields"].get("rank")
                   and g["state"] in ("open", "ready"))
    assert [r for r, _ in ranks] == list(range(1, len(ranks) + 1))     # 1..N over the backlog
    assert not (f.model / "run" / "backlog" / "pending.json").exists()
    f.run("backlog.py", argv=("groom",))                                # the split's sub-gaps are new: groomed
    assert len(f.db()["acts"]) == 2
    (f.model / "run" / "backlog" / "pending.json").unlink()
    f.fold([{"event": "gap.groomed", "item": k, "data": {"value": 3, "groomed_at": time.time()}}
            for k in ("gap/alpha-thing-1", "gap/alpha-thing-2")], None)
    f.run("backlog.py", argv=("groom",))                                # nothing new since: no session
    assert len(f.db()["acts"]) == 2 and "nothing new" in f.stderr


def test_status_prints_the_top_of_the_backlog(tmp_path):
    f = seeded(tmp_path)
    f.tool("backlog.py", "pin", "three", "1")
    f.drain()
    out = f.tool("status.py").stdout
    assert "Backlog (backlog.py show)" in out and out.split("Backlog")[1].splitlines()[1].split()[:2] == ["1*", "gap/three"]



def test_a_duplicate_close_that_would_close_a_cycle_is_refused_and_nothing_is_written(tmp_path):
    """b waits on d, d waits on a; a closed as a duplicate of b would leave d waiting on b: b -> d -> b."""
    f = seeded(tmp_path)
    f.fold([{"event": "gap.requested", "item": f"gap/{n}", "data": {"title": n, "source": "request", "branch": n}}
            for n in ("a", "b", "d")], None)
    f.tool("backlog.py", "dep", "add", "b", "d")
    f.tool("backlog.py", "dep", "add", "d", "a")
    f.drain()
    r = f.tool("backlog.py", "close", "a", "--duplicate-of", "b", "--why", "same", ok=False)
    assert "its dependents would close a cycle (gap/b -> gap/d)" in r.stderr
    assert f.drain() == [] and f.item("gap/a")["state"] == "open"         # nothing written
    gaps = f.py("import backlog, fac; fac.cli(fac.config()); g = {x['id']: x for x in fac.items('gap')}\n"
                "p, ref = backlog.check(g, json.loads(sys.argv[1])); print(json.dumps([backlog.diff(g, p, ref), ref]))",
                json.dumps({"closes": [{"gap": "gap/a", "end": "duplicate", "of": "gap/one", "reason": "x"}],
                            "grooming": {"gap/b": {"value": 5}}}))
    assert "~ gap/d waits on gap/one instead of gap/a" in gaps[0] and gaps[1] == []   # the re-pointing shown
