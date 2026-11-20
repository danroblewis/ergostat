"""The redesign benchmark's harness (scripts/redesign_bench.py), with the stand-in: no AI."""

import importlib.util
import json
import time
from pathlib import Path

from ergostat.bench import form as fm
from ergostat.bench import truth as tt

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("redesign_bench_under_test", ROOT / "scripts" / "redesign_bench.py")
rb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rb)


def rec_of(c, hours: float = 6.0):
    since = (time.time() // 60) * 60 - hours * 3600
    return tt.simulate(c, since, hours), since, since + hours * 3600


def test_the_stand_in_run_finds_each_repair_and_scores_the_harness(tmp_path):
    every = rb.cases()
    assert len(every) >= 6
    for c, v in every:                                  # each cut takes away exactly what the case expects back
        truth, rec = c.spec(), rec_of(c)
        assert rb.found(truth, v["expect"], truth.stocks, rec), c.id
        assert not rb.found(tt.spec_of(fm.render({**rb.cut(c, v), "description": None})), v["expect"], truth.stocks, rec), c.id
    rows = rb.bench(use_stand_in=True, work=tmp_path, hours=6.0, label="test")
    assert [r["case"] for r in rows] == [c.id for c, _ in every]
    for r in rows:
        assert r["found"] and r["compiles"] and r["extra_parts"] == 0, r
        assert r["cost"]["usd"] == 0.0 and r["model"] == "stand-in" and r["label"] == "test"
        assert r["fit_before"] is not None and r["fit_truth"] is not None
    assert sum(r["fit_improved"] for r in rows) >= 5
    said = rb.table(rows)
    assert "| capacity | yes | 0 | yes |" in said and f"found {len(rows)}/{len(rows)}" in said


def test_a_structural_match_follows_renames_and_ignores_names():
    c, v = dict((c.id, (c, v)) for c, v in rb.cases())["rework"]
    text = c.text().replace("  b:\n    unit: units\n", "  checked:\n    formerly: [b]\n    unit: units\n")
    text = text.replace("stock.b", "stock.checked").replace("from: b", "from: checked").replace("to: b", "to: checked")
    text = text.replace("  rework:\n", "  sent-back:\n")
    renamed = tt.spec_of(text)
    truth, rec = c.spec().stocks, rec_of(c)
    assert "checked" in renamed.stocks and "sent-back" in renamed.flows
    assert rb.found(renamed, {"flow": ["b", "a"]}, truth, rec)       # the rework loop, under other names
    assert not rb.found(renamed, {"flow": ["a", "b"]}, {"x": 1}, rec)  # a stock it cannot follow is new, never a match
    assert rb.found(renamed, {"flow": ["b", None]}, truth, rec) and not rb.found(renamed, {"limit": "b"}, truth, rec)


def test_a_match_must_work_on_the_record_not_only_be_drawn():
    every = dict((c.id, (c, v)) for c, v in rb.cases())

    def judged(case, old, new):
        c, v = every[case]
        assert old in c.text(), old
        return rb.found(tt.spec_of(c.text().replace(old, new)), v["expect"], c.spec().stocks, rec_of(c))
    assert not judged("capacity", "MIN(pick-per-waiting * stock.waiting, capacity)",
                      "MIN(pick-per-waiting * stock.waiting, 1000000000)")      # a limit that never binds
    assert not judged("goal", "driven-by: [-stock.i]\n    equation: orders-base - orders-per-i * stock.i",
                      "driven-by: [+stock.i]\n    equation: orders-base + orders-per-i * stock.i")   # it widens the gap
    assert not judged("rework", "equation: rework-per-b * stock.b", "equation: 0 * stock.b")   # a flow of nothing
    assert not judged("delay", "driven-by: [+flow.a-leaves]\n    equation: \"DELAY3(flow.a-leaves",
                      "driven-by: [+flow.a-in]\n    equation: \"DELAY3(flow.a-in")    # a delay of another path


def test_the_cap_stops_new_cases_and_rows_are_appended(tmp_path, monkeypatch):
    plain = rb.stand_in

    def dear(v):
        inner = plain(v)

        def call(text, model, timeout=None):
            return {**inner(text, model, timeout), "usd": 2.0}
        return call
    monkeypatch.setattr(rb, "stand_in", dear)
    rows = rb.bench(["capacity", "rework", "outflow"], use_stand_in=True, cap=3.0, work=tmp_path, hours=4.0)
    assert [r.get("skipped") is None for r in rows] == [True, True, False]
    assert rows[0]["cost"]["calls"] == 1                # the case's budget (0.5) spent by its first call
    assert "the cap ($3.00) is spent" in rows[2]["skipped"]
    monkeypatch.undo()
    out = tmp_path / "results.jsonl"
    for _ in range(2):
        assert rb.main(["--stand-in", "--cases", "outflow", "--hours", "4", "--results", str(out), "--work", str(tmp_path / "w")]) == 0
    got = [json.loads(x) for x in out.read_text().splitlines()]
    assert [r["case"] for r in got] == ["outflow", "outflow"] and all(r["found"] and r["commit"] for r in got)


def test_a_template_used_counts_as_one_extra_part():
    c, _ = dict((c.id, (c, v)) for c, v in rb.cases())["outflow"]
    plain = c.spec()
    used = tt.spec_of(c.text() + "uses:\n  modelling: {use: modelling}\n")
    added = [f"{k}.{n}" for k, t in (("stock", "stocks"), ("flow", "flows"), ("auxiliary", "auxiliaries"), ("goal", "goals"),
                                     ("block", "blocks")) for n in getattr(used, t) if n not in getattr(plain, t)]
    assert len(added) > 5
    assert rb.extra(used, added, {"stand_in": []}) == 1
    assert rb.extra(used, added + ["flow.a-in"], {"stand_in": [{"add": "flows"}]}) == 1


def test_a_repair_that_also_adds_the_modelling_loop_is_still_found():
    c, v = dict((c.id, (c, v)) for c, v in rb.cases())["outflow"]
    with_loop = tt.spec_of(c.text() + "uses:\n  modelling: {use: modelling}\n")
    assert rb.found(with_loop, v["expect"], c.spec().stocks, rec_of(c))     # its flows are read, never run
