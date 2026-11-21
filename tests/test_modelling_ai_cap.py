"""modelling-improves-the-model's acceptance tests (docs/roadmap/overnight/modelling-improves-the-model.md): the AI
tier's daily cap, checked before every call (the go-back too) and held through it; what a capped run leaves alone;
charges by reservation, settled by id; a ledger that cannot be read means no call; ceilings on its counts and dollars,
at config time and at run time; the status says the cap."""

from __future__ import annotations

import fcntl
import io
import json
import multiprocessing as mp
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ergostat.library import expand as ex
from ergostat.library import templates as tp
from ergostat.library.run import modelling as ml
from ergostat.numbers import improve as im
from ergostat.numbers import modeller as md
from ergostat.numbers import modeller_spend as sp
from ergostat.numbers import modelling_status as ms
from ergostat.numbers import requests as rq

from .test_self_improve import POOR
from .test_self_improve import project as poor_project

MODELLING = "uses:\n  modelling:\n    use: modelling\n    with:\n      fit: 0.05\n      ai: true\n"


def _project(tmp_path, monkeypatch, text=POOR + MODELLING):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = poor_project(tmp_path, text)
    monkeypatch.setattr(ml, "project", lambda: p)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    rq.sync(p)
    assert _waiting(p)
    return p


def _waiting(p, tries=2):
    return [r for r in rq.waiting(p, ("open", "held")) if r.get("tier") == "ai" and not r.get("owner")
            and int((r.get("tried") or {}).get("ai") or 0) < tries]


def _reservation(p, most=8):
    """The first call's reservation, as ``ml.ai`` makes it: the prompt of the group it would send."""
    group = ml._near(p, _waiting(p))[:most]
    return md.unsaid(md.prompt(p, p.model.spec, group), "haiku")["usd"], [r["id"] for r in group]


class Stand:
    """The AI: counts its calls, reports ``usd`` (or raises), answers ``result``."""

    def __init__(self, usd=0.01, result="", raises=None):
        self.usd, self.result, self.raises, self.calls = usd, result, raises, []

    def __call__(self, text, model, timeout=600.0):
        self.calls.append(text)
        if self.raises:
            raise self.raises
        return {"result": self.result, "usd": self.usd, "tokens_in": 10, "tokens_out": 10, "seconds": 0.0}


def _ledger(p) -> Path:
    d = Path(p.dir) / "modelling"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ai-spend.jsonl"


def _write(p, *rows, raw: str = ""):
    _ledger(p).write_text("".join(json.dumps(r) + "\n" for r in rows) + raw)


def _rows(p):
    return [json.loads(x) for x in _ledger(p).read_text().splitlines()] if _ledger(p).exists() else []


def _state(p, ids):
    got = rq.stored(p)
    return {i: (got[i]["state"], dict(got[i].get("tried") or {}), got[i].get("cost_usd"), got[i].get("why")) for i in ids}


def _run(*extra):
    return ml.ai(["--model", "haiku", *extra])


def test_a_call_starts_only_within_the_days_cap(tmp_path, monkeypatch, capsys):
    p = _project(tmp_path, monkeypatch)
    ai = Stand(usd=0.001)
    monkeypatch.setattr(md, "call", ai)
    R, _ = _reservation(p)
    S = 0.5
    _write(p, {"id": "old", "time": time.time() - 100, "reserved": S}, {"id": "old", "usd": S})
    assert _run("--daily", f"{S + R / 2:.6f}") == 0           # spent < daily, but spent + reserved > daily
    assert ai.calls == [] and "would pass it" in capsys.readouterr().err
    assert _run("--daily", f"{S + R + 0.001:.6f}") == 0
    assert len(ai.calls) == 1
    new = [r for r in _rows(p) if r.get("id") not in (None, "old")]
    assert len(new) == 2 and new[0]["id"] == new[1]["id"] and new[0]["reserved"] == pytest.approx(R)
    assert new[1]["usd"] == pytest.approx(0.001)


