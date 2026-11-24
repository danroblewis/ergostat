"""The backlog of gaps groomed and ranked (docs/roadmap/overnight/backlog.md): the solver, `takes: {order: rank}`, the
groomer with a stand-in AI and its gated proposal, closes, the intake's done rule, backlog.py on a fixture instance,
and the Items page's graph of the gaps' dependencies."""

from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path

import pytest

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


def test_a_dependency_in_a_starts_at_state_is_said_stacked_on():
    """merge-pipeline-stacks-turned-on: deps.py says a dependency in the relation's starts_at state (the gap is built on
    it) as `stacked on X (approved)`, not as waiting; one parked or building still waits. blocked_reason is a column the
    Items page shows already; the auxiliary gaps-stacked counts the gaps with stacked_on not merged or closed."""
    from ergostat.spec import read
    intake()                                                   # (dev/bin importable, as the factory runs it)
    deps, fac = module("deps"), module("fac")
    spec, _ = read(ROOT / "ergostat.yaml")
    assert spec.items["gap"].relations["depends_on"].starts_at == list(fac.STACKABLE)    # the one list, both sides
    assert "blocked_reason" in spec.items["gap"].show
    for state in fac.STACKABLE:
        gaps = {"gap/a": {"id": "gap/a", "state": state, "fields": {"branch": "a"}},
                "gap/b": {"id": "gap/b", "state": "ready", "fields": {"branch": "b", "depends_on": ["gap/a"]}}}
        got = deps.plan(gaps, {}, {})["gap/b"]
        assert (got["blocked_reason"], got["waits_on_parked"]) == (f"stacked on gap/a ({state})", False)
    for state, said in (("building", "waits on gap/a, which is building"), ("parked", "waits on gap/a, which is parked")):
        gaps["gap/a"]["state"] = state
        got = deps.plan(gaps, {}, {})["gap/b"]
        assert got["blocked_reason"].startswith(said) and got["waits_on_parked"] == (state == "parked")
    st = spec.auxiliaries["gaps-stacked"]
    assert st.unit == "gaps" and "deps.py stacked" in str(next(iter(st.sensors.values())).run)
    on = [{"gap": "gap/a", "sha": "0" * 40}]
    assert deps.stacked([{"state": s, "fields": {"stacked_on": v}} for s, v in (
        ("built", on), ("approved", on), ("fix", "unreadable"), ("merged", on), ("closed", on), ("ready", []),
        ("building", None))]) == 3


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

## Other things

- **Spans lines** (done, `churn`; owner, 2026-11-19: a loop's process that
  followed 2% held out was proposed, and the projections after a burst of 130 tickets were far off): a process is
  proposed only past a quality floor.
- **Done with a decision** (done, 5fa37de, `leasekill-only`; the owner decided 2026-11-18; SPEC §9.5
  *Fencing*): it.
- **Open right after** (open; found by
  a review): open.
- **Warm workers**: superseded by daemons (branch `daemons`, SPEC §9.7,
  `docs/RUNTIME.md`): long-lived processes.
- **Superseded across lines** (superseded
  by `daemons`): the rest.
- **A first slice across lines** (first slice done, 72da4e1, merged from `remote`; what is left below is open;
  `docs/proposals/remote-systems.md`, SPEC §4c): open.
- **Libraries** (parked on `libraries`, `docs/roadmap/overnight/libraries.md`, *Where it stopped*): templates
  and reference models.
- **Superseded by any edit, the title says**: open (not done) in its own words.
- **Superseded in a done title** (done, `churn` and `superseded-x`; owner, 2026-11-19): a version since changed.

## Done recently

