"""Disk hygiene (dev/model/resources.yaml, the block disk-cleanup): removes what the factory made and no longer needs,
by name, and nothing else.

  - session folders, `<live>/sessions/<branch>-<role>-<YYYYmmddHHMMSS>-<6 hex>` (agents.scratch), older than
    [resources] session_keep_hours by their name and their time;
  - installed versions, `<live>/<40-hex sha>` that are worktrees of the checkout (live.install), other than current,
    previous, and any younger than the same hours (one installed and waiting for its switch): removed with
    `git worktree remove`, never by hand.

    cleanup.py [--dry-run]    remove them (or only say which), and say what was freed"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402

SESSION = re.compile(r"^[a-z0-9][a-z0-9-]*-(\d{14})-[0-9a-f]{6}$")
SHA = re.compile(r"^[0-9a-f]{40}$")


def keep_seconds(cfg: dict) -> float:
    return float(cfg.get("resources", {}).get("session_keep_hours", 24)) * 3600


def kept(live: Path) -> set[str]:
    return {Path(os.readlink(live / n)).name for n in ("current", "previous") if (live / n).is_symlink()}


def is_worktree(cfg: dict, d: Path) -> bool:
    """A worktree of the checkout: its .git a file naming <checkout>/.git/worktrees/<its name>."""
    try:
        said = (d / ".git").read_text().strip() if (d / ".git").is_file() else ""
    except OSError:
        return False
    want = fac.path(cfg, "checkout") / ".git" / "worktrees" / d.name
    return said in (f"gitdir: {want}", f"gitdir: {want.resolve()}")


def sessions(cfg: dict, now: float | None = None, every: bool = False) -> list[Path]:
    """The session folders the factory made (past their time, unless ``every``)."""
    now, root = now or time.time(), fac.path(cfg, "live") / "sessions"
    out = []
    for d in sorted(root.iterdir()) if root.is_dir() and not root.is_symlink() else []:
        m = SESSION.match(d.name)
        if not m or d.is_symlink() or not d.is_dir():
            continue
        born = time.mktime(time.strptime(m[1], "%Y%m%d%H%M%S"))
        if every or now - max(born, d.stat().st_mtime) > keep_seconds(cfg):
            out.append(d)
    return out


def installs(cfg: dict, now: float | None = None, every: bool = False) -> list[Path]:
    """The installed versions other than current and previous (past their time, unless ``every``)."""
    now, live = now or time.time(), fac.path(cfg, "live")
    keep = kept(live)
    return [d for d in sorted(live.iterdir()) if live.is_dir() and SHA.match(d.name) and d.name not in keep
            and not d.is_symlink() and d.is_dir() and is_worktree(cfg, d)
            and (every or now - d.stat().st_mtime > keep_seconds(cfg))] if live.is_dir() else []


def du(paths: list[Path]) -> float:
    if not paths:
        return 0.0
    try:
        out = subprocess.run(["du", "-sk", *map(str, paths)], capture_output=True, text=True, timeout=120).stdout
    except subprocess.TimeoutExpired:
        return float("nan")
    return round(sum(int(x.split()[0]) for x in out.splitlines() if x.split()[:1] and x.split()[0].isdigit())
                 / 2**20, 2)


def sizes(cfg: dict) -> dict:
    """GB of the factory's session folders and of its installs other than current and previous (a sensor's)."""
    s, i = du(sessions(cfg, every=True)), du(installs(cfg, every=True))
    return {"sessions-disk": s, "installs-disk": i, "factory-disk": round(s + i, 2)}


def remove(cfg: dict, d: Path) -> None:
    if SHA.match(d.name):
        fac.git(fac.path(cfg, "checkout"), "worktree", "remove", "--force", str(d))
        return
    if d.resolve().parent != (fac.path(cfg, "live") / "sessions").resolve():
        raise ValueError(f"{d} is not in the sessions folder")

    def writable(fn, p, _):                         # (git's objects are read-only)
        os.chmod(p, stat.S_IRWXU)
        fn(p)
    shutil.rmtree(d, onexc=writable)


def main(argv: list[str]) -> int:
    cfg = fac.config()
    gone = [*sessions(cfg), *installs(cfg)]
    freed = du(gone)
    for d in gone:
        print(("would remove " if "--dry-run" in argv else "removing ") + str(d), flush=True)
        if "--dry-run" not in argv:
            remove(cfg, d)
    if "--dry-run" not in argv and any(SHA.match(d.name) for d in gone):
        fac.git(fac.path(cfg, "checkout"), "worktree", "prune", check=False)
    print(f"{len(gone)} folders, {freed:g} GB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
