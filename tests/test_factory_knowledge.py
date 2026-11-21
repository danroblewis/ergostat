"""The factory's knowledge and planning subsystem (docs/roadmap/overnight/knowledge.md): briefs that carry the
knowledge within a budget, the module map, the planner and its plan review, the researcher, the librarian and the
coordinator's tools, on the fixture of tests/test_factory.py with the free stand-ins."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_factory import BIN, FAKE, Factory, git

FAKE_MORE = FAKE.replace('if args[0] == "item":', 'if args[0] == "item" and "--kind" in args:').replace(
    '''elif args[0] == "lease":''', '''elif args[0] == "event" and args[1] == "--add":
    db.setdefault("added", []).append({"event": args[2], "item": args[args.index("--item") + 1],
                                       "data": json.loads(args[args.index("--data") + 1])})
    rec.write_text(json.dumps(db))
elif args[0] == "item" and "--kind" not in args:
    if args[1] not in db["items"]:
        sys.exit(f"no item {args[1]}")
    print(json.dumps(db["items"][args[1]]))
elif args[0] == "lease":''')

PLAN = """<definition branch="{b}">
# {b}: a plan

depends-on: []

## Definition of done

It works.

## Files to touch

- `app.py`, and `fresh.py` (new)

## Risks

- lesson-3: a ledger it cannot read.

## Acceptance tests

- `tests/test_x.py::test_unreadable_ledger_refuses`: fails if it fails open.

## Size budget

100 net lines.
</definition>"""


class Instance(Factory):
    """The factory fixture with the knowledge roles' settings, and a fake ergostat that also records `event --add`."""

    def __init__(self, tmp, **kw):
        super().__init__(tmp, **kw)
        self.config.write_text(self.config.read_text().replace("[ai]\n", "[ai]\n" + "".join(
            f'{r}_model = "opus"\n{r}_session_usd = 1.0\n' for r in ("planner", "plan_reviewer", "researcher",
                                                                     "librarian", "groomer"))))
        self.config.write_text(self.config.read_text() + "[knowledge]\nlibrarian = true\n[plan]\nreview = \"all\"\n")
        self.fake.write_text(FAKE_MORE)

    def drain(self) -> list[str]:
        """What the tools recorded with `event --add`, folded into the record."""
        db = self.db()
        added = db.pop("added", [])
        self.record.write_text(json.dumps(db))
        return self.fold(added, None)

    def tool(self, program: str, *argv: str, ok: bool = True) -> subprocess.CompletedProcess:
        r = subprocess.run([sys.executable, str(BIN / program), *argv], cwd=self.model, env=self.env,
                           capture_output=True, text=True, timeout=120)
        assert (r.returncode == 0) == ok, r.stderr
        return r

    def py(self, code: str, *argv: str):
        """Python with dev/bin on its path, in the instance's folder: what it prints, as JSON."""
        r = subprocess.run([sys.executable, "-c", f"import sys, json; sys.path[:0] = [{str(BIN)!r}]\n{code}", *argv],
                           cwd=self.model, env=self.env, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])

    def opened(self) -> str:
        self.run("intake.py")
        assert self.item("gap/alpha-thing")["state"] == "open"
        return "gap/alpha-thing"

    def define(self, text: str = "# alpha thing\n\n## Definition of done\n\nIt works.\n\n## Size budget\n\n600 net lines.\n"):
        d = self.model / "run" / "defs"
        d.mkdir(parents=True, exist_ok=True)
        (d / "alpha-thing.md").write_text(text)
        self.run("intake.py")


BLOCK = ("import fac, knowledge; cfg = fac.config(); cfg['knowledge'] = json.loads(sys.argv[1]); "
         "g = json.loads(fac.ergostat('item', sys.argv[2], '--json').stdout)\n"
         "text, got = knowledge.block(cfg, sys.argv[3], g, sys.argv[4]); print(json.dumps({**got, 'text': text}))")


def test_knowledge_files_parse():
    sys.path[:0] = [str(BIN)]
    try:
        import knowledge
        es = knowledge.entries()
    finally:
        sys.path.remove(str(BIN))
    ids = [e["id"] for e in es]
    assert len(ids) == len(set(ids)) and all(e["text"] for e in es)
    assert {"rules-process", "rules-machine", "rules-code", "rules-outside"} <= set(ids)
    assert [i for i in ids if i.startswith("lesson-")] == [f"lesson-{n}" for n in range(1, 14)]
    decisions = [e for e in es if e["id"].startswith("decision-")]
    assert len(decisions) == 9 and all(e["areas"] for e in decisions)       # each says the areas it is about


