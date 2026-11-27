"""item-metrics-from-the-log (dev/records/item-metrics-from-the-log.md): item counts, transitions and durations kept as
metrics from the item index (ergostat/itemmetrics.py), each minute written once: on a hand-worked record each metric is
the index's count at every minute; ten in and ten out between two samples shows in the counter with the gauge
unchanged; a backfill then live minutes, a refused write and a restart leave no gap and no double count; an item the
index forgets moves to (gone), so a gauge's change is its net transitions; a label with unbounded values is refused;
and the owner's "how long since the last merge" answered by its own query."""

from __future__ import annotations

import json
import textwrap
import uuid
from types import SimpleNamespace

import pytest

from ergostat import itemmetrics as im
from ergostat import model as mdl
from ergostat.spec.itemindex import index_for
from ergostat.store import Project
from ergostat.victoria import Victoria, VictoriaError

T0 = 1_699_999_980.0          # a whole minute
MODEL = """
name: t
projections:
  gap:
    query: key.startswith('gap/')
    fields:
      state:
        values: [open, building, merged]
      cost_usd: {fold: add}
    events:
      gap-found:
        when: type == 'gap.found'
        '...': data
        milestone: "data.milestone if 'milestone' in data else current"
        state: set('open')
      gap-started:
        when: type == 'gap.started'
        '...': data
        milestone: "data.milestone if 'milestone' in data else current"
        state: set('building')
      gap-merged:
        when: type == 'gap.merged'
        '...': data
        milestone: "data.milestone if 'milestone' in data else current"
        state: set('merged')
      other:
        when: true
        '...': data
        milestone: "data.milestone if 'milestone' in data else current"
    relations:
      milestone: {projection: milestone, group: true}
  milestone:
    query: key.startswith('milestone/')
    fields:
      state:
        values: [waiting, active]
    events:
      milestone-added:
        when: type == 'milestone.added'
        '...': data
        state: set('waiting')
      other:
        when: true
        '...': data
"""


class Mem:
    """A store that keeps labels (as VictoriaMetrics does), in memory: every sample written, once."""

    def __init__(self):
        self.s: dict[tuple, dict[float, float]] = {}
        self.fail = False

    def put(self, rows):
        if self.fail:
            raise VictoriaError("VictoriaMetrics at http://127.0.0.1:9: away")
        for labels, t, v in rows:
            pts = self.s.setdefault(tuple(sorted(labels.items())), {})
            assert t not in pts, ("written twice", labels, t)
            pts[t] = v

    def val(self, t: float, name: str, **want) -> float:
        """The sum of the series of ``name`` matching ``want`` (``frm`` for ``from``), at the minute ``t``."""
        want = {("from" if k == "frm" else k): v for k, v in want.items()}
        return sum(p[t] for k, p in self.s.items() if t in p and dict(k)["__name__"] == name
                   and all(dict(k).get(a) == b for a, b in want.items()))

    def minutes(self) -> list[float]:
        return sorted({t for p in self.s.values() for t in p})


def project(tmp_path, text: str = MODEL):
    (tmp_path / "m").mkdir(parents=True)
    (tmp_path / "state").mkdir()
    (tmp_path / "m" / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path / "m")
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    p = Project(m, directory=tmp_path / "state")
    return SimpleNamespace(events=p.events, dir=p.dir, measurements=Mem(), spec=m.spec)


def keep(p, now):
    return im.keep(p, p.spec, now=now)


def index_count(p, m: float, kind: str, state: str) -> int:
    ix = index_for(p.events, p.spec, False)
    return ix.tally(kind, state, "to", m) - ix.tally(kind, state, "from", m)


def index_moves(p, m: float, kind: str, frm, to: str) -> int:
    ix = index_for(p.events, p.spec, False)
    k, f, d = ix.known(kind), ix.known(frm) if frm else None, ix.known(to)
    sql = "select count(*) from moves where kind = ? and dst = ? and t <= ? and " + ("frm is null" if f is None else "frm = ?")
    return ix.db.execute(sql, (k, d, m) if f is None else (k, d, m, f)).fetchone()[0]


