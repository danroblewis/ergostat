"""redesign-rescored-as-the-record-moves (docs/roadmap/overnight/redesign-rescored-as-the-record-moves.md): a waiting
redesign is scored again when the record its scorecard reads has moved (a mark of it, never the scoring's age), at
most once every 30 minutes and one a pass; a promoted one is written only on a scorecard of the record as it is."""

from __future__ import annotations

import contextlib
import fcntl
import time

from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.numbers import redesign as rd
from ergostat.numbers import redesign_due as due
from ergostat.numbers import redesign_record as rr
from ergostat.numbers import scorecard as sc

from .test_modelling_core import MODELLING
from .test_modelling_core2 import TWO
from .test_redesign import BUSY, BUSY_AUX, CHAIN, READ, busy, project

MIN = 60.0


def _judged(monkeypatch) -> list[str]:
    """Every call of ``rd.judged``, by id."""
    calls, real = [], rd.judged

    def counted(p, x, at=None):
        calls.append(x["id"])
        return real(p, x, at)
    monkeypatch.setattr(rd, "judged", counted)
    return calls


def _verdict(monkeypatch, says: dict) -> None:
    """The scorecard's verdict set from ``says["verdict"]`` (when set), never the mark."""
    real = sc.score

    def score(*a, **k):
        card = real(*a, **k)
        if says.get("verdict"):
            card["verdict"], card["why"] = says["verdict"], f"{says['verdict']}: set by the test"
        return card
    monkeypatch.setattr(sc, "score", score)


def _reading(p, at: float, stock: str = "triage", value: float = 3.0) -> None:
    s = next(iter(p.model.spec.stocks[stock].sensors.values()))
    p.measurements.add(s.series, value, at)


def _mark(p) -> dict:
    return rr.mark(p, p.model.spec)


def _passed(p, t0: float, raw: dict | None = None) -> str:
    got = rd.submit(p, "redesigner", raw or {"title": "busy read", "edits": READ}, at=t0)
    assert got["status"] == "proposed", got["why"]
    jd.run(p, "judge", at=t0)
    x = pr.stored(p)[got["id"]]
    assert x["state"] == "passed" and x["scored"]["mark"] == _mark(p), x["state"]
    return got["id"]


def _judge_only(p, at: float) -> None:
    """What the judge, the redesigner and modelling do: none of it is the record the scorecard reads."""
    jd.run(p, "judge", at=at)
    rd.ran(p, "model", {"result": "nothing proposed"})
    rd.ask(p, None)
    p.events.add("ergostat.modelling-request.opened", item="ergostat.modelling-request/x", source="ergostat")


def test_the_mark_moves_with_what_the_scorecard_reads_and_not_with_the_judge(tmp_path):
    p = project(tmp_path / "m", BUSY.replace("AUXILIARIES", BUSY_AUX) + MODELLING)   # the judge a template's block
    t0 = time.time()
    _passed(p, t0)
    m = _mark(p)
    _judge_only(p, t0 + MIN)
    for b in ("judge", "redesigner"):                       # a once template's blocks' runs
        p.events.add("agent.ran", item=b, source="engine")
    assert _mark(p) == m
    assert p.events.last_seq() > m["seq"]                   # ... though the store's last seq moved with all of it
    moves = [lambda: p.events.add("alert.fired", item="alert/1", source="pager"),        # a model kind's item
             lambda: p.events.add("agent.started", item="step", source="engine"),        # a model block's run
             lambda: p.events.add("agent.ran", item="step", source="engine"),
             lambda: p.events.add("agent.failed", item="step", source="engine"),
             lambda: p.events.add("valve.opened", item="step", source="step", data={"amount": 1}),   # a model valve
             lambda: _reading(p, t0 + 2 * MIN)]                                         # a model sensor's reading
    for move in moves:
        move()
        now = _mark(p)
        assert now != m
        m = now


