"""The implementor's small test set ([suites] build in dev/factory.toml): runs the pytest command it is given on the
test files the branch changed (``git diff main...HEAD``), plus tests/test_<module>.py for each changed
ergostat/**/<module>.py that has one. With none, only checks that the tests collect (--collect-only). A diff that
cannot be read runs the command as given: the full unit suite, never a silent pass. So does a branch that turns a
feature flag on (ergostat/flags.py turned_on(); flags.json unreadable at either end counts): turning one on is its
own change with the full checks. Flags the branch declares anew are on for its run (ERGOSTAT_FLAGS), so the tests
of its flagged path run in its own build while they skip everywhere else.

    uv run python scripts/affected_tests.py [--base main] -- uv run python -m pytest -q -n 8 --dist worksteal

Arguments after the command (the suites' --deselect of quarantined tests) go to pytest as they are. Only files that
exist are named, so a deleted test file never fails the selection. A browser file (importorskip of Playwright) is
left out where Playwright cannot be imported: it would only skip, and the merge queue's browser suite runs it."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path, PurePosixPath


def changed(base: str) -> list[str] | None:
    """The paths the branch changed since it left ``base``; None when git cannot say."""
    try:
        got = subprocess.run(["git", "-c", "core.quotePath=false", "diff", "--name-only", f"{base}...HEAD"],
                             capture_output=True, text=True, timeout=60)   # (unquoted: a non-ASCII name as it is)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return got.stdout.splitlines() if got.returncode == 0 else None


def flags_said(base: str) -> tuple[list[str], list[str]]:
    """(why the branch turns a feature flag on since it left ``base``, the flags it declares anew). Anything that
    cannot be read, the flags module included, is a reason: the full suite."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # (the tree under test's ergostat)
    try:
        from ergostat import flags
        mb = subprocess.run(["git", "merge-base", base, "HEAD"], capture_output=True, text=True, timeout=60)
    except (ImportError, OSError, subprocess.TimeoutExpired) as e:
        return [f"feature flags not read ({e})"], []
    if mb.returncode != 0 or not mb.stdout.strip():
        return [f"feature flags not read (no merge base with {base})"], []
    return flags.turned_on_between(".", mb.stdout.strip()), flags.added_between(".", mb.stdout.strip())


def selected(paths: list[str]) -> list[str]:
    """The existing test files that ``paths`` name or whose module they change, sorted."""
    out = set()
    for p in map(PurePosixPath, paths):
        if p.parts[0] == "tests" and p.name.startswith("test_") and p.suffix == ".py":
            out.add(str(p))
        elif p.parts[0] == "ergostat" and p.suffix == ".py":
            out.add(f"tests/test_{p.stem}.py")
    return sorted(t for t in out if os.path.isfile(t))


def browser_only(tests: list[str]) -> list[str]:
    """Those of ``tests`` that skip whole without Playwright, when it cannot be imported here: run alone they make
    pytest's rc 5 (nothing ran), and the merge queue's browser suite runs them. With Playwright, none."""
    import importlib.util
    if importlib.util.find_spec("playwright") is not None:
        return []
    return [t for t in tests if 'importorskip("playwright' in Path(t).read_text(encoding="utf-8", errors="replace")]


def main(argv: list[str]) -> int:
    base = "main"
    if argv[:1] == ["--base"]:
        base, argv = argv[1], argv[2:]
    if argv[:1] != ["--"] or len(argv) < 2:
        print("usage: affected_tests.py [--base REF] -- <pytest command> [args]", file=sys.stderr)
        return 2
    cmd, paths = argv[1:], changed(base)
    turned, added = flags_said(base)
    if added:
        os.environ["ERGOSTAT_FLAGS"] = ",".join(sorted({*filter(None, os.environ.get("ERGOSTAT_FLAGS", "").split(",")),
                                                        *added}))
        print(f"affected_tests: the branch declares {', '.join(added)}: on for this run", flush=True)
    if paths is None:
        print(f"affected_tests: cannot read the diff {base}...HEAD: the full suite", file=sys.stderr, flush=True)
    elif turned:
        print(f"affected_tests: {'; '.join(turned)}: the full suite", flush=True)
    else:
        tests = selected(paths)
        if skipped := browser_only(tests):
            print(f"affected_tests: no Playwright here, left to the browser suite: {' '.join(skipped)}", flush=True)
            tests = [t for t in tests if t not in skipped]
        print(f"affected_tests: {len(paths)} changed, running {' '.join(tests) or 'collection only'}", flush=True)
        cmd += tests or ["--collect-only"]
    os.execvp(cmd[0], cmd)                             # (its own process: a kill of the suite reaches pytest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