def test_brief_carries_knowledge_within_budget(tmp_path):
    f = Instance(tmp_path)
    f.define("# alpha thing\n\nThe Process diagram, in `dev/bin/brief.py`.\n\n## Definition of done\n\nIt works.\n")
    said, _ = f.run("implement.py", "gap/alpha-thing")
    assert said == ["gap.started", "gap.built"]
    ctx = f.item("gap/alpha-thing")["fields"]["contexts"][0]
    assert {"rules-process", "lesson-1", "lesson-11", "decision-one-model-three-drawings"} <= set(ctx["knowledge"])
    assert "decision-daemons-over-a-process-per-item" not in ctx["knowledge"]      # its area is not named
    assert any(k.startswith("modules@") for k in ctx["knowledge"]) and ctx["knowledge_chars"] <= 24000
    brief = (f.model / ctx["brief"][5:]).read_text()
    assert "### lesson-3: Failing open" in brief and "**Check:**" in brief and "## The house rules" in brief
    must = f.py(BLOCK, json.dumps({"chars": 1}), "gap/alpha-thing", "implementor", "diagram")["knowledge_chars"]
    small = f.py(BLOCK, json.dumps({"chars": must + 400}), "gap/alpha-thing", "implementor", "a diagram")
    assert small["knowledge_chars"] <= must + 400                                # within the budget
    assert "decision-one-model-three-drawings" in small["knowledge"]             # the higher priority fits
    assert [k for k in small["knowledge_dropped"] if k.startswith("modules@")]   # the lower is dropped, and said
    lean = f.py(BLOCK, json.dumps({}), "gap/alpha-thing", "plan_reviewer", "a diagram")
    assert lean["knowledge"] == [f"lesson-{n}" for n in range(1, 14)]            # the plan review: the lessons only


def test_module_map_from_main_cached_by_sha(tmp_path):
    f = Instance(tmp_path)
    (f.checkout / "ergostat" / "spec").mkdir(parents=True)
    (f.checkout / "ergostat" / "spec" / "thing.py").write_text('"""The thing: it reads. More here."""\n')
    (f.checkout / "ergostat" / "bare.py").write_text("x = 1\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "pkg")
    code = "import fac, knowledge; sha, m = knowledge.module_map(fac.config()); print(json.dumps([sha, m]))"
    sha, mods = f.py(code)
    assert mods == {"ergostat": [["bare.py", "(no docstring)"]], "ergostat/spec": [["thing.py", "The thing: it reads."]]}
    cache = f.model / "run" / "modules" / f"{sha}.json"
    cache.write_text(json.dumps({"cached": []}))
    assert f.py(code) == [sha, {"cached": []}]                                   # read from its cache
    (f.checkout / "ergostat" / "new.py").write_text('"""New."""\n')
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "merge")
    sha2, mods2 = f.py(code)                                                     # a merge: a new map
    assert sha2 != sha and ["new.py", "New."] in mods2["ergostat"]
    near = f.py("import knowledge; print(json.dumps(knowledge.render_map(json.loads(sys.argv[1]), "
                "['ergostat/spec/thing.py'], 10000)))", json.dumps(mods2))
    assert "thing.py: The thing: it reads." in near and "- `ergostat/`: bare.py, new.py" in near


def test_related_gaps_and_past_findings(tmp_path):
    f = Instance(tmp_path)
    f.opened()
    f.fold([{"event": "gap.parked", "item": "gap/delta", "data": {"where_it_stopped": "Stopped at the lock order."}},
            {"event": "gap.measured", "item": "gap/alpha-thing", "data": {"depends_on": ["gap/delta"]}},
            {"event": "review.written", "item": "review/delta-1", "data": {
                "gap": "gap/delta", "verdict": "fix", "written_at": 1.0,
                "blocking": ["dev/bin/brief.py:12: reads the pool, then writes it, without the lock"]}},
            {"event": "review.written", "item": "review/other-1", "data": {
                "gap": "gap/other", "verdict": "fix", "blocking": ["ergostat/elsewhere.py:1: unrelated"]}}], None)
    got = f.py(BLOCK, json.dumps({}), "gap/alpha-thing", "implementor", "changes `dev/bin/brief.py`")
    assert "gap/delta" in got["knowledge"] and "Stopped at the lock order." in got["text"]
    assert "review/delta-1" in got["knowledge"] and "review/other-1" not in got["knowledge"]
    assert "reads the pool, then writes it" in got["text"]
    f.fold([{"event": "gap.requested", "item": "gap/sib", "data": {"parent": ["gap/p"], "title": "Sibling"}},
            {"event": "gap.measured", "item": "gap/alpha-thing", "data": {"parent": ["gap/p"]}}], None)
    got = f.py(BLOCK, json.dumps({}), "gap/alpha-thing", "implementor", "x")
    assert "gap/sib" in got["knowledge"]                          # a sibling of its split (a relation: a list of ids)