def test_accepting_another_change_has_a_waiting_redesign_scored_again_before_it_is_written(tmp_path, monkeypatch):
    from ergostat.numbers import improve as im
    p = busy(tmp_path / "m", "{redesign: auto}")
    t0 = time.time()
    rd.ran(p, "model", {"result": "started"})               # held, not written, while a redesign is being made
    rid = _passed(p, t0)
    words = im.submit(p, "modeller", {"kind": "description", "parts": ["stock.triage"], "title": "described",
                                       "edit": {"part": "stock.triage", "set": {"description": "alerts not yet triaged"}},
                                       "reasons": [{"says": "none", "evidence": "finding:no-description@stock.triage"}]})
    jd.run(p, "judge", at=t0 + 1)
    pr.accept(p, words["id"], {"at": t0, "window": 600})    # the owner writes another change: the model moves
    m = _mark(p)
    assert m["model"] != pr.stored(p)[rid]["scored"]["mark"]["model"]
    rd.ran(p, "model", {"result": "proposed"})
    calls = _judged(monkeypatch)
    out = jd.run(p, "judge", at=t0 + 2)
    assert calls == [rid] and out["accepted"] == 1
    x = pr.stored(p)[rid]
    assert x["state"] == "accepted" and x["scored"]["mark"] == m


def test_no_new_events_no_rescore(tmp_path, monkeypatch):
    p = busy(tmp_path / "m", "owner")
    t0 = time.time()
    rid = _passed(p, t0)
    was = pr.stored(p)[rid]["scored"]
    calls = _judged(monkeypatch)
    _judge_only(p, t0 + MIN)
    jd.run(p, "judge", at=t0 + 2 * 3600)
    x = pr.stored(p)[rid]
    assert calls == [] and x["scored"] == was and x["state"] == "passed"


def test_new_record_rescores_after_thirty_minutes_not_before(tmp_path, monkeypatch):
    p = busy(tmp_path / "m", "owner")
    t0 = time.time()
    rid = _passed(p, t0)
    was = pr.stored(p)[rid]
    _reading(p, t0 + MIN)
    calls = _judged(monkeypatch)
    jd.run(p, "judge", at=was["scored"]["at"] + 29 * MIN)
    assert calls == []
    at = was["scored"]["at"] + 31 * MIN
    out = jd.run(p, "judge", at=at)
    x = pr.stored(p)[rid]
    assert calls == [rid] and out["passed"] == 1 and x["state"] == "passed"
    assert x["scored"]["seq"] > was["scored"]["seq"] and x["scored"]["mark"] == _mark(p) and x["scored"]["at"] == at
    assert x["scorecard"]["coherence"]["until"] == at != was["scorecard"]["coherence"]["until"]


def test_a_rescore_no_longer_better_fails_it_and_the_unit_rests(tmp_path, monkeypatch):
    says = {}
    _verdict(monkeypatch, says)
    p = busy(tmp_path / "m", "owner")
    t0 = time.time()
    rid = _passed(p, t0)
    _reading(p, t0 + MIN)
    says["verdict"] = "mixed"
    at = t0 + 31 * MIN
    jd.run(p, "judge", at=at)
    x = pr.stored(p)[rid]
    assert x["state"] == "failed" and x["scorecard"]["verdict"] == "mixed"
    assert x["verdict"]["why"].startswith("no longer better on the record as it is now: mixed")
    assert "resting" in (due.resting(p, p.model.spec, "model", at + MIN) or "")


def _two(tmp_path, monkeypatch):
    """TWO with a passed redesign of front (scored first), then of back."""
    _verdict(monkeypatch, {"verdict": "better"})
    p = project(tmp_path / "m", TWO)
    t0 = time.time()
    front = _passed(p, t0, {"title": "front", "system": "front", "edits": [CHAIN[0]]})
    back = _passed(p, t0 + 1, {"title": "back", "system": "back",
                               "edits": [{"part": "stock.investigate", "set": {"description": "alerts looked into"}}]})
    st = pr.stored(p)
    assert st[front]["scored"]["seq"] < st[back]["scored"]["seq"]
    return p, t0, front, back


