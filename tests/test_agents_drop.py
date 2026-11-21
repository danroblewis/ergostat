"""agents.drop(): the drop's main is fetched under a lock, and a ref-lock failure is tried again a bounded number
of times (docs/roadmap/overnight/the-drop-s-main-is-fetched.md)."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "dev" / "bin"
if str(BIN) not in sys.path:
    sys.path.append(str(BIN))          # appended: dev/bin/queue.py must not shadow the standard library's queue

import agents  # noqa: E402
import fac  # noqa: E402


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def setup(tmp_path: Path, n: int) -> tuple[dict, Path, list[str]]:
    """A checkout with n commits on main; its refs/remotes/origin/main is moved by the test."""
    co = tmp_path / "checkout"
    co.mkdir()
    git(co, "init", "-q", "-b", "main")
    shas = []
    for i in range(n):
        git(co, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", f"c{i}")
        shas.append(git(co, "rev-parse", "HEAD"))
    git(co, "update-ref", "refs/remotes/origin/main", shas[0])
    cfg = {"paths": {"live": str(tmp_path / "live"), "checkout": str(co)}, "git": {"base": "main"}}
    return cfg, co, shas


def test_concurrent_drops_all_succeed(tmp_path, monkeypatch):
    cfg, co, shas = setup(tmp_path, 8)
    agents.drop(cfg)                   # (the drop exists, with a main of its own, so every fetch below moves a ref)
    git(co, "update-ref", "refs/remotes/origin/main", shas[1])
    start, moving, errors = threading.Barrier(8), threading.Lock(), []
    real, count, inside, most = fac.git, threading.Lock(), [0], [0]

    def watched(repo, *args, check=True):
        """The real git, counting the drop's steps in flight at once (a retry would hide a race; this does not)."""
        with count:
            inside[0] += 1
            most[0] = max(most[0], inside[0])
        try:
            return real(repo, *args, check=check)
        finally:
            with count:
                inside[0] -= 1

    monkeypatch.setattr(fac, "git", watched)

    def one(i: int) -> None:
        try:
            start.wait()
            with moving:               # (the test's own writes to the checkout, one at a time)
                git(co, "update-ref", "refs/remotes/origin/main", shas[i])
            agents.drop(cfg)
        except Exception as e:         # noqa: BLE001 (gathered, asserted below)
            errors.append(e)

    threads = [threading.Thread(target=one, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    assert not errors, errors
    assert most[0] == 1                # one caller at a time, across the init check, the symbolic-ref and the fetch
    d =Path(cfg["paths"]["live"]) / "drop.git"
    assert git(d, "rev-parse", "refs/heads/main") == git(co, "rev-parse", "refs/remotes/origin/main")


def test_a_ref_lock_failure_is_retried_then_raised(tmp_path, monkeypatch):
    cfg, _, _ = setup(tmp_path, 1)
    real, fetches = fac.git, []

    def stand_in(repo, *args, check=True):
        if args[0] == "fetch":
            fetches.append(args)
            raise RuntimeError("git fetch: error: cannot lock ref 'refs/heads/main': is at X but expected Y")
        return real(repo, *args, check=check)

    monkeypatch.setattr(fac, "git", stand_in)
    monkeypatch.setattr(agents.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="cannot lock ref"):
        agents.drop(cfg)
    assert len(fetches) == agents.DROP_TRIES == 3


def test_any_other_git_error_raises_at_once(tmp_path, monkeypatch):
    cfg, _, _ = setup(tmp_path, 1)
    real, fetches = fac.git, []

    def stand_in(repo, *args, check=True):
        if args[0] == "fetch":
            fetches.append(args)
            raise RuntimeError("git fetch: fatal: couldn't find remote ref refs/remotes/origin/main")
        return real(repo, *args, check=check)

    monkeypatch.setattr(fac, "git", stand_in)
    with pytest.raises(RuntimeError, match="couldn't find remote ref"):
        agents.drop(cfg)
    assert len(fetches) == 1
