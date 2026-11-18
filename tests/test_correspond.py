"""One selection across the views (ergostat/correspond.py): each shape is the model parts it stands
for, by identity, and each part is stood for by its own shapes, else by the smallest region holding
it; lighting a selection in the other view never cascades to everything it touches."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.correspond import _reaches, inside, system_of, universe
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module", params=["image-squeeze", "software-factory"])
def example(request, tmp_path_factory):
    name = request.param
    d = tmp_path_factory.mktemp(name) / name
    shutil.copytree(ROOT / "examples" / name, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    from ergostat.web.server import Live, api
    live = Live(Project(mdl.load(d)))
    return name, live.get().model.spec, lambda **q: api(live, "graph", {k: [v] for k, v in q.items()})


@pytest.fixture(scope="module")
def squeeze(tmp_path_factory):
    d = tmp_path_factory.mktemp("sq") / "image-squeeze"
    shutil.copytree(ROOT / "examples" / "image-squeeze", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    from ergostat.web.server import Live, api
    live = Live(Project(mdl.load(d)))
    graph = lambda **q: api(live, "graph", {k: [v] for k, v in q.items()})       # noqa: E731
    return live.get().model.spec, graph(view="dynamics", open="*")["corr"], graph(view="blocks", open="*")["corr"], graph


def lit(corr: dict, sel: set[str]) -> set[str]:
    """What a view lights for a selection, as the page does (interact.js): the shapes standing for each
    part chosen, and every shape all of whose parts are chosen."""
    out = {s for p in sel for s in corr["parts"].get(p, [])}
    return out | {s for s, x in corr["shapes"].items() if x["is"] and set(x["is"]) <= sel}


def chosen(corr: dict, shape: str) -> set[str]:
    return set(corr["shapes"][shape]["is"])


def views(spec):
    yield {}, None
    yield {"open": "*"}, None
    yield {"open": "-"}, None
    for s in spec.systems:
        yield {"open": s}, None
        yield {}, s


def drawn_within(g: dict, ids: list[str], focus: str, spec) -> bool:
    """Whether any of these shapes, as drawn with everything open, is in the system drawn alone."""
    nodes = {n["id"]: n for n in g["nodes"]}
    for i in ids:
        n = nodes.get(i)
        if n is None:
            continue
        where = n.get("system") if g["kind"] == "blocks" else (n.get("systems") or [None])[0]
        if focus in spec.chain(where):
            return True
    return False


def test_every_part_in_scope_is_stood_for_by_a_shape_in_every_view(example):
    """A part drawn in the whole system (its own shape, or a region that is not a system's outline) is
    stood for in every view of it: everything open or closed, a system opened, a system drawn alone."""
    name, spec, graph = example
    for view in ("dynamics", "blocks"):
        whole = graph(view=view, open="*")
        held_by_region = {p for p, ids in whole["corr"]["parts"].items()
                          if any(not i.startswith(("frame:", "hull:")) for i in ids)}
        for q, focus in views(spec):
            g = graph(view=view, **q, **({"system": focus} if focus else {}))
            where = f"{name} {view} {q} system={focus}"
            for p in universe(spec):
                if focus:
                    if p == f"system.{focus}" or p not in held_by_region or \
                            not drawn_within(whole, whole["corr"]["parts"][p], focus, spec):
                        continue                  # the whole canvas, or drawn outside the system drawn alone
                assert g["corr"]["parts"].get(p), (where, p)
            ids = {n["id"] for n in g["nodes"]} | {f"frame:{f['label']}" for f in g.get("frames") or []} | \
                {f"hull:{s}" for s in g.get("open") or []}
            for p, shapes in g["corr"]["parts"].items():
                assert set(shapes) <= ids, (where, p, set(shapes) - ids)


def test_no_shape_is_more_than_its_rule_allows(example):
    name, spec, graph = example
    for view in ("dynamics", "blocks"):
        for q, focus in views(spec):
            g = graph(view=view, **q, **({"system": focus} if focus else {}))
            nodes = {n["id"]: n for n in g["nodes"]}
            for sid, x in g["corr"]["shapes"].items():
                kind, _, rest = sid.partition(":")
                where = f"{name} {view} {q} {focus} {sid}: {x['is']}"
                if x.get("region"):                       # only these hold what is in them
                    assert kind in ("system", "hull", "sys", "frame", "proc", "psum", "mux", "demux"), where
                    if kind == "psum":
                        st = rest.split(".", 1)[1]
                        assert set(x["is"]) == {rest, *(f"flow.{f.name}" for f in spec.flows_of(st))}, where
                    if kind in ("sys", "system", "frame", "hull"):     # what the model puts in it, and what is drawn in it
                        system = nodes[sid]["label"] if sid in nodes else rest
                        extra = set(x["is"]) - set(inside(spec, system))   # what is drawn in it from elsewhere: a goal
                        assert set(inside(spec, system)) <= set(x["is"]), where   # placed with its reader, a valve's block
                        assert not any(p.startswith("system.") for p in extra), (where, extra)
                    continue
                if view == "dynamics":
                    assert len(x["is"]) <= 1, where       # a stock, a flow, a desired level, a gap, a decision
                elif kind == "sum":
                    assert set(x["is"]) == {f"goal.{rest}", f"goal.{rest}.r"}, where
                elif kind in ("ref", "out", "dist", "sen", "proc", "term"):
                    assert len(x["is"]) == 1, where
                elif kind in ("blk", "smp", "zoh", "jsum"):
                    b = rest.split(":")[0]
                    moves = {f"{t.kind}.{t.name}" for t in spec.blocks[b].targets() if t.kind in ("flow", "auxiliary")}
                    sets = {f"goal.{t.name}.r" for t in spec.blocks[b].targets() if t.kind == "goal"}
                    extra = set(x["is"]) - {f"block.{b}"} - moves - sets
                    assert f"block.{b}" in x["is"] and len(extra) <= 1 and all(e.startswith("stock.") for e in extra), where
                elif kind == "gen":
                    st = rest.split(".", 1)[1]
                    assert set(x["is"]) <= {f"flow.{f.name}" for f in spec.flows_of(st)}, where


def test_the_stated_cases_on_image_squeeze_all_open(squeeze):
    spec, dyn, blk, graph = squeeze
    # a stock's process sum: the stock and its flows, and nothing else, in the other view
    sel = chosen(blk, "psum:stock.capabilities")
    assert sel == {"stock.capabilities", "flow.gained", "flow.lost"}
    assert lit(dyn, sel) == {"stock:capabilities", "flow:gained", "flow:lost"}
    # a goal's comparator: the desired level and the gap
    assert lit(dyn, chosen(blk, "sum:every-case")) == {"desired:every-case", "gap:every-case"}
    # the reference input: the desired level alone
    assert lit(dyn, chosen(blk, "ref:every-case")) == {"desired:every-case"}
    # a controller, and its sampler, hold and junction: the valve it opens (and the setting it steps)
    for s in ("blk:tuner", "smp:tuner", "zoh:tuner", "jsum:tuner"):
        assert lit(dyn, chosen(blk, s)) == {"flow:quality-steps", "stock:quality-setting"}, s
    assert lit(blk, {"flow.quality-steps"}) == {"blk:tuner", "smp:tuner", "zoh:tuner", "jsum:tuner"}
    # an integrator and its output y: the stock
    assert lit(dyn, chosen(blk, "proc:stock.capabilities")) == {"stock:capabilities"}
    assert lit(dyn, chosen(blk, "out:stock.capabilities")) == {"stock:capabilities"}
    assert lit(blk, {"stock.capabilities"}) == {"proc:stock.capabilities", "out:stock.capabilities", "sen:stock.capabilities"}
    # a disturbance input: its flow
    assert lit(dyn, chosen(blk, "dist:flow.lost")) == {"flow:lost"}
    # the multi-input multi-output process of service: every part inside it, a region
    sel = chosen(blk, "proc:service")
    assert blk["shapes"]["proc:service"].get("region") and 10 <= len(sel) <= 20
    assert {"flow.quality-turnover", "auxiliary.batch-quality", "stock.quality"} <= sel
    assert all(spec.owner(__import__("ergostat.spec.ir", fromlist=["Ref"]).Ref(*p.split(".", 1))) == "service" for p in sel)
    # a part with no shape of its own in blocks: its containing shape, and the page says so
    assert blk["parts"]["flow.quality-turnover"] == ["proc:service"]
    assert blk["inside"]["flow.quality-turnover"] == ["P_service"]
    assert "flow.quality-turnover" not in dyn["inside"]
    # a closed system's Q block and module box: the whole system
    for view, box in (("blocks", "sys:lab"), ("dynamics", "system:lab")):
        c = graph(view=view, open="-")["corr"]
        assert set(c["shapes"][box]["is"]) >= set(inside(spec, "lab")), view     # (and goals compared there)
        assert c["parts"]["system.lab"] == [box] and c["parts"]["stock.ideas"] == [box]


def test_no_cascade_a_shape_lights_only_what_it_is(squeeze):
    """Every shape that is not a region lights, in the other view, at most a few shapes for each part it
    is (a part drawn twice, a shadow), never its neighbours; and choosing one dynamics part lights in
    blocks only shapes that are that part, or hold it."""
    spec, dyn, blk, _ = squeeze
    for here, there in ((blk, dyn), (dyn, blk)):
        for sid, x in here["shapes"].items():
            if x.get("region"):
                continue
            got = lit(there, set(x["is"]))
            reach = sum(len(_reaches(spec, p[6:])) for p in x["is"] if p.startswith("block."))
            groups = {re.sub(r"^(smp|zoh|jsum):([^:]+).*$", r"blk:\2", s) for s in got}   # a controller drawn with its T, ZOH, Σ
            groups = {re.sub(r"^sen:", "out:", s) for s in groups}          # a variable's output y and its sensor H on it
            assert len(groups) <= 2 * max(1, len(x["is"])) + reach, (sid, x["is"], got)
            for s in got:                             # each is what it lights, or stands for a block chosen
                stand_in = any(s in there["parts"].get(p, []) and set(there["shapes"][s]["is"]) <= set(_reaches(spec, p[6:]))
                               for p in x["is"] if p.startswith("block.")) or \
                    any(s in there["parts"].get(p, []) and str(spec.goals[p.split(".")[1]].of) in there["shapes"][s]["is"]
                        for p in x["is"] if p.startswith("goal."))    # a goal nothing acts on: by what it is about
                assert set(there["shapes"][s]["is"]) & set(x["is"]) or stand_in, (sid, s)
    total = len(dyn["shapes"])
    for sid in blk["shapes"]:
        if sid.startswith("psum:"):
            assert len(lit(dyn, chosen(blk, sid))) <= 6 < total / 4, sid


def test_a_loop_is_its_members_as_parts(squeeze):
    spec, dyn, blk, _ = squeeze
    for name, ps in dyn["loops"].items():
        assert ps and all(p.split(".", 1)[0] in ("stock", "flow", "auxiliary", "goal", "block") for p in ps), name
    assert set(blk["loops"]["every-case"]) >= {"goal.every-case", "goal.every-case.r", "stock.capabilities"}
    assert lit(dyn, set(blk["loops"]["every-case"])) >= {"gap:every-case", "desired:every-case", "stock:capabilities"}


def test_the_wiring_draws_each_agent_as_the_blocks_it_fills(example):
    name, spec, graph = example
    g = graph(view="wiring")
    for n in g["nodes"]:
        agent = n["id"].split(":", 1)[1]
        want = {f"block.{b}" for b, x in spec.blocks.items() if b == agent or x.agent == agent}
        assert set(g["corr"]["shapes"][n["id"]]["is"]) == want, n["id"]
    assert system_of(spec, f"system.{next(iter(spec.systems))}") in (None, *spec.systems)


def test_each_part_has_one_colour_in_every_view_and_parts_drawn_together_differ(example):
    """Colour by correspondence (colours.js): each part's palette slot is the same whatever view or systems
    are drawn; parts that touch (a flow and its stocks, a goal and its reference) get different hues, and
    the parts one block diagram shape is (a controller: its block, its valves, its setting) different slots;
    a closed system's box and an open one's outline say which system they are."""
    from ergostat.correspond import HUES, STEPS
    _name, spec, graph = example
    first = graph(view="dynamics", open="*")["corr"]["colours"]
    assert set(first) == set(universe(spec)) and all(0 <= i < HUES * STEPS for i in first.values())
    for view in ("dynamics", "blocks"):
        for q, _ in views(spec):
            assert graph(view=view, **q)["corr"]["colours"] == first, (view, q)
    for f in spec.flows.values():
        for x in (f.source, f.target):
            if x and f"stock.{x}" in first:
                assert first[f"flow.{f.name}"] % HUES != first[f"stock.{x}"] % HUES, (f.name, x)
    for g in spec.goals:
        assert first[f"goal.{g}"] % HUES != first[f"goal.{g}.r"] % HUES
    blocks = graph(view="blocks", open="*")["corr"]
    for sid, x in blocks["shapes"].items():
        if sid.startswith("blk:"):
            slots = [first[p] for p in x["is"]]
            assert len(set(slots)) == len(slots), (sid, x["is"], slots)
    shut = graph(view="dynamics", open="-")["corr"]["shapes"]
    assert {x["system"] for x in shut.values() if x.get("system")} == {s for s in spec.systems if not spec.within.get(s)}
    frames = {x["system"] for sid, x in blocks["shapes"].items() if sid.startswith("frame:")}
    assert frames and frames <= set(spec.systems)
