"""A remote's parts are data here (SPEC §4c): its stocks are given, never integrated, in the replay and the
projection; the fit's total, the residuals and what the record has not exercised leave them out. A local model
composing a planted remote cache (as tests/test_remote_chain.py and tests/test_remote_proposals.py do), with
recorded readings."""

from __future__ import annotations

import time

import pytest

from ergostat import model as mdl
from ergostat.numbers import closedloop as cl
from ergostat.numbers import exercised as ex
from ergostat.numbers import fit as ft
from ergostat.numbers import observe as ob
from ergostat.numbers import residuals as rs
from ergostat.numbers import simulate as sim
from ergostat.store import Project
from tests.test_remote import served_into, write

REM = """\
name: incidents
parameters:
  drain-time: {value: 1h}
stocks:
  queue:
    unit: jobs
    sensor: {manual: true}
flows:
  arrivals:
    to: queue
    sensor: {manual: true}
  served:
    from: queue
    driven-by: +stock.queue
    equation: stock.queue / drain-time
"""
LOCAL = """\
name: support
remotes:
  incidents:
    url: http://127.0.0.1:1
    token-file: incidents.token
parameters:
  k: {value: 2}
stocks:
  tickets:
    sensor: {manual: true}
  idle:
    sensor: {manual: true}
flows:
  pulled:
    from: incidents-queue
    to: tickets
    equation: k
"""
SPAN = 2 * 3600.0
QUEUE = 10.0          # the remote's queue as read here: flat, where its own equation would drain it


def _project(tmp_path):
    """The local model, the remote's queue read flat at QUEUE (its arrivals 0), tickets rising at k an hour, idle 0."""
    d = tmp_path / "support"
    write(d, LOCAL)
    served_into(d, tmp_path, text=REM)
    p = Project(mdl.load(d))
    now = time.time()
    for i in range(int(SPAN / 30) + 1):
        t = now - SPAN + i * 30
        p.measurements.add("sensor/incidents-queue.main", QUEUE, at=t)
        p.measurements.add("sensor/incidents-arrivals.main", 0.0, at=t)
        p.measurements.add("sensor/tickets.main", 5.0 + 2.0 * (t - (now - SPAN)) / 3600.0, at=t)
        p.measurements.add("sensor/idle.main", 0.0, at=t)
    spec = p.model.spec
    assert "stock.incidents-queue" in spec.remotes["incidents"]["parts"] and "tickets" in spec.stocks
    return p, spec, ob.measured(p, ob.Grid(now - SPAN, now, 120))


def test_remote_stock_is_given_not_integrated(tmp_path):
    _, spec, data = _project(tmp_path)
    pl = sim.plan(spec)
    assert "incidents-queue" not in pl.integrate and "tickets" in pl.integrate
    assert pl.remote == {"incidents-queue": "incidents"}
    run = sim.replay(spec, data, pl)
    assert run.how["stock.incidents-queue"] == "given" and run.how["stock.tickets"] == "integrated"
    assert "stock.incidents-queue is remote incidents's: taken as read, never integrated here" in run.notes
    assert "incidents-queue" not in run.state
    vals = [v for v in run.values["stock.incidents-queue"] if v is not None]
    assert len(vals) == data.grid.n and all(v == pytest.approx(QUEUE) for v in vals)      # its readings, as read
    assert run.how["flow.incidents-served"] == "equation"                                  # its equation still runs
    asked = sim.replay(spec, data, sim.plan(spec, integrate={"incidents-queue", "tickets"}))   # asked for by name
    assert asked.how["stock.incidents-queue"] == "integrated" and not sim.plan(spec, integrate={"tickets"}).remote
    assert min(v for v in asked.values["stock.incidents-queue"] if v is not None) < QUEUE / 2   # integrated, it drains


def test_projection_carries_remote_stock_as_input(tmp_path):
    _, spec, data = _project(tmp_path)
    pl = sim.plan(spec)
    run = sim.replay(spec, data, pl)
    start = data.recent("stock.tickets")
    for got in (sim.project(spec, data, run, 3600.0, pl, points=6, inputs="hold"),
                sim.project(spec, data, run, 3600.0, pl, points=6, inputs="trend"),
                cl.closed(spec, data, run, 3600.0, pl, 6, {}, cl.Start())):
        assert got.how["stock.incidents-queue"] == "given" and "incidents-queue" not in got.state
        assert got.values["stock.incidents-queue"] == pytest.approx([QUEUE] * 6)         # flat at its last reading
        tickets = got.values["stock.tickets"]                     # the local flow drained from it still moves tickets
        assert tickets[-1] == pytest.approx(start + 2.0, abs=1e-6) and tickets[0] < tickets[-1]


def test_fit_total_leaves_remote_out(tmp_path):
    _, spec, data = _project(tmp_path)
    run = sim.replay(spec, data, sim.plan(spec))
    got = ft.compare(spec, data, run)
    assert got["remote"] == {"stock.incidents-queue": "incidents"}
    assert "stock.incidents-queue" not in got["stocks"] and "stock.incidents-queue" not in got["accounting"]
    assert got["total"] is not None and got["total"]["stocks"] == 1
    # the remote's stock integrated by its own equation fits its readings badly; the local total does not move
    asked = sim.replay(spec, data, sim.plan(spec, integrate={"incidents-queue", "tickets"}))
    bad = ft._stats(spec, data, asked, "stock.incidents-queue")
    assert bad is not None and bad["nmse"] > 0.1
    again = ft.compare(spec, data, asked)
    assert again["remote"] == got["remote"] and set(again["stocks"]) == set(got["stocks"]) == {"stock.tickets"}
    assert again["total"]["stocks"] == 1 and again["total"]["n"] == got["total"]["n"]
    assert again["total"]["nmse"] == pytest.approx(got["total"]["nmse"], abs=1e-9)


def test_exercised_skips_remote(tmp_path):
    _, spec, data = _project(tmp_path)
    q = ex.quiet(spec, data)
    assert "stock.incidents-queue" not in q and "flow.incidents-arrivals" not in q      # flat there: not judged here
    assert q["stock.idle"]["why"] == "never-moved"                                       # flat here: still said
    about = [a for a, _ in ex.findings(spec, data)]
    assert "stock.idle" in about and not [a for a in about if a.startswith(("stock.incidents-", "flow.incidents-"))]
    assert "incidents" in (rs.examinable(spec, data, "incidents-queue") or "")            # nor its residual examined
    assert rs.examinable(spec, data, "tickets") is None and "incidents-queue" not in rs.unread(spec)
