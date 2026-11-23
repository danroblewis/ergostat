"""What caused an event, and its source, indexed in each segment and in the head (event-log-indexes-what-it-is-asked):
``caused_by`` and a query by source read only the segments, blocks and rows holding a match, give the old full scan's
answer across the head and a seal, and an old segment with no index beside it still answers (its index built once).
The query-cost check: each routine query's reads (blocks unpacked, events parsed) are counted, so a new full scan on
a routine path fails here."""

from __future__ import annotations

import random
import time

import pytest

from ergostat import segments as seg_mod
from ergostat.segments import KEYED, Segments, write_segment
from ergostat.store import Events

T = 1_700_000_000.0


def _old(sg, field, value):
    """The answer as it was: every event read, the field compared."""
    return sg._scan(test=lambda e: e.get(field) == value)


def _record(tmp_path, n=600, seal=50):
    rnd = random.Random(5)
    causes = [f"run{i}" for i in range(40)]
    evs = [{"id": f"e{i:05d}", "type": rnd.choice(["a.x", "agent.ran", "b.y"]), "item": f"t/{rnd.randrange(9)}",
            "source": rnd.choice(["m", "m/1", None]), "causedby": rnd.choice(causes + [None] * 20), "at": T + i}
           for i in range(n)]
    sg = Segments(tmp_path / "seg", seal=seal)
    for e in evs:
        sg.add(e["type"], item=e["item"], source=e["source"], causedby=e["causedby"], at=e["at"], id=e["id"])
    return sg, causes, evs


def test_caused_by_and_source_answer_as_the_old_scan_across_the_head_and_a_seal(tmp_path):
    sg, causes, evs = _record(tmp_path)
    assert len(sg._segs) == 12 and len(sg._head) == 0
    sg.add("a.x", item="t/1", causedby="run3", source="m", at=T + 700)      # in the head, after the seal
    sg.add("a.x", item="t/2", causedby="late", at=T + 701)
    (tmp_path / "sql").mkdir()
    sq = Events(tmp_path / "sql")
    sq.add_many([dict(e) for e in evs])
    sq.add("a.x", item="t/1", causedby="run3", source="m", at=T + 700)
    sq.add("a.x", item="t/2", causedby="late", at=T + 701)
    for c in [*causes, "late", "nothing"]:
        got = sg.caused_by(c)
        assert got == _old(sg, "causedby", c)
        assert [(e["type"], e["item"], e["time"]) for e in got] == [(e["type"], e["item"], e["time"]) for e in sq.caused_by(c)]
        assert [e["seq"] for e in got] == sorted(e["seq"] for e in got)
    assert [e["causedby"] for e in sg.caused_by("run3")][-1] == "run3" and sg.caused_by("late")[0]["item"] == "t/2"
    for src in ["m", "m/1", "none"]:
        assert sg.query(n=None, source=src) == _old(sg, "source", src)
        assert sg.query(n=3, source=src) == _old(sg, "source", src)[-3:]
        assert sg.query(n=None, source=src, type="a.x", item="t/1") == [
            e for e in _old(sg, "source", src) if e["type"] == "a.x" and e["item"] == "t/1"]
    busy = max(causes, key=lambda c: len(_old(sg, "causedby", c)))
    while len(sg._head) < 49:                                       # a seal falls between a run's events
        sg.add("b.y", item="t/3", causedby=busy)
    before = sg.caused_by(busy)
    sg.add("b.y", item="t/4", causedby=busy)
    assert len(sg._segs) == 13 and len(sg._head) == 0
    assert sg.caused_by(busy) == _old(sg, "causedby", busy) == before + [sg.caused_by(busy)[-1]]
    other = Segments(tmp_path / "seg", seal=50)                     # another process: it reads the files alone
    assert other.caused_by(busy) == sg.caused_by(busy)


def test_a_shared_hash_is_told_apart_by_the_event(tmp_path, monkeypatch):
    monkeypatch.setattr(seg_mod, "_key", lambda v: 1)               # every value under one key
    sg, causes, _ = _record(tmp_path, n=200)
    for c in causes[:5]:
        assert sg.caused_by(c) == _old(sg, "causedby", c)
        assert all(e["causedby"] == c for e in sg.caused_by(c))


