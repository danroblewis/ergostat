"""Git worktrees, the first kind of workspace (SPEC §12k): a worktree of the pool's repository per workspace, on the
item's own branch. A backend says how a workspace is made ready for an item, how it is checked, cleaned and removed;
the pool (``pool.py``) decides which one an item gets."""

from __future__ import annotations

import subprocess
from pathlib import Path


class Broken(Exception):
    """A workspace that cannot be used: the why is said, and the pool quarantines it."""


def git(*args, cwd: Path, check: bool = True) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120)
    if check and p.returncode:
        raise Broken(f"git {' '.join(args)}: {(p.stderr or p.stdout).strip()[:300]}")
    return p.stdout.strip()


class GitWorktrees:
    """``repo``: the repository; ``base``: the ref a new branch starts from."""

    def __init__(self, repo: Path, base: str = "HEAD"):
        self.repo, self.base = repo, base

    def branch_exists(self, branch: str) -> bool:
        return bool(git("branch", "--list", branch, cwd=self.repo))

    def check(self, d: Path) -> str | None:
        """Why this workspace cannot be given to another item (None: it can): missing, not this repository's
        worktree, or with changes not committed."""
        if not d.is_dir():
            return "missing"
        try:
            top = git("rev-parse", "--show-toplevel", cwd=d)
            common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=d)
            mine = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=self.repo)
        except Broken as e:
            return f"not a git worktree ({e})"
        if Path(top).resolve() != d.resolve() or Path(common).resolve() != Path(mine).resolve():
            return f"not a worktree of {self.repo}"
        dirty = git("status", "--porcelain", "--untracked-files=all", cwd=d, check=False)
        if dirty:
            n = len(dirty.splitlines())
            return f"dirty: {n} file{'s' if n > 1 else ''} changed and not committed ({dirty.splitlines()[0].strip()})"
        return None

    def make(self, d: Path, branch: str) -> str:
        """A fresh worktree at ``d`` on ``branch`` (made from the base, unless it is there already). Returns how."""
        d.parent.mkdir(parents=True, exist_ok=True)
        git("worktree", "prune", cwd=self.repo, check=False)
        if self.branch_exists(branch):
            git("worktree", "add", str(d), branch, cwd=self.repo)
            return "fresh, on its branch as it was"
        git("worktree", "add", "-b", branch, str(d), self.base, cwd=self.repo)
        return f"fresh, a new branch from {self.base}"

    def reuse(self, d: Path, branch: str) -> str:
        """A clean worktree, reset for another item: onto its branch (made from the base, unless there already)."""
        if self.branch_exists(branch):
            git("checkout", "--quiet", branch, cwd=d)
            return "reused, on its branch as it was"
        git("checkout", "--quiet", "-b", branch, self.base, cwd=d)
        return f"reused, a new branch from {self.base}"

    def clean(self, d: Path) -> None:
        """Back to nothing of any item's: detached at the base, its branch left in the repository for the record."""
        git("checkout", "--quiet", "--detach", self.base, cwd=d)
        git("clean", "-fdq", cwd=d)

    def remove(self, d: Path) -> None:
        """The worktree removed (the owner freeing a quarantined one): only this one, by its path."""
        git("worktree", "remove", "--force", str(d), cwd=self.repo, check=False)
        git("worktree", "prune", cwd=self.repo, check=False)

    def writes(self, d: Path, branch: str) -> list[str]:
        """What a session working in ``d`` must be able to write besides it, for git to commit there: the objects, this
        worktree's own folder, and its branch's ref and log, in the repository's common git directory."""
        common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=d))
        own = Path(git("rev-parse", "--path-format=absolute", "--git-dir", cwd=d))
        head = branch.rsplit("/", 1)[0] if "/" in branch else ""
        refs = common / "refs" / "heads" / head if head else common / "refs" / "heads"
        logs = common / "logs" / "refs" / "heads" / head if head else common / "logs" / "refs" / "heads"
        (logs).mkdir(parents=True, exist_ok=True)
        return [str(common / "objects"), str(own), str(refs), str(logs)]
