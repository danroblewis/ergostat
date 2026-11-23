"""plan.py's routing of done items an implementor's container cannot do (dev/records/a-definition-s-done-items-the.md):
each item classified at plan time against what a session runs; a measure need recorded as the measure-runs request
its tests satisfy, an owner need parked before the gap is ever ready (so never leased to the implementor)."""

from __future__ import annotations

import pytest

from tests.test_factory_knowledge import PLAN, Instance

pytestmark = pytest.mark.slow


def with_items(b: str, *items: str) -> str:
    return PLAN.format(b=b).replace("It works.", "\n".join(f"{n}. {x}" for n, x in enumerate(items, 1)))


def planned(tmp_path, *items: str) -> tuple[Instance, str, list[str]]:
    f = Instance(tmp_path)
    gid = f.opened()
    said, _ = f.run("plan.py", gid, FACTORY_STANDIN_PLANNER=with_items("alpha-thing", *items))
    return f, gid, said


def definition(f: Instance) -> str:
    return (f.model / "run" / "defs" / "alpha-thing.md").read_text()


def test_a_done_item_needing_a_port_server_is_marked_needs_measure(tmp_path):
    f, gid, said = planned(tmp_path, "The parser reads the file (`uv run python scripts/named_tests.py tests/test_x.py`).",
                           "With `ergostat serve` running on port 8765, the Blocks page draws the loop.")
    g = f.item(gid)
    assert said == ["gap.defined"] and g["state"] == "ready"           # the tests satisfy it: built, then measured
    assert [x["item"] for x in g["fields"]["env_needs"]] == [2] and g["fields"]["env_needs"][0]["needs"] == "measure"
    assert "a server on a port" in g["fields"]["env_needs"][0]["why"]
    assert g["fields"]["measure_runs_wanted"] == {"tests": ["tests/test_x.py::test_unreadable_ledger_refuses"],
                                                 "items": [2]}
    text = definition(f)
    assert "## Needs before building" in text and "- done item 2: `needs: measure`, a server on a port" in text
    assert "done item 1:" not in text
    # with no acceptance test a measure-runs request could run, it is the owner's: parked before building
    untested = with_items("x", "`CORR_SHOTS=1 uv run pytest tests/test_x.py` shows the shots.").replace(
        "- `tests/test_x.py::test_unreadable_ledger_refuses`: fails if it fails open.", "- none")
    got = classify(f, untested)
    assert got == [{"item": 1, "needs": "owner", "why": "an environment variable on a command, and no acceptance test a "
                    "measure-runs request could run"}]


def classify(f: Instance, body: str) -> list[dict]:
    return f.py("import plan; print(json.dumps(plan.env_needs(sys.argv[1])))", body)


def test_a_done_item_needing_files_outside_the_repo_is_a_needs_park_before_building(tmp_path):
    f, gid, said = planned(tmp_path, "The importer reads every model under ~/ergostat-demos/ and checks it.")
    g = f.item(gid)
    assert said == ["gap.parked"] and g["state"] == "parked"           # never ready: the implementor never takes it
    fl = g["fields"]
    assert fl["parked_for"] == "needs" and fl["parked_by"] == "plan-env" and fl["parked_in"] == "plan"
    assert fl["parked_until"]["who"] == "owner" and "input files not in the repository" in fl["parked_until"]["action"]
    assert fl["env_needs"] == [{"item": 1, "needs": "owner", "why": "input files not in the repository"}]
    assert fl["definition"] == "run/defs/alpha-thing.md" and fl["measure_runs_wanted"] is None and fl["env_parked_at"]
    assert "- done item 1: `needs: owner`, input files not in the repository" in definition(f)
    # a continue by hand is refused (no branch was built); the resumer leaves it parked until the need is met
    said = f.py("import fac, manage\ntry:\n    manage.continue_gap(fac.config(), sys.argv[1])\n    print('null')\n"
                "except manage.Refused as e:\n    print(json.dumps(str(e)))", gid)
    assert "parked at plan time" in said and f.drain() == []
    f.tool("parks.py", "resume")
    assert f.drain() == [] and f.item(gid)["state"] == "parked"
    f.fold([{"event": "gap.need-met", "item": gid, "data": {"need_met": "the demos are copied into tests/data"}}], None)
    f.tool("parks.py", "resume")
    assert f.drain() == ["gap.defined", "gap.resumed"] and f.item(gid)["state"] == "ready"
    assert f.item(gid)["fields"]["resumed_as"] == gid
    f.tool("parks.py", "resume")                                       # resumed once: never again
    assert f.drain() == []
    for owner in ("Screenshots of the Blocks page are looked at by a person.", "It runs under Docker --sandbox.",
                  "The seatbelt profile loads on macOS.", "The import reads input files outside the repository.",
                  "It is checked on macOS by hand."):
        assert classify(f, with_items("x", owner))[0]["needs"] == "owner", owner
    # a mention is not a need: docker or macOS named in passing, a path outside the repository that is refused
    for plain in ("The suite container (`docker run --init`) is killed by name; tests/test_x.py starts a fake.",
                  "The sandbox profile keeps macOS's five-entry limit (house rules).",
                  "A path outside the repository is refused, and so is ~/x or /home/y.",
                  "A read of a file not in the repo is rejected with bad-path."):
        assert [x["needs"] for x in classify(f, with_items("x", plain))] in ([], ["measure"]), plain