def test_the_go_back_checks_the_cap_again(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch)
    R, ids = _reservation(p)
    line = json.dumps({"propose": {"title": "t", "kind": "description", "reasons": [{"says": "x", "evidence": "e"}]}})
    ai = Stand(usd=R, result=line)                    # leaves less than the go-back's reservation under the cap
    monkeypatch.setattr(md, "call", ai)
    monkeypatch.setattr(im, "trial", lambda p, raw: {"would": "not be proposed", "why": "turned away"})
    before = _state(p, ids)
    assert _run("--daily", f"{R * 1.5:.6f}") == 0
    assert len(ai.calls) == 1
    assert len([r for r in _rows(p) if "id" in r and "reserved" in r]) == 1
    assert any("refused" in r for r in _rows(p))
    for i, (_, tried, *_) in _state(p, ids).items():
        assert tried.get("ai") == int(before[i][1].get("ai") or 0) + 1


def test_the_go_back_is_made_within_the_cap(tmp_path, monkeypatch):
    """The other side: with room for both, the go-back is made, so the test above reaches the second call."""
    p = _project(tmp_path, monkeypatch)
    R, _ = _reservation(p)
    line = json.dumps({"propose": {"title": "t", "kind": "description", "reasons": [{"says": "x", "evidence": "e"}]}})
    ai = Stand(usd=0.001, result=line)
    monkeypatch.setattr(md, "call", ai)
    monkeypatch.setattr(im, "trial", lambda p, raw: {"would": "not be proposed", "why": "turned away"})
    assert _run("--daily", "20") == 0
    assert len(ai.calls) == 2 and "turned away" in ai.calls[1]
    assert len([r for r in _rows(p) if "reserved" in r and "id" in r]) == 2


def test_a_failed_call_is_not_tried_again_in_the_run(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch)
    calls = []

    def slow(cmd, input=None, **k):
        calls.append(input)
        raise subprocess.TimeoutExpired(cmd, k.get("timeout"))
    monkeypatch.setattr(subprocess, "run", slow)
    monkeypatch.setenv("ERGOSTAT_AI", "stand-in")
    assert _run("--daily", "20") == 0
    assert len(calls) == 1
    settle = [r for r in _rows(p) if "usd" in r]
    assert len(settle) == 1 and settle[0]["estimated"] is True
    assert settle[0]["usd"] == pytest.approx(md.unsaid(calls[0], "haiku")["usd"]) and settle[0]["usd"] > 0


def test_the_next_run_checks_the_cap_and_a_capped_run_burns_no_try(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch)
    R, _ = _reservation(p)
    ai = Stand(usd=R * 0.9)
    monkeypatch.setattr(md, "call", ai)
    daily = f"{R * 1.5:.6f}"
    assert _run("--daily", daily, "--tries", "3") == 0 and len(ai.calls) == 1
    R2, ids = _reservation(p, 8)
    assert R * 0.9 + R2 > R * 1.5
    before = _state(p, [r["id"] for r in _waiting(p, 3)])
    assert _run("--daily", daily, "--tries", "3") == 0
    assert len(ai.calls) == 1 and _state(p, list(before)) == before


def test_a_call_that_costs_more_than_its_reservation_is_charged_what_it_said(tmp_path, monkeypatch, capsys):
    p = _project(tmp_path, monkeypatch)
    R, _ = _reservation(p)
    S = 0.25
    _write(p, {"id": "old", "time": time.time() - 100, "reserved": S}, {"id": "old", "usd": S})
    ai = Stand(usd=3 * R)
    monkeypatch.setattr(md, "call", ai)
    daily = f"{S + 2 * R:.6f}"
    assert _run("--daily", daily) == 0 and len(ai.calls) == 1
    assert sp.spent(p) == pytest.approx(S + 3 * R)
    assert f"over its ${R:.4f} reservation" in capsys.readouterr().err
    assert _run("--daily", daily) == 0 and len(ai.calls) == 1
    assert ms.of(p)["ai_spent"] == pytest.approx(S + 3 * R)


