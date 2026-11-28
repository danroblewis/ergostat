"""A projection's graph of states (SPEC §5a, *The list's header*): the moves its items have made, kept by the item
index as they are folded (``steps``), never the declared list with an arrow between neighbours."""

from __future__ import annotations

import random
import sqlite3
import textwrap
from collections import Counter

import pytest

from ergostat import model as mdl
from ergostat.rollup import compact
from ergostat.spec import itemindex
from ergostat.spec import items as its
from ergostat.store import Project

T0 = 1_700_000_000.0


def _cold() -> None:
    """As a process that starts: nothing of the index in memory."""
    for ix in list(itemindex._OPEN.values()):
        ix.close()
    itemindex._OPEN.clear()


STATES = ["made", "checked", "refused", "superseded", "verified", "leased"]


def _branching(tmp_path):
    kinds = "".join(f"""
              {s}:
                when: type == 'change.{s}'
                state: set('{s}')""" for s in STATES[1:])
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(f"""
        projections:
          change:
            query: key.startswith('change/')
            fields:
              state:
                values: [{', '.join(STATES)}]
            finished: [refused, superseded, verified]
            events:{kinds}
              reopened:
                when: type == 'change.reopened'
                state: set('made')
              other:
                when: true
        """))
    return Project(mdl.load(tmp_path))


def _moves(p, kind):
    return {(m["from"], m["to"]): m["n"] for m in its.moves(p.events, p.model.spec, kind)}


def test_a_branch_is_two_moves_from_its_state_and_none_between_its_ends(tmp_path):
    p = _branching(tmp_path)
    for i in range(10):
        p.events.add("change.made", item=f"change/{i}", at=T0 + i)
        p.events.add("change.checked", item=f"change/{i}", at=T0 + 100 + i)
        p.events.add("change.refused" if i < 3 else "change.superseded", item=f"change/{i}", at=T0 + 200 + i)
    p.events.add("change.made", item="change/x", at=T0 + 300)
    got = _moves(p, "change")
    assert got == {(None, "made"): 11, ("made", "checked"): 10, ("checked", "refused"): 3, ("checked", "superseded"): 7}
    assert ("refused", "superseded") not in got and ("superseded", "verified") not in got   # never made: never drawn
    k = next(k for k in its.listing(p.events, p.model.spec, kind="change")["projections"] if k["name"] == "change")
    assert k["moves"][0] == {"from": None, "to": "made", "n": 11}        # the most first, on the listing the header reads
    assert {"refused", "superseded", "verified"} <= set(k["finished"])  # its ends, as the header marks them
    from ergostat.cli.record import moves_line
    assert "checked → superseded 7, checked → refused 3" in moves_line(k["moves"])


def test_the_counts_are_kept_as_moves_are_folded_not_read_from_the_record_per_view(tmp_path):
    p = _branching(tmp_path)
    p.events.add("change.made", item="change/1", at=T0)
    assert _moves(p, "change") == {(None, "made"): 1}
    p.events.add("change.checked", item="change/1", at=T0 + 1)          # followed: only what is new folded
    assert _moves(p, "change") == {(None, "made"): 1, ("made", "checked"): 1}
    ix = itemindex.index_for(p.events, p.model.spec, False)
    with ix.lock:
        seen: list[str] = []
        ix.db.set_trace_callback(seen.append)
        try:
            ix.steps("change")
        finally:
            ix.db.set_trace_callback(None)
    assert seen and not any("from moves" in q for q in seen)            # a page view reads the counts, never the moves


def test_an_index_file_from_before_the_counts_counts_them_once_on_opening(tmp_path):
    p = _branching(tmp_path)
    for i in range(4):
        p.events.add("change.made", item=f"change/{i}", at=T0 + i)
        p.events.add("change.checked", item=f"change/{i}", at=T0 + 10 + i)
    want = _moves(p, "change")
    path = itemindex.index_for(p.events, p.model.spec, False).path
    _cold()
    c = sqlite3.connect(path)
    c.execute("delete from steps")
    c.execute("delete from meta where key = 'steps'")
    c.commit()
    c.close()
    p = Project(mdl.load(tmp_path))
    assert _moves(p, "change") == want


def test_the_kept_counts_equal_the_moves_as_events_arrive_leased_after_rollups_and_rebuilt(tmp_path):
    p = _branching(tmp_path)
    r = random.Random(7)
    types = ["change.checked", "change.refused", "change.superseded", "change.verified", "change.reopened",
             "change.leased", "change.noted"]

    def same():
        ix = itemindex.index_for(p.events, p.model.spec, False)
        ix.catch_up(p.events)
        with ix.lock:
            kept = Counter({(m["from"], m["to"]): m["n"] for m in ix.steps("change")})
            assert kept == +ix.transitions("change")
    t = T0
    for round_ in range(6):                    # each round folded on its own: a lease's hold spans folds
        for _ in range(40):
            t += 1
            p.events.add(r.choice(types), item=f"change/{r.randrange(8)}", at=t)
        same()
    assert any(m["to"] == "made" and m["from"] for m in its.moves(p.events, p.model.spec, "change"))   # reopened
    assert not any("leased" in (m["from"], m["to"]) for m in its.moves(p.events, p.model.spec, "change"))
    compact(p, now=t + p.storage.rollup_after)
    same()
    itemindex.reindex(p.events, p.model.spec)
    same()
