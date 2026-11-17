"""The gate a change to the model passes before it is tested (numbers/gate.py), what a change is classed as by what it
touches (improve.kind_of), evidence that must support the change and not only exist (improve.Evidence.supports), and
the memory of what was turned away (numbers/memory.py), SPEC §12e."""

from __future__ import annotations

import time

import pytest

from ergostat import model as mdl
from ergostat.numbers import gate as gt
from ergostat.numbers import improve as im
from ergostat.numbers import judge as jd
from ergostat.numbers import memory as mem
from ergostat.numbers import proposals as pr
from ergostat.numbers import review as rv
from ergostat.store import Project

from .test_numbers import write

TWO = """\
name: two
# two queues that never meet, each draining at its own rate; a goal holds the first
parameters:
  k:
    value: 2          # what we believe
    unit: 1/h
    estimate: true
  m:
    value: 1
    unit: 1/h
    estimate: true
stocks:
  queue:
    unit: jobs
    sensor:
      manual: true
  backlog:
    unit: jobs
    sensor:
      manual: true
flows:
  arrivals:
    to: queue
    sensor:
      manual: true
  served:
    from: queue
    driven-by: +stock.queue
    equation: k * stock.queue
  filed:
    to: backlog
    sensor:
      manual: true
  cleared:
    from: backlog
    driven-by: +stock.backlog
    equation: m * stock.backlog
goals:
  short-queue:
    stock: queue
    hold: "<= 20"
"""
LINE = "    value: 2          # what we believe"
HOLD = '    hold: "<= 20"'


