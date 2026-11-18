"""Quiet is not absent (SPEC §12e, numbers/exercised.py): a declared part the record has not exercised is never
proposed for removal; it is a finding (`not-exercised`) with its span of record and why, shown where findings are
shown; the estimator and the judge do not vouch for what it carries; the finding clears when the part moves; and
removal is left for structure with no declared reason that the record shows to be redundant, which always waits
for the owner."""

from __future__ import annotations

import json
import math
import textwrap
import time

from ergostat import model as mdl
from ergostat.numbers import estimate as es
from ergostat.numbers import exercised as ex
from ergostat.numbers import improve as im
from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.numbers import review as rv
from ergostat.spec import items as its
from ergostat.spec import watch
from ergostat.store import Project

POINTS = """\
name: pts
parameters:
  k:
    value: 2
    unit: 1/h
    estimate: true
  loss:
    value: 0.01
    unit: 1/h
    estimate: true
stocks:
  queue:
    unit: jobs
    sensor:
      manual: true
  flat-points:
    unit: points
    description: the benchmark's points on flat images
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
  flat-points-lost:
    from: flat-points
    description: what a release does worse; rare (an outage)
    driven-by: +stock.flat-points
    equation: loss * stock.flat-points
    sensor:
      manual: true
  flat-points-dropped:
    from: flat-points
    sensor:
      manual: true
"""
LOSS = "    value: 0.01"
KIND = "ergostat.model-change"


