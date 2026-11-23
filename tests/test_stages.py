"""Acceptance (merge-run-stages-with-times): a working item's stages (ergostat/stages.py), recorded as ordinary events and
read through the SQL source's views ``item_stages``, ``stage_estimates`` and ``item_progress`` (datasources/_itemviews.py)
and as Prometheus histograms (``GET /api/stages/metrics``).

The kind here is a deploy, not a merge batch (done 3: the stages are general); the merge queue's own batches are in
test_a_simulated_batch_... below and in tests/test_queue_batch_item.py. Every time is seconds after T, and the views'
"now" is pinned (NOW), so nothing reads the real clock."""

from __future__ import annotations

import textwrap
import time
import types

import pytest

from ergostat import model as mdl
from ergostat import stages
from ergostat.datasources import _itemviews
from ergostat.spec.itemindex import index_for
from ergostat.store import Project
from ergostat.web.server import Live, api

T = 1_795_400_000.0
NOW = T + 10_000

MODEL = """
    name: st
    stocks:
      q: {unit: deploys}
    items:
      deploy:
        id: deploy/*
        states: [queued, rolling, live, rolled-back]
        on: {deploy.rolling: rolling, deploy.live: live, deploy.rolled-back: rolled-back}
        finished: [live, rolled-back]
        pipeline:
          title: Deploys
          stages: [build, canary-a, canary-b, rollout]
    sources:
      record: {type: sql}
    """


@pytest.fixture
def p(tmp_path, monkeypatch):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    p = Project(mdl.load(tmp_path))
    assert not [x for x in p.model.problems if x.level == "error"], p.model.problems
    monkeypatch.setattr(_itemviews, "time", types.SimpleNamespace(time=lambda: NOW, monotonic=time.monotonic))
    return p


def stage(p, item, span, name, run, t0, t1=None, outcome="passed", run_kind="rollout", until=None):
    """A stage said as its recorder says it: started at T+t0, and finished at T+t1 unless t1 is None."""
    p.events.add("deploy.stage-started", item=item, at=T + t0,
                 data=stages.started(span, name, run, run_kind, T + t0, None if until is None else T + until))
    if t1 is not None:
        p.events.add("deploy.stage-finished", item=item, at=T + t1, data=stages.finished(span, outcome, T + t1))


def view(p, text: str) -> list[dict]:
    ix = index_for(p.events, p.model.spec, False)
    with _itemviews.opened(ix, p.model.spec, time.monotonic() + 10, text) as (c, _):
        cur = c.execute(text)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def green(p, n: int, at: float, build: float, a: float, b: float, rollout: float) -> None:
    """deploy/<n>, a green run: build, then canary-a and canary-b at once, then rollout; live after."""
    i = f"deploy/{n}"
    p.events.add("deploy.rolling", item=i, at=T + at)
    stage(p, i, f"{n}b", "build", 1, at, at + build)
    stage(p, i, f"{n}x", "canary-a", 1, at + build, at + build + a)
    stage(p, i, f"{n}y", "canary-b", 1, at + build, at + build + b)
    end = at + build + max(a, b)
    stage(p, i, f"{n}r", "rollout", 1, end, end + rollout)
    p.events.add("deploy.live", item=i, at=T + end + rollout)


def test_a_stage_is_recorded_started_and_finished_and_may_repeat(p):
    p.events.add("deploy.rolling", item="deploy/1", at=T)
    stage(p, "deploy/1", "s1", "build", 1, 0, 60)
    stage(p, "deploy/1", "s2", "canary-a", 1, 60, 90, outcome="failed")
    stage(p, "deploy/1", "s3", "canary-a", 1, 95, 125)                # the same stage again, in the same run
    stage(p, "deploy/1", "s4", "canary-a", 2, 200, 240, run_kind="retry")   # and in a run of its own
    got = view(p, "select span, stage, run, run_kind, state, outcome, started, finished, seconds from item_stages")
    assert [(r["span"], r["stage"], r["run"], r["run_kind"], r["state"], r["outcome"], r["seconds"]) for r in got] == [
        ("s1", "build", "1", "rollout", "done", "passed", 60.0), ("s2", "canary-a", "1", "rollout", "done", "failed", 30.0),
        ("s3", "canary-a", "1", "rollout", "done", "passed", 30.0), ("s4", "canary-a", "2", "retry", "done", "passed", 40.0)]
    assert got[2]["started"] == T + 95 and got[2]["finished"] == T + 125
    fields = view(p, "select value from item_fields where id = 'deploy/1' and field = 'stages'")
    assert len(fields) == 1                                            # one field, folded by merge: nothing replaced