def test_old_segments_with_no_index_still_answer_and_build_it_once(tmp_path):
    sg, causes, _ = _record(tmp_path)
    want = {c: sg.caused_by(c) for c in causes}
    for p in sg.dir.glob("seg-*"):
        if p.suffix in KEYED.values():
            p.unlink()
    (next(sg.dir.glob("seg-*.idx")).with_suffix(".cby")).write_bytes(b'{"keys": 9, "rows": 9}\n\0')   # not whole
    old = Segments(tmp_path / "seg", seal=50)
    assert {c: old.caused_by(c) for c in causes} == want
    assert old.reads["built"] == 12, "each old segment's index built once, on the first question"
    assert all(s.path.with_suffix(suf).exists() for s in old._segs for suf in KEYED.values()), "and kept beside it"
    assert old.query(n=None, source="m") == _old(old, "source", "m")
    again = Segments(tmp_path / "seg", seal=50)
    assert {c: again.caused_by(c) for c in causes} == want and again.reads["built"] == 0


def test_an_index_that_cannot_be_written_is_kept_in_memory(tmp_path, monkeypatch):
    sg, causes, _ = _record(tmp_path, n=200)
    want = {c: sg.caused_by(c) for c in causes}
    for p in sg.dir.glob("seg-*"):
        if p.suffix in KEYED.values():
            p.unlink()
    real = seg_mod.os.replace

    def refuse(a, b):
        if str(b).endswith(tuple(KEYED.values())):
            raise PermissionError(b)
        return real(a, b)
    monkeypatch.setattr(seg_mod.os, "replace", refuse)
    old = Segments(tmp_path / "seg", seal=50)
    assert {c: old.caused_by(c) for c in causes} == want and old.reads["built"] == 4
    assert not list(old.dir.glob("*.tmp"))


def test_a_rewritten_segment_takes_its_index_with_it(tmp_path):
    sg, causes, evs = _record(tmp_path, n=200)
    sg.prune(T + 1e9)                                                # every item forgotten: every segment rewritten
    left = {p.name.rsplit(".", 1)[0] for p in sg.dir.glob("seg-*")}
    assert left == {p.name[:-4] for p in sg.dir.glob("seg-*.idx")}, "no index left beside a segment gone"
    for c in causes:
        assert sg.caused_by(c) == _old(sg, "causedby", c)


# ---- the query-cost check: what each routine question reads


def _reads(sg):
    sg._blocks.clear()
    sg._block_bytes = 0
    sg._tallies.clear()
    sg.reads.update(blocks=0, rows=0, built=0)