def test_one_rescore_a_pass_least_recently_scored_first(tmp_path, monkeypatch):
    p, t0, front, back = _two(tmp_path, monkeypatch)
    new = rd.submit(p, "redesigner", {"title": "all", "edits": [{"part": "flow.in", "set": {"unit": "alerts"}}]}, at=t0 + 2)
    assert new["status"] == "proposed", new["why"]
    _reading(p, t0 + 3)
    calls = _judged(monkeypatch)
    jd.run(p, "judge", at=t0 + 1 + 31 * MIN)
    assert calls == [new["id"], front]                      # a first judging, not counted; one rescore: front's
    _reading(p, t0 + 32 * MIN)
    del calls[:]
    jd.run(p, "judge", at=t0 + 1 + 62 * MIN)
    assert calls == [back]                                  # front was scored more recently: back's turn


def test_an_unreadable_mark_writes_nothing_and_marks_rescoring(tmp_path, monkeypatch):
    p = busy(tmp_path / "m", "{redesign: auto}")
    t0 = time.time()
    rd.ran(p, "model", {"result": "started"})
    rid = _passed(p, t0)                                    # passed, held while the redesigner runs
    rd.ran(p, "model", {"result": "proposed"})
    real = rr.mark

    def broken(p_, spec):
        raise OSError("events.db is locked")
    monkeypatch.setattr(rr, "mark", broken)
    calls = _judged(monkeypatch)
    out = jd.run(p, "judge", at=t0 + MIN)
    x = pr.stored(p)[rid]
    assert out["accepted"] == 0 and x["state"] == "passed" and x["rescoring"] and "events.db is locked" in x["rescore_error"]
    from ergostat.numbers import review as rv
    assert rv.redesign_view(x)["rescore_error"] == x["rescore_error"]
    n = len(p.events.query(n=None, item=pr.item_of(rid)))
    jd.run(p, "judge", at=t0 + 2 * MIN)
    assert len(p.events.query(n=None, item=pr.item_of(rid))) == n      # no event a pass for a store still broken
    monkeypatch.setattr(rr, "mark", real)
    out = jd.run(p, "judge", at=t0 + 3 * MIN)                          # well under 30 minutes on
    x = pr.stored(p)[rid]
    assert calls == [rid] and out["accepted"] == 1 and x["state"] == "accepted"
    assert x["rescoring"] is False and x["rescore_error"] is None


def test_two_marked_rescoring_recover_one_a_pass_whatever_their_mark(tmp_path, monkeypatch):
    p, t0, front, back = _two(tmp_path, monkeypatch)
    real = rr.mark
    monkeypatch.setattr(rr, "mark", lambda p_, spec: (_ for _ in ()).throw(OSError("no store")))
    jd.run(p, "judge", at=t0 + 2)
    assert all(pr.stored(p)[i]["rescoring"] for i in (front, back))
    monkeypatch.setattr(rr, "mark", real)
    assert all(pr.stored(p)[i]["scored"]["mark"] == _mark(p) for i in (front, back))   # the record has not moved
    calls = _judged(monkeypatch)
    jd.run(p, "judge", at=t0 + 3)                           # rescoring counts against the cap: one a pass
    assert calls == [front] and pr.stored(p)[back]["rescoring"] and not pr.stored(p)[front]["rescoring"]
    jd.run(p, "judge", at=t0 + 4)
    assert calls == [front, back] and not pr.stored(p)[back]["rescoring"]


def test_same_id_remake_clears_rescoring_and_its_old_score(tmp_path):
    p = busy(tmp_path / "m", "owner")
    t0 = time.time()
    rid = _passed(p, t0)
    x = pr.stored(p)[rid]
    pr.event(p, rid, "passed", {"rescoring": True, "rescore_error": "old", "scored": {"mark": {"seq": -1}, "seq": 1, "at": 0}})
    pr.event(p, rid, "made", {k: x[k] for k in ("title", "made_by", "kind", "version", "structure", "system")} | {
        "made": t0 + 1, "created": t0 + 1}, source="redesigner")
    pr.event(p, rid, "checked", {})
    assert pr.stored(p)[rid]["rescoring"] and pr.stored(p)[rid]["state"] == "checked"   # the fold kept the old fields
    jd.run(p, "judge", at=t0 + MIN)
    x = pr.stored(p)[rid]
    assert x["state"] == "passed" and x["rescoring"] is False and x["rescore_error"] is None
    assert x["scored"]["mark"] == _mark(p) and x["scored"]["at"] == t0 + MIN


