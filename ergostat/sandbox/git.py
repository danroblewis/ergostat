"""Git on a work copy, run by ergostat only and never inside the sandbox: no system or global config, explicit
``GIT_DIR``, ``GIT_COMMON_DIR`` and ``GIT_WORK_TREE``, no fsmonitor, hooks, signing, external diff, textconv or filter
driver, and the work copy's ``.git`` pointer, its ``commondir`` and the worktree's back-pointer checked against what
ergostat made before every call. The sandboxed program cannot write any of them (``seatbelt.py``, ``bwrap.py``); the
check catches the day it could."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
       "GIT_ATTR_NOSYSTEM": "1", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_PAGER": "cat", "GIT_EDITOR": "true",
       "GIT_ASKPASS": "true", "GIT_SSH_COMMAND": "false"}
SAFE = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
        "-c", "tag.gpgsign=false", "-c", "core.attributesFile=/dev/null", "-c", "core.untrackedCache=false"]
DIFFS = {"diff", "show", "log", "diff-tree", "diff-index", "diff-files", "format-patch"}


class Tampered(RuntimeError):
    """The work copy's git metadata is not what ergostat made: no git command is run on it."""


def _real(p) -> str:
    return os.path.realpath(p)


def _git(args: list[str], env: dict, cwd: str, check: bool, input: str | None = None) -> subprocess.CompletedProcess:
    e = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/"), **ENV, **env}
    p = subprocess.run(["git", *args], cwd=cwd, env=e, input=input, capture_output=True, text=True, timeout=120)
    if check and p.returncode:
        raise subprocess.CalledProcessError(p.returncode, ["git", *args], p.stdout, p.stderr)
    return p


class Repo:
    """A work copy ergostat made: ``work``, its git folder (``gitdir``) and the repository's common folder
    (``common``; the same as ``gitdir`` for a plain clone)."""

    def __init__(self, work, gitdir, common=None, env: dict | None = None):
        self.work, self.gitdir = _real(work), _real(gitdir)
        self.common = _real(common or gitdir)
        self.env = dict(env or {})

    @classmethod
    def worktree(cls, repo, work, branch: str, start: str = "HEAD", env: dict | None = None) -> Repo:
        """Make ``work`` a new worktree of ``repo`` on a new ``branch``; its git folder stays in the repository."""
        main = cls(repo, Path(repo) / ".git", env=env)
        main("worktree", "add", "-b", branch, str(work), start)
        gitdir = _real(Path(work, ".git").read_text().removeprefix("gitdir:").strip())
        return cls(work, gitdir, main.common, env)

    def verify(self) -> None:
        dot = os.path.join(self.work, ".git")
        if os.path.islink(dot):
            raise Tampered(f"{dot} is a link")
        if self.gitdir == self.common:
            if not os.path.isdir(dot) or _real(dot) != self.gitdir:
                raise Tampered(f"{dot} is not the git folder ergostat made")
            return
        try:
            pointer = Path(dot).read_text()
            common = Path(self.gitdir, "commondir").read_text().strip()
            back = Path(self.gitdir, "gitdir").read_text().strip()
        except OSError as e:
            raise Tampered(f"git metadata missing: {e}") from None
        if not pointer.startswith("gitdir:") or _real(pointer[7:].strip()) != self.gitdir:
            raise Tampered(f"{dot} points elsewhere: {pointer.strip()[:200]}")
        if _real(os.path.join(self.gitdir, common)) != self.common:
            raise Tampered(f"{self.gitdir}/commondir points elsewhere: {common[:200]}")
        if _real(back) != _real(dot) or os.path.dirname(self.gitdir) != os.path.join(self.common, "worktrees"):
            raise Tampered(f"{self.gitdir} is not this work copy's worktree folder")

    def _env(self) -> dict:
        return {**self.env, "GIT_DIR": self.gitdir, "GIT_COMMON_DIR": self.common, "GIT_WORK_TREE": self.work}

    def _filters(self) -> list[str]:
        """Every filter driver the repository's config names, blanked: no clean, smudge or process command runs."""
        p = _git([*SAFE, "config", "--name-only", "--get-regexp", r"^filter\."], self._env(), self.work, False)
        drivers = {k.rsplit(".", 1)[0] for k in p.stdout.split()}
        return [x for d in sorted(drivers) for k in ("clean", "smudge", "process")
                for x in ("-c", f"{d}.{k}=")] + [x for d in sorted(drivers) for x in ("-c", f"{d}.required=false")]

    def __call__(self, *args: str, check: bool = True, input: str | None = None) -> str:
        """Run ``git ARGS`` on the work copy after checking its metadata; returns its output."""
        self.verify()
        args = list(args)
        if args and args[0] in DIFFS:
            args[1:1] = ["--no-ext-diff", "--no-textconv"]
        p = _git([*SAFE, *self._filters(), *args], self._env(), self.work, check, input)
        return p.stdout