def two_project(tmp_path, k_true=3.0, m_true=1.0, minutes=240, text=TWO):
    write(tmp_path, text)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    q = b = 0.0
    for i in range(minutes * 2 + 1):
        t = now - minutes * 60 + i * 30
        a = 10 + 5 * ((i // 20) % 2)
        f = 4 + 2 * ((i // 30) % 2)
        for ref, v in (("queue", q), ("arrivals", a), ("backlog", b), ("filed", f)):
            p.measurements.add(f"sensor/{ref}.main", v, at=t)
        for _ in range(30):
            q += (a - k_true * q) / 3600
            b += (f - m_true * b) / 3600
    return p


def k_to(v, reasons=None, parts=("parameter.k",)):
    return {"kind": "parameter", "parts": list(parts), "title": f"k is {v}",
            "edit": {"file": "ergostat.yaml", "replace": LINE, "with": LINE.replace("2 ", f"{v} ", 1)},
            "reasons": reasons or [{"says": "the replay of queue runs high", "evidence": "fit:stock.queue.um"}]}


# ---- what a change touches, and its neighbourhood

def test_a_parameter_touches_its_users_and_their_stocks_and_the_neighbourhood_is_one_link_on(tmp_path):
    p = two_project(tmp_path)
    spec = p.model.spec
    assert gt.touched(spec, ["parameter.k"]) == {"flow.served", "stock.queue"}
    near = gt.neighbourhood(spec, ["parameter.k"])
    assert {"flow.arrivals", "goal.short-queue", "parameter.k"} <= near
    assert not near & {"stock.backlog", "flow.cleared", "flow.filed"}           # the other queue is not near
    assert gt.stocks_of(spec, ["parameter.k"]) == ["stock.queue"]
    assert gt.stocks_of(spec, ["goal.short-queue"]) == ["stock.queue"]


# ---- the gate: the whole model and near what it touches, both said

def fit(total, **stocks):
    return {"total": {"nmse": total}, "stocks": {f"stock.{k}": {"nmse": v} for k, v in stocks.items()}}


def test_the_gate_refuses_what_worsens_the_whole_or_near_what_it_touches_and_says_both_numbers():
    import tempfile
    from pathlib import Path

    from ergostat.spec import read
    d = Path(tempfile.mkdtemp())
    spec, _ = read(write(d, TWO))
    g = gt.check(spec, fit(0.5, queue=0.1, backlog=0.9), fit(0.5, queue=0.3, backlog=0.7), ["parameter.k"])
    assert g["whole"]["before"] == g["whole"]["after"] == pytest.approx(0.5)     # the whole no worse ...
    assert g["worse"] == "near what it touches (stock.queue) 0.1 → 0.3, 3× worse; the whole model's scaled error 0.5 → 0.5, the same"
    g = gt.check(spec, fit(0.788, queue=0.2, backlog=1.376), fit(18.47, queue=0.1, backlog=36.84), ["parameter.k"])
    assert "the whole model's scaled error 0.788 → 18.5, 23.4× worse" in g["worse"]
    assert gt.check(spec, fit(0.5, queue=0.1, backlog=0.9), fit(0.45, queue=0.05, backlog=0.85), ["parameter.k"])["worse"] is None
    assert gt.summary(gt.check(spec, fit(0.5, queue=0.1, backlog=0.9), fit(0.45, queue=0.05, backlog=0.85), ["parameter.k"])) == \
        "whole model 0.5 → 0.45, 10% better; near what it touches (stock.queue) 0.1 → 0.05, 50% better"
    # like for like: a stock the change brings into the fit is not counted against it
    assert gt.check(spec, fit(0.1, queue=0.1), fit(0.5, queue=0.1, backlog=0.9), ["flow.cleared"])["worse"] is None


def test_ergostats_own_estimate_fitted_on_a_part_alone_is_refused_when_the_whole_model_gets_worse(tmp_path):
    """The owner's run: images-per-hour fitted on stock.paired alone, its objective there down 100%, and the whole
    replay 23 times worse. Refused before the judge sees it, with both numbers."""
    p = two_project(tmp_path)
    spec = p.model.spec
    x = {"id": "be3b9f3a", "kind": "parameter", "scope": "parts", "scope_words": "each part alone",
         "target": "parameter.k", "parameters": {"k": 2.4}, "previous": {"k": 2.0}, "parts": ["flow.served"],
         "touched": ["stock.queue"], "title": "k: 2 → 2.4", "objective": {"before": 151.73, "after": 0.635},
         "estimate": {"k": {"fitted_to": ["stock.queue"]}}, "edit": {"files": [], "diff": ""},
         "fit_before": fit(0.788, queue=0.2, backlog=1.376), "fit_after": fit(18.47, queue=0.1, backlog=36.84)}
    props = pr.stored(p)
    pr.admit(p, spec, props, [x], time.time(), 6 * 3600.0)
    pr.save(p, props)
    got = pr.stored(p)["be3b9f3a"]
    assert got["state"] == "refused" and got["gated"] and not pr.pending(p)
    assert got["why"] == ("it clearly worsens the fit: the whole model's scaled error 0.788 → 18.5, 23.4× worse; near what it "
                          "touches (stock.queue) 0.2 → 0.1, 50% better, though fitted each part alone, its weighted error on "
                          "stock.queue falls by 100% (152 → 0.635)")
    assert got["gate"]["said"].startswith("whole model 0.788 → 18.5, 23.4× worse")


def test_a_blocks_change_that_worsens_its_neighbourhood_is_refused_even_if_the_whole_is_no_worse(tmp_path):
    p = two_project(tmp_path)
    got = im.submit(p, "improver", k_to(40))
    assert got["status"] == "not-proposed" and got["why"].startswith("it clearly worsens the fit:")
    assert "near what it touches (stock.queue)" in got["why"] and "whole model" in got["why"]
    assert pr.stored(p)[got["id"]]["gated"]


def test_benefit_never_shows_a_worse_number_as_a_gain(tmp_path, capsys, monkeypatch):
    from ergostat.cli import main
    p = two_project(tmp_path)
    x = {"kind": "parameter", "fit_before": fit(7.23), "fit_after": fit(181.0), "touched": []}
    b = rv._benefit(x)
    assert b["better"] is False and b["said"] == "whole model 7.23 → 181, 25× worse"
    assert rv._benefit({**x, "fit_after": fit(3.0)})["better"] is True
    got = im.submit(p, "improver", k_to(3))                                 # nearer the truth: better
    assert got["status"] == "proposed", got
    monkeypatch.chdir(tmp_path)
    assert main(["proposals"]) == 0
    out = capsys.readouterr().out
    assert "benefit  scaled error, whole model" in out and "better" in out


# ---- what a change is: a goal, a sensor, a block are not parameters

def test_a_goal_edit_is_a_control_change_and_never_judged_or_written_by_the_judge(tmp_path):
    p = two_project(tmp_path, text=TWO + "blocks:\n  judge:\n    type: judge\n    accept: auto\n    hold-out: 10m\n")
    goal = {"kind": "parameter", "parts": ["goal.short-queue"], "title": "a looser goal",
            "edit": {"file": "ergostat.yaml", "replace": HOLD, "with": HOLD.replace("20", "200")}}
    # the review's trial: one rule cited, nothing that supports it
    got = im.submit(p, "improver", {**goal, "reasons": [{"says": "it is never met", "evidence": "rule:behaviour-reproduction"}]})
    assert got["status"] == "not-proposed" and "no reason with evidence that supports it" in got["why"], got
    assert im.trial(p, {**goal, "reasons": [{"says": "x", "evidence": "rule:behaviour-reproduction"}]})["would"] == "not be proposed"
    got = im.submit(p, "improver", {**goal, "reasons": [{"says": "the queue runs high", "evidence": "fit:stock.queue.um"}]},
                    at=time.time() - 3 * 3600)
    x = pr.stored(p)[got["id"]]
    assert got["status"] == "proposed" and x["kind"] == "control" and x["target"] == "goal.short-queue"
    out = jd.run(p, "judge")
    assert out["accepted"] == 0 and pr.stored(p)[got["id"]]["state"] == "checked"   # the owner's: not judged, not written


def test_a_sensor_edit_is_a_measurement_change(tmp_path):
    p = two_project(tmp_path)
    spec = p.model.spec
    raw = {"kind": "parameter", "parts": ["stock.queue"], "title": "read the queue every minute",
           "edit": {"file": "ergostat.yaml", "replace": "  queue:\n    unit: jobs\n    sensor:\n      manual: true",
                    "with": "  queue:\n    unit: jobs\n    sensor:\n      run: bin/read queue\n      every: 1m"},
           "reasons": [{"says": "the queue moves fast", "evidence": "fit:stock.queue.r2"}]}
    from ergostat.numbers import trial as tr
    after = tr.spec_after(p, im.edits(spec, raw["edit"]))
    assert im.kind_of(spec, after, "parameter") == "measurement"
    assert im.kind_of(spec, tr.spec_after(p, im.edits(spec, k_to(3)["edit"])), "structure") == "parameter"


# ---- evidence that supports, not evidence that exists

def test_ten_unsupported_reasons_are_each_refused(tmp_path):
    rate_on_rate = "    driven-by:\n      - +stock.backlog\n      - flow.filed\n"
    p = two_project(tmp_path, text=TWO.replace("    driven-by: +stock.backlog\n", rate_on_rate))
    (tmp_path / "notes.md").write_text("k is the rate the queue drains at\n")
    spec = p.model.spec
    away = "rate-driven-by-rate@flow.cleared"
    assert away in im.Evidence(p, spec).findings()
    unsupported = [
        "rule:behaviour-reproduction",                 # a rule check does not test: cited only
        "rule:parameter-assessment",
        "rule:first-order-drain",
        "notes.md:1",                                  # a line: cited only
        "docs/MODELLING.md:1",
        "https://example.org/sterman",                 # a URL: cited only
        "fit:stock.backlog.r2",                        # a statistic of a part the change does not touch
        "fit:total.nmse",                              # the total, which the change raises (k to 40)
        f"finding:{away}",                             # a finding about a part it does not touch
        "rule:" + away.split("@")[0],                  # a rule check applies, but elsewhere
    ]
    assert len(unsupported) == 10
    for ev in unsupported:
        v = 40 if ev == "fit:total.nmse" else 3
        raw = k_to(v, [{"says": "because", "evidence": ev}])
        got = im.trial(p, raw) if ev != "fit:total.nmse" else im.submit(p, "improver", raw)
        why = got.get("why") or ""
        assert "not" in (got.get("would") or got.get("status")) and \
            ("supports it" in why or "clearly worsens" in why), (ev, got)
    for ev in ("fit:stock.queue.um", "fit:total.nmse", "fit:stock.queue.r2"):
        assert im.trial(p, k_to(3, [{"says": "because", "evidence": ev}]))["would"] == "be proposed", ev


# ---- memory: what was turned away is not proposed again until the record has grown

def test_a_target_turned_away_is_held_back_counted_on_one_item_and_tried_again_once_the_record_grows(tmp_path):
    p = two_project(tmp_path)
    spec = p.model.spec
    now = time.time()
    first = im.submit(p, "improver", k_to(40), run="r1", at=now)
    assert first["status"] == "not-proposed"
    for i, v in enumerate((41, 39, 42), start=2):            # slightly different each time, every few minutes
        got = im.submit(p, "improver", k_to(v), run=f"r{i}", at=now + 180 * i)
        assert got["status"] == "not-proposed" and got["why"].startswith("held back:") and got["id"] == first["id"]
    xs = [x for x in pr.stored(p).values() if x.get("made_by") == "improver"]
    assert len(xs) == 1                                       # one item, with a count
    x = xs[0]
    assert x["repeats"] == 3 and x["held_until"] > now and x["held_back"].startswith("proposed again 3 times, held back until ")
    h = mem.held(p, spec, x["key"], now)
    assert h["wait"] == pytest.approx(max(mem.MIN_WAIT, mem.GROW * x["window"]))
    later = im.submit(p, "improver", k_to(40), run="r9", at=h["until"] + 1)     # the record grew: tried again
    assert later["status"] == "not-proposed" and later["id"] != first["id"] and later["why"].startswith("it clearly worsens")
    h2 = mem.held(p, spec, x["key"], h["until"] + 2)
    assert h2["times"] == 2 and h2["wait"] >= 2 * h["wait"]                     # backed off: twice as long, at least
    malformed = im.submit(p, "improver", {**k_to(3), "edit": {"file": "ergostat.yaml", "replace": "nope", "with": "x"}},
                          at=h["until"] + 3)
    assert "found 0 times" in malformed["why"]                # a proposal refused for its form is said so, never held


def test_ergostats_own_finders_are_held_back_too_and_a_model_change_lets_them_go(tmp_path):
    p = two_project(tmp_path)
    spec = p.model.spec
    now = time.time()

    def found(v):
        return {"id": f"x{v}", "kind": "parameter", "scope": "parts", "target": "parameter.k", "parts": ["flow.served"],
                "touched": ["stock.queue"], "title": f"k: 2 → {v}", "parameters": {"k": v}, "previous": {"k": 2.0},
                "edit": {"files": [], "diff": ""}, "fit_before": fit(0.5, queue=0.1), "fit_after": fit(5.0, queue=1.0)}
    for i, v in enumerate((2.5, 2.6, 2.7)):
        props = pr.stored(p)
        pr.admit(p, spec, props, [found(v)], now + 60 * i, 3600.0)
        pr.save(p, props)
    xs = [x for x in pr.stored(p).values() if x.get("target") == "parameter.k"]
    assert [x["id"] for x in xs] == ["x2.5"] and xs[0]["repeats"] == 2 and "proposed again 2 times" in xs[0]["held_back"]
    write(tmp_path, TWO.replace("    value: 1\n", "    value: 1.5\n", 1))           # the model changed: let go
    p.model = mdl.load(tmp_path)
    assert mem.held(p, p.model.spec, xs[0]["key"], now + 120) is None
