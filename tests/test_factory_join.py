"""The split parent judged at the join (docs/roadmap/overnight/split-verified-2.md): the join moves a split gap whose
sub-gaps all merged to `joined`, and the join judge (plan.py join) merges it (covered), requests a new sub-gap for what
is not built and splits it again (short, at most plan.MOST_SHORT times), or parks it; never merged when it fails.
Covered records no merged_at; a sub-gap it cannot read is short with no session."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import time

import pytest

from ergostat import model as mdl
from ergostat.spec import items as its
from ergostat.spec import read
from ergostat.spec.engine import Engine
from ergostat.store import Project
from tests.test_factory import BIN, ROOT
from tests.test_factory_knowledge import PLAN, Instance, covered

pytestmark = pytest.mark.slow                                        # (each 10 s or more: started first)
GID = "gap/alpha-thing"
COVERED = "Read it all.\n<verdict>covered</verdict>\n<reasons>both points built, in app.py</reasons>\n"


def short(*points: str) -> str:
    return "<verdict>short</verdict>\n<missing>\n" + "".join(f"- {p}\n" for p in points) + "</missing>\n<reasons>r</reasons>"


def gap_model(tmp_path) -> Project:
    """A project of the factory's own gap kind (its states, fold and join), as compiled from ergostat.yaml."""
    text = (ROOT / "ergostat.yaml").read_text()
    kind = text[text.index("\n  gap:\n"):text.index("\n  review:\n")]
    (tmp_path / "ergostat.yaml").write_text("name: t\nitems:" + kind + "\n")
    return Project(mdl.load(tmp_path))


def state(p, iid):
    it = its.one(p.events, p.model.spec, iid)
    return it.state if it else None


def wait_for(cond, seconds=10.0):
    end = time.time() + seconds
    while time.time() < end and not cond():
        time.sleep(0.02)
    return cond()


def check_found(folder) -> list[str]:
    """The model's errors and findings, as `ergostat check` reads them (in process, no store opened; its notes, the
    structure's screens, are advice and left out)."""
    _, problems = read(folder / "ergostat.yaml")
    return sorted(f"{p.level} {p.code} {p.message}" for p in problems if p.level != "note")


def test_a_split_whose_sub_gaps_all_merged_waits_in_joined(tmp_path):
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == [] and not [p for p in problems if p.code == "join-side-state"]
    states = spec.items["gap"].states
    assert states.index("split") < states.index("joined") < states.index("merged")
    assert [(j.to, j.states, j.all) for j in spec.items["gap"].join] == [("joined", ["merged"], True)]
    judge = spec.blocks["join-judge"]
    assert judge.takes.at == ["joined"] and set(judge.takes.to) == {"merged", "split", "parked"}
    assert not [b for n, b in spec.blocks.items() if n != "join-judge" and b.takes and "joined" in b.takes.at]
    main = tmp_path / "main"                                         # ergostat check: nothing new against main
    main.mkdir()
    tar = subprocess.run(["git", "archive", "main", "ergostat.yaml", "dev"], cwd=ROOT, capture_output=True,
                         check=True).stdout
    tarfile.open(fileobj=io.BytesIO(tar)).extractall(main, filter="data")
    here = {f"{x.level} {x.code} {x.message}" for x in problems if x.level != "note"}
    assert here - set(check_found(main)) == set()
    (tmp_path / "m").mkdir()
    p = gap_model(tmp_path / "m")
    p.events.add("gap.split", item=GID, source="t")
    for k in ("gap/alpha-one", "gap/alpha-two"):
        p.events.add("gap.requested", item=k, source="t", data={"parent": [GID]})
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        p.events.add("gap.merged", item="gap/alpha-one", source="t")
        time.sleep(0.4)
        assert state(p, GID) == "split"                              # one of two merged is not all
        p.events.add("gap.merged", item="gap/alpha-two", source="t")
        assert wait_for(lambda: state(p, GID) == "joined")
        time.sleep(0.4)
        assert state(p, GID) == "joined"                             # waits there for the judge: never merged by it
    finally:
        e.close()


