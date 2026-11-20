"""The redesign benchmark's harness (scripts/redesign_bench.py), with the stand-in: no AI."""

import importlib.util
import json
from pathlib import Path

from ergostat.bench import form as fm
from ergostat.bench import truth as tt

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("redesign_bench_under_test", ROOT / "scripts" / "redesign_bench.py")
rb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rb)


def test_the_stand_in_run_finds_each_repair_and_scores_the_harness(tmp_path):
    every = rb.cases()
    assert len(every) >= 6
    for c, v in every:                                  # each cut takes away exactly what the case expects back
        truth = c.spec()
        assert rb.found(truth, v["expect"], truth.stocks), c.id
        assert not rb.found(tt.spec_of(fm.render({**rb.cut(c, v), "description": None})), v["expect"], truth.stocks), c.id
    rows = rb.bench(use_stand_in=True, work=tmp_path, hours=6.0, label="test")
    assert [r["case"] for r in rows] == [c.id for c, _ in every]
    for r in rows:
        assert r["found"] and r["compiles"], r
        assert r["cost"]["usd"] == 0.0 and r["model"] == "stand-in" and r["label"] == "test"
        assert r["fit_before"] is not None and r["fit_truth"] is not None
    assert sum(r["fit_improved"] for r in rows) >= 5
    said = rb.table(rows)
    assert "| capacity | yes | yes |" in said and f"found {len(rows)}/{len(rows)}" in said


def test_a_structural_match_follows_renames_and_ignores_names():
    c, v = dict((c.id, (c, v)) for c, v in rb.cases())["rework"]
    text = c.text().replace("  b:\n    unit: units\n", "  checked:\n    formerly: [b]\n    unit: units\n")
    text = text.replace("stock.b", "stock.checked").replace("from: b", "from: checked").replace("to: b", "to: checked")
    text = text.replace("  rework:\n", "  sent-back:\n")
    renamed = tt.spec_of(text)
    truth = c.spec().stocks
    assert "checked" in renamed.stocks and "sent-back" in renamed.flows
    assert rb.found(renamed, {"flow": ["b", "a"]}, truth)            # the rework loop, under other names
    assert not rb.found(renamed, {"flow": ["a", "b"]}, {"x": 1})  # a stock it cannot follow is new, never a match
    assert rb.found(renamed, {"flow": ["b", None]}, truth) and not rb.found(renamed, {"limit": "b"}, truth)


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
