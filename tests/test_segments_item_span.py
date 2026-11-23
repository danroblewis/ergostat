"""A query by item over a record of several sealed segments: segments without the item are ruled out
before their types are tested (perf-segments-item-span-first), and the answer is what it was."""

from __future__ import annotations

import random

from ergostat import segments as seg_mod
from ergostat.segments import Segments
from ergostat.store import Events

T = 1_700_000_000.0
TYPES = ["a.x", "a.y", "b.z", "valve.opened", "agent.ran"]


def _record(tmp_path):
    """The same events in the segmented log (12 sealed segments and a head) and in SQLite (the old answer:
    the conformance suite holds the two to the same behaviour). Each item lives in a window of the log, so
    most segments do not hold it."""
    rnd = random.Random(7)
    evs = []
    for i in range(500):
        k = rnd.random()
        item = None if k < 0.05 else "loose" if k < 0.1 else f"w/{rnd.randrange(i // 6, i // 6 + 5)}"
        evs.append({"id": f"e{i:04d}", "type": rnd.choice(TYPES), "item": item, "at": T + i, "data": {"i": i}})
    (tmp_path / "sql").mkdir()
    sg, sq = Segments(tmp_path / "seg", seal=40), Events(tmp_path / "sql")
    sg.add_many(evs)
    sq.add_many(evs)
    assert len(sg._segs) >= 12
    return sg, sq, sorted({e["item"] for e in evs if e["item"] and "/" in e["item"]})


def _ids(rows):
    return [(e["id"], e["type"], e["item"], e["time"]) for e in rows]


def test_query_by_item_gives_the_old_answer(tmp_path):
    sg, sq, items = _record(tmp_path)
    rnd = random.Random(11)
    asks = [{}, {"type": "a.x"}, {"type": "a.*,agent.ran"}, {"skip": ("b.z",)}, {"type": "a.*", "skip": ("a.y",)},
            {"type": "none.such"}, {"n": 3}, {"n": 3, "type": "a.*"}, {"first": 2, "skip": ("a.x",)},
            {"since": T + 100, "until": T + 300, "type": "valve.opened,a.y"}, {"after_seq": 150, "before_seq": 420}]
    picked = rnd.sample(items, 50)
    assert all(sg.query(n=None, item=it) for it in picked)
    for it in picked:
        for a in asks:
            a = {"n": None, **a}
            assert _ids(sg.query(item=it, **a)) == _ids(sq.query(item=it, **a)), (it, a)


def test_segments_without_the_item_are_not_type_tested(tmp_path):
    sg, _, items = _record(tmp_path)
    sealed = [it for it in items if any(s.span(it) for s in sg._segs)]
    for it in random.Random(3).sample(sealed, 50):
        calls: list[str] = []

        def counting(t, calls=calls):
            calls.append(t)
            return t.startswith("a.")
        holding = [s for s in sg._segs if s.span(it) is not None]
        assert 0 < len(holding) < len(sg._segs)
        got = [r for s in sg._segs for r in sg._rows(s, it, counting)]
        assert len(calls) == sum(len(s.types) for s in holding), it    # only the segments holding it
        assert sum(len(sg._rows(s, it, None)) for s in sg._segs) == sum(s.span(it)[1] for s in holding)
        assert len(got) <= sum(s.span(it)[1] for s in holding)


def test_a_query_by_item_type_tests_only_the_segments_holding_it(tmp_path, monkeypatch):
    """Through ``query``: the matcher it makes is called for the head's types and the holding segments' only."""
    sg, sq, items = _record(tmp_path)
    made = seg_mod._types_matcher
    calls: list[str] = []

    def counting_matcher(type, skip):
        test = made(type, skip)
        return lambda t: calls.append(t) or test(t)
    monkeypatch.setattr(seg_mod, "_types_matcher", counting_matcher)
    it = items[len(items) // 3]
    got = sg.query(n=None, item=it, skip=("b.z",))
    holding = [s for s in sg._segs if s.span(it) is not None]
    assert len(calls) == sum(len(s.types) for s in holding) + len(sg._head.by_type)
    assert _ids(got) == _ids(sq.query(n=None, item=it, skip=("b.z",)))