@pytest.fixture
def rec(tmp_path):
    """The hand-worked record: three gaps in two milestones, their moves and costs, at known seconds."""
    p = project(tmp_path)
    ev = p.events
    ev.add("gap.found", item="gap/a", source="intake", data={"milestone": "milestone/m1"}, at=T0 + 10)
    ev.add("gap.found", item="gap/b", source="intake", data={"milestone": "milestone/m1"}, at=T0 + 20)
    ev.add("gap.started", item="gap/a", source="builder", at=T0 + 70)
    ev.add("gap.found", item="gap/c", source="intake", data={"milestone": "milestone/m2"}, at=T0 + 90)
    ev.add("gap.costed", item="gap/c", source="builder", data={"cost_usd": 0.5}, at=T0 + 95)
    ev.add("gap.started", item="gap/b", source="builder", at=T0 + 130)
    ev.add("gap.costed", item="gap/c", source="builder", data={"cost_usd": 0.25}, at=T0 + 150)
    ev.add("gap.merged", item="gap/a", source="queue", at=T0 + 200)
    return p


def test_on_a_hand_worked_record_each_metric_is_the_index_count_at_every_minute(rec):
    """Done item 1."""
    st = keep(rec, T0 + 250)
    s = rec.measurements
    m1, m2, m3, m4 = (T0 + 60 * i for i in (1, 2, 3, 4))
    assert s.minutes() == [m1, m2, m3, m4] and st["minute"] == m4 and st["backfill"]["from"] == m1
    by_hand = {   # minute: (open m1, open m2, building m1, merged m1, new>open, open>building, building>merged)
        m1: (2, 0, 0, 0, 2, 0, 0), m2: (1, 1, 1, 0, 3, 1, 0), m3: (0, 1, 2, 0, 3, 2, 0), m4: (0, 1, 1, 1, 3, 2, 1)}
    for m, (o1, o2, b1, g1, new, ob, bm) in by_hand.items():
        assert [s.val(m, im.ITEMS, kind="gap", state="open", milestone="milestone/m1"),
                s.val(m, im.ITEMS, kind="gap", state="open", milestone="milestone/m2"),
                s.val(m, im.ITEMS, kind="gap", state="building", milestone="milestone/m1"),
                s.val(m, im.ITEMS, kind="gap", state="merged", milestone="milestone/m1"),
                s.val(m, im.TRANS, kind="gap", frm=im.NEW, to="open"),
                s.val(m, im.TRANS, kind="gap", frm="open", to="building"),
                s.val(m, im.TRANS, kind="gap", frm="building", to="merged")] == [o1, o2, b1, g1, new, ob, bm], m
        for state in ("open", "building", "merged"):                        # and the index's own count, each minute
            assert s.val(m, im.ITEMS, kind="gap", state=state) == index_count(rec, m, "gap", state), (m, state)
        for frm, to in ((None, "open"), ("open", "building"), ("building", "merged")):
            assert s.val(m, im.TRANS, kind="gap", frm=frm or im.NEW, to=to) == index_moves(rec, m, "gap", frm, to)
    # the stays, observed as each left open (a: 60 s, b: 110 s) and building (a: 130 s)
    assert [s.val(m2, im.STAY + "_bucket", kind="gap", state="open", le=le) for le in ("60", "300", "+Inf")] == [1, 1, 1]
    assert [s.val(m3, im.STAY + "_bucket", kind="gap", state="open", le=le) for le in ("60", "300", "+Inf")] == [1, 2, 2]
    assert (s.val(m3, im.STAY + "_sum", kind="gap", state="open"), s.val(m3, im.STAY + "_count", kind="gap", state="open")) == (170, 2)
    assert s.val(m4, im.STAY + "_bucket", kind="gap", state="building", le="60") == 0
    assert s.val(m4, im.STAY + "_bucket", kind="gap", state="building", le="300") == 1
    assert s.val(m3, im.STAY + "_count", kind="gap", state="building") == 0            # b is still building: not seen
    assert [s.val(m, im.LAST, kind="gap", frm="open", to="building") for m in (m2, m3)] == [T0 + 70, T0 + 130]
    assert [s.val(m, im.FIELD, kind="gap", field="cost_usd") for m in (m1, m2, m3)] == [0, 0.5, 0.75]
    assert [s.val(m, im.EVENTS, type="gap.found", source="intake") for m in (m1, m2)] == [2, 3]
    assert [s.val(m, im.EVENTS, type="gap.started", source="builder") for m in (m1, m2, m3, m4)] == [0, 1, 2, 2]
    for labels in s.s:                                    # no id, ever: only the bounded labels, and no series label
        assert set(dict(labels)) <= im.LABELS | {"__name__"}
        assert not any(str(v).startswith("gap/") for v in dict(labels).values())
    assert "observed when they leave it" in im.HELP[im.STAY] and "stuck work" in im.HELP[im.STAY]


