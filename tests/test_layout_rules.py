"""The three Blocks rules of tests/layout_rules.py (crossing-without-hop, dot-not-at-takeoff, slash-on-crossing) on
small hand-made geometry, no browser: each finds its fault and passes the drawing that has none. The same rules run
over every example's Blocks views in tests/test_diagram_rendering.py."""
from __future__ import annotations

from tests import layout_rules as LR


def wire(i, pts, net=None):
    return {"id": i, "kind": "signal", "source": "", "target": "", "net": net or i, "pts": [list(p) for p in pts]}


def geo(edges, dots=(), hops=(), slashes=()):
    return {"view": "blocks", "nodes": [], "edges": edges, "dots": [list(d) for d in dots],
            "hops": [{"edge": e, "at": list(at)} for e, at in hops],
            "slashes": [{"edge": e, "at": list(at)} for e, at in slashes]}


CROSS = [wire("a", [(0, 50), (100, 50)]), wire("b", [(50, 0), (50, 100)])]   # a level wire over an upright one
# one signal's two wires: one straight on, one leaving it at (50, 0) and turning down: a take-off at (50, 0)
TAKEOFF = [wire("s1", [(0, 0), (100, 0)], "s"), wire("s2", [(0, 0), (50, 0), (50, 40)], "s")]


def found(g, name):
    return LR.check(g, [name])


def test_a_crossing_needs_a_hop_on_the_level_wire_and_no_dot():
    assert LR.wire_crossings(LR.G(geo(CROSS)))[0][:4] == (50, 50, "a", "b")
    assert len(found(geo(CROSS), "crossing-without-hop")) == 1
    assert found(geo(CROSS, hops=[("a", (50, 50))]), "crossing-without-hop") == []
    assert len(found(geo(CROSS, hops=[("b", (50, 50))]), "crossing-without-hop")) == 1     # on the wrong wire
    assert len(found(geo(CROSS, dots=[(50, 50)], hops=[("a", (50, 50))]), "crossing-without-hop")) == 1


def test_a_line_ending_on_another_is_no_crossing():
    tee = [wire("a", [(0, 50), (100, 50)]), wire("b", [(50, 0), (50, 50)])]
    assert LR.wire_crossings(LR.G(geo(tee))) == []


def test_a_dot_only_where_a_signals_wires_part():
    assert LR.takeoffs(LR.G(geo(TAKEOFF))) == [(50, 0)]
    assert found(geo(TAKEOFF, dots=[(50, 0)]), "dot-not-at-takeoff") == []
    assert len(found(geo(TAKEOFF, dots=[(25, 0)]), "dot-not-at-takeoff")) == 1               # mid-wire, no parting
    assert len(found(geo(CROSS, dots=[(50, 50)]), "dot-not-at-takeoff")) == 1                # two signals crossing


def test_a_vector_slash_at_least_12px_from_any_crossing():
    near = found(geo(CROSS, hops=[("a", (50, 50))], slashes=[("a", (45, 50))]), "slash-on-crossing")
    assert len(near) == 1 and near[0]["score"] == 7
    assert found(geo(CROSS, hops=[("a", (50, 50))], slashes=[("a", (62, 50)), ("b", (50, 85))]), "slash-on-crossing") == []
