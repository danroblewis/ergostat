"""The judge on a slow model and a sparse record (SPEC §12e; docs/roadmap/overnight/slowjudge.md): a queue drained over
about a day, filled at random, read every fifteen minutes, as the work model's stocks are. The judge pools the
record held out in one replay of each model, takes its noise from the record itself, and bounds the change's effect
with an always-valid confidence sequence, so a change no better than the model as it is is passed at most ALPHA of
the time however often it looks, a clearly better one is passed within a bounded record, and one it cannot decide yet
says how much more record it needs."""

from __future__ import annotations

import math
import random
import time

import pytest

from ergostat import model as mdl
from ergostat.numbers import identify as idf
from ergostat.numbers import improve as im
from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.store import Project

SLOW = """\
name: slow
parameters:
  k:
    value: {k}          # what we believe
    unit: 1/h
stocks:
  queue:
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
blocks:
  judge:
    type: judge
    hold-out: 1h
"""
BEFORE = 120.0          # hours of record before the change
WEEK = 168.0


def slow_world(tmp_path, seed: int, k_true: float, k_written: float, base: float = 2.0, every: float = 900.0,
               hours: float = WEEK):
    """The queue as the world ran it: arrivals at random (more by day), each job leaving at k_true an hour; a reading
    of the queue and of the arrivals since the last reading every ``every`` seconds."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(SLOW.format(k=k_written))
    p = Project(mdl.load(tmp_path))
    rng = random.Random(seed)
    now = time.time()
    t0 = now - (BEFORE + hours) * 3600
    q, arrived, t, nxt = int(base / k_true), 0, t0, t0
    rows = []
    while t <= now:
        rate = base * (1.6 if 8 <= ((t - t0) / 3600) % 24 < 18 else 0.4)
        a = sum(rng.random() < rate / 600 for _ in range(10))            # a minute in ten slices
        q += a - sum(rng.random() < k_true / 60 for _ in range(q))
        arrived += a
        if t >= nxt:
            rows += [("sensor/queue.main", q, t), ("sensor/arrivals.main", arrived * 3600 / every, t)]
            arrived, nxt = 0, nxt + every
        t += 60
    for s, v, at in rows:
        p.measurements.add(s, v, at=at)
    return p, now - hours * 3600


def judged(p, made: float, k_from: float, k_to: float, step_h: float = 6.0, hours: float = WEEK):
    """The change k_from → k_to made at ``made``, the judge run every ``step_h`` hours of record after it: its verdict,
    the hours held out when it came, and every undecided look's (hours, why, more)."""
    line = f"    value: {k_from}          # what we believe"
    raw = {"kind": "parameter", "parts": ["parameter.k"], "title": f"k is {k_to}",
           "edit": {"file": "ergostat.yaml", "replace": line, "with": line.replace(f"{k_from} ", f"{k_to} ", 1)},
           "reasons": [{"says": "the replay of queue drifts", "evidence": "fit:stock.queue.um"}], "confidence": 0.5}
    got = im.submit(p, "tester", raw, at=made)
    assert got["status"] == "proposed", got
    looks = []
    for j in range(1, int(hours / step_h) + 1):
        out = jd.run(p, "judge", at=made + j * step_h * 3600)
        v = next((v for v in out["verdicts"] if v["id"] == got["id"]), None)
        if v:
            return v["verdict"], j * step_h, looks
        looks += [(j * step_h, w.get("why"), w.get("more")) for w in out["waiting"] if w["id"] == got["id"] and "why" in w]
    return None, hours, looks


@pytest.fixture(autouse=True)
def _identified(monkeypatch):
    """What is measured is the judge: the improver's own hold on a value the record cannot yet identify is put aside."""
    monkeypatch.setattr(idf, "record_says", lambda *a, **k: None)


@pytest.mark.slow
def test_a_worse_change_on_a_slow_record_is_never_passed(tmp_path):
    """On main a fifth larger drain was passed in about a quarter of seeds (each window one noisy draw)."""
    got = []
    for seed in range(12):
        for shape, (k, worse, base) in {"queue": (0.05, 0.06, 2.0), "few": (0.1, 0.15, 0.2)}.items():
            p, made = slow_world(tmp_path / f"{shape}{seed}", seed, k, k, base=base)
            got.append(judged(p, made, k, worse)[0])
    assert "passed" not in got, got
    assert got.count("failed") >= 4             # it fails some within the week; most need more record than that holds


@pytest.mark.slow
def test_a_better_change_on_a_slow_record_is_passed_within_a_bounded_record(tmp_path):
    for seed in range(6):
        p, made = slow_world(tmp_path / str(seed), seed, 0.05, 0.1, hours=120)
        verdict, hours, _ = judged(p, made, 0.1, 0.05, hours=120)
        assert verdict == "passed", (seed, verdict, hours)                  # within five days of record, each


def test_an_undecided_change_says_how_much_more_record_it_needs(tmp_path):
    p, made = slow_world(tmp_path, 1, 0.05, 0.052, hours=48)
    verdict, _, looks = judged(p, made, 0.052, 0.05, step_h=24, hours=48)
    assert verdict is None and looks, looks
    hours, why, more = looks[-1]
    assert more and more > 3600 and "more record" in why                     # how much, in the record's own terms
    x = next(iter(pr.pending(p)))
    assert x["state"] == "testing" and x["more"] == more and x["undecided"] == why


def test_the_bound_holds_its_error_rate_however_often_it_is_looked_at():
    """Two replays equally good (each off the truth by a drift of its own, the other's mirror; the record's noise slow,
    AR(1), with readings' noise on it): over many records, each looked at seven times as it grows, a change is passed
    (the bound's low end above no change) at most ALPHA of the time; the same looks at a fixed 95% pass it more often."""
    rng = random.Random(7)
    unit, looks, trials = 120, 7, 300
    passed = naive = 0
    for _ in range(trials):
        x, rows, drift = 0.0, [], rng.uniform(-1, 1)
        for i in range(unit * looks):
            x = 0.97 * x + rng.gauss(0, 0.25)
            c = drift * math.sin(i / 90)
            rows.append((i, 1 + c, 1 - c, 1 + x + rng.gauss(0, 0.05)))
        hit = fixed = False
        for u in range(1, looks + 1):
            got = jd.pooled({"stock.q": rows[: u * unit : u]}, float(u))        # ~120 readings over the record, as compare
            hit = hit or got["lo"] > 0
            fixed = fixed or got["est"] - 1.96 * got["half"] / jd.bound(1.0, u) > 0
        passed, naive = passed + hit, naive + fixed
    assert passed / trials <= jd.ALPHA, (passed, naive)
    assert naive > passed, (passed, naive)


def evidence(b: float, a: float, rb: float | None = None, ra: float | None = None, n: int = 60, fallback=False) -> dict:
    """What compare returns, made by hand: replays off a noiseless record by √b and √a (and the rest's by √rb, √ra)."""
    def rows(x, z):
        return [(i, 1 + math.sqrt(x), 1 + math.sqrt(z), 1.0) for i in range(n)]
    return {"near": {"stock.q": rows(b, a)}, "rest": {"stock.r": rows(rb, ra)} if rb is not None else {},
            "goals": {}, "scored": ["stock.q"], "fallback": fallback, "start": 0.0, "width": 10.0}
