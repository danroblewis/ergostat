"""An object's name (SPEC §5a, *An object's name*): a projection's ``name:``, an expression over the folded object's
fields, shown in place of its key; never its identity, never a reason to fold again."""

from __future__ import annotations

import textwrap

import pytest

from ergostat import model as mdl
from ergostat.spec import itemindex
from ergostat.spec import items as its
from ergostat.spec import workbench
from ergostat.store import Project
from ergostat.web.server import Live, api

T0 = 1_700_000_000.0

BODY = """\
projections:
  instance:
    query: type.startswith('vm.')
    key: [region, instance_id]
    name: NAME
    fields:
      region: text
      instance_id: text
      state: {values: [running, stopped]}
      tags: {type: map, fold: merge}
    events:
      up:
        when: type == 'vm.up'
        region: data.region
        instance_id: data.id
        state: "'running'"
      tagged:
        when: type == 'vm.tagged'
        region: data.region
        instance_id: data.id
        tags: data.tags
"""


def project(tmp_path, name: str = "tags.Name or instance_id") -> Project:
    (tmp_path / "ergostat.yaml").write_text(BODY.replace("NAME", name))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [x.message for x in m.problems]
    return Project(m)


def recorded(p: Project) -> None:
    p.events.add("vm.up", data={"region": "eu", "id": "i-1"}, at=T0)
    p.events.add("vm.up", data={"region": "eu", "id": "i-2"}, at=T0 + 1)
    p.events.add("vm.tagged", data={"region": "eu", "id": "i-1", "tags": {"Name": "web-1"}}, at=T0 + 2)


def errors(tmp_path, name: str) -> list[tuple[str, str]]:
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(BODY.replace("NAME", name))
    _, problems = read(tmp_path / "ergostat.yaml", extremes=False)
    return [(x.code, x.message) for x in problems if x.level == "error"]


@pytest.mark.parametrize("bad, says", [
    ("tags.Name or colour", "colour is not one of its fields"),
    ("data.name", "data is not one of its fields"),
    ("tags.(", "does not parse"),
    ("add(1)", "plain expression"),
    ("''", "an expression"),
])
def test_a_bad_name_is_an_error(tmp_path, bad, says):
    got = errors(tmp_path, bad if bad != "''" else "''")
    assert any(c == "bad-display-name" and says in m for c, m in got), got


def test_a_good_name_checks(tmp_path):
    assert errors(tmp_path, "tags.Name or key") == []


def test_the_name_is_evaluated_and_falls_back_to_the_key(tmp_path):
    p = project(tmp_path)
    recorded(p)
    k = p.model.spec.items["instance"]
    one = {i.id: i for i in its.project(p.events, p.model.spec, "instance")}
    assert its.display_name(k, one["eu/i-1"]) == "web-1"
    assert its.display_name(k, one["eu/i-2"]) == "i-2"                     # tags.Name is none: or instance_id
    (tmp_path / "x").mkdir()
    p2 = project(tmp_path / "x", "tags.Name")
    recorded(p2)
    k2 = p2.model.spec.items["instance"]
    two = {i.id: i for i in its.project(p2.events, p2.model.spec, "instance")}
    assert its.display_name(k2, two["eu/i-2"]) is None                      # empty: the key is shown
    (tmp_path / "y").mkdir()
    p3 = project(tmp_path / "y", "instance_id / 2")
    recorded(p3)
    k3 = p3.model.spec.items["instance"]
    three = its.project(p3.events, p3.model.spec, "instance")
    assert all(its.display_name(k3, i) is None for i in three)              # raises: the key is shown


def test_the_api_carries_the_name(tmp_path):
    p = project(tmp_path)
    recorded(p)
    got = api(Live(p), "items", {"projection": ["instance"]})
    names = {i["id"]: i["name"] for i in got["items"]}
    assert names == {"eu/i-1": "web-1", "eu/i-2": "i-2"}
    d = api(Live(p), "items/eu%2Fi-1", {"projection": ["instance"]})
    assert d["id"] == "eu/i-1" and d["name"] == "web-1"
    plain = api(Live(p), "items", {})                                       # the plain list too
    assert {i["id"]: i.get("name") for i in plain["items"]}["eu/i-1"] == "web-1"


def test_the_workbench_names_its_samples(tmp_path):
    p = project(tmp_path)
    recorded(p)
    body = textwrap.dedent(BODY.replace("NAME", "tags.Name or instance_id")).split("instance:\n", 1)[1]
    r = workbench.review(p, {"name": "instance", "yaml": textwrap.dedent(body), "item": "eu/i-1"})
    assert r["ok"], r
    assert r["objects"]["names"] == {"eu/i-1": "web-1", "eu/i-2": "i-2"}
    assert r["timeline"]["name"] == "web-1"


def test_a_name_change_does_not_rebuild_the_index(tmp_path):
    a = project(tmp_path)
    b = project(tmp_path, "key")
    assert itemindex.kinds_key(a.model.spec) == itemindex.kinds_key(b.model.spec)
    assert a.model.spec.items["instance"].definition() == b.model.spec.items["instance"].definition()
