"""One conformance suite for every backend of the two stores (Orchestra's design: tests/bus and
tests/metrics there): each event backend and each measurement backend is held to the same
behaviour. SQLite and the segmented log always run (the log with tiny segments, so every test
crosses sealed segments and the head); VictoriaMetrics runs when ERGOSTAT_TEST_VM_URL is set
(``victoria-metrics -storageDataPath DIR -httpListenAddr 127.0.0.1:8428``), each test under its own
project label."""

from __future__ import annotations

import multiprocessing
import os
import threading
import uuid

import pytest

from ergostat.segments import Segments
from ergostat.store import ChangesetError, Events, Measurements

T = 1_700_000_000.0


def _events(kind: str, d):
    if kind == "sqlite":
        return Events(d)
    return Segments(d, seal=7)


@pytest.fixture(params=["sqlite", "segments"])
def ev(request, tmp_path):
    e = _events(request.param, tmp_path)
    e.kind = request.param
    return e


def test_order_n_newest_and_filters(ev):
    for i in range(20):
        ev.add("a.x" if i % 2 else "b.y", item=f"t/{i % 3}", source="m/1" if i % 4 else "m", data={"i": i}, at=T + i)
    allv = ev.query(n=None)
    assert [e["data"]["i"] for e in allv] == list(range(20))
    assert [e["seq"] for e in allv] == sorted(e["seq"] for e in allv) and len({e["seq"] for e in allv}) == 20
    assert [e["data"]["i"] for e in ev.query(n=3)] == [17, 18, 19]
    assert [e["data"]["i"] for e in ev.query(n=None, type="a.*")] == list(range(1, 20, 2))
    assert [e["data"]["i"] for e in ev.query(n=None, type="a.x,b.y", item="t/0")] == [0, 3, 6, 9, 12, 15, 18]
    assert [e["data"]["i"] for e in ev.query(n=2, type="b.*", item="t/1")] == [10, 16]
    assert [e["data"]["i"] for e in ev.query(n=None, since=T + 5, until=T + 8)] == [5, 6, 7, 8]
    assert [e["data"]["i"] for e in ev.query(n=None, skip=("a.x",))] == list(range(0, 20, 2))
    assert [e["data"]["i"] for e in ev.query(n=None, machine="m", type="b.*")] == list(range(0, 20, 2))
    assert [e["data"]["i"] for e in ev.query(n=None, source="m")] == [0, 4, 8, 12, 16]
    s5 = allv[5]["seq"]
    assert [e["data"]["i"] for e in ev.query(n=None, after_seq=s5)] == list(range(6, 20))
    assert [e["data"]["i"] for e in ev.query(n=2, before_seq=s5)] == [3, 4]
    assert ev.count() == 20 and ev.first_time() == T and ev.last_seq() == allv[-1]["seq"]


def test_a_transcripts_lines_skipped_by_prefix(ev):
    ev.add("t.x", item="s/1", data={"a": 1}, at=T)
    ev.add_many([{"type": "claude.message", "item": "s/1", "data": {"messages": "hi"}, "at": T + i, "id": f"l{i}"} for i in range(5)])
    ev.add("claudette", item="s/1", at=T + 9)
    assert [e["type"] for e in ev.query(n=None, skip=("claude.*",))] == ["t.x", "claudette"]
    assert [e["type"] for e in ev.of_items(skip=("claude.*",))] == ["t.x", "claudette"]
    assert ev.counted("claude.*") == {"s/1": (5, T + 4)}
    assert ev.add_many([{"type": "claude.message", "item": "s/1", "id": "l1", "at": T}, {"type": "claude.x", "item": "s/1", "id": "l9"},
                        {"type": "claude.x", "item": "s/1", "id": "l9"}]) == 1
    assert ev.known(["l0", "l9", "nope"]) == {"l0", "l9"}


def test_ids_get_prefix_dedup_and_causes(ev):
    a = ev.add("x", id="abc123" + "0" * 26, at=T)
    assert a["seq"] and ev.add("x", id=a["id"])["seq"] is None and ev.count() == 1
    b = ev.add("y", causedby=a["id"], at=T + 1)
    for i in range(10):
        ev.add("z", at=T + 2 + i)
    assert ev.get(a["id"])["type"] == "x" and ev.get("abc12")["id"] == a["id"] and ev.get("nope") is None
    assert [e["id"] for e in ev.caused_by(a["id"])] == [b["id"]]


