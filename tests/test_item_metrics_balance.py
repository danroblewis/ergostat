"""item-metrics-that-balance (dev/records/item-metrics-that-balance.md, catalog item B4): arrivals (from "(new)") and
items the index forgets (to "(gone)") are transitions, so between any two minutes written each gauge's change is its
net transitions (``itemmetrics.balance``), checked on a hand-worked record across a milestone change, a prune and a
late event; a kind whose state label is refused keeps its two edges and balances as a whole; across an index made
again no balance is claimed (``ergostat_item_index_rebuilds_total``); and a gauge that does not balance is said and
never made up by a flow of its own (G18)."""

from __future__ import annotations

import json
import textwrap
from itertools import combinations
from types import SimpleNamespace

from ergostat import itemmetrics as im
from ergostat import model as mdl
from tests.test_item_metrics import MODEL, T0, Mem, project

M = [T0 + 60 * i for i in range(1, 6)]               # the minutes written: T0+60 ... T0+300


def keep(p, now, say=None):
    return im.keep(p, p.spec, now=now, say=say)


def at(s: Mem, t: float) -> dict:
    """The values written at minute ``t``, as ``balance`` takes them: ``{(name, labels): value}``."""
    return {(dict(k)["__name__"], tuple((a, b) for a, b in k if a != "__name__")): p[t] for k, p in s.s.items() if t in p}


def row(b: dict, state) -> tuple:
    r = next(r for r in b["rows"] if r["kind"] == "gap" and r["state"] == state)
    return r["change"], r["net"]


def record(tmp_path):
    """The hand-worked record. z arrives and is started, then forgotten by a prune; a, b and c are found, started and
    merged at known seconds; b changes milestone while building; d is stamped before the last minute written."""
    p = project(tmp_path)
    ev = p.events
    ev.add("gap.found", item="gap/z", source="intake", at=T0 + 5)
    ev.add("gap.started", item="gap/z", source="builder", at=T0 + 30)
    ev.add("gap.found", item="gap/a", source="intake", data={"milestone": "milestone/m1"}, at=T0 + 10)
    ev.add("gap.found", item="gap/b", source="intake", data={"milestone": "milestone/m1"}, at=T0 + 20)
    ev.add("gap.started", item="gap/a", source="builder", at=T0 + 70)
    ev.add("gap.found", item="gap/c", source="intake", data={"milestone": "milestone/m2"}, at=T0 + 110)
    ev.add("gap.started", item="gap/b", source="builder", at=T0 + 130)
    ev.add("gap.noted", item="gap/b", source="builder", data={"milestone": "milestone/m2"}, at=T0 + 150)
    ev.add("gap.merged", item="gap/a", source="queue", at=T0 + 200)
    keep(p, T0 + 250)                                 # minutes T0+60 to T0+240
    assert p.events.prune(T0 + 100) == 2              # z: forgotten whole (a move to (gone))
    ev.add("gap.found", item="gap/d", source="intake", at=T0 + 230)     # late: before the last minute written
    ev.add("gap.started", item="gap/c", source="builder", at=T0 + 260)
    return p


def test_on_a_hand_worked_record_each_gauge_change_is_its_net_transitions(tmp_path):
    """Done item 1: worked by hand, then every pair of minutes written balances, state by state and the kind whole."""
    p = record(tmp_path)
    said = []
    st = keep(p, T0 + 310, said.append)              # the minute T0+300
    s = p.measurements
    assert s.minutes() == M
    by_hand = {   # minute: (open, building, merged, arrivals, gone)
        M[0]: (2, 1, 0, 3, 0), M[1]: (2, 2, 0, 4, 0), M[2]: (1, 3, 0, 4, 0), M[3]: (1, 2, 1, 4, 0), M[4]: (1, 2, 1, 5, 1)}
    for m, (o, b, g, new, gone) in by_hand.items():
        assert [s.val(m, im.ITEMS, kind="gap", state=x) for x in ("open", "building", "merged")] == [o, b, g], m
        assert s.val(m, im.TRANS, kind="gap", frm=im.NEW) == new and s.val(m, im.TRANS, kind="gap", to=im.GONE) == gone
        assert o + b + g == new - gone, m             # the stock is what came in less what went out, from the start
        for x in ("open", "building", "merged"):      # and each state's, its moves in less its moves out
            assert s.val(m, im.ITEMS, kind="gap", state=x) == (
                s.val(m, im.TRANS, kind="gap", to=x) - s.val(m, im.TRANS, kind="gap", frm=x)), (m, x)
    assert s.val(M[2], im.ITEMS, kind="gap", state="building", milestone="milestone/m2") == 1   # b moved milestone
    whole = im.balance(at(s, M[0]), at(s, M[4]))      # from the first minute to the last, by hand:
    assert whole["verdict"] == "balanced"
    assert row(whole, "open") == (-1, -1)             # in: c, d; out: a, b, c
    assert row(whole, "building") == (1, 1)           # in: a, b, c; out: a to merged, z to (gone)
    assert row(whole, "merged") == (1, 1)
    assert row(whole, None) == (1, 1)                 # the kind: arrivals c, d less z forgotten
    for x, y in combinations(M, 2):
        assert im.balance(at(s, x), at(s, y))["verdict"] == "balanced", (x, y)
    assert st["balance"] == {"from": M[3], "to": M[4], "checked": 4, "verdict": "balanced", "residuals": []}
    assert not said