def test_a_coordinator_definition_with_an_owner_item_is_parked_not_readied(tmp_path):
    body = with_items("alpha-thing", "The importer reads every model under ~/ergostat-demos/ and checks it.")
    f = Instance(tmp_path)
    f.opened()
    f.define(body)                                                     # the intake readies a coordinator's file
    g = f.item("gap/alpha-thing")
    assert g["state"] == "parked" and g["fields"]["parked_by"] == "plan-env" and g["fields"]["env_parked_at"]
    assert g["fields"]["defined_by"] == "coordinator" and g["fields"]["env_needs"][0]["needs"] == "owner"
    assert definition(f) == body                                       # the coordinator's file is left unmarked
    f.run("intake.py")
    assert f.item("gap/alpha-thing")["state"] == "parked"              # never readied on a later pass
    # the planner's own check for a coordinator's file routes it the same way
    p = Instance(tmp_path / "p")
    gid = p.opened()
    (p.model / "run" / "defs").mkdir(parents=True, exist_ok=True)
    (p.model / "run" / "defs" / "alpha-thing.md").write_text(body)
    said, _ = p.run("plan.py", gid)
    assert said == ["gap.parked"] and p.item(gid)["state"] == "parked" and definition(p) == body
    # a measure need only: ready, with the measure-runs request its tests satisfy
    (p.model / "run" / "defs" / "alpha-thing.md").write_text(with_items("x", "It serves on port 8765."))
    p.fold([{"event": "gap.found", "item": "gap/beta", "data": {"branch": "alpha-thing"}}], None)
    said, _ = p.run("plan.py", "gap/beta")
    b = p.item("gap/beta")["fields"]
    assert said == ["gap.defined"] and b["measure_runs_wanted"]["items"] == [1] and b["defined_by"] == "coordinator"


def test_a_plain_pytest_done_item_is_not_marked(tmp_path):
    f, gid, said = planned(tmp_path, "The ledger refuses an unreadable line (tests/test_x.py), "
                           "`uv run python scripts/suite_watch.py -- uv run python scripts/named_tests.py tests/test_x.py`.",
                           "`uv run ruff check ergostat tests scripts` is clean and `git diff --stat` names app.py.",
                           "`uv run python scripts/demo_check.py` passes; `python -m pytest -q tests/test_x.py` too.",
                           "`dev/bin/plan.py` and `needs: owner|measure` are named, not run.")
    g = f.item(gid)
    assert said == ["gap.defined"] and g["state"] == "ready"
    assert g["fields"]["env_needs"] is None and g["fields"]["measure_runs_wanted"] is None
    assert "Needs before building" not in definition(f)
    # a command off the allowlist is a measure need, its tests run by a measure-runs request
    got = classify(f, with_items("x", "`npm run build` makes the bundle.", "`python dev/bin/plan.py lint` passes."))
    assert [x["item"] for x in got] == [1, 2] and {x["needs"] for x in got} == {"measure"}