def judged_instance(tmp_path, **kw) -> Instance:
    """A gap split into alpha-one and alpha-two, both reviewed and merged, the parent joined."""
    f = Instance(tmp_path, **kw)
    f.config.write_text(f.config.read_text().replace("[ai]\n", '[ai]\njoin_judge_model = "opus"\n'
                                                     'join_judge_session_usd = 1.0\n'))
    gid = f.opened()
    f.run("plan.py", gid, FACTORY_STANDIN_PLANNER=PLAN.format(b="alpha-one") + PLAN.format(b="alpha-two")
          + covered(points=("it locks (by: alpha-one)", "it says why (by: alpha-two)")))
    for k in ("alpha-one", "alpha-two"):
        merge(f, k, f"the finding of {k}")
    joined(f)
    return f


def merge(f: Instance, branch: str, finding: str = "a finding") -> None:
    rid = f"review/{branch}-1"
    f.fold([{"event": "review.written", "item": rid, "data": {"gap": f"gap/{branch}", "round": 1, "verdict": "merge",
                                                              "blocking": [], "non_blocking": [finding]}},
            {"event": "gap.measured", "item": f"gap/{branch}", "data": {"reviews": [rid]}},
            {"event": "gap.merged", "item": f"gap/{branch}", "data": {"merged_at": time.time(), "main_sha": "abc123"}}],
           None)


def joined(f: Instance) -> None:
    """The engine's join (ergostat.item.joined), which the fixture's fold does not run."""
    db = f.db()
    assert all(db["items"][k]["state"] == "merged" for k in db["items"][GID]["fields"]["children"])
    db["items"][GID]["state"] = "joined"
    f.record.write_text(json.dumps(db))


def judge(f: Instance, said: str, fails: bool = False, **env):
    return f.run("plan.py", GID, argv=("join",), fails=fails, FACTORY_STANDIN_JOIN_JUDGE=said, **env)


def saved_brief(f: Instance) -> str:
    got = (f.model / "run" / "briefs").glob("alpha-thing-join_judge-*.md")
    return max(got, key=lambda p: int(p.stem.rsplit("-", 1)[1])).read_text()


WORK_MEASURES = ("cycle-hours", "cost-per-merged", "fix-rounds")


def test_join_moves_parent_to_joined_then_judge_merges(tmp_path):
    f = judged_instance(tmp_path)
    now = time.time()                                                # sub-gaps of 1 h and 3 h; a parent of 10 h that
    f.fold([{"event": "gap.measured", "item": f"gap/alpha-{k}", "data": {"ready_at": now - h * 3600}}    # would move
            for k, h in (("one", 1), ("two", 3))] + [{"event": "gap.measured", "item": GID, "data": {   # each measure
                "ready_at": now - 10 * 3600, "fix_rounds": 3, "ai_cost_usd": 50}}], None)
    before = [measure(f, m).stdout for m in WORK_MEASURES]
    assert before == ["2.0\n", "0.0\n", "0.0\n"], before
    said, _ = judge(f, COVERED)
    gap = f.item(GID)
    assert said == ["gap.merged"] and gap["state"] == "merged" and "merged_at" not in gap["fields"]
    assert [measure(f, m).stdout for m in WORK_MEASURES] == before      # no work merged: none of the three moves
    assert gap["fields"]["join_verdict"] == "covered" and "in app.py" in gap["fields"]["join_reasons"]
    assert gap["fields"]["judged_at"] > 0 and gap["fields"]["join_verdicts"][0]["verdict"] == "covered"
    assert gap["fields"]["sessions"] == 2 and "merged_lines" not in gap["fields"]   # (the planner's and the judge's)
    text = saved_brief(f)
    assert "- it locks (by: alpha-one)" in text and "- it says why (by: alpha-two)" in text
    assert "# alpha-one: a plan" in text and "# alpha-two: a plan" in text
    assert "- the finding of alpha-one" in text and "- the finding of alpha-two" in text
    assert "review/alpha-one-1: verdict merge" in text and text.count("(missing:") == 1   # (the prompt's own)