def test_the_reservation_is_claudes_budget(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch)
    monkeypatch.delenv("ERGOSTAT_AI", raising=False)
    got = []

    def run(cmd, input=None, **k):
        got.append((cmd, input))
        return SimpleNamespace(stdout=json.dumps({"result": "", "total_cost_usd": 0.001}), returncode=0)
    monkeypatch.setattr(subprocess, "run", run)
    assert _run("--daily", "20") == 0
    (cmd, text), = got
    assert cmd[0] == "claude"
    assert cmd[cmd.index("--max-budget-usd") + 1] == f"{md.unsaid(text, 'haiku')['usd']:.6f}"
    assert [r["reserved"] for r in _rows(p) if "reserved" in r] == [md.unsaid(text, "haiku")["usd"]]


@pytest.mark.parametrize("bad", [
    "not json\n",
    json.dumps({"id": "a", "time": 1.0}) + "\n",                         # a reservation missing reserved
    json.dumps({"id": "a", "usd": "0.5"}) + "\n",                        # not a number
    '{"id": "a", "time": 1.0, "reserved": NaN}\n',
    '{"id": "a", "usd": Infinity}\n',
    json.dumps({"id": "a", "time": 4.0e9, "reserved": -1.0}) + "\n",     # in the window (future), still bad
    json.dumps({"id": "a", "usd": -0.5}) + "\n",
])
def test_an_unreadable_ledger_means_no_call(tmp_path, monkeypatch, capsys, bad):
    p = _project(tmp_path, monkeypatch)
    ai = Stand()
    monkeypatch.setattr(md, "call", ai)
    good = {"id": "z", "time": time.time() - 50, "reserved": 0.01}
    _write(p, good, raw=bad)
    assert _run("--daily", "20") == 0
    assert ai.calls == [] and "cannot be read" in capsys.readouterr().err
    assert "spend ledger cannot be read: no AI call" in ms.of(p)["says"]
    _ledger(p).unlink()                                                  # a missing ledger is an empty one
    assert _run("--daily", "20") == 0 and len(ai.calls) == 1


def test_a_half_written_last_line_is_left_out_by_the_status_only(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch)
    _write(p, {"id": "z", "time": time.time() - 50, "reserved": 0.01}, raw='{"id": "y", "ti')
    assert ms.of(p)["ai_spent"] == pytest.approx(0.01)
    with pytest.raises(sp.Capped, match="cannot be read"):
        sp.rows(p)


def test_a_daily_of_0_or_a_reservation_of_0_makes_no_call(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch)
    ai = Stand()
    monkeypatch.setattr(md, "call", ai)
    assert _run("--daily", "0") == 0 and ai.calls == []
    monkeypatch.setattr(md, "unsaid", lambda text, model: {"usd": 0.0, "tokens_in": 0, "tokens_out": 0, "estimated": True})
    assert _run("--daily", "0") == 0 and ai.calls == []
    assert _run("--daily", "20") == 0 and ai.calls == []                # a reservation of 0 is never a pass
    assert not [r for r in _rows(p) if "reserved" in r and "id" in r]


def test_a_call_left_unsettled_counts_whole(tmp_path):
    p = SimpleNamespace(dir=tmp_path)
    now = time.time()
    _write(p, {"id": "a", "time": now - 10, "reserved": 0.3}, {"id": "b", "time": now - 5, "reserved": 0.2},
           {"id": "b", "usd": 0.05})
    assert sp.spent(p, now) == pytest.approx(0.35)


def test_a_charge_is_dated_by_its_reservation(tmp_path):
    p = SimpleNamespace(dir=tmp_path)
    now = time.time()
    _write(p, {"id": "a", "time": now - 86400 - 10, "reserved": 0.4},
           {"id": "b", "time": now - 100, "reserved": 0.2},
           {"id": "a", "usd": 0.1},                                     # settled within the day: still a's, out of it
           {"id": "b", "usd": 0.07})
    assert sp.spent(p, now) == pytest.approx(0.07)
    _write(p, {"id": "a", "time": now - 86400 - 10, "reserved": 0.4}, {"id": "a", "usd": 0.1})
    assert sp.spent(p, now) == 0.0


def test_a_reservation_dated_in_the_future_counts(tmp_path):
    p = SimpleNamespace(dir=tmp_path)
    now = time.time()
    _write(p, {"id": "a", "time": now + 3600, "reserved": 0.4})                 # the clock stepped back since
    assert sp.spent(p, now) == pytest.approx(0.4)


