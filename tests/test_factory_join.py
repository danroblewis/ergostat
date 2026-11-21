"""The split parent judged at the join (docs/roadmap/overnight/split-verified-2.md): the join moves a split gap whose
sub-gaps all merged to `joined`, and the join judge (plan.py join) merges it (covered), requests a new sub-gap for what
is not built and splits it again (short, at most plan.MOST_SHORT times), or parks it; never merged when it fails."""

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
from tests.test_factory import ROOT
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
    """`ergostat check`'s errors and findings (its notes, the structure's screens, are advice and left out)."""
    r = subprocess.run([sys.executable, "-m", "ergostat", "check", "--json", "--no-coherence"], cwd=folder,
                       capture_output=True, text=True, timeout=300)
    return sorted(f"{x.get('level')} {x.get('code')} {x.get('message')}" for x in json.loads(r.stdout).get("found", [])
                  if x.get("level") != "note")


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
    assert set(check_found(ROOT)) - set(check_found(main)) == set()
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


def test_a_covered_verdict_merges_the_parent(tmp_path):
    f = judged_instance(tmp_path)
    said, _ = judge(f, COVERED)
    gap = f.item(GID)
    assert said == ["gap.merged"] and gap["state"] == "merged"
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


def test_a_second_short_round_names_a_new_sub_gap(tmp_path):
    f = judged_instance(tmp_path)
    judge(f, short("it never times out"))
    merge(f, "alpha-thing-join-1", "the first round's finding")
    joined(f)
    said, _ = judge(f, short("it still never times out"))
    assert said == ["gap.requested", "gap.split"]
    one, two = f.item("gap/alpha-thing-join-1"), f.item("gap/alpha-thing-join-2")
    assert one["state"] == "merged" and two["state"] == "open"
    assert not set(two["fields"]) & {"reviews", "merged_at", "main_sha"}
    assert "it still never times out" in two["fields"]["entry"] and "\n- it never times out" not in two["fields"]["entry"]
    assert f.item(GID)["fields"]["join_short_rounds"] == 2
    assert "review/alpha-thing-join-1-1: verdict merge" in saved_brief(f)          # the judge saw the new sub-gap too
    assert "- the first round's finding" in saved_brief(f)


def test_the_third_short_verdict_parks_the_parent(tmp_path):
    f = judged_instance(tmp_path)
    for n in (1, 2):
        assert judge(f, short(f"point {n}"))[0] == ["gap.requested", "gap.split"]
        merge(f, f"alpha-thing-join-{n}")
        joined(f)
    said, _ = judge(f, short("it still never times out", "the doc"))
    gap = f.item(GID)
    assert said == ["gap.measured", "gap.parked"] and gap["state"] == "parked"
    assert "- it still never times out\n- the doc" in gap["fields"]["where_it_stopped"]
    assert gap["fields"]["parked_in"] == "joined" and "gap/alpha-thing-join-3" not in f.db()["items"]


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
    """A missing coverage file, definition or review: still judged (from the entry and the sub-gaps), each said."""
    (f.model / "run" / "plans" / "alpha-thing.md").unlink()
    (f.model / "run" / "defs" / "alpha-two.md").unlink()
    db = f.db()
    db["items"]["gap/alpha-one"]["fields"]["reviews"] = []
    f.record.write_text(json.dumps(db))
    said, _ = judge(f, COVERED)                                      # still judged, from the entry and the sub-gaps
    assert said == ["gap.merged"]
    text = saved_brief(f)
    assert "(missing: run/plans/alpha-thing.md: FileNotFoundError" in text, text
    assert "(missing: nothing readable at run/defs/alpha-two.md)" in text and "(missing: no review recorded)" in text
    assert "# alpha-one: a plan" in text
