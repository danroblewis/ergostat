"""A template's exports (SPEC §2a): exports: names the parts the rest of a model may read; a reference from outside an
instance to one it does not export is a finding (template-internal-reference) at the referring line; inside the
instance, or an instance within it, references are free; no exports: means every part is exported."""

import json
import textwrap
from pathlib import Path

import pytest

from ergostat.library import author
from ergostat.library import templates as tp
from ergostat.spec import read

TANK = """
template: tank
description: a level kept under a limit
{exports}
stocks:
  level: {{unit: u, sensor: {{run: echo 1}}}}
  spare: {{unit: u, sensor: {{run: echo 2}}}}
flows:
  out: {{from: spare}}
goals:
  low: {{stock: spare, hold: "<= 5"}}
"""

PLANT = """
template: plant
description: a tank inside
{exports}
stocks:
  feed: {{unit: u, sensor: {{run: echo 3}}}}
goals:
  inner: {{stock: "${{name}}-in-spare", hold: "<= 9"}}
uses:
  in:
    use: tank
"""


def project(tmp_path: Path, main: str, tank: str = "exports: [stock.level]", plant: str = "") -> Path:
    lib = tmp_path / "lib"
    lib.mkdir(exist_ok=True)
    (lib / "tank.yaml").write_text(TANK.format(exports=tank))
    (lib / "plant.yaml").write_text(PLANT.format(exports=plant))
    (tmp_path / "ergostat.yaml").write_text("name: t\nlibrary: lib\n" + textwrap.dedent(main))
    return tmp_path / "ergostat.yaml"


def internal(path: Path) -> list:
    _, ps = read(path)
    assert not [p for p in ps if p.level == "error"], ps
    return [p for p in ps if p.code == "template-internal-reference"]


def owner_goal(stock: str) -> str:
    return f"""
        uses:
          t:
            use: tank
        goals:
          mine:
            stock: {stock}
            hold: "<= 3"
        """


def test_exports_must_name_own_parts(tmp_path):
    f = tmp_path / "x.yaml"
    for bad, why in (("[stock.nope]", "stock.nope"), ("[goal.level]", "goal.level"), ("[items.level]", "items.level"),
                     ("stock.level", "a list")):
        f.write_text(TANK.format(exports=f"exports: {bad}"))
        with pytest.raises(tp.TemplateError, match=why):
            tp.read(f, False, "owner")
    f.write_text(TANK.format(exports="exports: [stock.level, goal.low, flow.out]"))
    assert tp.read(f, False, "owner").exports == ["stock.level", "goal.low", "flow.out"]
    f.write_text(PLANT.format(exports="exports: [stock.in-level, stock.feed]"))    # an inner use's part, by its local name
    assert tp.read(f, False, "owner").exports == ["stock.in-level", "stock.feed"]
    long = "a" * 65
    f.write_text(TANK.format(exports=f"exports: [stock.{long}]").replace("  level:", f"  {long}:"))
    assert tp.read(f, False, "owner").exports == [f"stock.{long}"]
    with pytest.raises(tp.TemplateError, match="not a ref"):     # an untrusted template's names are SAFE ones
        tp.read(f, False, "untrusted")


def test_reference_to_internal_part_is_finding(tmp_path):
    path = project(tmp_path, owner_goal("t-spare"))
    got = internal(path)
    assert len(got) == 1, got
    line = path.read_text().splitlines().index("    stock: t-spare") + 1          # the referring line
    assert got[0].level == "finding" and got[0].where.file == path and got[0].where.line == line
    assert got[0].message == ("goal.mine: stock.t-spare is internal to instance t (template tank exports: stock.level); "
                              "name one of its exports instead")
    assert internal(project(tmp_path, owner_goal("t-level"))) == []


def test_reference_within_instance_free(tmp_path):
    # tank's own goal and flow read its internal spare: neither is a finding
    assert internal(project(tmp_path, "uses:\n  t:\n    use: tank\n")) == []
    # the inner tank's own parts read the outer plant's internal feed: inside plant, so free
    inner = TANK.format(exports="exports: [stock.level]").replace("from: spare", "from: spare, driven-by: [stock.p-feed]")
    path = project(tmp_path, "uses:\n  p:\n    use: plant\n", plant="exports: []", tank="")
    (tmp_path / "lib" / "tank.yaml").write_text(inner)
    assert [p.message.split(" is internal")[0] for p in internal(path)] == ["goal.p-inner: stock.p-in-spare"]
    # plant's own goal reads its inner tank's spare: plant holds both, but the goal is outside the inner instance, and
    # tank keeps spare internal, so it is a finding, whatever plant exports
    for plant in ("", "exports: [stock.feed]"):
        got = internal(project(tmp_path, "uses:\n  p:\n    use: plant\n", plant=plant))
        assert [p.message.split(" is internal")[0] for p in got] == ["goal.p-inner: stock.p-in-spare"]
        assert "instance p-in (template tank" in got[0].message
    assert internal(project(tmp_path, "uses:\n  p:\n    use: plant\n", tank="")) == []


