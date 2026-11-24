"""Each item's risk score, learned from what failed before (SPEC §5a, *Risk score*; ergostat/numbers/itemrisk.py):
the backtest's calibration on a record shaped as the factory's, with the factory's own gap kind and declaration, and
the score on each item, from the command line and the item's detail."""

from __future__ import annotations

import json
import math
import random
import shutil
import textwrap
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.numbers import itemrisk
from ergostat.spec import items as its
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
T0 = 1_790_000_000.0
FILES = [f"ergostat/m{j}.py" for j in range(30)]


def factory_kinds() -> str:
    """The factory's gap and milestone kinds, as its ergostat.yaml declares them (risk-score: included)."""
    text = (ROOT / "ergostat.yaml").read_text()
    return "name: factory-record\nitems:" + text[text.index("\n  gap:\n"):text.index("\n  review:\n")] + "\n"


def project(tmp_path, text: str) -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(text)
    return Project(mdl.load(tmp_path))


def factory_record(p: Project, n: int = 800, seed: int = 7) -> list[tuple[float, bool]]:
    """n gaps as the factory records them, found, built (its paths, net lines, author), approved and queued, then
    failed in the queue, or merged, and some merges reverted on main five gaps later. The chance of failing is known:
    logit = -2.6 + 1.9 (touches the hot file) + 1.1 (big) + 0.8 (a planner's split). Each gap's (chance, failed)."""
    rng, evs, t, later, truth = random.Random(seed), [], [T0], {}, []

    def say(i: int, type: str, **data) -> None:
        t[0] += 60
        evs.append({"at": t[0], "type": type, "item": f"gap/g{i}", "data": data, "source": "test"})
    for i in range(n):
        hot, big, plan = rng.random() < 0.3, rng.random() < 0.4, rng.random() < 0.3
        paths = rng.sample(FILES, rng.randint(1, 3)) + (["ergostat/hot.py"] if hot else [])
        chance = 1 / (1 + math.exp(-(-2.6 + 1.9 * hot + 1.1 * big + 0.8 * plan)))
        fails = rng.random() < chance
        truth.append((chance, fails))
        say(i, "gap.found", title=f"g{i}", source="plan" if plan else rng.choice(["gaps", "request"]))
        say(i, "gap.started")
        say(i, "gap.built", paths=paths, net_lines=rng.choice([400, 900]) if big else rng.choice([10, 40, 120]),
            built_by="opus")
        say(i, "gap.approved")
        say(i, "gap.queued")
        if fails and rng.random() < 0.8:
            say(i, "gap.queue-failed")
        else:
            say(i, "gap.merged")
            if fails:
                later.setdefault(i + 5, []).append(i)
        for j in later.pop(i, []):
            say(j, "gap.reverted")
    p.events.add_many(evs)
    return truth


