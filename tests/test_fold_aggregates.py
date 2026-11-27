"""The aggregate fold rules (SPEC §5a, *Fold rules*): count, mean, variance, stdev and rms, each a plain number in its
field and a running state (Welford's, for the spread) kept beside the item's fields, so a fold from scratch, one caught
up in chunks by the item index, and one restored from a snapshot and continued are the same; and append's bound."""

from __future__ import annotations

import math
import random
import statistics
import textwrap

import pytest

from ergostat import model as mdl
from ergostat.rollup import compact
from ergostat.spec import itemindex
from ergostat.spec import items as its
from ergostat.spec.changes import fold_event
from ergostat.store import Project

T0 = 1_700_000_000.0
RULES = {"c": "count", "m": "mean", "v": "variance", "s": "stdev", "r": "rms", "a": "append"}
MODEL = """
projections:
  reading:
    query: key.startswith('reading/')
    fields:
      state:
        type: one of [open, done]
      c: {fold: count}
      m: {fold: mean}
      v: {fold: variance}
      s: {fold: stdev}
      r: {fold: rms}
      a: {fold: append(5)}
    events:
      reading-done:
        when: type == 'reading.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
"""


def _fold(values, rules=RULES, bounds=None):
    doc, acc, said = {}, {}, []
    for x in values:
        said.append(fold_event(doc, {"data": {k: x for k in rules}}, rules, bounds, acc))
    return doc, acc, said


def project(tmp_path, text=MODEL) -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def problems(tmp_path, text) -> list[str]:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    from ergostat.spec import read
    _, got = read(tmp_path / "ergostat.yaml")
    return [f"{p.code}: {p.message}" for p in got if p.level == "error"]


# ---- each rule's value


def test_each_aggregate_is_the_statistic_of_the_values_given():
    xs = [3, 1.5, 7, -2.25, 10, 0, 4]
    doc, acc, said = _fold(xs, {k: v for k, v in RULES.items() if k != "a"})
    assert all(why is None for _, why in said)
    assert doc["c"] == len(xs) and type(doc["c"]) is int
    assert doc["m"] == pytest.approx(statistics.mean(xs), rel=1e-12)
    assert doc["v"] == pytest.approx(statistics.variance(xs), rel=1e-12)           # the sample variance (n - 1)
    assert doc["s"] == pytest.approx(statistics.stdev(xs), rel=1e-12)
    assert doc["r"] == pytest.approx(math.sqrt(sum(x * x for x in xs) / len(xs)), rel=1e-12)
    assert set(acc) == {"m", "v", "s", "r"} and "c" not in acc                      # a count's state is its field
    assert acc["v"]["n"] == len(xs) and acc["v"]["v"] == doc["v"]


def test_variance_and_stdev_are_null_until_two_values_and_one_value_is_its_own_mean():
    doc, _, _ = _fold([5])
    assert doc["c"] == 1 and doc["m"] == 5.0 and doc["v"] is None and doc["s"] is None and doc["r"] == 5.0
    doc, _, _ = _fold([5, 5])
    assert doc["v"] == 0.0 and doc["s"] == 0.0


def test_welford_holds_where_the_naive_sum_of_squares_loses_it():
    xs = [1e9 + x for x in (4, 7, 13, 16)]               # the naive E[x²] - E[x]² cancels to noise here
    doc, _, _ = _fold(xs, {"v": "variance"})
    assert doc["v"] == pytest.approx(statistics.variance(xs), rel=1e-9)


def test_null_is_no_value_and_nothing_changes():
    doc, acc, _ = _fold([2, 4])
    before, state = dict(doc), {k: dict(v) for k, v in acc.items()}
    done, why = fold_event(doc, {"data": {k: None for k in RULES if k != "a"}}, RULES, None, acc)
    assert why is None and done == [] and doc == before and acc == state


