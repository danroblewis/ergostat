"""The extreme-conditions tests with the loops running, kept per part and run in the background; calibration per
part; and proposals that state the behaviour they predict, held against what happened (docs/roadmap/overnight/extremes.md)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import spec as sp
from ergostat.numbers import extremes as ex
from ergostat.numbers import extremes_cache as xc
from ergostat.numbers import fit as ft
from ergostat.numbers import judge as jd
from ergostat.numbers import predict as pd
from ergostat.numbers import proposals as pr
from ergostat.numbers import review as rv
from ergostat.numbers import simulate as sim
from ergostat.spec.findings import late
from ergostat.store import Project

from .test_numbers import QUEUE, queue_project, write

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def found(spec) -> list[tuple[str, str]]:
    out = []
    ex.findings(spec, lambda c, msg, where, about: out.append((about, msg)))
    return out


def fresh_process():
    """As a new process finds it: nothing in memory, only what was kept on disk."""
    xc._JOBS.clear()
    xc._MEM.clear()


def counting(monkeypatch) -> list[str]:
    ran: list[str] = []
    real = ex.condition_result

    def counted(spec, cond, params, scales):
        ran.append(cond.key)
        return real(spec, cond, params, scales)
    monkeypatch.setattr(ex, "condition_result", counted)
    return ran


TWO = (QUEUE + """\
  fill:
    to: other
    sensor:
      manual: true
  leak:
    from: other
    driven-by: +stock.other
    equation: stock.other / two-hours
""").replace("parameters:\n", "parameters:\n  two-hours: 2h\n").replace(
    "stocks:\n", "stocks:\n  other:\n    unit: jobs\n    sensor:\n      manual: true\n")


def test_a_stock_that_goes_negative_at_zero_inflow_is_caught(tmp_path):
    spec, _ = sp.read(write(tmp_path, QUEUE.replace("equation: k * stock.queue", "equation: k * 5")), extremes=False)
    got = found(spec)
    neg = [m for a, m in got if a == "stock.queue" and "falls below empty" in m]
    assert neg and "flow.arrivals at 0" in neg[0] and "the projection, with the loops running: from " in neg[0], got
    assert "everything as usual" not in neg[0]                          # 10 in, 10 out as usual: only at zero inflow
    assert any(a == "flow.served" and "takes more than the stock holds" in m for a, m in got), got
    spec, _ = sp.read(write(tmp_path, QUEUE), extremes=False)
    assert not found(spec)                                               # first-order: it stops when empty


def test_a_model_that_runs_away_at_ten_times_its_input_is_caught(tmp_path):
    text = QUEUE.replace("""    driven-by: +stock.queue
    equation: k * stock.queue
""", """    driven-by: +stock.queue
    equation: k * stock.queue
  copies:
    to: queue
    driven-by: [+stock.queue, +flow.arrivals]
    equation: stock.queue * flow.arrivals / 10
