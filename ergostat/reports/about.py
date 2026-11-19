"""What a report says about the ergostat that wrote it: its version and commit, Python and the OS. Read from this
machine only: the package's metadata, and the checkout's git HEAD when it runs from one (read as files, no git run)."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

from .. import __version__

PACKAGE = Path(__file__).resolve().parent.parent      # .../ergostat (the package folder)


def _commit_of_checkout(root: Path) -> str | None:
    """HEAD of the git checkout ergostat runs from, read from .git's files (a branch's ref, or packed-refs)."""
    git = root / ".git"
    try:
        if git.is_file():                                  # a worktree: "gitdir: PATH"
            git = Path(git.read_text().split(":", 1)[1].strip())
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return head[:12]
        ref = head[5:]
        common = git
        if (git / "commondir").exists():
            common = (git / (git / "commondir").read_text().strip()).resolve()
        for base in (git, common):
            f = base / ref
            if f.exists():
                return f.read_text().strip()[:12]
        packed = common / "packed-refs"
        if packed.exists():
            for line in packed.read_text().splitlines():
                if line.endswith(" " + ref):
                    return line.split()[0][:12]
    except (OSError, IndexError, ValueError):
        return None
    return None


def _commit_of_install() -> str | None:
    """The commit pip or uv installed from (direct_url.json, PEP 610), when installed from git."""
    try:
        from importlib.metadata import distribution
        text = distribution("ergostat").read_text("direct_url.json")
        if text:
            return (json.loads(text).get("vcs_info") or {}).get("commit_id", "")[:12] or None
    except Exception:
        return None
    return None


def commit() -> str | None:
    return _commit_of_checkout(PACKAGE.parent) or _commit_of_install()


def os_name() -> str:
    if sys.platform == "darwin":
        mac = platform.mac_ver()[0]
        return f"macOS {mac} {platform.machine()}".strip()
    return f"{platform.system()} {platform.release()} {platform.machine()}".strip()


def info() -> dict:
    return {"ergostat": __version__, "commit": commit(), "python": platform.python_version(), "os": os_name()}


def line(i: dict | None = None) -> str:
    i = i or info()
    return (f"ergostat {i['ergostat']}" + (f" (commit {i['commit']})" if i.get("commit") else "") +
            f", Python {i['python']}, {i['os']}")
