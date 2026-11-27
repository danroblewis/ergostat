"""The page's addresses per system (SPEC §4f, *Addresses*; docs/roadmap/systems-and-projections.md, step 5): one
segment at a time from the top level, each a dashboard, a projection, ``goals``, ``agents`` or a subsystem; a thing's
deeper address redirects to its top-most; two things at one address of one scope are a collision. Python's helpers
(spec/routes.py) and the page's (web/ui/src/lib/systemRoutes.ts, run with node) answer the same shared cases
(tests/fixtures/route_cases.json)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.spec import SpecError, load, read
from ergostat.spec.routes import href, resolve, shadowed, table
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "tests" / "fixtures" / "route_cases.json").read_text())
MODELS = {m["name"]: m for m in CASES["models"]}


def write(root: Path, files: dict) -> Path:
    for name, text in files.items():
        (root / name).write_text(text)
    return root / "ergostat.yaml"


def table_of(tmp_path, name) -> tuple[dict, list]:
    d = tmp_path / name
    d.mkdir()
    spec, probs = read(write(d, MODELS[name]["files"]))
    other = [p for p in probs if p.level == "error" and p.code != "address-unreachable"]
    assert not other, [str(p) for p in other]
    return table(spec), probs


@pytest.mark.parametrize("name", list(MODELS))
def test_each_shared_case_resolves_and_writes_as_the_fixture_says(tmp_path, name):
    t, _ = table_of(tmp_path, name)
    m = MODELS[name]
    got = [(path, resolve(t, path)) for path, _, _ in m["resolve"]]
    assert got == [(path, want) for path, want, _ in m["resolve"]]
    got = [href(t, thing, scope) for thing, scope, _ in m["href"]]
    assert got == [want for _, _, want in m["href"]]
    assert [[c["scope"], c["segment"], [c["kept"]["kind"], c["kept"]["name"]], [c["lost"]["kind"], c["lost"]["name"]]]
            for c in shadowed(t)] == m["shadowed"]
    assert [[u["kind"], u["name"]] for u in t["unaddressed"]] == m["unaddressed"]


def test_a_shadowed_name_is_a_finding_naming_both_and_a_thing_with_no_address_an_error(tmp_path):
    _, probs = table_of(tmp_path, "order")
    said = [p for p in probs if p.code == "address-shadowed"]
    assert [p.level for p in said] == ["finding", "finding"]
    assert said[0].message == ("address shadowed: /factory/ticket is system ticket in factory, so projection ticket is "
                               "not addressed there; it is at /ticket")
    assert not [p for p in probs if p.level == "error"]
    _, probs = table_of(tmp_path, "unreachable")
    errs = sorted(p.about for p in probs if p.code == "address-unreachable")
    assert errs == ["projection.events", "projection.static", "system.api", "system.goals", "system.review"]
    assert {p.level for p in probs if p.code == "address-unreachable"} == {"error"}
    with pytest.raises(SpecError, match="no address"):
        load(tmp_path / "unreachable" / "ergostat.yaml")


def test_a_remotes_parts_are_named_by_their_short_names_inside_it(tmp_path):
    from tests.test_remote import LOCAL, served_into
    from tests.test_remote import write as rwrite
    local = tmp_path / "support"
    rwrite(local, LOCAL)
    served_into(local, tmp_path)
    spec, probs = read(local / "ergostat.yaml")
    assert not [p for p in probs if p.level == "error"], probs
    t = table(spec)
    assert t["scopes"]["incidents-triage"]["path"] == "/incidents/triage"
    assert resolve(t, "/incidents/response") == {"scope": "incidents-response", "kind": "system",
                                                 "name": "incidents-response"}
    assert href(t, {"kind": "goal", "name": "incidents-few-open"}) == "/incidents/goals/few-open"   # carried up into the remote
    assert resolve(t, "/incidents/goals/few-open")["name"] == "incidents-few-open"
    assert href(t, {"kind": "agent", "name": "incidents-pager"}) == "/incidents/triage/agents/pager"


def test_the_factory_model_has_no_collision_and_every_written_address_reads_back(tmp_path):
    t, probs = table_of(tmp_path, "factory")
    assert not [p for p in probs if p.code.startswith("address-")]
    for thing, scope, want in MODELS["factory"]["href"]:
        if want is None:
            continue
        got = resolve(t, want)
        assert got is not None and "redirect" not in got, (thing, want, got)   # a written address is the top-most
        assert got["kind"] in (thing["kind"], "dashboard") or (thing["kind"], got["kind"]) == ("system", "system")


def test_the_route_table_is_served(tmp_path):
    from ergostat.web import server
    p = write(tmp_path, MODELS["factory"]["files"])
    got = server.api(server.Live(Project(mdl.load(p.parent))), "route-table", {})
    assert got["scopes"]["intake"]["path"] == "/factory/intake"
    assert got["projections"]["ticket"]["in"] == ["factory", "intake", "delivery"]
    assert json.loads(json.dumps(got)) == got


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_pages_helpers_answer_every_shared_case_as_pythons_do(tmp_path):
    """lib/systemRoutes.ts, run by node as it is (type stripping), over the tables Python wrote: the same answers."""
    tables, ask, want = {}, [], []
    for name, m in MODELS.items():
        t, _ = table_of(tmp_path, name)
        tables[name] = t
        for path, expected, _ in m["resolve"]:
            ask.append({"model": name, "path": path})
            want.append(expected)
        for thing, scope, expected in m["href"]:
            ask.append({"model": name, "thing": thing, "scope": scope})
            want.append(expected)
    q = tmp_path / "ask.json"
    q.write_text(json.dumps({"tables": tables, "ask": ask}))
    run = subprocess.run([NODE, "--no-warnings", ROOT / "tests" / "js" / "system_routes.mjs", q], capture_output=True,
                         text=True, timeout=60)
    if run.returncode and "Unknown file extension" in run.stderr:
        pytest.skip(f"node {subprocess.run([NODE, '--version'], capture_output=True, text=True).stdout.strip()} does "
                    "not strip types (22.6 or later does)")
    assert run.returncode == 0, run.stderr
    assert [(a, g) for a, g in zip(ask, json.loads(run.stdout))] == list(zip(ask, want))
