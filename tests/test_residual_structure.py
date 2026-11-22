"""The residual finder (numbers/residuals.py, hidden.py): a measured stock's one-step residuals, worked out from the
record; their whiteness (a portmanteau over lags 2 to 10 with Bartlett's MA(1) covariance); the inflow and lag that
explain them; a missing delay on that inflow proposed as DELAY3 or as a stock in transit, kept when the residuals
shrink by a fifth and whiten; a stock never read started from its initial: (observe.py); and every way a residual,
a candidate or the budget can fail closed. The worlds are planted: a record made by a truth the model lacks."""

from __future__ import annotations

import math
import random
import textwrap
import time
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat.numbers import hidden as hd
from ergostat.numbers import observe as ob
from ergostat.numbers import proposals as pr
from ergostat.numbers import residuals as rs
from ergostat.numbers import review as rv
from ergostat.numbers import simulate as sim
from ergostat.numbers import structural as stc
from ergostat.numbers import trial as tr
from ergostat.spec import read
from ergostat.store import Project

MINUTES = 120
TAU = 0.1                  # the truth's delay, hours: six one-minute buckets

QUEUE = """\
name: q
parameters:
  k:
    value: 2
    unit: 1/h
stocks:
  queue{s}:
    unit: jobs
    sensor:
      manual: true
flows:
  arrivals{s}:
    to: queue{s}
    sensor:
      manual: true
  served{s}:
    from: queue{s}
    driven-by: +stock.queue{s}
    equation: k * stock.queue{s}
"""

QUEUE_DELAYED = """\
name: q
parameters:
  k:
    value: 2
    unit: 1/h
  arrivals-delay:
    value: 0.1
    unit: h
stocks:
  queue:
    unit: jobs
    sensor:
      manual: true
flows:
  arrivals:
    sensor:
      manual: true
  queue-arrives:
    to: queue
    driven-by: +flow.arrivals
    equation: DELAY3(flow.arrivals, arrivals-delay)
  served:
    from: queue
    driven-by: +stock.queue
    equation: k * stock.queue
"""

CHAIN = """\
name: c
parameters:
  r:
    value: 3
    unit: 1/h
  k:
    value: 2
    unit: 1/h
stocks:
  upstream:
    unit: jobs
    sensor:
      manual: true
  downstream:
    unit: jobs
    sensor:
      manual: true
flows:
  arrivals:
    to: upstream
    sensor:
      manual: true
  moving:
    from: upstream
    to: downstream
    driven-by: +stock.upstream
    equation: r * stock.upstream
  done:
    from: downstream
    driven-by: +stock.downstream
    equation: k * stock.downstream
"""

CHAIN_TRANSIT = CHAIN.replace("    to: downstream\n    driven-by: +stock.upstream", "    to: moving-in-transit\n    driven-by: "
                              "+stock.upstream") \
    .replace("parameters:\n", "parameters:\n  moving-delay:\n    value: 0.1\n    unit: h\n") \
    .replace("flows:\n", "  moving-in-transit:\n    unit: jobs\n    initial: {initial}\nflows:\n  downstream-arrives:\n    "
             "from: moving-in-transit\n    to: downstream\n    driven-by: +stock.moving-in-transit\n    equation: "
             "stock.moving-in-transit / moving-delay\n")