def test_routine_questions_read_only_what_matches(tmp_path):
    """Each routine question of the dispatcher and the pages, over a record of 24 segments: the events it parses are
    the ones it answers with (``n`` newest: no more than n), and the blocks it unpacks hold them. A question that falls
    through to reading every segment parses thousands and fails here."""
    rnd = random.Random(3)
    sg = Segments(tmp_path / "seg", seal=1000)
    evs = []
    for i in range(24_000):
        evs.append({"id": f"e{i}", "type": rnd.choice(["a.x", "b.y", "claude.message"]), "item": f"t/{i // 500}/{i % 7}",
                    "source": f"agent{i // 3000}", "causedby": f"run{i // 40}" if i % 3 == 0 else None, "at": T + i})
    evs[100]["causedby"] = evs[23_500]["causedby"] = "both"
    evs[200].update(type="valve.opened", item="v/1", source="ctl", causedby=None)
    evs[23_600].update(type="agent.ran", item="w/1", causedby="run1")
    sg.add_many(evs, new=True)
    sg.add("a.x", item="t/9/1", causedby="both", source="agent7", at=T + 30_000)
    assert len(sg._segs) == 24
    checks = [
        (lambda: sg.caused_by("both"), 3, 2),
        (lambda: sg.caused_by("run300"), 14, 1),
        (lambda: sg.caused_by("unheard"), 0, 0),
        (lambda: sg.query(n=1, source="ctl"), 1, 1),
        (lambda: sg.query(n=1, source="nobody"), 0, 0),
        (lambda: sg.query(n=1, item="t/3/1", type="claude.*", since=T), 1, 1),
        (lambda: sg.query(n=1, item="t/40/2"), 1, 1),
        (lambda: sg.query(n=5, type="valve.opened"), 1, 1),
        (lambda: sg.query(n=1, item="t/40/2", type="a.*", unvoided=True), 1, 1),   # (a loop's last crossing: so asked)
        (lambda: sg.opened("v/1", T, T + 1e6), None, 0),
        (lambda: sg.runs("w/1", T, T + 1e6), None, 0),
        (lambda: sg.last_opening("v/1"), None, 1),
        (lambda: sg.times(["t/3/1"], "a.x", T, T + 1e6), None, 0),
        (lambda: sg.moments(n=50, type="b.y"), None, 0),
        (lambda: sg.counted("claude.*"), None, 0),
        (lambda: sg.known(["e5", "e23999", "nope"]), None, 0),
    ]
    for ask, rows, blocks in checks:
        _reads(sg)
        got = ask()
        parsed = sg.reads["rows"]
        if rows is not None:
            assert len(got) == rows and parsed <= rows, (got, sg.reads)
        else:
            assert parsed <= 2, sg.reads
        assert sg.reads["blocks"] <= blocks, sg.reads


def _synthetic(d, n, cause_at):
    """A record of ``n`` events written as sealed segments (a run's events at the seqs ``cause_at``), and a head."""
    (d / "events").mkdir(parents=True)
    seal = seg_mod.SEAL
    for lo in range(0, n - 1000, seal):
        evs = [{"seq": q, "id": f"e{q}", "time": T + q, "type": ("a.x", "b.y", "c.z")[q % 3], "item": f"t/{q % 997}",
                "source": f"s{q % 5}", "causedby": "run" if q in cause_at else f"r{q // 30}", "data": {"q": q}}
               for q in range(lo + 1, min(lo + seal, n - 1000) + 1)]
        write_segment(d / "events", evs)
    sg = Segments(d, seal=seal)
    sg.add_many([{"type": "a.x", "item": "t/1", "causedby": "run" if q in cause_at else None, "at": T + q}
                 for q in range(n - 999, n + 1)], new=True)
    return sg


@pytest.mark.slow
def test_caused_by_on_a_million_events_reads_only_the_segments_holding_it(tmp_path):
    """Done item 1: on 1,000,000 events (31 sealed segments and a head of 1,000), ``caused_by`` unpacks only the blocks
    of the segments holding the run's events, parses only those events, and reads the same on a tenth of the record:
    what it costs does not grow with events it is not asked about (counted, not timed: a time bound flakes under load)."""
    cause_at = {5, 70_000, 70_001, 999_500}
    small, big = (_synthetic(tmp_path / k, n, cause_at) for k, n in (("small", 100_000), ("big", 1_000_000)))
    assert len(big._segs) == 31 and len(small._segs) == 4 and big.count() == 1_000_000
    want = sorted(cause_at)
    for sg in (small, big):
        sg.caused_by("warm")                       # (each segment's keys read in once, as a long-running reader has)
        _reads(sg)
        t0 = time.perf_counter()
        got = sg.caused_by("run")
        sg.took, sg.cost = time.perf_counter() - t0, dict(sg.reads)
        assert [e["seq"] for e in got] == [q for q in want if q <= sg.last_seq()]
        assert got == _old(sg, "causedby", "run")
    assert len(big.caused_by("run")) == 4 and len(small.caused_by("run")) == 3   # (the 4th in the big one's head)
    assert big.cost == small.cost and big.cost["rows"] == 3 and big.cost["blocks"] <= 3, (big.cost, small.cost)
    print(f"caused_by: {small.took * 1e3:.1f} ms on 100k events, {big.took * 1e3:.1f} ms on 1M")