def test_changesets_carried_and_refused(ev):
    ev.add("t.p", item="t/1", patch=[{"op": "add", "path": "/a", "value": 1}], at=T)
    ev.add("t.s", item="t/1", set={"b": "ü" * 3, "big": "x" * 200_000}, at=T + 1)
    got = ev.query(n=None, item="t/1")
    assert got[0]["patch"] == [{"op": "add", "path": "/a", "value": 1}] and got[1]["set"]["b"] == "üüü"
    assert len(got[1]["set"]["big"]) == 200_000 and "set" not in got[0]
    with pytest.raises(ChangesetError):
        ev.add("t.p", item="t/1", data={"a": 1}, set={"b": 1})
    with pytest.raises(ChangesetError):
        ev.add("t.p", item="part", set={"b": 1})


def test_items_of_items_and_globs(ev):
    for i in range(12):
        ev.add("k.x", item=f"{'pr' if i % 2 else 'issue'}/{i % 4}", at=T + i)
    ev.add("agent.ran", item="someone", at=T + 50)
    rows = {r["item"]: r for r in ev.items()}
    assert set(rows) == {"pr/1", "pr/3", "issue/0", "issue/2"} and rows["pr/3"]["n"] == 3 and rows["pr/3"]["first"] == T + 3
    assert rows["pr/3"]["last"] == T + 11 and rows["pr/3"]["latest"] == "k.x"
    assert "someone" in {r["item"] for r in ev.items(own=True)}
    assert {e["item"] for e in ev.of_items(["pr/*"])} == {"pr/1", "pr/3"}
    assert len(ev.of_items(until=T + 5)) == 6
    s = ev.of_items()[7]["seq"]
    assert len(ev.of_items(after_seq=s)) == 4
    assert [e["seq"] for e in ev.of_items(limit=5)] == [e["seq"] for e in ev.of_items()][:5]
    assert [e["seq"] for e in ev.of_items(after_seq=s, limit=2)] == [e["seq"] for e in ev.of_items(after_seq=s)][:2]


def test_valves_controllers_and_runs(ev):
    run = ev.add("agent.ran", item="a", data={"refused": 2, "unread": 1}, at=T)
    ev.add("agent.ran", item="a", data={"why": "by hand", "refused": 5}, at=T + 1)
    ev.add("agent.failed", item="a", at=T + 2)
    ev.add("valve.opened", item="v", data={"amount": 2}, at=T + 3)
    ev.add("valve.opened", item="v", data={"amount": 3}, causedby=run["id"], at=T + 4)
    ev.add("valve.opened", item="v", causedby=run["id"], at=T + 5)
    ev.add("controller.decided", item="c", data={"decision": "up"}, at=T + 6)
    ev.add("controller.decided", item="c", data={"decision": "up"}, at=T + 7)
    ev.add("controller.decided", item="c", data={"decision": "hold"}, at=T + 8)
    assert ev.runs("a", T, T + 10) == {"runs": 3, "failed": 1, "refused": 2, "unread": 1}
    assert ev.opened("v", T, T + 10) == {"count": 3, "amount": 6.0, "last": T + 5}
    assert ev.last_opening("v") == {"time": T + 5, "count": 2, "amount": 4.0}
    assert ev.last_opening("v", until=T + 3.5) == {"time": T + 3, "count": 1, "amount": 2.0}
    assert sorted(ev.decided("c", T, T + 10)) == [("hold", 1), ("up", 2)]


def test_unvoided(ev):
    a = ev.add("loop.off", item="g", at=T)
    ev.add("loop.holding", item="g", at=T + 1)
    ev.add("ergostat.forgotten", data={"voids": [a["id"]]}, at=T + 2)
    assert [e["type"] for e in ev.query(n=None, item="g", type="loop.*", unvoided=True)] == ["loop.holding"]


