"""Existing controllers identified from their record (numbers/extlaw.py, numbers/external.py; SPEC §12d): each law
family recovered from a synthetic record made apart from the fitting code, the right family chosen, an HPA-like stepper
and an alert rule recovered within tolerance, a retuned controller found, too little record said, the closed-loop
projection running the identified law, and the Blocks view writing it in the block."""

from __future__ import annotations

import math
import random
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.numbers import closedloop as cl
from ergostat.numbers import external as ex
from ergostat.numbers import extlaw as el
from ergostat.numbers import observe as ob
from ergostat.numbers import simulate as sim
from ergostat.store import Project

HPA = {"up": 0.7, "down": 0.4, "for_up": 30.0, "for_down": 60.0, "cool_up": 60.0, "cool_down": 300.0}


def hpa(n=1500, dt=15.0, seed=1, change_at=None, retuned=None, tail=0, **kw):
    """Load → utilisation → replicas, through an HPA-like stepper written here, apart from extlaw."""
    c = {**HPA, **kw}
    rnd = random.Random(seed)
    reps, since, run_up, run_dn = 4, 10 ** 6, 0, 0
    xs, us = [], []
    for k in range(n):
        if change_at is not None and k == change_at:
            c = {**c, **retuned}
        load = 3 + 2.5 * math.sin(2 * math.pi * k / 400) + 1.5 * math.sin(2 * math.pi * k / 97) + rnd.gauss(0, 0.3)
        load = 10 + rnd.gauss(0, 0.3) if k >= n - tail else load    # a surge the record ends in
        util = max(0.0, load / reps + rnd.gauss(0, 0.03))
        since += 1
        run_up = run_up + 1 if util > c["up"] else 0
        run_dn = run_dn + 1 if util < c["down"] else 0
        if reps < 20 and run_up >= c["for_up"] / dt + 1 and since >= c["cool_up"] / dt:
            reps, since = reps + 1, 0
        elif reps > 2 and run_dn >= c["for_down"] / dt + 1 and since >= c["cool_down"] / dt:
            reps, since = reps - 1, 0
        xs.append(util)
        us.append(float(reps))
    return xs, us


def alert(n=1500, seed=2, on=300.0, off=250.0, for_=45.0, dt=15.0):
    """A latency and the alert rule on it: firing once above ``on`` for ``for_``, resolved once below ``off``."""
    rnd = random.Random(seed)
    firing, run, xs, us = 0, 0, [], []
    for k in range(n):
        x = 240 + 90 * math.sin(2 * math.pi * k / 130) * (0.6 + 0.4 * math.sin(k / 211)) + rnd.gauss(0, 15)
        run = run + 1 if x > on else 0
        if not firing and run >= for_ / dt + 1:
            firing = 1
        elif firing and x < off:
            firing = 0
        xs.append(x)
        us.append(float(firing))
    return xs, us


def prop(n=800, seed=3, c=2.0, k=0.5, d=2):
    rnd = random.Random(seed)
    xs, x = [], 5.0
    for _ in range(n):
        x += rnd.gauss(0, 1) + 0.05 * (8 - x)
        xs.append(x)
    return xs, [c + k * xs[max(0, i - d)] + rnd.gauss(0, 0.05) for i in range(n)]


def pi(n=800, seed=4, kp=0.8, ki=0.02, r=50.0, db=1.0, d=1, dt=10.0):
    """A lag driven by u and a disturbance, its output held at r by a PI law in velocity form with a deadband."""
    rnd = random.Random(seed)
    y, u, xs, us = 40.0, 5.0, [], []
    for i in range(n):
        y += (2 * u + 10 * math.sin(i / 60) - y) * 0.1 + rnd.gauss(0, 0.5)
        xs.append(y)
        x, xp = xs[max(0, i - d)], xs[max(0, i - d - 1)]
        if abs(x - r) > db:
            u = u - kp * (x - xp) - ki * dt * (x - r)
        us.append(u)
    return xs, us


def test_each_family_is_recovered_from_a_synthetic_record():
    law, *_ = el.fit(*prop(), 10.0)
    assert law.family == "proportional" and law.delay == 20.0
    assert law.p["k"] == pytest.approx(0.5, abs=0.01) and law.p["c"] == pytest.approx(2.0, abs=0.05)
    law, *_ = el.fit(*pi(), 10.0)
    assert law.family == "pi" and law.delay == 10.0
    assert law.p["kp"] == pytest.approx(-0.8, abs=0.02) and law.p["ki"] == pytest.approx(-0.02, abs=0.001)
    assert law.p["r"] == pytest.approx(50.0, abs=0.5) and law.p["db"] == pytest.approx(1.0, abs=0.1)
    law, *_ = el.fit(*alert(), 15.0)
    assert law.family == "onoff" and law.p["side"] == 1
    law, *_ = el.fit(*hpa(), 15.0)
    assert law.family == "stepper" and law.p["step_up"] == 1 and law.p["step_down"] == 1
    assert law.skill > 0.5 and "held out" in law.said() and law.se["up"] > 0   # R² runs free on the input as measured,
    # which in a closed loop answered the true controller: it says less there (SPEC §12d)