def test_a_short_verdict_requests_a_sub_gap_before_reopening_the_parent(tmp_path):
    f = judged_instance(tmp_path)
    said, lines = judge(f, short("it never times out (by: alpha-one)", "the doc says so"))
    assert said == ["gap.requested", "gap.split"]
    new = f.item("gap/alpha-thing-join-1")
    assert new["state"] == "open" and new["fields"]["parent"] == [GID] and new["fields"]["source"] == "join"
    assert "- it never times out\n- the doc says so" in new["fields"]["entry"]
    assert new["fields"]["entry"].startswith(f.item(GID)["fields"]["title"])
    plan = (f.model / "run" / "plans" / "alpha-thing.md").read_text()
    assert "- it never times out (by: alpha-thing-join-1)\n- the doc says so (by: alpha-thing-join-1)\n</coverage>" \
        in plan and plan.count("<coverage>") == 1 and "- it locks (by: alpha-one)" in plan
    parent = f.item(GID)
    assert parent["state"] == "split" and "gap/alpha-thing-join-1" in parent["fields"]["children"]
    assert parent["fields"]["join_short_rounds"] == 1 and parent["fields"]["join_missing"] == [
        "it never times out", "the doc says so"]
    (tmp_path / "m").mkdir()
    p = gap_model(tmp_path / "m")                                    # the run's events, in order, on the factory's
    p.events.add("gap.split", item=GID, source="t")                  # own model
    for k in ("gap/alpha-one", "gap/alpha-two"):
        p.events.add("gap.requested", item=k, source="t", data={"parent": [GID]})
        p.events.add("gap.merged", item=k, source="t")
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        assert wait_for(lambda: state(p, GID) == "joined")
        seqs = {x["event"]: p.events.add(x["event"], item=x.get("item") or GID, source="t", data=x.get("data"))["seq"]
                for x in lines if x.get("event", "").startswith("gap.")}
        assert seqs["gap.requested"] < seqs["gap.split"]
        time.sleep(0.4)
        assert state(p, GID) == "split"                              # not joined again: the new sub-gap is open
        p.events.add("gap.merged", item="gap/alpha-thing-join-1", source="t")
        assert wait_for(lambda: state(p, GID) == "joined")           # and joined once it merges
    finally:
        e.close()
    planned = f.run("plan.py", "gap/alpha-thing-join-1", FACTORY_STANDIN_PLANNER=PLAN.format(b="alpha-thing-join-1"))
    assert planned[0] == ["gap.defined"]                             # the planner plans it like any other
    assert "- the doc says so" in sorted((f.model / "run" / "briefs").glob("alpha-thing-join-1-planner-*.md"))[-1] \
        .read_text()


def test_join_not_covered_requests_new_gap_then_second_parks(tmp_path):
    f = judged_instance(tmp_path)
    f.fold([{"event": "gap.requested", "item": "gap/alpha-thing-join-1", "data": {"title": "an id taken"}},
            {"event": "gap.requested", "item": "gap/other", "data": {"branch": "alpha-thing-join-2"}}], None)
    said, _ = judge(f, short("it never times out"))                  # the name it would give, and the next, are taken
    assert said == ["gap.requested", "gap.split"]
    new = f.item("gap/alpha-thing-join-3")
    assert new["state"] == "open" and new["fields"]["parent"] == [GID] and new["fields"]["branch"] == "alpha-thing-join-3"
    assert f.item("gap/alpha-thing-join-1")["fields"] == {"title": "an id taken"}
    assert "(by: alpha-thing-join-3)" in (f.model / "run" / "plans" / "alpha-thing.md").read_text()
    assert f.run("plan.py", new["id"], FACTORY_STANDIN_PLANNER=PLAN.format(b="alpha-thing-join-3"))[0] == ["gap.defined"]
    merge(f, "alpha-thing-join-3", "the first round's finding")
    joined(f)
    said, _ = judge(f, short("it still never times out", "the doc"))
    gap = f.item(GID)
    assert said == ["gap.measured", "gap.parked"] and gap["state"] == "parked"       # the second short parks it
    assert "Not built:\n- it still never times out\n- the doc\n" in gap["fields"]["where_it_stopped"]
    assert gap["fields"]["parked_in"] == "joined" and gap["fields"]["join_short_rounds"] == 1
    assert [k for k in f.db()["items"] if k.startswith("gap/") and "-join-" in k] == ["gap/alpha-thing-join-1", "gap/alpha-thing-join-3"]
    assert "review/alpha-thing-join-3-1: verdict merge" in saved_brief(f)          # the judge saw the new sub-gap too
    assert "- the first round's finding" in saved_brief(f)


