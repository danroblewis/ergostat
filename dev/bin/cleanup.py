"""Disk hygiene (dev/model/resources.yaml, the block disk-cleanup): removes what the factory made and no longer needs,
by name, and nothing else.

  - session folders, `<live>/sessions/<branch>-<role>-<YYYYmmddHHMMSS>-<6 hex>` (agents.scratch), older than
    [resources] session_keep_hours by their name and their time, and Claude Code's folder for each session,
    `<item>-<role>-<n>-claude-<8 hex>` (sessions.py: its transcript is already copied to run/sessions/), by its time;
    and, sooner, either kind of a finished gap (`finished`: its work is on its branch), counted in run/resources/;
  - installed versions, `<live>/<40-hex sha>` that are worktrees of the checkout (live.install), other than current,
    previous, any younger than the same hours, and any whose switch waits (installed, approved or draining, read from
    the record: an approved switch can wait a day): removed with `git worktree remove`, never by hand.

    cleanup.py [--dry-run]    remove them (or only say which), and say what was freed"""

from __future__ import annotations

import contextlib
import fcntl
import json
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

SESSION = re.compile(r"^[a-z0-9][a-z0-9_-]*-(\d{14})-[0-9a-f]{6}$")
CLAUDE = re.compile(r"^[a-z0-9][a-z0-9_-]*-\d+-claude-[0-9a-f]{8}$")      # Claude Code's folder for one (sessions.py)
SHA = re.compile(r"^[0-9a-f]{40}$")
WAITING = ("installed", "approved", "draining")                         # an upgrade whose switch waits (drain.py's)
QUIET = 600                       # seconds: a session folder touched more recently than this is never removed early


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
        if not (m or CLAUDE.match(d.name)) or d.is_symlink() or not d.is_dir():
            continue
        born = time.mktime(time.strptime(m[1], "%Y%m%d%H%M%S")) if m else 0
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


def owners(gaps: list[dict], done: set[str]) -> dict[str, bool]:
    """Each name a gap's session folders begin with (its branch, agents.clone's; the slug of its id, sessions.py's for
    Claude Code's folders), and whether every gap of that name is in a ``done`` state (a branch a later gap continues
    is finished only when that one is too)."""
    out: dict[str, bool] = {}
    for g in gaps:
        names = {fac.slug(g["id"].split("/", 1)[-1], 64)}
        with contextlib.suppress(ValueError):              # (a branch no clone could be made on: no folder has it)
            names.add(fac.branch_of(g))
        for n in names - {""}:
            out[n] = out.get(n, True) and g["state"] in done
    return out


def touched(d: Path) -> float:
    """The newest change in a session folder: itself, the entries in it and in its folders (Claude Code's transcript,
    the clone's files) and in its clone's .git. One that cannot be read: now (so kept)."""
    try:
        top = list(d.iterdir())
        deeper = [p for t in [*top, d / "work" / ".git"] if t.is_dir() and not t.is_symlink() for p in t.iterdir()]
        return max(p.lstat().st_mtime for p in [d, *top, *deeper])
    except OSError:
        return time.time()


def docker(*args: str) -> str:
    got = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)
    if got.returncode:
        raise RuntimeError(f"docker {args[0]}: {got.stderr.strip()[:200]}")
    return got.stdout


def mounted() -> list[Path]:
    """The host folders the running containers mount. Docker not answering (or a container gone between the two
    asks) raises: nothing is then removed early."""
    ids = docker("ps", "-q").split()
    out = docker("inspect", "--format", "{{range .Mounts}}{{println .Source}}{{end}}", *ids) if ids else ""
    return [Path(x.strip()).resolve() for x in out.splitlines() if x.strip()]