def test_ten_in_and_ten_out_between_two_samples_shows_in_the_counter_not_the_gauge(tmp_path):
    """Done item 2."""
    p = project(tmp_path)
    for i in range(10):
        p.events.add("gap.found", item=f"gap/old{i}", at=T0 + 1 + i)
    keep(p, T0 + 60)
    for i in range(10):                                   # between T0+60 and T0+120: ten arrive, the ten before leave
        p.events.add("gap.found", item=f"gap/new{i}", at=T0 + 70 + i)
        p.events.add("gap.started", item=f"gap/old{i}", at=T0 + 80 + i)
    keep(p, T0 + 120)
    s, a, b = p.measurements, T0 + 60, T0 + 120
    assert s.val(a, im.ITEMS, kind="gap", state="open") == s.val(b, im.ITEMS, kind="gap", state="open") == 10
    into = s.val(b, im.TRANS, kind="gap", to="open") - s.val(a, im.TRANS, kind="gap", to="open")
    out = s.val(b, im.TRANS, kind="gap", frm="open") - s.val(a, im.TRANS, kind="gap", frm="open")
    assert (into, out) == (10, 10)
    assert s.val(b, im.ITEMS, kind="gap", state="open") - s.val(a, im.ITEMS, kind="gap", state="open") == into - out


def _every_minute_once(s: Mem) -> None:
    """No gap: each series written at every minute from its first to the last; no double count: put asserts once."""
    end = max(s.minutes())
    for k, pts in s.s.items():
        ts = sorted(pts)
        assert ts == [ts[0] + 60 * i for i in range(int((end - ts[0]) / 60) + 1)], k


def test_a_backfill_then_live_minutes_a_refused_write_and_a_restart_leave_no_gap_or_double_count(rec, tmp_path):
    """Done item 3: the minutes written over four runs (one refused, one after a restart) are those one run from the
    start would write, each once; an event stamped before the last minute written counts at the next."""
    keep(rec, T0 + 130)                                   # the backfill: up to T0+120
    rec.events.add("gap.found", item="gap/d", source="intake", at=T0 + 300)
    rec.measurements.fail = True
    with pytest.raises(VictoriaError):
        keep(rec, T0 + 310)                              # refused: the checkpoint stays at T0+120
    assert json.loads((rec.dir / im.STATE).read_text())["minute"] == T0 + 120
    rec.measurements.fail = False
    keep(rec, T0 + 310)
    late = rec.events.add("gap.found", item="gap/late", source="intake", at=T0 + 100)   # (before the last minute)
    assert late
    again = SimpleNamespace(**vars(rec))                  # a restart: nothing kept in memory, the checkpoint read
    assert keep(again, T0 + 300)["minute"] == T0 + 300    # (nothing new to write)
    keep(again, T0 + 430)
    s = rec.measurements
    _every_minute_once(s)
    assert s.minutes()[0] == T0 + 60 and s.minutes()[-1] == T0 + 420
    ref = {}
    for name, until, now in (("before", late["seq"] - 1, T0 + 300), ("after", late["seq"], T0 + 430)):
        one = project(tmp_path / name)                    # the same record, in one run from the start
        for e in rec.events.query(n=None, before_seq=until + 1):
            one.events.add(e["type"], item=e["item"], source=e["source"], data=e["data"], at=e["time"])
        keep(one, now)
        ref[name] = one.measurements.s
    for k, pts in s.s.items():                            # what was written before the late event came is the record
        for t, v in pts.items():                          # as it was then; from the next minute, as it is now
            assert v == ref["before" if t <= T0 + 300 else "after"][k][t], (k, t)
    assert s.val(T0 + 420, im.TRANS, kind="gap", frm=im.NEW, to="open") == 5
    assert s.val(T0 + 300, im.TRANS, kind="gap", frm=im.NEW, to="open") == 4      # written before it came
    assert s.val(T0 + 360, im.TRANS, kind="gap", frm=im.NEW, to="open") == 5      # the next minute: once


