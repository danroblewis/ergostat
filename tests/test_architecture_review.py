"""The daily architecture review (numbers/archreview.py, SPEC §12e *Redesign*): one call a day on a larger model reads
the architecture as a whole; its findings are held as requests (a redesign open and taken first, a split or merge held
for the owner); it writes no change; its cost shares the redesigner's cap, its estimate charged before the call; it
runs under redesign.lock, and the redesign that takes its request up marks it only if no newer review said it again."""

from __future__ import annotations

import fcntl
import io
import json
import time

import pytest

from ergostat.library.run import modelling as ml
from ergostat.numbers import archreview as arv
from ergostat.numbers import modeller as md
from ergostat.numbers import proposals as pr
from ergostat.numbers import redesign as rd
from ergostat.numbers import redesign_due as due
from ergostat.numbers import redesigner as rdr
from ergostat.numbers import requests as rq
from ergostat.numbers import reviewer as rv

from .test_architecture import _chain, _model
from .test_redesign import project

DAILY = due.DAILY
SYSTEMS = {"a": "takes work in", "big": "the big queue", "lab": "the lab", "ops": "runs it"}


def four(tmp_path, extra: str = ""):
    return project(tmp_path / "m", _model(SYSTEMS, *[_chain(s[0] + "q", 1, s) for s in SYSTEMS]) + extra)


def said(*findings, usd: float = 0.03, error: str | None = None):
    """A stand-in call answering these findings (system, advice, says), counting its calls."""
    def call(text, model, timeout=None):
        call.calls.append((text, model, timeout))
        if error:
            return {"result": "", "usd": usd, "error": error}
        return {"result": "\n".join(json.dumps({"review": {"system": s, "advice": a, "says": w}}) for s, a, w in findings)
                or json.dumps({"none": "nothing is wrong"}), "usd": usd, "tokens_in": 100, "tokens_out": 50, "seconds": 1.0}
    call.calls = []
    return call


def mine(p) -> dict:
    return {r["about"] + " " + r["code"]: r for r in rq.stored(p).values() if str(r.get("code")).startswith("review-")}


def reviewed(p) -> list[dict]:
    return [e["data"] for e in p.events.query(n=None, type=arv.REVIEWED)]


def block(monkeypatch, p):
    monkeypatch.setattr(ml, "project", lambda: p)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))


def nothing(seen: list):
    def run(p_, system, why, **k):
        seen.append({"system": system, "why": why, **k})
        return {"system": system, "rounds": [], "cost": {"usd": 0.0, "calls": 0}, "version": "v",
                "result": "nothing proposed", "reports": []}
    return run


def test_the_review_holds_each_finding_as_a_request_and_writes_no_change(tmp_path):
    p = four(tmp_path)
    disk = p.model.path.read_bytes()
    got = arv.run(p, "sonnet", 2.0, now=time.time(), call=said(("lab", "redesign", "its replay is poor"),
                                                               ("big", "split", "two clusters"), ("a", "merge", "with ops")))
    assert got["result"] == "reviewed"
    x = mine(p)
    assert set(x) == {"system.lab review-redesign", "system.big review-split", "system.a review-merge"}
    assert x["system.lab review-redesign"]["state"] == "open" and not x["system.lab review-redesign"].get("owner")
    for k in ("system.big review-split", "system.a review-merge"):
        assert x[k]["state"] == "held" and x[k]["owner"] is True            # structure: the owner's
    stamp = next(e for e in reviewed(p) if e["result"] == "started")
    assert all(r["source"] == "redesign" for r in x.values())
    assert {r["review"] for r in x.values()} == {p.events.query(n=None, type=arv.REVIEWED)[0]["id"]} and stamp
    assert not pr.stored(p) and not p.events.query(n=None, type="ergostat.model-change.*")
    assert p.model.path.read_bytes() == disk