def finished(cfg: dict, found: list[Path], now: float | None = None) -> list[Path]:
    """Of the session folders ``found``, those of finished gaps: every gap whose name the folder begins with is in a
    state of [resources] finished_states (none set: none), it was not touched in the last QUIET seconds, and no
    running container mounts it (or a folder holding it, or one in it). Raises when the record, the setting or Docker
    cannot be read, so nothing is removed early."""
    done = cfg.get("resources", {}).get("finished_states", [])
    if not isinstance(done, list) or not all(isinstance(s, str) for s in done):
        raise ValueError(f"[resources] finished_states is not a list of states: {done!r}")
    if not done or not found:
        return []
    names, mounts, now = owners(fac.items("gap"), set(done)), mounted(), now or time.time()
    out = []
    for d in found:
        own, r = [ok for n, ok in names.items() if d.name.startswith(n + "-")], d.resolve()
        if own and all(own) and now - touched(d) > QUIET and not any(
                m == r or m in r.parents or r in m.parents for m in mounts):
            out.append(d)
    return out


def counted(cfg: dict) -> int | None:
    """The session folders removed early since the count began (run/resources/cleanup.json): 0 before any; None when
    the file cannot be read."""
    try:
        return int(json.loads((fac.path(cfg, "run") / "resources" / "cleanup.json").read_text())["early-total"])
    except FileNotFoundError:
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        return None


def count(cfg: dict, early: int, gb: float) -> None:
    """Add this pass's early removals to run/resources/cleanup.json, under its lock (a count unreadable starts again,
    its `since` saying when)."""
    d = fac.run_dir(cfg, "resources")
    with open(d / "cleanup.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            was = json.loads((d / "cleanup.json").read_text())
            total, since = int(was["early-total"]), float(was["since"])
        except (OSError, ValueError, KeyError, TypeError):
            total, since = 0, time.time()
        new = {"since": since, "at": time.time(), "early": early, "early-gb": gb, "early-total": total + early}
        (d / "cleanup.new").write_text(json.dumps(new))
        (d / "cleanup.new").replace(d / "cleanup.json")


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
    """GB of the factory's session folders and of its installs other than current and previous, and the session
    folders removed early so far (a sensor's)."""
    s, i = du(sessions(cfg, every=True)), du(installs(cfg, every=True))
    return {"sessions-disk": s, "installs-disk": i, "factory-disk": round(s + i, 2),
            "sessions-removed-early": counted(cfg)}


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


def waiting() -> set[str]:
    """The versions whose switch waits (installed, approved or draining: drain.py), from the record; one that cannot
    be read stops the removal of installs (raised)."""
    return {u["fields"].get("sha") for u in fac.items("upgrade") if u["state"] in WAITING}


def main(argv: list[str]) -> int:
    cfg = fac.config()
    old = installs(cfg)
    keep = waiting() if old else set()
    aged = sessions(cfg)
    try:
        early = finished(cfg, [d for d in sessions(cfg, every=True) if d not in aged])
    except Exception as e:                              # (the record, the setting or Docker unread: none early)
        print(f"no session folder removed early: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        early = []
    gone = [*aged, *(d for d in old if d.name not in keep)]
    freed, early_gb, late = du(gone), du(early), []
    for d in [*gone, *early]:
        if d in early and time.time() - touched(d) <= QUIET:     # (touched since it was chosen: kept)
            late.append(d)
            continue
        print(("would remove " if "--dry-run" in argv else "removing ") + str(d), flush=True)
        if "--dry-run" not in argv:
            remove(cfg, d)
    if late:
        early, early_gb = [d for d in early if d not in late], round(early_gb - du(late), 2)
    if "--dry-run" not in argv and any(SHA.match(d.name) for d in gone):
        fac.git(fac.path(cfg, "checkout"), "worktree", "prune", check=False)
    if "--dry-run" not in argv and early:
        count(cfg, len(early), early_gb)
    print(f"{len(gone) + len(early)} folders, {freed + early_gb:g} GB ({len(early)} of finished gaps, "
          f"{early_gb:g} GB, early)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
