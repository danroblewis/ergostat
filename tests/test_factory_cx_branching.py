"""The branching family (dev/records/cx-cyclomatic.md, dev/bin/cx_branching.py): McCabe complexity per function,
nested ones apart, histograms over every function, the worst ones listed, and its model part."""

from __future__ import annotations

import json
import textwrap

import pytest

from .factory_cx import ROOT, Repo, cx, load

br = load("cx_branching")

KINDS = {
    "plain": ("def f(a):\n    return a\n", 1),
    "if": ("def f(a):\n    if a:\n        return 1\n    return 2\n", 2),
    "elif": ("def f(a):\n    if a:\n        return 1\n    elif a > 2:\n        return 3\n    else:\n        return 2\n", 3),
    "for": ("def f(a):\n    for x in a:\n        pass\n    else:\n        pass\n", 2),
    "async for": ("async def f(a):\n    async for x in a:\n        pass\n", 2),
    "while": ("def f(a):\n    while a:\n        a -= 1\n", 2),
    "except": ("def f(a):\n    try:\n        a()\n    except KeyError:\n        pass\n    except ValueError:\n"
               "        pass\n    else:\n        pass\n    finally:\n        pass\n", 3),
    "with": ("def f(a):\n    with a:\n        with a as b, a as c:\n            return b, c\n", 1),
    "comprehension for": ("def f(a):\n    return [x for x in a]\n", 2),
    "comprehension if": ("def f(a):\n    return [x for x in a if x]\n", 3),
    "two fors two ifs": ("def f(a):\n    return {x: y for x in a if x for y in x if y}\n", 5),
    "generator": ("def f(a):\n    return sum(x for x in a)\n", 2),
    "match": ("def f(a):\n    match a:\n        case 1:\n            pass\n        case [x]:\n            pass\n"
              "        case _:\n            pass\n", 4),
    "conditional": ("def f(a):\n    return 1 if a else 2\n", 2),
    "assert": ("def f(a):\n    assert a\n", 2),
    "and": ("def f(a, b, c):\n    return a and b and c\n", 3),
    "or and": ("def f(a, b, c):\n    return a or (b and c)\n", 3),
    "lambda": ("def f(a):\n    return lambda x: 1 if x else 2\n", 2),
}


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_counts_each_branch_kind(kind):
    text, want = KINDS[kind]
    ((name, got, lines),) = br.functions(text)
    assert (name, got, lines) == ("f", want, len(text.splitlines())), kind


def test_nested_functions_counted_apart():
    text = textwrap.dedent("""\
        @deco
        def outer(a):
            if a:
                pass

            def inner(b):
                for x in b:
                    if x:
                        pass
                return [y for y in b]
            return inner

        class C:
            def m(self, a):
                class D:
                    def n(self):
                        assert self
                return a or self

        def top():
            pass
        """)
    got = {q: (c, n) for q, c, n in br.functions(text)}
    assert got == {"outer": (2, 10), "outer.inner": (4, 5), "C.m": (2, 5), "C.m.D.n": (2, 2), "top": (1, 2)}


def fns(spec: list[tuple[int, int]]) -> str:
    """Python text of functions with the given (cyclomatic, lines): `cyclomatic - 1` asserts, padded with passes."""
    out = []
    for i, (c, n) in enumerate(spec):
        body = ["    assert a"] * (c - 1)
        body += ["    pass"] * (n - 1 - len(body))
        assert len(body) == n - 1
        out.append(f"def f{i}(a):\n" + "\n".join(body))
    return "\n\n\n".join(out) + "\n"


def test_median_counts_small_functions(tmp_path):
    r = Repo(tmp_path, {"branching": br})
    # the fixture's own functions (add, run, bench) taken out, so these 100 are all there are
    sha = r.commit({"ergostat/many.py": fns([(1, 3)] * 99 + [(25, 30)]), "ergostat/core.py": "A = 1\n",
                    "dev/bin/tool.py": "B = 1\n", "scripts/bench.py": "C = 1\n"})
    doc = cx.measure(r.ctx, sha)
    assert doc["families"]["branching"]["state"] == "ok", doc["families"]
    v = doc["values"]
    assert v["complexity-functions"] == 100
    assert v["complexity-function-lines-median"] == 3
    assert v["complexity-cyclomatic-p99"] == 1                # rank 99 of 100: the small ones, not the tail
    assert v["complexity-cyclomatic-max"] == 25 and v["complexity-functions-over-20"] == 1
    assert v["complexity-function-lines-p90"] == 3
    assert v["complexity-cyclomatic"] == 99 + 25
    (row,) = [x for x in cx.snapshot(r.ctx, sha, {"branching": br}).rows if x["path"] == "ergostat/many.py"]
    assert row["m"]["over_10"] == [["f99", 25, 30]] and row["m"]["cyclomatic_hist"] == [[1, 99], [25, 1]]