def test_a_kind_whose_state_label_is_refused_keeps_its_edges_and_balances_whole(tmp_path, monkeypatch):
    """Done item 2 (the cardinality guard, G24, tried on states): past the limit the state label is left out, but
    "(new)" and "(gone)" are kept, so arrivals and forgotten items are still counted and the kind still balances."""
    monkeypatch.setattr(im, "MOST_VALUES", 2)          # (three states: past it)
    p = record(tmp_path)
    st = keep(p, T0 + 310)
    s = p.measurements
    assert "gap: state" in st["refused"]
    assert {dict(k).get("state") for k in s.s if dict(k)["__name__"] == im.ITEMS} == {None}
    assert {(dict(k).get("from"), dict(k).get("to")) for k in s.s if dict(k)["__name__"] == im.TRANS} == {
        (im.NEW, None), (None, None), (None, im.GONE)}
    assert [s.val(M[4], im.TRANS, kind="gap", frm=im.NEW), s.val(M[4], im.TRANS, kind="gap", to=im.GONE)] == [5, 1]
    b = im.balance(at(s, M[0]), at(s, M[4]))
    assert b["verdict"] == "balanced" and [r["state"] for r in b["rows"]] == [None] and row(b, None) == (1, 1)
    assert st["balance"]["verdict"] == "balanced"


def test_across_an_index_made_again_no_balance_is_claimed(tmp_path):
    """Done items 3 and 4: a kind edited makes the index again, its gauge counted afresh while each counter is held, so
    its change need not be its net transitions; the rebuild is counted, and the balance across it is "unsure" (not
    "balanced", not "unbalanced"); from the next pass it balances again."""
    p = record(tmp_path)
    keep(p, T0 + 310)
    (tmp_path / "m" / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace("open", "queued"))
    q = SimpleNamespace(**{**vars(p), "spec": mdl.load(tmp_path / "m").spec})
    st = keep(q, T0 + 370)
    s = q.measurements
    assert [s.val(m, im.REBUILT) for m in (T0 + 300, T0 + 360)] == [0, 1]
    assert s.val(T0 + 360, im.ITEMS, kind="gap", state="queued") == 1 and s.val(T0 + 360, im.ITEMS, kind="gap", state="open") == 0
    assert s.val(T0 + 360, im.TRANS, kind="gap", to="queued") == 4      # counted afresh: no move made these
    naive = {k: v for k, v in at(s, T0 + 360).items() if k[0] != im.REBUILT}
    assert im.balance(at(s, T0 + 300), naive)["verdict"] == "unbalanced"   # what it would say, unmarked
    assert st["balance"]["verdict"] == "unsure" and "made again" in st["balance"]["why"]
    assert im.balance(at(s, T0 + 300), at(s, T0 + 360))["verdict"] == "unsure"
    q.events.add("gap.started", item="gap/d", source="builder", at=T0 + 380)
    st = keep(q, T0 + 430)
    assert s.val(T0 + 420, im.REBUILT) == 1 and st["balance"]["verdict"] == "balanced"
    assert row(im.balance(at(s, T0 + 360), at(s, T0 + 420)), "queued") == (-1, -1)
    assert im.balance({}, at(s, T0 + 420))["verdict"] == "unsure"          # nothing before: not owed


def test_a_gauge_that_does_not_balance_is_said_and_never_made_up_by_a_flow(tmp_path):
    """G18 tried: a written gauge one too high (as a defect would leave it) is reported with its residual, by state
    and for the kind; no series is added and no counter moves to close it."""
    p = record(tmp_path)
    path = p.dir / im.STATE
    cp = json.loads(path.read_text())
    r = next(r for r in cp["written"] if r[0] == im.ITEMS and ["state", "open"] in r[1] and ["milestone", "milestone/m2"] in r[1])
    r[2] += 1                                         # (c's series: one item, written as two)
    path.write_text(json.dumps(cp))
    said = []
    st = keep(p, T0 + 310, said.append)
    assert st["balance"]["verdict"] == "unbalanced"
    assert st["balance"]["residuals"] == [{"kind": "gap", "state": "open", "change": -1.0, "net": 0.0},
                                          {"kind": "gap", "state": None, "change": -1.0, "net": 0.0}]
    assert len(said) == 1 and "not its net transitions" in said[0] and "gap open -1 against +0" in said[0]
    s = p.measurements
    names = {dict(k)["__name__"] for k in s.s}
    assert names == {im.ITEMS, im.TRANS, im.LAST, im.STAY + "_bucket", im.STAY + "_sum", im.STAY + "_count",
                     im.EVENTS, im.REBUILT}            # (no flow of its own)
    assert {s.val(m, im.REBUILT) for m in M} == {0}
    assert [s.val(M[4], im.TRANS, kind="gap", frm=im.NEW), s.val(M[4], im.TRANS, kind="gap", to=im.GONE)] == [5, 1]