UNSESSIONED = """import runpy, sys
sys.path[:0] = [{bin!r}]
import agents, fac
def refused(*a, **k):
    raise SystemExit("a clone or a session was made")
fac.attempt = agents.clone = refused
sys.argv = [{plan!r}, "join"]
runpy.run_path({plan!r}, run_name="__main__")
"""


def judge_unsessioned(f: Instance) -> list[str]:
    """plan.py join with fac.attempt and agents.clone made to fail if called."""
    script = f.model / "unsessioned.py"
    script.write_text(UNSESSIONED.format(bin=str(BIN), plan=str(BIN / "plan.py")))
    r = subprocess.run([sys.executable, str(script)], input=json.dumps({"trigger": "item", "item": f.item(GID), "lease": {
        "fence": 1, "back": "joined"}}), cwd=f.model, capture_output=True, text=True, timeout=120,
        env={**f.env, "ERGOSTAT_ITEM": GID, "ERGOSTAT_LEASE": "1"})
    assert r.returncode == 0, r.stderr
    return f.fold([json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")], GID)


def test_join_with_missing_sub_gap_definition_is_not_covered(tmp_path):
    for case, why in (("definition", "its definition could not be read (missing: nothing readable at run/defs/"),
                      ("review", "its last review could not be read (missing: no review recorded)"),
                      ("child", "not in the record as a sub-gap of gap/alpha-thing")):
        f = judged_instance(tmp_path / case)
        if case == "definition":
            (f.model / "run" / "defs" / "alpha-two.md").unlink()
        db = f.db()
        if case == "review":
            db["items"]["gap/alpha-two"]["fields"]["reviews"] = []
        if case == "child":
            del db["items"]["gap/alpha-two"]
        f.record.write_text(json.dumps(db))
        cost, sessions = (f.item(GID)["fields"].get(k) for k in ("ai_cost_usd", "sessions"))
        assert judge_unsessioned(f) == ["gap.requested", "gap.split"], case
        g = f.item(GID)["fields"]
        assert g["join_verdict"] == "short" and g["join_verdicts"][-1]["verdict"] == "short", case
        assert [p for p in g["join_missing"] if p.startswith("gap/alpha-two: ") and why in p] == g["join_missing"], \
            (case, g["join_missing"])
        assert (g.get("ai_cost_usd") or 0, g.get("sessions")) == (cost or 0, sessions), case
        assert not list((f.model / "run" / "briefs").glob("alpha-thing-join_judge-*.md")), case


def test_join_judges_a_stopped_sub_gap_by_its_continuation(tmp_path):
    """parks.split_again's shape: the stopped alpha-two keeps its place in the parent's children but no longer names
    it as parent; its continuation does. Judged by a session through the continuation, never short for it."""
    f = judged_instance(tmp_path)
    defs = f.model / "run" / "defs"
    (defs / "alpha-two-continued.md").write_text((defs / "alpha-two.md").read_text())
    f.fold([{"event": "gap.requested", "item": "gap/alpha-two-continued", "data": {
        "branch": "alpha-two-continued", "parent": [GID]}}], None)
    merge(f, "alpha-two-continued", "the continuation's finding")
    db = f.db()
    db["items"]["gap/alpha-two"]["fields"].update(parent=[], resumed_as="gap/alpha-two-continued")
    db["items"]["gap/alpha-two"]["state"] = "parked"
    db["items"][GID]["state"] = "joined"
    f.record.write_text(json.dumps(db))
    said, _ = judge(f, COVERED)
    assert said == ["gap.merged"] and f.item(GID)["fields"]["join_verdict"] == "covered"
    text = saved_brief(f)
    assert "- the continuation's finding" in text and "not in the record as a sub-gap" not in text
    db = f.db()                                      # a stopped one never continued: still short, with no session
    db["items"]["gap/alpha-two"]["fields"]["resumed_as"] = "gap/nowhere"
    db["items"]["gap/alpha-two-continued"]["fields"]["parent"] = []
    db["items"][GID]["state"] = "joined"
    f.record.write_text(json.dumps(db))
    assert judge_unsessioned(f)[-1] == "gap.split"
    assert f.item(GID)["fields"]["join_missing"] == ["gap/alpha-two: not in the record as a sub-gap of gap/alpha-thing"]


UNREADABLE = ["It is all built.", COVERED + "<missing>\n- one\n</missing>", COVERED + COVERED,
              "<verdict>short</verdict>\n<missing>\n</missing>", "<verdict>short</verdict>\n- one", "<verdict>fine</verdict>",
              short("one") + "<missing>\n- two\n</missing>"]


def test_an_unreadable_verdict_or_failed_session_never_merges(tmp_path):
    f = judged_instance(tmp_path)
    for n, said in enumerate(UNREADABLE, start=2):
        judge(f, said, fails=True)                                   # (an attempt counted under the lease)
        gap = f.item(GID)
        assert gap["state"] == "joined" and "no readable verdict" in gap["fields"]["last_error"], said
        assert gap["fields"]["sessions"] == n and "join_verdict" not in gap["fields"]   # its cost recorded
    assert [k for k in f.db()["items"] if "-join-" in k] == []
    (f.model / "run" / "costs.jsonl").write_text("not json\n")       # a budget refusal: it waits, no session
    said, lines = judge(f, COVERED)
    assert said == [] and "budget" in [x for x in lines if "nack" in x][0]["nack"]["why"]
    assert f.item(GID)["state"] == "joined" and f.item(GID)["fields"]["sessions"] == len(UNREADABLE) + 1
    (f.model / "run" / "costs.jsonl").unlink()
    cfg = f.config.read_text()
    f.config.write_text(cfg.replace('mode = "standin"', 'mode = "container"')
                        + f'[agents]\ntoken_file = "{tmp_path / "no-token"}"\n')
    judge(f, COVERED, fails=True)                                    # a session that raises (no token)
    assert "no session token" in f.stderr and f.item(GID)["state"] == "joined"
    f.config.write_text(cfg)
    missing_brief(f)


def missing_brief(f: Instance) -> None:
    """A missing coverage file: still judged (from the entry and the sub-gaps), and said. (A missing sub-gap
    definition or review is short with no session: test_join_with_missing_sub_gap_definition_is_not_covered.)"""
    (f.model / "run" / "plans" / "alpha-thing.md").unlink()
    said, _ = judge(f, COVERED)                                      # still judged, from the entry and the sub-gaps
    assert said == ["gap.merged"]
    text = saved_brief(f)
    assert "(missing: run/plans/alpha-thing.md: FileNotFoundError" in text, text
    assert "# alpha-one: a plan" in text and "# alpha-two: a plan" in text


DAY = 86400


def measure(f: Instance, name: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BIN / "measure.py"), name], cwd=f.model, env=f.env,
                          capture_output=True, text=True, timeout=60)