def test_percentile_is_nearest_rank():
    from collections import Counter
    h = Counter({1: 99, 25: 1})
    assert br.percentile(h, 99) == 1 and br.percentile(h, 100) == 25 and br.percentile(h, 50) == 1
    assert br.percentile(Counter({1: 98, 25: 2}), 99) == 25
    with pytest.raises(ValueError):
        br.percentile(Counter(), 50)


def test_splitting_a_function_keeps_the_sum_near(tmp_path):
    whole = "def f(a, b):\n    if a:\n        pass\n    for x in b:\n        if x:\n            pass\n"
    split = ("def f(a, b):\n    if a:\n        pass\n    g(b)\n\n\ndef g(b):\n    for x in b:\n        if x:\n"
             "            pass\n")
    r = Repo(tmp_path, {"branching": br})
    one, two = r.commit({"dev/bin/w.py": whole}), r.commit({"dev/bin/w.py": split})
    a, b = (cx.measure(r.ctx, s)["values"] for s in (one, two))
    assert b["complexity-cyclomatic"] - a["complexity-cyclomatic"] == 1
    assert b["complexity-functions"] - a["complexity-functions"] == 1


def test_unparsed_file_is_no_value_and_only_python_of_the_code_scope_counts(tmp_path):
    r = Repo(tmp_path, {"branching": br})
    sha = r.commit({"tests/t.py": "def t(a):\n    return a or a\n", "ergostat/web/static/x.js": "if (a) {}\n",
                    "docs/broken.py": "def (:\n"})
    assert cx.measure(r.ctx, sha)["values"]["complexity-cyclomatic"] == 3        # add, run, bench
    bad = r.commit({"scripts/broken.py": "def (:\n"})
    doc = cx.measure(r.ctx, bad)
    assert doc["families"]["branching"]["state"] == "failed" and "scripts/broken.py" in doc["families"]["branching"][
        "error"]
    assert not any(k in doc["values"] for k in br.SERIES)


def test_report_lists_the_worst(tmp_path):
    r = Repo(tmp_path, {"branching": br})
    sha = r.commit({"ergostat/a.py": fns([(12, 15), (11, 11), (5, 6)]), "dev/bin/b.py": fns([(12, 20)] + [(40, 41)]),
                    "tests/test_c.py": fns([(50, 51)])})
    rows = br.REPORTS["branching"](cx.snapshot(r.ctx, sha, {"branching": br}))
    assert rows == [{"path": "dev/bin/b.py", "name": "f1", "cyclomatic": 40, "lines": 41},
                    {"path": "dev/bin/b.py", "name": "f0", "cyclomatic": 12, "lines": 20},
                    {"path": "ergostat/a.py", "name": "f0", "cyclomatic": 12, "lines": 15},
                    {"path": "ergostat/a.py", "name": "f1", "cyclomatic": 11, "lines": 11}]
    many = r.commit({"ergostat/a.py": fns([(11 + i, 12 + i) for i in range(40)])})
    rows = br.REPORTS["branching"](cx.snapshot(r.ctx, many, {"branching": br}))
    assert len(rows) == 30 and rows[0]["cyclomatic"] == 50 and rows[-1]["cyclomatic"] == 22


def test_descriptions_say_python_only():
    from ergostat.spec import read
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    for name, s in br.SERIES.items():
        assert "Python only" in s["description"], name
        part = spec.stocks.get(name) or spec.auxiliaries.get(name)
        assert bool(part) == s["part"], name
        if part:
            assert part.system == "complexity" and "Python only" in part.description, name
    assert spec.flows["complexity-cyclomatic-grown"].target == "complexity-cyclomatic"
    assert spec.flows["complexity-functions-over-20-distilled"].source == "complexity-functions-over-20"


@pytest.mark.slow
def test_ergostat_check_reports_no_new_finding(tmp_path, capsys, monkeypatch):
    from ergostat.cli import main, spec_cmds
    from ergostat.numbers import extremes_cache
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(spec_cmds, "CHECK_WAIT", None)
    monkeypatch.setattr(extremes_cache, "BOUND", 900.0)

    def found(where, keep) -> set[str]:
        (where / "dev" / "model").mkdir(parents=True)
        for x in (ROOT / "dev").iterdir():
            if x.name != "model":
                (where / "dev" / x.name).symlink_to(x)
        for x in (ROOT / "dev" / "model").iterdir():
            if keep or x.name != "complexity-branching.yaml":
                (where / "dev" / "model" / x.name).write_text(x.read_text())
        (where / "ergostat.yaml").write_text((ROOT / "ergostat.yaml").read_text())
        main(["-C", str(where), "check", "--json"])
        got = json.loads(capsys.readouterr().out)
        assert got["ok"], [x for x in got["found"] if x["level"] == "error"]
        return {x["id"] for x in got["found"] if x["level"] != "error"}
    assert sorted(found(tmp_path / "now", True) - found(tmp_path / "before", False)) == []
