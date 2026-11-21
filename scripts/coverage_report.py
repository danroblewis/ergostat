"""The unit suite's coverage per module (dev/README.md, *Coverage*), from the files tests/coverage_lines.py wrote:

    uv run python scripts/coverage_report.py DIR [--below FLOOR] [--root REPO]

combines DIR's worker files (``lines-<worker>.json``) into ``DIR/coverage.json``: ``{"main": sha, "seq": n,
"modules": {path: {"statements", "covered", "share"}}}``, for every ``.py`` file under ``ergostat/``, ``dev/bin/``
and ``scripts/``. ``main`` is the commit measured (HEAD), ``seq`` its count of first-parent commits (main's merges
and its direct commits): readers order reports by it, never by a file's time. ``--below FLOOR`` prints the modules
whose share is under FLOOR, worst first.

A statement is a line an ``ast`` statement starts on (docstrings, ``global`` and ``nonlocal`` are not statements: no
code runs for them); a line run anywhere inside a statement's own lines (a continuation, a decorator) covers it.

A module that no test imported in-process is marked ``"subprocess-only": true``: what of it ran in a child process
(a daemon, ``python -m ergostat`` under a subprocess, a dev/bin program called by its path) is not traced, so its
share is a lower bound, not a finding that it is untested.

No report is written (exit 1) when a worker file is missing, unreadable or from another run: never a coverage of
0, nor a partial union read as the whole."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOTS = ("ergostat", "dev/bin", "scripts")
WORKER = re.compile(r"^lines-([A-Za-z0-9_-]{1,32})\.json$")


class NoReport(Exception):
    """The worker files are missing, unreadable or incomplete."""


def statements(text: str) -> dict[int, int]:
    """Each line of a statement's own (not the statements inside it) -> the line the statement starts on."""
    tree = ast.parse(text)
    docs = {id(n.body[0]) for n in ast.walk(tree)
            if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)
            and isinstance(n.body[0].value.value, str)}
    owner: dict[int, int] = {}
    for n in ast.walk(tree):                            # (breadth first: a statement before those inside it)
        if isinstance(n, ast.stmt) and id(n) not in docs and not isinstance(n, ast.Global | ast.Nonlocal):
            first = min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])])
            for line in range(first, n.end_lineno + 1):
                owner[line] = n.lineno
    return owner


def workers(d: Path) -> list[dict]:
    """The worker files of one run, every one of them, or NoReport."""
    files = sorted(p for p in d.iterdir() if WORKER.match(p.name)) if d.is_dir() else []
    if not files:
        raise NoReport(f"no worker file in {d}")
    got = []
    for p in files:
        try:
            w = json.loads(p.read_text())
            got.append({"worker": str(w["worker"]), "workers": int(w["workers"]), "run": str(w["run"]),
                        "lines": {str(f): {int(x) for x in ls} for f, ls in w["lines"].items()},
                        "imported": {str(f) for f in w["imported"]}})
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            raise NoReport(f"{p.name} is unreadable ({e!r})") from None
    if len({w["run"] for w in got}) > 1:
        raise NoReport(f"the worker files in {d} are from more than one run")
    n = max(w["workers"] for w in got)
    missing = ({f"gw{i}" for i in range(n)} if n else {"main"}) - {w["worker"] for w in got}
    if missing:
        raise NoReport(f"no file from worker {', '.join(sorted(missing))} (of {n or 1})")
    return got


def modules(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for r in ROOTS if (root / r).is_dir() for p in (root / r).rglob("*.py")
                  if "__pycache__" not in p.parts)


def combine(d: Path, root: Path = ROOT) -> dict[str, dict]:
    """Each module's statements, those covered by any worker (the union), and the share."""
    ws = workers(d)
    ran: dict[str, set[int]] = {}
    for w in ws:
        for f, ls in w["lines"].items():
            ran.setdefault(f, set()).update(ls)
    imported = set(ran).union(*(w["imported"] for w in ws))
    out = {}
    for m in modules(root):
        try:
            owner = statements((root / m).read_text())
        except (SyntaxError, ValueError, UnicodeDecodeError):  # (not a Python module: a template, a fixture)
            continue
        starts = set(owner.values())
        if not starts:                                  # (an empty __init__.py: nothing to cover)
            continue
        covered = {owner[line] for line in ran.get(m, ()) if line in owner}
        out[m] = {"statements": len(starts), "covered": len(covered), "share": round(len(covered) / len(starts), 3),
                  **({"subprocess-only": True} if m not in imported else {})}
    return out


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def write(d: Path, root: Path = ROOT) -> dict:
    """DIR/coverage.json, stamped with the commit measured and its seq; the report."""
    mods = combine(d, root)
    try:
        sha = git(root, "rev-parse", "HEAD")
        seq = int(git(root, "rev-list", "--count", "--first-parent", "HEAD"))
    except (subprocess.CalledProcessError, ValueError) as e:
        raise NoReport(f"no commit to stamp the report with in {root} ({e})") from None
    report = {"main": sha, "seq": seq, "modules": mods}
    tmp = d / "coverage.json.new"
    tmp.write_text(json.dumps(report, indent=1, sort_keys=True))
    tmp.replace(d / "coverage.json")
    return report


def below(report: dict, floor: float) -> list[tuple[str, dict]]:
    """The modules under the floor, worst first (then by name)."""
    return sorted(((m, r) for m, r in report["modules"].items() if r["share"] < floor),
                  key=lambda mr: (mr[1]["share"], mr[0]))


def floor_of(text: str) -> float:
    f = float(text)
    if not 0 <= f <= 1:
        raise argparse.ArgumentTypeError(f"a floor is a share from 0 to 1, not {text}")
    return f


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir", type=Path)
    ap.add_argument("--below", type=floor_of, help="print the modules whose share is under this, worst first")
    ap.add_argument("--root", type=Path, default=ROOT, help="the repository measured (this one)")
    a = ap.parse_args(argv)
    try:
        report = write(a.dir, a.root.resolve())
    except NoReport as e:
        print(f"coverage_report: no report: {e}", file=sys.stderr)
        return 1
    if a.below is not None:
        for m, r in below(report, a.below):
            lower = "  (subprocess-only: a lower bound)" if r.get("subprocess-only") else ""
            print(f"{r['share']:.3f}  {r['covered']}/{r['statements']}  {m}{lower}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
