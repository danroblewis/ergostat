"""Run named test files, and only those: the implementor's one way to run tests (dev/bin/agents.py TOOLS).

    uv run python scripts/named_tests.py tests/test_x.py[::test_name] ...       (at most 3; no options)

An allowlist, not a denylist: each argument must be an existing tests/test_*.py file, or one of its tests (::name),
so no directory, glob that matched more than MOST files, option (-n, -k, -p ...) or whole suite gets through. pytest
runs serially (no xdist, the ini's addopts cleared), with -q -rs (a page test skipped is printed). Exits 2 if refused."""
import os
import re
import sys
from pathlib import Path

MOST = 3
ID = re.compile(r"tests/test_[A-Za-z0-9_]+\.py(::[A-Za-z0-9_.\[\]-]+)*")


def refused(args: list[str]) -> str:
    """Why ``args`` are not a run of named test files ('' when they are)."""
    if not 0 < len(args) <= MOST:
        return f"name 1 to {MOST} test files (got {len(args)}); the merge queue runs the whole suites"
    bad = [a for a in args if not ID.fullmatch(a) or not Path(a.split("::")[0]).is_file()]
    return f"not an existing tests/test_*.py file or test id: {' '.join(bad)}" if bad else ""


if __name__ == "__main__":
    if why := refused(sys.argv[1:]):
        print(f"named_tests: {why}", file=sys.stderr)
        sys.exit(2)
    os.execv(sys.executable, [sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:xdist", "-o", "addopts=",
                              *sys.argv[1:]])