def test_parallel_stages_run_at_once_and_the_time_left_takes_the_longer_of_them(p):
    for n, (build, a, b, rollout) in enumerate([(60, 100, 40, 300), (70, 110, 50, 310), (80, 120, 60, 320)], 1):
        green(p, n, 1000 * n, build, a, b, rollout)
    est = {(r["stage"]): (r["expected"], r["samples"]) for r in view(p, "select * from stage_estimates")}
    assert est == {"build": (70, 3), "canary-a": (110, 3), "canary-b": (50, 3), "rollout": (310, 3)}
    p.events.add("deploy.rolling", item="deploy/4", at=NOW - 105)
    stage(p, "deploy/4", "4b", "build", 1, 10_000 - 105, 10_000 - 30)
    stage(p, "deploy/4", "4x", "canary-a", 1, 10_000 - 30)
    stage(p, "deploy/4", "4y", "canary-b", 1, 10_000 - 30)
    running = view(p, "select stage, state, seconds from item_stages where id = 'deploy/4' and state = 'running'")
    assert running == [{"stage": "canary-a", "state": "running", "seconds": 30.0},
                       {"stage": "canary-b", "state": "running", "seconds": 30.0}]
    now = view(p, 'select stage, note, elapsed, expected, samples, "left" from item_progress where id = \'deploy/4\'')
    # the step under way ends with its longer stage: max(110 - 30, 50 - 30) = 80; then the rollout, 310
    assert now == [{"stage": "canary-a", "note": "", "elapsed": 30.0, "expected": 110.0, "samples": 3, "left": 390.0},
                   {"stage": "canary-b", "note": "", "elapsed": 30.0, "expected": 50.0, "samples": 3, "left": 390.0}]
    assert stages.green_path(stages.rows([("d", "deploy", False, {"stages": {
        "1": {"stage": "build", "run": "1", "run_kind": "k", "started": 0, "finished": 5, "outcome": "passed"},
        "2": {"stage": "canary-a", "run": "1", "run_kind": "k", "started": 5, "finished": 9, "outcome": "passed"},
        "3": {"stage": "canary-b", "run": "1", "run_kind": "k", "started": 6, "finished": 7, "outcome": "passed"},
        "4": {"stage": "rollout", "run": "1", "run_kind": "k", "started": 9, "finished": 12, "outcome": "passed"}}})],
        20), "deploy", "k") == [["build"], ["canary-a", "canary-b"], ["rollout"]]


def test_a_stage_whose_recorder_died_reads_unfinished_and_never_running(p):
    p.events.add("deploy.rolling", item="deploy/5", at=T + 9000)
    stage(p, "deploy/5", "5b", "build", 1, 9000, until=9600)          # its recorder said by T+9600, and is silent
    p.events.add("deploy.rolling", item="deploy/6", at=T + 9500)
    stage(p, "deploy/6", "6b", "build", 1, 9500, until=20_000)        # within its time, but the deploy was ended
    p.events.add("deploy.rolled-back", item="deploy/6", at=T + 9700)
    p.events.add("deploy.rolling", item="deploy/7", at=T + 9900)
    stage(p, "deploy/7", "7b", "build", 1, 9900, until=20_000)        # alive: within its time, its deploy open
    got = view(p, "select id, state, outcome, seconds from item_stages order by id")
    assert got == [{"id": "deploy/5", "state": "unfinished", "outcome": None, "seconds": None},
                   {"id": "deploy/6", "state": "unfinished", "outcome": None, "seconds": None},
                   {"id": "deploy/7", "state": "running", "outcome": None, "seconds": 100.0}]
    left = {r["id"]: (r["note"], r["left"]) for r in view(p, 'select id, note, "left" from item_progress')}
    assert left == {"deploy/5": ("build is unfinished: what ran it stopped before it ended", None),
                    "deploy/7": ("no green rollout of deploy yet", None)}              # deploy/6 is closed: not in it


