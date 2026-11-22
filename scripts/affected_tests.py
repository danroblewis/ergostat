"""The implementor's small test set ([suites] build in dev/factory.toml): runs the pytest command it is given on the
test files the branch changed (``git diff main...HEAD``), plus tests/test_<module>.py for each changed
ergostat/**/<module>.py that has one. With none, only checks that the tests collect (--collect-only). A diff that
cannot be read runs the command as given: the full unit suite, never a silent pass.

    uv run python scripts/affected_tests.py [--base main] -- uv run python -m pytest -q -n 8 --dist worksteal

Arguments after the command (the suites' --deselect of quarantined tests) go to pytest as they are. Only files that
exist are named, so a deleted test file never fails the selection."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import PurePosixPath


def changed(base: str) -> list[str] | None:
    """The paths the branch changed since it left ``base``; None when git cannot say."""
    try:
        got = subprocess.run(["git", "-c", "core.quotePath=false", "diff", "--name-only", f"{base}...HEAD"],
                             capture_output=True, text=True, timeout=60)   # (unquoted: a non-ASCII name as it is)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return got.stdout.splitlines() if got.returncode == 0 else None


def selected(paths: list[str]) -> list[str]:
    """The existing test files that ``paths`` name or whose module they change, sorted."""
    out = set()
    for p in map(PurePosixPath, paths):
        if p.parts[0] == "tests" and p.name.startswith("test_") and p.suffix == ".py":
            out.add(str(p))
        elif p.parts[0] == "ergostat" and p.suffix == ".py":
            out.add(f"tests/test_{p.stem}.py")
    return sorted(t for t in out if os.path.isfile(t))


def main(argv: list[str]) -> int:
    base = "main"
    if argv[:1] == ["--base"]:
        base, argv = argv[1], argv[2:]
    if argv[:1] != ["--"] or len(argv) < 2:
        print("usage: affected_tests.py [--base REF] -- <pytest command> [args]", file=sys.stderr)
        return 2
    cmd, paths = argv[1:], changed(base)
    if paths is None:
        print(f"affected_tests: cannot read the diff {base}...HEAD: the full suite", file=sys.stderr, flush=True)
    else:
        tests = selected(paths)
        print(f"affected_tests: {len(paths)} changed, running {' '.join(tests) or 'collection only'}", flush=True)
        cmd += tests or ["--collect-only"]
    os.execvp(cmd[0], cmd)                             # (its own process: a kill of the suite reaches pytest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