def test_reexport_reaches_outside_only_when_the_outer_exports_it(tmp_path):
    def mine(path):                       # (plant's own goal on its inner spare is a finding of its own, above)
        return [p for p in internal(path) if p.message.startswith("goal.mine:")]
    main = owner_goal("p-in-level").replace("t:\n            use: tank", "p:\n            use: plant")
    assert mine(project(tmp_path, main)) == []                                      # no exports: every part
    assert mine(project(tmp_path, main, plant="exports: [stock.in-level]")) == []   # re-exported
    got = mine(project(tmp_path, main, plant="exports: [stock.feed]"))
    assert [(p.message.split(" is internal")[0], "instance p " in p.message) for p in got] == [("goal.mine: stock.p-in-level", True)]
    got = mine(project(tmp_path, main.replace("p-in-level", "p-in-spare"), plant="exports: [stock.in-spare]"))
    assert ["instance p-in " in p.message for p in got] == [True]          # re-exported, but tank keeps it internal


def test_no_exports_means_all(tmp_path):
    assert internal(project(tmp_path, owner_goal("t-spare"), tank="")) == []
    # exports: [] exports nothing
    got = internal(project(tmp_path, owner_goal("t-level"), tank="exports: []"))
    assert len(got) == 1 and "exports: nothing" in got[0].message
    # a part named wholly by a parameter is the owner's name: never internal
    named = TANK.format(exports="params:\n  it: {type: name, default: thing}\nexports: []").replace("  spare:", "  ${it}:")
    path = project(tmp_path, owner_goal("thing"), tank="")
    (tmp_path / "lib" / "tank.yaml").write_text(named.replace("from: spare", "from: thing").replace("stock: spare", "stock: thing"))
    assert internal(path) == []
    assert len(internal(project(tmp_path, owner_goal("thing").replace("thing", "t-level"), tank="exports: []"))) == 1


def test_templates_tool_shows_exports(tmp_path):
    from ergostat.mcp import Server
    shown = json.loads(Server(tmp_path).call("templates", {"name": "respond-to"})["content"][0]["text"])
    assert shown["exports"] == ["stock.waiting", "auxiliary.oldest", "flow.arriving", "flow.answered", "goal.on-time"]
    assert "exports" not in author.library(None, "collect")                  # none declared: none shown
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "tank.yaml").write_text(TANK.format(exports="exports: [stock.level]"))
    (tmp_path / "ergostat.yaml").write_text("name: t\nlibrary: [{folder: lib}]\n")
    got = author.library(tmp_path, "tank")
    assert got["untrusted"] and got["exports"] == '\u27e6untrusted: template tank\u27e7["stock.level"]\u27e6end of untrusted\u27e7'


EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLOSED = [n for n, t in tp.find_all()[0].items() if t.builtin and t.exports is not None]


# (only an instance whose template declares exports can give the finding: the examples whose main file uses one)
@pytest.mark.parametrize("example", sorted(p.parent.name for p in EXAMPLES.glob("*/ergostat.yaml")
                                           if any(f"use: {n}\n" in p.read_text() for n in CLOSED)))
@pytest.mark.slow
def test_no_example_reads_an_internal_part(example):
    _, ps = read(EXAMPLES / example / "ergostat.yaml")
    assert [p for p in ps if p.code == "template-internal-reference"] == []


def test_respond_to_exports_its_loop_and_hides_its_fast_loop(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        name: t
        uses:
          q:
            use: respond-to
        goals:
          seen:
            auxiliary: q-oldest
            hold: "<= 1"
        blocks:
          watch:
            type: person
            goal: q-picked-up
            ask: look
        """))
    got = internal(tmp_path / "ergostat.yaml")
    assert [p.message.split(" is internal")[0] for p in got] == ["block.watch: goal.q-picked-up"]