def test_under_three_normal_runs_a_stage_has_no_estimate_and_a_failed_or_cut_short_one_is_not_normal(p):
    green(p, 1, 0, 60, 100, 40, 300)
    green(p, 2, 1000, 70, 110, 50, 310)
    p.events.add("deploy.rolling", item="deploy/3", at=T + 2000)
    stage(p, "deploy/3", "3r", "rollout", 1, 2000, 2005, outcome="failed")
    stage(p, "deploy/3", "3s", "rollout", 1, 2010, 2011, outcome="stopped")
    est = {r["stage"]: (r["expected"], r["samples"]) for r in view(p, "select * from stage_estimates")}
    assert est["rollout"] == (None, 2) and est["build"] == (None, 2)  # two normal runs: none; 5 s and 1 s not counted
    green(p, 4, 3000, 80, 120, 60, 320)
    est = {r["stage"]: (r["expected"], r["samples"]) for r in view(p, "select * from stage_estimates")}
    assert est["rollout"] == (310, 3)
    p.events.add("deploy.rolling", item="deploy/8", at=NOW - 10)
    stage(p, "deploy/8", "8b", "build", 1, 10_000 - 10, run_kind="hotfix")   # a kind of run never seen green
    (row,) = view(p, 'select note, expected, samples, "left" from item_progress where id = \'deploy/8\'')
    assert row == {"note": "no green hotfix of deploy yet", "expected": None, "samples": 0, "left": None}


def test_once_a_stage_did_not_pass_the_time_left_depends_on_what_fails(p):
    for n in (1, 2, 3):
        green(p, n, 1000 * n, 60, 100, 40, 300)
    p.events.add("deploy.rolling", item="deploy/9", at=NOW - 200)
    stage(p, "deploy/9", "9b", "build", 1, 10_000 - 200, 10_000 - 150, outcome="failed")
    stage(p, "deploy/9", "9c", "build", 2, 10_000 - 100)
    (row,) = view(p, 'select stage, note, elapsed, expected, "left" from item_progress where id = \'deploy/9\'')
    assert row == {"stage": "build", "note": stages.DEPENDS, "elapsed": 100.0, "expected": 60.0, "left": None}


def test_stage_durations_are_histograms_labelled_only_by_kind_declared_stage_and_outcome(p):
    green(p, 1, 0, 50, 100, 40, 300)
    stage(p, "deploy/1", "odd", "deploy/1 at 12:00", 1, 900, 905, outcome="weird")   # not a declared name: other
    stage(p, "deploy/1", "open", "build", 1, 950)                                   # not finished: not counted
    text = api(Live(p), "stages/metrics", {})["text"]
    lines = text.splitlines()
    assert lines[:2] == ["# HELP ergostat_stage_seconds How long each finished stage of a pipeline's items took.",
                         "# TYPE ergostat_stage_seconds histogram"]
    build = [x for x in lines if 'stage="build"' in x]
    assert 'ergostat_stage_seconds_bucket{kind="deploy",stage="build",outcome="passed",le="30"} 0' in build
    assert 'ergostat_stage_seconds_bucket{kind="deploy",stage="build",outcome="passed",le="60"} 1' in build
    assert 'ergostat_stage_seconds_count{kind="deploy",stage="build",outcome="passed"} 1' in build
    assert 'ergostat_stage_seconds_sum{kind="deploy",stage="build",outcome="passed"} 50' in build
    assert 'ergostat_stage_seconds_count{kind="deploy",stage="other",outcome="other"} 1' in lines
    labels = {x.split("{")[1].split("}")[0] for x in lines if not x.startswith("#")}
    assert all("12:00" not in x and "weird" not in x for x in labels)
    assert {tuple(sorted(k.split("=")[0] for k in x.split(","))) for x in labels} <= {
        ("kind", "outcome", "stage"), ("kind", "le", "outcome", "stage")}


@pytest.mark.parametrize("bad", [
    "pipeline: {stages: []}", "pipeline: {stages: [Not A Name]}", "pipeline: {title: x}",
    "pipeline: {stages: [a], waiting: {kind: gap}}", "pipeline: {stages: [a], colour: red}",
    "pipeline: {stages: [a]}\n    fold: {stages: append}", f"pipeline: {{stages: [{', '.join(f's{i}' for i in range(33))}]}}"])
def test_a_pipeline_that_is_not_one_is_refused(tmp_path, bad):
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text("name: st\nstocks:\n  q: {unit: deploys}\nitems:\n  deploy:\n"
                                            f"    id: deploy/*\n    states: [queued, live]\n    {bad}\n")
    spec, problems = read(tmp_path / "ergostat.yaml")
    assert [x.code for x in problems if x.level == "error"] == ["bad-pipeline"], problems
    assert spec.items["deploy"].pipeline is None


def test_a_declared_pipeline_folds_its_stages_by_merge_and_is_listed_for_the_dashboard(p):
    assert p.model.spec.items["deploy"].fold["stages"] == "merge"
    got = api(Live(p), "query/fields", {})
    assert got["pipelines"] == [{"kind": "deploy", "title": "Deploys", "stages": ["build", "canary-a", "canary-b", "rollout"],
                                 "waiting": None, "holds": None}]
    assert {"item_stages", "stage_estimates", "item_progress"} <= set(_itemviews.views(p.model.spec))