def test_an_item_the_index_forgets_moves_to_gone_and_the_counters_never_fall(tmp_path):
    """The amendment: a prune's forgotten items are a move to (gone); their moves stay counted (carried), so each
    gauge's change is its net transitions; a backfill says what it cannot recover."""
    p = project(tmp_path)
    for i in range(4):
        p.events.add("gap.found", item=f"gap/old{i}", at=T0 + 1 + i)
    p.events.add("gap.started", item="gap/old0", at=T0 + 30)
    p.events.add("gap.found", item="gap/kept", at=T0 + 200)
    keep(p, T0 + 240)
    assert p.events.prune(T0 + 100) == 5                  # the four old gaps' events: forgotten whole
    p.events.add("gap.started", item="gap/kept", at=T0 + 250)
    keep(p, T0 + 300)
    s, a, b = p.measurements, T0 + 240, T0 + 300
    _every_minute_once(s)                                 # (a gauge's series its items left stays, at none)
    for name in (im.TRANS, im.EVENTS, im.STAY + "_count"):
        for k, pts in s.s.items():
            if dict(k)["__name__"] == name and a in pts:
                assert pts[b] >= pts[a], k                 # carried: no counter falls
    assert s.val(b, im.TRANS, kind="gap", frm="open", to=im.GONE) == 3
    assert s.val(b, im.TRANS, kind="gap", frm="building", to=im.GONE) == 1
    assert s.val(b, im.LAST, kind="gap", to=im.GONE) > T0 + 240
    for state in ("open", "building"):
        d = s.val(b, im.ITEMS, kind="gap", state=state) - s.val(a, im.ITEMS, kind="gap", state=state)
        net = (s.val(b, im.TRANS, kind="gap", to=state) - s.val(a, im.TRANS, kind="gap", to=state)) - (
            s.val(b, im.TRANS, kind="gap", frm=state) - s.val(a, im.TRANS, kind="gap", frm=state))
        assert d == net, state
    fresh = SimpleNamespace(**{**vars(p), "measurements": Mem(), "dir": tmp_path / "again"})
    fresh.dir.mkdir()
    st = keep(fresh, T0 + 300)                            # a backfill now: the record was pruned before it
    assert "pruned" in st["backfill"]["not recovered"]


@pytest.mark.parametrize("cause", ["a kind edited", "a new layout", "a damaged file"])
def test_an_index_made_again_after_a_prune_holds_every_counter(tmp_path, monkeypatch, cause):
    """Round 2: what the index carried for items it forgot is in no index made again, so each counter is held at what
    was written and goes on from there: none falls, and the next move counts once."""
    p = project(tmp_path)
    for i in range(4):
        p.events.add("gap.found", item=f"gap/old{i}", source="intake", data={"cost_usd": 1.0}, at=T0 + 1 + i)
    p.events.add("gap.started", item="gap/old0", source="builder", at=T0 + 30)
    p.events.add("gap.found", item="gap/kept", source="intake", at=T0 + 200)
    keep(p, T0 + 240)
    assert p.events.prune(T0 + 100) == 5
    keep(p, T0 + 300)                                     # the four old gaps carried: (gone)
    before = index_for(p.events, p.spec, False).db.execute("select value from meta where key = 'epoch'").fetchone()
    if cause == "a kind edited":
        (tmp_path / "m" / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace("[open, building, merged]",
                                                                                     "[open, building, merged, parked]"))
        p = SimpleNamespace(**{**vars(p), "spec": mdl.load(tmp_path / "m").spec})
    elif cause == "a new layout":
        from ergostat.spec import itemindex
        monkeypatch.setattr(itemindex, "VERSION", itemindex.VERSION + 1)
    else:
        index_for(p.events, p.spec, False)._heal(RuntimeError("a damaged file"))
    ix = index_for(p.events, p.spec, False)
    assert ix.db.execute("select value from meta where key = 'epoch'").fetchone() != before      # made again
    assert ix.db.execute("select count(*) from carried").fetchone()[0] == 0                    # without the carry
    p.events.add("gap.started", item="gap/kept", source="builder", at=T0 + 310)
    keep(p, T0 + 360)
    s, a, b = p.measurements, T0 + 300, T0 + 360
    _every_minute_once(s)
    for k, pts in s.s.items():
        if dict(k)["__name__"] != im.ITEMS:
            assert pts[b] >= pts[a], k                     # no counter falls, no last-move time goes back
    assert s.val(a, im.TRANS, kind="gap", frm=im.NEW, to="open") == s.val(b, im.TRANS, kind="gap", frm=im.NEW, to="open") == 5
    assert [s.val(m, im.TRANS, kind="gap", frm="open", to="building") for m in (a, b)] == [1, 2]   # the next move: once
    assert [s.val(m, im.EVENTS, type="gap.started", source="builder") for m in (a, b)] == [1, 2]
    assert s.val(b, im.TRANS, kind="gap", to=im.GONE) == 4 and s.val(b, im.FIELD, kind="gap", field="cost_usd") == 4
    assert s.val(b, im.STAY + "_count", kind="gap", state="open") == 2 == s.val(a, im.STAY + "_count", kind="gap", state="open") + 1
    assert s.val(b, im.ITEMS, kind="gap", state="building") == 1 and s.val(b, im.ITEMS, kind="gap", state="open") == 0
    keep(p, T0 + 420)                                     # and on from there, the hold kept
    assert s.val(T0 + 420, im.TRANS, kind="gap", frm="open", to="building") == 2