def _one(root: str, ready, started, release, out):
    p = SimpleNamespace(dir=Path(root))
    ready.set()                                          # up and about to ask for the lock
    try:
        with sp.held(p, 0.5, 0.5) as box:
            started.set()
            release.wait(20)
            box.append({"usd": 0.5})
        out.put("called")
    except sp.Capped:
        out.put("capped")


def test_two_runs_cannot_both_take_the_last_of_the_cap(tmp_path):
    ctx = mp.get_context("spawn")                        # not fork: the pytest worker has other tests' threads
    started_a, started_b, release, out = ctx.Event(), ctx.Event(), ctx.Event(), ctx.Queue()
    ready_a, ready_b = ctx.Event(), ctx.Event()
    a = ctx.Process(target=_one, args=(str(tmp_path), ready_a, started_a, release, out))
    b = None
    a.start()
    try:
        assert started_a.wait(20)
        with open(tmp_path / "modelling" / "ai-spend.lock", "a") as lk:      # the lock is held through the call
            with pytest.raises(BlockingIOError):
                fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        b = ctx.Process(target=_one, args=(str(tmp_path), ready_b, started_b, release, out))
        b.start()
        assert ready_b.wait(20)
        assert not started_b.wait(1.0)                    # b waits for the lock while a is mid-call
        release.set()
        a.join(20)
        b.join(20)
    finally:
        release.set()
        for x in (a, b):
            if x is not None:
                x.join(5)
                if x.is_alive():
                    x.kill()
                    x.join(5)
    got = sorted(out.get(timeout=5) for _ in range(2))
    p = SimpleNamespace(dir=tmp_path)
    assert got == ["called", "capped"]
    assert len([r for r in _rows(p) if "reserved" in r and "id" in r]) == 1


def test_ai_counts_and_dollars_have_a_ceiling(tmp_path, monkeypatch):
    t = tp.find_all()[0]["modelling"]
    with pytest.raises(ex.ExpandError, match="max: 16"):
        ex.expand(t, "modelling", {"ai-most": 500})
    with pytest.raises(ex.ExpandError, match="max: 20"):
        ex.expand(t, "modelling", {"ai-daily": 1000})
    made = ex.expand(t, "modelling", {"ai": True, "ai-most": 16, "ai-daily": 20})
    assert "--most 16 --daily 20" in json.dumps(made.__dict__, default=str)
    f = tmp_path / "t.yaml"
    f.write_text("template: bounded\nparams:\n  n: {type: integer, default: 2, min: 1, max: 3}\n"
                 "parameters:\n  n-is:\n    value: ${n}\n")
    b = tp.read(f, False)
    with pytest.raises(ex.ExpandError, match="max: 3"):
        ex.expand(b, "x", {"n": 4})
    with pytest.raises(ex.ExpandError, match="min: 1"):
        ex.expand(b, "x", {"n": 0})
    ex.expand(b, "x", {"n": 3})
    p = _project(tmp_path / "m", monkeypatch)
    ai = Stand()
    monkeypatch.setattr(md, "call", ai)
    for bad in (["--most", "500", "--daily", "1"], ["--tries", "9", "--daily", "1"], ["--daily", "1000"], [],
                ["--daily", "nan"], ["--most", "0", "--daily", "1"]):
        with pytest.raises(SystemExit) as e:
            _run(*bad)
        assert e.value.code == 2 and ai.calls == []
    assert _run("--most", "16", "--tries", "3", "--daily", "20") == 0 and len(ai.calls) == 1
    assert p


def test_the_status_says_the_cap(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(md, "call", Stand())
    assert "of its $" not in ms.of(p)["says"]
    assert _run("--daily", "0") == 0                                     # refused for the cap
    got = ms.of(p)                                                       # the cap the block runs with (ai-daily: 1)
    assert "the AI tier has spent $0.0000 of its $1.00 today" in got["says"]
    assert got["ai_spent"] == 0.0 and got["ai_daily"] == 1.0
    (tmp_path / "off").mkdir()
    off = poor_project(tmp_path / "off", POOR + MODELLING.replace("ai: true", "ai: false"))
    got = ms.of(off)
    assert "spent" not in got["says"] and got["ai_spent"] is None