def test_the_selection_picks_the_true_family():
    for (xs, us), dt, true in ((prop(), 10.0, "proportional"), (pi(), 10.0, "pi"), (alert(), 15.0, "onoff"), (hpa(), 15.0, "stepper")):
        best, laws, _ = el.fit(xs, us, dt)
        assert best.family == true, [(w.family, w.score) for w in laws]
    best, laws, _ = el.fit(*prop(), 10.0)          # PI in velocity form fits a proportional law as well: parsimony decides
    assert {w.family for w in laws} >= {"proportional", "pi"}
    _, both, _ = el.fit(*alert(), 15.0)            # a stepper between two levels is an on-off law with more parameters
    assert [w.family for w in both][:2] == ["onoff", "stepper"]


def test_an_hpa_like_stepper_in_a_closed_loop_is_recovered():
    law, *_ = el.fit(*hpa(), 15.0)
    p = law.p
    print({k: (HPA[k], p[k]) for k in HPA})
    assert p["up"] == pytest.approx(0.7, abs=0.03) and p["down"] == pytest.approx(0.4, abs=0.03)
    assert abs(p["up"] - 0.7) < 3 * law.se["up"] + 0.01
    for k in ("for_up", "for_down", "cool_up", "cool_down"):
        assert p[k] == pytest.approx(HPA[k], abs=15.0), k
    assert law.delay == 0.0


def test_an_alert_rule_is_recovered():
    law, *_ = el.fit(*alert(), 15.0)
    print(law.p, law.se)
    assert law.p["on"] == pytest.approx(300, abs=5) and law.p["off"] == pytest.approx(250, abs=5)
    assert law.p["for"] == pytest.approx(45, abs=15) and law.p["for_off"] == 0 and law.p["lo"] == 0 and law.p["hi"] == 1
    assert "hysteresis" in law.said()


KUBE = """\
name: k
stocks:
  replicas:
    unit: pods
    sensor: {manual: true}
auxiliaries:
  load:
    unit: pods
    sensor: {manual: true}
  utilisation:
    unit: pods/pods
    sensor: {manual: true}
    equation: auxiliary.load / stock.replicas
flows:
  scale: {to: replicas, two-way: true}
goals:
  headroom: {auxiliary: utilisation, hold: "<= 0.7"}
blocks:
  hpa:
    type: external
    in: auxiliary.utilisation
    out: flow.scale
    identify: {input: auxiliary.utilisation, output: stock.replicas}
"""


def kube(tmp_path, xs, us, dt=15.0, load=None):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(KUBE))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    t0 = now - len(xs) * dt
    rows = []
    for i, (x, u) in enumerate(zip(xs, us, strict=True)):
        t = t0 + i * dt
        rows += [("sensor/utilisation.main", t, x), ("sensor/replicas.main", t, u), ("sensor/load.main", t, (load or x * u))]
    p.measurements.add_many(rows)
    return p, now


def found(p, now):
    out = []
    ex.findings(p, p.model.spec, now, lambda code, msg, where, about: out.append((code, msg)))
    return out


def test_a_day_of_record_is_fitted_at_the_sensors_own_period():
    for gen, check in ((hpa, lambda w: w.family == "stepper" and abs(w.p["up"] - 0.7) < 0.03 and w.p["cool_down"] == 300),
                       (alert, lambda w: w.family == "onoff" and abs(w.p["on"] - 300) < 6 and abs(w.p["off"] - 250) < 6)):
        for seed in range(3):
            xs, us = gen(n=5760, seed=seed)                  # a day at 15 s
            ts, gx, gu, dt, lag = ex.grid([(i * 15.0, x) for i, x in enumerate(xs)], [(i * 15.0, u) for i, u in enumerate(us)],
                                          5759 * 15.0)
            assert dt == 15.0 and len(ts) == ex.MAX_POINTS and gx == xs[-ex.MAX_POINTS:] and lag == 0
            law, *_ = el.fit(gx, gu, dt)
            assert check(law), (gen.__name__, seed, law.family, law.p)


def test_switching_laws_are_recovered_on_every_seed_with_no_wait_they_do_not_need():
    for seed in range(12):
        w, *_ = el.fit(*alert(n=2000, seed=seed), 15.0)
        assert w.p["side"] * (w.p["on"] - w.p["off"]) >= 0, seed           # never a negative hysteresis
        assert abs(w.p["on"] - 300) <= 6 and abs(w.p["off"] - 250) <= 6 and w.p["for"] == 45, (seed, w.p)
        assert w.p["min_on"] == w.p["min_off"] == 0, (seed, w.p)
        h, *_ = el.fit(*hpa(n=2000, seed=seed), 15.0)
        assert abs(h.p["up"] - 0.7) <= 0.03 and (h.p["cool_up"], h.p["cool_down"]) == (60, 300), (seed, h.p)