@pytest.mark.parametrize("rule", ["mean", "variance", "stdev", "rms"])
@pytest.mark.parametrize("bad", ["7", True, [1, 2], {"x": 1}, float("nan"), float("inf")])
def test_anything_but_a_finite_number_is_refused_as_sum_refuses_it(rule, bad):
    doc, acc = {"other": 1}, {}
    assert fold_event(doc, {"data": {"f": 2}}, {"f": rule}, None, acc)[1] is None
    before, state = dict(doc), {k: dict(v) for k, v in acc.items()}
    done, why = fold_event(doc, {"data": {"f": bad, "other": 9}}, {"f": rule}, None, acc)
    assert done == [] and f"f: {rule} takes finite numbers" in why
    assert doc == before and acc == state                    # refused whole: the other key did not change either


def test_count_counts_any_value_but_null_and_refuses_a_field_that_is_not_a_count():
    doc, acc, said = _fold(["a", 1, True, [1], {"x": 1}, None], {"c": "count"})
    assert doc == {"c": 5} and all(why is None for _, why in said)
    doc = {"c": "many"}
    assert "count needs a count" in fold_event(doc, {"data": {"c": 1}}, {"c": "count"}, None, {})[1]


def test_a_patch_or_set_that_changes_an_aggregate_starts_it_over():
    doc, acc, _ = _fold([10, 20], {"m": "mean"})
    assert doc["m"] == 15.0
    assert fold_event(doc, {"patch": [{"op": "replace", "path": "/m", "value": 0}]}, {"m": "mean"}, None, acc)[1] is None
    assert "m" not in acc                                    # its state no longer the field's: dropped
    fold_event(doc, {"data": {"m": 4}}, {"m": "mean"}, None, acc)
    assert doc["m"] == 4.0 and acc["m"]["n"] == 1
    fold_event(doc, {"set": {"other": 1}}, {"m": "mean"}, None, acc)
    assert acc == {}
    fold_event(doc, {"data": {"m": 8}}, {"m": "mean"}, None, acc)
    assert doc["m"] == 8.0


# ---- history: only what is seen to change


# ---- append's bound


def test_a_bounded_append_keeps_only_the_last_values():
    rules, bounds = {"a": "append", "u": "append"}, {"a": 3}
    doc, acc = {}, {}
    for i in range(6):
        assert fold_event(doc, {"data": {"a": i, "u": i}}, rules, bounds, acc)[1] is None
    assert doc["a"] == [3, 4, 5] and doc["u"] == list(range(6))                     # plain append stays unbounded
    fold_event(doc, {"data": {"a": [10, 11, 12, 13, 14]}}, rules, bounds, acc)       # more at once than it keeps
    assert doc["a"] == [12, 13, 14]
    fold_event(doc, {"data": {"a": [20]}}, rules, bounds, acc)
    assert doc["a"] == [13, 14, 20]


# ---- the same fold however it was reached


def _events(seed: int, n: int = 90) -> list[tuple]:
    r = random.Random(seed)
    out = []
    for i in range(n):
        x = r.choice([None, r.randint(-50, 50), r.uniform(-1e3, 1e3), r.uniform(0, 1)])
        if r.random() < 0.05:
            x = "not a number"                                     # refused, kept on the record
        out.append(("reading.taken", f"reading/{i % 3}", {k: x for k in RULES}, T0 + i * 60))
    return out


def _state(items) -> dict:
    return {(i.kind, i.id): (i.fields, i.acc, i.n, [x["why"] for x in i.refused]) for i in items}


def _scratch(p) -> dict:
    by: dict = {}
    for e in p.events.of_items(None):
        by.setdefault(e["item"], []).append(e)
    spec = p.model.spec
    return _state(its.fold(id, evs, k) for id, evs in by.items() for k in its.projections_of(spec, id) or [None])


def _cold() -> None:
    for ix in list(itemindex._OPEN.values()):
        ix.close()
    itemindex._OPEN.clear()