def test_a_review_redesign_makes_its_system_due_first(tmp_path):
    p = four(tmp_path)
    rd.ran(p, "ops", {"result": "nothing proposed"})                       # not the first run; ops reviewed today
    assert due.next_due(p)["system"] == "a"                                # a, big and lab due for their daily review
    due.hold(p, "lab", "review-redesign", "its interface reaches into ops", state="open", more={"review": "r1", "why": None})
    got = due.next_due(p)
    assert got["system"] == "lab" and got["why"][0].startswith("the architecture review: its interface reaches")
    assert got["review"]["stamp"] == "r1"


def test_a_resting_system_is_not_taken_whatever_the_review_says(tmp_path):
    p = four(tmp_path)
    rd.ran(p, "lab", {"result": "refused", "unit_sig": due.signature(p.model.spec, "lab")})
    due.hold(p, "lab", "review-redesign", "redesign it", state="open", more={"review": "r1", "why": None})
    got = due.next_due(p)
    assert got["system"] != "lab"
    assert due.resting(p, p.model.spec, "lab", time.time()) and "the architecture review: redesign it" in \
        due.triggers(p, p.model.spec, "lab", time.time())                   # due, and resting


def test_sync_does_not_answer_the_reviews_requests(tmp_path):
    p = four(tmp_path)
    arv.run(p, "sonnet", 2.0, now=time.time(), call=said(("lab", "redesign", "x"), ("big", "split", "y")))
    rq.sync(p)
    x = mine(p)
    assert x["system.lab review-redesign"]["state"] == "open" and x["system.big review-split"]["state"] == "held"


def test_the_review_runs_once_a_day_and_a_failed_call_counts(tmp_path):
    p = four(tmp_path)
    t0 = time.time()
    call = said(("lab", "redesign", "x"))
    arv.run(p, "sonnet", 5.0, now=t0, call=call)
    arv.run(p, "sonnet", 5.0, now=t0 + 3600, call=call)
    assert len(call.calls) == 1
    bad = said(error="the call failed (exit 1)")
    assert arv.run(p, "sonnet", 5.0, now=t0 + DAILY + 1, call=bad)["result"] == "failed"
    arv.run(p, "sonnet", 5.0, now=t0 + DAILY + 601, call=bad)              # a failed review is the day's: no retry
    assert len(bad.calls) == 1
    assert mine(p)["system.lab review-redesign"]["state"] == "open"        # a failed review lets nothing go
    arv.run(p, "sonnet", 5.0, now=t0 + 2 * DAILY + 2, call=call)
    assert len(call.calls) == 2
    nojson = {"result": "I think lab is fine", "usd": 0.01}
    assert arv.run(p, "sonnet", 5.0, now=t0 + 3 * DAILY + 3, call=lambda *a: nojson)["result"] == "failed"
    assert mine(p)["system.lab review-redesign"]["state"] == "open"


def test_the_review_is_not_called_when_its_estimated_most_would_pass_the_cap(tmp_path, monkeypatch, capsys):
    p = four(tmp_path)
    monkeypatch.setattr(md, "unsaid", lambda text, model: {"usd": 0.05, "tokens_in": 1, "tokens_out": 1, "estimated": True})
    rd.charge(p, "a", {"usd": 2.0 - 0.01})
    call = said(("lab", "redesign", "x"))
    assert arv.run(p, "sonnet", 2.0, now=time.time(), call=call)["result"] == "capped"
    assert not call.calls and reviewed(p)[-1]["result"] == "capped"
    assert arv.due_now(p, time.time())                                     # capped is no day's review
    monkeypatch.setattr(rv, "RESERVE", 0.0)                                # (the reviewer's share left out of this sum)
    monkeypatch.setattr(md, "call", lambda *a, **k: pytest.fail("called past the cap"))
    seen = []
    monkeypatch.setattr(rdr, "run", nothing(seen))
    block(monkeypatch, p)
    assert ml.redesign(["--when", "auto", "--review", "sonnet", "--daily", "2"]) == 0
    assert "would pass the $2.00 cap" in capsys.readouterr().err
    assert seen and 0.0 <= seen[0]["budget"] <= 0.01 + 1e-9
    monkeypatch.undo()
    out = rdr.run(p, "lab", [], budget=seen[0]["budget"], rounds=1, call=lambda *a: pytest.fail("a call with no budget"))
    assert out["cost"]["calls"] == 0