def test_a_promoted_redesign_on_an_unmoved_record_is_written_without_rescoring(tmp_path, monkeypatch):
    calls = _judged(monkeypatch)
    p = busy(tmp_path / "m", "{redesign: auto}")
    t0 = time.time()
    rd.ran(p, "model", {"result": "started"})
    rid = _passed(p, t0)
    rd.ran(p, "model", {"result": "proposed"})
    out = jd.run(p, "judge", at=t0 + 2 * 3600)              # however long ago it was scored
    assert out["accepted"] == 1 and pr.stored(p)[rid]["state"] == "accepted" and calls == [rid]


def _moved_before_the_write(monkeypatch, p, t0, then=None) -> dict:
    """``rd.running`` (between the verdicts and the writes) adds a model reading; returns the mark after it."""
    got = {}

    def running(p_, now=None, within=None):
        _reading(p, t0 + 1, value=7.0)
        got["mark"] = _mark(p)
        if then:
            then()
        return False
    monkeypatch.setattr(rd, "running", running)
    return got


def test_a_promoted_redesign_is_scored_again_before_written_when_the_record_moved(tmp_path, monkeypatch):
    for better in (True, False):
        says = {}
        _verdict(monkeypatch, says)
        calls = _judged(monkeypatch)
        p = busy(tmp_path / str(better), "{redesign: auto}")
        t0 = time.time()
        got = rd.submit(p, "redesigner", {"title": "busy read", "edits": READ}, at=t0)
        moved = _moved_before_the_write(monkeypatch, p, t0, None if better else lambda says=says: says.update(verdict="mixed"))
        out = jd.run(p, "judge", at=t0)
        x = pr.stored(p)[got["id"]]
        assert calls == [got["id"]] * 2                     # judged, then scored again before the write
        evs = [e["type"].rsplit(".", 1)[1] for e in p.events.query(n=None, item=pr.item_of(got["id"]))]
        if better:
            assert out["accepted"] == 1 and x["state"] == "accepted"
            last = [e for e in p.events.query(n=None, item=pr.item_of(got["id"]))][evs.index("accepted") - 1]
            assert last["type"].endswith(".passed") and last["data"]["scored"]["mark"] == moved["mark"]
        else:
            assert out["accepted"] == 0 and x["state"] == "failed" and "accepted" not in evs
            assert x["scored"]["mark"] == moved["mark"]


def test_the_write_path_rescore_and_write_hold_the_lock(tmp_path, monkeypatch):
    p = busy(tmp_path / "m", "{redesign: auto}")
    t0 = time.time()
    got = rd.submit(p, "redesigner", {"title": "busy read", "edits": READ}, at=t0)
    held, after = [], {}
    _moved_before_the_write(monkeypatch, p, t0, lambda: after.update(on=True))
    real, real_accept = rd.judged, pr._accept

    def lock_free() -> bool:
        with open(p.dir / "proposals.lock", "w") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh, fcntl.LOCK_UN)
                return True
            except OSError:
                return False

    real_locked, holds = pr.locked, {"n": 0, "in": None}

    @contextlib.contextmanager
    def counted(p_):                                         # numbers each hold, so two holds can't pass for one
        with real_locked(p_):
            holds["n"] += 1
            holds["in"] = holds["n"]
            try:
                yield
            finally:
                holds["in"] = None

    def watched(p_, x, at=None):
        if after:
            held.append((not lock_free(), holds["in"]))
        return real(p_, x, at)

    def accept(*a, **k):
        held.append((not lock_free(), holds["in"]))
        return real_accept(*a, **k)
    monkeypatch.setattr(pr, "locked", counted)
    monkeypatch.setattr(rd, "judged", watched)
    monkeypatch.setattr(pr, "_accept", accept)
    assert jd.run(p, "judge", at=t0)["accepted"] == 1 and pr.stored(p)[got["id"]]["state"] == "accepted"
    assert len(held) == 2 and all(h for h, _ in held)        # the write-path rescore, then the write, both locked
    assert held[0][1] is not None and held[0][1] == held[1][1]   # and in the same hold, with no gap between
