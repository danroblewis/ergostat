"""A parallel bisecting round asks each prefix only the failing tests it has: a test the failing merge adds is not on
the merges before it, and "not found" there made the queue fall back to a full run per step."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.test_factory import BIN, module

if str(BIN) not in sys.path:
    sys.path.append(str(BIN))          # appended: dev/bin/queue.py must not shadow the standard lib

queue = module("queue")


def git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(repo: Path, text: str) -> str:
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / "test_x.py").write_text(text)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "c")
    return git(repo, "rev-parse", "HEAD")


def history(tmp_path: Path) -> tuple[Path, str, str]:
    git_dir = tmp_path / "r"
    git_dir.mkdir()
    git(git_dir, "init", "-q")
    return git_dir, commit(git_dir, "def test_old(): pass\n"), commit(git_dir, "def test_old(): pass\ndef test_new(): 1/0\n")


OLD, NEW = "tests/test_x.py::test_old", "tests/test_x.py::test_new"


def test_a_test_a_later_merge_adds_is_not_present_before_it(tmp_path):
    repo, before, after = history(tmp_path)
    assert queue.present(repo, before, [OLD, NEW]) == [OLD]
    assert queue.present(repo, after, [OLD, NEW]) == [OLD, NEW]


def test_a_missing_file_has_no_tests(tmp_path):
    repo, before, _ = history(tmp_path)
    assert queue.present(repo, before, ["tests/test_gone.py::test_a"]) == []


def rounds(monkeypatch, tmp_path, repo, heads, logs_by_head):
    logs = tmp_path / "logs"
    asked = {}

    def suite(cfg, name, logs_, tag, tests=()):
        def run(i, work):
            asked[i] = [t for t in tests if t != "-rA"]
            queue.prefixes.log_of(logs_, tag, i).write_text(logs_by_head[i])
            return 1 if "FAILED" in logs_by_head[i] else 0
        return run

    def run_all(cfg, repo_, heads_, check, tag, logs_):
        out = []
        for i, h in enumerate(heads_):
            rc = check(i, tmp_path)
            out.append(queue.prefixes.read(h, rc, queue.prefixes.log_of(logs_, tag, i)))
        return out

    monkeypatch.setattr(queue.prefixes, "suite", suite)
    monkeypatch.setattr(queue.prefixes, "run_all", run_all)
    return queue.prefixed({}, repo, heads, {"failed": "unit", "tests": [NEW]}, "t-20260101T000000Z", logs), asked


def test_the_prefix_before_a_new_failing_test_passes_and_the_merge_is_found(monkeypatch, tmp_path):
    repo, before, after = history(tmp_path)
    got, asked = rounds(monkeypatch, tmp_path, repo, [before, after], {1: f"FAILED {NEW} - boom\n"})
    assert [r for r, _, _ in got] == ["pass", "fail"]
    assert got[1][1] == [NEW] and list(asked) == [1]


def test_a_serial_step_on_a_prefix_before_the_test_was_added_is_green(monkeypatch, tmp_path):
    repo, before, after = history(tmp_path)
    git(repo, "checkout", "-q", before)
    monkeypatch.setattr(queue.fac, "suite", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nothing to ask")))
    got = queue.named({}, repo, "t", tmp_path, {"failed": "unit", "tests": [NEW], "tip": after})
    assert got["named"]["not_on_this_prefix"] and not got.get("failed")


def test_a_test_not_found_with_no_proof_it_came_later_cannot_tell(monkeypatch, tmp_path):
    repo, before, after = history(tmp_path)
    git(repo, "checkout", "-q", before)
    missing = "tests/test_elsewhere.py::test_generated"

    def suite(cfg, name, repo_, log, **k):
        log.write_text(f"ERROR: not found: /work/{missing}\n")
        return 4, 1.0

    monkeypatch.setattr(queue.fac, "suite", suite)
    assert queue.named({}, repo, "t", tmp_path, {"failed": "unit", "tests": [missing], "tip": after}) is None