def test_prune_and_generation(ev):
    g = ev.generation()
    ev.add("model.changed", at=T)
    ev.add("loop.off", item="g", at=T + 1)
    ev.add("loop.holding", item="g", at=T + 2)
    ev.add("agent.ran", item="a", at=T + 3)
    ev.add("t.x", item="t/old", at=T + 4)
    ev.add("t.x", item="t/live", at=T + 5)
    ev.add("t.x", item="t/live", at=T + 500)
    for i in range(8):
        ev.add("noise", at=T + 600 + i)
    assert ev.prune(T + 100) == 3
    assert [e["type"] for e in ev.query(n=None) if e["type"] != "noise"] == ["model.changed", "loop.holding", "t.x", "t.x"]
    assert ev.generation() != g


def test_replace_puts_the_snapshot_where_the_last_one_was(ev):
    for i in range(10):
        ev.add("t.x", item="t/1" if i < 6 else "t/2", data={"i": i}, at=T + i)
    olds = [e["seq"] for e in ev.query(n=None, item="t/1")][:4]
    g = ev.generation()
    ev.replace([("t/1", olds, {"id": "snap", "type": "ergostat.item.snapshot", "time": T + 3, "source": "ergostat",
                              "data": {"rollup": {"n": 4}}, "set": {"i": 3}})])
    got = ev.query(n=None, item="t/1")
    assert [e["type"] for e in got] == ["ergostat.item.snapshot", "t.x", "t.x"] and got[0]["seq"] == olds[-1]
    assert got[0]["set"] == {"i": 3} and ev.count() == 7 and ev.generation() != g
    assert {r["item"]: r["n"] for r in ev.items()}["t/1"] == 6


def test_a_second_instance_threads_and_processes_lose_nothing(ev, tmp_path):
    other = _events(ev.kind, tmp_path)
    ev.add("x", at=T)
    other.add("y", at=T + 1)
    threads = [threading.Thread(target=lambda k=k: [ev.add("t", data={"k": k, "i": i}) for i in range(25)]) for k in range(4)]
    procs = [multiprocessing.get_context("spawn").Process(target=_write, args=(ev.kind, str(tmp_path), k)) for k in range(2)]
    for t in [*threads, *procs]:
        t.start()
    for t in [*threads, *procs]:
        t.join()
    got = _events(ev.kind, tmp_path).query(n=None)
    assert len(got) == 2 + 100 + 50 and len({e["seq"] for e in got}) == len(got)
    for k in range(4):                                   # each writer's order kept
        assert [e["data"]["i"] for e in got if e["type"] == "t" and e["data"]["k"] == k] == list(range(25))
    assert [e["type"] for e in ev.query(n=None)][:2] == ["x", "y"] and len(other.query(n=None)) == len(got)


def _write(kind, d, k):
    from pathlib import Path
    e = _events(kind, Path(d))
    for i in range(25):
        e.add("p", data={"k": k, "i": i})


def test_history_survives_a_reopen(ev, tmp_path):
    for i in range(9):
        ev.add("x", item="t/1", data={"i": i}, at=T + i)
    again = _events(ev.kind, tmp_path)
    assert [e["data"]["i"] for e in again.query(n=None)] == list(range(9))
    again.add("x", item="t/1", data={"i": 9})
    assert [e["data"]["i"] for e in ev.query(n=2)] == [8, 9]


# ---- measurements

VM = os.environ.get("ERGOSTAT_TEST_VM_URL")


def _measurements(kind, d):
    if kind == "sqlite":
        return Measurements(d)
    if kind == "tiers":
        return Measurements(d, raw=3600.0, tiers=[(60.0, 86400.0), (600.0, 7 * 86400.0)])
    from ergostat.victoria import Victoria
    return Victoria(VM, d, project=f"test-{uuid.uuid4().hex[:10]}", raw=3600.0, tiers=[(60.0, 86400.0), (600.0, 7 * 86400.0)])


@pytest.fixture(params=["sqlite", "tiers", "victoriametrics"])
def me(request, tmp_path):
    if request.param == "victoriametrics" and not VM:
        pytest.skip("set ERGOSTAT_TEST_VM_URL to run VictoriaMetrics")
    m = _measurements(request.param, tmp_path)
    m.kind = request.param
    yield m
    if request.param == "victoriametrics":
        m.drop()