- **Gone**: done.
"""


def test_the_done_rule_on_a_fixture():
    """The done rule on a fixture GAPS.md, never on the real one, whose entries change as gaps finish: each shape
    the real entries had (a parenthetical across lines, superseded, parked, open), and the simpler ones."""
    entries = intake().gaps_md(GAPS)
    says = {e["title"]: e["gaps_says"] for e in entries}
    assert says == {"Plain done": "done", "Done on a branch": "done", "Done comma on": "done", "Bold done": "done",
                    "Across lines": "done", "Old warm": "superseded", "First slice": "open", "Partly": "open",
                    "Computed": "open", "Done later in the clause": "open", "Parked one": "parked",
                    "Landing": "in progress", "No paren": "done", "Undone": "open",
                    "Spans lines": "done", "Done with a decision": "done", "Open right after": "open",
                    "Warm workers": "superseded", "Superseded across lines": "superseded",
                    "A first slice across lines": "open", "Libraries": "parked",
                    "Superseded by any edit, the title says": "open",
                    "Superseded in a done title": "done"}   # (not Gone: done recently)
    assert [e["line"] for e in entries][:2] == [5, 6]
    assert {e["section"] for e in entries} == {"Things", "Other things"}
    assert all(not e["head"].startswith("done") for e in entries if e["gaps_says"] != "done")


def on_records(f: Instance, records: dict[str, str]) -> None:
    """Main's dev/records made ``records`` ({name: text}, GAPS-head.md among them) and docs/GAPS.md removed, so what
    the intake reads can only be the records."""
    from tests.test_factory import NEW, commit_files, git
    git(f.checkout, "rm", "-q", "docs/GAPS.md")
    commit_files(f, {f"{NEW}/{name}.md": text for name, text in records.items()})


RECORDS = {"GAPS-head": "# Known gaps\n\n## Modelling\n\n@entry alpha-thing\n@entry beta\n@entry delta\n\n"
           "## Done recently\n\n@entry gamma\n",
           "alpha-thing": "## Entry\n\nsection: Modelling\n\n- **Alpha thing** (open; the first gap): what it lacks.\n"
           "  More of it.\n",
           "beta": "## Entry\n\nsection: Modelling\n\n- **Beta** (done, abc1234): landed.\n",
           "delta": "## Entry\n\nsection: Modelling\n\n- **Delta** (parked on `delta`, *Where it stopped*): stopped.\n",
           "gamma": "## Entry\n\nsection: Done recently\n\n- **Gamma**: done.\n"}


def test_two_records_of_one_title_are_reported_never_one_picked(tmp_path):
    """Two records whose entries' titles give one gap id (carry() makes `<branch>-2` for another of a title): the
    intake neither finds nor closes that gap (it never picks one), and says it as a dependency problem on its gap, or on
    stderr when no gap has it (lesson-3). Before the split the same holds for a GAPS.md a union merge left an entry
    twice in."""
    f = Instance(tmp_path)
    f.opened()
    two = {**RECORDS, "GAPS-head": RECORDS["GAPS-head"].replace("@entry delta", "@entry delta\n@entry epsilon"),
           "alpha-thing-2": "## Entry\n\nsection: Modelling\n\n- **Alpha thing** (done, abc1234): a second record.\n",
           "epsilon": "## Entry\n\nsection: Modelling\n\n- **Epsilon**: new.\n",
           "epsilon-2": "## Entry\n\nsection: Modelling\n\n- **Epsilon**: new, from the other side.\n"}
    on_records(f, two)
    said, lines = f.run("intake.py")
    assert "gap.closed" not in said and "gap/epsilon" not in {x["item"] for x in lines}   # neither closed nor found
    assert "intake: gap/epsilon: GAPS.md lists it 2 times" in f.stderr                    # no gap to say it on
    a = f.item("gap/alpha-thing")
    assert a["state"] == "open" and a["fields"]["dependency_problem"] is True
    assert "GAPS.md lists it 2 times, lines 5 (Modelling), 10 (Modelling)" in a["fields"]["dependency_problems"][0]
    g = Instance(tmp_path / "pre-split")                                    # (a GAPS.md with no records: the same)
    g.opened()
    from tests.test_factory import git
    md = g.checkout / "docs" / "GAPS.md"
    md.write_text(md.read_text().replace("- **Delta**", "- **Epsilon**: new.\n- **Epsilon**: again.\n- **Delta**"))
    git(g.checkout, "commit", "-qam", "a union merge left an entry twice")
    said, lines = g.run("intake.py")
    assert "gap/epsilon" not in {x["item"] for x in lines} and "gap/epsilon: GAPS.md lists it 2 times" in g.stderr


def test_one_copy_in_done_recently_is_counted_never_the_open_one_picked(tmp_path):
    """An entry listed in an open section and again in *Done recently* (two records of one title, one sectioned Done
    recently; before the split, a union merge's GAPS.md) is two entries of one gap: the open copy is neither found
    nor, when it says done, closes its gap; it is said, with each copy's line and section."""
    f = Instance(tmp_path)
    f.opened()
    again = {**RECORDS, "GAPS-head": RECORDS["GAPS-head"].replace("@entry delta", "@entry delta\n@entry gamma-2"),
             "gamma-2": "## Entry\n\nsection: Modelling\n\n- **Gamma** (open): listed again, open.\n"}
    on_records(f, again)
    said, lines = f.run("intake.py")
    assert "gap/gamma" not in {x["item"] for x in lines}                              # never found from the open copy
    said_gamma = [ln for ln in f.stderr.splitlines() if ln.startswith("intake: gap/gamma: GAPS.md lists it 2 times")]
    assert len(said_gamma) == 1 and re.search(r"lines \d+ \(Modelling\), \d+ \(Done recently\)", said_gamma[0])
    g = Instance(tmp_path / "pre-split")
    g.fold([{"event": "gap.requested", "item": "gap/zeta", "data": {"title": "Zeta", "source": "request",
                                                                     "branch": "zeta"}}], None)
    from tests.test_factory import git
    md = g.checkout / "docs" / "GAPS.md"
    md.write_text(md.read_text().replace("- **Delta**", "- **Zeta** (done, 5555555): the open copy.\n- **Delta**")
                  .replace("- **Gamma**: done.", "- **Gamma**: done.\n- **Zeta** (open): the done copy."))
    git(g.checkout, "commit", "-qam", "a union merge left an entry in a section and in Done recently")
    said, lines = g.run("intake.py")
    assert "gap.closed" not in said and g.item("gap/zeta")["state"] == "open"              # not closed by one copy
    problems = g.item("gap/zeta")["fields"]["dependency_problems"]
    assert any("GAPS.md lists it 2 times" in p and "(Done recently)" in p for p in problems), problems


def said_by_intake(f: Instance) -> list[dict]:
    """Every line the intake printed, its timestamps left out (each run has its own)."""
    _, lines = f.run("intake.py")
    return [{**x, "data": {k: v for k, v in x["data"].items() if not k.endswith("_at")}} for x in lines]


def test_intake_says_the_same_from_the_records_as_from_the_gaps_md_they_render(tmp_path):
    """On the pinned GAPS.md (tests/fixtures/gaps_md_pinned.md) split into records: the intake on main's records (no
    docs/GAPS.md there) says every gap found, closed and linked, with its sources, as it says on the GAPS.md the
    records render with no records beside it."""
    intake()
    gapsdoc, fac = module("gapsdoc"), module("fac")
    pinned = (Path(__file__).parent / "fixtures" / "gaps_md_pinned.md").read_text()
    s = gapsdoc.split(pinned)
    text, _ = gapsdoc.render(s["records"], s["head"])
    assert text == pinned                                           # (tests/test_gapsdoc.py: line for line)
    done = [e for e in intake().gaps_md(text) if e["gaps_says"] in ("done", "superseded")]
    assert done                                                     # (the pinned copy has entries to close)
    seeds = [{"event": "gap.requested", "item": e["id"], "data": {"title": e["title"], "source": "request",
                                                                  "branch": fac.slug(e["id"][4:], 32)}} for e in done]
    from tests.test_factory import commit_files
    said, stderr = [], []
    for where in ("rendered", "records"):
        f = Instance(tmp_path / where)
        f.fold(seeds, None)
        if where == "rendered":
            commit_files(f, {"docs/GAPS.md": text})
        else:
            on_records(f, {**s["records"], "GAPS-head": s["head"]})
        said.append(said_by_intake(f))
        stderr.append([ln for ln in f.stderr.splitlines() if "external-event-logs" in ln])
    assert said[0] == said[1]
    assert stderr[0] and stderr[0] == stderr[1]               # its two External event logs: said, never one picked
    events = {x["event"] for x in said[1]}
    assert {"gap.found", "gap.closed", "gap.dependencies"} <= events, events
    deps = [x["data"] for x in said[1] if x["event"] == "gap.dependencies"]
    assert any("GAPS.md:" in str(d["depends_on_sources"]) + str(d["dependency_problems"]) for d in deps)
    assert any(x["data"].get("source") == "gaps" for x in said[1] if x["event"] == "gap.found")


def test_an_entry_only_record_makes_no_gap_ready(tmp_path):
    """A record (dev/records/<branch>.md) is a definition only with a `## Definition of done` section: one holding
    its GAPS.md Entry alone, or with only a Where it stopped beside it, makes nothing ready; the section does."""
    from tests.test_factory import NEW, commit_files
    f = Instance(tmp_path)
    gid = f.opened()
    entry = RECORDS["alpha-thing"]
    for text in (entry, entry + "\n## Where it stopped\n\nNothing yet.\n"):
        commit_files(f, {f"{NEW}/alpha-thing.md": text})
        said, _ = f.run("intake.py")
        assert "gap.defined" not in said and f.item(gid)["state"] == "open"
    commit_files(f, {f"{NEW}/alpha-thing.md": "# alpha-thing\n\n## Definition of done\n\nIt works.\n\n" + entry})
    said, _ = f.run("intake.py")
    assert "gap.defined" in said and f.item(gid)["fields"]["definition"] == f"main:{NEW}/alpha-thing.md"


def test_an_unreadable_record_is_said_by_name_and_the_pass_goes_on(tmp_path):
    """A record whose Entry is malformed, or that is no text (not UTF-8), is drawn nowhere and said by name: on its
    gap as a dependency problem (the gap held), else on stderr. Never read as having no entry, and every other record
    still read."""
    f = Instance(tmp_path)
    f.opened()
    bad = {**RECORDS, "GAPS-head": RECORDS["GAPS-head"].replace("@entry delta", "@entry delta\n@entry epsilon"),
           "delta": "## Entry\n\nsection: Modelling\n\n- **Delta** (parked): stopped.\n\n  a blank line above.\n",
           "epsilon": "## Entry\n\nsection: Modelling\n\n- **Epsilon** (open): new.\n"}
    on_records(f, bad)
    from tests.test_factory import NEW, git
    (f.checkout / NEW / "zeta.md").write_bytes(b"## Entry\n\nsection: Modelling\n\n- **Zeta** \xff\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-qm", "a record that is no text")
    said, lines = f.run("intake.py")
    assert [x["item"] for x in lines if x["event"] == "gap.found"] == ["gap/epsilon"]   # the pass went on
    d = f.item("gap/delta")
    assert d["fields"]["dependency_problem"] is True
    assert "delta.md cannot be read (bullet line 2 is blank" in d["fields"]["dependency_problems"][0]
    assert d["fields"]["waits_on_parked"] is True                            # held: its dependencies are unknown
    assert "dev/records/zeta.md cannot be read (unreadable at main" in f.stderr   # no gap has it: said on stderr
    assert f.item("gap/alpha-thing")["fields"].get("dependency_problem") is not True


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


# ---- a link the coordinator refused is not proposed again

LINKS = {"links_add": [["gap/three", "gap/one", "it builds on one"], ["gap/three", "gap/two", "it needs two"]]}


def proposal(f: Instance) -> str:
    p = f.model / "run" / "backlog" / "links.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(LINKS))
    return str(p)


def test_a_refused_link_is_not_proposed_again(tmp_path):
    f = seeded(tmp_path)
    f.tool("backlog.py", "refuse-link", "three", "one", "--why", "its definition names no need of one")
    rec = [json.loads(x) for x in (f.model / "run" / "backlog" / "refused-links.jsonl").read_text().splitlines()]
    assert [(r["gap"], r["depends_on"], r["why"]) for r in rec] == [
        ("gap/three", "gap/one", "its definition names no need of one")]
    out = f.tool("backlog.py", "propose", proposal(f)).stdout
    assert "+ gap/three waits on gap/one" not in out and "+ gap/three waits on gap/two: it needs two" in out
    assert ("! refused: link gap/three -> gap/one: refused before by the coordinator "
            "(its definition names no need of one)") in out
    assert f.drain() == []                                              # propose writes nothing
    said, _ = f.run("backlog.py", argv=("groom",), FACTORY_STANDIN_GROOMER="```json\n" + json.dumps(LINKS) + "\n```")
    act = f.db()["acts"][-1]
    args = dict(a.split("=", 1) for a in act[act.index("--arg") + 1::2])
    assert args["summary"].startswith("1 links added")                  # the groomer's proposal drops it too
    f.tool("backlog.py", "apply", args["proposal"])
    f.drain()
    assert f.item("gap/three")["fields"]["depends_on"] == ["gap/two"]


def test_an_explicit_dep_add_clears_a_refused_link(tmp_path):
    f = seeded(tmp_path)
    f.tool("backlog.py", "refuse-link", "three", "one", "--why", "not needed")
    f.tool("backlog.py", "dep", "add", "three", "one")                  # the coordinator's own decision: it applies
    f.drain()
    assert f.item("gap/three")["fields"]["depends_on"] == ["gap/one"]
    assert json.loads((f.model / "run" / "backlog" / "refused-links.jsonl").read_text().splitlines()[-1])["cleared"]
    f.tool("backlog.py", "dep", "rm", "three", "one")
    f.drain()
    out = f.tool("backlog.py", "propose", proposal(f)).stdout
    assert "+ gap/three waits on gap/one: it builds on one" in out and "refused before" not in out


def test_an_unreadable_refusal_file_stops_nothing(tmp_path):
    f = seeded(tmp_path)
    f.tool("backlog.py", "refuse-link", "three", "one", "--why", "not needed")
    (f.model / "run" / "backlog" / "refused-links.jsonl").write_text('{"gap": "gap/three", "depends_on": "gap/one"\n')
    out = f.tool("backlog.py", "propose", proposal(f)).stdout
    assert "+ gap/three waits on gap/one: it builds on one" in out and "+ gap/three waits on gap/two" in out
    assert "! refused: refused-links.jsonl could not be read, so it refuses no link" in out


# ---- a split never abandons built work

CHECK = ("import backlog, fac; fac.cli(fac.config()); g = {x['id']: x for x in fac.items('gap')}\n"
         "p, ref = backlog.check(g, json.loads(sys.argv[1])); print(json.dumps([p['splits'], ref, backlog.diff(g, p, ref)]))")
ABANDON = "; its parts would start from main and abandon that work"


def split(*gids: str) -> dict:
    return {"splits": [{"gap": g, "into": [{"title": "A", "why": "x"}, {"title": "B", "why": "y"}]} for g in gids],
            "grooming": {"gap/three": {"value": 4, "size": "S", "risk": "low", "groomed_why": "the rest applies"}}}


def continuing(tmp_path) -> Instance:
    f = seeded(tmp_path)
    f.fold([{"event": "gap.requested", "item": "gap/one-continued",
             "data": {"title": "On", "source": "request", "continues": "one"}}], None)
    return f


def test_a_split_of_a_continued_gap_is_refused(tmp_path):
    f = continuing(tmp_path)
    kept, refused, md = f.py(CHECK, json.dumps(split("gap/one-continued")))
    assert kept == [] and refused == ["split gap/one-continued: it continues one" + ABANDON]
    assert "! refused: split gap/one-continued: it continues one" in md and "/ split" not in md


def test_a_split_of_a_gap_with_commits_is_refused(tmp_path):
    from tests.test_factory import git
    f = seeded(tmp_path)
    kept, refused, _ = f.py(CHECK, json.dumps(split("gap/two")))       # no branch in the drop yet: no work
    assert [s["gap"] for s in kept] == ["gap/two"] and refused == []
    drop = tmp_path / "live" / "drop.git"
    work = git(drop, "commit-tree", "main^{tree}", "-p", "main", "-m", "built work")
    git(drop, "update-ref", "refs/heads/factory/two", work)
    git(drop, "update-ref", "refs/heads/factory/three", git(drop, "rev-parse", "main"))   # a branch, nothing ahead
    kept, refused, _ = f.py(CHECK, json.dumps(split("gap/two", "gap/three")))
    assert [s["gap"] for s in kept] == ["gap/three"]
    assert refused == ["split gap/two: its branch has 1 commits main lacks" + ABANDON]
    (drop / "config").write_text("[[[ not a git config\n")             # the drop unreadable: work (lesson-3)
    kept, refused, _ = f.py(CHECK, json.dumps(split("gap/four")))
    assert kept == [] and refused[0].startswith("split gap/four: its branch could not be read")


def test_a_split_of_an_unbuilt_gap_still_applies(tmp_path):
    """One split refused, the rest of the proposal applied: the other split and the grooming."""
    f = continuing(tmp_path)
    p = f.model / "run" / "backlog" / "p.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(split("gap/one-continued", "gap/four")))
    r = f.tool("backlog.py", "apply", str(p))
    f.drain()
    assert "refused: split gap/one-continued: it continues one" + ABANDON in r.stdout
    assert f.item("gap/one-continued")["state"] == "open" and f.item("gap/four")["state"] == "split"
    assert f.item("gap/four-1")["fields"]["parent"] == ["gap/four"] and f.item("gap/four-2")["state"] == "open"
    assert f.item("gap/three")["fields"]["groomed_why"] == "the rest applies"


def test_the_halves_of_a_split_never_share_a_branch():
    """A long name cut to fit lost its -1 and -2, and both halves built on one branch from one definition."""
    text = (Path(__file__).resolve().parent.parent / "dev" / "bin" / "backlog.py").read_text()
    assert 'fac.slug(s["gap"].split("/", 1)[1], 29) + f"-{len(kids) + 1}"' in text


# ---- a split keeps what its parent waited on (dev/records/split-children-keep-parent-deps.md)


def split_four(f: Instance, *parts: dict):
    """gap/four split in two (``parts``: more for each part), applied as the approved action."""
    p = f.model / "run" / "backlog" / "split.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    into = [{"title": "A", "why": "x"}, {"title": "B", "why": "y"}]
    more = [*parts, {}, {}][:2]
    p.write_text(json.dumps({"splits": [{"gap": "gap/four", "into": [{**a, **b} for a, b in zip(into, more, strict=True)]}]}))
    r = f.tool("backlog.py", "apply", str(p))
    f.drain()
    return r


def waits(f: Instance, *gids: str) -> list[list[str]]:
    return [f.item(g)["fields"].get("depends_on") for g in gids]


def waiting_four(tmp_path) -> Instance:
    f = seeded(tmp_path)
    f.tool("backlog.py", "dep", "add", "four", "one")
    f.drain()
    return f


def test_a_split_first_part_waits_on_the_parents_unfinished_dependency(tmp_path):
    f = waiting_four(tmp_path)
    split_four(f)
    assert f.item("gap/four")["state"] == "split"
    assert waits(f, "gap/four-1", "gap/four-2") == [["gap/one"], ["gap/four-1"]]


def test_a_split_of_a_parent_whose_dependency_is_finished_gives_none(tmp_path):
    f = waiting_four(tmp_path)
    f.fold([{"event": "gap.merged", "item": "gap/one", "data": {}}], None)   # finished, still named by four
    assert f.item("gap/one")["state"] == "merged" and waits(f, "gap/four") == [["gap/one"]]
    split_four(f)
    assert waits(f, "gap/four-1", "gap/four-2") == [[], ["gap/four-1"]]


def test_a_split_parts_dependency_survives_intake_reading_its_definition(tmp_path):
    f = waiting_four(tmp_path)
    split_four(f)
    d = f.model / "run" / "defs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "four-1.md").write_text("# four-1: A\n\ndepends-on: [two]\n\n## Definition of done\n\nA.\n")
    f.run("intake.py")
    kid = f.item("gap/four-1")
    assert kid["state"] == "ready" and kid["fields"]["definition"] == "run/defs/four-1.md"
    assert kid["fields"]["depends_on"] == ["gap/one", "gap/two"]              # its definition's, and still the parent's
    assert "gap/one" in kid["fields"]["blocked_reason"]


def test_a_split_keeps_the_parts_named_dependencies_and_the_parents(tmp_path):
    f = waiting_four(tmp_path)
    split_four(f, {"depends_on": ["two"]}, {"depends_on": ["gap/three", "gap/four-1"]})
    assert waits(f, "gap/four-1", "gap/four-2") == [["gap/one", "gap/two"], ["gap/four-1", "gap/three"]]


def test_a_split_naming_a_dependency_it_cannot_keep_is_refused_whole(tmp_path):
    f = waiting_four(tmp_path)
    f.tool("backlog.py", "dep", "add", "three", "four")
    f.drain()
    for bad in ("nope", "four", "three", "gap/four-2"):           # no gap, the parent, one waiting on it, a later part
        r = split_four(f, {"depends_on": [bad]})
        assert f"refused: split gap/four: part 1 depends on {bad!r}" in r.stdout, r.stdout
        assert f.item("gap/four")["state"] == "open" and "gap/four-1" not in f.db()["items"]


# ---- deps reads the entries from main's dev/records/ (dev/records/merge-pipeline-gaps-deps-read-records.md)

PINNED = ROOT / "tests" / "fixtures" / "gaps_md_pinned.md"          # docs/GAPS.md as of a named commit (test_gapsdoc)
NOT_READ = "# Known gaps\n\n## Stale\n\n- **Stale** (open): after `nowhere`; never read where the records are.\n"
GITLINK = f"160000,{'1' * 40},"                                       # an entry git lists but cannot show


def bin_modules():
    intake()                                                         # (dev/bin on the path, as the factory runs it)
    import deps
    import gapsdoc
    return deps, gapsdoc


def records_main(tmp_path, records: dict[str, str], head: str | None, unshown: str = "") -> Path:
    """A repository whose main holds ``records`` (and ``head`` as GAPS-head.md) in dev/records/, an ``unshown``
    record git cannot show, and a docs/GAPS.md that is not their render: what deps reads is the records, never that."""
    from tests.test_factory import git
    repo = tmp_path / "main"
    (repo / "dev" / "records").mkdir(parents=True)
    (repo / "docs").mkdir()
    for name, text in {**records, **({"GAPS-head": head} if head is not None else {})}.items():
        (repo / "dev" / "records" / f"{name}.md").write_text(text)
    (repo / "docs" / "GAPS.md").write_text(NOT_READ)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    if unshown:
        git(repo, "update-index", "--add", "--cacheinfo", f"{GITLINK}dev/records/{unshown}.md")
    git(repo, "commit", "-qm", "main")
    return repo


def pinned_gaps(text: str) -> dict[str, dict]:
    """A gap for each entry of the rendered fixture, in the state its entry says (parked ones stopped, done ones
    closed), so the dependencies resolve, block and cycle as they would on the live record."""
    state = {"parked": "parked", "done": "closed", "superseded": "closed", "in progress": "building"}
    return {e["id"]: {"id": e["id"], "state": state.get(e["gaps_says"], "open"),
                      "fields": {"branch": e["id"].split("/", 1)[1][:32].rstrip("-"),
                                 "where_it_stopped": "stopped on the fixture"}}
            for e in intake().gaps_md(text)}


def test_deps_reads_the_same_dependencies_closes_and_blocked_reasons_from_the_records(tmp_path):
    deps, gapsdoc = bin_modules()
    s = gapsdoc.split(PINNED.read_text(encoding="utf-8"))
    rendered = gapsdoc.render(s["records"], s["head"])[0]
    repo = records_main(tmp_path, s["records"], s["head"])
    parsed, own, unreadable = deps.from_main(repo, "main", NOT_READ)
    assert unreadable == {} and (parsed, own) == deps.from_gaps(rendered)          # links, where from, own names
    assert "nowhere" not in str(parsed)                                             # docs/GAPS.md was not read
    closes = [(e["id"], e["gaps_says"]) for e in intake().gaps_md(gapsdoc.entries(repo, "main")[0])]
    assert closes == [(e["id"], e["gaps_says"]) for e in intake().gaps_md(rendered)]   # what the intake would close
    gaps = pinned_gaps(rendered)                   # (the fixture's links are `after `redesign``: a parked gap here)
    gaps["gap/redesign"] = {"id": "gap/redesign", "state": "parked", "fields": {"branch": "redesign"}}
    want, got = deps.plan(gaps, *deps.from_gaps(rendered)), deps.plan(gaps, parsed, own, unreadable=unreadable)
    assert got == want
    blocked = [g for g, w in got.items() if w["depends_on"] == ["gap/redesign"] and w["waits_on_parked"]]
    assert blocked and all("waits on gap/redesign, which is parked" in got[g]["blocked_reason"] for g in blocked)


def test_an_unreadable_record_is_said_by_name_and_its_gap_is_held_never_free(tmp_path, capsys):
    deps, gapsdoc = bin_modules()
    s = gapsdoc.split(PINNED.read_text(encoding="utf-8"))
    gaps = pinned_gaps(gapsdoc.render(s["records"], s["head"])[0])
    by_branch = {g["fields"]["branch"]: gid for gid, g in gaps.items()}
    free = deps.plan(gaps, *deps.from_main(records_main(tmp_path / "a", s["records"], s["head"]), "main", "")[:2])
    name = next(n for n in s["records"] if n in by_branch and not free[by_branch[n]]["blocked_reason"]
                and gaps[by_branch[n]]["state"] == "open")                          # a gap free while it can be read
    assert free[by_branch[name]]["waits_on_parked"] is False
    broken = {**s["records"], name: s["records"][name] + "a line that is not the bullet's\n"}
    repo = records_main(tmp_path / "b", broken, s["head"], unshown="no-such-gap")
    parsed, own, unreadable = deps.from_main(repo, "main", "")
    assert sorted(unreadable) == sorted([name, "no-such-gap"]) and "not indented" in unreadable[name]
    got = deps.plan(gaps, parsed, own, unreadable=unreadable)[by_branch[name]]
    assert got["waits_on_parked"] is True                                           # held: never taken
    assert f"dev/records/{name}.md cannot be read" in got["blocked_reason"] and got["problems"]
    assert "dev/records/no-such-gap.md cannot be read" in capsys.readouterr().err   # no gap's: said, on stderr
    said = dict(deps.changes(gaps, {by_branch[name]: got}))[by_branch[name]]
    assert said["dependency_problem"] is True and said["waits_on_parked"] is True
    gaps[by_branch[name]]["state"] = "merged"                                       # finished: nothing to hold
    assert deps.plan(gaps, parsed, own, unreadable=unreadable)[by_branch[name]]["waits_on_parked"] is False


def test_deps_reads_docs_gaps_md_only_before_the_split_and_never_past_an_unreadable_head(tmp_path, capsys):
    deps, _ = bin_modules()
    repo = records_main(tmp_path / "a", {}, None)                                   # no GAPS-head.md: before the split
    assert deps.from_main(repo, "main", NOT_READ) == (*deps.from_gaps(NOT_READ), {})
    assert "has no dev/records/GAPS-head.md" in capsys.readouterr().err
    repo = records_main(tmp_path / "b", {}, None, unshown="GAPS-head")
    with pytest.raises(ValueError, match="GAPS-head.md at main cannot be read"):
        deps.from_main(repo, "main", NOT_READ)