def test_a_kind_edited_then_undone_reopens_the_old_index_without_counting_twice(tmp_path):
    """Round 3 (lesson 5): after a prune, a kind edited (index B, held up to what A carried) and then undone reopens
    A's own file, with its old epoch and its carry: the hold is worked out afresh there (none needed), so what was
    pruned is counted once, and every counter goes on from what was written."""
    a = project(tmp_path)
    for i in range(4):
        a.events.add("gap.found", item=f"gap/old{i}", source="intake", data={"cost_usd": 1.0}, at=T0 + 1 + i)
    a.events.add("gap.started", item="gap/old0", source="builder", at=T0 + 30)
    a.events.add("gap.found", item="gap/kept", source="intake", at=T0 + 200)
    keep(a, T0 + 240)
    assert a.events.prune(T0 + 100) == 5
    keep(a, T0 + 300)                                     # A carries the four old gaps: (gone)
    epoch = lambda p: index_for(p.events, p.spec, False).db.execute(  # noqa: E731
        "select value from meta where key = 'epoch'").fetchone()[0]
    ea = epoch(a)
    (tmp_path / "m" / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace("[open, building, merged]",
                                                                                 "[open, building, merged, parked]"))
    b = SimpleNamespace(**{**vars(a), "spec": mdl.load(tmp_path / "m").spec})
    assert epoch(b) != ea
    a.events.add("gap.started", item="gap/kept", source="builder", at=T0 + 310)
    keep(b, T0 + 360)                                     # B: held at what A had written
    (tmp_path / "m" / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    back = SimpleNamespace(**{**vars(a), "spec": mdl.load(tmp_path / "m").spec})
    assert epoch(back) == ea                              # A's own file again, its carry in it
    assert index_for(back.events, back.spec, False).db.execute("select count(*) from carried").fetchone()[0] > 0
    a.events.add("gap.merged", item="gap/kept", source="queue", at=T0 + 370)
    keep(back, T0 + 420)
    keep(back, T0 + 480)                                  # and on from there
    s = a.measurements
    _every_minute_once(s)
    for k, pts in s.s.items():
        if dict(k)["__name__"] != im.ITEMS:
            ts = sorted(pts)
            assert all(pts[x] <= pts[y] for x, y in zip(ts, ts[1:], strict=False)), k     # no counter falls
    for m in (T0 + 420, T0 + 480):                        # what was pruned counted once, the moves since once each
        assert s.val(m, im.TRANS, kind="gap", to=im.GONE) == 4, m
        assert s.val(m, im.EVENTS, type="gap.found", source="intake") == 5, m
        assert s.val(m, im.FIELD, kind="gap", field="cost_usd") == 4, m
        assert s.val(m, im.TRANS, kind="gap", frm=im.NEW, to="open") == 5, m
        assert s.val(m, im.TRANS, kind="gap", frm="open", to="building") == 2, m
        assert s.val(m, im.TRANS, kind="gap", frm="building", to="merged") == 1, m
        assert s.val(m, im.EVENTS, type="gap.started", source="builder") == 2, m
        assert s.val(m, im.STAY + "_count", kind="gap", state="open") == 2, m
        assert s.val(m, im.ITEMS, kind="gap", state="merged") == 1 and s.val(m, im.ITEMS, kind="gap", state="building") == 0
    held = json.loads((a.dir / im.STATE).read_text())["held"]
    assert all(x == 0 or n in (im.LAST, im.REBUILT) for n, _, x in held)     # (B4: the rebuilds are held on purpose)
    assert [x for n, _, x in held if n == im.REBUILT] == [2] == [s.val(T0 + 480, im.REBUILT)]


def test_a_refused_write_is_not_tried_again_until_its_wait_is_over(rec):
    """Round 2 (lesson 4): the lead calls it each sweep (5 s); after a fault the next pass waits a minute, then two,
    doubling to an hour; after a pass, the next minute."""
    calls = []
    put = rec.measurements.put
    rec.measurements.put = lambda rows: calls.append(1) or put(rows)
    rec.measurements.fail = True
    said = []
    for dt in range(0, 60, 5):                            # a minute of sweeps: one try, one word
        im.kept(rec, rec.spec, said.append, now=T0 + 250 + dt)
    assert len(calls) == 1 and len(said) == 1 and "tried again in 60 s" in said[0]
    for dt in range(60, 180, 5):                          # the next two minutes: one more try, then a wait of two
        im.kept(rec, rec.spec, said.append, now=T0 + 250 + dt)
    assert len(calls) == 2 and "tried again in 120 s" in said[-1]
    rec.measurements.fail = False
    im.kept(rec, rec.spec, said.append, now=T0 + 250 + 180)
    assert len(calls) == 3 and json.loads((rec.dir / im.STATE).read_text())["minute"] == T0 + 420
    im.kept(rec, rec.spec, said.append, now=T0 + 250 + 185)   # written: not again within the minute
    assert len(calls) == 3 and len(said) == 2
    faults = 40
    im._due[rec.dir] = (faults, 0.0)
    rec.measurements.fail = True
    im.kept(rec, rec.spec, said.append, now=T0 + 600)
    assert f"tried again in {im.MOST_WAIT:.0f} s" in said[-1]   # (a ceiling)


def test_a_field_with_unbounded_values_is_refused_as_a_label(tmp_path):
    """Done item 4: a milestone named by every gap alike is a label; one with a value per gap is refused, its gauge
    summed; and a label that is not one of the bounded ones is never written."""
    p = project(tmp_path)
    for i in range(im.MOST_VALUES + 5):
        p.events.add("gap.found", item=f"gap/g{i}", data={"milestone": f"milestone/m{i}"}, at=T0 + 1)
    st = keep(p, T0 + 60)
    got = [dict(k) for k in p.measurements.s if dict(k)["__name__"] == im.ITEMS]
    assert got == [{"__name__": im.ITEMS, "kind": "gap", "state": "open"}]
    assert p.measurements.val(T0 + 60, im.ITEMS, kind="gap", state="open") == im.MOST_VALUES + 5
    assert st["refused"] == ["gap: milestone"]
    q = project(tmp_path / "few")
    for i in range(6):
        q.events.add("gap.found", item=f"gap/g{i}", data={"milestone": f"milestone/m{i % 2}"}, at=T0 + 1)
    assert keep(q, T0 + 60)["refused"] == []
    assert q.measurements.val(T0 + 60, im.ITEMS, kind="gap", state="open", milestone="milestone/m1") == 3
    for bad in ("id", "item", "branch", "session", "commit"):
        with pytest.raises(im.Refused, match=f"{bad} is never a label"):
            im.Tally().add(im.ITEMS, {"kind": "gap", bad: "x"}, 1)


def _since_last_merge(s: Mem, at: float) -> float:
    """``time() - max(ergostat_item_last_transition_timestamp_seconds{kind="gap",to="merged"})`` at ``at``, as PromQL
    evaluates it: each matching series' latest sample within the five minutes' lookback, their max, from the time."""
    got = [max((t, v) for t, v in p.items() if at - 300 < t <= at)[1] for k, p in s.s.items()
           if dict(k)["__name__"] == im.LAST and dict(k).get("kind") == "gap" and dict(k).get("to") == "merged"
           and any(at - 300 < t <= at for t in p)]
    return at - max(got)


def test_how_long_since_the_last_successful_merge(rec):
    """The owner's query, answered from the metric as written."""
    rec.events.add("gap.found", item="gap/e", at=T0 + 260)
    rec.events.add("gap.started", item="gap/e", at=T0 + 270)
    rec.events.add("gap.merged", item="gap/e", at=T0 + 330)
    keep(rec, T0 + 500)
    assert _since_last_merge(rec.measurements, T0 + 240) == 40           # a merged at T0+200
    assert _since_last_merge(rec.measurements, T0 + 480) == 150          # e merged at T0+330


def test_how_long_since_the_last_merge_in_a_real_victoriametrics(rec, vm):
    v = Victoria(vm, rec.dir, project=f"test-{uuid.uuid4().hex[:10]}")
    rec.measurements = v
    keep(rec, T0 + 250)
    got = v._query(f'time() - max(gap_last_transition_timestamp_seconds{{to="merged",project="{v.project}"}})', T0 + 240)
    assert got and got[0][1] == pytest.approx(40)
    v.drop()


def test_samples_go_to_victoriametrics_under_their_labels_and_stay_out_of_its_series(tmp_path, monkeypatch):
    sent = []
    v = Victoria("http://127.0.0.1:9", tmp_path, project="p1")
    monkeypatch.setattr(v, "_req", lambda path, params=None, body=None: sent.append((path, params, body)) or b"")
    v.put([({"__name__": im.ITEMS, "kind": "gap", "state": "open"}, T0, 3.0),
           ({"__name__": im.ITEMS, "kind": "gap", "state": "open"}, T0 + 60, 4.0)])
    lines = [json.loads(x) for x in sent[0][2].decode().splitlines()]
    assert sent[0][0] == "/api/v1/import" and sent[-1][0] == "/internal/force_flush"
    assert lines == [{"metric": {"__name__": "gap_items", "state": "open", "project": "p1"},   # (the kind's own name)
                      "values": [3.0, 4.0], "timestamps": [T0 * 1000, (T0 + 60) * 1000]}]
    sent.clear()
    monkeypatch.setattr(v, "_req", lambda path, params=None, body=None: sent.append(params) or
                        b'{"status": "success", "data": {"result": []}}')
    v.series()
    assert all('series!=""' in x["query"] for x in sent)  # (the store's own listing reads only its own series)


def test_a_checkpoint_that_cannot_be_read_stops_it_and_a_store_without_labels_is_left_alone(rec):
    (rec.dir / im.STATE).write_text("[]")
    with pytest.raises(ValueError, match="not a checkpoint"):
        keep(rec, T0 + 250)
    (rec.dir / im.STATE).write_text("{")
    said = []
    im.kept(rec, rec.spec, said.append)                   # as the engine calls it: said, never raised
    assert said and "item metrics" in said[0] and not rec.measurements.s
    assert im.keep(SimpleNamespace(**{**vars(rec), "measurements": object()}), rec.spec, now=T0 + 250) is None


def test_lead_time_is_kept_from_arrival_to_each_state_with_buckets_for_seconds(tmp_path):
    """A change request that took 12.4 s from its arrival to prod is in the lead histogram under to="prod", in a
    bucket fine enough to tell seconds apart (the toy factory's steps take seconds, not hours)."""
    t = im.Tally()
    t.move(1, "change-request", 100.0, None, "requested")
    t.move(1, "change-request", 100.2, "requested", "working")
    t.move(1, "change-request", 112.4, "working", "prod")
    def val(name, **lb):
        return sum(x for (n, labels), x in t.v.items() if n == name and all((k, w) in dict(labels).items() for k, w in lb.items()))
    assert val(im.LEAD + "_count", to="prod") == 1 and abs(val(im.LEAD + "_sum", to="prod") - 12.4) < 1e-9
    assert val(im.LEAD + "_bucket", to="prod", le="10") == 0 and val(im.LEAD + "_bucket", to="prod", le="15") == 1
    assert val(im.STAY + "_bucket", state="requested", le="0.25") == 1      # a 0.2 s step is told from a 1 s one
