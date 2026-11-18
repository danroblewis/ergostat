"""Workspaces: a git worktree per ticket, from a clone of the ticket's repository kept in SCRATCH/repos/, at
most WORKSPACES out at once (a pool).

    workspace.py list                      the worktrees out now
    workspace.py refresh REPO              clone the repository, or fetch it

PLUG POINT (branch `workspaces`, SPEC 12k): a `workspaces:` pool in the model (repo, size, branch template,
base) replaces this file: the AI blocks get `workspace: POOL` (ERGOSTAT_WORKSPACE, ERGOSTAT_BRANCH), the
`branch` step goes, and ergostat cleans the worktree when the ticket finishes instead of `close` here.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from tf import OFFLINE, SCRATCH, conf, git

REPOS = SCRATCH / "repos"
TREES = SCRATCH / "workspaces"


class Busy(Exception):
    """Every workspace is out: the step waits for one."""


def clone(repo: str) -> Path:
    """The repository's clone, made the first time and fetched every time after."""
    path = REPOS / repo.replace("/", "__")
    if not (path / ".git").exists():
        REPOS.mkdir(parents=True, exist_ok=True)
        if OFFLINE:
            import fakes
            src = str(fakes.origin(repo))
            subprocess.run(["git", "clone", "-q", src, str(path)], check=True, capture_output=True)
        else:
            r = subprocess.run(["gh", "repo", "clone", repo, str(path), "--", "-q"], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"cloning {repo}: {r.stderr.strip()}")
    git("fetch", "-q", "--prune", "origin", cwd=path)
    return path


def default_branch(path: Path) -> str:
    ref = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=path, check=False)
    return ref.split("/", 1)[1] if "/" in ref else "main"


def out() -> list[Path]:
    return sorted(p for p in TREES.iterdir() if p.is_dir()) if TREES.exists() else []


def take(key: str, repo: str, branch: str) -> Path:
    """A worktree for the ticket, on a new branch from the repository's default branch. The same ticket asking
    again gets the one it has."""
    tree = TREES / key
    if (tree / ".git").exists():
        return tree
    if len(out()) >= int(conf("WORKSPACES", "3")):
        raise Busy(f"all {conf('WORKSPACES', '3')} workspaces are out")
    base = clone(repo)
    TREES.mkdir(parents=True, exist_ok=True)
    git("worktree", "add", "-q", "-B", branch, str(tree), f"origin/{default_branch(base)}", cwd=base)
    return tree


def release(key: str, repo: str) -> None:
    tree = TREES / key
    if not tree.exists():
        return
    base = REPOS / repo.replace("/", "__")
    if base.exists():
        git("worktree", "remove", "--force", str(tree), cwd=base, check=False)
        git("worktree", "prune", cwd=base, check=False)
    shutil.rmtree(tree, ignore_errors=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["refresh"]:
        print(clone(sys.argv[2]))
    else:
        for p in out():
            print(p)