def parent(f: Instance, gid: str, *verdicts: tuple[str, float], kids: tuple[str, ...] = ("gap/x-one",), **merged):
    """A split parent with its children and join verdicts, in this record order (and merged, given its fields)."""
    lines = [{"event": "gap.split", "item": gid, "data": {"children": list(kids)}}]
    lines += [{"event": "gap.measured", "item": gid, "data": {"join_verdicts": [{"verdict": v, "missing": [], "at": at}]}}
              for v, at in verdicts]
    lines += [{"event": "gap.merged", "item": gid, "data": merged}] if merged else []
    f.fold(lines, None)


def gap(f: Instance, gid: str, merged: bool = True, **fields) -> None:
    f.fold([{"event": "gap.merged" if merged else "gap.requested", "item": gid,
             "data": {**({"merged_at": time.time() - DAY} if merged else {}), **fields}}], None)


def test_split_joins_counts_judged_parents_over_the_whole_record(tmp_path):
    f = Instance(tmp_path)
    now = time.time()
    parent(f, "gap/p-month", ("short", now - 30 * DAY))
    parent(f, "gap/p-twice", ("short", now), ("covered", now))
    parent(f, "gap/p-unjudged")
    r = measure(f, "split-joins")
    assert r.returncode == 0 and r.stdout.strip() == "2.0", r.stderr


def priced_split(f: Instance, gid: str = "gap/p") -> None:
    """A parent costing 2 whose children cost 10 and 8 with 60 and 50 lines (110: M)."""
    for k, cost, lines in (("one", 10, 60), ("two", 8, 50)):
        gap(f, f"{gid}-{k}", parent=[gid], ai_cost_usd=cost, merged_lines=lines)
    parent(f, gid, ("covered", time.time()), kids=(f"{gid}-one", f"{gid}-two"), judged_at=time.time(), ai_cost_usd=2)