def _rates(seed: int, minutes: int) -> list[float]:
    """The arrival rate (per hour) in each ten minutes: a random step every ten minutes."""
    R = random.Random(seed)
    out = [R.choice((10.0, 20.0, 30.0, 40.0))]
    for _ in range(minutes // 10 + 1):
        out.append(R.choice([v for v in (10.0, 20.0, 30.0, 40.0) if v != out[-1]]))
    return out


def _stages(order: int, tau: float, a0: float) -> list[float]:
    return [a0 * tau / order] * order if order else []


def _through(stages: list[float], inflow: float, tau: float, dt: float) -> float:
    """One step of a material delay of ``len(stages)`` stages (none: at once); what leaves it."""
    if not stages:
        return inflow
    m = len(stages)
    outs = [s * m / tau for s in stages]
    for j in range(m):
        stages[j] += ((inflow if j == 0 else outs[j - 1]) - outs[j]) * dt
    return outs[-1]


def world(tmp_path, text: str, chain: bool = False, order: int = 3, tau: float = TAU, seed: int = 0, sigma: float = 0.02,
          minutes: int = MINUTES, copies: tuple[str, ...] = ("",), read_in=lambda i: True, arrivals_read: bool = True,
          later: tuple[int, float] | None = None):
    """The model ``text``, and a record of a truth where what arrives (the queue world) or what moves (the chain world)
    reaches its stock through a delay of ``order`` stages over ``tau`` hours (order 1: a stock in transit; 0: at once;
    ``later``: from that minute on, over that many hours). Rates are read at each bucket's start and middle; stocks just
    before each bucket's end, with noise ``sigma``."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    start = now - minutes * 60
    dt = 1.0 / 3600.0
    k, r = 2.0, 3.0
    for c, s in enumerate(copies):
        rates = _rates(seed * 100 + c, minutes)
        R = random.Random(seed * 1000 + c)
        a0 = rates[0]
        if chain:
            up, st, down = a0 / r, _stages(order, tau, a0 / r * r), a0 / k
        else:
            st, down = _stages(order, tau, a0), a0 / k
        for sec in range(minutes * 60):
            a = rates[sec // 600]
            if later and sec == later[0] * 60:
                tau = later[1]
            if arrivals_read and sec % 30 == 0:
                p.measurements.add(f"sensor/arrivals{s}.main", a, at=start + sec)
            if sec % 60 == 59 and read_in(sec // 60):
                if chain:
                    p.measurements.add("sensor/upstream.main", up + R.gauss(0, sigma), at=start + sec)
                    p.measurements.add("sensor/downstream.main", down + R.gauss(0, sigma), at=start + sec)
                else:
                    p.measurements.add(f"sensor/queue{s}.main", down + R.gauss(0, sigma), at=start + sec)
            if chain:
                out = _through(st, r * up, tau, dt)
                up += (a - r * up) * dt
                down += (out - k * down) * dt
            else:
                down += (_through(st, a, tau, dt) - k * down) * dt
    return p, now


def find(p, now):
    data = ob.measured(p, ob.reference(p, now))
    return stc.find(p, p.model.spec, data)


def residual(found, code=None):
    return [x for x in found if str(x["code"]).startswith("residual-") and (code is None or x["code"] == code)]


def said(not_made, x: str) -> list[str]:
    return [m["why"] for m in not_made if m["title"] == f"A delay on an inflow of {x}"]


def reload(p):
    p.model = mdl.load(p.model.path.parent)
    return p


def accept(p, x):
    """The proposal's edit written, the model reloaded."""
    from pathlib import Path
    for f, text in tr.texts_after(tr.edits_of(x)).items():
        Path(f).write_text(text)
    return reload(p)


# ---- the residual, its whiteness, its lag

def test_the_residual_is_the_stock_change_less_what_the_model_moved(tmp_path):
    (tmp_path / "m.yaml").write_text(textwrap.dedent("""\
        name: m
        parameters:
          k:
            value: 1
            unit: jobs/h
        stocks:
          x:
            sensor:
              manual: true
        flows:
          out:
            from: x
            equation: k
          in1:
            to: x
          in2:
            to: x
        """))
    spec, problems = read(tmp_path / "m.yaml")
    assert not [q for q in problems if q.level == "error"], problems
    d = ob.Data(ob.Grid(0.0, 5 * 3600.0, 5))
    d.values["stock.x"] = [10.0, 12.0, 15.0, 17.0, None]
    d.counted["flow.in1"] = ob.Counted.of([(1800.0, 2.0), (5400.0, 3.0), (9000.0, 1.0), (12600.0, 4.0)])
    d.values["flow.in2"] = [None, None, 1.5, 2.0, 2.0]                     # read as a rate, per hour
    run = SimpleNamespace(moved={"flow.out": [1.0] * 5}, how={"flow.out": "equation"})
    e = rs.residuals(spec, d, run, "x")
    assert e == [None, None, 15 - 12 - (1 + 1.5 - 1), 17 - 15 - (4 + 2 - 1), None]
    assert e[1] is None                                                     # in2 unknown in bucket 1: not 0
    d.values["flow.in2"] = [1.0, 1.0, 1.5, 2.0, 2.0]
    assert rs.residuals(spec, d, run, "x")[1] == 12 - 10 - (3 + 1 - 1)


def _by_hand(e):
    got = [v for v in e if v is not None]
    n, m = len(got), sum(got) / len(got)
    d = sum((v - m) ** 2 for v in got)
    r = [sum((e[i] - m) * (e[i - k] - m) for i in range(k, len(e)) if e[i] is not None and e[i - k] is not None) / d
         for k in range(11)]
    p = max(-0.45, min(0.0, r[1]))
    S = [[{0: 1 + 2 * p * p, 1: 2 * p, 2: p * p}.get(abs(a - b), 0.0) for b in range(9)] for a in range(9)]
    x = r[2:11]
    A = [row[:] + [x[i]] for i, row in enumerate(S)]                         # Gauss–Jordan on [S | x]
    for c in range(9):
        piv = A[c][c]
        A[c] = [v / piv for v in A[c]]
        for i in range(9):
            if i != c:
                A[i] = [a - A[i][c] * b for a, b in zip(A[i], A[c], strict=True)]
    return n * sum(x[i] * A[i][9] for i in range(9)), n * sum(v * v for v in x)


def test_whiteness_q_matches_the_formula():
    R = random.Random(7)
    v = [R.gauss(0, 1) for _ in range(51)]
    e = [v[i + 1] - v[i] + 0.6 * math.sin(i / 3) for i in range(50)]      # reading noise: r1 negative, corrected for
    e[17] = None                                                             # pairs with it are left out
    q, coloured = rs.whiteness(e)
    want, plain = _by_hand(e)
    assert abs(q - want) < 1e-9 and abs(q - plain) > 1e-3
    assert coloured == (want > rs.CHI2_9_99)


def _ma1(seed: int) -> list[float]:
    R = random.Random(seed)
    v = [R.gauss(0, 1) for _ in range(201)]
    return [v[i] - v[i - 1] + 0.1 * R.gauss(0, 1) for i in range(1, 201)]


def test_a_right_model_with_reading_noise_is_rarely_called_coloured(monkeypatch):
    share = sum(rs.whiteness(_ma1(s))[1] for s in range(400)) / 400
    assert share <= 0.03, share
    eye = [[1.0 if a == b else 0.0 for b in range(9)] for a in range(9)]
    monkeypatch.setattr(rs, "bartlett", lambda r1, size=9: eye)             # without the correction: far too often
    assert sum(rs.whiteness(_ma1(s))[1] for s in range(400)) / 400 > 0.06


def _steps(seed: int, n: int = 200) -> list[float]:
    R = random.Random(seed)
    out, level = [], 0.0
    for i in range(n):
        if i % 3 == 0:
            level = R.gauss(0, 1)
        out.append(level)
    return out


@pytest.mark.parametrize("k", [2, 4, 6])
def test_lag_of_finds_a_planted_delay(k):
    u = _steps(k)
    R = random.Random(100 + k)
    e = [None] * k + [u[i - k] - u[i] + 0.3 * R.gauss(0, 1) for i in range(k, len(u))]
    got = rs.lag_of(e, u, 12)
    assert got is not None and got[0] == k and got[1] > 0
    assert rs.lag_of([R.gauss(0, 1) for _ in u], u, 12) is None


# ---- the two forms, proposed

def test_a_missing_third_order_delay_is_proposed(tmp_path):
    p, now = world(tmp_path, QUEUE.format(s=""))
    found, _ = find(p, now)
    [x] = residual(found)
    assert x["code"] == "residual-delay" and x["target"] == "stock.queue" and x["touched"] == ["stock.queue"]
    tr.spec_after(p, tr.edits_of(x))                                         # it compiles
    n = x["residual"]
    assert n["q"][0] > rs.CHI2_9_99 and n["q"][1] < n["q"][0] and n["sse"][1] <= 0.8 * n["sse"][0]
    assert f"q {n['q'][0]:.1f}, against 21.67" in x["reason"] and f"{n['k']} bucket" in x["reason"]
    assert "less what the model's flows moved" in x["reason"] and "Bartlett" in x["method"]
    assert "DELAY3(flow.arrivals, arrivals-delay)" in x["edit"]["diff"]


def test_a_missing_hidden_stock_is_proposed(tmp_path):
    p, now = world(tmp_path, CHAIN, chain=True, order=1)
    found, _ = find(p, now)
    [x] = residual(found)
    assert x["code"] == "residual-hidden-stock" and x["target"] == "stock.downstream"
    after = tr.spec_after(p, tr.edits_of(x))
    t = after.stocks["moving-in-transit"]
    assert not t.sensors and t.initial and t.initial > 0 and t.inferred == f"ergostat.model-change/{x['id']}"
    a = after.flows["downstream-arrives"]
    assert a.source == "moving-in-transit" and a.target == "downstream" and a.equation.text == "stock.moving-in-transit / moving-delay"
    assert after.flows["moving"].target == "moving-in-transit"
    assert x["residual"]["sse"][1] <= 0.8 * x["residual"]["sse"][0]


def _hidden(tmp_path):
    p, now = world(tmp_path, CHAIN, chain=True, order=1)
    [x] = residual(find(p, now)[0])
    return p, now, x


def test_a_stock_never_read_replays_from_its_initial(tmp_path, monkeypatch):
    p, now, x = _hidden(tmp_path / "chain")
    after = tr.spec_after(p, tr.edits_of(x))
    grid = ob.reference(p, now)
    run = sim.replay(after, ob.measured(p, grid, after))
    assert run.moved["flow.downstream-arrives"][0] > 0.01
    q, qnow = world(tmp_path / "queue", QUEUE.format(s=""))
    qgrid = ob.reference(q, qnow)
    with_6 = sim.replay(q.model.spec, ob.measured(q, qgrid)).values
    monkeypatch.setattr(ob, "unread_start", lambda spec, d, name: None)
    assert sim.replay(after, ob.measured(p, grid, after)).moved["flow.downstream-arrives"][0] == 0   # point 6 does it
    assert sim.replay(q.model.spec, ob.measured(q, qgrid)).values == with_6                          # and nothing else


def test_review_refresh_admits_the_hidden_stock_through_the_gate(tmp_path, monkeypatch):
    p, now = world(tmp_path / "a", CHAIN, chain=True, order=1)
    rv.refresh(p, p.model.spec, at=now, force=True)
    got = [x for x in pr.stored(p).values() if x.get("code") == "residual-hidden-stock"]
    assert [x["status"] for x in got] == ["pending"], [(x["status"], x.get("why")) for x in got]
    monkeypatch.setattr(ob, "unread_start", lambda spec, d, name: None)
    q, qnow = world(tmp_path / "b", CHAIN, chain=True, order=1)
    rv.refresh(q, q.model.spec, at=qnow, force=True)
    assert not [x for x in pr.stored(q).values() if x.get("code") == "residual-hidden-stock" and x["status"] == "pending"]


# ---- no proposal where there is nothing to find, or where it was found already

@pytest.mark.slow
def test_a_right_model_gets_no_residual_proposal(tmp_path):
    for seed in range(20):
        p, now = world(tmp_path / f"q{seed}", QUEUE_DELAYED, seed=seed)
        assert not residual(find(p, now)[0]), seed
        c, cnow = world(tmp_path / f"c{seed}", CHAIN_TRANSIT.format(initial=1.0), chain=True, order=1, seed=seed)
        assert not residual(find(c, cnow)[0]), seed


@pytest.mark.parametrize("form", ["delay", "hidden-stock"])
def test_not_offered_again_after_a_form_is_accepted(tmp_path, form):
    chain = form == "hidden-stock"
    p, now = world(tmp_path / "before", CHAIN if chain else QUEUE.format(s=""), chain=chain, order=1 if chain else 3)
    [x] = residual(find(p, now)[0])
    assert x["code"] == f"residual-{form}"
    p = accept(p, x)
    text = p.model.path.read_text()
    x_ = "downstream" if chain else "queue"
    q, qnow = world(tmp_path / "after", text, chain=chain, order=3, tau=0.4, seed=3)    # a longer delay: still coloured
    found, not_made = find(q, qnow)
    assert any("already delayed, drawn from a stock ergostat cannot read" in w for w in said(not_made, x_)), said(not_made, x_)
    assert not [y for y in residual(found) if y["target"] == f"stock.{x_}"]


def test_a_stock_whose_residual_cannot_be_worked_out_says_why(tmp_path):
    unread = CHAIN.replace("  upstream:\n    unit: jobs\n    sensor:\n      manual: true\n", "  upstream:\n    unit: jobs\n")
    p, now = world(tmp_path / "a", unread, chain=True, order=1)
    found, not_made = find(p, now)
    assert not residual(found)
    assert any("fed from upstream, never read and with no initial:" in w for w in said(not_made, "downstream"))
    p, now = world(tmp_path / "b", QUEUE.format(s=""), read_in=lambda i: i % 10 >= 3)
    found, not_made = find(p, now)
    assert not residual(found) and any("under 80%" in w for w in said(not_made, "queue")), said(not_made, "queue")
    p, now = world(tmp_path / "c", QUEUE.format(s=""), arrivals_read=False)
    found, not_made = find(p, now)
    assert not residual(found)
    assert any("arrivals neither measured nor worked out" in w for w in said(not_made, "queue")), said(not_made, "queue")


@pytest.mark.parametrize("how", ["invalid", "raises"])
def test_a_candidate_whose_after_run_fails_is_not_offered(tmp_path, monkeypatch, how):
    p, now = world(tmp_path, QUEUE.format(s=""))
    real, calls = rs.residual_run, []

    def run(spec, data):
        calls.append(1)
        got = real(spec, data)
        if len(calls) == 1:
            return got
        if how == "raises":
            raise RuntimeError("planted")
        got.invalid = ["planted"]
        return got
    monkeypatch.setattr(rs, "residual_run", run)
    found, not_made = find(p, now)
    assert len(calls) == 1 + hd.PER_STOCK and not residual(found)
    want = "its residual run failed (planted)" if how == "raises" else "its residual run is not valid (planted)"
    assert sum(want in w for w in said(not_made, "queue")) == hd.PER_STOCK


@pytest.mark.parametrize("most,examined", [(hd.MOST_REPLAYS, 4), (1 + 2 * hd.PER_STOCK, 2)])
def test_the_replays_a_find_runs_are_capped(tmp_path, monkeypatch, most, examined):
    copies = tuple(str(i) for i in range(1, 9))
    head = QUEUE.format(s="").split("stocks:\n")[0]
    stocks = "".join(QUEUE.format(s=s).split("stocks:\n")[1].split("flows:\n")[0] for s in copies)
    flows = "".join(QUEUE.format(s=s).split("flows:\n")[1] for s in copies)
    p, now = world(tmp_path, f"{head}stocks:\n{stocks}flows:\n{flows}", copies=copies)
    real, calls = rs.residual_run, []
    monkeypatch.setattr(rs, "residual_run", lambda spec, data: calls.append(1) or real(spec, data))
    monkeypatch.setattr(hd, "MOST_REPLAYS", most)
    found, not_made = find(p, now)
    assert len(calls) == 1 + examined * hd.PER_STOCK <= most
    budget = [m for m in not_made if "budget of" in m["why"]]
    assert len(budget) == 8 - examined and len(residual(found)) == examined


def test_a_residual_proposal_found_again_is_revised_and_a_dismissed_one_is_not_made_again(tmp_path):
    p, now = world(tmp_path, QUEUE.format(s=""), minutes=180)
    rv.refresh(p, p.model.spec, at=now - 80 * 60, force=True)                # 100 minutes of record: buckets of 50 s
    [x] = [x for x in pr.stored(p).values() if str(x.get("code")).startswith("residual-")]
    assert x["status"] == "pending", x.get("why")
    rv.refresh(p, p.model.spec, at=now, force=True)                          # 180: of 90 s, so another k and τ
    [y] = [y for y in pr.stored(p).values() if str(y.get("code")).startswith("residual-")]
    again = residual(find(p, now)[0])
    assert y["id"] == x["id"] and y["edit"] != x["edit"] and y["edit"] == again[0]["edit"] and y["revisions"] >= 1
    assert y["residual"]["tau"] != x["residual"]["tau"] and y["residual"] == again[0]["residual"]
    pr.dismiss(p, x["id"], "not this")
    not_made = rv.refresh(p, p.model.spec, at=now + 1, force=True)
    assert [z["status"] for z in pr.stored(p).values() if str(z.get("code")).startswith("residual-")] == ["dismissed"]
    assert any("was dismissed" in w for w in said(not_made, "queue"))           # nor the other form, for the same stock
