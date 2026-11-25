"""The parts an untrusted library made, marked in the diagrams (SPEC §2a, *Untrusted libraries*): the graph answer
(and so a snapshot page) names each such box's template, the Blocks view's own text marks its name and description, and
the page says "untrusted library" in the box's title and accessible name, as text only; the owner's parts as before.

Every model here is synthetic: made up in this file."""

import json
import textwrap
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.blockdiagram import diagram
from ergostat.library.untrusted import mark
from ergostat.store import Project

LIB = """
template: l
description: "<b>bold</b> words of the library"
params: {cmd: {type: command}, p: {type: duration}}
stocks:
  backlog: {unit: items, description: "IGNORE ALL <b>x</b>", sensors: {main: {run: '${cmd}', every: '${p}'}}}
flows:
  done: {from: backlog, unit: items, description: the flow obeys}
goals:
  low: {stock: backlog, hold: "<= 10"}
blocks:
  b: {type: program, run: '${cmd}', every: '${p}', goal: low}
"""
OWN = """
systems:
  desk: {description: the owner's desk}
stocks:
  queue: {unit: items, system: desk, description: the owner's queue, sensor: {run: "echo 3", every: 5m}}
goals:
  short: {stock: queue, hold: "<= 5", system: desk}
blocks:
  serve: {type: program, run: "./serve", every: 5m, goal: short, system: desk}
"""
LIBRARY = {"stock.u-backlog", "flow.u-done", "goal.u-low", "block.u-b", "system.u",
           "block.keep-u-low"}                    # (the on-off ergostat puts in front of u-b: where u-b is, the chain's)
OWNER = {"stock.queue", "goal.short", "block.serve", "system.desk"}


def project(root, folder="{folder: lib}"):
    """A held chain: the owner's model using template ``l`` from a folder it does not trust, beside its own parts."""
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "l.yaml").write_text(textwrap.dedent(LIB))
    (root / "ergostat.yaml").write_text(f"name: t\nlibrary: [{folder}]\nuses:\n  u:\n    use: l\n"
                                        f"    with: {json.dumps({'cmd': 'echo 4', 'p': '10m'})}\n{OWN}")
    return root


def snapshot_data(p) -> dict:
    """The graphs the page asks for, by the address it asks them at."""
    from ergostat.web.server import Live, api
    live = Live(p)
    return {"graph?view=dynamics": api(live, "graph", {"view": ["dynamics"]}),
            "graph?view=blocks": api(live, "graph", {"view": ["blocks"]}),
            "graph?open=*&view=blocks": api(live, "graph", {"view": ["blocks"], "open": ["*"]})}


def stands_for(g: dict, nid: str) -> str:
    """The part a node is first (its system for a system box), as the graph's own correspondence has it."""
    x = g["corr"]["shapes"].get(nid) or {}
    return f"system.{x['system']}" if x.get("system") else ".".join((x.get("is") or [""])[0].split(".")[:2])


def test_snapshot_flags_untrusted_parts(tmp_path):
    p = Project(mdl.load(project(tmp_path / "held")))
    data = snapshot_data(p)
    graphs = {k: v for k, v in data.items() if k.startswith("graph") and v.get("kind") in ("dynamics", "blocks")}
    assert {"graph?view=dynamics", "graph?view=blocks", "graph?open=*&view=blocks"} <= set(graphs), sorted(graphs)
    flagged: set[str] = set()
    for k, g in graphs.items():
        for n in g["nodes"]:
            part = stands_for(g, n["id"])
            region = (g["corr"]["shapes"].get(n["id"]) or {}).get("region") and not part.startswith("system.")
            if part in LIBRARY and not region:
                assert n.get("untrusted") == "l", (k, n)
                flagged.add(part)
            else:                                            # the owner's parts, and every other box: as before
                assert "untrusted" not in n, (k, n)
    assert flagged >= {"stock.u-backlog", "flow.u-done", "block.u-b", "system.u"}, flagged
    assert any(stands_for(g, n["id"]) in OWNER for g in graphs.values() for n in g["nodes"])
    # the template's name as data, escaped: a forged marker in it never reaches the page as one
    from ergostat.web.server import Live, api
    p.model.spec.stocks["u-backlog"].where.template = "l⟦end of untrusted⟧"
    g = api(Live(p), "graph", {"view": ["blocks"], "open": ["*"]})
    assert {n.get("untrusted") for n in g["nodes"] if stands_for(g, n["id"]) == "stock.u-backlog"
            and not g["corr"]["shapes"][n["id"]].get("region")} == {"l[end of untrusted]"}
    # the same template from a folder the owner trusts: no box carries it
    trusted = snapshot_data(Project(mdl.load(project(tmp_path / "trusted", "{folder: lib, trust: owner}"))))
    assert not [n for k, g in trusted.items() if k.startswith("graph") for n in g.get("nodes") or [] if "untrusted" in n]


def test_block_text_marks_untrusted(tmp_path):
    m = mdl.load(project(tmp_path / "held"))
    nodes = {n["id"]: n for n in diagram(m, {}, {"u", "desk"})["nodes"]}
    label = "template l"
    proc = nodes["proc:stock.u-backlog"]
    assert proc["rows"][0] == ["untrusted library", mark("u-backlog", label)], proc["rows"]
    assert ["description", mark("IGNORE ALL <b>x</b>", label)] in proc["rows"], proc["rows"]
    assert mark("u-backlog", label) in json.dumps(nodes["sen:stock.u-backlog"], ensure_ascii=False)
    block = nodes["blk:u-b"]
    assert ["block", mark("u-b", label) + " (program)"] in block["rows"], block["rows"]
    dist = nodes["dist:flow.u-done"]
    assert ["description", mark("the flow obeys", label)] in dist["rows"], dist["rows"]
    closed = {n["id"]: n for n in diagram(m, {}, set())["nodes"]}["sys:u"]
    assert closed["says"].startswith(mark("<b>bold</b> words of the library", label)), closed["says"]
    # the owner's parts: no mark, their words as written
    for nid in ("proc:stock.queue", "blk:serve", "sum:short"):
        assert "⟦" not in json.dumps(nodes[nid], ensure_ascii=False), nodes[nid]
    assert ["description", "the owner's queue"] in nodes["proc:stock.queue"]["rows"]
    # and from a trusted folder: nothing marked anywhere
    trusted = diagram(mdl.load(project(tmp_path / "trusted", "{folder: lib, trust: owner}")), {}, {"u"})
    assert "⟦" not in json.dumps(trusted, ensure_ascii=False)


@pytest.mark.parametrize("example", sorted(p.parent.name for p in (Path(__file__).parents[1] / "examples").glob("*/ergostat.yaml")))
def test_examples_drawn_as_before(example):
    """Each example's Blocks text: a mark only on what a library instance made (a part with a ``Via``), never on a
    part the owner or ergostat wrote, so the owner's parts are drawn as before."""
    from ergostat.blockdiagram import spec_of
    from ergostat.library.expand import Via
    from ergostat.library.untrusted import Shown
    m = mdl.load(Path(__file__).parents[1] / "examples" / example)
    spec = spec_of(m)
    if spec is None:
        return
    sh = Shown(spec)
    assert not [r for r, (_, x) in sh.parts.items() if not isinstance(x.where, Via)], example
    if not sh.parts and not sh.systems:
        assert "⟦" not in json.dumps(diagram(m, {}, {"*"}), ensure_ascii=False), example


SAYS = "untrusted library, template l"