def unsplit(f: Instance) -> None:
    for n, (cost, lines) in enumerate(((5, 100), (10, 120), (40, 60), (1, 10))):   # M: 5, 10, 40; S: 1
        gap(f, f"gap/u-{n}", ai_cost_usd=cost, merged_lines=lines)


def test_split_overhead_is_the_split_cost_over_the_unsplit_median_of_its_class(tmp_path):
    f = Instance(tmp_path)
    unsplit(f)
    priced_split(f)
    r = measure(f, "split-overhead")
    assert r.returncode == 0 and r.stdout.strip() == "2.0", r.stderr               # (2 + 10 + 8) / 10


def unpriceable(f: Instance) -> None:
    now = time.time()
    for gid, kid, merged, fields in (("gap/q-lines", "gap/q-lines-1", True, {"ai_cost_usd": 3}),
                                     ("gap/q-cost", "gap/q-cost-1", True, {"merged_lines": 80}),
                                     ("gap/q-open", "gap/q-open-1", False, {"ai_cost_usd": 3, "merged_lines": 80}),
                                     ("gap/q-class", "gap/q-class-1", True, {"ai_cost_usd": 3, "merged_lines": 900})):
        gap(f, kid, merged, parent=[gid], **fields)
        parent(f, gid, ("covered", now), kids=(kid,), judged_at=now, ai_cost_usd=1)


def test_split_overhead_leaves_out_a_parent_it_cannot_price(tmp_path):
    f = Instance(tmp_path / "a")
    unsplit(f)
    priced_split(f)
    unpriceable(f)
    r = measure(f, "split-overhead")
    assert r.returncode == 0 and r.stdout.strip() == "2.0", r.stderr
    for gid, why in (("gap/q-lines", "a child with no merged_lines"), ("gap/q-cost", "a child with no ai_cost_usd"),
                     ("gap/q-open", "a child not merged"), ("gap/q-class", "no merged unsplit XL gap")):
        assert f"{gid}: {why}" in r.stderr, (gid, r.stderr)
    assert "gap/p:" not in r.stderr
    g = Instance(tmp_path / "b")
    unsplit(g)
    unpriceable(g)
    r = measure(g, "split-overhead")
    assert r.returncode == 1 and r.stdout == "" and "no value" in r.stderr


def test_split_overhead_prices_a_parked_sub_gap_and_its_continuation(tmp_path):
    """parks.split_again unlinks the stopped sub-gap (parent set to []) and links its continuation by `parent` only,
    leaving the parent's `children` as they were: the stopped one's cost counts, its lines do not."""
    f = Instance(tmp_path)
    unsplit(f)
    now = time.time()
    gap(f, "gap/p-one", parent=["gap/p"], ai_cost_usd=10, merged_lines=60)
    f.fold([{"event": "gap.parked", "item": "gap/p-two", "data": {"parent": ["gap/p"], "ai_cost_usd": 2,
                                                                  "merged_lines": 999}},
            {"event": "gap.resumed", "item": "gap/p-two", "data": {"resumed_as": "gap/p-two-continued"}},
            {"event": "gap.measured", "item": "gap/p-two", "data": {"parent": {"set": []}}}], None)
    gap(f, "gap/p-two-continued", parent=["gap/p"], ai_cost_usd=6, merged_lines=50)
    parent(f, "gap/p", ("covered", now), kids=("gap/p-one", "gap/p-two"), judged_at=now, ai_cost_usd=2)
    r = measure(f, "split-overhead")
    assert r.returncode == 0 and r.stdout.strip() == "2.0", r.stderr        # (2 + 10 + 2 + 6) / 10, class M (110)


def test_the_split_measures_are_sensed_in_the_factory_model():
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    doc = (BIN / "measure.py").read_text().split('"""')[1]
    for name in ("splits-covered", "split-budgets-held", "split-joins", "split-overhead"):
        aux = spec.auxiliaries[name]
        assert aux.system == "intake" and [s.run for s in aux.sensors.values()] == [
            f"python3 dev/bin/measure.py {name}"]
        assert f"\n  {name} " in doc
