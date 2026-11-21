"""The evidence for a simplification (docs/roadmap/overnight/code-health-simplifier.md): one JSON row per module of
`ergostat/`, `dev/bin/` and `scripts/`, read from a git ref (main, by default HEAD), never from the working files.

    code_evidence.py [--root REPO] [--ref REF] --coverage FILE

Each row: `lines` (net: neither blank nor only a comment), `long_functions` (longer than 60 lines), `churn` (commits
touching it in the last 60 days, `git log --since`), `duplicates` (functions whose body, names and constants replaced,
hashes the same as another function's), `dead_candidates` and `coverage` (its share in code-health-coverage's report,
`{module: {"share": ...}}`; null when the report does not name it).

**Dead means only that nothing names it**: a top-level function or class whose name appears nowhere else as a word in
`ergostat/`, `dev/`, `scripts/`, `tests/`, `pyproject.toml` or `ergostat.yaml` (strings, YAML `run:` lines and the
entry points included). It is a candidate, never a finding: a name built at run time is not seen.

A git that fails (no history, no such ref) or a coverage report missing or unreadable is an error (exit 2), never "no
churn" or "covered"."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

MODULES = ("ergostat/", "dev/bin/", "scripts/")
NAMING = ("ergostat/", "dev/", "scripts/", "tests/", "pyproject.toml", "ergostat.yaml")
LONG = 60              # a function longer than this many lines
DUP_LINES = 5          # bodies shorter than this are too small to count as duplicates
CHURN_DAYS = 60
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class Missing(RuntimeError):
    """Evidence that cannot be read: no pick is made on it."""


def git(root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    r = subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True, timeout=300)
    if r.returncode:
        raise Missing(f"git {' '.join(args[:2])}: {r.stderr.decode(errors='replace').strip()[-300:]}")
    return r.stdout


def tree(root: Path, ref: str) -> dict[str, str]:
    """The text of every file under NAMING at ref, read in one `git cat-file --batch`."""
    names = [n for n in git(root, "ls-tree", "-r", "--name-only", ref).decode().splitlines()
             if n.startswith(NAMING) and n.endswith((".py", ".yaml", ".yml", ".toml", ".md", ".sh", ".js", ".txt"))]
    out = git(root, "cat-file", "--batch", stdin="".join(f"{ref}:{n}\n" for n in names).encode())
    files, i = {}, 0
    for n in names:
        head_end = out.index(b"\n", i)
        size = int(out[i:head_end].split()[2])
        files[n] = out[head_end + 1:head_end + 1 + size].decode(errors="replace")
        i = head_end + 1 + size + 1
    return files


def churn(root: Path, ref: str) -> Counter:
    out = git(root, "log", ref, f"--since={CHURN_DAYS}.days", "--format=", "--name-only", "--", *MODULES).decode()
    return Counter(n for n in out.splitlines() if n.strip())


def net_lines(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith("#"))


class _Blank(ast.NodeTransformer):
    """Names and constants replaced, so two bodies that differ only in them hash the same."""

    def visit_Name(self, node):
        return ast.copy_location(ast.Name(id="_", ctx=node.ctx), node)

    def visit_arg(self, node):
        node.arg, node.annotation = "_", None
        return node

    def visit_Constant(self, node):
        return ast.copy_location(ast.Constant(value=0), node)


def body_hash(fn: ast.AST) -> str:
    body = ast.Module(body=[_Blank().visit(ast.parse(ast.unparse(s))) for s in fn.body], type_ignores=[])
    return hashlib.sha256(ast.dump(body).encode()).hexdigest()


def functions(mod: ast.Module):
    for node in ast.walk(mod):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


def evidence(root: Path, ref: str, coverage: dict) -> list[dict]:
    files = tree(root, ref)
    mods = {n: t for n, t in files.items() if n.startswith(MODULES) and n.endswith(".py")}
    if not mods:
        raise Missing(f"no modules under {', '.join(MODULES)} at {ref}")
    changed = churn(root, ref)
    words = Counter(w for t in files.values() for w in WORD.findall(t))
    parsed, hashes = {}, Counter()
    for n, t in mods.items():
        try:
            parsed[n] = ast.parse(t)
        except SyntaxError as e:
            raise Missing(f"{n} does not parse: {e}") from e
        for fn in functions(parsed[n]):
            if fn.end_lineno - fn.lineno + 1 >= DUP_LINES:
                hashes[body_hash(fn)] += 1
    rows = []
    for n, mod in sorted(parsed.items()):
        fns = list(functions(mod))
        top = [s.name for s in mod.body if isinstance(s, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)]
        cov = coverage.get(n)
        rows.append({
            "module": n,
            "lines": net_lines(mods[n]),
            "long_functions": [f.name for f in fns if f.end_lineno - f.lineno + 1 > LONG],
            "churn": changed.get(n, 0),
            "duplicates": [f.name for f in fns if f.end_lineno - f.lineno + 1 >= DUP_LINES and hashes[body_hash(f)] > 1],
            "dead_candidates": [name for name in top if words[name] <= 1 and not name.startswith("__")],
            "coverage": cov.get("share") if isinstance(cov, dict) else None})
    return rows


def read_coverage(path: Path) -> dict:
    try:
        report = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise Missing(f"the coverage report {path} cannot be read ({type(e).__name__})") from e
    if not isinstance(report, dict):
        raise Missing(f"the coverage report {path} is not a map of modules")
    return report.get("modules", report) if isinstance(report.get("modules"), dict) else report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="code_evidence.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--coverage", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        rows = evidence(args.root, args.ref, read_coverage(args.coverage))
    except Missing as e:
        print(f"no evidence: {e}", file=sys.stderr)
        return 2
    print("dead_candidates: nothing names them - candidates only, never findings", file=sys.stderr)
    for row in rows:
        print(json.dumps(row))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