def test_a_backtest_on_a_factory_record_shows_calibration(tmp_path, capsys):
    """Done 1: each attempt scored from the attempts judged before it; the failure rate rises with the score band, and
    each well-filled band's rate is near its mean score."""
    p = project(tmp_path, factory_kinds())
    truth = factory_record(p)
    best = itemrisk.auc([{"score": s, "failed": f} for s, f in truth])      # the true chances' own: what knowing them buys
    bt = itemrisk.backtest(p.events, p.model.spec, "gap")
    assert bt["attempts"] == bt["judged"] == 800 and bt["open"] == 0 and bt["withdrawn"] == 0
    assert bt["unscored"] == 10 and bt["scored"] == 790                      # least: 10 judged before any score
    full = [b for b in bt["bands"] if b["attempts"] >= 50]
    assert len(full) >= 3, bt["bands"]
    for b in full:                                                           # calibrated
        assert abs(b["rate"] - b["mean_score"]) <= 0.1, str(bt)
    rates = [b["rate"] for b in full]
    assert rates == sorted(rates) and rates[-1] >= 3 * rates[0], full       # high scores failed more
    assert bt["auc"] >= best - 0.1 and bt["brier"] < bt["brier_base_rate"], (bt, best)    # near the truth; better
    assert bt["failed"] == sum(f for _, f in truth)                          # than the base rate; reverts counted
    assert sum(b["attempts"] for b in bt["bands"]) == 790
    assert main(["-C", str(tmp_path), "item", "--kind", "gap", "--risk-score", "--backtest", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == bt
    assert main(["-C", str(tmp_path), "item", "--kind", "gap", "--risk-score", "--backtest"]) == 0
    out = capsys.readouterr().out
    assert "MEAN SCORE" in out and "790 scored of 800 judged" in out


def test_the_score_is_on_each_item_and_queryable(tmp_path, capsys):
    """Done 2: every item of the kind has its score now, from the command line (highest first) and on its detail
    (the CLI's, the API's and MCP's), with the fields that moved it; a kind that declares none has none."""
    p = project(tmp_path, factory_kinds())
    factory_record(p, n=200)
    for i, paths in ((900, ["ergostat/hot.py", FILES[0]]), (901, [FILES[1]])):
        p.events.add_many([{"at": T0 + 10 ** 6 + i, "type": "gap.found", "item": f"gap/g{i}", "data": {"source": "plan"}},
                           {"at": T0 + 10 ** 6 + i, "type": "gap.built", "item": f"gap/g{i}",
                            "data": {"paths": paths, "net_lines": 900 if i == 900 else 10, "built_by": "opus"}}])
    assert main(["-C", str(tmp_path), "item", "--kind", "gap", "--risk-score", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    rows = {r["id"]: r for r in got["items"]}
    assert len(rows) == 202 and got["judged"] == 200 and all(r["score"] is not None for r in rows.values())
    assert [r["score"] for r in got["items"]] == sorted((r["score"] for r in got["items"]), reverse=True)
    hot, cold = rows["gap/g900"], rows["gap/g901"]
    assert hot["score"] > cold["score"] + 0.15 and hot["state"] == "built"
    assert any(w["field"] == "paths" and w["value"] == "ergostat/hot.py" for w in hot["why"])
    d = its.detail(p.events, p.model.spec, "gap/g900")
    assert d["risk_score"]["score"] == hot["score"] and d["risk_score"]["judged"] == 200
    assert main(["-C", str(tmp_path), "item", "gap/g900", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["risk_score"]["score"] == hot["score"]
    assert main(["-C", str(tmp_path), "item", "--kind", "gap", "--risk-score", "-n", "300"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].split() == ["ITEM", "STATE", "RISK", "WHY", "(FAILED/JUDGED)"]
    assert [x.split()[0] for x in out[1:-1]] == [r["id"] for r in got["items"]]            # highest first
    assert f"{hot['score']:.3f}" in next(x for x in out if x.startswith("gap/g900 "))
    assert main(["-C", str(tmp_path), "item", "--kind", "milestone", "--risk-score"]) == 2    # declares none
    assert main(["-C", str(tmp_path), "item", "--risk-score"]) == 2
    p.events.add("milestone.added", item="milestone/m", data={}, at=T0 + 2 * 10 ** 6)
    assert "risk_score" not in its.detail(p.events, p.model.spec, "milestone/m")          # off unless declared


def test_the_factory_records_what_its_score_reads(tmp_path):
    """The implementor's gap.built carries the paths the branch changed against its base (a stacked gap's own, not
    its base's) and the agent that built it; a queue conflict is counted in `conflicts` (tests/test_queue.py)."""
    from tests.test_factory import Factory, base_gap, stacked
    f = Factory(tmp_path)
    base_gap(f, "beta-base", {"base.py": "x = 1\n"}, rank=1)
    gid = stacked(f, "gap/beta-base")
    said, _ = f.run("implement.py", gid, FACTORY_STANDIN_WRITES="own.py", ERGOSTAT_AGENT="implementor")
    assert said == ["gap.started", "gap.built"]
    fields = f.item(gid)["fields"]
    assert fields["paths"] == ["own.py", "standin/work.txt"] and fields["built_by"] == "implementor"


KIND = """
name: t
items:
  change:
    id: change/*
    states: [open, ready, landed, failed]
    on: {change.readied: ready, change.landed: landed, change.failed: failed}
    risk-score:
      at: ready
      failed: [change.failed, change.reverted]
      passed: [landed]
      from: {paths: each, lines: size}
      least: 2
"""


def change(p, id: str, at: float, paths, end: str | None = None, lines: int = 10) -> None:
    evs = [{"at": at, "type": "change.readied", "item": id, "data": {"paths": paths, "lines": lines}}]
    if end:
        evs.append({"at": at + 1, "type": end, "item": id, "data": {}})
    p.events.add_many(evs)


def scored(p) -> list:
    return itemrisk.learned(p.events, p.model.spec, "change", lambda lr: [(a["item"], a["score"], a["failed"])
                                                                         for a in lr.attempts])


def test_an_attempt_is_scored_from_the_attempts_judged_before_it_in_record_order(tmp_path):
    """By seq, never by time: c is written after a and b were judged, though stamped before them, and is scored from
    them. A later failure never rescores it. A revert after landing fails the attempt after all. The kept replay,
    caught up, equals one from the start."""
    p = project(tmp_path, KIND)
    change(p, "change/a", T0 + 100, ["x.py"], "change.failed")
    change(p, "change/b", T0 + 200, ["y.py"], "change.landed")
    assert scored(p)[1][1] is None                                           # one judged: under least
    change(p, "change/c", T0, ["x.py"])                                      # stamped first, written third
    itemrisk._CACHE.clear()                                                  # a replay from the start
    first = scored(p)
    assert first[2][0] == "change/c" and first[2][1] is not None and first[2][1] > 0.5   # x.py failed before it
    change(p, "change/d", T0 + 300, ["y.py"], "change.landed")
    p.events.add("change.reverted", item="change/b", data={}, at=T0 + 400)  # b's landing undone: failed after all
    p.events.add("change.failed", item="change/c", data={}, at=T0 + 500)
    after = scored(p)
    assert [a[:2] for a in after[:3]] == [a[:2] for a in first[:3]]          # each score as it was given
    assert [a[2] for a in after] == [True, True, True, False]
    def state(lr):
        return lr.n, lr.f, dict(lr.by), lr.fit, [(a["item"], a["score"], a["failed"]) for a in lr.attempts]
    kept = itemrisk.learned(p.events, p.model.spec, "change", state)
    itemrisk._CACHE.clear()
    assert itemrisk.learned(p.events, p.model.spec, "change", state) == kept
    assert kept[:2] == (4, 3)


def test_a_record_made_again_in_the_same_place_is_replayed_from_the_start(tmp_path):
    """The kept replay never carries over to a new record at the same path, even one already past its last seq."""
    (tmp_path / "ergostat.yaml").write_text(KIND)
    model = mdl.load(tmp_path)
    (tmp_path / "state").mkdir()
    p = Project(model, directory=tmp_path / "state")
    change(p, "change/a", T0, ["x.py"], "change.failed")
    change(p, "change/b", T0 + 10, ["x.py"], "change.landed")
    assert itemrisk.item(p.events, model.spec, "change", "change/b")["judged"] == 2
    shutil.rmtree(tmp_path / "state")
    (tmp_path / "state").mkdir()
    p = Project(model, directory=tmp_path / "state")
    for j in range(4):
        change(p, f"change/n{j}", T0 + j, ["y.py"], "change.landed")
    got = itemrisk.learned(p.events, model.spec, "change", lambda lr: (lr.n, lr.f, sorted(lr.items)))
    assert got == (4, 0, [f"change/n{j}" for j in range(4)])


def test_a_missing_value_is_learned_as_its_own_and_too_few_gives_no_score(tmp_path):
    p = project(tmp_path, KIND)
    change(p, "change/a", T0, None, "change.failed")
    assert itemrisk.item(p.events, p.model.spec, "change", "change/a")["score"] is None      # under least: none, not 0
    assert "fewer than 2" in itemrisk.item(p.events, p.model.spec, "change", "change/a")["said"]
    change(p, "change/b", T0 + 10, ["x.py"], "change.landed")
    change(p, "change/c", T0 + 20, None)
    got = itemrisk.item(p.events, p.model.spec, "change", "change/c")
    assert got["score"] > 0.5 and any(w["value"] == "(none)" and w["failed"] == 1 for w in got["why"])
    assert itemrisk.keys(None, "size") == ["(none)"] and itemrisk.keys(float("nan"), "size") == ["(none)"]
    assert itemrisk.keys(5, "size") == ["4-7"] and itemrisk.keys(-3, "size") == ["<1"] and itemrisk.keys(1, "size") == ["1"]
    assert itemrisk.keys(["b", "a", "a", ""], "each") == ["a", "b"] and itemrisk.keys([], "each") == ["(none)"]


@pytest.mark.parametrize("bad", [
    "risk-score: null",
    "risk-score: {at: nowhere, failed: [change.failed], passed: [landed], from: {paths: each}}",
    "risk-score: {at: ready, failed: [change.failed], passed: [ready], from: {paths: each}}",
    "risk-score: {at: ready, failed: [], passed: [landed], from: {paths: each}}",
    "risk-score: {at: ready, failed: [change.failed], passed: [landed], from: {paths: many}}",
    "risk-score: {at: ready, failed: [change.failed], passed: [landed], from: {}}",
    "risk-score: {at: ready, failed: [change.failed], passed: [landed], from: {paths: each}, least: 0}",
    "risk-score: {at: ready, failed: [change.failed], passed: [landed], from: {paths: each}, least: true}",
    "risk-score: {at: ready, failed: [Bad Type], passed: [landed], from: {paths: each}}",
])
def test_a_bad_declaration_is_refused(tmp_path, bad):
    text = textwrap.dedent(KIND)
    text = text[:text.index("    risk-score:")] + "    " + bad + "\n"
    (tmp_path / "ergostat.yaml").write_text(text)
    with pytest.raises(Exception, match="risk-score"):
        mdl.load(tmp_path)