def test_a_call_killed_mid_way_leaves_its_estimate_charged(tmp_path):
    p = four(tmp_path)
    t0 = time.time()

    def killed(text, model, timeout=None):
        raise KeyboardInterrupt                                             # stands in for the run being killed
    with pytest.raises(KeyboardInterrupt):
        arv.run(p, "sonnet", 5.0, now=t0, call=killed)
    est = reviewed(p)[0]["estimate"]
    assert est > 0 and rd.spent(p, t0) == pytest.approx(est)
    call = said(("lab", "redesign", "x"))
    assert arv.run(p, "sonnet", 5.0, now=t0 + 60, call=call)["result"] is None and not call.calls   # started: the day's
    q = four(tmp_path / "q")
    arv.run(q, "sonnet", 5.0, now=t0, call=said(("lab", "redesign", "x"), usd=0.0123))
    assert rd.spent(q, t0) == pytest.approx(0.0123)                         # the estimate plus the difference


def test_the_answer_is_read_by_allowlist(tmp_path, monkeypatch):
    p = four(tmp_path, "uses:\n  modelling: {use: modelling}\n")
    assert "modelling" in p.model.spec.systems                              # the template's own system
    made = []
    real = rq.rid
    monkeypatch.setattr(rq, "rid", lambda s, c, a: made.append(a) or real(s, c, a))
    answer = said(("lab", "rewrite", "x"), ("../x", "split", "x"), ("ergostat", "redesign", "x"),
                  ("modelling", "merge", "x"), ("modelling", "redesign", "x"),
                  ("lab", "redesign", "first"), ("lab", "redesign", "again"),
                  ("a", "redesign", "x"), ("big", "redesign", "x"), ("ops", "redesign", "x"),
                  ("lab", "split", "x"), ("a", "split", "x"), ("big", "split", "x"), ("ops", "split", "x"),
                  ("lab", "merge", "ninth"))
    got = arv.run(p, "sonnet", 5.0, now=time.time(), call=answer)
    dropped = reviewed(p)[-1]["dropped"]
    for want in ("'rewrite'", "'../x'", "'ergostat'", "merge of 'modelling'", "redesign of 'modelling'",
                 "said again", "past the 8 findings"):
        assert any(want in d for d in dropped), (want, dropped)
    assert len(got["findings"]) == 8 and mine(p)["system.lab review-redesign"]["says"] == "first"
    assert {a.split(".", 1)[1] for a in made if a.startswith("system.")} <= {"lab", "a", "big", "ops"}
    assert "ninth" not in json.dumps(mine(p))
    long = said(("lab", "redesign", "w" * 5000))
    arv.run(p, "sonnet", 5.0, now=time.time() + DAILY + 1, call=long)
    assert len(mine(p)["system.lab review-redesign"]["says"]) == arv.SAYS


def test_a_finding_made_again_the_next_day_clears_what_the_last_one_left(tmp_path):
    p = four(tmp_path)
    t0 = time.time()
    arv.run(p, "sonnet", 5.0, now=t0, call=said(("lab", "redesign", "day one")))
    r = mine(p)["system.lab review-redesign"]
    arv.mark(p, {"id": r["id"], "stamp": r["review"]}, {"result": "proposed", "id": "c1"})
    assert rq.stored(p)[r["id"]]["state"] == "proposed" and rq.stored(p)[r["id"]]["change"] == "c1"
    rq.event(p, r["id"], "answered", {"why": "its redesign was refused"})
    arv.run(p, "sonnet", 5.0, now=t0 + DAILY + 1, call=said(("lab", "redesign", "day two")))
    x = rq.stored(p)[r["id"]]
    day2 = [e for e in p.events.query(n=None, type=arv.REVIEWED) if e["data"]["result"] == "started"][-1]["id"]
    assert x["state"] == "open" and x["change"] is None and x["why"] is None
    assert x["says"] == "day two" and x["review"] == day2 != r["review"]
    arv.run(p, "sonnet", 5.0, now=t0 + 2 * DAILY + 2, call=said(("lab", "redesign", "day three")))
    assert rq.stored(p)[r["id"]]["says"] == "day three"                     # said again while open: written again


