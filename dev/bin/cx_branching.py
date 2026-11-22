"""The branching family (dev/bin/complexity.py, dev/records/cx-cyclomatic.md): McCabe complexity of each Python function
and method, nested ones counted apart, and its length in lines. Python only: JavaScript is not read, so its branching
is no value here, never zero.

Complexity = 1 + each `if`, `elif`, `for`, `while`, `except` clause, comprehension `for` and `if`, `match` case,
conditional expression and `assert`, and each extra operand of `and`/`or` (`with`, `try`, `else` and `finally` add
nothing): the rules the common tools use. A lambda's branches count in the function it is written in; a class's
methods are `Class.method`, a nested function `outer.inner`. Lines run from the `def` line (decorators left out) to
the function's last line, nested functions included.

Per file: `functions`, `cyclomatic` (sum), `function_lines` (sum), the histograms `cyclomatic_hist` and `lines_hist`
(`[value, count]` pairs, every function) and `over_10` (`[qualname, cyclomatic, lines]`, only those over 10, for the
report). Percentiles and medians are of the histograms, by nearest rank: the smallest value at or below which at
least p% of all functions lie. A file that does not parse fails the family at that commit (no value, never zero)."""

from __future__ import annotations

import ast
import sys
import warnings
from collections import Counter

VERSION = 1
CODE = ("product", "factory", "scripts")
SCOPE = "Python functions and methods of ergostat/, dev/bin/ and scripts/ (Python only: JavaScript is not read)"
SERIES = {
    "complexity-cyclomatic": {"unit": "branches", "part": True, "description": f"McCabe complexity summed over the {SCOPE}"},
    "complexity-functions-over-20": {"unit": "functions", "part": True,
                                     "description": f"functions of complexity over 20, of the {SCOPE}"},
    "complexity-cyclomatic-p99": {"unit": "branches", "part": True,
                                  "description": f"the 99th percentile (nearest rank) of McCabe complexity, of the {SCOPE}"},
    "complexity-functions": {"unit": "functions", "part": False, "description": f"the {SCOPE}, counted"},
    "complexity-cyclomatic-max": {"unit": "branches", "part": False,
                                  "description": f"the highest McCabe complexity of the {SCOPE}"},
    "complexity-function-lines-median": {"unit": "lines", "part": False,
                                         "description": f"the median length (nearest rank) of the {SCOPE}"},
    "complexity-function-lines-p90": {"unit": "lines", "part": False,
                                      "description": f"the 90th percentile (nearest rank) of the length of the {SCOPE}"},
}
BRANCH = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.Assert, ast.match_case)
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)
WORST = 30


def ENV() -> str:  # noqa: N802 (the contract's name)
    return f"py{sys.version_info.major}.{sys.version_info.minor}"


def own(node: ast.AST, prefix: str, out: list) -> int:
    """The branches in node's own code; each function under it is measured apart into out."""
    n = 0
    for c in ast.iter_child_nodes(node):
        if isinstance(c, DEFS):
            name = prefix + c.name
            out.append([name, 1 + own(c, name + ".", out), c.end_lineno - c.lineno + 1])
            continue
        if isinstance(c, ast.ClassDef):
            n += own(c, prefix + c.name + ".", out)
            continue
        n += isinstance(c, BRANCH) + (len(c.values) - 1 if isinstance(c, ast.BoolOp) else 0)
        n += 1 + len(c.ifs) if isinstance(c, ast.comprehension) else 0
        n += own(c, prefix, out)
    return n


def functions(text: str) -> list[list]:
    """`[qualname, cyclomatic, lines]` of every function and method in a Python text (SyntaxError if none parses)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(text)
    out: list = []
    own(tree, "", out)
    return out


def per_file(path: str, text: str) -> dict:
    if not path.endswith(".py"):
        return {}
    try:
        fns = functions(text)
    except (SyntaxError, ValueError, RecursionError) as e:
        return {"unparsed": f"{type(e).__name__}: {e}"[:200]}
    return {"functions": len(fns), "cyclomatic": sum(f[1] for f in fns), "function_lines": sum(f[2] for f in fns),
            "cyclomatic_hist": sorted(map(list, Counter(f[1] for f in fns).items())),
            "lines_hist": sorted(map(list, Counter(f[2] for f in fns).items())),
            "over_10": [f for f in fns if f[1] > 10]}


def scope(snap) -> list[dict]:
    rows = [r for r in snap.rows if not r["vendored"] and r["area"] in CODE and r["lang"] == "python"]
    bad = [f"{r['path']} ({r['m']['unparsed']})" for r in rows if "unparsed" in r["m"]]
    if bad:
        raise ValueError(f"not parsed: {', '.join(bad[:3])}")
    return rows


def percentile(hist: Counter, p: int) -> int:
    """Nearest rank: the smallest value with at least p% of all the counted at or below it."""
    rank, seen = max(1, -(-p * sum(hist.values()) // 100)), 0
    for v in sorted(hist):
        seen += hist[v]
        if seen >= rank:
            return v
    raise ValueError("an empty histogram has no percentile")


def per_commit(snap) -> dict:
    cc, ln = Counter(), Counter()
    for r in scope(snap):
        cc.update(dict(map(tuple, r["m"]["cyclomatic_hist"])))
        ln.update(dict(map(tuple, r["m"]["lines_hist"])))
    n = sum(cc.values())
    out = {"complexity-cyclomatic": sum(v * k for v, k in cc.items()), "complexity-functions": n,
           "complexity-functions-over-20": sum(k for v, k in cc.items() if v > 20)}
    if n:                                                   # (no function: no percentile, never a zero)
        out |= {"complexity-cyclomatic-p99": percentile(cc, 99), "complexity-cyclomatic-max": max(cc),
                "complexity-function-lines-median": percentile(ln, 50),
                "complexity-function-lines-p90": percentile(ln, 90)}
    return out


def worst(snap) -> list[dict]:
    """The WORST most complex functions of the code scope (from `over_10`: fewer when fewer are over 10)."""
    fns = sorted((-c, -n, r["path"], q) for r in scope(snap) for q, c, n in r["m"]["over_10"])
    return [{"path": p, "name": q, "cyclomatic": -c, "lines": -n} for c, n, p, q in fns[:WORST]]


REPORTS = {"branching": worst}