""")
    spec, probs = sp.read(write(tmp_path, text), extremes=False)
    assert not [p for p in probs if p.level == "error"], [str(p) for p in probs if p.level == "error"]
    got = found(spec)
    away = [m for _, m in got if "flow.arrivals at 10 times its largest" in m and ("runs away" in m or "blows up" in m)]
    assert away and not [m for _, m in got if "everything as usual" in m], got


def test_a_pool_at_zero_and_a_setpoint_at_its_limit_run_with_the_loops_running():
    spec, _ = sp.read(EXAMPLES / "first-loop" / "ergostat.yaml", extremes=False)
    pl = sim.plan(spec)
    conds = {c.key: c for c in ex.conditions(spec, pl)}
    assert {"goal.inbox-short=low", "goal.inbox-short=high"} <= set(conds)
    as_usual = ex._run(spec, pl, conds["usual"], None).values["stock.inbox"][-1]
    pushed = ex._run(spec, pl, conds["goal.inbox-short=low"], None).values["stock.inbox"][-1]
    assert as_usual == 10 and pushed < 0.5                    # held at 20: left at 10; held at 0: the worker drains it
    spec, _ = sp.read(EXAMPLES / "image-squeeze" / "ergostat.yaml", extremes=False)
    pools = [c for c in ex.conditions(spec, sim.plan(spec)) if c.pools]
    assert pools and all(c.key.endswith("=empty-pool") for c in pools)
    run = ex._run(spec, sim.plan(spec), pools[0], None)
    took = [r for r, m in run.models.items() if m.block == pools[0].pools[0]]
    assert took and all(not any(run.values[r]) for r in took)          # no server: nothing taken


def test_a_second_check_is_fast_from_the_cache(tmp_path, monkeypatch):
    write(tmp_path, TWO)
    Project(mdl.load(tmp_path))                                          # its state directory: where they are kept
    spec, _ = sp.read(tmp_path / "ergostat.yaml", extremes=False)
    ran = counting(monkeypatch)
    first = [p.message for p in late(spec)]
    assert ran and (xc._path(spec)).is_file()
    fresh_process()
    ran.clear()
    t = time.monotonic()
    again = [p.message for p in late(sp.read(tmp_path / "ergostat.yaml", extremes=False)[0])]
    assert not ran and again == first and time.monotonic() - t < 0.5


def test_an_edit_reruns_only_the_conditions_of_the_part_it_changed(tmp_path, monkeypatch):
    write(tmp_path, TWO)
    Project(mdl.load(tmp_path))
    late(sp.read(tmp_path / "ergostat.yaml", extremes=False)[0])
    fresh_process()
    ran = counting(monkeypatch)
    write(tmp_path, TWO.replace("  two-hours: 2h\n", "  two-hours: 3h\n"))
    late(sp.read(tmp_path / "ergostat.yaml", extremes=False)[0])
    assert ran and not [k for k in ran if "arrivals" in k or "parameter.k" in k], ran
    assert {"flow.fill=0", "parameter.two-hours=low"} <= set(ran), ran


def test_the_check_status_says_extremes_running_until_they_are_done(tmp_path, monkeypatch):
    write(tmp_path, QUEUE.replace("equation: k * stock.queue", "equation: k * 5"))
    real = ex.condition_result
    monkeypatch.setattr(ex, "condition_result", lambda *a: (time.sleep(0.05), real(*a))[1])
    m = mdl.load(tmp_path)
    first = mdl.check(m)
    assert any(lv == "info" and msg.startswith("extremes: running (") for lv, msg in first), first
    for _ in range(400):
        if not any(lv == "info" for lv, _ in mdl.check(m)):
            break
        time.sleep(0.02)
    done = mdl.check(m)
    assert not any(lv == "info" for lv, _ in done) and any("falls below empty" in msg for lv, msg in done if lv == "warn")
    fresh_process()                                     # with a state directory: in a process of its own, at a low priority
    Project(mdl.load(tmp_path))
    (tmp_path / "ergostat.yaml").write_text((tmp_path / "ergostat.yaml").read_text().replace("k * 5", "k * 6"))
    m = mdl.load(tmp_path)
    first = mdl.check(m)
    job = next(iter(xc._JOBS.values()))
    assert job.proc is not None and any(msg.startswith("extremes: running") for lv, msg in first if lv == "info")
    job.proc.wait(timeout=60)
    job.thread.join(timeout=10)
    assert any("falls below empty" in msg for lv, msg in mdl.check(m) if lv == "warn")


def test_an_equation_that_fits_worse_than_its_mean_is_a_finding_and_its_panel_says_so(tmp_path):
    text = QUEUE.replace("    driven-by: +stock.queue\n", "    driven-by: +stock.queue\n    sensor:\n      manual: true\n")
    p, snap = queue_project(tmp_path, text=text)
    now = snap["at"]
    for i in range(241):                                             # served as measured: steady, whatever the queue
        p.measurements.add("sensor/served.main", 3.0 + (i % 2) * 0.2, at=now - 7200 + i * 30)
    _, _, fit = ft.compute(p, snap)
    s = fit["partial"]["flow.served"]
    assert s["skill"] < 0 and ft._slim(s)["skill"] == round(s["skill"], 6)
    got = ft.worse_than_mean(p.model.spec, fit)
    assert [r for r, _ in got] == ["flow.served"] and "worse than holding it at its mean" in got[0][1]
    from ergostat.cli.spec_cmds import calibration
    assert [x.code for x in calibration(tmp_path / "ergostat.yaml")] == ["calibration-worse-than-mean"]


def _accepted(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    pr.make(p, snap)
    x = next(x for x in pr.pending(p) if x["kind"] == "parameter")
    return p, snap, x


def test_a_proposal_carries_its_prediction(tmp_path):
    p, snap, x = _accepted(tmp_path)
    d = rv.effect(p, p.model.spec, [x])
    said = d["predicts"]["said"]
    assert said.startswith("queue settles at ") and " instead of " in said and "projected over" in said, said
    assert d["predicts"]["stocks"]["stock.queue"]["after"] < d["predicts"]["stocks"]["stock.queue"]["before"]   # k 2 → 3
    pr.accept(p, x["id"], snap)
    kept = pr.stored(p)[x["id"]]
    was, now = d["predicts"]["stocks"]["stock.queue"], kept["predicted"]["stocks"]["stock.queue"]
    assert kept["status"] == "accepted" and now["after"] == pytest.approx(was["after"], rel=0.02)
    assert kept["predicted"]["horizon"] > 0 and kept["predicted"]["at"] == snap["at"]


def test_the_prediction_is_compared_with_what_happened_after_acceptance(tmp_path):
    p, snap, x = _accepted(tmp_path)
    pr.accept(p, x["id"], snap)
    w = pr.stored(p)[x["id"]]["predicted"]
    assert pd.observe(p, snap["at"] + 1) == 0                            # its horizon not passed: nothing yet
    end = w["at"] + w["horizon"]
    for i in range(10):                                                  # what the queue did after
        p.measurements.add("sensor/queue.main", 3.4, at=w["at"] + (i + 1) * w["horizon"] / 10)
    got = jd.run(p, at=end + 1)
    assert got["observed"] == 1
    kept = pr.stored(p)[x["id"]]
    assert kept["observed"]["stocks"]["stock.queue"] == 3.4 and "predicted" in kept["observed"]["said"]
    assert "observed 3.4" in kept["observed"]["said"] and "nearer" in kept["observed"]["said"]
    assert jd.run(p, at=end + 2)["observed"] == 0                        # once