def test_a_finding_not_said_again_is_let_go_but_one_waiting_on_its_change_is_kept(tmp_path):
    p = four(tmp_path)
    t0 = time.time()
    arv.run(p, "sonnet", 5.0, now=t0, call=said(("lab", "redesign", "x"), ("ops", "redesign", "y"), ("big", "split", "z")))
    o = mine(p)["system.ops review-redesign"]
    arv.mark(p, {"id": o["id"], "stamp": o["review"]}, {"result": "proposed", "id": "c1"})
    arv.run(p, "sonnet", 5.0, now=t0 + DAILY + 1, call=said(("a", "redesign", "w")))
    x = mine(p)
    assert x["system.lab review-redesign"]["state"] == "answered"
    assert "no longer says it" in x["system.lab review-redesign"]["why"]
    assert x["system.big review-split"]["state"] == "answered"
    assert x["system.ops review-redesign"]["state"] == "proposed" and x["system.a review-redesign"]["state"] == "open"


def test_a_redesign_does_not_mark_a_request_a_newer_review_re_raised(tmp_path, monkeypatch, capsys):
    p = four(tmp_path)
    t0 = time.time()
    arv.run(p, "sonnet", 5.0, now=t0 - DAILY - 10, call=said(("lab", "redesign", "old")))
    old = mine(p)["system.lab review-redesign"]["review"]

    def run(p_, system, why, **k):                    # between the plan's read and the mark: a newer review says it
        assert system == "lab"
        arv.run(p, "sonnet", 5.0, now=t0, call=said(("lab", "redesign", "new")))
        return {"system": system, "rounds": [], "cost": {"usd": 0.0, "calls": 0}, "version": "v",
                "result": "nothing proposed", "reports": []}
    monkeypatch.setattr(rdr, "run", run)
    block(monkeypatch, p)
    assert ml.redesign(["--when", "auto", "--review", "off", "--daily", "5"]) == 0
    x = mine(p)["system.lab review-redesign"]
    assert x["state"] == "open" and x["review"] != old and x["says"] == "new"
    assert "a newer review said it again" in capsys.readouterr().err


def test_a_redesign_marks_the_request_it_took_up(tmp_path, monkeypatch, capsys):
    p = four(tmp_path)
    arv.run(p, "sonnet", 5.0, now=time.time() - DAILY - 10, call=said(("lab", "redesign", "old")))
    seen = []
    monkeypatch.setattr(rdr, "run", nothing(seen))
    block(monkeypatch, p)
    assert ml.redesign(["--when", "auto", "--review", "off", "--daily", "5"]) == 0
    assert seen[0]["system"] == "lab"
    x = mine(p)["system.lab review-redesign"]
    assert x["state"] == "answered" and "nothing proposed" in x["why"]