def test_write_read_latest_and_range(me):
    me.add("sensor/a", 3, at=T)
    me.add_many([("sensor/a", T + 10, 4), ("sensor/a", T + 20, 2), ("sensor/b", T + 5, 9)])
    me.add("sensor/a", 1, at=T - 100)                    # out of order
    assert me.range("sensor/a", T - 200, T + 100) == [(T - 100, 1), (T, 3), (T + 10, 4), (T + 20, 2)]
    assert me.range("sensor/a", T, T + 100, last=2) == [(T + 10, 4), (T + 20, 2)]
    assert me.latest("sensor/a") == (T + 20, 2) and me.latest("sensor/a", T + 15) == (T + 10, 4)
    assert me.latest("sensor/none") is None
    assert me.first("sensor/a", T + 1, T + 100) == (T + 10, 4)
    assert me.count("sensor/a", T, T + 100) == 3
    assert [r["series"] for r in me.series()] == ["sensor/a", "sensor/b"]
    assert me.first_time() == T - 100


def test_bucketed_and_sampled(me):
    me.add_many([("s", T + i, float(i)) for i in range(100)])
    got = me.bucketed("s", T, T + 100, 4)
    assert [(b, round(mean, 6), t, v) for b, mean, t, v in got] == [(0, 12.0, T + 24, 24.0), (1, 37.0, T + 49, 49.0),
                                                                    (2, 62.0, T + 74, 74.0), (3, 87.0, T + 99, 99.0)]
    pts = me.sampled("s", T, T + 100, points=10)
    assert pts[0] == (T, 0.0) and pts[-1] == (T + 99, 99.0) and len(pts) <= 12
    assert me.sampled("s", T, T + 10, points=10) == [(T + i, float(i)) for i in range(11)]


def test_forget_sets_readings_aside(me):
    me.add_many([("s", T + i, v) for i, v in enumerate([1, 2, 500, 3, -9])])
    assert sorted(me.forget("s", above=100, below=0)) == [(T + 2, 500.0), (T + 4, -9.0)]
    assert [v for _, v in me.range("s", T, T + 10)] == [1, 2, 3]
    assert me.forget("s", above=100) == []


def test_tiers_keep_old_readings_as_buckets(me, tmp_path):
    if me.kind == "sqlite":
        pytest.skip("no tiers")
    now = T + 10 * 86400
    me.add_many([("s", now - 3 * 86400 + 6 * i, float(i % 50)) for i in range(3 * 86400 // 6)])   # three days, every 6s
    me.add("s", 7.0, at=now - 1)
    me.roll(now)
    me.roll(now)                                          # again: nothing more, nothing lost
    old = me.range("s", now - 3 * 86400, now - 2 * 86400)
    if me.kind == "tiers":                                # kept: raw for the last hour, then buckets
        assert me.count() < 3 * 86400 // 6 / 4
        assert 120 < len(old) <= 145                       # ten-minute buckets, each its last reading
    else:                                                 # kept by the server, compressed; read one by one when few
        assert 0 < len(old) <= 20_000 and len(me.range("s", now - 3 * 86400, now)) <= 20_000 + 3600 // 6 + 1
    assert me.latest("s") == (now - 1, 7.0) and me.latest("s", now - 2 * 86400)[0] <= now - 2 * 86400
    got = me.bucketed("s", now - 3 * 86400, now, 72)      # an hour a bucket: every bucket's mean is the readings'
    assert len(got) == 72 and all(abs(mean - 24.5) < 1.5 for _, mean, _, _ in got[:-2])
    assert me.first("s", now - 4 * 86400, now) == (now - 3 * 86400, 0.0)
    fine = me.bucketed("s", now - 1800, now, 30)         # the last half hour: raw
    assert len(fine) == 30 and fine[-1][3] == 7.0
    assert me.count("s", now - 3 * 86400, now) == 3 * 86400 // 6 + 1


def test_late_readings_are_rolled_again(me):
    if me.kind == "sqlite":
        pytest.skip("no tiers")
    now = T + 10 * 86400
    me.add_many([("s", now - 7200 + i * 60, 1.0) for i in range(60)])
    me.roll(now)
    me.add_many([("s", now - 7200 + 30, 100.0)])           # late, into a bucket already made
    me.roll(now)
    assert me.bucketed("s", now - 7200, now - 3600, 1)[0][1] == pytest.approx((60 + 100) / 61)