def test_a_law_fitted_with_no_delay_says_its_gain_may_be_biased():
    law, *_ = el.fit(*prop(d=0), 10.0)
    assert law.delay == 0 and "Ljung ch. 13" in law.said() and "spread" not in law.said()
    law, *_ = el.fit(*alert(), 15.0)
    assert "(spread" in law.said() and "±" not in law.said().split("hysteresis")[0]


def test_a_law_on_an_auxiliary_is_identified_but_not_run_and_says_so(tmp_path):
    xs, us = hpa()
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(KUBE).replace("output: stock.replicas", "output: auxiliary.load"))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    rows = [(("sensor/utilisation.main", t, x), ("sensor/load.main", t, u))
            for i, (x, u) in enumerate(zip(xs, us, strict=True)) for t in [now - (1500 - i) * 15]]
    p.measurements.add_many([r for pair in rows for r in pair])
    (code, msg), = found(p, now)
    assert code == "external-not-run" and "not run ahead" in msg


def test_too_little_record_raises_external_unidentified(tmp_path):
    xs, us = hpa(n=20)
    p, now = kube(tmp_path, xs, us)
    (code, msg), = found(p, now)
    assert code == "external-unidentified" and "points of record" in msg and "at least 40" in msg
    from ergostat.spec import watch
    assert "external-unidentified" in {f.code for f in watch.find(p, p.model.spec, now=now)}


def test_identify_is_checked_at_compile(tmp_path):
    from ergostat.spec import load
    from ergostat.spec.load import SpecError
    for bad, code in (("{input: auxiliary.nope, output: stock.replicas}", "is not an auxiliary"),
                      ("{input: goal.x, output: stock.replicas}", "must be a stock or flow or auxiliary"),
                      ("auxiliary.load", "{input: SIGNAL, output: SIGNAL}")):
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(KUBE).replace(
            "{input: auxiliary.utilisation, output: stock.replicas}", bad))
        with pytest.raises(SpecError) as e:
            load(tmp_path / "ergostat.yaml")
        assert "identify" in str(e.value) and code in str(e.value), (bad, e.value)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(KUBE).replace("external", "program\n    run: 'true'"))
    with pytest.raises(SpecError):                     # only an external block is identified
        load(tmp_path / "ergostat.yaml")


def test_the_closed_loop_projection_runs_the_identified_law(tmp_path):
    xs, us = hpa(tail=40, cool_up=300.0)                # the record ends ten minutes into a surge, scaling up every 5m
    p, now = kube(tmp_path, xs, us)
    spec = p.model.spec
    data = ob.measured(p, ob.Grid(now - 1200, now, 40))
    run = sim.replay(spec, data)
    got = cl.projection(p, spec, data, run, 3600.0, points=60)
    m = got["models"]["flow.scale"]
    assert isinstance(m, ex.ExternalModel) and "identified, external" in m.said() and "step (floating)" in m.said()
    assert m.law.p["cool_up"] == pytest.approx(300.0, abs=15.0)
    reps = got["projection"].values["stock.replicas"]
    print(us[-1], [round(r, 2) for r in reps])
    assert reps[-1] >= us[-1] + 3                       # it goes on scaling up, a step at a time, till under 0.7
    assert 10 / reps[-1] < 0.7 and 10 / (reps[-1] - 1) > 0.7 - 0.05
    assert max(b - a for a, b in zip(reps, reps[1:], strict=False)) <= 1 + 1e-6
    ups = [i for i, (a, b) in enumerate(zip(reps, reps[1:], strict=False)) if b > a + 0.5]
    assert min(b - a for a, b in zip(ups, ups[1:], strict=False)) >= 5 - 1   # its cooldown: 5 minutes, a point a minute
    again = cl.projection(p, spec, data, run, 3600.0, points=60, models=got["models"])   # each run starts afresh
    assert again["projection"].values["stock.replicas"] == reps


def test_the_blocks_view_writes_the_identified_law_in_the_block(tmp_path):
    from ergostat.blockdiagram import diagram
    from ergostat.web.server import Live, api
    xs, us = hpa()
    p, now = kube(tmp_path, xs, us)
    live = Live(p)
    first = next(x for x in api(live, "graph", {"view": ["blocks"]})["nodes"] if x["id"] == "blk:hpa")
    assert not first.get("identified")                  # never fitted while the page waits: in a thread, drawn on a later poll
    for _ in range(100):
        n = next(x for x in api(live, "graph", {"view": ["blocks"]})["nodes"] if x["id"] == "blk:hpa")
        if n.get("identified"):
            break
        time.sleep(0.1)
    assert n["identified"] and n["fn"]["law"].startswith("+1 > 0.") and n["fn"]["sketch"] == "zoh"
    assert "identified" in n["says"] and any(r[0] == "identified" for r in n["rows"])
    plain = next(x for x in diagram(p.model, {})["nodes"] if x["id"] == "blk:hpa")   # without a record: as before
    assert not plain.get("identified") and "law" not in plain["fn"]
