"""Proposals that persist, identifications that are honest (docs/roadmap/overnight/churn.md): a change is what it is
about, revised in place when found again with new numbers; a loop's process is proposed only when the record identifies
it, else the goal says so; an outside step identifies it better than the loop working; a projection resting on parts
that fit badly says so in front."""

from __future__ import annotations

import math
import random
import time

from ergostat import model as mdl
from ergostat.control import ident
from ergostat.control import loop as lp
from ergostat.control import proposals as cp
from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.spec import watch
from ergostat.store import Project

from .test_control import loop_with_tests, tune_project

MODEL = """\
name: tf
parameters:
  review-time:
    value: 120s
    estimate: true
stocks:
  review-asked:
    unit: tickets
    sensor:
      manual: true
flows:
  asked:
    to: review-asked
    sensor:
      manual: true
  review:
    from: review-asked
    driven-by: +stock.review-asked
    equation: stock.review-asked / review-time
goals:
  reviews-answered:
    stock: review-asked
    hold: "<= 0"
blocks:
  judge:
    type: judge
    hold-out: 10m
"""


def factory(d, true_time=300.0, burst_at=-40 * 60, before=5 * 3600, after=3 * 3600, text=MODEL):
    """A ticket-factory-like review queue (a reviewer takes about five minutes a ticket; the model says two), with 130
    tickets added at once 40 minutes ago, and record on past now (for the judge's hold-out)."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(text)
    p = Project(mdl.load(d))
    now = time.time()
    q = 3.0
    for i in range(int((before + after) / 30)):
        t = now - before + i * 30
        a = 20 + 8 * ((i // 40) % 2)                       # tickets an hour
        if abs(t - (now + burst_at)) < 15:
            q += 130                                       # the burst
            a += 130 * 3600 / 30
        p.measurements.add("sensor/review-asked.main", q, at=t)
        p.measurements.add("sensor/asked.main", a, at=t)
        for _ in range(30):
            q += (a / 3600 if a < 1000 else 0) - q / true_time
    return p, now


def snap(now, at):
    return {"at": at, "window": 4 * 3600, "starts": now - 5 * 3600}


def history(p, pid):
    return [e["type"].rsplit(".", 1)[1] for e in p.events.query(n=None, type="ergostat.model-change.*", item=pr.item_of(pid))]


def test_a_proposal_found_again_with_new_numbers_keeps_its_id_and_history(tmp_path):
    p, now = factory(tmp_path)
    [a] = pr.make(p, snap(now, now - 20 * 60))
    [b] = pr.make(p, snap(now, now))                       # more record: new numbers, the same change
    assert a["id"] == b["id"] and a["title"] != b["title"] and b["revisions"] == 1
    assert history(p, a["id"]) == ["made", "checked", "revised"]
    assert pr.changes(p)[a["id"]][0] == "checked"
    pr.make(p, snap(now, now))                             # found again as it was: nothing new to say
    assert history(p, a["id"]) == ["made", "checked", "revised"]


def test_superseded_only_when_its_subject_goes(tmp_path):
    p, now = factory(tmp_path)
    [a] = pr.make(p, snap(now, now))
    f = tmp_path / "ergostat.yaml"
    f.write_text(f.read_text().replace("parameters:\n", "parameters:\n  other:\n    value: 3\n"))   # an edit elsewhere
    p.model = mdl.load(tmp_path)
    assert pr.supersede(p, p.model.spec) == []
    x = pr.changes(p)[a["id"]]
    assert x[0] == "checked" and x[1]["rebased"]["to"] == x[1]["version"] and a["id"] in {y["id"] for y in pr.pending(p)}
    f.write_text(f.read_text().replace("value: 120s", "value: 150s"))                   # its own subject edited
    p.model = mdl.load(tmp_path)
    assert pr.supersede(p, p.model.spec) == [a["id"]]
    st, got = pr.changes(p)[a["id"]]
    assert st == "superseded" and "parameter.review-time" in got["why"] and "edited" in got["why"]


def test_the_estimator_does_not_let_go_of_a_loops_process(tmp_path):
    p = tune_project(tmp_path)
    x = next(y for y in cp.offered(p, lp.analyse(p, "level-held")) if y["kind"] == "process")
    pr.make(p, {"at": time.time(), "window": 7200})       # the estimator's pass, as the page and the modeller make it
    assert pr.changes(p)[x["id"]][0] == "checked"
    cp._made(p, {**x, "title": x["title"] + " (again)"})  # offered again with other numbers: revised in place
    st, f = pr.changes(p)[x["id"]]
    assert st == "checked" and f["revisions"] == 1 and history(p, x["id"]) == ["made", "checked", "revised"]


def test_a_poor_identification_gives_the_finding_not_a_proposal(tmp_path):
    owners = {"found": True, "form": "fopdt", "K": 0.00308, "tau": 25.8, "theta": 64.8, "h": 5.0, "theta_max": 600.0,
              "tau_max": 3600.0, "se": {"K": 0.000565, "tau": 8.38, "theta": 0.886}, "moves": 12, "n_est": 400,
              "n_val": 100, "span": 2000.0, "closed_loop": True, "rms_val": 1.0, "noise": 1.0, "fit_best": 20.0,
              "fit_jitter": 60.0, "fit_val": 2.0, "fit_est": 8.0, "why": [],
              "whiteness": {"q": 82.2, "limit": 31.4, "lags": 20, "white": False},
              "independence": {"max": 0.4, "bound": 0.2, "ok": False}}
    r = ident.judge(owners)                                # the owner's numbers: every check passed but these three
    assert not r["proposable"] and len(r["poor"]) == 3 and r["poor"][0].startswith("follows 2% held out")

    p = loop_with_tests(tmp_path, [], n=5400, dist_every=300)      # closed loop, its disturbances unmeasured
    a = lp.analyse(p, "level-held")
    assert a["identified"]["found"] and a["identified"]["poor"]
    assert not [x for x in cp.offered(p, a) if x["kind"] == "process"]
    said = [x for x in watch.find(p, p.model.spec) if x.code == "loop-not-identifiable"]
    assert len(said) == 1 and said[0].about == "goal.level-held"
    assert "does not identify this loop's process (follows" in said[0].message and "a step test" in said[0].message
    assert "a burst of arrivals" in said[0].message and "more of record" in said[0].message


K, TAU, THETA, H, KD = 0.2, 60.0, 20.0, 10.0, 0.5


def burst_loop(seed, n=6000, burst=3000):
    """A loop under integral control, its process K e^(−θs)/(τs + 1), disturbed by steps nothing measures and once by
    a burst through a measured input (d, the same lag, gain KD)."""
    rnd = random.Random(seed)
    a = math.exp(-1 / TAU)
    x, xd, u, v = None, 0.0, 25.0, 0.0
    buf, dbuf = [25.0] * int(THETA), [0.0] * int(THETA)
    us, ys, ds = [], [], []
    for k in range(n):
        dk = 10.0 if burst <= k < burst + 60 else 0.0
        if k % 600 == 0 and not burst - 1000 <= k <= burst + 2000:
            v = rnd.choice([-1, -0.5, 0.5, 1]) * 0.4
        buf.append(u)
        dbuf.append(dk)
        ud, dd = buf.pop(0), dbuf.pop(0)
        x = K * u if x is None else a * x + (1 - a) * K * ud
        xd = a * xd + (1 - a) * KD * dd
        if k % 10 == 0:
            y = x + xd + v + rnd.gauss(0, 0.01)
            us.append(u)
            ys.append(y)
            ds.append(dk)
            u += 0.3 * (5.0 - y)
    return us, ys, ds


def test_identification_around_an_outside_step_beats_the_loop_working():
    err = {"loop": [], "step": []}
    for seed in range(6):
        u, y, d = burst_loop(seed)
        t = [k * H for k in range(len(u))]
        whole = ident.identify(H, t, u, y, {"d": d})
        [(k, jump)] = ident.outside_steps(d)[:1]
        assert t[k] == 300 * H and jump > 0                # found where it was
        step = ident.around(H, t, u, y, {"d": d}, k)
        assert step["outside_step"]["at"] == t[k]
        for name, r in (("loop", whole), ("step", step)):
            err[name].append(abs(r.get("K", 0.0) - K) / K + abs((r.get("tau") or 0.0) - TAU) / TAU)
        assert abs(step["K"] - K) < 0.5 * K and abs(step["theta"] - THETA) <= H
    loop, step = (sum(v) / len(v) for v in (err["loop"], err["step"]))
    assert step < 0.3 and step < loop / 3, err


def test_the_strip_says_low_confidence_in_front_and_widens_the_band(tmp_path):
    from ergostat.web.server import Live, api
    p, now = factory(tmp_path, after=0, text=MODEL.replace("value: 120s", "value: 2s"))   # far off: worse than its mean
    q = {"since": ["4h"], "refs": ["stock.review-asked"], "strip": ["1"], "replay": ["1"]}
    got = api(Live(p), "series", q)
    s = got["series"][0]
    assert got["low_confidence"].startswith("the model fits review-asked worse than its mean")
    assert s["fan_wide"] and all(lo <= hi for lo, hi in zip(s["fan"]["p5"], s["fan"]["p95"], strict=True))
    assert max(hi - lo for lo, hi in zip(s["fan"]["p5"], s["fan"]["p95"], strict=True)) > 0

    p2, _ = factory(tmp_path / "b", after=0)
    a = {"goal": "reviews-answered", "key": lp.key(p2.model.spec, "reviews-answered"),
         "identified": {"found": True, "proposable": False, "span": 7200.0, "poor": ["follows 2% held out (at least 50%)"]}}
    cp._unidentified(p2, a, False)
    got = api(Live(p2), "series", q)
    assert "reviews-answered's model follows 2% held out" in got["low_confidence"]


def test_the_owners_case_proposals_persist_and_get_judged(tmp_path):
    """Before (main at 214d864): each pass made a new change for the same parameter and let the last go ("let go: found
    again otherwise, or no longer found"), and the estimator's pass let a loop's process go the same way."""
    p, now = factory(tmp_path)
    ids = {x["id"] for at in (now - 30 * 60, now - 20 * 60, now - 10 * 60, now) for x in pr.make(p, snap(now, at))}
    assert len(ids) == 1                                   # one change, revised as the record grew
    [pid] = ids
    assert pr.changes(p)[pid][1]["revisions"] >= 1
    assert not [x for _, (st, x) in pr.changes(p).items() if st == "superseded"]
    out = jd.run(p, "judge", at=now + 3 * 3600)            # the record after it, held out
    st, x = pr.changes(p)[pid]
    assert out["passed"] == 1 and st == "passed" and x["verdict"]["verdict"] == "passed"
    assert history(p, pid)[:2] == ["made", "checked"] and "revised" in history(p, pid) and "testing" in history(p, pid)