def test_a_second_run_holding_no_lock_skips_the_review(tmp_path, monkeypatch, capsys):
    p = four(tmp_path)
    p.dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(md, "call", lambda *a, **k: pytest.fail("reviewed under another's lock"))
    seen = []
    monkeypatch.setattr(rdr, "run", nothing(seen))
    block(monkeypatch, p)
    with open(p.dir / "redesign.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        assert ml.redesign(["--when", "auto", "--review", "sonnet", "--daily", "5"]) == 0
    assert "another run holds redesign.lock" in capsys.readouterr().err
    assert seen and not reviewed(p)                                         # the redesign still goes ahead


def test_a_mark_under_another_runs_lock_leaves_the_request(tmp_path, monkeypatch, capsys):
    p = four(tmp_path)
    arv.run(p, "sonnet", 5.0, now=time.time() - DAILY - 10, call=said(("lab", "redesign", "old")))
    held = []

    def run(p_, system, why, **k):                    # another run's review takes the lock while this one works
        f = open(p.dir / "redesign.lock", "a")
        fcntl.flock(f, fcntl.LOCK_EX)
        held.append(f)
        return {"system": system, "rounds": [], "cost": {"usd": 0.0, "calls": 0}, "version": "v",
                "result": "nothing proposed", "reports": []}
    monkeypatch.setattr(rdr, "run", run)
    block(monkeypatch, p)
    try:
        assert ml.redesign(["--when", "auto", "--review", "off", "--daily", "5"]) == 0
    finally:
        for f in held:
            f.close()
    assert held and mine(p)["system.lab review-redesign"]["state"] == "open"
    assert "left unmarked: another run holds redesign.lock" in capsys.readouterr().err


def test_the_review_is_there_only_with_ai_and_off_turns_it_off(tmp_path, monkeypatch):
    from ergostat import model as mdl
    with_ai = "uses:\n  modelling:\n    use: modelling\n    with:\n      ai: true\n"
    p = four(tmp_path, with_ai)
    assert "--review sonnet" in p.model.spec.blocks["redesigner"].params["run"]
    assert rd.settings(p.model.spec)["review"] == "sonnet"
    off = four(tmp_path / "off", with_ai + "      redesign: {review: 'off'}\n")
    assert "--review off" in off.model.spec.blocks["redesigner"].params["run"] and rd.settings(off.model.spec)["review"] == "off"
    monkeypatch.setattr(md, "call", lambda *a, **k: pytest.fail("reviewed while off"))
    monkeypatch.setattr(rdr, "run", nothing([]))
    block(monkeypatch, off)
    assert ml.redesign(["--when", "auto", "--review", "off"]) == 0 and not reviewed(off)
    block(monkeypatch, p)
    rd.ask(p, "lab")
    assert ml.redesign(["--when", "ask", "--review", "sonnet"]) == 0 and not reviewed(p)
    assert ml.redesign(["--when", "off", "--review", "sonnet"]) == 0 and not reviewed(p)
    without = four(tmp_path / "noai", "uses:\n  modelling: {use: modelling}\n")
    assert "redesigner" not in without.model.spec.blocks
    whenoff = four(tmp_path / "whenoff", with_ai + "      redesign: {when: 'off'}\n")
    assert "redesigner" not in mdl.load(whenoff.model.path.parent).spec.blocks
    with pytest.raises(SystemExit):
        ml.redesign(["--review", "../x"])                                 # a model's name, or off: nothing else


def test_the_reviews_cost_is_printed_as_a_result_line_and_recorded_with_its_model(tmp_path, monkeypatch, capsys):
    p = four(tmp_path)
    call = said(("lab", "redesign", "x"), usd=0.042)
    monkeypatch.setattr(md, "call", call)
    monkeypatch.setattr(rdr, "run", nothing([]))
    block(monkeypatch, p)
    assert ml.redesign(["--when", "auto", "--review", "sonnet", "--daily", "5", "--timeout", "900", "--rounds", "2"]) == 0
    assert call.calls[0][1] == "sonnet" and call.calls[0][2] == md.per_call(900, 3)
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    assert [x["total_cost_usd"] for x in lines if x.get("type") == "result"] == [pytest.approx(0.042)]
    d = reviewed(p)[-1]
    assert d["result"] == "reviewed" and d["model"] == "sonnet" and d["cost"]["usd"] == pytest.approx(0.042)
    assert d["findings"] == [mine(p)["system.lab review-redesign"]["id"]]