def points_project(tmp_path, minutes: int = 240, moves_after: float | None = None, moves_before: float | None = None,
                   text: str = POINTS):
    """The queue, and flat points that never change: nothing is lost (``flat-points-lost`` reads 0), unless
    ``moves_after`` (minutes from the start) or ``moves_before``, when points are lost then."""
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    q, pts = 0.0, 50.0
    for i in range(minutes * 2 + 1):
        t = now - minutes * 60 + i * 30
        a = 10 + 5 * ((i // 20) % 2)
        lost = 0.0
        m = i / 2
        if (moves_after is not None and m >= moves_after) or (moves_before is not None and m < moves_before):
            lost = 6.0 + 4 * math.sin(i / 5)
        for k, v in (("queue", q), ("arrivals", a), ("flat-points", pts), ("flat-points-lost", lost),
                     ("flat-points-dropped", 0.0)):
            p.measurements.add(f"sensor/{k}.main", v, at=t)
        for _ in range(30):
            q += (a - 3.0 * q) / 3600
            pts -= lost / 3600
    ex._CACHE.clear()
    return p, {"at": now, "window": minutes * 60.0, "starts": now - minutes * 60}


def not_exercised(p) -> dict[str, str]:
    return {f.about: f.message for f in watch.find(p, p.model.spec) if f.code == ex.CODE}


def test_a_quiet_declared_flow_is_a_finding_and_never_a_removal(tmp_path):
    p, _ = points_project(tmp_path)
    got = not_exercised(p)
    assert "flow.flat-points-lost" in got and "flow.flat-points-dropped" in got   # with a description, and without
    said = got["flow.flat-points-lost"]
    assert "not exercised by the record" in said and "never moved" in said and "of record (" in said
    assert "not evidence it is absent" in said and "step test" in said
    assert "no variation" in got["stock.flat-points"]                              # it held one value
    assert "flow.arrivals" not in got and "stock.queue" not in got
    q = ex.quiet(p.model.spec, ex.of_project(p, p.model.spec)[0])
    assert q["flow.flat-points-lost"]["span"] >= 3.5 * 3600 and q["flow.flat-points-lost"]["readings"] >= 20
    rv.refresh(p, p.model.spec, force=True)
    removals = [x for x in pr.stored(p).values() if x.get("gone_parts") or x.get("removes")]
    assert not removals, [x["title"] for x in removals]                             # quiet is not absent


def test_the_finding_is_shown_by_ergostat_findings_and_the_page(tmp_path, capsys, monkeypatch):
    from ergostat.cli import main
    from ergostat.web.server import Live, api
    p, _ = points_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["findings", "--json"]) == 0
    got = {x["about"]: x for x in json.loads(capsys.readouterr().out) if x["code"] == ex.CODE}
    assert "flow.flat-points-lost" in got and got["flow.flat-points-lost"]["line"]
    live = Live(p)
    page = api(live, "exercised", {})
    assert any(x["about"] == "flow.flat-points-lost" and x["level"] == "warn" for x in page)    # the Check page
    panel = api(live, "part/flow/flat-points-lost", {})
    assert [x["code"] for x in panel["findings"]] == [ex.CODE]                     # the part's side panel
    assert not api(live, "part/flow/arrivals", {})["findings"]


def test_an_estimate_for_a_quiet_part_is_held_inconclusive(tmp_path):
    p, snap = points_project(tmp_path)
    got = es.estimate(p, snap)
    e = got["loss"]
    assert e["not_exercised"]["via"] == ["flow.flat-points-lost"]
    why = es.judged(e, 0.01)
    assert why.startswith("held, inconclusive") and "has not exercised" in why
    assert "k" in got and "not_exercised" not in got["k"]
    made = pr.make(p, snap)
    assert not [x for x in made if "parameter.loss" in str(x.get("target"))]       # not proposed
    out = im.submit(p, "improver", {"kind": "parameter", "parts": ["parameter.loss"], "title": "loss is 0.005",
                                    "edit": {"file": "ergostat.yaml", "replace": LOSS, "with": "    value: 0.005"},
                                    "reasons": [{"says": "nothing was lost", "evidence": "fit:total.nmse"}]})
    assert out["status"] == "not-proposed" and out["why"].startswith("held, inconclusive")
    assert its.detail(p.events, p.model.spec, f"{KIND}/{out['id']}")["state"] == "inconclusive"


def test_the_finding_clears_and_the_estimate_is_free_once_the_part_moves(tmp_path):
    p, snap = points_project(tmp_path, moves_after=180)                           # an outage in the last hour
    got = not_exercised(p)
    assert "flow.flat-points-lost" not in got and "stock.flat-points" not in got
    assert "flow.flat-points-dropped" in got                                       # still quiet: still said
    e = es.estimate(p, snap)["loss"]
    assert "not_exercised" not in e and "has not exercised" not in (es.judged(e, 0.01) or "")


def test_the_judge_does_not_vouch_for_a_change_the_record_held_out_has_not_exercised(tmp_path, monkeypatch):
    from ergostat.numbers import identify as idf

    from .test_improve import judge_block
    monkeypatch.setattr(idf, "record_says", lambda *a: {})          # a value the record could identify when it was made
    p, _ = points_project(tmp_path, minutes=600, moves_before=60, text=POINTS.replace(LOSS, "    value: 1.5") + judge_block())
    got = im.submit(p, "improver", {"kind": "parameter", "parts": ["parameter.loss"], "title": "loss is 1",
                                    "edit": {"file": "ergostat.yaml", "replace": "    value: 1.5", "with": "    value: 1"},
                                    "reasons": [{"says": "points were lost early on", "evidence": "fit:total.nmse"}]},
                    at=time.time() - 8 * 3600)
    assert got["status"] == "proposed", got                                        # the record before it moved it
    jd.run(p, "judge")
    x = pr.stored(p)[got["id"]]
    assert x["state"] == "inconclusive" and "has not exercised" in x["verdict"]["why"]       # never passed on it


TWINS = """\
name: twins
stocks:
  first:
    unit: jobs
    description: the queue as the service reads it
    sensor:
      manual: true
  copy:
    unit: jobs
    description: the queue, read again
    inferred: ergostat.model-change/ab12cd34
    sensor:
      manual: true
flows:
  arrive:
    to: first
    sensor:
      manual: true
  copy-in:
    to: copy
    sensor:
      manual: true
blocks:
  judge:
    type: judge
    accept: auto
"""


def test_a_truly_duplicate_inferred_part_is_proposed_for_removal_and_waits_for_the_owner(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(TWINS)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for i in range(241):
        t = now - 7200 + i * 30
        f = 20 + 10 * math.sin(i / 11) + i * 0.1
        for k, v in (("first", f), ("copy", f * 1.001), ("arrive", 5.0 + math.sin(i / 3)), ("copy-in", 1.0 + math.sin(i / 3))):
            p.measurements.add(f"sensor/{k}.main", v, at=t)
    rv.refresh(p, p.model.spec, force=True)
    x = next(x for x in pr.pending(p) if x.get("code") == "simplify-twin")
    assert x["target"] == "stock.copy" and x["removes"] and "stock.copy" in x["gone_parts"]
    assert "inferred by ergostat" in x["reason"] and "first" in x["reason"] and "correlation" in x["reason"]
    pr.event(p, x["id"], "passed", {"verdict": {"verdict": "passed", "why": "simpler, and no worse", "at": now}})
    out = jd.run(p, "judge")
    assert out["accepted"] == 0 and pr.stored(p)[x["id"]]["state"] == "passed"   # accept: auto, and still the owner's
    assert "copy" in mdl.load(tmp_path).spec.stocks


def test_a_block_may_not_remove_a_declared_part_for_being_quiet(tmp_path):
    p, _ = points_project(tmp_path)
    out = im.submit(p, "improver", {"kind": "structure", "parts": ["flow.flat-points-dropped"], "title": "drop it",
                                    "edit": {"file": "ergostat.yaml", "replace": "  flat-points-dropped:\n    from: flat-points\n"
                                             "    sensor:\n      manual: true", "with": ""},
                                    "reasons": [{"says": "it never moved", "evidence": "fit:total.nmse"}]})
    assert out["status"] == "not-proposed" and "the record has not exercised" in out["why"] and "quiet is not absent" in out["why"]