def test_planner_writes_plan_and_review_makes_ready(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    said, _ = f.run("plan.py", gid, FACTORY_STANDIN_PLANNER=PLAN.format(b="alpha-thing"))
    assert said == ["gap.defined"]                             # lint-clean: the definition at once, never a review gate
    gap = f.item(gid)
    assert gap["state"] == "ready" and gap["fields"]["defined_by"] == "plan" and gap["fields"]["risks"] == ["lesson-3"]
    assert gap["fields"]["replanned"] is False and gap["fields"]["plan_review"] == "wanted"
    assert gap["fields"]["contexts"][0]["role"] == "planner" and "lesson-3" in gap["fields"]["contexts"][0]["knowledge"]
    plan = (f.model / "run" / "defs" / "alpha-thing.md").read_text()
    assert plan.startswith("# alpha-thing: a plan") and "test_unreadable_ledger_refuses" in plan
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"]
    assert "test_unreadable_ledger_refuses" in git(tmp_path / "live" / "drop.git", "show",
                                                   "factory/alpha-thing:docs/roadmap/overnight/alpha-thing.md")


def test_a_written_definition_skips_the_planner(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    (f.model / "run" / "defs").mkdir(parents=True, exist_ok=True)
    (f.model / "run" / "defs" / "alpha-thing.md").write_text("# mine\n")
    said, _ = f.run("plan.py", gid)
    assert said == ["gap.defined"] and f.item(gid)["fields"]["defined_by"] == "coordinator"
    assert not (f.model / "run" / "plans").exists()           # no session, nothing spent


def test_plan_review_is_advice_never_a_gate(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    f.run("plan.py", gid)
    verdict = ('```json\n{"verdict": "fix", "blocking": ["[design] the step condition cancels severity out"], '
               '"non_blocking": ["[lesson-9] test the empty ledger", "untagged"]}\n```')
    said, _ = f.run("planreview.py", FACTORY_STANDIN_PLAN_REVIEWER=verdict)
    assert said == ["gap.measured", "review.written", "gap.measured"]
    gap = f.item(gid)
    assert gap["state"] == "ready" and gap["fields"]["plan_review"] == "done" and gap["fields"]["plan_flagged"] is True
    review = f.item("review/alpha-thing-plan")["fields"]        # each finding with its class, for the knowledge loop
    assert review["stage"] == "plan" and review["round"] == 0 and review["classes"] == ["design", "lesson-9"]
    assert [x["class"] for x in review["findings"]] == ["design", "lesson-9", "none"]
    text = (f.model / "run" / "defs" / "alpha-thing.md").read_text()
    assert text.endswith("## Notes from the plan review (answer each)\n\n- the step condition cancels severity out\n"
                         "- test the empty ledger\n- untagged\n")
    assert f.run("planreview.py")[0] == []                     # read once
    assert "acts" not in f.db()


def test_a_park_from_the_plan_review_is_only_asked(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    f.run("plan.py", gid)
    said, _ = f.run("planreview.py", FACTORY_STANDIN_VERDICT="park")
    assert "gap.parked" not in said and f.item(gid)["state"] == "ready"
    act = f.db()["acts"][0]
    assert act[1] == "park-gap" and f"gap={gid}" in act and "why=stopped by the stand-in" in act
    r = subprocess.run([sys.executable, str(BIN / "planreview.py"), "park", gid, "a", "duplicate"], cwd=f.model,
                       env=f.env, capture_output=True, text=True, timeout=120)             # approved: the action runs
    assert r.returncode == 0, r.stderr
    f.drain()
    assert f.item(gid)["state"] == "parked" and "a duplicate" in f.item(gid)["fields"]["where_it_stopped"]


@pytest.mark.parametrize("mode", ["all", "off", "sample"])
def test_the_plan_review_setting_marks_plans(mode, tmp_path):
    f = Instance(tmp_path)
    f.config.write_text(f.config.read_text().replace('review = "all"', f'review = "{mode}"\nsample_every = 3'))
    marked = f.py("import fac, plan; cfg = fac.config(); "
                  "print(json.dumps([plan.review_wanted(cfg, f'gap/g{i}') for i in range(30)]))")
    assert sum(marked) == {"all": 30, "off": 0}.get(mode, sum(marked)) and (mode != "sample" or 4 <= sum(marked) <= 16)


def test_planner_splits_into_sub_gaps(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    split = (PLAN.format(b="alpha-one").replace('branch="alpha-one"', 'branch="alpha-one" title="One"')
             + PLAN.format(b="alpha-two").replace("depends-on: []", "depends-on: [alpha-one]"))
    said, _ = f.run("plan.py", gid, FACTORY_STANDIN_PLANNER=split)
    assert said == ["gap.requested", "gap.defined", "gap.requested", "gap.defined", "gap.split"]
    assert f.item(gid)["state"] == "split" and f.item(gid)["fields"]["children"] == ["gap/alpha-one", "gap/alpha-two"]
    one, two = f.item("gap/alpha-one"), f.item("gap/alpha-two")
    assert one["state"] == two["state"] == "ready" and one["fields"]["title"] == "One"
    assert two["fields"]["parent"] == [gid] and two["fields"]["depends_on"] == ["gap/alpha-one"]
    assert one["fields"]["source"] == "plan" and one["fields"]["defined_by"] == "plan-split"
    assert (f.model / "run" / "defs" / "alpha-two.md").is_file()
    # a split naming a gap that exists (its id reused would merge old fields in) is refused, and sent back
    said, _ = f.run("plan.py", "gap/delta", FACTORY_STANDIN_PLANNER=PLAN.format(b="alpha-one") + PLAN.format(b="new"))
    assert said == ["gap.plan-sent-back"] and "'alpha-one'" in f.item("gap/delta")["fields"]["plan_findings"][0]
    assert f.item("gap/alpha-one")["fields"]["parent"] == [gid]
    f.fold([{"event": "gap.found", "item": "gap/a-long-title", "data": {"branch": "short"}}], None)
    said, _ = f.run("plan.py", "gap/delta", FACTORY_STANDIN_PLANNER=PLAN.format(b="short") + PLAN.format(b="new"))
    delta = f.item("gap/delta")["fields"]                       # (the lint's)
    assert said == ["gap.plan-sent-back"] and "'short'" in json.dumps(delta["plan_findings"])
    assert delta["plan_lint_failures"] == 2
    plan = f.py("import plan; print(json.dumps([plan.problems([(n, '', b) for n, b in json.loads(sys.argv[1])], "
                "'big', {'gap/old'})]))", json.dumps(
                    [[f"p{i}", ""] for i in range(7)] + [["Bad_Name", ""], ["late", "depends-on: [later]"],
                                                         ["later", "depends-on: [old, p1]"]]))[0]
    assert "a split into 10 sub-gaps: at most 6" in plan
    assert any("'Bad_Name'" in p for p in plan) and any("'late' depends on gap/later" in p for p in plan)
    assert not any("'later' depends" in p for p in plan)       # an earlier sub-gap, or a gap: fine


def test_researcher_answers(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    said, lines = f.run("plan.py", gid, FACTORY_STANDIN_PLANNER="<research>How does the queue\n decide?</research>")
    assert said == ["research.asked", "gap.measured"] and any("nack" in x for x in lines)
    rid = f.item(gid)["fields"]["research"][0]
    assert f.item(rid)["fields"]["question"] == "How does the queue decide?" and f.item(gid)["state"] == "open"
    said, lines = f.run("plan.py", gid)
    assert said == ["gap.measured"] and "waits for its research" in json.dumps(lines)   # no plan before its answer
    said, _ = f.run("research.py", rid)
    assert said == ["research.answered"]
    r = f.item(rid)
    assert r["state"] == "answered" and r["fields"]["summary"] == "The stand-in's answer."
    assert (f.model / r["fields"]["report"]).read_text().startswith("# The stand-in's answer")
    assert r["fields"]["contexts"][0]["role"] == "researcher" and r["fields"]["sources"] == ["none"]
    said, _ = f.run("plan.py", gid)
    assert said == ["gap.defined"]
    brief = (f.model / f.item(gid)["fields"]["contexts"][-1]["brief"][5:]).read_text()
    assert "Nothing was read." in brief                        # the report went into the planner's brief


LIB = "```json\n{}\n```"


def librarian(f: Instance, rid: str, blocking: list[str], rows: list[dict]) -> list[str]:
    r = subprocess.run([sys.executable, str(BIN / "librarian.py")], cwd=f.model, capture_output=True, text=True,
                       input=json.dumps({"trigger": "event", "event": {"item": rid, "data": {"blocking": blocking}}}),
                       env={**f.env, "FACTORY_STANDIN_LIBRARIAN": LIB.format(json.dumps(rows))}, timeout=120)
    assert r.returncode == 0, r.stderr
    return f.fold([json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")], None)


def test_librarian_proposes_from_a_finding(tmp_path):
    f = Instance(tmp_path)
    shape = {"finding": 1, "class": "lesson-1", "shape": "a pool slot taken after its check", "new_shape": True}
    said = librarian(f, "review/a-1", ["gate 1: not first", "dev/bin/x.py:3: checks the pool then takes a slot"],
                     [shape])
    assert said == ["lesson.proposed", "review.measured"]
    seen = [i for i in f.db()["items"].values() if i["kind"] == "lesson"][0]
    assert seen["id"].startswith("lesson/seen-lesson-1-") and seen["state"] == "proposed"
    assert seen["fields"]["text"] == "a pool slot taken after its check" and seen["fields"]["findings"] == [
        "dev/bin/x.py:3: checks the pool then takes a slot"]           # the gate's own finding is not classified
    assert f.db()["acts"][-1][:2] == ["act", "knowledge-change"] and f.item("review/a-1")["fields"]["classes"] == [
        "lesson-1"]
    assert librarian(f, "review/a-2", ["again"], [shape]) == ["review.measured"]          # proposed once
    assert librarian(f, "review/a-3", ["x"], [{**shape, "new_shape": False}]) == ["review.measured"]
    new = {"finding": 1, "class": "new", "name": "Stale cache", "shape": "a cache read after the merge"}
    assert librarian(f, "review/b-1", ["cached"], [new]) == ["lesson.seen", "review.measured"]   # once: counted
    assert f.item("lesson/new-stale-cache")["state"] == "seen" and len(f.db()["acts"]) == 1
    assert librarian(f, "review/b-1", ["cached"], [new]) == ["review.measured"]           # the same review: not twice
    assert librarian(f, "review/c-1", ["cached"], [new]) == ["lesson.seen", "lesson.proposed", "review.measured"]
    assert f.item("lesson/new-stale-cache")["state"] == "proposed" and len(f.db()["acts"]) == 2   # found twice
    assert f.item("lesson/new-stale-cache")["fields"]["times"] == 2


def test_cli_tools_on_a_fixture_instance(tmp_path):
    f = Instance(tmp_path)
    f.opened()
    rid = f.tool("ask.py", "How", "does the queue decide?").stdout.strip()
    assert f.drain() == ["research.asked"] and f.item(rid)["fields"]["question"] == "How does the queue decide?"
    (tmp_path / "def.md").write_text("# my change\n")
    f.tool("request.py", "My change", "--depends-on", "alpha-thing", "--definition", str(tmp_path / "def.md"))
    f.tool("request.py", "Other", "--depends-on", "nothing-here", ok=False)
    f.tool("request.py", "Bad", "--branch", "../up", ok=False)
    assert f.drain() == ["gap.requested"]
    mine = f.item("gap/my-change")["fields"]
    assert mine["depends_on"] == ["gap/alpha-thing"] and mine["definition"] == "run/defs/my-change.md"
    f.tool("lesson.py", "add", "Stale cache", "--check", "clear it on merge", "--seen", "a map read after a merge")
    assert f.drain() == ["gap.requested"]
    text = (f.model / "run" / "defs" / "knowledge-stale-cache.md").read_text()
    assert "## 14. Stale cache\nSeen as: a map read after a merge.\n**Check:** clear it on merge" in text
    assert "## Size budget" in text and "## Acceptance tests" in text
    f.tool("lesson.py", "add", "Stale cache", "--check", "again", ok=False)        # asked for already
    f.fold([{"event": "lesson.proposed", "item": "lesson/seen-lesson-1-abc", "data": {
        "kind": "seen", "lesson": "lesson-1", "text": "a slot taken after its check", "findings": ["x.py:1: it"]}}], None)
    f.tool("lesson.py", "request", "lesson/seen-lesson-1-abc")
    assert f.drain() == ["gap.requested", "lesson.requested"]
    assert f.item("lesson/seen-lesson-1-abc")["state"] == "requested"
    f.fold([{"event": "lesson.seen", "item": "lesson/new-once", "data": {"kind": "entry", "name": "Once"}}], None)
    f.tool("lesson.py", "request", "lesson/new-once", ok=False)                    # only a proposal is requested
    assert not (f.model / "run" / "defs" / "knowledge-new-once.md").exists()
    f.tool("lesson.py", "retire", "9", "carried for a month to no effect")
    assert f.drain() == ["gap.requested", "lesson.retired"]
    f.fold([{"event": "gap.parked", "item": "gap/delta", "data": {"where_it_stopped": "Stopped: the lock order."}},
            {"event": "gap.started", "item": "gap/alpha-thing", "data": {"lease": {"taken": 1.0}}}], None)
    out = f.tool("status.py").stdout
    assert "In flight (1)" in out and "gap/alpha-thing" in out
    assert "gap/my-change" in out and "waits on gap/alpha-thing (building)" in out
    assert "Stopped: the lock order." in out and "Spend today $0.00" in out and "no value yet" in out
    assert rid in out


@pytest.mark.parametrize("role", ["planner", "plan_reviewer", "researcher", "librarian"])
def test_new_roles_read_only_in_their_containers(role, tmp_path):
    sys.path[:0] = [str(BIN)]
    try:
        import agents
        cfg = {"ai": {f"{role}_model": "opus", f"{role}_session_usd": 1.0}, "agents": {}}
        args = agents.run_args(cfg, role, tmp_path, "n")
    finally:
        sys.path.remove(str(BIN))
    assert f"{tmp_path}:/work:ro" in args
    allowed = args[args.index("--allowedTools") + 1].split(",")
    assert not [t for t in allowed if t in ("Edit", "Write") or "commit" in t]
    assert ("WebSearch" in allowed) == (role == "researcher")


def test_the_knowledge_model_loads():
    from ergostat.spec import read
    from tests.test_factory import ROOT
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    assert {"research", "lesson"} <= set(spec.items) and "knowledge-change" in spec.actions
    assert {"planned", "replan", "split"} <= set(spec.items["gap"].states)
    for name in ("planner", "researcher"):
        assert spec.blocks[name].pool == 1
    assert spec.blocks["planner"].takes.at == ["open", "replan"] and spec.blocks["plan-review"].takes is None
    assert "ready" in spec.blocks["planner"].takes.to and "planned" not in spec.blocks["planner"].takes.to
    assert {"knowledge-entries", "gaps-planned", "lessons-proposed"} <= set(spec.stocks)


LONG = "A gap whose title runs on well past thirty-two characters"


def test_a_gap_whose_id_is_not_its_branch_is_one_item(tmp_path):
    f = Instance(tmp_path)
    gaps = f.checkout / "docs" / "GAPS.md"
    gaps.write_text(gaps.read_text().replace("## Done recently", f"- **{LONG}** (open): long.\n\n## Done recently"))
    git(f.checkout, "commit", "-qam", "a long one")
    f.run("intake.py")
    gid = [i for i in f.db()["items"] if i.startswith("gap/a-gap-whose")][0]
    branch = f.item(gid)["fields"]["branch"]
    assert gid != f"gap/{branch}"                                   # (60 characters of the title; the branch, 32)
    said, _ = f.run("plan.py", gid, FACTORY_STANDIN_PLANNER=PLAN.format(b=branch))
    assert said == ["gap.defined"] and f.item(gid)["state"] == "ready"
    f.run("intake.py")
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.built"]
    mine = [i for i in f.db()["items"].values() if i["kind"] == "gap" and i["fields"].get("branch") == branch]
    assert [i["id"] for i in mine] == [gid] and f"gap/{branch}" not in f.db()["items"]     # one item, taken once
    assert [i["id"] for i in f.db()["items"].values() if i["state"] == "ready"] == []


def test_a_split_whose_sub_gap_parks_is_parked(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    f.run("plan.py", gid, FACTORY_STANDIN_PLANNER=PLAN.format(b="alpha-one") + PLAN.format(b="alpha-two"))
    assert f.run("plan.py", argv=("splits",))[0] == []                # nothing stopped: it waits on
    f.fold([{"event": "gap.parked", "item": "gap/alpha-two", "data": {"where_it_stopped": "The lock order."}}], None)
    said, _ = f.run("plan.py", argv=("splits",))
    gap = f.item(gid)
    assert said == ["gap.parked"] and gap["state"] == "parked" and gap["fields"]["parked_in"] == "split"
    assert "gap/alpha-two (parked): The lock order." in gap["fields"]["where_it_stopped"]
    assert f.run("plan.py", argv=("splits",))[0] == []                # once


def test_a_dead_or_unanswered_question_is_planned_without(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    f.run("plan.py", gid, FACTORY_STANDIN_PLANNER="<research>One?</research><research>Two?</research>")
    one, two = f.item(gid)["fields"]["research"]
    db = f.db()
    db["items"][one]["state"] = "dead"                               # a dead letter
    f.record.write_text(json.dumps(db))
    said, _ = f.run("plan.py", gid)
    assert said == ["gap.measured"] and f.item(gid)["fields"]["research_waits"] == 1     # two still waits
    f.fold([{"event": "gap.measured", "item": gid, "data": {"research_waits": 11}}], None)
    said, _ = f.run("plan.py", gid)
    assert said == ["gap.defined"]                                   # after 12 waits: planned without
    brief = (f.model / f.item(gid)["fields"]["contexts"][-1]["brief"][5:]).read_text()
    assert f"### {one}\n\n(no answer: the question is a dead letter" in brief
    assert f"### {two}\n\n(no answer: the question was not answered in 12 waits)" in brief


def test_the_librarian_ships_off(tmp_path):
    f = Instance(tmp_path)
    f.config.write_text(f.config.read_text().replace("librarian = true", "librarian = false"))
    assert librarian(f, "review/a-1", ["x"], [{"finding": 1, "class": "lesson-1", "shape": "s", "new_shape": True}]) == []


RULES = "---\nkind: rules\n---\n# House rules\n\n**Process**\n- Define it first.\n\n**Code**\n- Keep it small.\n"
LESSONS = "---\nkind: lessons\n---\n# Lessons\n\n## 1. Failing open\nIt fails open.\n**Check:** fail closed.\n"
DECISIONS = ("---\nkind: decisions\n---\n# Decisions\n\n- **One model, three drawings.** Each its own style. *Areas: "
             "diagram, view.*\n")


def sync(f: Instance, dev: Path) -> list[dict]:
    """A run of the collector on the knowledge files of ``dev`` (a copy of dev/bin beside them): its event lines, folded."""
    r = subprocess.run([sys.executable, str(dev / "bin" / "knowledge.py"), "sync"], cwd=f.model, env=f.env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    f.fold(lines, None)
    return lines


def test_knowledge_sync_says_each_change_once(tmp_path):
    f = Instance(tmp_path)
    dev = tmp_path / "running" / "dev"
    shutil.copytree(BIN, dev / "bin", ignore=shutil.ignore_patterns("__pycache__"))
    k = dev / "knowledge"
    k.mkdir()
    for name, text in (("house-rules", RULES), ("review-lessons", LESSONS), ("decisions", DECISIONS)):
        (k / f"{name}.md").write_text(text)
    f.fold([{"event": "gap.started", "item": "gap/a", "data": {"contexts": [
        {"role": "implementor", "knowledge": ["rules-process", "lesson-1"]}, {"role": "reviewer", "knowledge": [
            "lesson-1", "lesson-1"]}]}}], None)
    lines = sync(f, dev)
    assert sorted(x["item"] for x in lines) == ["knowledge/decision-one-model-three-drawings", "knowledge/lesson-1",
                                                "knowledge/rules-code", "knowledge/rules-process"]
    assert {x["event"] for x in lines} == {"knowledge.found"}
    lesson = f.item("knowledge/lesson-1")
    assert lesson["state"] == "active" and lesson["fields"]["kind"] == "lesson"
    assert lesson["fields"]["title"] == "Failing open" and lesson["fields"]["file"] == "dev/knowledge/review-lessons.md"
    assert lesson["fields"]["text"].startswith("## 1. Failing open It fails open.") and lesson["fields"]["carried"] == 2
    decision = f.item("knowledge/decision-one-model-three-drawings")["fields"]
    assert decision["kind"] == "decision" and decision["areas"] == ["diagram", "view"] and decision["carried"] == 0
    assert f.item("knowledge/rules-process")["fields"]["kind"] == "rule"
    assert sync(f, dev) == []                                                       # idempotent: nothing said twice
    (k / "review-lessons.md").write_text(LESSONS.replace("It fails open.", "It fails open, quietly."))
    (k / "house-rules.md").write_text(RULES.split("**Code**")[0])
    f.fold([{"event": "gap.built", "item": "gap/a", "data": {"contexts": [
        {"role": "implementor", "knowledge": ["decision-one-model-three-drawings"]}]}}], None)
    lines = sync(f, dev)
    assert sorted((x["event"], x["item"]) for x in lines) == [
        ("knowledge.changed", "knowledge/decision-one-model-three-drawings"), ("knowledge.changed", "knowledge/lesson-1"),
        ("knowledge.retired", "knowledge/rules-code")]
    changed = {x["item"]: x["data"] for x in lines if x["event"] == "knowledge.changed"}
    assert set(changed["knowledge/lesson-1"]) == {"text", "changed_at"}             # only what changed
    assert changed["knowledge/decision-one-model-three-drawings"]["carried"] == 1
    assert "quietly" in f.item("knowledge/lesson-1")["fields"]["text"] and f.item("knowledge/rules-code")["state"] == "retired"
    assert sync(f, dev) == []
    (k / "house-rules.md").write_text(RULES)                                         # back in the files: found again
    assert [(x["event"], x["item"]) for x in sync(f, dev)] == [("knowledge.found", "knowledge/rules-code")]
    assert f.item("knowledge/rules-code")["state"] == "active"


def test_knowledge_entries_counts_the_items():
    from ergostat.spec import read
    from tests.test_factory import ROOT
    spec, _ = read(ROOT / "ergostat.yaml")
    sensor = spec.stocks["knowledge-entries"].sensors["main"]
    assert sensor.run is None and (sensor.items["kind"], sensor.items["state"]) == ("knowledge", ["active"])
    assert spec.items["knowledge"].states == ["active", "retired"] and spec.blocks["knowledge-sync"].type == "program"


LINT = "import fac, plan; print(json.dumps(plan.lint(fac.config(), sys.argv[1], tuple(sys.argv[2:]))))"
GOOD = PLAN.format(b="alpha-thing").split(">\n", 1)[1].rsplit("</definition>", 1)[0]


def test_the_lint_catches_each_missing_piece(tmp_path):
    f = Instance(tmp_path)
    f.opened()
    assert f.py(LINT, GOOD) == []
    assert f.py(LINT, GOOD.replace("depends-on: []", "depends-on: [alpha-thing, sib, nowhere]"), "sib") == [
        "depends-on 'nowhere': no gap, sub-gap of this plan or branch merged into main"]   # a gap, a sibling: fine
    git(f.checkout, "branch", "landed")                        # a branch merged into main: fine
    assert f.py(LINT, GOOD.replace("depends-on: []", "depends-on: [landed]")) == []
    for section in ("Definition of done", "Files to touch", "Risks", "Acceptance tests", "Size budget"):
        assert f"no `## {section}` section" in f.py(LINT, GOOD.replace(f"## {section}", "## Other"))
    cases = {"depends-on: []\n": ("", "no `depends-on"),
             "- `tests/test_x.py::test_unreadable_ledger_refuses`": ("- the ledger test", "not named as `tests/"),
             "100 net lines.": ("small.", "names no number"),
             "100 net lines": ("900 net lines", "900 net lines: at most 600"),
             "lesson-3:": ("lesson-999:", "lesson-999 under Risks is no review lesson"),
             "`fresh.py` (new)": ("`fresh.py`", "`fresh.py` under Files to touch is not on main"),
             "- `app.py`, and `fresh.py` (new)": ("- the app", "no file named under Files to touch")}
    for old, (new, found) in cases.items():
        got = f.py(LINT, GOOD.replace(old, new))
        assert len(got) == 1 and found in got[0], (old, got)   # each piece missing: exactly its finding


def test_a_lint_failure_goes_back_uncounted(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    bad = PLAN.format(b="alpha-thing").replace("## Risks", "## Worries")
    for n in range(1, 6):
        said, _ = f.run("plan.py", gid, FACTORY_STANDIN_PLANNER=bad)
        gap = f.item(gid)["fields"]
        assert said == ["gap.plan-sent-back"] and gap["plan_sent_back_by"] == "lint" and gap["plan_lint_failures"] == n
        assert gap["plan_findings"] == ["no `## Risks` section"] and not gap.get("plan_failures")
    assert not (f.model / "run" / "defs" / "alpha-thing.md").exists()         # never the definition
    said, _ = f.run("plan.py", gid, FACTORY_STANDIN_PLANNER=bad)              # the 6th: a planner that cannot
    assert said[-1] == "gap.parked" and f.item(gid)["fields"]["parked_in"] == "plan"


def test_the_sweep_defines_plans_the_old_review_held(tmp_path):
    f = Instance(tmp_path)
    plans = f.model / "run" / "plans"
    plans.mkdir(parents=True)
    for name in ("held", "sent", "bad", "linted"):
        (plans / f"{name}.md").write_text(GOOD.replace("## Risks", "## Worries") if name == "bad" else GOOD)
    f.fold([{"event": "gap.planned", "item": "gap/held", "data": {"branch": "held"}},
            {"event": "gap.planned", "item": "gap/bad", "data": {"branch": "bad"}},
            {"event": "gap.plan-sent-back", "item": "gap/sent", "data": {"branch": "sent",
                                                                          "plan_findings": ["a sharper test"]}},
            {"event": "gap.plan-sent-back", "item": "gap/linted", "data": {"branch": "linted",
                                                                            "plan_sent_back_by": "lint"}}], None)
    said, _ = f.run("plan.py", argv=("lint",))
    assert sorted(said) == ["gap.defined", "gap.defined", "gap.plan-sent-back"]
    assert f.item("gap/held")["state"] == f.item("gap/sent")["state"] == "ready"
    assert f.item("gap/held")["fields"]["released_from"] == "planned" and f.item("gap/bad")["state"] == "replan"
    assert (f.model / "run" / "defs" / "sent.md").read_text().endswith("(answer each)\n\n- a sharper test\n")
    assert f.item("gap/linted")["state"] == "replan"           # the lint's own: the planner writes it again
    assert f.run("plan.py", argv=("lint",))[0] == []


def graph_fixture(f: Instance, n_ready: int = 1) -> None:
    """A merged gap (its merge commit in the checkout), an active one and ready ones, each with its files."""
    (f.checkout / "merged_mod.py").write_text("x = 1\n")
    git(f.checkout, "checkout", "-q", "-b", "landed")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "landed")
    git(f.checkout, "checkout", "-q", "main")
    git(f.checkout, "merge", "-q", "--no-ff", "-m", "Merge landed", "landed")
    sha = git(f.checkout, "rev-parse", "HEAD")
    defs = f.model / "run" / "defs"
    defs.mkdir(parents=True, exist_ok=True)
    now = __import__("time").time()
    lines = [{"event": "gap.merged", "item": "gap/landed", "data": {"title": "Landed work", "branch": "landed",
                                                                    "merged_at": now - 3600, "main_sha": sha}},
             {"event": "gap.merged", "item": "gap/old", "data": {"title": "Old", "branch": "old", "merged_at": now - 9e5}}]
    for name, event in [("busy", "gap.started")] + [(f"next-{i}", "gap.defined") for i in range(n_ready)]:
        (defs / f"{name}.md").write_text(GOOD.replace("`app.py`, and `fresh.py` (new)", f"`{name}_mod.py` (new)"))
        lines.append({"event": event, "item": f"gap/{name}", "data": {
            "title": name.title(), "branch": name, "definition": f"run/defs/{name}.md", "depends_on": ["gap/landed"]}})
    f.fold(lines, None)


GRAPH = "import fac, brief; print(json.dumps(brief.graph(fac.config(), {'id': sys.argv[1]})))"


def test_the_graph_brief_lists_merged_active_and_ready(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    graph_fixture(f)
    text = f.py(GRAPH, gid)
    merged, active, ready = text.split("### ")[1:]
    assert "gap/landed (merged, `landed`): Landed work. Changed: merged_mod.py" in merged and "gap/old" not in text
    assert "gap/busy (building, `busy`): Busy. Touches: busy_mod.py" in active
    assert "gap/next-0 (ready, `next-0`): Next-0. Touches: next-0_mod.py. Depends on: gap/landed" in ready
    assert gid not in text                                     # never the gap itself


def test_the_graph_brief_stays_bounded(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    graph_fixture(f, n_ready=60)
    text = f.py(GRAPH, gid)
    lines = text.splitlines()
    assert len(lines) <= 40 and "gap/landed" in text and "gap/busy" in text      # every section keeps its share
    assert lines[-1].startswith("- ... and ") and lines[-1].endswith(" more not shown")


def test_the_reviewer_sees_overlap_in_its_brief(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    graph_fixture(f)
    dup = PLAN.format(b="alpha-thing").replace("`app.py`, and `fresh.py` (new)", "`merged_mod.py`, `busy_mod.py` (new)")
    assert f.run("plan.py", gid, FACTORY_STANDIN_PLANNER=dup)[0] == ["gap.defined"]
    planner = (f.model / f.item(gid)["fields"]["contexts"][-1]["brief"][5:]).read_text()
    f.run("planreview.py")
    context = f.item(gid)["fields"]["contexts"][-1]
    reviewer = (f.model / context["brief"][5:]).read_text()
    assert context["role"] == "plan_reviewer"
    for brief_ in (planner, reviewer):                         # what landed and what is active, with their files
        assert "Changed: merged_mod.py" in brief_ and "gap/busy (building, `busy`): Busy. Touches: busy_mod.py" in brief_
    assert "`merged_mod.py`, `busy_mod.py` (new)" in reviewer and "{graph}" not in reviewer
    assert "advice, never a gate" in reviewer


def test_plan_review_waits_for_money(tmp_path):
    f = Instance(tmp_path)
    gid = f.opened()
    f.run("plan.py", gid)
    f.config.write_text(f.config.read_text().replace("plan_reviewer_session_usd = 1.0", "plan_reviewer_session_usd = 9e9"))
    assert f.run("planreview.py")[0] == [] and f.item(gid)["fields"]["plan_review"] == "wanted"


def test_plan_review_measures(tmp_path):
    f = Instance(tmp_path)
    now = __import__("time").time()
    rev = lambda *bs: [{"verdict": "fix" if b else "merge", "blocking": b, "at": now - 60} for b in bs]  # noqa: E731
    gaps = [("a", "merged", rev(0), True, 0), ("b", "merged", rev(2), True, 3), ("c", "parked", rev(1), True, 0),
            ("d", "merged", rev(0), False, 1), ("e", "merged", [{"verdict": "fix", "blocking": 1, "at": now - 9e6}], False, 5)]
    f.fold([{"event": "gap.merged" if st == "merged" else "gap.parked", "item": f"gap/{n}", "data": {
        "plan_reviews": r, "plan_review": "done", "plan_flagged": any(x["blocking"] for x in r), "fix_rounds": fr,
        ("merged_at" if st == "merged" else "parked_at"): now - (9e6 if n == "e" else 60)}}
        for n, st, r, _, fr in gaps] + [{"event": "gap.defined", "item": "gap/w", "data": {"plan_review": "wanted"}}],
        None)
    read = lambda *a: f.py("import planreview; print(planreview.reading(*sys.argv[1:]))", *a)  # noqa: E731
    assert read("waiting") == 1.0
    assert read("agreement") == 0.5                            # a, d of a, b, c, d (e's review is past 14 days)
    assert read("value", "fix-rounds", "flagged") == 1.5 and read("value", "fix-rounds", "clean") == 0.5
    assert read("value", "parks", "flagged") == 0.5 and read("value", "parks", "clean") == 0.0
